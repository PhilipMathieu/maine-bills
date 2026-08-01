"""Upload a built `actions` config to HuggingFace (sprint node N3).

Takes what `build_actions_config.py` wrote and uploads it, then re-syncs the
dataset card so the new per-session configs are declared.

**This is the gated half.** It is the only script here that writes to the Hub,
so it runs exclusively inside the `huggingface-publish` environment, whose
required reviewer is the repo owner and whose secret is the only place HF_TOKEN
exists (docs/GOVERNANCE.md). Building is deliberately a separate, ungated step.

Re-validates before uploading rather than trusting the artifact. The build and
the publish are different jobs on different runners, and an artifact can arrive
truncated or partial; a session that fails validation here must not reach the
Hub, where correcting it means a visible bad revision rather than a red check.

Usage:
    uv run python scripts/publish_actions_config.py \\
        --input data/actions-parquet --repo-id pem207/maine-bills
"""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd  # noqa: E402

from maine_bills.actions_config import COLUMNS, ActionsConfigError  # noqa: E402
from maine_bills.publish import publish_actions_config, sync_dataset_card  # noqa: E402

logger = logging.getLogger("publish_actions_config")


def validate(parquet_dir: Path) -> list[int]:
    """Re-read every parquet and check it before anything is uploaded.

    Checks the whole set first, then uploads — so a bad session eleven files in
    does not leave the Hub holding ten uploaded ones.
    """
    sessions = sorted(int(d.name) for d in parquet_dir.iterdir() if d.is_dir() and d.name.isdigit())
    if not sessions:
        raise ActionsConfigError(f"No session directories under {parquet_dir}")

    for session in sessions:
        path = parquet_dir / str(session) / "train-00000-of-00001.parquet"
        if not path.exists():
            raise ActionsConfigError(f"{path} is missing; the build did not finish")

        frame = pd.read_parquet(path)
        if list(frame.columns) != COLUMNS:
            raise ActionsConfigError(
                f"{path}: columns {list(frame.columns)} do not match the published layout"
            )
        if frame.empty:
            raise ActionsConfigError(
                f"{path}: no rows. A Maine session has ~2,000 bills; zero means the build "
                f"produced an empty file."
            )
        if frame["ld_number"].duplicated().any():
            raise ActionsConfigError(f"{path}: duplicate ld_number would multiply rows on join")
        if set(frame["session"].unique()) != {session}:
            raise ActionsConfigError(
                f"{path}: holds sessions {sorted(frame['session'].unique())}, not {session}"
            )
        logger.info(
            f"Session {session}: {len(frame)} bills, {int(frame['action_count'].sum())} actions"
        )

    return sessions


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--input", type=Path, required=True, help="Directory of built parquet")
    parser.add_argument("--repo-id", required=True, help="HuggingFace dataset repo")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and report what would be uploaded, then stop without writing.",
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s:%(levelname)s:%(message)s")
    args = parse_args(argv)

    try:
        sessions = validate(args.input)
    except ActionsConfigError as e:
        logger.error(str(e))
        return 1

    if args.dry_run:
        logger.info(f"Dry run: would upload sessions {sessions} to {args.repo_id}")
        return 0

    publish_actions_config(args.input, args.repo_id)
    sync_dataset_card(args.repo_id)
    logger.info(f"Published {len(sessions)} actions sessions to {args.repo_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
