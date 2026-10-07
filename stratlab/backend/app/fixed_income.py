"""Fixed-income rates and after-tax yield (Money → Rates): one dated table of the latest T-bill auction cut-offs,
benchmark G-sec yields and the repo rate (from the Reserve Bank's Current Rates, rbi_rates.py), this quarter's small
savings rates with their tax treatment (from the Finance Ministry's quarterly notification), the RBI Floating Rate
Savings Bond's rate (pegged to the NSC rate), and the user's own deposits from Net worth; each beside its yield after
tax at the user's marginal rate.

The marginal rate is a slab picked on the page (everyone), or worked out from the user's own tax estimate inputs for
this financial year (Basic): the extra tax on the next ₹10,000 of interest, with the rebate, surcharge and cess.
Rates and arithmetic with their dates: no ranking, no "best" deposit and no corporate bonds or bank rate tables."""
from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query

from . import money_networth as nw, rbi_rates, tax_lots, tax_total
from .auth import current_profile
from .plans import FEATURE_PLAN, PLANS, allows
from .responses import err, ok

IST = ZoneInfo("Asia/Kolkata")
CESS = tax_total.CESS


def today() -> date:
    """Today in India: the server runs on UTC, whose date is the day before from midnight to 5:30 AM IST (the financial
    year turns on 1 April, and a deposit matures on its date, in India)."""
    return datetime.now(IST).date()


SLABS = (0, 5, 10, 15, 20, 25, 30)
PROBE = 10000.0                    # the marginal rate is the tax on this much more interest

# Small savings schemes, as notified for the quarter by the Ministry of Finance (Department of Economic Affairs)
# Office Memorandum of 30 Sep 2026 for 1 Oct to 31 Dec 2026: unchanged from the quarter before.
SMALL_SAVINGS = {
    "quarter": "October to December 2026", "from": "2026-10-01", "to": "2026-12-31", "notified": "2026-09-30",
    "source": "Ministry of Finance, Department of Economic Affairs, Office Memorandum of 30 September 2026",
    "rows": [
        # key, name, rate %, how interest works, tax ("eee" or "taxable"), 80C on the deposit (old regime)
        ("posb", "Post office savings account", 4.0, "Credited yearly", "taxable", False),
        ("td1", "Post office time deposit, 1 year", 6.9, "Compounded quarterly, paid yearly", "taxable", False),
        ("td2", "Post office time deposit, 2 years", 7.0, "Compounded quarterly, paid yearly", "taxable", False),
        ("td3", "Post office time deposit, 3 years", 7.1, "Compounded quarterly, paid yearly", "taxable", False),
        ("td5", "Post office time deposit, 5 years", 7.5, "Compounded quarterly, paid yearly", "taxable", True),
        ("rd5", "Post office recurring deposit, 5 years", 6.7, "Compounded quarterly", "taxable", False),
        ("mis", "Monthly Income Account (MIS)", 7.4, "Paid monthly", "taxable", False),
        ("scss", "Senior Citizens' Savings Scheme (SCSS)", 8.2, "Paid quarterly", "taxable", True),
        ("nsc", "National Savings Certificate (NSC), 5 years", 7.7, "Compounded yearly, paid at maturity", "taxable", True),
        ("kvp", "Kisan Vikas Patra (KVP), doubles in 115 months", 7.5, "Compounded yearly, paid at maturity", "taxable", False),
        ("ppf", "Public Provident Fund (PPF)", 7.1, "Compounded yearly", "eee", True),
        ("ssy", "Sukanya Samriddhi Account (SSY)", 8.2, "Compounded yearly", "eee", True),
    ],
}
FRB_SPREAD = 0.35                  # Floating Rate Savings Bonds, 2020 (Taxable): the NSC rate plus 0.35 points, reset each half-year
FRB_PERIOD = ("2026-07-01", "2026-12-31")

TAX_TEXT = {
    "eee": "Tax-free: the deposit (under 80C), the interest and the maturity",
    "taxable": "Interest taxed at your slab rate",
    "discount": "The discount is taxed at your slab rate when the bill matures or is sold",
    "reference": "A policy rate, not something you can hold",
}
NOTES = [
    "After-tax yield is the rate less tax at your marginal rate (slab rate with 4% cess, and surcharge when your estimate "
    "has one). It leaves out compounding and when the tax is paid.",
    "Section 80C (up to ₹1.5 lakh a year, deposits marked 80C) is in the old regime only.",
    "TDS: banks and the post office deduct 10% of interest above ₹50,000 in a financial year (₹1 lakh for senior "
    "citizens) per payer, under section 194A; Form 15G or 15H stops it when "
    "your tax is nil. TDS is not extra tax: it counts against what you owe.",
    "T-bill and G-sec figures are the last auction's cut-off yield and the market yield, from the Reserve Bank. What you "
    "get depends on the price on the day you buy.",
    "The Floating Rate Savings Bond's rate is the NSC rate plus 0.35 points, reset on 1 January and 1 July.",
]
DISCLAIMER = "Rates as published, and arithmetic at your tax rate. Not a recommendation of any deposit, bond or scheme."


def slab_rate(slab: float) -> float:
    """A slab picked on the page, with cess, as a fraction."""
    return slab / 100 * (1 + CESS)


def marginal(fy: int, inputs: dict) -> dict | None:
    """The tax on the next ₹10,000 of interest at the user's own inputs (rebate, surcharge and cess included), as a
    fraction, with the estimate's taxable income. None when there is no estimate for the year."""
    v = tax_total.clean(inputs)
    salary = v["other"] if v["salary"] is None else v["salary"]
    base = {**v, "salary": salary}
    a = tax_total.estimate(fy, base, [], 0.0, 0.0)
    b = tax_total.estimate(fy, {**base, "other": v["other"] + PROBE}, [], 0.0, 0.0)
    if not a.get("available") or not b.get("available"):
        return None
    return {"rate": round((b["total"] - a["total"]) / PROBE, 4), "regime": v["regime"], "income": v["other"],
            "age": v["age"], "fy": fy}


def after(rate: float | None, tax: str, t: float) -> float | None:
    if rate is None or tax == "reference":
        return None
    return round(rate if tax == "eee" else rate * (1 - t), 2)


def deposits(uid: str, t: float, at: date) -> list[dict]:
    """The user's own fixed and recurring deposits from Net worth, each with its rate after tax and, for a fixed
    deposit, the interest at maturity before and after tax."""
    out = []
    for i in nw.load(uid)["items"]:
        if i.get("kind") not in ("fd", "rd") or i.get("rate") is None:
            continue
        try:
            start, mat = date.fromisoformat(i["start"]), date.fromisoformat(i["maturity"])
        except (KeyError, TypeError, ValueError):
            continue
        row = {"id": i["id"], "kind": i["kind"], "name": i.get("name") or nw.LABEL[i["kind"]], "rate": i["rate"],
               "after_tax": after(i["rate"], "taxable", t), "maturity": mat.isoformat(), "matured": at >= mat}
        if i["kind"] == "fd":
            m = nw.fd_value(i["principal"], i["rate"], start, mat, i.get("compounding", "quarterly"), mat)
            interest = m - i["principal"]
            row.update(principal=i["principal"], interest=round(interest, 2), interest_after_tax=round(interest * (1 - t), 2),
                       compounding=i.get("compounding", "quarterly"))
        else:
            m, total = nw.rd_value(i["monthly"], i["rate"], start, mat, mat)
            row.update(monthly=i["monthly"], interest=round(m - total, 2), interest_after_tax=round((m - total) * (1 - t), 2))
        out.append(row)
    return out


def saved_inputs(uid: str, fy: int) -> tuple[int, dict] | None:
    """The tax inputs the person saved in the tax report that stand for `fy`: that year's own, else the latest year
    they saved before it, else the earliest after it (income rarely resets to nothing between years)."""
    got = {y: v for y, v in tax_total.load_inputs(uid).items() if v.get("saved")}
    if not got:
        return None
    use = fy if fy in got else max((y for y in got if y < fy), default=min(got))
    return use, got[use]


def tax_basis(profile: dict, slab: float | None, own: bool) -> tuple[float, str, dict | None, int]:
    """(tax rate as a fraction, "estimate" or "slab", the estimate's marginal-rate facts, the financial year). The
    user's own estimate counts only on a plan with `rates_slab`; everyone else gets the picked slab (30% by default)."""
    fy = tax_lots.fy_of(today().isoformat())
    mine = None
    if allows(profile["_plan"], "rates_slab") and own:
        found = saved_inputs(profile["id"], fy)
        if found:
            mine = marginal(*found)
    if mine:
        return mine["rate"], "estimate", mine, fy
    return slab_rate(slab if slab is not None else 30), "slab", None, fy


def networth_deposits(profile: dict) -> dict:
    """What Net worth shows beside each FD and RD: the interest to maturity after tax, at the same rate the Rates page
    uses by default (the user's own estimate on a plan with `rates_slab`, else the 30% slab)."""
    t, basis, _, _ = tax_basis(profile, None, True)
    rows = deposits(profile["id"], t, today())
    return {"tax_rate": round(t * 100, 2), "basis": basis,
            "items": {r["id"]: {"interest": r["interest"], "interest_after_tax": r["interest_after_tax"]} for r in rows}}


def view(profile: dict, slab: float | None, own: bool) -> dict:
    full = allows(profile["_plan"], "rates_slab")
    at = today()
    t, basis, mine, fy = tax_basis(profile, slab, own)
    rbi = rbi_rates.current()
    r = rbi["rates"]
    market = []
    if r.get("repo") is not None:
        market.append({"key": "repo", "name": "Policy repo rate", "rate": r["repo"], "tax": "reference", "after_tax": None,
                       "how": "Set by the Monetary Policy Committee", "as_of": rbi["read_at"]})
    for days, y in sorted((r.get("tbills") or {}).items(), key=lambda x: int(x[0])):
        market.append({"key": f"tbill{days}", "name": f"{days}-day Treasury bill", "rate": y, "tax": "discount",
                       "after_tax": after(y, "taxable", t), "how": "Cut-off yield at the last auction", "as_of": rbi["read_at"]})
    for g in r.get("gsecs") or []:
        market.append({"key": f"gs{g['year']}", "name": f"Government bond, {g['name']}", "rate": g["yield"], "tax": "taxable",
                       "after_tax": after(g["yield"], "taxable", t), "how": "Market yield", "as_of": r.get("gsec_date") or rbi["read_at"]})
    ss = SMALL_SAVINGS
    small = [{"key": k, "name": n, "rate": rate, "how": how, "tax": tax, "c80": c80, "after_tax": after(rate, tax, t)}
             for k, n, rate, how, tax, c80 in ss["rows"]]
    nsc = next(x["rate"] for x in small if x["key"] == "nsc")
    frb = round(nsc + FRB_SPREAD, 2)
    bonds = [{"key": "frb", "name": "RBI Floating Rate Savings Bonds, 2020 (Taxable)", "rate": frb, "tax": "taxable",
              "after_tax": after(frb, "taxable", t), "how": f"Paid half-yearly; NSC rate plus {FRB_SPREAD} points",
              "from": FRB_PERIOD[0], "to": FRB_PERIOD[1]}]
    return {"full": full, "plan": PLANS[FEATURE_PLAN["rates_slab"]]["name"], "tax_rate": round(t * 100, 2), "basis": basis,
            "slab": slab if basis == "slab" else None, "mine": mine,
            "inputs_saved": saved_inputs(profile["id"], fy) is not None, "slabs": list(SLABS), "fy": fy,
            "market": market, "market_read_at": rbi["read_at"], "market_available": bool(r),
            "small_savings": {"quarter": ss["quarter"], "from": ss["from"], "to": ss["to"], "notified": ss["notified"],
                              "source": ss["source"], "rows": small},
            "bonds": bonds, "deposits": deposits(profile["id"], t, at), "tax_text": TAX_TEXT, "notes": NOTES,
            "disclaimer": DISCLAIMER, "as_of": at.isoformat(), "rbi_source": rbi_rates.SOURCE}


router = APIRouter(prefix="/money/rates", tags=["money"])


@router.get("")
def rates(slab: float | None = Query(None), own: bool = True, profile=Depends(current_profile)):
    """Fixed-income rates with their yield after tax: at a picked slab (everyone) or at the marginal rate from your
    own tax estimate (Basic and up)."""
    if slab is not None and slab not in SLABS:
        err(400, "bad_slab", "Pick a slab of 0, 5, 10, 15, 20, 25 or 30%.")
    return ok(view(profile, slab, own and slab is None))
