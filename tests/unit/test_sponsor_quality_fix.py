"""
Test cases for sponsor extraction quality fixes.

These tests validate that the fixes for false positives work correctly:
1. Title words within names (e.g., "President JACKSON")
2. Common non-name words (e.g., "Department", "Regular Session")
3. Valid names still work correctly
"""

from maine_bills.text_extractor import TextExtractor


class TestTitleWordsInNames:
    """Test that title words within extracted names are filtered."""

    def test_president_in_name(self):
        """President JACKSON should be filtered out when it appears as a two-word name."""
        # The bug: "Representative President JACKSON" extracts "President JACKSON"
        text = "Presented by Representative President JACKSON of Aroostook"
        result = TextExtractor._extract_sponsors(text)
        assert result == [], f"Expected empty list, got {result}"

    def test_speaker_in_name(self):
        """Speaker TALBOT should be filtered out when it appears as a two-word name."""
        text = "Presented by Senator Speaker TALBOT of Cumberland"
        result = TextExtractor._extract_sponsors(text)
        assert result == [], f"Expected empty list, got {result}"

    def test_secretary_in_name(self):
        """Secretary BELLOWS should be filtered out when it appears as a two-word name."""
        text = "Introduced by Representative Secretary BELLOWS of Kennebec"
        result = TextExtractor._extract_sponsors(text)
        assert result == [], f"Expected empty list, got {result}"

    def test_clerk_in_name(self):
        """Clerk HUNT should be filtered out when it appears as a two-word name."""
        text = "Presented by Senator Clerk HUNT of Penobscot"
        result = TextExtractor._extract_sponsors(text)
        assert result == [], f"Expected empty list, got {result}"

    def test_state_in_name(self):
        """State SMITH should be filtered out when it appears as a two-word name."""
        text = "Presented by Representative State SMITH of York"
        result = TextExtractor._extract_sponsors(text)
        assert result == [], f"Expected empty list, got {result}"


class TestCommonNonNameWords:
    """Test that common non-name words are filtered."""

    def test_department_filtered(self):
        """Department should not be extracted."""
        # Realistic scenario: "Secretary of State" followed by text with "Department"
        text = "ROBERT B. HUNT Clerk States Department of Administrative Services"
        result = TextExtractor._extract_sponsors(text)
        assert "Department" not in result, f"'Department' should be filtered, got {result}"
        assert "States Department" not in result, f"'States Department' should be filtered, got {result}"  # noqa: E501

    def test_regular_session_filtered(self):
        """Regular Session should not be extracted."""
        text = "First Regular Session of the 131st Legislature"
        result = TextExtractor._extract_sponsors(text)
        assert "Regular Session" not in result, f"'Regular Session' should be filtered, got {result}"  # noqa: E501
        assert "Regular" not in result, f"'Regular' should be filtered, got {result}"
        assert "Session" not in result, f"'Session' should be filtered, got {result}"

    def test_special_session_filtered(self):
        """Special Session should not be extracted."""
        text = "Second Special Session of the 131st Legislature"
        result = TextExtractor._extract_sponsors(text)
        assert "Special Session" not in result
        assert "Special" not in result
        assert "Session" not in result

    def test_senate_house_filtered(self):
        """Senate and House should not be extracted."""
        text = "Presented by Senate Committee and House Committee"
        result = TextExtractor._extract_sponsors(text)
        assert "Senate Committee" not in result
        assert "House Committee" not in result
        assert "Senate" not in result
        assert "House" not in result

    def test_legislature_filtered(self):
        """Legislature should not be extracted."""
        text = "131st Maine Legislature First Regular Session"
        result = TextExtractor._extract_sponsors(text)
        assert "Legislature" not in result
        assert "Maine Legislature" not in result
        assert "Legislative" not in result


class TestValidNamesStillWork:
    """Ensure valid names are not filtered by the fix."""

    def test_simple_name(self):
        """Simple names should still work."""
        text = "Presented by Representative SMITH of Cumberland"
        result = TextExtractor._extract_sponsors(text)
        assert result == ["SMITH"]

    def test_name_with_apostrophe(self):
        """Names with apostrophes should still work."""
        text = "Introduced by Senator O'BRIEN of Androscoggin"
        result = TextExtractor._extract_sponsors(text)
        assert result == ["O'BRIEN"]

    def test_name_with_hyphen(self):
        """Names with hyphens should still work."""
        text = "Presented by Representative TALBOT-ROSS of Portland"
        result = TextExtractor._extract_sponsors(text)
        assert result == ["TALBOT-ROSS"]

    def test_two_word_name(self):
        """Two-word names should still work."""
        text = "Introduced by Senator VAN BUREN of Knox"
        result = TextExtractor._extract_sponsors(text)
        assert result == ["VAN BUREN"]

    def test_cosponsors_still_work(self):
        """Cosponsorship extraction should still work."""
        text = """
        Presented by Representative SMITH of Cumberland
        Cosponsored by Senator JONES of York and Representative BROWN of Penobscot
        """
        result = TextExtractor._extract_sponsors(text)
        assert "SMITH" in result
        assert "JONES" in result
        assert "BROWN" in result


class TestEdgeCases:
    """Test edge cases and complex scenarios."""

    def test_state_in_context_not_name(self):
        """'State' in 'Secretary of State' context should be filtered."""
        text = "SHENNA BELLOWS Secretary of State Be it enacted"
        result = TextExtractor._extract_sponsors(text)
        # "State" alone shouldn't be extracted, "Secretary" shouldn't be extracted
        assert "State" not in result
        assert "Secretary" not in result

    def test_mixed_valid_and_invalid(self):
        """Valid names should be extracted, invalid filtered."""
        text = """
        Presented by Representative SMITH of Cumberland
        ROBERT B. HUNT Clerk of the House
        Cosponsored by Senator JONES of York
        """
        result = TextExtractor._extract_sponsors(text)
        assert "SMITH" in result
        assert "JONES" in result
        # These should be filtered
        assert "ROBERT" not in result
        assert "HUNT" not in result
        assert "Clerk" not in result

    def test_no_false_positives_from_headers(self):
        """Document headers should not produce sponsor extractions."""
        text = """
        131st MAINE LEGISLATURE
        FIRST REGULAR SESSION-2023
        Legislative Document No. 1611
        House of Representatives, April 11, 2023
        """
        result = TextExtractor._extract_sponsors(text)
        # None of these header words should be extracted
        assert "MAINE" not in result
        assert "FIRST" not in result
        assert "Regular" not in result
        assert "Session" not in result
        assert "Legislative" not in result
        assert "Legislature" not in result
        assert "House" not in result

    def test_title_word_as_part_of_first_name(self):
        """Edge case: What if someone's first name is a title word?"""
        # This is purely theoretical - testing the boundary
        text = "Presented by Representative President SMITH of York"
        result = TextExtractor._extract_sponsors(text)
        # "President SMITH" should be filtered because "President" is a title word
        assert result == [] or "President SMITH" not in result


class TestCommaSeparatedFalsePositives:
    """Test that garbage names from comma-separated fallback are not extracted.

    The comma-separated fallback pattern matches 'NAME of PLACE', which can
    pick up phrases like 'Town of Cumberland', 'University of Maine', etc.
    These should NOT appear as sponsors.
    """

    def _make_bill_text(self, cosponsor_block: str) -> str:
        """Create realistic bill text with a given cosponsorship block."""
        return (
            "Presented by Representative SMITH of Cumberland\n"
            f"Cosponsored by {cosponsor_block}\n\n"
            "Be it enacted by the People of the State of Maine as follows:"
        )

    def test_town_not_extracted(self):
        """'Town' in 'Town of Cumberland' should not be a sponsor."""
        text = self._make_bill_text(
            "Senator JONES of York, the Town of Cumberland"
        )
        result = TextExtractor._extract_sponsors(text)
        assert "Town" not in result, f"'Town' should not be a sponsor, got {result}"

    def test_university_not_extracted(self):
        """'University' in 'University of Maine' should not be a sponsor."""
        text = self._make_bill_text(
            "Representative BROWN of Penobscot, the University of Maine"
        )
        result = TextExtractor._extract_sponsors(text)
        assert "University" not in result, f"'University' should not be a sponsor, got {result}"

    def test_board_not_extracted(self):
        """'Board' in 'Board of Education' should not be a sponsor."""
        text = self._make_bill_text(
            "Senator JONES of York, the Board of Education"
        )
        result = TextExtractor._extract_sponsors(text)
        assert "Board" not in result, f"'Board' should not be a sponsor, got {result}"

    def test_american_society_not_extracted(self):
        """'American Society' in 'American Society of Engineers' should not be a sponsor."""
        text = self._make_bill_text(
            "Representative BROWN of Penobscot, the American Society of Engineers"
        )
        result = TextExtractor._extract_sponsors(text)
        assert "American Society" not in result, f"'American Society' should not be a sponsor, got {result}"  # noqa: E501
        assert "American" not in result, f"'American' should not be a sponsor, got {result}"

    def test_national_association_not_extracted(self):
        """'National Association' in 'National Association of Counties' should not be a sponsor."""
        text = self._make_bill_text(
            "Senator JONES of York, the National Association of Counties"
        )
        result = TextExtractor._extract_sponsors(text)
        assert "National Association" not in result, f"'National Association' should not be a sponsor, got {result}"  # noqa: E501
        assert "National" not in result, f"'National' should not be a sponsor, got {result}"

    def test_finance_authority_not_extracted(self):
        """'Finance Authority' in 'Finance Authority of Maine' should not be a sponsor."""
        text = self._make_bill_text(
            "Representative BROWN of Penobscot, the Finance Authority of Maine"
        )
        result = TextExtractor._extract_sponsors(text)
        assert "Finance Authority" not in result, f"'Finance Authority' should not be a sponsor, got {result}"  # noqa: E501
        assert "Finance" not in result, f"'Finance' should not be a sponsor, got {result}"

    def test_justices_not_extracted(self):
        """'Justices' in 'Justices of the Supreme' should not be a sponsor."""
        text = self._make_bill_text(
            "Senator JONES of York, the Justices of the Supreme Judicial Court"
        )
        result = TextExtractor._extract_sponsors(text)
        assert "Justices" not in result, f"'Justices' should not be a sponsor, got {result}"

    def test_resources_not_extracted(self):
        """'Resources' in 'Resources of the State' should not be a sponsor."""
        text = self._make_bill_text(
            "Representative BROWN of Penobscot, Natural Resources of the State"
        )
        result = TextExtractor._extract_sponsors(text)
        assert "Resources" not in result, f"'Resources' should not be a sponsor, got {result}"
        assert "Natural Resources" not in result, f"'Natural Resources' should not be a sponsor, got {result}"  # noqa: E501

    def test_district_not_extracted(self):
        """'District' in 'District of Columbia' should not be a sponsor."""
        text = self._make_bill_text(
            "Senator JONES of York, the District of Columbia"
        )
        result = TextExtractor._extract_sponsors(text)
        assert "District" not in result, f"'District' should not be a sponsor, got {result}"

    def test_valid_sponsors_still_extracted(self):
        """Valid sponsors should still be extracted alongside garbage text."""
        text = self._make_bill_text(
            "Senator JONES of York, the Town of Cumberland, "
            "Representative BROWN of Penobscot"
        )
        result = TextExtractor._extract_sponsors(text)
        assert "SMITH" in result, f"'SMITH' should be a sponsor, got {result}"
        assert "JONES" in result, f"'JONES' should be a sponsor, got {result}"
        assert "BROWN" in result, f"'BROWN' should be a sponsor, got {result}"
        assert "Town" not in result, f"'Town' should not be a sponsor, got {result}"


class TestHyphenatedNameSpaceBug:
    """Test that hyphenated names with spaces around the hyphen are normalized.

    In some PDFs, line breaks cause names like 'BEEBE-CENTER' to appear as
    'BEEBE- CENTER' (space after hyphen). These should be normalized.
    """

    def test_space_after_hyphen_normalized(self):
        """'BEEBE- CENTER' should be normalized to 'BEEBE-CENTER'."""
        text = "Presented by Representative BEEBE- CENTER of Rockland"
        result = TextExtractor._extract_sponsors(text)
        assert "BEEBE-CENTER" in result, f"Expected 'BEEBE-CENTER', got {result}"
        assert "BEEBE- CENTER" not in result, f"Should not contain space in hyphenated name, got {result}"  # noqa: E501

    def test_space_before_hyphen_normalized(self):
        """'BEEBE -CENTER' should be normalized to 'BEEBE-CENTER'."""
        text = "Presented by Representative BEEBE -CENTER of Rockland"
        result = TextExtractor._extract_sponsors(text)
        assert "BEEBE-CENTER" in result, f"Expected 'BEEBE-CENTER', got {result}"

    def test_spaces_around_hyphen_normalized(self):
        """'BEEBE - CENTER' should be normalized to 'BEEBE-CENTER'."""
        text = "Presented by Representative BEEBE - CENTER of Rockland"
        result = TextExtractor._extract_sponsors(text)
        assert "BEEBE-CENTER" in result, f"Expected 'BEEBE-CENTER', got {result}"
