#!/usr/bin/env python3
"""Demo script to showcase enhanced bill extraction."""

import json
import tempfile
from pathlib import Path
import requests
from src.maine_bills.text_extractor import TextExtractor


def demo_bill_extraction(session: str, bill_id: str) -> None:
    """Download and extract a bill, displaying results."""
    print(f"\n{'='*80}")
    print(f"DEMO: {bill_id}")
    print(f"{'='*80}")

    # Download PDF
    url = f"http://lldc.mainelegislature.org/Open/LDs/{session}/{bill_id}.pdf"
    print(f"Downloading from: {url}")

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()

        # Save to temp file
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
            tmp.write(response.content)
            pdf_path = Path(tmp.name)

        # Extract
        print(f"\nExtracting with PyMuPDF...")
        bill_doc = TextExtractor.extract_bill_document(pdf_path)

        # Display results
        print(f"\n--- METADATA ---")
        print(f"Bill ID (from filename): {bill_id}")
        print(f"Bill ID (extracted from PDF): {bill_doc.bill_id or '(not found)'}")
        print(f"Session: {bill_doc.session or '(not found)'}")
        print(f"Title: {bill_doc.title or '(not found)'}")
        print(f"Sponsors: {', '.join(bill_doc.sponsors) if bill_doc.sponsors else '(not found)'}")
        print(f"Committee: {bill_doc.committee or '(not found)'}")
        print(f"Amended Code References: {', '.join(bill_doc.amended_code_refs) if bill_doc.amended_code_refs else '(none)'}")
        print(f"Extraction Confidence: {bill_doc.extraction_confidence:.2f}")

        print(f"\n--- BODY TEXT (first 500 chars) ---")
        print(bill_doc.body_text[:500] + "...")

        print(f"\n--- TEXT STATISTICS ---")
        print(f"Total length: {len(bill_doc.body_text)} characters")
        print(f"Lines: {len(bill_doc.body_text.splitlines())}")

        # Show JSON serialization
        print(f"\n--- JSON SERIALIZATION (metadata only) ---")
        metadata_dict = {
            'bill_id': bill_doc.bill_id,
            'title': bill_doc.title,
            'sponsors': bill_doc.sponsors,
            'committee': bill_doc.committee,
            'amended_code_refs': bill_doc.amended_code_refs
        }
        print(json.dumps(metadata_dict, indent=2))

        # Cleanup
        pdf_path.unlink()

    except requests.RequestException as e:
        print(f"ERROR downloading: {e}")
    except Exception as e:
        print(f"ERROR processing: {e}")


if __name__ == "__main__":
    # 1. Random bill from session 131
    demo_bill_extraction("131", "131-LD-0100")

    # 2. Bill with amendment from session 131
    demo_bill_extraction("131", "131-LD-0002-CA_A_H221")

    # 3. Bill from different session (132)
    demo_bill_extraction("132", "132-LD-0050")
