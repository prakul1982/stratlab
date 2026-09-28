"""Razorpay trouble gives a clear message, never a crash, and never a 401 (which would sign the user out)."""
from fastapi.testclient import TestClient
from razorpay import errors as rz

from app import billing, main


def client(monkeypatch, **patches):
    main.app.dependency_overrides[main.current_profile] = lambda: {"id": "u", "plan": "free", "_plan": "free", "_paid_plan": "free"}
    for k, v in patches.items():
        monkeypatch.setattr(billing, k, v)
    return TestClient(main.app)


def boom(exc):
    def f(*a, **k):
        raise exc
    return f


def test_subscribe_errors(monkeypatch):
    try:
        c = client(monkeypatch, create_subscription=boom(rz.BadRequestError("Authentication failed")))
        r = c.post("/billing/subscribe", json={"plan": "pro"})
        assert r.status_code == 502 and r.json()["detail"]["code"] == "billing_setup"
        monkeypatch.setattr(billing, "create_subscription", boom(rz.ServerError("down")))
        assert c.post("/billing/subscribe", json={"plan": "pro"}).json()["detail"]["code"] == "billing_unavailable"
        monkeypatch.setattr(billing, "create_subscription", boom(ValueError("Payments aren't set up on the server yet.")))
        assert c.post("/billing/subscribe", json={"plan": "pro"}).status_code == 503
    finally:
        main.app.dependency_overrides.clear()


def test_verify_rejects_bad_or_missing_fields(monkeypatch):
    body = {"razorpay_payment_id": "pay_1", "razorpay_subscription_id": "sub_1", "razorpay_signature": "sig"}
    try:
        c = client(monkeypatch, verify_checkout=boom(rz.SignatureVerificationError("mismatch")))
        r = c.post("/billing/verify", json=body)
        assert r.status_code == 400 and r.json()["detail"]["code"] == "payment_not_verified"
        assert c.post("/billing/verify", json={**body, "razorpay_signature": ""}).status_code == 422
        assert c.post("/billing/verify", json={"razorpay_payment_id": "pay_1"}).status_code == 422
        monkeypatch.setattr(billing, "verify_checkout", boom(rz.ServerError("down")))
        assert c.post("/billing/verify", json=body).json()["detail"]["code"] == "payment_pending"
    finally:
        main.app.dependency_overrides.clear()


def test_signature_check_is_real(monkeypatch):
    """The real SDK check: HMAC-SHA256 of payment_id|subscription_id with the key secret."""
    import hashlib
    import hmac

    from app.config import settings
    monkeypatch.setattr(settings, "RAZORPAY_KEY_ID", "rzp_test_x")
    monkeypatch.setattr(settings, "RAZORPAY_KEY_SECRET", "secret")
    monkeypatch.setattr(billing, "_client", None)
    good = hmac.new(b"secret", b"pay_1|sub_1", hashlib.sha256).hexdigest()
    billing.client().utility.verify_subscription_payment_signature(
        {"razorpay_subscription_id": "sub_1", "razorpay_payment_id": "pay_1", "razorpay_signature": good})
    try:
        billing.client().utility.verify_subscription_payment_signature(
            {"razorpay_subscription_id": "sub_1", "razorpay_payment_id": "pay_1", "razorpay_signature": "0" * 64})
        raise AssertionError("a wrong signature must fail")
    except rz.SignatureVerificationError:
        pass
    monkeypatch.setattr(billing, "_client", None)
