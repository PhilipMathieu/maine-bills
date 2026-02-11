#!/usr/bin/env python3
"""Show text quality comparison for the amendment bill."""

import tempfile
from pathlib import Path
import requests
from src.maine_bills.text_extractor import TextExtractor


def show_text_quality(session: str, bill_id: str) -> None:
    """Download and show cleaned vs raw text comparison."""
    print(f"\n{'='*80}")
    print(f"TEXT QUALITY DEMO: {bill_id}")
    print(f"{'='*80}")

    url = f"http://lldc.mainelegislature.org/Open/LDs/{session}/{bill_id}.pdf"

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()

        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
            tmp.write(response.content)
            pdf_path = Path(tmp.name)

        # Extract
        bill_doc = TextExtractor.extract_bill_document(pdf_path)

        print(f"\n--- CLEANED BODY TEXT (lines 100-130) ---")
        lines = bill_doc.body_text.splitlines()
        for i, line in enumerate(lines[100:130], start=100):
            print(f"{i:3}: {line}")

        print(f"\n--- FULL TEXT SAMPLE (showing the cleaning effect) ---")
        sample = bill_doc.body_text[1000:2000]
        print(sample)

        pdf_path.unlink()

    except Exception as e:
        print(f"ERROR: {e}")


if __name__ == "__main__":
    # Show the amendment bill - it's larger and more complex
    show_text_quality("131", "131-LD-0002-CA_A_H221")
