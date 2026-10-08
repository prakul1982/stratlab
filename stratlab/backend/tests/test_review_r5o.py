"""Round 5, the owner's review on the live site (8 Oct 2026): each test is built on the real example the reviewer saw."""
import json

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
