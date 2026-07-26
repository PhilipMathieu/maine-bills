"""Parse a Maine Legislature bill status page into structured legislative history.

Source: ``display_ps.asp?LD={ld}&snum={session}``. Recon (sprint track A1)
established two things that decide this module's shape:

* The page renders **identically for sessions 121 and 132**. There is no old/new
  era split to branch on, so one parser covers 2003-2026. The sprint plan's
  scale-back trigger — "status pages inconsistent across eras" — does not fire.
* It is structured by stable element ids (``#flags``, ``#sec0``, ``#sec3``,
  ``#sec6``), so parsing keys on those rather than on text position.

``#paper_box`` and ``#ld_box`` look like the obvious source for the paper and LD
numbers and are **not** — they are empty in the served HTML and filled by script.
Both numbers come from ``<title>`` instead, which carries them server-side.

robots.txt allows this path. It disallows ``/LawMakerWeb/`` and
``default_ps.asp``, so neither is used here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

from bs4 import BeautifulSoup

STATUS_URL = "https://legislature.maine.gov/legis/bills/display_ps.asp?LD={ld}&snum={session}"

# "LD 1, SP 29, Text and Status, 132nd Legislature, First Special Session"
_TITLE = re.compile(
    r"LD\s+(?P<ld>\d+),\s*(?P<paper>[A-Z]{2}\s*\d+),.*?(?P<session>\d+)(?:st|nd|rd|th)\s+Legislature",
    re.IGNORECASE,
)

# "Referred to Committee on Housing and Economic Development on Jan 28, 2025."
_REFERRAL = re.compile(
    r"Referred to Committee on\s+(?P<committee>.+?)\s+on\s+"
    r"(?P<date>[A-Z][a-z]{2}\s+\d{1,2},\s+\d{4})",
)

# "Final Disposition Ought Not to Pass Pursuant To Joint Rule 310, Mar 20, 2003"
_DISPOSITION = re.compile(
    r"Final Disposition\s+(?P<disposition>.+?),\s*(?P<date>[A-Z][a-z]{2}\s+\d{1,2},\s+\d{4})",
)

# "Chaptered Law ACTPUB , Chapter 33"
_CHAPTER = re.compile(r"Chaptered Law\s+(?P<law_type>[A-Z]+)\s*,\s*Chapter\s+(?P<chapter>\w+)")

# "Governor's Action: Emergency Signed, Apr 22, 2025"
_GOVERNOR = re.compile(
    r"Governor'?s Action:\s*(?P<action>.+?),\s*(?P<date>[A-Z][a-z]{2}\s+\d{1,2},\s+\d{4})",
)

_DATE_FORMAT = "%b %d, %Y"


LD_NUMBER_WIDTH = 4


def normalize_ld(ld: int | str) -> str:
    """Zero-pad an LD number to the width `schema.parse_filename` produces.

    Filenames carry "132-LD-0001", so `BillRecord.ld_number` is "0001", while
    the status page's title says "LD 1". Storing what the page says would make
    every join against the published dataset miss: "1" != "0001". Padding here
    keeps the two keyable against each other.

    Note the deliberate asymmetry with `status_url`, which strips the padding —
    the site wants `LD=1`, not `LD=0001`.
    """
    return str(ld).strip().lstrip("0").zfill(LD_NUMBER_WIDTH) or "0".zfill(LD_NUMBER_WIDTH)


def status_url(session: int, ld: int | str) -> str:
    """URL of the status page for one bill.

    Takes a padded or unpadded LD; the site expects it unpadded.
    """
    return STATUS_URL.format(ld=int(ld), session=int(session))


def parse_date(value: str | None) -> str | None:
    """ "Jan 15, 2025" -> "2025-01-15"; anything unparseable -> None.

    Returning None rather than raising keeps one malformed cell from discarding
    a whole bill's history — the raw text is preserved on the record either way.
    """
    if not value:
        return None
    try:
        return datetime.strptime(value.strip(), _DATE_FORMAT).date().isoformat()
    except ValueError:
        return None


@dataclass(frozen=True)
class BillAction:
    """One row of the committee docket."""

    date: str | None  # ISO, None if the cell was empty or unparseable
    action: str
    result: str | None  # "ONTP", "OTP-AM", "REFERRED", ... often blank
    raw_date: str | None = None


@dataclass
class BillStatus:
    """Legislative history for one bill, as published on its status page."""

    session: int
    ld_number: str
    paper: str | None = None
    title: str | None = None
    flags: list[str] = field(default_factory=list)  # EMERGENCY, GOVERNOR'S BILL
    committee: str | None = None
    referred_date: str | None = None
    final_disposition: str | None = None
    final_disposition_date: str | None = None
    governor_action: str | None = None
    governor_action_date: str | None = None
    chaptered_law: str | None = None
    actions: list[BillAction] = field(default_factory=list)
    source_url: str = ""


def _text(node) -> str:
    return re.sub(r"\s+", " ", node.get_text(" ", strip=True)) if node else ""


def _parse_bill_title(soup: BeautifulSoup) -> str | None:
    """The bill's title, which is the page's ``<h2>``.

    Not ``#legis_field_head`` despite the name — that id wraps the
    "Choose Another Bill" legislature picker, so reading it yields the list of
    every legislature from the 112th on. The ``<h1>`` is the legislature and
    session; the ``<h3>`` is the picker's own heading.
    """
    h2 = soup.find("h2")
    if h2 and _text(h2):
        return _text(h2)

    # Fall back to the longest heading that is neither the session line nor the
    # picker, in case the heading level ever changes.
    candidates = [
        text
        for h in soup.find_all(re.compile(r"^h[1-6]$"))
        if (text := _text(h))
        and "Legislature" not in text
        and "Choose Another" not in text
        and len(text) > 25
    ]
    return max(candidates, key=len) if candidates else None


_DOCKET_HEADER = ["date", "action", "result"]


def _find_docket(soup: BeautifulSoup) -> list:
    """Rows of the committee docket, located by its header rather than position.

    Two subtleties, both found against real pages:

    * The header is **not** the first row — both tables on a status page open
      with an empty or caption row, so row 0 must not be assumed to be it.
    * Status pages carry a second table (affected statutes) whose header is
      different, and an index would silently swap the two on a page where one
      table is absent. So match on the header text and return what follows it.
    """
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        for i, row in enumerate(rows):
            cells = [c.get_text(strip=True).lower() for c in row.find_all(["th", "td"])]
            if cells[:3] == _DOCKET_HEADER:
                return rows[i + 1 :]
    return []


def parse_actions(soup: BeautifulSoup) -> list[BillAction]:
    """Committee docket rows, in page order."""
    actions = []
    for row in _find_docket(soup):
        cells = [c.get_text(" ", strip=True) for c in row.find_all(["th", "td"])]
        if len(cells) < 2 or not any(cells):
            continue
        raw_date, action = cells[0].strip(), cells[1].strip()
        result = cells[2].strip() if len(cells) > 2 else ""
        if not action:
            continue
        actions.append(
            BillAction(
                date=parse_date(raw_date),
                action=action,
                result=result or None,
                raw_date=raw_date or None,
            )
        )
    return actions


def parse_status_page(html: str, session: int | None = None, ld: str | None = None) -> BillStatus:
    """Parse one status page.

    ``session`` and ``ld`` are read from the page title; pass them to override
    when the caller already knows them (they are then trusted over the title).
    """
    soup = BeautifulSoup(html, "html.parser")

    title_match = _TITLE.search(soup.title.get_text(strip=True) if soup.title else "")
    parsed_ld = title_match.group("ld") if title_match else None
    parsed_session = int(title_match.group("session")) if title_match else None
    paper = re.sub(r"\s+", " ", title_match.group("paper")).strip() if title_match else None

    resolved_session = session if session is not None else parsed_session
    resolved_ld = ld if ld is not None else parsed_ld
    if resolved_session is None or resolved_ld is None:
        raise ValueError("Could not determine session/LD; page title did not match and no override")

    status = BillStatus(
        session=int(resolved_session),
        ld_number=normalize_ld(resolved_ld),
        paper=paper,
        source_url=status_url(int(resolved_session), resolved_ld),
    )

    flags = _text(soup.find(id="flags"))
    status.flags = [f.strip() for f in re.findall(r"\(([^)]+)\)", flags)]

    status.title = _parse_bill_title(soup)

    committee_text = _text(soup.find(id="sec3"))
    referral = _REFERRAL.search(committee_text)
    if referral:
        status.committee = referral.group("committee")
        status.referred_date = parse_date(referral.group("date"))

    disposition_text = _text(soup.find(id="sec0"))
    disposition = _DISPOSITION.search(disposition_text)
    if disposition:
        status.final_disposition = disposition.group("disposition").strip()
        status.final_disposition_date = parse_date(disposition.group("date"))

    governor = _GOVERNOR.search(disposition_text)
    if governor:
        status.governor_action = governor.group("action").strip()
        status.governor_action_date = parse_date(governor.group("date"))

    chapter = _CHAPTER.search(disposition_text)
    if chapter:
        status.chaptered_law = f"{chapter.group('law_type')} Chapter {chapter.group('chapter')}"

    status.actions = parse_actions(soup)
    return status
