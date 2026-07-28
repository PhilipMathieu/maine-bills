"""Turn backfill artifacts into the published `actions` config (sprint node N3).

Reads the per-session JSON the backfill wrote (`actions-<session>.json` beside
`summary-<session>.json`) and writes one parquet per session, laid out the same
way the bills config is: `<out>/<session>/train-00000-of-00001.parquet`.

Refuses to build a session whose summary does not say `complete`. A partial
actions table looks exactly like a complete one for a smaller session, so the
summary is the only thing that can tell them apart — see actions_config.py.

Publishing is deliberately NOT part of this. It writes parquet locally and
stops; uploading is Tier-1 and goes through the `huggingface-publish` gate.

Usage:
    uv run python scripts/build_actions_config.py \\
        --input data/actions --output data/actions-parquet
"""

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from maine_bills.actions_config import (  # noqa: E402
    ActionsConfigError,
    build_session,
    orphan_summaries,
    resolve_sessions,
)

logger = logging.getLogger("build_actions_config")


def session_artifacts(input_dir: Path) -> list[Path]:
    """One records file per session, in session order.

    Searched recursively: artifacts from a workflow run arrive nested, a local
    run writes them flat, and several runs are downloaded into per-run
    directories. Duplicates across runs are resolved by resolve_sessions --
    a complete copy beats an incomplete one.
    """
    resolved = resolve_sessions(input_dir)
    return [resolved[session] for session in sorted(resolved)]


def build(input_dir: Path, output_dir: Path, strict: bool = True) -> dict:
    """Build every session found. Returns a summary of what was written."""
    artifacts = session_artifacts(input_dir)
    if not artifacts:
        raise ActionsConfigError(f"No actions-*.json under {input_dir}")

    # A crashed run uploads a summary with no records beside it. Globbing for
    # records alone cannot see that, so the build would silently produce one
    # session fewer and report success.
    orphans = orphan_summaries(input_dir)
    if orphans:
        message = (
            f"Sessions {orphans} have a summary but no records — their runs did not get "
            f"far enough to write one. Re-run the backfill for them before building."
        )
        if strict:
            raise ActionsConfigError(message)
        logger.error(message)
        skipped_orphans = [f"session-{s}" for s in orphans]
    else:
        skipped_orphans = []

    built, skipped, total_rows, total_actions = [], list(skipped_orphans), 0, 0
    for path in artifacts:
        try:
            frame = build_session(path)
        except ActionsConfigError as e:
            if strict:
                raise
            # --no-strict exists so an operator can publish the sessions that
            # are ready while one is re-running, rather than being blocked on
            # all-or-nothing. It is not the default, because the failure mode
            # it enables -- shipping eleven sessions and forgetting the
            # twelfth -- is quiet.
            logger.error(f"Skipping {path.name}: {e}")
            skipped.append(path.name)
            continue

        session = int(frame["session"].iloc[0])
        session_dir = output_dir / str(session)
        session_dir.mkdir(parents=True, exist_ok=True)
        out_path = session_dir / "train-00000-of-00001.parquet"
        frame.to_parquet(out_path, index=False)

        rows, actions = len(frame), int(frame["action_count"].sum())
        total_rows += rows
        total_actions += actions
        built.append({"session": session, "rows": rows, "actions": actions})
        logger.info(f"Session {session}: {rows} bills, {actions} actions -> {out_path}")

    return {
        "sessions_built": len(built),
        "sessions_skipped": skipped,
        "rows": total_rows,
        "actions": total_actions,
        "per_session": built,
    }


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--input", type=Path, required=True, help="Directory holding the backfill artifacts"
    )
    parser.add_argument("--output", type=Path, required=True, help="Where to write the parquet")
    parser.add_argument(
        "--no-strict",
        dest="strict",
        action="store_false",
        help="Skip sessions that are incomplete rather than failing. Off by default: "
        "publishing eleven of twelve sessions is a quiet way to ship a gap.",
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s:%(levelname)s:%(message)s")
    args = parse_args(argv)

    try:
        summary = build(args.input, args.output, strict=args.strict)
    except ActionsConfigError as e:
        logger.error(str(e))
        return 1

    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "build-summary.json").write_text(json.dumps(summary, indent=2))
    logger.info(
        f"Built {summary['sessions_built']} sessions, "
        f"{summary['rows']} bills, {summary['actions']} actions"
    )
    if summary["sessions_skipped"]:
        logger.warning(f"Skipped: {', '.join(summary['sessions_skipped'])}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
