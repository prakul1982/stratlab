"""Fixes from the India whole-market audit sheet of 5 Oct 2026 (6,142 rows over 4,147 companies): the run kept going
after the broker's data login ended (605 companies "not checked yet" in one alphabetical block, three exchange
quotes refused); BSE closes compared with the last trade; companies that only meet investors, or file no decks,
read as gaps; companies without sales, loss-makers and suspended shares read as gaps in the checklist and
valuation; capex left blank where the balance sheet can't estimate it; and funds, trusts and DVR shares checked as
companies."""
from datetime import datetime

import httpx
import pytest

from app import audit, deepdive, industry, main
from app.intel import filings as F
from app.intel.screener import Screener
from tests.test_deepdive import company


@pytest.fixture
def w(monkeypatch):
    from tests import world as W
    world = W.build(monkeypatch)
    yield world
    world["close"]()


def _clean(sym):
    return {"symbol": sym, "name": sym, "seconds": 0.1, "issues": []}


# ---------- 605 "daily prices couldn't be read": the broker's login ended mid-run ----------
def test_the_market_audit_waits_while_the_price_feed_is_offline(w):
    ready, checked = [False], []
    a = audit.MarketAudit(lambda: [{"symbol": s, "name": s, "listed": "2001-01-01"} for s in ("AAA", "BBB")],
                          lambda s: checked.append(s) or _clean(s), pause=0, ready_fn=lambda: ready[0])
    a.refresh_list(force=True)
    a.start_full()
    a.set_enabled(True)
    assert a.step() is None and checked == []                       # nothing checked, nothing marked "not checked yet"
    assert a.status()["paused"] == "offline" and a.status()["due"] == 2
    ready[0] = True
    assert a.step() == "AAA" and a.status()["paused"] is None
    assert main.market_audit.ready_fn() == main.kite.ready()         # India waits on the broker's data login


def test_a_refused_quote_reads_once(monkeypatch):
    from app import report_card
    monkeypatch.setattr(deepdive, "stored", lambda s: None)
    monkeypatch.setattr(report_card, "stored", lambda s: None)

    def refused(sym):
        raise F.SourceError("NSE", "The exchange feed refused the request (403). Try again later.", busy=True)
    p = company()
    row = audit.audit_company("ACME", lambda s: {"p": p, "docs": [], "doc_note": None, "filings": None, "trend": {"price": 100.0}},
                              lambda s, b: main.deep_view(s, b), refused)
    got = [i for i in row["issues"] if i["area"] == "Prices"]
    assert got == [audit._issue("pending", "Prices", "Not checked yet: the exchange's quote couldn't be read "
                                                     "(The exchange feed refused the request (403)). It is checked again later.")]


# ---------- 37 BSE closes "vs the exchange's live quote", 3 "vs the company page" ----------
def test_a_bse_close_inside_the_same_days_range_agrees():
    """BSE's close is the average of the last half hour's trades: on a thin stock it can sit 4-10% from the last
    trade (79.99 against a close of 76.88) while still inside the day's range."""
    trend = {"price": 76.88, "t": "2026-10-03T00:00:00+05:30"}
    quote = {"price": 79.99, "prev_close": 73.50, "low": 74.00, "high": 80.50, "at": "2026-10-03T15:29:58"}
    assert audit.check_prices({}, trend, quote) == []
    later = {**quote, "at": "2026-10-05T10:02:00"}                  # the range is another day's: no excuse
    found = audit.check_prices({}, trend, later)
    assert found[0]["level"] == "mismatch" and "76.88 vs 79.99" in found[0]["detail"]
    assert audit.check_prices({}, trend, {**later, "prev_close": 76.88}) == []    # the session before: its close
    assert audit.check_prices({}, {"price": 100.0}, (101.0, 99.0)) == []         # a pair still works


def test_the_company_page_can_be_a_session_behind():
    trend = {"price": 351.80, "chg": -8.6}                          # yesterday's close was 385
    assert audit.check_prices({"price": 385.00}, trend, None) == []
    found = audit.check_prices({"price": 300.00}, trend, None)
    assert found[0]["level"] == "mismatch" and "vs 300.00 on the company page" in found[0]["detail"]


def test_a_thin_stock_page_price_can_be_several_sessions_old():
    trend = {"price": 351.80, "chg": -3.0, "recent": [385.00, 372.0, 360.5, 355.0, 351.80]}
    assert audit.check_prices({"price": 385.00}, trend, None) == []         # five sessions back
    assert audit.check_prices({"price": 360.50}, trend, None) == []
    found = audit.check_prices({"price": 399.00}, trend, None)              # matches none of them
    assert found[0]["level"] == "mismatch" and "vs 399.00 on the company page" in found[0]["detail"]
    old = {**trend, "recent": [385.00, 372.0, 360.5, 355.0, 351.80, 340.0]}  # only the last 5 count
    assert audit.check_prices({"price": 385.00}, old, None)[0]["level"] == "mismatch"


def test_the_trend_carries_the_last_five_closes():
    bars = [{"t": f"2026-09-{d:02d}", "o": 10 + d, "h": 11 + d, "l": 9 + d, "c": 10 + d} for d in range(1, 31)]
    assert main.scan.analyse(bars)["recent"] == [float(10 + d) for d in range(26, 31)]


def test_the_quote_carries_its_last_trade_time(w):
    q = main.kite.quote(["RELIANCE"])["RELIANCE"]
    assert q["at"][:10] == datetime.now(main.IST).date().isoformat()
    got = main.live_price("RELIANCE")
    assert set(got) == {"price", "prev_close", "low", "high", "at"} and got["low"] <= got["price"] <= got["high"]


# ---------- 279 "no call transcript", 113 "no investor presentation" ----------
MEET = "Analysts/Institutional Investor Meet/Con. Call Updates"


def _item(at, text, url="https://nsearchives.nseindia.com/corporate/X_01082026190000_a.pdf", subject=MEET):
    cid, sev = F.classify(subject, text)
    return {"at": at, "category": cid, "severity": sev, "subject": subject, "text": text, "url": url}


def test_meetings_tell_earnings_calls_from_investor_meetings():
    items = [_item("2026-08-10T10:00", "XYZ Ltd has informed the Exchange about Schedule of meet"),
             _item("2026-07-01T10:00", "XYZ Ltd has informed the Exchange about Schedule of meet"),
             _item("2026-06-01T10:00", "Outcome of board meeting: financial results", subject="Outcome of Board Meeting"),
             _item("2023-01-01T10:00", "Audio recording of the earnings call")]                 # before the window
    assert deepdive.meetings(items, "2024-10-05T00:00") == {"meets": 2, "calls": 0, "calls_due": 0, "filed": 3}
    items.insert(0, _item("2026-08-12T10:00", "XYZ Ltd has informed the Exchange about Audio Recording"))
    assert deepdive.meetings(items, "2024-10-05T00:00")["calls"] == 1


def test_only_investor_meetings_and_no_decks_are_facts():
    view = {"region": "IN", "documents": [], "checklist": {"checks": [], "industry": {"path": ["x"]}}, "valuation": {"value": 1}}
    got = audit.check_view(view, {"meets": 4, "calls": 0, "filed": 30})
    assert [i["level"] for i in got] == ["fact", "fact"]
    assert "though 4 of its filings" in got[0]["detail"] and got[1]["detail"] == audit.NO_CALLS


def test_no_filings_at_all_is_ours_to_look_into_unless_the_shares_are_idle():
    view = {"region": "IN", "documents": [], "checklist": {"checks": [], "industry": {"path": ["x"]}}, "valuation": {"value": 1}}
    nothing = {"meets": 0, "calls": 0, "filed": 0}
    assert audit.check_view(view, nothing) == [audit._issue("gap", "Documents", audit.NO_FILINGS_READ)]
    assert audit.check_view(view, nothing, "untraded") == [audit._issue("fact", "Documents", audit.NOTHING_FILED)]


def test_the_pdf_name_says_what_a_filing_is_and_decks_cant_crowd_out_transcripts():
    named = _item("2026-08-12T10:00", "XYZ Ltd has informed the Exchange about Updates",
                  url="https://nsearchives.nseindia.com/corporate/XYZ_12082026193000_Q1FY27ConcallTranscript.pdf")
    letter = _item("2026-08-01T10:00", "XYZ Ltd has informed the Exchange about Shareholders' Letter for Q1 FY27", subject="Updates")
    assert [d["kind"] for d in deepdive.documents([named, letter])] == ["transcript", "presentation"]
    decks = [_item(f"2026-08-{d:02d}T10:00", "Investor Presentation") for d in range(28, 6, -1)]
    old = _item("2026-02-10T10:00", "Transcript of the Q3 earnings call")
    assert "transcript" not in [d["kind"] for d in deepdive.documents(decks + [old])[:20]]   # the old cut lost it
    got = deepdive.documents(decks + [old], per_kind=8)
    assert [d["kind"] for d in got].count("presentation") == 8 and got[-1]["kind"] == "transcript"


def test_bse_is_asked_a_year_at_a_time():
    """Checked live on 5 Oct 2026: BSE answers a range over twelve months with {"Status": false, "Message": "Date range
    cannot exceed 12 months."} and no table, which read as "filed nothing" for all 2,492 BSE-only companies."""
    asked = []

    def handler(r):
        if r.url.host == "www.bseindia.com":
            return httpx.Response(200, text="<html></html>")
        frm, to = r.url.params["strPrevDate"], r.url.params["strToDate"]
        asked.append((frm, to))
        if (datetime.strptime(to, "%Y%m%d") - datetime.strptime(frm, "%Y%m%d")).days > 365:
            return httpx.Response(200, json={"Status": False, "Message": "Date range cannot exceed 12 months."})
        table = [{"NEWSID": f"n{frm}", "DissemDT": f"{to[:4]}-{to[4:6]}-{to[6:]}T10:00:00",
                  "NEWSSUB": "A Ltd - 543210 - Analyst / Investor Meet - Intimation",
                  "SUBCATNAME": "Analyst / Investor Meet - Intimation", "HEADLINE": "", "ATTACHMENTNAME": "a.pdf"}]
        return httpx.Response(200, json={"Table": table, "Table1": [{"ROWCNT": 1}]})
    feed = F.BSEFilings(transport=httpx.MockTransport(handler), sleep=lambda s: None)
    items = feed.announcements("543210", 732)
    assert len(asked) == 3 and len(items) == 3 and items[0]["category"] == "concall"   # 365 + 365 + 2 days
    days = [(datetime.strptime(t, "%Y%m%d") - datetime.strptime(f, "%Y%m%d")).days for f, t in asked]
    assert max(days) <= 365
    assert all(datetime.strptime(asked[i + 1][1], "%Y%m%d") < datetime.strptime(asked[i][0], "%Y%m%d") for i in range(2))
    asked.clear()
    assert len(feed.announcements("543210", 365)) == 1 and len(asked) == 1     # a year is one request
    feed.WINDOW = 400                                                          # asked for more: said, not read as nothing
    with pytest.raises(F.SourceError) as e:
        feed.announcements("543211", 400)
    assert "Date range cannot exceed 12 months" in str(e.value) and not e.value.busy


# ---------- 299 checklist rows: companies without sales ----------
def test_checks_a_company_without_sales_cant_judge_are_a_fact():
    years = [{"year": f"Mar {2019 + i}", "sales": s, "profit": -1, "opm": None if not s else 5} for i, s in enumerate([5, 4, 3, 0, 0, 0, 0])]
    quarters = [{"quarter": f"Q{i}", "sales": 0} for i in range(8)]
    checks = [{"label": x, "state": "na"} for x in ("Sales growth, 3 years", "Latest quarter sales vs a year ago",
                                                     "Operating margin holding up", "Return on capital employed")]
    view = {"region": "IN", "numbers": {"years": years, "quarters": quarters}, "documents": [{"kind": "presentation"}, {"kind": "transcript"}],
            "checklist": {"checks": checks, "industry": {"path": ["x"]}}, "valuation": {"value": 1}}
    got = audit.check_view(view)
    assert got == [audit._issue("fact", "Checklist", "3 checks can't be judged without sales (none in a year compared): "
                                                     "Sales growth, 3 years, Latest quarter sales vs a year ago, Operating margin holding up")]
    years[-1]["sales"] = years[-4]["sales"] = 9                       # sales there: a missing number is still ours
    quarters[-1]["sales"] = quarters[-5]["sales"] = None
    assert audit.check_view(view)[0]["level"] == "gap"


# ---------- 70 no P/E, 9 no P/B, 4 no EV/EBITDA ----------
def test_valuation_is_computed_or_says_why_its_blank():
    p = company()                                                     # trailing profit 26
    v = industry.valuation(p, {"market_cap_cr": 520}, "general", "general")
    assert v["value"] == 20.0 and "market value divided by" in v["why"]
    p["pl"]["rows"]["EPS"] = [1, 1, 1, 1, 1, 1, -0.4]                 # the group made money, its shareholders didn't
    v = industry.valuation(p, {"market_cap_cr": 520}, "general", "general")
    assert v["value"] is None and "made a loss" in v["why"]
    for short, group, key in (("P/E", "general", "general"), ("P/B", "lender", "lender"), ("EV/EBITDA", "general", "cement")):
        v = industry.valuation(company(), {}, group, key)                # suspended: no market value on the page
        assert v["value"] is None and f"There's no {short} here: the company page shows no market value" in v["why"], short
        assert not audit.check_view({"valuation": v, "checklist": {"industry": {"path": ["x"]}},
                                     "documents": [{"kind": "presentation"}, {"kind": "transcript"}]})
    v = industry.valuation({**company(), "balance": None}, {"market_cap_cr": 500}, "lender", "lender")
    assert v["value"] is None and "no balance sheet" in v["why"]


# ---------- 60 no capex estimate ----------
def test_capex_comes_from_the_cash_flow_when_the_balance_sheet_cant_estimate_it():
    p = company()
    p.update(company_id="77", basis="standalone")
    p["balance"]["rows"]["Fixed Assets"] = [95, 80, 65, 50, 35, 20]   # shrinking: assets sold
    assert all(y["capex"] is None for y in deepdive.numbers(p)["years"][-3:])
    asked = []

    def handler(r):
        asked.append(dict(r.url.params))
        return httpx.Response(200, json={"Fixed assets purchased": {"Mar 2023": "-4", "Mar 2024": "-6", "Mar 2025": "-3"},
                                         "Fixed assets sold": {"Mar 2023": "12", "Mar 2024": "10", "Mar 2025": "9"}})
    got = Screener(transport=httpx.MockTransport(handler)).with_capex(p)
    assert asked[0]["parent"] == "Cash from Investing Activity" and asked[0]["section"] == "cash-flow"
    n = deepdive.numbers(got)
    assert [y["capex"] for y in n["years"][-3:]] == [4, 6, 3] and n["capex_reported"]
    assert not [i for i in audit.check_numbers(got, n, {}) if i["area"] == "Capex"]


# ---------- 17 operating margins above 100% ----------
def test_margins_above_100_are_read_against_sales_and_costs():
    def page(sales, costs):
        return {"pl": {"cols": ["Mar 2024", "Mar 2025"], "rows": {"Sales": sales, "Expenses": costs}}}
    years = [{"year": "Mar 2024", "sales": -0.5, "profit": 1, "opm": 300}, {"year": "Mar 2025", "sales": 2, "profit": 1, "opm": 150}]
    got = audit.check_numbers(page([-0.5, 2], [1, -1]), {"years": years}, {})
    assert [(i["level"], i["detail"][:22]) for i in got if i["area"] == "Numbers"][1:] == [
        ("fact", "Sales were nil or nega"), ("fact", "Costs were written bac")]
    got = audit.check_numbers(page([-0.5, 2], [1, 1]), {"years": years}, {})
    assert "Mar 2025 that its sales and costs don't explain" in got[-1]["detail"] and got[-1]["level"] == "gap"
    us = audit.check_numbers({"region": "US"}, {"years": years}, {})
    assert "The filings show an operating margin above 100% in Mar 2024, Mar 2025 (costs written back)" in [i["detail"] for i in us]


# ---------- 7 no industry, 8 no annual results, funds and trusts ----------
def test_a_new_listing_or_dvr_without_results_or_classification_is_a_fact():
    view = {"region": "IN", "documents": [{"kind": "presentation"}, {"kind": "transcript"}],
            "checklist": {"checks": [], "industry": {"label": "General"}}, "valuation": {"value": 1}}
    assert audit.check_view(view)[0]["level"] == "gap"
    assert audit.check_view(view, None, "new")[0]["level"] == "fact"
    assert audit.check_numbers({"name": "Jain Irrigation Systems Ltd-DVR"}, {}, {}) == [audit._issue("fact", "Numbers", audit.NO_RESULTS_DVR)]
    assert audit.check_numbers({}, {}, {}, young=True) == [audit._issue("fact", "Numbers", audit.NO_RESULTS_YET)]
    assert audit.check_numbers({}, {}, {})[0]["level"] == "gap"


def test_an_etf_or_trust_the_broker_names_otherwise_is_not_checked_as_a_company():
    for name in ("Aditya Birla Sun Life MSCI India ETF", "Property Share Investment Trust-Propshare Celestia",
                 "Digital Fibre Infrastructure Trust"):
        row = audit.audit_company("544706", lambda s: {"p": {"name": name, "region": "IN"}}, None)
        assert row["name"] == name and row["issues"] == [
            audit._issue("fact", "Company page", f"Not an operating company: {audit.FUND_OR_TRUST}, so there are no business numbers to check")]
