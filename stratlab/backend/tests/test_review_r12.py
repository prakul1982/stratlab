"""Round 12 review of the live site (9 Oct 2026), after PRs 178 and 179: the two data fixes that didn't act in production,
and the rest of the round.

R12-001: the public INFY high stayed ₹1,691.40 (traded 1,728.00) and ULTRACEMCO's range ₹10,118 to ₹12,848 (traded
10,325.00 to 13,110.00). Both fixes leant on the exchange's 52-week report, which production doesn't have (the exchange's
feed doesn't answer the server). The cause of the wrong figures is the broker's daily candles themselves: they are scaled
back for an extraordinary dividend (above 2% of the price), INFY's ₹25 of 10 Jun 2026 and ULTRACEMCO's ₹240 of 30 Jul
2026, so every candle before those days is about 2% low. The range is now worked out from the candles as traded.

The numbers are the live ones (the reviewer's bhavcopy rows, the dividends the price history lists); nothing is read from
the network and no clock matters: every day is fixed here."""
import json
from datetime import date, timedelta

import pytest

from app import main  # noqa: F401, I001  (first: the app loads the newsletter job before the modules built on it)
from app import official_close, screens, stock_alerts, stock_pages
from app.intel import company as company_mod
from app.intel import grounding, sec
from app.intel.company import Research
from app.intel.net import SourceError
from app.intel.news import company_headline, plain_headline
from app.intel.screener import fix_lender_margins
from tests.test_review_r10v import ctx, facts_page, instance, stat

INFY_EX, INFY_DIV, INFY_CUM = "2026-06-10", 25.0, 1180.30          # the dividend and the close the day before it went ex
ULTRA_EX, ULTRA_DIV, ULTRA_CUM = "2026-07-30", 240.0, 11998.00


def weekdays(first: str, last: str) -> list[str]:
    d, end, out = date.fromisoformat(first), date.fromisoformat(last), []
    while d <= end:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def traded_year(base: float, prints: dict[str, tuple[float, float, float]], first="2025-10-01", last="2026-10-09") -> list[dict]:
    """A year of daily candles as the exchange printed them: a flat `base`, with the given days' (high, low, close)."""
    out = []
    for d in weekdays(first, last):
        h, lo, c = prints.get(d, (base * 1.01, base * 0.99, base))
        out.append({"t": f"{d}T00:00:00+05:30", "o": c, "h": h, "l": lo, "c": c, "v": 1000.0})
    return out


def broker(bars: list[dict], ex: str, div: float, tick: float = 0.1) -> list[dict]:
    """The broker's copy: every candle before the ex-date scaled by (P - D) / P and rounded to its tick."""
    i = next(k for k, b in enumerate(bars) if b["t"][:10] >= ex)
    f = 1 - div / bars[i - 1]["c"]
    rnd = lambda v: round(round(v * f / tick) * tick, 2)      # noqa: E731
    return [{**b, **{k: rnd(b[k]) for k in ("o", "h", "l", "c")}} if j < i else dict(b) for j, b in enumerate(bars)]


def infy() -> list[dict]:
    return traded_year(1300.0, {"2026-02-03": (1728.0, 1653.0, 1656.0), "2026-06-09": (1190.0, 1170.0, INFY_CUM),
                                "2026-09-29": (1000.0, 980.40, 990.0), "2026-10-09": (1030.0, 1015.0, 1023.40)})


def ultracemco() -> list[dict]:
    return traded_year(11800.0, {"2026-02-10": (13110.0, 12968.0, 13023.0), "2026-03-23": (10877.0, 10325.0, 10362.0),
                                 "2026-07-29": (12050.0, 11900.0, ULTRA_CUM), "2026-10-09": (10700.0, 10550.0, 10675.0)})


# ---------- R12-001: the range from the candles as traded, with no exchange report ----------
def test_the_brokers_candles_are_two_percent_low_before_an_extraordinary_dividend():
    kite = broker(infy(), INFY_EX, INFY_DIV)
    assert stock_pages.year_low_high(kite) == (980.4, 1691.4)              # what the public page showed
    lo, hi = stock_pages.year_low_high(stock_pages.as_traded(kite, [{"date": INFY_EX, "amount": INFY_DIV}]))
    assert (lo, hi) == (980.4, 1728.0)
    ultra = broker(ultracemco(), ULTRA_EX, ULTRA_DIV, tick=1.0)
    assert stock_pages.year_low_high(ultra) == (10118.0, 12848.0)           # no session printed either
    lo, hi = stock_pages.year_low_high(stock_pages.as_traded(ultra, [{"ex_date": ULTRA_EX, "amount": ULTRA_DIV, "kind": "dividend"}]))
    # the broker rounds its scaled prices, so on its own the undone figure is within a tick or so of the print...
    assert abs(lo - 10325.0) <= 1.0 and abs(hi - 13110.0) <= 1.0
    # ...and another source's candles as traded give the print itself, where its close agrees with the undone one
    ref = ultracemco()
    got = stock_pages.as_traded(ultra, [{"date": ULTRA_EX, "amount": ULTRA_DIV}], reference=lambda: ref)
    assert stock_pages.year_low_high(got) == (10325.0, 13110.0)
    assert ultra[0]["h"] != ref[0]["h"] and got is not ultra                 # the candles given are not changed


def test_an_ordinary_dividend_is_not_undone_and_nothing_is_read_for_it():
    # TITAN's ₹15 of 9 Jul 2026 was 0.33% of its price: the broker didn't scale for it, so neither does the page
    bars = traded_year(4400.0, {"2026-07-08": (4600.0, 4570.0, 4586.40)})
    asked = []
    out = stock_pages.as_traded(bars, [{"date": "2026-07-09", "amount": 15.0}], reference=lambda: asked.append(1) or [])
    assert out is bars and not asked
    # a dividend after the last candle, or before the first, has nothing to undo
    assert stock_pages.as_traded(bars, [{"date": "2026-12-01", "amount": 900.0}, {"date": "2020-01-01", "amount": 900.0}]) is bars
    assert stock_pages.as_traded(bars, []) is bars and stock_pages.as_traded([], [{"date": "2026-07-09", "amount": 1}]) == []
    # a split or bonus in the corporate actions list is not a dividend
    assert stock_pages.dividend_list([{"kind": "split", "ex_date": "2026-07-09", "amount": 5}, {"kind": "dividend", "ex_date": "2026-07-09"}]) == []


def test_a_reference_that_cant_be_read_or_disagrees_leaves_the_undone_candles():
    ultra = broker(ultracemco(), ULTRA_EX, ULTRA_DIV, tick=1.0)
    divs = [{"date": ULTRA_EX, "amount": ULTRA_DIV}]

    def down():
        raise SourceError("x", "down")
    lo, hi = stock_pages.year_low_high(stock_pages.as_traded(ultra, divs, reference=down))
    assert abs(hi - 13110.0) <= 1.0
    other = [{**b, "h": b["h"] * 3, "l": b["l"] * 3, "c": b["c"] * 3, "o": b["o"] * 3} for b in ultracemco()]   # another listing
    lo, hi = stock_pages.year_low_high(stock_pages.as_traded(ultra, divs, reference=lambda: other))
    assert abs(hi - 13110.0) <= 1.0


@pytest.fixture
def no_exchange_report(monkeypatch):
    """Production as it is: the exchange's feed doesn't answer the server, so no 52-week report is stored."""
    monkeypatch.setattr(official_close, "ranges", lambda: None)
    monkeypatch.setattr(official_close, "overlay_bars", lambda bars, sym, *a, **k: bars)


def _page_bars(monkeypatch, kite: list[dict], divs: list[dict], reference=None):
    class Prov:
        def history(self, inst, tf, days, ttl=None):
            return [dict(b) for b in kite]
    monkeypatch.setattr(main.universes, "resolve", lambda markets, region, rows: (["IN:X"], None))
    monkeypatch.setattr(main.markets, "resolve", lambda i: (Prov(), {"symbol": "X"}))
    monkeypatch.setattr(main, "india_page_dividends", lambda sym, co, fetch=True, listed=None: divs)

    def chart(symbol, tf="1d", days=365, ttl=None, exact=False):
        if reference is None:
            raise SourceError("x", "not reachable")
        return {"meta": {}, "candles": reference}
    monkeypatch.setattr(main.research_hub.yahoo, "chart", chart)


def test_the_public_pages_range_is_right_with_no_exchange_report(monkeypatch, no_exchange_report):
    assert official_close.ranges() is None
    _page_bars(monkeypatch, broker(infy(), INFY_EX, INFY_DIV), [{"date": INFY_EX, "amount": INFY_DIV}])
    bars = main.stock_page_bars("IN", {"sym": "INFY", "bse": None, "name": "Infosys"})
    f = stock_pages.price_facts(bars)
    assert (f["low52"], f["high52"], f["price"]) == (980.4, 1728.0, 1023.4)
    # served through the stored-page path with its serve-time adjustment, which has no report to take in: unchanged
    page = {**facts_page("Mar 2026"), "region": "IN", "symbol": "INFY", "currency": "INR", **{k: f[k] for k in ("low52", "high52", "price")}}
    assert main.stock_page_store.adjust("IN", "INFY", page) is page
    html = stock_pages.render(page, "IN", "INFY", "Infosys")
    assert stat(html, "1-year range (intraday)") == "₹980.40 to ₹1,728.00"


def test_ultracemcos_public_range_is_the_exchanges_print_with_no_report(monkeypatch, no_exchange_report):
    _page_bars(monkeypatch, broker(ultracemco(), ULTRA_EX, ULTRA_DIV, tick=1.0), [{"date": ULTRA_EX, "amount": ULTRA_DIV}],
               reference=ultracemco())
    f = stock_pages.price_facts(main.stock_page_bars("IN", {"sym": "ULTRACEMCO", "bse": None, "name": "UltraTech Cement"}))
    assert (f["low52"], f["high52"]) == (10325.0, 13110.0)


def test_stored_indian_pages_from_before_are_built_again():
    # every page stored before (FACTS_VERSION 7 and older) had its range from the scaled candles: rebuilt when next opened,
    # and the screens' indexer rebuilds the largest first
    assert stock_pages.FACTS_VERSION == 8
    old = {"ts": 1e12, "price_ts": 1e12, "facts": {**facts_page("Mar 2026", v=7), "region": "IN"}}
    assert not stock_pages.fresh(old, "IN", now=1e12 + 60)


def _owner_company(monkeypatch, k1y: list[dict], divs: list[dict], reference=None) -> dict:
    class Kite:
        def equity(self, s):
            return {"symbol": s, "exchange": "NSE", "token": 1, "type": "EQ", "name": s, "id": f"IN:{s}"}

    class Yahoo:
        def chart(self, symbol, tf="1d", days=365, ttl=None, exact=False):
            if reference is None:
                raise SourceError("x", "not reachable")
            return {"meta": {}, "candles": reference}
    hub = Research.__new__(Research)
    hub.kite, hub.yahoo = Kite(), Yahoo()
    monkeypatch.setattr(hub, "_kite", lambda: True, raising=False)
    monkeypatch.setattr(hub, "_run", lambda tasks: ({"kq": {"price": k1y[-1]["c"]}, "k1y": k1y}, []), raising=False)
    monkeypatch.setattr(company_mod, "_stored_dividends_in", lambda sym: divs)
    return hub._company_in("INFY", lean=True)


def test_the_app_and_the_public_page_give_one_range(monkeypatch, no_exchange_report):
    kite = broker(infy(), INFY_EX, INFY_DIV)
    c = _owner_company(monkeypatch, kite, [{"ex_date": INFY_EX, "amount": INFY_DIV, "kind": "dividend"}])
    assert c["range52"] == {"low": 980.4, "high": 1728.0}
    _page_bars(monkeypatch, kite, [{"date": INFY_EX, "amount": INFY_DIV}])
    f = stock_pages.price_facts(main.stock_page_bars("IN", {"sym": "INFY", "bse": None, "name": "Infosys"}))
    assert (f["low52"], f["high52"]) == (c["range52"]["low"], c["range52"]["high"])


# ---------- R12-003: one 365-day window everywhere ----------
def titan() -> list[dict]:
    # 6 Oct 2025's low of 3,401.00 is 368 days before 9 Oct 2026; 14 Oct 2025's 3,506.50 is the year's. The exchange shuts on
    # about 16 weekdays a year, so 252 sessions reach back past a year
    prints = {"2025-10-06": (3480.0, 3401.0, 3450.0), "2025-10-14": (3560.0, 3506.50, 3540.0),
              "2026-08-27": (5186.70, 5100.0, 5150.0), "2026-10-09": (4430.70, 4360.20, 4410.0)}
    bars = traded_year(4400.0, prints)
    return [b for i, b in enumerate(bars) if i % 16 != 9 or b["t"][:10] in prints]


def test_titans_low_is_the_365_day_one_in_the_app_and_on_the_public_page(monkeypatch, no_exchange_report):
    bars = titan()
    assert min(b["l"] for b in bars[-252:]) == 3401.0                        # the last 252 candles reach 368 days back
    assert stock_pages.year_low_high(bars) == (3506.5, 5186.7)
    assert stock_pages.price_facts(bars)["low52"] == 3506.5
    c = _owner_company(monkeypatch, bars, [])
    assert c["range52"] == {"low": 3506.5, "high": 5186.7}


def test_the_52_week_alerts_use_the_same_window():
    bars = titan()[:-1]                                                      # the candles before today, 9 Oct 2026
    year = stock_alerts._prior_year(bars, "2026-10-09", "Asia/Kolkata")
    assert min(b["l"] for b in year) == 3506.5 and year[0]["t"][:10] == "2025-10-10"


# ---------- R12-002: a bank's financing margin ----------
ICICI = {"cols": ["Sep 2024", "Dec 2024", "Mar 2025", "Jun 2025", "Sep 2025", "Dec 2025", "Mar 2026", "Jun 2026"],
         "sales": [46326, 47037, 48387, 49080, 48181, 48364, 49594, 52241],
         "profit": [13906, 13847, 14354, 14456, 14318, 13481, 15681, 16276],
         "opm": [-18, -19, -25, -12, -18, -22, -29, -12]}
HDFC_OPM = [-17, -4, -9, -28, -6, -15, -2, -17]


def consolidated_bank(sales, profit, opm) -> dict:
    """A bank's quarters as the source gives them for consolidated accounts: the financing profit is revenue less interest
    less expenses, and the group's insurers' costs are in the expenses while their income is in other income, so the profit
    before tax is the financing profit plus other income exactly (why PR 178's check accepted the negative figure)."""
    fp = [round(m * s / 100) for m, s in zip(opm, sales)]
    pbt = [round(p / 0.75) for p in profit]
    return {"quarters": {"cols": ICICI["cols"], "rows": {
        "Revenue": [float(s) for s in sales], "Interest": [s * 0.48 for s in sales], "Expenses": [s - s * 0.48 - f for s, f in zip(sales, fp)],
        "Financing Profit": [float(f) for f in fp], "Financing Margin %": list(opm), "Other Income": [float(b - f) for b, f in zip(pbt, fp)],
        "Profit before tax": [float(b) for b in pbt], "Net Profit": [float(p) for p in profit]}}}


def test_icici_banks_live_quarters_show_no_negative_financing_margin():
    p = consolidated_bank(ICICI["sales"], ICICI["profit"], ICICI["opm"])
    fix_lender_margins(p)
    rows = p["quarters"]["rows"]
    assert rows["Financing Margin %"] == [None] * 8 and rows["Financing Profit"] == [None] * 8
    hdfc = consolidated_bank(ICICI["sales"], ICICI["profit"], HDFC_OPM)
    fix_lender_margins(hdfc)
    assert hdfc["quarters"]["rows"]["Financing Margin %"] == [None] * 8


def test_a_positive_margin_stays_and_a_loss_making_lenders_negative_one_too():
    axis = consolidated_bank(ICICI["sales"], ICICI["profit"], [5, 6, 0, 7, 5, 6, 0, 7])
    fix_lender_margins(axis)
    assert axis["quarters"]["rows"]["Financing Margin %"] == [5, 6, 0, 7, 5, 6, 0, 7]
    losing = consolidated_bank(ICICI["sales"], [-500] * 8, [-3] * 8)        # a loss: a negative margin beside it is no contradiction
    fix_lender_margins(losing)
    assert losing["quarters"]["rows"]["Financing Margin %"] == [-3] * 8


def test_the_company_page_hides_the_row_when_no_quarter_has_a_margin(monkeypatch):
    from app.intel import screener as S
    page = {"ratios": {"Current Price": "1,355"}, "pl": None, **consolidated_bank(ICICI["sales"], ICICI["profit"], ICICI["opm"])}
    monkeypatch.setattr(S.Screener, "fetch", lambda self, path, ttl=0, kind="json": "<h1>x</h1><div class='top-ratios'></div>")
    monkeypatch.setattr(S, "parse", lambda html: json.loads(json.dumps(page)))
    got = S.Screener()._page("/company/ICICIBANK/consolidated/")
    assert got["quarters"]["rows"]["Financing Margin %"] == [None] * 8
    # the page's own rule (Research.tsx): a "Financing margin" row whose every cell is empty is left out
    src = open(main.__file__.replace("backend/app/main.py", "frontend/src/components/Research.tsx"), encoding="utf-8").read()
    assert 'r.name === "Financing margin" && r.cells.every((c) => c === "–")' in src


# ---------- R12-004: one plain-headline rule for company news and the Pulse feed ----------
BLOCKED = [
    "Nvidia Has Already Made Investors Rich. Here's Where the Stock Could Be Headed Next",
    "Prediction: A $5,000 Investment Split Between Nvidia and Broadcom Will Triple by 2028",
    "Nvidia and AMD Lead the AI Market. 1 Chip Stock Has Far Greater Upside.",
    "Is Nvidia Stock a Bargain or Warning?",
    "Nutanix Nears Buy Point",
    "Are You Overpaying For Microsoft Stock Versus Its Rivals?",
    "Starbucks Turnaround: Smart Move or Costly Gamble?",
    "5 Milestones Show What Buying Into Hype Costs You",
    "My Position on Tesla Will Not Change Until Two Things Happen",
    "HDFC Bank Share Price Breakout Below Support Level",
    "HDFC Bank shares slip; what charts say?",
    "Jim Cramer sets a Starbucks buy level — plus his take on 3 stocks we just bought",
    "Stocks to watch: HDFC Bank, Infosys, TCS",
]
PLAIN = [
    "Nvidia shares rise 3% after record data-centre revenue",
    "Apple unveils new iPhone at September event",
    "HDFC Bank Q2 net profit rises 12% to ₹18,000 crore",
    "Sensex ends 300 points higher as IT stocks gain",
    "Tesla deliveries rise 8% in the third quarter",
    "Starbucks to close 200 stores in North America",
    "Markets rally on bargain hunting in banks",
    "Inflation's upside surprise pushes bond yields higher",
    "Kalshi says prediction markets volume doubled",
]


def test_advice_and_prediction_headlines_are_left_out_and_plain_ones_stay():
    for h in BLOCKED:
        assert not plain_headline(h), h
    for h in PLAIN:
        assert plain_headline(h), h


def test_company_news_must_name_the_company_in_the_headline():
    assert not company_headline("Apple Inc", "AAPL", "Are You Overpaying For Microsoft Stock Versus Its Rivals?")
    assert not company_headline("Apple Inc", "AAPL", "Microsoft's cloud revenue climbs 30%")         # Apple only in the summary
    assert company_headline("Apple Inc", "AAPL", "Apple unveils new iPhone at September event")
    assert company_headline("HDFC Bank Ltd", "HDFCBANK", "HDFC Bank Q2 net profit rises 12% to ₹18,000 crore")
    assert not company_headline("HDFC Bank Ltd", "HDFCBANK", "HDFC Bank Share Price Breakout Below Support Level")
    # both markets' company news and Pulse's feed go through the one rule
    src = open(company_mod.__file__, encoding="utf-8").read()
    assert src.count("company_headline(") >= 1 and 'mentions(p["name"], sym, n["headline"])][:8]' in src
    assert "mentions(p[\"name\"], sym, str(n.get(\"summary\")" not in src


def test_pulse_headlines_and_the_mood_never_carry_a_buy_level():
    class News:
        def search(self, q, region, limit=20):
            return [{"headline": h, "url": "", "source": "x", "at": None} for h in BLOCKED + PLAIN]
    hub = Research.__new__(Research)
    hub.news = News()

    class NoFinnhub:
        def ready(self):
            return False
    hub.finnhub = NoFinnhub()
    got = [h["headline"] for h in hub.headlines("US")]
    assert got and not set(got) & set(BLOCKED)
    # the mood read is grounded against its own words too: a sentence repeating a buy level is dropped
    text = "Stocks closed higher. Jim Cramer set a buy level for Starbucks and shared his take on three stocks."
    assert grounding.keep_sentences(text, []) == "Stocks closed higher."


# ---------- R12-005: BP's market cap, and the item always there ----------
def test_a_page_with_no_market_cap_always_shows_the_item_and_says_why():
    page = stock_pages.render(facts_page("Mar 2026", market_cap=None, pe=None), "US", "BP", None)
    assert stat(page, "Market cap") == "n/a" and "data-cap-missing" in page
    assert stock_pages.cap_missing_reason(facts_page("Mar 2026", market_cap=None, pe=None)) == "unknown"
    assert stock_pages.cap_missing_reason(facts_page("Mar 2026", market_cap=None, pe=None, price=None)) is None


BP_COVER = ('<dei:EntityCommonStockSharesOutstanding contextRef="o" unitRef="sh">16486312994</dei:EntityCommonStockSharesOutstanding>'
            '<dei:EntityCommonStockSharesOutstanding contextRef="p1" unitRef="sh">7232838</dei:EntityCommonStockSharesOutstanding>'
            '<ifrs-full:NumberOfSharesOutstanding contextRef="t" unitRef="sh">1109588000</ifrs-full:NumberOfSharesOutstanding>'
            '<ifrs-full:NumberOfSharesOutstanding contextRef="tp" unitRef="sh">857433000</ifrs-full:NumberOfSharesOutstanding>'
            '<ifrs-full:WeightedAverageShares contextRef="avg" unitRef="sh">15586782000</ifrs-full:WeightedAverageShares>')


def bp_contexts():
    cls, eq = "ifrs-full:ClassesOfShareCapitalAxis", "ifrs-full:ComponentsOfEquityAxis"
    return [ctx("o", None, "2025-12-31", (cls, "ifrs-full:OrdinarySharesMember")), ctx("p1", None, "2025-12-31", (cls, "bp:FirstPreferenceSharesMember")),
            ctx("t", None, "2025-12-31", (eq, "ifrs-full:TreasurySharesMember")), ctx("tp", None, "2025-12-31", (eq, "bp:TreasurySharesHeldByParentMember")),
            ctx("avg", "2025-01-01", "2025-12-31", (cls, "ifrs-full:OrdinarySharesMember"))]


def test_bps_cover_count_is_taken_net_of_its_treasury_shares():
    cs = sec.cover_shares(sec.instance(instance(BP_COVER, bp_contexts(), cur="USD")))
    assert cs == {"value": 16486312994.0, "end": "2025-12-31", "classes": 1, "treasury": 1109588000.0, "avg": 15586782000.0}
    p = sec.net_of_treasury({"shares": cs["value"], "shares_from": "cover", "avg_shares": cs["avg"]}, cs["treasury"])
    assert p["shares"] == 16486312994 - 1109588000 and p["shares_from"] == "cover net of treasury"
    # six ordinary shares to an ADS at $46.36: about $119B (the cover's issued count alone made $127B)
    cap = sec.market_value({**p, "ads_ratio": 6}, 46.36)
    assert 118_000 < cap < 120_000


# ---------- R12-006: a year an annual report gives in two parts ----------
def _part(start, end, val, accn="0001747079-26-000019", form="10-K", filed="2026-03-23"):
    return {"start": start, "end": end, "val": val, "accn": accn, "form": form, "filed": filed, "fy": 2025, "fp": "FY"}


def test_ballys_2025_split_at_its_change_of_control_is_one_year():
    revenue = [_part("2024-01-01", "2024-12-31", 2450478000, accn="0001747079-25-000039", filed="2025-03-17"),
               _part("2025-01-01", "2025-02-07", 220498000), _part("2025-02-08", "2025-12-31", 2436189000)]
    profit = [_part("2024-01-01", "2024-12-31", -567754000, accn="0001747079-25-000039", filed="2025-03-17"),
              _part("2025-01-01", "2025-02-07", -51024000), _part("2025-02-08", "2025-12-31", -650074000)]
    eps = [_part("2025-01-01", "2025-02-07", -0.8), _part("2025-02-08", "2025-12-31", -11.0)]
    facts = {"facts": {"us-gaap": {"RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"USD": revenue}},
                                   "NetIncomeLoss": {"units": {"USD": profit}},
                                   "EarningsPerShareBasic": {"units": {"USD/shares": eps}}}}}
    got = sec.flows(facts["facts"], ("RevenueFromContractWithCustomerExcludingAssessedTax",), "annual")
    assert got == {"2024-12-31": 2450478000.0, "2025-12-31": 220498000.0 + 2436189000.0}
    p = sec.build(facts, {"name": "Bally's Corp"})
    assert p["year_end"] == "2025-12-31" and p["pl"]["rows"]["Net Profit"][-1] == pytest.approx(-701.1, abs=0.1)
    # a per-share figure doesn't add up across two share counts: no year's earnings per share is made
    assert "2025-12-31" not in sec.flows(facts["facts"], ("EarningsPerShareBasic",), "annual", "USD/shares")
    # two parts from different filings, or with a gap between them, are not a year
    assert sec.split_years([_part("2025-01-01", "2025-02-07", 1, accn="a"), _part("2025-02-08", "2025-12-31", 2, accn="b")]) == {}
    assert sec.split_years([_part("2025-01-01", "2025-02-07", 1), _part("2025-03-08", "2025-12-31", 2)]) == {}


def test_a_page_still_behind_after_a_build_with_its_report_out_doesnt_hold_the_sweep(monkeypatch):
    filed = "2026-05-29"
    behind = facts_page("Mar 2025", annual_filed=filed)            # its newest year in the table ended over a year before the filing
    filed_ts = 1780012800.0                                         # 29 May 2026 00:00 UTC
    assert stock_pages.behind_due(behind, ts=filed_ts - 86400, now=filed_ts + 30 * 86400)          # built before the report
    assert not stock_pages.behind_due(behind, ts=filed_ts + 10 * 86400, now=filed_ts + 12 * 86400)  # built after it: wait
    assert stock_pages.behind_due(behind, ts=filed_ts + 10 * 86400, now=filed_ts + 18 * 86400)      # a week on: try again
    assert not stock_pages.behind_due(facts_page("Mar 2026", annual_filed=filed), ts=0, now=filed_ts)
    # in the screens' sweep: the page still behind after a recent build is no longer put before every other one
    from app import db
    import time as _time
    now = _time.time()
    # BALY: built an hour ago, its report filed 200 days ago and still not a year in its table; SIM: built long before its report
    long_ago = (date.fromtimestamp(now) - timedelta(days=200)).isoformat()
    store = {"stocks:page:US:BALY": json.dumps({"ts": now - 3600, "facts": facts_page("Mar 2023", annual_filed=long_ago, market_cap=5_000.0)}),
             "stocks:page:US:SIM": json.dumps({"ts": 1.0, "facts": facts_page("Mar 2025", annual_filed="2026-07-31", market_cap=10.0)}),
             "stocks:page:US:OLD": json.dumps({"ts": 1.0, "facts": facts_page("Mar 2026", v=7, market_cap=900_000.0)})}
    monkeypatch.setattr(db, "all_settings_with_prefix", lambda p, *a: [(k, v) for k, v in store.items() if k.startswith(p)])
    monkeypatch.setattr(db, "set_setting", lambda k, v: None)
    monkeypatch.setattr(stock_pages, "nse_twins", lambda: {})
    index = screens.build_index("US", store=False)
    order = sorted(index["_old"], key=lambda s: -index["_old"][s])
    assert order == ["SIM", "OLD"] and "BALY" not in index["_old"]


# ---------- R12-007: share counts and one period per figure ----------
def _shares_facts(cover: float, year_end_held: float, avg: float, profit: float, eps: float) -> dict:
    y = lambda v: [{"start": "2025-01-01", "end": "2025-12-31", "val": v, "form": "10-K", "filed": "2026-03-26", "fp": "FY",   # noqa: E731
                    "accn": "0001193125-26-126368"}]
    return {"facts": {"us-gaap": {"Revenues": {"units": {"USD": y(50e6)}}, "NetIncomeLoss": {"units": {"USD": y(profit)}},
                                  "EarningsPerShareBasic": {"units": {"USD/shares": y(eps)}},
                                  "WeightedAverageNumberOfSharesOutstandingBasic": {"units": {"shares": y(avg)}},
                                  "CommonStockSharesOutstanding": {"units": {"shares": [{"end": "2025-12-31", "val": year_end_held, "filed": "2026-03-26", "form": "10-K"}]}}},
                      "dei": {"EntityCommonStockSharesOutstanding": {"units": {"shares": [{"end": "2026-03-23", "val": cover, "filed": "2026-03-26", "form": "10-K"}]}}}}}


def test_libertys_count_is_its_cover_pages_not_the_years_average():
    # LBRX: most of its shares were issued during 2025, so the year's earnings imply the average, 8.0M, against 25.3M at the
    # year's end and 28.7M on the cover page
    p = sec.build(_shares_facts(28_674_827, 25_299_372, 8_045_145, -25_200_000, -3.13))
    assert p["shares"] == 28_674_827 and p["shares_from"] == "cover"
    # a thousandfold count stays caught, whatever the balance sheet says (Bradesco)
    bad = sec.build(_shares_facts(8_045_145_000, 8_045_145_000, 8_045_145, 25_200_000, 3.13))
    assert bad["shares"] == pytest.approx(25_200_000 / 3.13, rel=1e-6)


def test_a_cover_page_per_class_counts_every_class():
    cover = ('<dei:EntityCommonStockSharesOutstanding contextRef="a" unitRef="sh">76904346</dei:EntityCommonStockSharesOutstanding>'
             '<dei:EntityCommonStockSharesOutstanding contextRef="b" unitRef="sh">31171134</dei:EntityCommonStockSharesOutstanding>')
    ax = "us-gaap:StatementClassOfStockAxis"
    cs = sec.cover_shares(sec.instance(instance(cover, [ctx("a", None, "2026-08-10", (ax, "us-gaap:CommonClassAMember")),
                                                       ctx("b", None, "2026-08-10", (ax, "us-gaap:CommonClassBMember"))], cur="USD")))
    assert cs["value"] == 76904346 + 31171134 and cs["classes"] == 2
    # a filing whose company facts have no cover count at all is marked, so the newest report's per-class cover is read
    assert sec.build(_shares_facts(1, 1, 1, 1, 1) | {"facts": {"us-gaap": _shares_facts(1, 1, 1, 1, 1)["facts"]["us-gaap"]}})["no_cover_count"]


def test_the_key_figures_beside_the_last_twelve_months_name_their_year():
    # KPLT: "Net profit, last 12 months $16M" and "P/E 1.4" are the twelve months'; the net margin was its year to Dec 2025's
    f = facts_page("Dec 2025", profit_ttm=16.19, years=[{"year": "Dec 2025", "sales": 270.0, "profit": 1.36, "opm": 5.0, "debt": 1.0}],
                   net_margin=0.5, opm=5.0, pe_basis="ttm", foreign=False)
    page = stock_pages.render(f, "US", "KPLT", None)
    assert stat(page, "Net margin (year to Dec 2025)") == "0.5%" and stat(page, "EBITDA margin (year to Dec 2025)") == "5.0%"
    assert stat(page, "Net profit, last 12 months (INR million)") == "16"
    # without a twelve months' figure on the page there is nothing to tell apart: the plain labels
    plain = stock_pages.render(facts_page("Mar 2026"), "US", "RDY", None)
    assert stat(plain, "Net margin") == "17.4%"


# ---------- R12-013: no fund in the sitemap ----------
def test_a_page_whose_build_couldnt_tell_a_fund_from_a_company_is_not_in_the_sitemap(monkeypatch):
    assert stock_pages.sitemap_ok(facts_page("Mar 2026"))
    assert not stock_pages.sitemap_ok(facts_page("Mar 2026", type_unread=True))
    assert not stock_pages.sitemap_ok(facts_page("Mar 2026", not_company="a fund"))
    from app import db
    store = {"stocks:page:US:GSMT": json.dumps({"ts": 1.0, "facts": facts_page("Mar 2026", symbol="GSMT", type_unread=True)}),
             "stocks:page:US:AAPL": json.dumps({"ts": 1.0, "facts": facts_page("Mar 2026", symbol="AAPL")})}
    saved = {}
    monkeypatch.setattr(db, "all_settings_with_prefix", lambda p, *a: [(k, v) for k, v in store.items() if k.startswith(p)])
    monkeypatch.setattr(db, "set_setting", lambda k, v: saved.__setitem__(k, v))
    monkeypatch.setattr(stock_pages, "nse_twins", lambda: {})
    screens.build_index("US", store=True)
    built = json.loads(saved[stock_pages.BUILT_KEY + "US"])
    assert built["shown"] == ["AAPL"] and set(built["pages"]) == {"AAPL", "GSMT"}
    # ...and such a page is built again within the hour when opened, like one whose annual report couldn't be read
    stored = {"ts": 1e12, "price_ts": 1e12, "facts": facts_page("Mar 2026", type_unread=True)}
    assert not stock_pages.fresh(stored, "US", now=1e12 + stock_pages.UNREAD_FRESH + 5)
