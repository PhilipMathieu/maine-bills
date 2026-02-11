from pathlib import Path
from typing import List, Optional
from dataclasses import dataclass, field
from datetime import date
from pypdf import PdfReader
import fitz  # PyMuPDF
import re
import json
import dataclasses


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
    def extract_bill_document(pdf_path: Path) -> BillDocument:
        """
        Extract structured bill data from PDF using PyMuPDF.

        Args:
            pdf_path: Path to the PDF file

        Returns:
            BillDocument with metadata and clean body text

        Raises:
            FileNotFoundError: If PDF file doesn't exist
        """
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        with fitz.open(pdf_path) as doc:
            # Extract text from all pages using list comprehension
            pages = [page.get_text() for page in doc]
            full_text = '\n'.join(pages) + '\n'

        # Parse metadata
        metadata = {
            'bill_id': TextExtractor._extract_bill_id(full_text),
            'title': TextExtractor._extract_title(full_text),
            'sponsors': TextExtractor._extract_sponsors(full_text),
            'session': TextExtractor._extract_session(full_text),
            'introduced_date': TextExtractor._extract_date(full_text),
            'committee': TextExtractor._extract_committee(full_text),
            'amended_code_refs': TextExtractor._extract_amended_codes(full_text),
        }

        # Clean body text
        body_text = TextExtractor._clean_body_text(full_text, metadata)

        # Estimate confidence
        confidence = TextExtractor._estimate_confidence(full_text)

        return BillDocument(
            body_text=body_text,
            extraction_confidence=confidence,
            **metadata
        )

    @staticmethod
    def _estimate_confidence(text: str) -> float:
        """
        Estimate extraction confidence (0.0-1.0).

        Simple heuristic: higher confidence if text is substantial
        and contains expected keywords.
        """
        # Base confidence on text length
        confidence = min(1.0, len(text) / 5000.0)

        # Boost confidence if bill structure keywords found
        keywords = ['AMENDMENT', 'SECTION', 'enacted', 'Title']
        found_keywords = sum(1 for kw in keywords if kw in text)
        confidence += (found_keywords * 0.05)

        return min(1.0, confidence)

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
    def save_bill_document_json(output_path: Path, bill_doc: BillDocument) -> None:
        """
        Save BillDocument to JSON file.

        Args:
            output_path: Path where JSON file should be written
            bill_doc: BillDocument to save

        Raises:
            IOError: If file write fails
            PermissionError: If directory creation fails
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Convert dataclass to dict
        doc_dict = dataclasses.asdict(bill_doc)

        # Serialize all date fields to ISO format
        for key, value in doc_dict.items():
            if isinstance(value, date):
                doc_dict[key] = value.isoformat()

        with open(output_path, 'w') as f:
            json.dump(doc_dict, f, indent=2)

    @staticmethod
    def _extract_bill_id(text: str) -> Optional[str]:
        """
        Extract bill ID from text (e.g., '131-LD-0001').

        Uses multi-fallback approach:
        1. Try direct pattern match (fastest)
        2. Try component extraction from session + LD number (flexible)
        """
        # Primary: Try standard format first: "131-LD-1693"
        match = re.search(r'(\d{2,3})-LD-(\d{3,4})', text)
        if match:
            return match.group(0)

        # Fallback: Extract from separate components
        # Normalize whitespace to handle line breaks
        normalized_text = ' '.join(text.split())

        # Extract session from ordinal format: "131st MAINE LEGISLATURE"
        session_match = re.search(r'(\d{2,3})(?:st|nd|rd|th)\s+(?:MAINE\s+)?LEGISLATURE', normalized_text)

        # Extract LD number from various patterns
        ld_match = re.search(r'(?:Legislative\s+Document|Document)\s+No\.?\s+(\d{3,4})', normalized_text)
        if not ld_match:
            ld_match = re.search(r'No\.?\s+(\d{3,4})', normalized_text)

        if session_match and ld_match:
            session = session_match.group(1)
            ld_number = ld_match.group(1).zfill(4)  # Zero-pad to 4 digits
            return f"{session}-LD-{ld_number}"

        return None

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
        """
        Extract legislator names (sponsors) from text.

        Handles multi-line sponsor blocks and comma-separated lists.
        Supports both "Presented by" (real bills) and "Introduced by" (some bills/tests).
        """
        sponsors = []
        search_text = text[:2500]
        normalized_text = ' '.join(search_text.split())

        # Title filter - exclude these common false positives
        title_words = {
            # Leadership titles
            'President', 'Speaker', 'Secretary', 'Clerk', 'Chief',
            'Governor', 'Mayor', 'Attorney', 'General', 'Commissioner', 'Treasurer',
            # Government entities
            'State', 'States', 'Department', 'Senate', 'House', 'Bureau',
            'Office', 'Committee', 'Government', 'Council', 'Commission', 'Administration',
            # Document references
            'Session', 'Regular', 'Special', 'Legislature', 'Legislative',
            'Constitution', 'People', 'Law', 'Code', 'Rules',
            # Generic/Article words
            'The', 'Maine', 'Number'
        }

        # Helper function to validate names
        def is_valid_name(name: str) -> bool:
            """Check if extracted text is a valid legislator name."""
            if not name or name in sponsors or len(name.split()) > 2:
                return False
            # Check if any word in the name is a title word (word-level filtering)
            name_words = set(name.split())
            return not name_words.intersection(title_words)

        # Pattern 1: "Presented by Senator/Representative/President/Speaker NAME [of DISTRICT]"
        pattern1 = r'(?:Presented|Introduced) by\s+(?:Senator|Representative|President|Speaker)\s+([A-Z][A-Za-z\'\-]+(?:\s+[A-Z][A-Za-z\'\-]+)?)\s+of\s+[A-Za-z\s]+'
        for match in re.finditer(pattern1, normalized_text):
            name = match.group(1).strip()
            if is_valid_name(name):
                sponsors.append(name)

        # Pattern 1b: "Presented by Senator/Representative/President/Speaker NAME" (without district)
        # Use lookahead to stop at keywords that indicate end of sponsor name
        pattern1b = r'(?:Presented|Introduced) by\s+(?:Senator|Representative|President|Speaker)\s+([A-Z][A-Za-z\'\-]+(?:\s+[A-Z][A-Za-z\'\-]+)?)(?=\s+(?:Cosponsored|Be it|of|and|,)|$)'
        for match in re.finditer(pattern1b, normalized_text):
            name = match.group(1).strip()
            if is_valid_name(name):
                sponsors.append(name)

        # Pattern 2: Cosponsorship block
        cosp_block_match = re.search(r'Cosponsored by\s+(.+?)(?=\n\n|Be it enacted|Presented by|Introduced by|$)', normalized_text, re.DOTALL)
        if cosp_block_match:
            cosp_block = ' '.join(cosp_block_match.group(1).split())

            # Extract from "Representative/Senator/President/Speaker NAME of DISTRICT" pattern
            person_pattern = r'(?:Senator|Representative|President|Speaker)\s+([A-Z][A-Za-z\'\-]+(?:\s+[A-Z][A-Za-z\'\-]+)?)\s+of\s+[A-Za-z\s]+(?:\s+and)?'
            for match in re.finditer(person_pattern, cosp_block):
                name = match.group(1).strip()
                if is_valid_name(name):
                    sponsors.append(name)

            # Extract without "of" district
            person_pattern_no_district = r'(?:Senator|Representative|President|Speaker)\s+([A-Z][A-Za-z\'\-]+(?:\s+[A-Z][A-Za-z\'\-]+)?)\b(?:\s+(?:and|of)|,|$)'
            for match in re.finditer(person_pattern_no_district, cosp_block):
                name = match.group(1).strip()
                if is_valid_name(name):
                    sponsors.append(name)

            # Comma-separated names with districts
            # Remove "Senator/Representative/President/Speaker NAME" patterns first to prevent capturing title words
            cleaned_block = re.sub(r'\b(?:Senator|Representative|President|Speaker)\s+[A-Z][A-Za-z\'\-]+(?:\s+[A-Z][A-Za-z\'\-]+)?\b', '', cosp_block)
            comma_separated = re.findall(r'([A-Z][A-Za-z\'\-]+(?:\s+[A-Z][A-Za-z\'\-]+)?)\s+of\s+[A-Za-z\s]+', cleaned_block)
            for name in comma_separated:
                name = name.strip()
                if is_valid_name(name):
                    sponsors.append(name)

        # Remove duplicates while preserving order
        seen = set()
        unique = []
        for s in sponsors:
            normalized = s.strip()
            if normalized and normalized not in seen:
                unique.append(normalized)
                seen.add(normalized)

        return unique

    @staticmethod
    def _extract_session(text: str) -> Optional[str]:
        """
        Extract legislative session number from text.

        Supports multiple formats with whitespace normalization.
        """
        # First try full bill ID format
        match = re.search(r'(\d{2,3})-LD-\d{4}', text)
        if match:
            return match.group(1)

        # Normalize whitespace to handle line breaks
        search_text = ' '.join(text[:2000].split())

        # Ordinal format: "131st MAINE LEGISLATURE"
        match = re.search(r'(\d{2,3})(?:st|nd|rd|th)\s+(?:MAINE\s+)?LEGISLATURE', search_text)
        if match:
            return match.group(1)

        # Fallback: Ordinal without "LEGISLATURE"
        match = re.search(r'(\d{2,3})(?:st|nd|rd|th)\s+(?:Maine|MAINE)', search_text)
        if match:
            return match.group(1)

        return None

    @staticmethod
    def _extract_date(text: str) -> Optional[date]:
        """
        Extract introduced date from text.

        Supports multiple date formats including month names.
        """
        months = {
            'January': 1, 'February': 2, 'March': 3, 'April': 4,
            'May': 5, 'June': 6, 'July': 7, 'August': 8,
            'September': 9, 'October': 10, 'November': 11, 'December': 12,
            'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4,
            'May': 5, 'Jun': 6, 'Jul': 7, 'Aug': 8,
            'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12,
        }

        search_text = text[:2500]
        normalized_search = ' '.join(search_text.split())

        # Pattern 1: "House/Senate of Representatives, January 26, 2023"
        match = re.search(
            r'(?:House|Senate) of Representatives,\s+(January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2}),?\s+(\d{4})',
            normalized_search
        )
        if match:
            month_name, day, year = match.groups()
            month = months.get(month_name)
            if month:
                try:
                    return date(int(year), month, int(day))
                except ValueError:
                    pass

        # Pattern 2: "In Senate, January 26, 2023"
        match = re.search(
            r'In\s+(?:Senate|House),\s+(January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2}),?\s+(\d{4})',
            normalized_search
        )
        if match:
            month_name, day, year = match.groups()
            month = months.get(month_name)
            if month:
                try:
                    return date(int(year), month, int(day))
                except ValueError:
                    pass

        # Pattern 3: General written date format
        match = re.search(
            r'(January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2}),?\s+(\d{4})',
            normalized_search
        )
        if match:
            month_name, day, year = match.groups()
            month = months.get(month_name)
            if month:
                try:
                    return date(int(year), month, int(day))
                except ValueError:
                    pass

        # Pattern 4: MM/DD/YYYY
        match = re.search(r'(\d{1,2})/(\d{1,2})/(\d{4})', normalized_search)
        if match:
            m, d, y = match.groups()
            try:
                return date(int(y), int(m), int(d))
            except ValueError:
                pass

        # Pattern 5: YYYY-MM-DD
        match = re.search(r'(\d{4})-(\d{1,2})-(\d{1,2})', normalized_search)
        if match:
            y, m, d = match.groups()
            try:
                return date(int(y), int(m), int(d))
            except ValueError:
                pass

        return None

    @staticmethod
    def _extract_committee(text: str) -> Optional[str]:
        """
        Extract assigned committee from text.

        Uses non-greedy matching with keyword delimiters to avoid
        capturing trailing action text like "suggested and ordered".
        """
        search_text = text[:2500]
        normalized_text = ' '.join(search_text.split())

        # Pattern 1: "Reference to the Committee on COMMITTEE_NAME"
        # Use lookahead to stop at action keywords
        match = re.search(
            r'Reference to the Committee on\s+([A-Za-z\s&,]+?)(?=\s+(?:suggested|ordered|referred|assigned|printed))',
            normalized_text
        )
        if match:
            committee = match.group(1).strip()
            if committee:
                return committee

        # Pattern 2: With period or end of text
        match = re.search(
            r'Reference to the Committee on\s+([A-Za-z\s&,]+?)(?:\.|$)',
            normalized_text
        )
        if match:
            committee = match.group(1).strip()
            # Clean up any trailing markers
            committee = re.sub(r'\s+(?:suggested|ordered|referred|assigned).*$', '', committee, flags=re.IGNORECASE)
            if committee:
                return committee

        # Pattern 3: Alternative patterns
        match = re.search(
            r'(?:Committee on|Referred to|Assigned to)\s+([A-Za-z\s&,]+?)(?:\s+(?:suggested|ordered|referred|assigned)|\.|\s+printed|$)',
            normalized_text
        )
        if match:
            committee = match.group(1).strip()
            if committee:
                return committee

        return None

    @staticmethod
    def _extract_amended_codes(text: str) -> List[str]:
        """
        Extract Maine state code references being amended.

        Supports both traditional "Title X, Section Y" format
        and MRSA (Maine Revised Statutes Annotated) format.
        """
        refs = []

        # Pattern 1: Traditional Title format "Title 20, Section 1" or "Title 20-A, § 101"
        title_pattern = r'Title\s+(\d+(?:-[A-Z])?),\s*(?:Section|§)\s+(\d+)'
        for match in re.finditer(title_pattern, text):
            ref = f"Title {match.group(1)}, Section {match.group(2)}"
            if ref not in refs:
                refs.append(ref)

        # Pattern 2: MRSA format "35-A MRSA §4002" or "5 MRSA §12004-G"
        mrsa_pattern = r'(\d+(?:-[A-Z])?)\s+MRSA\s+§(\d+(?:-[A-Z])?)'
        for match in re.finditer(mrsa_pattern, text):
            ref = f"{match.group(1)} MRSA §{match.group(2)}"
            if ref not in refs:
                refs.append(ref)

        return refs

    @staticmethod
    def _is_line_number(line: str) -> bool:
        """Check if line is just a line number."""
        return bool(re.match(r'^\s+\d+\s*$', line))

    @staticmethod
    def _is_header_footer(line: str) -> bool:
        """Check if line is a header or footer."""
        line_stripped = line.strip()

        # Page numbers and pagination
        if re.match(r'^Page\s+\d+', line_stripped, re.IGNORECASE):
            return True

        # Bill IDs
        if re.match(r'^\d{2,3}-LD-\d{4}$', line_stripped):
            return True

        # Common headers
        if re.match(r'^(STATE OF MAINE|MAINE LEGISLATURE)', line_stripped, re.IGNORECASE):
            return True

        return False

    @staticmethod
    def _clean_body_text(text: str, metadata: dict) -> str:
        """
        Clean extracted text by removing:
        - Line numbers
        - Page headers/footers
        - Excessive whitespace
        """
        lines = text.split('\n')
        cleaned_lines = []

        for line in lines:
            # Skip line number patterns (just whitespace and number)
            if TextExtractor._is_line_number(line):
                continue

            # Skip headers/footers
            if TextExtractor._is_header_footer(line):
                continue

            # Remove leading line numbers from lines with content
            # Pattern: leading whitespace + digits + more content
            line_cleaned = re.sub(r'^\s+\d+\s+', '', line)

            # Keep non-empty lines
            if line_cleaned.strip():
                cleaned_lines.append(line_cleaned)

        # Join and normalize excessive blank lines (max 2 consecutive)
        body_text = '\n'.join(cleaned_lines)
        body_text = re.sub(r'\n\n\n+', '\n\n', body_text)

        return body_text.strip()
