"""MEM-3: why the process stayed near 1 GB after the day's peaks, and what it now does about it. Measured on a replay of the
day's jobs (nothing here repeats that): the census sees only what the garbage collector tracks, Python's own arenas kept
~300 MB after the peaks, and a cache budget counted a page with a rupee sign at half its size."""
import json
import sys
from pathlib import Path

import httpx
import pytest

from app import memguard
from app.intel import net
from tests import world

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def w(monkeypatch):
    from tests import world as W
    built = W.build(monkeypatch)
    yield built
    built["close"]()


def test_the_start_command_keeps_pythons_small_objects_in_malloc_and_one_worker():
    for name in ("Procfile", "railway.json"):
        text = (ROOT / name).read_text(encoding="utf-8")
        cmd = next(line for line in text.splitlines() if "uvicorn" in line)
        # a variable of the same name overrides it (rolling back is a variable, not a deploy of code)
        assert "PYTHONMALLOC=${PYTHONMALLOC:-malloc} uvicorn app.main:app" in cmd, name
        assert "--workers 1" in cmd and "--timeout-keep-alive" in cmd, name
    assert json.loads((ROOT / "railway.json").read_text(encoding="utf-8"))["deploy"]["startCommand"].startswith("PYTHONMALLOC=")


def test_the_allocators_in_use_are_reported(monkeypatch):
    monkeypatch.setenv("PYTHONMALLOC", "malloc")
    got = memguard.allocators()
    assert got["pymalloc"] is False and got["malloc"] in ("glibc", "jemalloc", "unknown")
    monkeypatch.delenv("PYTHONMALLOC")
    assert memguard.allocators()["pymalloc"] is True
    monkeypatch.setenv("MALLOC_CONF", "narenas:2")
    assert memguard.allocators()["malloc_conf"] == "narenas:2"


def test_pythons_own_arenas_are_measured_only_while_they_are_in_use(monkeypatch):
    monkeypatch.delenv("PYTHONMALLOC", raising=False)
    held = [str(i) * 3 for i in range(200_000)]
    got = memguard.python_heap()
    assert got is not None
    assert got["arenas_mb"] >= got["used_mb"] >= 10 and got["wasted_mb"] >= 0
    assert got["wasted_mb"] == pytest.approx(got["arenas_mb"] - got["used_mb"], abs=0.2)
    assert held
    monkeypatch.setenv("PYTHONMALLOC", "malloc")
    assert memguard.python_heap() is None


def test_stderr_is_back_after_the_measure(capfd):
    memguard.python_heap()
    print("after", file=sys.stderr)
    assert "after" in capfd.readouterr().err


def test_resident_memory_is_split_into_anonymous_and_file_backed():
    got = memguard.rss_split()
    if not got:
        pytest.skip("no /proc/self/smaps_rollup here")
    assert got["rss_mb"] > 0 and got["anon_mb"] > 0
    assert got["file_mb"] == pytest.approx(got["rss_mb"] - got["anon_mb"], abs=0.2)


def test_a_page_with_a_rupee_sign_is_counted_at_the_two_bytes_a_character_it_takes():
    plain, rupee = "a" * 10_000, "₹" * 10_000
    assert sys.getsizeof(rupee) >= 2 * len(rupee)
    assert net.approx_size(rupee) >= 2 * len(rupee) > net.approx_size(plain) + 9_000
    assert net.approx_size(["a" * 100, {"k": "₹" * 100}]) >= 100 + 200


def test_a_source_counts_the_page_it_holds_not_the_bytes_that_came():
    page = "<p>" + "₹ 1,400 " * 20_000 + "</p>"            # 3 bytes a rupee sign on the wire, two in memory (and 1 for the rest)
    s = net.Source("http://x.test", transport=httpx.MockTransport(lambda r: httpx.Response(200, content=page.encode("utf-8"))))
    assert s.fetch("/p", kind="text") == page
    assert s.cache.bytes >= sys.getsizeof(page)
    emoji = "<p>" + "ok 😀 " * 20_000 + "</p>"             # four bytes a character in memory once there is one in it
    s2 = net.Source("http://x.test", transport=httpx.MockTransport(lambda r: httpx.Response(200, content=emoji.encode("utf-8"))))
    s2.fetch("/e", kind="text")
    assert s2.cache.bytes >= 4 * len(emoji)


def test_the_caches_are_listed_by_name_largest_first(monkeypatch):
    from app import screens
    big, small = net.TTLCache(max_items=10), net.TTLCache(max_items=10)
    big.set("a", "x" * 3_000_000, 60)
    small.set("a", "y" * 1_000, 60)

    class Holder:
        def __init__(self):
            self.inner = type("Inner", (), {})()
            self.inner.cache = big

    monkeypatch.setattr(screens, "_mem3_probe", Holder(), raising=False)          # one held in a field of a field
    monkeypatch.setattr(screens, "_mem3_small", small, raising=False)             # one held by the module itself
    got = memguard.named_caches(top=500)
    names = [c["name"] for c in got]
    assert "app.screens._mem3_probe.inner.cache" in names and "app.screens._mem3_small" in names
    assert names.index("app.screens._mem3_probe.inner.cache") < names.index("app.screens._mem3_small")
    row = next(c for c in got if c["name"] == "app.screens._mem3_probe.inner.cache")
    assert row["items"] == 1 and row["mb"] >= 2.8
    assert [c["mb"] for c in got] == sorted((c["mb"] for c in got), reverse=True)


def test_admin_memory_names_the_allocators_and_with_detail_the_split(w):
    c = w["client"]
    plain = c.get("/admin/memory", headers=world.headers("admin-token")).json()
    assert plain["allocators"]["malloc"] and "pymalloc" in plain["allocators"] and "census" not in plain
    full = c.get("/admin/memory?detail=true", headers=world.headers("admin-token")).json()["census"]
    # the census says what the collector tracks; what Python holds in all is its own figure beside it
    assert full["tracked_mb"] > 0 and "python_heap" in full and "rss_split" in full and isinstance(full["caches"], list)
    assert all({"name", "items", "mb"} <= set(row) for row in full["caches"])
    assert c.get("/admin/memory?detail=true", headers=world.headers("pro-token")).status_code in (401, 403)
