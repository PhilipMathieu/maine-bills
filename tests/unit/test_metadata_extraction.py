from maine_bills.text_extractor import TextExtractor


def test_extract_bill_id():
    """Test bill ID extraction from text."""
    text = """
    131-LD-0001

    An Act Relating to Education
    """
    result = TextExtractor._extract_bill_id(text)
    assert result == "131-LD-0001"


def test_extract_bill_id_no_match():
    """Test bill ID extraction when none found."""
    text = "Some text without bill ID"
    result = TextExtractor._extract_bill_id(text)
    assert result is None


def test_extract_title():
    """Test title extraction."""
    text = """
    131-LD-0001

    An Act Relating to Education and Training

    Be it enacted...
    """
    result = TextExtractor._extract_title(text)
    assert "Education" in result or "An Act" in result


def test_extract_sponsors():
    """Test sponsor extraction."""
    text = """
    Introduced by Representative SMITH
    Cosponsored by Senator JONES
    """
    result = TextExtractor._extract_sponsors(text)
    # Should extract legislator names
    assert isinstance(result, list)


def test_extract_session():
    """Test session extraction."""
    text = "131-LD-0001"
    result = TextExtractor._extract_session(text)
    assert result == "131"


def test_extract_amended_codes():
    """Test amended code extraction."""
    text = """
    This act amends Title 20, Section 1.
    It also modifies Title 5, Section 10.
    """
    result = TextExtractor._extract_amended_codes(text)
    assert isinstance(result, list)
    assert len(result) >= 1
