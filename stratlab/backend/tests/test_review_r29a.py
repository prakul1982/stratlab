"""Review round 29A: the India company page waited on slow or refused sources in the evening (R29A-001), and smaller
items: the usage count's KeyError (R29A-013)."""
import threading
import time
from datetime import datetime, timedelta, timezone

import httpx
import pytest
import time_machine
from fastapi.testclient import TestClient

from app import db, main, official_close
from app.intel import net, routes
from app.intel.company import Research
from app.intel.news import GoogleNews, Wikipedia
from app.intel.screener import Screener
from app.intel.yahoo import Yahoo
from tests import fake_kite, fake_prices
from tests.fake_intel import fake_news, fake_screener, fake_wiki
from tests.fake_yahoo import fake_yahoo

IST = timezone(timedelta(hours=5, minutes=30))
EVENING = datetime(2026, 10, 15, 18, 30, tzinfo=IST)      # after the close and after the exchange's files are due


def _ist(hm: str) -> datetime:
    h, m = hm.split(":")
    return EVENING.replace(hour=int(h), minute=int(m))


@pytest.fixture
def mem(monkeypatch):
    store: dict = {}
    monkeypatch.setattr(db, "get_setting", lambda k: store.get(k))
    monkeypatch.setattr(db, "set_setting", lambda k, v: store.__setitem__(k, v))
    monkeypatch.setattr(db, "delete_setting", lambda k: store.pop(k, None))
    official_close.forget()
    yield store
    official_close.setup(None, None)
    official_close.forget()


def on_request(fn):
    """fn() as it runs for someone's request (the sources' short wait set, as the RequestWaits middleware does)."""
    return net.with_rate_wait(net.REQUEST_WAIT, fn)()


class Hang:
    """A source that takes `secs` to answer, then fails (a refused or timed-out connection), counting its calls."""

    def __init__(self, secs: float, answer=None):
        self.secs, self.answer, self.calls = secs, answer, 0
        self.gate = threading.Event()

    def __call__(self, *a, **kw):
        self.calls += 1
        self.gate.wait(self.secs)
        if self.answer is not None:
            return self.answer
        raise httpx.ConnectError("refused")


def _quote(price=2156.0, at="2026-10-15T15:31:07+05:30"):
    return {"TCS": {"price": price, "at": at}}


# ---------- R29A-001: the page never waits on the whole-market quotes or an exchange file ----------
def test_a_page_takes_its_own_quote_while_the_whole_market_read_hangs(mem):
    slow = Hang(10, answer=_quote())
    official_close.setup(None, lambda syms, max_wait=None: _quote(), force=True, all_quotes_fn=slow)
    t = time.monotonic()
    got = on_request(lambda: official_close.day_close("TCS", "2026-10-15", "cas", "NSE", now=_ist("16:30")))
    assert got == 2156.0                                   # the same official close, from the stock's own quote
    assert time.monotonic() - t < official_close.PAGE_WAIT + 1
    # a second page while the read is still under way doesn't wait for it again
    official_close._mem.pop(("q1", "NSE", "TCS"))
    t = time.monotonic()
    assert on_request(lambda: official_close.day_close("TCS", "2026-10-15", "cas", "NSE", now=_ist("16:30"))) == 2156.0
    assert time.monotonic() - t < 0.5 and slow.calls == 1
    slow.gate.set()


def test_the_whole_market_quotes_are_read_once_and_a_page_uses_the_last_copy(mem):
    calls = []
    official_close.setup(None, lambda syms, max_wait=None: {}, force=True,
                         all_quotes_fn=lambda: calls.append(1) or _quote())
    assert official_close.day_close("TCS", "2026-10-15", "cas", "NSE", now=_ist("16:30")) == 2156.0     # a job: waits
    # a walk over thousands of BSE-only companies fills the small memory; the quotes are kept outside it (they were
    # dropped there, and the next page read every stock's quote again)
    for i in range(official_close._mem.max + 100):
        official_close._mem.set(("q1", "BSE", f"S{i}"), {}, 60)
    assert on_request(lambda: official_close.day_close("TCS", "2026-10-15", "cas", "NSE", now=_ist("16:30"))) == 2156.0
    assert len(calls) == 1
    # past their time a page gets the last copy at once, and a fresh one is read in the background
    official_close._allq["until"] = 0.0
    assert on_request(lambda: official_close.day_close("TCS", "2026-10-15", "cas", "NSE", now=_ist("16:30"))) == 2156.0
    official_close._allq["flight"].result(timeout=5)
    assert len(calls) == 2


def test_a_page_never_waits_on_a_refused_exchange_file_and_it_is_not_asked_again(mem):
    files = Hang(10)
    official_close.setup(files, None, force=True)
    t = time.monotonic()
    assert on_request(lambda: official_close.closes("2026-10-15", now=_ist("18:30"))) is None
    assert time.monotonic() - t < 0.5
    # many stocks later (the memory full), the refused day is still not asked again for RETRY
    for i in range(official_close._mem.max + 100):
        official_close._mem.set(("q1", "BSE", f"S{i}"), {}, 60)
    files.gate.set()
    official_close._flights[("closes", "2026-10-15")].result(timeout=5)
    official_close._flights[("w52", "2026-10-15")].result(timeout=5)
    n = files.calls
    assert n == 2                                         # the closes and the 52-week report, once each
    assert official_close.closes("2026-10-15", now=_ist("18:31")) is None
    assert files.calls == n


def test_a_job_still_waits_for_the_exchange_file(mem, monkeypatch):
    from app import exchange_days
    monkeypatch.setattr(exchange_days, "cash_closes", lambda f, d: {"TCS": {"close": 2156.0}})
    monkeypatch.setattr(exchange_days, "week52", lambda f, d: {})
    official_close.setup(lambda: object(), None, force=True)
    assert official_close.closes("2026-10-15", now=_ist("18:30")) == {"TCS": 2156.0}


def test_a_refused_batch_of_the_whole_market_read_keeps_the_others():
    k = fake_kite.online()
    fake = k.kite
    for i in range(1200):                   # the exchange lists some 2,600: more than one batch of 500
        fake.rows["NSE"].append({"instrument_token": 900000 + i, "tradingsymbol": f"PAD{i}", "name": f"PAD{i}", "segment": "NSE",
                                 "instrument_type": "EQ", "lot_size": 1, "expiry": None, "strike": 0})
    fake.by_token = {r["instrument_token"]: r for rows in fake.rows.values() for r in rows}
    fake.by_key = {f"{ex}:{r['tradingsymbol']}": r for ex, rows in fake.rows.items() for r in rows}
    real, n = fake.quote, [0]

    def quote(keys):
        n[0] += 1
        if n[0] == 1:
            raise RuntimeError("Too many requests")
        return real(keys)
    k.kite.quote = quote
    got = k.day_quotes()
    rows = [r for r in k.equities() if r["exchange"] == "NSE"]
    assert len(rows) > 500 and len(got) == len(rows) - 500 and rows[-1]["symbol"] in got
    k.kite.quote = lambda keys: (_ for _ in ()).throw(RuntimeError("down"))
    with pytest.raises(RuntimeError):
        k.day_quotes()


def test_the_consolidated_and_standalone_pages_are_read_at_once():
    inner = fake_screener()

    class Slow(httpx.BaseTransport):
        def handle_request(self, req):
            time.sleep(0.6)
            return inner.handle_request(req)
    s = Screener(transport=Slow())
    t = time.monotonic()
    got = s.company("RELIANCE")
    assert got["name"] and time.monotonic() - t < 1.1          # two reads of 0.6 s each, side by side


# ---------- the lean India page in the evening, with every slow source hanging ----------
@pytest.fixture
def evening_page(monkeypatch, mem):
    day = EVENING.astimezone(timezone.utc)
    monkeypatch.setattr(fake_prices, "FROZEN", day)
    clock = time_machine.travel(day, tick=True)
    clock.start()
    kite = fake_kite.online()
    hang = {"files": Hang(20), "all": Hang(20, answer={}), "bse": Hang(20)}
    official_close.setup(lambda: hang["files"](), lambda syms, max_wait=None: kite.quote(syms, max_wait=max_wait),
                         force=True, all_quotes_fn=hang["all"])
    monkeypatch.setattr(kite, "day_close", official_close.history_close, raising=False)
    # BSE refuses the server (R29A-004): every call to it hangs, then fails
    for name in ("announcements", "corporate_actions", "actions_of", "filings", "company"):
        monkeypatch.setattr(main.filings_feed.bse, name, hang["bse"], raising=False)
    hub = Research(kite, yahoo=Yahoo(transport=fake_yahoo()), screener=Screener(transport=fake_screener()),
                   news=GoogleNews(transport=fake_news()), wiki=Wikipedia(transport=fake_wiki()))
    old = routes.hub
    routes.setup(hub, None, None)
    main.app.dependency_overrides[main.current_profile] = lambda: {"id": "u1", "_plan": "pro", "plan": "pro"}
    yield TestClient(main.app), hang
    for h in hang.values():
        h.gate.set()
    main.app.dependency_overrides.clear()
    routes.hub = old
    clock.stop()


def test_the_lean_india_page_is_quick_while_the_exchange_files_quotes_and_bse_hang(evening_page):
    c, hang = evening_page
    for sym in ("RELIANCE", "RELIANCE", "TCS"):
        t = time.monotonic()
        r = c.get(f"/research/company/IN/{sym}?lean=1")
        took = time.monotonic() - t
        assert r.status_code == 200 and r.json()["quote"]["price"] > 0
        assert took < official_close.PAGE_WAIT + 2, f"{sym} took {took:.1f} s"
    assert hang["bse"].calls == 0                       # nothing of BSE's is on the page's way
    assert hang["all"].calls == 1                       # one whole-market read, in the background


# ---------- R29A-013: the 4 Oct "KeyError: 819" in count_usage ----------
def test_usage_counts_go_over_http_1_1_where_a_shared_http2_stream_table_raised_keyerror(monkeypatch):
    """The 4 Oct error was the database client's one HTTP/2 connection shared by every thread: two threads at once in its
    stream table fail with a bare KeyError (the stream number, 819). Since 8 Oct every lane is HTTP/1.1, one request per
    connection; and a reply without a count is 0, never an error."""
    client = db._http()
    try:
        for transport, _ in (client._transport.request, client._transport.signin, client._transport.job):
            assert transport.inner._pool._http2 is False
    finally:
        client.close()

    class Q:
        count = None
        def __getattr__(self, name):
            return lambda *a, **k: self
        def execute(self):
            return self
    monkeypatch.setattr(db, "sb", lambda: type("C", (), {"table": lambda self, n: Q()})())
    assert db.count_usage("u1", "ai", "2026-10-01T00:00:00+00:00") == 0
