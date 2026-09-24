"""Regression tests for bugs fixed in the first review."""
import hashlib
import hmac
import json

import httpx
import pytest
from fastapi.testclient import TestClient
from razorpay.errors import SignatureVerificationError

from app import ai_writer, alerts, billing, kite_service
from app.config import settings
from app.main import app


def test_webhook_signed_with_empty_secret_is_rejected(monkeypatch):
    # with no secret configured, anyone can compute a "valid" HMAC using an empty key
    monkeypatch.setattr(settings, "RAZORPAY_WEBHOOK_SECRET", "")
    body = b'{"event": "subscription.activated", "payload": {}}'
    forged = hmac.new(b"", body, hashlib.sha256).hexdigest()
    with pytest.raises(SignatureVerificationError):
        billing.handle_webhook(body, forged)


def test_webhook_route_returns_400_for_forged_request(monkeypatch):
    monkeypatch.setattr(settings, "RAZORPAY_WEBHOOK_SECRET", "")
    r = TestClient(app).post("/billing/webhook", content=b"{}", headers={"X-Razorpay-Signature": "x"})
    assert r.status_code == 400


def test_cancel_needs_active_subscription():
    with pytest.raises(ValueError):
        billing.cancel({"id": "u", "razorpay_subscription_id": "sub_1", "plan_status": "cancelled"})


def test_kite_token_from_yesterday_is_not_ready(monkeypatch):
    k = kite_service.KiteService()
    k._set_token("tok", "2000-01-01")
    assert not k.ready()
    k._set_token("tok", kite_service.today_ist())
    assert k.ready()


def test_telegram_error_does_not_leak_bot_token(monkeypatch):
    monkeypatch.setattr(settings, "TELEGRAM_BOT_TOKEN", "SECRET123")
    monkeypatch.setattr(httpx, "post", lambda url, **kw: httpx.Response(
        400, json={"description": "chat not found"}, request=httpx.Request("POST", url)))
    with pytest.raises(RuntimeError) as e:
        alerts.send_telegram("42", "hi")
    assert "SECRET123" not in str(e.value) and "chat not found" in str(e.value)


def test_unconfigured_channel_is_an_error_not_a_silent_success(monkeypatch):
    monkeypatch.setattr(settings, "TELEGRAM_BOT_TOKEN", "")
    with pytest.raises(RuntimeError):
        alerts.send_telegram("42", "hi")


@pytest.mark.parametrize("reply", ["[]", '"text"', '{"entry": "oops", "risk": [1, 2]}'])
def test_ai_writer_handles_malformed_replies(monkeypatch, reply):
    monkeypatch.setattr(settings, "AI_PROVIDER", "gemini")
    monkeypatch.setattr(ai_writer, "_gemini", lambda system, text: reply)
    try:
        out = ai_writer.write_strategy("buy when rsi below 30", pro=False)
    except ai_writer.AIError:
        return
    assert out["entry"] == [] and out["risk"] == {}


def test_ai_writer_keeps_valid_rules(monkeypatch):
    reply = json.dumps({"name": "RSI dip", "tf": "1d", "entry": [{"l": {"t": "rsi", "p": 14}, "op": "lt", "r": {"t": "num", "v": 30}}],
                        "exit": [{"l": {"t": "macd"}, "op": "gt", "r": {"t": "num", "v": 0}}],
                        "risk": {"sl": 2, "capital": True}, "mentioned": ["sl"]})
    monkeypatch.setattr(settings, "AI_PROVIDER", "gemini")
    monkeypatch.setattr(ai_writer, "_gemini", lambda system, text: reply)
    out = ai_writer.write_strategy("x", pro=False)
    assert len(out["entry"]) == 1
    assert out["exit"] == []           # MACD is Pro-only
    assert out["risk"] == {"sl": 2}    # booleans are not numbers


def test_bad_ids_are_404_not_500(monkeypatch):
    from app import main
    app.dependency_overrides[main.current_profile] = lambda: {"id": "u", "_plan": "free"}
    try:
        c = TestClient(app)
        assert c.delete("/strategies/not-a-uuid").status_code == 404
        assert c.get("/live/sessions/not-a-uuid").status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_cors_accepts_comma_separated_origins():
    from app.config import origins
    assert origins("https://a.example, http://localhost:5500/") == ["https://a.example", "http://localhost:5500"]
