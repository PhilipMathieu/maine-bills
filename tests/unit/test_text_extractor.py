from unittest.mock import Mock, patch
import pytest
from pathlib import Path
from maine_bills.text_extractor import TextExtractor, BillDocument


def test_extract_bill_document_missing_file():
    """Test that extraction fails with missing file."""
    with pytest.raises(FileNotFoundError):
        TextExtractor.extract_bill_document(Path("/nonexistent/file.pdf"))


def test_extract_bill_document_success(tmp_path, mocker):
    """Test successful bill document extraction."""
    # Mock fitz.open and PDF structure
    mock_page = Mock()
    mock_page.get_text.return_value = """131-LD-0001

An Act Relating to Education

     1 Be it enacted by the People of the State of Maine as follows:
     2
     3 SECTION 1.  AMENDMENT.  Title 20, section 1 is amended to read:
"""

    mock_doc = Mock()
    mock_doc.page_count = 1
    mock_doc.__iter__ = Mock(return_value=iter([mock_page]))

    pdf_path = tmp_path / "test.pdf"
    pdf_path.touch()

    with patch('maine_bills.text_extractor.fitz.open', return_value=mock_doc):
        result = TextExtractor.extract_bill_document(pdf_path)

        assert isinstance(result, BillDocument)
        assert result.bill_id == "131-LD-0001"
        assert "AMENDMENT" in result.body_text or "Title 20" in result.body_text
        assert 0.0 <= result.extraction_confidence <= 1.0


def test_save_text_creates_file(tmp_path):
    """Test that save_text creates output file."""
    output_path = tmp_path / "output.txt"
    text = "Test content\nWith multiple lines"

    TextExtractor.save_text(output_path, text)

    assert output_path.exists()
    assert output_path.read_text() == text
