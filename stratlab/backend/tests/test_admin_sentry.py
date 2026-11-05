"""Admin → System: "Error alerts (Sentry): on / off" from the SDK itself, and an admin-only "Send a test error" that sends one
harmless message through app/errors.py, at most three an hour, and says whether Sentry was on (owner, 4 Nov)."""
import re

import pytest
import sentry_sdk

from app import errors, main
from tests import world as W
from tests.fake_db import headers

ADMIN = headers("admin-token")


@pytest.fixture
def w(monkeypatch):
    world = W.build(monkeypatch)
    with main._recent_lock:                 # the throttle is per process: start this admin's count at zero
        for k in [k for k in main._recent if k[1] == "admin_sentry_test"]:
            del main._recent[k]
    yield world
    world["close"]()


def _sentry(monkeypatch, on: bool) -> list:
    sent = []
    monkeypatch.setattr(sentry_sdk, "is_initialized", lambda: on)
    monkeypatch.setattr(sentry_sdk, "capture_message", lambda text, level=None, **k: sent.append((text, level)))
    return sent


def test_the_system_status_says_whether_sentry_is_on(w, monkeypatch):
    c = w["client"]
    _sentry(monkeypatch, False)
    assert c.get("/admin/overview", headers=ADMIN).json()["server"]["sentry"] is False
    _sentry(monkeypatch, True)
    assert c.get("/admin/overview", headers=ADMIN).json()["server"]["sentry"] is True
    assert errors.enabled() is True


def test_a_test_error_is_one_harmless_message_and_says_sentry_was_on(w, monkeypatch):
    c = w["client"]
    sent = _sentry(monkeypatch, True)
    r = c.post("/admin/sentry/test", headers=ADMIN)
    assert r.status_code == 200
    body = r.json()
    assert body["sentry_on"] is True
    assert re.fullmatch(r"StratLab test error from Admin, \d\d \w{3} \d{4} \d\d:\d\d:\d\d IST", body["message"]), body["message"]
    assert sent == [(body["message"], "error")]          # exactly one message, no exception raised anywhere


def test_with_sentry_off_nothing_is_sent_and_the_answer_says_so(w, monkeypatch):
    c = w["client"]
    sent = _sentry(monkeypatch, False)
    body = c.post("/admin/sentry/test", headers=ADMIN).json()
    assert body["sentry_on"] is False and sent == []
    assert errors.test_message("x") is False and errors.enabled() is False


def test_test_errors_are_throttled_to_three_an_hour(w, monkeypatch):
    c = w["client"]
    sent = _sentry(monkeypatch, True)
    for _ in range(main.TEST_ERRORS_HOUR):
        assert c.post("/admin/sentry/test", headers=ADMIN).status_code == 200
    r = c.post("/admin/sentry/test", headers=ADMIN)
    assert r.status_code == 429 and "3 test errors this hour" in r.json()["detail"]["message"]
    assert len(sent) == 3


def test_only_admins_can_send_a_test_error(w, monkeypatch):
    sent = _sentry(monkeypatch, True)
    for who in ("pro-token", "free-token"):
        assert w["client"].post("/admin/sentry/test", headers=headers(who)).status_code == 403
    assert w["client"].post("/admin/sentry/test").status_code in (401, 403)
    assert sent == []


def test_a_broken_sdk_never_breaks_the_page(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("sdk broken")
    monkeypatch.setattr(sentry_sdk, "is_initialized", boom)
    assert errors.enabled() is False and errors.test_message("x") is False
