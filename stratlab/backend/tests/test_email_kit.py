"""The shared email design: every email type renders HTML and text, escapes outside text, keeps its one-click
unsubscribe, names no data provider, and the preview gallery is for the admin only."""
import re

import pytest

from app import main  # noqa: F401,E402  (the app imports its modules in a fixed order)
from app import alerts, email_kit as kit, email_previews as P
from app.newsletter import job, write
from tests import world as W

PROVIDERS = re.compile(r"kite|zerodha|yahoo|screener|finnhub|brevo|resend|supabase|razorpay|gemini|openai|anthropic", re.I)
KINDS = list(P.registry())


@pytest.fixture(scope="module")
def built():
    from app import main  # noqa: F401  (imports the app in its usual order)
    return {k: P.describe(k, True) for k in KINDS}


@pytest.mark.parametrize("kind", KINDS)
def test_every_email_type_renders_html_and_text(built, kind):
    d = built[kind]
    assert d["subject"] and d["html"].startswith("<!doctype html>") and d["text"].strip()
    assert 'name="color-scheme"' in d["html"] and "max-width:600px" in d["html"] and "StratLab" in d["html"]
    assert "Manage emails" in d["html"] and "/settings#notifications" in d["text"]
    assert "<img" not in d["html"] and "<script" not in d["html"]
    assert "<" not in d["text"].replace("<=", "")                     # the text version has no markup
    assert d["html"].count('class="btn-a"') == 1                       # one primary button


@pytest.mark.parametrize("kind", KINDS)
def test_no_data_provider_is_named_and_no_advice_words(built, kind):
    d = built[kind]
    assert not PROVIDERS.search(d["text"]) and not PROVIDERS.search(re.sub(r"<[^>]+>|<style>.*?</style>", " ", d["html"]))
    body = d["text"].replace(write.FOOTER, "")
    assert not write.banned(re.sub(r"(?i)facts, not (tax )?advice|not (investment|tax) advice", "", body)), kind


@pytest.mark.parametrize("kind", [k for k in KINDS if P.registry()[k][3]])
def test_unsubscribe_types_keep_their_placeholder_and_label(built, kind):
    # the kit's footer has the {unsubscribe_url} placeholder, which the previews swap for Manage emails
    name, group, build, unsub, tx = P.registry()[kind]
    assert not tx and ("Unsubscribe" in built[kind]["text"] or "Turn off" in built[kind]["text"] or "Stop" in built[kind]["text"])


def test_finish_fills_the_unsubscribe_link_and_gives_the_headers(monkeypatch):
    html, text = kit.render("T", [kit.para("x")], kit.Footer(why="why", unsubscribe="Unsubscribe from X"))
    assert kit.UNSUBSCRIBE in html and kit.UNSUBSCRIBE in text
    h, t, headers = kit.finish(html, text, "u-1", "market_in")
    assert kit.UNSUBSCRIBE not in h and kit.UNSUBSCRIBE not in t and "/unsubscribe?t=" in h and "/unsubscribe?t=" in t
    assert headers["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click" and headers["List-Unsubscribe"].startswith("<http")
    assert kit.finish(html, text, "u-1", None)[2] is None             # a receipt has none


def test_newsletter_delivery_sends_unsubscribe_link_and_headers(monkeypatch):
    sent = []
    monkeypatch.setattr(alerts, "send_email", lambda to, subject, body, html=None, headers=None: sent.append((to, body, html, headers)))
    monkeypatch.setattr(alerts, "email_ready", lambda: True)
    monkeypatch.setattr(alerts, "email_confirmed", lambda p: True)
    monkeypatch.setattr(job, "teaser", lambda *a: None)
    subject, html, text = P._market("IN")
    from app import main  # noqa: F401
    facts_issue = P._issue({"kind": "market", "region": "IN", "day": "2026-10-06", "weekly": False,
                            "indices": [{"name": "NIFTY 50", "price": 22555.75, "change_pct": 0.6}]})
    assert job.deliver({"id": "u-9", "email": "a@example.com"}, facts_issue, "market_in")
    to, body, page, headers = sent[0]
    assert "/unsubscribe?t=" in page and "/unsubscribe?t=" in body and "List-Unsubscribe" in headers


def test_outside_text_is_escaped():
    evil = '<script>alert(1)</script>&"\''
    issue = {"id": "market.IN.2026-10-06", "subject": evil, "title": evil, "summary": evil, "label": evil, "kind": "market",
             "sections": [{"title": evil, "items": [{"text": evil, "url": "javascript:alert(1)", "lines": [
                 {"text": evil, "url": "https://example.com/?a=1&b=2"}]}]}],
             "indices": [{"name": evil, "price": 1.0, "change_pct": 1.0}]}
    html, text = write.render(issue)
    assert "<script" not in html and "&lt;script&gt;" in html and "javascript:" not in html
    assert 'href="https://example.com/?a=1&amp;b=2"' in html
    h2, _ = kit.message(evil, f"- {evil}\n{evil}", "/alerts", evil, evil)
    assert "<script" not in h2
    h3, _ = kit.render(evil, [kit.table([evil], [[evil]]), kit.bullets([(evil, evil, "data:text/html,x")]), kit.card(evil, [kit.Row(evil, evil, 1.0, evil)])],
                       kit.Footer(why=evil), label=evil, date=evil, summary=evil, cta=(evil, "/x"))
    assert "<script" not in h3 and "data:text" not in h3


def test_indian_numbers_and_arrows():
    assert kit.indian(1234567.5, 2) == "12,34,567.50" and kit.indian(999) == "999" and kit.indian(-100000) == "−1,00,000"
    assert kit.inr(100000) == "₹1,00,000" and kit.inr(1849.3, 2) == "₹1,849.30"
    assert kit.inr_compact(925) == "₹925" and kit.inr_compact(520000) == "₹5.2 lakh"
    assert kit.inr_compact(3472e7) == "₹3,472 cr" and kit.inr_compact(1.51e12) == "₹1.51 lakh cr"
    assert kit.pct(0.6) == "+0.60%" and kit.pct(-1.25) == "−1.25%"
    up, down = kit.delta(0.6)[1], kit.delta(-0.6)[1]
    assert up.startswith("▲") and down.startswith("▼")              # never colour alone
    assert kit.delta(2.0, tone="neutral")[0].count("c-muted") == 1


def test_tiles_two_or_three_to_a_row_and_stack_on_phones():
    three = kit.tiles([kit.Tile("a", "1"), kit.Tile("b", "2"), kit.Tile("c", "3")]).html
    assert three.count("<tr>") == 1 + 3 and "stack" in three and 'width="33%"' in three
    assert 'width="50%"' in kit.tiles([kit.Tile("a", "1"), kit.Tile("b", "2")]).html


def test_receipt_has_no_unsubscribe_and_tips_do(built):
    assert kit.UNSUBSCRIBE not in built["lifecycle_receipt"]["html"] and "/settings#notifications" in built["lifecycle_receipt"]["html"]
    assert built["lifecycle_welcome"]["unsubscribe"] and not built["lifecycle_receipt"]["unsubscribe"]


# ---------- the preview gallery is for the admin ----------
def test_previews_endpoint_is_admin_only_and_lists_every_email(monkeypatch):
    w = W.build(monkeypatch)
    try:
        c = w["client"]
        for path in ("/admin/email-previews", "/admin/email-previews/market_in"):
            assert c.get(path).status_code in (401, 403)
            r = c.get(path, headers=W.headers("pro-token"))
            assert r.status_code == 403 and r.json()["detail"]["code"] == "not_admin"
        r = c.get("/admin/email-previews", headers=W.headers("admin-token"))
        assert r.status_code == 200
        got = {p["kind"]: p for p in r.json()["previews"]}
        assert set(got) == set(KINDS) and all("error" not in p for p in got.values())
        one = c.get("/admin/email-previews/market_in", headers=W.headers("admin-token")).json()
        assert one["html"].startswith("<!doctype html>") and one["text"] and one["subject"].startswith("Market Brief India")
        page = c.get("/admin/email-previews/my_stocks?format=html", headers=W.headers("admin-token"))
        assert page.status_code == 200 and page.text.startswith("<!doctype html>")
        assert c.get("/admin/email-previews/nope", headers=W.headers("admin-token")).status_code == 404
    finally:
        w["close"]()
