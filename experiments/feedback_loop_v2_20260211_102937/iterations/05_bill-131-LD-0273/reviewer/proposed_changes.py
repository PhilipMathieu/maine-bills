"""
Proposed improvements to TextExtractor methods.
Apply these to src/maine_bills/text_extractor.py
"""

from pathlib import Path
from typing import List, Optional
from datetime import date
import re


@staticmethod
def _extract_bill_id(text: str) -> Optional[str]:
    """
    Extract bill ID from text (e.g., '131-LD-0273').

    Improvements:
    - Better handling of "No. XXX" pattern with flexible spacing
    - More robust whitespace normalization for component extraction
    - Improved zero-padding for LD numbers
    """
    # Primary: Try standard format first: "131-LD-1693"
    match = re.search(r'(\d{2,3})-LD-(\d{3,4})', text)
    if match:
        return match.group(0)

    # Fallback: Extract from separate components
    # Normalize whitespace to handle line breaks and multiple spaces
    normalized_text = ' '.join(text.split())

    # Extract session from ordinal format: "131st MAINE LEGISLATURE"
    # Handle flexible spacing around the ordinal indicator
    session_match = re.search(r'(\d{2,3})(?:st|nd|rd|th)\s+(?:MAINE\s+)?LEGISLATURE', normalized_text)

    # Extract LD number from "No. XXX" or "Legislative Document No. XXX"
    # More flexible pattern: allow optional period after No, flexible spacing
    ld_match = re.search(r'(?:Legislative\s+Document|Document)\s+No\.?\s+(\d{3,4})', normalized_text)

    # Fallback LD pattern if above doesn't match: just "No. XXX"
    if not ld_match:
        ld_match = re.search(r'No\.?\s+(\d{3,4})', normalized_text)

    if session_match and ld_match:
        session = session_match.group(1)
        ld_number = ld_match.group(1)
        # Ensure LD number is zero-padded to 4 digits
        ld_number_padded = ld_number.zfill(4)
        return f"{session}-LD-{ld_number_padded}"

    return None


@staticmethod
def _extract_sponsors(text: str) -> List[str]:
    """
    Extract legislator names (sponsors) from text.

    Improvements:
    - Handle names without district information
    - Better cosponsorship block detection
    - Support for multiple name formats (single line and multiline)
    - Handle "and" separators properly
    """
    sponsors = []

    # First 2500 chars contain sponsor info
    search_text = text[:2500]

    # Normalize whitespace to handle line breaks
    normalized_text = ' '.join(search_text.split())

    # Pattern 1: "Presented by Senator/Representative NAME [of DISTRICT]"
    # First try with "of DISTRICT" specification
    pattern1 = r'Presented by\s+(?:Senator|Representative)\s+([A-Z][A-Za-z\'\-]+(?:\s+[A-Z][A-Za-z\'\-]+)?)\s+of\s+[A-Za-z\s]+'
    for match in re.finditer(pattern1, normalized_text):
        name = match.group(1).strip()
        if name and name not in sponsors and len(name.split()) <= 2:
            sponsors.append(name)

    # Pattern 1b: "Presented by Senator/Representative NAME" (without "of" district)
    # More flexible: allow name at end of sentence or before period/comma
    pattern1b = r'Presented by\s+(?:Senator|Representative)\s+([A-Z][A-Za-z\'\-]+(?:\s+[A-Z][A-Za-z\'\-]+)?)\b'
    for match in re.finditer(pattern1b, normalized_text):
        name = match.group(1).strip()
        if name and name not in sponsors and len(name.split()) <= 2:
            sponsors.append(name)

    # Pattern 2: Cosponsored by Representative/Senator NAME
    # Look for the full cosponsorship block (may extend to next major section)
    cosp_block_match = re.search(r'Cosponsored by\s+(.+?)(?=\n\n|Be it enacted|Presented by|$)', normalized_text, re.DOTALL)

    if cosp_block_match:
        cosp_block = cosp_block_match.group(1)

        # Normalize the block
        cosp_normalized = ' '.join(cosp_block.split())

        # Find all individual sponsor patterns within the block
        # Pattern: "Representative/Senator NAME [of DISTRICT]"
        # Handles "and" separator between multiple sponsors
        person_pattern = r'(?:Senator|Representative)\s+([A-Z][A-Za-z\'\-]+(?:\s+[A-Z][A-Za-z\'\-]+)?)\s+of\s+[A-Za-z\s]+(?:\s+and)?'

        for match in re.finditer(person_pattern, cosp_normalized):
            name = match.group(1).strip()
            if name and name not in sponsors and len(name.split()) <= 2:
                sponsors.append(name)

        # Also handle names without "of" district
        # Look for "Representative/Senator NAME" followed by end, comma, or "and"
        person_pattern_no_district = r'(?:Senator|Representative)\s+([A-Z][A-Za-z\'\-]+(?:\s+[A-Z][A-Za-z\'\-]+)?)\b(?:\s+(?:and|of)|,|$)'

        for match in re.finditer(person_pattern_no_district, cosp_normalized):
            name = match.group(1).strip()
            if name and name not in sponsors and len(name.split()) <= 2:
                sponsors.append(name)

        # Handle comma-separated sponsor names within the block
        # Pattern for names like "BRENNAN of Portland, DODGE of Belfast"
        # Extract pairs of names and districts
        comma_separated = re.findall(
            r'([A-Z][A-Za-z\'\-]+(?:\s+[A-Z][A-Za-z\'\-]+)?)\s+of\s+[A-Za-z\s]+',
            cosp_normalized
        )
        for name in comma_separated:
            name = name.strip()
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


@staticmethod
def _extract_session(text: str) -> Optional[str]:
    """
    Extract legislative session number from text.

    Improvements:
    - Better whitespace normalization for multiline matching
    - More robust extraction from ordinal format
    - Fallback patterns for different session formats
    """
    # First try full bill ID format
    match = re.search(r'(\d{2,3})-LD-\d{4}', text)
    if match:
        return match.group(1)

    # Normalize whitespace to handle line breaks
    # Search in first 2000 chars where session typically appears
    search_text = ' '.join(text[:2000].split())

    # Ordinal format: "131st MAINE LEGISLATURE" with flexible spacing
    match = re.search(r'(\d{2,3})(?:st|nd|rd|th)\s+(?:MAINE\s+)?LEGISLATURE', search_text)
    if match:
        return match.group(1)

    # Fallback: Look for just the session number in ordinal format without "LEGISLATURE"
    match = re.search(r'(\d{2,3})(?:st|nd|rd|th)\s+(?:Maine|MAINE)', search_text)
    if match:
        return match.group(1)

    return None


@staticmethod
def _extract_date(text: str) -> Optional[date]:
    """
    Extract introduced date from text.

    Improvements:
    - Proper group index handling for optional prefix patterns
    - Support for "House of Representatives, January 26, 2023" format
    - Better month name parsing with exact group mapping
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

    # Search in first 2500 chars where date typically appears
    search_text = text[:2500]

    # Normalize whitespace to handle line breaks
    normalized_search = ' '.join(search_text.split())

    # Pattern 1: "House/Senate of Representatives, January 26, 2023"
    # This pattern explicitly captures month, day, year without optional groups
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

    # Pattern 2: "In Senate, January 26, 2023" or "In House, January 26, 2023"
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

    # Pattern 3: General written date format (month day, year)
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

    Improvements:
    - More precise boundary detection to exclude trailing markers
    - Better handling of committee names with multiple words
    - Improved pattern to avoid capturing "suggested and ordered"
    """
    # Search in first 2500 chars
    search_text = text[:2500]

    # Normalize whitespace to handle line breaks
    normalized_text = ' '.join(search_text.split())

    # Pattern 1: "Reference to the Committee on COMMITTEE_NAME"
    # Use a more specific boundary: committee name ends before trailing markers
    # Match committee name up to word boundary, then check for marker
    match = re.search(
        r'Reference to the Committee on\s+([A-Za-z\s&,]+?)(?=\s+(?:suggested|ordered|referred|assigned|printed))',
        normalized_text
    )
    if match:
        committee = match.group(1).strip()
        if committee:
            return committee

    # Pattern 2: "Reference to the Committee on COMMITTEE_NAME" with period or line end
    match = re.search(
        r'Reference to the Committee on\s+([A-Za-z\s&,]+?)(?:\.|$)',
        normalized_text
    )
    if match:
        committee = match.group(1).strip()
        # Filter out trailing markers that may have been included
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
