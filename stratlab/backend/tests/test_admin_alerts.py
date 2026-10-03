"""Admin alerts go to the admin's own email without any setup, as well as any phone or Telegram set in Account."""
from app import alerts, kite_auto
from app.config import settings


def _smtp(monkeypatch):
    sent = []
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.example.com")
    monkeypatch.setattr(settings, "SMTP_USER", "bot@example.com")
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "pw")
    monkeypatch.setattr(alerts, "send_email", lambda to, subject, body: sent.append((to, subject, body)))
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
        assert sent == [("owner@example.com", "StratLab: 1 check failing", "Prices: down")]
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
        monkeypatch.setattr(alerts, "send_email", lambda *a: (_ for _ in ()).throw(OSError("smtp down")))
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
        assert r.status_code == 400 and "SMTP_HOST" in r.json()["detail"]["message"]     # not set up yet
        sent = _smtp(monkeypatch)
        assert w["client"].post("/admin/alerts/test", headers=h).json() == {"sent_to": "owner@example.com"}
        assert sent[0][0] == "owner@example.com"
        monkeypatch.setattr(main.alerts, "send_email", lambda *a: (_ for _ in ()).throw(OSError("Network is unreachable")))
        r = w["client"].post("/admin/alerts/test", headers=h)
        assert r.status_code == 502 and "unreachable" in r.json()["detail"]["message"]
        assert w["client"].post("/admin/alerts/test", headers=W.headers("pro-token")).status_code == 403
    finally:
        w["close"]()
