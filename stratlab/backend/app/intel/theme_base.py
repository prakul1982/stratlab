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
RULES = 48                       # R48 (lane ex49, the outside review of the live Release 48 Consumer retail deck: lululemon in "Apparel and consumer brand owners" by its own words, left out of its figures as "another business"; proven on the exact replay of the live Release 46 placement inputs, where it is the one company of the 14 themes whose place in its layer's figures changes): a company read as a retailer whose own words say it designs the goods it sells (or makes them under its own brand), that the answer also read as a maker, and whose words say its layer's name, is in a layer of makers' figures (by_model `own_goods`); each company left out of a layer's figures carries why, precisely (by_model `out_why`: another business than its industry, another way of earning, how it earns read only weakly, no description of its own, words that don't state how it earns); R47 (lane cl48, the outside review of the live Release 46 Consumer retail deck: a designer of branded athletic apparel in "Off-price, dollar and discount store chains"; proven on the exact replay of the live Release 46 placement inputs): a company leaving a map layer by how it earns joins the largest layer of its family by default only when its own words say that layer's name or the name states no kind of business; else the map's layer it is in when its words say that layer's name (out of its figures), else a layer of its family sharing two of its words, else "Other" (by_model.home_of); a compound of a short word ("off-price") is one word in a layer's words, so "branched off" says nothing of it (whole_stems, says_most_of); a company listed in a layer as another way of earning is said to earn another way, never to have evidence that doesn't show how it earns (out_line); an industry of a replaced AI pick most of whose companies were in informative layers stays in the new pick (industries_for `held`); R46 (lane cv47, the live Release 46 Utilities deck: the cable and electrical equipment makers' layers formed on every replay but never on live, proven on the exact replay of the live Release 46 placement inputs, which carry each company's stored facts): the titles of a company's filings ("From its own filings: ...") are no words of its own (own_text), so their "own" no longer says "Makers of their own products" and keeps a cable maker out of its industry's layer (from_other 3); R45 (lane tx2, the outside review of the live Release 45 decks: Bosch and Asahi India Glass out of the component suppliers' layer; proven on the exact replay of the live Release 45 Automotive placement inputs): a company leaves a map layer mostly of its industry for another layer of its industry only on evidence of that layer (its own words say its name, or it holds a larger share of its industry: by_model evidence_for); the previous live placement of the same map (theme_changes' snapshot, place_rest `previous`) is kept by a company the split would move out of it with no evidence of the new layer, and by an unchecked map pick with no evidence of the layer it is in (held_to_previous); R44 (lane c1, the outside review of the live Release 43 decks, proven on the exact replay of its placement inputs): the companies left in "Other" placed only by their own words or official industry (theme_base.from_other: a layer whose name says all their industry says, the one layer of their way of earning whose name their words say two or more and half of the words of, a layer of one official industry made of them and of those the split moved by how they earn alone: ferro alloy, aluminium product, cable and electrical equipment makers), a map pick from another industry whose words say its layer's name is confirmed by them (confirmed_by_words: PB Fintech), a sportsbook, broadcast network, enterprise software house, VR concert producer and diversified holding company filed as retail are another business; R43 (lane d1, the outside review of the live Release 41 decks, proven on the exact replay of its placement inputs): a company the map named in a layer whose way of earning no layer of the map has stays in that layer, out of its figures (Arm, Fortinet); the largest layer of a family whose name states a kind of business the company's words don't say takes it by industry only as the family's catch-all, and such companies of one official industry with the like of them in "Other" make a layer of that industry (the apparel chains); a company named in a sub-theme only is placed like the theme's own; a company in no layer with no words of its own is "not checked yet" ("unread"); a weak-evidence company of the layer's industry is in its figures on its industry (Mahindra & Mahindra); pawnbrokers, IT resellers to business, blank-check companies, banks, payments and travel firms filed as retail are another business; "real estate development" is a developer's words; a maker read as a telecom operator makes its own products; R40 (lane s3-r40, the owner's review of the live Release 39 decks, proven on the exact replay of its placement inputs): a layer whose shown name states two ways of earning takes a company of either that holds its industry and whose words say what its name says (online sellers into "Online retailers and marketplaces"); a company the theme's industry brought in whose own words describe another business is dropped from the theme and named on its coverage (propane distributors under retail, solar makers under semiconductors: theme_base.without_off_industry); in a layer of one official industry a company of the layer's kin of making is in its figures (Bosch, Asahi India Glass: by_model KIN_FAMILIES); a layer the split named only by how its companies earn is never ranked ("by_how"); R41 (lane s2-exact, exact replays of the live Release 38.1 placement from its placement inputs): a company leaving a map layer by how it earns stays in it, out of its figures, when that layer is mostly of its industry and no layer of its family is (Bosch, Asahi India Glass); a layer whose name states another way of earning is not the map's layer of a company's industry, and the largest stands by default only as its family's catch-all (online sellers in "Off-price"); a company the split by model moved joins a map layer in 3b only when it fits (Qorvo in "Semiconductor equipment"); a model asked apart from the placement moves no company out of the map layer the placement put it in, and an answer carried from earlier rules sticks: nothing it answered is asked again (place_rest `carried`; Hikal and Brooks); R38.1: a kept placement carried back through every version that kept none of its own (theme_routes.placed), past 39's placements asked again from nothing; R38 (lane s1-fit, the outside review of the live R37 decks: 34 companies moved into "Off-price, dollar and value-format retailers", Micron, Intel and SK Hynix into "Semiconductor equipment"): a company leaving "Other" that the largest layer of its family neither holds by industry nor by words goes to the layer of its family that fits it, else stays in "Other", never the largest by default; a split-made layer joins a map layer of the same model only with the companies whose words fit it (by_model.home_of, fits). R37 (lane r2, the owner: misclassifications across all themes): a company no answer gave a model takes the one its own words state in so many words, read since (theme_check.stated_model, refine_kept), a bank's or lender's industry is lending, a landlord's own words make it one whatever its industry, OSAT and ESDM words are contract making, own-fab words read in an annual report make a chip maker no fabless one, a company leaving "Other" joins the largest layer of its family only when that holds its industry or words, else a layer all of its industry sharing its words, else stays in "Other" when no layer holds either (by_model.home_of), a contract maker joins only a contract layer of its kind (theme_check.contract_kind), a company the map placed whose model only its words state stays in its layer (by_model settled); R36 (GPT review of the live R35 decks): foundry words with products of its own named are no contract maker's and a chip maker naming its own products given contract manufacturing is a maker (theme_check.chip_idm), chips made using specialty process technologies are a foundry's, a seller of its own goods given platform is a retailer, a company of another business filed under the theme's industry (solar under semiconductors) stays in "Other" (theme_check.off_industry), a company leaving a map layer for its family goes to the family's layer of its own industry (by_model); q1: a network operator given software or capacity is telecom_services (theme_check.telecom_operator), a rule-made model of another family not held at the answer's "low" (said_for), foundry words read in a 10-K/20-F as contract making; lane n2: a kept model of low confidence read again from the evidence as it is now (refine_kept), foundry words as contract making, family words (theme_check.model_confidence), retail vs platform (refine_model); R34: the model rules that changed after R33 (a chip materials supplier is an ingredient maker; a model-named layer joins a map layer only when one layer has its model) apply to every kept check, placement and dive: whenever refine_model, by_model or a model rule changes, bump this; R33: a company with no model takes the one its map layer's name states (models_from_layer); R32: chip designers without fabs as fabless (theme_check.chip_designer), a layer named by how it earns joins the map's layer of its primary model, a market-value half with no shown company undone (unsplit_unshown); R31: lenders apart from developers and landlords, fabless vs IDM by owned fabs (theme_check.refine_model), a metals family's commodity as its sub-basis, a split-made layer of one primary model joins the map's (by_model 3b); R30: a kept placement's unknown models asked again once the companies' descriptions are kept (reask_unknown); R29: kinds of utility and of metals business as their own models (theme_check.refine_model); R21: every confirmed company in one of the map's layers (place_rest); R22: layer names fit, currencies, extra layers; R25: one revenue model a layer; R26: models from more evidence and checked by it, names after the split; R27: primary model, tags and confidence, comparable segments, no one-company layer; R28: the companies to place carry their own descriptions (theme_routes.describe_unplaced)
INDUSTRIES_DAYS = 30            # the AI's pick of a free-text theme's industries is made again after this long (at most monthly)
PICK_RULES = 45                 # cv47 (R46): the rules version the AI's industry pick (PICK_SYSTEM, ai_pick) last changed under: a pick kept under it or later rules is kept; bump to RULES only when the pick itself changes
FIGURES_MAX = 100               # companies the dive works figures out for: every one the AI named, then the largest of the base (R31: 60 -> 100; stored reads only, the deck built in under a second for 100 synthetic companies, the sector-figure worker bounded by its queue)
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
    # c1 (R44): names a layer of one official industry shows (theme_base.from_other)
    "cables - electricals": "Electrical cables", "ferro & silica manganese": "Ferro alloys",
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


def industry_label(name) -> str:
    """An official industry as the name of a layer of its companies (d1): its plain name without the SEC's "Retail-" kind of prefix, in
    sentence case ("Retail-Family Clothing Stores" -> "Family clothing stores")."""
    t = re.sub(r"^[A-Za-z]+-\s*(?=[A-Z])", "", plain_industry(name)).replace(" & ", " and ")
    return (t[:1].upper() + t[1:].lower()) if t else t


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


def industries_for(region: str, theme: str, rows: list[dict], ask, get_setting, set_setting, now=None, held=None) -> dict:
    """{"industries", "how", "named", "except"}: the official industries at the theme's core. "how":
    - "list": the curated table (with its named members and exclusions);
    - "ai": the AI's pick from the market's official list, kept INDUSTRIES_DAYS;
    - "words": the industries whose names share a word with the theme, when the AI picks none or can't answer now (THEMES, 4 Nov: a
      typed theme never rests on the AI alone), or the theme is an industry's own name;
    - "pending": the AI couldn't answer and no industry shares a word (asked again on the next request); "none": no index yet.
    A theme that is an official industry's own name always has that industry. `ask(system, text)` is the AI's JSON answer.
    cl48 (R47, the live Release 46 Consumer retail deck: the pick asked again swapped "Family Clothing Stores", whose eight chains were all in
    an informative layer, for "Retail Stores, Nec"): when the pick is made again, an industry of the pick it replaces that the new one
    leaves out stays in it when `held(industries)` names it (theme_routes.held_industries: most of its companies were in an informative
    layer of the theme's previous live placement), so a new pick never drops companies the evidence had placed."""
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
    # cv47 (R46, the live Release 46 Consumer retail deck: the bump to RULES 45 asked the pick again and the AI swapped "Family Clothing
    # Stores", whose chains all sat in a layer, for "Retail Stores, Nec", whose companies fit none): a pick kept under PICK_RULES or later
    # rules is kept (INDUSTRIES_DAYS), so a change of the placement rules never redraws a theme's universe; one kept under older rules is
    # made again
    rules = hit.get("rules") if isinstance(hit, dict) else None
    if isinstance(hit, dict) and hit.get("at") and isinstance(rules, int) and PICK_RULES <= rules <= RULES:
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
    kept_ = []
    was = [known[key(i)] for i in (hit.get("industries") or [] if isinstance(hit, dict) else []) if key(i) in known]
    dropped = [i for i in was if key(i) not in {key(x) for x in picked}]
    if picked and dropped and held is not None:
        try:
            kept_ = [i for i in held(dropped) or [] if i in dropped]
        except Exception as e:                  # the previous placement can't be read now: the new pick as it is
            print("theme base: industries of the previous pick not checked:", theme[:40], type(e).__name__, str(e)[:100])
        picked = picked + kept_
    try:
        set_setting(skey, json.dumps({"at": now.isoformat(timespec="seconds"), "industries": picked, "rules": RULES,
                                      **({"held": kept_} if kept_ else {})}, ensure_ascii=False))
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


def sub_theme_only(m: dict) -> list[dict]:
    """The companies the map names in a sub-theme only, in no layer of its value chain, each once (d1: the live Release 41 decks listed SAIL,
    GAIL, MercadoLibre, O'Reilly and Etsy in no layer and not in "Other" either)."""
    in_vc = {c.get("ticker") for v in m.get("value_chain") or [] for c in v.get("companies") or []}
    out: dict = {}
    for sub in m.get("sub_themes") or []:
        for c in sub.get("companies") or []:
            if c.get("ticker") and c["ticker"] not in in_vc:
                out.setdefault(c["ticker"], c)
    return list(out.values())


def with_sub_only(m: dict, theme: str) -> dict:
    """The map with each company it names in a sub-theme only (sub_theme_only) in its "Other" group (made when it has none), so every company
    of the theme is in a layer or in "Other", never in neither (d1). A map whose own layers place them (place_rest) has none left."""
    only = sub_theme_only(m)
    if not only:
        return m
    vc = [dict(v, companies=list(v.get("companies") or [])) for v in m.get("value_chain") or []]
    rest = next((v for v in vc if v.get("official") and v.get("basis") == "rest"), None)
    if rest is None:
        rest = {"layer": other_label(theme or m.get("sector") or ""), "description": "", "official": True, "basis": "rest", "companies": [],
                "sub_only": True}
        vc.append(rest)
    rest["companies"] = sorted(rest["companies"] + [{**c, "sub_only": True} for c in only], key=lambda c: (-(c.get("cap") or 0), c.get("ticker") or ""))
    return {**m, "value_chain": vc}


def place_rest(m: dict, theme: str, about_of, ask=None, kept: dict | None = None, facts_of=None, carried: bool = False,
               previous: dict | None = None) -> tuple[dict, dict]:
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
    "business") and the sentences of its description that speak of how it earns.
    R41 (lane s2-exact, the live Release 38.1 Pharma deck: Hikal and Brooks left the contract research layer the answer placed them in when
    the bump to RULES 40 asked their unknown models again): `carried`, a kept answer kept under an earlier rules version (theme_routes.placed),
    sticks: no unknown model is asked again (reask_unknown), a names check asked again changes no model or layer name the answer holds (it
    only adds those it lacks), and a layer the split renamed keeps the answer's name when the split reshapes it again (only a reshaped layer
    the answer never named is asked). Whatever the version, a model asked apart from the placement (R30, kept in "reasked") never moves the
    company out of the map layer the placement put it in (by_model `settled`).
    R45 (lane tx2, the outside review of the live Release 45 Automotive deck: Bosch and Asahi India Glass left the component suppliers'
    layer they were in on the live Release 43): `previous`, {symbol: its layer in the previous live placement as shown} (theme_changes'
    snapshot, theme_routes.placed): a company the split would move out of the layer it was in there moves only on evidence of the new
    layer (by_model `previous`), and an unchecked map pick keeps it without evidence of the layer it is in (held_to_previous)."""
    from .theme_check import (MODEL_MEMBERS, earning_lines, model_confidence, model_evidence, model_supported, model_tags, refine_model,
                              names_for_models, recheck_models, stated_model)
    vc = list(m.get("value_chain") or [])
    own = [v for v in vc if not v.get("official") and v.get("layer")]
    rest = [v for v in vc if v.get("official") and v.get("basis") in ("industry", "list") and not v.get("by_industry")]
    todo = [c for v in rest for c in v.get("companies") or []]
    kept = kept if isinstance(kept, dict) and "assign" in kept else {}
    if not own:
        return m, kept
    # d1 (the live Release 41 decks: SAIL, GAIL, MercadoLibre, O'Reilly and Etsy, named by the AI in a sub-theme only, were in no layer and not
    # in "Other"): a company the map names in a sub-theme only is placed like one of the theme's industries: in the map layer the answer or
    # its own words give it, else in "Other"
    todo += sub_theme_only(m)
    names = {v["layer"] for v in own}
    got = {s: x for s, x in (kept.get("assign") or {}).items() if isinstance(x, dict) and (x.get("layer") in names or x.get("layer") == "")}
    rename, extra = dict(kept.get("rename") or {}), list(kept.get("extra") or [])
    need = [c for c in sorted(todo, key=lambda c: -(c.get("cap") or 0)) if c["ticker"] not in got]
    asked, placed_models, placed_tags, placed_conf = False, None, {}, {}
    by_sym = {c.get("ticker"): c for v in vc for c in v.get("companies") or [] if c.get("ticker")}
    by_sym.update({c["ticker"]: c for c in todo if c.get("ticker") and c["ticker"] not in by_sym})
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
        for s_ in dict.fromkeys(syms if ans.get("models") else ()):     # R30: an answer that gave no models is left as it came
            if s_ and s_ not in keep:
                ev = evidence(s_)
                md = stated_model(ev)             # R37: each family's words, making and trading words too
                if md and model_supported(md, ev):
                    keep[s_], conf[s_] = md, "medium"
        # R29: a broad model (utility, resources, a maker in a metals industry) made exact where the evidence shows one kind only, so
        # regulated networks, generators and traders, or miners and fabricators, are never one layer
        for s_, md in list(keep.items()):
            keep[s_] = refine_model(md, evidence(s_))
            if keep[s_] != md:
                conf[s_] = model_confidence(keep[s_], evidence(s_), said_for(keep[s_], md, conf.get(s_, "")))
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
        # d1: one placed in no layer with no words of its own (no description kept, no line from the map), by the AI's answer on its name or
        # by its words: not checked yet, never "fits none of the layers"
        unread = not x.get("layer") and not (about_of(c["ticker"]) or c.get("what"))
        tag = {**c, "placed": x.get("by") or "words", "verified": c.get("verified", False) if c.get("sub_only") or not c.get("base", True) else False,
               **({"fit": True} if x.get("layer") else {}), **({"unread": True} if unread else {})}
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
            new_rename, names_for = {k: x for k, x in ans["rename"].items() if k in names}, sig
            new_models, new_tags, new_conf = checked_models(ans, [c.get("ticker") for v in sent for c in v["companies"]])
            if carried and models:         # R41: the carried answer's models and names stick; the check only adds what it lacks
                rename = {**new_rename, **{k: x for k, x in rename.items() if k in names}}
                tags = {**new_tags, **{s_: t for s_, t in tags.items() if s_ in models}}
                conf = {**(new_conf or {}), **(conf or {})}
                models = {**new_models, **models}
            else:
                rename, models, tags, conf = new_rename, new_models, new_tags, new_conf
        except Exception as e:
            print("theme base: layer names not checked:", theme[:40], type(e).__name__, str(e)[:100])
    reasked = list(kept.get("reasked") or []) if isinstance(kept.get("reasked"), list) else []
    # a kept placement whose models were read (an answer that gave none is not asked again for them)
    if models and ask is not None and not asked and not carried and isinstance(kept.get("models"), dict) and kept["models"]:
        models, tags, conf, reasked = reask_unknown(models, tags, conf, reasked, [c.get("ticker") for c in todo] + [c.get("ticker") for v in own for c in v.get("companies") or []],
                                                    about_of, by_sym, evidence, ask, theme)
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
        # R32: a company whose own stored words say nothing of how it earns takes the model its map layer's name states (live R31 semis:
        # Qualcomm, Broadcom, AMD... with only "From its own filings: Quarterly report" as evidence sat unknown in "Fabless chip design")
        models, conf = models_from_layer(out_vc, models, conf, evidence)
    settled = set()
    if models:
        # R31: a kept placement's models made exact by the R31 boundaries (lenders, landlords and developers; fabless and fab owners) from the
        # companies' evidence, with nothing asked again
        had = {s_ for s_, m_ in models.items() if m_ not in ("", "unknown")}
        models, conf = refine_kept(models, conf, evidence, [c.get("ticker") for v in out_vc for c in v.get("companies") or []])
        settled = {s_ for s_, m_ in models.items() if m_ not in ("", "unknown") and s_ not in had           # R37: models only their words state
                   and refine_model("unknown", evidence(s_)) in ("", "unknown")}
        # R41: a model asked apart from the placement (reask_unknown) moves no company out of the map layer the map itself or the AI's
        # placement answer put it in; one placed by its words alone, or in a layer the answer proposed for the companies that fit none of
        # the map's, moves as before
        settled |= {s_ for s_ in reasked if s_ not in got or (got[s_].get("by") == "ai" and got[s_].get("layer"))}
    if previous:
        out_vc = held_to_previous(out_vc, map_names_of(previous, kept), about_of)
    if models:
        before = {v["layer"]: {c.get("ticker") for c in v["companies"]} for v in out_vc if not v.get("official")}
        out_vc = by_model(out_vc, models, theme, tags=tags, confidence=conf, evidence_of=evidence, settled=settled,
                          previous=map_names_of(previous, kept))
        # R26: a layer of the map the split reshaped (companies moved in or out) whose name no longer fits how its companies earn is renamed by
        # the same check as the placement's; asked once a map and its split, kept with the rest
        reshaped = [v for v in out_vc if v["layer"] in before and not v.get("official") and not v.get("scale") and (v.get("model") or {}).get("line")
                    and not v["model"].get("sparse") and {c.get("ticker") for c in v["companies"]} != before[v["layer"]]]
        msig = model_names_signature(reshaped)
        model_names = kept.get("model_names") if isinstance(kept.get("model_names"), dict) and kept["model_names"].get("sig") == msig else None
        held_names = {}
        if model_names is None and carried and isinstance(kept.get("model_names"), dict):
            # R41: a carried answer's names for the layers the split renamed stick when the split reshapes them again
            held_names = {k: x for k, x in (kept["model_names"].get("rename") or {}).items() if k in {v["layer"] for v in reshaped}}
            if held_names and (ask is None or all(v["layer"] in held_names for v in reshaped)):
                model_names = {"sig": msig, "rename": held_names}
        if model_names is None and ask is not None and reshaped:
            try:
                ask_for = [v for v in reshaped if v["layer"] not in held_names]
                model_names = {"sig": msig, "rename": {**names_for_models(ask_for, ask, theme), **held_names}}
            except Exception as e:
                print("theme base: layer names after the split not checked:", theme[:40], type(e).__name__, str(e)[:100])
        if model_names and model_names.get("rename"):
            out_vc = renamed_after_split(out_vc, {v["layer"] for v in reshaped}, model_names["rename"])
    out_vc, off = without_off_industry(out_vc, {c.get("ticker") for c in todo}, evidence)
    placements = m.get("placements")
    out_vc, sure = confirmed_by_words(out_vc, about_of, theme)
    if sure and placements is not None:
        placements = {**placements, "confirmed": (placements.get("confirmed") or 0) + sure,
                      "unconfirmed": max(0, (placements.get("unconfirmed") or 0) - sure)}
    if off:
        placements = {**(placements or {}), "off_industry": off}
        for k_ in ("placed", "total", "base"):
            if isinstance(placements.get(k_), int):
                placements[k_] = max(0, placements[k_] - len(off))
    return {**m, "value_chain": out_vc, **({"placements": placements} if placements is not None else {})}, {"assign": got, "rename": rename, "extra": extra, **({"names_for": names_for} if names_for else {}),
                                          **({"models": models} if models is not None else {}), **({"model_names": model_names} if model_names else {}),
                                          **({"model_tags": tags} if models is not None and tags else {}),
                                          **({"model_confidence": conf} if models is not None and conf is not None else {}),
                                          **({"reasked": reasked} if reasked else {})}


def confirmed_by_words(vc: list[dict], about_of, theme: str) -> tuple[list[dict], int]:
    """(the layers, how many companies they confirm) (c1, R44: the live Release 43 Insurance deck listed PB Fintech, the map's own pick for
    "Distribution and aggregation", as "not confirmed", its words said to "describe other work", because the check of its words timed out):
    a company the AI added from another industry into one of the map's own layers (never one placed after the map) whose own words say what
    that layer's name says ("distributing and servicing financial products" says "Distribution") is in the theme by its own words: confirmed
    ("verified", "verified_by": "words"), whatever check did not answer. Which comparisons it is in is decided apart (by_model, calc_record):
    a distributor in its own layer is never among the underwriters."""
    tw = kind_stems(theme)
    n, out = 0, []
    for v in vc:
        if v.get("official") or v.get("by_model") or v.get("industry_group"):
            out.append(v)
            continue
        cos = []
        for c in v.get("companies") or []:
            if not c.get("base", True) and not c.get("verified") and not c.get("placed") and not c.get("moved"):
                words = own_text(about_of(c.get("ticker")) or c.get("what") or "")
                name = v.get("was") or v.get("layer") or ""
                head = next((_stem(w) for w in re.findall(r"[a-z]+", name.lower()) if len(w) >= 4 and w not in _PLAIN), "")
                # its words say a word of what the name says is done (name_says), or the name's head word ("Distribution", a way of earning
                # name_says leaves to the models)
                if words and not no_words(words) and (name_says(name, words, tw)[1] or (head and head in _stems(words))):
                    c = {**c, "verified": True, "verified_by": "words"}
                    n += 1
            cos.append(c)
        out.append({**v, "companies": cos})
    return out, n


def without_off_industry(vc: list[dict], todo: set, evidence) -> tuple[list[dict], list[dict]]:
    """(the layers without the companies of another business, those companies) (R40, the owner's review of the live Release 39 decks: solar
    makers in "Other semiconductor companies", propane distributors in "Other consumer retail companies"): a company the theme's official
    industry brought in (`todo`: placed after the map, never one the map named) whose own words describe another business than the one
    that industry files it under (theme_check.off_industry) is no member of the theme: dropped from every layer and from "Other", and named
    once, with the industry it is filed under ({"ticker", "name", "industry"}), so the theme's coverage says who was left out and why. A
    group left with no company is dropped."""
    from .theme_check import off_industry
    off, seen = [], set()
    for v in vc:
        for c in v.get("companies") or []:
            s_ = c.get("ticker")
            if s_ in todo and s_ not in seen and off_industry(evidence(s_)):
                seen.add(s_)
                off.append({"ticker": s_, "name": c.get("name") or s_, "industry": c.get("industry") or "",
                            # c1 (R44, reviewer ask 3): the reason it is out of the theme, kept beside it
                            "why": f"filed under {industry_label(c.get('industry')) or 'the theme’s industry'}, its own words describe another business"})
    if not off:
        return vc, []
    out = [{**v, "companies": [c for c in v.get("companies") or [] if c.get("ticker") not in seen]} for v in vc]
    return [v for v in out if v["companies"] or not v.get("official")], off


REASK_MAX = 40                   # R30: companies of a kept placement whose unknown model is asked again, one answer (the largest first as listed)


def reask_unknown(models: dict, tags: dict, conf, reasked: list, syms: list, about_of, by_sym: dict, evidence, ask, theme: str):
    """R30 (the owner's review of the live R28 Telecom deck: three tower companies left out of "Tower infrastructure" with unknown models): a
    placement kept from before R28 holds "unknown" for companies whose own descriptions are kept now. Those with a description and no model,
    not asked before (`reasked`), are asked once in one answer of at most REASK_MAX (theme_check.recheck_models: a model is kept only when the
    evidence shows it), and every symbol asked is kept in `reasked`, so none is asked twice. Background only (`ask` given). (models, tags,
    confidence, reasked)."""
    from .theme_check import model_confidence, recheck_models, refine_model
    done = set(reasked)
    want = []
    for s_ in dict.fromkeys(x for x in syms if x):
        if s_ in done or (models.get(s_) or "unknown") != "unknown" or not (about_of(s_) or "").strip():
            continue
        want.append(s_)
        if len(want) >= REASK_MAX:
            break
    if not want:
        return models, tags, conf, reasked
    try:
        got = recheck_models([{"symbol": s_, "name": (by_sym.get(s_) or {}).get("name") or s_, "was": "unknown", "evidence": evidence(s_)} for s_ in want],
                             ask, theme)
    except Exception as e:                   # the AI busy: asked on a later check
        print("theme base: unknown models not asked again:", theme[:40], type(e).__name__, str(e)[:100])
        return models, tags, conf, reasked
    models, conf = dict(models), dict(conf or {})
    for s_, md in got.items():
        models[s_] = refine_model(md, evidence(s_))
        conf[s_] = model_confidence(models[s_], evidence(s_), "medium")
    return models, tags, conf, sorted(done | set(want))


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
STORE_SAYS = r"\bstores?\b|\bretailer\b|\bshops?\b|\boutlets?\b"      # d1: a retailer's own words, for one with no model read
INDUSTRY_GROUP_MIN = 5          # d1: companies of one official industry that no map layer's name describes, grouped as a layer of that industry
SPLIT_MIN = 8                   # ...when it has at least this many, by revenue model, else by market value
SPLIT_PART = 3                  # each part of such a split holds at least this many companies


R31_REFINE = ("property_development", "property", "construction", "manufacturing", "fabless", "unknown", "retail",      # models the R31 boundaries can make exact
              "software", "capacity",         # q1: a network operator given software or capacity is telecom_services
              "contract_manufacturing", "platform",     # R36: a chip maker with products of its own is no contract maker; a seller of its own goods is a retailer
              "components",                             # R37: a chip company's packaging and test services are contract making
              "telecom_services")                       # d1: a maker of cables read as an operator makes its own products


def said_for(new, old_model, said) -> str:
    """The confidence an answer gave a company's model, as it counts for the model a rule made of it (q1): the answer's word on a model of
    another family (a telecom operator it called software, at "low") says nothing of the new one, so the rule's model reads its own evidence,
    at most "medium"; else the answer's word as given."""
    from .theme_check import model_family
    if new != old_model and model_family(new) != model_family(old_model) and said == "low":
        return "medium"
    return said


LAYER_MODEL_NOT = (r"\bmaterials?\b|chemicals?|\bgases\b|\bwafers? (?:supplier|maker)|substrates?|"
                   r"(?:semiconductor|wafer fab\w*|capital|process) equipment|electronic design automation|\beda\b")


def models_from_layer(vc: list[dict], models: dict, conf, evidence=None) -> tuple[dict, dict | None]:
    """(models, confidence) with each company of a map layer (not an official group, not "Other") that has no known model given the one
    model its layer's own name states in so many words (theme_check.model_from_words on the name), at "medium" confidence: the map placed it
    there and its own words don't contradict it. Unchanged when the name states no single model (R32). R34: never when the company's own
    evidence states another model, or names materials, chemicals, gases, substrates, equipment or design software (live: a materials maker
    in a fabless layer)."""
    import re
    from .theme_check import MODELS, model_from_words
    given = evidence
    ev_of = given if callable(given) else (lambda s_: (given if isinstance(given, dict) else {}).get(s_))   # the caller passes a reader
    models, out_conf = dict(models), (dict(conf) if isinstance(conf, dict) else {})
    for v in vc:
        if v.get("official") or v.get("by_model"):
            continue
        m_ = model_from_words(str(v.get("layer") or ""))
        if not m_ or m_ not in MODELS:
            continue
        for c in v.get("companies") or []:
            s_ = c.get("ticker")
            if s_ and models.get(s_, "") in ("", "unknown"):
                ev = str(ev_of(s_) or "")
                if model_from_words(ev) not in ("", m_) or re.search(LAYER_MODEL_NOT, ev, re.I):
                    continue
                models[s_] = m_
                out_conf[s_] = "medium"
    return models, (out_conf or conf)


def refine_kept(models: dict, conf, evidence, syms=()) -> tuple[dict, dict | None]:
    """(models, confidence) with the R31/R32 boundaries applied to the models in R31_REFINE (theme_check.refine_model); a company whose model
    changes, or a fabless one of low confidence, has its confidence read again from its evidence, never below what it was (R32: a kept
    placement left 29 of the 37 chip designers out with low confidence). R36: `syms`, the map's companies: one the answer gave no model at
    all is read as "unknown" is (live: Entegris, a chip materials supplier with no model, could sit in whatever layer it was placed in).
    Lane n2 (the outside review of the live R33 decks: TSMC and UMC left out of the foundry layer as "way of earning not shown"): every kept
    model of low confidence has its confidence read again from the evidence as it is now (a 20-F's Item 4 read since): "medium" at most
    when the company's own words show the model, never below what it was."""
    from .theme_check import model_confidence, model_supported, own_words_show, refine_model, stated_model
    models, out_conf = dict(models), (dict(conf) if isinstance(conf, dict) else None)
    absent = [(s_, "unknown") for s_ in dict.fromkeys(x for x in syms if x and x not in models)]
    for s_, md in list(models.items()) + absent:
        new = refine_model(md, evidence(s_)) if md in R31_REFINE else md
        old = (out_conf or {}).get(s_, "")
        stated = False
        if new in ("unknown", ""):
            # R37 (lane r2: 255 of the 1,334 companies of the 14 live maps with no model, most with no words read): one whose own words, read
            # since, state how it earns in so many words takes that model, at "medium" as one the answer didn't give (theme_check.stated_model)
            st = stated_model(evidence(s_))
            exact = refine_model(st, evidence(s_)) if st and model_supported(st, evidence(s_)) else ""
            if exact and (exact == st or model_confidence(exact, evidence(s_), "medium") != "low"):   # made exact into one its words don't show: unknown
                new, old, stated = exact, "medium", True
        if new != md or old == "low":
            models[s_] = new
            if new and new != "unknown":
                out_conf = out_conf if out_conf is not None else {}
                out_conf[s_] = model_confidence(new, evidence(s_), said_for(new, md, old))
                if old == "low" and new == md and own_words_show(new, evidence(s_)):
                    # lane n2: a kept "low" (the AI's word on thinner evidence) gives way to "medium" when the company's own words read since
                    # show the model, never above (the AI's word still caps it: R32)
                    out_conf[s_] = model_confidence(new, evidence(s_), "medium")
                if stated:
                    out_conf[s_] = "medium"          # stated in so many words, never read by the AI: "medium" (R27)
    return models, out_conf


# R37: words of how a company earns, never of what it does: they place no company in a layer (by_model.home_of)
_HOW_STEMS = {_stem(w) for w in ("manufacture", "manufacturer", "manufacturing", "make", "makes", "maker", "makers", "produce", "producer", "production",
              "sell", "sells", "selling", "sold", "sale", "sales", "supply", "supplier", "suppliers", "supplies", "distribution", "distributor",
              "service", "provide", "provider", "earning", "earn", "margin", "revenue", "market", "markets", "marketing", "trade", "trader", "trading",
              "company", "business", "chain", "chains", "store", "stores", "retail", "retailer", "retailers", "shop", "brand", "brands", "customer",
              "customers", "consumer", "consumers", "goods", "items", "range", "leading", "leader", "largest", "large", "small", "global", "group",
              "these", "their", "they", "which", "such", "mainly", "often", "including", "across", "through", "operates", "operator", "engaged",
              "offers", "offering", "focused", "specialty", "specialised", "specialized", "price", "prices", "cost", "costs", "scale", "exposure",
              "depends", "sets", "apart", "them", "from", "have", "with", "that", "this", "other", "unit", "units", "india", "states", "united",
              "headquartered", "incorporated", "limited", "corporation", "holdings", "american", "national", "international")}
STAY = object()
_HALF_RX = re.compile(r" \((?:larger|smaller)\)$")
_KIND_PLAIN = (_PLAIN - {"equipment", "equipments"}) | {"product", "solutions", "systems", "various", "wide"}


def kind_stems(text) -> set[str]:
    """The stems of what a company or a layer's name says is made, sold or done: its words, less those of how any company earns
    (_HOW_STEMS) and the plain words of industry names ("equipment" kept: what a network equipment maker makes)."""
    return {_stem(w) for w in re.findall(r"[a-z0-9]+", str(text or "").lower()) if len(w) >= 3 and w not in _KIND_PLAIN} - _HOW_STEMS


def _short_joined(text) -> str:
    """cl48 (R47): the text in lower case with a compound whose first part is a short word ("off-price", "e-commerce") written as one word,
    as name_says reads it, so "off" of "off-price" is never said by "branched off"."""
    return re.sub(r"\b([a-z0-9]{1,3})-([a-z0-9]+)\b", r"\1\2", str(text or "").lower())


def whole_stems(text) -> set[str]:
    """cl48 (R47): kind_stems with a compound whose first part is a short word read as one word (_short_joined)."""
    return kind_stems(_short_joined(text))


def name_says(name: str, text: str, theme_words: set) -> tuple[bool, bool]:
    """(whether a layer's name states a kind of business beyond the theme's own words, whether a company's own words say it) (d1): a
    hyphenated word of the name is one word ("off-price", never "off" by chance), the others by their stems (kind_stems)."""
    low = str(name or "").lower()
    # a compound whose first part is a short word ("off-price", "e-commerce") is one word; any other compound ("deposit-led") its parts
    joined = [w for w in re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)+", low) if len(w.split("-")[0]) <= 3]
    for w in joined:
        low = low.replace(w, " ")
    rest = kind_stems(low.replace("-", " ")) - theme_words
    if not joined and not rest:
        return False, False
    t = str(text or "").lower()
    mine = kind_stems(t)
    # a stem of five letters or more says the longer word it starts ("steel" says "steelmaking")
    near = lambda a, b: a == b or (min(len(a), len(b)) >= 5 and (a.startswith(b) or b.startswith(a)))      # noqa: E731
    said = any(re.search(r"\b" + r"[- ]?".join(map(re.escape, w.split("-"))) + r"\b", t) for w in joined) or any(near(a, b) for a in mine for b in rest)
    return True, said


FILING_TITLES = "From its own filings:"


def own_text(evidence) -> str:
    """A company's own words in its evidence, its official industry line left out. cv47 (R46, the live Release 46 Utilities deck: the cable
    and electrical equipment makers' layers never formed on live): the titles of its filings ("From its own filings: Board meeting...",
    theme_routes.own_filings) are no words of its own about its work (no_words), so they are left out too: their "own" said the name
    "Makers of their own products", and "Order or contract" would say "contracts"."""
    t = str(evidence or "")
    m = re.match(r"\s*Industry:\s*[^.]*\.\s*", t)
    t = t[m.end():] if m else t
    i = t.find(FILING_TITLES)
    return t[:i].rstrip() if i >= 0 else t


def layer_says(v: dict, text: str, theme_words: set) -> tuple[bool, bool]:
    """cl48 (R47): name_says over a layer's names, the map's own ("was") and the one shown (a half's "(larger)" left out): (whether either
    states a kind of business beyond the theme's words, whether the company's own words say what either says)."""
    got = [name_says(n, text, theme_words) for n in dict.fromkeys(x for x in (v.get("was"), _HALF_RX.sub("", v.get("layer") or "")) if x)]
    return any(g[0] for g in got), any(g[1] for g in got)


def _model_layer(name: str, cos: list[dict], **kw) -> dict:
    return {"layer": name, "description": "", "by_model": True, "companies": cos, **kw}


# R40: families whose companies one layer of a single official industry counts together (making its own products, or parts and components)
KIN_FAMILIES = (frozenset({"making", "components"}),)


def held_to_previous(vc: list[dict], previous: dict, about_of) -> list[dict]:
    """R45 (lane tx2; the live Release 45 Automotive deck, built while the map's picks were being checked again under the new rules: a
    tractor maker the check had moved out of "Commercial and three-wheeler vehicle makers" on the live Release 43 was back in it, unchecked):
    a company in a layer of the map that is not checked yet (the map's own pick, its words not yet checked for that layer) whose previous
    live layer (`previous`: {symbol: the map's name of that layer}, map_names_of) is another layer of the map keeps that previous layer,
    unless it has evidence of the one it is in: its own words say what that layer's name says, or that layer holds a larger share of its
    official industry. A company checked since ("verified") or placed after the map is never held."""
    own = [v for v in vc if not v.get("official") and v.get("layer")]
    name = lambda v: v.get("was") or _HALF_RX.sub("", v.get("layer") or "")      # noqa: E731
    by_name = {}
    for v in own:
        by_name.setdefault(name(v), v)
    inds = {id(v): [key(c.get("industry")) for c in v.get("companies") or [] if c.get("industry")] for v in own}
    share = lambda v, ind: inds[id(v)].count(ind) / max(1, len(v.get("companies") or []))      # noqa: E731
    moves = []
    for v in own:
        for c in v.get("companies") or []:
            s_ = c.get("ticker")
            to = by_name.get(previous.get(s_) or "")
            if to is None or to is v or name(to) == name(v) or c.get("verified") is not False or c.get("placed"):
                continue
            ind = key(c.get("industry")) if c.get("industry") else ""
            words = own_text(about_of(s_) or c.get("what") or "")
            if name_says(name(v), words, set())[1] or (ind and share(v, ind) > share(to, ind)):
                continue
            moves.append((v, c, to))
    if not moves:
        return vc
    copies = {id(v): {**v, "companies": list(v.get("companies") or [])} for v in own}
    for v, c, to in moves:
        copies[id(v)]["companies"] = [x for x in copies[id(v)]["companies"] if x is not c]
        copies[id(to)]["companies"].append({**c, "held": "previous"})
    return [copies.get(id(v), v) for v in vc]


def map_names_of(previous: dict | None, kept: dict | None) -> dict:
    """R45 (lane tx2): {symbol: the map's own name of its previous live layer}: a shown name the kept answer gave a map layer (its "rename",
    or the split's "model_names") read back as that layer's own name, a half of a layer split by market value as the layer."""
    if not previous:
        return {}
    back: dict = {}
    for ren in ((kept or {}).get("rename"), ((kept or {}).get("model_names") or {}).get("rename")):
        for k, x in (ren or {}).items() if isinstance(ren, dict) else ():
            if isinstance(x, dict) and x.get("name"):
                back.setdefault(str(x["name"]), str(k))
    return {s_: back.get(_HALF_RX.sub("", str(n)), _HALF_RX.sub("", str(n))) for s_, n in previous.items() if s_ and n}


def by_model(vc: list[dict], models: dict, theme: str = "", tags: dict | None = None, confidence: dict | None = None,
             evidence_of=None, settled=(), previous: dict | None = None) -> list[dict]:
    """The placed map's layers with one revenue model family each, from `models` ({symbol: model id}, theme_check.MODELS):
    1. a layer of the map whose companies earn in different ways keeps its main family (the most of its companies; a tie, the family of the first
       of them, the map's own pick); each other company moves to the layer whose main family is its own (the largest), else to a new layer named
       by that model ("Hardware resale and integration"). A company of the "Other" group whose model is known goes the same way, so "Other" keeps
       only companies the evidence can't place. A company with no known model stays where it is; so does one whose model is of "low"
       confidence (R27, `confidence`: {symbol: high/medium/low}), which counts as unknown.
    2. a layer above SPLIT_SHARE of the placed companies (and SPLIT_MIN or more) is split by its models when two or more hold SPLIT_PART
       companies each, else into its larger and smaller halves by market value.
    3. (R27) a split never leaves a layer of one company: a layer the split made or reshaped that holds one company gives it to the largest layer
       of its family, else to the theme's "Other" group, and is not a layer of its own. R39: the company of a layer the split made joins only
       a layer of its family whose words it shares (`fits`), else "Other".
    3b. (R31) one primary model a layer: a layer the split made whose primary model, family and sub-basis (theme_check.sub_basis: a metals
       family's commodity) are those of one of the map's own layers joins it. R32: so does any layer named by how it earns (a model's or a
       family's own name, "Product designers that outsource making"), and two such layers become one; it joins the largest layer of the same
       key named by what it makes or serves when there is one such layer (R36: with two or more, which of them a company belongs to isn't
       shown by how it earns, so the model-named layers become one layer of their own), else the largest of them. R39 (lane s1-fit: the live
       R37 Semiconductors deck had Micron, Intel and SK Hynix, lasers and LED makers in "Semiconductor equipment"): a model-named layer joins a
       layer named by what it makes or serves only with the companies the split moved there whose own words share two of the words that
       layer's name and description say is made or done (`fits`; the theme's own name left out); companies the map placed together keep
       joining as before; the others keep their layer (one left alone goes to "Other").
       Two of the map's own layers named by what they make or serve that share
       them both stay (two-wheelers and cars both make their own products), and each one's line says so (`same_as`).
    4. every layer of the map carries `model`: {"id", "family", "line", "known", "of", "out", "also"}, the one line the deck shows of what its
       companies have in common; R27: the companies whose model is unknown or of low confidence are listed but marked `model_out` (left out of
       the layer's figures and rankings; the line says how many and why), and the line names the commonest secondary way of earning of its
       companies ("3 of the 9 also earn from ..."; `tags`: {symbol: [model ids]}), so no company is shown as earning one way only.
    Every company carries "model", "model_tags" and "model_confidence" (R27, for the deck's checks). Facts only: the models are the companies'
    own evidence as the AI read it.
    R45 (lane tx2): `previous` ({symbol: the map's name of its layer in the previous live placement}, map_names_of): a company leaving the
    layer it was in there for another layer (a layer of the map or one the split names by how it earns) moves only on evidence of that layer
    (evidence_for: its own words say the layer's name, or the layer holds a larger share of its official industry); else it keeps its layer,
    listed but left out of the layer's figures as another way of earning. Moving to "Other" (no layer fits) is not held back."""
    from collections import Counter

    from .theme_check import (FAMILIES, MODELS, SUB_BASIS, SUB_JOIN, SUB_OF, model_evidence, model_family, name_models, off_industry, own_goods,
                              words_models,
                              stated_model, sub_basis)
    tags, conf = tags or {}, dict(confidence or {})          # d1: a copy (the industry group sets models its members state)
    every = {s: m_ for s, m_ in (models or {}).items() if m_ in MODELS}
    models = {s: m_ for s, m_ in every.items() if conf.get(s) != "low"}
    out = [dict(v, companies=list(v.get("companies") or [])) for v in vc]
    ev_memo: dict = {}

    def ev(c):
        s_ = c.get("ticker")
        if s_ not in ev_memo:
            got = ""
            if evidence_of is not None:
                try:
                    got = evidence_of(s_) or ""
                except Exception as e:          # the evidence store can't answer now: the company's own line and industry still count
                    print("theme base: evidence not read:", s_, type(e).__name__, str(e)[:100])
            ev_memo[s_] = got or model_evidence(c.get("industry") or "", c.get("what") or "")
        return ev_memo[s_]
    # R36 (GPT review of the live R35 Semiconductors deck: solar tracker and module makers, filed as semiconductors, among "Makers of their own
    # products"): a company whose own words show another business than the one its official industry files it under (theme_check.off_industry)
    # moves to no layer by how it earns: the "Other" group keeps it, and in a layer of the map it is left out of the figures as another business
    outside = {c.get("ticker") for v in out for c in v["companies"] if c.get("ticker") in models and off_industry(ev(c))}
    models = {s: m_ for s, m_ in models.items() if s not in outside}
    another, read = set(outside), dict(models)          # R40: the companies of another business, and every model as read (step 4)
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
            # R37 (lane r2): a company the map placed in a layer whose model only its own words state (`settled`: no answer gave it one) is never
            # moved by it: it stays in the map's layer, left out of its figures as a company of another way of earning
            held = {c.get("ticker") for c in v["companies"] if fam(c) not in ("", f) and c.get("ticker") in settled}
            outside |= held
            for s_ in held:
                models.pop(s_, None)
            movers += [{**c, "_from_layer": id(v)} for c in v["companies"] if fam(c) not in ("", f) and c.get("ticker") not in held]
            v["companies"] = [c for c in v["companies"] if fam(c) in ("", f) or c.get("ticker") in held]
    for v in out:
        if v.get("official") and v.get("basis") == "rest":
            movers += [{**c, "fit": True} for c in v["companies"] if fam(c)]
            v["companies"] = [c for c in v["companies"] if not fam(c)]
    home, homes = {}, {}
    for v in own:
        f = mains[id(v)]
        if f and (f not in home or len(v["companies"]) > len(home[f]["companies"])):
            home[f] = v
        if f:
            homes.setdefault(f, []).append(v)
    new: dict[str, dict] = {}

    inds = {id(v): Counter(key(x.get("industry")) for x in v["companies"] if x.get("industry")) for v in own}     # before any company moves
    sizes = {id(v): len(v["companies"]) for v in own}
    kinds = {id(v): sub_basis(mains[id(v)], [ev(x) for x in v["companies"] if fam(x) == mains[id(v)]]) for v in own
             if mains.get(id(v)) in SUB_JOIN}
    stays = []
    theme_words = kind_stems(theme)

    def fits(c, v) -> bool:
        """R39 (lane s1-fit): a company's own words share two of the words of what a layer's name and description say is made or done (the
        theme's own name left out: "Semiconductor" in "Semiconductor equipment" says nothing of which layer), never one by chance."""
        return len(kind_stems(own_text(ev(c))) & (kind_stems(f"{v.get('layer') or ''} {v.get('description') or ''}") - theme_words)) >= 2

    def evidence_for(c, t, src, ind) -> bool:
        """R45 (lane tx2): whether a company has evidence for layer `t` over the layer `src` it is in: its own words say what t's name says
        (name_says), or t holds a larger share of its official industry `ind` than src (both counted before any company moves)."""
        if name_says(t.get("was") or _HALF_RX.sub("", t.get("layer") or ""), own_text(ev(c)), theme_words)[1]:
            return True
        share = lambda v: inds.get(id(v), Counter())[ind] / max(1, sizes.get(id(v), 0))      # noqa: E731
        return bool(ind) and share(t) > share(src)

    def home_of(c, f):
        """The map's layer of its family a company moving by how it earns goes to: the largest of them. R36 (the live R35 Consumer retail
        deck: Amazon, leaving the marketplaces, would go to "Apparel and fashion retail chains"): for a company leaving a layer the map placed it
        in, not the largest when that holds no company of its own official industry and another is mostly of it.
        R37 (lane r2), for a company of the "Other" group only (the same deck: two propane distributors, two pawnbrokers and three online
        sellers moved out of "Other" into "Apparel and fashion retail chains"): the largest stands when it holds the company's official
        industry, or its name or description shares a word of what the company's own words say it does (none of how any company earns:
        makes, sells, supplies...), or the company has no words; else the layer whose every company is of its official industry and whose
        name or description shares such a word, unless the layer's name states another way of earning ("Custom synthesis manufacturers"); else,
        when no layer of its family holds its industry or shares its words, it stays in "Other" (the map has no layer of its business).
        R39 (lane s1-fit): a company with no words of its own joins the largest only when that layer holds its industry (or no industry is
        known), else stays in "Other" (also when leaving a map layer with no layer mostly of its industry). First, when the largest holds none of its industry and a layer of the map is all of its industry (and most of the
        map's companies of it), that layer, of whatever way of earning (left out of its figures); and where the largest neither holds its
        industry nor shares its words and no layer of its family holds its industry, never the largest: the layer of its family sharing
        two of its words (not one named for another way of earning), else "Other". Everything else as R37.
        A contract maker's kind (packaging and test, or a foundry: theme_check.contract_kind) joins only a contract layer of its kind, else
        a layer of its own (R37: foundries beside packaging and test services under "Packaging, test and materials suppliers")."""
        big = home.get(f)
        if big is None:
            return None
        cands = homes.get(f) or [big]
        if f in SUB_JOIN:
            kind = SUB_OF[SUB_BASIS[f]](ev(c))
            if kinds.get(id(big)) not in ("", kind):
                alike = [v for v in cands if kinds.get(id(v)) == kind]
                return max(alike, key=lambda v: sizes.get(id(v), 0)) if alike else None
        ind = key(c.get("industry")) if c.get("industry") else ""
        same = lambda v: inds.get(id(v), Counter())[ind] if ind else 0      # noqa: E731
        if c.get("_from_layer"):
            src = next((v for v in own if id(v) == c["_from_layer"]), None)
            mine = kind_stems(own_text(ev(c)))
            if not ind or same(big):
                return big
            mostly = [v for v in cands if same(v) * 2 > sizes.get(id(v), len(v["companies"]))]
            if mostly:
                t = max(mostly, key=lambda v: sizes.get(id(v), 0))
                # R45 (lane tx2, the outside review of the live Release 45 Automotive deck: Bosch and Asahi India Glass, in the component
                # suppliers' layer the map placed them in, went to "Batteries and tractor makers" once that layer, having lost a tractor
                # maker, was two of three of their industry): a company leaves a map layer mostly of its industry for another layer of
                # its industry only on evidence of that layer: its own words say what the layer's name says, or the layer holds a larger
                # share of its industry; else it stays, listed but left out of the layer's figures as another way of earning
                if src is not None and same(src) * 2 > sizes.get(id(src), 0) and not evidence_for(c, t, src, ind):
                    return src
                return t
            # R41 (lane s2-exact, the live Release 38.1 Automotive deck: Bosch and Asahi India Glass, in the component suppliers' layer the
            # map placed them in, read as makers of their own products, went to "Tyre manufacturers", the largest makers' layer, which holds
            # none of their industry): when no layer of its family is mostly of its industry and the map layer it is in is, it stays there,
            # listed but left out of the layer's figures as another way of earning; not when the largest's own name says what its words say
            if src is not None and same(src) * 2 > sizes.get(id(src), 0) and not mine & (kind_stems(big.get("layer") or "") - theme_words):
                return src
            # R39 (lane s1-fit): no words of its own and the largest holds none of its industry: nothing places it there ("Other")
            if not mine:
                return STAY
            # cl48 (R47, the outside review of the live Release 46 Consumer retail deck: a designer of branded athletic apparel the map
            # placed with the brand owners, read as a retailer, went to "Off-price and dollar stores", the largest of the retailers' layers,
            # which holds none of its industry): the largest takes it by default only when its own words say what that layer's name says
            # or the name states no kind of business; else its own words decide: the map's layer it is in when they say that layer's
            # name (listed there, left out of its figures as another way of earning), else the layer of its family that shares two of
            # their words, one of them in its name (never one by chance: "homes" never says "Home improvement"), else "Other"
            named_, says_ = layer_says(big, own_text(ev(c)), theme_words)
            if not named_ or says_:
                return big
            if src is not None and layer_says(src, own_text(ev(c)), theme_words)[1]:
                return src
            said_ = whole_stems(own_text(ev(c)))
            told = [v for v in cands if v is not big and stated_model(v.get("was") or v.get("layer") or "") in ("", models.get(c.get("ticker")))
                    and len(said_ & whole_stems(f"{v.get('layer') or ''} {v.get('description') or ''}")) >= 2
                    and said_ & (whole_stems(v.get("layer") or "") - theme_words)]
            return max(told, key=lambda v: (len(said_ & whole_stems(f"{v.get('layer') or ''} {v.get('description') or ''}")), sizes.get(id(v), 0))) \
                if told else STAY
        # R39 (lane s1-fit; the live R37 Automotive deck: Bosch and Asahi India Glass, auto component makers the answer read as makers of their
        # own products, moved into "Tyre manufacturers"): when the largest layer of its family holds none of its industry and a layer of the
        # map is all of its industry and holds most of the map's companies of it, that layer, whatever way its companies earn; it is listed
        # there but left out of the layer's figures and split as another way of earning. Not when the largest's own name says what its words
        # say ("Network equipment makers" for a telecom equipment maker)
        mine = kind_stems(own_text(ev(c)))
        spread = sum(same(v) for v in own)
        kin = [v for v in own if v not in cands and sizes.get(id(v)) and same(v) == sizes[id(v)] and same(v) * 2 > spread
               and stated_model(v.get("was") or v.get("layer") or "") in ("", models.get(c.get("ticker")))] \
            if ind and not same(big) and not mine & (kind_stems(big.get("layer") or "") - theme_words) else []
        if kin:
            return max(kin, key=lambda v: same(v))
        words = lambda v: kind_stems(f"{v.get('layer') or ''} {v.get('description') or ''}")      # noqa: E731
        # R39 (lane s1-fit; live R37 Consumer retail: a propane distributor and a pawnbroker whose stored evidence held no words of their
        # own went to "Off-price", the largest, which holds none of their industry): a company with no words joins the largest only when
        # that layer holds its official industry (no industry known either: the largest, as before); else it stays in "Other"
        if not mine:
            return big if (same(big) or not ind) else STAY
        # d1 (the outside review of the live Release 41 Consumer retail deck: Dillard's, Gap, Urban Outfitters, Abercrombie, Macy's and Kohl's
        # in "Off-price, dollar and discount store chains", the largest of the retailers' layers, by their industry alone, while American Eagle
        # and Buckle, as like them, sat in "Other"): when the largest's own name states a kind of business (its words apart from the theme's:
        # off-price, dollar, discount) that the company's own words don't say, holding its industry doesn't place it there: the layer of its
        # family whose name its words do say, else "Other"
        # off-price, dollar, discount) that the company's own words don't say, and the largest is no catch-all of its family (it holds under
        # half of the family's companies), and its words share none of that layer's, holding its industry doesn't place it there: "Other" (an
        # online seller still joins the layer whose name states both ways of earning: R40 below)
        named_, says_ = name_says(big.get("layer") or "", own_text(ev(c)), theme_words)
        # cl48 (R47): "off-price" in the layer's words is one word, never shared by a company's "branched off" by chance (whole_stems)
        narrow = named_ and not says_ and not whole_stems(own_text(ev(c))) & whole_stems(f"{big.get('layer') or ''} {big.get('description') or ''}") \
            and sizes.get(id(big), 0) * 2 <= sum(sizes.get(id(v), 0) for v in cands)
        if narrow:
            c["_narrow"] = True
        if (same(big) or mine & words(big)) and not narrow:
            return big
        alike = [v for v in cands if sizes.get(id(v)) and same(v) == sizes[id(v)] and mine & words(v)
                 and stated_model(v.get("was") or v.get("layer") or "") in ("", models.get(c.get("ticker")))]
        if alike:
            return max(alike, key=lambda v: sizes[id(v)])
        if ind and not any(same(v) or mine & words(v) for v in cands):
            return STAY
        # R39 (lane s1-fit; the live R37 Consumer retail deck had 34 such companies in "Off-price, dollar and value-format retailers", the
        # largest, because some other layer shared one of their words): the largest neither holds its industry nor shares its words, and no
        # layer of its family holds its industry (where one does, the map groups its industry there and the largest stands, as before): the
        # layer of its family sharing two of its words, never one whose name states another way of earning, never a new layer; else "Other".
        # R41 (lane s2-exact, the live Release 38.1 Consumer retail deck: Chewy and eleven more online sellers, two pawnbrokers and a propane
        # distributor in "Off-price, dollar and discount store chains", the largest, which holds none of their industry, because "Online
        # retailers and marketplaces", a layer whose name states another way of earning, held some of it): a layer whose name states another
        # way of earning, which never takes the company, doesn't count as the map's layer of its industry; then the largest stands only as the
        # family's catch-all (it holds most of the companies of the family's layers), and the layer sharing two of its words shares one of
        # its name (live: Lulus, sharing "beautiful" and "matter" with the prose of "Home improvement and specialty chains", stays in "Other")
        fair_name = lambda v: stated_model(v.get("was") or v.get("layer") or "") in ("", models.get(c.get("ticker")))      # noqa: E731
        holds = [v for v in cands if same(v)]
        # R40 (the owner's review of the live Release 39 Consumer retail deck: Chewy, Revolve, Stitch Fix and more online sellers in "Other"
        # beside "Online retailers and marketplaces", whose map name "Online marketplaces" states a platform's way of earning): a layer whose
        # shown name states two ways of earning, the company's one of them, takes it when it holds its industry and the company's own words
        # say what its name says (share a word of it; "e-commerce" says "online") or fit it (two words of its name and description)
        said = mine | ({_stem("online")} if re.search(r"\be-?commerce\b", own_text(ev(c)), re.I) else set())
        both = [v for v in holds if v is not big and len(name_models(v.get("layer"))) >= 2 and models.get(c.get("ticker")) in name_models(v.get("layer"))
                and (said & (kind_stems(v.get("layer") or "") - theme_words) or fits(c, v))]
        if both:
            return max(both, key=lambda v: (same(v), sizes.get(id(v), 0)))
        # d1: one the largest's name doesn't describe goes to the layer of its family it fits (below), else "Other" (with the like of it of
        # its industry, a layer of that industry: by_model below)
        if not narrow and (not ind or any(fair_name(v) for v in holds) or (holds and sizes.get(id(big), 0) * 2 > sum(sizes.get(id(v), 0) for v in cands))):
            return big
        fair = [v for v in cands if v is not big and fair_name(v)]
        two = [v for v in fair if len(mine & words(v)) >= 2 and mine & (kind_stems(v.get("layer") or "") - theme_words)
               and not (narrow and v is big)]
        return max(two, key=lambda v: (len(mine & words(v)), sizes.get(id(v), 0))) if two else STAY
    # d1 (the outside review of the live Release 41 decks: Fortinet, the map's own pick for "Network security appliances and subscriptions",
    # and Arm, its pick for "Design software and IP licensing", left them by how they earn for "Other", the map having no layer of their
    # way of earning): a company the map itself named in a layer (never one placed after it) whose way of earning no layer of the map has,
    # and no other company leaving a layer shares, and whose own words say what that layer's name says, stays in the map's layer, listed
    # but left out of its figures as another way of earning
    lone_fam = Counter(fam(c) for c in movers if home.get(fam(c)) is None)
    for c in movers:
        f = fam(c)
        if home.get(f) is None and lone_fam[f] == 1 and c.get("_from_layer") and not c.get("placed"):
            src_ = next((v for v in own if id(v) == c["_from_layer"]), None)
            # and only where its own words say what the layer's name says (a materials supplier in "Chip equipment" never stays: lane m1)
            if src_ is not None and name_says(src_.get("was") or src_.get("layer") or "", own_text(ev(c)), theme_words)[1]:
                outside.add(c.get("ticker"))
                models.pop(c.get("ticker"), None)
                src_["companies"].append({k: x for k, x in c.items() if k != "_from_layer"})
                continue
        target = home_of(c, f)
        src_ = next((v for v in own if id(v) == c.get("_from_layer")), None) if previous else None
        if src_ is not None and target is not STAY and target is not src_ and previous.get(c.get("ticker")) in (
                _HALF_RX.sub("", src_.get("layer") or ""), src_.get("was")) \
                and not evidence_for(c, target or {"layer": name_of([c], f)}, src_, key(c.get("industry")) if c.get("industry") else ""):
            target = src_            # R45: kept in its previous live layer, no evidence for the new one
        if target is STAY:
            stays.append({k: x for k, x in c.items() if k not in ("_from_layer", "fit")})
            continue
        c.pop("_narrow", None)
        if target is not None and mains.get(id(target)) != f:      # R39: in the layer of its industry, another way of earning
            outside.add(c.get("ticker"))
            models.pop(c.get("ticker"), None)
        stayed = target is not None and id(target) == c.get("_from_layer")       # R41: kept in the map's layer of its industry
        target = target or new.setdefault(f, _model_layer("", []))
        target["companies"].append({**{k: x for k, x in c.items() if k != "_from_layer"}, **({} if stayed else {"moved": True})})
    if stays:
        rest_v = next((v for v in out if v.get("official") and v.get("basis") == "rest"), None)
        if rest_v is not None:
            rest_v["companies"] = sorted(rest_v["companies"] + stays, key=lambda c: (-(c.get("cap") or 0), c.get("ticker") or ""))
            # d1: the companies the largest layer's name doesn't describe (above) and the companies of "Other" of the same official industry
            # whose words say no other way of earning become a layer of that industry when they are INDUSTRY_GROUP_MIN or more (the live
            # Release 41 Consumer retail deck: Gap, Abercrombie, Urban Outfitters beside American Eagle and Buckle, all family clothing chains)
            from .theme_check import OWN_SAYS
            for ind_k in sorted({key(c.get("industry")) for c in stays if c.get("_narrow") and c.get("industry")}):
                lead = [c for c in stays if c.get("_narrow") and key(c.get("industry")) == ind_k]
                f_ = fam(lead[0])
                if re.search(r"\b(?:misc\w*|other|diversified|nec|general)\b", industry_label(lead[0].get("industry") or ""), re.I):
                    continue          # an industry that names no one kind of business ("Miscellaneous retail") makes no layer
                says = "|".join([STORE_SAYS] * (f_ == model_family("retail")) + [OWN_SAYS[m_] for m_ in OWN_SAYS if model_family(m_) == f_])
                # with them, a company of "Other" of that industry whose model is unknown only when its own words state the family's way
                # of earning ("a clothing retailer ... 451 stores")
                lead_m = {models.get(c.get("ticker")) for c in lead}
                grp = [c for c in rest_v["companies"] if key(c.get("industry")) == ind_k
                       and (models.get(c.get("ticker")) in lead_m or (not fam(c) and says and re.search(says, own_text(ev(c)), re.I)))]
                if len(lead) >= SPLIT_PART and len(grp) >= INDUSTRY_GROUP_MIN:
                    ids = {id(c) for c in grp}
                    top_m = Counter(models.get(c.get("ticker")) for c in lead).most_common(1)[0][0]
                    for c in grp:            # one whose model no answer gave takes the one its own words state ("a clothing retailer")
                        if not fam(c) and c.get("ticker"):
                            models[c["ticker"]] = every[c["ticker"]] = top_m
                            conf[c["ticker"]] = "medium"
                    rest_v["companies"] = [c for c in rest_v["companies"] if id(c) not in ids]
                    label = industry_label(grp[0].get("industry") or "")
                    out.insert(next((i for i, v in enumerate(out) if v.get("official")), len(out)),
                               {"layer": label, "description": "", "industry_group": True,
                                "companies": [{k: x for k, x in c.items() if k != "_narrow"} for c in grp]})
            rest_v["companies"] = [{k: x for k, x in c.items() if k != "_narrow"} for c in rest_v["companies"]]
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
    split_out: set = set()          # R41: companies placed after the map that this split by model moved out of the layer they were placed in
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
                split_out |= {c.get("ticker") for c in mine if c.get("placed")}
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
    out = _no_single_layers(out, before, main, fam, theme, fits)
    # c1 (R44): the companies left in "Other" placed where their own words or official industry name a layer's business (from_other)
    out = from_other(out, models, conf, every, fam, main, ev, theme_words, outside)

    # 3b. R31: no two layers of one primary model (the live R30 Semiconductors deck had "Fabless chip design" beside "Product designers that
    # outsource making"): a layer the split made joins the map's own layer of its primary model, family and sub-basis
    def primary(cos):
        f = main(cos)
        known = [c for c in cos if fam(c) == f] if f else []
        if not known or len(known) * 2 < len(cos):
            return None
        fines = {models[c["ticker"]] for c in known}
        return (next(iter(fines)) if len(fines) == 1 else f, f, sub_basis(f, [ev(c) for c in known]))
    keys = {id(v): primary(v["companies"]) for v in out if not v.get("official") and v["companies"]}
    model_names = {x[1] for x in MODELS.values()} | {x[0] for x in FAMILIES.values()}
    by_how = lambda x: x.get("by_model") or x["layer"] in model_names or x["layer"].removesuffix(", by revenue model") in model_names     # noqa: E731
    groups: dict = {}
    for v in out:          # a half of a split by size stays
        k = keys.get(id(v))
        if k and k[2] != "mixed" and not v.get("official") and not v.get("scale"):
            groups.setdefault(k, []).append(v)
    gone, lone = set(), []
    for grp in groups.values():
        named = [x for x in grp if by_how(x)]
        if len(grp) < 2 or not named:
            continue
        plain = [x for x in grp if not by_how(x)]
        # R36 (live R32 Semiconductors: Qorvo, IPG Photonics, a chip materials supplier and six more makers shown under "Semiconductor
        # equipment", the larger of the map's two layers of makers): when the map itself keeps two layers that earn this way apart by what
        # they make, how a company earns doesn't say which of them it belongs to, so the model-named layers become one and stay beside them
        target = max(plain if len(plain) == 1 else named, key=lambda x: len(x["companies"]))
        for v in named:
            if v is not target:
                # R39 (lane s1-fit; the live R37 Semiconductors deck: Micron, Intel, SK Hynix, lasers and LED makers, 13 companies of a split
                # layer, joined "Semiconductor equipment" because both make their own products): a layer the split made joins the map's own
                # layer only with the companies whose own words share what that layer's name or description says is made or done; the others
                # keep their layer, and one left alone goes to the theme's "Other" group (no layer of one company: R27)
                # R41 (lane s2-exact, the live Release 38.1 Semiconductors deck: Qorvo, placed by the answer with the chip designers, split
                # out with the makers by how it earns, joined "Semiconductor equipment" as if the map had placed it with them): a company placed
                # after the map that the split by model moved out of its layer joins only when it fits, like one moved by how it earns (the
                # companies the map itself named keep joining as before: R31's managed-service firms)
                ok = lambda c: by_how(target) or not (c.get("moved") or c.get("ticker") in split_out) or fits(c, target)      # noqa: E731
                fit = [c for c in v["companies"] if ok(c)]
                left = [c for c in v["companies"] if not ok(c)]
                target["companies"] += [{**c, "moved": True} for c in fit]
                if len(left) == 1:
                    lone.append({**left[0], "moved": True, "single": True, "fit": True})
                    left = []
                v["companies"] = left
                if not left:
                    gone.add(id(v))
    out = [v for v in out if (v["companies"] or not v.get("by_model")) and id(v) not in gone]
    if lone:
        other = next((x for x in out if x.get("official") and x.get("basis") == "rest"), None)
        if other is None:
            other = {"layer": other_label(theme), "description": "", "official": True, "basis": "rest", "companies": []}
            out.append(other)
        other["companies"] += lone


    # ex49 (R48, the outside review of the live Release 48 decks: "distinguish a real difference in revenue model from insufficient evidence or
    # partial comparability; never use them interchangeably"): why a company listed in a layer is left out of its figures, precisely:
    # "off_industry" (its own words describe another business than its official industry files it under), "model" (its way of earning, read
    # from the answer or its own words, is another than the layer's), "weak" (its way of earning is read only with low confidence), "no_words"
    # (no description of its own is stored), "no_model" (its own words don't state how it earns)
    def out_why(c) -> str:
        s_ = c.get("ticker")
        if s_ in another:
            return "off_industry"
        if fam(c) or s_ in outside:
            return "model"
        if conf.get(s_) == "low" and every.get(s_):
            return "weak"
        return "no_model" if own_text(ev(c)).strip() else "no_words"

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
        # R40 (the owner's review of the live Release 39 Automotive deck: Bosch and Asahi India Glass, in "Component and systems suppliers",
        # left out of its figures as another business because they were read as makers of their own products): in a layer whose companies
        # are all of one official industry, a company of it whose model is of the layer's kin (making: its own products or parts and
        # components) is in the layer's figures; never one of another business than its industry files it under (off_industry)
        inds_ = {key(c.get("industry")) for c in cos}
        kin = {c.get("ticker") for c in cos if fam(c) != f and c.get("ticker") not in another and len(inds_) == 1 and "" not in inds_
               and any({f, model_family(read.get(c.get("ticker")))} <= k_ for k_ in KIN_FAMILIES)}
        # d1 (the outside review of the live Release 41 decks: a company left out of its layer's figures for want of a stored description):
        # one with no description of its own, of the layer's way of earning or of none shown, whose official industry is that of most of the
        # layer's companies and of no other layer of the map (an unambiguous fit), is in the layer's figures on its industry, and says so
        # ("on_industry"); one whose own words show how it earns only weakly stays out (R27)
        top_ind = Counter(key(c.get("industry")) for c in known if c.get("industry")).most_common(1)
        elsewhere = {key(x.get("industry")) for w in out if w is not v and not w.get("official") for x in w["companies"] if x.get("industry")}
        on_ind = {c.get("ticker") for c in cos if fam(c) == "" and c.get("ticker") not in another and c.get("ticker") not in outside and top_ind
                  and c.get("industry") and key(c.get("industry")) == top_ind[0][0] and top_ind[0][1] * 2 > len(known)
                  and top_ind[0][0] not in elsewhere and not own_text(ev(c)).strip()
                  and model_family(every.get(c.get("ticker")) or "") in ("", f)}
        kin |= on_ind
        # ex49 (R48, the outside review of the live Release 48 Consumer retail deck: lululemon, in "Apparel and consumer brand owners" by
        # its own words, left out of that layer's figures as "another business"): a company read as a retailer, whose own words say it
        # designs the goods it sells, or makes them under its own brand (theme_check.own_goods), that the answer also read as a maker, and whose
        # words say this layer's name, sells products of its own: in a layer of makers it is in the figures, and says why ("own_goods").
        # Never one of another business than its industry files it under (off_industry)
        brand = {c.get("ticker") for c in cos if f == "making" and every.get(c.get("ticker")) == "retail" and c.get("ticker") not in another
                 and conf.get(c.get("ticker")) != "low" and any(model_family(t) == "making" for t in tags.get(c.get("ticker")) or [])
                 and own_goods(ev(c)) and layer_says(v, own_text(ev(c)), theme_words)[1]}
        kin |= brand
        # ex49 (R48, the rotating review of the live Release 48 decks, G3: Fortinet in "Network security appliances and subscriptions", Akamai
        # in "Cloud-delivered security and edge networks", Route Mobile in "Enterprise connectivity and messaging", each the map's own pick and
        # each left out as "other business"): a company of another way of earning that the map itself put in this layer (never one the split
        # moved there), whose own words say the layer's name and name no way of earning but the layer's, and whose model rests on no words of
        # its own ("high" confidence is words of its kind), differs from the layer only by the answer's read: it is in the figures, and says
        # so ("by_words"). So is one placed there after the map whose own words state the layer's way of earning in so many words (an
        # assembly and test services firm in "Outsourced packaging and test" read as a parts maker). One whose own words name another way
        # of earning (a design services firm in a software layer) stays out, as does one placed after the map whose words state none.
        said_ = lambda c: {model_family(x) for x in words_models(ev(c))} - {""}      # noqa: E731
        words_ = {c.get("ticker") for c in cos if fam(c) != f and c.get("ticker") not in kin and c.get("ticker") not in another
                  and every.get(c.get("ticker")) and model_family(every.get(c.get("ticker"))) != f and not c.get("moved")
                  and conf.get(c.get("ticker")) in ("medium",) and said_(c) <= {f} and (not c.get("placed") or said_(c) == {f})
                  and layer_says(v, own_text(ev(c)), theme_words)[1]}
        kin |= words_
        rest = [c for c in cos if fam(c) != f and c.get("ticker") not in kin]
        known_ids = {c.get("ticker") for c in known} | kin
        v["companies"] = [({**c, "on_industry": True, "model": c.get("model") or Counter(models[x["ticker"]] for x in known).most_common(1)[0][0],
                            "model_confidence": c.get("model_confidence") or "low"} if c.get("ticker") in on_ind else
                           {**c, "own_goods": True} if c.get("ticker") in brand else
                           {**c, "by_words": True} if c.get("ticker") in words_ else c) if c.get("ticker") in known_ids else
                          {**c, "model_out": "other" if fam(c) or c.get("ticker") in outside else "unknown",
                           "out_why": out_why(c)} for c in cos]      # R34: why, named; ex49: precisely (out_why)
        known = known + [c for c in cos if c.get("ticker") in kin]
        away_ = {c.get("ticker") for c in rest if fam(c) or c.get("ticker") in outside}      # cl48: listed as another way of earning
        sparse = len(known) * 2 < len(cos)
        if sparse:
            # R26: a line resting on a few of a layer's companies isn't what they have in common: said plainly instead (the live R25 IT services
            # deck, "8 of 50; the others' descriptions don't show how they earn"); R27: the others are left out of its figures
            line = f"How they earn is shown for only {len(known)} of these {len(cos)} companies, mainly {what}; {out_line(rest, 'the other', away_)}"
        else:
            line = f"They earn mainly from {what}."
            if rest:
                line += " " + out_line(rest, f"of {len(cos)}", away_)
        also = also_earn(known, f)
        if also:
            n_, t_ = also
            line += f" {n_} of the {len(known)} also earn from {MODELS[t_][2]}."
        if v.get("scale"):
            line += f" The {v['scale']} half of one group by market value; the other half is “{v['sibling']}”."
        sub = sub_basis(f, [ev(c) for c in known])
        # ex49 (R48, the outside review of the live Release 48 Chemicals deck: "Custom synthesis manufacturers" ranked against commodity
        # intermediates, both read as makers of their own products): the business model the map's own name for the layer states in so many
        # words (theme_check.stated_model: "custom synthesis", "contract manufacturing", "foundry"), when it is of another family than how its
        # companies are read to earn ("named"): such a layer is ranked only beside layers of that same business model (theme_data.one_business)
        named = next((x for x in (stated_model(v.get("was") or ""), stated_model(_HALF_RX.sub("", v.get("layer") or ""))) if x in MODELS), "")
        v["model"] = {"id": mid, "family": f, "line": line, "known": len(known), "of": len(cos), "out": len(rest),
                      "also": [{"id": also[1], "n": also[0]}] if also else [], **({"sparse": True} if sparse else {}), **({"sub": sub} if sub else {}),
                      **({"named": named} if named and model_family(named) != f else {})}
        # R40 (the owner's review of the live Release 39 Semiconductors deck: "Makers of their own products", memory, optical and analog chip
        # makers the split grouped by how they earn, ranked beside the map's layers): a layer the split made and named only by how its
        # companies earn is shown, never ranked (theme_data.headline_ok)
        if v.get("by_model") and not v.get("scale") and v["layer"].removesuffix(", by revenue model") in model_names:
            v["model"]["by_how"] = True
            # c1 (R44, the outside review of the live Release 43 Semiconductors deck: "Makers of their own products" mixes memory, processor,
            # laser and optics makers): the reason it is never ranked, on its own page (no group of it holds the 5 companies a ranking needs)
            if BY_HOW_SAID not in v["model"].get("line", ""):
                v["model"]["line"] = (v["model"].get("line") or "").rstrip() + " " + BY_HOW_SAID
    # R31: two of the map's own layers of one primary model, family and sub-basis both stay (the map groups them by what they make or serve);
    # each one's line says so, so no reader takes them for two ways of earning
    mine = [v for v in out if not v.get("official") and not v.get("scale") and (v.get("model") or {}).get("id") and not v["model"].get("sparse")
            and v["model"].get("sub") != "mixed"]
    for v in mine:
        same = [x["layer"] for x in mine if x is not v and all(x["model"].get(k) == v["model"].get(k) for k in ("id", "family", "sub"))]
        if same:
            v["model"]["same_as"] = same
            v["model"]["line"] += (" Its companies earn the same way as those of " + ", ".join(f"“{x}”" for x in same)
                                   + "; the map keeps them as separate layers.")
    return out


def unsplit_unshown(vc: list[dict], shown: set) -> list[dict]:
    """The layers with a split by market value undone where one of its halves has no company the deck shows (R32: the live R31 Real estate
    deck had "Residential developers (larger)" and "No listed company is shown for Residential developers (smaller)"): one layer of both
    halves' companies, the map's name, no "(larger)"/"(smaller)", its line counted again over them without the halves' words. `shown`: the
    symbols the deck shows (confirmed, with figures).
    R40 (the owner's review of the live Release 39 Automotive deck: "Component and systems suppliers (smaller)" showed ONE company of its 69,
    the others beyond the dive's figures, theme_base.FIGURES_MAX, the largest first): undone too where a half shows fewer than SPLIT_PART
    companies in its figures (shown, not left out by how it earns), the floor the split itself keeps for each part."""
    out = list(vc)
    for v in vc:
        if v.get("scale") != "larger":
            continue
        sib = next((x for x in out if x.get("scale") == "smaller" and x.get("layer") == v.get("sibling")), None)
        if sib is None or all(sum(1 for c in x.get("companies") or [] if c.get("ticker") in shown and not c.get("model_out")) >= SPLIT_PART
                              for x in (v, sib)):
            continue
        cos = list(v.get("companies") or []) + list(sib.get("companies") or [])
        merged = {k: x for k, x in v.items() if k not in ("scale", "sibling")}
        merged.update(layer=re.sub(r" \(larger\)$", "", v["layer"]), companies=cos)
        md = next((x["model"] for x in (v, sib) if (x.get("model") or {}).get("id")), None) or v.get("model")
        if md:
            line = re.sub(r" The (?:larger|smaller) half of one group by market value; .*$", "", str(md.get("line") or ""))
            md = {**md, "line": line, "of": None}
            md = shown_model(md, [{**c, "model": c.get("model", "")} for c in cos])
            if md.get("of") is None:
                md["of"] = len(cos)
            merged["model"] = md
        out[out.index(v)] = merged
        out.remove(sib)
    return out


def out_line(rest: list[dict], of: str, other=frozenset()) -> str:
    """How many of a layer's companies are left out of its figures and rankings, and why (R27): their model unknown, or of low confidence.
    cl48 (R47): one listed there as another way of earning or another business (model_out "other", or in `other`) is said to earn
    another way, never to have evidence that doesn't show how it earns."""
    n = len(rest)
    away = [c for c in rest if c.get("model_out") == "other" or c.get("ticker") in other]
    left = [c for c in rest if c not in away]
    k, u = len(away), len(left)
    low = sum(1 for c in left if c.get("model_confidence") == "low")
    why = ("doesn't show how it earns" if u == 1 else "doesn't show how they earn") if not low else \
          ("shows how it earns only weakly" if u == 1 else "shows how they earn only weakly") if low == u else \
          "doesn't show, or only weakly shows, how they earn"
    own_ = lambda m: 'its' if m == 1 else 'their'      # noqa: E731
    earns = f"{'it earns' if k == 1 else 'they earn'} another way than the layer's companies"
    reason = (f"as {own_(u)} evidence {why}" if not k else f"as {earns}" if not u
              else f"{k} as {earns}, {u} as {own_(u)} evidence {why}")
    if of.startswith("the other"):
        return f"the other {n} {'is' if n == 1 else 'are'} listed but left out of this layer's figures and rankings, {reason}."
    return f"{n} {of} {'is' if n == 1 else 'are'} listed but left out of this layer's figures and rankings, {reason}."


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


def shown_model(model: dict | None, rows: list[dict]) -> dict | None:
    """The layer's "how they earn" line counted over the companies its page shows (R28: the live R27 IT deck said "shown for only 6 of these
    46 companies" on a page of 6: the 46 were every company the map put in the layer, most with no figures worked out). `rows`: the layer's
    confirmed companies with figures, carrying model, model_tags, model_confidence and model_out (theme_data.model_fields). Unchanged when
    the counts already agree or the layer carries no model."""
    if not model or not rows or not any("model" in r for r in rows):
        return model
    from .theme_check import FAMILIES, MODELS
    if len(rows) == model.get("of"):
        return model
    f, mid = model.get("family") or "", model.get("id") or ""
    known = [r for r in rows if r.get("model") and not r.get("model_out")] if f else []
    rest = [r for r in rows if r not in known]
    n = len(rows)
    if not known:
        line = (f"None of these {n} companies' descriptions shows how it earns, so no common way of earning is given for this group."
                if n > 1 else "Its description doesn't show how it earns.")
        half = re.search(r" The (?:larger|smaller) half of one group by market value; .*$", str(model.get("line") or ""))
        return {**model, "line": line + (half.group(0) if half else ""), "known": 0, "of": n, "out": len(rest), "sparse": True, "also": []}
    what = MODELS[mid][2] if mid in MODELS else FAMILIES.get(f, ("", ""))[1]
    sparse = len(known) * 2 < n
    if sparse:
        line = f"How they earn is shown for only {len(known)} of these {n} companies, mainly {what}; {out_line(rest, 'the other')}"
    else:
        line = f"They earn mainly from {what}." + (" " + out_line(rest, f"of {n}") if rest else "")
    also = also_earn(known, f)
    if also:
        line += f" {also[0]} of the {len(known)} also earn from {MODELS[also[1]][2]}."
    half = re.search(r" The (?:larger|smaller) half of one group by market value; .*$", str(model.get("line") or ""))
    if half:                                   # the split's own words stay (by_model step 2)
        line += half.group(0)
    out = {**model, "line": line, "known": len(known), "of": n, "out": len(rest), "also": [{"id": also[1], "n": also[0]}] if also else []}
    out.pop("sparse", None)
    return {**out, "sparse": True} if sparse else out


# c1 (R44, the outside review of the live Release 43 Semiconductors deck: "Makers of their own products" mixes memory, processor, laser and
# optics makers): what a layer named only by how its companies earn says on its own page, in the words of the ranking's own reason
# (theme_data.RANK_WHY "how"); its companies stay together, as no group of them by what they make is confirmed by their words
BY_HOW_SAID = "Shown, never ranked: a group by how its companies earn, of different businesses."
# c1 (R44, the outside review of the live Release 43 decks: 29 of 90 Consumer retail companies and 32 of 65 Metals companies in "Other"):
# words that name one kind of goods ("apparel" says what "clothing" says), for a company's words read against a layer's name
SAME_KIND = ((r"\bapparel\b|\bgarments?\b", "clothing"),)
NO_ONE_BUSINESS = r"\b(?:misc\w*|other|others|diversified|nec|general)\b"      # an official industry naming no one kind of business


def _near(a: str, b: str) -> bool:
    """One stem says another: the same, or one of five letters or more starting the other (name_says)."""
    return a == b or (min(len(a), len(b)) >= 5 and (a.startswith(b) or b.startswith(a)))


def says_most_of(name: str, text: str, theme_words: set) -> bool:
    """Whether a company's words say two or more, and at least half, of the words of a layer's name beyond the theme's own (c1, R44: "a
    specialty clothing store" says two of "Family clothing stores"; "aluminium powder" says one of "Aluminium and copper smelting", "sells
    furniture online" one of "Online retailers" (R38: one shared word places nothing): neither is placed there by its words)."""
    rest = _stems(_short_joined(name)) - theme_words           # cl48 (R47): "off-price" one word, never said by "branched off"
    mine = _stems(_short_joined(text))
    said = sum(1 for b in rest if any(_near(a, b) for a in mine))
    return said >= 2 and 2 * said >= len(rest)


def industry_named(name: str, industry, theme_words: set) -> bool:
    """Whether a layer's name says all that an official industry's plain name says (c1, R44: "Zinc" in "Zinc, lead and silver mining and
    smelting", "Shipbuilding" in "Naval shipbuilding"; "Industrial minerals" is not all said by "Coal, iron ore and mineral mining")."""
    ind = kind_stems(plain_industry(industry)) - theme_words
    mine = kind_stems(str(name or "").lower().replace("-", " "))
    return bool(ind) and all(any(_near(a, b) for a in mine) for b in ind)


def no_words(evidence) -> bool:
    """Whether a company's evidence holds no words of its own about its work: none, or only the titles of its filings (theme_routes)."""
    return not own_text(evidence).strip()


def from_other(out: list[dict], models: dict, conf: dict, every: dict, fam, main, ev, theme_words: set, outside: set) -> list[dict]:
    """c1 (R44, the outside review of the live Release 43 decks: "improve coverage only with evidence; never force"): the companies left in
    the "Other" group after the split by how companies earn, placed where their own words or official industry name a business a layer
    covers, each marked with how ("by_industry" or "by_words"); every other one stays in "Other".
    1. One with no words of its own and no way of earning shown goes to the layer made of its official industry and named by it (by_model's
       industry group), else to the one layer whose name says all its official industry's name says (industry_named: "Coal" in "Mining of
       coal and iron ore") when that layer holds more than half of the theme's companies of that industry that have words of their own: an
       industry named by two layers ("Aluminium": a smelter's and a product maker's) or held mostly elsewhere places nothing.
    2. One whose way of earning is shown (not at "low") goes to the one layer of that way of earning whose name its own words say at least
       half of (says_most_of: "a specialty clothing store" says "Family clothing stores"; "apparel" says "clothing", SAME_KIND), and, in a
       family whose layers differ
       by a sub-basis (theme_check.SUB_BASIS: a metals company's commodity), only to a layer of its own (a ferro chrome maker never joins
       steelmaking by the word "steel").
    3. The companies of one official industry naming one kind of business (not "Miscellaneous", "Diversified"...) left in "Other" with no
       words or with words of one way of earning, with those of it the split moved from "Other" by that way of earning alone into a layer
       whose name their words don't say, make a layer of that industry when they are INDUSTRY_GROUP_MIN or more and SPLIT_PART or more of them
       have words of their own (never a layer of unread companies), and no company of that industry with words sits elsewhere (Metals: ten ferro
       alloy makers, five of them in "Mining of coal and iron ore" or "Other" by how they earn, five with no words, all "Ferro & Silica
       Manganese")."""
    from collections import Counter

    from .theme_check import SUB_BASIS, SUB_OF, off_industry, sub_basis
    rest_v = next((v for v in out if v.get("official") and v.get("basis") == "rest"), None)
    if rest_v is None or not rest_v["companies"]:
        return out
    layers = [v for v in out if not v.get("official") and v["companies"] and not v.get("scale")]      # never a half of a layer split by size
    name_of = lambda v: v.get("was") or v["layer"]          # noqa: E731
    group_ind = lambda v: key(v["companies"][0].get("industry")) if v.get("industry_group") else None      # noqa: E731
    worded: dict = {}
    for v in out:
        for c in v["companies"]:
            if c.get("industry") and not no_words(ev(c)):
                worded.setdefault(key(c["industry"]), Counter())[id(v)] += 1

    def kinded(text: str) -> str:
        for rx, to in SAME_KIND:
            text = re.sub(rx, to, text, flags=re.I)
        return text

    def sub_ok(c, v, f) -> bool:
        k_ = SUB_BASIS.get(f)
        if not k_:
            return True
        return SUB_OF[k_](ev(c)) == sub_basis(f, [ev(x) for x in v["companies"] if fam(x) == f])

    left = []
    for c in rest_v["companies"]:
        ind = key(c.get("industry")) if c.get("industry") else ""
        target, how = None, ""
        if c.get("ticker") in outside or off_industry(ev(c)):
            pass
        elif no_words(ev(c)) and not fam(c) and not every.get(c.get("ticker")) and ind:
            grp = [v for v in layers if group_ind(v) == ind]
            if grp:
                target, how = grp[0], "by_industry"
            elif not re.search(NO_ONE_BUSINESS, industry_label(c.get("industry")), re.I):
                said = [v for v in layers if industry_named(name_of(v), c.get("industry"), theme_words)]
                held = worded.get(ind) or Counter()
                if len(said) == 1 and held[id(said[0])] * 2 > sum(held.values()):
                    target, how = said[0], "by_industry"
        elif fam(c):
            f = fam(c)
            text = kinded(own_text(ev(c)))
            said = [v for v in layers if main(v["companies"]) == f and says_most_of(name_of(v), text, theme_words) and sub_ok(c, v, f)]
            if len(said) == 1:
                target, how = said[0], "by_words"
        if target is None:
            left.append(c)
        else:
            target["companies"].append({**c, "moved": True, "placed_by": how})
    rest_v["companies"] = left
    # 3. a layer of one official industry from "Other" and the companies the split moved by how they earn alone
    for ind in sorted({key(c.get("industry")) for c in left if c.get("industry")}):
        mine = [c for c in left if key(c.get("industry")) == ind]
        label = industry_label(mine[0].get("industry"))
        if re.search(NO_ONE_BUSINESS, label, re.I):
            continue
        fams = Counter(fam(c) for c in mine if fam(c))
        # moved by how it earns alone: the layer's name isn't said by its words, or its commodity isn't the layer's (SUB_BASIS)
        moved_in = [(v, c) for v in layers for c in v["companies"] if key(c.get("industry")) == ind and c.get("moved") and c.get("placed")
                    and fam(c) and not v.get("industry_group") and not v.get("scale")
                    and (not name_says(name_of(v), own_text(ev(c)), theme_words)[1] or not sub_ok(c, v, fam(c)))]
        fams.update(fam(c) for _, c in moved_in)
        if len(fams) != 1:
            continue
        f = next(iter(fams))
        grp = [c for c in mine if fam(c) == f or (no_words(ev(c)) and not every.get(c.get("ticker")))] + [c for _, c in moved_in]
        has_words = [c for c in grp if not no_words(ev(c))]
        ids = {id(c) for c in grp}
        elsewhere = sum(1 for v in out for c in v["companies"] if key(c.get("industry")) == ind and id(c) not in ids and not no_words(ev(c))
                        and fam(c) == f)
        if len(grp) < INDUSTRY_GROUP_MIN or len(has_words) < SPLIT_PART or elsewhere:
            continue
        for v, c in moved_in:
            v["companies"] = [x for x in v["companies"] if x is not c]
        rest_v["companies"] = [c for c in rest_v["companies"] if id(c) not in ids]
        out.insert(next((i for i, v in enumerate(out) if v.get("official")), len(out)),
                   {"layer": label, "description": "", "industry_group": True,
                    "companies": [{**c, "moved": True, "placed_by": "by_industry" if no_words(ev(c)) else "by_words"} for c in grp]})
    return out


def _no_single_layers(out: list[dict], before: dict, main, fam, theme: str, fits=None) -> list[dict]:
    """The layers with none of one company that the split made or reshaped (R27): its company joins the largest other layer of its own family,
    else the theme's "Other" group (made when there is none), marked "single". R39 (lane s1-fit): the company of a layer the split made
    joins only a layer of its family it fits (`fits(company, layer)`: its own words share what that layer says is made or done)."""
    singles = [v for v in out if not v.get("official") and len(v["companies"]) == 1
               and (v.get("by_model") or id(v) not in before or {c.get("ticker") for c in v["companies"]} != before[id(v)])]
    if not singles:
        return out
    for v in singles:
        c = v["companies"][0]
        f = fam(c)
        same = [x for x in out if x is not v and x not in singles and not x.get("official") and x["companies"] and f and main(x["companies"]) == f
                and (fits is None or not v.get("by_model") or fits(c, x))]
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


# R35: a full stop after a legal form or an initial ends no sentence (live: "Qnity Electronics, Inc. is a major provider of materials..." was
# shown as "Qnity Electronics, Inc", and so were Marvell, Skyworks and four more; "the U.S. market")
_NOT_END = r"(?<![A-Z]\.)(?<!\bInc\.)(?<!\bINC\.)(?<!\bCorp\.)(?<!\bLtd\.)(?<!\bCo\.)(?<!\bPvt\.)(?<!\bNo\.)(?<!\bSt\.)(?<!\bDr\.)"
_FIRST = re.compile(r"^(.{20,240}?[.;])" + _NOT_END + r"(?:\s|$)")
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
    return [x.strip() for x in re.split(_NOT_END + r"(?<=[.;])\s+(?=[A-Z“\"(])", t) if x.strip()]


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


# LIVE6-007 (the live Cybersecurity page: "From its own filings: Annual report (20-F)", "Fortinet, Inc." alone, encyclopedia lead sentences
# such as "... is an American multinational corporation headquartered in Sunnyvale, California"): a line is shown as a company's own words
# only when it says what the company does
NO_WORDS = "No description in its own words yet"
_WORK = re.compile(r"\b(?:provid\w*|produc(?:es|ers?|ing|ts?|tion)|manufactur\w*|makes?|making|makers?|sells?|selling|suppl(?:y|ies|ying|iers?)|"
                   r"designs?|designing|develop(?:s|ing|ers?)|operat(?:es|ing|ors?)|offers?|offering|distribut\w*|retail\w*|services?|servic(?:es|ing)|"
                   r"foundr(?:y|ies)|licens\w*|leases?|leasing|lend(?:s|ing|ers?)|insur\w*|earns?|revenues?|customers?|clients?|subscri\w*|platforms?|"
                   r"stores?|brands?|engag(?:ed|es)|build(?:s|ing|ers?)|construct\w*|mines?|mining|miners?|refin\w*|generat(?:es|ing|ors?)|transmi\w*|"
                   r"explor(?:es|ing|ation)|invest(?:s|ing|ments?)|manag(?:es|ing)|deliver\w*|software|hardware|solutions?|products?|systems?|"
                   r"equipment|devices?|vehicles?|drugs?|medicines?|banking|bank|loans?|chemicals?|steel|cement|power|electricity|"
                   r"specializ\w*|specialis\w*|focus(?:es|ed) on|helps?|enables?|protect\w*|secur(?:es|ing))\b", re.I)
_FILING_TITLE = re.compile(r"^(?:annual|quarterly|current|interim|half[- ]yearly)\s+report\b|^(?:form\s+)?(?:10-[kq]|20-f|40-f|8-k|6-k|def\s*14a)\b|"
                           r"^(?:press release|investor presentation|board meeting|outcome of board meeting|shareholding pattern|financial results)\b", re.I)
_LEGAL_WORDS = re.compile(r"\b(?:inc|incorporated|corp|corporation|co|company|ltd|limited|plc|llc|lp|nv|sa|ag|the|holdings?|group)\b\.?", re.I)


# LIVE7A-004 (the live Semiconductors page: TOYO Co.'s "own words" were Toyo Tire's encyclopedia article, Monolithic Power's "an American,
# publicly traded company headquartered in West Palm Beach", AMD's "We also offer ...", Dillard's "It is headquartered in Little Rock ..."):
# an encyclopedia's opening line (a nationality or "multinational" right after "is a", "commonly known as") is not the company's own words,
# nor a line that only adds to what an earlier one said ("also", "In addition") or only says where it is
_ENCYCLOPEDIA = re.compile(r"^[^.]{0,160}?\b(?:is|was)\s+(?:an?|the)\s+(?:[\w&'-]+,?\s+){0,3}?(?:American|British|English|Scottish|Japanese|Taiwanese|"
                           r"(?:South\s+)?Korean|Chinese|Indian|Israeli|Dutch|German|French|Swiss|Canadian|Irish|Swedish|Finnish|Norwegian|Danish|"
                           r"Italian|Spanish|Belgian|Australian|Singaporean|Brazilian|Mexican|Argentine|Bermudian|Luxembourgish|Greek|Cypriot|"
                           r"multinational|publicly[\s-]traded)\b|^[^.]{0,80}?,\s+(?:commonly|also|formerly|better)\s+known\s+as\b", re.I)
_ABBR_DOT = re.compile(r"\b(inc|corp|co|ltd|plc|l\.p|n\.v|s\.a|bhd|pty|ltda|st)\.", re.I)      # "Inc." doesn't end the opening clause
_ADDS = re.compile(r"^(?:in\s+addition\b|additionally\b|also\b|(?:we|it|they|the\s+company)\s+also\b)", re.I)
_WHERE = re.compile(r"^(?:it|we|the\s+company)\s+(?:is|are)\s+(?:headquartered|based|located|domiciled|incorporated)\b", re.I)


def own_words(text, name: str = "") -> str:
    """A company's line as its own words on a page, a CSV or a slide, or "" when it isn't one (LIVE6-007): the titles of its filings (the
    "From its own filings:" lines stand in for a missing description in the checks, never as one), its name alone, or a sentence that says
    where it is and what it is called but not what it does (says no work: provides, makes, sells, operates; its software, its customers);
    LIVE7A-004: an encyclopedia's opening line, a line that only adds to an earlier one, or one that only says where the company is."""
    t = " ".join(str(text or "").split()).strip(" “”\"'")
    if not t or t.startswith("From its own filings:") or _FILING_TITLE.match(t) or _ENCYCLOPEDIA.search(_ABBR_DOT.sub(r"\1", t)) or _ADDS.match(t) or _WHERE.match(t):
        return ""
    words = lambda x: [w for w in re.findall(r"[a-z0-9]+", _LEGAL_WORDS.sub(" ", x.lower()))]        # noqa: E731
    if name and not [w for w in words(t) if w not in set(words(name))]:
        return ""
    return t if _WORK.search(t) else ""


def whole_words(what, about) -> str:
    """A company's line with a word cut by the end of its stored description taken off and an ellipsis in its place (LIVE7A-004: ADI's "a
    broad portfolio of solutio", eBay's "via retail sal": a description is kept to its first EVIDENCE_CHARS characters, so its last word can
    be part of one). Only a line that runs to the very end of a description that doesn't end a sentence is touched."""
    w = " ".join(str(what or "").split())
    a = " ".join(str(about or "").split())
    if not w or not a or " " not in w or a.rstrip(" ”\"'").endswith((".", "!", "?", ")", ";")):
        return w
    norm = lambda x: re.sub(r"\W+", " ", x).strip().lower()        # noqa: E731
    wn, an = norm(w), norm(a)
    if not wn or not an.endswith(wn[-40:]):
        return w
    return w[:w.rfind(" ")].rstrip(" ,;:-–—") + "…"


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
