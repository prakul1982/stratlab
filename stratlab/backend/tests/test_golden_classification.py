"""Golden classification check (R36 lane r1, the owner: "every fix breaks another sector"). Every company of the 14 benchmark themes' live
maps (11 Nov 2026, Release 35: tests/fixtures/themes_live/golden_r36.json, India and US) goes through the same path the dive gives a kept
placement's models (theme_base.refine_kept: theme_check.refine_model and model_confidence) and the placement rule that keeps a company of
another business out of a layer's figures (theme_check.off_industry, by_model), and is compared with its approved way of earning: the live
result, with the corrections below. A rule change that moves any company in any theme fails here; such a change is made on purpose by
editing APPROVED (with its reason), never by loosening the check. Fast: the classification functions only, no network, no AI."""
import json
import pathlib

from app.intel import theme_base as B
from app.intel import theme_check as C

LIVE = pathlib.Path(__file__).parent / "fixtures" / "themes_live"
GOLDEN = json.loads((LIVE / "golden_r36.json").read_text())

# Corrections to the live R35 result, approved on purpose: "theme:symbol" -> (model, how it counts: "" in the layer's figures, "low" left out
# as weakly shown, "other" left out as another business). Each with its reason.
APPROVED = {
    # R36 fix 1: an IDM ("It manufactures a wide range of microelectronics, including the widely used STM8 and STM32 microcontrollers"),
    # whatever "contract manufacturing" its encyclopedia line says
    "semis:STM": ("manufacturing", ""),
    # R36 fix 2: a specialty foundry ("manufactures integrated circuits using specialty process technologies")
    "semis:TSEM": ("contract_manufacturing", ""),
    # R36 fix 3: solar module, tracker and inverter makers filed as semiconductors are another business
    "semis:TE": ("manufacturing", "other"),
    "semis:FTCI": ("manufacturing", "other"),
    "semis:TYGO": ("manufacturing", "other"),
    "semis:MAXNQ": ("manufacturing", "other"),
    "semis:ASTI": ("manufacturing", "other"),
    # R40 (lane s3-r40, the owner's review of the live Release 39 Consumer retail deck, on purpose): propane distributors filed as retail
    # ("retail distribution of propane", "retail marketer of propane") with no stores, apparel or merchandise are another business
    # (theme_check.OFF_INDUSTRY); on a live map they are dropped from the theme and named on its coverage (theme_base.without_off_industry)
    "retail:SPH": ("retail", "other"),
    "retail:FGPR": ("distribution", "other"),
    # R36 fix 4: Amazon sells goods it owns ("products to be sold by us and by third parties"): a retailer with a marketplace beside it
    "retail:AMZN": ("retail", ""),
    # ---- R37 lane r2 (the owner: the remaining misclassifications across all themes) ----
    # fix 1: a bank's or lender's official industry is lending (refine_model); a landlord's own words (mall operator, space let on licence)
    # make it one whatever its official industry
    "realty:HDFCBANK": ('lending', ''),  # official industry 'Private Sector Bank': a bank earns interest on its loans
    "realty:PHOENIXLTD": ('property', ''),          # "…India's largest retail mall operator and offers retail malls and…"
    # fix 3: packaging and test services (OSAT) are contract making in so many words, so counted in the layer's figures
    "semis:AMKR": ('contract_manufacturing', ''),   # "…semiconductor product packaging and test services provider.…"
    "semis:IMOS": ('contract_manufacturing', ''),   # "…of semiconductor assembly and testing services…"
    "semis:ASX": ('contract_manufacturing', ''),    # "…of semiconductor manufacturing services in assembly and testing…"
    # fix 4: a company no answer gave a model takes the one its own words state in so many words (theme_check.stated_model), once its stored
    # description is read (the fixture's "p": its company page's words; theme_routes.reread_weak now reads one never read); each with its words
    "auto:EMMFORCE": ('components', ''),            # "…of different types of Automotive Parts Business Overview: EAL is…"
    "auto:SINTERCOM": ('components', ''),           # "…Sintercom India Ltd manufactures sintered metal components and auto components…"
    "auto:SETCO": ('components', ''),               # "…The company is a Tier I supplier clutches for commercial…"
    "auto:PAVNAIND": ('components', ''),            # "…Locks, Auto Locks and Auto Parts Business Overview: PIL is a…"
    "auto:SNL": ('components', ''),                 # "…1983, SNL Bearings Ltd manufactures and markets antifriction…"
    "auto:IPRINGLTD": ('components', ''),           # "…makes piston rings, precision forgings and differential gears…" (auto components)
    "auto:BGWTATO": ('components', ''),             # "…Autocast Ltd (BAL) manufactures specialised grey /cast iron…"
    "auto:MACPLASQ": ('components', ''),            # "…Machino Plastics Ltd manufactures injection moulding plastic components and moulds/dies Busine
    "auto:BHARATGEAR": ('components', ''),          # "…It manufactures a wide range of Ring Gears…"
    "auto:HINDHARD": ('components', ''),  # "…manufacturer of propeller shafts…" in an auto components industry (ISO "EMS certified" is no contract maker)
    "auto:LAPL": ('components', ''),                # "…a wide range of automotive components and accessories. Business…"
    "auto:GALLARD": ('components', ''),             # "…machining company that manufactures components, assemblies and…"
    "auto:LGBFORGE": ('components', ''),            # "…in 2006, LGB Forge Ltd manufactures Forged and Machined Components Business Overview: LGBFL is
    "auto:URAVIDEF": ('components', ''),            # "…and Technology Ltd manufactures and supplies automotive components and defence equipment…"
    "auto:AUTOPINS": ('components', ''),            # "…Parabolic Springs and Automotive Components under the brand name of…"
    "auto:SALAUTO": ('components', ''),             # "…Overview: SALAL is a manufacturer of automotive components and agricultural…"
    "auto:SAMKRG": ('components', ''),              # "…and Rings Ltd does manufacturing of automobile components Business Overview: SPRL is…"
    "auto:PORWAL": ('components', ''),              # "…Porwal Auto Components Ltd is a Pithampur-based…"
    "auto:AAIL": ('components', ''),                # "…Ltd manufactures automobile parts for heavy commercial…"
    "auto:GSAUTO": ('components', ''),              # "…Ltd deals in the manufacturing of auto components for commercial vehicles.…"
    "auto:SWANAGRO": ('components', ''),            # "…implements and Auto Parts. It is specialized in…"
    "auto:UNIAUTO": ('components', ''),             # "…Autofoundry Ltd does manufacturing and sales of C.I. Castings…"
    "auto:KRANTI": ('components', ''),              # "…Industries Ltd is a manufacturer of precision-machined…"
    "auto:ELFORGE": ('components', ''),             # "…1934, EL Forge Ltd is in the business of manufacture and sale of Steel Forgings.…"
    "auto:JAINEX": ('components', ''),              # "…Jainex Aamcol Ltd is engaged in the manufacturing of Gear Hobs and Cutting…"
    "auto:JAGANLAM": ('components', ''),            # "…Jagan Lamps Ltd manufactures automotive bulbs and…"
    "auto:SIBARAUT": ('components', ''),            # "…in 1983, Sibar Auto Parts Ltd manufactures and sells…"
    "auto:LAKPRE": ('components', ''),              # "…Jain Family. It is a manufacturer and supplier of High Tensile Fasteners…"
    "auto:PRITIKAUTO": ('components', ''),          # "…Auto Industries Ltd manufactures tractor and automobile components Business Overview: Pritika…
    "auto:DOLFIN": ('manufacturing', ''),           # "…Dolfin Rubbers Ltd is engaged in the manufacturing and selling of Auto Tube &…"
    "auto:VAMSHIRU": ('manufacturing', ''),         # "…Vamshi Rubber Ltd is in the business of manufacturing of Tyre Retreading…"
    "auto:EASTRED": ('components', ''),             # "…is in the business of manufacture and sale of tyre treads and associated components. Business 
    "auto:SEVL": ('manufacturing', ''),             # "…2022, Supertech EV Ltd manufactures and sells 2-wheeler EV…"
    "semis:DQ": ('manufacturing', 'other'),         # "…is a Chinese company engaged in the manufacture of monocrystalline silicon…"
    "it:ACESOFT": ('project_services', ''),         # "…data conversion, and technology consulting, serving clients in the…"
    "it:XELPMOC": ('project_services', ''),         # "…Professional and Technical consultancy services Business Overview: XELP…"
    "it:OMEGAIN": ('project_services', ''),         # "…business of providing Information Technology services. Business Overview: {#…"
    "it:AEIM": ('project_services', ''),            # "…developing & providing Software consultancy services and software development.…"
    "it:ODYSSEY": ('project_services', ''),         # "…is in the business of Software development with primary focus on…"
    "it:B2BSOFT": ('software', ''),                 # "…Technology Ltd develops and launches own products (certified by Microsoft)…"
    "it:COSYN": ('project_services', ''),           # "…offers a full range of software outsourcing services from end to end development…"
    "it:INDOCITY": ('lending', ''),                 # "…non-deposit-taking non-banking financial company. It focuses on…"
    "it:SVAMSOF": ('project_services', ''),         # "…is in the business of software development. Business Overview: SSL is…"
    "it:CLIOINFO": ('project_services', ''),        # "…Infotech Ltd offers software development and IT-enabled services…"
    "it:TSPIRITUAL": ('distribution', ''),          # "…Spiritual World Ltd is engaged in the business of trading. Business Overview: TSWL…"
    "it:PFLINFOTC": ('distribution', ''),           # "…PFL Infotech Ltd is in the business of trading Business Overview : PFLIL…"
    "it:VIRGOGLOB": ('telecom_services', ''),  # "…It operates as an Internet Service Provider in India…" (a network service it runs: refine_model, no R37 rule)
    "it:ATISHAY": ('project_services', ''),         # "…1989, Atishay Ltd is a IT Consultancy and Services company which…"
    "it:INTEGHIT": ('project_services', ''),        # "…Hitech Ltd provides Software Development Services Business Overview: IHT is…"
    "it:OMNIAX": ('project_services', ''),          # "…It provides software development training through…"
    "it:PANACHE": ('contract_manufacturing', ''),   # "…is a Bhiwandi-based electronics system design and manufacturing company providing…"
    "defence:CYIENTDLM": ('contract_manufacturing', ''),# "…Cyient DLM is a leading electronics system design and manufacturing player, which provides
    "defence:CENTUM": ('contract_manufacturing', ''),# "…is one of the largest Electronics System Design and Manufacturing (ESDM) companies in India…"
    "defence:CFF": ('manufacturing', ''),           # "…Fluid Control Ltd is in the business of manufacturing, overhaul, repairs, and…"
    "chem:INDIANACRY": ('manufacturing', ''),       # "…Indian Acrylics Ltd is in the business of manufacturing both acrylic fiber and…"
    "chem:POLYLINK": ('manufacturing', ''),         # "…Polymers Ltd is engaged in the manufacture and sale of polymeric…"
    "chem:NOL": ('manufacturing', ''),              # "…National Oxygen Ltd is engaged in the manufacturing of Industrial Gases.…"
    "chem:BHAGGAS": ('manufacturing', ''),          # "…Bhagwati Group. It is in the business of production and supply of liquid…"
    "chem:IGCL": ('manufacturing', ''),             # "…Limited is engaged in manufacturing crop protection products,…"
    "chem:AIMCOPEST": ('manufacturing', ''),        # "…Aimco Pesticides Ltd manufactures technical grade pesticides,…"
    "chem:ADARSHPL": ('manufacturing', ''),         # "…Plant Protect Ltd manufactures agricultural and industrial…"
    "chem:MANORG": ('manufacturing', ''),           # "…Organics Ltd is a manufacturer of Camphor, Resin and Sodium…"
    "chem:LORDSCHLO": ('manufacturing', ''),        # "…Chloro Alkali Ltd manufactures caustic soda and other…"
    "chem:PATELCHEM": ('manufacturing', ''),        # "…Limited (PCSL) is engaged in the manufacturing and exporting of…"
    "chem:ANDHRAPET": ('manufacturing', ''),        # "…Petrochemicals Ltd manufactures and sells Oxo Alcohols…"
    "chem:AGASTYAEN": ('manufacturing', ''),        # "…Chemicals Ltd is in the business of manufacturing of chemicals Business…"
    "chem:NPL": ('manufacturing', ''),              # "…Peroxide Ltd is a manufacturer of Hydrogen Peroxide Business…"
    "chem:PODDARMENT": ('manufacturing', ''),       # "…Poddar Pigments is a manufacturer of Color & Additive Master…"
    "chem:DYNPRO": ('manufacturing', ''),           # "…Dynemic Products is in the business of manufacturing and selling of Dyes & Dye…"
    "chem:CHEMBOND": ('manufacturing', ''),         # "…Chembond Chemicals Ltd manufactures and sells specialty…"
    "chem:INDGELA": ('manufacturing', ''),          # "…& Chemicals Ltd is engaged in manufacturing and export of Ossein,…"
    "chem:ARVEE": ('manufacturing', ''),            # "…Laboratories India Ltd manufactures specialized chemicals…"
    "chem:INDTONER": ('manufacturing', ''),         # "…& Developers Ltd manufactures Compatible Toners Business…"
    "chem:DIAMINESQ": ('manufacturing', ''),        # "…and Chemicals Ltd is in the business of manufacturing and marketing of organic…"
    "chem:DSFCL": ('manufacturing', ''),            # "…DCM Shriram Ltd is a producer of Pharmaceutical…"
    "chem:DAICHI": ('manufacturing', ''),           # "…Karkaria Ltd is in the business of manufacture and sale of Specialty…"
    "chem:ZR2": ('manufacturing', ''),              # "…economy, and produces biofuels, hydrogen and…"
    "chem:VIKASECO": ('manufacturing', ''),         # "…solutions company that manufactures eco-friendly rubber-plastic…"
    "chem:GENUSPRIME": ('property_development', ''),# "…is in the business of real estate development.…"
    "chem:KESARPE": ('manufacturing', ''),          # "…Petroproducts Ltd manufactures and markets Organic…"
    "chem:CHEMCRUX": ('manufacturing', ''),         # "…Enterprises Ltd manufactures and processes bulk drug…"
    "chem:DEEP": ('manufacturing', ''),             # "…Deep Polymers Ltd manufactures Masterbatch and Polymer…"
    "chem:SHLOKKA": ('manufacturing', ''),          # "…Dyes Limited is engaged in the manufacturing of reactive dyes and…"
    "chem:ALKALI": ('manufacturing', ''),           # "…Alkali Metals Ltd is a manufacturer of Sodium Derivatives,…"
    "chem:RITESHIN": ('manufacturing', ''),         # "…International Ltd is engaged in the manufacturing and selling of stearic…"
    "chem:EIKO": ('manufacturing', ''),             # "…Eiko LifeSciences Ltd manufacturing & sells Specialty Chemical and Fine…"
    "chem:ADVPETR-B": ('manufacturing', ''),        # "…Petrochemicals Ltd is in the business of manufacturing and supplier of petroleum…"
    "chem:GAYATRIBI": ('manufacturing', ''),        # "…Bio-Organics Ltd manufactures Starch, its derivatives and…"
    "chem:SHREYASI": ('manufacturing', ''),         # "…Intermediates Ltd is a manufacturer of Phthalocyanine Blue Crude…"
    "chem:CHEMIESYNT": ('manufacturing', ''),       # "…(Vapi) Ltd is in the business of manufacturing Dye Intermediates and…"
    "chem:MEHUL": ('manufacturing', ''),            # "…Mehul Colours Ltd manufactures Colour Masterbatches and…"
    "chem:MIDPOLY": ('manufacturing', ''),          # "…Midland Polymers is engaged in manufactures monaxially oriented…"
    "chem:VIKRAMAR": ('manufacturing', ''),         # "…2021, Vikram Aroma Ltd manufactures chemicals and chemical…"
    "chem:HARLETH": ('manufacturing', ''),          # "…Chemicals Ltd is in the business of manufacturing specialty chemical…"
    "chem:DECOMIC": ('manufacturing', ''),          # "…Dico Mica Ltd is a manufacturer and exporter of laminates Business Overview…"
    "chem:SONALAD": ('manufacturing', ''),          # "…Sonal Adhesives Ltd manufactures adhesive tapes, specialty…"
    "chem:VINYOFL": ('manufacturing', ''),          # "…in 1996, Vinyoflex Ltd manufactures PVC films and sheets…"
    "chem:CAPRO": ('contract_manufacturing', ''),   # "…to use facilities for Contract Manufactur…"
    "chem:PNTKYOR": ('distribution', ''),           # "…Overview: POIL is in the business of trading pharmaceutical products.…"
    "chem:VIVIDIND": ('manufacturing', ''),         # "…Global Industries Ltd manufactures dye intermediates and dye.…"
    "chem:CJGEL": ('manufacturing', ''),            # "…Gleatine Products Ltd manufactures Gelatine and related by…"
    "chem:SRECR": ('manufacturing', ''),            # "…Sreechem Resins Ltd is engaged in production of Resins Business Overview…"
    "chem:KOBO": ('manufacturing', ''),             # "…Business Overview: KBL manufactures Active Pharmaceutical…"
    "chem:PADMAIND": ('distribution', ''),          # "…Overview : PIL is engaged in trading agri goods, commodities,…"
    "chem:IGLFXPL-B": ('manufacturing', ''),        # "…Gulf Industries Ltd manufactures explosives, ammunition, and…"
    "chem:ZSOUTGAS": ('manufacturing', ''),         # "…Overview: TSGL is in the business of production and supply of: a) Medical…"
    "chem:SUDARSHAN": ('manufacturing', ''),        # "…Pharma Industries Ltd manufactures API and Pharmaceutical Items…"
    "metals:VISACHROME": ('commodity_mining', ''),  # "…VISA Steel Ltd does manufacturing of High Carbon Ferro Chrome…"
}
# Where the fixture's one-line description gives less than the words the live read had (its stored description, segments and filings), the
# same path gives these from the one line; kept apart from APPROVED so neither hides the other
ONE_LINE = {
    "semis:NLST": ("fabless", ""),          # "designs and sells": the live read also had its own making words
    "semis:UCTT": ("fabless", ""),          # live unknown; its one line ("developer and supplier of critical subsystems") reads as a designer
    "retail:JL": ("retail", ""),            # live "low"; its one line's own words show the family
    "retail:DBGI": ("retail", ""),
}


def evidence(c) -> str:
    """A fixture company's evidence as the dive builds it (theme_check.model_evidence): its official industry, then its own words (the
    encyclopedia summary where the fixture keeps it, the description its company page showed where the live map had no words for it (R37
    lane r2: what the never-read companies' stored words become once read), and its stored one-line description)."""
    return C.model_evidence(c["i"], " ".join(x for x in (c.get("a"), c.get("p"), c["w"]) if x))


def classify(c) -> tuple[str, str]:
    """(model, how it counts) for a fixture company by the dive's path for a kept placement."""
    ev = evidence(c)
    models, conf = B.refine_kept({c["s"]: c["m"]} if c["m"] else {}, {c["s"]: c["c"]} if c["c"] else {}, lambda s_: ev, [c["s"]])
    model, level = (models or {}).get(c["s"]) or "unknown", (conf or {}).get(c["s"], "")
    if model == "unknown":
        return "unknown", ""
    if C.off_industry(ev):
        return model, "other"
    return model, "low" if level == "low" else ""


def expected(theme: str, c) -> tuple[str, str]:
    k = f"{theme}:{c['s']}"
    if k in APPROVED:
        return APPROVED[k]
    if k in ONE_LINE:
        return ONE_LINE[k]
    return c["m"] or "unknown", "low" if c["c"] == "low" else ""


def company(theme: str, sym: str) -> dict:
    t = next(t for t in GOLDEN["themes"] if t["key"] == theme)
    return next(c for c in t["companies"] if c["s"] == sym)


# ---------- every company of every benchmark theme ----------
def test_golden_covers_the_fourteen_benchmark_themes():
    keys = {t["key"]: t["region"] for t in GOLDEN["themes"]}
    assert keys == {"auto": "IN", "bank": "IN", "semis": "US", "it": "IN", "pharma": "IN", "insurance": "IN", "defence": "IN", "cyber": "US",
                    "chem": "IN", "realty": "IN", "telecom": "IN", "retail": "US", "utilities": "IN", "metals": "IN"}
    n = sum(len(t["companies"]) for t in GOLDEN["themes"])
    assert n >= 1300
    assert sum(1 for t in GOLDEN["themes"] for c in t["companies"] if c["m"]) >= 1050


def test_no_company_in_any_theme_changes_its_way_of_earning_unless_approved():
    moved = []
    for t in GOLDEN["themes"]:
        for c in t["companies"]:
            got, want = classify(c), expected(t["key"], c)
            if got != want:
                moved.append(f"{t['key']}:{c['s']} ({c['n']}): expected {want}, got {got}")
    assert not moved, "a rule change moved these companies (edit APPROVED, with the reason, if on purpose):\n" + "\n".join(moved)


def test_every_approved_correction_is_a_company_of_the_fixture_and_differs_from_live():
    for k, (model, _) in {**APPROVED, **ONE_LINE}.items():
        theme, sym = k.split(":")
        c = company(theme, sym)
        assert (c["m"] or "unknown", "low" if c["c"] == "low" else "") != (APPROVED.get(k) or ONE_LINE[k])
        assert model in C.MODELS


# ---------- the curated anchors (the coordinator's list): each named company's way of earning or family ----------
ANCHORS = {
    ("semis", "Q"): "components", ("semis", "ENTG"): "components",                    # chip materials: ingredient makers, never equipment
    ("semis", "TSM"): "contract_manufacturing", ("semis", "UMC"): "contract_manufacturing",
    ("semis", "GFS"): "contract_manufacturing", ("semis", "TSEM"): "contract_manufacturing",
    ("semis", "STM"): "manufacturing", ("semis", "NXPI"): "manufacturing", ("semis", "ADI"): "manufacturing",
    ("semis", "AMAT"): "manufacturing", ("semis", "LRCX"): "manufacturing", ("semis", "KLAC"): "manufacturing",
    ("semis", "NVDA"): "fabless", ("semis", "AMD"): "fabless", ("semis", "QCOM"): "fabless",
    ("telecom", "JPL"): "telecom_services", ("telecom", "IDEA"): "telecom_services", ("telecom", "BHARTIARTL"): "telecom_services",
    ("retail", "AMZN"): "retail", ("retail", "GCT"): "platform", ("retail", "JMIA"): "platform",
    ("bank", "HDFCBANK"): "lending",
}


def test_anchor_companies_keep_their_way_of_earning():
    for (theme, sym), want in ANCHORS.items():
        model, out = classify(company(theme, sym))
        assert (model, out) == (want, ""), (theme, sym, model, out)


def test_texas_instruments_is_a_maker_of_its_own_chips_never_a_contract_maker():
    # its one line ("developing analog chips and embedded processors") reads as a designer: the making family, in the figures, never contract
    model, out = classify(company("semis", "TXN"))
    assert C.model_family(model) == "making" and model != "contract_manufacturing" and out == ""


def test_it_services_majors_are_in_the_outsourcing_layers_figures():
    for sym in ("WIPRO", "TCS", "INFY"):
        c = company("it", sym)
        model, out = classify(c)
        assert C.model_family(model) == "services" and out == "", (sym, model, out)
        assert c["l"].startswith("Large-scale outsourcing")


def test_solar_makers_are_out_of_every_chip_layer():
    for sym in ("FTCI", "TE"):
        assert classify(company("semis", sym))[1] == "other"
    # chip makers and equipment makers whose words also name solar stay in (Applied Materials: "... and solar products")
    for sym in ("AMAT", "Q", "NVDA", "TSM", "WOLF"):
        assert classify(company("semis", sym))[1] == ""
