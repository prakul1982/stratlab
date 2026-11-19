"""Release 48 (lane vr48, the outside review of the live R46 decks), P0: no figure is suppressed by an arithmetic check alone.

The live R46 Chemicals deck's data-confidence page (p.4) marked Swan Corp's 6.2% net margin invalid ("net profit positive, return on capital
negative") and showed it as "–". Its source row (p.37) printed the year's stored lines: revenue ₹4,371 crore, net profit ₹271 crore, an EBITDA
margin of −4.7%, other income, profit before tax and tax rate not stored. A positive net profit beside a negative ROCE does not by itself
show a wrong figure: the two are reconciled with the year's stored lines (its EBIT, the capital employed, the other years) and the record says
which explanation the lines give, or that they don't reconcile. A figure is invalid only on an established reporting or calculation defect
(a margin on no positive revenue, a unit gap the year's own lines show, a return on negative capital employed).

Swan Corp's lines are those its live R46 deck printed; its ROCE (negative, not printed on the deck) is a stand-in. Every other company is
synthetic."""
from app import deck
from app.intel import theme_data as D
from tests.test_export import texts
from tests.test_r18_deck import deck_of
from tests.test_theme1 import facts

BUILT = "2026-11-08T05:00:00+00:00"


def co(sym, name, sales, opm, profit, roce=12.0, lines=None, **kw):
    """A company's four years to Mar 2026 (the latest with `sales`, `opm` and `profit`), its latest year's stored lines (`lines`)."""
    f = facts(sym, name, [sales * 0.85, sales * 0.9, sales * 0.95, sales], [opm] * 4, [profit * 0.8, profit * 0.85, profit * 0.9, profit],
              roce=roce, industry=("Chemicals",), basis="consolidated", built_at=BUILT, **kw)
    if lines:
        f["years"][-1].update(lines)
    return f


def swan(**lines):
    # the live R46 lines: ₹271 crore of net profit on ₹4,371 crore of revenue, an EBITDA margin of −4.7%
    return co("SWANCORP", "Swan Corp Ltd", 4371.0, -4.7, 271.0, roce=-1.0, lines=lines or None)


# ---------- 1. the sign check reconciled, never invalid for the signs alone ----------
def test_the_live_swan_corp_lines_give_an_operating_loss_and_the_net_margin_is_shown_not_suppressed():
    r = D.company_row("IN", "SWANCORP", swan())
    rec = r["verify"]["net"]
    # before R48: r["net"] None, held "invalid" for "net profit positive, return on capital negative"
    assert r["net"] == 6.2 and "net" not in (r.get("held") or {}) and rec["state"] != D.INVALID
    # the lines: EBITDA −₹205 crore, an operating loss, so the negative ROCE agrees with the year; the net profit above EBITDA has no stored
    # line to explain it (the page predates them), so the margin is not reconciled: shown with †, out of the medians, the reason said
    assert rec["sign"]["kind"] == "operating_loss" and r["roce"] == -1.0 and "roce" not in (r.get("held") or {})
    assert "agrees with Mar 2026's operating loss before other income: −₹205 crore (EBITDA, before depreciation)" in rec["why"]
    assert rec["state"] == D.UNVERIFIED and r["one_off"] and D.in_median(r, "net") is None
    assert D.CHECKS["sign"] in rec["checks"] and D.CHECKS["net_above_ebitda"] in rec["checks"]
    # the record carries the source record vf46 added
    st = D.figure_states([{**r, "status": "core"}])
    assert [(x["key"], x["state"]) for x in st] == [("net", D.UNVERIFIED)] and st[0]["source"]["document"] == "annual results, consolidated"
    assert st[0]["sign"]["kind"] == "operating_loss" and st[0]["source"]["page"] == "/stocks/in/SWANCORP"


def test_the_same_lines_with_the_year_s_statement_stored_are_verified():
    # other income ₹600 crore lifts the operating loss to a net profit: profit before tax ₹350 crore at a 22.6% tax rate gives ₹271 crore
    r = D.company_row("IN", "SWANCORP", swan(op=-205.0, other_income=600.0, interest=20.0, dep=25.0, pbt=350.0, tax_pct=22.6))
    rec = r["verify"]["net"]
    assert r["net"] == 6.2 and rec["state"] == D.VERIFIED and not r["one_off"] and D.in_median(r, "net") == 6.2
    assert rec["sign"]["kind"] == "operating_loss" and "other income of ₹600 crore" in rec["why"]
    assert "covered by income outside operations of ₹600 crore" in rec["why"]


def test_negative_capital_employed_makes_the_roce_invalid_and_leaves_the_net_margin_verified():
    # book value −₹50 a share on 100 crore shares (₹10,000 crore at ₹100): equity −₹5,000 crore, debt ₹100 crore
    r = D.company_row("IN", "NEGCE", co("NEGCE", "Negative Capital Ltd", 2000.0, 15.0, 160.0, roce=-3.0, book_value=-50.0))
    assert r["net"] == 8.0 and r["roce"] is None and r["verify"]["roce"]["state"] == D.INVALID
    assert r["held"]["roce"]["checks"] == [D.CHECKS["neg_capital"]]
    rec = r["verify"]["net"]
    assert rec["state"] == D.VERIFIED and D.in_median(r, "net") == 8.0 and rec["sign"]["kind"] == "negative_capital"
    assert "capital employed of −₹4,900 crore (book equity −₹5,000 crore and debt ₹100 crore), below zero" in rec["why"]
    assert rec["sign"]["capital"] == {"equity": -5000.0, "debt": 100.0, "value": -4900.0}


def test_an_operating_loss_lifted_by_other_income_is_the_explanation_the_lines_give():
    # operating profit ₹50 crore less depreciation ₹80 crore: a loss of ₹30 crore before other income of ₹100 crore
    lines = {"op": 50.0, "other_income": 100.0, "interest": 10.0, "dep": 80.0, "pbt": 60.0, "tax_pct": 25.0}
    r = D.company_row("IN", "OPLOSS", co("OPLOSS", "Operating Loss Ltd", 1000.0, 5.0, 45.0, roce=-2.0, lines=lines))
    rec = r["verify"]["net"]
    assert r["net"] == 4.5 and rec["state"] == D.VERIFIED and rec["sign"]["kind"] == "operating_loss" and r["roce"] == -2.0
    assert "operating loss before other income: −₹30 crore (operating profit less depreciation), lifted to a net profit by other income of ₹100 crore" in rec["why"]


def test_positive_lines_put_the_roce_in_question_not_the_net_margin():
    # EBIT ₹130 crore (profit before tax ₹120 crore plus interest ₹10 crore) on positive capital: a positive return, not the −2% ROCE
    lines = {"op": 150.0, "other_income": 10.0, "interest": 10.0, "dep": 30.0, "pbt": 120.0, "tax_pct": 25.0}
    r = D.company_row("IN", "DISAG", co("DISAG", "Disagree Ltd", 1000.0, 15.0, 90.0, roce=-2.0, lines=lines, book_value=40.0))
    assert r["net"] == 9.0 and r["verify"]["net"]["state"] == D.VERIFIED and r["verify"]["net"]["sign"]["kind"] == "lines_disagree"
    assert r["roce"] is None and r["verify"]["roce"]["state"] == D.UNVERIFIED and "does not reconcile with the year's lines" in r["verify"]["roce"]["why"]
    # an earlier stored year whose EBIT was a loss: the ROCE is not of the year's lines
    f = co("OTHYR", "Other Year Ltd", 1000.0, 15.0, 90.0, roce=-2.0, lines=lines, book_value=40.0)
    f["years"][-2].update(op=-40.0, dep=30.0)
    r = D.company_row("IN", "OTHYR", f)
    assert r["verify"]["net"]["sign"]["kind"] == "other_year" and r["verify"]["roce"]["state"] == D.UNVERIFIED
    assert "another stored year was a loss (Mar 2025 EBIT −₹70 crore)" in r["verify"]["roce"]["why"]


def test_with_nothing_stored_to_tell_the_net_margin_is_not_reconciled_never_invalid():
    f = co("BARE", "Bare Lines Ltd", 1000.0, 15.0, 90.0, roce=-2.0)
    f["price"] = None                                   # no shares in issue to work the book equity out from, and no P/B
    r = D.company_row("IN", "BARE", f)
    rec = r["verify"]["net"]
    assert r["net"] == 9.0 and rec["state"] == D.UNVERIFIED and r["one_off"] and rec["sign"]["kind"] == "not_stored"
    assert "no profit before tax and interest, or depreciation or book value stored for Mar 2026 to reconcile them" in rec["why"]


def test_a_page_net_margin_of_the_other_sign_from_another_year_is_reconciled():
    f = co("PAGEY", "Page Year Ltd", 1000.0, 15.0, 90.0, net_margin=-4.0)
    f["years"][-2]["profit"] = -38.0                     # Mar 2025: −₹38 crore on ₹950 crore, −4.0%, the page's own figure
    r = D.company_row("IN", "PAGEY", f)
    assert r["net"] == 9.0 and r["verify"]["net"]["state"] == D.VERIFIED and r["verify"]["net"]["sign_page"]["year"] == "Mar 2025"
    assert "the page's own net margin of −4.0% is Mar 2025's (net profit −₹38 crore over revenue ₹950 crore), another year" in r["verify"]["net"]["why"]


# ---------- 2. the other arithmetic checks: invalid only on an established defect ----------
def test_a_profit_ten_times_revenue_is_a_unit_gap_only_when_no_stored_line_gives_it():
    # a holding company's gain on a sale: ₹1,500 crore of net profit on ₹100 crore of revenue, the year's lines giving it
    lines = {"op": 20.0, "other_income": 10.0, "interest": 0.0, "dep": 5.0, "pbt": 1800.0, "tax_pct": 16.7}
    r = D.company_row("IN", "GAIN", co("GAIN", "Gain Holdings Ltd", 100.0, 20.0, 1500.0, lines=lines))
    assert r["net"] == 1500.0 and r["verify"]["net"]["state"] == D.VERIFIED and "net" not in (r.get("held") or {})
    # twenty times with no line stored: not reconciled (shown with †), never invalid; a hundredfold or more: a unit gap (tests/test_r44_verify.py)
    r = D.company_row("IN", "TWENTY", co("TWENTY", "Twenty Times Ltd", 100.0, 20.0, 2000.0))
    assert r["net"] == 2000.0 and r["verify"]["net"]["state"] == D.UNVERIFIED and r["one_off"]
    # the net profit eighty times its own profit before tax too: the unit gap is shown by the filing's own lines
    short = {"op": 20.0, "other_income": 10.0, "interest": 0.0, "dep": 5.0, "pbt": 25.0, "tax_pct": 25.0}
    r = D.company_row("IN", "SHORT", co("SHORT", "Short Lines Ltd", 100.0, 20.0, 2000.0, lines=short))
    assert r["net"] is None and r["verify"]["net"]["state"] == D.INVALID and "and profit before tax ₹25 crore: the year's stored lines don't give it" in r["verify"]["net"]["why"]


def test_an_ebitda_margin_above_100_is_invalid_only_when_its_own_lines_do_not_give_it():
    as_filed = D.company_row("IN", "HIOP", co("HIOP", "High Op Ltd", 100.0, 130.0, 6.0, lines={"op": 130.0}))
    assert as_filed["ebitda"] is None and as_filed["verify"]["ebitda"]["state"] == D.UNVERIFIED
    assert "as filed: operating profit ₹130 crore on revenue ₹100 crore; not reconciled" in as_filed["verify"]["ebitda"]["why"]
    wrong = D.company_row("IN", "HIWR", co("HIWR", "High Wrong Ltd", 100.0, 130.0, 6.0, lines={"op": 13.0}))
    assert wrong["verify"]["ebitda"]["state"] == D.INVALID and wrong["held"]["ebitda"]["checks"] == [D.CHECKS["ebitda_lines"]]


def test_a_revenue_out_of_scale_is_not_reconciled_unless_its_years_show_the_slip():
    def row(revs, cap):
        return {"symbol": "T", "name": "Scale Co", "revenue": revs[-1], "cap": cap, "profit": -1.88, "ebitda": -0.5, "net": -0.1, "capital_rev": 0.0,
                "years": [{"year": f"Dec {2022 + i}", "sales": s, "profit": -1.0} for i, s in enumerate(revs)]}
    flat = D.validate_row(row([103536.0] * 3, 57.0), {}, None)
    assert flat["held"]["ebitda"]["state"] == D.UNVERIFIED and flat["verify"]["net"]["state"] == D.UNVERIFIED
    jump = D.validate_row(row([100.0, 103.0, 103536.0], 57.0), {}, None)
    assert jump["held"]["ebitda"]["state"] == D.INVALID and "a unit gap" in jump["verify"]["ebitda"]["why"]


def test_the_established_defects_stay_invalid():
    z = D.company_row("IN", "ZERO", co("ZERO", "Zero Co", -5.0, 12.0, 1.0))
    assert z["verify"]["ebitda"]["state"] == D.INVALID and z["held"]["ebitda"]["checks"] == [D.CHECKS["no_revenue"]]
    e = D.company_row("IN", "NEGEQ", co("NEGEQ", "Negative Equity Ltd", 1000.0, 15.0, 90.0, book_value=-1.0))
    assert e["roe"] is None and e["verify"]["roe"]["state"] == D.INVALID


# ---------- 3. the deck: the Chemicals p.4 acceptance on the live lines ----------
def chem_map():
    cos = [{"name": "Swan Corp Ltd", "ticker": "SWANCORP", "what": "makes petrochemicals"}] + \
          [{"name": f"Chem {i} Ltd", "ticker": f"CHM{i}", "what": "makes petrochemicals"} for i in range(5)]
    return {"sector": "Chemicals", "value_chain": [{"layer": "Petrochemicals", "description": "Makes petrochemicals.", "companies": cos}],
            "sub_themes": [], "placements": {"checked": True, "pending": 0, "left_out": 0, "placed": len(cos)}}


def chem_facts():
    f = {"SWANCORP": swan()}
    for i in range(5):
        f[f"CHM{i}"] = co(f"CHM{i}", f"Chem {i} Ltd", 1000.0 + 100 * i, 12.0 + i, 60.0 + 5 * i)
    return f


def conf_rows(slides):
    conf = next(s for s in slides if s.title == "Data confidence")
    return {r[0]: r for b in conf.blocks if b["kind"] == "table" for r in b["rows"]}


def test_no_figure_on_the_data_confidence_page_is_suppressed_for_the_signs_alone():
    v, slides = deck_of("IN", chem_map(), chem_facts())
    ch = v["checks"]
    assert not [x for x in ch["held"] if x["symbol"] == "SWANCORP"]          # nothing "–" for Swan Corp
    rows = conf_rows(slides)
    assert "Figure checks" not in rows or "Swan Corp" not in rows["Figure checks"][1]
    assert "Swan Corp Ltd (6.2% net, −4.7% EBITDA)" in rows["Net above EBITDA margin"][1]
    t = texts(slides)
    assert "6.2%†" in t
    src = next(s for s in slides if s.title.startswith(deck.SOURCES_TITLE))
    row = next(r for b in src.blocks if b["kind"] == "table" for r in b["rows"] if r[0].startswith("Swan Corp Ltd"))
    assert "not reconciled" in row[1] and "EBIT −205 (EBITDA, before depreciation): an operating loss, as ROCE −1% says" in row[4]
