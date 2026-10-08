"""The total tax estimate for one financial year: slab tax on the user's other income, intraday (speculative) income
and F&O, commodity and currency (non-speculative business) income, the special rates on listed share gains (sections
111A and 112A), the section 87A rebate, surcharge and 4% cess, with the loss set-off rules between them.

The user gives these per year: the regime (new by default, or old), their other income (salary, interest and the
like, as one number, with how much of it is salary), under the old regime their deductions, their age band (below 60,
60 to 79, 80 and over) and whether they are resident in India. Everything else comes from the uploaded files.

Age only changes the old regime's basic exemption (₹2.5 lakh, ₹3 lakh for a resident aged 60 to 79, ₹5 lakh for a
resident aged 80 or more); the new regime's slabs are the same at every age. A non-resident gets ₹2.5 lakh at any age
under the old regime, no section 87A rebate (it is for residents only), and can't set the unused basic exemption
against gains taxed under sections 111A and 112A (the provisos there are for residents only); surcharge and cess are
as usual. Facts and arithmetic only; an estimate, never a view on which regime to pick or what to do.

Sources, checked year by year (YEAR_SOURCES names each year's own):
- Slabs, rebate and surcharge for AY 2026-27 (FY 2025-26), both regimes, by age and residency:
  https://www.incometax.gov.in/iec/foportal/help/individual/return-applicable-1 (salaried),
  https://www.incometax.gov.in/iec/foportal/help/individual/return-applicable-2 (senior and super senior citizens),
  https://www.incometax.gov.in/iec/foportal/help/individual/return-applicable-0 (non-residents: no 87A, ₹2.5 lakh
  at any age).
- Sections 111A and 112A (rates, the 23 July 2024 switch, the ₹1.25 lakh exemption, the residents-only proviso on the
  basic exemption): https://www.pib.gov.in/PressReleasePage.aspx?PRID=2036604 (CBDT FAQs on the Budget 2024-25
  capital gains changes) and https://www.incometaxindia.gov.in/w/tax-on-long-term-capital-gains%E2%80%8B."""
import json
import math

from . import db

KEY = "taxinputs:"                # taxinputs:<uid> = {"2025": {"regime", "other", "salary", "deductions", "age", "resident"}}
CESS = 0.04
SPECIAL_SC_CAP = 0.15             # surcharge on the tax on 111A and 112A gains is capped at 15%
MAX_AMOUNT = 1e11                 # ₹10,000 crore: anything typed above this is a mistake
FIRST_FY, LAST_FY = 2020, 2026

AGES = ("below60", "60to79", "80plus")
AGE_NAMES = {"below60": "below 60", "60to79": "60 to 79", "80plus": "80 or more"}
OLD_SLABS = [(250000, 0.0), (500000, 0.05), (1000000, 0.20), (math.inf, 0.30)]
OLD_SLABS_60 = [(300000, 0.0), (500000, 0.05), (1000000, 0.20), (math.inf, 0.30)]      # resident, 60 to 79
OLD_SLABS_80 = [(500000, 0.0), (1000000, 0.20), (math.inf, 0.30)]                      # resident, 80 or more
# new regime (section 115BAC) slabs: (up to, rate)
NEW_2020 = [(250000, 0.0), (500000, 0.05), (750000, 0.10), (1000000, 0.15), (1250000, 0.20), (1500000, 0.25), (math.inf, 0.30)]
NEW_2023 = [(300000, 0.0), (600000, 0.05), (900000, 0.10), (1200000, 0.15), (1500000, 0.20), (math.inf, 0.30)]
NEW_2024 = [(300000, 0.0), (700000, 0.05), (1000000, 0.10), (1200000, 0.15), (1500000, 0.20), (math.inf, 0.30)]
NEW_2025 = [(400000, 0.0), (800000, 0.05), (1200000, 0.10), (1600000, 0.15), (2000000, 0.20), (2400000, 0.25), (math.inf, 0.30)]
SURCHARGE = [(50000000, 0.37), (20000000, 0.25), (10000000, 0.15), (5000000, 0.10)]     # above, rate
NRI_TDS = "TDS on NRI sales is deducted by the broker; this estimate does not reconcile TDS."
# the Income-tax Act, 2025 renumbers the sections from tax year 2026-27 (FY 2026-27); the rules themselves are the same
NEW_SECTIONS = {"111A": "196", "112A": "198", "87A": "156", "115BAC": "202", "139": "263", "234B": "424", "234C": "425"}
NEW_ACT_NOTE = ("From 1 April 2026 the Income-tax Act, 2025 replaces the 1961 Act and renumbers its sections: "
                + ", ".join(f"{o} is now {n}" for o, n in NEW_SECTIONS.items()) + ". The rules used here are the same.")

# where each year's rules were checked; a year missing from here shows "rules for this year not yet confirmed"
YEAR_SOURCES = {
    2020: "https://www.indiabudget.gov.in/budget2020-21/doc/memo.pdf (Finance Act 2020: section 115BAC brought in, "
          "new slabs in 2.5 lakh steps; 87A ₹12,500 up to ₹5 lakh from Finance Act 2019; surcharge 37% above ₹5 crore)",
    2021: "https://www.indiabudget.gov.in/budget2021-22/doc/memo.pdf (Finance Act 2021: rates as FY 2020-21)",
    2022: "https://www.indiabudget.gov.in/budget2022-23/doc/memo.pdf (Finance Act 2022: rates as FY 2020-21)",
    2023: "https://www.pib.gov.in/PressReleasePage.aspx?PRID=1895286 (Budget 2023-24: new regime default, 3 lakh steps, "
          "87A up to ₹7 lakh, standard deduction ₹50,000 in the new regime, top surcharge 25% in it)",
    2024: "https://www.indiabudget.gov.in/budget2024-25/doc/Budget_Speech.pdf and "
          "https://www.pib.gov.in/PressReleasePage.aspx?PRID=2036604 (Budget July 2024: new slabs, standard deduction "
          "₹75,000; 111A 20% and 112A 12.5% from 23 July 2024, exemption ₹1.25 lakh for the whole FY 2024-25)",
    2025: "https://www.pib.gov.in/PressReleasePage.aspx?PRID=2098406 and "
          "https://www.incometax.gov.in/iec/foportal/help/individual/return-applicable-1 (Budget 2025-26: 4 lakh steps "
          "to ₹24 lakh, 87A ₹60,000 up to ₹12 lakh, not against special-rate income)",
    2026: "https://www.pib.gov.in/PressReleasePage.aspx?PRID=2221458 and https://www.indiabudget.gov.in/doc/memo.pdf "
          "(Budget 2026-27, Finance Act 2026: no change to slabs, rebate, surcharge or the 111A and 112A rates; the "
          "Income-tax Act, 2025 applies from 1 April 2026)",
}


def rules(fy: int, regime: str, age: str = "below60", resident: bool = True) -> dict | None:
    """The year's slabs, standard deduction, 87A rebate and surcharge cap for a regime, age band and residency, or
    None for a year not covered. `rebate_special`: whether the rebate can be used against tax on 111A gains (never
    112A). `bel_on_gains`: whether the unused basic exemption can be set against 111A and 112A gains."""
    r = _rules(fy, regime, age if resident else "below60")
    if r is None:
        return None
    if not resident:                  # section 87A and the 111A/112A provisos are for residents only
        r = {**r, "rebate_limit": 0, "rebate_max": 0, "marginal": False}
    return {**r, "bel_on_gains": resident, "confirmed": fy in YEAR_SOURCES, "source": YEAR_SOURCES.get(fy)}


def _rules(fy: int, regime: str, age: str) -> dict | None:
    if not FIRST_FY <= fy <= LAST_FY:
        return None
    if regime == "old":              # the higher limits are for resident senior and super senior citizens
        slabs = OLD_SLABS_80 if age == "80plus" else OLD_SLABS_60 if age == "60to79" else OLD_SLABS
        return {"slabs": slabs, "std": 50000, "rebate_limit": 500000, "rebate_max": 12500, "marginal": False,
                "rebate_special": True, "sc_cap": 0.37, "deductions": True}
    if fy >= 2025:                    # Budget 2025 (FY 2026-27: no slab change)
        return {"slabs": NEW_2025, "std": 75000, "rebate_limit": 1200000, "rebate_max": 60000, "marginal": True,
                "rebate_special": False, "sc_cap": 0.25, "deductions": False}
    if fy == 2024:                    # Budget July 2024
        return {"slabs": NEW_2024, "std": 75000, "rebate_limit": 700000, "rebate_max": 25000, "marginal": True,
                "rebate_special": True, "sc_cap": 0.25, "deductions": False}
    if fy == 2023:                    # Budget 2023: the new regime became the default
        return {"slabs": NEW_2023, "std": 50000, "rebate_limit": 700000, "rebate_max": 25000, "marginal": True,
                "rebate_special": True, "sc_cap": 0.25, "deductions": False}
    return {"slabs": NEW_2020, "std": 0, "rebate_limit": 500000, "rebate_max": 12500, "marginal": False,
            "rebate_special": True, "sc_cap": 0.37, "deductions": False}


def slab_tax(income: float, slabs: list[tuple[float, float]]) -> float:
    """Tax on income at the slab rates."""
    tax, low = 0.0, 0.0
    for top, rate in slabs:
        if income <= low:
            break
        tax += (min(income, top) - low) * rate
        low = top
    return tax


def basic_exemption(slabs: list[tuple[float, float]]) -> float:
    return slabs[0][0] if slabs[0][1] == 0 else 0.0


def surcharge_rate(total: float, special: float, cap: float) -> float:
    """The surcharge rate on the slab part: by total income, but the 25% and 37% rates only when income other than
    111A and 112A gains is itself over ₹2 crore and ₹5 crore."""
    for above, rate in SURCHARGE:
        rate = min(rate, cap)
        if total > above and (above < 20000000 or total - special > above):
            return rate
    return 0.0


# ---------- the user's inputs ----------
def _key(uid: str) -> str:
    return f"{KEY}{uid}"


def default_inputs() -> dict:
    return {"regime": "new", "other": 0.0, "salary": None, "deductions": 0.0, "age": "below60", "resident": True, "saved": False}


def clean(v: dict | None) -> dict:
    """Inputs as stored, each one checked: an unknown regime is the new one, amounts are 0 or more and capped, an
    unknown age band is below 60 and anything but an explicit false is resident."""
    v = v if isinstance(v, dict) else {}

    def amount(x, none_ok=False):
        if x is None and none_ok:
            return None
        if not isinstance(x, (int, float)) or isinstance(x, bool) or not math.isfinite(x) or x < 0:
            return None if none_ok else 0.0
        return round(min(float(x), MAX_AMOUNT), 2)
    other = amount(v.get("other"))
    salary = amount(v.get("salary"), none_ok=True)
    return {"regime": "old" if v.get("regime") == "old" else "new", "other": other,
            "salary": None if salary is None else min(salary, other), "deductions": amount(v.get("deductions")),
            "age": v.get("age") if v.get("age") in AGES else "below60", "resident": v.get("resident") is not False,
            "saved": bool(v.get("saved", True))}


def load_inputs(uid: str) -> dict[int, dict]:
    got = db.json_value(db.get_setting(_key(uid)), {})
    got = got if isinstance(got, dict) else {}
    out = {}
    for k, v in got.items():
        if str(k).isdigit() and 2000 <= int(k) <= 2100:
            out[int(k)] = clean(v)
    return out


def save_inputs(uid: str, fy: int, v: dict):
    allv = {str(k): x for k, x in load_inputs(uid).items()}
    allv[str(fy)] = {**clean(v), "saved": True}
    db.set_setting(_key(uid), json.dumps(allv, separators=(",", ":")))


def delete_inputs(uid: str):
    db.delete_setting(_key(uid))


# ---------- the estimate ----------
def money(v: float) -> str:
    from .tax_lots import money as m
    return m(v)


def _pct(r: float) -> str:
    return f"{r * 100:g}%"


def _base(normal: float, gains: dict[str, float], g_rates: dict[str, float], total: float, r: dict) -> dict:
    """Slab tax, special-rate tax and the 87A rebate for one set of incomes (before surcharge and cess)."""
    gains = dict(gains)
    shortfall = max(0.0, basic_exemption(r["slabs"]) - normal) if r.get("bel_on_gains", True) else 0.0
    used_bel = {}
    for b in sorted(gains, key=lambda b: -g_rates[b]):     # the unused basic exemption against the highest rate first
        take = min(gains[b], shortfall)
        if take > 0:
            gains[b] -= take
            shortfall -= take
            used_bel[b] = take
    slab = slab_tax(normal, r["slabs"])
    special = {b: gains[b] * g_rates[b] for b in gains}
    st_tax = sum(v for b, v in special.items() if b.startswith("st"))
    eligible = slab + (st_tax if r["rebate_special"] else 0.0)
    rebate = 0.0
    if r["rebate_limit"]:
        if total <= r["rebate_limit"]:
            rebate = min(eligible, r["rebate_max"])
        elif r["marginal"]:          # just over the limit: the tax it covers is at most the income over the limit
            rebate = max(0.0, eligible - (total - r["rebate_limit"]))
    rebate_slab = min(rebate, slab)
    return {"slab": slab, "special": special, "special_total": sum(special.values()), "rebate": rebate,
            "rebate_slab": rebate_slab, "used_bel": used_bel, "gains": gains}


def _with_surcharge(b: dict, total: float, special_income: float, cap: float) -> tuple[float, float, float]:
    """(tax before surcharge, surcharge, rate on the slab part)."""
    rate = surcharge_rate(total, special_income, cap)
    tax_slab = b["slab"] - b["rebate_slab"]
    tax_special = b["special_total"] - (b["rebate"] - b["rebate_slab"])
    sc = tax_slab * rate + tax_special * min(rate, SPECIAL_SC_CAP)
    return tax_slab + tax_special, sc, rate


def estimate(fy: int, inputs: dict, buckets: list[dict], intraday: float, business: float,
             dividends: float = 0.0, slab_gains: float = 0.0) -> dict:
    """The year's total tax estimate.

    `buckets` are the capital gains year's buckets (key, rate, after_setoff, exempt, taxable); `intraday` the
    speculative profit or loss; `business` the F&O, commodity and currency profit or loss after charges;
    `dividends` the year's dividend income (income from other sources, at slab rates), when the user includes it; `slab_gains` short-term gains taxed at slab rates (gold, debt and other
    non-equity ETFs and gold bonds, after their own set-off). Returns the steps in plain words, a breakdown table and
    the total."""
    v = clean(inputs)
    r = rules(fy, v["regime"], v["age"], v["resident"])
    if r is None:
        return {"available": False, "regime": v["regime"], "inputs": v,
                "reason": f"The total tax estimate covers FY {FIRST_FY}-{str(FIRST_FY + 1)[2:]} to FY {LAST_FY}-{str(LAST_FY + 1)[2:]}."}
    steps: list[str] = []
    lines: list[dict] = []
    notes: list[str] = []
    if not r["confirmed"]:
        notes.append(f"Rules for this year not yet confirmed: the FY {fy}-{str(fy + 1)[2:]} figures repeat the year before "
                     "until they are checked against the Finance Act.")
    if fy >= 2026:
        notes.append(NEW_ACT_NOTE)
    who = f"{'Resident' if v['resident'] else 'Non-resident'} individual, aged {AGE_NAMES[v['age']]}"
    bel = basic_exemption(r["slabs"])
    if v["regime"] == "old":
        steps.append(f"{who}: the old regime's basic exemption is {money(bel)}"
                     + ("." if v["resident"] or v["age"] == "below60" else " (the higher limits from 60 are for residents only)."))
    else:
        steps.append(f"{who}: the new regime's slabs are the same at every age, with {money(bel)} not taxed.")
    if not v["resident"]:
        steps.append("Non-resident: no section 87A rebate, and the unused basic exemption can't be set against share "
                     "gains taxed under sections 111A and 112A. Surcharge and cess apply as usual.")
        notes.append(NRI_TDS)

    def line(label, amount, kind="amount"):
        lines.append({"label": label, "amount": round(amount, 2), "kind": kind})

    salary = v["other"] if v["salary"] is None else v["salary"]
    rest = max(0.0, v["other"] - salary) + max(0.0, slab_gains)
    std = min(r["std"], salary)
    if v["other"]:
        steps.append(f"Other income you entered: {money(v['other'])}" + (f", of which {money(salary)} is salary or pension." if salary else ", none of it salary.")
                     + (" All of it is taken as salary, as you didn't say how much is." if v["salary"] is None and salary else ""))
    div = max(0.0, min(float(dividends or 0.0), MAX_AMOUNT)) if isinstance(dividends, (int, float)) and math.isfinite(dividends) else 0.0
    if div:
        rest += div
        steps.append(f"Dividends of {money(div)} are income from other sources, taxed at your slab rate (from Tax tools, where they can be left out).")
    if slab_gains > 0:
        steps.append(f"Short-term gains on ETFs and gold bonds taxed at slab rates: {money(slab_gains)}.")
    if std:
        steps.append(f"Standard deduction of {money(std)} on salary ({v['regime']} regime, {money(r['std'])} at most).")

    # mutual fund gains taxed at the slab rate (money_mf.py) are slab income, not special-rate gains
    slab_mf = sum(max(0.0, b.get("taxable") or 0.0) for b in buckets if b.get("slab") and b["key"] != "st_us")
    slab_us = sum(max(0.0, b.get("taxable") or 0.0) for b in buckets if b.get("slab") and b["key"] == "st_us")
    slab_cg = slab_mf + slab_us
    buckets = [b for b in buckets if not b.get("slab")]
    if slab_mf:
        steps.append(f"Mutual fund gains taxed at your slab rate (debt funds and the like, after set-off): {money(slab_mf)}, "
                     "added to the income taxed at slab rates.")
    if slab_us:
        steps.append(f"Short-term gains on foreign shares (held 24 months or less), after set-off: {money(slab_us)}, "
                     "added to the income taxed at slab rates.")
    rest += slab_cg
    g_rates = {b["key"]: b["rate"] for b in buckets}
    lt_exempt = {b["key"]: b.get("exempt") or 0.0 for b in buckets}
    taxable = {b["key"]: max(0.0, b.get("taxable") or 0.0) for b in buckets}

    spec = intraday
    spec_cf = 0.0
    if spec < 0:
        spec_cf = -spec
        spec = 0.0
        steps.append(f"Intraday (speculative) loss of {money(spec_cf)}: it can only be set off against speculative "
                     "income, and there's none this year, so it is carried forward (up to 4 years).")
    elif spec > 0:
        steps.append(f"Intraday (speculative) profit of {money(spec)} is business income, taxed at your slab rate.")

    biz = business
    biz_cf = 0.0
    if biz > 0:
        steps.append(f"F&O, commodity and currency profit after charges, {money(biz)}, is non-speculative business income, taxed at your slab rate.")
    elif biz < 0:
        loss = -biz
        steps.append(f"F&O, commodity and currency loss after charges: {money(loss)}. It can be set off against any "
                     "income this year except salary, and what's left is carried forward (up to 8 years, against business income only).")
        take = min(spec, loss)
        if take > 0:
            spec -= take
            loss -= take
            steps.append(f"{money(take)} of it set off against the intraday profit.")
        take = min(rest, loss)
        if take > 0:
            rest -= take
            loss -= take
            steps.append(f"{money(take)} of it set off against your other income that isn't salary.")
        for b in sorted(taxable, key=lambda b: -g_rates[b]):
            take = min(taxable[b], loss)
            if take > 0:
                taxable[b] -= take
                loss -= take
                steps.append(f"{money(take)} of it set off against taxable {'short' if b.startswith('st') else 'long'}-term gains at {_pct(g_rates[b])}.")
        for b in lt_exempt:            # then against the exempt part of long-term gains (no tax saved there)
            take = min(lt_exempt[b], loss)
            if take > 0:
                lt_exempt[b] -= take
                loss -= take
                steps.append(f"{money(take)} of it set off against long-term gains within the exemption.")
        biz_cf = loss
        if loss > 0:
            steps.append(f"{money(loss)} of business loss is left to carry forward.")
        biz = 0.0

    normal_gross = salary - std + rest + spec + biz
    ded = min(v["deductions"], normal_gross) if r["deductions"] else 0.0
    if r["deductions"] and v["deductions"]:
        steps.append(f"Deductions you entered (80C and the like): {money(ded)} taken off income taxed at slab rates"
                     + (" (no more than that income)." if ded < v["deductions"] else ".")
                     + " They can't reduce share gains taxed at special rates.")
    elif v["deductions"] and not r["deductions"]:
        steps.append("The new regime allows almost no deductions, so the deductions you entered aren't used.")
    normal = max(0.0, normal_gross - ded)
    special_income = sum(taxable.values())
    total = normal + special_income + sum(lt_exempt.values())
    steps.append(f"Income taxed at slab rates: {money(normal)}. Share gains taxed at special rates: {money(special_income)}"
                 + (f" (plus {money(sum(lt_exempt.values()))} of long-term gains within the exemption)" if sum(lt_exempt.values()) > 0.5 else "")
                 + f". Total income: {money(total)}.")

    b = _base(normal, taxable, g_rates, total, r)
    if not v["resident"] and special_income > 0 and normal < bel:
        steps.append(f"Slab income is below the {money(bel)} basic exemption limit, but as a non-resident the unused part "
                     "can't be used against share gains, so they are taxed in full.")
    for k, take in b["used_bel"].items():
        steps.append(f"Slab income is below the {money(basic_exemption(r['slabs']))} basic exemption limit, so {money(take)} of the "
                     f"gains at {_pct(g_rates[k])} is not taxed (the unused limit can be used against them).")
    steps.append(f"Slab tax on {money(normal)}: {money(b['slab'])}. Tax on share gains at special rates: {money(b['special_total'])}.")
    if b["rebate"] > 0:
        what = "slab tax" if not r["rebate_special"] or b["rebate"] <= b["slab"] else "slab tax and short-term gains tax"
        if total <= r["rebate_limit"]:
            steps.append(f"Section 87A rebate: total income is {money(r['rebate_limit'])} or less, so {money(b['rebate'])} of the "
                         f"{what} is not payable (up to {money(r['rebate_max'])}).")
        else:
            steps.append(f"Section 87A marginal relief: total income is just over {money(r['rebate_limit'])}, so the {what} is cut "
                         f"to the income over that limit ({money(b['rebate'])} less).")
    if r["rebate_limit"] and not r["rebate_special"] and b["special_total"] > 0 and total <= r["rebate_limit"] + 100000:
        steps.append("From FY 2025-26 under the new regime, the 87A rebate can't be used against tax on share gains at special rates.")
    elif b["special"] and any(k.startswith("lt") and t > 0 for k, t in b["special"].items()) and r["rebate_limit"] and total <= r["rebate_limit"]:
        steps.append("The 87A rebate can't be used against tax on long-term gains (section 112A).")

    tax, sc, rate = _with_surcharge(b, total, special_income, r["sc_cap"])
    relief = 0.0
    for above, _ in SURCHARGE:           # marginal relief: just over a threshold, the extra tax is at most the extra income
        above_rate = surcharge_rate(above, min(special_income, above), r["sc_cap"])
        if total > above and rate > above_rate:
            cut = total - above
            n2 = max(0.0, normal - cut)
            left = cut - (normal - n2)
            g2 = dict(taxable)
            for k in sorted(g2, key=lambda k: -g_rates[k]):
                take = min(g2[k], left)
                g2[k] -= take
                left -= take
            b2 = _base(n2, g2, g_rates, above, r)
            t2, sc2, _ = _with_surcharge(b2, above, sum(g2.values()), r["sc_cap"])
            relief = max(0.0, (tax + sc) - (t2 + sc2 + cut))
            relief = min(relief, sc)
            break
    if sc > 0:
        steps.append(f"Surcharge: {_pct(rate)} on the slab tax" + (f" and {_pct(min(rate, SPECIAL_SC_CAP))} on the special-rate tax" if b["special_total"] else "")
                     + f" as total income is over {money(next(a for a, _ in SURCHARGE if total > a))}: {money(sc)}"
                     + (f", less marginal relief of {money(relief)}" if relief > 0.5 else "") + ".")
    before_cess = tax + sc - relief
    cess = before_cess * CESS
    final = before_cess + cess
    steps.append(f"Health and education cess at 4%: {money(cess)}. Estimated total tax: {money(final)}.")

    # each source's share: the special-rate tax is the gains'; the slab tax is split by each source's slab income
    special_after = b["special_total"] - (b["rebate"] - b["rebate_slab"])
    slab_after = b["slab"] - b["rebate_slab"]
    sc_special = special_after * min(rate, SPECIAL_SC_CAP)
    sc_slab = slab_after * rate
    total_sc = sc_special + sc_slab
    rel_special = relief * (sc_special / total_sc) if total_sc else 0.0
    cg_tax = (special_after + sc_special - rel_special) * (1 + CESS)
    slab_total = max(0.0, final - cg_tax)
    slab_left = min(slab_cg, rest)        # what's left of the slab-rate fund gains after any business loss set-off
    shares = {"other": max(0.0, salary - std + rest - slab_left), "intraday": spec, "fno": biz, "slab_gains": slab_left}
    whole = sum(shares.values())
    parts = {"capital_gains": round(cg_tax, 2)}
    for k, s in shares.items():
        parts[k] = round(slab_total * s / whole, 2) if whole > 0 else 0.0
    parts["capital_gains"] = round(parts["capital_gains"] + parts.pop("slab_gains"), 2)

    line("Other income (salary, interest and the like)", v["other"])
    if div:
        line("Dividends (income from other sources)", div)
    if std:
        line("Less standard deduction", -std)
    if slab_gains > 0:
        line("Non-equity short-term gains at slab rates (ETFs, gold bonds)", slab_gains)
    line("Intraday (speculative) profit or loss", intraday)
    line("F&O, commodity and currency profit or loss, after charges", business)
    if slab_mf:
        line("Mutual fund gains taxed at slab rates", slab_mf)
    if slab_us:
        line("Foreign share gains taxed at slab rates", slab_us)
    if spec_cf:
        line("Intraday loss carried forward (not set off this year)", spec_cf, "note")
    if biz_cf:
        line("Business loss carried forward (not set off this year)", biz_cf, "note")
    if ded:
        line("Less deductions (old regime)", -ded)
    line("Income taxed at slab rates", normal, "subtotal")
    line("Share gains taxed at special rates (after set-off and exemption)", special_income, "subtotal")
    line("Total income", total, "subtotal")
    line("Slab tax", b["slab"], "tax")
    line("Tax on share gains at special rates", b["special_total"], "tax")
    if b["rebate"]:
        line("Less section 87A rebate", -b["rebate"], "tax")
    if sc:
        line(f"Surcharge ({_pct(rate)})", sc, "tax")
    if relief > 0.5:
        line("Less marginal relief on surcharge", -relief, "tax")
    line("Cess (4%)", cess, "tax")
    line("Estimated total tax", final, "total")
    return {"available": True, "regime": v["regime"], "inputs": v, "total": round(final, 2), "parts": parts,
            "slab_tax": round(b["slab"], 2), "special_tax": round(b["special_total"], 2), "rebate": round(b["rebate"], 2),
            "surcharge": round(sc - relief, 2), "surcharge_rate": rate, "cess": round(cess, 2),
            "income": {"normal": round(normal, 2), "special": round(special_income, 2), "total": round(total, 2),
                       "salary": round(salary, 2), "standard_deduction": round(std, 2), "deductions": round(ded, 2),
                       "dividends": round(div, 2),
                       # the F&O and intraday lines the Money home shows beside the total (R6O-014)
                       "business": round(business, 2), "intraday": round(intraday, 2)},
            "carry_forward": {"speculative": round(spec_cf, 2), "business": round(biz_cf, 2)},
            "steps": steps, "lines": lines, "notes": notes, "confirmed": r["confirmed"], "source": r["source"]}


# ---------- returns and audit, facts only ----------
CRORE = 1e7


def _crore(v: float) -> str:
    return f"₹{v / CRORE:,.1f} crore".replace(".0 crore", " crore")


def audit_fact(fy: int, turnover: float, has_business: bool) -> str | None:
    """Where the year's turnover stands against section 44AB's limits, as a fact (the owner's FY 2025-26: Rs39.7 crore
    of F&O turnover, past the Rs10 crore limit, while no page said so). None below Rs1 crore or with no business income."""
    if not has_business or not turnover or turnover <= CRORE:
        return None
    high = 10 * CRORE if fy >= 2020 else 5 * CRORE if fy == 2019 else CRORE
    if turnover > high:
        return f"Turnover of {_crore(turnover)} is above {_crore(high)}, the higher limit in section 44AB: a tax audit applies."
    return (f"Turnover of {_crore(turnover)} is above ₹1 crore: section 44AB requires a tax audit unless cash receipts "
            f"and cash payments were each no more than 5% of the total, when the limit is {_crore(high)}.")


def filing_facts(fy: int, turnover: float, has_business: bool) -> list[str]:
    """What the law says about the return form and tax audit, for a year with business income."""
    if not has_business:
        return []
    out = ["Intraday, F&O, commodity and currency trading results are business income. Individuals with business "
           "income file ITR-3 (ITR-4 is only for the presumptive scheme).",
           f"Turnover worked out from your files (the total of profits and losses, trade by trade): {money(turnover)}."]
    mine = audit_fact(fy, turnover, has_business)
    if mine:
        out.append(mine)
    if fy >= 2020:
        out.append("Tax audit (section 44AB): needed when turnover is over ₹1 crore, or over ₹10 crore when cash "
                   "receipts and cash payments are each no more than 5% of the total (the ₹10 crore limit applies "
                   "from FY 2020-21; it was ₹5 crore in FY 2019-20).")
    else:
        out.append("Tax audit (section 44AB): needed when turnover is over ₹1 crore (₹5 crore from FY 2019-20 when "
                   "cash transactions are no more than 5%).")
    out.append("Under the presumptive scheme (section 44AD), a business that declares profit below 6% of turnover, or "
               "a loss, with total income above the basic exemption limit can also need an audit, depending on the "
               "years it opted in or out.")
    if fy >= 2025:                    # Finance Act 2026 (section 139(1); section 263 of the 2025 Act)
        out.append("Due dates for the return: 31 August after the year ends for business income without an audit (31 "
                   "July when there's no business income), 31 October with an audit, unless extended. A revised return "
                   "can be filed until 31 March after the year ends.")
    else:
        out.append("Due dates for the return: 31 July after the year ends without an audit, 31 October with one, unless extended.")
    if fy >= 2026:
        out.append(NEW_ACT_NOTE)
    return out
