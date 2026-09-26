"""The request guard (size cap, rate limit, headers), per-user throttles, and input checks added in the audit."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import guard, main
from app.intel.news import GoogleNews
from app.intel.net import SourceError
from app.models import AlertsReq


def small_app():
    app = FastAPI()

    @app.api_route("/x", methods=["GET", "POST"])
    def x():
        return {"ok": True}

    @app.get("/health")
    def health():
        return {"ok": True}

    app.add_middleware(guard.Guard)
    return app


def test_security_headers_and_size_cap():
    c = TestClient(small_app())
    r = c.get("/x")
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["x-frame-options"] == "DENY"
    assert c.post("/x", content=b"a" * 100).status_code == 200
    big = c.post("/x", content=b"a" * (guard.MAX_BODY + 1))
    assert big.status_code == 413 and big.json()["detail"]["code"] == "too_large"


def test_rate_limit_is_per_caller_and_skips_health(monkeypatch):
    monkeypatch.setattr(guard, "PER_MINUTE_ANON", 3)
    monkeypatch.setattr(guard, "PER_MINUTE_USER", 5)
    c = TestClient(small_app())
    assert [c.get("/x").status_code for _ in range(4)] == [200, 200, 200, 429]
    assert c.get("/health").status_code == 200                       # the host's health check is never limited
    user = {"Authorization": "Bearer abc"}
    assert [c.get("/x", headers=user).status_code for _ in range(6)] == [200] * 5 + [429]
    assert c.get("/x", headers={"Authorization": "Bearer other"}).status_code == 200
    assert c.get("/x", headers={"X-Real-IP": "1.2.3.4"}).status_code == 200


def test_made_up_tokens_still_hit_the_address_limit(monkeypatch):
    monkeypatch.setattr(guard, "PER_MINUTE_ADDRESS", 4)
    c = TestClient(small_app())
    codes = [c.get("/x", headers={"Authorization": f"Bearer fake{i}", "X-Real-IP": "9.9.9.9"}).status_code for i in range(6)]
    assert codes == [200] * 4 + [429, 429]


def test_window_resets_each_minute():
    w = guard.Window()
    assert w.hit("k", 1, now=60.0) and not w.hit("k", 1, now=61.0)
    assert w.hit("k", 1, now=121.0)


def test_test_sends_are_throttled():
    p = {"id": "throttle-user"}
    for _ in range(3):
        main.throttle(p, "t", 3, 3600, "slow")
    try:
        main.throttle(p, "t", 3, 3600, "slow")
        raise AssertionError("expected 429")
    except main.HTTPException as e:
        assert e.status_code == 429


def test_alert_contacts_are_checked():
    assert AlertsReq(alert_email="me@mail.example.com", telegram_chat_id="-100123456").alert_email
    assert AlertsReq(alert_email="", telegram_chat_id="").alert_email == ""
    for bad in ({"alert_email": "a@b.com\nBcc: x@y.com"}, {"alert_email": "a@b.com, c@d.com"}, {"alert_email": "nope"},
                {"telegram_chat_id": "abc; rm"}):
        try:
            AlertsReq(**bad)
            raise AssertionError(bad)
        except ValueError:
            pass


def test_public_health_has_no_provider_details():
    body = TestClient(main.app).get("/health").json()
    assert set(body) == {"ok", "data_online", "feed_connected", "ai_configured"}


def test_news_feed_with_a_dtd_is_refused(monkeypatch):
    g = GoogleNews()
    monkeypatch.setattr(g, "fetch", lambda *a, **k: '<?xml version="1.0"?><!DOCTYPE r [<!ENTITY a "aaaa">]><rss><channel></channel></rss>')
    try:
        g.search("x")
        raise AssertionError("expected SourceError")
    except SourceError:
        pass
