"""Golden layer check (R37 lane r2, the owner: "no theme may get worse"): every company of the 14 benchmark themes' live maps (11 Nov 2026,
Release 35: tests/fixtures/themes_live/layers_r36.json, 1,621 companies, India and US) is placed again from the map's kept answer
(theme_base.place_rest with its refine_kept and by_model, no AI) and its layer, or "Other", is compared with the one the R36 rules gave the
same map and words ("e"), with the moves below approved on purpose. A rule change that moves any company to another layer fails here; such a
change is made on purpose by editing APPROVED_LAYER (with its reason), never by loosening the check. The halves of a layer split by market
value count as one layer (which half a company falls in follows the companies counted). A company the map placed in a layer whose model
only its own words state stays in that layer (left out of its figures as another way of earning), so the classification check's model and
this check's layer are read together."""
import json
import pathlib
import re

from app.intel import theme_base as B

LIVE = pathlib.Path(__file__).parent / "fixtures" / "themes_live"
LAYERS = json.loads((LIVE / "layers_r36.json").read_text())

# "theme:symbol" -> (its layer now, why it moved)
APPROVED_LAYER = {
    "auto:EMMFORCE": ('Component and systems suppliers', "its own words now state its model, so it leaves Other for its family's layer"),
    "auto:SINTERCOM": ('Component and systems suppliers', "its own words now state its model, so it leaves Other for its family's layer"),
    "auto:SETCO": ('Component and systems suppliers', "its own words now state its model, so it leaves Other for its family's layer"),
    "auto:PAVNAIND": ('Component and systems suppliers', "its own words now state its model, so it leaves Other for its family's layer"),
    "auto:SNL": ('Component and systems suppliers', "its own words now state its model, so it leaves Other for its family's layer"),
    "auto:IPRINGLTD": ('Component and systems suppliers', "its own words now state its model, so it leaves Other for its family's layer"),
    "auto:BGWTATO": ('Component and systems suppliers', "its own words now state its model, so it leaves Other for its family's layer"),
    "auto:MACPLASQ": ('Component and systems suppliers', "its own words now state its model, so it leaves Other for its family's layer"),
    "auto:BHARATGEAR": ('Component and systems suppliers', "its own words now state its model, so it leaves Other for its family's layer"),
    "auto:HINDHARD": ('Component and systems suppliers', "its own words now state its model, so it leaves Other for its family's layer"),
    "auto:LAPL": ('Component and systems suppliers', "its own words now state its model, so it leaves Other for its family's layer"),
    "auto:GALLARD": ('Component and systems suppliers', "its own words now state its model, so it leaves Other for its family's layer"),
    "auto:LGBFORGE": ('Component and systems suppliers', "its own words now state its model, so it leaves Other for its family's layer"),
    "auto:URAVIDEF": ('Component and systems suppliers', "its own words now state its model, so it leaves Other for its family's layer"),
    "auto:AUTOPINS": ('Component and systems suppliers', "its own words now state its model, so it leaves Other for its family's layer"),
    "auto:SALAUTO": ('Component and systems suppliers', "its own words now state its model, so it leaves Other for its family's layer"),
    "auto:SAMKRG": ('Component and systems suppliers', "its own words now state its model, so it leaves Other for its family's layer"),
    "auto:PORWAL": ('Component and systems suppliers', "its own words now state its model, so it leaves Other for its family's layer"),
    "auto:AAIL": ('Component and systems suppliers', "its own words now state its model, so it leaves Other for its family's layer"),
    "auto:GSAUTO": ('Component and systems suppliers', "its own words now state its model, so it leaves Other for its family's layer"),
    "auto:SWANAGRO": ('Component and systems suppliers', "its own words now state its model, so it leaves Other for its family's layer"),
    "auto:UNIAUTO": ('Component and systems suppliers', "its own words now state its model, so it leaves Other for its family's layer"),
    "auto:KRANTI": ('Component and systems suppliers', "its own words now state its model, so it leaves Other for its family's layer"),
    "auto:ELFORGE": ('Component and systems suppliers', "its own words now state its model, so it leaves Other for its family's layer"),
    "auto:JAINEX": ('Component and systems suppliers', "its own words now state its model, so it leaves Other for its family's layer"),
    "auto:JAGANLAM": ('Component and systems suppliers', "its own words now state its model, so it leaves Other for its family's layer"),
    "auto:SIBARAUT": ('Component and systems suppliers', "its own words now state its model, so it leaves Other for its family's layer"),
    "auto:LAKPRE": ('Component and systems suppliers', "its own words now state its model, so it leaves Other for its family's layer"),
    "semis:Q": ('Parts, component and ingredient makers', 'materials maker: a layer of its own, the packaging and test services now counted as contract makers'),
    "semis:ENTG": ('Parts, component and ingredient makers', 'materials maker: a layer of its own, the packaging and test services now counted as contract makers'),
    "semis:AXTI": ('Parts, component and ingredient makers', 'materials maker: a layer of its own, the packaging and test services now counted as contract makers'),
    "semis:ALMU": ('Parts, component and ingredient makers', 'materials maker: a layer of its own, the packaging and test services now counted as contract makers'),
    "pharma:ADVENZYMES": ('Other', 'an enzyme maker (Biotechnology): no layer holds its industry or its words (not generic formulations); stays in Other'),
    "chem:PODDARMENT": ('Specialty and performance chemicals', "its own words now state its model, so it leaves Other for its family's layer"),
    "chem:DYNPRO": ('Specialty and performance chemicals', "its own words now state its model, so it leaves Other for its family's layer"),
    "chem:CHEMBOND": ('Specialty and performance chemicals', "its own words now state its model, so it leaves Other for its family's layer"),
    "chem:INDGELA": ('Specialty and performance chemicals', "its own words now state its model, so it leaves Other for its family's layer"),
    "chem:INDTONER": ('Specialty and performance chemicals', "its own words now state its model, so it leaves Other for its family's layer"),
    "chem:DAICHI": ('Specialty and performance chemicals', "its own words now state its model, so it leaves Other for its family's layer"),
    "chem:VIKASECO": ('Specialty and performance chemicals', "its own words now state its model, so it leaves Other for its family's layer"),
    "chem:KESARPE": ('Specialty and performance chemicals', "its own words now state its model, so it leaves Other for its family's layer"),
    "chem:CHEMCRUX": ('Specialty and performance chemicals', "its own words now state its model, so it leaves Other for its family's layer"),
    "chem:DEEP": ('Specialty and performance chemicals', "its own words now state its model, so it leaves Other for its family's layer"),
    "chem:SHLOKKA": ('Specialty and performance chemicals', "its own words now state its model, so it leaves Other for its family's layer"),
    "chem:ADVPETR-B": ('Specialty and performance chemicals', "its own words now state its model, so it leaves Other for its family's layer"),
    "chem:SHREYASI": ('Specialty and performance chemicals', "its own words now state its model, so it leaves Other for its family's layer"),
    "chem:CHEMIESYNT": ('Specialty and performance chemicals', "its own words now state its model, so it leaves Other for its family's layer"),
    "chem:MEHUL": ('Specialty and performance chemicals', "its own words now state its model, so it leaves Other for its family's layer"),
    "chem:HARLETH": ('Specialty and performance chemicals', "its own words now state its model, so it leaves Other for its family's layer"),
    "chem:PNTKYOR": ('Distribution and trading', "its own words now state its model, so it leaves Other for its family's layer"),
    "chem:VIVIDIND": ('Specialty and performance chemicals', "its own words now state its model, so it leaves Other for its family's layer"),
    "chem:CJGEL": ('Specialty and performance chemicals', "its own words now state its model, so it leaves Other for its family's layer"),
    "chem:PADMAIND": ('Distribution and trading', "its own words now state its model, so it leaves Other for its family's layer"),
    "chem:IGLFXPL-B": ('Specialty and performance chemicals', "its own words now state its model, so it leaves Other for its family's layer"),
    "chem:SUDARSHAN": ('Specialty and performance chemicals', "its own words now state its model, so it leaves Other for its family's layer"),
    "realty:PROZONER": ('Residential developers', 'a developer ("Build & Sell"), leaving the mall owners\' layer, which now holds landlords only (Phoenix Mills\' words: mall operator, space on licence)'),
    "retail:CPNG": ('Online direct-to-consumer retailers', 'an online seller ("online retail"), to the online retailers: every one of them of its industry, and their words'),
    "retail:W": ('Online direct-to-consumer retailers', 'an online seller ("sells furniture and home goods online"), to the online retailers'),
    "retail:VIPS": ('Online direct-to-consumer retailers', 'an online seller ("online discount sales"), to the online retailers'),
    "retail:FCFS": ('Other', 'a pawnshop chain: no layer of the map holds its industry or its business, so it stays in Other'),
    "retail:EZPW": ('Other', 'a pawnshop operator: no layer holds its industry or its business, so it stays in Other'),
    "retail:SVV": ('Other', 'a thrift store operator: no layer holds its industry or its business, so it stays in Other'),
    "retail:SPH": ('Other', 'a propane distributor ("retail marketer of propane"): fuel distribution is not apparel retail; stays in Other'),
    "retail:CIMG": ('Other', 'a distributor (coffee and other goods in Asia): no layer holds its industry or business; stays in Other'),
    "retail:FGPR": ('Other', 'a propane distributor ("retail distribution of propane"): stays in Other'),
    # R38 lane s1-fit (RULES 39): a company the split moves goes to the layer it fits, never the largest by default
    "auto:BOSCHLTD": ("Component and systems suppliers", "R39: fuel injection systems and auto parts, not tyres: the component suppliers' layer is all of its industry (left out of its figures as another way of earning)"),
    "auto:ASAHIINDIA": ("Component and systems suppliers", "R39: automotive glass, not tyres: the component suppliers' layer is all of its industry (left out of its figures as another way of earning)"),
    "auto:STUDDS": ("Other", "R39: a helmet and motorcycle accessories maker: its words name two-wheelers, its industry another layer: no layer by default, stays in Other"),
    "auto:VELJAN": ("Component and systems suppliers", "R39: hydraulic pumps, motors and valves, not tyres: the component suppliers' layer is all of its industry (left out of its figures)"),
    "bank:TMB": ("Lenders", "R39: a bank whose industry is most of three layers and whose words name none: the layer of how it earns, not the largest bank layer by default (this replay reads the map's smaller half as moved)"),
    "bank:KTKBANK": ("Lenders", "R39: a bank whose industry is most of three layers and whose words name none: the layer of how it earns, not the largest bank layer by default (this replay reads the map's smaller half as moved)"),
    "bank:DCBBANK": ("Lenders", "R39: a bank whose industry is most of three layers and whose words name none: the layer of how it earns, not the largest bank layer by default (this replay reads the map's smaller half as moved)"),
    "bank:CSBBANK": ("Lenders", "R39: a bank whose industry is most of three layers and whose words name none: the layer of how it earns, not the largest bank layer by default (this replay reads the map's smaller half as moved)"),
    "bank:DHANBANK": ("Lenders", "R39: a bank whose industry is most of three layers and whose words name none: the layer of how it earns, not the largest bank layer by default (this replay reads the map's smaller half as moved)"),
    "semis:QRVO": ("Makers of their own products", "R39: its industry is most of several layers and its words fit none twice: the layer named by how it earns, not the memory and logic fabricators by default"),
    "semis:VIAV": ("Makers of their own products", "R39: its industry is most of several layers and its words fit none twice: the layer named by how it earns, not the memory and logic fabricators by default"),
    "semis:AAOI": ("Makers of their own products", "R39: its industry is most of several layers and its words fit none twice: the layer named by how it earns, not the memory and logic fabricators by default"),
    "semis:IPGP": ("Makers of their own products", "R39: its industry is most of several layers and its words fit none twice: the layer named by how it earns, not the memory and logic fabricators by default"),
    "semis:LASR": ("Makers of their own products", "R39: its industry is most of several layers and its words fit none twice: the layer named by how it earns, not the memory and logic fabricators by default"),
    "semis:PLAB": ("Makers of their own products", "R39: its industry is most of several layers and its words fit none twice: the layer named by how it earns, not the memory and logic fabricators by default"),
    "semis:KOPN": ("Makers of their own products", "R39: its industry is most of several layers and its words fit none twice: the layer named by how it earns, not the memory and logic fabricators by default"),
    "semis:LPTH": ("Makers of their own products", "R39: its industry is most of several layers and its words fit none twice: the layer named by how it earns, not the memory and logic fabricators by default"),
    "semis:STM": ("Makers of their own products", "R39: its industry is most of several layers and its words fit none twice: the layer named by how it earns, not the memory and logic fabricators by default"),
    "it:XCHANGING": ("Other", "R39: \"an Information Technology services provider\": its words name no layer and no one layer holds most of its industry: stays in Other"),
    "it:TRIGYN": ("Digital engineering and consulting projects", "R39: consulting and systems integration: that layer holds its industry and shares its words (consulting), not engineering R&D"),
    "it:TERASOFT": ("Other", "R39: public-sector technology systems: no layer holds its industry and shares its words: stays in Other"),
    "it:ESDS": ("Digital engineering and consulting projects", "R39: cloud, managed services and data centres: that layer holds its industry and shares its words (cloud, data), not engineering R&D"),
    "it:TECHNVISN": ("Other", "R39: \"IT products and services\": its words name no layer twice and no layer is mostly of its industry: stays in Other"),
    "it:SOFTTECH": ("Other", "R39: IT design, development and servicing: its words name no layer twice and no layer is mostly of its industry: stays in Other"),
    "it:VIRINCHI": ("Other", "R39: \"IT products and services\": its words name no layer twice and no layer is mostly of its industry: stays in Other"),
    "it:DIGISPICE": ("Other", "R39: \"Information and Communication Technology business\": its words name no layer and no layer is mostly of its industry: stays in Other"),
    "pharma:AARTIPHARM": ("Makers of their own products", "R39: its industry (Pharmaceuticals) is most of several layers and its words name none of them (not export generics): a layer named by how it earns"),
    "pharma:KOPRAN": ("Makers of their own products", "R39: its industry (Pharmaceuticals) is most of several layers and its words name none of them (not export generics): a layer named by how it earns"),
    "pharma:ANUHPHR": ("Makers of their own products", "R39: its industry (Pharmaceuticals) is most of several layers and its words name none of them (not export generics): a layer named by how it earns"),
    "pharma:HIKAL": ("Makers of their own products", "R39: its industry (Pharmaceuticals) is most of several layers and its words name none of them (not export generics): a layer named by how it earns"),
    "pharma:BROOKS": ("Makers of their own products", "R39: its industry (Pharmaceuticals) is most of several layers and its words name none of them (not export generics): a layer named by how it earns"),
    "pharma:VIYASH": ("Makers of their own products", "R39: its industry (Pharmaceuticals) is most of several layers and its words name none of them (not export generics): a layer named by how it earns"),
    "pharma:HESTERBIO": ("Makers of their own products", "R39: its industry (Pharmaceuticals) is most of several layers and its words name none of them (not export generics): a layer named by how it earns"),
    "pharma:AMRUTANJAN": ("Makers of their own products", "R39: its industry (Pharmaceuticals) is most of several layers and its words name none of them (not export generics): a layer named by how it earns"),
    "pharma:SIGACHI": ("Makers of their own products", "R39: its industry (Pharmaceuticals) is most of several layers and its words name none of them (not export generics): a layer named by how it earns"),
    "pharma:AMBALALSA": ("Makers of their own products", "R39: its industry (Pharmaceuticals) is most of several layers and its words name none of them (not export generics): a layer named by how it earns"),
    "defence:UNIMECH": ("Makers of their own products", "R39: precision engineering: its industry is most of several layers and its words fit none: a layer named by how it earns, not electronics by default"),
    "defence:JAYKAY": ("Makers of their own products", "R39: additive manufacturing and 3D printing: its industry is most of several layers and its words fit none: a layer named by how it earns"),
    "defence:SIGMAADV": ("Makers of their own products", "R39: aerospace and defence manufacturing: its industry is most of several layers and its words fit none: a layer named by how it earns"),
    "cyber:GEN": ("Other", "R39: its words say only \"software company\" and its industry is most of several layers: no layer by default (alone in a layer of its way of earning, so Other)"),
    "chem:LINDEINDIA": ("Fluorochemicals and refrigerants", "R39: industrial and medical gases: the layer where the map keeps the industrial gas makers, holding its industry and sharing its words (gases)"),
    "chem:UPL": ("Other", "R39: an agrochemical maker: the one layer of its industry is named for contract making and \"Specialty and performance chemicals\" holds neither its industry nor its words: stays in Other"),
    "chem:SUMICHEM": ("Other", "R39: an agrochemical maker: the one layer of its industry is named for contract making and \"Specialty and performance chemicals\" holds neither its industry nor its words: stays in Other"),
    "chem:BAYERCROP": ("Other", "R39: an agrochemical maker: the one layer of its industry is named for contract making and \"Specialty and performance chemicals\" holds neither its industry nor its words: stays in Other"),
    "chem:DEEPAKFERT": ("Basic organic intermediates", "R39: fertilisers and petrochemicals: that layer converts petrochemical feedstocks and holds its industry"),
    "chem:SPLPETRO": ("Basic organic intermediates", "R39: a petrochemical maker (polystyrene): that layer converts petrochemical feedstocks and holds its industry"),
    "chem:GNFC": ("Makers of their own products", "R39: its words say nothing of what it makes and its industry is spread over the map: a layer named by how it earns"),
    "chem:RAIN": ("Other", "R39: carbon, cement and advanced materials: no layer holds its industry and shares its words: stays in Other"),
    "chem:DHANUKA": ("Other", "R39: an agrochemical maker: the one layer of its industry is named for contract making and \"Specialty and performance chemicals\" holds neither its industry nor its words: stays in Other"),
    "chem:ELLEN": ("Fluorochemicals and refrigerants", "R39: an industrial gases maker: the layer where the map keeps the industrial gas makers, holding its industry and sharing its words (gases)"),
    "chem:RALLIS": ("Other", "R39: an agrochemical maker: the one layer of its industry is named for contract making and \"Specialty and performance chemicals\" holds neither its industry nor its words: stays in Other"),
    "chem:BEPL": ("Other", "R39: ABS and engineering resins: no layer holds its industry and shares its words (not niche additives or dyes): stays in Other"),
    "chem:BHAGCHEM": ("Other", "R39: an agrochemical maker: the one layer of its industry is named for contract making and \"Specialty and performance chemicals\" holds neither its industry nor its words: stays in Other"),
    "chem:GSPCROP": ("Other", "R39: an agrochemical maker: the one layer of its industry is named for contract making and \"Specialty and performance chemicals\" holds neither its industry nor its words: stays in Other"),
    "chem:INSECTICID": ("Other", "R39: an agrochemical maker: the one layer of its industry is named for contract making and \"Specialty and performance chemicals\" holds neither its industry nor its words: stays in Other"),
    "chem:BHARATRAS": ("Other", "R39: an agrochemical maker: the one layer of its industry is named for contract making and \"Specialty and performance chemicals\" holds neither its industry nor its words: stays in Other"),
    "chem:IPL": ("Other", "R39: an agrochemical maker: the one layer of its industry is named for contract making and \"Specialty and performance chemicals\" holds neither its industry nor its words: stays in Other"),
    "chem:MOL": ("Other", "R39: an agrochemical maker: the one layer of its industry is named for contract making and \"Specialty and performance chemicals\" holds neither its industry nor its words: stays in Other"),
    "chem:ASTEC": ("Other", "R39: an agrochemical maker: the one layer of its industry is named for contract making and \"Specialty and performance chemicals\" holds neither its industry nor its words: stays in Other"),
    "chem:ANDHRSUGAR": ("Chlor-alkali and soda ash producers", "R39: its words name chlor-alkali products, and that layer holds its industry"),
    "chem:TNPETRO": ("Basic organic intermediates", "R39: a petrochemical products maker: that layer converts petrochemical feedstocks and holds its industry"),
    "chem:DHARMAJ": ("Other", "R39: an agrochemical maker: the one layer of its industry is named for contract making and \"Specialty and performance chemicals\" holds neither its industry nor its words: stays in Other"),
    "chem:ADVANCE": ("Other", "R39: an agrochemical maker: the one layer of its industry is named for contract making and \"Specialty and performance chemicals\" holds neither its industry nor its words: stays in Other"),
    "chem:KOTHARIPET": ("Basic organic intermediates", "R39: a petrochemical maker (polyisobutylene): that layer converts petrochemical feedstocks and holds its industry"),
    "chem:PASUPTAC": ("Other", "R39: acrylic fibre and film: no layer holds its industry and shares its words: stays in Other"),
    "chem:HERANBA": ("Other", "R39: an agrochemical maker: the one layer of its industry is named for contract making and \"Specialty and performance chemicals\" holds neither its industry nor its words: stays in Other"),
    "chem:BESTAGRO": ("Other", "R39: an agrochemical maker: the one layer of its industry is named for contract making and \"Specialty and performance chemicals\" holds neither its industry nor its words: stays in Other"),
    "chem:SHIVALIK": ("Other", "R39: an agrochemical maker: the one layer of its industry is named for contract making and \"Specialty and performance chemicals\" holds neither its industry nor its words: stays in Other"),
    "chem:ARVEE": ("Basic organic intermediates", "R39: polymer modifiers and contrast-media intermediates: that layer holds its industry and its name's word (intermediates)"),
    "chem:DIAMINESQ": ("Basic organic intermediates", "R39: organic chemical compounds: that layer holds its industry and its name's word (organic)"),
    "chem:DSFCL": ("Basic organic intermediates", "R39: pharmaceutical intermediates: that layer holds its industry and its name's word (intermediates)"),
    "chem:ZR2": ("Makers of their own products", "R39: its words name none of the layers and its industry is spread over the map: a layer named by how it earns, never the largest by default (an ethanol and bioenergy maker)"),
    "chem:ALKALI": ("Chlor-alkali and soda ash producers", "R39: sodium (alkali metal) derivatives: that layer holds its industry and its name's word (alkali)"),
    "chem:RITESHIN": ("Makers of their own products", "R39: its words name none of the layers and its industry is spread over the map: a layer named by how it earns, never the largest by default (stearic and fatty acids)"),
    "chem:EIKO": ("Basic organic intermediates", "R39: organic and inorganic fine chemicals and pharma intermediates: that layer holds its industry and its words (organic, intermediates)"),
    "chem:GAYATRIBI": ("Basic organic intermediates", "R39 (weak: one word, \"Bio-Organics\" in its own name, and the layer holds its industry): a starch maker in \"Basic organic intermediates\"; only this replay moves it (the live R37 map placed it itself, layers_r38 keeps it there)"),
    "chem:MIDPOLY": ("Basic organic intermediates", "R39 (weak: one word, \"organic product marks\", and the layer holds its industry): a polypropylene film maker; only this replay moves it (the live R37 map placed it itself, layers_r38 keeps it there)"),
    "chem:VIKRAMAR": ("Basic organic intermediates", "R39: aromatic and petrochemical-derived chemicals: that layer holds its industry and its words (aromatic, organic, petrochemical)"),
    "chem:DECOMIC": ("Makers of their own products", "R39: its words name none of the layers and its industry is spread over the map: a layer named by how it earns, never the largest by default (laminates)"),
    "chem:SONALAD": ("Makers of their own products", "R39: its words name none of the layers and its industry is spread over the map: a layer named by how it earns, never the largest by default (adhesive tapes and emulsions)"),
    "chem:VINYOFL": ("Makers of their own products", "R39: its words name none of the layers and its industry is spread over the map: a layer named by how it earns, never the largest by default (PVC films and sheets)"),
    "chem:SRECR": ("Basic organic intermediates", "R39: phenol-based resins: that layer (phenol among its products) holds its industry"),
    "chem:KOBO": ("Makers of their own products", "R39: its words name none of the layers and its industry is spread over the map: a layer named by how it earns, never the largest by default (fermentation-based pharmaceutical ingredients)"),
    "chem:ZSOUTGAS": ("Fluorochemicals and refrigerants", "R39: an industrial gas maker: the layer where the map keeps the gas makers, holding its industry and sharing its words (gases)"),
    "telecom:TIKONA": ("Other", "R39: telecom equipment: one word shared with the equipment makers and its industry another layer's: no layer by default, stays in Other"),
    "telecom:PACEDIGITK": ("Tower infrastructure", "R39: telecom infrastructure: no makers' layer holds its industry or its words; the layer of its industry takes it (left out of its figures as another way of earning)"),
    "retail:HEPS": ("Online direct-to-consumer retailers", "R39: an online seller: the online retailers' layer is most of its industry (Catalog & Mail-Order Houses), not apparel chains"),
    "retail:BWMX": ("Online direct-to-consumer retailers", "R39: a catalogue (Catalog & Mail-Order Houses) seller: the online retailers' layer is most of its industry, not apparel chains"),
    "retail:PLBY": ("Other", "R39: licensing, digital subscriptions and lifestyle brands: no layer holds its industry and shares its words: stays in Other"),
    "utilities:TRIVENIPT": ("Other", "R39: its only words are a filing's title: no layer holds its industry and shares its words: stays in Other"),
    "metals:JSL": ("Integrated steelmaking", "R39: stainless steel flat products: that layer holds its industry and its words (steel, flat), not ferro alloys"),
    "metals:MMP": ("Aluminium and copper smelting", "R39: aluminium powder: that layer is most of its industry (Aluminium) and shares its word, not ferro alloys"),
    "metals:20MICRONS": ("Coal, iron ore and mineral mining", "R39: industrial minerals: that layer holds its industry and its words (industrial minerals), not ferro alloys"),
    "metals:GOACARBON": ("Coal, iron ore and mineral mining", "R39: calcined petroleum coke: the layer of its industry (Industrial Minerals), mostly of it and holding most of it; not ferro alloys"),
    "metals:MANAKALUCO": ("Other", "R39: secondary aluminium products: no metal processors' layer holds its industry and shares two of its words: stays in Other"),
    "metals:HINDALUMI": ("Other", "R39: aluminium products and power: no metal processors' layer holds its industry and shares two of its words: stays in Other"),
}


def replay_theme(t) -> dict:
    """{symbol: its layer, or "Other"} when the live map is placed again from its kept answer (theme_base.place_rest, no AI): the map's own
    layers with the companies the kept placement left there, every company the split moved (and the "Other" group's) back in one official
    group, each company's words its other words and its one line; a layer split by market value counted as one."""
    own, rest, models, conf, tags, words = [], [], {}, {}, {}, {}
    by_x = {}
    for c in t["companies"]:
        by_x.setdefault(c["x"], []).append(c)
    for i, v in enumerate(t["layers"]):
        stay = []
        for c in by_x.get(i, []):
            words[c["s"]] = " ".join(x for x in (c.get("a"), c["w"]) if x)
            row = {"ticker": c["s"], "name": c["n"], "what": c["w"], "industry": c["i"], "cap": c["cap"], "basis": c["b"]}
            if c["m"]:
                models[c["s"]], conf[c["s"]] = c["m"], c["c"]
            if c.get("g"):
                tags[c["s"]] = c["g"]
            (rest if v.get("official") or v.get("by_model") or c.get("mv") else stay).append(row)
        if not v.get("official") and not v.get("by_model"):
            own.append({"layer": v["layer"], "description": v.get("description") or "", "companies": stay})
    m = {"sector": t["theme"], "value_chain": own + [{"layer": "Official", "official": True, "basis": "industry", "companies": rest}]}
    kept = {"assign": {c["ticker"]: {"layer": "", "by": "ai"} for c in rest}, "models": models, "model_confidence": conf, "model_tags": tags}
    out, _ = B.place_rest(m, t["theme"], lambda s: words.get(s) or "", ask=None, kept=kept)
    return {c["ticker"]: ("Other" if v.get("official") else re.sub(r"( \((?:larger|smaller)\))+$", "", v["layer"]))
            for v in out["value_chain"] for c in v["companies"]}


def test_the_fixture_holds_the_fourteen_benchmark_maps():
    assert [t["key"] for t in LAYERS["themes"]] == ["auto", "bank", "semis", "it", "pharma", "insurance", "defence", "cyber", "chem", "realty",
                                                    "telecom", "retail", "utilities", "metals"]
    assert sum(len(t["companies"]) for t in LAYERS["themes"]) >= 1600


def test_no_company_in_any_theme_changes_its_layer_unless_approved():
    moved = []
    for t in LAYERS["themes"]:
        got = replay_theme(t)
        for c in t["companies"]:
            k = f"{t['key']}:{c['s']}"
            want = APPROVED_LAYER[k][0] if k in APPROVED_LAYER else c["e"]
            if got[c["s"]] != want:
                moved.append(f"{k} ({c['n']}): expected {want!r}, got {got[c['s']]!r}")
    assert not moved, "a rule change moved these companies to another layer (edit APPROVED_LAYER, with the reason, if on purpose):\n" + "\n".join(moved)


def test_every_approved_move_is_a_company_of_the_fixture_and_differs_from_r36():
    every = {f"{t['key']}:{c['s']}": c for t in LAYERS["themes"] for c in t["companies"]}
    for k, (layer, why) in APPROVED_LAYER.items():
        assert k in every and every[k]["e"] != layer and why, k


def test_the_moves_are_the_intended_ones_only():
    r37 = {k: v for k, v in APPROVED_LAYER.items() if not v[1].startswith("R39")}
    r39 = {k: v for k, v in APPROVED_LAYER.items() if v[1].startswith("R39")}
    by_theme = {}
    for k in r37:
        by_theme.setdefault(k.split(":")[0], set()).add(k.split(":")[1])
    assert set(by_theme) == {"auto", "chem", "semis", "pharma", "realty", "retail"}
    assert by_theme["retail"] == {"CPNG", "W", "VIPS", "FCFS", "EZPW", "SVV", "SPH", "CIMG", "FGPR"}
    assert by_theme["semis"] == {"Q", "ENTG", "AXTI", "ALMU"} and by_theme["realty"] == {"PROZONER"} and by_theme["pharma"] == {"ADVENZYMES"}
    every = {f"{t['key']}:{c['s']}": c for t in LAYERS["themes"] for c in t["companies"]}
    for th in ("auto", "chem"):        # companies leaving "Other" because their own words now state their model, nothing else
        assert all(every[f"{th}:{s}"]["e"] == "Other" and not every[f"{th}:{s}"]["m"] for s in by_theme[th]), th
    # R38 lane s1-fit (updated on purpose): 96 companies the split had put in the largest layer of their family now go to the layer they
    # fit, a layer named by how they earn, or "Other"; none goes to the largest layer by default, and none was placed by the map itself
    assert len(r39) == 96
    assert {k.split(":")[0] for k in r39} == {"auto", "bank", "semis", "it", "pharma", "defence", "cyber", "chem", "telecom", "retail", "utilities",
                                              "metals"}
    for k, (layer, _) in r39.items():
        t = next(t for t in LAYERS["themes"] if t["key"] == k.split(":")[0])
        c = every[k]
        v = t["layers"][c["x"]]
        assert c.get("mv") or v.get("official") or v.get("by_model"), k
        assert layer != c["e"], k
