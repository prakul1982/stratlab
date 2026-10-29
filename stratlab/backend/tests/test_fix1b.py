"""FIX-1B: the findings of the live-site review LIVE-1B (the real site, with test accounts and signed out), each with the test
that proves it. Plain asserts on the existing fixtures and the `world` helpers."""
import base64
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app import holdings, main
from tests import world

FIX = Path(__file__).parent / "fixtures" / "holdings"
PRO, FREE = world.headers("pro-token"), world.headers("free-token")


@pytest.fixture
def w(monkeypatch):
    built = world.build(monkeypatch)
    yield built
    built["close"]()


def csv_upload(c, text: str, mode="replace", headers=PRO, name="x.csv"):
    return c.post("/holdings/import", headers=headers, json={"filename": name, "data": base64.b64encode(text.encode()).decode(), "mode": mode})


def file_upload(c, name: str, mode="replace", headers=PRO):
    return c.post("/holdings/import", headers=headers, json={"filename": name, "data": base64.b64encode((FIX / name).read_bytes()).decode(), "mode": mode})


# ---------- Holdings ----------
def test_live1b_003_a_position_too_large_to_be_real_is_refused_with_its_reason(w):
    """1,000,000,000 shares of a Rs 685 stock was saved and made every figure Rs 68,530 crore."""
    c = w["client"]
    r = csv_upload(c, "Symbol,Quantity,Average price\nHDFCBANK,1000000000,685\nTCS,10,3200\n")
    assert r.status_code == 200, r.text
    body = r.json()
    assert [x["symbol"] for x in body["holdings"]["rows"]] == ["TCS"]                    # the sane line is kept
    bad = [u for u in body["unmatched"] if u["text"] == "HDFCBANK" or u.get("symbol") == "HDFCBANK"]
    assert bad and "crore" in bad[0]["reason"] and "Check the quantity" in bad[0]["reason"]
    # typed by hand: the line comes back unmatched with the reason, and nothing is added
    r = c.put("/holdings", headers=PRO, json={"changes": [{"op": "add", "symbol": "INFY", "qty": 5e8, "avg": 1500, "market": "IN"}]})
    assert r.status_code == 200 and "crore" in r.json()["unmatched"][0]["reason"]
    assert "INFY" not in {x["symbol"] for x in c.get("/holdings", headers=PRO).json()["rows"]}
    # a stock already held, its quantity edited to a size that can't be real: a 422 with the reason for the quantity box
    r = c.put("/holdings", headers=PRO, json={"changes": [{"op": "set", "symbol": "TCS", "qty": 9e8, "market": "IN"}]})
    assert r.status_code == 422 and "Check the quantity" in r.json()["detail"]["fields"]["qty"]
    assert {x["symbol"]: x for x in c.get("/holdings", headers=PRO).json()["rows"]}["TCS"]["qty"] == 10
    # an ordinary large holding still saves
    r = c.put("/holdings", headers=PRO, json={"changes": [{"op": "add", "symbol": "INFY", "qty": 100000, "avg": 1500, "market": "IN"}]})
    assert r.status_code == 200, r.text


def test_live1b_003_the_size_rule_in_rupees_and_dollars():
    assert holdings.size_problem(10, 3200) is None and holdings.size_problem(1e9, None) is None       # nothing to compare: left alone
    assert "₹68,530 crore" in holdings.size_problem(1e9, 685.3)                            # 1e9 x Rs 685.30 = Rs 68,530 crore
    assert holdings.size_problem(50000, 150, "USD") is None and "million" in holdings.size_problem(1e6, 300, "USD")


def test_live1b_046_indian_shares_are_whole_units(w):
    c = w["client"]
    r = c.put("/holdings", headers=PRO, json={"changes": [{"op": "add", "symbol": "TCS", "qty": 2.5, "avg": 3000, "market": "IN"}]})
    assert r.status_code == 422 and r.json()["detail"]["fields"]["qty"].startswith("Whole shares only")
    assert "TCS" not in {x["symbol"] for x in c.get("/holdings", headers=PRO).json()["rows"]}
    assert holdings.whole_problem(2.5, "US") is None and holdings.whole_problem(3.0, "IN") is None and holdings.whole_problem(0.5, "IN")


def test_live1b_065_the_same_file_added_twice_is_recognised(w):
    c = w["client"]
    first = file_upload(c, "zerodha_kite_holdings.csv", "replace").json()
    sbin = {x["symbol"]: x for x in first["holdings"]["rows"]}["SBIN"]["qty"]
    again = file_upload(c, "zerodha_kite_holdings.csv", "add")
    assert again.status_code == 200
    body = again.json()
    assert body["duplicate"] is True and body["saved"] is False
    assert {x["symbol"]: x for x in body["holdings"]["rows"]}["SBIN"]["qty"] == sbin          # not doubled
    # a different file still adds; and after a delete the same file can be read again
    other = file_upload(c, "upstox_holdings.csv", "add").json()
    assert other["saved"] is True and not other["duplicate"]
    assert c.delete("/holdings", headers=PRO).status_code == 200
    assert file_upload(c, "zerodha_kite_holdings.csv", "add").json()["saved"] is True


def test_live1b_065_replacing_makes_that_file_the_only_one_remembered(w):
    c = w["client"]
    file_upload(c, "zerodha_kite_holdings.csv", "replace")
    file_upload(c, "upstox_holdings.csv", "replace")
    assert file_upload(c, "zerodha_kite_holdings.csv", "add").json()["saved"] is True          # no longer "in" the holdings


def test_live1b_006_a_company_has_the_exchange_lists_name_not_the_feeds_capitals():
    listed = {"SBIN": "State Bank of India"}
    equity = lambda s: {"symbol": s, "exchange": "NSE", "name": "STATE BANK OF INDIA"} if s == "SBIN" else None
    m = holdings.Matcher(equity, lambda n: equity("SBIN"), lambda c: None, listed, True)
    assert m.match({"symbol": "SBIN"})[0]["name"] == "State Bank of India"
    assert m.match({"symbol": "", "name": "state bank of india"})[0]["name"] == "State Bank of India"
    assert m.match({"symbol": "SBIN"})[0]["name"] == holdings.Matcher(lambda s: None, lambda n: None, lambda c: None, listed, False).match({"symbol": "SBIN"})[0]["name"]


def test_live1b_008_prices_as_of_stops_at_the_india_close():
    """15:59 IST is the closing session still trading at the 15:30 close's price."""
    t = datetime(2026, 10, 28, 10, 29, tzinfo=timezone.utc)                  # 15:59 IST
    assert holdings.at_close(t) == datetime(2026, 10, 28, 10, 0, tzinfo=timezone.utc)       # 15:30 IST
    early = datetime(2026, 10, 28, 8, 0, tzinfo=timezone.utc)                # 13:30 IST, the market is trading
    assert holdings.at_close(early) == early
    assert main._prices_at([{"at": "2026-10-28T15:59:12+05:30"}], True).startswith("2026-10-28T15:30")
    assert main._prices_at([{"at": "2026-10-29T01:30:00+05:30"}]).startswith("2026-10-29T01:30")           # the US close is left as it is


def test_live1b_008_a_list_of_both_markets_has_a_stamp_for_each(w, monkeypatch):
    c = w["client"]
    holdings.save("u-pro", [{"symbol": "TCS", "exchange": "NSE", "name": "TCS", "qty": 5.0, "avg": 3000.0},
                            {"symbol": "AAPL", "exchange": "US", "name": "Apple", "market": "US", "currency": "USD", "qty": 3.0, "avg": 150.0}], "Manual")
    got = c.get("/holdings", headers=PRO).json()
    assert "us_prices_at" in got and "prices_at" in got


# ---------- Mutual funds ----------
def test_live1b_064_a_category_keeps_no_stray_hyphen():
    from app import money_mf
    assert money_mf.broad_of("Equity Scheme - ELSS- Tax Saver Fund", "equity") == ("Equity", "ELSS Tax Saver Fund")
    assert money_mf.broad_of("Equity Scheme - Flexi Cap Fund", "equity") == ("Equity", "Flexi Cap Fund")
    assert money_mf.broad_of("Debt Scheme - Short Duration Fund", "debt") == ("Debt", "Short Duration Fund")
    assert money_mf.broad_of("Other Scheme - Index Funds", "equity") == ("Equity", "Index funds")


# ---------- Net worth ----------
@pytest.fixture
def nw_w(monkeypatch):
    """The page is read on Monday 5 October 2026, 10:30 IST (as tests/test_money_networth.py reads it)."""
    import time_machine
    from tests import fake_prices
    day = datetime(2026, 10, 5, 5, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(fake_prices, "FROZEN", day)
    with time_machine.travel(day, tick=True):
        built = world.build(monkeypatch)
        main._nw_prices.clear()
        yield built
        main._nw_prices.clear()
        built["close"]()


def test_live1b_023_the_total_is_the_sum_of_the_rows_as_shown(nw_w):
    c = nw_w["client"]
    for v in (1000.4, 2000.4, 3000.4):
        r = c.post("/money/net-worth/items", headers=PRO, json={"kind": "cash", "value": v})
        assert r.status_code == 200, r.text
    got = c.get("/money/net-worth", headers=PRO).json()
    shown = sum(round(r["value"]) for r in got["assets"])
    assert shown == 6000 and got["totals"]["assets"] == 6000 and got["totals"]["net"] == 6000       # not 6001 over rows that add to 6000
    assert got["allocation"][0]["value"] == 6000


def test_live1b_063_todays_snapshot_follows_the_page_when_my_holdings_move(nw_w):
    c = nw_w["client"]
    assert c.post("/money/net-worth/items", headers=PRO, json={"kind": "cash", "value": 50000}).status_code == 200
    first = c.get("/money/net-worth", headers=PRO).json()
    assert first["history"][-1]["net"] == first["totals"]["net"] == 50000
    # My Holdings change after the entry did: the headline moves, and today's snapshot with it
    holdings.save("u-pro", [{"symbol": "RELIANCE", "exchange": "NSE", "name": "Reliance", "qty": 10.0, "avg": 2400.0}], "Manual")
    second = c.get("/money/net-worth", headers=PRO).json()
    assert second["totals"]["net"] > 50000
    assert second["history"][-1]["net"] == second["totals"]["net"] and second["history"][-1]["d"] == first["history"][-1]["d"]
    assert len(second["history"]) == len(first["history"])                                      # the same day's snapshot, not a new one
    # a snapshot of an earlier day is that day's fact
    from app import money_networth as nw
    nw.record("u-pro", {"net": 1.0, "assets": 1.0, "liabilities": 0.0}, "month", datetime(2026, 9, 1).date())
    third = c.get("/money/net-worth", headers=PRO).json()
    assert [h["net"] for h in third["history"] if h["d"] == "2026-09-01"] == [1.0]



# ---------- Tax tools and the tax report ----------
def test_live1b_034_the_dividends_page_waits_only_a_few_seconds_for_company_histories(w, monkeypatch):
    from app import money_routes
    seen = {}
    monkeypatch.setattr(main, "_corp_histories", lambda uid, syms, today, sync=8, wait=12.0: seen.setdefault("wait", wait) or 0)
    holdings.save("u-pro", [{"symbol": "TCS", "exchange": "NSE", "name": "TCS", "qty": 5.0, "avg": 3000.0}], "Manual")
    assert w["client"].get("/money/dividends", headers=PRO).status_code == 200
    assert seen["wait"] == money_routes.DIVIDEND_WAIT <= 6.0


def test_live1b_029_dividends_left_out_of_the_total_are_said_beside_it(w, monkeypatch):
    from app import money_routes
    c = w["client"]
    monkeypatch.setattr(money_routes, "dividend_parts", lambda uid, fetch=True: (
        {"rows": [], "files": [], "include": {}, "updated_at": None},
        [{"d": "2025-06-10", "sym": "INFY", "qty": 100.0, "ps": 18.0, "amount": 1800.0, "cur": "INR", "src": "estimated", "label": "Dividend", "ex": "2025-06-10", "country": "IN"}],
        [], None))
    got = money_routes.dividends_split({"id": "u-pro"})
    assert got[0] == {} and got[1].get(2025) == 1800.0                    # estimated: left out until included, and said
    assert c.post("/tax/import", headers=PRO, json={"filename": "t.csv", "data": base64.b64encode(
        b"Date,Symbol,ISIN,Type,Quantity,Price\n2025-05-02,INFY,INE009A01021,BUY,10,1500\n2025-11-03,INFY,INE009A01021,SELL,10,1400\n").decode(), "mode": "replace"}).status_code == 200
    rep = c.get("/tax", headers=PRO).json()
    y = next(x for x in rep["years"] if x["fy"] == 2025)
    assert y["dividends_left_out"] == 1800.0


def test_live1b_039_a_return_not_needed_says_when_dividends_are_not_in_it(w, monkeypatch):
    from app import money_routes
    c = w["client"]
    monkeypatch.setattr(money_routes, "dividend_parts", lambda uid, fetch=True: (
        {"rows": [], "files": [], "include": {}, "updated_at": None},
        [{"d": "2025-06-10", "sym": "INFY", "qty": 100.0, "ps": 18.0, "amount": 1800.0, "cur": "INR", "src": "estimated", "label": "Dividend", "ex": "2025-06-10", "country": "IN"}],
        [], None))
    assert c.post("/tax/import", headers=PRO, json={"filename": "t.csv", "data": base64.b64encode(
        b"Date,Symbol,ISIN,Type,Quantity,Price\n2025-05-02,INFY,INE009A01021,BUY,10,1500\n2025-11-03,INFY,INE009A01021,SELL,10,1400\n").decode(), "mode": "replace"}).status_code == 200
    got = c.get("/money/itr?fy=2025", headers=PRO).json()
    by = {s["label"]: s["value"] for s in got["summary"]}
    # (LIVE1C: the dividends are left out of the total here, so the line says so beside the figure)
    assert by["Dividends in the year (India), not in the total tax estimate below"] == "₹1,800"
    # within the basic exemption: the answer names what it leaves out
    assert "dividends of ₹1,800 are not counted in it" in by["Return needed"]


# ---------- US stocks tax ----------
def test_live1b_060_a_made_up_us_ticker_is_refused_under_its_box(w, monkeypatch):
    c = w["client"]
    monkeypatch.setattr(main, "_sec_companies", lambda: [{"symbol": "AAPL", "name": "Apple Inc.", "cik": 320193}])
    main.suggester.clear()
    # the fake price feed prices any ticker: only the list of US companies decides here
    monkeypatch.setattr(main, "_us_find", lambda sym: main.suggester.find(sym, "US"))
    bad = c.post("/money/us-tax/trades", headers=PRO, json={"d": "2024-01-05", "side": "S", "sym": "ZZZZ", "qty": 1, "price": 100, "fees": 0})
    assert bad.status_code == 422, bad.text
    d = bad.json()["detail"]
    assert d["fields"]["sym"] == "No US-listed company has the ticker ZZZZ. Check the spelling." and d["code"] == "unknown_ticker"
    ok = c.post("/money/us-tax/trades", headers=PRO, json={"d": "2024-01-05", "side": "B", "sym": "AAPL", "qty": 1, "price": 100, "fees": 0})
    assert ok.status_code == 200, ok.text
    assert [t["sym"] for t in ok.json()["trades"]] == ["AAPL"]                  # the refused one was not kept


# ---------- Blog ----------
def test_live1b_082_the_blogs_lists_are_kept_by_the_cache_for_minutes_not_a_day(w):
    c = w["client"]
    for path in ("/blog", "/blog/briefs", "/blog/research"):
        r = c.get(path)
        assert r.status_code == 200, path
        cc = r.headers["cache-control"]
        assert "s-maxage=600" in cc and "s-maxage=86400" not in cc, f"{path}: {cc}"


# ---------- Public company pages ----------
def test_live1b_074_an_exchange_low_set_before_the_pages_year_is_not_taken_in():
    from app import stock_pages
    report = {"day": "2026-10-27", "rows": {"SBIN": [1_100.0, "2026-06-02", 906.0, "2025-10-27"]}}
    page = {"region": "IN", "symbol": "SBIN", "price_at": "2026-10-28", "high52": 1_090.0, "low52": 917.7}
    got = stock_pages.with_week52_report(page, report, "SBIN")
    assert got["low52"] == 917.7 and got["high52"] == 1_100.0                  # the 27 Oct 2025 low is outside the year to 28 Oct 2026; the June high is inside
    inside = {**page, "price_at": "2026-10-26"}                                 # the year to 26 Oct 2026 starts after 26 Oct 2025: 27 Oct 2025 is in it
    assert stock_pages.with_week52_report(inside, report, "SBIN")["low52"] == 906.0
    held = {"day": "2026-10-27", "rows": {"SBIN": [1_100.0, "2026-06-02", 906.0, "2025-11-03"]}}
    assert stock_pages.with_week52_report(page, held, "SBIN")["low52"] == 906.0
