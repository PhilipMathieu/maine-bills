import re
from dataclasses import dataclass, field
from datetime import UTC, datetime

AMENDMENT_TYPES = {
    "CA": "Committee Amendment",
    "HA": "House Amendment",
    "SA": "Senate Amendment",
}

CHAMBER_MAP = {"H": "House", "S": "Senate"}

FILENAME_PATTERN = re.compile(
    r"^(?P<session>\d+)-LD-(?P<ld>\d+)(?:-(?P<amendment>[A-Z]{2}_[A-Z]_[HS]\d+))?$"
)


def parse_filename(filename: str) -> dict:
    """Parse a bill filename stem into its structural components.

    Args:
        filename: Filename without .pdf extension, e.g. "131-LD-0686-CA_A_H0266"

    Returns:
        Dict with keys: session, ld_number, amendment_code, amendment_type, chamber

    Raises:
        ValueError: If filename doesn't match expected pattern
    """
    match = FILENAME_PATTERN.match(filename)
    if not match:
        raise ValueError(f"Unexpected filename format: {filename!r}")

    amendment = match.group("amendment")
    amendment_type = None
    chamber = None
    if amendment:
        prefix = amendment.split("_")[0]
        amendment_type = AMENDMENT_TYPES.get(prefix, prefix)
        chamber_char = amendment.split("_")[2][0]
        chamber = CHAMBER_MAP.get(chamber_char)

    return {
        "session": int(match.group("session")),
        "ld_number": match.group("ld"),
        "amendment_code": amendment,
        "amendment_type": amendment_type,
        "chamber": chamber,
    }


@dataclass
class BillRecord:
    """Complete bill record combining filename metadata and extracted content."""

    # Filename-based (always present)
    session: int
    ld_number: str
    document_type: str
    amendment_code: str | None
    amendment_type: str | None
    chamber: str | None

    # Core content
    text: str
    extraction_confidence: float

    # Content-based (optional, from text extraction)
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
        cls, filename: str, bill_doc: object, base_url: str
    ) -> "BillRecord":
        """Create a BillRecord by combining filename parsing with a BillDocument.

        Args:
            filename: Bill filename without .pdf extension
            bill_doc: BillDocument from TextExtractor
            base_url: Session base URL for constructing source_url

        Raises:
            ValueError: If filename doesn't match expected pattern
        """
        parts = parse_filename(filename)
        return cls(
            session=parts["session"],
            ld_number=parts["ld_number"],
            document_type="bill",
            amendment_code=parts["amendment_code"],
            amendment_type=parts["amendment_type"],
            chamber=parts["chamber"],
            text=bill_doc.body_text,
            extraction_confidence=bill_doc.extraction_confidence,
            title=bill_doc.title,
            sponsors=bill_doc.sponsors,
            committee=bill_doc.committee,
            amended_code_refs=bill_doc.amended_code_refs,
            source_url=f"{base_url}{filename}.pdf",
            source_filename=filename,
            scraped_at=datetime.now(UTC).isoformat(),
        )
