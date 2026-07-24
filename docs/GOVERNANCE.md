# Governance: PR Approval Tiers

This project is developed primarily by LLM agents with limited human oversight (~30 min/day). This document defines which changes require human approval and which can be approved by an independent agent review. It exists so that agents can merge safely without waiting on a human, while everything irreversible or outward-facing stays human-gated.

## Tiers

### Tier 1 — human approval required

A PR is Tier 1 if it touches **any** of the following:

- **Publishing:** anything that uploads to HuggingFace Hub or otherwise makes data/artifacts public (including HF Space deploys).
- **Dataset schema:** changes to `BillRecord` fields, parquet column layout, or dataset card structure.
- **Governance:** this document.
- **CI/workflows:** files under `.github/`.
- **Secrets/credentials:** anything reading, writing, or configuring tokens and keys.
- **Dependencies:** additions or removals in `pyproject.toml` (version bumps of existing deps are Tier 2).

**Marking:** title prefixed `[Tier-1]` and label `needs-human` (label optional if unavailable; the title prefix is authoritative). The PR description must include a short agent-written **risk summary**: one paragraph stating what is irreversible or outward-facing about the change and what was verified.

**Merging:** only a human merges (or explicitly instructs an agent to merge) a Tier-1 PR.

### Tier 2 — agent-review eligible

Everything else: extraction/matching/scraper code, tests, refactors, docs (other than this file), bug fixes.

**Requirements to merge:**
1. CI green (unit tests + ruff).
2. An **independent agent review** — a reviewer session/agent that did not author the change reads the diff and approves. The author agent may not approve its own work.
3. Title prefixed `[Tier-2]`; review recorded as a PR review or comment ending with the reviewer's verdict.

A human may always review, request changes on, or revert a Tier-2 PR; agent-merge authority is a default, not an exclusion.

### Escalation rule

If an agent is unsure which tier applies, the PR is Tier 1. A PR that mixes tiers is Tier 1. Reviewers who discover hidden Tier-1 surface (e.g. a "test fix" that alters schema) re-label and stop the merge.

## The publish gate

Dataset publishes run only through the `huggingface-publish` GitHub environment (required-reviewer protection), or by the repo owner locally. Agents never run `--publish` with a live token outside that gate.

## Human review tooling

For data-quality gates (match-rate reviews, backfill validation), agents provide a **sample-feedback UI** — a lightweight page showing extracted/enriched fields side-by-side with source evidence, with ✓/✗/flag verdicts saved as JSON that agents consume. Every review offers a **targeted** sample (low-confidence/edge cases) and a **random** sample (unbiased accuracy estimate). Verdicts become regression tests where applicable.

## Daily queue discipline

Agents never block mid-task on a human. Questions and Tier-1 approvals queue for the daily window, each with a one-paragraph risk summary. The daily window clears the whole queue, not just the oldest item.
