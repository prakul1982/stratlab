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
left out (its candle isn't a close yet, and an Indian day's official close is only taken some hours after the bell), a
stored page is rebuilt once its market has closed again, and a background job re-reads the price of every stored page
after each close (Pages.refresh_prices). A page whose price is still older than the market's last close says so: "Last
price, 5 Oct 2026", never "close" (R6V-002).

Market values are checked before they are shown or ranked (cap_problem): an American depositary share counted as an
ordinary share, a share count a thousand times off or a shell's stray trade can make a $46 trillion bank. Such a value
is n/a on the page and left out of every "largest" list, and so is a P/E above 1,000 (R6V-001)."""
import json
import re
import threading
import time
from collections import deque
from datetime import date, datetime, time as dtime, timedelta, timezone
from html import escape as e
from urllib.parse import quote
from zoneinfo import ZoneInfo

from . import db, instrument_kinds, sector_members, site_pages, universes
from .branding import public_text
from .config import settings
from .intel.net import TTLCache

REGIONS = {"in": "IN", "us": "US"}
FRESH = 24 * 3600              # the longest a stored page is kept, whatever the market did (the reported numbers change quarterly)
EMPTY_FOR = 6 * 3600           # a company the sources had nothing on: not asked again for this long
SETTLE = 45 * 60               # a market's closing prices are taken as final this long after its close (past the price caches)
# India's official closing prices (the last half hour's average, not the last trade) reach the daily candles some time
# after the bell; until then the day's candle can carry a last-traded price, so the page keeps the day before (R6V-002)
SETTLE_BY = {"IN": 3 * 3600}
# pages built before market values (and depositary shares, R7O-004) were checked, or before every class of shares was
# counted and P/E had one definition (R7V-001, R7V-002), or (5) before an Indian page's dividend yield came from the
# company's own dividends list (R8O-001: TCS's stored page kept 3.08%, the last reported year's, after the fix went
# live, since only US pages were checked for their version), or (6) before a foreign filer's market value was checked
# against its own profit and an Indian market value stopped counting shares net of those its employee trusts hold
# (R8V-001, R8V-005), are rebuilt when next opened, in either market. Until then such a page is served brought in line
# where that's cheap (main.stock_page_older_facts), and the screens' indexer rebuilds the largest first (R8V-003)
FACTS_VERSION = 6
ADR_CHECKED = 3                # the version from which a depositary share's market value was checked (screens.row)
PE_BASIS_KEPT = 4              # the version from which a page keeps what its P/E's earnings cover (pe_basis, pe_end)
PE_STALE_DAYS = 456            # a P/E on a year that ended more than about 15 months before the price is n/a (R7V-003)
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
# a market value above this (in the page's unit: $ million, ₹ crore) is a data error: no company is worth $8 trillion
CAP_CEILING = {"US": 8_000_000.0, "IN": 10_000_000.0}
PE_MAX = 1000.0                # a P/E above this says the market value or the profit is off, not the company: n/a
# a foreign filer's (20-F, depositary shares) market value against its own reported profit (R8V-001: Mizuho at a P/E of
# 1.8, its depositary ratio read ten times too high): a P/E under PE_MIN_FOREIGN on a profit, or a P/E and the market
# value over that profit more than PE_GAP times apart, says the share count or the ratio is off, not the company
PE_MIN_FOREIGN = 3.0
PE_GAP = 2.0
UNREAD_FRESH = 3600            # seconds a page built without its latest annual report (unreadable just then) is kept
PS_MAX = 250.0                 # market value over a year's revenue, for a company with $1 billion of revenue or more
PRE_REVENUE_MAX = 20_000.0     # $ million: a company with under $10 million of revenue isn't worth $20 billion
# what the price source calls something that trades but isn't a company's stock
FUND_TYPES = {"ETF": "an exchange-traded product (an ETF or ETN)", "MUTUALFUND": "a fund", "INDEX": "an index",
              "CURRENCY": "a currency", "CRYPTOCURRENCY": "a crypto asset", "FUTURE": "a futures contract"}


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


def nse_twins() -> dict[str, str]:
    """{BSE scrip code: NSE symbol} for companies whose BSE page sits beside an NSE one (the BSE list's trading symbol
    is also an NSE page), so a list of companies can keep each one once."""
    cos = companies("IN")
    bse = _setting("audit:bse-only") or {}
    out = {}
    for code, v in bse.items():
        ts = str((v or {}).get("ts") or "").upper() if isinstance(v, dict) else ""
        if ts and ts in cos and cos[ts].get("bse") is None and code in cos:
            out[code] = ts
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
    if region == "US" and callable(share_class_page):
        # another class of the same company's common stock (GOOG beside GOOGL, BRK-A beside BRK-B): its one page
        # (R7V-001: /stocks/us/GOOG was a 404); the address then redirects there
        try:
            other = share_class_page(s)
        except Exception:
            other = None
        if other and other in cos:
            return other, cos[other]
    return None


share_class_page = None          # (US ticker) -> the page symbol of the same company's other class, or None (set by main)


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
def settle(region: str | None) -> int:
    """Seconds after a market's close before its closing prices are taken as final."""
    return SETTLE_BY.get(region or "", SETTLE)


def last_close(region: str, now: datetime | None = None) -> tuple[date, datetime]:
    """(day, when) of the market's latest settled close: the latest trading day whose close was at least settle(region)
    ago. Before then, today's candle is still a session in progress (or not yet the official close), not a close."""
    from .data.calendar import is_trading_day
    from .data.markets import BY_ID
    m = BY_ID.get(region) or {}
    tz = ZoneInfo(m.get("tz") or "UTC")
    hh, mm = ((m.get("hours") or {}).get("close") or "23:59").split(":")
    local = (now or datetime.now(timezone.utc)).astimezone(tz)
    d = local.date()
    for _ in range(15):
        at = datetime.combine(d, dtime(int(hh), int(mm)), tz)
        if is_trading_day(region, d) and at + timedelta(seconds=settle(region)) <= local:
            return d, at
        d -= timedelta(days=1)
    return d, datetime.combine(d, dtime(int(hh), int(mm)), tz)


def session_day(region: str, now: datetime | None = None) -> date:
    """The trading session a price read now belongs to: today once the market has opened, else the latest trading day
    before (R7V-004: a price read at 07:15 in India on 9 Oct is 8 Oct's, not 9 Oct's)."""
    from .data.calendar import is_trading_day
    from .data.markets import BY_ID
    m = BY_ID.get(region) or {}
    tz = ZoneInfo(m.get("tz") or "UTC")
    hh, mm = ((m.get("hours") or {}).get("open") or "00:00").split(":")
    local = (now or datetime.now(timezone.utc)).astimezone(tz)
    d = local.date()
    for _ in range(15):
        if is_trading_day(region, d) and datetime.combine(d, dtime(int(hh), int(mm)), tz) <= local:
            return d
        d -= timedelta(days=1)
    return d


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
            "high52": max(highs) if highs else None, "low52": min(lows) if lows else None,
            "price_official": bool(bars[-1].get("official"))}


def with_new_close(f: dict, bars: list[dict], analyse=None) -> dict:
    """A page's facts at a newer close (already only closed sessions): the price, its date and the year's range from
    the candles, the trend when `analyse` is given, and the market value and P/E scaled by the price's move (shares and
    profit as reported), the dividend yield against it. Unchanged when the candles have no newer close."""
    new = price_facts(bars) if bars else {}
    old_p, new_p = _num(f.get("price")), _num(new.get("price"))
    newer = str(new.get("price_at") or "") > str(f.get("price_at") or "")
    # a last trade (no candles when the page was built) gives way to that session's close (R7V-004)
    same_day_close = not is_close(f) and str(new.get("price_at") or "") == str(f.get("price_at") or "")
    if not new_p or new_p <= 0 or not (newer or same_day_close):
        return f
    out = {**f, **{k: new[k] for k in ("price", "price_at", "price_basis", "high52", "low52", "price_official") if new.get(k) is not None}}
    if old_p and old_p > 0:
        k = new_p / old_p
        for key in ("market_cap", "pe"):
            if _num(f.get(key)) is not None:
                out[key] = round(_num(f[key]) * k, 2)
        if _num(f.get("div_yield")) is not None:
            out["div_yield"] = round(_num(f["div_yield"]) / k, 2)
    if analyse:
        try:
            t = analyse(bars) or {}
            out.update({k: t.get(k) for k in ("stage", "stage_days", "st_up", "st_days")})
        except Exception:                 # too few candles for the trend: the old one stays
            pass
    return out


def with_official_close(f: dict, close) -> dict:
    """A page's facts with the exchange's official close of the same day in place of the candle's last trade
    (R7O-004): the market value and P/E move with it, the dividend yield against it, the year's range takes it in."""
    old, new = _num(f.get("price")), _num(close)
    if not new or new <= 0:
        return f
    out = {**f, "price_official": True, "price_basis": "close"}
    if not old or old <= 0 or old == new:
        return out
    k = new / old
    out["price"] = new
    for key in ("market_cap", "pe"):
        if _num(f.get(key)) is not None:
            out[key] = round(_num(f[key]) * k, 2)
    if _num(f.get("div_yield")) is not None:
        out["div_yield"] = round(_num(f["div_yield"]) / k, 2)
    if _num(f.get("high52")) is not None and new > _num(f["high52"]):
        out["high52"] = new
    if _num(f.get("low52")) is not None and new < _num(f["low52"]):
        out["low52"] = new
    return out


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


def _latest_sales(f: dict):
    """The latest year's revenue from the page's own table, when it is in the market value's unit."""
    unit, cap_unit = str(f.get("unit") or ""), str(f.get("market_cap_unit") or "")
    if not unit or unit != cap_unit:
        return None
    vals = [_num(y.get("sales")) for y in f.get("years") or []]
    vals = [v for v in vals if v is not None]
    return vals[-1] if vals else None


def cap_problem(f: dict | None) -> str | None:
    """Why a page's market value can't be right, or None when it passes every check (or there is none). Checked:
    - depositary shares whose ratio to ordinary shares couldn't be read (the value counts ordinary shares at the ADS price);
    - above any company's worth (CAP_CEILING);
    - a US company's value against its revenue: over PS_MAX times a year's revenue of $1 billion or more, or over
      PRE_REVENUE_MAX with almost no revenue (a shell's stray trade, a share count far off);
    - a P/E above PE_MAX on a company reporting in another currency (a page built before the revenue was stored);
    - a foreign filer's (see foreign_filer) value against its own profit: a P/E under PE_MIN_FOREIGN on a profit, or a
      P/E and the market value over the reported profit ("profit_usd") more than PE_GAP times apart (R8V-001);
    - a foreign company's page stored before depositary shares were checked (the screens leave its value out too, so
      the page and the lists by size agree: R8V-004)."""
    if not f:
        return None
    cap = _num(f.get("market_cap"))
    if cap is None or cap <= 0:
        return None
    region = f.get("region") or ("US" if f.get("currency") == "USD" else "IN")
    if f.get("not_company"):
        return "not a company"
    if f.get("cap_unverified"):
        return "depositary share ratio unknown"
    if cap > CAP_CEILING.get(region, float("inf")):
        return "above any company's value"
    if region == "US" and foreign_filer(f):
        if _num(f.get("v")) is not None and f["v"] < ADR_CHECKED and not str(f.get("unit") or "$").startswith("$"):
            return "not checked for depositary shares"
        pe, profit = _num(f.get("pe")), _num(f.get("profit_usd"))
        if pe is not None and 0 < pe < PE_MIN_FOREIGN:
            return "out of line with profit"
        if profit is not None and profit > 0:
            by_profit = cap / profit
            if by_profit < PE_MIN_FOREIGN or pe is not None and pe > 0 and not 1 / PE_GAP <= pe / by_profit <= PE_GAP:
                return "out of line with profit"
    if region == "US":
        sales = _num(f.get("sales_usd"))
        if sales is None:
            sales = _latest_sales(f)
        if sales is not None:
            if sales < 10 and cap > PRE_REVENUE_MAX:
                return "no revenue to match the value"
            if sales >= 1000 and cap / sales > PS_MAX:
                return "out of line with revenue"
        elif not str(f.get("unit") or "$").startswith("$") and (_num(f.get("pe")) or 0) > PE_MAX:
            return "out of line with profit"
    return None


def foreign_filer(f: dict | None) -> bool:
    """Whether a US page is a foreign company's: one filing a 20-F or with depositary shares (said when the page was
    built), or, on a page stored before that was said, one reporting in another currency."""
    f = f or {}
    if f.get("foreign") is not None:
        return bool(f["foreign"])
    return not str(f.get("unit") or "$").startswith("$")


def shown_cap(f: dict | None):
    """The market value to show and rank on: None when there is none or it fails a check."""
    if not f or cap_problem(f):
        return None
    v = _num(f.get("market_cap"))
    return v if v is not None and v > 0 else None


def _month_end(label: str) -> str | None:
    """"Mar 2025" → "2025-03-31": a table column's year end."""
    try:
        d = datetime.strptime(str(label).strip(), "%b %Y").date()
    except ValueError:
        return None
    nxt = date(d.year + (d.month == 12), d.month % 12 + 1, 1)
    return (nxt - timedelta(days=1)).isoformat()


def pe_period(f: dict | None) -> tuple[str | None, str | None]:
    """(basis, end) of the earnings a page's P/E is on: "ttm" or "year", and the day they run to. As the page was built
    told it; a US page stored before that was kept (R8V-003: Toyota's, ASML's and Itaú's showed a bare "P/E" on a year
    up to 18 months old) has no trailing-twelve-months profit when its P/E was on the latest year in its table, so that
    year it is."""
    f = f or {}
    if f.get("pe_basis"):
        return f["pe_basis"], (str(f.get("pe_end") or "")[:10] or None)
    if (f.get("region") == "US" and (f.get("v") or 1) < PE_BASIS_KEPT and _num(f.get("pe")) is not None
            and f.get("profit_ttm") is None):
        years = [y for y in f.get("years") or [] if isinstance(y, dict) and y.get("year")]
        end = _month_end(years[-1]["year"]) if years else None
        if end:
            return "year", end
    return None, None


def pe_stale(f: dict | None) -> bool:
    """Whether the P/E's earnings ended more than about 15 months before the price (PE_STALE_DAYS): a foreign company
    whose latest annual report couldn't be read (R7V-003: TSMC's P/E of 65.5 was on its 2024 profit)."""
    f = f or {}
    end, at = str(pe_period(f)[1] or "")[:10], str(f.get("price_at") or "")[:10]
    try:
        return bool(end and at) and (date.fromisoformat(at) - date.fromisoformat(end)).days > PE_STALE_DAYS
    except ValueError:
        return False


def pe_label(f: dict | None) -> str:
    """"P/E", or "P/E (year to Dec 2025)" whenever its earnings are a reported year's, not the last four quarters'."""
    basis, end = pe_period(f)
    if basis == "year" and end:
        try:
            return f"P/E (year to {date.fromisoformat(end):%b %Y})"
        except ValueError:
            pass
    return "P/E"


def shown_pe(f: dict | None):
    """The P/E to show: None for a loss, a P/E above PE_MAX, a market value that fails a check, or earnings from a year
    that ended more than about 15 months before the price (pe_stale)."""
    pe = _num((f or {}).get("pe"))
    if pe is None or pe <= 0 or pe > PE_MAX or cap_problem(f) or pe_stale(f):
        return None
    return pe


def shown_yield(f: dict | None):
    """The dividend yield to show: None when unknown, when the market value it's measured on fails a check, and a 0%
    from a price history that lists no dividend while the company's own accounts show dividends paid (R6V-011)."""
    f = f or {}
    dy = _num(f.get("div_yield"))
    if dy is None or (f.get("region") == "US" and cap_problem(f)):
        return None
    if dy == 0 and f.get("divs_paid"):
        return None
    return dy


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
          filings: list[dict], exchange: str, red_flags: int | None = None, checks: dict | None = None) -> dict:
    """What a page shows, from what the deep dive already works out. Plain numbers and words; nothing from AI.
    `red_flags` is how many red-flag filings (India) the last three months held, for the stock screens. `checks` carries
    what the market value is checked against (see cap_problem): "sales_usd" (a year's revenue, $ million),
    "cap_unverified" (depositary shares whose ratio couldn't be read) and "not_company" (what the symbol is instead)."""
    years = [{k: y.get(k) for k in ("year", "sales", "profit", "opm", "debt")} for y in (nums.get("years") or [])[-5:]]
    prices = dict(prices or {})
    checks = checks or {}
    if _num(prices.get("price")) is None and _num(snap.get("price")) is not None:
        # no daily candles: the fundamentals source's price, a last trade, dated by the session it is from and never
        # called a close (R7V-004: HAL "Last price ₹4,647.00" with no date, the page "as of" the day it was built)
        prices.update(price=snap["price"], price_at=session_day(region).isoformat(), price_basis="last")
    # the EBITDA margin of the latest year in the table, as the net margin is: one period for the headline and the table
    # (R8V-010: Kinetic Seas' "EBITDA margin 43.7%" was its last twelve months', above a table whose latest year says
    # −1,634.4%)
    opm = years[-1].get("opm") if years else snap.get("opm")
    return {
        "v": FACTS_VERSION, **{k: checks[k] for k in ("sales_usd", "cap_unverified", "not_company", "divs_paid", "pe_basis", "pe_end", "eps",
                                                      "foreign", "profit_usd", "annual_unread")
                               if checks.get(k) is not None},
        "region": region, "symbol": symbol, "name": public_text(p.get("name") or symbol), "exchange": exchange,
        "industry": _dedupe(public_text(str(x)) for x in (p.get("industry_path") or []) if x)[:4],
        "currency": "USD" if region == "US" else "INR", "unit": nums.get("unit") or ("$ million" if region == "US" else "₹ crore"),
        "price": prices.get("price"), "price_at": prices.get("price_at"),
        "price_basis": prices.get("price_basis"),
        "high52": prices.get("high52") or snap.get("high52"), "low52": prices.get("low52") or snap.get("low52"),
        "market_cap": snap.get("market_cap_cr"), "market_cap_unit": "$ million" if region == "US" else "₹ crore", "pe": snap.get("pe"), "roe": snap.get("roe"), "roce": snap.get("roce"),
        "div_yield": snap.get("div_yield"), "profit_ttm": _ttm_profit(p),
        "net_margin": snap.get("net_margin"), "opm": opm, "debt": snap.get("debt_cr"), "debt_equity": snap.get("debt_equity"),
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
    if (stored["facts"].get("v") or 1) < FACTS_VERSION:
        return False                     # a page built before the facts a page shows now: rebuilt when next opened
    if stored["facts"].get("annual_unread") and now - ts >= UNREAD_FRESH:
        return False                     # built without its latest annual report, which couldn't be read then (R8V-003)
    settled = last_close(region, datetime.fromtimestamp(now, timezone.utc))[1].timestamp() + settle(region)
    # its own build, or the price job's re-read of its price, came after the market's latest settled close
    return ts >= settled or (stored.get("price_ts") or 0) >= settled


BUILT_KEY = "stocks:built:"          # stocks:built:<region> = {"at", "pages": every stored page, "shown": those with something to show}
FOREIGN_OTC = re.compile(r"^[A-Z]{4}[FY]$")      # a foreign company's US over-the-counter line: it rarely files results here


def has_content(f: dict | None) -> bool:
    """Whether a page has something to show and may be indexed: facts of a company. A listed company the sources had
    nothing on (no price and no numbers) is a short noindex page, and a fund or a note filed under a company's name a
    404 (see render)."""
    return bool(f) and not f.get("not_company")


_thin: set[tuple[str, str]] = set()          # companies already marked in this process


def _mark_thin(region: str, symbol: str, thin: bool):
    """Remember which companies' pages had nothing to show (the page says so and is kept out of search results), so the
    sitemap doesn't list them. One tiny setting per company; written once, cleared when facts turn up."""
    key = f"stocks:thin:{region}:{symbol}"
    try:
        if thin and (region, symbol) not in _thin:
            _thin.add((region, symbol))
            _put(key, 1)
        elif not thin:
            _thin.discard((region, symbol))
            if _setting(key):
                db.delete_setting(key)
    except Exception as ex:
        print("stock pages: could not mark", key, str(ex)[:120])


def thin_symbols(region: str) -> set[str]:
    """The companies whose last build had nothing to show."""
    try:
        return {k.rsplit(":", 1)[1] for k, _ in db.all_settings_with_prefix(f"stocks:thin:{region}:")}
    except Exception:
        return set()


class Pages:
    """Built pages: in memory for a few minutes, stored until the market's next close, and rebuilt at most `per_minute`
    times a minute. `gather(region, company)` builds one company's facts from the sources, or returns None when they
    have nothing."""

    def __init__(self, gather, per_minute: int = 6, older=None):
        # `older(region, symbol, facts)`: a stored page from before FACTS_VERSION, served while it can't be rebuilt,
        # brought in line where that's cheap (see main.stock_page_older_facts)
        self.gather, self.per_minute, self.older = gather, per_minute, older
        self.on_built = None           # (region, symbol, facts) after a page is built and stored: screens.note_page
        self.mem = TTLCache(max_items=3000)
        self.recent: deque = deque()
        self.lock = threading.Lock()
        self.building: dict[str, threading.Lock] = {}
        self.prices_done: dict[str, str] = {}          # {region: the close every stored page's price was read at}
        self.tries: dict[str, tuple[str, dict[str, int]]] = {}    # {region: (close, {symbol: reads with no newer close})}

    MAX_TRIES = 8              # reads of one page at one close that found no newer candle, before it waits for its next build

    def _may_build(self) -> bool:
        with self.lock:
            now = time.time()
            while self.recent and now - self.recent[0] > 60:
                self.recent.popleft()
            if len(self.recent) >= self.per_minute:
                return False
            self.recent.append(now)
            return True

    def _as_served(self, region: str, symbol: str, f: dict | None) -> dict | None:
        if f and self.older and (f.get("v") or 1) < FACTS_VERSION:
            try:
                return self.older(region, symbol, f)
            except Exception as ex:
                print("stock pages: older page not brought in line:", region, symbol, str(ex)[:120])
        return f

    def peek(self, region: str, symbol: str) -> dict | None:
        """A company's stored facts as they are, however old, without building anything: for the app's company page to
        use the same reported earnings as the public page (R7O-004). None when nothing is stored."""
        key = f"stocks:page:{region}:{symbol}"
        hit = self.mem.get(key)
        if hit is not None:
            return hit or None
        try:
            stored = _setting(key)
        except Exception:
            return None
        return (stored or {}).get("facts") or None

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
            if not stored.get("facts"):
                _mark_thin(region, symbol, True)       # a page stored before the sitemap kept track of these
            return stored.get("facts")
        with self.lock:
            one = self.building.setdefault(key, threading.Lock())
        with one:                        # two crawlers on the same page: the second waits for the first's build
            hit = self.mem.get(key)
            if hit is not None:
                return hit or None
            if not self._may_build():
                if stored:
                    return self._as_served(region, symbol, stored.get("facts"))
                raise Busy()
            try:
                got = self.gather(region, co)
            except Exception as ex:      # a source down: the stored copy, however old, or busy
                print("stock page build failed:", region, symbol, str(ex)[:160])
                if stored:
                    f = self._as_served(region, symbol, stored.get("facts"))
                    self.mem.set(key, f or {}, 600)
                    return f
                raise Busy() from None
            if got:
                got["symbol"] = symbol
            _put(key, {"ts": time.time(), "facts": got})
            _mark_thin(region, symbol, not has_content(got))         # nothing to show (or a fund): not in the sitemap
            self.mem.set(key, got or {}, 600)
            if self.on_built:
                try:
                    self.on_built(region, symbol, got)   # the screens' index takes the page's figures at once (R8O-005)
                except Exception as ex:
                    print("stock pages: index not told of", region, symbol, str(ex)[:120])
            return got

    def refresh_prices(self, region: str, bars_of, analyse=None, limit: int = 200, gap: float = 1.0, sleep=time.sleep,
                       now: datetime | None = None, official=None, official_ready=None) -> dict:
        """After a market's close: re-read the price of stored pages whose last close is older than the market's, the
        largest companies first, at most `limit` a run with `gap` seconds between reads (so people's pages and
        backtests keep the price sources' room). `bars_of(region, symbol)` gives a company's daily candles, read after
        the close settled. The price, its date, the year's range and the trend move to the new close; the market value
        and P/E move with the price (the share count and the profit stay what was reported); the dividend yield moves
        against it. The reported numbers wait for the page's next full build. {"refreshed", "left", "failed"}."""
        now = now or datetime.now(timezone.utc)
        day, at = last_close(region, now)
        if self.prices_done.get(region) == day.isoformat():
            return {"refreshed": 0, "left": 0, "failed": 0}       # every page already read at this close: no storage read
        settled = at.timestamp() + settle(region)
        prefix = f"stocks:page:{region}:"
        due = []
        try:
            rows = db.all_settings_with_prefix(prefix)
        except Exception as ex:                       # storage down: next run
            print("stock pages: price refresh could not read", region, str(ex)[:120])
            return {"refreshed": 0, "left": 0, "failed": 0}
        swapped = 0
        if self.tries.get(region, ("", {}))[0] != day.isoformat():
            self.tries[region] = (day.isoformat(), {})            # each close starts its own count of tries
        tries = self.tries[region][1]
        for key, raw in rows:
            stored = db.json_value(raw, {}) if not isinstance(raw, dict) else raw
            f = stored.get("facts") or {}
            symbol = key[len(prefix):]
            # a page read at today's close before the exchange's official close was known: that close now, with no read
            # of prices (R7O-004)
            if f and official and str(f.get("price_at") or "") == day.isoformat() and not f.get("price_official"):
                c = official(symbol, day.isoformat())
                if c is not None:
                    _put(key, {**stored, "facts": with_official_close(f, c)})
                    self.mem.pop(key)
                    self.mem.pop(f"html:{region}:{symbol}")
                    swapped += 1
                    continue
            at_close = str(f.get("price_at") or "") >= day.isoformat() and is_close(f)
            if not f or at_close or (stored.get("price_ts") or 0) >= settled:
                continue
            if tries.get(symbol, 0) >= self.MAX_TRIES:           # the source has no newer close for it today
                continue
            due.append((symbol, stored))
        # the largest companies first, and a page the source had no newer close for at an earlier try after the rest
        due.sort(key=lambda x: (tries.get(x[0], 0), -(shown_cap(x[1]["facts"]) or 0)))
        done = failed = 0
        ok: set[str] = set()
        for i, (symbol, stored) in enumerate(due[:limit]):
            if i and gap:
                sleep(gap)
            try:
                bars = closed_bars(bars_of(region, symbol) or [], region, now)
            except Exception as ex:                   # no prices for this one today: tried again at its next build
                failed += 1
                print("stock pages: price refresh failed:", region, symbol, str(ex)[:120])
                continue
            facts_now = with_new_close(stored["facts"], bars, analyse)
            stored = {**stored, "facts": facts_now}
            if str(facts_now.get("price_at") or "") >= day.isoformat():
                stored["price_ts"] = time.time()      # read at this close: not read again until the next one
                done += 1
                ok.add(symbol)
            else:
                # the source had no candle for the market's last close yet (a small company's day comes in late): tried
                # again at the next runs, a few times, instead of being marked read and left a session behind until the
                # next close (R7V-005: a long tail one or two sessions behind)
                tries[symbol] = tries.get(symbol, 0) + 1
                failed += 1
            _put(prefix + symbol, stored)
            self.mem.pop(prefix + symbol)
            self.mem.pop(f"html:{region}:{symbol}")
        retry = sum(1 for s, _ in due[:limit] if s not in ok and 0 < tries.get(s, 0) < self.MAX_TRIES)
        if len(due) <= limit and not retry and (official_ready is None or official_ready(day.isoformat())):
            self.prices_done[region] = day.isoformat()            # a page still behind is tried again at its next build
        return {"refreshed": done, "left": max(0, len(due) - limit), "failed": failed, **({"retry": retry} if retry else {}),
                **({"official": swapped} if official else {})}

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


def _sized(region: str) -> list[dict]:
    """The index's companies whose market value passed its checks, largest first. A US row must come from an index
    built after the checks existed ("cap_checked"); any row above CAP_CEILING is left out whatever its age."""
    cos = companies(region)
    out = []
    for r in _index_rows(region):
        cap = _num(r.get("market_cap"))
        if r.get("symbol") not in cos or cap is None or cap <= 0 or cap > CAP_CEILING.get(region, float("inf")):
            continue
        if region == "US" and not r.get("cap_checked"):
            continue
        out.append(r)
    return sorted(out, key=lambda r: -_num(r["market_cap"]))


LARGE_CAP = {"US": 10_000.0, "IN": 20_000.0}       # $ million, ₹ crore: a large company, whose peers should be of its size
PEER_MIN_SHARE = 0.01                               # a large company's industry peers outside its index group: 1% of its value or more
PEER_STALE_DAYS = 7                                 # a peer whose last price is older than this (before the newest) is left out


def _sp500_sectors() -> dict[str, str]:
    """{symbol: GICS sector} for the S&P 500 (the committed list), a coarser grouping than the SIC industry."""
    global _SP500_SECTORS
    if _SP500_SECTORS is None:
        try:
            _SP500_SECTORS = {r[0]: r[2] for r in universes.sp500_doc()["rows"] if r[2]}
        except Exception:
            _SP500_SECTORS = {}
    return _SP500_SECTORS


_SP500_SECTORS: dict[str, str] | None = None


def _fresh_rows(rows: list[dict]) -> list[dict]:
    """Rows whose last price is no more than PEER_STALE_DAYS older than the newest in the index (R7V-009: TCS's list
    ranked IDREAM, last price 29 Sep, above KPITTECH, priced 8 Oct). Measured against the index's own newest price, not
    the clock; a row with no price date stays."""
    days = [str(r.get("price_at") or "")[:10] for r in rows if r.get("price_at")]
    if not days:
        return rows
    try:
        cut = (date.fromisoformat(max(days)) - timedelta(days=PEER_STALE_DAYS)).isoformat()
    except ValueError:
        return rows
    return [r for r in rows if not r.get("price_at") or str(r["price_at"])[:10] >= cut]


def peer_sections(region: str, symbol: str, industry: list[str], cap: float | None = None) -> list[dict]:
    """The page's lists of related companies, each {"title", "caption", "rows": [(page symbol, full name)]}, and each
    caption true of its list (R6V-003): the largest companies in the company's own industry by checked market value;
    when that industry has few, the largest in its wider sector; when the index knows none, StratLab's own sector lists,
    said to be unranked.

    A large company (`cap`, its checked market value, else its index row's) whose own industry has fewer than three
    companies at least a tenth its size gets the largest companies of its wider sector first (R7V-009: Apple's
    industry, Electronic Computers, is Dell, Super Micro and four small makers; its sector has Microsoft and NVIDIA): in
    the US the S&P 500's sector for its members, in India its sector. Companies whose last price is more than a week
    older than the index's newest are left out (no price for a week says little about their size today)."""
    cos = companies(region)
    ind = _dedupe(industry)
    sized = _sized(region)
    if cap is None:
        cap = next((_num(r.get("market_cap")) for r in sized if r.get("symbol") == symbol), None)
    rows = _fresh_rows([r for r in sized if r.get("symbol") != symbol])
    name = lambda r: str(r.get("name") or cos[r["symbol"]]["name"] or r["symbol"])        # noqa: E731
    out: list[dict] = []
    same_ind = [r for r in rows if ind and str(r.get("industry") or "").lower() == ind[-1].lower()]
    large = bool(cap and cap >= LARGE_CAP.get(region, float("inf")))
    if large:
        # a large company's industry is its own size's business, not every filer under the same code (R8V-012: Apple's
        # "Same industry" listed Omnicell, Zepp and Socket Mobile; Visa's, under "business services", Uber, Accenture
        # and DoorDash): an S&P 500 company keeps the S&P 500 members of its own sector, and companies outside the
        # S&P 500 of at least PEER_MIN_SHARE of its value; an Indian company keeps those of that size
        sp = _sp500_sectors() if region == "US" else {}
        mine = sp.get(symbol)
        same_ind = [r for r in same_ind if (sp.get(r["symbol"]) == mine if mine and r["symbol"] in sp
                                            else (_num(r.get("market_cap")) or 0) >= cap * PEER_MIN_SHARE)]
    same_ind = same_ind[:PEERS]
    big = [r for r in same_ind if cap and (_num(r.get("market_cap")) or 0) >= cap / 10]
    coarse: list[dict] = []
    if large and len(big) < 3:
        if region == "US" and symbol in _sp500_sectors():
            where = _sp500_sectors()[symbol]
            coarse = [r for r in rows if _sp500_sectors().get(r["symbol"]) == where][:PEERS]
        elif region == "IN" and ind:
            where = ind[0]
            coarse = [r for r in rows if str(r.get("sector") or "").lower() == where.lower()][:PEERS]
        if coarse:
            out.append({"title": "Same sector", "rows": [(r["symbol"], name(r)) for r in coarse],
                        "caption": f"The largest companies in the wider sector ({where}), by market value."})
    if same_ind:
        out.append({"title": "Same industry", "rows": [(r["symbol"], name(r)) for r in same_ind],
                    "caption": f"The largest companies in the same industry ({ind[-1]}), by market value."})
    if len(same_ind) < 4 and len(ind) > 1 and not coarse:
        have = {r["symbol"] for r in same_ind}
        sector = [r for r in rows if r["symbol"] not in have and str(r.get("sector") or "").lower() == ind[0].lower()]
        sector = sector[:PEERS - len(same_ind)]
        if sector:
            out.append({"title": "Same sector", "rows": [(r["symbol"], name(r)) for r in sector],
                        "caption": f"The largest companies in the wider sector ({ind[0]}), by market value."})
    if not out:
        listed: list[tuple[str, str]] = []
        for group, members in sector_members.BY_MARKET.get(region, {}).items():
            if symbol in members:
                listed += [(s, cos[s]["name"] or s) for s in members if s != symbol and s in cos and s not in dict(listed)]
        if listed:
            out.append({"title": "Same sector", "rows": listed[:PEERS],
                        "caption": "Companies StratLab lists in the same sector, in no particular order."})
    return out


def peers(region: str, symbol: str, industry: list[str]) -> tuple[list[tuple[str, str]], bool]:
    """(page symbol, full name) of related companies, as the page lists them, and whether the first list is ranked by
    market value (see peer_sections)."""
    sections = peer_sections(region, symbol, industry)
    rows = [x for s in sections for x in s["rows"]][:PEERS]
    return rows, bool(sections) and "by market value" in sections[0]["caption"]


def largest(region: str, n: int = 24) -> tuple[list[tuple[str, str]], bool]:
    """The market's largest companies with a stored page, by checked market value, and True; before the index has any,
    StratLab's own sector lists and False (the page then doesn't call them the largest).

    Each one's value is its own stored page's, the figure that page shows (R7V-001: Alphabet, $4.26T on its page, was
    missing from the list the index gave): the index's largest and StratLab's own lists of the biggest companies are the
    candidates, each read from its stored page."""
    cos = companies(region)
    rows = _sized(region)
    names = {r["symbol"]: str(r.get("name") or r["symbol"]) for r in rows}
    cands = list(dict.fromkeys([r["symbol"] for r in rows[:n * 2]]
                               + [s for p in universes.PRESETS.get(region, []) for s in p["symbols"] if s in cos]))
    keys = [f"stocks:page:{region}:{s}" for s in cands]
    try:
        db.prefetch_settings(keys)
    except Exception:                       # only a head start: each page is read on its own then
        pass
    twins = set(nse_twins()) if region == "IN" else set()
    index_cap = {r["symbol"]: _num(r.get("market_cap")) for r in rows}
    sized = []
    for s, key in zip(cands, keys):
        stored = _setting(key)
        f = ((stored or {}).get("facts")) or {}
        # the page's own figure; an index row whose page isn't stored here any more keeps the figure it was built from
        cap = shown_cap(f) if stored is not None else index_cap.get(s)
        if s in twins or cap is None or cap > CAP_CEILING.get(region, float("inf")):
            continue
        sized.append((cap, s, names.get(s) or str(f.get("name") or (cos.get(s) or {}).get("name") or s)))
    out = [(s, name) for _, s, name in sorted(sized, key=lambda x: -x[0])[:n]]
    if out:
        return out, True
    return [(s, cos[s]["name"] or s) for s in sorted(_seeds(region)) if s in cos][:n], False


def search(region: str, q: str, n: int = 30) -> list[tuple[str, str]]:
    """Companies whose symbol or name matches what was typed: the exact symbol first, then symbols that start with it,
    then names that contain it. At most `n` (ask for one more to know whether the list was cut)."""
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
    """A number with `digits` decimals. One that would round to zero shows two more decimals (a $40,000 loss in a
    $ million column is -0.04, not "-0"), and only a real zero is 0 (R6V-011)."""
    v = _num(v)
    if v is None:
        return "–"
    if v != 0 and round(v, digits) == 0:
        if round(v, digits + 2) == 0:
            v = 0.0                               # nothing to show even with more decimals: zero
        else:
            digits += 2
    if v == 0:
        v = 0.0                                   # never "-0"
    return f"{v:,.{digits}f}{suffix}"


def _pct(v, whole: bool = False) -> str:
    """A percentage; with `whole`, figures the source gives in whole percent show none of the ".0" they don't have."""
    v = _num(v)
    if v is None:
        return "–"
    return f"{v:,.0f}%" if whole and v == round(v) else f"{v:,.1f}%"


def _money(f: dict, v) -> str:
    """A price as the market quotes it: $12.34, and four decimals below 10 cents ($0.0247, not $0.02: R7V-005)."""
    v = _num(v)
    if v is None:
        return "–"
    if f.get("currency") == "USD":
        return f"${v:,.4f}" if 0 < abs(v) < 0.10 else f"${v:,.2f}"
    from .email_kit import inr
    return inr(v, 2)                            # Indian grouping for rupees: Rs1,40,250.00


def _inr_group(v: float) -> str:
    """Indian digit grouping: 77034 -> 77,034; 1905432 -> 19,05,432."""
    s = f"{abs(v):.0f}"
    head, tail = s[:-3], s[-3:]
    while len(head) > 2:
        tail = head[-2:] + "," + tail
        head = head[:-2]
    return ("-" if v < 0 else "") + (head + "," + tail if head else tail)


def cap_text(f: dict) -> str:
    """Market value in the words people use: "$4.87T", "$85.8B", "$950M", "<$1M"; "₹7.70 lakh crore", "₹20,345 crore".
    "–" when there is none or it failed its checks (cap_problem)."""
    v = shown_cap(f)
    if v is None:
        return "–"
    if f.get("currency") == "USD":                       # stored in $ million
        if v >= 1e6:
            return f"${v / 1e6:,.2f}T"
        if v >= 1e3:
            return f"${v / 1e3:,.1f}B"
        # $0.5M rounds to "$0M" (TAOP, R6V-011): anything under a whole million is "<$1M"
        return f"${v:,.0f}M" if round(v) >= 1 else "<$1M"
    if v >= 1e5:                                          # stored in ₹ crore
        return f"₹{v / 1e5:,.2f} lakh crore"
    return f"₹{_inr_group(v)} crore" if round(v) >= 1 else "<₹1 crore"


def _date(iso: str | None) -> str:
    try:
        d = datetime.fromisoformat(str(iso)[:10])
        return f"{d.day} {d:%b %Y}"
    except (TypeError, ValueError):
        return ""


def behind(f: dict, now: datetime | None = None) -> bool:
    """Whether the page's price is from before its market's latest settled close: then it isn't "the last close", and
    the page says "Last price" with its date instead (R6V-002)."""
    at = str(f.get("price_at") or "")[:10]
    region = f.get("region")
    if not at or region not in REGIONS.values():
        return False
    try:
        return at < last_close(region, now)[0].isoformat()
    except Exception:                     # no calendar: nothing to say against the date shown
        return False


def is_close(f: dict) -> bool:
    """Whether the page's price is a session's close: not a last trade read from a quote (price_basis "last")."""
    return f.get("price_basis") != "last"


def price_label(f: dict, now: datetime | None = None) -> str:
    """The price's name on the page, always with the session it is from (R7V-004): "Last close, 7 Oct 2026", or
    "Last price, 5 Oct 2026" for a price older than the market's latest close or one that isn't a close (never called a
    close then)."""
    when = _date(f.get("price_at"))
    if not when:
        return "Last price"
    return ("Last price, " if behind(f, now) or not is_close(f) else "Last close, ") + when


def as_of_text(f: dict, now: datetime | None = None) -> str:
    """The page's one "as of": the close the price is from ("7 Oct 2026 close"), the date of a price older than the
    market's last close ("5 Oct 2026 (last price this page has)"), or, with no price at all, when it was built."""
    if f.get("price_at"):
        if behind(f, now):
            return _date(f["price_at"]) + " (the last price this page has; the market has closed since)"
        return _date(f["price_at"]) + (" close" if is_close(f) else " (last price)")
    return _date(f.get("built_at"))


def description(f: dict) -> str:
    """The search result's snippet: what the page holds, in facts."""
    bits = [f"{f['name']} ({f['symbol']})"]
    if _num(f.get("price")) is not None:
        word = "last price" if behind(f) or not is_close(f) else "last close"
        bits.append(f"{word} {_money(f, f['price'])}" + (f" on {_date(f['price_at'])}" if f.get("price_at") else ""))
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
    if f.get("not_company"):
        return _not_company_page(region, symbol, str(f["not_company"]))
    desc = description(f)
    as_of = as_of_text(f)
    if _num(f.get("price")) is not None and is_close(f):
        as_of_line = (f"As of {e(as_of)}. Prices are closing prices; facts from reported results, exchange filings and "
                      "daily prices. Not investment advice.")
    elif _num(f.get("price")) is not None:              # a last trade, dated by its session (R7V-004)
        as_of_line = (f"As of {e(as_of)}. The price is the last trade of that session, not yet its close; facts from "
                      "reported results, exchange filings and daily prices. Not investment advice.")
    else:                                 # no price to date the page by: say so, never a bare "As of" over no price
        as_of_line = ("No recent share price is available for this company. Facts from reported results and exchange "
                      f"filings{', page built ' + e(as_of) if as_of else ''}. Not investment advice.")
    ld = _ld([{"@context": "https://schema.org", "@type": "Corporation", "name": name, "tickerSymbol": symbol,
               "url": canonical, **({"industry": f["industry"][-1]} if f.get("industry") else {})},
              {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
                  {"@type": "ListItem", "position": 1, "name": "StratLab", "item": site + "/"},
                  {"@type": "ListItem", "position": 2, "name": name, "item": canonical}]}])
    ind = " · ".join(_dedupe(f.get("industry")))
    parts = [f"""<h1>{e(name)} <span class="muted">({e(symbol)})</span></h1>
<p class="muted">{e(f.get("exchange") or country)}{(" · " + e(ind)) if ind else ""}</p>
<p class="small muted" data-as-of>{as_of_line}</p>"""]
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
    for sec in peer_sections(region, symbol, f.get("industry") or [], shown_cap(f)):
        parts.append(f'<h2>{e(sec["title"])}</h2><p class="small muted" data-peers>{e(sec["caption"])}</p>' + _links(region, sec["rows"]))
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
    cap = cap_text(f)
    if cap == "–" and cap_problem(f):
        cap = "n/a"                               # a value that failed its checks: said, not hidden (see _notes)
    pe, dy = shown_pe(f), shown_yield(f)
    out = [(price_label(f), _money(f, f.get("price"))),
           # the range is the year's highest and lowest trade, not closes (R6V-014)
           ("1-year range (intraday)", f"{_money(f, f.get('low52'))} to {_money(f, f.get('high52'))}"
            if _num(f.get("low52")) is not None and _num(f.get("high52")) is not None else "–"),
           ("Market cap", cap), (pe_label(f), _fmt(pe) if pe is not None else "n/a"),
           (f"Net profit, last 12 months ({unit})", _fmt(f.get("profit_ttm"), 0)),
           ("Return on equity", _pct(f.get("roe")))]
    if not f.get("bank"):
        out += [("EBITDA margin", _pct(f.get("opm"), whole)), ("Debt to equity", _fmt(f.get("debt_equity"), 2))]
    out += [("Net margin", _pct(f.get("net_margin"))),
            ("Dividend yield", _fmt(dy, 2, "%") if dy is not None else "n/a")]
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
    if cap_problem(f):
        out.append('<p class="note warn" data-cap-check>The market value worked out from the share count and the price '
                   "doesn't agree with the company's own reported figures (it may count ordinary shares against a "
                   "depositary share's price), so it isn't shown, nor is P/E, and the company is left out of lists "
                   "ranked by size.</p>")
    if pe_stale(f) and _num(f.get("pe")) is not None:
        out.append(f'<p class="note" data-pe-old>P/E isn\'t shown: the latest reported earnings on this page are for the '
                   f'year to {e(_date(pe_period(f)[1]))}, more than 15 months before this price, and a newer annual '
                   "report's figures aren't on the page yet.</p>")
    if behind(f):
        out.append(f'<p class="note" data-behind>The price shown is from {e(_date(f.get("price_at")))}. The market has '
                   "closed since, and this page hasn't read a newer price yet (or the stock hasn't traded since).</p>")
    if extreme(f):
        out.append('<p class="note warn" data-extreme>Revenue is very small next to this company\'s costs or profit, so its margins '
                   "here are extreme figures (beyond ±100%). They are what the reported numbers give, but they say little about "
                   "how the business earns.</p>")
    return out


# one definition of P/E and of the dividend yield on every page, India and the US, and in the app (R7V-002)
PE_NOTE = ("P/E: the last close divided by earnings per share over the last four reported quarters, the profit that belongs "
           "to the company's shareholders per share, as the company reports it. So P/E can differ from market cap divided "
           "by the net profit shown (a different share count, or the profit before minority interests). A company that "
           "reports only once a year has its latest year's earnings, and the P/E names that year; when that year ended "
           "more than about 15 months before the close, P/E is n/a. A loss has no P/E. Above 1,000 it is n/a.")
YIELD_NOTE = ("Dividend yield: every dividend per share with an ex-date in the 12 months to the last close, special "
              "dividends included, as a share of that close. n/a when the company's dividends couldn't be read.")


def _how(f: dict) -> str:
    """How each figure is worked out, so a reader can check one against another."""
    india = f.get("region") == "IN"
    items = [
        "Last close: the closing price on the date shown. The page follows the market's close; it doesn't show prices "
        "during the session. A price older than the market's latest close, or a last trade that isn't a close, is labelled "
        "as the last price, with the session it is from.",
        "1-year range: the lowest and highest prices traded during the sessions of the last year (intraday), so they can "
        "lie outside the closing prices.",
        "Market cap: the last close times the shares in issue. It is n/a when it doesn't agree with the company's own "
        "reported figures (for example a depositary share counted as an ordinary share).",
        PE_NOTE,
        "EBITDA margin: operating profit before depreciation, interest and tax (and before other income), as a share of "
        "revenue in the latest reported year, the table's last column." + (" The results give it in whole percent." if india else ""),
        "Net margin: net profit as a share of revenue in the latest reported period.",
        YIELD_NOTE,
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
    the date of the list. The badge's colours are the page's theme tokens, so it reads in dark mode too (R8V-009: a
    fixed dark amber on the dark card was 2.37:1)."""
    if not flags:
        return ""
    badge = ("display:inline-block;border:1px solid var(--orange-ink);color:var(--orange-ink);background:var(--orange-soft);"
             "border-radius:999px;padding:2px 10px;font-size:13px;font-weight:600;margin:0 6px 6px 0")
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
    s = (symbol or "")[:40]
    kind = not_a_company(region, s)
    if kind:
        return _not_company_page(region, s, kind)
    site = settings.PUBLIC_SITE_URL
    title = "Company not found · StratLab"
    body = (f"<h1>No company page for {e(s)}</h1>"
            '<p class="muted">Check the symbol, or find the company by its name.</p>' + _find_form(region))
    return _page(_head(title, "No listed company has that symbol.", site + "/stocks", robots="noindex,follow"), None, body)


BUSY_REFRESH = 30          # seconds before a "being prepared" page asks again by itself


def busy_page(region: str | None, symbol: str, name: str | None = None) -> str:
    """A company page that is still being built: a page a visitor from a search engine can read, which loads itself
    again shortly (R7O-009: a cold page answered with raw JSON). Sent with 503 and Retry-After, and kept out of
    search results."""
    site = settings.PUBLIC_SITE_URL
    s = (symbol or "")[:40].upper()
    who = f"{e(name)} ({e(s)})" if name else e(s)
    path = f"/stocks/{(region or 'IN').lower()}/{quote(s, safe='')}"
    head = _head(f"{s}: being prepared · StratLab", "This company's page is being prepared.", site + path,
                 extra=f'<meta http-equiv="refresh" content="{BUSY_REFRESH}">', robots="noindex,follow")
    body = (f"<h1>{who}: this page is being prepared</h1>"
            f'<p class="muted">StratLab is gathering this company\'s reported numbers and prices. The page loads by itself '
            f'in about {BUSY_REFRESH} seconds; if it doesn\'t, <a href="{e(path)}">open it again</a> in a minute or two.</p>'
            + _find_form(region))
    return _page(head, None, body)


def _not_company_page(region: str | None, symbol: str, kind: str) -> str:
    """A fund, an exchange-traded note or an index: what it is, and where it can be charted and tested."""
    site = settings.PUBLIC_SITE_URL
    s = symbol.upper()
    market = "US" if region == "US" else "IN"
    app = f"{site}/research/{market}/{quote(s, safe='')}"
    title = f"{s} is {kind} · StratLab"
    body = (f"<h1>{e(s)} is {e(kind)}</h1>"
            f'<p>Public pages here cover listed companies, with their reported results. {e(s)} isn\'t a company, so it '
            f"has no page of its own. Inside StratLab you can chart it and test a trading idea on its prices.</p>"
            f'<div class="ctas"><a class="btn" href="{e(app)}">Open {e(s)} in StratLab</a>'
            f'<a class="btn ghost" href="/stocks">Find a company</a></div>')
    return _page(_head(title, "No listed company has that symbol.", site + "/stocks", robots="noindex,follow"), app, body)


SEARCH_SHOWN = 30


def index_page(region: str | None, q: str = "") -> str:
    """/stocks: find a company by name or symbol, and the largest companies in each market."""
    site = settings.PUBLIC_SITE_URL
    q = (q or "").strip()[:40]
    regions = [region] if region else ["IN", "US"]
    body = ['<h1>Company pages</h1><p class="muted">Every company listed in India (NSE and BSE) and the US: its last close, '
            "reported results, margins, debt and recent filings. Facts, not advice.</p>", _find_form(region, q)]
    if q:
        for r in regions:
            got = search(r, q, SEARCH_SHOWN + 1)
            more, got = len(got) > SEARCH_SHOWN, got[:SEARCH_SHOWN]
            label = "India" if r == "IN" else "US"
            # a list cut at its length says so: "the first 30 matches", never "30 matches" (R6V-015)
            count = f"the first {len(got)} matches" if more else f"{len(got)} {'match' if len(got) == 1 else 'matches'}"
            body.append(f"<h2>{label}: {count} for “{e(q)}”</h2>"
                        + (_links(r.lower(), got) if got else '<p class="muted">None. Try part of the name, or the symbol.</p>')
                        + ('<p class="small muted">More companies match. Type more of the name or the symbol to narrow it down.</p>' if more else ""))
    else:
        for r in regions:
            big, ranked = largest(r)
            if big:
                where = "India" if r == "IN" else "US"
                head = (f"{where}: the largest companies" if ranked else f"{where}: some of the companies")
                cap = ('<p class="small muted">By market value, among companies whose value passed StratLab\'s checks against '
                       "their reported figures. Funds and notes are left out.</p>" if ranked else "")
                body.append(f"<h2>{head}</h2>{cap}{_links(r.lower(), big)}")
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
    def day(n: str) -> str:
        if n == "pages":
            return max(d for _, d in site_pages.PAGES)
        return str(((_setting(f"stocks:list:{REGIONS[n.split('-')[1]]}") or {}).get("at")) or "")[:10]
    items = "".join(f"<sitemap><loc>{site}/sitemaps/{n}.xml</loc>" + (f"<lastmod>{d}</lastmod>" if (d := day(n)) else "") + "</sitemap>" for n in names)
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{items}</sitemapindex>\n'


def _urlset(rows: list) -> str:
    """A sitemap file. A row is an address, or (address, last-changed day) for a page whose date is known."""
    items = ""
    for r in rows:
        loc, mod = (r, None) if isinstance(r, str) else r
        items += f"<url><loc>{e(loc)}</loc>" + (f"<lastmod>{e(mod)}</lastmod>" if mod else "") + "</url>"
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{items}</urlset>\n'


def sitemap(name: str) -> str | None:
    """One sitemap file: "pages" (the public site pages, with the day each last changed, and StratLab's own library
    strategies) or "stocks-in-1", "stocks-us-2"… (companies whose page has facts to show; the day is when the list of
    listed companies was last refreshed); None for any other name."""
    site = settings.PUBLIC_SITE_URL
    if name == "pages":
        # /stocks is the API's own list of company pages, not one of the site's pages: it changes with the companies list
        listed = max((str(((_setting(f"stocks:list:{R}") or {}).get("at")) or "")[:10] for R in REGIONS.values()), default="")
        return _urlset([(site + p, d) for p, d in site_pages.PAGES] + [(site + "/stocks", listed or max(d for _, d in site_pages.PAGES))]
                       + [(site + p, d) for p, d in site_pages.library_pages()])
    bits = name.split("-")
    if len(bits) != 3 or bits[0] != "stocks" or bits[1] not in REGIONS or not bits[2].isdigit() or len(bits[2]) > 6:
        return None
    region = REGIONS[bits[1]]
    syms = sorted(companies(region))
    i = int(bits[2]) - 1
    if i < 0 or (i * CHUNK >= len(syms) and i > 0):
        return None
    day = str(((_setting(f"stocks:list:{region}") or {}).get("at")) or "")[:10] or None
    known = listing(region)
    return _urlset([(site + path(bits[1], s), day) for s in syms[i * CHUNK:(i + 1) * CHUNK] if listable(region, s, known)])


def listing(region: str) -> tuple[set, set, set, bool]:
    """(marked as having nothing to show, every stored page, stored pages with something to show, whether the screens
    have gathered the stored pages yet), for listable."""
    built = _setting(BUILT_KEY + region) or {}
    return thin_symbols(region), set(built.get("pages") or []), set(built.get("shown") or []), bool(built)


def listable(region: str, symbol: str, known: tuple | None = None) -> bool:
    """Whether a company's page belongs in the sitemap: by the screens' last gathering of the stored pages, a page
    stored with something to show, and not marked since as having nothing to show (noindex) or as a fund. A page not
    built yet isn't listed until the screens' indexer has built it (it builds the missing ones first): unbuilt, its
    first visit could be a 503 "being prepared" or a fund's 404 (R8V-007: MDXR, a fund, listed; TEAM and STRS 503s
    on a crawler's first hit). Before the first gathering, every page not marked (R7V-007: about one listed page in
    ten was noindex)."""
    thin, pages, shown, gathered = known or listing(region)
    if symbol in thin:
        return False
    if not gathered:                     # before the first gathering: every page not marked
        return True
    return symbol in shown
