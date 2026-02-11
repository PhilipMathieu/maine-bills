from pathlib import Path
from typing import List, Optional
from dataclasses import dataclass, field
from datetime import date
from pypdf import PdfReader
import re


@dataclass
class BillDocument:
    """Structured representation of a Maine legislature bill."""

    # Metadata
    bill_id: str                          # e.g., "131-LD-0001"
    title: str                            # Bill's descriptive title
    session: str                          # Legislative session number
    body_text: str                        # Clean, extracted bill text
    extraction_confidence: float          # 0.0-1.0 confidence score

    # Optional metadata
    sponsors: List[str] = field(default_factory=list)  # Legislator names
    introduced_date: Optional[date] = None  # When bill was introduced
    committee: Optional[str] = None  # Assigned committee
    amended_code_refs: List[str] = field(default_factory=list)  # Maine state code sections being amended

    def __post_init__(self):
        """Validate extraction_confidence is between 0.0 and 1.0."""
        if not 0.0 <= self.extraction_confidence <= 1.0:
            raise ValueError(
                f"extraction_confidence must be between 0.0 and 1.0, "
                f"got {self.extraction_confidence}"
            )


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

    @staticmethod
    def _extract_bill_id(text: str) -> Optional[str]:
        """Extract bill ID from text (e.g., '131-LD-0001')."""
        match = re.search(r'(\d{2,3}-LD-\d{4})', text)
        return match.group(1) if match else None

    @staticmethod
    def _extract_title(text: str) -> str:
        """Extract bill title from beginning of text."""
        lines = text.split('\n')
        for i, line in enumerate(lines):
            stripped = line.strip()
            # Skip empty lines and numbers
            if stripped and not re.match(r'^\d+$', stripped):
                # Title usually starts with "An Act"
                if "An Act" in stripped:
                    return stripped
                # Otherwise take first non-empty line after bill ID
                if i > 0 and re.search(r'\d{2,3}-LD-\d{4}', lines[i-1]):
                    return stripped
        return "Unknown Title"

    @staticmethod
    def _extract_sponsors(text: str) -> List[str]:
        """Extract legislator names (sponsors) from text."""
        sponsors = []
        # Look for "by Representative/Senator NAME" patterns
        patterns = [
            r'(?:Introduced by|Rep\.|Representative)\s+([A-Z][A-Za-z\s]+)',
            r'(?:by|Cosponsored by|Senator|Sen\.)\s+([A-Z][A-Za-z\s]+)',
        ]

        for pattern in patterns:
            matches = re.findall(pattern, text[:1000])  # Search first 1000 chars
            sponsors.extend([m.strip() for m in matches])

        # Remove duplicates while preserving order
        seen = set()
        unique = []
        for s in sponsors:
            if s not in seen:
                unique.append(s)
                seen.add(s)

        return unique

    @staticmethod
    def _extract_session(text: str) -> Optional[str]:
        """Extract legislative session number from text."""
        match = re.search(r'(\d{2,3})-LD-\d{4}', text)
        return match.group(1) if match else None

    @staticmethod
    def _extract_date(text: str) -> Optional[date]:
        """Extract introduced date from text."""
        # Look for date patterns (optional - may not always be present)
        patterns = [
            r'(\d{1,2})/(\d{1,2})/(\d{4})',  # MM/DD/YYYY
            r'(\d{4})-(\d{1,2})-(\d{1,2})',  # YYYY-MM-DD
        ]

        for pattern in patterns:
            match = re.search(pattern, text[:2000])
            if match:
                try:
                    if '/' in pattern:
                        m, d, y = match.groups()
                        return date(int(y), int(m), int(d))
                    else:
                        y, m, d = match.groups()
                        return date(int(y), int(m), int(d))
                except ValueError:
                    continue

        return None

    @staticmethod
    def _extract_committee(text: str) -> Optional[str]:
        """Extract assigned committee from text."""
        # Look for "Committee on..." pattern
        match = re.search(r'(?:Committee on|Referred to|Assigned to)\s+([A-Za-z\s&]+?)(?:\n|$)', text[:2000])
        return match.group(1).strip() if match else None

    @staticmethod
    def _extract_amended_codes(text: str) -> List[str]:
        """Extract Maine state code references being amended."""
        refs = []
        # Look for patterns like "Title 20, Section 1" or "Title 20-A, § 101"
        patterns = [
            r'Title\s+(\d+(?:-[A-Z])?),\s*(?:Section|§)\s+(\d+)',
        ]

        for pattern in patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                ref = f"Title {match[0]}, Section {match[1]}"
                if ref not in refs:
                    refs.append(ref)

        return refs
