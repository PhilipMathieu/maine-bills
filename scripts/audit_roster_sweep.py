"""Measure what the roster sweep contributes, and whether any of it is junk.

The sweep reads bare surnames out of a "Senators:" / "Representatives:" roster
in a cosponsor block. It is bounded by shape: a roster is a contiguous
comma-delimited run of ``NAME of LOCALITY`` cells, and the first cell that is
not one ends it.

Shape alone cannot tell a surname from an acronym -- "DHHS of Augusta" parses
exactly like "BAILEY of York". So the guard is not "can this be defeated by
constructed prose" (it can) but "does real bill text defeat it". That is an
empirical question about the corpus, and this script answers it.

Method: extract each session's sponsors twice, once with the sweep live and
once with it disabled, and diff. The difference is exactly what the sweep
contributed. Each contributed name is then matched against the OpenStates
roster for that session -- a real surname matches a sitting legislator, an
agency acronym does not -- and the unmatched names are printed in full so a
human can see what they are.

An unmatched name is not automatically a false positive: roster coverage for
sessions 121-124 is poor (issue #13), so an unmatched name there is more
likely a coverage gap than a bad extraction. Read the per-session split, not
the total.

Usage:
    uv run python scripts/audit_roster_sweep.py --sessions 131 132
"""

import argparse
import importlib.util
import json
import logging
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from maine_bills import text_extractor as tx  # noqa: E402
from maine_bills.openstates import get_roster  # noqa: E402
from maine_bills.sponsor_matching import METHOD_UNMATCHED, SponsorMatcher  # noqa: E402

logger = logging.getLogger("audit_roster_sweep")

# A pattern that cannot match, used to switch the sweep off for the control run.
_NEVER = re.compile(r"(?!x)x")


def load_session_bills(parquet_source: str, session: int):
    report_path = Path(__file__).with_name("run_matching_report.py")
    spec = importlib.util.spec_from_file_location("_matching_report", report_path)
    if spec is None or spec.loader is None:  # pragma: no cover - packaging error
        raise ImportError(f"Cannot load the parquet loader from {report_path}")
    report = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(report)
    return report.load_session_bills(parquet_source, session)


def sponsors_for(texts, sweep: bool) -> list[list[str]]:
    """Extract sponsors for every text, with the roster sweep on or off."""
    extractor = tx.TextExtractor()
    original = tx._ROSTER_SEGMENTS
    if not sweep:
        tx._ROSTER_SEGMENTS = _NEVER
    try:
        return [extractor._extract_sponsors(t if isinstance(t, str) else "") or [] for t in texts]
    finally:
        tx._ROSTER_SEGMENTS = original


def audit_session(parquet_source: str, session: int) -> dict:
    df = load_session_bills(parquet_source, session)
    texts = list(df["text"])

    with_sweep = sponsors_for(texts, sweep=True)
    without_sweep = sponsors_for(texts, sweep=False)

    contributed = Counter()
    bills_affected = 0
    for got, base in zip(with_sweep, without_sweep):
        extra = [n for n in got if n not in set(base)]
        if extra:
            bills_affected += 1
            contributed.update(extra)

    try:
        matcher = SponsorMatcher(roster=get_roster(session))
    except Exception as e:
        logger.warning(f"Session {session}: no roster ({type(e).__name__}: {e})")
        matcher = None

    unmatched = Counter()
    if matcher is not None:
        for name, count in contributed.items():
            if matcher.match(name).method == METHOD_UNMATCHED:
                unmatched[name] = count

    total = sum(contributed.values())
    return {
        "session": session,
        "bills": len(df),
        "bills_gaining_sponsors": bills_affected,
        "names_contributed": total,
        "distinct_names": len(contributed),
        "unmatched_distinct": len(unmatched),
        "unmatched_mentions": sum(unmatched.values()),
        "unmatched_rate": round(sum(unmatched.values()) / total, 4) if total else None,
        "roster_available": matcher is not None,
        # The whole point of the audit: a human reads these and decides whether
        # they are legislators the roster is missing, or junk. `all_names` is
        # what makes the audit useful without a roster at all -- an agency
        # acronym is obvious on sight next to a column of Maine surnames.
        "unmatched_names": [n for n, _c in unmatched.most_common()],
        "all_names": [[n, c] for n, c in contributed.most_common()],
        # Names seen once or twice in a whole session. A sitting legislator
        # cosponsors far more than that, so this tail is where a misparse
        # shows up -- and unlike the roster check it works for 121-124, where
        # OpenStates coverage is too poor to judge anything.
        "singleton_names": sorted(n for n, c in contributed.items() if c == 1),
        "rare_names": [f"{n}({c})" for n, c in contributed.most_common()[-25:]],
    }


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--sessions", type=int, nargs="+", required=True)
    p.add_argument("--parquet-source", default="hf://datasets/pem207/maine-bills")
    p.add_argument("--output", type=Path, default=Path("report/roster-sweep-audit.json"))
    return p.parse_args(argv)


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s:%(levelname)s:%(message)s")
    # One signed CDN URL per parquet range request, several per session, each
    # hundreds of characters. They bury the only output anyone reads.
    for noisy in ("httpx", "huggingface_hub", "urllib3", "filelock"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    args = parse_args(argv)

    results = []
    for session in args.sessions:
        logger.info(f"Auditing session {session}")
        result = audit_session(args.parquet_source, session)
        results.append(result)
        logger.info(
            f"  +{result['names_contributed']} names on "
            f"{result['bills_gaining_sponsors']} bills; "
            f"{result['unmatched_mentions']} unmatched "
            f"({result['unmatched_rate']})"
        )
        if result["unmatched_names"]:
            logger.info(f"  unmatched: {', '.join(result['unmatched_names'][:40])}")
        elif not result["roster_available"]:
            # No roster to check against, so the names themselves are the
            # finding -- print them rather than reporting a silent zero.
            logger.info(f"  names: {', '.join(n for n, _c in result['all_names'][:60])}")

        # The rare tail is where junk lives. A sitting legislator cosponsors
        # many bills a session; a misparse appears once or twice. This is the
        # roster-independent check, which matters because the OpenStates
        # rosters are poor for 121-124 and cannot be used to judge those.
        logger.info(
            f"  distinct={result['distinct_names']} (chamber has ~186 seats); "
            f"rarest: {result['rare_names']}"
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, indent=2))

    # Repeated at the end as a table: this is the finding, and scrolling back
    # through per-session logs to reassemble it is how it gets misread.
    logger.info("=" * 72)
    logger.info(
        f"{'session':>8} {'bills':>7} {'+names':>8} {'distinct':>9} {'unmatched':>10} {'rate':>7}"
    )
    for r in results:
        rate = "n/a" if r["unmatched_rate"] is None else f"{r['unmatched_rate']:.4f}"
        flag = "" if r["roster_available"] else "  (no roster)"
        logger.info(
            f"{r['session']:>8} {r['bills']:>7} {r['names_contributed']:>8} "
            f"{r['distinct_names']:>9} {r['unmatched_mentions']:>10} {rate:>7}{flag}"
        )
    total_unmatched = sum(r["unmatched_mentions"] for r in results)
    logger.info(f"Total unmatched across all sessions: {total_unmatched}")
    logger.info(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
