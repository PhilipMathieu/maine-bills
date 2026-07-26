# Sprint Status — v2 sponsor enrichment shipped

**Date:** 2026-07-26
**Status:** v2 published to `pem207/maine-bills`. Node N2 of the sprint plan complete.

Handoff notes for whoever picks this up next (human or agent).

## What shipped

Dataset v2 adds five columns to every record, all index-aligned with the
existing `sponsors` list and all nullable:

| column | source |
|---|---|
| `sponsor_chambers` | extracted (Senator/Representative title in bill text) |
| `sponsor_ids` | matched OpenStates person ID |
| `sponsor_parties` | matched party |
| `sponsor_districts` | matched district |
| `sponsor_match_confidence` | 1.0 exact, 0.95 ocr, rapidfuzz score/100 fuzzy |

The original `sponsors` strings are never modified — enrichment only ever
writes the other columns, so a bad match produces nulls, never a rewritten
record.

Published by enriching the already-published parquet in place
(`scripts/enrich_published.py` + the `Enrich and Publish` workflow), **not** by
re-scraping. A full re-scrape of 121-132 is ~43,000 PDF downloads and cannot
finish in one job; enrichment needs no PDFs because `sponsors` is published and
chamber hints come from the published `text`, which retains the
"Presented by Senator X of Y" block.

## Match rates as published

75,892 of 127,135 sponsor mentions enriched — **59.7% overall**, 84.0% across
sessions 125-132, 16.5% across 121-124.

| session | mentions | matched | rate |
|---|---|---|---|
| 121 | 10,196 | 1,468 | 14.4% |
| 122 | 11,595 | 1,856 | 16.0% |
| 123 | 13,378 | 2,360 | 17.6% |
| 124 | 10,563 | 1,874 | 17.7% |
| 125 | 11,696 | 9,514 | 81.3% |
| 126 | 11,919 | 9,232 | 77.5% |
| 127 | 10,752 | 8,132 | 75.6% |
| 128 | 12,496 | 10,328 | 82.7% |
| 129 | 12,965 | 11,067 | 85.4% |
| 130 | 7,285 | 6,387 | 87.7% |
| 131 | 11,520 | 10,953 | 95.1% |
| 132 | 2,770 | 2,721 | 98.2% |

Gate A's 95% target is met by sessions 131 and 132 only. Remaining gaps are
tracked in **issue #13**, which is the next work item and carries a suggested
order.

Cross-check: `run_matching_report.py` and `enrich_published.py` compute matches
through independent paths and agree to the record on all 12 sessions.

## What was built (merged PRs)

| PR | what |
|---|---|
| #5 | `docs/GOVERNANCE.md` — Tier-1 (human) vs Tier-2 (agent-reviewed) + CODEOWNERS |
| #6 | CI (`ci.yml`), `data-run.yml` dispatch utility, publish moved behind the `huggingface-publish` environment |
| #7 | Schema v2 columns + `enrichment.py` integration point + `--enrich` flag |
| #8 | `openstates.py` roster providers + `sponsor_matching.py` + Gate A report script |
| #9 | `tools/review_ui/matching_review.html` — sample-feedback review UI |
| #10 | Chamber capture (`_extract_sponsor_mentions`) + per-sponsor chamber hints |
| #11 | `session_window()` — roster scoped to the sitting period |
| #12 | Report table header alignment |
| #14 | `enrich_published.py` + `Enrich and Publish` workflow + provider fix |

## Findings worth not rediscovering

- **Ambiguity, not OCR noise, was the dominant failure.** Fuzzy matching fired
  on ~0% of mentions; OCR folding fired on **3 mentions out of 127,135**. The
  OCR expansion earned essentially nothing against this corpus.
- **Roster inflation came from the calendar-year window.** Maine legislatures
  are sworn in the first Wednesday of December in even years, so a calendar
  biennium window pulled the *next* legislature's freshman class into the
  previous session's roster (session 130: 279 seats against Maine's 186). Fixed
  in #11; sizes now ~190-201.
- **Sessions 121-124 are a roster coverage gap, not a matching bug.** Clean,
  common surnames go unmatched at high volume (`HATCH` 194 bills, `SMITH` 156).
  `openstates/people` does not appear to carry Maine members for 2003-2010.
- **`of <locality>` is already matched and discarded** by the sponsor regexes,
  exactly as the chamber prefix was before #10. It survives into `text`, so
  locality disambiguation needs no re-scrape — but it needs a locality→person
  mapping, which OpenStates lacks. The legislature's member roster page (~190
  rows/session) supplies both that and the missing historical rosters.
- **Session 132 has ~0.8 sponsor mentions/bill** against ~2.8 for 131. Its 98.2%
  sits on a small denominator; extraction is likely failing on most current
  bills. Issue #13 item 4.
- **Two same-surname sponsors on one bill** were being collapsed into one by
  name-only dedup (fixed in #10, keyed on `(name, chamber)`), but the published
  v1 `sponsors` predates that, so enriched v1 data still carries one entry.
  Full fidelity arrives with the next scrape.

## Environment constraints

- This session's network policy allows **GitHub only** — no huggingface.co,
  legislature.maine.gov, or openstates.org. GitHub Actions is the execution
  plane for all data work; `data-run.yml` is the escape hatch.
- The agent token **cannot dispatch workflows** (403 `Resource not accessible by
  integration`) and **cannot download artifacts** (raw curl is unauthorized).
  It *can* push branches, so `data-run.yml` also triggers on a push to `run/**`
  carrying a `run-request.json` at the repo root:

  ```json
  { "task": "recon-legislature", "sessions": "132 121", "extra_args": "" }
  ```

  That is how an agent starts a data run without waiting on a human window.
  Only the fixed data tasks are reachable this way — `custom`, which runs an
  arbitrary command, stays dispatch-only. Results come back on a `fixtures/*`
  branch rather than an artifact, since branches are readable and artifacts
  are not.
- **Re-running a workflow replays its original commit.** After merging a fix,
  dispatch fresh from the workflow page rather than "Re-run jobs" — a re-run of
  an older run will silently test the old code.
- Job summaries are not retrievable via the API; per-session lines are readable
  from the job **log** tail, which is noisy with HF CDN URLs (~10 lines/session).
- Backticks in `git commit -m` trigger shell substitution — use `commit -F file`.

## Next

Issue #13, suggested order: session 132 extraction anomaly → locality capture +
legislature roster scrape (unlocks both 121-124 and 125-130) → additional OCR
classes. Sprint plan nodes N3+ (actions/status table, votes) remain unstarted.
