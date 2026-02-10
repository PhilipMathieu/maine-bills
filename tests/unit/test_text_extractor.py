import pytest
from pathlib import Path
from unittest.mock import Mock, patch
from maine_bills.text_extractor import TextExtractor


def test_extract_from_pdf_missing_file():
    """Test that extraction fails with missing file."""
    with pytest.raises(FileNotFoundError):
        TextExtractor.extract_from_pdf(Path("/nonexistent/file.pdf"))


def test_extract_from_pdf_success(tmp_path, mocker):
    """Test successful PDF text extraction."""
    # Mock PdfReader
    mock_page = Mock()
    mock_page.extract_text.return_value = "Page 1\nContent"

    mock_reader = Mock()
    mock_reader.pages = [mock_page]

    pdf_path = tmp_path / "test.pdf"
    pdf_path.touch()

    with patch('maine_bills.text_extractor.PdfReader', return_value=mock_reader):
        result = TextExtractor.extract_from_pdf(pdf_path)
        assert "Page 1" in result
        assert "Content" in result


def test_extract_from_pdf_multiple_pages(tmp_path, mocker):
    """Test extraction from PDF with multiple pages."""
    mock_page1 = Mock()
    mock_page1.extract_text.return_value = "Page 1\nContent 1"

    mock_page2 = Mock()
    mock_page2.extract_text.return_value = "Page 2\nContent 2"

    mock_reader = Mock()
    mock_reader.pages = [mock_page1, mock_page2]

    pdf_path = tmp_path / "test.pdf"
    pdf_path.touch()

    with patch('maine_bills.text_extractor.PdfReader', return_value=mock_reader):
        result = TextExtractor.extract_from_pdf(pdf_path)
        assert "Page 1" in result
        assert "Page 2" in result
        assert "Content 1" in result
        assert "Content 2" in result


def test_save_text_creates_file(tmp_path):
    """Test that save_text creates output file."""
    output_path = tmp_path / "subdir" / "output.txt"
    text = "Test content\nWith multiple lines"

    TextExtractor.save_text(output_path, text)

    assert output_path.exists()
    assert output_path.read_text() == text


def test_save_text_creates_parents(tmp_path):
    """Test that save_text creates parent directories."""
    output_path = tmp_path / "deep" / "nested" / "output.txt"
    text = "Content"

    TextExtractor.save_text(output_path, text)

    assert output_path.parent.exists()
    assert output_path.exists()
