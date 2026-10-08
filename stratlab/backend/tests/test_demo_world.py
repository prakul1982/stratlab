"""The demo world (tests/world.py with the browser tests' fundamentals and screener index, tests/visual_server.py) tells
one story: an instrument has one price and one market value whichever fake source a page reads it from, the indices
agree everywhere, and each company shows its own name, description and news (R3-001, R3-002, R3-017)."""
from datetime import timedelta

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
    assert auction == {"NIFTY 50": nifty, "NIFTY BANK": bank}
    stocks = {r["symbol"]: r["finalPrice"] for r in fake_cas.answer(fake_cas.PATH, {"functionName": "getCASData"})["data"] if r.get("finalPrice")}
    assert stocks == {s: P.last(s) for s in ("RELIANCE", "TCS", "INFY")}
    # the options desk's spot is the index's last close (it stands still in the demo world)
    assert main.options_data.kite.spot("NSE:NIFTY 50", None) == P.level("NIFTY 50")
    assert main.options_data.kite.spot("NSE:NIFTY BANK", None) == P.level("NIFTY BANK")


def test_each_company_is_itself(w):
    c = w["client"]
    tcs = c.get("/research/company/IN/TCS", headers=H).json()
    assert tcs["name"] == "Tata Consultancy Services Ltd"
    text = " ".join(filter(None, [(tcs["about"]["wiki"] or {}).get("extract"), tcs["about"]["profile"]] + [n["headline"] for n in tcs["news"]]))
    assert "Reliance" not in text and "Jio" not in text and "Tata Consultancy" in text
    assert [p["v"] for p in tcs["trend"]["profit"]][:3] == [-8520, -53360, -40080]         # still the loss-years case
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
