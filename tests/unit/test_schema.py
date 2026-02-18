"""Tests for schema.py filename parsing and BillRecord creation."""

from datetime import datetime
from unittest.mock import Mock

import pytest

from maine_bills.schema import (
    AMENDMENT_TYPES,
    CHAMBER_MAP,
    DOCUMENT_TYPE_MAP,
    FILENAME_PATTERN,
    BillRecord,
    parse_filename,
)


class TestFilenamePattern:
    """Test the FILENAME_PATTERN regex directly."""

    def test_pattern_matches_original_bill(self):
        """Test pattern matches original bill without amendments."""
        match = FILENAME_PATTERN.match("131-LD-0001")
        assert match is not None
        assert match.group("session") == "131"
        assert match.group("bill_type") == "LD"
        assert match.group("number") == "0001"
        assert match.group("amendment") is None

    def test_pattern_matches_single_amendment(self):
        """Test pattern matches single-level amendment."""
        match = FILENAME_PATTERN.match("131-LD-0686-CA_A_H0266")
        assert match is not None
        assert match.group("session") == "131"
        assert match.group("number") == "0686"
        assert match.group("amendment") == "CA_A_H0266"

    def test_pattern_matches_double_amendment(self):
        """Test pattern matches double-level (nested) amendment."""
        match = FILENAME_PATTERN.match("132-LD-0004-CA_A_SA_A_S337")
        assert match is not None
        assert match.group("session") == "132"
        assert match.group("number") == "0004"
        assert match.group("amendment") == "CA_A_SA_A_S337"

    def test_pattern_matches_double_amendment_hyphen_separator(self):
        """Test pattern matches double amendment with hyphen separator (older sessions 122-129)."""
        match = FILENAME_PATTERN.match("122-LD-0001-CA_A-HA_A_H5")
        assert match is not None
        assert match.group("session") == "122"
        assert match.group("number") == "0001"
        assert match.group("amendment") == "CA_A-HA_A_H5"

    def test_pattern_matches_sp_bill(self):
        """Test pattern matches Senate Paper (SP) bill type."""
        match = FILENAME_PATTERN.match("131-SP-0042")
        assert match is not None
        assert match.group("bill_type") == "SP"
        assert match.group("number") == "0042"
        assert match.group("amendment") is None

    def test_pattern_matches_hp_bill(self):
        """Test pattern matches House Paper (HP) bill type."""
        match = FILENAME_PATTERN.match("130-HP-0100")
        assert match is not None
        assert match.group("bill_type") == "HP"
        assert match.group("number") == "0100"

    def test_pattern_matches_ho_bill_with_amendment(self):
        """Test pattern matches House Order (HO) with amendment."""
        match = FILENAME_PATTERN.match("131-HO-0021-HA_A_H21")
        assert match is not None
        assert match.group("bill_type") == "HO"
        assert match.group("number") == "0021"
        assert match.group("amendment") == "HA_A_H21"

    def test_pattern_rejects_invalid_format(self):
        """Test pattern rejects malformed filenames."""
        assert FILENAME_PATTERN.match("invalid") is None
        assert FILENAME_PATTERN.match("131-LD") is None
        assert FILENAME_PATTERN.match("LD-0001") is None
        assert FILENAME_PATTERN.match("131-LD-0001-INVALID") is None
        assert FILENAME_PATTERN.match("131-XX-0001") is None


class TestParseFilename:
    """Test parse_filename() function."""

    def test_parse_original_bill(self):
        """Test parsing original bill without amendments."""
        result = parse_filename("131-LD-0001")
        assert result == {
            "session": 131,
            "ld_number": "0001",
            "bill_type": "LD",
            "document_type": "bill",
            "amendment_code": None,
            "amendment_type": None,
            "chamber": None,
        }

    def test_parse_committee_amendment_house(self):
        """Test parsing Committee Amendment filed in House."""
        result = parse_filename("131-LD-0686-CA_A_H0266")
        assert result["session"] == 131
        assert result["ld_number"] == "0686"
        assert result["amendment_code"] == "CA_A_H0266"
        assert result["amendment_type"] == "Committee Amendment"
        assert result["chamber"] == "House"

    def test_parse_committee_amendment_senate(self):
        """Test parsing Committee Amendment filed in Senate."""
        result = parse_filename("131-LD-0001-CA_A_S0001")
        assert result["session"] == 131
        assert result["ld_number"] == "0001"
        assert result["amendment_code"] == "CA_A_S0001"
        assert result["amendment_type"] == "Committee Amendment"
        assert result["chamber"] == "Senate"

    def test_parse_house_amendment(self):
        """Test parsing House Amendment."""
        result = parse_filename("131-LD-0050-HA_A_H0100")
        assert result["amendment_code"] == "HA_A_H0100"
        assert result["amendment_type"] == "House Amendment"
        assert result["chamber"] == "House"

    def test_parse_senate_amendment(self):
        """Test parsing Senate Amendment."""
        result = parse_filename("131-LD-0075-SA_A_S0200")
        assert result["amendment_code"] == "SA_A_S0200"
        assert result["amendment_type"] == "Senate Amendment"
        assert result["chamber"] == "Senate"

    def test_parse_double_amendment_ca_sa(self):
        """Test parsing double amendment: Senate Amendment to Committee Amendment."""
        result = parse_filename("132-LD-0004-CA_A_SA_A_S337")
        assert result["session"] == 132
        assert result["ld_number"] == "0004"
        assert result["amendment_code"] == "CA_A_SA_A_S337"
        # Should extract type from FIRST segment (CA = Committee Amendment)
        assert result["amendment_type"] == "Committee Amendment"
        # Should extract chamber from the amendment code (S337 = Senate)
        assert result["chamber"] == "Senate"

    def test_parse_double_amendment_ca_ha(self):
        """Test parsing double amendment: House Amendment to Committee Amendment."""
        result = parse_filename("132-LD-0029-CA_A_HA_A_H126")
        assert result["session"] == 132
        assert result["ld_number"] == "0029"
        assert result["amendment_code"] == "CA_A_HA_A_H126"
        assert result["amendment_type"] == "Committee Amendment"
        assert result["chamber"] == "House"

    def test_parse_double_amendment_real_examples(self):
        """Test parsing real double-amendment examples from session 132."""
        # Real examples from the issue description
        examples = [
            ("132-LD-0004-CA_A_SA_A_S337", "Committee Amendment", "Senate"),
            ("132-LD-0029-CA_A_HA_A_H126", "Committee Amendment", "House"),
            ("132-LD-0030-CA_A_HA_A_H127", "Committee Amendment", "House"),
        ]

        for filename, expected_type, expected_chamber in examples:
            result = parse_filename(filename)
            assert result["amendment_type"] == expected_type
            assert result["chamber"] == expected_chamber

    def test_parse_amendment_version_b(self):
        """Test parsing amendments with version B."""
        result = parse_filename("131-LD-1621-CA_B_H0319")
        assert result["amendment_code"] == "CA_B_H0319"
        assert result["amendment_type"] == "Committee Amendment"
        assert result["chamber"] == "House"

    def test_parse_amendment_version_c(self):
        """Test parsing amendments with version C."""
        result = parse_filename("131-LD-0428-CA_C_H0125")
        assert result["amendment_code"] == "CA_C_H0125"
        assert result["amendment_type"] == "Committee Amendment"
        assert result["chamber"] == "House"

    def test_parse_double_amendment_mixed_versions(self):
        """Test parsing double amendments with different versions."""
        result = parse_filename("131-LD-0424-CA_A_SA_B_S0014")
        assert result["amendment_code"] == "CA_A_SA_B_S0014"
        assert result["amendment_type"] == "Committee Amendment"
        assert result["chamber"] == "Senate"

        result2 = parse_filename("131-LD-0424-CA_A_HA_E_H0019")
        assert result2["amendment_code"] == "CA_A_HA_E_H0019"
        assert result2["amendment_type"] == "Committee Amendment"
        assert result2["chamber"] == "House"

    def test_parse_double_amendment_hyphen_separator(self):
        """Test parsing double amendment with hyphen separator (older sessions 122-129)."""
        result = parse_filename("122-LD-0001-CA_A-HA_A_H5")
        assert result["session"] == 122
        assert result["ld_number"] == "0001"
        assert result["amendment_code"] == "CA_A-HA_A_H5"
        assert result["amendment_type"] == "Committee Amendment"
        assert result["chamber"] == "House"
        assert result["document_type"] == "bill"

    def test_parse_double_amendment_hyphen_separator_senate(self):
        """Test parsing double amendment with hyphen separator, Senate chamber."""
        result = parse_filename("122-LD-0001-CA_A-SA_A_S1")
        assert result["amendment_code"] == "CA_A-SA_A_S1"
        assert result["amendment_type"] == "Committee Amendment"
        assert result["chamber"] == "Senate"

    def test_parse_sp_bill(self):
        """Test parsing Senate Paper (SP) bill type."""
        result = parse_filename("131-SP-0042")
        assert result["session"] == 131
        assert result["ld_number"] == "0042"
        assert result["bill_type"] == "SP"
        assert result["document_type"] == "sp_bill"
        assert result["amendment_code"] is None

    def test_parse_hp_bill(self):
        """Test parsing House Paper (HP) bill type."""
        result = parse_filename("130-HP-0100")
        assert result["bill_type"] == "HP"
        assert result["document_type"] == "hp_bill"

    def test_parse_ho_bill(self):
        """Test parsing House Order (HO) bill type."""
        result = parse_filename("129-HO-0005")
        assert result["bill_type"] == "HO"
        assert result["document_type"] == "ho_bill"

    def test_parse_ho_bill_with_amendment(self):
        """Test parsing House Order with amendment."""
        result = parse_filename("131-HO-0021-HA_A_H21")
        assert result["bill_type"] == "HO"
        assert result["document_type"] == "ho_bill"
        assert result["amendment_code"] == "HA_A_H21"
        assert result["amendment_type"] == "House Amendment"
        assert result["chamber"] == "House"

    def test_parse_invalid_filename_raises_error(self):
        """Test that invalid filenames raise ValueError."""
        with pytest.raises(ValueError, match="Unexpected filename format"):
            parse_filename("invalid-format")

        with pytest.raises(ValueError, match="Unexpected filename format"):
            parse_filename("131-LD")

        with pytest.raises(ValueError, match="Unexpected filename format"):
            parse_filename("LD-0001")


class TestBillRecord:
    """Test BillRecord dataclass."""

    def test_bill_record_creation(self):
        """Test creating a BillRecord with all fields."""
        record = BillRecord(
            session=131,
            ld_number="0001",
            document_type="bill",
            amendment_code=None,
            amendment_type=None,
            chamber=None,
            text="Bill text here",
            extraction_confidence=0.95,
            title="An Act To Do Something",
            sponsors=["Senator Smith", "Representative Jones"],
            committee="Judiciary",
            amended_code_refs=["Title 5", "Title 10"],
            source_url="http://example.com/131-LD-0001.pdf",
            source_filename="131-LD-0001",
            scraped_at="2026-02-18T00:00:00+00:00",
        )

        assert record.session == 131
        assert record.ld_number == "0001"
        assert record.text == "Bill text here"
        assert len(record.sponsors) == 2
        assert record.extraction_confidence == 0.95

    def test_from_filename_and_bill_document_original(self):
        """Test creating BillRecord from original bill filename."""
        # Mock BillDocument
        bill_doc = Mock()
        bill_doc.body_text = "Bill text content"
        bill_doc.extraction_confidence = 0.9
        bill_doc.title = "An Act To Test"
        bill_doc.sponsors = ["Senator Test"]
        bill_doc.committee = "Test Committee"
        bill_doc.amended_code_refs = ["Title 1"]

        record = BillRecord.from_filename_and_bill_document(
            filename="131-LD-0001",
            bill_doc=bill_doc,
            base_url="http://example.com/",
        )

        assert record.session == 131
        assert record.ld_number == "0001"
        assert record.amendment_code is None
        assert record.amendment_type is None
        assert record.chamber is None
        assert record.text == "Bill text content"
        assert record.title == "An Act To Test"
        assert record.sponsors == ["Senator Test"]
        assert record.source_url == "http://example.com/131-LD-0001.pdf"
        assert record.source_filename == "131-LD-0001"

    def test_from_filename_and_bill_document_single_amendment(self):
        """Test creating BillRecord from single-amendment filename."""
        bill_doc = Mock()
        bill_doc.body_text = "Amendment text"
        bill_doc.extraction_confidence = 0.85
        bill_doc.title = "Committee Amendment A"
        bill_doc.sponsors = []
        bill_doc.committee = None
        bill_doc.amended_code_refs = []

        record = BillRecord.from_filename_and_bill_document(
            filename="131-LD-0686-CA_A_H0266",
            bill_doc=bill_doc,
            base_url="http://lldc.mainelegislature.org/Open/LDs/131/",
        )

        assert record.session == 131
        assert record.ld_number == "0686"
        assert record.amendment_code == "CA_A_H0266"
        assert record.amendment_type == "Committee Amendment"
        assert record.chamber == "House"
        assert record.text == "Amendment text"

    def test_from_filename_and_bill_document_double_amendment(self):
        """Test creating BillRecord from double-amendment filename."""
        bill_doc = Mock()
        bill_doc.body_text = "Double amendment text"
        bill_doc.extraction_confidence = 0.88
        bill_doc.title = "Senate Amendment to Committee Amendment"
        bill_doc.sponsors = []
        bill_doc.committee = None
        bill_doc.amended_code_refs = []

        record = BillRecord.from_filename_and_bill_document(
            filename="132-LD-0004-CA_A_SA_A_S337",
            bill_doc=bill_doc,
            base_url="http://lldc.mainelegislature.org/Open/LDs/132/",
        )

        assert record.session == 132
        assert record.ld_number == "0004"
        assert record.amendment_code == "CA_A_SA_A_S337"
        assert record.amendment_type == "Committee Amendment"
        assert record.chamber == "Senate"
        assert record.text == "Double amendment text"
        assert record.source_filename == "132-LD-0004-CA_A_SA_A_S337"

    def test_from_filename_invalid_raises_error(self):
        """Test that invalid filename raises ValueError."""
        bill_doc = Mock()
        bill_doc.body_text = "Text"
        bill_doc.extraction_confidence = 0.9
        bill_doc.title = None
        bill_doc.sponsors = []
        bill_doc.committee = None
        bill_doc.amended_code_refs = []

        with pytest.raises(ValueError, match="Unexpected filename format"):
            BillRecord.from_filename_and_bill_document(
                filename="invalid-format",
                bill_doc=bill_doc,
                base_url="http://example.com/",
            )

    def test_scraped_at_timestamp_format(self):
        """Test that scraped_at timestamp is in ISO format with timezone."""
        bill_doc = Mock()
        bill_doc.body_text = "Text"
        bill_doc.extraction_confidence = 0.9
        bill_doc.title = None
        bill_doc.sponsors = []
        bill_doc.committee = None
        bill_doc.amended_code_refs = []

        record = BillRecord.from_filename_and_bill_document(
            filename="131-LD-0001",
            bill_doc=bill_doc,
            base_url="http://example.com/",
        )

        # Should be ISO format with timezone
        assert "T" in record.scraped_at
        assert "+" in record.scraped_at or "Z" in record.scraped_at
        # Should be parseable back to datetime
        datetime.fromisoformat(record.scraped_at)


class TestAmendmentConstants:
    """Test amendment type and chamber mapping constants."""

    def test_amendment_types_complete(self):
        """Test all expected amendment types are defined."""
        assert "CA" in AMENDMENT_TYPES
        assert "HA" in AMENDMENT_TYPES
        assert "SA" in AMENDMENT_TYPES
        assert AMENDMENT_TYPES["CA"] == "Committee Amendment"
        assert AMENDMENT_TYPES["HA"] == "House Amendment"
        assert AMENDMENT_TYPES["SA"] == "Senate Amendment"

    def test_chamber_map_complete(self):
        """Test both chambers are mapped."""
        assert "H" in CHAMBER_MAP
        assert "S" in CHAMBER_MAP
        assert CHAMBER_MAP["H"] == "House"
        assert CHAMBER_MAP["S"] == "Senate"

    def test_document_type_map_complete(self):
        """Test all bill types are mapped to document types."""
        assert DOCUMENT_TYPE_MAP["LD"] == "bill"
        assert DOCUMENT_TYPE_MAP["SP"] == "sp_bill"
        assert DOCUMENT_TYPE_MAP["HP"] == "hp_bill"
        assert DOCUMENT_TYPE_MAP["HO"] == "ho_bill"


class TestBillRecordDocumentType:
    """Test that BillRecord.from_filename_and_bill_document sets document_type correctly."""

    def _make_bill_doc(self):
        bill_doc = Mock()
        bill_doc.body_text = "Text"
        bill_doc.extraction_confidence = 0.9
        bill_doc.title = None
        bill_doc.sponsors = []
        bill_doc.committee = None
        bill_doc.amended_code_refs = []
        return bill_doc

    def test_ld_bill_document_type(self):
        """LD bills get document_type='bill'."""
        record = BillRecord.from_filename_and_bill_document(
            "131-LD-0001", self._make_bill_doc(), "http://example.com/"
        )
        assert record.document_type == "bill"

    def test_sp_bill_document_type(self):
        """SP bills get document_type='sp_bill'."""
        record = BillRecord.from_filename_and_bill_document(
            "131-SP-0042", self._make_bill_doc(), "http://example.com/"
        )
        assert record.document_type == "sp_bill"

    def test_hp_bill_document_type(self):
        """HP bills get document_type='hp_bill'."""
        record = BillRecord.from_filename_and_bill_document(
            "130-HP-0100", self._make_bill_doc(), "http://example.com/"
        )
        assert record.document_type == "hp_bill"

    def test_ho_bill_document_type(self):
        """HO bills get document_type='ho_bill'."""
        record = BillRecord.from_filename_and_bill_document(
            "129-HO-0005", self._make_bill_doc(), "http://example.com/"
        )
        assert record.document_type == "ho_bill"
