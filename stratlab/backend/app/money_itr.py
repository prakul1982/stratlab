"""ITR-ready export and the pack for your CA (/money/itr): one financial year's figures from the tax report laid out
the way the return's schedules ask for them, as an Excel workbook, a ZIP of CSV files and one PDF.

Prepared from the user's own files to help them or their CA fill the return; it is not a return and StratLab files
nothing (filing for someone needs ERI registration with the Income Tax Department; an export doesn't).

The layouts follow the ITR-2 and ITR-3 forms for AY 2026-27 (FY 2025-26), checked on 4 Oct 2026:
- Schedule 112A, columns 1a to 14 in the form's order, 1a "BE"/"AE" for acquired on or before / after 31 Jan 2018.
  Column 1b (transferred before / on or after 23 Jul 2024) was on the AY 2025-26 (FY 2024-25) form only, the one year
  that straddles the rate change; it is gone from AY 2026-27, so it is in the files for FY 2024-25 alone (DH-010). For
  "AE" holdings the portal's CSV upload takes one consolidated row (ISIN INNOTREQUIRD, name CONSOLIDATED), so that
  file is made too, with the template's header word for word (PORTAL_112A) and the money columns in whole rupees as
  its instructions ask. Sources, checked 25 Oct 2026: the portal's 112A/115AD CSV instructions (columns, codes,
  rounding, no special characters),
  https://static.incometax.gov.in/iec/foservices/assets/itr-shared/documents/112A_115AD_CSV_Instructions.pdf; the
  template's header as printed by https://freefincal.com/how-to-upload-equity-mf-share-ltcg-transactions-in-itr2-itr3-schedule-112a/
  and casparser's July 2026 change for the AY 2026-27 utility (https://github.com/codereverser/casparser/pull/144),
  which agree word for word; the utility itself couldn't be fetched, so the sheet says to check it against the template.
- Schedule CG: the full value of consideration, cost, expenditure on transfer and gain by section (111A, 112A, 112,
  slab), and Table F, the gains by the period they arose (to 15 Jun, 16 Jun-15 Sep, 16 Sep-15 Dec, 16 Dec-15 Mar,
  16 Mar-31 Mar) for section 234C; the table takes no negative cells. ITR-2 validation rules AY 2026-27,
  https://www.incometax.gov.in/iec/foportal/sites/default/files/2026-05/CBDT__e-Filing_ITR%202_Validation%20Rules_AY%202026-27_V1.0.pdf
- Schedule OS: dividends with the same five-period split (asked for from AY 2026-27 for 234C).
- ITR-3, Part A Trading Account: turnover and income from intraday trading, and from futures and options, reported
  separately from AY 2026-27; turnover as the sum of absolute profits and losses trade by trade (ICAI Guidance Note
  on Tax Audit under section 44AB, 2022 edition). https://upstox.com/news/personal-finance/tax/itr-filing-for-ay-2026-27-6-points-intraday-and-f-and-o-traders-must-know/article-196524/
- Schedule IT (advance and self-assessment tax: BSR code, date, challan number, amount) and the TDS entered.
- Schedules FSI and TR and Form 67 for US dividends (money_us_tax.py), and Schedule FA Table A3 for the calendar
  year. https://www.incometax.gov.in/iec/foportal/sites/default/files/2026-03/Step%20by%20Step%20Guide%20FA%20FSI.pdf

The figures are the tax report's (main.tax_inputs): the user's tradebooks and tax P&L files, mutual fund CAS,
US trades, dividend files or the estimate from holdings, and the advance tax and TDS entered in Tax tools. Facts
and arithmetic; never a view on what to do."""
import csv
import io
import re
import zipfile
from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from . import instrument_kinds, money_advance_tax as adv, money_dividends as divs, money_routes, money_us_routes
from . import money_us_tax as us, tax_due, tax_lots, tax_total, xlsx_write
from .auth import current_profile
from .plans import FEATURE_PLAN, PLANS, allows
from .tax_lots import GF_DATE, RATE_CHANGE, fy_label, money
from .email_kit import fmt_date as _day

router = APIRouter(prefix="/money/itr", tags=["money"])
IST = ZoneInfo("Asia/Kolkata")      # the day a pack is made is India's (RC3M-004)
LABEL = ("Prepared by StratLab from your files to help you or your CA fill the return. This is not a filed return, "
         "and StratLab files nothing for you.")
CHECK = ("Check every figure against your broker's statements, Form 26AS and the AIS before you use it, and use the "
         "portal's own computation when you file.")
PERIODS = ["Up to 15 Jun", "16 Jun to 15 Sep", "16 Sep to 15 Dec", "16 Dec to 15 Mar", "16 Mar to 31 Mar"]
SECTIONS = {
    "st_new": ("Short-term, section 111A (listed shares and equity funds, STT paid)", "20%"),
    "st_old": ("Short-term, section 111A (listed shares and equity funds, STT paid), sold before 23 Jul 2024", "15%"),
    "lt_new": ("Long-term, section 112A (listed shares and equity funds, STT paid)", "12.5% above the exemption"),
    "lt_old": ("Long-term, section 112A, sold before 23 Jul 2024", "10% above the exemption"),
    "st_slab": ("Short-term, other mutual funds (section 50AA where it applies)", "slab rate"),
    "lt_112": ("Long-term, section 112, other mutual funds, without indexation", "12.5%"),
    "lt_112i": ("Long-term, section 112, other mutual funds, with indexation", "20%"),
    "st_us": ("Short-term, foreign shares (unlisted in India)", "slab rate"),
    "lt_us": ("Long-term, section 112, foreign shares (unlisted in India), without indexation", "12.5%"),
    "lt_usi": ("Long-term, section 112, foreign shares, with indexation, sold before 23 Jul 2024", "20%"),
    "st_unit": ("Short-term, ETFs and gold bonds (section 50AA where it applies)", "slab rate"),
    "lt_unit": ("Long-term, section 112, ETFs and gold bonds, without indexation", "12.5%"),
    "lt_uniti": ("Long-term, section 112, ETFs and gold bonds sold before 23 Jul 2024, with indexation", "20%"),
    "lt_unit10": ("Long-term, section 112 proviso, gold bonds sold before 23 Jul 2024, without indexation", "10%"),
}
F_GROUPS = [("111A at 20%", {"st_new"}), ("111A at 15%", {"st_old"}), ("112A at 12.5%", {"lt_new"}), ("112A at 10%", {"lt_old"}),
            ("112 at 12.5%", {"lt_112", "lt_us", "lt_unit"}), ("112 at 20%", {"lt_112i", "lt_usi", "lt_uniti"}),
            ("112 at 10%", {"lt_unit10"}), ("At slab rates", {"st_slab", "st_us", "st_unit"})]


def _m():
    from . import main
    return main


def r2(v) -> float | None:
    return None if v is None else round(float(v), 2)


def period(d: str) -> int:
    """Which of the return's five periods a date in the financial year falls in."""
    return us.quarter_of(d)


# ---------- gathering the year ----------
def gather(profile, fy: int) -> dict:
    """Everything the schedules need for one financial year, from the tax report's inputs."""
    M = _m()
    uid = profile["id"]
    i = M.tax_inputs(profile)
    c, equity, units = money_routes.tax_computed(profile, i)
    mf, usr = c["mf"], c["us"]
    dv = money_routes.dividends_for_tax(profile)
    unit_rows = instrument_kinds.bucket_rows(units, c["names"])
    y = tax_lots.years_with_total([fy], equity, c["intraday"], unit_rows, units, c["names"], i["business"], i["income"], dv,
                                  limit=None)[fy]
    # dividends: the year's lines, from the user's files or the estimate (as Tax tools shows them)
    stored, est, ahead, rate = money_routes.dividend_parts(uid, fetch=False)
    dview = divs.view(stored, est, ahead, rate, money_routes.today())
    dyear = next((x for x in dview["years"] if x["fy"] == fy), None)
    src = (dyear or {}).get("source") or "none"
    lines = [r for r in (stored["rows"] if src == "files" else est) if tax_lots.fy_of(r["d"]) == fy and r["cur"] == "INR"]
    saved = adv.load(uid)["years"].get(fy) or adv.clean_year({})
    try:                          # the interest lines of Part B-TTI (DH-003), from Tax tools' own working
        a = money_routes._advance_year(profile, fy, i)
    except Exception as e:
        print("ITR interest lines:", type(e).__name__)
        a = {}
    business = bool(y["business"]["segments"]) or y["intraday"]["count"] > 0
    return {"fy": fy, "y": y, "payable": a.get("payable"), "schedule": a.get("schedule"),
            "audit": tax_total.audit_applies(fy, y.get("turnover") or 0, business), "business": business,
            "fno_lines": int(sum(b["trades"] for b in i["business"] if b["fy"] == fy)), "rows": [r for r in equity if r["fy"] == fy], "unit_rows": [r for r in unit_rows if r["fy"] == fy], "names": c["names"], "files": i["data"]["files"],
            "fmv_src": i["fmv_src"], "div_lines": lines, "div_source": src, "div_year": dyear,
            "us_div": money_us_routes.us_dividends(profile, fy, y), "fa": money_us_routes.fa_for(profile, fy),
            "us_count": usr["count"], "us_allowed": usr["allowed"], "us_warning": ((usr.get("years") or {}).get(fy) or {}).get("warning"),
            "tds": saved["tds"], "paid": saved["paid"],
            "mf_count": len(mf["rows"]), "made": datetime.now(IST)}


# ---------- the schedules, as tables ----------
def table(key: str, title: str, columns: list[str], rows: list[list], notes: list[str] | None = None, sheet: str | None = None) -> dict:
    """`sheet`: the Excel sheet's name when the title, shortened, would be cut at 31 characters (DH-010)."""
    return {"key": key, "title": title, "columns": columns, "rows": rows, "notes": notes or [], "sheet": sheet}


def _name(names: dict, key: str) -> tuple[str, str]:
    n = names.get(key) or {}
    return n.get("isin") or "", n.get("name") or n.get("symbol") or key


def is_112a(r: dict) -> bool:
    return r["term"] == "LT" and tax_lots._bucket(r) in ("lt_new", "lt_old")


def rows_112a(rows: list[dict], names: dict) -> list[dict]:
    """Schedule 112A's lines: one per sale lot for shares acquired on or before 31 Jan 2018 (each grandfathered on its
    own), and one per company and sale day for the rest. Each line in the form's columns 1a to 14."""
    out: dict[tuple, dict] = {}
    for r in sorted((r for r in rows if is_112a(r)), key=lambda r: (r["sold"], r["key"], r["bought"])):
        be = r["bought"] <= GF_DATE
        isin, name = _name(names, r["key"])
        k = (r["key"], r["sold"], r["bought"], id(r)) if be else (r["key"], r["sold"], "AE")
        gross = r.get("sale_gross") if r.get("sale_gross") is not None else r["sale"]
        actual = r.get("actual_cost") if r.get("actual_cost") is not None else r["cost"]
        fmv = r.get("fmv_total")
        if be:
            col9 = min(gross, fmv) if fmv is not None else (r["cost"] if r.get("gf") == "applied" else 0.0)
        else:
            col9 = 0.0
        cur = out.setdefault(k, {"1a": "BE" if be else "AE", "1b": "BE" if r["sold"] < RATE_CHANGE else "AE", "isin": isin, "name": name,
                                 "key": r["key"], "sold": r["sold"], "qty": 0.0, "gross": 0.0, "cost8": 0.0, "col9": 0.0, "fmv": None,
                                 "exp": 0.0, "gf_missing": False})
        cur["qty"] += r["qty"]
        cur["gross"] += gross
        cur["cost8"] += actual
        cur["col9"] += col9
        cur["exp"] += max(0.0, gross - r["sale"])
        if fmv is not None:
            cur["fmv"] = (cur["fmv"] or 0.0) + fmv
        cur["gf_missing"] |= r.get("gf") == "missing"
    lines = []
    for v in out.values():
        col7 = max(v["cost8"], v["col9"])
        lines.append({**v, "price": v["gross"] / v["qty"] if v["qty"] else 0.0, "col7": col7,
                      "fmv_each": v["fmv"] / v["qty"] if v["fmv"] is not None and v["qty"] else None,
                      "col13": col7 + v["exp"], "col14": v["gross"] - col7 - v["exp"]})
    return lines


COL_1B = "Share/Unit transferred (1b)"
COLS_112A = ["Share/Unit acquired (1a)", "ISIN Code (2)", "Name of the Share/Unit (3)",
             "No. of Shares/Units (4)", "Sale-price per Share/Unit (5)", "Full Value of Consideration (6) = 4 x 5",
             "Cost of acquisition without indexation (7) = higher of 8 and 9", "Cost of acquisition (8)",
             "If acquired before 01.02.2018, lower of 6 and 11 (9)", "Fair Market Value per share/unit as on 31 Jan 2018 (10)",
             "Total Fair Market Value as on 31 Jan 2018 (11) = 4 x 10", "Expenditure wholly and exclusively in connection with transfer (12)",
             "Total deductions (13) = 7 + 12", "Balance (14) = 6 - 13", "Sold on (for your records)"]
# the portal template's own header, word for word (its instructions: "its header must match exactly"); 1b only for FY 2024-25
PORTAL_112A = ["Share/Unit acquired(1a)", "ISIN Code(2)", "Name of the Share/Unit(3)", "No. of Shares/Units(4)",
               "Sale-price per Share/Unit(5)", "Full Value of Consideration(Total Sale Value)(6) = 4 * 5",
               "Cost of acquisition without indexation(7)", "Cost of acquisition(8)",
               "If the long term capital asset was acquired before 01.02.2018(9)",
               "Fair Market Value per share/unit as on 31st January 2018(10)",
               "Total Fair Market Value of capital asset as per section 55(2)(ac)(11) = 4 * 10",
               "Expenditure wholly and exclusively in connection with transfer(12)", "Total deductions(13) = 7 + 12",
               "Balance(14) = 6 - 13"]
PORTAL_1B = "Share/Unit Transferred(1b)"
ONE_B_FY = 2024                   # the only year whose form has column 1b


def _fy(g: dict) -> int | None:
    return g.get("fy") or (tax_lots.fy_of(g["rows"][0]["sold"]) if g.get("rows") else None)


def _with_1b(cols: list[str], fy: int | None, name: str) -> list[str]:
    return cols[:1] + [name] + cols[1:] if fy == ONE_B_FY else list(cols)


def t_112a(g: dict) -> dict:
    fy = _fy(g)
    one_b = fy == ONE_B_FY
    lines = rows_112a(g["rows"], g["names"])
    rows = [[v["1a"]] + ([v["1b"]] if one_b else []) + [v["isin"], v["name"], round(v["qty"], 4), r2(v["price"]), r2(v["gross"]), r2(v["col7"]), r2(v["cost8"]),
             r2(v["col9"]) if v["1a"] == "BE" else None, r2(v["fmv_each"]) if v["1a"] == "BE" else None,
             r2(v["fmv"]) if v["1a"] == "BE" else None, r2(v["exp"]), r2(v["col13"]), r2(v["col14"]), v["sold"]] for v in lines]
    if lines:
        rows.append(["Total"] + ([""] if one_b else []) + ["", "", None, None, r2(sum(v["gross"] for v in lines)), r2(sum(v["col7"] for v in lines)),
                     r2(sum(v["cost8"] for v in lines)), r2(sum(v["col9"] for v in lines if v["1a"] == "BE")), None, None,
                     r2(sum(v["exp"] for v in lines)), r2(sum(v["col13"] for v in lines)), r2(sum(v["col14"] for v in lines)), ""])
    notes = ["Long-term sales of listed shares and equity mutual fund units on which STT was paid (section 112A). Short-term "
             "sales are reported as totals in Schedule CG, not scrip by scrip.",
             ("1a: BE = acquired on or before 31 Jan 2018, AE = after. 1b (on the FY 2024-25 form only): BE = transferred "
              "before 23 Jul 2024, AE = on or after." if one_b else
              "1a: BE = acquired on or before 31 Jan 2018, AE = after. The form for this year has no column 1b (it was on "
              "the FY 2024-25 form only, for the 23 Jul 2024 rate change)."),
             "Column 9 for shares bought on or before 31 Jan 2018 is the lower of the sale value and the 31 Jan 2018 value, "
             "so the cost (7) is the higher of the actual cost and that, worked out lot by lot.",
             "Full value (6) is before the selling charges; those charges are the expenditure on transfer (12). STT isn't "
             "deductible and isn't included. The ₹1.25 lakh exemption is applied in the return's Schedule SI, not here."]
    if any(v["gf_missing"] for v in lines):
        notes.append("Some lines bought before 1 Feb 2018 have no 31 Jan 2018 price, so their column 9 is 0 and the actual cost "
                     "is used. Enter the price in the tax report to grandfather them.")
    return table("112a", "Schedule 112A (scrip-wise long-term gains)", _with_1b(COLS_112A, fy, COL_1B), rows, notes, sheet="112A")


def t_112a_portal(g: dict) -> dict:
    """The portal's upload file: lines for shares acquired on or before 31 Jan 2018 scrip-wise, and everything
    acquired after as one consolidated line, under the template's own header (DH-010). The money columns are whole
    rupees as the instructions ask (6, 11, 13 and 14 "rounded off to the nearest unit"), each worked from the rounded
    ones before it, so 6 = 4 x 5, 7 = higher of 8 and 9, 9 = lower of 6 and 11, 13 = 7 + 12 and 14 = 6 - 13 hold exactly."""
    fy = _fy(g)
    one_b = fy == ONE_B_FY
    lines = rows_112a(g["rows"], g["names"])
    be = [v for v in lines if v["1a"] == "BE"]
    ae = [v for v in lines if v["1a"] == "AE"]
    rows = []
    for v in be:
        qty, price = round(v["qty"], 4), round(v["price"], 4)
        gross = round(qty * price)
        fmv_each = round(v["fmv_each"], 4) if v["fmv_each"] is not None else None
        fmv = round(qty * fmv_each) if fmv_each is not None else None
        cost8, exp = round(v["cost8"]), round(v["exp"])
        col9 = min(gross, fmv) if fmv is not None else round(v["col9"])
        col7 = max(cost8, col9)
        rows.append([v["1a"]] + ([v["1b"]] if one_b else []) + [v["isin"], _plain(v["name"]), qty, price, gross, col7, cost8, col9,
                                                                 fmv_each, fmv, exp, col7 + exp, gross - col7 - exp])
    for code in sorted({v["1b"] for v in ae}) if one_b else (["AE"] if ae else []):
        part = [v for v in ae if not one_b or v["1b"] == code]
        gross, cost, exp = round(sum(v["gross"] for v in part)), round(sum(v["col7"] for v in part)), round(sum(v["exp"] for v in part))
        rows.append(["AE"] + ([code] if one_b else []) + ["INNOTREQUIRD", "CONSOLIDATED", None, None, gross, cost, cost, None, None, None,
                                                          exp, cost + exp, gross - cost - exp])
    return table("112a_portal", "Schedule 112A, the portal's upload layout", _with_1b(PORTAL_112A, fy, PORTAL_1B), rows,
                 ["The portal takes shares acquired after 31 Jan 2018 as one consolidated line (ISIN INNOTREQUIRD, name "
                  "CONSOLIDATED) and those acquired on or before it scrip by scrip. The header is the template's own, word "
                  "for word; the amounts are in whole rupees. Check it against the template the portal's utility gives for "
                  "the year before you upload: its header must match exactly."], sheet="112A upload layout")


def _plain(s: str) -> str:
    """A name without the characters the portal's CSV refuses."""
    import re
    return re.sub(r"[-,/()&@'\";:_\\]", " ", str(s or "")).strip()[:100]


def bucket_sums(rows: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for r in rows:
        b = tax_lots._bucket(r)
        if b is None:
            continue
        gross = r.get("sale_gross") if r.get("sale_gross") is not None else r["sale"]
        cur = out.setdefault(b, {"sale": 0.0, "cost": 0.0, "exp": 0.0, "gain": 0.0, "count": 0, "periods": [0.0] * 5})
        cur["sale"] += gross
        cur["cost"] += r["cost"]
        cur["exp"] += max(0.0, gross - r["sale"])
        cur["gain"] += r["gain"]
        cur["count"] += 1
        cur["periods"][period(r["sold"])] += r["gain"]
    return out


def t_cg(g: dict) -> dict:
    y = g["y"]
    sums = bucket_sums(g["rows"] + g.get("unit_rows", []))
    after = {b["key"]: b for b in y["buckets"]}
    rows = []
    for key, (label, rate) in SECTIONS.items():
        s = sums.get(key)
        if not s:
            continue
        b = after.get(key) or {}
        rows.append([label, rate, s["count"], r2(s["sale"]), r2(s["cost"]), r2(s["exp"]), r2(s["gain"]), r2(b.get("after_setoff")),
                     r2(b.get("exempt")), r2(b.get("taxable"))])
    units = y.get("units") or {}
    part = [r for r in units.get("rows") or [] if r["head"] == "exempt"]     # the slab and 12.5% heads are in the rows above
    if part:
        rows.append(["Gold bonds redeemed with the RBI (exempt)", "exempt", len(part), r2(sum(r["sale"] for r in part)),
                     r2(sum(r["cost"] for r in part)), 0.0, r2(sum(r["gain"] for r in part)), None, None, 0.0])
    notes = list(y["steps"]) + [f"Short-term loss left to carry forward: {money(y['carry_forward']['st'])}; long-term: "
                                f"{money(y['carry_forward']['lt'])}. Losses carry forward only when the return is filed by its due date.",
                                f"Exemption under section 112A used: {money(y['exemption']['used'])} of {money(y['exemption']['limit'])}."]
    if g["us_count"] and not g["us_allowed"]:
        notes.append("US share sales aren't included: they are on the " + PLANS[FEATURE_PLAN["us_tax"]]["name"] + " plan.")
    elif g.get("us_warning"):
        notes.append("US shares: " + g["us_warning"])
    return table("cg", "Schedule CG (capital gains by section)",
                 ["Head", "Rate", "Sales", "Full value of consideration", "Cost of acquisition (after grandfathering or indexation)",
                  "Expenditure on transfer", "Gain or loss", "After set-off", "Exempt (112A)", "Taxable"], rows, notes)


def spread(raw: list[float], total: float) -> list[float]:
    """A row's after set-off total over the five periods: each period's own gains and losses, a negative period
    carried into the next, none below zero, and no more than the total by the end (the last period makes it up)."""
    out, carry, run = [], 0.0, 0.0
    for x in raw[:-1]:
        v = max(0.0, min(x + carry, total - run))
        carry = min(0.0, x + carry)
        run += v
        out.append(v)
    return out + [max(0.0, total - run)]


def t_cg_periods(g: dict) -> dict:
    sums = bucket_sums(g["rows"] + g.get("unit_rows", []))
    after = {b["key"]: b for b in g["y"]["buckets"]}
    rows = []
    for label, keys in F_GROUPS:
        raw = [sum(sums[k]["periods"][i] for k in keys if k in sums) for i in range(5)]
        total = sum(max(0.0, (after.get(k) or {}).get("after_setoff") or 0.0) - ((after.get(k) or {}).get("exempt") or 0.0) for k in keys)
        if any(abs(x) > 0.005 for x in raw):
            p = spread(raw, max(0.0, total))
            rows.append([label] + [r2(x) for x in p] + [r2(sum(p))])
    return table("cg_periods", "Schedule CG Table F (gains by when they arose)", ["Rate"] + PERIODS + ["Total"], rows,
                 ["Each row is the gain after set-off (and, for section 112A, after the exemption), spread over the periods by "
                  "sale date: a negative period is carried into the next one, no cell is below zero, and the last period makes "
                  "the row add up to that total. These periods drive interest under section 234C."])


def t_os(g: dict) -> dict:
    rows, totals = [], [0.0] * 5
    by: dict[str, dict] = {}
    for r in g["div_lines"]:
        k = r.get("isin") or r["sym"]
        c = by.setdefault(k, {"name": r.get("name") or r["sym"], "isin": r.get("isin") or "", "p": [0.0] * 5, "tds": 0.0, "tds_file": False,
                              "taxed": 0.0})
        c["p"][period(r["d"])] += r["amount"]
        c["taxed"] += r["amount"] * divs.tds_rate(r["d"])
        if r.get("tds"):
            c["tds"] += r["tds"]
            c["tds_file"] = True
    fy = g["fy"]
    for c in sorted(by.values(), key=lambda c: -sum(c["p"])):
        total = sum(c["p"])
        tds = c["tds"] if c["tds_file"] else divs.expected_tds(fy, total, c["taxed"])
        rows.append([c["name"], c["isin"], "India"] + [r2(x) for x in c["p"]] + [r2(total), r2(tds), "your file" if c["tds_file"] else "expected"])
        totals = [a + b for a, b in zip(totals, c["p"])]
    ud = g["us_div"]
    if ud:
        for s in ud["stocks"]:
            p = [0.0] * 5
            for ln in s["lines"]:
                p[period(ln["d"])] += ln["inr"]
            rows.append([s["symbol"], "", "United States"] + [r2(x) for x in p] + [r2(s["inr"]), r2(s["tax_inr"]), "US tax withheld"])
            totals = [a + b for a, b in zip(totals, p)]
    if rows:
        rows.append(["Total", "", ""] + [r2(x) for x in totals] + [r2(sum(totals)), None, ""])
    # DH-013: a year with none said as a sentence; RC2B-016: the estimate's sentence reads whole ("Indian dividends from an
    # estimate from your holdings" did not)
    lead = {"files": "Indian dividends are from your dividend files.",
            "estimated": "Indian dividends are an estimate from your holdings and the dividends declared (upload your broker's "
                         "dividend statement for the actual figures)."}.get(g["div_source"], "No Indian dividends in your dividend files or holdings for the year.")
    notes = [lead + " Gross amounts, before TDS; dividends are taxed at your slab rate.",
             "TDS shown is what the rule gives (10% once a company's dividends to you pass ₹10,000 in FY 2025-26; ₹5,000 "
             "before; 7.5% for payments from 14 May 2020 to 31 March 2021) unless your file gave it; Form 26AS and the AIS "
             "have what was actually cut.",
             "The five periods are the return's quarterly breakup of dividends for section 234C."]
    if ud:
        notes.append("US dividends are in rupees at SBI's TT buying rate on the last day of the month before each one (Rule 115)"
                     + ("; some are estimated from the stocks' dividends and your trades." if ud.get("estimated") else "."))
    return table("os", "Schedule OS (dividends)", ["Company", "ISIN", "Country"] + PERIODS + ["Total", "TDS or tax withheld", "TDS from"], rows, notes)


def t_business(g: dict) -> dict:
    y = g["y"]
    intra = y["intraday"]
    biz = y["business"]
    rows = []
    # turnover in whole rupees, as the form takes it (DH-007: "39,55,74,093.5")
    if intra["count"]:
        rows.append(["Intraday trading (speculative business, section 43(5))", intra["count"], round(intra["turnover"]), None,
                     r2(intra["sell"] - intra["buy"]), 0.0, r2(intra["pnl"])])
    for s in biz["segments"]:
        rows.append([f"{s['label']} (non-speculative business)", s["trades"], round(s["turnover"]), round(s["turnover_contract"]), r2(s["pnl"]),
                     r2(s["charges"]), r2(s["net"])])
    if biz["segments"]:
        rows.append(["F&O, commodity and currency together", biz["trades"], round(biz["turnover"]), round(biz["turnover_contract"]), r2(biz["pnl"]),
                     r2(biz["charges"]), r2(biz["net"])])
    notes = ["ITR-3 for AY 2026-27 asks, in Part A Trading Account, for the turnover and the income of intraday trading and of "
             "futures and options separately.",
             "Turnover method: the sum of the absolute profit or loss of each trade (ICAI Guidance Note on Tax Audit under section "
             "44AB, 2022 edition); for intraday, of each day's round trip per company. Option premium isn't added. The figure "
             "netted per contract (as some broker summaries show) is given beside it.",
             "Income before charges is the profit or loss on the trades; the charges in your broker's file (including STT and "
             "CTT, which business income can deduct) are taken off to get the net."] + list(y.get("filing") or [])
    return table("business", "Business income for ITR-3 (intraday and F&O)",
                 ["Activity", "Exit lines (intraday: round trips)", "Turnover (sum of absolute profit and loss)", "Turnover netted per contract",
                  "Profit or loss before charges", "Charges", "Net profit or loss"], rows, notes)


def t_tax_paid(g: dict) -> dict:
    fy = g["fy"]
    advance, later = adv.split_paid(fy, g["paid"])           # the same split as the 234B working in Tax tools
    rows = [["Advance tax", p["d"], r2(p["amount"]), "", ""] for p in advance] + [["Self-assessment tax", p["d"], r2(p["amount"]), "", ""] for p in later]
    if g["paid"]:
        adv_t = sum(p["amount"] for p in advance)
        sa_t = sum(p["amount"] for p in later)
        rows.append(["Total advance tax", "", r2(adv_t), "", ""])
        rows.append(["Total self-assessment tax", "", r2(sa_t), "", ""])
    if g["tds"]:
        rows.append(["TDS you entered (Schedule TDS)", "", r2(g["tds"]), "", ""])
    dt = (g["div_year"] or {}).get("tds") or {}
    if dt.get("expected"):
        rows.append(["Dividend TDS the rule gives (check Form 26AS)", "", r2(dt["expected"]), "", ""])
    return table("tax_paid", "Tax paid (Schedule IT and TDS)", ["Kind", "Date of deposit", "Amount", "BSR code", "Challan serial number"], rows,
                 ["From the payments entered in Tax tools: those dated by 31 March are advance tax, those after it self-assessment "
                  "tax. Fill the BSR code and challan serial number from each challan (the AIS's 'Payment of taxes' section has "
                  "them); the portal's prefill often misses advance tax challans.",
                  "TDS needs each deductor's TAN and amounts from Form 26AS for Schedule TDS; only the total you entered is here."])


CF_UNTIL = {"st": 8, "lt": 8, "speculative": 4, "business": 8}
CF_NAMES = {"st": "Short-term capital loss", "lt": "Long-term capital loss", "business": "Business loss (non-speculative: F&O, "
            "commodity, currency)", "speculative": "Speculative business loss (intraday)"}


def t_cfl(g: dict) -> dict:
    """Schedule CFL: the losses carried forward after this year, by the year each arose and kind (DH-011: the ₹59 carried
    was only in a note). From the tax report's set-off: capital losses from year(), business ones from the estimate."""
    y, fy = g["y"], g["fy"]
    t = y.get("total") or {}
    left = [(p["fy"], p["kind"], p["left"]) for p in y.get("brought_forward") or []]
    left += [(p["fy"], p["kind"], p["left"]) for p in (t.get("brought_forward") or []) if t.get("available")]
    left += [(fy, k, y["carry_forward"][k]) for k in ("st", "lt")]
    own = t.get("carry_forward") if t.get("available") else {"speculative": max(0.0, -y["intraday"]["pnl"]), "business": max(0.0, -y["business"]["net"])}
    left += [(fy, k, own[k]) for k in ("speculative", "business")]
    rows = [[f"AY {f + 1}-{str(f + 2)[2:]} (FY {f}-{str(f + 1)[2:]})", CF_NAMES[k], r2(a), f"AY {f + 1 + CF_UNTIL[k]}-{str(f + 2 + CF_UNTIL[k])[2:]}"]
            for f, k, a in sorted(left) if a > 0.5]
    return table("cfl", "Schedule CFL (losses carried forward)", ["Year the loss arose", "Kind", "Left to carry forward",
                                                                   "Can be set off up to"], rows,
                 ["Losses left after this year's set-off, as the tax report works them out from your files (losses from years "
                  "not in your files aren't here). A loss carries forward only when the return of the year it arose was filed "
                  "by its due date (section 80).",
                  "Capital losses and business losses carry forward 8 years, intraday (speculative) losses 4 years."], sheet="CFL")


def t_setoff(g: dict) -> dict:
    """Schedules CYLA and BFLA: this year's business loss set off against other heads, and the losses brought forward
    that were used this year (DH-011). Set-off within capital gains is in Schedule CG."""
    y = g["y"]
    t = y.get("total") or {}
    rows = [["CYLA (this year's loss)", "Business loss (F&O, commodity, currency)", x["against"], r2(x["amount"])]
            for x in (t.get("set_off") or []) if t.get("available") and x["amount"] > 0.005]
    rows += [["BFLA (brought forward)", f"{CF_NAMES[p['kind']]} of FY {p['fy']}-{str(p['fy'] + 1)[2:]}",
              "Capital gains of the year" if p["kind"] in ("st", "lt") else "Intraday profit" if p["kind"] == "speculative" else "Business income of the year",
              r2(p["used"])] for p in list(y.get("brought_forward") or []) + list(t.get("brought_forward") or []) if p["used"] > 0.005]
    return table("setoff", "Schedules CYLA and BFLA (set-off of losses)", ["Schedule", "Loss", "Set off against", "Amount"], rows,
                 ["A business loss can be set off against any income except salary in the same year; capital losses only "
                  "against capital gains (in Schedule CG); intraday losses only against intraday profit."], sheet="CYLA BFLA")


def t_general(g: dict) -> dict:
    """Part A-General's audit fields for an audited year (DH-011): whether section 44AB applies on these figures, the
    dates, and the fields only the audit report has."""
    fy = g["fy"]
    rows = []
    if g.get("business"):
        if g.get("audit"):
            rows = [["Liable to audit under section 44AB?", "Yes: turnover " + money(g["y"].get("turnover") or 0) + " is above the ₹10 crore limit"],
                    ["Due date of the audit report", tax_due.said(fy, "audit_report")],
                    ["Due date of the return", tax_due.said(fy, "audit")],
                    ["Date of the audit report", "From the audit report (Form 3CA or 3CB, with 3CD)"],
                    ["Acknowledgement number of the audit report", "From the e-filing portal, once the auditor uploads it"],
                    ["Auditor's name, membership number and firm registration number", "From the audit report"]]
        else:
            rows = [["Liable to audit under section 44AB?", "Not on these figures alone: turnover " + money(g["y"].get("turnover") or 0)
                     + ". Between ₹1 crore and ₹10 crore it depends on the share of cash receipts and payments."]]
    return table("general", "Part A-General (audit information)", ["Field", "What to fill"], rows,
                 ["An audited case fills Part A-BS (balance sheet) and Part A-P&L in full from the audited accounts; the "
                  "'no account case' lines can't be used." if g.get("audit") else
                  "Shown for a year with business income (intraday or F&O)."] + ([tax_due.PENALTY_271B] if g.get("audit") else []),
                 sheet="Part A-General")


def t_tti(g: dict) -> dict:
    """Part B-TTI's tax, paid and interest lines (DH-003: the export had no interest at all): the tax as the return
    rounds it, TDS and tax paid, and the interest under sections 234A, 234B and 234C from Tax tools' working."""
    p = g.get("payable")
    rows = [[x["label"], r2(x["amount"])] for x in (p or {}).get("lines") or []]
    notes = ["From Tax tools: the payments and TDS you entered there, the instalments and the interest worked out on them."]
    if p:
        notes.append(("Worked out as if the tax is paid and the return filed by its due date, " + tax_due.day(date.fromisoformat(p["due"]))
                      if not p["past_due"] else f"The due date, {tax_due.day(date.fromisoformat(p['due']))}, has passed: worked out "
                      "as if paid and filed today") + "; interest under sections 234A and 234B grows by 1% a month of the tax unpaid after that.")
        if p["refund"] > 0.5:
            notes.append(f"TDS and tax paid are more than the tax by {money(p['refund'])}: a refund, before any interest.")
    elif g["fy"] >= tax_lots.fy_of(money_routes.today().isoformat()):
        notes.append("The year is still running: the interest is worked out once it has ended.")
    return table("tti", "Part B-TTI (tax, tax paid and interest)", ["Line", "Amount"], rows, notes, sheet="Part B-TTI")


def not_covered(g: dict) -> list[str]:
    """What the return needs that isn't in these files (DH-011: "laid out for the return" read as all of it)."""
    y = g["y"]
    t = y.get("total") or {}
    income = (t.get("income") or {}).get("total") or 0.0
    out = []
    if income > 1e7:
        out.append(f"Schedule AL (assets and liabilities at the end of the year): needed when total income is over ₹1 crore; "
                   f"this year's estimate is {money(income)}.")
    if g.get("audit"):
        out.append("Part A-BS and Part A-P&L in full, from the audited accounts (an audited case can't use the 'no account "
                   "case' lines), and the audit report itself.")
    out += ["Schedules S (salary), HP (house property) and VI-A (deductions), and Schedule TDS deductor by deductor: from Form 16, "
            "Form 26AS and the AIS.",
            "Schedule BP's adjustments beyond the trading results (depreciation, disallowances), and Schedule SI and the tax "
            "computation, which the portal works out from the schedules."]
    return out


def t_foreign(g: dict) -> dict:
    ud = g["us_div"]
    rows = []
    if ud:
        f = ud["ftc"]
        rows.append([us.COUNTRY, "Other sources (dividends)", r2(f["income"]), r2(f["foreign_tax"]), r2(f["indian_tax"]), r2(f["credit"]),
                     "Article 10 (India-US treaty)"])
    us_rows = [r for r in g["rows"] if r.get("src") == "us"]
    if us_rows:
        gain = sum(r["gain"] for r in us_rows)
        rows.append([us.COUNTRY, "Capital gains (US shares)", r2(gain), 0.0, None, 0.0, "Article 13 (gains taxed in India only)"])
    notes = ["Schedule FSI lists foreign income country by country; Schedule TR the tax relief claimed under section 90. The "
             "credit is the lower of the US tax and the Indian tax on that income; the Indian tax here is at your average rate "
             f"of tax from the total estimate ({(ud or {}).get('indian_rate', 0) * 100:.2f}%)." if ud else
             "No US dividends in this year.",
             "File Form 67 on the portal with the US tax figures before claiming the credit, by the end of the assessment year "
             f"(31 March {g['fy'] + 2})."]
    return table("foreign", "Foreign income and tax relief (Schedules FSI and TR)",
                 ["Country", "Head of income", "Income from outside India", "Tax paid outside India", "Tax payable on it in India",
                  "Tax relief available in India", "Relevant treaty article"], rows, notes)


def t_form67(g: dict) -> dict:
    ud = g["us_div"]
    rows = []
    for s in (ud or {}).get("stocks") or []:
        for ln in s["lines"]:
            rows.append([s["symbol"], ln["d"], ln["usd"], ln["tax_usd"], ln["rate"], ln["rate_on"], ln["inr"], r2(ln["tax_usd"] * ln["rate"]),
                         "estimated" if ln["estimated"] else "your file"])
    return table("form67", "Form 67 workings (US dividends and tax withheld)",
                 ["Stock", "Date", "Dividend (USD)", "US tax withheld (USD)", "Rupees a dollar", "Rate of", "Dividend (₹)", "US tax (₹)", "From"],
                 rows, ["Each line at SBI's TT buying rate on the last day of the month before it (Rule 115 for the income, Rule "
                        "128 for the tax). Your broker's year-end tax statement (Form 1042-S) has the actual tax withheld."])


COLS_FA = ["Sl. No.", "Country name and code", "Name of entity", "Address of entity", "ZIP code", "Nature of entity",
           "Date of acquiring the interest", "Initial value of the investment", "Peak value of investment during the period",
           "Closing balance", "Total gross amount paid/credited with respect to the holding during the period",
           "Total gross proceeds from sale or redemption of investment during the period", "Ticker", "Lot", "Peak on", "Shares on 31 Dec"]


def fa_table(fa: dict | None) -> dict:
    rows = []
    for n, r in enumerate((fa or {}).get("rows") or [], 1):
        rows.append([n, r["country"], r["name"], "", "", r["nature"], r["acquired"], r["initial"], r["peak"], r["closing"], r["income"],
                     r["proceeds"] if r["proceeds"] is not None else 0.0, r["symbol"], r["lot"], r["peak_day"], r["closing_qty"]])
    notes = [f"Table A3 (foreign equity held), {fa['label']}." if fa else "No US trades entered.",
             "One line per purchase lot held at any time in the calendar year. Each value at SBI's TT buying rate on its own date: "
             "the purchase day for the initial value, the day of the highest value (shares × that day's close × that day's "
             "rate) for the peak, 31 December for the closing balance, each dividend's and sale's day for the income and proceeds.",
             "Fill the entity's address and ZIP code from its annual report. The broker account itself (its cash) goes in Table "
             "A2, from your broker's statement; it isn't here.",
             "Schedule FA is filed with the return by its due date. Since 1 Oct 2024 the Black Money Act's ₹10 lakh penalty "
             "doesn't apply when foreign assets other than property total ₹20 lakh or less, but the disclosure has no minimum."]
    if fa and fa.get("missing_prices"):
        notes.append("No prices for " + ", ".join(fa["missing_prices"]) + ": their peak value, and the closing value of shares still held on 31 December, are blank. Use your broker's statement.")
    if fa and fa.get("fallback"):
        notes.append("Some rates are the RBI reference rate because SBI's rate for that date isn't known.")
    return table("fa", "Schedule FA, Table A3 (foreign equity)", COLS_FA, rows, notes)


def tables(g: dict) -> list[dict]:
    return [t_112a(g), t_112a_portal(g), t_cg(g), t_cg_periods(g), t_os(g), t_business(g), t_general(g), t_setoff(g), t_cfl(g),
            t_tax_paid(g), t_tti(g), t_foreign(g), t_form67(g), fa_table(g["fa"])]


IN_ONLY = ", Indian shares and funds"       # beside the US shares' own lines


def form_fits(g: dict) -> str:
    """Which return the year's figures from these files point to (DP2-011: ITR-2 was said for an empty year and for a year of
    dividends only). ITR-1 is the resident's form for salary, one house and other sources up to ₹50 lakh of income: the
    files can't tell those, so a dividends-only year says the condition."""
    y = g["y"]
    if y["intraday"]["count"] or y["business"]["segments"]:
        return "ITR-3 (business income: intraday or F&O)"
    if g.get("rows") or g.get("unit_rows") or y.get("count") or y.get("foreign") or g.get("fa") or g.get("us_div"):
        return "ITR-2 (capital gains or foreign assets, no business income)"
    if g.get("div_lines"):
        return "ITR-1 if your total income is ₹50 lakh or less (dividends, no capital gains), else ITR-2"
    return "Nothing in your files for this year"


def summary(g: dict) -> list[tuple[str, str]]:
    y = g["y"]
    t = y.get("total") or {}
    out = [("Financial year", f"{y['label']} (assessment year {g['fy'] + 1}-{str(g['fy'] + 2)[2:]})"),
           ("Return that fits", form_fits(g)),
           (f"Short-term gains{IN_ONLY if y.get('foreign') else ''} (net)", money(y["stcg"]["net"])),
           (f"Long-term gains{IN_ONLY if y.get('foreign') else ''} (net)", money(y["ltcg"]["net"])),
           *([("US shares: short-term gains (net)", money(y["foreign"]["st"]["net"])),
              ("US shares: long-term gains (net)", money(y["foreign"]["lt"]["net"]))] if y.get("foreign") else []),
           ("Section 112A exemption used", money(y["exemption"]["used"])),
           ("Intraday result", money(y["intraday"]["pnl"])), ("F&O, commodity and currency result after charges", money(y["business"]["net"])),
           ("Dividends in the year (India)", money(sum(r["amount"] for r in g["div_lines"])))]
    if g["us_div"]:
        out.append(("US dividends in rupees (Rule 115)", money(g["us_div"]["inr"])))
        out.append(("Foreign tax credit (lower of US tax and Indian tax on it)", money(g["us_div"]["ftc"]["credit"])))
    if t.get("available"):
        out.append(("Total tax estimate (" + ("new" if t["regime"] == "new" else "old") + " regime, with cess)", money(t["total"])))
        if t.get("rounded"):          # the way the return rounds them (DH-004)
            out.append(("Total income, rounded to ₹10 (section 288A)", money(t["rounded"]["income"])))
            out.append(("Tax, rounded to ₹10 (section 288B)", money(t["rounded"]["tax"])))
    advance, later = adv.split_paid(g["fy"], g["paid"])
    out.append(("Advance tax entered", money(sum(p["amount"] for p in advance))))
    if later:
        out.append(("Self-assessment tax entered", money(sum(p["amount"] for p in later))))
    out.append(("TDS entered", money(g["tds"])))
    p = g.get("payable")
    if p:                             # DH-003: the year's tax, what's paid and the interest, as one figure
        out.append(("Interest under sections 234A, 234B and 234C", money(p["interest_234a"] + p["interest_234b"] + p["interest_234c"])))
        out.append(("Payable now, with the interest" + (" and late fee" if p["fee_234f"] else ""), money(p["total"])))
        if not p.get("return_needed", True):       # RC2B-003: a year within the basic exemption needs no return, so no late fee
            out.append(("Return needed", f"No: total income {money(p['income'])} is within the {money(p['exempt'])} basic exemption limit (section 139(1))"))
    if g.get("audit"):
        out.append(("Tax audit (section 44AB)", "Applies: report by " + tax_due.day(tax_due.due(g["fy"], "audit_report")["date"])
                    + ", return by " + tax_due.day(tax_due.due(g["fy"], "audit")["date"])))
    if g["fa"]:
        out.append((f"Schedule FA lines (calendar year {g['fy']})", str(len(g["fa"]["rows"]))))
    return out


def _india_day(at) -> str:
    """The India day of a stored upload time (UTC, "2026-10-26T22:30+00:00" is 27 Oct): the first ten characters were the UTC date,
    a day behind from midnight to 5:30 AM (RC3M-004)."""
    try:
        t = datetime.fromisoformat(str(at))
    except ValueError:
        return str(at or "")[:10]
    return (t.astimezone(IST) if t.tzinfo else t).date().isoformat()


def sources(g: dict) -> list[str]:
    out = []
    for f in g["files"][-20:]:
        # DH-007: the F&O lines a file brought are said too (it read "38 trades" beside 1,11,202 F&O lines), and "1 trade"
        n, fno = int(f.get("trades") or 0), int(f.get("fno_lines") or 0)
        what = ", ".join(x for x in (f"{n:,} trade{'' if n == 1 else 's'}" if n or not fno else "",
                                     f"{fno:,} F&O, commodity and currency line{'' if fno == 1 else 's'}" if fno else "") if x)
        out.append(f"Your file {f.get('name')} ({f.get('broker') or 'broker'}, {what}, uploaded {_day(_india_day(f.get('at')))}).")
    if g["mf_count"]:
        out.append(f"Your mutual fund statement (CAS): {g['mf_count']} realised sales in all years.")
    if g["us_count"]:
        out.append(f"Your US trades: {g['us_count']} entered or uploaded in Money · US stocks.")
    srcs = {v for v in g["fmv_src"].values() if v}
    if srcs:
        out.append("31 Jan 2018 prices: " + ", ".join(sorted({"yours": "typed in by you", "your file": "from your broker's file",
                                                                "looked up": "the stored price history's high that day"}.get(s, s) for s in srcs)) + ".")
    out.append("Dividends: " + {"files": "your dividend files", "estimated": "estimated from your holdings and the dividends the companies declared"}.get(g["div_source"], "none in this year") + ".")
    out.append("Bonuses and splits: the stored corporate actions of each company.")
    if g["us_count"] or g["us_div"]:
        out.append("Rupees a dollar: SBI's TT buying rate from its daily rate sheets (RBI reference rate where SBI's isn't known, labelled).")
    out.append("Advance tax, self-assessment tax and TDS: the figures you entered in Money · Tax tools.")
    return out


def assumptions(g: dict) -> list[str]:
    out = [LABEL, CHECK] + list(tax_lots.NOTES)
    if g["us_count"] or g["us_div"]:
        out += us.ASSUMPTIONS
    return out


# ---------- the files ----------
def csv_text(t: dict) -> str:
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\r\n")
    w.writerow([t["title"]])
    w.writerow([LABEL])
    w.writerow(t["columns"])
    for r in t["rows"]:
        w.writerow([_safe(v) for v in r])
    for n in t["notes"]:
        w.writerow(["Note", _safe(n)])
    return out.getvalue()


def portal_csv(t: dict) -> str:
    """The 112A upload layout: the header and the lines only, nothing above or below."""
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\r\n")
    w.writerow([_safe(v) for v in t["columns"]])
    for r in t["rows"]:
        w.writerow([_safe(v) for v in r])           # a name or ISIN that starts like a formula is kept as text
    return out.getvalue()


_NUMBER = re.compile(r"[+-](?:\d+(?:\.\d*)?|\.\d+|(?:\d{1,3}(?:,\d{3})+|\d{1,2}(?:,\d{2})+,\d{3})(?:\.\d*)?)(?:[eE][+-]?\d+)?")


def _safe(v):
    """A text cell a spreadsheet won't run as a formula. "=" and "@" (and a tab or return) are always escaped; "+" and "-"
    only when the whole value isn't a plain signed number ("-1,234.50" and "-1,23,456" are, "-2+3" is not)."""
    if v is None:
        return ""
    if isinstance(v, str) and v[:1] in ("=", "+", "-", "@", "\t", "\r") and not (v[:1] in ("+", "-") and _NUMBER.fullmatch(v)):
        return "'" + v
    return v


def to_xlsx(g: dict) -> bytes:
    y = g["y"]
    read = [[f"ITR-ready schedules, {y['label']}"], [LABEL], [CHECK], [], ["Summary"]] + [[a, b] for a, b in summary(g)]
    read += [[], ["Not covered here"]] + [[s] for s in not_covered(g)]
    read += [[], ["Where the figures come from"]] + [[s] for s in sources(g)] + [[], ["Assumptions"]] + [[s] for s in assumptions(g)]
    sheets = [("Read me", read, {0, 4})]
    for t in tables(g):
        rows = [[t["title"]], [LABEL], t["columns"]] + t["rows"] + [[]] + [["Note", n] for n in t["notes"]]
        sheets.append(((t.get("sheet") or t["title"].split(" (")[0].replace("Schedule ", ""))[:31], rows, {0, 2}))
    return xlsx_write.workbook(sheets)


FILE_NAMES = {"112a": "schedule-112A.csv", "112a_portal": "schedule-112A-portal-upload.csv", "cg": "schedule-CG.csv",
              "cg_periods": "schedule-CG-table-F.csv", "os": "schedule-OS-dividends.csv", "business": "ITR-3-business-income.csv",
              "tax_paid": "schedule-IT-tax-paid.csv", "foreign": "schedules-FSI-TR.csv", "form67": "form-67-workings.csv",
              "general": "part-A-general-audit.csv", "setoff": "schedules-CYLA-BFLA.csv", "cfl": "schedule-CFL.csv", "tti": "part-B-TTI-interest.csv",
              "fa": "schedule-FA-A3.csv"}


def to_zip(g: dict) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("README.txt", "\r\n".join([f"ITR-ready schedules, {g['y']['label']}", LABEL, CHECK, ""] + [f"{a}: {b}" for a, b in summary(g)]
                                              + ["", "Not covered here:"] + not_covered(g)
                                              + ["", "Where the figures come from:"] + sources(g)))
        for t in tables(g):
            z.writestr(FILE_NAMES[t["key"]], (portal_csv(t) if t["key"] == "112a_portal" else csv_text(t)).encode("utf-8-sig"))
    return out.getvalue()


def to_pdf(g: dict) -> bytes:
    """The pack for your CA: the summary, every schedule, the tax estimate's workings, the assumptions and the data
    sources, in one landscape PDF."""
    from xml.sax.saxutils import escape
    from reportlab.lib.colors import HexColor
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from .deck import _fonts
    _fonts()
    y = g["y"]
    from reportlab.pdfbase.pdfmetrics import stringWidth
    body = ParagraphStyle("b", fontName="Body", fontSize=9, leading=12)
    small = ParagraphStyle("s", parent=body, fontSize=7.5, leading=10, textColor=HexColor("#5B6475"))
    head = ParagraphStyle("h", fontName="Head", fontSize=18, leading=22, spaceAfter=4)
    h2 = ParagraphStyle("h2", fontName="Body-Bold", fontSize=11.5, leading=15, spaceBefore=10, spaceAfter=4)
    label = ParagraphStyle("l", parent=body, fontName="Body-Bold", textColor=HexColor("#8A4B00"))
    buf = io.BytesIO()
    page = landscape(A4)
    doc = SimpleDocTemplate(buf, pagesize=page, leftMargin=12 * mm, rightMargin=12 * mm, topMargin=12 * mm, bottomMargin=12 * mm,
                            title=f"Pack for your CA, {y['label']}", author="StratLab")
    width = page[0] - 24 * mm
    grid = TableStyle([("FONT", (0, 0), (-1, -1), "Body", 7), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                       ("LINEBELOW", (0, 0), (-1, -1), 0.3, HexColor("#DDE3EA")), ("BACKGROUND", (0, 0), (-1, 0), HexColor("#F2F4F7")),
                       ("LEFTPADDING", (0, 0), (-1, -1), 2), ("RIGHTPADDING", (0, 0), (-1, -1), 2)])

    def fmt(v, places=None):
        if v is None:
            return ""
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            # DH-007: Indian grouping, as everywhere else (it printed 395,574,093.50); RC2B-016: the app's own minus sign, and two
            # places down a whole column when any of it has paise ("302.50" and "1,762.50" stood beside whole numbers)
            return indian(v, places).replace("-", "\u2212")
        return str(v)

    def tbl(t: dict) -> list:
        out = [Paragraph(escape(t["title"]), h2)]
        if t["rows"]:
            n = len(t["columns"])
            rows = t["rows"][:400]
            places = [2 if any(isinstance(r[i], float) and not float(r[i]).is_integer() for r in rows if i < len(r)
                               and isinstance(r[i], (int, float)) and not isinstance(r[i], bool)) else None for i in range(n)]
            texts = [[fmt(r[i], places[i]) if i < len(r) else "" for i in range(n)] for r in rows]
            # RC2B-016: every column at least as wide as its longest unbreakable piece (a date, an ISIN, a figure, a header word), so
            # no word breaks mid-word; the room left goes to the columns with text that can wrap. The type steps down when even
            # that does not fit the page.
            pad, size = 5, 6.5            # the cell's 2 + 2 points of padding, and a point to spare
            while True:
                hard = [max([stringWidth(w, "Body-Bold", size) for w in t["columns"][i].split()] +
                            [stringWidth(w, "Body", size) for tx in texts for w in tx[i].split()] + [0]) + pad for i in range(n)]
                if sum(hard) <= width or size <= 4.5:
                    break
                size -= 0.5
            soft = [min(max([stringWidth(tx[i], "Body", size) for tx in texts] + [0]) + pad, 70 * mm) for i in range(n)]
            grow = [max(0.0, s - h) for s, h in zip(soft, hard)]
            spare = max(0.0, width - sum(hard))
            widths = [h + (spare * g / sum(grow) if sum(grow) else spare / n) for h, g in zip(hard, grow)]
            if sum(widths) > width:
                widths = [w * width / sum(widths) for w in widths]
            cell = ParagraphStyle("c", fontName="Body", fontSize=size, leading=size + 1.5)
            head_cell = ParagraphStyle("hc", fontName="Body-Bold", fontSize=size, leading=size + 1.5)
            data = [[Paragraph(escape(c), head_cell) for c in t["columns"]]] + [[Paragraph(escape(x), cell) for x in tx] for tx in texts]
            out.append(Table(data, colWidths=widths, repeatRows=1, style=grid))
            if len(t["rows"]) > 400:
                out.append(Paragraph(f"{len(t['rows'])} lines in all; the spreadsheet has every one.", small))
        else:
            out.append(Paragraph("Nothing to report in this year from your files.", small))
        out += [Paragraph("• " + escape(n), small) for n in t["notes"]]
        return out

    # DH-013: a cover a CA can file it by: name and PAN to fill in (StratLab keeps neither), the assessment year
    cover = [["Name", "(fill in)"], ["PAN", "(fill in)"], ["Assessment year", f"{g['fy'] + 1}-{str(g['fy'] + 2)[2:]}"],
             ["Financial year", y["label"]], ["Return that fits", form_fits(g)]]
    story = [Paragraph(f"Pack for your CA, {escape(y['label'])}", head), Paragraph(escape(LABEL), label), Paragraph(escape(CHECK), small),
             Spacer(1, 6), Table(cover, colWidths=[50 * mm, 150 * mm], style=TableStyle([("FONT", (0, 0), (-1, -1), "Body", 10),
                                                                                       ("FONT", (0, 0), (0, -1), "Body-Bold", 10),
                                                                                       ("LINEBELOW", (0, 0), (-1, -1), 0.3, HexColor("#DDE3EA"))])),
             Spacer(1, 6), Paragraph("Summary", h2),
             Table([[a, b] for a, b in summary(g)], colWidths=[120 * mm, 80 * mm],
                   style=TableStyle([("FONT", (0, 0), (-1, -1), "Body", 9), ("LINEBELOW", (0, 0), (-1, -1), 0.3, HexColor("#DDE3EA"))]))]
    t = y.get("total") or {}
    if t.get("available") and t.get("steps"):
        story += [Paragraph("How the total tax estimate was worked out", h2)] + [Paragraph(f"{i}. " + escape(s), body) for i, s in enumerate(t["steps"], 1)]
    empty = []
    for x in tables(g):
        if x["key"] == "112a_portal":
            continue
        if not x["rows"]:             # DH-013: the empty schedules share one line, not a page each (7 of 11 pages were)
            empty.append(x["title"])
            continue
        story += [PageBreak()] + tbl(x)
    story += [PageBreak()]
    if empty:
        story += [Paragraph("Nothing this year from your files in", h2), Paragraph(escape(" · ".join(empty)) + ".", body)]
    story += [Paragraph("Not covered here", h2)] + [Paragraph("• " + escape(s), body) for s in not_covered(g)]
    story += [Paragraph("Where the figures come from", h2)] + [Paragraph("• " + escape(s), body) for s in sources(g)]
    story += [Paragraph("Assumptions", h2)] + [Paragraph("• " + escape(s), body) for s in assumptions(g)]
    story += [Paragraph("Set-off rules", h2)] + [Paragraph("• " + escape(s), body) for s in tax_lots.SETOFF_RULES]
    story += [Spacer(1, 8), Paragraph(f"Made by StratLab on {_day(g['made'])}. " + escape(LABEL), small)]

    def number(canvas, d):            # DH-007: page numbers
        canvas.setFont("Body", 7)
        canvas.setFillColor(HexColor("#5B6475"))
        canvas.drawRightString(page[0] - 12 * mm, 6 * mm, f"Page {d.page} · Pack for your CA, {y['label']}")
    doc.build(story, onFirstPage=number, onLaterPages=number)
    return buf.getvalue()


def indian(v: float, places: int | None = None) -> str:
    """A number with Indian digit grouping (1,23,45,678.50), whole numbers without decimals unless `places` asks for them."""
    neg, v = v < 0, abs(float(v))
    whole, frac = (f"{v:.2f}".split(".") if places or not float(v).is_integer() else (f"{int(v)}", ""))
    if len(whole) > 3:
        whole = re.sub(r"(\d)(?=(\d{2})+$)", r"\1,", whole[:-3]) + "," + whole[-3:]
    return ("-" if neg else "") + whole + (f".{frac}" if frac else "")


# ---------- routes ----------
def preview(profile, fy: int) -> dict:
    """What the page shows: every schedule's table on Pro; on other plans each schedule's name and how many lines it
    would have."""
    g = gather(profile, fy)
    full = allows(profile["_plan"], "itr_export")
    ts = tables(g)
    cur = tax_lots.fy_of(money_routes.today().isoformat())
    return {"fy": fy, "label": g["y"]["label"], "ay": f"{fy + 1}-{str(fy + 2)[2:]}", "label_text": LABEL, "check": CHECK,
            "locked": not full, "plan": PLANS[FEATURE_PLAN["itr_export"]]["name"], "summary": [{"label": a, "value": b} for a, b in summary(g)],
            "sources": sources(g), "assumptions": assumptions(g), "not_covered": not_covered(g),
            "years": [x for x in range(cur, cur - 6, -1)],
            "tables": [{"key": x["key"], "title": x["title"], "count": len([r for r in x["rows"] if r and r[0] not in ("Total",)]),
                        **({"columns": x["columns"], "rows": x["rows"][:200], "notes": x["notes"]} if full else {})} for x in ts]}


@router.get("")
def itr(fy: int | None = Query(None, ge=2018, le=2100), profile=Depends(current_profile)):
    """The year's ITR schedules from the tax report: Schedule 112A, CG (with Table F), OS, the ITR-3 business figures,
    tax paid, FSI and TR with the Form 67 workings, and Schedule FA. Prepared to help fill the return; not a return."""
    fy = fy or tax_lots.fy_of(money_routes.today().isoformat()) - 1
    return _m().ok(preview(profile, fy))


@router.get("/export")
def itr_export(fy: int = Query(..., ge=2018, le=2100), format: str = Query("xlsx", pattern="^(xlsx|zip|pdf)$"),
               profile=Depends(current_profile)):
    """The schedules as an Excel workbook, a ZIP of CSV files (with the 112A upload layout), or the PDF pack for your CA."""
    M = _m()
    M.need(profile, "itr_export", "The ITR-ready export")
    M.throttle(profile, "tax_export", 60, 3600, "That's a lot of downloads in an hour. Try again a little later.")
    g = gather(profile, fy)
    name = f"stratlab-ITR-{fy_label(fy).replace(' ', '-')}"
    if format == "pdf":
        return Response(to_pdf(g), media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{name}-CA-pack.pdf"'})
    if format == "zip":
        return Response(to_zip(g), media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{name}-schedules.zip"'})
    return Response(to_xlsx(g), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{name}-schedules.xlsx"'})
