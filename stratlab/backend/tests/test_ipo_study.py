"""The IPO study (ipo_study.py) on synthetic rows: each issue's arithmetic, the aggregates, the markdown, and drafts whose every figure
comes from the study's JSON."""
import json
import re
from datetime import date

from app import ipo_study as St
from tests.test_ipo import ADVICE, PROVIDERS

TODAY = date(2026, 10, 25)
SUB_A = {"times": 61.43, "rows": [{"label": "Qualified institutional buyers", "sr": "1", "offered": 1000000, "bid": 80000000, "times": 80.0},
                                  {"label": "Non-institutional investors", "sr": "2", "offered": 750000, "bid": 30000000, "times": 40.0},
                                  {"label": "Retail individual investors", "sr": "3", "offered": 1750000, "bid": 105000000, "times": 60.0},
                                  {"label": "Total", "sr": "total", "offered": 3500000, "bid": 215000000, "times": 61.43}]}
SUB_B = {"times": 2.5, "rows": [{"label": "Retail individual investors", "sr": "3", "offered": 400000, "bid": 1200000, "times": 3.0, "apps": 20000},
                                {"label": "Total", "sr": "total", "offered": 1000000, "bid": 2500000, "times": 2.5}]}
ROWS = [
    {"id": "in-alpha", "market": "IN", "segment": "mainboard", "name": "Alpha Limited", "symbol": "ALPHA", "listing": "2025-03-10", "price": 100.0,
     "industry": "Capital Goods", "fresh_cr": 300.0, "ofs_cr": 200.0, "sub": SUB_A,
     "perf": {"issue_price": 100.0, "listing_change_pct": 15.0, "day_change_pct": 21.0, "latest": 91.0, "change_pct": -9.0}},
    {"id": "in-beta", "market": "IN", "segment": "mainboard", "name": "Beta Limited", "symbol": "BETA", "listing": "2026-01-15", "price": 200.0,
     "industry": "Financial Services", "fresh": 1000000, "issue_text": "Fresh issue of 10,00,000 equity shares", "lot": 20, "sub": SUB_B},
    {"id": "in-bse-543210", "market": "IN", "segment": "sme", "name": "Gamma Foods Ltd", "symbol": None, "listing": "2026-05-05", "price": 50.0,
     "bse_perf": {"issue_price": 50.0, "day_close": 55.0, "latest": 40.0}},
    {"id": "in-gone", "market": "IN", "segment": "mainboard", "name": "Gone Limited", "symbol": "GONE", "listing": "2025-06-17", "price": 80.0, "issue_status": "withdrawn"},
]
CLOSES = {"ALPHA": {"2025-03-10": 121.0, "2026-10-23": 91.0}, "BETA": {"2026-01-14": 170.0, "2026-01-15": 180.0, "2026-10-23": 250.0}}
BENCH = {"nifty50": {"2025-03-07": 1000.0, "2025-03-10": 1010.0, "2026-01-14": 1050.0, "2026-10-23": 1100.0},
         "smallcap250": {"2025-03-07": 500.0, "2026-01-14": 600.0, "2026-10-23": 450.0}}


OPENS = {"BETA": {"2026-01-15": 210.0}}


def res():
    return St.study(ROWS, lambda r: (CLOSES.get(r.get("symbol") or "") or {}, OPENS.get(r.get("symbol") or "")), BENCH, TODAY, ("2024-10-25", "2026-10-25"))


def test_each_issue_against_its_issue_price_and_the_index_over_the_same_days():
    got = {i["id"]: i for i in res()["issues"]}
    assert set(got) == {"in-alpha", "in-beta", "in-bse-543210"}                    # an issue that did not go ahead is not counted
    a = got["in-alpha"]
    assert (a["listing_open_pct"], a["listing_close_pct"], a["return_pct"], a["last_day"], a["below_issue"]) == (15.0, 21.0, -9.0, "2026-10-23", True)
    assert a["nifty50_pct"] == 10.0 and a["vs_nifty50_pct"] == -19.0               # from the close before the listing day (7 Mar) to 23 Oct
    assert a["smallcap250_pct"] == -10.0 and a["vs_smallcap250_pct"] == 1.0
    assert a["retail_times"] == 60.0 and a["retail_fill_pct"] == 1.67 and a["retail_odds_pct"] is None
    assert (a["size_cr"], a["fresh_cr"], a["ofs_cr"], a["sector"]) == (500.0, 300.0, 200.0, "Capital Goods")
    b = got["in-beta"]
    assert b["listing_close_pct"] == -10.0 and b["listing_open_pct"] == 5.0         # the first session's close and open from the daily prices
    assert b["return_pct"] == 25.0 and b["nifty50_pct"] == 4.76 and b["vs_nifty50_pct"] == 20.24
    assert (b["size_cr"], b["fresh_cr"], b["ofs_cr"]) == (20.0, 20.0, 0.0)          # a fresh issue only: no offer for sale
    assert b["retail_fill_pct"] == 33.33 and b["retail_odds_pct"] == 100.0          # 20,000 lots for 20,000 applications
    c = got["in-bse-543210"]
    assert (c["listing_close_pct"], c["return_pct"], c["below_issue"], c["vs_nifty50_pct"]) == (10.0, -20.0, True, None)


def test_a_split_since_listing_is_counted_back_in_from_the_exchanges_listing_day_close():
    row = {"id": "in-cordelia", "market": "IN", "segment": "mainboard", "name": "Waterways", "symbol": "CORDELIA", "listing": "2026-07-01", "price": 808.0,
           "bse_perf": {"issue_price": 808.0, "day_close": 667.35, "latest": 89.95}}
    got = St.issue_figures(row, {"2026-07-01": 66.81, "2026-11-06": 88.29}, {}, date(2026, 11, 7), {"2026-07-01": 68.1})
    assert got["split_factor"] == 10.0 and got["listing_close_pct"] == -17.41 and got["listing_open_pct"] == -15.72
    assert got["last_close"] == 882.9 and got["return_pct"] == 9.27 and not got["check_split"]
    assert St.split_factor(100.0, 98.0) == 1.0 and St.split_factor(300.0, 100.5) == 3.0 and St.split_factor(150.0, 100.0) == 1.5
    # no exchange close to check against and a price a fifth of the issue price: flagged, and never named as the worst issue
    odd = St.issue_figures({**row, "id": "in-odd", "bse_perf": None}, {"2026-07-01": 66.81, "2026-11-06": 88.29}, {}, date(2026, 11, 7))
    assert odd["check_split"] and St.segment_block([odd, got], "mainboard")["worst"]["id"] == "in-cordelia"


def test_aggregates_by_segment_retail_subscription_and_money_raised():
    r = res()
    assert r["coverage"]["issues"] == 3 and r["coverage"]["mainboard"] == 2 and r["coverage"]["sme"] == 1
    m = r["segments"]["mainboard"]["all"]
    assert m["issues"] == 2 and m["median_listing_close_pct"] == 5.5 and m["closed_above_issue_pct"] == 50.0
    assert m["below_issue_now"] == 1 and m["below_issue_now_pct"] == 50.0 and m["median_return_pct"] == 8.0
    assert m["raised_cr"] == 520.0 and m["fresh_cr"] == 320.0 and m["ofs_cr"] == 200.0 and m["fresh_share_pct"] == 61.5
    assert m["median_vs_nifty50_pct"] == 0.62 and m["beat_nifty50_pct"] == 50.0
    retail = {g["label"]: g for g in r["segments"]["mainboard"]["by_retail"]}
    assert set(retail) == {"Retail over 50 times", "Retail under 5 times"}
    assert retail["Retail over 50 times"]["median_return_pct"] == -9.0 and retail["Retail under 5 times"]["median_return_pct"] == 25.0
    assert [g["label"] for g in r["segments"]["mainboard"]["by_year"]] == ["2025", "2026"]
    assert [g["label"] for g in r["segments"]["mainboard"]["by_size"]] == ["Under ₹100 cr", "₹500 to 1,000 cr"]
    assert r["segments"]["sme"]["all"]["below_issue_now_pct"] == 100.0
    assert r["segments"]["mainboard"]["best"]["id"] == "in-beta" and r["segments"]["mainboard"]["worst"]["return_pct"] == -9.0


def test_the_markdown_has_a_table_per_grouping():
    md = St.markdown(res())
    for title in ("## Main board", "## SME", "**Main board by year**", "**Main board by size**", "**Main board by retail subscription**", "**Main board by sector**"):
        assert title in md
    assert "| Retail over 50 times | 1 | +21.0% |" in md


def test_drafts_use_only_the_studys_figures_and_give_no_advice():
    r = res()
    out = St.drafts(r)
    assert set(out) == {"research-note.md", "x-article.md", "linkedin-post.md"}
    for name, text in out.items():
        body, sources = text.split("Figures used (paths in ipo-study.json):")
        assert body.startswith("> DRAFT") and "https://stratlab.studio/invest/ipos" in body and "StratLab" in body
        assert not ADVICE.search(body) and not PROVIDERS.search(body), name
        # every percentage, multiple and rupee figure in the text is one of the figures listed, formatted
        allowed = set()
        for path in re.findall(r"^- `([^`]+)`", sources, re.MULTILINE):
            v = St.Figures(r)(path)
            allowed |= {St.fmt_pct(v), St.fmt_pct(v, False), St.fmt_x(v), St.fmt_cr(v), str(v)}
        for fig in re.findall(r"[+-]?\d[\d,]*(?:\.\d+)?%|\d[\d,]*(?:\.\d+)?x\b|₹[\d,]+ cr", body):
            assert fig in allowed, (name, fig)
    words = len(re.sub(r"\n---\n.*", "", out["linkedin-post.md"], flags=re.DOTALL).split())
    assert words < 300


def test_run_writes_the_json_the_markdown_the_drafts_and_the_charts(tmp_path):
    rows = tmp_path / "rows.json"
    rows.write_text(json.dumps({"rows": ROWS}))
    St.main(["--out", str(tmp_path / "out"), "--rows", str(rows), "--today", "2026-10-25", "--no-prices", "--drafts", "--charts"])
    out = tmp_path / "out"
    got = json.loads((out / "ipo-study.json").read_text())
    assert got["coverage"]["issues"] == 3 and (out / "ipo-study.md").exists() and (out / "research-note.md").exists()
    assert (out / "chart-specs.json").exists() or (out / "chart-1-retail-subscription.png").exists()
    specs = St.chart_specs(got)
    assert [s["file"] for s in specs] == ["chart-1-retail-subscription.png", "chart-2-below-issue.png"]
    assert specs[1]["series"][0]["values"] == [100.0, 100.0]          # with no daily closes, Beta has no latest close to count
