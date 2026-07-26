"""Enrich the published dataset with sponsor matches, in place.

Reads each session's parquet from HuggingFace (or a local dir), fills the v2
sponsor enrichment columns, and writes the result to a local directory for the
gated publish job to upload.

Enrichment needs no PDFs: `sponsors` is already published, and chamber hints
are derived from the published `text`, which retains the "Presented by Senator
X of Y" block. A full re-scrape of sessions 121-132 would mean ~43,000 PDF
downloads; this runs in minutes against the same data.

Two caveats, documented in the dataset card:

- `sponsors` was deduplicated by name when v1 was scraped, so a bill sponsored
  by two legislators sharing a surname in different chambers has one entry and
  takes that surname's first-mentioned chamber. Full fidelity arrives with the
  next scrape (see schema.py / text_extractor.py).
- Sessions differ widely in match rate; rates are reported per session so the
  card can state them honestly rather than averaging them away.

Usage:
    uv run python scripts/enrich_published.py \\
        --sessions 121 122 ... 132 \\
        --parquet-source hf://datasets/pem207/maine-bills \\
        --output data
"""

import argparse
import importlib.util
import json
import logging
import sys
from pathlib import Path

from maine_bills.enrichment import apply_enrichment  # noqa: F401  (contract reference)
from maine_bills.openstates import get_roster
from maine_bills.sponsor_matching import MATCHED_METHODS, SponsorMatcher

logger = logging.getLogger("enrich_published")

# Reuse the report script's loader and chamber derivation rather than
# duplicating them; it is a script, not a package module.
_REPORT = Path(__file__).with_name("run_matching_report.py")
_spec = importlib.util.spec_from_file_location("_matching_report", _REPORT)
_report = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_report)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sessions", type=int, nargs="+", required=True)
    parser.add_argument("--parquet-source", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, default=None)
    return parser.parse_args(argv)


def enrich_session(df, session: int, cache_dir: Path | None):
    """Fill the four enrichment columns plus sponsor_chambers for one session."""
    roster_kwargs = {"cache_dir": cache_dir} if cache_dir else {}
    matcher = SponsorMatcher(get_roster(session, **roster_kwargs))

    ids, parties, districts, confidences, chambers_col = [], [], [], [], []
    matched = total = 0

    for _, row in df.iterrows():
        raw = row.get("sponsors")
        sponsors = [] if raw is None else list(raw)
        chambers = _report.chambers_for_row(row, sponsors)
        results = matcher.match_all(sponsors, chambers=chambers)

        ids.append([r.openstates_id if r.method in MATCHED_METHODS else None for r in results])
        parties.append([r.party if r.method in MATCHED_METHODS else None for r in results])
        districts.append([r.district if r.method in MATCHED_METHODS else None for r in results])
        confidences.append([r.confidence if r.method in MATCHED_METHODS else None for r in results])
        chambers_col.append(chambers)
        total += len(sponsors)
        matched += sum(1 for r in results if r.method in MATCHED_METHODS)

    df = df.copy()
    df["sponsor_chambers"] = chambers_col
    df["sponsor_ids"] = ids
    df["sponsor_parties"] = parties
    df["sponsor_districts"] = districts
    df["sponsor_match_confidence"] = confidences
    rate = matched / total if total else 0.0
    logger.info(f"Session {session}: enriched {matched}/{total} sponsor mentions ({rate:.1%})")
    return df, {"session": session, "mentions": total, "matched": matched, "rate": round(rate, 4)}


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s:%(levelname)s:%(message)s")
    args = parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=True)

    summary = []
    for session in args.sessions:
        logger.info(f"=== Session {session} ===")
        df = _report.load_session_bills(args.parquet_source, session)
        enriched, stats = enrich_session(df, session, args.cache_dir)

        session_dir = args.output / str(session)
        session_dir.mkdir(parents=True, exist_ok=True)
        enriched.to_parquet(session_dir / "train-00000-of-00001.parquet", index=False)
        summary.append(stats)

    (args.output / "enrichment_summary.json").write_text(json.dumps(summary, indent=2))
    logger.info(f"Wrote {len(summary)} enriched sessions to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
