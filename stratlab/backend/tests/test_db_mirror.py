"""The stored company pages ("stocks:" settings) are read from the database once and kept in memory (app/db.py), so the
screens index, the price refresh, the sitemaps and every page view stop pulling them out of the database again and
again (the free plan's egress ran over: 9.6 GB of 5 GB)."""
import threading

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
    assert fake.reads == 1                           # stale: read again (picks up writes made elsewhere)
    other = Counting()
    monkeypatch.setattr(db, "_client", other)
    assert db.get_setting("stocks:page:IN:A") is None    # a different database: its own rows
    assert other.reads == 1


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
