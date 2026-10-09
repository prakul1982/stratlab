"""Round 7, mail, payments, broker and reliability (9 Oct 2026): each test is built on the real example the reviewer saw.
Nothing here depends on the time of day: every clock is a fixed instant, and India's and New York's zones are named."""
import json
import re
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import httpx
import pytest

from app import main  # noqa: F401, I001  (first: the app loads the newsletter job before the modules built on it)
from app import ai_providers as P, ai_rank as R, alerts, db, email_kit, invoices, job_status, mail_tokens, money_networth, newsletter_prefs, pricing
from app.ai_catalog import PROVIDERS
from app.ai_clients import parse_aliases
from app.config import settings
from app.kite_service import IST
from app.newsletter import content, job, write
from tests import world
from tests.test_weekly_summary import _week

ADMIN = world.headers("admin-token")
PRO = world.headers("pro-token")
THU = date(2026, 10, 1)                                              # a trading day in India and the US
AFTER_IN_CLOSE = datetime(2026, 10, 1, 11, 0, tzinfo=timezone.utc)   # 16:30 IST
FIVE = timedelta(minutes=5)


@pytest.fixture
def w(monkeypatch):
    built = world.build(monkeypatch)
    content._cache.clear()
    write._cache.clear()
    yield built
    built["close"]()


@pytest.fixture
def mem(monkeypatch):
    """The settings table in memory, for the modules that keep their state there."""
    store: dict = {}
    monkeypatch.setattr(db, "get_setting", lambda k: store.get(k))
    monkeypatch.setattr(db, "set_setting", lambda k, v: store.__setitem__(k, v))
    monkeypatch.setattr(db, "delete_setting", lambda k: store.pop(k, None))
    monkeypatch.setattr(db, "all_settings_with_prefix", lambda p: [(k, v) for k, v in sorted(store.items()) if k.startswith(p)])
    pricing.forget()
    pricing._rates_cache[0] = 0.0
    invoices.forget_gst()
    yield store
    pricing.forget()
    pricing._rates_cache[0] = 0.0
    invoices.forget_gst()


# ---------- R7M-001: empty invoice seller details ----------
def test_empty_seller_details_are_a_warning_and_the_pages_promise_no_gst(w):
    c = w["client"]
    assert invoices.readiness() == {"complete": False, "missing": ["legal name", "address", "state", "GSTIN"], "gst": False}
    # what the first invoice would actually say: a plain one, no GST (the Plans page used to promise "incl. 18% GST")
    lines, supply, note = invoices.tax_lines(699.0, invoices.seller(), {"country": "IN"})
    assert lines == [] and supply == "Unregistered" and "not registered under GST" in note
    assert c.get("/pricing").json()["invoice"] == {"gst": False}                    # so the pages say nothing of GST
    server = c.get("/admin/overview", headers=ADMIN).json()["server"]
    assert server["invoice_seller"]["missing"] == ["legal name", "address", "state", "GSTIN"]
    assert c.get("/admin/invoices", headers=ADMIN).json()["seller_status"]["complete"] is False
    # filled in: invoices carry GST, and the pages may say so
    saved = c.put("/admin/invoices/seller", headers=ADMIN, json={"legal_name": "Example Labs LLP", "address": "1 Example Road, Pune",
                                                                 "state": "27", "gstin": "27AAAAA0000A1Z5"})
    assert saved.json()["seller_status"] == {"complete": True, "missing": [], "gst": True}
    assert c.get("/pricing").json()["invoice"] == {"gst": True}
    lines, supply, _ = invoices.tax_lines(699.0, invoices.seller(), {"country": "IN", "state": "27"})
    assert [x["name"] for x in lines] == ["CGST 9%", "SGST 9%"] and supply == "Intra-state"
    assert c.get("/admin/overview", headers=ADMIN).json()["server"]["invoice_seller"]["complete"] is True


def test_a_seller_with_a_gstin_but_no_address_is_incomplete_not_unregistered(mem):
    invoices.save_seller({"gstin": "27AAAAA0000A1Z5", "state": "27"})
    got = invoices.readiness()
    assert got == {"complete": False, "missing": ["legal name", "address"], "gst": True}


# ---------- R7M-002: the US brief, one weekday and one zone ----------
def test_a_us_brief_names_the_weekday_of_its_date_and_stamps_new_york_time_in_the_email():
    text = "U.S. equity indices were mixed on Tuesday, with the S&P 500 slipping 0.47% to 7,765.36."
    assert write.own_weekday(text, {"day": "2026-10-08", "weekly": False}) == text.replace("Tuesday", "Thursday")
    # "as of 9 Oct 2026, 02:04 IST" in the email beside "16:34 ET" on the page, for the same moment
    assert write.as_of("2026-10-09T02:04:00+05:30", "US") == "8 Oct 2026, 16:34 ET"
    assert write.as_of("2026-10-08T16:16:00+05:30", "IN") == "8 Oct 2026, 16:16 IST"
    assert write.as_of("2026-10-08T16:16:00+05:30") == "8 Oct 2026, 16:16 IST"
    issue = {"id": "market.US.2026-10-08", "kind": "market", "region": "US", "day": "2026-10-08", "weekly": False, "subject": "Market Brief US, Thu 8 Oct",
             "summary": "x", "sections": [], "indices": [], "at": "2026-10-09T02:04+05:30"}
    html, plain = write.render(issue)
    assert "Prices and numbers as of 8 Oct 2026, 16:34 ET" in plain and "IST" not in plain
    assert "16:34 ET" in html


def test_stored_us_briefs_are_stamped_again_in_new_york_time_once(w):
    issue = job.make_issue({"kind": "market", "region": "US", "day": "2026-10-08", "weekly": False,
                            "indices": [{"name": "S&P 500", "price": 7765.36, "change_pct": -0.47}]}, "US")
    issue["at"] = "2026-10-09T02:04+05:30"
    issue["html"], issue["text"] = write.render(issue)
    issue["text"] = issue["text"].replace("8 Oct 2026, 16:34 ET", "9 Oct 2026, 02:04 IST")          # as it was stored before the fix
    job.save(issue)
    assert job.repair_us_stamp() == 1
    assert "as of 8 Oct 2026, 16:34 ET" in job.load(issue["id"])["text"]
    assert job.repair_us_stamp() == 0


# ---------- R7M-003: a currency with no rate ----------
def test_a_currency_with_no_rate_is_hidden_from_visitors_and_flagged_in_admin(mem):
    mem[pricing.RATES] = json.dumps({"rates": {"USD": 96.78}, "errors": ["SAR: no rate", "NOK: no rate", "QAR: no rate"]})
    t = pricing.table()
    assert t["NOK"]["no_rate"] and t["NOK"]["basic"] == 64                      # only the built-in default
    assert not t["SAR"]["no_rate"] and t["SAR"]["basic"] == 27 and t["SAR"]["pro"] == 77        # through the dollar's peg
    assert not t["QAR"]["no_rate"] and not t["USD"]["no_rate"] and not t["INR"]["no_rate"]
    pub = pricing.public()
    assert "NOK" not in pub["currencies"] and "NO" not in pub["countries"]      # a Norwegian visitor sees dollars
    assert pub["currencies"]["SAR"]["basic"] == 27 and pub["countries"]["SA"] == "SAR"
    assert "no_rate" not in pub["currencies"]["USD"]
    pricing.save({"NOK": {"basic": 300, "pro": 900}})                           # a price the owner typed is the owner's
    assert pricing.public()["currencies"]["NOK"]["basic"] == 300 and pricing.public()["countries"]["NO"] == "NOK"


def test_before_any_rate_is_read_only_the_fixed_prices_are_shown(mem):
    assert set(pricing.public()["currencies"]) == {"INR", "USD", "EUR", "GBP"}
    assert pricing.public()["countries"]["DE"] == "EUR" and "JP" not in pricing.public()["countries"]


def test_admin_prices_say_which_currencies_have_no_rate(w, mem):
    mem[pricing.RATES] = json.dumps({"at": "2026-10-09T00:00:00+00:00", "rates": {"USD": 96.78}, "errors": ["NOK: no rate", "AUD: down"]})
    rows = w["client"].get("/admin/prices", headers=ADMIN).json()
    assert rows["currencies"]["NOK"]["no_rate"] is True and rows["currencies"]["SAR"]["no_rate"] is False


# ---------- R7M-004: the unsubscribe page, the one-click header ----------
def test_the_unsubscribe_page_has_the_sites_look_and_points_at_settings(w):
    c = w["client"]
    t = mail_tokens.make("u-pro", "unsubscribe", "market_in")
    r = c.get("/unsubscribe", params={"t": t})
    assert r.status_code == 200 and "Unsubscribe from the India market email?" in r.text and "<form method=post" in r.text
    for look in ("<style>", 'class="brand"', "--paper:#F5F1E8", "prefers-color-scheme:dark", '"Fraunces"', 'class="btn"', "noindex"):
        assert look in r.text, look
    assert "/settings#notifications" in r.text and "/account" not in r.text      # the real path, not "Account"
    assert newsletter_prefs.get("u-pro")["market_in"] == "off"                  # opening the link changed nothing (it was off already)
    done = c.post("/unsubscribe", params={"t": t, "page": 1})
    assert "Settings → Notifications" in done.text and "/settings#notifications" in done.text and "Account" not in done.text
    bad = c.get("/unsubscribe", params={"t": "nonsense"})
    assert bad.status_code == 400 and "Settings → Notifications" in bad.text and "<style>" in bad.text
    assert c.get("/email/confirm", params={"t": "nonsense"}).status_code == 400
    assert "Settings → Notifications" in c.post("/email/confirm", params={"t": "nonsense"}).text


def test_a_brief_email_carries_the_one_click_header_on_the_sites_own_address(w, monkeypatch):
    monkeypatch.setattr(settings, "PUBLIC_SITE_URL", "https://stratlab.studio")
    real_send = alerts.send_email
    got = []
    monkeypatch.setattr(alerts, "email_ready", lambda: True)
    monkeypatch.setattr(alerts, "send_email", lambda to, subject, text, html=None, headers=None: got.append(headers))
    db.get_profile("u-pro", "pro@example.com")
    db.update_profile("u-pro", alert_email="pro@example.com")
    db.set_setting(alerts.CONFIRMED + "u-pro", "pro@example.com")
    issue = job.make_issue({"kind": "market", "region": "IN", "day": "2026-10-01", "weekly": False,
                            "indices": [{"name": "NIFTY 50", "price": 24812.3, "change_pct": 0.42}]}, "IN")
    assert job.deliver(db.get_profile("u-pro"), issue, "market_in")
    headers = got[0]
    assert headers["List-Unsubscribe"].startswith("<https://stratlab.studio/unsubscribe?t=") and "railway" not in headers["List-Unsubscribe"]
    assert headers["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    # the sender hands both to Brevo as custom headers, to replace its own
    sent = {}
    monkeypatch.setattr(settings, "BREVO_API_KEY", "key")
    monkeypatch.setattr(settings, "ALERT_FROM_EMAIL", "hello@stratlab.studio")
    monkeypatch.setattr(alerts.httpx, "post", lambda url, **kw: sent.update(kw) or SimpleNamespace(status_code=201))
    real_send("pro@example.com", "Subject", "Text", html="<p>x</p>", headers=headers)
    assert sent["json"]["headers"]["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    assert sent["json"]["headers"]["List-Unsubscribe"] == headers["List-Unsubscribe"]
    assert "railway" not in json.dumps(sent["json"]["headers"])


def test_the_brief_previews_show_the_real_stored_issue_which_is_why_the_label_no_longer_says_made_up(w):
    from app import email_previews
    issue = job.save(job.make_issue({"kind": "market", "region": "IN", "day": "2026-10-08", "weekly": False,
                                     "indices": [{"name": "NIFTY 50", "price": 22231.8, "change_pct": -1.64}]}, "IN"))
    d = email_previews.describe("market_in", True)
    assert d["subject"] == issue["subject"] and "22,231.80" in d["text"]
    assert "/unsubscribe?t=" + email_kit.PREVIEW_TOKEN in d["text"]


# ---------- R7M-005: the newsletters job, who got what ----------
def market(region="IN", weekly=False, day=THU):
    return {"kind": "market", "region": region, "day": day.isoformat(), "weekly": weekly, "since": "2026-09-30",
            "indices": [{"name": "NIFTY 50", "price": 24812.3, "change_pct": 0.42}], "rotation": [],
            "headlines": [{"headline": "Nifty ends higher as banks gain", "url": "https://example.com/a"}]}


def reader(uid, email, plan="pro", confirmed=True, **choices):
    db.get_profile(uid, email)
    db.update_profile(uid, plan=plan, plan_status="active", alert_email=email)
    newsletter_prefs.set(uid, **choices)
    if confirmed:
        db.set_setting(alerts.CONFIRMED + uid, email)


@pytest.fixture
def outbox(monkeypatch, w):
    sent = []
    monkeypatch.setattr(alerts, "email_ready", lambda: True)
    monkeypatch.setattr(alerts, "send_email", lambda to, subject, text, html=None, headers=None: sent.append(to))
    monkeypatch.setattr(content, "market_facts", lambda region, day, weekly=False: market(region, weekly, day))
    monkeypatch.setattr(content, "stock_facts", lambda *a, **k: {"changed": False})
    return sent


def test_a_reader_confirmed_after_the_send_gets_that_days_brief_at_the_next_check(outbox):
    reader("u-pro", "pro@example.com", confirmed=False, market_in="daily")        # the address "Confirmed" only later in the day
    reader("u-basic", "basic@example.com", plan="basic", market_in="daily")
    j = job.Job("newsletters")
    assert j.tick(AFTER_IN_CLOSE) == 1 and outbox == ["basic@example.com"]
    rep = j.status["regions"]["IN"]
    assert (rep["readers"], rep["sent"], rep["skipped"]) == (2, 1, {"email address not confirmed": 1})
    assert j.tick(AFTER_IN_CLOSE + FIVE) == 0                                    # still unconfirmed: nothing, and no noise
    db.set_setting(alerts.CONFIRMED + "u-pro", "pro@example.com")
    restarted = job.Job("newsletters")                                           # a restart in between changes nothing
    assert restarted.tick(AFTER_IN_CLOSE + 2 * FIVE) == 1
    assert outbox == ["basic@example.com", "pro@example.com"]
    rep = restarted.status["regions"]["IN"]
    assert (rep["sent"], rep["skipped"]) == (2, {})
    assert restarted.tick(AFTER_IN_CLOSE + 3 * FIVE) == 0 and job.Job().tick(AFTER_IN_CLOSE + 4 * FIVE) == 0
    assert outbox == ["basic@example.com", "pro@example.com"]                    # each reader once


def test_one_readers_failure_never_stops_the_others_and_is_tried_again(outbox, monkeypatch):
    reader("u-basic", "basic@example.com", plan="basic", market_in="daily")      # first in line, and the database drops the call
    reader("u-pro", "pro@example.com", market_in="daily")
    real = db.get_profile

    def flaky(uid, email=None):
        if uid == "u-basic":
            raise RuntimeError("Server disconnected")
        return real(uid, email)
    monkeypatch.setattr(db, "get_profile", flaky)
    j = job.Job("newsletters")
    assert j.tick(AFTER_IN_CLOSE) == 1 and outbox == ["pro@example.com"]          # the old loop ended at the first failure, for good
    assert j.status["regions"]["IN"]["skipped"] == {"the account couldn't be read": 1}
    monkeypatch.setattr(db, "get_profile", real)
    assert j.tick(AFTER_IN_CLOSE + FIVE) == 1 and outbox == ["pro@example.com", "basic@example.com"]
    assert j.status["regions"]["IN"]["skipped"] == {}


def test_an_email_that_fails_is_recorded_and_tried_again(outbox, monkeypatch):
    reader("u-pro", "pro@example.com", market_in="daily")
    down = {"on": True}

    def send(to, subject, text, html=None, headers=None):
        if down["on"]:
            raise RuntimeError("Brevo refused the email (401).")
        outbox.append(to)
    monkeypatch.setattr(alerts, "send_email", send)
    j = job.Job("newsletters")
    assert j.tick(AFTER_IN_CLOSE) == 0
    assert j.status["regions"]["IN"]["skipped"] == {"the email failed to send": 1}
    down["on"] = False
    assert j.tick(AFTER_IN_CLOSE + FIVE) == 1 and outbox == ["pro@example.com"]


def test_a_brief_sent_before_the_ledger_existed_is_never_sent_again(outbox):
    reader("u-pro", "pro@example.com", market_in="daily")
    job.build_market("IN", THU)                                                  # stored, and marked as run, but no ledger (an older deploy)
    db.set_setting("newsjob:market-IN", THU.isoformat())
    assert job.Job().tick(AFTER_IN_CLOSE) == 0 and outbox == []


def test_a_reader_who_chose_the_other_edition_is_counted_apart_not_as_skipped(outbox):
    reader("u-pro", "pro@example.com", market_in="weekly")
    reader("u-basic", "basic@example.com", plan="basic", market_in="daily")
    j = job.Job("newsletters")
    j.tick(AFTER_IN_CLOSE)
    rep = j.status["regions"]["IN"]
    assert (rep["readers"], rep["sent"], rep["other_edition"], rep["skipped"]) == (2, 1, 1, {})


def test_admin_data_and_jobs_has_a_newsletters_row_with_who_got_what(w, outbox, monkeypatch):
    monkeypatch.setattr(main.newsletter_job, "last", {})
    monkeypatch.setattr(main.newsletter_job, "status", job_status.Status("newsletters", {"last_run": None, "sent": 0, "last_error": None}))
    reader("u-pro", "pro@example.com", confirmed=False, market_in="daily")
    reader("u-basic", "basic@example.com", plan="basic", market_in="daily")
    main.newsletter_job.tick(AFTER_IN_CLOSE)
    rows = {r["id"]: r for r in w["client"].get("/admin/jobs", headers=ADMIN).json()["jobs"]}
    row = rows["newsletters"]
    assert row["name"] == "Newsletters" and row["last_run"] and row["state"] == "ok" and row["error"] is None
    assert any(x.startswith("India, 2026-10-01: sent to 1 of 2 readers") and "1 email address not confirmed" in x for x in row["log"]), row["log"]
    assert "India 4:15 PM IST" in row["schedule"]


# ---------- R7M-006: the weekly email counts the last 7 days ----------
def test_the_weekly_email_counts_seven_days_not_the_month(w, monkeypatch):
    now = datetime(2026, 10, 12, 9, 0, tzinfo=IST)                                # a Monday: 11 days into the month
    _week(w, monkeypatch, now)
    w["db"].tables["usage_events"].append({"user_id": "b", "kind": "backtest", "created_at": (now - timedelta(days=8)).astimezone(timezone.utc).isoformat()})
    w["db"].tables["usage_events"].append({"user_id": "b", "kind": "ai", "created_at": (now - timedelta(days=9)).astimezone(timezone.utc).isoformat()})
    subject, text = main.weekly_summary(now)
    assert "- 3 experiments run, 1 AI build in the last 7 days" in text
    month = main.admin.stats((now.replace(day=1, hour=0, minute=0)).astimezone(timezone.utc).isoformat())
    assert (month["experiments_month"], month["ai_month"]) == (4, 2)              # this month's, on Overview, are bigger


# ---------- R7M-008: the AI providers tile counts what worked last ----------
@pytest.fixture
def ai_clean(monkeypatch):
    for p in PROVIDERS.values():
        monkeypatch.setattr(settings, p.key_env, "")
        if p.name != "anthropic":
            monkeypatch.setattr(settings, p.model_env, "auto")
    monkeypatch.setattr(settings, "CLOUDFLARE_ACCOUNT_ID", "")
    monkeypatch.setattr(settings, "AI_PROVIDERS", "auto")
    monkeypatch.setattr(settings, "AI_PROVIDERS_RESEARCH", "auto")
    monkeypatch.setattr(P, "_sleep", lambda s: None)


def _keys(monkeypatch, *names):
    for n in names:
        monkeypatch.setattr(settings, PROVIDERS[n].key_env, "k-" + n)


def _chat():
    return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({"ok": True})}, "finish_reason": "stop"}]})


def _result(name):
    return next(p for p in P.health() if p["name"] == name)["result"]


def test_a_provider_is_working_out_of_credit_failing_or_untried_by_its_last_real_result(ai_clean, monkeypatch):
    _keys(monkeypatch, "groq", "vercel", "github", "mistral")
    assert [_result(n) for n in ("groq", "vercel", "github", "mistral", "cerebras")] == ["untested"] * 4 + [None]     # a key is not a result
    ok = httpx.MockTransport(lambda req: _chat())
    P.complete("s", "t", transport=ok)                                               # whichever answers first
    answered = next(n for n in ("groq", "vercel", "github", "mistral") if _result(n) == "working")
    assert answered
    # the account needs a card (Vercel's 403): out of credit, not "answering"
    P.R.status("vercel").last_error = "the account needs a payment method on file (403: card)"
    P.R.status("vercel").last_error_at = 9e12
    P.R.status("vercel").last_error_kind = "auth"
    assert _result("vercel") == "quota"
    # empty replies (GitHub Models): failing
    gh = P.R.status("github")
    gh.last_error, gh.last_error_at, gh.last_error_kind, gh.last_ok = "answered 200 without a chat reply (text/html)", 9e12, "bad_reply", None
    assert _result("github") == "failed"
    # a short rate limit after an answer still counts as working
    mi = P.R.status("mistral")
    mi.last_ok, mi.last_error, mi.last_error_at, mi.last_error_kind = 8e12, "rate limited (429)", 9e12, "rate"
    assert _result("mistral") == "working"
    # used-up free credit
    q = P.R.status("groq")
    q.quota, q.last_error, q.last_error_at, q.last_error_kind, q.cooldown_until = True, "the free credit is used up", 9e12, "credit", 9e15
    assert _result("groq") == "quota"


def test_cloudflare_models_listed_by_uuid_are_shown_by_name(ai_clean, monkeypatch):
    listing = {"success": True, "result": [
        {"id": "02c16efa-29f5-4304-8e6c-3d188889f875", "name": "@cf/meta/llama-3.3-70b-instruct-fp8-fast"},
        {"id": "a1b2c3d4-0000-4000-8000-000000000001", "name": "@cf/openai/gpt-oss-120b"}]}
    assert parse_aliases(listing) == {"02c16efa-29f5-4304-8e6c-3d188889f875": "@cf/meta/llama-3.3-70b-instruct-fp8-fast",
                                      "a1b2c3d4-0000-4000-8000-000000000001": "@cf/openai/gpt-oss-120b"}
    assert parse_aliases({"data": [{"id": "gpt-4o"}]}) == {}
    _keys(monkeypatch, "cloudflare")
    monkeypatch.setattr(settings, "CLOUDFLARE_ACCOUNT_ID", "acct")
    named, unnamed, twin = "3b2f9d52-1111-4222-8333-444444444444", "ffffffff-1111-4222-8333-444444444444", "02c16efa-29f5-4304-8e6c-3d188889f875"
    st = R.status("cloudflare")
    st.aliases = {named: "@cf/mistral/mistral-small-3.1-24b-instruct", twin: "@cf/meta/llama-3.3-70b-instruct-fp8-fast"}
    for m in (named, unnamed, twin):
        R.stats("cloudflare", m).probe_tries = 1
    view = next(p for p in P.admin_view()["providers"] if p["name"] == "cloudflare")
    shown = {m["id"]: m["name"] for m in view["models"]}
    assert shown[named] == "@cf/mistral/mistral-small-3.1-24b-instruct"          # by name, where one is known
    assert shown[unnamed] == "unnamed model (ffffffff…)"                         # never the whole UUID
    assert twin not in shown                                                     # the same model as one already listed by name
    assert all(not R._UUID.match(m["name"]) for m in view["models"])


# ---------- R7M-009 / R7M-011: Zerodha ----------
def test_holdings_says_when_zerodha_is_connected_and_returned_nothing(w, monkeypatch):
    from cryptography.fernet import Fernet
    from app.connect import state, vault
    monkeypatch.setattr(settings, "CONNECT_SECRET_KEY", Fernet.generate_key().decode())
    c = w["client"]
    assert c.get("/holdings", headers=ADMIN).json()["zerodha"] is None            # not connected: the page keeps its ordinary words
    state.update("u-admin", "kite", token=vault.seal("T"), day="2020-01-01", refreshed_at="2026-10-09T00:41:00+00:00", count=0, status="ok")
    got = c.get("/holdings", headers=ADMIN).json()
    assert got["rows"] == [] and got["zerodha"]["count"] == 0 and got["zerodha"]["read_at"] == "2026-10-09T00:41:00+00:00"
    assert c.get("/holdings", headers=PRO).json()["zerodha"] is None


def test_the_kite_token_alert_names_the_zone_and_the_actual_button():
    from app.kite_service import KiteService
    seen = []
    k = KiteService.__new__(KiteService)
    k.access_token, k.token_day, k.invalid_reason, k.on_invalid = "T", datetime.now(IST).date().isoformat(), None, seen.append
    k.ready = lambda: True
    k._token_rejected(RuntimeError("TokenException"))
    reason = k.invalid_reason
    assert re.search(r"Kite token at \d\d:\d\d IST\.", reason)
    assert 'Admin → Data and jobs' in reason and '"Run the automatic login now"' in reason
    assert "another bot or script" in reason and seen == [reason]


# ---------- R7M-012: a leftover snapshot with nothing entered ----------
def test_a_leftover_snapshot_shows_with_nothing_entered_and_can_be_removed(w):
    uid, c = "u-pro", w["client"]
    db.set_setting(money_networth.LOG + uid, json.dumps([{"d": "2026-10-08", "net": 243481.78, "assets": 243481.78, "liabilities": 0.0, "why": "change"}]))
    page = c.get("/money/net-worth", headers=PRO).json()
    assert page["totals"]["net"] == 0 and page["assets"] == [] and page["history_allowed"]
    assert [h["d"] for h in page["history"]] == ["2026-10-08"] and page["history_count"] == 1
    left = c.delete("/money/net-worth/history/2026-10-08", headers=PRO).json()
    assert left == {"history": [], "history_count": 0}
    assert c.get("/money/net-worth", headers=PRO).json()["history"] == []
