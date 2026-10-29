"""/research/theme-dive: the theme page's deep dive (THEME-1), and the checks the theme map goes through before it is served.

- `checked(region, theme, map)`: the map with only the companies whose own description shows their work, and its tailwinds and
  risks beside the dated headline that supports them (theme_check.py). Kept for a day with the map.
- GET /theme-dive: the tables and sections worked out from the stored company facts (theme_data.py), kept in memory for half an hour.
- GET /theme-dive/prices: returns, breadth and relative strength from the companies' daily closes (theme_prices.py), read at a
  gentle pace and kept until the market's next close.
- GET /theme-dive/news: the latest dated headlines and exchange filings for the theme's companies.

No job of its own: everything is read when a page asks, through the caches the app already keeps. Memory: see DIVE_CACHE, PRICE_CACHE,
EVIDENCE_CACHE and VERDICTS below."""
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends

from .. import db
from ..ai_providers import AIError
from ..auth import current_profile
from ..guard import Window
from ..responses import err
from . import ai as A
from . import theme_check, theme_data, theme_prices
from .net import SourceError, TTLCache
from .news import aggregator_url, company_headline, plain_headline, publisher_url

router = APIRouter(tags=["research"])

DIVE_TTL = 30 * 60
DIVE_CACHE = TTLCache(max_items=24, max_bytes=3 * 1024 * 1024)            # a dive is about 60 KB of numbers
PRICE_CACHE = TTLCache(max_items=300, max_bytes=3 * 1024 * 1024)          # one company's reduced closes: 160 weekly closes and a few numbers (about 6 KB)
EVIDENCE_CACHE = TTLCache(max_items=600, max_bytes=1500 * 1024)           # one company's description, 700 characters
NEWS_CACHE = TTLCache(max_items=24, max_bytes=1024 * 1024)
EVIDENCE_DAYS = 30                                                        # a description is read again after this long
NO_DESCRIPTION_DAYS = 3                                                   # ...a company with none, after this long
VERDICTS: dict = {}                                                       # placement answers (a few hundred bytes each), cleared past VERDICT_KEEP
VERDICT_KEEP = 3000
PRICE_READS_PER_MINUTE = 20                                               # companies' candles read from the sources a minute, across every theme
PRICE_BUDGET = 45.0                                                       # seconds a request may spend reading candles
price_reads = Window()
_price_gate = threading.BoundedSemaphore(2)
_ai_gate = threading.Lock()
HISTORY_KEEP = 120                                                        # a theme's kept points: about two years of weekly ones


def _routes():
    from . import routes
    return routes


# ---------- the placement and claims checks ----------
def evidence_reader(region: str, names: dict):
    """A function symbol-list -> ({symbol: {about, industry}}, pending) that reads each company's own description once (the company
    page's profile), keeps it for EVIDENCE_DAYS, and reads no more than the request's budget allows."""
    R = _routes()

    def read(sym):
        key = f"theme:evidence:{region}:{sym}"
        hit = EVIDENCE_CACHE.get(key)
        if hit is None:
            try:
                got = db.json_value(db.get_setting(key), {})
            except Exception:
                got = {}
            if got.get("at"):
                age = (datetime.now(timezone.utc) - datetime.fromisoformat(got["at"])).days
                if age < (EVIDENCE_DAYS if got.get("about") else NO_DESCRIPTION_DAYS):
                    hit = got
        if hit is None:
            about, industry = "", ""
            if region == "IN":
                p = R.hub.screener.company(sym)
                about, industry = p.get("about") or "", " > ".join(p.get("industry_path") or [])
            if not about:
                w = R.hub.wiki.company(names.get(sym) or sym)
                about = (w or {}).get("extract") or ""
            hit = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "about": theme_check.clean_description(about), "industry": industry}
            try:
                db.set_setting(key, json.dumps(hit, ensure_ascii=False))
            except Exception as e:
                print("theme: description not kept:", sym, str(e)[:100])
        EVIDENCE_CACHE.set(key, hit, 6 * 3600)
        return hit if hit.get("about") else None

    def evidence_of(symbols):
        return theme_check.gather_evidence(symbols, read)
    return evidence_of


def _ask(system: str, text: str) -> dict:
    return A.ask(system, text, _routes()._ai)


def _headlines(region: str):
    R = _routes()

    def search(q):
        out = []
        for n in R.hub.news.search(q, region, limit=12):
            if plain_headline(n.get("headline")):
                url = publisher_url(n.get("url"))
                out.append({"headline": n["headline"], "at": n.get("at"), "source": n.get("source") or "", "url": "" if aggregator_url(url) else (url or "")})
        return out
    return search


def _map_names(m: dict) -> dict:
    return {c["ticker"]: c.get("name") or c["ticker"] for grp in (m.get("value_chain") or []) + (m.get("sub_themes") or []) for c in grp.get("companies") or []}


def _plain_claims(m: dict) -> dict:
    """Tailwinds and risks as {"text", "status": "general", "source": None} when they couldn't be checked."""
    m = dict(m)
    for k in ("tailwinds", "risks"):
        m[k] = [{"text": c["text"], "status": "general", "source": None} for c in m.get(k) or [] if isinstance(c, dict)]
    return m


def checked(region: str, theme: str, m: dict) -> dict:
    """The map as the page shows it: placements checked against the companies' own descriptions, claims against dated headlines. A part
    that can't be checked right now (a source or the AI is busy) is left to the next request, never shown unchecked."""
    key = (region, theme.lower(), int(float(m.get("generated_at") or 0)))
    hit = A.get("sector_checked", key)
    if hit is not None:
        return hit
    with _ai_gate:                                  # one check at a time: the sources and the AI are shared
        hit = A.get("sector_checked", key)
        if hit is not None:
            return hit
        if len(VERDICTS) > VERDICT_KEEP:
            VERDICTS.clear()
        out = theme_check.check_placements(m, evidence_reader(region, _map_names(m)), _ask, theme, VERDICTS)
        claims = A.get("sector_claims", key)
        if claims is None:
            try:
                claims = theme_check.check_claims(m, _headlines(region), _ask)
                A.keep("sector_claims", key, {"tailwinds": claims["tailwinds"], "risks": claims["risks"]}, 24 * 3600)
            except AIError:
                claims = _plain_claims(m)
        out["tailwinds"], out["risks"] = claims["tailwinds"], claims["risks"]
        if out["placements"]["checked"]:
            A.keep("sector_checked", key, out, 24 * 3600)
    return out


# ---------- the dive ----------
def sources(region: str, theme: str):
    """The stored readers a dive uses, each on the market it is for."""
    from .. import corp_actions, deals, redflags, report_card, results, shareholders
    R = _routes()
    today = datetime.now(R.IST).date() if region == "IN" else datetime.now(timezone.utc).date()
    hist_key = f"theme:hist:{region}:{theme_data.slug(theme)}"

    def history(_, point):
        try:
            pts = db.json_value(db.get_setting(hist_key), [])
        except Exception:
            pts = []
        pts = [p for p in pts if isinstance(p, dict) and p.get("d")]
        if point.get("pe") is not None and (not pts or (date.fromisoformat(point["d"]) - date.fromisoformat(pts[-1]["d"])).days >= 6):
            pts = (pts + [point])[-HISTORY_KEEP:]
            try:
                db.set_setting(hist_key, json.dumps(pts, separators=(",", ":")))
            except Exception as e:
                print("theme: history not kept:", str(e)[:100])
        return pts

    def card(sym, row):
        stored = report_card.stored(sym) if region == "IN" else None
        if not stored or not row:
            return None
        nums = {"years": [{"year": y["year"], "sales": y["sales"], "profit": y["profit"], "opm": y["opm"], "capex": None} for y in row["years"]],
                "quarters": [], "fye": 3, "bank": row.get("bank"), "unit": row.get("unit") or "₹ crore"}
        return report_card.view(stored, nums, today)

    def red(symbols, frm, to):
        return redflags.listing(region, frm=frm.isoformat(), to=to.isoformat(), symbols=symbols, size=200, today=today)["items"]
    return theme_data.Sources(
        today, facts=lambda s: R.public_facts(region, s) if callable(R.public_facts) else None, index_rows=lambda: R.index_rows(region),
        shareholding=(lambda s: shareholders.company(s)) if region == "IN" else (lambda s: None),
        insider_buys=(lambda: deals.buys().get("buys") or {}) if region == "IN" else (lambda: {}),
        results=lambda a, b, s: results.between(region, a, b, s), actions=lambda a, b, s: corp_actions.between(region, a, b, s),
        red_flags=red, card=card, history=history)


@router.get("/theme-dive")
def theme_dive(q: str, region: str = "IN", refresh: bool = False, profile=Depends(current_profile)):
    R = _routes()
    r, theme, m, _ = R.sector_map(profile, region, q, False)
    m = checked(r, theme, m)
    key = (r, theme.lower(), int(float(m.get("generated_at") or 0)), (m.get("placements") or {}).get("placed"))
    hit = None if refresh else DIVE_CACHE.get(key)
    if hit is None:
        hit = theme_data.build(r, theme, m, sources(r, theme))
        hit["placements"] = m.get("placements")
        if (m.get("placements") or {}).get("checked"):
            DIVE_CACHE.set(key, hit, DIVE_TTL)
    return R.ok(hit)


# ---------- prices ----------
def bars_loader(region: str):
    """symbol -> daily candles of three years and a bit, from the same source the company pages read; raises when the sources are busy."""
    from .. import main, universes
    reg = main.markets

    def load(sym):
        ids, _ = universes.resolve(reg, region, [{"symbol": sym}])
        if not ids:
            return []
        prov, inst = reg.resolve(ids[0])
        if not prov or not inst:
            return []
        return prov.history(inst, "1d", 1200)
    return load


def bench_loader(region: str):
    from .. import main, rotation
    reg = main.markets

    def load():
        bid, sym = rotation.benchmark_id(reg, region)
        prov, inst = reg.resolve(bid)
        return sym, prov.history(inst, "1d", 1200)
    return load


def _price_ttl(region: str) -> int:
    try:
        from .. import main
        return main._chart_ttl(region)
    except Exception:
        return 900


def gather_prices(region: str, members: list[tuple[str, str]], load, bench, budget: float = PRICE_BUDGET) -> dict:
    """The price section for the members, reading each company's candles that isn't already reduced and kept; a company whose read has
    to wait (the minute's allowance is used, or the time is up) is counted as pending and read on a later request."""
    started = time.monotonic()
    reduced: dict = {}
    todo = []
    for sym, _ in members:
        hit = PRICE_CACHE.get(f"{region}:{sym}")
        if hit is not None:
            reduced[sym] = hit or None
        else:
            todo.append(sym)

    def one(sym):
        if time.monotonic() - started > budget or not price_reads.hit("all", PRICE_READS_PER_MINUTE):
            return sym, "late"
        try:
            return sym, theme_prices.reduce_bars(load(sym))
        except Exception as e:
            print("theme prices: candles not read:", sym, type(e).__name__, str(e)[:100])
            return sym, "late"
    if todo:
        with ThreadPoolExecutor(max_workers=min(4, len(todo))) as pool:
            for sym, red in pool.map(one, todo):
                if red == "late":
                    continue
                PRICE_CACHE.set(f"{region}:{sym}", red or {}, _price_ttl(region))
                reduced[sym] = red
    pending = sum(1 for s, _ in members if s not in reduced)
    bname, braw = None, None
    try:
        bname, braw = bench()
    except Exception as e:
        print("theme prices: index not read:", type(e).__name__, str(e)[:100])
    return theme_prices.compute(members, reduced, theme_prices.reduce_bars(braw or []), bname or "", pending)


@router.get("/theme-dive/prices")
def theme_dive_prices(q: str, region: str = "IN", profile=Depends(current_profile)):
    R = _routes()
    r, theme, m, _ = R.sector_map(profile, region, q, False)
    m = checked(r, theme, m)
    names = _map_names(m)
    placed = {c["ticker"]: names.get(c["ticker"]) for grp in (m.get("value_chain") or []) + (m.get("sub_themes") or []) for c in grp.get("companies") or []}
    members = sorted(placed.items())
    if not members:
        return R.ok({"companies": [], "pending": 0, "line": None, "returns": None, "median": {}, "benchmark": ""})
    if not _price_gate.acquire(timeout=30):
        err(503, "busy", "Prices are busy right now. Try again in a minute.")
    try:
        out = gather_prices(r, members, bars_loader(r), bench_loader(r))
    finally:
        _price_gate.release()
    return R.ok(out)


# ---------- news ----------
NEWS_COMPANIES = 6            # the largest companies whose news is searched
NEWS_ITEMS = 20


def theme_news(region: str, theme: str, members: list[dict], search, today: date) -> list[dict]:
    """The latest dated items for a theme: exchange filings kept on each company's page (a company's own announcements), and headlines found
    for the theme and its largest companies. `members`: [{symbol, name, cap, filings}]. Newest first; a headline appears once."""
    items = []
    for c in members:
        for f in c.get("filings") or []:
            items.append({"at": f.get("at"), "headline": f.get("name") or f.get("title"), "company": c["name"], "symbol": c["symbol"],
                          "source": "Exchange filing" if region == "IN" else "SEC filing", "url": f.get("url") or "", "kind": "filing"})
    queries = [(theme, None)] + [(f"{c['name']} share price" if region == "IN" else f"{c['name']} stock", c) for c in sorted(members, key=lambda c: -(c.get("cap") or 0))[:NEWS_COMPANIES]]

    def one(item):
        q, c = item
        try:
            rows = search(q)
        except Exception as e:
            print("theme news: not read:", q, type(e).__name__, str(e)[:100])
            return []
        out = []
        for n in rows:
            if c and not company_headline(c["name"], c["symbol"], n["headline"]):
                continue
            out.append({"at": n.get("at"), "headline": n["headline"], "company": c["name"] if c else None, "symbol": c["symbol"] if c else None,
                        "source": n.get("source") or "", "url": n.get("url") or "", "kind": "news"})
        return out
    with ThreadPoolExecutor(max_workers=3) as pool:
        for rows in pool.map(one, queries):
            items += rows
    seen, out = set(), []
    for i in sorted((i for i in items if i.get("at") and i.get("headline")), key=lambda i: str(i["at"]), reverse=True):
        k = " ".join(str(i["headline"]).lower().split())[:80]
        if k in seen:
            continue
        seen.add(k)
        out.append({**i, "at": str(i["at"])[:10]})
    return out[:NEWS_ITEMS]


@router.get("/theme-dive/news")
def theme_dive_news(q: str, region: str = "IN", profile=Depends(current_profile)):
    R = _routes()
    r, theme, m, _ = R.sector_map(profile, region, q, False)
    m = checked(r, theme, m)
    key = (r, theme.lower(), int(float(m.get("generated_at") or 0)))
    hit = NEWS_CACHE.get(key)
    if hit is None:
        names = _map_names(m)
        members = []
        for sym, name in sorted(names.items()):
            f = (R.public_facts(r, sym) if callable(R.public_facts) else None) or {}
            members.append({"symbol": sym, "name": name, "cap": f.get("market_cap"), "filings": (f.get("filings") or [])[:6]})
        today = datetime.now(timezone.utc).date()
        hit = {"items": theme_news(r, theme, members, _headlines(r), today), "as_of": datetime.now(timezone.utc).isoformat(timespec="minutes")}
        NEWS_CACHE.set(key, hit, 20 * 60)
    return R.ok(hit)
