"""ITR-ready export and the pack for your CA (/money/itr): one financial year's figures from the tax report laid out
the way the return's schedules ask for them, as an Excel workbook, a ZIP of CSV files and one PDF.

Prepared from the user's own files to help them or their CA fill the return; it is not a return and StratLab files
nothing (filing for someone needs ERI registration with the Income Tax Department; an export doesn't).

The layouts follow the ITR-2 and ITR-3 forms for AY 2026-27 (FY 2025-26), checked on 4 Oct 2026:
- Schedule 112A, columns 1a to 14 in the form's order, 1a "BE"/"AE" for acquired on or before / after 31 Jan 2018 and
  1b (added from AY 2025-26 for the 23 Jul 2024 rate change) for transferred before / on or after 23 Jul 2024. For
  "AE" holdings the portal's CSV upload takes one consolidated row (ISIN INNOTREQUIRD, name CONSOLIDATED), so that
  file is made too. Sources: the portal's 112A/115AD CSV instructions,
  https://static.incometax.gov.in/iec/foservices/assets/itr-shared/documents/112A_115AD_CSV_Instructions.pdf, and
  https://github.com/ankitkr/india-itr-skills/blob/main/skills/itr-112a-csv/SKILL.md (AY 2026-27 portal notes).
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
import zipfile
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from . import instrument_kinds, money_advance_tax as adv, money_dividends as divs, money_routes, money_us_routes
from . import money_us_tax as us, tax_lots, xlsx_write
from .auth import current_profile
from .plans import FEATURE_PLAN, PLANS, allows
from .tax_lots import GF_DATE, RATE_CHANGE, fy_label, money

router = APIRouter(prefix="/money/itr", tags=["money"])
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
}
F_GROUPS = [("111A at 20%", {"st_new"}), ("111A at 15%", {"st_old"}), ("112A at 12.5%", {"lt_new"}), ("112A at 10%", {"lt_old"}),
            ("112 at 12.5%", {"lt_112", "lt_us"}), ("112 at 20%", {"lt_112i", "lt_usi"}), ("At slab rates", {"st_slab", "st_us"})]


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
    c = tax_lots.compute(i["trades"], i["acts"], i["fmv"], i["today"])
    mf = M.tax_mf(profile)
    usr = money_us_routes.for_tax(profile)
    c["realised"] += mf["rows"] + usr["rows"]
    c["names"].update(mf["names"])
    c["names"].update(usr["names"])
    equity, units = tax_lots.split_units(c)
    dv_total = money_routes.dividends_for_tax(profile).get(fy, 0.0)
    y = tax_lots.with_total(tax_lots.year(fy, equity, c["intraday"], limit=None), i["business"], i["income"].get(fy), dv_total,
                            instrument_kinds.other_year(fy, units, c["names"]))
    # dividends: the year's lines, from the user's files or the estimate (as Tax tools shows them)
    stored, est, ahead, rate = money_routes.dividend_parts(uid, fetch=False)
    dview = divs.view(stored, est, ahead, rate, money_routes.today())
    dyear = next((x for x in dview["years"] if x["fy"] == fy), None)
    src = (dyear or {}).get("source") or "none"
    lines = [r for r in (stored["rows"] if src == "files" else est) if tax_lots.fy_of(r["d"]) == fy and r["cur"] == "INR"]
    saved = adv.load(uid)["years"].get(fy) or adv.clean_year({})
    return {"fy": fy, "y": y, "rows": [r for r in equity if r["fy"] == fy], "names": c["names"], "files": i["data"]["files"],
            "fmv_src": i["fmv_src"], "div_lines": lines, "div_source": src, "div_year": dyear,
            "us_div": money_us_routes.us_dividends(profile, fy, y), "fa": money_us_routes.fa_for(profile, fy),
            "us_count": usr["count"], "us_allowed": usr["allowed"], "tds": saved["tds"], "paid": saved["paid"],
            "mf_count": len(mf["rows"]), "made": datetime.now(timezone.utc)}


# ---------- the schedules, as tables ----------
def table(key: str, title: str, columns: list[str], rows: list[list], notes: list[str] | None = None) -> dict:
    return {"key": key, "title": title, "columns": columns, "rows": rows, "notes": notes or []}


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


COLS_112A = ["Share/Unit acquired (1a)", "Share/Unit transferred (1b)", "ISIN Code (2)", "Name of the Share/Unit (3)",
             "No. of Shares/Units (4)", "Sale-price per Share/Unit (5)", "Full Value of Consideration (6) = 4 x 5",
             "Cost of acquisition without indexation (7) = higher of 8 and 9", "Cost of acquisition (8)",
             "If acquired before 01.02.2018, lower of 6 and 11 (9)", "Fair Market Value per share/unit as on 31 Jan 2018 (10)",
             "Total Fair Market Value as on 31 Jan 2018 (11) = 4 x 10", "Expenditure wholly and exclusively in connection with transfer (12)",
             "Total deductions (13) = 7 + 12", "Balance (14) = 6 - 13", "Sold on (for your records)"]


def t_112a(g: dict) -> dict:
    lines = rows_112a(g["rows"], g["names"])
    rows = [[v["1a"], v["1b"], v["isin"], v["name"], round(v["qty"], 4), r2(v["price"]), r2(v["gross"]), r2(v["col7"]), r2(v["cost8"]),
             r2(v["col9"]) if v["1a"] == "BE" else None, r2(v["fmv_each"]) if v["1a"] == "BE" else None,
             r2(v["fmv"]) if v["1a"] == "BE" else None, r2(v["exp"]), r2(v["col13"]), r2(v["col14"]), v["sold"]] for v in lines]
    if lines:
        rows.append(["Total", "", "", "", None, None, r2(sum(v["gross"] for v in lines)), r2(sum(v["col7"] for v in lines)),
                     r2(sum(v["cost8"] for v in lines)), r2(sum(v["col9"] for v in lines if v["1a"] == "BE")), None, None,
                     r2(sum(v["exp"] for v in lines)), r2(sum(v["col13"] for v in lines)), r2(sum(v["col14"] for v in lines)), ""])
    notes = ["Long-term sales of listed shares and equity mutual fund units on which STT was paid (section 112A). Short-term "
             "sales are reported as totals in Schedule CG, not scrip by scrip.",
             "1a: BE = acquired on or before 31 Jan 2018, AE = after. 1b: BE = transferred before 23 Jul 2024, AE = on or "
             "after (every sale in FY 2025-26 is AE). Check the codes against the current year's template on the portal.",
             "Column 9 for shares bought on or before 31 Jan 2018 is the lower of the sale value and the 31 Jan 2018 value, "
             "so the cost (7) is the higher of the actual cost and that, worked out lot by lot.",
             "Full value (6) is before the selling charges; those charges are the expenditure on transfer (12). STT isn't "
             "deductible and isn't included. The ₹1.25 lakh exemption is applied in the return's Schedule SI, not here."]
    if any(v["gf_missing"] for v in lines):
        notes.append("Some lines bought before 1 Feb 2018 have no 31 Jan 2018 price, so their column 9 is 0 and the actual cost "
                     "is used. Enter the price in the tax report to grandfather them.")
    return table("112a", "Schedule 112A (scrip-wise long-term gains)", COLS_112A, rows, notes)


def t_112a_portal(g: dict) -> dict:
    """The portal's upload file: lines for shares acquired on or before 31 Jan 2018 scrip-wise, and everything
    acquired after as one consolidated line."""
    lines = rows_112a(g["rows"], g["names"])
    be = [v for v in lines if v["1a"] == "BE"]
    ae = [v for v in lines if v["1a"] == "AE"]
    rows = [[v["1a"], v["1b"], v["isin"], _plain(v["name"]), round(v["qty"], 4), r2(v["price"]), r2(v["gross"]), r2(v["col7"]),
             r2(v["cost8"]), r2(v["col9"]), r2(v["fmv_each"]), r2(v["fmv"]), r2(v["exp"]), r2(v["col13"]), r2(v["col14"])] for v in be]
    for code in sorted({v["1b"] for v in ae}):
        part = [v for v in ae if v["1b"] == code]
        gross, cost, exp = sum(v["gross"] for v in part), sum(v["col7"] for v in part), sum(v["exp"] for v in part)
        rows.append(["AE", code, "INNOTREQUIRD", "CONSOLIDATED", None, None, r2(gross), r2(cost), r2(cost), None, None, None,
                     r2(exp), r2(cost + exp), r2(gross - cost - exp)])
    return table("112a_portal", "Schedule 112A, the portal's upload layout", COLS_112A[:15], rows,
                 ["The portal takes shares acquired after 31 Jan 2018 as one consolidated line (ISIN INNOTREQUIRD, name "
                  "CONSOLIDATED) and those acquired on or before it scrip by scrip. Download the current template from the "
                  "portal and copy these figures into it: its header must match exactly."])


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
    sums = bucket_sums(g["rows"])
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
    if units:
        for head, label in (("slab", "ETFs and gold bonds, short-term at slab rates"), ("lt", "ETFs and gold bonds, long-term, section 112 at 12.5%"),
                            ("exempt", "Gold bonds redeemed with the RBI (exempt)")):
            part = [r for r in units.get("rows") or [] if r["head"] == head]
            if part:
                rows.append([label, "slab rate" if head == "slab" else "12.5%" if head == "lt" else "exempt", len(part),
                             r2(sum(r["sale"] for r in part)), r2(sum(r["cost"] for r in part)), 0.0, r2(sum(r["gain"] for r in part)),
                             None, None, r2((units.get(head) or {}).get("taxable")) if head != "exempt" else 0.0])
    notes = list(y["steps"]) + [f"Short-term loss left to carry forward: {money(y['carry_forward']['st'])}; long-term: "
                                f"{money(y['carry_forward']['lt'])}. Losses carry forward only when the return is filed by its due date.",
                                f"Exemption under section 112A used: {money(y['exemption']['used'])} of {money(y['exemption']['limit'])}."]
    if g["us_count"] and not g["us_allowed"]:
        notes.append("US share sales aren't included: they are on the " + PLANS[FEATURE_PLAN["us_tax"]]["name"] + " plan.")
    return table("cg", "Schedule CG (capital gains by section)",
                 ["Head", "Rate", "Sales", "Full value of consideration", "Cost of acquisition (after grandfathering or indexation)",
                  "Expenditure on transfer", "Gain or loss", "After set-off", "Exempt (112A)", "Taxable"], rows, notes)


def t_cg_periods(g: dict) -> dict:
    sums = bucket_sums(g["rows"])
    rows = []
    for label, keys in F_GROUPS:
        p = [sum(sums[k]["periods"][i] for k in keys if k in sums) for i in range(5)]
        if any(abs(x) > 0.005 for x in p):
            rows.append([label] + [r2(x) for x in p] + [r2(sum(p))])
    return table("cg_periods", "Schedule CG Table F (gains by when they arose)", ["Rate"] + PERIODS + ["Total"], rows,
                 ["Each sale's gain or loss in the period it was sold, before set-off and the exemption. The return wants the "
                  "figures after set-off and takes no negative cells: a negative period is rolled into the next one, so the "
                  "row still adds up. These periods drive interest under section 234C."])


def t_os(g: dict) -> dict:
    rows, totals = [], [0.0] * 5
    by: dict[str, dict] = {}
    for r in g["div_lines"]:
        k = r.get("isin") or r["sym"]
        c = by.setdefault(k, {"name": r.get("name") or r["sym"], "isin": r.get("isin") or "", "p": [0.0] * 5, "tds": 0.0, "tds_file": False})
        c["p"][period(r["d"])] += r["amount"]
        if r.get("tds"):
            c["tds"] += r["tds"]
            c["tds_file"] = True
    fy = g["fy"]
    for c in sorted(by.values(), key=lambda c: -sum(c["p"])):
        total = sum(c["p"])
        tds = c["tds"] if c["tds_file"] else divs.expected_tds(fy, total)
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
    src = {"files": "your dividend files", "estimated": "an estimate from your holdings and the dividends declared (upload your "
           "broker's dividend statement for the actual figures)", "none": "none found"}[g["div_source"] if g["div_source"] in ("files", "estimated") else "none"]
    notes = [f"Indian dividends from {src}. Gross amounts, before TDS; dividends are taxed at your slab rate.",
             "TDS shown is what the 10% rule gives (once a company's dividends to you pass ₹10,000 in FY 2025-26; ₹5,000 "
             "before) unless your file gave it; Form 26AS and the AIS have what was actually cut.",
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
    if intra["count"]:
        rows.append(["Intraday trading (speculative business, section 43(5))", intra["count"], r2(intra["turnover"]), None,
                     r2(intra["sell"] - intra["buy"]), 0.0, r2(intra["pnl"])])
    for s in biz["segments"]:
        rows.append([f"{s['label']} (non-speculative business)", s["trades"], r2(s["turnover"]), r2(s["turnover_contract"]), r2(s["pnl"]),
                     r2(s["charges"]), r2(s["net"])])
    if biz["segments"]:
        rows.append(["F&O, commodity and currency together", biz["trades"], r2(biz["turnover"]), r2(biz["turnover_contract"]), r2(biz["pnl"]),
                     r2(biz["charges"]), r2(biz["net"])])
    notes = ["ITR-3 for AY 2026-27 asks, in Part A Trading Account, for the turnover and the income of intraday trading and of "
             "futures and options separately.",
             "Turnover method: the sum of the absolute profit or loss of each trade (ICAI Guidance Note on Tax Audit under section "
             "44AB, 2022 edition); for intraday, of each day's round trip per company. Option premium isn't added. The figure "
             "netted per contract (as some broker summaries show) is given beside it.",
             "Income before charges is the profit or loss on the trades; the charges in your broker's file (including STT and "
             "CTT, which business income can deduct) are taken off to get the net."] + list(y.get("filing") or [])
    return table("business", "Business income for ITR-3 (intraday and F&O)",
                 ["Activity", "Trades", "Turnover (sum of absolute profit and loss)", "Turnover netted per contract",
                  "Profit or loss before charges", "Charges", "Net profit or loss"], rows, notes)


def t_tax_paid(g: dict) -> dict:
    fy = g["fy"]
    end = f"{fy + 1}-03-31"
    rows = [["Advance tax" if p["d"] <= end else "Self-assessment tax", p["d"], r2(p["amount"]), "", ""] for p in g["paid"]]
    if g["paid"]:
        adv_t = sum(p["amount"] for p in g["paid"] if p["d"] <= end)
        sa_t = sum(p["amount"] for p in g["paid"] if p["d"] > end)
        rows.append(["Total advance tax", "", r2(adv_t), "", ""])
        rows.append(["Total self-assessment tax", "", r2(sa_t), "", ""])
    if g["tds"]:
        rows.append(["TDS you entered (Schedule TDS)", "", r2(g["tds"]), "", ""])
    dt = (g["div_year"] or {}).get("tds") or {}
    if dt.get("expected"):
        rows.append(["Dividend TDS the 10% rule gives (check Form 26AS)", "", r2(dt["expected"]), "", ""])
    return table("tax_paid", "Tax paid (Schedule IT and TDS)", ["Kind", "Date of deposit", "Amount", "BSR code", "Challan serial number"], rows,
                 ["From the payments entered in Tax tools: those dated by 31 March are advance tax, those after it self-assessment "
                  "tax. Fill the BSR code and challan serial number from each challan (the AIS's 'Payment of taxes' section has "
                  "them); the portal's prefill often misses advance tax challans.",
                  "TDS needs each deductor's TAN and amounts from Form 26AS for Schedule TDS; only the total you entered is here."])


def t_foreign(g: dict) -> dict:
    ud, y = g["us_div"], g["y"]
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
        notes.append("No prices for " + ", ".join(fa["missing_prices"]) + ": their peak and closing values are blank. Use your broker's statement.")
    if fa and fa.get("fallback"):
        notes.append("Some rates are the RBI reference rate because SBI's rate for that date isn't known.")
    return table("fa", "Schedule FA, Table A3 (foreign equity)", COLS_FA, rows, notes)


def tables(g: dict) -> list[dict]:
    return [t_112a(g), t_112a_portal(g), t_cg(g), t_cg_periods(g), t_os(g), t_business(g), t_tax_paid(g), t_foreign(g), t_form67(g),
            fa_table(g["fa"])]


def summary(g: dict) -> list[tuple[str, str]]:
    y = g["y"]
    t = y.get("total") or {}
    out = [("Financial year", f"{y['label']} (assessment year {g['fy'] + 1}-{str(g['fy'] + 2)[2:]})"),
           ("Return that fits", "ITR-3 (business income: intraday or F&O)" if y["intraday"]["count"] or y["business"]["segments"] else "ITR-2 (capital gains, no business income)"),
           ("Short-term gains (net)", money(y["stcg"]["net"])), ("Long-term gains (net)", money(y["ltcg"]["net"])),
           ("Section 112A exemption used", money(y["exemption"]["used"])),
           ("Intraday result", money(y["intraday"]["pnl"])), ("F&O, commodity and currency result after charges", money(y["business"]["net"])),
           ("Dividends in the year (India)", money(sum(r["amount"] for r in g["div_lines"])))]
    if g["us_div"]:
        out.append(("US dividends in rupees (Rule 115)", money(g["us_div"]["inr"])))
        out.append(("Foreign tax credit (lower of US tax and Indian tax on it)", money(g["us_div"]["ftc"]["credit"])))
    if t.get("available"):
        out.append(("Total tax estimate (" + ("new" if t["regime"] == "new" else "old") + " regime, with cess)", money(t["total"])))
    out.append(("Advance tax entered", money(sum(p["amount"] for p in g["paid"] if p["d"] <= f"{g['fy'] + 1}-03-31"))))
    out.append(("TDS entered", money(g["tds"])))
    if g["fa"]:
        out.append((f"Schedule FA lines (calendar year {g['fy']})", str(len(g["fa"]["rows"]))))
    return out


def sources(g: dict) -> list[str]:
    out = []
    for f in g["files"][-20:]:
        out.append(f"Your file {f.get('name')} ({f.get('broker') or 'broker'}, {f.get('trades', 0)} trades, uploaded {str(f.get('at'))[:10]}).")
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
    w.writerow(t["columns"])
    for r in t["rows"]:
        w.writerow(["" if v is None else v for v in r])
    return out.getvalue()


def _safe(v):
    if v is None:
        return ""
    if isinstance(v, str) and v[:1] in ("=", "+", "-", "@", "\t", "\r") and not v[1:2].isdigit():
        return "'" + v
    return v


def to_xlsx(g: dict) -> bytes:
    y = g["y"]
    read = [[f"ITR-ready schedules, {y['label']}"], [LABEL], [CHECK], [], ["Summary"]] + [[a, b] for a, b in summary(g)]
    read += [[], ["Where the figures come from"]] + [[s] for s in sources(g)] + [[], ["Assumptions"]] + [[s] for s in assumptions(g)]
    sheets = [("Read me", read, {0, 4})]
    for t in tables(g):
        rows = [[t["title"]], [LABEL], t["columns"]] + t["rows"] + [[]] + [["Note", n] for n in t["notes"]]
        sheets.append((t["title"].split(" (")[0].replace("Schedule ", "")[:31], rows, {0, 2}))
    return xlsx_write.workbook(sheets)


FILE_NAMES = {"112a": "schedule-112A.csv", "112a_portal": "schedule-112A-portal-upload.csv", "cg": "schedule-CG.csv",
              "cg_periods": "schedule-CG-table-F.csv", "os": "schedule-OS-dividends.csv", "business": "ITR-3-business-income.csv",
              "tax_paid": "schedule-IT-tax-paid.csv", "foreign": "schedules-FSI-TR.csv", "form67": "form-67-workings.csv",
              "fa": "schedule-FA-A3.csv"}


def to_zip(g: dict) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("README.txt", "\r\n".join([f"ITR-ready schedules, {g['y']['label']}", LABEL, CHECK, ""] + [f"{a}: {b}" for a, b in summary(g)]
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
    body = ParagraphStyle("b", fontName="Body", fontSize=9, leading=12)
    small = ParagraphStyle("s", parent=body, fontSize=7.5, leading=10, textColor=HexColor("#5B6475"))
    cell = ParagraphStyle("c", fontName="Body", fontSize=6.5, leading=8)
    head_cell = ParagraphStyle("hc", fontName="Body-Bold", fontSize=6.5, leading=8)
    head = ParagraphStyle("h", fontName="Head", fontSize=18, leading=22, spaceAfter=4)
    h2 = ParagraphStyle("h2", fontName="Body-Bold", fontSize=11.5, leading=15, spaceBefore=10, spaceAfter=4)
    label = ParagraphStyle("l", parent=body, fontName="Body-Bold", textColor=HexColor("#8A4B00"))
    buf = io.BytesIO()
    page = landscape(A4)
    doc = SimpleDocTemplate(buf, pagesize=page, leftMargin=12 * mm, rightMargin=12 * mm, topMargin=12 * mm, bottomMargin=12 * mm,
                            title=f"Pack for your CA, {y['label']}", author="StratLab")
    width = page[0] - 24 * mm
    grid = TableStyle([("FONT", (0, 0), (-1, -1), "Body", 7), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                       ("LINEBELOW", (0, 0), (-1, -1), 0.3, HexColor("#DDE3EA")), ("BACKGROUND", (0, 0), (-1, 0), HexColor("#F2F4F7"))])

    def fmt(v):
        if v is None:
            return ""
        if isinstance(v, float):
            return f"{v:,.2f}"
        return str(v)

    def tbl(t: dict) -> list:
        out = [Paragraph(escape(t["title"]), h2)]
        if t["rows"]:
            n = len(t["columns"])
            # each column as wide as its longest cell needs (within limits), shared out across the page
            need = [min(22, max(9, max((len(fmt(r[i])) for r in t["rows"][:400] if i < len(r)), default=0),
                                max(len(w) for w in t["columns"][i].split()), len(t["columns"][i]) // 5)) for i in range(n)]
            data = [[Paragraph(escape(c), head_cell) for c in t["columns"]]] + [[Paragraph(escape(fmt(v)), cell) for v in r] for r in t["rows"][:400]]
            out.append(Table(data, colWidths=[width * x / sum(need) for x in need], repeatRows=1, style=grid))
            if len(t["rows"]) > 400:
                out.append(Paragraph(f"{len(t['rows'])} lines in all; the spreadsheet has every one.", small))
        else:
            out.append(Paragraph("Nothing to report in this year from your files.", small))
        out += [Paragraph("• " + escape(n), small) for n in t["notes"]]
        return out

    story = [Paragraph(f"Pack for your CA, {escape(y['label'])}", head), Paragraph(escape(LABEL), label), Paragraph(escape(CHECK), small),
             Spacer(1, 6), Paragraph("Summary", h2),
             Table([[a, b] for a, b in summary(g)], colWidths=[120 * mm, 80 * mm],
                   style=TableStyle([("FONT", (0, 0), (-1, -1), "Body", 9), ("LINEBELOW", (0, 0), (-1, -1), 0.3, HexColor("#DDE3EA"))]))]
    t = y.get("total") or {}
    if t.get("available") and t.get("steps"):
        story += [Paragraph("How the total tax estimate was worked out", h2)] + [Paragraph(f"{i}. " + escape(s), body) for i, s in enumerate(t["steps"], 1)]
    for x in tables(g):
        if x["key"] == "112a_portal":
            continue
        story += [PageBreak()] + tbl(x)
    story += [PageBreak(), Paragraph("Where the figures come from", h2)] + [Paragraph("• " + escape(s), body) for s in sources(g)]
    story += [Paragraph("Assumptions", h2)] + [Paragraph("• " + escape(s), body) for s in assumptions(g)]
    story += [Paragraph("Set-off rules", h2)] + [Paragraph("• " + escape(s), body) for s in tax_lots.SETOFF_RULES]
    story += [Spacer(1, 8), Paragraph(f"Made by StratLab on {g['made']:%d %b %Y}. " + escape(LABEL), small)]
    doc.build(story)
    return buf.getvalue()


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
            "sources": sources(g), "assumptions": assumptions(g),
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
