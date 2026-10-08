"""Round 5, the owner's review on the live site (8 Oct 2026): each test is built on the real example the reviewer saw."""
import json

from app import db, investor
from tests.test_deepdive import api  # noqa: F401  (a fixture)


# ---------- R5O-003: the watchlist's two tabs read one price, with its time ----------
def test_at_a_glance_takes_the_list_tabs_quote_not_a_cached_candle():
    # 8 Oct 15:01 IST: the cached daily candle said TCS 2,106.70 +1.3%; the List tab's quote said 2,061.30 -0.91%
    trend = {"price": 2106.70, "chg": 1.27, "stage": 4, "t": "2026-10-08T00:00:00+05:30"}
    quote = {"price": 2061.30, "change_pct": -0.91, "at": "2026-10-08T15:01:12+05:30"}
    got = investor.price_of(quote, trend)
    assert got == {"price": 2061.30, "chg": -0.91, "price_at": "2026-10-08T15:01:12+05:30"}
    # no quote: the candle stands in, dated by its day only (never passed off as the price of the moment)
    assert investor.price_of(None, trend) == {"price": 2106.70, "chg": 1.27, "price_at": "2026-10-08"}
    assert investor.price_of({"price": None}, None) == {"price": None, "chg": None, "price_at": None}


def test_investor_endpoint_uses_the_quotes_call(api, monkeypatch):  # noqa: F811
    from app import main
    c, who, _calls, _usage = api
    who["p"] = {"id": "u1", "plan": "pro", "_plan": "pro"}
    db.set_setting("watchlist:u1", json.dumps({"items": [{"region": "IN", "symbol": "ACME"}]}))
    asked = []

    def quotes(region, syms):
        asked.append((region, list(syms)))
        return {"ACME": {"price": 2061.30, "change_pct": -0.91, "at": "2026-10-08T15:01:00+05:30"}}
    monkeypatch.setattr(main.research_hub, "quotes", quotes)
    monkeypatch.setattr(main, "price_trend", lambda s, m="IN": {"price": 2106.70, "chg": 1.3, "stage": 2, "st_up": True, "t": "2026-10-08"})
    row = c.get("/research/investor").json()["rows"][0]
    assert asked == [("IN", ["ACME"])]
    assert (row["price"], row["chg"], row["price_at"]) == (2061.30, -0.91, "2026-10-08T15:01:00+05:30") and row["stage"] == 2


# ---------- R5O-004: holdings with a US stock ----------
def test_holdings_totals_add_up_with_a_us_stock_without_a_buy_price():
    from app import holdings
    # the owner's test: RELIANCE 10 @ 1,250, TCS 5 @ 3,000, INFY 20 @ 1,800, AAPL 3 with no buy price; 8 Oct, 14:27 IST
    items = [{"symbol": "RELIANCE", "qty": 10, "avg": 1250, "sector": "Energy"},
             {"symbol": "TCS", "qty": 5, "avg": 3000, "sector": "Information Technology"},
             {"symbol": "INFY", "qty": 20, "avg": 1800, "sector": "Information Technology"},
             {"symbol": "AAPL", "qty": 3, "avg": None, "sector": "Technology", "market": "US", "exchange": "US"}]
    at = "2026-10-08T14:27:00+05:30"
    quotes = {"RELIANCE": {"price": 1177.10, "change": -10.0, "at": at}, "TCS": {"price": 2076.00, "change": -4.30, "at": at},
              "INFY": {"price": 999.40, "change": 2.0, "at": at}}
    # AAPL's +0.91% is from the 7 Oct US session (it closed at 01:30 IST on 8 Oct)
    us = {"AAPL": {"price": 336.67, "change": 3.04, "change_pct": 0.91, "at": "2026-10-07T20:00:00+00:00"}}
    v = holdings.view(items, quotes, us, 96.77)
    t = v["totals"]
    assert t["value"] == round(11771 + 10380 + 19988, 2) and t["invested"] == 63500
    assert round(t["value"] - t["invested"], 2) == t["pnl"]                       # was 1,39,858 - 63,500 against -21,381
    assert t["no_cost"]["symbols"] == ["AAPL"] and t["no_cost"]["value"] == round(3 * 336.67 * 96.77, 2)
    # the day's change is India's session
    assert t["session"] == "2026-10-08" and t["other_session"] == []               # AAPL is out of the totals anyway
    assert t["day"] == round(-100 - 21.5 + 40, 2)
    # one sector for both technology labels
    assert [a["sector"] for a in v["allocation"]].count("Information Technology") == 1
    assert next(a for a in v["allocation"] if a["sector"] == "Information Technology")["count"] == 3
    # with a buy price, AAPL joins the totals at the one stated rate, but its last-session move still isn't "today"
    items[3]["avg"] = 300
    v = holdings.view(items, quotes, us, 96.77)
    t = v["totals"]
    assert t["invested"] == round(63500 + 900 * 96.77, 2) and round(t["value"] - t["invested"], 2) == t["pnl"]
    assert t["other_session"] == ["AAPL"] and t["day"] == round(-100 - 21.5 + 40, 2) and v["usd_inr"] == 96.77
    # in the evening the US session of the same day counts
    us["AAPL"]["at"] = "2026-10-08T15:00:00+00:00"                                 # 11:00 ET on 8 Oct
    t = holdings.view(items, quotes, us, 96.77)["totals"]
    assert t["other_session"] == [] and t["day"] == round(-100 - 21.5 + 40 + 3 * 3.04 * 96.77, 2)
    assert holdings.us_sector("XLK") == "Information Technology"
