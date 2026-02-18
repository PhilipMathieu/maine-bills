# Experiment: Linking Sponsors to OpenStates

**Date:** 2026-02-18
**Status:** In progress

## Goal

Validate sponsor extraction accuracy and build toward enrichment by matching extracted sponsor names to OpenStates legislator records. Start with session 132, then generalize to all sessions.

## Approach

### Two-pass matching

1. **Fetch legislators from OpenStates** — Use the GraphQL API (`https://openstates.org/graphql`) to pull all Maine legislators for session 132. Cache the response locally as JSON.

2. **Load extracted sponsors** — Read the session 132 parquet file from `data/132/`. In the future, load from HuggingFace datasets instead.

3. **Pass 1 (exact):** Normalize both sides (uppercase, strip whitespace, handle hyphens) and match on last name. Maine has ~186 legislators per session, so ambiguity should be rare.

4. **Pass 2 (fuzzy fallback):** For unmatched names, use `rapidfuzz` to find closest matches with a confidence threshold. Flag these for manual review.

5. **Output:** Match rate statistics, unmatched names, ambiguous matches, and example enriched records.

## Notebook Structure

```
Cell 1: Setup & config (API key, session number)
Cell 2: Fetch OpenStates legislators → cache to experiments/ as JSON
Cell 3: Load sponsors from parquet (future: HF datasets)
Cell 4: Normalize names on both sides
Cell 5: Pass 1 — exact last-name matching
Cell 6: Pass 2 — fuzzy fallback for unmatched
Cell 7: Results summary — match rates, unmatched list, ambiguous matches
Cell 8: Sample enriched records (sponsor name → OpenStates ID, full name, party, district)
```

## Dependencies

- `rapidfuzz` — fuzzy string matching
- `requests` (already in project) — GraphQL API calls

## Output Location

- `experiments/openstates_sponsor_linking/` — notebook + cached API responses
