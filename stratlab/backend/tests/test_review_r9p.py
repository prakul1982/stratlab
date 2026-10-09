"""Round 9 review, plan views, payments and emails (R9P-001 to 009, and the R7M-008 leftover): one unsubscribe of our own on
every email that has an unsubscribe, the My Stocks closes, the receipt preview a real payment would match, the weekly
email's error line in Admin's words, the AI caps on Account, a Net worth and Mutual funds page that doesn't wait on the
public NAV file, and plain-text headline lists without 500-character links."""
import threading
import time
from datetime import date, datetime, timedelta, timezone

import httpx
import pytest

from app import main  # noqa: F401, I001  (first: the app loads its modules in a fixed order)
from app import alerts, db, email_kit as kit, email_previews as P, lifecycle, mail_tokens, money_mf_nav as N, money_networth, official_close
from app.config import settings
from tests import world as W
from tests.fake_db import headers
from tests.test_review_r8b import _bars, _ist, _quotes, mem  # noqa: F401  (mem: the settings table in memory)

IST = timezone(timedelta(hours=5, minutes=30))


@pytest.fixture
def brevo(monkeypatch):
    """Email over Brevo's API, captured; the site's own address for links."""
    for k in ("RESEND_API_KEY", "SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD"):
        monkeypatch.setattr(settings, k, "")
    monkeypatch.setattr(settings, "BREVO_API_KEY", "xkeysib-test")
    monkeypatch.setattr(settings, "ALERT_FROM_EMAIL", "hello@stratlab.studio")
    monkeypatch.setattr(settings, "PUBLIC_SITE_URL", "https://stratlab.studio")
    sent = []

    def post(url, **kw):
        sent.append(kw["json"])
        return httpx.Response(201, json={"messageId": "x"})
    monkeypatch.setattr(httpx, "post", post)
    return sent


# ---------- R9P-001: our own List-Unsubscribe on every email that has an unsubscribe ----------
def test_an_alert_email_carries_our_own_unsubscribe_headers_and_link(brevo):
    alerts.send_message("a@example.com", "StratLab: RELIANCE crossed ₹2,900", "RELIANCE crossed above ₹2,900.", "/alerts",
                        "Price and stock alerts", "You get this because you set these alerts on StratLab.", uid="u-1")
    msg, = brevo
    h = msg["headers"]
    assert h["List-Unsubscribe"].startswith("<https://stratlab.studio/unsubscribe?t=") and h["List-Unsubscribe"].endswith(">")
    assert h["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    token = h["List-Unsubscribe"][1:-1].split("t=", 1)[1]
    assert mail_tokens.read(token, "unsubscribe") == ("u-1", alerts.ALERT_EMAILS)           # signed, for this reader and type
    assert f"https://stratlab.studio/unsubscribe?t={token}" in msg["htmlContent"] and "Turn off alert emails" in msg["htmlContent"]
    assert f"Turn off alert emails: https://stratlab.studio/unsubscribe?t={token}" in msg["textContent"]
    assert "sendibt" not in msg["htmlContent"] + msg["textContent"]


def test_a_purely_transactional_email_sends_no_unsubscribe_header(brevo):
    # the test email, a confirmation, a receipt: nothing to unsubscribe from (Brevo may still add its own to these: that
    # is an account setting, not something a message can switch off)
    subject, html, text = P.test_email()
    alerts.send_email("a@example.com", subject, text, html=html)
    assert "headers" not in brevo[0]
    html, text, headers_ = kit.finish(html, text, "u-1", None)
    assert headers_ is None


def test_the_weekly_summary_and_the_test_alert_go_out_with_the_header(brevo, monkeypatch):
    monkeypatch.setattr(alerts, "email_confirmed", lambda p: True)
    profile = {"id": "u-owner", "alert_email": "owner@example.com"}
    sent, failed = alerts.test(profile)                                            # "Settings → Notifications → Send a test"
    assert sent == ["email"] and not failed
    assert brevo[0]["headers"]["List-Unsubscribe"].startswith("<https://stratlab.studio/unsubscribe?t=")
    brevo.clear()
    alerts.notify(profile, "StratLab weekly: 4 new users, 95 things to look at", "Users\n- 4 new this week", background=False, url="/admin")
    assert brevo[0]["headers"]["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"


def test_lifecycle_tips_and_the_admin_test_of_them_carry_it_but_a_receipt_does_not(brevo, monkeypatch):
    monkeypatch.setattr(db, "get_setting", lambda k: None)
    lifecycle.send_test("welcome", {"id": "u-1", "email": "a@example.com"}, "owner@example.com")
    kind = next(k for k, (_, tx) in lifecycle.EMAILS.items() if not tx)
    brevo.clear()
    lifecycle.send_test(kind, {"id": "u-1", "email": "a@example.com"}, "owner@example.com")
    assert brevo[0]["headers"]["List-Unsubscribe"].startswith("<https://stratlab.studio/unsubscribe?t=")
    brevo.clear()
    lifecycle.send_test("receipt", {"id": "u-1", "email": "a@example.com"}, "owner@example.com")
    assert "headers" not in brevo[0]


def test_unsubscribing_from_alert_emails_stops_them_and_saving_an_address_turns_them_back_on(monkeypatch):
    w = W.build(monkeypatch)
    try:
        c = w["client"]
        t = mail_tokens.make("u-pro", "unsubscribe", alerts.ALERT_EMAILS)
        assert c.get("/unsubscribe", params={"t": t}).status_code == 200
        assert alerts.alert_emails_on("u-pro")                                  # opening the link (a mail scanner) changes nothing
        r = c.post("/unsubscribe", params={"t": t})                              # the mail app's one-click button
        assert r.status_code == 200 and not alerts.alert_emails_on("u-pro")
        monkeypatch.setattr(alerts, "email_ready", lambda: True)
        monkeypatch.setattr(alerts, "email_confirmed", lambda p: True)
        profile = {"id": "u-pro", "alert_email": "pro@example.com"}
        assert [ch for ch, _ in alerts.jobs_for(profile, "S", "T")] == []        # no email any more
        assert [ch for ch, _ in alerts.jobs_for(profile, "S", "T", force_email=True)] == ["email"]   # a test they ask for still goes
        assert [ch for ch, _ in alerts.jobs_for({"id": "u-other", "alert_email": "o@example.com"}, "S", "T")] == ["email"]
        me = c.get("/me", headers=headers("pro-token")).json()
        assert me["alerts"]["email_off"] is True
        c.put("/me/alerts", headers=headers("pro-token"), json={"alerts_enabled": False, "alert_email": "pro@example.com"})
        assert alerts.alert_emails_on("u-pro")
    finally:
        w["close"]()


def test_every_email_type_with_an_unsubscribe_shows_one_in_its_preview():
    for kind in P.registry():
        d = P.describe(kind, True)
        has_link = "unsubscribe?t=preview" in d["html"] and "unsubscribe?t=preview" in d["text"]
        assert has_link == d["unsubscribe"], kind
    for kind in ("stock_alert", "scan_alert", "result_alert", "events", "fo_changes", "money_calendar", "admin_alert"):
        assert P.describe(kind)["unsubscribe"] is True, kind
    for kind in ("test", "confirm", "lifecycle_receipt"):
        assert P.describe(kind)["unsubscribe"] is False, kind


# ---------- R9P-002: My Stocks takes the official closes ----------
def test_my_stocks_email_shows_the_official_close_and_its_move(monkeypatch, mem):
    from app.newsletter import content
    official_close.save("2026-10-08", {"TCS": 2076.0})
    official_close.setup(None, lambda syms: {}, force=True, all_quotes_fn=lambda: _quotes())
    bars = official_close.history_close(_bars(), "TCS", now=_ist("2026-10-09", "16:19"))       # 2,171.50 before the auction
    monkeypatch.setattr(content, "_symbol_data", lambda r, s, d: {"bars": bars, "filings": [], "news": []})
    monkeypatch.setattr(content, "surveillance_lines", lambda s, since: None)
    monkeypatch.setattr(content.deals, "recent_for", lambda s, since: [])
    row = content.stock_row("IN", "TCS", date(2026, 10, 9), False, "2026-10-08T16:19")
    assert row["price"] == 2156.0 and row["change_pct"] == 3.85                    # the app's own "Last close ₹2,156.00 +3.85%"
    day = "2026-10-09"
    issue = P._issue({"kind": "my_stocks", "uid": "sample", "day": day, "weekly": False, "since": "2026-10-08", "stocks": [row],
                      "unchanged": [], "results": [], "actions": [], "paper": []})
    assert "2,156" in issue["text"] and "3.85" in issue["text"] and "2,171" not in issue["text"]


# ---------- R9P-003: the receipt preview is what a real payment gets ----------
def test_the_receipt_preview_is_the_plain_invoice_while_the_seller_has_no_gstin(monkeypatch):
    from app import invoices
    store: dict = {}
    monkeypatch.setattr(db, "get_setting", lambda k: store.get(k))
    monkeypatch.setattr(db, "set_setting", lambda k, v: store.__setitem__(k, v))
    monkeypatch.setattr(invoices, "seller", lambda: {**{f: "" for f in invoices.FIELDS}, "prefix": "SL"})        # nothing filled in
    inv = lifecycle.sample_invoice(datetime.now(timezone.utc))
    assert inv["taxes"] == [] and inv["supply"] == "Unregistered" and inv["seller"]["gstin"] == ""
    # the invoice a real payment would make for the same seller says the same
    real = invoices.make({"id": "pay_r9p", "amount": 199900, "currency": "INR", "created_at": 1791331200}, {"id": "u-x", "email": "a@example.com"},
                         "pro", "month")
    assert (real["taxes"], real["supply"], real["note"]) == (inv["taxes"], inv["supply"], inv["note"])
    assert real["item"]["taxable"] == inv["item"]["taxable"] == 1999.0
    text = P.describe("lifecycle_receipt", True)["text"]
    assert "Not registered under GST" in text and "no GST charged" in text
    assert "CGST" not in text and "SGST" not in text and "GSTIN 27" not in text and "27ABCDE1234F1Z5" not in text
    assert "₹1,999.00" in text


def test_the_receipt_preview_has_gst_lines_once_a_gstin_is_set(monkeypatch):
    from app import invoices
    monkeypatch.setattr(invoices, "seller", lambda: {**{f: "" for f in invoices.FIELDS}, "legal_name": "StratLab Labs LLP", "state": "27",
                                                     "gstin": "27ABCDE1234F1Z5", "prefix": "SL"})
    text = P.describe("lifecycle_receipt", True)["text"]
    assert "CGST 9%" in text and "SGST 9%" in text and "GSTIN 27ABCDE1234F1Z5" in text


# ---------- R9P-004: the weekly email's error line, in Admin's words ----------
def test_the_weekly_error_line_uses_admins_wording_and_numbers(monkeypatch):
    from app import weekly
    started = datetime(2026, 10, 9, 6, 0, tzinfo=IST)
    monkeypatch.setattr(main, "SERVER_STARTED_AT", started.isoformat())
    kept = [{"ref": f"K{i}", "at": (started - timedelta(hours=1 + i)).isoformat()} for i in range(23)]
    monkeypatch.setattr(main, "RECENT_ERRORS", kept)
    assert main.error_counts() == {"errors_since_restart": 0, "errors_before_restart": 23}
    # the same split as Admin's: one error since the start joins the "since the last restart" count
    main.RECENT_ERRORS.append({"ref": "N1", "at": (started + timedelta(minutes=5)).isoformat()})
    assert main.error_counts() == {"errors_since_restart": 1, "errors_before_restart": 23}
    facts = {"stats": {"users": 9, "new": 4, "paid": {}, "paying": {}, "given": {"pro": 6}, "experiments": 14, "ai": 16},
             "checks": [], "audits": {}, "errors": 21, "errors_since_restart": 0, "errors_before_restart": 23, "admin_url": None}
    _, text = weekly.summary(datetime(2026, 10, 12, 9, 0, tzinfo=IST), facts)
    assert "- 21 errors this week (0 since the last restart, 23 kept from before it)" in text
    assert "listed on Admin" not in text
    facts.update(errors_since_restart=2, errors_before_restart=0, errors=2)
    assert "- 2 errors this week (2 since the last restart)" in weekly.summary(datetime(2026, 10, 12, 9, 0, tzinfo=IST), facts)[1]


# ---------- R9P-005: Account says the viewed plan's AI caps ----------
def test_me_gives_the_viewed_plans_ai_caps_to_the_owner(monkeypatch):
    w = W.build(monkeypatch)
    try:
        c = w["client"]

        def usage(view):
            h = headers("admin-token") | ({"X-View-As": view} if view else {})
            return c.get("/me", headers=h).json()["usage"]
        free, basic, pro = usage("free"), usage("basic"), usage("pro")
        assert free["ai_reads_limit"] is None and free["ai_reads_cap_for"] == "admin"                  # not enforced for the owner
        assert free["ai_reads_plan_limit"] == settings.RESEARCH_AI_PER_DAY == basic["ai_reads_plan_limit"]
        assert pro["ai_reads_plan_limit"] is None
        assert free["ai_builds_per_day"] is None and basic["ai_builds_per_day"] is None
        assert pro["ai_builds_per_day"] == main.AI_BUILDS_PER_DAY == 200                              # the Plans card's "up to 200 a day"
        assert usage(None)["ai_builds_per_day"] == 200                                                 # the owner's own Pro
    finally:
        w["close"]()


# ---------- R9P-008: Net worth and Mutual funds don't wait on the public NAV file ----------
DAILY = "Scheme Code;ISIN Div Payout/ISIN Growth;ISIN Div Reinvestment;Scheme Name;Net Asset Value;Date\n" + \
    "\n".join(f"Open Ended Schemes(Equity Scheme - Flexi Cap Fund)\nExample Mutual Fund\n9{i:05d};INF{i:05d}X01AA{i % 10};;Example Fund {i} Direct Growth;{10 + i}.5;09-Oct-2026"
              for i in range(60))


def test_a_stale_nav_copy_is_used_at_once_and_read_again_in_the_background(monkeypatch):
    N.forget()
    release = threading.Event()
    reads = []

    def slow_fetch(url):
        reads.append(url)
        release.wait(10)                                                      # the public file answering slowly (it took 16 to 21 s)
        return DAILY
    monkeypatch.setattr(N, "fetch_text", slow_fetch)
    monkeypatch.setattr(db, "get_setting", lambda k: None)
    monkeypatch.setattr(db, "set_setting", lambda k, v: None)
    old = N.parse(DAILY)
    N._daily.update(data={**old, "read_at": time.time() - N.MAX_AGE - 60}, at=time.time() - N.MAX_AGE - 60, tried=0.0)
    began = time.monotonic()
    got = N.daily()                                                           # older than MAX_AGE: used as it is
    assert time.monotonic() - began < 2 and len(got["schemes"]) == 60
    assert N.daily() is not None and time.monotonic() - began < 2             # and again, while the read is still running
    release.set()
    t = N._daily["thread"]
    t.join(5)
    assert reads == [N.DAILY_URL] and N._daily["at"] > time.time() - 30       # one background read, which refreshed the copy
    N.forget()


def test_with_no_copy_at_all_a_page_waits_a_bounded_time_not_for_the_whole_read(monkeypatch):
    N.forget()
    release = threading.Event()
    monkeypatch.setattr(N, "fetch_text", lambda url: (release.wait(10), DAILY)[1])
    monkeypatch.setattr(N, "COLD_WAIT", 0.3)
    monkeypatch.setattr(db, "get_setting", lambda k: None)
    monkeypatch.setattr(db, "set_setting", lambda k, v: None)
    began = time.monotonic()
    got = N.daily()
    assert time.monotonic() - began < 3 and got["schemes"] == {} and got["read_at"] is None
    release.set()
    N._daily["thread"].join(5)
    assert len(N.daily()["schemes"]) == 60                                    # the next visitor has it
    N.forget()


def test_a_failed_read_is_not_tried_on_every_visit(monkeypatch):
    N.forget()
    calls = []

    def down(url):
        calls.append(url)
        raise OSError("down")
    monkeypatch.setattr(N, "fetch_text", down)
    monkeypatch.setattr(db, "get_setting", lambda k: None)
    N.daily()
    N._daily["thread"].join(5)
    N.daily()
    N.daily()
    assert len(calls) == 1                                                    # then nothing until RETRY passes
    N.forget()


def test_net_worth_reads_holdings_funds_and_history_together(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    store: dict = {}
    monkeypatch.setattr(db, "get_setting", lambda k: store.get(k))
    monkeypatch.setattr(db, "set_setting", lambda k, v: store.__setitem__(k, v))
    meet = threading.Barrier(3)                                               # holdings, funds and the history must all be waiting at once
    seen = []

    def stocks_of(profile):
        meet.wait(5)
        seen.append("stocks")
        return None

    def mf_value(uid):
        meet.wait(5)
        seen.append("mf")
        return {"value": 0, "as_of": None, "link": None}

    def history(uid):
        meet.wait(5)
        seen.append("history")
        return []
    monkeypatch.setattr(money_networth, "mf_value", mf_value)
    monkeypatch.setattr(money_networth, "history", history)
    profile = {"id": "u-nw", "_plan": "pro"}
    app = FastAPI()
    app.include_router(money_networth.make_router(lambda: profile, stocks_of, money_networth.Prices(lambda: None, lambda c: None, lambda: 90.0),
                                                  lambda plan: None, lambda plan: True, lambda *a, **k: None))
    began = time.monotonic()
    r = TestClient(app).get("/money/net-worth")
    assert r.status_code == 200, r.text
    assert sorted(seen) == ["history", "mf", "stocks"] and time.monotonic() - began < 4


def test_the_pages_draw_their_shell_before_the_server_answers():
    import re
    from pathlib import Path
    root = Path(__file__).resolve().parents[2] / "frontend" / "src" / "pages" / "money"
    for page, label in (("NetWorthPage.tsx", "Adding up your net worth"), ("MutualFundsPage.tsx", "Opening your mutual funds")):
        src = (root / page).read_text()
        assert re.search(r"PageHeader", src) and f'Skeleton label="{label}"' in src, page      # header and a skeleton while it loads
        assert src.count("useEffect(() => { load(); }, [load]);") == 1, page                          # one question on opening, not a chain of them


# ---------- R9P-009: plain-text headline lists carry no 500-character links ----------
LONG = "https://news.google.com/rss/articles/" + "CBMi" + "x" * 480 + "?oc=5"


def test_the_plain_text_part_names_the_headline_and_its_publisher_not_a_wall_of_address():
    from app.newsletter import write
    facts = {"kind": "market", "region": "IN", "day": "2026-10-09", "weekly": False,
             "indices": [{"name": "NIFTY 50", "price": 22520.45, "change_pct": 1.3}],
             "headlines": [{"headline": "Sensex ends 879 points higher as IT stocks rally", "url": LONG, "source": "Economic Times"},
                           {"headline": "Rupee ends flat against the dollar", "url": "https://example.com/rupee", "source": None}]}
    issue = P._issue(facts)
    text = issue["text"]
    assert "Sensex ends 879 points higher as IT stocks rally (Economic Times)" in text
    assert "news.google.com" not in text and "CBMi" not in text and max(len(ln) for ln in text.splitlines()) < 200
    assert "(https://example.com/rupee)" in text                                       # a short address still prints
    assert issue["html"].count(LONG.replace("&", "&amp;")) >= 1 or "news.google.com/rss/articles/CBMi" in issue["html"]    # the link stays in the HTML
    assert write.banned("") is False


def test_the_kit_prints_an_address_in_plain_text_only_when_it_reads_as_one():
    assert kit.plain_url("https://stratlab.studio/research/IN/TCS") == "https://stratlab.studio/research/IN/TCS"
    assert kit.plain_url(LONG) is None and kit.plain_url("https://news.google.com/x") is None and kit.plain_url("javascript:alert(1)") is None
    block = kit.card("Headlines", [kit.Row("A story", url=LONG, source="Mint")])
    assert "A story (Mint)" in block.text and "news.google.com" not in block.text and LONG in block.html.replace("&amp;", "&")


def test_the_brief_keeps_a_headlines_publisher_but_never_an_aggregator_as_one():
    from app.newsletter import content
    assert content.publisher("Economic Times") == "Economic Times" and content.publisher("Google News") is None and content.publisher(None) is None
    rows = [{"headline": "Sensex ends 879 points higher as IT stocks rally", "url": LONG, "source": "Google News", "at": "2026-10-09T10:00:00+00:00"}]
    got = content.pick_headlines("IN", rows, "0000-00-00", "9999-99-99")
    assert got and got[0]["source"] is None and got[0]["url"] == LONG
