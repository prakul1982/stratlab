from datetime import datetime

import httpx
import pytest

from app import kite_auto
from app.config import settings
from app.kite_auto import AutoLoginError, fetch_request_token, login_due, totp
from app.kite_service import IST

LOGIN_URL = "https://kite.zerodha.com/connect/login?api_key=abc&v=3"


@pytest.fixture(autouse=True)
def creds(monkeypatch):
    monkeypatch.setattr(settings, "KITE_USER_ID", "AB1234")
    monkeypatch.setattr(settings, "KITE_PASSWORD", "pw")
    monkeypatch.setattr(settings, "KITE_TOTP_SECRET", "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ")
    monkeypatch.setattr(settings, "KITE_AUTO_LOGIN_AT", "08:00")


def test_totp_matches_rfc6238_vectors():
    # RFC 6238 SHA-1 test vectors, last 6 digits
    assert totp("GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ", at=59) == "287082"
    assert totp("GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ", at=1111111109) == "081804"
    assert totp("gezd gnbv gy3t qojq gezd gnbv gy3t qojq", at=59) == "287082"


def fake_zerodha(password_ok=True, totp_ok=True, gives_token=True):
    seen = {}

    def handler(req: httpx.Request):
        path = req.url.path
        if path == "/connect/login":
            if seen.get("twofa"):
                return httpx.Response(302, headers={"location": "/connect/finish?sess_id=1"})
            return httpx.Response(200, text="login page")
        if path == "/api/login":
            seen["form"] = req.content.decode()
            if not password_ok:
                return httpx.Response(403, json={"status": "error", "message": "Invalid password"})
            return httpx.Response(200, json={"status": "success", "data": {"request_id": "r1"}})
        if path == "/api/twofa":
            if not totp_ok:
                return httpx.Response(403, json={"status": "error", "message": "Invalid TOTP"})
            seen["twofa"] = True
            return httpx.Response(200, json={"status": "success", "data": {}})
        if path == "/connect/finish":
            if not gives_token:
                return httpx.Response(200, text="authorize this app")
            return httpx.Response(302, headers={"location": "https://api.example/admin/kite/callback?request_token=TOKEN42&status=success"})
        return httpx.Response(404)

    return httpx.MockTransport(handler), seen


def test_full_login_returns_request_token():
    transport, seen = fake_zerodha()
    assert fetch_request_token(LOGIN_URL, transport) == "TOKEN42"
    assert "user_id=AB1234" in seen["form"]


@pytest.mark.parametrize("kw", [{"password_ok": False}, {"totp_ok": False}, {"gives_token": False}])
def test_rejections_are_not_retried(kw):
    transport, _ = fake_zerodha(**kw)
    with pytest.raises(AutoLoginError) as e:
        fetch_request_token(LOGIN_URL, transport)
    assert e.value.retry is False
    assert "pw" not in str(e.value).split(":")[0]  # never echo the password


def test_login_due_once_a_day_after_the_set_time():
    at = lambda h, m: datetime(2026, 9, 24, h, m, tzinfo=IST)
    assert not login_due(at(7, 59), "2026-09-23")
    assert login_due(at(8, 0), "2026-09-23")
    assert login_due(at(14, 0), None)
    assert not login_due(at(9, 0), "2026-09-24")


def test_run_once_saves_token_then_calls_on_login(monkeypatch):
    calls = []

    class FakeKite:
        token_day = None
        kite = type("K", (), {"login_url": staticmethod(lambda: LOGIN_URL)})()

        def accept_request_token(self, rt):
            calls.append(("token", rt))

    monkeypatch.setattr(kite_auto, "fetch_request_token", lambda url: "TOKEN42")
    al = kite_auto.AutoLogin(FakeKite(), lambda: calls.append(("on_login",)))
    al.run_once()
    assert calls == [("token", "TOKEN42"), ("on_login",)]
    assert al.last["ok"] is True


def test_rejected_login_stops_retries_for_the_day(monkeypatch):
    def boom(url):
        raise AutoLoginError("bad password", retry=False)

    monkeypatch.setattr(kite_auto, "fetch_request_token", boom)
    al = kite_auto.AutoLogin(type("K", (), {"kite": type("C", (), {"login_url": staticmethod(lambda: LOGIN_URL)})()})(), lambda: None)
    with pytest.raises(AutoLoginError):
        al.run_once()
    assert al._gave_up and al.last["ok"] is False


@pytest.mark.parametrize("raw", [
    "gezd gnbv gy3t qojq gezd gnbv gy3t qojq",
    '"GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"',
    "otpauth://totp/Kite:AB1234?secret=GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ&issuer=Kite",
])
def test_secret_accepted_in_common_pasted_forms(raw):
    assert totp(raw, at=59) == "287082"


@pytest.mark.parametrize("raw", ["481920", "", "not a secret!"])
def test_invalid_secret_is_a_clear_non_retryable_error(raw):
    with pytest.raises(AutoLoginError) as e:
        totp(raw)
    assert e.value.retry is False and "KITE_TOTP_SECRET" in str(e.value)


def test_invalid_secret_fails_before_contacting_zerodha(monkeypatch):
    monkeypatch.setattr(settings, "KITE_TOTP_SECRET", "123456")
    calls = []
    transport = httpx.MockTransport(lambda req: calls.append(req) or httpx.Response(500))
    with pytest.raises(AutoLoginError):
        fetch_request_token(LOGIN_URL, transport)
    assert calls == []
