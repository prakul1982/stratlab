#!/usr/bin/env python3
"""Release gate on placement inputs (lane g57, Release 57; the owner's review of the live R56 decks: Capital One removed from Payments as not
a card issuer, Sarepta removed from Biotech on one narrow layer's mismatch, Duolingo alone in a "Hotels, travel and consumer services" layer):
before decks go out, the current placement engine is run offline on each theme's stored placement inputs and every company-level change
against the placement stored in the input is listed with the reason the deck would print, and what must never ship is flagged.

    python scripts/release_gate.py <folder of placement inputs> [--only key,key] [--json] [--show N]

--model none runs the engine with no model at all instead of the stub (an empty answer can change a placement: compare).
Each <key>.json in the folder is a GET /research/theme-dive/placement-inputs answer (as saved, {"data": ...} or bare). Offline: no network
(every socket connect is refused while the gate runs) and no AI: the kept answer the input holds is the only answer, and the engine's model
is a stub that answers nothing. The engine run is the exact replay of the live placement (the map as theme_routes.placed hands it to
theme_base.place_rest; a map pick the split moved is put back in the map layer whose replay gives the most companies their stored layer).

Changes, stored placement -> engine (each with the reason the deck would print, "" when the engine gives none):
  left       a company in the stored placement the engine leaves out of the theme
  joined     a company the engine places that the stored placement doesn't hold
  moved      a company in another layer
  layer +/-  a layer created or removed
  share      the share of companies in informative layers (not "Other ...") on both sides

FAIL (the exit code is 1 when any theme has one; each row says on which side it is found: stored, engine or both):
  removal unreasoned   a company left out of the theme with no reason the deck could print
  own industry out     a company left out of the theme whose official industry is one of the theme's own, unless its reason is that its
                       own words describe another business or a scope the theme's definition excludes
  layer-only removal   a company left out of the theme because its own words don't show one layer's work (the check's "no" or
                       "unbacked" for its group): a mismatch with a layer is a reason to place it elsewhere, never to remove it
  member with removal  a company the placement keeps in the theme that also carries a business-membership removal (the check's "no"
                       or "unbacked" for a group): the change log prints that removal as the reason it is gone whenever it leaves the
                       deck's figures (Sarepta, kept in "Other biotech companies" by its official industry in the stored R56 Biotech
                       placement); the row says when it is kept in the very layer the removal says its words don't show
  reason contradicted  a removal saying its own words don't show a layer's work while its own words say that layer's name
  layer words          a layer whose name shares no word with any of its members' own words, official industry or name (a hotels and
                       travel layer holding a language-learning app); a company the engine moved into a layer its own words don't name;
                       a layer whose name has no word of three letters or more
  one-company layer    a named layer (not "Other ...", not an official group) holding one company whose own words don't say its name
                       (r58: one valid member keeps its layer, with no median)
  largest left out     a company of a named layer left out of its figures on insufficient evidence alone (read only weakly, no words, none
                       found, no way of earning stated) that is one of the theme's 10 largest by market value (never more than its
                       largest quarter: theme_base.TOP_MEMBERS, TOP_SHARE) or larger than every company
                       in the layer's figures (r572: the live R57.1 decks left McDonald's, Yum, SLB and Disney out while every fixture passed)
  layer lost           a named layer of the published version, with a company still in the theme, that no layer of the placement holds
                       under any of its names, unless half or more of its companies sit in one or two layers new to this version
                       or every one of its companies was moved out by a rule naming it with its reason (r58: Consumer retail's
                       "Single-category specialty retailers" lost twice)
  model contradicted   a company's printed way of earning that its own words contradict: they state another way of earning in so many
                       words (theme_check.model_from_words), of a family not kin to it (the families of making are one kin), and
                       show no word of its own
Exit codes: 0 no FAIL, 1 a FAIL, 2 bad usage. Read-only: reads the input files, writes nothing."""
import argparse
import contextlib
import itertools
import json
import pathlib
import re
import socket
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.intel import theme_base as B          # noqa: E402
from app.intel import theme_changes as TC      # noqa: E402
from app.intel import theme_check as C         # noqa: E402

_HALF = re.compile(r"( \((?:larger|smaller)\))+$")
_SPLIT_MARKS = ("placed", "fit", "moved", "single", "model", "model_tags", "model_confidence", "model_out")
_STALE = ("out_why", "on_industry", "refit", "own_goods", "by_words", "unfit")       # what the placement adds; worked out again by the engine
# words a layer's name may use that say no particular business: what any company is, does or serves
_NAME_GENERIC = {"and", "or", "of", "the", "for", "in", "to", "with", "by", "on", "from", "other", "others", "own", "their", "they", "them",
                 "company", "companies", "firms", "players", "business", "businesses", "group", "groups", "service", "services", "product",
                 "products", "goods", "consumer", "consumers", "customer", "customers", "client", "clients", "makers", "maker", "producers",
                 "producer", "suppliers", "supplier", "providers", "provider", "sellers", "seller", "owners", "owner", "operators",
                 "partners", "specialty", "speciality", "diversified", "integrated", "sized", "small", "smaller", "large", "larger", "mid",
                 "scale", "wide", "broad", "general", "focused", "led", "based", "commercial", "listed", "segment", "segments", "related",
                 "allied", "plus", "global", "domestic", "new", "solutions", "systems"}
# families of making: a maker, a parts maker, a contract maker, a miner or smelter and a metal processor all make what they sell, so
# one's printed model is never contradicted by another's words ("manufactures steel" beside "Miners and primary metal producers")
_KIN = ({"making", "components", "contract_making", "mining", "metal_processing", "resources"},)
_SUFFIXES = ("ations", "ation", "ings", "ing", "ers", "er", "ies", "es", "s", "ed", "al")
OWN_REASON = re.compile(r"another business|outside the theme's|scope|definition doesn't include|isn't one of the theme's|not one of the theme's", re.I)
LAYER_ONLY = ("no", "unbacked")
INSUFFICIENT = ("weak", "no_words", "none_found", "no_model")       # r572: the figures verdicts of insufficient evidence (theme_base.by_model out_why)


# ---------- words ----------
def _stem(w: str) -> str:
    for suf in _SUFFIXES:
        if w.endswith(suf) and len(w) - len(suf) >= 4:
            w = w[:-len(suf)]
            break
    return w[:5]


def name_words(name: str) -> set[str]:
    """The stems of the words of a layer's name that say a business (no generic work word, no qualifier)."""
    ws = re.findall(r"[a-z0-9]+", str(name or "").lower().replace("&", " and "))
    return {_stem(w) for w in ws if len(w) > 2 and not w.isdigit() and w not in _NAME_GENERIC}


def text_words(text: str) -> set[str]:
    return {_stem(w) for w in re.findall(r"[a-z0-9]+", str(text or "").lower().replace("&", " and ")) if len(w) > 2}


def shares(name: str, text: str) -> bool | None:
    """Whether a text says a word of a layer's name; None when the name has no word that says a business."""
    nw = name_words(name)
    if not nw:
        return None
    tw = text_words(text)
    return any(a == b or (len(a) >= 4 and len(b) >= 4 and (a.startswith(b) or b.startswith(a))) for a in nw for b in tw)


# the words before a model's words that make them the customers' business, not the company's ("shared by the Wireless Telecom Operators",
# "requirements of Telecom Operators", "Data Centre & Cloud companies, Telecom operators")
_FOR_WHOM = re.compile(r"(?:\b(?:by|for|to|of|with|serv\w*|customers?|clients?|such as|includ\w*|like|across|among)\s+(?:the\s+|its\s+|their\s+|leading\s+|global\s+)?"
                       r"(?:[\w&-]+\s+){0,3}|,\s*(?:[\w&-]+\s+){0,2}|\band\s+)$", re.I)


def says_model(evidence: str) -> str:
    """The one way of earning a company's own words state in so many words (theme_check.model_from_words), "" when its words only name
    it as its customers' business."""
    st = C.model_from_words(evidence)
    if not st:
        return ""
    _, own = C._split_evidence(evidence)
    own = C.not_customers(own)
    hits = list(re.finditer(C.MODEL_SAYS.get(st) or r"(?!)", own, re.I))
    if not hits:                  # read in its own way (a chip designer without fabs: theme_check.chip_designer)
        return st
    return st if any(not _FOR_WHOM.search(own[max(0, m.start() - 60):m.start()]) for m in hits) else ""


def kin(a: str, b: str) -> bool:
    fa, fb = C.model_family(a), C.model_family(b)
    return fa == fb or any(fa in k and fb in k for k in _KIN)


# ---------- the input ----------
def load(path: pathlib.Path) -> dict:
    d = json.loads(path.read_text())
    d = d.get("data", d) if isinstance(d, dict) else d
    if not isinstance(d, dict) or not isinstance(d.get("value_chain"), list) or "kept" not in d:
        raise ValueError("not a placement-inputs answer")
    # r572: each company's figures verdict as the stored placement printed it (the stale marks are worked out again by the engine)
    d["stored_out"] = {c["ticker"]: c.get("out_why") or "" for v in d["value_chain"] for c in v.get("companies") or [] if c.get("ticker")}
    for v in d["value_chain"]:
        v["companies"] = [{k: x for k, x in c.items() if k not in _STALE} for c in v.get("companies") or []]
    return d


def shown(v: dict) -> str:
    return _HALF.sub("", str(v.get("layer") or ""))


def rows_of(vc: list) -> dict:
    """{symbol: (its layer as the deck names it, the layer, the company)} of a placement, each company in its first layer."""
    out = {}
    for v in vc or []:
        for c in v.get("companies") or []:
            if c.get("ticker") and c["ticker"] not in out:
                out[c["ticker"]] = (shown(v), v, c)
    return out


def words_of(d: dict, s: str, c: dict | None = None) -> str:
    """A company's own words, official industry and name, as the input holds them."""
    c = c or {}
    f = (d.get("facts") or {}).get(s) or {}
    return " ".join(str(x or "") for x in ((d.get("evidence") or {}).get(s), c.get("what"), c.get("industry"), f.get("industry"),
                                           f.get("business"), " ".join(f.get("segments") or []), c.get("name")))


def own_text(d: dict, s: str, c: dict | None = None) -> str:
    """Its evidence as the model rules read it: "Industry: ...." then its own words."""
    c = c or {}
    f = (d.get("facts") or {}).get(s) or {}
    ind = c.get("industry") or f.get("industry") or ""
    own = " ".join(str(x) for x in ((d.get("evidence") or {}).get(s), c.get("what"), f.get("business")) if x)
    return (f"Industry: {ind}. " if ind else "") + own


def theme_industries(d: dict) -> set[str]:
    return {B.key(x) for x in (d.get("placements") or {}).get("industries") or [] if x}


def own_industry(d: dict, industry: str) -> bool:
    inds = theme_industries(d)
    if not industry or not inds:
        return False
    parts = [B.key(industry)] + [B.key(p) for p in str(industry).split(">")]
    return any(p in inds for p in parts if p)


# ---------- the engine, offline ----------
def _is_map_layer(v) -> bool:
    return not v.get("official") and not v.get("by_place") and not v.get("industry_group") and not (v.get("by_model") and not v.get("scale"))


def pre_map(d: dict, origin: dict | None = None) -> dict:
    """The map as theme_routes.placed handed it to place_rest on live (with_base's output), from the stored placement: the map's own
    layers under their map names, a company placed after the map back in its official group, one the split moved in `origin`'s layer."""
    origin = origin or {}
    kept = d["kept"] or {}
    after_split = {x["name"]: k for k, x in ((kept.get("model_names") or {}).get("rename") or {}).items() if isinstance(x, dict) and x.get("name")}
    placed_as = {x["name"]: k for k, x in (kept.get("rename") or {}).items() if isinstance(x, dict) and x.get("name")}

    def map_name(v) -> tuple[str, str]:
        name = shown(v)
        seen = after_split.get(name, name)
        return (v["was"] if v.get("was") and seen == name else placed_as.get(seen, seen)), seen
    layers: dict = {}
    for v in d["value_chain"]:
        if not _is_map_layer(v):
            continue
        own, seen = map_name(v)
        if own not in layers:
            text = ((kept.get("rename") or {}).get(own) or {}).get("description") or "" if seen != shown(v) else v.get("description") or ""
            layers[own] = {"layer": own, "description": text, "companies": []}
    official: dict = {}
    for v in d["value_chain"]:
        for c in v["companies"]:
            if c.get("placed"):
                official.setdefault(c.get("basis") or "industry", []).append(
                    {"ticker": c["ticker"], "name": c.get("name"), "what": "", "verified": False, "base": True, "basis": c.get("basis") or "industry",
                     "industry": c.get("industry") or "", "cap": c.get("cap")})
                continue
            if _is_map_layer(v) and not c.get("moved"):
                own = map_name(v)[0]
            else:
                own = origin.get(c["ticker"]) or ("?" + c["ticker"])
                layers.setdefault(own, {"layer": own, "description": "", "companies": []})
            layers[own]["companies"].append({k: x for k, x in c.items() if k not in _SPLIT_MARKS})
    vc = [v for v in layers.values() if v["companies"] or not v["layer"].startswith("?")]
    for ind in (d.get("placements") or {}).get("industries") or []:
        cos = sorted((c for c in official.get("industry", []) if B.key(c["industry"]) == B.key(ind)), key=lambda c: (-(c.get("cap") or 0), c["ticker"]))
        if cos:
            vc.append({"layer": B.plain_industry(ind), "description": "", "official": True, "basis": "industry", "companies": cos})
    rest = [c for c in official.get("industry", []) if not any(B.key(c["industry"]) == B.key(i) for i in (d.get("placements") or {}).get("industries") or [])]
    named = sorted(official.get("list", []) + rest, key=lambda c: (-(c.get("cap") or 0), c["ticker"]))
    if named:
        vc.append({"layer": "Named in the theme's list", "description": "", "official": True, "basis": "list", "companies": named})
    subs = sorted(official.get("added", []), key=lambda c: (-(c.get("cap") or 0), c["ticker"]))
    return {"sector": d["theme"], "value_chain": vc, **({"sub_themes": [{"name": "sub-theme", "companies": subs}]} if subs else {})}


class _NoAnswer:
    """The engine's model offline: answers nothing (an empty answer), and counts how often it was asked."""

    def __init__(self):
        self.calls = 0

    def __call__(self, *a, **k):
        self.calls += 1
        return {}


class _Vocabulary(_NoAnswer):
    """p57: the engine's model offline with the misfit question answered by the vocabulary test (theme_check.vocabulary_fake, a
    deterministic stand-in: production asks the model), every other question answered with nothing."""

    def __call__(self, system, text, *a, **k):
        self.calls += 1
        return C.vocabulary_fake(system, text)


def _kwargs(d: dict) -> dict:
    names = B.place_rest.__code__.co_varnames
    kw = {"previous": d.get("previous") or {}, "carried": d.get("kept_version") != B.RULES}
    for k in ("off_before", "moved_before", "moved_out", "published"):          # p57: the published memory the live placement reads
        if k in names and d.get(k) is not None:
            kw[k] = d.get(k) or {}
    if "published" in names and "published" not in kw:
        kw["published"] = d.get("previous") or {}      # p57: inputs served before "published" was: the stored snapshot stands for it
    if "figures_of" in names and d.get("figures"):
        kw["figures_of"] = lambda s: (d.get("figures") or {}).get(s) or {}
    return kw


STORED_ANSWERS = True      # r572: the model's stored answers to the questions asked once a rules version stand for its answer under new rules


def as_current(kept: dict) -> dict:
    """r572 (the RULES bump of R57.2: offline, the stub's empty answer to the misfit and audit questions, asked again once a rules version,
    undid every move the stored answers made, 109 changes in 34 themes that production, asking the model again, would not show): the kept
    answers to those questions, and the mark of the models asked again, as if given under the engine's rules (the model's last answer is the
    best offline stand-in for the one it gives again; --ask-again replays with the stub's empty answer instead)."""
    kept = dict(kept or {})
    for k in ("fit", "audit"):
        if isinstance(kept.get(k), dict) and kept[k].get("rules") is not None:
            kept[k] = {**kept[k], "rules": B.RULES}
    if kept.get("reasked_rules") is not None:
        kept["reasked_rules"] = B.RULES
    return kept


def run(d: dict, origin: dict, ask) -> tuple[dict, dict]:
    """place_rest on the map as live handed it. The split's renames the kept answer holds are keyed by a signature of the members the
    live split saw; the replay applies them as live did (the signature pinned to the kept one, as lane t56's exact replays do)."""
    if STORED_ANSWERS and d.get("kept"):
        d = {**d, "kept": as_current(d["kept"])}
    m = pre_map(json.loads(json.dumps(d)), origin)
    m["placements"] = json.loads(json.dumps(d.get("placements") or {}))      # p57: as with_base hands the checked map's placements on
    # r58: a company the stored placement kept on a layer's answer alone ("layer_no", theme_base.layer_answer_removals) was in the check's
    # "dropped" when the placement read it: the replay hands it on as the check gave it, so the same rule decides it again (offline, BWX,
    # Curtiss-Wright, Howmet, Palantir and Spirit left Aerospace "with no reason", a replay that skipped the rule live had applied)
    pl_ = m["placements"]
    if pl_.get("layer_no"):
        have = {x.get("ticker") for x in pl_.get("dropped") or [] if isinstance(x, dict)}
        pl_["dropped"] = list(pl_.get("dropped") or []) + [x for x in pl_.pop("layer_no") if isinstance(x, dict) and x.get("ticker") not in have]
    ev, facts = d.get("evidence") or {}, d.get("facts") or {}
    sig = ((d.get("kept") or {}).get("model_names") or {}).get("sig")
    was = B.model_names_signature
    if sig:
        B.model_names_signature = lambda *a, **k: sig
    try:
        return B.place_rest(m, d["theme"], lambda s: ev.get(s), ask=ask, kept=d["kept"], facts_of=lambda s: facts.get(s) or {}, **_kwargs(d))
    finally:
        B.model_names_signature = was


def recover_origin(d: dict, ask) -> dict:
    """The map layer of each map pick the split moved: the one whose replay gives the most companies their stored layer (one company at
    a time; every combination for up to two)."""
    moved = [c["ticker"] for v in d["value_chain"] for c in v["companies"] if c.get("moved") and not c.get("placed")]
    if not moved:
        return {}
    probe = {s: "?" + s for s in moved}
    names = [v["layer"] for v in pre_map(json.loads(json.dumps(d)), probe)["value_chain"] if not v.get("official") and not v["layer"].startswith("?")]
    if not names:
        return {}
    stored = {s: x[0] for s, x in rows_of(d["value_chain"]).items()}

    def score(o):
        return sum(1 for s, x in rows_of(run(d, o, ask)[0]["value_chain"]).items() if stored.get(s) == x[0])
    if len(moved) <= 2:
        return max((dict(zip(moved, c)) for c in itertools.product(names, repeat=len(moved))), key=score)
    origin = dict(probe)
    for s in moved:
        origin[s] = max(names, key=lambda n: score({**origin, s: n}))
    return origin


def engine(d: dict, model: str = "stub") -> tuple[dict, int]:
    """(the placement the current engine gives offline, how often it asked the stub model). `model` "none": no model at all (the
    engine's own path when the AI is not set up), to tell a change an empty answer makes from one the rules make."""
    ask = _NoAnswer() if model == "stub" else _Vocabulary() if model == "vocab" else None
    origin = recover_origin(d, ask)
    out, _ = run(d, origin, ask)
    return out, ask.calls if ask is not None else 0


# ---------- reasons ----------
def move_reason(c: dict, v: dict) -> str:
    r = c.get("refit") if isinstance(c.get("refit"), dict) else {}
    for x in (r.get("why"), c.get("sold_by"), c.get("unfit") if isinstance(c.get("unfit"), str) else None, c.get("by_words") if isinstance(c.get("by_words"), str) else None):
        if x:
            return str(x)
    md = v.get("model") if isinstance(v.get("model"), dict) else {}
    if v.get("by_model") and md.get("line"):
        return "a group by how its companies earn: " + str(md["line"]).split(". ")[0]
    if v.get("official"):
        return "in its official industry's group: " + (str(c.get("out_why")) if c.get("out_why") else "no layer of the map takes it")
    return ""


def out_reasons(placements: dict) -> dict:
    """{symbol: the reason the change log prints for a company left out} of a placement's own lists."""
    out = {}
    for o in (placements or {}).get("off_industry") or []:
        if isinstance(o, dict) and o.get("ticker"):
            out[o["ticker"]] = str(o.get("why") or (f"another business (filed under {o['industry']})" if o.get("industry") else "another business"))
    for x in (placements or {}).get("dropped") or []:
        if isinstance(x, dict) and x.get("ticker"):
            out.setdefault(x["ticker"], TC.dropped_why(x) if x.get("said") else "")
    return out


def join_reason(c: dict) -> str:
    t = c.get("theme") if isinstance(c.get("theme"), dict) else {}
    if t.get("why"):
        return str(t["why"])
    return {"industry": f"filed under {c.get('industry') or 'an official industry'}, an official industry of the theme",
            "list": "named in the theme's list", "added": "named by the theme's map"}.get(c.get("basis") or "", "")


# ---------- the gate ----------
def informative(rows: dict) -> tuple[int, int]:
    return B._informative({s: x[1].get("layer") for s, x in rows.items()})


def renames(a: dict, b: dict) -> dict:
    """{engine layer: stored layer} for a layer renamed, not reshaped: one new to the engine, more than half of whose companies were in
    one stored layer the engine no longer has, that being where more than half of that layer's companies went (theme_changes pairs a
    rename the same way). Its companies are then compared under the stored name; the rename is listed once."""
    la, lb = {x[0] for x in a.values()}, {x[0] for x in b.values()}
    out = {}
    for new in sorted(lb - la):
        mem = [s for s, x in b.items() if x[0] == new and s in a]
        if not mem:
            continue
        old, n = max(((o, sum(1 for s in mem if a[s][0] == o)) for o in {a[s][0] for s in mem}), key=lambda t: (t[1], t[0]))
        size = sum(1 for x in a.values() if x[0] == old)
        if old not in lb and not old.startswith("Other ") and n * 2 > len(mem) and n * 2 > size and old not in out.values():
            out[new] = old
    return out


def diff(d: dict, new_vc: list, new_pl: dict) -> list[dict]:
    a, b = rows_of(d["value_chain"]), rows_of(new_vc)
    outs = out_reasons(new_pl)
    rows = []
    ren = renames(a, b)
    for new, old in ren.items():
        rows.append({"kind": "renamed", "symbol": "", "name": f"“{old}” -> “{new}”", "from": old, "to": new,
                     "reason": "the layer's companies kept, its name changed", "n": sum(1 for x in b.values() if x[0] == new)})
    b = {s: ((ren.get(x[0], x[0]),) + tuple(x[1:])) for s, x in b.items()}
    for s in sorted(set(a) - set(b)):
        rows.append({"kind": "left", "symbol": s, "name": a[s][2].get("name"), "from": a[s][0], "to": "", "reason": outs.get(s, ""),
                     "industry": a[s][2].get("industry") or ""})
    for s in sorted(set(b) - set(a)):
        rows.append({"kind": "joined", "symbol": s, "name": b[s][2].get("name"), "from": "", "to": b[s][0], "reason": join_reason(b[s][2])})
    for s in sorted(set(a) & set(b)):
        if a[s][0] != b[s][0]:
            rows.append({"kind": "moved", "symbol": s, "name": b[s][2].get("name"), "from": a[s][0], "to": b[s][0],
                         "reason": move_reason(b[s][2], b[s][1])})
    la = {x[0] for x in a.values()}
    lb = {}
    for x in b.values():
        lb.setdefault(x[0], x[1])
    gone = {str(g.get("layer")): g for g in (new_pl or {}).get("layers_gone") or [] if isinstance(g, dict)}
    for name in sorted(set(lb) - la):
        v = lb[name]
        md = v.get("model") if isinstance(v.get("model"), dict) else {}
        why = ("a group by how its companies earn: " + str(md.get("line") or "").split(". ")[0]) if v.get("by_model") and md.get("line") else \
            str(v.get("description") or "")[:160]
        rows.append({"kind": "layer +", "symbol": "", "name": name, "from": "", "to": name, "reason": why,
                     "n": sum(1 for x in b.values() if x[0] == name)})
    for name in sorted(la - set(lb)):
        g = gone.get(name) or {}
        went = sorted({b[s][0] for s, x in a.items() if x[0] == name and s in b})
        rows.append({"kind": "layer -", "symbol": "", "name": name, "from": name, "to": "", "reason": str(g.get("why") or (("its companies went to " + ", ".join(f"“{w}”" for w in went)) if went else "")),
                     "n": sum(1 for x in a.values() if x[0] == name)})
    return rows


def checks(d: dict, vc: list, placements: dict, moved_in: set = frozenset(), why_of=None) -> list[dict]:
    """What must never ship, in one placement (the stored one, or the engine's with its own placements). `why_of(symbol, company)`: why a
    company is left out of its layer's figures ("" when it is in them)."""
    out = []
    rows = rows_of(vc)
    why_of = why_of or (lambda s, c: c.get("out_why") or "")

    def fail(kind, subject, detail):
        out.append({"fail": kind, "subject": subject, "detail": detail})
    # removals: the check's own list of companies it left out, with their reasons
    for x in (placements or {}).get("dropped") or []:
        if not isinstance(x, dict) or not x.get("ticker"):
            continue
        s, said = x["ticker"], x.get("said")
        name = f"{x.get('name') or s} ({s})"
        groups = [str(g) for g in x.get("groups") or [] if g]
        why = TC.dropped_why(x) if said else ""
        if s in rows:
            c = rows[s][2]
            if said in LAYER_ONLY:
                where = ("in the very layer the removal names" if rows[s][0] in groups else
                         f"by its official industry ({c.get('industry')})" if rows[s][1].get("official") and own_industry(d, c.get("industry") or "")
                         else "elsewhere")
                fail("member with removal", name, f"kept in “{rows[s][0]}” ({where}) while it carries “{why}”: printed as its removal "
                     f"when it leaves the deck's figures")
            continue
        if not said or (said in LAYER_ONLY and not groups):
            fail("removal unreasoned", name, why or "no reason")
            continue
        if said in LAYER_ONLY:
            fail("layer-only removal", name, why)
        ind = ((d.get("facts") or {}).get(s) or {}).get("industry") or ""
        if own_industry(d, ind) and not OWN_REASON.search(why):
            fail("own industry out", name, f"filed under {ind}; {why}")
        text = words_of(d, s)
        if said == "no" and (d.get("evidence") or {}).get(s):
            hit = [g for g in groups if shares(g, text)]
            if hit:
                fail("reason contradicted", name, f"its own words say “{hit[0]}”'s name; printed: {why}")
    for o in (placements or {}).get("off_industry") or []:
        if isinstance(o, dict) and o.get("ticker") and not (o.get("why") or o.get("industry") or o.get("scope")):
            fail("removal unreasoned", f"{o.get('name') or o['ticker']} ({o['ticker']})", "off_industry with no reason")
    # layers
    by_layer: dict = {}
    for s, (name, v, c) in rows.items():
        by_layer.setdefault(name, (v, []))[1].append((s, c))
    for name, (v, cos) in by_layer.items():
        if v.get("official") or name.startswith("Other "):
            continue
        if not re.search(r"[A-Za-z]{3,}", name):
            fail("layer words", f"“{name}”", f"a layer name with no word, {len(cos)} companies")
            continue
        if len(cos) == 1:
            s, c = cos[0]
            # r58 (R58, the owner: "a category with one valid member can remain useful even if it cannot support a median"): a layer of one
            # company whose own words say its name is valid; one whose words don't is the FAIL
            w1 = words_of(d, s, c)
            if not (shares(name, w1) is True or B.words_support(name, w1, d.get("theme") or "")):
                fail("one-company layer", f"“{name}”", f"{c.get('name') or s} ({s}) alone, its own words not saying the layer's name")
        said = [shares(name, words_of(d, s, c)) for s, c in cos]
        if said and all(x is False for x in said):
            who = ", ".join(f"{c.get('name') or s}" for s, c in cos[:4]) + (f" and {len(cos) - 4} more" if len(cos) > 4 else "")
            fail("layer words", f"“{name}”", f"no member's own words, industry or name say a word of its name: {who}")
            continue
        for s, c in cos:
            if s in moved_in and shares(name, words_of(d, s, c)) is False:
                fail("layer words", f"“{name}”", f"{c.get('name') or s} ({s}) moved in; its own words, industry and name say no word of it")
    # r572 (R57.2, the live R57.1 decks: McDonald's, the Restaurants theme's largest company, Yum, SLB, Baker Hughes, Enbridge and Disney
    # left out of their layers' figures as "insufficient evidence", while every replay of the fixes' own fixtures passed): a company of a
    # named layer left out of its figures on insufficient evidence alone, that is one of the theme's TOP_MEMBERS largest by market value or
    # larger than every company in the layer's figures
    caps = {s: c.get("cap") or 0 for s, (_, _, c) in rows.items()}
    top = {s for s, cap in sorted(caps.items(), key=lambda kv: (-kv[1], kv[0]))[:min(B.TOP_MEMBERS, len(caps) // B.TOP_SHARE)] if cap}
    for name, (v, cos) in by_layer.items():
        if v.get("official") or name.startswith("Other "):
            continue
        top_in = max((caps[s] for s, c in cos if not why_of(s, c)), default=0)
        for s, c in cos:
            w = why_of(s, c)
            if w in INSUFFICIENT and (s in top or caps[s] > top_in > 0):
                fail("largest left out", f"{c.get('name') or s} ({s})", f"left out of “{name}”'s figures: insufficient evidence ({w}), "
                     + ("one of the theme's largest companies" if s in top else "larger than every company in its figures"))
    # printed ways of earning
    for s, (name, v, c) in rows.items():
        md = c.get("model")
        if md not in C.MODELS:
            continue
        ev = own_text(d, s, c)
        st = says_model(ev)
        if st and st != md and not kin(st, md) and not C.own_words_show(md, ev):
            fail("model contradicted", f"{c.get('name') or s} ({s})", f"printed “{C.MODELS[md][1]}” in “{name}”; its own words state "
                 f"“{C.MODELS[st][1]}”")
    return out


def lost_layers(d: dict, vc: list) -> list[dict]:
    """r58 (R58, the owner's review of the live R57.2 decks: Consumer retail's "Single-category specialty retailers", 9 companies, and
    Insurance's one-company "Distribution and aggregation" gone): each named layer of the published version (the previous live version)
    with a company still in the theme that no layer of the placement holds under any of its names, unless half or more of its companies
    sit in one or two layers new to this version (renamed or split). A layer whose companies all left the theme is their removals' case."""
    theme = d.get("theme") or ""
    pub = d.get("published") or {}
    rest = B.other_label(theme)
    inside = set(rows_of(vc))
    by_layer: dict = {}
    for s_, lay in pub.items():
        if s_ not in inside:
            continue
        lay = _HALF.sub("", str(lay or ""))
        if lay and lay != rest and not lay.startswith("Other "):
            by_layer.setdefault(lay, []).append(s_)
    held = set().union(*[B._names(v) for v in vc if not v.get("official")] or [set()])
    rows = rows_of(vc)
    where = {s_: x[0] for s_, x in rows.items()}

    def said_out(lay, syms) -> bool:
        """every one of its companies moved out by a rule that names the layer and says why (a layer not made, with its reason)"""
        for s_ in syms:
            r = rows[s_][2].get("refit") if s_ in rows and isinstance(rows[s_][2].get("refit"), dict) else {}
            if _HALF.sub("", str(r.get("from") or "")) != lay or not r.get("why"):
                return False
        return bool(syms)
    out = []
    for lay, syms in sorted(by_layer.items()):
        if lay in held or said_out(lay, syms):
            continue
        new = {}
        for s_ in syms:
            w = where.get(s_)
            if w and w not in by_layer and not w.startswith("Other "):
                new[w] = new.get(w, 0) + 1
        took = sorted(new.values(), reverse=True)[:2]
        if syms and sum(took) * 2 >= len(syms) and (took[0] >= 2 or len(syms) == 1):
            continue
        went = {}
        for s_ in syms:
            went[where.get(s_) or "not in the theme"] = went.get(where.get(s_) or "not in the theme", 0) + 1
        out.append({"fail": "layer lost", "subject": lay, "side": "engine",
                    "detail": f"a layer of the published version with {len(syms)} compan{'y' if len(syms) == 1 else 'ies'}, gone; now: "
                              + ", ".join(f"{k} {n}" for k, n in sorted(went.items(), key=lambda kv: -kv[1]))})
    return out


def gate(d: dict, model: str = "stub") -> dict:
    new, asked = engine(d, model)
    new_vc, new_pl = new.get("value_chain") or [], new.get("placements") or {}
    stored_pl = d.get("placements") or {}
    changes = diff(d, new_vc, new_pl)
    moved_in = {r["symbol"] for r in changes if r["kind"] in ("moved", "joined")}
    eng_pl = {**stored_pl, **{k: v for k, v in new_pl.items() if k in ("off_industry", "layers_gone", "dropped")}}
    if "layer_no" in new_pl:
        eng_pl["dropped"] = new_pl.get("dropped") or []          # p57: the engine moved the rest (a layer decision, "layer_no")
    elif "dropped" not in new_pl:
        eng_pl["dropped"] = stored_pl.get("dropped") or []       # the membership check is not re-run offline: its removals stand
    fs = checks(d, d["value_chain"], stored_pl, why_of=lambda s, c: (d.get("stored_out") or {}).get(s) or "")
    fe = checks(d, new_vc, eng_pl, moved_in)
    key = lambda f: (f["fail"], f["subject"])       # noqa: E731
    ks, ke = {key(f) for f in fs}, {key(f) for f in fe}
    fails = [{**f, "side": "both" if key(f) in ks else "engine"} for f in fe] + [{**f, "side": "stored"} for f in fs if key(f) not in ke]
    for r in changes:                  # a removal by the engine without a reason, or of a company of the theme's own industry
        if r["kind"] != "left":
            continue
        subj = f"{r['name'] or r['symbol']} ({r['symbol']})"
        if not r["reason"]:
            fails.append({"fail": "removal unreasoned", "subject": subj, "detail": f"left “{r['from']}”, no reason", "side": "engine"})
        if own_industry(d, r.get("industry") or "") and not OWN_REASON.search(r["reason"]):
            fails.append({"fail": "own industry out", "subject": subj, "detail": f"filed under {r['industry']}; {r['reason'] or 'no reason'}", "side": "engine"})
    fails += lost_layers(d, new_vc)
    inf_a, n_a = informative(rows_of(d["value_chain"]))
    inf_b, n_b = informative(rows_of(new_vc))
    return {"theme": d.get("theme"), "region": d.get("region"), "rules": d.get("rules"), "engine_rules": B.RULES, "asked": asked,
            "share": {"stored": [inf_a, n_a], "engine": [inf_b, n_b]}, "changes": changes,
            "fails": sorted(fails, key=lambda f: (f["fail"], f["subject"]))}


# ---------- output ----------
def _pct(a: int, b: int) -> str:
    return f"{a} of {b} ({round(a * 100 / b) if b else 0}%)"


def table(rows: list[list[str]], widths: list[int]) -> list[str]:
    out = []
    for r in rows:
        out.append("  ".join(str(x)[:w].ljust(w) for x, w in zip(r, widths)).rstrip())
    return out


def report(key: str, g: dict, show: int = 40) -> str:
    sa, se = g["share"]["stored"], g["share"]["engine"]
    lines = [f"== {key}: {g['theme']} ({g['region']}), stored under rules {g['rules']}, engine rules {g['engine_rules']}"
             + (f", stub model asked {g['asked']} times (no answer)" if g["asked"] else ""),
             f"   informative share: stored {_pct(*sa)} -> engine {_pct(*se)}"
             + (f"  ({round(se[0] * 100 / se[1]) - round(sa[0] * 100 / sa[1]):+d} points)" if sa[1] and se[1] else "")]
    ch = g["changes"]
    if ch:
        lines.append(f"   changes ({len(ch)}):")
        lines += ["     " + x for x in table([["kind", "company", "from", "to", "reason"]] +
                                             [[r["kind"], (f"{r['name']} ({r['symbol']})" if r["symbol"] else f"{r['name']} ({r.get('n', '')})"),
                                               r["from"], r["to"], r["reason"] or "(no reason)"] for r in ch[:show]], [8, 34, 30, 30, 90])]
        if len(ch) > show:
            lines.append(f"     ... and {len(ch) - show} more")
    else:
        lines.append("   changes: none")
    fs = g["fails"]
    if fs:
        lines.append(f"   FAIL ({len(fs)}):")
        lines += ["     " + x for x in table([["class", "side", "subject", "detail"]] +
                                             [[f["fail"], f["side"], f["subject"], f["detail"]] for f in fs[:show]], [19, 6, 40, 120])]
        if len(fs) > show:
            lines.append(f"     ... and {len(fs) - show} more")
    else:
        lines.append("   FAIL: none")
    return "\n".join(lines)


@contextlib.contextmanager
def offline():
    """Every socket connect refused while the gate runs (put back after)."""
    was = (socket.socket.connect, socket.socket.connect_ex, socket.create_connection)

    def refuse(*a, **k):
        raise OSError("release_gate runs offline")
    socket.socket.connect = socket.socket.connect_ex = socket.create_connection = refuse
    try:
        yield
    finally:
        socket.socket.connect, socket.socket.connect_ex, socket.create_connection = was


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("folder", type=pathlib.Path)
    ap.add_argument("--only", default="", help="comma-separated keys (file stems) to gate")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--show", type=int, default=40, help="rows shown per table")
    ap.add_argument("--model", choices=("stub", "none", "vocab"), default="stub",
                    help="the engine's model offline: a stub that answers nothing (default), none at all, or the vocabulary stand-in for the "
                         "misfit question (p57)")
    ap.add_argument("--new-only", action="store_true", help="r572: the exit code from what the engine would ship (FAIL rows found on the engine's "
                                                            "side, or on both); a row found only in the stored placement is one the engine fixes")
    ap.add_argument("--ask-again", action="store_true", help="r572: the questions asked once a rules version answered by the stub (nothing) "
                                                             "under new rules, instead of by the model's stored answers")
    a = ap.parse_args(argv)
    global STORED_ANSWERS
    STORED_ANSWERS = not a.ask_again
    if not a.folder.is_dir():
        print(f"not a folder: {a.folder}", file=sys.stderr)
        return 2
    only = {x.strip() for x in a.only.split(",") if x.strip()}
    paths = sorted(p for p in a.folder.glob("*.json") if not only or p.stem in only)
    if not paths:
        print(f"no placement inputs in {a.folder}", file=sys.stderr)
        return 2
    results = {}
    with offline():
        for p in paths:
            try:
                d = load(p)
            except (ValueError, json.JSONDecodeError) as e:
                print(f"== {p.stem}: not read ({e})")
                continue
            results[p.stem] = gate(d, a.model)
            if not a.json:
                print(report(p.stem, results[p.stem], a.show), flush=True)
    failing = [k for k, g in results.items() if [f for f in g["fails"] if not a.new_only or f.get("side") != "stored"]]
    if a.json:
        print(json.dumps(results, ensure_ascii=False, indent=1))
    else:
        tot = {}
        for g in results.values():
            for f in g["fails"]:
                tot[f["fail"]] = tot.get(f["fail"], 0) + 1
        print(f"\n{len(results)} themes gated; {len(failing)} with a FAIL" + (": " + ", ".join(failing) if failing else "")
              + ("; " + ", ".join(f"{k} {n}" for k, n in sorted(tot.items())) if tot else ""))
        print(f"changes against the stored placement: {sum(len(g['changes']) for g in results.values())}")
    return 1 if failing else 0


if __name__ == "__main__":
    sys.exit(main())
