# Extraction Comparison

## Summary

| Metric | Baseline | Improved | Delta | Status |
|--------|----------|----------|-------|--------|
| **Metadata Score** | 1/7 | 5/7 | +4 | ✅ |
| **Cleanliness Score** | 60/100 | 100/100 | +40 | ✅ |
| **Confidence** | 1.00 | 1.00 | +0.00 | — |

## Field-by-Field Comparison

| Field | Baseline | Improved | Status |
|-------|----------|----------|--------|
| **bill_id** | `null` | 131-LD-1611 | ✅ |
| **session** | `null` | 131 | ✅ |
| **title** | An Act to Create the Pine Tree Power Company, a Nonprofit, | An Act to Create the Pine Tree Power Company, a Nonprofit, | — |
| **sponsors** | `[]` | `[]` | — |
| **committee** | `null` | `null` | — |
| **introduced_date** | `null` | 2023-04-11 | ✅ |
| **amended_code_refs** | `[]` | 8 references | ✅ |

## Amended Code References (Extracted)

**Baseline:** Empty list

**Improved:**
1. 5 MRSA §12004-G
2. 35-A MRSA §4002
3. 21-A MRSA §354
4. 21-A MRSA §1011
5. 35-A MRSA §1511-A
6. 35-A MRSA §3501
7. 35-A MRSA §3502
8. 35-A MRSA §3506

## Body Text Quality

**Baseline:**
- Length: 48209 chars
- Contains boilerplate: Yes (library headers, page markers, etc.)
- Cleanliness: 60/100

**Improved:**
- Length: 47488 chars (-721 chars)
- Contains boilerplate: Removed
- Cleanliness: 100/100

The improved version removes institutional headers like "Law and Legislative Digital Library," page numbers, and other metadata that clutters the extracted text.

## Analysis of Missing Fields

Two fields remain unextracted:

1. **sponsors** - This is an initiated bill (I.B. 2), which has no legislative sponsors. This is correct behavior.
2. **committee** - The document does not reference a committee assignment, which is expected for initiated bills.

## Legend

- ✅ New data extracted or improved
- 🔄 Value changed
- — No change
