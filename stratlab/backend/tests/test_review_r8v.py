"""Round 8 visitor review of the live site (9 Oct 2026), the server's side: Mizuho's market value a tenth of its real one
(its 20-F still states the depositary ratio from before its 2020 share consolidation), a plausibility check on every
foreign filer's value against its own profit, Itaú on a two-year-old column and one class of shares, 20-F tables a year
behind with unlabelled P/Es (March and June years included), stored pages from before a fix served as they were, an
Indian value net of the shares employee trusts hold, the sitemap's unbuilt pages, the surveillance badges in dark mode,
one period for the EBITDA margin, and a large company's industry peers. tests/fixtures/sec_r8v holds the SEC's own
public data for Mizuho, Itaú, Toyota and BHP, trimmed to what the tests read (the 20-F cover pages without their
contact persons)."""
import json
import re
import time
from pathlib import Path

import httpx
import pytest

from app import main  # noqa: F401, I001  (first: the app loads the newsletter job before the modules built on it)
from app import corp_actions, db, screens, stock_pages
from app.intel import screener, sec

FIX = Path(__file__).parent / "fixtures" / "sec_r8v"
JPY, BRL = 1 / 158.2, 0.1996              # US dollars to one yen and one real on 8 Oct 2026, as the review read them


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
    screens._built.clear()
    yield store
    screens._mem.clear()
    screens._built.clear()


def us(**kw) -> dict:
    """A US page's facts; market value in $ million."""
    base = {"region": "US", "symbol": "ACME", "name": "Acme Inc", "exchange": "Listed in the US", "industry": ["Manufacturing", "Widgets"],
            "currency": "USD", "unit": "$ million", "market_cap_unit": "$ million", "price": 50.0, "price_at": "2026-10-08",
            "price_basis": "close", "high52": 60.0, "low52": 40.0, "market_cap": 50_000.0, "pe": 20.0, "div_yield": 1.0,
            "net_margin": 10.0, "opm": 20.0, "years": [{"year": "Dec 2025", "sales": 20_000.0, "profit": 2_000.0, "opm": 20.0, "debt": 100.0}],
            "growth": {}, "filings": [], "built_at": "2026-10-08T22:00:00+00:00", "v": stock_pages.FACTS_VERSION, "sales_usd": 20_000.0}
    return {**base, **kw}


# ---------- the SEC's public data, served as the SEC serves it ----------
COS = {
    "MFG": {"cik": 1335730, "accn": "0001193125-26-283791", "doc": "d119090d20f.htm", "inst": None},
    "ITUB": {"cik": 1132597, "accn": "0001132597-26-000132", "doc": "itub-20251231.htm", "inst": "itub-annual_htm.xml"},
    "TM": {"cik": 1094517, "accn": "0001193125-26-264811", "doc": "d101983d20f.htm", "inst": "tm-annual_htm.xml"},
    "BHP": {"cik": 811809, "accn": "0001193125-26-354647", "doc": "bhp-20260630.htm", "inst": "bhp-annual_htm.xml"},
}


def transport(symbol: str, calls: list | None = None, instance_down: bool = False):
    co = COS[symbol]
    folder = f"/Archives/edgar/data/{co['cik']}/{co['accn'].replace('-', '')}/"
    low = symbol.lower()

    def handler(r: httpx.Request):
        if calls is not None:
            calls.append(r.url.path)
        p = r.url.path
        if p == "/files/company_tickers.json":
            return httpx.Response(200, json={"0": {"cik_str": co["cik"], "ticker": symbol, "title": symbol}})
        if p == f"/submissions/CIK{co['cik']:010d}.json":
            return httpx.Response(200, json=fixture(f"{low}-submissions.json"))
        if p == f"/api/xbrl/companyfacts/CIK{co['cik']:010d}.json":
            return httpx.Response(200, json=fixture(f"{low}-companyfacts.json"))
        if p == folder + co["doc"]:
            return httpx.Response(200, text="<html><body><p>" + fixture(f"{low}-20f-cover.txt") + "</p></body></html>")
        if p == folder + re.sub(r"\.htm$", "_htm.xml", co["doc"]):
            if instance_down:
                return httpx.Response(503)
            return httpx.Response(200, text=fixture(co["inst"])) if co["inst"] else httpx.Response(404)
        return httpx.Response(404)
    return httpx.MockTransport(handler)


def company(symbol: str, rate: float | None = None, **kw) -> dict:
    p = sec.SEC(transport=transport(symbol, **kw)).company(symbol)
    return {**p, "fx": {"rate": rate}} if rate else p


# ---------- R8V-001: Mizuho, a ratio its own 20-F states wrongly, and a check on every foreign filer ----------
def test_mizuhos_20f_still_states_the_ratio_from_before_its_share_consolidation():
    # the cover page says two shares an ADS; since the 1-for-10 consolidation of October 2020 an ADS is 0.2 of a share
    # (8411.T closed at about ¥8,350, $52.8, against MFG's $10.67): read as two, the value was $13.3B and the P/E 1.8
    cover = fixture("mfg-20f-cover.txt")
    assert sec.ads_ratio(cover) == {"ratio": 2, "ads": True}
    assert sec.ADS_RATIO_KNOWN[1335730] == 0.2


def test_mizuhos_market_value_and_pe_count_five_adss_to_a_share():
    p = company("MFG", JPY)
    assert p["ads_ratio"] == 0.2 and p["foreign"] is True and p["currency"] == "JPY"
    assert "1/5 of one" in p["share_note"] and "still gives the earlier figure, 2" in p["share_note"]
    assert p["pl"]["cols"][-1] == "Mar 2026" and p["shares"] == 2_489_848_594
    r = sec.ratios(p, 10.67)
    assert 125_000 < r["Market Cap"] < 140_000                  # about $133B, not $13.3B
    pe, basis = sec.pe_and_basis(p, 10.67)
    assert basis == {"basis": "year", "end": "2026-03-31"} and 15 < pe < 21
    assert 7_000 < sec.basis_profit(p, "year") < 7_600         # ¥1,158,031m at ¥158.2


def test_a_foreign_filers_value_out_of_line_with_its_profit_is_na_with_the_note():
    # Mizuho as the page showed it: $13.3B on ¥1,158,031m of profit, P/E 1.8
    mfg = us(symbol="MFG", unit="JPY million", market_cap=13_284.0, pe=1.8, pe_basis="year", pe_end="2026-03-31",
             foreign=True, profit_usd=7_320.0, sales_usd=55_000.0)
    assert stock_pages.cap_problem(mfg) == "out of line with profit"
    assert stock_pages.shown_cap(mfg) is None and stock_pages.shown_pe(mfg) is None
    page = stock_pages.render(mfg, "US", "MFG", None)
    assert "<span>Market cap</span><b>n/a</b>" in page and "<span>P/E (year to Mar 2026)</span><b>n/a</b>" in page
    assert "data-cap-check" in page and "13.3B" not in page and ">1.8<" not in page
    # the corrected value passes: $132.8B, P/E 18.1
    assert stock_pages.cap_problem({**mfg, "market_cap": 132_840.0, "pe": 18.1}) is None
    # a P/E that disagrees with the value over the reported profit by more than two times, either way
    assert stock_pages.cap_problem({**mfg, "market_cap": 132_840.0, "pe": 40.0})
    assert stock_pages.cap_problem({**mfg, "market_cap": 132_840.0, "pe": 8.0})
    assert stock_pages.cap_problem({**mfg, "market_cap": 132_840.0, "pe": 30.0}) is None
    # a loss has no P/E to check; a value over a profit below three times it fails on its own
    assert stock_pages.cap_problem({**mfg, "market_cap": 132_840.0, "pe": None, "profit_usd": -500.0}) is None
    assert stock_pages.cap_problem({**mfg, "market_cap": 13_284.0, "pe": None})
    # a US company is not held to it (a P/E under 3 is rare but real there), and dollar reporters that file a 20-F are
    assert stock_pages.cap_problem({**mfg, "foreign": False, "unit": "$ million"}) is None
    assert stock_pages.cap_problem({**mfg, "unit": "$ million"}) == "out of line with profit"
    # a page stored before "foreign" was kept: one reporting in another currency is taken as foreign
    old = {k: v for k, v in mfg.items() if k not in ("foreign", "profit_usd")}
    assert stock_pages.cap_problem({**old, "v": 5}) == "out of line with profit"


def test_the_index_and_the_lists_by_size_leave_an_implausible_value_out(mem):
    mem["stocks:page:US:MFG"] = json.dumps({"ts": time.time(), "facts": us(symbol="MFG", unit="JPY million", market_cap=13_284.0, pe=1.8,
                                                                        pe_basis="year", pe_end="2026-03-31", foreign=True, profit_usd=7_320.0)})
    row = screens.row("US", "MFG", json.loads(mem["stocks:page:US:MFG"])["facts"])
    assert row["market_cap"] is None and row["pe"] is None


# ---------- R8V-002: Itaú, the latest 20-F and every class of shares ----------
def test_itaus_page_reads_its_2025_20f_and_counts_both_classes():
    calls: list = []
    p = sec.SEC(transport=transport("ITUB", calls)).company("ITUB")
    assert p["pl"]["cols"][-1] == "Dec 2025" and p["pl"]["rows"]["Net Profit"][-1] == 44_857.0
    # 5,617,742,977 common and 5,408,781,553 preferred shares outstanding at the end of 2025, as the cover page gives them
    assert p["shares"] == 11_026_524_530 and p["ads_ratio"] == 1 and p["foreign"] is True
    p = {**p, "fx": {"rate": BRL}}
    r = sec.ratios(p, 9.83)
    assert 100_000 < r["Market Cap"] < 115_000                 # about $108B, not $48.7B on one class
    pe, basis = sec.pe_and_basis(p, 9.83)
    assert basis == {"basis": "year", "end": "2025-12-31"} and 10 < pe < 14
    assert not p.get("annual_unread")


def test_itaus_page_without_the_new_report_counts_the_balance_sheets_shares_and_tries_again_soon():
    # the 20-F couldn't be read just now: the 2024 table stands, with both classes from the 2024 balance sheet
    # (9,776,104,515), never the 2023 cover page's one class (4,958,290,359), and the build is kept a quarter of an hour
    s = sec.SEC(transport=transport("ITUB", instance_down=True))
    p = s.company("ITUB")
    assert p["pl"]["cols"][-1] == "Dec 2024"
    assert p["shares"] == 9_776_104_515 and p["shares_from"] is None
    assert p["annual_unread"] == "2026-04-30"
    at, _ = s._built.get(str(COS["ITUB"]["cik"]))
    assert time.time() - at > 6 * 3600 - sec.UNREAD_RETRY - 5
    # the page says so in its facts, and is built again within the hour, not kept for the day
    f = us(symbol="ITUB", unit="BRL million", annual_unread="2026-04-30")
    now = time.time()
    assert stock_pages.fresh({"ts": now - 600, "price_ts": now, "facts": f}, "US", now=now)
    assert not stock_pages.fresh({"ts": now - stock_pages.UNREAD_FRESH - 1, "price_ts": now, "facts": f}, "US", now=now)


def test_a_cover_count_older_than_the_latest_year_gives_way_to_the_balance_sheets():
    facts = fixture("itub-companyfacts.json")
    p = sec.build(facts, fixture("itub-submissions.json"), symbol="ITUB")
    assert p["year_end"] == "2024-12-31" and p["shares"] == 9_776_104_515
    # a cover count from after the year's end stands
    q = sec.build(fixture("tm-companyfacts.json"), fixture("tm-submissions.json"), symbol="TM")
    assert q["shares_from"] == "cover"


# ---------- R8V-003: 20-F tables of March and June years from the filing itself, and P/E labels ----------
@pytest.mark.parametrize("symbol,last,end,rate", [("TM", "Mar 2026", "2026-03-31", JPY), ("BHP", "Jun 2026", "2026-06-30", 1.0)])
def test_a_march_or_june_years_20f_missing_from_the_company_facts_is_read_from_the_filing(symbol, last, end, rate):
    facts = fixture(f"{symbol.lower()}-companyfacts.json")
    assert not sec.has_filing(facts, COS[symbol]["accn"])
    before = sec.build(facts, fixture(f"{symbol.lower()}-submissions.json"), symbol=symbol)
    assert before["pl"]["cols"][-1] != last                    # the company facts alone stop a year earlier
    p = company(symbol, rate)
    assert p["pl"]["cols"][-1] == last and p["eps"]["basis"] == "year" and p["eps"]["end"] == end
    assert p["foreign"] is True and p["ads_ratio"] in (10, 2)
    pe, basis = sec.pe_and_basis(p, 186.0 if symbol == "TM" else 60.0)
    assert basis == {"basis": "year", "end": end} and pe and pe > 0
    f = us(symbol=symbol, pe=round(pe, 1), pe_basis=basis["basis"], pe_end=basis["end"])
    assert f"<span>P/E (year to {last})</span>" in stock_pages.render(f, "US", symbol, None)


def test_toyotas_profit_in_the_new_column_is_the_filings():
    p = company("TM", JPY)
    np_ = dict(zip(p["pl"]["cols"], p["pl"]["rows"]["Net Profit"]))
    assert np_["Mar 2026"] == 3_848_098.0 and np_["Mar 2025"] == 4_765_086.0
    assert 290 < p["eps"]["value"] < 300                       # ¥295.25 a share


def test_a_page_stored_before_pe_bases_were_kept_names_its_year_and_drops_a_stale_one():
    # Toyota's stored page: P/E 8.0, unlabelled, on the year to March 2025, 18 months before the close
    old = us(symbol="TM", unit="JPY million", pe=8.0, v=3, years=[{"year": "Mar 2025", "sales": 48_036_704.0, "profit": 4_765_086.0}])
    old.pop("sales_usd")
    assert stock_pages.pe_period(old) == ("year", "2025-03-31")
    assert stock_pages.pe_stale(old) and stock_pages.shown_pe(old) is None
    page = stock_pages.render(old, "US", "TM", None)
    assert "<span>P/E (year to Mar 2025)</span><b>n/a</b>" in page and "data-pe-old" in page
    # ASML's: a Dec 2025 year, shown and labelled
    asml = us(symbol="ASML", unit="EUR million", pe=63.9, v=3, years=[{"year": "Dec 2025", "sales": 32_000.0, "profit": 9_609.4}])
    assert "<span>P/E (year to Dec 2025)</span><b>63.9</b>" in stock_pages.render(asml, "US", "ASML", None)
    # a page with the last twelve months' profit is on those: plain "P/E"
    assert stock_pages.pe_label(us(v=3, profit_ttm=2_100.0)) == "P/E"
    # a page of today's version says its own basis, and is never second-guessed
    assert stock_pages.pe_label(us(pe_basis="ttm", pe_end="2026-06-30")) == "P/E"
    assert stock_pages.pe_label(us()) == "P/E"


def test_the_indexer_rebuilds_older_pages_largest_first_before_the_long_tail(monkeypatch):
    cos = {s: {"name": s, "sym": s, "bse": None} for s in ("TM", "ITUB", "WIT", "NEWCO", "ABCDF", "ZZZ", "INFY")}
    monkeypatch.setattr(stock_pages, "companies", lambda r: cos)
    monkeypatch.setattr(stock_pages, "_seeds", lambda r: set())
    monkeypatch.setattr(stock_pages, "_sp500_sectors", lambda: {})
    now = time.time()
    ages = {"TM": now - 3600, "ITUB": now - 7200, "WIT": now - 1800, "ZZZ": now - 30 * 3600, "INFY": now - 600}
    old = {"TM": 242_400.0, "ITUB": 48_700.0, "WIT": 26_000.0}
    due = [s for s, _ in screens.Indexer(warm_per_run=10)._due("US", ages, set(old), old)]
    # Toyota, Itaú and Wipro by size, then the companies with no page (a foreign over-the-counter line last), then the stalest
    assert due == ["TM", "ITUB", "WIT", "NEWCO", "ABCDF", "ZZZ"]


def test_the_index_notes_older_pages_with_their_value(mem, monkeypatch):
    monkeypatch.setattr(screens, "with_us_red", lambda rows: rows)
    mem["stocks:page:US:TM"] = json.dumps({"ts": 1, "facts": us(symbol="TM", v=3, market_cap=242_400.0)})
    mem["stocks:page:US:AAPL"] = json.dumps({"ts": 1, "facts": us(symbol="AAPL")})
    mem["stocks:page:US:SIAI"] = json.dumps({"ts": 1, "facts": None})
    index = screens.build_index("US", store=False)
    assert index["_old"] == {"TM": 242_400.0} and index["_empty"] == {"TM", "SIAI"}


# ---------- R8V-004: a foreign page from before depositary shares were checked: the page and the lists agree ----------
def test_a_foreign_page_stored_before_depositary_checks_shows_no_value_the_lists_leave_out():
    old = us(symbol="ASML", unit="EUR million", market_cap=682_100.0, pe=63.9, v=2)
    assert stock_pages.cap_problem(old) == "not checked for depositary shares"
    assert screens.row("US", "ASML", old)["market_cap"] is None
    built = {**old, "v": stock_pages.FACTS_VERSION, "foreign": True, "profit_usd": 11_150.0}
    assert stock_pages.cap_problem(built) is None and screens.row("US", "ASML", built)["market_cap"] == 682_100.0


# ---------- R8V-005: an Indian value counts the shares in issue, employee trusts' included ----------
def test_mms_value_counts_every_share_in_issue():
    # M&M, 8 Oct 2026: ₹3,44,849 Cr at ₹2,792 (123.5 crore shares); the consolidated balance sheet's ₹559 Cr of ₹5 shares
    # (111.8 crore) is net of the shares its employee trusts hold, which made ₹3.08 lakh crore at the same close
    assert screener.market_cap(344_849.0, 2_792.0, 559.0, 5.0) == 344_849.0
    page = {"ratios": {"Market Cap": "₹ 3,44,849 Cr.", "Current Price": "₹ 2,792", "Face Value": "₹ 5.00"},
            "balance": {"cols": ["Mar 2025", "Mar 2026"], "rows": {"Equity Capital": [558.0, 559.0]}}}
    assert screener.summary(page)["market_cap_cr"] == 344_849.0
    # TCS's lagging count still gives way to its share capital (R5O-011), and so does a count the source hasn't caught up with
    assert screener.market_cap(770_345.0, 2_080.30, 362.0, 1.0) == round(2_080.30 * 362, 2)
    assert screener.market_cap(100_000.0, 100.0, 1_100.0, 1.0) == 110_000.0


def test_a_stored_us_page_from_before_the_yield_definition_takes_the_dividends_lists(mem):
    # P&G's page kept 2.93%, the filings' dividends paid over its value, against 2.85% by ex-date (R8V-011)
    rows = [{"id": f"PG|dividend|{d}|dividend", "region": "US", "symbol": "PG", "kind": "dividend", "amount": a, "ex_date": d}
            for d, a in (("2025-07-18", 1.0568), ("2025-10-24", 1.0568), ("2026-01-23", 1.0568), ("2026-04-24", 1.0885),
                         ("2026-07-24", 1.0885))]
    corp_actions.hist_save("US", "PG", rows)
    f = us(symbol="PG", price=150.59, div_yield=2.93, v=3)
    got = main.stock_page_older_facts("US", "PG", f)
    assert got["div_yield"] == round((1.0568 * 2 + 1.0885 * 2) / 150.59 * 100, 2) == 2.85
    # a company whose list was read and holds none: a real 0%; no list at all: n/a, never the other definition's figure
    corp_actions.hist_save("US", "NODIV", [])
    assert main.stock_page_older_facts("US", "NODIV", us(symbol="NODIV", div_yield=1.4, v=3))["div_yield"] == 0.0
    assert main.stock_page_older_facts("US", "NEVER", us(symbol="NEVER", div_yield=1.4, v=3))["div_yield"] is None
    # a page of today's version is served as it is
    assert main.stock_page_older_facts("US", "PG", us(symbol="PG", div_yield=2.85))["div_yield"] == 2.85


def test_pages_say_which_facts_version_built_them():
    f = stock_pages.facts("US", "ACME", {"name": "Acme"}, {"years": []}, {}, None, None, [], "Listed in the US",
                          checks={"foreign": True, "profit_usd": 7_320.0, "annual_unread": "2026-04-30"})
    assert f["v"] == stock_pages.FACTS_VERSION == 6
    assert f["foreign"] is True and f["profit_usd"] == 7_320.0 and f["annual_unread"] == "2026-04-30"


# ---------- R8V-007: the sitemap lists built pages only ----------
def test_the_sitemap_lists_only_pages_built_with_something_to_show(mem, monkeypatch):
    cos = {s: {"name": s, "sym": s, "bse": None} for s in ("AAPL", "MDXR", "TEAM", "STRS")}
    real = stock_pages.companies
    monkeypatch.setattr(stock_pages, "companies", lambda r: cos if r == "US" else real(r))
    # MDXR built as a fund (marked as nothing to show); TEAM and STRS not built yet
    mem[stock_pages.BUILT_KEY + "US"] = json.dumps({"at": "2026-10-09", "pages": ["AAPL", "MDXR"], "shown": ["AAPL"]})
    mem["stocks:thin:US:MDXR"] = "1"
    listed = set(re.findall(r"/stocks/us/([A-Z.-]+)</loc>", stock_pages.sitemap("stocks-us-1")))
    assert listed == {"AAPL"}


def test_a_fund_built_since_the_last_gathering_leaves_the_sitemap(mem, monkeypatch):
    cos = {s: {"name": s, "sym": s, "bse": None} for s in ("AAPL", "MDXR")}
    real = stock_pages.companies
    monkeypatch.setattr(stock_pages, "companies", lambda r: cos if r == "US" else real(r))
    mem[stock_pages.BUILT_KEY + "US"] = json.dumps({"at": "2026-10-09", "pages": ["AAPL", "MDXR"], "shown": ["AAPL", "MDXR"]})
    pages = stock_pages.Pages(lambda r, co: us(symbol="MDXR", not_company="a fund"))
    pages.get("US", "MDXR", cos["MDXR"])
    assert "MDXR" not in stock_pages.sitemap("stocks-us-1")


# ---------- R8V-009: surveillance badges in the page's theme colours ----------
def test_surveillance_badges_use_the_theme_tokens():
    html = stock_pages.surveillance_html([{"short": "ESM", "label": "Enhanced surveillance", "text": "Trade for trade.", "as_of": "2026-10-08"}])
    assert "#92400e" not in html and "#b45309" not in html
    assert "color:var(--orange-ink)" in html and "background:var(--orange-soft)" in html
    assert "--orange-ink:#F2A877" in stock_pages.STYLE and "--orange-soft:#3A2416" in stock_pages.STYLE    # the dark theme's


# ---------- R8V-010: the EBITDA margin of the table's latest year ----------
def test_the_ebitda_margin_is_the_latest_years_in_the_table():
    # Kinetic Seas: the last twelve months' 43.7% above a table whose latest year says −1,634.4%
    nums = {"years": [{"year": "Dec 2024", "sales": 0.21, "profit": -3.9, "opm": -1775.0}, {"year": "Dec 2025", "sales": 0.07, "profit": -1.24, "opm": -1634.4}]}
    f = stock_pages.facts("US", "KSEZ", {"name": "Kinetic Seas Inc."}, nums, {"opm": 43.7, "net_margin": -1771.4}, None, None, [], "Listed in the US")
    assert f["opm"] == -1634.4
    page = stock_pages.render(f, "US", "KSEZ", None)
    assert "43.7%" not in page and "data-extreme" in page
    assert stock_pages.facts("US", "NEW", {"name": "New"}, {"years": []}, {"opm": 12.0}, None, None, [], "Listed in the US")["opm"] == 12.0


# ---------- R8V-012: a large company's industry peers are of its kind ----------
def _row(s, ind, cap, sector="Manufacturing"):
    return {"symbol": s, "name": s, "industry": ind, "sector": sector, "market_cap": cap, "cap_checked": True, "price_at": "2026-10-08"}


def test_a_large_companys_industry_leaves_out_small_filers_and_other_sectors(monkeypatch):
    rows = [_row("AAPL", "Electronic Computers", 4_970_000.0), _row("DELL", "Electronic Computers", 90_000.0),
            _row("HPQ", "Electronic Computers", 25_000.0), _row("OMCL", "Electronic Computers", 1_500.0),
            _row("ZEPP", "Electronic Computers", 300.0), _row("SCKT", "Electronic Computers", 10.0),
            _row("SMCI", "Electronic Computers", 60_000.0), _row("NVDA", "Semiconductors", 5_550_000.0),
            _row("MSFT", "Software", 3_880_000.0),
            _row("V", "Services-Business Services, Nec", 700_500.0, "Services"), _row("PYPL", "Services-Business Services, Nec", 70_000.0, "Services"),
            _row("UBER", "Services-Business Services, Nec", 180_000.0, "Services"), _row("ACN", "Services-Business Services, Nec", 160_000.0, "Services"),
            _row("DASH", "Services-Business Services, Nec", 100_000.0, "Services"), _row("EBAY", "Services-Business Services, Nec", 40_000.0, "Services"),
            _row("TINY", "Services-Business Services, Nec", 300.0, "Services"), _row("MA", "Services-Business Services, Nec", 520_000.0, "Services")]
    cos = {r["symbol"]: {"name": r["symbol"], "sym": r["symbol"], "bse": None} for r in rows}
    monkeypatch.setattr(stock_pages, "companies", lambda r: cos)
    monkeypatch.setattr(stock_pages, "_index_rows", lambda r: rows)
    sp = {"AAPL": "Information Technology", "DELL": "Information Technology", "HPQ": "Information Technology", "SMCI": "Information Technology",
          "NVDA": "Information Technology", "MSFT": "Information Technology", "V": "Financials", "PYPL": "Financials", "MA": "Financials",
          "UBER": "Industrials", "ACN": "Information Technology", "DASH": "Consumer Discretionary", "EBAY": "Consumer Discretionary"}
    monkeypatch.setattr(stock_pages, "_sp500_sectors", lambda: sp)
    aapl = {s["title"]: [x[0] for x in s["rows"]] for s in stock_pages.peer_sections("US", "AAPL", ["Manufacturing", "Electronic Computers"], 4_970_000.0)}
    assert aapl["Same industry"] == ["DELL", "SMCI", "HPQ"]            # no Omnicell, Zepp or Socket Mobile
    assert aapl["Same sector"][:2] == ["NVDA", "MSFT"]
    v = {s["title"]: [x[0] for x in s["rows"]] for s in stock_pages.peer_sections("US", "V", ["Services", "Services-Business Services, Nec"], 700_500.0)}
    assert v["Same industry"] == ["MA", "PYPL"]                         # no Uber, Accenture, DoorDash or eBay
    # a small company keeps every company of its industry
    small = stock_pages.peer_sections("US", "TINY", ["Services", "Services-Business Services, Nec"], 300.0)
    assert "UBER" in [x[0] for x in small[0]["rows"]]
