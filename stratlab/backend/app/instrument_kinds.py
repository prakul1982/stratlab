"""What a listed unit is, beyond a company's shares: an exchange-traded fund (equity, gold, silver, debt or
international), a real-estate or infrastructure trust (REIT, InvIT) or a Sovereign Gold Bond (SGB); and how the
tax law treats a sale of each.

A holding or trade is told apart by what the broker's file says: the ISIN (funds' ISINs start INF, the
government's IN00), the exchange's series after the symbol (-GB for gold bonds, -RR for REITs, -IV for InvITs),
the symbol (SGBMAY29I, NIFTYBEES, EMBASSY) and the name. Anything else is a company's shares.

Tax, as the law stands (each rule's source is next to it). Facts and arithmetic; never a view on what to hold:
- Equity ETFs (65% or more in Indian shares), REIT and InvIT units: sections 111A and 112A, like shares.
- Gold, silver and international ETFs: not equity funds. Bought from 1 Apr 2023 and sold before 1 Apr 2025, a
  "specified mutual fund" under section 50AA, so short term at slab rates whatever the holding. Otherwise, sold
  from 23 Jul 2024, long term after 12 months at 12.5% (section 112, no exemption, no indexation), short term at
  slab rates.
- Debt ETFs (more than 65% in debt): bought from 1 Apr 2023, always short term at slab rates (section 50AA);
  bought earlier, as gold ETFs.
- SGBs: redemption at maturity exempt for an individual (section 47(viic)); a sale on the exchange is a capital
  gain, long term after 12 months, 12.5% from 23 Jul 2024. The 2.5% interest is taxed at slab rates."""
import re
from datetime import date

RATE_CHANGE = "2024-07-23"        # Finance (No.2) Act 2024: new rates and holding periods for transfers from this day
SPECIFIED_FROM = "2023-04-01"     # Finance Act 2023, section 50AA: specified mutual fund units bought from this day
SPECIFIED_NEW_DEF = "2025-04-01"  # Finance (No.2) Act 2024 narrowed "specified mutual fund" to >65% debt from FY 2025-26
SGB_PRIMARY_ONLY_FY = 2026        # Finance Act 2026: the maturity exemption only for bonds bought at issue, from 1 Apr 2026
LT_RATE = 0.125                   # section 112 on transfers from 23 Jul 2024, without indexation

# Sources, checked 4 Oct 2026:
# - 50AA and its narrowed definition (only funds with more than 65% in debt and money market instruments from
#   FY 2025-26; gold and international ETFs left out): Finance (No.2) Act 2024; summarised at
#   https://www.zerodhafundhouse.com/blog/gold-etf-taxation-2025/ and
#   https://www.finnovate.in/learn/blog/etf-taxation-india
# - Holding periods from 23 Jul 2024: 12 months for listed securities, 24 for other assets (section 2(42A) as amended
#   by the Finance (No.2) Act 2024; Budget 2024 memorandum). Listed REIT/InvIT units moved from 36 to 12 months:
#   https://www.business-standard.com/budget/news/govt-brings-parity-between-listed-equity-units-of-reits-invits-to-calculate-ltcg-124072301277_1.html
# - 111A and 112A cover "a unit of a business trust" with STT paid on the sale (sections 111A(1), 112A(1)).
# - REIT/InvIT distributions: interest at slab rates (TDS under 194LBA); dividend exempt unless the SPV chose
#   section 115BAA; repayment of debt taxable under 56(2)(xii) beyond the unit's cost (Finance Act 2023):
#   https://cleartax.in/s/taxation-of-reit-and-invit
# - SGB: 47(viic) exempts redemption by an individual; Finance Act 2026 limits it, from 1 Apr 2026, to bonds
#   subscribed at issue and held to maturity:
#   https://www.valueresearchonline.com/learn/mutual-funds/sovereign-gold-bonds-budget-2026-tax-rule-change/
#   Interest of 2.5% a year is "income from other sources" at slab rates, with no TDS (the RBI's SGB FAQs on
#   rbi.org.in).

KINDS = ("stock", "etf", "reit", "invit", "sgb")
FUNDS = ("equity", "gold", "silver", "debt", "intl")
LABELS = {"stock": "Shares", "etf": "ETF", "reit": "REIT", "invit": "InvIT", "sgb": "Gold bond"}
FUND_LABELS = {"equity": "Equity ETF", "gold": "Gold ETF", "silver": "Silver ETF", "debt": "Debt ETF", "intl": "International ETF"}
SECTORS = {"etf": "ETFs", "reit": "REITs and InvITs", "invit": "REITs and InvITs", "sgb": "Sovereign Gold Bonds"}

ETFS = {"MAFANG", "MON100", "MASPTOP50", "MAHKTECH", "MANXT50", "MAN50ETF", "MAM150ETF", "MAKEINDIA", "CONSUMBEES"}
REITS = {"EMBASSY", "MINDSPACE", "BIRET", "NXST", "KRT"}
INVITS = {"INDIGRID", "PGINVIT", "IRBINVIT", "NHIT", "INDINFRAT", "CUBEINVIT", "ANZEN", "IRBINFRA"}
_SERIES = {"GB": "sgb", "RR": "reit", "IV": "invit"}
_ETF_NAME = re.compile(r"(?<![a-z])ETFs?\b|exchange[\s-]*traded|\bBeES\b", re.I)
_REIT_NAME = re.compile(r"\bREIT\b|real\s+estate\s+investment\s+trust", re.I)
_INVIT_NAME = re.compile(r"\bInvIT\b|infrastructure\s+investment\s+trust|infra(?:structure)?\s+trust", re.I)
_MF_NAME = re.compile(r"mutual\s+fund|\bplan\b|\bgrowth\b|\bIDCW\b|\bdirect\b|\bregular\b|\bdividend\s+option|\bfund\b", re.I)
_SGB_NAME =re.compile(r"sovereign\s+gold\s+bond|\bSGB\b|\bGOLDBOND", re.I)
_DEBT = re.compile(r"LIQUID|GILT|GSEC|G-SEC|\bSDL\b|SDL[0-9A-Z]*ETF|BOND|BBETF|\bDEBT\b|MONEY\s*MARKET|OVERNIGHT|TBILL|"
                   r"\b1D\b|ONEDAY|CRISIL\s*IBX|NIFTY\s*\d+\s*YR|\bAAA\b|CORP(?:ORATE)?\s*BOND", re.I)
_INTL = re.compile(r"NASDAQ|MON100|MAFANG|\bFANG|S&P\s*500|MASPTOP|HANG\s*SENG|HNGSNG|MAHKTECH|NYSE|GLOBAL|INTERNATIONAL|"
                   r"\bMSCI\b|JAPAN|CHINA|TAIWAN|\bUS\b|U\.S\.", re.I)


def _plain(symbol) -> tuple[str, str]:
    """(symbol, series) without the exchange around it: "NSE:SGBMAY29I-GB" -> ("SGBMAY29I", "GB")."""
    s = re.sub(r"^(NSE|BSE)[:\s]+", "", str(symbol or "").strip().upper())
    s = re.sub(r"(\.NS|\.BO)$", "", s)
    m = re.match(r"^(.+?)-([A-Z]{2})$", s)
    return (m.group(1), m.group(2)) if m else (s, "")


def classify(symbol=None, isin=None, name=None) -> str:
    """"stock", or "etf-<fund>" (equity, gold, silver, debt, intl), "reit", "invit" or "sgb"; "mf" for a mutual
    fund plan (not covered)."""
    sym, series = _plain(symbol)
    isin = str(isin or "").strip().upper()
    nm = str(name or "").strip()
    if series in _SERIES:
        return _SERIES[series]
    if re.match(r"^SGB[A-Z0-9]{3,14}$", sym) or _SGB_NAME.search(nm) or (isin.startswith("IN00") and re.search(r"gold", nm, re.I)):
        return "sgb"
    if sym in REITS or _REIT_NAME.search(nm):
        return "reit"
    if sym in INVITS or sym.endswith("INVIT") or _INVIT_NAME.search(nm):
        return "invit"
    if sym in ETFS or _ETF_NAME.search(nm) or re.search(r"(BEES|ETF|IETF|CASE)$", sym):
        return "etf-" + fund_of(f"{sym} {nm}")
    if isin.startswith("INF"):          # a fund: exchange-traded unless its name says it's a mutual fund's plan
        return "mf" if _MF_NAME.search(nm) else "etf-" + fund_of(f"{sym} {nm}")
    return "stock"


def fund_of(text: str) -> str:
    """What an ETF holds, from its symbol and name: gold, silver, debt, international or (by default) Indian shares."""
    t = str(text or "")
    if re.search(r"GOLD(?!MAN)", t, re.I):
        return "gold"
    if re.search(r"SILVER", t, re.I):
        return "silver"
    if _DEBT.search(t):
        return "debt"
    if _INTL.search(t):
        return "intl"
    return "equity"


def base(code) -> str:
    """"etf" for any ETF code, else the code itself; "stock" for anything unknown."""
    c = str(code or "stock")
    c = "etf" if c.startswith("etf") else c
    return c if c in KINDS else "stock"


def fund(code) -> str | None:
    c = str(code or "")
    return c[4:] if c.startswith("etf-") and c[4:] in FUNDS else ("equity" if c == "etf" else None)


def label(code) -> str:
    """The badge: "Gold ETF", "REIT", "Gold bond"; "Shares" for a company."""
    f = fund(code)
    return FUND_LABELS[f] if f else LABELS[base(code)]


def tax_class(code) -> str:
    """"equity" for shares, equity ETFs, REITs and InvITs (sections 111A and 112A); "sgb"; "debt" for debt ETFs;
    "other" for gold, silver and international ETFs."""
    b = base(code)
    if b == "sgb":
        return "sgb"
    if b == "etf":
        f = fund(code)
        return "debt" if f == "debt" else "other" if f in ("gold", "silver", "intl") else "equity"
    return "equity"


def code_of(n: dict) -> str:
    """A tax report name entry's code: the one kept from the file, else read from its symbol, ISIN and name."""
    return n.get("kind") or classify(n.get("symbol"), n.get("isin"), n.get("name"))


# ---------- the tax treatment of each sale ----------
def sgb_maturity(symbol) -> str | None:
    """The month a gold bond matures, from its exchange symbol (SGBMAY29I matures in May 2029), as YYYY-MM."""
    sym, _ = _plain(symbol)
    m = re.match(r"^SGB([A-Z]{3})(\d{2})", sym)
    months = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")
    if not m or m.group(1) not in months:
        return None
    return f"20{m.group(2)}-{months.index(m.group(1)) + 1:02d}"


def _after_months(buy: str, sell: str, months: int) -> bool:
    """Held for more than `months` months: sold after that anniversary of the buy."""
    b = date.fromisoformat(buy)
    y, m = b.year + (b.month - 1 + months) // 12, (b.month - 1 + months) % 12 + 1
    try:
        ann = b.replace(year=y, month=m)
    except ValueError:
        ann = date(y, m, 28)
    return date.fromisoformat(sell) > ann


def treatment(code: str, symbol: str, bought: str, sold: str, fy: int) -> tuple[str, str]:
    """(head, why) for one non-equity sale: "slab" (short term at slab rates), "lt" (long term at 12.5% under
    section 112), "exempt", or "old" (a sale before 23 Jul 2024 taxed under the old rules with indexation, shown
    but not worked out)."""
    tc = tax_class(code)
    if tc == "sgb":
        mat = sgb_maturity(symbol)
        if mat and sold[:7] >= mat:
            if fy < SGB_PRIMARY_ONLY_FY:
                return "exempt", "Gold bond redeemed at maturity: exempt for an individual (section 47(viic))."
            return "lt", ("Gold bond redeemed at maturity, bought on the exchange: from 1 April 2026 the exemption is only "
                          "for bonds subscribed at issue, so this is a long-term gain.")
        if not _after_months(bought, sold, 12):
            return "slab", "Gold bond sold within 12 months: short-term gain at slab rates."
        if sold < RATE_CHANGE:
            return "old", "Gold bond sold on the exchange before 23 Jul 2024: long term under the old rules (10%, or 20% with indexation)."
        return "lt", "Gold bond sold on the exchange after 12 months: long-term gain at 12.5% (section 112)."
    if bought >= SPECIFIED_FROM and (tc == "debt" or sold < SPECIFIED_NEW_DEF):
        return "slab", ("Bought from 1 Apr 2023: a specified mutual fund (section 50AA), so the gain is short term at slab "
                        "rates whatever the holding period.")
    if sold >= RATE_CHANGE:
        if _after_months(bought, sold, 12):
            return "lt", "Listed fund units held over 12 months: long-term gain at 12.5% (section 112), no exemption."
        return "slab", "Held 12 months or less: short-term gain at slab rates."
    if _after_months(bought, sold, 36):
        return "old", "Sold before 23 Jul 2024 after 36 months: long term under the old rules (20% with indexation)."
    return "slab", "Sold before 23 Jul 2024 within 36 months: short-term gain at slab rates."


def adjust_trusts(realised: list[dict], names: dict) -> None:
    """REIT and InvIT units sold before 23 Jul 2024 were long term only after 36 months (12 from that day): the
    rows the share rules called long term in between become short term."""
    for r in realised:
        if r["term"] == "LT" and r["sold"] < RATE_CHANGE and base(code_of(names.get(r["key"]) or {})) in ("reit", "invit"):
            if not _after_months(r["bought"], r["sold"], 36):
                r["term"] = "ST"


def split(realised: list[dict], names: dict) -> tuple[list[dict], list[dict]]:
    """(equity rows, other rows): sales taxed like shares, and the gold, silver, international and debt ETFs and
    gold bonds, which follow their own rules."""
    eq, other = [], []
    for r in realised:
        (eq if tax_class(code_of(names.get(r["key"]) or {})) == "equity" else other).append(r)
    return eq, other


def _r(v, dp=2):
    return None if v is None else round(v, dp)


def other_year(fy: int, rows: list[dict], names: dict) -> dict | None:
    """One financial year's non-equity sales: each with its head, the totals, set-off (short-term losses against
    any gains, long-term losses only against long-term gains) and what goes into the tax estimate. None when the
    year has none."""
    mine = [r for r in rows if r["fy"] == fy]
    if not mine:
        return None
    out_rows, sums = [], {"slab": [0.0, 0.0], "lt": [0.0, 0.0]}
    exempt = old = 0.0
    for r in sorted(mine, key=lambda r: (r["sold"], r["key"])):
        n = names.get(r["key"]) or {}
        code = code_of(n)
        head, why = treatment(code, n.get("symbol") or r["key"], r["bought"], r["sold"], fy)
        if head in sums:
            sums[head][0 if r["gain"] >= 0 else 1] += abs(r["gain"])
        elif head == "exempt":
            exempt += r["gain"]
        else:
            old += r["gain"]
        out_rows.append({"key": r["key"], "kind": code, "label": label(code), "bought": r["bought"], "sold": r["sold"],
                         "qty": round(r["qty"], 4), "cost": _r(r["cost"]), "sale": _r(r["sale"]), "gain": _r(r["gain"]),
                         "head": head, "why": why})
    slab_gain, slab_loss = sums["slab"]
    lt_gain, lt_loss = sums["lt"]
    st_left = max(0.0, slab_loss - slab_gain)
    slab_net = max(0.0, slab_gain - slab_loss)
    take = min(st_left, max(0.0, lt_gain - lt_loss))
    st_left -= take
    lt_net = max(0.0, lt_gain - lt_loss - take)
    lt_left = max(0.0, lt_loss - lt_gain)
    return {"rows": out_rows[:500], "count": len(out_rows),
            "slab": {"gains": _r(slab_gain), "losses": _r(slab_loss), "taxable": _r(slab_net)},
            "lt": {"gains": _r(lt_gain), "losses": _r(lt_loss), "taxable": _r(lt_net), "rate": LT_RATE, "tax": _r(lt_net * LT_RATE)},
            "exempt": _r(exempt), "old": _r(old) if any(x["head"] == "old" for x in out_rows) else None,
            "carry_forward": {"st": _r(st_left), "lt": _r(lt_left)}}


NOTES = [
    "Equity ETFs (65% or more in Indian shares), REIT and InvIT units are taxed like shares: sections 111A and 112A, "
    "long term after 12 months, and their gains share the ₹1.25 lakh exemption.",
    "REIT and InvIT units sold before 23 Jul 2024 were long term only after 36 months.",
    "Gold, silver and international ETFs: long term after 12 months at 12.5% (section 112, no exemption); short term at "
    "your slab rate. Units bought from 1 Apr 2023 and sold before 1 Apr 2025 were short term at slab rates whatever the "
    "holding (section 50AA).",
    "Debt ETFs bought from 1 Apr 2023: short term at your slab rate, however long they were held (section 50AA).",
    "Sovereign Gold Bonds: a sale on the exchange is a capital gain (long term after 12 months, 12.5% from 23 Jul 2024). "
    "Redemption at maturity is exempt for an individual; from 1 Apr 2026, only for bonds subscribed at issue and held "
    "to maturity. The 2.5% yearly interest is taxed at your slab rate and isn't in these files.",
    "REIT and InvIT distributions come in parts taxed differently: interest at your slab rate, dividend exempt unless "
    "the trust's company opted for the lower corporate tax rate (section 115BAA), and repayment of debt taxable once "
    "the total received passes the units' cost (section 56(2)(xii)). The trust's statement gives the split; "
    "distributions aren't in these files.",
    "This estimate sets off losses within the non-equity sales and within share sales, not across the two. The law "
    "allows short-term losses against any capital gain and long-term losses against any long-term gain.",
]
