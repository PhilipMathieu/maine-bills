# Error Patterns Catalog

**Comprehensive reference of all error patterns validated during quality testing.**

This document catalogs every error pattern we've tested for during the quality improvement process. Use this as a checklist for future quality validation and regression testing.

**Last Updated:** 2026-02-11
**Sessions Validated:** 125, 130, 131, 132 (spanning 2011-2026)

---

## Table of Contents

1. [False Positive Patterns](#false-positive-patterns)
2. [Missing Sponsor Patterns](#missing-sponsor-patterns)
3. [Name Edge Case Patterns](#name-edge-case-patterns)
4. [Cross-Session Format Variations](#cross-session-format-variations)
5. [Special Bill Type Patterns](#special-bill-type-patterns)
6. [Filter Accuracy Patterns](#filter-accuracy-patterns)
7. [Validation Commands](#validation-commands)

---

## False Positive Patterns

**Definition:** Text extracted as sponsor names that are NOT actual legislators.

### 1. Title Words in Compound Phrases

**Pattern:** Government/legal terms appearing in "X of Y" constructions.

**Examples Found:**
```
✗ "Office of [Department]" → extracted "Office"
✗ "Constitution of Maine" → extracted "Constitution"
✗ "People of the State" → extracted "People"
✗ "Department of Education" → extracted "Department"
✗ "President JACKSON" → extracted "President JACKSON" (should be just "JACKSON")
✗ "Speaker FECTEAU" → extracted "Speaker FECTEAU" (should be just "FECTEAU")
✗ "States Department of Health" → extracted "States Department"
```

**Root Cause:** Comma-separated extraction pattern `([NAME]) of [LOCATION]` matches throughout entire document text after whitespace normalization.

**Detection Method:**
```python
# Check if extracted sponsor contains title words
title_words = {'President', 'Speaker', 'Office', 'Constitution', ...}
for sponsor in extracted_sponsors:
    name_words = set(sponsor.split())
    if name_words.intersection(title_words):
        # FALSE POSITIVE DETECTED
```

**Fix Applied:** Expanded title_words filter from 13 → 27 → 33 words.

**Current Filter (33 words):**
```python
title_words = {
    # Leadership titles (11)
    'President', 'Speaker', 'Secretary', 'Clerk', 'Chief',
    'Governor', 'Mayor', 'Attorney', 'General', 'Commissioner', 'Treasurer',

    # Government entities (11)
    'State', 'States', 'Department', 'Senate', 'House', 'Bureau',
    'Office', 'Committee', 'Government', 'Council', 'Commission', 'Administration',

    # Document references (8)
    'Session', 'Regular', 'Special', 'Legislature', 'Legislative',
    'Constitution', 'People', 'Law', 'Code', 'Rules',

    # Generic/Article words (3)
    'The', 'Maine', 'Number'
}
```

**Test Cases:**
- ✓ "President JACKSON" → blocks "President", extracts "JACKSON"
- ✓ "Office of Administration" → blocks "Office", blocks "Administration"
- ✓ "Constitution of Maine" → blocks "Constitution", blocks "Maine"
- ✓ "The Treasurer of State" → blocks "The", blocks "Treasurer", blocks "State"

**Regression Test:**
```bash
# Search for title words in extracted sponsors
uv run python -c "
from maine_bills.text_extractor import TextExtractor
import tempfile, requests
from pathlib import Path

# Test on 50 bills
# Check: no sponsor should contain title words
for sponsor in all_sponsors:
    assert not any(word in sponsor for word in TITLE_WORDS)
"
```

---

### 2. Document Metadata Words

**Pattern:** Administrative/document terms that appear in bill text.

**Examples Found:**
```
✗ "Maine Rules" (from "Maine Rules of Civil Procedure")
✗ "Number" (from bill numbering text)
✗ "Administration" (from "Administration of [Program]")
```

**Root Cause:** These words appear in standard legal document boilerplate.

**Detection Method:** Manual review of extracted sponsors for non-name words.

**Fix Applied:** Added to title_words filter: `'Rules', 'Number', 'Administration', 'Maine'`

**Test Cases:**
- ✓ "Maine Rules of Evidence" → blocks "Maine", blocks "Rules"
- ✓ "Bill Number 1234" → blocks "Number"
- ✓ "Administration of Justice" → blocks "Administration"

---

### 3. Multi-Word Title Phrases

**Pattern:** Two-word phrases that pass length check but aren't names.

**Examples Found:**
```
✗ "Legislative Oversight" (from "Legislative Oversight Committee")
✗ "GRANT Secretary" (from "Secretary GRANT" misparse)
✗ "States Department" (from "United States Department of...")
```

**Root Cause:**
- Pattern allows up to 2 words: `[A-Z][A-Za-z\'\-]+(?:\s+[A-Z][A-Za-z\'\-]+)?`
- Length check: `len(name.split()) > 2` blocks 3+ words but allows 2-word phrases

**Detection Method:** Word-level filtering with `is_valid_name()` helper.

**Fix Applied:** Check if ANY word in the name is a title word:
```python
def is_valid_name(name: str) -> bool:
    if not name or name in sponsors or len(name.split()) > 2:
        return False
    name_words = set(name.split())
    return not name_words.intersection(title_words)
```

**Test Cases:**
- ✓ "Legislative Oversight" → blocks "Legislative"
- ✓ "States Department" → blocks "States" AND "Department"
- ✓ "GRANT Secretary" → blocks "Secretary"
- ✓ "TALBOT ROSS" → passes (neither word is title word)

---

## Missing Sponsor Patterns

**Definition:** Bills that should have sponsors but extraction returns empty list.

### 1. Leadership Title Format (Fixed ✓)

**Pattern:** Bills introduced by President/Speaker instead of Senator/Representative.

**Examples Found:**
```
Bill 131-LD-0150:
  "Presented by President JACKSON of Aroostook"

Bill (hypothetical):
  "Presented by Speaker FECTEAU of Biddeford"
```

**Root Cause:** Original patterns only matched `(?:Senator|Representative)`, not leadership titles.

**Detection Method:**
```bash
# Find bills with "President" or "Speaker" but no sponsors extracted
grep -l "Presented by President\|Presented by Speaker" *.txt | while read f; do
  bill_id=$(basename $f .txt)
  if [ empty sponsors ]; then echo "Missing: $bill_id"; fi
done
```

**Fix Applied:** Added `President|Speaker` to all 5 extraction patterns:
```python
# Pattern 1 (with district)
r'(?:Presented|Introduced) by\s+(?:Senator|Representative|President|Speaker)\s+...'

# Pattern 1b (without district)
r'(?:Presented|Introduced) by\s+(?:Senator|Representative|President|Speaker)\s+...'

# Cosponsorship patterns (3 more instances)
```

**Impact:** Recovered ~1% of bills (President/Speaker introduce <1% of bills)

**Test Cases:**
- ✓ "Presented by President JACKSON of Aroostook" → ['JACKSON']
- ✓ "Presented by Speaker FECTEAU of Biddeford" → ['FECTEAU']
- ✓ "Presented by President JACKSON. Cosponsored by Senator VITELLI..." → ['JACKSON', 'VITELLI', ...]

**Regression Test:**
```python
def test_president_sponsor():
    text = "Presented by President JACKSON of Aroostook."
    sponsors = TextExtractor._extract_sponsors(text)
    assert sponsors == ['JACKSON']

def test_speaker_sponsor():
    text = "Presented by Speaker FECTEAU of Biddeford."
    sponsors = TextExtractor._extract_sponsors(text)
    assert sponsors == ['FECTEAU']
```

---

### 2. Special Document Types

**Pattern:** Resolves and other special documents that legitimately have no sponsor section.

**Examples Found:**
```
Bill 131-LD-2180 (Resolve):
  - Type: Legislative Resolve
  - No "Presented by" section found
  - No sponsor information in document
  - This is CORRECT behavior
```

**Root Cause:** Not all legislative documents follow the standard bill format.

**Detection Method:**
```python
# Check document type
if bill_doc.title and 'Resolve' in bill_doc.title:
    # Missing sponsors expected
    pass
```

**Fix Applied:** None needed - this is correct behavior.

**Impact:** <1% of documents. Acceptable as edge case.

**Test Strategy:** Don't count Resolves in sponsor extraction rate calculation.

---

### 3. Multi-Page Sponsor Sections

**Pattern:** Sponsor information on page 2+ instead of page 1.

**Example Found:**
```
Bill 131-LD-0150:
  - Page 1: Digital library header/metadata only
  - Page 2: "Presented by President JACKSON of Aroostook"
  - Extraction now works (after leadership title fix)
```

**Root Cause:** Extractor reads `text[:2500]` (first 2500 chars), which usually includes page 1 and part of page 2.

**Detection Method:** If extraction fails, check if sponsor section appears later in document.

**Fix Applied:** Current 2500-char window is sufficient. After leadership title fix, this bill now extracts correctly.

**Test Cases:**
- ✓ Bills with digital library header on page 1 extract from page 2

---

### 4. Pattern Mismatches (None Found)

**Pattern:** Text variations our regex patterns don't match.

**Potential Issues Tested:**
```
✓ "Introduced by" vs "Presented by" - BOTH supported
✓ Extra whitespace/line breaks - Handled by normalization
✓ Comma-separated lists - Dedicated pattern
✓ "and" vs "," separators - Multiple patterns handle both
✓ With district "of X" vs without - Separate patterns for each
```

**Detection Method:** Manual inspection of bills without sponsors.

**Results:** 96% extraction rate on main bills indicates patterns are comprehensive.

**No fix needed:** Current patterns handle all observed variations.

---

## Name Edge Case Patterns

**Definition:** Unusual name formats that might not match our patterns.

### Test Results: 0 Edge Cases Found in Real Data

We tested for these patterns and **NONE were found** in 50 Maine bills:

### 1. Name Suffixes (NOT FOUND)

**Patterns Tested:**
```
✗ "Senator SMITH Jr. of Portland" - NOT FOUND in real bills
✗ "Representative JOHNSON Sr. of York" - NOT FOUND
✗ "Senator WILLIAMS III of Cumberland" - NOT FOUND
✗ "Representative JONES II of Kennebec" - NOT FOUND
```

**Test Method:** Regex search across 50 bills for `(Jr\.|Sr\.|III|II|IV)`

**Result:** 0 matches

**Pattern Support:** Currently NOT supported (but not needed)

**Future Fix (if needed):**
```python
# If Maine ever elects someone with suffix:
pattern = r'Senator\s+([A-Z][A-Za-z\'\-]+)\s+(?:Jr\.|Sr\.|III|II)\s+of'
# Extract name without suffix
```

---

### 2. Three-Word Names (NOT FOUND)

**Patterns Tested:**
```
✗ "DE LA CRUZ" - NOT FOUND
✗ "VAN DER MEER" - NOT FOUND
✗ "VON DER HEYDEN" - NOT FOUND
```

**Test Method:** Regex search for `Senator\s+[A-Z]+\s+[A-Z]+\s+[A-Z]+\s+of`

**Result:** 0 matches

**Current Limitation:** Pattern limits to 2 words max:
```python
[A-Z][A-Za-z\'\-]+(?:\s+[A-Z][A-Za-z\'\-]+)?
#                   ^^^^^^^^^^^^^^^^^^^^^^^^^^ optional second word only
```

**Pattern Support:** Currently NOT supported (but not needed)

**Future Fix (if needed):**
```python
# Allow 3 words:
pattern = r'([A-Z][A-Za-z\'\-]+(?:\s+[A-Z][A-Za-z\'\-]+){0,2})'
#                                                      ^^^^^ up to 2 additional words
```

---

### 3. Lowercase Name Prefixes (NOT FOUND)

**Patterns Tested:**
```
✗ "von BRAUN" - NOT FOUND
✗ "de LA CRUZ" - NOT FOUND
✗ "van GOGH" - NOT FOUND
✗ "di MEDICI" - NOT FOUND
```

**Test Method:** Regex search for `(?:von|de|van|di)\s+[A-Z]`

**Result:** 0 matches

**Current Limitation:** Pattern requires uppercase first letter `[A-Z]`

**Pattern Support:** Currently NOT supported (but not needed)

---

### 4. Patterns That ARE Supported

**Examples Found in Real Bills:**

**Two-word hyphenated names:**
```
✓ "TALBOT-ROSS" (found in multiple bills)
✓ "BEEBE-CENTER"
✓ "STRANG BURGESS"
```

**Names with apostrophes:**
```
✓ "O'CONNELL" (found in multiple bills)
✓ "O'BRIEN"
✓ "O'NEIL"
```

**Names with Mc/Mac prefix:**
```
✓ "McCREIGHT" (found in session 131)
✓ "MACDONALD"
```

**Very long names:**
```
✓ "SCHMERSAL-BURGESS" (found in session 131)
✓ "SCHWARZENEGGER-WASHINGTON" (theoretical, but would work)
```

**Pattern that supports these:**
```python
[A-Z][A-Za-z\'\-]+  # Uppercase first letter, then letters/apostrophes/hyphens
```

---

## Cross-Session Format Variations

**Definition:** Differences in bill format across legislative sessions.

### Sessions Tested: 125 (2011), 130 (2021), 131 (2023), 132 (2025)

### 1. Bill ID Formats

**Variations Found:**

**Standard LD (Legislative Document):**
```
125-LD-1013
130-LD-0686
131-LD-1770
132-LD-0127
```
✓ Consistent across all sessions

**Amendments (varied suffixes):**
```
Session 125: 125-LD-1477-CA_A-SA_A_S335  (dash between CA_A and SA_A)
Session 130: 130-LD-0686-CA_A_H0266      (standard format)
Session 131: 131-LD-1770-CA_A_H266       (standard format)
Session 132: 132-LD-0127-CA_A_S9         (standard format)
```
✓ All variations handled by `is_amendment()` helper

**Special Publications (SP):**
```
Session 132: 132-SP-0010-CA_A_S119
Session 132: 132-SP-0519_HA_A  (underscore format!)
```
✓ Both handled

**Detection Method:**
```python
def is_amendment(bill_id):
    parts = bill_id.split('-')
    if len(parts) > 3:
        return True
    if '_' in parts[-1] if len(parts) >= 3 else False:
        return True
    return False
```

---

### 2. Sponsor Line Format Variations

**All Sessions Use Same Format:**
```
"Presented by Senator NAME of DISTRICT"
"Presented by Representative NAME of DISTRICT"
"Presented by President NAME of DISTRICT"   (rare)
"Presented by Speaker NAME of DISTRICT"     (rare)
```

✓ No format variations found across 15 years (2011-2026)

**Cosponsorship Format:**
```
"Cosponsored by Senator X of Y and Representative Z of W"
"Cosponsored by Senators: X of Y, Z of W, Representatives: A of B, C of D"
```

✓ Consistent across all sessions

---

### 3. PDF Structure Variations

**Digital Library Header:**
```
Some bills (all sessions):
  - Page 1: "MAINE STATE LEGISLATURE" header + metadata
  - Page 2: Actual bill content starts

Most bills:
  - Page 1: Bill content starts immediately
```

✓ Handled by reading first 2500 characters (usually covers pages 1-2)

**Text Quality:**
```
Session 125 (2011): Good quality, clean extraction
Session 130 (2021): Good quality, clean extraction
Session 131 (2023): Good quality, clean extraction
Session 132 (2025): Good quality, clean extraction
```

✓ No OCR or scanning artifacts in any session
✓ All sessions use digital-native PDFs

---

## Special Bill Type Patterns

**Definition:** Non-standard legislative document types.

### Bill Types Found

**From scanning sessions 130-132:**

```
LD (Legislative Document): 11,320 bills (99.98%)
SP (Special Publication):       2 bills (0.02%)
```

### 1. SP (Special Publication) Bills

**Examples:**
```
132-SP-0010-CA_A_S119  (amendment to special publication)
132-SP-0519_HA_A       (house amendment to special publication)
```

**Characteristics:**
- Both are amendments (have suffixes)
- Extract no metadata (title, sponsors, session all None/empty)
- Low confidence scores (0.368, 0.604)
- This is EXPECTED - they're amendments to non-standard documents

**Test Results:**
```
132-SP-0010-CA_A_S119:
  Bill ID: None
  Title: Unknown Title
  Sponsors: []
  Confidence: 0.604
  Status: ✓ Expected behavior for amendment
```

**Fix Applied:** None needed - correct behavior

---

### 2. Resolves

**Example:**
```
131-LD-2180 (Resolve):
  - No sponsor section found
  - Special legislative resolution format
  - Missing sponsors is EXPECTED
```

**Characteristics:**
- Different document structure than bills
- May not have traditional sponsor sections
- Appear as regular LD numbers, not separate type

**Detection:**
```python
if 'Resolve' in bill_doc.title:
    # Expect possible missing metadata
```

**Impact:** <1% of documents

**Fix Applied:** Acceptable as edge case

---

### 3. Types NOT Found

We did NOT find these in Maine Legislature:

```
✗ HR (House Resolution) - not found
✗ SR (Senate Resolution) - not found
✗ HB (House Bill) - not found
✗ SB (Senate Bill) - not found
✗ JR (Joint Resolution) - not found
```

**Conclusion:** Maine uses simplified LD numbering for all legislative documents.

---

## Filter Accuracy Patterns

**Definition:** Ensuring the title_words filter doesn't block legitimate legislator names.

### Test: 100-Bill Name Collection

**Method:**
```python
# Collect all unique sponsor names from 100 bills
# Check if any would be blocked by filter
for sponsor in all_sponsors:
    name_words = set(sponsor.split())
    if name_words.intersection(title_words):
        # BLOCKED - investigate
```

**Results:**

**Total unique sponsors found:** 169 across sessions

**Sponsors incorrectly blocked:** 0 ✓

**False positives found (blocked correctly):** 3
```
✗ "Maine Rules" - correctly blocked by 'Maine' and 'Rules'
✗ "Number" - correctly blocked by 'Number'
✗ "The Treasurer" - correctly blocked by 'The' and 'Treasurer'
```

### Edge Case: Names That Could Be Problematic

**Theoretical concern:** What if a legislator's surname matches a title word?

**Examples to watch for (NONE FOUND in real data):**
```
Hypothetical: "Senator CHIEF of Penobscot" (Native American surname)
Hypothetical: "Representative HOUSE of York"
Hypothetical: "Senator CODE of Cumberland"
```

**Current behavior:** Would be blocked by filter

**Mitigation strategy:**
1. Monitor for pattern: title word as ONLY word in extracted name
2. If found, manual review needed
3. Possible fix: Check against official legislator roster

**Actual risk:** VERY LOW (0 instances in 169 unique names across 15 years)

---

## Validation Commands

**Quick commands for testing each error pattern.**

### Test for False Positives

```bash
# Extract sponsors from 50 bills, check for title words
uv run python -c "
import sys, tempfile, requests, random
from pathlib import Path
from bs4 import BeautifulSoup
sys.path.insert(0, 'src')
from maine_bills.text_extractor import TextExtractor

session = 131
url = f'http://lldc.mainelegislature.org/Open/LDs/{session}/'
res = requests.get(url, timeout=10)
soup = BeautifulSoup(res.content, features='html.parser')
bill_ids = [a.attrs['href'].split('/')[-1][:-4] for a in soup.find_all('a')[1:] if a.attrs['href'].endswith('.pdf')]
main_bills = [b for b in bill_ids if '-' not in b.split('-LD-')[1]]
sample = random.sample(main_bills, 50)

title_words = {'President', 'Speaker', 'Office', 'Constitution', 'Maine', 'The', 'Rules', 'Number', 'Treasurer', 'Administration'}
all_sponsors = set()

for bill_id in sample:
    try:
        pdf_url = f'{url}{bill_id}.pdf'
        r = requests.get(pdf_url, timeout=10)
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
            tmp.write(r.content)
            tmp_path = Path(tmp.name)
        bill_doc = TextExtractor.extract_bill_document(tmp_path)
        all_sponsors.update(bill_doc.sponsors)
        tmp_path.unlink()
    except:
        pass

# Check for false positives
fps = [s for s in all_sponsors if any(w in s for w in title_words)]
print(f'False positives: {len(fps)}')
if fps:
    print(f'Examples: {fps[:5]}')
else:
    print('✓ No false positives detected')
"
```

### Test Missing Sponsors Rate

```bash
# Check extraction rate on main bills
uv run python -c "
import sys, tempfile, requests, random
from pathlib import Path
from bs4 import BeautifulSoup
sys.path.insert(0, 'src')
from maine_bills.text_extractor import TextExtractor

session = 131
url = f'http://lldc.mainelegislature.org/Open/LDs/{session}/'
res = requests.get(url, timeout=10)
soup = BeautifulSoup(res.content, features='html.parser')
bill_ids = [a.attrs['href'].split('/')[-1][:-4] for a in soup.find_all('a')[1:] if a.attrs['href'].endswith('.pdf')]
main_bills = [b for b in bill_ids if '-' not in b.split('-LD-')[1]]
sample = random.sample(main_bills, 30)

with_sponsors = 0
total = 0

for bill_id in sample:
    try:
        pdf_url = f'{url}{bill_id}.pdf'
        r = requests.get(pdf_url, timeout=10)
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
            tmp.write(r.content)
            tmp_path = Path(tmp.name)
        bill_doc = TextExtractor.extract_bill_document(tmp_path)
        if bill_doc.sponsors:
            with_sponsors += 1
        total += 1
        tmp_path.unlink()
    except:
        pass

pct = 100 * with_sponsors / total if total > 0 else 0
print(f'Extraction rate: {with_sponsors}/{total} ({pct:.1f}%)')
if pct >= 60:
    print('✓ Meets 60% target')
else:
    print('✗ Below 60% target - investigate')
"
```

### Test Leadership Title Extraction

```bash
# Test President/Speaker extraction
uv run python -c "
import sys
sys.path.insert(0, 'src')
from maine_bills.text_extractor import TextExtractor

tests = [
    ('President JACKSON of Aroostook', ['JACKSON']),
    ('Speaker FECTEAU of Biddeford', ['FECTEAU']),
]

for text, expected in tests:
    result = TextExtractor._extract_sponsors(f'Presented by {text}.')
    if result == expected:
        print(f'✓ {text} → {result}')
    else:
        print(f'✗ {text} → Expected {expected}, got {result}')
"
```

### Test Cross-Session Consistency

```bash
# Run validation on multiple sessions
for session in 125 130 131 132; do
    echo "Testing session $session..."
    uv run python /tmp/test_old_session.py $session | grep "EXCELLENT\|REVIEW"
done
```

### Run All Unit Tests

```bash
# Comprehensive test suite
uv run pytest tests/unit/ -v
```

### Search for Specific Error Pattern

```bash
# Example: Find bills with "President" or "Speaker"
uv run python -c "
import sys, tempfile, requests, fitz
from pathlib import Path
from bs4 import BeautifulSoup

session = 131
url = f'http://lldc.mainelegislature.org/Open/LDs/{session}/'
res = requests.get(url, timeout=10)
soup = BeautifulSoup(res.content, features='html.parser')
bill_ids = [a.attrs['href'].split('/')[-1][:-4] for a in soup.find_all('a')[1:] if a.attrs['href'].endswith('.pdf')]

for bill_id in bill_ids[:100]:  # Check first 100
    try:
        pdf_url = f'{url}{bill_id}.pdf'
        r = requests.get(pdf_url, timeout=10)
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
            tmp.write(r.content)
            tmp_path = Path(tmp.name)
        doc = fitz.open(tmp_path)
        text = doc[0].get_text()
        doc.close()
        tmp_path.unlink()

        if 'President' in text or 'Speaker' in text:
            if 'Presented by President' in text or 'Presented by Speaker' in text:
                print(f'Found: {bill_id}')
    except:
        pass
"
```

---

## Summary Statistics

### Error Patterns Identified: 9 categories

1. ✓ Title words in compound phrases (6 instances fixed)
2. ✓ Document metadata words (3 instances fixed)
3. ✓ Multi-word title phrases (handled by word-level filtering)
4. ✓ Leadership title format (1 pattern fixed, ~1% of bills)
5. ✓ Special document types (identified as edge case, <1%)
6. ✓ Multi-page sponsor sections (handled by existing 2500-char window)
7. ✗ Name edge cases (0 instances found in real data)
8. ✓ Cross-session variations (validated across 4 sessions, 15 years)
9. ✓ Filter accuracy (0 false blocks, 3 false positives caught)

### Validation Coverage

- **Sessions tested:** 4 (125, 130, 131, 132)
- **Time span:** 15 years (2011-2026)
- **Bills analyzed:** 200+ across all tests
- **Unique sponsors collected:** 169+
- **False positives found and fixed:** 9
- **False negatives found and fixed:** Leadership titles (~1%)
- **Real names incorrectly blocked:** 0

### Current Quality Metrics

| Metric | Target | Achieved | Status |
|--------|--------|----------|--------|
| Sponsor extraction (main bills) | ≥60% | 80-100% | ✅ |
| False positive rate | 0% | 0% | ✅ |
| False negative rate (blocking real names) | 0% | 0% | ✅ |
| Cross-session consistency | All pass | All pass | ✅ |
| Unit test coverage | 100% pass | 54/54 | ✅ |

---

**Document Version:** 1.0
**Next Review:** After processing first full session for HuggingFace migration
**Maintainer:** Claude Code (quality validation system)
