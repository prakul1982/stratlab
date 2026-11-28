"""The daily theme post's words (social103, owner 28 Nov: "daily posting on X and LinkedIn fully automated; I have no time to post").

One theme a day per network, picked in rotation from the public theme pages (public_themes.entries: the themes the site offers anyone),
written from that theme's live public page (public_themes.view): the same counts, names and dates the page shows, so a reader who opens
the link sees every figure of the post on it. Facts only:

  - only figures the public page itself shows (companies, layers, the map's date, the largest companies by market value at a named close,
    the membership check's tally on its day). The public pages' own rule (public_themes: "StratLab works out no figure on this page") holds
    for a post too, so no margin, median, share or sum is worked out here; the "concentration" a post says is a count (the largest layer's
    companies of the theme's) and the names of the largest companies;
  - every figure with its date;
  - never a buy, sell, target or recommendation word: lint() blocks a post holding one (the advice and promotion patterns the public pages
    use, and a plain list of words on top), and a fact line that would trip it (a company called "Target Corp") is left out, never the lint
    loosened;
  - "Facts only, not investment advice." on every post;
  - the theme's public page with ?from=x or ?from=linkedin, so a visit from a post can be told apart.

X: a thread of three posts, each at most X_LIMIT characters (counted plainly, a link at its full length: X counts it as 23, so this is the
safe side); LinkedIn: one post of at most LINKEDIN_LIMIT characters. Pure functions: nothing here reads a network or stores anything."""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta

X_LIMIT = 280
LINKEDIN_LIMIT = 1300
NETWORKS = ("x", "linkedin")
REPEAT_DAYS = 30                 # a theme is never posted twice on one network within this many days
NOT_ADVICE = "Facts only, not investment advice."

# a plain list on top of the public pages' advice and promotion patterns (grounding.ADVICE, share.PROMO), which cover phrases
BANNED = re.compile(
    r"\b(buy|buys|buying|bought|sell|sells|selling|sold|target|targets|targeted|recommend\w*|accumulate|accumulating|hold|"
    r"price\s+target|stop[- ]?loss|entry\s+point|undervalued|overvalued|upside|downside|multi-?baggers?|outperform\w*|underperform\w*|"
    r"top\s+picks?|must[- ]own|strong\s+buy|rally|breakout|cheap|bargain|guaranteed|returns?\s+of)\b", re.I)


def lint(text: str) -> list[str]:
    """The advice or promotion words in `text` (empty when it is fit to post)."""
    from .intel.grounding import ADVICE
    from .share import PROMO
    t = " ".join(str(text or "").split())
    hits = [m.group(0) for m in BANNED.finditer(t)]
    hits += [m.group(0) for m in ADVICE.finditer(t)]
    hits += [m.group(0) for m in PROMO.finditer(t)]
    out: list[str] = []
    for h in hits:
        if h.lower() not in (x.lower() for x in out):
            out.append(h)
    return out


class PostRefused(ValueError):
    """A post that may not go out: a banned word, a part too long, no link."""


def check(net: str, parts: list[str], link: str) -> None:
    """Raises PostRefused unless every part is fit to post: no banned word, within the network's length, the link and the not-advice line
    present. Run on every post before it is sent, whoever built it."""
    if not parts:
        raise PostRefused("Nothing to post.")
    limit = X_LIMIT if net == "x" else LINKEDIN_LIMIT
    for i, p in enumerate(parts):
        bad = lint(p)
        if bad:
            raise PostRefused(f"Part {i + 1} holds words a facts-only post never uses: {', '.join(bad)}.")
        if len(p) > limit:
            raise PostRefused(f"Part {i + 1} is {len(p)} characters, over {limit}.")
        if not p.strip():
            raise PostRefused(f"Part {i + 1} is empty.")
    whole = "\n".join(parts)
    if link not in whole:
        raise PostRefused("The post has no link to the theme's page.")
    if NOT_ADVICE not in parts[0]:
        raise PostRefused("The post doesn't say it is not investment advice.")


def day_text(iso) -> str:
    """'27 Nov 2026' from an ISO date or time; '' when there is none."""
    s = str(iso or "")[:10]
    try:
        d = datetime.strptime(s, "%Y-%m-%d")
    except ValueError:
        return ""
    return f"{d.day} {d.strftime('%b %Y')}"


def link_for(site: str, region: str, slug: str, net: str) -> str:
    return f"{site.rstrip('/')}/themes/{region.lower()}/{slug}?from={net}"


def _plural(n: int, one: str, many: str | None = None) -> str:
    return f"{n:,} {one if n == 1 else (many or one + 's')}"


def facts(v: dict) -> dict:
    """What a post may say, from a theme page's view (public_themes.view): each figure with its date, None where the page has none."""
    from .public_themes import short_label
    layers = [x for x in v.get("layers") or [] if x.get("companies")]
    label = short_label(v.get("label") or v.get("name") or "")
    market = "India" if v.get("region") == "IN" else "the US"
    biggest = max(layers, key=lambda x: (len(x["companies"]), -layers.index(x)), default=None)
    seen, top = set(), []
    for x in layers:
        for c in x["companies"]:
            if c.get("symbol") in seen or not isinstance(c.get("cap_v"), (int, float)) or not c.get("cap"):
                continue
            seen.add(c.get("symbol"))
            top.append(c)
    top.sort(key=lambda c: -c["cap_v"])
    ev = v.get("evidence") if isinstance(v.get("evidence"), dict) else None
    return {"label": label, "market": market, "members": int(v.get("members") or 0), "layers": len(layers),
            "layer_names": [x["name"] for x in layers], "day": v.get("day"), "prices": v.get("prices"),
            "biggest": {"name": biggest["name"], "n": len(biggest["companies"])} if biggest and len(layers) > 1 else None,
            "top": [{"name": c["name"], "cap": c["cap"]} for c in top[:3]],
            "verified": int(ev.get("description_verified") or 0) if ev and v.get("tally_at") else None,
            "all": int(v.get("all") or 0), "tally_at": v.get("tally_at")}


def _ok(line: str) -> bool:
    return bool(line) and not lint(line)


def top_line(f: dict, limit: int) -> str:
    """ "Largest by market value at the 27 Nov 2026 close: A (₹19.00 lakh crore), B (…), C (…)." with as many of the three largest as fit
    in `limit` characters, each with its value (a name is left out whole, never cut); "" when none fits or the page names no close."""
    close = day_text(f.get("prices"))
    names = [c for c in f.get("top") or [] if _ok(f"{c['name']} ({c['cap']})")]
    while names and close:
        line = f"Largest by market value at the {close} close: " + ", ".join(f"{c['name']} ({c['cap']})" for c in names) + "."
        if len(line) <= limit and _ok(line):
            return line
        names = names[:-1]
    return ""


def lines(f: dict, limit: int = X_LIMIT) -> dict:
    """The post's fact lines, each fit on its own and within `limit` characters (a line that trips the lint, a company named "Target Corp",
    is left out, as is one too long to say whole)."""
    head = f"{f['label']} in {f['market']}: {_plural(f['members'], 'listed company', 'listed companies')} in {_plural(f['layers'], 'layer')}"
    head += f" (map made {day_text(f['day'])})." if day_text(f["day"]) else "."
    keep = lambda line: line if line and _ok(line) and len(line) <= limit else None  # noqa: E731
    b = f.get("biggest")
    check_line = ""
    if f.get("verified") is not None and day_text(f.get("tally_at")) and f.get("all"):
        check_line = (f"Membership check of {day_text(f['tally_at'])}: {f['verified']:,} of the {f['all']:,} companies are confirmed by "
                      f"their own company description.")
    return {"head": keep(head),
            "layer": keep(f"Largest layer: {b['name']}, with {b['n']:,} of the {f['members']:,} companies." if b else ""),
            "top": keep(top_line(f, limit)),
            "check": keep(check_line)}


def build(net: str, v: dict, site: str) -> dict | None:
    """The post for one network from a theme page's view: {"parts": [...], "link", "figures", "theme": {...}}, or None when the theme gives
    no fit headline or the post would not pass check().

    X: the headline (companies, layers, the map's date), the not-advice line and the link first; then one post a further fact (the largest
    layer, the largest companies by market value, the membership check), a thread of three or four; with fewer than two further facts, one
    post. LinkedIn: one post with every fact, the layers' names, the link and the not-advice line."""
    f = facts(v)
    if not f["label"] or f["members"] <= 0 or f["layers"] <= 0:
        return None
    link = link_for(site, v["region"], v["slug"], net)
    if net == "x":
        ln = lines(f, X_LIMIT)
        if not ln["head"]:
            return None
        first = f"{ln['head']} {NOT_ADVICE}\n\nThe map, layer by layer: {link}"
        if len(first) > X_LIMIT:
            first = f"{ln['head']} {NOT_ADVICE}\n\n{link}"
        if len(first) > X_LIMIT:
            return None
        extra = [x for x in (ln["layer"], ln["top"], ln["check"]) if x]
        if len(extra) >= 2:
            parts = [first] + extra
        else:
            one = first.replace(f"{NOT_ADVICE}\n\n", f"{extra[0]} {NOT_ADVICE}\n\n", 1) if extra else first
            parts = [one if len(one) <= X_LIMIT else first]
    else:
        ln = lines(f, LINKEDIN_LIMIT)
        if not ln["head"]:
            return None
        body = [ln["head"]]
        names = f"Its layers: {', '.join(f['layer_names'][:8])}{', and more' if len(f['layer_names']) > 8 else ''}."
        if len(f["layer_names"]) > 1 and _ok(names):
            body.append(names)
        body += [x for x in (ln["layer"], ln["top"], ln["check"]) if x]
        tail = [f"Every company, layer by layer, on the theme's public page: {link}", NOT_ADVICE]
        while len("\n\n".join(body + tail)) > LINKEDIN_LIMIT and len(body) > 1:
            body.pop()
        parts = ["\n\n".join(body + tail)]
    figures = 2 + sum(1 for k in ("layer", "top", "check") if ln[k] and ln[k] in "\n".join(parts))
    try:
        check(net, parts, link)
    except PostRefused:
        return None
    return {"parts": parts, "link": link, "figures": figures,
            "theme": {"region": v["region"], "slug": v["slug"], "label": f["label"], "name": v.get("name")}}


def theme_key(t: dict) -> str:
    return f"{str(t.get('region') or '').upper()}/{t.get('slug') or ''}"


def order(entries: list[dict]) -> list[dict]:
    """The rotation: India and US themes taking turns, each market's by name (public_themes.entries' own order), so two days running are
    rarely the same market."""
    ind = [e for e in entries if e.get("region") == "IN"]
    us = [e for e in entries if e.get("region") == "US"]
    out = []
    for i in range(max(len(ind), len(us))):
        out += ind[i:i + 1] + us[i:i + 1]
    return out


def recent(rows: list[dict], net: str, today: date, days: int = REPEAT_DAYS) -> set[str]:
    """The themes posted (or perhaps posted) on `net` within `days` days of `today`."""
    since = (today - timedelta(days=days - 1)).isoformat()
    return {theme_key(r.get("theme") or {}) for r in rows
            if r.get("net") == net and str(r.get("day") or "") >= since and (r.get("status") in ("posted", "unknown", "sending") or r.get("ids"))}


def last_posted(rows: list[dict], net: str) -> str | None:
    """The theme of the newest post on `net` that went out (the rotation carries on after it)."""
    for r in sorted(rows, key=lambda r: str(r.get("at") or ""), reverse=True):
        if r.get("net") == net and (r.get("status") in ("posted", "unknown") or r.get("ids")):
            return theme_key(r.get("theme") or {})
    return None


def pick(net: str, entries: list[dict], rows: list[dict], today: date, make, limit: int = 60):
    """The next post for `net`: the first theme after the last one posted, in rotation, that wasn't posted within REPEAT_DAYS and gives a fit
    post. `make(entry)` -> the built post or None. Tries at most `limit` themes (bounded work: each one reads a stored page)."""
    ring = order(entries)
    if not ring:
        return None
    keys = [theme_key(e) for e in ring]
    last = last_posted(rows, net)
    start = (keys.index(last) + 1) if last in keys else 0
    skip = recent(rows, net, today)
    tried = 0
    for i in range(len(ring)):
        e = ring[(start + i) % len(ring)]
        if theme_key(e) in skip:
            continue
        tried += 1
        if tried > limit:
            break
        got = make(e)
        if got:
            return got
    return None
