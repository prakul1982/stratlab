"""Round 5, the owner's review on the live site (8 Oct 2026): each test is built on the real example the reviewer saw."""
import json
import socket
import threading

import httpx
import pytest

from app import main  # noqa: F401, I001  (first: the app loads the newsletter job before the modules built on it)
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


def test_net_worth_states_the_dollar_rate_its_us_stocks_are_at():
    from app import money_networth as N
    stocks = {"in": 42139.0, "us": 3 * 336.67 * 96.77, "as_of": "2026-10-08T14:27:00+05:30", "count": 4, "usd_inr": 96.77}
    v = N.build([], stocks, None, N.Prices())
    us = next(a for a in v["assets"] if a["kind"] == "stocks_us")
    assert us["rule"] == "From My Holdings, at today's prices in rupees, at ₹96.77 a dollar"


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


def test_an_adrs_yearly_results_are_in_the_currency_they_are_reported_in():
    from app.intel.company import Research
    # Eni files its annual report in euros: the sales and profit charts say EUR, not the ADR's USD
    rep = {"data": [{"year": y, "report": {"ic": [{"label": "Total revenue", "value": v}, {"label": "Net income", "value": v / 20}]}}
                    for y, v in ((2023, 93.7e9), (2024, 88.8e9))]}
    assert Research._us_trend(rep, "EUR")["unit"] == "EUR"
    assert Research._us_trend(rep)["unit"] == "USD"


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


# ---------- R5O-009: the red-flag rules, on the filings the owner saw ----------
import pytest  # noqa: E402

from app.intel import filings as F  # noqa: E402


@pytest.mark.parametrize("desc,text,cat,sev", [
    # RELIANCE, 5 Sep 2026: a dissolved step-down subsidiary, certified by Cyprus's Department of Insolvency
    ("Other Restructuring", "Roptonal Limited, a step-down subsidiary of the Company, stands dissolved with effect from September 4, 2026, "
     "pursuant to the certificate issued by the Department of Insolvency, Republic of Cyprus.", "subsidiary_closed", "info"),
    ("Updates", "XYZ Limited, a wholly owned subsidiary, has been struck off from the register of companies", "subsidiary_closed", "info"),
    # the company's own insolvency is still a red flag
    ("Insolvency and Bankruptcy", "The NCLT has admitted the application under Section 7 of the IBC and initiated the corporate insolvency resolution process",
     "insolvency", "red"),
    # routine NCD allotments and servicing
    ("Allotment of Non-Convertible Debentures", "The Company has allotted 50,000 secured NCDs of Rs 1,00,000 each on private placement basis", "debt_routine", "info"),
    ("Record Date", "Record date for payment of interest on NCDs", "debt_routine", "info"),
    # UGROCAP: its NCDs' trading suspended for a record date, which was read as a debt raise
    ("Suspension of Trading", "Suspension of trading in Non-Convertible Debentures on account of record date for redemption", "debt_routine", "info"),
    ("Suspension of Trading", "Trading in the equity shares of the Company is suspended with effect from 12 October 2026 for non-compliance",
     "suspension", "red"),
    # a new borrowing plan stays worth a look
    ("Board Meeting Outcome", "The Board approved the issue of non-convertible debentures up to Rs 500 crore", "ncd", "amber"),
    # resignations: directors and key officers stay; senior management and terms that ended are routine
    ("Resignation of Director/KMP/SMP", "Resignation of Mr. A Kumar, Senior Manager - Sales (Senior Management Personnel)", "officer_change", "info"),
    ("Resignation of Director/KMP/SMP", "Resignation of Ms. B Rao as Chief Financial Officer and Key Managerial Personnel", "kmp_resign", "amber"),
    ("Change in Directorate", "Cessation of Mr. C Shah as Independent Director on completion of his second term", "officer_change", "info"),
    ("Change in Directorate", "Resignation of Mr X as Independent Director", "kmp_resign", "amber"),
    ("Resignation of Director/KMP/SMP", "", "kmp_resign", "amber"),                 # nothing says who: kept
])
def test_red_flag_rules_on_real_filings(desc, text, cat, sev):
    assert F.classify(desc, text) == (cat, sev)


def test_the_same_filing_listed_again_shows_once():
    def nse(seq, when, text="Resignation of Mr. D Jain as Company Secretary and Compliance Officer"):
        return {"symbol": "KSHITIJPOL", "sm_name": "Kshitij Polyline Limited", "desc": "Resignation of Director/KMP/SMP", "attchmntText": text,
                "sort_date": when, "seq_id": seq, "attchmntFile": "https://nsearchives.nseindia.com/c/x.pdf"}
    rows = F.flagged_rows([nse("1", "2026-10-07 11:02:00"), nse("2", "2026-10-07 11:40:00"), nse("3", "2026-10-07 16:05:00"),
                           nse("4", "2026-10-07 16:10:00", "Resignation of Mr. E Patel as Whole-time Director")])
    assert len(rows) == 2                                           # KSHITIJPOL: the one secretary's filing three times, and another
    one = next(r for r in rows if "Secretary" in r["text"])
    assert one["copies"] == 3 and one["at"] == "2026-10-07T16:05"


def test_stored_rows_are_read_with_todays_rules_and_once(monkeypatch):
    from app import redflags as R
    rows = [
        {"id": "a", "symbol": "RELIANCE", "company": "Reliance", "at": "2026-09-05T18:00", "category": "insolvency", "label": "Insolvency proceedings",
         "severity": "red", "subject": "Other Restructuring", "text": "Roptonal Limited, a step-down subsidiary, stands dissolved; certificate from the Department of Insolvency, Republic of Cyprus", "url": None},
        {"id": "b", "symbol": "OLAELEC", "company": "Ola Electric", "at": "2026-10-01T10:00", "category": "rights", "label": "Rights issue (fund raise)",
         "severity": "red", "subject": "Rights Issue", "url": None},
        {"id": "c", "symbol": "OLAELEC", "company": "Ola Electric", "at": "2026-10-01T12:30", "category": "rights", "label": "Rights issue (fund raise)",
         "severity": "red", "subject": "Rights Issue", "url": None},
    ]
    got = R.current("IN", rows)
    assert [(i["symbol"], i.get("copies", 1)) for i in got] == [("OLAELEC", 2)]


def test_a_rules_change_reads_the_last_90_days_again(monkeypatch):
    from datetime import date
    from app import db, redflags as R
    store = {}
    monkeypatch.setattr(db, "get_setting", lambda k: store.get(k))
    monkeypatch.setattr(db, "set_setting", lambda k, v: store.__setitem__(k, v))
    R.forget()
    today = date(2026, 10, 8)
    old = {"id": "RELIANCE|2026-09-07T18:00|x", "symbol": "RELIANCE", "company": "Reliance", "at": "2026-09-07T18:00", "category": "insolvency",
           "label": "Insolvency proceedings", "severity": "red", "subject": "Other Restructuring", "url": None}
    R.flags.add("IN", [old])
    store[R.STATE_KEY + "IN"] = json.dumps({"through": "2026-10-07"})          # stored under the old rules
    asked = []

    class Feed:
        def market_flags(self, day):
            asked.append(day)
            return []
    runner = R.Runner(lambda: {"in": Feed()}, sleep=lambda s: None, pause=0)
    runner.run("IN", today)
    assert asked[0] <= date(2026, 7, 10) and R.flags.between("IN", date(2026, 9, 1), today) == []    # the false flag is gone
    assert R.state("IN")["rules"] == F.RULES_VERSION
    asked.clear()
    runner.run("IN", today)
    assert asked[0] == date(2026, 10, 6)                                       # then the usual two-day overlap
    R.forget()


# ---------- R5O-011: TCS's key numbers, one computation each ----------
def tcs_page():
    return {"ratios": {"Market Cap": "₹ 7,70,345 Cr.", "Current Price": "₹ 2,080", "Book Value": "₹ 296", "Face Value": "₹ 1.00",
                       "Dividend Yield": "3.13 %", "Stock P/E": "14.0"},
            "pl": {"cols": ["Mar 2024", "Mar 2025", "Mar 2026", "TTM"],
                   "rows": {"Sales +": [240893, 255324, 267021, 275859], "Net Profit +": [46099, 48797, 49454, 50055],
                            "EPS in Rs": [126.88, 134.19, 136.32, 137.64]}},
            "balance": {"cols": ["Mar 2025", "Mar 2026"], "rows": {"Equity Capital": [362, 362], "Reserves": [94394, 104766], "Borrowings": [10000, 11283]}}}


def test_net_margin_is_the_last_reported_years():
    from app.intel.screener import summary
    s = summary(tcs_page())
    assert round(s["net_margin"], 1) == 18.5                # FY26 49,454 / 2,67,021, not the TTM 18.1%


def test_market_value_counts_one_number_of_shares():
    from app.intel.screener import market_cap, summary
    # the screener's 7,70,345 cr at 2,080.30 is 370.3 crore shares; the share capital says 362 (of Rs 1)
    assert market_cap(770345, 2080.30, 362, 1.0) == round(2080.30 * 362, 2)
    assert market_cap(751000, 2076.40, 362, 1.0) == 751000            # 361.7 against 362: within 1.5%, the source's stands
    assert market_cap(751000, 2076.40, None, None) == 751000
    assert round(summary(tcs_page())["market_cap_cr"]) == round(2080 * 362)


def test_no_scraped_strengths_and_concerns():
    import inspect
    from app.intel import company
    src = inspect.getsource(company.Research._company_in)
    assert '"pros": [], "cons": []' in src
    from app.intel import ai as A
    assert "screener_pros" not in inspect.getsource(A.company_facts)


def test_dividend_yield_counts_the_special_and_says_so():
    from app.intel.company import with_dividend_yield
    c = {"quote": {"price": 2076.40}, "summary": {"div_yield": 3.1},
         "metrics": [{"title": "Valuation", "items": [{"label": "Div yield", "value": 3.1, "unit": "%"}]}]}
    divs = [{"kind": "dividend", "sub": "interim", "amount": 12, "ex_date": "2026-07-15"},
            {"kind": "dividend", "sub": "final", "amount": 31, "ex_date": "2026-05-25"},
            {"kind": "dividend", "sub": "interim", "amount": 11, "ex_date": "2026-01-16"},
            {"kind": "dividend", "sub": "special", "amount": 46, "ex_date": "2026-01-16"},
            {"kind": "dividend", "sub": "interim", "amount": 11, "ex_date": "2025-10-15"},
            {"kind": "dividend", "sub": "interim", "amount": 10, "ex_date": "2025-07-10"}]      # over a year ago
    out = with_dividend_yield(c, divs, "2026-10-08")
    item = out["metrics"][0]["items"][0]
    assert item["value"] == round(111 / 2076.40 * 100, 2) == 5.35 and out["summary"]["div_yield"] == 5.35
    assert item["note"] == "₹111 a share in the last 12 months, including a ₹46 special dividend; 3.1% without it"
    # nothing stored: the source's figure stays, saying what it is
    same = with_dividend_yield(c, [], "2026-10-08")["metrics"][0]["items"][0]
    assert same["value"] == 3.1 and same["note"] == "From the last reported year's dividends"


# ---------- R5O-012: the screener's rows, order and size bands ----------
def test_a_company_on_both_exchanges_is_one_row_the_nse_one():
    from app import screens
    rows = [{"symbol": "3BFILMS", "name": "3B Films Ltd", "market_cap": 60, "price": 14.00},
            {"symbol": "544412", "name": "3B Films Ltd", "market_cap": 57, "price": 13.33},
            {"symbol": "3CIT", "name": "3C IT Solutions & Telecoms (India) Ltd", "market_cap": 40},
            {"symbol": "544190", "name": "3C IT Solutions and Telecoms India Limited", "market_cap": 41},   # named by the twin list
            {"symbol": "540615", "name": "7NR Retail Ltd", "market_cap": 20},                                  # BSE only: kept
            {"symbol": "ACCEL", "name": "Accel Ltd", "market_cap": 100}, {"symbol": "517494", "name": "Accel Limited", "market_cap": 98}]
    kept = screens.one_per_company(rows, {"544190": "3CIT"})
    assert [r["symbol"] for r in kept] == ["3BFILMS", "3CIT", "540615", "ACCEL"]


def test_size_bands_are_ranks_as_sebi_defines_them_and_the_default_is_the_largest_first():
    from app import screens
    rows = screens.with_ranks([{"symbol": f"S{n}", "name": f"Co {n:04d}", "market_cap": 1_000_000 - n} for n in range(1, 601)])
    by = {r["symbol"]: r for r in rows}
    band = lambda s, b: screens._in_band("IN", by[s], [b])  # noqa: E731
    assert band("S100", "large") and band("S101", "mid") and band("S250", "mid") and band("S251", "small")
    assert band("S500", "small") and band("S501", "micro") and not band("S101", "large")
    assert screens.CAP_BANDS["IN"]["large"][0] == "Large (the 100 largest)"
    got = screens.run("IN", {}, index={"rows": rows, "at": None})
    assert [r["symbol"] for r in got["rows"][:3]] == ["S1", "S2", "S3"] and got["sort"] == "market_cap" and got["desc"] is True
    assert "cap_rank" not in got["rows"][0]
    from app.models import ScreenRunReq
    assert (ScreenRunReq().sort, ScreenRunReq().desc) == ("market_cap", True)


# ---------- R5O-013: NIFTY 500, Midcap 150 and Smallcap 250 had no list of stocks ----------
def test_index_members_come_from_the_archive_file_when_the_live_api_turns_us_away():
    import httpx
    from app.intel.filings import NSEFilings
    head = "Company Name,Industry,Symbol,Series,ISIN Code\n"
    files = {"/content/indices/ind_nifty500list.csv": head + "360 ONE WAM Ltd.,Financial Services,360ONE,EQ,INE466L01038\n"
             + "".join(f"Co {i} Ltd.,Industrials,CO{i},EQ,INE00000{i:04d}\n" for i in range(499))}
    asked = []

    def handler(req: httpx.Request):
        asked.append(req.url.host + req.url.path)
        if req.url.host == "nsearchives.nseindia.com" and req.url.path in files:
            return httpx.Response(200, text=files[req.url.path])
        return httpx.Response(403, text="Access Denied")               # the live site's bot check
    feed = NSEFilings(transport=httpx.MockTransport(handler), sleep=lambda s: None)
    got = feed.index_members("NIFTY 500")
    assert len(got) == 500 and got[0] == "360ONE"
    assert asked == ["nsearchives.nseindia.com/content/indices/ind_nifty500list.csv"]   # the live API wasn't needed
    assert feed.INDEX_FILES["NIFTY MIDCAP 150"] == "ind_niftymidcap150list.csv"
    assert feed.INDEX_FILES["NIFTY SMALLCAP 250"] == "ind_niftysmallcap250list.csv"


def test_a_group_without_a_list_neither_blanks_its_history_nor_forces_a_two_year_run(monkeypatch):
    from datetime import datetime, timezone
    from app import breadth as B
    store = {}
    monkeypatch.setattr(db, "get_setting", lambda k: store.get(k))
    monkeypatch.setattr(db, "set_setting", lambda k, v: store.__setitem__(k, v))
    from datetime import date as _d, timedelta as _td
    # the NIFTY 50 has two years of counts stored; the other groups have no list of stocks (the live API refuses)
    days = [(_d(2026, 10, 7) - _td(days=n)).isoformat() for n in range(400)]
    B.save_hist("nifty50", {d: [1] * len(B.COLS) for d in days})
    asked = []

    def load(region, sym, n):
        asked.append(n)
        raise LookupError("no prices here")
    runner = B.Runner(load, None, lambda name: (_ for _ in ()).throw(RuntimeError("refused")), lambda: [], sectors=lambda r: {}, gap=0)
    try:
        runner.run("IN", datetime(2026, 10, 8, 14, 0, tzinfo=timezone.utc))
    except RuntimeError:
        pass
    # before, the empty groups' missing history made every run read two years for every stock
    assert asked and set(asked) == {B.RECENT_DAYS}


# ---------- R5O-019: the brief's rotation is the rotation page's, and one style for every brief ----------
def test_the_briefs_rotation_is_the_pages_weekly_chart():
    import numpy as np
    from app import rotation
    from tests.test_rotation import bars_from
    rng = np.random.default_rng(7)
    series = {s: bars_from(list(100 * np.cumprod(1 + rng.normal(0.0004, 0.012, 700)))) for s in rotation.SECTORS["US"]["members"] + ["SPY"]}

    class Prov:
        def ready(self): return True
        def instrument(self, key): return {"symbol": key, "name": key}

    class Reg:
        def provider(self, m): return Prov()
        def resolve(self, iid): return Prov(), {"symbol": iid.split(":")[1]}
    load = (lambda iid, days: series[iid.split(":")[1]])
    reg = Reg()
    found = 0
    days = [b["t"][:10] for b in series["SPY"]][-25:]
    for day in days:                    # each day's shifts against the page's chart drawn on that day and the one before
        cut = {k: [b for b in v if b["t"][:10] <= day] for k, v in series.items()}
        prev_day = [b["t"][:10] for b in cut["SPY"]][-2]
        page = rotation.compute(reg, "US", [(f"US:{s}", s) for s in rotation.SECTORS["US"]["members"]], "weekly", 1,
                                lambda iid, n: cut[iid.split(":")[1]])
        before = rotation.compute(reg, "US", [(f"US:{s}", s) for s in rotation.SECTORS["US"]["members"]], "weekly", 1,
                                  lambda iid, n: [b for b in cut[iid.split(":")[1]] if b["t"][:10] <= prev_day])
        now_q = {r["symbol"]: r["quadrant"] for r in page["rows"]}
        was_q = {r["symbol"]: r["quadrant"] for r in before["rows"]}
        got = rotation.shifts(reg, "US", day, False, load=load)
        assert {r["symbol"]: (r["from"], r["to"]) for r in got} == {s: (was_q[s], now_q[s]) for s in now_q if was_q.get(s) != now_q[s]}
        found += len(got)
    assert found > 0                    # some day in those weeks had a sector change quadrant


def test_stored_briefs_get_one_style_and_the_pages_rotation(monkeypatch):
    from datetime import date
    from app.newsletter import job, write
    store = {}
    monkeypatch.setattr(db, "get_setting", lambda k: store.get(k))
    monkeypatch.setattr(db, "set_setting", lambda k, v: store.__setitem__(k, v))
    monkeypatch.setattr(db, "all_settings_with_prefix", lambda p: [(k, v) for k, v in store.items() if k.startswith(p)])
    monkeypatch.setattr(job, "date", type("D", (date,), {"today": classmethod(lambda cls: date(2026, 10, 8))}))
    weekly = {"id": "market.IN.2026-10-03-weekly", "kind": "market", "region": "IN", "day": "2026-10-03", "weekly": True,
              "subject": "Market Brief India, week to 03 Oct: NIFTY 50 -3.11%", "title": "NIFTY 50 down 3.11% over the week",
              "summary": "The NIFTY 50 fell -3.11% over the week.", "ai": True, "indices": [],
              "sections": [{"title": "Indices", "items": [{"text": "NIFTY 50: 22,421.95, -3.11% over the week", "url": None, "lines": []}]}],
              "at": "2026-10-03T16:15+05:30"}
    daily = {"id": "market.IN.2026-10-08", "kind": "market", "region": "IN", "day": "2026-10-08", "weekly": False,
             "subject": "Market Brief India, Thu 8 Oct: NIFTY 50 −1.64%", "title": "NIFTY 50 down 1.64%",
             "summary": "Nifty IT moving from weakening to leading stood out.", "ai": True,
             "indices": [{"name": "NIFTY 50", "price": 22231.8, "change_pct": -1.64}],
             "sections": [{"title": "Indices", "items": [{"text": "NIFTY 50: 22,231.80, −1.64% on the day", "url": None, "lines": []}]},
                          {"title": "Sector rotation", "items": [{"text": "Nifty IT moved from Weakening to Leading on the rotation chart", "url": None, "lines": []}]}],
             "at": "2026-10-08T16:20+05:30"}
    for i in (weekly, daily):
        i["html"], i["text"] = write.render(i)
        job.save(i)
    # as the page draws it on 8 Oct: Nifty IT is still Weakening, nothing moved
    n = job.repair_briefs("IN", shifts=lambda region, wk, day: [])
    assert n == 2
    w = job.load("market.IN.2026-10-03-weekly")
    assert w["subject"] == "Market Brief India, week to 3 Oct: NIFTY 50 −3.11%"
    assert "−3.11% over the week" in w["sections"][0]["items"][0]["text"] and "-3.11" not in w["html"] + w["text"]
    d = job.load("market.IN.2026-10-08")
    assert [s["title"] for s in d["sections"]] == ["Indices"] and "Leading" not in d["html"] + d["text"]
    assert not d["ai"] and "leading" not in d["summary"].lower()
    assert job.repair_briefs("IN", shifts=lambda region, wk, day: []) == 0          # once is enough


# ---------- R5O-021: whole-number growth rates stay whole ----------
def test_a_whole_number_rate_from_the_source_says_so():
    from app.intel.company import _item
    # TCS's stock price CAGRs from the source: "-12%" and "6%", shown as "-12.0%" and "+6.0%"
    assert _item("5Y", "-12%", "%±") == {"label": "5Y", "value": -12.0, "unit": "%±", "dp": 0}
    assert _item("10Y", "6%", "%±")["dp"] == 0
    assert "dp" not in _item("1Y", -31.42, "%±")                     # worked out from the candles: its decimals stand
    assert "dp" not in _item("Div yield", "3.13 %", "%") and "dp" not in _item("P/E", "14", "x")
    # TCS and Infosys's identical 5Y and 10Y profit CAGRs are real (5 Oct pages: 8.72% and 8.70% over FY21-FY26 from
    # 32,562 -> 49,454 and 19,423 -> 29,474 crore; both "8%" over ten years); the compare page now names each section
    assert round(((49454 / 32562) ** (1 / 5) - 1) * 100, 1) == round(((29474 / 19423) ** (1 / 5) - 1) * 100, 1) == 8.7


# ---------- R5O-022: the Money card's tax is the tax report's; the audit limit as a fact ----------
def test_turnover_past_the_audit_limit_is_said_as_a_fact():
    from app import tax_total as T
    import re
    got = T.audit_fact(2025, 39.7e7, True)                       # the owner's FY 2025-26 F&O turnover, Rs39.7 crore
    assert got == "Turnover of ₹39.7 crore is above ₹10 crore, the higher limit in section 44AB: a tax audit applies."
    assert got in T.filing_facts(2025, 39.7e7, True)
    mid = T.audit_fact(2025, 4.2e7, True)
    assert mid.startswith("Turnover of ₹4.2 crore is above ₹1 crore") and "₹10 crore" in mid
    assert T.audit_fact(2025, 0.8e7, True) is None and T.audit_fact(2025, 39.7e7, False) is None
    assert not re.search(r"\b(should|must get|we recommend|consult|advise)\b", got + mid, re.I)


# ---------- R5O-026: "the quarter to 5 Oct 2026" ----------
def test_named_holders_coverage_is_a_quarter_end(monkeypatch):
    from app import shareholders as S
    # a pattern filed for an allotment on 5 Oct sits beside the 30 Sep quarter's
    monkeypatch.setattr(S, "_index", lambda: {"ABC": {"name": "Abc", "q": {"2026-06-30": {}, "2026-10-05": {}}},
                                              "XYZ": {"name": "Xyz", "q": {"2026-06-30": {}, "2026-09-30": {}}}})
    monkeypatch.setattr(db, "get_setting", lambda k: None)
    assert S.coverage()["latest_quarter"] == "2026-09-30"
    assert S.quarter_end("2026-12-31") and not S.quarter_end("2026-10-05")


# ---------- R5O-028: the SIP test's "lowest" includes the run above it ----------
def test_the_lowest_xirr_is_never_above_the_run_shown():
    from app import sip_test as SIP
    from tests.test_sip_test import leg, plan, weekdays
    # five years to 8 Oct 2026 ending in a fall after 1 Oct: the latest start does worst, as NIFTYBEES's did (3.7% from Nov 2021
    # against "Lowest XIRR 4.2% from Oct 2021", the month starts stopping a month short of it)
    days = [d for d in weekdays("2019-01-01", 2100) if d <= "2026-10-08"]
    prices = {d: 100 * (1 + 0.0002 * i) * (0.9 if d > "2026-10-01" else 1.0) for i, d in enumerate(days)}   # the last week falls
    legs = [leg(prices)]
    start, end = SIP._add_years("2026-10-08", -5), "2026-10-08"
    shown = SIP.simulate(legs, plan(), start, end)
    s = SIP.spread(legs, plan(), 5, days[0], days[-1], also=(start,))
    assert shown["start"][:7] == "2021-11" and any(r["start"] == "2021-11" for r in s["runs"])
    assert s["worst"]["xirr"] <= shown["xirr"]
    old = SIP.spread(legs, plan(), 5, days[0], days[-1])
    assert old["worst"]["xirr"] > shown["xirr"]                     # what the page said before


# ---------- R5O-033: the break-even percentage is rounded once ----------
def test_margin_funding_break_even_is_rounded_once():
    from app import mtf
    # Rs1,000 a share, 100 shares, half funded at 15% for 45 days: Rs924.66 of interest, Rs1,009.25 to break even
    out = mtf.cost(mtf.CostReq(buy=1000, qty=100, margin_pct=50, rate_pct=15, days=45))
    assert out["breakeven"] == 1009.25
    assert f"{out['breakeven_pct']:.2f}" == "0.92"                  # was 0.925 on the wire, shown "+0.93%"


# ---------- R5O-039: a stop hit never costs more than the stated risk ----------
def test_rupees_are_grouped_the_indian_way_and_dates_unpadded():
    import json as _json
    from datetime import date
    from app import money_networth as N
    # the owner's "R5 test FD": "Rs100,000 at 7% ... from 01 Apr 2026" beside "Rs1,03,670" and "1 Apr 2027"
    v = N.build([{"id": "a", "kind": "fd", "name": "R5 test FD", "principal": 100000, "rate": 7, "compounding": "quarterly",
                  "start": "2026-04-01", "maturity": "2027-04-01"}], None, None, N.Prices(), date(2026, 10, 8))
    text = _json.dumps(v, ensure_ascii=False)
    assert "₹1,00,000 at 7% a year, compounded quarterly, from 1 Apr 2026" in text and "₹100,000" not in text and "01 Apr" not in text
    from app import sip_test as SIP
    from tests.test_sip_test import leg, plan
    assert "invest ₹1,00,000" in SIP.words(plan(amount=100000), [leg({}, "NIFTYBEES")])


def test_risk_sizing_never_exceeds_the_stated_risk():
    from app.engine.core import backtest
    from app.models import Strategy
    from tests.test_engine import bars_from
    # 1% of Rs5,00,000 with a 2% stop: Rs5,000 at risk. After a winning trade the account had grown, and the next entry at
    # NIFTY 24,187 took 11 units (11 x 2% x 24,187 = Rs5,321); it takes 10 (Rs4,837), the most within Rs5,000
    s = Strategy(entry=[{"l": {"t": "price"}, "op": "xa", "r": {"t": "num", "v": 20000}}],
                 exit=[{"l": {"t": "price"}, "op": "xa", "r": {"t": "num", "v": 23000}}],
                 risk={"capital": 500000, "riskPct": 1, "sl": 2, "tgt": 0, "brokerage": 0, "slippage": 0})
    closes = [19000.0] * 10 + [20500.0] * 3 + [23500.0] * 3 + [19000.0] * 5 + [24187.0] * 5
    out = backtest(bars_from(closes), s, start=2, cost_kind="flat")
    buys = [e for e in out["events"] if e["side"] == "buy"]
    assert len(buys) == 2 and out["equity"][15] > 500000                 # the first trade won: the account grew
    for e in buys:
        assert e["qty"] * e["px"] * 0.02 <= 5000 + 1e-6, e
    assert buys[1]["qty"] == 10


# ---------- R5O-002: the database connection drops ----------
class Flaky(httpx.BaseTransport):
    """Fails the first `fail` requests with `exc`, then answers 200."""

    def __init__(self, exc, fail=1):
        self.exc, self.fail, self.calls = exc, fail, []

    def handle_request(self, request):
        self.calls.append(request.method)
        if len(self.calls) <= self.fail:
            raise self.exc("Server disconnected without sending a response.", request=request)
        return httpx.Response(200, json=[{"id": 1}])


def test_a_read_is_tried_once_more_when_the_connection_drops():
    inner = Flaky(httpx.RemoteProtocolError)
    with httpx.Client(transport=db.RetryReads(inner)) as c:
        r = c.get("https://db.example/rest/v1/profiles")
    assert r.json() == [{"id": 1}] and inner.calls == ["GET", "GET"]


def test_a_read_fails_after_one_retry_not_forever():
    inner = Flaky(httpx.RemoteProtocolError, fail=5)
    with httpx.Client(transport=db.RetryReads(inner)) as c, pytest.raises(httpx.RemoteProtocolError):
        c.get("https://db.example/rest/v1/profiles")
    assert inner.calls == ["GET", "GET"]


def test_a_write_is_not_sent_twice_when_it_may_have_landed():
    inner = Flaky(httpx.RemoteProtocolError)
    with httpx.Client(transport=db.RetryReads(inner)) as c, pytest.raises(httpx.RemoteProtocolError):
        c.post("https://db.example/rest/v1/usage_events", json={"kind": "x"})
    assert inner.calls == ["POST"]


def test_a_write_that_never_left_is_sent_again():
    inner = Flaky(httpx.ConnectError)
    with httpx.Client(transport=db.RetryReads(inner)) as c:
        r = c.post("https://db.example/rest/v1/usage_events", json={"kind": "x"})
    assert r.status_code == 200 and inner.calls == ["POST", "POST"]


def test_the_database_client_uses_a_pool_of_http1_connections(monkeypatch):
    """HTTP/2 shared by every thread raised KeyError: 819 (a stream number) in count_usage and "Server disconnected"
    for every request in flight; the client is HTTP/1.1 with the retrying transport."""
    monkeypatch.setattr(db, "_client", None)
    monkeypatch.setattr(db.settings, "SUPABASE_URL", "http://127.0.0.1:9")
    monkeypatch.setattr(db.settings, "SUPABASE_SERVICE_KEY", "eyJhbGciOiJIUzI1NiJ9.eyJyb2xlIjoic2VydmljZV9yb2xlIn0.x")
    c = db.sb()
    try:
        session = c.postgrest.session
        assert isinstance(session._transport, db.RetryReads)
        pool = session._transport.inner._pool
        assert pool._http2 is False and pool._http1 is True
    finally:
        monkeypatch.setattr(db, "_client", None)


def _server(replies):
    """A one-thread HTTP server on localhost: the first connection is closed without an answer, the rest answer."""
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    s.listen(8)
    seen = []

    def run():
        while True:
            try:
                conn, _ = s.accept()
            except OSError:
                return
            with conn:
                data = conn.recv(65536)
                if not data:
                    continue
                seen.append(data.split(b"\r\n", 1)[0].decode())
                if len(seen) <= replies.get("drop", 0):
                    continue            # close without a word: "Server disconnected without sending a response"
                body = b'[{"id": 7}]'
                conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Range: 0-0/3\r\n"
                             b"Connection: close\r\nContent-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body)
    threading.Thread(target=run, daemon=True).start()
    return s, seen


def test_a_real_count_survives_a_dropped_connection(monkeypatch):
    srv, seen = _server({"drop": 1})
    try:
        monkeypatch.setattr(db, "_client", None)
        monkeypatch.setattr(db, "RETRY_PAUSE", 0.0)
        monkeypatch.setattr(db.settings, "SUPABASE_URL", f"http://127.0.0.1:{srv.getsockname()[1]}")
        monkeypatch.setattr(db.settings, "SUPABASE_SERVICE_KEY", "eyJhbGciOiJIUzI1NiJ9.eyJyb2xlIjoic2VydmljZV9yb2xlIn0.x")
        assert db.count_usage("u1", "backtest", "2026-10-01T00:00:00+00:00") == 3
        assert len(seen) == 2 and all(x.startswith("GET /rest/v1/usage_events") for x in seen)
    finally:
        srv.close()
        monkeypatch.setattr(db, "_client", None)


def test_admin_sessions_lists_an_options_session_with_its_market():
    """'OptionSession' object has no attribute 'market' (25 Sep): the session carries its market now."""
    from app.options.session import OptionSession
    src = OptionSession.__init__.__code__.co_names
    assert "market" in src


# ---------- R5O-008: the theme map's tickers ----------
LISTED_IN = [{"symbol": "BHARTIARTL", "name": "BHARTI AIRTEL"}, {"symbol": "BHEL", "name": "BHARAT HEAVY ELECTRICALS"},
             {"symbol": "BEL", "name": "BHARAT ELECTRONICS"}, {"symbol": "MAZDOCK", "name": "MAZAGON DOCK SHIPBUILDERS"},
             {"symbol": "HAL", "name": "HINDUSTAN AERONAUTICS"}, {"symbol": "TATAELXSI", "name": "TATA ELXSI"},
             {"symbol": "MODEFENCE", "name": "MOTILAL OSWAL NIFTY INDIA DEFENCE ETF"},
             {"symbol": "SOLARINDS", "name": "SOLAR INDUSTRIES (I) LTD"}]


def fake_lookup(q, region):
    """A stand-in for the market's list: the exact symbol, else names with the first two words typed."""
    from app.intel.grounding import _words, _same_word
    exact = [r for r in LISTED_IN if r["symbol"] == q.upper()]
    if exact:
        return exact
    want = _words(q)
    return [r for r in LISTED_IN if want and all(any(_same_word(w, x) for x in _words(r["name"])) for w in want[:2])]


def test_names_agree():
    from app.intel.grounding import names_agree
    assert names_agree("Bharat Heavy Electricals Ltd", "BHARAT HEAVY ELECTRICALS")
    assert names_agree("Solar Industries India", "SOLAR INDUSTRIES (I) LTD")
    assert names_agree("Tata Consultancy Services", "TATA CONSULTANCY SERV LT")
    assert names_agree("Vertiv", "Vertiv Holdings Co")
    assert not names_agree("Bharat Heavy Electricals Ltd", "BHARTI AIRTEL")
    assert not names_agree("Bharat Heavy Electricals", "BHARAT ELECTRONICS")
    assert not names_agree("Tata Advanced Systems", "TATA ELXSI")
    assert not names_agree("Hindustan Aeronautics", "HINDUSTAN UNILEVER")


def test_theme_tickers_are_checked_against_the_list():
    from app.intel.grounding import ground_sector
    ai = {"screen": [{"name": "Bharat Heavy Electricals Ltd", "ticker": "BHARTIARTL", "layer": "OEM"},
                     {"name": "Mazagon Dock Shipbuilders", "ticker": "MDSL", "layer": "Shipyards"},
                     {"name": "Tata Advanced Systems", "ticker": "TATASYS", "layer": "Private OEM"},
                     {"name": "Hindustan Aeronautics", "ticker": "HAL", "layer": "Aircraft"}],
          "clusters": [{"name": "State-owned OEMs", "companies": [
              {"name": "Bharat Heavy Electricals Ltd", "ticker": "BHARTIARTL"}, {"name": "Tata Advanced Systems", "ticker": "TATASYS"},
              {"name": "Antrix", "ticker": ""}, {"name": "Bharat Electronics", "ticker": "BEL"}]}],
          "value_chain": [{"layer": "Ships", "companies": [{"name": "Mazagon Dock", "ticker": "MDSL"}]}],
          "etfs": [{"ticker": "NIFTYDEF", "name": "Nifty India Defence ETF"}, {"ticker": "INDDEF", "name": "India Defence Fund"},
                   {"ticker": "MODEFENCE", "name": "Motilal Oswal Nifty India Defence ETF"}]}
    out = ground_sector(ai, "IN", fake_lookup)
    assert [(s["ticker"], s["name"]) for s in out["screen"]] == [
        ("BHEL", "Bharat Heavy Electricals Ltd"), ("MAZDOCK", "Mazagon Dock Shipbuilders"), ("HAL", "Hindustan Aeronautics")]
    cos = out["clusters"][0]["companies"]
    assert [(c["name"], c["ticker"], c["listed"]) for c in cos] == [
        ("Bharat Heavy Electricals Ltd", "BHEL", True), ("Tata Advanced Systems", "", False), ("Antrix", "", False),
        ("Bharat Electronics", "BEL", True)]
    assert out["value_chain"][0]["companies"][0]["ticker"] == "MAZDOCK"
    assert out["etfs"] == [{"ticker": "MODEFENCE", "name": "MOTILAL OSWAL NIFTY INDIA DEFENCE ETF"}]


def test_a_theme_map_is_grounded_before_it_is_cached():
    """The route runs the check on what the AI wrote, so a cached map never carries an unchecked ticker."""
    from app.intel import routes
    src = open(routes.__file__).read()
    assert "grounding.ground_sector(A.sector(theme, r, _ai), r, hub.search)" in src


def test_when_the_list_is_down_nothing_passes_as_checked():
    from app.intel.grounding import ground_sector

    def down(q, region):
        raise RuntimeError("list down")
    out = ground_sector({"screen": [{"name": "Hindustan Aeronautics", "ticker": "HAL"}], "etfs": [{"ticker": "X", "name": "Y"}]},
                        "IN", down)
    assert out["screen"] == [] and out["etfs"] == []


# ---------- R5O-018: the market read, checked against the index numbers ----------
NIFTY_8_OCT = [{"name": "NIFTY 50", "price": 22231.80, "change_pct": -1.64, "high52": 26400.0, "low52": 22182.55,
                "from_high_pct": -15.79},
               {"name": "SENSEX", "price": 71593.24, "change_pct": -1.44, "high52": 85900.0, "low52": 71000.0, "from_high_pct": -16.7}]
HEADLINES = [{"headline": "Sensex, Nifty fall 1.6% as IT and banking shares slide; RBI raises repo rate to 5.5%"}]


def test_the_market_read_keeps_only_what_the_numbers_and_headlines_support():
    from app.intel.grounding import ground_pulse
    ai = {"tone": ("The NIFTY 50 fell 1.64% to 22,231.80 and the SENSEX lost 1.44%. Selling pushed the indices well below their "
                   "52-week lows, erasing roughly ₹7 lakh crore of market value. Hawkish Fed minutes weighed on sentiment. "
                   "Money rotated into utilities. The RBI raised the repo rate to 5.5%. Markets could rebound next week."),
          "hot": [{"name": "Infosys", "ticker": "INFY", "why": "IT shares slid."}, {"name": "Reliance", "ticker": "RELIANCE", "why": "Jio."}],
          "flows": [{"title": "FII selling", "detail": "Foreign investors sold.", "direction": "OUTFLOW"}],
          "themes": []}
    out = ground_pulse(ai, NIFTY_8_OCT, HEADLINES)
    assert out["tone"] == "The NIFTY 50 fell 1.64% to 22,231.80 and the SENSEX lost 1.44%. The RBI raised the repo rate to 5.5%."
    assert out["hot"] == [] and out["flows"] == []        # no headline names them
    for gone in ("52-week lows", "lakh crore", "Fed", "utilities", "rebound"):
        assert gone not in out["tone"]


def test_a_52_week_claim_must_match_the_levels():
    from app.intel.grounding import range_claims_ok
    assert not range_claims_ok("The indices fell well below their 52-week lows.", NIFTY_8_OCT)
    assert range_claims_ok("The NIFTY 50 closed near its 52-week low.", NIFTY_8_OCT)          # 0.2% above it
    assert not range_claims_ok("The market hit record highs.", NIFTY_8_OCT)
    below = [{**NIFTY_8_OCT[0], "price": 22100.0}]
    assert range_claims_ok("The NIFTY 50 broke below its 52-week low.", below)


def test_when_nothing_survives_the_read_is_the_numbers_alone():
    from app.intel.grounding import ground_pulse
    out = ground_pulse({"tone": "Stocks rallied to record highs on hopes of a Fed cut."}, NIFTY_8_OCT, HEADLINES)
    assert out["tone"].startswith("NIFTY 50 at 22,231.80, −1.64% on the day, 0.2% above its 52-week low and 15.8% below its high.")


def test_the_pulse_gives_the_ai_the_52_week_position_and_checks_its_reply(monkeypatch):
    import json as _json
    from app.intel import ai as A
    seen = {}

    def fake(system, text, **k):
        seen["facts"] = text
        return _json.dumps({"tone": "Indices sank below their 52-week lows. The NIFTY 50 fell 1.64%.", "hot": [], "flows": [], "themes": []})
    monkeypatch.setattr(A, "complete", fake)
    out = A.pulse("IN", "", NIFTY_8_OCT, HEADLINES, (None, None))
    assert out["tone"] == "The NIFTY 50 fell 1.64%." and '"from_low_pct": 0.22' in seen["facts"]


# ---------- R5O-027: the company read, checked against the company's numbers ----------
def test_the_company_read_states_facts_only():
    from datetime import date
    from app.intel.grounding import ground_company
    facts = {"symbol": "AAPL", "price": 336.67, "metrics": {"P/E": 37.98, "200-day average": 290.2}, "range_52w": [190.0, 340.0]}
    read = {"summary": "Apple sells iPhones, Macs and services. Its P/E is 37.98, lower than the typical range of 20-30 for the company.",
            "valuation_note": "The share price is 16% above its 200-day average, indicating limited upside.",
            "bull": ["Services keep growing.", "The stock looks cheap at 37.98 times earnings."], "bear": ["Rivals may pressure margins."],
            "position": "", "watch": ["Q4 FY2025 earnings release"],
            "ideas": [{"title": "Fade overbought", "text": "Sell AAPL short when 14-day RSI exceeds 70, cover when it drops below 50, 3% stop loss", "why": "x"},
                      {"title": "Trend", "text": "Buy AAPL when the 20-day EMA crosses above the 50-day EMA, sell when it crosses back below", "why": "y"}]}
    out = ground_company(read, facts, "US", date(2026, 10, 8))
    assert out["summary"] == "Apple sells iPhones, Macs and services."
    assert out["valuation_note"] == ""                     # "limited upside" is a forecast; 16% isn't in the facts either
    assert out["bull"] == ["Services keep growing."] and out["bear"] == []
    texts = [i["text"] for i in out["ideas"]]
    assert texts[0] == "Enter short when 14-day RSI exceeds 70, cover when it drops below 50, 3% stop loss"
    assert texts[1] == "Enter long when the 20-day EMA crosses above the 50-day EMA, exit when it crosses back below"
    assert not any("AAPL" in t or t.lower().startswith(("sell", "buy")) for t in texts)


def test_indian_fiscal_quarter_labels_follow_the_calendar():
    from datetime import date
    from app.intel.grounding import fiscal_quarter, fix_fiscal_labels, ground_company
    assert fiscal_quarter(date(2026, 10, 8), "IN") == (2, 2027)
    assert fiscal_quarter(date(2027, 2, 1), "IN") == (3, 2027)
    assert fiscal_quarter(date(2026, 5, 1), "IN") == (4, 2026)
    assert fix_fiscal_labels("Q2 FY2026 earnings release", date(2026, 10, 8), "IN") == "Q2 FY2027 earnings release"
    assert fix_fiscal_labels("Q1 FY27 results", date(2026, 10, 8), "IN") == "Q1 FY2027 results"
    out = ground_company({"summary": "Revenue grew in Q3 FY26.", "watch": ["Q2 FY2026 earnings release"]}, {"symbol": "TCS"}, "IN", date(2026, 10, 8))
    assert out["watch"] == ["Q2 FY2027 earnings release"] and out["summary"] == "Revenue grew in Q3 FY26."   # the past stays


def test_company_profiles_lose_scrape_residue():
    from app.intel.screener import clean_profile
    raw = ("Tata Consultancy Services is an IT services, consulting and business solutions company.[1] "
           "[1] Revenue Breakup Q3FY26 [1] BFSI : 31.9% Manufacturing : 8.4%")
    assert clean_profile(raw) == "Tata Consultancy Services is an IT services, consulting and business solutions company."


# ---------- R5O-023: the scan page ----------
def test_a_live_scan_says_last_price_not_closed_at():
    import numpy as np
    from app import scan_presets
    from tests.test_scan_presets import bars
    closes = list(np.concatenate([np.linspace(150, 100, 260), [100.0] * 5]))
    b = bars(closes + [min(closes[-253:]) * 1.03])
    live = scan_presets.evaluate(b, only=["near_low52"], live=True)["matches"]["near_low52"]["detail"]
    stored = scan_presets.evaluate(b, only=["near_low52"])["matches"]["near_low52"]["detail"]
    assert live.startswith("Last price ") and stored.startswith("Closed at ")


def test_a_skipped_stock_is_named_by_its_symbol_and_counted():
    from app import scan

    class Prov:
        def instrument(self, token):
            return {"symbol": "SIMPLXREA", "name": "Simplex Realty"} if token == "195818241" else None

    class Reg:
        def provider(self, market):
            return Prov()

        def resolve(self, iid):
            return Prov(), {"id": iid}
    import app.universes as U
    orig_resolve, orig_bars = U.resolve, scan._bars
    try:
        U.resolve = lambda reg, market, members: (["IN:195818241"], [])
        scan._bars = lambda reg, iid: [{"t": "2026-10-08", "o": 1, "h": 1, "l": 1, "c": 1, "v": 1}] * 3
        out = scan.run_preset(Reg(), "IN", [{"symbol": "SIMPLXREA"}], "near_low52")
    finally:
        U.resolve, scan._bars = orig_resolve, orig_bars
    assert out["problems"] == ["SIMPLXREA: not enough daily prices yet"] and out["checked"] == 0 and out["asked"] == 1


# ---------- R5O-020: no provider names; a US company's own news and peers ----------
def test_us_peers_start_with_companies_of_its_size_in_its_sector():
    from app.intel.company import us_peers
    got = us_peers("AAPL", ["DELL", "SNDK", "WDC", "HPE", "NTAP", "SMCI", "HPQ", "NOTREAL"])
    assert got[:3] == ["MSFT", "NVDA", "AVGO"] and "NOTREAL" not in got and len(got) == 8


def test_a_providers_news_page_is_not_shown_as_the_publisher():
    from app.branding import public_research
    out = public_research({"news": [{"headline": "Apple unveils", "source": "Yahoo"}, {"headline": "x", "source": "Reuters"}]})
    assert [n["source"] for n in out["news"]] == [None, "Reuters"]


def test_us_company_news_is_about_the_company():
    from app.intel.news import mentions
    assert mentions("Apple Inc", "AAPL", "Apple's iPhone 18 sales rise in China")
    assert not mentions("Apple Inc", "AAPL", "Dow futures slip ahead of jobs data")
    assert not mentions("Apple Inc", "AAPL", "OneKey launches a new hardware wallet")
    src = open(__import__("app.intel.company", fromlist=["x"]).__file__).read()
    assert 'mentions(p["name"], sym, n["headline"])' in src


# ---------- R5O-031: the owner's Zerodha holdings, on the data login's token ----------
from tests.test_connect import ADMIN, FakeKite, kite, kite_login, on   # noqa: E402,F401  (fixtures)


def _data_login(monkeypatch, user="AB1234"):
    from app.kite_service import today_ist
    monkeypatch.setattr(db.settings, "KITE_USER_ID", user)
    db.set_setting("kite_access_token", "DATA-TOKEN-TODAY")
    db.set_setting("kite_token_day", today_ist())


def test_the_owners_holdings_follow_the_data_login_without_a_daily_login(w, kite, monkeypatch):
    from app.connect import jobs, kite_user, state, vault
    c = w["client"]
    kite_login(c)                                       # connected yesterday, as Zerodha user AB1234
    state.update("u-admin", "kite", day="2020-01-01", refreshed_at="2020-01-01T09:00:00+00:00")
    assert c.post("/connect/kite/refresh", headers=ADMIN).status_code == 409        # no data login today: log in again
    _data_login(monkeypatch)
    v = c.get("/connect", headers=ADMIN).json()["kite"]
    assert v["live"] and not v["expired"]
    from datetime import datetime
    from app.kite_service import IST
    assert jobs.kite_user.run_daily(datetime.now(IST).replace(hour=10, minute=0)) == 1
    box = state.section("u-admin", "kite")
    assert vault.unseal(box["token"]) == "DATA-TOKEN-TODAY" and box["status"] == "ok"
    assert kite_user.run_daily(datetime.now(IST).replace(hour=11)) == 0          # once a day


def test_another_zerodha_account_still_logs_in_itself(w, kite, monkeypatch):
    from app.connect import state
    c = w["client"]
    kite_login(c)
    state.update("u-admin", "kite", day="2020-01-01")
    _data_login(monkeypatch, user="ZZ9999")             # the data login is a different Zerodha account
    assert c.post("/connect/kite/refresh", headers=ADMIN).status_code == 409


def test_the_owner_connecting_shares_the_data_login_instead_of_cancelling_it(w, kite, monkeypatch):
    from app.connect import state
    _data_login(monkeypatch)
    r = w["client"].get("/connect/kite/login", headers=ADMIN).json()
    assert r["shared"] is True and r["url"] == "https://site.example/settings?kite=ok#accounts"
    assert not [x for x in FakeKite.log if x[0] == "session"]                        # no second Zerodha login
    assert state.section("u-admin", "kite")["status"] == "ok"


# ---------- R5O-025: slow pages ----------
def test_a_daily_candles_time_is_its_day_not_midnight():
    from app.main import candle_day
    assert candle_day("2026-10-08T00:00:00+05:30") == "2026-10-08"
    assert candle_day("2026-10-08") == "2026-10-08"
    assert candle_day("2026-10-08T15:29:00+05:30") == "2026-10-08T15:29:00+05:30"
    assert candle_day(None) is None


def test_a_sector_of_business_updates_is_read_in_one_database_call(monkeypatch):
    from app import biz_updates as B
    reads, batches = [], []
    monkeypatch.setattr(B._cache, "get", lambda k: None)
    monkeypatch.setattr(B._cache, "set", lambda *a, **k: None)
    monkeypatch.setattr(db, "prefetch_settings", lambda keys: batches.append(list(keys)))
    monkeypatch.setattr(db, "get_setting", lambda k: reads.append(k) or None)
    sector = next(iter(B.SECTORS))
    B.sector_view(sector)
    assert len(batches) == 1 and len(batches[0]) == len(B.SECTORS[sector]["symbols"])


def test_holders_page_opens_on_the_kept_count_and_builds_the_index_behind(monkeypatch):
    from app import shareholders as S
    store = {S.COVERAGE_KEY: '{"companies": 1840, "latest_quarter": "2026-06-30"}'}
    monkeypatch.setattr(db, "get_setting", lambda k: store.get(k))
    monkeypatch.setattr(db, "set_setting", lambda k, v: store.__setitem__(k, v))
    monkeypatch.setattr(S._cache, "get", lambda k: None)
    built = []
    monkeypatch.setattr(S, "_build_behind", lambda: built.append(1))
    monkeypatch.setattr(S, "_index", lambda: (_ for _ in ()).throw(AssertionError("no full read on opening")))
    assert S.coverage() == {"companies": 1840, "latest_quarter": "2026-06-30", "queued": 0} and built == [1]


def test_a_fresh_recording_answers_while_the_live_chain_is_read(monkeypatch):
    from datetime import datetime, timedelta, timezone
    from app import positioning as P
    now = datetime.now(timezone.utc)
    rec = {"expiry": "2026-10-13", "expiries": ["2026-10-13"], "spot": 22200, "chain": [], "source": "recorded",
           "taken_at": (now - timedelta(minutes=2)).isoformat()}
    monkeypatch.setattr(P, "recorded_last", lambda name, day: [rec])
    monkeypatch.setattr(P, "recorded_chain", lambda name, choice, day: rec)
    assert P._fresh_recording("NIFTY", "current") is rec
    old = {**rec, "taken_at": (now - timedelta(minutes=30)).isoformat()}
    monkeypatch.setattr(P, "recorded_chain", lambda name, choice, day: old)
    assert P._fresh_recording("NIFTY", "current") is None


def test_the_deep_dive_reads_its_sources_side_by_side():
    from app import main
    src = open(main.__file__).read()
    assert '_deep_pool.submit(filings_feed.announcements, sym' in src and '_deep_pool.submit(price_status, sym)' in src


# ---------- R5O-016: a job's last run survives a restart ----------
def test_a_jobs_last_run_is_shown_after_a_restart(monkeypatch):
    from app import job_status
    store = {}
    monkeypatch.setattr(db, "get_setting", lambda k: store.get(k))
    monkeypatch.setattr(db, "set_setting", lambda k, v: store.__setitem__(k, v))
    monkeypatch.setattr(job_status, "_written", {})

    class Job:
        status = {"last_run": "2026-10-08T03:00:00+00:00", "last_error": None, "problems": []}
    job_status.keep("positioning", Job())
    after_restart = {"last_run": None, "last_error": None, "problems": []}
    got = job_status.kept("positioning", after_restart)
    assert got["last_run"] == "2026-10-08T03:00:00+00:00" and got["before_restart"] is True
    assert job_status.kept("never-ran", after_restart) == after_restart


def test_the_news_jobs_keep_their_status_when_they_mark_a_run():
    from app import main  # noqa: F401  (the jobs import each other through the app, as when it starts)
    from app import etf_nav, fo_changes, market_events, positioning, surveillance, vix
    keys_ = {m.Job.status_key for m in (etf_nav, fo_changes, market_events, positioning, surveillance, vix)}
    assert keys_ == {"etf", "fo", "events", "positioning", "surveillance", "vix"}
    src = open(__import__("app.admin_jobs", fromlist=["x"]).__file__).read()
    for k in keys_ | {"corp", "results", "closing-auction"}:
        assert f'"{k}")' in src, k


# ---------- R5O-014: the library's cards beside buy and hold ----------
def test_library_entries_carry_their_return_beside_buy_and_hold():
    from app import library
    e = {"stats": {"ret": 55.8, "buy_hold": 172.9, "trades": 40}, "verdict": {"verdict": "edge", "checks": []}}
    assert library.public(e)["vs_hold"] == {"ret": 55.8, "hold": 172.9, "gap": -117.1}
    assert library.public({**e, "stats": {**e["stats"], "trades": 0}})["vs_hold"] is None       # never traded: nothing to compare
    assert library.public({**e, "stats": {"ret": 5.0, "buy_hold": None, "trades": 20}})["vs_hold"] is None


# ---------- R5O-010: notebook defaults ----------
@pytest.fixture
def w(monkeypatch):
    from tests import world
    built = world.build(monkeypatch)
    yield built
    built["close"]()


def test_the_questions_about_an_idea_stay_with_the_notebook(w):
    c, h = w["client"], w["headers"]("pro-token")
    gaps = {"mentioned": ["sl"], "notes": [], "instName": None, "usedAI": True, "fallback": ""}
    strat = {"name": "EMA", "entry": [{"l": {"t": "ema", "p": 20}, "op": "xa", "r": {"t": "ema", "p": 50}}], "risk": {"sl": 2, "tgt": 0}}
    nb = c.post("/notebooks", headers=h, json={"name": "EMA", "strategy": strat, "gaps": gaps}).json()
    assert c.get(f"/notebooks/{nb['id']}", headers=h).json()["gaps"]["mentioned"] == ["sl"]
    # an answer is kept: the person leaves and comes back to the same place
    r = c.put(f"/notebooks/{nb['id']}", headers=h, json={"gaps": {**gaps, "answered": {"exit": "Sell when EMA 20 drops below EMA 50"}}})
    assert r.status_code == 200
    back = c.get(f"/notebooks/{nb['id']}", headers=h).json()
    assert back["gaps"]["answered"] == {"exit": "Sell when EMA 20 drops below EMA 50"}
    assert back["strategy"]["risk"]["tgt"] == 0          # no target was asked for, none is stored
    # an unrelated save keeps them; "Close" clears them
    c.put(f"/notebooks/{nb['id']}", headers=h, json={"notes": "x"})
    assert c.get(f"/notebooks/{nb['id']}", headers=h).json()["gaps"]["mentioned"] == ["sl"]
    c.put(f"/notebooks/{nb['id']}", headers=h, json={"clearGaps": True})
    assert not c.get(f"/notebooks/{nb['id']}", headers=h).json().get("gaps")


def test_gaps_are_bounded(w):
    c, h = w["client"], w["headers"]("pro-token")
    nb = c.post("/notebooks", headers=h, json={"name": "X"}).json()
    r = c.put(f"/notebooks/{nb['id']}", headers=h, json={"gaps": {"mentioned": ["x" * 50]}})
    assert r.status_code == 422


def test_the_ai_builders_internal_notes_are_not_shown():
    from app.ai_writer import user_note
    assert not user_note("No timeframe specified, left as null.")
    assert not user_note("Timeframe not specified; defaulted to daily.")
    assert not user_note("No stop loss was given.")
    assert not user_note("The user did not mention an exit.")
    assert user_note("Option legs can't be tested here, so the straddle part was left out.")
    assert user_note("Advanced indicators need the Basic plan, so MACD was left out.")
    assert user_note("The volume filter you mentioned isn't available, so it was skipped.")


def test_write_strategy_drops_internal_notes(monkeypatch):
    import json as _json
    from app import ai_writer
    reply = {"entry": [{"l": {"t": "ema", "p": 20}, "op": "xa", "r": {"t": "ema", "p": 50}}], "exit": [], "tf": None,
             "risk": {"sl": 2}, "mentioned": ["sl"],
             "notes": ["No timeframe specified, left as null.", "Short selling on delivery isn't possible, so only longs are tested."]}
    monkeypatch.setattr(ai_writer, "complete", lambda *a, **k: _json.dumps(reply))
    out = ai_writer.write_strategy("Buy when EMA 20 crosses above EMA 50, stop loss 2%", False)
    assert out["notes"] == ["Short selling on delivery isn't possible, so only longs are tested."]
    assert "tgt" not in out.get("risk", {})
    assert "Never invent exits, stops or targets" in ai_writer.SYSTEM
