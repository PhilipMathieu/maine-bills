#!/usr/bin/env python3
"""
Quality Gate Feedback Loop - Targeted improvement for failing tests.

This variant of the feedback loop focuses specifically on:
1. Making all unit tests pass
2. Improving sponsor extraction rate to 60%+
3. Validating on real bill sample

Instead of random bills, we:
- Use bills that expose test failures
- Include test case patterns in reviewer context
- Measure against both tests AND real-world performance
"""

import json
import random
from datetime import datetime
from pathlib import Path
from typing import Dict, List
import requests
from bs4 import BeautifulSoup
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
from maine_bills.text_extractor import TextExtractor, BillDocument


class QualityGateFeedbackLoop:
    """Quality gate feedback loop targeting specific test failures."""

    BASE_URL = "http://lldc.mainelegislature.org/Open/LDs"
    TIMEOUT = 10
    SESSION = "131"

    def __init__(self):
        """Initialize the quality gate loop."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.experiment_dir = Path(f"experiments/quality_gate_{timestamp}")
        self.experiment_dir.mkdir(parents=True, exist_ok=True)

        print(f"Quality Gate Experiment: {self.experiment_dir}")

    def run(self) -> None:
        """Run the quality gate feedback loop."""
        print("\n" + "="*80)
        print("QUALITY GATE FEEDBACK LOOP")
        print("="*80)

        # Phase 1: Run tests and identify failures
        print("\nPhase 1: Analyzing current test failures...")
        test_results = self._run_unit_tests()
        self._save_test_results(test_results, "baseline")

        if test_results['passed'] == test_results['total']:
            print("✅ All tests already passing!")
            return

        # Phase 2: Download sample bills for real-world validation
        print("\nPhase 2: Downloading sample bills...")
        sample_bills = self._download_sample_bills(count=20)
        baseline_quality = self._measure_quality(sample_bills)
        self._save_quality_metrics(baseline_quality, "baseline")

        # Phase 3: Create comprehensive reviewer prompt
        print("\nPhase 3: Creating reviewer prompt...")
        self._create_quality_gate_prompt(test_results, baseline_quality, sample_bills)

        print("\n" + "="*80)
        print("READY FOR AGENT REVIEW")
        print("="*80)
        print(f"\nNext steps:")
        print(f"1. Review the prompt at: {self.experiment_dir / 'reviewer_prompt.md'}")
        print(f"2. Agent should create:")
        print(f"   - analysis.md (what's broken and why)")
        print(f"   - proposed_changes.py (fixed methods)")
        print(f"   - metadata.json (change summary)")
        print(f"\n3. Then run tester validation")

    def _run_unit_tests(self) -> Dict:
        """Run unit tests and capture results."""
        result = subprocess.run(
            ["uv", "run", "pytest", "tests/unit/test_metadata_extraction.py", "-v", "--tb=no"],
            capture_output=True,
            text=True
        )

        # Parse pytest output
        lines = result.stdout.split('\n')
        failures = []
        for line in lines:
            if 'FAILED' in line:
                test_name = line.split('::')[1].split(' ')[0] if '::' in line else 'unknown'
                failures.append(test_name)

        passed = result.stdout.count('PASSED')
        failed = result.stdout.count('FAILED')

        return {
            'total': passed + failed,
            'passed': passed,
            'failed': failed,
            'failures': failures,
            'output': result.stdout
        }

    def _download_sample_bills(self, count: int = 20) -> List[Dict]:
        """Download sample bills for quality measurement."""
        url = f"{self.BASE_URL}/{self.SESSION}/"
        response = requests.get(url, timeout=self.TIMEOUT)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, features="html.parser")
        hrefs = [a.attrs["href"] for a in soup.find_all("a")[1:]]
        bill_ids = [href.split('/')[-1][:-4] for href in hrefs if href.endswith('.pdf')]

        # Get random sample
        sample = random.sample(bill_ids[:100], min(count, len(bill_ids)))

        bills = []
        for bill_id in sample:
            pdf_url = f"{url}{bill_id}.pdf"
            try:
                pdf_response = requests.get(pdf_url, timeout=self.TIMEOUT)
                if pdf_response.status_code == 200:
                    bills.append({
                        'bill_id': bill_id,
                        'content': pdf_response.content
                    })
            except Exception as e:
                print(f"  ⚠️  Failed to download {bill_id}: {e}")

        print(f"  Downloaded {len(bills)} sample bills")
        return bills

    def _measure_quality(self, sample_bills: List[Dict]) -> Dict:
        """Measure extraction quality on sample bills."""
        import tempfile

        results = []
        for bill_data in sample_bills:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(bill_data['content'])
                tmp_path = Path(tmp.name)

            try:
                bill_doc = TextExtractor.extract_bill_document(tmp_path)
                results.append({
                    'bill_id': bill_data['bill_id'],
                    'has_bill_id': bool(bill_doc.bill_id),
                    'has_session': bool(bill_doc.session),
                    'has_title': bool(bill_doc.title and bill_doc.title != 'Unknown Title'),
                    'has_sponsors': bool(bill_doc.sponsors),
                    'sponsor_count': len(bill_doc.sponsors),
                    'has_committee': bool(bill_doc.committee),
                    'has_codes': bool(bill_doc.amended_code_refs),
                    'confidence': bill_doc.extraction_confidence,
                })
            except Exception as e:
                results.append({
                    'bill_id': bill_data['bill_id'],
                    'error': str(e)
                })
            finally:
                tmp_path.unlink()

        # Calculate aggregate metrics
        successful = [r for r in results if 'error' not in r]
        total = len(successful)

        if total == 0:
            return {'error': 'No successful extractions'}

        metrics = {
            'total_bills': len(sample_bills),
            'successful_extractions': total,
            'bill_id_rate': sum(r['has_bill_id'] for r in successful) / total,
            'session_rate': sum(r['has_session'] for r in successful) / total,
            'title_rate': sum(r['has_title'] for r in successful) / total,
            'sponsor_rate': sum(r['has_sponsors'] for r in successful) / total,
            'avg_sponsors': sum(r['sponsor_count'] for r in successful) / total,
            'committee_rate': sum(r['has_committee'] for r in successful) / total,
            'code_ref_rate': sum(r['has_codes'] for r in successful) / total,
            'avg_confidence': sum(r['confidence'] for r in successful) / total,
            'details': successful
        }

        print(f"  Sponsor extraction: {metrics['sponsor_rate']*100:.1f}%")
        print(f"  Committee extraction: {metrics['committee_rate']*100:.1f}%")

        return metrics

    def _save_test_results(self, results: Dict, phase: str) -> None:
        """Save test results."""
        path = self.experiment_dir / f"test_results_{phase}.json"
        with open(path, 'w') as f:
            json.dump(results, f, indent=2)

    def _save_quality_metrics(self, metrics: Dict, phase: str) -> None:
        """Save quality metrics."""
        path = self.experiment_dir / f"quality_metrics_{phase}.json"
        with open(path, 'w') as f:
            json.dump(metrics, f, indent=2)

    def _create_quality_gate_prompt(self, test_results: Dict, quality_metrics: Dict, sample_bills: List[Dict]) -> None:
        """Create comprehensive reviewer prompt."""
        prompt = f"""# Quality Gate Feedback Loop - Reviewer Task

## Mission

Fix the remaining extraction quality issues to pass the quality gate:

**REQUIRED CRITERIA:**
- ✅ All unit tests must pass (currently {test_results['passed']}/{test_results['total']})
- ✅ Sponsor extraction ≥ 60% (currently {quality_metrics['sponsor_rate']*100:.1f}%)
- ✅ Committee extraction ≥ 60% (currently {quality_metrics['committee_rate']*100:.1f}%)
- ✅ No regressions in other metrics

## Current Issues

### Unit Test Failures ({test_results['failed']} failures)

Failed tests:
{chr(10).join(f"- {failure}" for failure in test_results['failures'])}

**Key insight:** Tests use "Introduced by" but current code only handles "Presented by" (real bill format).
Real bills use "Presented by", but we should support BOTH patterns for robustness.

### Real-World Performance (20-bill sample)

| Metric | Current | Target | Status |
|--------|---------|--------|--------|
| Sponsor extraction | {quality_metrics['sponsor_rate']*100:.1f}% | 60%+ | {'✅' if quality_metrics['sponsor_rate'] >= 0.6 else '❌'} |
| Committee extraction | {quality_metrics['committee_rate']*100:.1f}% | 60%+ | {'✅' if quality_metrics['committee_rate'] >= 0.6 else '❌'} |
| Session extraction | {quality_metrics['session_rate']*100:.1f}% | 95%+ | {'✅' if quality_metrics['session_rate'] >= 0.95 else '⚠️'} |

## Context Files

- **Test results:** `test_results_baseline.json`
- **Quality metrics:** `quality_metrics_baseline.json`
- **Test code:** `../../tests/unit/test_metadata_extraction.py`
- **Current extractor:** `../../src/maine_bills/text_extractor.py`

## Your Task

Create THREE files:

### 1. `analysis.md`

Analyze:
- Why tests are failing (missing "Introduced by" pattern?)
- Why sponsor extraction is only {quality_metrics['sponsor_rate']*100:.1f}%
- Why committee extraction is only {quality_metrics['committee_rate']*100:.1f}%
- What patterns are missing

### 2. `proposed_changes.py`

Provide complete method implementations for:
- `_extract_sponsors()` - Must handle BOTH "Introduced by" AND "Presented by"
- `_extract_committee()` - Improve extraction rate
- Any other methods that need fixes

Requirements:
- Keep all existing patterns that work
- Add missing patterns
- Use @staticmethod decorator
- Include type hints
- Add docstrings

### 3. `metadata.json`

```json
{{
  "methods_modified": ["_extract_sponsors", "_extract_committee"],
  "expected_test_fixes": ["test_extract_sponsors", "test_extract_sponsors_with_apostrophe", ...],
  "expected_quality_improvements": {{
    "sponsor_rate": 0.70,
    "committee_rate": 0.65
  }},
  "summary": "Added 'Introduced by' pattern for test compatibility while keeping 'Presented by' for real bills"
}}
```

## Key Hints

1. **Sponsor extraction:** Add pattern for "Introduced by" alongside existing "Presented by" patterns
2. **False positives:** Filter out titles (President, Speaker, Secretary, State, etc.)
3. **Committee extraction:** Check if patterns are too restrictive
4. **Test compatibility:** Support synthetic test data AND real bill formats

## Previous Feedback Loop Results

The previous feedback loop (100% success rate) added:
- Whitespace normalization
- Multi-fallback extraction
- Ordinal session format
- Month-name date parsing
- Multi-line sponsor blocks

Build on these improvements, don't replace them!

---

**Goal:** Make all tests pass + achieve 60%+ sponsor/committee extraction on real bills.
"""

        prompt_path = self.experiment_dir / "reviewer_prompt.md"
        prompt_path.write_text(prompt)

        print(f"  Created prompt at: {prompt_path}")


if __name__ == "__main__":
    loop = QualityGateFeedbackLoop()
    loop.run()
