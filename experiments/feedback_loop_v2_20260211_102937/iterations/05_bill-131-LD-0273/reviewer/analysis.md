# Extraction Analysis - Bill 131-LD-0273

## Issues Identified

### 1. Bill ID Extraction Failure
- **Expected:** "131-LD-0273"
- **Got:** null
- **Root Cause:** The bill ID pattern in the text appears as separate components:
  - Session: "131st MAINE LEGISLATURE" (ordinal format)
  - Legislative Document Number: "No. 273" (without leading zeros)
  - The current `_extract_bill_id()` method correctly falls back to parsing these components separately
  - However, the fallback pattern for document number looks for "Legislative Document|Document No.|No." but the regex `(?:Legislative Document|Document No\.?|No\.?)` is not matching "No. 273" properly due to spacing
  - The zero-padding logic correctly handles converting "273" to "0273", so the issue is in the initial pattern matching

**Proposed Fix:** Improve the regex pattern to more robustly handle the "No." pattern with variable spacing and punctuation.

### 2. Sponsors Not Extracted (Empty List)
- **Expected:** At least ["ZAGER", "BRENNAN", "DODGE", "MILLETT", "MURPHY", "RIELLY", "SARGENT", "PIERCE"]
- **Got:** []
- **Root Cause:** The sponsor extraction patterns are looking for specific markers:
  - "Presented by Representative ZAGER of Portland" is in the text
  - "Cosponsored by Representatives: BRENNAN of Portland..." is in the text
  - The patterns use `[A-Z][A-Za-z\'\-]+` to match names, but in this bill the names appear without district suffixes on some entries
  - The cosponsorship block extends across multiple lines in the raw text, and the pattern boundaries may be cutting off matches
  - Pattern 1b requires whitespace after the name, but the line may end or have "of" immediately

**Proposed Fix:**
1. Relax the pattern matching to handle names that appear without "of" district specification
2. Improve the cosponsorship block detection to handle multiline formats better
3. Add fallback pattern for names in comma-separated lists

### 3. Session Number Not Extracted
- **Expected:** "131"
- **Got:** null
- **Root Cause:** Both the primary pattern (`\d{2,3}-LD-\d{4}`) and the ordinal pattern fail to match
  - The bill ID isn't in the format "131-LD-XXXX" anywhere in isolation
  - The ordinal pattern looks for "131st ... LEGISLATURE" but may have issues with:
    - Line break handling (the text shows "131st MAINE LEGISLATURE" on separate lines in raw_text.txt)
    - The search space is limited to first 1000 chars of normalized text
  - Need to verify the normalization is working correctly

**Proposed Fix:** Ensure the text normalization for session extraction handles the "131st MAINE LEGISLATURE" pattern even with embedded line breaks.

### 4. Committee Extraction Includes Extra Text
- **Expected:** "Education and Cultural Affairs"
- **Got:** "Education and Cultural Affairs suggested and ordered"
- **Root Cause:** The pattern `r'Reference to the Committee on\s+([A-Za-z\s&,]+?)(?:\s+(?:suggested|ordered|referred|assigned))'` is greedy with the `[A-Za-z\s&,]+?` capture
  - The lookahead `(?:\s+(?:suggested|ordered|referred|assigned))` requires this word to be present, but the captured group itself may include it
  - The pattern boundary is not tight enough - it's capturing beyond the committee name

**Proposed Fix:** Use more specific boundary detection or a non-greedy match with better delimiter handling.

### 5. Introduced Date Not Extracted
- **Expected:** "2023-01-26" (or similar, based on "House of Representatives, January 26, 2023")
- **Got:** null
- **Root Cause:** The date extraction pattern looks for dates in specific formats:
  - The text contains "House of Representatives, January 26, 2023"
  - This matches the pattern but the context prefix changes the group indices
  - The pattern `(?:In (?:Senate|House),?\s+)?` is optional, and when it matches, the groups shift
  - The current implementation tries to handle this but may not be correctly parsing the month/day/year

**Proposed Fix:** Improve date parsing to properly handle the "House of Representatives, January 26, 2023" format with correct group index handling.

## Summary of Improvements Needed

1. **Fix `_extract_bill_id()` fallback:** Improve "No. XXX" pattern matching with better handling of spacing and punctuation
2. **Fix `_extract_sponsors()`:** Add more flexible name matching patterns, handle comma-separated sponsor lists, relax district requirement
3. **Fix `_extract_session()`:** Ensure text normalization works correctly for "131st MAINE LEGISLATURE"
4. **Fix `_extract_committee()`:** Tighten the capture boundary to exclude trailing markers like "suggested and ordered"
5. **Fix `_extract_date()`:** Improve group handling for the "House of Representatives, January 26, 2023" pattern

## Data Flow Issues

The core problem appears to be a combination of:
- Whitespace normalization not fully capturing multiline patterns
- Regex patterns being too greedy or having incorrect boundaries
- Insufficient testing against actual Maine Legislature bill formats
