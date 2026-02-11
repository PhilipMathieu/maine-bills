# Extraction Improvement Review - Bill 131-LD-1693

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
No. 1693
S.P. 680
In Senate, April 18, 2023
An Act to Amend the Kennebunk Sewer District Charter
Reference to the Committee on Energy, Utilities and Technology suggested and ordered 
printed.
DAREK M. GRANT
Secretary of the Senate
Presented by Senator RAFFERTY of York.
Cosponsored by Representative GERE of Kennebunkport and
Representative: SAYRE of Kennebunk.

Page 1 - 131LR1657(01)
1
Be it enacted by the People of the State of Maine as follows:
2
Sec. 1.  P&SL 2015, c. 9, §1, first ¶ is repealed and the following enacted in its 
3
place:
4
Sec. 1.  Territorial limits; corporate name; purposes. The inhabitants and 
5
territorial limits within that part of the Town of Kennebunk situated between the Atlantic 
6
Ocean, to a point where the Little River meets the Atlantic Ocean, 43°20'07.3"N 
7
70°32'21.0"W, along the eastern edge of the Little River to a point where the Little River 
8
meets Branch Brook, 43°20'59.8"N 70°32'54.7"W, along the eastern edge of Branch Brook 
9
to the western side of the Maine Turnpike where the Maine Turnpike crosses Branch Brook, 
10
43°22'36.4"N 70°34'42.8"W, along the western edge of the Maine Turnpike to a point 
11
where the Maine Turnpike crosses the eastern edge of the Mousam River, 43°24'01.0"N 
12
70°33'55.7"W, along the northeastern edge of the Mousam River to a point along the 
13
northeastern edge, 43°24'21.1"N 70°36'02.2"W, along a straight line on a northeastern 
14
bearing to a point, 43°24'45.0"N 70°35'37.5"W, along the centerline of Alfred Road, along 
15
a straight line on an eastern bearing to 
...
[See inputs/raw_text.txt for full content]
```

## Baseline Extraction Results

**Metadata:**
- bill_id: (not found)
- session: (not found)
- title: An Act to Amend the Kennebunk Sewer District Charter
- sponsors: (empty)
- committee: (not found)
- introduced_date: (not found)
- amended_code_refs: (empty)
- confidence: 0.7836000000000001

**Body text:** 3609 chars, preview:
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
No. 1693
S.P. 680
In Senate, April 18, 2023
An Act to Amend the Kennebunk Sewer District Charter
R...
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
- **Expected:** "131-LD-1693"
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
  "iteration": 0.7836000000000001,
  "bill_id": "131-LD-1693",
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
