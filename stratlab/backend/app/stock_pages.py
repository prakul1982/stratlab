"""Public company pages for search engines: one plain HTML page per listed company (India, NSE and BSE-only; the US),
plus robots and sitemaps, so people searching for a company can find StratLab and sign up.

The app itself is a single-page app, so crawlers would see an empty shell. These pages are rendered here instead and
the site's host forwards /stocks/*, /sitemap.xml and /sitemaps/* to the API, the way public verdict links work.

Facts only: price, the 1-year range, reported numbers, recent filings and the Stage/trend facts, never advice. A
page is built from the cheap sources the deep dive already uses (reported numbers, the filings list, daily prices),
never from AI. Built pages are stored for a day and kept in memory, and fresh builds are rationed per minute, so a
crawler going through thousands of companies can't hammer the data sources: past the ration it gets the stored copy,
or a "busy, come back later" answer."""
import hashlib
import json
import re
import threading
import time
from collections import deque
from datetime import datetime, timezone
from html import escape as e
from urllib.parse import quote

from . import db, sector_members, universes
from .branding import public_text
from .config import settings
from .intel.net import TTLCache

REGIONS = {"in": "IN", "us": "US"}
FRESH = 24 * 3600              # a stored page is rebuilt after a day (prices move daily; the rest quarterly)
EMPTY_FOR = 6 * 3600           # a company the sources had nothing on: not asked again for this long
CHUNK = 5000                   # companies per sitemap file (the limit is 50,000; smaller files are quicker to fetch)
PEERS = 12
CACHE_CONTROL = "public, max-age=3600, s-maxage=86400, stale-while-revalidate=604800"
STAGE = {1: "Stage 1 (basing)", 2: "Stage 2 (advancing)", 3: "Stage 3 (topping)", 4: "Stage 4 (declining)"}
STAGE_WHY = {1: "the 150-day average has stopped falling, or the price has climbed above a falling average",
             2: "the price is above a rising 150-day average", 3: "the 150-day average has stopped rising, or the price is below a rising one",
             4: "the price is below a falling 150-day average"}


class Busy(Exception):
    """Too many fresh pages built this minute, and no stored copy to show."""


def _setting(key: str):
    try:
        raw = db.get_setting(key)
        return json.loads(raw) if raw else None
    except Exception:            # storage down or a damaged value: as if nothing were stored
        return None


def _put(key: str, value):
    try:
        db.set_setting(key, json.dumps(value))
    except Exception as ex:
        print("stock pages: could not save", key, str(ex)[:120])


# ---------- which companies have a page ----------
_companies: dict[str, tuple[float, dict]] = {}
_companies_lock = threading.Lock()


def save_list(region: str, rows: list[dict]):
    """Keep the day's list of listed companies ([{symbol, name}]); the daily job calls this."""
    if len(rows) >= 100:          # a broken answer keeps the last good list
        _put(f"stocks:list:{region}", {"at": datetime.now(timezone.utc).isoformat(),
                                       "rows": {r["symbol"]: r.get("name") or r["symbol"] for r in rows if r.get("symbol")}})
        _companies.pop(region, None)


def _seeds(region: str) -> set[str]:
    out = {s for members in sector_members.BY_MARKET.get(region, {}).values() for s in members}
    return out | {s for p in universes.PRESETS.get(region, []) for s in p["symbols"]}


def companies(region: str) -> dict[str, dict]:
    """{page symbol: {name, sym, bse}} for every company with a page. From the stored lists (the whole-market audit's
    and this module's daily one), and StratLab's own sector lists so there is always something. A BSE-only company's
    page is under its BSE trading symbol (or its scrip code when that isn't known); `sym` is what the sources take."""
    with _companies_lock:
        hit = _companies.get(region)
        if hit and time.time() - hit[0] < 3600:
            return hit[1]
    out: dict[str, dict] = {s: {"name": None, "sym": s, "bse": None} for s in _seeds(region)}
    own = (_setting(f"stocks:list:{region}") or {}).get("rows") or {}
    audit = _setting("audit:market-us:list" if region == "US" else "audit:market:list") or {}
    bse = (_setting("audit:bse-only") or {}) if region == "IN" else {}
    for rows in (own, audit):
        for sym, v in rows.items():
            name = v.get("name") if isinstance(v, dict) else v
            if sym.startswith("BSE:"):
                code = sym.split(":", 1)[1]
                ts = str((bse.get(code) or {}).get("ts") or "").upper()
                page = ts if ts and ts not in out else code
                out[page] = {"name": name, "sym": code, "bse": code}
            else:
                out[sym.upper()] = {"name": name, "sym": sym.upper(), "bse": None}
    out = {k: v for k, v in out.items() if k and len(k) <= 20 and "/" not in k}
    with _companies_lock:
        _companies[region] = (time.time(), out)
    return out


def find(region: str, symbol: str) -> tuple[str, dict] | None:
    """(page symbol, company) for a symbol in an address, case-insensitively; None for a company with no page."""
    cos = companies(region)
    s = (symbol or "").strip().upper()
    if s in cos:
        return s, cos[s]
    if s.isdigit() and len(s) == 6:          # a BSE-only company by its scrip code: its page is under its symbol
        return next(((k, v) for k, v in cos.items() if v["bse"] == s), None)
    return None


def path(region: str, symbol: str) -> str:
    return f"/stocks/{region.lower()}/{quote(symbol, safe='-.')}"


# ---------- the facts on a page ----------
def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f and abs(f) != float("inf") else None


def price_facts(bars: list[dict]) -> dict:
    """The last close, its date and the range over the last year of daily candles."""
    year = bars[-252:]
    highs = [x for x in (_num(b.get("h")) for b in year) if x is not None]
    lows = [x for x in (_num(b.get("l")) for b in year) if x is not None]
    return {"price": _num(bars[-1].get("c")), "price_at": str(bars[-1].get("t") or "")[:10],
            "high52": max(highs) if highs else None, "low52": min(lows) if lows else None}


def facts(region: str, symbol: str, p: dict, nums: dict, snap: dict, trend: dict | None, prices: dict | None,
          filings: list[dict], exchange: str, red_flags: int | None = None) -> dict:
    """What a page shows, from what the deep dive already works out. Plain numbers and words; nothing from AI.
    `red_flags` is how many red-flag filings (India) the last three months held, for the stock screens."""
    years = [{k: y.get(k) for k in ("year", "sales", "profit", "opm", "debt")} for y in (nums.get("years") or [])[-5:]]
    prices = prices or {}
    return {
        "region": region, "symbol": symbol, "name": public_text(p.get("name") or symbol), "exchange": exchange,
        "industry": [public_text(str(x)) for x in (p.get("industry_path") or []) if x][:4],
        "currency": "USD" if region == "US" else "INR", "unit": nums.get("unit") or ("$ million" if region == "US" else "₹ crore"),
        "price": prices.get("price") or snap.get("price"), "price_at": prices.get("price_at"),
        "high52": prices.get("high52") or snap.get("high52"), "low52": prices.get("low52") or snap.get("low52"),
        "market_cap": snap.get("market_cap_cr"), "pe": snap.get("pe"), "roe": snap.get("roe"), "roce": snap.get("roce"),
        "div_yield": snap.get("div_yield"),
        "net_margin": snap.get("net_margin"), "opm": snap.get("opm"), "debt": snap.get("debt_cr"), "debt_equity": snap.get("debt_equity"),
        "bank": bool(nums.get("bank")), "years": years,
        "growth": {k: (nums.get("growth") or {}).get(k) for k in ("sales_cagr_3y", "profit_cagr_3y", "sales_cagr_5y", "profit_cagr_5y")},
        "stage": (trend or {}).get("stage"), "stage_days": (trend or {}).get("stage_days"),
        "st_up": (trend or {}).get("st_up"), "st_days": (trend or {}).get("st_days"),
        "filings": [{"at": str(f.get("at") or "")[:10], "title": public_text(str(f.get("title") or ""))[:200]} for f in filings[:6]],
        "red_flags": red_flags, "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


class Pages:
    """Built pages: in memory for a few minutes, stored for a day, and rebuilt at most `per_minute` times a minute.
    `gather(region, company)` builds one company's facts from the sources, or returns None when they have nothing."""

    def __init__(self, gather, per_minute: int = 6):
        self.gather, self.per_minute = gather, per_minute
        self.mem = TTLCache(max_items=3000)
        self.recent: deque = deque()
        self.lock = threading.Lock()
        self.building: dict[str, threading.Lock] = {}

    def _may_build(self) -> bool:
        with self.lock:
            now = time.time()
            while self.recent and now - self.recent[0] > 60:
                self.recent.popleft()
            if len(self.recent) >= self.per_minute:
                return False
            self.recent.append(now)
            return True

    def get(self, region: str, symbol: str, co: dict) -> dict | None:
        """The company's facts; None when the sources have nothing on it. Raises Busy when a fresh build is due,
        none is allowed right now and nothing is stored."""
        key = f"stocks:page:{region}:{symbol}"
        hit = self.mem.get(key)
        if hit is not None:
            return hit or None
        stored = _setting(key)
        age = time.time() - (stored or {}).get("ts", 0)
        if stored and age < (FRESH if stored.get("facts") else EMPTY_FOR):
            self.mem.set(key, stored.get("facts") or {}, 600)
            return stored.get("facts")
        with self.lock:
            one = self.building.setdefault(key, threading.Lock())
        with one:                        # two crawlers on the same page: the second waits for the first's build
            hit = self.mem.get(key)
            if hit is not None:
                return hit or None
            if not self._may_build():
                if stored:
                    return stored.get("facts")
                raise Busy()
            try:
                got = self.gather(region, co)
            except Exception as ex:      # a source down: the stored copy, however old, or busy
                print("stock page build failed:", region, symbol, str(ex)[:160])
                if stored:
                    self.mem.set(key, stored.get("facts") or {}, 600)
                    return stored.get("facts")
                raise Busy() from None
            if got:
                got["symbol"] = symbol
                _note_industry(region, symbol, got.get("industry") or [])
            _put(key, {"ts": time.time(), "facts": got})
            self.mem.set(key, got or {}, 600)
            return got

    def html(self, region: str, symbol: str, co: dict) -> str:
        """The rendered page, kept in memory for ten minutes (the sector links read storage)."""
        key = f"html:{region}:{symbol}"
        hit = self.mem.get(key)
        if hit is None:
            hit = render(self.get(region, symbol, co), region, symbol, co["name"])
            self.mem.set(key, hit, 600)
        return hit


# ---------- companies in the same industry ----------
def _ind_key(region: str, industry: str) -> str:
    return f"stocks:ind:{region}:{hashlib.sha1(industry.lower().encode()).hexdigest()[:12]}"


def _note_industry(region: str, symbol: str, path_: list[str]):
    """Remember which companies are in an industry, so pages can link to each other."""
    if not path_:
        return
    key = _ind_key(region, path_[-1])
    have = [s for s in (_setting(key) or []) if s != symbol]
    _put(key, ([symbol] + have)[:60])


def peers(region: str, symbol: str, industry: list[str]) -> list[tuple[str, str]]:
    """(page symbol, name) of companies in the same sector or industry, then the companies next to it on the list."""
    cos = companies(region)
    got: list[str] = []
    for members in sector_members.BY_MARKET.get(region, {}).values():
        if symbol in members:
            got += members
    if industry:
        got = (_setting(_ind_key(region, industry[-1])) or []) + got
    out = list(dict.fromkeys(s for s in got if s != symbol and s in cos))[:PEERS]
    return [(s, cos[s]["name"] or s) for s in out]


def neighbours(region: str, symbol: str, n: int = 4) -> list[tuple[str, str]]:
    cos = companies(region)
    keys = sorted(cos)
    try:
        i = keys.index(symbol)
    except ValueError:
        return []
    near = keys[max(0, i - n):i] + keys[i + 1:i + 1 + n]
    return [(s, cos[s]["name"] or s) for s in near]


# ---------- the page ----------
def _fmt(v, digits: int = 1, suffix: str = "") -> str:
    v = _num(v)
    if v is None:
        return "–"
    return f"{v:,.{digits}f}{suffix}"


def _money(f: dict, v) -> str:
    v = _num(v)
    if v is None:
        return "–"
    return ("$" if f.get("currency") == "USD" else "₹") + f"{v:,.2f}"


def _date(iso: str | None) -> str:
    try:
        d = datetime.fromisoformat(str(iso)[:10])
        return f"{d.day} {d:%b %Y}"
    except (TypeError, ValueError):
        return ""


def description(f: dict) -> str:
    """The search result's snippet: what the page holds, in facts."""
    bits = [f"{f['name']} ({f['symbol']})"]
    if _num(f.get("price")) is not None:
        bits.append(f"last price {_money(f, f['price'])}")
    if _num(f.get("low52")) is not None and _num(f.get("high52")) is not None:
        bits.append(f"1-year range {_money(f, f['low52'])} to {_money(f, f['high52'])}")
    out = ", ".join(bits) + ". Revenue and profit trend, margins, debt, recent filings and the price trend, from reported data."
    return out[:300]


STYLE = """
:root{--bg:#F5F1E8;--card:#FFFDF8;--ink:#1D1B17;--muted:#6B655A;--line:#E2DBCC;--accent:#1F5F4A}
@media (prefers-color-scheme:dark){:root{--bg:#16140F;--card:#1F1C16;--ink:#F1EDE3;--muted:#A8A08F;--line:#353024;--accent:#7CC4A6}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:880px;margin:0 auto;padding:20px 16px 48px}a{color:var(--accent)}
header.top{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:18px}
.brand{font-weight:700;font-size:20px;text-decoration:none;color:var(--ink);display:inline-flex;align-items:center;min-height:40px}
h1{font-family:Georgia,serif;font-weight:400;font-size:clamp(28px,5vw,40px);line-height:1.15;margin:4px 0 6px}
h2{font-size:18px;margin:28px 0 10px}.muted{color:var(--muted)}.small{font-size:14px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;margin:12px 0}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}
.stat b{display:block;font-size:20px}.stat span{font-size:13px;color:var(--muted)}
.tbl{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:15px}th,td{text-align:right;padding:8px;border-bottom:1px solid var(--line);white-space:nowrap}
th:first-child,td:first-child{text-align:left}ul.plain{list-style:none;padding:0;margin:0}ul.plain li{padding:8px 0;border-bottom:1px solid var(--line)}
.btn{display:inline-flex;align-items:center;justify-content:center;min-height:44px;padding:10px 18px;border-radius:10px;background:var(--accent);color:#fff;text-decoration:none;font-weight:600}
.btn.ghost{background:transparent;color:var(--accent);border:1px solid var(--accent)}
.ctas{display:flex;flex-wrap:wrap;gap:10px;margin-top:12px}
.links{display:flex;flex-wrap:wrap;gap:8px}.links a{display:inline-flex;align-items:center;min-height:36px;padding:4px 12px;border:1px solid var(--line);border-radius:999px;text-decoration:none;background:var(--card)}
footer{margin-top:36px;font-size:13px;color:var(--muted)}
"""


def _head(title: str, desc: str, canonical: str, extra: str = "", robots: str = "index,follow") -> str:
    site = settings.PUBLIC_SITE_URL
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)}</title>
<meta name="description" content="{e(desc)}">
<meta name="robots" content="{robots}">
<link rel="canonical" href="{e(canonical)}">
<link rel="icon" href="{site}/favicon.svg" type="image/svg+xml">
<meta property="og:type" content="website"><meta property="og:site_name" content="StratLab">
<meta property="og:title" content="{e(title)}"><meta property="og:description" content="{e(desc)}">
<meta property="og:url" content="{e(canonical)}"><meta property="og:image" content="{site}/og-image.png">
<meta name="twitter:card" content="summary_large_image"><meta name="twitter:image" content="{site}/og-image.png">
{extra}<style>{STYLE}</style></head>"""


def _ld(obj) -> str:
    """JSON-LD for search engines; "<" is written as \\u003c so no value can open or close a tag inside it."""
    return '<script type="application/ld+json">' + json.dumps(obj, ensure_ascii=False).replace("<", "\\u003c") + "</script>"


def _links(region: str, rows: list[tuple[str, str]]) -> str:
    return '<div class="links">' + "".join(f'<a href="{e(path(region, s))}">{e(n if n == s else f"{n} ({s})")}</a>' for s, n in rows) + "</div>"


def render(f: dict | None, region: str, symbol: str, name: str | None) -> str:
    """The page. `f` is None when the sources had nothing on a listed company: a short page, kept out of the index."""
    site = settings.PUBLIC_SITE_URL
    canonical = site + path(region, symbol)
    name = (f or {}).get("name") or name or symbol
    market = "US" if region == "US" else "IN"
    deep = f"{site}/research/{market}/{quote(symbol, safe='')}/deep"
    test = f"{site}/new?market={market}&symbol={quote(symbol, safe='')}"
    country = "US" if region == "US" else "India"
    title = f"{name} ({symbol}) share price, financials and filings · StratLab"
    near = neighbours(region, symbol)
    if not f:
        desc = f"{name} ({symbol}), listed in {country}. Test a trading idea on it or read its numbers on StratLab."
        body = f"""<h1>{e(name)} <span class="muted">({e(symbol)})</span></h1>
<p class="muted">Listed in {country}. Its reported numbers aren't available to show here right now.</p>"""
        return (_head(title, desc, canonical, robots="noindex,follow") + "<body><main>" + _top() + body + _cta(symbol, test, deep)
                + (f"<h2>Other companies</h2>{_links(region, near)}" if near else "") + _foot(None) + "</main></body></html>")
    desc = description(f)
    as_of = _date(f.get("price_at")) or _date(f.get("built_at"))
    ld = _ld([{"@context": "https://schema.org", "@type": "Corporation", "name": name, "tickerSymbol": symbol,
               "url": canonical, **({"industry": f["industry"][-1]} if f.get("industry") else {})},
              {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
                  {"@type": "ListItem", "position": 1, "name": "StratLab", "item": site + "/"},
                  {"@type": "ListItem", "position": 2, "name": name, "item": canonical}]}])
    ind = " · ".join(f.get("industry") or [])
    parts = [f"""<h1>{e(name)} <span class="muted">({e(symbol)})</span></h1>
<p class="muted">{e(f.get("exchange") or country)}{(" · " + e(ind)) if ind else ""}</p>
<p class="small muted">As of {e(as_of)}. Facts from reported results, exchange filings and daily prices. Not investment advice.</p>"""]
    parts.append('<div class="card grid">' + "".join(
        f'<div class="stat"><span>{e(label)}</span><b>{e(val)}</b></div>' for label, val in _stats(f)) + "</div>")
    parts.append(_trend(f))
    parts.append(_table(f))
    if f.get("filings"):
        parts.append("<h2>Recent filings</h2><div class=\"card\"><ul class=\"plain\">" + "".join(
            f'<li><span class="muted small">{e(_date(x["at"]))}</span><br>{e(x["title"])}</li>' for x in f["filings"]) + "</ul></div>")
    parts.append(_cta(symbol, test, deep))
    same = peers(region, symbol, f.get("industry") or [])
    if same:
        parts.append(f"<h2>Same sector</h2>{_links(region, same)}")
    if near:
        parts.append(f"<h2>Other companies</h2>{_links(region, near)}")
    return _head(title, desc, canonical, ld) + "<body><main>" + _top() + "".join(parts) + _foot(as_of) + "</main></body></html>"


def _top() -> str:
    site = settings.PUBLIC_SITE_URL
    return f'<header class="top"><a class="brand" href="{site}/">StratLab</a><a class="btn ghost" href="{site}/">Sign up free</a></header>'


def _cta(symbol: str, test: str, deep: str) -> str:
    return f"""<div class="card"><h2 style="margin-top:0">Go further with {e(symbol)}</h2>
<p class="muted">Free to start: test a trading idea on {e(symbol)}'s real prices after costs, or open the full deep dive with ten years of numbers, red flags and management's record.</p>
<div class="ctas"><a class="btn" href="{e(test)}">Test a strategy on {e(symbol)}</a><a class="btn ghost" href="{e(deep)}">Open the full deep dive</a></div></div>"""


def _foot(as_of: str | None) -> str:
    return (f'<footer><p>{"Data as of " + e(as_of) + ". " if as_of else ""}StratLab shows facts from reported data for research and '
            "education. Nothing here is investment advice or a recommendation. Past prices don't predict future returns.</p>"
            f'<p><a href="{settings.PUBLIC_SITE_URL}/terms">Terms</a> · <a href="{settings.PUBLIC_SITE_URL}/privacy">Privacy</a></p></footer>')


def _stats(f: dict) -> list[tuple[str, str]]:
    unit = f.get("unit") or ""
    out = [("Last price", _money(f, f.get("price"))),
           ("1-year range", f"{_money(f, f.get('low52'))} to {_money(f, f.get('high52'))}"
            if _num(f.get("low52")) is not None and _num(f.get("high52")) is not None else "–"),
           (f"Market cap ({unit})", _fmt(f.get("market_cap"), 0)), ("P/E", _fmt(f.get("pe"))),
           ("Return on equity", _fmt(f.get("roe"), 1, "%"))]
    if not f.get("bank"):
        out += [("Operating margin", _fmt(f.get("opm"), 1, "%")), ("Debt to equity", _fmt(f.get("debt_equity"), 2))]
    out += [("Net margin", _fmt(f.get("net_margin"), 1, "%")), ("Dividend yield", _fmt(f.get("div_yield"), 2, "%"))]
    return [(k, v) for k, v in out if v != "–"]


def _trend(f: dict) -> str:
    s = f.get("stage")
    if not s and f.get("st_up") is None:
        return ""
    bits = []
    if s in STAGE:
        days = f.get("stage_days")
        bits.append(f"<li><b>{STAGE[s]}</b>: {STAGE_WHY[s]}{f', for {days} trading days' if days else ''}.</li>")
    if f.get("st_up") is not None:
        side = "above" if f["st_up"] else "below"
        d = f.get("st_days")
        bits.append(f"<li><b>Supertrend (10, 3)</b>: the price has closed {side} the line{f' for {d} trading days' if d else ''}.</li>")
    return '<h2>Price trend</h2><div class="card"><ul class="plain">' + "".join(bits) + "</ul></div>"


def _table(f: dict) -> str:
    ys = f.get("years") or []
    if not ys:
        return ""
    g = f.get("growth") or {}
    rows = [("Revenue", "sales", 0, ""), ("Net profit", "profit", 0, "")]
    if not f.get("bank"):
        rows += [("Operating margin", "opm", 1, "%"), ("Borrowings", "debt", 0, "")]
    head = "".join(f"<th>{e(str(y.get('year') or ''))}</th>" for y in ys)
    body = "".join(f"<tr><td>{label}</td>" + "".join(f"<td>{_fmt(y.get(k), d, sfx)}</td>" for y in ys) + "</tr>"
                   for label, k, d, sfx in rows if any(_num(y.get(k)) is not None for y in ys))
    growth = []
    if _num(g.get("sales_cagr_3y")) is not None:
        growth.append(f"revenue grew {_fmt(g['sales_cagr_3y'], 1, '%')} a year over three years")
    if _num(g.get("profit_cagr_3y")) is not None:
        growth.append(f"net profit {_fmt(g['profit_cagr_3y'], 1, '%')} a year")
    note = f'<p class="small muted">{e(f.get("unit") or "")}{". Compounded: " + ", ".join(growth) if growth else ""}.</p>'
    return f'<h2>Revenue and profit</h2><div class="card"><div class="tbl"><table><tr><th></th>{head}</tr>{body}</table></div>{note}</div>'


def with_ref(page: str, code: str) -> str:
    """A page whose links into the app (sign up, test, deep dive) carry an invite code, for someone who arrived from
    a shared card. Links to other company pages, and the canonical address, stay as they are."""
    site = re.escape(settings.PUBLIC_SITE_URL)

    def add(m):
        return f'{m.group(1)}{m.group(2)}{"&amp;" if "?" in m.group(2) else "?"}ref={code}"'
    return re.sub(rf'(<a [^>]*?href=")({site}/(?!stocks/)[^"#]*)"', add, page)


def not_found(region: str | None, symbol: str) -> str:
    site = settings.PUBLIC_SITE_URL
    return (_head("Company not found · StratLab", "No listed company has that symbol.", site + "/", robots="noindex,follow")
            + "<body><main>" + _top() + f"<h1>No company called {e(symbol[:40])}</h1>"
            f'<p class="muted">Check the symbol, or search every listed company on <a href="{site}/">StratLab</a>.</p>'
            + _foot(None) + "</main></body></html>")


# ---------- robots and sitemaps ----------
def robots() -> str:
    site = settings.PUBLIC_SITE_URL
    return f"User-agent: *\nAllow: /\nDisallow: /admin\nDisallow: /account\n\nSitemap: {site}/sitemap.xml\n"


def sitemap_index() -> str:
    site = settings.PUBLIC_SITE_URL
    names = ["pages"] + [f"stocks-{r}-{i + 1}" for r, R in REGIONS.items() for i in range(max(1, -(-len(companies(R)) // CHUNK)))]
    items = "".join(f"<sitemap><loc>{site}/sitemaps/{n}.xml</loc></sitemap>" for n in names)
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{items}</sitemapindex>\n'


def _urlset(locs: list[str]) -> str:
    items = "".join(f"<url><loc>{e(u)}</loc></url>" for u in locs)
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{items}</urlset>\n'


def sitemap(name: str) -> str | None:
    """One sitemap file: "pages" (the public site pages) or "stocks-in-1", "stocks-us-2"…; None for any other name."""
    site = settings.PUBLIC_SITE_URL
    if name == "pages":
        return _urlset([site + p for p in ("/", "/terms", "/privacy", "/refunds", "/contact")])
    bits = name.split("-")
    if len(bits) != 3 or bits[0] != "stocks" or bits[1] not in REGIONS or not bits[2].isdigit() or len(bits[2]) > 6:
        return None
    syms = sorted(companies(REGIONS[bits[1]]))
    i = int(bits[2]) - 1
    if i < 0 or (i * CHUNK >= len(syms) and i > 0):
        return None
    return _urlset([site + path(bits[1], s) for s in syms[i * CHUNK:(i + 1) * CHUNK]])
