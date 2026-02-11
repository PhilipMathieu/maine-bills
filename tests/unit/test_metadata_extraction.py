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
    assert result == "An Act Relating to Education and Training"


def test_extract_sponsors():
    """Test sponsor extraction."""
    text = """
    Introduced by Representative SMITH
    Cosponsored by Senator JONES
    """
    result = TextExtractor._extract_sponsors(text)
    # Should extract legislator names
    assert isinstance(result, list)
    assert "SMITH" in result
    assert "JONES" in result


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
    assert "Title 20, Section 1" in result
    assert "Title 5, Section 10" in result


def test_extract_sponsors_with_apostrophe():
    """Test sponsor extraction with apostrophe in name (e.g., O'BRIEN)."""
    text = """
    Introduced by Representative O'BRIEN
    Cosponsored by Senator O'MALLEY
    """
    result = TextExtractor._extract_sponsors(text)
    assert "O'BRIEN" in result
    assert "O'MALLEY" in result


def test_extract_sponsors_multiple_on_one_line():
    """Test sponsor extraction with multiple sponsors on one line."""
    text = """
    Introduced by Representative JEAN-PAUL SMITH
    """
    result = TextExtractor._extract_sponsors(text)
    assert "JEAN-PAUL SMITH" in result


def test_extract_date_valid():
    """Test date extraction with valid date."""
    text = """
    131-LD-0001
    Introduced on 03/15/2024
    An Act Relating to Education
    """
    result = TextExtractor._extract_date(text)
    assert result is not None
    assert result.month == 3
    assert result.day == 15
    assert result.year == 2024


def test_extract_committee():
    """Test committee extraction from text."""
    text = """
    131-LD-0001
    Referred to Committee on Education and Cultural Affairs
    An Act Relating to Education
    """
    result = TextExtractor._extract_committee(text)
    assert result is not None
    assert "Education" in result
