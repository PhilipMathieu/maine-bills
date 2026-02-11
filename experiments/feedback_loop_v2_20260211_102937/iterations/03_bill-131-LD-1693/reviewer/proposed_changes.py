"""
Proposed improvements to TextExtractor.
Apply these to src/maine_bills/text_extractor.py
"""

from pathlib import Path
from typing import List, Optional
from datetime import date
import re


@staticmethod
def _extract_bill_id(text: str) -> Optional[str]:
    """
    Extract bill ID from text (e.g., '131-LD-1693').

    Improved to:
    - Handle ordinal session format (131st, 132nd, etc.)
    - Extract LD numbers from "No." pattern
    - Better fallback when bill ID isn't in combined format
    - Properly zero-pad LD numbers
    """
    # Primary: Try standard format first: "131-LD-1693"
    match = re.search(r'(\d{2,3})-LD-(\d{3,4})', text)
    if match:
        return match.group(0)

    # Fallback: Extract from separate components
    # Normalize whitespace to handle line breaks and multiple spaces
    normalized_text = ' '.join(text.split())

    # Extract session from ordinal format: "131st MAINE LEGISLATURE" or variations
    # More flexible to handle different spacing
    session_match = re.search(r'(\d{2,3})(?:st|nd|rd|th)\s+(?:MAINE\s+)?LEGISLATURE', normalized_text)

    # Extract LD number from "No. XXXX" or "Document No. XXXX"
    # Handle both "No." and "No" (with optional period)
    ld_match = re.search(r'(?:Legislative Document|Document No\.?|No\.?)\s+(\d{3,4})', normalized_text)

    if session_match and ld_match:
        session = session_match.group(1)
        ld_number = ld_match.group(1)
        # Ensure LD number is zero-padded to 4 digits
        ld_number_padded = ld_number.zfill(4)
        return f"{session}-LD-{ld_number_padded}"

    return None


@staticmethod
def _extract_session(text: str) -> Optional[str]:
    """
    Extract legislative session number from text.

    Improved to:
    - Handle whitespace normalization for multi-line matching
    - Robustly extract from ordinal format (131st, 132nd, etc.)
    - Fallback to full bill ID format if available
    """
    # First try full bill ID format
    match = re.search(r'(\d{2,3})-LD-\d{4}', text)
    if match:
        return match.group(1)

    # Normalize whitespace to handle line breaks
    # The session number typically appears near the start in "131st MAINE LEGISLATURE"
    # which may have line breaks or extra spaces
    search_text = ' '.join(text[:1000].split())

    # Ordinal format: "131st MAINE LEGISLATURE" with flexible spacing
    match = re.search(r'(\d{2,3})(?:st|nd|rd|th)\s+(?:MAINE\s+)?LEGISLATURE', search_text)
    if match:
        return match.group(1)

    return None


@staticmethod
def _extract_sponsors(text: str) -> List[str]:
    """
    Extract legislator names (sponsors) from text.

    Improved to:
    - Handle multi-line cosponsorship blocks
    - Parse "and" separators between multiple sponsors
    - Normalize whitespace to handle line breaks
    - Better extraction of names in different formats
    - Handle "Representative:" with colon
    """
    sponsors = []

    # First 2500 chars contain sponsor info
    search_text = text[:2500]

    # Normalize whitespace but preserve some structure
    # Replace line breaks within sponsor block with spaces for easier parsing
    normalized_text = ' '.join(search_text.split())

    # Pattern 1: "Presented by Senator/Representative NAME [of DISTRICT]"
    # Captures just the name part (before "of")
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
    # Handles multiple sponsors separated by "and"
    # Look for the full cosponsorship block
    cosp_block_match = re.search(r'Cosponsored by\s+(.+?)(?=\n\n|Be it enacted|$)', normalized_text, re.DOTALL)

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

        # Also handle names without "of" district (in case format varies)
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


@staticmethod
def _extract_committee(text: str) -> Optional[str]:
    """
    Extract assigned committee from text.

    Improved to:
    - Normalize whitespace to handle multi-line patterns
    - Better handling of trailing markers
    - More flexible punctuation handling
    """
    # Search in first 2500 chars (increased from 2000)
    search_text = text[:2500]

    # Normalize whitespace to handle line breaks while preserving content
    normalized_text = ' '.join(search_text.split())

    # Pattern: "Reference to the Committee on COMMITTEE_NAME"
    # Handles trailing text like "suggested and ordered printed"
    match = re.search(
        r'Reference to the Committee on\s+([A-Za-z\s&]+?)(?:\s+(?:suggested|ordered|referred|assigned)|,|$)',
        normalized_text
    )
    if match:
        committee = match.group(1).strip()
        if committee:
            return committee

    # Alternative pattern: "Assigned to/Referred to Committee on COMMITTEE_NAME"
    match = re.search(
        r'(?:Committee on|Referred to|Assigned to)\s+([A-Za-z\s&]+?)(?:\s+(?:suggested|ordered|referred|assigned)|,|$)',
        normalized_text
    )
    if match:
        committee = match.group(1).strip()
        if committee:
            return committee

    return None


@staticmethod
def _extract_date(text: str) -> Optional[date]:
    """
    Extract introduced date from text.

    Improved to:
    - Handle dates in context like "In Senate, April 18, 2023"
    - Normalize whitespace for better pattern matching
    - More robust month name parsing
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
        # Prioritize dates that appear after "In Senate," or "In House,"
        (r'(?:In (?:Senate|House),?\s+)?(January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2}),?\s+(\d{4})', 'written'),
        # MM/DD/YYYY
        (r'(\d{1,2})/(\d{1,2})/(\d{4})', 'slash'),
        # YYYY-MM-DD
        (r'(\d{4})-(\d{1,2})-(\d{1,2})', 'dash'),
    ]

    # Search in first 2500 chars where date typically appears
    search_text = text[:2500]

    # Normalize whitespace to handle line breaks
    normalized_search = ' '.join(search_text.split())

    for pattern, fmt in patterns:
        match = re.search(pattern, normalized_search)
        if match:
            try:
                if fmt == 'written':
                    # Group indices may shift based on optional prefix
                    groups = match.groups()
                    if len(groups) == 3:
                        month_name, day, year = groups
                    else:
                        # If optional group wasn't captured, adjust
                        month_name = groups[0]
                        day = groups[1]
                        year = groups[2]

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
