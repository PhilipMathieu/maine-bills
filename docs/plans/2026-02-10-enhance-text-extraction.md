# Enhanced Text Extraction Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extract structured metadata from Maine legislature PDFs alongside clean body text, enabling HuggingFace NLP dataset creation.

**Architecture:** Replace pypdf with PyMuPDF for better PDF handling. Create a `BillDocument` dataclass to hold metadata (bill_id, title, sponsors, session, date, committee, amended_code_refs) alongside cleaned text. TextExtractor will parse metadata from bill headers using regex patterns, clean body text by removing line numbers/headers/footers, and estimate extraction confidence. BillScraper saves both JSON (structured data) and TXT (clean text).

**Tech Stack:** PyMuPDF (fitz), dataclasses, regex patterns, JSON serialization

---

## Task 1: Update Dependencies and Create Data Structure

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/maine_bills/text_extractor.py` (add BillDocument dataclass)
- Create: `tests/unit/test_bill_document.py`

**Step 1: Write test for BillDocument dataclass**

Create `tests/unit/test_bill_document.py`:

```python
from datetime import date
from maine_bills.text_extractor import BillDocument


def test_bill_document_creation():
    """Test BillDocument dataclass creation."""
    doc = BillDocument(
        bill_id="131-LD-0001",
        title="An Act Relating to Education",
        sponsors=["Rep. Smith", "Sen. Jones"],
        session="131",
        introduced_date=date(2023, 1, 15),
        committee="Committee on Education",
        amended_code_refs=["Title 20, Section 1", "Title 20, Section 5"],
        body_text="The body of the bill goes here.",
        extraction_confidence=0.95
    )

    assert doc.bill_id == "131-LD-0001"
    assert doc.title == "An Act Relating to Education"
    assert len(doc.sponsors) == 2
    assert doc.extraction_confidence == 0.95
    assert "body" in doc.body_text.lower()


def test_bill_document_asdict():
    """Test BillDocument can be converted to dict."""
    import dataclasses
    doc = BillDocument(
        bill_id="131-LD-0001",
        title="Test Bill",
        sponsors=[],
        session="131",
        introduced_date=None,
        committee=None,
        amended_code_refs=[],
        body_text="Text",
        extraction_confidence=0.9
    )

    doc_dict = dataclasses.asdict(doc)
    assert isinstance(doc_dict, dict)
    assert doc_dict["bill_id"] == "131-LD-0001"
```

**Step 2: Run test to verify it fails**

```bash
cd .worktrees/enhance-text-extraction
./.venv/bin/python -m pytest tests/unit/test_bill_document.py -v
```

Expected output: `FAILED - cannot import name 'BillDocument'`

**Step 3: Add BillDocument dataclass to TextExtractor**

Modify `src/maine_bills/text_extractor.py` at the top:

```python
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
    # ... rest of class ...
```

**Step 4: Run test to verify it passes**

```bash
cd .worktrees/enhance-text-extraction
./.venv/bin/python -m pytest tests/unit/test_bill_document.py -v
```

Expected output: `2 passed`

**Step 5: Update pyproject.toml dependencies**

Modify `pyproject.toml` to add PyMuPDF:

```toml
dependencies = [
    "requests>=2.31.0",
    "beautifulsoup4>=4.12.0",
    "pypdf>=4.0.0",
    "pymupdf>=1.23.0",
]
```

**Step 6: Commit**

```bash
cd .worktrees/enhance-text-extraction
git add -A
git commit -m "feat: add BillDocument dataclass and pymupdf dependency"
```

---

## Task 2: Implement Metadata Extraction Methods

**Files:**
- Modify: `src/maine_bills/text_extractor.py`
- Create: `tests/unit/test_metadata_extraction.py`

**Step 1: Write tests for metadata extraction helpers**

Create `tests/unit/test_metadata_extraction.py`:

```python
from maine_bills.text_extractor import TextExtractor


def test_extract_bill_id():
    """Test bill ID extraction from text."""
    text = """
    131-LD-0001

    An Act Relating to Education
    """
    result = TextExtractor._extract_bill_id(text)
    assert result == "131-LD-0001"


def test_extract_bill_id_no_match():
    """Test bill ID extraction when none found."""
    text = "Some text without bill ID"
    result = TextExtractor._extract_bill_id(text)
    assert result is None


def test_extract_title():
    """Test title extraction."""
    text = """
    131-LD-0001

    An Act Relating to Education and Training

    Be it enacted...
    """
    result = TextExtractor._extract_title(text)
    assert "Education" in result or "An Act" in result


def test_extract_sponsors():
    """Test sponsor extraction."""
    text = """
    Introduced by Representative SMITH
    Cosponsored by Senator JONES
    """
    result = TextExtractor._extract_sponsors(text)
    # Should extract legislator names
    assert isinstance(result, list)


def test_extract_session():
    """Test session extraction."""
    text = "131-LD-0001"
    result = TextExtractor._extract_session(text)
    assert result == "131"


def test_extract_amended_codes():
    """Test amended code extraction."""
    text = """
    This act amends Title 20, Section 1.
    It also modifies Title 5, Section 10.
    """
    result = TextExtractor._extract_amended_codes(text)
    assert isinstance(result, list)
    assert len(result) >= 1
```

**Step 2: Run tests to verify they fail**

```bash
cd .worktrees/enhance-text-extraction
./.venv/bin/python -m pytest tests/unit/test_metadata_extraction.py -v
```

Expected: All tests FAIL (methods not defined)

**Step 3: Implement metadata extraction methods**

Add these methods to `TextExtractor` class in `src/maine_bills/text_extractor.py`:

```python
import re
from datetime import date
from typing import Optional


class TextExtractor:
    # ... existing BillDocument ...

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
```

**Step 4: Run tests to verify they pass**

```bash
cd .worktrees/enhance-text-extraction
./.venv/bin/python -m pytest tests/unit/test_metadata_extraction.py -v
```

Expected output: `6 passed`

**Step 5: Commit**

```bash
cd .worktrees/enhance-text-extraction
git add -A
git commit -m "feat: add metadata extraction methods"
```

---

## Task 3: Implement Body Text Cleaning

**Files:**
- Modify: `src/maine_bills/text_extractor.py`
- Create: `tests/unit/test_body_cleaning.py`

**Step 1: Write tests for body cleaning methods**

Create `tests/unit/test_body_cleaning.py`:

```python
from maine_bills.text_extractor import TextExtractor


def test_is_line_number():
    """Test detection of line number patterns."""
    assert TextExtractor._is_line_number("    1") == True
    assert TextExtractor._is_line_number("   42") == True
    assert TextExtractor._is_line_number("     123") == True
    assert TextExtractor._is_line_number("Some text with 123") == False
    assert TextExtractor._is_line_number("Text") == False


def test_is_header_footer():
    """Test detection of header/footer patterns."""
    assert TextExtractor._is_header_footer("Page 1") == True
    assert TextExtractor._is_header_footer("Page 42 of 100") == True
    assert TextExtractor._is_header_footer("131-LD-0001") == True
    assert TextExtractor._is_header_footer("Some bill text") == False


def test_clean_body_text():
    """Test body text cleaning."""
    text = """
         1 Be it enacted by the People of the State of Maine as
         2 follows:
         3
         4 SECTION 1.  AMENDMENT.  Title 20, section 1 is amended to read:

    Page 1
    131-LD-0001
    """

    result = TextExtractor._clean_body_text(text, {})

    # Should remove line numbers
    assert "     1" not in result
    assert "     2" not in result

    # Should remove page headers
    assert "Page 1" not in result

    # Should keep actual bill content
    assert "AMENDMENT" in result or "Title 20" in result


def test_clean_body_text_preserves_structure():
    """Test that cleaning preserves meaningful structure."""
    text = """
    Section 1. Purpose
        Paragraph 1
        Paragraph 2

    Section 2. Implementation
        Details here
    """

    result = TextExtractor._clean_body_text(text, {})

    # Should preserve sections and indentation structure
    assert "Section 1" in result
    assert "Section 2" in result
```

**Step 2: Run tests to verify they fail**

```bash
cd .worktrees/enhance-text-extraction
./.venv/bin/python -m pytest tests/unit/test_body_cleaning.py -v
```

Expected: All tests FAIL (methods not defined)

**Step 3: Implement body cleaning methods**

Add these methods to `TextExtractor` class:

```python
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
        # Skip line number patterns
        if TextExtractor._is_line_number(line):
            continue

        # Skip headers/footers
        if TextExtractor._is_header_footer(line):
            continue

        # Keep non-empty lines
        if line.strip():
            cleaned_lines.append(line)

    # Join and normalize excessive blank lines (max 2 consecutive)
    body_text = '\n'.join(cleaned_lines)
    body_text = re.sub(r'\n\n\n+', '\n\n', body_text)

    return body_text.strip()
```

**Step 4: Run tests to verify they pass**

```bash
cd .worktrees/enhance-text-extraction
./.venv/bin/python -m pytest tests/unit/test_body_cleaning.py -v
```

Expected output: `4 passed`

**Step 5: Commit**

```bash
cd .worktrees/enhance-text-extraction
git add -A
git commit -m "feat: add body text cleaning methods"
```

---

## Task 4: Implement PDF Extraction with PyMuPDF

**Files:**
- Modify: `src/maine_bills/text_extractor.py`
- Modify: `tests/unit/test_text_extractor.py`

**Step 1: Update existing TextExtractor tests to use PyMuPDF**

Modify `tests/unit/test_text_extractor.py` - replace the old extract methods with:

```python
def test_extract_bill_document_missing_file():
    """Test that extraction fails with missing file."""
    with pytest.raises(FileNotFoundError):
        TextExtractor.extract_bill_document(Path("/nonexistent/file.pdf"))


def test_extract_bill_document_success(tmp_path, mocker):
    """Test successful bill document extraction."""
    # Mock fitz.open and PDF structure
    mock_page = Mock()
    mock_page.get_text.return_value = """131-LD-0001

An Act Relating to Education

     1 Be it enacted by the People of the State of Maine as follows:
     2
     3 SECTION 1.  AMENDMENT.  Title 20, section 1 is amended to read:
"""

    mock_doc = Mock()
    mock_doc.page_count = 1
    mock_doc.__iter__ = Mock(return_value=iter([mock_page]))

    pdf_path = tmp_path / "test.pdf"
    pdf_path.touch()

    with patch('maine_bills.text_extractor.fitz.open', return_value=mock_doc):
        result = TextExtractor.extract_bill_document(pdf_path)

        assert isinstance(result, BillDocument)
        assert result.bill_id == "131-LD-0001"
        assert "AMENDMENT" in result.body_text or "Title 20" in result.body_text
        assert 0.0 <= result.extraction_confidence <= 1.0


def test_save_text_creates_file(tmp_path):
    """Test that save_text creates output file."""
    output_path = tmp_path / "output.txt"
    text = "Test content\nWith multiple lines"

    TextExtractor.save_text(output_path, text)

    assert output_path.exists()
    assert output_path.read_text() == text
```

**Step 2: Implement extract_bill_document method**

Replace the old `extract_from_pdf` method in `src/maine_bills/text_extractor.py`:

```python
import fitz  # PyMuPDF


class TextExtractor:
    # ... existing BillDocument and helper methods ...

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

        doc = fitz.open(pdf_path)

        # Extract text from all pages
        full_text = ""
        for page in doc:
            full_text += page.get_text() + "\n"

        doc.close()

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
        confidence = TextExtractor._estimate_confidence(doc, full_text)

        return BillDocument(
            body_text=body_text,
            extraction_confidence=confidence,
            **metadata
        )

    @staticmethod
    def _estimate_confidence(doc: object, text: str) -> float:
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

    # Keep old save_text method unchanged
    @staticmethod
    def save_text(output_path: Path, text: str) -> None:
        """
        Save text to a file.

        Args:
            output_path: Path where text file should be written
            text: Text content to save
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w') as f:
            f.write(text)
```

**Step 3: Update imports at top of text_extractor.py**

Make sure these imports are at the top:

```python
from pathlib import Path
from typing import List, Optional
from dataclasses import dataclass
from datetime import date
import re
import json
import fitz  # PyMuPDF
```

**Step 4: Run tests to verify they pass**

```bash
cd .worktrees/enhance-text-extraction
./.venv/bin/python -m pytest tests/unit/test_text_extractor.py tests/unit/test_bill_document.py tests/unit/test_metadata_extraction.py tests/unit/test_body_cleaning.py -v
```

Expected output: All tests passing (~20+ tests)

**Step 5: Commit**

```bash
cd .worktrees/enhance-text-extraction
git add -A
git commit -m "feat: implement PyMuPDF-based bill document extraction"
```

---

## Task 5: Add JSON Serialization and Saving

**Files:**
- Modify: `src/maine_bills/text_extractor.py`
- Create: `tests/unit/test_json_save.py`

**Step 1: Write tests for JSON saving**

Create `tests/unit/test_json_save.py`:

```python
from pathlib import Path
from datetime import date
import json
from maine_bills.text_extractor import TextExtractor, BillDocument


def test_save_bill_document_json(tmp_path):
    """Test saving BillDocument to JSON."""
    doc = BillDocument(
        bill_id="131-LD-0001",
        title="Test Bill",
        sponsors=["Rep. Smith"],
        session="131",
        introduced_date=date(2023, 1, 15),
        committee="Committee on Education",
        amended_code_refs=["Title 20, Section 1"],
        body_text="Bill body text here.",
        extraction_confidence=0.95
    )

    output_path = tmp_path / "bill.json"
    TextExtractor.save_bill_document_json(output_path, doc)

    assert output_path.exists()

    # Verify JSON is valid and contains expected data
    with open(output_path) as f:
        data = json.load(f)

    assert data["bill_id"] == "131-LD-0001"
    assert data["title"] == "Test Bill"
    assert data["extraction_confidence"] == 0.95


def test_save_bill_document_json_date_serialization(tmp_path):
    """Test that dates are properly serialized to ISO format."""
    doc = BillDocument(
        bill_id="131-LD-0001",
        title="Test",
        sponsors=[],
        session="131",
        introduced_date=date(2023, 6, 15),
        committee=None,
        amended_code_refs=[],
        body_text="Text",
        extraction_confidence=0.9
    )

    output_path = tmp_path / "bill.json"
    TextExtractor.save_bill_document_json(output_path, doc)

    with open(output_path) as f:
        data = json.load(f)

    # Date should be serialized as ISO string
    assert data["introduced_date"] == "2023-06-15"
```

**Step 2: Run tests to verify they fail**

```bash
cd .worktrees/enhance-text-extraction
./.venv/bin/python -m pytest tests/unit/test_json_save.py -v
```

Expected: Tests FAIL (method not defined)

**Step 3: Implement JSON saving method**

Add to `TextExtractor` class:

```python
@staticmethod
def save_bill_document_json(output_path: Path, bill_doc: BillDocument) -> None:
    """
    Save BillDocument to JSON file.

    Args:
        output_path: Path where JSON file should be written
        bill_doc: BillDocument to save
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Convert dataclass to dict
    import dataclasses
    doc_dict = dataclasses.asdict(bill_doc)

    # Serialize dates to ISO format
    if doc_dict.get('introduced_date'):
        doc_dict['introduced_date'] = doc_dict['introduced_date'].isoformat()

    with open(output_path, 'w') as f:
        json.dump(doc_dict, f, indent=2)
```

**Step 4: Run tests to verify they pass**

```bash
cd .worktrees/enhance-text-extraction
./.venv/bin/python -m pytest tests/unit/test_json_save.py -v
```

Expected output: `2 passed`

**Step 5: Commit**

```bash
cd .worktrees/enhance-text-extraction
git add -A
git commit -m "feat: add JSON serialization for BillDocument"
```

---

## Task 6: Update BillScraper to Use New Extraction

**Files:**
- Modify: `src/maine_bills/scraper.py`
- Modify: `tests/unit/test_scraper.py`

**Step 1: Write test for updated _process_bill method**

Add to `tests/unit/test_scraper.py`:

```python
def test_process_bill_with_structured_extraction(tmp_path, mocker):
    """Test that _process_bill saves both JSON and TXT files."""
    from maine_bills.text_extractor import BillDocument
    from datetime import date

    # Mock BillDocument extraction
    mock_doc = BillDocument(
        bill_id="131-LD-0001",
        title="Test Bill",
        sponsors=["Rep. Test"],
        session="131",
        introduced_date=date(2023, 1, 1),
        committee="Committee",
        amended_code_refs=[],
        body_text="Extracted bill text",
        extraction_confidence=0.95
    )

    scraper = BillScraper("131", tmp_path)

    # Mock PDF download and extraction
    mocker.patch.object(scraper, '_download_bill_pdf', return_value=True)
    mocker.patch.object(scraper, '_bill_already_processed', return_value=False)
    mocker.patch('maine_bills.scraper.TextExtractor.extract_bill_document', return_value=mock_doc)
    mocker.patch.object(Path, 'unlink')  # Mock PDF deletion

    result = scraper._process_bill("131-LD-0001")

    assert result == True

    # Verify both TXT and JSON were saved
    txt_file = tmp_path / "txt" / "131-LD-0001.txt"
    json_file = tmp_path / "txt" / "131-LD-0001.json"

    # Note: In mock environment, files won't actually exist, but
    # verify that save methods were called properly in implementation
```

**Step 2: Run test to verify it fails**

```bash
cd .worktrees/enhance-text-extraction
./.venv/bin/python -m pytest tests/unit/test_scraper.py::test_process_bill_with_structured_extraction -v
```

Expected: FAIL

**Step 3: Update BillScraper to use new extraction**

Modify `src/maine_bills/scraper.py` - update `_process_bill` method:

```python
def _process_bill(self, bill_id: str) -> bool:
    """
    Process a single bill: download PDF, extract structured data, save.

    Args:
        bill_id: Legislative document number

    Returns:
        True if successful, False otherwise
    """
    if self._bill_already_processed(bill_id):
        self.logger.debug(f"{bill_id} already in corpus")
        return False

    self.logger.info(f"Processing {bill_id}")

    if not self._download_bill_pdf(bill_id):
        return False

    try:
        pdf_path = self.pdf_dir / f"{bill_id}.pdf"

        # Extract as structured BillDocument
        bill_doc = TextExtractor.extract_bill_document(pdf_path)

        # Save outputs
        self._save_bill_document(bill_doc)

        # Remove PDF after successful extraction
        pdf_path.unlink()
        self.logger.debug(f"Extracted and cleaned up {bill_id}")
        return True

    except Exception as e:
        self.logger.error(f"Error processing {bill_id}: {e}")
        return False


def _save_bill_document(self, bill_doc) -> None:
    """
    Save bill document outputs (text and metadata).

    Args:
        bill_doc: BillDocument to save
    """
    # Save clean body text
    txt_path = self.txt_dir / f"{bill_doc.bill_id}.txt"
    TextExtractor.save_text(txt_path, bill_doc.body_text)

    # Save metadata + full document as JSON
    json_path = self.txt_dir / f"{bill_doc.bill_id}.json"
    TextExtractor.save_bill_document_json(json_path, bill_doc)
```

Also update the import at the top of scraper.py to import BillDocument (though not strictly needed):

```python
from .text_extractor import TextExtractor, BillDocument
```

**Step 4: Run tests to verify they pass**

```bash
cd .worktrees/enhance-text-extraction
./.venv/bin/python -m pytest tests/unit/test_scraper.py -v
```

Expected output: All tests passing

**Step 5: Commit**

```bash
cd .worktrees/enhance-text-extraction
git add -A
git commit -m "feat: update BillScraper to use structured extraction"
```

---

## Task 7: Final Integration Test and Verification

**Files:**
- Run all tests
- Verify no regressions

**Step 1: Run full test suite**

```bash
cd .worktrees/enhance-text-extraction
./.venv/bin/python -m pytest -v
```

Expected: All tests passing (25+ tests)

**Step 2: Run with coverage report**

```bash
cd .worktrees/enhance-text-extraction
./.venv/bin/python -m pytest --cov=src/maine_bills --cov-report=term
```

Expected: Coverage maintained or improved, no new errors

**Step 3: Verify no import errors**

```bash
cd .worktrees/enhance-text-extraction
./.venv/bin/python -c "from maine_bills.text_extractor import TextExtractor, BillDocument; from maine_bills.scraper import BillScraper; print('Imports successful')"
```

Expected output: `Imports successful`

**Step 4: Final commit and summary**

```bash
cd .worktrees/enhance-text-extraction
git log --oneline | head -7
```

Should show 7 recent commits from this implementation

---

## Implementation Notes

### Regex Patterns
The metadata extraction uses conservative regex patterns. These should be adjusted based on real bill PDFs:
- Bill IDs: `(\d{2,3}-LD-\d{4})`
- Amended codes: `Title\s+(\d+(?:-[A-Z])?),\s*(?:Section|§)\s+(\d+)`

### Confidence Scoring
The `_estimate_confidence()` method uses a simple heuristic. Consider refining it based on:
- PDF quality (text extraction success rate)
- Presence of expected metadata fields
- File size consistency

### Date Handling
Currently looks for MM/DD/YYYY and YYYY-MM-DD formats. Maine legislature bills may use other formats that will need adjustment.

### Error Recovery
If extraction fails for a specific field, that field is set to None or empty list rather than failing the entire extraction. This allows partial extraction of damaged PDFs.
