from pathlib import Path
from typing import List, Optional
from dataclasses import dataclass
from datetime import date
from pypdf import PdfReader


@dataclass
class BillDocument:
    """Structured representation of a Maine legislature bill."""

    # Metadata
    bill_id: str                          # e.g., "131-LD-0001"
    title: str                            # Bill's descriptive title
    sponsors: List[str]                   # Legislator names
    session: str                          # Legislative session number
    introduced_date: Optional[date]       # When bill was introduced
    committee: Optional[str]              # Assigned committee
    amended_code_refs: List[str]         # Maine state code sections being amended

    # Content
    body_text: str                        # Clean, extracted bill text
    extraction_confidence: float          # 0.0-1.0 confidence score


class TextExtractor:
    """Extracts text from PDF bill documents."""

    @staticmethod
    def extract_from_pdf(pdf_path: Path) -> str:
        """
        Extract all text from a PDF file.

        Args:
            pdf_path: Path to the PDF file

        Returns:
            Extracted text with newlines preserved

        Raises:
            FileNotFoundError: If PDF file doesn't exist
            Exception: If PDF parsing fails
        """
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        reader = PdfReader(pdf_path)
        lines: List[str] = []

        for page in reader.pages:
            text_all = page.extract_text()
            lines.extend(text_all.split('\n'))

        return '\n'.join(lines)

    @staticmethod
    def save_text(output_path: Path, text: str) -> None:
        """
        Save extracted text to a file.

        Args:
            output_path: Path where text file should be written
            text: Text content to save

        Raises:
            IOError: If file write fails
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w') as f:
            f.write(text)
