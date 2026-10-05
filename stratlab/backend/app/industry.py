"""Which set of checklist rules fits a company. The generic rules (margins, debt, capex, cash conversion) were written
for companies that make and sell things; for a lender, an insurer or a holding company some of them measure nothing,
and for power, telecom, real estate or metals they hold the whole industry to a bar it isn't built for.

The industry comes from the company page's own classification, then the shape of its reported statements, then
StratLab's sector lists."""
import re

from . import sector_members

GROUPS = {
    "lender": ("Bank or lender", "Lenders earn interest and lend out their cash flow, so capex, free cash flow, operating margin and "
               "debt to equity don't describe them. Return on equity is used instead."),
    "insurer": ("Insurer", "Insurers hold premiums to pay future claims, so operating margin, debt and capex checks don't apply. "
                "Return on equity is used instead; claims and solvency ratios aren't in the reported tables."),
    "holding": ("Holding or investment company", "Most of its income is dividends and gains from the companies it holds, so sales, "
                "margin and capex checks say little. Growth checks can't fail, only ask for a closer look."),
    "realty": ("Real estate", "Developers spend cash for years before a project is sold and book revenue in lumps, so cash flow "
               "and margin checks can't fail, only ask for a closer look."),
    "utility": ("Power, telecom or infrastructure", "These businesses run on long-term debt by design, so debt to equity can't "
                "fail, only ask for a closer look."),
    "cyclical": ("Cyclical: metals, cement, chemicals", "Growth and margins swing with the commodity cycle, so 3-year growth and "
                 "margin checks can't fail, only ask for a closer look."),
    "general": ("General", "Standard rules for companies that make and sell things."),
    # US only, from the company's SEC filings (see intel.sec.company_kind)
    "reit": ("Real estate investment trust (REIT)", "REITs own property or property loans and pay out most of their income. "
             "Depreciation and gains on property sales swing their operating profit, so operating margin isn't judged, and "
             "growth, debt and cash flow checks can't fail, only ask for a closer look."),
    "bdc": ("Business development company", "Business development companies lend to and invest in private companies and "
            "pay out most of their income, so sales, margin, capex and debt checks don't describe them. Return on equity "
            "is used instead."),
}
KINDS = {"reit": "reit", "bdc": "bdc"}       # a US company's kind from its filings -> its group

WORDS = [  # first match wins, checked against the industry classification and then the company name
    ("insurer", r"insurance|insurer"),
    ("realty", r"real estate|realty|residential|commercial projects"),
    ("holding", r"holding compan|investment compan|\bholdings?\b|\binvestments?\b"),
    ("lender", r"\bbanks?\b|banking|non banking|nbfc|housing finance|microfinance|\blending|consumer finance|financial institution"),
    ("utility", r"\bpower\b|utilit|telecom|infrastructure|\broads?\b|\bports?\b|airport|gas transmission|gas distribution|"
                r"electric services|electric & other services|telephone communications|radiotelephone"),
    ("cyclical", r"metal|steel|alumin|copper|zinc|mining|\bcement|chemical|fertili[sz]er|\bsugar|\bpaper\b"),
]
LISTS = {"lender": ["NIFTY BANK", "NIFTY PSU BANK", "NIFTY PVT BANK"], "realty": ["NIFTY REALTY"],
         "cyclical": ["NIFTY METAL", "NIFTY CHEMICALS"]}
UTILITIES = {"NTPC", "POWERGRID", "TATAPOWER", "ADANIPOWER", "ADANIGREEN", "NHPC", "JSWENERGY", "TORNTPOWER", "BHARTIARTL",
             "IDEA", "INDUSTOWER", "ADANIPORTS", "GMRAIRPORT", "IRB", "GAIL", "IGL", "MGL", "GUJGASLTD"}


def classify(p: dict, nums: dict | None = None, symbol: str | None = None) -> dict:
    path = [x for x in (p.get("industry_path") or []) if x][:4]
    group = KINDS.get(p.get("kind") or "") or ("lender" if (nums or {}).get("bank") else None)
    # the most specific part first: a US division like "Finance, Insurance & Real Estate" would otherwise decide
    for hay in ((path[-1] if path else "").lower(), " / ".join(path).lower(), (p.get("name") or "").lower()):
        if group:
            break
        group = next((g for g, rx in WORDS if hay and re.search(rx, hay)), None)
    if not group and symbol:
        group = next((g for g, idx in LISTS.items() if any(symbol in sector_members.IN.get(i, []) for i in idx)), None)
        group = group or ("utility" if symbol in UTILITIES else None)
    group = group or "general"
    label, note = GROUPS[group]
    return {"group": group, "label": label, "path": path, "note": note}


# ---------- the operating measures each industry is judged on ----------
# Not in the reported financial tables: read from the company's own investor presentation. First match wins.
MEASURES = [
    ("hospital", "Hospitals", r"hospital|healthcare facilit|health care facilit",
     ["ARPOB (average revenue per occupied bed)", "Bed occupancy %", "Operational beds", "Average length of stay", "New beds planned"]),
    ("lender", "Banks and lenders", r"\bbanks?\b|banking|non banking|nbfc|housing finance|microfinance|lending|consumer finance",
     ["Net interest margin (NIM)", "Gross NPA %", "Net NPA %", "CASA ratio", "Capital adequacy ratio", "Loan growth", "Credit cost"]),
    ("insurer", "Insurers", r"insurance|insurer",
     ["Value of new business (VNB) margin", "Gross written premium growth", "Solvency ratio", "Combined ratio or claims ratio", "13th-month persistency"]),
    ("hotel", "Hotels", r"hotel|resort",
     ["RevPAR (revenue per available room)", "ARR (average room rate)", "Occupancy %", "Rooms in operation", "Rooms in pipeline"]),
    ("airline", "Airlines", r"airline|aviation|air transportation, scheduled",
     ["Passenger load factor", "RASK (revenue per seat km)", "CASK (cost per seat km)", "Fleet size", "Market share"]),
    ("telecom", "Telecom", r"telecom|telephone communications|radiotelephone",
     ["ARPU (average revenue per user)", "Subscribers", "Data usage per user", "Towers or sites"]),
    ("cement", "Cement", r"\bcement",
     ["Installed capacity (MTPA)", "Capacity utilisation %", "Sales volume (tonnes)", "EBITDA per tonne", "Capacity being added"]),
    ("metal", "Metals and mining", r"metal|steel|alumin|copper|zinc|mining",
     ["Production volume", "Sales volume", "EBITDA per tonne", "Capacity being added", "Net debt"]),
    ("realty", "Real estate", r"real estate|realty|residential|commercial projects",
     ["Pre-sales (bookings value)", "Collections", "Area sold (sq ft)", "New launches", "Net debt"]),
    ("power", "Power", r"\bpower\b|electric utilit|renewable|electric services|electric & other services",
     ["Installed capacity (MW)", "Plant load factor (PLF)", "Renewable share of capacity", "Capacity under construction"]),
    ("restaurant", "Restaurants", r"restaurant|quick service|\bqsr\b|food service|eating places",
     ["Same-store sales growth", "Store count", "Average daily sales per store", "Delivery share"]),
    ("retail", "Retail", r"retail|department store|hypermarket|apparel retail",
     ["Revenue per sq ft", "Same-store sales growth", "Store count", "Retail area (sq ft)"]),
    ("it", "IT services", r"\bit\b|software|computer (?:programming|services|integrated|processing)|information technology|it enabled",
     ["Constant-currency revenue growth", "Deal wins (TCV)", "Attrition %", "Headcount", "Top-client concentration"]),
    ("pharma", "Pharmaceuticals", r"pharma|drug|formulation",
     ["US sales and growth", "India sales growth", "R&D spend % of sales", "Product approvals or filings"]),
    ("auto", "Automobiles", r"automobile|passenger car|two wheeler|commercial vehicle|tractor|\bauto\b",
     ["Sales volume (units)", "Market share", "EV share of volume", "Realisation per vehicle"]),
    ("fmcg", "Consumer staples", r"fmcg|consumer staple|personal care|household|packaged food|food products|beverage",
     ["Volume growth", "Rural vs urban growth", "Distribution reach (outlets)", "Gross margin"]),
    ("chemical", "Chemicals", r"chemical|fertili[sz]er|agro",
     ["Capacity utilisation %", "Specialty share of revenue", "Volume growth", "Capacity being added"]),
]
MEASURE_LISTS = {"lender": ["NIFTY BANK", "NIFTY PSU BANK", "NIFTY PVT BANK"], "it": ["NIFTY IT"], "pharma": ["NIFTY PHARMA"],
                 "auto": ["NIFTY AUTO"], "fmcg": ["NIFTY FMCG"], "metal": ["NIFTY METAL"], "realty": ["NIFTY REALTY"],
                 "chemical": ["NIFTY CHEMICALS"]}
GENERAL_MEASURES = ["The operating measures the company itself highlights (volumes, capacity, utilisation, customers, pricing)"]


def measures(p: dict, symbol: str | None = None) -> dict:
    """{"key", "label", "measures"}: what to look for in this company's presentation."""
    parts = [x for x in (p.get("industry_path") or []) if x]
    for hay in ((parts[-1] if parts else "").lower(), " / ".join(parts).lower(), (p.get("name") or "").lower()):
        for key, label, rx, ms in MEASURES:
            if hay and re.search(rx, hay):
                return {"key": key, "label": label, "measures": ms}
    if symbol:
        for key, idx in MEASURE_LISTS.items():
            if any(symbol in sector_members.IN.get(i, []) for i in idx):
                label, ms = next((lb, m) for k, lb, _, m in MEASURES if k == key)
                return {"key": key, "label": label, "measures": ms}
    return {"key": "general", "label": None, "measures": GENERAL_MEASURES}


# ---------- how each kind of business is usually valued ----------
EV_EBITDA = {"hospital", "hotel", "telecom", "cement", "metal", "power", "airline"}
BOOK = {"lender", "insurer", "holding", "realty", "reit", "bdc"}


def _last(table: dict | None, prefix: str):
    for label, vals in ((table or {}).get("rows") or {}).items():
        if label.lower().startswith(prefix.lower()):
            v = [x for x in vals if x is not None]
            return v[-1] if v else None
    return None


def _none_because(short: str, snap: dict, p: dict, own: str | None) -> str:
    """Why a multiple is blank, when it is a fact about the company: `own` is the multiple's own reason (a loss,
    negative net worth or EBITDA); otherwise no market value (shares not trading) or no reported results."""
    why = own or ("the company page shows no market value for its shares" if not snap.get("market_cap_cr")
                  else "there are no reported results to divide by" if not (p.get("pl") or {}).get("rows") else None)
    return f" There's no {short} here: {why}." if why else ""


def valuation(p: dict, snap: dict, group: str, measure_key: str) -> dict:
    """The multiple this kind of business is usually valued on, with P/E alongside. Facts, not a verdict."""
    pe = snap.get("pe")
    ttm = _last(p.get("pl"), "Net Profit")
    eps = _last(p.get("pl"), "EPS")
    # a loss for the shareholders: the group's profit can be positive while their share of it (EPS) isn't
    loss = (ttm is not None and ttm <= 0) or (eps is not None and eps <= 0)
    mcap = snap.get("market_cap_cr")
    if mcap and p.get("currency") not in (None, "USD", "INR"):
        # a US-listed company reporting in another currency: its market value (dollars) in that currency, at today's
        # rate, to set against its reported profit, book, debt and EBITDA
        rate = (p.get("fx") or {}).get("rate")
        mcap = mcap / rate if rate else None
    computed = pe is None and not loss and bool(mcap) and ttm is not None
    if computed:                               # no P/E on the page: market value ÷ the last 12 months' profit
        pe = mcap / ttm
    if group in BOOK or measure_key in BOOK:
        v = snap.get("pb")
        bal = p.get("balance")
        worth = ((_last(bal, "Reserves") or 0) + (_last(bal, "Equity Capital") or 0) if _last(bal, "Reserves") is not None
                 else _last(bal, "Equity"))
        if v is None and mcap and worth and worth > 0:   # no book value on the page: from the balance sheet
            v = mcap / worth
        own = ("the company's net worth is negative" if worth is not None and worth < 0
               else "the company has no balance sheet on its page" if worth is None and snap.get("market_cap_cr") else None)
        return {"name": "Price to book", "short": "P/B", "value": round(v, 2) if v is not None else None, "pe": pe,
                "why": ("REITs and business development companies are usually valued on their book (net asset value)."
                        if group in KINDS else "Lenders, insurers, holding companies and developers are usually valued on their book (net worth).")
                       + (_none_because("P/B", snap, p, own) if v is None else "")}
    if measure_key in EV_EBITDA or group == "utility":
        ebitda = _last(p.get("pl"), "Operating Profit")          # the latest column is the trailing twelve months
        debt = _last(p.get("balance"), "Borrowings") or 0
        cash = _last(p.get("balance"), "Cash")             # US filings report it; for India, the Other Assets breakdown
        v = (mcap + debt - (cash or 0)) / ebitda if mcap and ebitda and ebitda > 0 else None
        own = "EBITDA was negative over the last 12 months" if ebitda is not None and ebitda <= 0 else None
        return {"name": "EV / EBITDA", "short": "EV/EBITDA", "value": round(v, 1) if v is not None else None, "pe": pe,
                "why": "Asset-heavy businesses (hospitals, hotels, telecom, cement, metals, power, airlines) are usually valued on "
                       "enterprise value to EBITDA, because depreciation and debt differ so much between them. Here EV is market "
                       + ("value plus borrowings less cash" if cash is not None else "value plus borrowings (cash isn't subtracted)")
                       + " and EBITDA is the last twelve months' operating profit."
                       + (_none_because("EV/EBITDA", snap, p, own) if v is None else "")}
    return {"name": "Price to earnings", "short": "P/E", "value": round(pe, 1) if pe is not None else None, "pe": pe,
            "why": "Most businesses are compared on price to earnings."
                   + (" Here it is market value divided by the last 12 months' net profit." if computed else "")
                   + (_none_because("P/E", snap, p, "the company made a loss over the last 12 months" if loss else None)
                      if pe is None else "")}
