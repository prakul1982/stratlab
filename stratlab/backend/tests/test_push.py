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
    monkeypatch.setattr(settings, "VAPID_PRIVATE_KEY", "")
    assert not push.enabled() and not live.report_on({"id": "u1", "plan": "free"})
