"""Publish previously scraped parquet files to HuggingFace Hub.

Used by the human-gated `publish` job in scraper-uv.yml: the scrape job writes
<data_dir>/<session>/*.parquet and uploads it as an artifact; after a reviewer
approves the `huggingface-publish` environment, this script uploads exactly
those files (no re-scrape between review and publish).

Requires HF_TOKEN in the environment (huggingface_hub picks it up).

Usage:
    uv run python scripts/publish_from_artifact.py --data-dir data
    uv run python scripts/publish_from_artifact.py --data-dir data --sessions 131 132
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

from maine_bills.publish import publish_session, sync_dataset_card


def discover_sessions(data_dir: Path) -> list[int]:
    """Find session numbers with parquet files under <data_dir>/<session>/."""
    return sorted(
        int(d.name)
        for d in data_dir.iterdir()
        if d.is_dir() and d.name.isdigit() and any(d.glob("*.parquet"))
    )


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s:%(levelname)s:%(message)s",
        stream=sys.stdout,
    )
    logger = logging.getLogger("publish_from_artifact")

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument(
        "--repo-id",
        default="pem207/maine-bills",
        help="HuggingFace dataset repo ID (default: pem207/maine-bills)",
    )
    parser.add_argument(
        "--sessions",
        nargs="+",
        type=int,
        default=None,
        metavar="SESSION",
        help="Sessions to publish (default: every session dir found in --data-dir)",
    )
    args = parser.parse_args()

    if not args.data_dir.is_dir():
        logger.error(f"Data dir not found: {args.data_dir}")
        return 1

    sessions = args.sessions or discover_sessions(args.data_dir)
    if not sessions:
        logger.error(f"No session parquet files found under {args.data_dir}")
        return 1

    try:
        for session in sessions:
            parts = sorted((args.data_dir / str(session)).glob("*.parquet"))
            if not parts:
                logger.error(f"No parquet files for session {session}; aborting")
                return 1
            df = pd.concat([pd.read_parquet(p) for p in parts], ignore_index=True)
            logger.info(f"Publishing session {session}: {len(df)} records")
            publish_session(df, session, args.repo_id, args.data_dir)

        sync_dataset_card(args.repo_id)
        return 0
    except Exception as e:
        logger.error(f"Publish failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
