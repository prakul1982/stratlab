"""Synthetic themes of structures the earlier fixtures don't have (R27, shared by every lane): chemicals, real estate, telecom (India and the US),
US consumer retail, utilities and power, metals and mining, plus a US semiconductor theme of chip makers and design licensors, Indian insurers
of every type, Indian banks whose filings give NII / assets, and an Indian defence theme with a business update that states an order book.
Each builder returns (region, map, facts, extra) where extra holds the keyword arguments D.Sources and deck_of take (metrics=..., extra=...).
Facts only: no figure or name is tuned to a real company."""
from app.intel import sector_metrics as S
from tests.test_theme1 import facts

CR = 10_000_000


def co(sym, name, what="", industry=""):
    return {"ticker": sym, "name": name, "what": what, "industry": industry, "base": True, "basis": "industry", "verified": True}


def placements(n):
    return {"checked": True, "pending": 0, "placed": n, "total": n, "base": n, "named": 0, "added": 0, "confirmed": 0}


def model(family, n, line="They earn mainly from making and selling products of their own."):
    return {"id": "", "family": family, "line": line, "known": n, "of": n}


def _theme(sector, region, layers, fact_of, summary=""):
    """A map of AI layers [(layer, prefix, industry, n, model family or None)] and each company's facts from fact_of(i, sym, name, industry)."""
    m = {"sector": sector, "summary": summary or f"{sector} companies.", "value_chain": [], "sub_themes": [], "tailwinds": [], "risks": [],
         "generated_at": 1.0}
    f, k = {}, 0
    for layer, pre, ind, n, fam in layers:
        cos = [co(f"{pre}{i}", f"{layer.split()[0]} {pre} {i} {'Inc' if region == 'US' else 'Ltd'}", f"works in {layer.lower()}", ind) for i in range(n)]
        lay = {"layer": layer, "description": f"{layer}.", "companies": cos}
        if fam:
            lay["model"] = model(fam, n)
        m["value_chain"].append(lay)
        for i, c in enumerate(cos):
            f[c["ticker"]] = fact_of(k + i, c["ticker"], c["name"], ind)
        k += n
    m["placements"] = placements(k)
    return m, f


def _in(i, sym, name, ind, margins=(14, 15, 16, 17), grow=1.0):
    sales = [1000 + i * 40, 1100 + i * 40, 1210 + i * 40, round((1330 + i * 40) * grow)]
    return facts(sym, name, sales, [m + i * 1.5 for m in margins], [s // 10 for s in sales], cap=60000 - i * 2500, pe=24.0 + i, industry=("Industrials", ind))


def _us(i, sym, name, ind, margins=(20, 21, 22, 23)):
    return {**facts(sym, name, [900 + i * 30, 1000 + i * 30, 1100 + i * 30, 1250 + i * 30], [m + i % 4 for m in margins],
                    [90 + i, 100 + i, 115 + i, 130 + i * 2], cap=90000 - i * 4000, pe=30.0 + i, industry=(ind,)),
            "region": "US", "unit": "$ million"}


# ---------- India: the new structures, generic figures only ----------
def chemicals_in():
    m, f = _theme("Specialty chemicals", "IN", [("Specialty chemical makers", "SC", "Specialty Chemicals", 4, "making"),
                                                ("Agrochemical makers", "AG", "Pesticides & Agrochemicals", 3, "making"),
                                                ("Contract chemical manufacturing", "CM", "Specialty Chemicals", 3, "making")], _in)
    return "IN", m, f, {}


def real_estate_in():
    """Real estate, one developer with revenue growth from a small base (unusual growth: its base is said)."""
    def fact(i, sym, name, ind):
        if sym == "RD0":           # a developer whose sales grew from a small base (a jump over 60% is a series break: no growth shown)
            return facts(sym, name, [40, 45, 50, 75], [20, 22, 24, 30], [4, 5, 6, 9], cap=30000, pe=35.0, industry=("Realty", ind))
        return _in(i, sym, name, ind, margins=(24, 25, 26, 27))
    m, f = _theme("Real estate", "IN", [("Residential developers", "RD", "Residential, Commercial Projects", 5, "property"),
                                        ("Commercial landlords", "CL", "Real Estate Investment Trusts (REITs)", 3, "property")], fact)
    return "IN", m, f, {}


def telecom_in():
    m, f = _theme("Telecom", "IN", [("Mobile and broadband operators", "TO", "Telecom - Cellular & Fixed line services", 3, "capacity"),
                                    ("Towers and fibre", "TT", "Telecom - Infrastructure", 3, "capacity"),
                                    ("Telecom equipment makers", "TE", "Telecom - Equipment & Accessories", 3, "making")],
                  lambda i, s, n, ind: _in(i, s, n, ind, margins=(38, 40, 41, 42)))
    return "IN", m, f, {}


def utilities_in():
    m, f = _theme("Power utilities", "IN", [("Power generation", "PG", "Power Generation", 4, "utility"),
                                            ("Power transmission and distribution", "PT", "Power - Transmission", 3, "utility"),
                                            ("Gas distribution", "GD", "Gas Distribution", 3, "utility")],
                  lambda i, s, n, ind: _in(i, s, n, ind, margins=(28, 29, 30, 31)))
    return "IN", m, f, {}


def metals_in():
    m, f = _theme("Metals and mining", "IN", [("Steel makers", "ST", "Iron & Steel", 4, "making"),
                                              ("Non-ferrous metals", "NF", "Aluminium", 3, "making"),
                                              ("Miners", "MN", "Industrial Minerals", 3, "resources")],
                  lambda i, s, n, ind: _in(i, s, n, ind, margins=(16, 18, 20, 19)))
    return "IN", m, f, {}


# ---------- the US: telecom and retail with SEC figures ----------
def flow(val, end, start, form="10-K"):
    return {"start": start, "end": end, "val": val, "form": form, "filed": end, "fy": int(end[:4]), "fp": "FY"}


def inst(val, end, form="10-K"):
    return {"end": end, "val": val, "form": form, "filed": end}


def companyfacts(rev=1000e6, capex=80e6, inv=None, cost=None, rd=None, rpo=None, sbc=50e6, cfo=250e6, deferred=None):
    """A US company's company facts for two fiscal years to Dec 2025: revenue, cash from operations, capital spending, and each optional figure."""
    a, b, a0, b0 = "2025-12-31", "2025-01-01", "2024-12-31", "2024-01-01"
    g = {"RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"USD": [flow(rev * 0.9, a0, b0), flow(rev, a, b)]}},
         "ShareBasedCompensation": {"units": {"USD": [flow(sbc, a, b)]}},
         "NetCashProvidedByUsedInOperatingActivities": {"units": {"USD": [flow(cfo, a, b)]}},
         "PaymentsToAcquirePropertyPlantAndEquipment": {"units": {"USD": [flow(capex, a, b)]}}}
    if inv is not None:
        g["InventoryNet"] = {"units": {"USD": [inst(inv * 0.9, a0), inst(inv, a)]}}
    if cost is not None:
        g["CostOfRevenue"] = {"units": {"USD": [flow(cost * 0.9, a0, b0), flow(cost, a, b)]}}
    if rd is not None:
        g["ResearchAndDevelopmentExpense"] = {"units": {"USD": [flow(rd * 0.9, a0, b0), flow(rd, a, b)]}}
    if rpo is not None:
        g["RevenueRemainingPerformanceObligation"] = {"units": {"USD": [inst(rpo[0], a0), inst(rpo[1], a)]}}
    if deferred is not None:
        g["ContractWithCustomerLiability"] = {"units": {"USD": [inst(deferred[0], a0), inst(deferred[1], a)]}}
    return {"cik": 1, "entityName": "X", "facts": {"us-gaap": g}}


def us_piece(cf) -> dict:
    got = S.us_figures(cf)
    end = got.pop("_end", None)
    return {"family": "us", "end": end, "metrics": got}


def reader_of(pieces):
    return lambda sym, fam: pieces.get(sym)


def telecom_us():
    m, f = _theme("US telecom", "US", [("Wireless and cable operators", "UT", "Radiotelephone Communications", 3, "capacity"),
                                       ("Network equipment makers", "UE", "Telephone & Telegraph Apparatus", 3, "making")], _us)
    pieces = {s: us_piece(companyfacts(capex=(180e6 if s.startswith("UT") else 40e6) + i * 5e6, inv=None if s.startswith("UT") else 90e6,
                                       cost=600e6, rd=None if s.startswith("UT") else 120e6)) for i, s in enumerate(sorted(f))}
    return "US", m, f, {"metrics": reader_of(pieces)}


def retail_us():
    m, f = _theme("US consumer retail", "US", [("Store chains", "RS", "Retail-Variety Stores", 4, "resale"),
                                               ("Online retailers", "RO", "Retail-Catalog & Mail-Order Houses", 3, "resale")],
                  lambda i, s, n, ind: _us(i, s, n, ind, margins=(12, 12, 13, 13)))
    pieces = {s: us_piece(companyfacts(capex=30e6 + i * 2e6, inv=120e6 + i * 10e6, cost=700e6, sbc=10e6)) for i, s in enumerate(sorted(f))}
    return "US", m, f, {"metrics": reader_of(pieces)}


def semis_us(ip_rpo=True):
    """US semiconductors: chip makers (some file RPO, as the live R26 deck showed) and design licensors (royalties: RPO applies)."""
    m, f = _theme("US semiconductors", "US", [("Chip makers", "CH", "Semiconductors & Related Devices", 6, "making"),
                                              ("Equipment makers", "EQ", "Special Industry Machinery, Nec", 3, "making"),
                                              ("Chip design licensors", "IP", "Services-Prepackaged Software", 3, "royalties")], _us)
    pieces = {}
    for i, s in enumerate(sorted(f)):
        maker = not s.startswith("IP")
        cf = companyfacts(capex=(150e6 if maker else 10e6) + i * 4e6, inv=200e6 + i * 5e6 if maker else None, cost=500e6 if maker else 100e6,
                          rd=150e6 + i * 5e6, rpo=((500e6, 470e6) if maker and i % 2 == 0 else (800e6, 900e6 + i * 10e6) if not maker and ip_rpo else None),
                          deferred=(100e6, 300e6 + i) if maker and i == 0 else (200e6, 230e6) if not maker else None)
        pieces[s] = us_piece(cf)
    return "US", m, f, {"metrics": reader_of(pieces)}


# ---------- India: insurers of every type ----------
def xbrl(end, q_start, ytd_start, q=None, ytd=None, at=None, meta=None):
    from tests.test_r23_metrics import xbrl as x
    return x(end, q_start, ytd_start, q=q, ytd=ytd, at=at, meta=meta, kind="ins")


def insurers_in():
    groups = [("Life insurers", "LF", "Life Insurance", 3, "LI"), ("General insurers", "GN", "General Insurance", 3, "GI"),
              ("Health insurers", "HL", "General Insurance", 3, "GI"), ("Reinsurers", "RE", "General Insurance", 1, "GI")]
    m = {"sector": "Insurance", "summary": "Insurers.", "value_chain": [], "sub_themes": [], "tailwinds": [], "risks": [], "generated_at": 1.0}
    f, pieces, k = {}, {}, 0
    for layer, pre, ind, n, kind in groups:
        word = {"HL": "Health", "RE": "Reinsurance", "LF": "Life", "GN": "General"}[pre]
        cos = [co(f"{pre}{i}", f"{word} Cover {i} Ltd", f"sells {layer.lower()} policies", ind) for i in range(n)]
        m["value_chain"].append({"layer": layer, "description": f"{layer}.", "companies": cos, "model": model("underwriting", n, "They earn mainly from premiums.")})
        for i, c in enumerate(cos):
            f[c["ticker"]] = {**facts(c["ticker"], c["name"], [3000, 3400, 3900, 4500 + (k + i) * 100], [None] * 4, [300, 340, 390, 450 + i * 20],
                                      cap=90000 - (k + i) * 5000, pe=50.0, roce=None, de=None, industry=("Financial Services", "Insurance", ind)),
                              "roe": 12.0 + i, "pb": 5.0 - i * 0.2}
            if kind == "LI":
                doc = xbrl("2026-09-30", "2026-07-01", "2026-04-01", q={"SolvencyRatio": 1.9 + i * 0.1, "GrossPremiumIncome": (1000 + i * 50) * CR},
                           ytd={"PersistencyRatio13ThMonth": 0.85 + i * 0.01})
            else:
                base = {"GN": 1.02, "HL": 0.98, "RE": 1.10}[pre]
                doc = xbrl("2026-09-30", "2026-07-01", "2026-04-01", q={"SolvencyRatio": 2.0 + i * 0.1, "GrossPremiumsWritten": (1000 + i * 50) * CR},
                           ytd={"IncurredClaimRatio": base - 0.3 + i * 0.01, "CombinedRatio": base + i * 0.01})
            ago = xbrl("2025-09-30", "2025-07-01", "2025-04-01", q={"GrossPremiumIncome": 900 * CR, "GrossPremiumsWritten": 900 * CR})
            pieces[c["ticker"]] = {"family": "insurer", "kind": kind, "end": "2026-09-30",
                                   "metrics": S.insurer_figures(S.parse_results(doc), S.parse_results(ago), kind)}
        k += n
    m["placements"] = placements(k)
    return "IN", m, f, {"metrics": reader_of(pieces)}


# ---------- India: banks whose filings give NII / assets ----------
def bank_doc(end, q_start, ytd_start, ie, ix, adv, dep, assets, profit=200, prov=40):
    from tests.test_r23_metrics import xbrl as x
    return x(end, q_start, ytd_start, meta={"Symbol": "B", "NatureOfReportStandaloneConsolidated": "Standalone"},
             q={"InterestEarned": ie * CR, "InterestExpended": ix * CR, "PercentageOfGrossNpa": 0.012, "PercentageOfNpa": 0.004, "CET1Ratio": 0.16},
             ytd={"InterestEarned": ie * 2 * CR, "InterestExpended": ix * 2 * CR, "ProfitLossForThePeriod": profit * CR,
                  "ProvisionsOtherThanTaxAndContingencies": prov * CR},
             at={"Advances": adv * CR, "Deposits": dep * CR, "Assets": assets * CR})


def banks_in(unfiled=(4,)):
    """Eight banks in two layers; each has its results filings read (NII / assets from them) but those in `unfiled` (the largest regional
    bank), which have only their pages' annual figure."""
    cos = [co(f"BK{i}", f"Bank {i} Ltd", "takes deposits and lends", "Private Sector Bank") for i in range(8)]
    line = "They earn mainly from interest on loans they make."
    m = {"sector": "Banks", "summary": "Banks.", "sub_themes": [], "tailwinds": [], "risks": [], "generated_at": 1.0, "placements": placements(8),
         "value_chain": [{"layer": "Large deposit-led banks", "description": "Large banks.", "companies": cos[:4], "model": model("lending", 4, line)},
                         {"layer": "Regional banks", "description": "Regional banks.", "companies": cos[4:], "model": model("lending", 4, line)}]}
    f, pieces = {}, {}
    for i, c in enumerate(cos):
        f[c["ticker"]] = {**facts(c["ticker"], c["name"], [9000, 10000, 11000, 12000 + i * 500], [None] * 4, [1500, 1700, 1900, 2000 + i * 40],
                                  cap=200000 - i * 15000, pe=12.0, roce=None, de=None, industry=("Financial Services", "Banks")),
                          "bank": True, "roe": 15.0 + i, "pb": 2.0, "lender": {"gnpa": 1.5, "nnpa": 0.4, "nii_assets": 2.9 + i * 0.1, "roa": 1.5, "year": "Mar 2026"}}
        if i not in unfiled:
            cur = S.parse_results(bank_doc("2026-09-30", "2026-07-01", "2026-04-01", 3000 + i * 60, 1800, 110000 + i * 1000, 115000, 160000 + i * 2000,
                                           profit=1000))
            ago = S.parse_results(bank_doc("2025-09-30", "2025-07-01", "2025-04-01", 2700, 1620, 100000, 100000, 140000, profit=900))
            pieces[c["ticker"]] = {"family": "bank", "kind": "BANKING", "end": "2026-09-30", "metrics": S.bank_figures(cur, ago, filed="2026-10-17")}
        else:
            pieces[c["ticker"]] = {"family": "bank", "end": None, "metrics": {}, "none": "no bank results filing in XBRL on the exchange"}
    return "IN", m, f, {"metrics": reader_of(pieces)}


# ---------- India: defence with an order book stated in a business update ----------
def defence_in(stated=True):
    m, f = _theme("Defence", "IN", [("Defence platforms", "DF", "Aerospace & Defense", 4, "making"),
                                    ("Defence electronics", "DE", "Aerospace & Defense", 3, "making")],
                  lambda i, s, n, ind: _in(i, s, n, ind, margins=(20, 21, 22, 23)))
    rows = [{"symbol": "DF0", "name": "Defence DF 0 Ltd", "metric": "Order book" if stated else "Total sales", "unit": "₹ crore", "span": "quarter",
             "period": "Sep 2026", "value": 182000.0, "filed": "2026-10-10", "prev": 176000.0, "change_prev": 3.4, "year_ago": 160000.0,
             "change_year": 13.8},
            {"symbol": "DE0", "name": "Defence DE 0 Ltd", "metric": "Order inflow" if stated else "Units delivered", "unit": "₹ crore" if stated else "units",
             "span": "quarter", "period": "Sep 2026", "value": 5400.0, "filed": "2026-10-08", "prev": 5100.0, "change_prev": 5.9, "year_ago": 4900.0,
             "change_year": 10.2},
            {"symbol": "DE1", "name": "Defence DE 1 Ltd", "metric": "Order book", "unit": "US$ million", "span": "quarter", "period": "Sep 2026",
             "value": 900.0, "filed": "2026-10-08", "prev": 880.0, "change_prev": 2.3, "year_ago": 800.0, "change_year": 12.5}]
    business = {"allowed": True, "layers": [{"layer": "Defence platforms", "rows": rows[:1]}, {"layer": "Defence electronics", "rows": rows[1:]}],
                "subs": [], "companies": 3, "of": 7, "held": []}
    return "IN", m, f, {"extra": {"business": business}}


STRUCTURES = {"chemicals (IN)": chemicals_in, "real estate (IN)": real_estate_in, "telecom (IN)": telecom_in, "telecom (US)": telecom_us,
              "consumer retail (US)": retail_us, "utilities and power (IN)": utilities_in, "metals and mining (IN)": metals_in}
SECTOR_THEMES = {"semiconductors (US)": semis_us, "insurers by type (IN)": insurers_in, "banks, NII / assets (IN)": banks_in, "defence (IN)": defence_in}


def deck_of(region, m, f, extra=None, metrics=None):
    """The dive, the deck's view and its slides for a synthetic theme (the business updates and other page parts in `extra`)."""
    from app import deck
    from app.intel import theme_data as D
    from app.intel import theme_routes as T
    from tests.test_r18_deck import NOW
    from tests.test_theme1 import TODAY
    dive = D.build(region, m["sector"], m, D.Sources(TODAY, facts=f.get, **({"metrics": metrics} if metrics else {})))
    v = T.deck_view(region, m, dive, extra)
    return v, deck.theme_plan(v, now=NOW)[0]


def build(name):
    """A named synthetic theme's (view, slides)."""
    region, m, f, kw = {**STRUCTURES, **SECTOR_THEMES}[name]()
    return deck_of(region, m, f, **kw)
