# Extraction Comparison - Baseline vs. Improved

## Metadata Fields Comparison

### 1. Bill ID

**Baseline:**
```
null
```

**Improved:**
```
"131-LD-1693"
```

**Impact:** CRITICAL - Bill ID is a required identifier field
**Root Cause Fixed:** The improved `_extract_bill_id()` now normalizes whitespace and properly matches the "No. 1693" pattern combined with "131st MAINE LEGISLATURE"

---

### 2. Session Number

**Baseline:**
```
null
```

**Improved:**
```
"131"
```

**Impact:** CRITICAL - Session is required for organizing bills
**Root Cause Fixed:** The improved `_extract_session()` normalizes whitespace before searching for ordinal format, allowing it to match "131st MAINE LEGISLATURE" even with line breaks

---

### 3. Sponsors

**Baseline:**
```
[]
```

**Improved:**
```
[
  "RAFFERTY",
  "GERE",
  "SAYRE"
]
```

**Impact:** IMPORTANT - Sponsors are key metadata for legislative tracking
**Root Cause Fixed:** The improved `_extract_sponsors()` now:
- Normalizes whitespace to handle "Presented by Senator RAFFERTY of York."
- Properly parses multi-line cosponsorship with "and" separator
- Handles "Representative:" with colon format
- Increased search window to 2500 chars

---

### 4. Introduced Date

**Baseline:**
```
null
```

**Improved:**
```
"2023-04-18"
```

**Impact:** IMPORTANT - Date metadata is valuable for historical tracking
**Root Cause Fixed:** The improved `_extract_date()` now:
- Normalizes whitespace before pattern matching
- Updated regex to handle optional "In Senate," prefix
- Properly parses "April 18, 2023" format
- Increased search window to 2500 chars

---

### 5. Committee

**Baseline:**
```
null
```

**Improved:**
```
"Energy, Utilities and Technology"
```

**Impact:** IMPORTANT - Committee assignment is key for bill workflow tracking
**Root Cause Fixed:** The improved `_extract_committee()` now:
- Normalizes whitespace to handle multi-line patterns
- Pattern now properly handles commas within committee names
- Updated lookahead to delimit on "suggested" keyword
- Correctly extracts full "Energy, Utilities and Technology" name

---

### 6. Title

**Baseline:**
```
"An Act to Amend the Kennebunk Sewer District Charter"
```

**Improved:**
```
"An Act to Amend the Kennebunk Sewer District Charter"
```

**Status:** UNCHANGED (already extracted correctly)

---

### 7. Amended Code References

**Baseline:**
```
[]
```

**Improved:**
```
[]
```

**Status:** UNCHANGED (none found, as expected - this bill has general amendments only)

---

### 8. Body Text

**Baseline:**
```
[3635 characters, includes boilerplate]
MAINE STATE LEGISLATURE
The following document is provided by the
LAW AND LEGISLATIVE DIGITAL LIBRARY
...
[includes institutional headers and library boilerplate]
```

**Improved:**
```
[3451 characters, cleaner]
Be it enacted by the People of the State of Maine as follows:
...
[properly cleaned, starts with actual legislative content]
```

**Status:** IMPROVED - Cleaner extraction with better boilerplate removal

---

## Confidence Score Analysis

| Metric | Baseline | Improved |
|--------|----------|----------|
| extraction_confidence | 0.7836 | 0.7836 |
| Metadata fields extracted | 1 of 7 (14%) | 6 of 7 (86%) |
| Critical fields (bill_id, session) | 0 of 2 (0%) | 2 of 2 (100%) |
| Optional fields extracted | 0 of 5 (0%) | 4 of 5 (80%) |

**Note:** Confidence score remains the same because it's calculated independently in `_estimate_confidence()` based on text length and keywords. The metadata extraction improvements don't affect this scoring mechanism directly.

---

## Pattern Matching Improvements

### Whitespace Normalization
**Before:** Regex patterns failed on multi-line text
```
"131st MAINE\nLEGISLATURE" → NO MATCH
"No.\n1693" → NO MATCH
```

**After:** Whitespace normalization enables successful matching
```
"131st MAINE LEGISLATURE" → MATCH ✓
"No. 1693" → MATCH ✓
```

### Committee Name Handling
**Before:** Pattern stopped at first ","
```
"Energy, Utilities and Technology suggested" → "Energy" only
```

**After:** Pattern properly delimits on keywords
```
"Energy, Utilities and Technology suggested" → "Energy, Utilities and Technology" ✓
```

### Multi-line Sponsor Parsing
**Before:** Line breaks broke the pattern
```
"Cosponsored by Representative GERE of Kennebunkport and\nRepresentative: SAYRE" → NO MATCH
```

**After:** Normalized whitespace allows proper parsing
```
"Cosponsored by Representative GERE of Kennebunkport and Representative: SAYRE" → MATCH ✓
```

---

## Summary

The proposed improvements successfully fix all five previously-failing extraction methods. The key innovation is **whitespace normalization** (`' '.join(text.split())`) which normalizes multi-line text before regex matching, allowing patterns designed for single-line text to work robustly across PDFs with varying formatting.

**Extraction Success Rate:** 14% → 86% (6 of 7 fields now extracted)
