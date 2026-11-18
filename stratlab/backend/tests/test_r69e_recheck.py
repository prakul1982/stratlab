"""Lane r69e hotfix (live Release 72 = R68, Railway logs 10:50-11:30 UTC): the theme re-check job.

1. "theme re-check: <theme>: failed (its dive was not kept); N left" for nine themes, put back on the queue again and again (25-27 left):
   the job read the dive's key off the library's stored read without today's market values, while the rebuild and the page key it with
   them (theme_routes.checked: the figures' window follows the market values), so a dive kept every time was never found. A theme that
   fails the same way twice is left with why, not looped.
2. "US restaurant: failed (its checks are not finished yet)" every ~4 min: tried again at once, each page view moving it to the front.
   Now it waits for its checks (WAIT_FIRST, doubling) and a page view does not move a waiting or left theme.
3. memguard: page-prices, stock-desks, screens-index and corp-actions waited 20-129 s for the theme re-check: the re-check takes the turn
   only when no other job holds or waits for it, phase by phase, and yields otherwise.
"""
import threading
import time

from app import computed, memguard
from app.intel import theme_library, theme_recheck, theme_routes
from tests.test_r66e_fixes import keep, payload, w  # noqa: F401 (the stored-library fixture)


def test_a_dive_kept_under_the_key_the_page_reads_is_current(w, monkeypatch):
    """Fails before: with today's market values changing the figures' window (and so the dive key's count of described companies), the
    rebuild kept the dive under the page's key and the job looked under the stored read's: "failed (its dive was not kept)" each pass."""
    keep("ships", payload("Ships"))
    real = theme_routes.checked

    def with_todays_values(region, theme, m, wait=False):       # today's market values: one more company described in the figures' window
        got = real(region, theme, m, wait)
        return {**got, "placements": {**(got.get("placements") or {}), "placed": (got.get("placements") or {}).get("placed", 0) + 1}}
    monkeypatch.setattr(theme_routes, "checked", with_todays_values)
    p = theme_library.stored("IN", "ship")["payload"]
    m = theme_routes.with_descriptions("IN", theme_routes.checked("IN", "ship", {**p, "_library": "ship"}))
    key = theme_routes.dive_key("IN", "ship", m)
    computed.put(theme_library.DIVE, key, {"dive": {"sector": "Ships", "layers": []}, "pieces": {}}, label="Ships", region="IN",
                 meta={"q": "ship", "rules": 0})
    assert theme_recheck.current("IN", "ship")
    theme_recheck.queue()
    assert theme_recheck.step(lambda *a: (_ for _ in ()).throw(AssertionError("rebuilt again")))["outcome"] == "current"


def test_a_theme_that_fails_the_same_way_twice_is_left_with_why(w, monkeypatch):
    """Fails before: a theme whose rebuild failed went back to the end of the queue, TRIES times, each pass, whatever the reason."""
    keep("ships", payload("Ships"))
    theme_recheck.queue()
    called = []

    def broken(region, name):
        called.append(name)
        raise RuntimeError("the dive builder broke")
    outs = []
    while (x := theme_recheck.step(broken)) is not None:
        outs.append(x["outcome"])
    assert called == ["ship", "ship"] and outs == ["failed", "failed"]
    left = theme_recheck.state()["left"]["IN|ship"]
    assert left.startswith("failed the same way twice") and "the dive builder broke" in left
    # a page's view of it does not put it back on the queue (it was every few minutes)
    assert theme_recheck.ask("IN", "ship") is False and theme_recheck._load()["todo"] == []


def test_a_theme_whose_checks_are_not_finished_waits_for_them_and_a_view_does_not_hurry_it(w, monkeypatch):
    """Fails before: "its checks are not finished yet" put it back at the end of the queue and the next pass, or a page's view moving it to the
    front, tried it again at once (live: every ~4 min)."""
    keep("rail", payload("Rail"))
    theme_recheck.queue()
    called = []

    def unfinished(region, name):
        called.append(name)
        raise theme_recheck.NotDone("its checks are not finished yet", later=True)
    t0 = 10_000.0
    assert theme_recheck.step(unfinished, now=t0)["outcome"] == "waiting"
    theme_recheck._asked.clear()
    assert theme_recheck.ask("IN", "rail", now=t0 + 5) is True            # still being checked: said so, not hurried
    assert theme_recheck.step(unfinished, now=t0 + 60) is None and called == ["rail"]
    assert theme_recheck.step(unfinished, now=t0 + theme_recheck.WAIT_FIRST + 1)["outcome"] == "waiting" and called == ["rail", "rail"]
    # the second wait is twice the first
    assert theme_recheck.step(unfinished, now=t0 + 2 * theme_recheck.WAIT_FIRST + 2) is None


def test_the_recheck_takes_the_turn_only_when_no_other_job_holds_or_waits_for_it():
    """Fails before: the re-check held the memory guard's turn for a whole theme, and the price jobs queued behind it 20-129 s."""
    held, release = threading.Event(), threading.Event()

    def price_job():
        with memguard.heavy("page-prices"):
            held.set()
            release.wait(5)
    t = threading.Thread(target=price_job)
    t.start()
    held.wait(5)
    began = time.monotonic()
    try:
        with memguard.heavy_idle("theme re-check: dive", 0.3) as got:
            assert got is False                         # another job has the turn: the re-check gives way
    finally:
        release.set()
        t.join(5)
    assert time.monotonic() - began < 2
    with memguard.heavy_idle("theme re-check: dive", 1.0) as got:
        assert got is True                              # free: it takes its turn
    # a rebuild's phase that cannot get the turn yields: the theme stays first, its tries not counted
    st_before = memguard.TURNS.name
    assert st_before is None


def test_a_yielded_rebuild_keeps_its_place_uncounted(w, monkeypatch):
    keep("ships", payload("Ships"))
    keep("rail", payload("Rail"))
    theme_recheck.queue()
    first = theme_recheck._load()["todo"][0]

    def busy(region, name):
        raise theme_recheck.Yielded("the dive gave way to other jobs")
    assert theme_recheck.step(busy)["outcome"] == "yielded"
    st = theme_recheck._load()
    assert st["todo"][0] == first and f"{first[0]}|{first[1]}" not in (st.get("failed") or {})
