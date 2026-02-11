# Extraction Analysis - Bill 131-LD-1693

## Issues Identified

### 1. Bill ID Extraction Failure

**Expected:** "131-LD-1693"
**Got:** `null`
**Confidence Impact:** Major (this is a required field)

**Root Cause:**
The baseline text contains:
- Session: `131st MAINE LEGISLATURE` (ordinal format)
- LD Number: `No. 1693` (without padding)

The current `_extract_bill_id()` method has two issues:
1. The primary regex pattern `r'(\d{2,3})-LD-(\d{3,4})'` fails because the bill ID never appears in the combined format "131-LD-1693" in the document - it's split across separate fields.
2. The fallback pattern searches for "No." but doesn't handle the ordinal session format properly when the extraction needs to reconstruct the ID.

The document clearly shows:
```
131st MAINE LEGISLATURE
...
No. 1693
```

**Proposed Fix:**
Enhance the fallback logic to:
- More robustly extract the session from ordinal format (131st, 132nd, etc.)
- Extract LD number from "No. XXXX" pattern with better handling
- Ensure proper zero-padding of LD numbers (1693 → 1693, no padding needed for 4+ digits)
- Verify both components exist before returning

### 2. Session Number Not Extracted

**Expected:** "131" (from "131st MAINE LEGISLATURE")
**Got:** `null`
**Confidence Impact:** Major (required field)

**Root Cause:**
The `_extract_session()` method has the pattern `r'(\d{2,3})(?:st|nd|rd|th)\s+MAINE\s+LEGISLATURE'`, which should match "131st MAINE LEGISLATURE". However, there's a whitespace issue in the raw text - there appear to be extra spaces or newlines between the session line and the legislature keywords.

Looking at the raw text:
```
131st MAINE LEGISLATURE
FIRST SPECIAL SESSION-2023
```

The pattern should work, but the implementation may not be handling line boundaries correctly. The regex might need to account for line breaks and multiple spaces.

**Proposed Fix:**
- Preprocess text to normalize whitespace when searching for session
- Replace newlines and multiple spaces with single space before pattern matching
- Test the session extraction specifically on the first 1000 characters where this always appears

### 3. Sponsors Not Extracted

**Expected:**
- Primary sponsor: "RAFFERTY" (Senator from York)
- Cosponsors: "GERE" (Representative from Kennebunkport), "SAYRE" (Representative from Kennebunk)
**Got:** `[]` (empty list)
**Confidence Impact:** Minor-to-Moderate (optional field but frequently available)

**Root Cause:**
The document shows:
```
Presented by Senator RAFFERTY of York.
Cosponsored by Representative GERE of Kennebunkport and
Representative: SAYRE of Kennebunk.
```

The sponsor extraction patterns fail because:
1. Pattern 1 looks for "Presented by Senator NAME" but the name extraction includes full last names only without accounting for proper formatting. The regex captures but the extractor may be too strict.
2. Pattern 2 for "Cosponsored by" expects the name to follow immediately, but in this document there's a line break after "and" before the next representative.
3. The multi-line cosponsorship pattern (Pattern 3) uses a complex lookahead that may not handle the "and" separator between cosponsors properly.

Key issue: The text has:
```
Cosponsored by Representative GERE of Kennebunkport and
Representative: SAYRE of Kennebunk.
```

The "and" at the end of the line followed by a newline before the next representative breaks the current parsing.

**Proposed Fix:**
- Normalize whitespace in the sponsor search block before pattern matching
- Update Pattern 2 to handle cases where "and" is followed by a newline
- Add explicit handling for multi-line cosponsorship where "and" separates sponsors
- Better parsing of the "Representative:" (with colon) format
- Improve name extraction to capture single names (RAFFERTY, GERE, SAYRE) more reliably

### 4. Committee Not Extracted

**Expected:** "Energy, Utilities and Technology"
**Got:** `null`
**Confidence Impact:** Moderate (useful contextual metadata)

**Root Cause:**
The document contains:
```
Reference to the Committee on Energy, Utilities and Technology suggested and ordered
printed.
```

The current `_extract_committee()` has a pattern that looks for "Reference to the Committee on" but the trailing text handling doesn't account for the phrase continuing across multiple lines. The pattern stops at word boundaries but doesn't handle line breaks effectively.

Additionally, the phrase "suggested and ordered printed" spans into the next line, but the regex is designed to match within a single line context.

**Proposed Fix:**
- Normalize newlines in the search text before pattern matching
- Update the pattern for "Reference to the Committee on" to be more greedy
- Ensure the negative lookahead for trailing markers works across line boundaries
- Test specifically for the "suggested and ordered printed" terminator

### 5. Introduced Date Not Extracted

**Expected:** "2023-04-18" (April 18, 2023 from "In Senate, April 18, 2023")
**Got:** `null`
**Confidence Impact:** Minor-to-Moderate (contextual metadata)

**Root Cause:**
The document shows:
```
In Senate, April 18, 2023
```

The current date extraction pattern `r'(January|February|...|December|Jan|Feb|...)\s+(\d{1,2}),?\s+(\d{4})'` should match "April 18, 2023". However:
1. The search is limited to the first 2000 characters, and the date is well within that range.
2. The pattern explicitly looks for the month name first, which is correct.
3. The real issue is likely that the pattern is found but in a context that shouldn't be processed (e.g., it might be finding dates in timestamps or other metadata first).

Actually, reviewing the pattern more carefully: `r'(January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2}),?\s+(\d{4})'`

This pattern should match "April 18, 2023". The issue is that "In Senate, April 18, 2023" has a comma after "Senate" before "April", which shouldn't affect the pattern.

**Proposed Fix:**
- Debug by testing the date pattern directly on the first 2000 characters
- The pattern itself appears sound; the issue may be in how the date is being extracted or validated
- Consider adding explicit context checking (e.g., ensure date follows "In Senate," or "In House,")
- Make sure the date parsing doesn't encounter ValueError from invalid months

---

## Summary of Required Changes

**Methods to improve:**
1. `_extract_bill_id()` - Fix fallback logic for reconstructing ID from components
2. `_extract_session()` - Handle whitespace normalization in ordinal format detection
3. `_extract_sponsors()` - Improve multi-line sponsor parsing, handle "and" separators
4. `_extract_committee()` - Normalize whitespace before pattern matching
5. `_extract_date()` - Debug and potentially add context-aware date extraction

**Shared improvement:** Normalize whitespace in search text before applying regex patterns. This will handle line breaks and multiple spaces that can interfere with pattern matching in multi-line documents.

**Expected outcome:** All five failing metadata fields should extract correctly, bringing confidence score from 0.78 to approximately 0.95+ (assuming good extraction quality).
