"""Sponsor enrichment integration point (dataset schema v2).

Applies sponsor match results to BillRecords / DataFrames without depending on
any particular matcher implementation. A matcher is any callable with the
contract:

    matcher_fn(sponsors: list[str]) -> list[Match | dict | None]

where the returned list is aligned index-wise with the input `sponsors` list,
None marks an unmatched sponsor, and each match (attribute-style object or
dict) provides: openstates_id, canonical_name, party, district, confidence,
method.

The default matcher is loaded lazily from ``maine_bills.sponsor_matching``
(built separately); if that module is unavailable, enrichment no-ops with a
warning so the v1 pipeline keeps working unchanged.
"""

import inspect
import logging

import pandas as pd

from .schema import BillRecord

logger = logging.getLogger(__name__)

# Attribute/key names a match object or dict must provide
MATCH_FIELDS = ("openstates_id", "canonical_name", "party", "district", "confidence", "method")


def _match_value(match, name: str):
    """Read a field from a match, supporting both objects and dicts."""
    if isinstance(match, dict):
        return match.get(name)
    return getattr(match, name, None)


def as_aligned_list(value) -> list | None:
    """Coerce a parquet list-column cell to a list, or None if it isn't one.

    Nulls arrive as None, NaN, or pd.NA depending on dtype — none of which are
    iterable — and list columns round-trip as numpy arrays. Strings are treated
    as absent rather than exploded into characters.
    """
    if value is None or isinstance(value, str):
        return None
    try:
        return list(value)
    except TypeError:
        return None


def apply_enrichment(record: BillRecord, matches: list) -> BillRecord:
    """Apply sponsor match results to a BillRecord in place.

    The original `sponsors` strings are never modified (provenance); only the
    four v2 enrichment fields are populated.

    Args:
        record: BillRecord to enrich
        matches: List aligned index-wise with record.sponsors. Each entry is
                 either None (unmatched) or a match object/dict exposing
                 openstates_id, party, district, and confidence.

    Returns:
        The same BillRecord, with sponsor_ids, sponsor_parties,
        sponsor_districts, and sponsor_match_confidence populated
        (None entries where unmatched).

    Raises:
        ValueError: If len(matches) != len(record.sponsors)
    """
    if len(matches) != len(record.sponsors):
        raise ValueError(
            f"Got {len(matches)} matches for {len(record.sponsors)} sponsors; "
            "matches must align index-wise with sponsors"
        )

    record.sponsor_ids = [
        _match_value(m, "openstates_id") if m is not None else None for m in matches
    ]
    record.sponsor_parties = [_match_value(m, "party") if m is not None else None for m in matches]
    record.sponsor_districts = [
        _match_value(m, "district") if m is not None else None for m in matches
    ]
    record.sponsor_match_confidence = [
        _match_value(m, "confidence") if m is not None else None for m in matches
    ]
    return record


def enrich_dataframe(df: pd.DataFrame, matcher_fn) -> pd.DataFrame:
    """Populate the v2 enrichment columns of a scraped DataFrame.

    Args:
        df: DataFrame of BillRecord rows (must have `session` and `sponsors`
            columns; enrichment columns are created if absent)
        matcher_fn: Callable taking a list of sponsor name strings and
                    returning an aligned list of match objects/dicts (with
                    openstates_id, party, district, confidence) or None for
                    unmatched names. Also receives the record's session as a
                    `session` keyword argument if it accepts one.

    Returns:
        The same DataFrame with sponsor_ids, sponsor_parties,
        sponsor_districts, and sponsor_match_confidence columns filled.
    """
    if df.empty:
        return df

    try:
        params = inspect.signature(matcher_fn).parameters
        has_var_kwargs = any(p.kind == p.VAR_KEYWORD for p in params.values())
        accepts_session = "session" in params or has_var_kwargs
        accepts_chambers = "chambers" in params or has_var_kwargs
    except (TypeError, ValueError):
        # Some callables (e.g. C-implemented) aren't introspectable; assume the
        # simpler contract rather than aborting enrichment.
        accepts_session = accepts_chambers = False

    ids_col, parties_col, districts_col, confidence_col = [], [], [], []
    matched = total = 0

    for _, row in df.iterrows():
        sponsors = list(row["sponsors"])
        kwargs = {}
        if accepts_session:
            kwargs["session"] = row["session"]
        if accepts_chambers:
            chambers = as_aligned_list(row.get("sponsor_chambers"))
            if chambers is not None and len(chambers) == len(sponsors):
                kwargs["chambers"] = chambers
        matches = matcher_fn(sponsors, **kwargs)
        if len(matches) != len(sponsors):
            raise ValueError(
                f"Matcher returned {len(matches)} matches for {len(sponsors)} sponsors"
            )
        ids_col.append(
            [_match_value(m, "openstates_id") if m is not None else None for m in matches]
        )
        parties_col.append([_match_value(m, "party") if m is not None else None for m in matches])
        districts_col.append(
            [_match_value(m, "district") if m is not None else None for m in matches]
        )
        confidence_col.append(
            [_match_value(m, "confidence") if m is not None else None for m in matches]
        )
        total += len(sponsors)
        matched += sum(1 for m in matches if m is not None)

    df["sponsor_ids"] = ids_col
    df["sponsor_parties"] = parties_col
    df["sponsor_districts"] = districts_col
    df["sponsor_match_confidence"] = confidence_col

    if total:
        logger.info(f"Enriched {matched}/{total} sponsor mentions ({matched / total:.1%})")
    return df


def load_matcher(logger_: logging.Logger | None = None):
    """Load the default matcher from maine_bills.sponsor_matching, if available.

    Returns:
        A matcher_fn suitable for enrich_dataframe(), or None (with a warning)
        if the sponsor_matching module or its match function is unavailable —
        callers should treat None as "skip enrichment".
    """
    log = logger_ or logger
    try:
        from . import sponsor_matching
    except ImportError:
        log.warning(
            "Sponsor enrichment unavailable: maine_bills.sponsor_matching not found; "
            "skipping --enrich (records keep null enrichment fields)"
        )
        return None

    matcher_fn = getattr(sponsor_matching, "match_sponsors", None)
    if matcher_fn is None:
        log.warning(
            "Sponsor enrichment unavailable: sponsor_matching.match_sponsors not found; "
            "skipping --enrich (records keep null enrichment fields)"
        )
        return None
    return matcher_fn
