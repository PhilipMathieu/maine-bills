# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A Python scraper for Maine Legislature bills that extracts text and metadata from PDFs and publishes structured Parquet files to HuggingFace Hub at `pem207/maine-bills`.

**Current state:** Production pipeline covering sessions 121-132 (2003-2026)
**Dataset:** `pem207/maine-bills` on HuggingFace Hub

**Quality Status (2026-02-18):**
- 151 unit tests passing, 88% coverage
- Sponsor extraction: ~98% accuracy against OpenStates, 0 garbage false positives
- Validated across sessions 121-132
- Progress bars via tqdm for long scrape runs

## Essential Commands

### Setup
```bash
uv sync                          # Install dependencies
```

### Running
```bash
uv run maine-bills                                    # Scrape default session (132)
uv run maine-bills --sessions 131 132                 # Multiple sessions
uv run maine-bills --sessions 132 --publish           # Scrape and upload to HuggingFace
uv run maine-bills --sessions 121 122 ... 132 --publish  # Full release
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

### Code Structure

```
src/maine_bills/
├── cli.py                 # Entry point (--sessions, --publish, --workers)
├── scraper.py             # BillScraper: downloads PDFs, extracts, produces DataFrame
├── text_extractor.py      # TextExtractor: PyMuPDF extraction + metadata parsing
├── schema.py              # BillRecord dataclass + filename parsing
├── publish.py             # HuggingFace upload + dataset card generation
└── sponsor_validation.py  # Optional sponsor filtering against known legislator lists
```

**Key classes:**
- `BillDocument` (text_extractor.py): Content-based metadata (title, sponsors, committee)
- `BillRecord` (schema.py): Combines BillDocument + filename metadata for HF dataset
- `BillScraper` (scraper.py): Orchestrates download → extract → DataFrame pipeline

### Data Flow

```
Website → PDF list → Download PDF → TextExtractor → BillDocument
  → Combine with filename parsing → BillRecord
  → DataFrame → Parquet → HuggingFace Hub
```

## Important Context

### Metadata Extraction

**Hybrid approach — two metadata sources:**
1. **Filename-based** (reliable): session, LD number, amendment code, chamber, amendment type
2. **Content-based** (best-effort): title, sponsors, committee, amended code refs

### Sponsor Extraction

All sponsor patterns require a `Senator/Representative/President/Speaker` prefix — this prevents false positives from bill text like "Town of Brunswick" or "University of Maine".

**Key details:**
- Title filter: 34 words blocking false positives (leadership titles, government entities, etc.)
- Word-level filtering via `is_valid_name()` checks each word against title_words set
- Hyphenated names normalized (stray spaces collapsed: `BEEBE- CENTER` → `BEEBE-CENTER`)
- `sponsor_validation.py`: optional post-processing to filter against known legislator lists (e.g., OpenStates)

### Text Cleaning

The `TextExtractor` removes:
- Line numbers (both standalone and inline)
- Page headers/footers (e.g., "STATE OF MAINE", "Page 5")
- Bill ID headers
- Excessive blank lines

### HuggingFace Publishing

- Each session = one parquet file uploaded via `HfApi.upload_file()`
- `sync_dataset_card()` auto-generates README.md with per-session configs
- Full rescrape per session on each release (simpler than tracking incremental changes)

### Testing Strategy

**Unit tests** (`tests/unit/`): Mocked, fast
- Extraction logic, metadata parsing, text cleaning, sponsor quality, schema

**Integration tests** (`tests/integration/`): Hit live website
- Marked with `@pytest.mark.integration`, skipped by default

### Dependencies

**Runtime:** pymupdf, beautifulsoup4, requests, tenacity, pandas, pyarrow, huggingface-hub, tqdm
**Dev:** pytest, pytest-mock, pytest-cov, ruff, jupyter, python-dotenv, rapidfuzz

## Documentation

- `docs/ERROR-PATTERNS-CATALOG.md` - Error pattern reference
- `docs/QUALITY-IMPROVEMENT-HISTORY.md` - Quality improvement record
- `docs/DEVELOPMENT.md` - Setup and development guide
- `docs/plans/` - Historical implementation plans

## Git Workflow

- `.worktrees/` directory for parallel feature development
- `data/` and `experiments/` are gitignored
