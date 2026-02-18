from datetime import UTC
from unittest.mock import MagicMock, Mock

import pandas as pd
import pytest

from maine_bills.scraper import BillScraper


@pytest.fixture
def scraper():
    return BillScraper(131, workers=2)


# --- Initialization ---

def test_scraper_init(scraper):
    assert scraper.session == 131
    assert scraper.session_url == "http://lldc.mainelegislature.org/Open/LDs/131/"
    assert scraper.workers == 2


def test_scraper_default_workers():
    s = BillScraper(131)
    assert s.workers >= 4  # sensible default for parallel downloads


# --- _fetch_bill_list ---

def test_fetch_bill_list_returns_filenames(scraper, mocker):
    mock_html = """
    <html>
        <a href="../">Parent</a>
        <a href="131-LD-0001.pdf">Link 1</a>
        <a href="131-LD-0002.pdf">Link 2</a>
        <a href="index.html">Index</a>
        <a>No href at all</a>
    </html>
    """
    mock_response = Mock()
    mock_response.content = mock_html.encode()
    mocker.patch("maine_bills.scraper.requests.get", return_value=mock_response)

    result = scraper._fetch_bill_list()

    assert result == ["131-LD-0001", "131-LD-0002"]


def test_fetch_bill_list_raises_on_network_error(scraper, mocker):
    import requests
    mocker.patch(
        "maine_bills.scraper.requests.get",
        side_effect=requests.RequestException("Network error"),
    )
    with pytest.raises(requests.RequestException):
        scraper._fetch_bill_list()


# --- _download_and_extract_bill ---

def test_download_and_extract_bill_returns_bill_record(scraper, mocker):
    from maine_bills.schema import BillRecord

    mock_response = Mock()
    mock_response.content = b"%PDF fake content"
    mocker.patch("maine_bills.scraper.requests.get", return_value=mock_response)

    mock_doc = MagicMock()
    mock_doc.body_text = "Bill text"
    mock_doc.extraction_confidence = 0.9
    mock_doc.title = "An Act"
    mock_doc.sponsors = []
    mock_doc.committee = None
    mock_doc.amended_code_refs = []
    mocker.patch("maine_bills.scraper.TextExtractor.extract_bill_document", return_value=mock_doc)

    result = scraper._download_and_extract_bill("131-LD-0001")

    assert isinstance(result, BillRecord)
    assert result.session == 131
    assert result.ld_number == "0001"
    assert result.text == "Bill text"


def test_download_retries_on_timeout(scraper, mocker):
    """A transient timeout should be retried, succeeding on the second attempt."""
    import requests as req

    call_count = 0

    def flaky_get(url, timeout):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise req.exceptions.ConnectTimeout("timeout")
        m = Mock()
        m.content = b"%PDF fake"
        return m

    mocker.patch("maine_bills.scraper.requests.get", side_effect=flaky_get)
    mocker.patch("maine_bills.scraper.TextExtractor.extract_bill_document",
                 return_value=MagicMock(body_text="", extraction_confidence=0.0,
                                       title=None, sponsors=[], committee=None,
                                       amended_code_refs=[]))

    result = scraper._download_and_extract_bill("131-LD-0001")

    assert call_count == 2
    assert result is not None


def test_download_fails_after_max_retries(scraper, mocker):
    """Persistent timeouts should eventually raise and be skipped by scrape_session."""
    import requests as req

    mocker.patch("maine_bills.scraper.requests.get",
                 side_effect=req.exceptions.ConnectTimeout("always fails"))

    with pytest.raises(Exception):
        scraper._download_and_extract_bill("131-LD-0001")


def test_download_and_extract_bill_cleans_up_temp_file(scraper, mocker):
    """Temp PDF file should be deleted after extraction."""
    mock_response = Mock()
    mock_response.content = b"%PDF fake"
    mocker.patch("maine_bills.scraper.requests.get", return_value=mock_response)

    captured_paths = []

    def capture_and_mock(path):
        captured_paths.append(path)
        return MagicMock(body_text="", extraction_confidence=0.0,
                         title=None, sponsors=[], committee=None, amended_code_refs=[])

    mocker.patch("maine_bills.scraper.TextExtractor.extract_bill_document",
                 side_effect=capture_and_mock)

    scraper._download_and_extract_bill("131-LD-0001")

    assert len(captured_paths) == 1
    assert not captured_paths[0].exists(), "Temp file should be deleted after extraction"


# --- scrape_session ---

def test_scrape_session_returns_dataframe(scraper, mocker):
    from datetime import datetime

    from maine_bills.schema import BillRecord

    mocker.patch.object(scraper, "_fetch_bill_list", return_value=["131-LD-0001", "131-LD-0002"])

    def make_record(filename):
        return BillRecord(
            session=131, ld_number=filename.split("-")[2], document_type="bill",
            amendment_code=None, amendment_type=None, chamber=None,
            text="text", extraction_confidence=0.9,
            source_filename=filename, source_url="http://example.com",
            scraped_at=datetime.now(UTC).isoformat(),
        )

    mocker.patch.object(scraper, "_download_and_extract_bill", side_effect=make_record)

    result = scraper.scrape_session()

    assert isinstance(result, pd.DataFrame)
    assert len(result) == 2
    assert "session" in result.columns
    assert "ld_number" in result.columns
    assert "text" in result.columns


def test_scrape_session_skips_unrecognized_filenames(scraper, mocker):
    mocker.patch.object(scraper, "_fetch_bill_list",
                        return_value=["131-LD-0001", "not-a-valid-name"])

    from datetime import datetime

    from maine_bills.schema import BillRecord

    def make_record(filename):
        return BillRecord(
            session=131, ld_number="0001", document_type="bill",
            amendment_code=None, amendment_type=None, chamber=None,
            text="text", extraction_confidence=0.9,
            source_filename=filename, source_url="",
            scraped_at=datetime.now(UTC).isoformat(),
        )

    mocker.patch.object(scraper, "_download_and_extract_bill", side_effect=make_record)

    result = scraper.scrape_session()

    assert len(result) == 1


def test_scrape_session_processes_all_bills_in_parallel(mocker):
    """Workers > 1 should still return all records (order may vary)."""
    import time

    scraper = BillScraper(131, workers=4)
    filenames = [f"131-LD-{str(i).zfill(4)}" for i in range(1, 9)]
    mocker.patch.object(scraper, "_fetch_bill_list", return_value=filenames)

    from datetime import datetime

    from maine_bills.schema import BillRecord

    def slow_make_record(filename):
        time.sleep(0.01)
        return BillRecord(
            session=131, ld_number=filename.split("-")[2], document_type="bill",
            amendment_code=None, amendment_type=None, chamber=None,
            text="text", extraction_confidence=0.9,
            source_filename=filename, source_url="",
            scraped_at=datetime.now(UTC).isoformat(),
        )

    mocker.patch.object(scraper, "_download_and_extract_bill", side_effect=slow_make_record)

    result = scraper.scrape_session()

    assert len(result) == 8
    assert set(result["ld_number"]) == {str(i).zfill(4) for i in range(1, 9)}


def test_scrape_session_continues_after_individual_failure(scraper, mocker):
    mocker.patch.object(scraper, "_fetch_bill_list",
                        return_value=["131-LD-0001", "131-LD-0002"])

    call_count = 0

    def fail_first(filename):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("Download failed")
        from datetime import datetime

        from maine_bills.schema import BillRecord
        return BillRecord(
            session=131, ld_number="0002", document_type="bill",
            amendment_code=None, amendment_type=None, chamber=None,
            text="text", extraction_confidence=0.9,
            source_filename=filename, source_url="",
            scraped_at=datetime.now(UTC).isoformat(),
        )

    mocker.patch.object(scraper, "_download_and_extract_bill", side_effect=fail_first)

    result = scraper.scrape_session()

    assert len(result) == 1
    assert result.iloc[0]["ld_number"] == "0002"
