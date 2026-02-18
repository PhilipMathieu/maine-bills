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
ds = load_dataset("pem207/maine-bills")

# Load a specific legislative session
ds = load_dataset("pem207/maine-bills", "132")

# Stream without downloading
ds = load_dataset("pem207/maine-bills", streaming=True)
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
| `title` | string | Bill title extracted from content, or null |
| `sponsors` | list | Sponsor names extracted from content |
| `committee` | string | Referred committee, or null |
| `source_url` | string | Direct URL to the original PDF |
| `source_filename` | string | Original filename without extension |
| `scraped_at` | string | ISO 8601 timestamp of extraction |

## License

Bill text is extracted from public government documents. The extraction
code is MIT-licensed.
"""


def publish_session(df: pd.DataFrame, session: int, repo_id: str, local_dir: Path) -> None:
    """Write a parquet file for one session and upload it to HuggingFace."""
    api = HfApi()

    session_dir = local_dir / str(session)
    session_dir.mkdir(parents=True, exist_ok=True)
    local_path = session_dir / "train-00000-of-00001.parquet"
    df.to_parquet(local_path, index=False)

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

    repo_items = api.list_repo_tree(repo_id, repo_type="dataset", path_in_repo="data")
    sessions = sorted(
        int(item.path.split("/")[-1])
        for item in repo_items
        if item.path.split("/")[-1].isdigit()
    )

    if not sessions:
        logger.warning("No session directories found in repo; skipping card sync")
        return

    session_config_lines = []
    for s in sessions:
        session_config_lines.extend([
            f'  - config_name: "{s}"',
            "    data_files:",
            "      - split: train",
            f'        path: "data/{s}/*.parquet"',
        ])

    readme_content = DATASET_CARD_TEMPLATE.format(
        session_configs="\n".join(session_config_lines)
    )
    api.upload_file(
        path_or_fileobj=readme_content.encode("utf-8"),
        path_in_repo="README.md",
        repo_id=repo_id,
        repo_type="dataset",
        commit_message=(
            f"Sync dataset card: {len(sessions)} sessions "
            f"({sessions[0]}–{sessions[-1]})"
        ),
    )
    logger.info(f"Dataset card updated with {len(sessions)} session configs")
