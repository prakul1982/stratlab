"""Usage analytics from the server: "payment completed" goes to PostHog once per payment, only when POSTHOG_KEY is
set, with nothing personal in it, and a slow or broken analytics service never holds up or breaks a payment."""
import json
import threading
import time
from types import SimpleNamespace

import pytest

from app import billing, invoices, product_analytics
from app.config import settings

PAY = {"id": "pay_1", "amount": 99900, "currency": "INR", "created_at": 1791000000, "international": False, "status": "captured"}
SUB = {"id": "sub_1", "plan_id": "plan_inrB", "notes": {"user_id": "u1", "plan": "basic", "period": "month"}, "current_end": 1793000000}
PROFILE = {"id": "u1", "email": "someone@example.com", "name": "Some One"}


@pytest.fixture
def sent(monkeypatch):
    saved, posts = {}, []
    for mod in (invoices.db, product_analytics.db):
        monkeypatch.setattr(mod, "get_setting", lambda k: saved.get(k))
        monkeypatch.setattr(mod, "set_setting", lambda k, v: saved.__setitem__(k, v))
    monkeypatch.setattr(product_analytics, "BACKGROUND", False)
    monkeypatch.setattr(product_analytics.httpx, "post", lambda url, json=None, timeout=None:
                        posts.append({"url": url, "body": json}) or SimpleNamespace(status_code=200, text=""))
    monkeypatch.setattr(settings, "RAZORPAY_PLAN_BASIC", "plan_inrB")
    return posts


def test_nothing_is_sent_without_a_key(sent, monkeypatch):
    monkeypatch.setattr(settings, "POSTHOG_KEY", "")
    assert not product_analytics.enabled()
    assert billing.invoice_for(PROFILE, SUB, PAY)                    # the payment's invoice is still made
    assert not product_analytics.capture("u1", "anything")
    assert sent == []


def test_a_payment_is_sent_once_by_user_id_with_nothing_personal(sent, monkeypatch):
    monkeypatch.setattr(settings, "POSTHOG_KEY", "phc_test")
    monkeypatch.setattr(settings, "POSTHOG_HOST", "https://eu.i.posthog.com")
    billing.invoice_for(PROFILE, SUB, PAY)
    billing.invoice_for(PROFILE, SUB, PAY)                           # the charged webhook after checkout: still one
    assert len(sent) == 1
    post = sent[0]
    assert post["url"] == "https://eu.i.posthog.com/i/v0/e/"
    body = post["body"]
    assert body["api_key"] == "phc_test" and body["event"] == "payment completed" and body["distinct_id"] == "u1"
    assert body["properties"]["plan"] == "basic" and body["properties"]["period"] == "month"
    assert body["timestamp"].startswith("2026-")                      # when it was paid, not when it was sent
    text = json.dumps(body)
    for personal in ("someone@example.com", "Some One", "99900", "999", "pay_1", "sub_1"):
        assert personal not in text, personal
    billing.invoice_for(PROFILE, SUB, {**PAY, "id": "pay_2"})         # next month's renewal is a new event
    assert len(sent) == 2 and sent[1]["body"]["uuid"] != body["uuid"]


def test_the_charge_webhook_sends_it_too(sent, monkeypatch):
    monkeypatch.setattr(settings, "POSTHOG_KEY", "phc_test")
    monkeypatch.setattr(settings, "RAZORPAY_WEBHOOK_SECRET", "w")
    monkeypatch.setattr(billing, "_client", SimpleNamespace(utility=SimpleNamespace(verify_webhook_signature=lambda *a: True)))
    monkeypatch.setattr(billing.db, "profile_by_subscription", lambda sid: dict(PROFILE))
    monkeypatch.setattr(billing.db, "update_profile", lambda *a, **k: None)
    body = json.dumps({"event": "subscription.charged", "payload": {"subscription": {"entity": SUB}, "payment": {"entity": {**PAY, "id": "pay_9"}}}})
    billing.handle_webhook(body.encode(), "sig")
    billing.handle_webhook(body.encode(), "sig")
    assert [p["body"]["event"] for p in sent] == ["payment completed"]


def test_a_broken_analytics_service_never_breaks_a_payment(sent, monkeypatch):
    monkeypatch.setattr(settings, "POSTHOG_KEY", "phc_test")

    def down(*a, **k):
        raise ConnectionError("unreachable")
    monkeypatch.setattr(product_analytics.httpx, "post", down)
    assert billing.invoice_for(PROFILE, SUB, PAY)
    monkeypatch.setattr(product_analytics.db, "get_setting", down)     # even the database marker failing
    assert billing.invoice_for(PROFILE, SUB, {**PAY, "id": "pay_3"})
    assert product_analytics.capture("u1", "payment completed", once="x") is False


def test_sending_happens_off_the_request(sent, monkeypatch):
    monkeypatch.setattr(settings, "POSTHOG_KEY", "phc_test")
    monkeypatch.setattr(product_analytics, "BACKGROUND", True)
    release, done = threading.Event(), threading.Event()

    def slow(*a, **k):
        release.wait(5)
        done.set()
        return SimpleNamespace(status_code=200, text="")
    monkeypatch.setattr(product_analytics.httpx, "post", slow)
    t = time.monotonic()
    assert product_analytics.capture("u1", "payment completed")
    assert time.monotonic() - t < 0.5                                 # returned before the slow send finished
    release.set()
    assert done.wait(5)
