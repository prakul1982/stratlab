"""Telegram alerts reach only a chat whose 6-digit code the user entered: sending the code, wrong tries, expiry, the
hourly limit, delivery only to the verified chat, and a changed chat starting over."""
import re
import time

import pytest

from app import alerts, db, main
from app.config import settings
from tests import world

ME = "u-pro"


@pytest.fixture
def w(monkeypatch):
    built = world.build(monkeypatch)
    monkeypatch.setattr(settings, "TELEGRAM_BOT_TOKEN", "t")
    main._recent.clear()
    msgs = []
    monkeypatch.setattr(alerts, "send_telegram", lambda chat, text: msgs.append((chat, text)))
    prof = {"id": ME, "_plan": "pro", "plan": "pro", "telegram_chat_id": None}
    saved = []

    def update(uid, **f):
        saved.append(f)
        prof.update(f)
    monkeypatch.setattr(db, "update_profile", update)
    main.app.dependency_overrides[main.current_profile] = lambda: prof
    built.update(msgs=msgs, prof=prof)
    yield built
    main.app.dependency_overrides.clear()
    built["close"]()


def save(w, chat):
    return w["client"].put("/me/alerts", json={"alerts_enabled": True, "telegram_chat_id": chat})


def code_of(w):
    return re.search(r"code: (\d{6})\.", w["msgs"][-1][1]).group(1)


def verify(w, code):
    return w["client"].post("/me/alerts/telegram/verify", json={"code": code})


def test_saving_a_chat_sends_one_code_and_stays_off(w):
    assert save(w, "123").json()["telegram_code_sent"] is True
    assert len(w["msgs"]) == 1 and w["msgs"][0][0] == "123"
    assert w["msgs"][0][1].endswith("If you didn't ask for this, ignore it.")
    assert not alerts.telegram_verified(w["prof"])
    assert alerts.jobs_for(w["prof"], "s", "t") == []
    assert verify(w, code_of(w)).status_code == 200
    assert alerts.telegram_verified(w["prof"]) and [c for c, _ in alerts.jobs_for(w["prof"], "s", "t")] == ["telegram"]


def test_saving_the_same_chat_again_sends_nothing(w):
    save(w, "123")
    verify(w, code_of(w))
    assert save(w, "123").json()["telegram_code_sent"] is None
    assert len(w["msgs"]) == 1 and alerts.telegram_verified(w["prof"])


def test_wrong_code_and_five_wrong_tries_void_it(w):
    save(w, "123")
    good = code_of(w)
    bad = "000000" if good != "000000" else "111111"
    for _ in range(5):
        assert verify(w, bad).status_code == 400
    assert verify(w, good).status_code == 400            # voided: even the right code no longer works
    assert not alerts.telegram_verified(w["prof"])
    assert w["client"].post("/me/alerts/telegram/code").status_code == 200
    assert verify(w, code_of(w)).status_code == 200


def test_code_expires_after_15_minutes(w, monkeypatch):
    save(w, "123")
    code = code_of(w)
    real = time.time()
    monkeypatch.setattr(alerts.time, "time", lambda: real + 16 * 60)
    assert verify(w, code).status_code == 400
    assert not alerts.telegram_verified(w["prof"])


def test_five_code_sends_an_hour(w):
    save(w, "123")
    for _ in range(4):
        assert w["client"].post("/me/alerts/telegram/code").status_code == 200
    assert w["client"].post("/me/alerts/telegram/code").status_code == 429
    assert len(w["msgs"]) == 5


def test_changing_or_clearing_the_chat_resets_verification(w):
    save(w, "123")
    verify(w, code_of(w))
    assert save(w, "456").json()["telegram_code_sent"] is True
    assert w["msgs"][-1][0] == "456" and not alerts.telegram_verified(w["prof"])
    assert alerts.jobs_for(w["prof"], "s", "t") == []
    verify(w, code_of(w))
    assert alerts.telegram_verified(w["prof"])
    w["client"].put("/me/alerts", json={"alerts_enabled": False, "telegram_chat_id": ""})
    w["prof"]["telegram_chat_id"] = "456"           # the same id typed again is a new chat to confirm
    assert not alerts.telegram_verified(w["prof"])


def test_a_chat_saved_before_codes_existed_is_unverified(w):
    w["prof"]["telegram_chat_id"] = "789"
    assert not alerts.telegram_verified(w["prof"])
    assert alerts.test(w["prof"]) == ([], {})
