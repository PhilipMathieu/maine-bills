# Sample-feedback review UIs

Disposable, self-contained HTML pages for human data-quality review during
gates (see docs/GOVERNANCE.md "Human review tooling"). No build step, no
network — open the file in a browser.

## matching_review.html (Gate A)

1. Run the `data-run.yml` workflow with task `run-matching` (sessions e.g.
   `121 122 ... 132`); download the report artifact. If the workflow version
   you're on doesn't pass source/output flags itself, set `extra_args` to
   `--parquet-source hf://datasets/pem207/maine-bills --output report`.
2. Open `matching_review.html`, drop `matching_report.json` on it.
3. Review: per-session match rates vs the 95% gate, the random fuzzy-match
   sample (✓/✗/⚑, keys y/n/f), and the unmatched/ambiguous name lists.
4. Export `matching_verdicts.json` and attach it to the gate PR/issue —
   agents consume it to tune thresholds and add regression tests.

Verdicts persist in localStorage for the most recently loaded report, so an
interrupted review resumes; loading a different report starts fresh.
