from maine_bills.text_extractor import TextExtractor


def test_is_line_number():
    """Test detection of line number patterns."""
    assert TextExtractor._is_line_number("    1") == True
    assert TextExtractor._is_line_number("   42") == True
    assert TextExtractor._is_line_number("     123") == True
    assert TextExtractor._is_line_number("Some text with 123") == False
    assert TextExtractor._is_line_number("Text") == False


def test_is_header_footer():
    """Test detection of header/footer patterns."""
    assert TextExtractor._is_header_footer("Page 1") == True
    assert TextExtractor._is_header_footer("Page 42 of 100") == True
    assert TextExtractor._is_header_footer("131-LD-0001") == True
    assert TextExtractor._is_header_footer("Some bill text") == False


def test_clean_body_text():
    """Test body text cleaning."""
    text = """
         1 Be it enacted by the People of the State of Maine as
         2 follows:
         3
         4 SECTION 1.  AMENDMENT.  Title 20, section 1 is amended to read:

    Page 1
    131-LD-0001
    """

    result = TextExtractor._clean_body_text(text, {})

    # Should remove line numbers
    assert "     1" not in result
    assert "     2" not in result

    # Should remove page headers
    assert "Page 1" not in result

    # Should keep actual bill content
    assert "AMENDMENT" in result or "Title 20" in result


def test_clean_body_text_preserves_structure():
    """Test that cleaning preserves meaningful structure."""
    text = """
    Section 1. Purpose
        Paragraph 1
        Paragraph 2

    Section 2. Implementation
        Details here
    """

    result = TextExtractor._clean_body_text(text, {})

    # Should preserve sections and indentation structure
    assert "Section 1" in result
    assert "Section 2" in result
