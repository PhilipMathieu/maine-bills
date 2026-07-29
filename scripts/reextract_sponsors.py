"""Re-extract `sponsors` from the published `text` column (issue #13, item 1).

**Why this exists.** The published dataset is internally inconsistent. Sessions
were scraped at different times against different extractors, and two fixes
since then changed what the extractor finds:

- #16 restored the plural-roster sweep that `300cd207` removed. Session 131 was
  scraped before that removal and carries full cosponsor lists; 132 was scraped
  after and does not. A bill with 99 cosponsors stored 2.
- #24 recovered two surname forms and, through the cascade, everything printed
  behind them.

So a cross-session analysis of `sponsors` today is measuring scrape dates as
much as it is measuring the legislature, and the Gate A match rates in issue #13
cannot be compared across sessions until this is fixed.

**Why not a re-scrape.** The sponsor block survives into the published `text`,
so the current extractor can be re-run against it: ~43,000 PDF downloads
avoided, and the result is identical because `text` is the same string the
extractor saw the first time. Verified while measuring #24, which reproduced
that PR's figures exactly from this column.

**What this does NOT do.** It does not upload. It writes parquet locally and
reports what changed; publishing is Tier-1 and goes through the
`huggingface-publish` gate.

Usage:
    uv run python scripts/reextract_sponsors.py \\
        --sessions 121 122 ... 132 \\
        --parquet-source hf://datasets/pem207/maine-bills \\
        --output data/reextracted
"""

import argparse
import json
import logging
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd  # noqa: E402

from maine_bills.text_extractor import TextExtractor  # noqa: E402

logger = logging.getLogger("reextract_sponsors")

# Published layout. The `data/` segment is not optional -- reading
# `<source>/<session>/...` without it silently 404s on the real repo.
PARQUET_TEMPLATE = "{source}/data/{session}/train-00000-of-00001.parquet"


def reextract_row(text) -> tuple[list[str], list[str | None]]:
    """Sponsors and their chambers for one row, from its published text."""
    if not isinstance(text, str) or not text:
        return [], []
    mentions = TextExtractor._extract_sponsor_mentions(text)
    return [name for name, _ in mentions], [chamber for _, chamber in mentions]


def compare(published, extracted) -> tuple[Counter, Counter]:
    """Multiset difference both ways, so a count change is not read as a swap."""
    was = Counter(published or [])
    now = Counter(extracted or [])
    return now - was, was - now


def reextract_session(df: pd.DataFrame, session: int) -> tuple[pd.DataFrame, dict]:
    """Rebuild `sponsors`/`sponsor_chambers` and report what moved.

    The enrichment columns are NOT recomputed here. They are index-aligned with
    `sponsors`, so rewriting that list leaves them pointing at the wrong
    entries -- they are cleared, and re-running enrich_published.py is a
    required second step rather than an optional one.
    """
    out = df.copy()
    gained, lost = Counter(), Counter()
    changed = before = after = 0
    new_sponsors, new_chambers = [], []

    for row in df.itertuples():
        published = list(row.sponsors) if row.sponsors is not None else []
        names, chambers = reextract_row(row.text)
        new_sponsors.append(names)
        new_chambers.append(chambers)

        before += len(published)
        after += len(names)
        up, down = compare(published, names)
        if up or down:
            changed += 1
            gained.update(up)
            lost.update(down)

    out["sponsors"] = new_sponsors
    out["sponsor_chambers"] = new_chambers
    # Created unconditionally, not only when the source already had them: a
    # v1-era parquet without the enrichment columns would otherwise produce
    # output missing them, breaking the "written in the published layout"
    # contract and leaving enrich_published.py to discover the gap later.
    for column in (
        "sponsor_ids",
        "sponsor_parties",
        "sponsor_districts",
        "sponsor_match_confidence",
    ):
        out[column] = [[None] * len(n) for n in new_sponsors]

    summary = {
        "session": session,
        "rows": len(df),
        "rows_changed": changed,
        "mentions_before": before,
        "mentions_after": after,
        "mentions_delta": after - before,
        "distinct_gained": len(gained),
        "distinct_lost": len(lost),
        "top_gained": gained.most_common(10),
        "top_lost": lost.most_common(10),
    }
    return out, summary


def load_session(source: str, session: int) -> pd.DataFrame:
    return pd.read_parquet(PARQUET_TEMPLATE.format(source=source.rstrip("/"), session=session))


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sessions", type=int, nargs="+", required=True)
    parser.add_argument("--parquet-source", default="hf://datasets/pem207/maine-bills")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Measure and report without writing parquet. Use this first — the "
        "point of the exercise is the size of the drift, not the files.",
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s:%(levelname)s:%(message)s")
    args = parse_args(argv)

    summaries = []
    for session in args.sessions:
        try:
            df = load_session(args.parquet_source, session)
        except Exception as e:
            logger.error(f"Session {session}: {type(e).__name__}: {e}")
            return 1

        frame, summary = reextract_session(df, session)
        summaries.append(summary)
        logger.info(
            f"Session {session}: {summary['rows']} rows | {summary['rows_changed']} changed | "
            f"{summary['mentions_before']} -> {summary['mentions_after']} "
            f"({summary['mentions_delta']:+d}) | +{summary['distinct_gained']} "
            f"-{summary['distinct_lost']} distinct"
        )

        if not args.report_only:
            session_dir = args.output / str(session)
            session_dir.mkdir(parents=True, exist_ok=True)
            frame.to_parquet(session_dir / "train-00000-of-00001.parquet", index=False)

    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "reextract-summary.json").write_text(json.dumps(summaries, indent=2))

    total_before = sum(s["mentions_before"] for s in summaries)
    total_after = sum(s["mentions_after"] for s in summaries)
    # Summed per session, so a name lost in two sessions counts twice. That is
    # the right unit for this warning -- each session is inspected and published
    # separately -- but it must not be labelled "distinct names", which review
    # of an earlier report read as a cross-session union and had to correct.
    loss_events = sum(s["distinct_lost"] for s in summaries)
    logger.info(
        f"TOTAL: {sum(s['rows_changed'] for s in summaries)} rows changed, "
        f"{total_before} -> {total_after} mentions ({total_after - total_before:+d})"
    )
    if loss_events:
        # Losing names is not automatically wrong -- the old extractor captured
        # things that were not people -- but it is never routine, and a silent
        # loss is how a regression ships.
        logger.warning(
            f"{loss_events} per-session distinct-name losses; "
            f"inspect each session's top_lost before publishing"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
