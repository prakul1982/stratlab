"""The India data code against trimmed samples of what the exchanges, the company-data site and the industry body's
NAV file actually answered on 5 Oct 2026 (tests/fixtures/*/..._2026-10-05.* and the like). Each test says what the live
answer showed that the earlier code had assumed otherwise."""
import json
from datetime import datetime
from pathlib import Path

import httpx
import pytest

from app import main  # noqa: F401  (the app first: its modules import each other in that order)
from app import audit, deepdive, etf_nav as E, fo_changes as FO, money_mf_nav
from app.intel import filings as F
from app.intel.screener import Screener

FIX = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 10, 5, 12, 0)


def _json(path: str):
    return json.loads((FIX / path).read_text())


# ---------- BSE announcements ----------
def _bse_feed(asked: list):
    sample = _json("bse/announcements_500325.json")

    def handler(r):
        if r.url.host == "www.bseindia.com":
            return httpx.Response(200, text="<html></html>")
        frm, to = (datetime.strptime(r.url.params[k], "%Y%m%d") for k in ("strPrevDate", "strToDate"))
        asked.append((frm, to))
        if (to - frm).days > 365:
            return httpx.Response(200, json={"Status": False, "Message": "Date range cannot exceed 12 months."})
        rows = [x for x in sample["Table"] if frm.date().isoformat() <= x["DissemDT"][:10] <= to.date().isoformat()]
        return httpx.Response(200, json={"Table": rows if r.url.params["pageno"] == "1" else [], "Table1": [{"ROWCNT": len(rows)}]})
    return F.BSEFilings(transport=httpx.MockTransport(handler), sleep=lambda s: None)


def test_bse_two_years_of_filings_come_back_with_the_calls_and_documents(monkeypatch):
    monkeypatch.setattr(F, "ist_now", lambda: NOW)
    asked = []
    items = _bse_feed(asked).announcements("500325", 732)
    assert len(asked) == 3 and all((to - frm).days <= 365 for frm, to in asked)
    assert len(items) == 4 and all(i["url"].startswith("https://www.bseindia.com/xml-data/corpfiling/AttachHis/") for i in items)
    docs = deepdive.documents(items)
    # the transcript filed under "Analyst / Investor Meet - Outcome"; the deck explaining a postal ballot's resolutions
    # is not the company's investor presentation
    assert [d["kind"] for d in docs] == ["transcript"]
    told = deepdive.meetings(items, "2024-10-05T00:00")
    assert told == {"meets": 2, "calls": 1, "calls_due": 1, "shareholder": 1, "filed": 4}
    assert not audit._india_documents([d["kind"] for d in docs], told, None)[1:]       # a transcript: no call gap


# ---------- NSE announcements ----------
def test_a_promoters_yearly_no_encumbrance_declaration_is_not_a_pledge():
    """Infosys's promoters each file a Regulation 31(4) declaration every year (27 of them in the last year): they say
    no shares were encumbered, and read as 27 red "promoter pledge" flags."""
    desc = "Disclosure under SEBI Takeover Regulations"
    text = ("Infosys Limited has Submitted to the Exchange a copy of Disclosure under Regulation 31(4) of the Securities "
            "and Exchange Board of India (Substantial Acquisition of Shares and Takeovers) Regulations, 2011.")
    assert F.classify(desc, text)[0] != "pledge"
    assert F.classify(desc, "Creation of pledge on promoter shares, Regulation 31(1)") == ("pledge", "red")
    assert F.classify(desc, "Disclosure under Regulation 31 of encumbrance") == ("pledge", "red")


def _item(subject, text, cat=None, at="2026-07-01T10:00", url="https://nsearchives.nseindia.com/corporate/X_1.pdf"):
    return {"subject": subject, "text": text, "category": cat or F.classify(subject, text)[0], "at": at, "url": url}


def test_shareholder_meeting_transcripts_and_decks_are_not_calls_or_investor_decks():
    """Live: Infosys files its AGM's transcript, Aarti Surfactants a "presentation made to shareholders at the AGM",
    Reliance decks for postal-ballot resolutions. None of them is an earnings call or the business presentation."""
    agm_t = _item("Updates", "Infosys Limited has informed the Exchange regarding 'Transcript of the 45th Annual General Meeting'.")
    agm_p = _item("Updates", "Aarti Surfactants Limited has informed the Exchange regarding 'Presentation made to shareholders "
                             "at 8th Annual General Meeting'")
    ballot = _item("General", "Presentation On The Resolutions Proposed For Shareholders' Approval Vide Postal Ballot Notice")
    call_t = _item("Updates", "Infosys Limited has informed the Exchange regarding 'Earnings Call Transcript'.")
    deck = _item("Investor Presentation", "HDFC Bank Limited has informed the Exchange about Investor Presentation")
    assert deepdive.documents([agm_t, agm_p, ballot]) == []
    assert [d["kind"] for d in deepdive.documents([call_t, deck])] == ["transcript", "presentation"]
    assert agm_t["category"] == "agm"                             # a shareholder meeting, never labelled an earnings call
    assert deepdive.meetings([agm_t], "2024-01-01T00:00") == {"meets": 0, "calls": 0, "calls_due": 0, "shareholder": 1, "filed": 1}
    assert deepdive.meetings([agm_t, call_t], "2024-01-01T00:00") == {"meets": 1, "calls": 1, "calls_due": 1, "shareholder": 1, "filed": 2}


def test_no_call_with_no_meetings_told_says_so():
    """Live: Aarti Surfactants filed a deck but told the exchange of no calls or meetings at all."""
    got = audit._india_documents(["presentation"], {"meets": 0, "calls": 0, "filed": 91}, None)
    assert [i["detail"] for i in got] == [audit.NO_CALLS_TOLD]
    got = audit._india_documents(["presentation"], {"meets": 3, "calls": 0, "filed": 91}, None)
    assert [i["detail"] for i in got] == [audit.NO_CALLS]


# ---------- the capex line of the cash flow breakdown ----------
def test_capex_from_the_real_cash_flow_breakdown():
    page = _json("screener/cashflow_abrel.json")
    p = {"company_id": page["company_id"], "basis": page["basis"], "cashflow": {"cols": page["cols"], "rows": page["rows"]}}
    assert not any(k.lower().startswith("capex") for k in page["rows"])      # the page shows only the investing total
    asked = []

    def handler(r):
        asked.append(dict(r.url.params))
        return httpx.Response(200, json=_json("screener/schedules_cash_investing_abrel.json"))
    got = Screener(transport=httpx.MockTransport(handler)).with_capex(p)
    assert asked == [{"parent": "Cash from Investing Activity", "section": "cash-flow", "consolidated": "true"}]
    assert got["cashflow"]["rows"]["Capex"][-3:] == [-181.0, -286.0, -212.0]           # outflows: read as their size


# ---------- the last close against the live quote ----------
# BSE-only companies from the 5 Oct sheet's 37 price mismatches, with BSE's own record of 1 Oct 2026 (the last
# session before the sheet): our close is BSE's official close, the quote's price the session's last trade
REAL = [  # code, our close, quote price, day low, day high, previous close
    ("538520", 1.95, 1.78, 1.78, 1.96, 1.87),
    ("523100", 170.20, 163.00, 157.20, 172.00, None),
    ("513252", 775.60, 740.00, 740.00, 815.05, None),
    ("538714", 37.86, 34.20, 34.20, 38.00, None),
    ("544399", 79.45, 77.00, 77.00, 88.00, None),
    ("531667", 43.24, 47.44, 43.11, 47.63, None),
]


@pytest.mark.parametrize("code,ours,price,low,high,prev", REAL)
def test_a_bse_close_and_the_last_trade_of_the_same_session_agree(code, ours, price, low, high, prev):
    q = {"price": price, "prev_close": prev, "low": low, "high": high, "at": "2026-10-01T15:29:58"}
    assert audit._agrees(ours, "2026-10-01T00:00:00+05:30", q)
    assert not audit._agrees(ours, "2026-09-30T00:00:00+05:30", q)          # another day's close: still a mismatch
    assert not audit.check_prices({}, {"price": ours, "t": "2026-10-01T00:00:00+05:30", "chg": 0}, q)


# ---------- the F&O contract file and circulars ----------
def test_the_live_contract_file_lists_long_dated_index_months_and_only_real_exits_come_out():
    """The live file lists the long-dated index options (MAR-27 to JUN-31); judged against those, every stock read as
    leaving F&O (218 of them). Against the monthly series, three do, as the exchange's exclusion circular says."""
    lots = FO.read_lots((FIX / "fo_changes/fo_mktlots_live_2026-10-05.csv").read_text())
    assert lots["months"][:4] == ["2026-10", "2026-11", "2026-12", "2027-03"] and lots["months"][-1] == "2031-06"
    assert FO.serial_months(lots["months"]) == ["2026-10", "2026-11", "2026-12"]
    assert lots["rows"]["NIFTY"]["index"] and not lots["rows"]["IEX"]["index"]
    got = FO.derive(lots, lambda sym, month: FO.rule_expiry(month))
    assert [(e["kind"], e["symbol"], e["series"]) for e in got] == [
        ("exit", "BAJAJHLDNG", "2026-10"), ("exit", "IEX", "2026-11"), ("exit", "IREDA", "2026-11")]


def test_only_the_fo_desks_circulars_are_read_with_their_dates():
    """Live, the circulars answer mixes every department: commodity "futures", SME "market lot" adjustments, gold
    receipt "trading hours", clearing limits. Its first date field is "cirDate": "20261001"."""
    got = FO.read_circulars(_json("fo_changes/circulars_live_2026-10-05.json"), FO.INDEX_NAMES)
    assert got and all(c["no"].startswith("NSE/FAOP/") for c in got)
    assert all(c["date"] and c["date"].startswith("2026-") for c in got)
    assert not [c for c in got if "mock trading" in c["subject"].lower()]
    kinds = {c["subject"]: c["kind"] for c in got}
    assert kinds["Exclusion of Futures and Options contracts on Two Securities"] == "exit"
    assert kinds["Introduction of Futures & Options Contracts on Three Individual Securities"] == "entry"
    assert kinds["Revision in Market Lot of Derivative Contracts on Individual Stocks"] == "lot"
    assert kinds["Quantity Freeze Limits for Indices"] == "circular"
    assert len({c["id"] for c in got}) == len(got)


# ---------- ETF prices against NAV ----------
class _EtfFeed:
    def etf_list(self):
        return _json("etf/etf_list_2026-10-05.json")

    def etf_securities(self):
        return F.etf_isins((FIX / "etf/eq_etfseclist_2026-10-05.csv").read_text())


def test_the_live_etf_list_gives_the_last_nav_and_the_isins_come_from_the_securities_file(monkeypatch):
    """Live: the list's "nav" equals the evening NAV file's NAV to the paisa for 345 of 346 ETFs (it is the published
    NAV, dated by "navDate", not an indicative NAV); it carries no ISIN, so no NAV was ever matched; and "assets"
    names the underlying ("Gold"), not the fund."""
    monkeypatch.setattr(E, "load_live", lambda: {"read": None, "as_of": None, "rows": {}})
    parsed = E.parse_exchange(_EtfFeed().etf_list())
    assert parsed["as_of"] == "2026-10-05T12:12+05:30"
    gold = parsed["rows"]["GOLDBEES"]
    assert (gold["inav"], gold["nav"], gold["nav_date"], gold["isin"], gold["name"]) == (None, 121.5196, "2026-10-04", "", "Gold")
    E.add_isins(parsed, _EtfFeed())
    assert parsed["rows"]["NIFTYBEES"]["isin"] == "INF204KB14I2" and all(r["isin"] for r in parsed["rows"].values())
    navs = money_mf_nav.parse((FIX / "etf/navall_2026-10-05.txt").read_text())
    v = E.row_view("GOLDBEES", parsed["rows"]["GOLDBEES"], navs, parsed["as_of"])
    assert (v["name"], v["basis"], v["nav"], v["nav_date"], v["inav"]) == ("Nippon India ETF Gold BeES", "NAV", 121.5196, "2026-10-01", None)
    assert v["text"] == "GOLDBEES trades 0.28% below its last NAV"
    fang = E.row_view("MAFANG", parsed["rows"]["MAFANG"], navs, parsed["as_of"])
    assert fang["gap"] == 42.69 and fang["basis"] == "NAV"                   # an overseas ETF's real premium
    # with no NAV file match, the list's own NAV and date stand in
    alone = E.row_view("GOLDBEES", parsed["rows"]["GOLDBEES"], {"schemes": {}, "isin": {}}, parsed["as_of"])
    assert (alone["nav"], alone["nav_date"], alone["basis"]) == (121.5196, "2026-10-04", "NAV")


def test_etf_isins_reads_the_columns_by_name():
    assert F.etf_isins("Symbol,Underlying Asset,ISINNumber\nNIFTYBEES,Nifty 50,INF204KB14I2\nBAD,x,notanisin\n") == {
        "NIFTYBEES": "INF204KB14I2"}
    assert F.etf_isins("") == {} and F.etf_isins("a,b\n1,2\n") == {}
