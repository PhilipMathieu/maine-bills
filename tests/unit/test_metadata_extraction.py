from datetime import date

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


def test_extract_date_pattern1_house():
    """Pattern 1: House of Representatives header date."""
    text = "House of Representatives, March 15, 2024\nAn Act Relating to Education"
    result = TextExtractor._extract_date(text)
    assert result is not None
    assert result == date(2024, 3, 15)


def test_extract_date_pattern2_in_senate():
    """Pattern 2: In Senate header date."""
    text = "In Senate, January 26, 2023\nAn Act Relating to Education"
    result = TextExtractor._extract_date(text)
    assert result is not None
    assert result == date(2023, 1, 26)


def test_extract_date_pattern3_general_in_header():
    """Pattern 3: General date format within first 800 chars."""
    text = "131-LD-0001\nFebruary 10, 2025\nAn Act Relating to Education"
    result = TextExtractor._extract_date(text)
    assert result is not None
    assert result == date(2025, 2, 10)


def test_extract_date_in_body_not_extracted():
    """Dates deep in the body text should NOT be extracted as introduced date."""
    header = "131-LD-0001\nAn Act Relating to Education\n"
    # Push a date past 800 chars
    padding = "x " * 500
    body = padding + "effective January 15, 2020"
    result = TextExtractor._extract_date(header + body)
    assert result is None


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


def test_extract_sponsors_excludes_houses():
    """'Houses' is noise text that should not appear as a sponsor name."""
    text = "Presented by Representative SMITH of Houses\nCosponsored by Senator JONES of District 5"
    result = TextExtractor._extract_sponsors(text)
    assert "Houses" not in result


def test_extract_sponsors_excludes_town():
    """'Town' is a location word that should not appear as a sponsor name."""
    text = "Cosponsored by Representative Town of Cumberland"
    result = TextExtractor._extract_sponsors(text)
    assert "Town" not in result


def test_extract_title_strips_amendment_header_prefix():
    """'An Act' embedded in an amendment header — return just the 'An Act' portion."""
    line = 'COMMITTEE AMENDMENT "A" to H.P. 970, L.D. 1515, "An Act to Fund Emergency Services"'
    result = TextExtractor._extract_title(line)
    assert result is not None
    assert result.startswith("An Act")
    assert "COMMITTEE AMENDMENT" not in result


def test_extract_title_resolve_document():
    """Resolve documents have titles starting with 'Resolve'."""
    text = "131-LD-2180\nResolve, Regarding Legislative Review of Special Education\n"
    result = TextExtractor._extract_title(text)
    assert result is not None
    assert result.startswith("Resolve")


def test_extract_title_no_fallback_guess():
    """Non-title text after bill ID should NOT be returned as title."""
    text = "131-LD-0001\nSome random committee text here\nBe it enacted"
    result = TextExtractor._extract_title(text)
    assert result is None


class TestSponsorChamberCapture:
    """The Senator/Representative title is captured as a chamber hint."""

    PRESENTED = (
        "Presented by Senator DAUGHTRY of Cumberland.\n"
        "Cosponsored by Representative PERRY of Calais, Senator PERRY of Bangor, "
        "Representative BEEBE-CENTER of Rockland and Speaker FECTEAU of Biddeford.\n"
        "Be it enacted by the People of the State of Maine as follows:"
    )

    def test_titles_map_to_chambers(self):
        mentions = TextExtractor._extract_sponsor_mentions(self.PRESENTED)
        assert ("DAUGHTRY", "Senate") in mentions
        assert ("BEEBE-CENTER", "House") in mentions
        # Speaker is Speaker of the House
        assert ("FECTEAU", "House") in mentions

    def test_two_legislators_sharing_a_surname_are_both_kept(self):
        """Name-only dedup would drop one of these; they are different people."""
        mentions = TextExtractor._extract_sponsor_mentions(self.PRESENTED)
        perrys = [(n, c) for n, c in mentions if n == "PERRY"]
        assert sorted(c for _n, c in perrys) == ["House", "Senate"]

    def test_same_person_mentioned_twice_is_not_duplicated(self):
        text = (
            "Presented by Senator DAUGHTRY of Cumberland.\n"
            "Cosponsored by Senator DAUGHTRY of Cumberland and "
            "Representative GATTINE of Westbrook.\nBe it enacted"
        )
        mentions = TextExtractor._extract_sponsor_mentions(text)
        assert [n for n, _c in mentions].count("DAUGHTRY") == 1

    def test_president_maps_to_senate(self):
        text = "Presented by President JACKSON of Aroostook.\nBe it enacted"
        assert TextExtractor._extract_sponsor_mentions(text) == [("JACKSON", "Senate")]

    def test_sponsors_wrapper_returns_names_only(self):
        names = TextExtractor._extract_sponsors(self.PRESENTED)
        assert all(isinstance(n, str) for n in names)
        assert "DAUGHTRY" in names

    def test_bill_document_exposes_aligned_chambers(self):
        doc_text = "An Act to Test\n" + self.PRESENTED
        mentions = TextExtractor._extract_sponsor_mentions(doc_text)
        names = [n for n, _c in mentions]
        chambers = [c for _n, c in mentions]
        assert len(names) == len(chambers)
