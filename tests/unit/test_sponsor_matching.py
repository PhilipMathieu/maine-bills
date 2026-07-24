"""Tests for two-pass sponsor -> OpenStates matching."""

import pytest

from maine_bills.openstates import RosterEntry
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
