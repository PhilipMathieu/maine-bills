# Phase 1.5: Quality Gate - Pre-Migration Improvements

**STATUS:** REQUIRED before Phase 2 (HF migration)

**RATIONALE:** We're about to extract thousands of PDFs. Any quality improvements made now will benefit the entire dataset. Re-extracting later is expensive and wasteful.

---

## Current State Baseline (from 10-bill sample)

### ✅ What Works Well
- **PDF extraction:** 100% success rate
- **Title extraction:** 100% (all bills have titles)
- **Text cleaning:** Good (avg confidence 0.88)
- **Basic structure:** PyMuPDF extraction is solid

### ❌ Critical Quality Issues

| Metric | Current | Target | Gap |
|--------|---------|--------|-----|
| Bill ID extraction | 0% | 90%+ | **CRITICAL** |
| Session extraction | 30% | 95%+ | **HIGH** |
| Sponsor extraction | 20% | 70%+ | **HIGH** |
| Committee extraction | 20% | 70%+ | **MEDIUM** |
| Code references | 40% | 60%+ | **LOW** |

### 🐛 Identified Bugs

1. **Bill ID extraction failing completely (0%)**
   - Current regex expects "131-LD-0001" in text
   - Real PDFs don't contain this format consistently
   - **FIX:** Hybrid approach (Phase 2) will parse from filename ✅ DEFERRED

2. **Session extraction low (30%)**
   - Only works for main bills, not amendments
   - Amendments don't have "131st MAINE LEGISLATURE" header
   - **FIX:** Filename parsing will provide this ✅ DEFERRED

3. **Sponsor extraction broken**
   - Test failures: expects "Introduced by" but code looks for "Presented by"
   - Real bills use BOTH patterns
   - Extracting garbage: "President", "State", "States Secretary"
   - **FIX:** Update regex patterns ⚠️ MUST FIX

4. **Legacy pypdf code still present**
   - `extract_from_pdf()` method (lines 105-129) uses old pypdf library
   - Unused, should be removed
   - **FIX:** Remove dead code ⚠️ MUST FIX

---

## Quality Improvements Plan

### Priority 1: Critical Fixes (MUST DO)

#### 1.1. Fix Sponsor Extraction
**Current issues:**
- Patterns don't match "Introduced by" (tests expect this)
- Patterns extract titles like "President" as sponsor names
- Hyphenated names (e.g., "JEAN-PAUL SMITH") not extracted
- Need to filter out non-names

**Changes needed:**
```python
# Add pattern for "Introduced by" (currently missing)
# Improve name validation (exclude titles: President, Speaker, etc.)
# Fix pattern to capture multi-part names
# Test against real bill samples
```

**Success criteria:**
- All 3 sponsor extraction tests pass
- Real bill sample shows 60%+ sponsor extraction rate
- No garbage values (President, State, etc.)

#### 1.2. Remove Legacy pypdf Code
**Files to update:**
- `src/maine_bills/text_extractor.py`: Remove `extract_from_pdf()` method
- `pyproject.toml`: Remove `pypdf` dependency (will be done in Phase 1)

**Success criteria:**
- No pypdf imports in codebase
- All tests still pass

#### 1.3. Update Unit Tests
**Current issues:**
- Tests use synthetic data that doesn't match real bill formats
- Need tests based on actual bill patterns

**Changes needed:**
- Add tests with real bill text snippets (anonymized/minimal)
- Test both "Presented by" and "Introduced by" patterns
- Test amendment format (different from main bills)

**Success criteria:**
- All unit tests pass
- Tests cover both main bills and amendments

### Priority 2: Validation Tooling (SHOULD DO)

#### 2.1. Create Extraction Quality Analyzer
**Purpose:** Measure extraction quality on sample bills

**Features:**
- Download N bills from a session
- Extract metadata and measure success rates
- Generate quality report
- Compare before/after improvements

**Deliverable:** `scripts/analyze_quality.py` (already prototyped ✓)

#### 2.2. Add Extraction Validation
**Purpose:** Detect low-quality extractions during scraping

**Features:**
- Flag bills with confidence < 0.5
- Flag bills missing critical metadata (title, session)
- Log warnings for manual review

**Deliverable:** Add validation to `scraper.py`

### Priority 3: Optional Enhancements (NICE TO HAVE)

#### 3.1. Improve Committee Extraction
- Test against more patterns
- Add fallback patterns

#### 3.2. Improve Code Reference Extraction
- Add more MRSA patterns
- Test against bills with many references

---

## Quality Gate Decision Criteria

### ✅ GO - Proceed to Migration IF:

**Required (all must pass):**
1. ✅ All unit tests passing (currently 32/35, need 35/35)
2. ✅ Sponsor extraction ≥ 60% on 20-bill sample
3. ✅ No legacy pypdf code remaining
4. ✅ Quality analyzer script working

**Desired (at least 2 of 3):**
5. ⭕ Committee extraction ≥ 60% on sample
6. ⭕ Code reference extraction ≥ 50% on sample
7. ⭕ Average confidence ≥ 0.90 on sample

### ❌ NO-GO - Fix Issues First IF:

**Blockers:**
- Unit tests failing
- Sponsor extraction < 40% (too many false positives/negatives)
- Quality analyzer shows data corruption issues

**NOTE:** Bill ID and Session extraction failures are NOT blockers because the hybrid approach (filename parsing) will fix these in Phase 2.

---

## Execution Plan

### Step 1: Fix Sponsor Extraction (1-2 hours)
1. Analyze failing tests to understand expected behavior
2. Update `_extract_sponsors()` method:
   - Add "Introduced by" pattern
   - Add title filtering (exclude: President, Speaker, Secretary, etc.)
   - Improve name validation
3. Run unit tests until all pass
4. Run quality analyzer on 20-bill sample
5. Iterate until ≥ 60% extraction rate

### Step 2: Remove Legacy Code (15 min)
1. Delete `extract_from_pdf()` method from text_extractor.py
2. Remove pypdf imports
3. Run full test suite to confirm no breakage

### Step 3: Improve Test Coverage (30 min)
1. Add test cases based on real bill patterns
2. Add tests for amendment format
3. Add edge case tests (apostrophes, hyphens)

### Step 4: Run Quality Gate Validation (30 min)
1. Run quality analyzer on 20-bill sample
2. Generate quality report
3. Check against decision criteria
4. Document results

### Step 5: Decision Gate Review
**Decision:** If all required criteria pass → PROCEED to Phase 2
**If not:** Iterate on fixes until criteria met

**Estimated time:** 2.5-3.5 hours

---

## Success Metrics

**Before (current):**
- Unit tests: 32/35 passing (91%)
- Sponsor extraction: 20% (with false positives)
- Committee extraction: 20%
- Quality score: **C-**

**After (target):**
- Unit tests: 35/35 passing (100%)
- Sponsor extraction: 60%+ (clean data)
- Committee extraction: 60%+
- Quality score: **B+**

**Note:** We're targeting B+ not A+ because:
- Content-based metadata is best-effort (regex-based)
- Some bills legitimately lack sponsors/committees
- Filename parsing (Phase 2) will provide reliable structure
- Perfect is the enemy of good - we want quality improvements, not perfection

---

## Post-Migration Path

These improvements can wait until after migration:

1. **LLM-based extraction** - Use Claude to extract metadata (higher accuracy but slower/costly)
2. **External API integration** - Hit Open States API for verified metadata
3. **OCR improvements** - Handle scanned PDFs
4. **Table extraction** - Parse fiscal notes, vote tallies
5. **Embeddings** - Pre-compute semantic embeddings for search

---

## Approval

This phase must be completed and approved before starting Phase 2 (schema design).

**Prepared by:** Quality Analysis Script
**Date:** 2026-02-11
**Estimated effort:** 2.5-3.5 hours
**Blocking:** Yes - required before migration
