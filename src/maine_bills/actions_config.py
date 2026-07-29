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
import re
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


def _read_json(path: Path):
    """Parse an artifact, reporting a bad one as an ActionsConfigError.

    A truncated or half-written JSON file is one of the concrete things this
    module exists to catch, and letting json.JSONDecodeError escape meant
    catching it nowhere: the CLI only handles ActionsConfigError, so a
    truncated artifact produced a bare traceback instead of a message naming
    the file, and --no-strict could not skip past it to build the other
    eleven sessions.
    """
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as e:
        raise ActionsConfigError(
            f"{path}: not valid JSON ({e}). The artifact is truncated or was written "
            f"by a run that died mid-write; re-run the backfill for this session."
        ) from e
    except OSError as e:
        raise ActionsConfigError(f"{path}: cannot be read ({e})") from e


def load_backfill(path: Path) -> list[dict]:
    """Read one session's backfill output, refusing anything incomplete.

    The summary sitting beside the records is what makes this safe: a run that
    aborted or failed writes a summary saying so, and its partial actions table
    is shape-identical to a complete one. Publishing that would silently ship a
    session with bills missing and no way to tell from the data.
    """
    records = _read_json(path)
    if not isinstance(records, list):
        raise ActionsConfigError(f"{path}: expected a list of records")

    summary_path = path.with_name(path.name.replace("actions-", "summary-"))
    if not summary_path.exists():
        raise ActionsConfigError(
            f"{path}: no summary beside it ({summary_path.name}). A run always writes one, "
            f"even when it crashes, so its absence means this artifact is not from a "
            f"finished run."
        )

    summary = _read_json(summary_path)
    if not isinstance(summary, dict):
        raise ActionsConfigError(
            f"{summary_path}: expected an object, not {type(summary).__name__}"
        )

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


def session_of(path: Path) -> int | None:
    """The session number in an `actions-<n>.json` / `summary-<n>.json` name."""
    try:
        return int(path.stem.split("-")[-1])
    except ValueError:  # pragma: no cover - defensive
        return None


def is_complete(records_path: Path) -> bool:
    """Whether this artifact's summary reports a finished session."""
    summary_path = records_path.with_name(records_path.name.replace("actions-", "summary-"))
    if not summary_path.exists():
        return False
    try:
        return bool(json.loads(summary_path.read_text()).get("complete"))
    except (json.JSONDecodeError, TypeError, AttributeError, OSError):
        # A summary that cannot be read is not evidence of completeness. The
        # artifact still reaches load_backfill, which reports WHY.
        return False


def _natural_key(path: Path) -> tuple:
    """Sort key that orders embedded numbers numerically.

    Plain lexicographic ordering puts `run-9` after `run-10`, so "the later run
    wins" silently meant "the run whose id sorts last as text". Today's GitHub
    run ids are all the same width, which hides the bug — a local input
    directory numbered run-1..run-12 does not.
    """
    return tuple(
        (1, int(part), "") if part.isdigit() else (0, 0, part)
        for part in re.split(r"(\d+)", str(path))
    )


def resolve_sessions(input_dir: Path) -> dict[int, Path]:
    """One records file per session, choosing between duplicates.

    A session can appear more than once when artifacts come from several runs:
    session 126 failed in the first full backfill and was re-dispatched, so
    both runs carry an `actions-126` artifact. A complete copy always wins over
    an incomplete one — that is what re-running a session means. Between two
    equally complete copies the later run wins, ordered numerically on the run
    id in the path rather than as text.
    """
    candidates: dict[int, list[Path]] = {}
    for path in sorted(input_dir.rglob("actions-*.json"), key=_natural_key):
        session = session_of(path)
        if session is not None:
            candidates.setdefault(session, []).append(path)

    resolved = {}
    for session, paths in candidates.items():
        complete = [p for p in paths if is_complete(p)]
        resolved[session] = (complete or paths)[-1]
    return resolved


def orphan_summaries(input_dir: Path) -> list[int]:
    """Sessions with a summary but no records file ANYWHERE in the input.

    This is what a crashed run leaves behind: session 126 of the first full
    backfill died on a rate limit during enumeration and uploaded a summary
    with no `actions-126.json` beside it. Globbing for records alone would not
    find it, so the build would quietly produce eleven sessions and report
    success — the exact silent gap the completeness check exists to prevent,
    arriving through the one path that check cannot see.

    Scoped across the whole input rather than per-directory, because a session
    whose failed attempt is present alongside its successful re-run is not a
    gap; it is the re-run working as intended.
    """
    have_records = set(resolve_sessions(input_dir))
    missing = {
        session
        for summary_path in input_dir.rglob("summary-*.json")
        if (session := session_of(summary_path)) is not None and session not in have_records
    }
    return sorted(missing)


# Columns whose dtype is pinned rather than inferred. Applied to the empty
# frame too: pandas infers `object` for every column of an empty frame, so an
# empty session written to parquet would carry a different schema than every
# other session in the same config -- int64 vs object on the join key's
# neighbours is exactly the kind of drift a reader hits only at load time.
_DTYPES = {"session": "int64", "ld_number": "string", "action_count": "int64"}


def build_frame(records: list[dict]) -> pd.DataFrame:
    """One session's records as a DataFrame with the published column order."""
    if not records:
        empty = pd.DataFrame({name: pd.Series(dtype="object") for name in COLUMNS})
        return empty.astype(_DTYPES)

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

    return pd.DataFrame(rows, columns=COLUMNS).astype(_DTYPES)


def build_session(path: Path) -> pd.DataFrame:
    """Load and validate one session's backfill artifact into a frame.

    Never returns an empty frame. `build_frame([])` is a legitimate primitive
    -- it is what gives an empty frame the published dtypes -- but a *session*
    with no bills is not a small session, it is a broken run: enumeration reads
    the LD set from the published parquet, so zero records means enumeration
    came back empty and the backfill still declared itself complete. Publishing
    that is the silent gap the completeness check exists to prevent, reaching
    the same end by a different road.

    Refusing here also keeps the builder simple: it can read the session number
    off the frame without an empty-frame branch, and --no-strict downgrades
    this to a skip like any other per-session refusal.
    """
    frame = build_frame(load_backfill(path))

    if frame.empty:
        raise ActionsConfigError(
            f"{path}: complete but has no records. A Maine session has ~2,000 bills; "
            f"zero means enumeration returned nothing and the run finished anyway. "
            f"Re-run the backfill for this session."
        )

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
