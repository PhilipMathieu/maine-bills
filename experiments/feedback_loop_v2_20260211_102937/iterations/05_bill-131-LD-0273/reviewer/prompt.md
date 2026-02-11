# Extraction Improvement Review - Bill 131-LD-0273

## Your Task

Review the baseline extraction results and propose improvements to TextExtractor methods.

## Input Files

- **Raw PDF text:** `../inputs/raw_text.txt` (first 2000 chars shown below)
- **Baseline extraction:** `../inputs/baseline.md`
- **Baseline JSON:** `../inputs/baseline.json`

## Raw Text Preview

```
 
MAINE STATE LEGISLATURE 
 
 
 
The following document is provided by the 
LAW AND LEGISLATIVE DIGITAL LIBRARY 
at the Maine State Law and Legislative Reference Library 
http://legislature.maine.gov/lawlib 
 
 
 
 
 
 
 
 
 
 
Reproduced from electronic originals 
(may include minor formatting differences from printed original) 
 
 

Printed on recycled paper
131st MAINE LEGISLATURE
FIRST REGULAR SESSION-2023
Legislative Document
No. 273
H.P. 171
House of Representatives, January 26, 2023
An Act to Provide Funds to the Malaga 1912 Scholarship Fund
Reference to the Committee on Education and Cultural Affairs suggested and ordered 
printed.
ROBERT B. HUNT
Clerk
Presented by Representative ZAGER of Portland.
Cosponsored by Representatives: BRENNAN of Portland, DODGE of Belfast, MILLETT of 
Cape Elizabeth, MURPHY of Scarborough, RIELLY of Westbrook, SARGENT of York, 
Senator: PIERCE of Cumberland.

Page 1 - 131LR0679(01)
1
Be it enacted by the People of the State of Maine as follows:
2
Sec. 1.  Appropriations and allocations.  The following appropriations and 
3
allocations are made.
4
EDUCATION, DEPARTMENT OF
5
General Purpose Aid for Local Schools 0308
6
Initiative: Provides one-time funds for scholarships for descendants of former residents of 
7
Malaga Island or members of a federally recognized Indian tribe in the State. The 
8
Commissioner of Education shall award these funds to a nonprofit entity to administer the 
9
scholarship program.
GENERAL FUND
2023-24
2024-25
All Other
$300,000
$0
 
__________
__________
GENERAL FUND TOTAL
$300,000
$0
10
SUMMARY
11
This bill provides one-time funds for scholarships for descendants of former residents 
12
of Malaga Island or members of a federally recognized Indian tribe in the State and 
13
specifies that the Commissioner of Education must award these funds to a nonprofit entity 
14
to administer the scholarship program.
10
11
12
13
14
15
16
17
18

...
[See inputs/raw_text.txt for full content]
```

## Baseline Extraction Results

**Metadata:**
- bill_id: (not found)
- session: (not found)
- title: An Act to Provide Funds to the Malaga 1912 Scholarship Fund
- sponsors: (empty)
- committee: Education and Cultural Affairs suggested and ordered
- introduced_date: (not found)
- amended_code_refs: (empty)
- confidence: 0.4352

**Body text:** 1865 chars, preview:
```
MAINE STATE LEGISLATURE 
The following document is provided by the 
LAW AND LEGISLATIVE DIGITAL LIBRARY 
at the Maine State Law and Legislative Reference Library 
http://legislature.maine.gov/lawlib 
Reproduced from electronic originals 
(may include minor formatting differences from printed original) 
Printed on recycled paper
131st MAINE LEGISLATURE
FIRST REGULAR SESSION-2023
Legislative Document
No. 273
H.P. 171
House of Representatives, January 26, 2023
An Act to Provide Funds to the Malaga ...
```

---

## Output Requirements

Create **THREE files** in this directory:

### 1. `analysis.md`

Write a human-readable analysis covering:
- What extraction failures you identified
- Root causes for each failure
- Your proposed solution approach

Example format:
```markdown
# Extraction Analysis

## Issues Identified

### 1. Bill ID Extraction Failure
- **Expected:** "131-LD-0273"
- **Got:** null
- **Root Cause:** ...
- **Proposed Fix:** ...

### 2. Sponsors Not Extracted
...
```

### 2. `proposed_changes.py`

Write actual Python code with method implementations:

```python
"""
Proposed improvements to TextExtractor.
Apply these to src/maine_bills/text_extractor.py
"""

from pathlib import Path
from typing import List, Optional
from datetime import date
import re


@staticmethod
def _extract_bill_id(text: str) -> Optional[str]:
    """Extract bill ID from text (e.g., '131-LD-0001')."""
    # Your implementation here
    ...


@staticmethod
def _extract_session(text: str) -> Optional[str]:
    """Extract session number."""
    ...

# Add all improved methods
```

### 3. `metadata.json`

Minimal JSON with just metadata:

```json
{
  "iteration": 0.4352,
  "bill_id": "131-LD-0273",
  "methods_modified": ["_extract_bill_id", "_extract_session", ...],
  "summary": "Brief one-line summary of changes"
}
```

---

## Key Points

- Focus on **concrete improvements** visible in this bill
- Provide **complete, executable** method implementations
- Use proper Python syntax with docstrings
- Match existing method signatures (`@staticmethod`, type hints)
- Be specific about what patterns you're adding/changing
