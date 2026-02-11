import dataclasses
from datetime import date
import pytest

from maine_bills.text_extractor import BillDocument


def test_bill_document_creation():
    """Test BillDocument dataclass creation."""
    doc = BillDocument(
        bill_id="131-LD-0001",
        title="An Act Relating to Education",
        sponsors=["Rep. Smith", "Sen. Jones"],
        session="131",
        introduced_date=date(2023, 1, 15),
        committee="Committee on Education",
        amended_code_refs=["Title 20, Section 1", "Title 20, Section 5"],
        body_text="The body of the bill goes here.",
        extraction_confidence=0.95
    )

    assert doc.bill_id == "131-LD-0001"
    assert doc.title == "An Act Relating to Education"
    assert len(doc.sponsors) == 2
    assert doc.extraction_confidence == 0.95
    assert "body" in doc.body_text.lower()


def test_bill_document_asdict():
    """Test BillDocument can be converted to dict."""
    doc = BillDocument(
        bill_id="131-LD-0001",
        title="Test Bill",
        session="131",
        body_text="Text",
        extraction_confidence=0.9
    )

    doc_dict = dataclasses.asdict(doc)
    assert isinstance(doc_dict, dict)
    assert doc_dict["bill_id"] == "131-LD-0001"


def test_bill_document_confidence_validation():
    """Test that invalid confidence values raise ValueError."""
    with pytest.raises(ValueError, match="extraction_confidence must be between"):
        BillDocument(
            bill_id="131-LD-0001",
            title="Test",
            session="131",
            body_text="Text",
            extraction_confidence=1.5  # Invalid
        )
