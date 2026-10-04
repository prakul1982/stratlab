"""Company suggestions while a symbol is typed (the ranking, BSE-only codes, US common shares only, the stored list
when the full one is down) and US stocks in My Holdings: valued in dollars, counted in rupees at the day's rate, and
left out of what only Indian stocks have (filings, corporate actions, the tax report, the My Stocks newsletter)."""
import json

import pytest

from app import db, holdings, main, pricing, suggest
from tests import world

PRO = world.headers("pro-token")


def _rows(pairs, market="IN"):
    return [suggest._entry(s, n, "NSE" if market == "IN" else "US", market) for s, n in pairs]


INDIA = _rows([("RELIANCE", "Reliance Industries Ltd"), ("RECLTD", "REC Limited"), ("REDINGTON", "Redington Limited"),
               ("RE", "Re Sustainability"), ("RELAXO", "Relaxo Footwears"), ("TATAPOWER", "Tata Power Renewable Energy"),
               ("ABREL", "Aditya Birla Real Estate"), ("INFY", "Infosys Limited")]) + \
        [suggest._entry("TINYCO", "Tiny Co", "BSE", "IN", code="543210", ident="543210")]


# ---------- ranking ----------
def test_exact_symbol_first_then_symbol_prefix_then_names():
    # the exact symbol; symbols starting with it, shorter first; then names with a word starting with it
    assert [r["symbol"] for r in suggest.rank("re", INDIA)] == ["RE", "RECLTD", "RELAXO", "RELIANCE", "REDINGTON", "ABREL", "TATAPOWER"]
    # a name starting with it comes before a name with a later word starting with it
    assert [r["symbol"] for r in suggest.rank("red", INDIA)] == ["REDINGTON"]
    assert [r["symbol"] for r in suggest.rank("rec", INDIA)] == ["RECLTD"]
    assert [r["symbol"] for r in suggest.rank("relia", INDIA)] == ["RELIANCE"]


def test_name_word_prefix_and_several_words():
    assert [r["symbol"] for r in suggest.rank("renew", INDIA)] == ["TATAPOWER"]
    assert [r["symbol"] for r in suggest.rank("aditya real", INDIA)] == ["ABREL"]
    assert [r["symbol"] for r in suggest.rank("reliance ind", INDIA)] == ["RELIANCE"]
    assert suggest.rank("", INDIA) == [] and suggest.rank("zzz", INDIA) == []


def test_bse_only_company_by_code_fills_the_code():
    got = suggest.rank("543210", INDIA)
    assert got == [{"symbol": "TINYCO", "id": "543210", "name": "Tiny Co", "exchange": "BSE", "market": "IN"}]
    assert suggest.rank("tiny", INDIA)[0]["id"] == "543210"


def test_at_most_eight():
    many = _rows([(f"RE{i:02d}", f"Re company {i}") for i in range(30)])
    assert len(suggest.rank("re", many)) == 8


def test_us_common_shares_only():
    listed = {"ACON", "ACONW", "ALFU", "ALFUU", "BRK-B", "BAC-PL", "XYZ-WT", "AAPL"}
    keep = {t for t in listed if suggest.us_common(t, listed)}
    assert keep == {"ACON", "ALFU", "BRK-B", "AAPL"}
    rows = suggest.us_rows([{"symbol": t, "name": t} for t in sorted(listed)])
    assert {r["symbol"] for r in rows} == keep and all(r["market"] == "US" and r["exchange"] == "US" for r in rows)


def test_india_rows_from_the_broker_list():
    eq = [{"symbol": "RELIANCE", "name": "RELIANCE INDUSTRIES", "exchange": "NSE"},
          {"symbol": "SLOWCO-BE", "name": "SLOW CO", "exchange": "NSE"},
          {"symbol": "TINYCO", "name": "TINY CO", "exchange": "BSE", "bse_code": "543210"}]
    rows = {r["symbol"]: r for r in map(suggest.shown, suggest.india_rows(eq))}
    assert rows["SLOWCO"]["id"] == "SLOWCO" and rows["TINYCO"]["id"] == "543210" and rows["TINYCO"]["exchange"] == "BSE"


def test_stored_list_when_the_full_one_is_down():
    def down():
        raise RuntimeError("offline")
    s = suggest.Suggester({"IN": down, "US": lambda: []},
                          {"IN": lambda: {"RELIANCE": {"name": "Reliance Industries", "bse": None},
                                          "TINYCO": {"name": "Tiny Co", "bse": "543210"}},
                           "US": lambda: {"AAPL": {"name": "Apple Inc."}, "BAC-PL": {"name": "Bank of America pref"}}})
    assert [r["id"] for r in s.search("rel", "IN")] == ["RELIANCE"]
    assert [r["id"] for r in s.search("tiny", "IN")] == ["543210"]
    assert [r["symbol"] for r in s.search("ba", "US")] == []
    assert s.find("aapl", "US")["name"] == "Apple Inc."
    both = s.search("a", None)
    assert both and both[0]["symbol"] == "AAPL"


# ---------- the endpoint ----------
@pytest.fixture
def w(monkeypatch):
    built = world.build(monkeypatch)
    main.suggester.clear()
    yield built
    main.suggester.clear()
    built["close"]()


def test_endpoint_suggests_while_typing(w):
    c = w["client"]
    r = c.get("/suggest/companies?q=re&market=IN", headers=PRO)
    assert r.status_code == 200
    rows = r.json()["rows"]
    assert rows and rows[0]["symbol"].startswith("RE") and len(rows) <= 8
    assert any(x["symbol"] == "RELIANCE" for x in rows) and all(x["market"] == "IN" for x in rows)
    us = c.get("/suggest/companies?q=aap&market=US", headers=PRO).json()["rows"]
    assert us[0] == {"symbol": "AAPL", "id": "AAPL", "name": "Apple Inc.", "exchange": "US", "market": "US"}
    assert c.get("/suggest/companies?q=", headers=PRO).json()["rows"] == []
    assert c.get("/suggest/companies?q=re").status_code == 401


# ---------- US holdings ----------
def _rate(rate=85.0):
    db.set_setting(pricing.RATES, json.dumps({"at": "2026-10-04T00:00:00+00:00", "rates": {"USD": rate}}))
    pricing._rates_cache[0] = 0.0


def test_us_view_math():
    v = holdings.view([{"symbol": "RELIANCE", "qty": 10, "avg": 100, "sector": "Energy"},
                       {"symbol": "AAPL", "qty": 2, "avg": 150, "sector": "Technology", "market": "US", "exchange": "US"}],
                      {"RELIANCE": {"price": 120, "change": 1}}, {"AAPL": {"price": 200, "change": 2, "change_pct": 1.0}}, 80.0)
    rows = {r["symbol"]: r for r in v["rows"]}
    assert rows["AAPL"]["currency"] == "USD" and rows["AAPL"]["value"] == 400 and rows["AAPL"]["pnl"] == 100
    assert rows["RELIANCE"]["currency"] == "INR" and rows["RELIANCE"]["market"] == "IN"
    t = v["totals"]
    assert t["value"] == 1200 + 400 * 80 and t["pnl"] == 200 + 100 * 80 and t["day"] == 10 + 4 * 80 and t["count"] == 2
    assert v["us"]["value"] == 400 and v["us"]["pnl"] == 100 and v["us"]["in_total"] is True and v["usd_inr"] == 80
    assert rows["AAPL"]["weight"] == round(32000 / 33200 * 100, 1)
    # no exchange rate: the US stock is shown in dollars and left out of the rupee totals
    v = holdings.view([{"symbol": "RELIANCE", "qty": 10, "avg": 100}, {"symbol": "AAPL", "qty": 2, "avg": 150, "market": "US"}],
                      {"RELIANCE": {"price": 120}}, {"AAPL": {"price": 200}}, None)
    assert v["totals"]["value"] == 1200 and v["us"]["value"] == 400 and v["us"]["in_total"] is False
    assert {r["symbol"]: r["weight"] for r in v["rows"]}["AAPL"] is None
    assert holdings.view([{"symbol": "A", "qty": 1, "avg": 1}], {})["us"] is None


def test_add_a_us_stock_by_hand(w, monkeypatch):
    c = w["client"]
    _rate(85.0)
    r = c.put("/holdings", headers=PRO, json={"items": [{"symbol": "RELIANCE", "qty": 10, "avg": 2400},
                                                        {"symbol": "aapl", "qty": 3, "avg": 150, "market": "US"}]})
    assert r.status_code == 200 and r.json()["unmatched"] == []
    v = r.json()["holdings"]
    aapl = next(x for x in v["rows"] if x["symbol"] == "AAPL")
    q = main.research_hub.quotes("US", ["AAPL"])["AAPL"]
    assert aapl["market"] == "US" and aapl["currency"] == "USD" and aapl["name"] == "Apple Inc." and aapl["exchange"] == "US"
    assert aapl["price"] == round(q["price"], 2) and aapl["value"] == round(3 * q["price"], 2)
    assert v["usd_inr"] == 85 and v["us"]["count"] == 1 and v["us"]["in_total"] is True
    rel = next(x for x in v["rows"] if x["symbol"] == "RELIANCE")
    assert abs(v["totals"]["value"] - (rel["value"] + aapl["value"] * 85)) < 0.1
    # kept when saved again (and an Indian stock with the same symbol is a different holding)
    r = c.put("/holdings", headers=PRO, json={"items": [{"symbol": "RELIANCE", "qty": 10, "avg": 2400},
                                                        {"symbol": "AAPL", "qty": 5, "avg": 150, "market": "US"}]})
    assert next(x for x in r.json()["holdings"]["rows"] if x["symbol"] == "AAPL")["qty"] == 5
    # a ticker no US company has (and no price for it) is sent back
    monkeypatch.setattr(main.research_hub, "quotes", lambda region, syms: {s: None for s in syms})
    r = c.put("/holdings", headers=PRO, json={"items": [{"symbol": "ZZZZQ", "qty": 1, "market": "US"}]})
    assert r.json()["unmatched"][0]["reason"] == "No US-listed company has that ticker."


def test_us_stocks_stay_out_of_what_covers_indian_stocks(w):
    c = w["client"]
    _rate()
    c.put("/holdings", headers=PRO, json={"items": [{"symbol": "RELIANCE", "qty": 10, "avg": 2400},
                                                    {"symbol": "AAPL", "qty": 3, "avg": 150, "market": "US"}]})
    assert {i["symbol"] for i in holdings.load("u-pro")["items"]} == {"RELIANCE", "AAPL"}
    facts = c.get("/holdings/facts", headers=PRO).json()
    assert "AAPL" not in facts["rows"] and "RELIANCE" in facts["rows"]
    ca = c.get("/holdings/corp-actions", headers=PRO)
    assert ca.status_code == 200 and "AAPL" not in json.dumps(ca.json())
    assert c.get("/tax", headers=PRO).status_code == 200
    assert [i["symbol"] for i in main.tax_inputs({"id": "u-pro"})["items"]] == ["RELIANCE"]
    assert holdings.symbols("u-pro") == ["RELIANCE"]


def test_without_us_prices_a_us_stock_counts_at_cost(w, monkeypatch):
    c = w["client"]
    _rate(80.0)
    monkeypatch.setattr(main.research_hub, "quotes", lambda region, syms: {s: None for s in syms})
    monkeypatch.setattr(main, "_us_find", lambda s: {"symbol": s, "name": "Apple Inc."})
    v = c.put("/holdings", headers=PRO, json={"items": [{"symbol": "AAPL", "qty": 2, "avg": 100, "market": "US"}]}).json()["holdings"]
    assert v["rows"][0]["price"] is None and v["totals"]["value"] == 200 * 80 and v["us_prices"] is False
