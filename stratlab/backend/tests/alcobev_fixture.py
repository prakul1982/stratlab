"""deck89 (owner, 25 Nov: "I made an alcoholic beverage deck, check that out, it looks absolutely trash"): a realistic alcoholic-beverages
theme for the deck tests, built from the live deck's appendix and the theme's public page (30 companies in 7 layers, each with its market
value, revenue, growth, margins, ROCE, P/E and P/B as the live deck printed them). It goes through the real dive (theme_data.build) and the
real deck view (theme_routes.deck_view), so every rule of the engine runs on it. Nothing here is a real filing: it is a test theme."""
import copy
from datetime import date

from app.intel import theme_data as D
from app.intel import theme_routes as T

TODAY = date(2026, 11, 23)
INDUSTRY = ("Breweries & Distilleries",)

# symbol, name, layer, market value (₹ cr), revenue (₹ cr), growth %, EBITDA margin %, net margin %, ROCE %, P/E, P/B, what it does
ROWS = [
    ("UNITDSPR", "United Spirits Limited", "Spirits brand owning and bottling (larger)", 107000, 12467, 3.3, 18.3, 14.7, 26.4, 58.2, 11.3,
     "makes and sells whisky, rum, brandy and vodka brands across India"),
    ("RADICO", "Radico Khaitan Limited", "Spirits brand owning and bottling (larger)", 62124, 6037, 24.7, 16.9, 10.0, 24.2, 78.0, 16.8,
     "makes and sells Indian-made foreign liquor brands such as vodka and whisky"),
    ("UBL", "United Breweries Limited", "Beer brewing and sale", 32612, 9240, 3.6, 8.7, 4.5, 10.7, 68.4, 7.1, "brews and sells beer brands across India"),
    ("ABDL", "Allied Blenders and Distillers Limited", "Spirits brand owning and bottling (larger)", 22457, 3923, 11.4, 13.8, 5.6, 18.4, 98.4, 12.9,
     "makes and sells whisky and other spirits brands"),
    ("TI", "Tilaknagar Industries Ltd", "Spirits brand owning and bottling (larger)", 13651, 2346, 9.0, 17.9, 0.9, 11.4, None, 4.2,
     "makes and sells brandy and other spirits brands"),
    ("BORORENEW", "Borosil Renewables Limited", "Other alcoholic beverage companies", 5385, 1556, 5.4, 28.3, 8.2, 25.3, 12.1, 3.2,
     "makes glass for bottles and other uses"),
    ("IGLSPIRITS", "IGL Spirits Ltd", "Other alcoholic beverage companies", 5341, 8416, 6.0, 5.8, 2.9, None, 21.6, None,
     "distils alcohol and sells spirits in bulk and in bottles"),
    ("PICCADIL", "Piccadily Agro Industries Limited", "Grain distilling and extra neutral alcohol", 5274, 1000, 25.5, 23.3, 13.8, 18.0, 38.6, 5.8,
     "distils grain into extra neutral alcohol and malt spirit"),
    ("AGI", "AGI Greenpac Limited", "Glass bottle and packaging manufacturing", 4198, 2665, 5.4, 22.3, 13.2, 19.5, 11.9, 1.8,
     "makes glass bottles for beer, spirits and other drinks"),
    ("GLOBUSSPR", "Globus Spirits Limited", "Grain distilling and extra neutral alcohol", 2367, 2710, 6.8, 9.4, 3.4, 11.2, 24.2, 1.7,
     "distils grain into extra neutral alcohol and bottles spirits"),
    ("INDIAGLYCO", "India Glycols Ltd", "Spirits brand owning and bottling (larger)", 1980, 4211, 4.0, 15.4, 7.0, 12.4, 9.4, 1.6,
     "makes potable alcohol and spirits as well as chemicals"),
    ("GMBREW", "G M Breweries Ltd", "Spirits brand owning and bottling (larger)", 1951, 748, 17.4, 24.2, 21.0, 18.0, 11.3, 1.7,
     "makes and sells country liquor brands in Maharashtra"),
    ("SDBL", "Som Distilleries & Breweries Ltd", "Beer brewing and sale", 1551, 1229, -14.8, 7.0, 0.8, 5.7, None, 2.1, "brews beer and makes spirits"),
    ("SULA", "Sula Vineyards Limited", "Wine making and sales", 1173, 556, -4.0, 18.7, 4.7, 7.5, 43.5, 2.0, "makes and sells wine from its own vineyards"),
    ("ASGARD", "Asgard Alcobev Ltd", "Beer brewing and sale", 1087, 101, 74.1, 6.9, 1.0, 7.4, 290.6, 9.3, "brews and sells beer"),
    ("ASALCBR", "Associated Alcohols & Breweries Ltd.", "Grain distilling and extra neutral alcohol", 1060, 1020, 8.0, 14.0, 8.6, 18.0, 13.6, 1.4,
     "distils grain into extra neutral alcohol and bottles liquor"),
    ("BCLIND", "BCL Industries Ltd", "Grain distilling and extra neutral alcohol", 826, 2792, -0.8, 8.0, 4.5, 12.8, 7.0, 0.9,
     "distils grain into extra neutral alcohol and ethanol"),
    ("IFBAGRO", "IFB Agro Industries Ltd", "Grain distilling and extra neutral alcohol", 809, 1404, 32.6, 7.2, 4.0, 12.7, 13.4, 1.3,
     "distils grain into extra neutral alcohol and bottles liquor"),
    ("JAGAJITIND", "Jagatjit Industries Ltd", "Grain distilling and extra neutral alcohol", 554, 254, -48.4, -18.5, 3.9, 10.5, 15.5, 12.5,
     "distils grain and sells liquor brands"),
    ("FRATELLI", "Fratelli Vineyards Ltd", "Wine making and sales", 488, 153, -44.6, -4.9, -16.3, -4.9, None, 3.7, "makes and sells wine"),
    ("AGRIBIO", "Agribio Spirits Ltd", "Spirits brand owning and bottling (smaller)", 337, 46, 5.0, 0.6, 6.3, 4.2, 84.7, 4.7, "bottles and sells spirits"),
    ("MONIKA", "Monika Alcobev Ltd", "Other alcoholic beverage companies", 293, 300, 27.7, 15.3, 10.7, 14.7, 9.1, 1.2, "imports and sells wine and spirits brands"),
    ("COMFINTE", "Comfort Intech Ltd", "Spirits brand owning and bottling (smaller)", 178, 145, -5.8, 7.0, -2.1, 2.7, None, 1.1, "bottles and sells liquor"),
    ("SHRIGANG", "Shri Gang Industries & Allied Products Ltd", "Spirits brand owning and bottling (smaller)", 90, 366, 13.0, 9.8, 5.2, 30.0, 4.5, 2.0,
     "makes and bottles country liquor"),
    ("KATIPATANG", "Kati patang Lifestyle Ltd", "Other alcoholic beverage companies", 75, 9, 2.0, 12.0, 4.0, -29.6, None, 3.1, "sells beverages"),
    ("RKDL", "Ravikumar Distilleries Ltd", "Spirits brand owning and bottling (smaller)", 42, 20, -46.2, -5.3, 0.7, 1.6, None, 1.0, "distils and bottles liquor"),
    ("SILVOAK", "Silver Oak (India) Ltd", "Spirits brand owning and bottling (smaller)", 24, 1, -10.0, 2.0, 1.0, -0.3, None, 5.7, "bottles spirits"),
    ("TAHMARENT", "Tahmar Enterprises Ltd", "Grain distilling and extra neutral alcohol", 18, 2, -40.6, 5.0, 2.0, -2.3, None, 1.1, "distils alcohol"),
    ("WINSOMBR", "Winsome Breweries Ltd", "Beer brewing and sale", 15, 1, -59.9, 5.0, 2.0, -1.3, None, 1.5, "brews beer"),
    ("CUPIDALBV", "Cupid Breweries & Distilleries Ltd", "Other alcoholic beverage companies", 201, 1, 1.0, 3.0, 1.0, 1.0, None, 0.3, "brews beer and distils"),
]

LAYERS = [
    ("Glass bottle and packaging manufacturing", "Glass makers supply the bottles for whisky, beer and wine to bottlers."),
    ("Grain distilling and extra neutral alcohol", "This layer ferments and distils grain or molasses into extra neutral alcohol, often alongside ethanol for fuel blending."),
    ("Spirits brand owning and bottling (larger)", "This layer blends, bottles and markets whisky, brandy, rum and vodka to state-licensed retailers."),
    ("Spirits brand owning and bottling (smaller)", "Smaller blenders and bottlers of spirits, many selling regional and country-liquor brands."),
    ("Beer brewing and sale", "This layer brews beer and sells it through state-controlled distribution and on-premise outlets."),
    ("Wine making and sales", "Wineries grow or buy grapes and make, bottle and sell wine."),
    ("Other alcoholic beverage companies", "Companies of the theme's industry that fit none of the layers above."),
]

# the industry-supported five of the live page: on their official industry only
INDUSTRY_ONLY = {"RADICO", "COMFINTE", "SILVOAK", "WINSOMBR", "IGLSPIRITS"}


def _facts(sym, name, cap, rev, g, eb, net, roce, pe, pb):
    prev = rev / (1 + g / 100)
    sales = [round(prev * 0.85, 1), round(prev * 0.92, 1), round(prev, 1), float(rev)]
    margins = [eb - 1.0, eb - 0.6, eb - 0.4, eb]
    profits = [round(s * net / 100, 2) for s in sales]
    years = [{"year": y, "sales": s, "profit": p, "opm": m, "debt": round(s * 0.2, 1), "cfo": round(p * 1.1, 2)}
             for y, s, p, m in zip(["Mar 2023", "Mar 2024", "Mar 2025", "Mar 2026"], sales, profits, margins)]
    return {"v": 9, "region": "IN", "symbol": sym, "name": name, "unit": "₹ crore", "industry": list(INDUSTRY), "price": 100.0, "price_at": "2026-11-23",
            "high52": 130.0, "low52": 80.0, "market_cap": cap, "pe": pe, "pb": pb, "roe": 12.0, "roce": roce, "net_margin": net, "opm": eb,
            "debt_equity": 0.4, "bank": False, "stage": 2, "st_up": True, "filings": [], "red_flags": 0,
            "growth": {"sales_cagr_3y": 8.0, "profit_cagr_3y": 10.0, "sales_cagr_5y": 7.0, "profit_cagr_5y": 6.0}, "years": years}


FACTS = {r[0]: _facts(r[0], r[1], *r[3:11]) for r in ROWS}

MAP = {
    "sector": "Alcoholic beverages",
    "summary": ("India's alcohol industry is shifting from mass-market spirits toward premium and luxury labels, as rising incomes and a young urban "
                "drinking population lead consumers to trade up in whisky, gin, vodka and craft beer. Alcohol is a state subject, so each state sets "
                "its own excise duty, pricing, licensing and distribution rules, which makes margins depend heavily on state policy."),
    "value_chain": [{"layer": name, "description": desc,
                     "companies": [{"name": r[1], "ticker": r[0], "what": r[11], "base": True, "basis": "industry", "verified": r[0] not in INDUSTRY_ONLY,
                                    "cap": float(r[3])} for r in ROWS if r[2] == name]} for name, desc in LAYERS],
    "sub_themes": [{"name": "Spirits brand owners", "detail": "These companies blend, brand and market whisky, rum, brandy, vodka and gin.",
                    "companies": [{"name": r[1], "ticker": r[0], "what": r[11]} for r in ROWS if r[2].startswith("Spirits")]},
                   {"name": "Beer brewing", "detail": "Brewers make and sell lager and strong beer.",
                    "companies": [{"name": r[1], "ticker": r[0], "what": r[11]} for r in ROWS if r[2] == "Beer brewing and sale"]}],
    "tailwinds": [{"text": "Grain-based distillers can sell ethanol for fuel blending in addition to alcohol, adding a second revenue stream.", "status": "current",
                   "source": {"headline": "India achieves 20% ethanol blending; grain-based feedstocks account for 73% of supplies", "at": "2026-11-20",
                              "outlet": "ChiniMandi", "url": "https://example.com/news/ethanol"}},
                  {"text": "Trade agreements with spirit-producing countries may change import duties on scotch and other imported liquor, affecting premium competition.",
                   "status": "current", "source": {"headline": "UK-India free trade agreement hits single malt prices", "at": "2026-11-20",
                                                   "outlet": "BigGo Finance", "url": "https://example.com/news/fta"}}],
    "risks": [{"text": "State governments can raise excise duty, change pricing rules or move to state-run retail, squeezing margins with little notice.",
               "status": "general", "source": None},
              {"text": "Grain, glass, energy and packaging costs can rise faster than approved price increases, lowering margins.", "status": "general", "source": None}],
    "placements": {"checked": True, "pending": 0, "placed": 30, "total": 30, "base": 30, "named": 0, "added": 0, "confirmed": 0},
}


def _src():
    return D.Sources(TODAY, facts=FACTS.get, index_rows=lambda: [{"symbol": "X", "pe": 22.0, "opm": 10.8, "net_margin": 5.9, "roce": 9.2, "sales_cagr_3y": 10.1}])


def alco_view() -> dict:
    """The alcoholic-beverages theme as the deck reads it, with the parts the page reads on its own (prices, the latest quarter)."""
    dive = D.build("IN", "Alcoholic beverages", copy.deepcopy(MAP), _src())
    v = T.deck_view("IN", copy.deepcopy(MAP), dive)
    weeks = ["2026-09-07", "2026-09-14", "2026-09-21", "2026-09-28", "2026-10-05", "2026-10-12", "2026-10-19", "2026-10-26", "2026-11-02",
             "2026-11-09", "2026-11-16", "2026-11-23"]
    theme = [100, 99.1, 97.8, 98.6, 96.2, 95.0, 93.9, 95.4, 94.1, 92.8, 93.5, 92.2]
    bench = [100, 100.6, 101.2, 100.4, 101.9, 102.8, 102.1, 103.5, 104.0, 103.1, 104.4, 105.2]
    v["prices"] = {"companies": [], "benchmark": "Nifty 500", "returns_to": "2026-11-23",
                   "median": {"1M": {"median": 8.2, "n": 18}, "3M": {"median": -7.7, "n": 18}, "1Y": {"median": -22.5, "n": 17}, "3Y": None},
                   "returns": {"1M": {"theme": 4.6, "bench": 10.8}, "3M": {"theme": -9.5, "bench": 0.9}, "1Y": {"theme": -17.2, "bench": -0.2},
                               "3Y": {"theme": None, "bench": 34.6}},
                   "line": {"weeks": weeks, "theme": theme, "bench": bench, "rs": [round(t / b * 100, 1) for t, b in zip(theme, bench)]}}
    sec = v["sections"]
    # (changed on purpose, e89: the latest quarter is of the companies in the theme's figures, as theme_data.quarter_section reads them: the
    # floor's companies and a business demerged since its year, the dive's "too_small", are in it no more than in any other figure)
    apart = {x["symbol"] for x in dive.get("too_small") or []}
    qc = [(r[0], r[1], round(r[5] / 3 + 2, 1), round(r[7] - 5, 1)) for r in ROWS[:28] if r[0] not in apart]
    sales = sorted(x[2] for x in qc)
    sec["quarter"] = {"quarter": "Sep 2026", "companies": [{"symbol": s, "name": n, "of": "Sep 2026", "sales": a, "profit": p} for s, n, a, p in qc],
                      "sales_up": sum(1 for x in qc if x[2] > 0), "sales_down": sum(1 for x in qc if x[2] <= 0),
                      "profit_up": sum(1 for x in qc if x[3] > 0), "profit_down": sum(1 for x in qc if x[3] <= 0),
                      "sales": {"n": len(qc), "median": sales[len(sales) // 2], "min": sales[0], "max": sales[-1]}, "profit": None}
    return v
