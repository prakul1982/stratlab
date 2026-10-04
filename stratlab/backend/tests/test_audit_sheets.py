"""Fixes from the full whole-market audit sheets (India 6,822 rows, US 7,075): the exchange refusing BSE filings is a
check to run again, not a company's error; true facts about a company (a recent listing, no earnings calls, no
revenue yet, suspended shares) read as facts, not as our gaps; funds and SPACs leave the universe; and the US filings
are read in the concepts banks, REITs, miners and IFRS filers actually use."""
from datetime import date, datetime, timedelta, timezone

import httpx
import pytest

from app import audit, deepdive, industry, main, report_card, universes
from app.intel import filings as F
from app.intel import sec
from app.kite_service import bse_only_rows, not_company
from tests.test_deepdive import company


# ---------- the exchange refusing the documents step ----------
def _bse(handler, slept=None):
    slept = [] if slept is None else slept
    return F.BSEFilings(transport=httpx.MockTransport(handler), sleep=slept.append), slept


def test_bse_refusal_warms_up_a_session_and_retries_with_backoff():
    """BSE's bot guard answered 403 to 2,138 BSE-only companies in a row: visit the website for cookies first, and
    on a refusal fetch fresh ones and try again after a pause."""
    seen = []

    def handler(r):
        seen.append(r.url.host + r.url.path)
        if r.url.host == "www.bseindia.com":
            return httpx.Response(200, text="<html></html>", headers={"set-cookie": "bm_sv=ok; Domain=.bseindia.com; Path=/"})
        if len([s for s in seen if "AnnSub" in s]) == 1:
            return httpx.Response(403, text="Access denied")
        return httpx.Response(200, json={"Table": []})
    feed, slept = _bse(handler)
    assert feed.announcements("543210") == []
    assert seen[0] == "www.bseindia.com/" and seen.count("www.bseindia.com/") == 2      # warmed up, then again after the 403
    assert feed.BACKOFF[0] in slept                                                     # paused before trying again


def test_bse_refusing_every_time_is_busy_and_rests():
    calls = []

    def handler(r):
        calls.append(r.url.path)
        return httpx.Response(200, text="") if r.url.host == "www.bseindia.com" else httpx.Response(429, headers={"retry-after": "9"})
    feed, slept = _bse(handler)
    with pytest.raises(F.SourceError) as e:
        feed.announcements("543210")
    assert e.value.busy and "refused the request (429)" in str(e.value)                # try again later, not a fact
    assert 9.0 in slept                                                                 # the exchange's own wait is kept
    n = len(calls)
    with pytest.raises(F.SourceError):
        feed.corporate_actions("543210")                                                # resting: not asked at all
    assert len(calls) == n


def test_bse_calls_are_paced():
    feed, slept = _bse(lambda r: httpx.Response(200, json={"Table": []}))
    feed.GAP = 5.0
    feed.announcements("500001")
    feed.announcements("500002")
    assert any(s > 4 for s in slept)                                                    # the second waited its turn


def test_bse_classification_from_its_quote_header():
    def handler(r):
        if r.url.path.endswith("/ComHeadernew/w"):
            return httpx.Response(200, json={"Sector": "Industrials", "IndustryNew": "Capital Goods",
                                             "IGroupName": "Electrical Equipment", "ISubGroupName": "Cables - Electricals"})
        return httpx.Response(200, text="")
    feed, _ = _bse(handler)
    assert feed.industry("544960") == ["Industrials", "Capital Goods", "Electrical Equipment", "Cables - Electricals"]
    india = F.IndiaFilings(None, feed, lambda s: s if s.isdigit() else None)
    assert india.industry("544960")[-1] == "Cables - Electricals"


def test_nse_refusal_is_retried_then_busy():
    n = [0]

    def handler(r):
        if r.url.path == "/api/corporate-announcements":
            n[0] += 1
            return httpx.Response(429) if n[0] < 3 else httpx.Response(200, json={"data": []})
        return httpx.Response(200, text="<html></html>")
    slept = []
    assert F.NSEFilings(transport=httpx.MockTransport(handler), sleep=slept.append).announcements("ABC") == [] and slept
    always = httpx.MockTransport(lambda r: httpx.Response(403) if r.url.path.startswith("/api") else httpx.Response(200, text=""))
    with pytest.raises(F.SourceError) as e:
        F.NSEFilings(transport=always, sleep=lambda s: None).announcements("XYZ")
    assert e.value.busy


def test_a_refused_documents_step_is_pending_not_an_error(monkeypatch):
    monkeypatch.setattr(deepdive, "stored", lambda s: None)
    monkeypatch.setattr(report_card, "stored", lambda s: None)
    base = {"p": company(), "docs": [], "doc_note": "The exchange feed refused the request (403). Try again later.",
            "filings": None, "trend": {"price": 100.0}}
    row = audit.audit_company("ACME", lambda s: base, main.deep_view)
    docs = [i for i in row["issues"] if i["area"] == "Documents"]
    assert docs == [audit._issue("pending", "Documents", "Not checked yet: the exchange feed refused the request (403). "
                                                         "It is checked again later.")]
    assert audit._transient(row)


# ---------- stored rows, read with today's rules ----------
def test_stored_refusals_and_short_histories_are_restated():
    row = {"issues": [audit._issue("error", "Documents", "The exchange feed refused the request (403)."),
                      audit._issue("error", "Company page", "Server disconnected"),
                      audit._issue("error", "Prices", "Exchange price unavailable: Unknown Content-Type (text/html) with response"),
                      audit._issue("gap", "Numbers", "Only 2 years of annual results"),
                      audit._issue("gap", "Checklist", "5 checks couldn't be judged: Sales growth, 3 years"),
                      audit._issue("gap", "Company page", "the fundamentals source has nothing for that.")]}
    got = audit.restate_row(row)
    levels = [i["level"] for i in got]
    assert levels == ["pending", "pending", "pending", "fact", "fact", "fact"]
    assert got[0]["detail"].startswith("Not checked yet: the exchange feed refused the request (403)")
    assert got[3]["detail"].startswith("Only 2 years of annual results so far")
    assert "need more history" in got[4]["detail"]
    assert audit.restate(audit._issue("gap", "Numbers", "Only 0 years of annual results"))["level"] == "gap"   # no results at all
    us = {"issues": [audit._issue("gap", "Documents", "No annual report (10-K) filed in the last two years"),
                     audit._issue("gap", "Documents", "No quarterly report (10-Q) filed in the last two years")]}
    assert audit.restate_row(us, us=True) == [audit._issue("fact", "Documents", audit.STOPPED_FILING)]


def test_market_audit_rechecks_only_refused_companies(monkeypatch):
    from tests import world as W
    w = W.build(monkeypatch)
    try:
        listing = [{"symbol": s, "name": f"{s} Ltd", "listed": "2001-01-01"} for s in ("AAA", "BBB", "CCC")]
        refused = {"BBB": True}

        def check(sym):
            if refused.get(sym):
                return {"symbol": sym, "name": sym, "seconds": 0,
                        "issues": [audit._later("Documents", "The exchange feed refused the request (403).")]}
            return {"symbol": sym, "name": f"{sym} Ltd", "seconds": 0, "issues": []}
        a = audit.MarketAudit(lambda: listing, check, pause=0)
        a.set_enabled(True)
        a.start_full()
        assert [a.step(), a.step(), a.step(), a.step()] == ["AAA", "BBB", "CCC", None]
        assert a.rows["BBB"]["name"] == "BBB Ltd"                           # the listing's name, not the bare symbol
        assert a.cool == 0 and a.status()["pending"] == 1 and a.status()["summary"]["pending"] == 1
        a.rows["BBB"]["tries"] = audit.MAX_TRIES                            # past the automatic retries
        assert a.queue() == []
        refused["BBB"] = False
        h = W.headers("admin-token")
        monkeypatch.setattr(main, "market_audit", a)
        r = w["client"].post("/admin/audit/market", headers=h, json={"retry": True}).json()
        assert r["full"]["running"] and r["full"]["pending_only"] and r["full"]["left"] == 1
        assert a.queue() == ["BBB"] and a.step() == "BBB" and a.step() is None
        assert a.status()["pending"] == 0 and not a.status()["full"]["running"]
    finally:
        w["close"]()


def test_market_audit_slows_down_while_a_source_refuses(monkeypatch):
    from tests import world as W
    w = W.build(monkeypatch)
    try:
        listing = [{"symbol": s, "name": s, "listed": date.today().isoformat()} for s in ("A1", "A2", "A3")]
        later = lambda s: {"symbol": s, "name": s, "seconds": 0, "issues": [audit._later("Company page", "refused the request")]}  # noqa: E731
        a = audit.MarketAudit(lambda: listing, later, pause=0)
        a.set_enabled(True)
        a.step()
        first = a.cool
        assert a.status()["paused"] == "cooling"
        a.step()
        assert first >= 60 and a.cool == first * 2
        a.check_fn = lambda s: {"symbol": s, "name": s, "seconds": 0, "issues": []}
        a.step()
        assert a.cool == 0
    finally:
        w["close"]()


# ---------- India: documents, funds on BSE, prices ----------
@pytest.mark.parametrize("subject,text,kind", [
    ("Analysts/Institutional Investor Meet/Con. Call Updates", "Transcript of the earnings call held on 12-Aug-2026", "transcript"),
    ("Analysts/Institutional Investor Meet/Con. Call Updates", "Transcipt of conference call", "transcript"),
    ("Earnings Call Transcript", "Earnings Call Transcript", "transcript"),
    ("Analysts/Institutional Investor Meet/Con. Call Updates", "XYZ Ltd has informed the Exchange about Presentation", "presentation"),
    ("Updates", "Investors Presentation for Q1 FY27", "presentation"),
    ("Updates", "Presentation made to the analysts", "presentation"),
    ("Investor Presentation", "Investor Presentation", "presentation"),
    ("Analysts/Institutional Investor Meet/Con. Call Updates", "Schedule of analyst meet on 20-Aug-2026", None),
])
def test_common_subject_lines_are_found(subject, text, kind):
    cid, _ = F.classify(subject, text)
    got = deepdive.documents([{"subject": subject, "text": text, "category": cid, "url": "https://x/a.pdf", "at": "2026-08-01"}])
    assert [d["kind"] for d in got] == ([kind] if kind else [])


def test_no_calls_held_is_a_fact_not_two_gaps():
    view = {"region": "IN", "documents": [], "checklist": {"checks": [], "industry": {"path": ["x"]}}, "valuation": {"value": 1}}
    assert audit.check_view(view, meets=0) == [audit._issue("fact", "Documents", audit.NO_MEETS)]
    gaps = audit.check_view(view, meets=3)               # it held calls and filed nothing we found: worth a look
    assert [i["level"] for i in gaps] == ["gap", "gap"]
    assert len(audit.check_view(view)) == 2              # unknown (an older check): as before


def test_etfs_reits_and_invits_are_not_bse_companies():
    rows = [{"instrument_type": "EQ", "segment": "BSE", "tradingsymbol": t, "exchange_token": c, "name": n}
            for t, c, n in (("TATNIFTY", 590160, "Tata Nifty 50 ETF"), ("MOM100", 544130, "Mirae Asset Nifty Smallcap 250 Momen.Quali. 100ETF"),
                            ("GOLDETF", 590140, "Tata Gold Exchange Traded Fund"), ("PGINVIT", 543290, "Powergrid Infrastructure Investment Trust"),
                            ("EMBASSY", 542602, "Embassy Office Parks REIT"), ("CUBE", 544100, "Cube Highways Trust"),
                            ("RAJKOT", 506000, "Rajkot Investment Trust Ltd"), ("SILVEROAK", 531000, "Silver Oak (India) Ltd"))]
    assert [r["tradingsymbol"] for r in bse_only_rows(rows, [])] == ["RAJKOT", "SILVEROAK"]
    assert not_company("IRB InvIT Fund") and not not_company("Capital Trust Ltd")


def test_no_prices_says_why():
    fact = lambda why: audit.check_prices({}, None, None, why)[0]      # noqa: E731
    assert fact("new")["level"] == "fact" and "Listed recently" in fact("new")["detail"]
    assert fact("untraded")["level"] == "fact" and fact("stale")["level"] == "fact"
    assert fact("error")["level"] == "pending"
    assert fact(None)["level"] == "gap"                                  # unknown: still ours to look into


def test_price_status_reasons(monkeypatch):
    monkeypatch.setattr(universes, "resolve", lambda reg, m, members: ([], ["X"]))
    assert main.price_status("GONE") == (None, "untraded")
    monkeypatch.setattr(universes, "resolve", lambda reg, m, members: (["IN:1"], []))
    today = datetime.now(timezone.utc).date()
    bar = lambda d: {"t": (today - timedelta(days=d)).isoformat(), "o": 1, "h": 1, "l": 1, "c": 1, "v": 1}  # noqa: E731
    for bars, why in (([bar(i) for i in range(10, 0, -1)], "new"), ([bar(90 - i) for i in range(40)], "stale"), ([], "untraded")):
        monkeypatch.setattr(main.scan, "_bars", lambda reg, iid, b=bars: b)
        assert main.price_status("X") == (None, why)
    monkeypatch.setattr(main.scan, "_bars", lambda reg, iid: (_ for _ in ()).throw(RuntimeError("503")))
    assert main.price_status("X") == (None, "error")


def test_the_exact_symbol_is_found_before_a_search(monkeypatch):
    class Prov:
        def equity(self, s):
            return {"id": "IN:77", "symbol": "BI-BE", "type": "EQ", "exchange": "NSE"} if s == "BI" else None

        def search(self, q, allow_fno=False, limit=8):
            return [{"id": f"IN:{i}", "symbol": f"BI{i}", "type": "EQ", "exchange": "NSE"} for i in range(8)]

    class Reg:
        def provider(self, m):
            return Prov()
    assert universes.resolve(Reg(), "IN", [{"symbol": "BI"}]) == (["IN:77"], [])


def test_a_close_a_day_behind_the_last_trade_is_not_a_mismatch():
    """48 BSE-only stocks read 3-10% apart: a thinly traded stock's last daily close against today's last trade."""
    assert audit.check_prices({}, {"price": 170.20}, (163.00, 170.20)) == []           # matches the previous close
    found = audit.check_prices({}, {"price": 170.20}, (150.0, 151.0))
    assert found[0]["level"] == "mismatch" and "170.20 vs 150.00" in found[0]["detail"]
    assert audit.check_prices({}, {"price": 100.0}, 100.5) == []                       # a plain price still works


# ---------- facts about the company in the numbers and checklist ----------
def test_short_history_no_revenue_and_late_sales_are_facts():
    years = lambda *rows: {"years": [{"year": f"Mar {2020 + i}", "sales": s, "profit": p} for i, (s, p) in enumerate(rows)]}  # noqa: E731
    got = audit.check_numbers({}, years((10, 1), (12, 2)), {})
    assert got == [audit._issue("fact", "Numbers", audit.short_history(2))]
    got = [i for i in audit.check_numbers({}, years(*[(None, -5)] * 6), {}) if i["area"] == "Numbers"]
    assert got == [audit._issue("fact", "Numbers", audit.NO_REVENUE)]
    got = [i for i in audit.check_numbers({}, years((None, -5), (None, -4), (3, -2), (9, 1), (12, 2)), {}) if i["area"] == "Numbers"]
    assert got == [audit._issue("fact", "Numbers", "No revenue before Mar 2022: sales began then")]
    got = audit.check_numbers({}, years((10, 1), (None, 2), (12, 2), (13, 3), (14, 3)), {})
    assert got[0]["level"] == "gap" and "Mar 2021" in got[0]["detail"]               # a hole in the middle: ours


def test_checks_a_short_history_explains_are_a_fact():
    years = [{"year": f"Mar {2023 + i}", "sales": 10, "profit": 1} for i in range(3)]
    checks = [{"label": x, "state": "na"} for x in ("Sales growth, 3 years", "Profit growth, 3 years",
                                                     "Latest quarter sales vs a year ago", "Price in Stage 2")]
    view = {"region": "IN", "numbers": {"years": years, "quarters": [{}] * 3}, "documents": [{"kind": "presentation"}, {"kind": "transcript"}],
            "checklist": {"checks": checks, "industry": {"path": ["x"]}}, "valuation": {"value": 1}}
    got = audit.check_view(view)
    assert [i["level"] for i in got] == ["fact"] and "need more history" in got[0]["detail"]
    view["checklist"]["checks"] = [{"label": x, "state": "na"} for x in ("Return on capital employed", "Debt to equity",
                                                                         "Operating margin holding up", "Insider buying and selling, 6 months")]
    view["numbers"]["years"] = years * 3
    got = audit.check_view(view)
    assert got[0]["level"] == "gap" and got[0]["detail"].startswith("3 checks couldn't be judged")   # insiders: "None" is an answer


def test_valuation_says_why_when_ebitda_or_net_worth_is_negative():
    p = company()
    p["pl"]["rows"]["Operating Profit"] = [5, 5, 5, 5, 5, 5, -3]
    v = industry.valuation(p, {"market_cap_cr": 500}, "general", "cement")
    assert v["value"] is None and "EBITDA was negative" in v["why"]
    p["balance"]["rows"]["Reserves"] = [-80] * 6
    p["balance"]["rows"]["Equity Capital"] = [20] * 6
    v = industry.valuation(p, {"market_cap_cr": 500}, "lender", "lender")
    assert v["value"] is None and "net worth is negative" in v["why"]
    assert not audit.check_view({"valuation": v, "checklist": {"industry": {"path": ["x"]}}, "documents": [{"kind": "presentation"},
                                                                                                         {"kind": "transcript"}]})


# ---------- US ----------
def _f(v, end="2024-12-31", start="2024-01-01", form="10-K", filed="2025-02-20"):
    return {"start": start, "end": end, "val": v, "form": form, "filed": filed}


def _year(end_year, v, form="10-K"):
    return _f(v, f"{end_year}-12-31", f"{end_year}-01-01", form, f"{end_year + 1}-03-01")


def test_ifrs_filers_in_dollars_are_read():
    """A 40-F or 20-F filer under IFRS (a miner, a lessor) tags Revenue and ProfitLoss, not the US names."""
    facts = {"cik": 1, "entityName": "Gold Miner", "facts": {"ifrs-full": {
        "Revenue": {"units": {"USD": [_year(y, (y - 1000) * 1e6) for y in range(2019, 2025)]}},
        "ProfitLoss": {"units": {"USD": [_year(y, 100e6) for y in range(2019, 2025)]}},
        "PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities": {"units": {"USD": [_year(y, 50e6) for y in range(2019, 2025)]}},
        "Equity": {"units": {"USD": [{"end": f"{y}-12-31", "val": 900e6, "filed": f"{y + 1}-03-01"} for y in range(2019, 2025)]}},
    }}}
    p = sec.build(facts, {"sic": "1040", "name": "Gold Miner"})
    assert p["pl"]["rows"]["Sales"][-1] == 1024.0 and p["pl"]["rows"]["Net Profit"][-1] == 100.0
    assert p["cashflow"]["rows"]["Capex"][-1] == 50.0 and p["balance"]["rows"]["Equity"][-1] == 900.0


def test_a_filer_in_another_currency_is_not_covered():
    facts = {"facts": {"ifrs-full": {"Revenue": {"units": {"EUR": [_year(2024, 5e9)]}}}}}
    with pytest.raises(sec.SourceError) as e:
        sec.build(facts)
    assert "reports its results in EUR" in str(e.value)
    assert any(x in str(e.value) for x in audit.NOT_COVERED)


def test_bank_reit_and_profit_fallbacks():
    bank = {"us-gaap": {"InterestAndDividendIncomeOperating": {"units": {"USD": [_f(80)]}},
                        "NoninterestIncome": {"units": {"USD": [_f(20)]}}}}
    assert sec.revenue(bank, "annual") == {"2024-12-31": 100.0}            # interest plus fees: the bank's top line
    reit = {"us-gaap": {"RealEstateRevenueNet": {"units": {"USD": [_f(55)]}}}}
    assert sec.revenue(reit, "annual") == {"2024-12-31": 55.0}
    lp = {"us-gaap": {"IncomeLossFromContinuingOperations": {"units": {"USD": [_f(7)]}}}}
    assert sec.flows(lp, sec.NET_INCOME, "annual") == {"2024-12-31": 7.0}
    oil = {"us-gaap": {"PaymentsToAcquireOilAndGasPropertyAndEquipment": {"units": {"USD": [_f(30)]}}}}
    assert sec.flows(oil, sec.CAPEX, "annual") == {"2024-12-31": 30.0}


def test_shares_when_the_cover_page_has_none():
    """Two share classes give the cover-page count per class, which the facts leave out: no P/E or P/B followed."""
    facts = {"facts": {"us-gaap": {"Revenues": {"units": {"USD": [_year(2024, 500e6)]}},
                                   "NetIncomeLoss": {"units": {"USD": [_year(2024, 50e6)]}},
                                   "CommonStockSharesOutstanding": {"units": {"shares": [{"end": "2024-12-31", "val": 1e8, "filed": "2025-03-01"}]}}}}}
    p = sec.build(facts)
    assert p["shares"] == 1e8 and sec.ratios(p, 20.0)["Stock P/E"] == 40.0


def test_funds_spacs_and_derived_tickers_leave_the_us_universe(monkeypatch):
    for name in ("Adams Diversified Equity Fund Inc", "SPDR Gold Trust", "Grayscale Bitcoin Trust (BTC)", "AAC Acquisition Corp",
                 "BlackRock Municipal Income Trust", "iShares Gold Trust"):
        assert sec.not_operating(name), name
    for name in ("Northern Trust Corp", "Federal Realty Investment Trust", "Apple Inc.", "Fundamental Global Inc"):
        assert not sec.not_operating(name), name
    assert sec.derived_ticker("ALFUU", ["ALFU", "ALFUU"]) and not sec.derived_ticker("ALFUU", ["ALFUU"])
    from tests import world as W
    w = W.build(monkeypatch)
    try:
        monkeypatch.setattr(main.sec_feed, "tickers", lambda: {
            "ADX": {"cik": 1, "name": "Adams Diversified Equity Fund Inc"}, "ALFUU": {"cik": 2, "name": "Alfa Holdings Corp"},
            "ALFU": {"cik": 2, "name": "Alfa Holdings Corp"}, "ALFUW": {"cik": 2, "name": "Alfa Holdings Corp"},
            "BRK-B": {"cik": 3, "name": "Berkshire"}, "BRK-A": {"cik": 3, "name": "Berkshire"}})
        assert [c["symbol"] for c in main._sec_companies()] == ["ALFU", "BRK-B"]
    finally:
        w["close"]()


def test_a_spac_or_fund_is_a_fact_not_a_page_of_gaps():
    p = {"region": "US", "sic": "6770", "name": "Blank Check Co"}
    row = audit.audit_company("BLNK", lambda s: {"p": p}, lambda s, b: (_ for _ in ()).throw(AssertionError("not reached")))
    assert [i["level"] for i in row["issues"]] == ["fact"] and "SPAC" in row["issues"][0]["detail"]


def test_a_company_that_stopped_filing_is_one_fact():
    view = {"region": "US", "documents": [], "checklist": {"checks": [], "industry": {"path": ["x"]}}, "valuation": {"value": 1}}
    assert audit.check_view(view) == [audit._issue("fact", "Documents", audit.STOPPED_FILING)]
    view["documents"] = [{"kind": "annual_report", "form": "40-F"}]
    assert audit.check_view(view) == []                                     # a Canadian filer: no 10-Qs expected
