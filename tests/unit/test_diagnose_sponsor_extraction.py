"""Tests for the sponsor-extraction diagnostic (issue #13 item 4)."""

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "diagnose_sponsor_extraction.py"


@pytest.fixture(scope="module")
def diag():
    spec = importlib.util.spec_from_file_location("diagnose_sponsor_extraction", SCRIPT)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load {SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SPONSOR_BLOCK = (
    "STATE OF MAINE\n"
    "IN THE YEAR OF OUR LORD\n"
    "An Act To Do Something\n"
    "Presented by Senator DAUGHTRY of Cumberland.\n"
    "Cosponsored by Representative PERRY of Calais.\n"
)


def _row(filename, sponsors, text, amendment_code=None):
    return {
        "source_filename": filename,
        "sponsors": sponsors,
        "text": text,
        "amendment_code": amendment_code,
    }


# --- sponsor_count ---


@pytest.mark.parametrize(
    "value,expected",
    [
        (None, 0),
        (float("nan"), 0),
        (np.nan, 0),
        (pd.NA, 0),  # not a float, so an isinstance(value, float) guard misses it
        (np.array(["A", "B"], dtype=object), 2),  # list columns round-trip as ndarrays
        ("DAUGHTRY", 0),  # a bare string must not be exploded into characters
        ([], 0),
        (["A", "B"], 2),
    ],
)
def test_sponsor_count_tolerates_null_forms(diag, value, expected):
    assert diag.sponsor_count(value) == expected


def test_null_sponsors_do_not_crash_a_real_frame(diag):
    """Regression: a session slice with null sponsor cells must still summarize."""
    df = pd.DataFrame(
        [
            _row("a", ["X"], "t"),
            _row("b", None, "t"),
            _row("c", pd.NA, "t"),
        ]
    )
    summary = diag.summarize_group(df)
    assert summary["mentions"] == 1
    assert summary["zero_sponsor_docs"] == 2


# --- summarize_group ---


def test_summarize_group_counts_docs_mentions_and_gaps(diag):
    df = pd.DataFrame(
        [
            _row("a", ["X", "Y"], "t"),
            _row("b", [], "t"),
            _row("c", ["Z"], "t"),
        ]
    )
    summary = diag.summarize_group(df)
    assert summary["documents"] == 3
    assert summary["mentions"] == 3
    assert summary["mentions_per_doc"] == 1.0
    assert summary["zero_sponsor_docs"] == 1


def test_summarize_group_handles_an_empty_slice(diag):
    df = pd.DataFrame(columns=["sponsors"])
    summary = diag.summarize_group(df)
    assert summary == {
        "documents": 0,
        "mentions": 0,
        "mentions_per_doc": 0.0,
        "zero_sponsor_docs": 0,
        "zero_sponsor_share": 0.0,
    }


# --- analyze_zero_sponsor_docs ---


def test_recoverable_when_text_still_holds_parseable_sponsors(diag):
    """Stored sponsors empty but the current extractor finds them: a v1 gap."""
    df = pd.DataFrame([_row("131-LD-0001", [], SPONSOR_BLOCK)])
    buckets = diag.analyze_zero_sponsor_docs(df)
    assert buckets["recoverable"] == ["131-LD-0001"]
    assert buckets["marker_only"] == []


def test_marker_only_when_a_block_exists_but_nothing_parses(diag):
    text = "An Act To Do Something\nPresented by the Department of Transportation.\n"
    df = pd.DataFrame([_row("131-LD-0002", [], text)])
    buckets = diag.analyze_zero_sponsor_docs(df)
    assert buckets["marker_only"] == ["131-LD-0002"]


def test_no_marker_when_the_sponsor_block_is_absent(diag):
    df = pd.DataFrame([_row("131-LD-0003", [], "Be it enacted by the People of Maine.")])
    buckets = diag.analyze_zero_sponsor_docs(df)
    assert buckets["no_marker"] == ["131-LD-0003"]


def test_documents_with_stored_sponsors_are_not_bucketed(diag):
    df = pd.DataFrame([_row("131-LD-0004", ["DAUGHTRY"], SPONSOR_BLOCK)])
    buckets = diag.analyze_zero_sponsor_docs(df)
    assert buckets == {"recoverable": [], "marker_only": [], "no_marker": []}


def test_missing_text_counts_as_no_marker(diag):
    df = pd.DataFrame([_row("131-LD-0005", [], None)])
    buckets = diag.analyze_zero_sponsor_docs(df)
    assert buckets["no_marker"] == ["131-LD-0005"]


# --- diagnose_session ---


def _session_frame():
    return pd.DataFrame(
        [
            _row("132-LD-0001", ["DAUGHTRY", "PERRY"], SPONSOR_BLOCK),
            _row("132-LD-0002", [], SPONSOR_BLOCK),
            _row("132-LD-0003", [], "Be it enacted."),
            _row("132-LD-0004-CA_A_S337", [], "Amend the bill", amendment_code="CA_A_S337"),
            _row("132-LD-0005-CA_A_H0266", [], "Amend the bill", amendment_code="CA_A_H0266"),
        ]
    )


def test_diagnose_session_separates_amendments_from_originals(diag):
    result, _ = diag.diagnose_session(_session_frame(), 132, samples=5)
    assert result["all"]["documents"] == 5
    assert result["amendments"]["documents"] == 2
    assert result["originals"]["documents"] == 3
    # 2 mentions over 3 originals, not over all 5 documents -- this ratio is the
    # one that is comparable across sessions.
    assert result["originals"]["mentions_per_doc"] == 0.67
    assert result["all"]["mentions_per_doc"] == 0.4


def test_diagnose_session_buckets_only_originals(diag):
    result, _ = diag.diagnose_session(_session_frame(), 132, samples=5)
    zero = result["zero_sponsor_originals"]
    assert zero["recoverable"]["count"] == 1
    assert zero["no_marker"]["count"] == 1
    assert zero["recoverable"]["examples"] == ["132-LD-0002"]


def test_diagnose_session_samples_the_problem_buckets(diag):
    _, samples = diag.diagnose_session(_session_frame(), 132, samples=5)
    problem = [s for s in samples if s["bucket"] in ("recoverable", "marker_only")]
    assert [s["source_filename"] for s in problem] == ["132-LD-0002"]
    sample = problem[0]
    assert sample["bucket"] == "recoverable"
    assert sample["session"] == 132
    assert ("DAUGHTRY", "Senate") in [tuple(m) for m in sample["reextracted"]]
    assert sample["text_head"].startswith("STATE OF MAINE")


# --- sampling bills that DO have sponsors ---


def _mixed_frame():
    """Three sponsored bills with 1, 2 and 4 stored sponsors."""
    return pd.DataFrame(
        [
            _row("132-LD-0010", ["ONLYONE"], SPONSOR_BLOCK),
            _row("132-LD-0011", ["A", "B"], SPONSOR_BLOCK),
            _row("132-LD-0012", ["A", "B", "C", "D"], SPONSOR_BLOCK),
            _row("132-LD-0013", [], "Be it enacted."),
        ]
    )


def test_low_sponsor_samples_lead_with_the_fewest(diag):
    _, samples = diag.diagnose_session(_mixed_frame(), 132, samples=1)
    low = [s for s in samples if s["bucket"] == "has_sponsors_low"]
    assert [s["source_filename"] for s in low] == ["132-LD-0010"]
    assert low[0]["stored_sponsors"] == ["ONLYONE"]


def test_high_sponsor_control_is_included(diag):
    _, samples = diag.diagnose_session(_mixed_frame(), 132, samples=1)
    high = [s for s in samples if s["bucket"] == "has_sponsors_high"]
    assert [s["source_filename"] for s in high] == ["132-LD-0011", "132-LD-0012"]


def test_samples_expose_stored_vs_reextracted(diag):
    """The whole point: what the record holds, next to what the text says."""
    _, samples = diag.diagnose_session(_mixed_frame(), 132, samples=1)
    low = next(s for s in samples if s["bucket"] == "has_sponsors_low")
    assert low["stored_sponsors"] == ["ONLYONE"]
    # The text names two people, so the record is demonstrably losing sponsors.
    assert len(low["reextracted"]) == 2
    assert low["text_head"].startswith("STATE OF MAINE")


def test_unsponsored_bills_are_never_sampled_as_healthy(diag):
    _, samples = diag.diagnose_session(_mixed_frame(), 132, samples=1)
    healthy = [s for s in samples if s["bucket"].startswith("has_sponsors")]
    assert "132-LD-0013" not in [s["source_filename"] for s in healthy]


def test_no_healthy_samples_when_nothing_has_sponsors(diag):
    df = pd.DataFrame([_row("132-LD-0020", [], "Be it enacted.")])
    _, samples = diag.diagnose_session(df, 132, samples=3)
    assert [s for s in samples if s["bucket"].startswith("has_sponsors")] == []


def test_sample_count_is_capped(diag):
    rows = [_row(f"132-LD-{i:04d}", [], SPONSOR_BLOCK) for i in range(20)]
    _, samples = diag.diagnose_session(pd.DataFrame(rows), 132, samples=3)
    assert len(samples) == 3


# --- format_markdown ---


def test_markdown_reports_both_tables(diag):
    result, _ = diag.diagnose_session(_session_frame(), 132, samples=5)
    markdown = diag.format_markdown([result])
    assert "| 132 |" in markdown
    assert "mentions/doc (originals)" in markdown
    assert "recoverable" in markdown


# --- main ---


def test_main_writes_all_three_outputs(diag, tmp_path, monkeypatch):
    monkeypatch.setattr(
        diag._report, "load_session_bills", lambda source, session: _session_frame()
    )
    argv = ["--sessions", "132", "--parquet-source", "local", "--output", str(tmp_path)]
    assert diag.main(argv) == 0

    diagnosis = json.loads((tmp_path / "sponsor-extraction-diagnosis.json").read_text())
    assert diagnosis[0]["session"] == 132
    assert json.loads((tmp_path / "sponsor-extraction-samples.json").read_text())
    assert "mentions/doc" in (tmp_path / "sponsor-extraction-diagnosis.md").read_text()
