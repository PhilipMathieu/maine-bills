"""
Metrics for evaluating extraction quality.

Used by tester agent to compare baseline vs improved extractions.
"""

import re
from typing import Dict, Tuple
from src.maine_bills.text_extractor import BillDocument


def compute_metadata_score(bill_doc: BillDocument) -> int:
    """
    Count non-null/non-empty metadata fields.

    Args:
        bill_doc: BillDocument to evaluate

    Returns:
        Score 0-7 (number of fields with data)
    """
    score = 0

    if bill_doc.bill_id:
        score += 1
    if bill_doc.session:
        score += 1
    if bill_doc.title and bill_doc.title != "Unknown Title":
        score += 1
    if bill_doc.sponsors:  # Non-empty list
        score += 1
    if bill_doc.committee:
        score += 1
    if bill_doc.introduced_date:
        score += 1
    if bill_doc.amended_code_refs:  # Non-empty list
        score += 1

    return score


def compute_cleanliness_score(body_text: str) -> float:
    """
    Evaluate text cleanliness (100 = perfectly clean, 0 = very dirty).

    Checks for:
    - Line numbers (standalone or inline)
    - Page headers/footers
    - Bill ID headers

    Args:
        body_text: Cleaned body text to evaluate

    Returns:
        Score 0-100 (higher is cleaner)
    """
    penalties = 0

    # Count standalone line numbers (e.g., "  42  " on its own line)
    standalone_numbers = len(re.findall(r'^\s*\d+\s*$', body_text, re.MULTILINE))
    penalties += standalone_numbers * 0.5  # Each line number is 0.5 penalty

    # Count page headers
    page_headers = len(re.findall(r'STATE OF MAINE|MAINE LEGISLATURE|MAINE STATE LEGISLATURE', body_text))
    penalties += page_headers * 2  # Headers are more annoying

    # Count page numbers in headers (e.g., "Page 5")
    page_numbers = len(re.findall(r'Page \d+', body_text))
    penalties += page_numbers * 1

    # Count "Reproduced from..." disclaimers
    disclaimers = len(re.findall(r'Reproduced from|LAW AND LEGISLATIVE', body_text))
    penalties += disclaimers * 2

    return max(0.0, 100.0 - penalties)


def compute_metrics(bill_doc: BillDocument) -> Dict[str, float]:
    """
    Compute all metrics for a BillDocument.

    Args:
        bill_doc: BillDocument to evaluate

    Returns:
        Dict with metadata_score, cleanliness_score, confidence
    """
    return {
        "metadata_score": compute_metadata_score(bill_doc),
        "cleanliness_score": compute_cleanliness_score(bill_doc.body_text),
        "confidence": bill_doc.extraction_confidence
    }


def compare_extractions(
    baseline: BillDocument,
    improved: BillDocument
) -> Tuple[bool, str, Dict[str, float]]:
    """
    Compare baseline vs improved extraction and determine accept/reject.

    Args:
        baseline: Original extraction result
        improved: Extraction with proposed improvements

    Returns:
        Tuple of (accepted: bool, reasoning: str, deltas: dict)
    """
    base_metrics = compute_metrics(baseline)
    improved_metrics = compute_metrics(improved)

    deltas = {
        "metadata_delta": improved_metrics["metadata_score"] - base_metrics["metadata_score"],
        "cleanliness_delta": improved_metrics["cleanliness_score"] - base_metrics["cleanliness_score"],
        "confidence_delta": improved_metrics["confidence"] - base_metrics["confidence"]
    }

    # Check for regressions
    if deltas["metadata_delta"] < 0:
        return False, "Metadata regression: lost extracted fields", deltas

    if deltas["cleanliness_delta"] < -5.0:  # Allow small noise
        return False, f"Text cleanliness regression: {deltas['cleanliness_delta']:.1f}", deltas

    # Check for improvements
    improvements = []
    if deltas["metadata_delta"] > 0:
        improvements.append(f"+{int(deltas['metadata_delta'])} metadata fields")

    if deltas["cleanliness_delta"] > 5.0:  # Meaningful improvement
        improvements.append(f"+{deltas['cleanliness_delta']:.1f} cleanliness")

    if deltas["confidence_delta"] > 0.05:  # 5% improvement
        improvements.append(f"+{deltas['confidence_delta']:.2f} confidence")

    if improvements:
        return True, ", ".join(improvements), deltas

    return False, "No measurable improvement", deltas


def format_metrics_report(metrics: Dict[str, float]) -> str:
    """
    Format metrics as a readable string.

    Args:
        metrics: Metrics dict from compute_metrics()

    Returns:
        Formatted string
    """
    return (
        f"Metadata: {metrics['metadata_score']}/7, "
        f"Cleanliness: {metrics['cleanliness_score']:.1f}/100, "
        f"Confidence: {metrics['confidence']:.2f}"
    )
