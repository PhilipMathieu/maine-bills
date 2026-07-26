"""Tests for OpenStates roster acquisition (session mapping, parsing, caching)."""

import json
from unittest.mock import MagicMock

import pytest

from maine_bills.openstates import (
    Legislator,
    OpenStatesAPIProvider,
    PeopleRepoProvider,
    Role,
    RosterEntry,
    RosterProvider,
    fetch_all_legislators,
    get_roster,
    roster_cache_path,
    roster_for_session,
    session_biennium,
)

# --- session_biennium ---


def test_session_121_is_2003_2004():
    assert session_biennium(121) == (2003, 2004)


def test_session_132_is_2025_2026():
    assert session_biennium(132) == (2025, 2026)


def test_session_125_is_2011_2012():
    assert session_biennium(125) == (2011, 2012)


# --- Role.overlaps_biennium ---


def test_role_within_biennium_overlaps():
    role = Role(chamber="Senate", start_date="2003-01-08", end_date="2004-12-01")
    assert role.overlaps_biennium(2003, 2004)


def test_role_sworn_in_december_before_biennium_overlaps():
    """Maine legislators are sworn in early December of the election year."""
    role = Role(chamber="House", start_date="2002-12-04", end_date="2004-12-01")
    assert role.overlaps_biennium(2003, 2004)


def test_role_ending_before_biennium_does_not_overlap():
    role = Role(chamber="House", start_date="2000-12-06", end_date="2002-12-04")
    assert not role.overlaps_biennium(2003, 2004)


def test_role_starting_after_biennium_does_not_overlap():
    role = Role(chamber="Senate", start_date="2025-01-01", end_date=None)
    assert not role.overlaps_biennium(2023, 2024)


def test_open_ended_role_overlaps_current_biennium():
    role = Role(chamber="Senate", start_date="2023-12-06", end_date=None)
    assert role.overlaps_biennium(2025, 2026)


def test_undated_role_overlaps_everything():
    """v3 API roles carry no dates; they must count for any queried biennium."""
    role = Role(chamber="House")
    assert role.overlaps_biennium(2003, 2004)
    assert role.overlaps_biennium(2025, 2026)


# --- roster_for_session ---


def _legislator(name, family, roles, party="Democratic", os_id="ocd-person/x"):
    return Legislator(
        openstates_id=os_id,
        name=name,
        family_name=family,
        party=party,
        roles=roles,
    )


def test_roster_includes_only_overlapping_legislators():
    serving = _legislator(
        "Mattie Daughtry",
        "Daughtry",
        [Role("Senate", "23", "2022-12-07", None)],
        os_id="ocd-person/daughtry",
    )
    retired = _legislator(
        "Old Timer",
        "Timer",
        [Role("House", "5", "2000-12-06", "2002-12-04")],
        os_id="ocd-person/timer",
    )
    roster = roster_for_session([serving, retired], 131)
    assert len(roster) == 1
    assert roster[0].openstates_id == "ocd-person/daughtry"
    assert roster[0].chamber == "Senate"
    assert roster[0].district == "23"


def test_chamber_switcher_gets_one_entry_per_chamber():
    """A rep who moved to the Senate mid-biennium appears once per chamber."""
    switcher = _legislator(
        "Chamber Switcher",
        "Switcher",
        [
            Role("House", "40", "2020-12-02", "2023-06-01"),
            Role("Senate", "20", "2023-06-02", None),
        ],
    )
    roster = roster_for_session([switcher], 131)
    chambers = {entry.chamber for entry in roster}
    assert chambers == {"House", "Senate"}


def test_multiple_districts_same_chamber_yields_single_entry():
    redistricted = _legislator(
        "Redistricted Rep",
        "Rep",
        [
            Role("House", "40", "2018-12-05", "2022-12-07"),
            Role("House", "44", "2022-12-07", None),
        ],
    )
    roster = roster_for_session([redistricted], 131)
    assert len(roster) == 1
    assert roster[0].district == "44"


# --- OpenStatesAPIProvider ---


def _api_person(os_id, name, family, party, classification, district):
    return {
        "id": os_id,
        "name": name,
        "family_name": family,
        "given_name": name.split()[0],
        "party": party,
        "current_role": {
            "title": "Senator" if classification == "upper" else "Representative",
            "org_classification": classification,
            "district": district,
        },
    }


def test_api_provider_requires_key(monkeypatch):
    monkeypatch.delenv("OPENSTATES_API_KEY", raising=False)
    with pytest.raises(ValueError, match="OPENSTATES_API_KEY"):
        OpenStatesAPIProvider()


def test_api_provider_paginates_and_parses(mocker):
    page1 = MagicMock()
    page1.json.return_value = {
        "results": [
            _api_person("ocd-person/1", "Mattie Daughtry", "Daughtry", "Democratic", "upper", 23),
        ],
        "pagination": {"page": 1, "max_page": 2},
    }
    page2 = MagicMock()
    page2.json.return_value = {
        "results": [
            _api_person("ocd-person/2", "Ryan Fecteau", "Fecteau", "Democratic", "lower", 132),
        ],
        "pagination": {"page": 2, "max_page": 2},
    }
    mock_get = mocker.patch("maine_bills.openstates.requests.get", side_effect=[page1, page2])

    provider = OpenStatesAPIProvider(api_key="test-key")
    legislators = provider.fetch_legislators()

    assert len(legislators) == 2
    assert legislators[0].openstates_id == "ocd-person/1"
    assert legislators[0].roles == [Role(chamber="Senate", district="23")]
    assert legislators[1].roles == [Role(chamber="House", district="132")]
    # API key sent as header on every request
    for call in mock_get.call_args_list:
        assert call.kwargs["headers"]["X-API-KEY"] == "test-key"


def test_api_provider_uses_env_key(monkeypatch):
    monkeypatch.setenv("OPENSTATES_API_KEY", "env-key")
    provider = OpenStatesAPIProvider()
    assert provider.api_key == "env-key"


# --- PeopleRepoProvider ---

TALBOT_ROSS_YAML = """\
id: ocd-person/talbot-ross
name: Rachel Talbot Ross
given_name: Rachel
family_name: Talbot Ross
party:
- name: Democratic
roles:
- type: lower
  district: '118'
  jurisdiction: ocd-jurisdiction/country:us/state:me/government
  start_date: '2016-12-07'
  end_date: '2022-12-07'
- type: upper
  district: '28'
  jurisdiction: ocd-jurisdiction/country:us/state:me/government
  start_date: '2024-12-04'
"""

RETIRED_YAML = """\
id: ocd-person/retired
name: Old Timer
family_name: Timer
party:
- name: Republican
  end_date: '2002-12-04'
roles:
- type: lower
  district: '5'
  start_date: '2000-12-06'
  end_date: '2002-12-04'
"""

GOVERNOR_YAML = """\
id: ocd-person/governor
name: Janet Mills
family_name: Mills
party:
- name: Democratic
roles:
- type: governor
  jurisdiction: ocd-jurisdiction/country:us/state:me/government
  start_date: '2019-01-02'
"""


def _mock_response(json_data=None, text=None):
    res = MagicMock()
    res.json.return_value = json_data
    res.text = text
    return res


def test_people_repo_provider_enumerates_and_parses(mocker):
    listing_legislature = [
        {
            "type": "file",
            "name": "Rachel-Talbot-Ross.yml",
            "download_url": "https://raw.githubusercontent.com/openstates/people/main/data/me/legislature/Rachel-Talbot-Ross.yml",
        },
        {"type": "dir", "name": "subdir", "download_url": None},
    ]
    listing_retired = [
        {
            "type": "file",
            "name": "Old-Timer.yml",
            "download_url": "https://raw.githubusercontent.com/openstates/people/main/data/me/retired/Old-Timer.yml",
        },
        {
            "type": "file",
            "name": "Janet-Mills.yml",
            "download_url": "https://raw.githubusercontent.com/openstates/people/main/data/me/retired/Janet-Mills.yml",
        },
    ]
    mocker.patch(
        "maine_bills.openstates.requests.get",
        side_effect=[
            _mock_response(json_data=listing_legislature),
            _mock_response(text=TALBOT_ROSS_YAML),
            _mock_response(json_data=listing_retired),
            _mock_response(text=RETIRED_YAML),
            _mock_response(text=GOVERNOR_YAML),
        ],
    )

    legislators = PeopleRepoProvider().fetch_legislators()

    # Governor has no legislative roles and is excluded
    assert [leg.openstates_id for leg in legislators] == [
        "ocd-person/talbot-ross",
        "ocd-person/retired",
    ]

    talbot_ross = legislators[0]
    assert talbot_ross.family_name == "Talbot Ross"
    assert talbot_ross.party == "Democratic"
    assert talbot_ross.roles == [
        Role(chamber="House", district="118", start_date="2016-12-07", end_date="2022-12-07"),
        Role(chamber="Senate", district="28", start_date="2024-12-04", end_date=None),
    ]

    retired = legislators[1]
    assert retired.party == "Republican"
    assert retired.roles[0].end_date == "2002-12-04"


def test_people_repo_provider_sends_github_token(mocker):
    mock_get = mocker.patch(
        "maine_bills.openstates.requests.get",
        side_effect=[_mock_response(json_data=[]), _mock_response(json_data=[])],
    )
    PeopleRepoProvider(github_token="gh-token").fetch_legislators()
    for call in mock_get.call_args_list:
        assert call.kwargs["headers"]["Authorization"] == "Bearer gh-token"


# --- caching ---


class FakeProvider(RosterProvider):
    """Counts fetches so cache behavior can be asserted."""

    name = "fake"

    def __init__(self, legislators):
        self.legislators = legislators
        self.fetch_count = 0

    def fetch_legislators(self):
        self.fetch_count += 1
        return self.legislators


@pytest.fixture
def fake_provider():
    return FakeProvider(
        [
            _legislator(
                "Mattie Daughtry",
                "Daughtry",
                [Role("Senate", "23", "2022-12-07", None)],
                os_id="ocd-person/daughtry",
            ),
        ]
    )


def test_fetch_all_legislators_caches_to_json(tmp_path, fake_provider):
    first = fetch_all_legislators(fake_provider, cache_dir=tmp_path)
    second = fetch_all_legislators(fake_provider, cache_dir=tmp_path)

    assert fake_provider.fetch_count == 1
    assert first == second
    cache_file = tmp_path / "legislators_fake.json"
    assert cache_file.exists()
    assert json.loads(cache_file.read_text())[0]["openstates_id"] == "ocd-person/daughtry"


def test_get_roster_caches_per_session(tmp_path, fake_provider):
    roster = get_roster(132, provider=fake_provider, cache_dir=tmp_path)
    assert len(roster) == 1
    assert roster_cache_path(tmp_path, 132, fake_provider).exists()

    # Second call reads the per-session cache (no new fetch)
    again = get_roster(132, provider=fake_provider, cache_dir=tmp_path)
    assert fake_provider.fetch_count == 1
    assert again == roster
    assert isinstance(again[0], RosterEntry)


def test_get_roster_refresh_refetches(tmp_path, fake_provider):
    get_roster(132, provider=fake_provider, cache_dir=tmp_path)
    get_roster(132, provider=fake_provider, cache_dir=tmp_path, refresh=True)
    assert fake_provider.fetch_count == 2


def test_get_roster_excludes_out_of_biennium(tmp_path, fake_provider):
    """Daughtry's role starts 2022-12-07, so she is absent from session 125."""
    roster = get_roster(125, provider=fake_provider, cache_dir=tmp_path)
    assert roster == []


def test_roster_cache_is_keyed_by_provider(tmp_path, fake_provider):
    """Rosters from different providers must not share a cache file.

    Regression: a provider switch (e.g. OPENSTATES_API_KEY becoming set) would
    otherwise silently reuse the previous provider's roster.
    """
    other = FakeProvider(
        [
            _legislator(
                "Someone Else",
                "Else",
                [Role("House", "99", "2024-12-04", None)],
                os_id="ocd-person/other",
            )
        ]
    )
    other.name = "other_fake"

    first = get_roster(132, provider=fake_provider, cache_dir=tmp_path)
    second = get_roster(132, provider=other, cache_dir=tmp_path)

    path_a = roster_cache_path(tmp_path, 132, fake_provider)
    path_b = roster_cache_path(tmp_path, 132, other)
    assert path_a != path_b
    assert path_a.exists() and path_b.exists()
    # The second provider actually fetched rather than reusing the first's roster
    assert other.fetch_count == 1
    assert first[0].openstates_id != second[0].openstates_id
