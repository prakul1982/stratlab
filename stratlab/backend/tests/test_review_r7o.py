"""Round 7, the owner's review on the live site (9 Oct 2026): each test is built on the real example the reviewer saw."""
import json
from datetime import date, datetime, timedelta, timezone

import pytest

from app import main  # noqa: F401, I001  (first: the app loads the newsletter job before the modules built on it)
from app import admin_jobs, ai_rank, db, etf_nav, library, money_networth, official_close, pricing, redflags as R, screens, stock_pages
from app.intel import ai as A, company as C, grounding as G, news as N, routes as research_routes
from app.intel import filings as F
from app.newsletter import content, job as news_job, write
from tests import world

IST = timezone(timedelta(hours=5, minutes=30))


@pytest.fixture
def mem(monkeypatch):
    """The settings table in memory, for the modules that keep their state there."""
    store: dict = {}
    monkeypatch.setattr(db, "get_setting", lambda k: store.get(k))
    monkeypatch.setattr(db, "set_setting", lambda k, v: store.__setitem__(k, v))
    monkeypatch.setattr(db, "delete_setting", lambda k: store.pop(k, None))
    monkeypatch.setattr(db, "all_settings_with_prefix", lambda p: [(k, v) for k, v in sorted(store.items()) if k.startswith(p)])
    R.forget()
    official_close.forget()
    etf_nav.forget()
    yield store
    R.forget()
    official_close.forget()


@pytest.fixture
def w(monkeypatch):
    built = world.build(monkeypatch)
    yield built
    built["close"]()


# ---------- R7O-001: the ICICIBANK AI read ----------
ICICI_READ = {
    "summary": "ICICI Bank is an Indian multinational private bank. The company has reported a net profit of ₹57936.0 crore in the "
               "latest fiscal year, FY26. Its stock price has decreased by 0.6261510128913406% on the day, with a 52-week range of ₹1187.6 to ₹1480.0.",
    "valuation_note": "The company's current P/E ratio is 17.2, with a P/B ratio of 2.55977229601518 and a dividend yield of 0.89.",
    "bull": ["Net profit has grown at a 3-year CAGR of 17.8%"],
    "bear": ["The company's EBITDA margin is -20.0%",
             "The company's debt is not explicitly stated, but its financial health can be affected by various market and economic factors",
             "The banking sector is highly competitive and regulated"],
    "position": "", "watch": ["The next results date is 2026-10-17"],
    "ideas": [
        {"title": "Mean Reversion Strategy", "text": "Enter long when the stock price crosses above its 50-day SMA, exit when it crosses below its 200-day SMA, 5% stop loss",
         "why": "The stock price has been below its 50-day average, and mean reversion strategies can be effective in such cases"},
        {"title": "Trend Following Strategy", "text": "Enter long when the 20-day EMA crosses above the 50-day EMA, exit when it crosses back below, 5% stop loss",
         "why": "The company's net profit has been growing at a high rate, and trend following strategies can be effective in such cases"},
        {"title": "Breakout Strategy", "text": "Enter long when the stock price crosses above its 52-week high, exit when it crosses below its 52-week low, 5% stop loss",
         "why": "The stock price has been range-bound, and breakout strategies can be effective when the price breaks out of its range"},
    ],
}


def test_the_icicibank_read_is_written_the_pages_way_and_holds_nothing_a_bank_has_not():
    out = G.polish_company(ICICI_READ, "IN", lender=True)
    assert "0.63%" in out["summary"] and "0.6261510128913406" not in out["summary"]
    assert "₹57,936 crore" in out["summary"] and "₹1,187.60" in out["summary"]
    assert "2.56" in out["valuation_note"] and "2.55977229601518" not in out["valuation_note"]
    assert out["bear"] == []                                   # EBITDA for a bank, "not explicitly stated" filler, "highly competitive"
    assert [i["title"] for i in out["ideas"]] == ["Trend Following Strategy", "Breakout Strategy"]   # the "mean reversion" crossover goes
    assert all(i["why"] == "" for i in out["ideas"])           # "... can be effective in such cases" is never kept


def test_a_kept_read_from_before_the_checks_gets_them_as_it_is_served():
    stored = {**ICICI_READ, "lender": True, "region": "IN", "facts": [{"label": "Margins and returns", "items": [{"label": "EBITDA margin, 5 years", "text": "x"}]}]}
    out = A.clean_company(stored)
    assert "0.6261510128913406" not in out["summary"] and out["bear"] == [] and out["facts"] == []
    assert len(out["ideas"]) == 2


def test_the_bank_page_has_no_ebitda_margin_and_the_model_gets_page_figures():
    scr = {"pl": {"cols": ["Mar 2026"], "rows": {"Revenue": [195218], "Financing Profit": [-39000], "Net Profit": [57936]}}}
    assert C.is_lender(scr) and C.is_lender(None, "Banking") and not C.is_lender({"pl": {"rows": {"Sales": [1]}}}, "Technology")
    c = {"region": "IN", "symbol": "ICICIBANK", "name": "ICICI Bank Ltd", "currency": "INR", "bank": True, "market_cap": 9.68e12,
         "quote": {"price": 1349.0, "change_pct": -0.6261510128913406}, "range52": {"low": 1187.6, "high": 1480.0},
         "metrics": [{"title": "Valuation", "items": [{"label": "P/B", "value": 2.55977229601518, "unit": "x"},
                                                      {"label": "Div yield", "value": 0.8895, "unit": "%"}]}]}
    f = A.company_facts(c)
    assert f["day_change_pct"] == -0.63 and f["metrics"]["Valuation: P/B"] == 2.56 and f["metrics"]["Valuation: Div yield"] == "0.9%"
    assert f["market_cap"] == "₹9.68 lakh crore" and "lender" in f


def test_two_holder_classes_that_offset_are_named_as_a_class_move():
    rows = [{"label": "FIIs", "value": 33.8, "change": -13.0}, {"label": "DIIs", "value": 42.3, "change": -1.6},
            {"label": "Public", "value": 23.7, "change": 14.6}]
    note = C.class_move_note(rows)
    assert note and note.startswith("FIIs −13.0 and Public +14.6") and "depositary" in note
    assert C.class_move_note([{"label": "FIIs", "value": 20, "change": -6.0}, {"label": "Public", "value": 30, "change": 1.0}]) is None


# ---------- R7O-002: comparisons only with figures the page shows ----------
@pytest.mark.parametrize("sentence,kept", [
    ("P/E is 14.6, near the lower end of its historical 15-20 range.", False),
    ("P/B 6.31 is high relative to peers.", False),
    ("The P/E of 39.02 is higher than its multi-year average of roughly 30.", False),
    ("Valuation looks elevated relative to peers and well above historical levels.", False),
    ("The price is 3.2% below its 50-day average.", True),
    ("The P/E is 14.6 and the dividend yield is 5.35%.", True),
])
def test_a_comparison_needs_a_figure_on_the_page(sentence, kept):
    assert G.plain_ok(sentence) is kept


def test_a_comparison_read_is_held_to_both_pages(monkeypatch):
    a = {"region": "IN", "symbol": "TCS", "name": "TCS", "metrics": [], "quote": {"price": 2076.0}}
    b = {"region": "IN", "symbol": "INFY", "name": "Infosys", "metrics": [], "quote": {"price": 997.0}}
    monkeypatch.setattr(A, "_ask", lambda *x, **k: {"verdict": "TCS trades at 2076 and Infosys at 997. TCS is cheaper than its peers at 12.5 times.",
                                                     "differences": ["TCS at 2076 against Infosys at 997", "A historical premium of 40%"]})
    out = A.compare(a, b, (None, None))
    assert out["verdict"] == "TCS trades at 2076 and Infosys at 997." and out["differences"] == ["TCS at 2076 against Infosys at 997"]


# ---------- R7O-003: red flags under today's rules, stored rows too ----------
FIVE = [("MOL", "Amalgamation/Merger", "insolvency"), ("POLYCAB", "Corporate Insolvency Resolution Process", "insolvency"),
        ("ICICIBANK", "Certificate under SEBI (Depositories and Participants) Regulations, 2018", "ncd"),
        ("RAYMONDREL", "General Updates", "preferential"), ("TITAN", "Updates", "ncd")]


def _row(sym, subject, cat, text=None):
    r = {"id": f"{sym}|2026-10-08T18:00|x", "symbol": sym, "company": f"{sym} Ltd", "at": "2026-10-08T18:00", "category": cat,
         "label": F.LABEL[cat], "severity": "red" if cat != "ncd" else "amber", "subject": subject, "url": None}
    return {**r, "text": text} if text is not None else r


def test_the_five_rows_the_owner_saw_are_routine_even_stored_without_a_summary():
    rows = [_row(*x) for x in FIVE] + [_row("BHAGYANGR", "Resignation of Director/KMP/SMP", "kmp_resign"), _row("ABC", "x", "auditor_resign")]
    shown = R.current("IN", rows)
    assert sorted(r["symbol"] for r in shown) == ["ABC", "BHAGYANGR"]      # a subject no rule reads keeps its label
    with_text = [_row("POLYCAB", FIVE[1][1], "insolvency", "Polycab India Limited has informed the Exchange regarding Corporate Insolvency Resolution Process"),
                 _row("MOL", FIVE[0][1], "insolvency", "The NCLT has sanctioned the Scheme of Amalgamation of the wholly owned subsidiary with the Company")]
    assert R.current("IN", with_text) == []


def test_the_stored_list_is_rewritten_under_new_rules_once_without_a_source_read(mem):
    R.flags.add("IN", [_row(*x) for x in FIVE] + [_row("BGR", "Resignation of the Statutory Auditor", "auditor_resign")])
    R._set_state("IN", through="2026-10-08", rules=F.RULES_VERSION - 1)
    assert R.reclassify_stored("IN", date(2026, 10, 9)) == 5
    left = json.loads(mem["redflags:IN:2026-10"])["items"]
    assert [r["symbol"] for r in left] == ["BGR"]
    assert R.reclassify_stored("IN", date(2026, 10, 9)) == 0                 # once per rules version


def test_new_rules_are_read_again_at_once_not_at_the_evening_run(mem, monkeypatch):
    monkeypatch.setattr("app.data.calendar.is_trading_day", lambda market, d: True)

    class Runner:
        runs: list = []

        def run(self, region):
            self.runs.append(region)
            R._set_state(region, through="2026-10-08", at="2026-10-09T05:00:00+00:00", rules=F.RULES_VERSION)
            return {"ok": True}
    R._set_state("IN", through="2026-10-08", at="2026-10-08T15:30:00+00:00", rules=F.RULES_VERSION - 1)
    R._set_state("US", through="2026-10-08", at="2026-10-08T23:30:00+00:00")
    job = R.Job(Runner())
    job.last["redflags-IN-filled"] = job.last["redflags-US-filled"] = "1"
    noon = datetime(2026, 10, 9, 6, 30, tzinfo=timezone.utc)                  # 12:00 IST: hours before the 21:00 run
    assert job.tick(noon) == 1 and Runner.runs == ["IN"]
    assert job.tick(noon + timedelta(minutes=5)) == 0                         # done: the stored list carries the rules now


def test_a_rebuild_cut_short_carries_on_from_where_it_stopped(mem):
    from app.intel.net import SourceError
    asked, failed = [], []

    class Feed:
        def market_flags(self, day):
            asked.append(day.isoformat())
            if len(asked) == 3 and not failed:
                failed.append(day)
                raise SourceError("the exchange", "busy", busy=True)
            return []
    R._set_state("IN", through="2026-10-08", rules=F.RULES_VERSION - 1)
    run = R.Runner(lambda: {"in": Feed()}, pause=0)
    run.run_india(date(2026, 10, 9))
    st = R.state("IN")
    assert st.get("rules") == F.RULES_VERSION - 1 and st["rebuild_at"] == asked[-1]
    asked.clear()
    run.run_india(date(2026, 10, 9))
    assert asked[0] == st["rebuild_at"] and R.state("IN")["rules"] == F.RULES_VERSION


# ---------- R7O-004 and R7O-007: one close, the exchange's ----------
def test_a_public_pages_candle_takes_the_exchanges_official_close(mem):
    official_close.save("2026-10-08", {"TCS": 2076.0, "ICICIBANK": 1349.0})
    bars = [{"t": "2026-10-07", "o": 1, "h": 2090, "l": 2070, "c": 2080.3}, {"t": "2026-10-08", "o": 1, "h": 2085, "l": 2071, "c": 2077.0}]
    out = official_close.overlay_bars(bars, "TCS", use_quote=False)
    assert out[-1]["c"] == 2076.0 and out[-1]["official"] and out[0] == bars[0]
    assert stock_pages.price_facts(out)["price"] == 2076.0 and stock_pages.price_facts(out)["price_official"]
    assert official_close.overlay_bars(bars, "NOTLISTED", use_quote=False) == bars


def test_a_quote_counts_only_when_it_is_of_the_same_day(mem):
    official_close.setup(None, lambda syms: {"TCS": {"price": 2076.0, "at": "2026-10-08T15:59:58+05:30"}}, force=True)
    try:
        assert official_close.official("TCS", "2026-10-08") == 2076.0
        assert official_close.official("TCS", "2026-10-07") is None
    finally:
        official_close.setup(None, None)


def test_a_page_read_before_the_official_close_takes_it_without_a_price_read(mem):
    f = {"region": "IN", "symbol": "ICICIBANK", "price": 1344.9, "price_at": "2026-10-08", "market_cap": 960000.0, "pe": 17.14, "div_yield": 0.89,
         "high52": 1480.0, "low52": 1187.6}
    mem["stocks:page:IN:ICICIBANK"] = json.dumps({"ts": 1.0, "facts": f})
    now = datetime(2026, 10, 8, 20, 0, tzinfo=IST)
    pages = stock_pages.Pages(lambda r, c: None)
    got = pages.refresh_prices("IN", lambda r, s: [], gap=0, now=now, official=lambda s, d: 1349.0 if s == "ICICIBANK" else None,
                               official_ready=lambda d: True)
    new = json.loads(mem["stocks:page:IN:ICICIBANK"])["facts"]
    assert got["official"] == 1 and new["price"] == 1349.0 and new["price_official"]
    assert round(new["market_cap"]) == round(960000.0 * 1349.0 / 1344.9) and new["div_yield"] == round(0.89 / (1349.0 / 1344.9), 2)


def test_etf_closes_are_the_exchanges_and_an_impossible_gap_is_left_out(mem, monkeypatch):
    live = {"rows": {"MOGSEC": {"price": 62.5, "isin": None, "nav": None, "nav_date": None, "volume": 10}}}
    monkeypatch.setattr(etf_nav, "official_closes", lambda day: {})
    etf_nav.record_close("2026-10-07", live, {})
    assert etf_nav.history("MOGSEC")[0]["close"] == 62.5                     # the last trade, until the official close is out
    monkeypatch.setattr(etf_nav, "official_closes", lambda day: {"MOGSEC": 64.87})
    etf_nav.fill_navs({}, date(2026, 10, 8))
    h = etf_nav.history("MOGSEC")[0]
    assert h["close"] == 64.87 and h["official"]
    # MOGSEC's 62.50 "close", 3.4% below a NAV of 64.68, while the latest price was 64.77: not shown
    assert etf_nav.doubtful(62.5, 64.77, 64.68) and not etf_nav.doubtful(64.87, 64.77, 64.68)
    assert not etf_nav.doubtful(100.0, 97.0, 100.2)                         # a real 3% market move against yesterday's NAV


def test_the_screener_says_its_oldest_close_and_drops_an_unchecked_adr_value():
    old = {"region": "US", "symbol": "EC", "name": "Ecopetrol", "v": 2, "unit": "COP million", "market_cap": 697300.0, "price": 10.0,
           "price_at": "2026-10-07"}
    assert screens.row("US", "EC", old)["market_cap"] is None
    assert screens.row("US", "EC", {**old, "v": stock_pages.FACTS_VERSION, "unit": "$ million", "market_cap": 34800.0})["market_cap"] == 34800.0
    assert screens.rows_as_of([{"price_at": "2026-10-08"}, {"price_at": "2026-10-07"}], None) == ("2026-10-07", "2026-10-08")


def test_the_apps_us_pe_is_the_public_pages_earnings(monkeypatch):
    monkeypatch.setattr(research_routes, "public_facts", lambda r, s: {"price": 340.42, "pe": 38.1})
    c = {"region": "US", "symbol": "AAPL", "quote": {"price": 340.42},
         "metrics": [{"title": "Valuation", "items": [{"label": "P/E", "value": 39.02}]},
                     {"title": "Per share and returns", "items": [{"label": "EPS TTM", "value": 8.72}]}]}
    out = research_routes.with_public_eps("US", c)
    items = {i["label"]: i["value"] for g in out["metrics"] for i in g["items"]}
    assert items["P/E"] == 38.1 and items["EPS TTM"] == round(340.42 / 38.1, 2)
    assert research_routes.with_public_eps("IN", c) is c


def test_a_public_pages_yield_is_the_apps(monkeypatch):
    monkeypatch.setattr(research_routes, "stored_dividends", lambda r, s: [
        {"kind": "dividend", "ex_date": "2026-01-16", "amount": 46.0}, {"kind": "dividend", "ex_date": "2026-06-10", "amount": 30.0},
        {"kind": "dividend", "ex_date": "2026-07-17", "amount": 11.0}, {"kind": "dividend", "ex_date": "2026-10-16", "amount": 24.0},
        {"kind": "bonus", "ex_date": "2026-03-01", "amount": None}])
    assert main.page_dividend_yield("IN", "TCS", 2076.0, "2026-10-08") == round(87 / 2076 * 100, 2)


# ---------- R7O-005: briefs ----------
def test_a_daily_briefs_weekday_is_its_own_days():
    f = {"day": "2026-10-08", "weekly": False}
    assert write.own_weekday("U.S. equity indices were mixed on Tuesday, with the S&P 500 slipping 0.47%.", f).startswith(
        "U.S. equity indices were mixed on Thursday")
    assert write.own_weekday("Stocks fell on Friday. The week ended lower.", {"day": "2026-10-03", "weekly": True}) == "The week ended lower."


def test_a_brief_summary_with_a_number_not_in_the_facts_falls_back():
    f = {"kind": "market", "region": "US", "day": "2026-10-08", "weekly": False, "indices": [{"name": "S&P 500", "price": 7765.36, "change_pct": -0.47}]}
    assert write.grounded("The S&P 500 slipped 0.47% to 7,765.36.", f)
    assert not write.grounded("The S&P 500 slipped 0.9% to 7,765.36.", f)


IN7 = [{"name": "NIFTY 50", "price": 22431.0, "change_pct": -0.76}, {"name": "SENSEX", "price": 72604.0, "change_pct": -0.59}]


@pytest.mark.parametrize("region,title,ok", [
    ("IN", "Stock Market Today Highlights , Oct 6: Sensex settles 685 pts higher; Nifty 50 rises 220 pts", False),   # another day, the other way
    ("IN", "Stock Market Highlights, Sept 28: Sensex tanks 1,124 points, Nifty ends below 22,800", False),
    ("IN", "NSE - National Stock Exchange of India Ltd: Live Share/Stock Market News & Updates, Quotes- Nseindia.com", False),
    ("IN", "Closing Bell: Nifty at 22,600, Sensex down 429 pts after RBI hikes rate", True),
    ("US", "'I'm getting fed up': voters line up before dawn as early voting begins in Ohio - Reuters", False),
    ("US", "We're adding to our position in a hard-hit stock before important catalysts arrive", False),
    ("US", "What Marvell's rosy long-term guidance means for our AI chip stocks", False),
    ("US", "Treasury yields are 'really, really high,' but can come down soon, Bessent's new adviser says", True),
])
def test_brief_headlines_are_market_stories_of_the_day(region, title, ok):
    day = "2026-10-07" if region == "IN" else "2026-10-08"
    assert content.headline_ok(region, title, day, day, IN7 if region == "IN" else None) is ok


def test_a_story_sinking_on_a_day_every_index_rose_is_left_out():
    up = [{"name": "NIFTY 50", "price": 22776.0, "change_pct": 0.98}, {"name": "SENSEX", "price": 73000.0, "change_pct": 0.95}]
    t = "Five reasons India's stock market is sinking even when its economy is growing"
    assert not content.headline_ok("IN", t, "2026-10-06", "2026-10-06", up) and content.headline_ok("IN", t, "2026-10-07", "2026-10-07", IN7)


def test_undated_headlines_are_left_out_of_a_dated_brief():
    rows = [{"headline": "Sensex down 429 pts after RBI hikes rate", "at": None},
            {"headline": "Nifty falls as banks drag; Sensex down 400 points", "at": "2026-10-07T10:00:00+00:00"}]
    got = content.pick_headlines("IN", rows, "2026-10-07", "2026-10-07", indices=IN7)
    assert [h["headline"] for h in got] == ["Nifty falls as banks drag; Sensex down 400 points"]


def test_pulse_and_company_news_drop_advice_style_headlines():
    assert not N.plain_headline("We're buying the dip in a stock that has fallen 20%")
    assert not N.plain_headline("HDFC vs ICICI vs Yes Bank: Which Bank Stock Wins The Race? Target Price")
    assert not N.plain_headline("ICICI Bank Prediction for Tomorrow: 9 Oct 2026")
    assert N.plain_headline("ICICI Bank Q2 results: net profit rises 6%")


def test_stored_briefs_are_checked_again_once(mem, monkeypatch):
    issue = {"id": "market.US.2026-10-08", "kind": "market", "region": "US", "day": "2026-10-08", "weekly": False, "ai": True,
             "subject": "s", "title": "t", "summary": "U.S. equity indices were mixed on Tuesday.",
             "sections": [{"title": "Indices", "items": [{"text": "S&P 500: 7,765.36, −0.47% on the day"}]},
                          {"title": "Headlines", "items": [{"text": "We're adding to our position in a hard-hit stock before important catalysts arrive"},
                                                           {"text": "Treasury yields are 'really, really high,' but can come down soon"}]}]}
    monkeypatch.setattr(news_job, "ids", lambda kind, region: ["market.US.2026-10-08"] if region == "US" else [])
    monkeypatch.setattr(news_job, "load", lambda iid: json.loads(json.dumps(issue)))
    saved = {}
    monkeypatch.setattr(news_job, "parse_id", lambda iid: ("market", "US", "2026-10-08"))
    monkeypatch.setattr(news_job, "_key", lambda *a: "k")
    monkeypatch.setattr(db, "set_setting", lambda k, v: saved.__setitem__(k, json.loads(v)))
    assert news_job.repair_r7("US", days=3650) == 1
    got = saved["k"]
    assert got["summary"] == "U.S. equity indices were mixed on Thursday."
    assert [i["text"] for s in got["sections"] if s["title"] == "Headlines" for i in s["items"]] == [
        "Treasury yields are 'really, really high,' but can come down soon"]


# ---------- R7O-006: admin ----------
def test_option_chain_recording_reads_the_recordings_when_this_server_has_not_recorded(monkeypatch):
    from app import positioning
    monkeypatch.setattr(positioning, "chain_coverage", lambda name: {"days": 8, "first": "2026-09-28", "last": "2026-10-08"} if name == "NIFTY" else {})
    assert admin_jobs.recorded_through(["NFO:NIFTY", "BFO:SENSEX"]) == "2026-10-08"


def test_a_paused_provider_goes_to_the_end_of_the_chain(monkeypatch):
    monkeypatch.setattr(ai_rank, "in_use", lambda name: ["m"])
    monkeypatch.setattr(ai_rank, "score", lambda name, m, task: {"huggingface": 9.0, "groq": 5.0, "gemini": 4.0}[name])
    monkeypatch.setattr(ai_rank, "ready", lambda name, m, now=None: 600.0 if name == "huggingface" else 0.0)
    assert [n for n, _ in ai_rank.route("research", ["huggingface", "groq", "gemini"])] == ["groq", "gemini", "huggingface"]
    assert [n for n, _ in ai_rank.route("research", ["huggingface", "groq", "gemini"], fixed=True)] == ["groq", "gemini", "huggingface"]


def test_the_overview_says_when_the_server_started():
    assert datetime.fromisoformat(main.SERVER_STARTED_AT).utcoffset() == timedelta(hours=5, minutes=30)


# ---------- R7O-008: plans in riyals ----------
def test_riyals_go_through_the_dollar_and_the_peg():
    quotes = {"USDINR=X": 96.78, "SAR=X": 3.75, "NOK=X": 10.8}
    assert round(pricing.cross_rate("SAR", quotes.get), 2) == 25.81
    assert round(pricing.cross_rate("NOK", quotes.get), 2) == round(96.78 / 10.8, 2)
    assert round(pricing.cross_rate("QAR", {"USDINR=X": 96.78}.get), 2) == round(96.78 / 3.64, 2)    # no market read: the peg
    with pytest.raises(ValueError):
        pricing.cross_rate("NOK", {"USDINR=X": 96.78}.get)


def test_the_riyal_price_is_the_rupee_charge_converted(mem):
    mem[pricing.RATES] = json.dumps({"rates": {"USD": 96.78}})       # SAR not read yet: the dollar's rate over the peg
    pricing._rates_cache[0] = 0.0
    pricing.forget()
    t = pricing.table()
    assert t["SAR"]["basic"] == 27 and t["SAR"]["pro"] == 77 and t["SAR"]["converted"] and t["SAR"]["charged_in"] == "INR"
    assert t["USD"]["basic"] == 8 and t["USD"]["pro"] == 20 and not t["USD"]["converted"]         # dollars stay as the owner set them
    pricing._rates_cache[0] = 0.0


# ---------- R7O-009: a cold public page is a page ----------
def test_a_page_being_prepared_is_html_that_loads_itself_again():
    html = stock_pages.busy_page("US", "SNY", "Sanofi")
    assert html.startswith("<!doctype html>") and "Sanofi (SNY): this page is being prepared" in html
    assert 'http-equiv="refresh"' in html and 'content="noindex,follow"' in html and "<h1>" in html


# ---------- R7O-013: one net-worth snapshot removed ----------
def test_one_snapshot_leaves_the_history_and_the_rest_stays(w):
    uid = "u-pro"
    db.set_setting(money_networth.LOG + uid, json.dumps([{"d": "2026-09-01", "net": 1000.0, "assets": 1000.0, "liabilities": 0.0, "why": "month"},
                                                         {"d": "2026-10-08", "net": 243481.78, "assets": 243481.78, "liabilities": 0.0, "why": "change"}]))
    c = w["client"]
    r = c.delete("/money/net-worth/history/2026-10-08", headers=world.headers("pro-token"))
    assert r.status_code == 200, r.text
    assert [h["d"] for h in r.json()["history"]] == ["2026-09-01"]
    assert c.delete("/money/net-worth/history/2026-10-08", headers=world.headers("pro-token")).status_code == 404
    assert c.delete("/money/net-worth/history/not-a-day", headers=world.headers("pro-token")).status_code == 400


# ---------- round 6 leftovers ----------
def test_half_a_million_is_under_a_million_not_zero():
    us = {"region": "US", "currency": "USD", "market_cap": 0.5, "sales_usd": 30.0}
    assert stock_pages.cap_text(us) == "<$1M" and stock_pages.cap_text({**us, "market_cap": 1.4}) == "$1M"


def test_a_strategy_behind_buy_and_hold_leads_with_the_shortfall():
    e = {"verdict": {"verdict": "edge", "headline": "Likely a real edge.", "passed": 3, "total": 3}, "group": {"id": "g"},
         "stats": {"ret": 55.83, "buy_hold": 172.93, "trades": 250, "unseen": 19.05}}
    head = library.restated(e)["fact_headline"]
    assert head.startswith("117.1 points behind buy and hold after costs") and "passed all 3 checks run" in head
    ahead = {**e, "stats": {**e["stats"], "ret": 200.0}}
    assert library.restated(ahead)["fact_headline"].startswith("Passed all 3 checks run")
