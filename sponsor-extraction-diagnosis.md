# Sponsor extraction diagnosis

Mentions per document, split by whether the document is an amendment.
Amendments carry no sponsor block, so only the `originals` column is
comparable across sessions.

| session | docs | amendments | originals | mentions/doc (all) | mentions/doc (originals) | originals w/o sponsors |
|---|---|---|---|---|---|---|
| 132 | 3375 | 1509 | 1866 | 0.82 | 1.48 | 4.2% |
| 131 | 4072 | 1781 | 2291 | 2.83 | 5.03 | 4.5% |

## Original bills with no stored sponsors

- **recoverable** — the current extractor finds mentions in the published
  text that the record lacks: an extraction gap, no re-scrape needed.
- **marker_only** — a 'Presented by' block is present but nothing parses.
- **no_marker** — no sponsor block in the text at all.

| session | recoverable | marker_only | no_marker |
|---|---|---|---|
| 132 | 0 | 3 | 75 |
| 131 | 0 | 4 | 99 |
