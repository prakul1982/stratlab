"""Round 10 visitor review of the live site (9 Oct 2026), the server's side: Deutsche Bank's blank latest profits under a
margin from another year (its statement is tagged for the consolidated entity, which the SEC's company facts leave out),
every ratio from one year's own column, 20-F tables a year behind and key figures past 15 months, three India 52-week
ranges (a window of 252 candles, a stray low, a clipped high), ICICI Bank's missing price and Baidu's and BP's missing
market value, the shorter descriptions and canonical-free noindex pages, and a large company's peers.

The data is shaped like the real cases (Deutsche Bank's 2025 20-F, Baidu's and BP's cover pages, ICICI Bank's 20-F filed
without XBRL) but small and made here: nothing is read from the network."""
import json
import re
from datetime import date, datetime, timedelta, timezone

import httpx
import pytest

from app import main  # noqa: F401, I001  (first: the app loads the newsletter job before the modules built on it)
from app import deepdive, screens, stock_pages
from app.intel import screener, sec

TODAY = date(2026, 10, 9)


# ---------- a small SEC: company facts, a filing list and an XBRL instance ----------
def fact(concept_end, val, start=None, accn="0000000000-25-000001", form="20-F", filed="2025-03-13"):
    row = {"end": concept_end, "val": val, "accn": accn, "fy": int(concept_end[:4]), "fp": "FY", "form": form, "filed": filed}
    if start:
        row["start"] = start
    return row


def year(y: int) -> tuple[str, str]:
    return f"{y}-01-01", f"{y}-12-31"


def companyfacts(cik: int, ifrs: dict, cur: str = "EUR") -> dict:
    """{concept: [(year, value, accn, filed)]} as the SEC's company facts hold them (annual flows only)."""
    out = {}
    for concept, rows in ifrs.items():
        out[concept] = {"units": {cur: [fact(year(y)[1], v, year(y)[0], accn=a, filed=f) for y, v, a, f in rows]}}
    return {"cik": cik, "entityName": "Dbank AG", "facts": {"ifrs-full": out}}


def submissions(cik: int, filings: list[tuple[str, str, str, str]]) -> dict:
    """filings: (form, accession, filed, primary document)."""
    return {"cik": cik, "name": "Dbank AG", "sic": "6029", "sicDescription": "Commercial Banks, NEC", "tickers": ["DBK"],
            "filings": {"recent": {"form": [f[0] for f in filings], "accessionNumber": [f[1] for f in filings], "filingDate": [f[2] for f in filings],
                                   "primaryDocument": [f[3] for f in filings], "items": [""] * len(filings)}, "files": []}}


NS = ('xmlns:xbrli="http://www.xbrl.org/2003/instance" xmlns:xbrldi="http://xbrl.org/2006/xbrldi" '
      'xmlns:ifrs-full="http://xbrl.ifrs.org/taxonomy/2025-03-27/ifrs-full" xmlns:dei="http://xbrl.sec.gov/dei/2025" '
      'xmlns:iso4217="http://www.xbrl.org/2003/iso4217" xmlns:db="http://www.db.com/20251231"')


def ctx(cid: str, start: str | None, end: str, dim: tuple[str, str] | None = None) -> str:
    seg = f'<xbrli:segment><xbrldi:explicitMember dimension="{dim[0]}">{dim[1]}</xbrldi:explicitMember></xbrli:segment>' if dim else ""
    per = (f"<xbrli:startDate>{start}</xbrli:startDate><xbrli:endDate>{end}</xbrli:endDate>" if start else f"<xbrli:instant>{end}</xbrli:instant>")
    return (f'<xbrli:context id="{cid}"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">0001</xbrli:identifier>{seg}'
            f"</xbrli:entity><xbrli:period>{per}</xbrli:period></xbrli:context>")


def instance(body: str, contexts: list[str], cur: str = "EUR") -> str:
    units = (f'<xbrli:unit id="{cur}"><xbrli:measure>iso4217:{cur}</xbrli:measure></xbrli:unit>'
             f'<xbrli:unit id="sh"><xbrli:measure>xbrli:shares</xbrli:measure></xbrli:unit>')
    return f'<?xml version="1.0" encoding="utf-8"?><xbrli:xbrl {NS}>{"".join(contexts)}{units}{body}</xbrli:xbrl>'


CONSOLIDATED = ("ifrs-full:LegalEntityAxis", "db:ConsolidatedBankEntityMember")
PARENT = ("ifrs-full:LegalEntityAxis", "db:DeutscheBankAGMember")
SEGMENT = ("ifrs-full:SegmentsAxis", "db:PrivateBankMember")


def db_instance() -> str:
    """Deutsche Bank's 2025 20-F as its XBRL gives it: revenue and profit before tax plain (a note), the income statement's
    profit, owners' profit and earnings per share for the consolidated entity only, a different profit for the parent
    bank alone, and a segment's profit that is neither."""
    contexts = []
    for y in (2023, 2024, 2025):
        s, e = year(y)
        contexts += [ctx(f"p{y}", s, e), ctx(f"c{y}", s, e, CONSOLIDATED), ctx(f"a{y}", s, e, PARENT), ctx(f"s{y}", s, e, SEGMENT)]
    contexts += [ctx("b25", None, "2025-12-31"), ctx("bc25", None, "2025-12-31", CONSOLIDATED), ctx("bc24", None, "2024-12-31", CONSOLIDATED)]
    body = ""
    own = {2023: 6332, 2024: 2680, 2025: 6606}
    rev = {2023: 31155, 2024: 31504, 2025: 31434}
    for y in (2023, 2024, 2025):
        M = 1_000_000
        body += (f'<ifrs-full:Revenue contextRef="p{y}" unitRef="EUR">{rev[y] * M}</ifrs-full:Revenue>'
                 f'<ifrs-full:ProfitLossBeforeTax contextRef="p{y}" unitRef="EUR">{(own[y] + 2300) * M}</ifrs-full:ProfitLossBeforeTax>'
                 f'<ifrs-full:ProfitLossAttributableToOwnersOfParent contextRef="c{y}" unitRef="EUR">{own[y] * M}</ifrs-full:ProfitLossAttributableToOwnersOfParent>'
                 f'<ifrs-full:ProfitLoss contextRef="c{y}" unitRef="EUR">{(own[y] + 208) * M}</ifrs-full:ProfitLoss>'
                 f'<ifrs-full:ProfitLossAttributableToOwnersOfParent contextRef="a{y}" unitRef="EUR">{1111 * M}</ifrs-full:ProfitLossAttributableToOwnersOfParent>'
                 f'<ifrs-full:ProfitLossAttributableToOwnersOfParent contextRef="s{y}" unitRef="EUR">{222 * M}</ifrs-full:ProfitLossAttributableToOwnersOfParent>'
                 f'<ifrs-full:BasicEarningsLossPerShare contextRef="c{y}" unitRef="EURsh">{round(own[y] / 1950, 2)}</ifrs-full:BasicEarningsLossPerShare>')
    body += '<ifrs-full:Equity contextRef="bc25" unitRef="EUR">86000000000</ifrs-full:Equity>'
    body += '<ifrs-full:Equity contextRef="bc24" unitRef="EUR">82000000000</ifrs-full:Equity>'
    inst = instance(body, contexts)
    return inst.replace('<xbrli:unit id="sh">', '<xbrli:unit id="EURsh"><xbrli:divide><xbrli:unitNumerator><xbrli:measure>iso4217:EUR</xbrli:measure>'
                        '</xbrli:unitNumerator><xbrli:unitDenominator><xbrli:measure>xbrli:shares</xbrli:measure></xbrli:unitDenominator></xbrli:divide>'
                        '</xbrli:unit><xbrli:unit id="sh">')


OLD, NEW = ("0000000000-25-000020", "2025-03-13"), ("0000000000-26-000017", "2026-03-12")


def db_facts() -> dict:
    """The SEC's company facts for a Deutsche-Bank-shaped filer: 2021 to 2023 profit from the older reports, revenue for
    every year (a note gives it plain), and no profit at all for 2024 and 2025, as the live facts are."""
    rev = [(2021, 27_000, *OLD), (2022, 27_063, *OLD), (2023, 31_155, *OLD), (2024, 31_504, *OLD), (2025, 31_434, *NEW)]
    own = [(2021, 2_451, *OLD), (2022, 5_420, *OLD), (2023, 6_332, *OLD)]
    return companyfacts(1159508, {"Revenue": [(y, v * 1_000_000, a, f) for y, v, a, f in rev],
                                  "ProfitLossAttributableToOwnersOfParent": [(y, v * 1_000_000, a, f) for y, v, a, f in own],
                                  "ProfitLoss": [(y, (v + 208) * 1_000_000, a, f) for y, v, a, f in own]})


DB_FILINGS = [("20-F", NEW[0], NEW[1], "db-20251231.htm"), ("20-F", OLD[0], OLD[1], "db-20241231.htm")]


def transport(cik: int, facts: dict | None, subs: dict, instances: dict[str, str | None], calls: list | None = None):
    """The SEC's hosts as a mock. `instances`: accession -> the XBRL instance text, or None for a filing with no data file."""
    def handler(r: httpx.Request):
        p = r.url.path
        if calls is not None:
            calls.append(p)
        if p == "/files/company_tickers.json":
            return httpx.Response(200, json={"0": {"cik_str": cik, "ticker": "DBK", "title": "Dbank AG"}})
        if p == f"/submissions/CIK{cik:010d}.json":
            return httpx.Response(200, json=subs)
        if p == f"/api/xbrl/companyfacts/CIK{cik:010d}.json":
            return httpx.Response(200, json=facts) if facts is not None else httpx.Response(404)
        m = re.match(rf"/Archives/edgar/data/{cik}/(\d{{10}})(\d{{2}})(\d{{6}})/(.+)$", p)
        if m:
            accn = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
            name = m.group(4)
            if name.endswith("_htm.xml"):
                text = instances.get(accn)
                return httpx.Response(200, text=text) if text else httpx.Response(404)
            return httpx.Response(200, text="<html><body><p>Annual report cover page.</p></body></html>")
        return httpx.Response(404)
    return httpx.MockTransport(handler)


def db_company(instances=None, **kw) -> dict:
    inst = {NEW[0]: db_instance()} if instances is None else instances
    return sec.SEC(transport=transport(1159508, db_facts(), submissions(1159508, DB_FILINGS), inst, **kw)).company("DBK")


# ---------- R10V-001: the consolidated entity's figures, and every ratio from one year ----------
def test_a_figure_tagged_for_the_consolidated_entity_stands_when_the_plain_one_is_missing():
    inst = sec.instance(db_instance())
    got = sec.instance_facts(inst, "20-F", "2026-03-12", "0000000000-26-000017")["ifrs-full"]
    owners = {(r["start"], r["end"]): r["val"] for r in got["ProfitLossAttributableToOwnersOfParent"]["units"]["EUR"]}
    assert owners[("2025-01-01", "2025-12-31")] == 6_606_000_000 and owners[("2024-01-01", "2024-12-31")] == 2_680_000_000
    assert len(owners) == 3                                    # the parent bank's 1,111 and the segment's 222 are not the group's
    assert 1_111_000_000 not in owners.values() and 222_000_000 not in owners.values()
    # a plain fact wins over the consolidated entity's where both are given (profit before tax is given both ways)
    pre = {r["end"]: r["val"] for r in got["ProfitLossBeforeTax"]["units"]["EUR"]}
    assert pre["2025-12-31"] == (6606 + 2300) * 1_000_000 and len(got["ProfitLossBeforeTax"]["units"]["EUR"]) == 3
    assert sec.consolidated_only({"LegalEntityAxis": "ConsolidatedMember"})
    assert sec.consolidated_only({"ConsolidatedAndSeparateFinancialStatementsAxis": "ConsolidatedMember"})
    assert not sec.consolidated_only({"LegalEntityAxis": "DeutscheBankAGMember"})
    assert not sec.consolidated_only({"LegalEntityAxis": "SeparateMember"})
    assert not sec.consolidated_only({"SegmentsAxis": "ConsolidatedMember"})
    assert not sec.consolidated_only({"LegalEntityAxis": "ConsolidatedMember", "SegmentsAxis": "PrivateBankMember"})


def test_a_filing_whose_revenue_is_in_the_facts_but_not_its_profit_is_read_from_the_filing():
    facts = db_facts()
    assert not sec.has_filing(facts, NEW[0])                  # revenue of the 2026 report is there; its profit is not
    assert sec.has_filing(facts, OLD[0])                      # the 2025 report's older profit rows are
    both = companyfacts(1, {"Revenue": [(2025, 1, *NEW)], "ProfitLoss": [(2025, 1, *NEW)]})
    assert sec.has_filing(both, NEW[0])
    # a quarter's profit in the same filing is not the year's
    q = {"facts": {"ifrs-full": {"ProfitLoss": {"units": {"EUR": [{**fact("2025-03-31", 1, "2025-01-01", accn=NEW[0])}]}}}}}
    assert not sec.has_filing(q, NEW[0])


def test_deutsche_banks_two_newest_years_have_their_profit_and_nothing_is_taken_from_another_year():
    p = db_company()
    assert p["pl"]["cols"][-3:] == ["Dec 2023", "Dec 2024", "Dec 2025"]
    assert p["pl"]["rows"]["Net Profit"][-3:] == [6332.0, 2680.0, 6606.0]
    assert p["pl"]["rows"]["Sales"][-1] == 31434.0 and p["currency"] == "EUR"
    assert p["balance"]["rows"]["Equity"][-1] == 86000.0
    r = sec.ratios({**p, "fx": {"rate": 1.1}}, 20.0)
    assert r["ROE"] == round(6606 / 86000 * 100, 1)           # 2025's profit over 2025's equity
    # and the SEC's facts alone, as they stand live: the profit of 2024 and 2025 is blank, not 2023's
    bare = sec.build(db_facts(), submissions(1159508, DB_FILINGS), symbol="DBK")
    assert bare["pl"]["rows"]["Net Profit"][-3:] == [6332.0, None, None] and bare["pl"]["rows"]["Sales"][-1] == 31434.0


def test_no_ratio_takes_a_blank_years_input_from_an_earlier_year():
    bare = sec.build(db_facts(), submissions(1159508, DB_FILINGS), symbol="DBK")
    bare["balance"]["rows"]["Equity"] = [50_000.0] * len(bare["balance"]["cols"])
    r = sec.ratios({**bare, "fx": {"rate": 1.1}}, 20.0)
    assert "ROE" not in r                                     # 6,332 of 2023 over 2025's equity was 7.7% on the live page
    # the index of the same page: net margin is the latest year's own, blank when its profit is
    snap = screener.summary(bare)
    assert snap["net_margin"] is None and snap["profit_yoy"] is None and snap["sales_yoy"] is not None
    # a full row gives the margin of the latest column
    bare["pl"]["rows"]["Net Profit"][-1] = 3_143.0
    assert screener.summary(bare)["net_margin"] == pytest.approx(3_143.0 / 31_434.0 * 100)


def test_a_growth_rate_counts_the_years_as_columns_and_a_blank_year_is_a_gap():
    # Deutsche Bank's live text: "net profit grew 135.8% a year", from 2,451 to 6,332 over three filtered "years"
    profit = [2_451.0, 5_420.0, 6_332.0, None, None]
    assert deepdive._cagr(profit, 3) is None and deepdive._cagr(profit, 1) is None
    assert deepdive._cagr([100.0, None, 110.0, 120.0, 133.1], 3) is None          # the year three columns back is blank
    assert deepdive._cagr([100.0, 110.0, 121.0, 133.1], 3) == pytest.approx(10.0, abs=0.01)
    assert deepdive._cagr([100.0, 110.0], 3) is None and deepdive._cagr([-5.0, 1.0, 2.0, 3.0], 3) is None
    # the page says nothing about growth it hasn't the years for
    nums = deepdive.numbers({"pl": {"cols": ["Dec 2021", "Dec 2022", "Dec 2023", "Dec 2024", "Dec 2025"],
                                    "rows": {"Sales": [27.0, 27.0, 31.0, 31.0, 31.0], "Net Profit": profit}}, "unit": "€ million"})
    assert nums["growth"]["profit_cagr_3y"] is None and nums["growth"]["sales_cagr_3y"] is not None
    assert stock_pages.growth_words("net profit", nums["growth"]["profit_cagr_3y"]) is None


def test_deutsche_banks_page_has_no_margin_where_it_has_no_profit_and_none_of_another_years():
    p = sec.with_fx(dict(sec.build(db_facts(), submissions(1159508, DB_FILINGS), symbol="DBK")), lambda c: 1.1)
    snap = screener.summary(p)
    f = stock_pages.facts("US", "DB", p, deepdive.numbers(p), snap, None, {"price": 20.0, "price_at": "2026-10-08", "price_basis": "close"},
                          [], "Listed in the US")
    assert f["net_margin"] is None and f["growth"]["profit_cagr_3y"] is None
    page = stock_pages.render({**f, "unit": "EUR million"}, "US", "DB", None)
    assert "20.1%" not in page and "135.8" not in page and "net profit grew" not in page
    assert "<span>Net margin</span>" not in page            # blank, not another year's number


# ---------- R10V-002: the newest 20-F, and key figures past 15 months ----------
def facts_page(last_year="Mar 2025", at="2026-09-30", **kw):
    years = [{"year": f"Mar {y}", "sales": 100.0 + y, "profit": 10.0, "opm": 20.0, "debt": 5.0} for y in range(2021, int(last_year[-4:]) + 1)]
    base = {"region": "US", "symbol": "RDY", "name": "Dr. Reddy's", "exchange": "Listed in the US", "industry": ["Manufacturing", "Drugs"],
            "currency": "USD", "unit": "INR million", "market_cap_unit": "$ million", "price": 14.0, "price_at": at, "price_basis": "close",
            "high52": 16.0, "low52": 12.0, "market_cap": 11_500.0, "pe": 18.0, "roe": 17.0, "opm": 27.3, "net_margin": 17.4, "debt_equity": 0.03,
            "years": years, "growth": {}, "filings": [], "built_at": "2026-10-08T22:00:00+00:00", "v": stock_pages.FACTS_VERSION,
            "sales_usd": 3_800.0, "foreign": True, "profit_usd": 650.0, "pe_basis": "year", "pe_end": "2025-03-31"}
    return {**base, **kw}


def stat(page: str, label: str) -> str | None:
    m = re.search(rf"<span>{re.escape(label)}</span><b>([^<]*)</b>", page)
    return m.group(1) if m else None


def test_the_key_figures_of_a_year_over_15_months_old_are_na_and_say_why():
    old = facts_page("Mar 2025")                              # Dr. Reddy's: a table to Mar 2025 beside a Sep 2026 price
    assert stock_pages.figures_stale(old) and stock_pages.figures_end(old) == "2025-03-31"
    page = stock_pages.render(old, "US", "RDY", None)
    for label in ("Return on equity", "EBITDA margin", "Debt to equity", "Net margin"):
        assert stat(page, label) == "n/a", label
    assert "17.0%" not in page and "27.3%" not in page and "17.4%" not in page
    assert "data-figures-old" in page and "31 Mar 2025" in page and "15 months" in page
    # the same page with its newest year in the table: the figures stand, no note
    new = stock_pages.render(facts_page("Mar 2026"), "US", "RDY", None)
    assert stat(new, "Return on equity") == "17.0%" and stat(new, "Net margin") == "17.4%" and "data-figures-old" not in new
    # a year that ended 14 months before the price is not yet too old; 16 months is
    assert not stock_pages.figures_stale(facts_page("Mar 2025", at="2026-05-30"))
    assert stock_pages.figures_stale(facts_page("Mar 2025", at="2026-08-01"))
    assert not stock_pages.figures_stale({"years": [], "price_at": "2026-10-01"})
    assert not stock_pages.figures_stale(facts_page("Mar 2026", at="2026-10-01", years=[{"year": "Mar 2026 3m"}]))


def test_a_page_whose_table_is_behind_its_newest_annual_report_is_built_again_within_the_hour():
    behind = facts_page("Mar 2025", annual_filed="2026-05-29")          # the 20-F of 29 May 2026 is not in the table
    assert stock_pages.annual_behind(behind)
    assert not stock_pages.annual_behind(facts_page("Mar 2026", annual_filed="2026-05-29"))
    assert not stock_pages.annual_behind(facts_page("Mar 2025", annual_filed="2025-06-06"))       # last year's report, filed in time
    assert not stock_pages.annual_behind(facts_page("Mar 2025"))        # an older page that doesn't say
    now = 1_791_500_000.0
    close = stock_pages.last_close("US", datetime.fromtimestamp(now, timezone.utc))[1].timestamp() + stock_pages.settle("US")
    assert stock_pages.fresh({"ts": close + 60, "price_ts": close + 60, "facts": behind}, "US", now=close + 120)       # just built
    assert not stock_pages.fresh({"ts": close + 60, "price_ts": close + 60, "facts": behind}, "US", now=close + 60 + stock_pages.UNREAD_FRESH + 5)
    ok = facts_page("Mar 2026", annual_filed="2026-05-29")
    assert stock_pages.fresh({"ts": close + 60, "price_ts": close + 60, "facts": ok}, "US", now=close + 60 + stock_pages.UNREAD_FRESH + 5)


def test_the_screens_rebuild_a_behind_page_first(monkeypatch, tmp_path):
    from app import db
    store = {"stocks:page:US:RDY": json.dumps({"ts": 1.0, "facts": facts_page("Mar 2025", annual_filed="2026-05-29")}),
             "stocks:page:US:OK": json.dumps({"ts": 1.0, "facts": facts_page("Mar 2026", annual_filed="2026-05-29")})}
    monkeypatch.setattr(db, "all_settings_with_prefix", lambda p, *a: [(k, v) for k, v in store.items() if k.startswith(p)])
    monkeypatch.setattr(db, "set_setting", lambda k, v: None)
    monkeypatch.setattr(stock_pages, "nse_twins", lambda: {})
    index = screens.build_index("US", store=False)
    assert "RDY" in index["_old"] and "OK" not in index["_old"]


def test_a_new_filings_missing_data_file_is_asked_for_again_within_the_hour_an_old_ones_is_not():
    s = sec.SEC(transport=transport(1159508, db_facts(), submissions(1159508, DB_FILINGS), {}))
    today = date.today().isoformat()
    assert s.filing_data(1159508, {"form": "20-F", "accn": "0000000000-26-000099", "filed": today, "doc": "x.htm"}) == {}
    assert s.filing_data(1159508, {"form": "20-F", "accn": "0000000000-24-000099", "filed": "2024-03-01", "doc": "x.htm"}) == {}
    import time
    fresh = s.cache._d[("instance", "0000000000-26-000099")][0] - time.time()
    stale = s.cache._d[("instance", "0000000000-24-000099")][0] - time.time()
    assert 3000 < fresh <= 3600 and stale > 20 * 86400


def test_the_filing_read_waits_for_the_sources_rate_limit_longer_than_a_listing_does(monkeypatch):
    s = sec.SEC(transport=transport(1159508, db_facts(), submissions(1159508, DB_FILINGS), {}))
    waits = []
    monkeypatch.setattr(s.limit, "take", lambda max_wait=8.0: waits.append(max_wait) or False)
    assert s.filing_data(1159508, {"form": "20-F", "accn": "0000000000-26-000098", "filed": "2026-03-12", "doc": "x.htm"}) is None
    assert waits == [30.0]


def test_a_built_company_says_when_its_newest_annual_report_was_filed():
    p = db_company()
    assert p["annual_filed"] == "2026-03-12"
    checks = {k: v for k, v in main.us_cap_checks(p, "DBK").items()}
    assert "annual_filed" not in checks                       # kept by the page build (stock_page_facts), not the value checks


# ---------- R10V-003: a year's range over exactly 365 days, held to the exchange's own 52-week report ----------
def bars_from(start: date, n: int, price=100.0, high=1.0, low=1.0, skip=lambda d: d.weekday() >= 5):
    out, d = [], start
    while len(out) < n:
        if not skip(d):
            out.append({"t": f"{d.isoformat()}T00:00:00+05:30", "o": price, "h": price + high, "l": price - low, "c": price, "v": 1})
        d += timedelta(days=1)
    return out


def test_the_range_runs_over_the_last_365_days_not_the_last_252_candles():
    # TITAN, 9 Oct 2026: 252 candles reach back to 3 Oct 2025 (371 days) and showed that day's low of 3,378
    bars = bars_from(date(2025, 10, 1), 262, skip=holidays)
    last = bars[-1]["t"][:10]
    first_of_252 = bars[-252:][0]["t"][:10]
    assert (date.fromisoformat(last) - date.fromisoformat(first_of_252)).days > 365
    for b in bars:
        if b["t"][:10] <= "2025-10-08":
            b["l"] = 90.0                                       # a low from before the window
    bars[-5]["l"] = 95.0
    got = stock_pages.price_facts(bars)
    assert got["low52"] == 95.0
    within = stock_pages.year_bars(bars)
    assert within[0]["t"][:10] > (date.fromisoformat(within[-1]["t"][:10]) - timedelta(days=365)).isoformat()
    assert all(b["t"][:10] > "2025-10-08" for b in within) or within[0]["t"][:10] > "2025-10-08"
    # candles that cover less than a year are all used
    short = bars_from(date(2026, 8, 3), 30)
    assert len(stock_pages.year_bars(short)) == 30
    assert stock_pages.year_bars([]) == []


def holidays(d: date) -> bool:
    """Weekends and about twelve weekdays a year, which is how many sessions an Indian year has (about 248)."""
    return d.weekday() >= 5 or d.toordinal() % 20 == 0


def row_for(hi=1728.0, hi_day="2026-02-03", lo=980.4, lo_day="2026-09-29"):
    return [hi, hi_day, lo, lo_day]


def test_a_stray_low_the_exchange_does_not_have_is_brought_back_to_its_figure():
    # ULTRACEMCO: the page's low was 10,118.00; no exchange or price-history bar printed it, the exchange's low is 10,325.00
    bars = bars_from(date(2025, 10, 10), 250, price=11_000.0, high=100.0, low=100.0)
    by_day = {b["t"][:10]: b for b in bars}
    by_day["2026-03-23"]["l"] = 10_325.0
    stray = next(b for b in bars if b["t"][:10] == "2026-05-12")
    stray["l"] = 10_118.0
    report_day = bars[-1]["t"][:10]
    assert stock_pages.price_facts(bars)["low52"] == 10_118.0
    fitted = stock_pages.fit_to_exchange_range(bars, [13_110.0, "2026-02-10", 10_325.0, "2026-03-23"], report_day)
    assert stock_pages.price_facts(fitted)["low52"] == 10_325.0
    assert stray["l"] == 10_118.0 and fitted is not bars        # the candles given are not changed


def test_a_high_the_candle_clipped_is_brought_out_to_the_exchanges():
    # INFY, 3 Feb 2026: the candle's high 1,691.40, the exchange's 1,728.00
    bars = bars_from(date(2025, 10, 10), 250, price=1_500.0, high=20.0, low=20.0)
    clipped = next(b for b in bars if b["t"][:10] == "2026-02-03")
    clipped["h"] = 1_691.4
    report_day = bars[-1]["t"][:10]
    assert stock_pages.price_facts(bars)["high52"] == 1_691.4
    fitted = stock_pages.fit_to_exchange_range(bars, row_for(lo=1_480.0, lo_day="2026-09-29"), report_day)
    assert stock_pages.price_facts(fitted)["high52"] == 1_728.0
    # a figure far from the candles' (another basis, an unadjusted one) is left alone
    assert stock_pages.price_facts(stock_pages.fit_to_exchange_range(bars, [5_000.0, "2026-02-03", 1_480.0, "2026-09-29"], report_day))["high52"] == 1_691.4


def test_candles_after_the_reports_day_and_before_its_year_are_not_held_to_it():
    bars = bars_from(date(2025, 6, 2), 330, price=100.0, high=1.0, low=1.0)
    old_low = next(b for b in bars if b["t"][:10] == "2025-07-01")
    old_low["l"] = 60.0                                         # before the report's year: stands (it is outside the window too)
    report_day = "2026-09-01"
    newer = [b for b in bars if b["t"][:10] > report_day]
    assert newer
    newer[0]["l"] = 80.0                                        # after the report: a new low the report doesn't know
    fitted = stock_pages.fit_to_exchange_range(bars, [101.0, "2026-03-02", 99.0, "2026-04-01"], report_day)
    assert next(b for b in fitted if b["t"] == old_low["t"])["l"] == 60.0
    assert next(b for b in fitted if b["t"] == newer[0]["t"])["l"] == 80.0
    assert stock_pages.fit_to_exchange_range(bars, None, report_day) is bars and stock_pages.fit_to_exchange_range(bars, [1], report_day) is bars
    assert stock_pages.fit_to_exchange_range(bars, [101.0, "x", 99.0, "y"], None) is bars


def test_the_public_pages_candles_are_held_to_the_report_in_the_data_path():
    src = open(main.__file__, encoding="utf-8").read()
    body = src[src.index("def stock_page_bars("):src.index("_class_pages: dict")]
    assert "fit_to_exchange_range" in body and "official_close.ranges()" in body


# ---------- R10V-004: a price without numbers, and a market value from a cover page ----------
BIDU_COVER = ('<dei:EntityCommonStockSharesOutstanding contextRef="a" unitRef="sh">2197993760</dei:EntityCommonStockSharesOutstanding>'
              '<dei:EntityCommonStockSharesOutstanding contextRef="b" unitRef="sh">524020320</dei:EntityCommonStockSharesOutstanding>'
              '<dei:EntityCommonStockSharesOutstanding contextRef="p" unitRef="sh">7232838</dei:EntityCommonStockSharesOutstanding>'
              '<dei:EntityCommonStockSharesOutstanding contextRef="adr" unitRef="sh">99</dei:EntityCommonStockSharesOutstanding>')


def cover_contexts():
    ax = "ifrs-full:ClassesOfShareCapitalAxis"
    return [ctx("a", None, "2025-12-31", (ax, "db:CommonClassAMember")), ctx("b", None, "2025-12-31", (ax, "db:CommonClassBMember")),
            ctx("p", None, "2025-12-31", (ax, "db:FirstPreferenceSharesMember")), ctx("adr", None, "2025-12-31", (ax, "db:AmericanDepositarySharesMember"))]


def test_a_cover_page_that_counts_shares_per_class_gives_every_ordinary_share_and_no_preference_share():
    got = sec.cover_shares(sec.instance(instance(BIDU_COVER, cover_contexts())))
    assert got == {"value": 2_197_993_760 + 524_020_320, "end": "2025-12-31", "classes": 2}      # Baidu: Class A and Class B
    assert sec.cover_shares(sec.instance(instance("", []))) is None
    # an undimensioned count (the usual cover page) counts alone
    plain = instance('<dei:EntityCommonStockSharesOutstanding contextRef="x" unitRef="sh">1000</dei:EntityCommonStockSharesOutstanding>', [ctx("x", None, "2025-12-31")])
    assert sec.cover_shares(sec.instance(plain))["value"] == 1000.0
    # the latest date given is the one used
    two = instance('<dei:EntityCommonStockSharesOutstanding contextRef="x" unitRef="sh">1000</dei:EntityCommonStockSharesOutstanding>'
                   '<dei:EntityCommonStockSharesOutstanding contextRef="y" unitRef="sh">900</dei:EntityCommonStockSharesOutstanding>',
                   [ctx("x", None, "2026-01-31"), ctx("y", None, "2025-12-31")])
    assert sec.cover_shares(sec.instance(two))["end"] == "2026-01-31"


def test_a_company_with_no_share_count_in_the_facts_takes_it_from_its_newest_covers_classes(monkeypatch):
    # Baidu and BP: the cover page gives the count per class, which the company facts leave out, so there was no market value
    inst = instance(db_instance().split("</xbrli:unit>")[-1].replace("</xbrli:xbrl>", "") + BIDU_COVER, cover_contexts() + [
        ctx("p2025", *year(2025)), ctx("bc25", None, "2025-12-31", CONSOLIDATED)])
    facts = companyfacts(1159508, {"Revenue": [(2025, 31_434_000_000, *NEW), (2024, 31_504_000_000, *OLD)],
                                   "ProfitLoss": [(2025, 6_800_000_000, *NEW), (2024, 2_900_000_000, *OLD)]})
    s = sec.SEC(transport=transport(1159508, facts, submissions(1159508, DB_FILINGS), {NEW[0]: inst.replace("<xbrli:xbrl ", "<xbrli:xbrl ", 1)}))
    monkeypatch.setattr(s, "ads", lambda subs: {"ratio": 8.0, "ads": True, "form": "20-F", "treasury": None, "url": ""})
    p = s.company("DBK")
    assert p["shares"] == 2_197_993_760 + 524_020_320 and p["shares_from"] == "cover" and p["ads_ratio"] == 8.0
    r = sec.ratios({**p, "fx": {"rate": 1.1}}, 80.0)
    assert r["Market Cap"] == pytest.approx(80.0 * (2_722_014_080 / 8.0) / 1e6, rel=1e-3)          # about $27B for 8 shares an ADS


def test_a_company_whose_20f_is_filed_without_data_is_one_with_no_numbers_not_one_with_no_page():
    # ICICI Bank: the SEC has no company facts for its 20-F; its page showed no price at all
    s = sec.SEC(transport=transport(1103838, None, submissions(1103838, [("20-F", "0001-26-000001", "2026-06-01", "ibn.htm")]), {}))
    with pytest.raises(sec.NoNumbers) as e:
        s.company("DBK")
    assert "not as structured data" in str(e.value) and isinstance(e.value, sec.SourceError)
    with pytest.raises(sec.NoNumbers):
        s.company("DBK")                                      # the same answer again from the memory of it
    assert s.listing("DBK")["name"] == "Dbank AG" and s.cik("DBK") == 1103838


def price_only(**kw):
    f = stock_pages.facts("US", "IBN", {"name": "ICICI Bank Ltd", "industry_path": [], "no_numbers": "x"}, deepdive.numbers({"unit": "$ million"}),
                          {}, None, {"price": 27.9, "price_at": "2026-10-08", "price_basis": "close", "high52": 31.0, "low52": 26.0}, [],
                          "Listed in the US", None, {"no_numbers": sec.NO_RESULTS["no_xbrl"], **kw})
    return f


def test_a_price_only_page_shows_the_price_and_range_and_says_why_it_has_no_numbers():
    f = price_only()
    assert f["no_numbers"] and f["price"] == 27.9 and not stock_pages.has_content(f)
    page = stock_pages.render(f, "US", "IBN", None)
    assert "$27.90" in page and "$26.00 to $31.00" in page and "aren't available to show here right now" not in page
    assert stat(page, "Market cap") == "n/a" and "data-cap-missing" in page and "not as structured data" in page
    assert '<meta name="robots" content="noindex,follow">' in page and 'rel="canonical"' not in page
    assert len(re.search(r'<meta name="description" content="([^"]*)"', page).group(1)) <= 160
    assert "Revenue and profit trend" not in page
    assert "<h2>Revenue and profit</h2>" not in page


def test_the_price_only_company_is_built_from_the_sec_listing_and_never_for_a_fund_or_a_missing_price(monkeypatch):
    meta = {"price": 27.9, "type": "EQUITY"}
    monkeypatch.setattr(main.research_hub.yahoo, "meta", lambda s: meta)
    monkeypatch.setattr(main.sec_feed, "listing", lambda s: {"cik": 1, "name": "ICICI Bank Ltd"})
    got = main.price_only_company("IBN", {"name": "x"}, sec.NO_RESULTS["no_xbrl"])
    assert got["name"] == "ICICI Bank Ltd" and got["no_numbers"] == sec.NO_RESULTS["no_xbrl"] and got["pl"] is None
    assert main.price_only_company("IBN", {"name": "x"}, sec.NO_RESULTS["fund"]) is None
    assert main.price_only_company("IBN", {"name": "x"}, sec.NO_RESULTS["stopped"]) is None
    meta["type"] = "ETF"
    assert main.price_only_company("IBN", {"name": "x"}, sec.NO_RESULTS["no_xbrl"]) is None
    meta.update(type="EQUITY", price=None)
    assert main.price_only_company("IBN", {"name": "x"}, sec.NO_RESULTS["no_xbrl"]) is None
    meta.update(price=27.9)
    assert main.price_only_company("IBN-PA", {"name": "x"}, sec.NO_RESULTS["no_xbrl"]) is None       # a preferred share


def test_a_page_with_no_market_value_says_why_when_it_knows():
    f = facts_page("Mar 2026", market_cap=None, pe=None, cap_why="shares")
    page = stock_pages.render(f, "US", "BIDU", None)
    assert stat(page, "Market cap") == "n/a" and "data-cap-missing" in page and "number of shares in issue couldn't be read" in page
    # no reason known (an older page): nothing is claimed
    page = stock_pages.render(facts_page("Mar 2026", market_cap=None, pe=None), "US", "BIDU", None)
    assert stat(page, "Market cap") is None and "data-cap-missing" not in page
    # a failed check keeps its own note
    assert stock_pages.cap_missing_reason(facts_page("Mar 2026", cap_why="shares")) is None


# ---------- R10V-005: descriptions of at most 160 characters, no canonical on a noindex page ----------
def test_a_company_pages_description_is_at_most_160_characters():
    f = facts_page("Mar 2026", name="Industrial and Commercial Bank of China Limited", symbol="IDCBY")
    d = stock_pages.description(f)
    assert len(d) <= stock_pages.DESCRIPTION_MAX == 160 and d.startswith("Industrial and Commercial Bank of China Limited (IDCBY)")
    short = stock_pages.description(facts_page("Mar 2026", name="Acme", symbol="ACME"))
    assert "$14.00" in short and "1-year range $12.00 to $16.00" in short and short.endswith("from reported data.")
    huge = stock_pages.description(facts_page("Mar 2026", name="N" * 200, symbol="X"))
    assert len(huge) <= 160 and huge.endswith("…")


def test_a_page_kept_out_of_search_results_names_no_canonical_address(monkeypatch):
    nf = stock_pages.not_found("IN", "NOSUCHTICKER")
    assert 'content="noindex,follow"' in nf and 'rel="canonical"' not in nf and 'property="og:url"' not in nf
    assert 'rel="canonical"' not in stock_pages.busy_page("IN", "TCS", "Tata")
    assert 'rel="canonical"' not in stock_pages.render(None, "US", "ZZZZ", "Zed")
    assert 'rel="canonical"' not in stock_pages.index_page("IN", "tata")                      # a search is noindex
    # the pages that are indexed keep theirs
    assert '<link rel="canonical" href="https://stratlab.studio/stocks">' in stock_pages.index_page(None, "")
    assert '<link rel="canonical" href="https://stratlab.studio/stocks/us/RDY">' in stock_pages.render(facts_page("Mar 2026"), "US", "RDY", None)


# ---------- R10V-007: peers ----------
def peer(s, ind, cap, sector="Services", foreign=False, name=None):
    return {"symbol": s, "name": name or s, "industry": ind, "sector": sector, "market_cap": cap, "cap_checked": True,
            "price_at": "2026-10-08", "foreign": foreign}


def peers_world(monkeypatch, rows, sp):
    cos = {r["symbol"]: {"name": r["name"], "sym": r["symbol"], "bse": None} for r in rows}
    monkeypatch.setattr(stock_pages, "companies", lambda r: cos)
    monkeypatch.setattr(stock_pages, "_index_rows", lambda r: rows)
    monkeypatch.setattr(stock_pages, "_sp500_sectors", lambda: sp)


def test_visas_industry_peers_leave_out_foreign_and_unrelated_filers_of_a_broad_code(monkeypatch):
    nec = "Services-Business Services, Nec"
    rows = [peer("V", nec, 700_500.0), peer("MA", nec, 520_000.0), peer("PYPL", nec, 70_000.0), peer("FI", nec, 60_000.0),
            peer("BABA", nec, 300_000.0, foreign=True), peer("MELI", nec, 100_000.0, foreign=True), peer("RELX", nec, 90_000.0, foreign=True),
            peer("RBA", nec, 20_000.0), peer("GRAB", nec, 20_000.0, foreign=True), peer("UBER", nec, 180_000.0)]
    peers_world(monkeypatch, rows, {"V": "Financials", "MA": "Financials", "PYPL": "Financials", "FI": "Financials", "UBER": "Industrials"})
    got = {s["title"]: [x[0] for x in s["rows"]] for s in stock_pages.peer_sections("US", "V", ["Services", nec], 700_500.0)}
    assert got["Same industry"] == ["MA", "PYPL", "FI"]
    for gone in ("BABA", "MELI", "RELX", "RBA", "GRAB", "UBER"):
        assert gone not in got["Same industry"]
    # a company of a specific industry outside the index still counts when it is of the same kind
    rows.append(peer("DELL", "Electronic Computers", 90_000.0, "Manufacturing"))
    rows.append(peer("AAPL", "Electronic Computers", 4_970_000.0, "Manufacturing"))
    rows.append(peer("ASMLY", "Electronic Computers", 80_000.0, "Manufacturing", foreign=True))
    rows.append(peer("NOIDX", "Electronic Computers", 60_000.0, "Manufacturing"))
    sp = {"AAPL": "Information Technology", "DELL": "Information Technology"}
    peers_world(monkeypatch, rows, sp)
    apple = {s["title"]: [x[0] for x in s["rows"]] for s in stock_pages.peer_sections("US", "AAPL", ["Manufacturing", "Electronic Computers"], 4_970_000.0)}
    assert "NOIDX" in apple["Same industry"] and "ASMLY" not in apple["Same industry"]        # a US filer beside a US filer


def test_a_company_shows_once_across_the_sector_and_industry_lists(monkeypatch):
    ind = "Electronic Computers"
    rows = [peer("AAPL", ind, 4_970_000.0, "Manufacturing"), peer("DELL", ind, 90_000.0, "Manufacturing"), peer("SMCI", ind, 60_000.0, "Manufacturing"),
            peer("NVDA", "Semiconductors", 5_550_000.0, "Manufacturing"), peer("MSFT", "Software", 3_880_000.0, "Manufacturing")]
    peers_world(monkeypatch, rows, {s: "Information Technology" for s in ("AAPL", "DELL", "SMCI", "NVDA", "MSFT")})
    got = {s["title"]: [x[0] for x in s["rows"]] for s in stock_pages.peer_sections("US", "AAPL", ["Manufacturing", ind], 4_970_000.0)}
    assert got["Same industry"] == ["DELL", "SMCI"] and got["Same sector"] == ["NVDA", "MSFT"]      # Dell was in both lists
    assert not set(got["Same industry"]) & set(got["Same sector"])


def test_the_index_row_says_whether_a_us_company_is_a_foreign_filer():
    assert screens.row("US", "BABA", facts_page("Mar 2026", symbol="BABA", foreign=True))["foreign"] is True
    assert screens.row("US", "V", facts_page("Mar 2026", symbol="V", foreign=False))["foreign"] is False
    old = {k: v for k, v in facts_page("Mar 2026").items() if k != "foreign"}
    assert screens.row("US", "OLD", old)["foreign"] is None
