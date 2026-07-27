"""Tests for the bill status backfill (sprint node N3).

All offline: the network is a fake session, and `time.sleep` is patched out so
the rate limit doesn't make the suite slow.
"""

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "backfill_bill_status.py"


@pytest.fixture(scope="module")
def backfill_mod():
    spec = importlib.util.spec_from_file_location("backfill_bill_status", SCRIPT)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load {SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch, backfill_mod):
    monkeypatch.setattr(backfill_mod.time, "sleep", lambda _s: None)


def status_page(session=132, ld="1", paper="SP 29", rows=(("Jan 15, 2025", "Voted", "OTP"),)):
    docket = "".join(f"<tr><td>{d}</td><td>{a}</td><td>{r}</td></tr>" for d, a, r in rows)
    return f"""
    <html><head><title>LD {ld}, {paper}, Text and Status, {session}nd Legislature,
    First Regular Session</title></head><body>
      <h1>{session}nd Maine Legislature</h1><h2>An Act To Do A Thing</h2>
      <div id="flags"></div>
      <div id="sec0">Documents and Disposition</div>
      <div id="sec3">Status In Committee
        <table><tr><td></td></tr>
        <tr><td>Date</td><td>Action</td><td>Result</td></tr>{docket}</table></div>
    </body></html>
    """


class FakeResponse:
    def __init__(self, status_code=200, text=""):
        self.status_code = status_code
        self.text = text


class FakeSession:
    """Serves canned responses by URL; records every request made."""

    def __init__(self, by_url=None, default=None, sequence=None):
        self.by_url = by_url or {}
        self.default = default
        self.sequence = list(sequence or [])
        self.requested: list[str] = []
        self.headers: dict = {}

    def get(self, url, timeout=None):
        self.requested.append(url)
        if self.sequence:
            return self.sequence.pop(0)
        if url in self.by_url:
            return self.by_url[url]
        return self.default or FakeResponse(404, "not found")


@pytest.fixture
def fake_http(backfill_mod, monkeypatch):
    def install(session_obj):
        monkeypatch.setattr(backfill_mod, "http_session", lambda: session_obj)
        return session_obj

    return install


# --- politeness, which is the part with an outside party ---


def test_requests_go_to_the_robots_allowed_path(backfill_mod, fake_http, tmp_path):
    http = fake_http(FakeSession(default=FakeResponse(200, status_page())))
    backfill_mod.backfill(132, ["0001", "0002"], tmp_path / "a.json", delay=0)
    assert all("display_ps.asp" in u for u in http.requested)
    assert not any("default_ps" in u or "LawMakerWeb" in u for u in http.requested)


def test_one_request_per_bill(backfill_mod, fake_http, tmp_path):
    http = fake_http(FakeSession(default=FakeResponse(200, status_page())))
    backfill_mod.backfill(132, ["0001", "0002", "0003"], tmp_path / "a.json", delay=0)
    assert len(http.requested) == 3


def test_urls_are_unpadded_even_though_records_are_padded(backfill_mod, fake_http, tmp_path):
    """The site wants LD=1; the record must key as "0001"."""
    http = fake_http(FakeSession(default=FakeResponse(200, status_page())))
    backfill_mod.backfill(132, ["0001"], tmp_path / "a.json", delay=0)
    assert http.requested == [
        "https://legislature.maine.gov/legis/bills/display_ps.asp?LD=1&snum=132"
    ]
    assert json.loads((tmp_path / "a.json").read_text())[0]["ld_number"] == "0001"


# --- failure handling: one bad bill must not cost the session ---


def test_404_is_recorded_as_no_status_page_and_not_retried(backfill_mod, fake_http, tmp_path):
    http = fake_http(FakeSession(default=FakeResponse(404, "nope")))
    summary = backfill_mod.backfill(132, ["0001"], tmp_path / "a.json", delay=0)
    assert summary["no_status_page"] == 1
    assert summary["failed"] == 0
    assert len(http.requested) == 1, "a 404 will still be a 404; retrying wastes a request"


def test_server_errors_are_retried_then_reported_as_failed(backfill_mod, fake_http, tmp_path):
    http = fake_http(FakeSession(default=FakeResponse(503, "busy")))
    summary = backfill_mod.backfill(132, ["0001"], tmp_path / "a.json", delay=0)
    assert summary["failed"] == 1
    assert len(http.requested) == backfill_mod.MAX_ATTEMPTS


def test_a_transient_error_recovers_on_retry(backfill_mod, fake_http, tmp_path):
    fake_http(FakeSession(sequence=[FakeResponse(503, ""), FakeResponse(200, status_page())]))
    summary = backfill_mod.backfill(132, ["0001"], tmp_path / "a.json", delay=0)
    assert summary["records"] == 1
    assert summary["failed"] == 0


def test_a_200_that_is_not_a_status_page_is_not_recorded(backfill_mod, fake_http, tmp_path):
    """The session/ld overrides mean parse_status_page cannot raise on an error
    page — it already has the identifiers. Without a shape check the run would
    record an all-null row and call it a success."""
    good = FakeResponse(200, status_page())
    fake_http(FakeSession(sequence=[FakeResponse(200, "<html><title>Error</title></html>"), good]))
    summary = backfill_mod.backfill(132, ["0001", "0002"], tmp_path / "a.json", delay=0)
    assert summary["failed"] == 1
    assert summary["records"] == 1
    assert [r["ld_number"] for r in json.loads((tmp_path / "a.json").read_text())] == ["0002"]


def test_a_bill_with_no_docket_is_still_a_valid_record(backfill_mod, fake_http, tmp_path):
    """Empty docket is legitimate — it must not be mistaken for an error page."""
    fake_http(FakeSession(default=FakeResponse(200, status_page(rows=()))))
    summary = backfill_mod.backfill(132, ["0001"], tmp_path / "a.json", delay=0)
    assert summary["records"] == 1
    assert summary["failed"] == 0
    assert json.loads((tmp_path / "a.json").read_text())[0]["action_count"] == 0


# --- resumability, which is what makes a 40-minute job restartable ---


def test_an_existing_output_is_resumed_not_refetched(backfill_mod, fake_http, tmp_path):
    out = tmp_path / "a.json"
    http = fake_http(FakeSession(default=FakeResponse(200, status_page())))
    backfill_mod.backfill(132, ["0001", "0002"], out, delay=0)
    assert len(http.requested) == 2

    http2 = fake_http(FakeSession(default=FakeResponse(200, status_page())))
    summary = backfill_mod.backfill(132, ["0001", "0002", "0003"], out, delay=0)
    assert http2.requested == [
        "https://legislature.maine.gov/legis/bills/display_ps.asp?LD=3&snum=132"
    ]
    assert summary["records"] == 3


def test_a_404_is_persisted_so_a_resumed_run_does_not_ask_again(backfill_mod, fake_http, tmp_path):
    """Without this, every resume re-asks the site for pages known not to exist —
    wasted requests against a state server, which is the whole thing this script
    is careful about."""
    out = tmp_path / "a.json"
    http = fake_http(FakeSession(default=FakeResponse(404, "nope")))
    backfill_mod.backfill(132, ["0001", "0002"], out, delay=0)
    assert len(http.requested) == 2

    http2 = fake_http(FakeSession(default=FakeResponse(404, "nope")))
    summary = backfill_mod.backfill(132, ["0001", "0002"], out, delay=0)
    assert http2.requested == []
    assert summary["no_status_page"] == 2, "the count must survive the resume too"


def test_server_errors_are_not_persisted_and_are_retried_on_resume(
    backfill_mod, fake_http, tmp_path
):
    """A 503 is transient. Retrying it is the main reason to resume at all, so it
    must not be recorded alongside the definitive 404s."""
    out = tmp_path / "a.json"
    fake_http(FakeSession(default=FakeResponse(503, "busy")))
    backfill_mod.backfill(132, ["0001"], out, delay=0)

    http2 = fake_http(FakeSession(default=FakeResponse(200, status_page())))
    summary = backfill_mod.backfill(132, ["0001"], out, delay=0)
    assert len(http2.requested) == 1
    assert summary["records"] == 1


def test_recheck_missing_reopens_the_known_404s(backfill_mod, fake_http, tmp_path):
    """A session still in progress can gain a page after we looked."""
    out = tmp_path / "a.json"
    fake_http(FakeSession(default=FakeResponse(404, "nope")))
    backfill_mod.backfill(132, ["0001"], out, delay=0)

    http2 = fake_http(FakeSession(default=FakeResponse(200, status_page())))
    summary = backfill_mod.backfill(132, ["0001"], out, delay=0, recheck_missing=True)
    assert len(http2.requested) == 1
    assert summary["records"] == 1
    assert summary["no_status_page"] == 0


def test_the_missing_sidecar_does_not_pollute_the_actions_table(backfill_mod, fake_http, tmp_path):
    out = tmp_path / "a.json"
    fake_http(FakeSession(sequence=[FakeResponse(404, ""), FakeResponse(200, status_page())]))
    backfill_mod.backfill(132, ["0001", "0002"], out, delay=0)

    assert [r["ld_number"] for r in json.loads(out.read_text())] == ["0002"]
    assert json.loads((tmp_path / "a-missing.json").read_text()) == ["0001"]


def test_a_corrupt_missing_sidecar_refetches_rather_than_crashing(
    backfill_mod, fake_http, tmp_path
):
    out = tmp_path / "a.json"
    (tmp_path / "a-missing.json").write_text("{ not json")
    http = fake_http(FakeSession(default=FakeResponse(200, status_page())))
    assert backfill_mod.backfill(132, ["0001"], out, delay=0)["records"] == 1
    assert len(http.requested) == 1


def test_a_corrupt_output_file_restarts_rather_than_crashing(backfill_mod, fake_http, tmp_path):
    out = tmp_path / "a.json"
    out.write_text("{ this is not json")
    fake_http(FakeSession(default=FakeResponse(200, status_page())))
    assert backfill_mod.backfill(132, ["0001"], out, delay=0)["records"] == 1


def test_progress_is_checkpointed_mid_run(backfill_mod, fake_http, tmp_path):
    """A crash at bill 900 of 2500 must not discard the first 899."""
    out = tmp_path / "a.json"
    fake_http(FakeSession(default=FakeResponse(200, status_page())))
    backfill_mod.backfill(132, [f"{i:04d}" for i in range(1, 7)], out, delay=0, checkpoint_every=2)
    assert len(json.loads(out.read_text())) == 6


# --- the record shape the actions config will be built from ---


def test_record_carries_the_docket_and_the_join_key(backfill_mod, fake_http, tmp_path):
    rows = (("Jan 15, 2025", "Work Session Held", ""), ("Jan 21, 2025", "Reported Out", "OTP-AM"))
    fake_http(FakeSession(default=FakeResponse(200, status_page(rows=rows))))
    backfill_mod.backfill(132, ["0001"], tmp_path / "a.json", delay=0)

    record = json.loads((tmp_path / "a.json").read_text())[0]
    assert (record["session"], record["ld_number"]) == (132, "0001")
    assert record["action_count"] == 2
    assert record["actions"][1] == {
        "date": "2025-01-21",
        "action": "Reported Out",
        "result": "OTP-AM",
        "raw_date": "Jan 21, 2025",
    }


def test_summary_totals_actions_across_bills(backfill_mod, fake_http, tmp_path):
    rows = (("Jan 15, 2025", "Voted", "OTP"), ("Jan 21, 2025", "Reported Out", "OTP"))
    fake_http(FakeSession(default=FakeResponse(200, status_page(rows=rows))))
    summary = backfill_mod.backfill(132, ["0001", "0002"], tmp_path / "a.json", delay=0)
    assert summary["actions_total"] == 4


def test_limit_caps_the_run_for_a_smoke_test(backfill_mod, fake_http, tmp_path):
    http = fake_http(FakeSession(default=FakeResponse(200, status_page())))
    backfill_mod.backfill(132, ["0001", "0002", "0003"], tmp_path / "a.json", delay=0, limit=2)
    assert len(http.requested) == 2
