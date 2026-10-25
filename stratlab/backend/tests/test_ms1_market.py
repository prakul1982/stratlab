"""MS1: the whole-market sweep. A US company that has traded for decades is not a new listing because the SEC's list gained
it; a share that has just listed is checked the day it appears, each day of its first weeks, and with the checks only a
new listing has (the range since listing, the first session against the issue price, the market value on the shares in
issue now, no growth rate from a tiny base); a read of the list that comes back short is a failed read."""
from datetime import date, datetime, timedelta, timezone

import pytest

from app import audit


def _clean(sym):
    return {"symbol": sym, "name": sym, "seconds": 0.1, "issues": []}


@pytest.fixture
def w(monkeypatch):
    from tests import world as W
    world = W.build(monkeypatch)
    yield world
    world["close"]()


def _market(n, prefix="S"):
    return [{"symbol": f"{prefix}{i:04d}", "name": f"{prefix}{i}", "listed": None} for i in range(n)]


# ---------- MS1-005: the US list's "new listings" ----------
def test_a_list_that_gains_hundreds_of_companies_at_once_adds_no_new_listings(w):
    """NVDA, AAPL and MSFT were shown as new listings: the list gained them in a body (a partial read before), and a
    missing listing date counted as new."""
    big = _market(300)
    a = audit.MarketAudit(lambda: big[:100], _clean, pause=0, key="audit:ms1-us")
    a.refresh_list(force=True)
    a.list_fn = lambda: big
    a.refresh_list(force=True)
    assert a.status()["new_listings"] == [] and not any(i.get("seen") for i in a.listing.values())


def test_a_stored_list_with_hundreds_first_seen_on_one_day_is_put_right_on_load(w):
    a = audit.MarketAudit(lambda: _market(200), _clean, pause=0, key="audit:ms1-stored")
    a.refresh_list(force=True)
    today = datetime.now(timezone.utc).date().isoformat()
    for i in a.listing.values():
        i["seen"] = today                      # what the live list holds: every ticker "first seen" together
    a.listing["S0005"]["seen"] = None
    a._save("list")
    b = audit.MarketAudit(lambda: _market(200), _clean, pause=0, key="audit:ms1-stored")
    assert b.status()["new_listings"] == []


def test_a_company_new_to_the_list_is_a_listing_only_if_it_began_trading_recently(w):
    today = datetime.now(timezone.utc).date()
    first = {"OLDCO": (today - timedelta(days=4000)).isoformat(), "NEWCO": (today - timedelta(days=3)).isoformat()}

    def dates(sym):
        if sym == "NOWAY":
            raise RuntimeError("the price source is down")
        return first.get(sym)
    listing = _market(150)
    a = audit.MarketAudit(lambda: listing, _clean, pause=0, key="audit:ms1-dates", date_fn=dates)
    a.refresh_list(force=True)
    listing = listing + [{"symbol": s, "name": s, "listed": None} for s in ("OLDCO", "NEWCO", "NOWAY")]
    a.list_fn = lambda: listing
    a.refresh_list(force=True)
    new = {n["symbol"]: n["listed"] for n in a.status()["new_listings"]}
    assert new == {"NEWCO": first["NEWCO"], "NOWAY": None}                    # the old one isn't; one whose date can't be read is, for now
    assert a.listing["OLDCO"]["listed"] == first["OLDCO"]
    assert sorted(a.queue()[:2]) == ["NEWCO", "NOWAY"]                         # and they are checked first


def test_a_list_read_that_comes_back_short_keeps_the_last_good_list_and_every_result(w):
    market = _market(200)
    a = audit.MarketAudit(lambda: market, _clean, pause=0, key="audit:ms1-short")
    a.refresh_list(force=True)
    a.rows["S0001"] = {**_clean("S0001"), "at": "2026-10-25T00:00:00+00:00"}
    a.list_fn = lambda: market[:20]
    assert a.refresh_list(force=True) is False
    s = a.status()
    assert s["listed"] == 200 and "keeping the last one" in s["list_error"] and "S0001" in a.rows
    a.list_fn = lambda: market[:190]                                           # ten delisted is a real change
    assert a.refresh_list(force=True) is True and a.status()["listed"] == 190


# ---------- MS1-006: a new listing is checked the day it lists, then every day ----------
def test_a_new_listing_is_checked_the_day_it_appears_and_again_each_day_of_its_first_weeks(w):
    today = date.today()
    listing = [{"symbol": "OLD", "name": "OLD", "listed": "2001-01-01"},
               {"symbol": "TODAY", "name": "TODAY", "listed": today.isoformat()},
               {"symbol": "WEEKOLD", "name": "WEEKOLD", "listed": (today - timedelta(days=7)).isoformat()},
               {"symbol": "MONTHOLD", "name": "MONTHOLD", "listed": (today - timedelta(days=45)).isoformat()}]
    a = audit.MarketAudit(lambda: listing, _clean, pause=0, key="audit:ms1-new")
    a.set_enabled(True)
    a.refresh_list(force=True)
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    a.rows["WEEKOLD"] = {**_clean("WEEKOLD"), "at": yesterday}
    a.rows["MONTHOLD"] = {**_clean("MONTHOLD"), "at": yesterday}
    assert a.queue() == ["TODAY", "WEEKOLD"]                                   # the unchecked listing, then the one not yet seen today
    assert [a.step(), a.step()] == ["TODAY", "WEEKOLD"] and a.step() is None   # and the old ones aren't repeated by this
    a.rows["TODAY"]["at"] = yesterday
    assert a.queue() == ["TODAY"]                                              # the next day it is checked again


def test_the_list_is_read_every_six_hours(w):
    calls = [0]

    def lst():
        calls[0] += 1
        return _market(5)
    a = audit.MarketAudit(lst, _clean, pause=0, key="audit:ms1-six")
    assert a.refresh_list() is True and a.refresh_list() is False
    a.state["list_tried_at"] = (datetime.now(timezone.utc) - timedelta(hours=7)).isoformat()
    assert a.refresh_list() is True and calls[0] == 2


# ---------- MS1-006: the checks only a new listing has ----------
def _page(since="2026-10-23", ref="issue", change=-2.26, at="2026-10-23T10:00:00+00:00", prev=1160.0):
    return {"range52": {"low": 1100, "high": 1300, **({"since": since} if since else {})},
            "quote": {"price": 1134, "at": at, "ref": ref, "change_pct": change, "prev_close": prev}}


def _p(cols=("Mar 2025", "Mar 2026"), cap=6495.0, price=1134.0):
    return {"region": "IN", "balance": {"cols": list(cols)}, "ratios": {"Market Cap": str(cap), "Current Price": str(price)}}


def test_a_new_listings_range_is_since_listing_and_its_first_day_is_against_the_issue_price():
    nums = {"years": [{"year": "Mar 2026", "sales": 100.0, "profit": 10.0}]}
    snap = {"price": 1134.0, "market_cap_cr": 6495.0}
    assert audit.check_listing(_page(), _p(), nums, snap) == []
    got = audit.check_listing(_page(since=None), _p(), nums, snap)
    assert [(i["level"], i["area"]) for i in got] == [("gap", "New listing")] and "since listing" in got[0]["detail"]
    got = audit.check_listing(_page(ref=None, change=-8.4, prev=151.0), _p(), nums, snap)       # the open as the base, as the exchange does not
    assert [i["level"] for i in got] == ["mismatch"] and "issue price" in got[0]["detail"]
    got = audit.check_listing(_page(ref=None, change=None, prev=None), _p(), nums, snap)       # no issue price known: said, not guessed
    assert [(i["level"], "isn't known yet" in i["detail"]) for i in got] == [("fact", True)]
    later = _page(at="2026-10-26T10:00:00+00:00", ref=None, change=1.5, prev=1117.0)             # the third day: the usual previous close
    assert audit.check_listing(later, _p(), nums, snap) == []


def test_the_market_value_of_a_new_listing_counts_the_shares_in_issue_now():
    """DD-011: a balance sheet from before the issue has the old share count; TONBO's value was Rs 6,236 cr against 6,495."""
    nums = {"years": []}
    page = _page()
    got = audit.check_listing(page, _p(), nums, {"price": 1134.0, "market_cap_cr": 6236.0})
    assert [i["level"] for i in got] == ["mismatch"] and "6,236" in got[0]["detail"] and "6,495" in got[0]["detail"]
    assert audit.check_listing(page, _p(), nums, {"price": 1134.0, "market_cap_cr": 6495.0}) == []
    assert audit.check_listing(page, _p(cols=("Mar 2026", "Oct 2026")), nums, {"price": 1134.0, "market_cap_cr": 6236.0}) == []   # a balance sheet after the issue


def test_a_growth_rate_from_a_tiny_base_must_be_said_n_m():
    years = [{"year": f"Mar {2022 + i}", "sales": s, "profit": p} for i, (s, p) in enumerate(((97.0, 1.0), (140.0, 8.0), (260.0, 30.0), (420.0, 50.0)))]
    nums = {"years": years, "growth_nm": {}}
    got = audit.check_listing(_page(), _p(), nums, {"price": 1134.0, "market_cap_cr": 6495.0})
    assert [i["level"] for i in got] == ["mismatch"] and "profit growth rate" in got[0]["detail"] and "Mar 2022" in got[0]["detail"]
    nums["growth_nm"] = {"profit_cagr_3y": {"from": 1.0, "year": "Mar 2022"}}
    assert audit.check_listing(_page(), _p(), nums, {"price": 1134.0, "market_cap_cr": 6495.0}) == []


def test_the_listing_checks_run_for_a_share_that_has_traded_under_30_days_only():
    seen = []

    def base(sym):
        return {"p": {"name": "N", "region": "IN"}, "trend": None, "trend_why": why[0], "told": {"filed": 5, "meets": 1, "calls": 0}}
    view = {"name": "N", "numbers": {"years": [], "quarters": []}, "snapshot": {}, "documents": [], "checklist": {"industry": {"path": ["x"]}}, "valuation": {"value": 1}}
    why = ["new"]
    row = audit.audit_company("NEWCO", base, lambda s, b: view, None, None, lambda s: seen.append(s) or _page(since=None))
    assert seen == ["NEWCO"] and any(i["area"] == "New listing" and i["level"] == "gap" for i in row["issues"])
    why[0] = None
    seen.clear()
    audit.audit_company("OLDCO", base, lambda s, b: view, None, None, lambda s: seen.append(s) or _page())
    assert seen == []

    def broken(sym):
        raise RuntimeError("The exchange feed refused the request (403). Try again later.")
    why[0] = "new"
    row = audit.audit_company("NEWCO", base, lambda s, b: view, None, None, broken)
    assert any(i["area"] == "New listing" and i["level"] == "pending" for i in row["issues"])


# ---------- MS1: the audit's other findings ----------
def _view(**kw):
    return {"region": kw.pop("region", "IN"), "documents": kw.pop("documents", [{"kind": "presentation"}, {"kind": "transcript"}]),
            "checklist": {"checks": kw.pop("checks", []), "industry": {"path": ["x"]}}, "valuation": {"value": 1}, **kw}


def test_calls_held_long_ago_with_no_transcript_filed_are_the_companys_omission_not_ours():
    """MS1-008: 24 Indian companies filed notices of earnings calls and never a transcript (due within five working days)."""
    view = _view(documents=[{"kind": "presentation"}])
    old = audit.check_view(view, {"meets": 9, "calls": 9, "calls_due": 9, "calls_old": 7, "filed": 90})
    assert [i["level"] for i in old] == ["fact"] and "none to read" in old[0]["detail"] and "five working days" in old[0]["detail"]
    recent = audit.check_view(view, {"meets": 1, "calls": 1, "calls_due": 1, "calls_old": 0, "filed": 90})
    assert [i["level"] for i in recent] == ["gap"]                      # a call of the last weeks: the transcript may still be looked for
    from app import deepdive
    from app.intel.filings import ist_now
    day = lambda n: (ist_now() - timedelta(days=n)).strftime("%Y-%m-%dT%H:%M")      # noqa: E731
    items = [{"at": day(60), "category": "concall", "subject": "Earnings call", "text": "Earnings call on results", "url": "a.pdf"},
             {"at": day(3), "category": "concall", "subject": "Earnings call", "text": "Earnings call on results", "url": "b.pdf"}]
    got = deepdive.meetings(items, day(700))
    assert got["calls"] == 2 and got["calls_old"] == 1 and got["calls_due"] == 1


def test_checks_whose_figures_arent_in_the_filed_data_are_a_fact():
    """MS1-007: ROCE, debt to equity, cash conversion and free cash flow need figures some filings don't give; 34 US
    companies were gaps for that."""
    years = [{"year": f"Dec {2021 + i}", "sales": 10.0, "profit": 1.0, "opm": 5.0, "debt": None, "cfo": None, "fcf": None} for i in range(5)]
    checks = [{"label": x, "state": "na"} for x in ("Return on capital employed", "Total debt / equity", "Profit turning into cash", "Free cash flow, 3 years")]
    got = audit.check_view(_view(region="US", checks=checks, numbers={"years": years, "quarters": []}))
    assert [(i["level"], i["area"]) for i in got if i["area"] == "Checklist"] == [("fact", "Checklist")]
    assert "isn't in the company's filed data" in got[0]["detail"]
    for y in years:                                                     # the figures are there: a check that still can't be judged is ours
        y.update(debt=1.0, cfo=2.0, fcf=1.0)
    assert [i["level"] for i in audit.check_view(_view(region="US", checks=checks, numbers={"years": years, "quarters": []})) if i["area"] == "Checklist"] == ["gap"]


def test_a_us_company_with_no_quarterly_reports_says_why():
    """MS1-014: companies that deregistered (Form 15), a new registrant with its first annual report only, and a late filer
    catching up are facts; two annual reports and no quarterly report stay ours to look at."""
    one = _view(region="US", documents=[{"kind": "annual_report", "form": "10-K"}])
    assert audit.check_view(one, deregistered=True)[0] == audit._issue("fact", "Documents", audit.DEREGISTERED_NO_QUARTERLY)
    assert audit.check_view(one)[0] == audit._issue("fact", "Documents", audit.ONE_ANNUAL_ONLY)
    two = _view(region="US", documents=[{"kind": "annual_report", "form": "10-K"}, {"kind": "annual_report", "form": "10-K"}])
    assert audit.check_view(two)[0]["level"] == "gap"


def test_a_page_price_from_a_trade_long_before_our_last_close_is_not_a_mismatch():
    """MS1-015: KBSR's last trade on the company page was 2 May 2025 at 0.90 while the daily candles run to 23 Oct 2026."""
    trend = {"price": 0.01, "t": "2026-10-23T00:00:00-04:00", "chg": -56.0}
    got = audit.check_prices({"price": 0.9}, trend, None, None, (0.9, 0.064, 0.9, 0.9, "2025-05-02T14:33:26+00:00"))
    assert [i["level"] for i in got] == ["fact"] and "2025-05-02" in got[0]["detail"]
    fresh = audit.check_prices({"price": 0.9}, trend, None, None, (0.9, 0.064, 0.9, 0.9, "2026-10-23T14:33:26+00:00"))
    assert [i["level"] for i in fresh] == ["mismatch"]


def test_a_pe_under_one_on_a_us_company_is_a_one_off_gain_and_on_a_suspended_share_an_old_price():
    p = {"region": "US", "pl": {"cols": ["Dec 2025", "TTM"], "rows": {"Net Profit": [90.0, 101.0]}}, "currency": "USD"}
    got = audit.check_numbers(p, {"years": []}, {"pe": 0.5, "market_cap_cr": 50.5})
    assert [(i["level"], i["area"]) for i in got if i["area"] == "Valuation"] == [("fact", "Valuation")]
    india = audit.check_numbers({"region": "IN"}, {"years": []}, {"pe": 0.08})
    assert [i["level"] for i in india if i["area"] == "Valuation"] == ["gap"]            # units can slip in India: ours to look at
    view = {"name": "Coromandel", "numbers": {"years": [], "quarters": []}, "snapshot": {"pe": 0.08, "price": 2.58}, "documents": [],
            "checklist": {"industry": {"path": ["x"]}}, "valuation": {"value": 1}}
    base = lambda s: {"p": {"name": "Coromandel", "region": "IN"}, "trend": None, "trend_why": "untraded", "told": {"filed": 0}}      # noqa: E731
    row = audit.audit_company("507543", base, lambda s, b: view)
    assert [(i["level"], i["area"]) for i in row["issues"] if i["area"] == "Valuation"] == [("fact", "Valuation")]


def test_a_small_trailing_profit_is_known_only_to_its_rounding_in_the_pe_check():
    """MS1-001: a trailing profit of Rs 0.05 cr is anything from 0.045 to 0.055, so the P/E from it is a tenth either way
    (Frontier Capital: 318 on the page, 426.7 here)."""
    p = {"region": "IN", "pl": {"cols": ["Mar 2025", "TTM"], "rows": {"Net Profit": [0.05, 0.05]}}}
    assert not [i for i in audit.check_numbers(p, {"years": [], "notes": []}, {"pe": 318.0, "market_cap_cr": 21.3}) if i["level"] == "mismatch"]
    p["pl"]["rows"]["Net Profit"] = [26.0, 26.0]
    assert [i["level"] for i in audit.check_numbers(p, {"years": [], "notes": []}, {"pe": 10.0, "market_cap_cr": 520.0}) if i["area"] == "Valuation"] == ["mismatch"]


def test_a_valuation_that_cant_be_worked_out_says_the_figure_isnt_in_the_filings():
    """MS1-007: EV/EBITDA for a company whose filings give no operating profit, P/E with no net profit, P/B with a nil net worth."""
    from app import industry
    p = {"region": "US", "pl": {"cols": ["Dec 2025"], "rows": {"Sales": [5.0], "Net Profit": [None]}}, "balance": {"cols": ["Dec 2025"], "rows": {"Equity": [0.0]}}}
    snap = {"market_cap_cr": 100.0}
    ev = industry.valuation(p, snap, "general", "cement")
    assert ev["value"] is None and "give no operating profit to work EBITDA out from" in ev["why"]
    pe = industry.valuation(p, snap, "general", "general")
    assert pe["value"] is None and "give no net profit for the last 12 months" in pe["why"]
    pb = industry.valuation(p, snap, "lender", "lender")
    assert pb["value"] is None and "net worth is nil" in pb["why"]
    assert not audit.check_view({"valuation": ev, "checklist": {"industry": {"path": ["x"]}}, "documents": [{"kind": "presentation"}, {"kind": "transcript"}]})


def test_a_us_company_with_no_industry_code_is_a_fact_and_a_year_with_no_capex_line_in_india_is_nil():
    base = lambda s: {"p": {"name": "CBC", "region": "US", "sic": ""}, "trend": None, "trend_why": None, "told": None}      # noqa: E731
    view = {"name": "CBC", "numbers": {"years": [], "quarters": []}, "snapshot": {}, "documents": [{"kind": "annual_report"}, {"kind": "quarterly_report"}],
            "checklist": {"industry": {"label": "General"}}, "valuation": {"value": 1}, "region": "US"}
    row = audit.audit_company("CBC", base, lambda s, b: view)
    assert [(i["level"], i["detail"]) for i in row["issues"] if i["area"] == "Industry"] == [("fact", audit.NO_SIC)]
    from app import deepdive
    cols = ["Mar 2022", "Mar 2023", "Mar 2024", "Mar 2025", "Mar 2026"]
    t = lambda rows: {"cols": cols, "rows": rows}      # noqa: E731
    p = {"pl": t({"Sales": [100] * 5, "Net Profit": [5] * 5, "Depreciation": [1] * 5}),
         "balance": t({"Fixed Assets": [60, 40, 30, 20, 10], "CWIP": [0] * 5}),
         "cashflow": t({"Cash from Investing Activity": [-5, 2, 3, 1, 1], "Capex": [4.0, None, None, None, None]}), "quarters": {"cols": [], "rows": {}}}
    nums = deepdive.numbers(p)
    assert [y["capex"] for y in nums["years"]] == [4.0, 0.0, 0.0, 0.0, 0.0]        # the breakdown lists fixed assets bought once, then none
    assert [i for i in audit.check_numbers(p, nums, {}) if i["area"] == "Capex"] == []


def test_margins_left_out_of_an_indian_page_are_said_on_it_and_recorded():
    from app.intel import screener
    p = {"pl": {"cols": ["Mar 2024", "Mar 2025", "TTM"], "rows": {"Sales": [100.0, -16.0, 12.0], "OPM %": [20.0, -322.0, 140.0]}},
         "quarters": {"cols": [], "rows": {}}}
    got = screener.drop_impossible_margins(p)
    assert got["pl"]["rows"]["OPM %"] == [20.0, None, None] and got["margin_left_out"] == ["Mar 2025"]
    assert "Mar 2025" in got["margin_note"]
    out = audit.check_numbers({**got, "region": "IN"}, {"years": [], "margin_left_out": got["margin_left_out"]}, {})
    assert any(i["level"] == "fact" and i["detail"].startswith("Operating margin left out for Mar 2025") for i in out)


def test_an_empty_announcements_list_is_asked_again_with_fresh_cookies_before_it_is_called_empty():
    """MS1-002: a bot guard can answer cookies it no longer knows with an empty list; asked once more with new ones, the company's
    filings come back. A company that really filed nothing costs one more request."""
    import httpx
    from app.intel import filings as F
    calls = []
    row = {"symbol": "ABBOTINDIA", "desc": "Updates", "an_dt": "10-Oct-2026 10:00:00", "attchmntText": "Investor presentation",
           "attchmntFile": "https://nsearchives.nseindia.com/x.pdf", "sm_name": "Abbott India Limited"}

    def handler(r):
        calls.append(r.url.path)
        if r.url.path == "/api/corporate-announcements":
            return httpx.Response(200, json={"data": [row] if calls.count("/") >= 2 else []})
        return httpx.Response(200, text="<html></html>")
    feed = F.NSEFilings(transport=httpx.MockTransport(handler), sleep=lambda s: None)
    assert len(feed.announcements("ABBOTINDIA")) == 1 and calls == ["/", "/api/corporate-announcements", "/", "/api/corporate-announcements"]
    calls.clear()
    nothing = F.NSEFilings(transport=httpx.MockTransport(lambda r: (calls.append(r.url.path), httpx.Response(200, json={"data": []}))[1]), sleep=lambda s: None)
    assert nothing.announcements("QUIET") == [] and calls.count("/api/corporate-announcements") == 2


def test_a_share_that_listed_today_with_no_candle_yet_is_a_new_listing_not_an_untraded_share():
    """MS1-006: on its first day the exchange's list says it listed but there is no daily candle to read; that is not a
    company "not on the trading list", and it gets the new listing's checks that day."""
    seen = []
    base = lambda s: {"p": {"name": "N", "region": "IN"}, "trend": None, "trend_why": "untraded", "told": {"filed": 2, "meets": 0, "calls": 0}}   # noqa: E731
    view = {"name": "N", "numbers": {"years": [], "quarters": []}, "snapshot": {}, "documents": [{"kind": "presentation"}],
            "checklist": {"industry": {"path": ["x"]}}, "valuation": {"value": 1}}
    row = audit.audit_company("NEWCO", base, lambda s, b: view, None, None, lambda s: seen.append(s) or _page(), new=True)
    prices = [i["detail"] for i in row["issues"] if i["area"] == "Prices"]
    assert seen == ["NEWCO"] and prices == [audit.NO_PRICES["new"][1]]
    row = audit.audit_company("OLDCO", base, lambda s, b: view, None, None, lambda s: seen.append(s) or _page())
    assert [i["detail"] for i in row["issues"] if i["area"] == "Prices"] == [audit.NO_PRICES["untraded"][1]]
