from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from maine_bills.text_extractor import BillDocument, TextExtractor


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
    mock_doc.__enter__ = Mock(return_value=mock_doc)
    mock_doc.__exit__ = Mock(return_value=False)

    pdf_path = tmp_path / "test.pdf"
    pdf_path.touch()

    with patch('maine_bills.text_extractor.fitz.open', return_value=mock_doc):
        result = TextExtractor.extract_bill_document(pdf_path)

        assert isinstance(result, BillDocument)
        assert result.bill_id == "131-LD-0001"
        assert "AMENDMENT" in result.body_text or "Title 20" in result.body_text
        assert 0.0 <= result.extraction_confidence <= 1.0
        # Verify context manager was used (close called via __exit__)
        mock_doc.__exit__.assert_called_once()


def test_extract_bill_document_corrupted_pdf(tmp_path):
    """Test that extraction fails gracefully with corrupted PDF."""
    pdf_path = tmp_path / "corrupted.pdf"
    pdf_path.touch()

    with patch('maine_bills.text_extractor.fitz.open', side_effect=Exception("PDF parsing failed")):
        with pytest.raises(Exception, match="PDF parsing failed"):
            TextExtractor.extract_bill_document(pdf_path)


def test_save_text_creates_file(tmp_path):
    """Test that save_text creates output file."""
    output_path = tmp_path / "output.txt"
    text = "Test content\nWith multiple lines"

    TextExtractor.save_text(output_path, text)

    assert output_path.exists()
    assert output_path.read_text() == text


def test_extract_title_returns_none_when_not_found():
    """Test that _extract_title() returns None when no title is found."""
    # Text has no "An Act" phrase and no bill ID preceding a content line
    text = "This is some text\nWith no recognizable title pattern\nJust random content"
    result = TextExtractor._extract_title(text)
    assert result is None


def test_extract_title_finds_an_act():
    """Test that _extract_title() returns the title when 'An Act' is present."""
    text = "131-LD-0001\nAn Act To Improve Education\nSome more content"
    result = TextExtractor._extract_title(text)
    assert result == "An Act To Improve Education"


def test_bill_document_title_can_be_none(tmp_path, mocker):
    """Test that BillDocument.title accepts None (no fallback to 'Unknown Title')."""
    mock_page = Mock()
    mock_page.get_text.return_value = "Just some text without a recognizable title or bill ID\n"

    mock_doc = Mock()
    mock_doc.__iter__ = Mock(return_value=iter([mock_page]))
    mock_doc.__enter__ = Mock(return_value=mock_doc)
    mock_doc.__exit__ = Mock(return_value=False)

    pdf_path = tmp_path / "test.pdf"
    pdf_path.touch()

    with patch('maine_bills.text_extractor.fitz.open', return_value=mock_doc):
        result = TextExtractor.extract_bill_document(pdf_path)

    assert result.title is None
