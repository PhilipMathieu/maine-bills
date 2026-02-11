# Extraction Feedback Loop - Experimental Design

**Date:** 2026-02-10
**Purpose:** Automated system for iteratively improving bill extraction via agent feedback

## Overview

An experimental feedback loop that uses AI agents to propose and test improvements to the text extraction system. Runs 5 cycles of: sample random bill → extract → review → propose changes → test → accept/reject.

## System Architecture

The system consists of four main components working in a loop:

### 1. Sampler Script (`feedback_experiment.py`)
- Fetches random bill from Maine Legislature website
- Runs current extraction with `TextExtractor.extract_bill_document()`
- Saves three artifacts per iteration:
  - Raw PDF text (unprocessed PyMuPDF output)
  - Current extraction results (BillDocument JSON)
  - Comparison baseline (for metrics)

### 2. Reviewer Agent (general-purpose subagent)
- Receives: raw text + current extraction results
- Analyzes gaps: missing metadata, remaining noise in body_text
- Generates: Python code patch with replacement methods
- Output format: JSON with `{method_name: new_code, rationale: explanation}`

### 3. Tester Agent (separate general-purpose subagent)
- Receives: original bill + code patch from reviewer
- Applies patch in isolated scope (no file modification)
- Runs extraction with patched methods
- Computes metrics: before/after comparison
- Decision: accept (if any metric improves without regressions) or reject

### 4. Results Logger
- Appends each cycle to `feedback_results.jsonl` (JSON Lines format)
- Records: bill_id, iteration number, proposal, test results, accept/reject decision
- Summary report generated at end

## Core Components & Implementation

### Sampler Script Structure

```python
# feedback_experiment.py
class FeedbackExperiment:
    def __init__(self, num_iterations=5):
        self.iterations = num_iterations
        self.results = []

    def run_cycle(self, iteration: int):
        # 1. Fetch random bill from session 131
        bill_id = self._fetch_random_bill()

        # 2. Download and extract with current code
        pdf_path = self._download_bill(bill_id)
        raw_text = self._get_raw_text(pdf_path)
        current_result = TextExtractor.extract_bill_document(pdf_path)

        # 3. Send to reviewer agent
        proposal = self._get_reviewer_proposal(raw_text, current_result)

        # 4. Send to tester agent
        test_result = self._test_proposal(pdf_path, proposal)

        # 5. Log results
        self._log_cycle(iteration, bill_id, proposal, test_result)
```

### Agent Communication

- **Reviewer agent** receives markdown file with raw text + current extraction
- Returns JSON: `{patches: [{method: str, code: str}], rationale: str}`
- **Tester agent** receives same bill + patches
- Returns JSON: `{accepted: bool, metrics: {...}, reasoning: str}`

### Metrics Tracked

- **Metadata fields:** count of non-null/non-empty fields (bill_id, title, sponsors, etc.)
- **Text cleanliness:** line numbers detected (regex count), header/footer remnants
- **Overall quality:** extraction_confidence score

## Data Flow & Patch Application

### How Code Patches Work

The tester agent needs to apply proposed changes without modifying `text_extractor.py`. We'll use dynamic method replacement:

```python
# Tester applies patches like this:
class PatchedExtractor(TextExtractor):
    pass

# Dynamically add proposed methods
for patch in proposal['patches']:
    method_code = patch['code']
    # Compile and bind to PatchedExtractor
    exec(method_code, globals())
    setattr(PatchedExtractor, patch['method'], locals()[patch['method']])

# Test with patched version
result = PatchedExtractor.extract_bill_document(pdf_path)
```

### Cycle Data Flow

```
Iteration N:
  └─> Random bill selected (e.g., 131-LD-0423)
  └─> Extract with current code → baseline metrics
  └─> Write temp files:
      ├─ iteration_N_raw.txt (raw PDF text)
      ├─ iteration_N_baseline.json (current extraction)
      └─ iteration_N_prompt.md (for reviewer agent)

  └─> Reviewer agent reads prompt.md → outputs proposal.json
  └─> Tester agent receives:
      ├─ PDF file
      ├─ proposal.json
      └─ baseline.json (for comparison)

  └─> Tester outputs test_result.json → logged to results.jsonl
```

### Agent Isolation

Each agent runs via `Task` tool with fresh context, preventing context window bloat across 5 iterations.

## Metrics & Evaluation Criteria

### Metrics Computed by Tester Agent

**Metadata Completeness (0-7 points):**
- Count non-null fields: bill_id, session, title, sponsors (non-empty list), committee, introduced_date, amended_code_refs (non-empty list)
- Before: X fields, After: Y fields
- Improvement: +1 for each new field extracted

**Text Cleanliness Score:**
- Line numbers remaining: `len(re.findall(r'^\s*\d+\s*$', body_text, re.MULTILINE))`
- Page headers: count of "STATE OF MAINE", "LEGISLATURE", page number patterns
- Cleanliness = 100 - (line_numbers + headers)
- Higher is better

**Extraction Confidence:**
- Use existing `extraction_confidence` field (0.0-1.0)
- Direct comparison: before vs after

### Accept/Reject Logic

```python
def should_accept(baseline, improved):
    # Reject if any metric got worse
    if improved.metadata_count < baseline.metadata_count:
        return False, "Metadata regression"
    if improved.cleanliness < baseline.cleanliness:
        return False, "Text got dirtier"

    # Accept if ANY metric improved
    improvements = []
    if improved.metadata_count > baseline.metadata_count:
        improvements.append(f"+{improved.metadata_count - baseline.metadata_count} metadata fields")
    if improved.cleanliness > baseline.cleanliness:
        improvements.append(f"+{improved.cleanliness - baseline.cleanliness:.1f} cleanliness")

    if improvements:
        return True, ", ".join(improvements)

    return False, "No improvement"
```

## Output Format & Results

### Directory Structure

```
experiments/
└── feedback_loop_YYYYMMDD_HHMMSS/
    ├── iteration_1/
    │   ├── raw_text.txt
    │   ├── baseline_extraction.json
    │   ├── reviewer_prompt.md
    │   ├── proposal.json
    │   └── test_result.json
    ├── iteration_2/
    │   └── ...
    ├── iteration_5/
    │   └── ...
    ├── results.jsonl (all cycles)
    └── summary_report.md
```

### Results JSONL Format

```json
{"iteration": 1, "bill_id": "131-LD-0423", "accepted": true,
 "metrics": {"metadata_delta": 2, "cleanliness_delta": 15.3},
 "proposal_summary": "Improved line number regex and added session extraction",
 "patches": [...]}
```

### Summary Report Contents

- Success rate: X/5 proposals accepted
- Best improvement: iteration N (+3 metadata fields)
- Common patterns: what types of changes worked
- Recommendations: which patches to consider applying
- Failed proposals: what didn't work and why

### Final Script Behavior

```bash
$ uv run python feedback_experiment.py
Cycle 1/5: Testing bill 131-LD-0423...
  → Reviewer proposed 3 patches
  → Tester: ACCEPTED (+2 metadata, +15.3 cleanliness)
Cycle 2/5: Testing bill 131-LD-1234...
  → Reviewer proposed 2 patches
  → Tester: REJECTED (cleanliness regression)
...
Experiment complete! Results in experiments/feedback_loop_20260210_143022/
```

## Design Decisions

### Focus Areas
- **Both text cleaning AND metadata extraction** - Comprehensive improvement across all extraction aspects
- **One random bill per cycle** - Diverse test cases to avoid overfitting

### Safety & Tracking
- **Log proposals only** - No automatic code modification, manual review required
- **Comparison-based testing** - Quantifiable metrics for objective evaluation
- **Executable code patches** - Concrete, testable proposals from reviewer agent

## Implementation Notes

- Use `Task` tool with `subagent_type="general-purpose"` for both reviewer and tester
- Session 131 as source (most recent complete session)
- Timeout per agent: 5 minutes max
- Save all artifacts for manual inspection and learning
