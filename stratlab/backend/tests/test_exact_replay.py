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
    return not v.get("official") and not v.get("by_place") and not (v.get("by_model") and not v.get("scale"))


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
    return {"sector": d["theme"], "value_chain": vc}


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
APPROVED: dict = {}
# the owner's review of Release 38: these companies' layers (or "Other") on the exact replay, whatever a later rule changes
REGRESSION = {"auto:BOSCHLTD": "Component and systems suppliers", "auto:ASAHIINDIA": "Component and systems suppliers",
              "retail:CHWY": "Other", "retail:FGPR": "Other", "retail:SPH": "Other",
              "semis:MU": "Makers of their own products", "semis:INTC": "Makers of their own products",
              "semis:QRVO": "Makers of their own products", "semis:GFS": "Contract chip foundries", "semis:TE": "Other"}


def joined(name: str, v: dict | None = None) -> str:
    return "Other" if (v or {}).get("official") else _HALF.sub("", name)


# live layer names a change approved here takes away, and those it adds (halves as one), by theme
RENAMED: dict = {}
ADDED: dict = {}


def name_only(d: dict) -> dict:
    """{a live layer's name: the name it had before the split renamed it}: in a theme where one company's live layer is unexplained by the
    returned inputs (recovered.json), the split's renames, keyed by the layers' members, are lost with it on a replay whose answer is not
    carried: name-only knock-ons, never a company's move."""
    return {x["name"]: k for k, x in ((d["kept"].get("model_names") or {}).get("rename") or {}).items() if x.get("name")}


def now_layers(key: str) -> dict:
    """{symbol: layer, or "Other"} on the exact replay under the rules as they are now (RULES 41 carries every live kept answer, kept under
    40 or before), the halves of a layer split by market value as one."""
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
        assert set(want) == set(got), key
        odd = RECOVERED["unexplained"].get(key) or {}
        back = name_only(d) if odd else {}
        for s_ in want:
            ok = APPROVED.get(f"{key}:{s_}", (want[s_],))[0]
            if got[s_] != ok and s_ not in odd and back.get(ok) != got[s_]:
                diffs[f"{key}:{s_}"] = (want[s_], got[s_])
        for s_ in odd:
            assert got[s_] != want[s_]          # still unexplained by the returned inputs: kept listed, never silently matched
        out, _ = replay(key, carried=d["kept_version"] != B.RULES)
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
        assert now_layers(key)[s_] == layer, k
    semis = now_layers("semis")
    assert not {"MU", "INTC", "SKHY", "QRVO"} & {s_ for s_, x in semis.items() if x == "Semiconductor equipment"}


def test_a_carried_answer_keeps_the_split_s_names_and_none_is_asked_again():
    """R41: the live answers kept under RULES 40 or before are carried as they are; the layers the split renamed keep the answer's names when
    the split reshapes them again (with no AI, as a page waiting reads it, and in the background check: only a reshaped layer the answer
    never named is asked)."""
    d = live("retail")
    stale = {**d["kept"], "model_names": {**d["kept"]["model_names"], "sig": "stale"}}      # the split reshaped its layers again
    m = pre_map(d, RECOVERED["origin"].get("retail"), RECOVERED["description"].get("retail"))
    out, _ = B.place_rest(m, d["theme"], lambda s: d["evidence"].get(s), ask=None, kept=stale, carried=True)
    names = {v["layer"] for v in out["value_chain"]}
    assert "Off-price, dollar and discount store chains" in names and "Off-price and dollar stores" not in names
    plain, _ = B.place_rest(m, d["theme"], lambda s: d["evidence"].get(s), ask=None, kept=stale, carried=False)
    assert "Off-price and dollar stores" in {v["layer"] for v in plain["value_chain"]}          # not carried: renamed only on the same members


def test_each_recovered_layer_is_the_only_one_the_kept_answer_fits():
    """A company the map named itself and the split moved is replayed in the map layer it was named in: the endpoint shows only where it
    ended, so it is recovered as the one map layer (of every combination for the theme's moved companies) whose replayed placement has the
    layer-name signature the kept answer holds (theme_base.names_signature over the map's layers before the split)."""
    for key, origin in RECOVERED["origin"].items():
        d = live(key)
        names = [v["layer"] for v in pre_map(d, origin)["value_chain"] if not v.get("official")]
        fits = []
        for combo in itertools.product(names, repeat=len(origin)):
            got = replay(key, origin=dict(zip(origin, combo)))[1]
            if got.get("names_for") == d["kept"]["names_for"]:
                fits.append(dict(zip(origin, combo)))
        assert fits == [origin], key


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
    _, same = B.place_rest(mapped(), "Defence", ABOUT.get, ask=lambda s, t: pytest.fail("asked again"), kept=got, carried=True)
    assert "SH2" not in same["models"] and "reasked" not in same
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
    d = live("retail")
    m = pre_map(d, RECOVERED["origin"].get("retail"), RECOVERED["description"].get("retail"))
    out, got = B.place_rest(m, d["theme"], lambda s: d["evidence"].get(s), ask=lambda s, t: {"models": {}}, kept=d["kept"], carried=True)
    held = set(d["kept"]["model_names"]["rename"])
    assert not any(held & set(x) for x in sent)
    assert "Off-price, dollar and discount store chains" in {v["layer"] for v in out["value_chain"]}
    assert set(got["model_names"]["rename"]) >= held & {v.get("was") for v in out["value_chain"]}
