"""rev9a: a client can't choose its own address, failed sign-ins are limited per address before the sign-in
service is asked, a Razorpay body is handled once whatever its id header says, and heavy reads are throttled per user."""
import hashlib
import hmac
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import auth, billing, db, guard
from app.config import settings
from tests import world


def scope(headers, peer="203.0.113.9"):
    return {"headers": [(k.encode(), v.encode()) for k, v in headers.items()], "client": (peer, 1234)}


def test_spoofed_address_headers_are_ignored(monkeypatch):
    monkeypatch.delenv("TRUSTED_PROXY_HOPS", raising=False)
    monkeypatch.delenv("TRUST_X_REAL_IP", raising=False)
    # the proxy appended 198.51.100.7; the client's own entries sit to its left
    s = scope({"x-real-ip": "10.9.9.9", "x-forwarded-for": "10.1.1.1, 198.51.100.7"})
    assert guard.address(s) == "198.51.100.7"
    assert guard.address(scope({"x-real-ip": "10.9.9.9"})) == "203.0.113.9"      # no forwarded header: the socket peer
    assert guard.address(scope({})) == "203.0.113.9"


def test_hop_count_is_honoured(monkeypatch):
    monkeypatch.setenv("TRUSTED_PROXY_HOPS", "2")
    s = scope({"x-forwarded-for": "10.1.1.1, 198.51.100.7, 192.0.2.5"})
    assert guard.address(s) == "198.51.100.7"
    assert guard.address(scope({"x-forwarded-for": "192.0.2.5"})) == "203.0.113.9"    # fewer entries than hops: the peer


def test_x_real_ip_only_when_trusted(monkeypatch):
    monkeypatch.setenv("TRUST_X_REAL_IP", "1")
    assert guard.address(scope({"x-real-ip": "192.0.2.44", "x-forwarded-for": "1.1.1.1"})) == "192.0.2.44"


@pytest.fixture
def w(monkeypatch):
    built = world.build(monkeypatch)
    yield built
    built["close"]()


def test_bad_token_flood_is_limited_before_the_sign_in_call(w, monkeypatch):
    c = w["client"]
    assert c.get("/me", headers=world.headers("pro-token")).status_code == 200     # a real user, signed in before the flood
    calls = {"n": 0}
    real = w["db"].auth.get_user

    def counting(tok):
        calls["n"] += 1
        return real(tok)
    monkeypatch.setattr(w["db"].auth, "get_user", counting)
    monkeypatch.setattr(guard.time, "time", lambda: 1_800_000_030.0)
    # a rotating X-Real-IP no longer gives each request its own address
    codes = [c.get("/me", headers={"Authorization": f"Bearer junk-{i}", "X-Real-IP": f"10.0.0.{i % 250}"}).status_code
             for i in range(guard.BAD_TOKENS_PER_MINUTE + 20)]
    assert codes[:guard.BAD_TOKENS_PER_MINUTE] == [401] * guard.BAD_TOKENS_PER_MINUTE
    assert codes[guard.BAD_TOKENS_PER_MINUTE:] == [429] * 20
    assert calls["n"] == guard.BAD_TOKENS_PER_MINUTE
    # that signed-in user, from the same address, is not held
    assert c.get("/me", headers=world.headers("pro-token")).status_code == 200


def _body():
    return json.dumps({"event": "subscription.halted", "payload": {"subscription": {"entity": {"id": "sub_X"}}}}).encode()


def _post(c, body, eid):
    sig = hmac.new(b"whsec", body, hashlib.sha256).hexdigest()
    return c.post("/billing/webhook", content=body, headers={"X-Razorpay-Signature": sig, "X-Razorpay-Event-Id": eid,
                                                             "Content-Type": "application/json"})


def test_replayed_body_with_a_new_event_id_does_nothing(w, monkeypatch):
    monkeypatch.setattr(settings, "RAZORPAY_WEBHOOK_SECRET", "whsec")
    acted = []
    monkeypatch.setattr(billing, "_act", lambda ev: acted.append(ev["event"]))
    for eid in ("evt_1", "evt_1", "evt_2", "evt_3"):
        assert _post(w["client"], _body(), eid).status_code == 200
    assert len(acted) == 1
    other = json.dumps({"event": "subscription.charged", "payload": {}}).encode()
    assert _post(w["client"], other, "evt_4").status_code == 200       # a genuinely new event still acts
    assert acted == ["subscription.halted", "subscription.charged"]


def test_a_failed_event_is_retried(w, monkeypatch):
    monkeypatch.setattr(settings, "RAZORPAY_WEBHOOK_SECRET", "whsec")
    acted = []

    def act(ev):
        acted.append(1)
        if len(acted) == 1:
            raise RuntimeError("boom")
    monkeypatch.setattr(billing, "_act", act)
    monkeypatch.setattr(billing, "_client", type("C", (), {"utility": type("U", (), {"verify_webhook_signature": staticmethod(lambda *a: True)})()}))
    with pytest.raises(RuntimeError):
        billing.handle_webhook(_body(), "sig", "evt_1")
    billing.handle_webhook(_body(), "sig", "evt_1")
    billing.handle_webhook(_body(), "sig", "evt_1")
    assert len(acted) == 2


def test_heavy_reads_are_throttled_per_user(w):
    c = w["client"]
    h = world.headers("pro-token")
    for path in ("/research/rotation", "/research/investor"):
        got = [c.get(path, headers=h).status_code for _ in range(25)]
        assert 429 in got, path
        again = c.get(path, headers=h)
        assert again.status_code == 429 and "wait a minute" in again.json()["detail"]["message"].lower()
        break          # the three share one allowance, so the first route used it up
    assert c.get("/research/investor", headers=world.headers("basic-token")).status_code != 429     # another account isn't held


def test_the_hosts_internal_hops_are_skipped_not_the_clients_entries(monkeypatch):
    monkeypatch.delenv("TRUSTED_PROXY_HOPS", raising=False)
    monkeypatch.delenv("TRUST_X_REAL_IP", raising=False)
    # the edge appended the client 198.51.100.7, then an internal proxy appended its own 10.x / 100.64.x hop
    assert guard.address(scope({"x-forwarded-for": "198.51.100.7, 10.20.0.3"})) == "198.51.100.7"
    assert guard.address(scope({"x-forwarded-for": "1.1.1.1, 198.51.100.7, 100.64.3.2, 10.0.0.1"})) == "198.51.100.7"
    # every user doesn't collapse onto one internal address, and a lone internal entry is still used rather than nothing
    assert guard.address(scope({"x-forwarded-for": "10.20.0.3"})) == "10.20.0.3"
    assert guard.address(scope({"x-forwarded-for": "2001:db8::1, fd00::5"})) == "2001:db8::1"
