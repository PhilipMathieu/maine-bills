# Extraction Improvement Review - Bill 131-LD-0732

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
No. 732
S.P. 290
In Senate, February 16, 2023
An Act to Prohibit Off-trail Operation of a Snowmobile in an Area 
Closed to Off-trail Operation
Reference to the Committee on Inland Fisheries and Wildlife suggested and ordered 
printed.
DAREK M. GRANT
Secretary of the Senate
Presented by Senator BLACK of Franklin.
Cosponsored by Representative LANDRY of Farmington and
Representatives: MASON of Lisbon, WOOD of Greene.

Page 1 - 131LR0290(01)
1
Be it enacted by the People of the State of Maine as follows:
2
Sec. 1.  12 MRSA §13106-A, sub-§27 is enacted to read:
3
27.  Operating snowmobile in posted area.  A person may not operate a snowmobile 
4
off a snowmobile trail in an area that is posted as being closed to off-trail snowmobile 
5
operation.
6
A.  A person who violates this subsection commits a civil violation for which a fine of 
7
not less than $100 and not more than $500 may be adjudged.
8
B.  A person who violates this subsection after having been adjudicated as having 
9
committed 3 or more civil violations under this Part within the previous 5-year period 
10
commits a Class E crime.
11
SUMMARY
12
This bill prohibits a person from operating a snowmobile off a snowmobile trail in an 
13
area that is posted as being closed to off-trail snowmobile operation.  It provides for a fine 
14
of not less than $100 and not more than $500 for the first violation of the prohibition and 
15
that a violation after 3 or more civil violations of the inland fisheries and wildlife laws is a 
16
Class E crime.
12
13
14
15
16

...
[See inputs/raw_text.txt for full content]
```

## Baseline Extraction Results

**Metadata:**
- bill_id: (not found)
- session: (not found)
- title: An Act to Prohibit Off-trail Operation of a Snowmobile in an Area
- sponsors: (empty)
- committee: Inland Fisheries and Wildlife suggested and ordered
- introduced_date: (not found)
- amended_code_refs: (empty)
- confidence: 0.4448

**Body text:** 1915 chars, preview:
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
No. 732
S.P. 290
In Senate, February 16, 2023
An Act to Prohibit Off-trail Operation of a Snowmobi...
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
- **Expected:** "131-LD-0732"
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
  "iteration": 0.4448,
  "bill_id": "131-LD-0732",
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
