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
