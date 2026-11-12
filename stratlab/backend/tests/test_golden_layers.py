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
    "chem:ARVEE": ('Specialty and performance chemicals', "its own words now state its model, so it leaves Other for its family's layer"),
    "chem:INDTONER": ('Specialty and performance chemicals', "its own words now state its model, so it leaves Other for its family's layer"),
    "chem:DIAMINESQ": ('Specialty and performance chemicals', "its own words now state its model, so it leaves Other for its family's layer"),
    "chem:DSFCL": ('Specialty and performance chemicals', "its own words now state its model, so it leaves Other for its family's layer"),
    "chem:DAICHI": ('Specialty and performance chemicals', "its own words now state its model, so it leaves Other for its family's layer"),
    "chem:ZR2": ('Specialty and performance chemicals', "its own words now state its model, so it leaves Other for its family's layer"),
    "chem:VIKASECO": ('Specialty and performance chemicals', "its own words now state its model, so it leaves Other for its family's layer"),
    "chem:KESARPE": ('Specialty and performance chemicals', "its own words now state its model, so it leaves Other for its family's layer"),
    "chem:CHEMCRUX": ('Specialty and performance chemicals', "its own words now state its model, so it leaves Other for its family's layer"),
    "chem:DEEP": ('Specialty and performance chemicals', "its own words now state its model, so it leaves Other for its family's layer"),
    "chem:SHLOKKA": ('Specialty and performance chemicals', "its own words now state its model, so it leaves Other for its family's layer"),
    "chem:ALKALI": ('Specialty and performance chemicals', "its own words now state its model, so it leaves Other for its family's layer"),
    "chem:RITESHIN": ('Specialty and performance chemicals', "its own words now state its model, so it leaves Other for its family's layer"),
    "chem:EIKO": ('Specialty and performance chemicals', "its own words now state its model, so it leaves Other for its family's layer"),
    "chem:ADVPETR-B": ('Specialty and performance chemicals', "its own words now state its model, so it leaves Other for its family's layer"),
    "chem:GAYATRIBI": ('Specialty and performance chemicals', "its own words now state its model, so it leaves Other for its family's layer"),
    "chem:SHREYASI": ('Specialty and performance chemicals', "its own words now state its model, so it leaves Other for its family's layer"),
    "chem:CHEMIESYNT": ('Specialty and performance chemicals', "its own words now state its model, so it leaves Other for its family's layer"),
    "chem:MEHUL": ('Specialty and performance chemicals', "its own words now state its model, so it leaves Other for its family's layer"),
    "chem:MIDPOLY": ('Specialty and performance chemicals', "its own words now state its model, so it leaves Other for its family's layer"),
    "chem:VIKRAMAR": ('Specialty and performance chemicals', "its own words now state its model, so it leaves Other for its family's layer"),
    "chem:HARLETH": ('Specialty and performance chemicals', "its own words now state its model, so it leaves Other for its family's layer"),
    "chem:DECOMIC": ('Specialty and performance chemicals', "its own words now state its model, so it leaves Other for its family's layer"),
    "chem:SONALAD": ('Specialty and performance chemicals', "its own words now state its model, so it leaves Other for its family's layer"),
    "chem:VINYOFL": ('Specialty and performance chemicals', "its own words now state its model, so it leaves Other for its family's layer"),
    "chem:PNTKYOR": ('Distribution and trading', "its own words now state its model, so it leaves Other for its family's layer"),
    "chem:VIVIDIND": ('Specialty and performance chemicals', "its own words now state its model, so it leaves Other for its family's layer"),
    "chem:CJGEL": ('Specialty and performance chemicals', "its own words now state its model, so it leaves Other for its family's layer"),
    "chem:SRECR": ('Specialty and performance chemicals', "its own words now state its model, so it leaves Other for its family's layer"),
    "chem:KOBO": ('Specialty and performance chemicals', "its own words now state its model, so it leaves Other for its family's layer"),
    "chem:PADMAIND": ('Distribution and trading', "its own words now state its model, so it leaves Other for its family's layer"),
    "chem:IGLFXPL-B": ('Specialty and performance chemicals', "its own words now state its model, so it leaves Other for its family's layer"),
    "chem:ZSOUTGAS": ('Specialty and performance chemicals', "its own words now state its model, so it leaves Other for its family's layer"),
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
    "semis:QRVO": ('Makers of their own products', 'an RF chip company ("a semiconductor company"): R39 (lane s1-fit): moved from "Other" into the split\'s "Makers of their own products"; that layer no longer joins the map\'s "Memory and logic chip fabricators" whole for sharing its model: only companies whose own words share two of that layer\'s words join'),
    "semis:VIAV": ('Makers of their own products', 'network test and measurement: R39 (lane s1-fit): moved from "Other" into the split\'s "Makers of their own products"; that layer no longer joins the map\'s "Memory and logic chip fabricators" whole for sharing its model: only companies whose own words share two of that layer\'s words join'),
    "semis:AAOI": ('Makers of their own products', 'fiber-optic networking products: R39 (lane s1-fit): moved from "Other" into the split\'s "Makers of their own products"; that layer no longer joins the map\'s "Memory and logic chip fabricators" whole for sharing its model: only companies whose own words share two of that layer\'s words join'),
    "semis:IPGP": ('Makers of their own products', 'fiber lasers: R39 (lane s1-fit): moved from "Other" into the split\'s "Makers of their own products"; that layer no longer joins the map\'s "Memory and logic chip fabricators" whole for sharing its model: only companies whose own words share two of that layer\'s words join'),
    "semis:LASR": ('Makers of their own products', 'high-power lasers: R39 (lane s1-fit): moved from "Other" into the split\'s "Makers of their own products"; that layer no longer joins the map\'s "Memory and logic chip fabricators" whole for sharing its model: only companies whose own words share two of that layer\'s words join'),
    "semis:PLAB": ('Makers of their own products', 'photomasks: R39 (lane s1-fit): moved from "Other" into the split\'s "Makers of their own products"; that layer no longer joins the map\'s "Memory and logic chip fabricators" whole for sharing its model: only companies whose own words share two of that layer\'s words join'),
    "semis:KOPN": ('Makers of their own products', 'microdisplays and optics: R39 (lane s1-fit): moved from "Other" into the split\'s "Makers of their own products"; that layer no longer joins the map\'s "Memory and logic chip fabricators" whole for sharing its model: only companies whose own words share two of that layer\'s words join'),
    "semis:LPTH": ('Makers of their own products', 'optics (its words name no product): R39 (lane s1-fit): moved from "Other" into the split\'s "Makers of their own products"; that layer no longer joins the map\'s "Memory and logic chip fabricators" whole for sharing its model: only companies whose own words share two of that layer\'s words join'),
    "semis:STM": ('Makers of their own products', 'its stored words call it "a semiconductor contract manufacturing and design company": R39 (lane s1-fit): moved from "Other" into the split\'s "Makers of their own products"; that layer no longer joins the map\'s "Memory and logic chip fabricators" whole for sharing its model: only companies whose own words share two of that layer\'s words join'),
    "retail:PLBY": ('Other', 'R39 (lane s1-fit): no words of its own in this fixture, and "Apparel and fashion retail chains", the largest, holds none of its industry (Miscellaneous Retail): it stays in Other (licensing, digital content, lingerie: not an apparel chain)'),
}

# R40 (lane s3-r40, the owner's review of the live Release 39 decks, on purpose): companies the theme's official industry brought in whose own
# words describe another business are dropped from the theme, never placed in "Other" (theme_base.without_off_industry): solar makers filed
# as semiconductors, propane distributors filed as retail. "theme:symbol" -> why
DROPPED = {**{f"semis:{s_}": "solar products and no chips, filed as semiconductors: another business" for s_ in ("TE", "TYGO", "FTCI", "MAXNQ", "DQ", "ASTI")},
           **{f"retail:{s_}": "propane distribution and no stores, filed as retail: another business" for s_ in ("SPH", "FGPR")},
           **{f"retail:{s_}": 'filed under retail, its own words describe another business (pawnbroking, IT services to business, a blank-check company, a bank, payments or travel): R43, theme_check.OFF_INDUSTRY' for s_ in ('CDW', 'EZPW', 'FBCD', 'FCFS', 'IPSI', 'NSIT', 'TMS')}}
# lane d1 (R43, the outside review of the live Release 41 decks, approved on purpose): the moves its rules make on this older fixture,
# each with why; kept apart from APPROVED_LAYER so the earlier lanes' checks of their own moves stand
_D1_NARROW = 'R43 (lane d1, approved on purpose): the largest layer of its family took it by its industry alone, but that layer\'s own name states a kind of business its own words don\'t say, nor any word of its description, and it is no catch-all of its family (by_model.home_of `narrow`): the layer of its family it fits, else "Other"'
_D1_GROUP = 'R43 (lane d1, approved on purpose): the largest\'s name doesn\'t describe it (by_model.home_of `narrow`); with the like of it of its official industry in "Other" it makes a layer of that industry (INDUSTRY_GROUP_MIN)'
D1 = {
    'auto:ASAHIINDIA': ('Other', _D1_NARROW),
    'auto:STUDDS': ('Two-wheeler makers', _D1_NARROW),
    'bank:TMB': ('High-yield retail and microfinance lenders', _D1_NARROW),
    'defence:JAYKAY': ('Other', _D1_NARROW),
    'defence:SIGMAADV': ('Other', _D1_NARROW),
    'defence:UNIMECH': ('Specialty materials and forgings', _D1_NARROW),
    'metals:20MICRONS': ('Other', _D1_NARROW),
    'metals:GOACARBON': ('Other', _D1_NARROW),
    'metals:MMP': ('Other', _D1_NARROW),
    'retail:BWMX': ('Other', _D1_NARROW),
    'retail:HEPS': ('Other', _D1_NARROW),
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
            want = None if k in DROPPED else D1[k][0] if k in D1 else APPROVED_LAYER[k][0] if k in APPROVED_LAYER else c["e"]          # lane d1: D1 (updated on purpose)
            if got.get(c["s"]) != want:
                moved.append(f"{k} ({c['n']}): expected {want!r}, got {got.get(c['s'])!r}")
    assert not moved, "a rule change moved these companies to another layer (edit APPROVED_LAYER, with the reason, if on purpose):\n" + "\n".join(moved)


def test_every_approved_move_is_a_company_of_the_fixture_and_differs_from_r36():
    every = {f"{t['key']}:{c['s']}": c for t in LAYERS["themes"] for c in t["companies"]}
    for k, (layer, why) in APPROVED_LAYER.items():
        assert k in every and every[k]["e"] != layer and why, k


def test_the_moves_are_the_intended_ones_only():
    by_theme = {}
    for k in APPROVED_LAYER:
        by_theme.setdefault(k.split(":")[0], set()).add(k.split(":")[1])
    assert set(by_theme) == {"auto", "chem", "semis", "pharma", "realty", "retail"}
    assert by_theme["retail"] == {"CPNG", "W", "VIPS", "FCFS", "EZPW", "SVV", "SPH", "CIMG", "FGPR", "PLBY"}     # R38 lane s1-fit: PLBY (on purpose)
    assert by_theme["semis"] == {"Q", "ENTG", "AXTI", "ALMU"} | {"QRVO", "VIAV", "AAOI", "IPGP", "LASR", "PLAB", "KOPN", "LPTH", "STM"} \
        and by_theme["realty"] == {"PROZONER"} and by_theme["pharma"] == {"ADVENZYMES"}      # R38 lane s1-fit added the nine makers (on purpose)
    every = {f"{t['key']}:{c['s']}": c for t in LAYERS["themes"] for c in t["companies"]}
    for th in ("auto", "chem"):        # companies leaving "Other" because their own words now state their model, nothing else
        assert all(every[f"{th}:{s}"]["e"] == "Other" and not every[f"{th}:{s}"]["m"] for s in by_theme[th]), th
