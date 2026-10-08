"""Public company pages for search engines: one plain HTML page per listed company (India, NSE and BSE-only; the US),
plus robots and sitemaps, so people searching for a company can find StratLab and sign up.

The app itself is a single-page app, so crawlers would see an empty shell. These pages are rendered here instead and
the site's host forwards /stocks/*, /sitemap.xml and /sitemaps/* to the API, the way public verdict links work. They
wear the site's own header and footer, type and colours, so a visitor from a search lands on StratLab, not on a
different-looking site.

Facts only: price, the 1-year range, reported numbers, recent filings and the Stage/trend facts, never advice. A
page is built from the cheap sources the deep dive already uses (reported numbers, the filings list, daily prices),
never from AI. Fresh builds are rationed per minute, so a crawler going through thousands of companies can't hammer the
data sources: past the ration it gets the stored copy, or a "busy, come back later" answer.

One price rule on every page: the last close, with its date ("As of 7 Oct 2026 close"). A session still trading is
left out (its candle isn't a close yet), and a stored page is rebuilt once its market has closed again, so a page is
never a session behind and never mixes an intraday price with a daily label."""
import json
import re
import threading
import time
from collections import deque
from datetime import date, datetime, time as dtime, timedelta, timezone
from html import escape as e
from urllib.parse import quote
from zoneinfo import ZoneInfo

from . import db, instrument_kinds, sector_members, universes
from .branding import public_text
from .config import settings
from .intel.net import TTLCache

REGIONS = {"in": "IN", "us": "US"}
FRESH = 24 * 3600              # the longest a stored page is kept, whatever the market did (the reported numbers change quarterly)
EMPTY_FOR = 6 * 3600           # a company the sources had nothing on: not asked again for this long
SETTLE = 45 * 60               # a market's closing prices are taken as final this long after its close (past the price caches)
CHUNK = 5000                   # companies per sitemap file (the limit is 50,000; smaller files are quicker to fetch)
PEERS = 12
# browsers keep a page five minutes and the site's cache fifteen: a page follows its market's close within minutes, never
# a day later (a stored page itself is rebuilt after each close, see Pages.get)
CACHE_CONTROL = "public, max-age=300, s-maxage=900, stale-while-revalidate=600"
EXTREME = 100.0                # a margin beyond ±100% says revenue is tiny next to costs or profit
STAGE = {1: "Stage 1 (basing)", 2: "Stage 2 (advancing)", 3: "Stage 3 (topping)", 4: "Stage 4 (declining)"}
STAGE_WHY = {1: "the 150-day average has stopped falling, or the price has climbed above a falling average",
             2: "the price is above a rising 150-day average", 3: "the 150-day average has stopped rising, or the price is below a rising one",
             4: "the price is below a falling 150-day average"}
# well-known US funds and the index names people type: not companies, so no company page, but a page that says so
US_FUNDS = {"SPY", "QQQ", "IVV", "VOO", "VTI", "DIA", "IWM", "EFA", "EEM", "GLD", "SLV", "TLT", "AGG", "BND", "ARKK", "SCHD",
            "VGT", "VEA", "VWO", "SOXX", "SMH", "HYG", "LQD", "VNQ", "XLK", "XLF", "XLV", "XLE", "XLI", "XLY", "XLP", "XLU",
            "XLB", "XLRE", "XLC", "IGV", "XBI", "KRE", "KBE", "ITA", "XOP", "GDX", "ITB", "XHB", "XRT", "JETS", "TAN", "IYT",
            "CIBR", "PAVE", "IEMG", "IJH", "IJR", "VUG", "VTV", "VYM", "RSP", "IBIT"}
US_INDICES = {"SPX", "GSPC", "^GSPC", "NDX", "IXIC", "^IXIC", "DJI", "^DJI", "DJIA", "RUT", "VIX", "^VIX"}
IN_INDEX = re.compile(r"^(NIFTY|SENSEX|BANKNIFTY|FINNIFTY|MIDCPNIFTY|BANKEX|INDIAVIX|CNX)[A-Z0-9 &-]*$")


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
    """(page symbol, company) for a symbol in an address, case-insensitively; None for a company with no page. A US
    share class reads the same written either way (BRK.B, BRK-B, BRK/B), and the address then redirects to one."""
    cos = companies(region)
    s = (symbol or "").strip().upper()
    if s in cos:
        return s, cos[s]
    if region == "US":
        for alt in (re.sub(r"[./]", "-", s), s.replace("-", ".")):
            if alt in cos:
                return alt, cos[alt]
    if s.isdigit() and len(s) == 6:          # a BSE-only company by its scrip code: its page is under its symbol
        return next(((k, v) for k, v in cos.items() if v["bse"] == s), None)
    return None


def path(region: str, symbol: str) -> str:
    return f"/stocks/{region.lower()}/{quote(symbol, safe='-.')}"


def not_a_company(region: str | None, symbol: str) -> str | None:
    """What a symbol with no company page is, when it's plainly a fund or an index: "an ETF", "an index"…; None when
    nothing can be said (a mistyped or delisted symbol)."""
    s = (symbol or "").strip().upper()
    if region == "IN":
        kind = instrument_kinds.classify(s)
        if kind.startswith("etf"):
            return "an exchange-traded fund (ETF)"
        if kind == "reit":
            return "a REIT (a real-estate trust's units)"
        if kind == "invit":
            return "an InvIT (an infrastructure trust's units)"
        if kind == "sgb":
            return "a Sovereign Gold Bond"
        if IN_INDEX.match(s):
            return "an index"
    if region == "US":
        if s in US_FUNDS:
            return "an exchange-traded fund (ETF)"
        if s in US_INDICES:
            return "an index"
    return None


# ---------- the market's last close ----------
def last_close(region: str, now: datetime | None = None) -> tuple[date, datetime]:
    """(day, when) of the market's latest settled close: the latest trading day whose close was at least SETTLE ago.
    Before then, today's candle is still a session in progress, not a close."""
    from .data.calendar import is_trading_day
    from .data.markets import BY_ID
    m = BY_ID.get(region) or {}
    tz = ZoneInfo(m.get("tz") or "UTC")
    hh, mm = ((m.get("hours") or {}).get("close") or "23:59").split(":")
    local = (now or datetime.now(timezone.utc)).astimezone(tz)
    d = local.date()
    for _ in range(15):
        at = datetime.combine(d, dtime(int(hh), int(mm)), tz)
        if is_trading_day(region, d) and at + timedelta(seconds=SETTLE) <= local:
            return d, at
        d -= timedelta(days=1)
    return d, datetime.combine(d, dtime(int(hh), int(mm)), tz)


def closed_bars(bars: list[dict], region: str | None, now: datetime | None = None) -> list[dict]:
    """Daily candles up to the market's latest settled close: a session still trading (or only just shut) is left out,
    so the last candle is always a close."""
    if not region or not bars:
        return bars
    day = last_close(region, now)[0].isoformat()
    return [b for b in bars if str(b.get("t") or "")[:10] <= day]


# ---------- the facts on a page ----------
def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f and abs(f) != float("inf") else None


def price_facts(bars: list[dict], region: str | None = None, now: datetime | None = None) -> dict:
    """The last close, its date and the range over the last year of daily candles. With `region`, only closed sessions
    count (see closed_bars), so the price is the close of the day it's dated."""
    bars = closed_bars(bars, region, now)
    if not bars:
        return {}
    year = bars[-252:]
    highs = [x for x in (_num(b.get("h")) for b in year) if x is not None]
    lows = [x for x in (_num(b.get("l")) for b in year) if x is not None]
    return {"price": _num(bars[-1].get("c")), "price_at": str(bars[-1].get("t") or "")[:10], "price_basis": "close",
            "high52": max(highs) if highs else None, "low52": min(lows) if lows else None}


def dividend_yield(dividends: list[dict], price, as_of: str | None) -> float | None:
    """Dividends with an ex-date in the year to `as_of`, per share, as a share of `price` (%). 0 when the year had none:
    the price history lists every dividend, so none is a fact, not a gap. None without a price."""
    price = _num(price)
    if not price or price <= 0 or not as_of:
        return None
    try:
        end = date.fromisoformat(as_of[:10])
    except ValueError:
        return None
    start = (end - timedelta(days=365)).isoformat()
    total = sum(_num(d.get("amount")) or 0 for d in dividends or [] if start < str(d.get("date") or "") <= end.isoformat())
    return round(total / price * 100, 2)


def _dedupe(parts) -> list[str]:
    """An industry path without repeats ("Information Technology · Information Technology" once)."""
    out: list[str] = []
    for x in parts or []:
        x = str(x or "").strip()
        if x and x.lower() not in {o.lower() for o in out}:
            out.append(x)
    return out


def _ttm_profit(p: dict):
    """The last twelve months' net profit, when the numbers have a trailing-twelve-months column."""
    pl = p.get("pl") or {}
    cols = [str(c).strip().upper() for c in pl.get("cols") or []]
    row = next((v for k, v in (pl.get("rows") or {}).items() if str(k).lower().startswith("net profit")), None)
    if not cols or cols[-1] != "TTM" or not row or len(row) < len(cols):
        return None
    return _num(row[len(cols) - 1])


def facts(region: str, symbol: str, p: dict, nums: dict, snap: dict, trend: dict | None, prices: dict | None,
          filings: list[dict], exchange: str, red_flags: int | None = None) -> dict:
    """What a page shows, from what the deep dive already works out. Plain numbers and words; nothing from AI.
    `red_flags` is how many red-flag filings (India) the last three months held, for the stock screens."""
    years = [{k: y.get(k) for k in ("year", "sales", "profit", "opm", "debt")} for y in (nums.get("years") or [])[-5:]]
    prices = prices or {}
    return {
        "region": region, "symbol": symbol, "name": public_text(p.get("name") or symbol), "exchange": exchange,
        "industry": _dedupe(public_text(str(x)) for x in (p.get("industry_path") or []) if x)[:4],
        "currency": "USD" if region == "US" else "INR", "unit": nums.get("unit") or ("$ million" if region == "US" else "₹ crore"),
        "price": prices.get("price") or snap.get("price"), "price_at": prices.get("price_at"),
        "price_basis": prices.get("price_basis"),
        "high52": prices.get("high52") or snap.get("high52"), "low52": prices.get("low52") or snap.get("low52"),
        "market_cap": snap.get("market_cap_cr"), "market_cap_unit": "$ million" if region == "US" else "₹ crore", "pe": snap.get("pe"), "roe": snap.get("roe"), "roce": snap.get("roce"),
        "div_yield": snap.get("div_yield"), "profit_ttm": _ttm_profit(p),
        "net_margin": snap.get("net_margin"), "opm": snap.get("opm"), "debt": snap.get("debt_cr"), "debt_equity": snap.get("debt_equity"),
        "bank": bool(nums.get("bank")), "years": years, "currency_note": p.get("currency_note"),
        "growth": {k: (nums.get("growth") or {}).get(k) for k in ("sales_cagr_3y", "profit_cagr_3y", "sales_cagr_5y", "profit_cagr_5y")},
        "stage": (trend or {}).get("stage"), "stage_days": (trend or {}).get("stage_days"),
        "st_up": (trend or {}).get("st_up"), "st_days": (trend or {}).get("st_days"),
        "filings": [{"at": str(f.get("at") or "")[:10], "title": public_text(str(f.get("title") or ""))[:200]} for f in filings[:6]],
        "red_flags": red_flags, "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def fresh(stored: dict | None, region: str, now: float | None = None) -> bool:
    """Whether a stored page can be shown as it is: a page with facts until its market closes again (then its price is a
    session behind), and never past FRESH; a page the sources had nothing on for EMPTY_FOR."""
    if not stored:
        return False
    now = now if now is not None else time.time()
    ts = stored.get("ts", 0) or 0
    if not stored.get("facts"):
        return now - ts < EMPTY_FOR
    if now - ts >= FRESH:
        return False
    return ts >= last_close(region, datetime.fromtimestamp(now, timezone.utc))[1].timestamp() + SETTLE


class Pages:
    """Built pages: in memory for a few minutes, stored until the market's next close, and rebuilt at most `per_minute`
    times a minute. `gather(region, company)` builds one company's facts from the sources, or returns None when they
    have nothing."""

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
        if fresh(stored, region):
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
            _put(key, {"ts": time.time(), "facts": got})
            self.mem.set(key, got or {}, 600)
            return got

    def html(self, region: str, symbol: str, co: dict) -> str:
        """The rendered page, kept in memory for ten minutes (the sector links read the screens' index)."""
        key = f"html:{region}:{symbol}"
        hit = self.mem.get(key)
        if hit is None:
            hit = render(self.get(region, symbol, co), region, symbol, co["name"])
            self.mem.set(key, hit, 600)
        return hit


# ---------- companies in the same industry ----------
def _index_rows(region: str) -> list[dict]:
    from . import screens               # the screens' index of stored pages: names, industries and market values
    try:
        return screens.load_index(region).get("rows") or []
    except Exception:                    # no index yet, or storage down: StratLab's own sector lists instead
        return []


def peers(region: str, symbol: str, industry: list[str]) -> tuple[list[tuple[str, str]], bool]:
    """(page symbol, full name) of the largest companies in the same industry by market value, then in the same sector,
    then StratLab's own sector lists (the index's large companies) when the stored pages know too few; and whether the
    list is ranked by market value."""
    cos = companies(region)
    rows = [r for r in _index_rows(region) if r.get("symbol") != symbol and r.get("symbol") in cos and _num(r.get("market_cap"))]
    ind = [x.lower() for x in _dedupe(industry)]
    picked: list[dict] = []
    for match in ((lambda r: ind and str(r.get("industry") or "").lower() == ind[-1]),
                  (lambda r: ind and str(r.get("sector") or "").lower() == ind[0])):
        picked += sorted((r for r in rows if match(r) and r not in picked), key=lambda r: -_num(r["market_cap"]))
    out = [(r["symbol"], str(r.get("name") or cos[r["symbol"]]["name"] or r["symbol"])) for r in picked][:PEERS]
    ranked = bool(out)
    seen = {s for s, _ in out} | {symbol}
    for members in sector_members.BY_MARKET.get(region, {}).values():
        if symbol in members and len(out) < PEERS:
            for s in members:
                if s not in seen and s in cos and len(out) < PEERS:
                    out.append((s, cos[s]["name"] or s))
                    seen.add(s)
    return out, ranked


def largest(region: str, n: int = 24) -> list[tuple[str, str]]:
    """The market's largest companies with a stored page, by market value; StratLab's sector lists before there are any."""
    cos = companies(region)
    rows = sorted((r for r in _index_rows(region) if r.get("symbol") in cos and _num(r.get("market_cap"))),
                  key=lambda r: -_num(r["market_cap"]))
    out = [(r["symbol"], str(r.get("name") or r["symbol"])) for r in rows[:n]]
    if len(out) < n:
        have = {s for s, _ in out}
        for s in sorted(_seeds(region)):
            if s not in have and s in cos and len(out) < n:
                out.append((s, cos[s]["name"] or s))
    return out


def search(region: str, q: str, n: int = 30) -> list[tuple[str, str]]:
    """Companies whose symbol or name matches what was typed: the exact symbol first, then symbols that start with it,
    then names that contain it."""
    q = re.sub(r"\s+", " ", (q or "").strip()).upper()[:40]
    if not q:
        return []
    cos = companies(region)
    names = {r["symbol"]: str(r.get("name") or "") for r in _index_rows(region) if r.get("symbol")}
    hit = find(region, q)
    exact = [hit[0]] if hit else []
    starts = sorted(s for s in cos if s.startswith(q) and s not in exact)
    contains = sorted(s for s, v in cos.items() if s not in exact and s not in starts
                      and q in (names.get(s) or v.get("name") or "").upper())
    return [(s, names.get(s) or cos[s]["name"] or s) for s in (exact + starts + contains)[:n]]


# ---------- the page ----------
def _fmt(v, digits: int = 1, suffix: str = "") -> str:
    v = _num(v)
    if v is None:
        return "–"
    return f"{v:,.{digits}f}{suffix}"


def _pct(v, whole: bool = False) -> str:
    """A percentage; with `whole`, figures the source gives in whole percent show none of the ".0" they don't have."""
    v = _num(v)
    if v is None:
        return "–"
    return f"{v:,.0f}%" if whole and v == round(v) else f"{v:,.1f}%"


def _money(f: dict, v) -> str:
    v = _num(v)
    if v is None:
        return "–"
    return ("$" if f.get("currency") == "USD" else "₹") + f"{v:,.2f}"


def _inr_group(v: float) -> str:
    """Indian digit grouping: 77034 -> 77,034; 1905432 -> 19,05,432."""
    s = f"{abs(v):.0f}"
    head, tail = s[:-3], s[-3:]
    while len(head) > 2:
        tail = head[-2:] + "," + tail
        head = head[:-2]
    return ("-" if v < 0 else "") + (head + "," + tail if head else tail)


def cap_text(f: dict) -> str:
    """Market value in the words people use: "$4.87T", "$85.8B", "$950M"; "₹7.70 lakh crore", "₹20,345 crore"."""
    v = _num(f.get("market_cap"))
    if v is None or v <= 0:
        return "–"
    if f.get("currency") == "USD":                       # stored in $ million
        if v >= 1e6:
            return f"${v / 1e6:,.2f}T"
        if v >= 1e3:
            return f"${v / 1e3:,.1f}B"
        return f"${v:,.0f}M"
    if v >= 1e5:                                          # stored in ₹ crore
        return f"₹{v / 1e5:,.2f} lakh crore"
    return f"₹{_inr_group(v)} crore"


def _date(iso: str | None) -> str:
    try:
        d = datetime.fromisoformat(str(iso)[:10])
        return f"{d.day} {d:%b %Y}"
    except (TypeError, ValueError):
        return ""


def as_of_text(f: dict) -> str:
    """The page's one "as of": the close the price is from ("7 Oct 2026 close"), or when the page was built."""
    if f.get("price_at"):
        return _date(f["price_at"]) + " close"
    return _date(f.get("built_at"))


def description(f: dict) -> str:
    """The search result's snippet: what the page holds, in facts."""
    bits = [f"{f['name']} ({f['symbol']})"]
    if _num(f.get("price")) is not None:
        bits.append(f"last close {_money(f, f['price'])}" + (f" on {_date(f['price_at'])}" if f.get("price_at") else ""))
    if _num(f.get("low52")) is not None and _num(f.get("high52")) is not None:
        bits.append(f"1-year range {_money(f, f['low52'])} to {_money(f, f['high52'])}")
    out = ", ".join(bits) + ". Revenue and profit trend, margins, debt, recent filings and the price trend, from reported data."
    return out[:300]


# the site's own look (frontend/src/styles.css): paper and ink, one blue, Fraunces headings and IBM Plex text. The fonts
# are the site's own files (the frontend build copies them to /fonts), so a slow or missing font only falls back
STYLE = """
@font-face{font-family:"Fraunces";font-style:normal;font-weight:400;font-display:swap;src:url(/fonts/fraunces-latin-400-normal.woff2) format("woff2")}
@font-face{font-family:"IBM Plex Sans";font-style:normal;font-weight:400;font-display:swap;src:url(/fonts/ibm-plex-sans-latin-400-normal.woff2) format("woff2")}
@font-face{font-family:"IBM Plex Sans";font-style:normal;font-weight:600;font-display:swap;src:url(/fonts/ibm-plex-sans-latin-600-normal.woff2) format("woff2")}
@font-face{font-family:"Montserrat";font-style:normal;font-weight:300;font-display:swap;src:url(/fonts/montserrat-latin-300-normal.woff2) format("woff2")}
@font-face{font-family:"Montserrat";font-style:normal;font-weight:800;font-display:swap;src:url(/fonts/montserrat-latin-800-normal.woff2) format("woff2")}
:root{--paper:#F5F1E8;--card:#FFFDF8;--ink:#1D1B17;--ink-2:#2E2B25;--muted:#5C574D;--line:#E2DAC8;--line-2:#D8CFBA;--chip:#ECE6D8;
--blue:#1F4FB5;--blue-ink:#163A87;--on-ink:#F5F1E8;--orange-ink:#8A3A0A;--orange-soft:#F8E7D9;color-scheme:light;
--serif:"Fraunces",Georgia,serif;--sans:"IBM Plex Sans",system-ui,-apple-system,"Segoe UI",sans-serif}
@media (prefers-color-scheme:dark){:root{--paper:#141311;--card:#1F1D1A;--ink:#EFE9DC;--ink-2:#D8D1C2;--muted:#B3AC9C;--line:#34312A;
--line-2:#413D34;--chip:#2A2823;--blue:#7EA0F0;--blue-ink:#A9C0F6;--on-ink:#141311;--orange-ink:#F2A877;--orange-soft:#3A2416;color-scheme:dark}}
*{box-sizing:border-box}html,body{margin:0}
body{background:var(--paper);color:var(--ink);font:15px/1.55 var(--sans);-webkit-font-smoothing:antialiased;font-variant-numeric:tabular-nums}
a{color:var(--blue)}a:hover{color:var(--blue-ink)}
.skip{position:absolute;left:-9999px;padding:12px 16px}.skip:focus{left:16px;top:8px;z-index:2;background:var(--card);border-radius:10px}
.nav{max-width:1080px;margin:0 auto;padding:12px 16px;display:flex;align-items:center;gap:20px;border-bottom:1px solid var(--line)}
.brand{display:inline-flex;align-items:center;gap:8px;text-decoration:none;color:var(--ink);min-height:44px;font-size:17px}
.brand svg{height:36px;width:auto}.word{font-family:"Montserrat",var(--sans);font-weight:300;letter-spacing:-.035em}.word b{font-weight:800;letter-spacing:-.045em}
.nav nav{display:flex;gap:4px;flex:1;flex-wrap:wrap}.nav nav a{color:var(--ink-2);text-decoration:none;padding:10px 10px;border-radius:8px;font-weight:500}
.nav nav a:hover{background:var(--chip)}
.btn{display:inline-flex;align-items:center;justify-content:center;min-height:44px;padding:10px 18px;border-radius:10px;border:1px solid var(--ink);
background:var(--ink);color:var(--on-ink);text-decoration:none;font-weight:600}.btn:hover{color:var(--on-ink);filter:brightness(1.12)}
.btn.ghost{background:transparent;color:var(--ink)}.btn.ghost:hover{background:var(--card);color:var(--ink);filter:none}
main{max-width:880px;margin:0 auto;padding:24px 16px 48px}
h1{font-family:var(--serif);font-weight:400;font-size:clamp(28px,4vw,42px);line-height:1.15;letter-spacing:-.02em;margin:4px 0 6px}
h2{font-family:var(--serif);font-weight:600;font-size:21px;margin:30px 0 10px}.muted{color:var(--muted)}.small{font-size:14px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px;margin:12px 0}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:14px}
.stat b{display:block;font-size:20px;font-weight:600}.stat span{font-size:13px;color:var(--muted)}
.note{border-left:3px solid var(--line-2);padding:4px 0 4px 12px;margin:10px 0;font-size:14px;color:var(--ink-2)}
.note.warn{border-color:var(--orange-ink);background:var(--orange-soft);padding:8px 12px;border-radius:0 10px 10px 0}
details.how summary{cursor:pointer;min-height:40px;display:flex;align-items:center;font-weight:600}details.how li{margin:6px 0}
.tbl{overflow-x:auto;direction:rtl}.tbl table{direction:ltr}
table{border-collapse:collapse;width:100%;font-size:15px}th,td{text-align:right;padding:8px;border-bottom:1px solid var(--line);white-space:nowrap}
th:first-child,td:first-child{text-align:left;position:sticky;left:0;background:var(--card)}
.scroll-cue{display:none;font-size:13px;color:var(--muted);margin:0 0 6px}
@media (max-width:640px){.nav nav{display:none}.nav{justify-content:space-between}.scroll-cue{display:block}}
ul.plain{list-style:none;padding:0;margin:0}ul.plain li{padding:8px 0;border-bottom:1px solid var(--line)}
.ctas{display:flex;flex-wrap:wrap;gap:10px;margin-top:12px}
.links{display:flex;flex-wrap:wrap;gap:8px}.links a{display:inline-flex;align-items:center;min-height:40px;padding:4px 12px;border:1px solid var(--line);border-radius:999px;text-decoration:none;background:var(--card);color:var(--ink-2)}
form.find{display:flex;gap:8px;flex-wrap:wrap;margin:12px 0}form.find input,form.find select{min-height:44px;border:1px solid var(--line-2);border-radius:10px;padding:0 12px;background:var(--card);color:var(--ink);font:inherit}
form.find input{flex:1;min-width:200px}form.find button{cursor:pointer;font:inherit}
footer.site{border-top:1px solid var(--line);margin-top:24px}footer.site .in{max-width:880px;margin:0 auto;padding:20px 16px 40px;font-size:13px;color:var(--muted)}
footer.site nav{display:flex;flex-wrap:wrap;gap:4px 16px}footer.site nav a{color:var(--muted);display:inline-block;padding:8px 0}
"""

# the StratLab mark (frontend/src/lib/brand.ts), drawn inline so the header needs no extra request
LOGO = ('<svg viewBox="254 174 156 382" aria-hidden="true" focusable="false"><defs><linearGradient id="lg" gradientUnits="userSpaceOnUse" '
        'x1="392" y1="228" x2="300" y2="365"><stop offset="0" stop-color="#16CC8F"/><stop offset=".55" stop-color="#0C8A5C"/>'
        '<stop offset="1" stop-color="#063B28"/></linearGradient><linearGradient id="lr" gradientUnits="userSpaceOnUse" x1="285" '
        'y1="525" x2="345" y2="395"><stop offset="0" stop-color="#FF585E"/><stop offset=".5" stop-color="#E6333C"/><stop offset="1" '
        'stop-color="#930C17"/></linearGradient></defs><path fill="#FFFFFF" d="M266,308C268,322 300,338 330,352C370,372 400,392 404,418'
        'C408,432 394,448 390,460C390,440 360,416 320,396C285,378 262,362 257,343C254,330 258,316 266,308Z"/><rect x="381" y="177" '
        'width="10" height="56" rx="1.5" fill="#12C48A"/><path fill="url(#lg)" d="M345,252C310,268 266,290 266,308C268,322 300,338 330,352'
        'C370,372 400,392 404,418V234Q404,230 400,230H361Q357,230 357,234V348L345,342Z"/><rect x="277" y="455" width="11" height="98" '
        'rx="1.5" fill="#FF444B"/><path fill="url(#lr)" d="M257,343C262,362 285,378 320,396C362,416 391,436 390,460C390,480 350,510 316,530'
        'V405L306,399V453Q306,457 302,457H261Q257,457 257,453Z"/></svg>')


def _head(title: str, desc: str, canonical: str, extra: str = "", robots: str = "index,follow") -> str:
    site = settings.PUBLIC_SITE_URL
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)}</title>
<meta name="description" content="{e(desc)}">
<meta name="robots" content="{robots}">
<link rel="canonical" href="{e(canonical)}">
<link rel="icon" href="{site}/favicon.svg" type="image/svg+xml">
<meta name="theme-color" content="#F5F1E8">
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


def _top(sign_in: str | None = None) -> str:
    """The site's header: the logo home, the landing page's sections, company search, and Sign in. Sign in opens the
    app's own address for what the visitor is looking at (a company's page in the app), whose "Sign in to see …" screen
    signs in with Google and comes back to it."""
    site = settings.PUBLIC_SITE_URL
    sign_in = sign_in or f"{site}/mine"
    links = "".join(f'<a href="{site}/#{k}">{v}</a>' for k, v in (("trade", "Trade"), ("invest", "Invest"), ("money", "Money")))
    return (f'<a class="skip" href="#main">Skip to the page</a><header class="nav"><a class="brand" href="{site}/" aria-label="StratLab home">'
            f'{LOGO}<span class="word"><b>Strat</b>Lab</span></a><nav aria-label="Site">{links}<a href="{site}/pricing">Pricing</a>'
            f'<a href="/stocks">Companies</a></nav><a class="btn ghost" href="{e(sign_in)}">Sign in</a></header>')


def _foot() -> str:
    site = settings.PUBLIC_SITE_URL
    links = "".join(f'<a href="{site}{p}">{t}</a>' for p, t in (("/terms", "Terms of service"), ("/privacy", "Privacy policy"),
                                                                ("/refunds", "Cancellation and refunds"), ("/contact", "Contact us"),
                                                                ("/pricing", "Pricing")))
    return (f'<footer class="site"><div class="in"><p>Research and paper trading only. No real orders are placed. StratLab shows '
            "facts from reported data for research and education; nothing here is investment advice or a recommendation, and "
            f"past prices don't predict future returns. © {datetime.now(timezone.utc).year} StratLab.</p>"
            f'<nav aria-label="Policies">{links}</nav></div></footer>')


def _page(head: str, sign_in: str | None, body: str) -> str:
    return head + "<body>" + _top(sign_in) + f'<main id="main">{body}</main>' + _foot() + "</body></html>"


def _find_form(region: str | None, q: str = "") -> str:
    r = (region or "IN").lower()
    opts = "".join(f'<option value="{k}"{" selected" if k == r else ""}>{v}</option>' for k, v in (("in", "India"), ("us", "US")))
    return (f'<form class="find" action="/stocks" method="get" role="search"><label class="skip" for="q">Company name or symbol</label>'
            f'<input id="q" name="q" value="{e(q[:40])}" placeholder="Company name or symbol" autocomplete="off">'
            f'<label class="skip" for="m">Market</label><select id="m" name="m">{opts}</select>'
            '<button class="btn" type="submit">Find</button></form>')


def render(f: dict | None, region: str, symbol: str, name: str | None) -> str:
    """The page. `f` is None when the sources had nothing on a listed company: a short page, kept out of the index."""
    site = settings.PUBLIC_SITE_URL
    canonical = site + path(region, symbol)
    name = (f or {}).get("name") or name or symbol
    market = "US" if region == "US" else "IN"
    app = f"{site}/research/{market}/{quote(symbol, safe='')}"
    deep = app + "/deep"
    test = f"{site}/new?market={market}&symbol={quote(symbol, safe='')}"
    country = "US" if region == "US" else "India"
    title = f"{name} ({symbol}) share price, financials and filings · StratLab"
    if not f:
        desc = f"{name} ({symbol}), listed in {country}. Test a trading idea on it or read its numbers on StratLab."
        body = f"""<h1>{e(name)} <span class="muted">({e(symbol)})</span></h1>
<p class="muted">Listed in {country}. Its reported numbers aren't available to show here right now.</p>"""
        return _page(_head(title, desc, canonical, robots="noindex,follow"), app, body + _cta(symbol, test, deep))
    desc = description(f)
    as_of = as_of_text(f)
    ld = _ld([{"@context": "https://schema.org", "@type": "Corporation", "name": name, "tickerSymbol": symbol,
               "url": canonical, **({"industry": f["industry"][-1]} if f.get("industry") else {})},
              {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
                  {"@type": "ListItem", "position": 1, "name": "StratLab", "item": site + "/"},
                  {"@type": "ListItem", "position": 2, "name": name, "item": canonical}]}])
    ind = " · ".join(_dedupe(f.get("industry")))
    parts = [f"""<h1>{e(name)} <span class="muted">({e(symbol)})</span></h1>
<p class="muted">{e(f.get("exchange") or country)}{(" · " + e(ind)) if ind else ""}</p>
<p class="small muted" data-as-of>As of {e(as_of)}. Prices are closing prices; facts from reported results, exchange filings and daily prices. Not investment advice.</p>"""]
    parts.append('<div class="card grid">' + "".join(
        f'<div class="stat"><span>{e(label)}</span><b>{e(val)}</b></div>' for label, val in _stats(f)) + "</div>")
    parts += _notes(f)
    parts.append(_how(f))
    parts.append(_trend(f))
    parts.append(_table(f))
    if f.get("filings"):
        parts.append("<h2>Recent filings</h2><div class=\"card\"><ul class=\"plain\">" + "".join(
            f'<li><span class="muted small">{e(_date(x["at"]))}</span><br>{e(x["title"])}</li>' for x in f["filings"]) + "</ul></div>")
    parts.append(_cta(symbol, test, deep))
    same, ranked = peers(region, symbol, f.get("industry") or [])
    if same:
        parts.append(f"<h2>Same sector</h2>" + ('<p class="small muted">The largest companies in the same industry, by market value.</p>'
                                                 if ranked else "") + _links(region, same))
    return _page(_head(title, desc, canonical, ld), app, "".join(parts))


def _cta(symbol: str, test: str, deep: str) -> str:
    return f"""<div class="card"><h2 style="margin-top:0">Go further with {e(symbol)}</h2>
<p class="muted">Free to start: test a trading idea on {e(symbol)}'s real prices after costs, or open the full deep dive with ten years of numbers, red flags and management's record.</p>
<div class="ctas"><a class="btn" href="{e(test)}">Test a strategy on {e(symbol)}</a><a class="btn ghost" href="{e(deep)}">Open the full deep dive</a></div></div>"""


def _whole(values) -> bool:
    """Whether a source gives these percentages in whole numbers (the Indian results do): then no ".0" is shown."""
    vals = [v for v in (_num(x) for x in values) if v is not None]
    return bool(vals) and all(v == round(v) for v in vals)


def _stats(f: dict) -> list[tuple[str, str]]:
    unit = f.get("unit") or ""
    whole = f.get("region") == "IN" and _whole([f.get("opm")] + [y.get("opm") for y in f.get("years") or []])
    out = [("Last close" + (f", {_date(f['price_at'])}" if f.get("price_at") else ""), _money(f, f.get("price"))),
           ("1-year range", f"{_money(f, f.get('low52'))} to {_money(f, f.get('high52'))}"
            if _num(f.get("low52")) is not None and _num(f.get("high52")) is not None else "–"),
           ("Market cap", cap_text(f)), ("P/E", _fmt(f.get("pe")) if _num(f.get("pe")) is not None else "n/a"),
           (f"Net profit, last 12 months ({unit})", _fmt(f.get("profit_ttm"), 0)),
           ("Return on equity", _pct(f.get("roe")))]
    if not f.get("bank"):
        out += [("EBITDA margin", _pct(f.get("opm"), whole)), ("Debt to equity", _fmt(f.get("debt_equity"), 2))]
    out += [("Net margin", _pct(f.get("net_margin"))),
            ("Dividend yield", _fmt(f.get("div_yield"), 2, "%") if _num(f.get("div_yield")) is not None else "n/a")]
    return [(k, v) for k, v in out if v != "–"]


def extreme(f: dict) -> bool:
    """Whether a margin on the page is beyond ±100%: revenue tiny next to costs or profit, so the margins are arithmetic,
    not a description of the business."""
    vals = [f.get("opm"), f.get("net_margin")] + [y.get("opm") for y in f.get("years") or []]
    for y in f.get("years") or []:
        s, p = _num(y.get("sales")), _num(y.get("profit"))
        if s and p is not None and s > 0:
            vals.append(p / s * 100)
    return any(abs(v) > EXTREME for v in (_num(x) for x in vals) if v is not None)


def _notes(f: dict) -> list[str]:
    out = []
    unit = f.get("unit") or ""
    if f.get("region") == "US" and unit and not unit.startswith("$"):
        cur = unit.split()[0]
        out.append(f'<p class="note" data-currency-note>The share price and market cap are in US dollars. Reported results are in '
                   f"{e(unit)}, as the company files them; P/E and the dividend yield set them against the dollar price at the "
                   f"exchange rate when the page was built, while the table and the margins stay in {e(cur)}.</p>")
    if extreme(f):
        out.append('<p class="note warn" data-extreme>Revenue is very small next to this company\'s costs or profit, so its margins '
                   "here are extreme figures (beyond ±100%). They are what the reported numbers give, but they say little about "
                   "how the business earns.</p>")
    return out


def _how(f: dict) -> str:
    """How each figure is worked out, so a reader can check one against another."""
    india = f.get("region") == "IN"
    items = [
        "Last close: the closing price on the date shown. The page follows the market's close; it doesn't show prices "
        "during the session.",
        "Market cap: the last close times the shares in issue.",
        ("P/E: the last close divided by earnings per share over the last four reported quarters. Earnings per share use the "
         "profit that belongs to the company's shareholders, after minority interests, so P/E can differ from market cap "
         "divided by the net profit in the table (a full year, before minority interests)." if india else
         "P/E: market cap divided by net profit over the last four reported quarters (shown above as net profit, last 12 "
         "months). A loss has no P/E."),
        "EBITDA margin: operating profit before depreciation, interest and tax (and before other income), as a share of "
        "revenue." + (" The results give it in whole percent." if india else ""),
        "Net margin: net profit as a share of revenue in the latest reported period.",
        ("Dividend yield: the last year's dividends per share as a share of the price." if india else
         "Dividend yield: dividends per share with an ex-date in the year to the last close, as a share of that close. "
         "n/a when the price history couldn't be read."),
    ]
    return ('<details class="card how"><summary>How these figures are worked out</summary><ul class="small">'
            + "".join(f"<li>{e(t)}</li>" for t in items) + "</ul></details>")


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


def growth_words(what: str, v) -> str | None:
    """"revenue grew 6.4% a year", "revenue fell 14.7% a year", "revenue was flat"; None without a figure."""
    v = _num(v)
    if v is None:
        return None
    if abs(v) < 0.05:
        return f"{what} was flat"
    return f"{what} {'grew' if v > 0 else 'fell'} {abs(v):,.1f}% a year"


def _table(f: dict) -> str:
    ys = f.get("years") or []
    if not ys:
        return ""
    g = f.get("growth") or {}
    whole = f.get("region") == "IN" and _whole([y.get("opm") for y in ys])
    rows = [("Revenue", "sales", lambda v: _fmt(v, 0)), ("Net profit", "profit", lambda v: _fmt(v, 0))]
    if not f.get("bank"):
        rows += [("EBITDA margin", "opm", lambda v: _pct(v, whole)), ("Borrowings", "debt", lambda v: _fmt(v, 0))]
    head = "".join(f"<th>{e(str(y.get('year') or ''))}</th>" for y in ys)
    body = "".join(f"<tr><td>{label}</td>" + "".join(f"<td>{fmt(y.get(k))}</td>" for y in ys) + "</tr>"
                   for label, k, fmt in rows if any(_num(y.get(k)) is not None for y in ys))
    growth = [w for w in (growth_words("revenue", g.get("sales_cagr_3y")), growth_words("net profit", g.get("profit_cagr_3y"))) if w]
    note = f'<p class="small muted">{e(f.get("unit") or "")}{". Over three years, compounded: " + ", ".join(growth) if growth else ""}.</p>'
    cue = '<p class="scroll-cue" aria-hidden="true">Newest year on the right. Swipe for earlier years →</p>' if len(ys) > 2 else ""
    return (f'<h2>Revenue and profit</h2><div class="card">{cue}<div class="tbl" tabindex="0" role="region" aria-label="Revenue and profit by year">'
            f'<table><tr><th scope="col">Year</th>{head}</tr>{body}</table></div>{note}</div>')


def surveillance_html(flags: list[dict]) -> str:
    """The stock's exchange surveillance flags as small badges, each opening to what the exchange's measure is and
    the date of the list. Inline styles, so pages stored before this existed show it the same way."""
    if not flags:
        return ""
    badge = ("display:inline-block;border:1px solid #b45309;color:#92400e;border-radius:999px;padding:2px 10px;"
             "font-size:13px;font-weight:600;margin:0 6px 6px 0")
    items = "".join(
        f'<details style="margin:6px 0"><summary style="cursor:pointer;min-height:32px;line-height:32px">'
        f'<span style="{badge}">{e(f["short"])}</span> {e(f["label"])}</summary>'
        f'<p class="small" style="margin:4px 0 0">{e(f["text"])}'
        f'{" List as of " + e(_date(f["as_of"])) + "." if f.get("as_of") else ""}</p></details>' for f in flags)
    return (f'<div class="card" data-surveillance><h2 style="margin-top:0">Exchange surveillance</h2>{items}'
            '<p class="small muted">From the exchange\'s published surveillance lists: measures the exchange applies '
            'for a time. They are facts about trading rules, not a view on the company.</p></div>')


def with_surveillance(page: str, flags: list[dict]) -> str:
    """A stored page with today's surveillance flags added under the heading (the lists change daily; the page is
    kept until the next close)."""
    block = surveillance_html(flags)
    if not block:
        return page
    for anchor in ('<div class="card grid">', '<div class="card"><h2 style="margin-top:0">Go further'):
        i = page.find(anchor)
        if i >= 0:
            return page[:i] + block + page[i:]
    return page


def with_ref(page: str, code: str) -> str:
    """A page whose links into the app (sign up, test, deep dive) carry an invite code, for someone who arrived from
    a shared card. Links to other company pages, and the canonical address, stay as they are."""
    site = re.escape(settings.PUBLIC_SITE_URL)

    def add(m):
        return f'{m.group(1)}{m.group(2)}{"&amp;" if "?" in m.group(2) else "?"}ref={code}"'
    return re.sub(rf'(<a [^>]*?href=")({site}/(?!stocks/)[^"#]*)"', add, page)


def not_found(region: str | None, symbol: str) -> str:
    """No company page for this symbol: say what it is when it's plainly a fund or an index (and where it can be
    charted and tested), and offer the company search."""
    site = settings.PUBLIC_SITE_URL
    s = (symbol or "")[:40]
    kind = not_a_company(region, s)
    if kind:
        market = "US" if region == "US" else "IN"
        app = f"{site}/research/{market}/{quote(s.upper(), safe='')}"
        title = f"{s.upper()} is {kind} · StratLab"
        body = (f"<h1>{e(s.upper())} is {e(kind)}</h1>"
                f'<p>Public pages here cover listed companies, with their reported results. {e(s.upper())} isn\'t a company, so it '
                f"has no page of its own. Inside StratLab you can chart it and test a trading idea on its prices.</p>"
                f'<div class="ctas"><a class="btn" href="{e(app)}">Open {e(s.upper())} in StratLab</a>'
                f'<a class="btn ghost" href="/stocks">Find a company</a></div>')
        sign_in = app
    else:
        title = "Company not found · StratLab"
        body = (f"<h1>No company page for {e(s)}</h1>"
                '<p class="muted">Check the symbol, or find the company by its name.</p>' + _find_form(region))
        sign_in = None
    return _page(_head(title, "No listed company has that symbol.", site + "/stocks", robots="noindex,follow"), sign_in, body)


def index_page(region: str | None, q: str = "") -> str:
    """/stocks: find a company by name or symbol, and the largest companies in each market."""
    site = settings.PUBLIC_SITE_URL
    q = (q or "").strip()[:40]
    regions = [region] if region else ["IN", "US"]
    body = ['<h1>Company pages</h1><p class="muted">Every company listed in India (NSE and BSE) and the US: its last close, '
            "reported results, margins, debt and recent filings. Facts, not advice.</p>", _find_form(region, q)]
    if q:
        for r in regions:
            got = search(r, q)
            label = "India" if r == "IN" else "US"
            body.append(f"<h2>{label}: {len(got)} {'match' if len(got) == 1 else 'matches'} for “{e(q)}”</h2>"
                        + (_links(r.lower(), got) if got else '<p class="muted">None. Try part of the name, or the symbol.</p>'))
    else:
        for r in regions:
            big = largest(r)
            if big:
                body.append(f"<h2>{'India' if r == 'IN' else 'US'}: the largest companies</h2>{_links(r.lower(), big)}")
    canonical = site + (f"/stocks/{region.lower()}" if region else "/stocks")
    return _page(_head("Company pages: India and US · StratLab", "Find any company listed in India or the US: price, results, "
                       "margins, debt and filings, from reported data.", canonical, robots="noindex,follow" if q else "index,follow"),
                 None, "".join(body))


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
        return _urlset([site + p for p in ("/", "/stocks", "/terms", "/privacy", "/refunds", "/contact")])
    bits = name.split("-")
    if len(bits) != 3 or bits[0] != "stocks" or bits[1] not in REGIONS or not bits[2].isdigit() or len(bits[2]) > 6:
        return None
    syms = sorted(companies(REGIONS[bits[1]]))
    i = int(bits[2]) - 1
    if i < 0 or (i * CHUNK >= len(syms) and i > 0):
        return None
    return _urlset([site + path(bits[1], s) for s in syms[i * CHUNK:(i + 1) * CHUNK]])
