"""Exact replays of the live placement (Release 39, lane s2-exact; the owner, after Releases 37-38: fixes proven on replays of the live maps
did not hold on the live site, whose placement read stored descriptions and a kept answer the replays did not have).

The inputs are what GET /research/theme-dive/placement-inputs (Release 39a) returned for the 14 benchmark themes on 12 Nov 2026 under the
Release 39 rules (RULES 41; refreshed by lane s3-r40 from the first read, under Release 38.1, RULES 40): tests/fixtures/themes_live/inputs_r39/<theme>.json, each the checked map as served (every company's layer,
model and whether the split moved it), the kept placement answer and the rules version it was kept under, and each company's stored
description as theme_routes.placed reads it (None: no words). Real estate and Telecom were still being re-checked when read
(placements.checked False); they are replayed like the others. The replay of Release 39's code on them gave every company its exact live
layer, but Hind Aluminium (still unexplained, recovered.json) and the three layer names the split's renames hold in Metals (name-only
knock-ons of it: the answer kept under RULES 41 is not carried, and its renames are keyed by the layers' members).

The replay feeds theme_base.place_rest exactly what theme_routes.placed fed it on live: the AI map's own layers (their names and descriptions
before any rename) with the companies the map named itself, every company of the theme's official industries in its official group (with
theme_base.with_base's order and fields: no words of its own, largest first), the kept answer as `kept`, each company's stored description as
`about_of`, and no AI. What the endpoint doesn't return is in inputs_r39/recovered.json, each item with how it was recovered (the layer the
map named a company in, found from the kept answer's layer-name signature; a layer's own description before the split renamed it; one
company's stored industry path; one company's description read after the served map). The layers split into "(larger)"/"(smaller)" halves
are made by the split itself, never fed in."""
import itertools
import json
import pathlib
import re

from app.intel import theme_base as B

INPUTS = pathlib.Path(__file__).parent / "fixtures" / "themes_live" / "inputs_r39"
THEMES = ("auto", "bank", "semis", "it", "pharma", "insurance", "defence", "cyber", "chem", "realty", "telecom", "retail", "utilities", "metals")
RECOVERED = json.loads((INPUTS / "recovered.json").read_text())
_HALF = re.compile(r" \((?:larger|smaller)\)$")
_SPLIT_MARKS = ("placed", "fit", "moved", "single", "model", "model_tags", "model_confidence", "model_out")
_CACHE: dict = {}


def live(key: str) -> dict:
    if key not in _CACHE:
        d = json.loads((INPUTS / f"{key}.json").read_text())
        _CACHE[key] = d.get("data", d)
    return _CACHE[key]


def _is_map_layer(v) -> bool:
    """One of the AI map's own layers as served (a half of one split by market value included); not an official group, the "Other"
    group, a layer the placement added (`by_place`) or one the split made by how its companies earn."""
    return not v.get("official") and not v.get("by_place") and not v.get("industry_group") and not (v.get("by_model") and not v.get("scale"))


def pre_map(d: dict, origin: dict | None = None, description: dict | None = None) -> dict:
    """The map as theme_routes.placed handed it to place_rest on live (with_base's output)."""
    origin, description = origin or {}, description or {}
    kept = d["kept"]
    after_split = {x["name"]: k for k, x in ((kept.get("model_names") or {}).get("rename") or {}).items() if x.get("name")}
    placed_as = {x["name"]: k for k, x in (kept.get("rename") or {}).items() if x.get("name")}

    def map_name(v) -> tuple[str, str]:
        """(the map's own name of a served layer, its name when the split saw it)."""
        name = _HALF.sub("", v["layer"])
        seen = after_split.get(name, name)
        return (v["was"] if v.get("was") and seen == name else placed_as.get(seen, seen)), seen
    layers: dict = {}
    for v in d["value_chain"]:
        if not _is_map_layer(v):
            continue
        own, seen = map_name(v)
        if own not in layers:
            if seen != _HALF.sub("", v["layer"]):          # renamed after the split: the description the split saw
                text = description.get(seen) or ((kept.get("rename") or {}).get(own) or {}).get("description") or ""
            else:
                text = v.get("description") or ""
            layers[own] = {"layer": own, "description": description.get(own, text), "companies": []}
    official: dict = {}
    for v in d["value_chain"]:
        for c in v["companies"]:
            if c.get("placed"):                            # placed after the map: in its official group until place_rest places it
                official.setdefault(c["basis"], []).append({"ticker": c["ticker"], "name": c.get("name"), "what": "", "verified": False,
                                                            "base": True, "basis": c["basis"], "industry": c.get("industry") or "",
                                                            "cap": c.get("cap")})
                continue
            if _is_map_layer(v) and not c.get("moved"):
                own = map_name(v)[0]
            else:
                own = origin[c["ticker"]]                  # named by the map, moved by the split: recovered
                layers.setdefault(own, {"layer": own, "description": description.get(own, ""), "companies": []})
            layers[own]["companies"].append({k: x for k, x in c.items() if k not in _SPLIT_MARKS})
    vc = list(layers.values())
    industries = d["placements"]["industries"]
    for ind in industries:
        cos = sorted((c for c in official.get("industry", []) if B.key(c["industry"]) == B.key(ind)), key=lambda c: (-(c.get("cap") or 0), c["ticker"]))
        if cos:
            vc.append({"layer": B.plain_industry(ind), "description": "", "official": True, "basis": "industry", "companies": cos})
    named = sorted(official.get("list", []), key=lambda c: (-(c.get("cap") or 0), c["ticker"]))
    if named:
        vc.append({"layer": "Named in the theme's list", "description": "", "official": True, "basis": "list", "companies": named})
    # c1 (R44, inputs read from the live Release 43): a company the map named in a sub-theme only (basis "added") is placed after the map
    # like the theme's own (d1): it is fed as a sub-theme's company, as theme_routes.placed fed it
    subs = sorted(official.get("added", []), key=lambda c: (-(c.get("cap") or 0), c["ticker"]))
    return {"sector": d["theme"], "value_chain": vc, **({"sub_themes": [{"name": "sub-theme", "companies": subs}]} if subs else {})}


def replay(key: str, origin: dict | None = None, **kw) -> tuple[dict, dict]:
    """(the placed map, the answer as worked out) when the live map is placed again from its live inputs, no AI."""
    d = live(key)
    facts = RECOVERED["facts"].get(key) or {}
    words = {**d["evidence"], **(RECOVERED["evidence"].get(key) or {})}
    m = pre_map(d, RECOVERED["origin"].get(key) if origin is None else origin, RECOVERED["description"].get(key))
    return B.place_rest(m, d["theme"], lambda s: words.get(s), ask=None, kept=d["kept"], facts_of=lambda s: facts.get(s) or {}, **kw)


def layers_of(vc) -> dict:
    return {c["ticker"]: v["layer"] for v in vc for c in v["companies"]}


_ROLL = "{} kept answer was carried from earlier rules"
_OFF = ("\"Off-price, dollar and discount store chains\", the largest layer of its family, holds none of its industry and shares none of its "
        "words; the only layer holding its industry, \"Online retailers and marketplaces\", has a name stating another way of earning (it never "
        "takes a retailer), and the largest is no catch-all of the family: no longer the largest by default, so \"Other\" (no layer of the "
        "family shares two of its words with one in its name)")
_KIN = ("an auto component maker the answer read as a maker of its own products, leaving the component suppliers' layer the map placed it in: "
        "no makers' layer is mostly of its industry (\"Tyre manufacturers\", the largest, holds none of it) and the component layer is, so it "
        "stays there, listed but left out of the layer's figures as another way of earning")
_SPLIT = ("placed with the chip designers, moved out by the split by model into \"Makers of their own products\"; that layer joins "
          "\"Semiconductor equipment\" only with companies whose words fit it (two of its words), and its own share none (or one), so it keeps "
          "the makers' layer, never the equipment one")
_ASKED = ("the AI's placement answer put it in \"{}\" with no model; its model, asked apart from the placement afterwards (\"reasked\"), "
          "no longer moves it out: it stays, left out of the layer's figures as another way of earning")

# "theme:symbol" -> (its layer now, why it moved), against the exact replay of Release 39's code (RULES 41 = the live layer); halves as one
# layer. Release 39's own moves (lane s2-exact: Bosch, Asahi India Glass, Qorvo, Netlist, ASE, Hikal, Brooks, 17 retailers to "Other") are
# live since, so are in the inputs.
_ONLINE = ("leaving \"Other\" (R41: the online layer's map name \"Online marketplaces\" states a platform's way of earning, so it took no "
           "retailer): \"Online retailers and marketplaces\" now states both ways of earning, holds its industry (catalogue and mail-order "
           "houses) and its own words say \"online\" or \"e-commerce\", what the layer's name says (R40)")
# R40's moves (nine online sellers into "Online retailers and marketplaces", _ONLINE) are live since and so in the inputs read from the live
# Release 41 (d1, updated on purpose): the moves below are against the exact replay of RULES 42, the live layer
_STAYS = ("the map's own pick for this layer, moved out by the split for a way of earning no layer of the map has (it alone of the movers): "
          "R43 keeps it in the map's layer, listed but out of its figures as another way of earning, never \"Other\"")
_NARROW = ("an Other-mover the largest layer of its family took by its industry alone: that layer's own name states a kind of business "
           "(\"off-price\", \"dollar\", \"discount\" / \"ferro alloy\") its own words don't say, nor any word of its description, and it "
           "is no catch-all of its family (R43, by_model.home_of `narrow`)")
_GROUP = ("{}; with the chains of its official industry in \"Other\" (no model, own words that say they sell in stores) it makes a layer of "
          "that industry, {} or more of them (R43, by_model INDUSTRY_GROUP_MIN)")
# d1's moves (RULES 43) are live since Release 43, so in the inputs read from it (c1, 13 Nov, updated on purpose): APPROVED restarts
# against the exact replay of RULES 43 (the live layer); c1's own moves (RULES 44, theme_base.from_other: the outside review of the live
# Release 43 decks, "improve coverage only with evidence; never force") are below with their reasons
_C1_IND = ("no words of its own and no way of earning shown: placed by its official industry ({}) in the one layer whose name that "
           "industry's name says, which holds most of the theme's companies of that industry with words (c1, R44, theme_base.from_other 1)")
_C1_IN_GROUP = ("no words of its own and no way of earning shown: placed by its official industry ({}) in the layer made of that industry "
                "and named by it (c1, R44, theme_base.from_other 1)")
_C1_WORDS = ("in \"Other\" with its way of earning shown (retail): its own words ({}) say what the layer's name says, the one layer of its "
             "way of earning that does (c1, R44, theme_base.from_other 2: \"apparel\" says \"clothing\", SAME_KIND)")
_C1_GROUP = ("of the official industry {}, {}; with the others of that industry left in \"Other\" or moved by how they earn alone into a "
             "layer whose name their words don't say, they make a layer of that industry: 5 or more, 3 or more with words of their own, "
             "none of that industry with words of that way of earning elsewhere (c1, R44, theme_base.from_other 3)")
_FROM_MAKERS = "moved by the split from \"Other\" into \"Makers of their own products\", a group named only by how its companies earn"
_FROM_OTHER = "in \"Other\" with no words of its own"
_CL48_MAP = ("the map (or its answer) placed it in {}; read as a retailer, the split moved it into \"Off-price and dollar stores\", the "
             "largest layer of the retailers, which holds none of its industry and whose name (\"off-price\", \"dollar\") its words ({}) "
             "don't say; they don't say its map layer's name either, nor two words of any retailers' layer: \"Other\" (cl48, R47, "
             "by_model.home_of)")
_CL48_OFF = ("in \"Other\" with its way of earning shown (retail): \"branched off\" no longer says \"off-price\" (a compound of a short "
             "word is one word, as name_says reads it), so neither \"Off-price and dollar stores\" (its words say neither its name nor its "
             "description) nor from_other 2 takes it there by chance; its words (\"plus-size clothing\", \"store\") say most of \"Family "
             "clothing stores\", the one layer of its way of earning that they do (cl48, R47, theme_base.from_other 2)")
_GL50_FIT = ("placed by its words alone in {}, whose name its own words don't say (more than half of a part of it) nor share a word of "
             "its kind with the layer's description, its official industry ({}) not the layer's: no layer's name its first sentence says, "
             "no layer naming its industry: \"Other\" (gl50, R50, theme_base.definition_fit)")
APPROVED: dict = {
    "realty:SIL": ("Other", _GL50_FIT.format("\"Rent-yielding commercial property trusts\"", "Real Estate related services")),
    **{f"it:{s_}": ("Software products and SaaS platforms", _C1_IND.format("Software Products")) for s_ in ("ACESOFT", "SOTEFIN")},
    "defence:LAXMIPATI": ("Naval shipbuilding", _C1_IND.format("Ship Building & Allied Services")),
    "metals:SIZEMASTER": ("Zinc, lead and silver mining and smelting", _C1_IND.format("Zinc")),
    "retail:CAHO": ("Catalog and mail-order houses", _C1_IN_GROUP.format("Retail-Catalog & Mail-Order Houses")),
    "retail:PLCE": ("Family clothing stores", _C1_IN_GROUP.format("Retail-Family Clothing Stores")),
    "retail:ZUMZ": ("Family clothing stores", _C1_WORDS.format("\"a specialty clothing store\"")),
    "retail:TLYS": ("Family clothing stores", _C1_WORDS.format("\"a specialty retailer of casual apparel\"")),
    "retail:DLTH": ("Family clothing stores", _C1_WORDS.format("\"workwear, casual wear, outdoor apparel\"")),
    # Utilities: the cable makers and the electrical equipment makers, apart from each other by their official industry. cv47 (R46): these
    # 52 are also exactly the moves against the live Release 46 placement (inputs_r46/utilities.json, with each company's stored facts), where
    # the titles of its filings had been read as a company's own words ("From its own filings" said "Makers of their own products"):
    # test_cv47_coverage holds each of them to its entry here; no other company of the 14 themes' live Release 46 inputs moves
    **{f"utilities:{s_}": ("Electrical cables", _C1_GROUP.format("Cables - Electricals", _FROM_MAKERS)) for s_ in (
        "CMICABLES", "CORDSCABLE", "DYCL", "FINCABLES", "KEI", "KSHINTL", "LASERPOWER", "LUMINO", "PARACABLES", "POLYCAB", "QUADFUTURE",
        "UNIVCABLES")},
    **{f"utilities:{s_}": ("Electrical cables", _C1_GROUP.format("Cables - Electricals", _FROM_OTHER)) for s_ in (
        "DEFRAIL", "JDCABLES", "JOHNSONCAB", "SUSAN", "SYSTEMATIC", "ULTRACAB")},
    **{f"utilities:{s_}": ("Heavy electrical equipment", _C1_GROUP.format("Heavy Electrical Equipment", _FROM_MAKERS)) for s_ in (
        "AARTECH", "ABB", "ATLANTAELE", "AZAD", "BBL", "BHEL", "CGPOWER", "ELECON", "EXICOM", "INDOTECH", "INOXWIND", "KANOHAR",
        "KARAMTARA", "MARSONS", "NEUEON", "POWERINDIA", "SCHNEIDER", "SIEMENS", "SKIPPER", "SUZLON", "SWELECTES", "TARIL", "TDPOWERSYS",
        "THERMAX", "TRITURBINE", "VOLTAMP", "WAAREEINDO")},
    **{f"utilities:{s_}": ("Heavy electrical equipment", _C1_GROUP.format("Heavy Electrical Equipment", _FROM_OTHER)) for s_ in (
        "ACCORDTS", "JYOTI", "KPGEL", "RAKSAN", "STARDELTA", "UVDRHOR", "VANS")},
    # Metals: the ferro alloy makers (ferro chrome, manganese and silicon alloys), out of the mining layer, which they don't mine for
    **{f"metals:{s_}": ("Ferro alloys", _C1_GROUP.format("Ferro & Silica Manganese", "moved by the split into \"Mining of coal and iron "
                                                         "ore\" by how it earns (commodity making) alone: its words name ferro alloys, "
                                                         "not coal or iron ore")) for s_ in (
        "IMPEXFERRO", "MAITHANALL", "SHYAMCENT", "VISACHROME")},
    "metals:IMFA": ("Ferro alloys", _C1_GROUP.format("Ferro & Silica Manganese", "in \"Other\", its words a ferro chrome maker's")),
    **{f"metals:{s_}": ("Ferro alloys", _C1_GROUP.format("Ferro & Silica Manganese", _FROM_OTHER)) for s_ in (
        "CHROME", "FACORALL", "INDSILHYD", "NAGPI", "NCML")},
    # Metals: the makers of aluminium products (powder, profiles, foil, secondary aluminium), apart from the smelters, which keep their layer
    **{f"metals:{s_}": ("Aluminium", _C1_GROUP.format("Aluminium", "moved by the split into \"Metal pipe, tube and product fabricators\" "
                                                      "by how it earns (metal processing) alone: its words name aluminium products, not "
                                                      "pipes or tubes")) for s_ in ("ARFIN", "MAANALU", "MANAKALUCO")},
    **{f"metals:{s_}": ("Aluminium", _C1_GROUP.format("Aluminium", "in \"Other\", its words an aluminium product maker's")) for s_ in (
        "HINDALUMI", "MMP")},
    **{f"metals:{s_}": ("Aluminium", _C1_GROUP.format("Aluminium", _FROM_OTHER)) for s_ in (
        "BMAL", "JIVIAL", "KANISHK", "MAITRI", "MSAFE", "PALCO", "PGFOILQ", "SACHEMT", "SUDAI")},
    # cl48 (R47, the outside review of the live Release 46 Consumer retail deck: a designer of branded athletic apparel in "Off-price, dollar
    # and discount store chains"): a company's layer rests on its own words or official industry, never on the largest layer by default or
    # on a word shared by chance (test_cl48_class holds the same rule on the live Release 46 inputs)
    "retail:LULU": ("Other", _CL48_MAP.format("\"Brand owners selling direct and wholesale\"", "athletic apparel and footwear")),
    "retail:REAL": ("Other", _CL48_MAP.format("\"Online marketplaces\"", "luxury consignment and resale")),
    "retail:CURV": ("Family clothing stores", _CL48_OFF),
}
# R40: "theme:symbol" -> why it is no longer in the theme (theme_base.without_off_industry): a company the theme's official industry brought
# in whose own words describe another business is dropped, never placed in "Other", and named on the theme's coverage (placements.off_industry)
_SOLAR = "filed under semiconductors, its own words describe solar {} and no chips: another business"
_FUEL = "filed under retail, its own words describe propane distribution and no stores, apparel or merchandise: another business"
_PAWN = "filed under retail, its own words describe {}: another business (R43, theme_check.OFF_INDUSTRY)"
DROPPED = {**{f"retail:{s_}": _PAWN.format(what) for s_, what in (
               ("FCFS", "pawn stores (loans against pledged goods)"), ("EZPW", "pawn shops"), ("CDW", "IT services to business and government"),
               ("NSIT", "business-to-business IT"), ("TMS", "a blank check company"), ("FBCD", "a commercial bank"),
               ("IPSI", "digital payment solutions"), ("WBUY", "a travel platform"))},
           "semis:DQ": _SOLAR.format("polysilicon"), "semis:TE": _SOLAR.format("modules"), "semis:TYGO": _SOLAR.format("power electronics"),
           "semis:FTCI": _SOLAR.format("trackers"), "semis:SUNE": _SOLAR.format("installations"), "semis:ASTI": _SOLAR.format("panels"),
           "semis:MAXNQ": _SOLAR.format("panels"), "retail:SPH": _FUEL, "retail:FGPR": _FUEL,
           # c1 (R44, the outside review of the live Release 43 Consumer retail deck: 29 of 90 in "Other"; theme_check.OFF_INDUSTRY)
           **{f"retail:{s_}": _PAWN.format(what).replace("R43", "c1, R44") for s_, what in (
               ("VIPZ", "an online mobile sportsbook"), ("MDEX", "a live broadcast network"), ("ESSI", "enterprise software"),
               ("AMZE", "a virtual reality concert production company"), ("LIVE", "a diversified holding company"))}}
# the owner's review of Release 38: these companies' layers (or "Other") on the exact replay, whatever a later rule changes; R40 (the owner's
# review of Release 39, updated on purpose): Chewy into the online layer; Ferrellgas, Suburban Propane and T1 Energy out of the theme (None)
REGRESSION = {"auto:BOSCHLTD": "Component and systems suppliers", "auto:ASAHIINDIA": "Component and systems suppliers",
              "retail:CHWY": "Catalog and mail-order houses",          # c1 (updated on purpose): its layer on the live Release 43
              "retail:FGPR": None, "retail:SPH": None,
              "semis:MU": "Makers of their own products", "semis:INTC": "Makers of their own products",
              "semis:QRVO": "Makers of their own products", "semis:GFS": "Contract chip foundries", "semis:TE": None,
              # d1 (the outside review of the live Release 41 decks, updated on purpose): Arm, Fortinet, the apparel chains, the pawnbrokers
              "semis:ARM": "Design software and IP licensing", "cyber:FTNT": "Network security appliances and subscriptions",
              "retail:GAP": "Family clothing stores", "retail:AEO": "Family clothing stores", "retail:BKE": "Family clothing stores",
              "retail:DDS": "Other", "retail:FCFS": None, "retail:CDW": None, "realty:PENINLAND": "Residential developers",
              # c1 (updated on purpose): on the live Release 43 the map's two makers' layers hold none of the map's own picks, so the cable
              # and equipment makers were one layer the split named by how they earn; c1 (R44) puts the cable makers in a layer of their
              # official industry, apart from the equipment makers (theme_base.from_other 3)
              "utilities:PARACABLES": "Electrical cables", "utilities:BHEL": "Heavy electrical equipment",
              "metals:MAITHANALL": "Ferro alloys", "retail:VIPZ": None, "retail:LIVE": None}


def joined(name: str, v: dict | None = None) -> str:
    return "Other" if (v or {}).get("official") else _HALF.sub("", name)


# live layer names a change approved here takes away, and those it adds (halves as one), by theme
RENAMED: dict = {}          # c1 (updated on purpose): d1's renames are live since Release 43
ADDED: dict = {"utilities": {"Electrical cables", "Heavy electrical equipment"}, "metals": {"Ferro alloys", "Aluminium"}}      # c1 (R44)


def name_only(d: dict) -> dict:
    """{a live layer's name: the name it had before the split renamed it}: in a theme where one company's live layer is unexplained by the
    returned inputs (recovered.json), the split's renames, keyed by the layers' members, are lost with it on a replay whose answer is not
    carried: name-only knock-ons, never a company's move."""
    return {x["name"]: k for k, x in ((d["kept"].get("model_names") or {}).get("rename") or {}).items() if x.get("name")}


def now_layers(key: str) -> dict:
    """{symbol: layer, or "Other"} on the exact replay under the rules as they are now (RULES 42 carries every live kept answer, kept under
    41 or before), the halves of a layer split by market value as one."""
    out, _ = replay(key, carried=live(key)["kept_version"] != B.RULES)
    return {c["ticker"]: joined(v["layer"], v) for v in out["value_chain"] for c in v["companies"]}


def test_the_replay_reproduces_the_live_layer_of_every_company_but_the_approved_moves():
    """Step 1 (lane s2-exact): Release 38.1's code (RULES 40) on the first inputs gave every company of the 14 themes its live layer by its
    exact name (halves and the split's renames included), but Hind Aluminium (recovered.json "unexplained"). Step 1 (lane s3-r40): Release
    39's code (RULES 41) on the refreshed inputs did the same, but Hind Aluminium and, in Metals, the split's three renames lost with it
    (`name_only`: the answer kept under 41 is not carried there). Since, every company still has its live layer (the halves as one) but the
    moves in APPROVED, each with its reason; a rule change that moves any other company fails here, and is made on purpose by editing
    APPROVED with its reason, never by loosening the check. Every live layer name is kept but those an approved change takes away
    (RENAMED) or adds (ADDED)."""
    diffs = {}
    for key in THEMES:
        d = live(key)
        want = {c["ticker"]: joined(v["layer"], v) for v in d["value_chain"] for c in v["companies"]}
        got = now_layers(key)
        gone = {k.split(":")[1] for k in DROPPED if k.startswith(f"{key}:")}
        # d1 (updated on purpose): the inputs read from the live Release 41 (RULES 42) no longer hold the companies Release 40 dropped as
        # another business (the live placement dropped them before serving), so a dropped company is absent from the inputs or dropped
        # by the replay, named on the coverage either way
        assert set(want) - gone == set(got), key
        odd = RECOVERED["unexplained"].get(key) or {}
        back = name_only(d) if odd else {}
        for s_ in set(want) - gone:
            ok = APPROVED.get(f"{key}:{s_}", (want[s_],))[0]
            if got[s_] != ok and s_ not in odd and back.get(ok) != got[s_]:
                diffs[f"{key}:{s_}"] = (want[s_], got[s_])
        for s_ in odd:
            assert got[s_] != want[s_]          # still unexplained by the returned inputs: kept listed, never silently matched
        out, _ = replay(key, carried=d["kept_version"] != B.RULES)
        named = {x["ticker"] for p_ in ((out.get("placements") or {}), d["placements"]) for x in p_.get("off_industry") or []}
        assert named == gone, key      # named on the coverage
        names = {joined(v["layer"]) for v in out["value_chain"] if v["companies"]}
        was = {joined(v["layer"]) for v in d["value_chain"] if v["companies"]}
        allowed = (was | {back[x] for x in was if x in back}) - RENAMED.get(key, set()) | ADDED.get(key, set())
        assert was - set(back) - RENAMED.get(key, set()) <= names <= allowed, key
    assert diffs == {}
    for k, (layer, why) in APPROVED.items():
        key, s_ = k.split(":")
        assert why and now_layers(key)[s_] == layer != joined(next(v["layer"] for v in live(key)["value_chain"] for c in v["companies"] if c["ticker"] == s_)), k


def test_the_owners_regression_list_holds_on_the_exact_replay():
    for k, layer in REGRESSION.items():
        key, s_ = k.split(":")
        assert now_layers(key).get(s_) == layer, k
    semis = now_layers("semis")
    assert not {"MU", "INTC", "SKHY", "QRVO"} & {s_ for s_, x in semis.items() if x == "Semiconductor equipment"}


def test_a_carried_answer_keeps_the_split_s_names_and_none_is_asked_again():
    """R41: the live answers kept under RULES 40 or before are carried as they are; the layers the split renamed keep the answer's names when
    the split reshapes them again (with no AI, as a page waiting reads it, and in the background check: only a reshaped layer the answer
    never named is asked). d1 (updated on purpose): the retail layer this was shown on is no longer reshaped (R43 keeps the apparel chains
    out of it), so it is shown on the two themes whose split still renames a layer."""
    for key, new, old in (("semis", "Contract chip foundries", "Foundry and memory manufacturing"),
                          ("pharma", "Export-focused generic formulation makers", "Export generic formulation makers")):
        d = live(key)
        stale = {**d["kept"], "model_names": {**d["kept"]["model_names"], "sig": "stale"}}      # the split reshaped its layers again
        m = pre_map(d, RECOVERED["origin"].get(key), RECOVERED["description"].get(key))
        out, _ = B.place_rest(m, d["theme"], lambda s: d["evidence"].get(s), ask=None, kept=stale, carried=True)
        names = {v["layer"] for v in out["value_chain"]}
        assert new in names and old not in names, key
        plain, _ = B.place_rest(m, d["theme"], lambda s: d["evidence"].get(s), ask=None, kept=stale, carried=False)
        assert old in {v["layer"] for v in plain["value_chain"]}, key          # not carried: renamed only on the same members


def test_each_recovered_layer_is_the_only_one_the_kept_answer_fits():
    """A company the map named itself and the split moved is replayed in the map layer it was named in: the endpoint shows only where it
    ended, so it is recovered as the one map layer (of every combination for the theme's moved companies) whose replayed placement has the
    layer-name signature the kept answer holds (theme_base.names_signature over the map's layers before the split). c1 (updated on purpose:
    the answers read from the live Release 43 are kept under the rules as they are, so the replay works their names out afresh and holds
    no signature to compare): the one combination whose replay gives every company its exact live layer, names included (the companies
    still unexplained aside). An origin of a company the live split no longer moves is not read, so not checked."""
    for key, origin in RECOVERED["origin"].items():
        d = live(key)
        moved = {c["ticker"] for v in d["value_chain"] for c in v["companies"] if c.get("moved") and not c.get("placed")}
        origin = {s_: x for s_, x in origin.items() if s_ in moved}
        if not origin:
            continue
        odd = set(RECOVERED["unexplained"].get(key) or {})
        # c1 (updated on purpose): a company APPROVED moves is expected in its approved layer, as the first test expects it
        want = {c["ticker"]: APPROVED.get(f"{key}:{c['ticker']}", (v["layer"],))[0] for v in d["value_chain"] for c in v["companies"]}
        names = [v["layer"] for v in pre_map(d, {**RECOVERED["origin"][key], **{s_: "?" for s_ in origin}})["value_chain"]
                 if not v.get("official") and v["layer"] != "?"]
        fits = []
        for combo in itertools.product(names, repeat=len(origin)):
            out, _ = replay(key, origin={**RECOVERED["origin"][key], **dict(zip(origin, combo))}, carried=d["kept_version"] != B.RULES)
            got = layers_of(out["value_chain"])
            if odd or d.get("kept_version") != B.RULES:        # names lost with an unexplained company: members only (halves as one)
                got = {s_: joined(v["layer"], v) for v in out["value_chain"] for c in v["companies"] for s_ in [c["ticker"]]}
                ref = {c["ticker"]: APPROVED.get(f"{key}:{c['ticker']}", (joined(v["layer"], v),))[0] for v in d["value_chain"]
                       for c in v["companies"]}
                back = name_only(d)
                ok = all(got.get(s_) in (x, back.get(x)) for s_, x in ref.items() if s_ not in odd)
            else:
                ok = all(got.get(s_) == x for s_, x in want.items())
            if ok:
                fits.append(dict(zip(origin, combo)))
        # c1 (updated on purpose): where two map layers give the same replay (semis: Micron replays the same from the foundry layer or the
        # licensing one, which both send it to the makers), the recovered one is among them; the placement is the same either way
        assert origin in fits, key


def test_the_recovered_inputs_are_needed():
    """Each recovered input changes the replay: without the industry path DigiSpice's evidence reads as a telecom operator's (its kept
    "software" made telecom_services) and leaves the software layer; with the description read since, Shradha's low-confidence model is
    read again and leaves the developers' layer."""
    d = live("it")
    out, _ = B.place_rest(pre_map(d), d["theme"], lambda s: d["evidence"].get(s), ask=None, kept=d["kept"])
    assert layers_of(out["value_chain"])["DIGISPICE"] != layers_of(d["value_chain"])["DIGISPICE"]
    d = live("realty")
    out, _ = B.place_rest(pre_map(d), d["theme"], lambda s: d["evidence"].get(s), ask=None, kept=d["kept"])
    assert layers_of(out["value_chain"])["SHRADHA"] != layers_of(d["value_chain"])["SHRADHA"]


def test_a_carried_answer_asks_no_unknown_model_again_and_keeps_its_models():
    """R41 (the live Release 38.1 Pharma deck: the bump to RULES 40 asked Hikal's and Brooks's unknown models again and moved them out of the
    contract research layer): a kept answer carried from earlier rules asks no unknown model again; under its own rules it still does (R30).
    A names check asked again for a carried answer only adds the models and names it lacks."""
    import pytest

    from app.intel import theme_check as C
    from tests.test_r21_deck import ABOUT, mapped

    def first(system, text):
        if system == C.MODEL_SYSTEM:
            return {"models": {}}
        return {"place": [{"symbol": "EL2", "layer": "L2"}, {"symbol": "MS2", "layer": "L0"}, {"symbol": "SH2", "layer": "L1"}, {"symbol": "XX1", "layer": "none"}],
                "models": {"EL2": "manufacturing"}}
    _, got = B.place_rest(mapped(), "Defence", ABOUT.get, ask=first)
    assert "SH2" not in got["models"]
    # gl50 (R50, updated on purpose): every kept placement is carried after a rules bump, so "never asked again" left a theme whose answer
    # gave few models without them for good (the live FMCG deck: 37 of 48 left out). A carried answer now asks each unknown model once
    # (kept in "reasked", never asked twice), its own models kept; a model asked apart never moves a company out of the layer the map or
    # the AI's answer put it in (settled: Hikal and Brooks stay)
    once = []
    _, same = B.place_rest(mapped(), "Defence", ABOUT.get, ask=lambda s, t: once.append(s) or {"models": {}}, kept=got, carried=True)
    assert once == [C.MODEL_SYSTEM] and "SH2" in same["reasked"] and same["models"]["EL2"] == "manufacturing"
    _, again = B.place_rest(mapped(), "Defence", ABOUT.get, ask=lambda s, t: pytest.fail("asked again"), kept=same, carried=True)
    assert "SH2" not in again["models"]
    asked = []
    B.place_rest(mapped(), "Defence", ABOUT.get, ask=lambda s, t: asked.append(s) or {"models": {}}, kept=got)
    assert asked == [C.MODEL_SYSTEM]                 # its own rules: the unknown model asked once (R30)

    def names(system, text):
        if system == C.MODEL_SYSTEM:
            return {"models": {}}
        return {"place": [], "rename": [], "models": {"EL2": "project_services", "SH2": "manufacturing"}}
    stale = {**got, "names_for": "stale"}            # the layers' members changed: the names are checked again
    _, kept = B.place_rest(mapped(), "Defence", ABOUT.get, ask=names, kept=stale, carried=True)
    assert kept["models"]["EL2"] == "manufacturing" and kept["models"].get("SH2") == "manufacturing"
    _, fresh = B.place_rest(mapped(), "Defence", ABOUT.get, ask=names, kept=stale)
    assert fresh["models"].get("EL2") != "manufacturing"         # not carried: the new answer stands, as before


def test_a_carried_answer_asks_names_only_for_a_reshaped_layer_it_never_named(monkeypatch):
    from app.intel import theme_check as C
    sent = []
    monkeypatch.setattr(C, "names_for_models", lambda layers, ask, theme: sent.append(sorted(v["layer"] for v in layers)) or {})
    d = live("semis")            # d1 (updated on purpose): retail's renamed layer is no longer reshaped (R43)
    m = pre_map(d, RECOVERED["origin"].get("semis"), RECOVERED["description"].get("semis"))
    out, got = B.place_rest(m, d["theme"], lambda s: d["evidence"].get(s), ask=lambda s, t: {"models": {}}, kept=d["kept"], carried=True)
    held = set(d["kept"]["model_names"]["rename"])
    assert not any(held & set(x) for x in sent)
    assert "Contract chip foundries" in {v["layer"] for v in out["value_chain"]}
    assert set(got["model_names"]["rename"]) >= held & {v.get("was") for v in out["value_chain"]}
