"""Tests for BillRecord and filename parsing in schema.py."""

from unittest.mock import MagicMock

import pytest

from maine_bills.schema import BillRecord, parse_filename

# --- parse_filename tests ---

def test_parse_simple_bill():
    result = parse_filename("131-LD-0686")
    assert result["session"] == 131
    assert result["ld_number"] == "0686"
    assert result["amendment_code"] is None
    assert result["amendment_type"] is None
    assert result["chamber"] is None


def test_parse_committee_amendment():
    result = parse_filename("131-LD-0686-CA_A_H0266")
    assert result["session"] == 131
    assert result["ld_number"] == "0686"
    assert result["amendment_code"] == "CA_A_H0266"
    assert result["amendment_type"] == "Committee Amendment"
    assert result["chamber"] == "House"


def test_parse_house_amendment():
    result = parse_filename("132-LD-0001-HA_A_H0001")
    assert result["amendment_type"] == "House Amendment"
    assert result["chamber"] == "House"


def test_parse_senate_amendment():
    result = parse_filename("130-LD-0100-SA_B_S0042")
    assert result["amendment_type"] == "Senate Amendment"
    assert result["chamber"] == "Senate"
    assert result["amendment_code"] == "SA_B_S0042"


def test_parse_invalid_filename_raises():
    with pytest.raises(ValueError, match="Unexpected filename format"):
        parse_filename("not-a-valid-filename")


def test_parse_missing_ld_prefix_raises():
    with pytest.raises(ValueError, match="Unexpected filename format"):
        parse_filename("131-0686")


# --- BillRecord.from_filename_and_bill_document tests ---

def _make_bill_doc(**kwargs):
    """Create a mock BillDocument with sensible defaults."""
    doc = MagicMock()
    doc.body_text = kwargs.get("body_text", "Bill text here.")
    doc.extraction_confidence = kwargs.get("extraction_confidence", 0.95)
    doc.title = kwargs.get("title", "An Act Relating to Education")
    doc.sponsors = kwargs.get("sponsors", ["Rep. Smith"])
    doc.committee = kwargs.get("committee", "Committee on Education")
    doc.amended_code_refs = kwargs.get("amended_code_refs", [])
    return doc


def test_from_filename_and_bill_doc_basic():
    doc = _make_bill_doc()
    record = BillRecord.from_filename_and_bill_document(
        filename="131-LD-0686",
        bill_doc=doc,
        base_url="http://lldc.mainelegislature.org/Open/LDs/131/",
    )
    assert record.session == 131
    assert record.ld_number == "0686"
    assert record.document_type == "bill"
    assert record.amendment_code is None
    assert record.text == "Bill text here."
    assert record.extraction_confidence == 0.95
    assert record.title == "An Act Relating to Education"
    assert record.sponsors == ["Rep. Smith"]
    assert record.source_filename == "131-LD-0686"
    assert record.source_url == "http://lldc.mainelegislature.org/Open/LDs/131/131-LD-0686.pdf"


def test_from_filename_and_bill_doc_amendment():
    doc = _make_bill_doc()
    record = BillRecord.from_filename_and_bill_document(
        filename="131-LD-0686-CA_A_H0266",
        bill_doc=doc,
        base_url="http://lldc.mainelegislature.org/Open/LDs/131/",
    )
    assert record.amendment_code == "CA_A_H0266"
    assert record.amendment_type == "Committee Amendment"
    assert record.chamber == "House"


def test_from_filename_and_bill_doc_scraped_at_is_iso8601():
    doc = _make_bill_doc()
    record = BillRecord.from_filename_and_bill_document(
        filename="131-LD-0001",
        bill_doc=doc,
        base_url="http://example.com/",
    )
    # ISO 8601 with timezone: ends with +00:00 or Z
    assert "T" in record.scraped_at
    assert len(record.scraped_at) > 10
