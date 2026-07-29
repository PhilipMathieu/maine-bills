import logging
from pathlib import Path

import pandas as pd
from huggingface_hub import HfApi

logger = logging.getLogger(__name__)

# Where each config lives in the repo.
#
# The actions config is deliberately NOT under `data/`. The default "all" config
# globs `data/**/*.parquet`, so an actions parquet placed anywhere beneath it
# would be loaded as if it were bill rows -- a different schema silently unioned
# into the config most consumers use without naming it. A sibling top-level
# directory keeps the two globs disjoint by construction.
BILLS_ROOT = "data"
ACTIONS_ROOT = "actions"

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
  - config_name: "actions"
    data_files:
      - split: train
        path: "actions/**/*.parquet"
{session_configs}
{actions_configs}
---

# Maine Legislative Bills

Full text of bills and amendments from the Maine State Legislature,
extracted from PDFs published by the Law and Legislative Reference Library.

**Dataset version: v2.** Adds five nullable sponsor-enrichment columns
(`sponsor_chambers`, `sponsor_ids`, `sponsor_parties`, `sponsor_districts`,
`sponsor_match_confidence`) linking extracted sponsor names to OpenStates
legislator records. All v1 columns are unchanged, so existing consumers are
unaffected; records scraped without enrichment carry null entries in the new
columns.

## Usage

```python
from datasets import load_dataset

# Load all sessions (default)
ds = load_dataset("pem207/maine-bills")

# Load a specific legislative session
ds = load_dataset("pem207/maine-bills", "132")

# Stream without downloading
ds = load_dataset("pem207/maine-bills", streaming=True)

# Legislative history: one row per bill, with its committee docket
actions = load_dataset("pem207/maine-bills", "actions")
actions_132 = load_dataset("pem207/maine-bills", "actions-132")
```

## Configs

| Config | Rows | What |
|---|---|---|
| `all` (default) | one per **document** | Bill and amendment text. |
| `<session>` e.g. `132` | one per document | The same, for a single session. |
| `actions` | one per **bill** | Legislative history and docket. |
| `actions-<session>` | one per bill | The same, for a single session. |

Amendments are separate rows in `all` and share their parent's `ld_number`.
The two families do not share a schema and live under separate paths, so
the default `all` config never mixes them.

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
| `sponsors` | list | Sponsor names extracted from content (verbatim; provenance) |
| `sponsor_chambers` | list | Chamber per sponsor from the bill's title prefix; nulls where absent |
| `sponsor_ids` | list | OpenStates person IDs, aligned with `sponsors`; nulls where unmatched |
| `sponsor_parties` | list | Party affiliations, aligned with `sponsors`; nulls where unmatched |
| `sponsor_districts` | list | Districts, aligned with `sponsors`; nulls where unmatched |
| `sponsor_match_confidence` | list | Confidence 0-1, aligned; nulls where unmatched |
| `committee` | string | Referred committee, or null |
| `source_url` | string | Direct URL to the original PDF |
| `source_filename` | string | Original filename without extension |
| `scraped_at` | string | ISO 8601 timestamp of extraction |

The five `sponsor_*` enrichment columns are index-aligned with `sponsors`:
entry *i* of each list describes `sponsors[i]`. `sponsors` itself is always
the verbatim extracted name and is never rewritten by enrichment.

## The `actions` config

One row per **bill**, carrying the bill-level status fields and its committee
docket as a nested list.

| Column | Type | Description |
|---|---|---|
| `session` | int | Legislative session number |
| `ld_number` | string | Legislative Document number (zero-padded) — the join key |
| `paper` | string | Paper number, e.g. "SP 29" / "HP 1289" |
| `title` | string | Bill title as printed on the status page |
| `flags` | list | Status flags, e.g. EMERGENCY |
| `committee` | string | Committee of referral, or null if never referred |
| `referred_date` | string | ISO date of referral, or null |
| `final_disposition` | string | e.g. PUBLIC LAW, DIED BETWEEN HOUSES, or null |
| `final_disposition_date` | string | ISO date, or null |
| `governor_action` | string | e.g. Signed, Vetoed, or null |
| `governor_action_date` | string | ISO date, or null |
| `chaptered_law` | string | e.g. "ACTPUB Chapter 33", or null |
| `actions` | list of struct | The docket: `{{date, action, result, raw_date}}` per entry |
| `action_count` | int | `len(actions)`, carried so it can be filtered without exploding |
| `source_url` | string | Direct URL to the status page |

### Joining to the bills config

The key is `(session, ld_number)`, zero-padded on both sides. The join is
**one-to-many** from this side: amendments in the bills config share their
parent's `ld_number`, because a bill's status describes the bill, not each
printed document. A bill with several amendments therefore matches several
rows in `all`.

```python
import pandas as pd

bills = load_dataset("pem207/maine-bills", "132")["train"].to_pandas()
acts = load_dataset("pem207/maine-bills", "actions-132")["train"].to_pandas()
merged = bills.merge(acts, on=["session", "ld_number"], how="left", suffixes=("", "_status"))

# Long format, if you want one row per docket entry:
long = acts.explode("actions")
```

### Nulls

Nulls are meaningful and are never filled in. `committee = None` means the bill
was never referred — it does **not** mean the referral failed to parse. A status
page that does not parse is recorded as a failure and excluded from the config
rather than written as an empty row, so an absent `ld_number` and a null field
are different statements.

Three bills across sessions 121–132 have no status page at all and are absent
from this config while present in `all`.

## Sponsor enrichment methodology

Extracted sponsor names are matched against the OpenStates roster of Maine
legislators for the corresponding session using two-pass matching:

1. **Exact pass:** the extracted name is normalized (case-folded, whitespace
   and punctuation collapsed) and matched on last name against the roster.
   Unambiguous exact matches are accepted with confidence 1.0.
2. **Fuzzy fallback:** names not resolved by the exact pass are scored with
   rapidfuzz string similarity against roster names; the best candidate is
   accepted only above a similarity threshold, with the normalized score
   recorded in `sponsor_match_confidence`.

Sponsors that fail both passes are left null in all four enrichment columns —
no match is ever forced. The original extracted string in `sponsors` is kept
untouched as provenance either way.

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


def publish_actions_config(parquet_dir: Path, repo_id: str) -> list[int]:
    """Upload a built `actions` config, one parquet per session.

    ``parquet_dir`` is what ``scripts/build_actions_config.py`` writes:
    ``<dir>/<session>/train-00000-of-00001.parquet`` plus a build-summary.json,
    which is not uploaded — it describes the build, not the data.

    Returns the sessions uploaded, in order. Refuses an empty directory rather
    than reporting success, because "nothing to upload" and "uploaded nothing"
    look identical in a log otherwise.
    """
    api = HfApi()

    sessions = sorted(int(d.name) for d in parquet_dir.iterdir() if d.is_dir() and d.name.isdigit())
    if not sessions:
        raise ValueError(
            f"No session directories under {parquet_dir}. Run build_actions_config.py first."
        )

    for session in sessions:
        local_path = parquet_dir / str(session) / "train-00000-of-00001.parquet"
        if not local_path.exists():
            raise FileNotFoundError(
                f"{local_path} is missing though its directory exists — the build did not finish."
            )
        path_in_repo = f"{ACTIONS_ROOT}/{session}/train-00000-of-00001.parquet"
        api.upload_file(
            path_or_fileobj=str(local_path),
            path_in_repo=path_in_repo,
            repo_id=repo_id,
            repo_type="dataset",
            commit_message=f"Update actions config for session {session}",
        )
        logger.info(f"Uploaded {path_in_repo}")

    return sessions


def _session_dirs(api: HfApi, repo_id: str, root: str) -> list[int]:
    """Session numbers directly under ``root`` in the repo, ascending.

    Returns [] when the directory does not exist yet — the actions config has
    not been published on every repo this code runs against, and a missing
    directory is a normal state rather than an error.
    """
    try:
        items = api.list_repo_tree(repo_id, repo_type="dataset", path_in_repo=root)
    except Exception as e:  # EntryNotFoundError and its transport-specific kin
        logger.info(f"No {root}/ directory in {repo_id} ({type(e).__name__}); skipping its configs")
        return []
    return sorted(int(i.path.split("/")[-1]) for i in items if i.path.split("/")[-1].isdigit())


def _config_block(name: str, path: str) -> list[str]:
    return [
        f'  - config_name: "{name}"',
        "    data_files:",
        "      - split: train",
        f'        path: "{path}"',
    ]


def sync_dataset_card(repo_id: str) -> None:
    """Regenerate the HF dataset README.md to include configs for all sessions."""
    api = HfApi()

    sessions = _session_dirs(api, repo_id, BILLS_ROOT)

    if not sessions:
        logger.warning("No session directories found in repo; skipping card sync")
        return

    session_config_lines = []
    for s in sessions:
        session_config_lines.extend(_config_block(str(s), f"{BILLS_ROOT}/{s}/*.parquet"))

    # The actions config is additive: a repo that has never published one still
    # gets a correct card, just without those entries.
    actions_sessions = _session_dirs(api, repo_id, ACTIONS_ROOT)
    actions_config_lines = []
    for s in actions_sessions:
        actions_config_lines.extend(_config_block(f"actions-{s}", f"{ACTIONS_ROOT}/{s}/*.parquet"))

    readme_content = DATASET_CARD_TEMPLATE.format(
        session_configs="\n".join(session_config_lines),
        actions_configs="\n".join(actions_config_lines),
    )
    api.upload_file(
        path_or_fileobj=readme_content.encode("utf-8"),
        path_in_repo="README.md",
        repo_id=repo_id,
        repo_type="dataset",
        commit_message=(
            f"Sync dataset card: {len(sessions)} sessions ({sessions[0]}–{sessions[-1]})"
            + (f", {len(actions_sessions)} actions configs" if actions_sessions else "")
        ),
    )
    logger.info(
        f"Dataset card updated with {len(sessions)} session configs "
        f"and {len(actions_sessions)} actions configs"
    )
