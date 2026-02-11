#!/usr/bin/env python3
"""
Experimental feedback loop for iteratively improving bill extraction.

This script runs cycles of:
1. Sample random bill → extract baseline
2. Reviewer agent → writes analysis.md + proposed_changes.py
3. Tester agent → writes results.md + comparison.md
4. Log decision with metrics

Outputs human-readable artifacts (.md, .py files) for easy review.
"""

import json
import random
from datetime import datetime
from pathlib import Path
from typing import Dict, List
import requests
from bs4 import BeautifulSoup

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
from maine_bills.text_extractor import TextExtractor, BillDocument


class FeedbackExperiment:
    """Orchestrates the feedback loop experiment with improved artifacts."""

    BASE_URL = "http://lldc.mainelegislature.org/Open/LDs"
    TIMEOUT = 10
    SESSION = "131"

    def __init__(self, num_iterations: int = 5):
        """Initialize the experiment."""
        self.num_iterations = num_iterations
        self.results: List[Dict] = []

        # Create experiment directory with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.experiment_dir = Path(f"experiments/feedback_loop_{timestamp}")
        self.iterations_dir = self.experiment_dir / "iterations"
        self.iterations_dir.mkdir(parents=True, exist_ok=True)

        print(f"Experiment directory: {self.experiment_dir}")

    def run(self) -> None:
        """Run the complete experiment (all iterations)."""
        print(f"\nStarting {self.num_iterations}-cycle feedback experiment")
        print("=" * 80)

        for i in range(1, self.num_iterations + 1):
            print(f"\n{'='*80}")
            print(f"CYCLE {i}/{self.num_iterations}")
            print(f"{'='*80}")

            try:
                self._run_cycle(i)
            except Exception as e:
                print(f"ERROR in cycle {i}: {e}")
                import traceback
                traceback.print_exc()
                # Log error and continue
                self.results.append({
                    "iteration": i,
                    "error": str(e),
                    "accepted": False
                })

        print(f"\n{'='*80}")
        print(f"All cycles complete! Results in: {self.experiment_dir}")
        print(f"{'='*80}")

    def _run_cycle(self, iteration: int) -> None:
        """Run a single feedback cycle."""
        # Create iteration directory with bill ID prefix
        bill_id = self._fetch_random_bill()
        iter_dir = self.iterations_dir / f"{iteration:02d}_bill-{bill_id}"

        # Create subdirectories
        inputs_dir = iter_dir / "inputs"
        reviewer_dir = iter_dir / "reviewer"
        tester_dir = iter_dir / "tester"

        for d in [inputs_dir, reviewer_dir, tester_dir]:
            d.mkdir(parents=True, exist_ok=True)

        print(f"Selected bill: {bill_id}")
        print(f"Iteration dir: {iter_dir}")

        # Download and extract
        pdf_path = self._download_bill(bill_id, inputs_dir)
        raw_text = self._get_raw_text(pdf_path)
        baseline_result = TextExtractor.extract_bill_document(pdf_path)

        # Save inputs
        self._save_inputs(inputs_dir, raw_text, baseline_result)

        # Create reviewer prompt
        self._create_reviewer_prompt(reviewer_dir, bill_id, raw_text, baseline_result)

        print(f"  ✓ Setup complete")
        print(f"    Reviewer prompt: {reviewer_dir / 'prompt.md'}")
        print(f"    Expected outputs:")
        print(f"      - {reviewer_dir / 'analysis.md'}")
        print(f"      - {reviewer_dir / 'proposed_changes.py'}")
        print(f"      - {reviewer_dir / 'metadata.json'}")

        # Log placeholder result
        self.results.append({
            "iteration": iteration,
            "bill_id": bill_id,
            "iter_dir": str(iter_dir),
            "accepted": False,
            "reasoning": "Pending agent review"
        })

    def _fetch_random_bill(self) -> str:
        """Fetch a random bill ID from the session."""
        url = f"{self.BASE_URL}/{self.SESSION}/"
        response = requests.get(url, timeout=self.TIMEOUT)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, features="html.parser")
        hrefs = [a.attrs["href"] for a in soup.find_all("a")[1:]]
        bill_ids = [href.split('/')[-1][:-4] for href in hrefs if href.endswith('.pdf')]

        # Filter to base bills only (no amendments)
        base_bills = [bid for bid in bill_ids if '-' not in bid.split('-LD-')[1]]
        if not base_bills:
            base_bills = bill_ids

        return random.choice(base_bills)

    def _download_bill(self, bill_id: str, output_dir: Path) -> Path:
        """Download bill PDF."""
        url = f"{self.BASE_URL}/{self.SESSION}/{bill_id}.pdf"
        response = requests.get(url, timeout=self.TIMEOUT)
        response.raise_for_status()

        pdf_path = output_dir / "bill.pdf"
        pdf_path.write_bytes(response.content)

        # Also save with original name for reference
        (output_dir / f"{bill_id}.pdf").write_bytes(response.content)
        return pdf_path

    def _get_raw_text(self, pdf_path: Path) -> str:
        """Extract raw text from PDF using PyMuPDF."""
        import fitz
        with fitz.open(pdf_path) as doc:
            pages = [page.get_text() for page in doc]
            return '\n'.join(pages)

    def _save_inputs(self, inputs_dir: Path, raw_text: str, baseline: BillDocument) -> None:
        """Save input artifacts."""
        # Save raw text
        (inputs_dir / "raw_text.txt").write_text(raw_text)

        # Save baseline extraction
        TextExtractor.save_bill_document_json(
            inputs_dir / "baseline.json",
            baseline
        )

        # Save baseline as readable markdown too
        self._save_baseline_markdown(inputs_dir / "baseline.md", baseline)

    def _save_baseline_markdown(self, path: Path, baseline: BillDocument) -> None:
        """Save baseline extraction as human-readable markdown."""
        content = f"""# Baseline Extraction

## Metadata

| Field | Value |
|-------|-------|
| bill_id | {baseline.bill_id or '`null`'} |
| session | {baseline.session or '`null`'} |
| title | {baseline.title} |
| sponsors | {', '.join(baseline.sponsors) if baseline.sponsors else '`[]`'} |
| committee | {baseline.committee or '`null`'} |
| introduced_date | {baseline.introduced_date or '`null`'} |
| amended_code_refs | {', '.join(baseline.amended_code_refs) if baseline.amended_code_refs else '`[]`'} |
| confidence | {baseline.extraction_confidence:.2f} |

## Body Text Preview

```
{baseline.body_text[:800]}
...
```

**Total length:** {len(baseline.body_text)} characters
"""
        path.write_text(content)

    def _create_reviewer_prompt(
        self,
        reviewer_dir: Path,
        bill_id: str,
        raw_text: str,
        baseline: BillDocument
    ) -> None:
        """Create prompt for reviewer agent."""
        prompt_path = reviewer_dir / "prompt.md"

        # Truncate raw text for readability
        raw_preview = raw_text[:2000] + "\n...\n[See inputs/raw_text.txt for full content]"

        prompt_content = f"""# Extraction Improvement Review - Bill {bill_id}

## Your Task

Review the baseline extraction results and propose improvements to TextExtractor methods.

## Input Files

- **Raw PDF text:** `../inputs/raw_text.txt` (first 2000 chars shown below)
- **Baseline extraction:** `../inputs/baseline.md`
- **Baseline JSON:** `../inputs/baseline.json`

## Raw Text Preview

```
{raw_preview}
```

## Baseline Extraction Results

**Metadata:**
- bill_id: {baseline.bill_id or '(not found)'}
- session: {baseline.session or '(not found)'}
- title: {baseline.title}
- sponsors: {baseline.sponsors or '(empty)'}
- committee: {baseline.committee or '(not found)'}
- introduced_date: {baseline.introduced_date or '(not found)'}
- amended_code_refs: {baseline.amended_code_refs or '(empty)'}
- confidence: {baseline.extraction_confidence}

**Body text:** {len(baseline.body_text)} chars, preview:
```
{baseline.body_text[:500]}...
```

---

## Output Requirements

Create **THREE files** in this directory:

### 1. `analysis.md`

Write a human-readable analysis covering:
- What extraction failures you identified
- Root causes for each failure
- Your proposed solution approach

Example format:
```markdown
# Extraction Analysis

## Issues Identified

### 1. Bill ID Extraction Failure
- **Expected:** "131-LD-{bill_id.split('-LD-')[1] if '-LD-' in bill_id else 'XXXX'}"
- **Got:** null
- **Root Cause:** ...
- **Proposed Fix:** ...

### 2. Sponsors Not Extracted
...
```

### 2. `proposed_changes.py`

Write actual Python code with method implementations:

```python
\"\"\"
Proposed improvements to TextExtractor.
Apply these to src/maine_bills/text_extractor.py
\"\"\"

from pathlib import Path
from typing import List, Optional
from datetime import date
import re


@staticmethod
def _extract_bill_id(text: str) -> Optional[str]:
    \"\"\"Extract bill ID from text (e.g., '131-LD-0001').\"\"\"
    # Your implementation here
    ...


@staticmethod
def _extract_session(text: str) -> Optional[str]:
    \"\"\"Extract session number.\"\"\"
    ...

# Add all improved methods
```

### 3. `metadata.json`

Minimal JSON with just metadata:

```json
{{
  "iteration": {baseline.extraction_confidence},
  "bill_id": "{bill_id}",
  "methods_modified": ["_extract_bill_id", "_extract_session", ...],
  "summary": "Brief one-line summary of changes"
}}
```

---

## Key Points

- Focus on **concrete improvements** visible in this bill
- Provide **complete, executable** method implementations
- Use proper Python syntax with docstrings
- Match existing method signatures (`@staticmethod`, type hints)
- Be specific about what patterns you're adding/changing
"""

        prompt_path.write_text(prompt_content)


if __name__ == "__main__":
    experiment = FeedbackExperiment(num_iterations=5)
    experiment.run()
