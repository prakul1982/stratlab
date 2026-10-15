"""R11E: the waits on first loads and heavy routes. Concurrent callers of one source share one upstream call, a request
doesn't sleep on the rate limit, the US company page reads its profile alongside the rest and its corporate actions
from storage, and the parsed calendar is kept a minute."""
import threading
import time
from datetime import date, datetime, timedelta, timezone

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
