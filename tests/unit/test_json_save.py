from pathlib import Path
from datetime import date
import json
from maine_bills.text_extractor import TextExtractor, BillDocument


def test_save_bill_document_json(tmp_path):
    """Test saving BillDocument to JSON."""
    doc = BillDocument(
        bill_id="131-LD-0001",
        title="Test Bill",
        session="131",
        body_text="Bill body text here.",
        extraction_confidence=0.95,
        sponsors=["Rep. Smith"],
        introduced_date=date(2023, 1, 15),
        committee="Committee on Education",
        amended_code_refs=["Title 20, Section 1"]
    )

    output_path = tmp_path / "bill.json"
    TextExtractor.save_bill_document_json(output_path, doc)

    assert output_path.exists()

    # Verify JSON is valid and contains expected data
    with open(output_path) as f:
        data = json.load(f)

    assert data["bill_id"] == "131-LD-0001"
    assert data["title"] == "Test Bill"
    assert data["extraction_confidence"] == 0.95


def test_save_bill_document_json_date_serialization(tmp_path):
    """Test that dates are properly serialized to ISO format."""
    doc = BillDocument(
        bill_id="131-LD-0001",
        title="Test",
        session="131",
        body_text="Text",
        extraction_confidence=0.9,
        introduced_date=date(2023, 6, 15)
    )

    output_path = tmp_path / "bill.json"
    TextExtractor.save_bill_document_json(output_path, doc)

    with open(output_path) as f:
        data = json.load(f)

    # Date should be serialized as ISO string
    assert data["introduced_date"] == "2023-06-15"


def test_save_bill_document_json_with_none_values(tmp_path):
    """Test that None values are properly serialized."""
    doc = BillDocument(
        bill_id="131-LD-0001",
        title="Test",
        session="131",
        body_text="Text",
        extraction_confidence=0.9,
        introduced_date=None,  # None value
        committee=None  # None value
    )

    output_path = tmp_path / "bill.json"
    TextExtractor.save_bill_document_json(output_path, doc)

    assert output_path.exists()

    with open(output_path) as f:
        data = json.load(f)

    # Verify None values are preserved
    assert data["introduced_date"] is None
    assert data["committee"] is None
    assert data["bill_id"] == "131-LD-0001"
    assert data["extraction_confidence"] == 0.9
