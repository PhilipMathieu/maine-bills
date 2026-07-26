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

STEWART = """
<html><head><title>Sen. Trey Stewart (R-Aroostook) | Maine State Legislature</title></head>
<body>
  <h1>Sen. Trey Stewart (R-Aroostook)</h1>
  <p>District 2 : In Aroostook County: Amity; Bancroft Township; Blaine;
  Bridgewater; Central Aroostook UT. In Penobscot County: Chester;
  Drew Plantation; East Millinocket.
  Mailing Address: 3 State House Station, Augusta, Maine 04333</p>
  <p>Legislative Service : Senate 130-132; House 128-129.
  Committee Assignments : Senate Republican Minority Leader</p>
</body></html>
"""

CURRY = """
<html><head><title>Sen. Chip Curry (D-Waldo) | Maine State Legislature</title></head>
<body>
  <h1>Sen. Chip Curry (D-Waldo)</h1>
  <p>District 11 : All of Waldo County.
  Mailing Address: 3 State House Station, Augusta, Maine 04333</p>
  <p>Legislative Service : Senate 130-132.
  Committee Assignments : Housing and Economic Development (Chair)</p>
</body></html>
"""


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


def test_whole_county_districts_record_the_county():
    """No town list is published for these, so the county is the locality."""
    assert parse_member_page(CURRY).localities == ["All of Waldo County"]


def test_localities_stop_before_the_mailing_address():
    assert not any("Augusta" in loc for loc in parse_member_page(STEWART).localities)
    assert not any("State House" in loc for loc in parse_member_page(CURRY).localities)


def test_parse_localities_on_an_empty_body():
    assert parse_localities("") == []


# --- legislative service ---


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
