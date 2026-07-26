"""Two-pass matching of extracted sponsor names to OpenStates legislators.

Extracted sponsors are surname-style strings (e.g., "DAUGHTRY", "BEEBE-CENTER",
occasionally "Talbot Ross") with no chamber attached — the extraction pipeline
(text_extractor.py) drops the Senator/Representative prefix — so matching runs
without a chamber hint by default, but accepts one when available.

Pass 1: normalized exact last-name match (uppercase, accents stripped, hyphen
spacing collapsed). Multiple distinct roster candidates sharing a last name are
disambiguated by chamber if a hint is given, else marked ambiguous.

Pass 2: rapidfuzz fallback (token_sort_ratio) with a confidence threshold
(default 88). Below threshold = unmatched.
"""

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from rapidfuzz import fuzz

from .openstates import RosterEntry, get_roster

DEFAULT_FUZZY_THRESHOLD = 88.0

METHOD_EXACT = "exact"
METHOD_OCR = "ocr"
METHOD_FUZZY = "fuzzy"
METHOD_AMBIGUOUS = "ambiguous"
METHOD_UNMATCHED = "unmatched"

# Methods that identify exactly one legislator (i.e. produce enrichment values)
MATCHED_METHODS = (METHOD_EXACT, METHOD_OCR, METHOD_FUZZY)


@dataclass(frozen=True)
class MatchResult:
    """Outcome of matching one extracted sponsor string against a roster.

    For "ambiguous" and "unmatched" methods the identity fields are None and
    confidence is 0.0. Confidence is 1.0 for exact matches and the rapidfuzz
    score scaled to 0-1 for fuzzy matches.
    """

    openstates_id: str | None
    canonical_name: str | None
    party: str | None
    district: str | None
    chamber: str | None
    confidence: float
    method: str  # "exact" | "ocr" | "fuzzy" | "ambiguous" | "unmatched"


_NO_MATCH_FIELDS = dict(
    openstates_id=None,
    canonical_name=None,
    party=None,
    district=None,
    chamber=None,
    confidence=0.0,
)


def normalize_name(name: str) -> str:
    """Normalize a name for comparison.

    Uppercases, strips accents (NFKD + drop combining marks), collapses spacing
    around hyphens ("BEEBE- CENTER" -> "BEEBE-CENTER"), and collapses internal
    whitespace.
    """
    decomposed = unicodedata.normalize("NFKD", name)
    ascii_name = "".join(c for c in decomposed if not unicodedata.combining(c))
    ascii_name = ascii_name.upper().strip()
    ascii_name = re.sub(r"\s*-\s*", "-", ascii_name)
    return re.sub(r"\s+", " ", ascii_name)


# Characters a scanner commonly swaps, folded to one representative per class.
# Applied to BOTH the extracted string and roster names, so folding can only
# merge confusable forms — it can never break a match that already worked.
#
# Folding happens AFTER uppercasing, which makes the L/I class case-insensitive.
# That matters: roster names are mixed-case ("Vitelli") while extracted sponsors
# are usually uppercase ("VITELLl"), so folding lowercase "l" alone would treat
# the two sides differently and defeat the purpose.
_OCR_DIGRAPHS = (("RN", "M"), ("VV", "W"))
_OCR_CHARS = str.maketrans(
    {
        "L": "I",
        "1": "I",
        "|": "I",
        "!": "I",
        "0": "O",
        "5": "S",
        "8": "B",
        "6": "G",
        "2": "Z",
        "4": "A",
        "7": "T",
    }
)

OCR_CONFIDENCE = 0.95


def ocr_canonical(name: str) -> str:
    """Normalize a name with OCR-confusable characters folded together.

    Catches single-character substitutions ("GROHOSKl" -> "GROHOSKI") regardless
    of name length, where a similarity ratio would miss short names: at
    threshold 88, one wrong character only clears the bar at 9+ characters.
    """
    canonical = normalize_name(name)
    for digraph, replacement in _OCR_DIGRAPHS:
        canonical = canonical.replace(digraph, replacement)
    return canonical.translate(_OCR_CHARS)


@dataclass
class SponsorMatcher:
    """Matches extracted sponsor strings to a session roster in two passes."""

    roster: list[RosterEntry]
    fuzzy_threshold: float = DEFAULT_FUZZY_THRESHOLD

    # Built in __post_init__
    _by_last_name: dict[str, list[RosterEntry]] = field(init=False, default_factory=dict)
    _by_full_name: dict[str, list[RosterEntry]] = field(init=False, default_factory=dict)
    _by_ocr: dict[str, list[RosterEntry]] = field(init=False, default_factory=dict)

    def __post_init__(self):
        for entry in self.roster:
            self._by_last_name.setdefault(normalize_name(entry.family_name), []).append(entry)
            self._by_full_name.setdefault(normalize_name(entry.name), []).append(entry)
            for value in (entry.family_name, entry.name):
                self._by_ocr.setdefault(ocr_canonical(value), []).append(entry)

    def match(self, sponsor: str, chamber: str | None = None) -> MatchResult:
        """Match one extracted sponsor string.

        Args:
            sponsor: Extracted sponsor name (e.g., "DAUGHTRY", "Beebe- Center")
            chamber: Optional chamber hint ("Senate" or "House") from the
                sponsor prefix, used to disambiguate shared last names

        Returns:
            MatchResult with identity fields, confidence, and method
        """
        normalized = normalize_name(sponsor)
        if not normalized:
            return MatchResult(**_NO_MATCH_FIELDS, method=METHOD_UNMATCHED)

        # Pass 1: exact match on last name, falling back to full name
        # (extraction sometimes yields two-word names like "Talbot Ross")
        candidates = self._by_last_name.get(normalized) or self._by_full_name.get(normalized)
        if candidates:
            return self._resolve_candidates(candidates, chamber)

        # Pass 2: OCR-confusable characters folded (catches short names that a
        # similarity ratio cannot rescue)
        ocr_candidates = self._by_ocr.get(ocr_canonical(sponsor))
        if ocr_candidates:
            return self._resolve_candidates(
                ocr_candidates, chamber, confidence=OCR_CONFIDENCE, method=METHOD_OCR
            )

        # Pass 3: fuzzy fallback
        return self._fuzzy_match(normalized, chamber)

    def match_all(self, sponsors: list[str], chamber: str | None = None) -> list[MatchResult]:
        """Match a bill's sponsor list, preserving order and length."""
        return [self.match(sponsor, chamber) for sponsor in sponsors]

    def _resolve_candidates(
        self,
        candidates: list[RosterEntry],
        chamber: str | None,
        confidence: float = 1.0,
        method: str = METHOD_EXACT,
    ) -> MatchResult:
        """Resolve a candidate set to one entry, using the chamber hint if needed.

        Multiple roster entries for the *same* person (e.g., a representative
        who moved to the Senate mid-biennium) are not ambiguous — the entry
        matching the chamber hint wins, else the first is used.
        """
        if chamber:
            narrowed = [c for c in candidates if c.chamber == chamber]
            if narrowed:
                candidates = narrowed

        distinct_ids = {c.openstates_id for c in candidates}
        if len(distinct_ids) > 1:
            return MatchResult(**_NO_MATCH_FIELDS, method=METHOD_AMBIGUOUS)

        entry = candidates[0]
        return MatchResult(
            openstates_id=entry.openstates_id,
            canonical_name=entry.name,
            party=entry.party,
            district=entry.district,
            chamber=entry.chamber,
            confidence=confidence,
            method=method,
        )

    def _fuzzy_match(self, normalized: str, chamber: str | None) -> MatchResult:
        """Pass 2: best rapidfuzz token_sort_ratio over last and full names."""
        pool = self.roster
        if chamber:
            narrowed = [e for e in pool if e.chamber == chamber]
            if narrowed:
                pool = narrowed

        best_score = 0.0
        best_entries: list[RosterEntry] = []
        for entry in pool:
            score = max(
                fuzz.token_sort_ratio(normalized, normalize_name(entry.family_name)),
                fuzz.token_sort_ratio(normalized, normalize_name(entry.name)),
            )
            if score > best_score:
                best_score = score
                best_entries = [entry]
            elif score == best_score:
                best_entries.append(entry)

        if best_score < self.fuzzy_threshold or not best_entries:
            return MatchResult(**_NO_MATCH_FIELDS, method=METHOD_UNMATCHED)

        return self._resolve_candidates(
            best_entries,
            chamber,
            confidence=round(best_score / 100.0, 4),
            method=METHOD_FUZZY,
        )


_MATCHERS: dict[tuple, SponsorMatcher] = {}


def match_sponsors(
    sponsors: list[str],
    session: int,
    cache_dir: Path | str | None = None,
    fuzzy_threshold: float = DEFAULT_FUZZY_THRESHOLD,
) -> list[MatchResult | None]:
    """Match sponsors for one session; the entry point enrichment.load_matcher uses.

    Builds a SponsorMatcher from the session roster (cached per session for the
    process lifetime; roster fetches cache to disk via openstates.get_roster) and
    returns a list aligned with ``sponsors``. Entries are None where no single
    legislator was identified ("ambiguous"/"unmatched"), so the enrichment
    columns stay null for those sponsors.
    """
    key = (session, str(cache_dir) if cache_dir is not None else None, fuzzy_threshold)
    matcher = _MATCHERS.get(key)
    if matcher is None:
        roster_kwargs = {"cache_dir": Path(cache_dir)} if cache_dir is not None else {}
        roster = get_roster(session, **roster_kwargs)
        matcher = SponsorMatcher(roster, fuzzy_threshold=fuzzy_threshold)
        _MATCHERS[key] = matcher
    results = matcher.match_all(sponsors)
    return [r if r.method in MATCHED_METHODS else None for r in results]
