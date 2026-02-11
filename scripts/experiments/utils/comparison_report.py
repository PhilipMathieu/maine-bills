"""Generate human-readable comparison reports."""

from typing import Dict
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))
from maine_bills.text_extractor import BillDocument


def generate_comparison_markdown(
    baseline: BillDocument,
    improved: BillDocument,
    baseline_metrics: Dict,
    improved_metrics: Dict,
    deltas: Dict
) -> str:
    """
    Generate side-by-side comparison markdown.

    Args:
        baseline: Original extraction
        improved: Extraction with proposed improvements
        baseline_metrics: Metrics dict from compute_metrics()
        improved_metrics: Metrics dict from compute_metrics()
        deltas: Delta values from compare_extractions()

    Returns:
        Markdown formatted comparison
    """

    def format_field(value) -> str:
        """Format a field value for display."""
        if value is None:
            return "`null`"
        if isinstance(value, list):
            if not value:
                return "`[]`"
            return ", ".join(str(v) for v in value)
        return str(value)

    def status_icon(baseline_val, improved_val) -> str:
        """Get status icon based on change."""
        if baseline_val == improved_val:
            return "—"
        if (baseline_val is None or baseline_val == [] or baseline_val == "") and improved_val:
            return "✅"
        if improved_val and baseline_val:
            return "🔄"
        return "—"

    md = f"""# Extraction Comparison

## Summary

| Metric | Baseline | Improved | Delta | Status |
|--------|----------|----------|-------|--------|
| **Metadata Score** | {baseline_metrics['metadata_score']}/7 | {improved_metrics['metadata_score']}/7 | {deltas.get('metadata_delta', 0):+d} | {'✅' if deltas.get('metadata_delta', 0) > 0 else '—'} |
| **Cleanliness Score** | {baseline_metrics['cleanliness_score']:.1f}/100 | {improved_metrics['cleanliness_score']:.1f}/100 | {deltas.get('cleanliness_delta', 0):+.1f} | {'✅' if deltas.get('cleanliness_delta', 0) > 5 else '—'} |
| **Confidence** | {baseline_metrics['confidence']:.2f} | {improved_metrics['confidence']:.2f} | {deltas.get('confidence_delta', 0):+.2f} | {'✅' if deltas.get('confidence_delta', 0) > 0.05 else '—'} |

## Field-by-Field Comparison

| Field | Baseline | Improved | Status |
|-------|----------|----------|--------|
| **bill_id** | {format_field(baseline.bill_id)} | {format_field(improved.bill_id)} | {status_icon(baseline.bill_id, improved.bill_id)} |
| **session** | {format_field(baseline.session)} | {format_field(improved.session)} | {status_icon(baseline.session, improved.session)} |
| **title** | {format_field(baseline.title)} | {format_field(improved.title)} | {status_icon(baseline.title, improved.title)} |
| **sponsors** | {format_field(baseline.sponsors)} | {format_field(improved.sponsors)} | {status_icon(baseline.sponsors, improved.sponsors)} |
| **committee** | {format_field(baseline.committee)} | {format_field(improved.committee)} | {status_icon(baseline.committee, improved.committee)} |
| **introduced_date** | {format_field(baseline.introduced_date)} | {format_field(improved.introduced_date)} | {status_icon(baseline.introduced_date, improved.introduced_date)} |
| **amended_code_refs** | {format_field(baseline.amended_code_refs)} | {format_field(improved.amended_code_refs)} | {status_icon(baseline.amended_code_refs, improved.amended_code_refs)} |

## Body Text Quality

**Baseline:**
- Length: {len(baseline.body_text)} chars
- Preview (first 400 chars):
```
{baseline.body_text[:400]}...
```

**Improved:**
- Length: {len(improved.body_text)} chars ({len(improved.body_text) - len(baseline.body_text):+d} chars)
- Preview (first 400 chars):
```
{improved.body_text[:400]}...
```

## Legend

- ✅ New data extracted or improved
- 🔄 Value changed
- — No change
"""

    return md


def generate_results_markdown(
    accepted: bool,
    reasoning: str,
    deltas: Dict,
    baseline_metrics: Dict,
    improved_metrics: Dict
) -> str:
    """
    Generate test results markdown.

    Args:
        accepted: Whether proposal was accepted
        reasoning: Explanation of decision
        deltas: Delta values
        baseline_metrics: Baseline metrics dict
        improved_metrics: Improved metrics dict

    Returns:
        Markdown formatted results
    """

    status = "✅ ACCEPTED" if accepted else "❌ REJECTED"
    status_emoji = "🎉" if accepted else "⚠️"

    md = f"""# Test Results

## Decision: {status} {status_emoji}

**Reasoning:** {reasoning}

## Metrics

### Baseline
- Metadata Score: {baseline_metrics['metadata_score']}/7
- Cleanliness Score: {baseline_metrics['cleanliness_score']:.1f}/100
- Confidence: {baseline_metrics['confidence']:.2f}

### Improved
- Metadata Score: {improved_metrics['metadata_score']}/7
- Cleanliness Score: {improved_metrics['cleanliness_score']:.1f}/100
- Confidence: {improved_metrics['confidence']:.2f}

### Deltas
- Metadata: {deltas.get('metadata_delta', 0):+d} fields
- Cleanliness: {deltas.get('cleanliness_delta', 0):+.1f} points
- Confidence: {deltas.get('confidence_delta', 0):+.2f}

## Evaluation Criteria

"""

    if accepted:
        md += "✅ **All criteria met:**\n"
        if deltas.get('metadata_delta', 0) > 0:
            md += f"- Metadata improved by {deltas['metadata_delta']} fields\n"
        if deltas.get('cleanliness_delta', 0) > 5:
            md += f"- Cleanliness improved by {deltas['cleanliness_delta']:.1f} points\n"
        md += "- No regressions detected\n"
    else:
        md += "❌ **Failed criteria:**\n"
        md += f"- {reasoning}\n"

    md += """
## Next Steps

"""

    if accepted:
        md += """- Review `proposed_changes.py` for implementation details
- Consider applying these improvements to `text_extractor.py`
- Add unit tests for new patterns
"""
    else:
        md += """- Review why the proposal was rejected
- Consider alternative approaches
- May need different patterns or logic
"""

    return md
