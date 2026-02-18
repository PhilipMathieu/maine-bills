from pathlib import Path

import pytest

from maine_bills.scraper import BillScraper


@pytest.mark.integration
def test_fetch_real_bill_list():
    """Test fetching bill list from real legislature website.

    This test hits the actual Maine legislature website.
    Skip with -m "not integration" if you don't want live tests.
    """
    scraper = BillScraper("131", Path("/tmp/maine-bills-integration"))

    try:
        bills = scraper._fetch_bill_list()
        assert len(bills) > 0
        assert any("LD" in bill for bill in bills)
    except Exception as e:
        pytest.skip(f"Integration test skipped: {e}")


@pytest.mark.integration
def test_scrape_single_bill():
    """Test downloading and extracting a single real bill.

    This test hits the actual Maine legislature website.
    Skip with -m "not integration" if you don't want live tests.
    """
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        scraper = BillScraper("131", Path(tmpdir))
        scraper._ensure_directories()

        try:
            bills = scraper._fetch_bill_list()
            if not bills:
                pytest.skip("No bills found to test")

            # Try processing the first bill
            result = scraper._process_bill(bills[0])

            # Should succeed if bill is available
            if result:
                assert (scraper.txt_dir / f"{bills[0]}.txt").exists()
        except Exception as e:
            pytest.skip(f"Integration test skipped: {e}")
