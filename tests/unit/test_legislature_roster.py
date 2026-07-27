"""Tests for member profile parsing (issue #13 items 1 and 2).

Fixtures reproduce the real shape of ``legislature.maine.gov/District{N}`` as
captured on ``fixtures/recon``, including both published locality forms — an
enumerated town list per county, and a whole county.
"""

import pytest

from maine_bills.legislature_roster import (
    MemberProfile,
    ServiceTerm,
    family_name_of,
    member_url,
    parse_localities,
    parse_member_page,
    parse_service,
)


def _page(heading, district_line, service_line):
    """Wrap real page text in the real page's structure."""
    return f"""
<html><head><title>{heading} | Maine State Legislature</title></head>
<body>
  <h1>{heading}</h1>
  <p>{district_line}
  Mailing Address: 3 State House Station, Augusta, Maine 04333</p>
  <p>{service_line}</p>
</body></html>
"""


# Text below is copied from the real pages on `fixtures/recon`, quirks intact.
# An earlier draft of these fixtures was hand-written and tidied — it dropped
# the serial "and", used a semicolon where the site uses none, and normalized
# the service heading to the plural. All 22 tests passed against a parser that
# mangled every real page. Do not sanitize these.

# District 2 — serial conjunction closes each county block: "...; and Weston."
STEWART = _page(
    "Sen. Trey Stewart (R-Aroostook)",
    "District 2 : In Aroostook County: Amity; Bancroft Township; Blaine; "
    "Bridgewater; Central Aroostook UT; and Weston. "
    "In Penobscot County: Chester; Drew Plantation; and Woodville.",
    "Legislative Service : Senate 130-132; House 128-129. "
    "Committee Assignments : Senate Republican Minority Leader",
)

# District 9 — two towns, no semicolon at all. Splitting on ";" loses Bangor.
BALDACCI = _page(
    "Sen. Joe Baldacci (D-Penobscot)",
    "District 9 : In Penobscot County: Bangor and Hermon.",
    "Legislative Service : Senate 130-132. "
    "Committee Assignments : Inland Fisheries and Wildlife (Chair)",
)

# District 10 — service heading is SINGULAR and the line has no closing period.
HAGGAN = _page(
    "Sen. David Haggan (R-Penobscot)",
    "District 10 : In Hancock County: Bucksport; Dedham; and Otis. "
    "In Penobscot County: Bradley; Brewer; Carmel; and Orrington.",
    "Legislative Service : Senate 132; House 128-131 "
    "Committee Assignment : Health Coverage, Insurance, and Financial Services",
)

# District 11 — whole county, no town list published.
CURRY = _page(
    "Sen. Chip Curry (D-Waldo)",
    "District 11 : All of Waldo County.",
    "Legislative Service : Senate 130-132. "
    "Committee Assignments : Housing and Economic Development (Chair)",
)


# --- heading ---


def test_parses_name_party_county_and_chamber():
    member = parse_member_page(STEWART)
    assert member.name == "Trey Stewart"
    assert member.chamber == "Senate"
    assert member.party == "Republican"  # spelled out to match OpenStates rosters
    assert member.county == "Aroostook"
    assert member.district == "2"


def test_democratic_party_letter_is_expanded():
    assert parse_member_page(CURRY).party == "Democratic"


def test_a_non_profile_page_raises():
    with pytest.raises(ValueError, match="Not a member profile page"):
        parse_member_page("<html><body><h1>Maine State Legislature</h1></body></html>")


def test_representative_pages_map_to_the_house():
    html = STEWART.replace("Sen. Trey Stewart", "Rep. Trey Stewart")
    assert parse_member_page(html).chamber == "House"


# --- family name ---


@pytest.mark.parametrize(
    "full,expected",
    [
        ("Trey Stewart", "Stewart"),
        ("Chip Curry", "Curry"),
        # Sitting members with two-word surnames: taking only the last token
        # would fail to match "TALBOT ROSS" as it appears in bill text.
        ("Rachel Talbot Ross", "Talbot Ross"),
        ("Marianne Beebe-Center", "Beebe-Center"),
        ("Mononym", "Mononym"),
    ],
)
def test_family_name_of(full, expected):
    assert family_name_of(full) == expected


# --- localities ---


def test_enumerated_towns_across_multiple_counties():
    localities = parse_member_page(STEWART).localities
    assert "Amity" in localities
    assert "Bancroft Township" in localities
    assert "Chester" in localities  # second county block
    assert "Drew Plantation" in localities
    assert not any(loc.startswith("In ") for loc in localities)


# --- the serial conjunction, which every real county block ends with ---


def test_last_town_of_a_block_is_not_prefixed_with_and():
    """Regression: splitting on ";" alone yielded "and Weston".

    16 of 235 localities across the real District pages came out this way — a
    plausible-looking string that will never join to the town it names.
    """
    localities = parse_member_page(STEWART).localities
    assert "Weston" in localities
    assert "Woodville" in localities  # last town of the second block too
    assert not any(loc.lower().startswith("and ") for loc in localities)


def test_two_towns_with_no_semicolon_are_both_captured():
    """Regression: District 9 publishes "Bangor and Hermon." with no semicolon,
    and splitting on ";" alone returned one string — losing Bangor entirely."""
    localities = parse_member_page(BALDACCI).localities
    assert localities == ["Bangor", "Hermon"]


def test_and_inside_a_block_is_a_separator_everywhere():
    localities = parse_member_page(HAGGAN).localities
    assert "Otis" in localities
    assert "Orrington" in localities
    assert not any(" and " in loc for loc in localities)


def test_mixed_enumerated_and_whole_county_forms():
    """The whole-county clause used to be a fallback, so on a mixed page it
    glued onto the last town: 'and Owls Head. All of Waldo County'."""
    body = "In Knox County: Rockland; Thomaston; and Owls Head. All of Waldo County."
    assert parse_localities(body) == [
        "Rockland",
        "Thomaston",
        "Owls Head",
        "All of Waldo County",
    ]


def test_whole_county_districts_record_the_county():
    """No town list is published for these, so the county is the locality."""
    assert parse_member_page(CURRY).localities == ["All of Waldo County"]


def test_localities_stop_before_the_mailing_address():
    assert not any("Augusta" in loc for loc in parse_member_page(STEWART).localities)
    assert not any("State House" in loc for loc in parse_member_page(CURRY).localities)


def test_parse_localities_on_an_empty_body():
    assert parse_localities("") == []


# --- legislative service ---


def test_singular_committee_heading_without_a_period():
    """Regression: District 10 publishes "Committee Assignment" singular and no
    closing period, so requiring the plural returned no service at all — a
    sitting senator read as never having served."""
    member = parse_member_page(HAGGAN)
    assert member.service == [
        ServiceTerm(chamber="Senate", first_session=132, last_session=132),
        ServiceTerm(chamber="House", first_session=128, last_session=131),
    ]
    assert member.served_in(132) is True
    assert member.service_unparsed is False


def test_unparsed_service_is_distinguishable_from_absent_service():
    """served_in() returns False for both; the caller must be able to tell."""
    absent = _page("Sen. A B (D-Knox)", "District 1 : All of Knox County.", "No service line.")
    unparsed = _page(
        "Sen. C D (D-Knox)",
        "District 1 : All of Knox County.",
        "Legislative Service : ??? Committee Assignments : x",
    )
    assert parse_member_page(absent).service_unparsed is False
    assert parse_member_page(unparsed).service_unparsed is True
    assert parse_member_page(unparsed).served_in(132) is False


def test_service_across_two_chambers():
    service = parse_member_page(STEWART).service
    assert service == [
        ServiceTerm(chamber="Senate", first_session=130, last_session=132),
        ServiceTerm(chamber="House", first_session=128, last_session=129),
    ]


def test_a_single_session_has_no_range():
    assert parse_service("Legislative Service : Senate 132. Committee Assignments : x") == [
        ServiceTerm(chamber="Senate", first_session=132, last_session=132)
    ]


def test_absent_service_line_is_empty_not_an_error():
    assert parse_service("no such line here") == []


# --- session coverage, which is what makes these pages worth scraping ---


def test_served_in_spans_both_chambers():
    """One current page answers for earlier sessions — that is the whole point.

    A member who moved chambers covers 128-132 from a single fetch, which
    reaches into the 125-130 ambiguity band issue #13 item 2 is about.
    """
    member = parse_member_page(STEWART)
    assert [s for s in range(124, 134) if member.served_in(s)] == [128, 129, 130, 131, 132]


def test_chamber_in_follows_the_move_between_chambers():
    member = parse_member_page(STEWART)
    assert member.chamber_in(128) == "House"
    assert member.chamber_in(131) == "Senate"
    assert member.chamber_in(121) is None


def test_a_first_term_member_does_not_claim_earlier_sessions():
    member = parse_member_page(CURRY)
    assert member.served_in(130) is True
    assert member.served_in(129) is False
    assert member.served_in(125) is False


# --- url ---


def test_member_url():
    assert member_url(11) == "https://legislature.maine.gov/District11"
    assert parse_member_page(CURRY).source_url == "https://legislature.maine.gov/District11"


def test_district_override_wins():
    assert parse_member_page(STEWART, district=99).district == "99"


# --- the dataclass contract used downstream ---


def test_profile_defaults_are_empty_not_none():
    member = MemberProfile(name="A B", family_name="B", chamber="Senate")
    assert member.localities == []
    assert member.service == []
    assert member.served_in(132) is False
