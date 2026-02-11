# Quality Gate Feedback Loop - Reviewer Task

## Mission

Fix the remaining extraction quality issues to pass the quality gate:

**REQUIRED CRITERIA:**
- ✅ All unit tests must pass (currently 7/13)
- ✅ Sponsor extraction ≥ 60% (currently 60.0%)
- ✅ Committee extraction ≥ 60% (currently 60.0%)
- ✅ No regressions in other metrics

## Current Issues

### Unit Test Failures (6 failures)

Failed tests:
- test_extract_sponsors
- test_extract_sponsors_with_apostrophe
- test_extract_sponsors_multiple_on_one_line
- test_extract_sponsors
- test_extract_sponsors_with_apostrophe
- test_extract_sponsors_multiple_on_one_line

**Key insight:** Tests use "Introduced by" but current code only handles "Presented by" (real bill format).
Real bills use "Presented by", but we should support BOTH patterns for robustness.

### Real-World Performance (20-bill sample)

| Metric | Current | Target | Status |
|--------|---------|--------|--------|
| Sponsor extraction | 60.0% | 60%+ | ✅ |
| Committee extraction | 60.0% | 60%+ | ✅ |
| Session extraction | 60.0% | 95%+ | ⚠️ |

## Context Files

- **Test results:** `test_results_baseline.json`
- **Quality metrics:** `quality_metrics_baseline.json`
- **Test code:** `../../tests/unit/test_metadata_extraction.py`
- **Current extractor:** `../../src/maine_bills/text_extractor.py`

## Your Task

Create THREE files:

### 1. `analysis.md`

Analyze:
- Why tests are failing (missing "Introduced by" pattern?)
- Why sponsor extraction is only 60.0%
- Why committee extraction is only 60.0%
- What patterns are missing

### 2. `proposed_changes.py`

Provide complete method implementations for:
- `_extract_sponsors()` - Must handle BOTH "Introduced by" AND "Presented by"
- `_extract_committee()` - Improve extraction rate
- Any other methods that need fixes

Requirements:
- Keep all existing patterns that work
- Add missing patterns
- Use @staticmethod decorator
- Include type hints
- Add docstrings

### 3. `metadata.json`

```json
{
  "methods_modified": ["_extract_sponsors", "_extract_committee"],
  "expected_test_fixes": ["test_extract_sponsors", "test_extract_sponsors_with_apostrophe", ...],
  "expected_quality_improvements": {
    "sponsor_rate": 0.70,
    "committee_rate": 0.65
  },
  "summary": "Added 'Introduced by' pattern for test compatibility while keeping 'Presented by' for real bills"
}
```

## Key Hints

1. **Sponsor extraction:** Add pattern for "Introduced by" alongside existing "Presented by" patterns
2. **False positives:** Filter out titles (President, Speaker, Secretary, State, etc.)
3. **Committee extraction:** Check if patterns are too restrictive
4. **Test compatibility:** Support synthetic test data AND real bill formats

## Previous Feedback Loop Results

The previous feedback loop (100% success rate) added:
- Whitespace normalization
- Multi-fallback extraction
- Ordinal session format
- Month-name date parsing
- Multi-line sponsor blocks

Build on these improvements, don't replace them!

---

**Goal:** Make all tests pass + achieve 60%+ sponsor/committee extraction on real bills.
