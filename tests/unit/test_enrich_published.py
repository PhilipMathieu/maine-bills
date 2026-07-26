"""Tests for the enrich-in-place publishing path."""

import importlib.util
import json
from pathlib import Path

import pandas as pd
import pytest

from maine_bills.openstates import RosterEntry, roster_cache_path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "enrich_published.py"


@pytest.fixture(scope="module")
def enrich_mod():
    spec = importlib.util.spec_from_file_location("enrich_published", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _entry(os_id, name, family, chamber, district, party="Democratic"):
    return RosterEntry(
        openstates_id=os_id,
        name=name,
        family_name=family,
        party=party,
        chamber=chamber,
        district=district,
    )


ROSTER = [
    _entry("ocd-person/perry-a", "Anne Perry", "Perry", "House", "9"),
    _entry("ocd-person/perry-j", "Joseph Perry", "Perry", "Senate", "31"),
    _entry("ocd-person/daughtry", "Mattie Daughtry", "Daughtry", "Senate", "23"),
]


@pytest.fixture
def source(tmp_path):
    """A local parquet source plus a seeded roster cache."""
    cache = tmp_path / "cache"
    cache.mkdir()
    roster_cache_path(cache, 132).write_text(json.dumps([r.to_dict() for r in ROSTER]))

    session_dir = tmp_path / "src" / "132"
    session_dir.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "session": 132,
                "ld_number": "1",
                "source_filename": "132-LD-1",
                "sponsors": ["DAUGHTRY", "PERRY"],
                "text": (
                    "Presented by Senator DAUGHTRY of Cumberland.\n"
                    "Cosponsored by Senator PERRY of Bangor.\nBe it enacted"
                ),
            },
            {
                "session": 132,
                "ld_number": "2",
                "source_filename": "132-LD-2",
                "sponsors": ["PERRY"],
                "text": "Presented by Representative PERRY of Calais.\nBe it enacted",
            },
            {
                "session": 132,
                "ld_number": "3",
                "source_filename": "132-LD-3",
                "sponsors": ["NOBODY"],
                "text": "Presented by Senator NOBODY of Nowhere.\nBe it enacted",
            },
        ]
    ).to_parquet(session_dir / "train-00000-of-00001.parquet", index=False)
    return tmp_path / "src", cache


def _run(enrich_mod, source, tmp_path):
    src, cache = source
    out = tmp_path / "out"
    rc = enrich_mod.main(
        [
            "--sessions",
            "132",
            "--parquet-source",
            str(src),
            "--output",
            str(out),
            "--cache-dir",
            str(cache),
        ]
    )
    assert rc == 0
    return pd.read_parquet(out / "132" / "train-00000-of-00001.parquet"), out


def test_chamber_hint_splits_shared_surname(enrich_mod, source, tmp_path):
    """The two Perrys must resolve to different legislators."""
    df, _ = _run(enrich_mod, source, tmp_path)
    assert list(df.sponsor_ids[0]) == ["ocd-person/daughtry", "ocd-person/perry-j"]
    assert list(df.sponsor_ids[1]) == ["ocd-person/perry-a"]


def test_unmatched_sponsor_stays_null(enrich_mod, source, tmp_path):
    df, _ = _run(enrich_mod, source, tmp_path)
    assert list(df.sponsor_ids[2]) == [None]
    assert list(df.sponsor_parties[2]) == [None]


def test_enrichment_columns_stay_aligned(enrich_mod, source, tmp_path):
    df, _ = _run(enrich_mod, source, tmp_path)
    for _, row in df.iterrows():
        n = len(row.sponsors)
        assert len(row.sponsor_chambers) == n
        assert len(row.sponsor_ids) == n
        assert len(row.sponsor_parties) == n
        assert len(row.sponsor_districts) == n
        assert len(row.sponsor_match_confidence) == n


def test_original_sponsor_strings_untouched(enrich_mod, source, tmp_path):
    """Provenance: enrichment must never rewrite the extracted names."""
    df, _ = _run(enrich_mod, source, tmp_path)
    assert list(df.sponsors[0]) == ["DAUGHTRY", "PERRY"]
    assert list(df.sponsors[2]) == ["NOBODY"]


def test_summary_reports_per_session_rate(enrich_mod, source, tmp_path):
    _, out = _run(enrich_mod, source, tmp_path)
    summary = json.loads((out / "enrichment_summary.json").read_text())
    assert summary == [{"session": 132, "mentions": 4, "matched": 3, "rate": 0.75}]
