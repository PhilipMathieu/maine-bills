# Maine Bills Dataset

High-quality text and metadata extraction from Maine Legislature bills. Ready for HuggingFace dataset migration with **80-100% sponsor extraction accuracy** and **zero quality issues** across 15 years of legislative history (2011-2026).

**Status:** Production-ready extraction system validated across 4 legislative sessions.

Data extracted from PDFs hosted by the [Maine Legislature Law Library](https://legislature.maine.gov/lawLibrary).

## Quick Start

### Prerequisites
- Python 3.9+
- [uv](https://astral.sh/uv/) for Python package management

### Installation

```bash
git clone https://github.com/PhilipMathieu/maine-bills.git
cd maine-bills
uv sync
```

### Running the Scraper

Scrape the default session (131):
```bash
uv run maine-bills
```

Scrape a specific session:
```bash
uv run maine-bills -s 132 -o ./data
```

For full documentation, see [DEVELOPMENT.md](docs/DEVELOPMENT.md).

## Using This Data

### Option 1: Clone the Repository
```bash
git clone https://github.com/PhilipMathieu/maine-bills.git
```

### Option 2: Use as a Git Submodule
```bash
cd [your project directory]
git submodule add https://github.com/PhilipMathieu/maine-bills data/maine-bills
```

## Data Structure

Bills are organized by legislative session:
```
data/
├── 130/txt/           # Session 130 bills
├── 131/txt/           # Session 131 bills
└── 132/txt/           # Session 132 bills (if available)
```

Each text file is named by legislative document number (e.g., `131-LD-0001.txt`).

## Quality Metrics

**Production-Ready Extraction System** (validated 2026-02-11):
- **Sponsor Extraction:** 80-100% on main bills (target: 60%)
- **False Positive Rate:** 0%
- **Sessions Validated:** 125, 130, 131, 132 (spanning 2011-2026)
- **Unit Test Coverage:** 54/54 tests passing (100%)
- **Quality Grade:** A+ across all sessions

See [QUALITY-IMPROVEMENT-HISTORY.md](docs/QUALITY-IMPROVEMENT-HISTORY.md) for complete quality validation details.

## How It Works

### Overview
The scraper (`src/maine_bills/scraper.py`) performs these steps:

1. Fetches the list of available bills from the Maine Legislature website
2. Downloads each bill PDF
3. Extracts text and metadata using PyMuPDF (fitz)
4. Applies intelligent text cleaning (removes line numbers, headers, footers)
5. Extracts structured metadata (sponsors, title, committee, session)
6. Saves text to `.txt` file and metadata to `.json` file

### Architecture

**Three main components:**

1. **`TextExtractor`** - Advanced PDF extraction with metadata parsing
   - PyMuPDF-based extraction with text cleaning
   - Regex-based metadata extraction (sponsors, title, committee)
   - Word-level filtering to prevent false positives
   - Supports Senator, Representative, President, Speaker titles

2. **`BillScraper`** - Download and processing workflow orchestration
   - Manages PDF downloads and extraction pipeline
   - Skips already-processed bills
   - Handles both main bills and amendments

3. **`cli`** - Command-line interface
   - Session selection (`-s/--session`)
   - Output directory configuration (`-o/--output-dir`)

### CI/CD
The GitHub Actions workflow (`.github/workflows/scraper-uv.yml`) periodically runs the scraper to fetch new bills.

## Documentation

### Essential Docs
- **[DEVELOPMENT.md](docs/DEVELOPMENT.md)** - Development setup, testing, and commands
- **[ERROR-PATTERNS-CATALOG.md](docs/ERROR-PATTERNS-CATALOG.md)** - Comprehensive error pattern reference (856 lines)
- **[QUALITY-IMPROVEMENT-HISTORY.md](docs/QUALITY-IMPROVEMENT-HISTORY.md)** - Quality validation timeline and results

### Plans
- **[HuggingFace Migration Plan](docs/plans/2026-02-10-convert-to-hf.md)** - Complete migration roadmap
- **[Quality Gate Specification](docs/plans/phase-1.5-quality-gate.md)** - Quality validation criteria

All documentation in `docs/` directory with dated plans in `docs/plans/`.

## Contributing

Contributions are welcome! To contribute:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests: `uv run pytest tests/`
5. Submit a pull request

See [DEVELOPMENT.md](docs/DEVELOPMENT.md) for more details on development setup and testing.

## License

The data extracted from Maine Legislature PDFs is used in accordance with the terms of the Law and Legislative Reference Library. This project is not officially affiliated with the Maine State Legislature.

The code is licensed under the MIT License (see LICENSE file).

Copyright 2023-2026 Philip Mathieu
