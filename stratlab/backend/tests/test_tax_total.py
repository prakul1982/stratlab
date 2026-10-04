"""The total tax estimate: every year's slabs under both regimes, the section 87A rebate around its limits (with the
marginal relief and the FY 2025-26 rule on special-rate gains), surcharge brackets with the 15% cap on share gains
and the marginal relief, 4% cess, the unused basic exemption against share gains, switching regime, and the
speculative and business loss set-off. Worked by hand, so a change in the rules shows here first."""
import math

import pytest

from app import db, holdings_file, tax_total as X
from tests import tradebook_maker as M, world

RATES = {"st_new": 0.20, "st_old": 0.15, "lt_new": 0.125, "lt_old": 0.10}
L, CR = 100000, 10000000


def bk(exempt: float = 0, **gains) -> list[dict]:
    """Capital gains buckets as year() gives them; `exempt` comes off lt_new."""
    out = []
    for k, v in gains.items():
        ex = min(exempt, v) if k == "lt_new" else 0
        out.append({"key": k, "rate": RATES[k], "after_setoff": v, "exempt": ex, "taxable": v - ex})
    return out


def est(fy=2025, regime="new", other=0.0, salary=None, deductions=0.0, buckets=None, intraday=0.0, business=0.0,
        age="below60", resident=True):
    return X.estimate(fy, {"regime": regime, "other": other, "salary": salary, "deductions": deductions, "age": age,
                           "resident": resident}, buckets or [], intraday, business)


# ---------- the slabs ----------
@pytest.mark.parametrize("fy,regime,income,tax", [
    # FY 2025-26 and 2026-27, new: 0-4L, 5% to 8L, 10% to 12L, 15% to 16L, 20% to 20L, 25% to 24L, 30% above
    (2025, "new", 4 * L, 0), (2025, "new", 8 * L, 20000), (2025, "new", 12 * L, 60000), (2025, "new", 16 * L, 120000),
    (2025, "new", 20 * L, 200000), (2025, "new", 24 * L, 300000), (2025, "new", 25 * L, 330000), (2026, "new", 24 * L, 300000),
    # FY 2024-25, new (Budget July 2024): 0-3L, 5% to 7L, 10% to 10L, 15% to 12L, 20% to 15L, 30% above
    (2024, "new", 3 * L, 0), (2024, "new", 7 * L, 20000), (2024, "new", 10 * L, 50000), (2024, "new", 12 * L, 80000),
    (2024, "new", 15 * L, 140000), (2024, "new", 16 * L, 170000),
    # FY 2023-24, new: 0-3L, then 5/10/15/20% in 3 lakh steps to 15L, 30% above
    (2023, "new", 6 * L, 15000), (2023, "new", 9 * L, 45000), (2023, "new", 15 * L, 150000), (2023, "new", 16 * L, 180000),
    # FY 2020-21 to 2022-23, new: 2.5 lakh steps, 5% to 25%, 30% above 15L
    (2022, "new", 15 * L, 187500), (2020, "new", 5 * L, 12500),
    # old, every year: 0-2.5L, 5% to 5L, 20% to 10L, 30% above
    (2025, "old", 5 * L, 12500), (2024, "old", 10 * L, 112500), (2023, "old", 15 * L, 262500), (2020, "old", 2.5 * L, 0),
])
def test_slab_tables(fy, regime, income, tax):
    assert X.slab_tax(income, X.rules(fy, regime)["slabs"]) == pytest.approx(tax)


def test_standard_deduction_by_year_and_regime():
    assert [X.rules(fy, "new")["std"] for fy in (2022, 2023, 2024, 2025, 2026)] == [0, 50000, 75000, 75000, 75000]
    assert {X.rules(fy, "old")["std"] for fy in range(2020, 2027)} == {50000}
    # only on salary: interest alone gets none
    assert est(other=10 * L, salary=0)["income"]["standard_deduction"] == 0
    assert est(other=10 * L)["income"]["standard_deduction"] == 75000           # salary not said: all of it is salary
    assert est(other=10 * L, salary=40000)["income"]["standard_deduction"] == 40000


def test_years_outside_the_tables_say_so():
    for fy in (2018, 2019, 2027):
        e = est(fy=fy, other=10 * L)
        assert e["available"] is False and "covers FY 2020-21 to FY 2026-27" in e["reason"]


# ---------- the 87A rebate ----------
def test_rebate_fy2025_new_up_to_12_lakh_and_the_marginal_relief():
    assert est(other=12.75 * L)["total"] == 0                                    # 12L after the standard deduction
    just = est(other=12.75 * L + 1)                                               # one rupee over: tax is that rupee
    assert just["slab_tax"] == pytest.approx(60000.15) and just["total"] == pytest.approx(1.04)
    half = est(other=12.5 * L, salary=0)                                          # 50,000 over: tax capped at 50,000
    assert half["rebate"] == pytest.approx(17500) and half["total"] == pytest.approx(52000)
    far = est(other=13 * L, salary=0)                                             # past where relief helps
    assert far["rebate"] == 0 and far["total"] == pytest.approx(75000 * 1.04)
    # where the relief ends: 60,000 + 15% of the excess = the excess
    edge = 12 * L + 60000 / 0.85
    assert est(other=edge - 1, salary=0)["rebate"] > 0 and est(other=edge + 1, salary=0)["rebate"] == 0


def test_rebate_fy2025_new_not_against_special_rate_gains():
    e = est(other=8 * L, salary=0, buckets=bk(st_new=2 * L))                     # total 10L: inside the 12L limit
    assert e["slab_tax"] == 20000 and e["rebate"] == 20000 and e["special_tax"] == 40000
    assert e["total"] == pytest.approx(40000 * 1.04)
    assert any("can't be used against tax on share gains" in s for s in e["steps"])
    # gains count towards the 12L limit: 11L of interest plus 2L of gains is over it
    over = est(other=11 * L, salary=0, buckets=bk(st_new=2 * L))
    assert over["income"]["total"] == 13 * L and over["rebate"] == 0


def test_rebate_fy2024_against_short_term_gains_not_long_term():
    st = est(fy=2024, other=5 * L, salary=0, buckets=bk(st_new=1 * L))           # total 6L <= 7L
    assert (st["slab_tax"], st["special_tax"], st["rebate"]) == (10000, 20000, 25000)
    assert st["total"] == pytest.approx(5000 * 1.04)
    lt = est(fy=2024, other=4 * L, salary=0, buckets=bk(exempt=1.25 * L, lt_new=2.25 * L))   # total 6.25L (all LTCG counts)
    assert lt["income"]["total"] == 6.25 * L and lt["rebate"] == 5000 and lt["special_tax"] == 12500
    assert lt["total"] == pytest.approx(12500 * 1.04)
    assert any("long-term gains (section 112A)" in s for s in lt["steps"])


@pytest.mark.parametrize("fy", [2023, 2024])
def test_rebate_seven_lakh_edges(fy):
    assert est(fy=fy, other=7 * L, salary=0)["total"] == 0
    over = est(fy=fy, other=7.1 * L, salary=0)                                     # marginal relief: tax = 10,000
    assert over["total"] == pytest.approx(10000 * 1.04)
    # salaried: 7L plus the standard deduction
    std = X.rules(fy, "new")["std"]
    assert est(fy=fy, other=7 * L + std)["total"] == 0


def test_rebate_old_regime_five_lakh_without_marginal_relief():
    assert est(regime="old", other=5 * L, salary=0)["total"] == 0
    over = est(regime="old", other=5 * L + 100, salary=0)
    assert over["rebate"] == 0 and over["total"] == pytest.approx((12500 + 20) * 1.04)
    # FY 2022-23 new regime: 5 lakh, no marginal relief either
    assert est(fy=2022, other=5 * L, salary=0)["total"] == 0 and est(fy=2022, other=5.01 * L, salary=0)["rebate"] == 0


def test_unused_basic_exemption_goes_against_share_gains():
    only = est(buckets=bk(st_new=5 * L))                                           # FY 2025-26: 4L of it untaxed
    assert only["special_tax"] == pytest.approx(20000) and only["rebate"] == 0 and only["total"] == pytest.approx(20800)
    old = est(fy=2024, buckets=bk(st_new=5 * L))                                    # FY 2024-25: 3L untaxed, rebate on the rest
    assert old["special_tax"] == 40000 and old["rebate"] == 25000 and old["total"] == pytest.approx(15600)
    # against the highest rate first
    mix = est(fy=2024, other=1 * L, salary=0, buckets=bk(st_new=2 * L, st_old=2 * L))
    assert mix["special_tax"] == pytest.approx(0 * 0.20 + 2 * L * 0.15)


# ---------- surcharge and cess ----------
def test_surcharge_brackets_and_cess():
    sixty = est(other=60 * L, salary=0)
    slab = 300000 + 36 * L * 0.30
    assert sixty["surcharge_rate"] == 0.10 and sixty["surcharge"] == pytest.approx(slab * 0.10)
    assert sixty["cess"] == pytest.approx(slab * 1.10 * 0.04) and sixty["total"] == pytest.approx(slab * 1.10 * 1.04)
    assert est(other=1.5 * CR, salary=0)["surcharge_rate"] == 0.15
    assert est(other=3 * CR, salary=0)["surcharge_rate"] == 0.25
    assert est(other=6 * CR, salary=0)["surcharge_rate"] == 0.25                    # the new regime stops at 25%
    assert est(regime="old", other=6 * CR, salary=0)["surcharge_rate"] == 0.37
    assert est(fy=2022, other=6 * CR, salary=0)["surcharge_rate"] == 0.37          # before FY 2023-24, 37% in both
    for e in (est(other=20 * L), est(regime="old", other=9 * L, deductions=50000)):
        assert e["cess"] == pytest.approx((e["total"]) / 1.04 * 0.04)


def test_marginal_relief_on_surcharge():
    e = est(other=50 * L + 10000, salary=0)                                         # 10,000 over 50 lakh
    at50 = 300000 + 26 * L * 0.30
    assert e["total"] == pytest.approx((at50 + 10000) * 1.04)                       # the extra tax is at most the extra income
    assert any("marginal relief" in s for s in e["steps"])


def test_surcharge_on_share_gains_is_capped_at_15_percent():
    e = est(other=1.5 * CR, salary=0, buckets=bk(st_new=1 * CR))                   # 2.5 crore, of which 1 crore gains
    slab = 300000 + (1.5 * CR - 24 * L) * 0.30
    assert e["surcharge_rate"] == 0.15                                              # income without the gains is under 2 crore
    assert e["total"] == pytest.approx((slab + 2000000) * 1.15 * 1.04)
    big = est(other=2.5 * CR, salary=0, buckets=bk(st_new=1 * CR))                  # without the gains, over 2 crore
    slab = 300000 + (2.5 * CR - 24 * L) * 0.30
    assert big["surcharge_rate"] == 0.25
    assert big["surcharge"] == pytest.approx(slab * 0.25 + 2000000 * 0.15)


# ---------- regimes ----------
def test_switching_regime():
    new = est(other=10 * L, deductions=1.5 * L)
    old = est(regime="old", other=10 * L, deductions=1.5 * L)
    assert new["regime"] == "new" and new["total"] == 0 and new["income"]["deductions"] == 0
    assert any("new regime allows almost no deductions" in s for s in new["steps"])
    assert old["income"]["normal"] == 8 * L and old["total"] == pytest.approx(72500 * 1.04)
    # deductions never cut gains taxed at special rates
    capped = est(regime="old", other=1 * L, salary=0, deductions=5 * L, buckets=bk(st_new=6 * L))
    assert capped["income"]["deductions"] == 1 * L and capped["income"]["special"] == 6 * L


def test_inputs_are_cleaned():
    c = X.clean({"regime": "sideways", "other": -5, "salary": float("nan"), "deductions": 1e30})
    assert c == {"regime": "new", "other": 0.0, "salary": None, "deductions": X.MAX_AMOUNT, "age": "below60",
                 "resident": True, "saved": True}
    assert X.clean({"age": "70", "resident": "no"})["age"] == "below60" and X.clean({"resident": "no"})["resident"] is True
    assert X.clean({"age": "80plus", "resident": False})["resident"] is False
    assert X.clean({"other": 100, "salary": 500})["salary"] == 100                  # salary can't be more than the whole
    assert X.clean(None)["regime"] == "new" and X.clean({"other": True})["other"] == 0


# ---------- losses ----------
def test_speculative_loss_only_against_speculative_income():
    e = est(other=5 * L, salary=5 * L, intraday=-1 * L, business=2 * L)
    assert e["carry_forward"]["speculative"] == 1 * L
    assert e["income"]["normal"] == 5 * L - 75000 + 2 * L                           # the business profit stays whole
    assert any("carried forward (up to 4 years)" in s for s in e["steps"])


def test_business_loss_against_everything_but_salary_in_order():
    e = est(other=12 * L, salary=10 * L, intraday=50000, business=-3 * L, buckets=bk(st_new=1 * L))
    # 3L: 50k against intraday, 2L against interest, 50k against short-term gains
    assert e["carry_forward"]["business"] == 0
    assert e["income"]["normal"] == 10 * L - 75000 and e["income"]["special"] == 50000
    assert e["slab_tax"] == 32500 and e["rebate"] == 32500 and e["special_tax"] == 10000
    assert e["total"] == pytest.approx(10400)
    steps = " ".join(e["steps"])
    assert "against the intraday profit" in steps and "isn't salary" in steps and "short-term gains at 20%" in steps


def test_business_loss_never_against_salary_and_carried_forward():
    e = est(other=10 * L, business=-20 * L)
    assert e["carry_forward"]["business"] == 20 * L and e["income"]["normal"] == 10 * L - 75000
    assert any("carry forward" in s for s in e["steps"])
    # against the long-term exemption last, where it saves no tax
    lt = est(business=-2 * L, buckets=bk(exempt=1.25 * L, lt_new=2.25 * L))
    assert lt["income"]["special"] == 0 and lt["carry_forward"]["business"] == 0
    assert any("within the exemption" in s for s in lt["steps"])


def test_each_source_has_its_share_and_the_shares_add_up():
    e = est(other=30 * L, salary=20 * L, intraday=5 * L, business=10 * L, buckets=bk(st_new=4 * L))
    p = e["parts"]
    assert p["capital_gains"] == pytest.approx(80000 * 1.04)
    assert sum(p.values()) == pytest.approx(e["total"], abs=0.05)
    assert p["fno"] == pytest.approx(2 * p["intraday"], rel=1e-6)                   # by slab income: 10L against 5L


def test_the_breakdown_and_steps_are_plain():
    e = est(regime="old", other=9 * L, deductions=50000, intraday=-2000, business=3000)
    assert e["lines"][-1]["kind"] == "total" and e["lines"][-1]["amount"] == e["total"]
    assert all(isinstance(s, str) and s.endswith(".") for s in e["steps"])
    text = " ".join(e["steps"]).lower()
    for word in ("you should", "we suggest", "better", "recommend", "choose", "switch"):
        assert word not in text


def test_never_nan_on_odd_inputs():
    for other in (0, 1, 1e11):
        for b in (-1e11, 0, 1e11):
            for regime in ("new", "old"):
                e = est(regime=regime, other=other, business=b, intraday=-b, buckets=bk(st_new=1e9, lt_new=1e9, exempt=125000))
                assert math.isfinite(e["total"]) and e["total"] >= 0


def test_filing_facts():
    assert X.filing_facts(2025, 0, False) == []
    f = " ".join(X.filing_facts(2025, 12345678, True))
    assert "ITR-3" in f and "₹1 crore" in f and "₹10 crore" in f and "FY 2020-21" in f and "₹1,23,45,678" in f
    assert "Income-tax Act, 2025" in " ".join(X.filing_facts(2026, 1, True))


# ---------- through the app ----------
PRO, FREE = world.headers("pro-token"), world.headers("free-token")
EXITS = "Tradewise Exits from 2024-04-01 to 2025-03-31-"


@pytest.fixture
def w(monkeypatch):
    built = world.build(monkeypatch)
    yield built
    built["close"]()


def send(c, data: bytes, name: str, mode: str = "add", headers=PRO):
    return c.post("/tax/import", params={"filename": name, "mode": mode}, headers={**headers, "Content-Type": "application/octet-stream"},
                  content=data)


def fno(rows: list[list]) -> bytes:
    return M._csv([M.DERIV_HEAD] + rows).encode()


def line(exit_day: str, pnl: float, sym: str = "NIFTY24SEP25000CE") -> list:
    return [sym, exit_day, exit_day, 25, 1000, 1000 + pnl, pnl, abs(pnl)] + [0] * 9


def year_of(rep: dict, fy: int) -> dict:
    return next(y for y in rep["years"] if y["fy"] == fy)


def test_inputs_are_saved_per_user_and_year_and_change_the_estimate(w):
    c = w["client"]
    assert send(c, M.zerodha_tax_zip(), "taxpnl.zip").status_code == 200
    y = year_of(c.get("/tax", headers=PRO).json(), 2024)
    assert y["inputs"] == {"regime": "new", "other": 0.0, "salary": None, "deductions": 0.0, "age": "below60",
                           "resident": True, "saved": False}
    assert y["total"]["available"] and y["other_regime"]["regime"] == "old"
    assert "ITR-3" in " ".join(y["filing"])
    r = c.put("/tax/inputs", headers=PRO, json={"fy": 2024, "regime": "old", "other": 1500000, "salary": 1200000, "deductions": 150000})
    assert r.status_code == 200
    y = year_of(r.json(), 2024)
    assert y["inputs"]["regime"] == "old" and y["inputs"]["saved"] and y["total"]["regime"] == "old"
    assert y["total"]["income"]["deductions"] == 150000 and y["other_regime"]["regime"] == "new"
    assert y["total"]["total"] > 0 and sum(y["total"]["parts"].values()) == pytest.approx(y["total"]["total"], abs=0.05)
    this = r.json()["current_fy"]
    assert year_of(r.json(), this)["inputs"]["saved"] is False                         # per year
    assert year_of(c.get("/tax", headers=FREE).json(), this)["inputs"]["saved"] is False  # per user
    r = c.put("/tax/inputs", headers=PRO, json={"fy": 2024, "other": 1000000, "salary": 0, "age": "80plus", "resident": False})
    y = year_of(r.json(), 2024)
    assert y["inputs"]["age"] == "80plus" and y["inputs"]["resident"] is False and y["total"]["rebate"] == 0
    assert X.NRI_TDS in y["total"]["notes"]
    for bad in ({"fy": 2024, "regime": "both"}, {"fy": 2024, "other": -1}, {"fy": 1990}, {"fy": 2024, "other": 1e13}, {},
                {"fy": 2024, "age": "senior"}, {"fy": 2024, "resident": "maybe"}):
        assert c.put("/tax/inputs", headers=PRO, json=bad).status_code == 422
    assert c.put("/tax/inputs", json={"fy": 2024}).status_code == 401
    assert db.get_setting("taxinputs:u-pro")
    c.delete("/tax", headers=PRO)
    assert db.get_setting("taxinputs:u-pro") is None


def test_fno_files_merge_by_their_dates(w):
    c = w["client"]
    q1 = send(c, fno([line("2024-05-10", 1000), line("2024-06-20", -300)]), EXITS + "F&O.csv").json()
    assert q1["business"] == {"lines": 2, "added": 1, "replaced": 0, "same": 0, "years": [2024]}
    q3 = send(c, fno([line("2024-10-10", 500)]), "Tradewise Exits Q3-F&O.csv").json()       # the next quarter: added
    assert q3["business"]["added"] == 1
    y = year_of(q3["report"], 2024)
    assert y["business"]["pnl"] == 1200 and y["business"]["trades"] == 3 and q3["report"]["business_lines"] == 3
    whole = send(c, fno([line("2024-05-10", 1000), line("2024-06-20", -300), line("2024-10-10", 500), line("2025-02-03", 50)]),
                 EXITS + "F&O.csv").json()                                                   # the full year: replaces both
    assert whole["business"]["replaced"] == 1
    y = year_of(whole["report"], 2024)
    assert y["business"]["pnl"] == 1250 and y["business"]["trades"] == 4
    again = send(c, fno([line("2024-05-10", 1000), line("2024-06-20", -300), line("2024-10-10", 500), line("2025-02-03", 50)]),
                 EXITS + "F&O.csv").json()
    assert again["business"]["same"] == 1 and year_of(again["report"], 2024)["business"]["pnl"] == 1250
    # the F&O lines alone make a year with a total tax estimate
    assert y["total"]["available"] and y["total"]["income"]["normal"] == pytest.approx(1250)
    # a 31 Jan 2018 price saved later keeps the F&O totals
    assert year_of(c.get("/tax", headers=PRO).json(), 2024)["business"]["pnl"] == 1250
    # starting again with an equity file drops them
    rep = send(c, M._csv(M.TAX_SHORT).encode(), "short.csv", mode="replace").json()["report"]
    assert year_of(rep, 2024)["business"]["segments"] == [] and rep["business_lines"] == 0


def test_the_fmv_and_the_inputs_keep_the_fno_totals(w):
    c = w["client"]
    send(c, M.zerodha_tax_zip(), "taxpnl.zip")
    r = c.put("/tax/fmv", headers=PRO, json={"symbol": "WIPRO", "fmv": 320})
    assert r.status_code == 200 and year_of(r.json(), 2024)["business"]["net"] == pytest.approx(48.69)
    r = c.put("/tax/inputs", headers=PRO, json={"fy": 2024, "other": 100000})
    assert len(year_of(r.json(), 2024)["business"]["segments"]) == 3


def test_a_big_fno_file_gets_its_own_limit(w):
    c = w["client"]
    big = fno([line("2024-05-10", 10)] * 150000)                                              # ~12 MB: over 10, under 20
    assert 10 * 1024 * 1024 < len(big) < 20 * 1024 * 1024
    assert send(c, big, EXITS + "F&O.csv").status_code == 200
    r = send(c, big, "tradebook.csv")
    assert r.status_code == 413 and "10 MB" in r.json()["detail"]["message"]
    r = send(c, b"x" * (holdings_file.FNO_MAX_BYTES + 1), EXITS + "F&O.csv")
    assert r.status_code == 413 and "20 MB" in r.json()["detail"]["message"]


def test_exports_carry_the_total(w):
    c = w["client"]
    send(c, M.zerodha_tax_zip(), "taxpnl.zip")
    c.put("/tax/inputs", headers=PRO, json={"fy": 2024, "other": 900000, "salary": 900000})
    text = c.get("/tax/export?fy=2024&format=csv", headers=PRO).text
    for want in ("Total tax estimate", "How we got here", "Estimated total tax", "Share of the total: F&O", "F&O: charges",
                 "Regime,New regime", "Age band,below 60", "Resident in India,Yes", "ITR-3", "advance tax and TDS",
                 "only the income you enter or import"):
        assert want in text, want
    pdf = c.get("/tax/export?fy=2024&format=pdf", headers=PRO)
    from pypdf import PdfReader
    import io
    words = " ".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf.content)).pages)
    assert "Total tax estimate" in words and "How we got here" in words and "Returns and tax audit" in words
    c.put("/tax/inputs", headers=PRO, json={"fy": 2024, "other": 900000, "age": "60to79", "resident": False})
    text = c.get("/tax/export?fy=2024&format=csv", headers=PRO).text
    assert "Age band,60 to 79" in text and "Resident in India,No" in text and "does not reconcile TDS" in text
    pdf = c.get("/tax/export?fy=2024&format=pdf", headers=PRO)
    words = " ".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf.content)).pages)
    assert "reconcile TDS" in words.replace("\n", " ")
    # a year outside the tables still downloads, saying so
    assert "covers FY 2020-21" in c.get("/tax/export?fy=2010&format=csv", headers=PRO).text


def test_the_page_says_no_advice_and_no_provider(w):
    c = w["client"]
    send(c, M.zerodha_tax_zip(), "taxpnl.zip")
    import json
    text = json.dumps(c.get("/tax", headers=PRO).json()).lower()
    for bad in ("yahoo", "kite", "screener", "finnhub", "you should", "we suggest", "recommend", "better off", "switch to"):
        assert bad not in text, bad
    assert "advance tax and tds" in text and "slab tax depends on your full income" in text


# ---------- age and residency ----------
@pytest.mark.parametrize("age,old_tax,old_bel", [("below60", 32500, 250000), ("60to79", 30000, 300000), ("80plus", 20000, 500000)])
def test_age_bands_change_only_the_old_regime(age, old_tax, old_bel):
    old = est(regime="old", other=6 * L, salary=0, age=age)                     # over the 5L rebate limit
    assert old["slab_tax"] == old_tax and old["rebate"] == 0 and old["total"] == pytest.approx(old_tax * 1.04)
    assert X.basic_exemption(X.rules(2025, "old", age)["slabs"]) == old_bel
    assert any(X.money(old_bel) in st for st in old["steps"])
    new = est(other=13 * L, salary=0, age=age)                                   # the same at every age
    assert new["slab_tax"] == 75000 and new["total"] == pytest.approx(78000)
    for fy in range(2020, 2027):
        assert X.rules(fy, "new", age)["slabs"] == X.rules(fy, "new")["slabs"]
        assert X.rules(fy, "old", age)["slabs"] == X.rules(2025, "old", age)["slabs"]


@pytest.mark.parametrize("age", ["60to79", "80plus"])
def test_seniors_old_regime_rebate_and_unused_exemption(age):
    assert est(regime="old", other=5 * L, salary=0, age=age)["total"] == 0
    # 2L of interest and 4L of short-term gains: the senior's higher limit is set against the gains
    e = est(regime="old", other=2 * L, salary=0, age=age, buckets=bk(st_new=4 * L))
    bel = 3 * L if age == "60to79" else 5 * L
    assert e["special_tax"] == pytest.approx((6 * L - bel) * 0.20)


def test_non_resident_gets_no_rebate_at_any_age_and_the_basic_limit():
    for fy in (2020, 2023, 2024, 2025, 2026):
        r = X.rules(fy, "new", resident=False)
        assert r["rebate_limit"] == 0 and r["bel_on_gains"] is False
    nri = est(other=10 * L, salary=0, resident=False)                             # FY 2025-26, new: 40,000, no rebate
    assert nri["rebate"] == 0 and nri["total"] == pytest.approx(41600)
    assert est(other=10 * L, salary=0)["total"] == 0                                # resident: all rebated
    # the old regime's higher limits for 60 and over are for residents only
    for age in ("60to79", "80plus"):
        assert X.basic_exemption(X.rules(2025, "old", age, resident=False)["slabs"]) == 250000
        assert est(regime="old", other=6 * L, salary=0, age=age, resident=False)["slab_tax"] == 32500
    assert est(regime="old", other=5 * L, salary=0, resident=False)["total"] == pytest.approx(12500 * 1.04)


def test_non_resident_cant_use_the_unused_limit_against_111a_or_112a():
    st = est(buckets=bk(st_new=5 * L), resident=False)
    assert st["special_tax"] == 100000 and st["total"] == pytest.approx(104000)
    assert any("as a non-resident the unused part" in x for x in st["steps"])
    lt = est(buckets=bk(exempt=1.25 * L, lt_new=3.25 * L), resident=False)        # the ₹1.25 lakh exemption still applies
    assert lt["special_tax"] == 25000 and lt["total"] == pytest.approx(26000)
    assert est(buckets=bk(exempt=1.25 * L, lt_new=3.25 * L))["total"] == 0         # resident: the 4L limit covers it


def test_non_resident_surcharge_and_cess_as_usual_and_the_tds_note():
    nri, res = est(other=60 * L, salary=0, resident=False), est(other=60 * L, salary=0)
    assert nri["surcharge"] > 0 and nri["total"] == pytest.approx(res["total"]) and nri["surcharge_rate"] == 0.10
    assert X.NRI_TDS in nri["notes"] and res["notes"] == []
    assert nri["notes"][0] == "TDS on NRI sales is deducted by the broker; this estimate does not reconcile TDS."
    big = est(other=3 * CR, salary=0, buckets=bk(st_new=1 * CR), resident=False)  # 15% cap on the gains' surcharge too
    assert big["surcharge_rate"] == 0.25


def test_switching_regime_keeps_age_and_residency():
    from app import tax_lots as T
    y = {"fy": 2025, "buckets": [], "intraday": {"pnl": 0, "count": 0, "turnover": 0}}
    out = T.with_total(y, [], {"regime": "new", "other": 6 * L, "salary": 0, "age": "80plus", "resident": True})
    assert out["inputs"]["age"] == "80plus" and out["other_regime"]["total"] == pytest.approx(20800)


# ---------- the FY 2024-25 split by sale date ----------
def test_fy2024_split_by_sale_date_flows_into_the_total():
    from app import tax_lots as T

    def t(d, side, qty, price, sym):
        return {"d": d, "side": side, "qty": qty, "price": price, "sym": sym}
    trades = [t("2024-04-02", "B", 2, 100, "S"), t("2024-07-22", "S", 1, 100_100, "S"), t("2024-07-23", "S", 1, 100_100, "S"),
              t("2022-01-03", "B", 2, 100, "L"), t("2024-07-22", "S", 1, 200_100, "L"), t("2024-07-23", "S", 1, 200_100, "L")]
    c = T.compute(trades, today="2026-10-04")
    y = T.year(2024, c["realised"], c["intraday"])
    got = {b["key"]: b for b in y["buckets"]}
    # 1,00,000 short-term and 2,00,000 long-term each side of 23 July
    assert got["lt_old"]["rate"] == 0.10 and got["lt_new"]["rate"] == 0.125
    assert got["st_old"]["rate"] == 0.15 and got["st_new"]["rate"] == 0.20
    assert got["st_old"]["taxable"] == 100_000 and got["st_new"]["taxable"] == 100_000
    assert y["exemption"]["limit"] == 125000                                       # ₹1.25 lakh for the whole year
    assert got["lt_new"]["exempt"] == 125_000 and got["lt_old"]["exempt"] == 0       # against the 12.5% gains first
    e = X.estimate(2024, {"regime": "new", "other": 20 * L, "salary": 0}, y["buckets"], 0, 0)
    want = sum(b["taxable"] * b["rate"] for b in y["buckets"])
    assert e["special_tax"] == pytest.approx(want)


def test_every_year_is_confirmed_with_a_source_and_an_unconfirmed_one_says_so(monkeypatch):
    for fy in range(X.FIRST_FY, X.LAST_FY + 1):
        r = X.rules(fy, "new")
        assert r["confirmed"] and r["source"].startswith("https://")
        assert est(fy=fy, other=10 * L)["notes"] == ([X.NEW_ACT_NOTE] if fy >= 2026 else [])
    monkeypatch.delitem(X.YEAR_SOURCES, 2026)
    e = est(fy=2026, other=10 * L)
    assert e["confirmed"] is False and "Rules for this year not yet confirmed" in e["notes"][0]
