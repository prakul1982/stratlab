"""Round 10 review, owner (R10O-001 to 012): the receipt's heading without a GSTIN, the market mood on the day's FII and DII
figures, rule ideas made of indicators, advice-flavoured headlines, the public page's 52-week range on the exchange's
report, a PCR table that answers at once, a company page that doesn't wait on its news, the ITR page's dates, the rotation
chart's last finished session, a bank's financing margin, and the screener's stale close. Every clock here is a fixed
instant, and nothing depends on a job having run."""
from datetime import date, datetime, timedelta, timezone

import pytest

from app import main  # noqa: F401, I001  (first: the app loads its modules in a fixed order)
from app import db, lifecycle, official_close, positioning as PO, rotation, screens, stock_pages
from app import email_previews as P
from app.intel import grounding as G, news
from app.intel.screener import fix_lender_margins
from tests.test_review_r8b import mem  # noqa: F401  (mem: the settings table in memory)

IST = timezone(timedelta(hours=5, minutes=30))


def _ist(d: str, hm: str) -> datetime:
    h, m = hm.split(":")
    return datetime.fromisoformat(d).replace(hour=int(h), minute=int(m), tzinfo=IST)


# ---------- R10O-003: an unregistered seller issues an invoice, not a tax invoice ----------
def test_the_receipt_is_headed_invoice_while_the_seller_has_no_gstin(monkeypatch):
    from app import invoices
    monkeypatch.setattr(invoices, "seller", lambda: {**{f: "" for f in invoices.FIELDS}, "prefix": "SL"})
    text = P.describe("lifecycle_receipt", True)["text"]
    assert "Not registered under GST" in text
    assert "tax invoice" not in text.lower() and "INVOICE SL/2026-27/0001" in text
    inv = lifecycle.sample_invoice(datetime(2026, 10, 9, 12, 0, tzinfo=timezone.utc))
    assert "Tax invoice" not in invoices.html(inv) and "<h1>Invoice</h1>" in invoices.html(inv)


def test_the_receipt_is_a_tax_invoice_once_a_gstin_is_set(monkeypatch):
    from app import invoices
    monkeypatch.setattr(invoices, "seller", lambda: {**{f: "" for f in invoices.FIELDS}, "legal_name": "StratLab Labs LLP", "state": "27",
                                                     "gstin": "27ABCDE1234F1Z5", "prefix": "SL"})
    assert "TAX INVOICE SL/" in P.describe("lifecycle_receipt", True)["text"]
    inv = lifecycle.sample_invoice(datetime(2026, 10, 9, 12, 0, tzinfo=timezone.utc))
    assert "<h1>Tax invoice</h1>" in invoices.html(inv)


# ---------- R10O-004: who bought or sold comes from the day's FII and DII figures ----------
CASH = {"kind": "cash", "status": "ok", "as_of": "2026-10-09", "fii": {"buy": 10374.0, "sell": 13943.0, "net": -3569.0},
        "dii": {"buy": 15627.0, "sell": 10883.0, "net": 4743.0}}
NIFTY = [{"name": "NIFTY 50", "price": 22520.45, "change_pct": 1.3, "day": "2026-10-09", "from_low_pct": 12.0, "from_high_pct": -2.0}]
HEADS = [{"headline": "Foreign investors dump Indian shares for a third week", "at": "2026-10-08"},
         {"headline": "Sensex jumps 879 points as IT and FMCG stocks rally", "at": "2026-10-09"}]


def test_a_sentence_inferring_flows_from_price_moves_is_dropped():
    nets = {"fii": {"net": -3569.0}, "dii": {"net": 4743.0}}
    for s in ("Today's upward move suggests a reversal or stabilization of flows.",
              "The surge in IT and FMCG stocks indicates strong domestic institutional interest.",
              "A headline noted a foreign exodus, but the market's rise points to a reversal of flows."):
        assert not G.flow_claim_ok(s, nets), s
        assert not G.flow_claim_ok(s, None), s
    # direction as the net figures have it, for the holder named
    assert G.flow_claim_ok("FIIs sold ₹3,569 crore of shares while DIIs bought ₹4,743 crore.", nets)
    assert not G.flow_claim_ok("FIIs bought shares on the day.", nets)
    assert not G.flow_claim_ok("Domestic institutions were net sellers.", nets)
    assert not G.flow_claim_ok("Outflows continued.", nets)            # no holder named: can't be checked
    assert G.flow_claim_ok("Sensex rose 1.2% and Nifty ended at 22,520.", nets)


def test_the_mood_keeps_flow_sentences_only_when_the_days_figures_bear_them_out():
    read = {"tone": "The Nifty rose 1.3%. Today's upward move suggests a reversal of flows. FIIs sold ₹3,569 crore on the day.",
            "hot": [], "themes": [],
            "flows": [{"title": "Foreign investors", "detail": "FIIs sold ₹3,569 crore.", "direction": "OUTFLOW"},
                      {"title": "Foreign investors", "detail": "FIIs bought ₹3,569 crore.", "direction": "INFLOW"}]}
    out = G.ground_pulse(read, NIFTY, HEADS, None, CASH)
    assert "reversal" not in out["tone"] and "FIIs sold" in out["tone"] and "rose 1.3%" in out["tone"]
    assert [f["detail"] for f in out["flows"]] == ["FIIs sold ₹3,569 crore."]
    # without the day's figures an inference still goes, and what a headline reports can stay
    bare = G.ground_pulse(read, NIFTY, HEADS, None, None)
    assert "reversal" not in bare["tone"]


def test_the_mood_is_given_the_days_fii_and_dii_figures(monkeypatch):
    from app.intel import ai as A
    seen = {}

    def ask(system, facts, ai, tokens):
        seen.update(system=system, facts=facts)
        return {"tone": "The Nifty rose 1.3%.", "hot": [], "flows": [], "themes": []}
    monkeypatch.setattr(A, "_ask", ask)
    A.pulse("IN", "", NIFTY, HEADS, (None, None), closed=True, cash=CASH)
    assert seen["facts"]["institutional_flows"] == {"as_of": "2026-10-09", "fii_buy_crore": 10374.0, "fii_sell_crore": 13943.0,
                                                    "fii_net_crore": -3569.0, "dii_buy_crore": 15627.0, "dii_sell_crore": 10883.0,
                                                    "dii_net_crore": 4743.0}
    assert "never work out who is buying or selling" in seen["system"].lower()
    A.pulse("IN", "", NIFTY, HEADS, (None, None), closed=True, cash={**CASH, "status": "pending"})        # the day's not in yet
    assert "institutional_flows" not in seen["facts"]
    A.pulse("US", "", NIFTY, HEADS, (None, None), closed=True)
    assert "institutional_flows" not in seen["facts"]


# ---------- R10O-005: a rule made of indicators and percentages ----------
POLYCAB = [
    {"title": "Price breakout above current level", "text": "Enter long when price rises above 8255, exit when price drops 5% below the entry, 5% stop loss",
     "why": "Current price is 8255."},
    {"title": "Trend following with 20-day SMA", "text": "Enter long when price stays above 8255 for three consecutive days, 5% stop loss",
     "why": "The price is 8255."},
    {"title": "Mean reversion to 5-day low", "text": "Enter long when price drops 5% below 8255, exit when price recovers to 8255",
     "why": "The price is 8255."},
    {"title": "Trend following with 20-day SMA", "text": "Enter long when the close is above its 20-day SMA, exit when it closes below it, 5% stop loss",
     "why": "The close is 8255."},
    {"title": "Mean reversion on RSI", "text": "Enter long when RSI(14) drops below 30, exit when RSI rises above 55, 5% stop loss", "why": "x"},
]


def test_a_rule_that_types_in_a_price_level_is_a_hardcoded_price():
    texts = [i["text"] for i in POLYCAB]
    assert [G.hardcodes_price(t, 8255) for t in texts] == [True, True, True, False, False]
    assert G.hardcodes_price(texts[0]) and not G.hardcodes_price(texts[3])        # without the price: a level of 100 or more
    assert not G.hardcodes_price("Enter long when volume rises above 1,000,000 shares and price closes above its 50-day average", 8255)
    assert not G.hardcodes_price("Enter long when price closes above its 52-week high, 3% stop loss", 8255)
    assert G.hardcodes_price("Enter long when price closes above ₹250", None)


def test_a_title_names_an_indicator_its_rule_uses():
    assert not G.idea_uses_what_it_names("Trend following with 20-day SMA", POLYCAB[1]["text"])
    assert not G.idea_uses_what_it_names("Mean reversion to 5-day low", POLYCAB[2]["text"])
    assert G.idea_uses_what_it_names("Trend following with 20-day SMA", POLYCAB[3]["text"])
    assert G.idea_uses_what_it_names("Mean reversion to 5-day low", "Enter long when price closes at its 5-day low, 3% stop loss")
    assert G.idea_uses_what_it_names("Breakout above the high", "Enter long when price closes above its 20-day high")


def test_the_read_keeps_only_the_ideas_made_of_indicators():
    facts = {"symbol": "POLYCAB", "price": 8255.0, "name": "Polycab India Ltd", "currency": "INR", "market": "India (NSE)"}
    read = {"summary": "", "valuation_note": "", "position": "", "bull": [], "bear": [], "watch": [], "ideas": POLYCAB[:4]}
    out = G.ground_company(read, facts, "IN", date(2026, 10, 9))
    assert [i["title"] for i in out["ideas"]] == ["Trend following with 20-day SMA"]
    assert "20-day SMA" in out["ideas"][0]["text"]
    # a stored read comes through the same check when it's served
    stored = G.polish_company({"summary": "", "ideas": POLYCAB}, "IN", False)
    assert [i["text"] for i in stored["ideas"]] == [POLYCAB[3]["text"], POLYCAB[4]["text"]]


# ---------- R10O-006: advice-flavoured headlines ----------
ADVICE = ["Where Could Titan Share Price Potentially Be in the Next 5 Years?", "Citi says correction offers 'attractive entry point'",
          "Titan: brokerages retain bullish calls", "Polycab India stock gains 1.13 percent as target stays high",
          "Brokerages keep a bullish call on Titan", "Titan: entry point for long-term investors", "Titan target raised by two brokerages",
          "Where will Titan be in 2030?"]
FACTUAL = ["Titan Q2 results: net profit rises 6% to Rs 1,100 crore", "Reliance Retail adds 300 stores; targets 5,000 by FY28",
           "Titan shares gain 2% after Q2 business update", "Company's entry into the EV market announced", "Where is the Nifty trading? Index ends at 22,520",
           "Sensex ends higher as bullish sentiment in banks cools", "Titan opens 40 new stores in Tamil Nadu", "Polycab India stock gains 1.13 percent"]


@pytest.mark.parametrize("title", ADVICE)
def test_advice_flavoured_headlines_are_left_out(title):
    assert not news.plain_headline(title), title


@pytest.mark.parametrize("title", FACTUAL)
def test_factual_headlines_stay(title):
    assert news.plain_headline(title), title


# ---------- R10O-007: the public page's range is the exchange's ----------
def test_a_stored_page_takes_the_exchanges_52_week_high_when_served(mem):
    from app import exchange_days as E
    report = {"day": "2026-10-09", "rows": E.week52_rows("SYMBOL,SERIES,52_WEEK_HIGH_DATE,52_WEEK_LOW_DATE,52_WEEK_HIGH,52_WEEK_LOW\n"
                                                         "INFY,EQ,03-Feb-2026,29-Sep-2026,1728.00,980.40\n")}
    f = {"region": "IN", "symbol": "INFY", "price": 997.0, "high52": 1691.4, "low52": 980.4}
    out = stock_pages.with_week52_report(f, report)
    assert out["high52"] == 1728.0 and out["low52"] == 980.4 and f["high52"] == 1691.4          # a copy; never narrowed
    assert stock_pages.with_week52_report({**f, "high52": 1800.0}, report)["high52"] == 1800.0
    assert stock_pages.with_week52_report({**f, "high52": 1000.0}, report)["high52"] == 1000.0   # another basis: left alone
    assert stock_pages.with_week52_report({**f, "region": "US"}, report)["high52"] == 1691.4
    assert stock_pages.with_week52_report(f, None) is f

    pages = stock_pages.Pages(lambda *a: None)
    pages.adjust = lambda r, s, facts: stock_pages.with_week52_report(facts, report, s) if r == "IN" else facts
    pages.mem.set("stocks:page:IN:INFY", f, 600)
    assert pages.get("IN", "INFY", {})["high52"] == 1728.0
    assert main.stock_page_store.adjust is not None


# ---------- R10O-008: the PCR table answers at once ----------
class _NoFeed:
    """A feed that must not be asked: any read raises."""
    def ready(self):
        raise AssertionError("the PCR table read the live feed")

    def __getattr__(self, name):
        raise AssertionError(f"the PCR table asked the feed for {name}")


def _recording(expiry="2026-10-13", taken="2026-10-09T15:39:00+05:30"):
    chain = [[22400 + 50 * i, 0, 0, 0, 1000 + i, 0, 0, 0, 900 + i, 500, 400] for i in range(61)]
    return {"expiry": expiry, "expiries": [expiry], "spot": 22520.0, "chain": chain, "source": "recorded", "taken_at": taken, "lot": 65}


def test_with_the_market_shut_the_pcr_table_reads_the_recordings_and_not_the_feed(monkeypatch):
    monkeypatch.setattr(PO, "recorded_chain", lambda name, choice, day: _recording())
    out = PO.pcr_table(_NoFeed(), _ist("2026-10-09", "19:00"), ("NIFTY", "BANKNIFTY"))
    assert [r["name"] for r in out] == ["NIFTY", "BANKNIFTY"]
    assert all(r["at_close"] and r["source"] == "recorded" and r["pcr_oi"] and r["strikes_read"] == 61 for r in out)
    # an expiry that has passed isn't a current one: that index reads the feed (here offline) instead of an expired chain
    monkeypatch.setattr(PO, "recorded_chain", lambda name, choice, day: _recording(expiry="2026-10-08"))
    monkeypatch.setattr(PO, "live_chains", lambda od, names, choice, quick=False: {n: None for n in names})
    out = PO.pcr_table(_NoFeed(), _ist("2026-10-10", "11:00"), ("NIFTY",))
    assert out[0]["name"] == "NIFTY" and out[0]["source"] == "recorded" and out[0].get("expiry") == "2026-10-08"


def test_in_market_hours_todays_recording_answers_while_the_live_chain_is_read_behind_it(monkeypatch):
    rec = _recording(taken="2026-10-09T09:20:00+05:30")
    asked = {}
    monkeypatch.setattr(PO, "_cache", PO._cache.__class__(max_items=50))
    PO._last_live.clear()
    monkeypatch.setattr(PO, "ist_now", lambda: _ist("2026-10-09", "11:00"))
    monkeypatch.setattr(PO, "recorded_last", lambda name, day: [rec])
    monkeypatch.setattr(PO, "recorded_chain", lambda name, choice, day: rec)
    monkeypatch.setattr(PO, "_refresh_behind", lambda od, names, choice: asked.update(behind=list(names)))
    monkeypatch.setattr(PO, "_read_live", lambda *a, **k: pytest.fail("the page waited for a live read"))
    monkeypatch.setattr(PO.time, "time", lambda: _ist("2026-10-09", "11:00").timestamp())
    got = PO.live_chains(object(), ("NIFTY",), "current", quick=True)
    assert got["NIFTY"] is rec and asked["behind"] == ["NIFTY"]
    # a plain read still wants a recording from the last five minutes
    PO._last_live.clear()
    monkeypatch.setattr(PO, "_read_live", lambda *a, **k: {})
    assert PO.live_chains(object(), ("NIFTY",), "current")["NIFTY"] is None
    PO._last_live.clear()


# ---------- R10O-009: a company page's first answer doesn't wait on its news ----------
def test_a_lean_company_page_leaves_the_news_and_the_entry_for_a_second_request(monkeypatch):
    from tests import world as W
    w = W.build(monkeypatch)
    try:
        h = W.headers("pro-token")
        hub = main.research_hub

        def slow(*a, **k):
            raise AssertionError("a lean page asked a slow source")
        full = w["client"].get("/research/company/IN/TCS", headers=h).json()
        assert full["news"] and "lazy" not in full
        monkeypatch.setattr(hub.news, "search", slow)
        monkeypatch.setattr(hub.wiki, "company", slow)
        lean = w["client"].get("/research/company/IN/TCS?lean=1", headers=h).json()
        assert lean["quote"]["price"] == full["quote"]["price"] and lean["metrics"] == full["metrics"] and lean["quarters"] == full["quarters"]
        assert lean["news"] == [] and lean["about"]["wiki"] is None and lean["lazy"] == ["news", "about"]
        assert lean["about"]["profile"] == full["about"]["profile"]
        monkeypatch.undo()
    finally:
        w["close"]()


def test_the_second_request_brings_the_news_the_entry_and_the_peers(monkeypatch):
    from tests import world as W
    w = W.build(monkeypatch)
    try:
        h = W.headers("pro-token")
        for path in ("IN/TCS", "US/AAPL"):
            full = w["client"].get(f"/research/company/{path}", headers=h).json()
            more = w["client"].get(f"/research/company/{path}/more", headers=h).json()
            assert more["news"] == full["news"] and more["wiki"] == full["about"]["wiki"] and more["peers"] == full["peers"]
        us = w["client"].get("/research/company/US/AAPL?lean=1", headers=h).json()
        assert us["news"] == [] and us["about"]["wiki"] is None and us["peers"] == full["peers"] and us["quote"]["price"]
    finally:
        w["close"]()


# ---------- R10O-010: the ITR page's dates, and a rotation chart of finished sessions ----------
def test_the_itr_page_writes_the_upload_day_the_apps_way():
    from app import money_itr
    g = {"files": [{"name": "tradebook.csv", "broker": "Zerodha", "trades": 38, "at": "2026-10-04T08:15:00+00:00"}],
         "mf_count": 0, "us_count": 0, "us_div": None, "fmv_src": {}, "div_source": "estimated"}
    line = money_itr.sources(g)[0]
    assert line == "Your file tradebook.csv (Zerodha, 38 trades, uploaded 4 Oct 2026)."
    assert "2026-10" not in " ".join(money_itr.sources(g))


def _bar(day: str, close: float) -> dict:
    return {"t": f"{day}T00:00:00-04:00", "o": close, "h": close, "l": close, "c": close, "v": 1.0}


def test_a_session_still_trading_is_left_out_of_the_rotation_charts_candles():
    bars = [_bar("2026-10-07", 100.0), _bar("2026-10-08", 101.0), _bar("2026-10-09", 102.0)]
    load = rotation.completed_sessions("US", lambda iid, days: bars, _ist("2026-10-09", "20:25"))      # 10:55 in New York
    assert [str(b["t"])[:10] for b in load("US:SPY", 220)] == ["2026-10-07", "2026-10-08"]
    shut = rotation.completed_sessions("US", lambda iid, days: bars, _ist("2026-10-10", "02:00"))        # the session has closed
    assert [str(b["t"])[:10] for b in shut("US:SPY", 220)] == ["2026-10-07", "2026-10-08", "2026-10-09"]
    india = rotation.completed_sessions("IN", lambda iid, days: bars, _ist("2026-10-09", "20:25"))       # India closed at 15:30
    assert len(india("NSE:NIFTY BANK", 220)) == 3


# ---------- R10O-011: a bank's financing margin ----------
def _bank(fp, interest, pbt=None, revenue=None, net=None):
    revenue = revenue or [52_241.0] * len(fp)
    rows = {"Revenue": revenue, "Interest": interest, "Expenses": [r * 0.55 for r in revenue], "Financing Profit": fp,
            "Financing Margin %": [round(f / r * 100) for f, r in zip(fp, revenue)],
            "Net Profit": net or [r * 0.31 for r in revenue]}
    if pbt is not None:
        rows["Profit before tax"] = pbt
    return {"quarters": {"cols": [f"Q{i}" for i in range(len(fp))], "rows": rows}}


def test_a_banks_financing_margin_does_not_take_the_interest_out_twice():
    # ICICIBANK-shaped: revenue 52,241 a quarter, net profit near 31% of it; the source's financing profit is revenue less the
    # expenses (which hold the interest) less the interest again: negative, beside a profit
    p = _bank(fp=[-6_300.0, -9_500.0, -14_000.0], interest=[24_000.0, 25_000.0, 26_000.0], pbt=[17_700.0, 15_500.0, 12_000.0])
    assert p["quarters"]["rows"]["Financing Margin %"] == [-12, -18, -27]
    fix_lender_margins(p)
    rows = p["quarters"]["rows"]
    assert rows["Financing Profit"] == [17_700, 15_500, 12_000]
    assert rows["Financing Margin %"] == [34, 30, 23] and all(m > 0 for m in rows["Financing Margin %"])


def test_a_margin_that_cannot_be_checked_is_left_out_not_shown_wrong():
    # no interest line and no profit before tax: a negative margin beside a profit can only be wrong
    p = {"quarters": {"cols": ["Q0", "Q1"], "rows": {"Revenue": [52_241.0, 50_000.0], "Financing Profit": [-6_300.0, 4_000.0],
                                                    "Financing Margin %": [-12, 8], "Net Profit": [16_276.0, 15_000.0]}}}
    fix_lender_margins(p)
    assert p["quarters"]["rows"]["Financing Margin %"] == [None, 8]          # the one that holds up stays
    # a margin that already fits the profit before tax is not touched
    good = _bank(fp=[17_000.0], interest=[24_000.0], pbt=[17_200.0])
    fix_lender_margins(good)
    assert good["quarters"]["rows"]["Financing Margin %"] == [33]
    # a company with no financing margin at all (not a lender) is untouched
    plain = {"quarters": {"cols": ["Q0"], "rows": {"Sales": [100.0], "OPM %": [20]}}}
    assert fix_lender_margins(plain) == {"quarters": {"cols": ["Q0"], "rows": {"Sales": [100.0], "OPM %": [20]}}}


def test_the_company_page_gets_the_corrected_margin_from_the_source(monkeypatch):
    from app.intel import screener as S
    page = {"ratios": {"Current Price": "1,355"}, "pl": None, **_bank(fp=[-6_300.0], interest=[24_000.0], pbt=[17_700.0])}
    monkeypatch.setattr(S.Screener, "fetch", lambda self, *a, **k: "<html top-ratios></html>")
    monkeypatch.setattr(S, "parse", lambda html: __import__("copy").deepcopy(page))
    sc = S.Screener()
    got = sc._page("/company/ICICIBANK/consolidated/")
    assert got["quarters"]["rows"]["Financing Margin %"] == [34]


# ---------- R10O-012: one stock's old close is named, not the list's date ----------
def test_a_stale_close_is_named_and_does_not_set_the_lists_date():
    rows = [{"symbol": "AAPL", "name": "Apple", "price_at": "2026-10-08"}, {"symbol": "MSFT", "name": "Microsoft", "price_at": "2026-10-08"},
            {"symbol": "XYZ", "name": "Xyz Corp", "price_at": "2026-10-02"}, {"symbol": "NVDA", "name": "NVIDIA", "price_at": "2026-10-07"}]
    assert screens.rows_as_of(rows, None) == ("2026-10-07", "2026-10-08")          # one day older is still the list's own
    assert screens.stale_rows(rows) == [{"symbol": "XYZ", "name": "Xyz Corp", "price_at": "2026-10-02"}]
    assert screens.rows_as_of([{"price_at": "2026-10-08"}, {"price_at": "2026-10-07"}], None) == ("2026-10-07", "2026-10-08")
    assert screens.stale_rows([{"symbol": "A", "price_at": "2026-10-08"}, {"symbol": "B", "price_at": "2026-10-05"}]) == []          # a weekend apart: the list's own
    assert [s["symbol"] for s in screens.stale_rows([{"symbol": "A", "price_at": "2026-10-08"}, {"symbol": "B", "price_at": "2026-10-04"}])] == ["B"]
    assert screens.stale_rows([]) == [] and screens.rows_as_of([], "2026-10-09") == ("2026-10-09", "2026-10-09")


def test_the_screens_answer_carries_the_stale_stocks(monkeypatch):
    index = {"at": "2026-10-09", "rows": [
        {"symbol": s, "name": s, "market_cap": 100.0 - i, "price_at": d, "sector": "Tech", "price": 10.0}
        for i, (s, d) in enumerate([("AAA", "2026-10-08"), ("BBB", "2026-10-08"), ("XYZ", "2026-10-02")])]}
    out = screens.run("US", {}, index=index)
    assert out["as_of"] == "2026-10-08" and out["as_of_newest"] == "2026-10-08"
    assert [s["symbol"] for s in out["stale"]] == ["XYZ"]
