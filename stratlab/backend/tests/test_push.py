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

    def update(key, fn, tries=10):                      # db.update_setting without a database: the new text, None to leave, REMOVE
        new = fn(store.get(key))
        if new is db.REMOVE:
            store.pop(key, None)
        elif new is not None:
            store[key] = new
        return store.get(key)
    monkeypatch.setattr(db, "update_setting", update)
    monkeypatch.setattr(db, "all_settings_with_prefix", lambda p: sorted((k, v) for k, v in store.items() if k.startswith(p)))
    monkeypatch.setattr(settings, "VAPID_PUBLIC_KEY", "pub")
    monkeypatch.setattr(settings, "VAPID_PRIVATE_KEY", "priv")
    return store


SUB = lambda n: {"endpoint": f"https://fcm.googleapis.com/fcm/send/{n}", "keys": {"p256dh": "k", "auth": "a"}}


def test_devices_are_remembered_once_and_dead_ones_forgotten(kv, monkeypatch):
    push.add("u1", SUB(1)); push.add("u1", SUB(1)); push.add("u1", SUB(2))
    assert [s["endpoint"] for s in push.devices("u1")] == ["https://fcm.googleapis.com/fcm/send/1", "https://fcm.googleapis.com/fcm/send/2"]
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
    assert [s["endpoint"] for s in push.devices("u1")] == ["https://fcm.googleapis.com/fcm/send/1"]      # the gone device is dropped
    push.remove("u1", "https://fcm.googleapis.com/fcm/send/1")
    assert push.devices("u1") == [] and "push:u1" not in kv


def test_push_is_a_channel_for_alerts_and_the_report(kv, monkeypatch):
    calls = []
    monkeypatch.setattr(push, "send", lambda *a, **k: calls.append(a) or 1)
    assert alerts.notify({"id": "u1"}, "s", "t", background=False) == []                  # no device yet
    push.add("u1", SUB(1))
    assert alerts.notify({"id": "u1"}, "Daily report", "text", background=False) == ["push"] and calls
    basic = {"id": "u1", "plan": "basic", "plan_status": "active"}
    assert live.report_on(basic)                                                           # the daily report is Basic
    assert not live.report_on({"id": "u1", "plan": "free"})                                # Free: not, payments on or not (7 Oct)
    monkeypatch.setattr(push, "keys", lambda: None)                                        # no keys at all: push is off
    assert not push.enabled() and not live.report_on(basic)


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
    assert ok == ["push"] and failed == {"telegram": "Telegram couldn't deliver to that chat"}          # one failure doesn't block the rest


def test_only_browser_push_services_are_accepted():
    ok = ["https://fcm.googleapis.com/fcm/send/x", "https://web.push.apple.com/abc", "https://updates.push.services.mozilla.com/wpush/v2/x",
          "https://wns2-par02p.notify.windows.com/w/?token=x"]
    bad = ["http://fcm.googleapis.com/x", "https://169.254.169.254/latest", "https://localhost/x", "https://evilfcm.googleapis.com.attacker.io/x",
           "https://user:pw@fcm.googleapis.com/x", "https://fcm.googleapis.com:8443/x", "https://notify.windows.com.evil/x", "not a url"]
    assert all(push.valid_endpoint(u) for u in ok)
    assert not any(push.valid_endpoint(u) for u in bad)


def test_a_push_is_given_ten_seconds_and_a_device_added_while_sending_is_kept(kv, monkeypatch):
    push.add("u1", SUB(1)); push.add("u1", SUB(2))
    seen = []

    class Gone(Exception):
        def __init__(self):
            self.response = SimpleNamespace(status_code=410)

    def webpush(subscription_info, **kw):
        seen.append(kw.get("timeout"))
        if subscription_info["endpoint"].endswith("/2"):
            push.add("u1", SUB(3))                       # a device is added from another request while this one is sending
            raise Gone()

    monkeypatch.setitem(sys.modules, "pywebpush", SimpleNamespace(webpush=webpush, WebPushException=Gone))
    push.send("u1", "t", "b")
    assert seen == [10, 10]                              # pywebpush's own default is no timeout at all
    assert [s["endpoint"][-1] for s in push.devices("u1")] == ["1", "3"]      # the gone one is dropped, the new one stays


def test_an_endpoint_belongs_to_the_last_user_who_subscribed_it(kv):
    push.add("u1", SUB(1)); push.add("u1", SUB(2)); push.add("u2", SUB(9))
    push.add("u3", SUB(1))                               # the same browser, signed in as someone else
    assert [s["endpoint"][-1] for s in push.devices("u1")] == ["2"]
    assert [s["endpoint"][-1] for s in push.devices("u3")] == ["1"] and [s["endpoint"][-1] for s in push.devices("u2")] == ["9"]
    push.remove("u3", SUB(1)["endpoint"]); push.remove("u1", SUB(2)["endpoint"])
    assert "push:u1" not in kv and "push:u3" not in kv
