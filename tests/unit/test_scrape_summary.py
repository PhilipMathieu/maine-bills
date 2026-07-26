"""Unit tests for scripts/scrape_summary.py (CI job-summary generator)."""

import importlib.util
from pathlib import Path

import pandas as pd
import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "scrape_summary.py"

spec = importlib.util.spec_from_file_location("scrape_summary", SCRIPT_PATH)
scrape_summary = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scrape_summary)


def _write_session(data_dir: Path, session: int, rows: list[dict]) -> None:
    session_dir = data_dir / str(session)
    session_dir.mkdir(parents=True)
    pd.DataFrame(rows).to_parquet(session_dir / "train-00000-of-00001.parquet", index=False)


def _rows(*specs: tuple[str, str, str | None]) -> list[dict]:
    """Each spec is (source_filename, text, amendment_code)."""
    return [{"source_filename": f, "text": t, "amendment_code": a} for f, t, a in specs]


@pytest.fixture
def data_dir(tmp_path):
    d = tmp_path / "data"
    _write_session(
        d,
        132,
        _rows(
            ("132-LD-0001", "text one", None),
            ("132-LD-0002", "text two", None),
            ("132-LD-0002-CA_A_H0001", "amend text", "CA_A_H0001"),
        ),
    )
    return d


def test_counts_without_previous(data_dir):
    summary = scrape_summary.build_summary(data_dir, None)
    assert "| 132 | 3 | 2 | 1 |" in summary
    assert "Total: 3 records across 1 session(s)" in summary
    assert "No previous-run artifact" in summary


def test_diff_against_previous(data_dir, tmp_path):
    prev = tmp_path / "previous"
    _write_session(
        prev,
        132,
        _rows(
            ("132-LD-0001", "text one", None),  # unchanged
            ("132-LD-0002", "OLD text two", None),  # changed
            ("132-LD-9999", "gone", None),  # removed
        ),
    )
    summary = scrape_summary.build_summary(data_dir, prev)
    # new=1 (the amendment), removed=1 (LD-9999), changed=1 (LD-0002)
    assert "| 132 | 3 | 2 | 1 | 1 | 1 | 1 |" in summary


def test_empty_data_dir(tmp_path):
    summary = scrape_summary.build_summary(tmp_path / "nope", None)
    assert "scrape produced nothing" in summary


def test_previous_session_missing_shows_dashes(data_dir, tmp_path):
    prev = tmp_path / "previous"
    _write_session(prev, 131, _rows(("131-LD-0001", "x", None)))
    summary = scrape_summary.build_summary(data_dir, prev)
    assert "| 132 | 3 | 2 | 1 | - | - | - |" in summary
