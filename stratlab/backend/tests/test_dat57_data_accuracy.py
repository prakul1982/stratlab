"""Lane dat57: data accuracy of the US figures against the SEC's company facts (the R56 decks' audit).

1. A card issuer that tags its ASC 606 fee revenue under a top-line concept and its whole revenue only as revenue net of
   interest expense (American Express: $41.3 bn of contract revenue beside $72.2 bn in total for 2025) showed the part as
   its revenue, so its revenue, growth and net margin were all wrong.
2. A stock split after the latest annual report: the cover page's new count was replaced by the old count the annual
   earnings per share imply, so the market value was off by the split's ratio (CrowdStrike's 4:1 split: $56.7 bn against
   $232 bn; SkinHealth's 1:20 reverse split: $1.94 bn against $107 m)."""
import pytest

from app import main  # noqa: F401, I001  (first: the app loads the newsletter job before the modules built on it)
from app.intel import sec


def _fy(end: str, start: str, v: float, filed: str) -> dict:
    return {"start": start, "end": end, "val": v, "form": "10-K", "filed": filed, "fp": "FY"}


# ---------- 1. revenue net of interest expense beside a part tagged as contract revenue ----------
def _issuer_facts() -> dict:
    rows = lambda a, b: [_fy("2024-12-31", "2024-01-01", a, "2025-02-07"), _fy("2025-12-31", "2025-01-01", b, "2026-02-06")]   # noqa: E731
    return {"us-gaap": {"RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"USD": rows(38_800e6, 41_304e6)}},
                        "RevenuesNetOfInterestExpense": {"units": {"USD": rows(65_949e6, 72_229e6)}},
                        "NetIncomeLoss": {"units": {"USD": rows(10_129e6, 10_833e6)}}}}


def test_a_card_issuers_revenue_is_its_whole_revenue_net_of_interest_not_its_fee_part():
    rev = sec.revenue(_issuer_facts(), "annual")
    assert rev["2025-12-31"] == pytest.approx(72_229e6) and rev["2024-12-31"] == pytest.approx(65_949e6)
    p = sec.build({"facts": _issuer_facts()})
    sales, profit = p["pl"]["rows"]["Sales"], p["pl"]["rows"]["Net Profit"]
    assert sales[-1] == pytest.approx(72_229, abs=1) and profit[-1] / sales[-1] == pytest.approx(0.150, abs=0.001)


def test_a_gross_top_line_above_revenue_net_of_interest_is_kept():
    # a bank that tags its gross revenue (interest income plus fees) as Revenues keeps it: the larger figure is the top line,
    # as before; revenue net of interest only lifts a top line that is a part of it
    f = _issuer_facts()
    f["us-gaap"]["Revenues"] = {"units": {"USD": [_fy("2025-12-31", "2025-01-01", 90_000e6, "2026-02-06")]}}
    assert sec.revenue(f, "annual")["2025-12-31"] == pytest.approx(90_000e6)
    # ...and a revenue net of interest a thousand times the top line is a unit slip, not the whole (as for the top-line concepts)
    g = _issuer_facts()
    g["us-gaap"]["RevenuesNetOfInterestExpense"] = {"units": {"USD": [_fy("2025-12-31", "2025-01-01", 41_304e9, "2026-02-06")]}}
    assert sec.revenue(g, "annual")["2025-12-31"] == pytest.approx(41_304e6)


# ---------- 2. a split after the latest annual report ----------
def _split_facts(year_end: str, year_start: str, filed: str, profit: float, eps: float, year_end_held: float,
                 cover: tuple[str, float], quarter: tuple[str, str, float, str] | None) -> dict:
    y = lambda v: [_fy(year_end, year_start, v, filed)]   # noqa: E731
    us = {"Revenues": {"units": {"USD": y(4_812e6)}}, "NetIncomeLoss": {"units": {"USD": y(profit)}},
          "EarningsPerShareBasic": {"units": {"USD/shares": y(eps)}},
          "WeightedAverageNumberOfSharesOutstandingBasic": {"units": {"shares": y(profit / eps)}},
          "CommonStockSharesOutstanding": {"units": {"shares": [{"end": year_end, "val": year_end_held, "filed": filed, "form": "10-K"}]}}}
    if quarter:
        start, end, avg, qfiled = quarter
        us["WeightedAverageNumberOfSharesOutstandingBasic"]["units"]["shares"].append(
            {"start": start, "end": end, "val": avg, "form": "10-Q", "filed": qfiled, "fp": "Q2"})
    return {"facts": {"us-gaap": us, "dei": {"EntityCommonStockSharesOutstanding": {"units": {"shares": [
        {"end": cover[0], "val": cover[1], "filed": cover[0], "form": "10-Q"}]}}}}}


def test_a_forward_split_after_the_annual_report_keeps_the_new_cover_count():
    # CRWD: FY to Jan 2026 (EPS -0.65 on 250 M shares), a 4:1 split on 2 Jul 2026, and 1,023,934,842 shares on the cover of the
    # 10-Q filed in August, whose quarter's average count (1,044 M) is on the new basis
    f = _split_facts("2026-01-31", "2025-02-01", "2026-03-05", -162.5e6, -0.65, 251_000_000,
                     ("2026-08-20", 1_023_934_842), ("2026-05-01", "2026-07-31", 1_044_469_000, "2026-08-27"))
    p = sec.build(f)
    assert p["shares"] == 1_023_934_842 and p["shares_from"] == "cover"


def test_a_reverse_split_after_the_annual_report_keeps_the_new_cover_count():
    # SKIN: FY 2025 on 119 M shares, a 1:20 reverse split on 14 Oct 2026, 6,542,468 shares on the cover of the Q3 10-Q, whose
    # quarter's average is restated to the new basis
    f = _split_facts("2025-12-31", "2025-01-01", "2026-03-10", -59.5e6, -0.50, 120_000_000,
                     ("2026-11-02", 6_542_468), ("2026-07-01", "2026-09-30", 6_510_000, "2026-11-04"))
    p = sec.build(f)
    assert p["shares"] == 6_542_468 and p["shares_from"] == "cover"


def test_a_mistyped_cover_count_is_still_replaced_without_a_later_report_on_its_basis():
    # no later report agrees with the cover count (Alibaba's mistyped 20-F cover, a foreign filer with no quarterly reports):
    # the count the earnings imply, as before
    f = _split_facts("2026-03-31", "2025-04-01", "2026-06-26", 130_000e6, 7.0, 18_580_374_278, ("2026-06-20", 1_858_037_427), None)
    assert sec.build(f)["shares"] == pytest.approx(130_000e6 / 7.0, rel=1e-6)
    # a later quarter whose average agrees with the earnings, not with the cover, doesn't save a mistyped cover count
    g = _split_facts("2025-12-31", "2025-01-01", "2026-03-10", -59.5e6, -0.50, 120_000_000,
                     ("2026-11-02", 6_542_468), ("2026-07-01", "2026-09-30", 119_500_000, "2026-11-04"))
    assert sec.build(g)["shares"] == pytest.approx(119_000_000, rel=1e-6)
    # a thousandfold count stays a unit error even when a later quarter repeats it
    h = _split_facts("2025-12-31", "2025-01-01", "2026-03-10", 25_200_000, 3.13, 8_045_145,
                     ("2026-11-02", 8_045_145_000), ("2026-07-01", "2026-09-30", 8_045_145_000, "2026-11-04"))
    assert sec.build(h)["shares"] == pytest.approx(25_200_000 / 3.13, rel=1e-6)


# ---------- 3. R&D: the total, never a smaller line filed under the total's name ----------
def test_rd_share_is_the_larger_rd_line_not_a_small_line_under_the_totals_name():
    from app.intel import sector_metrics
    y = lambda v: [_fy("2025-12-28", "2024-12-30", v, "2026-02-11")]   # noqa: E731
    facts = {"us-gaap": {"Revenues": {"units": {"USD": y(94_193e6)}},
                         "ResearchAndDevelopmentExpense": {"units": {"USD": y(109e6)}},
                         "ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost": {"units": {"USD": y(14_665e6)}}}}
    got = sector_metrics.us_figures(facts)
    assert got["rd_share"]["v"] == pytest.approx(15.6, abs=0.05)
    # a company filing only the total keeps it
    del facts["us-gaap"]["ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost"]
    assert sector_metrics.us_figures(facts)["rd_share"]["v"] == pytest.approx(0.1, abs=0.05)


# ---------- 4. India: a busy consolidated page never leaves the standalone numbers as the company's ----------
def _screener(con_status: int):
    import httpx
    from app.intel.screener import Screener
    from tests.fake_intel import SCREENER_HTML

    def handler(req):
        if req.url.path.endswith("/consolidated/"):
            return httpx.Response(con_status, text="<html>busy</html>")
        return httpx.Response(200, text=SCREENER_HTML)
    return Screener(transport=httpx.MockTransport(handler))


def test_a_busy_consolidated_page_raises_busy_instead_of_returning_standalone_numbers():
    from app.intel.net import SourceError
    for status in (429, 503, 403):
        with pytest.raises(SourceError) as e:
            _screener(status).company("INDHOTEL")
        assert e.value.busy
    # a company with no consolidated accounts (the site has no such page) still gets its standalone numbers
    p = _screener(404).company("INDHOTEL")
    assert p["basis"] == "standalone" and (p.get("pl") or {}).get("cols")


# ---------- 5. a total profit filed with the wrong sign doesn't turn the shareholders' loss into a profit ----------
def test_a_loss_stays_a_loss_when_only_the_total_profit_is_filed_positive():
    # ALMU: FY to Jun 2026, revenue $4.46 m, NetIncomeLoss -9.16 m, profit before tax -9.16 m, ProfitLoss +9.16 m (the sign slip)
    y = lambda v: [_fy("2026-06-30", "2025-07-01", v, "2026-09-12")]   # noqa: E731
    facts = {"us-gaap": {"Revenues": {"units": {"USD": y(4.46e6)}}, "NetIncomeLoss": {"units": {"USD": y(-9.16e6)}},
                         "ProfitLoss": {"units": {"USD": y(9.16e6)}},
                         "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest": {"units": {"USD": y(-9.16e6)}}}}
    assert sec.build({"facts": facts})["pl"]["rows"]["Net Profit"][-1] == pytest.approx(-9.16, abs=0.01)
    # the shareholders' figure filed the wrong way round, profit before tax with the total's sign: still put right (Santander Chile)
    owners = {"2021-12-31": -842_467.0}
    sec.owner_sign(owners, {"2021-12-31": 852_428.0}, {"2021-12-31": 9_961.0}, {"2021-12-31": 1_010_000.0})
    assert owners["2021-12-31"] == 842_467.0


# ---------- 6. India: consolidated accounts that stopped, or a consolidated page with no table, never hide current figures ----------
def test_stale_or_empty_consolidated_accounts_give_way_to_current_standalone_ones():
    from app.intel import screener as scr
    pl = lambda last, n: {"cols": [f"Mar {last - n + 1 + i}" for i in range(n)] + ["TTM"], "rows": {"Sales": [1] * (n + 1)}}   # noqa: E731
    std = {"ratios": {"x": 1}, "pl": pl(2026, 12)}
    # KOVAI: consolidated 2008-2018, standalone to Mar 2026
    got = scr._pick({"consolidated": {"ratios": {"x": 1}, "pl": pl(2018, 11)}, "standalone": std})
    assert got["basis"] == "standalone" and got["pl"]["cols"][-2] == "Mar 2026" and "stop at Mar 2018" in got["basis_note"]
    # JYOTHYLAB: consolidated a year behind
    assert scr._pick({"consolidated": {"ratios": {"x": 1}, "pl": pl(2025, 12)}, "standalone": std})["basis"] == "standalone"
    # INDRAMEDCO: a consolidated page without a results table
    got = scr._pick({"consolidated": {"ratios": {"x": 1}, "pl": {"cols": [], "rows": {}}}, "standalone": std})
    assert got["basis"] == "standalone" and got["pl"]["cols"][-2] == "Mar 2026"
    # consolidated as current as the standalone, with the longer history: consolidated, as before
    assert scr._pick({"consolidated": {"ratios": {"x": 1}, "pl": pl(2026, 12)}, "standalone": std})["basis"] == "consolidated"


def test_a_current_consolidated_table_with_a_short_history_is_the_companys_figures():
    from app.intel import screener as scr
    pl = lambda last, n: {"cols": [f"Mar {last - n + 1 + i}" for i in range(n)] + ["TTM"], "rows": {"Sales": [1] * (n + 1)}}   # noqa: E731
    # INA: consolidated accounts since Mar 2022 (5 years), standalone since Mar 2020 (7)
    got = scr._pick({"consolidated": {"ratios": {"x": 1}, "pl": pl(2026, 5)}, "standalone": {"ratios": {"x": 1}, "pl": pl(2026, 7)}})
    assert got["basis"] == "consolidated"
