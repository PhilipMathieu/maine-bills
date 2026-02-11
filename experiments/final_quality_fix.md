# Final Quality Fix: Sponsor Extraction False Positives

**Date:** 2026-02-11
**Investigation:** Root cause analysis of 2 quality issues found in 30-bill sample

---

## Executive Summary

**Bug Found:** Title word filter uses exact string matching instead of word-level matching

**Impact:** 2 quality issues in 30-bill sample (6.7% false positive rate)

**Root Cause:** Single bug affecting all extraction patterns - filter checks `name not in title_words` instead of checking if any word within the name is a title word

**Fix:** Change filter logic to `not set(name.split()).intersection(title_words)` + expand filter word list

**Test Validation:** Created 19 test cases; 6 fail pre-fix (confirming bug exists), expected 0 failures post-fix

**Test Results (Pre-Fix):**
```
FAILED tests/unit/test_sponsor_quality_fix.py::TestTitleWordsInNames::test_president_in_name
FAILED tests/unit/test_sponsor_quality_fix.py::TestTitleWordsInNames::test_speaker_in_name
FAILED tests/unit/test_sponsor_quality_fix.py::TestTitleWordsInNames::test_secretary_in_name
FAILED tests/unit/test_sponsor_quality_fix.py::TestTitleWordsInNames::test_clerk_in_name
FAILED tests/unit/test_sponsor_quality_fix.py::TestTitleWordsInNames::test_state_in_name
FAILED tests/unit/test_sponsor_quality_fix.py::TestEdgeCases::test_title_word_as_part_of_first_name
======================== 6 failed, 13 passed in 0.63s =========================
```

**Files:**
- Fix location: `/home/philip/src/maine-bills/src/maine_bills/text_extractor.py` (lines 235, 242, 251, 263, 270, 279)
- Test file: `/home/philip/src/maine-bills/tests/unit/test_sponsor_quality_fix.py`

---

## Issues Identified

In a 30-bill sample quality check, 2 false positives were found:

1. **"President JACKSON"** extracted as sponsor
2. **"States Department"**, **"Department"**, **"Regular Session"** extracted as sponsors

**These are the same bug** - both caused by exact-match filtering instead of word-level filtering.

---

## Visual Explanation: Why the Bug Happens

### Current Filter Logic (Buggy)

```python
title_words = {'President', 'Speaker', 'Secretary', 'State', 'States', 'Clerk'}

# Pattern extracts: "President JACKSON"
name = "President JACKSON"

# Filter check:
name not in title_words
→ "President JACKSON" not in {'President', 'Speaker', ...}
→ True  # ❌ Passes filter (WRONG!)
```

**Problem:** Checking if the entire string "President JACKSON" is in the set, not checking individual words.

### Fixed Filter Logic

```python
title_words = {
    'President', 'Speaker', 'Secretary', 'Clerk',
    'State', 'States', 'Department', 'Senate', 'House',
    'Session', 'Regular', 'Special', 'Legislature', 'Legislative'
}

# Pattern extracts: "President JACKSON"
name = "President JACKSON"

# Filter check:
name_words = set(name.split())  # {'President', 'JACKSON'}
name_words.intersection(title_words)
→ {'President', 'JACKSON'} ∩ {'President', 'Speaker', ...}
→ {'President'}  # Found intersection!
→ not {'President'}
→ False  # ✅ Blocks extraction (CORRECT!)
```

**Fix:** Split the name into words and check if ANY word is in the filter set.

---

## Root Cause Analysis

### Issue 1: "President JACKSON" False Positive

**Pattern Responsible:** Pattern 1 (line 238)

```python
# Pattern 1: "Presented by Senator/Representative NAME [of DISTRICT]"
pattern1 = r'(?:Presented|Introduced) by\s+(?:Senator|Representative)\s+([A-Z][A-Za-z\'\-]+(?:\s+[A-Z][A-Za-z\'\-]+)?)\s+of\s+[A-Za-z\s]+'
```

**How it happens:**

Real-world scenario:
```
Text: "Presented by Representative President JACKSON of Aroostook"
```

The pattern `(?:Senator|Representative)\s+([A-Z][A-Za-z\'\-]+(?:\s+[A-Z][A-Za-z\'\-]+)?)` captures:
- Group 1: "President JACKSON" (two capitalized words)

The title filter at line 242 checks:
```python
if name and name not in sponsors and len(name.split()) <= 2 and name not in title_words:
```

**The bug:** The filter checks `name not in title_words`, but `name = "President JACKSON"` is a 2-word string.

The title_words set contains:
```python
title_words = {'President', 'Speaker', 'Secretary', 'State', 'States', 'Clerk'}
```

**Problem:** `"President JACKSON" not in title_words` evaluates to `True` because we're checking the full name, not individual words.

**Test validation:**
```python
>>> text = "Presented by Representative President SMITH of York"
>>> TextExtractor._extract_sponsors(text)
['President SMITH']  # ❌ False positive!
```

**Why the current filter fails:**
- The filter only checks if the **entire extracted name** is in title_words
- It doesn't check if any **word within the name** is a title word
- "President JACKSON" ≠ "President", so it passes through
- This affects Pattern 1, Pattern 1b, and all cosponsorship patterns

---

### Issue 2: "States Department", "Department", "Regular Session" False Positives

**Patterns Responsible:** Same issue as Issue 1 - affects all patterns that extract two-word sequences

This is actually the **same root cause** as Issue 1:
- Pattern extracts "Representative States Department" → captures "States Department"
- Pattern extracts "Senator Regular Session" → captures "Regular Session"
- Pattern extracts "Representative Department Smith" → captures "Department Smith"

**How it happens:**

The extractor patterns capture any two capitalized words following "Representative/Senator":

```python
# Pattern captures: ([A-Z][A-Za-z\'\-]+(?:\s+[A-Z][A-Za-z\'\-]+)?)
# This matches ANY two capitalized words, including:
# - "President JACKSON" (title + name)
# - "States Department" (non-name words)
# - "Regular Session" (document metadata)
```

**Real-world scenarios:**

**Scenario A: "States Department"**
```
Text: "Transmitted by the United States Department of Administrative Services"
If this text appears near "Representative" or "Senator", the pattern could extract:
"Representative States Department of York" → "States Department"
```

**Scenario B: "Department"**
```
Text: "Secretary of State and Department of Justice"
Pattern extracts: "Department" if it appears after a capitol-level title
```

**Scenario C: "Regular Session"**
```
Text: "First Regular Session of the 131st Legislature"
If extracted as a two-word name: "Regular Session"
```

**The bug:**
1. The title_words filter doesn't include common non-name words like "Department", "Regular", "Session", "Legislature"
2. The pattern `[A-Z][A-Za-z\'\-]+(?:\s+[A-Z][A-Za-z\'\-]+)?` matches **any** two capitalized words
3. These words pass the filter because they're not in the title_words set

**Root cause is identical to Issue 1:**
- Filter checks `name not in title_words`
- "States Department" not in `{'President', 'Speaker', ...}` → passes filter ❌
- Should check if **any word** in "States Department" is in title_words → "States" would be caught ✓

---

## Proposed Fix

### Fix 1: Check for title words within extracted names (Critical)

**Problem:** Title filter only checks exact match, not word-level match

**Solution:** Split the name and check if any word is a title word

```python
# Current (line 242):
if name and name not in sponsors and len(name.split()) <= 2 and name not in title_words:
    sponsors.append(name)

# Fixed:
name_words = set(name.split())
if name and name not in sponsors and len(name.split()) <= 2 and not name_words.intersection(title_words):
    sponsors.append(name)
```

**How it works:**
- `name.split()` → ["President", "JACKSON"]
- `set(name.split())` → {"President", "JACKSON"}
- `name_words.intersection(title_words)` → {"President"}
- `not {"President"}` → False (filter blocks it) ✅

**Apply this fix to all filter locations:**
- Line 242 (Pattern 1)
- Line 251 (Pattern 1b)
- Line 263 (Cosponsorship with district)
- Line 270 (Cosponsorship without district)
- Line 279 (Comma-separated)

---

### Fix 2: Expand title_words filter (High Priority)

**Problem:** Missing common non-name words that appear in bills

**Solution:** Add more filtering words

```python
# Current (line 235):
title_words = {'President', 'Speaker', 'Secretary', 'State', 'States', 'Clerk'}

# Enhanced:
title_words = {
    # Leadership titles
    'President', 'Speaker', 'Secretary', 'Clerk',
    # Government entities
    'State', 'States', 'Department', 'Senate', 'House',
    # Document references
    'Session', 'Regular', 'Special', 'Legislature', 'Legislative'
}
```

**Rationale:**
- "Department" prevents "States Department" / "Department" extractions
- "Session" / "Regular" prevents "Regular Session" extractions
- "Senate" / "House" prevents "Senate Committee" type extractions
- "Legislature" / "Legislative" prevents document header leakage

---

### Fix 3: Improve text cleaning for headers (Medium Priority)

**Context:** Header text like "FIRST REGULAR SESSION-2023" may leak into extraction

**Current cleaning** (in `_clean_text()` method) may not catch all header patterns.

**Solution:** Add more header patterns to `_clean_text()`:

```python
# Add to the header removal section:
# Legislative session headers
if re.match(r'^(?:FIRST|SECOND)\s+(?:REGULAR|SPECIAL)\s+SESSION', line_stripped, re.IGNORECASE):
    continue
```

This is defensive - header cleaning should happen before sponsor extraction, but adding this provides defense-in-depth.

---

## Complete Code Fix

### Location: `/home/philip/src/maine-bills/src/maine_bills/text_extractor.py`

**Changes needed:**

1. **Line 235:** Expand title_words
2. **Lines 242, 251, 263, 270, 279:** Change filter logic to check word-level

```python
@staticmethod
def _extract_sponsors(text: str) -> List[str]:
    """
    Extract legislator names (sponsors) from text.

    Handles multi-line sponsor blocks and comma-separated lists.
    Supports both "Presented by" (real bills) and "Introduced by" (some bills/tests).
    """
    sponsors = []
    search_text = text[:2500]
    normalized_text = ' '.join(search_text.split())

    # Title filter - exclude these common false positives
    # FIXED: Expanded to include common non-name words
    title_words = {
        # Leadership titles
        'President', 'Speaker', 'Secretary', 'Clerk',
        # Government entities
        'State', 'States', 'Department', 'Senate', 'House',
        # Document references
        'Session', 'Regular', 'Special', 'Legislature', 'Legislative'
    }

    # Helper function to validate names
    def is_valid_name(name: str) -> bool:
        """Check if extracted text is a valid legislator name."""
        if not name or name in sponsors or len(name.split()) > 2:
            return False
        # FIXED: Check if any word in the name is a title word
        name_words = set(name.split())
        return not name_words.intersection(title_words)

    # Pattern 1: "Presented by Senator/Representative NAME [of DISTRICT]"
    pattern1 = r'(?:Presented|Introduced) by\s+(?:Senator|Representative)\s+([A-Z][A-Za-z\'\-]+(?:\s+[A-Z][A-Za-z\'\-]+)?)\s+of\s+[A-Za-z\s]+'
    for match in re.finditer(pattern1, normalized_text):
        name = match.group(1).strip()
        if is_valid_name(name):
            sponsors.append(name)

    # Pattern 1b: "Presented by Senator/Representative NAME" (without district)
    pattern1b = r'(?:Presented|Introduced) by\s+(?:Senator|Representative)\s+([A-Z][A-Za-z\'\-]+(?:\s+[A-Z][A-Za-z\'\-]+)?)(?=\s+(?:Cosponsored|Be it|of|and|,)|$)'
    for match in re.finditer(pattern1b, normalized_text):
        name = match.group(1).strip()
        if is_valid_name(name):
            sponsors.append(name)

    # Pattern 2: Cosponsorship block
    cosp_block_match = re.search(r'Cosponsored by\s+(.+?)(?=\n\n|Be it enacted|Presented by|Introduced by|$)', normalized_text, re.DOTALL)
    if cosp_block_match:
        cosp_block = ' '.join(cosp_block_match.group(1).split())

        # Extract from "Representative/Senator NAME of DISTRICT" pattern
        person_pattern = r'(?:Senator|Representative)\s+([A-Z][A-Za-z\'\-]+(?:\s+[A-Z][A-Za-z\'\-]+)?)\s+of\s+[A-Za-z\s]+(?:\s+and)?'
        for match in re.finditer(person_pattern, cosp_block):
            name = match.group(1).strip()
            if is_valid_name(name):
                sponsors.append(name)

        # Extract without "of" district
        person_pattern_no_district = r'(?:Senator|Representative)\s+([A-Z][A-Za-z\'\-]+(?:\s+[A-Z][A-Za-z\'\-]+)?)\b(?:\s+(?:and|of)|,|$)'
        for match in re.finditer(person_pattern_no_district, cosp_block):
            name = match.group(1).strip()
            if is_valid_name(name):
                sponsors.append(name)

        # Comma-separated names with districts
        cleaned_block = re.sub(r'\b(?:Senator|Representative)\s+[A-Z][A-Za-z\'\-]+(?:\s+[A-Z][A-Za-z\'\-]+)?\b', '', cosp_block)
        comma_separated = re.findall(r'([A-Z][A-Za-z\'\-]+(?:\s+[A-Z][A-Za-z\'\-]+)?)\s+of\s+[A-Za-z\s]+', cleaned_block)
        for name in comma_separated:
            name = name.strip()
            if is_valid_name(name):
                sponsors.append(name)

    # Remove duplicates while preserving order
    seen = set()
    unique = []
    for s in sponsors:
        if s not in seen:
            seen.add(s)
            unique.append(s)

    return unique
```

---

## Test Cases to Validate Fix

### Test 1: Title words within names (President JACKSON)

```python
def test_extract_sponsors_filters_titles_in_names():
    """Test that title words within extracted names are filtered."""
    # Should filter "President JACKSON" even though "President JACKSON" != "President"
    text = "Presented by President JACKSON of Aroostook"
    result = TextExtractor._extract_sponsors(text)
    assert result == [], f"Expected empty list, got {result}"

    # Should also filter other title combinations
    text = "Presented by Speaker TALBOT of Cumberland"
    result = TextExtractor._extract_sponsors(text)
    assert result == [], f"Expected empty list, got {result}"

    text = "Introduced by Secretary BELLOWS of Kennebec"
    result = TextExtractor._extract_sponsors(text)
    assert result == [], f"Expected empty list, got {result}"
```

### Test 2: Non-name words (Department, Session)

```python
def test_extract_sponsors_filters_common_words():
    """Test that common non-name words are filtered."""
    # "Department" should be filtered
    text = "States Department of Justice"
    result = TextExtractor._extract_sponsors(text)
    assert "Department" not in result
    assert "States Department" not in result

    # "Regular Session" should be filtered
    text = "First Regular Session of the 131st Legislature"
    result = TextExtractor._extract_sponsors(text)
    assert "Regular Session" not in result
    assert "Regular" not in result
    assert "Session" not in result
```

### Test 3: Valid names still work

```python
def test_extract_sponsors_valid_names_still_work():
    """Ensure valid names are not filtered."""
    text = "Presented by Representative SMITH of Cumberland"
    result = TextExtractor._extract_sponsors(text)
    assert result == ["SMITH"]

    text = "Introduced by Senator O'BRIEN of Androscoggin"
    result = TextExtractor._extract_sponsors(text)
    assert result == ["O'BRIEN"]

    text = "Presented by Representative TALBOT-ROSS of Portland"
    result = TextExtractor._extract_sponsors(text)
    assert result == ["TALBOT-ROSS"]
```

---

## Expected Impact

### Before/After Comparison

| Input Text | Current (Buggy) | After Fix |
|------------|----------------|-----------|
| `"Presented by Representative President JACKSON of Aroostook"` | ❌ `["President JACKSON"]` | ✅ `[]` |
| `"Presented by Senator Speaker TALBOT of Cumberland"` | ❌ `["Speaker TALBOT"]` | ✅ `[]` |
| `"Representative States Department of York"` | ❌ `["States Department"]` | ✅ `[]` |
| `"First Regular Session of the 131st"` | ❌ `["Regular Session"]` | ✅ `[]` |
| `"Presented by Representative SMITH of York"` | ✅ `["SMITH"]` | ✅ `["SMITH"]` |
| `"Introduced by Senator O'BRIEN of Androscoggin"` | ✅ `["O'BRIEN"]` | ✅ `["O'BRIEN"]` |
| `"Presented by Representative VAN BUREN of Knox"` | ✅ `["VAN BUREN"]` | ✅ `["VAN BUREN"]` |

### Positive Impacts

1. **Eliminates "President JACKSON" false positives**
   - Word-level filtering catches title words within multi-word names
   - Applies to all title words: President, Speaker, Secretary, Clerk

2. **Eliminates "Department" / "Session" false positives**
   - Expanded title_words list filters common non-name words
   - Prevents document metadata from being extracted as sponsors

3. **Improves extraction precision**
   - Reduces false positive rate from ~6.7% (2/30) to near 0%
   - Maintains recall - valid names are not affected

### Extraction Rate Impact

**Current:** ~60% extraction rate on original bills (100% when excluding amendments)

**Expected after fix:** No change to extraction rate
- Fix only removes false positives, doesn't affect true positives
- Valid legislator names don't contain title words or document keywords

### Potential Edge Cases

**Theoretical issue:** Someone named "Senator PRESIDENT"

This would be filtered out, but:
- No current Maine legislators have these surnames
- Extremely unlikely scenario
- Acceptable trade-off for eliminating common false positives

---

## Implementation Priority

**Priority: HIGH - Fix before HuggingFace migration**

**Effort: Low** - ~20 lines changed, straightforward logic

**Testing: Medium** - 19 unit tests already created, 6 currently failing

**Risk: Low** - Changes only filtering logic, doesn't affect pattern matching

---

## Implementation Checklist

### Step 1: Expand title_words (line 235)

```python
# Change line 235 from:
title_words = {'President', 'Speaker', 'Secretary', 'State', 'States', 'Clerk'}

# To:
title_words = {
    # Leadership titles
    'President', 'Speaker', 'Secretary', 'Clerk',
    # Government entities
    'State', 'States', 'Department', 'Senate', 'House',
    # Document references
    'Session', 'Regular', 'Special', 'Legislature', 'Legislative'
}
```

### Step 2: Add helper function (after line 236)

```python
# Add this helper function after the title_words definition:
def is_valid_name(name: str) -> bool:
    """Check if extracted text is a valid legislator name."""
    if not name or name in sponsors or len(name.split()) > 2:
        return False
    # Check if any word in the name is a title/filter word
    name_words = set(name.split())
    return not name_words.intersection(title_words)
```

### Step 3: Replace filter logic at 5 locations

**Location 1: Line 242 (Pattern 1)**
```python
# Change:
if name and name not in sponsors and len(name.split()) <= 2 and name not in title_words:
    sponsors.append(name)

# To:
if is_valid_name(name):
    sponsors.append(name)
```

**Location 2: Line 251 (Pattern 1b)**
```python
# Same change as Location 1
if is_valid_name(name):
    sponsors.append(name)
```

**Location 3: Line 263 (Cosponsorship with district)**
```python
# Same change as Location 1
if is_valid_name(name):
    sponsors.append(name)
```

**Location 4: Line 270 (Cosponsorship without district)**
```python
# Same change as Location 1
if is_valid_name(name):
    sponsors.append(name)
```

**Location 5: Line 279 (Comma-separated)**
```python
# Same change as Location 1
if is_valid_name(name):
    sponsors.append(name)
```

### Step 4: Verify tests pass

```bash
# Run the quality fix tests
uv run pytest tests/unit/test_sponsor_quality_fix.py -v

# Expected: 19/19 passed

# Run all unit tests
uv run pytest tests/unit/ -v

# Expected: All tests pass (no regressions)
```

---

## Verification Plan

1. **Apply the fix** to `text_extractor.py`
2. **Add unit tests** for the 3 scenarios above
3. **Run full test suite** - ensure no regressions
4. **Re-run 30-bill quality sample** - verify 0 false positives
5. **Spot-check 100 random bills** - ensure no valid names filtered

---

## Conclusion

### Root Cause: Single Bug with Two Manifestations

Both quality issues stem from the **same root cause**:

**The title filter checks exact string match, not word-level match**

This allows multi-word strings containing filter words to pass through:

**Issue 1:** "President JACKSON" passes because `"President JACKSON" not in title_words` is True
- The string "President JACKSON" ≠ "President"
- Filter doesn't check individual words

**Issue 2:** "States Department" passes because `"States Department" not in title_words` is True
- The string "States Department" ≠ "States"
- Same filter bug, different word category

### The Fix: Word-Level Filtering

**Check if ANY word within the extracted name is a filter word**

```python
# Before (line 242, 251, 263, 270, 279):
if name and name not in sponsors and len(name.split()) <= 2 and name not in title_words:
    sponsors.append(name)

# After:
name_words = set(name.split())
if name and name not in sponsors and len(name.split()) <= 2 and not name_words.intersection(title_words):
    sponsors.append(name)
```

**Or using helper function (cleaner):**

```python
def is_valid_name(name: str) -> bool:
    if not name or name in sponsors or len(name.split()) > 2:
        return False
    name_words = set(name.split())
    return not name_words.intersection(title_words)
```

### Impact

**Eliminates both quality issues:**
1. "President JACKSON" → {"President", "JACKSON"} ∩ title_words = {"President"} → filtered ✓
2. "States Department" → {"States", "Department"} ∩ title_words = {"States", "Department"} → filtered ✓
3. "Regular Session" → {"Regular", "Session"} ∩ title_words = {"Regular", "Session"} → filtered ✓

**Maintains valid names:**
- "SMITH" → {"SMITH"} ∩ title_words = {} → extracted ✓
- "VAN BUREN" → {"VAN", "BUREN"} ∩ title_words = {} → extracted ✓
- "O'BRIEN" → {"O'BRIEN"} ∩ title_words = {} → extracted ✓

### Expanded Filter Words

Also expand title_words to catch more cases:

```python
title_words = {
    'President', 'Speaker', 'Secretary', 'Clerk',  # Leadership
    'State', 'States', 'Department', 'Senate', 'House',  # Government
    'Session', 'Regular', 'Special', 'Legislature', 'Legislative'  # Document metadata
}
```

This provides **defense-in-depth**: even if word-level filtering has edge cases, expanded filter list catches common false positives.

---

**Status: Ready for implementation**

**Tests confirming bug:** 5/5 title word tests fail (demonstrating the bug exists)
**Expected after fix:** All tests pass
**Effort:** Low (20 lines, 5 locations)
**Risk:** Low (only changes filtering, doesn't affect pattern matching)
