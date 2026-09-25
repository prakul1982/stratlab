import sys
from types import SimpleNamespace

import pytest

from app import alerts, db, live, push
from app.config import settings


@pytest.fixture
def kv(monkeypatch):
    store = {}
    monkeypatch.setattr(db, "set_setting", lambda k, v: store.__setitem__(k, v))
    monkeypatch.setattr(db, "get_setting", lambda k: store.get(k))
    monkeypatch.setattr(db, "delete_setting", lambda k: store.pop(k, None))
    monkeypatch.setattr(settings, "VAPID_PUBLIC_KEY", "pub")
    monkeypatch.setattr(settings, "VAPID_PRIVATE_KEY", "priv")
    return store


SUB = lambda n: {"endpoint": f"https://push.example/{n}", "keys": {"p256dh": "k", "auth": "a"}}


def test_devices_are_remembered_once_and_dead_ones_forgotten(kv, monkeypatch):
    push.add("u1", SUB(1)); push.add("u1", SUB(1)); push.add("u1", SUB(2))
    assert [s["endpoint"] for s in push.devices("u1")] == ["https://push.example/1", "https://push.example/2"]
    sent = []

    class Gone(Exception):
        def __init__(self):
            self.response = SimpleNamespace(status_code=410)

    def webpush(subscription_info, **kw):
        if subscription_info["endpoint"].endswith("/2"):
            raise fake.WebPushException()
        sent.append((subscription_info["endpoint"], kw["data"]))

    fake = SimpleNamespace(webpush=webpush, WebPushException=Gone)
    monkeypatch.setitem(sys.modules, "pywebpush", fake)
    assert push.send("u1", "EMA: BUY BTC", "Bought 0.1 BTC", "/paper/x") == 1
    assert '"url": "/paper/x"' in sent[0][1]
    assert [s["endpoint"] for s in push.devices("u1")] == ["https://push.example/1"]      # the gone device is dropped
    push.remove("u1", "https://push.example/1")
    assert push.devices("u1") == [] and "push:u1" not in kv


def test_push_is_a_channel_for_alerts_and_the_report(kv, monkeypatch):
    calls = []
    monkeypatch.setattr(push, "send", lambda *a, **k: calls.append(a) or 1)
    assert alerts.notify({"id": "u1"}, "s", "t", background=False) == []                  # no device yet
    push.add("u1", SUB(1))
    assert alerts.notify({"id": "u1"}, "Daily report", "text", background=False) == ["push"] and calls
    assert live.report_on({"id": "u1", "plan": "free"})                                    # early access: plan allows it
    monkeypatch.setattr(push, "keys", lambda: None)                                        # no keys at all: push is off
    assert not push.enabled() and not live.report_on({"id": "u1", "plan": "free"})


def test_keys_are_made_once_saved_and_sign_real_pushes(kv, monkeypatch):
    monkeypatch.setattr(settings, "VAPID_PUBLIC_KEY", "")
    monkeypatch.setattr(settings, "VAPID_PRIVATE_KEY", "")
    monkeypatch.setattr(push, "_cache", {})
    pub, priv = push.keys()
    assert push.enabled() and push.public_key() == pub and len(pub) == 87 and "vapid:keys" in kv
    monkeypatch.setattr(push, "_cache", {})                                                # a restart reads the saved pair
    assert push.keys() == (pub, priv)

    import requests
    from py_vapid import b64urlencode
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import serialization
    dev = ec.generate_private_key(ec.SECP256R1())                                         # a browser's own key pair
    p256 = b64urlencode(dev.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint))
    posted = []
    monkeypatch.setattr(requests, "post", lambda url, **kw: posted.append((url, kw["headers"])) or SimpleNamespace(status_code=201, text="", headers={}))
    push.add("u1", {"endpoint": "https://fcm.googleapis.com/fcm/send/abc", "keys": {"p256dh": p256, "auth": "tBHItJI5svbpez7KI4CCXg"}})
    assert push.send("u1", "StratLab", "hello") == 1
    assert posted and f"k={pub}" in posted[0][1]["Authorization"].replace(" ", "")


def test_unset_channels_are_skipped_and_tests_report_each_channel(kv, monkeypatch):
    monkeypatch.setattr(settings, "SMTP_HOST", ""); monkeypatch.setattr(settings, "TELEGRAM_BOT_TOKEN", "t")
    prof = {"id": "u1", "alert_email": "a@b.c", "telegram_chat_id": "42"}
    sent = []
    monkeypatch.setattr(alerts, "send_telegram", lambda chat, text: sent.append(("tg", chat)))
    monkeypatch.setattr(alerts, "send_email", lambda *a: (_ for _ in ()).throw(AssertionError("email must be skipped")))
    assert alerts.notify(prof, "s", "t", background=False) == ["telegram"] and sent == [("tg", "42")]   # no SMTP: email skipped
    assert alerts.ready_channels()["email"] is False
    def boom(chat, text):
        raise RuntimeError("Telegram refused the message (400).")
    monkeypatch.setattr(alerts, "send_telegram", boom)
    push.add("u1", SUB(1))
    monkeypatch.setattr(push, "send", lambda *a, **k: 1)
    ok, failed = alerts.test(prof)
    assert ok == ["push"] and failed == {"telegram": "Telegram refused the message (400)."}          # one failure doesn't block the rest
