"""The stored company pages ("stocks:" settings) are read from the database once and kept in memory (app/db.py), so the
screens index, the price refresh, the sitemaps and every page view stop pulling them out of the database again and
again (the free plan's egress ran over: 9.6 GB of 5 GB)."""
import threading
import time

import pytest

from app import db
from tests.fake_db import FakeSupabase


class Counting(FakeSupabase):
    """Counts the reads of app_settings."""
    def __init__(self):
        super().__init__()
        self.reads = 0

    def table(self, name):
        q = super().table(name)
        if name == "app_settings":
            real = q.execute

            def execute():
                if q.op == "select":
                    self.reads += 1
                return real()
            q.execute = execute
        return q


@pytest.fixture
def fake(monkeypatch):
    f = Counting()
    monkeypatch.setattr(db, "_client", f)
    return f


def test_the_pages_are_read_once_then_served_from_memory(fake):
    for s in ("AAA", "BBB", "CCC"):
        db.set_setting(f"stocks:page:IN:{s}", f'{{"s": "{s}"}}')
    fake.reads = 0
    for _ in range(5):
        assert [k for k, _ in db.all_settings_with_prefix("stocks:page:IN:")] == [f"stocks:page:IN:{s}" for s in ("AAA", "BBB", "CCC")]
        assert db.get_setting("stocks:page:IN:BBB") == '{"s": "BBB"}'
        assert db.get_setting("stocks:page:IN:NONE") is None
    assert fake.reads == 1                           # one full read; everything after it from memory


def test_writes_and_deletes_reach_the_copy(fake):
    db.set_setting("stocks:page:US:X", "1")
    assert dict(db.all_settings_with_prefix("stocks:page:US:")) == {"stocks:page:US:X": "1"}
    db.set_setting("stocks:page:US:X", "2")
    db.set_setting("stocks:page:US:Y", "3")
    db.delete_setting("stocks:thin:US:Z")
    assert dict(db.all_settings_with_prefix("stocks:page:US:")) == {"stocks:page:US:X": "2", "stocks:page:US:Y": "3"}
    db.delete_setting("stocks:page:US:X")
    assert db.get_setting("stocks:page:US:X") is None
    assert dict(db.all_settings_with_prefix("stocks:")) == {"stocks:page:US:Y": "3"}
    # and the database itself holds the same
    db.forget_mirror()
    assert dict(db.all_settings_with_prefix("stocks:")) == {"stocks:page:US:Y": "3"}


def test_other_settings_still_go_to_the_database(fake):
    db.set_setting("screens:index:IN", "x")
    fake.reads = 0
    db.get_setting("screens:index:IN")
    db.get_setting("screens:index:IN")
    assert fake.reads == 2


def test_the_copy_is_read_again_after_a_while_and_for_another_database(fake, monkeypatch):
    db.set_setting("stocks:page:IN:A", "1")
    db.get_setting("stocks:page:IN:A")
    fake.reads = 0
    clock = [db.time.monotonic() + db.MIRROR_FOR + 1]
    monkeypatch.setattr(db.time, "monotonic", lambda: clock[0])
    db.get_setting("stocks:page:IN:A")
    _wait_reloaded()
    assert fake.reads == 1                           # stale: read again (picks up writes made elsewhere), in the background
    other = Counting()
    monkeypatch.setattr(db, "_client", other)
    assert db.get_setting("stocks:page:IN:A") is None    # a different database: its own rows
    assert other.reads == 1


def _wait_reloaded(timeout=2.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        with db._mirror_lock:
            if not db._mirror_reloading:
                return
        time.sleep(0.002)
    raise AssertionError("the background read never finished")


def _seed_copy(fake, monkeypatch, rows):
    """A copy read now, then the clock moved past its age."""
    for k, v in rows.items():
        db.set_setting(k, v)
    db.all_settings_with_prefix("stocks:")
    fake.reads = 0
    clock = [time.monotonic() + db.MIRROR_FOR + 1]
    monkeypatch.setattr(db.time, "monotonic", lambda: clock[0])
    return clock


def test_a_stale_copy_is_served_while_one_background_read_runs(fake, monkeypatch):
    _seed_copy(fake, monkeypatch, {"stocks:page:IN:A": "1"})
    fake.tables["app_settings"] = [r if r["key"] != "stocks:page:IN:A" else {**r, "value": "2"}
                                   for r in fake.tables["app_settings"]]          # written by another container
    real = db._all_from_db
    started, go, calls = threading.Event(), threading.Event(), []

    def slow(prefix, page=1000):
        calls.append(prefix)
        started.set()
        go.wait(2)
        return real(prefix, page)
    monkeypatch.setattr(db, "_all_from_db", slow)
    assert db.get_setting("stocks:page:IN:A") == "1"          # served from the old copy at once
    started.wait(2)
    for _ in range(5):                                         # while the read runs: still the copy, and no second read
        assert db.get_setting("stocks:page:IN:A") == "1"
        assert dict(db.all_settings_with_prefix("stocks:page:")) == {"stocks:page:IN:A": "1"}
    go.set()
    _wait_reloaded()
    assert calls == ["stocks:"]
    assert db.get_setting("stocks:page:IN:A") == "2"          # the new read in place


def test_a_failed_background_read_keeps_the_old_copy(fake, monkeypatch, caplog):
    clock = _seed_copy(fake, monkeypatch, {"stocks:page:IN:A": "1", "stocks:page:IN:B": "2"})
    fake.fail = RuntimeError("db down")
    with caplog.at_level("ERROR", logger="app.db"):
        assert db.get_setting("stocks:page:IN:A") == "1"
        _wait_reloaded()
    assert "could not read stocks:" in caplog.text
    fake.fail = None
    assert db.get_setting("stocks:page:IN:A") == "1"          # never "nothing stored"
    assert dict(db.all_settings_with_prefix("stocks:")) == {"stocks:page:IN:A": "1", "stocks:page:IN:B": "2"}
    _wait_reloaded()
    assert fake.reads == 1                                     # the failed try counted; no retry inside MIRROR_RETRY
    clock[0] += db.MIRROR_RETRY + 1
    db.get_setting("stocks:page:IN:A")
    _wait_reloaded()
    assert fake.reads == 2                                     # tried again after the pause


def test_one_key_before_any_copy_is_read_alone(fake, monkeypatch):
    for s in ("AAA", "BBB"):
        db.set_setting(f"stocks:page:IN:{s}", s)
    db.forget_mirror()
    fake.reads = 0
    called = []
    real = db._all_from_db
    monkeypatch.setattr(db, "_all_from_db", lambda prefix, page=1000: called.append(prefix) or real(prefix, page))
    assert db.get_setting("stocks:page:IN:BBB") == "BBB"
    assert db.get_setting("stocks:page:IN:NONE") is None
    assert called == [] and fake.reads == 2                  # two single-key reads, no full read


def test_warm_mirror_reads_the_prefix_once(fake):
    db.set_setting("stocks:page:IN:A", "1")
    db.forget_mirror()
    fake.reads = 0
    db.warm_mirror()
    assert db.get_setting("stocks:page:IN:A") == "1"
    assert fake.reads == 1


def test_reload_mirror_keeps_serving_the_copy_and_reads_again(fake, monkeypatch):
    db.set_setting("stocks:page:IN:A", "1")
    db.all_settings_with_prefix("stocks:")
    fake.reads = 0
    gate = threading.Event()
    real = db._all_from_db
    monkeypatch.setattr(db, "_all_from_db", lambda p, page=1000: (gate.wait(2), real(p, page))[1])
    db.reload_mirror()
    assert db.get_setting("stocks:page:IN:A") == "1"          # not thrown away
    gate.set()
    _wait_reloaded()
    assert fake.reads == 1


def test_a_write_during_the_full_read_is_not_lost(fake, monkeypatch):
    db.set_setting("stocks:page:IN:OLD", "old")
    db.forget_mirror()
    real = db._all_from_db
    started, go = threading.Event(), threading.Event()

    def slow(prefix, page=1000):
        rows = real(prefix, page)                    # the read sees the database before the write below
        started.set()
        go.wait(5)
        return rows
    monkeypatch.setattr(db, "_all_from_db", slow)
    got = {}
    t = threading.Thread(target=lambda: got.update(dict(db.all_settings_with_prefix("stocks:"))))
    t.start()
    started.wait(5)
    db.set_setting("stocks:page:IN:NEW", "new")      # written while the read is on its way
    db.set_setting("stocks:page:IN:OLD", "newer")
    go.set()
    t.join(5)
    assert got == {"stocks:page:IN:NEW": "new", "stocks:page:IN:OLD": "newer"}


def test_a_failed_read_is_not_kept(fake):
    fake.fail = RuntimeError("db down")
    with pytest.raises(RuntimeError):
        db.all_settings_with_prefix("stocks:page:IN:")
    fake.fail = None
    db.set_setting("stocks:page:IN:A", "1")
    assert db.get_setting("stocks:page:IN:A") == "1"


def test_with_the_second_database_the_pages_live_there_and_the_copy_follows(fake, monkeypatch):
    """Once MARKET_DATABASE_URL is set, the company pages are market data (market_store.MARKET_PREFIXES): moved there
    with the rest, written there, and still served from the in-memory copy."""
    from app import market_store
    from app.config import settings
    from tests.test_storage import FakeStore
    db.set_setting("stocks:page:IN:OLD", "old")                  # written before the second database existed
    s = FakeStore()
    monkeypatch.setattr(settings, "MARKET_DATABASE_URL", "postgresql://second")
    market_store.use(s)
    try:
        assert market_store.move(db, s)["settings"] == 1
        assert s.get("stocks:page:IN:OLD") == "old"
        assert not [r for r in fake.tables.get("app_settings", []) if r["key"].startswith("stocks:")]
        db.forget_mirror()
        db.set_setting("stocks:page:IN:NEW", "new")               # written there, and into the copy
        assert s.get("stocks:page:IN:NEW") == "new"
        fake.reads = 0
        assert dict(db.all_settings_with_prefix("stocks:page:IN:")) == {"stocks:page:IN:NEW": "new", "stocks:page:IN:OLD": "old"}
        db.set_setting("stocks:page:IN:NEW", "newer")
        assert db.get_setting("stocks:page:IN:NEW") == "newer"
        assert fake.reads == 1                                    # one (now empty) read of the main database, then memory
    finally:
        market_store.use(None)


def test_a_delete_reaches_the_copy_even_when_the_main_database_fails_after_the_second(fake, monkeypatch):
    from app import market_store
    from app.config import settings
    from tests.test_storage import FakeStore
    s = FakeStore()
    monkeypatch.setattr(settings, "MARKET_DATABASE_URL", "postgresql://second")
    market_store.use(s)
    try:
        db.set_setting("stocks:page:IN:GONE", "1")
        assert db.get_setting("stocks:page:IN:GONE") == "1"
        fake.fail = RuntimeError("main db down")
        with pytest.raises(RuntimeError):
            db.delete_setting("stocks:page:IN:GONE")
        fake.fail = None
        assert s.get("stocks:page:IN:GONE") is None
        assert db.get_setting("stocks:page:IN:GONE") is None
    finally:
        market_store.use(None)
