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
import os
import re
import signal
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

# Stop the session after this many consecutive failures. Per-LD retry alone is
# not enough: if the site starts refusing -- a WAF block, a rate limiter, an
# outage -- every remaining LD is still attempted at the full request rate, so a
# 2,000-bill session becomes 2,000 futile requests against a server that has
# already said stop, times however many sessions run at once. The point of this
# script's throttle is not to be a burden; continuing past a sustained refusal
# would be exactly that.
MAX_CONSECUTIVE_FAILURES = 10

# A long run of "no such bill" WITH NOTHING RECORDED YET is a systemic problem,
# not a sparse session. The concrete case is a wrong session number: the site
# answers the identical not-found body for every LD, which without this guard
# produced 2,000 requests, an empty actions table, and a green check.
#
# The `and not records` half matters. An earlier version aborted on the run
# length alone, justified by "enumeration comes from the parquet, so every LD
# we ask about is one we hold a document for". That reasoning is wrong: the
# documents come from lldc.mainelegislature.org and the status pages from
# legislature.maine.gov, which are independent systems. Review found session
# 124 has a real page at LD 1800 and none at LD 1850 -- so a contiguous gap
# where the document repository outruns the status application is a normal
# thing that would have aborted a perfectly healthy session. Requiring zero
# records keeps the wrong-session protection intact (that case never records
# anything) while making a mid-session gap harmless.
MAX_CONSECUTIVE_MISSING = 50

# A Retry-After longer than this ends the session rather than being slept
# through. Sitting out a 300s wait three times per bill is how the breaker
# failed to fire inside the job timeout.
RETRY_AFTER_ABORT = 120.0

# How many failures a single end-of-run retry pass will take on. Sized to catch
# the transient tail -- the smoke run finished sessions 132 and 121 with exactly
# 7 read timeouts each out of ~2,000 -- while refusing to re-drive a session
# that failed in bulk, which is what the breakers are for.
MAX_RETRY_PASS = 50

# Enumeration is a single anonymous HuggingFace API call per session, made at
# job start. Several sessions launching together on one runner IP can exhaust
# the anonymous budget (500 requests per 300s), which killed session 126 of the
# first full backfill four seconds in. The retry is generous because the window
# is short and the alternative is losing the whole session.
ENUMERATION_ATTEMPTS = 4


class SiteRefusing(Exception):
    """The site asked us to go away for longer than this run should wait."""


# The site does NOT return 404 for a bill that does not exist. It answers 200
# with a normal-looking page whose only tell is this heading. Verified against
# LD=9999 and LD=99999 on session 132, and every real page sampled across
# sessions 121-132 carries a paper number while this one does not.
#
# This matters more than it looks: it means the HTTP-404 path below is
# effectively dead code on this host, and every nonexistent LD arrives as a 200
# that must be classified by shape instead.
NOT_FOUND_MARKER = "Cannot find requested paper"


def _load_report_module():
    """The parquet loader from run_matching_report.py.

    Separate from its caller so a test can substitute it without a network or a
    real parquet file.
    """
    import importlib.util

    report_path = Path(__file__).with_name("run_matching_report.py")
    spec = importlib.util.spec_from_file_location("_matching_report", report_path)
    if spec is None or spec.loader is None:  # pragma: no cover - packaging error
        raise ImportError(f"Cannot load the parquet loader from {report_path}")
    report = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(report)
    return report


def _hf_retry_after(error: Exception) -> float | None:
    """Seconds HuggingFace asked us to wait, if this is a rate limit.

    The 429 body carries "Retry after N seconds"; the header is not always
    present on the exception, so the message is the reliable source.
    """
    text = str(error)
    if "429" not in text and "rate limit" not in text.lower():
        return None
    match = re.search(r"Retry after (\d+) second", text)
    return min(float(match.group(1)), 300.0) if match else 60.0


def session_ld_numbers(
    parquet_source: str, session: int, attempts: int = ENUMERATION_ATTEMPTS
) -> list[str]:
    """Every distinct LD number published for a session, in order.

    Retries a HuggingFace rate limit. Enumeration is one anonymous API call per
    session at job start, and with several sessions launching at once on a
    shared runner IP that is enough to exhaust the anonymous budget: session
    126 of the first full backfill died four seconds in with "429 ... 0/500
    requests remaining in current 300s window", losing an otherwise healthy
    session's worth of work.

    Deliberately not solved with a token. HF_TOKEN is scoped to the
    `huggingface-publish` environment so it is only ever exposed to approved
    publish runs (docs/GOVERNANCE.md); handing it to an ungated read job to
    dodge a rate limit would trade a publish-gate guarantee for a retry loop.
    """
    report = _load_report_module()

    for attempt in range(1, attempts + 1):
        try:
            df = report.load_session_bills(parquet_source, session)
        except Exception as e:
            wait = _hf_retry_after(e)
            if wait is None or attempt == attempts:
                raise
            logger.warning(
                f"Session {session}: enumeration rate-limited, waiting {wait:.0f}s "
                f"(attempt {attempt}/{attempts})"
            )
            time.sleep(wait)
        else:
            # Amendments share their parent bill's LD, so distinct LDs are what
            # we want: the status page describes the bill, not each printed
            # document.
            return sorted({normalize_ld(ld) for ld in df["ld_number"].dropna().unique()})

    raise RuntimeError(f"Session {session}: enumeration failed after {attempts} attempts")


def retry_after(response, default: float) -> float:
    """Honor a ``Retry-After`` header, capped so a silly value cannot stall us.

    Only the delta-seconds form is handled; the HTTP-date form is rare and a
    miss just falls back to our own backoff.
    """
    raw = getattr(response, "headers", {}).get("Retry-After")
    if not raw:
        return default
    try:
        return min(max(float(raw), 0.0), 300.0)
    except (TypeError, ValueError):
        return default


def fetch_status(
    http: requests.Session, session: int, ld: str, delay: float
) -> tuple[str | None, int | None]:
    """Fetch one status page. Returns (html, status_code); html is None on failure."""
    try:
        url = status_url(session, ld)
    except ValueError as e:
        # normalize_ld int-casts. Unreachable through the parquet enumeration
        # (schema.FILENAME_PATTERN constrains the number to \d+), but a bad LD
        # here would otherwise kill the whole session having written nothing.
        logger.warning(f"LD {ld!r}: not a usable LD number ({e})")
        return None, None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        last = attempt == MAX_ATTEMPTS
        try:
            res = http.get(url, timeout=REQUEST_TIMEOUT)
        except requests.RequestException as e:
            logger.warning(f"LD {ld}: {type(e).__name__}: {e} (attempt {attempt})")
            # Never sleep after the final attempt: the wait is a backoff before
            # a retry, and there is no retry left. Sleeping anyway is pure
            # dead time, and with a long Retry-After it was enough to keep the
            # circuit breaker from ever firing inside the job timeout.
            if not last:
                time.sleep(delay * attempt)
            continue

        if res.status_code == 200:
            return res.text, 200
        if res.status_code not in RETRY_STATUSES:
            return None, res.status_code

        wait = retry_after(res, delay * attempt * 2)
        if wait > RETRY_AFTER_ABORT:
            # The server has named a wait longer than we are willing to sit
            # through. Waiting it out would park the job; ignoring it would be
            # rude. Stopping is the honest reading of what it asked for.
            raise SiteRefusing(
                f"HTTP {res.status_code} with Retry-After {wait:.0f}s on LD {ld}; "
                f"the site is asking us to back off for longer than this run should wait"
            )

        logger.warning(f"LD {ld}: HTTP {res.status_code} (attempt {attempt})")
        # Back off proportionally rather than hammering a server already
        # signalling distress -- and when it has told us exactly how long to
        # wait, wait that long instead of guessing.
        if not last:
            time.sleep(wait)

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

    Keys on the paper number specifically. An earlier version accepted ``paper
    or title``, which the site's not-found page defeats: ``_parse_bill_title``
    falls back to the longest heading, so "Cannot find requested paper, please
    provide a Paper or LD number in the box to the left." was read as an act
    title and the page recorded as a real bill. Every nonexistent LD in every
    session would have landed in the actions table titled with an error
    message, and the run would have reported complete success.

    Every real page sampled across sessions 121-132 carries a paper number
    (SP 29, HP 1287, ...) whatever else is missing — a bill can legitimately
    have no docket rows and no disposition — and the not-found page carries
    none.
    """
    return bool(status.paper)


def classify_page(html: str, status: BillStatus) -> str:
    """One of "ok", "missing", or "unrecognized".

    The distinction that matters is definitive-vs-transient. "missing" is the
    site telling us this LD does not exist, which is permanent and worth
    remembering. "unrecognized" is a 200 we cannot account for — a WAF
    challenge, an outage page, a redirect to a portal — which may well clear on
    a later run, so it counts as a failure and is never persisted as missing.
    Collapsing the two would let a transient block be recorded as "this bill
    does not exist" and never asked about again.
    """
    if is_status_page(status):
        return "ok"
    if NOT_FOUND_MARKER in html:
        return "missing"
    return "unrecognized"


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
    # "No such bill" is definitive — the site will not grow a page for it
    # mid-run — so it is persisted and skipped on resume. Failures are
    # deliberately NOT persisted: those are transient, and retrying them is the
    # main thing a resumed run is for.
    #
    # Under --recheck-missing the known set is still LOADED, and entries are
    # removed only when the site is observed to answer for them. Starting from
    # an empty set instead means a recheck that does not finish -- a --limit, a
    # crash, the job timeout -- rewrites the sidecar with only what it happened
    # to re-reach and forgets the rest.
    known_missing = load_missing(miss_path)
    missing: set[str] = set(known_missing)

    skip = set(records) if recheck_missing else set(records) | missing
    todo = [ld for ld in ld_numbers if ld not in skip]
    if limit is not None:
        todo = todo[:limit]

    logger.info(
        f"Session {session}: {len(ld_numbers)} LDs, {len(records)} already fetched, "
        f"{len(missing)} known to have no page, "
        f"{len(todo)} to go at {delay}s/request (~{len(todo) * delay / 60:.0f} min)"
    )

    failed: list[str] = []
    consecutive_failures = 0
    consecutive_missing = 0
    aborted = False
    abort_reason: str | None = None

    def fetch_one(ld: str) -> str:
        """Fetch, classify and record one bill. Returns its outcome.

        Raises SiteRefusing, which the caller turns into an abort.
        """
        html, code = fetch_status(http_session(), session, ld, delay)
        if html is None:
            # Retained for correctness on a host that does hard-404, though
            # legislature.maine.gov does not -- see NOT_FOUND_MARKER.
            return "missing" if code == 404 else "failed"
        try:
            status = parse_status_page(html, session=session, ld=ld)
        except ValueError as e:
            # A page that does not parse is a data problem worth seeing, not
            # a reason to abandon the remaining bills.
            logger.warning(f"LD {ld}: unparseable ({e})")
            return "failed"
        outcome = classify_page(html, status)
        if outcome == "ok":
            records[ld] = to_record(status)
        elif outcome == "unrecognized":
            logger.warning(f"LD {ld}: 200 but not a recognizable page")
        return outcome

    for i, ld in enumerate(todo, start=1):
        try:
            outcome = fetch_one(ld)
        except SiteRefusing as e:
            logger.error(f"Session {session}: {e}; stopping after {i - 1}/{len(todo)}")
            aborted, abort_reason = True, str(e)
            break

        if outcome == "ok":
            missing.discard(ld)
            consecutive_failures = consecutive_missing = 0
        elif outcome == "missing":
            missing.add(ld)
            # Not a failure: the site answered us plainly. It must not count
            # toward the failure breaker, or a session with genuine gaps would
            # abort. It gets its own, looser breaker instead.
            consecutive_failures = 0
            consecutive_missing += 1
            if consecutive_missing >= MAX_CONSECUTIVE_MISSING and not records:
                logger.error(
                    f"Session {session}: {consecutive_missing} bills with no status page "
                    f"and not one real page yet; stopping after {i}/{len(todo)}. That "
                    f"pattern means the session number is wrong or the site has changed, "
                    f"not that these particular bills are absent."
                )
                aborted = True
                abort_reason = f"{consecutive_missing} consecutive bills with no status page"
                break
        else:
            failed.append(ld)
            consecutive_missing = 0
            consecutive_failures += 1
            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                logger.error(
                    f"Session {session}: {consecutive_failures} consecutive failures; "
                    f"stopping after {i}/{len(todo)}. The site is not answering, and "
                    f"continuing would be {len(todo) - i} more requests at it."
                )
                aborted = True
                abort_reason = f"{consecutive_failures} consecutive failures"
                break

        if i % checkpoint_every == 0:
            write_output(out_path, records)
            write_missing(miss_path, missing)
            logger.info(f"  {i}/{len(todo)} ({len(records)} records)")
        time.sleep(delay)

    # One sweep back over the failures before giving up on them.
    #
    # The smoke run made the case: sessions 132 and 121 each finished with 2034
    # of 2041 and 1957 of 1965, failing only on a handful of read timeouts --
    # and each reported incomplete and exited 1 over them. Because a CI job
    # cannot resume, recovering those seven would have meant refetching two
    # thousand pages. Seven requests here instead is both the cheaper and the
    # more considerate answer.
    #
    # Bounded deliberately: one pass, and only when the failures are few enough
    # to look transient. A session that failed in bulk has something actually
    # wrong with it, and retrying all of it is the behaviour the breakers exist
    # to prevent.
    if failed and not aborted and len(failed) <= MAX_RETRY_PASS:
        retrying, failed = failed, []
        logger.info(f"Session {session}: retrying {len(retrying)} failed bills")
        for ld in retrying:
            try:
                outcome = fetch_one(ld)
            except SiteRefusing as e:
                logger.error(f"Session {session}: {e} (during retry pass)")
                aborted, abort_reason = True, str(e)
                failed.extend(retrying[retrying.index(ld) :])
                break
            if outcome == "missing":
                missing.add(ld)
            elif outcome != "ok":
                failed.append(ld)
            time.sleep(delay)
        logger.info(
            f"Session {session}: retry recovered {len(retrying) - len(failed)} of {len(retrying)}"
        )

    write_output(out_path, records)
    write_missing(miss_path, missing)
    # A partial actions table is shape-identical to a complete one, so the
    # summary has to say which it is. Without `complete` and `not_attempted`,
    # a run that aborted at LD 40 of 2,000 produces a file that looks like a
    # small session.
    # Measured against the FULL LD set, not against `todo`. Deriving it from
    # `todo` made a --limit smoke test report complete: the run finishes
    # everything it was asked for while thousands of bills remain unfetched.
    outstanding = [ld for ld in ld_numbers if ld not in records and ld not in missing]
    # `records` must be non-empty. Without it, a run where EVERY bill came back
    # "no such bill" has nothing outstanding and reports success: a wrong
    # session number does exactly that, since the site answers the identical
    # not-found body for every LD. Green check, empty actions table.
    summary = {
        "session": session,
        "lds_total": len(ld_numbers),
        "records": len(records),
        "no_status_page": len(missing),
        "failed": len(failed),
        "failed_lds": failed,
        "not_attempted": len(outstanding),
        "aborted": aborted,
        "abort_reason": abort_reason,
        "complete": not aborted and not outstanding and bool(records),
        "actions_total": sum(r["action_count"] for r in records.values()),
    }
    logger.info(
        f"Session {session}: {summary['records']} records, "
        f"{summary['actions_total']} actions, {summary['no_status_page']} without a page, "
        f"{summary['failed']} failed, {len(outstanding)} not attempted"
        f"{' (ABORTED)' if aborted else ''}"
    )
    return summary


_HTTP: requests.Session | None = None


def http_session() -> requests.Session:
    global _HTTP
    if _HTTP is None:
        _HTTP = requests.Session()
        _HTTP.headers.update({"User-Agent": USER_AGENT})
    return _HTTP


def write_json(path: Path, payload) -> None:
    """Write atomically, so a kill mid-checkpoint cannot truncate the file.

    A bare ``write_text`` leaves a half-written file if the process dies during
    it, and ``load_existing`` treats an unparseable file as "start fresh" —
    which at session scale means silently re-requesting ~2,000 pages that were
    already fetched.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    # PID in the temp name: two processes writing the same session would
    # otherwise share one temp path, interleave into the same file, and rename
    # corrupt JSON into place — defeating the point of writing atomically. The
    # matrix dedupe prevents that within one dispatch, but not across two, nor
    # a local run alongside CI.
    tmp = path.with_suffix(f"{path.suffix}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(payload, indent=1))
    tmp.replace(path)


def write_output(path: Path, records: dict[str, dict]) -> None:
    write_json(path, sorted(records.values(), key=lambda r: r["ld_number"]))


def write_missing(path: Path, missing: set[str]) -> None:
    write_json(path, sorted(missing))


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


def _exit_on_sigterm(_signum, _frame):
    """Turn SIGTERM into SystemExit so the summary still gets written.

    Python's default SIGTERM disposition terminates the process outright — it
    does not raise, so `except BaseException` never runs and a job killed at
    its timeout left a partial actions table with no summary at all, which is
    indistinguishable from a small complete session. 143 is the conventional
    128+SIGTERM exit code.
    """
    sys.exit(143)


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s:%(levelname)s:%(message)s")
    signal.signal(signal.SIGTERM, _exit_on_sigterm)
    args = parse_args(argv)

    out_path = args.output / f"actions-{args.session}.json"
    summary_path = args.output / f"summary-{args.session}.json"

    # Inside the try as well: enumeration reads the published parquet over the
    # network, and a session missing from it raised before any summary existed
    # -- the one hole in "a run always leaves a summary saying what happened".
    # Bound first so the handler can report it even when enumeration is what
    # failed.
    ld_numbers: list[str] = []
    try:
        ld_numbers = session_ld_numbers(args.parquet_source, args.session)
        summary = backfill(
            args.session,
            ld_numbers,
            out_path,
            args.delay,
            args.limit,
            recheck_missing=args.recheck_missing,
        )
    except BaseException as e:
        # Including KeyboardInterrupt and the job timeout's SIGTERM: an
        # interrupted run must still say it was interrupted. Without this the
        # artifact holds a partial actions table and no summary at all, which
        # is indistinguishable from a small complete session.
        write_json(
            summary_path,
            {
                "session": args.session,
                "lds_total": len(ld_numbers),
                "complete": False,
                "aborted": True,
                "error": f"{type(e).__name__}: {e}",
            },
        )
        raise

    write_json(summary_path, summary)

    # Exit non-zero on an incomplete run. Returning 0 unconditionally meant a
    # session that was blocked at request one produced a green check, an empty
    # artifact, and a summary nobody is obliged to read — indistinguishable
    # from a successful backfill.
    if not summary["complete"]:
        logger.error(
            f"Session {args.session} incomplete: {summary['failed']} failed, "
            f"{summary['not_attempted']} not attempted"
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
