from maine_bills.text_extractor import TextExtractor

ELECTRONIC_PREAMBLE = (
    "MAINE STATE LEGISLATURE \n"
    "The following document is provided by the \n"
    "LAW AND LEGISLATIVE DIGITAL LIBRARY \n"
    "at the Maine State Law and Legislative Reference Library \n"
    "http://legislature.maine.gov/lawlib \n"
    "Reproduced from electronic originals \n"
    "(may include minor formatting differences from printed original) \n"
    "Printed on recycled paper\n"
)

SCANNED_PREAMBLE = (
    "MAINE STATE LEGISLATURE \n"
    "The following document is provided by the \n"
    "LAW AND LEGISLATIVE DIGITAL LIBRARY \n"
    "at the Maine State Law and Legislative Reference Library \n"
    "http://legislature.maine.gov/lawlib \n"
    "Reproduced from scanned originals with text recognition applied \n"
    "(searchable text may contain some errors and/or omissions) \n"
)


def test_is_line_number():
    """Test detection of line number patterns."""
    assert TextExtractor._is_line_number("    1")
    assert TextExtractor._is_line_number("   42")
    assert TextExtractor._is_line_number("     123")
    assert not TextExtractor._is_line_number("Some text with 123")
    assert not TextExtractor._is_line_number("Text")


def test_is_line_number_bare_digit():
    """Bare digit lines (no leading whitespace) from scanned PDFs are line numbers."""
    assert TextExtractor._is_line_number("1")
    assert TextExtractor._is_line_number("42")
    assert TextExtractor._is_line_number("123")
    assert not TextExtractor._is_line_number("1515")  # 4 digits = not a line number
    assert not TextExtractor._is_line_number("1 STATE OF MAINE")  # has content


def test_is_header_footer():
    """Test detection of header/footer patterns."""
    assert TextExtractor._is_header_footer("Page 1")
    assert TextExtractor._is_header_footer("Page 42 of 100")
    assert TextExtractor._is_header_footer("131-LD-0001")
    assert not TextExtractor._is_header_footer("Some bill text")


def test_is_header_footer_scanned_session_lines():
    """Scanned-PDF session header lines should be recognised as headers."""
    assert TextExtractor._is_header_footer("HOUSE OF REPRESENTATIVES")
    assert TextExtractor._is_header_footer("131ST LEGISLATURE")
    assert TextExtractor._is_header_footer("SECOND REGULAR SESSION")
    assert TextExtractor._is_header_footer("FIRST SPECIAL SESSION")
    assert not TextExtractor._is_header_footer("Be it enacted by the People")


def test_strip_preamble_electronic():
    """Electronic preamble is stripped; text starts at session ordinal line."""
    text = ELECTRONIC_PREAMBLE + "131st MAINE LEGISLATURE\nAn Act To Do Something\n"
    result = TextExtractor._strip_preamble(text)
    assert result.startswith("131st MAINE LEGISLATURE")
    assert "LAW AND LEGISLATIVE DIGITAL LIBRARY" not in result


def test_strip_preamble_scanned():
    """Scanned preamble is stripped; text starts at session ordinal line."""
    text = SCANNED_PREAMBLE + "7 131ST LEGISLATURE\n9 COMMITTEE AMENDMENT to H.P. 970\n"
    result = TextExtractor._strip_preamble(text)
    assert "LAW AND LEGISLATIVE DIGITAL LIBRARY" not in result


def test_strip_preamble_no_preamble_unchanged():
    """Text without preamble is returned unchanged."""
    text = "131st MAINE LEGISLATURE\nSome content"
    result = TextExtractor._strip_preamble(text)
    assert result == text


def test_clean_body_text_strips_scanned_inline_line_numbers():
    """Line numbers at start of lines without leading whitespace are removed."""
    text = "5 STATE OF MAINE\n9 COMMITTEE AMENDMENT to H.P. 970"
    result = TextExtractor._clean_body_text(text, {})
    assert "STATE OF MAINE" not in result
    assert "COMMITTEE AMENDMENT" in result


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
