"""rel1 item 1 (CX1 problem 3): a paying user's deep dive never ends on "the fundamentals source is busy (our rate limit)".
Production logs (16 Nov, 18:09-19:43 UTC) show the theme check reading hundreds of small companies' descriptions in a row, each
"Screener.in is busy (our rate limit)", and pages failing between them (RELIANCE, 19:19). The jobs spent every turn of the shared
allowance, so a person's request, which waits one second at most, found none. Now: turns are kept for requests, a deep dive waits a
little longer, the company's last whole read stands in when it still can't be read, and with none the page asks again on its own."""
import time

import httpx
import pytest

from app.intel import net
from app.intel.net import JOB_WAIT, REQUEST_WAIT, RateLimit, SourceError, with_rate_wait
from app.intel.screener import Screener


def test_a_request_finds_a_turn_after_the_jobs_spent_the_bucket():
    lim = RateLimit(per_minute=0.0001, burst=6)          # no refill within the test
    assert lim.reserve == 3
    assert [lim.take(max_wait=0, job=True) for _ in range(7)] == [True] * 6 + [False]    # the jobs spent every turn
    assert [lim.take(max_wait=0, job=False) for _ in range(4)] == [True, True, True, False]   # a person's request still gets one
    assert lim.take(max_wait=0, job=True) is False                                        # the jobs wait out the turns taken ahead
    assert with_rate_wait(REQUEST_WAIT, lambda: lim.take(max_wait=0))() is False and lim.take(max_wait=0) is False


def test_with_no_requests_about_jobs_run_as_before():
    lim = RateLimit(per_minute=60, burst=2)
    assert lim.take(max_wait=0) and lim.take(max_wait=0) and not lim.take(max_wait=0)


def test_requests_and_jobs_are_told_apart_by_their_wait():
    assert net.in_job()                                  # outside a request: a job's wait
    assert not with_rate_wait(REQUEST_WAIT, net.in_job)()
    assert not with_rate_wait(6.0, net.in_job)()         # a page that asked for a longer wait on purpose is still a request
    assert with_rate_wait(JOB_WAIT, net.in_job)()


def test_a_busy_source_gives_a_request_the_last_whole_read_and_a_job_the_busy_answer():
    state = {"up": True}

    from tests.fake_intel import SCREENER_HTML

    def handler(req):
        return httpx.Response(200, text=SCREENER_HTML) if state["up"] else httpx.Response(429, text="slow down")
    s = Screener(transport=httpx.MockTransport(handler))
    first = with_rate_wait(REQUEST_WAIT, lambda: s.company("RELIANCE"))()
    assert first["name"] and (first.get("pl") or {}).get("cols") and "kept_busy" not in first
    state["up"] = False
    s.cache.clear()                                       # the 6-hour copy gone: the source must be asked again
    s._down_until = 0
    again = with_rate_wait(REQUEST_WAIT, lambda: s.company("RELIANCE"))()
    assert again["kept_busy"] is True and again["fetched_at"] == first["fetched_at"] and again["pl"] == first["pl"]
    s._down_until = 0
    with pytest.raises(SourceError) as e:                 # a background job asks again later instead
        s.company("RELIANCE")
    assert e.value.busy


from tests.test_deepdive import api  # noqa: E402,F401  (the deep dive's own test setup)


@pytest.fixture
def deep(api, monkeypatch):
    from app import main
    from tests.test_deepdive import company
    c, who, calls, used = api
    who["p"] = {"id": "u1", "plan": "pro", "_plan": "pro"}
    mode = {"m": "busy"}

    class Scr:
        def company(self, sym):
            if mode["m"] == "kept":
                return {**company(), "kept_busy": True, "fetched_at": "2026-11-12T10:00+00:00"}
            raise SourceError("Screener.in", "Screener.in is busy (our rate limit). Try again in a minute.", busy=True)
    monkeypatch.setattr(main.research_hub, "screener", Scr())
    return c, mode, used


def test_a_busy_deep_dive_says_it_asks_again_and_is_not_counted(deep):
    c, mode, used = deep
    r = c.get("/research/deep/ACME")
    assert r.status_code == 503, r.text
    d = r.json()["detail"]
    assert d["code"] == "source_busy" and "asks again on its own" in d["message"] and "rate limit" not in d["message"]
    assert "Screener" not in d["message"] and used == []


def test_a_deep_dive_on_the_last_whole_read_says_so(deep):
    c, mode, used = deep
    mode["m"] = "kept"
    v = c.get("/research/deep/ACME").json()
    assert v["figures_kept"] is True and v["numbers_at"] == "2026-11-12T10:00+00:00" and v["numbers"]["years"]


# ---------- item 3 (CX1 problem 9): a live price is labelled live with its time; "last close" names the close's own day ----------
def test_a_session_still_trading_is_live_and_the_close_is_the_session_before(monkeypatch):
    from app import last_session, main
    monkeypatch.setattr(last_session, "latest_day", lambda region, now=None: "2026-11-13")
    bars = [{"t": "2026-11-12T00:00:00-05:00", "c": 350.0}, {"t": "2026-11-13T00:00:00-05:00", "c": 356.27},
            {"t": "2026-11-16T00:00:00-05:00", "c": 352.10}]
    t = main.with_session({"price": 352.10, "t": bars[-1]["t"]}, bars, "US")
    assert t["live"] == {"price": 352.10, "day": "2026-11-16"} and t["close"] == 356.27
    assert main.close_price(t) == 356.27 and main.close_day(t) == "2026-11-13"
    live = main.deep_live_price({"trend": t})
    assert live["price"] == 352.10 and live["at"]
    # after the close the last candle is the close: nothing live, "last close" is its day
    done = main.with_session({"price": 356.27, "t": bars[1]["t"]}, bars[:2], "US")
    assert "live" not in done and main.close_price(done) == 356.27 and main.close_day(done) == "2026-11-13"
    assert main.deep_live_price({"trend": done}) is None


def test_a_us_deep_dive_in_the_session_values_the_company_at_the_last_close(monkeypatch):
    from app import main
    seen = []
    monkeypatch.setattr(main.sec_feed, "company", lambda sym: {"name": "Apple Inc.", "documents": []})
    monkeypatch.setattr(main.sec, "with_fx", lambda p, f: p)
    monkeypatch.setattr(main, "us_price_ratios", lambda p, sym: {"price": 352.10, "prev_close": 356.27, "at": "2026-11-16T19:20:00+00:00"})
    monkeypatch.setattr(main.sec, "ratios", lambda p, price, *a: seen.append(price) or {"pe": price / 9.08})
    monkeypatch.setattr(main, "research_hub_market_open", lambda region: True)
    monkeypatch.setattr(main, "price_status", lambda sym, market="IN": ({"price": 352.10, "t": "2026-11-16T00:00:00-05:00",
                                                                          "live": {"price": 352.10, "day": "2026-11-16"},
                                                                          "close": 356.27, "close_t": "2026-11-13T00:00:00-05:00"}, None))
    b = main.deep_base_us("AAPL")
    assert seen == [356.27] and b["p"]["ratios"]["pe"] == 356.27 / 9.08 and b["in_session"]
    assert main.deep_live_price(b) == {"price": 352.10, "at": "2026-11-16T19:20:00+00:00"}
    assert main.close_day(b["trend"]) == "2026-11-13"


# ---------- item 8 / LIVE9B-010: after the close, a stock's last-session quote serves every page until the next session ----------
def test_a_closed_markets_quotes_come_from_the_kept_closes(monkeypatch):
    from app.intel import company as C
    C.forget_closed_quotes()
    reads = []

    class Kite:
        def ready(self):
            return True

    class Hub(C.Research):
        def __init__(self):
            self.kite = Kite()

        def _last_session(self, sym, q, bars=None):
            reads.append(sym)                       # each costs the broker's daily candles
            return {**q, "change_pct": 0.38}
    monkeypatch.setattr(C, "market_open", lambda region, now=None: False)
    monkeypatch.setattr(C, "_settled_day", lambda region: "2026-11-16")
    monkeypatch.setattr(C.quote_share, "read", lambda kite, syms: {s: {"price": 100.0 + i, "at": "2026-11-16T15:30:00+05:30"} for i, s in enumerate(syms)})
    h = Hub()
    first, _ = h.quotes_pending("IN", ["RELIANCE", "TCS"])
    assert first["RELIANCE"]["price"] == 100.0 and sorted(reads) == ["RELIANCE", "TCS"]
    t0 = time.time()
    again, _ = h.quotes_pending("IN", ["RELIANCE", "TCS"])
    assert again == first and sorted(reads) == ["RELIANCE", "TCS"] and time.time() - t0 < 0.5     # no broker read the second time
    # hours later, same settled session: still kept; once a newer session settles, read again
    monkeypatch.setattr(C.time, "time", lambda: t0 + 5 * 3600)
    assert C._closed_quote("IN", "TCS")["price"] == 101.0
    monkeypatch.setattr(C, "_settled_day", lambda region: "2026-11-17")
    assert C._closed_quote("IN", "TCS") is None
    C.forget_closed_quotes()
