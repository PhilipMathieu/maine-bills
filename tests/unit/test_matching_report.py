"""Tests for the CI matching report script (scripts/run_matching_report.py)."""

import importlib.util
import json
from pathlib import Path

import pandas as pd
import pytest

from maine_bills.openstates import RosterEntry, roster_cache_path
from maine_bills.sponsor_matching import SponsorMatcher

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "run_matching_report.py"


@pytest.fixture(scope="module")
def report_mod():
    spec = importlib.util.spec_from_file_location("run_matching_report", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _entry(os_id, name, family, party, chamber, district):
    return RosterEntry(
        openstates_id=os_id,
        name=name,
        family_name=family,
        party=party,
        chamber=chamber,
        district=district,
    )


ROSTER = [
    _entry("ocd-person/daughtry", "Mattie Daughtry", "Daughtry", "Democratic", "Senate", "23"),
    _entry("ocd-person/libby-n", "Nathan Libby", "Libby", "Democratic", "Senate", "21"),
    _entry("ocd-person/libby-l", "Laurel Libby", "Libby", "Republican", "House", "90"),
    _entry("ocd-person/carney", "Anne Carney", "Carney", "Democratic", "Senate", "29"),
]


def _bills_df():
    return pd.DataFrame(
        [
            {
                "session": 132,
                "ld_number": "0001",
                "source_filename": "132-LD-0001",
                "sponsors": ["DAUGHTRY", "LIBBY"],
            },
            {
                "session": 132,
                "ld_number": "0002",
                "source_filename": "132-LD-0002",
                "sponsors": ["DAUGHTREY", "GARBAGEXYZ"],
            },
            {
                "session": 132,
                "ld_number": "0003",
                "source_filename": "132-LD-0003",
                "sponsors": ["LIBBY", "CARNEY"],
            },
            {
                "session": 132,
                "ld_number": "0004",
                "source_filename": "132-LD-0004",
                "sponsors": [],
            },
        ]
    )


# --- analyze_session ---


def test_analyze_session_counts_and_rates(report_mod):
    matcher = SponsorMatcher(ROSTER)
    stats = report_mod.analyze_session(_bills_df(), matcher, 132)

    assert stats["session"] == 132
    assert stats["bills"] == 4
    assert stats["sponsor_mentions"] == 6
    assert stats["counts"] == {"exact": 2, "ocr": 0, "fuzzy": 1, "ambiguous": 2, "unmatched": 1}
    assert stats["rates"]["exact"] == pytest.approx(2 / 6, abs=1e-4)
    assert stats["rates"]["unmatched"] == pytest.approx(1 / 6, abs=1e-4)


def test_analyze_session_name_lists_with_bill_counts(report_mod):
    matcher = SponsorMatcher(ROSTER)
    stats = report_mod.analyze_session(_bills_df(), matcher, 132)

    assert stats["unmatched"] == [{"name": "GARBAGEXYZ", "bill_count": 1}]
    assert stats["ambiguous"] == [{"name": "LIBBY", "bill_count": 2}]


def test_analyze_session_records_fuzzy_matches(report_mod):
    matcher = SponsorMatcher(ROSTER)
    stats = report_mod.analyze_session(_bills_df(), matcher, 132)

    assert len(stats["fuzzy_matches"]) == 1
    fuzzy = stats["fuzzy_matches"][0]
    assert fuzzy["sponsor"] == "DAUGHTREY"
    assert fuzzy["canonical_name"] == "Mattie Daughtry"
    assert fuzzy["bill_id"] == "132-LD-0002"
    assert 0.88 <= fuzzy["confidence"] < 1.0


# --- build_report ---


def test_build_report_samples_fuzzy_matches_deterministically(report_mod):
    fuzzy = [
        {"session": 132, "bill_id": f"132-LD-{i:04d}", "sponsor": f"NAME{i}"} for i in range(50)
    ]
    stats = {
        "session": 132,
        "bills": 50,
        "sponsor_mentions": 50,
        "counts": {},
        "rates": {},
        "unmatched": [],
        "ambiguous": [],
        "fuzzy_matches": fuzzy,
    }
    report_a = report_mod.build_report([stats], seed=42)
    report_b = report_mod.build_report([stats], seed=42)

    assert len(report_a["fuzzy_sample"]) == 30
    assert report_a["fuzzy_sample"] == report_b["fuzzy_sample"]
    # Session stats keep everything except the raw fuzzy match list
    assert "fuzzy_matches" not in report_a["sessions"][0]


def test_build_report_sample_smaller_than_pool(report_mod):
    stats = {
        "session": 132,
        "bills": 1,
        "sponsor_mentions": 1,
        "counts": {},
        "rates": {},
        "unmatched": [],
        "ambiguous": [],
        "fuzzy_matches": [{"session": 132, "bill_id": "132-LD-0001", "sponsor": "X"}],
    }
    report = report_mod.build_report([stats], seed=1)
    assert len(report["fuzzy_sample"]) == 1


# --- render_markdown ---


def test_render_markdown_contains_rates_and_lists(report_mod):
    matcher = SponsorMatcher(ROSTER)
    stats = report_mod.analyze_session(_bills_df(), matcher, 132)
    report = report_mod.build_report([stats], seed=1)
    markdown = report_mod.render_markdown(report)

    assert "# Sponsor -> OpenStates Matching Report" in markdown
    assert "| 132 | 4 | 6 |" in markdown
    assert "GARBAGEXYZ" in markdown
    assert "LIBBY" in markdown
    assert "DAUGHTREY" in markdown
    assert "Mattie Daughtry" in markdown


# --- load_session_bills ---


def test_load_session_bills_local_dir(report_mod, tmp_path):
    session_dir = tmp_path / "132"
    session_dir.mkdir()
    _bills_df().to_parquet(session_dir / "train-00000-of-00001.parquet", index=False)

    df = report_mod.load_session_bills(str(tmp_path), 132)
    assert len(df) == 4


def test_load_session_bills_missing_raises(report_mod, tmp_path):
    with pytest.raises(FileNotFoundError, match="session 131"):
        report_mod.load_session_bills(str(tmp_path), 131)


# --- main (end-to-end with cached roster, no network) ---


def test_main_writes_reports_from_cached_roster(report_mod, tmp_path):
    # Pre-populate the roster cache so no provider fetch happens
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    roster_json = [entry.to_dict() for entry in ROSTER]
    roster_cache_path(cache_dir, 132).write_text(json.dumps(roster_json))

    # Local parquet source
    data_dir = tmp_path / "data"
    (data_dir / "132").mkdir(parents=True)
    _bills_df().to_parquet(data_dir / "132" / "train-00000-of-00001.parquet", index=False)

    output_dir = tmp_path / "report"
    exit_code = report_mod.main(
        [
            "--sessions",
            "132",
            "--parquet-source",
            str(data_dir),
            "--output",
            str(output_dir),
            "--cache-dir",
            str(cache_dir),
        ]
    )

    assert exit_code == 0
    report = json.loads((output_dir / "matching_report.json").read_text())
    assert report["sessions"][0]["session"] == 132
    assert report["sessions"][0]["counts"]["exact"] == 2
    markdown = (output_dir / "matching_report.md").read_text()
    assert "Sponsor -> OpenStates Matching Report" in markdown


# --- chamber hints ---


def test_chambers_from_stored_column(report_mod):
    """When data was extracted with chamber capture, use it directly."""
    row = {"sponsor_chambers": ["House", "Senate"], "text": "irrelevant"}
    assert report_mod.chambers_for_row(row, ["PERRY", "PERRY"]) == ["House", "Senate"]


def test_chambers_derived_from_published_text(report_mod):
    """v1 data has no chamber column, but the text retains the sponsor block."""
    row = {
        "text": (
            "An Act to Test\nPresented by Senator LIBBY of Androscoggin.\n"
            "Cosponsored by Representative CARNEY of Cape Elizabeth.\nBe it enacted"
        )
    }
    assert report_mod.chambers_for_row(row, ["LIBBY", "CARNEY"]) == ["Senate", "House"]


def test_chambers_absent_when_no_text(report_mod):
    assert report_mod.chambers_for_row({}, ["LIBBY"]) == [None]


def test_misaligned_stored_column_falls_back(report_mod):
    """A stale/misaligned column must not be zipped against sponsors."""
    row = {"sponsor_chambers": ["House"], "text": "Presented by Senator LIBBY of X.\nBe it"}
    assert report_mod.chambers_for_row(row, ["LIBBY", "CARNEY"]) == ["Senate", None]


def test_analyze_session_uses_hints_to_resolve_ambiguity(report_mod):
    """End to end: the ambiguous LIBBY resolves once the text supplies a chamber."""
    df_no_text = pd.DataFrame(
        [{"session": 132, "ld_number": "1", "source_filename": "132-LD-1", "sponsors": ["LIBBY"]}]
    )
    assert (
        report_mod.analyze_session(df_no_text, SponsorMatcher(ROSTER), 132)["counts"]["ambiguous"]
        == 1
    )

    df_with_text = df_no_text.copy()
    df_with_text["text"] = ["Presented by Senator LIBBY of Androscoggin.\nBe it enacted"]
    stats = report_mod.analyze_session(df_with_text, SponsorMatcher(ROSTER), 132)
    assert stats["counts"]["ambiguous"] == 0
    assert stats["counts"]["exact"] == 1
