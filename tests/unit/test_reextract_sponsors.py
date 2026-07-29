"""Tests for the sponsor re-extraction over published text (issue #13, item 1).

The hazards these pin, in order of what they would cost:

1. Carrying the enrichment columns across a sponsors rewrite. They are
   index-aligned with `sponsors`, so keeping them attributes every enriched
   sponsor on a changed bill to the WRONG legislator — strictly worse than the
   inconsistency the re-extraction exists to fix.
2. Reading a count change as a swap. The comparison is a multiset difference
   both ways; a set difference reports {A:2}->{A:1} as no change.
3. Losing names silently. Losses are not automatically wrong, but they are
   never routine.
"""

import importlib.util
import json
from pathlib import Path

import pandas as pd
import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "reextract_sponsors.py"


@pytest.fixture(scope="module")
def mod():
    spec = importlib.util.spec_from_file_location("reextract_sponsors", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BILL = (
    "Presented by Senator BRENNER of Cumberland.\n"
    "Cosponsored by Senators: BAILEY of York, CURRY of Waldo.\n"
    "Be it enacted by the People of the State of Maine as follows:\n"
)


def frame(rows):
    return pd.DataFrame(rows)


def row(ld="0001", text=BILL, sponsors=("OLD",), **overrides):
    base = {
        "session": 132,
        "ld_number": ld,
        "text": text,
        "sponsors": list(sponsors),
        "sponsor_chambers": [None] * len(sponsors),
        "sponsor_ids": ["ocd-person/x"] * len(sponsors),
        "sponsor_parties": ["Democratic"] * len(sponsors),
        "sponsor_districts": ["12"] * len(sponsors),
        "sponsor_match_confidence": [1.0] * len(sponsors),
    }
    base.update(overrides)
    return base


# --- the alignment hazard, which is the reason this file exists ---


def test_enrichment_is_cleared_not_carried_across_the_rewrite(mod):
    """sponsor_ids[i] describes sponsors[i]. After the rewrite, position i is a
    different person, so carrying the old values attributes every enriched
    sponsor on a changed bill to the wrong legislator."""
    out, _ = mod.reextract_session(frame([row()]), 132)

    sponsors = out["sponsors"].iloc[0]
    assert sponsors == ["BRENNER", "BAILEY", "CURRY"]
    # All FOUR enrichment columns — review caught sponsor_match_confidence
    # missing from this loop, which left one v2 column's clearing unpinned.
    for column in (
        "sponsor_ids",
        "sponsor_parties",
        "sponsor_districts",
        "sponsor_match_confidence",
    ):
        assert out[column].iloc[0] == [None, None, None], column
    # ...and the cleared lists are aligned with the NEW sponsors, not the old.
    assert len(out["sponsor_ids"].iloc[0]) == len(sponsors)


def test_a_source_without_enrichment_columns_still_gets_them(mod):
    """A v1-era parquet has no enrichment columns. The output must carry the
    published layout regardless — clearing only what already existed would
    hand enrich_published.py a schema gap to discover later."""
    v1 = frame(
        [
            {
                "session": 132,
                "ld_number": "0001",
                "text": BILL,
                "sponsors": ["OLD"],
            }
        ]
    )
    out, _ = mod.reextract_session(v1, 132)
    for column in (
        "sponsor_chambers",
        "sponsor_ids",
        "sponsor_parties",
        "sponsor_districts",
        "sponsor_match_confidence",
    ):
        assert column in out.columns, column
        assert len(out[column].iloc[0]) == 3, column


def test_chambers_are_rebuilt_alongside_the_names(mod):
    out, _ = mod.reextract_session(frame([row()]), 132)
    assert out["sponsor_chambers"].iloc[0] == ["Senate", "Senate", "Senate"]


def test_an_unchanged_bill_still_gets_cleared_enrichment(mod):
    """Clearing is keyed on the rewrite happening at all, not on whether the
    names moved: the columns describe a (names, roster-version) pair, and the
    roster half changes for every row. Re-running enrichment is a REQUIRED
    second step; leaving stale ids on 'unchanged' rows would make the dataset
    a mix of two enrichment runs with nothing marking which is which."""
    out, summary = mod.reextract_session(frame([row(sponsors=("BRENNER", "BAILEY", "CURRY"))]), 132)
    assert summary["rows_changed"] == 0
    assert out["sponsor_ids"].iloc[0] == [None, None, None]


# --- the comparison, which must not flatter the result ---


def test_a_count_change_is_reported_not_swallowed(mod):
    """Multiset both ways: {PERRY:2} -> {PERRY:1} is a loss, not a no-op."""
    text = (
        "Presented by Senator PERRY of Bangor.\n"
        "Cosponsored by Representative PERRY of Calais.\nBe it enacted:\n"
    )
    _, summary = mod.reextract_session(
        frame([row(text=text, sponsors=("PERRY", "PERRY", "PERRY"))]), 132
    )
    assert summary["mentions_before"] == 3
    assert summary["mentions_after"] == 2
    assert summary["distinct_lost"] == 1
    assert dict(summary["top_lost"])["PERRY"] == 1


def test_gains_and_losses_on_one_bill_are_both_reported(mod):
    _, summary = mod.reextract_session(frame([row(sponsors=("GONE", "BAILEY"))]), 132)
    assert summary["rows_changed"] == 1
    assert dict(summary["top_gained"]) == {"BRENNER": 1, "CURRY": 1}
    assert dict(summary["top_lost"]) == {"GONE": 1}


def test_null_and_empty_text_rows_survive_without_inventing_sponsors(mod):
    out, summary = mod.reextract_session(
        frame([row(text=None, sponsors=()), row(ld="0002", text="", sponsors=("OLD",))]), 132
    )
    assert list(out["sponsors"]) == [[], []]
    assert summary["mentions_after"] == 0
    assert dict(summary["top_lost"]) == {"OLD": 1}


# --- the CLI contract ---


def test_report_only_writes_the_summary_but_no_parquet(mod, tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "load_session", lambda source, session: frame([row()]))
    code = mod.main(["--sessions", "132", "--output", str(tmp_path / "out"), "--report-only"])
    assert code == 0
    assert (tmp_path / "out" / "reextract-summary.json").exists()
    assert not (tmp_path / "out" / "132").exists()


def test_a_full_run_writes_one_parquet_per_session_in_the_published_layout(
    mod, tmp_path, monkeypatch
):
    monkeypatch.setattr(mod, "load_session", lambda source, session: frame([row()]))
    code = mod.main(["--sessions", "132", "--output", str(tmp_path / "out")])
    assert code == 0
    written = pd.read_parquet(tmp_path / "out" / "132" / "train-00000-of-00001.parquet")
    assert list(written["sponsors"].iloc[0]) == ["BRENNER", "BAILEY", "CURRY"]
    summary = json.loads((tmp_path / "out" / "reextract-summary.json").read_text())
    assert summary[0]["session"] == 132


def test_a_session_that_cannot_be_loaded_fails_the_run(mod, tmp_path, monkeypatch):
    def boom(source, session):
        raise FileNotFoundError("no parquet")

    monkeypatch.setattr(mod, "load_session", boom)
    assert mod.main(["--sessions", "132", "--output", str(tmp_path / "o")]) == 1


def test_the_parquet_path_includes_the_data_segment(mod):
    """Reading `<source>/<session>/...` without `data/` silently 404s on the
    real repo — this exact mistake cost a debugging round earlier tonight."""
    path = mod.PARQUET_TEMPLATE.format(source="hf://datasets/pem207/maine-bills", session=132)
    assert path == "hf://datasets/pem207/maine-bills/data/132/train-00000-of-00001.parquet"
