# Development Guide

## Setup

This project uses [uv](https://astral.sh/uv/) for Python dependency management.

### Prerequisites
- Python 3.9 or higher
- `uv` installed (`pip install uv` or see https://astral.sh/uv/)

### Installation

```bash
git clone https://github.com/PhilipMathieu/maine-bills.git
cd maine-bills
uv sync
```

## Running the Scraper

### Basic usage (scrape session 132, save locally)
```bash
uv run maine-bills
```

### Scrape multiple sessions
```bash
uv run maine-bills --sessions 131 132
```

### Scrape and publish to HuggingFace
```bash
uv run maine-bills --sessions 132 --publish
```

### Full release (all sessions)
```bash
uv run maine-bills --sessions 121 122 123 124 125 126 127 128 129 130 131 132 --publish
```

### Options
- `--sessions`: Legislative session number(s) (default: 132)
- `--publish`: Upload parquet files to HuggingFace Hub after scraping
- `--repo-id`: HuggingFace dataset repo ID (default: pem207/maine-bills)
- `--local-dir`: Local directory for parquet output (default: ./data)
- `--workers`: Number of parallel download workers (default: 8)

## Running Tests

### Unit tests only (default)
```bash
uv run pytest tests/ -v
```

### With coverage report
```bash
uv run pytest tests/ -v --cov
```

### Integration tests (hits live website)
```bash
uv run pytest tests/integration/ -v -m integration
```

### All tests
```bash
uv run pytest tests/ -v -m "" --cov
```

## Code Quality

### Linting and formatting
```bash
uv run ruff check src/ tests/
uv run ruff format src/ tests/
```

## Project Structure

```
maine-bills/
├── src/maine_bills/
│   ├── __init__.py              # Package initialization
│   ├── cli.py                   # Command-line interface
│   ├── scraper.py               # BillScraper class (download + extract)
│   ├── schema.py                # Filename parsing and BillRecord dataclass
│   ├── text_extractor.py        # TextExtractor class (PDF → text + metadata)
│   ├── publish.py               # HuggingFace upload and dataset card
│   └── sponsor_validation.py    # Optional sponsor name validation
├── tests/
│   ├── unit/                    # Unit tests (mocked)
│   └── integration/             # Integration tests (live)
├── docs/
│   ├── plans/                   # Implementation plans
│   └── DEVELOPMENT.md           # This file
├── data/                        # Bill data output (gitignored)
├── experiments/                 # Experiment notebooks (gitignored)
├── pyproject.toml               # Project configuration
└── uv.lock                      # Dependency lock file
```

## Filename Format

Maine legislative bill filenames follow a consistent pattern:

- **Original bills:** `{session}-LD-{number}` (e.g., `131-LD-0001`)
- **SP/HP/HO bills:** `{session}-SP-{number}`, `{session}-HP-{number}`, `{session}-HO-{number}`
- **Single amendments:** `{session}-LD-{number}-{type}_{version}_{chamber}{number}` (e.g., `131-LD-0686-CA_A_H0266`)
- **Double amendments:** `{session}-LD-{number}-{type}_{version}_{type}_{version}_{chamber}{number}` (e.g., `132-LD-0004-CA_A_SA_A_S337`)

Where:
- `type` = CA (Committee Amendment), HA (House Amendment), or SA (Senate Amendment)
- `version` = A, B, C, etc. (represents different versions of the same amendment)
- `chamber` = H (House) or S (Senate)

## Adding a New Legislative Session

```bash
uv run maine-bills --sessions 133 --publish
```

The scraper will:
1. Fetch all available bill PDFs from the Maine Legislature website
2. Download and extract text with parallel workers (progress bar shown)
3. Parse metadata from filenames and content
4. Save parquet locally to `data/{session}/`
5. Upload to HuggingFace (with `--publish`)
6. Update the dataset card with the new session config

## Troubleshooting

### "command not found: uv"
Install uv: `pip install uv`

### Tests fail with import errors
Make sure `uv sync` was run to install dependencies.

### Network errors during scraping
The scraper retries timeouts up to 3 times with exponential backoff. Failed bills are logged and skipped.

### HuggingFace upload fails
Ensure you're logged in: `huggingface-cli login`
