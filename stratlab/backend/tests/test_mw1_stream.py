"""MW-1: live prices over one shared broker connection. An instrument is subscribed when its first viewer arrives and let go a
short grace after its last leaves; a viewer's stream carries a symbol at most twice a second with the last price and the day's
volume; nothing is held for a viewer that left; and fifty viewers on twenty symbols stay small."""
import asyncio
import gc
import json
import time
import tracemalloc

import pytest

from app import watch_stream as WS


class FakeTicks:
    """The shared tick feed's surface: add, remove, started."""

    def __init__(self):
        self.listeners: dict[str, tuple[int, object]] = {}
        self.adds, self.removes = [], []
        self.started = True

    def add(self, lid, token, cb, full=False):
        self.listeners[lid] = (token, cb)
        self.adds.append(lid)

    def remove(self, lid):
        self.listeners.pop(lid, None)
        self.removes.append(lid)

    def tick(self, token, price, volume=None):
        for tok, cb in list(self.listeners.values()):
            if tok == token:
                cb({"instrument_token": token, "last_price": price, "volume_traded": volume})


TOKENS = {f"IN:S{i}": 1000 + i for i in range(60)}


def make(clock=None, timers=None):
    ticks = FakeTicks()
    hub = WS.StreamHub(ticks, lambda k: TOKENS.get(k), clock=clock or time.monotonic,
                       start_timer=(lambda after, fn: timers.append((after, fn))) if timers is not None else (lambda after, fn: None))
    return ticks, hub


def run(coro):
    return asyncio.run(coro)


def test_a_symbol_is_subscribed_for_its_first_viewer_and_dropped_after_the_last_one_leaves():
    now = [100.0]
    timers = []
    ticks, hub = make(clock=lambda: now[0], timers=timers)

    async def go():
        loop = asyncio.get_running_loop()
        a, live, poll = hub.open("u1", ["IN:S1", "IN:S2", "US:AAPL"], loop)
        assert live == ["IN:S1", "IN:S2"] and poll == ["US:AAPL"]                      # the broker's feed carries only its own
        b, live_b, _ = hub.open("u2", ["IN:S2", "IN:S3"], loop)
        return a, b
    a, b = run(go())
    assert sorted(ticks.adds) == ["watch:1001", "watch:1002", "watch:1003"]            # S2 was subscribed once, for two viewers
    hub.close(a)
    assert ticks.removes == [] and timers                                              # S2 still has a viewer; S1 waits out its grace
    assert hub.sweep(now[0] + 5) == 0 and ticks.removes == []                          # inside the grace: still subscribed
    assert hub.sweep(now[0] + WS.GRACE + 1) == 1 and ticks.removes == ["watch:1001"]
    hub.close(b)
    assert hub.sweep(now[0] + 2 * WS.GRACE) == 2
    assert sorted(ticks.removes) == ["watch:1001", "watch:1002", "watch:1003"]
    assert hub.stats() == {"streams": 0, "instruments": 0, "waiting": 0, "kept": 0}


def test_a_viewer_back_within_the_grace_keeps_the_subscription():
    now = [0.0]
    ticks, hub = make(clock=lambda: now[0], timers=[])

    async def go():
        loop = asyncio.get_running_loop()
        a, _, _ = hub.open("u1", ["IN:S1"], loop)
        hub.close(a)
        now[0] += 5
        b, _, _ = hub.open("u1", ["IN:S1"], loop)                                      # a chart switched from 1m to 5m
        return b
    b = run(go())
    assert hub.sweep(now[0] + WS.GRACE + 1) == 0 and ticks.removes == [] and ticks.adds == ["watch:1001"]
    hub.close(b)


def test_closing_twice_and_a_late_tick_do_nothing():
    ticks, hub = make(timers=[])

    async def go():
        a, _, _ = hub.open("u1", ["IN:S1"], asyncio.get_running_loop())
        hub.close(a)
        hub.close(a)
        ticks.tick(1001, 10.0)                                                          # a tick for an instrument nobody follows
        return a
    run(go())
    assert hub.stats()["streams"] == 0


def test_limits_on_streams_per_person_and_instruments_in_all():
    ticks, hub = make(timers=[])

    async def go():
        loop = asyncio.get_running_loop()
        for _ in range(WS.CONNS_PER_USER):
            assert hub.open("u1", ["IN:S1"], loop)[0] is not None
        conn, _, poll = hub.open("u1", ["IN:S1"], loop)
        assert conn is None and poll == ["IN:S1"]                                      # a fourth tab polls instead
        many, live, left = hub.open("u2", [f"IN:S{i}" for i in range(60)], loop)
        assert len(live) == WS.MAX_PER_CONN and len(left) == 60 - WS.MAX_PER_CONN
    run(go())
    old = (WS.MAX_TOKENS,)
    try:
        WS.MAX_TOKENS = 45
        ticks2, hub2 = make(timers=[])

        async def fill():
            loop = asyncio.get_running_loop()
            hub2.open("a", [f"IN:S{i}" for i in range(0, 40)], loop)
            _, live, poll = hub2.open("b", [f"IN:S{i}" for i in range(40, 60)], loop)
            assert len(live) == 5 and len(poll) == 15                                    # the feed's share is full: the rest poll
            assert hub2.stats()["instruments"] == 45
        run(fill())
    finally:
        WS.MAX_TOKENS = old[0]


def test_a_stream_sends_the_last_price_and_volume_at_most_twice_a_second():
    ticks, hub = make(timers=[])
    events = []

    async def go():
        loop = asyncio.get_running_loop()
        conn, live, poll = hub.open("u1", ["IN:S1"], loop)
        gen = hub.feed(conn, {"live": live, "poll": poll})

        async def read():
            async for chunk in gen:
                events.append((time.monotonic(), chunk))
                if len([e for e in events if "event: tick" in e[1]]) >= 3:
                    return
        task = asyncio.create_task(read())
        await asyncio.sleep(0.05)
        for i in range(40):                                                              # forty ticks in about 1.2 seconds
            ticks.tick(1001, 100 + i, 5000 + i * 10)
            await asyncio.sleep(0.03)
        await asyncio.wait_for(task, 5)
        await gen.aclose()
    run(go())
    assert events[0][1].startswith("event: hello")
    ticks_at = [t for t, c in events if "event: tick" in c]
    gaps = [b - a for a, b in zip(ticks_at, ticks_at[1:])]
    assert gaps and all(g >= WS.MIN_GAP - 0.03 for g in gaps), gaps                      # never more than two a second
    last = json.loads(events[-1][1].split("data: ")[1])
    assert last[0]["k"] == "IN:S1" and last[0]["v"] >= 5000 and last[0]["p"] >= 100 and last[0]["t"]
    # many ticks are folded into the newest price: fewer events than ticks
    assert len(ticks_at) < 40
    assert hub.stats()["streams"] == 0                                                   # the stream's end let go of the viewer


def test_a_new_viewer_is_given_the_last_price_at_once():
    ticks, hub = make(timers=[])
    got = []

    async def go():
        loop = asyncio.get_running_loop()
        first, _, _ = hub.open("u1", ["IN:S1"], loop)
        ticks.tick(1001, 250.5, 777)
        second, live, poll = hub.open("u2", ["IN:S1"], loop)
        gen = hub.feed(second, {"live": live, "poll": poll})
        async for chunk in gen:
            got.append(chunk)
            if len(got) == 2:
                break
        await gen.aclose()
        hub.close(first)
    run(go())
    assert got[0].startswith("event: hello") and '"p":250.5' in got[1] and '"v":777' in got[1]


def test_a_quiet_stream_sends_a_keepalive_and_ends_after_its_age(monkeypatch):
    ticks, hub = make(timers=[])
    monkeypatch.setattr(WS, "HEARTBEAT", 0.05)
    monkeypatch.setattr(WS, "MAX_AGE", 0.12)
    out = []

    async def go():
        conn, live, poll = hub.open("u1", ["IN:S1"], asyncio.get_running_loop())
        async for chunk in hub.feed(conn, {"live": live, "poll": poll}):
            out.append(chunk)
    run(go())
    assert any(c.startswith(": keep-alive") for c in out) and out[-1].startswith("event: bye")
    assert hub.stats()["streams"] == 0


def test_fifty_viewers_on_twenty_symbols_stay_small_and_one_subscription_each():
    """The memory a crowd costs: 50 streams following 20 of 40 symbols each, ticking. Reported by the test (see the printed line)."""
    ticks, hub = make(timers=[])
    symbols = [f"IN:S{i}" for i in range(40)]

    async def go():
        loop = asyncio.get_running_loop()
        gc.collect()
        tracemalloc.start()
        base = tracemalloc.take_snapshot()
        conns = []
        for v in range(50):
            mine = [symbols[(v + k) % 40] for k in range(20)]
            conn, live, _ = hub.open(f"user{v}", mine, loop)
            conns.append(conn)
            assert len(live) == 20
        for rnd in range(5):
            for tok in range(1000, 1040):
                ticks.tick(tok, 100 + rnd, 10_000 * rnd)
        await asyncio.sleep(0)
        sent = sum(len(hub.take(c)) for c in conns)
        snap = tracemalloc.take_snapshot()
        grown = sum(s.size_diff for s in snap.compare_to(base, "filename"))
        tracemalloc.stop()
        for c in conns:
            hub.close(c)
        return sent, grown
    sent, grown = run(go())
    assert len(ticks.adds) == 40                                                          # 40 subscriptions for 1,000 follows
    assert sent == 50 * 20                                                                # each viewer was given each symbol's newest price once
    print(f"\nmemory for 50 viewers on 20 symbols (40 symbols, 1,000 follows): {grown / 1024:.0f} KiB")
    assert grown < 1_500_000                                                              # well under 1.5 MB for the whole crowd
    assert hub.stats()["streams"] == 0


# ---------- through the API ----------
def test_the_stream_route_follows_the_brokers_feed_and_lets_go_when_the_page_does(monkeypatch):
    from app import watch_routes
    from app.intel import company
    from tests import world
    built = world.build(monkeypatch)
    try:
        import app.main as main
        ticks = FakeTicks()
        monkeypatch.setattr(main, "hub", ticks)
        monkeypatch.setattr(watch_routes, "_hub", None)
        monkeypatch.setattr(company, "market_open", lambda region, now=None: True)
        c = built["client"]
        hdr = world.headers("pro-token")
        seen = []
        with c.stream("GET", "/watch/stream?ids=IN:INFY,US:AAPL", headers=hdr) as r:
            assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
            assert r.headers["cache-control"] == "no-cache, no-transform"
            lines = r.iter_lines()
            hello = next(lines), next(lines)
            seen.append(hello)
            assert hello[0] == "event: hello"
            body = json.loads(hello[1][6:])
            assert body["live"] == ["IN:INFY"] and body["poll"] == ["US:AAPL"] and "reason" not in body
            token = next(iter(ticks.listeners.values()))[0]
            ticks.tick(token, 1500.25, 123456)
            next(lines)                                                                   # the blank line ending hello
            ev = [next(lines) for _ in range(2)]
            assert ev[0] == "event: tick"
            row = json.loads(ev[1][6:])[0]
            assert row["k"] == "IN:INFY" and row["p"] == 1500.25 and row["v"] == 123456
        # the page went: the instrument is let go after its grace (swept at once here)
        hub = watch_routes.stream_hub()
        deadline = time.time() + 3
        while hub.stats()["streams"] and time.time() < deadline:
            time.sleep(0.05)
        assert hub.stats()["streams"] == 0
        assert hub.sweep(time.monotonic() + WS.GRACE + 1) == 1 and ticks.removes
    finally:
        built["close"]()
