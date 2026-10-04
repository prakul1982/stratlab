"""The total tax estimate for one financial year: slab tax on the user's other income, intraday (speculative) income
and F&O, commodity and currency (non-speculative business) income, the special rates on listed share gains (sections
111A and 112A), the section 87A rebate, surcharge and 4% cess, with the loss set-off rules between them.

The user gives three things per year: the regime (new by default, or old), their other income (salary, interest and
the like, as one number, with how much of it is salary) and, under the old regime, their deductions. Everything else
comes from the uploaded files. A resident individual under 60 is assumed. Facts and arithmetic only; an estimate,
never a view on which regime to pick or what to do."""
import json
import math

from . import db

KEY = "taxinputs:"                # taxinputs:<uid> = {"2025": {"regime", "other", "salary", "deductions"}}
CESS = 0.04
SPECIAL_SC_CAP = 0.15             # surcharge on the tax on 111A and 112A gains is capped at 15%
MAX_AMOUNT = 1e11                 # ₹10,000 crore: anything typed above this is a mistake
FIRST_FY, LAST_FY = 2020, 2026

OLD_SLABS = [(250000, 0.0), (500000, 0.05), (1000000, 0.20), (math.inf, 0.30)]
# new regime (section 115BAC) slabs: (up to, rate)
NEW_2020 = [(250000, 0.0), (500000, 0.05), (750000, 0.10), (1000000, 0.15), (1250000, 0.20), (1500000, 0.25), (math.inf, 0.30)]
NEW_2023 = [(300000, 0.0), (600000, 0.05), (900000, 0.10), (1200000, 0.15), (1500000, 0.20), (math.inf, 0.30)]
NEW_2024 = [(300000, 0.0), (700000, 0.05), (1000000, 0.10), (1200000, 0.15), (1500000, 0.20), (math.inf, 0.30)]
NEW_2025 = [(400000, 0.0), (800000, 0.05), (1200000, 0.10), (1600000, 0.15), (2000000, 0.20), (2400000, 0.25), (math.inf, 0.30)]
SURCHARGE = [(50000000, 0.37), (20000000, 0.25), (10000000, 0.15), (5000000, 0.10)]     # above, rate


def rules(fy: int, regime: str) -> dict | None:
    """The year's slabs, standard deduction, 87A rebate and surcharge cap for a regime, or None for a year not
    covered. `rebate_special`: whether the rebate can be used against tax on 111A gains (never 112A)."""
    if not FIRST_FY <= fy <= LAST_FY:
        return None
    if regime == "old":
        return {"slabs": OLD_SLABS, "std": 50000, "rebate_limit": 500000, "rebate_max": 12500, "marginal": False,
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
    return {"regime": "new", "other": 0.0, "salary": None, "deductions": 0.0, "saved": False}


def clean(v: dict | None) -> dict:
    """Inputs as stored, each one checked: an unknown regime is the new one, amounts are 0 or more and capped."""
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
    shortfall = max(0.0, basic_exemption(r["slabs"]) - normal)
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
             business_parts: dict[str, float] | None = None, slab_gains: float = 0.0) -> dict:
    """The year's total tax estimate.

    `buckets` are the capital gains year's buckets (key, rate, after_setoff, exempt, taxable); `intraday` the
    speculative profit or loss; `business` the F&O, commodity and currency profit or loss after charges, with
    `business_parts` the same by segment; `slab_gains` short-term gains taxed at slab rates (gold, debt and other
    non-equity ETFs and gold bonds, after their own set-off). Returns the steps in plain words, a breakdown table and
    the total."""
    v = clean(inputs)
    r = rules(fy, v["regime"])
    if r is None:
        return {"available": False, "regime": v["regime"], "inputs": v,
                "reason": f"The total tax estimate covers FY {FIRST_FY}-{str(FIRST_FY + 1)[2:]} to FY {LAST_FY}-{str(LAST_FY + 1)[2:]}."}
    steps: list[str] = []
    lines: list[dict] = []

    def line(label, amount, kind="amount"):
        lines.append({"label": label, "amount": round(amount, 2), "kind": kind})

    salary = v["other"] if v["salary"] is None else v["salary"]
    rest = max(0.0, v["other"] - salary) + max(0.0, slab_gains)
    std = min(r["std"], salary)
    if v["other"]:
        steps.append(f"Other income you entered: {money(v['other'])}" + (f", of which {money(salary)} is salary or pension." if salary else ", none of it salary.")
                     + (" All of it is taken as salary, as you didn't say how much is." if v["salary"] is None and salary else ""))
    if slab_gains > 0:
        steps.append(f"Short-term gains on ETFs and gold bonds taxed at slab rates: {money(slab_gains)}.")
    if std:
        steps.append(f"Standard deduction of {money(std)} on salary ({v['regime']} regime, {money(r['std'])} at most).")

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
    if not r["rebate_special"] and b["special_total"] > 0 and total <= r["rebate_limit"] + 100000:
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
    shares = {"other": max(0.0, salary - std + rest), "intraday": spec, "fno": biz}
    whole = sum(shares.values())
    parts = {"capital_gains": round(cg_tax, 2)}
    for k, s in shares.items():
        parts[k] = round(slab_total * s / whole, 2) if whole > 0 else 0.0

    line("Other income (salary, interest and the like)", v["other"])
    if std:
        line("Less standard deduction", -std)
    if slab_gains > 0:
        line("Non-equity short-term gains at slab rates (ETFs, gold bonds)", slab_gains)
    line("Intraday (speculative) profit or loss", intraday)
    line("F&O, commodity and currency profit or loss, after charges", business)
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
                       "salary": round(salary, 2), "standard_deduction": round(std, 2), "deductions": round(ded, 2)},
            "carry_forward": {"speculative": round(spec_cf, 2), "business": round(biz_cf, 2)},
            "steps": steps, "lines": lines}


# ---------- returns and audit, facts only ----------
def filing_facts(fy: int, turnover: float, has_business: bool) -> list[str]:
    """What the law says about the return form and tax audit, for a year with business income."""
    if not has_business:
        return []
    out = ["Intraday, F&O, commodity and currency trading results are business income. Individuals with business "
           "income file ITR-3 (ITR-4 is only for the presumptive scheme).",
           f"Turnover worked out from your files (the total of profits and losses, trade by trade): {money(turnover)}."]
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
    out.append("Due dates for the return: 31 July after the year ends without an audit, 31 October with one, unless extended.")
    if fy >= 2026:
        out.append("From 1 April 2026 the Income-tax Act, 2025 replaces the 1961 Act, so section numbers differ.")
    return out
