"""Map the Maine Legislature site so parsers can be written offline.

Two separate work items need the same thing and neither can be started from the
dev environment, whose network policy allows GitHub only:

* **Bill actions/status** (sprint track A1) — the legislative-history page for a
  bill, keyed by LD number and session.
* **Member rosters** (issue #13, items 1 and 2) — the ~190-member list per
  session, which supplies both the missing 121-124 rosters and the town/county
  needed to disambiguate same-chamber surname collisions.

Guessing URL patterns costs a full human-dispatched CI round trip per guess. So
this script discovers structure instead: a bounded, polite crawl from a handful
of seed pages that saves every response and writes a link map. One run produces
enough raw HTML to write both parsers against reality.

Politeness: honors robots.txt, one request per second by default, descriptive
User-Agent, hard cap on pages fetched, and never leaves the legislature hosts.

Usage:
    uv run python scripts/recon_legislature.py --session 132 --out data/recon
    uv run python scripts/recon_legislature.py --session 121 --max-pages 40
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import urllib.robotparser
from collections import deque
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

USER_AGENT = (
    "maine-bills-recon/1.0 "
    "(+https://github.com/PhilipMathieu/maine-bills; research dataset tooling)"
)

REQUEST_TIMEOUT = 30
MAX_SAVED_BYTES = 2_000_000  # skip saving anything implausibly large for an HTML page

# Only these hosts are ever fetched, regardless of what a page links to.
ALLOWED_HOSTS = {
    "legislature.maine.gov",
    "www.legislature.maine.gov",
    "mainelegislature.org",
    "www.mainelegislature.org",
    "lldc.mainelegislature.org",
}

# Entry points, in crawl priority order. Several are expected to 404 -- the
# point is to find out which exist, and every response is recorded either way.
SEED_TEMPLATES: list[str] = [
    # Bill status / legislative history
    "https://legislature.maine.gov/legis/bills/",
    "https://legislature.maine.gov/LawMakerWeb/search.asp",
    "https://legislature.maine.gov/legis/bills/display_ps.asp?LD=1&snum={session}",
    "https://legislature.maine.gov/LawMakerWeb/searchresults.asp?LD=1&SessionID={session}",
    # Member rosters
    "https://legislature.maine.gov/house/house/MemberProfiles/ListAlpha",
    "https://legislature.maine.gov/senate/senators/",
    "https://legislature.maine.gov/legis/senate/senators.htm",
    "https://legislature.maine.gov/house/house/MemberProfiles/ListDistrict",
    # Generic entry points, in case the paths above have moved
    "https://legislature.maine.gov/",
    "https://legislature.maine.gov/legis/",
]

# Roster-only seeds, used by --focus roster. These are the real pages the first
# crawl surfaced as links but never had budget to fetch -- the bill directory
# ate it. "Senators Listed by Municipality" is the locality -> legislator map
# issue #13 item 2 needs and OpenStates does not provide.
ROSTER_SEED_TEMPLATES: list[str] = [
    "https://legislature.maine.gov/senate/find-your-state-senator/9392",
    "https://legislature.maine.gov/senate/district-listing/9526",
    "https://legislature.maine.gov/senate/senators/9536",
    "https://legislature.maine.gov/house/house/",
    "https://legislature.maine.gov/housedems/",
    "https://legislature.maine.gov/house-independents/house-independents/9453",
    # Historical rosters are the open question -- sessions 121-124 predate the
    # current site. LawMakerWeb is the era-appropriate application, so probe it.
    "https://legislature.maine.gov/LawMakerWeb/sponsors.asp?SessionID={session}",
    "https://legislature.maine.gov/legis/house/hbiolist.htm",
    "https://legislature.maine.gov/legis/senate/sbiolist.htm",
]

# Link text/href fragments worth spending the page budget on. Ordered roughly by
# how directly they bear on the two parsers.
INTEREST_PATTERNS: list[tuple[str, str]] = [
    ("bill_status", r"display_ps|paper\s*status|legislative\s*history|bill\s*status|summary\.asp"),
    ("bill_search", r"lawmakerweb|searchresults|billtracking|/bills?/"),
    (
        "roster",
        # Party caucus pages carry the member lists, and their links say
        # "House Democrats" rather than anything with "member" in it.
        r"memberprofile|listalpha|listdistrict|senators?|representatives?|roster|members?\b"
        r"|housedems|househsubmit|democrats|republicans|independents|unenrolled"
        r"|district-listing|find-your-state|biolist",
    ),
    ("session_index", r"snum=|sessionid=|session\s*\d{3}"),
]

# --focus roster confines the crawl to roster links. Without it the bill
# directory absorbs the page budget: the first run spent 42 of 60 pages on
# billdirectory_ps.asp and never reached a single member list.
FOCUS_CATEGORIES = {"roster": {"roster"}}

_SLUG_RE = re.compile(r"[^A-Za-z0-9._-]+")


def slugify_url(url: str) -> str:
    """Turn a URL into a filesystem-safe, still-readable filename."""
    parsed = urlparse(url)
    raw = f"{parsed.netloc}{parsed.path}"
    if parsed.query:
        raw = f"{raw}__{parsed.query}"
    slug = _SLUG_RE.sub("-", raw).strip("-")
    if len(slug) > 120:
        # sha256, not hash(): PYTHONHASHSEED randomization would give the same
        # URL a different filename each run, and these land on a force-pushed
        # fixtures branch that should stay diffable between runs.
        digest = hashlib.sha256(url.encode()).hexdigest()[:8]
        slug = f"{slug[:100]}--{digest}"
    return f"{slug or 'index'}.html"


def classify(href: str, text: str) -> list[str]:
    """Label a link with every interest category it matches."""
    haystack = f"{href} {text}".lower()
    return [name for name, pattern in INTEREST_PATTERNS if re.search(pattern, haystack)]


def in_scope(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in ("http", "https") and parsed.netloc.lower() in ALLOWED_HOSTS


def extract_links(html: str, base_url: str) -> list[dict]:
    """Pull in-scope links out of a page, each with its text and categories."""
    soup = BeautifulSoup(html, features="html.parser")
    links: list[dict] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a"):
        href = (anchor.get("href") or "").strip()
        if not href or href.startswith(("#", "mailto:", "javascript:")):
            continue
        absolute = urljoin(base_url, href)
        if not in_scope(absolute) or absolute in seen:
            continue
        seen.add(absolute)
        text = " ".join(anchor.get_text(" ", strip=True).split())[:120]
        links.append({"url": absolute, "text": text, "categories": classify(absolute, text)})
    return links


def page_title(html: str) -> str:
    soup = BeautifulSoup(html, features="html.parser")
    return soup.title.get_text(strip=True)[:200] if soup.title else ""


class RobotsPolicy:
    """robots.txt lookup, cached per host; fails open if robots.txt is absent."""

    def __init__(self, http: requests.Session, respect: bool = True):
        self._http = http
        self._respect = respect
        self._parsers: dict[str, urllib.robotparser.RobotFileParser | None] = {}

    def allows(self, url: str) -> bool:
        if not self._respect:
            return True
        host = urlparse(url).netloc.lower()
        if host not in self._parsers:
            self._parsers[host] = self._load(url)
        parser = self._parsers[host]
        return True if parser is None else parser.can_fetch(USER_AGENT, url)

    def _load(self, url: str) -> urllib.robotparser.RobotFileParser | None:
        parsed = urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        try:
            res = self._http.get(robots_url, timeout=REQUEST_TIMEOUT)
            if res.status_code != 200:
                return None
            parser = urllib.robotparser.RobotFileParser()
            parser.parse(res.text.splitlines())
            return parser
        except requests.RequestException:
            return None


def fetch(url: str, http: requests.Session) -> dict:
    """GET one URL; return a record. Never raises."""
    record: dict = {"url": url, "status": None, "length": 0, "error": None, "content_type": ""}
    try:
        res = http.get(url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
        record["status"] = res.status_code
        record["length"] = len(res.content)
        record["content_type"] = res.headers.get("Content-Type", "")
        record["final_url"] = res.url
        if res.status_code == 200 and "html" in record["content_type"].lower():
            record["_html"] = res.text
    except requests.RequestException as e:
        record["error"] = f"{type(e).__name__}: {e}"
    return record


def crawl(
    seeds: list[str],
    http: requests.Session,
    out_dir: Path,
    max_pages: int,
    delay: float,
    robots: RobotsPolicy,
    categories: set[str] | None = None,
) -> list[dict]:
    """Breadth-first crawl from the seeds, saving HTML and recording link maps.

    Newly discovered links are only enqueued when they match an interest
    category, so the page budget is spent on status pages and rosters rather
    than on site chrome.
    """
    queue: deque[tuple[str, int]] = deque((s, 0) for s in seeds)
    visited: set[str] = set()
    records: list[dict] = []

    while queue and len(records) < max_pages:
        url, depth = queue.popleft()
        if url in visited:
            continue
        visited.add(url)

        if not robots.allows(url):
            records.append({"url": url, "skipped": "robots.txt disallows", "depth": depth})
            print(f"[robots] {url}")
            continue

        record = fetch(url, http)
        record["depth"] = depth
        html = record.pop("_html", None)
        if html and record["length"] <= MAX_SAVED_BYTES:
            filename = slugify_url(url)
            (out_dir / filename).write_text(html, encoding="utf-8")
            record["file"] = filename
            record["title"] = page_title(html)
            links = extract_links(html, record.get("final_url", url))
            record["links"] = links
            record["interesting"] = [link for link in links if link["categories"]]
            for link in record["interesting"]:
                if categories and not categories.intersection(link["categories"]):
                    continue
                if link["url"] not in visited:
                    queue.append((link["url"], depth + 1))

        records.append(record)
        print(f"[{record.get('status') or record.get('error')}] d{depth} {url}")
        time.sleep(delay)

    return records


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--session", type=int, default=132, help="Session number for seed URLs")
    parser.add_argument("--out", type=Path, default=Path("data/recon"), help="Output directory")
    parser.add_argument("--max-pages", type=int, default=60, help="Hard cap on pages fetched")
    parser.add_argument("--delay", type=float, default=1.0, help="Seconds between requests")
    parser.add_argument(
        "--ignore-robots",
        action="store_true",
        help="Skip robots.txt checks (default: honor them)",
    )
    parser.add_argument(
        "--focus",
        choices=["all", "roster"],
        default="all",
        help="'roster' seeds and follows member lists only, so the bill directory "
        "cannot absorb the page budget",
    )
    args = parser.parse_args()

    out_dir = args.out / f"session-{args.session}"
    out_dir.mkdir(parents=True, exist_ok=True)

    http = requests.Session()
    http.headers.update({"User-Agent": USER_AGENT})

    templates = ROSTER_SEED_TEMPLATES if args.focus == "roster" else SEED_TEMPLATES
    seeds = [template.format(session=args.session) for template in templates]
    summary: dict = {
        "session": args.session,
        "seeds": seeds,
        "max_pages": args.max_pages,
        "pages": [],
    }

    try:
        robots = RobotsPolicy(http, respect=not args.ignore_robots)
        summary["pages"] = crawl(
            seeds,
            http,
            out_dir,
            args.max_pages,
            args.delay,
            robots,
            categories=FOCUS_CATEGORIES.get(args.focus),
        )
    except Exception as e:  # noqa: BLE001 -- degrade gracefully, always write the index
        summary["fatal_error"] = f"{type(e).__name__}: {e}"
        print(f"Unexpected error: {e}", file=sys.stderr)
    finally:
        fetched = [p for p in summary["pages"] if p.get("file")]
        summary["fetched_count"] = len(fetched)
        summary["by_category"] = {
            name: sorted(
                {
                    link["url"]
                    for page in summary["pages"]
                    for link in page.get("interesting", [])
                    if name in link["categories"]
                }
            )
            for name, _ in INTEREST_PATTERNS
        }
        index_path = out_dir / "recon-index.json"
        index_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(f"\nSaved {len(fetched)} pages; wrote {index_path}")

    # Always exit 0 so CI keeps whatever was collected; recon-index.json carries
    # the success/failure detail.
    return 0


if __name__ == "__main__":
    sys.exit(main())
