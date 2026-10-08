"""The demo world (tests/world.py with the browser tests' fundamentals and screener index, tests/visual_server.py) tells
one story: an instrument has one price and one market value whichever fake source a page reads it from, the indices
agree everywhere, and each company shows its own name, description and news (R3-001, R3-002, R3-017). Round 4 adds: the
exchange's events are on trading days, the ETF list and the holdings read one price, every index and sector has its own
line, the screener's 52-week figures are the company page's, and the loss-years case is a made-up company (R4-005 to R4-104)."""
import statistics
from datetime import date, datetime, timedelta

import pytest

from app import main  # noqa: F401,I001  (first: the app wires the modules)
from app import holdings
from tests import fake_cas, fake_fundamentals, fake_prices as P
from tests import visual_server as V
from tests import world as W
from tests.fake_db import headers

H = headers("pro-token")
STOCKS = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ITC", "SBIN", "WIPRO"]


@pytest.fixture(scope="module")
def w():
    mp = pytest.MonkeyPatch()
    world = W.build(mp)
    fake_fundamentals.install(mp, main.research_hub.screener)
    V.screen_index()
    V.etf_gaps(mp)
    yield world
    world["close"]()
    mp.undo()


def test_the_price_table_closes_at_its_levels_and_stands_still_out_of_hours():
    close = P.last_close("IN")
    for name, level in (("NIFTY 50", 25000.0), ("RELIANCE", 1400.0), ("TCS", 3050.0)):
        assert P.price(name, close) == level
    clock = P.session_clock(None, "IN")
    assert P.last("RELIANCE") == P.price("RELIANCE", clock)
    # out of hours, the same reading a minute apart (no drift while nobody trades)
    shut = close + timedelta(hours=3)
    assert P.price("TCS", P.session_clock(shut, "IN"), shut) == P.price("TCS", P.session_clock(shut + timedelta(minutes=1), "IN"), shut)


def test_nifty_500_moves_with_nifty_50_and_stays_below_it():
    end = P.last_close("IN")
    for d in range(0, 800, 7):
        t = end - timedelta(days=d)
        ratio = P.price("NIFTY 500", t) / P.price("NIFTY 50", t)
        assert ratio == pytest.approx(23000 / 25000, rel=1e-6)      # to the paisa


def test_one_price_per_stock_on_every_page(w):
    c = w["client"]
    kite = main.kite.quote(STOCKS)
    rows = {r["symbol"]: r for r in c.post("/research/screens/run", headers=H, json={"region": "IN", "limit": 100}).json()["rows"]}
    holdings.save("u-pro", [{"symbol": s, "qty": 1, "avg": 100.0} for s in STOCKS], "manual")
    held = {r["symbol"]: r for r in c.get("/holdings", headers=H).json()["rows"]}
    for sym in STOCKS:
        price = P.last(sym)
        page = c.get(f"/research/company/IN/{sym}", headers=H).json()
        assert kite[sym]["price"] == price, sym
        assert main.research_hub.yahoo.meta(f"{sym}.NS")["price"] == price, sym              # the quote site
        assert page["quote"]["price"] == price, sym                                           # the company page
        assert rows[sym]["price"] == price, sym                                               # the screener
        assert held[sym]["price"] == price, sym                                               # holdings
        # one market value: shares x that price, on the company page and the screener
        # the company page re-prices the fundamentals source's market value, which that source states to the whole crore
        assert page["market_cap"] / 1e7 == pytest.approx(P.market_cap(sym), abs=1.0), sym
        assert rows[sym]["market_cap"] == pytest.approx(P.market_cap(sym), abs=1.0), sym       # the screener's, likewise
        candles = c.get(f"/research/chart/IN/{sym}?range=1m&tf=1d", headers=H).json()["candles"]
        assert candles[-1]["c"] == price, sym                                                 # the chart's last candle
    cmp = c.get("/research/compare?region=IN&a=TCS&b=INFY", headers=H).json()
    for side, sym in (("a", "TCS"), ("b", "INFY")):
        assert cmp[side]["quote"]["price"] == P.last(sym)
        assert cmp[side]["market_cap"] / 1e7 == pytest.approx(P.market_cap(sym), rel=1e-6)
        assert len(cmp[side]["metrics"]) >= 4                                                # Infosys has its numbers too


def test_one_level_per_index_on_every_page(w):
    c = w["client"]
    nifty, bank = P.last("NIFTY 50"), P.last("NIFTY BANK")
    pulse = {i["name"]: i["price"] for i in c.get("/research/pulse?region=IN", headers=H).json()["indices"]}
    assert pulse["NIFTY 50"] == nifty and pulse["NIFTY BANK"] == bank
    q = main.kite.quote(["NIFTY 50", "NIFTY BANK", "NIFTY 500"])
    assert q["NIFTY 50"]["price"] == nifty and q["NIFTY BANK"]["price"] == bank
    assert q["NIFTY 500"]["price"] < q["NIFTY 50"]["price"]
    auction = {r["indexName"]: r["currentPrice"] for r in fake_cas.answer(fake_cas.PATH, {"functionName": "indices"})}
    # the auction that has just ended: the latest close at least six minutes old (the same prices as every other page's out of hours)
    close = fake_cas.last_auction_close()
    assert auction == {"NIFTY 50": P.price("NIFTY 50", close), "NIFTY BANK": P.price("NIFTY BANK", close)}
    if P.session_clock(None, "IN") == close:
        assert auction == {"NIFTY 50": nifty, "NIFTY BANK": bank}
    stocks = {r["symbol"]: r["finalPrice"] for r in fake_cas.answer(fake_cas.PATH, {"functionName": "getCASData"})["data"] if r.get("finalPrice")}
    assert stocks == {s: P.price(s, close) for s in ("RELIANCE", "TCS", "INFY")}
    # the options desk's spot is the index's last close (it stands still in the demo world)
    assert main.options_data.kite.spot("NSE:NIFTY 50", None) == P.level("NIFTY 50")
    assert main.options_data.kite.spot("NSE:NIFTY BANK", None) == P.level("NIFTY BANK")


def test_each_company_is_itself(w):
    c = w["client"]
    tcs = c.get("/research/company/IN/TCS", headers=H).json()
    assert tcs["name"] == "Tata Consultancy Services Ltd"
    text = " ".join(filter(None, [(tcs["about"]["wiki"] or {}).get("extract"), tcs["about"]["profile"]] + [n["headline"] for n in tcs["news"]]))
    assert "Reliance" not in text and "Jio" not in text and "Tata Consultancy" in text
    # a famous profitable company shows profits (R4-104): the loss-years case is a made-up one (test_the_loss_years_case_is_made_up)
    assert all(p["v"] > 0 for p in tcs["trend"]["profit"])
    infy = c.get("/research/company/IN/INFY", headers=H).json()
    assert infy["market_cap"] and infy["trend"] and "Reliance" not in (infy["about"]["profile"] or "")
    aapl = c.get("/research/company/US/AAPL", headers=H).json()
    assert aapl["name"] == "Apple Inc" and "NVIDIA" not in str(aapl["news"])
    assert aapl["quote"]["price"] == P.last("AAPL") == main.research_hub.yahoo.meta("AAPL")["price"]
    assert aapl["market_cap"] == pytest.approx(P.market_cap("AAPL"), rel=1e-3)
    assert "Apple" in aapl["about"]["wiki"]["extract"] and "Indian" not in aapl["about"]["wiki"]["extract"]
    # its prices are as of its last trade (the close, out of hours), never the moment the page was asked for
    from datetime import datetime
    # (in market hours "now" moves on between the read and this line: within a few minutes then)
    clock = P.session_clock(None, "US")
    for at in (aapl["quote"]["at"], aapl["as_of"]):
        assert abs((datetime.fromisoformat(at) - clock).total_seconds()) < 300


def test_the_reported_numbers_are_as_of_a_year_that_has_ended():
    """Read in October 2026, a company page has the June 2026 quarter and the year to March 2026 (not 2025's)."""
    page = fake_fundamentals.company("TCS", _fixture())
    assert page["quarters"]["cols"][-1] == "Jun 2026" and "Mar 2026" in page["pl"]["cols"]
    assert page["shareholding"]["cols"][-1] == "Jun 2026"


def _fixture() -> dict:
    from app.intel.screener import Screener
    from tests.fake_intel import fake_screener
    return Screener(transport=fake_screener()).company("RELIANCE")


# ---------- round 4 ----------
def _event_days(today: date) -> dict[str, list]:
    """Every exchange event the demo world makes up for a day, by the market whose calendar it follows."""
    from tests import fake_market_events as FM
    ev = FM.state(today)
    india = [datetime.strptime(a["exDate"], "%d-%b-%Y").date() for a in W.corporate_actions(today)]
    india += [datetime.strptime(m["bm_date"], "%d-%b-%Y").date() for m in W.board_meetings(today)]
    for m in ev["rbi"]["meetings"]:
        india += [date.fromisoformat(m[k]) for k in ("start", "end", "decided", "minutes") if m.get(k)]
    for r in ev["india_data"]["calendar"]:
        india += [date.fromisoformat(r[k]) for k in ("date", "released") if r.get(k)]
    for c in ev["index"]["changes"]:
        india += [date.fromisoformat(c[k]) for k in ("announced", "effective")]
    us = [date.fromisoformat(r["date"]) for r in ev["us_data"]["releases"]]
    for m in ev["fed"]["meetings"]:
        us += [date.fromisoformat(m[k]) for k in ("start", "end")]
    return {"IN": india, "US": us}


def test_exchange_events_are_never_on_a_weekend_or_holiday():
    """Ex-dates, board meetings, the policy meetings and the data releases are on trading days whichever day of the week the
    demo is opened (R4-009); so are the US companies' results dates."""
    for k in range(21):
        today = date(2026, 10, 5) + timedelta(days=k)
        for market, days in _event_days(today).items():
            assert days, market
            for d in days:
                assert P.trading_day(market, d), f"{market} event on {d} ({d:%a}), demo day {today} ({today:%a})"
    from tests.fake_intel import us_calendar
    for row in us_calendar():
        if row["date"][:2] == "20":
            assert P.trading_day("US", date.fromisoformat(row["date"])), row
    assert P.on_trading_day(date(2026, 10, 10)) == date(2026, 10, 12)                       # a Saturday goes to Monday
    assert P.on_trading_day(date(2026, 10, 11), back=True) == date(2026, 10, 9)             # a past Sunday to the Friday


def test_the_etf_list_and_the_holdings_read_one_price_and_a_trading_day(w):
    c = w["client"]
    holdings.save("u-pro", [{"symbol": s, "qty": 1, "avg": 100.0} for s in ("NIFTYBEES", "GOLDBEES", "SILVERBEES")], "manual")
    held = {r["symbol"]: r for r in c.get("/holdings", headers=H).json()["rows"]}
    table = c.get("/invest/etf-gaps", headers=H).json()
    listed = {r["symbol"]: r for r in table["rows"]}
    for sym in ("NIFTYBEES", "GOLDBEES", "SILVERBEES"):
        assert held[sym]["price"] == listed[sym]["price"] == P.last(sym), sym                  # the badge's price is the row's
        assert listed[sym]["nav_gap"] == pytest.approx((listed[sym]["price"] / listed[sym]["nav"] - 1) * 100, abs=0.006), sym
    # the list is dated the latest trading day's close: never a weekend, never a time still to come (R4-010)
    stamp = datetime.fromisoformat(table["as_of"])
    assert P.trading_day("IN", stamp.date()) and stamp <= datetime.now(P.IST)
    assert table["nav_as_of"] == stamp.date().isoformat()
    assert stamp == P.last_close("IN")


def test_every_index_and_sector_has_its_own_line():
    """NIFTY and SENSEX move together but are not one line, nor are the S&P 500 and the dollar in rupees (R4-102); no two
    sectors share one (R4-022)."""
    end = P.last_close("IN")

    def line(name):
        closes = [P.price(name, end - timedelta(days=d)) for d in range(30, -1, -1)]
        return [round(x / closes[0] * 100, 3) for x in closes]

    for a, b in (("NIFTY 50", "SENSEX"), ("^GSPC", "USDINR=X"), ("NIFTY 50", "NIFTY BANK"), ("^GSPC", "GC=F")):
        la, lb = line(a), line(b)
        assert sum(1 for x, y in zip(la, lb) if abs(x - y) > 0.05) >= 20, (a, b)
        assert round(P.last(a) / P.prev(a), 4) != round(P.last(b) / P.prev(b), 4), (a, b)      # nor the same change today
    assert statistics.correlation(line("NIFTY 50"), line("SENSEX")) > 0.9                     # the two Indian indices still go together
    from app import rotation
    names = sorted({x for g in rotation.SECTORS.values() for v in (g.values() if isinstance(g, dict) else [g])
                    if isinstance(v, (list, tuple, set)) for x in v if isinstance(x, str) and x.startswith("NIFTY ")})
    assert len(names) > 25
    assert len({tuple(line(n)) for n in names}) == len(names)


def test_the_rotation_page_has_no_tied_sectors(w):
    rows = w["client"].get("/research/rotation?region=IN", headers=H).json()["rows"]
    assert len(rows) > 25
    assert len({(r["x"], r["y"]) for r in rows}) == len(rows)


def test_the_screeners_52_week_high_is_the_company_pages(w):
    """"vs 52-week high" is the price over the 52-week high the company page shows, minus 1, rounded the same way (R4-103)."""
    c = w["client"]
    rows = {r["symbol"]: r for r in c.post("/research/screens/run", headers=H, json={"region": "IN", "limit": 100}).json()["rows"]}
    assert len(rows) >= 20
    for sym, row in rows.items():
        page = c.get(f"/research/company/IN/{sym}", headers=H).json()
        want = (row["price"] / page["range52"]["high"] - 1) * 100         # the screener's own price: the table's column
        assert row["from_high"] == pytest.approx(want, abs=0.006), sym
        assert page["range52"]["low"] < page["quote"]["price"] <= page["range52"]["high"] * 1.05, sym
    # not a few values shared by many companies
    assert len({r["from_high"] for r in rows.values()}) >= len(rows) - 2


def test_the_loss_years_case_is_made_up(w):
    """Only a made-up company has loss years; the well-known ones are profitable in every year, with sales that don't fall (R4-104)."""
    c = w["client"]
    orion = c.get("/research/company/IN/ORIONPOLY", headers=H).json()
    assert orion["name"] == "Orion Polymers Ltd"
    assert [p["v"] for p in orion["trend"]["profit"]][:3] == [-640, -1250, -980]
    assert orion["market_cap"] / 1e7 == pytest.approx(P.market_cap("ORIONPOLY"), abs=1.0)
    for sym in fake_fundamentals.PROFILE:
        if sym == "ORIONPOLY":
            continue
        page = fake_fundamentals.company(sym, _fixture())
        profit = [v for v in page["pl"]["rows"]["Net Profit"] if v is not None]
        assert profit and all(v > 0 for v in profit), sym
        sales = next(v for k, v in page["pl"]["rows"].items() if k in ("Sales", "Revenue"))[:-1]       # the full years (no TTM)
        assert all(b >= a for a, b in zip(sales, sales[1:])), sym


def test_each_company_has_its_own_filings(w):
    """No more one "QIP opened" row under every company (R4-012): each stock's filings are its own, and the count in "N filings
    in all" is the number the page can list."""
    c = w["client"]
    seen = {}
    for sym in ("RELIANCE", "TCS", "INFY", "HDFCBANK", "ITC", "SLOWCO-BE", "ONGC"):
        rep = c.get(f"/research/filings/{sym}", headers=H).json()
        seen[sym] = rep
        assert rep["summary"]["total"] == len(rep["items"]) > 0 or sym == "ONGC", sym
        assert all(i["url"] and sym.split("-")[0] in i["url"] or sym == "RELIANCE" for i in rep["items"]), sym
    keys = {sym: frozenset((i["subject"], i["text"]) for i in rep["items"]) for sym, rep in seen.items()}
    assert len(set(keys.values())) == len(keys)                                       # no two companies share a list
    qip = [sym for sym, rep in seen.items() if any(i["category"] == "qip" for i in rep["items"])]
    assert qip == ["RELIANCE"]


def test_the_live_breadth_card_is_never_live_as_of_a_time_still_to_come(w):
    """"Live as of 10:45" at ten past ten was a time that had not happened (R4-010): the demo's points run up to the market's last
    trade, whatever the time of day."""
    from app import breadth_live as BL
    mp = pytest.MonkeyPatch()
    try:
        V.live_breadth(mp, {"nifty500": 120, "nifty50": 50})
        v = BL.view("nifty50")
        assert v["state"] == "live" and 3 <= len(v["points"]) <= 6
        at = datetime.fromisoformat(f"{v['day']}T{v['as_of']}:00").replace(tzinfo=P.IST)
        assert at <= datetime.now(P.IST), (v["day"], v["as_of"])
        assert P.trading_day("IN", date.fromisoformat(v["day"]))
        times = [p[0] for p in v["points"]]
        assert times == sorted(set(times)) and "09:15" <= times[0] and times[-1] <= "15:30"
    finally:
        mp.undo()
