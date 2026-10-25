"""R11E: the waits on first loads and heavy routes. Concurrent callers of one source share one upstream call, a request
doesn't sleep on the rate limit, the US company page reads its profile alongside the rest and its corporate actions
from storage, and the parsed calendar is kept a minute."""
import json
import threading
import time
from datetime import date, datetime, timedelta, timezone

from types import SimpleNamespace

import httpx
import pytest

from app.intel import net
from app.intel.net import Source, SourceError


def _source(handler, **kw) -> Source:
    s = Source("https://example.test", transport=httpx.MockTransport(handler), **kw)
    s.name = "Example"
    return s


class Upstream:
    """A fake upstream that counts calls and can hold them until released."""
    def __init__(self, status=200, body=None):
        self.calls, self.status, self.body = 0, status, body if body is not None else {"v": 1}
        self.gate = threading.Event()
        self.gate.set()
        self.lock = threading.Lock()

    def __call__(self, request):
        with self.lock:
            self.calls += 1
        self.gate.wait(2)
        return httpx.Response(self.status, json=self.body)


def _together(n, fn):
    out, errs = [], []

    def go():
        try:
            out.append(fn())
        except Exception as e:
            errs.append(e)
    ts = [threading.Thread(target=go) for _ in range(n)]
    for t in ts:
        t.start()
    return ts, out, errs


# ---------- one upstream call per key ----------
def test_concurrent_callers_share_one_upstream_call():
    up = Upstream()
    s = _source(up)
    up.gate.clear()
    ts, out, errs = _together(8, lambda: s.fetch("/q", {"symbol": "NVDA"}, ttl=60))
    time.sleep(0.05)                                   # all eight are in fetch, one of them upstream
    up.gate.set()
    for t in ts:
        t.join(2)
    assert errs == [] and out == [{"v": 1}] * 8
    assert up.calls == 1


def test_different_keys_are_not_shared():
    up = Upstream()
    s = _source(up)
    s.fetch("/q", {"symbol": "A"})
    s.fetch("/q", {"symbol": "B"})
    assert up.calls == 2


def test_a_failure_is_shared_by_the_callers_waiting_on_it():
    up = Upstream(status=500)
    s = _source(up)
    up.gate.clear()
    ts, out, errs = _together(5, lambda: s.fetch("/q"))
    time.sleep(0.05)
    up.gate.set()
    for t in ts:
        t.join(2)
    assert out == [] and len(errs) == 5 and all(isinstance(e, SourceError) for e in errs)
    assert up.calls == 1


# ---------- the last good answer, when the source can't be asked ----------
def test_a_stale_copy_answers_when_the_source_is_busy(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(net.time, "time", lambda: clock[0])
    up = Upstream(body={"price": 10})
    s = _source(up)
    assert s.fetch("/q", ttl=60, with_time=True) == ({"price": 10}, 1000.0)
    clock[0] += 61                                     # past its ttl
    up.status = 503
    assert s.fetch("/q", ttl=60, with_time=True) == ({"price": 10}, 1000.0)    # the old copy, with the time it was sent
    up.status, up.body = 200, {"price": 11}
    assert s.fetch("/q", ttl=60) == {"price": 11}      # a normal answer again: fresh as before


def test_a_fresh_answer_is_never_replaced_by_the_stale_copy(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(net.time, "time", lambda: clock[0])
    up = Upstream(body={"price": 10})
    s = _source(up)
    s.fetch("/q", ttl=60)
    clock[0] += 61
    up.body = {"price": 12}
    assert s.fetch("/q", ttl=60) == {"price": 12}      # the source answered: its answer, not the copy
    assert up.calls == 2


def test_no_such_thing_is_not_answered_from_the_copy(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(net.time, "time", lambda: clock[0])
    up = Upstream()
    s = _source(up)
    s.fetch("/q", ttl=60)
    clock[0] += 61
    up.status = 404
    with pytest.raises(SourceError):
        s.fetch("/q", ttl=60)


def test_the_copy_is_kept_only_a_while(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(net.time, "time", lambda: clock[0])
    up = Upstream()
    s = _source(up)
    s.fetch("/q", ttl=60)
    clock[0] += 60 * Source.STALE_FOR + 1
    up.status = 503
    with pytest.raises(SourceError):
        s.fetch("/q", ttl=60)


def test_a_source_without_a_fallback_copy_says_busy(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(net.time, "time", lambda: clock[0])
    up = Upstream()
    s = _source(up)
    s.STALE_FOR = 0
    s.fetch("/q", ttl=60)
    clock[0] += 61
    up.status = 503
    with pytest.raises(SourceError):
        s.fetch("/q", ttl=60)


# ---------- the rate limit's wait ----------
def test_a_request_waits_briefly_on_the_rate_limit_and_a_job_its_turn(monkeypatch):
    up = Upstream()
    s = _source(up)
    waits = []
    monkeypatch.setattr(s.limit, "take", lambda max_wait=8.0: waits.append(max_wait) or False)
    with pytest.raises(SourceError):
        s.fetch("/a")
    net.with_rate_wait(net.REQUEST_WAIT, lambda: pytest.raises(SourceError, s.fetch, "/b"))()
    assert waits == [net.JOB_WAIT, net.REQUEST_WAIT]
    assert up.calls == 0


def test_an_empty_bucket_answers_a_request_from_the_copy_at_once(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(net.time, "time", lambda: clock[0])
    up = Upstream(body={"v": "old"})
    s = _source(up, per_minute=60, burst=1)
    s.fetch("/q", ttl=60)
    clock[0] += 61
    slept = []
    monkeypatch.setattr(net.time, "sleep", lambda x: slept.append(x))
    s.limit.tokens, s.limit.at = 0.0, clock[0]
    got = net.with_rate_wait(0.0, lambda: s.fetch("/q", ttl=60))()
    assert got == {"v": "old"} and slept == [] and up.calls == 1


def test_the_request_middleware_sets_the_short_wait():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    app = FastAPI()
    app.add_middleware(net.RequestWaits)
    app.get("/w")(lambda: {"wait": net.rate_wait()})
    assert TestClient(app).get("/w").json() == {"wait": net.REQUEST_WAIT}
    assert net.rate_wait() == net.JOB_WAIT


def test_a_pages_tasks_take_the_requests_wait_onto_the_pool():
    from app.intel.company import Research
    r, _ = net.with_rate_wait(net.REQUEST_WAIT, lambda: Research._run({"a": ("X", net.rate_wait)}))()
    assert r == {"a": net.REQUEST_WAIT}
    r, _ = Research._run({"a": ("X", net.rate_wait)})
    assert r == {"a": net.JOB_WAIT}


# ---------- the US company page ----------
def test_the_us_profile_is_read_alongside_the_other_calls(monkeypatch):
    """The profile no longer goes first and alone: the other calls are under way while it is read."""
    from app import main
    hub = main.research_hub
    fh = hub.finnhub
    started = threading.Event()
    seen = {}

    def profile(sym):
        seen["others_running"] = started.wait(1)
        return {"name": "Example Corp", "currency": "USD", "finnhubIndustry": "Tech"}
    monkeypatch.setattr(fh, "profile", profile)
    monkeypatch.setattr(fh, "quote", lambda s: started.set() or {"c": 10.0, "t": 1760000000})
    for name in ("metrics", "peers", "recommendation", "earnings", "financials", "insider", "earnings_calendar", "news"):
        monkeypatch.setattr(fh, name, lambda s, _n=name: {} if _n in ("metrics", "insider") else [])
    monkeypatch.setattr(hub.yahoo, "meta", lambda s: {})
    monkeypatch.setattr(hub, "_quiet_candles", lambda s: [])
    wiki = []
    monkeypatch.setattr(hub.wiki, "company", lambda name: wiki.append(name) or None)
    out = hub._company_us("EXM", lean=True)
    assert seen["others_running"] and out["name"] == "Example Corp" and wiki == []
    out = hub._company_us("EXM")
    assert wiki == ["Example Corp"]
    assert [x["source"] for x in out["sources"]] == ["Yahoo Finance", "Finnhub", "Wikipedia"]


def test_an_unknown_us_symbol_is_still_not_found(monkeypatch):
    from app import main
    from app.intel.net import NotFound
    hub = main.research_hub
    monkeypatch.setattr(hub.finnhub, "profile", lambda s: {})
    with pytest.raises(NotFound):
        hub._company_us("NOPE", lean=True)


class EventsFeed:
    def __init__(self, events):
        self.events_of, self.calls = events, 0
        self.gate = threading.Event()
        self.gate.set()

    def events(self, symbol):
        self.calls += 1
        self.gate.wait(2)
        return self.events_of


def _us_events(*divs):
    return {"dividends": [{"date": d, "amount": a} for d, a in divs]}


def _wait_for(cond, timeout=2.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return
        time.sleep(0.002)
    raise AssertionError("never happened")


@pytest.fixture
def fake_db(monkeypatch):
    from app import db
    from tests.fake_db import FakeSupabase
    f = FakeSupabase()
    monkeypatch.setattr(db, "_client", f)
    return f


def test_us_dividends_on_the_page_come_from_storage_and_refresh_in_the_background(fake_db, monkeypatch):
    from app import corp_actions
    from app.intel import routes
    today = date.today()
    d1 = (today - timedelta(days=100)).isoformat()
    d2 = (today - timedelta(days=10)).isoformat()
    feed = EventsFeed(_us_events((d1, 0.25)))
    corp_actions.hist_save("US", "ABC", corp_actions.us_rows("ABC", _us_events((d1, 0.25))))
    monkeypatch.setattr(routes, "corp_sources", lambda: {"us": feed})
    # a fresh stored history: no read at all
    assert [r["amount"] for r in routes.stored_dividends("US", "ABC")] == [0.25]
    assert feed.calls == 0
    # a day old: the page gets the stored rows at once, and one background read follows
    old = corp_actions.hist_load("US", "ABC")
    corp_actions.db.set_setting(corp_actions.HIST + "US:ABC", corp_actions.json.dumps(
        {"at": (datetime.now(timezone.utc) - timedelta(hours=21)).isoformat(timespec="minutes"), "rows": old["rows"]}))
    feed.events_of = _us_events((d1, 0.25), (d2, 0.26))
    feed.gate.clear()
    for _ in range(3):
        assert [r["amount"] for r in routes.stored_dividends("US", "ABC")] == [0.25]
    feed.gate.set()
    _wait_for(lambda: not routes._hist_reading and feed.calls >= 1)
    assert feed.calls == 1
    assert sorted(r["amount"] for r in routes.stored_dividends("US", "ABC")) == [0.25, 0.26]


def test_a_us_history_never_stored_is_still_read_on_the_page(fake_db, monkeypatch):
    from app.intel import routes
    d1 = (date.today() - timedelta(days=100)).isoformat()
    feed = EventsFeed(_us_events((d1, 0.4)))
    monkeypatch.setattr(routes, "corp_sources", lambda: {"us": feed})
    assert [r["amount"] for r in routes.stored_dividends("US", "NEW")] == [0.4]
    assert feed.calls == 1


def test_the_parsed_calendar_is_kept_a_minute_and_dropped_on_save(fake_db, monkeypatch):
    from app import corp_actions, db
    ex = date.today().isoformat()
    corp_actions.save("US", [corp_actions.row("US", "AAA", {"kind": "dividend", "label": "Dividend", "text": "Dividend $1 a share", "amount": 1.0}, date.today())])
    reads = []
    real = db.get_setting
    monkeypatch.setattr(db, "get_setting", lambda k: reads.append(k) or real(k))
    clock = [time.monotonic()]
    monkeypatch.setattr(corp_actions.time, "monotonic", lambda: clock[0])
    for _ in range(3):
        assert [r["ex_date"] for r in corp_actions.load_cached("US")["rows"]] == [ex]
    assert reads == [corp_actions.KEY + "US"]
    corp_actions.load_cached("US")["rows"].clear()                         # a caller's copy, not the kept one
    assert len(corp_actions.load_cached("US")["rows"]) == 1
    corp_actions.save("US", [])
    assert corp_actions.load_cached("US")["rows"] == []                     # a save is seen at once
    n = len(reads)
    clock[0] += corp_actions.CAL_MEMO_FOR + 1
    corp_actions.load_cached("US")
    assert len(reads) == n + 1                                              # read again after a minute


# ---------- Admin's Overview ----------
class CountingDB:
    """Wraps the fake database, counting the queries per table."""
    def __init__(self, inner):
        self.inner, self.calls = inner, {}

    def table(self, name):
        q = self.inner.table(name)
        real = q.execute

        def execute():
            self.calls[name] = self.calls.get(name, 0) + 1
            return real()
        q.execute = execute
        return q

    def __getattr__(self, k):
        return getattr(self.inner, k)


def _legacy_stats(month_start):
    """Overview's counts as they were worked out before R11E (every profile read), to hold the new counts to."""
    from collections import Counter
    from app import admin
    from app.plans import PLANS, effective_plan
    rows = admin._profiles(admin._COUNT_COLS)
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)
    today = now.astimezone(admin.IST).replace(hour=0, minute=0, second=0, microsecond=0)
    plans = Counter(effective_plan(r) for r in rows)
    given = admin.granted()
    paying = Counter(effective_plan(r) for r in rows if admin._paying(r, given))
    made = [t for t in (admin._at(r.get("created_at")) for r in rows) if t]
    return {"users": len(rows), "plans": {p: plans.get(p, 0) for p in PLANS}, "new_7d": sum(1 for t in made if t >= week_ago),
            "signups_today": sum(1 for t in made if t >= today),
            "paying": {p: paying.get(p, 0) for p in ("basic", "pro")},
            "given": {p: plans.get(p, 0) - paying.get(p, 0) for p in ("basic", "pro")},
            "experiments_month": admin._count_since("backtest", month_start), "ai_month": admin._count_since("ai", month_start),
            "ai_reads_month": admin._count_since("research_ai", month_start)}


def test_overview_counts_match_reading_every_profile(fake_db):
    from app import admin, db
    now = datetime.now(timezone.utc)
    later, earlier = (now + timedelta(days=20)).isoformat(), (now - timedelta(days=20)).isoformat()
    rows = [
        {"id": "a", "plan": "free", "created_at": (now - timedelta(days=40)).isoformat()},
        {"id": "b", "plan": None, "created_at": (now - timedelta(hours=1)).isoformat()},
        {"id": "c", "plan": "pro", "plan_status": "active", "current_period_end": later, "razorpay_subscription_id": "s1",
         "created_at": (now - timedelta(days=3)).isoformat()},
        {"id": "d", "plan": "pro", "plan_status": "active", "current_period_end": later, "created_at": (now - timedelta(days=9)).isoformat()},
        {"id": "e", "plan": "basic", "plan_status": "cancelled", "current_period_end": later, "created_at": earlier},
        {"id": "f", "plan": "basic", "plan_status": "active", "current_period_end": earlier, "created_at": earlier},
        {"id": "g", "plan": "basic", "plan_status": "active", "current_period_end": later, "razorpay_subscription_id": "s2",
         "created_at": (now - timedelta(days=6)).isoformat()},
        {"id": "h", "plan": "weird", "plan_status": "active", "created_at": None},
        {"id": "i", "plan": "pro", "plan_status": "active", "current_period_end": later, "razorpay_subscription_id": "s3",
         "created_at": (now - timedelta(minutes=5)).isoformat()},
    ]
    fake_db.tables["profiles"] = rows
    fake_db.tables["usage_events"] = [{"id": n, "user_id": "c", "kind": k, "created_at": now.isoformat()}
                                      for n, k in enumerate(["backtest", "backtest", "ai", "research_ai"])]
    admin.mark_granted("i", True)                       # a subscription id, and a plan given by hand after it
    month = (now - timedelta(days=1)).isoformat()
    got = admin.stats(month)
    assert got.pop("test_accounts") == 0 and got == _legacy_stats(month)     # DJ-001 added only the test-account count
    assert got["users"] == 9 and got["plans"] == {"free": 5, "basic": 1, "pro": 3}
    assert got["paying"] == {"basic": 1, "pro": 1} and got["experiments_month"] == 2


def test_overview_reads_only_the_paid_profiles(fake_db, monkeypatch):
    from app import admin, db
    fake_db.tables["profiles"] = [{"id": f"u{i}", "plan": "free", "created_at": "2026-01-01T00:00:00+00:00"} for i in range(50)] + \
        [{"id": "p", "plan": "pro", "plan_status": "active", "created_at": "2026-01-01T00:00:00+00:00"}]
    seen = []
    real = admin._paged
    monkeypatch.setattr(admin, "_paged", lambda q, page=1000: (lambda r: seen.append(len(r)) or r)(real(q, page)))
    st = admin.stats("2026-10-01T00:00:00+05:30")
    assert st["users"] == 51 and st["plans"]["free"] == 50 and st["plans"]["pro"] == 1
    assert seen == [1]                                   # one profile read, not 51


@pytest.fixture
def w(monkeypatch):
    from tests import world as W
    world = W.build(monkeypatch)
    yield world
    world["close"]()


def test_overview_counts_are_kept_and_refresh_reads_them_again(w, monkeypatch):
    from app import db, main
    from tests.fake_db import headers
    A = headers("admin-token")
    c = w["client"]
    counting = CountingDB(db.sb())
    monkeypatch.setattr(db, "_client", counting)
    clock = [time.monotonic()]
    monkeypatch.setattr(main.time, "monotonic", lambda: clock[0])
    first = c.get("/admin/overview", headers=A).json()
    reads = counting.calls.get("usage_events", 0)
    assert reads == 4                          # the month's three counts, and who was active this week (DJ-004)
    db.update_profile("u-basic", razorpay_subscription_id="sub_1")
    again = c.get("/admin/overview", headers=A).json()
    assert counting.calls["usage_events"] == reads and again["stats"] == first["stats"]       # kept: no count read again
    assert "server" in again and again["server"]["kite_ready"] == first["server"]["kite_ready"]   # the status: read each time
    fresh = c.get("/admin/overview?fresh=1", headers=A).json()                               # Refresh
    assert counting.calls["usage_events"] == reads + 4
    assert fresh["stats"]["paying"]["basic"] == first["stats"]["paying"]["basic"] + 1
    clock[0] += main.OVERVIEW_FOR + 1
    c.get("/admin/overview", headers=A)
    assert counting.calls["usage_events"] == reads + 8                                         # read again once old


def test_overview_reads_go_at_once(fake_db, monkeypatch):
    """The counts' reads overlap: each one held until all eight have started."""
    from app import admin
    n = 8
    barrier = threading.Barrier(n, timeout=2)

    def held(v):
        def f(*a):
            barrier.wait()
            return v
        return f
    monkeypatch.setattr(admin, "_count_profiles", held(1))
    monkeypatch.setattr(admin, "_paid_profiles", held([]))
    monkeypatch.setattr(admin, "granted", held(set()))
    monkeypatch.setattr(admin, "_count_since", held(0))
    st = admin.stats("2026-10-01T00:00:00+05:30")             # one after another, the barrier would break
    assert st["users"] == 1


# ---------- the pulse ----------
class Levels:
    """Index levels to hand out, with some names missing on a read."""
    def __init__(self):
        self.missing, self.price = set(), 100.0

    def meta(self, sym):
        from app.intel.company import INDICES
        name = next(n for n, s in INDICES["US"] if s == sym)
        if name in self.missing:
            return {}
        return {"price": self.price, "prev_close": 99.0, "at": "2026-10-14T20:00:00+00:00"}


def _pulse_hub():
    from types import SimpleNamespace
    from app.intel.company import Research
    y = Levels()
    return Research(None, finnhub=SimpleNamespace(ready=lambda: False), yahoo=y, screener=object(), news=object(), wiki=object()), y


def test_a_refresh_with_an_index_missing_keeps_its_last_row():
    hub, y = _pulse_hub()
    got, _ = hub.indices_now("US", wait=2)
    assert [i["name"] for i in got] == ["S&P 500", "NASDAQ", "DOW JONES"]
    y.missing, y.price = {"NASDAQ"}, 101.0
    levels, _ = hub._snaps()
    levels.fresh_for = 0
    hub.indices_now("US", wait=2)
    _wait_for(lambda: levels.kept("US")[1][0]["price"] == 101.0)
    got, _ = hub.indices_now("US", wait=2)
    assert [(i["name"], i["price"]) for i in got] == [("S&P 500", 101.0), ("NASDAQ", 100.0), ("DOW JONES", 101.0)]


def test_the_first_read_of_the_pulse_still_leaves_out_what_it_lacks():
    hub, y = _pulse_hub()
    y.missing = {"NASDAQ"}
    got, _ = hub.indices_now("US", wait=2)
    assert [i["name"] for i in got] == ["S&P 500", "DOW JONES"]


def test_a_pulse_refresh_waits_briefly_for_the_broker_and_keeps_the_levels_when_busy():
    from types import SimpleNamespace
    from app.intel.company import Research
    from app.kite_service import KiteBusy

    class Kite:
        def __init__(self):
            self.waits, self.busy = [], False

        def ready(self):
            return True

        def index_quotes(self, keys, max_wait=None):
            self.waits.append(max_wait)
            if self.busy:
                raise KiteBusy("busy")
            return {k: {"price": 22774.65, "prev_close": 22666.8, "change_pct": 0.48, "at": "2026-10-15T09:46:00+05:30"} for k in keys}

    k = Kite()
    hub = Research(k, finnhub=SimpleNamespace(ready=lambda: False), yahoo=SimpleNamespace(meta=lambda s: {}), screener=object(),
                   news=object(), wiki=object())
    got, _ = hub.indices_now("IN", wait=2)
    assert len(got) == 3 and k.waits == [None]                 # the first read waits its turn
    levels, _ = hub._snaps()
    levels.fresh_for = 0
    k.busy = True
    got, _ = hub.indices_now("IN", wait=2)
    _wait_for(lambda: len(k.waits) == 2 and "KiteBusy" in levels.errors.get("IN", ""))
    assert k.waits[1] == hub.PULSE_KITE_WAIT
    assert [i["price"] for i in levels.kept("IN")[1]] == [22774.65] * 3      # kept, not replaced by a partial read


def test_index_quotes_honours_max_wait():
    from tests import fake_kite
    from app.kite_service import KiteBusy
    k = fake_kite.online()
    k._last_call = time.time() + 30
    with pytest.raises(KiteBusy):
        k.index_quotes(["NSE:NIFTY 50"], max_wait=2)


def test_the_index_reads_use_their_own_pool(monkeypatch):
    from app.intel import company
    names = []
    hub, y = _pulse_hub()
    real = y.meta
    y.meta = lambda s: names.append(threading.current_thread().name) or real(s)
    hub.indices("US")
    assert names and all(n.startswith("indices") for n in names)


def test_warm_caches_starts_the_pulse_and_reads_the_mirror(monkeypatch):
    from app import db, main
    calls = []
    monkeypatch.setattr(main.research_hub, "indices_now", lambda r, wait=6.0: calls.append(("levels", r, wait)) or (None, None))
    monkeypatch.setattr(main.research_hub, "headlines_now", lambda r, wait=3.0: calls.append(("news", r, wait)) or [])
    monkeypatch.setattr(db, "warm_mirror", lambda: calls.append(("mirror",)))
    monkeypatch.setattr(main, "isin_list", lambda: calls.append(("stop",)) or (_ for _ in ()).throw(RuntimeError("enough")))
    monkeypatch.setattr(main.kite, "ready", lambda: False)
    monkeypatch.setattr(main.options_data, "ready", lambda: False)
    monkeypatch.setattr(main.markets, "markets", lambda: None)
    monkeypatch.setattr(main.markets, "provider", lambda r: SimpleNamespace(ready=lambda: False))
    monkeypatch.setattr(main.scan, "run", lambda *a, **k: None)
    monkeypatch.setattr(main.rotation, "run", lambda *a, **k: None)
    main.warm_caches()
    assert calls[:5] == [("levels", "IN", 0), ("news", "IN", 0), ("levels", "US", 0), ("news", "US", 0), ("mirror",)]


# ---------- smaller ones ----------
def test_peek_keeps_a_fresh_stored_page_in_memory(fake_db, monkeypatch):
    from app import stock_pages
    p = stock_pages.Pages(gather=lambda r, co: None)
    facts = {"symbol": "ZZZ", "pe": 12, "v": stock_pages.FACTS_VERSION}
    stock_pages._put("stocks:page:US:ZZZ", {"ts": time.time(), "facts": facts})
    assert stock_pages.fresh(stock_pages._setting("stocks:page:US:ZZZ"), "US")
    reads = []
    real = stock_pages._setting
    monkeypatch.setattr(stock_pages, "_setting", lambda k: reads.append(k) or real(k))
    assert p.peek("US", "ZZZ") == facts
    assert p.peek("US", "ZZZ") == facts
    assert reads == ["stocks:page:US:ZZZ"]                     # parsed once
    assert p.get("US", "ZZZ", {}) == facts                     # and what the page itself serves is the same


def test_peek_leaves_an_old_stored_page_out_of_memory(fake_db):
    from app import stock_pages
    p = stock_pages.Pages(gather=lambda r, co: {"symbol": "OLD", "pe": 99})
    stock_pages._put("stocks:page:US:OLD", {"ts": time.time() - stock_pages.FRESH - 10, "facts": {"symbol": "OLD", "pe": 12, "v": stock_pages.FACTS_VERSION}})
    assert p.peek("US", "OLD")["pe"] == 12
    assert p.mem.get("stocks:page:US:OLD") is None             # an old page is still rebuilt when it's served


def test_a_burst_of_errors_is_saved_in_one_write(monkeypatch):
    from app import db, main
    writes, timers = [], []

    class Timer:
        def __init__(self, after, fn):
            self.after, self.fn, self.daemon = after, fn, False
            timers.append(self)

        def start(self):
            pass
    monkeypatch.setattr(main.threading, "Timer", Timer)
    monkeypatch.setattr(db, "set_setting", lambda k, v: writes.append((k, v)))
    monkeypatch.setattr(main, "RECENT_ERRORS", [])
    monkeypatch.setattr(main, "_errors_due", [False])                 # (other tests' crashes leave their own state)
    monkeypatch.setattr(main, "_errors_saved_at", [float("-inf")])
    main.RECENT_ERRORS.append({"ref": "first"})
    main._save_errors()
    assert len(timers) == 1 and timers[0].after == 0                 # a lone error: written at once
    timers[0].fn()
    for i in range(20):                                               # then a burst
        main.RECENT_ERRORS.append({"ref": str(i)})
        main._save_errors()
    assert len(timers) == 2 and 0 < timers[1].after <= main.ERRORS_SAVE_AFTER
    timers[1].fn()
    assert len(writes) == 2 and len(json.loads(writes[1][1])) == 21  # the burst in one write, the list as it was then


def test_me_reads_its_settings_in_one_call(w, monkeypatch):
    from app import db
    from tests.fake_db import headers
    c = w["client"]
    U = headers("pro-token")
    c.get("/me", headers=U)
    one = []
    real = db._read_setting
    monkeypatch.setattr(db, "_read_setting", lambda k: one.append(k) or real(k))
    before = c.get("/me", headers=U).json()
    assert one == []                                           # every setting /me reads came in the prefetch
    monkeypatch.setattr(db, "prefetch_settings", lambda keys: None)
    assert c.get("/me", headers=U).json() == before            # and the answer is the same without it
    assert len(one) >= 4


def test_a_caller_arriving_after_a_failure_asks_again():
    up = Upstream(status=500)
    s = _source(up)
    with pytest.raises(SourceError):
        s.fetch("/q")
    up.status = 200
    assert s.fetch("/q") == {"v": 1}                   # not handed the earlier failure
    assert up.calls == 2


def test_a_busy_profile_source_leaves_the_us_page_standing_on_its_listing(monkeypatch):
    """R88-001: the profile source down for a minute failed the whole AAPL page ("Couldn't open AAPL")."""
    from app import main
    from app.intel.net import SourceError
    hub = main.research_hub
    fh = hub.finnhub

    def busy(*a, **k):
        raise SourceError("Finnhub", "Finnhub isn't answering right now. Try again in a minute.", busy=True)
    for name in ("profile", "quote", "metrics", "peers", "recommendation", "earnings", "financials", "insider", "earnings_calendar", "news"):
        monkeypatch.setattr(fh, name, busy)
    monkeypatch.setattr(hub.yahoo, "meta", lambda s: {"name": "Apple Inc.", "currency": "USD", "exchange": "NasdaqGS", "price": 348.2})
    monkeypatch.setattr(hub, "_quiet_candles", lambda s: [])
    out = hub._company_us("AAPL", lean=True)
    assert out["name"] == "Apple Inc." and out["currency"] == "USD"
    # with the listing gone too, the page still says it can't be opened
    monkeypatch.setattr(hub.yahoo, "meta", lambda s: (_ for _ in ()).throw(SourceError("Yahoo", "down", busy=True)))
    with pytest.raises(SourceError):
        hub._company_us("AAPL", lean=True)
