# Sponsor Extraction Fix + OpenStates Validation

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Eliminate false-positive sponsor extraction (51 garbage names like "Town", "University", "Board") by tightening regex patterns and adding optional OpenStates validation.

**Architecture:** Two-layer fix: (1) Remove the overly permissive comma-separated fallback regex in `_extract_sponsors()` that captures any `NAME of PLACE` without requiring a Senator/Representative prefix. (2) Add a `validate_sponsors()` function that filters extracted sponsors against a known-legislator set, usable as a post-processing step.

**Tech Stack:** Python, regex, existing test infrastructure. OpenStates JSON cached locally (already fetched in experiment).

---

### Task 1: Add failing tests for the garbage sponsor cases

**Files:**
- Modify: `tests/unit/test_sponsor_quality_fix.py`

**Step 1: Write failing tests**

Add a new test class that reproduces the actual false positives from the experiment:

```python
class TestCommaSeparatedFalsePositives:
    """The comma-separated fallback regex captures 'NAME of PLACE' without
    requiring Senator/Representative prefix, producing garbage sponsors."""

    def test_town_of_not_extracted(self):
        """'Town of Brunswick' should not produce 'Town' as a sponsor."""
        text = """
        Presented by Representative SMITH of Cumberland
        Cosponsored by Senator JONES of York, Town of Brunswick
        """
        result = TextExtractor._extract_sponsors(text)
        assert "Town" not in result
        assert "SMITH" in result
        assert "JONES" in result

    def test_university_of_not_extracted(self):
        """'University of Maine' should not produce 'University' as a sponsor."""
        text = """
        Presented by Representative SMITH of Cumberland
        Cosponsored by Senator JONES of York, University of Maine
        """
        result = TextExtractor._extract_sponsors(text)
        assert "University" not in result

    def test_board_of_not_extracted(self):
        """'Board of Education' should not produce 'Board' as a sponsor."""
        text = """
        Presented by Representative SMITH of Cumberland
        Cosponsored by Senator JONES of York, Board of Education
        """
        result = TextExtractor._extract_sponsors(text)
        assert "Board" not in result

    def test_american_society_not_extracted(self):
        """'American Society of Civil Engineers' should not produce 'American Society'."""
        text = """
        Presented by Representative SMITH of Cumberland
        Cosponsored by Senator JONES of York, American Society of Civil Engineers
        """
        result = TextExtractor._extract_sponsors(text)
        assert "American Society" not in result

    def test_national_association_not_extracted(self):
        text = """
        Presented by Representative SMITH of Cumberland
        Cosponsored by Senator JONES of York, National Association of Counties
        """
        result = TextExtractor._extract_sponsors(text)
        assert "National Association" not in result

    def test_finance_authority_not_extracted(self):
        text = """
        Presented by Representative SMITH of Cumberland
        Cosponsored by Senator JONES of York, Finance Authority of Maine
        """
        result = TextExtractor._extract_sponsors(text)
        assert "Finance Authority" not in result

    def test_generic_words_not_extracted(self):
        """Words like 'Justices', 'Membership', 'Resources' etc should never be sponsors."""
        text = """
        Presented by Representative SMITH of Cumberland
        Cosponsored by Senator JONES of York, Justices of the Supreme Court,
        Resources of Maine, District of Columbia
        """
        result = TextExtractor._extract_sponsors(text)
        for bad in ["Justices", "Membership", "Resources", "District"]:
            assert bad not in result


class TestHyphenatedNameSpaceBug:
    """Extracted names like 'BEEBE- CENTER' have a space before the hyphen."""

    def test_beebe_center_normalized(self):
        text = "Presented by Representative BEEBE- CENTER of Rockland"
        result = TextExtractor._extract_sponsors(text)
        # Should either extract as "BEEBE-CENTER" (normalized) or "BEEBE- CENTER"
        # but NOT produce two separate entries
        assert len(result) <= 1
        if result:
            assert "BEEBE" in result[0]
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_sponsor_quality_fix.py -v -k "CommaSeparated or HyphenatedNameSpace"`
Expected: Multiple FAIL results

**Step 3: Commit**

```bash
git add tests/unit/test_sponsor_quality_fix.py
git commit -m "test: add failing tests for sponsor false positives from comma-separated fallback"
```

---

### Task 2: Remove the comma-separated fallback regex

**Files:**
- Modify: `src/maine_bills/text_extractor.py:305-312`

**Step 1: Remove the problematic pattern**

The comma-separated fallback (lines 305-312) captures any `NAME of PLACE` without requiring a Senator/Representative prefix. This is the primary source of garbage. Delete it entirely:

```python
# DELETE these lines (305-312):
            # Comma-separated names with districts
            # Remove "Senator/Representative/President/Speaker NAME" patterns first to prevent capturing title words
            cleaned_block = re.sub(r'\b(?:Senator|Representative|President|Speaker)\s+[A-Z][A-Za-z\'\-]+(?:\s+[A-Z][A-Za-z\'\-]+)?\b', '', cosp_block)
            comma_separated = re.findall(r'([A-Z][A-Za-z\'\-]+(?:\s+[A-Z][A-Za-z\'\-]+)?)\s+of\s+[A-Za-z\s]+', cleaned_block)
            for name in comma_separated:
                name = name.strip()
                if is_valid_name(name):
                    sponsors.append(name)
```

**Step 2: Run all sponsor tests**

Run: `uv run pytest tests/unit/test_sponsor_quality_fix.py tests/unit/test_metadata_extraction.py -v`
Expected: All new false-positive tests PASS. Check existing tests still pass.

**Step 3: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: All tests pass

**Step 4: Commit**

```bash
git add src/maine_bills/text_extractor.py
git commit -m "fix: remove comma-separated fallback regex that produced garbage sponsors"
```

---

### Task 3: Fix hyphenated name space bug

**Files:**
- Modify: `src/maine_bills/text_extractor.py`

**Step 1: Add name normalization in `_extract_sponsors`**

Before the dedup step at the end of `_extract_sponsors`, add a normalization pass that collapses `BEEBE- CENTER` → `BEEBE-CENTER`:

```python
        # Normalize hyphenated names with stray spaces (e.g., "BEEBE- CENTER" -> "BEEBE-CENTER")
        sponsors = [re.sub(r'\s*-\s*', '-', s) for s in sponsors]
```

Add this right before the "Remove duplicates while preserving order" block (line 314).

**Step 2: Run tests**

Run: `uv run pytest tests/unit/test_sponsor_quality_fix.py -v -k "HyphenatedNameSpace"`
Expected: PASS

**Step 3: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: All pass

**Step 4: Commit**

```bash
git add src/maine_bills/text_extractor.py
git commit -m "fix: normalize stray spaces in hyphenated sponsor names"
```

---

### Task 4: Add OpenStates sponsor validation utility

**Files:**
- Create: `src/maine_bills/sponsor_validation.py`
- Create: `tests/unit/test_sponsor_validation.py`

**Step 1: Write failing tests**

```python
"""Tests for sponsor validation against known legislator lists."""
from maine_bills.sponsor_validation import validate_sponsors


def test_valid_sponsors_kept():
    known = {"SMITH", "JONES", "BROWN"}
    result = validate_sponsors(["SMITH", "JONES"], known)
    assert result == ["SMITH", "JONES"]


def test_garbage_removed():
    known = {"SMITH", "JONES"}
    result = validate_sponsors(["SMITH", "Town", "University"], known)
    assert result == ["SMITH"]


def test_empty_known_returns_all():
    """If no known legislators provided, return all (no-op)."""
    result = validate_sponsors(["SMITH", "Town"], known_last_names=None)
    assert result == ["SMITH", "Town"]


def test_case_insensitive():
    known = {"SMITH", "TALBOT-ROSS"}
    result = validate_sponsors(["Smith", "TALBOT-ROSS"], known)
    assert result == ["Smith", "TALBOT-ROSS"]


def test_ambiguous_kept():
    """Ambiguous names (multiple legislators) are still valid."""
    known = {"LIBBY", "WHITE"}
    result = validate_sponsors(["LIBBY", "WHITE", "Garbage"], known)
    assert result == ["LIBBY", "WHITE"]
```

**Step 2: Run to verify fail**

Run: `uv run pytest tests/unit/test_sponsor_validation.py -v`
Expected: ImportError

**Step 3: Implement**

```python
"""Validate extracted sponsor names against known legislator lists.

Optional post-processing step: filters extracted sponsors to only include
names that match known legislators (e.g., from OpenStates).
"""


def validate_sponsors(
    sponsors: list[str],
    known_last_names: set[str] | None,
) -> list[str]:
    """Filter sponsors to only those matching known legislators.

    Args:
        sponsors: Extracted sponsor last names
        known_last_names: Set of known legislator last names (uppercase).
            If None, returns sponsors unfiltered (no-op).

    Returns:
        Filtered list preserving original order and casing.
    """
    if known_last_names is None:
        return sponsors
    return [s for s in sponsors if s.upper() in known_last_names]
```

**Step 4: Run tests**

Run: `uv run pytest tests/unit/test_sponsor_validation.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/maine_bills/sponsor_validation.py tests/unit/test_sponsor_validation.py
git commit -m "feat: add sponsor validation utility for filtering against known legislators"
```

---

### Task 5: Verify improvement with experiment notebook

**Files:**
- Modify: `experiments/openstates_sponsor_linking/sponsor_linking.ipynb` (add cells)

**Step 1: Re-scrape session 132 to regenerate parquet with fixed extraction**

Run: `uv run maine-bills -s 132`

Note: This may take a while. Alternatively, just re-run extraction on a subset to validate.

**Step 2: Add notebook cells to compare before/after**

Add cells that:
1. Load the regenerated parquet
2. Re-run the matching analysis
3. Compare unmatched count (should drop from 51 to ~2-5)

**Step 3: Commit**

```bash
git add experiments/openstates_sponsor_linking/sponsor_linking.ipynb
git commit -m "experiment: verify sponsor extraction improvement after regex fix"
```
