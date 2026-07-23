# Sprint Plan: Dataset v2 — Sponsor Enrichment Release

**Dates:** Thu 2026-07-24 → Wed 2026-07-30 (7 days)
**Headline deliverable:** `pem207/maine-bills` v2 on HuggingFace — every bill record enriched with matched OpenStates legislator data (canonical name, OpenStates ID, party, district) for sponsors, across sessions 121–132.
**Stretch goals (cut in this order if budget/time runs short):** ③ embeddings demo → ② bill actions/status → ① GitHub Actions automation.

## Constraints & operating model

- **Labor:** Nearly all work done by LLM agents (Claude Code sessions + subagents), bounded by one Claude Max $100/mo plan. Human input: ~30 min/day for decisions, reviews, and approvals.
- **Budget discipline:** Enrichment works off existing parquet files — no PDF re-downloading or re-extraction, which keeps token and wall-clock costs low. Mechanical/grind subagent work (batch matching runs, test scaffolding) runs at low effort settings; high-effort reasoning reserved for design, tricky matching edge cases, and verification. OpenStates API responses cached to disk on first fetch and never re-fetched.
- **Nothing publishes to HuggingFace without explicit human approval.** Publishing is always a Tier-1 action (see governance below).

## Day 1 (Thu): Governance + OpenStates foundation

1. **PR approval convention (first task).** Author `docs/GOVERNANCE.md` + PR labels defining two tiers:
   - **Tier 1 — human approval required:** HuggingFace publishes, dataset schema changes, governance/CI/workflow changes, anything touching secrets or credentials, dependency additions.
   - **Tier 2 — agent-review eligible:** code changes with green CI **plus** an independent agent review (a reviewer session that did not author the change), docs, tests, refactors that don't change the published schema.
   - Labels: `needs-human`, `agent-reviewed`. Convention doc itself lands as a Tier-1 PR for human sign-off.
2. **OpenStates roster module.** New `src/maine_bills/openstates.py`: fetch Maine legislators per session (GraphQL API, key from env var `OPENSTATES_API_KEY`), cache to JSON. Fallback path if key is delayed: OpenStates bulk CSV downloads (no key required).
3. **Human window:** approve governance PR; register OpenStates API key and add it as a repo/environment secret.

## Day 2 (Fri): Matching engine + quality gate

1. Implement two-pass matching per the 2026-02-18 plan: exact normalized last-name match, then rapidfuzz fallback with confidence threshold. Ambiguous matches (duplicate last names in a session) resolved by first-initial, else flagged.
2. Run against all sessions 121–132; produce a per-session match-rate report plus the full list of unmatched/ambiguous names.
3. **🚪 GATE A — match quality.** Target ≥95% of sponsor mentions matched per session.
   - Pass → proceed to schema work.
   - Fail → scale back: publish enrichment only for high-confidence matches, leave others null, and file the unmatched tail as post-sprint issues.
4. **Human window:** eyeball a sample of fuzzy matches + the unmatched list (this is the highest-value 30 minutes of the sprint).

## Day 3 (Sat): Schema v2 + publish pipeline

1. Extend `BillRecord`/schema: `sponsors` gains structured companions — `sponsor_ids`, `sponsor_parties`, `sponsor_districts`, `sponsor_match_confidence` (aligned lists; exact shape decided in Day 2 review). Keep original extracted strings untouched for provenance.
2. Update `publish.py` + dataset card generation to describe the new fields and match methodology.
3. Full test coverage for matching + schema; CI green.
4. **Human window:** Tier-1 review of the schema PR (schema is the hardest thing to change later — this is the sprint's key design decision).

## Day 4 (Sun): v2 release + start stretch ② (bill actions/status)

1. Regenerate all 12 session parquet files with enrichment; run quality checks; **Tier-1 approval → publish v2** with release notes in the dataset card.
2. Begin actions/status scraper: reconnaissance of the legislature's bill-status pages for session 132; prototype parser for legislative history (referral, committee votes, floor actions, enacted/died/carried over).
3. **🚪 GATE B — actions feasibility.** If status pages are inconsistent or heavy to scrape across old sessions, scope to session 132 only (current session is where status is most valuable); if even that is shaky, cut stretch ② entirely and pull stretch ① forward.

## Day 5 (Mon): Bill actions/status build-out

1. Build `actions` scraper as a separate table/config (bill_id → list of {date, chamber, action, outcome}) rather than widening the main schema — lower risk, independent publish decision.
2. Validate against a human-checked sample of ~20 bills with known outcomes.
3. **Human window:** review sample validation; Tier-1 decision on whether actions data ships in v2.1 this week or waits.

## Day 6 (Tue): Stretch ① automation + stretch ③ demo

1. **GitHub Action:** weekly scheduled workflow that re-scrapes the active session (132), re-runs enrichment, and opens a PR with the diff summary — publish still requires human approval per governance. Small, high-leverage, lands as Tier-1.
2. **Embeddings demo (first to cut):** notebook computing embeddings over bill titles/text with a simple semantic-search example; stretch-stretch: HF Space.
3. **🚪 GATE C — budget check.** If Max plan usage is running hot by Tuesday morning, cut ③ immediately and ship ① only.

## Day 7 (Wed): Buffer, docs, release notes

1. Buffer for anything that slipped; fix stragglers from agent reviews.
2. Update CLAUDE.md, README, QUALITY-IMPROVEMENT-HISTORY.md; write sprint retro notes (what the gates decided and why).
3. **Human window:** final sign-off on any pending Tier-1 PRs; close the sprint.

## Daily human window (30 min) — standing agenda

1. (≤10 min) Approve/reject queued Tier-1 PRs.
2. (≤10 min) Answer the day's queued decision questions (agents batch questions rather than blocking).
3. (≤10 min) Spot-check data samples when a gate calls for it (Days 2, 5 especially).

## Risks

| Risk | Mitigation |
|---|---|
| OpenStates key delayed | Bulk CSV fallback path built Day 1 |
| Historical sessions (121–125) missing from OpenStates | Gate A allows per-session partial enrichment; older sessions may ship with lower match rates, documented in the card |
| Token budget exhaustion | Gates B/C cut stretch scope; enrichment core needs no PDF re-processing |
| Schema regret | Original extracted strings preserved verbatim; enrichment fields additive only |
