"""The `actions` dataset config: legislative history, keyed to the bills table.

One row per bill, carrying the bill-level status fields and its committee
docket as a nested list. That shape rather than one-row-per-action because the
bill-level fields (committee, final disposition, chaptered law) belong to the
bill, not to any single docket row — a long table would repeat them on every
row and invite disagreement between copies. Consumers who want long format can
explode `actions` in one line; going the other way means a groupby and a
reconstruction.

**Join key.** `(session, ld_number)`, matching the bills config exactly.
`ld_number` is zero-padded there and here. Amendments in the bills table share
their parent's LD, so the join is one-to-many from this side: a bill's status
describes the bill, not each printed document.

Nulls are meaningful and are never filled in. A bill with no committee referral
has `committee = None`, which is different from a bill whose referral we failed
to parse — the latter does not exist, because a page that does not parse is
recorded as a failure and excluded rather than written as an empty row.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

# Column order for the published parquet. Explicit rather than derived from a
# dict, so adding a field to the backfill record cannot silently reorder or
# introduce a column in the published schema without this file changing too.
COLUMNS = [
    "session",
    "ld_number",
    "paper",
    "title",
    "flags",
    "committee",
    "referred_date",
    "final_disposition",
    "final_disposition_date",
    "governor_action",
    "governor_action_date",
    "chaptered_law",
    "actions",
    "action_count",
    "source_url",
]

# The nested action struct. Same reasoning as COLUMNS.
ACTION_FIELDS = ["date", "action", "result", "raw_date"]


class ActionsConfigError(ValueError):
    """A backfill artifact is not usable as a published config."""


def load_backfill(path: Path) -> list[dict]:
    """Read one session's backfill output, refusing anything incomplete.

    The summary sitting beside the records is what makes this safe: a run that
    aborted or failed writes a summary saying so, and its partial actions table
    is shape-identical to a complete one. Publishing that would silently ship a
    session with bills missing and no way to tell from the data.
    """
    records = json.loads(path.read_text())
    if not isinstance(records, list):
        raise ActionsConfigError(f"{path}: expected a list of records")

    summary_path = path.with_name(path.name.replace("actions-", "summary-"))
    if not summary_path.exists():
        raise ActionsConfigError(
            f"{path}: no summary beside it ({summary_path.name}). A run always writes one, "
            f"even when it crashes, so its absence means this artifact is not from a "
            f"finished run."
        )

    summary = json.loads(summary_path.read_text())
    if not summary.get("complete"):
        raise ActionsConfigError(
            f"{path}: session {summary.get('session')} is not complete "
            f"(aborted={summary.get('aborted')}, failed={summary.get('failed')}, "
            f"not_attempted={summary.get('not_attempted')}, "
            f"reason={summary.get('abort_reason')}). Re-run the backfill for it; "
            f"publishing a partial session is indistinguishable from a small one."
        )

    if len(records) != summary.get("records"):
        raise ActionsConfigError(
            f"{path}: {len(records)} records but the summary claims "
            f"{summary.get('records')}. The two were written by the same run, so a "
            f"disagreement means one of the files is truncated."
        )
    return records


def orphan_summaries(input_dir: Path) -> list[int]:
    """Sessions that have a summary but no records file.

    This is what a crashed run leaves behind: session 126 of the first full
    backfill died on a rate limit during enumeration and uploaded a summary
    with no `actions-126.json` beside it. Globbing for records alone would not
    find it, so the build would quietly produce eleven sessions and report
    success — the exact silent gap the completeness check exists to prevent,
    arriving through the one path that check cannot see.
    """
    missing = []
    for summary_path in input_dir.rglob("summary-*.json"):
        records_path = summary_path.with_name(summary_path.name.replace("summary-", "actions-"))
        if not records_path.exists():
            try:
                missing.append(int(summary_path.stem.split("-")[-1]))
            except ValueError:  # pragma: no cover - defensive
                continue
    return sorted(missing)


def build_frame(records: list[dict]) -> pd.DataFrame:
    """One session's records as a DataFrame with the published column order."""
    if not records:
        return pd.DataFrame({name: pd.Series(dtype="object") for name in COLUMNS})

    rows = []
    for record in records:
        missing = [c for c in COLUMNS if c not in record]
        if missing:
            raise ActionsConfigError(
                f"record {record.get('ld_number')!r} is missing {missing}; the backfill "
                f"and this config have drifted apart"
            )
        row = {c: record[c] for c in COLUMNS}
        # Normalize the nested structs so every row has identical keys in the
        # same order. Parquet infers the struct from the data, and a record
        # whose actions happen to omit a key would otherwise change the
        # published schema for the whole file.
        row["actions"] = [{f: a.get(f) for f in ACTION_FIELDS} for a in record["actions"]]
        rows.append(row)

    frame = pd.DataFrame(rows, columns=COLUMNS)
    frame["session"] = frame["session"].astype("int64")
    frame["ld_number"] = frame["ld_number"].astype("string")
    frame["action_count"] = frame["action_count"].astype("int64")
    return frame


def build_session(path: Path) -> pd.DataFrame:
    """Load and validate one session's backfill artifact into a frame."""
    frame = build_frame(load_backfill(path))

    if frame.empty:
        return frame

    sessions = frame["session"].unique()
    if len(sessions) != 1:
        raise ActionsConfigError(f"{path}: expected one session, found {sorted(sessions)}")

    duplicates = frame["ld_number"][frame["ld_number"].duplicated()].tolist()
    if duplicates:
        # The join key has to be unique on this side or a join silently
        # multiplies rows in the bills table.
        raise ActionsConfigError(f"{path}: duplicate ld_number values {duplicates[:10]}")

    if (frame["action_count"] != frame["actions"].map(len)).any():
        raise ActionsConfigError(f"{path}: action_count disagrees with the actions list")

    return frame
