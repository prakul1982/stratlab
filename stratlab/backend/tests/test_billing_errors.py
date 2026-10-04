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


def test_admin_sees_razorpays_reason(monkeypatch):
    from app import admin
    try:
        c = client(monkeypatch, create_subscription=boom(rz.BadRequestError("The id provided does not exist")))
        assert "Razorpay said" not in c.post("/billing/subscribe", json={"plan": "pro"}).json()["detail"]["message"]
        monkeypatch.setattr(admin, "is_admin", lambda p: True)
        assert "does not exist" in c.post("/billing/subscribe", json={"plan": "pro"}).json()["detail"]["message"]
    finally:
        main.app.dependency_overrides.clear()


def test_setup_check_reports_keys_and_plans(monkeypatch):
    from app.config import settings

    class FakePlan:
        def __init__(self, bad_auth): self.bad = bad_auth
        def all(self, q):
            if self.bad:
                raise rz.BadRequestError("Authentication failed")
        def fetch(self, pid):
            if pid != "plan_good":
                raise rz.BadRequestError("The id provided does not exist")
            return {"interval": 1, "period": "monthly", "item": {"name": "StratLab Basic", "amount": 99900}}

    for k, v in {"RAZORPAY_KEY_ID": "rzp_test_ABCDEFGH1234", "RAZORPAY_KEY_SECRET": "s" * 24, "RAZORPAY_WEBHOOK_SECRET": "",
                 "RAZORPAY_PLAN_BASIC": "plan_good", "RAZORPAY_PLAN_PRO": "plan_typo", "RAZORPAY_PLAN_BASIC_YEAR": "",
                 "RAZORPAY_PLAN_PRO_YEAR": ""}.items():
        monkeypatch.setattr(settings, k, v)
    monkeypatch.setattr(billing, "international_status", lambda k, s: {"enabled": None, "detail": "x"})
    bad = {"auth": True}
    monkeypatch.setattr(billing.razorpay, "Client", lambda auth: type("C", (), {"plan": FakePlan(bad["auth"])})())
    r = billing.check_setup()
    assert r["mode"] == "test" and not r["keys_ok"] and "Authentication failed" in r["keys_error"]
    assert "s" * 24 not in str(r) and r["secret_length"] == 24 and r["key_id"].endswith("1234")   # nothing secret returned
    bad["auth"] = False
    r = billing.check_setup()
    plans = {p["label"]: p for p in r["plans"]}
    assert r["keys_ok"] and plans["Basic monthly"]["ok"] and "₹999" in plans["Basic monthly"]["detail"]
    assert not plans["Pro monthly"]["ok"] and "can't find" in plans["Pro monthly"]["detail"]
    assert plans["Basic yearly"]["detail"] == "Not set" and r["webhook_secret_set"] is False
    assert r["currencies"] == ["INR"] and r["international"]["enabled"] is None


def test_international_cards_is_an_info_row_not_an_error(monkeypatch):
    """Razorpay has no public API for the international payments setting, so the row points to the dashboard as
    information: no network call, no "Couldn't ask Razorpay" error, no warning."""
    import httpx

    def boom(*a, **k):
        raise AssertionError("no call to Razorpay")
    monkeypatch.setattr(httpx, "get", boom)
    r = billing.international_status("rzp_live_x", "secret")
    assert r["enabled"] is None and r["info"] is True
    assert "Account & Settings → International payments" in r["detail"] and "Couldn't" not in r["detail"]
