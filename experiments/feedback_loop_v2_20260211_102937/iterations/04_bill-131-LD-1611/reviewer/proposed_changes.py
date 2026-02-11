"""
Proposed improvements to TextExtractor for Bill 131-LD-1611.
Apply these to src/maine_bills/text_extractor.py
"""

from pathlib import Path
from typing import List, Optional
from datetime import date
import re


@staticmethod
def _extract_bill_id(text: str) -> Optional[str]:
    """
    Extract bill ID from text (e.g., '131-LD-1611').

    Improvements:
    - Ensure fallback component extraction is always attempted
    - Better handling of non-zero-padded LD numbers (1611 instead of 0001)
    - More robust session extraction from ordinal format
    """
    # Primary: Try standard format first: "131-LD-1693"
    match = re.search(r'(\d{2,3})-LD-(\d{3,4})', text)
    if match:
        return match.group(0)

    # Fallback: Extract from separate components
    # Normalize whitespace to handle line breaks and multiple spaces
    normalized_text = ' '.join(text.split())

    # Extract session from ordinal format: "131st MAINE LEGISLATURE"
    # More flexible: allow for extra whitespace, optional "MAINE", and variations
    session_match = re.search(r'(\d{2,3})(?:st|nd|rd|th)\s+(?:MAINE\s+)?LEGISLATURE', normalized_text)

    # Extract LD number from "No. 1611" or "Legislative Document 1611"
    # This regex captures 3 or 4 digit LD numbers without requiring zero-padding
    ld_match = re.search(r'(?:Legislative Document|Document No\.?|No\.?)\s+(\d{3,4})', normalized_text)

    if session_match and ld_match:
        session = session_match.group(1)
        ld_number = ld_match.group(1)
        # Zero-pad LD number to 4 digits for consistency
        ld_number_padded = ld_number.zfill(4)
        return f"{session}-LD-{ld_number_padded}"

    return None


@staticmethod
def _extract_session(text: str) -> Optional[str]:
    """
    Extract legislative session number from text.

    Improvements:
    - More robust whitespace handling in ordinal format
    - Better search scope targeting the first section where session appears
    - Explicit fallback if combined bill ID not found
    """
    # First try full bill ID format: "131-LD-1693"
    match = re.search(r'(\d{2,3})-LD-\d{3,4}', text)
    if match:
        return match.group(1)

    # Search in first 1500 chars where session number typically appears
    # The session appears near the document header
    search_text = ' '.join(text[:1500].split())

    # Ordinal format: "131st MAINE LEGISLATURE" or "131ST MAINE LEGISLATURE"
    # Allow for optional "MAINE" and flexible spacing
    match = re.search(r'(\d{2,3})(?:st|nd|rd|th)\s+(?:MAINE\s+)?LEGISLATURE', search_text, re.IGNORECASE)
    if match:
        return match.group(1)

    # Fallback: look for session in broader context
    # Sometimes session appears as "131st" followed by "SPECIAL SESSION" or "REGULAR SESSION"
    match = re.search(r'(\d{2,3})(?:st|nd|rd|th)(?:\s+SPECIAL|\s+REGULAR)?\s+(?:SESSION|LEGISLATURE)', search_text, re.IGNORECASE)
    if match:
        return match.group(1)

    return None


@staticmethod
def _extract_date(text: str) -> Optional[date]:
    """
    Extract introduced date from text.

    Improvements:
    - Handle dates after "House of Representatives," or "Senate,"
    - More flexible context matching for date detection
    - Support for common date formats in Maine bills
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
        # Context-aware patterns for chamber presentation
        # Pattern: "House of Representatives, April 11, 2023" or "In Senate, April 18, 2023"
        (r'(?:House of Representatives|Senate|In (?:Senate|House)|In House),?\s+(January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2}),?\s+(\d{4})', 'written'),
        # Written month format without chamber context: "February 21, 2023"
        (r'(January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2}),?\s+(\d{4})', 'written'),
        # MM/DD/YYYY format
        (r'(\d{1,2})/(\d{1,2})/(\d{4})', 'slash'),
        # YYYY-MM-DD format
        (r'(\d{4})-(\d{1,2})-(\d{1,2})', 'dash'),
    ]

    # Search in first 3000 chars where date typically appears
    search_text = text[:3000]

    # Normalize whitespace to handle line breaks
    normalized_search = ' '.join(search_text.split())

    for pattern, fmt in patterns:
        match = re.search(pattern, normalized_search)
        if match:
            try:
                if fmt == 'written':
                    # Group indices: month is always group 1, day is group 2, year is group 3
                    month_name = match.group(1)
                    day = match.group(2)
                    year = match.group(3)

                    month = months.get(month_name)
                    if month:
                        return date(int(year), month, int(day))
                elif fmt == 'slash':
                    m, d, y = match.groups()
                    return date(int(y), int(m), int(d))
                else:  # fmt == 'dash'
                    y, m, d = match.groups()
                    return date(int(y), int(m), int(d))
            except (ValueError, TypeError):
                continue

    return None


@staticmethod
def _extract_amended_codes(text: str) -> List[str]:
    """
    Extract Maine state code references being amended.

    Improvements:
    - Add support for MRSA references (Maine Revised Statutes Annotated)
    - Capture patterns like "35-A MRSA §4002" and "5 MRSA §12004-G"
    - Support both "Title X" and "MRSA" reference styles
    - Deduplicate while preserving order
    """
    refs = []

    # Pattern 1: Traditional Title format "Title 20, Section 1" or "Title 20-A, § 101"
    title_pattern = r'Title\s+(\d+(?:-[A-Z])?),\s*(?:Section|§)\s+(\d+)'
    for match in re.finditer(title_pattern, text):
        ref = f"Title {match.group(1)}, Section {match.group(2)}"
        if ref not in refs:
            refs.append(ref)

    # Pattern 2: MRSA format "35-A MRSA §4002" or "5 MRSA §12004-G"
    # Captures: Title number (with optional letter suffix), section with optional letter suffix
    mrsa_pattern = r'(\d+(?:-[A-Z])?)\s+MRSA\s+§(\d+(?:-[A-Z])?)'
    for match in re.finditer(mrsa_pattern, text):
        title = match.group(1)
        section = match.group(2)
        ref = f"{title} MRSA §{section}"
        if ref not in refs:
            refs.append(ref)

    # Pattern 3: Alternative MRSA format without special character: "21-A MRSA section 354"
    mrsa_alt_pattern = r'(\d+(?:-[A-Z])?)\s+MRSA\s+(?:section|Section)\s+(\d+(?:-[A-Z])?)'
    for match in re.finditer(mrsa_alt_pattern, text):
        title = match.group(1)
        section = match.group(2)
        ref = f"{title} MRSA section {section}"
        # Only add if not already captured in MRSA format
        if ref not in refs and f"{title} MRSA §{section}" not in refs:
            refs.append(ref)

    return refs


@staticmethod
def _is_bill_initiated(text: str) -> bool:
    """
    Detect if a bill is an initiated bill (I.B. number).

    Initiated bills are citizen-initiated and have no legislator sponsors.

    Returns:
        True if bill contains "I.B." or "Initiated Bill" indicator
    """
    # Look for "I.B. X" pattern in first 2000 chars
    search_text = ' '.join(text[:2000].split())

    # Pattern: "I.B. 2" or "I.B. 1"
    if re.search(r'I\.B\.\s+\d+', search_text, re.IGNORECASE):
        return True

    # Pattern: "Initiated Bill" in document header
    if re.search(r'Initiated Bill', search_text, re.IGNORECASE):
        return True

    return False


@staticmethod
def _extract_sponsors(text: str) -> List[str]:
    """
    Extract legislator names (sponsors) from text.

    Improvements:
    - Better handling of initiated bills (which have no sponsors)
    - Clearer distinction between failed extraction and initiated bills
    - More robust multi-line cosponsorship parsing
    """
    sponsors = []

    # First 2500 chars contain sponsor info
    search_text = text[:2500]

    # Normalize whitespace but preserve some structure
    normalized_text = ' '.join(search_text.split())

    # Pattern 1: "Presented by Senator/Representative NAME [of DISTRICT]"
    pattern1 = r'Presented by\s+(?:Senator|Representative)\s+([A-Z][A-Za-z\'\-]+(?:\s+[A-Z][A-Za-z\'\-]+)?)\s+of\s+[A-Za-z\s]+'
    for match in re.finditer(pattern1, normalized_text):
        name = match.group(1).strip()
        if name and name not in sponsors and len(name.split()) <= 2:
            sponsors.append(name)

    # Pattern 1b: "Presented by Senator/Representative NAME" (without "of" district)
    pattern1b = r'Presented by\s+(?:Senator|Representative)\s+([A-Z][A-Za-z\'\-]+(?:\s+[A-Z][A-Za-z\'\-]+)?)\s*\.?(?:\s+of\s+[A-Za-z\s]+)?(?:\s+|$)'
    for match in re.finditer(pattern1b, normalized_text):
        name = match.group(1).strip()
        if name and name not in sponsors and len(name.split()) <= 2:
            sponsors.append(name)

    # Pattern 2: "Cosponsored by Representative/Senator NAME" with "and" separator
    cosp_block_match = re.search(r'Cosponsored by\s+(.+?)(?=\n\n|Be it enacted|$)', normalized_text, re.DOTALL)

    if cosp_block_match:
        cosp_block = cosp_block_match.group(1)
        cosp_normalized = ' '.join(cosp_block.split())

        # Find all individual sponsor patterns within the block
        person_pattern = r'(?:Senator|Representative)\s+([A-Z][A-Za-z\'\-]+(?:\s+[A-Z][A-Za-z\'\-]+)?)\s+of\s+[A-Za-z\s]+(?:\s+and)?'

        for match in re.finditer(person_pattern, cosp_normalized):
            name = match.group(1).strip()
            if name and name not in sponsors and len(name.split()) <= 2:
                sponsors.append(name)

        # Also handle names without "of" district
        person_pattern_no_district = r'(?:Senator|Representative|Rep\.?)\s*[:]*\s*([A-Z][A-Za-z\'\-]+(?:\s+[A-Z][A-Za-z\'\-]+)?)\s+(?:of|and|$)'

        for match in re.finditer(person_pattern_no_district, cosp_normalized):
            name = match.group(1).strip()
            if name and name not in sponsors and len(name.split()) <= 2:
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
