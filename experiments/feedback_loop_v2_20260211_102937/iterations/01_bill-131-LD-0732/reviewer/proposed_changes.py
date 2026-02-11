"""
Proposed improvements to TextExtractor.
Apply these to src/maine_bills/text_extractor.py

These methods provide enhanced metadata extraction with better pattern matching
and fallback strategies for Maine legislature bills.
"""

from pathlib import Path
from typing import List, Optional
from datetime import date
import re


@staticmethod
def _extract_bill_id(text: str) -> Optional[str]:
    """
    Extract bill ID from text (e.g., '131-LD-0732').

    Tries multiple approaches:
    1. Direct bill ID pattern match
    2. Parse from session + LD number components
    3. Convert from bill reference format (e.g., "131LR0290" → "131-LD-0290")
    """
    # Approach 1: Try direct pattern match
    match = re.search(r'(\d{2,3})-LD-(\d{4})', text)
    if match:
        return match.group(0)

    # Approach 2: Parse from separate components
    # Extract session from legislature line
    session_match = re.search(r'(\d{2,3})(?:st|nd|rd|th)\s+MAINE LEGISLATURE', text)
    if session_match:
        session = session_match.group(1)

        # Look for "No. XXX" which indicates the LD number
        ld_match = re.search(r'No\.\s+(\d{3,4})', text[:1000])
        if ld_match:
            ld_number = ld_match.group(1).zfill(4)
            return f"{session}-LD-{ld_number}"

    # Approach 3: Parse from bill reference format (e.g., "131LR0290")
    # This format appears in page footers like "Page 1 - 131LR0290(01)"
    ref_match = re.search(r'(\d{2,3})LR(\d{4})', text)
    if ref_match:
        session = ref_match.group(1)
        lr_number = ref_match.group(2)
        # Convert LR number to LD number (usually same, but LR format is legislative reference)
        return f"{session}-LD-{lr_number}"

    return None


@staticmethod
def _extract_session(text: str) -> Optional[str]:
    """
    Extract legislative session number from text.

    Tries multiple approaches:
    1. Extract from bill ID (if found)
    2. Parse from "Xst/nd/rd/th MAINE LEGISLATURE" line
    3. Extract from bill reference format
    """
    # Approach 1: From bill ID format
    match = re.search(r'(\d{2,3})-LD-\d{4}', text)
    if match:
        return match.group(1)

    # Approach 2: From legislature designation line
    match = re.search(r'(\d{2,3})(?:st|nd|rd|th)\s+MAINE LEGISLATURE', text)
    if match:
        return match.group(1)

    # Approach 3: From bill reference format
    match = re.search(r'(\d{2,3})LR\d{4}', text)
    if match:
        return match.group(1)

    return None


@staticmethod
def _extract_sponsors(text: str) -> List[str]:
    """
    Extract legislator names (sponsors) from text.

    Handles Maine-specific formats:
    - "Presented by Senator/Representative NAME of TOWN"
    - "Cosponsored by Representative/Senator NAME of TOWN"
    - "Representatives: NAME of TOWN, NAME of TOWN"

    Returns list of sponsor names without duplicates.
    """
    sponsors = []

    # Pattern 1: "Presented by Senator/Representative NAME of TOWN"
    pattern1 = r'Presented by\s+(?:Senator|Representative)\s+([A-Z][A-Za-z\'\-]+(?:\s+[A-Z][A-Za-z\'\-]+)*?)\s+of\s+[A-Za-z\s]+[,\n]'
    matches = re.findall(pattern1, text[:2000])
    sponsors.extend([m.strip() for m in matches])

    # Pattern 2: "Cosponsored by Representative/Senator NAME of TOWN"
    pattern2 = r'Cosponsored by\s+(?:Representative|Senator)\s+([A-Z][A-Za-z\'\-]+(?:\s+[A-Z][A-Za-z\'\-]+)*?)\s+of\s+[A-Za-z\s]+[,\n]'
    matches = re.findall(pattern2, text[:2000])
    sponsors.extend([m.strip() for m in matches])

    # Pattern 3: Multi-line sponsors after "Representatives:" or "Senators:"
    # Matches "LASTNAME of TOWN" format after the label
    pattern3 = r'(?:Representatives|Senators):\s+([A-Z][A-Za-z\'\-]+(?:\s+[A-Z][A-Za-z\'\-]+)*?)\s+of\s+[A-Za-z\s]+[,\n]'
    matches = re.findall(pattern3, text[:2000])
    sponsors.extend([m.strip() for m in matches])

    # Pattern 4: Continuation sponsors in cosponsored list
    # Matches "NAME of TOWN" when preceded by commas in sponsor section
    pattern4 = r'(?:and\s+)?(?:Representative|Senator|Rep\.|Sen\.)\s+([A-Z][A-Za-z\'\-]+(?:\s+[A-Z][A-Za-z\'\-]+)*?)\s+of\s+[A-Za-z\s]+[,\n]'
    matches = re.findall(pattern4, text[:2000])
    sponsors.extend([m.strip() for m in matches])

    # Remove duplicates while preserving order
    seen = set()
    unique = []
    for s in sponsors:
        s_normalized = s.strip()
        if s_normalized and s_normalized not in seen:
            unique.append(s_normalized)
            seen.add(s_normalized)

    return unique


@staticmethod
def _extract_date(text: str) -> Optional[date]:
    """
    Extract introduced date from text.

    Handles multiple date formats:
    1. Month name format: "February 16, 2023"
    2. Numeric formats: "02/16/2023" or "2023-02-16"
    3. Context: "In Senate, February 16, 2023"
    """
    # Approach 1: Month name format (e.g., "February 16, 2023")
    # This is the most common format in Maine bills
    month_pattern = r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),\s+(\d{4})'
    match = re.search(month_pattern, text[:2000])
    if match:
        month_str, day_str, year_str = match.groups()
        month_map = {
            'January': 1, 'February': 2, 'March': 3, 'April': 4,
            'May': 5, 'June': 6, 'July': 7, 'August': 8,
            'September': 9, 'October': 10, 'November': 11, 'December': 12
        }
        try:
            return date(int(year_str), month_map[month_str], int(day_str))
        except ValueError:
            pass

    # Approach 2: Numeric MM/DD/YYYY format
    pattern2 = r'(\d{1,2})/(\d{1,2})/(\d{4})'
    match = re.search(pattern2, text[:2000])
    if match:
        m, d, y = match.groups()
        try:
            return date(int(y), int(m), int(d))
        except ValueError:
            pass

    # Approach 3: Numeric YYYY-MM-DD format
    pattern3 = r'(\d{4})-(\d{1,2})-(\d{1,2})'
    match = re.search(pattern3, text[:2000])
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

    Handles Maine-specific formats:
    - "Reference to the Committee on COMMITTEE_NAME suggested and ordered"
    - "Committee on COMMITTEE_NAME"
    - "Referred to COMMITTEE_NAME"

    Returns committee name without trailing action words.
    """
    # Pattern 1: "Reference to the Committee on X suggested and ordered printed"
    match = re.search(r'Reference to the Committee on\s+([A-Za-z\s&]+?)(?:\s+suggested|\s+ordered|\s+and|\n|$)', text[:2000])
    if match:
        committee = match.group(1).strip()
        # Clean up any remaining action words
        committee = re.sub(r'\s+(?:suggested|ordered|and|printed).*$', '', committee)
        return committee.strip()

    # Pattern 2: Standard "Committee on X" format
    match = re.search(r'Committee on\s+([A-Za-z\s&]+?)(?:\n|$)', text[:2000])
    if match:
        committee = match.group(1).strip()
        # Clean up any trailing words
        committee = re.sub(r'\s+(?:suggested|ordered|and|printed).*$', '', committee)
        return committee.strip()

    # Pattern 3: "Referred to X" format
    match = re.search(r'Referred to\s+([A-Za-z\s&]+?)(?:\n|$)', text[:2000])
    if match:
        committee = match.group(1).strip()
        committee = re.sub(r'\s+(?:suggested|ordered|and|printed).*$', '', committee)
        return committee.strip()

    return None


@staticmethod
def _clean_body_text(text: str, metadata: dict) -> str:
    """
    Clean extracted text by removing:
    - Library/copyright boilerplate
    - Line numbers
    - Page headers/footers
    - Bill header metadata lines (No., S.P., etc.)
    - Excessive whitespace

    Returns text starting from bill content (ideally from "Be it enacted" onwards).
    """
    lines = text.split('\n')
    cleaned_lines = []
    in_boilerplate = True

    for line in lines:
        stripped = line.strip()

        # Skip library boilerplate section until we hit actual bill content
        if in_boilerplate:
            # Check for known boilerplate patterns
            if any(pattern in stripped for pattern in [
                'LAW AND LEGISLATIVE DIGITAL LIBRARY',
                'legislature.maine.gov/lawlib',
                'Reproduced from electronic originals',
                'Printed on recycled paper',
                'MAINE STATE LEGISLATURE',
                'The following document is provided by',
                'at the Maine State Law and Legislative Reference Library',
                'may include minor formatting differences',
            ]):
                continue

            # Exit boilerplate section when we hit substantive content
            if any(marker in stripped for marker in [
                'Be it enacted',
                'Sec.',
                'An Act',
                'Legislative Document',
            ]) and stripped:
                in_boilerplate = False
            elif re.match(r'^FIRST REGULAR SESSION|^SECOND REGULAR SESSION|^SPECIAL SESSION', stripped):
                # Skip session headers
                continue
            else:
                # Still in boilerplate, skip unless we found content
                if not any(skip in stripped for skip in ['Legislative Document', 'No.', 'S.P.', 'In Senate', 'In House']):
                    pass
                else:
                    continue

        # Skip bill metadata lines
        if re.match(r'^(?:No\.|S\.P\.|In Senate|In House)\s+', stripped):
            continue

        # Skip line number patterns (just whitespace and number)
        if re.match(r'^\s*\d+\s*$', line):
            continue

        # Skip page headers/footers
        if re.match(r'^Page\s+\d+', stripped, re.IGNORECASE):
            continue

        # Skip bill ID footer patterns like "131LR0290(01)"
        if re.match(r'^\d{2,3}LR\d{4}\(\d{2}\)\s*$', stripped):
            continue

        # Skip legislative reference number patterns
        if re.match(r'^\d{2,3}-LD-\d{4}$', stripped):
            continue

        # Skip common headers
        if re.match(r'^(STATE OF MAINE|MAINE LEGISLATURE)', stripped, re.IGNORECASE):
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


@staticmethod
def _is_line_number(line: str) -> bool:
    """Check if line is just a line number."""
    return bool(re.match(r'^\s+\d+\s*$', line))


@staticmethod
def _is_header_footer(line: str) -> bool:
    """
    Check if line is a header or footer.

    Enhanced to catch more Maine-specific patterns.
    """
    line_stripped = line.strip()

    # Page numbers and pagination
    if re.match(r'^Page\s+\d+', line_stripped, re.IGNORECASE):
        return True

    # Bill IDs and references
    if re.match(r'^\d{2,3}-LD-\d{4}$', line_stripped):
        return True

    # Bill reference format (e.g., "131LR0290(01)")
    if re.match(r'^\d{2,3}LR\d{4}\(\d{2}\)', line_stripped):
        return True

    # Common headers
    if re.match(r'^(STATE OF MAINE|MAINE LEGISLATURE)', line_stripped, re.IGNORECASE):
        return True

    # Legislative document metadata
    if re.match(r'^(?:No\.|S\.P\.)\s+\d+$', line_stripped):
        return True

    # Session headers
    if re.match(r'^\d{2,3}(?:st|nd|rd|th)\s+MAINE LEGISLATURE', line_stripped):
        return True

    return False
