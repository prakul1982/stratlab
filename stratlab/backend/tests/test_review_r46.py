"""Round 46: the Zerodha connection says when Zerodha has cancelled its login, and when the login ends by itself."""
from datetime import datetime

import pytest

from app import main  # noqa: F401, I001  (first: the app loads the newsletters' routes)
from app import db
from app.kite_service import CANCELLED_KEY, IST, login_ends, token_mark, today_ist
from tests.test_connect import ADMIN, FakeKite, kite, kite_login, on   # noqa: F401  (fixtures)


@pytest.fixture
def w(monkeypatch):
    from tests import world
    built = world.build(monkeypatch)
    yield built
    built["close"]()


def _data_login(monkeypatch, user="AB1234", tok="DATA-TOKEN-TODAY"):
    monkeypatch.setattr(db.settings, "KITE_USER_ID", user)
    db.set_setting("kite_access_token", tok)
    db.set_setting("kite_token_day", today_ist())


def test_a_linked_login_zerodha_cancelled_is_not_connected_and_says_so(w, kite, monkeypatch):
    from app.connect import state
    c = w["client"]
    kite_login(c)
    state.update("u-admin", "kite", day="2020-01-01")
    _data_login(monkeypatch)
    v = c.get("/connect", headers=ADMIN).json()["kite"]
    assert v["live"] and v["ends_at"]                       # live on the data login's token, with its end time
    db.set_setting(CANCELLED_KEY, token_mark("DATA-TOKEN-TODAY"))   # Zerodha refused it (any container noted it)
    v = c.get("/connect", headers=ADMIN).json()["kite"]
    assert not v["live"] and v["expired"] and v["ends_at"] is None
    assert c.get("/holdings", headers=ADMIN).json()["zerodha"]["live"] is False
    db.set_setting("kite_access_token", "DATA-TOKEN-NEW")   # the next data login brings it back
    assert c.get("/connect", headers=ADMIN).json()["kite"]["live"] is True


def test_a_refused_own_login_stays_ended_though_its_day_is_today(w, kite):
    from app.connect import state
    c = w["client"]
    kite_login(c)
    assert c.get("/connect", headers=ADMIN).json()["kite"]["live"] is True
    FakeKite.fail = type("TokenException", (Exception,), {})("Incorrect `api_key` or `access_token`.")
    assert c.post("/connect/kite/refresh", headers=ADMIN).status_code == 409
    assert state.section("u-admin", "kite")["day"] == today_ist()
    v = c.get("/connect", headers=ADMIN).json()["kite"]
    assert not v["live"] and v["expired"]


def test_a_live_login_ends_at_the_next_six_in_the_morning():
    assert login_ends(datetime(2026, 10, 17, 23, 0, tzinfo=IST)) == datetime(2026, 10, 18, 6, 0, tzinfo=IST)
    assert login_ends(datetime(2026, 10, 18, 5, 0, tzinfo=IST)) == datetime(2026, 10, 18, 6, 0, tzinfo=IST)
    assert login_ends(datetime(2026, 10, 18, 6, 0, tzinfo=IST)) == datetime(2026, 10, 19, 6, 0, tzinfo=IST)


def test_a_cancelled_data_login_is_noted_for_every_container_and_kept_after_a_restart(monkeypatch):
    from app.kite_service import KiteService
    store = {"kite_access_token": "TOK-1", "kite_token_day": today_ist()}
    monkeypatch.setattr(db, "get_setting", lambda k: store.get(k))
    monkeypatch.setattr(db, "set_setting", lambda k, v: store.__setitem__(k, v))
    k = KiteService()
    k.load_saved_token()
    assert k.ready()
    k._token_rejected(Exception("token invalid"))
    assert not k.ready() and store[CANCELLED_KEY] == token_mark("TOK-1")
    again = KiteService()                                   # a restart: the same token is still refused
    again.load_saved_token()
    assert not again.ready() and again.invalid_reason


def test_a_kept_answer_comes_at_once_and_is_read_again_behind_it():
    import threading
    from app import swr
    swr.clear()
    reads, done = [], threading.Event()

    def read():
        reads.append(1)
        if len(reads) > 1:
            done.set()
        return len(reads)
    assert swr.get("k", read, now=1000) == 1                      # nothing kept: read now
    assert swr.get("k", read, fresh=3600, now=1000 + 60) == 1     # young: kept, no read
    t = __import__("time").time()
    assert swr.get("k", read, fresh=0, keep=86400, now=t + 10) == 1   # old: the kept one at once, read behind it
    assert done.wait(5) and swr.get("k", read, fresh=3600, now=__import__("time").time()) == 2


def test_a_failed_read_behind_keeps_the_old_answer():
    import time
    from app import swr
    swr.clear()
    assert swr.get("x", lambda: "old") == "old"
    swr.get("x", lambda: (_ for _ in ()).throw(RuntimeError("down")), fresh=0)
    time.sleep(0.2)
    assert swr.get("x", lambda: "new") == "old"
