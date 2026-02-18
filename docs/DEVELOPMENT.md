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

### Basic usage (scrape session 131)
```bash
uv run maine-bills
```

### Scrape specific session
```bash
uv run maine-bills -s 132 -o ./data
```

### Options
- `-s, --session`: Legislative session number (default: 131)
- `-o, --output-dir`: Output directory for bill data (default: ./)

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
│   ├── __init__.py           # Package initialization
│   ├── cli.py                # Command-line interface
│   ├── scraper.py            # BillScraper class
│   ├── schema.py             # Filename parsing and BillRecord dataclass
│   └── text_extractor.py     # TextExtractor class
├── tests/
│   ├── unit/                 # Unit tests (mocked)
│   └── integration/          # Integration tests (live)
├── docs/
│   ├── plans/                # Implementation plans
│   └── DEVELOPMENT.md        # This file
├── data/                     # Bill data (generated)
├── pyproject.toml            # Project configuration
└── uv.lock                   # Dependency lock file
```

## Filename Format

Maine legislative bill filenames follow a consistent pattern:

- **Original bills:** `{session}-LD-{number}` (e.g., `131-LD-0001`)
- **Single amendments:** `{session}-LD-{number}-{type}_{version}_{chamber}{number}` (e.g., `131-LD-0686-CA_A_H0266`)
- **Double amendments:** `{session}-LD-{number}-{type}_{version}_{type}_{version}_{chamber}{number}` (e.g., `132-LD-0004-CA_A_SA_A_S337`)

Where:
- `type` = CA (Committee Amendment), HA (House Amendment), or SA (Senate Amendment)
- `version` = A, B, C, etc. (represents different versions of the same amendment)
- `chamber` = H (House) or S (Senate)

The `schema.py` module provides:
- `parse_filename()` function to extract metadata from filenames
- `BillRecord` dataclass to combine filename metadata with extracted content
- Support for both single-level and nested (double) amendments

## Adding a New Legislative Session

To scrape a new session:

```bash
uv run maine-bills -s 132 -o ./data
```

The scraper will:
1. Fetch all available bills from session 132
2. Download PDFs
3. Extract text
4. Save to `data/132/txt/`
5. Skip any bills already processed

## Troubleshooting

### "command not found: uv"
Install uv: `pip install uv`

### Tests fail with import errors
Make sure `uv sync` was run to install dependencies

### Network errors during scraping
The scraper will log errors and retry on next run. Already-processed bills are never re-downloaded.
