"""Validate extracted sponsor names against known legislator lists.

Optional post-processing step: filters extracted sponsors to only include
names that match known legislators (e.g., from OpenStates).
"""


def validate_sponsors(
    sponsors: list[str],
    known_last_names: set[str] | None,
) -> list[str]:
    """Filter sponsors to only those matching known legislators.

    Args:
        sponsors: Extracted sponsor last names
        known_last_names: Set of known legislator last names (uppercase).
            If None, returns sponsors unfiltered (no-op).

    Returns:
        Filtered list preserving original order and casing.
    """
    if known_last_names is None:
        return sponsors
    return [s for s in sponsors if s.upper() in known_last_names]
