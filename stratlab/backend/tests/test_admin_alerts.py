"""Admin alerts go to the admin's own email without any setup, as well as any phone or Telegram set in Account."""
from app import alerts, kite_auto
from app.config import settings


def _smtp(monkeypatch):
    sent = []
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.example.com")
    monkeypatch.setattr(settings, "SMTP_USER", "bot@example.com")
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "pw")
    monkeypatch.setattr(alerts, "send_email", lambda to, subject, body, html=None, headers=None: sent.append((to, subject, body)))
    return sent


def test_admins_get_alerts_by_email_without_setting_anything(monkeypatch):
    from tests import world as W
    w = W.build(monkeypatch)
    try:
        sent = _smtp(monkeypatch)
        assert alerts.email_for({"email": "Owner@Example.com"}) == "owner@example.com"     # their sign-in address
        assert alerts.email_for({"email": "someone@example.com"}) is None                  # not for other users
        assert alerts.email_for({"email": "someone@example.com", "alert_email": "a@b.c"}) == "a@b.c"
        assert alerts.tell_admins("StratLab: 1 check failing", "Prices: down") == 1
        assert [(s[0], s[1]) for s in sent] == [("owner@example.com", "StratLab: 1 check failing")] and "Prices: down" in sent[0][2]
        sent.clear()
        kite_auto.AutoLogin(None, lambda: None)._alert("StratLab: Kite auto-login failed and won't retry today. Bad OTP.")
        assert sent and sent[0][0] == "owner@example.com" and "Bad OTP" in sent[0][2]
    finally:
        w["close"]()


def test_an_admin_alert_never_breaks_the_caller(monkeypatch):
    from tests import world as W
    w = W.build(monkeypatch)
    try:
        monkeypatch.setattr(settings, "SMTP_HOST", "smtp.example.com")
        monkeypatch.setattr(settings, "SMTP_USER", "bot@example.com")
        monkeypatch.setattr(settings, "SMTP_PASSWORD", "pw")
        monkeypatch.setattr(alerts, "send_email", lambda *a, **k: (_ for _ in ()).throw(OSError("smtp down")))
        assert alerts.tell_admins("x", "y") in (0, 1)                 # tried, and the failure stayed inside
    finally:
        w["close"]()


def test_admin_can_send_themselves_a_test_email(monkeypatch):
    from app import main
    from tests import world as W
    w = W.build(monkeypatch)
    try:
        h = W.headers("admin-token")
        r = w["client"].post("/admin/alerts/test", headers=h)
        assert r.status_code == 400 and "RESEND_API_KEY" in r.json()["detail"]["message"]     # not set up yet
        sent = _smtp(monkeypatch)
        assert w["client"].post("/admin/alerts/test", headers=h).json() == {"sent_to": "owner@example.com"}
        assert sent[0][0] == "owner@example.com"
        monkeypatch.setattr(main.alerts, "send_email", lambda *a, **k: (_ for _ in ()).throw(OSError("Network is unreachable")))
        r = w["client"].post("/admin/alerts/test", headers=h)
        assert r.status_code == 502 and "RESEND_API_KEY" in r.json()["detail"]["message"]   # says what to do
        assert w["client"].post("/admin/alerts/test", headers=W.headers("pro-token")).status_code == 403
    finally:
        w["close"]()


def test_email_goes_over_https_through_resend_when_its_key_is_set(monkeypatch):
    import httpx
    calls = []

    def post(url, **kw):
        calls.append((url, kw))
        return httpx.Response(200 if len(calls) == 1 else 403, json={"message": "You can only send testing emails to your own address"})
    monkeypatch.setattr(settings, "RESEND_API_KEY", "re_test")
    monkeypatch.setattr(settings, "SMTP_HOST", "")
    monkeypatch.setattr(settings, "ALERT_FROM_EMAIL", "")
    monkeypatch.setattr(httpx, "post", post)
    assert alerts.email_ready()
    alerts.send_email("owner@example.com", "Subject", "Body")
    url, kw = calls[0]
    assert url == "https://api.resend.com/emails" and kw["headers"]["Authorization"] == "Bearer re_test"
    assert kw["json"] == {"from": alerts.RESEND_FROM, "to": ["owner@example.com"], "subject": "Subject", "text": "Body",
                          "reply_to": "info@stratlab.studio"}      # replies reach a real inbox
    import pytest
    with pytest.raises(RuntimeError, match="own address"):
        alerts.send_email("someone@example.com", "s", "b")


def test_brevo_emails_carry_a_reply_to_a_real_inbox(monkeypatch):
    """The sender (ALERT_FROM_EMAIL) may be send-only; replies go to REPLY_TO_EMAIL."""
    from app import alerts
    from app.config import settings
    sent = {}

    class R:
        status_code = 201

    monkeypatch.setattr(settings, "BREVO_API_KEY", "xkeysib-test")
    monkeypatch.setattr(settings, "ALERT_FROM_EMAIL", "hello@stratlab.studio")
    monkeypatch.setattr(alerts.httpx, "post", lambda url, **kw: sent.update(kw["json"]) or R())
    alerts.send_email("owner@example.com", "Subject", "Body")
    assert sent["sender"]["email"] == "hello@stratlab.studio"
    assert sent["replyTo"] == {"email": "info@stratlab.studio"}
