"""Round 7 visitor review of the live site (9 Oct 2026), the server's side: the largest US companies list missing Alphabet,
Berkshire and Visa (several classes of shares), one definition of P/E and of the dividend yield, 20-F filers a year
behind and a bank's sign-flipped profit, prices dated by their session, the long tail of small caps a session or two
behind and sub-dime prices rounded to cents, noindex pages in the sitemap, and peer lists. The SEC fixtures in
tests/fixtures/sec_r7v are the SEC's own public data, trimmed to what each test reads."""
import json
import re
import time
from datetime import date, datetime, timezone
from pathlib import Path

import httpx
import pytest

from app import main  # noqa: F401, I001  (first: the app loads the newsletter job before the modules built on it)
from app import corp_actions, db, library_seed, screens, stock_pages
from app.intel import net, routes as research_routes, sec

FIX = Path(__file__).parent / "fixtures" / "sec_r7v"
ROOT = Path(__file__).resolve().parents[2]
UTC = timezone.utc


def fixture(name: str):
    text = (FIX / name).read_text(encoding="utf-8")
    return json.loads(text) if name.endswith(".json") else text


@pytest.fixture
def mem(monkeypatch):
    """The settings table in memory."""
    store: dict = {}
    monkeypatch.setattr(db, "get_setting", lambda k: store.get(k))
    monkeypatch.setattr(db, "set_setting", lambda k, v: store.__setitem__(k, v))
    monkeypatch.setattr(db, "delete_setting", lambda k: store.pop(k, None))
    monkeypatch.setattr(db, "all_settings_with_prefix", lambda p, *a: [(k, v) for k, v in sorted(store.items()) if k.startswith(p)])
    monkeypatch.setattr(db, "prefetch_settings", lambda keys: None)
    screens._mem.clear()
    yield store
    screens._mem.clear()


def us(**kw) -> dict:
    """A US page's facts; market value in $ million."""
    base = {"region": "US", "symbol": "ACME", "name": "Acme Inc", "exchange": "Listed in the US", "industry": ["Manufacturing", "Widgets"],
            "currency": "USD", "unit": "$ million", "market_cap_unit": "$ million", "price": 50.0, "price_at": "2026-10-08",
            "price_basis": "close", "high52": 60.0, "low52": 40.0, "market_cap": 50_000.0, "pe": 20.0, "div_yield": 1.0,
            "net_margin": 10.0, "opm": 20.0, "years": [{"year": "Dec 2025", "sales": 20_000.0, "profit": 2_000.0, "opm": 20.0, "debt": 100.0}],
            "growth": {}, "filings": [], "built_at": "2026-10-08T22:00:00+00:00", "v": stock_pages.FACTS_VERSION, "sales_usd": 20_000.0}
    return {**base, **kw}


def india(**kw) -> dict:
    base = {**us(), "region": "IN", "symbol": "TCS", "name": "Tata Consultancy Services Ltd", "exchange": "NSE", "currency": "INR",
            "unit": "₹ crore", "market_cap_unit": "₹ crore", "industry": ["Information Technology", "IT - Software"]}
    base.pop("sales_usd")
    return {**base, **kw}


def companies(monkeypatch, region: str, symbols: list[str]):
    cos = {s: {"name": s, "sym": s, "bse": None} for s in symbols}
    real = stock_pages.companies
    monkeypatch.setattr(stock_pages, "companies", lambda r: cos if r == region else real(r))
    return cos


# ---------- R7V-003: a 20-F the SEC's company facts leave out is read from the filing itself ----------
TSM_CIK = 1046179
TSM_NEW = "0001628280-26-025362"


def tsm_subs() -> dict:
    return {"cik": TSM_CIK, "name": "Taiwan Semiconductor Manufacturing Co Ltd", "sic": "3674", "sicDescription": "Semiconductors & Related Devices",
            "tickers": ["TSM"], "addresses": {"business": {"isForeignLocation": 1}},
            "filings": {"recent": {"form": ["6-K", "20-F", "6-K", "20-F"],
                                   "filingDate": ["2026-07-16", "2026-04-16", "2025-07-17", "2025-04-17"],
                                   "accessionNumber": ["0001046179-26-000010", TSM_NEW, "0001046179-25-000010", "0001193125-25-083423"],
                                   "primaryDocument": ["a.htm", "tsm-20251231.htm", "b.htm", "d896993d20f.htm"], "items": ["", "", "", ""]}}}


def tsm_transport(calls: list):
    def handler(r: httpx.Request):
        calls.append(r.url.path)
        if r.url.path == "/files/company_tickers.json":
            return httpx.Response(200, json={"0": {"cik_str": TSM_CIK, "ticker": "TSM", "title": "TAIWAN SEMICONDUCTOR MANUFACTURING CO LTD"}})
        if r.url.path == f"/submissions/CIK{TSM_CIK:010d}.json":
            return httpx.Response(200, json=tsm_subs())
        if r.url.path == f"/api/xbrl/companyfacts/CIK{TSM_CIK:010d}.json":
            return httpx.Response(200, json=fixture("tsm-companyfacts.json"))
        if r.url.path == f"/Archives/edgar/data/{TSM_CIK}/{TSM_NEW.replace('-', '')}/tsm-20251231_htm.xml":
            return httpx.Response(200, text=fixture("tsm-20251231_htm.xml"))
        if r.url.path == f"/Archives/edgar/data/{TSM_CIK}/{TSM_NEW.replace('-', '')}/tsm-20251231.htm":
            # the 20-F's cover page, as TSMC writes it (the rest of the report left out)
            return httpx.Response(200, text="<html><p>ANNUAL REPORT PURSUANT TO SECTION 13 OR 15(d) For the fiscal year ended December 31, "
                                            "2025 Commission file number: 001-14700 " + "x " * 200 + "Securities registered or to be "
                                            "registered pursuant to Section 12(b) of the Act. Title of each class Trading Symbol(s) American "
                                            "Depositary Shares, each representing 5 Common Shares TSM New York Stock Exchange. "
                                            "Table of contents</p></html>")
        return httpx.Response(404)
    return httpx.MockTransport(handler)


def test_a_20f_missing_from_the_company_facts_is_read_from_the_filing():
    # TSMC's 20-F of 16 Apr 2026, filed under the 2025 IFRS taxonomy, isn't in the SEC's company facts: the page stopped
    # at Dec 2024 (NT$2,894,308m of revenue) and its P/E of 65.5 was on 2024's profit
    facts = fixture("tsm-companyfacts.json")
    assert not sec.has_filing(facts, TSM_NEW) and sec.has_filing(facts, "0001193125-25-083423")
    calls: list = []
    s = sec.SEC(transport=tsm_transport(calls))
    p = s.company("TSM")
    pl = dict(zip(p["pl"]["cols"], p["pl"]["rows"]["Net Profit"]))
    sales = dict(zip(p["pl"]["cols"], p["pl"]["rows"]["Sales"]))
    assert p["pl"]["cols"][-1] == "Dec 2025" and p["unit"] == "TWD million"
    assert sales["Dec 2025"] == 3_809_054.3 and pl["Dec 2025"] == 1_697_604.0 and sales["Dec 2024"] == 2_894_307.7
    assert p["eps"]["basis"] == "year" and p["eps"]["end"] == "2025-12-31" and 65.4 <= p["eps"]["value"] <= 65.5
    assert p["ads_ratio"] == 5
    # the P/E on 2025's earnings, labelled with its year: $457.99 an ADS, five shares of NT$65.46 at 0.0313 $/NT$
    p = {**p, "fx": {"rate": 0.0313}}
    pe, basis = sec.pe_and_basis(p, 457.99)
    assert basis == {"basis": "year", "end": "2025-12-31"} and 44 < pe < 45.5
    # the filing is read once a month, not at every build
    assert s.filing_data(TSM_CIK, sec.latest_filing(tsm_subs(), sec.ANNUAL_FORMS))["facts"]
    instance_reads = [c for c in calls if c.endswith("_htm.xml")]
    assert len(instance_reads) == 1


def test_the_instance_reader_takes_figures_without_dimensions_in_the_company_facts_shape():
    inst = sec.instance(fixture("tsm-20251231_htm.xml"))
    got = sec.instance_facts(inst, "20-F", "2026-04-16", TSM_NEW)
    rows = got["ifrs-full"]["RevenueFromContractsWithCustomers"]["units"]["TWD"]
    year = next(r for r in rows if r["start"] == "2025-01-01" and r["end"] == "2025-12-31")
    assert year == {"start": "2025-01-01", "end": "2025-12-31", "val": 3_809_054_300_000.0, "accn": TSM_NEW, "form": "20-F", "filed": "2026-04-16"}
    assert "TWD/shares" in got["ifrs-full"]["BasicEarningsLossPerShare"]["units"]
    # an ADS figure (a dimension) never stands for the ordinary share's
    assert all(r["val"] < 100 for r in got["ifrs-full"]["BasicEarningsLossPerShare"]["units"]["TWD/shares"])
    with pytest.raises(ValueError):
        sec.instance('<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><xbrl></xbrl>')


def test_a_pe_on_a_year_that_ended_over_15_months_ago_is_na_and_a_yearly_one_is_labelled():
    old = us(symbol="TSM", unit="TWD million", pe=65.5, pe_basis="year", pe_end="2024-12-31", price_at="2026-10-08")
    assert stock_pages.pe_stale(old) and stock_pages.shown_pe(old) is None
    page = stock_pages.render(old, "US", "TSM", None)
    assert "<span>P/E (year to Dec 2024)</span><b>n/a</b>" in page and "data-pe-old" in page and "65.5" not in page
    new = {**old, "pe": 44.7, "pe_end": "2025-12-31"}
    assert not stock_pages.pe_stale(new) and stock_pages.shown_pe(new) == 44.7
    assert "<span>P/E (year to Dec 2025)</span><b>44.7</b>" in stock_pages.render(new, "US", "TSM", None)
    # the last four quarters' earnings: plain "P/E"
    assert "<span>P/E</span><b>20.0</b>" in stock_pages.render(us(pe_basis="ttm", pe_end="2026-06-30"), "US", "ACME", None)


def test_santander_chiles_2021_profit_isnt_a_loss():
    # its 2019-2021 reports tag the profit attributable to shareholders as -842,467 (CLP million) for 2021, a year whose
    # total profit was +852,428 and whose minority's share was 9,961
    p = sec.build(fixture("bsac-companyfacts.json"), {"sic": "6029"})
    pl = dict(zip(p["pl"]["cols"], p["pl"]["rows"]["Net Profit"]))
    assert pl["Dec 2021"] == 842_467.0 and pl["Dec 2020"] == 547_614.0 and pl["Dec 2022"] == 792_276.0
    assert all(v > 0 for v in pl.values())


def test_a_real_shareholders_loss_beside_a_minoritys_profit_stands():
    owners, total, minority = {"2025-12-31": -200.0, "2024-12-31": -95.0}, {"2025-12-31": 100.0, "2024-12-31": 100.0}, {"2025-12-31": 300.0}
    sec.owner_sign(owners, total, minority)
    assert owners["2025-12-31"] == -200.0                          # 100 - 300 = -200: as filed
    assert owners["2024-12-31"] == 95.0                            # no minority figure, about the total's size: a flipped sign
    far = {"2025-12-31": -20.0}
    sec.owner_sign(far, {"2025-12-31": 100.0}, {})
    assert far["2025-12-31"] == -20.0                              # far from the total's size: not a sign error


# ---------- R7V-001: every class of shares, the list from the pages' own values, GOOG ----------
def test_berkshire_and_visa_count_every_class_of_their_shares():
    brk = sec.class_shares(sec.instance(fixture("brka-20260630_htm.xml")))
    # 488,450 Class A shares, each earning what 1,500 Class B shares do, and 1,408,035,161 Class B shares
    assert brk["BRK-B"] == pytest.approx(488_450 * 1500 + 1_408_035_161, rel=1e-3)
    assert brk["BRK-A"] == pytest.approx(488_450 + 1_408_035_161 / 1500, rel=1e-3)
    v = sec.class_shares(sec.instance(fixture("v-20260630_htm.xml")))
    assert set(v) == {"V"} and v["V"] == pytest.approx(1_867_610_089, rel=1e-6)    # class A plus B-1, B-2, B-3 and C as converted
    # the market value at the 8 Oct closes: Berkshire about $1.09 trillion at $511.05, Visa about $0.70 trillion at $375.10
    p = sec.for_symbol({"shares": None, "class_shares": brk}, "BRK.B")
    assert p["symbol"] == "BRK.B" and stock_pages.cap_text({"currency": "USD", "market_cap": sec.market_value(p, 511.05)}) == "$1.09T"
    assert stock_pages.cap_text({"currency": "USD", "market_cap": sec.market_value({"shares": v["V"]}, 375.10)}) == "$700.5B"


def test_a_company_with_one_class_or_an_unknown_weight_gets_no_class_count():
    one = sec.instance(fixture("v-20260630_htm.xml").replace("v:CommonClassB1Member", "us-gaap:CommonClassAMember")
                       .replace("v:CommonClassB2Member", "us-gaap:CommonClassAMember").replace("v:CommonClassB3Member", "us-gaap:CommonClassAMember")
                       .replace("us-gaap:CommonClassCMember", "us-gaap:CommonClassAMember"))
    assert sec.class_shares(one) == {}
    no_eps = sec.instance(re.sub(r"<us-gaap:EarningsPerShare\w+ [^>]*>[^<]*</us-gaap:EarningsPerShare\w+>", "", fixture("v-20260630_htm.xml")))
    assert sec.class_shares(no_eps) == {}


def test_berkshire_b_gets_its_class_count_from_its_latest_report():
    cik, acc = 1067983, "0001193125-26-341032"
    facts = {"cik": cik, "entityName": "BERKSHIRE HATHAWAY INC", "facts": {"us-gaap": {
        "Revenues": {"units": {"USD": [{"start": "2025-01-01", "end": "2025-12-31", "val": 371e9, "form": "10-K", "filed": "2026-03-02", "accn": "a"}]}},
        "NetIncomeLoss": {"units": {"USD": [{"start": "2025-01-01", "end": "2025-12-31", "val": 66e9, "form": "10-K", "filed": "2026-03-02", "accn": "a"}]}}}}}
    subs = {"cik": cik, "name": "BERKSHIRE HATHAWAY INC", "sic": "6331", "tickers": ["BRK-B", "BRK-A"],
            "filings": {"recent": {"form": ["10-Q", "10-K"], "filingDate": ["2026-08-10", "2026-03-02"], "accessionNumber": [acc, "a"],
                                   "primaryDocument": ["brka-20260630.htm", "brka-20251231.htm"], "items": ["", ""]}}}

    def handler(r: httpx.Request):
        if r.url.path == "/files/company_tickers.json":
            return httpx.Response(200, json={"0": {"cik_str": cik, "ticker": "BRK-B", "title": "BERKSHIRE HATHAWAY INC"},
                                             "1": {"cik_str": cik, "ticker": "BRK-A", "title": "BERKSHIRE HATHAWAY INC"}})
        if r.url.path.startswith("/submissions/"):
            return httpx.Response(200, json=subs)
        if "companyfacts" in r.url.path:
            return httpx.Response(200, json=facts)
        if r.url.path.endswith("brka-20260630_htm.xml"):
            return httpx.Response(200, text=fixture("brka-20260630_htm.xml"))
        return httpx.Response(404)
    s = sec.SEC(transport=httpx.MockTransport(handler))
    b, a = s.company("BRK-B"), s.company("BRK.A")
    assert b["shares"] == pytest.approx(2_140_827_931, rel=1e-3) and a["shares"] == pytest.approx(1_426_989, rel=1e-3)
    assert sec.ratios(b, 511.05)["Market Cap"] == pytest.approx(1_094_000, rel=0.01)


def test_the_largest_list_reads_each_companys_own_page(mem, monkeypatch):
    companies(monkeypatch, "US", ["NVDA", "AAPL", "MSFT", "GOOGL", "BRK-B", "V", "BBD"])
    rows = [{"symbol": "NVDA", "name": "NVIDIA", "market_cap": 5_600_000.0, "cap_checked": True},
            {"symbol": "AAPL", "name": "Apple", "market_cap": 4_968_000.0, "cap_checked": True},
            {"symbol": "MSFT", "name": "Microsoft", "market_cap": 3_884_000.0, "cap_checked": True},
            {"symbol": "BBD", "name": "Bradesco", "market_cap": 47_600.0, "cap_checked": True}]
    mem[screens.INDEX_KEY + "US"] = json.dumps({"at": "2026-10-09", "rows": rows})
    # Alphabet: $4.26T on its own page, missing from the index; Berkshire and Visa: every class counted now
    for s, cap in (("GOOGL", 4_260_000.0), ("BRK-B", 1_094_000.0), ("V", 700_500.0), ("MSFT", 3_884_000.0)):
        mem[f"stocks:page:US:{s}"] = json.dumps({"ts": 1, "facts": us(symbol=s, market_cap=cap, sales_usd=400_000.0)})
    # Bradesco's stored page now fails its checks: its old index row doesn't rank it
    mem["stocks:page:US:BBD"] = json.dumps({"ts": 1, "facts": us(symbol="BBD", market_cap=45_900_000.0, sales_usd=55_000.0)})
    big, ranked = stock_pages.largest("US")
    assert ranked and [s for s, _ in big] == ["NVDA", "AAPL", "GOOGL", "MSFT", "BRK-B", "V"]


def test_goog_opens_alphabets_page(mem, monkeypatch):
    from fastapi.testclient import TestClient
    companies(monkeypatch, "US", ["GOOGL", "BRK-B", "AAPL"])
    names = {"GOOGL": {"cik": 1652044, "name": "Alphabet Inc."}, "GOOG": {"cik": 1652044, "name": "Alphabet Inc."},
             "BRK-B": {"cik": 1067983, "name": "BERKSHIRE HATHAWAY INC"}, "BRK-A": {"cik": 1067983, "name": "BERKSHIRE HATHAWAY INC"},
             "AAPL": {"cik": 320193, "name": "Apple Inc."}, "BAC-PL": {"cik": 70858, "name": "BANK OF AMERICA"}}
    main.sec_feed.cache.set("tickers", names, 3600)
    main._class_pages.update(names=None, by_cik={})
    try:
        assert stock_pages.find("US", "GOOG")[0] == "GOOGL" and stock_pages.find("US", "BRK.A")[0] == "BRK-B"
        assert stock_pages.find("US", "BAC-PL") is None and stock_pages.find("US", "NOPE") is None
        r = TestClient(main.app).get("/stocks/us/GOOG", follow_redirects=False)
        assert r.status_code == 301 and r.headers["location"] == "/stocks/us/GOOGL"
    finally:
        main.sec_feed.cache.pop("tickers")
        main._class_pages.update(names=None, by_cik={})


def test_no_share_class_lookup_reads_the_sec_on_its_own(monkeypatch):
    monkeypatch.setattr(main.sec_feed, "tickers", lambda: pytest.fail("a 404 must not read the SEC's list"))
    main.sec_feed.cache.pop("tickers")
    assert main.us_share_class_page("GOOG") is None


# ---------- R7V-002: one P/E and one dividend yield, on every page and in the app ----------
def test_apples_pe_is_the_close_over_four_quarters_earnings_per_share_as_in_the_app(monkeypatch):
    p = sec.build(fixture("aapl-companyfacts.json"), {"sic": "3571"})
    assert p["eps"] == {"value": 8.71, "basis": "ttm", "end": "2026-06-27"}      # 1.84 + 2.84 + 2.01 + 2.02, diluted
    pe, basis = sec.pe_and_basis(p, 340.42)
    assert basis == {"basis": "ttm", "end": "2026-06-27"} and round(pe, 2) == 39.08
    assert sec.ratios(p, 340.42)["Stock P/E"] == 39.1                          # was 38.5: market cap over net profit
    # the app: the same earnings per share, set against its own price
    c = {"symbol": "AAPL", "quote": {"price": 340.42},
         "metrics": [{"title": "Valuation", "items": [{"label": "P/E", "value": 39.02}]},
                     {"title": "Per share and returns", "items": [{"label": "EPS TTM", "value": 8.72}]}]}
    monkeypatch.setattr(research_routes, "public_facts", lambda r, s: {"price": 340.42, "pe": 39.1, "eps": 8.71, "pe_basis": "ttm"})
    out = research_routes.with_public_eps("US", c)
    items = {i["label"]: i["value"] for g in out["metrics"] for i in g["items"]}
    assert items["EPS TTM"] == 8.71 and items["P/E"] == round(340.42 / 8.71, 2) and round(items["P/E"], 1) == 39.1


def test_a_pe_from_earnings_per_share_that_dont_match_the_value_gives_way_to_value_over_profit():
    p = {"shares": 1_000_000_000, "eps": {"value": 50.0, "basis": "ttm", "end": "2026-06-30"}, "ttm_end": "2026-06-30",
         "pl": {"cols": ["Dec 2025", "TTM"], "rows": {"Net Profit": [900.0, 1000.0]}}}
    pe, basis = sec.pe_and_basis(p, 100.0)          # $100bn over $1bn of profit is 100; $100 over $50 a share is 2
    assert pe == pytest.approx(100.0) and basis["basis"] == "ttm"
    loss = {**p, "pl": {"cols": ["Dec 2025", "TTM"], "rows": {"Net Profit": [900.0, -5.0]}}}
    assert sec.pe_and_basis(loss, 100.0)[0] is None


def test_tcs_yield_counts_every_dividend_of_the_year_specials_included(monkeypatch):
    # ex-dates in the year to the 8 Oct close of ₹2,076: ₹11 (15 Oct 2025), ₹11 + ₹46 special (16 Jan 2026), ₹31 (25 May),
    # ₹12 (15 Jul): ₹111, 5.35% (the page said 3.08%, the last reported year's)
    rows = [{"kind": "dividend", "sub": s, "amount": a, "ex_date": d} for d, a, s in
            (("2025-10-15", 11, "interim"), ("2026-01-16", 11, "interim"), ("2026-01-16", 46, "special"), ("2026-05-25", 31, "final"),
             ("2026-07-15", 12, "interim"), ("2025-07-17", 11, "interim"))]
    seen = {}
    monkeypatch.setattr(corp_actions, "actions_for", lambda r, s, src=None, today=None, fetch=True, **k: seen.update(fetch=fetch) or rows)
    monkeypatch.setattr(corp_actions, "hist_load", lambda r, s: {"at": "2026-10-08T12:00", "rows": rows})
    co = {"name": "TCS", "sym": "TCS", "bse": None}
    assert main.page_dividend_yield("IN", "TCS", 2076.0, "2026-10-08", co) == 5.35 and seen["fetch"] is True
    # a list that was read and has no dividend in the year: a real 0%
    monkeypatch.setattr(corp_actions, "actions_for", lambda *a, **k: [])
    assert main.page_dividend_yield("IN", "TCS", 2076.0, "2026-10-08", co) == 0.0
    # no list at all: the price history's dividends; neither: n/a, never another definition
    monkeypatch.setattr(corp_actions, "hist_load", lambda r, s: {"at": None, "rows": []})
    monkeypatch.setattr(main.research_hub.yahoo, "events", lambda sym, days: {"dividends": [{"date": "2026-01-16", "amount": 57.0}]})
    assert main.page_dividend_yield("IN", "TCS", 2076.0, "2026-10-08", co) == round(57 / 2076 * 100, 2)
    monkeypatch.setattr(main.research_hub.yahoo, "events", lambda sym, days: (_ for _ in ()).throw(RuntimeError("down")))
    assert main.page_dividend_yield("IN", "TCS", 2076.0, "2026-10-08", co) is None


def test_india_and_us_pages_define_pe_and_yield_in_the_same_words():
    def how(page):
        return [re.sub(r"<[^>]+>", "", x) for x in re.findall(r"<li>(P/E: .*?|Dividend yield: .*?)</li>", page)]
    a, b = how(stock_pages.render(india(), "IN", "TCS", None)), how(stock_pages.render(us(), "US", "ACME", None))
    assert len(a) == 2 and a == b
    assert "special dividends included" in a[1] and "four reported quarters" in a[0]
    assert "the last year's dividends" not in " ".join(a)


# ---------- R7V-004: a price dated by its session ----------
def test_a_price_read_before_indias_open_belongs_to_the_day_before():
    before_open = datetime(2026, 10, 9, 1, 45, tzinfo=UTC)               # 07:15 in India, Friday 9 Oct
    assert stock_pages.session_day("IN", before_open) == date(2026, 10, 8)
    assert stock_pages.session_day("IN", datetime(2026, 10, 9, 4, 0, tzinfo=UTC)) == date(2026, 10, 9)      # 09:30, trading
    assert stock_pages.session_day("US", datetime(2026, 10, 12, 12, 0, tzinfo=UTC)) == date(2026, 10, 9)    # Monday before the open


def test_hals_page_dates_its_price_and_never_calls_a_last_trade_a_close(monkeypatch):
    monkeypatch.setattr(stock_pages, "session_day", lambda region, now=None: date(2026, 10, 8))
    nums = {"years": [{"year": "Mar 2026", "sales": 31000.0, "profit": 8000.0}]}
    f = stock_pages.facts("IN", "HAL", {"name": "Hindustan Aeronautics Ltd"}, nums, {"price": 4647.0, "market_cap_cr": 310_000.0},
                          None, {}, [], "NSE")
    assert f["price"] == 4647.0 and f["price_at"] == "2026-10-08" and f["price_basis"] == "last"
    now = datetime(2026, 10, 9, 1, 45, tzinfo=UTC)
    assert stock_pages.price_label(f, now) == "Last price, 8 Oct 2026"
    assert stock_pages.as_of_text(f, now) == "8 Oct 2026 (last price)"
    # that session's close, when the candles come, takes its place and is called a close
    bars = [{"t": "2026-10-08T00:00:00+05:30", "o": 4600, "h": 4700, "l": 4590, "c": 4647.4, "official": True}]
    g = stock_pages.with_new_close(f, bars)
    assert g["price"] == 4647.4 and g["price_basis"] == "close" and stock_pages.price_label(g, now) == "Last close, 8 Oct 2026"
    # so does the exchange's official close
    h = stock_pages.with_official_close(f, 4647.4)
    assert h["price_basis"] == "close" and stock_pages.price_label(h, now) == "Last close, 8 Oct 2026"


# ---------- R7V-005: the long tail, closes read after they are final, sub-dime prices ----------
def test_prices_under_ten_cents_show_four_decimals():
    f = {"currency": "USD"}
    assert stock_pages._money(f, 0.0247) == "$0.0247" and stock_pages._money(f, 0.0999) == "$0.0999"
    assert stock_pages._money(f, 0.10) == "$0.10" and stock_pages._money(f, 8.79) == "$8.79" and stock_pages._money(f, 0) == "$0.00"


def test_a_cached_copy_is_never_older_than_the_caller_allows(monkeypatch):
    clock = [1_000_000.0]
    monkeypatch.setattr(net.time, "time", lambda: clock[0])
    c = net.TTLCache()
    c.set("k", "kept for a day", 86400)
    clock[0] += 600
    assert c.get("k") == "kept for a day" and c.get("k", max_age=900) == "kept for a day" and c.get("k", max_age=300) is None
    assert c.stored_at("k") == 1_000_000.0
    # a source: the chart read at 16:01, kept for a day by its caller, isn't given to the page that asks for one read
    # after 16:45
    calls = []

    def handler(r):
        calls.append(clock[0])
        return httpx.Response(200, json={"n": len(calls)})
    src = net.Source("https://example.test", transport=httpx.MockTransport(handler))
    assert src.fetch("/chart", ttl=86400) == {"n": 1}
    clock[0] += 44 * 60
    assert src.fetch("/chart", ttl=86400) == {"n": 1}
    assert src.fetch("/chart", ttl=60, with_time=True) == ({"n": 2}, clock[0])


def test_the_price_job_tries_again_when_the_new_close_isnt_out_yet(mem):
    now = datetime(2026, 10, 9, 0, 30, tzinfo=UTC)                      # 20:30 in New York, Thursday 8 Oct: settled
    day = stock_pages.last_close("US", now)[0].isoformat()
    assert day == "2026-10-08"
    built = now.timestamp() - 30 * 3600
    mem["stocks:page:US:BFLY"] = json.dumps({"ts": built, "facts": us(symbol="BFLY", price=8.79, price_at="2026-10-06", market_cap=2_000.0)})
    mem["stocks:page:US:NVDA"] = json.dumps({"ts": built, "facts": us(symbol="NVDA", price=200.0, price_at="2026-10-07", market_cap=5_000_000.0)})
    late = {"BFLY": True}

    def bars_of(region, sym):
        last = [{"t": "2026-10-07T00:00:00-04:00", "o": 8.4, "h": 8.64, "l": 8.13, "c": 8.27}]
        if not late.get(sym):
            last.append({"t": "2026-10-08T00:00:00-04:00", "o": 8.1, "h": 8.17, "l": 7.79, "c": 8.03})
        return last
    pages = stock_pages.Pages(lambda r, c: None)
    got = pages.refresh_prices("US", bars_of, gap=0, now=now)
    assert got["refreshed"] == 1 and got["retry"] == 1 and pages.prices_done.get("US") != day
    bfly = json.loads(mem["stocks:page:US:BFLY"])
    assert bfly["facts"]["price_at"] == "2026-10-07" and not bfly.get("price_ts")     # moved a session, not marked read
    late["BFLY"] = False                                                 # the source has the day now
    got = pages.refresh_prices("US", bars_of, gap=0, now=now)
    bfly = json.loads(mem["stocks:page:US:BFLY"])
    assert got["refreshed"] == 1 and bfly["facts"]["price"] == 8.03 and bfly["facts"]["price_at"] == day and bfly["price_ts"]
    assert pages.prices_done["US"] == day
    # a page the source never has the day for stops being read after a few tries
    late["NVDA"] = True
    mem["stocks:page:US:NVDA"] = json.dumps({"ts": built, "facts": us(symbol="NVDA", price=200.0, price_at="2026-10-06", market_cap=5_000_000.0)})
    pages.prices_done.clear()
    for _ in range(stock_pages.Pages.MAX_TRIES + 2):
        pages.refresh_prices("US", bars_of, gap=0, now=now)
    assert pages.tries["US"][1]["NVDA"] == stock_pages.Pages.MAX_TRIES and pages.prices_done["US"] == day


def test_a_pass_with_pages_left_over_runs_again_within_a_minute():
    assert main.refresh_backlog({"IN": {"refreshed": 300, "left": 40, "failed": 0}, "US": {"refreshed": 3, "left": 0, "failed": 0}})
    assert not main.refresh_backlog({"IN": {"refreshed": 3, "left": 0, "failed": 0}, "US": {"refreshed": 3, "left": 0, "failed": 0, "retry": 2}})
    assert not main.refresh_backlog({"IN": {"error": "down"}, "US": None})
    assert main.PRICE_REFRESH_BACKLOG <= 60 < main.PRICE_REFRESH_EVERY


# ---------- R7V-007: pages with nothing to show stay out of the sitemap ----------
def test_the_sitemap_leaves_out_pages_with_nothing_to_show(mem, monkeypatch):
    companies(monkeypatch, "US", ["AAPL", "VUECF", "WIPKF", "SIAI", "NEWCO", "FCHDF"])
    # built: AAPL with facts, VUECF and SIAI with nothing; not built yet: NEWCO, and FCHDF and WIPKF (foreign OTC lines)
    mem[stock_pages.BUILT_KEY + "US"] = json.dumps({"at": "2026-10-09", "pages": ["AAPL", "SIAI", "VUECF"], "shown": ["AAPL"]})
    xml = stock_pages.sitemap("stocks-us-1")
    listed = set(re.findall(r"/stocks/us/([A-Z.-]+)</loc>", xml))
    # changed on purpose in R8V-007: a page not built yet (NEWCO) is no longer listed until the screens' indexer has built
    # it, since an unbuilt page's first visit could be a 503 "being prepared" or a fund's 404 (MDXR)
    assert listed == {"AAPL"}
    # before the screens have gathered the stored pages: every company not marked as empty
    del mem[stock_pages.BUILT_KEY + "US"]
    mem["stocks:thin:US:SIAI"] = "1"
    listed = set(re.findall(r"/stocks/us/([A-Z.-]+)</loc>", stock_pages.sitemap("stocks-us-1")))
    assert listed == {"AAPL", "VUECF", "WIPKF", "NEWCO", "FCHDF"}


def test_the_index_records_which_pages_have_something_to_show(mem, monkeypatch):
    monkeypatch.setattr(screens, "with_us_red", lambda rows: rows)
    mem["stocks:page:US:AAPL"] = json.dumps({"ts": 1, "facts": us(symbol="AAPL")})
    mem["stocks:page:US:SIAI"] = json.dumps({"ts": 1, "facts": None})
    mem["stocks:page:US:GLDI"] = json.dumps({"ts": 1, "facts": us(symbol="GLDI", not_company="an ETN")})
    mem["stocks:page:US:OLD"] = json.dumps({"ts": 1, "facts": us(symbol="OLD", v=3)})
    index = screens.build_index("US")
    built = json.loads(mem[stock_pages.BUILT_KEY + "US"])
    assert built["pages"] == ["AAPL", "GLDI", "OLD", "SIAI"] and built["shown"] == ["AAPL", "OLD"]
    assert index["_empty"] == {"SIAI", "OLD"}                   # built again first, when a large company's


def test_the_indexer_builds_large_companies_with_nothing_stored_first(monkeypatch):
    cos = {s: {"name": s, "sym": s, "bse": None} for s in ("AAA", "GOOGL", "HPQ", "ZZZ")}
    monkeypatch.setattr(stock_pages, "companies", lambda r: cos)
    monkeypatch.setattr(stock_pages, "_seeds", lambda r: {"GOOGL"})
    now = time.time()
    ages = {"GOOGL": now - 7 * 3600, "AAA": now - 30 * 3600, "ZZZ": now - 3600}
    due = [s for s, _ in screens.Indexer(warm_per_run=4)._due("US", ages, {"GOOGL"})]
    assert due[:3] == ["HPQ", "GOOGL", "AAA"]                   # HP Inc. (S&P 500, never built), Alphabet's empty page, the stalest


# ---------- R7V-009: peers of a size, and with a current price ----------
def _row(s, ind, cap, sector="Manufacturing", at="2026-10-08"):
    return {"symbol": s, "name": s, "sector": sector, "industry": ind, "market_cap": cap, "cap_checked": True, "price_at": at}


def test_apples_peers_include_companies_of_its_size(mem, monkeypatch):
    rows = [_row("DELL", "Electronic Computers", 367_700.0), _row("HPQ", "Electronic Computers", 25_000.0),
            _row("SMCI", "Electronic Computers", 28_100.0), _row("OMCL", "Electronic Computers", 1_600.0),
            _row("ZEPP", "Electronic Computers", 61.0), _row("NVDA", "Semiconductors & Related Devices", 5_600_000.0),
            _row("MSFT", "Services-Prepackaged Software", 3_884_000.0, "Services"), _row("ORCL", "Services-Prepackaged Software", 700_000.0, "Services"),
            _row("LLY", "Pharmaceutical Preparations", 900_000.0)]
    mem[screens.INDEX_KEY + "US"] = json.dumps({"at": "2026-10-09", "rows": rows})
    companies(monkeypatch, "US", [r["symbol"] for r in rows] + ["AAPL"])
    secs = stock_pages.peer_sections("US", "AAPL", ["Manufacturing", "Electronic Computers"], 4_968_000.0)
    assert secs[0]["title"] == "Same sector" and "(Information Technology)" in secs[0]["caption"]
    first = [s for s, _ in secs[0]["rows"]]
    # changed on purpose in R10V-007: a company shows once, under the closer list. Dell and HP Inc. are the industry's, so
    # the sector's list (it listed Dell first) has the rest of the sector
    assert first[:3] == ["NVDA", "MSFT", "ORCL"] and "LLY" not in first and not {"DELL", "HPQ", "SMCI"} & set(first)
    assert secs[1]["title"] == "Same industry" and [s for s, _ in secs[1]["rows"]][:2] == ["DELL", "SMCI"] and "HPQ" in [s for s, _ in secs[1]["rows"]]
    # a small company in the same industry keeps its own industry first
    small = stock_pages.peer_sections("US", "OMCL", ["Manufacturing", "Electronic Computers"], 1_600.0)
    assert small[0]["title"] == "Same industry"


def test_a_peer_with_no_price_for_over_a_week_is_left_out(mem, monkeypatch):
    rows = [_row("INFY", "IT - Software", 405_000.0, "Information Technology"),
            _row("IDREAM", "IT - Software", 13_309.0, "Information Technology", at="2026-09-29"),
            _row("KPITTECH", "IT - Software", 12_899.0, "Information Technology", at="2026-10-08"),
            _row("NOPRICE", "IT - Software", 12_000.0, "Information Technology", at=None)]
    mem[screens.INDEX_KEY + "IN"] = json.dumps({"at": "2026-10-09", "rows": rows})
    companies(monkeypatch, "IN", [r["symbol"] for r in rows] + ["TCS"])
    monkeypatch.setattr(stock_pages, "nse_twins", lambda: {})
    monkeypatch.setattr(screens, "with_ranks", lambda rows: rows)
    got = [s for s, _ in stock_pages.peer_sections("IN", "TCS", ["Information Technology", "IT - Software"], 750_000.0)[0]["rows"]]
    assert got == ["INFY", "KPITTECH", "NOPRICE"]


# ---------- R7V-008: each library strategy's rules, written into its page at build time, match the seeds ----------
def test_the_sites_library_rules_match_the_seeds():
    src = (ROOT / "frontend" / "src" / "content" / "seo.ts").read_text()
    block = src[src.index("export const LIBRARY_RULES"):src.index("};", src.index("export const LIBRARY_RULES"))]
    listed = dict(re.findall(r'"([a-z0-9-]+)": "((?:[^"\\]|\\.)*)"', block))
    assert listed == {slug: s["text"] for slug, s in library_seed.STRATEGIES.items()}
