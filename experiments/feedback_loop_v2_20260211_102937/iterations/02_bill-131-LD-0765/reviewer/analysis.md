# Extraction Analysis - Bill 131-LD-0765

## Issues Identified

### 1. Bill ID Not Extracted
- **Expected:** "131-LD-0765"
- **Got:** null
- **Root Cause:** Current regex `(\d{2,3}-LD-\d{4})` requires the full format in text, but bill ID appears split across lines:
  - "131st MAINE LEGISLATURE" (session number)
  - "Legislative Document"
  - "No. 765" (LD number)
  - Filename parsing would be more reliable: `131-LD-0765-CA_A_H0266.pdf`
- **Proposed Fix:** Add fallback pattern to extract session from "Xst MAINE LEGISLATURE" and LD number from "No. XXXX", then combine them

### 2. Session Not Extracted
- **Expected:** "131"
- **Got:** null
- **Root Cause:** Current regex looks for full "131-LD-XXXX" pattern. Session appears as "131st MAINE LEGISLATURE" which doesn't match.
- **Proposed Fix:** Add pattern `r'(\d{2,3})(?:st|nd|rd|th)\s+MAINE LEGISLATURE'` to extract session from ordinal format

### 3. Sponsors Not Extracted
- **Expected:** ["CARNEY", "HENDERSON", "BEEBE-CENTER", "BENNETT", "DUSON", "CLOUTIER", "LEE", "MILLETT", "MOONEN", "POIRIER"]
- **Got:** []
- **Root Cause:** Regex patterns are too strict:
  - Looking for "Introduced by/by Representative/Senator" but text has "Presented by Senator"
  - Looking for "Cosponsored by" but text has "Cosponsored by Representative/Senators:" with complex formatting
  - Pattern doesn't handle multi-line cosponsorship blocks with multiple people listed
- **Proposed Fix:** Improve patterns to:
  - Match "Presented by" in addition to "Introduced by"
  - Handle multi-line cosponsorship lists more robustly
  - Extract district names (e.g., "of Cumberland") separately or include

### 4. Committee Not Extracted
- **Expected:** "Judiciary"
- **Got:** null
- **Root Cause:** Current pattern looks for "Committee on|Referred to|Assigned to" but bill text has "Reference to the Committee on Judiciary suggested and ordered printed" which doesn't match the regex boundary `(?:\n|$)` correctly in multi-line context.
- **Proposed Fix:** Update pattern to be more flexible with trailing text, handle "suggested and ordered printed" suffix

### 5. Introduced Date Not Extracted
- **Expected:** date(2023, 2, 21)
- **Got:** null
- **Root Cause:** Current date patterns look for MM/DD/YYYY or YYYY-MM-DD formats, but text has "February 21, 2023" (written month format).
- **Proposed Fix:** Add pattern to match written month names: `r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),?\s+(\d{4})'`

### 6. Title Incomplete
- **Expected:** "An Act to Permit Recordings of a Protected Person to Be Admissible in Evidence"
- **Got:** "An Act to Permit Recordings of a Protected Person to Be Admissible"
- **Root Cause:** Title is split across two lines in PDF:
  - Line 1: "An Act to Permit Recordings of a Protected Person to Be Admissible"
  - Line 2: "in Evidence"
  - Current extractor doesn't continue reading next lines if title is incomplete
- **Proposed Fix:** Check if title ends with incomplete phrase (lowercase starting next word) and continue to next line

### 7. Text Cleaning Issues
- **Problem:** Body text still contains header/footer material:
  - "MAINE STATE LEGISLATURE"
  - "The following document is provided by the LAW AND LEGISLATIVE DIGITAL LIBRARY..."
  - "Printed on recycled paper"
  - "Page X - 131LR0999(01)" patterns
  - Bill metadata lines that should be separated from body
- **Root Cause:** Current `_is_header_footer` misses library reference blocks and doesn't remove institutional footer text
- **Proposed Fix:**
  - Identify and skip document boilerplate blocks (library reference, printed on recycled paper)
  - Better detection of bill preamble vs. actual content
  - More aggressive removal of page markers in format "Page X - XXXXXXX(XX)"

## Summary of Root Causes

1. **Format variations**: Maine bills use multiple formats for the same metadata (ordinal session, written dates)
2. **Multi-line metadata**: Sponsors and titles span multiple lines
3. **Complex punctuation**: Committee names have trailing "suggested and ordered printed"
4. **Boilerplate text**: Library headers and footers not fully cleaned
5. **Regex boundaries**: Word boundaries and line endings don't account for all format variations

## Proposed Solution Approach

1. **Improve session extraction** with ordinal pattern
2. **Enhance date parsing** to support written month names
3. **Expand sponsor patterns** to handle "Presented by" and multi-line cosponsorship blocks
4. **Refine committee extraction** with more flexible trailing text handling
5. **Enhance title extraction** to continue reading next line if needed
6. **Better text cleaning** for institutional boilerplate and page markers
7. **Consider filename-based parsing** as fallback for bill_id reliability
