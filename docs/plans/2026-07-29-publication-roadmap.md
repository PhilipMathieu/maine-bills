# Critical analysis and roadmap to a publication-ready academic dataset

**Date:** 2026-07-29. Repository state: `main` at `a728d57d`, 582 unit test
functions, v2 published to `pem207/maine-bills`, one open PR (#29), seven open
issues, 31 branches.

This document does two things: a critical assessment of everything the project
holds today — merged work, open issues, open branches, and the published
artifact itself — and a phased roadmap from here to a dataset a researcher
could cite in a peer-reviewed paper without caveats the card doesn't state.

---

## Part 1 — Critical analysis

### 1.1 What the project has genuinely gotten right

Credit first, because these are the assets the roadmap builds on and none of
them should be relitigated:

- **Measurement over argument.** Every extraction change since #16 has been
  validated by diffing real output across sessions and hand-inspecting every
  difference (#24: +696 mentions, 0 lost, all 126 gained names verified by
  eye). This discipline is *exactly* the evaluation methodology an academic
  dataset needs — it just isn't yet packaged as one (see 1.4).
- **Provenance invariant.** Extracted `sponsors` strings are never rewritten;
  enrichment writes only the aligned nullable columns, and a failed match is a
  null, never a guess. This is the single most defensible design decision in
  the dataset and should be a headline claim in any paper.
- **Two-tier governance with a gated publish path.** Irreversible actions
  (HF uploads, schema) are human-gated via the `huggingface-publish`
  environment; everything else moves at agent speed with independent review.
  Eleven review rounds across four PRs caught real defects every round.
- **Honest failure records.** `ERROR-PATTERNS-CATALOG.md`,
  `QUALITY-IMPROVEMENT-HISTORY.md`, issue #31's damage taxonomy, and the
  (unmerged) sprint retrospective are unusually candid. Most of the
  "limitations" section of a future data paper is already written — it's just
  scattered across issues.

### 1.2 The central problem: the published dataset is internally inconsistent

This is the largest threat to academic credibility and everything else is
downstream of it.

Sessions were scraped at different times under different extractor versions.
`300cd207` (Feb 18) removed the bare-name roster sweep; #16 (July) restored it
correctly. Session 131 was scraped before the removal and carries full
cosponsor lists; session 132 was scraped after and holds ~0.8 mentions/bill
against 131's ~2.8. A researcher computing cosponsorship networks across
sessions today would find a spurious structural break at 132 that is an
artifact of the pipeline, not of politics. The same class of inconsistency
affects 121–128 at smaller magnitude.

Current state of the fix (issue #13, comments of 2026-07-29):

- Re-extraction from the published `text` column is **measured across all 12
  sessions** and **staged for 125–127 and 129–132** (+8,000 mentions, 0–1
  distinct names lost per session), awaiting owner inspection → enrichment
  re-run → gated publish.
- **121–124 and 128 are correctly held** behind #31: their published sponsors
  came from the old permissive sweep which tolerated OCR noise; the current
  sweep's contiguity rule stops at the first corrupted cell and would destroy
  thousands of real mentions (124: −1,357). The measurement that caught this
  before it shipped is the process working as designed.
- **Session 125 has an open judgment call:** 19 residual OCR-class losses
  (`ofCurnberland`-type). Publishing it now trades 19 known losses for +294
  gains; holding it behind #31 keeps the 121–128 block together.

**Assessment:** the diagnosis, the ordering inversion (#31 before re-extracting
old sessions), and the hold are all correct. The risk is drift: the staged
parquets live in a session workspace and the re-extraction plan lives in issue
comments. This should be driven to publication within days, not weeks, or the
v2 data's known inconsistency keeps accruing downstream users.

### 1.3 The enrichment cliff is a coverage problem wearing a matching costume

Match rates: 84% for sessions 125–132, 16.5% for 121–124. The project has
correctly established (issue #13) that this is a **roster coverage gap** —
`openstates/people` simply lacks Maine members for 2003–2010 — not a matcher
defect. Three consequences:

1. The advertised "59.7% overall" number is a blend of two regimes and is the
   wrong summary statistic. Per-era rates should be the only numbers quoted.
2. The identified fix — scraping the Legislature's own member rosters (~190
   rows/session) — also supplies **town names**, which unlocks locality
   disambiguation for the 12–23% ambiguous mentions in 125–130. One scrape,
   two problems. The roster-page recon that was blocking this **was executed
   2026-07-29** — sources are pinned down in Appendix A. The primary source
   (the law library's Legislators' Biographical Database) sits on a host this
   analysis session's proxy blocks, so the scrape itself runs through
   `data-run` on GitHub Actions, which has open network.
3. Two matcher gaps are queued and correctly scoped to ride the same
   enrichment re-run: #27 (disambiguating initials, `SANBORN, H.` — 164
   structurally resolvable mentions in session 129 alone) and #28 (denylist
   misses inflected forms — latent, zero observed hits, needs the same
   measure-then-inspect standard).

**Assessment:** the plan is right; the sequencing discipline (fold #27/#28
into one enrichment pass so Gate A is re-read once) is right. What's missing
is a decision on the *fallback*: if the historical roster scrape fails or
stalls, the dataset card must state the 121–124 enrichment cutoff as a
documented feature boundary rather than leaving 83% nulls unexplained.

### 1.4 Quality is measured rigorously but only differentially

Every quality number in the repo is a *diff*: branch vs `main`, on vs off,
before vs after. There is no absolute measurement anywhere — no hand-labeled
gold sample, so no precision/recall estimate for sponsor extraction, title
extraction, or text cleaning. Differential testing proves changes don't
regress; it cannot answer "what fraction of true sponsors does the published
dataset contain?" — which is the first question a reviewer of a data paper
will ask, and the question issue #25 (continuous parse quality scoring)
gestures at without naming.

The infrastructure to fix this cheaply already exists: the sample-feedback
review UI (#9, `tools/review_ui/`) with its targeted+random sampling modes was
built for exactly this workflow and has been used only for gate spot-checks.

### 1.5 The actions data is the biggest unrealized asset

A complete twelve-session legislative-history backfill exists: **24,196 bills,
91,787 docket actions, 0 failures** — committee dockets, final dispositions,
governor's actions, chaptered-law references. This turns a text corpus into a
dataset that supports outcome prediction, committee-pathway analysis, and
survival modeling — the difference between "an NLP corpus" and "a political
science resource." PR #29 (the gated publish path) is open, Copilot-reviewed,
and waiting on Tier-1 human review.

Two risks: (a) the built parquets live in **GitHub Actions artifacts, which
expire** — if the Tier-1 window slips past retention, the backfill must be
re-run; (b) `document_type` in the bills config is still `"bill"` for every
row including amendments, which will confuse joins against actions (amendments
share their parent's `ld_number`; the card documents the one-to-many join, but
the bills side can't distinguish originals from amendments by a typed column —
only by `amendment_code` nullness).

### 1.6 The dataset card would not survive academic review today

Specific defects in the published card (template in `publish.py`):

| Defect | Detail |
|---|---|
| **License is wrong** | Front-matter says `license: mit` for the *dataset*. MIT is the code license. The bill texts are Maine government edicts — public domain under the government-edicts doctrine. Mislicensing public-domain text as MIT is both incorrect and a red flag to any data librarian. Needs `license: cc0-1.0` (or `other` with a public-domain statement) plus a clear code-vs-data license split. |
| **Size category wrong** | `1K<n<10K`; the dataset holds ~43K documents / 24K bills. |
| **Column-count drift** | Card says "four" enrichment columns, lists five (fix already riding PR #29). |
| **No versioning surface** | "v2" appears in prose but there are no tagged HF revisions, no changelog, no statement of what changed between v1 and v2, and re-publishes overwrite in place. A citing researcher cannot pin the version they used. |
| **No quality/limitations section** | The per-session match-rate table, the OCR damage classes for 121–124, the era discontinuity, the extraction consistency history — none of it is on the card. It lives in GitHub issues, invisible to HF users. |
| **No citation** | No BibTeX, no DOI, no preferred-citation field. |
| **No datasheet** | None of the standard datasheet/data-statement questions (motivation, composition, collection process, recommended uses, known biases) are answered on the card. |
| **Split semantics unexamined** | Everything is a single `train` split. Fine as a convention, but a card for academic use should warn about leakage hazards: amendments duplicate large spans of their parent bill's text, and carry-over bills recur across sessions — random splits will leak. |

### 1.7 Governance: one true claim short of trustworthy

The sprint retrospective's finding stands: `GOVERNANCE.md`'s enforcement
section describes a branch ruleset (Code Owners review, self-approval block,
required checks) that is **not configured** — #19, #22, #23, #24 all merged
without a Code Owners event. Issue #21 tracks this as P1. For a dataset whose
selling point is auditable provenance, a governance document that overstates
its enforcement is a liability an academic reviewer could actually notice.
Either configure the ruleset or rewrite the section; both are ≤30 minutes of
human time.

The same retrospective (314 lines, genuinely valuable methodology findings on
mutation-testing direction, guard-interaction bugs, and overclaiming in prose)
sits **unmerged** on `claude/sprint-writeup`.

### 1.8 Branch audit

31 branches. Disposition:

| Group | Branches | Action |
|---|---|---|
| Active PR | `claude/sprint-publish-actions` (#29) | Tier-1 review, merge |
| Unmerged docs, keep | `claude/sprint-writeup` (retrospective, 2 commits) | Open small PR, merge |
| Redundant docs | `claude/sprint-planning-week-qz2dz4` (4 commits; final file content already on `main`) | Delete |
| Fixture data (by design) | `fixtures/recon`, `fixtures/diagnosis` | Keep — this is the sanctioned artifact channel |
| Merged, stale (ahead=0) | 18 `claude/sprint-*`/`pr16-fix`/`copilot/*` branches | Delete in one sweep |
| Setup debris | 3× `add-claude-github-actions-*` | Delete |
| **Divergent history** | `feature-testimony` — 78 commits, **no merge base** with `main`; the pre-refactor scraper including **testimony collection** for sessions 127–131 | Never merge. Mine for domain knowledge (testimony URL schemes, directory layout) when testimony support is designed, then archive with a tag and delete the branch |

`feature-testimony` deserves a note: it is the only artifact in the repo
bearing on testimony scraping, which alongside fiscal notes (#26) is the
obvious v4+ expansion. Its *knowledge* is valuable; its *code* predates the
entire current architecture.

### 1.9 Issue-tracker assessment

The seven open issues are all real, current, and well-written — there is no
stale backlog to triage. Their implicit dependency structure, made explicit:

```
#31 (OCR pre-pass) ──► re-extract 121–124,128 ──┐
                                                ├──► Gate A re-read (#13) ──► v3
roster recon ──► roster scrape (#13 items 1+2) ─┤
#27 (initials)  ─────── same enrichment pass ───┤
#28 (denylist)  ─────── same measured pass ─────┘
#25 (quality scoring) — independent, feeds the card's limitations section
#26 (fiscal notes) — independent, post-v3
#21 (governance) — independent, one Tier-1 batch PR
```

---

## Part 2 — Roadmap to a publication-ready academic dataset

"Publication-ready" is taken to mean: (a) internally consistent across
sessions, (b) quality quantified absolutely, not just differentially, (c)
correctly licensed, versioned, and citable with a DOI, (d) documented to
datasheet standard, and (e) ideally accompanied by a short data paper.

### Phase 0 — Land what is already built (days; mostly Tier-1 windows)

Everything here is finished work waiting on gates. No new engineering.

1. **Publish the staged re-extraction for 125–127, 129–132** (issue #13 item
   1): owner inspects staged parquets → enrichment re-run on the rewritten
   sponsors → gated publish → re-read Gate A for those sessions. Decide 125
   explicitly (recommend: hold with 121–128 unless the 19 losses are deemed
   acceptable; they are one OCR pre-pass away from being zero).
2. **Merge PR #29 and publish the `actions` config** (dry-run first, as the PR
   prescribes). Before the artifact expires — re-running the backfill is
   cheap but not free. This ships v2.1.
3. **Merge the sprint retrospective** from `claude/sprint-writeup`.
4. **Governance batch (#21):** at minimum the P1 item — configure the branch
   ruleset or rewrite the enforcement section to say what is actually
   enforced. Fold in the P2 reviewer-methodology rules.
5. **Branch sweep:** delete the 22 stale/redundant branches per the table
   above; tag `feature-testimony` (`archive/feature-testimony`) before
   deleting.

**Exit criteria:** 125–132 internally consistent and enriched on the Hub;
actions config live; repo carries only active branches.

### Phase 1 — Data consistency and the enrichment ceiling (1–2 weeks)

The v3 quality release. Order matters and is dictated by #31's inversion.

1. **Roster recon — done 2026-07-29** (Appendix A). Primary source: the law
   library's Legislators' Biographical Database
   (`history.mainelegislature.org/Presto/...`); fallbacks: Wikipedia's
   per-session Maine Senate rosters and the Legislative Record front matter
   on `lldc.mainelegislature.org`. First task is a `data-run` probe of the
   Presto database's search/export surface, since it was unreachable from
   the analysis session's proxy.
2. **`legislature_roster` historical provider:** scrape ~190 rows/session —
   name, chamber, district, **town**, party. Town is the disambiguation key
   OpenStates lacks. (Module scaffolding already exists.)
3. **#31 OCR normalization pre-pass**, scoped to the cosponsor block, in the
   recommended order: (a) widen `_ROSTER_WORD` to accented capitals (`CASÁS`
   is plausibly the *correct* spelling — arguably not OCR damage at all);
   (b) fold `Of`→`of`, missing-space `ofX`→`of X`, stray punctuation on
   otherwise-clean all-caps tokens; (c) check `BEAR of the Houlton Band of
   Maliseet Indians` as a possible live tribal-designation gap distinct from
   OCR (#24 covers only the Passamaquoddy form). Keep the contiguity rule
   untouched; measure per #24's standard (zero real names lost, every gained
   name inspected) on 121, 124, 128 minimum.
4. **Re-extract 121–124 and 128**, publish behind the gate.
5. **One combined matching pass:** #27 (trailing-initial resolution against
   roster `given_name`), #28 (denylist inflections, measured), locality
   capture (persist the already-matched `of <locality>` group — issue #13
   calls this "mostly mechanical" now) and locality-based disambiguation
   against the new roster. **Schema note:** persisting locality means a new
   `sponsor_localities` column — Tier-1, additive, nullable, and worth
   batching with any other v3 schema changes so consumers see one change.
6. **Re-read Gate A across all 12 sessions.** Realistic targets: ≥95% matched
   for 125–132; 121–124 moving from 16.5% to the 80s+ if the roster scrape
   succeeds. If it fails, invoke the documented fallback: enrichment is a
   125+ feature and the card says so explicitly.

**Exit criteria:** every session extracted by the same extractor version;
per-session match rates published; ambiguity <5% where rosters exist.

### Phase 2 — Absolute quality measurement (1–2 weeks, parallelizable with Phase 1)

This is issue #25 turned into the evaluation section of a data paper.

1. **Gold-standard sample:** stratified random sample (~300–400 documents:
   per-era strata 121–124 / 125–130 / 131–132, plus a targeted stratum of
   known-hard cases — rosters, amendments, OCR-heavy). Hand-label sponsors,
   title, committee via the existing review UI; verdict JSONs become both the
   eval set and regression fixtures. This is the one step that irreducibly
   costs human minutes; the UI and the 30-min/day budget make it ~a week of
   windows.
2. **Report precision/recall with confidence intervals** per field per era.
   These numbers go on the dataset card and in the paper. (Prediction based
   on the differential evidence: sponsor precision will be high everywhere;
   recall high for 125+ and materially lower for 121–124 — and stating that
   with a measured number is precisely what makes the dataset citable.)
3. **Mechanical text-quality scores** per document, published as a
   session-level quality table (and optionally a per-record column):
   non-dictionary token rate, line-number residue, hyphenation artifacts,
   OCR-confusion frequency (`TI`-for-`TT` class). Cheap, unsupervised, and
   they let downstream users filter by quality.
4. **CI regression guard:** the gold sample runs in CI against the extractor;
   any change moving precision/recall on it fails visibly.

**Exit criteria:** the sentence "sponsor extraction achieves P=x.xx/R=x.xx
(95% CI …) on a hand-labeled sample of N documents" is true and on the card.

### Phase 3 — Academic packaging (1 week)

1. **Card overhaul:** fix `license:` (CC0/public-domain for data, MIT noted
   for code), fix `size_categories`, add the full **datasheet** sections
   (motivation, composition, collection, cleaning, uses, distribution,
   maintenance), the Phase-2 quality tables, the limitations section (era
   discontinuity, OCR classes, enrichment coverage boundary, roster-list
   history), and split-leakage warnings (amendments duplicate parent text;
   carry-over bills recur across sessions; recommend session-based splits).
2. **Versioning:** semantic dataset versions as tagged HF revisions; a
   `CHANGELOG` on the card mapping version → extractor commit → what changed.
   Cite-this-version instructions.
3. **DOI:** mint via the Hub's DOI integration or Zenodo. Add
   `preferred_citation` BibTeX to the card front matter.
4. **README parity:** the GitHub README gets the same headline numbers and a
   pointer to the card as the source of truth.

**Exit criteria:** a researcher can cite `pem207/maine-bills v3.0, DOI:…` and
a reviewer checking the card finds license, provenance, quality numbers, and
limitations without opening a GitHub issue.

### Phase 4 — The data paper and demonstration analyses (2–4 weeks, elastic)

1. **Baseline tasks** demonstrating utility (each is a notebook + a section):
   - **Outcome prediction:** enacted/died from text + sponsors + committee,
     joinable today via the actions config's final disposition.
   - **Cosponsorship networks:** party/chamber structure over 24 years —
     made honest for the first time by Phase 1's consistency work.
   - **Topic drift:** committee referral patterns over 12 sessions.
2. **Related-work positioning** (grounded in a 2026-07-29 literature pass;
   see Appendix B): position against OpenStates (metadata, no full text),
   LegiScan (API, licensing limits), and congressional corpora (federal,
   different genre). The published literature makes the case directly:
   researchers studying state legislation repeatedly **hand-assemble** bill
   histories and cosponsorship records at high cost — Thieme (2020) manually
   collected bill histories and cosponsorship for three states over 2003–2016;
   Parinandi et al. (2020) note "no database exists" for failed bills and
   gathered cosponsorship from state archives by hand; Rosa (2024) hand-coded
   273 state bills spanning 2003–2023, exactly this dataset's era. Huang et
   al. (2013) document how shallow and inconsistent state legislative archives
   are, and Cayton (2020) calls measuring the policy content of bills "one of
   the major unsolved problems in legislative studies." Text-as-data work at
   state scale exists (Linder et al. 2018's 500k-bill text-reuse corpus) but
   as derived similarity scores, not a maintained full-text resource with
   resolved sponsors and outcomes. The 24-year × full-text × docket-actions ×
   sponsor-resolution combination for one state, with quantified extraction
   quality, is the contribution.
3. **Venue:** *Scientific Data* or NeurIPS Datasets & Benchmarks for the
   dataset-paper form; *State Politics & Policy Quarterly* if led by an
   application. The methodology story (measured extraction changes,
   provenance invariant, adversarial review) is itself a contribution worth a
   section.
4. **Freshness automation** (the unstarted GA track): weekly re-scrape of the
   active session producing a diff-summary PR, publish still human-gated. A
   maintained dataset is worth more academically than a snapshot; the paper
   can promise a maintenance policy only if this exists.

### Deferred, deliberately

- **Fiscal notes (#26) and testimony:** high-value expansions; start each
  with recon + a joinability design doc, after v3. Mine `feature-testimony`
  for URL/layout knowledge first.
- **Votes config** (sprint node N5): same pattern as actions; post-v3.
- **Embeddings/search Space:** demo material, not on the publication path.
- **Pre-121 sessions:** coverage probe only after the quality machinery
  (Phase 2) exists to score what comes back.

### Risk register

| Risk | Mitigation |
|---|---|
| Actions artifact expires before Tier-1 window | Phase 0 item 2 this week; else re-run backfill (known-good, ~0 failures) |
| Presto biographical database resists scraping (JS-heavy Inmagic UI) | Two fallbacks pinned in Appendix A: Wikipedia per-session Senate rosters + Legislative Record front-matter PDFs; last resort documented on card: enrichment is a 125+ feature |
| OCR pre-pass reopens the prose-harvest hole | Contiguity rule stays; #24's measure-and-inspect standard is the merge bar; permissive-direction mutation tests required (#21 P2) |
| Gold-labeling stalls in the 30-min/day budget | Sample sized to ~1 week of windows; targeted stratum first so the highest-information labels land early |
| Card/license rewrite drifts from template | Card is generated from `publish.py` — all Phase 3 changes go through the template + tests, never hand-edits on the Hub |

### Sequencing summary

```
Phase 0  land staged work          ── days, mostly approval windows
Phase 1  consistency + enrichment  ── 1–2 wks   ┐ parallel where
Phase 2  absolute quality          ── 1–2 wks   ┘ human windows allow
Phase 3  packaging + DOI           ── 1 wk
Phase 4  paper + baselines         ── 2–4 wks, elastic
```

Total: a citable, DOI-bearing v3 in roughly a month of the current working
model; a submitted data paper in roughly two.

---

## Appendix A — Roster recon findings (2026-07-29)

Executed live from the analysis session. First, a correction to the
environment notes in `2026-07-26-sprint-status.md`: analysis sessions are no
longer GitHub-only. Reachable through this session's proxy:
`legislature.maine.gov`, `lldc.mainelegislature.org`, plus scholarly search
(Scholar Gateway, alphaXiv). Still blocked (HTTP 403 at the proxy):
`www.maine.gov`, `history.mainelegislature.org`, `en.wikipedia.org`,
`web.archive.org`. GitHub Actions runners (`data-run`) have open network and
remain the execution plane for anything the proxy blocks.

**Sources for historical rosters (name, chamber, district, town, party),
sessions 121–124, in preference order:**

1. **Legislators' Biographical Database** —
   `https://history.mainelegislature.org/Presto/home/home.aspx?ssid=Consolidated_Home_Page`,
   linked as the canonical member database from the law library's Historical
   Lists page (`legislature.maine.gov/lawlibrary/historical-lists/9140`).
   Covers 1820–present. An Inmagic Presto instance — search/export surface
   unprobed (host proxy-blocked from analysis sessions); first Phase-1 task
   is a `data-run` probe.
2. **Wikipedia per-session rosters** — structured articles exist per Senate
   (`121st Maine Senate`, …) with member/party/district tables; House
   equivalents are thinner. Useful as an independent cross-check even if not
   the primary source; note CC-BY-SA attribution if data is ingested.
3. **Legislative Record front matter** — per-session index pages at
   `legislature.maine.gov/legis/lawlib/lldl/legisrecord{snum}.htm` link the
   full digitized record (all PDFs on `lldc.mainelegislature.org/Open/`),
   whose front matter and appendices carry member lists. OCR-era scans for
   old sessions — same damage classes as #31, so this is the fallback, not
   the plan.

**Dead ends, so nobody re-walks them:** the House site's own historical
dropdown (`/house/Documents/History`) reaches back only to the 131st; the
lawlib `sessions.htm` page maps session numbers to years but links no
per-session member lists; `www.maine.gov/legis/lio` cloture archives are
proxy-blocked from analysis sessions (reachable from Actions).

**Bonus finding for the automation track:** the House site exposes a
machine-readable **current-session roster export** at
`/house/Home/ExportActiveMembers` (CSV/Excel), plus town-keyed listings
(`MemberProfiles/ListAlphaTown`, `ListDistrictTowns`) — the natural roster
source for the weekly re-scrape of the active session, no PDF parsing
involved.

## Appendix B — Literature grounding for the data paper

From a Scholar Gateway pass (15 passages, 10 articles, 2013–2024) on state
legislative text datasets. What it establishes:

**The gap is real and repeatedly paid for by hand.** Thieme (2020, *Leg.
Studies Q.*, [10.1111/lsq.12315](https://doi.org/10.1111/lsq.12315))
assembled roll-call, bill-history, and cosponsorship data for three states
2003–2016 manually to study gatekeeping. Parinandi, Langehennig & Trautmann
(2020, *Policy Studies J.*,
[10.1111/psj.12414](https://doi.org/10.1111/psj.12414)) state outright that
"no database exists identifying the names of unsuccessful … bills; we gather
cosponsorship and … floor voting records … manually using state legislative
websites." Rosa (2024, *Science Education*,
[10.1002/sce.21907](https://doi.org/10.1002/sce.21907)) hand-identified and
coded 273 state bills over 2003–2023 — precisely this dataset's window.
Huang, Leal, Lee & Strube (2013, *Policy & Internet*,
[10.1002/poi3.11](https://doi.org/10.1002/poi3.11)) document the wide
variation and shallow archives of state legislative websites that force this
manual work.

**The methods literature is ready to consume it.** Linder, Desmarais,
Burgess & Giraudy (2018, *Policy Studies J.*,
[10.1111/psj.12257](https://doi.org/10.1111/psj.12257)) validate text-reuse
similarity over ~500k state bills (a derived-scores corpus, not a maintained
full-text one); Kroeger, Karch & Callaghan (2022, *Leg. Studies Q.*,
[10.1111/lsq.12373](https://doi.org/10.1111/lsq.12373)) apply text analysis
to model-bill diffusion; Chen et al. (2022, *Policy Studies J.*,
[10.1111/psj.12457](https://doi.org/10.1111/psj.12457)) run institutional-
grammar and NER pipelines over state bill text; Cheng et al. (2016, *Stat.
Analysis & Data Mining*,
[10.1002/sam.11309](https://doi.org/10.1002/sam.11309)) predict legislative
votes from bill text plus legislator profiles — the exact join this
dataset's sponsors/actions/votes configs enable. Cayton (2020, *Leg. Studies
Q.*, [10.1111/lsq.12299](https://doi.org/10.1111/lsq.12299)) frames
measuring policy content of bills as "one of the major unsolved problems in
legislative studies"; cosponsorship-network methodology is active in
statistics as well (Signorelli & Wit 2017, *JRSS-C*,
[10.1111/rssc.12234](https://doi.org/10.1111/rssc.12234)).

**The NLP/ML side (companion scan, 2026-07-29, arXiv-focused).** The
adjacent NLP-dataset landscape confirms the same gap from the other
direction — state-level structured bill data is nearly absent:

- **BillSum** (Kornilova & Eidelman 2019,
  [arXiv:1910.00523](https://arxiv.org/abs/1910.00523)) is the closest
  neighbor: 22,218 US Congress bills plus **1,237 California** bills for
  summarization. That is the extent of state coverage in the standard
  benchmarks — one state, one task, no sponsors or outcomes.
- **Pile of Law** (Henderson et al. 2022,
  [arXiv:2207.00220](https://arxiv.org/abs/2207.00220)) aggregates 256GB of
  legal text including legislative records, but as bulk pretraining text —
  no per-bill structure, sponsors, or docket actions. Same for legal-NLU
  benchmarks (**LexGLUE**, Chalkidis et al. 2021,
  [arXiv:2110.00976](https://arxiv.org/abs/2110.00976)), which contain no
  state-legislature task at all.
- Outcome/vote prediction from bill text is an established task hungry for
  data: **DeepParliament** ([arXiv:2211.15424](https://arxiv.org/abs/2211.15424))
  frames bill-status classification; Kornilova et al.'s "Party Matters"
  ([arXiv:1805.08182](https://arxiv.org/abs/1805.08182)) predicts votes from
  text plus sponsor party — exactly the columns this dataset publishes.
- Recent siblings show the direction of travel: **LOCUS**, a US local-
  ordinance corpus ([arXiv:2606.19334](https://arxiv.org/abs/2606.19334)),
  and **CoCoHD** congressional hearings
  ([arXiv:2410.03099](https://arxiv.org/abs/2410.03099)) — sub-federal and
  non-bill legislative text is an active dataset-building frontier.

Two methodology anchors for Phases 2–3, both standard citations reviewers
will expect: **Datasheets for Datasets** (Gebru et al.,
[arXiv:1803.09010](https://arxiv.org/abs/1803.09010)) plus Bender &
Friedman's data statements for the Phase-3 card overhaul; and the
OCR-impact literature — van Strien et al., "Assessing the Impact of OCR
Quality on Downstream NLP Tasks," and "An Assessment of the Impact of OCR
Noise on Language Models"
([arXiv:2202.00470](https://arxiv.org/abs/2202.00470)) — which gives
Phase 2's quality scoring an established measurement framing for the
121–124 scanned-era sessions (issues #25/#31).

**Framing for the paper:** the dataset converts a recurring per-project
manual cost, documented across this literature, into a maintained, versioned,
quality-quantified resource for one state over 24 years — and the pipeline
is a template for the other 49. On the NLP side it is, to the scan's
knowledge, the first state-legislature dataset combining full text with
resolved sponsors and docket outcomes at multi-decade depth — BillSum's
1,237 California summaries being the nearest prior art. The venue shortlist
in Phase 4 stands; *Policy Studies Journal* and *Legislative Studies
Quarterly* are where the consuming audience publishes, which argues for
*Scientific Data* (dataset descriptor) plus an application-led companion
aimed at one of those two, with NeurIPS D&B viable if the baselines lead.
