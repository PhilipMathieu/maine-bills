# Extraction Improvement Review - Bill 131-LD-1611

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
FIRST SPECIAL SESSION-2023
Legislative Document
No. 1611
I.B. 2
House of Representatives, April 11, 2023
An Act to Create the Pine Tree Power Company, a Nonprofit, 
Customer-owned Utility
Transmitted to the Clerk of the 131st Maine Legislature by the Secretary of State on April 
10, 2023 and ordered printed.
ROBERT B. HUNT
Clerk

Page 1 - 131LR2471(01)
1
Be it enacted by the People of the State of Maine as follows:
2
Sec. 1.  5 MRSA §12004-G, sub-§36 is enacted to read:
3
36.  
Public 
Utilities 
Pine Tree Power Company Board 
$110/Day and 
Expenses 
35-A MRSA 
§4002 
4
Sec. 2.  21-A MRSA §354, sub-§5, ¶G, as enacted by PL 1985, c. 161, §6, is 
5
amended to read:
8
G.  For a candidate for State Representative, at least 50 and not more than 80 voters; 
9
and
10
Sec. 3.  21-A MRSA §354, sub-§5, ¶H, as enacted by PL 1985, c. 161, §6, is 
11
amended to read:
12
H.  For a candidate for county charter commission member, at least 50 and not more 
13
than 80 voters.; and
14
Sec. 4.  21-A MRSA §354, sub-§5, ¶I is enacted to read:
15
I.  For a candidate for member of the Pine Tree Power Company Board under Title 
16
35-A, section 4002, subsection 2, paragraph A, at least 300 and not more than 400 
17
voters.
18
Sec. 5.  21-A MRSA §1011, first ¶, as amended by PL 2013, c. 334, §2, is further 
19
amended to read:
20
This subchapter applies to candidates for all state and county offices and to campaigns 
21
for their nomination and election.  Candidates for municipal office as described in Title 
22
30‑A, section 2502, subsection 1 and candidates for the Pine Tree Power Company Board 
23
as describe
...
[See inputs/raw_text.txt for full content]
```

## Baseline Extraction Results

**Metadata:**
- bill_id: (not found)
- session: (not found)
- title: An Act to Create the Pine Tree Power Company, a Nonprofit,
- sponsors: (empty)
- committee: (not found)
- introduced_date: (not found)
- amended_code_refs: (empty)
- confidence: 1.0

**Body text:** 48209 chars, preview:
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
FIRST SPECIAL SESSION-2023
Legislative Document
No. 1611
I.B. 2
House of Representatives, April 11, 2023
An Act to Create the Pine Tree Power Comp...
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
- **Expected:** "131-LD-1611"
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
  "iteration": 1.0,
  "bill_id": "131-LD-1611",
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
