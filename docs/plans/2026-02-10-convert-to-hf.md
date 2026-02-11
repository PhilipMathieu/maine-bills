# maine-bills Migration Plan: HuggingFace Datasets

## Plan Status: UPDATED After Feature Merge (2026-02-10)

**What changed:** The `feature/enhance-text-extraction` branch was merged, adding:
- ✅ PyMuPDF dependency
- ✅ `BillDocument` dataclass with content-based metadata extraction
- ✅ Text cleaning logic (removes line numbers, headers, footers)
- ✅ Extraction confidence scoring
- ✅ Comprehensive test suite

**Revised approach:** **Hybrid metadata** - combine filename + content extraction:
- **Filename-based** (new): session, LD number, amendment codes - reliable, always available
- **Content-based** (merged): title, sponsors, committee - rich context when extractable
- **Result**: Best of both worlds! Reliable structure + enhanced metadata

**Key decisions:**
1. ✅ Keep merged `BillDocument` - content extraction works well
2. ✅ Add new `BillRecord` that combines both metadata sources
3. ✅ Keep text cleaning and confidence scoring
4. ✅ Change output from .txt/.json → Parquet → HuggingFace

## Overview

Migrate `PhilipMathieu/maine-bills` from a git-repo-as-dataset (raw text files committed directly) to a proper Python package that scrapes Maine legislative bill PDFs and publishes structured data to HuggingFace Hub. The code repo becomes *code only*; the data lives at `huggingface.co/datasets/PhilipMathieu/maine-bills`.

**End-state consumer experience:**

```python
from datasets import load_dataset

# Load all sessions (default config)
ds = load_dataset("PhilipMathieu/maine-bills")

# Load one session
ds = load_dataset("PhilipMathieu/maine-bills", "131")

# Stream without downloading everything
ds = load_dataset("PhilipMathieu/maine-bills", streaming=True)
```

---

## Architecture: Publish Strategy

### Why not `push_to_hub`?

The `datasets` library's `push_to_hub()` method is designed for one-shot
uploads. There is no `append=True` mode (requested in datasets issue #6290
since Oct 2023, still unimplemented). Using it for incremental updates
requires a costly round-trip: `load_dataset` → merge in memory → re-push
everything. This is slow, fragile, and wasteful.

### The right pattern: file-per-config with direct upload

Instead of going through the `datasets` library on the publisher side, we:

1. Write one parquet file per session locally
2. Upload each file directly to the HF dataset repo via `HfApi.upload_file()`
3. Maintain a YAML `README.md` in the HF repo that maps config names to
   file paths via glob patterns

This means:

- **Incremental updates only touch the sessions that changed.** When the
  weekly cron finds 5 new bills in session 132, we regenerate only the
  session 132 parquet file and upload it.
- **Xet chunk-level deduplication makes re-uploads cheap.** As of
  `huggingface_hub` v1.0, the Xet storage backend (which replaced
  `hf_transfer`) deduplicates at 64KB chunks. Re-uploading a parquet file
  with a few new rows appended transfers only the changed chunks.
- **No merge/dedup logic needed in our code.** Each session is a complete,
  self-contained parquet file. The scraper is the single source of truth for
  that session's data.
- **The `datasets` library is a consumer-side dependency only.** The
  scraper needs only `huggingface_hub` and `pandas` (with `pyarrow` for
  parquet). Students use `datasets` to load.

### HuggingFace dataset repo layout

```
PhilipMathieu/maine-bills (HF dataset repo)
├── README.md                              # Dataset card with YAML config mapping
└── data/
    ├── 128/
    │   └── train-00000-of-00001.parquet
    ├── 129/
    │   └── train-00000-of-00001.parquet
    ├── 130/
    │   └── train-00000-of-00001.parquet
    ├── 131/
    │   └── train-00000-of-00001.parquet
    └── 132/
        └── train-00000-of-00001.parquet
```

### README YAML frontmatter (in HF repo)

```yaml
---
configs:
  - config_name: "all"
    default: true
    data_files:
      - split: train
        path: "data/**/*.parquet"
  - config_name: "128"
    data_files:
      - split: train
        path: "data/128/*.parquet"
  - config_name: "129"
    data_files:
      - split: train
        path: "data/129/*.parquet"
  # ... one entry per session
  - config_name: "132"
    data_files:
      - split: train
        path: "data/132/*.parquet"
---
```

The `all` config is marked `default: true`, so bare `load_dataset("PhilipMathieu/maine-bills")` loads everything. Each per-session config appears separately in the Dataset Viewer.

When a new session is added, the publish script auto-regenerates this
YAML block (see Phase 3).

---

## Phase 0: Prerequisites & Accounts

- [ ] Create a HuggingFace account (if not already): https://huggingface.co/join
- [ ] Generate a **write-scoped** API token: Settings → Access Tokens → New Token (role: `write`)
- [ ] Store the token as a GitHub Actions secret named `HF_TOKEN` in the `maine-bills` repo
- [ ] Create the HF dataset repo: `huggingface-cli repo create maine-bills --type dataset`
- [ ] Install `uv` locally if not already available

**Time estimate:** 15 minutes

---

## Phase 1: Project Restructuring ✅ PARTIALLY COMPLETE

**Status:** Package structure exists; needs migration to uv and addition of new modules.

### Current state (after merge)
- ✅ Package structure: `src/maine_bills/` with `__init__.py`, `cli.py`, `scraper.py`, `text_extractor.py`
- ✅ PyMuPDF dependency added
- ✅ Comprehensive test suite
- ✅ Text cleaning logic
- ❌ Still using setuptools (not uv)
- ❌ Has content-based `BillDocument` (needs replacement)
- ❌ Missing: `schema.py` (filename parser) and `publish.py` (HF upload)

### Target directory layout

```
maine-bills/                         # GitHub code repo
├── pyproject.toml                   # MIGRATE to uv
├── uv.lock                          # generated by uv
├── README.md                        # updated — points users to HF dataset
├── LICENSE
├── .gitignore                       # updated to exclude data/
├── .github/
│   └── workflows/
│       └── scrape.yml               # replaces run-with-conda.yml
├── src/
│   └── maine_bills/
│       ├── __init__.py              # ✅ exists
│       ├── cli.py                   # ✅ exists, needs update
│       ├── scraper.py               # ✅ exists, needs refactor
│       ├── extract.py               # NEW - simple PyMuPDF extraction
│       ├── schema.py                # NEW - BillRecord + filename parser
│       └── publish.py               # NEW - HF direct-upload logic
└── tests/
    ├── unit/
    │   ├── test_bill_document.py    # ✅ exists, needs update for BillRecord
    │   ├── test_metadata_extraction.py  # ✅ exists, repurpose for filename parsing
    │   ├── test_text_extractor.py   # ✅ exists, simplify
    │   └── ...                      # ✅ other tests exist
    └── integration/
        └── test_scraper_live.py     # ✅ exists
```

### pyproject.toml

```toml
[project]
name = "maine-bills"
version = "2.0.0"
description = "Scraper and dataset publisher for Maine legislative bill text"
readme = "README.md"
license = { text = "MIT" }
requires-python = ">=3.11"
authors = [{ name = "Philip Mathieu" }]

dependencies = [
    "requests>=2.31",
    "beautifulsoup4>=4.12",
    "pymupdf>=1.25",            # replaces pypdf — faster, cleaner extraction
    "huggingface-hub>=1.0",     # v1.0+ includes hf_xet (chunk-level dedup)
    "pandas>=2.2",
    "pyarrow>=18.0",            # parquet read/write
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "ruff>=0.8",
    "datasets>=3.0",           # for local testing of load_dataset()
]

[project.scripts]
maine-bills = "maine_bills.scraper:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.ruff]
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "UP"]
```

Note: `datasets` is a dev-only dependency. The scraper/publisher needs only
`huggingface-hub`, `pandas`, and `pyarrow`. This keeps the install fast and
the dependency tree small in CI.

### Steps

- [ ] Migrate from setuptools to uv:
  ```bash
  # Install uv if not present
  curl -LsSf https://astral.sh/uv/install.sh | sh

  # Initialize uv (will convert pyproject.toml)
  uv init --no-workspace

  # Replace pyproject.toml with HF plan version (see below)
  # Then sync
  uv sync
  ```
- [ ] Replace `pyproject.toml` with uv-compatible version (see below)
- [ ] Update `.gitignore` to include:
  ```
  # Data artifacts (no longer committed)
  /data/
  *.pdf
  *.parquet

  # Python / uv
  __pycache__/
  .venv/
  .python-version

  # Keep existing
  *.json
  *.txt
  *.log
  ```
- [ ] Delete the `131/` directory from git history (optional but recommended):
  ```bash
  git rm -r --cached 131/
  git commit -m "Remove committed data files; data now published to HuggingFace"
  ```
  For a full history rewrite (shrink clone size): use `git filter-repo` or
  BFG Repo-Cleaner. This is optional — the files being untracked from HEAD
  is sufficient for going forward.

**Updated pyproject.toml for uv:**

```toml
[project]
name = "maine-bills"
version = "2.0.0"
description = "Scraper and dataset publisher for Maine legislative bill text"
readme = "README.md"
license = { text = "MIT" }
requires-python = ">=3.11"
authors = [{ name = "Philip Mathieu" }]

dependencies = [
    "requests>=2.31",
    "beautifulsoup4>=4.12",
    "pymupdf>=1.25",            # Merged feature branch added this ✅
    "huggingface-hub>=1.0",     # NEW - for HF upload
    "pandas>=2.2",              # NEW - for DataFrame/parquet
    "pyarrow>=18.0",            # NEW - parquet read/write
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-cov>=4.1.0",
    "pytest-mock>=3.11.0",
    "ruff>=0.8",
    "datasets>=3.0",           # for local testing of load_dataset()
]

[project.scripts]
maine-bills = "maine_bills.cli:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.ruff]
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "UP"]

[tool.pytest.ini_options]
minversion = "7.0"
testpaths = ["tests"]
python_files = ["test_*.py"]
addopts = "-v --cov=src/maine_bills --cov-report=term --cov-report=html -m 'not integration'"
markers = [
    "integration: marks tests as integration tests that hit external services",
]
```

**Key changes from current:**
- Remove `pypdf` (only use PyMuPDF)
- Add `huggingface-hub`, `pandas`, `pyarrow`
- Switch build-backend from setuptools to hatchling (better uv compatibility)
- Keep pytest config from merged work

**Time estimate:** 30 minutes

---

## Phase 2: Dataset Schema Design (Hybrid: Filename + Content)

**Status:** Enhance merged `BillDocument` with filename-based fields.

**✅ REVISED APPROACH: Combine both metadata sources**

The merged work's content parsing (title, sponsors, committee) works well and adds valuable context. Rather than replace it, we'll **combine** it with filename-based metadata:

**Filename-based fields (always reliable):**
- ✅ Session, LD number, amendment info from filename pattern
- ✅ Always present, never null
- ✅ Enables filtering: "show me all session 131 bills" or "only House amendments"

**Content-based fields (best-effort enhancement):**
- ✅ Title, sponsors, committee extracted from bill text (merged work already does this!)
- ✅ Adds human-readable context when available
- ✅ Graceful degradation: null/empty when not found
- ✅ Already implemented and tested!

**Result: Best of both worlds**
- Reliable structure metadata for every record (session, LD number)
- Rich content metadata when extractable (title, sponsors)
- Dataset is more useful than filename-only approach
- Leverages work already completed in the merge

### Columns

| Column | Type | Example | Source |
|---|---|---|---|
| **Filename-based (always present)** |
| `session` | `int` | `131` | Parsed from filename |
| `ld_number` | `string` | `0686` | Parsed from filename |
| `document_type` | `string` | `bill` | Constant for now |
| `amendment_code` | `string` or `null` | `CA_A_H0266` | Parsed from filename |
| `amendment_type` | `string` or `null` | `Committee Amendment` | Derived from amendment_code |
| `chamber` | `string` or `null` | `House` | Derived from amendment_code |
| **Core content** |
| `text` | `string` | (cleaned text) | PDF extraction with cleaning ✅ |
| `extraction_confidence` | `float` | `0.95` | Quality metric ✅ |
| **Content-based (optional enrichment)** |
| `title` | `string` or `null` | `An Act Relating to Education` | Extracted from content ✅ |
| `sponsors` | `list[string]` | `["Rep. Smith", "Sen. Jones"]` | Extracted from content ✅ |
| `committee` | `string` or `null` | `Committee on Education` | Extracted from content ✅ |
| `amended_code_refs` | `list[string]` | `["Title 20, Section 1"]` | Extracted from content ✅ |
| **Provenance** |
| `source_url` | `string` | `https://lldc...pdf` | Constructed from filename |
| `source_filename` | `string` | `131-LD-0686-CA_A_H0266` | Original filename |
| `scraped_at` | `string` (ISO 8601) | `2026-02-10T12:00:00Z` | Extraction timestamp |

**✅ = Already implemented in merged work**

### Filename parsing logic (`schema.py`)

The upstream filenames follow this pattern:
```
{session}-LD-{ld_number}[-{amendment_code}].pdf
```

Amendment codes have the structure `{type}_{letter}_{chamber}{number}`:
- `CA` = Committee Amendment
- `HA` = House Amendment
- `SA` = Senate Amendment

The letter (A, B, C...) distinguishes multiple amendments of the same type.
The chamber prefix on the number (`H` or `S`) indicates originating chamber.

```python
# src/maine_bills/schema.py
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List

AMENDMENT_TYPES = {
    "CA": "Committee Amendment",
    "HA": "House Amendment",
    "SA": "Senate Amendment",
}

CHAMBER_MAP = {"H": "House", "S": "Senate"}

FILENAME_PATTERN = re.compile(
    r"^(?P<session>\d+)-LD-(?P<ld>\d+)(?:-(?P<amendment>[A-Z]{2}_[A-Z]_[HS]\d+))?$"
)


@dataclass
class BillRecord:
    """Complete bill record combining filename and content metadata.

    Merges the HF plan's filename-based approach with the merged work's
    content-based extraction. This gives us:
    - Reliable structure fields (session, LD number) for filtering
    - Rich content fields (title, sponsors) when extractable
    """
    # Filename-based metadata (always present)
    session: int
    ld_number: str
    document_type: str
    amendment_code: str | None
    amendment_type: str | None
    chamber: str | None

    # Core content
    text: str
    extraction_confidence: float

    # Content-based metadata (optional, from merged work)
    title: str | None = None
    sponsors: List[str] = field(default_factory=list)
    committee: str | None = None
    amended_code_refs: List[str] = field(default_factory=list)

    # Provenance
    source_url: str = ""
    source_filename: str = ""
    scraped_at: str = ""

    @classmethod
    def from_filename_and_bill_document(
        cls, filename: str, bill_doc: 'BillDocument', base_url: str
    ) -> "BillRecord":
        """Create BillRecord by parsing filename and merging with BillDocument.

        Args:
            filename: Bill filename without .pdf extension (e.g., "131-LD-0686-CA_A_H0266")
            bill_doc: BillDocument from merged work's text extraction
            base_url: Base URL for constructing source_url

        Returns:
            BillRecord with both filename and content metadata

        Raises:
            ValueError: If filename doesn't match expected pattern
        """
        match = FILENAME_PATTERN.match(filename)
        if not match:
            raise ValueError(f"Unexpected filename format: {filename}")

        # Parse filename for structural metadata
        session = int(match.group("session"))
        ld_number = match.group("ld")
        amendment = match.group("amendment")

        amendment_type = None
        chamber = None
        if amendment:
            prefix = amendment.split("_")[0]
            amendment_type = AMENDMENT_TYPES.get(prefix, prefix)
            chamber_char = amendment.split("_")[2][0]
            chamber = CHAMBER_MAP.get(chamber_char)

        # Combine with content-based metadata from BillDocument
        return cls(
            # Filename-based
            session=session,
            ld_number=ld_number,
            document_type="bill",
            amendment_code=amendment,
            amendment_type=amendment_type,
            chamber=chamber,
            # Content
            text=bill_doc.body_text,
            extraction_confidence=bill_doc.extraction_confidence,
            # Content-based metadata
            title=bill_doc.title,
            sponsors=bill_doc.sponsors,
            committee=bill_doc.committee,
            amended_code_refs=bill_doc.amended_code_refs,
            # Provenance
            source_url=f"{base_url}{filename}.pdf",
            source_filename=filename,
            scraped_at=datetime.now(timezone.utc).isoformat(),
        )
```

### HuggingFace dataset configs (subsets)

Each legislative session becomes a **named configuration** (subset) in HF
parlance. This allows `load_dataset("PhilipMathieu/maine-bills", "131")`
to load only the 131st legislature. The default `all` config loads every
session via a `data/**/*.parquet` glob.

Configs are defined in the YAML frontmatter of the HF dataset repo's
README.md (see Architecture section above). The publish script
auto-generates these entries.

### Migration steps

- [ ] Create new `src/maine_bills/schema.py` with:
  - [ ] `BillRecord` dataclass (code above)
  - [ ] `FILENAME_PATTERN` regex
  - [ ] `from_filename_and_bill_document()` class method
- [ ] Keep `text_extractor.py` with `BillDocument` - it's working well!
  - [ ] BillDocument extracts content-based metadata
  - [ ] BillRecord adds filename-based metadata
  - [ ] They work together via `from_filename_and_bill_document()`
- [ ] Update tests:
  - [ ] Add `tests/unit/test_schema.py` for filename parsing
  - [ ] Test `BillRecord.from_filename_and_bill_document()` with sample data
  - [ ] Keep all existing tests for `BillDocument` - they're good!

**Time estimate:** 1 hour (mostly new code, existing tests stay)

---

## Phase 3: Refactor the Scraper

### Key changes

| Aspect | Before (merged state) | After (hybrid approach) |
|---|---|---|
| PDF library | `pypdf` + `pymupdf` (both) | `pymupdf` only (remove pypdf) |
| Dataclass | `BillDocument` (content only) | `BillDocument` + `BillRecord` (both!) |
| Metadata | Content-based only | Filename + content (hybrid) ✅ |
| Text cleaning | ✅ Comprehensive | ✅ Keep as-is |
| Confidence scoring | ✅ Present | ✅ Keep as-is |
| Output | `.txt` + `.json` files | DataFrame → parquet |
| Publish method | N/A (local files) | `HfApi.upload_file()` per-session parquet |
| Idempotency | Check for `.txt` file | Full rescrape per session; Xet dedup handles efficiency |
| Session handling | Single session (`--session 131`) | Multi-session (`--sessions 131 132`) |
| CLI | `argparse` with `-s` | `argparse` with `--sessions`, `--publish`, `--repo-id` |

### No need for new `extract.py` ✅

**The merged `text_extractor.py` already does everything we need!**

- ✅ Uses PyMuPDF (fitz)
- ✅ Extracts and cleans text
- ✅ Estimates confidence
- ✅ Parses content metadata (title, sponsors, committee)
- ✅ Returns `BillDocument` with all fields

**We'll keep using it as-is.** The only change needed is in the scraper to also parse the filename and create a `BillRecord`.

### `scraper.py` — updated main logic

**Changes from current merged version:**
- Add filename parsing via `schema.py`
- Combine `BillDocument` (from merged work) + filename metadata → `BillRecord`
- Return DataFrame of BillRecords
- Remove `.txt` and `.json` file saving
- Support multiple sessions

```python
# src/maine_bills/scraper.py
import logging
import tempfile
from pathlib import Path
from typing import List

import pandas as pd
import requests
from bs4 import BeautifulSoup

from maine_bills.text_extractor import TextExtractor  # Merged work ✅
from maine_bills.schema import BillRecord, FILENAME_PATTERN  # New
from maine_bills.publish import publish_session, sync_dataset_card  # New

logger = logging.getLogger(__name__)


class BillScraper:
    """Scrapes Maine legislature bills and produces structured records."""

    BASE_URL = "http://lldc.mainelegislature.org/Open/LDs"
    TIMEOUT = 10

    def __init__(self, session: int, logger=None):
        self.session = session
        self.logger = logger or logging.getLogger(__name__)
        self.session_url = f"{self.BASE_URL}/{session}/"

    def _fetch_bill_list(self) -> List[str]:
        """Fetch list of bill filenames (without .pdf extension)."""
        self.logger.debug(f"Fetching bill list from {self.session_url}")
        res = requests.get(self.session_url, timeout=self.TIMEOUT)
        res.raise_for_status()

        soup = BeautifulSoup(res.content, features="html.parser")
        hrefs = [a.attrs["href"] for a in soup.find_all("a")[1:]]
        filenames = [href.split('/')[-1].removesuffix('.pdf') for href in hrefs]

        self.logger.info(f"Found {len(filenames)} bills in session {self.session}")
        return filenames

    def _download_and_extract_bill(self, filename: str) -> BillRecord:
        """Download a bill PDF and extract structured BillRecord.

        Combines:
        1. Content extraction via merged TextExtractor (BillDocument)
        2. Filename parsing (session, LD number, amendment info)
        """
        pdf_url = f"{self.session_url}{filename}.pdf"

        # Download PDF to temp file
        response = requests.get(pdf_url, timeout=self.TIMEOUT)
        response.raise_for_status()

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(response.content)
            tmp_path = Path(tmp.name)

        try:
            # Extract content metadata using merged work
            bill_doc = TextExtractor.extract_bill_document(tmp_path)

            # Add filename-based metadata
            bill_record = BillRecord.from_filename_and_bill_document(
                filename=filename,
                bill_doc=bill_doc,
                base_url=self.session_url
            )

            return bill_record

        finally:
            tmp_path.unlink()  # Clean up temp file

    def scrape_session(self) -> pd.DataFrame:
        """Scrape all bills in session and return DataFrame of BillRecords."""
        self.logger.info(f"=== Scraping session {self.session} ===")

        filenames = self._fetch_bill_list()
        records = []

        for filename in filenames:
            # Skip files that don't match expected pattern
            if not FILENAME_PATTERN.match(filename):
                self.logger.warning(f"Skipping unrecognized filename: {filename}")
                continue

            try:
                record = self._download_and_extract_bill(filename)
                records.append(record.__dict__)  # Convert dataclass to dict
                self.logger.debug(f"Processed {filename}")
            except Exception:
                self.logger.exception(f"Failed to process {filename}; skipping")
                continue

        self.logger.info(f"Successfully processed {len(records)} bills")
        return pd.DataFrame(records)
```

### `publish.py` — direct upload to HuggingFace Hub

This is the core architectural change. Instead of the `datasets` library's
round-trip (`load_dataset` → merge → `push_to_hub`), we upload parquet
files directly using `huggingface_hub` and maintain the config mapping in
the README YAML.

```python
# src/maine_bills/publish.py
import logging
from pathlib import Path

import pandas as pd
from huggingface_hub import HfApi

logger = logging.getLogger(__name__)

DATASET_CARD_TEMPLATE = """\
---
license: mit
language:
  - en
tags:
  - legislation
  - maine
  - government
  - legal
  - nlp
task_categories:
  - text-classification
  - summarization
  - feature-extraction
size_categories:
  - 1K<n<10K
pretty_name: Maine Legislative Bills
configs:
  - config_name: "all"
    default: true
    data_files:
      - split: train
        path: "data/**/*.parquet"
{session_configs}
---

# Maine Legislative Bills

Full text of bills and amendments from the Maine State Legislature,
extracted from PDFs published by the Law and Legislative Reference Library.

## Usage

```python
from datasets import load_dataset

# Load all sessions (default)
ds = load_dataset("PhilipMathieu/maine-bills")

# Load a specific legislative session
ds = load_dataset("PhilipMathieu/maine-bills", "132")

# Stream without downloading
ds = load_dataset("PhilipMathieu/maine-bills", streaming=True)
```

## Source

PDFs are published by the Maine Law and Legislative Reference Library at
`https://lldc.mainelegislature.org/Open/LDs/`. This dataset is neither
endorsed by nor affiliated with the Maine State Legislature.

## Schema

| Column | Type | Description |
|---|---|---|
| `session` | int | Legislative session number |
| `ld_number` | string | Legislative Document number (zero-padded) |
| `document_type` | string | Currently always "bill" |
| `amendment_code` | string | Amendment identifier (e.g., CA_A_H0266) or null |
| `amendment_type` | string | Human-readable amendment type or null |
| `chamber` | string | House or Senate (derived from amendment) or null |
| `text` | string | Full extracted text of the document |
| `source_url` | string | Direct URL to the original PDF |
| `source_filename` | string | Original filename without extension |
| `scraped_at` | string | ISO 8601 timestamp of extraction |

## Configurations

Each legislative session is a named configuration (subset). Use `"all"`
(the default) to load every session, or pass a session number like `"132"`
to load just that legislature.

## Limitations

- Text quality depends on PDF extraction; some formatting artifacts
  (page headers, line numbers, table misalignment) may be present
- Only includes documents published to the LLDC open file server
- No bill status, sponsor, committee, or vote metadata (yet)

## License

Bill text is extracted from public government documents. The extraction
code is MIT-licensed.
"""


def publish_session(
    df: pd.DataFrame, session: int, repo_id: str, local_dir: Path
) -> None:
    """Write a parquet file for one session and upload it directly."""
    api = HfApi()

    # Write locally
    session_dir = local_dir / str(session)
    session_dir.mkdir(parents=True, exist_ok=True)
    local_path = session_dir / "train-00000-of-00001.parquet"
    df.to_parquet(local_path, index=False)

    # Upload just this one file.
    # Xet (built into huggingface_hub >=1.0) deduplicates at the chunk
    # level, so re-uploading a parquet with a few new rows appended
    # transfers only the changed 64KB chunks — not the whole file.
    path_in_repo = f"data/{session}/train-00000-of-00001.parquet"
    api.upload_file(
        path_or_fileobj=str(local_path),
        path_in_repo=path_in_repo,
        repo_id=repo_id,
        repo_type="dataset",
        commit_message=f"Update session {session}: {len(df)} records",
    )
    logger.info(f"Uploaded {path_in_repo} ({len(df)} records)")


def sync_dataset_card(repo_id: str) -> None:
    """Regenerate the HF dataset README.md to include configs for all sessions."""
    api = HfApi()

    # List existing session directories in the repo
    repo_files = api.list_repo_tree(repo_id, repo_type="dataset", path_in_repo="data")
    sessions = sorted(
        int(item.rfilename) for item in repo_files
        if hasattr(item, "rfilename") and item.rfilename.isdigit()
    )

    if not sessions:
        logger.warning("No session directories found in repo; skipping card sync")
        return

    # Build per-session config YAML entries
    session_config_lines = []
    for s in sessions:
        session_config_lines.append(f'  - config_name: "{s}"')
        session_config_lines.append(f"    data_files:")
        session_config_lines.append(f"      - split: train")
        session_config_lines.append(f'        path: "data/{s}/*.parquet"')
    session_configs = "\n".join(session_config_lines)

    # Render and upload the README
    readme_content = DATASET_CARD_TEMPLATE.format(session_configs=session_configs)
    api.upload_file(
        path_or_fileobj=readme_content.encode("utf-8"),
        path_in_repo="README.md",
        repo_id=repo_id,
        repo_type="dataset",
        commit_message=f"Sync dataset card: {len(sessions)} sessions ({sessions[0]}–{sessions[-1]})",
    )
    logger.info(f"Dataset card updated with {len(sessions)} session configs")
```

### Design notes on idempotency

The original scraper skipped already-processed files by checking for `.txt`
on disk. The new approach is simpler: **always rescrape the full session
and re-upload the parquet.** This is safe because:

1. Xet chunk-level dedup means re-uploading an unchanged file is nearly
   free (no data actually transfers if the content is identical).
2. A full rescrape catches upstream changes (e.g., the legislature adding
   a new amendment to an existing bill mid-session).
3. It eliminates the need for any local or remote state tracking.

For very large historical sessions where rescraping every time is wasteful,
you could add a `--skip-existing` flag that checks `HfApi.list_repo_tree()`
and compares remote file sizes. But this is optional and not needed for the
MVP.

### Migration steps for Phase 3

- [ ] Update `src/maine_bills/scraper.py`:
  - [ ] Import `BillRecord` from `schema.py`
  - [ ] Keep using `TextExtractor.extract_bill_document()` - it works! ✅
  - [ ] Wrap result with `BillRecord.from_filename_and_bill_document()`
  - [ ] Change `scrape_session()` to return `pd.DataFrame` of BillRecords
  - [ ] Remove `.txt` and `.json` file saving logic
  - [ ] Remove `_save_bill_document()` method
  - [ ] Remove directory creation for txt/pdf dirs
- [ ] Update `src/maine_bills/cli.py`:
  - [ ] Change `-s/--session` to `--sessions` (accepts multiple, nargs="+")
  - [ ] Add `--publish` flag
  - [ ] Add `--repo-id` arg (default: "PhilipMathieu/maine-bills")
  - [ ] Add `--local-dir` arg (default: "./data")
  - [ ] Loop over sessions
  - [ ] Call `publish_session()` when `--publish` is set
  - [ ] Otherwise save parquet locally for testing
- [ ] Keep `text_extractor.py` as-is - no changes needed! ✅
- [ ] Update tests:
  - [ ] Update scraper tests to expect DataFrame output
  - [ ] Keep all existing `text_extractor.py` tests - they're good! ✅

**Time estimate:** 2 hours (mostly updating scraper + CLI, text extraction stays)

---

## Phase 4: Dataset Card

The dataset card is now generated programmatically by `sync_dataset_card()`
in `publish.py` (see above). The template is embedded in the source code so
it stays in sync with schema changes.

On every publish run, after all session parquets are uploaded, the script:

1. Lists the `data/` directory on HF to discover all session folders
2. Generates one YAML config entry per session
3. Renders the full README from the template
4. Uploads it via `HfApi.upload_file()`

This means adding a new session automatically adds it to the Dataset
Viewer — no manual YAML editing required.

**Time estimate:** Already included in Phase 3 (the template is part of `publish.py`)

---

## Phase 5: GitHub Actions Workflow

Replace `run-with-conda.yml` with a `uv`-based workflow.

```yaml
# .github/workflows/scrape.yml
name: Scrape and Publish

on:
  schedule:
    # Weekly on Sunday at 06:00 UTC
    - cron: "0 6 * * 0"
  workflow_dispatch:
    inputs:
      sessions:
        description: "Space-separated session numbers (e.g., '131 132')"
        required: false
        default: "132"

permissions:
  contents: read

jobs:
  scrape:
    runs-on: ubuntu-latest
    timeout-minutes: 120

    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v4

      - name: Install dependencies
        run: uv sync

      - name: Run scraper
        env:
          HF_TOKEN: ${{ secrets.HF_TOKEN }}
        run: |
          SESSIONS="${{ github.event.inputs.sessions || '132' }}"
          uv run maine-bills \
            --sessions $SESSIONS \
            --publish \
            --repo-id PhilipMathieu/maine-bills
```

**Notes:**

- `workflow_dispatch` lets you manually trigger for any session(s) — useful for backfilling
- The weekly schedule keeps the current session fresh during the legislative term
- The `HF_TOKEN` env var is automatically picked up by `huggingface_hub`
- Timeout is generous because downloading hundreds of PDFs takes a while
- Each session is uploaded independently, so a failure mid-run doesn't
  lose progress — already-uploaded sessions are committed to HF

**Time estimate:** 30 minutes

---

## Phase 6: Update the Code Repo README

The `maine-bills` GitHub README should pivot from "here's a dataset repo"
to "here's the tool that produces a dataset."

Key sections:

1. **Overview** — what this project does (one paragraph)
2. **Using the dataset** — `load_dataset()` snippet, link to HF dataset
   page with viewer
3. **Running the scraper yourself** — `uv sync && uv run maine-bills --sessions 132`
4. **Schema reference** — link to dataset card on HF
5. **How it works** — brief explanation of the pipeline
   (scrape → extract → structure → upload parquet → sync dataset card)
6. **Contributing** — how to add features, file issues
7. **License** — MIT for code, public domain for bill text

**Time estimate:** 30 minutes

---

## Phase 7: Backfill Historical Sessions

Once the pipeline is working for session 132, backfill older sessions. The
upstream server has data back to session 100 (and even a `1-46` archive).

Suggested approach:

```bash
# Start with the most recent sessions and work backward
uv run maine-bills --sessions 132 131 130 129 128 --publish

# Then optionally backfill older sessions in batches
uv run maine-bills --sessions 127 126 125 124 123 122 121 120 --publish
```

Each session uploads independently. The dataset card is regenerated after
each run to include all sessions present in the repo.

**Time estimate:** Mostly wall-clock time waiting for downloads. ~1–3
hours of babysitting, depending on how far back you go and how many PDFs
exist per session.

---

## Execution Summary (Updated for Hybrid Approach)

| Phase | Work | Status | Time |
|---|---|---|---|
| 0. Accounts & secrets | HF account, token, GH secret, create dataset repo | To do | 15 min |
| 1. Project restructuring | Migrate to uv, update pyproject.toml | Partial ✅ | 30 min |
| 2. Schema design | Add BillRecord + filename parsing | To do | 1 hr |
| 3. Scraper refactor | Update to use BillRecord + DataFrame output | To do | 2 hr |
| 4. Publish module | publish.py with HF upload | To do | 1 hr |
| 5. Dataset card | Template in publish.py (auto-generated) | To do | (included) |
| 6. GitHub Actions | New workflow with uv | To do | 30 min |
| 7. Code repo README | Rewrite for new architecture | To do | 30 min |
| 8. Backfill | Run scraper for historical sessions | To do | 1–3 hr |
| | **Total** | | **~6–8 hr** |

**What's already done from merge:**
- ✅ PyMuPDF extraction
- ✅ Text cleaning
- ✅ Content metadata extraction
- ✅ Comprehensive tests
- ✅ Package structure

**Critical path:** Phases 1–4. The merged work gives us a head start! A reasonable MVP is: complete Phases 1–4 for session 132, upload to HF, confirm `load_dataset` works, *then* do the rest.

---

## Future Enhancements (Not In Scope)

These are things worth noting but explicitly out of scope for the migration:

- **Enhanced metadata quality** — The current content-based extraction (title, sponsors, committee) uses regex which may miss some records or extract incorrectly. Future work could:
  - Hit the Open States API or Maine's LawMakerWeb for verified metadata
  - Add bill status, vote data, fiscal notes
  - Use LLM-based extraction for more robust parsing
- **Text cleaning** — Strip page headers/footers, line numbers, boilerplate;
  normalize whitespace
- **Embeddings column** — Pre-compute embeddings (e.g., via
  `sentence-transformers`) and store as a column for similarity search demos
- **PDF retention** — Store original PDFs alongside text (HF supports binary
  columns) for layout analysis or OCR comparison tasks
- **Sharding large sessions** — If a session grows beyond ~1GB parquet, split
  into multiple shards (`train-00000-of-00002.parquet`, etc.). The glob
  pattern in the YAML already handles this transparently.
- **Parquet content-defined chunking** — HuggingFace recently added
  `use_content_defined_chunking=True` as a PyArrow write option that further
  optimizes Xet dedup for row insertions/deletions. Worth enabling once
  `pyarrow` exposes it stably.