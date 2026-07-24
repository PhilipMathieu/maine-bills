"""Fetch a sample of Maine Legislature bill *status* pages as parser fixtures.

The bill PDFs come from lldc.mainelegislature.org (see BillScraper), but the
legislative-history / status pages live elsewhere on legislature.maine.gov and
their exact URL scheme is not verifiable from the network-restricted dev
environment. So this script works in two phases:

1. Probe: try several candidate URL patterns for LD 1 (and confirm with LD 2,
   to rule out soft-404 pages that return 200 for anything) and record every
   response in probe-results.json.
2. Fetch: use the winning pattern to download status pages for LD 1..N at
   1 request/second with a descriptive User-Agent.

It degrades gracefully: any probe/fetch failure is recorded, whatever HTML was
retrieved is kept, probe-results.json is always written, and the exit code is
0 so CI can still upload partial results.

Usage:
    uv run python scripts/fetch_status_samples.py --session 132 --count 25 \
        --out data/status-samples
    uv run python scripts/fetch_status_samples.py --session 132 --probe-only
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

import requests

USER_AGENT = (
    "maine-bills-fixture-fetcher/1.0 "
    "(+https://github.com/PhilipMathieu/maine-bills; research dataset tooling)"
)

# Candidate URL patterns for a bill status page, in priority order.
# Assumptions (unverified from the dev environment -- hence the probe):
#   - `display_ps.asp?LD=<n>&snum=<session>` is the historical "paper status"
#     page under /legis/bills/ on both legislature.maine.gov and
#     www.mainelegislature.org.
#   - LawMakerWeb summary.asp normally takes an opaque ID, but some deployments
#     accept LD/session query params; included as a long-shot fallback.
CANDIDATE_PATTERNS: list[str] = [
    "https://legislature.maine.gov/legis/bills/display_ps.asp?LD={ld}&snum={session}",
    "https://www.mainelegislature.org/legis/bills/display_ps.asp?LD={ld}&snum={session}",
    "https://legislature.maine.gov/bills/display_ps.asp?LD={ld}&snum={session}",
    "https://legislature.maine.gov/LawMakerWeb/summary.asp?LD={ld}&SessionID={session}",
]

REQUEST_TIMEOUT = 30
MIN_PLAUSIBLE_LENGTH = 500  # bytes of HTML below which a page is likely an error stub


def build_url(pattern: str, session: int, ld: int) -> str:
    return pattern.format(session=session, ld=ld)


def fetch_page(url: str, http: requests.Session) -> dict:
    """GET one URL; return a result record (never raises)."""
    record: dict = {"url": url, "ok": False, "status": None, "length": 0, "error": None}
    try:
        res = http.get(url, timeout=REQUEST_TIMEOUT)
        record["status"] = res.status_code
        record["length"] = len(res.content)
        record["content_type"] = res.headers.get("Content-Type", "")
        if res.status_code == 200:
            record["ok"] = True
            record["text"] = res.text
    except requests.RequestException as e:
        record["error"] = f"{type(e).__name__}: {e}"
    return record


def looks_like_status_page(record: dict, ld: int) -> bool:
    """Heuristic: 200 HTML of plausible size that mentions the LD number."""
    if not record.get("ok"):
        return False
    if "html" not in record.get("content_type", "").lower():
        return False
    text = record.get("text", "")
    if len(text) < MIN_PLAUSIBLE_LENGTH:
        return False
    return re.search(rf"\bLD\s*0*{ld}\b", text, re.IGNORECASE) is not None


def probe(session: int, http: requests.Session, delay: float) -> tuple[str | None, list[dict]]:
    """Try each candidate pattern for LD 1; confirm the winner with LD 2.

    Returns (winning_pattern_or_None, probe_records).
    """
    records: list[dict] = []
    winner: str | None = None

    for pattern in CANDIDATE_PATTERNS:
        rec = fetch_page(build_url(pattern, session, 1), http)
        rec["pattern"] = pattern
        rec["ld"] = 1
        rec["plausible"] = looks_like_status_page(rec, 1)
        text_ld1 = rec.pop("text", "")
        records.append(rec)
        time.sleep(delay)

        if not rec["plausible"] or winner is not None:
            continue

        # Confirm with LD 2: content must also be plausible AND differ from
        # LD 1's, otherwise this is likely a soft-404 that 200s on anything.
        rec2 = fetch_page(build_url(pattern, session, 2), http)
        rec2["pattern"] = pattern
        rec2["ld"] = 2
        rec2["plausible"] = looks_like_status_page(rec2, 2)
        text_ld2 = rec2.pop("text", "")
        rec2["differs_from_ld1"] = text_ld2 != text_ld1
        records.append(rec2)
        time.sleep(delay)

        if rec2["plausible"] and rec2["differs_from_ld1"]:
            winner = pattern

    return winner, records


def fetch_samples(
    pattern: str,
    session: int,
    count: int,
    out_dir: Path,
    http: requests.Session,
    delay: float,
) -> list[dict]:
    """Fetch status pages for LD 1..count, saving HTML files; returns records."""
    results: list[dict] = []
    for ld in range(1, count + 1):
        rec = fetch_page(build_url(pattern, session, ld), http)
        rec["ld"] = ld
        rec["plausible"] = looks_like_status_page(rec, ld)
        text = rec.pop("text", None)
        if rec["ok"] and text:
            path = out_dir / f"LD-{ld:04d}.html"
            path.write_text(text, encoding="utf-8")
            rec["file"] = path.name
        results.append(rec)
        status = rec["status"] if rec["status"] is not None else rec["error"]
        print(f"LD {ld}: {status} ({rec['length']} bytes)")
        time.sleep(delay)
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--session", type=int, default=132, help="Legislative session number")
    parser.add_argument("--count", type=int, default=25, help="Number of LDs to sample (1..N)")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("data/status-samples"),
        help="Output directory for HTML files and probe-results.json",
    )
    parser.add_argument(
        "--probe-only",
        action="store_true",
        help="Only probe candidate URL patterns; skip the sample fetch",
    )
    parser.add_argument(
        "--delay", type=float, default=1.0, help="Seconds between requests (be polite)"
    )
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)

    http = requests.Session()
    http.headers.update({"User-Agent": USER_AGENT})

    output: dict = {
        "session": args.session,
        "count_requested": args.count,
        "candidate_patterns": CANDIDATE_PATTERNS,
        "winning_pattern": None,
        "probe": [],
        "fetch": [],
    }

    try:
        winner, probe_records = probe(args.session, http, args.delay)
        output["probe"] = probe_records
        output["winning_pattern"] = winner

        if winner is None:
            print("PROBE FAILED: no candidate URL pattern produced a plausible status page.")
            print("See probe-results.json for per-pattern responses.")
        else:
            print(f"Winning pattern: {winner}")
            if not args.probe_only:
                output["fetch"] = fetch_samples(
                    winner, args.session, args.count, args.out, http, args.delay
                )
                fetched = sum(1 for r in output["fetch"] if r.get("file"))
                print(f"Fetched {fetched}/{args.count} pages into {args.out}")
    except Exception as e:  # noqa: BLE001 -- degrade gracefully, always write results
        output["fatal_error"] = f"{type(e).__name__}: {e}"
        print(f"Unexpected error: {e}", file=sys.stderr)
    finally:
        results_path = args.out / "probe-results.json"
        results_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
        print(f"Wrote {results_path}")

    # Always exit 0 so CI uploads whatever was collected; probe-results.json
    # carries the success/failure detail.
    return 0


if __name__ == "__main__":
    sys.exit(main())
