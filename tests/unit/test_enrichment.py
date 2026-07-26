"""Tests for the sponsor enrichment integration point (schema v2)."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd
import pytest

from maine_bills.enrichment import apply_enrichment, enrich_dataframe, load_matcher
from maine_bills.schema import BillRecord


def make_record(sponsors):
    return BillRecord(
        session=132,
        ld_number="0001",
        document_type="bill",
        amendment_code=None,
        amendment_type=None,
        chamber=None,
        text="Bill text",
        extraction_confidence=0.9,
        sponsors=sponsors,
    )


def make_match(**overrides):
    """Attribute-style match object as produced by the sponsor matcher."""
    defaults = dict(
        openstates_id="ocd-person/abc-123",
        canonical_name="Jane Smith",
        party="Democratic",
        district="12",
        confidence=1.0,
        method="exact",
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


# --- apply_enrichment ---


class TestApplyEnrichment:
    def test_applies_object_matches(self):
        record = make_record(["Senator SMITH", "Representative JONES"])
        matches = [
            make_match(),
            make_match(
                openstates_id="ocd-person/def-456",
                party="Republican",
                district="45",
                confidence=0.91,
            ),
        ]

        apply_enrichment(record, matches)

        assert record.sponsor_ids == ["ocd-person/abc-123", "ocd-person/def-456"]
        assert record.sponsor_parties == ["Democratic", "Republican"]
        assert record.sponsor_districts == ["12", "45"]
        assert record.sponsor_match_confidence == [1.0, 0.91]

    def test_applies_dict_matches(self):
        record = make_record(["Senator SMITH"])
        matches = [
            {
                "openstates_id": "ocd-person/abc-123",
                "canonical_name": "Jane Smith",
                "party": "Democratic",
                "district": "12",
                "confidence": 0.88,
                "method": "fuzzy",
            }
        ]

        apply_enrichment(record, matches)

        assert record.sponsor_ids == ["ocd-person/abc-123"]
        assert record.sponsor_parties == ["Democratic"]
        assert record.sponsor_districts == ["12"]
        assert record.sponsor_match_confidence == [0.88]

    def test_unmatched_sponsors_stay_none(self):
        record = make_record(["Senator SMITH", "Representative UNKNOWN"])

        apply_enrichment(record, [make_match(), None])

        assert record.sponsor_ids == ["ocd-person/abc-123", None]
        assert record.sponsor_parties == ["Democratic", None]
        assert record.sponsor_districts == ["12", None]
        assert record.sponsor_match_confidence == [1.0, None]

    def test_sponsors_strings_never_modified(self):
        """Enrichment must not rewrite the verbatim sponsor names (provenance)."""
        sponsors = ["Senator SMTIH"]  # deliberate typo, fuzzy-matched
        record = make_record(list(sponsors))

        apply_enrichment(record, [make_match(canonical_name="Jane Smith", method="fuzzy")])

        assert record.sponsors == sponsors

    def test_misaligned_matches_raise(self):
        record = make_record(["Senator SMITH", "Representative JONES"])
        with pytest.raises(ValueError, match="align index-wise"):
            apply_enrichment(record, [make_match()])

    def test_empty_sponsors_empty_matches(self):
        record = make_record([])
        apply_enrichment(record, [])
        assert record.sponsor_ids == []
        assert record.sponsor_match_confidence == []

    def test_returns_same_record(self):
        record = make_record(["Senator SMITH"])
        assert apply_enrichment(record, [None]) is record


# --- enrich_dataframe ---


class TestEnrichDataframe:
    def _make_df(self):
        records = [
            make_record(["Senator SMITH", "Representative UNKNOWN"]),
            make_record([]),
        ]
        return pd.DataFrame([r.__dict__ for r in records])

    def test_fills_enrichment_columns(self):
        df = self._make_df()

        def matcher_fn(sponsors):
            return [make_match() if "SMITH" in name else None for name in sponsors]

        result = enrich_dataframe(df, matcher_fn)

        assert result.iloc[0]["sponsor_ids"] == ["ocd-person/abc-123", None]
        assert result.iloc[0]["sponsor_parties"] == ["Democratic", None]
        assert result.iloc[0]["sponsor_districts"] == ["12", None]
        assert result.iloc[0]["sponsor_match_confidence"] == [1.0, None]
        assert result.iloc[1]["sponsor_ids"] == []

    def test_passes_session_when_matcher_accepts_it(self):
        df = self._make_df()
        seen_sessions = []

        def matcher_fn(sponsors, session=None):
            seen_sessions.append(session)
            return [None] * len(sponsors)

        enrich_dataframe(df, matcher_fn)
        assert seen_sessions == [132, 132]

    def test_sponsors_column_untouched(self):
        df = self._make_df()
        enrich_dataframe(df, lambda sponsors: [make_match()] * len(sponsors))
        assert list(df.iloc[0]["sponsors"]) == ["Senator SMITH", "Representative UNKNOWN"]

    def test_misaligned_matcher_output_raises(self):
        df = self._make_df()
        with pytest.raises(ValueError, match="Matcher returned"):
            enrich_dataframe(df, lambda sponsors: [None])

    def test_empty_dataframe_is_noop(self):
        df = pd.DataFrame()
        matcher_fn = MagicMock()
        result = enrich_dataframe(df, matcher_fn)
        assert result.empty
        matcher_fn.assert_not_called()


# --- load_matcher ---


class TestLoadMatcher:
    def test_returns_none_and_warns_when_module_missing(self):
        """sponsor_matching is built on a parallel branch; absence must no-op."""
        logger = MagicMock()
        matcher_fn = load_matcher(logger)

        # The module does not exist on this branch
        assert matcher_fn is None
        logger.warning.assert_called_once()
        assert "sponsor_matching" in logger.warning.call_args.args[0]

    def test_returns_match_function_when_module_present(self, mocker):
        fake_module = MagicMock()
        fake_module.match_sponsors = lambda sponsors: [None] * len(sponsors)
        mocker.patch.dict("sys.modules", {"maine_bills.sponsor_matching": fake_module})

        matcher_fn = load_matcher(MagicMock())
        assert matcher_fn is fake_module.match_sponsors

    def test_warns_when_module_lacks_match_function(self, mocker):
        fake_module = MagicMock(spec=[])  # no match_sponsors attribute
        mocker.patch.dict("sys.modules", {"maine_bills.sponsor_matching": fake_module})

        logger = MagicMock()
        assert load_matcher(logger) is None
        logger.warning.assert_called_once()


class TestMatcherContractEdgeCases:
    """Regression tests for review findings on falsy matches and introspection."""

    def test_falsy_match_object_is_not_treated_as_unmatched(self):
        """A match with a falsy __bool__ must still populate enrichment columns."""

        class FalsyMatch:
            openstates_id = "ocd-person/x1"
            party = "Democratic"
            district = "23"
            confidence = 1.0

            def __bool__(self):
                return False

        df = pd.DataFrame([{"session": 132, "sponsors": ["DAUGHTRY"]}])
        out = enrich_dataframe(df, lambda sponsors: [FalsyMatch()])
        assert out["sponsor_ids"][0] == ["ocd-person/x1"]
        assert out["sponsor_parties"][0] == ["Democratic"]
        assert out["sponsor_match_confidence"][0] == [1.0]

    def test_empty_dict_match_is_not_treated_as_unmatched(self):
        """An empty dict is falsy but present; its (absent) fields read as None."""
        df = pd.DataFrame([{"session": 132, "sponsors": ["DAUGHTRY"]}])
        out = enrich_dataframe(df, lambda sponsors: [{}])
        assert out["sponsor_ids"][0] == [None]

    def test_uninspectable_matcher_falls_back_instead_of_raising(self):
        """inspect.signature() raising must not abort enrichment."""

        class NoSignature:
            def __call__(self, sponsors):
                return [None] * len(sponsors)

            @property
            def __signature__(self):
                raise ValueError("not introspectable")

        df = pd.DataFrame([{"session": 132, "sponsors": ["DAUGHTRY"]}])
        out = enrich_dataframe(df, NoSignature())
        assert out["sponsor_ids"][0] == [None]
