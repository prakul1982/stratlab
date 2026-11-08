"""A theme's companies start from the exchange's own classification; the AI only adds on top (THEMES, owner 31 Oct: "the whole purpose
of themes is company discoverability and understanding of a sector"; "should we index every company with their own sector so no AI
issue?"). Live before this, "India Defence" showed 4 companies and left out 9: the AI decided who was in.

- The sector index: the screener's stored index (screens.load_index) already holds every listed company's official classification, from
  its stored page: India, NSE's macro-economic sector and basic industry (the exchange's four-level list; "Aerospace & Defense",
  "Ship Building & Allied Services", "Explosives"); the US, the SEC's SIC division and industry ("Semiconductors & Related Devices").
  Nothing more is read for it: the index is rebuilt with the company pages, so a new listing joins when its page is built. (A US
  company with no SIC code stored has no page built and no market value either, so it can't be shown in a theme yet.)
- The theme's industries (`industries_for`): a curated table for the usual themes and the page's suggestions; any other theme, the AI
  picks from the market's own list of industries (a name that isn't on it is dropped), kept a month in storage.
- Membership (`with_base`): every company in those industries is the base. The AI's map can sort a base company into one of its
  layers and show the words from its description, but a "no" from that check only moves it out of that layer, never out of the
  theme. Companies the AI names from other industries are the additions, checked against their own descriptions as before
  (theme_check.py): confirmed with the quote, or not yet confirmed; a clear "no" leaves an addition out.

No source is called here; every name and industry is the stored index's."""
import json
import re
from datetime import datetime, timezone

# the version of the membership rules (who is in a theme, which industries, which layers): part of every cached read's key, so a read kept
# from before a deploy never keeps the old rules' companies or figures (R18: "Private banks" kept the public banks after the fix)
RULES = 28                       # R21: every confirmed company in one of the map's layers (place_rest); R22: layer names fit, currencies, extra layers; R25: one revenue model a layer; R26: models from more evidence and checked by it, names after the split; R27: primary model, tags and confidence, comparable segments, no one-company layer; R28: the companies to place carry their own descriptions (theme_routes.describe_unplaced)
INDUSTRIES_DAYS = 30            # the AI's pick of a free-text theme's industries is made again after this long (at most monthly)
FIGURES_MAX = 60                # companies the dive works figures out for: every one the AI named, then the largest of the base
DESCRIBE_MAX = 120              # base companies whose own one-line description is looked up for the page, largest first

# The usual themes and the page's suggestions: the official industries at their core. `words`: a theme naming any of them (or a
# phrase) has these industries; `unless`: a phrase that means a narrower theme with its own entry. A market with no list here is left to
# the AI's pick; an empty list says no official industry is the theme's core (a narrow theme inside a wide industry).
CONCEPTS = [
    {"words": {"defence", "defense", "military", "missile", "warship", "armament", "ammunition", "munition", "drone", "aerospace"},
     "IN": ["Aerospace & Defense", "Ship Building & Allied Services", "Explosives"], "IN_named": ["BEML"],
     "US": ["Guided Missiles & Space Vehicles & Parts", "Ordnance & Accessories, (No Vehicles/Guided Missiles)",
            "Search, Detection, Navigation, Guidance, Aeronautical Sys", "Aircraft Engines & Engine Parts",
            "Aircraft Parts & Auxiliary Equipment, Nec", "Ship & Boat Building & Repairing", "Aircraft"]},
    {"words": {"shipbuilding", "shipyard", "shipbuilder"}, "IN": ["Ship Building & Allied Services"], "US": ["Ship & Boat Building & Repairing"]},
    {"words": {"railway", "rail", "railroad", "train", "metro"}, "IN": ["Railway Wagons"],
     "IN_named": ["RVNL", "IRCON", "IRFC", "RITES", "IRCTC", "RAILTEL", "BEML", "CONCOR", "KERNEX"],
     "US": ["Railroads, Line-Haul Operating", "Railroad Equipment"]},
    {"words": {"ev", "evs"}, "phrases": ("electric vehicle", "electric vehicles", "electric mobility", "e mobility", "electric cars",
                                        "electric two wheelers", "electric scooters"),
     "IN": ["Passenger Cars & Utility Vehicles", "2/3 Wheelers", "Commercial Vehicles", "Auto Components & Equipments"],
     "US": ["Motor Vehicles & Passenger Car Bodies", "Motor Vehicle Parts & Accessories"]},
    {"words": {"auto", "automobile", "automotive", "car", "carmaker", "vehicle"}, "phrases": ("two wheelers",),
     "unless": ("ev", "evs", "electric vehicle", "electric vehicles", "electric cars", "electric two wheelers", "electric scooters"),
     "IN": ["Passenger Cars & Utility Vehicles", "2/3 Wheelers", "Commercial Vehicles", "Tractors", "Auto Components & Equipments",
            "Tyres & Rubber Products"],
     "US": ["Motor Vehicles & Passenger Car Bodies", "Motor Vehicle Parts & Accessories", "Tires & Inner Tubes", "Truck & Bus Bodies"]},
    # India's "Power Generation" mixes coal and gas plants with solar and wind ones, and the module and turbine makers sit in wide electrical
    # industries: India's renewables are a named list only, so a thermal-only company is out unless the AI names it (THEMES, 4 Nov)
    {"words": {"renewable", "solar", "wind"}, "phrases": ("clean energy", "green energy", "green power"),
     "IN": [], "IN_named": ["WAAREEENER", "PREMIERENE", "SUZLON", "INOXWIND", "KPIGREEN", "NTPCGREEN", "ADANIGREEN", "TATAPOWER", "ACMESOLAR",
                            "SJVN", "NHPC", "JSWENERGY", "EMMVEE", "VIKRAMSOLR", "SAATVIKGL", "WAAREERTL", "WEBELSOLAR", "BORORENEW", "INOXGREEN",
                            "SWSOLAR", "CLEANMAX", "IREDA"],
     "US": ["Cogeneration Services & Small Power Producers"],
     "US_named": ["NEE", "FSLR", "ENPH", "NXT", "BEP", "BEPC", "CWEN", "ORA", "SEDG", "RUN", "SHLS", "FLNC", "ARRY", "CSIQ", "JKS"]},
    {"words": {"electricity", "grid", "electrification", "utility", "utilities"}, "phrases": ("power sector", "power utilities", "power transmission"),
     "IN": ["Power Generation", "Integrated Power Utilities", "Power - Transmission", "Power Distribution", "Power Trading",
            "Heavy Electrical Equipment", "Cables - Electricals"],
     "US": ["Electric Services", "Electric & Other Services Combined", "Switchgear & Switchboard Apparatus", "Electrical Industrial Apparatus",
            "Motors & Generators", "Drawing & Insulating Of Nonferrous Wire", "Water, Sewer, Pipeline, Comm & Power Line Construction"]},
    {"words": {"bank", "banking"}, "IN": ["Private Sector Bank", "Public Sector Bank", "Other Bank"],
     "US": ["National Commercial Banks", "State Commercial Banks", "Commercial Banks, Nec", "Savings Institution, Federally Chartered",
            "Savings Institutions, Not Federally Chartered"]},
    {"words": {"nbfc", "lending", "lender", "microfinance"}, "phrases": ("housing finance", "consumer finance"),
     "IN": ["Non Banking Financial Company (NBFC)", "Housing Finance Company", "Microfinance Institutions", "Financial Institution"],
     "US": ["Personal Credit Institutions", "Short-Term Business Credit Institutions", "Miscellaneous Business Credit Institution",
            "Mortgage Bankers & Loan Correspondents"]},
    # the US files card networks and payment processors under wide service codes: named
    {"words": {"payment", "fintech", "upi"}, "IN": ["Financial Technology (Fintech)"],
     "US": [], "US_named": ["V", "MA", "PYPL", "AXP", "FIS", "GPN", "XYZ", "AFRM", "TOST", "FOUR", "COIN"]},
    {"words": {"insurance", "insurer"}, "IN": ["Life Insurance", "General Insurance", "Insurance Distributors"],
     "US": ["Life Insurance", "Fire, Marine & Casualty Insurance", "Accident & Health Insurance", "Insurance Agents, Brokers & Service",
            "Surety Insurance", "Title Insurance", "Insurance Carriers, Nec"]},
    {"words": {"broking", "broker", "exchanges", "amc", "depository"}, "phrases": ("capital markets", "capital market", "asset management", "wealth management"),
     "IN": ["Asset Management Company", "Stockbroking & Allied", "Exchange and Data Platform", "Depositories, Clearing Houses and Other Intermediaries",
            "Other Capital Market related Services", "Ratings", "Financial Products Distributor"],
     "US": ["Security Brokers, Dealers & Flotation Companies", "Security & Commodity Brokers, Dealers, Exchanges & Services", "Investment Advice"]},
    {"words": {"pharma", "pharmaceutical", "drug", "drugmaker", "medicine", "generic", "biotech", "biotechnology"},
     "unless": ("glp 1", "obesity"),
     "IN": ["Pharmaceuticals", "Biotechnology"],
     "US": ["Pharmaceutical Preparations", "Biological Products, (No Diagnostic Substances)", "Medicinal Chemicals & Botanical Products",
            "In Vitro & In Vivo Diagnostic Substances"]},
    # a narrow theme inside a wide industry (no official industry is its core): the theme's own companies, named, so it never rests on the
    # AI alone (THEMES, 4 Nov: "every curated theme has a base")
    {"words": {"glp"}, "phrases": ("glp 1", "obesity drugs", "weight loss drugs"),
     "IN": [], "IN_named": ["SUNPHARMA", "DRREDDY", "BIOCON", "ZYDUSLIFE", "LUPIN", "MANKIND", "CIPLA", "GLENMARK", "DIVISLAB"],
     "US": [], "US_named": ["LLY", "NVO", "AMGN", "VKTX", "PFE", "BDX", "WST", "TMO", "STVN", "HIMS", "ALT", "GPCR"]},
    {"words": {"hospital", "healthcare", "diagnostic", "medtech"}, "phrases": ("medical devices",),
     "IN": ["Hospital", "Healthcare Service Provider", "Medical Equipment & Supplies", "Healthcare Research, Analytics & Technology"],
     "US": ["Services-General Medical & Surgical Hospitals, Nec", "Services-Hospitals", "Services-Medical Laboratories",
            "Surgical & Medical Instruments & Apparatus", "Electromedical & Electrotherapeutic Apparatus"]},
    {"words": {"software", "saas"}, "phrases": ("it services", "indian it", "information technology"),
     "IN": ["Computers - Software & Consulting", "Software Products", "IT Enabled Services"],
     "US": ["Services-Prepackaged Software", "Services-Computer Programming Services", "Services-Computer Integrated Systems Design",
            "Services-Computer Processing & Data Preparation", "Services-Computer Programming, Data Processing, Etc."]},
    # the SEC files solar-cell and inverter makers under semiconductors (SIC 3674): they are renewables' named list, not the chip base;
    # the chip-equipment makers and Qualcomm file under other codes
    {"words": {"semiconductor", "chip", "chipmaker", "foundry"}, "IN": [], "IN_named": ["CGPOWER", "KAYNES", "MOSCHIP", "ASMTEC", "RIR", "TATAELXSI"],
     "US": ["Semiconductors & Related Devices"],
     "US_named": ["ASML", "LRCX", "KLAC", "QCOM", "TER", "ENTG"], "US_except": ["FSLR", "ENPH", "NXT", "SEDG", "SHLS", "ARRY", "CSIQ", "JKS"]},
    {"words": {"cybersecurity"}, "phrases": ("cyber security",), "IN": [], "IN_named": ["QUICKHEAL"],
     "US": [], "US_named": ["CRWD", "PANW", "FTNT", "ZS", "OKTA", "S", "CHKP", "NET", "TENB", "RPD", "QLYS", "VRNS", "GEN", "AKAM"]},
    {"words": {"datacenter", "datacentre"}, "phrases": ("data center", "data centers", "data centre", "data centres"),
     "IN": [], "IN_named": ["ANANTRAJ", "NETWEB", "TECHNOE", "TATACOMM", "BLUESTARCO", "BHARTIARTL"],
     "US": [], "US_named": ["EQIX", "DLR", "IRM", "NVDA", "AMD", "AVGO", "ANET", "VRT", "ETN", "SMCI", "DELL", "APLD", "CORZ", "CRWV", "NBIS"]},
    {"words": {"nuclear", "uranium", "smr"}, "IN": [], "IN_named": ["NTPC", "LT", "BHEL", "WALCHANNAG", "MTARTECH", "HCC"],
     "US": [], "US_named": ["CEG", "VST", "TLN", "CCJ", "OKLO", "SMR", "NNE", "BWXT", "LEU", "UEC", "GEV", "NXE", "DNN"]},
    {"words": {"telecom", "telecommunication", "5g"},
     "IN": ["Telecom - Cellular & Fixed line services", "Telecom - Infrastructure", "Telecom - Equipment & Accessories", "Other Telecom Services"],
     "US": ["Radiotelephone Communications", "Telephone Communications (No Radiotelephone)", "Communications Services, Nec", "Telephone & Telegraph Apparatus"]},
    {"words": {"cement"}, "IN": ["Cement & Cement Products"], "US": ["Cement, Hydraulic"]},
    {"words": {"steel"}, "IN": ["Iron & Steel", "Iron & Steel Products", "Sponge Iron", "Pig Iron"],
     "US": ["Steel Works, Blast Furnaces & Rolling Mills (Coke Ovens)", "Steel Works, Blast Furnaces & Rolling & Finishing Mills", "Steel Pipe & Tubes"]},
    {"words": {"mining", "mine", "miner", "metal", "aluminium", "aluminum", "copper", "zinc", "coal"},
     "IN": ["Coal", "Aluminium", "Copper", "Zinc", "Diversified Metals", "Industrial Minerals", "Ferro & Silica Manganese"],
     "US": ["Metal Mining", "Miscellaneous Metal Ores", "Bituminous Coal & Lignite Surface Mining", "Primary Production Of Aluminum",
            "Mining & Quarrying Of Nonmetallic Minerals (No Fuels)"]},
    {"words": {"gold", "silver"}, "phrases": ("precious metals",), "IN": ["Precious Metals"], "US": ["Gold And Silver Ores", "Silver Ores"]},
    {"words": {"oil", "petroleum", "refining", "refinery", "lng", "cng", "upstream"}, "phrases": ("oil and gas", "natural gas", "city gas"),
     "IN": ["Oil Exploration & Production", "Refineries & Marketing", "LPG/CNG/PNG/LNG Supplier", "Gas Transmission/Marketing",
            "Oil Equipment & Services", "Offshore Support Solution Drilling", "Oil Storage & Transportation"],
     "US": ["Crude Petroleum & Natural Gas", "Petroleum Refining", "Drilling Oil & Gas Wells", "Oil & Gas Field Services, Nec",
            "Oil & Gas Field Machinery & Equipment", "Natural Gas Transmission", "Natural Gas Distribution", "Pipe Lines (No Natural Gas)"]},
    {"words": set(), "phrases": ("specialty chemicals", "speciality chemicals"), "IN": ["Specialty Chemicals"],
     "US": ["Industrial Organic Chemicals", "Miscellaneous Chemical Products", "Chemicals & Allied Products"]},
    {"words": {"chemical", "agrochemical", "petrochemical"}, "unless": ("specialty chemicals", "speciality chemicals"),
     "IN": ["Specialty Chemicals", "Commodity Chemicals", "Petrochemicals", "Dyes And Pigments", "Pesticides & Agrochemicals", "Industrial Gases"],
     "US": ["Industrial Organic Chemicals", "Industrial Inorganic Chemicals", "Chemicals & Allied Products",
            "Plastic Materials, Synth Resins & Nonvulcan Elastomers", "Agricultural Chemicals"]},
    {"words": {"fertiliser", "fertilizer"}, "IN": ["Fertilizers"], "US": ["Agricultural Chemicals"]},
    {"words": {"fmcg", "staples"}, "phrases": ("consumer staples", "packaged food", "packaged foods"),
     "IN": ["Diversified FMCG", "Personal Care", "Packaged Foods", "Household Products", "Dairy Products", "Other Food Products", "Edible Oil",
            "Tea & Coffee", "Cigarettes & Tobacco Products", "Other Beverages"],
     "US": ["Food And Kindred Products", "Perfumes, Cosmetics & Other Toilet Preparations", "Soap, Detergents, Cleang Preparations, Perfumes, Cosmetics",
            "Beverages", "Bottled & Canned Soft Drinks & Carbonated Waters", "Cigarettes"]},
    {"words": {"realty", "reit", "property", "housing"}, "phrases": ("real estate",), "unless": ("housing finance",),
     "IN": ["Residential, Commercial Projects", "Real Estate related services", "Real Estate Investment Trusts (REITs)"],
     "US": ["Real Estate Investment Trusts", "Operative Builders", "Real Estate", "Real Estate Operators (No Developers) & Lessors"]},
    {"words": {"infrastructure", "infra", "construction", "road", "highway"},
     "IN": ["Civil Construction", "Road AssetsToll, Annuity, Hybrid-Annuity"],
     "US": ["Heavy Construction Other Than Bldg Const - Contractors", "Water, Sewer, Pipeline, Comm & Power Line Construction",
            "Construction - Special Trade Contractors"]},
    {"words": {"hotel", "tourism", "travel", "hospitality"}, "IN": ["Hotels & Resorts", "Tour, Travel Related Services"],
     "US": ["Hotels & Motels", "Hotels, Rooming Houses, Camps & Other Lodging Places"]},
    {"words": {"aviation", "airline", "airport"}, "IN": ["Airline", "Airport & Airport services"],
     "US": ["Air Transportation, Scheduled", "Airports, Flying Fields & Airport Terminal Services", "Air Transportation, Nonscheduled"]},
    {"words": {"logistics", "shipping", "port", "freight"}, "IN": ["Logistics Solution Provider", "Shipping", "Port & Port services", "Road Transport"],
     "US": ["Trucking (No Local)", "Arrangement Of Transportation Of Freight & Cargo", "Deep Sea Foreign Transportation Of Freight", "Air Courier Services"]},
    {"words": {"media", "entertainment", "broadcasting", "film"},
     "IN": ["Media & Entertainment", "TV Broadcasting & Software Production", "Film Production, Distribution & Exhibition", "Digital Entertainment",
            "Electronic Media", "Print Media"],
     "US": ["Cable & Other Pay Television Services", "Television Broadcasting Stations", "Services-Motion Picture & Video Tape Production"]},
    {"words": {"water"}, "IN": ["Water Supply & Management"], "US": ["Water Supply"]},
]


# the exchange's industry names as a layer shows them (R20, the owner: "Computer Peripheral Equipment, Nec" and "Services-Prepackaged Software" as
# layer names): the common ones by a plain name, any other cleaned (no "Services-" prefix, no "Nec", no "(No ...)", "&" for "And")
PLAIN_INDUSTRY = {
    "services-prepackaged software": "Software", "services-computer programming services": "IT services",
    "services-computer integrated systems design": "IT services", "services-computer programming, data processing, etc.": "IT services",
    "services-computer processing & data preparation": "Data processing", "computer peripheral equipment, nec": "Computer hardware",
    "electronic computers": "Computer hardware", "computer communications equipment": "Networking equipment",
    "computer storage devices": "Computer hardware", "semiconductors & related devices": "Semiconductors",
    "services-business services, nec": "Business services", "telephone communications (no radiotelephone)": "Telecom services",
    "radiotelephone communications": "Wireless telecom", "pharmaceutical preparations": "Pharmaceuticals",
    "biological products, (no diagnostic substances)": "Biotech products", "in vitro & in vivo diagnostic substances": "Diagnostics",
    "national commercial banks": "Commercial banks", "state commercial banks": "Commercial banks", "commercial banks, nec": "Commercial banks",
    "motor vehicles & passenger car bodies": "Vehicle makers", "motor vehicle parts & accessories": "Vehicle parts",
    "crude petroleum & natural gas": "Oil and gas producers", "petroleum refining": "Refining", "electric services": "Electric utilities",
    "real estate investment trusts": "REITs", "retail-eating places": "Restaurants", "services-medical laboratories": "Medical laboratories",
    "surgical & medical instruments & apparatus": "Medical instruments", "electromedical & electrotherapeutic apparatus": "Medical devices",
    "aircraft parts & auxiliary equipment, nec": "Aircraft parts", "guided missiles & space vehicles & parts": "Missiles and space",
    # India's exchange names where a plainer word says the same (R21: "Computers - Software & Consulting" as a layer)
    "computers - software & consulting": "IT services", "it enabled services": "IT-enabled services", "software products": "Software products",
    "passenger cars & utility vehicles": "Cars and utility vehicles", "2/3 wheelers": "Two- and three-wheelers", "auto components & equipments": "Auto components",
    "tyres & rubber products": "Tyres", "private sector bank": "Private banks", "public sector bank": "Public sector banks",
    "non banking financial company (nbfc)": "Non-bank lenders (NBFC)", "aerospace & defense": "Aerospace and defence",
    "ship building & allied services": "Shipbuilding", "telecom - cellular & fixed line services": "Telecom services",
    "residential, commercial projects": "Real estate developers", "road assetstoll, annuity, hybrid-annuity": "Road assets",
}


def plain_industry(name) -> str:
    """An official industry's name as a layer shows it: the common ones by a plain name (PLAIN_INDUSTRY), any other cleaned. Both markets."""
    raw = " ".join(str(name or "").split())
    if not raw:
        return raw
    hit = PLAIN_INDUSTRY.get(raw.lower())
    if hit:
        return hit
    t = re.sub(r"^services-\s*", "", raw, flags=re.I)
    t = re.sub(r",?\s*\bnec\b\.?", "", t, flags=re.I)
    t = re.sub(r",?\s*\((?:no|not|except)\b[^)]*\)", "", t, flags=re.I)
    t = re.sub(r"\s+and\s+", " & ", t, flags=re.I).strip(" ,-")
    if t.isupper() or t.islower():
        t = t.title()
    return t or raw


def key(name) -> str:
    """An industry name as compared: case and spacing aside (the SEC writes "Drawing & Insulating Of  Nonferrous Wire")."""
    return " ".join(str(name or "").split()).lower()


def _words(theme: str) -> tuple[str, set[str]]:
    t = " " + " ".join(re.findall(r"[a-z0-9]+", str(theme or "").lower())) + " "
    words = set(t.split())
    words |= {w[:-1] for w in list(words) if w.endswith("s") and len(w) > 3}        # "banks", "railways", "chips"
    return t, words


def concepts_of(theme: str) -> list[dict]:
    """The curated entries a theme names."""
    t, words = _words(theme)
    out = []
    for c in CONCEPTS:
        if any(f" {p} " in t for p in c.get("unless", ())):
            continue
        if words & c["words"] or any(f" {p} " in t for p in c.get("phrases", ())):
            out.append(c)
    return out


def known_industries(rows: list[dict]) -> dict[str, str]:
    """{key: the industry as the list writes it} for every industry in the market's index."""
    out = {}
    for r in rows or []:
        i = str(r.get("industry") or "").strip()
        if i:
            out.setdefault(key(i), i)
    return out


def named_lists(region: str, theme: str) -> tuple[list[str], list[str]]:
    """(symbols the curated table names as the theme's own, symbols it keeps out of the industry base unless the AI names them)."""
    named, out = [], []
    for c in concepts_of(theme):
        named += [s for s in c.get(f"{region}_named", []) if s not in named]
        out += [s for s in c.get(f"{region}_except", []) if s not in out]
    return named, [s for s in out if s not in named]


def curated(region: str, theme: str, known: dict[str, str]) -> list[str] | None:
    """The curated industries for a theme in a market (as the index writes them), or None when the table has no entry for it there."""
    lists = [c[region] for c in concepts_of(theme) if region in c]
    if not lists:
        return None
    out = []
    for names in lists:
        for n in names:
            got = known.get(key(n))
            if got and got not in out:
                out.append(got)
    return out


PICK_SYSTEM = """You map a market theme to the stock exchange's official industry classification. From the LIST of industries given (the
exchange's own names), pick the industries whose listed companies, nearly all of them, do the theme's core work. Pick none when every
industry on the list is much wider than the theme (a single product, a drug class, a technology inside a wider industry). Copy each
name exactly as it is on the list. At most 6.
Reply with ONLY this JSON: {"industries": ["<a name from the list>"]}"""


def ai_pick(theme: str, known: dict[str, str], ask) -> list[str]:
    """The industries the AI picks for a theme, only names on the market's list (anything else is dropped)."""
    got = ask(PICK_SYSTEM, f"THEME: {theme}\nLIST:\n" + json.dumps(sorted(known.values()), ensure_ascii=False))
    out = []
    for x in (got.get("industries") if isinstance(got, dict) else None) or []:
        n = known.get(key(x))
        if n and n not in out:
            out.append(n)
    return out[:6]


def _slug(theme: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(theme or "").lower()).strip("-")[:60]


# words every industry or theme shares, which say nothing about which industry: never matched on their own
_PLAIN = {"and", "the", "for", "with", "other", "others", "service", "services", "product", "products", "diversified", "industries", "industry",
          "misc", "miscellaneous", "general", "goods", "related", "allied", "india", "indian", "usa", "american", "stock", "stocks", "company",
          "companies", "sector", "sectors", "theme", "themes", "supply", "chain", "nec", "except", "including", "equipment", "equipments",
          "trading", "wholesale", "new", "based", "listed", "business", "businesses", "ltd", "inc"}


def _stem(w: str) -> str:
    """A word's start as industry names are matched on: plural and British/American endings aside ("fertilisers" and "Fertilizers",
    "ports" and "Port", "centres" and "Center" all meet on their first five letters)."""
    w = w.lower()
    if w.endswith("s") and len(w) > 4:
        w = w[:-1]
    return w[:5]


def _stems(text: str) -> set[str]:
    return {_stem(w) for w in re.findall(r"[a-z0-9]+", str(text or "").lower()) if len(w) >= 3 and w not in _PLAIN}


def words_pick(theme: str, known: dict[str, str]) -> list[str]:
    """The official industries whose names share a word with the theme ("paints" -> Paints; "cloud software" -> the software industries):
    the rule a typed theme falls back on when the AI picks none or can't answer. Deterministic, both markets."""
    tw = _stems(theme)
    return [name for k, name in sorted(known.items()) if tw & _stems(k)] if tw else []


# a theme that names a subset (R18, the owner: "Private banks" pulled in the public-sector banks): the words people write for one, as the
# exchange's industry names spell it
_ALIAS = {"psu": "public", "government": "public", "pvt": "private", "listed": ""}


def _concept_stems(theme: str) -> set[str]:
    """The stems of the curated entries' own trigger words and phrases that this theme names (they say which theme, not which part of it)."""
    out = set()
    for c in concepts_of(theme):
        out |= _stems(" ".join(c["words"]) + " " + " ".join(c.get("phrases", ())))
    return out


def subset_pick(theme: str, industries: list[str]) -> tuple[list[str], list[str]]:
    """(the industries kept, the industries left out) when the theme's name narrows its curated industries: a word of the theme that is not
    the entry's own trigger ("private" in "Private banks", "components" in "Auto components") and that some of the industries' names carry
    keeps only those. A theme that names no such word keeps them all."""
    t = " ".join(_ALIAS.get(w, w) for w in re.findall(r"[a-z0-9]+", str(theme or "").lower()))
    want = _stems(t) - _concept_stems(theme) - {_stem(w) for w in SIZE_WORDS}
    if not want or len(industries) < 2:
        return list(industries), []
    keep = [i for i in industries if want & _stems(i)]
    if not keep or len(keep) == len(industries):
        return list(industries), []
    return keep, [i for i in industries if i not in keep]


# a theme of one size of company (the owner: "small-cap"): India by SEBI's ranks of market value (the largest 100 large, the next 150 mid,
# the rest small), the US by market value ($10 bn and up large, $2 bn to $10 bn mid, below small)
SIZE_WORDS = ("cap", "caps", "smallcap", "smallcaps", "midcap", "midcaps", "largecap", "largecaps")
IN_RANKS = {"large": (1, 100), "mid": (101, 250), "small": (251, 10 ** 9)}
US_BANDS = {"large": (10000.0, 1e18), "mid": (2000.0, 10000.0), "small": (0.0, 2000.0)}       # $ million


def size_band(theme: str) -> str | None:
    """"small", "mid" or "large" when the theme names a size of company ("Small-cap pharma", "midcap IT"), else None."""
    t = " ".join(re.findall(r"[a-z0-9]+", str(theme or "").lower()))
    m = re.search(r"\b(small|mid|large)\s?caps?\b", t)
    return m.group(1) if m else None


def in_band(region: str, band: str | None, rows: list[dict]) -> set[str] | None:
    """The symbols of the market's companies of that size (None: no size named, everyone is in)."""
    if not band:
        return None
    caps = sorted(((r.get("market_cap") or 0, r["symbol"]) for r in rows or [] if r.get("symbol") and r.get("market_cap")), key=lambda x: (-x[0], x[1]))
    if region == "US":
        lo, hi = US_BANDS[band]
        return {s for c, s in caps if lo <= c < hi}
    lo, hi = IN_RANKS[band]
    return {s for k, (_, s) in enumerate(caps, 1) if lo <= k <= hi}


def industries_for(region: str, theme: str, rows: list[dict], ask, get_setting, set_setting, now=None) -> dict:
    """{"industries", "how", "named", "except"}: the official industries at the theme's core. "how":
    - "list": the curated table (with its named members and exclusions);
    - "ai": the AI's pick from the market's official list, kept INDUSTRIES_DAYS;
    - "words": the industries whose names share a word with the theme, when the AI picks none or can't answer now (THEMES, 4 Nov: a
      typed theme never rests on the AI alone), or the theme is an industry's own name;
    - "pending": the AI couldn't answer and no industry shares a word (asked again on the next request); "none": no index yet.
    A theme that is an official industry's own name always has that industry. `ask(system, text)` is the AI's JSON answer."""
    known = known_industries(rows)
    if not known:
        return {"industries": [], "how": "none", "named": [], "except": []}
    exact = known.get(key(theme))
    cur = curated(region, theme, known)
    if cur is not None:
        named, out = named_lists(region, theme)
        listed = {r.get("symbol") for r in rows or []}
        cur, drop = subset_pick(theme, cur + ([exact] if exact and exact not in cur else []))
        return {"industries": cur, "how": "list", "named": [s for s in named if s in listed], "except": out, "drop": drop}
    if exact:
        return {"industries": [exact], "how": "words", "named": [], "except": []}

    def answer(picked, how):
        if picked:
            return {"industries": picked, "how": how, "named": [], "except": []}
        words = words_pick(theme, known)
        return {"industries": words, "how": "words" if words else ("pending" if how == "pending" else how), "named": [], "except": []}
    now = now or datetime.now(timezone.utc)
    skey = f"theme:industries:{region}:{_slug(theme)}"
    try:
        hit = json.loads(get_setting(skey) or "null")
    except Exception:
        hit = None
    if isinstance(hit, dict) and hit.get("at") and hit.get("rules") == RULES:       # a pick kept under older rules is made again
        try:
            fresh = (now - datetime.fromisoformat(hit["at"])).days < INDUSTRIES_DAYS
        except ValueError:
            fresh = False
        if fresh:
            return answer([known[key(i)] for i in hit.get("industries") or [] if key(i) in known], "ai")
    try:
        picked = ai_pick(theme, known, ask)
    except Exception as e:                      # the AI busy: the words rule for now, the AI asked again next time
        print("theme base: industries not picked:", theme[:40], type(e).__name__, str(e)[:100])
        return answer([], "pending")
    try:
        set_setting(skey, json.dumps({"at": now.isoformat(timespec="seconds"), "industries": picked, "rules": RULES}, ensure_ascii=False))
    except Exception as e:
        print("theme base: industries not kept:", str(e)[:100])
    return answer(picked, "ai")


# ---------- membership ----------
def _named(m: dict) -> set[str]:
    return {c.get("ticker") for g in (m.get("value_chain") or []) + (m.get("sub_themes") or []) for c in g.get("companies") or [] if c.get("ticker")}


def with_base(m_before: dict, out: dict, rows: list[dict], industries: list[str], name_of=lambda n, s: n or s, named=(), exclude=(),
              drop=(), sized: set[str] | None = None) -> dict:
    """The checked map (`out`, from theme_check.check_placements on `m_before`) with every company of the theme's industries in it. Each
    company carries `base` (it is in an official industry of the theme), its `industry` and `cap` (the index's market value). A base company
    the AI put in a layer stays there when its words show it or weren't checked yet; one the check moved out of every layer, or the AI never
    named, is listed under its own industry as a layer of its own ("official": true), largest first. `placements` gets the honest counts:
    `total`, `base`, `added` (companies from other industries the AI named that are kept), `confirmed` (of those, shown in their own words),
    `left_out` (named additions whose own words said no) and the `industries`. `named`: the curated table's own members of the theme, base too
    (`basis` "list", listed under "Named in the theme's list" when the AI didn't place them); `exclude`: companies of the industries that are
    another theme's (solar-cell makers filed as semiconductors), out of the base unless the AI names them. `drop`: the industries a theme's
    name leaves out (subset_pick: the public-sector banks of "Private banks") and `sized`: the companies of the size it names (in_band), so
    a company the AI names from them is out too (R18)."""
    # a layer the AI left without a name (R20: four of the live Cybersecurity map's five, kept in the store from before ai.layer_name) is
    # dropped here too, so a stored map never draws "Layer 2 ·": its companies are then placed as any company the AI didn't name
    # R25: and one whose name only stands in for one ("placeholder" in the live R24 Insurance map), kept in the store from before ai.stand_in
    from .ai import stand_in
    m_before = {**m_before, "value_chain": [v for v in m_before.get("value_chain") or [] if v.get("official") or not stand_in(v.get("layer"))]}
    out = {**out, "value_chain": [v for v in out.get("value_chain") or [] if v.get("official") or not stand_in(v.get("layer"))]}
    idx = {r["symbol"]: r for r in rows or [] if r.get("symbol")}
    inset = {key(i) for i in industries}
    skip = set(exclude)
    gone = {key(i) for i in drop}
    by_industry = {s: r for s, r in idx.items() if key(r.get("industry")) in inset and s not in skip and (sized is None or s in sized)}
    by_list = {s: idx[s] for s in named if s in idx and s not in by_industry and (sized is None or s in sized)}
    base = {**by_industry, **by_list}

    def outside(c) -> bool:              # a company the theme's own name leaves out, whoever named it
        sym = c.get("ticker")
        if sym in base:
            return False
        r = idx.get(sym) or {}
        return key(r.get("industry")) in gone or (sized is not None and sym in idx and sym not in sized)
    out = {**out, "value_chain": [{**v, "companies": [c for c in v.get("companies") or [] if not outside(c)]} for v in out.get("value_chain") or []],
           "sub_themes": [{**x, "companies": [c for c in x.get("companies") or [] if not outside(c)]} for x in out.get("sub_themes") or []]}
    out["value_chain"] = keep_map_layers(m_before, out["value_chain"], base)

    def tag(c):
        r = idx.get(c.get("ticker")) or {}
        sym = c.get("ticker")
        return {**c, "base": sym in base, "basis": "industry" if sym in by_industry else "list" if sym in by_list else "added",
                "industry": r.get("industry") or "", "cap": r.get("market_cap")}
    out = dict(out)
    out["value_chain"] = [{**v, "companies": [tag(c) for c in v.get("companies") or []]} for v in out.get("value_chain") or []]
    out["sub_themes"] = [{**s, "companies": [tag(c) for c in s.get("companies") or []]} for s in out.get("sub_themes") or []]
    in_layer = {c["ticker"] for v in out["value_chain"] for c in v["companies"]}
    groups = [(ind, "industry", [r for s, r in by_industry.items() if key(r.get("industry")) == key(ind)]) for ind in industries]
    groups.append(("Named in the theme's list", "list", list(by_list.values())))
    for name, basis, members in groups:
        cos = sorted((r for r in members if r["symbol"] not in in_layer), key=lambda r: (-(r.get("market_cap") or 0), r["symbol"]))
        if cos:
            out["value_chain"].append({"layer": plain_industry(name) if basis == "industry" else name, "description": "", "official": True, "basis": basis,
                                       "companies": [{"ticker": r["symbol"], "name": name_of(r.get("name"), r["symbol"]), "what": "", "verified": False,
                                                      "base": True, "basis": basis, "industry": r.get("industry") or "", "cap": r.get("market_cap")} for r in cos]})
    placed = _named(out)
    added = {c["ticker"]: c for g in out["value_chain"] + out["sub_themes"] for c in g["companies"] if not c["base"]}
    confirmed = {s for s in added if any(c["ticker"] == s and c.get("verified") for g in out["value_chain"] + out["sub_themes"] for c in g["companies"])}
    out["screen"] = [x for x in out.get("screen") or [] if x.get("ticker") in placed]
    out["placements"] = {**(out.get("placements") or {}), "placed": len(placed), "total": len(placed), "base": len(base), "named": len(by_list),
                         "added": len(added), "confirmed": len(confirmed), "unconfirmed": len(added) - len(confirmed),
                         "left_out": len({s for s in _named(m_before) if s not in placed and s not in base}), "industries": list(industries)}
    return out


def keep_map_layers(m_before: dict, layers: list[dict], base: dict) -> list[dict]:
    """The AI map's own layers kept as the theme's scheme (R20: "Private banks" lost "Deposit gathering", "Retail and SME lending"... when
    the check of each bank's own words against each layer said no for nearly all of them, and every bank fell back to its exchange industry,
    one layer). When the check leaves fewer than two of the map's layers with a company but the map placed companies of the theme's own
    industries in two or more, each such company goes back to the first of the map's layers that named it ("verified" False: placed by the
    map, its words not checked for that layer). A company from another industry the check said no to stays out."""
    own = [v for v in layers if not v.get("official") and v.get("companies")]
    if len(own) >= 2:
        return layers
    before = {v.get("layer"): [c for c in v.get("companies") or [] if c.get("ticker") in base] for v in m_before.get("value_chain") or [] if not v.get("official")}
    if sum(1 for cos in before.values() if cos) < 2:
        return layers
    seen = {c.get("ticker") for v in layers for c in v.get("companies") or []}
    out = []
    for v in layers:
        add = []
        if not v.get("official"):
            for c in before.get(v.get("layer")) or []:
                if c.get("ticker") not in seen:
                    seen.add(c.get("ticker"))
                    add.append({**c, "what": "", "verified": False, "by_map": True})
        out.append({**v, "companies": list(v.get("companies") or []) + add} if add else v)
    return out


# ---------- every company in one of the map's layers (R21) ----------
# The AI's map names a few companies a layer (Defence: 12 of 42 in its five layers; IT services: one layer of its own beside three of the
# exchange's industries). After the map, the companies of the theme's industries it didn't place are put in the best of its own layers from
# their own words: one batched AI answer a theme (kept with the map), else by the words they share with each layer's name and description.
# Only a company that fits no layer goes to one "Other <theme> companies" layer; the exchange's industries are never layers beside the map's.
PLACE_MAX = 120                  # companies one AI answer places (the largest first); the rest by their words


def _place_words(layers: list[dict], what: str, industry: str) -> str:
    """The map layer whose name and description share the most words with a company's own words (and its industry's name), or "" for none."""
    from .theme_data import _stems, does_the_work
    best, score = "", 0
    for v in layers:
        words = _stems(f"{v.get('layer') or ''} {v.get('description') or ''}")
        mine = _stems(what or industry)          # its own words; the industry's name only when it has none (every company shares it)
        k = sum(1 for m_ in mine if any(m_ == w or (len(w) >= 5 and (m_.startswith(w) or w.startswith(m_))) for w in words))
        if k > score or (k == score and k and does_the_work(what, _stems(v.get("layer") or ""))):
            best, score = v.get("layer") or "", k
    return best if score else ""


RESIDUAL_SHARE, RESIDUAL_MIN = 0.15, 5      # an "Other" layer this large (a share of the companies, or a count) gets extra layers proposed


def other_label(theme: str) -> str:
    """"Other <theme> companies" with the theme's last word singular, as an adjective reads (R22: "Other semiconductors companies")."""
    words = " ".join(str(theme or "the theme").split()).split(" ")
    last = words[-1]
    if last.lower().endswith("ies") and len(last) > 4:
        last = last[:-3] + "y"
    elif last.lower().endswith("s") and not last.lower().endswith(("ss", "us", "is")) and len(last) > 3 and not last.isupper():
        last = last[:-1]
    words[-1] = last
    label = " ".join(words)
    if label[:1].isupper() and not label[:2].isupper():
        label = label[:1].lower() + label[1:]
    return f"Other {label} companies"


def place_rest(m: dict, theme: str, about_of, ask=None, kept: dict | None = None, facts_of=None) -> tuple[dict, dict]:
    """(the map with every base company in one of the map's own layers, the answer as worked out: {"assign": {symbol: {"layer", "by"}},
    "rename": {layer: {"name", "description"}}, "extra": [{"name", "description", "symbols"}]}). Runs only when the map has layers of its own;
    companies in its official-industry or named-list layers (not a list grouped by industry) are placed: from `kept` (the answer kept with the map),
    else one `ask` answer for up to PLACE_MAX of them, which also renames a layer whose name doesn't fit the companies it then holds and proposes
    up to two more layers when many fit none (R22); else by their words, the map's names kept. A company placed this way is marked "placed" (its
    words weren't checked against that layer, so it isn't "verified"); one that fits none goes to one "Other <theme> companies" layer.
    R25: the same answer gives each company's revenue model ("models": {symbol: model}, kept with the rest, so asked once a map); the layers are
    then split so each holds one way of earning (by_model).
    R26: each company's model rests on more of what the app keeps (`facts_of(symbol)` -> {"industry": its official industry path, "segments":
    [names], "filings": its filings' titles}, stored only), is kept only when that evidence shows it (theme_check.model_supported; else asked
    once more with the evidence, else unknown), and a layer the split reshaped whose name no longer fits how its companies earn is renamed
    (theme_check.names_for_models): every answer kept with the map, so asked once.
    R27: the same answer gives each company's secondary ways of earning ("model_tags") and how directly its evidence states its model
    ("model_confidence": high, medium, low; theme_check.model_confidence), kept with the rest; a company the AI left unknown whose own words
    state a model in so many words gets it ("medium"); the evidence also carries the company page's stored business read (`facts_of` ->
    "business") and the sentences of its description that speak of how it earns."""
    from .theme_check import (MODEL_MEMBERS, earning_lines, model_confidence, model_evidence, model_from_words, model_supported, model_tags,
                              names_for_models, recheck_models)
    vc = list(m.get("value_chain") or [])
    own = [v for v in vc if not v.get("official") and v.get("layer")]
    rest = [v for v in vc if v.get("official") and v.get("basis") in ("industry", "list") and not v.get("by_industry")]
    todo = [c for v in rest for c in v.get("companies") or []]
    kept = kept if isinstance(kept, dict) and "assign" in kept else {}
    if not own:
        return m, kept
    names = {v["layer"] for v in own}
    got = {s: x for s, x in (kept.get("assign") or {}).items() if isinstance(x, dict) and (x.get("layer") in names or x.get("layer") == "")}
    rename, extra = dict(kept.get("rename") or {}), list(kept.get("extra") or [])
    need = [c for c in sorted(todo, key=lambda c: -(c.get("cap") or 0)) if c["ticker"] not in got]
    asked, placed_models, placed_tags, placed_conf = False, None, {}, {}
    by_sym = {c.get("ticker"): c for v in vc for c in v.get("companies") or [] if c.get("ticker")}
    facts: dict[str, dict] = {}

    def facts_for(sym) -> dict:
        if sym not in facts:
            f = {}
            if facts_of is not None:
                try:
                    f = facts_of(sym) or {}
                except Exception as e:           # a store that can't answer now: the company's own words and industry still count
                    print("theme base: company facts not read:", sym, type(e).__name__, str(e)[:100])
            facts[sym] = f if isinstance(f, dict) else {}
        return facts[sym]

    def evidence(sym, words: bool = True) -> str:
        """A company's evidence of how it earns (theme_check.model_evidence); `words` False leaves out its description (sent beside it)."""
        c, f = by_sym.get(sym) or {}, facts_for(sym)
        own_words = about_of(sym) or c.get("what") or ""
        about = own_words if words else ""
        earns = None
        if not words:        # sent beside its description (its first 220 characters, or its one line): only what those leave out
            earns = earning_lines(own_words, limit=240)
            earns = "" if earns[:60] in str(own_words)[:200] else earns
        return model_evidence(f.get("industry") or c.get("industry") or "", about, f.get("segments") or (), f.get("filings") or "",
                              business=f.get("business") or "", earns=earns)

    def checked_models(ans: dict, syms) -> tuple[dict, dict, dict]:
        """(models, tags, confidence): the models the AI gave, each kept only when the company's evidence shows it; the rest asked once more
        with it, else unknown; one of `syms` still unknown whose own words state a model in so many words gets that one (R27, "medium").
        Each kept model's confidence is how directly its evidence states it (at most "medium" for one asked again), its tags those its
        evidence shows."""
        keep, rejected, tags, conf = {}, [], {}, {}
        for s_, md in (ans.get("models") or {}).items():
            ev = evidence(s_)
            if model_supported(md, ev):
                keep[s_] = md
                conf[s_] = model_confidence(md, ev, (ans.get("confidence") or {}).get(s_, ""))
                t = model_tags((ans.get("tags") or {}).get(s_), md, ev)
                if t:
                    tags[s_] = t
            else:
                rejected.append({"symbol": s_, "name": (by_sym.get(s_) or {}).get("name") or s_, "was": md, "evidence": ev})
        if rejected and ask is not None:
            try:
                for s_, md in recheck_models(rejected, ask, theme).items():
                    keep[s_] = md
                    conf[s_] = model_confidence(md, evidence(s_), "medium")
            except Exception as e:           # the AI busy: those companies' models stay unknown
                print("theme base: models not asked again:", theme[:40], type(e).__name__, str(e)[:100])
        for s_ in dict.fromkeys(syms):
            if s_ and s_ not in keep:
                ev = evidence(s_)
                md = model_from_words(ev)
                if md and model_supported(md, ev):
                    keep[s_], conf[s_] = md, "medium"
        return keep, tags, conf
    if need and ask is not None:
        asked = True
        from .theme_check import place_in_layers
        try:
            with_ev = [{**v, "companies": [{**c, "evidence": evidence(c.get("ticker"), not c.get("what"))} for c in (v.get("companies") or [])[:MODEL_MEMBERS]]}
                       for v in own]
            ans = place_in_layers(with_ev, [{"symbol": c["ticker"], "name": c.get("name") or c["ticker"], "industry": c.get("industry") or "",
                                         "about": about_of(c["ticker"]) or "", "evidence": evidence(c["ticker"], False)} for c in need[:PLACE_MAX]],
                                  ask, theme)
            got.update({s: {"layer": x if x in names else "", "by": "ai"} for s, x in ans["place"].items()})
            rename = {k: v for k, v in ans["rename"].items() if k in names}
            extra = ans["extra"]
            placed_models, placed_tags, placed_conf = checked_models(ans, [c["ticker"] for c in need[:PLACE_MAX]]
                                                                     + [c.get("ticker") for v in with_ev for c in v["companies"]])
        except Exception as e:               # the AI busy: the words place them now, the AI is asked again on the next check
            print("theme base: companies not placed by the AI:", theme[:40], type(e).__name__, str(e)[:100])
    for c in need:
        if c["ticker"] not in got:
            got[c["ticker"]] = {"layer": _place_words(own, about_of(c["ticker"]) or c.get("what") or "", plain_industry(c.get("industry"))), "by": "words"}
    by_layer: dict[str, list] = {}
    other = []
    for c in todo:
        x = got.get(c["ticker"]) or {}
        tag = {**c, "placed": x.get("by") or "words", "verified": False, **({"fit": True} if x.get("layer") else {})}
        (by_layer.setdefault(x["layer"], []) if x.get("layer") else other).append(tag)
    total = sum(len(v.get("companies") or []) for v in vc)
    extra_layers = []
    if extra and other and (len(other) >= RESIDUAL_MIN or len(other) > RESIDUAL_SHARE * max(1, total)):
        left = {c["ticker"]: c for c in other}
        for x in extra[:2]:
            cos = [{**left.pop(s_), "fit": True} for s_ in x.get("symbols") or [] if s_ in left]
            if len(cos) >= 2:
                extra_layers.append({"layer": x["name"], "description": x.get("description") or "", "by_place": True, "companies": cos})
        other = list(left.values())
    # the layers' names checked against the companies they hold once a map and its placements (R23: a map with nothing left to place kept
    # "Raw materials and castings" for forgers, since the check rode only on the placement call): asked again only when the members change
    sig = names_signature(own, by_layer)
    names_for = kept.get("names_for") if kept.get("names_for") == sig else None
    # how each company earns (R25): asked with the placements or the names' check, once a map; kept with them, never asked again for that map
    models = kept.get("models") if isinstance(kept.get("models"), dict) else None
    tags = dict(kept.get("model_tags") or {}) if isinstance(kept.get("model_tags"), dict) else {}
    conf = dict(kept.get("model_confidence")) if isinstance(kept.get("model_confidence"), dict) else None
    if asked:
        names_for = sig
        if placed_models is not None:
            models, tags, conf = {**(models or {}), **placed_models}, {**tags, **placed_tags}, {**(conf or {}), **placed_conf}
    elif ask is not None and (names_for is None or models is None):
        from .theme_check import place_in_layers
        try:
            said = lambda c: {**c, "what": c.get("what") or one_line(about_of(c.get("ticker")) or ""),           # noqa: E731 (its own words, for its model)
                              "evidence": evidence(c.get("ticker"), not c.get("what"))}
            sent = [{**v, "companies": [said(c) for c in (list(v.get("companies") or []) + by_layer.get(v["layer"], []))[:MODEL_MEMBERS]]} for v in own]
            ans = place_in_layers(sent, [], ask, theme)
            rename, names_for = {k: x for k, x in ans["rename"].items() if k in names}, sig
            models, tags, conf = checked_models(ans, [c.get("ticker") for v in sent for c in v["companies"]])
        except Exception as e:
            print("theme base: layer names not checked:", theme[:40], type(e).__name__, str(e)[:100])
    out_vc = []
    for v in vc:
        if v in rest:
            continue
        if v in own:
            v = {**v, "companies": list(v.get("companies") or []) + by_layer.get(v.get("layer"), [])}
            r = rename.get(v["layer"])
            if r and r.get("name"):            # a name that fits the companies the layer now holds; the map's name kept as "was" (R22)
                v = {**v, "layer": r["name"], "description": r.get("description") or v.get("description") or "", "was": v["layer"]}
        out_vc.append(v)
    out_vc += extra_layers
    if other:
        out_vc.append({"layer": other_label(theme), "description": "", "official": True, "basis": "rest",
                       "companies": sorted(other, key=lambda c: (-(c.get("cap") or 0), c["ticker"]))})
    model_names = None
    if models:
        before = {v["layer"]: {c.get("ticker") for c in v["companies"]} for v in out_vc if not v.get("official")}
        out_vc = by_model(out_vc, models, theme, tags=tags, confidence=conf)
        # R26: a layer of the map the split reshaped (companies moved in or out) whose name no longer fits how its companies earn is renamed by
        # the same check as the placement's; asked once a map and its split, kept with the rest
        reshaped = [v for v in out_vc if v["layer"] in before and not v.get("official") and not v.get("scale") and (v.get("model") or {}).get("line")
                    and not v["model"].get("sparse") and {c.get("ticker") for c in v["companies"]} != before[v["layer"]]]
        msig = model_names_signature(reshaped)
        model_names = kept.get("model_names") if isinstance(kept.get("model_names"), dict) and kept["model_names"].get("sig") == msig else None
        if model_names is None and ask is not None and reshaped:
            try:
                model_names = {"sig": msig, "rename": names_for_models(reshaped, ask, theme)}
            except Exception as e:
                print("theme base: layer names after the split not checked:", theme[:40], type(e).__name__, str(e)[:100])
        if model_names and model_names.get("rename"):
            out_vc = renamed_after_split(out_vc, {v["layer"] for v in reshaped}, model_names["rename"])
    return {**m, "value_chain": out_vc}, {"assign": got, "rename": rename, "extra": extra, **({"names_for": names_for} if names_for else {}),
                                          **({"models": models} if models is not None else {}), **({"model_names": model_names} if model_names else {}),
                                          **({"model_tags": tags} if models is not None and tags else {}),
                                          **({"model_confidence": conf} if models is not None and conf is not None else {})}


def model_names_signature(layers: list[dict]) -> str:
    """Which companies, and which way of earning, each layer the split reshaped holds: its name check is asked again only when this changes."""
    import hashlib
    parts = sorted(f"{v['layer']}:{(v.get('model') or {}).get('id')}:" + ",".join(sorted(c.get("ticker") or "" for c in v["companies"])) for v in layers)
    return hashlib.sha1("|".join(parts).encode(), usedforsecurity=False).hexdigest()[:16]


def renamed_after_split(vc: list[dict], names: set[str], rename: dict) -> list[dict]:
    """The layers with the split's renames (R26) applied to the layers in `names`: the map's name kept as "was", a name another layer has left alone."""
    taken = {v["layer"] for v in vc}
    out = []
    for v in vc:
        r = rename.get(v["layer"]) if v["layer"] in names else None
        if r and r.get("name") and r["name"] not in taken:
            taken.add(r["name"])
            v = {**v, "layer": r["name"], "description": r.get("description") or v.get("description") or "", "was": v.get("was") or v["layer"]}
        out.append(v)
    return out


# ---------- one revenue model a layer (R25) ----------
# The owner's outside review of the R23 decks: "avoid grouping businesses with fundamentally different revenue models just because they
# belong to the same broad theme" (IT services: hardware resellers in "Cloud, AI infrastructure and hardware", an 18-company "Mid-tier digital
# and cloud specialists" catch-all). Each company's model comes with the placement answer (theme_check.place_in_layers, kept with the map).
SPLIT_SHARE = 0.40              # a layer holding more than this share of the theme's placed companies is split...
SPLIT_MIN = 8                   # ...when it has at least this many, by revenue model, else by market value
SPLIT_PART = 3                  # each part of such a split holds at least this many companies


def _model_layer(name: str, cos: list[dict], **kw) -> dict:
    return {"layer": name, "description": "", "by_model": True, "companies": cos, **kw}


def by_model(vc: list[dict], models: dict, theme: str = "", tags: dict | None = None, confidence: dict | None = None) -> list[dict]:
    """The placed map's layers with one revenue model family each, from `models` ({symbol: model id}, theme_check.MODELS):
    1. a layer of the map whose companies earn in different ways keeps its main family (the most of its companies; a tie, the family of the first
       of them, the map's own pick); each other company moves to the layer whose main family is its own (the largest), else to a new layer named
       by that model ("Hardware resale and integration"). A company of the "Other" group whose model is known goes the same way, so "Other" keeps
       only companies the evidence can't place. A company with no known model stays where it is; so does one whose model is of "low"
       confidence (R27, `confidence`: {symbol: high/medium/low}), which counts as unknown.
    2. a layer above SPLIT_SHARE of the placed companies (and SPLIT_MIN or more) is split by its models when two or more hold SPLIT_PART
       companies each, else into its larger and smaller halves by market value.
    3. (R27) a split never leaves a layer of one company: a layer the split made or reshaped that holds one company gives it to the largest layer
       of its family, else to the theme's "Other" group, and is not a layer of its own.
    4. every layer of the map carries `model`: {"id", "family", "line", "known", "of", "out", "also"}, the one line the deck shows of what its
       companies have in common; R27: the companies whose model is unknown or of low confidence are listed but marked `model_out` (left out of
       the layer's figures and rankings; the line says how many and why), and the line names the commonest secondary way of earning of its
       companies ("3 of the 9 also earn from ..."; `tags`: {symbol: [model ids]}), so no company is shown as earning one way only.
    Every company carries "model", "model_tags" and "model_confidence" (R27, for the deck's checks). Facts only: the models are the companies'
    own evidence as the AI read it."""
    from collections import Counter

    from .theme_check import FAMILIES, MODELS, model_family
    tags, conf = tags or {}, confidence or {}
    every = {s: m_ for s, m_ in (models or {}).items() if m_ in MODELS}
    models = {s: m_ for s, m_ in every.items() if conf.get(s) != "low"}
    out = [dict(v, companies=list(v.get("companies") or [])) for v in vc]
    own = [v for v in out if not v.get("official")]
    if not own or not every:
        return vc
    fam = lambda c: model_family(models.get(c.get("ticker")))       # noqa: E731
    before = {id(v): {c.get("ticker") for c in v["companies"]} for v in own}

    def main(cos):
        counts = Counter(fam(c) for c in cos if fam(c))
        if not counts:
            return ""
        top = max(counts.values())
        return next(fam(c) for c in cos if fam(c) and counts[fam(c)] == top)

    def name_of(cos, f):
        fines = {models[c["ticker"]] for c in cos if c.get("ticker") in models and fam(c) == f}
        return MODELS[next(iter(fines))][1] if len(fines) == 1 else FAMILIES.get(f, (MODELS[sorted(fines)[0]][1],))[0]

    # 1. one family a layer; "Other" keeps only what the evidence can't place
    mains, movers = {}, []
    for v in own:
        f = mains[id(v)] = main(v["companies"])
        if f:
            movers += [c for c in v["companies"] if fam(c) not in ("", f)]
            v["companies"] = [c for c in v["companies"] if fam(c) in ("", f)]
    for v in out:
        if v.get("official") and v.get("basis") == "rest":
            movers += [{**c, "fit": True} for c in v["companies"] if fam(c)]
            v["companies"] = [c for c in v["companies"] if not fam(c)]
    home = {}
    for v in own:
        f = mains[id(v)]
        if f and (f not in home or len(v["companies"]) > len(home[f]["companies"])):
            home[f] = v
    new: dict[str, dict] = {}
    for c in movers:
        f = fam(c)
        target = home.get(f) or new.setdefault(f, _model_layer("", []))
        target["companies"].append({**c, "moved": True})
    taken = {v["layer"] for v in out}
    for f, v in new.items():
        nm = name_of(v["companies"], f)
        v["layer"] = nm if nm not in taken else f"{nm}, by revenue model"
        taken.add(v["layer"])
    rest_at = next((i for i, v in enumerate(out) if v.get("official")), len(out))
    out[rest_at:rest_at] = list(new.values())
    out = [v for v in out if v["companies"] or not v.get("official") or v.get("basis") != "rest"]

    # 2. size: no catch-all above SPLIT_SHARE of the placed companies when a split is possible
    total = sum(len(v["companies"]) for v in out)
    for _ in range(4):
        # a half of an earlier split isn't halved again (R26: a catch-all of mostly unknown models became "… (smaller) (smaller)")
        big = next((v for v in out if not v.get("official") and not v.get("scale") and len(v["companies"]) >= SPLIT_MIN
                    and len(v["companies"]) > SPLIT_SHARE * total), None)
        if big is None:
            break
        at = out.index(big)
        cos = big["companies"]
        fines = Counter(models[c["ticker"]] for c in cos if c.get("ticker") in models)
        parts = [m_ for m_, n in fines.most_common() if n >= SPLIT_PART]
        if len(parts) >= 2:
            add = []
            for m_ in parts[1:]:
                mine = [c for c in cos if models.get(c.get("ticker")) == m_]
                cos = [c for c in cos if models.get(c.get("ticker")) != m_]
                same = next((v for v in out if v is not big and v["layer"] == MODELS[m_][1]), None)
                if same is not None:
                    same["companies"] += mine
                else:
                    add.append(_model_layer(MODELS[m_][1], mine))
            big["companies"] = cos
            out[at + 1:at + 1] = add
            continue
        ranked = sorted(cos, key=lambda c: (-(c.get("cap") or 0), c.get("ticker") or ""))
        half = len(ranked) // 2
        if half < SPLIT_PART:
            break
        name = big["layer"]
        small = _model_layer(f"{name} (smaller)", ranked[half:], scale="smaller", sibling=f"{name} (larger)")
        out[at] = {**big, "layer": f"{name} (larger)", "companies": ranked[:half], "scale": "larger", "sibling": small["layer"]}
        out.insert(at + 1, small)

    # 3. no layer of one company made by the split (R27: the live R26 IT deck had a visa and e-governance firm alone, a full page, as
    # "Hotels, travel and consumer services")
    out = _no_single_layers(out, before, main, fam, theme)

    # 4. what each layer's companies have in common, and who is left out of its figures
    for v in out:
        v["companies"] = [{**c, "model": every.get(c.get("ticker"), ""), "model_tags": list(tags.get(c.get("ticker")) or []),
                           "model_confidence": conf.get(c.get("ticker"), "") if c.get("ticker") in every else ""} for c in v["companies"]]
        if v.get("official"):
            continue
        cos = v["companies"]
        f = main(cos)
        known = [c for c in cos if fam(c) == f] if f else []
        if not known:
            if cos:          # R26: said plainly, never left blank beside layers that have a line
                line = (f"None of these {len(cos)} companies' descriptions shows how it earns, so no common way of earning is given for this group."
                        if len(cos) > 1 else "Its description doesn't show how it earns.")
                if v.get("scale"):
                    line += f" The {v['scale']} half of one group by market value; the other half is “{v['sibling']}”."
                v["model"] = {"id": "", "family": "", "line": line, "known": 0, "of": len(cos), "sparse": True}
            continue
        fines = {models[c["ticker"]] for c in known}
        mid = next(iter(fines)) if len(fines) == 1 else f
        what = MODELS[mid][2] if mid in MODELS else FAMILIES.get(f, ("", MODELS[sorted(fines)[0]][2]))[1]
        rest = [c for c in cos if fam(c) != f]
        known_ids = {c.get("ticker") for c in known}
        v["companies"] = [c if c.get("ticker") in known_ids else {**c, "model_out": True} for c in cos]
        sparse = len(known) * 2 < len(cos)
        if sparse:
            # R26: a line resting on a few of a layer's companies isn't what they have in common: said plainly instead (the live R25 IT services
            # deck, "8 of 50; the others' descriptions don't show how they earn"); R27: the others are left out of its figures
            line = f"How they earn is shown for only {len(known)} of these {len(cos)} companies, mainly {what}; {out_line(rest, 'the other')}"
        else:
            line = f"They earn mainly from {what}."
            if rest:
                line += " " + out_line(rest, f"of {len(cos)}")
        also = also_earn(known, f)
        if also:
            n_, t_ = also
            line += f" {n_} of the {len(known)} also earn from {MODELS[t_][2]}."
        if v.get("scale"):
            line += f" The {v['scale']} half of one group by market value; the other half is “{v['sibling']}”."
        v["model"] = {"id": mid, "family": f, "line": line, "known": len(known), "of": len(cos), "out": len(rest),
                      "also": [{"id": also[1], "n": also[0]}] if also else [], **({"sparse": True} if sparse else {})}
    return out


def out_line(rest: list[dict], of: str) -> str:
    """How many of a layer's companies are left out of its figures and rankings, and why (R27): their model unknown, or of low confidence."""
    n = len(rest)
    low = sum(1 for c in rest if c.get("model_confidence") == "low")
    why = ("doesn't show how it earns" if n == 1 else "doesn't show how they earn") if not low else \
          ("shows how it earns only weakly" if n == 1 else "shows how they earn only weakly") if low == n else \
          "doesn't show, or only weakly shows, how they earn"
    if of.startswith("the other"):
        return f"the other {n} {'is' if n == 1 else 'are'} listed but left out of this layer's figures and rankings, as {'its' if n == 1 else 'their'} evidence {why}."
    return f"{n} {of} {'is' if n == 1 else 'are'} listed but left out of this layer's figures and rankings, as {'its' if n == 1 else 'their'} evidence {why}."


def also_earn(known: list[dict], family: str) -> tuple[int, str] | None:
    """(how many, model) the commonest secondary way of earning of a layer's companies outside the layer's own family (R27), or None."""
    from collections import Counter

    from .theme_check import model_family
    counts, first = Counter(), {}
    for i, c in enumerate(known):
        for t in c.get("model_tags") or []:
            if model_family(t) and model_family(t) != family:
                counts[t] += 1
                first.setdefault(t, i)
    if not counts:
        return None
    t = min(counts, key=lambda t: (-counts[t], first[t]))
    return counts[t], t


def _no_single_layers(out: list[dict], before: dict, main, fam, theme: str) -> list[dict]:
    """The layers with none of one company that the split made or reshaped (R27): its company joins the largest other layer of its own family,
    else the theme's "Other" group (made when there is none), marked "single"."""
    singles = [v for v in out if not v.get("official") and len(v["companies"]) == 1
               and (v.get("by_model") or id(v) not in before or {c.get("ticker") for c in v["companies"]} != before[id(v)])]
    if not singles:
        return out
    for v in singles:
        c = v["companies"][0]
        f = fam(c)
        same = [x for x in out if x is not v and x not in singles and not x.get("official") and x["companies"] and f and main(x["companies"]) == f]
        if same:
            target = max(same, key=lambda x: len(x["companies"]))
            target["companies"].append({**c, "moved": True, "single": True})
        else:
            other = next((x for x in out if x.get("official") and x.get("basis") == "rest"), None)
            if other is None:
                other = {"layer": other_label(theme), "description": "", "official": True, "basis": "rest", "companies": []}
                out.append(other)
            other["companies"].append({**c, "moved": True, "single": True, "fit": True})
        v["companies"] = []
    return [v for v in out if not (v in singles and v.get("by_model"))]


def names_signature(own: list[dict], by_layer: dict) -> str:
    """Which companies each of the map's layers holds once placed: the layer-name check is asked again only when this changes."""
    import hashlib
    parts = sorted(f"{v['layer']}:" + ",".join(sorted(c.get("ticker") or "" for c in list(v.get("companies") or []) + by_layer.get(v["layer"], [])))
                   for v in own)
    return hashlib.sha1("|".join(parts).encode(), usedforsecurity=False).hexdigest()[:16]


def for_figures(m: dict, cap: int = FIGURES_MAX) -> tuple[dict, dict]:
    """(the map the dive's figures, prices and news are worked out on, {"shown", "of"}): every company the AI named, then the largest of
    the rest of the base, `cap` in all at most (a theme of 500 drug makers is listed in full, its figures on the largest). Official
    layers left with no company are dropped."""
    # the companies the AI named itself; one placed in a layer after the map (place_rest) is base, by size like the rest
    named = {c["ticker"] for v in m.get("value_chain") or [] if not v.get("official") for c in v.get("companies") or [] if not c.get("placed")}
    named |= {c["ticker"] for s in m.get("sub_themes") or [] for c in s.get("companies") or []}
    rest = sorted({(c.get("cap") or 0, c["ticker"]) for v in m.get("value_chain") or [] for c in v.get("companies") or []
                   if (v.get("official") or c.get("placed")) and c["ticker"] not in named}, key=lambda x: (-x[0], x[1]))
    keep = named | {s for _, s in rest[:max(0, cap - len(named))]}
    total = len(named | {s for _, s in rest})
    vc = []
    for v in m.get("value_chain") or []:
        cos = [c for c in v.get("companies") or [] if c["ticker"] in keep]
        if cos or not v.get("official"):
            vc.append({**v, "companies": cos})
    return {**m, "value_chain": vc}, {"shown": len(keep), "of": total}


def to_describe(m: dict, n: int = DESCRIBE_MAX) -> list[str]:
    """The base companies whose own one-line description the page shows (official layers, largest first), at most `n`."""
    rows = sorted({(c.get("cap") or 0, c["ticker"]) for v in m.get("value_chain") or [] for c in v.get("companies") or []
                   if v.get("official") or c.get("placed")}, key=lambda x: (-x[0], x[1]))
    return [s for _, s in rows[:n]]


_FIRST = re.compile(r"^(.{20,240}?[.;])(?:\s|$)")
# what a company's description says before its business (the owner, 7 Nov: "**Company Overview **", "Incorporatedin1994", "Business Overview:")
_MARKUP = re.compile(r"\*+|#+")
_HEADING = re.compile(r"\s*\b(?:company|business|corporate)\s+(?:overview|profile|description)\s*:?|\s*\babout\s+(?:us|the\s+company)\s*:", re.I)
_GLUED = re.compile(r"(?i)\b(incorporated|established|founded|set up|formed)(in)(\d{4})")
_HISTORY = re.compile(r"^(?:originally\s+)?(?:incorporated|established|founded|set up|formed|promoted)\b[^,.;]*?\b(?:in|on)\s+\d{4}\s*(?:,|as\b[^,]*,|and\b)?\s*", re.I)
# a results or sales line, not what the company does: "reported total dispatches of 7,34,403 units in October 2026"
_PRESS = re.compile(r"\b(?:reported|announced|posted|recorded|registered|clocked)\b.{0,60}\d|\b\d[\d,.]*\s*(?:units|crore|lakh|million|billion)\b.{0,30}"
                    r"\b(?:in|for|during)\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|q[1-4]|fy)", re.I)
_DOES = re.compile(r"\b(?:manufactur|make|produc|suppl|provid|engag|offer|design|develop|sell|operat|build|distribut|deal|trad|serv|run|own|"
                   r"leader|maker|player|largest|company|business)", re.I)


def _sentences(t: str) -> list[str]:
    return [x.strip() for x in re.split(r"(?<=[.;])\s+(?=[A-Z“\"(])", t) if x.strip()]


def one_line(about: str) -> str:
    """The first sentence of a company's own description that says what it does (its words): headings and markdown left off, words an
    extraction glued together parted ("Incorporatedin1994"), a founding-history opening and a results line (units sold in a month) skipped.
    A sentence too long for the line is cut at a word with an ellipsis, never mid-word. "" when there is no description."""
    t = _HEADING.sub(". ", _MARKUP.sub(" ", _GLUED.sub(r"\1 \2 \3", str(about or ""))))
    t = " ".join(re.sub(r"^[\s.]+|(?<=[.;])\s*\.\s", " ", t).split())
    if not t:
        return ""
    if t.startswith("From its own filings:"):           # the filings that back a company with no description: said as filings (own_filings)
        m = _FIRST.match(t)
        return (m.group(1) if m else t[:200]).rstrip(" .;")
    picks = []
    for x in _sentences(t):
        x = _HISTORY.sub("", x).strip(" ,;:-–—")
        if len(x) < 15 or _PRESS.search(x):
            continue
        picks.append(x)
    best = next((x for x in picks if _DOES.search(x)), picks[0] if picks else "")
    if not best:
        m = _FIRST.match(t)
        best = "" if _PRESS.search(t) else (m.group(1) if m else t)
    if not best:
        return ""
    m = _FIRST.match(best + " ")
    if m:
        return m.group(1).rstrip(" .;")
    if len(best) <= 240:
        return best.rstrip(" .;")
    cut = best[:220]
    return cut[:cut.rfind(" ")].rstrip(" ,;:") + "…"


def described(m: dict, about_of) -> dict:
    """The map with each official layer's company carrying `what`: the first sentence of its own description, from `about_of(symbol)`
    (the description or None; it never reads more than the caller allows). A company with none keeps "", which the page shows as not yet
    confirmed from its own description."""
    out = dict(m)
    vc = []
    for v in m.get("value_chain") or []:
        if v.get("official") or any(c.get("placed") for c in v.get("companies") or []):
            cos = []
            for c in v.get("companies") or []:
                if v.get("official") or c.get("placed"):          # a company placed after the map shows its own words too (R21)
                    about = about_of(c["ticker"])
                    c = {**c, "what": one_line(about) if about else ""}
                cos.append(c)
            v = {**v, "companies": cos}
        vc.append(v)
    out["value_chain"] = vc
    return out


# ---------- US companies with no industry on file ----------
# A US company whose page isn't built has no SIC code in the index (967 of 7,021 on 4 Nov). Each theme check reads a few of their SEC
# records (the submissions JSON the company pages read) and keeps the code, so they join a theme by industry; no job of its own.
SIC_KEY = "theme:sic:US"
SIC_DAYS = 30                   # a company the SEC gave no code for is asked again after this long
SIC_PER_RUN = 40                # records read in one theme check, at most
SIC_BUDGET = 20.0               # ...and seconds spent on them


def with_sic(rows: list[dict], stored: dict) -> list[dict]:
    """The index rows with the industry kept from the SEC's record filled in where the index has none."""
    paths = (stored or {}).get("paths") or {}
    out = []
    for r in rows or []:
        p = paths.get(r.get("symbol")) if not r.get("industry") else None
        out.append({**r, "sector": r.get("sector") or p[0], "industry": p[-1]} if p else r)
    return out


def unclassified(rows: list[dict]) -> int:
    return sum(1 for r in rows or [] if r.get("symbol") and not r.get("industry"))


def fill_sic(rows: list[dict], stored: dict, read, now=None, limit: int = SIC_PER_RUN, budget: float = SIC_BUDGET) -> tuple[dict, int]:
    """(the kept codes with up to `limit` more read, how many were read). `read(symbol)` -> the SIC path ([division, industry]), [] when
    the SEC has none, or raises when it can't answer now (tried again next time). Largest first, then A to Z; a company tried within
    SIC_DAYS with no code is skipped."""
    import time as _t
    now = now or datetime.now(timezone.utc)
    stored = {"paths": dict((stored or {}).get("paths") or {}), "tried": dict((stored or {}).get("tried") or {})}
    cut = (now.date().toordinal() - SIC_DAYS)
    todo = []
    for r in sorted(rows or [], key=lambda r: (-(r.get("market_cap") or 0), str(r.get("symbol")))):
        s = r.get("symbol")
        if not s or r.get("industry") or s in stored["paths"]:
            continue
        t = stored["tried"].get(s)
        if t and datetime.fromisoformat(t).date().toordinal() > cut:
            continue
        todo.append(s)
    started, n = _t.monotonic(), 0
    for s in todo[:limit]:
        if _t.monotonic() - started > budget:
            break
        try:
            path = read(s)
        except Exception as e:
            print("theme base: SEC record not read:", s, type(e).__name__, str(e)[:80])
            continue
        n += 1
        if path:
            stored["paths"][s] = list(path)[:2]
            stored["tried"].pop(s, None)
        else:
            stored["tried"][s] = now.date().isoformat()
    return stored, n
