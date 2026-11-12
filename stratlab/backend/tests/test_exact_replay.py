"""Exact replays of the live placement (Release 39, lane s2-exact; the owner, after Releases 37-38: fixes proven on replays of the live maps
did not hold on the live site, whose placement read stored descriptions and a kept answer the replays did not have).

The inputs are what GET /research/theme-dive/placement-inputs (Release 39a) returned for the 14 benchmark themes on 12 Nov 2026 under the
Release 38.1 rules (RULES 40): tests/fixtures/themes_live/inputs_r39/<theme>.json, each the checked map as served (every company's layer,
model and whether the split moved it), the kept placement answer and the rules version it was kept under, and each company's stored
description as theme_routes.placed reads it (None: no words). Real estate and Telecom were still being re-checked when read
(placements.checked False); they are replayed like the others.

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


def test_the_replay_reproduces_the_live_layer_of_every_company():
    """Release 38.1's code (RULES 40) on the live inputs gives every company of the 14 themes the layer the live map gives it, by its exact
    name (halves and the split's renames included), but one (inputs_r39/recovered.json "unexplained": Hind Aluminium, whose live evidence
    held words the endpoint doesn't return; in that map the split's renames follow the membership, so its two renamed layers are compared by
    the name the split saw)."""
    diffs = {}
    for key in THEMES:
        d = live(key)
        out, _ = replay(key)
        want, got = layers_of(d["value_chain"]), layers_of(out["value_chain"])
        odd = RECOVERED["unexplained"].get(key) or {}
        if odd:
            back = {x["name"]: k for k, x in ((d["kept"].get("model_names") or {}).get("rename") or {}).items()}
            want = {s: back.get(x, x) for s, x in want.items()}
        bad = {s: (want.get(s), got.get(s)) for s in set(want) | set(got) if want.get(s) != got.get(s) and s not in odd}
        if bad:
            diffs[key] = bad
        assert set(want) == set(got), key
        for s in odd:
            assert want[s] != got[s]                       # still unexplained by the returned inputs: kept listed, never silently matched
    assert diffs == {}


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
