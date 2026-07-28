"""Tests for the actions-config builder script."""

import importlib.util
import json
from pathlib import Path

import pandas as pd
import pytest

from maine_bills.actions_config import ActionsConfigError

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "build_actions_config.py"


@pytest.fixture(scope="module")
def build_mod():
    spec = importlib.util.spec_from_file_location("build_actions_config", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def artifact(directory: Path, session: int, n: int = 2, complete: bool = True, nested=False):
    """Write one session's artifact pair, optionally in a per-artifact subdir."""
    target = directory / f"actions-{session}" if nested else directory
    target.mkdir(parents=True, exist_ok=True)
    records = [
        {
            "session": session,
            "ld_number": f"{i:04d}",
            "paper": f"SP {i}",
            "title": "An Act",
            "flags": [],
            "committee": "Judiciary",
            "referred_date": None,
            "final_disposition": None,
            "final_disposition_date": None,
            "governor_action": None,
            "governor_action_date": None,
            "chaptered_law": None,
            "actions": [
                {"date": "2025-01-15", "action": "Voted", "result": "OTP", "raw_date": "Jan 15"}
            ],
            "action_count": 1,
            "source_url": "https://legislature.maine.gov/x",
        }
        for i in range(1, n + 1)
    ]
    (target / f"actions-{session}.json").write_text(json.dumps(records))
    (target / f"summary-{session}.json").write_text(
        json.dumps(
            {"session": session, "records": n, "complete": complete, "aborted": not complete}
        )
    )


def test_it_writes_one_parquet_per_session_laid_out_like_the_bills_config(build_mod, tmp_path):
    src, out = tmp_path / "in", tmp_path / "out"
    artifact(src, 131, n=3)
    artifact(src, 132, n=2)

    summary = build_mod.build(src, out)

    assert summary["sessions_built"] == 2
    assert summary["rows"] == 5
    assert summary["actions"] == 5
    for session, rows in ((131, 3), (132, 2)):
        path = out / str(session) / "train-00000-of-00001.parquet"
        assert path.exists()
        assert len(pd.read_parquet(path)) == rows


def test_the_parquet_round_trips_the_nested_actions(build_mod, tmp_path):
    src, out = tmp_path / "in", tmp_path / "out"
    artifact(src, 132, n=1)
    build_mod.build(src, out)

    frame = pd.read_parquet(out / "132" / "train-00000-of-00001.parquet")
    actions = list(frame["actions"].iloc[0])
    assert len(actions) == 1
    assert actions[0]["action"] == "Voted"
    assert actions[0]["date"] == "2025-01-15"


def test_artifacts_are_found_in_per_artifact_subdirectories(build_mod, tmp_path):
    """Downloading N artifacts from a run nests each one in its own directory."""
    src, out = tmp_path / "in", tmp_path / "out"
    artifact(src, 131, nested=True)
    artifact(src, 132, nested=True)
    assert build_mod.build(src, out)["sessions_built"] == 2


def test_an_incomplete_session_stops_the_build_by_default(build_mod, tmp_path):
    src, out = tmp_path / "in", tmp_path / "out"
    artifact(src, 131)
    artifact(src, 132, complete=False)
    with pytest.raises(ActionsConfigError, match="not complete"):
        build_mod.build(src, out)


def test_no_strict_skips_the_bad_session_and_reports_it(build_mod, tmp_path):
    src, out = tmp_path / "in", tmp_path / "out"
    artifact(src, 131)
    artifact(src, 132, complete=False)

    summary = build_mod.build(src, out, strict=False)
    assert summary["sessions_built"] == 1
    assert summary["sessions_skipped"] == ["actions-132.json"]
    assert not (out / "132").exists()


def test_skipping_a_session_still_exits_non_zero(build_mod, tmp_path, monkeypatch):
    """Otherwise --no-strict is a green build that quietly shipped a gap."""
    src, out = tmp_path / "in", tmp_path / "out"
    artifact(src, 131)
    artifact(src, 132, complete=False)
    code = build_mod.main(["--input", str(src), "--output", str(out), "--no-strict"])
    assert code == 1
    assert json.loads((out / "build-summary.json").read_text())["sessions_skipped"]


def test_an_empty_input_directory_is_an_error_not_an_empty_config(build_mod, tmp_path):
    src = tmp_path / "in"
    src.mkdir()
    with pytest.raises(ActionsConfigError, match="No actions"):
        build_mod.build(src, tmp_path / "out")


def test_main_returns_zero_and_writes_a_summary_on_a_clean_build(build_mod, tmp_path):
    src, out = tmp_path / "in", tmp_path / "out"
    artifact(src, 132, n=4)
    assert build_mod.main(["--input", str(src), "--output", str(out)]) == 0
    summary = json.loads((out / "build-summary.json").read_text())
    assert summary["per_session"] == [{"session": 132, "rows": 4, "actions": 4}]


def test_a_summary_with_no_records_is_caught_not_silently_skipped(build_mod, tmp_path):
    """Session 126 of the first full backfill: it crashed during enumeration and
    uploaded a summary with no actions file. Globbing for records alone cannot
    see that, so the build would quietly produce one session fewer and report
    success — the same silent gap the completeness check exists to prevent,
    arriving by the one route that check cannot cover."""
    src, out = tmp_path / "in", tmp_path / "out"
    artifact(src, 131)
    (src / "summary-126.json").write_text(
        json.dumps({"session": 126, "complete": False, "aborted": True, "error": "HfHubHTTPError"})
    )
    with pytest.raises(ActionsConfigError, match="126"):
        build_mod.build(src, out)


def test_an_orphan_summary_is_reported_under_no_strict(build_mod, tmp_path):
    src, out = tmp_path / "in", tmp_path / "out"
    artifact(src, 131)
    (src / "summary-126.json").write_text(json.dumps({"session": 126, "complete": False}))

    summary = build_mod.build(src, out, strict=False)
    assert summary["sessions_built"] == 1
    assert "session-126" in summary["sessions_skipped"]


def test_orphan_detection_finds_nested_artifacts_too(build_mod, tmp_path):
    src, out = tmp_path / "in", tmp_path / "out"
    artifact(src, 131, nested=True)
    (src / "actions-126").mkdir(parents=True)
    (src / "actions-126" / "summary-126.json").write_text(json.dumps({"session": 126}))
    with pytest.raises(ActionsConfigError, match="126"):
        build_mod.build(src, out)


def test_a_re_dispatched_session_supersedes_its_failed_attempt(build_mod, tmp_path):
    """Session 126 failed in the first full backfill and was re-run, so
    `actions-126` exists on two runs. The complete copy has to win, and the
    failed one must not register as a gap."""
    src, out = tmp_path / "in", tmp_path / "out"
    failed_run, good_run = src / "run-1" / "actions-126", src / "run-2" / "actions-126"
    failed_run.mkdir(parents=True)
    (failed_run / "summary-126.json").write_text(
        json.dumps({"session": 126, "complete": False, "aborted": True})
    )
    good_run.mkdir(parents=True)
    artifact(good_run, 126, n=3)
    # The good copy is written flat inside its own directory by `artifact`.

    summary = build_mod.build(src, out)
    assert summary["sessions_built"] == 1
    assert summary["rows"] == 3
    assert summary["sessions_skipped"] == []


def test_the_complete_copy_wins_regardless_of_directory_order(build_mod, tmp_path):
    """Even when the incomplete copy sorts last."""
    src, out = tmp_path / "in", tmp_path / "out"
    good, bad = src / "run-a", src / "run-z"
    good.mkdir(parents=True)
    bad.mkdir(parents=True)
    artifact(good, 131, n=5)
    artifact(bad, 131, n=1, complete=False)

    summary = build_mod.build(src, out)
    assert summary["per_session"] == [{"session": 131, "rows": 5, "actions": 5}]


def test_a_session_failed_on_every_run_is_still_a_gap(build_mod, tmp_path):
    src, out = tmp_path / "in", tmp_path / "out"
    for run in ("run-1", "run-2"):
        d = src / run
        d.mkdir(parents=True)
        (d / "summary-126.json").write_text(json.dumps({"session": 126, "complete": False}))
    artifact(src / "run-1", 131)
    with pytest.raises(ActionsConfigError, match="126"):
        build_mod.build(src, out)
