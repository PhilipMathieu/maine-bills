# Extraction Improvement Review - Bill 131-LD-0765

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
No. 765
S.P. 324
In Senate, February 21, 2023
An Act to Permit Recordings of a Protected Person to Be Admissible 
in Evidence
Reference to the Committee on Judiciary suggested and ordered printed.
DAREK M. GRANT
Secretary of the Senate
Presented by Senator CARNEY of Cumberland.
Cosponsored by Representative HENDERSON of Rumford and
Senators: BEEBE-CENTER of Knox, BENNETT of Oxford, DUSON of Cumberland, 
Representatives: CLOUTIER of Lewiston, LEE of Auburn, MILLETT of Cape Elizabeth, 
MOONEN of Portland, POIRIER of Skowhegan.

Page 1 - 131LR0999(01)
1
Be it enacted by the People of the State of Maine as follows:
2
Sec. 1.  16 MRSA §358 is enacted to read:
3
§358.  Admissibility of recordings of protected person
4
1.  Definitions. As used in this section, unless the context otherwise indicates, the 
5
following terms have the following meanings.
6
A.  "Forensic interview" means a fact-finding conversation conducted by a forensic 
7
interviewer using an evidence-based practice.
8
B.  "Forensic interviewer" means an individual who meets the qualifications in 
9
subsection 2.
10
C.  "Protected person" means a person who at the time of a recording of a forensic 
11
interview:
12
(1)  Has not attained 18 years of age; or
13
(2)  Is an adult who is eligible for protective services pursuant to the Adult 
14
Protective Services Act.
15
2.  Qualifications of forensic interviewer.  In order to be qualified as a forensic 
16
interviewer, an individual must:
17
A.  Be employed by a child advocacy center or affiliated with a child advocacy center;
18
B. 
...
[See inputs/raw_text.txt for full content]
```

## Baseline Extraction Results

**Metadata:**
- bill_id: (not found)
- session: (not found)
- title: An Act to Permit Recordings of a Protected Person to Be Admissible
- sponsors: (empty)
- committee: (not found)
- introduced_date: (not found)
- amended_code_refs: (empty)
- confidence: 1.0

**Body text:** 9866 chars, preview:
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
No. 765
S.P. 324
In Senate, February 21, 2023
An Act to Permit Recordings of a Protected Person to...
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
- **Expected:** "131-LD-0765"
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
  "bill_id": "131-LD-0765",
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
