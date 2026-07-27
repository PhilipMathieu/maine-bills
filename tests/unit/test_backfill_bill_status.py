"""Tests for the bill status backfill (sprint node N3).

All offline: the network is a fake session, and `time.sleep` is patched out so
the rate limit doesn't make the suite slow.
"""

import importlib.util
import json
import os
import subprocess
import sys
import time
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
def sleeps(monkeypatch, backfill_mod):
    """Record sleeps instead of taking them.

    A `lambda _s: None` that recorded nothing left the rate limit untested:
    deleting `time.sleep(delay)` from the request loop entirely kept the whole
    suite green. Politeness is the one behaviour here with an outside party, so
    it gets asserted.
    """
    taken: list[float] = []
    monkeypatch.setattr(backfill_mod.time, "sleep", taken.append)
    return taken


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


def test_every_request_is_followed_by_the_configured_delay(
    backfill_mod, fake_http, sleeps, tmp_path
):
    """The 1 req/sec is the design, per the module docstring and the workflow
    comment. Deleting it must not be invisible."""
    fake_http(FakeSession(default=FakeResponse(200, status_page())))
    backfill_mod.backfill(132, ["0001", "0002", "0003"], tmp_path / "a.json", delay=1.0)
    assert sleeps == [1.0, 1.0, 1.0]


def test_the_delay_is_honored_at_other_rates(backfill_mod, fake_http, sleeps, tmp_path):
    fake_http(FakeSession(default=FakeResponse(200, status_page())))
    backfill_mod.backfill(132, ["0001", "0002"], tmp_path / "a.json", delay=2.5)
    assert sleeps == [2.5, 2.5]


def test_the_default_rate_is_one_request_per_second(backfill_mod):
    """The workflow passes no --delay, so the argparse default IS the production
    rate against a state government server. Every other delay assertion passes
    the value explicitly, which left this one number — the number the whole
    design is about — with nothing behind it."""
    args = backfill_mod.parse_args(
        ["--session", "132", "--parquet-source", "x", "--output", "/tmp/x"]
    )
    assert args.delay == 1.0
    assert backfill_mod.DEFAULT_DELAY == 1.0


def test_the_workflow_relies_on_that_default():
    """If the workflow ever starts passing --delay, this test should be replaced
    by one asserting the value it passes. Until then the default is the rate."""
    workflow = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "data-run.yml"
    body = workflow.read_text()
    backfill_step = body.split("scripts/backfill_bill_status.py")[1][:400]
    assert "--delay" not in backfill_step


def test_requests_carry_a_contactable_user_agent(backfill_mod):
    """A state server should be able to tell who is asking and why."""
    backfill_mod._HTTP = None
    try:
        agent = backfill_mod.http_session().headers["User-Agent"]
    finally:
        backfill_mod._HTTP = None
    assert "github.com/PhilipMathieu/maine-bills" in agent


def test_requests_use_a_timeout(backfill_mod, fake_http, tmp_path):
    """Without one a hung connection stalls the whole session indefinitely."""
    seen = {}

    class RecordingSession(FakeSession):
        def get(self, url, timeout=None):
            seen["timeout"] = timeout
            return super().get(url, timeout=timeout)

    fake_http(RecordingSession(default=FakeResponse(200, status_page())))
    backfill_mod.backfill(132, ["0001"], tmp_path / "a.json", delay=0)
    assert seen["timeout"] == backfill_mod.REQUEST_TIMEOUT


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
    # MAX_ATTEMPTS in the main loop, then the end-of-run retry pass tries the
    # same bill once more with its own attempts.
    assert len(http.requested) == backfill_mod.MAX_ATTEMPTS * 2


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
    bad = FakeResponse(200, "<html><title>Error</title></html>")
    # `default` set so the retry pass sees the same unrecognized page rather
    # than falling off the end of the sequence.
    fake_http(FakeSession(sequence=[bad, good], default=bad))
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


# --- the site soft-404s, which is the whole shape of "no such bill" here ---


def not_found_page():
    """The real not-found page: 200, normal chrome, no paper number.

    Captured from display_ps.asp?LD=9999&snum=132. The heading is what
    _parse_bill_title's longest-heading fallback picks up.
    """
    return (
        "<html><head><title>Maine Legislature</title></head><body>"
        "<h1>Cannot find requested paper,<br> please provide a Paper or LD "
        "number in the box to the left.</h1>"
        "<p>Please call Legislative Information at 287-1692 for assistance.</p>"
        "</body></html>"
    )


def test_the_soft_404_is_not_recorded_as_a_bill(backfill_mod, fake_http, tmp_path):
    """The site answers 200 for a nonexistent LD. Accepting `paper or title`
    let the error heading through as an act title, so every nonexistent LD in
    every session would have been stored as a real bill titled "Cannot find
    requested paper..." and the run would have reported success."""
    fake_http(FakeSession(default=FakeResponse(200, not_found_page())))
    summary = backfill_mod.backfill(132, ["9999"], tmp_path / "a.json", delay=0)
    assert summary["records"] == 0
    assert summary["no_status_page"] == 1
    assert summary["failed"] == 0, "a plain answer from the site is not a failure"
    assert json.loads((tmp_path / "a.json").read_text()) == []


def test_the_soft_404_is_persisted_like_a_hard_404(backfill_mod, fake_http, tmp_path):
    """Since this host never hard-404s, persistence has to key off the soft one
    or the resume optimization does nothing at all in practice."""
    out = tmp_path / "a.json"
    fake_http(FakeSession(default=FakeResponse(200, not_found_page())))
    backfill_mod.backfill(132, ["9999"], out, delay=0)
    assert json.loads((tmp_path / "a-missing.json").read_text()) == ["9999"]

    http2 = fake_http(FakeSession(default=FakeResponse(200, not_found_page())))
    backfill_mod.backfill(132, ["9999"], out, delay=0)
    assert http2.requested == []


def test_an_unrecognized_200_is_a_failure_not_a_missing_bill(backfill_mod, fake_http, tmp_path):
    """A WAF challenge or outage page is transient. Recording it as "this bill
    does not exist" would persist it and never ask again."""
    fake_http(FakeSession(default=FakeResponse(200, "<html><body>Access denied</body></html>")))
    summary = backfill_mod.backfill(132, ["0001"], tmp_path / "a.json", delay=0)
    assert summary["failed"] == 1
    assert summary["no_status_page"] == 0
    assert (
        not (tmp_path / "a-missing.json").exists()
        or json.loads((tmp_path / "a-missing.json").read_text()) == []
    )


# --- the circuit breaker: not being a burden when the site says stop ---


def test_sustained_failure_aborts_instead_of_running_the_whole_session(
    backfill_mod, fake_http, tmp_path
):
    """Per-LD retry alone means a blocked run still issues one request per
    remaining bill. Against a state server that has already refused, times
    three concurrent sessions, that is the exact harm the throttle exists to
    avoid."""
    http = fake_http(FakeSession(default=FakeResponse(403, "blocked")))
    lds = [f"{i:04d}" for i in range(1, 501)]
    summary = backfill_mod.backfill(132, lds, tmp_path / "a.json", delay=0)

    assert summary["aborted"] is True
    assert len(http.requested) == backfill_mod.MAX_CONSECUTIVE_FAILURES
    # All 500 remain outstanding: the 10 we did try failed, so they still need
    # fetching too. "Not attempted" counts what a rerun must still do.
    assert summary["not_attempted"] == 500
    assert summary["complete"] is False


def test_scattered_failures_do_not_abort_a_healthy_run(backfill_mod, fake_http, tmp_path):
    """The breaker is for a site that has stopped answering, not for one bad
    bill every so often.

    Deliberately more scattered failures (30) than the threshold (10), spread
    over 300 bills. An earlier version used 6 failures over 30 bills — under
    the threshold, so it passed even with the on-success counter reset deleted,
    which is the one line that makes the breaker safe for a healthy run.
    """
    good, bad = FakeResponse(200, status_page()), FakeResponse(403, "")
    sequence = [bad if i % 10 == 0 else good for i in range(300)]
    # `default` keeps the retry pass failing too, so the assertions below are
    # about the breaker rather than about the fake running out of responses.
    fake_http(FakeSession(sequence=sequence, default=bad))
    summary = backfill_mod.backfill(
        132, [f"{i:04d}" for i in range(1, 301)], tmp_path / "a.json", 0
    )
    assert summary["aborted"] is False
    assert summary["failed"] == 30
    assert summary["records"] == 270


def test_a_long_retry_after_stops_the_session_rather_than_sitting_it_out(
    backfill_mod, fake_http, sleeps, tmp_path
):
    """A rate limiter naming a 300s wait, honored three times per bill, meant a
    single LD cost ~900s. Ten of those is 150 minutes against a 120-minute job
    timeout, so the breaker could never fire — the job just slept until it was
    killed. A wait we are not willing to sit through ends the run instead."""
    busy = FakeResponse(429, "")
    busy.headers = {"Retry-After": "300"}
    http = fake_http(FakeSession(default=busy))
    summary = backfill_mod.backfill(
        132, [f"{i:04d}" for i in range(1, 501)], tmp_path / "a.json", delay=1.0
    )
    assert summary["aborted"] is True
    assert "Retry-After" in summary["abort_reason"]
    assert len(http.requested) == 1, "it should stop on the first such answer"
    assert max(sleeps, default=0) <= backfill_mod.RETRY_AFTER_ABORT


def test_no_backoff_sleep_after_the_final_attempt(backfill_mod, fake_http, sleeps, tmp_path):
    """The wait is a backoff before a retry. After the last attempt there is no
    retry, so sleeping is pure dead time against the job's clock."""
    fake_http(FakeSession(default=FakeResponse(503, "")))
    backfill_mod.backfill(132, ["0001"], tmp_path / "a.json", delay=1.0)
    # Backoff before attempts 2 and 3, none after 3, then the inter-bill delay.
    # Asserted as an exact sequence: filtering by value silently dropped the
    # first backoff, which happens to equal the inter-bill delay. The retry
    # pass repeats the same shape, so only the first pass is pinned here.
    assert sleeps[:3] == [2.0, 4.0, 1.0]


def test_no_backoff_sleep_after_the_final_attempt_on_a_network_error(
    backfill_mod, fake_http, sleeps, tmp_path
):
    """Same rule on the connection-error path, which has its own sleep."""

    class ExplodingSession(FakeSession):
        def get(self, url, timeout=None):
            self.requested.append(url)
            raise backfill_mod.requests.ConnectionError("refused")

    fake_http(ExplodingSession())
    backfill_mod.backfill(132, ["0001"], tmp_path / "a.json", delay=1.0)
    assert sleeps[:3] == [1.0, 2.0, 1.0]


def test_a_missing_bill_resets_the_failure_streak(backfill_mod, fake_http, tmp_path):
    """The two breakers count separately. A site answering "no such bill" in
    between failures is still answering, so the failure streak must reset — or
    scattered failures with normal gaps between them accumulate to an abort
    that never actually happened consecutively."""
    bad, gap = FakeResponse(403, ""), FakeResponse(200, not_found_page())
    # Nine failures, then a plain answer, repeated: never ten in a row.
    sequence = []
    for _ in range(12):
        sequence.extend([bad] * 9 + [gap])
    fake_http(FakeSession(sequence=sequence))
    summary = backfill_mod.backfill(
        132, [f"{i:04d}" for i in range(1, 121)], tmp_path / "a.json", delay=0
    )
    assert summary["aborted"] is False


def test_a_gap_in_a_working_session_does_not_abort_it(backfill_mod, fake_http, tmp_path):
    """The missing breaker requires that NOTHING has been recorded yet.

    The documents come from lldc.mainelegislature.org and the status pages from
    legislature.maine.gov — independent systems — so a contiguous stretch where
    the document repository outruns the status application is normal. Session
    124 has a real page at LD 1800 and none at LD 1850. Aborting on the run
    length alone would kill a healthy session for it.
    """
    good, gone = FakeResponse(200, status_page()), FakeResponse(200, not_found_page())
    # One real bill, then a gap three times longer than the breaker's threshold.
    sequence = [good] + [gone] * (backfill_mod.MAX_CONSECUTIVE_MISSING * 3)
    http = fake_http(FakeSession(sequence=sequence))
    lds = [f"{i:04d}" for i in range(1, len(sequence) + 1)]
    summary = backfill_mod.backfill(124, lds, tmp_path / "a.json", delay=0)

    assert summary["aborted"] is False
    assert len(http.requested) == len(lds)
    assert summary["records"] == 1
    assert summary["complete"] is True


def test_a_missing_bill_does_not_reset_the_failure_streak_counter(
    backfill_mod, fake_http, tmp_path
):
    """The failure branch clears `consecutive_missing`. Without it, missing
    bills scattered between failures accumulate toward the missing breaker and
    could abort a run where they were never consecutive at all."""
    gone, bad = FakeResponse(200, not_found_page()), FakeResponse(403, "")
    sequence = []
    for _ in range(30):
        sequence.extend([gone] * 5 + [bad])
    fake_http(FakeSession(sequence=sequence))
    lds = [f"{i:04d}" for i in range(1, 181)]
    summary = backfill_mod.backfill(132, lds, tmp_path / "a.json", delay=0)
    assert summary["abort_reason"] is None or "consecutive failures" in summary["abort_reason"]


def test_the_missing_breaker_records_why_it_stopped(backfill_mod, fake_http, tmp_path):
    fake_http(FakeSession(default=FakeResponse(200, not_found_page())))
    lds = [f"{i:04d}" for i in range(1, 201)]
    summary = backfill_mod.backfill(140, lds, tmp_path / "a.json", delay=0)
    assert summary["aborted"] is True
    assert "no status page" in summary["abort_reason"]


def test_a_retry_after_exactly_at_the_threshold_is_slept_not_aborted(
    backfill_mod, fake_http, sleeps, tmp_path
):
    """Pins the boundary: the abort is for a wait LONGER than we will sit
    through, so the threshold value itself is still honored normally."""
    busy = FakeResponse(503, "")
    busy.headers = {"Retry-After": str(int(backfill_mod.RETRY_AFTER_ABORT))}
    fake_http(FakeSession(sequence=[busy, FakeResponse(200, status_page())]))
    summary = backfill_mod.backfill(132, ["0001"], tmp_path / "a.json", delay=1.0)
    assert summary["aborted"] is False
    assert backfill_mod.RETRY_AFTER_ABORT in sleeps


def test_missing_bills_do_not_trip_the_breaker(backfill_mod, fake_http, tmp_path):
    """A session with a long run of nonexistent LDs is normal, not a refusal."""
    fake_http(FakeSession(default=FakeResponse(200, not_found_page())))
    lds = [f"{i:04d}" for i in range(1, 41)]
    summary = backfill_mod.backfill(132, lds, tmp_path / "a.json", delay=0)
    assert summary["aborted"] is False
    assert summary["no_status_page"] == 40


def test_retry_after_is_honored_over_our_own_backoff(backfill_mod, fake_http, sleeps, tmp_path):
    busy = FakeResponse(503, "")
    busy.headers = {"Retry-After": "7"}
    fake_http(FakeSession(sequence=[busy, FakeResponse(200, status_page())]))
    backfill_mod.backfill(132, ["0001"], tmp_path / "a.json", delay=1.0)
    assert 7.0 in sleeps, "the server told us how long to wait"


def test_an_absurd_retry_after_is_capped(backfill_mod):
    class R:
        headers = {"Retry-After": "999999"}

    assert backfill_mod.retry_after(R(), 2.0) == 300.0


def test_a_junk_retry_after_falls_back_to_our_backoff(backfill_mod):
    class R:
        headers = {"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"}

    assert backfill_mod.retry_after(R(), 2.0) == 2.0


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


def test_an_incomplete_recheck_does_not_forget_the_rest_of_the_missing_set(
    backfill_mod, fake_http, tmp_path
):
    """Regression: --recheck-missing started from an empty set and overwrote the
    sidecar with only what it re-reached, so a recheck cut short by --limit, a
    crash, or the job timeout erased every LD it had not got to yet. The next
    normal run then re-asked the site for all of them."""
    out = tmp_path / "a.json"
    lds = [f"{i:04d}" for i in range(1, 6)]
    fake_http(FakeSession(default=FakeResponse(200, not_found_page())))
    backfill_mod.backfill(132, lds, out, delay=0)
    assert len(json.loads((tmp_path / "a-missing.json").read_text())) == 5

    fake_http(FakeSession(default=FakeResponse(200, not_found_page())))
    backfill_mod.backfill(132, lds, out, delay=0, recheck_missing=True, limit=1)
    assert json.loads((tmp_path / "a-missing.json").read_text()) == lds, (
        "the four LDs this run never reached must still be recorded as missing"
    )

    http = fake_http(FakeSession(default=FakeResponse(200, not_found_page())))
    backfill_mod.backfill(132, lds, out, delay=0)
    assert http.requested == [], "a normal resume must not refetch them"


def test_a_recheck_that_finds_a_page_removes_only_that_ld(backfill_mod, fake_http, tmp_path):
    out = tmp_path / "a.json"
    lds = ["0001", "0002", "0003"]
    fake_http(FakeSession(default=FakeResponse(200, not_found_page())))
    backfill_mod.backfill(132, lds, out, delay=0)

    fake_http(FakeSession(sequence=[FakeResponse(200, status_page())]))
    backfill_mod.backfill(132, lds, out, delay=0, recheck_missing=True, limit=1)
    assert json.loads((tmp_path / "a-missing.json").read_text()) == ["0002", "0003"]


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
    """A crash at bill 900 of 2500 must not discard the first 899.

    Asserted DURING the run: checking the file afterwards passes even with
    checkpointing deleted entirely, because the final write produces the same
    result. The whole point is what is on disk before the run ends.
    """
    out = tmp_path / "a.json"
    on_disk = []

    class WatchingSession(FakeSession):
        def get(self, url, timeout=None):
            on_disk.append(len(json.loads(out.read_text())) if out.exists() else 0)
            return super().get(url, timeout=timeout)

    fake_http(WatchingSession(default=FakeResponse(200, status_page())))
    backfill_mod.backfill(132, [f"{i:04d}" for i in range(1, 7)], out, delay=0, checkpoint_every=2)

    assert len(json.loads(out.read_text())) == 6
    # Before requests 3 and 5 the first 2 and 4 records must already be saved.
    assert on_disk == [0, 0, 2, 2, 4, 4]


def test_a_truncated_checkpoint_does_not_discard_the_session(backfill_mod, fake_http, tmp_path):
    """A kill mid-write used to leave half a JSON file, which load_existing
    treats as "start fresh" — silently re-requesting ~2000 already-fetched
    pages. Writes go through a temp file and a rename instead."""
    out = tmp_path / "a.json"
    fake_http(FakeSession(default=FakeResponse(200, status_page())))
    backfill_mod.backfill(132, [f"{i:04d}" for i in range(1, 5)], out, delay=0)

    # Nothing should be left behind that a resume would trip over.
    assert list(tmp_path.glob("*.tmp")) == []
    http = fake_http(FakeSession(default=FakeResponse(200, status_page())))
    backfill_mod.backfill(132, [f"{i:04d}" for i in range(1, 5)], out, delay=0)
    assert http.requested == []


def test_the_temp_file_is_private_to_this_process(backfill_mod, monkeypatch, tmp_path):
    """Two runs of the same session sharing one temp path interleave into the
    same file and can rename corrupt JSON into place — defeating the point of
    writing atomically. The matrix dedupe covers one dispatch, not two, nor a
    local run alongside CI."""
    seen = []
    real_replace = Path.replace

    def spy(self, target):
        seen.append(self.name)
        return real_replace(self, target)

    monkeypatch.setattr(Path, "replace", spy)
    backfill_mod.write_json(tmp_path / "a.json", [])
    assert seen and str(os.getpid()) in seen[0]


def test_a_write_that_dies_partway_leaves_the_previous_file_intact(
    backfill_mod, monkeypatch, tmp_path
):
    """The property atomicity actually buys. A plain write_text truncates the
    destination before the new bytes land, so a kill during a checkpoint costs
    the whole session; writing to a temp file and renaming cannot.
    """
    out = tmp_path / "a.json"
    backfill_mod.write_json(out, [{"ld_number": "0001"}])

    def die(self, target):
        raise OSError("killed during rename")

    monkeypatch.setattr(Path, "replace", die)
    with pytest.raises(OSError):
        backfill_mod.write_json(out, [{"ld_number": "9999"}])

    assert json.loads(out.read_text()) == [{"ld_number": "0001"}]


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


# --- the exit code, which is how a dispatched run reports itself ---


def run_main(backfill_mod, monkeypatch, fake_http, tmp_path, response, lds=("0001",)):
    monkeypatch.setattr(backfill_mod, "session_ld_numbers", lambda _src, _s: list(lds))
    fake_http(FakeSession(default=response))
    code = backfill_mod.main(
        [
            "--session",
            "132",
            "--parquet-source",
            "unused",
            "--output",
            str(tmp_path),
            "--delay",
            "0",
        ]
    )
    return code, json.loads((tmp_path / "summary-132.json").read_text())


def test_a_clean_run_exits_zero(backfill_mod, monkeypatch, fake_http, tmp_path):
    code, summary = run_main(
        backfill_mod, monkeypatch, fake_http, tmp_path, FakeResponse(200, status_page())
    )
    assert code == 0
    assert summary["complete"] is True


def test_some_missing_bills_do_not_make_the_session_incomplete(
    backfill_mod, monkeypatch, fake_http, tmp_path
):
    """A missing bill is a plain answer from the site, not a failure."""
    monkeypatch.setattr(backfill_mod, "session_ld_numbers", lambda _src, _s: ["0001", "0002"])
    fake_http(
        FakeSession(
            sequence=[FakeResponse(200, not_found_page()), FakeResponse(200, status_page())]
        )
    )
    code = backfill_mod.main(
        ["--session", "132", "--parquet-source", "u", "--output", str(tmp_path), "--delay", "0"]
    )
    summary = json.loads((tmp_path / "summary-132.json").read_text())
    assert code == 0
    assert (summary["records"], summary["no_status_page"]) == (1, 1)
    assert summary["complete"] is True


def test_a_session_where_every_bill_is_missing_is_not_a_success(
    backfill_mod, monkeypatch, fake_http, tmp_path
):
    """A wrong session number returns the identical not-found body for every LD.
    Nothing is then outstanding, so the run reported complete with an empty
    actions table and a green check. Enumeration comes from the parquet, so
    every LD asked about is one we hold a document for — this many misses in a
    row is systemic, not a sparse session."""
    lds = [f"{i:04d}" for i in range(1, 201)]
    http = fake_http(FakeSession(default=FakeResponse(200, not_found_page())))
    monkeypatch.setattr(backfill_mod, "session_ld_numbers", lambda _src, _s: lds)
    code = backfill_mod.main(
        ["--session", "140", "--parquet-source", "u", "--output", str(tmp_path), "--delay", "0"]
    )
    summary = json.loads((tmp_path / "summary-140.json").read_text())

    assert code == 1
    assert summary["complete"] is False
    assert summary["aborted"] is True
    assert len(http.requested) == backfill_mod.MAX_CONSECUTIVE_MISSING
    assert json.loads((tmp_path / "actions-140.json").read_text()) == []


def test_an_empty_ld_set_is_not_a_success(backfill_mod, monkeypatch, fake_http, tmp_path):
    """A session absent from the parquet has nothing outstanding either."""
    monkeypatch.setattr(backfill_mod, "session_ld_numbers", lambda _src, _s: [])
    fake_http(FakeSession(default=FakeResponse(200, status_page())))
    code = backfill_mod.main(
        ["--session", "133", "--parquet-source", "u", "--output", str(tmp_path)]
    )
    assert code == 1
    assert json.loads((tmp_path / "summary-133.json").read_text())["complete"] is False


def test_a_blocked_run_exits_non_zero(backfill_mod, monkeypatch, fake_http, tmp_path):
    """Returning 0 unconditionally meant a run blocked at request one produced a
    green check and an empty artifact — indistinguishable from success."""
    lds = [f"{i:04d}" for i in range(1, 60)]
    code, summary = run_main(
        backfill_mod, monkeypatch, fake_http, tmp_path, FakeResponse(403, "blocked"), lds=lds
    )
    assert code == 1
    assert summary["aborted"] is True
    assert summary["complete"] is False


def test_sigterm_still_leaves_a_summary(tmp_path):
    """The job timeout kills with SIGTERM, and Python's default disposition
    terminates the process WITHOUT raising — so `except BaseException` never
    ran and a timed-out job left a partial actions table and no summary, which
    is indistinguishable from a small complete session.

    Has to be a real subprocess: the whole point is what the signal does to a
    normal interpreter, which an in-process fake cannot show.
    """
    driver = tmp_path / "driver.py"
    driver.write_text(
        "import importlib.util, sys, time, os\n"
        f"spec = importlib.util.spec_from_file_location('bf', {str(SCRIPT)!r})\n"
        "bf = importlib.util.module_from_spec(spec); spec.loader.exec_module(bf)\n"
        "bf.session_ld_numbers = lambda *_a: ['0001']\n"
        "bf.backfill = lambda *a, **k: time.sleep(60)\n"
        f"sys.exit(bf.main(['--session','132','--parquet-source','u','--output',{str(tmp_path)!r}]))\n"
    )
    proc = subprocess.Popen(
        [sys.executable, str(driver)], stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    summary_path = tmp_path / "summary-132.json"
    deadline = time.time() + 20
    while not proc.poll() and time.time() < deadline:
        time.sleep(0.1)
        if (tmp_path / "driver.py").exists() and time.time() > deadline - 18:
            break
    proc.terminate()
    proc.wait(timeout=15)

    assert summary_path.exists(), "SIGTERM must not lose the summary"
    summary = json.loads(summary_path.read_text())
    assert summary["complete"] is False
    assert summary["aborted"] is True
    # The signal path bypasses main()'s `return 1` entirely, so the exit code is
    # whatever the handler names. 128+SIGTERM by convention; without this
    # assertion the handler could exit 0 and report a killed job as a success.
    assert proc.returncode == 143


def test_a_crash_still_leaves_a_summary_saying_it_failed(
    backfill_mod, monkeypatch, fake_http, tmp_path
):
    """Otherwise the artifact holds a partial actions table and no summary,
    which looks exactly like a small complete session."""
    monkeypatch.setattr(backfill_mod, "session_ld_numbers", lambda _src, _s: ["0001"])

    def boom(*_a, **_k):
        raise KeyboardInterrupt

    monkeypatch.setattr(backfill_mod, "backfill", boom)
    with pytest.raises(KeyboardInterrupt):
        backfill_mod.main(["--session", "132", "--parquet-source", "u", "--output", str(tmp_path)])

    summary = json.loads((tmp_path / "summary-132.json").read_text())
    assert summary["complete"] is False
    assert "KeyboardInterrupt" in summary["error"]


def test_a_limited_smoke_test_does_not_claim_the_session_is_complete(
    backfill_mod, fake_http, tmp_path
):
    """Completeness is measured against the full LD set. Derived from the run's
    own todo list, --limit reported complete: the run finished everything it was
    asked for while thousands of bills remained unfetched."""
    fake_http(FakeSession(default=FakeResponse(200, status_page())))
    lds = [f"{i:04d}" for i in range(1, 101)]
    summary = backfill_mod.backfill(132, lds, tmp_path / "a.json", delay=0, limit=3)
    assert summary["records"] == 3
    assert summary["not_attempted"] == 97
    assert summary["complete"] is False


def test_limit_caps_the_run_for_a_smoke_test(backfill_mod, fake_http, tmp_path):
    http = fake_http(FakeSession(default=FakeResponse(200, status_page())))
    backfill_mod.backfill(132, ["0001", "0002", "0003"], tmp_path / "a.json", delay=0, limit=2)
    assert len(http.requested) == 2


# --- the end-of-run retry pass, added after the smoke run ---


def test_a_transient_tail_of_failures_is_retried_and_the_session_completes(
    backfill_mod, fake_http, tmp_path
):
    """The case the smoke run actually hit.

    Sessions 132 and 121 each finished 2034/2041 and 1957/1965, failing only on
    a handful of read timeouts, and each reported incomplete and exited 1 over
    them. A CI job cannot resume, so recovering seven bills would have meant
    refetching two thousand pages — worse for us and ruder to the site than
    seven requests at the end of the run.
    """
    good, flaky = FakeResponse(200, status_page()), FakeResponse(503, "")
    # Bill 3 fails its three attempts, then succeeds on the retry pass.
    sequence = [good, good, flaky, flaky, flaky, good, good]
    fake_http(FakeSession(sequence=sequence, default=good))
    summary = backfill_mod.backfill(
        132, ["0001", "0002", "0003", "0004"], tmp_path / "a.json", delay=0
    )

    assert summary["failed"] == 0
    assert summary["records"] == 4
    assert summary["complete"] is True


def test_the_retry_pass_does_not_re_drive_a_session_that_failed_in_bulk(
    backfill_mod, fake_http, tmp_path
):
    """Bounded on purpose: a session failing at scale has something actually
    wrong with it, and re-driving all of it is what the breakers exist to
    prevent. Only a transient-looking tail is retried."""
    lds = [f"{i:04d}" for i in range(1, 401)]
    # Alternate so the consecutive-failure breaker never fires but the failure
    # count climbs past the retry ceiling.
    good, bad = FakeResponse(200, status_page()), FakeResponse(403, "")
    fake_http(FakeSession(sequence=[bad if i % 2 else good for i in range(400)], default=good))
    summary = backfill_mod.backfill(132, lds, tmp_path / "a.json", delay=0)

    assert summary["failed"] > backfill_mod.MAX_RETRY_PASS
    assert summary["complete"] is False


def test_an_aborted_run_is_not_retried(backfill_mod, fake_http, tmp_path):
    """If the breaker stopped us, going back for more is exactly wrong."""
    http = fake_http(FakeSession(default=FakeResponse(403, "blocked")))
    lds = [f"{i:04d}" for i in range(1, 101)]
    summary = backfill_mod.backfill(132, lds, tmp_path / "a.json", delay=0)
    assert summary["aborted"] is True
    assert len(http.requested) == backfill_mod.MAX_CONSECUTIVE_FAILURES


def test_the_retry_pass_records_a_bill_that_turns_out_to_be_missing(
    backfill_mod, fake_http, tmp_path
):
    """A retried bill answering "no such bill" belongs in the sidecar, not the
    failed list — otherwise it is refetched forever."""
    good, flaky = FakeResponse(200, status_page()), FakeResponse(503, "")
    fake_http(
        FakeSession(
            sequence=[good, flaky, flaky, flaky],
            default=FakeResponse(200, not_found_page()),
        )
    )
    summary = backfill_mod.backfill(132, ["0001", "0002"], tmp_path / "a.json", delay=0)
    assert summary["failed"] == 0
    assert summary["no_status_page"] == 1
    assert json.loads((tmp_path / "a-missing.json").read_text()) == ["0002"]
