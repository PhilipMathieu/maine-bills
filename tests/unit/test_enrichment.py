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
    """load_matcher() resolves maine_bills.sponsor_matching lazily.

    Note: `from . import sponsor_matching` resolves the attribute on the
    package, so patching sys.modules alone does not intercept it once the
    real module exists — these tests patch the package attribute too.
    """

    def test_returns_the_real_matcher_when_available(self):
        """Now that both modules ship together, the default path must work."""
        from maine_bills import sponsor_matching

        logger = MagicMock()
        matcher_fn = load_matcher(logger)

        assert matcher_fn is sponsor_matching.match_sponsors
        logger.warning.assert_not_called()

    def test_returns_none_and_warns_when_module_missing(self, monkeypatch):
        """A stripped install without sponsor_matching must no-op, not crash.

        `from . import X` short-circuits on the package attribute, so the
        attribute must be removed as well as the sys.modules entry nulled.
        """
        import sys

        import maine_bills

        monkeypatch.delattr(maine_bills, "sponsor_matching", raising=False)
        monkeypatch.setitem(sys.modules, "maine_bills.sponsor_matching", None)
        logger = MagicMock()

        assert load_matcher(logger) is None
        logger.warning.assert_called_once()
        assert "sponsor_matching" in logger.warning.call_args.args[0]

    def test_returns_match_function_when_module_present(self, mocker):
        import maine_bills

        fake_module = MagicMock()
        fake_module.match_sponsors = lambda sponsors: [None] * len(sponsors)
        mocker.patch.object(maine_bills, "sponsor_matching", fake_module)
        mocker.patch.dict("sys.modules", {"maine_bills.sponsor_matching": fake_module})

        assert load_matcher(MagicMock()) is fake_module.match_sponsors

    def test_warns_when_module_lacks_match_function(self, mocker):
        import maine_bills

        fake_module = MagicMock(spec=[])  # no match_sponsors attribute
        mocker.patch.object(maine_bills, "sponsor_matching", fake_module)
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


class TestAsAlignedList:
    """Parquet null cells are not iterable; coercion must not raise."""

    def test_null_forms_return_none(self):
        import numpy as np

        from maine_bills.enrichment import as_aligned_list

        for null in (None, np.nan, pd.NA):
            assert as_aligned_list(null) is None

    def test_list_and_array_pass_through(self):
        import numpy as np

        from maine_bills.enrichment import as_aligned_list

        assert as_aligned_list(["House", None]) == ["House", None]
        assert as_aligned_list(np.array(["House", "Senate"])) == ["House", "Senate"]

    def test_string_is_not_exploded(self):
        from maine_bills.enrichment import as_aligned_list

        assert as_aligned_list("House") is None

    def test_enrichment_survives_null_chambers_cell(self):
        """Regression: a NaN sponsor_chambers cell must not abort enrichment."""
        import numpy as np

        def matcher(sponsors, session=None, chambers=None):
            return [None] * len(sponsors)

        df = pd.DataFrame(
            [
                {"session": 132, "sponsors": ["DAUGHTRY"], "sponsor_chambers": np.nan},
                {"session": 132, "sponsors": ["PERRY"], "sponsor_chambers": ["House"]},
            ]
        )
        out = enrich_dataframe(df, matcher)
        assert out["sponsor_ids"][0] == [None]

    def test_chambers_forwarded_when_present(self):
        seen = {}

        def matcher(sponsors, session=None, chambers=None):
            seen["chambers"] = chambers
            return [None] * len(sponsors)

        df = pd.DataFrame(
            [
                {
                    "session": 132,
                    "sponsors": ["PERRY", "LIBBY"],
                    "sponsor_chambers": ["House", "Senate"],
                }
            ]
        )
        enrich_dataframe(df, matcher)
        assert seen["chambers"] == ["House", "Senate"]
