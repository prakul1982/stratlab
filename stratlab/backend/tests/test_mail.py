"""Newsletter email plumbing: the HTTPS email services, HTML and headers, signed unsubscribe and confirmation links,
and the public pages those links open."""
import json
import time
from email import message_from_bytes

import httpx
import pytest

from app import alerts, db, mail_tokens, newsletter_prefs
from app.config import settings
from tests import world as W


@pytest.fixture
def no_email(monkeypatch):
    for k in ("BREVO_API_KEY", "RESEND_API_KEY", "SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "ALERT_FROM_EMAIL"):
        monkeypatch.setattr(settings, k, "")
    monkeypatch.setattr(settings, "ADMIN_EMAILS", "owner@example.com, other@example.com")


def _capture(monkeypatch, status=201):
    calls = []

    def post(url, **kw):
        calls.append((url, kw))
        return httpx.Response(status, json={"message": "sender not verified"} if status >= 400 else {"messageId": "x"})
    monkeypatch.setattr(httpx, "post", post)
    return calls


def test_brevo_request_shape_and_sender_falls_back_to_the_first_admin(no_email, monkeypatch):
    monkeypatch.setattr(settings, "BREVO_API_KEY", "xkeysib-test")
    calls = _capture(monkeypatch)
    assert alerts.email_ready()
    alerts.send_email("a@b.c", "Hello", "Plain", html="<p>Rich</p>", headers={"List-Unsubscribe": "<https://x>"})
    url, kw = calls[0]
    assert url == "https://api.brevo.com/v3/smtp/email" and kw["headers"]["api-key"] == "xkeysib-test"
    assert kw["json"] == {"sender": {"name": "StratLab", "email": "owner@example.com"}, "to": [{"email": "a@b.c"}],
                          "subject": "Hello", "textContent": "Plain", "htmlContent": "<p>Rich</p>",
                          "headers": {"List-Unsubscribe": "<https://x>"}}
    monkeypatch.setattr(settings, "ALERT_FROM_EMAIL", "news@stratlab.studio")
    alerts.send_email("a@b.c", "Hello", "Plain")                          # the old three-argument call
    assert calls[1][1]["json"]["sender"]["email"] == "news@stratlab.studio"
    assert "htmlContent" not in calls[1][1]["json"] and "headers" not in calls[1][1]["json"]


def test_brevo_refusal_is_reported(no_email, monkeypatch):
    monkeypatch.setattr(settings, "BREVO_API_KEY", "k")
    _capture(monkeypatch, status=400)
    with pytest.raises(RuntimeError, match="sender not verified"):
        alerts.send_email("a@b.c", "s", "b")


def test_provider_order_brevo_then_resend_then_smtp(no_email, monkeypatch):
    calls = _capture(monkeypatch, status=200)
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.example.com")
    monkeypatch.setattr(settings, "SMTP_USER", "bot@example.com")
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "pw")
    monkeypatch.setattr(settings, "RESEND_API_KEY", "re_x")
    monkeypatch.setattr(settings, "BREVO_API_KEY", "br_x")
    alerts.send_email("a@b.c", "s", "b")
    monkeypatch.setattr(settings, "BREVO_API_KEY", "")
    alerts.send_email("a@b.c", "s", "b", html="<b>b</b>", headers={"X-Test": "1"})
    assert [u for u, _ in calls] == ["https://api.brevo.com/v3/smtp/email", "https://api.resend.com/emails"]
    assert calls[1][1]["json"]["html"] == "<b>b</b>" and calls[1][1]["json"]["headers"] == {"X-Test": "1"}

    sent = []

    class FakeSMTP:
        def __init__(self, *a, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def starttls(self): pass
        def login(self, *a): pass
        def send_message(self, msg): sent.append(msg)
    monkeypatch.setattr(alerts.smtplib, "SMTP_SSL", FakeSMTP)
    monkeypatch.setattr(settings, "RESEND_API_KEY", "")
    assert alerts.email_ready()
    alerts.send_email("a@b.c", "s", "plain", html="<p>rich</p>", headers={"List-Unsubscribe-Post": "List-Unsubscribe=One-Click"})
    msg = message_from_bytes(sent[0].as_bytes())
    assert msg.get_content_type() == "multipart/alternative" and msg["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    assert [p.get_content_type() for p in msg.get_payload()] == ["text/plain", "text/html"]
    alerts.send_email("a@b.c", "s", "plain")
    assert sent[1].get_content_type() == "text/plain"
    monkeypatch.setattr(settings, "SMTP_HOST", "")
    assert not alerts.email_ready()


def test_tokens_round_trip_and_reject_tampering_and_old_confirm_links(monkeypatch):
    monkeypatch.setattr(settings, "MAIL_TOKEN_SECRET", "s3cret")
    t = mail_tokens.make("u-1", "unsubscribe", "market_in")
    assert mail_tokens.read(t, "unsubscribe") == ("u-1", "market_in")
    assert mail_tokens.read(t, "confirm") is None                          # made for something else
    payload, sig = t.split(".")
    forged = mail_tokens._b64(json.dumps(["u-2", "unsubscribe", "all", int(time.time())]).encode())
    for bad in (forged + "." + sig, payload + "." + sig[:-2] + "AA", payload, "", "a.b.c", "!!.??"):
        assert mail_tokens.read(bad, "unsubscribe") is None
    monkeypatch.setattr(settings, "MAIL_TOKEN_SECRET", "other")
    assert mail_tokens.read(t, "unsubscribe") is None                     # a different server secret
    monkeypatch.setattr(settings, "MAIL_TOKEN_SECRET", "s3cret")
    c = mail_tokens.make("u-1", "confirm", "a@b.c")
    later = time.time() + 2 * 86400
    monkeypatch.setattr(mail_tokens.time, "time", lambda: later)
    assert mail_tokens.read(c, "confirm") == ("u-1", "a@b.c")
    assert mail_tokens.read(t, "unsubscribe") == ("u-1", "market_in")
    later += 2 * 86400
    assert mail_tokens.read(c, "confirm") is None                          # past 3 days
    monkeypatch.setattr(mail_tokens.time, "time", lambda: later + 10 ** 8)
    assert mail_tokens.read(t, "unsubscribe") == ("u-1", "market_in")    # unsubscribe links never expire


def test_secret_falls_back_to_one_derived_from_the_service_key(monkeypatch):
    monkeypatch.setattr(settings, "MAIL_TOKEN_SECRET", "")
    monkeypatch.setattr(settings, "SUPABASE_SERVICE_KEY", "service-key")
    t = mail_tokens.make("u-1", "unsubscribe", "all")
    assert mail_tokens._secret() != b"service-key" and mail_tokens.read(t, "unsubscribe") == ("u-1", "all")


def test_unsubscribe_links_and_headers(monkeypatch):
    monkeypatch.setattr(settings, "PUBLIC_API_URL", "https://api.example.com")
    url = alerts.unsubscribe_url("u-1", "my_stocks")
    assert url.startswith("https://api.example.com/unsubscribe?t=")
    assert mail_tokens.read(url.split("t=", 1)[1], "unsubscribe") == ("u-1", "my_stocks")
    h = alerts.list_unsubscribe_headers("u-1", "my_stocks")
    assert h["List-Unsubscribe"].startswith("<https://api.example.com/unsubscribe?t=") and h["List-Unsubscribe"].endswith(">")
    assert h["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"


def test_prefs_default_off_and_validate(monkeypatch):
    w = W.build(monkeypatch)
    try:
        assert newsletter_prefs.get("u-pro") == {"market_in": "off", "market_us": "off", "my_stocks": "off"}
        assert newsletter_prefs.set("u-pro", {"market_in": "daily"})["market_in"] == "daily"
        assert newsletter_prefs.get("u-pro") == {"market_in": "daily", "market_us": "off", "my_stocks": "off"}
        for bad in ({"market_in": "hourly"}, {"crypto": "daily"}):
            with pytest.raises(ValueError):
                newsletter_prefs.set("u-pro", bad)
    finally:
        w["close"]()


def test_unsubscribe_get_and_one_click_post_need_a_valid_link(monkeypatch):
    w = W.build(monkeypatch)
    try:
        c = w["client"]
        newsletter_prefs.set("u-pro", {"market_in": "daily", "market_us": "weekly", "my_stocks": "daily"})
        t = mail_tokens.make("u-pro", "unsubscribe", "market_in")
        r = c.get("/unsubscribe", params={"t": t})
        assert r.status_code == 200 and "text/html" in r.headers["content-type"]
        assert "Unsubscribe from the India market email?" in r.text and "<form method=post" in r.text
        assert newsletter_prefs.get("u-pro")["market_in"] == "daily"         # opening the link (a mail scanner) changes nothing
        r = c.post("/unsubscribe", params={"t": t, "page": 1})                # the button on that page
        assert "unsubscribed from the India market email" in r.text and "text/html" in r.headers["content-type"]
        assert newsletter_prefs.get("u-pro") == {"market_in": "off", "market_us": "weekly", "my_stocks": "daily"}

        r = c.post("/unsubscribe", params={"t": mail_tokens.make("u-pro", "unsubscribe", "my_stocks")})
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/plain")
        assert newsletter_prefs.get("u-pro")["my_stocks"] == "off"

        for bad in ("", "nonsense", t[:-3] + "xyz", mail_tokens.make("u-pro", "confirm", "all"),
                    mail_tokens.make("u-pro", "unsubscribe", "crypto")):
            assert c.get("/unsubscribe", params={"t": bad}).status_code == 400
            assert c.post("/unsubscribe", params={"t": bad}).status_code == 400
        assert newsletter_prefs.get("u-pro")["market_us"] == "weekly"         # bad links changed nothing

        c.post("/unsubscribe", params={"t": mail_tokens.make("u-pro", "unsubscribe", "all")})
        assert set(newsletter_prefs.get("u-pro").values()) == {"off"}
    finally:
        w["close"]()


def test_confirming_the_newsletter_address(monkeypatch):
    w = W.build(monkeypatch)
    try:
        c = w["client"]
        sent = []
        monkeypatch.setattr(alerts, "send_email", lambda to, subject, body, html=None, headers=None: sent.append((to, body, html)))
        monkeypatch.setattr(settings, "SMTP_HOST", "smtp.example.com")
        monkeypatch.setattr(settings, "SMTP_USER", "bot@example.com")
        monkeypatch.setattr(settings, "SMTP_PASSWORD", "pw")
        pro = db.get_profile("u-pro")
        assert alerts.newsletter_email(pro) == "pro@example.com" and not alerts.email_confirmed(pro)

        r = c.post("/me/email/confirm", headers=W.headers("pro-token"))
        assert r.json() == {"confirmed": False, "sent_to": "pro@example.com"}
        to, body, html = sent[0]
        link = body.split("\n\n")[1]
        assert to == "pro@example.com" and "/email/confirm?t=" in link and link in html.replace("&amp;", "&")

        assert c.get("/email/confirm", params={"t": "forged"}).status_code == 400
        assert c.post("/email/confirm", params={"t": "forged"}).status_code == 400
        r = c.get(link[link.index("/email/confirm"):])
        assert r.status_code == 200 and "pro@example.com" in r.text and "<form method=post" in r.text
        assert not alerts.email_confirmed(db.get_profile("u-pro"))     # opening the link (a mail scanner) confirms nothing
        r = c.post(link[link.index("/email/confirm"):])                  # the button on that page
        assert r.status_code == 200 and "pro@example.com" in r.text
        assert alerts.email_confirmed(db.get_profile("u-pro"))
        assert c.post("/me/email/confirm", headers=W.headers("pro-token")).json() == {"confirmed": True, "sent_to": None}

        db.update_profile("u-pro", alert_email="new@example.com")          # a new address needs confirming again
        assert not alerts.email_confirmed(db.get_profile("u-pro"))

        for _ in range(4):
            c.post("/me/email/confirm", headers=W.headers("free-token"))
        r = c.post("/me/email/confirm", headers=W.headers("free-token"))
        assert r.status_code == 200
        assert c.post("/me/email/confirm", headers=W.headers("free-token")).status_code == 429   # 5 an hour

        assert alerts.email_confirmed({"id": "u-admin", "email": "owner@example.com"})     # the admin's own address
        assert not alerts.email_confirmed({"id": "u-imposter", "email": "owner@example.com", "_email_verified": False})
        assert c.post("/me/email/confirm", headers=W.headers("admin-token")).json()["confirmed"] is True
    finally:
        w["close"]()


def test_brevo_ip_block_says_where_to_turn_it_off():
    from types import SimpleNamespace
    from app import alerts
    r = SimpleNamespace(status_code=401, json=lambda: {"message": "We have detected you are using an unrecognised IP address 1.2.3.4. "
                                                                  "If you performed this action make sure to add the new IP address in this link: https://app.brevo.com/security/authorised_ips"})
    msg = str(alerts._refused("Brevo", r))
    assert "Authorized IPs" in msg and "turn IP blocking off" in msg and "https://app.brevo.com/security/authorised_ips" in msg
