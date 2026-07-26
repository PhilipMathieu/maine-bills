"""Tests for bill status page parsing (sprint track A1).

Fixtures mirror the real structure of ``display_ps.asp`` as captured on the
``fixtures/recon`` branch — the empty leading row in both tables, the ``<h1>``
session line, the ``#legis_field_head`` picker, and the ``#sec*`` containers —
because two of the parser's bugs came from assuming otherwise.
"""

import pytest
from bs4 import BeautifulSoup

from maine_bills.bill_status import (
    BillAction,
    parse_actions,
    parse_date,
    parse_status_page,
    status_url,
)


def page(
    *,
    session="132nd",
    session_name="First Special Session",
    ld="1",
    paper="SP 29",
    title="An Act to Increase Storm Preparedness",
    flags="(EMERGENCY) (GOVERNOR'S BILL)",
    sec0="",
    sec3="",
    docket_rows=(),
    include_statutes=True,
):
    """Build a page with the real page's structure."""
    rows = "".join(f"<tr><td>{d}</td><td>{a}</td><td>{r}</td></tr>" for d, a, r in docket_rows)
    docket = (
        # The real table opens with an EMPTY row; the header is row 1.
        "<table><tr><td></td></tr>"
        "<tr><td>Date</td><td>Action</td><td>Result</td></tr>"
        f"{rows}</table>"
        if docket_rows
        else ""
    )
    statutes = (
        "<table><tr><td>Affected Statute Titles and Sections</td></tr>"
        "<tr><td>Title</td><td>Section</td><td>Subsection</td><td>Paragraph</td>"
        "<td>Effect</td><td>Law Type</td><td>Chapter</td></tr>"
        "<tr><td>5</td><td>3109</td><td>2</td><td></td><td>AMD</td>"
        "<td>Public Law</td><td>33</td></tr></table>"
        if include_statutes
        else ""
    )
    return f"""
    <html><head><title>LD {ld}, {paper}, Text and Status, {session} Legislature,
    {session_name}</title></head><body>
      <h1>{session} Maine Legislature, {session_name}</h1>
      <div id="legis_field_head">Legislature 132nd 131st 130th 129th 128th 127th
        126th 125th 124th 123rd 122nd 121st 120th</div>
      <h3>Choose Another Bill</h3>
      <h2>{title}</h2>
      <div id="paper_box"></div><div id="ld_box"></div>
      <div id="flags">{flags}</div>
      <div id="sec0">Documents and Disposition LD {ld}, {paper} {sec0}</div>
      <div id="sec3">Status In Committee {sec3}{docket}</div>
      <div id="sec6">{statutes}</div>
    </body></html>
    """


# --- status_url ---


def test_status_url_uses_the_robots_allowed_path():
    url = status_url(132, 1)
    assert url == "https://legislature.maine.gov/legis/bills/display_ps.asp?LD=1&snum=132"
    # robots.txt disallows default_ps.asp, search_ps.asp and /LawMakerWeb
    assert "default_ps" not in url and "LawMakerWeb" not in url


def test_status_url_accepts_a_string_ld():
    assert status_url(121, "0001").endswith("LD=1&snum=121")


# --- parse_date ---


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Jan 15, 2025", "2025-01-15"),
        ("Mar 6, 2025", "2025-03-06"),
        ("Dec 31, 2003", "2003-12-31"),
        ("", None),
        (None, None),
        ("not a date", None),
        ("15 January 2025", None),
    ],
)
def test_parse_date(raw, expected):
    assert parse_date(raw) == expected


# --- the docket header is not row 0 ---


def test_docket_header_is_found_below_an_empty_leading_row():
    """Regression: assuming row 0 was the header returned zero actions."""
    html = page(docket_rows=[("Jan 15, 2025", "Voted", "REFERRED")])
    actions = parse_actions(BeautifulSoup(html, "html.parser"))
    assert actions == [
        BillAction(date="2025-01-15", action="Voted", result="REFERRED", raw_date="Jan 15, 2025")
    ]


def test_affected_statutes_table_is_not_mistaken_for_the_docket():
    """Both tables exist; a positional index would pick the wrong one."""
    html = page(docket_rows=[], include_statutes=True)
    assert parse_actions(BeautifulSoup(html, "html.parser")) == []


def test_blank_result_becomes_none_not_empty_string():
    html = page(docket_rows=[("Jan 15, 2025", "Work Session Held", "")])
    assert parse_actions(BeautifulSoup(html, "html.parser"))[0].result is None


def test_unparseable_date_keeps_the_row_and_the_raw_text():
    """One bad cell must not discard a bill's history."""
    html = page(docket_rows=[("Indeterminate", "Voted", "ONTP")])
    action = parse_actions(BeautifulSoup(html, "html.parser"))[0]
    assert action.date is None
    assert action.raw_date == "Indeterminate"
    assert action.action == "Voted"


def test_rows_without_an_action_are_skipped():
    html = page(docket_rows=[("Jan 15, 2025", "", ""), ("Jan 16, 2025", "Voted", "OTP")])
    actions = parse_actions(BeautifulSoup(html, "html.parser"))
    assert [a.action for a in actions] == ["Voted"]


# --- the title is the h2 ---


def test_title_is_the_bill_not_the_legislature_picker():
    """Regression: #legis_field_head is the picker, and yields a list of
    legislatures rather than the bill's title."""
    status = parse_status_page(page(title="An Act to Do a Specific Thing"))
    assert status.title == "An Act to Do a Specific Thing"
    assert "131st" not in (status.title or "")


def test_title_falls_back_when_there_is_no_h2():
    html = page().replace("<h2>", "<h4>").replace("</h2>", "</h4>")
    assert parse_status_page(html).title == "An Act to Increase Storm Preparedness"


# --- identifiers ---


def test_identifiers_come_from_the_title_since_the_boxes_are_script_filled():
    status = parse_status_page(page(ld="1", paper="SP 29", session="132nd"))
    assert (status.session, status.ld_number, status.paper) == (132, "1", "SP 29")


def test_overrides_win_over_the_page_title():
    status = parse_status_page(page(), session=131, ld="0042")
    assert status.session == 131
    assert status.ld_number == "0042"


def test_unrecognisable_page_raises_rather_than_guessing():
    with pytest.raises(ValueError, match="Could not determine session/LD"):
        parse_status_page("<html><head><title>Error</title></head><body/></html>")


def test_flags_are_split():
    assert parse_status_page(page()).flags == ["EMERGENCY", "GOVERNOR'S BILL"]


def test_no_flags_is_an_empty_list():
    assert parse_status_page(page(flags="")).flags == []


# --- prose fields ---


def test_committee_referral():
    status = parse_status_page(
        page(sec3="Referred to Committee on Housing and Economic Development on Jan 28, 2025.")
    )
    assert status.committee == "Housing and Economic Development"
    assert status.referred_date == "2025-01-28"


def test_final_disposition_and_governor_action():
    status = parse_status_page(
        page(
            sec0="Final Disposition Emergency Enacted, Apr 22, 2025 "
            "Governor's Action: Emergency Signed, Apr 22, 2025 "
            "Chaptered Law ACTPUB , Chapter 33"
        )
    )
    assert status.final_disposition == "Emergency Enacted"
    assert status.final_disposition_date == "2025-04-22"
    assert status.governor_action == "Emergency Signed"
    assert status.chaptered_law == "ACTPUB Chapter 33"


def test_a_bill_that_died_has_a_disposition_and_no_chapter():
    status = parse_status_page(
        page(sec0="Final Disposition Ought Not to Pass Pursuant To Joint Rule 310, Mar 20, 2003")
    )
    assert status.final_disposition == "Ought Not to Pass Pursuant To Joint Rule 310"
    assert status.chaptered_law is None
    assert status.governor_action is None


# --- the two eras parse identically ---


def test_session_121_and_132_take_the_same_path():
    """Recon established the page renders identically across eras; if that ever
    stops being true, this is where it shows up."""
    old = parse_status_page(
        page(
            session="121st",
            session_name="First Regular Session",
            paper="HP 8",
            title="An Act to Increase the Property Tax Exemption for Veterans",
            flags="",
            sec3="Referred to Committee on Taxation on Jan 9, 2003.",
            sec0="Final Disposition Ought Not to Pass Pursuant To Joint Rule 310, Mar 20, 2003",
            docket_rows=[
                ("Mar 13, 2003", "Work Session Held", ""),
                ("Mar 13, 2003", "Voted", "ONTP"),
                ("Mar 17, 2003", "Reported Out", "ONTP"),
            ],
        )
    )
    new = parse_status_page(
        page(
            sec3="Referred to Committee on Housing and Economic Development on Jan 28, 2025.",
            docket_rows=[("Jan 15, 2025", "Voted", "REFERRED")],
        )
    )

    assert old.session == 121 and new.session == 132
    assert old.committee == "Taxation" and new.committee == "Housing and Economic Development"
    assert [a.result for a in old.actions] == [None, "ONTP", "ONTP"]
    assert len(new.actions) == 1
