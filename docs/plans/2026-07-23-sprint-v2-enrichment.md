# Sprint Plan: Dataset v2+ — Enrichment, Actions, Votes, Automation, Search

**Dates:** Thu 2026-07-24 → Wed 2026-07-30 (7 days)
**Posture:** Maximal scope, executed almost entirely by LLM agents in parallel. Human approval gates protect only irreversible/outward-facing actions (HuggingFace publishes, schema, governance, CI). Everything else proceeds without waiting. Scale-back happens at explicit gates, never by default.

**End-of-week target state:**
1. **v2 published:** sponsor enrichment (OpenStates ID, party, district, confidence) across sessions 121–132.
2. **v2.1 published:** `actions` table — full legislative history (referrals, committee/floor actions, final outcome) for every bill, all sessions.
3. **v2.2 (stretch):** `votes` table — roll-call votes where the legislature site provides them.
4. **Automation live:** scheduled GitHub Action re-scrapes the active session weekly and opens a publish-ready PR.
5. **Semantic search demo:** embeddings + HF Space over the full dataset.

## Constraints

- One Claude Max $100/mo plan; ~30 min/day human input. Enrichment/matching works off existing parquet (no PDF re-processing). Grind work (batch scraping, backfills) runs on cheap low-effort subagents; high effort reserved for design and verification. All external API/page fetches cached to disk once.
- **Tier-1 (human approval required):** HF publishes, dataset schema changes, governance/CI changes, secrets, dependency additions. **Tier-2 (independent agent review + green CI):** everything else. Convention doc lands Day 1, first item in the approval queue.

## Day 1 (Thu) — v2 complete, end to end

All of this lands in one day as a stack of PRs; only the *publish* waits on you.

1. `docs/GOVERNANCE.md` + tier labels (Tier-1, first in queue).
2. `openstates.py`: legislator roster per session via GraphQL (env key) with bulk-CSV no-key fallback; cached JSON.
3. Two-pass matcher (exact normalized last-name → rapidfuzz fallback, first-initial disambiguation), run across all 12 sessions; per-session match-rate report + unmatched/ambiguous list.
4. Schema v2: additive aligned-list fields (`sponsor_ids`, `sponsor_parties`, `sponsor_districts`, `sponsor_match_confidence`); original strings untouched. Publish pipeline + dataset card updated. Full tests, CI green.
5. **🚪 GATE A (your ~30 min):** approve governance + schema, skim fuzzy-match sample and match-rate report (target ≥95%; below that, high-confidence-only enrichment ships and the tail becomes issues), then **approve → v2 publishes same day**. If the OpenStates key isn't ready, the CSV fallback keeps this on schedule.

## Day 2 (Fri) — actions scraper + automation, in parallel

Two independent workstreams, separate agent sessions:

- **A. Actions scraper:** recon of legislature bill-status pages; parser producing an `actions` table (bill_id → [{date, chamber, action, outcome}]) as a separate dataset config — independent publish decision, no main-schema risk. Validated against ~20 human-checkable bills for session 132.
- **B. GitHub Action:** weekly scheduled workflow — re-scrape active session, re-run enrichment, open a diff-summary PR (publish still Tier-1). Lands for approval today.
- **🚪 GATE B:** if status pages are inconsistent across eras, scope the backfill (Day 3) to whatever range parses cleanly (minimum: sessions 128–132); cut only if session 132 itself is shaky.

## Day 3–4 (Sat–Sun) — actions backfill + votes recon

1. **Backfill:** parallel agent fan-out scrapes actions for every bill across the in-scope sessions; per-session validation reports; cached raw HTML so re-runs are free.
2. **Votes recon (v2.2 stretch):** while backfill grinds, a separate session investigates roll-call vote pages; if structured enough, build the `votes` table parser for session 132.
3. **🚪 GATE C (weekend window optional):** approve **v2.1 publish** of the actions table whenever the validation report looks right — Sunday or Monday, your pick. If you're offline all weekend, everything queues; nothing blocks.

## Day 5 (Mon) — votes backfill + semantic search

1. Votes backfill (if Gate C recon passed) → **v2.2 publish queued**.
2. **Embeddings + HF Space:** compute embeddings over titles/summaries, build a semantic-search Space over the dataset. Space deployment is Tier-1.
3. **🚪 GATE D (budget check):** if Max plan usage is running hot, votes backfill narrows to session 132 and the Space falls back to a notebook demo.

## Day 6 (Tue) — polish + opportunistic scope

1. Clear agent-review backlog; harden anything flaky from the weekend backfills.
2. **Opportunistic (only if ahead of schedule and under budget):** pre-121 session coverage probe, or cross-session bill linkage (same bill re-introduced across sessions), or an example analysis notebook (e.g., sponsorship networks) showcased in the dataset card.
3. Dataset card gets a full methodology section covering enrichment, actions, and votes provenance.

## Day 7 (Wed) — buffer + close

1. Buffer for slippage; final Tier-1 queue cleared.
2. CLAUDE.md, README, QUALITY-IMPROVEMENT-HISTORY.md updated; sprint retro (what each gate decided and why).

## Daily human window (30 min) — standing agenda

1. Approve/reject queued Tier-1 PRs (agents keep the queue annotated with a one-paragraph risk summary each).
2. Answer batched decision questions — agents never block mid-day on you; they queue and keep moving on parallel work.
3. Gate-day spot checks: Day 1 fuzzy matches, Day 3/4 actions validation sample.

## Risks

| Risk | Mitigation |
|---|---|
| OpenStates key delayed | Bulk CSV fallback built into Day 1 |
| Older sessions missing from OpenStates / status pages | Per-session partial shipping; gaps documented in the card, never blocking newer sessions |
| Weekend approval unavailable | All publishes queue; agents continue on non-gated work |
| Token budget exhaustion | Gate D narrows scope; backfills cache raw fetches so nothing is paid for twice |
| Backfill scraping load on legislature site | Rate-limited, cached, resumable — same politeness settings as existing scraper |
