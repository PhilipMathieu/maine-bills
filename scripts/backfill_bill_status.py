"""Fetch and parse bill status pages for a session (sprint node N3).

Produces the `actions` dataset config: one record per bill carrying its
legislative history — committee docket, referral, final disposition, governor's
action, chaptered law.

**Enumeration comes from the published dataset, not from the site.** Every LD
number for a session is already in the parquet we publish, so the bill directory
(`billdirectory_ps.asp`, ~13 paged fetches per session) never has to be
crawled. Fewer requests, and the LD set is exactly the one the actions table
must join against — enumerating from the site could drift from it.

**Request rate.** robots.txt for legislature.maine.gov states no `Crawl-delay`
and no `Request-rate`, so the rate is our judgment, not the site's instruction:
one request per second per session, and the workflow caps concurrent sessions.
Twelve sessions at once would mean twelve sustained requests per second against
a state government server, which is not a reasonable thing to do unasked.

Resumable: an existing output file is read back and its bills skipped, so an
interrupted run costs only what it had not yet fetched.

Usage:
    uv run python scripts/backfill_bill_status.py \\
        --session 132 \\
        --parquet-source hf://datasets/pem207/maine-bills \\
        --output data/actions
"""

import argparse
import json
import logging
import sys
import time
from pathlib import Path

import requests

from maine_bills.bill_status import BillStatus, normalize_ld, parse_status_page, status_url

logger = logging.getLogger("backfill_bill_status")

USER_AGENT = (
    "maine-bills-status/1.0 "
    "(+https://github.com/PhilipMathieu/maine-bills; research dataset tooling)"
)
REQUEST_TIMEOUT = 30
DEFAULT_DELAY = 1.0

# Retry only what a retry can fix. A 404 means the LD has no status page and
# will still have none on a second attempt.
RETRY_STATUSES = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 3


def session_ld_numbers(parquet_source: str, session: int) -> list[str]:
    """Every distinct LD number published for a session, in order."""
    import importlib.util

    report_path = Path(__file__).with_name("run_matching_report.py")
    spec = importlib.util.spec_from_file_location("_matching_report", report_path)
    if spec is None or spec.loader is None:  # pragma: no cover - packaging error
        raise ImportError(f"Cannot load the parquet loader from {report_path}")
    report = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(report)

    df = report.load_session_bills(parquet_source, session)
    # Amendments share their parent bill's LD, so distinct LDs are what we want:
    # the status page describes the bill, not each printed document.
    return sorted({normalize_ld(ld) for ld in df["ld_number"].dropna().unique()})


def fetch_status(
    http: requests.Session, session: int, ld: str, delay: float
) -> tuple[str | None, int | None]:
    """Fetch one status page. Returns (html, status_code); html is None on failure."""
    url = status_url(session, ld)
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            res = http.get(url, timeout=REQUEST_TIMEOUT)
        except requests.RequestException as e:
            logger.warning(f"LD {ld}: {type(e).__name__}: {e} (attempt {attempt})")
            time.sleep(delay * attempt)
            continue

        if res.status_code == 200:
            return res.text, 200
        if res.status_code not in RETRY_STATUSES:
            return None, res.status_code

        logger.warning(f"LD {ld}: HTTP {res.status_code} (attempt {attempt})")
        # Back off proportionally rather than hammering a server already
        # signalling distress.
        time.sleep(delay * attempt * 2)

    return None, None


def to_record(status: BillStatus) -> dict:
    """Flatten a BillStatus for parquet/JSON, keyed to join the bills table."""
    return {
        "session": status.session,
        "ld_number": status.ld_number,
        "paper": status.paper,
        "title": status.title,
        "flags": status.flags,
        "committee": status.committee,
        "referred_date": status.referred_date,
        "final_disposition": status.final_disposition,
        "final_disposition_date": status.final_disposition_date,
        "governor_action": status.governor_action,
        "governor_action_date": status.governor_action_date,
        "chaptered_law": status.chaptered_law,
        "actions": [
            {"date": a.date, "action": a.action, "result": a.result, "raw_date": a.raw_date}
            for a in status.actions
        ],
        "action_count": len(status.actions),
        "source_url": status.source_url,
    }


def is_status_page(status: BillStatus) -> bool:
    """Whether a parsed page is actually a bill's status page.

    Deliberately lenient: it rejects only a page carrying *neither* the paper
    number (from ``<title>``) nor the act title (from ``<h2>``). A real status
    page always has at least one, whatever else is missing — a bill can
    legitimately have no docket rows and no disposition — while an error or
    redirect page has neither. Requiring both would discard real bills whose
    page omits one of the two.
    """
    return bool(status.paper or status.title)


def load_existing(path: Path) -> dict[str, dict]:
    """Records already fetched, keyed by LD, so a rerun resumes."""
    if not path.exists():
        return {}
    try:
        return {r["ld_number"]: r for r in json.loads(path.read_text())}
    except (json.JSONDecodeError, KeyError, TypeError):
        logger.warning(f"{path} is unreadable; starting fresh")
        return {}


def missing_path_for(out_path: Path) -> Path:
    """Sidecar listing LDs the site has no status page for.

    Kept beside the records rather than inside them so the output file stays a
    clean actions table with no null-filled placeholder rows.
    """
    return out_path.with_name(f"{out_path.stem}-missing.json")


def load_missing(path: Path) -> set[str]:
    """LDs already known to 404, so a resumed run does not ask again."""
    if not path.exists():
        return set()
    try:
        return set(json.loads(path.read_text()))
    except (json.JSONDecodeError, TypeError):
        logger.warning(f"{path} is unreadable; will refetch missing LDs")
        return set()


def backfill(
    session: int,
    ld_numbers: list[str],
    out_path: Path,
    delay: float,
    limit: int | None = None,
    checkpoint_every: int = 50,
    recheck_missing: bool = False,
) -> dict:
    """Fetch and parse every LD's status page, writing progress as it goes."""
    records = load_existing(out_path)
    miss_path = missing_path_for(out_path)
    # A 404 is definitive — the site has no page for that LD and will not grow
    # one mid-run — so it is persisted and skipped on resume. Server errors are
    # deliberately NOT persisted: those are transient, and retrying them is the
    # main thing a resumed run is for.
    missing: set[str] = set() if recheck_missing else load_missing(miss_path)

    todo = [ld for ld in ld_numbers if ld not in records and ld not in missing]
    if limit is not None:
        todo = todo[:limit]

    logger.info(
        f"Session {session}: {len(ld_numbers)} LDs, {len(records)} already fetched, "
        f"{len(missing)} known to have no page, "
        f"{len(todo)} to go at {delay}s/request (~{len(todo) * delay / 60:.0f} min)"
    )

    failed: list[str] = []
    for i, ld in enumerate(todo, start=1):
        html, code = fetch_status(http_session(), session, ld, delay)
        if html is None:
            if code == 404:
                missing.add(ld)
            else:
                failed.append(ld)
        else:
            try:
                status = parse_status_page(html, session=session, ld=ld)
            except ValueError as e:
                # A page that does not parse is a data problem worth seeing, not
                # a reason to abandon the remaining bills.
                logger.warning(f"LD {ld}: unparseable ({e})")
                failed.append(ld)
            else:
                if not is_status_page(status):
                    # Passing session/ld as overrides means parse_status_page
                    # cannot raise on an error page — it has the identifiers it
                    # needs from us. Without this check the run would happily
                    # record an all-null row for every 200-that-isn't-a-bill and
                    # report success.
                    logger.warning(f"LD {ld}: 200 but not a status page; skipping")
                    failed.append(ld)
                else:
                    records[ld] = to_record(status)

        if i % checkpoint_every == 0:
            write_output(out_path, records)
            write_missing(miss_path, missing)
            logger.info(f"  {i}/{len(todo)} ({len(records)} records)")
        time.sleep(delay)

    write_output(out_path, records)
    write_missing(miss_path, missing)
    summary = {
        "session": session,
        "lds_total": len(ld_numbers),
        "records": len(records),
        "no_status_page": len(missing),
        "failed": len(failed),
        "failed_lds": failed[:50],
        "actions_total": sum(r["action_count"] for r in records.values()),
    }
    logger.info(
        f"Session {session}: {summary['records']} records, "
        f"{summary['actions_total']} actions, {summary['no_status_page']} without a page, "
        f"{summary['failed']} failed"
    )
    return summary


_HTTP: requests.Session | None = None


def http_session() -> requests.Session:
    global _HTTP
    if _HTTP is None:
        _HTTP = requests.Session()
        _HTTP.headers.update({"User-Agent": USER_AGENT})
    return _HTTP


def write_output(path: Path, records: dict[str, dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sorted(records.values(), key=lambda r: r["ld_number"]), indent=1))


def write_missing(path: Path, missing: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sorted(missing), indent=1))


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--session", type=int, required=True)
    parser.add_argument("--parquet-source", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--delay",
        type=float,
        default=DEFAULT_DELAY,
        help="Seconds between requests. robots.txt states no Crawl-delay, so this "
        "is our own restraint; do not lower it without a reason.",
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="Fetch at most N bills (smoke test)"
    )
    parser.add_argument(
        "--recheck-missing",
        action="store_true",
        help="Retry LDs previously recorded as having no status page. Needed only "
        "for a session still in progress, where a newly filed bill can gain a page "
        "after we looked.",
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s:%(levelname)s:%(message)s")
    args = parse_args(argv)

    ld_numbers = session_ld_numbers(args.parquet_source, args.session)
    out_path = args.output / f"actions-{args.session}.json"
    summary = backfill(
        args.session,
        ld_numbers,
        out_path,
        args.delay,
        args.limit,
        recheck_missing=args.recheck_missing,
    )

    (args.output / f"summary-{args.session}.json").write_text(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
