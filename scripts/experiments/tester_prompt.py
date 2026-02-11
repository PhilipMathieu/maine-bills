"""Generate tester agent prompts for feedback loop experiments."""

from pathlib import Path
from typing import Dict
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
from maine_bills.text_extractor import BillDocument


def create_tester_prompt(
    tester_dir: Path,
    bill_id: str,
    inputs_dir: Path,
    reviewer_dir: Path
) -> Path:
    """
    Create prompt for tester agent.

    Args:
        tester_dir: Tester directory path
        bill_id: Bill identifier
        inputs_dir: Path to inputs directory
        reviewer_dir: Path to reviewer directory

    Returns:
        Path to prompt file
    """
    prompt_path = tester_dir / "prompt.md"

    prompt_content = f"""# Test Extraction Improvements - Bill {bill_id}

## Your Task

Test the proposed extraction improvements and determine if they should be accepted.

## Input Files

- **PDF:** `../inputs/bill.pdf`
- **Baseline extraction:** `../inputs/baseline.json` (and `baseline.md`)
- **Raw text:** `../inputs/raw_text.txt`
- **Reviewer's analysis:** `../reviewer/analysis.md`
- **Proposed changes:** `../reviewer/proposed_changes.py`
- **Proposal metadata:** `../reviewer/metadata.json`

## Testing Process

### 1. Load and Apply Patches

```python
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from maine_bills.text_extractor import TextExtractor, BillDocument
import json

# Load proposal
with open("../reviewer/proposed_changes.py") as f:
    proposal_code = f.read()

# Create patched extractor class
class PatchedExtractor(TextExtractor):
    pass

# Execute the proposed code to get the new methods
exec_globals = {{
    'TextExtractor': TextExtractor,
    'BillDocument': BillDocument,
    're': __import__('re'),
    'Optional': __import__('typing').Optional,
    'List': __import__('typing').List,
    'Path': Path,
    'date': __import__('datetime').date,
    'staticmethod': staticmethod
}}

exec(proposal_code, exec_globals)

# Bind each method to PatchedExtractor
# (Extract method names from metadata.json)
with open("../reviewer/metadata.json") as f:
    metadata = json.load(f)

for method_name in metadata['methods_modified']:
    if method_name in exec_globals:
        setattr(PatchedExtractor, method_name, exec_globals[method_name])

# Run extraction with patched version
pdf_path = Path("../inputs/bill.pdf")
improved_result = PatchedExtractor.extract_bill_document(pdf_path)
```

### 2. Compare Metrics

```python
from scripts.experiments.utils.metrics import compute_metrics, compare_extractions
import json

# Load baseline
with open("../inputs/baseline.json") as f:
    baseline_data = json.load(f)

# Reconstruct BillDocument from JSON
# (You may need to handle date fields)

# Compare
accepted, reasoning, deltas = compare_extractions(baseline, improved_result)
```

### 3. Generate Reports

Use the utilities in `scripts/experiments/utils/comparison_report.py`:

```python
from scripts.experiments.utils.comparison_report import (
    generate_comparison_markdown,
    generate_results_markdown
)

comparison_md = generate_comparison_markdown(
    baseline, improved_result,
    baseline_metrics, improved_metrics,
    deltas
)

results_md = generate_results_markdown(
    accepted, reasoning, deltas,
    baseline_metrics, improved_metrics
)
```

---

## Output Requirements

Create **THREE files** in this directory:

### 1. `results.md`

Human-readable test results with decision and reasoning.
Use `generate_results_markdown()` helper.

### 2. `comparison.md`

Side-by-side comparison of baseline vs improved extraction.
Use `generate_comparison_markdown()` helper.

### 3. `metrics.json`

Just the numbers:

```json
{{
  "accepted": true,
  "reasoning": "explanation",
  "baseline_metrics": {{
    "metadata_score": 1,
    "cleanliness_score": 77.0,
    "confidence": 0.54
  }},
  "improved_metrics": {{
    "metadata_score": 6,
    "cleanliness_score": 85.0,
    "confidence": 0.67
  }},
  "deltas": {{
    "metadata_delta": 5,
    "cleanliness_delta": 8.0,
    "confidence_delta": 0.13
  }}
}}
```

---

## Acceptance Criteria

**REJECT if:**
- Metadata score decreased
- Cleanliness score decreased by >5 points
- Patches cause errors/exceptions

**ACCEPT if:**
- At least one metric improved meaningfully (metadata +1, cleanliness +5)
- No regressions in other metrics
- Code executes without errors

The logic is in `scripts/experiments/utils/metrics.py::compare_extractions()`.
"""

    prompt_path.write_text(prompt_content)
    return prompt_path
