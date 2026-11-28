"""Public theme pages (bet 3): /themes, /themes/<in|us> and /themes/<in|us>/<slug>, server-rendered from the theme library's stored
entries (intel/theme_library.py), for search engines and people who aren't signed in.

A page is a teaser that brings people to the app (owner, 12 Nov): the theme's description, its layers with the names of their checked
companies (each linked to its public /stocks page), the date the map was made and a note on the method, then a call to open the full
theme in the app. Only figures that are reported, never one StratLab works out (owner, until the data terms are confirmed): a member's
market value and its latest reported revenue in its own reporting currency. No layer medians, ranks, margins or sums; no decks,
downloads or tables beyond the member list.

A page is offered to search engines only when it has at least MIN_LAYERS layers with checked companies and MIN_MEMBERS checked
companies in all; any other is noindex and left out of the sitemap. One page per theme: the address is the stored name's slug, and
a slug of one of its aliases answers 301 to it. Rendering reads stored entries only (no AI, no source call); the edge keeps a page
for hours (CACHE)."""
import html
from collections import Counter
import json
import re
from datetime import datetime, timezone
from urllib.parse import quote

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, RedirectResponse

from . import computed, stock_pages
from .config import settings
from .intel import theme_base, theme_library
from .share import FACTS_LINE, checked, day_text, public_words, theme_layers
from .titles import page_title

router = APIRouter(include_in_schema=False)

REGIONS = {"in": "IN", "us": "US"}
MIN_LAYERS = 2
MIN_MEMBERS = 8
CACHE = "public, max-age=600, s-maxage=21600, stale-while-revalidate=86400"
MISSING_CACHE = "public, max-age=60, s-maxage=300"
SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*\Z")
# e54 (R54, the owner's review of the live R53 decks: an official-industry record said to be confirmed by its own description): what each
# company's place rests on is said as it is, a company kept on its official industry alone never said to be confirmed by its own words
METHOD = ("How companies are chosen: a theme's companies come from its official industries (the exchange's own classification) and "
          "from a map of the theme's layers. A company the map adds from another industry is shown here only once its own filings or "
          "description confirm the work its layer names; a company of the theme's official industries is shown on that classification, "
          "and each one says what its place rests on: description-verified (its own description was checked and shows the work), "
          "industry-supported (kept on its official industry only) or not checked (its membership is not checked yet). Market value is at "
          "the last close; revenue is the latest full year as the company reported it, in its own reporting currency. StratLab works out "
          "no figure on this page.")
# l55 (R55, the owner's review of the live R54 decks): the evidence states by the same names as the deck, never one "confirmed" total
EVIDENCE_PUBLIC = {"description_verified": "description-verified", "industry_code_supported": "industry-supported (official industry only)",
                   "list_supported": "list-supported (the theme's own list only)", "membership_unverified": "not checked",
                   # e80 (LIVE16A-008: Fertilizers "284 companies" beside "266 description-verified, 12 industry-supported, 0 not checked"): a
                   # member whose own words describe other work is said, in its row and in every tally, so the parts add up to the whole
                   "not_confirmed": "own words describe other work"}
# fix20 (LIVE14A-004: Fertilizers "284 companies ...: 266 description-verified, 12 industry-supported, 0 not checked", 278 of 284): the members
# whose own words describe other work said too, as the app and the deck say them, so the parts add up to the whole
EVIDENCE_PUBLIC_MANY = (("description_verified", "description-verified"), ("industry_code_supported", "industry-supported"),
                        ("list_supported", "list-supported"), ("not_confirmed", "own words describe other work"),
                        ("membership_unverified", "not checked"))
EVIDENCE_PUBLIC_ALWAYS = ("description_verified", "industry_code_supported", "membership_unverified")


MARK_NOTE = "A company with no Membership mark in a table is description-verified: its own words show the theme's work."
OLDER_LINE = "This page shows the theme as it was checked under an earlier version of StratLab's checks."
RECHECKING_LINE = "It is being checked again now, and this page shows the new check once it is done."


def evidence_said(tally: dict) -> str:
    """l55: "97 description-verified, 63 industry-supported, 51 not checked": the three states by name (the theme's own list where it has
    any), each with its count."""
    return ", ".join(f"{tally.get(k) or 0} {w}" for k, w in EVIDENCE_PUBLIC_MANY if tally.get(k) or k in EVIDENCE_PUBLIC_ALWAYS)


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(name or "").lower()).strip("-")[:80]


def path(region: str, s: str) -> str:
    return f"/themes/{region.lower()}/{s}"


def entries(region: str | None = None) -> list[dict]:
    """The library's stored themes under today's membership rules: {region, name, label, slug, aliases, at, hk}, by name."""
    # ...and a theme not read again yet under rules newer than its stored entry keeps its newest stored one meanwhile (LIVE8A-001: a
    # rules bump took 15 of 21 public theme pages to "No theme at this address" until each was read again), never one of an older map
    # name: an entry under today's rules always wins
    best: dict = {}
    gated: dict = {}
    pubs = _dive_pubs()
    for hk, e in (computed.index(theme_library.KIND).get("entries") or {}).items():
        m = e.get("meta") or {}
        if not isinstance(m.get("rules"), int) or m["rules"] > theme_base.RULES or e.get("region") not in ("IN", "US") \
                or (region and e.get("region") != region):
            continue
        name = str(m.get("q") or "")
        if not slug(name):
            continue
        label = public_words(e.get("label") or name, 80) or name
        # LIVE9A-029: the address is the theme's name as shown ("/themes/in/logistics", "/us/aerospace-and-defense"), not the library's
        # singular key ("/logistic", "/capital-good"); the old address is an alias that answers 301 to it
        own = slug(short_label(label)) or slug(name)
        row = {"region": e["region"], "name": name, "label": label, "slug": own,
               "aliases": [x for x in dict.fromkeys([slug(name)] + [slug(a) for a in m.get("aliases") or []]) if x and x != own], "at": e.get("at"), "hk": hk,
               "rules": m["rules"]}
        key, rank = (e["region"], slug(name)), (m["rules"], str(e.get("at") or ""))
        if key not in best or rank > best[key][0]:
            best[key] = (rank, row)
            gated[key] = _gate(row, m, pubs.get((e["region"], name)))
    # e80 (LIVE16A-009: Public sector banks' public page "checked under an earlier version ... being checked again now" for 4 h and more while
    # its app page said "checked 19 Nov"): an entry kept under older rules whose theme the library now finds under today's rules by another
    # name (the re-check kept it there) stands for nothing: its address answers 301 to that theme's page
    for k, (rank, row) in list(best.items()):
        if row["rules"] >= theme_base.RULES:
            continue
        try:
            now = theme_library.find(row["region"], row["name"])
        except Exception:
            now = None
        if not now or now.get("name") == row["name"]:
            continue
        cur = best.get((row["region"], slug(str(now.get("name") or ""))))
        if cur and cur[1]["rules"] >= theme_base.RULES:
            cur[1]["aliases"] = [x for x in dict.fromkeys(cur[1]["aliases"] + [row["slug"]] + row["aliases"]) if x and x != cur[1]["slug"]]
            best.pop(k, None)
    # e82 (LIVE18A-002): a theme is offered here only once its newest entry passes the quality gate (theme_library.gate_why)
    return sorted((row for k, (_, row) in best.items() if not gated.get(k)), key=lambda x: (x["region"], x["label"].lower()))


_GATE_MEMO: dict = {}


def _gate(row: dict, m: dict, pub: dict | None) -> str:
    """e83 (LIVE19A-001): the quality gate on a theme's newest entry, every entry in full (theme_library.gate_why): an entry kept before the
    gate is judged on its stored read (broad industries) and its dive's own tally of companies not checked, read once per entry and dive
    count (memoised), only where its index meta and kept count don't say them."""
    need_p = "broad" not in m
    # e85 (LIVE21A-001): a count kept before the evidence share was kept with it reads the dive's tally for it too
    need_t = not (isinstance(pub, dict) and isinstance(pub.get("unchecked"), int) and isinstance(pub.get("evidenced"), int))
    if not (need_p or need_t):
        return theme_library.gate_why(m, pub)
    k = (row.get("hk"), str(row.get("at") or ""), json.dumps(pub, sort_keys=True, default=str))
    if k not in _GATE_MEMO:
        p = dive = None
        try:
            p = payload(row)
            if need_t and isinstance(p, dict):
                dive = _dive(row["region"], row["name"], p)
        except Exception:
            p = p if isinstance(p, dict) else None
        dt = (dive or {}).get("tally") if isinstance((dive or {}).get("tally"), dict) else None
        if len(_GATE_MEMO) > 2000:
            _GATE_MEMO.clear()
        _GATE_MEMO[k] = (theme_library.broad_industries(p) if need_p and isinstance(p, dict) else None,
                         int(dt.get("membership_unverified") or 0) if dt and dt.get("total") else None,
                         int(dt["total"]) if dt and dt.get("total") else None, evidenced(dive))
    broad, unchecked, total, ev = _GATE_MEMO[k]
    if not isinstance(pub, dict):
        pub = {"total": total} if total else None
    if ev and isinstance(pub, dict) and not isinstance(pub.get("evidenced"), int):
        pub = {**pub, **ev}
    return theme_library.gate_why(m, pub, unchecked=unchecked, broad=broad)


def _dive_pubs() -> dict:
    """e82: {(region, theme name): the count kept with its newest dive (index meta "pub")}, from the store's index in memory."""
    out, at = {}, {}
    try:
        rows = (computed.index(theme_library.DIVE).get("entries") or {}).values()
    except Exception:
        return {}
    for x in rows:
        m = (x or {}).get("meta") or {}
        k = (x.get("region"), m.get("q"))
        if isinstance(m.get("pub"), dict) and float(x.get("at") or 0) >= at.get(k, -1.0):
            out[k], at[k] = m["pub"], float(x.get("at") or 0)
    return out


def page_path(region: str, name: str) -> str:
    """The public page of the theme the library keeps under `name`: the address its stored entry answers at (LIVE9A-029, from the name as
    shown), or the name's own slug when no entry is stored (that address then finds it, or says no theme is there)."""
    s = slug(name)
    try:
        hit = next((x for x in entries(region) if slug(x["name"]) == s), None)
    except Exception:
        hit = None
    return path(region, hit["slug"] if hit else s)


def public_address(region: str | None, name: str | None) -> str:
    """conv101 (deck footer): the site address a theme's deck names so a forwarded PDF leads back: "stratlab.studio/themes/in/defence" when the
    theme has a public page (by its library name, its normalised name or its label), else the market's themes ("stratlab.studio/themes/in")."""
    host = re.sub(r"^https?://", "", settings.PUBLIC_SITE_URL).rstrip("/")
    r = region if region in REGIONS.values() else None
    if not r:
        return host + "/themes"
    want = {slug(name or "")}
    try:
        want.add(slug(theme_library.normalise(name or "", r)))
        hit = next((x for x in entries(r) if want & {slug(x["name"]), x["slug"], slug(short_label(x["label"]))} - {""}), None)
    except Exception:
        hit = None
    return host + (path(r, hit["slug"]) if hit else f"/themes/{r.lower()}")


def find(region: str, s: str) -> tuple[dict | None, str | None]:
    """(the entry at this slug, None), or (None, the canonical slug) when the slug is one of a theme's aliases, or (None, None)."""
    rows = entries(region)
    hit = next((x for x in rows if x["slug"] == s), None)
    if hit:
        return hit, None
    alias = [x for x in rows if s in x["aliases"]]
    if len(alias) == 1:
        return None, alias[0]["slug"]
    # blog2: the theme as people write it ("it-services", "private-banks", "medical-devices") is the library's normalised name
    # ("it-service", ...): it answers 301 to that page, never "No theme at this address"
    try:
        norm = slug(theme_library.normalise(s.replace("-", " "), region))
    except Exception:
        norm = ""
    hit = next((x for x in rows if norm and x["slug"] == norm), None)
    return (None, hit["slug"]) if hit and hit["slug"] != s else (None, None)


def payload(entry: dict) -> dict | None:
    # the entry found, of whichever rules (an older one stands until the theme is read again under today's: entries)
    got = computed.get_hk(theme_library.KIND, entry["hk"]) if entry.get("hk") else computed.get(theme_library.KIND, theme_library.key_of(entry["region"], entry["name"]), count=False)
    p = ((got or {}).get("value") or {}).get("payload")
    return p if isinstance(p, dict) else None


def _index_caps(region: str) -> dict:
    """{symbol: market value} as the screens' index has it (each page's own checked value: a failed one is None)."""
    try:
        from . import screens
        return {r["symbol"]: r.get("market_cap") for r in screens.load_index(region).get("rows") or [] if r.get("symbol")}
    except Exception:
        return {}


def _index_days(region: str) -> dict:
    """e84: {symbol: the close its market value in the screens' index is at (its price day)}."""
    try:
        from . import screens
        return {r["symbol"]: str(r.get("price_at") or "")[:10] for r in screens.load_index(region).get("rows") or []
                if r.get("symbol") and re.match(r"^\d{4}-\d\d-\d\d$", str(r.get("price_at") or "")[:10])}
    except Exception:
        return {}


def dive_days(dive: dict) -> dict:
    """e84: {symbol: the close the stored dive's market value of it is at (its row's price day)}."""
    out: dict = {}
    for x in (dive.get("layers") or []) + (dive.get("subs") or []) + [{"companies": (dive.get("sections") or {}).get("leaders") or []}]:
        for c in (x or {}).get("companies") or []:
            if not isinstance(c, dict):
                continue
            d_ = str(c.get("price_at") or "")[:10]
            if c.get("symbol") and re.match(r"^\d{4}-\d\d-\d\d$", d_):
                out.setdefault(c["symbol"], d_)
    return out


def _index_newer(region: str, day: str | None) -> dict:
    """r69e (LIVE13A-004: the US theme pages "market values at the 13 Nov 2026 close", the dive's own, while the app and the heatmap showed
    the 17 Nov close): {symbol: (market value, price day)} of the screens' index rows priced at a later close than `day` (the stored dive's
    own), so the page shows each company at the latest completed session as the app does; {} without a day to compare."""
    if not day:
        return {}
    try:
        from . import screens
        out = {}
        for r in screens.load_index(region).get("rows") or []:
            d_ = str(r.get("price_at") or "")[:10]
            if r.get("symbol") and isinstance(r.get("market_cap"), (int, float)) and r["market_cap"] > 0 and re.match(r"^\d{4}-\d\d-\d\d$", d_) \
                    and d_ > day:
                out[r["symbol"]] = (r["market_cap"], d_)
        return out
    except Exception:
        return {}


def _index_sales(region: str) -> dict:
    """LIVE10A-007: {symbol: (revenue, year, unit)} from the screens' index (each company page's newest full year), for a theme whose stored
    dive isn't kept under the current rules."""
    try:
        from . import screens
        return {r["symbol"]: (r["sales"], r.get("sales_year"), r.get("sales_unit")) for r in screens.load_index(region).get("rows") or []
                if r.get("symbol") and isinstance(r.get("sales"), (int, float)) and r["sales"] > 0 and r.get("sales_unit") in ("₹ crore", "$ million")}
    except Exception:
        return {}


def _price_day(region: str, symbols) -> str | None:
    """LIVE9A-011: the close the page's market values are at (the newest price day among its companies in the screens' index), or None."""
    try:
        from . import screens
        want = set(symbols)
        days = [str(r.get("price_at") or "")[:10] for r in screens.load_index(region).get("rows") or [] if r.get("symbol") in want]
        days = [d for d in days if re.match(r"^\d{4}-\d\d-\d\d$", d)]
        return max(days) if days else None
    except Exception:
        return None


def short_label(label: str) -> str:
    """LIVE9A-011/020: a theme's name as a page title or card says it: without a market in brackets ("Capital goods (India)", the market is
    said beside it) and without a long bracketed gloss ("Utilities (Indian power, gas and water-linked infrastructure)")."""
    out = re.sub(r"\s*\((?:India|Indian|US|USA|United States)\)\s*$", "", str(label or ""), flags=re.I).strip()
    m = re.match(r"^(.*?)\s*\(([^)]*)\)\s*$", out)
    if m and m.group(1) and len(m.group(2)) > 20:
        out = m.group(1).strip()
    return out or str(label or "")


def clean_name(name: str) -> str:
    """LIVE9A-011: a company's name as people write it, not a filing's capitals or state mark ("TransDigm Group INC", "Bank Of Montreal /can/")."""
    n = stock_pages.proper_name(name) or name
    n = re.sub(r"\s*/[A-Za-z]{2,4}/?\s*$", "", n).strip()
    n = re.sub(r"\b(INC|CORP|LTD|PLC|CO)\b\.?", lambda m_: m_.group(1).title() + ("." if m_.group(0).endswith(".") else ""), n)
    return re.sub(r"\bOf\b", "of", n) if re.search(r"[a-z]", n) else n


def _dive(region: str, name: str, p: dict) -> dict:
    """The theme's stored dive (read only, never worked out here), {} when none is kept."""
    try:
        from .intel import theme_routes
        got = computed.get(theme_library.DIVE, theme_routes.dive_key(region, name, {**p, "_library": name}), count=False)
    except Exception:
        return {}
    dive = ((got or {}).get("value") or {}).get("dive")
    if not isinstance(dive, dict):
        # r66e: none kept under today's versions yet (a version bump, the theme still to be checked again): the newest one kept
        try:
            old = theme_routes.latest_dive(region, name, str(p.get("sector") or ""))
        except Exception:
            old = None
        dive = (old or {}).get("dive")
    return dive if isinstance(dive, dict) else {}


def dive_caps(dive: dict) -> dict:
    """r66e: {symbol: market value} as the theme's stored dive holds them (its layers, sub-themes and leaders), the app's and the deck's."""
    out: dict = {}
    for x in (dive.get("layers") or []) + (dive.get("subs") or []) + [{"companies": (dive.get("sections") or {}).get("leaders") or []}]:
        for c in (x or {}).get("companies") or []:
            if isinstance(c, dict) and c.get("symbol") and isinstance(c.get("cap"), (int, float)) and c["cap"] > 0:
                out.setdefault(c["symbol"], c["cap"])
    return out


def dive_names(dive: dict) -> dict:
    """e77: {symbol: its name} as the theme's stored dive names it (theme_data.member_name: the app's rows and the deck's)."""
    out: dict = {}
    for x in (dive.get("layers") or []) + (dive.get("subs") or []):
        for c in (x or {}).get("companies") or []:
            if isinstance(c, dict) and c.get("symbol") and str(c.get("name") or "").strip():
                out.setdefault(c["symbol"], str(c["name"]))
    return out


def _evidence(dive: dict):
    """e54: symbol -> its evidence state as the theme's stored dive keeps it (the figures' window, then the companies the membership check
    reached beyond it), "membership_unverified" for one neither has; None for a dive kept before the states were (nothing is claimed)."""
    inner = dive.get("evidence")
    if not isinstance(inner, dict):
        return None
    outer = (dive.get("membership_check") or {}).get("outside") or {}
    return lambda sym: inner.get(sym) or outer.get(sym) or "membership_unverified"


# e81 (LIVE17A-005: 7 of 50 /themes cards differing from their pages, Electric utilities 126 on the card and 118 on its page; the Semiconductors
# post "104 listed US companies ... 9 layers" beside its page's "102 companies in 10 layers"; Space and satellites "19 companies (5 more of the
# theme's 24 not listed: not confirmed by their own words or official industry yet)" while 23 of its 24 were confirmed): one count of a theme's
# companies for every surface, worked out here from the stored read and its dive: the companies the page lists (shown on their official
# industry or confirmed by their own words, the map's check or the dive's evidence: SHOWN_STATES), one listed under two symbols counted once,
# in how many layers, of how many in the theme, and why each one not listed is not (UNLISTED_SAID)
SHOWN_STATES = ("description_verified", "industry_code_supported", "list_supported")
UNLISTED_SAID = (("membership_unverified", "not checked yet"), ("not_confirmed", "whose own words describe other work"),
                 ("", "not confirmed by their own words or official industry yet"))


def public_layers(p: dict, dive: dict | None = None) -> list[dict]:
    """e81: each layer of the stored read with the companies its public page lists (share.checked, or a dive evidence state in SHOWN_STATES),
    a company the dive lists once under another symbol left out; layers with none left out."""
    dive = dive if isinstance(dive, dict) else {}
    ev = _evidence(dive)
    twice = {str(x.get("symbol")) for x in dive.get("duplicates") or [] if isinstance(x, dict) and x.get("symbol")}
    out = []
    for v in (p or {}).get("value_chain") or []:
        if not isinstance(v, dict):
            continue
        cos, seen = [], set()
        for c in v.get("companies") or []:
            if not isinstance(c, dict) or not c.get("ticker") or c["ticker"] in seen or c["ticker"] in twice:
                continue
            if checked(c) or (ev is not None and ev(c["ticker"]) in SHOWN_STATES):
                seen.add(c["ticker"])
                cos.append(c)
        name = public_words(v.get("layer"), 80)
        if cos and name:
            out.append({"name": name, "companies": cos})
    return out


def evidenced(dive: dict | None) -> dict:
    """e85 (LIVE21A-001): {"evidenced": the dive's companies in the theme on evidence of its work (description-verified or list-supported),
    "tallied": of its tally's total}, the public gate's measure (theme_library.gate_why); {} with no tally of the states."""
    dt = (dive or {}).get("tally") if isinstance((dive or {}).get("tally"), dict) else None
    if not dt or not dt.get("total") or "description_verified" not in dt:
        return {}
    return {"evidenced": int(dt.get("description_verified") or 0) + int(dt.get("list_supported") or 0), "tallied": int(dt["total"])}


def counts(p: dict, dive: dict | None = None) -> dict:
    """e81: the theme's one count, as its card, its page and its post say it: {"listed": companies its page lists, "layers": layers its page
    shows, "all": companies in the theme (the dive's tally, the app's and the deck's; else the read's own, each once), "unlisted": [[why, n]]
    for those not listed, adding up to all - listed}."""
    dive = dive if isinstance(dive, dict) else {}
    layers = public_layers(p, dive)
    listed = {c["ticker"] for v in layers for c in v["companies"]}
    twice = {str(x.get("symbol")) for x in dive.get("duplicates") or [] if isinstance(x, dict) and x.get("symbol")}
    every = {c.get("ticker") for v in (p or {}).get("value_chain") or [] if isinstance(v, dict) for c in v.get("companies") or []
             if isinstance(c, dict) and c.get("ticker")} - twice
    dt = dive.get("tally") if isinstance(dive.get("tally"), dict) else None
    total = int(dt["total"]) if dt and dt.get("total") else len(every)
    total = max(total, len(listed))
    ev = _evidence(dive)
    rest = Counter()
    for s_ in sorted(every - listed):
        st = ev(s_) if ev is not None else ""
        rest[st if st in ("membership_unverified", "not_confirmed") else ""] += 1
    unlisted = [[said, rest[k]] for k, said in UNLISTED_SAID if rest[k]]
    # e82 (LIVE18A-005: Indian Pharma "1 more of the theme's 212 not listed: not confirmed by their own words or official industry yet"
    # beside its own "205 description-verified, 7 industry-supported, 0 not checked", and six pages more): the true reason for each one left:
    # a company the dive counts under a second symbol (listed once, under the symbol it keeps), then one its check counts that the stored
    # read's layers don't hold; never "not confirmed" for a company that was
    left = total - len(listed) - sum(n for _, n in unlisted)
    if left > 0:
        mapped = {c.get("ticker") for v in (p or {}).get("value_chain") or [] if isinstance(v, dict) for c in v.get("companies") or []
                  if isinstance(c, dict) and c.get("ticker")}
        dup = min(left, len(twice & mapped) if dt else 0)
        if dup:
            unlisted.append([TWICE_SAID, dup])
        if left - dup:
            unlisted.append([OUTSIDE_SAID, left - dup])
    elif left < 0:
        unlisted = [[UNLISTED_SAID[-1][1], total - len(listed)]] if total > len(listed) else []
    return {"listed": len(listed), "layers": len(layers), "all": total, "unlisted": unlisted}


TWICE_SAID = "the same company under a second symbol, listed once"
OUTSIDE_SAID = "counted by the membership check, in none of the stored layers"


def unlisted_said(c: dict) -> str:
    """e81: the page's line on the theme's companies it doesn't list, each reason with its count ("2 more of the theme's 104 not listed: 1 not
    checked yet, 1 whose own words describe other work"); "" when it lists them all."""
    more = int(c.get("all") or 0) - int(c.get("listed") or 0)
    if more <= 0:
        return ""
    parts = [f"{n} {why}" if len(c.get("unlisted") or []) > 1 else why for why, n in c.get("unlisted") or []]
    return f"{more} more of the theme's {c['all']} not listed" + (f": {', '.join(parts)}" if parts else "")


def stored_counts(region: str, name: str, p: dict) -> dict | None:
    """e81: the theme's count kept with its newest dive (computed index meta "pub", written when the dive was kept: theme_routes.dive_of), so a
    /themes card says its page's numbers without reading the dive; None when no dive kept with it."""
    try:
        from .intel import theme_routes
        hk = computed.hkey(computed._keyed(theme_library.DIVE, theme_routes.dive_key(region, name, {**p, "_library": name})))
        entries = computed.index(theme_library.DIVE).get("entries") or {}
    except Exception:
        return None
    e = entries.get(hk)
    if not (isinstance(e, dict) and isinstance((e.get("meta") or {}).get("pub"), dict)):
        best = None                     # (r66e: none under today's versions yet: the newest one kept, as the page serves it)
        for x in entries.values():
            if isinstance(x, dict) and x.get("region") == region and (x.get("meta") or {}).get("q") == name:
                if best is None or float(x.get("at") or 0) > float(best.get("at") or 0):
                    best = x
        e = best
    got = ((e or {}).get("meta") or {}).get("pub")
    return got if isinstance(got, dict) and isinstance(got.get("listed"), int) else None


BASIS_NOTE = "revenue basis not confirmed"          # e89: theme_data.basis_apart, the deck's mark the same


def basis_apart_of(dive: dict) -> set:
    """e89: the symbols whose stored revenue is on a basis that can't be checked (theme_data.basis_apart: IGL Spirits' one stored year beside
    its layer's revenue net of excise duty), as the stored dive marks them."""
    return {c.get("symbol") for b in (dive or {}).get("layers") or [] for c in b.get("companies") or [] if c.get("basis_apart") and c.get("symbol")}


def _revenues(region: str, name: str, p: dict, dive: dict | None = None) -> dict:
    """{symbol: (revenue, year, unit)} from the theme's stored dive, only where the figure is the company's own reported revenue in
    the market's reporting unit (a figure turned from another currency is left out: that conversion is StratLab's)."""
    dive = _dive(region, name, p) if dive is None else dive
    out = {}
    for b in dive.get("layers") or []:
        for c in b.get("companies") or []:
            v = c.get("revenue")
            if isinstance(v, (int, float)) and v > 0 and not c.get("fx") and c.get("unit") in ("₹ crore", "$ million") and c.get("symbol"):
                out.setdefault(c["symbol"], (v, c.get("year"), c["unit"]))
    return out


def reported_ffos(dive: dict) -> dict:
    """e82 (LIVE18A-004/007: no FFO anywhere on the public REITs page while the deck prints Camden's reported $745 m): {symbol: FFO in $
    million} of the property owners whose own annual report states their FFO (Nareit's definition; the dive's row "ffo_basis" "reported").
    A derived FFO is StratLab's working, never on this page (only reported figures are: the module's rule); the app and the deck show it."""
    out = {}
    for b in dive.get("layers") or []:
        for c in b.get("companies") or []:
            v = c.get("ffo")
            if c.get("symbol") and c.get("ffo_basis") == "reported" and isinstance(v, (int, float)) and v > 0:
                out.setdefault(c["symbol"], v)
    return out


FFO_LINE = ("FFO: funds from operations as the company reports it (Nareit's definition, from its annual report), marked (reported); for a "
            "company that reports none, StratLab's derived FFO is in the app and the deck, marked (derived).")


RESTATED_SHARE = 0.02          # e79: a revenue of the same year moved by more than this share (theme_changes.REVENUE_SHARE) is restated


def restated_sales(index: dict, dive: dict) -> dict:
    """e79 (LIVE15A-017, the owner's P0: Camden Property Trust "$13M Dec 2025" here after its page was rebuilt to $1,574 m, the stored dive
    still the read before): {symbol: (revenue, year, unit)}, the stored dive's figure (the app's and the deck's) unless the company's page,
    as the screens' index has it now, gives the same year in the same unit another revenue (rebuilt since: restated): then the page's."""
    out = {**index, **dive}
    for s_, d in dive.items():
        i = index.get(s_)
        if i and str(i[1] or "") == str(d[1] or "") and i[2] == d[2] and d[0] and abs(i[0] - d[0]) > RESTATED_SHARE * max(i[0], d[0]):
            out[s_] = i
    return out


def money(region: str, v, unit: str | None = None) -> str | None:
    if not isinstance(v, (int, float)) or v <= 0:
        return None
    return stock_pages.usd_text(v) if (unit or ("$ million" if region == "US" else "₹ crore")) == "$ million" else stock_pages.inr_text(v)


def view(entry: dict, p: dict) -> dict:
    """What a theme page shows: checked companies only, reported figures only."""
    region = entry["region"]
    dive = _dive(region, entry["name"], p)
    # r66e (LIVE12A-014: Ambuja ₹97,122 cr in the app beside ₹97,008 crore here at the same close): the market values of the theme's stored
    # dive, the ones its app page and deck show, at the dive's own price date; the index's only for a company the dive doesn't hold
    dcaps = dive_caps(dive)
    dive_day = str(dive.get("as_of"))[:10] if dcaps and dive.get("as_of") else None
    newer = _index_newer(region, dive_day)          # r69e: a company priced at a later close than the dive's: that close's value
    caps, revs, ev = ({**_index_caps(region), **dcaps, **{k: x[0] for k, x in newer.items()}},
                      restated_sales(_index_sales(region), _revenues(region, entry["name"], p, dive)), _evidence(dive))
    known = stock_pages.companies(region)
    ffos = reported_ffos(dive)                # e82: a property owner's FFO as its annual report states it
    # e77 (the R76 decks: "OSI Systems Inc" in the deck beside "Osi Systems Inc" here; "ExxonMobil Holdings Corp" after the owner's "Exxon Mobil
    # Corporation"): each company named as the app's rows and the deck name it (the stored dive's name), a reporting registrant's name first
    named = dive_names(dive)
    # e80 (LIVE16A-007: "Empire State Realty Trust, Inc. ESRT $1.5B" and "Empire State Realty OP, L.P. ESBA $1.4B" both listed): a company the
    # dive found listed under two symbols (theme_data.same_company) is listed once, under the symbol the dive keeps
    twice = {str(x.get("symbol")) for x in dive.get("duplicates") or [] if isinstance(x, dict) and x.get("symbol")}
    apart_basis = basis_apart_of(dive)        # e89: revenue on a basis that can't be checked (excise duty), said beside it
    layers = []
    for v in public_layers(p, dive):          # e81: the companies every surface counts (counts)
        rows = []
        for c in v["companies"]:
            sym = c["ticker"]
            if sym in twice:
                continue
            rev = revs.get(sym)
            # e54: what its place rests on; a company the map added is shown only confirmed by its own words (share.checked)
            # e84 (LIVE20A-001: Capital goods' layers summed to 180 description-verified and 137 industry-supported beside its headline's 178
            # and 139): the stored dive's state first, the one its tally counts; the map's own check only for a company the dive has none for
            state = ev(sym) if ev else None
            if c.get("verified") is True and state in (None, "membership_unverified"):
                state = "description_verified"
            nm_ = stock_pages.reporting_name(region, sym) or named.get(sym) or c.get("name") or sym
            rows.append({"symbol": sym, "name": clean_name(public_words(nm_, 100) or sym),
                         "page": stock_pages.path(region, sym) if sym in known else None,
                         "cap": money(region, caps.get(sym)), "cap_v": caps.get(sym) if isinstance(caps.get(sym), (int, float)) else None,
                         "revenue": money(region, rev[0], rev[2]) if rev else None,
                         "year": str(rev[1] or "")[:20] if rev else None, "evidence": state if state in EVIDENCE_PUBLIC else None,
                         **({"revenue_note": BASIS_NOTE} if rev and sym in apart_basis else {}),
                         **({"ffo": money(region, ffos[sym], "$ million") + " (reported)"} if sym in ffos and region == "US" else {})})
        # l55 (R55): each layer's companies by what their place rests on, as the page's count does for the whole theme
        # LIVE9A-011: a layer's companies largest first by market value (those without one last, by name)
        rows.sort(key=lambda r_: (r_["cap_v"] is None, -(r_["cap_v"] or 0), r_["name"].lower()))
        mine = {r_["symbol"]: r_.get("evidence") for r_ in rows}
        layers.append({"name": v["name"], "companies": rows,
                       "evidence": {k: sum(1 for x in mine.values() if x == k) for k in EVIDENCE_PUBLIC} if ev else None})
    n = len({c["symbol"] for v in layers for c in v["companies"]})
    once = {c["symbol"]: c.get("evidence") for v in layers for c in v["companies"]}
    tally = {k: sum(1 for x in once.values() if x == k) for k in EVIDENCE_PUBLIC} if ev else None
    # r69e (LIVE13A-002): the theme's members by evidence state as the stored dive's one tally has them (the app's and the deck's), of the
    # read it names, in place of a count of the companies this page lists
    dt = dive.get("tally") if isinstance(dive.get("tally"), dict) else None
    if dt and dt.get("total"):
        tally = {k: int(dt.get(k) or 0) for k in EVIDENCE_PUBLIC}
    cn = counts(p, dive)                      # e81: the one count (its card's and its post's)
    older = isinstance(entry.get("rules"), int) and entry["rules"] < theme_base.RULES
    rechecking = False
    if older:
        try:
            from .intel import theme_recheck
            rechecking = theme_recheck.queued(region, entry["name"])
        except Exception:
            rechecking = False
    return {"region": region, "label": entry["label"], "slug": entry["slug"], "name": entry["name"], "evidence": tally,
            # r66e (LIVE12A-001): a theme stored under older rules says so, and that it is being checked again while it is in the queue
            "older": older, "rechecking": rechecking,
            "summary": public_words(p.get("summary"), 700), "layers": layers, "members": n,
            # r64e (LIVE11A-015: Semiconductors "102 companies" here, 104 in the app, deck and blog): the theme's companies, those not
            # confirmed yet not listed here, so the page says how many it leaves out
            "all": cn["all"], "counts": cn,
            "tally_at": str(dive.get("tally_at") or "")[:10] if dt else None,
            # (the close most of its market values are at: each company's own, the index's later one or the dive's)
            # e84 (LIVE20A-020: India pages "market values at the 19 Nov 2026 close" over UltraTech's and TCS's 20 Nov values): each value's
            # own close (the dive row's, the index's later one, or the index's for a company the dive holds none of), and how many are at
            # another close
            **_price_label(once, caps, dcaps, newer, dive_days(dive), _index_days(region), dive_day, region, layers),
            "day": _map_day(region, p, entry),
            "indexable": len(layers) >= MIN_LAYERS and n >= MIN_MEMBERS}


def _price_label(once, caps, dcaps, newer, ddays, idays, dive_day, region, layers) -> dict:
    """e84: {"prices": the close the page's market values are at, "prices_older": how many are at an earlier close}.
    e85 (LIVE21A-004: IT services' head "market values at the 20 Nov 2026 close (9 at the 19 Nov 2026 close) (2 at the 18 Nov ...) ... (1 at
    the 3 Sep 2026 close)", 14 brackets, while its app said "(2 companies at an earlier close)"): the latest close any value is at, as the
    app's dive says it (theme_data.price_day), and one count of the values at an earlier one, of the same companies the dive counts
    (theme_data.older_count)."""
    days = []
    for k in once:
        if not caps.get(k):
            continue
        d_ = newer[k][1] if k in newer else (ddays.get(k) or dive_day) if k in dcaps else idays.get(k) or dive_day
        if d_:
            days.append(d_)
    if not days:
        return {"prices": dive_day or _price_day(region, {c["symbol"] for v in layers for c in v["companies"] if c.get("cap")}), "prices_older": 0}
    top = max(days)
    return {"prices": top, "prices_older": sum(1 for d_ in days if d_ < top)}


def _map_day(region: str, p: dict, entry: dict) -> str | None:
    """LIVE10A-005: the day the map was written (the payload's generated_at, the app's "Last updated" and the deck's "map was written"), in the
    market's own time; the library entry's time (when it was last stored again: "map made 16 Nov" beside the app's 7 Nov) only without it."""
    from zoneinfo import ZoneInfo
    t = float(p.get("generated_at") or 0) or float(entry.get("at") or 0)
    if not t:
        return None
    return datetime.fromtimestamp(t, ZoneInfo("Asia/Kolkata" if region == "IN" else "America/New_York")).date().isoformat()


def indexable(entry: dict) -> bool:
    p = payload(entry)
    if not p:
        return False
    layers = theme_layers(p)
    return len(layers) >= MIN_LAYERS and len({c["ticker"] for v in layers for c in v["companies"]}) >= MIN_MEMBERS


def sitemap_rows(site: str) -> list[tuple[str, str | None]]:
    """(address, day) for the sitemap: the directory pages, and every theme page that is offered to search engines."""
    rows = entries()
    newest = max((datetime.fromtimestamp(float(x["at"]), timezone.utc).date().isoformat() for x in rows if x.get("at")), default=None)
    out = [(site + "/themes", newest)] + [(site + f"/themes/{r}", newest) for r in REGIONS]
    for x in rows:
        if indexable(x):
            out.append((site + path(x["region"], x["slug"]), datetime.fromtimestamp(float(x["at"]), timezone.utc).date().isoformat() if x.get("at") else None))
    return out


def latest_day() -> str:
    return max((datetime.fromtimestamp(float(x["at"]), timezone.utc).date().isoformat() for x in entries() if x.get("at")), default="")


# ---------- pages ----------
def _market(region: str) -> str:
    return "India" if region == "IN" else "the US"


def _app(region: str, name: str | None = None) -> str:
    return settings.PUBLIC_SITE_URL + "/research/themes" + (f"?q={quote(name)}&region={region}" if name else f"?region={region}")


def _where(v: dict) -> str:
    """ "Listed companies in India" (LIVE9A-011: one pattern, never "Hospitals companies in India" or "Capital goods (India) companies")."""
    return f"Listed companies in {_market(v['region'])}"


def render(v: dict) -> str:
    e = html.escape
    site = settings.PUBLIC_SITE_URL
    r = v["region"]
    canonical = site + path(r, v["slug"])
    label = short_label(v["label"])
    title = page_title(f"{label}: listed companies in {_market(r)} by layer")      # LIVE10A-022: "in India", never "in india"
    word = ""        # LIVE10A-022: one header format on every theme page ("41 companies in 9 layers"; "checked" was on the pages without kept states)
    desc = (f"{label} in {_market(r)}: {v['members']} {word}companies in {len(v['layers'])} layers"
            + (f", from {', '.join(x['name'] for x in v['layers'][:3])}" if v["layers"] else "") + ". Facts from filings, not advice.")
    crumbs_html, crumbs_ld = stock_pages._crumbs([("Themes", "/themes"), ("India" if r == "IN" else "US", f"/themes/{r.lower()}"),
                                                  (label, path(r, v["slug"]))])
    ld = stock_pages._ld({"@context": "https://schema.org", "@type": "Dataset", "name": f"{label}: listed companies in {_market(r)}",
                          "description": stock_pages.clamp_desc(desc, 300), "url": canonical, "dateModified": v["day"],
                          "creator": {"@type": "Organization", "name": "StratLab", "url": site}, "isAccessibleForFree": True}) + crumbs_ld
    head = stock_pages._head(title, desc, canonical, extra=ld, robots="index,follow" if v["indexable"] else "noindex,follow")
    app = _app(r, v["name"])
    body = (crumbs_html + f"<h1>{e(label)} <span class=\"muted\">{e(_where(v))}</span></h1>"
            f'<p class="muted">{v["members"]} {word}compan{"y" if v["members"] == 1 else "ies"} in {len(v["layers"])} layer{"" if len(v["layers"]) == 1 else "s"}'
            + (f" ({unlisted_said({**(v.get('counts') or {}), 'listed': v['members'], 'all': v.get('all') or 0})})"
               if (v.get("all") or 0) > v["members"] else "")
            + (f" · map made {e(day_text(v['day']))}" if v.get("day") else "")
            # LIVE9A-011: the close the market values are at, said once; e85 (LIVE21A-004): with one count of those at an earlier close
            + (f" · market values at the {e(day_text(v['prices']))} close" if v.get("prices") else "")
            + (f"; {v['prices_older']} compan{'y' if v['prices_older'] == 1 else 'ies'} at an earlier close"
               if v.get("prices") and v.get("prices_older") else "") + "</p>")
    # conv101 (P2, funnel 27 Nov: the only call to action sat 91% of the way down, under 180 company cards on a phone): what signing up opens and
    # what the theme's deck holds, at the top. The deck itself: Free one theme PDF a month, marked; Basic and Pro more (plans.PLANS decks_per_month, DECK_RULES), so
    # the page offers the free sample to look at, never the theme's own deck as free
    n_layers = len(v["layers"])
    outline = ["Cover and the theme at a glance", f"The value chain: {n_layers} layer{'' if n_layers == 1 else 's'}, as a chart and a table"]
    if v["layers"]:
        outline.append(f"Each layer's companies and figures ({v['members']} compan{'y' if v['members'] == 1 else 'ies'})")
    outline += ["Tailwinds and risks, each with its source", "How every number was worked out"]
    body += (f'<section class="card" data-cta-top><h2>The full {e(label)} theme, free with an account</h2>'
             f"<p>Sign in free to open the whole theme: each company's place in the map and how it was checked, every layer's figures, the "
             f"tailwinds and risks with their sources, and the news.</p>"
             f'<div class="ctas"><a class="btn" rel="nofollow" href="{e(app)}">Open the theme, free (needs sign-in)</a>'
             f'<a class="btn ghost" href="{e(site)}/sample-deck">Preview a theme deck, no sign-in</a></div>'
             f'<details class="how" data-deck-preview><summary>What the {e(label)} slide deck holds</summary><ol>'
             + "".join(f"<li>{e(x)}</li>" for x in outline)
             + f'</ol><p class="muted small">A free account makes one theme deck a month as a PDF, marked "Made with StratLab"; Basic and Pro make '
             f'more, as PDF or PowerPoint. Anyone can download <a href="{e(site)}/sample-deck">the sample deck</a>.</p></details></section>')
    if v.get("older"):             # r66e (LIVE12A-001): a theme shown from its read under an earlier version of the checks says so
        body += ('<p class="note" data-older>' + e(OLDER_LINE + (" " + RECHECKING_LINE if v.get("rechecking") else "")) + "</p>")
    if v.get("evidence"):          # e54: the companies by what their place rests on, adding up to those shown
        # r69e (LIVE13A-002): of the theme's members, from the read the app and the deck say, named by its day
        body += ('<p class="muted small" data-evidence>Membership' + (f" of the theme's {v['all']} companies, as checked on {e(day_text(v['tally_at']))}"
                                                                     if v.get("tally_at") else "") + ": " + e(evidence_said(v["evidence"])) + ".</p>")
    # LIVE9A-011 (owner, 29 Oct: "wherever you can, just make a table"): each layer is a table, largest company first; the theme's
    # description comes after the companies, so a phone's first screen holds companies, not a paragraph
    # LIVE10A-007: no company on the page with a revenue: no Revenue column (it was "–" on every row of 29 pages); on a phone each row is a
    # stacked card (name, then ticker, market value, revenue), never a table wider than the screen
    has_rev = any(c.get("revenue") for x in v["layers"] for c in x["companies"])
    has_ffo = any(c.get("ffo") for x in v["layers"] for c in x["companies"])       # e82: a property owner's reported FFO
    # e83 (LIVE19A-010: four grey notes above the first table, in a column half the tables' width): the notes on the tables' columns (FFO,
    # the Membership mark) come after the tables they explain
    notes = f'<p class="muted small" data-ffo-note>{e(FFO_LINE)}</p>' if has_ffo else ""
    # r69e (LIVE13A-013: Semiconductors' layer tables of 4 and 5 columns, the Ticker edge jumping from x 662 to 555, "description-verified"
    # on 31 of 39 rows): one set of columns on every layer table of the page, and a Membership cell only for a company that is not
    # description-verified (the page's line says so once)
    state_page = any(c.get("evidence") and c["evidence"] != "description_verified" for x in v["layers"] for c in x["companies"])
    if state_page:
        notes += f'<p class="muted small" data-membership-note>{e(MARK_NOTE)}</p>'
    for x in v["layers"]:
        state = state_page
        rows = ""
        for c in x["companies"]:
            name = f'<a href="{e(c["page"])}">{e(c["name"])}</a>' if c["page"] else e(c["name"])
            # LIVE11A-017: the value and its period in one box, so a phone's stacked row keeps them together at the right (the value sat
            # mid-row, its period at the edge, while Ticker and Market value were right-aligned)
            rev = ("<span>" + e(c["revenue"]) + (f' <span class="muted small">{e(c["year"])}</span>' if c.get("year") else "")
                   # e89: a revenue on a basis that can't be checked (excise duty) is said so beside it, never read as comparable
                   + (f' <span class="muted small">({e(c["revenue_note"])})</span>' if c.get("revenue_note") else "") + "</span>") if c["revenue"] else "–"
            ev = ""
            if state:                  # e54: never said confirmed by its own words when it isn't
                ev = f'<td class="l">{e(EVIDENCE_PUBLIC[c["evidence"]]) if c.get("evidence") and c["evidence"] != "description_verified" else "" if c.get("evidence") else "–"}</td>'
            if ev and ev != '<td class="l"></td>':
                ev = ev.replace('<td class="l">', '<td class="l" data-label="Membership">', 1)
            # e80 (LIVE16A-019 / LIVE15A-019: every phone card of a description-verified company carried an empty "Membership" label): an
            # empty cell keeps the table's columns and carries no label, so a phone's stacked card shows no row for it
            rows += (f'<tr><td>{name}</td><td class="l" data-label="Ticker">{e(c["symbol"])}</td><td data-label="Market value">{e(c["cap"]) if c["cap"] else "–"}</td>'
                     + (f'<td data-label="Revenue">{rev}</td>' if has_rev else "")
                     # e83 (LIVE19A-010: every phone card of a company with no FFO ended on a lone unlabelled "–", R78's fix undone): labelled
                     + ((f'<td data-label="FFO">{e(c["ffo"])}</td>' if c.get("ffo") else '<td data-label="FFO">–</td>') if has_ffo else "") + f"{ev}</tr>")
        thead = ('<tr><th scope="col">Company</th><th scope="col" class="l">Ticker</th><th scope="col">Market value</th>'
                + ('<th scope="col">Revenue</th>' if has_rev else "") + ('<th scope="col">FFO</th>' if has_ffo else "")
                + ('<th scope="col" class="l">Membership</th>' if state else "") + "</tr>")
        # the layer's own mix of states only where it isn't every company description-verified (the page's line above says the whole)
        lev = (f'<p class="muted small" data-layer-evidence>{e(evidence_said(x["evidence"]))}</p>'
               if x.get("evidence") and any(c.get("evidence") and c["evidence"] != "description_verified" for c in x["companies"]) else "")
        body += (f'<section class="card" data-layer><h2>{e(x["name"])}</h2>{lev}<div class="cotbl" data-stack><table aria-label="{e(x["name"])}">'
                 f"<thead>{thead}</thead><tbody>{rows}</tbody></table></div></section>")
    body += notes
    if not v["layers"]:
        body += '<p class="note">No company in this theme has been checked yet.</p>'
    if v["summary"]:
        body += f'<section class="card" data-about><h2>About the theme</h2><p>{e(v["summary"])}</p></section>'
    body += (f'<section class="card" data-cta><h2>See the full theme on StratLab</h2><p>Sign in for the whole theme: the figures of each layer, '
             f"every company placed by the map and how it was checked, the tailwinds and risks with their sources, the news and the slides.</p>"
             f'<div class="ctas"><a class="btn" rel="nofollow" href="{e(app)}">Open the {e(label)} theme (needs sign-in)</a><a class="btn ghost" href="{e(site)}/pricing">See the plans</a></div></section>'
             f'<details class="how"><summary>How this page is made</summary><p>{e(METHOD)}</p></details>'
             f'<p class="note">{e(FACTS_LINE)} <a href="{e(site)}/help#feedback">Report an error</a>.</p>')
    return stock_pages._page(head, app, body, src="theme")


def directory(region: str | None) -> str:
    e = html.escape
    site = settings.PUBLIC_SITE_URL
    rows = entries(region)
    where = f" in {_market(region)}" if region else ""
    canonical = site + ("/themes" + (f"/{region.lower()}" if region else ""))
    title = page_title(f"Investment themes{where}: companies by layer")
    desc = f"Themes{where} mapped into layers of listed companies, each checked against its own filings. Facts, not advice."
    trail = [("Themes", "/themes")] + ([("India" if region == "IN" else "US", f"/themes/{region.lower()}")] if region else [])
    crumbs_html, crumbs_ld = stock_pages._crumbs(trail)
    if not region:
        crumbs_html = ""               # LIVE9A-020: a breadcrumb "Themes" over the h1 "Themes" said the page's name twice
    head = stock_pages._head(title, desc, canonical, extra=crumbs_ld)
    tabs = "".join(f'<a href="/themes{p}"' + (' aria-current="page"' if (region or "") == R else "") + f">{t}</a>"
                   for p, R, t in (("", "", "All"), ("/in", "IN", "India"), ("/us", "US", "US")))
    body = (crumbs_html + f"<h1>Themes{e(where)}</h1><p class=\"muted\">{e(desc)}</p><nav class=\"links\" aria-label=\"Markets\">{tabs}</nav>")
    if rows:
        # LIVE9A-020: each card its short name (never "Capital goods (India) · India"), how many companies and the map's date
        # LIVE10A-006: the name on its own line and the count line under it, both inside the card's one link, so a long name never runs
        # into "India · 281 companies" and every card in a row is as tall as the tallest (they collided and differed in height)
        body += ('<ul class="dir" data-cards>' + "".join(f'<li><a href="{e(path(x["region"], x["slug"]))}"><span class="nm">{e(short_label(x["label"]))}</span>'
                                                         f'<span class="muted">{e(card_line(x))}</span></a></li>' for x in rows) + "</ul>")
    else:
        body += '<p class="note">No theme has been mapped and checked yet. Open the themes in the app to map one.</p>'
    body += (f'<div class="ctas"><a class="btn" href="{e(_app(region or "IN"))}">Map any theme on StratLab</a></div>'
             f'<p class="note">{e(FACTS_LINE)}</p>')
    return stock_pages._page(head, _app(region or "IN"), body, src="theme")


def card_line(x: dict) -> str:
    """LIVE9A-020: a directory card's small line: "India · 69 companies · 16 Nov" (the count of checked companies on its page)."""
    bits = ["India" if x["region"] == "IN" else "US"]
    p = None
    try:
        p = payload(x)
        # e81 (LIVE17A-005): its page's own count, as kept with its dive (stored_counts), never a count of its own
        got = stored_counts(x["region"], x["name"], p) if p and x.get("name") else None
        n = got["listed"] if got else (counts(p)["listed"] if p else 0)
    except Exception:
        n = 0
    if n:
        bits.append(f"{n} compan{'y' if n == 1 else 'ies'}")
    day = _map_day(x["region"], p or {}, x)          # LIVE10A-005: the map's own day, as its page and the app say it
    if day:
        d = datetime.fromisoformat(day)
        bits.append(f"{d.day} {d.strftime('%b')}")
    return " · ".join(bits)


def not_found() -> str:
    site = settings.PUBLIC_SITE_URL
    head = stock_pages._head(page_title("Theme not found"), "No theme at this address.", site + "/themes", robots="noindex,follow")
    return stock_pages._page(head, None, '<h1>No theme at this address</h1><p><a href="/themes">See every theme</a></p>', src="theme")


def _missing():
    return HTMLResponse(not_found(), status_code=404, headers={"Cache-Control": MISSING_CACHE, "X-Robots-Tag": "noindex"})


@router.get("/themes")
@router.get("/themes/", include_in_schema=False)       # the site's host forwards /themes as /themes/: answered here, never a redirect to the API's own host (AS1)
def themes_all():
    return HTMLResponse(directory(None), headers={"Cache-Control": CACHE})


@router.get("/themes/{region}")
def themes_region(region: str):
    R = REGIONS.get(region)
    if not R:
        return _missing()
    return HTMLResponse(directory(R), headers={"Cache-Control": CACHE})


@router.get("/themes/{region}/{s}")
def theme_page(region: str, s: str):
    R = REGIONS.get(region)
    if not R or not SLUG.match(s or "") or len(s) > 80:
        return _missing()
    entry, canonical = find(R, s)
    if canonical:
        return RedirectResponse(path(R, canonical), status_code=301, headers={"Cache-Control": CACHE})
    p = payload(entry) if entry else None
    if not p:
        return _missing()
    v = view(entry, p)
    headers = {"Cache-Control": CACHE}
    if not v["indexable"]:
        headers["X-Robots-Tag"] = "noindex, follow"
    return HTMLResponse(render(v), headers=headers)


__all__ = ["router", "slug", "path", "entries", "find", "view", "render", "sitemap_rows", "indexable", "checked"]
