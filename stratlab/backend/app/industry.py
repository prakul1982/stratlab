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
}

WORDS = [  # first match wins, checked against the industry classification and then the company name
    ("insurer", r"insurance|insurer"),
    ("holding", r"holding compan|investment compan|\bholdings?\b|\binvestments?\b"),
    ("lender", r"\bbanks?\b|banking|non banking|nbfc|housing finance|microfinance|\blending|consumer finance|financial institution"),
    ("realty", r"real estate|realty|residential|commercial projects"),
    ("utility", r"\bpower\b|utilit|telecom|infrastructure|\broads?\b|\bports?\b|airport|gas transmission|gas distribution"),
    ("cyclical", r"metal|steel|alumin|copper|zinc|mining|\bcement|chemical|fertili[sz]er|\bsugar|\bpaper\b"),
]
LISTS = {"lender": ["NIFTY BANK", "NIFTY PSU BANK", "NIFTY PVT BANK"], "realty": ["NIFTY REALTY"],
         "cyclical": ["NIFTY METAL", "NIFTY CHEMICALS"]}
UTILITIES = {"NTPC", "POWERGRID", "TATAPOWER", "ADANIPOWER", "ADANIGREEN", "NHPC", "JSWENERGY", "TORNTPOWER", "BHARTIARTL",
             "IDEA", "INDUSTOWER", "ADANIPORTS", "GMRAIRPORT", "IRB", "GAIL", "IGL", "MGL", "GUJGASLTD"}


def classify(p: dict, nums: dict | None = None, symbol: str | None = None) -> dict:
    path = [x for x in (p.get("industry_path") or []) if x][:4]
    group = "lender" if (nums or {}).get("bank") else None
    for hay in (" / ".join(path).lower(), (p.get("name") or "").lower()):
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
    ("airline", "Airlines", r"airline|aviation",
     ["Passenger load factor", "RASK (revenue per seat km)", "CASK (cost per seat km)", "Fleet size", "Market share"]),
    ("telecom", "Telecom", r"telecom",
     ["ARPU (average revenue per user)", "Subscribers", "Data usage per user", "Towers or sites"]),
    ("cement", "Cement", r"\bcement",
     ["Installed capacity (MTPA)", "Capacity utilisation %", "Sales volume (tonnes)", "EBITDA per tonne", "Capacity being added"]),
    ("metal", "Metals and mining", r"metal|steel|alumin|copper|zinc|mining",
     ["Production volume", "Sales volume", "EBITDA per tonne", "Capacity being added", "Net debt"]),
    ("realty", "Real estate", r"real estate|realty|residential|commercial projects",
     ["Pre-sales (bookings value)", "Collections", "Area sold (sq ft)", "New launches", "Net debt"]),
    ("power", "Power", r"\bpower\b|electric utilit|renewable",
     ["Installed capacity (MW)", "Plant load factor (PLF)", "Renewable share of capacity", "Capacity under construction"]),
    ("retail", "Retail", r"retail|department store|hypermarket|apparel retail",
     ["Revenue per sq ft", "Same-store sales growth", "Store count", "Retail area (sq ft)"]),
    ("restaurant", "Restaurants", r"restaurant|quick service|\bqsr\b|food service",
     ["Same-store sales growth", "Store count", "Average daily sales per store", "Delivery share"]),
    ("it", "IT services", r"\bit\b|software|computers|information technology|it enabled",
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
    path = " / ".join(x for x in (p.get("industry_path") or []) if x).lower()
    for hay in (path, (p.get("name") or "").lower()):
        for key, label, rx, ms in MEASURES:
            if hay and re.search(rx, hay):
                return {"key": key, "label": label, "measures": ms}
    if symbol:
        for key, idx in MEASURE_LISTS.items():
            if any(symbol in sector_members.IN.get(i, []) for i in idx):
                label, ms = next((lb, m) for k, lb, _, m in MEASURES if k == key)
                return {"key": key, "label": label, "measures": ms}
    return {"key": "general", "label": None, "measures": GENERAL_MEASURES}
