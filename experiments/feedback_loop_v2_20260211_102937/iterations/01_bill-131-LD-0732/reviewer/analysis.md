# Extraction Analysis - Bill 131-LD-0732

## Issues Identified

### 1. Bill ID Extraction Failure
- **Expected:** "131-LD-0732"
- **Got:** null
- **Root Cause:** The current regex pattern `(\d{2,3}-LD-\d{4})` requires the bill ID to appear standalone in the text. However, in this bill, the ID appears as "No. 732" and "S.P. 290" separately, with the bill ID needing to be reconstructed from the session number and LD number found on different lines. The bill ID can also be extracted from the footer text "131LR0290(01)" which contains the session and legislative reference number.
- **Proposed Fix:** Enhance `_extract_bill_id()` to:
  - First try the current pattern
  - Fall back to parsing from "131st MAINE LEGISLATURE" → session number, then extract "No. 732" → LD number
  - Try extracting from bill reference like "131LR0290" and converting to "131-LD-0290" format
  - Construct "session-LD-ld_number" from found components

### 2. Session Extraction Failure
- **Expected:** "131"
- **Got:** null
- **Root Cause:** The current `_extract_session()` method relies entirely on finding a bill ID pattern first (`\d{2,3}-LD-\d{4}`). When that fails, session extraction fails. The session number is present in "131st MAINE LEGISLATURE" and "131LR0290(01)" but these patterns aren't being used.
- **Proposed Fix:** Enhance `_extract_session()` to:
  - Try the current bill ID pattern first
  - Add fallback pattern for "(\d{2,3})[st|nd|rd|th]\s+MAINE LEGISLATURE"
  - Add fallback for extracting session from bill reference "(\d{2,3})LR\d+"

### 3. Sponsors Not Extracted
- **Expected:** ["BLACK", "LANDRY", "MASON", "WOOD"] or full names
- **Got:** [] (empty list)
- **Root Cause:** The current patterns in `_extract_sponsors()` search for "Introduced by/by Senator/Representative NAME" formats. However, this bill uses "Presented by Senator BLACK of Franklin" and "Cosponsored by Representative LANDRY..." which don't match the regex patterns. The current patterns also have word boundary issues and don't capture all sponsor types.
- **Proposed Fix:** Enhance `_extract_sponsors()` to:
  - Add pattern for "Presented by (Senator|Representative) ([A-Z][A-Za-z\'\-]+)"
  - Add pattern for "Cosponsored by (Representative|Senator|Senators?) ([A-Z][A-Za-z\'\-]+)"
  - Handle multi-line sponsor lists with "Representatives:" or "Senators:" prefixes
  - Extract names from patterns like "LANDRY of Farmington" and "MASON of Lisbon"
  - Search in first 2000 chars instead of 1000 to catch cosponsors

### 4. Introduced Date Extraction Failure
- **Expected:** "2023-02-16" or date(2023, 2, 16)
- **Got:** null
- **Root Cause:** The current `_extract_date()` looks for MM/DD/YYYY or YYYY-MM-DD formats in the first 2000 chars. This bill has "In Senate, February 16, 2023" which uses a named month format (February) not covered by the current patterns.
- **Proposed Fix:** Enhance `_extract_date()` to:
  - Add pattern for month names: `r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),\s+(\d{4})'`
  - Search in first 2000 chars (current) but add month name parsing
  - Handle "In Senate, February 16, 2023" format specifically

### 5. Committee Extraction Issues
- **Expected:** "Inland Fisheries and Wildlife"
- **Got:** "Inland Fisheries and Wildlife suggested and ordered"
- **Root Cause:** The current pattern `(?:Committee on|Referred to|Assigned to)\s+([A-Za-z\s&]+?)(?:\n|$)` uses a non-greedy quantifier that still captures trailing words. The actual text is "Reference to the Committee on Inland Fisheries and Wildlife suggested and ordered" - the pattern doesn't account for context-specific language like "Reference to" and "suggested and ordered".
- **Proposed Fix:** Enhance `_extract_committee()` to:
  - Add "Reference to the Committee on" pattern
  - Use more precise word boundaries to stop before "suggested", "ordered", "printed"
  - Pattern: `(?:Reference to the )?Committee on\s+([A-Za-z\s&]+?)(?:\s+(?:suggested|ordered|printed|and)|\n|$)`
  - Strip any trailing words like "and ordered printed"

### 6. Body Text Not Properly Cleaned
- **Expected:** Clean text starting with bill enactment, without boilerplate
- **Got:** Still contains "MAINE STATE LEGISLATURE", library headers, copyright notices
- **Root Cause:** The `_clean_body_text()` method removes some headers but not the complete boilerplate section. It removes "STATE OF MAINE" lines but misses the full library introductory block which includes "LAW AND LEGISLATIVE DIGITAL LIBRARY" and "http://legislature.maine.gov/lawlib".
- **Proposed Fix:** Enhance `_clean_body_text()` to:
  - Add patterns to remove full boilerplate block: "The following document is provided by the LAW AND LEGISLATIVE DIGITAL LIBRARY..."
  - Add pattern for "Reproduced from electronic originals..."
  - Add pattern for "Printed on recycled paper"
  - Remove standalone "S.P. 290", "No. 732" lines
  - Consider starting clean body text from "Be it enacted" onwards or first numbered section
  - Add pattern detection for "131LR0290(01)" style footers

## Summary of Improvements

| Field | Issue | Solution |
|-------|-------|----------|
| bill_id | No pattern match | Multi-fallback parsing from session + LD number components |
| session | Depends on bill_id | Direct extraction from legislature designation line |
| sponsors | Pattern mismatch | Enhanced patterns for "Presented by" and "Cosponsored by" formats |
| introduced_date | Format not covered | Add month name pattern support (February 16, 2023) |
| committee | Over-matching | Precise word boundary detection with context keywords |
| body_text | Incomplete cleaning | Remove full boilerplate blocks and legal document headers |

## Key Observations

1. **Filename-based fallback**: The filename "131-LD-0732.pdf" contains all the information needed to reconstruct bill_id and session, confirming the hybrid metadata approach mentioned in CLAUDE.md.

2. **Sponsor format variance**: Maine bills use "Presented by" for primary sponsor and "Cosponsored by" for cosponsors, unlike other patterns the extractor was looking for.

3. **Date format variance**: Natural language dates (month names) are common in Maine bills and should be primary pattern.

4. **Boilerplate is extensive**: The library header block takes up significant space and should be more aggressively removed to improve text quality.
