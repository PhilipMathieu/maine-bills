"""Tests for two-pass sponsor -> OpenStates matching."""

import pytest

from maine_bills.openstates import RosterEntry, roster_cache_path
from maine_bills.sponsor_matching import MatchResult, SponsorMatcher, normalize_name


def _entry(os_id, name, family, party, chamber, district):
    return RosterEntry(
        openstates_id=os_id,
        name=name,
        family_name=family,
        party=party,
        chamber=chamber,
        district=district,
    )


# Realistic Maine-style fixture roster: hyphenated names, a two-word surname,
# shared surnames across chambers (Libby, Perry), a shared surname within one
# chamber (Smith), and an accented name (Côté).
FIXTURE_ROSTER = [
    _entry("ocd-person/daughtry", "Mattie Daughtry", "Daughtry", "Democratic", "Senate", "23"),
    _entry(
        "ocd-person/beebe-center", "Pinny Beebe-Center", "Beebe-Center", "Democratic", "House", "94"
    ),
    _entry(
        "ocd-person/talbot-ross", "Rachel Talbot Ross", "Talbot Ross", "Democratic", "House", "118"
    ),
    _entry("ocd-person/libby-n", "Nathan Libby", "Libby", "Democratic", "Senate", "21"),
    _entry("ocd-person/libby-l", "Laurel Libby", "Libby", "Republican", "House", "90"),
    _entry("ocd-person/cote", "Marc Côté", "Côté", "Democratic", "House", "35"),
    _entry("ocd-person/jackson", "Troy Jackson", "Jackson", "Democratic", "Senate", "1"),
    _entry("ocd-person/fecteau", "Ryan Fecteau", "Fecteau", "Democratic", "House", "132"),
    _entry("ocd-person/vitelli", "Eloise Vitelli", "Vitelli", "Democratic", "Senate", "24"),
    _entry("ocd-person/rotundo", "Margaret Rotundo", "Rotundo", "Democratic", "Senate", "18"),
    _entry("ocd-person/carney", "Anne Carney", "Carney", "Democratic", "Senate", "29"),
    _entry("ocd-person/gattine", "Drew Gattine", "Gattine", "Democratic", "House", "126"),
    _entry("ocd-person/perry-a", "Anne Perry", "Perry", "Democratic", "House", "9"),
    _entry("ocd-person/perry-j", "Joseph Perry", "Perry", "Democratic", "Senate", "31"),
    _entry("ocd-person/smith-d", "David Smith", "Smith", "Republican", "House", "60"),
    _entry("ocd-person/smith-s", "Sarah Smith", "Smith", "Democratic", "House", "45"),
]


@pytest.fixture
def matcher():
    return SponsorMatcher(FIXTURE_ROSTER)


# --- normalize_name ---


def test_normalize_uppercases_and_strips():
    assert normalize_name("  Daughtry ") == "DAUGHTRY"


def test_normalize_collapses_hyphen_spacing():
    assert normalize_name("BEEBE- CENTER") == "BEEBE-CENTER"
    assert normalize_name("Beebe - Center") == "BEEBE-CENTER"


def test_normalize_strips_accents():
    assert normalize_name("Côté") == "COTE"


def test_normalize_collapses_internal_whitespace():
    assert normalize_name("Talbot   Ross") == "TALBOT ROSS"


# --- Pass 1: exact matching ---


def test_exact_match_returns_full_identity(matcher):
    result = matcher.match("DAUGHTRY")
    assert result == MatchResult(
        openstates_id="ocd-person/daughtry",
        canonical_name="Mattie Daughtry",
        party="Democratic",
        district="23",
        chamber="Senate",
        confidence=1.0,
        method="exact",
    )


def test_exact_match_hyphenated_with_stray_space(matcher):
    result = matcher.match("BEEBE- CENTER")
    assert result.method == "exact"
    assert result.openstates_id == "ocd-person/beebe-center"
    assert result.confidence == 1.0


def test_exact_match_accented_roster_name_from_plain_ascii(matcher):
    """Extraction loses accents; 'COTE' must still hit roster 'Côté'."""
    result = matcher.match("COTE")
    assert result.method == "exact"
    assert result.canonical_name == "Marc Côté"


def test_exact_match_two_word_surname(matcher):
    result = matcher.match("Talbot Ross")
    assert result.method == "exact"
    assert result.openstates_id == "ocd-person/talbot-ross"


def test_exact_match_full_name_fallback(matcher):
    """A full-name extraction still matches via the full-name index."""
    result = matcher.match("Troy Jackson")
    assert result.method == "exact"
    assert result.openstates_id == "ocd-person/jackson"


def test_exact_match_is_case_insensitive(matcher):
    assert matcher.match("fecteau").method == "exact"


# --- ambiguity and chamber disambiguation ---


def test_shared_surname_without_chamber_is_ambiguous(matcher):
    result = matcher.match("LIBBY")
    assert result == MatchResult(
        openstates_id=None,
        canonical_name=None,
        party=None,
        district=None,
        chamber=None,
        confidence=0.0,
        method="ambiguous",
    )


def test_shared_surname_disambiguated_by_chamber(matcher):
    senate = matcher.match("LIBBY", chamber="Senate")
    assert senate.method == "exact"
    assert senate.openstates_id == "ocd-person/libby-n"

    house = matcher.match("PERRY", chamber="House")
    assert house.method == "exact"
    assert house.openstates_id == "ocd-person/perry-a"


def test_shared_surname_same_chamber_stays_ambiguous(matcher):
    """Two House Smiths cannot be resolved even with a chamber hint."""
    assert matcher.match("SMITH").method == "ambiguous"
    assert matcher.match("SMITH", chamber="House").method == "ambiguous"


def test_same_person_in_both_chambers_is_not_ambiguous():
    """A mid-biennium chamber switcher has two roster entries but one identity."""
    roster = [
        _entry("ocd-person/switcher", "Chamber Switcher", "Switcher", "Democratic", "House", "40"),
        _entry("ocd-person/switcher", "Chamber Switcher", "Switcher", "Democratic", "Senate", "20"),
    ]
    result = SponsorMatcher(roster).match("SWITCHER")
    assert result.method == "exact"
    assert result.openstates_id == "ocd-person/switcher"


# --- Pass 2: fuzzy matching ---


def test_fuzzy_match_close_misspelling(matcher):
    result = matcher.match("DAUGHTREY")  # extra E
    assert result.method == "fuzzy"
    assert result.openstates_id == "ocd-person/daughtry"
    assert result.canonical_name == "Mattie Daughtry"
    assert 0.88 <= result.confidence < 1.0


def test_fuzzy_match_respects_threshold(matcher):
    assert matcher.match("ZYXWV").method == "unmatched"


def test_fuzzy_below_custom_threshold_unmatched():
    strict = SponsorMatcher(FIXTURE_ROSTER, fuzzy_threshold=99.0)
    assert strict.match("DAUGHTREY").method == "unmatched"


def test_fuzzy_tie_between_distinct_people_is_ambiguous(matcher):
    """'LIBBYY' scores identically against both Libbys."""
    assert matcher.match("LIBBYY").method == "ambiguous"


def test_fuzzy_tie_broken_by_chamber_hint(matcher):
    result = matcher.match("LIBBYY", chamber="House")
    assert result.method == "fuzzy"
    assert result.openstates_id == "ocd-person/libby-l"


def test_unmatched_returns_empty_identity(matcher):
    result = matcher.match("UNIVERSITY")
    assert result == MatchResult(
        openstates_id=None,
        canonical_name=None,
        party=None,
        district=None,
        chamber=None,
        confidence=0.0,
        method="unmatched",
    )


def test_empty_sponsor_is_unmatched(matcher):
    assert matcher.match("").method == "unmatched"
    assert matcher.match("   ").method == "unmatched"


# --- match_all ---


def test_match_all_preserves_order_and_length(matcher):
    sponsors = ["DAUGHTRY", "LIBBY", "ZYXWV", "DAUGHTREY"]
    results = matcher.match_all(sponsors)
    assert len(results) == len(sponsors)
    assert [r.method for r in results] == ["exact", "ambiguous", "unmatched", "fuzzy"]


def test_match_all_with_chamber_hint(matcher):
    results = matcher.match_all(["LIBBY", "PERRY"], chamber="Senate")
    assert [r.openstates_id for r in results] == ["ocd-person/libby-n", "ocd-person/perry-j"]


def test_empty_roster_everything_unmatched():
    matcher = SponsorMatcher([])
    assert matcher.match("DAUGHTRY").method == "unmatched"


class TestMatchSponsorsAdapter:
    """Module-level match_sponsors(), the entry point enrichment.load_matcher uses."""

    def _seed_cache(self, tmp_path):
        import json

        cache = tmp_path / "cache"
        cache.mkdir()
        roster_cache_path(cache, 132).write_text(json.dumps([e.to_dict() for e in FIXTURE_ROSTER]))
        return cache

    def test_matched_and_unmatched_alignment(self, tmp_path):
        from maine_bills.sponsor_matching import match_sponsors

        cache = self._seed_cache(tmp_path)
        results = match_sponsors(
            ["DAUGHTRY", "NOT A LEGISLATOR", "LIBBY"], session=132, cache_dir=cache
        )
        assert len(results) == 3
        assert results[0].openstates_id == "ocd-person/daughtry"
        assert results[0].method == "exact"
        assert results[1] is None  # unmatched -> None so enrichment stays null
        assert results[2] is None  # ambiguous (shared surname) -> None

    def test_matcher_is_cached_per_session(self, tmp_path):
        from maine_bills import sponsor_matching
        from maine_bills.sponsor_matching import match_sponsors

        cache = self._seed_cache(tmp_path)
        sponsor_matching._MATCHERS.clear()
        match_sponsors(["DAUGHTRY"], session=132, cache_dir=cache)
        roster_cache_path(cache, 132).unlink()  # would break a rebuild
        results = match_sponsors(["BEEBE-CENTER"], session=132, cache_dir=cache)
        assert results[0].openstates_id == "ocd-person/beebe-center"


class TestOCRCanonicalMatching:
    """Pass 2: OCR-confusable character folding, for names a ratio can't rescue."""

    def test_lowercase_l_for_i_matches(self, matcher):
        """VITELLl -> VITELLI: one wrong character, too short for the ratio."""
        result = matcher.match("VITELLl")
        assert result.method == "ocr"
        assert result.canonical_name == "Eloise Vitelli"
        assert result.confidence == 0.95

    def test_short_name_digit_substitutions(self, matcher):
        """Digit-for-letter swaps on short names, exactly where the ratio fails."""
        for extracted, expected in (
            ("5MITH", None),  # ambiguous: two Smiths
            ("CARNEV", None),  # V/Y not in the map -> not an OCR match
            ("JACK5ON", "ocd-person/jackson"),
            ("R0TUND0", "ocd-person/rotundo"),
            ("GATT1NE", "ocd-person/gattine"),
        ):
            result = matcher.match(extracted)
            if expected:
                assert result.method == "ocr", extracted
                assert result.openstates_id == expected, extracted
            else:
                assert result.openstates_id is None, extracted

    def test_ratio_would_have_missed_these(self, matcher):
        """Confirms the gap being closed: these score below the fuzzy threshold."""
        from rapidfuzz import fuzz

        for extracted, roster_name in (("JACK5ON", "JACKSON"), ("GATT1NE", "GATTINE")):
            assert fuzz.token_sort_ratio(extracted, roster_name) < 88, extracted
            assert matcher.match(extracted).method == "ocr", extracted

    def test_ocr_pass_does_not_shadow_exact(self, matcher):
        """A clean name still resolves as exact, not ocr."""
        assert matcher.match("DAUGHTRY").method == "exact"
        assert matcher.match("JACKSON").method == "exact"

    def test_ocr_ambiguity_is_reported_not_guessed(self, matcher):
        """Folding must not silently pick one of two shared-surname legislators."""
        assert matcher.match("PERRV").openstates_id is None
        assert matcher.match("5MITH").method == "ambiguous"

    def test_canonicalization_is_symmetric(self):
        """Folding applies to roster names too, so it never breaks a match."""
        roster = [_entry("ocd-person/c", "Jane O'Neil1", "O'Neil1", "Democratic", "House", "3")]
        m = SponsorMatcher(roster)
        assert m.match("O'NEILI").openstates_id == "ocd-person/c"

    def test_digraph_rn_to_m(self):
        roster = [_entry("ocd-person/d", "Sam Thames", "Thames", "Democratic", "House", "4")]
        m = SponsorMatcher(roster)
        assert m.match("Tharnes").method == "ocr"

    def test_ocr_matches_produce_enrichment_values(self, tmp_path):
        """match_sponsors() must not drop OCR matches as unmatched."""
        import json

        from maine_bills.openstates import roster_cache_path
        from maine_bills.sponsor_matching import match_sponsors

        cache = tmp_path / "cache"
        cache.mkdir()
        roster_cache_path(cache, 132).write_text(json.dumps([e.to_dict() for e in FIXTURE_ROSTER]))
        results = match_sponsors(["JACK5ON"], session=132, cache_dir=cache)
        assert results[0] is not None
        assert results[0].openstates_id == "ocd-person/jackson"


class TestChamberHint:
    """Per-sponsor chamber hints resolve legislators who share a surname."""

    def test_shared_surname_resolves_with_per_sponsor_chambers(self, matcher):
        """The Gate A fix: two Perrys on one bill, each resolved by chamber."""
        sponsors = ["PERRY", "PERRY", "DAUGHTRY"]
        chambers = ["House", "Senate", "Senate"]
        results = matcher.match_all(sponsors, chambers=chambers)

        assert [r.method for r in results] == ["exact", "exact", "exact"]
        assert results[0].openstates_id == "ocd-person/perry-a"
        assert results[1].openstates_id == "ocd-person/perry-j"

    def test_same_sponsors_are_ambiguous_without_hints(self, matcher):
        """Baseline: without chambers these are exactly the ambiguous case."""
        results = matcher.match_all(["PERRY", "PERRY"])
        assert [r.method for r in results] == ["ambiguous", "ambiguous"]

    def test_none_entries_fall_back_to_no_hint(self, matcher):
        """A missing hint must not break the others on the same bill."""
        results = matcher.match_all(["PERRY", "DAUGHTRY"], chambers=[None, "Senate"])
        assert results[0].method == "ambiguous"
        assert results[1].method == "exact"

    def test_misaligned_chambers_rejected(self, matcher):
        with pytest.raises(ValueError, match="chambers has 1 entries"):
            matcher.match_all(["PERRY", "DAUGHTRY"], chambers=["House"])

    def test_wrong_hint_does_not_invent_a_match(self, matcher):
        """A hint naming a chamber the surname isn't in must not force a pick."""
        # Both Smiths are in the House; a Senate hint leaves them unresolved
        result = matcher.match("SMITH", chamber="Senate")
        assert result.openstates_id is None

    def test_match_sponsors_forwards_chambers(self, tmp_path):
        import json

        from maine_bills.openstates import roster_cache_path
        from maine_bills.sponsor_matching import match_sponsors

        cache = tmp_path / "cache"
        cache.mkdir()
        roster_cache_path(cache, 132).write_text(json.dumps([e.to_dict() for e in FIXTURE_ROSTER]))
        results = match_sponsors(
            ["PERRY", "PERRY"], session=132, cache_dir=cache, chambers=["House", "Senate"]
        )
        assert results[0].openstates_id == "ocd-person/perry-a"
        assert results[1].openstates_id == "ocd-person/perry-j"
