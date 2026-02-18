"""Tests for sponsor validation against known legislator lists."""
from maine_bills.sponsor_validation import validate_sponsors


def test_valid_sponsors_kept():
    known = {"SMITH", "JONES", "BROWN"}
    result = validate_sponsors(["SMITH", "JONES"], known)
    assert result == ["SMITH", "JONES"]


def test_garbage_removed():
    known = {"SMITH", "JONES"}
    result = validate_sponsors(["SMITH", "Town", "University"], known)
    assert result == ["SMITH"]


def test_empty_known_returns_all():
    """If no known legislators provided, return all (no-op)."""
    result = validate_sponsors(["SMITH", "Town"], known_last_names=None)
    assert result == ["SMITH", "Town"]


def test_case_insensitive():
    known = {"SMITH", "TALBOT-ROSS"}
    result = validate_sponsors(["Smith", "TALBOT-ROSS"], known)
    assert result == ["Smith", "TALBOT-ROSS"]


def test_ambiguous_kept():
    """Ambiguous names (multiple legislators) are still valid."""
    known = {"LIBBY", "WHITE"}
    result = validate_sponsors(["LIBBY", "WHITE", "Garbage"], known)
    assert result == ["LIBBY", "WHITE"]
