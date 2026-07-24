# Governance: PR Approval Tiers

This project is developed primarily by LLM agents with limited human oversight (~30 min/day). This document defines which changes require human approval and which can be approved by an independent agent review. It exists so that agents can merge safely without waiting on a human, while everything irreversible or outward-facing stays human-gated.

## Tiers

### Tier 1 — human approval required

A PR is Tier 1 if it touches **any** of the following:

- **Publishing:** anything that uploads to HuggingFace Hub or otherwise makes data/artifacts public (including HF Space deploys).
- **Dataset schema:** changes to `BillRecord` fields, parquet column layout, or dataset card structure (`src/maine_bills/schema.py`, `src/maine_bills/publish.py`).
- **Governance:** this document and `.github/CODEOWNERS`.
- **CI/workflows:** files under `.github/`, including action version pins.
- **Secrets/credentials:** anything reading, writing, or configuring tokens and keys.
- **Dependencies:** additions or removals in `pyproject.toml`; any `uv.lock` change beyond the mechanical result of an approved `pyproject.toml` change; **major-version or security-sensitive bumps** of existing dependencies. (Minor/patch version bumps of existing deps are Tier 2.)

**Marking:** title prefixed `[Tier-1]` and label `needs-human` (label optional if unavailable; the title prefix is authoritative). The PR description must include a short agent-written **risk summary**: one paragraph stating what is irreversible or outward-facing about the change and what was verified.

**Merging:** only a human merges (or explicitly instructs an agent to merge) a Tier-1 PR.

### Tier 2 — agent-review eligible

Everything else: extraction/matching/scraper code, tests, refactors, docs (other than this file), bug fixes, minor/patch dependency bumps.

**Requirements to merge:**
1. Required CI checks green: unit tests (`pytest -m "not integration"`) **and** lint (`ruff check`), as run by `.github/workflows/ci.yml`.
2. An **independent agent review** — a reviewer session/agent that did not author the change reads the diff and approves. The author agent may not approve its own work.
3. The review is submitted as a formal GitHub PR review with an **Approve** verdict, containing the structured checklist below. Mechanical caveat: agent sessions authenticate as the repo owner's account, and GitHub forbids Approve/Request-Changes events on one's own PRs — in that case the reviewer submits a comment-event PR review whose body opens with an explicit, unambiguous verdict line (**APPROVE** or **REQUEST CHANGES**); that verdict line is authoritative. Checklist:
   - **Tier decision:** confirmed Tier 2, with one line on why no Tier-1 surface is touched.
   - **Risk:** what could break and blast radius.
   - **Checks:** tests/lint status and any manual verification performed.
   - **Rollback:** how to revert (usually "revert commit"; note anything stateful).
4. Title prefixed `[Tier-2]`.

A human may always review, request changes on, or revert a Tier-2 PR; agent-merge authority is a default, not an exclusion.

### Escalation rule

If an agent is unsure which tier applies, the PR is Tier 1. A PR that mixes tiers is Tier 1. Reviewers who discover hidden Tier-1 surface (e.g. a "test fix" that alters schema) re-label and stop the merge.

## Enforcement (repo configuration)

Policy is enforced by repository settings, not only by convention. `.github/CODEOWNERS` assigns the repo owner to all Tier-1 surfaces. The repo owner should configure (one-time, in Settings):

- [ ] **Branch ruleset on `main`:** require a pull request before merging; require review from Code Owners; dismiss stale approvals on new pushes; block self-approval; require status checks `test` and `lint` (from `ci.yml`) to pass.
- [ ] **Environment `huggingface-publish`:** required reviewer = repo owner; `HF_TOKEN` scoped to this environment only.
- [ ] **Secret `OPENSTATES_API_KEY`** (repository secret) for matching jobs.

With CODEOWNERS + ruleset in place, Tier-1 surfaces mechanically require the owner's review even if an agent mislabels a PR; the tier convention then governs everything the ruleset can't express (risk summaries, reviewer checklists, agent independence).

## The publish gate

Dataset publishes run only through the `huggingface-publish` GitHub environment (required-reviewer protection), or by the repo owner locally. Agents never run `--publish` with a live token outside that gate. There is **no unattended scheduled publish path**: the weekly scheduled workflow produces artifacts and a diff summary, and the publish job waits on environment approval. (The pre-existing auto-publish in `scraper-uv.yml` is being retired in the CI workstream PR.)

## Human review tooling

For data-quality gates (match-rate reviews, backfill validation), agents provide a **sample-feedback UI** — a lightweight page showing extracted/enriched fields side-by-side with source evidence, with ✓/✗/flag verdicts saved as JSON that agents consume. Every review offers a **targeted** sample (low-confidence/edge cases) and a **random** sample (unbiased accuracy estimate). Verdicts become regression tests where applicable.

## Daily queue discipline

Agents never block mid-task on a human. Questions and Tier-1 approvals queue for the daily window, each with a one-paragraph risk summary. The daily window clears the whole queue, not just the oldest item.
