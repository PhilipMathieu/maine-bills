## Scripts Directory

Utility scripts and experimental tools for maine-bills project.

### Structure

```
scripts/
├── README.md                          # This file
├── demo_extraction.py                 # Demo: extraction on 3 bills
├── demo_text_quality.py               # Demo: text quality comparison
├── generate_final_summary.py          # Legacy summary generator
└── experiments/                       # Experimental feedback loop
    ├── feedback_loop.py               # Main experiment orchestrator
    ├── tester_prompt.py               # Tester prompt generator
    └── utils/
        ├── metrics.py                 # Metrics calculation
        └── comparison_report.py       # Generate comparison markdown
```

### Feedback Loop Experiment

**AI-driven iterative extraction improvement with human-readable artifacts:**

```bash
# Run experiment
uv run python scripts/experiments/feedback_loop.py

# Output structure:
experiments/feedback_loop_TIMESTAMP/
├── summary.md                         # Generated after all cycles
├── iterations/
│   ├── 01_bill-131-LD-0740/
│   │   ├── inputs/
│   │   │   ├── bill.pdf
│   │   │   ├── baseline.json
│   │   │   ├── baseline.md           # Human-readable baseline
│   │   │   └── raw_text.txt
│   │   ├── reviewer/
│   │   │   ├── prompt.md
│   │   │   ├── analysis.md           # ✨ Human-readable analysis
│   │   │   ├── proposed_changes.py   # ✨ Actual Python code
│   │   │   └── metadata.json         # Just metadata
│   │   └── tester/
│   │       ├── prompt.md
│   │       ├── results.md            # ✨ Human-readable results
│   │       ├── comparison.md         # ✨ Side-by-side comparison
│   │       └── metrics.json          # Just numbers
│   └── 02_bill-131-LD-1615/
│       └── ...
```

### Key Features

1. **No serialized Python in JSON** - Actual `.py` files with syntax highlighting
2. **Human-readable reports** - Markdown files for easy review
3. **Side-by-side comparisons** - Clear before/after views
4. **Organized directories** - inputs/reviewer/tester separation
5. **Minimal JSON** - Only for machine-readable data
6. **Metrics-based validation** - Accept/reject based on objective criteria

### Demo Scripts

**Basic extraction demo:**
```bash
uv run python scripts/demo_extraction.py
```

**Text quality demo:**
```bash
uv run python scripts/demo_text_quality.py
```

### Utilities

Import metrics utilities:
```python
from scripts.experiments.utils.metrics import (
    compute_metrics,
    compare_extractions,
    compute_metadata_score,
    compute_cleanliness_score
)
```

Import comparison report generators:
```python
from scripts.experiments.utils.comparison_report import (
    generate_comparison_markdown,
    generate_results_markdown
)
```
