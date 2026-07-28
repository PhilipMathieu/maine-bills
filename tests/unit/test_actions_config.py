"""Tests for the `actions` dataset config.

The record fixture below is the exact shape `backfill_bill_status.to_record`
writes — if the two drift apart, `build_frame` raises rather than publishing a
config with a missing column.
"""

import json

import pytest

from maine_bills.actions_config import (
    ACTION_FIELDS,
    COLUMNS,
    ActionsConfigError,
    build_frame,
    build_session,
    load_backfill,
)


def record(ld="0001", session=132, actions=None, **overrides):
    actions = (
        [{"date": "2025-01-15", "action": "Voted", "result": "OTP", "raw_date": "Jan 15, 2025"}]
        if actions is None
        else actions
    )
    base = {
        "session": session,
        "ld_number": ld,
        "paper": "SP 29",
        "title": "An Act To Do A Thing",
        "flags": ["EMERGENCY"],
        "committee": "Judiciary",
        "referred_date": "2025-01-10",
        "final_disposition": "PUBLIC LAW",
        "final_disposition_date": "2025-06-01",
        "governor_action": "Signed",
        "governor_action_date": "2025-06-05",
        "chaptered_law": "ACTPUB Chapter 33",
        "actions": actions,
        "action_count": len(actions),
        "source_url": "https://legislature.maine.gov/legis/bills/display_ps.asp?LD=1&snum=132",
    }
    base.update(overrides)
    return base


def write_session(tmp_path, session=132, records=None, summary=None):
    """Write an artifact pair the way a real backfill run does."""
    records = [record()] if records is None else records
    actions_path = tmp_path / f"actions-{session}.json"
    actions_path.write_text(json.dumps(records))
    full = {
        "session": session,
        "records": len(records),
        "complete": True,
        "aborted": False,
        "failed": 0,
        "not_attempted": 0,
        "abort_reason": None,
    }
    full.update(summary or {})
    (tmp_path / f"summary-{session}.json").write_text(json.dumps(full))
    return actions_path


# --- the contract with the backfill ---


def test_the_published_columns_match_what_the_backfill_writes(tmp_path):
    frame = build_session(write_session(tmp_path))
    assert list(frame.columns) == COLUMNS


def test_a_record_missing_a_column_is_refused_not_published(tmp_path):
    """If to_record and this config drift apart, the config must not quietly
    ship a column of nulls."""
    incomplete = record()
    del incomplete["chaptered_law"]
    path = write_session(tmp_path, records=[incomplete])
    with pytest.raises(ActionsConfigError, match="chaptered_law"):
        build_session(path)


def test_nested_actions_have_identical_keys_in_every_row(tmp_path):
    """Parquet infers the struct from the data, so a row whose action omits a
    key would change the published schema for the whole file."""
    sparse = record(ld="0002", actions=[{"action": "Filed"}])
    frame = build_session(write_session(tmp_path, records=[record(), sparse]))
    for row in frame["actions"]:
        for action in row:
            assert list(action.keys()) == ACTION_FIELDS


# --- the join key, which is the point of the config ---


def test_the_join_key_is_padded_the_way_the_bills_config_is(tmp_path):
    frame = build_session(write_session(tmp_path, records=[record(ld="0042")]))
    assert frame["ld_number"].iloc[0] == "0042"
    assert frame["ld_number"].dtype == "string"


def test_a_duplicate_ld_is_refused(tmp_path):
    """A repeated key silently multiplies rows when joined to the bills table."""
    path = write_session(tmp_path, records=[record(ld="0001"), record(ld="0001")])
    with pytest.raises(ActionsConfigError, match="duplicate"):
        build_session(path)


def test_a_mixed_session_artifact_is_refused(tmp_path):
    path = write_session(tmp_path, records=[record(session=132), record(ld="0002", session=131)])
    with pytest.raises(ActionsConfigError, match="one session"):
        build_session(path)


def test_action_count_must_agree_with_the_actions_list(tmp_path):
    path = write_session(tmp_path, records=[record(action_count=99)])
    with pytest.raises(ActionsConfigError, match="action_count"):
        build_session(path)


# --- refusing to publish a partial session, which is the real hazard ---


def test_an_incomplete_session_is_refused(tmp_path):
    """A partial actions table is shape-identical to a complete one for a
    smaller session. The summary is the only thing that can tell them apart."""
    path = write_session(tmp_path, summary={"complete": False, "failed": 7})
    with pytest.raises(ActionsConfigError, match="not complete"):
        build_session(path)


def test_an_aborted_session_is_refused(tmp_path):
    path = write_session(
        tmp_path,
        summary={"complete": False, "aborted": True, "abort_reason": "10 consecutive failures"},
    )
    with pytest.raises(ActionsConfigError, match="10 consecutive failures"):
        build_session(path)


def test_an_artifact_with_no_summary_is_refused(tmp_path):
    """Every run writes a summary, even when it crashes — so its absence means
    this did not come from a finished run at all."""
    path = tmp_path / "actions-132.json"
    path.write_text(json.dumps([record()]))
    with pytest.raises(ActionsConfigError, match="no summary"):
        build_session(path)


def test_a_truncated_records_file_is_caught_by_the_summary(tmp_path):
    """Both files come from the same run, so a count disagreement means one of
    them is truncated."""
    path = write_session(tmp_path, records=[record()], summary={"records": 2041})
    with pytest.raises(ActionsConfigError, match="truncated"):
        build_session(path)


# --- shapes that are legitimate and must survive ---


def test_a_bill_with_no_docket_is_a_valid_row(tmp_path):
    frame = build_session(write_session(tmp_path, records=[record(actions=[], action_count=0)]))
    assert len(frame) == 1
    assert frame["action_count"].iloc[0] == 0


def test_nulls_are_preserved_rather_than_filled(tmp_path):
    """A bill with no committee referral is different from one we failed to
    parse; the latter never reaches here."""
    sparse = record(committee=None, chaptered_law=None, governor_action=None)
    frame = build_session(write_session(tmp_path, records=[sparse]))
    assert frame["committee"].iloc[0] is None
    assert frame["chaptered_law"].iloc[0] is None


def test_an_empty_session_still_has_the_published_columns(tmp_path):
    frame = build_session(write_session(tmp_path, records=[], summary={"records": 0}))
    assert list(frame.columns) == COLUMNS
    assert frame.empty


def test_load_backfill_rejects_a_non_list(tmp_path):
    (tmp_path / "actions-132.json").write_text(json.dumps({"not": "a list"}))
    (tmp_path / "summary-132.json").write_text(json.dumps({"complete": True, "records": 0}))
    with pytest.raises(ActionsConfigError, match="list of records"):
        load_backfill(tmp_path / "actions-132.json")


def test_build_frame_on_no_records_is_not_an_error():
    assert build_frame([]).empty
