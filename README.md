# Maine Bills Repository

This repository contains text extracted from the PDFs of bills hosted by the [Maine Legislature Law Library](https://legislature.maine.gov/lawLibrary).

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

## How It Works

### Overview
The scraper (`src/maine_bills/scraper.py`) performs these steps:

1. Fetches the list of available bills from the Maine Legislature website
2. Downloads each bill PDF
3. Extracts text using `pypdf`
4. Saves text to a `.txt` file
5. Cleans up the temporary PDF

### Architecture
- `TextExtractor`: Handles PDF text extraction
- `BillScraper`: Manages the download and processing workflow
- `cli`: Command-line interface

### CI/CD
The GitHub Actions workflow (`.github/workflows/scraper-uv.yml`) periodically runs the scraper to fetch new bills.

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
