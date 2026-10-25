"""Review DH: the tax report, Tax tools, the ITR export, US tax and the money calendar. Due dates from one table of
the Act's dates and the CBDT's extensions (FY 2025-26 audit cases: report 21 Oct 2026, return 21 Nov 2026), firm audit
wording, one "payable now" figure with 234A/234B/234C, the return's rounding (288A/288B), the AY 2026-27 112A upload
layout, the schedules added or listed as not covered, and the calendar's own items. All figures are made up here."""
import base64
from datetime import date

import pytest

from app import money_advance_tax as A, money_calendar as M, money_itr as I, money_routes as R, money_us_tax as U
from app import tax_due as D, tax_lots as T, tax_total as X, xlsx_write
from tests import world

PRO, FREE = world.headers("pro-token"), world.headers("free-token")
L = 100000.0


# ---------- DH-001, DH-030, DH-040: one table of due dates ----------
def test_due_dates_follow_the_cbdt_extensions():
    a = D.due(2025, "audit")
    assert a["date"] == date(2026, 11, 21) and a["statutory"] == date(2026, 10, 31) and a["extended"] and "7/2026" in a["source"]
    assert D.due(2025, "audit_report")["date"] == date(2026, 10, 21)
    assert D.return_due(2025) == date(2026, 7, 31) and D.return_due(2025, True) == date(2026, 8, 31)     # not extended
    assert D.return_due(2024, True) == date(2025, 9, 16) and D.return_due(2024, True, True) == date(2025, 12, 10)
    assert D.return_due(2023, True, True) == date(2024, 11, 15) and D.due(2023, "audit_report")["date"] == date(2024, 10, 7)
    assert D.return_due(2022, True, True) == date(2023, 10, 31) and not D.due(2022, "audit")["extended"]     # the Act's date
    assert A.return_due(2025, True, True) == date(2026, 11, 21)            # Tax tools reads the same table


def test_234a_months_count_a_part_month_as_a_month():
    due = date(2026, 11, 21)
    assert D.months_late(due, date(2026, 11, 21)) == 0 and D.months_late(due, date(2026, 12, 5)) == 1
    assert D.months_late(due, date(2026, 12, 22)) == 2 and D.months_late(date(2026, 8, 31), date(2026, 9, 30)) == 1


def test_every_page_says_the_extended_date():
    facts = " ".join(X.filing_facts(2025, 39.7e7, True))
    assert "21 November 2026" in facts and "unless extended" not in facts and "31 October with an audit" not in facts
    assert "31 March 2027" in facts and "fee" in facts
    us = " ".join(U.FACTS)
    assert "21 November 2026" in us and "or 31 October with an audit" not in us
    evs = {e["kind"]: e for e in M.tax_dates(2025)}
    assert evs["audit_report"]["date"] == "2026-10-21" and "3CD" in evs["audit_report"]["detail"] and "271B" in evs["audit_report"]["detail"]
    assert [e["date"] for e in M.tax_dates(2025) if e["title"].endswith("(audit cases)")] == ["2026-11-21"]
    assert "fee" in evs["itr_revise"]["detail"]


# ---------- DH-002: the audit wording ----------
def test_audit_above_the_higher_limit_is_said_firmly():
    got = X.audit_fact(2025, 25e7, True)                  # a made-up ₹25 crore of turnover
    assert "a tax audit applies" in got and "usually" not in got and "cash receipts" not in got
    assert "21 October 2026" in got and "21 November 2026" in got and "0.5% of turnover" in got
    assert X.audit_applies(2025, 25e7, True)
    assert "unless cash receipts" in X.audit_fact(2025, 4e7, True)        # between the limits it still depends on cash


# ---------- DH-004: the return's rounding ----------
def test_round10_as_sections_288a_and_288b():
    assert X.round10(21300765) == 21300770 and X.round10(7761298.4) == 7761300 and X.round10(14.99) == 10
    assert X.round10(15) == 20 and X.round10(0) == 0 and X.round10(-5) == 0


def test_the_estimate_carries_the_return_rounding():
    inp = {"regime": "new", "other": 30 * L + 3, "salary": None}        # total income ₹29,25,003 after the deduction
    e = X.estimate(2025, inp, [], 0, 0)
    assert e["income"]["total"] == pytest.approx(2925003) and e["rounded"]["income"] == 2925000
    # the tax on the rounded income, rounded: the same as the estimate on ₹3 less
    assert e["rounded"]["tax"] == X.round10(X.estimate(2025, {**inp, "other": 30 * L}, [], 0, 0)["total"])
    assert [ln for ln in e["lines"] if ln["kind"] == "rounded"][-1]["amount"] == e["rounded"]["tax"]


# ---------- DH-003: payable now, with 234A, 234B and 234C ----------
def test_payable_counts_234b_to_the_extended_date_for_an_audit_case():
    s = A.schedule(2025, 10 * L, [10 * L] * 4, 0.0, [], date(2026, 10, 25), business=True, audit=True)
    assert s["b234"]["months"] == 8 and s["b234"]["interest"] == 80000            # April to November 2026
    p = A.payable(2025, s, 10 * L, 30 * L, [], date(2026, 10, 25), business=True, audit=True)
    assert p["interest_234a"] == 0 and p["fee_234f"] == 0 and not p["past_due"] and p["due"] == "2026-11-21"
    assert p["total"] == X.round10(10 * L + 80000 + s["interest_234c"])
    assert [ln["label"] for ln in p["lines"]][-1].startswith("Payable now")


def test_payable_adds_234a_and_the_late_fee_once_the_due_date_has_passed():
    today = date(2026, 12, 5)
    s = A.schedule(2025, 2 * L, [2 * L] * 4, 50000.0, [{"d": "2026-03-10", "amount": 50000.0}], today, business=True)
    p = A.payable(2025, s, 2 * L, 10 * L, [{"d": "2026-03-10", "amount": 50000.0}], today, business=True)
    assert p["past_due"] and p["months_234a"] == 4 and p["interest_234a"] == 4000      # 1 Sep to 5 Dec on ₹1 lakh
    assert p["fee_234f"] == 5000 and p["balance"] == 1 * L
    assert A.payable(2026, s, 2 * L, 10 * L, [], date(2026, 12, 5)) is None             # the year still running


# ---------- DH-010: Schedule 112A for AY 2026-27 ----------
def _b(d, q, p, k="A"):
    return {"d": d, "side": "B", "qty": q, "price": p, "sym": k, "isin": f"INE{k:0>3}A01011", "name": f"{k} Ltd"}


def _s(d, q, p, k="A"):
    return {**_b(d, q, p, k), "side": "S"}


def _rows(trades, fy, fmv=None):
    c = T.compute(trades, fmv=fmv, today="2026-10-25")
    return [r for r in c["realised"] if r["fy"] == fy], c["names"]


def test_the_portal_layout_has_the_templates_header_and_no_1b_from_fy_2025_26():
    rows, names = _rows([_b("2017-01-02", 3, 100.3), _s("2025-06-03", 3, 300.7), _b("2020-01-02", 3, 10), _s("2025-07-01", 3, 30.4, "A")],
                        2025, fmv={"A": 150.25})
    p = I.t_112a_portal({"fy": 2025, "rows": rows, "names": names})
    assert p["columns"] == I.PORTAL_112A and len(p["columns"]) == 14 and not any("1b" in c for c in p["columns"])
    assert p["columns"][5] == "Full Value of Consideration(Total Sale Value)(6) = 4 * 5"
    for r in p["rows"]:
        assert all(isinstance(r[i], int) for i in (5, 6, 7, 11, 12, 13))           # columns 6, 7, 8, 12, 13, 14: whole rupees
        assert r[12] == r[6] + r[11] and r[13] == r[5] - r[12]                     # 13 = 7 + 12, 14 = 6 - 13
    be = next(r for r in p["rows"] if r[0] == "BE")
    assert be[5] == round(be[3] * be[4]) and be[6] == max(be[7], be[8])            # 6 = 4 x 5, 7 = higher of 8 and 9
    assert not any("1b" in c for c in I.t_112a({"fy": 2025, "rows": rows, "names": names})["columns"])
    rows24, names24 = _rows([_b("2017-01-02", 1, 100), _s("2024-06-03", 1, 300)], 2024, fmv={"A": 150})
    p24 = I.t_112a_portal({"fy": 2024, "rows": rows24, "names": names24})
    assert p24["columns"][1] == "Share/Unit Transferred(1b)" and p24["rows"][0][1] == "BE"
    assert all(len(x["sheet"] or "") <= 31 for x in (p, I.t_112a({"fy": 2025, "rows": rows, "names": names})))


# ---------- DH-011, DH-013: the schedules added, the ones not covered, the files ----------
def _g(other=0.0, biz=None):
    biz = biz or []
    y = T.with_total(T.year(2025, [], [], limit=None), biz, {"regime": "new", "other": other, "salary": 0.0} if other else None)
    return {"fy": 2025, "y": y, "rows": [], "unit_rows": [], "names": {}, "files": [], "fmv_src": {}, "div_lines": [], "div_source": "none",
            "div_year": None, "us_div": None, "fa": None, "us_count": 0, "us_allowed": True, "tds": 0.0, "paid": [], "mf_count": 0,
            "made": date(2026, 10, 25), "audit": X.audit_applies(2025, y["turnover"], bool(biz)), "business": bool(biz), "payable": None}


def test_new_schedules_and_the_not_covered_list():
    biz = [{"seg": "fno", "fy": 2025, "first": "2025-04-02", "last": "2026-03-20", "trades": 900, "pnl": -6 * L, "charges": 50000.0,
            "stt": 10000.0, "turnover": 12e7, "turnover_contract": 11e7, "by": []}]
    g = _g(other=150 * L, biz=biz)                        # ₹1.5 crore of other income (none salary), a ₹6.5 lakh F&O loss, ₹12 crore turnover
    keys = [t["key"] for t in I.tables(g)]
    assert {"cfl", "setoff", "general", "tti"} <= set(keys)
    general = dict((r[0], r[1]) for r in I.t_general(g)["rows"])
    assert general["Liable to audit under section 44AB?"].startswith("Yes") and "21 October 2026" in general["Due date of the audit report"]
    setoff = I.t_setoff(g)["rows"]
    assert setoff and setoff[0][0].startswith("CYLA") and setoff[0][3] == pytest.approx(6.5 * L)
    nc = " ".join(I.not_covered(g))
    assert "Schedule AL" in nc and "Part A-BS" in nc
    assert "Schedule AL" not in " ".join(I.not_covered(_g(other=20 * L)))
    loss = _g(biz=[{**biz[0], "pnl": -3 * L, "turnover": 3e7}])         # nothing to set it off against: carried forward
    cfl = I.t_cfl(loss)["rows"]
    assert cfl and cfl[0][1].startswith("Business loss") and cfl[0][2] == pytest.approx(3.5 * L) and cfl[0][3] == "AY 2034-35"
    assert I.t_os(_g())["notes"][0].startswith("No Indian dividends")             # not "from none found"
    assert "cellStyles" in xlsx_write.STYLES and 'name="Normal"' in xlsx_write.STYLES


def test_the_pack_has_a_cover_one_line_for_empty_schedules_and_page_numbers():
    from pypdf import PdfReader
    import io
    pdf = I.to_pdf(_g())
    pages = PdfReader(io.BytesIO(pdf)).pages
    text = " ".join(p.extract_text() for p in pages)
    assert "PAN" in text and "Assessment year" in text and "2026-27" in text and "Page 1" in text
    assert "Nothing this year from your files in" in text and len(pages) <= 4
    assert I.indian(395574093.5) == "39,55,74,093.50"


# ---------- DH-005, DH-007: the gains table's losses and the polish ----------
def test_the_year_carries_its_losses_and_plain_labels_from_fy_2025_26():
    rows, names = _rows([_b("2025-04-02", 1, 100), _s("2025-05-02", 1, 105), _b("2025-04-02", 1, 100, "B"), _s("2025-06-02", 1, 90, "B")], 2025)
    y = T.year(2025, rows, [])
    assert y["losses"]["st"] == pytest.approx(10) and y["carry_forward"]["st"] == pytest.approx(5)
    assert y["buckets"][0]["label"] == "Short-term, section 111A (20%)" and "23 Jul" not in " ".join(y["steps"])
    from app import tax_export
    one = {**T.with_total(y, [{"seg": "fno", "fy": 2025, "first": "2025-04-02", "last": "2025-04-02", "trades": 1, "pnl": 10.0,
                                "charges": 1.0, "stt": 0.0, "turnover": 10.0, "turnover_contract": 10.0, "by": []}], None)}
    assert any("(1 exit line)" in a for a, _ in tax_export.summary_lines(one))


def test_sources_count_the_fno_lines_too():
    g = {**_g(), "files": [{"name": "pnl.zip", "broker": "Zerodha", "trades": 1, "fno_lines": 12345, "at": "2026-07-01T00:00"}]}
    assert "1 trade, 12,345 F&O, commodity and currency lines" in I.sources(g)[0]


# ---------- the pages, end to end ----------
@pytest.fixture
def w(monkeypatch):
    M._hits.clear()
    built = world.build(monkeypatch)
    monkeypatch.setattr(R, "today", lambda: date(2026, 10, 25))
    yield built
    built["close"]()
    M._hits.clear()


def _upload(c, h):
    csv = ("Date,Symbol,ISIN,Type,Quantity,Price\n2025-04-02,ACME,INE002A01018,BUY,1000,100\n"
           "2025-05-02,ACME,INE002A01018,SELL,1000,600\n")              # a made-up ₹5 lakh short-term gain in FY 2025-26
    r = c.post("/tax/import", headers=h, json={"filename": "trades.csv", "data": base64.b64encode(csv.encode()).decode(), "mode": "replace"})
    assert r.status_code == 200, r.text


def test_tax_report_tax_tools_and_calendar_say_what_is_still_payable(w):
    c = w["client"]
    _upload(c, PRO)
    assert c.put("/tax/inputs", headers=PRO, json={"fy": 2025, "regime": "new", "other": 20 * L, "salary": None, "deductions": 0,
                                                   "age": "below60", "resident": True}).status_code == 200
    rep = c.get("/tax", headers=PRO).json()
    p = rep["payable"]
    assert p and not p["locked"] and p["fy"] == 2025 and p["total"] > p["tax"] and p["interest_234b"] > 0
    y = next(x for x in rep["years"] if x["fy"] == 2025)
    assert p["tax"] == y["total"]["rounded"]["tax"]
    # DH-020: Tax tools opens on the year with tax still owed
    a = c.get("/money/advance-tax", headers=PRO).json()
    assert a["fy"] == 2025 and a["opened_on_owed"] and a["payable"]["total"] == p["total"]
    now = c.get("/money/advance-tax?fy=2026", headers=PRO).json()
    assert now["fy"] == 2026 and now["owed"]["fy"] == 2025 and now["owed"]["total"] == p["total"]
    # DH-040, DH-043: the calendar's own items
    evs = c.get("/money/calendar?start=2026-10-20&end=2027-01-31", headers=PRO).json()["events"]
    sa = [e for e in evs if e["kind"] == "self_assessment"]
    assert sa and sa[0]["amount"] == p["total"] and "140A" in sa[0]["detail"]
    third = [e for e in evs if e["date"] == "2026-12-15" and e["cat"] == "tax"]
    assert len(third) == 1 and third[0]["kind"] in ("advance_none", "advance_due")


def test_free_sees_the_shares_and_a_lock_for_the_rest(w):
    c = w["client"]
    _upload(c, FREE)
    rep = c.get("/tax", headers=FREE).json()
    assert rep["payable"]["locked"] and rep["payable"]["plan"] == "Pro"
    a = c.get("/money/advance-tax?fy=2025", headers=FREE).json()
    assert a["locked"] and "schedule" not in a and a["plain"]["tax"] > 0
    assert [r["amount"] for r in a["plain"]["rows"]] == [round(a["plain"]["tax"] * x, 2) for x in (0.15, 0.45, 0.75, 1.0)]


def test_the_same_own_date_twice_is_refused(w):
    c = w["client"]
    body = {"date": "2026-11-05", "title": "FD matures"}
    assert c.post("/money/calendar/events", headers=PRO, json=body).status_code == 200
    r = c.post("/money/calendar/events", headers=PRO, json={**body, "title": "fd MATURES"})
    assert r.status_code == 409 and "already in your calendar" in r.text
    assert c.post("/money/calendar/events", headers=PRO, json={**body, "amount": -500}).status_code == 422
