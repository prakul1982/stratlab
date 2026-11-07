"""The theme library (R19, owner 7 Nov: "if someone on that very day searches for the same theme we can directly provide it").

Every finished theme read (the AI map, its checked membership, the descriptions: what GET /research/sector answers) is kept once for
everyone in the shared store (computed.py, kind "theme"), keyed by the market, the theme's normalised name and the membership rules'
version (theme_base.RULES). Anyone searching the same theme, however they write it ("EV", "electric vehicles", "Electric Vehicle"),
gets that read at once: no AI call, no check run again. Market values are put in from the stored index as it is served (with_caps).

A stored read is served until someone presses Refresh (computed.refresh_gate) or the owner refreshes or removes it in Admin → Library;
nothing expires on its own. A rules change is a new key.

Matching a search to a stored theme (`find`): the normalised name, then the aliases each entry has gathered (every way it was searched
for and the AI map's own name), then a close spelling only above a high bar, word by word (`close`). Never a different theme: "private
banks" is not "public banks", "IT services" is not "IT hardware"."""
import re
import threading
import time
import unicodedata
from difflib import SequenceMatcher

from .. import computed
from . import theme_base

KIND = "theme"
DIVE = "theme:dive"
FACTS = "theme:facts"
REGION_WORDS = {"IN": {"india", "indian", "indias", "bharat"}, "US": {"us", "usa", "american", "america", "united", "states"}}
FILLER = {"sector", "sectors", "industry", "industries", "theme", "themes", "stocks", "stock", "companies", "company", "the", "of", "in", "space"}
WORDS = {"evs": "ev", "defense": "defence", "centre": "center", "centres": "center", "automobile": "automotive", "auto": "automotive", "autos": "automotive",
         "pharma": "pharmaceutical", "pharmaceuticals": "pharmaceutical", "chip": "semiconductor", "chips": "semiconductor",
         "psu": "public", "govt": "public", "government": "public", "renewables": "renewable", "telecommunication": "telecom",
         "telecommunications": "telecom", "fintech": "financial technology", "infra": "infrastructure"}
ALIASES = {"ev": "electric vehicle", "electric car": "electric vehicle", "electric mobility": "electric vehicle", "e mobility": "electric vehicle",
           "ai": "artificial intelligence", "green energy": "renewable energy", "clean energy": "renewable energy", "renewable": "renewable energy",
           "solar power": "solar energy", "solar": "solar energy", "oil gas": "oil and gas", "realty": "real estate", "fmcg": "consumer staple",
           "it": "it service", "information technology": "it service", "railway": "rail", "railway capex": "rail capex"}
CLOSE = 0.92                 # a close spelling: the whole name at least this alike...
CLOSE_WORD = 0.8             # ...and every word that differs this alike, same first letter, no digits
REFRESH_HOLD = 15 * 60       # a Refresh under way: the page is given the live work, not the stored read, for at most this long
_refreshing: dict = {}       # (region, name) -> when a Refresh started
_lock = threading.Lock()


def _sing(w: str) -> str:
    if len(w) > 4 and w.endswith("ies"):
        return w[:-3] + "y"
    if len(w) > 3 and w.endswith("s") and not w.endswith(("ss", "us", "is")):
        return w[:-1]
    return w


def normalise(q: str, region: str = "") -> str:
    """A theme's name as compared: case, accents, punctuation, plurals, spellings and filler words aside, and the market's own name
    dropped ("India defence" in India is "defence"); then the alias table ("ev" is "electric vehicle")."""
    t = unicodedata.normalize("NFKD", str(q or "")).encode("ascii", "ignore").decode().lower().replace("&", " and ")
    words = re.sub(r"[^a-z0-9]+", " ", t).split()
    words = [x for w in words for x in WORDS.get(w, w).split()]
    if len(words) > 1:
        rest = [w for w in words if w not in REGION_WORDS.get(region, set())]
        words = rest or words
    if len(words) > 1:
        rest = [w for w in words if w not in FILLER]
        words = rest or words
    phrase = " ".join(_sing(w) for w in words)
    phrase = ALIASES.get(phrase, phrase)
    return phrase if phrase != "and" else ""


def close(a: str, b: str) -> bool:
    """Two normalised names close enough to be the same theme misspelt: the same number of words, the whole at least CLOSE alike, and
    each differing word at least CLOSE_WORD alike with the same first letter and no digits."""
    if a == b:
        return True
    wa, wb = a.split(), b.split()
    if len(wa) != len(wb) or min(len(a), len(b)) < 6 or SequenceMatcher(None, a, b).ratio() < CLOSE:
        return False
    for x, y in zip(wa, wb):
        if x == y:
            continue
        if len(x) < 4 or len(y) < 4 or x[0] != y[0] or any(c.isdigit() for c in x + y) or SequenceMatcher(None, x, y).ratio() < CLOSE_WORD:
            return False
    return True


def key_of(region: str, name: str) -> list:
    return [region, name, theme_base.RULES]


def find(region: str, q: str) -> dict | None:
    """The stored theme a search is for ({"id", "name", "label", ...}), or None: exact name, then an alias, then a close spelling."""
    n = normalise(q, region)
    if not n:
        return None
    ix = computed.index(KIND)["entries"]
    mine = [(hk, e) for hk, e in ix.items() if e.get("region") == region and (e.get("meta") or {}).get("rules") == theme_base.RULES]
    for test in (lambda e: (e.get("meta") or {}).get("q") == n, lambda e: n in ((e.get("meta") or {}).get("aliases") or []),
                 lambda e: any(close(n, a) for a in [(e.get("meta") or {}).get("q") or ""] + list((e.get("meta") or {}).get("aliases") or []))):
        got = [(hk, e) for hk, e in mine if test(e)]
        if len(got) == 1:
            hk, e = got[0]
            return {"id": hk, "name": (e.get("meta") or {}).get("q"), **e}
        if len(got) > 1:            # two stored themes alike: none is served rather than the wrong one
            return None
    return None


def refreshing(region: str, name: str) -> dict | None:
    """The Refresh under way for a stored theme ({"at", "by"}), or None."""
    with _lock:
        t = _refreshing.get((region, name))
        if t is not None and time.time() - t["at"] > REFRESH_HOLD:
            _refreshing.pop((region, name), None)
            return None
        return t


def mark_refreshing(region: str, name: str, on: bool = True, by: str | None = None) -> None:
    with _lock:
        if on:
            _refreshing[(region, name)] = {"at": time.time(), "by": by}
        else:
            _refreshing.pop((region, name), None)


def stored(region: str, q: str) -> dict | None:
    """The stored read for a search, as {"entry", "payload", "at"}, or None (not stored, or a Refresh of it is under way)."""
    e = find(region, q)
    if e is None or refreshing(region, e["name"]):
        return None
    got = computed.get(KIND, key_of(region, e["name"]))
    if got is None or not isinstance((got.get("value") or {}).get("payload"), dict):
        return None
    return {"entry": e, "payload": got["value"]["payload"], "at": got.get("at"), "name": e["name"]}


def complete(payload: dict) -> bool:
    """A read worth keeping for everyone: the AI map written, every check done, nothing still being worked on."""
    p = payload.get("placements") or {}
    return bool(float(payload.get("generated_at") or 0)) and payload.get("ai") is None and bool(p.get("checked")) and not p.get("pending")


def members(payload: dict) -> int:
    return len({c.get("ticker") for grp in (payload.get("value_chain") or []) + (payload.get("sub_themes") or [])
                for c in grp.get("companies") or [] if c.get("ticker")})


def keep(region: str, q: str, payload: dict, by: str | None = None) -> bool:
    """Keep a finished read for everyone, under the stored theme the search matched (so its aliases grow) or a new one."""
    if not complete(payload):
        return False
    e = find(region, q)
    name = e["name"] if e else normalise(q, region)
    if not name:
        return False
    busy = refreshing(region, name)
    if busy and float(payload.get("generated_at") or 0) < busy["at"]:
        return False                # the read from before the Refresh: the new one is still being written
    by = by or (busy or {}).get("by")
    aliases = set((e.get("meta") or {}).get("aliases") or []) if e else set()
    aliases |= {normalise(q, region), normalise(payload.get("sector") or "", region)}
    aliases.discard("")
    body = {k: v for k, v in payload.items() if k not in ("ai", "refresh_state")}
    kept = computed.put(KIND, key_of(region, name), {"payload": body, "q": q}, label=payload.get("sector") or q, region=region,
                        meta={"q": name, "aliases": sorted(aliases), "members": members(payload), "rules": theme_base.RULES}, by=by)
    mark_refreshing(region, name, False)
    return kept is not None


def suggest(region: str, q: str, limit: int = 5) -> list[dict]:
    """Stored themes for the search box: the one this search is for first, then names starting with or containing what's typed."""
    n = normalise(q, region)
    ix = computed.index(KIND)["entries"]
    rows = []
    hit = find(region, q) if n else None
    for hk, e in ix.items():
        m = e.get("meta") or {}
        if e.get("region") != region or m.get("rules") != theme_base.RULES:
            continue
        names = [m.get("q") or ""] + list(m.get("aliases") or []) + [str(e.get("label") or "").lower()]
        rank = 0 if hit and hit["id"] == hk else 1 if n and any(x.startswith(n) for x in names) else 2 if n and any(n in x for x in names) else 3 if not n else None
        if rank is None:
            continue
        rows.append((rank, -(e.get("hits") or 0), {"name": e.get("label") or m.get("q"), "q": m.get("q"), "region": region,
                                                   "at": computed._iso(e.get("at")), "members": m.get("members"), "searched": e.get("hits") or 0}))
    rows.sort(key=lambda x: (x[0], x[1]))
    return [r for _, _, r in rows[:limit]]
