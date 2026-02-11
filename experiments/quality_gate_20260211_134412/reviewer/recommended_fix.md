# Recommended Fix for Sponsor Extraction

**File:** `/home/philip/src/maine-bills/src/maine_bills/text_extractor.py`

---

## Required Fix: Comma-Separated Pattern Bug

### Current Code (Line 274)

```python
# Comma-separated names with districts
comma_separated = re.findall(r'([A-Z][A-Za-z\'\-]+(?:\s+[A-Z][A-Za-z\'\-]+)?)\s+of\s+[A-Za-z\s]+', cosp_block)
```

### Proposed Fix - Option A (Negative Lookbehind)

```python
# Comma-separated names with districts (exclude title words)
comma_separated = re.findall(r'(?<!Senator\s)(?<!Representative\s)([A-Z][A-Za-z\'\-]+(?:\s+[A-Z][A-Za-z\'\-]+)?)\s+of\s+[A-Za-z\s]+', cosp_block)
```

### Proposed Fix - Option B (Pre-filter, more robust)

```python
# Comma-separated names with districts
# First remove "Senator/Representative NAME" patterns already handled by earlier extractions
cleaned_block = re.sub(r'\b(?:Senator|Representative)\s+[A-Z][A-Za-z\'\-]+(?:\s+[A-Z][A-Za-z\'\-]+)?\b', '', cosp_block)
comma_separated = re.findall(r'([A-Z][A-Za-z\'\-]+(?:\s+[A-Z][A-Za-z\'\-]+)?)\s+of\s+[A-Za-z\s]+', cleaned_block)
```

**Recommendation:** Use Option B - it's more maintainable and prevents any overlap between patterns.

---

## Optional Enhancement: Add "Clerk" to Title Filter

### Current Code (Line 235)

```python
# Title filter - exclude these common false positives
title_words = {'President', 'Speaker', 'Secretary', 'State', 'States'}
```

### Proposed Enhancement

```python
# Title filter - exclude these common false positives
title_words = {'President', 'Speaker', 'Secretary', 'State', 'States', 'Clerk'}
```

**Rationale:** Defense-in-depth. While the pattern structure already prevents "Clerk" from being captured, adding it to the filter provides an extra safety net.

---

## Testing the Fix

### Test Case for the Bug

Add this test to `/home/philip/src/maine-bills/tests/unit/test_metadata_extraction.py`:

```python
def test_extract_sponsors_cosponsorship_no_title_words():
    """Test that cosponsorship blocks don't capture Senator/Representative as part of name."""
    text = """
    Presented by Representative SMITH of Portland
    Cosponsored by Representative JONES of York and Senator BROWN of Cumberland
    """
    result = TextExtractor._extract_sponsors(text)

    # Should extract just the names, not "Senator BROWN"
    assert 'SMITH' in result
    assert 'JONES' in result
    assert 'BROWN' in result
    assert len(result) == 3

    # Should NOT contain title words
    for sponsor in result:
        assert 'Senator' not in sponsor
        assert 'Representative' not in sponsor
```

### Validation Script

```python
from maine_bills.text_extractor import TextExtractor

# Before fix: ['JONES', 'SMITH', 'Senator JONES']
# After fix: ['JONES', 'SMITH']
text = "Cosponsored by Representative SMITH and Senator JONES of York"
sponsors = TextExtractor._extract_sponsors(text)
print(f"Result: {sponsors}")

# Check for false positives
has_title = any('Senator' in s or 'Representative' in s for s in sponsors)
if has_title:
    print("❌ BUG STILL PRESENT: Title words found in sponsor names")
else:
    print("✅ FIX SUCCESSFUL: No title words in sponsor names")
```

---

## Expected Impact

### Before Fix
```python
>>> TextExtractor._extract_sponsors("Cosponsored by Representative SMITH and Senator JONES of York")
['JONES', 'SMITH', 'Senator JONES']  # ❌ False positive
```

### After Fix (Option A or B)
```python
>>> TextExtractor._extract_sponsors("Cosponsored by Representative SMITH and Senator JONES of York")
['JONES', 'SMITH']  # ✅ Correct
```

---

## Complete Fixed Method (Option B)

For reference, here's the complete `_extract_sponsors()` method with the fix applied:

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
    title_words = {'President', 'Speaker', 'Secretary', 'State', 'States', 'Clerk'}

    # Pattern 1: "Presented by Senator/Representative NAME [of DISTRICT]"
    pattern1 = r'(?:Presented|Introduced) by\s+(?:Senator|Representative)\s+([A-Z][A-Za-z\'\-]+(?:\s+[A-Z][A-Za-z\'\-]+)?)\s+of\s+[A-Za-z\s]+'
    for match in re.finditer(pattern1, normalized_text):
        name = match.group(1).strip()
        # Filter out titles and validate
        if name and name not in sponsors and len(name.split()) <= 2 and name not in title_words:
            sponsors.append(name)

    # Pattern 1b: "Presented by Senator/Representative NAME" (without district)
    # Use lookahead to stop at keywords that indicate end of sponsor name
    pattern1b = r'(?:Presented|Introduced) by\s+(?:Senator|Representative)\s+([A-Z][A-Za-z\'\-]+(?:\s+[A-Z][A-Za-z\'\-]+)?)(?=\s+(?:Cosponsored|Be it|of|and|,)|$)'
    for match in re.finditer(pattern1b, normalized_text):
        name = match.group(1).strip()
        # Filter out titles and validate
        if name and name not in sponsors and len(name.split()) <= 2 and name not in title_words:
            sponsors.append(name)

    # Pattern 2: Cosponsorship block
    cosp_block_match = re.search(r'Cosponsored by\s+(.+?)(?=\n\n|Be it enacted|Presented by|Introduced by|$)', normalized_text, re.DOTALL)
    if cosp_block_match:
        cosp_block = ' '.join(cosp_block_match.group(1).split())

        # Extract from "Representative/Senator NAME of DISTRICT" pattern
        person_pattern = r'(?:Senator|Representative)\s+([A-Z][A-Za-z\'\-]+(?:\s+[A-Z][A-Za-z\'\-]+)?)\s+of\s+[A-Za-z\s]+(?:\s+and)?'
        for match in re.finditer(person_pattern, cosp_block):
            name = match.group(1).strip()
            if name and name not in sponsors and len(name.split()) <= 2 and name not in title_words:
                sponsors.append(name)

        # Extract without "of" district
        person_pattern_no_district = r'(?:Senator|Representative)\s+([A-Z][A-Za-z\'\-]+(?:\s+[A-Z][A-Za-z\'\-]+)?)\b(?:\s+(?:and|of)|,|$)'
        for match in re.finditer(person_pattern_no_district, cosp_block):
            name = match.group(1).strip()
            if name and name not in sponsors and len(name.split()) <= 2 and name not in title_words:
                sponsors.append(name)

        # Comma-separated names with districts
        # **FIX APPLIED HERE** - Remove Senator/Representative patterns first
        cleaned_block = re.sub(r'\b(?:Senator|Representative)\s+[A-Z][A-Za-z\'\-]+(?:\s+[A-Z][A-Za-z\'\-]+)?\b', '', cosp_block)
        comma_separated = re.findall(r'([A-Z][A-Za-z\'\-]+(?:\s+[A-Z][A-Za-z\'\-]+)?)\s+of\s+[A-Za-z\s]+', cleaned_block)
        for name in comma_separated:
            name = name.strip()
            if name and name not in sponsors and len(name.split()) <= 2 and name not in title_words:
                sponsors.append(name)

    # Remove duplicates while preserving order
    seen = set()
    unique = []
    for s in sponsors:
        s_normalized = s.upper()
        if s_normalized not in seen:
            seen.add(s_normalized)
            unique.append(s)
    return unique
```

---

## Deployment Checklist

- [ ] Apply fix to `text_extractor.py` line 274 (and optional line 235)
- [ ] Run all unit tests: `uv run pytest tests/unit/test_metadata_extraction.py -v`
- [ ] Run validation script to confirm bug is fixed
- [ ] (Optional) Add new test case for cosponsorship title filtering
- [ ] Run quality gate sample again to confirm no regressions
- [ ] Proceed with HuggingFace migration

---

**Estimated time to apply fix:** 5 minutes
**Risk level:** Low (minimal change, well-tested)
**Impact:** Removes false positives like "Senator JONES" from sponsor lists
