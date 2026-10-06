"""Fixes from the India whole-market audit sheet of 6 Oct 2026 (5,815 rows over 3,741 companies): an NSE feed that
answers nothing for listed companies (244 "no filings came back"), company pages that came without their results
tables (53 "only 0 years"), our last candle against a company page that quotes another minute of the session (45),
old thinly traded shares called new listings (134), calls from the last week with no transcript due yet, capex read
as missing where the fixed assets only shrank (33), first part-year reports not lining up with the balance sheet,
half-yearly reporters whose four columns are two years, and a P/E under one turn shown to one decimal."""
import httpx

from app import audit, deepdive, main
from app.intel import filings as F
from app.intel.screener import Screener


# ---------- 45 "Last close vs the company page": the page quotes another minute of the same session ----------
def test_a_company_page_price_inside_our_last_sessions_range_agrees():
    """EXXARO on 6 Oct: the last candle ran 5.80 to 6.66 and closed 6.14; the page's 5.80 is the session's own low."""
    trend = {"price": 6.22, "chg": 4.0, "recent": [5.9, 5.95, 6.0, 5.98, 6.22], "day_low": 5.80, "day_high": 6.66}
    assert audit.check_prices({"price": 5.80}, trend, None) == []
    # SIMPLXREA: 142 on the page against NSE candles of 113.75 to 122.95, a different price altogether
    far = {"price": 122.95, "chg": -1.0, "recent": [118.0, 117.4, 120.0, 123.0, 122.95], "day_low": 113.75, "day_high": 122.95}
    found = audit.check_prices({"price": 142.0}, far, None)
    assert found[0]["level"] == "mismatch" and "122.95 vs 142.00 on the company page" in found[0]["detail"]


def test_the_trend_carries_the_last_sessions_range():
    bars = [{"t": f"2026-09-{d:02d}", "o": 10 + d, "h": 12 + d, "l": 8 + d, "c": 10 + d} for d in range(1, 31)]
    got = main.scan.analyse(bars)
    assert got["day_low"] == 38.0 and got["day_high"] == 42.0


# ---------- 244 "No filings came back from the exchange": NSE answers nothing for ABBOTINDIA, GOODYEAR, BAYERCROP... ----------
class _Feed:
    def __init__(self, items):
        self.items, self.asked = items, []

    def announcements(self, key, days):
        self.asked.append(key)
        return self.items


def test_filings_the_exchange_feed_lacks_are_read_under_the_bse_listing():
    item = {"at": "2026-09-01T10:00", "category": "results", "subject": "Results", "text": "", "url": None}
    nse, bse = _Feed([]), _Feed([item])
    feed = F.IndiaFilings(nse, bse, lambda s: None, lambda s: "500488" if s == "ABBOTINDIA" else None)
    assert feed.announcements("ABBOTINDIA", 732) == [item] and bse.asked == ["500488"]
    assert feed.announcements("NOBSE", 732) == []                       # no BSE listing: still nothing
    full = F.IndiaFilings(_Feed([item]), bse, lambda s: None, lambda s: "1")
    bse.asked.clear()
    assert full.announcements("ITC", 732) == [item] and bse.asked == []   # NSE answered: BSE isn't asked
    assert F.IndiaFilings(nse, bse, lambda s: None).announcements("X", 1) == []   # no twin lookup: as before


def test_a_bse_feed_refusal_leaves_the_nse_answer():
    class Down:
        def announcements(self, key, days):
            raise F.SourceError("BSE", "refused", busy=True)
    assert F.IndiaFilings(_Feed([]), Down(), lambda s: None, lambda s: "500488").announcements("ABBOTINDIA", 732) == []


# ---------- calls from the last week ----------
def _call(at):
    return {"at": at, "category": "concall", "subject": "Analysts/Institutional Investor Meet/Con. Call Updates",
            "text": "XYZ Ltd has informed the Exchange about Intimation of earnings call", "url": "https://nsearchives.nseindia.com/a.pdf"}


def test_a_call_from_the_last_week_has_no_transcript_due_yet():
    now = F.ist_now()
    stamp = lambda days: (now - F.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M")      # noqa: E731
    told = deepdive.meetings([_call(stamp(2))], stamp(700))
    assert told["calls"] == 1 and told["calls_due"] == 0
    assert audit._india_documents(["presentation"], told, None) == []                    # nothing to look into yet
    old = deepdive.meetings([_call(stamp(2)), _call(stamp(60))], stamp(700))
    assert old["calls"] == 2 and old["calls_due"] == 1
    got = audit._india_documents(["presentation"], old, None)
    assert got[0]["level"] == "gap" and "though 2 of its filings" in got[0]["detail"]
    legacy = {"meets": 1, "calls": 1, "filed": 5}                                        # a stored read without the new count
    assert audit._india_documents(["presentation"], legacy, None)[0]["level"] == "gap"


# ---------- 53 "Only 0 years of annual results": the page came without its results tables ----------
PARTIAL = ("<html><h1>Acme Ltd</h1><ul id='top-ratios'><li><span class='name'>Stock P/E</span>"
           "<span class='value'>12</span></li></ul></html>")
FULL = PARTIAL.replace("</html>", "<section id='profit-loss'><table class='data-table'><thead><tr><th></th><th>Mar 2025</th>"
                                  "<th>Mar 2026</th></tr></thead><tbody><tr><td>Sales</td><td>100</td><td>120</td></tr>"
                                  "</tbody></table></section></html>")


def _screener(pages):
    asked = []

    def handler(request):
        asked.append(request.url.path)
        return httpx.Response(200, text=pages[min(len(asked), len(pages)) - 1])
    return Screener(transport=httpx.MockTransport(handler)), asked


def test_a_page_without_its_results_tables_is_asked_again():
    scr, asked = _screener([PARTIAL, PARTIAL, FULL, FULL])
    p = scr.company("ACME")
    assert p["pl"]["cols"] == ["Mar 2025", "Mar 2026"] and len(asked) == 4
    assert len(deepdive.numbers(p)["years"]) == 2


def test_a_company_with_no_results_yet_is_asked_once_more_only():
    scr, asked = _screener([PARTIAL])
    p = scr.company("ACME")
    assert "pl" not in p and len(asked) == 4
    scr.company("ACME")                                                   # the second answer is kept
    assert len(asked) == 4


# ---------- 134 "Listed recently": old shares that trade on a few days a year ----------
def _status(monkeypatch, first, count):
    last = main.datetime.now(main.IST).date().isoformat()
    bars = [{"t": f"{first if i == 0 else last}T00:00:00+05:30", "o": 1, "h": 1, "l": 1, "c": 1} for i in range(count)]
    monkeypatch.setattr(main.universes, "resolve", lambda *a, **k: (["x"], None))
    monkeypatch.setattr(main.scan, "_bars", lambda *a, **k: bars)
    monkeypatch.setattr(main.scan, "analyse", lambda b: None)
    return main.price_status("ACME")


def test_a_thinly_traded_old_share_is_not_a_new_listing(monkeypatch):
    today = main.datetime.now(main.IST).date()
    recent = (today - main.timedelta(days=20)).isoformat()
    year_ago = (today - main.timedelta(days=380)).isoformat()
    assert _status(monkeypatch, recent, 12) == (None, "new")
    assert _status(monkeypatch, year_ago, 12) == (None, "sparse")
    why = audit.NO_PRICES["sparse"]
    assert why[0] == "fact" and "Listed recently" not in why[1]
    assert audit.check_prices({}, None, None, "sparse")[0]["level"] == "fact"


# ---------- 33 "No capex estimate for the last three years" ----------
def _company(fa, cwip=None, dep=None, years=("Mar 2023", "Mar 2024", "Mar 2025", "Mar 2026")):
    t = lambda rows, cols=years: {"cols": list(cols), "rows": rows}                       # noqa: E731
    return {"name": "Acme", "pl": t({"Sales": [100] * 4, "Net Profit": [5] * 4, "Depreciation": dep or [1] * 4}),
            "balance": t({"Fixed Assets": fa, "CWIP": cwip or [0] * 4}), "cashflow": t({}), "quarters": {"cols": [], "rows": {}}}


def test_fixed_assets_that_only_shrank_are_a_fact_not_a_missing_number():
    p = _company([60, 40, 30, 20])
    nums = deepdive.numbers(p)
    assert [y["capex"] for y in nums["years"][-3:]] == [None] * 3 and all(y["capex_cut"] for y in nums["years"][-3:])
    got = [i for i in audit.check_numbers(p, nums, {}) if i["area"] == "Capex"]
    assert got == [audit._issue("fact", "Capex", audit.CAPEX_SHRUNK)]
    # fixed assets grew in one year: capex is read there, so the rest isn't a "shrank every year" claim
    p = _company([60, 40, 55, 20])
    nums = deepdive.numbers(p)
    assert nums["years"][2]["capex"] == 16 and not [i for i in audit.check_numbers(p, nums, {}) if i["area"] == "Capex"]
    # no balance sheet at all: a missing number, ours to look into
    p = _company([None] * 4)
    got = [i for i in audit.check_numbers(p, deepdive.numbers(p), {}) if i["area"] == "Capex"]
    assert got == [audit._issue("gap", "Capex", "No capex estimate for the last three years")]


def test_a_part_year_report_lines_up_with_its_balance_sheet():
    """ENRIN: results say "Sep 2024 8m" and "Feb 2025 5m", the balance sheet "Sep 2024" and "Feb 2025"."""
    p = _company([0, 435, 536, 610], years=("Sep 2024", "Feb 2025", "Sep 2025", "Mar 2026"))
    p["pl"]["cols"] = ["Sep 2024 8m", "Feb 2025 5m", "Sep 2025", "Mar 2026"]
    capex = [y["capex"] for y in deepdive.numbers(p)["years"]]
    assert capex[1:] == [436.0, 102.0, 75.0] and capex[0] is None


# ---------- 1 "Trailing revenue 598 cr vs last four quarters 1,134 cr": a half-yearly reporter ----------
def test_half_yearly_columns_are_not_four_quarters():
    years = [{"year": f"Mar {2022 + i}", "sales": 100, "profit": 5, "opm": 10, "capex": 3} for i in range(5)]
    nums = {"years": years, "quarters": [{"quarter": q, "sales": s} for q, s in
                                       (("Sep 2024", 165), ("Mar 2025", 282), ("Sep 2025", 254), ("Mar 2026", 299))]}
    p = {"name": "Acme", "pl": {"cols": ["Mar 2026", "TTM"], "rows": {"Sales": [553, 598]}}}
    assert not [i for i in audit.check_numbers(p, nums, {}) if i["area"] == "Numbers"]
    nums["quarters"] = [{"quarter": q, "sales": s} for q, s in
                        (("Jun 2025", 100), ("Sep 2025", 110), ("Dec 2025", 120), ("Mar 2026", 130))]
    found = [i for i in audit.check_numbers(p, nums, {}) if i["area"] == "Numbers"]
    assert found == [audit._issue("mismatch", "Numbers", "Trailing revenue 598 cr vs last four quarters 460 cr")]
    assert audit._quarterly(["Dec 2025", "Mar 2026"]) and not audit._quarterly(["Mar 2025", "Sep 2025"])
    assert audit._quarterly(["Q1", "Q2"])                      # not dated: nothing to tell them apart by


# ---------- "P/E 0.1 on the company page, 0.1 from market cap ÷ trailing profit" ----------
def test_a_pe_under_a_turn_apart_is_rounding():
    p = {"name": "Acme", "pl": {"cols": ["Mar 2026", "TTM"], "rows": {"Sales": [100, 100], "Net Profit": [20, 20]}}}
    nums = {"years": [], "quarters": []}
    assert not [i for i in audit.check_numbers(p, nums, {"pe": 0.1, "market_cap_cr": 4.0}) if i["area"] == "Valuation"]   # ours 0.2
    got = audit.check_numbers(p, nums, {"pe": 10.0, "market_cap_cr": 400.0})        # ours 20: a real difference
    assert [i["level"] for i in got if i["area"] == "Valuation"] == ["mismatch"]
