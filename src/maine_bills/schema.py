"""Schema definitions for Maine legislative bill records.

Provides filename parsing and BillRecord dataclass for HuggingFace dataset.
"""

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime

# Filename pattern supporting LD/SP/HP/HO bill types, single and double amendments,
# and both underscore and hyphen separators between double amendment parts.
# where VERSION is A-Z (A=first version, B=second version, etc.)
#
# Examples:
#   - Original: 131-LD-0001
#   - SP bill: 131-SP-0001
#   - Single amendment: 131-LD-0686-CA_A_H0266 (Committee Amendment v.A, House #266)
#   - Single amendment v.B: 131-LD-1621-CA_B_H0319 (Committee Amendment v.B, House #319)
#   - Double amendment (underscore): 132-LD-0004-CA_A_SA_A_S337 (Senate Amend to Committee Amend)
#   - Double amendment (hyphen): 122-LD-0001-CA_A-HA_A_H5 (older sessions 122-129)
#   - Double amendment mixed: 131-LD-0424-CA_A_SA_B_S0014 (Senate Amendment v.B to Committee Amendment v.A)  # noqa: E501
FILENAME_PATTERN = re.compile(
    r"^(?P<session>\d+)-(?P<bill_type>LD|SP|HP|HO)-(?P<number>\d+)"
    r"(?:-(?P<amendment>[A-Z]{2}_[A-Z](?:[-_][A-Z]{2}_[A-Z])?_[HS]\d+))?$"
)

# Document type mapping from bill_type code
DOCUMENT_TYPE_MAP = {
    "LD": "bill",
    "SP": "sp_bill",
    "HP": "hp_bill",
    "HO": "ho_bill",
}

# Amendment type prefixes
AMENDMENT_TYPES = {
    "CA": "Committee Amendment",
    "HA": "House Amendment",
    "SA": "Senate Amendment",
}

# Chamber mapping from amendment code character
CHAMBER_MAP = {
    "H": "House",
    "S": "Senate",
}


def parse_filename(filename: str) -> dict:
    """Parse Maine bill filename into structured metadata.

    Supports LD/SP/HP/HO bill types, single-level and double-level (nested) amendment codes,
    and both underscore and hyphen separators in double amendments (sessions 122-129 use hyphen).

    Args:
        filename: Bill filename without .pdf extension
                  Examples:
                  - "131-LD-0001" (original bill)
                  - "131-SP-0001" (Senate Paper)
                  - "131-LD-0686-CA_A_H0266" (single amendment)
                  - "132-LD-0004-CA_A_SA_A_S337" (double amendment, underscore)
                  - "122-LD-0001-CA_A-HA_A_H5" (double amendment, hyphen, older sessions)

    Returns:
        Dictionary with keys:
        - session: int - Legislative session number
        - ld_number: str - Bill number (zero-padded, e.g., "0001")
        - bill_type: str - Bill type code ("LD", "SP", "HP", "HO")
        - document_type: str - Human-readable type ("bill", "sp_bill", "hp_bill", "ho_bill")
        - amendment_code: str | None - Full amendment suffix or None
        - amendment_type: str | None - Human-readable type from first segment
        - chamber: str | None - "House" or "Senate" from first segment

    Raises:
        ValueError: If filename doesn't match expected pattern

    Examples:
        >>> parse_filename("131-LD-0001")
        {'session': 131, 'ld_number': '0001', 'bill_type': 'LD',
         'document_type': 'bill', 'amendment_code': None,
         'amendment_type': None, 'chamber': None}

        >>> parse_filename("131-LD-0686-CA_A_H0266")
        {'session': 131, 'ld_number': '0686', 'bill_type': 'LD',
         'document_type': 'bill', 'amendment_code': 'CA_A_H0266',
         'amendment_type': 'Committee Amendment', 'chamber': 'House'}

        >>> parse_filename("132-LD-0004-CA_A_SA_A_S337")
        {'session': 132, 'ld_number': '0004', 'bill_type': 'LD',
         'document_type': 'bill', 'amendment_code': 'CA_A_SA_A_S337',
         'amendment_type': 'Committee Amendment', 'chamber': 'Senate'}
    """
    match = FILENAME_PATTERN.match(filename)
    if not match:
        raise ValueError(f"Unexpected filename format: {filename}")

    # Extract basic components
    session = int(match.group("session"))
    bill_type = match.group("bill_type")
    ld_number = match.group("number")
    amendment = match.group("amendment")

    # Parse amendment metadata from first segment only
    amendment_type = None
    chamber = None

    if amendment:
        # For double amendments like "CA_A_SA_A_S337", we parse the first segment "CA"
        # to determine the primary amendment type and extract chamber from the code
        parts = amendment.split("_")
        prefix = parts[0]  # e.g., "CA", "HA", "SA"
        amendment_type = AMENDMENT_TYPES.get(prefix, prefix)

        # Extract chamber from the first occurrence of H or S followed by digits
        # This handles both single ("CA_A_H0266") and double ("CA_A_SA_A_S337") amendments
        chamber_match = re.search(r"[HS]\d+", amendment)
        if chamber_match:
            chamber_char = chamber_match.group()[0]
            chamber = CHAMBER_MAP.get(chamber_char)

    return {
        "session": session,
        "ld_number": ld_number,
        "bill_type": bill_type,
        "document_type": DOCUMENT_TYPE_MAP[bill_type],
        "amendment_code": amendment,
        "amendment_type": amendment_type,
        "chamber": chamber,
    }


@dataclass
class BillRecord:
    """Complete bill record combining filename and content metadata.

    Merges filename-based metadata (always present) with content-based metadata
    (extracted from bill text, may be None/empty).
    """

    # Filename-based metadata (always present)
    session: int
    ld_number: str
    document_type: str
    amendment_code: str | None
    amendment_type: str | None
    chamber: str | None

    # Core content
    text: str
    extraction_confidence: float

    # Content-based metadata (optional, from text extraction)
    title: str | None = None
    sponsors: list[str] = field(default_factory=list)
    committee: str | None = None
    amended_code_refs: list[str] = field(default_factory=list)

    # Provenance
    source_url: str = ""
    source_filename: str = ""
    scraped_at: str = ""

    @classmethod
    def from_filename_and_bill_document(
        cls, filename: str, bill_doc, base_url: str
    ) -> "BillRecord":
        """Create BillRecord by parsing filename and merging with BillDocument.

        Args:
            filename: Bill filename without .pdf extension (e.g., "131-LD-0686-CA_A_H0266")
            bill_doc: BillDocument from text extraction
            base_url: Base URL for constructing source_url

        Returns:
            BillRecord with both filename and content metadata

        Raises:
            ValueError: If filename doesn't match expected pattern
        """
        # Parse filename for structural metadata
        parsed = parse_filename(filename)

        # Combine with content-based metadata from BillDocument
        return cls(
            # Filename-based
            session=parsed["session"],
            ld_number=parsed["ld_number"],
            document_type=parsed["document_type"],
            amendment_code=parsed["amendment_code"],
            amendment_type=parsed["amendment_type"],
            chamber=parsed["chamber"],
            # Content
            text=bill_doc.body_text,
            extraction_confidence=bill_doc.extraction_confidence,
            # Content-based metadata
            title=bill_doc.title,
            sponsors=bill_doc.sponsors,
            committee=bill_doc.committee,
            amended_code_refs=bill_doc.amended_code_refs,
            # Provenance
            source_url=f"{base_url}{filename}.pdf",
            source_filename=filename,
            scraped_at=datetime.now(UTC).isoformat(),
        )
