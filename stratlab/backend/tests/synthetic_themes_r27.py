"""Release 27: synthetic themes of new structures, shared by the R27 lanes (quality, metrics, classification). Each is a function that returns
(region, map, facts) for tests.test_r18_deck.deck_of, and `market` rows where a theme carries listed peers of its own sector. Facts only:
no figure or name is tuned to a real company.

  chemicals_in      India, three official industries; whole-point margins; a net margin above the EBITDA margin; sector peers in the market
  real_estate_in    India, the AI's layers (developers, leasing, contractors); lumpy revenue (a broken series) and a part year
  telecom_in        India, a few large operators, a two-company layer (under the base) and a loss-maker
  telecom_us        the US, the AI's layers (wireless, cable, towers), dollar figures, quarters on different months
  retail_us         the US, big-box, apparel and e-commerce (loss-makers), a layer whose models are mostly unknown (sparse)
  utilities_in      India, generation, transmission and a small distribution layer; high debt
  metals_mining_in  India, steel, aluminium and mining with falling margins and one diversified group
"""
from app.intel import theme_data as D
from tests.test_theme1 import facts

TODAY_Q = {"of": "Sep 2026 vs Sep 2025", "basis": "quarter"}


def co(sym, name, what="", industry="", base=True, verified=True):
    return {"ticker": sym, "name": name, "what": what, "industry": industry, "base": base, "basis": "industry" if base else "added", "verified": verified}


def placements(n, industries=None):
    p = {"checked": True, "pending": 0, "placed": n, "total": n, "base": n, "named": 0, "added": 0, "confirmed": 0}
    return {**p, "industries": industries} if industries else p


def official(layers: dict, sector: str, summary: str) -> dict:
    """A map whose layers are the exchange's own industries: {industry: [companies]}."""
    return {"sector": sector, "summary": summary, "sub_themes": [], "tailwinds": [], "risks": [],
            "value_chain": [{"layer": ind, "official": True, "basis": "industry", "description": "", "companies": cos} for ind, cos in layers.items()],
            "placements": placements(sum(len(c) for c in layers.values()), list(layers))}


def ai_map(layers: dict, sector: str, summary: str, models: dict | None = None) -> dict:
    """A map of the AI's own layers: {layer: [companies]}; `models`: {layer: model dict} (theme_base.by_model's)."""
    return {"sector": sector, "summary": summary, "sub_themes": [], "tailwinds": [], "risks": [], "generated_at": 1.0,
            "value_chain": [{"layer": nm, "description": f"Companies in {nm.lower()}.", "companies": cos, **({"model": models[nm]} if models and nm in models else {})}
                            for nm, cos in layers.items()],
            "placements": placements(sum(len(c) for c in layers.values()))}


def us(f: dict) -> dict:
    return {**f, "region": "US", "unit": "$ million"}


def sector_of(region: str, f: dict) -> str:
    """The sector a company's row is filed under (screens.row), so a market of its peers can share it."""
    return D.company_row(region, f["symbol"], f)["sector"]


def peers_for(region: str, f: dict, n: int = 12, pe: float = 18.0) -> list[dict]:
    """`n` listed companies of a company's own sector and similar market value, outside the theme (the market's rows)."""
    sec, cap = sector_of(region, f), f["market_cap"]
    return [{"symbol": f"PEER{f['symbol']}{i}", "name": f"Peer {i}", "sector": sec, "market_cap": cap * (0.8 + i * 0.03), "pe": pe + i * 0.5,
             "sales_cagr_3y": 7.0 + i * 0.2, "roce": 12.0 + i * 0.3, "opm": 15.0, "net_margin": 8.0} for i in range(n)]


# ---------- the themes ----------
def chemicals_in():
    spec = {"Specialty Chemicals": ("SC", "makes specialty chemicals for agrochemical and pharma customers", 5),
            "Commodity Chemicals": ("CC", "manufactures caustic soda, chlorine and soda ash", 4),
            "Fertilizers": ("FZ", "manufactures urea and complex fertilisers", 3)}
    layers, f = {}, {}
    for ind, (p_, what, n) in spec.items():
        cos = [co(f"{p_}{i}", f"{ind.split()[0]} Chem {i} Ltd", what, ind) for i in range(n)]
        layers[ind] = cos
        for i, c in enumerate(cos):
            m = {"SC": [22, 21, 19, 18 + i], "CC": [16, 14, 12, 11 + i % 2], "FZ": [9, 8, 8, 7]}[p_]
            f[c["ticker"]] = facts(c["ticker"], c["name"], [1500, 1650, 1700, 1800 + i * 60], m, [150, 160, 150, 160 + i * 8],
                                   cap=60000 - i * 6000 - len(f) * 1000, pe=32.0 - i, roce=15.0 + i, industry=("Chemicals", ind))
    f["FZ2"] = facts("FZ2", "Fertilizers Chem 2 Ltd", [2000, 2100, 2200, 2300], [7, 7, 7, 7], [60, 70, 80, 300], cap=20000, pe=11.0,
                     industry=("Chemicals", "Fertilizers"))      # a net margin above its EBITDA margin (13% on 7%)
    market = peers_for("IN", f["SC0"]) + peers_for("IN", f["CC0"])
    return "IN", official(layers, "Chemicals", "Speciality and commodity chemicals and fertiliser makers."), f, market


def real_estate_in():
    spec = {"Residential developers": ("RD", "develops and sells residential apartments", 4), "Commercial leasing": ("CL", "leases office and retail space", 3),
            "Construction contractors": ("CN", "builds buildings and infrastructure under contract", 3)}
    layers, f = {}, {}
    for layer, (p_, what, n) in spec.items():
        cos = [co(f"{p_}{i}", f"{layer.split()[0]} Realty {i} Ltd", what, "Realty") for i in range(n)]
        layers[layer] = cos
        for i, c in enumerate(cos):
            sales = {"RD": [3000, 2400, 4100, 3600 + i * 200], "CL": [900, 980, 1050, 1120 + i * 30], "CN": [5000, 5600, 6000, 6500 + i * 100]}[p_]
            m = {"RD": [28, 24, 30, 27 + i], "CL": [72, 74, 75, 74 + i], "CN": [11, 11, 10, 10]}[p_]
            prof = [round(s * mm / 300) for s, mm in zip(sales, m)]
            f[c["ticker"]] = facts(c["ticker"], c["name"], sales, m, prof, cap=70000 - len(f) * 4000, pe=38.0 + i, roce=9.0 + i, de=0.9,
                                   industry=("Realty", "Realty"))
    f["RD3"]["years"][-1]["year"] = "Mar 2026 9m"          # a part year: its growth and margins are on a different basis
    f["RD1"]["years"][-1]["sales"] = 9000                   # lumpy revenue: a break in its series (a merger's size)
    return "IN", ai_map(layers, "Real estate", "Home builders, landlords of offices and malls, and building contractors."), f, []


def telecom_in():
    spec = {"Telecom - Services": ("TS", "provides mobile and broadband services", 3), "Telecom - Infrastructure": ("TI", "owns and leases telecom towers", 2),
            "Telecom - Equipment & Accessories": ("TE", "manufactures optical fibre cable and network equipment", 3)}
    layers, f = {}, {}
    for ind, (p_, what, n) in spec.items():
        cos = [co(f"{p_}{i}", f"{ind.split(' - ')[1].split()[0]} Tel {i} Ltd", what, ind) for i in range(n)]
        layers[ind] = cos
        for i, c in enumerate(cos):
            m = {"TS": [38, 40, 45, 48 + i], "TI": [52, 53, 55, 56], "TE": [14, 12, 9, 8 + i]}[p_]
            prof = {"TS": [-900, -400, 600, 1500 - i * 1200], "TI": [800, 850, 900, 950], "TE": [80, 60, 40, 30 + i * 5]}[p_]
            f[c["ticker"]] = facts(c["ticker"], c["name"], [20000, 22000, 25000, 28000 - i * 3000] if p_ == "TS" else [3000, 3200, 3400, 3600 + i * 50],
                                   m, prof, cap=400000 - len(f) * 30000, pe=None if prof[-1] <= 0 else 40.0 + i, roce=8.0 + i, de=2.5,
                                   industry=("Telecommunication", ind), latest_yoy={**TODAY_Q, "sales": 9.0 + i, "profit": 12.0 + i})
    return "IN", official(layers, "Telecom", "Mobile operators, tower companies and network equipment makers."), f, []


def telecom_us():
    spec = {"Wireless carriers": ("WC", "provides wireless phone and data service", 3), "Cable and broadband": ("CB", "provides cable television and home broadband", 3),
            "Tower and fibre landlords": ("TW", "leases space on communication towers and fibre", 3)}
    layers, f = {}, {}
    for layer, (p_, what, n) in spec.items():
        cos = [co(f"{p_}{i}", f"{layer.split()[0]} Comm {i} Inc", what, "Radiotelephone Communications") for i in range(n)]
        layers[layer] = cos
        for i, c in enumerate(cos):
            m = {"WC": [34, 35, 36, 37 + i], "CB": [38, 37, 36, 35 + i], "TW": [62, 63, 64, 65 + i]}[p_]
            month = ("Sep 2026 vs Sep 2025", "Jun 2026 vs Jun 2025")[i % 2]
            f[c["ticker"]] = us(facts(c["ticker"], c["name"], [60000, 62000, 63000, 64000 + i * 900] if p_ != "TW" else [9000, 9600, 10200, 10800 + i * 150],
                                      m, [7000, 7300, 7600, 7900 + i * 100] if p_ != "TW" else [1800, 1900, 2100, 2300], cap=200000 - len(f) * 12000,
                                      pe=18.0 + i, roce=7.0 + i, de=1.6, industry=("Radiotelephone Communications",),
                                      latest_yoy={"of": month, "basis": "quarter", "sales": 3.0 + i, "profit": 5.0 - i}))
    return "US", ai_map(layers, "US telecom", "Wireless carriers, cable operators and the landlords of towers and fibre."), f, []


def retail_us():
    spec = {"Big-box retail": ("BB", "operates warehouse clubs and supercentres", 4), "Apparel retail": ("AP", "sells clothing and footwear in stores and online", 3),
            "E-commerce marketplaces": ("EC", "operates online marketplaces for third-party sellers", 4)}
    sparse = {"id": "", "family": "", "line": "Under half of these companies have a known way of earning.", "known": 1, "of": 4, "sparse": True}
    layers, f = {}, {}
    for layer, (p_, what, n) in spec.items():
        cos = [co(f"{p_}{i}", f"{layer.split()[0]} Shop {i} Inc", what, "Retail-Variety Stores") for i in range(n)]
        layers[layer] = cos
        for i, c in enumerate(cos):
            loss = p_ == "EC" and i >= 2
            m = {"BB": [6, 6, 7, 7], "AP": [12, 11, 13, 14 + i], "EC": [-8.0, -6.0, -4.0, -3.0 - i] if loss else [9.0, 10.0, 11.0, 12.0 + i]}[p_]
            f[c["ticker"]] = us(facts(c["ticker"], c["name"], [50000, 53000, 56000, 60000 + i * 500] if p_ == "BB" else [8000, 8600, 9500, 10500 + i * 300],
                                      m, [-600, -500, -400, -300] if loss else [1500, 1600, 1700, 1900 + i * 50], cap=150000 - len(f) * 9000,
                                      pe=None if loss else 25.0 + i, roce=11.0 + i, de=0.7, industry=("Retail-Variety Stores",),
                                      latest_yoy={"of": "Oct 2026 vs Oct 2025", "basis": "quarter", "sales": 6.0 + i, "profit": 4.0 + i}))
    return "US", ai_map(layers, "US retail", "Store chains, apparel sellers and online marketplaces.", {"E-commerce marketplaces": sparse}), f, []


def utilities_in():
    spec = {"Power Generation": ("PG", "generates and sells electricity from thermal and renewable plants", 4),
            "Power - Transmission": ("PT", "builds and operates high-voltage transmission lines", 3), "Power Distribution": ("PD", "distributes electricity to consumers", 2)}
    layers, f = {}, {}
    for ind, (p_, what, n) in spec.items():
        cos = [co(f"{p_}{i}", f"{ind.split()[-1]} Power {i} Ltd", what, ind) for i in range(n)]
        layers[ind] = cos
        for i, c in enumerate(cos):
            m = {"PG": [26, 27, 28, 29 + i], "PT": [86, 87, 88, 88], "PD": [12, 12, 13, 13]}[p_]
            f[c["ticker"]] = facts(c["ticker"], c["name"], [40000, 43000, 46000, 49000 + i * 1000], m, [4000, 4300, 4600, 4900 + i * 100],
                                   cap=300000 - len(f) * 20000, pe=17.0 + i, roce=10.0 + i * 0.5, de=1.8, industry=("Power", ind))
    return "IN", official(layers, "Power utilities", "Power generators, transmission companies and distributors."), f, []


def metals_mining_in():
    spec = {"Iron & Steel": ("ST", "manufactures flat and long steel products", 4), "Aluminium": ("AL", "smelts and rolls aluminium", 3),
            "Industrial Minerals": ("MN", "mines iron ore and coal", 3)}
    layers, f = {}, {}
    for ind, (p_, what, n) in spec.items():
        cos = [co(f"{p_}{i}", f"{ind.split()[0]} Metal {i} Ltd", what, ind) for i in range(n)]
        layers[ind] = cos
        for i, c in enumerate(cos):
            m = {"ST": [24, 18, 14, 12 + i], "AL": [30, 22, 19, 17 + i], "MN": [45, 41, 38, 36 + i]}[p_]
            f[c["ticker"]] = facts(c["ticker"], c["name"], [60000, 64000, 62000, 61000 + i * 900], m, [9000, 7000, 5000, 4000 + i * 200],
                                   cap=250000 - len(f) * 15000, pe=14.0 + i, roce=12.0 + i, de=0.8, industry=("Metals & Mining", ind))
    layers["Aluminium"].append(co("VEDL", "Diversified Metals Group Ltd", "mines and smelts zinc, aluminium, oil and gas", "Aluminium"))
    f["VEDL"] = facts("VEDL", "Diversified Metals Group Ltd", [140000, 145000, 150000, 152000], [26, 25, 27, 28], [12000, 11000, 13000, 14000],
                      cap=180000, pe=12.0, industry=("Metals & Mining", "Aluminium"))
    return "IN", official(layers, "Metals and mining", "Steel, aluminium and mining companies."), f, []


THEMES = (("chemicals (IN)", chemicals_in), ("real estate (IN)", real_estate_in), ("telecom (IN)", telecom_in), ("telecom (US)", telecom_us),
          ("consumer retail (US)", retail_us), ("utilities and power (IN)", utilities_in), ("metals and mining (IN)", metals_mining_in))


def decks():
    """Every R27 synthetic theme as (name, view, slides), built as the route builds a deck."""
    from tests.test_r18_deck import deck_of
    for name, fn in THEMES:
        region, m, f, market = fn()
        v, slides = deck_of(region, m, f, index_rows=(lambda mk=market: mk))
        yield name, v, slides
