"""Release 42, lane m1: business updates read from a filing with year-to-date columns (LIVE7B-001), one row per figure, and a
farm-machinery maker's operating measures (LIVE7B-023)."""
from app import biz_updates as B
from app import industry
from tests.test_review_df1 import biz_pages


def _reply(period, rows):
    return {"period": period, "span": "month", "figures": [
        {"metric": m, "segment": seg, "value": v, "unit": u, "basis": "month", "prior": p, "headline": h, "quote": q, "page": 1}
        for m, seg, v, u, p, h, q in rows]}


def test_a_year_to_date_column_is_never_the_year_ago_month():
    # the filing's own table: "October -26 Year to Date October - 25 Year to Date"; the AI gave the year-to-date column as the year-ago figure
    pages = biz_pages("VSTTILLERS_01112026132436_Sales.pdf")
    assert B.column_periods(pages[0], "2026-10") == ["2026-10", B.TO_DATE, "2025-10", B.TO_DATE]
    reply = _reply("2026-10", [
        ("Total sales", None, 3519, "nos", 33103, True, "Total (in Nos) 3519 33103 4664 32069"),
        ("Power tiller", "Power Tiller", 3114, "units", 30272, False, "Power Tiller 3114 30272 4077 28906"),
        ("Tractor", "Tractor", 405, "Nos.", 2831, False, "Tractor 405 2831 587 3163")])
    period, _, figs = B.clean_figures(reply, pages, "2026-11-01T13:24")
    assert period == "2026-10"
    assert [(f["metric"], f["value"], f["prior"]) for f in figs] == [("Total sales", 3519, 4664), ("Power tiller", 3114, 4077), ("Tractor", 405, 587)]
    # no doubled labels, one unit for a count
    assert all(f["segment"] is None and f["unit"] == "units" for f in figs)
    reads = {"oct": {"at": "2026-11-01T13:24", "title": "Monthly Business Update", "url": "https://nsearchives.nseindia.com/corporate/x.pdf",
                     "period": period, "span": "month", "figures": figs, "reader": B.READER}}
    top = B.headline(B.series(reads))
    assert top["change_year"] == -24.5          # 3,519 against 4,664
    assert B.words(top) == "Total sales 3,519 units in Oct 2026: down 24.5% on Oct 2025"


def test_a_cumulative_range_heading_is_a_column_too():
    page = "Particulars Apr-Oct 26 Oct-26 Oct-25 Apr-Oct 25\nTotal 33,103 3,519 4,664 32,069"
    assert B.column_periods(page, "2026-10") == [B.TO_DATE, "2026-10", "2025-10", B.TO_DATE]
    assert B.own_column(3519, 33103, "Total 33,103 3,519 4,664 32,069", page, "2026-10") == (3519, 4664)


def test_the_same_figure_read_from_both_exchanges_is_one_row():
    # September: the BSE copy read "Power weeder (nos)", the NSE copy "Power weeder (Power weeder), units"; one row, the later read's figures
    pages = biz_pages("VSTTILLERS_01102026105207_SALESNOS.pdf")
    bse = _reply("2026-09", [("Power weeder", None, 1004, "nos", 1001, False, "Power weeder 1004 6076 1001 4970")])
    nse = _reply("2026-09", [("Power weeder", "Power weeder", 1004, "units", 6076, False, "Power weeder 1004 6076 1001 4970")])
    reads = {}
    for fid, at, ex, reply in (("b", "2026-10-01T10:50", "BSE", bse), ("n", "2026-10-01T10:52", "NSE", nse)):
        period, span, figs = B.clean_figures(reply, pages, at)
        reads[fid] = {"at": at, "title": "Monthly Business Update", "url": f"https://nsearchives.nseindia.com/corporate/{fid}.pdf",
                      "exchange": ex, "period": period, "span": span, "figures": figs, "reader": B.READER}
    rows = B.series(reads)
    assert len(rows) == 1
    assert (rows[0]["latest"]["value"], rows[0]["year_ago"]["value"], rows[0]["change_year"]) == (1004, 1001, 0.3)
    # reads stored by an older reader, with the doubled label and another spelling of the unit, also make one row
    old = {k: {**r, "figures": [{**f, "segment": "Power Weeder", "unit": u} for f in r["figures"]]} for (k, r), u in zip(reads.items(), ("Nos", "units"))}
    assert len(B.series(old)) == 1 and B.series(old)[0]["segment"] is None


def test_a_monthly_figure_has_no_previous_quarter():
    def r(at, period, value):
        return {"at": at, "title": "update", "url": f"https://nsearchives.nseindia.com/corporate/{at}.pdf", "period": period, "span": "month",
                "reader": B.READER, "figures": [{"metric": "Power weeder", "segment": None, "value": value, "unit": "units", "basis": "month",
                                                 "prior": None, "headline": False, "quote": "q", "page": 1, "own": True}]}
    # months read: May, Jun, then Sep (Jul and Aug not read): Sep's "previous" is not June
    reads = {"a": r("2026-06-01", "2026-05", 900), "b": r("2026-07-01", "2026-06", 1001), "c": r("2026-10-01", "2026-09", 1004)}
    row = B.series(reads)[0]
    assert row["prev"] is None and row["change_prev"] is None and row["step"] == "month"
    # a figure filed only once a quarter still has its previous quarter
    reads = {"b": r("2026-07-01", "2026-06", 1001), "c": r("2026-10-01", "2026-09", 1004)}
    row = B.series(reads)[0]
    assert row["prev"]["period"] == "2026-06" and row["step"] == "quarter"


def test_a_farm_machinery_maker_is_not_given_automobile_measures():
    for path in (["Automobile and Auto Components", "Automobiles", "Tractors"], ["Capital Goods", "Agricultural machinery"],
                 ["Manufacturing", "Farm Machinery & Equipment"]):
        got = industry.measures({"industry_path": path, "name": "A Company Ltd"})
        assert got["key"] == "farm", path
        assert not any("EV share" in m or "vehicle" in m.lower() for m in got["measures"])
    # a carmaker keeps the automobile measures
    assert industry.measures({"industry_path": ["Automobiles", "Passenger Cars & Utility Vehicles"], "name": "Cars Ltd"})["key"] == "auto"
    # the name decides when the industry says only "Automobiles"
    assert industry.measures({"industry_path": ["Automobiles"], "name": "Example Tillers Tractors Ltd"})["key"] == "farm"
