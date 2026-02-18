# maine-bills

Scraper and dataset publisher for Maine Legislature bill text. Downloads PDFs from the [Maine Law and Legislative Reference Library](https://lldc.mainelegislature.org/Open/LDs/), extracts clean text and metadata, and publishes structured data to HuggingFace.

## Using the Dataset

```python
from datasets import load_dataset

# Load all sessions (default)
ds = load_dataset("pem207/maine-bills")

# Load a specific legislative session
ds = load_dataset("pem207/maine-bills", "132")

# Stream without downloading everything
ds = load_dataset("pem207/maine-bills", streaming=True)
```

Dataset: [huggingface.co/datasets/pem207/maine-bills](https://huggingface.co/datasets/pem207/maine-bills)

## Running the Scraper

### Prerequisites

- Python 3.11+
- [uv](https://astral.sh/uv/)

### Setup

```bash
git clone https://github.com/PhilipMathieu/maine-bills.git
cd maine-bills
uv sync
```

### Scrape locally (saves parquet to `./data/`)

```bash
uv run maine-bills --sessions 132
uv run maine-bills --sessions 130 131 132   # multiple sessions
```

### Scrape and publish to HuggingFace

```bash
HF_TOKEN=hf_... uv run maine-bills --sessions 132 --publish
```

## How It Works

```
Website → PDF list → Download PDF → TextExtractor → BillDocument
  → BillRecord (adds filename metadata: session, LD number, amendment info)
  → DataFrame → Parquet → HuggingFace Hub
```

**Three main components:**

- **`text_extractor.py`** — PyMuPDF-based PDF extraction with text cleaning and content metadata parsing (sponsors, title, committee)
- **`schema.py`** — `BillRecord` dataclass combining filename-parsed metadata (session, LD number, amendment type) with extracted content
- **`scraper.py`** — Downloads PDFs, calls TextExtractor, returns a `pd.DataFrame` of BillRecords
- **`publish.py`** — Writes per-session parquet files and uploads to HuggingFace via direct `HfApi.upload_file()`, with auto-generated dataset card

CI runs weekly via GitHub Actions (`.github/workflows/scraper-uv.yml`), uploading fresh parquet for session 132. Historical sessions can be backfilled manually via `workflow_dispatch`.

## Testing

```bash
uv sync --extra dev
uv run pytest tests/              # unit tests (default, fast)
uv run pytest tests/ -m ""        # all tests including integration
uv run ruff check src/ tests/     # lint
```

## Schema

| Column | Type | Description |
|---|---|---|
| `session` | int | Legislative session number |
| `ld_number` | string | Legislative Document number (zero-padded) |
| `document_type` | string | Currently always `"bill"` |
| `amendment_code` | string | e.g. `CA_A_H0266`, or null for main bills |
| `amendment_type` | string | `"Committee Amendment"` / `"House Amendment"` / `"Senate Amendment"` or null |
| `chamber` | string | `"House"` or `"Senate"` (derived from amendment), or null |
| `text` | string | Full extracted and cleaned bill text |
| `title` | string | Bill title extracted from content, or null |
| `sponsors` | list | Sponsor names extracted from content |
| `committee` | string | Referred committee, or null |
| `source_url` | string | Direct URL to the original PDF |
| `source_filename` | string | Original filename without extension |
| `scraped_at` | string | ISO 8601 extraction timestamp |

## License

Bill text is extracted from public government documents. Code is MIT-licensed.

Copyright 2023-2026 Philip Mathieu
