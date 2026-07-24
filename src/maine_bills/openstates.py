"""OpenStates legislator roster acquisition for Maine.

Two roster providers behind one interface:

- ``OpenStatesAPIProvider`` — OpenStates v3 REST API (requires ``OPENSTATES_API_KEY``).
  The v3 people endpoint only reports each person's *current* role (no role
  history), so this provider is most accurate for the current biennium.
- ``PeopleRepoProvider`` — bulk YAML data from the ``openstates/people`` GitHub
  repository (``data/me/legislature`` + ``data/me/retired``). Includes full role
  history for retired members, so it works for historical sessions. No API key
  needed. This is the default provider.

All fetches are cached to local JSON (default ``data/openstates_cache/``):
the full parsed legislator list per provider, plus one roster file per session.

Session -> biennium mapping: Maine session 121 = 2003-2004; each session +1 adds
2 years. A legislator belongs to a session's roster if any of their legislative
roles overlaps that biennium.
"""

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

import requests
import yaml
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

DEFAULT_CACHE_DIR = Path("data/openstates_cache")

# OpenStates v3 REST API
OPENSTATES_API_URL = "https://v3.openstates.org/people"
OPENSTATES_API_KEY_ENV = "OPENSTATES_API_KEY"
MAINE_JURISDICTION = "ocd-jurisdiction/country:us/state:me/government"

# openstates/people bulk data on GitHub
PEOPLE_REPO_CONTENTS_URL = "https://api.github.com/repos/openstates/people/contents"
PEOPLE_REPO_DIRS = ("data/me/legislature", "data/me/retired")

REQUEST_TIMEOUT = 30

# Maps OpenStates role/org classification to chamber names used in this project
CHAMBER_FROM_CLASSIFICATION = {
    "upper": "Senate",
    "lower": "House",
}


def session_biennium(session: int) -> tuple[int, int]:
    """Map a Maine legislative session number to its biennium years.

    Session 121 = 2003-2004; each subsequent session adds two years.

    Args:
        session: Legislative session number (e.g., 132)

    Returns:
        Tuple of (start_year, end_year), e.g., session 132 -> (2025, 2026)
    """
    start_year = 2003 + 2 * (session - 121)
    return start_year, start_year + 1


@dataclass(frozen=True)
class Role:
    """A single legislative role (one stint in one chamber)."""

    chamber: str  # "Senate" or "House"
    district: str | None = None
    start_date: str | None = None  # ISO date string, None = unknown/open
    end_date: str | None = None  # ISO date string, None = ongoing

    def overlaps_biennium(self, start_year: int, end_year: int) -> bool:
        """Check whether this role overlaps a biennium window.

        The window is treated as ``start_year-01-01`` through ``end_year-12-31``.
        Missing start/end dates are treated as unbounded on that side, so a role
        with no dates (e.g., a current role from the v3 API) overlaps everything.
        """
        window_start = f"{start_year}-01-01"
        window_end = f"{end_year}-12-31"
        # ISO date strings compare correctly as strings
        if self.start_date and self.start_date > window_end:
            return False
        if self.end_date and self.end_date < window_start:
            return False
        return True


@dataclass
class Legislator:
    """A legislator with full role history, as parsed from a provider."""

    openstates_id: str
    name: str
    family_name: str
    given_name: str = ""
    party: str | None = None
    roles: list[Role] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Legislator":
        roles = [Role(**r) for r in data.get("roles", [])]
        return cls(
            openstates_id=data["openstates_id"],
            name=data["name"],
            family_name=data["family_name"],
            given_name=data.get("given_name", ""),
            party=data.get("party"),
            roles=roles,
        )


@dataclass(frozen=True)
class RosterEntry:
    """One legislator's seat in a specific session's roster.

    A legislator who served in both chambers during one biennium produces one
    entry per chamber.
    """

    openstates_id: str
    name: str
    family_name: str
    party: str | None
    chamber: str  # "Senate" or "House"
    district: str | None

    def to_dict(self) -> dict:
        return asdict(self)


class RosterProvider:
    """Interface for legislator roster providers."""

    name: str = "base"

    def fetch_legislators(self) -> list[Legislator]:
        """Fetch all Maine legislators (current and historical where available)."""
        raise NotImplementedError


class OpenStatesAPIProvider(RosterProvider):
    """Fetch Maine legislators from the OpenStates v3 REST API.

    Requires an API key (``OPENSTATES_API_KEY`` env var or ``api_key`` arg).

    Note: the v3 people endpoint reports only each person's current role, with
    no start/end dates, so roles are treated as open-ended. This makes the API
    provider accurate for the current biennium only; use ``PeopleRepoProvider``
    for historical sessions.
    """

    name = "openstates_api"

    def __init__(self, api_key: str | None = None, per_page: int = 50):
        self.api_key = api_key or os.environ.get(OPENSTATES_API_KEY_ENV)
        if not self.api_key:
            raise ValueError(
                f"OpenStates API key required: set {OPENSTATES_API_KEY_ENV} "
                "or pass api_key explicitly"
            )
        self.per_page = per_page

    @retry(
        retry=retry_if_exception_type(
            (requests.exceptions.Timeout, requests.exceptions.ConnectionError)
        ),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def _fetch_page(self, page: int) -> dict:
        res = requests.get(
            OPENSTATES_API_URL,
            params={
                "jurisdiction": MAINE_JURISDICTION,
                "per_page": self.per_page,
                "page": page,
            },
            headers={"X-API-KEY": self.api_key},
            timeout=REQUEST_TIMEOUT,
        )
        res.raise_for_status()
        return res.json()

    def fetch_legislators(self) -> list[Legislator]:
        legislators = []
        page = 1
        while True:
            data = self._fetch_page(page)
            for person in data.get("results", []):
                legislator = self._parse_person(person)
                if legislator is not None:
                    legislators.append(legislator)
            pagination = data.get("pagination", {})
            if page >= pagination.get("max_page", page):
                break
            page += 1
        logger.info(f"OpenStates API: fetched {len(legislators)} Maine legislators")
        return legislators

    @staticmethod
    def _parse_person(person: dict) -> Legislator | None:
        """Convert a v3 API person object to a Legislator."""
        current_role = person.get("current_role") or {}
        chamber = CHAMBER_FROM_CLASSIFICATION.get(current_role.get("org_classification"))
        roles = []
        if chamber:
            district = current_role.get("district")
            roles.append(
                Role(
                    chamber=chamber,
                    district=str(district) if district is not None else None,
                    # v3 API does not expose role dates; treat as open-ended
                    start_date=None,
                    end_date=None,
                )
            )
        name = person.get("name", "")
        family_name = person.get("family_name") or _family_name_from_full(name)
        if not name or not family_name:
            return None
        return Legislator(
            openstates_id=person.get("id", ""),
            name=name,
            family_name=family_name,
            given_name=person.get("given_name", ""),
            party=person.get("party"),
            roles=roles,
        )


class PeopleRepoProvider(RosterProvider):
    """Fetch Maine legislators from the openstates/people GitHub repository.

    Enumerates YAML files under ``data/me/legislature`` (current members) and
    ``data/me/retired`` (historical members) via the GitHub contents API, then
    downloads and parses each person file. No API key required; a GitHub token
    (``GITHUB_TOKEN``) is used for rate limits if present.
    """

    name = "people_repo"

    def __init__(self, github_token: str | None = None):
        self.github_token = github_token or os.environ.get("GITHUB_TOKEN")

    def _headers(self) -> dict:
        headers = {"Accept": "application/vnd.github+json"}
        if self.github_token:
            headers["Authorization"] = f"Bearer {self.github_token}"
        return headers

    @retry(
        retry=retry_if_exception_type(
            (requests.exceptions.Timeout, requests.exceptions.ConnectionError)
        ),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def _get(self, url: str, params: dict | None = None) -> requests.Response:
        res = requests.get(url, params=params, headers=self._headers(), timeout=REQUEST_TIMEOUT)
        res.raise_for_status()
        return res

    def _list_yaml_files(self, repo_dir: str) -> list[str]:
        """Enumerate YAML file download URLs in a repo directory."""
        url = f"{PEOPLE_REPO_CONTENTS_URL}/{repo_dir}"
        entries = self._get(url).json()
        return [
            entry["download_url"]
            for entry in entries
            if entry.get("type") == "file" and entry.get("name", "").endswith((".yml", ".yaml"))
        ]

    def fetch_legislators(self) -> list[Legislator]:
        legislators = []
        for repo_dir in PEOPLE_REPO_DIRS:
            urls = self._list_yaml_files(repo_dir)
            logger.info(f"people repo: {len(urls)} person files in {repo_dir}")
            for url in urls:
                person = yaml.safe_load(self._get(url).text)
                legislator = self._parse_person(person)
                if legislator is not None:
                    legislators.append(legislator)
        logger.info(f"people repo: parsed {len(legislators)} Maine legislators")
        return legislators

    @staticmethod
    def _parse_person(person: dict) -> Legislator | None:
        """Convert an openstates/people YAML person document to a Legislator."""
        if not isinstance(person, dict):
            return None
        roles = []
        for role in person.get("roles", []):
            chamber = CHAMBER_FROM_CLASSIFICATION.get(role.get("type"))
            if not chamber:
                continue  # skip non-legislative roles (e.g., governor)
            district = role.get("district")
            roles.append(
                Role(
                    chamber=chamber,
                    district=str(district) if district is not None else None,
                    start_date=_iso_or_none(role.get("start_date")),
                    end_date=_iso_or_none(role.get("end_date")),
                )
            )
        if not roles:
            return None
        name = person.get("name", "")
        family_name = person.get("family_name") or _family_name_from_full(name)
        if not name or not family_name:
            return None
        return Legislator(
            openstates_id=person.get("id", ""),
            name=name,
            family_name=family_name,
            given_name=person.get("given_name", ""),
            party=_latest_party(person.get("party", [])),
            roles=roles,
        )


def _iso_or_none(value) -> str | None:
    """Normalize a YAML date value (date object or string) to ISO string or None."""
    if value is None or value == "":
        return None
    return str(value)


def _latest_party(party_memberships: list) -> str | None:
    """Pick the most recent party from an openstates/people party list.

    Memberships without an end_date (still active) win; otherwise the one with
    the latest end_date.
    """
    if not party_memberships:
        return None

    def sort_key(membership: dict) -> tuple:
        end = _iso_or_none(membership.get("end_date"))
        return (end is None, end or "")

    latest = max(party_memberships, key=sort_key)
    return latest.get("name")


def _family_name_from_full(name: str) -> str:
    """Best-effort family name from a full name string (last whitespace token)."""
    parts = name.strip().split()
    return parts[-1] if parts else ""


def default_provider() -> RosterProvider:
    """Pick a provider: the v3 API if an API key is configured, else bulk data."""
    if os.environ.get(OPENSTATES_API_KEY_ENV):
        return OpenStatesAPIProvider()
    return PeopleRepoProvider()


def roster_for_session(legislators: list[Legislator], session: int) -> list[RosterEntry]:
    """Build a session roster from legislators via biennium role overlap.

    A legislator appears once per chamber they served in during the biennium.
    If they held multiple districts in one chamber within the biennium, the
    most recent role's district is used.
    """
    start_year, end_year = session_biennium(session)
    entries = []
    for legislator in legislators:
        overlapping = [r for r in legislator.roles if r.overlaps_biennium(start_year, end_year)]
        # One entry per chamber; last-listed overlapping role per chamber wins
        by_chamber: dict[str, Role] = {}
        for role in overlapping:
            by_chamber[role.chamber] = role
        for chamber, role in by_chamber.items():
            entries.append(
                RosterEntry(
                    openstates_id=legislator.openstates_id,
                    name=legislator.name,
                    family_name=legislator.family_name,
                    party=legislator.party,
                    chamber=chamber,
                    district=role.district,
                )
            )
    return entries


def _load_json(path: Path):
    with open(path) as f:
        return json.load(f)


def _save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def fetch_all_legislators(
    provider: RosterProvider | None = None,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    refresh: bool = False,
) -> list[Legislator]:
    """Fetch the full Maine legislator list, using/populating the local cache.

    The parsed list is cached per provider (``legislators_{provider}.json``) so
    that building rosters for many sessions costs one network fetch.
    """
    provider = provider or default_provider()
    cache_path = Path(cache_dir) / f"legislators_{provider.name}.json"
    if cache_path.exists() and not refresh:
        logger.debug(f"Loading legislators from cache: {cache_path}")
        return [Legislator.from_dict(d) for d in _load_json(cache_path)]

    legislators = provider.fetch_legislators()
    _save_json(cache_path, [leg.to_dict() for leg in legislators])
    logger.info(f"Cached {len(legislators)} legislators to {cache_path}")
    return legislators


def get_roster(
    session: int,
    provider: RosterProvider | None = None,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    refresh: bool = False,
) -> list[RosterEntry]:
    """Get the legislator roster for one session, using/populating the cache.

    Rosters are cached one JSON file per session (``roster_{session}.json``).

    Args:
        session: Legislative session number (e.g., 132)
        provider: Roster provider; defaults to the API when a key is set,
            otherwise the openstates/people bulk data
        cache_dir: Directory for cache files (default ``data/openstates_cache/``)
        refresh: If True, ignore caches and re-fetch

    Returns:
        List of RosterEntry for legislators serving during the session's biennium
    """
    cache_dir = Path(cache_dir)
    roster_path = cache_dir / f"roster_{session}.json"
    if roster_path.exists() and not refresh:
        logger.debug(f"Loading session {session} roster from cache: {roster_path}")
        return [RosterEntry(**d) for d in _load_json(roster_path)]

    legislators = fetch_all_legislators(provider, cache_dir, refresh=refresh)
    roster = roster_for_session(legislators, session)
    _save_json(roster_path, [entry.to_dict() for entry in roster])
    logger.info(f"Cached session {session} roster ({len(roster)} seats) to {roster_path}")
    return roster
