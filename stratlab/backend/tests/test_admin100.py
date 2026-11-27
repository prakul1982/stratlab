"""Lane admin100 (owner, 27 Nov: "errors in Admin", twice, while the exchange's archive refused this server on one host): every outside
source has an Admin row with its real last good answer and last failure, a passing failure is never shown as broken, a check clears after
the next good run, and only what the owner can fix reaches Needs your attention. Each test fails on origin/main 28fc7cf."""
from app import main  # noqa: F401, I001  (main first: it loads the modules in the order they need)
import json
import time

import httpx
import pytest

from app import admin_jobs, alerts, autofix, billing, db, source_health as H
from app.intel import nse_archive as A
from app.intel.net import Source, SourceError

NOW = 1_800_000_000.0           # a fixed moment (Jan 2027)


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    store: dict = {}
    monkeypatch.setattr(db, "set_setting", lambda k, v: store.__setitem__(k, v))
    monkeypatch.setattr(db, "get_setting", lambda k: store.get(k))
    H.reset()
    yield store
    H.reset()


def row(key: str, now: float = NOW) -> dict:
    return next(r for r in H.rows(now) if r["key"] == key)


# ---------- the exchange's archive: one row with the truth ----------
def test_an_archive_file_served_by_the_next_host_is_ok_with_a_note_naming_both_hosts():
    """fix98's case: .in refused (403), .com served. Admin had no row for the archive at all; it now says OK, and why nothing is needed."""
    def handler(r):
        return httpx.Response(403) if r.url.host == "nsearchives.nseindia.in" else httpx.Response(200, text="SYMBOL\n")
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        assert A.get(http, "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv").status_code == 200
    r = row("nse-archive", time.time())
    assert r["state"] == "ok" and r["last_ok"] and not r["last_fail"]
    assert "Served by nsearchives.nseindia.com after nsearchives.nseindia.in refused (403)" in r["detail"]
    assert "nothing to do" in r["detail"] and not r["owner"]


def test_every_host_refusing_is_a_failure_and_the_next_good_read_clears_it():
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(403))) as http:
        assert A.get(http, "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv").status_code == 403
    r = row("nse-archive", time.time())
    assert r["last_fail"] and r["error"] == "every archive host refused this server (403)"
    assert r["state"] == "ok" and r["word"] == "Retrying"          # one failed read: retried by itself, not a warning
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(404))) as http:    # a 404 is the archive's answer
        A.get(http, "https://nsearchives.nseindia.com/archives/x.csv")
    r = row("nse-archive", time.time())
    assert r["state"] == "ok" and r["word"] == "OK" and "the next one worked" in r["detail"]


def test_a_source_not_answering_is_retrying_then_a_check_then_down_never_the_owners():
    for i in range(2):
        H.record("nse-archive", False, "every archive host refused this server (403)", now=NOW + i * 60)
    assert row("nse-archive", NOW + 120)["word"] == "Retrying"            # two failures in two minutes: a blip
    H.record("nse-archive", False, "every archive host refused this server (403)", now=NOW + 40 * 60)
    r = row("nse-archive", NOW + 41 * 60)
    assert r["state"] == "warn" and r["word"] == "Not answering" and "nothing for you to do" in r["detail"] and not r["owner"]
    r = row("nse-archive", NOW + 25 * 3600)
    assert r["state"] == "bad" and r["word"] == "Down" and "nothing in Admin fixes it" in r["detail"] and not r["owner"]
    H.record("nse-archive", True, now=NOW + 25 * 3600 + 5)                # the next good read: cleared at once
    assert row("nse-archive", NOW + 25 * 3600 + 10)["state"] == "ok"


def test_every_known_source_has_a_row_even_before_it_is_asked():
    keys = [r["key"] for r in H.rows(NOW)]
    assert keys[:7] == ["broker", "nse-archive", "nse-feed", "bse", "sec", "mail", "payments"]
    r = row("sec")
    assert r["state"] == "ok" and r["word"] == "Not asked yet" and r["last_ok"] is None


def test_a_research_source_notes_each_upstream_call_but_not_its_own_rate_limit():
    def handler(r):
        return httpx.Response(503) if r.url.path == "/down" else httpx.Response(404) if r.url.path == "/none" else httpx.Response(200, json={"a": 1})

    class Sec(Source):
        name = "The SEC"
    s = Sec("https://data.sec.gov", transport=httpx.MockTransport(handler))
    with pytest.raises(SourceError):
        s.fetch("/down")
    assert row("sec", time.time())["error"] == "The SEC is having trouble (503)."
    with pytest.raises(SourceError):
        s.fetch("/none")                    # "nothing for that" is the source answering
    assert row("sec", time.time())["word"] == "OK"
    s.limit.tokens, s.limit.rate = 0, 1e-9
    fails = row("sec", time.time())["last_fail"]
    with pytest.raises(SourceError, match="our rate limit"):
        s.fetch("/again")
    assert row("sec", time.time())["last_fail"] == fails


def test_the_exchange_feeds_are_noted_by_how_each_call_ended():
    from app.intel import filings as F
    feed = F.NSEFilings(transport=httpx.MockTransport(lambda r: httpx.Response(200, text="<html>guard</html>")), sleep=lambda s: None)
    with pytest.raises(SourceError):
        feed._get("/api/corporate-announcements", {})
    assert "page instead of data" in row("nse-feed", time.time())["error"]
    bse = F.BSEFilings(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"Table": []})), sleep=lambda s: None)
    bse._call("/x", {})
    assert row("bse", time.time())["word"] == "OK"


# ---------- owner-fixed sources: the email service and payments ----------
def test_the_email_service_failing_twice_is_the_owners_to_fix_with_the_exact_step(monkeypatch):
    monkeypatch.setattr(alerts.settings, "BREVO_API_KEY", "k")

    def refuse(*a, **k):
        raise RuntimeError("Brevo refused the email (401). Brevo only accepts emails from addresses you approved, and this server's IP address isn't one.")
    monkeypatch.setattr(alerts, "_send_brevo", refuse)
    with pytest.raises(RuntimeError):
        alerts.send_email("owner@example.com", "x", "y")
    assert row("mail", time.time())["word"] == "Retrying" and not row("mail", time.time())["owner"]
    with pytest.raises(RuntimeError):
        alerts.send_email("owner@example.com", "x", "y")
    r = row("mail", time.time())
    assert r["state"] == "bad" and r["owner"] and "Authorized IPs" in r["action"]
    monkeypatch.setattr(alerts, "_send_brevo", lambda *a, **k: None)
    alerts.send_email("owner@example.com", "x", "y")
    assert row("mail", time.time())["state"] == "ok"


def test_no_email_service_set_up_is_not_noted_as_a_failure(monkeypatch):
    for k in ("BREVO_API_KEY", "RESEND_API_KEY", "SMTP_HOST"):
        monkeypatch.setattr(alerts.settings, k, "")
    with pytest.raises(RuntimeError):
        alerts.send_email("owner@example.com", "x", "y")
    assert row("mail")["word"] == "Not asked yet"


def test_razorpays_reads_are_noted_for_the_payments_row(monkeypatch):
    monkeypatch.setattr(billing.settings, "RAZORPAY_KEY_ID", "rzp_test_x")
    monkeypatch.setattr(billing.settings, "RAZORPAY_KEY_SECRET", "s")

    class Bad:
        def all(self, *a):
            raise RuntimeError("Authentication failed")

    class Client:
        subscription = refund = payment = Bad()
    monkeypatch.setattr(billing, "client", lambda: Client())
    billing.activity()
    billing.activity()
    r = row("payments", time.time())
    assert r["state"] == "bad" and r["owner"] and "RAZORPAY_KEY_ID" in r["action"]


# ---------- kept across a restart, small ----------
def test_the_table_survives_a_restart_and_stays_bounded(clean):
    H.record("nse-archive", False, "every archive host refused this server (403)", now=NOW)
    assert json.loads(clean[H.KEY])["nse-archive"]["fails"] == 1
    H._st.clear()
    H._loaded["done"] = False                 # a new server
    r = row("nse-archive", NOW + 60)
    assert r["before_restart"] and r["last_fail"]
    for i in range(H.MAX_KEYS + 10):
        H.record(f"Source {i}", True, now=NOW)
    assert len(H._st) <= H.MAX_KEYS


def test_a_key_or_token_in_an_address_never_reaches_the_row():
    H.record("Finnhub", False, "Couldn't read https://finnhub.io/api/v1/quote?symbol=X&token=SECRET123", now=NOW)
    assert "SECRET123" not in json.dumps(H.rows(NOW))


# ---------- jobs: a Problem is what the self-healing couldn't fix ----------
def test_a_job_that_just_failed_is_a_check_while_the_sweep_is_on(monkeypatch):
    rows = [{"id": "ipo", "name": "IPOs", "state": "bad", "error": "BONFIG: The exchange sent a page instead of data."},
            {"id": "breadth", "name": "Market breadth", "state": "bad", "error": "Stuck: running for 3 h"},
            {"id": "holidays", "name": "Exchange holidays", "state": "bad", "error": "couldn't reach"}]
    empty = autofix._empty()
    monkeypatch.setattr(autofix, "ON", True)
    out = {r["id"]: r for r in autofix.annotate(rows, empty, unwatched=admin_jobs.OWN_CHECK)}
    assert out["ipo"]["state"] == "warn" and out["ipo"]["error"].endswith(autofix.FRESH_NOTE)
    assert out["breadth"]["state"] == "bad" and out["holidays"]["state"] == "bad"
    monkeypatch.setattr(autofix, "ON", False)                  # no self-healing (the browser tests' world): as the job reads
    assert autofix.annotate(rows, empty)[0]["state"] == "bad"


def test_jobs_that_mail_users_are_watched_too_listed_for_the_owner_never_mailed(monkeypatch):
    rows = [{"id": "ibkr-daily", "name": "IBKR daily pull", "state": "bad", "error": "2 accounts", "run": [{"label": "Run now", "path": "/admin/connect/run?part=ibkr"}]},
            {"id": "holidays", "name": "Exchange holidays", "state": "bad", "error": "x", "run": []}]
    monkeypatch.setattr(admin_jobs, "rows", lambda: rows)
    checks = {c.id: c for c in admin_jobs.job_checks()}
    assert "job:holidays" not in checks
    c = checks["job:ibkr-daily"]
    assert c.problem == "2 accounts" and c.fix is None and c.mail is False
    # it escalates (into Needs your attention) only after the window a re-run job gets, and no mail goes
    sent = []
    st = autofix.sweep([c], now=autofix.datetime.fromtimestamp(NOW, autofix.timezone.utc), st=autofix._empty(), send=lambda s, t: sent.append(s) or True)
    assert not autofix.status(st)["escalated"]
    later = autofix.datetime.fromtimestamp(NOW + sum(c.backoff) + c.settle + 60, autofix.timezone.utc)
    st = autofix.sweep([c], now=later, st=st, send=lambda s, t: sent.append(s) or True)
    assert autofix.status(st)["escalated"] and not sent


def test_a_job_switched_off_on_purpose_is_not_a_check():
    r = admin_jobs._row("supply-links", "Customer and supplier map", "Off", None, None)
    assert r["state"] == "ok"
    assert admin_jobs._row("ter", "Fund costs (TER)", "Every 12 hours", None, None)["state"] == "warn"      # never run: still a Check


def test_overview_carries_every_sources_row(monkeypatch):
    from tests import world as W
    from tests.fake_db import headers
    w = W.build(monkeypatch)
    try:
        H.record("nse-archive", True, via="nsearchives.nseindia.com", refused="nsearchives.nseindia.in refused (403)")
        sv = w["client"].get("/admin/overview", headers=headers("admin-token")).json()["server"]
        got = {r["key"]: r for r in sv["sources"]}
        assert got["nse-archive"]["state"] == "ok" and "Served by nsearchives.nseindia.com" in got["nse-archive"]["detail"]
        assert {"nse-feed", "bse", "sec", "mail", "payments"} <= set(got)
    finally:
        w["close"]()


def test_a_feature_check_failing_on_its_sources_side_is_not_the_owners_fix():
    """The daily feature check escalated every failure at once as "Only you can fix this" (owner_only), its own action saying a source's
    fault clears by itself: an exchange refusing the server reached the owner as a Fix and a mail."""
    from app import platform_check as pc
    out = {"at": "2026-11-27T11:20:00+00:00", "checks": [
        pc._result("Exchange filings", "Research", "fail", "The exchange feed refused the request (403). Try again later."),
        pc._result("SEC company", "Research", "fail", "The SEC is having trouble (503)."),
        pc._result("Prices: FX", "Prices", "fail", "1 candle of EUR/USD on 2 Nov is off"),
        pc._result("Fine", "Research", "pass", "ok")]}
    before = ["Exchange filings", "SEC company", "Prices: FX"]
    issue = main.platform_issue(out, before)
    assert issue.problem == "1 check failing after a retry: Prices: FX (1 candle of EUR/USD on 2 Nov is off)"
    only_sources = {**out, "checks": out["checks"][:2] + out["checks"][3:]}
    assert main.platform_issue(only_sources, before).problem is None


def test_the_brokers_reads_are_noted_and_a_cancelled_login_says_so():
    from kiteconnect.exceptions import NetworkException, TokenException
    from app.kite_service import _Guarded

    class Inner:
        def quote(self, keys):
            return {"NSE:X": {}}

        def ltp(self, keys):
            raise NetworkException("Gateway timed out", 504)

        def margins(self):
            raise TokenException("Incorrect api_key or access_token")
    g = _Guarded(Inner(), lambda e: None)
    g.quote(["NSE:X"])
    assert row("broker", time.time())["word"] == "OK"
    with pytest.raises(NetworkException):
        g.ltp(["NSE:X"])
    assert "Gateway timed out" in row("broker", time.time())["error"]
    with pytest.raises(TokenException):
        g.margins()
    assert row("broker", time.time())["error"] == "Zerodha cancelled the day's login"
