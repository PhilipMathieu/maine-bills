#!/usr/bin/env python
"""Run sponsor matching against OpenStates rosters and write a review report.

CI-runnable: loads bill parquet files (local directory or HuggingFace Hub),
matches every extracted sponsor against the session's OpenStates roster, and
writes a markdown + JSON report with per-session match rates, full unmatched
and ambiguous name lists (with bill counts), and a random sample of fuzzy
matches for human review.

Usage:
    uv run python scripts/run_matching_report.py \\
        --sessions 121 122 ... 132 \\
        --parquet-source data \\
        --output reports/matching

    # From HuggingFace Hub (needs network):
    uv run python scripts/run_matching_report.py \\
        --sessions 132 \\
        --parquet-source hf://datasets/pem207/maine-bills \\
        --output reports/matching

Rosters come from the cache dir when present; otherwise they are fetched via
the OpenStates v3 API (if OPENSTATES_API_KEY is set) or the openstates/people
bulk data (default), then cached.
"""

import argparse
import json
import logging
import random
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from maine_bills.enrichment import as_aligned_list
from maine_bills.openstates import get_roster  # noqa: E402
from maine_bills.sponsor_matching import (  # noqa: E402
    DEFAULT_FUZZY_THRESHOLD,
    METHOD_AMBIGUOUS,
    METHOD_EXACT,
    METHOD_FUZZY,
    METHOD_OCR,
    METHOD_UNMATCHED,
    SponsorMatcher,
)
from maine_bills.text_extractor import TextExtractor

logger = logging.getLogger("run_matching_report")

METHODS = (METHOD_EXACT, METHOD_OCR, METHOD_FUZZY, METHOD_AMBIGUOUS, METHOD_UNMATCHED)
FUZZY_SAMPLE_SIZE = 30

# Column headings for the per-session table, keyed by method so adding a method
# cannot silently shift the columns out of alignment with the data rows.
_METHOD_HEADINGS = {
    METHOD_EXACT: "Exact",
    METHOD_OCR: "OCR",
    METHOD_FUZZY: "Fuzzy",
    METHOD_AMBIGUOUS: "Ambiguous",
    METHOD_UNMATCHED: "Unmatched",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sponsor -> OpenStates matching report")
    parser.add_argument(
        "--sessions",
        nargs="+",
        type=int,
        required=True,
        metavar="SESSION",
        help="Legislative session number(s) to analyze",
    )
    parser.add_argument(
        "--parquet-source",
        required=True,
        help=(
            "Local directory with per-session parquet (e.g., 'data', laid out as "
            "<dir>/<session>/*.parquet) or a HuggingFace dataset URL "
            "(e.g., 'hf://datasets/pem207/maine-bills', read as "
            "<url>/data/<session>/*.parquet)"
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Directory for the markdown + JSON report",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=Path("data/openstates_cache"),
        help="OpenStates roster cache directory (default: data/openstates_cache)",
    )
    parser.add_argument(
        "--fuzzy-threshold",
        type=float,
        default=DEFAULT_FUZZY_THRESHOLD,
        help=f"Minimum rapidfuzz score for a fuzzy match (default: {DEFAULT_FUZZY_THRESHOLD})",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=132,
        help="Random seed for the fuzzy-match sample (default: 132)",
    )
    return parser


def load_session_bills(parquet_source: str, session: int) -> pd.DataFrame:
    """Load one session's bill records from a local dir or hf:// dataset URL."""
    if parquet_source.startswith("hf://"):
        from huggingface_hub import HfFileSystem

        fs = HfFileSystem()
        pattern = f"{parquet_source.removeprefix('hf://')}/data/{session}/*.parquet"
        paths = [f"hf://{p}" for p in fs.glob(pattern)]
    else:
        paths = sorted(str(p) for p in Path(parquet_source).glob(f"{session}/*.parquet"))

    if not paths:
        raise FileNotFoundError(f"No parquet files for session {session} in {parquet_source}")

    return pd.concat([pd.read_parquet(p) for p in paths], ignore_index=True)


def chambers_for_row(row, sponsors: list[str]) -> list[str | None]:
    """Chamber hint per sponsor, aligned with ``sponsors``.

    Prefers the ``sponsor_chambers`` column when the data was extracted with
    chamber capture. Otherwise derives it from the bill ``text``, which retains
    the "Presented by Senator X of Y" block (text cleaning only strips line
    numbers and page furniture) — so published v1 data can be matched with
    hints without re-scraping any PDFs.

    Caveat for the derived path: v1 ``sponsors`` was deduplicated by name, so a
    bill sponsored by two legislators sharing a surname in different chambers
    has only one entry; it takes that surname's first-mentioned chamber.
    """
    stored = as_aligned_list(row.get("sponsor_chambers"))
    if stored is not None and len(stored) == len(sponsors):
        return stored

    text = row.get("text")
    if not isinstance(text, str) or not text:
        return [None] * len(sponsors)

    by_name: dict[str, str] = {}
    for name, chamber in TextExtractor._extract_sponsor_mentions(text):
        if chamber and name not in by_name:
            by_name[name] = chamber
    return [by_name.get(sponsor) for sponsor in sponsors]


def analyze_session(df: pd.DataFrame, matcher: SponsorMatcher, session: int) -> dict:
    """Match every sponsor mention in a session and aggregate statistics.

    Returns a dict with method counts/rates, unmatched and ambiguous names with
    bill counts, and the full list of fuzzy matches (for sampling).
    """
    method_counts = Counter()
    unmatched_bills: dict[str, set] = {}
    ambiguous_bills: dict[str, set] = {}
    fuzzy_matches = []

    for _, row in df.iterrows():
        # Parquet round-trips list columns as numpy arrays; normalize to list
        raw_sponsors = row.get("sponsors")
        sponsors = [] if raw_sponsors is None else list(raw_sponsors)
        bill_id = row.get("source_filename") or f"{session}-LD-{row.get('ld_number', '?')}"
        chambers = chambers_for_row(row, sponsors)
        for sponsor, result in zip(sponsors, matcher.match_all(sponsors, chambers=chambers)):
            method_counts[result.method] += 1
            if result.method == METHOD_UNMATCHED:
                unmatched_bills.setdefault(sponsor, set()).add(bill_id)
            elif result.method == METHOD_AMBIGUOUS:
                ambiguous_bills.setdefault(sponsor, set()).add(bill_id)
            elif result.method in (METHOD_FUZZY, METHOD_OCR):
                fuzzy_matches.append(
                    {
                        "session": session,
                        "bill_id": bill_id,
                        "sponsor": sponsor,
                        "canonical_name": result.canonical_name,
                        "openstates_id": result.openstates_id,
                        "confidence": result.confidence,
                        "method": result.method,
                    }
                )

    total = sum(method_counts.values())

    def name_list(bills_by_name: dict[str, set]) -> list[dict]:
        return sorted(
            ({"name": name, "bill_count": len(bills)} for name, bills in bills_by_name.items()),
            key=lambda item: (-item["bill_count"], item["name"]),
        )

    return {
        "session": session,
        "bills": len(df),
        "sponsor_mentions": total,
        "counts": {method: method_counts.get(method, 0) for method in METHODS},
        "rates": {
            method: round(method_counts.get(method, 0) / total, 4) if total else 0.0
            for method in METHODS
        },
        "unmatched": name_list(unmatched_bills),
        "ambiguous": name_list(ambiguous_bills),
        "fuzzy_matches": fuzzy_matches,
    }


def build_report(
    session_stats: list[dict], seed: int, sample_size: int = FUZZY_SAMPLE_SIZE
) -> dict:
    """Combine per-session stats into the final report structure."""
    all_fuzzy = [m for stats in session_stats for m in stats["fuzzy_matches"]]
    rng = random.Random(seed)
    sample = sorted(
        rng.sample(all_fuzzy, min(sample_size, len(all_fuzzy))),
        key=lambda m: (m["session"], m["bill_id"]),
    )
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "sessions": [
            {k: v for k, v in stats.items() if k != "fuzzy_matches"} for stats in session_stats
        ],
        "fuzzy_sample": sample,
    }


def render_markdown(report: dict) -> str:
    """Render the report as human-reviewable markdown."""
    lines = [
        "# Sponsor -> OpenStates Matching Report",
        "",
        f"Generated: {report['generated_at']}",
        "",
        "## Per-session match rates",
        "",
        # Derived from METHODS so a new match method can't silently shift columns
        "| Session | Bills | Mentions | " + " | ".join(_METHOD_HEADINGS[m] for m in METHODS) + " |",
        "|---------|-------|----------|" + "|".join(["-------"] * len(METHODS)) + "|",
    ]
    for stats in report["sessions"]:
        rates = stats["rates"]
        counts = stats["counts"]
        cells = " | ".join(f"{rates[m]:.1%} ({counts[m]})" for m in METHODS)
        lines.append(
            f"| {stats['session']} | {stats['bills']} | {stats['sponsor_mentions']} | {cells} |"
        )

    for stats in report["sessions"]:
        session = stats["session"]
        for kind in ("unmatched", "ambiguous"):
            names = stats[kind]
            lines += ["", f"## Session {session}: {kind} names ({len(names)})", ""]
            if not names:
                lines.append("_None._")
                continue
            lines += ["| Name | Bills |", "|------|-------|"]
            lines += [f"| {item['name']} | {item['bill_count']} |" for item in names]

    sample = report["fuzzy_sample"]
    lines += ["", f"## Fuzzy match sample for human review ({len(sample)})", ""]
    if not sample:
        lines.append("_No fuzzy matches._")
    else:
        lines += [
            "| Session | Bill | Extracted | Matched to | OpenStates ID | Confidence |",
            "|---------|------|-----------|------------|---------------|------------|",
        ]
        lines += [
            f"| {m['session']} | {m['bill_id']} | {m['sponsor']} | {m['canonical_name']} "
            f"| {m['openstates_id']} | {m['confidence']:.2f} |"
            for m in sample
        ]

    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s:%(levelname)s:%(message)s",
        stream=sys.stdout,
    )
    args = build_parser().parse_args(argv)

    session_stats = []
    for session in args.sessions:
        logger.info(f"=== Session {session} ===")
        roster = get_roster(session, cache_dir=args.cache_dir)
        if not roster:
            logger.warning(f"Empty roster for session {session}; skipping")
            continue
        matcher = SponsorMatcher(roster, fuzzy_threshold=args.fuzzy_threshold)
        df = load_session_bills(args.parquet_source, session)
        stats = analyze_session(df, matcher, session)
        logger.info(
            f"Session {session}: {stats['sponsor_mentions']} mentions, "
            f"exact {stats['rates'][METHOD_EXACT]:.1%}, "
            f"fuzzy {stats['rates'][METHOD_FUZZY]:.1%}, "
            f"ambiguous {stats['rates'][METHOD_AMBIGUOUS]:.1%}, "
            f"unmatched {stats['rates'][METHOD_UNMATCHED]:.1%}"
        )
        session_stats.append(stats)

    if not session_stats:
        logger.error("No sessions analyzed")
        return 1

    report = build_report(session_stats, seed=args.seed)
    args.output.mkdir(parents=True, exist_ok=True)
    json_path = args.output / "matching_report.json"
    md_path = args.output / "matching_report.md"
    with open(json_path, "w") as f:
        json.dump(report, f, indent=2)
    md_path.write_text(render_markdown(report))
    logger.info(f"Wrote {json_path} and {md_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
