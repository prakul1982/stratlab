"""R10C: the accuracy of company figures. Each test failed before its fix."""
import gzip
import json
import re

import httpx

from app import checklist, deck, deepdive, main, report_card, screens, stock_pages as sp
from app.intel import ai as A
from app.intel import key_facts, routes, sec
from app.intel.company import _series
from app.intel.grounding import page_value
from app.intel.net import num
from app.intel.screener import Screener, summary
from tests import fake_intel
from tests.test_audit import base_for
from tests.test_deepdive import company
from tests.test_research_api import api  # noqa: F401  (the fixture)


# ---------- 1. the India Research page, deep dive, deck, valuation and AI facts check the market value ----------
def _bad_cap_screener():
    html = fake_intel.SCREENER_HTML.replace("19,05,432", "1,11,30,000")     # ₹1.1 crore crore: no company's value

    def handler(req):
        return httpx.Response(200, text=html) if "/company/RELIANCE/" in req.url.path else httpx.Response(404, text="x")
    return Screener(transport=httpx.MockTransport(handler))


def test_india_research_page_blanks_a_cap_the_public_page_fails(api):  # noqa: F811
    routes.hub.screener = _bad_cap_screener()
    r = api.get("/research/company/IN/RELIANCE").json()
    assert r["market_cap"] is None and r["summary"]["market_cap_cr"] is None
    assert {"label": "Market cap", "value": "Unavailable"} in r["facts"]
    assert r["cap_note"].startswith("Market cap unavailable")
    assert not any(i["label"] == "P/E" for g in r["metrics"] for i in g["items"])      # as the public page's shown_pe
    assert A.company_facts(r)["market_cap"] == "Market cap unavailable"


def test_india_research_page_keeps_a_cap_that_passes(api):  # noqa: F811
    r = api.get("/research/company/IN/RELIANCE").json()
    assert r["market_cap"] and r.get("cap_note") is None


def test_deep_view_deck_and_valuation_blank_a_failed_cap(monkeypatch):
    p = company()
    p["ratios"] = {"Market Cap": "100000000", "Stock P/E": "20", "Current Price": "100"}   # 10 lakh crore crore of shares
    monkeypatch.setattr(deepdive, "stored", lambda s: None)
    monkeypatch.setattr(report_card, "stored", lambda s: None)
    monkeypatch.setattr(main, "page_dividend_yield", lambda *a, **k: None)
    view = main.deep_view("ACME", base_for(p, {"price": 100.0})("ACME"))
    snap = view["snapshot"]
    assert snap["market_cap_cr"] is None and snap["pe"] is None and snap["cap_note"].startswith("Market cap unavailable")
    assert view["valuation"]["pe"] is None                          # no P/E worked out from the market value either
    slides, _ = deck.plan(view)
    tiles = dict(next(b for b in slides[0].blocks if b["kind"] == "stats")["items"])
    assert tiles["Market cap"] == "Unavailable"


def test_india_snap_check_matches_the_public_page():
    p = company()
    good = {"market_cap_cr": 520.0, "price": 10000.0, "pe": 20.0}
    assert sp.india_snap_checked(good, p) is good
    bad = sp.india_snap_checked({**good, "market_cap_cr": 520 * 1000.0}, p)          # 2,476 times the latest revenue
    assert bad["market_cap_cr"] is None and bad["pe"] is None and bad["cap_problem"] == "out of line with revenue"


# ---------- stored India index rows are checked when read ----------
def test_stale_india_index_row_never_ranks(monkeypatch):
    rows = [{"symbol": "OLD", "market_cap": 9_000_000.0, "price": 1.0},             # 90 lakh crore shares: a stale row
            {"symbol": "TCS", "market_cap": 1_100_000.0, "price": 3000.0}]
    monkeypatch.setattr(sp, "_index_rows", lambda region: rows)
    monkeypatch.setattr(sp, "companies", lambda region: {"OLD": {"name": "Old"}, "TCS": {"name": "TCS"}})
    assert [r["symbol"] for r in sp._sized("IN")] == ["TCS"]


# ---------- 2. screens rank only on figures the public page shows ----------
def test_screen_row_drops_old_and_extreme_figures():
    f = {"region": "US", "symbol": "XYZ", "name": "Xyz", "price": 50, "price_at": "2026-10-14", "currency": "USD",
         "unit": "$ million", "v": 99, "market_cap": 5000, "high52": 60, "low52": 30, "pe": 20, "roe": 80, "roce": 30,
         "net_margin": 4500.0, "opm": -3000.0, "debt_equity": 0.5,
         "years": [{"year": "Dec 2024", "sales": 1, "profit": 45, "opm": -3000}], "profit_ttm": 3, "growth": {}}
    r = screens.row("US", "XYZ", f)
    assert [r[k] for k in ("net_margin", "opm", "roe", "roce", "debt_equity")] == [None] * 5
    fresh = {**f, "years": [{"year": "Dec 2025", "sales": 100, "profit": 45, "opm": -300}], "net_margin": 45.0, "opm": -300.0}
    r = screens.row("US", "XYZ", fresh)
    assert r["net_margin"] is None and r["opm"] is None and r["roe"] == 80 and r["debt_equity"] == 0.5     # extreme: margins only


# ---------- 3. a quarter against the same quarter a year before ----------
def test_quarter_vs_a_year_ago_matches_by_period():
    cols = ["Mar 2025", "Jun 2025", "Dec 2025", "Mar 2026", "Jun 2026"]     # Sep 2025 missing
    p = {"region": "US", "pl": {"cols": ["Dec 2025"], "rows": {"Sales": [100]}},
         "quarters": {"cols": cols, "rows": {"Sales": [100, 110, 130, 120, 500], "Net Profit": [1] * 5, "OPM %": [1] * 5}}}
    q = {x["quarter"]: x["sales_yoy"] for x in deepdive.numbers(p)["quarters"]}
    assert q["Jun 2026"] == round((500 / 110 - 1) * 100, 1) and q["Mar 2026"] == 20.0 and q["Dec 2025"] is None


# ---------- 4. a part-year first report is no growth base ----------
def test_part_year_column_is_no_growth_base():
    cols = ["Mar 2023 3m", "Mar 2024", "Mar 2025", "Mar 2026"]
    p = {"ratios": {"Current Price": "100", "Market Cap": "1000"},
         "pl": {"cols": cols, "rows": {"Sales": [25, 100, 120, 150], "Net Profit": [2, 10, 12, 15], "OPM %": [40, 10, 11, 12]}},
         "balance": {"cols": cols, "rows": {}}}
    n = deepdive.numbers(p)
    assert n["growth"]["sales_cagr_3y"] is None and n["growth"]["profit_cagr_3y"] is None
    c = checklist.evaluate(p, n)
    margin = next(x for x in c["checks"] if x["label"] == "EBITDA margin holding up")
    assert margin["state"] == "na"                       # never the part year's 40% as "three years ago"
    p["pl"] = {"cols": ["Mar 2025 3m", "Mar 2026"], "rows": {"Sales": [25, 150], "Net Profit": [2, 15]}}
    s = summary(p)
    assert s["sales_yoy"] is None and s["profit_yoy"] is None


# ---------- 5. key facts never compound over the profit trend's gaps ----------
def test_key_facts_profit_growth_keeps_blank_years():
    cols = ["Mar 2020", "Mar 2021", "Mar 2022", "Mar 2023", "Mar 2024", "Mar 2025"]
    profit = [50, 60, 70, 80, None, None]
    p = {"pl": {"cols": cols, "rows": {"Sales": [100, 110, 120, 130, 140, 150], "Net Profit": profit}}}
    n = deepdive.numbers(p)
    g = key_facts.growth({"trend": {"profit": _series(cols, profit)}, "metrics": []}, n)
    assert not any(i["label"].startswith("Net profit") for i in g["items"])


# ---------- 6. US earnings per share across a split ----------
def test_eps_older_than_a_split_is_restated():
    true = {y: round(2.0 * 1.1 ** (y - 2019), 2) for y in range(2019, 2025)}
    rows = []
    for fy in range(2019, 2025):
        filed, pre = f"{fy + 1}-02-15", fy + 1 <= 2022           # a 4:1 split in mid-2022
        for y in (fy - 2, fy - 1, fy):
            if y in true:
                rows.append({"start": f"{y}-01-01", "end": f"{y}-12-31", "val": round(true[y] * (4 if pre else 1), 2),
                             "form": "10-K", "filed": filed, "accn": f"a{y}{filed}"})
    eps = sec.flows({"us-gaap": {"EarningsPerShareBasic": {"units": {"USD/shares": rows}}}}, ("EarningsPerShareBasic",),
                    "annual", "USD/shares")
    vals = [v for _, v in sorted(eps.items())]
    assert vals[0] == 2.0 and round(deepdive._cagr(vals, 5), 1) == 10.0


# ---------- 7. the public page writes ₹ crore in Indian grouping ----------
def test_public_page_crore_in_indian_grouping():
    f = {"region": "IN", "currency": "INR", "unit": "₹ crore", "profit_ttm": 4945400.0,
         "years": [{"year": "Mar 2026", "sales": 267021, "profit": 49454, "opm": 24, "debt": 9000},
                   {"year": "Mar 2025", "sales": 2570.4, "profit": -0.3, "opm": 24, "debt": None}]}
    table = re.sub(r"<[^>]+>", " ", sp._table(f))
    assert "2,67,021" in table and "267,021" not in table and "-0.30" in table
    stats = dict(sp._stats(f))
    assert stats["Net profit, last 12 months (₹ crore)"] == "49,45,400"
    us = {**f, "region": "US", "currency": "USD", "unit": "$ million"}
    assert "267,021" in sp._table(us)


# ---------- section 2 ----------
def test_grounding_crore_as_the_page_writes_it():
    assert page_value(310000, "cr") == "₹3.1 lakh cr"
    assert page_value(3472.4, "cr") == "₹3,472 cr"


def test_deck_never_prints_minus_zero():
    assert deck._cr(-0.3) == "0" and deck._cr(-1234567) == "-12,34,567"
    assert deck._plain(-0.3, 1, 0) == "0" and deck._plain(-1.6, 1, 0) == "-2" and deck._plain(None, 1, 0) == "–"


def test_ayr_share_count_blanks_cap_and_yield():
    d = json.load(gzip.open("tests/fixtures/sec_live/ayr.json.gz"))
    p = sec.build(d["facts"], d["subs"], symbol="AYR")
    r = sec.ratios(p, 100.0)
    assert r["Dividend Yield"] > 1000                               # 17,840 shares: the ratio itself is off
    f = {"region": "US", "currency": "USD", "unit": "$ million", "price": 100.0, "market_cap": r["Market Cap"],
         "pe": r["Stock P/E"], "div_yield": r["Dividend Yield"], "profit_ttm": p["pl"]["rows"]["Net Profit"][-1],
         "sales_usd": p["pl"]["rows"]["Sales"][-2]}
    assert sp.shown_yield(f) is None and sp.shown_cap(f) is None and sp.shown_pe(f) is None
    assert screens.row("US", "AYR", {**f, "name": "AYR"})["div_yield"] is None
    assert sp.shown_yield({"region": "IN", "div_yield": 75.0}) is None and sp.shown_yield({"region": "IN", "div_yield": 3.1}) == 3.1


def test_checklist_profit_growth_wording_says_a_loss_is_na():
    p = company()
    p["pl"]["rows"]["Net Profit"] = [10, 12, -5, 18, 20, 25, 26]     # a loss three years back
    n = deepdive.numbers(p)
    row = next(x for x in checklist.evaluate(p, n)["checks"] if x["label"] == "Profit growth, 3 years")
    assert row["state"] == "na" and "loss" in row["rule"]


def test_num_reads_accounting_and_dash_signs():
    assert num("(12.5)") == -12.5 and num("(1,234)") == -1234.0
    assert num("–5") == -5.0 and num("—5") == -5.0 and num("−5") == -5.0
    assert num("nan") is None and num("inf") is None and num("-inf") is None and num(float("inf")) is None
    assert num("—") is None and num("--") is None and num("12.5%") == 12.5


def _us_page(api, monkeypatch, **patch):  # noqa: F811
    for k, v in patch.items():
        monkeypatch.setattr(fake_intel, k, v)
    from app.intel.finnhub import Finnhub
    routes.hub.finnhub = Finnhub(transport=fake_intel.fake_finnhub())
    return api.get("/research/company/US/NVDA").json()


def test_us_eps_surprise_on_a_zero_estimate_has_no_percentage(api, monkeypatch):  # noqa: F811
    earn = [dict(e) for e in fake_intel.EARN]
    earn[0].update(estimate=0.0, surprisePercent=0.0)
    r = _us_page(api, monkeypatch, EARN=earn)
    by = {e["period"]: e["surprise_pct"] for e in r["earnings"]}
    assert by["2025-07-31"] is None and by["2025-04-30"] == 3.2


def test_us_lender_metrics_leave_out_what_describes_no_bank(api, monkeypatch):  # noqa: F811
    metric = {"metric": {**fake_intel.METRIC["metric"], "currentEv/freeCashFlowTTM": 31.2, "assetTurnoverTTM": 0.05}}
    some = {"EV/EBITDA", "EV/FCF", "Gross margin", "Current ratio", "Asset turnover"}
    r = _us_page(api, monkeypatch, METRIC=metric)
    assert some <= {i["label"] for g in r["metrics"] for i in g["items"]}            # a company that isn't a lender
    r = _us_page(api, monkeypatch, METRIC=metric, PROFILE={**fake_intel.PROFILE, "finnhubIndustry": "Banking"})
    assert not some & {i["label"] for g in r["metrics"] for i in g["items"]}
    assert r["margins"]["gross"] is None
