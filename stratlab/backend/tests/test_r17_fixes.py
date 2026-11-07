"""Release 17 fixes: the business-update reader's year-ago column (a group's filing listing two companies' volumes; a table whose other
column is the month before), demergers from corporate-action filings, and the theme deck's layout and wording on synthetic themes."""
from app import biz_updates as B


# ---------- R17-005 (a): the year-ago figure is the year-ago column's ----------
def test_a_groups_filing_gives_each_company_its_own_year_ago_figure():
    # one line of the PDF's text holds both companies' rows under one pair of column headings (Tata Motors PV's and CV's volumes read
    # from one filing: both showed a year-ago 37,530, PV's)
    page = ("Tata Motors Group sales for October 2026\nCompany Oct-26 Oct-25\n"
            "Tata Motors Passenger Vehicles 45,120 37,530 Tata Motors Commercial Vehicles 32,004 30,118")
    quote = "Tata Motors Passenger Vehicles 45,120 37,530 Tata Motors Commercial Vehicles 32,004 30,118"
    for value, ai_prior, want in ((45120, 37530, 37530), (32004, 37530, 30118)):
        reply = {"period": "2026-10", "figures": [{"metric": "Total sales", "value": value, "unit": "units", "basis": "month", "prior": ai_prior,
                                                   "headline": True, "quote": quote, "page": 1}]}
        _, _, figs = B.clean_figures(reply, [page], "2026-11-01T12:00")
        assert (figs[0]["value"], figs[0]["prior"]) == (value, want)


def test_without_headings_the_row_befores_figure_is_not_this_ones():
    quote = "PV 45,120 37,530 CV 32,004 30,118"
    assert B.own_column(32004, 37530, quote, "no headings here", "2026-10") == (32004, None)
    assert B.own_column(32004, 30118, quote, "no headings here", "2026-10") == (32004, 30118)
    # prose: the year-ago figure after the value, months named in between, is kept
    prose = "sales with 672,790 units in September 2026 as against 541,064 units in September 2025."
    assert B.own_column(672790, 541064, prose, prose, "2026-09") == (672790, 541064)


def test_a_table_whose_other_column_is_the_month_before_gives_no_year_ago_figure():
    # Mahindra: 1,14,737 against 38,563, a column that wasn't the year before
    page = "Mahindra & Mahindra sales\nCategory Oct-26 Sep-26\nTotal 1,14,737 38,563"
    reply = {"period": "2026-10", "figures": [{"metric": "Total sales", "value": 114737, "unit": "units", "basis": "month", "prior": 38563,
                                               "headline": True, "quote": "Total 1,14,737 38,563", "page": 1}]}
    _, _, figs = B.clean_figures(reply, [page], "2026-11-01T12:00")
    assert (figs[0]["value"], figs[0]["prior"]) == (114737, None)
    # three columns, this month, the month before and the year before: the year-ago column's figure
    page3 = "Category Oct-26 Sep-26 Oct-25\nTotal 1,14,737 38,563 1,02,110"
    assert B.own_column(114737, 38563, "Total 1,14,737 38,563 1,02,110", page3, "2026-10") == (114737, 102110)
    page3b = "Category Oct-26 Oct-25 Sep-26\nTotal 1,14,737 1,02,110 38,563"
    assert B.own_column(114737, 38563, "Total 1,14,737 1,02,110 38,563", page3b, "2026-10") == (114737, 102110)


# ---------- R17-005 (b): a demerger from the stored corporate actions ----------
def test_a_demerger_in_the_stored_corporate_actions_breaks_the_series_even_without_a_revenue_jump():
    from tests.test_r16_deck import build
    from tests.test_theme1 import TODAY
    acts = {"MINEA": [{"kind": "demerger", "ex_date": "2025-10-14", "text": "Demerger"}, {"kind": "dividend", "ex_date": "2026-07-01"}],
            "MINEB": [{"kind": "dividend", "ex_date": "2025-08-01"}, {"kind": "demerger", "ex_date": "2019-01-01"}]}     # too long ago to matter
    out = build(corp_history=lambda s: acts.get(s, []))
    lead = {x["symbol"]: x for x in out["sections"]["leaders"]}
    assert lead["MINEA"]["sales_1y"] is None and lead["MINEB"]["sales_1y"] is not None
    assert [(x["symbol"], x.get("demerger")) for x in out["checks"]["series"]] == [("MINEA", "2025-10-14")]
    # a source that fails is no demerger, and no crash
    out = build(corp_history=lambda s: (_ for _ in ()).throw(RuntimeError("down")))
    assert out["checks"]["series"] == [] and TODAY
