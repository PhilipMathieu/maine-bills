"""Parse Maine Legislature member profile pages into roster entries.

Source: ``legislature.maine.gov/District{N}``. Recon captured these while
looking for the locality → legislator mapping issue #13 item 2 needs and
OpenStates does not provide (it gives district numbers, not town names).

Each page carries more than expected:

    Sen. Trey Stewart (R-Aroostook)
    District 2 : In Aroostook County: Amity; Bancroft Township; Blaine; ...
    Legislative Service : Senate 130-132; House 128-129.

So one page yields the member, their party, their county, every municipality
they represent, and **which sessions they served** — the last of which lets a
single current-session scrape answer questions about earlier sessions.

Two limits worth stating plainly, because they bound what this can fix:

* These pages exist only for the **current** legislature. A member who has left
  has no page, so historical coverage reaches only as far back as the service
  line of someone still serving. Sessions 121-124 are effectively out of reach —
  robots.txt disallows ``/LawMakerWeb``, which was the only other route.
* The district pages found so far are Senate seats. House members are published
  through party caucus pages with a different shape, so House locality data
  needs its own parser.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from bs4 import BeautifulSoup

MEMBER_URL = "https://legislature.maine.gov/District{district}"

# "Sen. Trey Stewart (R-Aroostook)"
_HEADING = re.compile(
    r"^(?P<title>Sen|Rep)\.\s+(?P<name>.+?)\s*\((?P<party>[A-Z])-(?P<county>[^)]+)\)",
)

# "District 2 : In Aroostook County: Amity; Bancroft Township; ..."
_DISTRICT = re.compile(r"District\s+(?P<number>\d+)\s*:\s*(?P<body>.+?)(?=Mailing Address|$)", re.S)

# "Legislative Service : Senate 130-132; House 128-129."
_SERVICE = re.compile(r"Legislative Service\s*:\s*(?P<body>.+?)(?:\.|Committee Assignments)", re.S)
_SERVICE_TERM = re.compile(r"(?P<chamber>Senate|House)\s+(?P<first>\d+)\s*(?:-\s*(?P<last>\d+))?")

# "In Aroostook County: Amity; Bancroft Township; ..." — repeated per county.
_COUNTY_NAME = r"[A-Z][A-Za-z .'-]+?"
_COUNTY_BLOCK = re.compile(
    rf"In\s+(?P<county>{_COUNTY_NAME})\s+County\s*:\s*(?P<towns>[^:]+?)"
    rf"(?=In\s+{_COUNTY_NAME}\s+County\s*:|$)",
    re.S,
)

# "All of Waldo County."
_WHOLE_COUNTY = re.compile(r"All of\s+(?P<county>[A-Z][A-Za-z .'-]+?)\s+County")

_CHAMBER_BY_TITLE = {"Sen": "Senate", "Rep": "House"}

# The site uses single letters; OpenStates rosters spell them out, and these
# entries are matched against those.
_PARTY = {
    "D": "Democratic",
    "R": "Republican",
    "I": "Independent",
    "U": "Unenrolled",
    "G": "Green",
}


@dataclass(frozen=True)
class ServiceTerm:
    """One stretch of service in one chamber, in session numbers."""

    chamber: str
    first_session: int
    last_session: int

    def covers(self, session: int) -> bool:
        return self.first_session <= session <= self.last_session


@dataclass
class MemberProfile:
    """A sitting legislator, as published on their profile page."""

    name: str
    family_name: str
    chamber: str
    party: str | None = None
    county: str | None = None
    district: str | None = None
    localities: list[str] = field(default_factory=list)
    service: list[ServiceTerm] = field(default_factory=list)
    source_url: str = ""

    def served_in(self, session: int) -> bool:
        """Whether this member sat in the given session, per their service line."""
        return any(term.covers(session) for term in self.service)

    def chamber_in(self, session: int) -> str | None:
        """Which chamber they sat in for that session — they may have switched."""
        for term in self.service:
            if term.covers(session):
                return term.chamber
        return None


def member_url(district: int | str) -> str:
    return MEMBER_URL.format(district=district)


def family_name_of(full_name: str) -> str:
    """Everything after the first token.

    Bill text names sponsors by surname alone, and Maine has sitting members
    with two-word surnames (Talbot Ross), so taking only the last token would
    fail to match them. Taking everything after the given name matches those
    correctly and mis-handles only a middle name, which these pages do not use.
    """
    parts = full_name.split()
    return " ".join(parts[1:]) if len(parts) > 1 else full_name


def parse_service(text: str) -> list[ServiceTerm]:
    """ "Senate 130-132; House 128-129." -> two terms.

    A single session appears without a range ("Senate 132"), which becomes a
    term covering just that session.
    """
    match = _SERVICE.search(text)
    if not match:
        return []
    terms = []
    for term in _SERVICE_TERM.finditer(match.group("body")):
        first = int(term.group("first"))
        last = int(term.group("last")) if term.group("last") else first
        terms.append(
            ServiceTerm(chamber=term.group("chamber"), first_session=first, last_session=last)
        )
    return terms


def parse_localities(body: str) -> list[str]:
    """Municipalities in a district description, in page order.

    Handles both published forms: an enumerated list per county
    ("In Aroostook County: Amity; Bancroft Township; ...") and a whole county
    ("All of Waldo County."), which yields the county as the single locality
    since no town list is given.
    """
    localities: list[str] = []
    for block in _COUNTY_BLOCK.finditer(body):
        for town in block.group("towns").split(";"):
            cleaned = re.sub(r"\s+", " ", town).strip(" .,")
            if cleaned:
                localities.append(cleaned)

    if not localities:
        for whole in _WHOLE_COUNTY.finditer(body):
            localities.append(f"All of {whole.group('county').strip()} County")

    return localities


def parse_member_page(html: str, district: int | str | None = None) -> MemberProfile:
    """Parse one member profile page."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(["script", "style", "nav", "footer"]):
        tag.decompose()

    heading = soup.find("h1")
    heading_text = re.sub(r"\s+", " ", heading.get_text(" ", strip=True)) if heading else ""
    match = _HEADING.match(heading_text)
    if not match:
        raise ValueError(f"Not a member profile page; heading was {heading_text[:80]!r}")

    name = match.group("name").strip()
    text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))

    district_match = _DISTRICT.search(text)
    resolved_district = (
        str(district)
        if district is not None
        else (district_match.group("number") if district_match else None)
    )

    return MemberProfile(
        name=name,
        family_name=family_name_of(name),
        chamber=_CHAMBER_BY_TITLE[match.group("title")],
        party=_PARTY.get(match.group("party"), match.group("party")),
        county=match.group("county").strip(),
        district=resolved_district,
        localities=parse_localities(district_match.group("body")) if district_match else [],
        service=parse_service(text),
        source_url=member_url(resolved_district) if resolved_district else "",
    )
