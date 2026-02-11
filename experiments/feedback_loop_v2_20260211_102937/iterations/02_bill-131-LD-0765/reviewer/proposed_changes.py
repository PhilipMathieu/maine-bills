"""
Proposed improvements to TextExtractor methods.
Apply these to src/maine_bills/text_extractor.py

These methods address extraction failures in bill 131-LD-0765 and improve
overall metadata and text extraction quality.
"""

from pathlib import Path
from typing import List, Optional
from datetime import date
import re


@staticmethod
def _extract_session(text: str) -> Optional[str]:
    """
    Extract legislative session number from text.

    Handles both full format (131-LD-1234) and ordinal format (131st MAINE LEGISLATURE).
    """
    # First try full bill ID format
    match = re.search(r'(\d{2,3})-LD-\d{4}', text)
    if match:
        return match.group(1)

    # Fall back to ordinal format: "131st MAINE LEGISLATURE"
    match = re.search(r'(\d{2,3})(?:st|nd|rd|th)\s+MAINE\s+LEGISLATURE', text)
    if match:
        return match.group(1)

    return None


@staticmethod
def _extract_date(text: str) -> Optional[date]:
    """
    Extract introduced date from text.

    Handles multiple date formats:
    - MM/DD/YYYY
    - YYYY-MM-DD
    - "Month DD, YYYY" (e.g., "February 21, 2023")
    """
    # Month name to number mapping
    months = {
        'January': 1, 'February': 2, 'March': 3, 'April': 4,
        'May': 5, 'June': 6, 'July': 7, 'August': 8,
        'September': 9, 'October': 10, 'November': 11, 'December': 12,
        'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4,
        'May': 5, 'Jun': 6, 'Jul': 7, 'Aug': 8,
        'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12,
    }

    patterns = [
        # Written month format: "February 21, 2023" or "February 21 2023"
        (r'(January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2}),?\s+(\d{4})', 'written'),
        # MM/DD/YYYY
        (r'(\d{1,2})/(\d{1,2})/(\d{4})', 'slash'),
        # YYYY-MM-DD
        (r'(\d{4})-(\d{1,2})-(\d{1,2})', 'dash'),
    ]

    # Search in first 2000 chars where date typically appears
    search_text = text[:2000]

    for pattern, fmt in patterns:
        match = re.search(pattern, search_text)
        if match:
            try:
                if fmt == 'written':
                    month_name, day, year = match.groups()
                    month = months[month_name]
                    return date(int(year), month, int(day))
                elif fmt == 'slash':
                    m, d, y = match.groups()
                    return date(int(y), int(m), int(d))
                else:  # fmt == 'dash'
                    y, m, d = match.groups()
                    return date(int(y), int(m), int(d))
            except ValueError:
                continue

    return None


@staticmethod
def _extract_sponsors(text: str) -> List[str]:
    """
    Extract legislator names (sponsors) from text.

    Improved to handle:
    - "Presented by Senator/Representative NAME"
    - "Cosponsored by" blocks with multiple people
    - Complex multi-line sponsor lists
    - Names with apostrophes, hyphens, and districts
    """
    sponsors = []

    # First 2000 chars contain sponsor info
    search_text = text[:2000]

    # Pattern 1: "Presented by Senator/Representative NAME [of DISTRICT]"
    pattern1 = r'Presented by\s+(?:Senator|Representative|Rep\.)\s+([A-Z][A-Za-z\'\-]+(?:\s+[A-Z][A-Za-z\'\-]+)*?)(?:\s+of\s+[A-Za-z\s]+)?(?:\n|\.)'
    for match in re.finditer(pattern1, search_text):
        name = match.group(1).strip()
        if name:
            sponsors.append(name)

    # Pattern 2: "Cosponsored by Representative/Senator NAME" (single person)
    pattern2 = r'Cosponsored by\s+(?:Senator|Representative|Rep\.)\s+([A-Z][A-Za-z\'\-]+(?:\s+[A-Z][A-Za-z\'\-]+)*?)(?:\s+of\s+[A-Za-z\s]+)?(?:\n|\.|\s+and)'
    for match in re.finditer(pattern2, search_text):
        name = match.group(1).strip()
        if name:
            sponsors.append(name)

    # Pattern 3: Multi-line sponsor block starting with "Cosponsored by"
    # This handles the format where multiple senators/representatives are listed on subsequent lines
    cosp_match = re.search(r'Cosponsored by(.+?)(?=\n\n|\nPage|\n\d+|Be it enacted)', search_text, re.DOTALL)
    if cosp_match:
        cosp_block = cosp_match.group(1)
        # Extract individual names preceded by Senator/Representative
        name_pattern = r'(?:Senator|Representative|Rep\.)\s+([A-Z][A-Za-z\'\-]+(?:\s+[A-Z][A-Za-z\'\-]+)*?)(?:\s+of\s+[A-Za-z\s]+)?(?:,|\n|and)'
        for name_match in re.finditer(name_pattern, cosp_block):
            name = name_match.group(1).strip()
            if name and name not in sponsors:
                sponsors.append(name)

    # Pattern 4: Fallback for simpler "by NAME of PLACE" patterns
    pattern4 = r'(?:Introduced|Cosponsored)\s+by\s+([A-Z][A-Za-z\'\-]+(?:\s+[A-Z][A-Za-z\'\-]+)*?)(?:\s+of\s+[A-Za-z\s]+)?(?:\n|\.|\s+and)'
    for match in re.finditer(pattern4, search_text):
        name = match.group(1).strip()
        if name and name not in sponsors:
            sponsors.append(name)

    # Remove duplicates while preserving order
    seen = set()
    unique = []
    for s in sponsors:
        # Normalize: remove trailing commas, extra spaces
        normalized = s.rstrip(',').strip()
        if normalized and normalized not in seen:
            unique.append(normalized)
            seen.add(normalized)

    return unique


@staticmethod
def _extract_committee(text: str) -> Optional[str]:
    """
    Extract assigned committee from text.

    Improved to handle trailing text like "suggested and ordered printed"
    and more flexible punctuation.
    """
    # Search in first 2000 chars
    search_text = text[:2000]

    # Pattern: "Committee on COMMITTEE_NAME" with optional trailing text
    match = re.search(
        r'(?:Committee on|Referred to|Assigned to)\s+([A-Za-z\s&]+?)(?:\s+(?:suggested|ordered|referred|assigned)|,|\n|$)',
        search_text
    )
    if match:
        committee = match.group(1).strip()
        if committee:
            return committee

    # Alternative pattern: "Reference to the Committee on COMMITTEE_NAME"
    match = re.search(
        r'Reference to the Committee on\s+([A-Za-z\s&]+?)(?:\s+(?:suggested|ordered)|\.|\n|$)',
        search_text
    )
    if match:
        committee = match.group(1).strip()
        if committee:
            return committee

    return None


@staticmethod
def _extract_title(text: str) -> str:
    """
    Extract bill title from beginning of text.

    Improved to:
    - Handle titles that span multiple lines
    - Better detection of "An Act" titles
    - Continuation to next line if title seems incomplete
    """
    lines = text.split('\n')

    # Find the first "An Act" line
    title_start = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if "An Act" in stripped:
            title_start = i
            break

    if title_start is None:
        return "Unknown Title"

    # Build title, potentially spanning multiple lines
    title_lines = [lines[title_start].strip()]

    # Check if title continues on next line(s)
    # A line is a continuation if:
    # - It doesn't start a new section or metadata
    # - It's not a line number
    # - It starts with lowercase or continues the sentence
    i = title_start + 1
    while i < len(lines):
        next_line = lines[i].strip()

        # Stop conditions
        if not next_line:  # Empty line
            break
        if re.match(r'^\d+$', next_line):  # Just a number
            i += 1
            continue
        if any(marker in next_line for marker in ['Reference to', 'Presented by', 'Cosponsored']):
            break
        if re.match(r'^[A-Z][A-Z\s]+$', next_line) and len(next_line) < 30:  # ALL CAPS header
            break

        # If line starts with lowercase or looks like title continuation, add it
        if next_line and (next_line[0].islower() or next_line[0] in ['(', '–', '-']):
            title_lines.append(next_line)
            i += 1
        else:
            break

    title = ' '.join(title_lines).strip()
    return title if title else "Unknown Title"


@staticmethod
def _is_header_footer(line: str) -> bool:
    """
    Check if line is a header or footer that should be removed.

    Enhanced to catch more boilerplate text and institutional headers.
    """
    line_stripped = line.strip()

    # Empty line
    if not line_stripped:
        return False

    # Page numbers and pagination (e.g., "Page 2 - 131LR0999(01)")
    if re.match(r'^Page\s+\d+', line_stripped, re.IGNORECASE):
        return True

    # Bill reference IDs (e.g., "131-LD-0765")
    if re.match(r'^\d{2,3}-LD-\d{4}$', line_stripped):
        return True

    # Legislature headers
    if re.match(r'^(STATE OF MAINE|MAINE LEGISLATURE|MAINE STATE LEGISLATURE)', line_stripped, re.IGNORECASE):
        return True

    # Library reference boilerplate
    if any(phrase in line_stripped for phrase in [
        'Law and Legislative Digital Library',
        'Maine State Law and Legislative Reference Library',
        'legislature.maine.gov/lawlib',
        'Reproduced from electronic originals',
        'Printed on recycled paper',
        'may include minor formatting differences',
    ]):
        return True

    # Legislative document headers
    if re.match(r'^(?:Legislative Document|Session|First Regular Session)', line_stripped, re.IGNORECASE):
        return True

    # Session year markers
    if re.match(r'^\d{4}$', line_stripped):  # Just a year
        return True

    return False


@staticmethod
def _clean_body_text(text: str, metadata: dict) -> str:
    """
    Clean extracted text by removing:
    - Line numbers
    - Page headers/footers
    - Institutional boilerplate
    - Excessive whitespace
    - Document preamble metadata
    """
    lines = text.split('\n')
    cleaned_lines = []
    skip_until_content = True  # Skip boilerplate at start
    found_enactment = False

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

        # Skip document preamble until we hit the actual content
        if skip_until_content:
            # Keep going until we see "Be it enacted" or similar markers
            if any(marker in line_cleaned for marker in [
                'Be it enacted',
                'SUMMARY',
                'FISCAL NOTE',
            ]):
                skip_until_content = False
                # Include the "Be it enacted" line
                if line_cleaned.strip():
                    cleaned_lines.append(line_cleaned)
                continue
            else:
                # Still in preamble, skip unless it's sponsor/committee info
                # (We've already extracted that)
                if any(marker in line_cleaned for marker in [
                    'Presented by',
                    'Cosponsored',
                    'Committee on',
                    'Reference to',
                ]):
                    # Skip sponsor/committee metadata - already extracted
                    continue
                else:
                    # Other preamble, skip
                    continue

        # Keep non-empty lines after we've started processing content
        if line_cleaned.strip():
            cleaned_lines.append(line_cleaned)

    # Join and normalize excessive blank lines (max 2 consecutive)
    body_text = '\n'.join(cleaned_lines)
    body_text = re.sub(r'\n\n\n+', '\n\n', body_text)

    return body_text.strip()


@staticmethod
def _extract_bill_id(text: str) -> Optional[str]:
    """
    Extract bill ID from text (e.g., '131-LD-0765').

    Current implementation tries full format; enhanced version would
    combine session and LD number from document structure.
    """
    # Try standard format first: "131-LD-0765"
    match = re.search(r'(\d{2,3})-LD-(\d{4})', text)
    if match:
        return match.group(0)

    # Fallback: extract from separate components (less reliable but more coverage)
    # Look for session (ordinal format) and LD number separately
    session_match = re.search(r'(\d{2,3})(?:st|nd|rd|th)\s+MAINE\s+LEGISLATURE', text)
    ld_match = re.search(r'(?:No\.\s+|Document\s+No\.\s+)(\d{4})', text)

    if session_match and ld_match:
        session = session_match.group(1)
        ld_number = ld_match.group(1)
        return f"{session}-LD-{ld_number}"

    return None
