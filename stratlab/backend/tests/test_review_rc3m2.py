"""RC3-M2: the Money findings RC3-M left open (RC3M-007 to RC3M-011), each fixed at the root. Each test names its finding."""
import pytest

from app import cii, instrument_kinds as I, money_itr, tax_export, tax_lots as T, tax_total
from tests.test_instrument_kinds import lots

TODAY = "2025-10-01"


def year(trades, fy, other=20 * 100000):
    inputs = {fy: {"regime": "new", "other": other, "salary": 0}}
    return next(y for y in T.report(trades, {}, {}, {}, [], TODAY, inputs=inputs)["years"] if y["fy"] == fy)


def plain_tax(fy, other=20 * 100000):
    return tax_total.estimate(fy, {"regime": "new", "other": other, "salary": 0}, [], 0, 0)["total"]


# ---------- RC3M-007: long-term gains under the old rules are worked out ----------
def test_the_cost_inflation_index_table_is_the_published_series():
    assert sorted(cii.CII) == list(range(2001, 2026))
    assert (cii.CII[2001], cii.CII[2010], cii.CII[2017], cii.CII[2020], cii.CII[2023], cii.CII[2024]) == (100, 167, 272, 301, 348, 363)
    assert all(b > a for a, b in zip(list(cii.CII.values()), list(cii.CII.values())[1:]))     # the index only rises
    assert cii.ratio(2020, 2024) == pytest.approx(363 / 301)
    assert cii.ratio(2000, 2024) is None and cii.ratio(2020, 2030) is None


def test_a_gold_etf_held_over_36_months_and_sold_before_23_jul_2024_is_taxed_at_20_percent_on_the_indexed_gain():
    # bought FY 2018-19 (index 280), sold FY 2022-23 (331): 10 units at 100 cost 1,000, sold at 150
    y = year(lots("GOLDBEES", "", "2019-01-10", "2023-03-01", qty=1000, bp=100, sp=150), 2022)
    row = y["units"]["rows"][0]
    assert row["head"] == "lt_idx" and row["gain"] == 50000 and row["indexed_cost"] == pytest.approx(100000 * 331 / 280, abs=0.01)
    assert row["taxed_gain"] == pytest.approx(150000 - 100000 * 331 / 280, abs=0.01)
    assert "× 331/280" in row["why"] and "FY 2022-23 over FY 2018-19" in row["why"] and "not units" in row["why"]
    gain = 150000 - 100000 * 331 / 280
    assert [b["key"] for b in y["buckets"]] == ["lt_uniti"] and y["buckets"][0]["rate"] == 0.20
    assert y["units"]["old"] is None and y["units"]["lt_idx"]["taxable"] == pytest.approx(gain, abs=0.01)
    assert y["total"]["total"] == pytest.approx(plain_tax(2022) + gain * 0.20 * 1.04, abs=0.5)      # in the total, with cess


def test_a_debt_etf_bought_before_april_2023_is_indexed_and_one_bought_after_is_slab():
    y = year(lots("LIQUIDBEES", "", "2019-01-10", "2024-03-01", qty=100, bp=1000, sp=1500), 2023)
    assert y["units"]["rows"][0]["head"] == "lt_idx"
    assert y["units"]["rows"][0]["indexed_cost"] == pytest.approx(100000 * 348 / 280, abs=0.01)
    y = year(lots("LIQUIDBEES", "", "2023-04-01", "2024-07-01", qty=100, bp=1000, sp=1500), 2024)       # section 50AA
    assert y["units"]["rows"][0]["head"] == "slab" and y["buckets"][0]["key"] == "st_unit"


def test_a_gold_bond_pays_the_lower_of_20_percent_indexed_and_10_percent_plain():
    # indexation cuts the gain a lot: 20% of 2,192.69 = 438.54 against 10% of 10,000 = 1,000
    y = year(lots("SGBMAY29I", "", "2020-06-01", "2023-12-01", qty=10, bp=5000, sp=6000), 2023)
    r = y["units"]["rows"][0]
    assert r["head"] == "lt_idx" and r["indexed_cost"] == pytest.approx(50000 * 348 / 301, abs=0.01)
    assert "the lower is 20% with indexation (proviso to section 112(1))" in r["why"]
    assert y["total"]["total"] == pytest.approx(plain_tax(2023) + (60000 - 50000 * 348 / 301) * 0.20 * 1.04, abs=0.5)
    # a small index step: 20% of 7,342 = 1,468 against 10% of 10,000 = 1,000, so 10% without indexation
    y = year(lots("SGBMAY29I", "", "2020-06-01", "2021-12-01", qty=10, bp=5000, sp=6000), 2021)
    r = y["units"]["rows"][0]
    assert r["head"] == "lt_10" and r["taxed_gain"] == 10000 and "the lower is 10% without indexation" in r["why"]
    assert [(b["key"], b["rate"], b["taxable"]) for b in y["buckets"]] == [("lt_unit10", 0.10, 10000)]
    assert y["units"]["lt_10"]["tax"] == 1000 and y["units"]["lt_idx"] is None
    # the 10% option is for listed securities other than units: a gold ETF with the same dates is 20% indexed whatever is lower
    y = year(lots("GOLDBEES", "", "2020-06-01", "2021-12-01", qty=10, bp=5000, sp=6000), 2021)       # held only 18 months: slab
    assert y["units"]["rows"][0]["head"] == "slab"
    y = year(lots("GOLDBEES", "", "2017-06-01", "2021-12-01", qty=10, bp=5000, sp=6000), 2021)
    assert y["units"]["rows"][0]["head"] == "lt_idx" and y["units"]["lt_10"] is None


def test_indexation_can_turn_a_gain_into_a_loss_and_a_gold_bond_then_has_no_tax():
    # cost 50,000 x 348/301 = 57,807; sold at 55,000 is a gain of 5,000 on the plain cost but a loss once indexed
    y = year(lots("SGBMAY29I", "", "2020-06-01", "2023-12-01", qty=10, bp=5000, sp=5500), 2023)
    r = y["units"]["rows"][0]
    assert r["head"] == "lt_idx" and r["gain"] == 5000 and r["taxed_gain"] < 0
    assert y["units"]["lt_idx"]["losses"] == pytest.approx(57807.31 - 55000, abs=0.01) and y["units"]["lt_idx"]["tax"] == 0
    assert y["carry_forward"]["lt"] == pytest.approx(57807.31 - 55000, abs=0.01)


def test_old_rule_losses_are_set_off_against_the_highest_rate_gains_first():
    trades = (lots("GOLDBEES", "", "2018-06-01", "2023-06-02", qty=1000, bp=100, sp=200) +          # indexed gain at 20%
              lots("SILVERBEES", "", "2018-06-01", "2023-06-02", qty=100, bp=100, sp=50) +          # indexed loss
              lots("SGBMAY29I", "", "2022-06-01", "2023-08-01", qty=10, bp=5000, sp=6000))          # bond gain, lower tax at 10%
    y = year(trades, 2023)
    g = {x["key"]: x for x in y["units"]["rows"]}
    assert (g["GOLDBEES"]["head"], g["SILVERBEES"]["head"], g["SGBMAY29I"]["head"]) == ("lt_idx", "lt_idx", "lt_10")
    gold, silver = g["GOLDBEES"]["taxed_gain"], g["SILVERBEES"]["taxed_gain"]
    assert gold > 0 > silver
    u = y["units"]
    assert u["lt_idx"]["taxable"] == pytest.approx(gold + silver, abs=0.01) and u["lt_10"]["taxable"] == 10000
    assert y["carry_forward"] == {"st": 0, "lt": 0}
    assert {b["key"]: b["taxable"] for b in y["buckets"]} == {"lt_uniti": pytest.approx(gold + silver, abs=0.01), "lt_unit10": 10000}


def test_a_sale_whose_cost_cannot_be_indexed_stays_not_worked_out_with_the_reason():
    w = I.old_rules("etf-gold", "1999-05-01", "2023-05-01", 1000.0, 3000.0)
    assert w["head"] == "old" and "1 April 2001" in w["why"] and "Not worked out" in w["why"] and w["gain"] == 2000.0
    r = {"key": "GOLDBEES", "fy": 2023, "bought": "1999-05-01", "sold": "2023-05-01", "qty": 1, "cost": 1000.0, "sale": 3000.0, "gain": 2000.0}
    assert I.bucket_rows([r], {}) == []                                   # not in the total, and said so
    out = I.other_year(2023, [r], {"GOLDBEES": {"symbol": "GOLDBEES", "name": "Gold BeES"}})
    assert out["old"] == 2000.0 and out["rows"][0]["head"] == "old"


def test_the_old_rule_heads_reach_the_exports_and_the_return():
    keys = {k for k, _, _ in T.BUCKETS}
    assert keys <= set(money_itr.SECTIONS)                                  # a row for every bucket in Schedule CG
    assert keys - {"st_new", "st_old", "lt_new", "lt_old"} <= set().union(*(s for _, s in money_itr.F_GROUPS))
    y = year(lots("SGBMAY29I", "", "2020-06-01", "2021-12-01", qty=10, bp=5000, sp=6000), 2021)
    names = {"SGBMAY29I": {"symbol": "SGBMAY29I", "name": "SGB"}}
    csv = tax_export.to_csv(y, [], names)
    assert "Long-term, 10% without indexation (section 112 proviso)" in csv and "KeyError" not in csv


def test_the_unit_rules_note_says_what_is_worked_out_and_what_is_not():
    note = next(n for n in I.NOTES if "Cost Inflation Index" in n)
    assert "20% on the gain after indexing" in note and "lower of 20% with indexation and 10% without it" in note
    assert "units have no 10% option" in note and "stays marked as not worked out" in note


# ---------- RC3M-008: the 15% surcharge cap on section 112 gains starts in FY 2022-23 ----------
def surcharge_case(fy, bucket, gain=2_000_000):
    """2.5 crore of other income and a gain of 20 lakh in one 20% bucket (old regime): the slab part pays 25% surcharge in
    every year, the gains' tax 15% where capped."""
    b = [{"key": bucket, "rate": 0.20, "after_setoff": gain, "exempt": 0.0, "taxable": gain, "tax": gain * 0.2}]
    return tax_total.estimate(fy, {"regime": "old", "other": 25_000_000, "salary": 0}, b, 0, 0)


def test_section_112_gains_pay_the_full_surcharge_before_fy_2022_23_and_the_capped_one_after():
    for fy, capped in ((2020, False), (2021, False), (2022, True), (2023, True)):
        t = surcharge_case(fy, "lt_112i")
        assert t["surcharge_rate"] == 0.25
        gains_tax = 2_000_000 * 0.20
        slab_tax = t["slab_tax"]
        # slab tax + gains tax; surcharge at 25% on the slab tax, and on the gains' tax 15% when capped, else 25%
        expect = slab_tax * 0.25 + gains_tax * (0.15 if capped else 0.25)
        assert t["surcharge"] == pytest.approx(expect, abs=1.0), fy
        assert ("the 15% cap on those starts in FY 2022-23" in " ".join(t["steps"])) is (not capped), fy


def test_111a_and_112a_gains_and_dividends_stay_capped_in_every_year():
    for fy in (2020, 2021, 2022):
        for key in ("lt_new", "lt_old", "st_new"):
            t = surcharge_case(fy, key)
            assert t["surcharge"] == pytest.approx(t["slab_tax"] * 0.25 + 2_000_000 * 0.20 * 0.15, abs=1.0), (fy, key)
            assert "section 112 gains" not in " ".join(t["steps"])


def test_a_112_gain_does_not_count_as_special_income_for_the_25_percent_threshold_before_fy_2022_23():
    # 1.9 crore of other income and 30 lakh of 112 gains: total 2.2 crore. Section 112 gains count with the rest then, so the
    # income "other than special gains" is 2.2 crore, over the 2 crore threshold: 25%. A 112A gain is excluded: 1.9 crore, 15%.
    big = {"regime": "old", "other": 19_000_000, "salary": 0}
    g = lambda k: [{"key": k, "rate": 0.10, "after_setoff": 3_000_000, "exempt": 0.0, "taxable": 3_000_000, "tax": 300_000}]
    assert tax_total.estimate(2021, big, g("lt_usi"), 0, 0)["surcharge_rate"] == 0.25
    assert tax_total.estimate(2021, big, g("lt_old"), 0, 0)["surcharge_rate"] == 0.15
    assert tax_total.estimate(2023, big, g("lt_usi"), 0, 0)["surcharge_rate"] == 0.15      # capped from FY 2022-23


def test_the_surcharge_parts_add_up_with_uncapped_gains():
    t = surcharge_case(2021, "lt_usi")
    assert sum(t["parts"].values()) == pytest.approx(t["total"], abs=0.05)
    assert t["total"] == pytest.approx((t["slab_tax"] + t["special_tax"] + t["surcharge"]) * 1.04, abs=1.0)
