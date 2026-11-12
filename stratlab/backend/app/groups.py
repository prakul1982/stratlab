"""India's business groups, made out from the promoters the companies name in their own shareholding filings.

Each listed company names its promoter group's members in its quarterly shareholding pattern (shareholders.py keeps the
ones above 1% of the company, and the promoter group's total). The rule, the same for every company:

1. A company's promoters are the promoter-group members named in its latest stored filing, leaving out the government:
   the President of India, a state's Governor, a government or ministry, a state's industrial development or investment
   corporation, and any listed company whose own largest promoter is one of these (a public-sector company). They
   promote public-sector companies and joint ventures, which are not a business group. A name promoting more than
   MAX_SPREAD companies is left out too (a public body, not a family's holding).
2. Two companies are tied when they name the same promoter entity (a company, trust, firm or LLP) that is the largest
   promoter of at least one of the two, or at least two of the same promoter individuals (one shared personal name can
   be two people), or when one company is itself the largest promoter of the other. A partner holding a minority
   promoter stake in a joint venture does not tie the venture to its own group.
3. A group is a set of companies tied to each other, directly or through other members, of at least MIN_MEMBERS
   companies. A set larger than MAX_MEMBERS is left out: a chain that long is more likely to join separate groups
   than to be one group.
4. A group is named by the first word most of its companies' names share ("Alpha" for Alpha Steel, Alpha Power ...),
   the company names being only this tie-breaker; when no word is shared by most of them, by the promoter named in
   the most of its companies.

Each group says how sure the rule is: "high" when at least HIGH_SHARE of its companies name the same promoter (its
anchor), "medium" otherwise (some companies are in it only through a chain of shared promoters). Each company says
which promoter names tie it in. Nothing is typed in by hand: a family's companies that name no promoter in common
are not put together, and a name shared by two unrelated companies is not enough on its own.

Prices are the heatmap's stored daily rows (heatmap.py); market values the screens' index. Facts only: names as
filed, figures as stored."""
import re
import threading
from collections import Counter, defaultdict

from . import shareholders
from .intel.net import TTLCache

MIN_MEMBERS = 3
MAX_MEMBERS = 60
MAX_SPREAD = 25
HIGH_SHARE = 0.75
GOVERNMENT = re.compile(r"\bPRESIDENT OF INDIA\b|\bGOVERNOR OF\b|\bGOVERNMENT OF\b|\bGOVT OF\b|\bSTATE OF [A-Z]+\b|"
                        r"\bMINISTRY OF\b|\bUNION OF INDIA\b|\bINDUSTRIAL DEVELOPMENT CORPORATION\b|\bSTATE INDUSTRIAL\b|"
                        r"\bINDUSTRIAL INVESTMENT CORPORATION\b|\bSTATE INVESTMENTS?\b|\bSTATE FINANCIAL CORPORATION\b")
PERSON_KINDS = {"Individual or HUF", "Foreign individual", "Director or relative", "Person acting in concert"}
NAME_STOP = {"THE", "SHREE", "SHRI", "SRI", "NEW", "INDIA", "INDIAN", "LIMITED", "LTD", "AND", "OF"}
PERIODS = ("1d", "1w", "1m", "3m", "ytd", "1y")
NOTE = ("Companies are grouped by the promoters they name in their own quarterly shareholding filings: two companies are in one "
        "group when they share their main promoter company, trust or firm, or two promoter individuals, or one is the main "
        "promoter of the other. Names as filed; a family's companies that name no promoter in common are not put together. "
        "Prices are the last stored close. Not advice.")
_cache = TTLCache(max_items=8, max_bytes=8 * 1024 * 1024)
_lock = threading.Lock()


def _latest(co: dict) -> tuple[str | None, dict]:
    qs = co.get("q") or {}
    if not qs:
        return None, {}
    q = max(qs)
    return q, qs[q] or {}


def promoters(qrow: dict) -> list[dict]:
    """A filing's promoter-group members, the government left out, the largest first: [{"key", "name", "kind", "pct", "person"}]."""
    out = []
    for r in shareholders._rows(qrow):
        if r["group"] != "promoter" or r["kind"] == "Government" or GOVERNMENT.search(r["key"]):
            continue
        out.append({"key": r["mkey"], "name": r["name"], "kind": r["kind"], "pct": r["pct"], "person": r["kind"] in PERSON_KINDS})
    out.sort(key=lambda p: -p["pct"])
    return out


def _public_sector(index: dict[str, dict], names: dict[str, str]) -> set[str]:
    """The name keys of listed companies whose largest promoter is the government, or a company that is (worked out
    until nothing changes: a subsidiary of a public-sector company is one too)."""
    gov: set[str] = set()
    for _ in range(6):
        found = set()
        for sym, co in index.items():
            rows = [r for r in shareholders._rows(_latest(co)[1]) if r["group"] == "promoter"]
            if not rows:
                continue
            top = max(rows, key=lambda r: r["pct"])
            if top["kind"] == "Government" or GOVERNMENT.search(top["key"]) or top["mkey"] in gov:
                found.add(shareholders.holder_key(names.get(sym) or sym))
        if found <= gov:
            break
        gov |= found
    return gov


class _Sets:
    def __init__(self, items):
        self.up = {i: i for i in items}

    def find(self, x):
        while self.up[x] != x:
            self.up[x] = self.up[self.up[x]]
            x = self.up[x]
        return x

    def join(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.up[max(ra, rb)] = min(ra, rb)


def _first_word(name: str) -> str | None:
    words = [w for w in re.findall(r"[A-Z0-9&]+", str(name or "").upper()) if w not in NAME_STOP and len(w) > 1]
    return words[0] if words else None


def _title(s: str) -> str:
    s = re.sub(r"\s+[.,]+$|[.,]+$", "", str(s or "").strip())
    return " ".join(w if len(w) <= 3 and w.isupper() and not w.isalpha() else w.capitalize() for w in s.split())


def _shared_start(names: list[str], word: str, most: int = 3) -> list[str]:
    """The words the names share from `word` on ("Aditya Birla" for Aditya Birla Capital and Aditya Birla Fashion), at most
    `most`, never a whole name and never ending on "&"."""
    toks = []
    for n in names:
        t = re.findall(r"[A-Z0-9&]+", n.upper())
        toks.append(t[t.index(word):] if word in t else [word])
    out = [word]
    for i in range(1, most):
        nxt = {t[i] if len(t) > i + 1 else None for t in toks}
        if len(nxt) != 1 or None in nxt or next(iter(nxt)) in NAME_STOP - {"AND"}:
            break
        out.append(next(iter(nxt)))
    while out and out[-1] in ("&", "AND"):
        out.pop()
    return out


def _cased(word: str, names: list[str]) -> str:
    """A shared first word as the companies write it ("HDFC Bank Limited" → "HDFC"); a short one filed only in capitals
    stays in capitals (an acronym), a longer one gets a capital letter."""
    for n in names:
        for w in re.findall(r"[A-Za-z0-9&]+", n):
            if w.upper() == word and not w.isupper():
                return w
    for n in names:
        for w in re.findall(r"[A-Za-z0-9&]+", n):
            if w.upper() == word and w.isupper() and (len(w) <= 4 or "&" in w):
                return w
    return word.capitalize()


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:50] or "group"


def build(index: dict[str, dict]) -> dict:
    """The groups the rule makes out of the stored filings ({symbol: {"name", "q": {quarter: filing}}}): {"groups": [...],
    "left_out": [sets larger than MAX_MEMBERS], "companies": how many companies' filings were read}."""
    pro: dict[str, list[dict]] = {}
    names = {sym: co.get("name") or sym for sym, co in index.items()}
    gov = _public_sector(index, names)
    ppct: dict[str, float | None] = {}
    quarter: dict[str, str] = {}
    for sym, co in index.items():
        q, row = _latest(co)
        if not q:
            continue
        pro[sym] = [p for p in promoters(row) if p["key"] not in gov]
        quarter[sym] = q
        ppct[sym] = row.get("ppct") if isinstance(row.get("ppct"), (int, float)) else None
    holders: dict[str, set[str]] = defaultdict(set)
    label: dict[str, str] = {}
    person: dict[str, bool] = {}
    for sym, ps in pro.items():
        for p in ps:
            holders[p["key"]].add(sym)
            label.setdefault(p["key"], p["name"])
            person[p["key"]] = person.get(p["key"], True) and p["person"]
    common = {k for k, syms in holders.items() if 2 <= len(syms) <= MAX_SPREAD}
    sets = _Sets(pro)
    ties: dict[tuple[str, str], set[str]] = defaultdict(set)       # (a, b) -> the promoter names they share
    pairs: dict[tuple[str, str], list[str]] = defaultdict(list)
    for k in common:
        for a in holders[k]:
            for b in holders[k]:
                if a < b:
                    pairs[(a, b)].append(k)
    top = {sym: ps[0]["key"] for sym, ps in pro.items() if ps}           # each company's largest promoter
    for (a, b), keys in pairs.items():
        same_top = [k for k in keys if not person[k] and k == top.get(a) == top.get(b)]
        if same_top or len(keys) >= 2:
            sets.join(a, b)
            ties[(a, b)] |= set(keys)
    # a listed company that is the largest promoter of another
    by_name = {shareholders.holder_key(n): s for s, n in names.items() if s in pro}
    for sym, key in top.items():
        other = by_name.get(key)
        if other and other != sym:
            sets.join(sym, other)
            ties[tuple(sorted((sym, other)))].add(key)
    tied_to: dict[str, list[tuple[str, set[str]]]] = defaultdict(list)
    for (a, b), keys in ties.items():
        tied_to[a].append((b, keys))
        tied_to[b].append((a, keys))
    members: dict[str, list[str]] = defaultdict(list)
    for sym in pro:
        members[sets.find(sym)].append(sym)
    groups, left_out = [], []
    for syms in members.values():
        if len(syms) < MIN_MEMBERS:
            continue
        syms = sorted(syms)
        if len(syms) > MAX_MEMBERS:
            left_out.append({"companies": len(syms), "sample": syms[:8]})
            continue
        inside = set(syms)
        count = Counter(k for s in syms for k in {p["key"] for p in pro[s]} if k in common)
        weight = Counter()
        for s_ in syms:
            for p in pro[s_]:
                weight[p["key"]] += p["pct"]
        # the promoter named in the most members; then an entity before a person; then the larger stake in them all
        anchor = max(count, key=lambda k: (count[k], not person[k], weight[k], k)) if count else None
        firsts = Counter(w for w in (_first_word(names[s]) for s in syms) if w)
        word, n = (firsts.most_common(1)[0] if firsts else (None, 0))
        named = None
        if word and n >= 2 and n * 2 >= len(syms):
            sharing = [names[x] for x in syms if _first_word(names[x]) == word]
            named = " ".join(_cased(w, sharing) for w in _shared_start(sharing, word))
        title = named or _title(shareholders.tidy_name(label.get(anchor, "")) or syms[0])
        share = (count[anchor] / len(syms)) if anchor else 0
        rows = []
        for s in syms:
            tied = set().union(*[keys for other, keys in tied_to[s] if other in inside])
            rows.append({"symbol": s, "name": names[s], "quarter": quarter[s], "promoter_pct": ppct[s],
                         "promoter_named_pct": round(sum(p["pct"] for p in pro[s]), 2),
                         "anchor": anchor in {p["key"] for p in pro[s]},
                         "ties": sorted((label[k] for k in tied if k in label), key=lambda x: (-len(holders.get(shareholders.holder_key(x), ())), x))[:4]})
        groups.append({"name": title, "named_by": "company names" if named else "promoter", "anchor": label.get(anchor),
                       "anchor_count": count[anchor] if anchor else 0, "confidence": "high" if share >= HIGH_SHARE else "medium",
                       "members": rows})
    # a name two groups would share: each told apart by its anchor promoter
    seen = Counter(g["name"] for g in groups)
    for g in groups:
        if seen[g["name"]] > 1 and g["anchor"]:
            g["name"] = f"{g['name']} ({_title(shareholders.tidy_name(g['anchor']))})"
    taken: set[str] = set()
    for g in sorted(groups, key=lambda g: (-len(g["members"]), g["name"])):
        slug = _slug(g["name"])
        while slug in taken:
            slug += "-2"
        taken.add(slug)
        g["slug"] = slug
    return {"groups": groups, "left_out": left_out, "companies": len(pro)}


def made() -> dict:
    """The groups from every stored filing, kept for an hour (the filings change once a quarter)."""
    hit = _cache.get("groups")
    if hit is not None:
        return hit
    with _lock:
        hit = _cache.get("groups")
        if hit is None:
            hit = build(shareholders._index())
            _cache.set("groups", hit, 3600 if hit["companies"] else 300)
    return hit


def forget() -> None:
    _cache.clear()


# ---------- prices ----------
def _tiles(symbols: list[str], on_demand: bool) -> tuple[dict[str, dict], str | None]:
    """{symbol: the heatmap's tile (px last close, r the six changes, cap ₹ crore)} and the day of the closes."""
    from . import heatmap
    if on_demand:
        v = heatmap.view("IN", symbols=symbols)
        return {t["s"]: t for t in v["tiles"]}, v.get("as_of")
    doc = heatmap.load("IN")
    stocks = doc.get("stocks") or {}
    rows, sectors = heatmap._facts("IN")
    return {s: heatmap.tile(s, stocks[s], rows.get(s), sectors.get(s)) for s in symbols if s in stocks}, doc.get("day")


def combined(tiles: list[dict]) -> dict:
    """The members' market value added up, and how that total moved over each period (from each company's value then:
    today's value over one plus its change)."""
    caps = [t for t in tiles if t.get("cap")]
    total = sum(t["cap"] for t in caps)
    moves = {}
    for i, p in enumerate(PERIODS):
        have = [t for t in caps if t["r"][i] is not None and t["r"][i] > -100]
        before = sum(t["cap"] / (1 + t["r"][i] / 100) for t in have)
        now = sum(t["cap"] for t in have)
        moves[p] = round((now / before - 1) * 100, 2) if before > 0 and len(have) * 2 >= len(caps) else None
    return {"cap": round(total, 2) if caps else None, "change": moves, "priced": len(caps)}


TEASER_PERIODS = ("1d",)               # what a plan without business group figures sees of the changes (plans.py group_figures)


def _teaser(change: dict, full: bool) -> dict:
    return change if full else {p: (v if p in TEASER_PERIODS else None) for p, v in change.items()}


def index_view(full: bool = True) -> dict:
    got = made()
    every = sorted({m["symbol"] for g in got["groups"] for m in g["members"]})
    tiles, day = _tiles(every, on_demand=False)
    out = []
    for g in got["groups"]:
        mine = [tiles[m["symbol"]] for m in g["members"] if m["symbol"] in tiles]
        c = combined(mine)
        top = sorted(mine, key=lambda t: -(t.get("cap") or 0))[:3]
        out.append({"slug": g["slug"], "name": g["name"], "companies": len(g["members"]), "confidence": g["confidence"],
                    "anchor": g["anchor"], "cap": c["cap"], "change": _teaser(c["change"], full),
                    "largest": [{"symbol": t["s"], "name": t["n"]} for t in top] or [{"symbol": m["symbol"], "name": m["name"]} for m in g["members"][:3]]})
    out.sort(key=lambda g: (-(g["cap"] or 0), g["name"]))
    return {"groups": out, "as_of": day, "companies": sum(g["companies"] for g in out), "read": got["companies"],
            "left_out": len(got["left_out"]), "note": NOTE, "rule": RULE, "full": full}


RULE = [f"A company's promoters are the promoter-group members named in its latest shareholding filing (above 1% of the company), "
        "leaving out the government, state development and investment corporations, and public-sector companies, and any name "
        f"promoting more than {MAX_SPREAD} companies.",
        "Two companies are tied when they name the same promoter company, trust, firm or LLP and it is the largest promoter of at "
        "least one of them, or two of the same promoter individuals, or when one company is the largest promoter of the other.",
        f"A group is every company tied to another member, of {MIN_MEMBERS} companies or more; a set of more than {MAX_MEMBERS} "
        "is left out as unreliable.",
        "Its name is the first word most of its companies' names share; otherwise the promoter named in the most of them.",
        f"'High' confidence: at least {int(HIGH_SHARE * 100)}% of its companies name the same promoter. 'Medium': some are in "
        "only through a chain of shared promoters."]


def group_view(slug: str, full: bool = True) -> dict | None:
    """One group's page. Without `full` (a plan without business group figures): each member's market value and the day's
    change, not its longer changes, its promoter holding or the members' heatmap."""
    got = made()
    g = next((x for x in got["groups"] if x["slug"] == slug), None)
    if g is None:
        return None
    syms = [m["symbol"] for m in g["members"]]
    tiles, day = _tiles(syms, on_demand=True)
    rows = []
    for m in g["members"]:
        t = tiles.get(m["symbol"]) or {}
        row = {**m, "name": t.get("n") or m["name"], "cap": t.get("cap"), "close": t.get("px"),
               "change": _teaser({p: (t.get("r") or [None] * len(PERIODS))[i] for i, p in enumerate(PERIODS)}, full), "sector": t.get("sec")}
        if not full:
            row.update(promoter_pct=None, promoter_named_pct=None)
        rows.append(row)
    rows.sort(key=lambda r: (-(r["cap"] or 0), r["name"]))
    c = combined(list(tiles.values()))
    return {"slug": g["slug"], "name": g["name"], "named_by": g["named_by"], "anchor": g["anchor"], "anchor_count": g["anchor_count"],
            "confidence": g["confidence"], "companies": rows, "tiles": [tiles[s] for s in syms if s in tiles] if full else [], "cap": c["cap"],
            "change": _teaser(c["change"], full), "as_of": day, "quarter": max((m["quarter"] for m in g["members"]), default=None),
            "note": NOTE, "rule": RULE, "full": full}


def group_of(symbol: str) -> dict | None:
    for g in made()["groups"]:
        if any(m["symbol"] == symbol for m in g["members"]):
            return {"slug": g["slug"], "name": g["name"], "companies": len(g["members"]), "confidence": g["confidence"]}
    return None
