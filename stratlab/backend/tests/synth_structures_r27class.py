"""Synthetic themes of new structures (Release 27, lane r27-class), shared so the other lanes can reuse them: chemicals (IN), real estate (IN),
telecom (IN and US), consumer retail (US), utilities and power (IN), metals and mining (IN), and the structures of the benchmark families (IT
services, pharma, semiconductors, auto, insurance, banks). Each map's own layers mix ways of earning, as an AI map does; every company carries
the revenue model, secondary tags and confidence its words would give. Synthetic only: no real company's name or figure.

structures() yields (name, theme) where theme = {"region", "map", "facts", "models", "tags", "confidence", "apart"}: `apart` lists pairs of
models that must never share a layer once the map is split by how its companies earn (theme_base.by_model)."""
from tests.test_theme1 import facts


def _co(sym, name, what, industry, cap):
    return {"ticker": sym, "name": name, "what": what, "industry": industry, "base": True, "basis": "industry", "verified": True, "cap": cap}


def build(region: str, sector: str, layers: list, apart: list) -> dict:
    """layers: [(layer name, description, [(symbol, name, what, industry, model, tags, confidence)])]; a layer named "Other" is the theme's
    "Other" group (official, basis "rest")."""
    m = {"sector": sector, "summary": f"Synthetic {sector.lower()} theme.", "sub_themes": [], "tailwinds": [], "risks": [], "generated_at": 1.0,
         "value_chain": []}
    f, models, tags, conf = {}, {}, {}, {}
    k = 0
    for name, desc, rows in layers:
        cos = []
        for sym, nm, what, ind, model, tg, cf in rows:
            cap = 90000 - k * 2500
            cos.append(_co(sym, nm, what, ind, cap))
            margin = 12.0 + (k % 9) * 2.5
            fx = facts(sym, nm, [900 + k * 10, 1000 + k * 10, 1100 + k * 12, 1250 + k * 15], [margin - 1, margin - 0.5, margin, margin + 0.5],
                       [80 + k, 90 + k, 100 + k, 115 + k * 2], cap=cap, pe=18.0 + k % 11, roce=11.0 + k % 13, industry=(sector, ind))
            if region == "US":
                fx = {**fx, "region": "US", "unit": "$ million"}
            f[sym] = fx
            if model:
                models[sym] = model
            if tg:
                tags[sym] = list(tg)
            if cf:
                conf[sym] = cf
            k += 1
        layer = {"layer": name, "description": desc, "companies": cos}
        if name == "Other":
            layer = {"layer": f"Other {sector.lower()} companies", "description": "", "official": True, "basis": "rest",
                     "companies": [{**c, "placed": "ai"} for c in cos]}
        m["value_chain"].append(layer)
    n = sum(len(v["companies"]) for v in m["value_chain"])
    m["placements"] = {"checked": True, "pending": 0, "placed": n, "total": n, "base": n, "named": 0, "added": 0, "confirmed": n, "industries": []}
    return {"region": region, "map": m, "facts": f, "models": models, "tags": tags, "confidence": conf, "apart": apart}


def _rows(prefix, n, name, what, ind, model, tags=(), conf="high"):
    return [(f"{prefix}{i}", f"{name} {i} Ltd", what, ind, model, tags, conf) for i in range(n)]


def chemicals_in():
    return build("IN", "Chemicals", [
        ("Speciality and performance chemicals", "Makers of speciality molecules.",
         _rows("SPC", 4, "Molecula", "makes and sells its own speciality chemicals under its brands", "Specialty Chemicals", "manufacturing")
         + _rows("CRM", 3, "Synthon", "custom synthesis and contract manufacturing (CRAMS) for global innovators", "Specialty Chemicals", "contract_manufacturing")),
        ("Commodity chemicals and trading", "Bulk chemicals.",
         _rows("CMD", 3, "Bulkchem", "manufactures caustic soda and chlor-alkali products in its plants", "Commodity Chemicals", "manufacturing")
         + _rows("CTR", 3, "Chemtrade", "trading and distribution of chemicals bought from makers", "Trading - Chemicals", "distribution")),
    ], [("manufacturing", "contract_manufacturing"), ("manufacturing", "distribution"), ("contract_manufacturing", "distribution")])


def real_estate_in():
    return build("IN", "Real estate", [
        ("Residential and commercial real estate", "Builds and owns property.",
         _rows("DEV", 4, "Homestead", "develops and sells residential projects and apartments", "Residential, Commercial Projects", "property_development")
         + _rows("LND", 3, "Leasewell", "owns office parks and malls and earns rent on leases", "Real Estate Investment Trusts (REITs)", "property")),
        ("Property services", "Services around property.",
         _rows("PRT", 3, "Listly", "runs an online marketplace for property listings and earns listing fees", "Real Estate related services", "platform")),
    ], [("property_development", "property"), ("property", "platform")])


def telecom_in():
    return build("IN", "Telecom", [
        ("Telecom operators and infrastructure", "Networks and towers.",
         _rows("TOP", 3, "Callnet", "mobile and broadband services to subscribers over its own network", "Telecom - Cellular & Fixed line services", "capacity")
         + _rows("TWR", 3, "Towerco", "leases telecom towers and fibre network capacity to operators", "Telecom - Infrastructure", "capacity")
         + _rows("TEQ", 3, "Wavegear", "manufactures optical fibre cable and telecom equipment", "Telecom - Equipment & Accessories", "manufacturing")),
        ("Telecom software", "Software for operators.",
         _rows("TSW", 3, "Billsoft", "sells licences and subscriptions for its own billing software", "Software Products", "software")),
    ], [("capacity", "manufacturing"), ("capacity", "software")])


def telecom_us():
    return build("US", "Telecom US", [
        ("Carriers and networks", "Wireless and cable carriers.",
         _rows("UCR", 3, "Skyline", "wireless services to subscribers over its own spectrum and network", "Radiotelephone Communications", "capacity")
         + _rows("UTW", 3, "Mastrent", "owns towers and earns rent on leases to carriers", "Real Estate Investment Trusts", "property")),
        ("Network equipment", "Gear for carriers.",
         _rows("UEQ", 3, "Routerly", "designs and manufactures network routers and switches", "Telephone & Telegraph Apparatus", "manufacturing")
         + _rows("USV", 3, "Netops", "runs and maintains carriers' networks under managed services contracts", "Communications Services, Nec", "managed_services")),
    ], [("capacity", "property"), ("manufacturing", "managed_services")])


def retail_us():
    return build("US", "Consumer retail", [
        ("Store and online retailers", "Retail to consumers.",
         _rows("URT", 4, "Shopwise", "sells goods to consumers in its own stores and online; a store credit card", "Retail-Variety Stores", "retail", ("lending",))[:2]
         + _rows("URS", 2, "Martway", "sells groceries to consumers in its own supermarkets", "Retail-Grocery Stores", "retail")
         + _rows("UMP", 3, "Bazaarly", "runs an online marketplace and earns commissions and advertising from sellers", "Services-Business Services, Nec", "platform")),
        ("Wholesale and distribution", "Wholesale to businesses.",
         _rows("UWD", 3, "Pallet", "wholesale distribution of consumer goods to retailers", "Wholesale-Groceries & Related Products", "distribution")),
    ], [("retail", "platform"), ("platform", "distribution")])


def utilities_in():
    return build("IN", "Power", [
        ("Generation and distribution", "Generate and supply power.",
         _rows("GEN", 5, "Voltgen", "generates electricity and sells power under long-term tariffs", "Power Generation", "utility")
         + _rows("EPC", 3, "Gridbuild", "EPC contracts to build transmission lines and substations, with an order book", "Civil Construction", "construction")),
        ("Electrical equipment", "Equipment for the grid.",
         _rows("HEQ", 3, "Transfo", "manufactures transformers and switchgear in its plants", "Heavy Electrical Equipment", "manufacturing")
         + [("PTR0", "Powertrade 0 Ltd", "trading of power bought from generators", "Power Trading", "distribution", (), "high")]),
    ], [("utility", "construction"), ("utility", "manufacturing")])


def metals_in():
    return build("IN", "Metals and mining", [
        ("Miners and metal makers", "Dig and make metals.",
         _rows("MIN", 3, "Orecore", "mines iron ore and coal and sells it", "Industrial Minerals", "resources")
         + _rows("STL", 4, "Steelco", "manufactures steel in its integrated plants", "Iron & Steel", "manufacturing")
         + [("MTR0", "Metaltrade 0 Ltd", "trading of metals bought from smelters", "Trading - Metals", "distribution", (), "high")]),
    ], [("resources", "manufacturing")])


# ---------- the benchmark families' structures ----------
def it_in():
    return build("IN", "IT services", [
        ("Digital and IT services", "Services for enterprises.",
         _rows("PRJ", 4, "Codecraft", "delivers IT projects and consulting to clients", "Computers - Software & Consulting", "project_services")
         + _rows("MSV", 3, "Runwell", "runs clients' IT infrastructure under managed services contracts", "Computers - Software & Consulting", "managed_services")
         + _rows("BPO", 3, "Callwise", "business process outsourcing: customer service and back-office work for banks", "IT Enabled Services", "bpo")),
        ("Products, platforms and hardware", "Products and kit.",
         _rows("SAS", 3, "Cloudly", "sells subscriptions for its own SaaS software", "Software Products", "software")
         + _rows("PLT", 3, "Jobhub", "runs an online marketplace for jobs and earns listing fees", "Software Products", "platform")
         + _rows("HWR", 3, "Boxline", "resells and installs servers of global brands as a system integrator", "Computers - Software & Consulting", "hardware_resale")),
    ], [("project_services", "bpo"), ("managed_services", "bpo"), ("software", "platform"), ("software", "hardware_resale"),
        ("platform", "hardware_resale"), ("project_services", "software")])


def pharma_in():
    return build("IN", "Pharma", [
        ("Branded and generic formulations", "Medicines under own brands.",
         _rows("FRM", 2, "Curelab", "makes and sells its own branded formulations; also contract manufacturing for others", "Pharmaceuticals", "manufacturing",
               ("contract_manufacturing",))
         + _rows("GEN", 2, "Genrx", "makes and sells its own generic medicines", "Pharmaceuticals", "manufacturing")
         + _rows("CDM", 3, "Moleserve", "a CDMO: contract development and manufacturing for innovator companies", "Pharmaceuticals", "contract_manufacturing")),
        ("Ingredients", "Active ingredients.",
         _rows("API", 3, "Apichem", "makes active pharmaceutical ingredients (APIs) sold to formulators", "Pharmaceuticals", "components")),
    ], [("manufacturing", "contract_manufacturing"), ("manufacturing", "components"), ("contract_manufacturing", "components")])


def semis_us():
    return build("US", "Semiconductors", [
        ("Chip designers and makers", "Chips.",
         _rows("FBL", 3, "Gatesign", "fabless: designs chips that foundries make", "Semiconductors & Related Devices", "fabless")
         + _rows("IDM", 3, "Wafermade", "designs and manufactures its own chips in its fabs (an IDM)", "Semiconductors & Related Devices", "manufacturing")
         + _rows("FDY", 3, "Fabforhire", "a pure-play foundry and OSAT making chips to customers' designs", "Semiconductors & Related Devices", "contract_manufacturing")),
        ("Design licensing", "Licences.",
         [("IPL0", "Corelicense 0 Inc", "licenses chip designs and patents for royalties", "Semiconductors & Related Devices", "royalties", (), "high")]
         + _rows("EQP", 3, "Etchtool", "manufactures wafer fab equipment", "Special Industry Machinery", "manufacturing")),
    ], [("fabless", "contract_manufacturing"), ("manufacturing", "contract_manufacturing")])


def auto_in():
    return build("IN", "Automobiles", [
        ("Vehicle makers", "Cars, two-wheelers and trucks.",
         _rows("OEM", 2, "Motorco", "manufactures and sells cars under its brands; a financing arm lends to buyers", "Passenger Cars & Utility Vehicles", "manufacturing",
               ("lending",))
         + _rows("TWO", 2, "Scootwell", "manufactures and sells two-wheelers under its brands", "2/3 Wheelers", "manufacturing")
         + _rows("CMP", 4, "Partsline", "makes auto components and parts supplied to vehicle makers", "Auto Components & Equipments", "components")),
        ("Tyres and parts", "Tyres.",
         _rows("TYR", 3, "Treadco", "makes tyres for vehicle makers and the replacement market", "Tyres & Rubber Products", "components")),
    ], [("manufacturing", "components")])


def insurance_in():
    return build("IN", "Insurance", [
        ("Insurers", "Underwrite risks.",
         _rows("LIF", 3, "Lifeshield", "a life insurance company selling term plans, annuities and pension policies", "Life Insurance", "life_insurance")
         + _rows("GIN", 3, "Covergen", "a general insurance company: motor, health and fire insurance", "General Insurance", "general_insurance")
         + [("REI0", "Reassure 0 Ltd", "a reinsurer taking risks from other insurers", "General Insurance", "reinsurance", (), "high")]),
        ("Distributors", "Distribute policies.",
         _rows("BRK", 3, "Policyhub", "an insurance broker earning commissions on policies it sells", "Insurance Distributors", "broking")),
    ], [("life_insurance", "general_insurance"), ("life_insurance", "broking"), ("general_insurance", "reinsurance")])


def banks_in():
    """Seven lenders in one layer, one of low confidence and one whose evidence doesn't show how it earns (R27: listed, left out of the figures)."""
    return build("IN", "Banks", [
        ("Retail and commercial lenders", "Take deposits and lend.",
         _rows("LND", 5, "Lendwell", "a bank: takes deposits and lends to households and firms", "Private Sector Bank", "lending")
         + [("LOW0", "Vaguebank 0 Ltd", "a financial group", "Private Sector Bank", "lending", (), "low"),
            ("UNK0", "Quietfin 0 Ltd", "", "Private Sector Bank", "", (), "")]),
        ("Fee businesses", "Fees.",
         _rows("AMC", 3, "Fundco", "an asset manager earning fees on mutual funds it manages", "Asset Management Company", "asset_management")),
    ], [("lending", "asset_management")])


NEW = {"chemicals (IN)": chemicals_in, "real estate (IN)": real_estate_in, "telecom (IN)": telecom_in, "telecom (US)": telecom_us,
       "consumer retail (US)": retail_us, "utilities and power (IN)": utilities_in, "metals and mining (IN)": metals_in}
BENCHMARK = {"IT services (IN)": it_in, "pharma (IN)": pharma_in, "semiconductors (US)": semis_us, "auto (IN)": auto_in,
             "insurance (IN)": insurance_in, "banks (IN)": banks_in}


def structures():
    for name, fn in {**NEW, **BENCHMARK}.items():
        yield name, fn()
