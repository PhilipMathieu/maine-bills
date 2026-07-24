# Sample-feedback review UIs

Disposable, self-contained HTML pages for human data-quality review during
gates (see docs/GOVERNANCE.md "Human review tooling"). No build step, no
network — open the file in a browser.

## matching_review.html (Gate A)

1. Run the `data-run.yml` workflow with task `run-matching`; download the
   report artifact.
2. Open `matching_review.html`, drop `matching_report.json` on it.
3. Review: per-session match rates vs the 95% gate, the random fuzzy-match
   sample (✓/✗/⚑, keys y/n/f), and the unmatched/ambiguous name lists.
4. Export `matching_verdicts.json` and attach it to the gate PR/issue —
   agents consume it to tune thresholds and add regression tests.

Verdicts persist in localStorage per report, so an interrupted review resumes.
