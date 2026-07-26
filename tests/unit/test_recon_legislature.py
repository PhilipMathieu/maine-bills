"""Tests for the legislature site recon crawler.

Everything here is offline: the network-touching helpers are exercised through
a fake requests.Session, and the parsing helpers are pure.
"""

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "recon_legislature.py"


@pytest.fixture(scope="module")
def recon():
    spec = importlib.util.spec_from_file_location("recon_legislature", SCRIPT)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load {SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeResponse:
    def __init__(self, url, status=200, text="", content_type="text/html"):
        self.url = url
        self.status_code = status
        self.text = text
        self.content = text.encode()
        self.headers = {"Content-Type": content_type}


class FakeSession:
    """Serves canned pages by URL; records the order requests were made in."""

    def __init__(self, pages: dict):
        self.pages = pages
        self.requested: list[str] = []
        self.headers: dict = {}

    def get(self, url, timeout=None, allow_redirects=None):
        self.requested.append(url)
        page = self.pages.get(url)
        if page is None:
            return FakeResponse(url, status=404, text="not found")
        return page


# --- slugify_url ---


def test_slug_is_readable_and_encodes_query(recon):
    slug = recon.slugify_url(
        "https://legislature.maine.gov/legis/bills/display_ps.asp?LD=1&snum=132"
    )
    assert slug.endswith(".html")
    assert "display_ps.asp" in slug
    assert "LD-1" in slug and "snum-132" in slug


def test_slugs_differ_by_query_string(recon):
    base = "https://legislature.maine.gov/legis/bills/display_ps.asp?LD={}&snum=132"
    assert recon.slugify_url(base.format(1)) != recon.slugify_url(base.format(2))


def test_long_urls_are_truncated_but_stay_unique(recon):
    long_a = "https://legislature.maine.gov/" + "a" * 300
    long_b = "https://legislature.maine.gov/" + "a" * 301
    assert len(recon.slugify_url(long_a)) <= 130
    assert recon.slugify_url(long_a) != recon.slugify_url(long_b)


def test_truncated_slugs_are_stable_across_processes(recon):
    """PYTHONHASHSEED randomizes hash(), which would rename fixtures each run."""
    url = "https://legislature.maine.gov/" + "a" * 300
    expected = recon.slugify_url(url)
    script = (
        "import importlib.util,sys;"
        f"spec=importlib.util.spec_from_file_location('r', {str(SCRIPT)!r});"
        "m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);"
        f"print(m.slugify_url({url!r}))"
    )
    seeds = ["0", "1", "12345"]
    outputs = {
        subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            check=True,
            env={**os.environ, "PYTHONHASHSEED": seed},
        ).stdout.strip()
        for seed in seeds
    }
    assert outputs == {expected}


# --- classify ---


@pytest.mark.parametrize(
    "href,text,expected",
    [
        ("/legis/bills/display_ps.asp?LD=5&snum=132", "Status", "bill_status"),
        ("/LawMakerWeb/searchresults.asp", "Search", "bill_search"),
        ("/house/house/MemberProfiles/ListAlpha", "Members", "roster"),
        ("/senate/senators/", "Senators", "roster"),
        ("/x?snum=131", "Session", "session_index"),
    ],
)
def test_classify_labels_interesting_links(recon, href, text, expected):
    assert expected in recon.classify(href, text)


def test_classify_returns_empty_for_site_chrome(recon):
    assert recon.classify("/about/contact.htm", "Contact Us") == []


# --- in_scope ---


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://legislature.maine.gov/legis/", True),
        ("http://lldc.mainelegislature.org/Open/LDs/132/", True),
        ("https://example.com/legis/bills/", False),
        ("mailto:someone@legislature.maine.gov", False),
    ],
)
def test_in_scope_confines_the_crawl(recon, url, expected):
    assert recon.in_scope(url) is expected


# --- extract_links ---


def test_extract_links_resolves_relative_hrefs_and_drops_offsite(recon):
    html = """
    <a href="display_ps.asp?LD=1&snum=132">LD 1 Status</a>
    <a href="https://example.com/elsewhere">Offsite</a>
    <a href="#top">Anchor</a>
    <a href="mailto:x@y.gov">Mail</a>
    """
    links = recon.extract_links(html, "https://legislature.maine.gov/legis/bills/")
    assert [link["url"] for link in links] == [
        "https://legislature.maine.gov/legis/bills/display_ps.asp?LD=1&snum=132"
    ]
    assert "bill_status" in links[0]["categories"]


def test_extract_links_deduplicates(recon):
    html = '<a href="/a">One</a><a href="/a">One again</a>'
    links = recon.extract_links(html, "https://legislature.maine.gov/")
    assert len(links) == 1


# --- crawl ---


def _index_page(hrefs):
    body = "".join(f'<a href="{h}">Paper Status</a>' for h in hrefs)
    return f"<html><head><title>Bills</title></head><body>{body}</body></html>"


def test_crawl_follows_interesting_links_and_saves_html(recon, tmp_path):
    root = "https://legislature.maine.gov/legis/bills/"
    child = "https://legislature.maine.gov/legis/bills/display_ps.asp?LD=1&snum=132"
    pages = {
        root: FakeResponse(root, text=_index_page(["display_ps.asp?LD=1&snum=132"])),
        child: FakeResponse(child, text="<html><title>LD 1</title><body>LD 1</body></html>"),
    }
    http = FakeSession(pages)
    records = recon.crawl([root], http, tmp_path, max_pages=10, delay=0, robots=_AllowAll())

    assert [r["url"] for r in records] == [root, child]
    assert all(r["status"] == 200 for r in records)
    saved = sorted(p.name for p in tmp_path.glob("*.html"))
    assert len(saved) == 2
    assert records[1]["title"] == "LD 1"


def test_crawl_does_not_follow_uninteresting_links(recon, tmp_path):
    root = "https://legislature.maine.gov/"
    html = '<html><body><a href="/about/contact.htm">Contact Us</a></body></html>'
    http = FakeSession({root: FakeResponse(root, text=html)})
    records = recon.crawl([root], http, tmp_path, max_pages=10, delay=0, robots=_AllowAll())
    assert len(records) == 1


def test_crawl_respects_the_page_cap(recon, tmp_path):
    hrefs = [f"display_ps.asp?LD={i}&snum=132" for i in range(1, 20)]
    root = "https://legislature.maine.gov/legis/bills/"
    pages = {root: FakeResponse(root, text=_index_page(hrefs))}
    for href in hrefs:
        url = root + href
        pages[url] = FakeResponse(url, text=f"<html><title>{href}</title></html>")
    http = FakeSession(pages)
    records = recon.crawl([root], http, tmp_path, max_pages=5, delay=0, robots=_AllowAll())
    assert len(records) == 5


def test_focus_confines_the_crawl_to_one_category(recon, tmp_path):
    """The first run spent 42 of 60 pages on the bill directory and never
    reached a member list; --focus roster is what prevents that."""
    root = "https://legislature.maine.gov/senate/senators/9536"
    roster = "https://legislature.maine.gov/senate/district-listing/9526"
    bills = "https://legislature.maine.gov/bills/billdirectory_ps.asp?snum=132&ldFrom=0"
    html = (
        f'<html><title>Senators</title><body><a href="{roster}">Senators by District</a>'
        f'<a href="{bills}">Bill Directory</a></body></html>'
    )
    pages = {
        root: FakeResponse(root, text=html),
        roster: FakeResponse(roster, text="<html><title>Districts</title></html>"),
        bills: FakeResponse(bills, text="<html><title>Bills</title></html>"),
    }

    unfocused_dir = tmp_path / "unfocused"
    focused_dir = tmp_path / "focused"
    unfocused_dir.mkdir()
    focused_dir.mkdir()

    http = FakeSession(pages)
    unfocused = recon.crawl([root], http, unfocused_dir, max_pages=10, delay=0, robots=_AllowAll())
    assert bills in [r["url"] for r in unfocused]

    http = FakeSession(pages)
    focused = recon.crawl(
        [root],
        http,
        focused_dir,
        max_pages=10,
        delay=0,
        robots=_AllowAll(),
        categories={"roster"},
    )
    urls = [r["url"] for r in focused]
    assert roster in urls
    assert bills not in urls


def test_party_caucus_links_count_as_roster(recon):
    """Caucus pages carry the member lists but their text says "House Democrats"."""
    for href, text in [
        ("https://legislature.maine.gov/housedems/", "House Democrats"),
        ("/house-independents/house-independents/9453", "House Independents"),
        ("/senate/find-your-state-senator/9392", "Senators Listed by Municipality"),
        ("/senate/district-listing/9526", "Senators Listed by Senate District"),
    ]:
        assert "roster" in recon.classify(href, text), href


def test_crawl_records_failures_without_raising(recon, tmp_path):
    missing = "https://legislature.maine.gov/legis/nope/"
    http = FakeSession({})
    records = recon.crawl([missing], http, tmp_path, max_pages=5, delay=0, robots=_AllowAll())
    assert records[0]["status"] == 404
    assert list(tmp_path.glob("*.html")) == []


def test_crawl_skips_pages_robots_disallows(recon, tmp_path):
    url = "https://legislature.maine.gov/legis/bills/"
    http = FakeSession({url: FakeResponse(url, text="<html><title>Bills</title></html>")})
    records = recon.crawl([url], http, tmp_path, max_pages=5, delay=0, robots=_DenyAll())
    assert records[0]["skipped"] == "robots.txt disallows"
    assert http.requested == []


class _AllowAll:
    def allows(self, url):
        return True


class _DenyAll:
    def allows(self, url):
        return False


# --- RobotsPolicy ---


def test_robots_policy_fails_open_when_robots_txt_is_missing(recon):
    http = FakeSession({})
    policy = recon.RobotsPolicy(http)
    assert policy.allows("https://legislature.maine.gov/legis/bills/") is True


def test_robots_policy_honors_disallow(recon):
    robots_url = "https://legislature.maine.gov/robots.txt"
    body = "User-agent: *\nDisallow: /private/\n"
    http = FakeSession({robots_url: FakeResponse(robots_url, text=body, content_type="text/plain")})
    policy = recon.RobotsPolicy(http)
    assert policy.allows("https://legislature.maine.gov/private/x") is False
    assert policy.allows("https://legislature.maine.gov/legis/bills/") is True


def test_robots_policy_fetches_robots_txt_once_per_host(recon):
    robots_url = "https://legislature.maine.gov/robots.txt"
    http = FakeSession({robots_url: FakeResponse(robots_url, text="User-agent: *\n")})
    policy = recon.RobotsPolicy(http)
    policy.allows("https://legislature.maine.gov/a")
    policy.allows("https://legislature.maine.gov/b")
    assert http.requested.count(robots_url) == 1


def test_ignore_robots_skips_the_lookup_entirely(recon):
    http = FakeSession({})
    policy = recon.RobotsPolicy(http, respect=False)
    assert policy.allows("https://legislature.maine.gov/private/x") is True
    assert http.requested == []


# --- main ---


def test_main_always_writes_the_index(recon, tmp_path, monkeypatch):
    """Even a run where every seed 404s must leave a readable index behind."""
    monkeypatch.setattr(recon.requests, "Session", lambda: FakeSession({}))
    monkeypatch.setattr(
        recon.sys,
        "argv",
        ["recon_legislature.py", "--session", "132", "--out", str(tmp_path), "--delay", "0"],
    )
    assert recon.main() == 0

    index = json.loads((tmp_path / "session-132" / "recon-index.json").read_text())
    assert index["session"] == 132
    assert index["fetched_count"] == 0
    assert set(index["by_category"]) == {name for name, _ in recon.INTEREST_PATTERNS}
    assert all("snum=132" not in seed or "132" in seed for seed in index["seeds"])


def test_seeds_are_formatted_with_the_session(recon, tmp_path, monkeypatch):
    monkeypatch.setattr(recon.requests, "Session", lambda: FakeSession({}))
    monkeypatch.setattr(
        recon.sys,
        "argv",
        ["recon_legislature.py", "--session", "121", "--out", str(tmp_path), "--delay", "0"],
    )
    recon.main()
    index = json.loads((tmp_path / "session-121" / "recon-index.json").read_text())
    assert any("snum=121" in seed for seed in index["seeds"])
    assert not any("{session}" in seed for seed in index["seeds"])


# --- robots.txt capture ---


def test_directive_reads_crawl_delay(recon):
    body = "User-agent: *\nCrawl-delay: 10\nDisallow: /LawMakerWeb/\n"
    assert recon._directive(body, "crawl-delay") == "10"
    assert recon._directive(body, "request-rate") is None


def test_directive_ignores_comments_and_case(recon):
    body = "# Crawl-delay: 99\nUser-agent: *\nCRAWL-DELAY: 5  # be nice\n"
    assert recon._directive(body, "crawl-delay") == "5"


def test_robots_policy_keeps_the_raw_text(recon):
    robots_url = "https://legislature.maine.gov/robots.txt"
    body = "User-agent: *\nCrawl-delay: 10\nDisallow: /LawMakerWeb/\n"
    http = FakeSession({robots_url: FakeResponse(robots_url, text=body)})
    policy = recon.RobotsPolicy(http)
    policy.allows("https://legislature.maine.gov/a")
    assert policy.raw["legislature.maine.gov"] == body


def test_main_records_and_saves_robots(recon, tmp_path, monkeypatch):
    robots_url = "https://legislature.maine.gov/robots.txt"
    body = "User-agent: *\nCrawl-delay: 10\n"
    monkeypatch.setattr(
        recon.requests,
        "Session",
        lambda: FakeSession({robots_url: FakeResponse(robots_url, text=body)}),
    )
    monkeypatch.setattr(
        recon.sys,
        "argv",
        ["recon_legislature.py", "--session", "132", "--out", str(tmp_path), "--delay", "0"],
    )
    recon.main()

    out = tmp_path / "session-132"
    index = json.loads((out / "recon-index.json").read_text())
    assert index["robots"]["legislature.maine.gov"]["crawl_delay"] == "10"
    assert (out / "robots-legislature.maine.gov.txt").read_text() == body
