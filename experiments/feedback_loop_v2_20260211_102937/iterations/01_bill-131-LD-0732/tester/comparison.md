# Extraction Comparison

## Summary

| Metric | Baseline | Improved | Delta | Status |
|--------|----------|----------|-------|--------|
| **Metadata Score** | 2/7 | 6/7 | +4 | ✅ |
| **Cleanliness Score** | 81.5/100 | 98.0/100 | +16.5 | ✅ |
| **Confidence** | 0.44 | 0.44 | +0.00 | — |

## Field-by-Field Comparison

| Field | Baseline | Improved | Status |
|-------|----------|----------|--------|
| **bill_id** | `null` | 131-LD-0732 | ✅ |
| **session** | `null` | 131 | ✅ |
| **title** | An Act to Prohibit Off-trail Operation of a Snowmobile in an Area | An Act to Prohibit Off-trail Operation of a Snowmobile in an Area | — |
| **sponsors** | `[]` | LANDRY, MASON | ✅ |
| **committee** | Inland Fisheries and Wildlife suggested and ordered | Inland Fisheries | 🔄 |
| **introduced_date** | `null` | 2023-02-16 | ✅ |
| **amended_code_refs** | `[]` | `[]` | — |

## Body Text Quality

**Baseline:**
- Length: 1915 chars
- Preview (first 400 chars):
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
Legislative Documen...
```

**Improved:**
- Length: 1487 chars (-428 chars)
- Preview (first 400 chars):
```
131st MAINE LEGISLATURE
Legislative Document
In Senate, February 16, 2023
An Act to Prohibit Off-trail Operation of a Snowmobile in an Area 
Closed to Off-trail Operation
Reference to the Committee on Inland Fisheries and Wildlife suggested and ordered 
printed.
DAREK M. GRANT
Secretary of the Senate
Presented by Senator BLACK of Franklin.
Cosponsored by Representative LANDRY of Farmington and
Rep...
```

## Legend

- ✅ New data extracted or improved
- 🔄 Value changed
- — No change
