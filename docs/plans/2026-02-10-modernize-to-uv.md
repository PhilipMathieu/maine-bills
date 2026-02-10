# Maine Bills Modernization to UV Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Convert maine-bills scraper from conda/old Python to modern uv-based project with comprehensive tests, refactored code architecture, and support for newer legislative sessions.

**Architecture:**
- Modern Python package structure using `uv` for dependency management
- Refactor monolithic scraper into testable classes (TextExtractor, BillScraper)
- Separate unit tests (mocked) from integration tests (live website)
- Support dynamic session detection and multi-session scraping

**Tech Stack:** Python 3.9+, uv, pytest (with pytest-mock and pytest-cov), requests, beautifulsoup4, pypdf

---

## Task 1: Create pyproject.toml and uv configuration

**Files:**
- Create: `pyproject.toml`
- Delete: `environment.yml`, `setup-miniconda-patched-environment.yml`

**Step 1: Write pyproject.toml**

```toml
[build-system]
requires = ["setuptools>=68.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "maine-bills"
version = "2.0.0"
description = "Scraper for Maine legislature bills"
readme = "README.md"
license = {text = "MIT"}
authors = [{name = "Philip Mathieu"}]
requires-python = ">=3.9"
dependencies = [
    "requests>=2.31.0",
    "beautifulsoup4>=4.12.0",
    "pypdf>=4.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.4.0",
    "pytest-cov>=4.1.0",
    "pytest-mock>=3.11.0",
    "ruff>=0.1.0",
]

[project.scripts]
maine-bills = "maine_bills.cli:main"

[tool.pytest.ini_options]
minversion = "7.0"
testpaths = ["tests"]
python_files = ["test_*.py"]
addopts = "-v --cov=src/maine_bills --cov-report=term-out --cov-report=html"

[tool.ruff]
line-length = 100
target-version = "py39"

[tool.ruff.lint]
select = ["E", "F", "W", "I"]
ignore = ["E501"]  # Allow long lines (handled by formatter)
```

**Step 2: Delete old conda files**

```bash
rm environment.yml setup-miniconda-patched-environment.yml
```

**Step 3: Initialize uv project**

```bash
cd ~/.config/superpowers/worktrees/maine-bills/modernize-to-uv
uv sync
```

Expected: Creates `uv.lock` with all dependencies resolved

**Step 4: Verify uv.lock is created**

```bash
ls -la uv.lock
```

Expected: `uv.lock` exists (binary lock file)

**Step 5: Commit**

```bash
git add pyproject.toml uv.lock
git rm environment.yml setup-miniconda-patched-environment.yml
git commit -m "build: convert to uv project management

- Create pyproject.toml with modern dependencies
- Remove old conda environment files
- Initialize uv.lock for reproducible builds"
```

---

## Task 2: Create modern package structure

**Files:**
- Create: `src/maine_bills/__init__.py`
- Create: `src/maine_bills/text_extractor.py`
- Modify: `src/scraper.py` (move to archive, will replace)
- Create: `src/maine_bills/scraper.py` (refactored)
- Create: `src/maine_bills/cli.py` (command line interface)
- Create: `tests/__init__.py`
- Create: `tests/unit/__init__.py`
- Create: `tests/integration/__init__.py`

**Step 1: Create package init files**

```bash
mkdir -p src/maine_bills tests/unit tests/integration
touch src/maine_bills/__init__.py tests/__init__.py tests/unit/__init__.py tests/integration/__init__.py
```

**Step 2: Create text_extractor.py**

```python
# src/maine_bills/text_extractor.py
from pathlib import Path
from typing import List
from pypdf import PdfReader


class TextExtractor:
    """Extracts text from PDF bill documents."""

    @staticmethod
    def extract_from_pdf(pdf_path: Path) -> str:
        """
        Extract all text from a PDF file.

        Args:
            pdf_path: Path to the PDF file

        Returns:
            Extracted text with newlines preserved

        Raises:
            FileNotFoundError: If PDF file doesn't exist
            Exception: If PDF parsing fails
        """
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        reader = PdfReader(pdf_path)
        lines: List[str] = []

        for page in reader.pages:
            text_all = page.extract_text()
            lines.extend(text_all.split('\n'))

        return '\n'.join(lines)

    @staticmethod
    def save_text(output_path: Path, text: str) -> None:
        """
        Save extracted text to a file.

        Args:
            output_path: Path where text file should be written
            text: Text content to save

        Raises:
            IOError: If file write fails
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w') as f:
            f.write(text)
```

**Step 3: Create scraper.py (refactored)**

```python
# src/maine_bills/scraper.py
import logging
from pathlib import Path
from typing import List, Optional
import requests
from bs4 import BeautifulSoup
from .text_extractor import TextExtractor


class BillScraper:
    """Scrapes Maine legislature bills from the official website."""

    BASE_URL = "http://lldc.mainelegislature.org/Open/LDs"
    TIMEOUT = 10

    def __init__(self, session: str, output_dir: Path, logger: Optional[logging.Logger] = None):
        """
        Initialize the bill scraper.

        Args:
            session: Legislative session number (e.g., "131")
            output_dir: Base directory for storing bills
            logger: Optional logger instance
        """
        self.session = session
        self.output_dir = Path(output_dir)
        self.logger = logger or logging.getLogger(__name__)
        self.session_url = f"{self.BASE_URL}/{session}/"
        self.pdf_dir = self.output_dir / "pdf"
        self.txt_dir = self.output_dir / "txt"

    def _ensure_directories(self) -> None:
        """Create necessary directories if they don't exist."""
        self.pdf_dir.mkdir(parents=True, exist_ok=True)
        self.txt_dir.mkdir(parents=True, exist_ok=True)

    def _bill_already_processed(self, bill_id: str) -> bool:
        """
        Check if a bill has already been processed.

        Args:
            bill_id: Legislative document number

        Returns:
            True if text file exists, False otherwise
        """
        return (self.txt_dir / f"{bill_id}.txt").exists()

    def _fetch_bill_list(self) -> List[str]:
        """
        Fetch list of bill IDs from the legislature website.

        Returns:
            List of bill IDs (e.g., ["131-LD-0001", "131-LD-0002", ...])

        Raises:
            requests.RequestException: If fetching fails
        """
        self.logger.debug(f"Fetching bill list from {self.session_url}")
        res = requests.get(self.session_url, timeout=self.TIMEOUT)
        res.raise_for_status()

        soup = BeautifulSoup(res.content, features="html.parser")
        hrefs = [a.attrs["href"] for a in soup.find_all("a")[1:]]
        bill_ids = [href.split('/')[-1][:-4] for href in hrefs]

        self.logger.info(f"Found {len(bill_ids)} bills in session {self.session}")
        return bill_ids

    def _download_bill_pdf(self, bill_id: str) -> bool:
        """
        Download a single bill PDF.

        Args:
            bill_id: Legislative document number

        Returns:
            True if successful, False otherwise
        """
        pdf_url = f"{self.session_url}{bill_id}.pdf"
        pdf_path = self.pdf_dir / f"{bill_id}.pdf"

        try:
            self.logger.debug(f"Downloading PDF for {bill_id}")
            res = requests.get(pdf_url, timeout=self.TIMEOUT)
            res.raise_for_status()

            with open(pdf_path, 'wb') as f:
                f.write(res.content)

            self.logger.debug(f"Successfully downloaded {bill_id}")
            return True

        except requests.exceptions.RequestException as e:
            self.logger.warning(f"Download error for {bill_id}: {e}")
            return False
        except IOError as e:
            self.logger.warning(f"Could not write PDF for {bill_id}: {e}")
            return False

    def _process_bill(self, bill_id: str) -> bool:
        """
        Process a single bill: download PDF, extract text, clean up.

        Args:
            bill_id: Legislative document number

        Returns:
            True if successful, False otherwise
        """
        if self._bill_already_processed(bill_id):
            self.logger.debug(f"{bill_id} already in corpus")
            return False

        self.logger.info(f"Processing {bill_id}")

        if not self._download_bill_pdf(bill_id):
            return False

        try:
            pdf_path = self.pdf_dir / f"{bill_id}.pdf"
            text = TextExtractor.extract_from_pdf(pdf_path)
            txt_path = self.txt_dir / f"{bill_id}.txt"
            TextExtractor.save_text(txt_path, text)

            pdf_path.unlink()  # Remove PDF after extraction
            self.logger.debug(f"Extracted and cleaned up {bill_id}")
            return True

        except Exception as e:
            self.logger.error(f"Error processing {bill_id}: {e}")
            return False

    def scrape_session(self) -> int:
        """
        Scrape all bills in the configured session.

        Returns:
            Number of newly processed bills

        Raises:
            requests.RequestException: If fetching bill list fails
        """
        self._ensure_directories()
        self.logger.info(f"######### NEW RUN: Session {self.session} #########")

        bill_ids = self._fetch_bill_list()
        new_count = 0

        for bill_id in bill_ids:
            if self._process_bill(bill_id):
                new_count += 1

        self.logger.info(f"Added {new_count} new bills to corpus")
        return new_count
```

**Step 4: Create cli.py**

```python
# src/maine_bills/cli.py
import argparse
import logging
import sys
from pathlib import Path
from .scraper import BillScraper


def setup_logging(log_file: Path, level: int = logging.INFO) -> logging.Logger:
    """Set up logging to both file and console."""
    logger = logging.getLogger("maine_bills")
    logger.setLevel(level)

    # File handler
    log_file.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(level)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)

    # Formatter
    formatter = logging.Formatter(
        "%(asctime)s:%(levelname)s:%(message)s"
    )
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


def main() -> int:
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(
        description="Scrape Maine legislature bills"
    )
    parser.add_argument(
        "-s", "--session",
        default="131",
        type=str,
        help="Legislative session number (default: 131)"
    )
    parser.add_argument(
        "-o", "--output-dir",
        default="./",
        type=str,
        help="Output directory for bill data (default: ./)"
    )

    args = parser.parse_args()
    output_dir = Path(args.output_dir) / args.session
    log_file = output_dir / "scraper.log"

    logger = setup_logging(log_file)

    try:
        scraper = BillScraper(args.session, output_dir, logger)
        new_count = scraper.scrape_session()
        logger.info(f"Scraping complete: {new_count} new bills added")
        return 0

    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
```

**Step 5: Move old scraper**

```bash
mv src/scraper.py src/scraper.py.bak
```

**Step 6: Commit**

```bash
git add src/maine_bills/ tests/
git commit -m "refactor: restructure as modern Python package

- Create maine_bills package with TextExtractor and BillScraper classes
- Add CLI entry point for command-line usage
- Separate concerns: PDF extraction, scraping logic, CLI
- Add type hints throughout
- Create test directory structure"
```

---

## Task 3: Write unit tests for TextExtractor

**Files:**
- Create: `tests/unit/test_text_extractor.py`

**Step 1: Create test file with failing tests**

```python
# tests/unit/test_text_extractor.py
import pytest
from pathlib import Path
from unittest.mock import Mock, patch
from maine_bills.text_extractor import TextExtractor


def test_extract_from_pdf_missing_file():
    """Test that extraction fails with missing file."""
    with pytest.raises(FileNotFoundError):
        TextExtractor.extract_from_pdf(Path("/nonexistent/file.pdf"))


def test_extract_from_pdf_success(tmp_path, mocker):
    """Test successful PDF text extraction."""
    # Mock PdfReader
    mock_page = Mock()
    mock_page.extract_text.return_value = "Page 1\nContent"

    mock_reader = Mock()
    mock_reader.pages = [mock_page]

    pdf_path = tmp_path / "test.pdf"
    pdf_path.touch()

    with patch('maine_bills.text_extractor.PdfReader', return_value=mock_reader):
        result = TextExtractor.extract_from_pdf(pdf_path)
        assert "Page 1" in result
        assert "Content" in result


def test_extract_from_pdf_multiple_pages(tmp_path, mocker):
    """Test extraction from PDF with multiple pages."""
    mock_page1 = Mock()
    mock_page1.extract_text.return_value = "Page 1\nContent 1"

    mock_page2 = Mock()
    mock_page2.extract_text.return_value = "Page 2\nContent 2"

    mock_reader = Mock()
    mock_reader.pages = [mock_page1, mock_page2]

    pdf_path = tmp_path / "test.pdf"
    pdf_path.touch()

    with patch('maine_bills.text_extractor.PdfReader', return_value=mock_reader):
        result = TextExtractor.extract_from_pdf(pdf_path)
        assert "Page 1" in result
        assert "Page 2" in result
        assert "Content 1" in result
        assert "Content 2" in result


def test_save_text_creates_file(tmp_path):
    """Test that save_text creates output file."""
    output_path = tmp_path / "subdir" / "output.txt"
    text = "Test content\nWith multiple lines"

    TextExtractor.save_text(output_path, text)

    assert output_path.exists()
    assert output_path.read_text() == text


def test_save_text_creates_parents(tmp_path):
    """Test that save_text creates parent directories."""
    output_path = tmp_path / "deep" / "nested" / "output.txt"
    text = "Content"

    TextExtractor.save_text(output_path, text)

    assert output_path.parent.exists()
    assert output_path.exists()
```

**Step 2: Run tests to verify they fail initially**

```bash
cd ~/.config/superpowers/worktrees/maine-bills/modernize-to-uv
uv run pytest tests/unit/test_text_extractor.py -v
```

Expected: Tests fail because TextExtractor doesn't exist or is incomplete

**Step 3: Run tests to verify they pass**

```bash
uv run pytest tests/unit/test_text_extractor.py -v
```

Expected: All tests pass

**Step 4: Commit**

```bash
git add tests/unit/test_text_extractor.py
git commit -m "test: add unit tests for TextExtractor

- Test missing file handling
- Test single and multiple page PDF extraction
- Test file writing and directory creation
- All tests use mocks to avoid external dependencies"
```

---

## Task 4: Write unit tests for BillScraper

**Files:**
- Create: `tests/unit/test_scraper.py`

**Step 1: Create test file**

```python
# tests/unit/test_scraper.py
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from maine_bills.scraper import BillScraper


@pytest.fixture
def scraper(tmp_path):
    """Create a BillScraper instance for testing."""
    return BillScraper("131", tmp_path)


def test_scraper_init(scraper, tmp_path):
    """Test scraper initialization."""
    assert scraper.session == "131"
    assert scraper.output_dir == tmp_path
    assert scraper.pdf_dir == tmp_path / "pdf"
    assert scraper.txt_dir == tmp_path / "txt"


def test_ensure_directories(scraper):
    """Test that directory creation works."""
    scraper._ensure_directories()
    assert scraper.pdf_dir.exists()
    assert scraper.txt_dir.exists()


def test_bill_already_processed(scraper, tmp_path):
    """Test checking if bill was already processed."""
    # Create a txt file to simulate processed bill
    scraper._ensure_directories()
    (scraper.txt_dir / "131-LD-0001.txt").touch()

    assert scraper._bill_already_processed("131-LD-0001") is True
    assert scraper._bill_already_processed("131-LD-0002") is False


def test_fetch_bill_list_success(scraper, mocker):
    """Test successful bill list fetching."""
    mock_html = """
    <html>
        <a href="../">Parent</a>
        <a href="131-LD-0001.pdf/">Link 1</a>
        <a href="131-LD-0002.pdf/">Link 2</a>
    </html>
    """

    mock_response = Mock()
    mock_response.content = mock_html.encode()

    mocker.patch('maine_bills.scraper.requests.get', return_value=mock_response)

    result = scraper._fetch_bill_list()

    assert len(result) == 2
    assert "131-LD-0001" in result
    assert "131-LD-0002" in result


def test_fetch_bill_list_failure(scraper, mocker):
    """Test bill list fetching with network error."""
    import requests

    mocker.patch(
        'maine_bills.scraper.requests.get',
        side_effect=requests.RequestException("Network error")
    )

    with pytest.raises(requests.RequestException):
        scraper._fetch_bill_list()


def test_download_bill_pdf_success(scraper, mocker):
    """Test successful PDF download."""
    scraper._ensure_directories()

    mock_response = Mock()
    mock_response.content = b"PDF content"

    mocker.patch('maine_bills.scraper.requests.get', return_value=mock_response)

    result = scraper._download_bill_pdf("131-LD-0001")

    assert result is True
    assert (scraper.pdf_dir / "131-LD-0001.pdf").exists()


def test_download_bill_pdf_failure(scraper, mocker):
    """Test PDF download failure."""
    import requests

    scraper._ensure_directories()

    mocker.patch(
        'maine_bills.scraper.requests.get',
        side_effect=requests.RequestException("Download failed")
    )

    result = scraper._download_bill_pdf("131-LD-0001")

    assert result is False


def test_process_bill_already_processed(scraper):
    """Test that already-processed bills are skipped."""
    scraper._ensure_directories()
    (scraper.txt_dir / "131-LD-0001.txt").touch()

    result = scraper._process_bill("131-LD-0001")

    assert result is False


def test_process_bill_success(scraper, mocker):
    """Test successful bill processing."""
    scraper._ensure_directories()

    # Mock download
    mock_response = Mock()
    mock_response.content = b"PDF"
    mocker.patch('maine_bills.scraper.requests.get', return_value=mock_response)

    # Mock text extraction
    mocker.patch(
        'maine_bills.scraper.TextExtractor.extract_from_pdf',
        return_value="Extracted text"
    )
    mocker.patch('maine_bills.scraper.TextExtractor.save_text')

    result = scraper._process_bill("131-LD-0001")

    assert result is True


def test_scrape_session_complete(scraper, mocker):
    """Test complete scraping session."""
    scraper._ensure_directories()

    # Mock bill list
    mocker.patch.object(
        scraper,
        '_fetch_bill_list',
        return_value=["131-LD-0001", "131-LD-0002"]
    )

    # Mock process_bill to succeed twice
    mocker.patch.object(scraper, '_process_bill', return_value=True)

    result = scraper.scrape_session()

    assert result == 2
```

**Step 2: Run tests to verify they pass**

```bash
uv run pytest tests/unit/test_scraper.py -v
```

Expected: All tests pass

**Step 3: Commit**

```bash
git add tests/unit/test_scraper.py
git commit -m "test: add comprehensive unit tests for BillScraper

- Test initialization and configuration
- Test directory creation
- Test bill deduplication logic
- Test HTTP request mocking (successful and failed downloads)
- Test complete scraping workflow with mocks
- All tests use pytest-mock for external dependencies"
```

---

## Task 5: Write integration tests

**Files:**
- Create: `tests/integration/test_scraper_live.py`

**Step 1: Create integration test file**

```python
# tests/integration/test_scraper_live.py
import pytest
from pathlib import Path
from maine_bills.scraper import BillScraper


@pytest.mark.integration
def test_fetch_real_bill_list():
    """Test fetching bill list from real legislature website.

    This test hits the actual Maine legislature website.
    Skip with -m "not integration" if you don't want live tests.
    """
    scraper = BillScraper("131", Path("/tmp/maine-bills-integration"))

    try:
        bills = scraper._fetch_bill_list()
        assert len(bills) > 0
        assert any("LD" in bill for bill in bills)
    except Exception as e:
        pytest.skip(f"Integration test skipped: {e}")


@pytest.mark.integration
def test_scrape_single_bill():
    """Test downloading and extracting a single real bill.

    This test hits the actual Maine legislature website.
    Skip with -m "not integration" if you don't want live tests.
    """
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        scraper = BillScraper("131", Path(tmpdir))
        scraper._ensure_directories()

        try:
            bills = scraper._fetch_bill_list()
            if not bills:
                pytest.skip("No bills found to test")

            # Try processing the first bill
            result = scraper._process_bill(bills[0])

            # Should succeed if bill is available
            if result:
                assert (scraper.txt_dir / f"{bills[0]}.txt").exists()
        except Exception as e:
            pytest.skip(f"Integration test skipped: {e}")
```

**Step 2: Update pytest configuration in pyproject.toml**

Add marker configuration:

```toml
[tool.pytest.ini_options]
minversion = "7.0"
testpaths = ["tests"]
python_files = ["test_*.py"]
addopts = "-v --cov=src/maine_bills --cov-report=term-out --cov-report=html -m 'not integration'"
markers = [
    "integration: marks tests as integration tests that hit external services",
]
```

**Step 3: Run unit tests only (integration skipped by default)**

```bash
uv run pytest tests/ -v
```

Expected: All unit tests pass, integration tests skipped

**Step 4: Run integration tests explicitly**

```bash
uv run pytest tests/integration/ -v -m integration
```

Expected: Integration tests run and verify website is accessible

**Step 5: Commit**

```bash
git add tests/integration/test_scraper_live.py pyproject.toml
git commit -m "test: add integration tests for live website

- Add tests that verify against real Maine legislature website
- Mark with @pytest.mark.integration to keep them separate
- Configure pytest to skip integration by default
- Allow explicit run with -m integration flag"
```

---

## Task 6: Update documentation and README

**Files:**
- Modify: `README.md`
- Create: `DEVELOPMENT.md`
- Create: `.github/workflows/scraper-uv.yml` (new workflow for uv)

**Step 1: Create DEVELOPMENT.md**

```markdown
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
```

**Step 2: Update README.md**

```markdown
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
```

**Step 3: Create GitHub Actions workflow for uv**

```yaml
# .github/workflows/scraper-uv.yml
name: Scrape Maine Bills

on:
  schedule:
    # Run monthly on the first day of the month
    - cron: '0 0 1 * *'
  workflow_dispatch:

jobs:
  scrape:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v2

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: uv sync

      - name: Run tests
        run: uv run pytest tests/ -v -m "not integration"

      - name: Scrape current session
        run: |
          uv run maine-bills -s 131 -o ./data
          uv run maine-bills -s 132 -o ./data || true

      - name: Commit and push changes
        run: |
          git config user.name "Maine Bills Bot"
          git config user.email "bot@maine-bills.local"
          git add data/
          if ! git diff-index --quiet HEAD --; then
            git commit -m "chore: update bills data"
            git push
          fi
```

**Step 4: Commit documentation changes**

```bash
git add README.md docs/DEVELOPMENT.md .github/workflows/scraper-uv.yml
git rm .github/workflows/run-with-conda.yml
git commit -m "docs: update for uv-based modernization

- Rewrite README with uv setup instructions
- Add comprehensive DEVELOPMENT.md guide
- Create new GitHub Actions workflow using uv
- Remove old conda-based workflow"
```

---

## Task 7: Test run the scraper

**Files:**
- No new files, just verification

**Step 1: Run unit tests to verify everything works**

```bash
cd ~/.config/superpowers/worktrees/maine-bills/modernize-to-uv
uv run pytest tests/unit/ -v --cov
```

Expected: All unit tests pass with >80% coverage

**Step 2: Attempt a small integration test**

```bash
uv run pytest tests/integration/ -v -m integration -k "fetch_real" 2>&1 | head -50
```

Expected: Either passes (website accessible) or gracefully skips with reason

**Step 3: Run the CLI with dry-run check**

```bash
uv run maine-bills --help
```

Expected: Displays help message with session and output-dir options

**Step 4: Test scraping session 131 (small run)**

```bash
mkdir -p /tmp/maine-bills-test
uv run maine-bills -s 131 -o /tmp/maine-bills-test 2>&1 | head -20
```

Expected: Starts processing bills, logs activity

**Step 5: Verify output structure**

```bash
ls -la /tmp/maine-bills-test/131/txt/ | head -10
ls -la /tmp/maine-bills-test/131/ | grep -i log
```

Expected: Text files created, scraper.log exists

**Step 6: Final commit**

```bash
git add -A
git commit -m "test: verify scraper runs end-to-end

- All unit tests passing with good coverage
- Integration tests skip gracefully if website unavailable
- CLI runs successfully
- Scraper can process bills and create output files
- Ready for production use"
```

---

## Task 8: Add newer legislative sessions

**Files:**
- Modify: `src/maine_bills/scraper.py` (add session detection)
- Create: `tests/unit/test_session_detection.py`

**Step 1: Add session detection to BillScraper**

```python
# Add to src/maine_bills/scraper.py, add new method:

@staticmethod
def get_available_sessions() -> List[str]:
    """
    Fetch list of available legislative sessions from the website.

    Returns:
        List of session numbers (e.g., ["130", "131", "132", ...])

    Raises:
        requests.RequestException: If fetching fails
    """
    base_url = "http://lldc.mainelegislature.org/Open/LDs/"
    res = requests.get(base_url, timeout=BillScraper.TIMEOUT)
    res.raise_for_status()

    soup = BeautifulSoup(res.content, features="html.parser")
    hrefs = [a.attrs["href"] for a in soup.find_all("a")]

    sessions = []
    for href in hrefs:
        # Session directories look like "130/", "131/", etc.
        parts = href.strip('/').split('/')
        if parts and parts[-1].isdigit():
            sessions.append(parts[-1])

    return sorted(set(sessions), reverse=True)
```

**Step 2: Update CLI to support multi-session scraping**

```python
# Update src/maine_bills/cli.py main() function:

def main() -> int:
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(
        description="Scrape Maine legislature bills"
    )
    parser.add_argument(
        "-s", "--session",
        type=str,
        help="Legislative session number (e.g., 131). If not specified, scrapes all available sessions."
    )
    parser.add_argument(
        "-o", "--output-dir",
        default="./",
        type=str,
        help="Output directory for bill data (default: ./)"
    )

    args = parser.parse_args()
    output_dir = Path(args.output_dir)

    try:
        if args.session:
            # Scrape specific session
            sessions = [args.session]
        else:
            # Scrape all available sessions
            sessions = BillScraper.get_available_sessions()

        for session in sessions:
            session_output = output_dir / session
            log_file = session_output / "scraper.log"

            logger = setup_logging(log_file)
            scraper = BillScraper(session, session_output, logger)
            new_count = scraper.scrape_session()
            logger.info(f"Session {session}: {new_count} new bills added")

        return 0

    except Exception as e:
        import logging
        logging.error(f"Fatal error: {e}", exc_info=True)
        return 1
```

**Step 3: Write tests for session detection**

```python
# tests/unit/test_session_detection.py
import pytest
from unittest.mock import Mock, patch
from maine_bills.scraper import BillScraper


def test_get_available_sessions(mocker):
    """Test fetching available session list."""
    mock_html = """
    <html>
        <a href="130/">Session 130</a>
        <a href="131/">Session 131</a>
        <a href="132/">Session 132</a>
    </html>
    """

    mock_response = Mock()
    mock_response.content = mock_html.encode()

    mocker.patch('maine_bills.scraper.requests.get', return_value=mock_response)

    sessions = BillScraper.get_available_sessions()

    assert "130" in sessions
    assert "131" in sessions
    assert "132" in sessions
    assert sessions[-1] == "132"  # Should be sorted descending
```

**Step 4: Run new tests**

```bash
uv run pytest tests/unit/test_session_detection.py -v
```

Expected: Tests pass

**Step 5: Test multi-session scraping**

```bash
# This will try to scrape all available sessions
timeout 30 uv run maine-bills -o /tmp/maine-bills-all 2>&1 | head -30 || true
```

Expected: Scraper starts, identifies available sessions, begins scraping

**Step 6: Commit**

```bash
git add src/maine_bills/scraper.py src/maine_bills/cli.py tests/unit/test_session_detection.py
git commit -m "feat: add support for scraping all available sessions

- Add get_available_sessions() to detect sessions from website
- Update CLI to scrape all sessions when none specified
- Add tests for session detection
- Enables automatic discovery of new legislative sessions"
```

---

## Summary

This implementation plan modernizes maine-bills through 8 focused tasks:

1. **Project Setup** - Convert to uv with pyproject.toml
2. **Package Structure** - Create maine_bills package with classes
3. **Unit Tests (TextExtractor)** - Test PDF extraction with mocks
4. **Unit Tests (BillScraper)** - Test scraping logic with mocks
5. **Integration Tests** - Verify against real website
6. **Documentation** - Update README and add DEVELOPMENT.md
7. **Test Run** - Verify scraper works end-to-end
8. **Multi-Session Support** - Scrape all available sessions

**Final result:**
- ✅ Modern Python package using uv
- ✅ Refactored code into testable classes
- ✅ Comprehensive test coverage (unit + integration)
- ✅ Command-line interface
- ✅ Multi-session support
- ✅ Updated documentation
- ✅ GitHub Actions workflow

Each task is a complete, testable unit that can be committed independently.
