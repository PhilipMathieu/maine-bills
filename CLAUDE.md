# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A Python scraper for Maine Legislature bills that extracts text and metadata from PDFs. Currently in transition from a git-repo-as-dataset to a proper HuggingFace dataset with Parquet files.

**Current state:** Production-ready extraction system validated across 4 sessions (2011-2026)
**Next step:** HuggingFace setup and migration
**Target state:** Publish structured Parquet files to HuggingFace Hub at `PhilipMathieu/maine-bills`

**Quality Status (2026-02-11):**
- ✅ Extraction quality: 80-100% sponsor accuracy, 0 false positives
- ✅ Cross-session validation: 125, 130, 131, 132 (15 years)
- ✅ Unit tests: 54/54 passing
- ✅ Documentation: Complete error pattern catalog + quality history
- ✅ Ready for HuggingFace migration

## Essential Commands

### Setup
```bash
uv sync                          # Install dependencies
```

### Running
```bash
uv run maine-bills               # Scrape default session (131)
uv run maine-bills -s 132        # Scrape specific session
```

### Testing
```bash
uv run pytest tests/ -v          # Unit tests only (default, fast)
uv run pytest tests/ -v --cov    # With coverage report
uv run pytest tests/integration/ -v -m integration  # Integration tests (hits live website)
uv run pytest tests/ -v -m ""    # ALL tests (unit + integration)
```

### Code Quality
```bash
uv run ruff check src/ tests/    # Lint
uv run ruff format src/ tests/   # Format
```

## Architecture

### Current Code Structure

**Three main components:**

1. **`text_extractor.py`** - PDF extraction and metadata parsing
   - `BillDocument` dataclass: content-based metadata (title, sponsors, committee, amended_code_refs)
   - `TextExtractor.extract_bill_document()`: PyMuPDF-based extraction with text cleaning
   - Extracts metadata from bill content using regex patterns
   - Cleans text: removes line numbers, page headers/footers

2. **`scraper.py`** - Orchestration
   - `BillScraper` class: downloads PDFs, calls TextExtractor, saves output
   - Currently saves to `.txt` and `.json` files
   - Checks for existing `.txt` files to skip already-processed bills

3. **`cli.py`** - Entry point
   - Single session at a time: `-s/--session` flag
   - Output directory: `-o/--output-dir` flag

### Migration in Progress: HuggingFace Dataset

**See `docs/plans/2026-02-10-convert-to-hf.md` for complete plan.**

**Key architectural change: Hybrid metadata approach**

The migration combines two metadata sources:

1. **Filename-based** (reliable, always present):
   - Parse from filename pattern: `{session}-LD-{ld_number}[-{amendment_code}].pdf`
   - Example: `131-LD-0686-CA_A_H0266.pdf` → session=131, ld_number=0686, amendment_code=CA_A_H0266
   - Derives: chamber (House/Senate), amendment_type (Committee/House/Senate Amendment)

2. **Content-based** (rich, best-effort):
   - Already implemented in `text_extractor.py`
   - Extracts: title, sponsors, committee, amended_code_refs from bill text
   - May be null/empty if not found

**New dataclass: `BillRecord`** (to be added in `schema.py`)
- Combines `BillDocument` fields with filename-parsed fields
- Created via `BillRecord.from_filename_and_bill_document()`
- Converted to DataFrame → Parquet → uploaded to HuggingFace

**Migration phases:**
1. ✅ DONE: PyMuPDF extraction, content metadata, text cleaning
2. ✅ DONE: Migrate pyproject.toml from setuptools to uv + hatchling
3. ✅ DONE: Quality validation and cross-session testing (Phase 1.5)
4. 🔄 NEXT: HuggingFace setup (Phase 0 - 15 minutes)
5. TODO: Add `schema.py` with BillRecord + filename parsing
6. TODO: Add `publish.py` with HuggingFace upload logic
7. TODO: Update scraper to output DataFrame instead of .txt/.json
8. TODO: Update CLI for multi-session support and `--publish` flag

### Data Flow

**Current:**
```
Website → PDF list → Download PDF → TextExtractor → BillDocument → Save .txt + .json
```

**Target (post-migration):**
```
Website → PDF list → Download PDF → TextExtractor → BillDocument
  → Combine with filename parsing → BillRecord
  → DataFrame → Parquet → HuggingFace Hub
```

## Important Context

### Metadata Extraction Philosophy

**Why hybrid approach?**
- Filename parsing is 100% reliable but limited (just session/LD number/amendments)
- Content parsing is rich (title, sponsors) but fragile (regex-based, format varies)
- Combining both gives reliable structure + optional enrichment

**BillDocument vs BillRecord:**
- `BillDocument`: Content-only metadata from TextExtractor (current, stays as-is)
- `BillRecord`: Combines BillDocument + filename metadata (new, for HF dataset)

### Text Cleaning

The `TextExtractor` removes:
- Line numbers (both standalone and inline)
- Page headers/footers (e.g., "STATE OF MAINE", "Page 5")
- Bill ID headers
- Excessive blank lines

Keep this logic when refactoring - it significantly improves text quality.

### Extraction Quality Standards

**Production-ready quality achieved through iterative validation (2026-02-11):**

**Sponsor Extraction:**
- **Title Filter:** 33 words blocking false positives (leadership titles, government entities, document terms)
- **Pattern Support:** Senator, Representative, President, Speaker
- **Word-Level Filtering:** Prevents compound phrases like "Office of Education"
- **Accuracy:** 80-100% extraction on main bills, 0% false positives
- **Validated:** Sessions 125, 130, 131, 132 (2011-2026)

**Key Implementation Details:**
- Filter uses word-level intersection, not exact string matching
- Helper function `is_valid_name()` checks each word against title_words set
- Supports hyphenated names (TALBOT-ROSS), apostrophes (O'BRIEN)
- Handles both "of DISTRICT" and no-district formats
- Leadership bills (President/Speaker) extract correctly

**Error Patterns Documented:**
See `docs/ERROR-PATTERNS-CATALOG.md` for:
- 9 error pattern categories with examples
- Detection methods and test cases
- Validation commands for regression testing
- Cross-session format variations

**Quality Validation Process:**
See `docs/QUALITY-IMPROVEMENT-HISTORY.md` for:
- Complete 3-round improvement timeline
- Technical changes (filter 13→27→33 words)
- Cross-session validation results
- Lessons learned and ROI analysis

### Testing Strategy

**Unit tests** (`tests/unit/`): Mocked, fast
- Test extraction logic with fixtures
- Test metadata parsing
- Test text cleaning

**Integration tests** (`tests/integration/`): Hit live website
- Marked with `@pytest.mark.integration`
- Skipped by default (`-m 'not integration'` in pytest config)
- Use sparingly to avoid hitting Maine Legislature servers excessively

### Dependencies

**Current (Production-Ready):**
- `pymupdf` (fitz) - Primary PDF extraction library (fast, clean, reliable)
- `pypdf` - Legacy library, can be removed if confident
- `beautifulsoup4` + `requests` - Website scraping
- `pytest` + `pytest-mock` + `pytest-cov` - Testing infrastructure

**For HuggingFace migration (Phase 2+):**
- `huggingface-hub>=1.0` for dataset upload
- `pandas>=2.2` + `pyarrow>=18.0` for Parquet
- `datasets>=3.0` in dev dependencies for testing `load_dataset()`

### HuggingFace Publishing Pattern

**Direct upload, not `push_to_hub()`:**
- Each session = one parquet file uploaded via `HfApi.upload_file()`
- README.md with YAML config maps session numbers to file paths
- Xet chunk-level deduplication makes re-uploads efficient (only changed chunks transfer)
- Full rescrape per session is fine - simpler than tracking incremental changes

**Dataset card auto-generation:**
- `publish.py` will list all session folders in HF repo
- Generate YAML config entries for each session
- Upload README.md with updated configs

## Documentation Structure

**Persistent Reference Docs:**
- `docs/ERROR-PATTERNS-CATALOG.md` - Comprehensive error pattern reference (856 lines)
  - All 9 error pattern categories with examples
  - Detection methods and validation commands
  - Use for regression testing and quality validation

- `docs/QUALITY-IMPROVEMENT-HISTORY.md` - Complete quality improvement record (415 lines)
  - Timeline from baseline to production-ready
  - Technical changes and cross-session validation
  - Lessons learned and migration readiness

- `docs/DEVELOPMENT.md` - Ongoing development notes
  - Setup, testing, and common commands
  - Keep in sync with command changes

**Dated Plans (Historical Record):**
- `docs/plans/2026-02-10-convert-to-hf.md` - HuggingFace migration roadmap
- `docs/plans/2026-02-10-enhance-text-extraction.md` - Extraction enhancements
- `docs/plans/2026-02-10-extraction-feedback-loop-design.md` - Feedback loop design
- `docs/plans/2026-02-10-modernize-to-uv.md` - uv migration (completed)
- `docs/plans/phase-1.5-quality-gate.md` - Quality gate specification

**Documentation Philosophy:**
- Keep persistent reference docs (patterns, quality history)
- Preserve all dated plans as historical record
- Remove in-the-moment assessments and intermediate reports

## Git Workflow Notes

- `.worktrees/` directory is used for parallel feature development
- Migration plan updates go in `docs/plans/`
- Keep DEVELOPMENT.md in sync with command changes
- Quality validation complete - ready for HuggingFace migration
