"""Write a Markdown summary of a scrape run (for $GITHUB_STEP_SUMMARY).

Reads parquet files laid out as <data_dir>/<session>/*.parquet, prints per-
session record counts, and -- if a previous run's artifact is available under
--previous-dir -- a cheap diff (new / removed / changed documents keyed by
source_filename, changed = same filename with different text).

Usage:
    uv run python scripts/scrape_summary.py --data-dir data --previous-dir previous
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd


def load_session_frames(data_dir: Path) -> dict[int, pd.DataFrame]:
    """Map session number -> DataFrame for every <data_dir>/<session>/*.parquet."""
    frames: dict[int, pd.DataFrame] = {}
    if not data_dir.is_dir():
        return frames
    for session_dir in sorted(data_dir.iterdir()):
        if not (session_dir.is_dir() and session_dir.name.isdigit()):
            continue
        parts = sorted(session_dir.glob("*.parquet"))
        if parts:
            frames[int(session_dir.name)] = pd.concat(
                [pd.read_parquet(p) for p in parts], ignore_index=True
            )
    return frames


def diff_counts(current: pd.DataFrame, previous: pd.DataFrame) -> tuple[int, int, int]:
    """Return (new, removed, changed) document counts keyed by source_filename."""
    cur = current.set_index("source_filename")["text"]
    prev = previous.set_index("source_filename")["text"]
    new = len(cur.index.difference(prev.index))
    removed = len(prev.index.difference(cur.index))
    common = cur.index.intersection(prev.index)
    changed = int((cur.loc[common] != prev.loc[common]).sum())
    return new, removed, changed


def build_summary(data_dir: Path, previous_dir: Path | None) -> str:
    """Build the Markdown job summary."""
    current = load_session_frames(data_dir)
    previous = load_session_frames(previous_dir) if previous_dir else {}

    lines = ["## Scrape summary", ""]
    if not current:
        lines.append(f"No parquet files found under `{data_dir}` -- scrape produced nothing.")
        return "\n".join(lines) + "\n"

    have_diff = bool(previous)
    if have_diff:
        lines.append("| Session | Records | Originals | Amendments | New | Removed | Changed |")
        lines.append("|---|---|---|---|---|---|---|")
    else:
        lines.append("| Session | Records | Originals | Amendments |")
        lines.append("|---|---|---|---|")

    total = 0
    for session, df in sorted(current.items()):
        total += len(df)
        amendments = int(df["amendment_code"].notna().sum())
        originals = len(df) - amendments
        row = f"| {session} | {len(df)} | {originals} | {amendments} |"
        if have_diff:
            if session in previous:
                new, removed, changed = diff_counts(df, previous[session])
                row += f" {new} | {removed} | {changed} |"
            else:
                row += " - | - | - |"
        lines.append(row)

    lines.append("")
    lines.append(f"**Total: {total} records across {len(current)} session(s).**")
    if not have_diff:
        lines.append("")
        lines.append("_No previous-run artifact available; skipping new/changed diff._")
    lines.append("")
    lines.append(
        "Parquet uploaded as the `scraped-parquet` artifact. Publishing to "
        "HuggingFace requires approval on the `huggingface-publish` environment."
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument(
        "--previous-dir",
        type=Path,
        default=None,
        help="Previous run's artifact dir (optional; diff is skipped if missing)",
    )
    args = parser.parse_args()

    previous_dir = args.previous_dir if args.previous_dir and args.previous_dir.is_dir() else None
    print(build_summary(args.data_dir, previous_dir))
    return 0


if __name__ == "__main__":
    sys.exit(main())
