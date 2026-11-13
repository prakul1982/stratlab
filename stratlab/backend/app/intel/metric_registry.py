"""Every operating and sector figure a theme deck can show, in one table (R27, the owner's outside review of the eight R26 decks: Semiconductors
fell to 8.0 because remaining performance obligations and deferred revenue headlined for chip makers, "median RPO growth −3.9% covers 21 of 53").

Each figure: its id, label, what it measures and how it is worked out, its unit, period and source, its limitation, and the business models it
APPLIES to (theme_check.MODELS' families, R25, and the structures below read from a company's official industry). Every company and figure is in
one of four states, never a zero for a missing figure and never a proxy in place of the real one:
- value: the figure as filed or worked out;
- unavailable ("–"): the figure applies to the company's model but isn't filed, or wasn't found, in the sources the app reads;
- not applicable ("n/a"): the figure doesn't apply to how the company earns (RPO for a chip maker, CET1 for an insurer);
- not comparable ("n.c."): the figure is on another basis or period than the rest of its table (a fiscal year more than a year older, an amount
  in another currency, an annual-accounts ratio beside filed ones).
Medians and counts use the "value" rows only and say "N of M", M the companies the figure applies to. A figure headlines (a summary tile, a
finding) only when it applies to the main model of its group and at least HEADLINE_COVER of the companies it applies to have it.
The deck's "How the figures are built" page reads each figure's definition, period, source and limitation from here (one source of truth)."""
import re
from datetime import date, datetime
from typing import NamedTuple

VALUE, UNAVAILABLE, NOT_APPLICABLE, NOT_COMPARABLE = "value", "unavailable", "n/a", "n.c."
MARK = {UNAVAILABLE: "–", NOT_APPLICABLE: "n/a", NOT_COMPARABLE: "n.c."}
LEGEND = "– not filed or not found; n/a does not apply to how the company earns; n.c. not comparable (another basis or period)."
HEADLINE_COVER = 0.5            # share of the companies a figure applies to that must have it for the figure to headline
MIN_BASE = 3                    # companies a median needs (theme_data.MIN_BASE, deck.MIN_BASE)
GROWTH_EXTREME = 100.0          # a growth figure above this many % either way is unusual: its base is said beside it
SMALL_BASE = 0.05               # ...and so is one whose starting figure is under this share of its group's median starting figure
STALE_MONTHS = {"year": 15, "quarter": 4}   # a figure's period this many months before its table's latest is not comparable


class Metric(NamedTuple):
    id: str
    label: str
    definition: str             # what it measures and how it is worked out
    unit: str                   # pct (a share, %), chg (a change, %), x (times), amt (money in the theme's unit), days
    period: str                 # "year" or "quarter" (how stale a period may be: STALE_MONTHS)
    source: str                 # period and source, as the notes page prints it
    limit: str                  # the figure's limitation
    applies: frozenset          # the families and structures it applies to; "*" every company of its regions
    regions: tuple = ("IN", "US")
    headline: bool = True       # whether it may headline at all (an amount never does)
    group: str = ""             # the sector family whose page carries it ("bank", "insurer", "us", "orders"); "" a page table's own figure


def _m(id_, label, definition, unit, period, source, limit, applies, regions=("IN", "US"), headline=True, group=""):
    return Metric(id_, label, definition, unit, period, source, limit, frozenset(applies), tuple(regions), headline, group)


_YEAR_SRC = "Latest full year; annual accounts"
_LAST_SRC = "Latest reported; annual accounts"
BANK = ("bank",)
LENDING = ("bank", "lender")
INSURERS = ("life", "general", "health", "reinsurance")
NON_LIFE = ("general", "health", "reinsurance")
CONTRACTED = ("software", "royalties", "services")          # models paid ahead or under multi-year contracts (RPO, deferred revenue)
# R29: the kinds of utility and of metals business (theme_check.MODELS) are families of their own; a marketplace ("platform") holds no stock
ASSETS_HEAVY = ("making", "capacity", "telecom_services", "resources", "utility", "transport", "semis", "hardware", "regulated_utility", "generation", "mining",
                "metal_processing")
STOCK_HOLDERS = ("making", "resale", "semis", "hardware", "mining", "metal_processing")    # companies that hold goods for sale
RESEARCH = ("making", "semis", "hardware", "software", "royalties", "pharma")
ORDERS = ("defence", "capital_goods", "construction")
_BQ, _IQ, _US = "Latest quarter; exchange filing", "Latest period; exchange filing", "Latest fiscal year; SEC filing"

METRICS = (
    # the page tables' own figures (stored company pages)
    _m("revenue", "Revenue", "Sales of the year; a layer's is its companies' added together", "amt", "year", _YEAR_SRC,
       "Consolidated where filed, else standalone", "*", headline=False),
    _m("sales_1y", "Revenue growth", "Revenue over the year before's, less one; two consecutive full years only", "chg", "year", _YEAR_SRC,
       "One year; deals and demergers move it", "*"),
    _m("ebitda", "EBITDA margin", "Operating profit before depreciation, interest and tax, over revenue", "pct", "year", _YEAR_SRC,
       "None for banks, lenders, insurers; some file whole points", "*"),
    _m("net", "Net margin", "Net profit over revenue; one above the EBITDA margin or unusual that its own filed figures don't give (†) is out of the median", "pct", "year", _YEAR_SRC,
       "Includes other income, exceptional items and tax", "*"),
    _m("roce", "ROCE", "Operating profit before interest and tax over equity plus debt", "pct", "year", _LAST_SRC, "None for banks, lenders, insurers", "*"),
    _m("roe", "ROE", "Net profit over shareholders' equity", "pct", "year", _LAST_SRC, "Debt raises it; lenders' and others' differ", "*"),
    _m("nii_assets", "NII / assets", "Interest earned less interest paid, over average total assets; filed results annualised where read, "
       "else the latest full year", "pct", "year", "Latest half year, exchange filing; else annual accounts",
       "Not the bank's own net interest margin (NIM)", BANK, ("IN",)),
    _m("gnpa", "Gross NPA", "Gross non-performing assets over gross advances", "pct", "quarter", "Latest quarter given; results", "One quarter's end", LENDING, ("IN",)),
    _m("nnpa", "Net NPA", "Net non-performing assets over net advances", "pct", "quarter", "Latest quarter given; results", "One quarter's end; after provisions",
       LENDING, ("IN",)),
    _m("deposit_growth", "Deposit growth", "Deposits against a year before", "chg", "year", "Reported balance sheets", "Two balance-sheet dates only", BANK, ("IN",)),
    _m("pe", "P/E", "Market value over net profit of the last four quarters", "x", "year", "Last close; last four quarters", "None for a loss-maker", "*"),
    _m("pb", "P/B", "Market value over shareholders' equity", "x", "year", "Last close; latest balance sheet", "Book value at the balance-sheet date", "*"),
    _m("ev_ebitda", "EV/EBITDA", "Market value plus debt less cash, over the year's EBITDA", "x", "year", "Last close; latest full year",
       "None for banks, lenders, insurers", "*"),
    _m("cap", "Market value", "Price times shares in issue", "amt", "year", "Last close", "Moves with the price every day", "*", headline=False),
    # India banks: the exchange's results filing (banking format)
    _m("gnpa_f", "Gross NPA", "Gross non-performing assets as a share of gross advances, as filed for the quarter's end", "pct", "quarter", _BQ,
       "As filed; standalone", LENDING, ("IN",), group="bank"),
    _m("nnpa_f", "Net NPA", "Net non-performing assets as a share of net advances, as filed for the quarter's end", "pct", "quarter", _BQ,
       "As filed; standalone", LENDING, ("IN",), group="bank"),
    _m("cet1", "CET1 ratio", "Common equity tier 1 capital over risk-weighted assets, as filed (the filing has no total capital adequacy ratio)", "pct",
       "quarter", _BQ, "Core capital only; no total capital ratio filed", BANK, ("IN",), group="bank"),
    _m("roa_f", "ROA", "Net profit for the year to date, annualised, over the average of total assets at the period's end and a year earlier "
       "(banks file their own ROA on different bases, some annualised and some not)", "pct", "quarter", _BQ, "Annualised from the year to date",
       LENDING, ("IN",), group="bank"),
    _m("nii_assets_f", "NII / assets", "Net interest income (interest earned less interest expended) for the year to date, annualised, over the "
       "average of total assets at the period's end and a year earlier", "pct", "quarter", _BQ, "Annualised; not the bank's own NIM", BANK, ("IN",),
       group="bank"),
    _m("nii_q", "NII, quarter", "Net interest income: interest earned less interest expended in the quarter", "amt", "quarter", _BQ, "As filed; standalone",
       LENDING, ("IN",), headline=False, group="bank"),
    _m("nii_growth_f", "NII growth", "Net interest income against the same quarter a year before", "chg", "quarter", _BQ, "As filed; standalone",
       LENDING, ("IN",), group="bank"),
    _m("advances_growth", "Advances growth", "Advances against a year before, from the half-year balance sheets", "chg", "quarter", _BQ,
       "Two balance-sheet dates only", LENDING, ("IN",), group="bank"),
    _m("deposit_growth_f", "Deposit growth", "Deposits against a year before, from the half-year balance sheets", "chg", "quarter", _BQ,
       "Two balance-sheet dates only", BANK, ("IN",), group="bank"),
    _m("credit_cost", "Credit cost", "Provisions other than tax for the year to date, annualised, over the average of advances at the period's end "
       "and a year earlier", "pct", "quarter", _BQ, "Annualised from the year to date", LENDING, ("IN",), group="bank"),
    _m("nim", "NIM", "Net interest margin, as the filing states it", "pct", "quarter", _BQ, "Only where a filing states it", BANK, ("IN",), group="bank"),
    _m("casa", "CASA", "Current and savings deposits as a share of deposits, as the filing states it", "pct", "quarter", _BQ,
       "Only where a filing states it", BANK, ("IN",), group="bank"),
    # India insurers: the exchange's results filing (life and general formats); each type summarised on its own
    _m("solvency", "Solvency ratio", "Available over required solvency margin, as filed for the quarter's end", "x", "quarter", _IQ,
       "As filed; life and general differ", INSURERS, ("IN",), group="insurer"),
    _m("claims_ratio", "Claims ratio", "Incurred claims over net premium earned, as filed for the year to date (general and health insurers)", "pct",
       "quarter", _IQ, "General and health insurers only", NON_LIFE, ("IN",), group="insurer"),
    _m("combined_ratio", "Combined ratio", "Claims, commission and expenses over premium, as filed for the year to date (general and health insurers)",
       "pct", "quarter", _IQ, "General insurers and health insurers; no investment income", NON_LIFE, ("IN",), group="insurer"),
    _m("persistency_13", "13th-month persistency", "Policies still paying premium in their 13th month, as filed for the year to date (life insurers)",
       "pct", "quarter", _IQ, "Life insurers only", ("life",), ("IN",), group="insurer"),
    _m("premium_growth", "Premium growth", "Gross premium against the same quarter a year before", "chg", "quarter", _IQ, "As filed; one quarter",
       INSURERS, ("IN",), group="insurer"),
    _m("vnb_margin", "VNB margin", "Value of new business over annualised premium equivalent, as the filing states it", "pct", "quarter", _IQ,
       "Only where a filing states it", ("life",), ("IN",), group="insurer"),
    # US companies outside finance: the SEC's company facts
    _m("sbc_share", "SBC / revenue", "Stock-based compensation over revenue, the latest fiscal year", "pct", "year", _US, "No cash cost in the year",
       ("us",), ("US",), group="us"),
    _m("capex_share", "Capex / revenue", "Capital spending (payments for property, plant and equipment) over revenue, the latest fiscal year", "pct",
       "year", _US, "One fiscal year; spending is lumpy", ASSETS_HEAVY, ("US",), group="us"),
    _m("capex", "Capex", "Capital spending (payments for property, plant and equipment), the latest fiscal year", "amt", "year", _US,
       "Filings in US dollars only", ASSETS_HEAVY, ("US",), headline=False, group="us"),
    _m("inventory_days", "Inventory days", "Inventory at the fiscal year's end over that year's cost of revenue, times 365", "days", "year", _US,
       "One balance-sheet date", STOCK_HOLDERS, ("US",), group="us"),
    _m("rd_share", "R&D / revenue", "Research and development expense over revenue, the latest fiscal year", "pct", "year", _US,
       "As expensed; capitalised R&D not in it", RESEARCH, ("US",), group="us"),
    _m("rpo_cover", "RPO / revenue", "Remaining performance obligations at the latest date filed, over the latest fiscal year's revenue", "x", "year",
       _US, "Contracts can be cancelled; software and licensing models only", CONTRACTED, ("US",), group="us"),
    _m("rpo_growth", "RPO growth", "Remaining performance obligations against a year before", "chg", "year", _US,
       "Software and licensing models only", CONTRACTED, ("US",), group="us"),
    _m("deferred_growth", "Deferred revenue growth", "Deferred revenue (contract liabilities) at the fiscal year's end against a year before", "chg",
       "year", _US, "Software and licensing models only", CONTRACTED, ("US",), group="us"),
    _m("fcf_margin", "FCF margin", "Free cash flow (cash from operations less capital spending) over revenue, the latest fiscal year", "pct", "year",
       _US, "One fiscal year", ("us",), ("US",), group="us"),
    # India defence and capital goods: only where a business update the app reads states it, with its period
    _m("order_book", "Order book", "Orders in hand as the company's own update states them, at the date it gives", "amt", "quarter",
       "Latest business update filed with the exchange", "As the company states it; not revenue", ORDERS, ("IN",), headline=False, group="orders"),
    _m("order_inflow", "Order inflow", "New orders in the period, as the company's own update states them", "amt", "quarter",
       "Latest business update filed with the exchange", "As the company states it; not revenue", ORDERS, ("IN",), headline=False, group="orders"),
)
BY_ID = {m.id: m for m in METRICS}
# figures no source the app reads carries for these structures: listed so the report and the notes can say so, never filled by a proxy
NOT_READ = {"pharma": ("R&D / revenue and the export and domestic mix aren't in any filing the app reads for Indian companies",),
            "defence": ("The order book and order inflow are read only from a business update the company files and the app reads",),
            "capital_goods": ("The order book and order inflow are read only from a business update the company files and the app reads",)}

# the structures a company's official industry shows, and the family of theme_check.MODELS each maps to when its layer has no model (R27)
STRUCTURES = (
    ("semis", r"semiconductor|integrated circuit|\bchips?\b|wafer"),
    ("hardware", r"computer (?:peripheral|storage|communications) equipment|electronic computers|electronic components|printed circuit|"
                 r"computer hardware|telephone (?:&|and) telegraph apparatus"),
    ("software", r"prepackaged software|software|computer programming|computer integrated systems|data processing"),
    ("pharma", r"pharma|drugs?\b|biolog|biotech|medicinal"),
    ("defence", r"defen[cs]e|aerospace|ordnance|guided missile|ship ?building"),
    ("capital_goods", r"heavy electrical|industrial machinery|electrical equipment|capital goods|construction (?:&|and) engineering|"
                      r"civil construction|engineering services"),
    ("chemicals", r"chemical|fertili[sz]|agrochemical|pesticide|paints?\b|plastics materials"),
    ("real_estate", r"real estate|realty|residential,? commercial|\breit\b|land subdividers"),
    ("telecom", r"telecom|telephone communications|radiotelephone|cellular|wireless|cable (?:&|and) other pay"),
    ("retail", r"retail|department stores|variety stores|stores?\b|supermarket|e-retail|catalog (?:&|and) mail-order"),
    ("utility", r"power generation|power distribution|power transmission|electric services|electric utilit|integrated power|gas distribution|"
                r"water supply|cogeneration|electric (?:&|and) other services"),
    ("metals", r"iron (?:&|and) steel|steel|alumini?um|copper|zinc|non[- ]ferrous|metals?\b|mining|coal|minerals|ferro"),
)
STRUCTURE_FAMILY = {"semis": "making", "hardware": "making", "software": "software", "pharma": "making", "defence": "making",
                    "capital_goods": "construction", "chemicals": "making", "real_estate": "property", "telecom": "capacity", "retail": "resale",
                    "utility": "utility", "metals": "resources"}
_STRUCT_RX = tuple((k, re.compile(rx, re.I)) for k, rx in STRUCTURES)


def structures(row: dict) -> list[str]:
    """The structures a company's official industry (its path, the exchange's or the SEC's industry) shows, in STRUCTURES' order."""
    text = " ".join(str(row.get(k) or "") for k in ("official_industry", "map_industry", "sector")) + " " + \
        " ".join(str(x) for x in (row.get("industry") or []) if x)
    return [k for k, rx in _STRUCT_RX if rx.search(text)]


def insurer_type(row: dict, kind: str = "") -> str:
    """An insurer's type: "reinsurance" or "health" from its own words (industry, name, what the map says it does), else "life" or "general"
    from its filing's format (LI, GI), else from its words."""
    text = (" ".join(str(x) for x in (row.get("industry") or []) if x) + " " +
            " ".join(str(row.get(k) or "") for k in ("name", "map_industry", "map_what"))).lower()
    kind = str(kind or "").upper()
    if "reinsur" in text:
        return "reinsurance"
    if "health" in text and kind != "LI":
        return "health"
    if kind in ("LI", "GI"):
        return "life" if kind == "LI" else "general"
    return "life" if "life" in text else "general"


def tags(region: str, row: dict, model_family: str | None = None) -> set[str]:
    """What a company is, for which figures apply to it: its model's family (its layer's, else its structure's), its structures, and for a
    financial company its kind ("bank", "lender", an insurer's type); "us" for a US company outside finance."""
    prof = row.get("profile") or ("lender" if row.get("bank") else "other")
    out = set(structures(row))
    if prof == "insurer":
        out |= {"underwriting", insurer_type(row, row.get("sector_kind") or "")}
    elif prof in ("bank", "lender"):
        out |= {"lending", prof}
    else:
        fam = model_family or next((STRUCTURE_FAMILY[s] for s in out if s in STRUCTURE_FAMILY), "")
        if fam:
            out.add(fam)
        if region == "US":
            out.add("us")
    return out


def applies(metric_id: str, region: str, tagset: set[str]) -> bool:
    m = BY_ID.get(metric_id)
    if m is None or region not in m.regions:
        return False
    return "*" in m.applies or bool(m.applies & tagset)


_MON = re.compile(r"([A-Z][a-z]{2}) (\d{4})")


def period_end(text) -> date | None:
    """The last "Mon YYYY" a period's words name ("6 months to Sep 2026, annualised", "FY Jan 2026"), as that month's first day."""
    found = _MON.findall(str(text or ""))
    if not found:
        return None
    try:
        return datetime.strptime(" ".join(found[-1]), "%b %Y").date()
    except ValueError:
        return None


def _months(a: date, b: date) -> int:
    return (b.year - a.year) * 12 + b.month - a.month


def states(metric_id: str, region: str, rows: list[dict], tagsets: list[set]) -> list[str]:
    """Each company's state for one figure in one table: not applicable where it doesn't apply to the company's model; else not comparable
    where its period is STALE_MONTHS behind the table's latest or its basis differs (a row's `nc` list); else value or unavailable."""
    m = BY_ID[metric_id]
    ends = [period_end(((r.get("src") or r.get("sector_src") or {}).get(metric_id) or {}).get("period")) for r in rows]
    latest = max((e for e, r in zip(ends, rows) if e and r.get(metric_id) is not None), default=None)
    out = []
    for r, t, e in zip(rows, tagsets, ends):
        if not applies(metric_id, region, t):
            out.append(NOT_APPLICABLE)
        elif metric_id in (r.get("nc") or ()):
            out.append(NOT_COMPARABLE)
        elif r.get(metric_id) is None:
            out.append(UNAVAILABLE)
        elif latest and e and _months(e, latest) > STALE_MONTHS.get(m.period, 15):
            out.append(NOT_COMPARABLE)
        else:
            out.append(VALUE)
    return out


def coverage(values: list, sts: list[str], stat) -> dict:
    """A figure's median over its "value" rows (`stat`: theme_data.stat) and the count of the companies it applies to: {"n", "of", "median", ...}."""
    of = sum(1 for s in sts if s != NOT_APPLICABLE)
    st = stat(v for v, s in zip(values, sts) if s == VALUE) or {}
    return {**st, "n": st.get("n", 0), "of": of}


def fits_main(metric_id: str, region: str, tagsets: list[set], main: str | None) -> bool:
    """Whether a figure applies to a group's main model: to at least half of the companies of that model (all of them when none is known)."""
    mine = [t for t in tagsets if main in t] if main else list(tagsets)
    return bool(mine) and sum(1 for t in mine if applies(metric_id, region, t)) * 2 >= len(mine)


def headline_ok(metric_id: str, cov: dict, main_fits: bool, extreme: int = 0) -> bool:
    """Whether a figure may headline (a summary tile, a finding): it applies to the group's main model (`main_fits`: fits_main), a median of at
    least MIN_BASE companies, and at least HEADLINE_COVER of the companies it applies to have it; an unusual growth figure that makes up a third
    of its values doesn't."""
    m = BY_ID.get(metric_id)
    if m is None or not m.headline or not cov or (cov.get("n") or 0) < MIN_BASE or not cov.get("of") or not main_fits:
        return False
    if extreme and extreme * 3 >= cov["n"]:
        return False
    return cov["n"] >= HEADLINE_COVER * cov["of"]


def main_family(tagsets: list[set]) -> str | None:
    """The main model of a group: the family most of its companies have (theme_check.MODELS' families and the financial kinds)."""
    from collections import Counter
    fams = ("making", "software", "royalties", "services", "platform", "resale", "capacity", "telecom_services", "construction", "lending", "underwriting",
            "financial_fees", "resources", "utility", "property", "care", "media", "transport", "consumer_services", "holding",
            "regulated_utility", "generation", "power_trading", "mining", "metal_processing")
    c = Counter(f for t in tagsets for f in t if f in fams)
    return c.most_common(1)[0][0] if c else None


def is_extreme(growth, base_from=None, median_from=None) -> bool:
    """A growth figure worth its base said beside it: above GROWTH_EXTREME either way, or from a base under SMALL_BASE of its group's median base."""
    if growth is None:
        return False
    if abs(growth) > GROWTH_EXTREME:
        return True
    return base_from is not None and median_from is not None and median_from > 0 and 0 < base_from < SMALL_BASE * median_from


def dominated(values) -> bool:
    """Whether unusual growth figures (above GROWTH_EXTREME either way) make up a third or more of a group's values: its median isn't headlined."""
    vals = [v for v in values if v is not None]
    return bool(vals) and sum(1 for v in vals if abs(v) > GROWTH_EXTREME) * 3 >= len(vals)


def year_bases(row: dict) -> tuple | None:
    """A company's revenue growth's base: the revenue of the year before and of the latest year, from its stored years."""
    ys = [y for y in row.get("years") or [] if y.get("sales") is not None]
    return (ys[-2]["sales"], ys[-1]["sales"]) if len(ys) >= 2 else None


_ORDER_RX = {"order_book": re.compile(r"order ?book|orders? (?:in hand|on hand)|outstanding orders|unexecuted orders|backlog", re.I),
             "order_inflow": re.compile(r"order (?:inflow|intake)|new orders|orders? (?:received|won|secured|booked)", re.I)}


def orders_from_business(business: dict | None) -> dict:
    """The order book and order inflow each company's own business update states (the headline figure the app read from it: biz_updates), in ₹
    crore with its period and filing date: {symbol: {metric id: {"v", "period", "source"}}}. Nothing inferred: a figure in another unit, or
    with no period, isn't taken; future revenue is never worked out from it."""
    out: dict = {}
    for grp in ((business or {}).get("layers") or []) + ((business or {}).get("subs") or []):
        for r in grp.get("rows") or []:
            name, unit = str(r.get("metric") or ""), str(r.get("unit") or "").lower()
            if r.get("value") is None or not r.get("period") or "crore" not in unit or r.get("held_latest"):
                continue
            for k, rx in _ORDER_RX.items():
                if rx.search(name) and k not in out.get(r["symbol"], {}):
                    out.setdefault(r["symbol"], {})[k] = {"v": float(r["value"]), "period": str(r["period"]),
                                                          "source": "Business update filed with the exchange" + (f" on {r['filed']}" if r.get("filed") else "")}
                    break
    return out


def note_row(metric_id: str, financials: bool = True, plain_limits: dict | None = None) -> list[str]:
    """The notes page's row for a figure: name, what it measures and how it is worked out, its period and source, its limitation."""
    m = BY_ID[metric_id]
    limit = (plain_limits or {}).get(metric_id, m.limit) if not financials else m.limit
    return [m.label, m.definition.rstrip("."), m.source, limit]
