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


# ---------- R5O-005: an ETF's gap is one day's close against that day's NAV ----------
def test_etf_gap_through_the_day_is_the_last_close_against_its_nav(monkeypatch):
    from app import etf_nav as E
    # 8 Oct 14:25 IST, Nifty -1.7%: NIFTYBEES 254.15 against the 7 Oct NAV 257.8026 read "1.4% below"
    live = {"name": "Nifty 50", "isin": "INF204KB14I2", "price": 254.15, "inav": None, "underlying": "Nifty 50",
            "nav": 257.8026, "nav_date": "2026-10-07"}
    no_file = {"schemes": {}, "isin": {}}
    monkeypatch.setattr(E, "_days", lambda: {})
    v = E.row_view("NIFTYBEES", live, no_file, "2026-10-08T14:25+05:30")
    assert v["gap"] is None and v["basis"] is None and v["nav_waiting"] is True       # not -1.42: that's the day's move
    # 7 Oct's close stored after that day's close: the gap is of 7 Oct, and the words say so
    monkeypatch.setattr(E, "_days", lambda: {"2026-10-07": {"NIFTYBEES": [257.60, 257.8026]}})
    v = E.row_view("NIFTYBEES", live, no_file, "2026-10-08T14:25+05:30")
    assert (v["gap"], v["nav_price"], v["nav_price_day"]) == (-0.08, 257.60, "2026-10-07")
    assert v["text"] == "NIFTYBEES closed 0.08% below its NAV on 7 Oct"
    # in the evening, with the 8 Oct NAV out, the 8 Oct price stands against it
    tonight = {**live, "nav": 254.30, "nav_date": "2026-10-08"}
    v = E.row_view("NIFTYBEES", tonight, no_file, "2026-10-08T15:30+05:30")
    assert v["gap"] == E.gap(254.15, 254.30) and v["text"] == "NIFTYBEES trades 0.06% below its last NAV"
    # the alert never fires on the day's move either
    monkeypatch.setattr(E, "load_live", lambda: {"read": None, "as_of": "2026-10-08T14:25+05:30", "rows": {"NIFTYBEES": live}})
    monkeypatch.setattr(E, "navs", lambda: no_file)
    assert E.gap_now("NIFTYBEES", 254.15) is None
    assert "the day's market move is never read as a gap" in E.NOTE


# ---------- R5O-006: one listing per US symbol ----------
ENI_PROFILE = {"name": "Eni SpA", "exchange": "AIM ITALIA - MERCATO ALTERNATIVO DEL CAPITALE", "currency": "EUR",
               "marketCapitalization": 70600.0, "country": "IT"}
ENI_ADR = {"symbol": "E", "currency": "USD", "exchange": "NYSE", "price": 53.96, "high52": 55.10, "low52": 31.20}
ENI_METRICS = {"52WeekLow": 14.54, "52WeekHigh": 25.02, "epsTTM": 1.75}      # Milan's euros


def test_an_adr_page_is_its_us_listing_in_dollars():
    from app.intel.company import us_listing
    one = us_listing(ENI_PROFILE, ENI_ADR, ENI_METRICS, fx=lambda a, b: 1.17 if (a, b) == ("EUR", "USD") else None)
    assert (one["exchange"], one["currency"], one["reporting_currency"], one["foreign"]) == ("NYSE", "USD", "EUR", True)
    assert one["range52"] == {"low": 31.20, "high": 55.10}             # the ADR's own range: 53.96 sits inside it
    assert one["market_cap"] == 70600.0 * 1e6 * 1.17                   # in dollars, at the day's rate
    # no rate: no market value, rather than euros labelled as dollars
    assert us_listing(ENI_PROFILE, ENI_ADR, ENI_METRICS, fx=lambda a, b: None)["market_cap"] is None
    # an ordinary US company is unchanged
    nvda = us_listing({"exchange": "NASDAQ NMS - GLOBAL MARKET", "currency": "USD", "marketCapitalization": 4312000.5},
                      {"currency": "USD", "exchange": "NasdaqGS", "high52": 1, "low52": 1}, {"52WeekLow": 86.6, "52WeekHigh": 195.6})
    assert (nvda["exchange"], nvda["currency"], nvda["foreign"], nvda["range52"]) == ("NASDAQ NMS - GLOBAL MARKET", "USD", False, {"low": 86.6, "high": 195.6})
    assert nvda["market_cap"] == 4312000.5e6
    # its "similar companies" were ENI.MI and GSP.MI, Milan's euro prices shown with a dollar sign: US listings only
    from app.intel.company import FOREIGN_TICKER
    assert [x for x in ("ENI.MI", "GSP.MI", "BRK.B", "XOM", "SHEL.L", "BP") if not FOREIGN_TICKER.search(x)] == ["BRK.B", "XOM", "BP"]


# ---------- R5O-007: AAPL's page ----------
def test_insider_net_is_the_sum_of_the_rows_shown():
    from app.intel.company import insider_view
    # AAPL, 8 Oct: the 8 visible rows all sold (-1,39,005 in total) while the header said "Net +2,08,772" over 40
    sold = [-108136, -4000, -6500, -3200, -2900, -5000, -4269, -5000]
    later = [{"name": "Grant", "change": 120000, "filingDate": "2026-04-01"}] * 32         # older awards, not shown
    ins = [{"name": f"Officer {i}", "change": c, "filingDate": f"2026-09-{20 - i:02d}"} for i, c in enumerate(sold)] + later
    v = insider_view(ins)
    assert v["count"] == 8 and len(v["rows"]) == 8 and v["net"] == sum(sold) == -139005
    assert insider_view([]) is None and insider_view([{"name": "x", "change": 0}]) is None


def test_the_ai_read_carries_no_revenue_split():
    from app.intel import ai as A
    # a stored read with the model's split ("iPhone 100%, Services 0%, Mac 0%") goes out without it
    stored = {"summary": "Apple makes phones.", "segments": [{"label": "iPhone", "share": 100}, {"label": "Services", "share": 0}]}
    assert A.clean_company(stored)["segments"] == []
    import inspect
    assert '"segments"' not in inspect.getsource(A.company).split("RULES")[0]          # the model isn't asked for one
