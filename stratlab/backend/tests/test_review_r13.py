"""Round 13 review: the US close and the US brief, watched live on Fri 9 Oct 2026, 20:05 to 21:57 UTC.

Every moment here is fixed (the 16:00 ET close of Fri 9 Oct 2026 is 20:00 UTC); nothing depends on today's date, the
weekday the tests run on, or a background job having run. No network is read."""
import json
import time
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app import main  # noqa: F401, I001  (first: the app loads the newsletter job before the modules built on it)
from app import admin_jobs, breadth, db, scan, stock_alerts, stock_pages, us_ticker
from app.data.yahoo_markets import YahooProvider
from app.intel import grounding, routes
from app.intel.company import Research, us_year_range
from app.newsletter import content, job, write
from app.options import data as optdata
from app.options.data import OptionsData, broker_qty, frozen_series, no_live_quote
from tests.test_review_r10v import facts_page

UTC = timezone.utc
CLOSE = datetime(2026, 10, 9, 20, 0, tzinfo=UTC)          # 16:00 ET, Fri 9 Oct 2026
FRI = date(2026, 10, 9)


@pytest.fixture
def mem(monkeypatch):
    store: dict = {}
    monkeypatch.setattr(db, "get_setting", lambda k: store.get(k))
    monkeypatch.setattr(db, "set_setting", lambda k, v: store.__setitem__(k, v))
    monkeypatch.setattr(db, "delete_setting", lambda k: store.pop(k, None))
    monkeypatch.setattr(db, "all_settings_with_prefix", lambda p: [(k, v) for k, v in sorted(store.items()) if k.startswith(p)])
    return store


# ---------- R13-001: BRK.B is BRK-B everywhere in the app ----------
def test_a_dotted_us_share_class_is_written_with_a_dash():
    for typed in ("BRK.B", "brk.b", " BRK/B ", "BRK-B"):
        assert us_ticker.canon_us(typed) == "BRK-B", typed
    assert us_ticker.canon_us("BF.B") == "BF-B" and us_ticker.canon_us("MOG.A") == "MOG-A"
    # not a share class: a preferred series, an ordinary ticker, an index, and India's symbols, as typed
    assert us_ticker.canon_us("BAC.PRL") == "BAC.PRL" and us_ticker.canon_us("AAPL") == "AAPL" and us_ticker.canon_us("^GSPC") == "^GSPC"
    assert us_ticker.canon("IN", "m&m") == "M&M" and us_ticker.canon("IN", "BRK.B") == "BRK.B"


class _Hub:
    """The research hub, answering what each route asks it for, so the symbol it was asked about can be read back."""

    def __init__(self):
        self.asked = []

    def company(self, region, symbol, lean=False):
        self.asked.append(("company", symbol))
        return {"region": region, "symbol": symbol, "name": "Berkshire Hathaway", "quote": {"price": 515.62, "at": "2026-10-09T16:00:00-04:00"},
                "market_cap": 1.104e12, "metrics": []}

    def company_more(self, region, symbol):
        self.asked.append(("more", symbol))
        return {"news": [], "wiki": None, "peers": [], "sources": []}

    def chart(self, region, symbol, rng, tf, before):
        self.asked.append(("chart", symbol))
        return {"candles": [], "more": False}

    def quotes(self, region, symbols):
        self.asked.append(("quotes", tuple(symbols)))
        return {s: {"price": 515.62} for s in symbols}

    def search(self, q, region):
        self.asked.append(("search", q))
        return []


@pytest.fixture
def client(monkeypatch, mem):
    hub = _Hub()
    monkeypatch.setattr(routes, "hub", hub)
    monkeypatch.setattr(routes, "page_figures", lambda r, c: c)
    main.app.dependency_overrides[main.current_profile] = lambda: {"id": "u1", "_plan": "pro", "plan": "pro"}
    c = TestClient(main.app)
    c.hub = hub
    yield c
    main.app.dependency_overrides.clear()


def test_brk_dot_b_asks_every_source_for_brk_dash_b(client):
    c = client.get("/research/company/US/BRK.B").json()
    assert c["symbol"] == "BRK-B" and c["market_cap"] == 1.104e12          # the canonical page's share basis, not $983.7B
    client.get("/research/company/US/brk.b/more")
    assert client.get("/research/chart/US/BRK.B?tf=1d&range=1y").status_code == 200       # was a 502
    q = client.get("/research/quotes?region=US&symbols=BRK.B,AAPL").json()
    assert q["BRK-B"]["price"] == 515.62 and q["BRK.B"]["price"] == 515.62   # also under the ticker asked for
    client.get("/research/search?q=BRK.B&region=US")
    assert client.hub.asked == [("company", "BRK-B"), ("more", "BRK-B"), ("chart", "BRK-B"), ("quotes", ("BRK-B", "AAPL")), ("search", "BRK-B")]
    # India's symbols are left as they are
    client.get("/research/company/IN/M&M")
    assert client.hub.asked[-1] == ("company", "M&M")


def test_the_watchlist_compare_and_alerts_keep_brk_dash_b(client, monkeypatch):
    got = client.put("/research/watchlist", json={"items": [{"region": "US", "symbol": "BRK.B"}, {"region": "US", "symbol": "BRK-B"}]}).json()
    assert got["items"] == [{"region": "US", "symbol": "BRK-B", "name": None}]          # one item, the dashed one
    client.get("/research/compare?a=BRK.B&b=AAPL&region=US")
    assert ("company", "BRK-B") in client.hub.asked
    a = stock_alerts.clean({"region": "US", "symbol": "brk.b", "kind": "price", "op": "above", "value": 520})
    assert a["symbol"] == "BRK-B"
    assert main.deep_symbol("brk.b", "US") == "BRK-B"


def test_the_hub_and_the_markets_registry_read_brk_dash_b(monkeypatch):
    seen = []
    r = Research.__new__(Research)
    monkeypatch.setattr(r, "_company_us", lambda sym, lean=False: seen.append(sym) or {"symbol": sym}, raising=False)
    assert r.company("US", "brk.b")["symbol"] == "BRK-B" and seen == ["BRK-B"]

    class Yahoo:                          # notebooks, charts and scans resolve "US:BRK.B" to the source's own BRK-B
        WINDOW = 400

        def chart(self, key, tf, days, **kw):
            seen.append(key)
            return {"meta": {"regularMarketPrice": 515.62, "longName": "Berkshire Hathaway Inc.", "currency": "USD"}, "candles": []}
    prov = YahooProvider("US", Yahoo())
    inst = prov.instrument("BRK.B")
    assert inst["id"] == "US:BRK-B" and seen[-1] == "BRK-B"


# ---------- R13-002: USDINR's frozen quote ----------
FROZEN = [{"t": f"2026-09-{d:02d}T00:00:00+05:30", "o": 96.135, "h": 96.135, "l": 96.135, "c": 96.135, "v": 0}
          for d in (9, 10, 11, 15, 16, 17, 18, 21, 22, 23)]


def test_a_quote_with_no_bid_no_ask_and_no_volume_is_no_live_quote():
    assert no_live_quote({"ltp": 1.1025, "bid": None, "ask": None, "oi": 0, "volume": 0, "close": 1.1025})      # the reviewer's legs
    assert no_live_quote(None)
    assert not no_live_quote({"ltp": 1.1, "bid": 1.09, "ask": None, "volume": 0})        # someone bids: live
    assert not no_live_quote({"ltp": 1.1, "bid": None, "ask": None, "volume": 1200})    # traded today: its last trade stands (R11C-007)
    assert not no_live_quote({"ltp": 1.1, "bid": None, "ask": None})                     # no volume figure: can't be judged here


def test_a_month_of_one_standing_price_with_no_volume_is_a_frozen_series():
    assert frozen_series(FROZEN)
    moving = [dict(b, c=96.135 + i * 0.01, h=96.2 + i * 0.01, v=1000) for i, b in enumerate(FROZEN)]
    assert not frozen_series(moving) and not frozen_series(FROZEN[:3])
    assert not frozen_series(FROZEN[:-1] + [dict(FROZEN[-1], c=96.5, h=96.5)])


class _CdsKite:
    """The broker as the reviewer saw it on 9 Oct: USDINR's options and its future with no bid, no ask, no volume and a
    month-old last price (96.135); the spot pair at 96.76."""

    def __init__(self, exp: date, fut: date):
        self.exp, self.fut, self.baskets = exp, fut, []
        self.kite = self

    def ready(self):
        return True

    def _require(self):
        pass

    def _throttle(self):
        pass

    def instruments(self, exch):
        if exch != "CDS":
            return []
        rows = [{"tradingsymbol": "USDINR26OCTFUT", "name": "USDINR", "instrument_type": "FUT", "strike": 0, "expiry": self.fut, "lot_size": 1}]
        for k in (95.875, 96.0, 96.125, 96.25, 96.375, 96.5, 96.625, 96.75, 96.875, 97.0):
            for t in ("CE", "PE"):
                rows.append({"tradingsymbol": f"USDINR{k}{t}", "name": "USDINR", "instrument_type": t, "strike": k, "expiry": self.exp, "lot_size": 1})
        return rows

    def quote(self, keys):
        return {k: {"last_price": 96.135 if k.endswith("FUT") else 1.1025, "depth": {"buy": [], "sell": []}, "oi": 0, "volume": 0,
                    "timestamp": None, "ohlc": {"close": 96.135}} for k in keys}

    def basket_order_margins(self, orders, **kw):
        self.baskets.append(orders)
        return {"final": {"total": 1689.13 * sum(o["quantity"] for o in orders) / len(orders)}}


def test_usdinr_options_with_no_live_quote_take_the_spot_rate_and_are_not_priced(monkeypatch):
    exp, fut = FRI + timedelta(days=7), FRI + timedelta(days=19)
    monkeypatch.setattr(optdata, "ist_date", lambda: FRI)
    monkeypatch.setattr(optdata, "expired_today", lambda exch, now=None: False)
    kite = _CdsKite(exp, fut)
    data = OptionsData(kite)
    data.spot_source = lambda pair: {"USDINR=X": 96.76}.get(pair)
    spot, q, where = data.spot("CDS", "USDINR", exp.isoformat())
    assert (spot, where) == (96.76, "spot")             # not the future's 96.135, a month old
    monkeypatch.setattr(main, "options_data", data)
    main.app.dependency_overrides[main.current_profile] = lambda: {"id": "u", "_plan": "pro", "plan": "pro"}
    try:
        pv = TestClient(main.app).post("/options/preview", json={"strategy": {
            "name": "USDINR short straddle", "structure": "short_straddle", "exchange": "CDS", "underlying": "USDINR", "expiry": "current",
            "legs": [{"side": "sell", "opt": "CE", "offset": 0}, {"side": "sell", "opt": "PE", "offset": 0}],
            "timing": {"entry": "09:15", "lastEntry": "16:15", "squareoff": "16:45"}}}).json()
    finally:
        main.app.dependency_overrides.clear()
    assert pv["spot"] == 96.76 and pv["spot_from"] == "spot" and pv["atm"] == 96.75
    assert pv["no_live"] == 2 and "No live quote" in pv["no_live_text"]
    assert all(l["no_live"] and l["fill"] is None for l in pv["legs"]) and pv["charges"] is None
    # PR 181's margin fix holds for the ₹16,89,130 case: one lot is asked as quantity 1 (lots), never 1,000
    assert all(o["quantity"] == 1 for o in kite.baskets[0]) and pv["margin_one"] == pytest.approx(1689.13)
    assert broker_qty("CDS:USDINR26O1696.125CE", 1000) == 1 and broker_qty("NFO:NIFTY26O1325000CE", 65) == 65


def test_a_paper_session_never_enters_a_currency_option_with_no_live_quote():
    from app.options.engine import Contracts, OptionsEngine
    eng = OptionsEngine.__new__(OptionsEngine)
    eng.s = type("S", (), {"exchange": "CDS", "costs": type("C", (), {"slippageTicks": 0})()})()
    c = Contracts([{"opt": "CE", "strike": 96.75, "symbol": "USDINRCE", "lot": 1000}], 1000, "2026-10-16", "CDS")
    q = {"CDS:USDINRCE": {"ltp": 1.1025, "bid": None, "ask": None, "volume": 0}}
    assert eng._open_leg(None, c, q, "CE", "sell", 96.75, 1000, "entry", []) is False


def test_the_currency_chart_reads_the_contract_when_the_stitched_series_is_frozen():
    from app.data.cds import CDSProvider
    calls = []

    class Kite:
        def history(self, token, tf, days, continuous=None, **kw):
            calls.append(continuous)
            return FROZEN if continuous else [dict(b, c=96.1 + i / 50, h=96.2 + i / 50, v=5000) for i, b in enumerate(FROZEN)]
    bars = CDSProvider(Kite()).history({"token": 1, "symbol": "USDINR"}, "1d", 30)
    assert calls == [True, False] and not frozen_series(bars)


# ---------- R13-003: the US brief from settled closes ----------
def et(h, m):
    return CLOSE + timedelta(hours=h - 16, minutes=m)


def test_the_us_day_is_over_for_the_brief_once_its_closing_prints_have_settled(mem, monkeypatch):
    assert not content.closed("US", FRI, et(16, 32))          # the 9 Oct brief was built here, on provisional prints
    assert content.closed("US", FRI, et(16, 46))
    assert job.SEND_AT["US"] == ("America/New_York", "16:50") and "US 4:50 PM New York time" in job.SEND_WORDS
    monkeypatch.setattr("app.data.calendar.is_trading_day", lambda m, d: True)
    j = job.Job()
    assert j.due("market-US", et(16, 40), *job.SEND_AT["US"], region="US") is None
    assert j.due("market-US", et(16, 52), *job.SEND_AT["US"], region="US") == FRI
    # India's brief keeps its time
    assert job.SEND_AT["IN"] == ("Asia/Kolkata", "16:15")


def test_the_stage_2_plus_supertrend_list_holds_only_the_whole_rule(monkeypatch):
    rows = [{"symbol": "V", "price": 385.45, "chg": 2.76, "signal": "fresh", "st_days": 1, "stage": 2, "st_up": True, "stage_days": 31},
            {"symbol": "MA", "price": 589.14, "chg": 2.5, "signal": "fresh", "st_days": 1, "stage": 2, "st_up": True, "stage_days": 2},
            {"symbol": "UNH", "price": 379.30, "chg": 2.25, "signal": "stage2", "st_days": 9, "stage": 2, "st_up": False, "stage_days": 1}]
    monkeypatch.setattr(scan, "run", lambda reg, market, members: {"rows": rows})
    monkeypatch.setattr(content, "_main", lambda: type("M", (), {"markets": None})())
    got = content.stage2_names("US", False)
    assert [r["symbol"] for r in got["st_s2"]] == ["V", "MA"] and [r["symbol"] for r in got["stage2"]] == ["UNH"]
    f = {"kind": "market", "region": "US", "day": "2026-10-09", "weekly": False, "scan": got}
    secs = write.market_sections(f)
    assert [s["title"] for s in secs] == ["New on Stage 2 + Supertrend (20 of the largest US companies)", "New in Stage 2 only (20 of the largest US companies)"]
    assert [i["text"].split()[0] for i in secs[0]["items"]] == ["V", "MA"]
    lead = write.template(f)
    assert "2 stocks from the 20 of the largest US companies newly matched the Stage 2 + Supertrend rule." in lead
    assert "1 other stock newly entered Stage 2 without the Supertrend." in lead


def test_the_brief_reads_candles_taken_after_the_close_settled(monkeypatch):
    reads = []

    class Prov:
        def history(self, inst, tf, days, ttl=None):
            reads.append(ttl)
            return [{"t": "2026-10-09", "c": 385.45}]

    class Reg:
        def resolve(self, iid):
            return Prov(), {"token": "V"}
    settled = time.time() - 300                          # the close settled five minutes ago
    monkeypatch.setattr(scan, "settled_at", lambda market, now=None: settled if market == "US" else None)
    scan._cache.clear()
    scan._cache.set("US:V", (settled - 600, [{"t": "2026-10-09", "c": 385.70}]), 900)     # read at 16:35 ET, provisional
    assert scan._bars(Reg(), "US:V")[-1]["c"] == 385.45 and reads and reads[0] >= 60
    assert scan._bars(Reg(), "US:V")[-1]["c"] == 385.45 and len(reads) == 1           # the settled copy is kept
    scan._cache.clear()


def test_off_region_headlines_stay_out_of_the_us_brief():
    london = "London stocks post weekly gains as gilt yields retreat; telecom stocks fall – Reuters"
    assert not content.headline_ok("US", london)
    assert content.headline_ok("US", "Wall Street set for weekly gains with earnings, inflation data on tap - Reuters")
    assert content.headline_ok("US", "Wall Street ends higher as European stocks also rise")      # names its own market
    assert not content.headline_ok("US", "Sensex, Nifty end higher as IT stocks rally")
    assert not content.headline_ok("IN", "FTSE 100 slips as miners drag")


def test_the_plain_text_brief_gives_every_headline_an_address_and_the_close_as_its_stamp(mem, monkeypatch):
    google = "https://news.google.com/rss/articles/CBMi" + "x" * 400 + "?oc=5"
    issue = {"id": "market.US.2026-10-09", "kind": "market", "region": "US", "day": "2026-10-09", "weekly": False,
             "subject": "Market Brief US, Fri 9 Oct: S&P 500 +0.59%", "summary": "S&P 500 +0.59% today.", "indices": [],
             "at": "2026-10-09T16:32:00-04:00",
             "sections": [{"title": "Headlines", "items": [{"text": "Wall Street set for weekly gains - Reuters", "url": google},
                                                           {"text": "Stocks rise", "url": "https://example.com/a"}]}]}
    html, text = write.render(issue)
    short = "https://stratlab.studio/news-link/market.US.2026-10-09/0"
    assert short in text and "(https://example.com/a)" in text and google not in text
    assert short in html and google.replace("&", "&amp;") not in html and google not in html      # R19-006: the HTML links the same short address
    assert "Prices and numbers as of the 16:00 ET close of 9 Oct 2026" in text and "16:32" not in text
    job.save(issue)
    c = TestClient(main.app)
    r = c.get("/news-link/market.US.2026-10-09/0", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == google
    gone = c.get("/news-link/market.US.2026-10-09/7", follow_redirects=False)       # R23-004: a story no longer listed opens the brief
    assert gone.status_code == 302 and gone.headers["location"].endswith("/news?tab=US&issue=market.US.2026-10-09")
    assert c.get("/news-link/my_stocks.u1.2026-10-09/0", follow_redirects=False).status_code == 404     # only a market brief's


# ---------- R13-005: "Last close" waits for the settle point ----------
def test_a_us_price_between_the_close_and_its_settle_point_is_still_settling():
    assert stock_pages.settling("US", et(16, 12)) == "2026-10-09"
    assert stock_pages.settling("US", et(16, 44)) == "2026-10-09"
    assert stock_pages.settling("US", et(16, 46)) is None and stock_pages.settling("US", et(15, 59)) is None
    assert stock_pages.settling("US", et(16, 12) + timedelta(days=1)) is None          # Saturday
    assert stock_pages.settling("IN", datetime(2026, 10, 9, 10, 5, tzinfo=UTC)) is None  # India: the official close (R8B-001)
    c = {"quote": {"price": 336.68, "at": "2026-10-09T16:00:00-04:00"}}
    assert routes.price_phase("US", c, et(16, 12)) == "settling"
    assert routes.price_phase("US", c, et(16, 50)) is None
    assert routes.price_phase("US", {"quote": {"price": 1, "at": "2026-10-08T16:00:00-04:00"}}, et(16, 12)) is None


# ---------- R13-006: public pages after the close ----------
def test_no_cached_copy_of_a_public_page_outlives_the_next_settle_point():
    f = facts_page(at="2026-10-09", region="US")
    early = stock_pages.cache_control("US", f, datetime(2026, 10, 9, 13, 0, tzinfo=UTC))        # 09:00 ET: hours to go
    assert early == stock_pages.CACHE_CONTROL
    near = stock_pages.cache_control("US", f, et(16, 40))                                      # five minutes before it
    assert "s-maxage=300" in near and "stale-while-revalidate=0" in near
    assert stock_pages.html_ttl("US", et(16, 40)) == 300
    behind = facts_page(at="2026-10-08", region="US")                                          # the page still on 8 Oct
    assert stock_pages.cache_control("US", behind, et(17, 28)) == stock_pages.BEHIND_CACHE


def test_the_long_tail_is_retried_within_minutes_on_a_fresh_read():
    assert main.PRICE_REFRESH["US"][0] >= 300
    assert main.refresh_wait({"US": {"refreshed": 300, "left": 900}}) == main.PRICE_REFRESH_BACKLOG
    assert main.refresh_wait({"US": {"refreshed": 40, "left": 0, "retry": 6}}) == main.PRICE_REFRESH_RETRY <= 180
    assert main.refresh_wait({"US": {"refreshed": 40, "left": 0}}) == main.PRICE_REFRESH_EVERY


def test_a_page_on_an_older_close_never_says_prices_are_closing_prices_beside_last_price():
    page = stock_pages.render(facts_page(at="2026-09-30"), "US", "RDY", None)
    assert "Last price, 30 Sep 2026" in page and "Prices are closing prices" not in page
    assert "The price shown is the close of 30 Sep 2026, the last this page has" in page


# ---------- R13-008: one 365-day window for the US range ----------
def test_the_us_52_week_low_is_the_last_365_days_of_candles():
    bars = [{"t": "2025-10-07T00:00:00-04:00", "o": 66, "h": 66.5, "l": 65.87, "c": 66.1},     # 367 days back
            {"t": "2025-10-10T00:00:00-04:00", "o": 66.2, "h": 66.8, "l": 66.00, "c": 66.4}]
    bars += [{"t": f"2026-{m:02d}-15T00:00:00-04:00", "o": 80, "h": 90.0 if m == 6 else 81, "l": 79, "c": 80} for m in range(1, 10)]
    bars += [{"t": "2026-10-09T00:00:00-04:00", "o": 87.8, "h": 88.3, "l": 87.6, "c": 88.05}]
    rng = us_year_range({"low": 65.87, "high": 90.0}, bars, 88.05)
    assert rng == {"low": 66.0, "high": 90.0}
    assert us_year_range({"low": 65.87, "high": 90.0}, [], 88.05) == {"low": 65.87, "high": 90.0}       # no candles: as given


# ---------- R13-009: breadth's stated time and revised days ----------
def test_breadth_says_when_the_count_is_in_and_notes_a_revised_day(mem):
    assert breadth.due_label("US") == "5:55 PM ET"
    row = lambda adv, dec, unch: [501, adv, dec, unch] + [0] * (len(breadth.COLS) - 4)      # noqa: E731
    old = {"2026-10-07": row(250, 250, 1), "2026-10-08": row(337, 163, 1)}
    new = {"2026-10-08": row(338, 163, 1), "2026-10-09": row(317, 184, 0)}
    rev = breadth.revisions(old, new, "2026-10-09")
    assert rev == [{"day": "2026-10-08", "before": {"adv": 337, "dec": 163, "unch": 1}, "after": {"adv": 338, "dec": 163, "unch": 1}}]
    days = {f"2026-10-0{d}": row(300, 200, 1) for d in range(1, 9)} | {"2026-10-09": row(317, 184, 0)}
    breadth.save_hist("sp500", days, rev)
    assert breadth.view("sp500")["revised"] == rev


# ---------- R13-011: one mood per close, no unbacked causes ----------
HEADS = ["Wall Street set for weekly gains with earnings, inflation data on tap - Reuters",
         "What's behind the recovery rally in tech stocks — plus, Elon Musk's very good week"]


def test_a_cause_no_headline_reports_is_dropped_from_the_mood():
    assert not grounding.cause_backed("Strong earnings helped lift most sectors, with nine advancing and two falling.", HEADS)
    assert grounding.cause_backed("The Nasdaq rose 0.64% amid a recovery rally in tech stocks.", HEADS)
    assert grounding.cause_backed("The S&P 500 rose 0.59%, with nine of eleven sectors up.", HEADS)
    idx = [{"name": "S&P 500", "price": 7811.54, "change_pct": 0.59, "from_high_pct": -0.4, "day": "2026-10-09"}]
    read = {"tone": "The S&P 500 rose 0.59%. Strong earnings helped lift most sectors.", "hot": [], "flows": [], "themes": []}
    out = grounding.ground_pulse(read, idx, [{"headline": h} for h in HEADS])
    assert "earnings" not in out["tone"] and "0.59%" in out["tone"]


def test_after_the_close_the_mood_is_one_read_per_close(monkeypatch):
    got = {}

    class Hub:
        def indices(self, r):
            return [{"name": "S&P 500", "price": 7811.54, "change_pct": 0.59, "day": "2026-10-09", "live": False}]
    monkeypatch.setattr(routes, "hub", Hub())
    monkeypatch.setattr(routes, "market_open", lambda r, now=None: False)
    monkeypatch.setattr(routes, "ai_call", lambda profile, kind, key, ttl, refresh, build, counted=True, min_age=0:
                        got.update(key=key, ttl=ttl, min_age=min_age) or {"tone": "x"})
    routes.pulse_ai(region="US", refresh=True, profile={"id": "u"})
    first = got["key"]
    assert first[2] == "close" and got["ttl"] == routes.CLOSED_MOOD_TTL == got["min_age"]
    routes.pulse_ai(region="US", profile={"id": "u"})
    assert got["key"] == first                                # no hour in it: twelve minutes later, the same read


# ---------- R13-012: the holidays read failing is a Check while months are on file ----------
def test_the_exchange_holidays_row_is_a_check_with_the_days_on_file(monkeypatch):
    monkeypatch.setattr(main, "calendar_status", lambda: {"days_left": 83, "auto": {"at": None, "error": "Couldn't reach the exchange.", "count": 0}})
    row = next(r for r in admin_jobs.rows() if r["id"] == "holidays")
    assert row["state"] == "warn" and row["note"] == "Holidays on file for 83 more days · live feed down"
    assert row["error"]                                   # the read's own problem is still said
    monkeypatch.setattr(main, "calendar_status", lambda: {"days_left": 12, "auto": {"at": None, "error": "Couldn't reach the exchange.", "count": 0}})
    assert next(r for r in admin_jobs.rows() if r["id"] == "holidays")["state"] == "bad"     # a real shortage stays a Problem


def test_the_headline_links_are_numbered_in_the_order_the_brief_lists_them(mem):
    # the brief's issue as stored keeps its sections in order for the headline links
    issue = {"sections": [{"title": "Indices", "items": [{"text": "x"}]}, {"title": "Headlines", "items": [{"text": "a", "url": "https://a"}, {"text": "b"}]}]}
    assert write.headline_urls(json.loads(json.dumps(issue))) == ["https://a", None]


def test_an_early_close_day_settles_from_its_own_close():
    half = datetime(2026, 11, 27, 13, 20, tzinfo=timezone(timedelta(hours=-5)))        # the day after Thanksgiving: 13:00 close
    assert stock_pages.close_of("US", half.date()) == "13:00" and stock_pages.close_of("US", date(2026, 11, 25)) == "16:00"
    assert stock_pages.settling("US", half) == "2026-11-27"
    assert stock_pages.settling("US", half.replace(hour=16, minute=10)) is None
    after = half.replace(minute=50)
    assert stock_pages.last_close("US", after)[0] == date(2026, 11, 27)
    bars = [{"t": "2026-11-25T00:00:00-05:00"}, {"t": "2026-11-27T00:00:00-05:00"}]
    assert stock_pages.closed_bars(bars, "US", after) == bars
    assert stock_pages.closed_bars(bars, "US", half) == bars[:1]                          # still settling
    from app.intel.company import market_open
    assert market_open("US", half.replace(hour=12, minute=59)) and not market_open("US", half)
