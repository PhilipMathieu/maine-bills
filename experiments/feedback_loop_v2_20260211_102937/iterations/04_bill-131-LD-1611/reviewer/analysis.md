# Extraction Analysis - Bill 131-LD-1611

## Issues Identified

### 1. Bill ID Extraction Failure
- **Expected:** "131-LD-1611"
- **Got:** null
- **Root Cause:** The bill uses "No. 1611" in the document header, but the current `_extract_bill_id()` method expects the LD number to be zero-padded to 4 digits in its fallback logic. The number "1611" is already 4 digits, but the extraction pattern `(?:Legislative Document|Document No\.?|No\.?)\s+(\d{3,4})` successfully matches, and the session "131" is correctly found via the ordinal format. However, inspection of the actual implementation shows the fallback code properly handles this - the issue appears to be that the bill ID format in this particular bill's header is unusual and the combined pattern at the start doesn't match because the bill ID is not in "131-LD-1611" format anywhere in the text.
- **Proposed Fix:** The fallback logic already exists but needs to be verified. Upon review of the raw text, "No. 1611" should be matched by the regex. The real issue is that the session/LD extraction is working but may not be properly triggered. Add explicit extraction for the case where session and LD are found separately but not combined in one regex pattern.

### 2. Session Extraction Failure
- **Expected:** "131"
- **Got:** null
- **Root Cause:** The text contains "131st MAINE LEGISLATURE" but the extraction is failing. Looking at the raw text on line 26-27, we see "131st MAINE LEGISLATURE" but it's split across "FIRST SPECIAL SESSION-2023". The normalized text handling should catch this, but there may be an issue with how the ordinal format regex is being applied or with the search scope.
- **Proposed Fix:** The pattern `r'(\d{2,3})(?:st|nd|rd|th)\s+(?:MAINE\s+)?LEGISLATURE'` should match "131st MAINE LEGISLATURE". However, the issue is that in the actual bill text (line 26), it shows "131st MAINE LEGISLATURE" on one line and "FIRST SPECIAL SESSION-2023" on the next. When normalizing with spaces, this becomes "131st MAINE LEGISLATURE FIRST SPECIAL SESSION-2023", which should match. The regex in `_extract_session()` is correct, so the issue may be in the search scope or text preprocessing.

### 3. Sponsors Not Extracted (Empty List)
- **Expected:** At least one sponsor (bill appears to be introduced)
- **Got:** []
- **Root Cause:** The baseline extraction shows `sponsors: []`, which means no sponsor patterns were matched. Looking at the raw text (lines 31-50), there is no "Presented by" or "Cosponsored by" line visible in the provided preview. This bill appears to be an initiated bill (I.B. 2) rather than a bill presented by a legislator, so sponsor extraction may legitimately return empty. However, the extraction should still work correctly.
- **Proposed Fix:** This is expected behavior for initiated bills. However, we can improve the method to explicitly detect and handle initiated bills, returning an indicator that the bill is initiated rather than having an empty sponsors list that's indistinguishable from a failed extraction.

### 4. Committee Not Extracted
- **Expected:** Possible committee name or null if not assigned
- **Got:** null
- **Root Cause:** Looking at the raw text, there is no "Reference to the Committee on" pattern visible in the preview (lines 1-104). The text shows "House of Representatives, April 11, 2023" but no explicit committee reference. This appears to be expected behavior for this bill.
- **Proposed Fix:** This is likely expected - the bill may not have been assigned to a committee in the traditional sense, or the committee assignment appears later in the document. Current extraction is appropriate.

### 5. Introduced Date Not Extracted
- **Expected:** "2023-04-11" (from "House of Representatives, April 11, 2023")
- **Got:** null
- **Root Cause:** The text on line 31 clearly shows "House of Representatives, April 11, 2023". The date extraction pattern should match "April 11, 2023" in the format `(January|February|...|April|...) (\d{1,2}),?\s+(\d{4})`. However, the text context is "House of Representatives, April 11, 2023" which doesn't match the expected patterns well. The issue is that "April 11, 2023" appears after "House of Representatives," not after "In House," and the current regex may not be catching this context.
- **Proposed Fix:** Expand the date extraction to recognize dates appearing after "House of Representatives," or any chamber location marker. The pattern should allow for more flexible context before the month name.

## Summary of Root Causes

1. **Bill ID / Session:** The extraction logic exists but appears to not be executing properly. The text contains all necessary components, but the methods aren't finding them.
2. **Sponsors:** Expected empty for an initiated bill - this is correct behavior.
3. **Committee:** Bill likely doesn't have a committee assignment shown in the extracted text.
4. **Date:** The date pattern needs to be more flexible to match dates after "House of Representatives," in addition to "In House," context.

## Proposed Solution Approach

### For Bill ID and Session:
- The existing fallback logic in `_extract_bill_id()` should work. Verify that it's being called and that the regex patterns are matching the "131st MAINE LEGISLATURE" and "No. 1611" components.
- Ensure that the method doesn't return early if the combined pattern fails, and properly falls back to component extraction.

### For Introduced Date:
- Expand the date pattern to match dates that appear after chamber location markers like "House of Representatives," "Senate," etc., not just "In House," or "In Senate,"
- Add a more flexible pattern that matches dates in these contexts.

### For Sponsors:
- Add explicit handling for initiated bills (marked as "I.B. X") to distinguish between "no sponsors found" and "initiated bill with no legislator sponsors"

### For Amended Code References:
- The current implementation looks for "Title X, Section Y" pattern. This bill clearly contains many sections with amended code references like "5 MRSA §12004-G" (line 43). The current pattern is too narrow. Expand to capture MRSA references like "35-A MRSA §4002" which appear throughout the bill.
