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
import hashlib
import json
import math
import re
import threading
import time
import unicodedata
from collections import deque
from datetime import date, datetime, time as dtime, timedelta, timezone
from html import escape as e
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo

from . import blog, db, instrument_kinds, memguard, sector_members, site_pages, universes
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
# (R8V-001, R8V-005), or (7) before a profit tagged for the consolidated entity was read (Deutsche Bank), a share count
# from a cover page that gives one per class (Baidu, BP), every ratio came from one year's own column, a year's range ran
# over exactly 365 days held to the exchange's 52-week report, and a company with no reported numbers could show its price
# (R10V-001, 003, 004), or (8) before an Indian year's range was of candles as traded, the broker's scaling for an
# extraordinary dividend undone (R12-001: INFY, ULTRACEMCO), a year split at a change of control was added up, a cover
# page's issued count was taken net of treasury shares, and a page knew whether its ticker's type was read (R12-005 to
# 013), are rebuilt when next opened, in either market. Until then such a page is served brought in line
# where that's cheap (main.stock_page_older_facts), and the screens' indexer rebuilds the largest first (R8V-003)
# (9: or before a US page kept each quarter's filed EPS and whether its annual report gives an interest expense, which the
# app's results rows are checked by: RC1 DD-030, AAPL's Jun 2026 quarter stayed 1.91 against a filed 2.02)
FACTS_VERSION = 9
ADR_CHECKED = 3                # the version from which a depositary share's market value was checked (screens.row)
PE_BASIS_KEPT = 4              # the version from which a page keeps what its P/E's earnings cover (pe_basis, pe_end)
PE_STALE_DAYS = 456            # a P/E on a year that ended more than about 15 months before the price is n/a (R7V-003)
ANNUAL_BEHIND_DAYS = 395       # a newest annual report filed this long after the table's newest year ended isn't in the table
CHUNK = 5000                   # companies per sitemap file (the limit is 50,000; smaller files are quicker to fetch)
PEERS = 12
# SEO-1: a company, directory or blog page is kept by the site's cache (the host's edge, which serves the API's pages through a
# rewrite: vercel.json's x-vercel-enable-rewrite-caching) for a day, and stale for a week while it is read again. A cold build
# took 0.6 to 1.8 s, which Google counts against crawling a site it has found 13,000 addresses on and not yet read. The price on
# a page is the close its "As of" names, so a copy a day old still says what is true of it; only a page that is already a close
# behind (BEHIND_CACHE) is kept a minute, so it follows its refresh at once. Browsers keep a page five minutes.
CACHE_CONTROL = "public, max-age=300, s-maxage=86400, stale-while-revalidate=604800"
FEED_CACHE = "public, max-age=300, s-maxage=900, stale-while-revalidate=600"     # robots, the sitemaps and search results: a list that changes by the hour
BEHIND_CACHE = "public, max-age=60, s-maxage=60, stale-while-revalidate=30"   # a page waiting for its new close
MIN_CACHE = 60
EXTREME = 100.0                # a margin beyond ±100% says revenue is tiny next to costs or profit
NOT_MEANINGFUL = 1000.0        # a margin or return beyond ±1,000% is arithmetic on near-zero revenue: shown as "n/m", not a number (DK-024)
FINANCIAL_GROUPS = {"lender", "insurer", "bdc"}     # industry.classify groups for which EBITDA margin and debt to equity mean nothing (DK-023)
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
IN_SHARES_MAX = 30e9        # an Indian company's implied share count (market value ÷ price) above this is a unit or share-count error (R26-001)
IN_PS_MAX = 50              # an Indian market value over this many times its latest year's revenue is out of line (R26-001)
# an exchange operator that is not itself a listed company, which an instrument list can carry under its own code (R26-001)
UNLISTED_NAMES = re.compile(r"^\s*national stock exchange of india\b", re.I)
PE_MAX = 1000.0                # a P/E above this says the market value or the profit is off, not the company: n/a
# a foreign filer's (20-F, depositary shares) market value against its own reported profit (R8V-001: Mizuho at a P/E of
# 1.8, its depositary ratio read ten times too high): a P/E under PE_MIN_FOREIGN on a profit, or a P/E and the market
# value over that profit more than PE_GAP times apart, says the share count or the ratio is off, not the company
PE_MIN_FOREIGN = 3.0
PE_GAP = 2.0
UNREAD_FRESH = 3600            # seconds a page built without its latest annual report (unreadable just then) is kept
PS_MAX = 250.0                 # market value over a year's revenue, for a company with $1 billion of revenue or more
PRE_REVENUE_MAX = 20_000.0     # $ million: a company with under $10 million of revenue isn't worth $20 billion
# a US market value under a year's profit (a P/E under 1) is a share count far too low, not a company (R10C: AYR's 17,840
# shares at $100 gave $1.8 million against $178 million of profit, a P/E of 0.0 and a dividend yield of 3,519%)
PE_MIN_US = 1.0
YIELD_MAX = 50.0               # a dividend yield above this (%) is a share count or dividend error: n/a, never ranked
# what the price source calls something that trades but isn't a company's stock
FUND_TYPES = {"ETF": "an exchange-traded product (an ETF or ETN)", "MUTUALFUND": "a fund", "INDEX": "an index",
              "CURRENCY": "a currency", "CRYPTOCURRENCY": "a crypto asset", "FUTURE": "a futures contract"}



def _source_down(ex: Exception) -> bool:
    """The market data source is down for every company, not just this one: India's broker login has ended."""
    try:
        from .kite_service import KiteNotReady
    except Exception:
        return False
    return isinstance(ex, KiteNotReady)

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
        _dir.pop(region, None)
        _dir_index.pop(region, None)


def _seeds(region: str) -> set[str]:
    out = {s for members in sector_members.BY_MARKET.get(region, {}).values() for s in members}
    return out | {s for p in universes.PRESETS.get(region, []) for s in p["symbols"]}


class Listed(dict):
    """The companies with a page ({page symbol: {name, sym, bse}}), with `twins`: {a BSE-listed page's names (its scrip
    code and its page symbol): the NSE page symbol} for the companies that are listed on both exchanges and so have
    no page of their own (DK-025)."""
    twins: dict[str, str] = {}


_NAME_DROP = {"ltd", "limited", "the", "co", "company", "india", "inds", "industries", "pvt", "private"}
TRUNCATED_MIN = 12             # characters a BSE name must have before it counts as a cut-off form of a longer NSE name


def name_words(name) -> list[str]:
    """A company name as words for matching across exchanges: lower case, no punctuation, without Ltd, Limited, India…"""
    return [w for w in re.sub(r"[^a-z0-9 ]", " ", str(name or "").lower()).split() if w not in _NAME_DROP]


def cut_form_of(short: list[str], long: list[str]) -> bool:
    """Whether `short` is `long` cut short: every word the same, the last one possibly cut part-way ("relic technolog"
    for "relic technologies"). BSE's list cuts long names, so its entry reads as a start of the NSE one."""
    if len(short) < 2 or len(short) > len(long) or len(" ".join(short)) < TRUNCATED_MIN:
        return False
    return short[:-1] == long[:len(short) - 1] and long[len(short) - 1].startswith(short[-1])


def same_company(bse_name, nse_name, same_symbol: bool = False) -> bool:
    """Whether two exchanges' names for a company are one company: the same words, or BSE's cut-off form of NSE's. With
    `same_symbol` (BSE trades it under the symbol NSE uses), the first word agreeing is enough: the symbol is shared by
    some unrelated companies, and a different first word says it is one of them."""
    a, b = name_words(bse_name), name_words(nse_name)
    if not a or not b:
        return False
    if a == b or cut_form_of(a, b):
        return True
    return same_symbol and a[0] == b[0]


def twin_pages(out: dict[str, dict], bse_ts: dict[str, str]) -> dict[str, str]:
    """{BSE page symbol (and scrip code): NSE page symbol} for each BSE-only entry of `out` that is a company NSE also
    lists (DK-025: RELICTEC and 511712 were two pages, with two canonical addresses, for one company). `bse_ts` is
    {scrip code: BSE trading symbol}. Matched on the symbol BSE trades it under when NSE has that symbol and the names
    agree on their first word, else on the name (the same words, or BSE's cut-off form of NSE's, one NSE company
    only). No ISIN is kept for a BSE listing, so the name is what a match rests on."""
    nse = {k: name_words(v.get("name")) for k, v in out.items() if not v.get("bse") and v.get("name")}
    by_first: dict[str, list[str]] = {}
    for k, w in nse.items():
        if w:
            by_first.setdefault(w[0], []).append(k)
    twins: dict[str, str] = {}
    for page, v in out.items():
        code = v.get("bse")
        if not code or not v.get("name"):
            continue
        ts = bse_ts.get(code, "")
        hit = ts if ts in out and not out[ts].get("bse") and same_company(v["name"], out[ts].get("name"), same_symbol=True) else None
        if not hit and ts in out and not out[ts].get("bse") and not out[ts].get("name"):
            hit = ts                       # NSE's entry has no name to compare (one of StratLab's own lists): the shared symbol stands
        if not hit:
            words = name_words(v["name"])
            found = [k for k in by_first.get(words[0], []) if same_company(v["name"], out[k]["name"])] if words else []
            hit = found[0] if len(found) == 1 else None
        if hit:
            twins[page] = twins[code] = hit
    return twins


def companies(region: str) -> dict[str, dict]:
    """{page symbol: {name, sym, bse}} for every company with a page. From the stored lists (the whole-market audit's
    and this module's daily one), and StratLab's own sector lists so there is always something. A BSE-only company's
    page is under its BSE trading symbol (or its scrip code when that isn't known); `sym` is what the sources take. A
    BSE listing of a company NSE also lists has no page of its own: its names are in `.twins`, which find() sends to the
    NSE page (DK-025). A BSE name, which BSE writes in capitals, is in proper case."""
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
                out[page] = {"name": proper_name(name), "sym": code, "bse": code}
            else:
                out[sym.upper()] = {"name": name, "sym": sym.upper(), "bse": None}
    out = {k: v for k, v in out.items() if k and len(k) <= 20 and "/" not in k and not UNLISTED_NAMES.match(str(v.get("name") or ""))}
    listed = Listed()
    if region == "IN":
        listed.twins = twin_pages(out, {c: str((v or {}).get("ts") or "").upper() for c, v in bse.items() if isinstance(v, dict)})
    listed.update({k: v for k, v in out.items() if k not in listed.twins})
    with _companies_lock:
        _companies[region] = (time.time(), listed)
    return listed


def nse_twins() -> dict[str, str]:
    """{BSE scrip code or BSE page symbol: NSE symbol} for companies listed on both exchanges, whose BSE listing has no
    page of its own, so a list of companies can keep each one once."""
    return dict(getattr(companies("IN"), "twins", {}) or {})


def find(region: str, symbol: str) -> tuple[str, dict] | None:
    """(page symbol, company) for a symbol in an address, case-insensitively; None for a company with no page. A US
    share class reads the same written either way (BRK.B, BRK-B, BRK/B), and the address then redirects to one."""
    cos = companies(region)
    s = (symbol or "").strip().upper()
    if s in cos:
        return s, cos[s]
    if region == "IN":
        from .us_ticker import canon_in
        s = canon_in(s)          # TCS.NS, TCS.BO and NSE:TCS are TCS's page, at TCS's address (RC5-010)
        if s in cos:
            return s, cos[s]
    twin = getattr(cos, "twins", {}).get(s)          # a BSE listing of a company NSE lists too: its one page is NSE's (DK-025)
    if twin in cos:
        return twin, cos[twin]
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


RENAME_HOPS = 3                  # an old symbol that was renamed again is followed this far


def _rename_of(region: str, symbol: str) -> str | None:
    """What one old symbol became, from the places the app already records it: the exchange's F&O circulars that rename a
    stock (fo_changes), a company merged into another (intel.company.MERGED), the known symbol changes the company-data reader
    keeps (Tata Motors' demerger), and the short names and former names the search resolves to exactly one company
    (name_search.ALIASES: ZOMATO is ETERNAL). None when nothing says."""
    if region == "IN":
        try:
            from . import fo_changes
            events = [x for x in fo_changes.load_events() if x.get("kind") == "rename" and str(x.get("was_symbol") or "").upper() == symbol and x.get("symbol")]
            if events:
                return str(max(events, key=lambda x: str(x.get("effective") or ""))["symbol"]).upper()
        except Exception as ex:                  # storage down: the other sources still answer
            print("stock pages: renames not read:", str(ex)[:120])
        from .intel.company import MERGED
        from .intel.screener import Screener
        into = (MERGED.get(symbol) or {}).get("into_symbol") or Screener.RENAMED.get(symbol)
        if into:
            return into
    from . import name_search
    one = name_search.ALIASES.get(region, {}).get(symbol) or []
    return one[0] if len(one) == 1 else None


def renamed_to(region: str, symbol: str) -> str | None:
    """The page symbol a company's old ticker now has (ZOMATO -> ETERNAL), for a ticker with no page of its own: the address
    then redirects there for good, so the pages Google found under the old ticker pass to the new one. None for a ticker
    nothing says was renamed, which stays a 404."""
    cur = (symbol or "").strip().upper()
    if not cur or len(cur) > 20 or region not in REGIONS.values():
        return None
    seen = {cur}
    for _ in range(RENAME_HOPS):
        nxt = _rename_of(region, cur)
        if not nxt or nxt in seen:
            return None
        seen.add(nxt)
        hit = find(region, nxt)
        if hit:
            return hit[0]
        cur = nxt
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


def close_of(region: str, d: date) -> str | None:
    """The market's closing time ("HH:MM") on a day: the calendar's (early closes included), else its usual hours."""
    from .data.calendar import day_close
    from .data.markets import BY_ID
    return day_close(region, d) or ((BY_ID.get(region) or {}).get("hours") or {}).get("close")


def next_settle(region: str, now: datetime | None = None) -> datetime | None:
    """When the market's next close settles (its close plus settle(region)), after `now`; None without its hours."""
    from .data.calendar import is_trading_day
    from .data.markets import BY_ID
    m = BY_ID.get(region) or {}
    if not (m.get("hours") or {}).get("close"):
        return None
    tz = ZoneInfo(m.get("tz") or "UTC")
    local = (now or datetime.now(timezone.utc)).astimezone(tz)
    d = local.date()
    for _ in range(15):
        hh, mm = (close_of(region, d) or m["hours"]["close"]).split(":")
        at = datetime.combine(d, dtime(int(hh), int(mm)), tz) + timedelta(seconds=settle(region))
        if at > local and is_trading_day(region, d):
            return at
        d += timedelta(days=1)
    return None


def cache_control(region: str | None, f: dict | None = None, now: datetime | None = None) -> str:
    """A company page's Cache-Control: the day-long CACHE_CONTROL, or a minute (BEHIND_CACHE) for a page whose price is from
    before its market's latest close, so that page follows its refresh within a minute or two and never says "the market
    has closed since" for long after it has caught up (R13-006). A page that is up to date says "As of <the close>" and stays
    true of that close whenever it is read (SEO-1: this used to end every copy at the market's next settle point, so a crawler
    met a cold build on most requests)."""
    if f and region and behind(f, now):
        return BEHIND_CACHE
    return CACHE_CONTROL


def html_ttl(region: str | None, now: datetime | None = None) -> int:
    """How long a rendered page is kept in memory: ten minutes, never past the market's next settle point."""
    nxt = next_settle(region, now) if region else None
    if nxt is None:
        return 600
    return max(MIN_CACHE, min(600, int((nxt - (now or datetime.now(timezone.utc))).total_seconds())))


def last_close(region: str, now: datetime | None = None) -> tuple[date, datetime]:
    """(day, when) of the market's latest settled close: the latest trading day whose close was at least settle(region)
    ago. Before then, today's candle is still a session in progress (or not yet the official close), not a close."""
    from .data.calendar import is_trading_day
    from .data.markets import BY_ID
    m = BY_ID.get(region) or {}
    tz = ZoneInfo(m.get("tz") or "UTC")
    local = (now or datetime.now(timezone.utc)).astimezone(tz)
    d = local.date()
    for _ in range(15):
        hh, mm = (close_of(region, d) or "23:59").split(":")
        at = datetime.combine(d, dtime(int(hh), int(mm)), tz)
        if is_trading_day(region, d) and at + timedelta(seconds=settle(region)) <= local:
            return d, at
        d -= timedelta(days=1)
    hh, mm = (close_of(region, d) or "23:59").split(":")
    return d, datetime.combine(d, dtime(int(hh), int(mm)), tz)


SETTLING_MARKETS = ("US",)      # where the app's prices say they are still settling after the bell (India: R8B-001's official close)


def settling(region: str, now: datetime | None = None) -> str | None:
    """The day (ISO) whose closing prints are still settling: from a trading day's close until settle(region) after it,
    in a market whose app prices say so; None otherwise. R13-005: from 16:00 to about 16:30 ET the company header, the
    scans and the chart showed provisional prints, all labelled "Last close" and disagreeing by a few cents."""
    if region not in SETTLING_MARKETS:
        return None
    from .data.calendar import is_trading_day
    from .data.markets import BY_ID
    m = BY_ID.get(region) or {}
    tz = ZoneInfo(m.get("tz") or "UTC")
    local = (now or datetime.now(timezone.utc)).astimezone(tz)
    close = close_of(region, local.date())
    if not close:
        return None
    hh, mm = close.split(":")
    at = datetime.combine(local.date(), dtime(int(hh), int(mm)), tz)
    try:
        trading = is_trading_day(region, local.date())
    except Exception:
        return None
    return local.date().isoformat() if trading and at <= local < at + timedelta(seconds=settle(region)) else None


DUE_AT = {"IN": "18:30 IST"}     # when the evening's stored numbers (breadth, screens, public pages) are usually in


def day_due(region: str, have: str | None, now: datetime | None = None, due: str | None = None, during: bool = False) -> dict | None:
    """When numbers stored once a day are still of an older session than the one that closed today: {"day" (today's
    session), "due" (about when its numbers come, or None)}; else None. A page then says "Latest: 8 Oct · 9 Oct due
    about 18:30 IST" instead of "Today's numbers · 8 Oct" on the evening of 9 Oct (R8B-008). `due` names another time
    than DUE_AT's. With `during`, a session still trading counts too, answered with "during": True (R9R-007: the US
    breadth page said "Today's numbers · 8 Oct" three minutes after the US open, with no live view to explain it)."""
    from .data.calendar import is_trading_day
    from .data.markets import BY_ID
    if not have:
        return None
    m = BY_ID.get(region) or {}
    tz = ZoneInfo(m.get("tz") or "UTC")
    oh, om = ((m.get("hours") or {}).get("open") or "00:00").split(":")
    local = (now or datetime.now(timezone.utc)).astimezone(tz)
    d = local.date()
    if not is_trading_day(region, d) or str(have)[:10] >= d.isoformat():
        return None
    hh, mm = (close_of(region, d) or "23:59").split(":")
    closed = local >= datetime.combine(d, dtime(int(hh), int(mm)), tz)
    if not closed and not (during and local >= datetime.combine(d, dtime(int(oh), int(om)), tz)):
        return None
    out = {"day": d.isoformat(), "due": due or DUE_AT.get(region)}
    return out if closed else {**out, "during": True}


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


NEW_LISTING_DAYS = 340         # candles reaching back less than this are of a share listed within the year (as intel/company.py counts it)
RANGE_DAYS = 365               # the 1-year range runs over exactly this many days back from the last close
RANGE_SLACK = 1.25             # an exchange figure further than this from the candle's is another basis (an unadjusted one)


def year_bars(bars: list[dict]) -> list[dict]:
    """The candles of the last 365 days: those dated after the same date a year before the last candle (R10V-003: the
    last 252 candles of TITAN reached back to 3 Oct 2025, 371 days before 9 Oct 2026, and showed that day's low)."""
    last = str(bars[-1].get("t") or "")[:10] if bars else ""
    try:
        start = (date.fromisoformat(last) - timedelta(days=RANGE_DAYS)).isoformat()
    except ValueError:
        return bars[-252:]
    return [b for b in bars if str(b.get("t") or "")[:10] > start]


def year_low_high(bars: list[dict]) -> tuple[float | None, float | None]:
    """The lowest low and highest high of the last 365 days of daily candles (year_bars): the one 1-year window every
    page uses, the app's company page, the public pages, the screens built from them (R12-003: the app's TITAN low was
    ₹3,401.00 of 6 Oct 2025, 368 days back, from its last 252 candles, against the public page's ₹3,506.50)."""
    year = year_bars(bars) if bars else []
    highs = [x for x in (_num(b.get("h")) for b in year) if x is not None]
    lows = [x for x in (_num(b.get("l")) for b in year) if x is not None]
    return (min(lows) if lows else None), (max(highs) if highs else None)


# The broker's daily candles of an Indian stock are adjusted back for an extraordinary dividend, one above 2% of the price
# the day before it went ex (the exchange's rule for its derivatives): every candle before the ex-date is scaled by
# (P - D) / P (R12-001: INFY's ₹25 of 10 Jun 2026, 2.12% of its 1,180.30 close, scaled its 3 Feb 2026 high of 1,728.00 to
# 1,691.40; ULTRACEMCO's ₹240 of 30 Jul 2026, 2.00% of 11,998.00, took its 13,110.00 high to 12,848 and its 10,325.00 low
# to 10,118, a print no session had). A 1-year range is of prices as they traded, so the adjustment is undone for it.
EXTRA_DIVIDEND = 0.0198        # a dividend above this share of the cum-dividend close was adjusted for (2%, less rounding)
TRADED_MATCH = 0.006           # another source's as-traded candle within this of the undone close is the same session's print


def dividend_list(rows, restate: bool = False) -> list[dict]:
    """[{"date", "amount"}] from a dividends list in either shape: the price history's ({"date", "amount"}) or the
    corporate actions card's ({"ex_date", "kind": "dividend", "amount"}). `restate`: each amount as declared, divided by
    the factor of every split or bonus in the list with a later ex-date, to the price after them (the exchange's amounts
    are per share at the time; the price history's are already adjusted)."""
    out = []
    later = restating_actions(rows) if restate else []
    for d in rows or []:
        if not isinstance(d, dict) or (d.get("kind") not in (None, "dividend")):
            continue
        day, amt = str(d.get("date") or d.get("ex_date") or "")[:10], _num(d.get("amount"))
        if day and amt and amt > 0:
            from .corp_actions import is_special
            out.append({"date": day, "amount": amt / restated_by(later, day), **({"special": True} if is_special(d) else {})})
    return out


def special_in_year(dividends: list[dict], as_of: str | None) -> float | None:
    """The special dividends among those dividend_yield counts (ex-date in the year to `as_of`), per share; None when none."""
    try:
        end = date.fromisoformat((as_of or "")[:10])
    except ValueError:
        return None
    start = (end - timedelta(days=365)).isoformat()
    total = sum(_num(d.get("amount")) or 0 for d in dividends or [] if d.get("special") and start < str(d.get("date") or "") <= end.isoformat())
    return round(total, 2) if total else None


def restating_actions(rows) -> list[tuple[str, float]]:
    """(ex-date, factor) of each split or bonus in a corporate actions list."""
    from .corp_actions import adjusts
    return [(str(a.get("ex_date") or "")[:10], a["factor"]) for a in rows or [] if isinstance(a, dict) and adjusts(a)]


def restated_by(actions: list[tuple[str, float]], day: str) -> float:
    """The product of the factors of the splits and bonuses with an ex-date after `day`."""
    out = 1.0
    for ex, f in actions:
        if ex > day:
            out *= f
    return out


def as_traded(bars: list[dict], dividends, reference=None) -> list[dict]:
    """Daily candles as the exchange printed them: the broker's scaling for each extraordinary dividend (see
    EXTRA_DIVIDEND) undone on the candles before its ex-date. A candle the broker scaled has the close (P - D) the day
    before the ex-date, so the dividend's share of the price is D / (close + D), and the scale close / (close + D).
    The broker rounds the scaled prices, so an undone price can be a tick or so off: `reference()`, when given, is called
    only if something was undone and gives another source's daily candles of the same listing as traded; a candle whose
    close agrees with the undone one (TRADED_MATCH) takes that candle's own prices. The candles given are not changed;
    the ones undone carry "traded": True."""
    if not bars:
        return bars
    divs = sorted(dividend_list(dividends), key=lambda d: d["date"], reverse=True)
    if not divs:
        return bars
    days = [str(b.get("t") or "")[:10] for b in bars]
    out = None
    for d in divs:                                  # newest first: an older one's close is read with the newer undone
        i = next((k for k, day in enumerate(days) if day >= d["date"]), None)
        if not i:                                   # after the last candle, or before the first: nothing to undo
            continue
        cur = out or bars
        prev = _num(cur[i - 1].get("c"))
        if not prev or prev <= 0 or d["amount"] / (prev + d["amount"]) <= EXTRA_DIVIDEND:
            continue
        k = (prev + d["amount"]) / prev
        out = list(cur)
        for j in range(i):
            b = out[j]
            out[j] = {**b, **{x: round(_num(b[x]) * k, 2) for x in ("o", "h", "l", "c") if _num(b.get(x)) is not None},
                      "traded": True}
    if out is None:
        return bars
    if reference:
        try:
            ref = {str(r.get("t") or "")[:10]: r for r in (reference() or []) if isinstance(r, dict)}
        except Exception as ex:                     # the undone candles rather than none
            print("as-traded candles: reference not read:", str(ex)[:120])
            ref = {}
        for j, b in enumerate(out):
            r = ref.get(days[j]) if b.get("traded") else None
            rc, bc = (_num(r.get("c")), _num(b.get("c"))) if r else (None, None)
            if rc and bc and abs(rc / bc - 1) <= TRADED_MATCH and all(_num(r.get(x)) is not None for x in ("o", "h", "l")):
                out[j] = {**b, **{x: float(r[x]) for x in ("o", "h", "l", "c")}}
    return out


def fit_to_exchange_range(bars: list[dict], row, report_day: str | None) -> list[dict]:
    """Daily candles held to the exchange's own 52-week high and low for the stock (`row`: [high, its day, low, its day],
    from the report of `report_day`; official_close.ranges). A candle's extreme beyond the exchange's, within the report's
    year, is a stray print the exchange doesn't count (R10V-003: ULTRACEMCO's 10,118.00 low matched no bar of the
    exchange's or any price history, whose lowest was 10,325.00 on 23 Mar 2026): it is brought back to the exchange's
    figure. A candle short of the exchange's high or low on the day the report names is brought out to it (INFY's
    1,728.00 of 3 Feb 2026, which the broker's candle clipped at 1,691.40). A figure further than RANGE_SLACK off is another
    basis (unadjusted), and left alone. The candles given are not changed."""
    if not bars or not row or not report_day or len(row) < 4:
        return bars
    hi, hi_day, lo, lo_day = row[:4]
    try:
        start = (date.fromisoformat(report_day) - timedelta(days=RANGE_DAYS + 1)).isoformat()
    except ValueError:
        return bars
    out = None
    for i, b in enumerate(bars):
        d = str(b.get("t") or "")[:10]
        if not d or d > report_day:
            continue
        h, l, c = _num(b.get("h")), _num(b.get("l")), _num(b.get("c"))
        # (a candle's extremes are never brought inside its own close: the exchange's figure leaves out a closing auction's print, and
        # a page whose "Last close" is beyond its own 1-year range is wrong, RC4-011)
        top = lambda v: max(float(v), c) if c is not None else float(v)         # noqa: E731
        bottom = lambda v: min(float(v), c) if c is not None else float(v)      # noqa: E731
        nb = None
        if hi and h is not None:
            if d == hi_day and h < hi <= h * RANGE_SLACK:
                nb = {**b, "h": top(hi)}
            elif d >= start and h > hi and h <= hi * RANGE_SLACK:
                nb = {**b, "h": top(hi)}
        if lo and l is not None:
            if d == lo_day and l > lo >= l / RANGE_SLACK:
                nb = {**(nb or b), "l": bottom(lo)}
            elif d >= start and l < lo and l >= lo / RANGE_SLACK:
                nb = {**(nb or b), "l": bottom(lo)}
        if nb:
            out = out or list(bars)
            out[i] = nb
    return out if out is not None else bars


def price_facts(bars: list[dict], region: str | None = None, now: datetime | None = None) -> dict:
    """The last close, its date and the range over the last 365 days of daily candles. With `region`, only closed
    sessions count (see closed_bars), so the price is the close of the day it's dated."""
    bars = closed_bars(bars, region, now)
    if not bars:
        return {}
    low, high = year_low_high(bars)
    out = {"price": _num(bars[-1].get("c")), "price_at": str(bars[-1].get("t") or "")[:10], "price_basis": "close",
           "high52": high, "low52": low, "price_official": bool(bars[-1].get("official"))}
    # a share listed within the year: its range is since its first day of trading, and the page says so (RC1-007: ZETWERK's
    # "1-year range" two days after listing)
    try:
        first, last = str(bars[0].get("t") or "")[:10], out["price_at"]
        if (date.fromisoformat(last) - date.fromisoformat(first)).days < NEW_LISTING_DAYS:
            out["range_since"] = first
    except ValueError:
        pass
    return out


MOVE_BOUNDS = (0.6, 1.7)      # a day's move beyond this is a split or bonus, not the price: ratios are not scaled by it


def split_since(region: str, symbol: str | None, since) -> bool:
    """Whether a split or bonus of the company has an ex-date after `since` (a day, or a time, as ISO text), from the
    stored corporate actions (no read of any source). False without a symbol or a stored history."""
    since = str(since or "")[:10]
    if not symbol or not since:
        return False
    try:
        from .corp_actions import actions_for
        return any(ex > since for ex, _ in restating_actions(actions_for(region, symbol, None, fetch=False)))
    except Exception:
        return False


def can_reprice(old, new, region: str = "IN", symbol: str | None = None, since=None) -> bool:
    """Whether ratios worked out at the price `old` can be scaled to `new`: not across a move outside MOVE_BOUNDS, and not
    across a split or bonus with an ex-date after `since` (it changes the price, not the company's value)."""
    if not (MOVE_BOUNDS[0] <= new / old <= MOVE_BOUNDS[1]):
        return False
    return not (since and abs(new / old - 1) > 0.03 and split_since(region, symbol, since))


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
    if old_p and old_p > 0 and can_reprice(old_p, new_p, f.get("region") or "IN", f.get("symbol"), f.get("price_at")):
        k = new_p / old_p
        for key in ("market_cap", "pe"):
            if _num(f.get(key)) is not None:
                out[key] = round(_num(f[key]) * k, 2)
        if _num(f.get("div_yield")) is not None:
            out["div_yield"] = round(_num(f["div_yield"]) / k, 2)
    if analyse:
        try:
            t = analyse(bars) or {}
            # a read with too few candles for the 150-day average has no Stage: the page's own stays rather than going
            # blank (DE-009: TCS and INFY had no Stage in the screens, while their candles give Stage 1)
            if t.get("stage") is not None or f.get("stage") is None:
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
    if can_reprice(old, new):
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


RANGE_SLACK = 1.25      # as official_close.RANGE_SLACK: a report figure this far beyond the page's is another basis (unadjusted)


def with_week52_report(f: dict | None, report: dict | None, symbol: str | None = None) -> dict | None:
    """A page's facts with the exchange's own 52-week high and low taken in (never narrowing the range): a page stored
    before that report widened the candles kept the candles' range (R10O-007: the public INFY page read ₹1,691.40 after the
    app, on the corrected candles, read ₹1,728.00). Served that way, with no rebuild, so every stored page agrees with the
    app from the first request. `report` is official_close.ranges(): {"rows": {symbol: [high, day, low, day]}}."""
    if not f or f.get("region") != "IN":
        return f
    from .official_close import range_row
    row = range_row(symbol or f.get("symbol") or "", report)        # None for a report on the basis before a split
    if not row:
        return f
    hi, lo = _num(row[0]), _num(row[2])
    # LIVE1B-074: the exchange's report lags a session, so its 52-week window starts a day earlier than the page's own year: a high or low it
    # set on a day before the page's year (SBIN's ₹906.00 of 27 Oct 2025 on a page of 28 Oct 2026) is not this page's
    try:
        start = (date.fromisoformat(str(f.get("price_at") or "")[:10]) - timedelta(days=RANGE_DAYS)).isoformat()
    except ValueError:
        start = None
    if start:
        hi = hi if str(row[1] or "")[:10] > start else None
        lo = lo if str(row[3] or "")[:10] > start else None
    cur_hi, cur_lo = _num(f.get("high52")), _num(f.get("low52"))
    out = dict(f)
    if hi is not None and cur_hi is not None and cur_hi < hi <= cur_hi * RANGE_SLACK:
        out["high52"] = hi
    if lo is not None and cur_lo is not None and cur_lo / RANGE_SLACK <= lo < cur_lo:
        out["low52"] = lo
    # a figure in whole rupees (the fundamentals source's, cut down, when the page was built with no daily candles; the
    # page says so with range_whole) with the exchange's within a rupee of it: the same price, to the paisa (DK-028: TCS
    # ₹1,976.00 against 1,976.80, INFY ₹980.00 against 980.40). A page stored before that was marked is told by the
    # figure being whole.
    whole = lambda v: v is not None and v == int(v)          # noqa: E731
    if hi is not None and cur_hi is not None and 0 < abs(hi - cur_hi) < 1 and (f.get("range_whole") or whole(cur_hi)):
        out["high52"] = hi
    if lo is not None and cur_lo is not None and 0 < abs(lo - cur_lo) < 1 and (f.get("range_whole") or whole(cur_lo)):
        out["low52"] = lo
    return out if (out.get("high52"), out.get("low52")) != (f.get("high52"), f.get("low52")) else f


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
    - a US value under a year's profit (PE_MIN_US): a share count far too low;
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
    if region == "IN":
        price, sales = _num(f.get("price")), _latest_sales(f)
        if price and price > 0 and cap * 1e7 / price > IN_SHARES_MAX:
            return "implied share count out of range"
        if sales is not None and sales > 0 and cap / sales > IN_PS_MAX:
            return "out of line with revenue"
    if region == "US":
        profit, pe = _num(f.get("profit_usd")), _num(f.get("pe"))
        if profit is None and str(f.get("unit") or "$").startswith("$"):
            profit = _num(f.get("profit_ttm"))
        if pe is not None and 0 < pe < PE_MIN_US or profit is not None and profit > 0 and cap / profit < PE_MIN_US:
            return "implied share count out of range"
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


CAP_UNAVAILABLE = ("Market cap unavailable: the value worked out from the share count and the price doesn't agree with the "
                   "company's reported figures, so it isn't shown, nor is P/E.")


def india_snap_checked(snap: dict, p: dict) -> dict:
    """An Indian company's fundamentals summary (after at_live_price) with the public page's market value check
    (cap_problem) applied: the Research page, the deep dive, the deck, the valuation and the AI read show no market value,
    and nothing worked out from it, where the public page says "Market cap unavailable". A failed value is blanked with
    the P/E (as shown_pe does), and "cap_problem" says why."""
    pl = p.get("pl") or {}
    sales = next((v for k, v in (pl.get("rows") or {}).items() if str(k).lower().startswith(("sales", "revenue"))), [])
    years = [{"year": c, "sales": s} for c, s in zip(pl.get("cols") or [], sales) if str(c).strip().upper() != "TTM"][-5:]
    why = cap_problem({"region": "IN", "market_cap": snap.get("market_cap_cr"), "price": snap.get("price"),
                       "unit": p.get("unit") or "₹ crore", "market_cap_unit": "₹ crore", "years": years})
    return {**snap, "market_cap_cr": None, "pe": None, "cap_problem": why} if why else snap


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


def figures_end(f: dict | None) -> str | None:
    """The day the newest year in a page's table ended: what its return on equity, margins and debt to equity are on."""
    years = [y for y in (f or {}).get("years") or [] if isinstance(y, dict) and y.get("year")]
    return _month_end(re.sub(r"\s+\d+m$", "", str(years[-1]["year"]))) if years else None


def figures_stale(f: dict | None) -> bool:
    """Whether the newest year in the table ended more than about 15 months before the price (PE_STALE_DAYS, the rule
    P/E has): then the return on equity and the margins in the key figures, which are that year's, are n/a rather than
    presented as current (R10V-002: Dr. Reddy's key figures were its year to Mar 2025 beside a Sep 2026 price, its 20-F
    of 29 May 2026 not read yet)."""
    f = f or {}
    end, at = figures_end(f), str(f.get("price_at") or "")[:10]
    try:
        return bool(end and at) and (date.fromisoformat(at) - date.fromisoformat(end)).days > PE_STALE_DAYS
    except ValueError:
        return False


def annual_behind(f: dict | None) -> bool:
    """Whether the company's newest annual report (the filing date the page was built with) was filed more than a year
    and a month after the newest year in its table ended: that report's year isn't in the table, so the page is built
    again soon rather than kept (R10V-002: a 20-F filed on 29 May 2026 beside a table to Mar 2025)."""
    f = f or {}
    end, filed = figures_end(f), str(f.get("annual_filed") or "")[:10]
    if not filed and (f.get("v") or 1) < FACTS_VERSION:
        filed = str(f.get("price_at") or "")[:10]         # a page from before the filing date was kept: the price's date, a sweep of the old tables
    try:
        return bool(end and filed) and (date.fromisoformat(filed) - date.fromisoformat(end)).days > ANNUAL_BEHIND_DAYS
    except ValueError:
        return False


BEHIND_RETRY = 7 * 86400       # a page still behind after a build that came after its report was filed: swept again weekly
SEC_DATA_LAG = 4 * 86400       # how long after a filing the SEC's data has it


def behind_due(f: dict | None, ts: float | None, now: float | None = None) -> bool:
    """Whether the screens' sweep should build a page that is behind its newest annual report (annual_behind) ahead of
    the rest: it was built before that report's data could be out, or not for a week. A page built after it and still
    behind is one whose report doesn't give the year as one period (R12-006: Bally's 2025 10-K gives 1 Jan to 7 Feb and
    8 Feb to 31 Dec) or can't be read: building it every half hour first kept the sweep from ever reaching the others
    (Simec's and Synthesis's pages kept tables a year or more behind until someone opened them)."""
    if not annual_behind(f):
        return False
    now = time.time() if now is None else now
    ts = ts or 0.0
    filed = str((f or {}).get("annual_filed") or "")[:10]
    try:
        filed_ts = datetime.fromisoformat(filed).replace(tzinfo=timezone.utc).timestamp() if filed else 0.0
    except ValueError:
        filed_ts = 0.0
    return ts < filed_ts + SEC_DATA_LAG or now - ts >= BEHIND_RETRY


def cap_missing_reason(f: dict | None) -> str | None:
    """Why a page has no market cap at all (not why a cap failed its checks: see cap_problem), in words, when the page
    knows: None when it has one or has no price to multiply (R10V-004: Baidu and BP showed nothing). A page that doesn't
    know why (one stored before the reason was kept) is "unknown": the item is still shown, as n/a, with a note that
    claims no cause (R12-005: BP's stored page showed no Market cap item at all)."""
    f = f or {}
    if _num(f.get("market_cap")) is not None or _num(f.get("price")) is None or f.get("not_company"):
        return None
    if f.get("no_numbers"):
        return "no_numbers"
    return "shares" if f.get("cap_why") == "shares" else "unknown"


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
    """The dividend yield to show: None when unknown, above YIELD_MAX, when the market value it's measured on fails a
    check, and a 0% from a price history that lists no dividend while the company's own accounts show dividends paid (R6V-011)."""
    f = f or {}
    dy = _num(f.get("div_yield"))
    if dy is None or dy > YIELD_MAX or (f.get("region") == "US" and cap_problem(f)):
        return None
    if dy == 0 and f.get("divs_paid"):
        return None
    return dy


def shown_industry(parts, plain: bool = False) -> list[str]:
    """The industry path as a page shows it: a filing category that starts with the division before it, "Services" then
    "Services-Prepackaged Software", without that word again. `plain`: the SEC's classification worded for a reader
    (plain_industry)."""
    out: list[str] = []
    for x in _dedupe(parts):
        for o in out:
            if x.lower().startswith(o.lower() + "-"):
                x = x[len(o) + 1:].strip()
        out.append(plain_industry(x) if plain else x)
    return out


_SIC_ACRONYMS = {"tv": "TV", "us": "US", "hmos": "HMOs", "reits": "REITs", "reit": "REIT", "ii": "II", "iii": "III", "ev": "EV"}
_SIC_PREFIX = re.compile(r"^(?:services|retail|wholesale)\s*-\s*", re.I)
_SIC_CATCHALL = re.compile(r"[,\s]*\(?\b(?:nec|not elsewhere classified)\b\)?\s*$", re.I)


def plain_industry(text: str) -> str:
    """The SEC's industry title worded for a reader (DK-024: "Motor Vehicles & Passenger Car Bodies"): "&" as "and",
    sentence case, without a "Retail-" or "Services-" prefix (the division beside it says that) or the catch-all "NEC",
    and with TV and the like in capitals. Names that have lower case already, an Indian industry's, are left alone."""
    t = str(text or "").strip()
    if not t or t != t.title():
        return t
    t = _SIC_CATCHALL.sub("", _SIC_PREFIX.sub("", t)).strip(" ,-") or t
    words = t.replace(" & ", " and ").split(" ")
    out = " ".join(_SIC_ACRONYMS.get(w.lower().strip("(),"), w.lower()) for w in words)
    return out[:1].upper() + out[1:]


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
    # (cash from operations too, for a theme's cash-against-profit line: THEME-1; a page stored before has none, and the line says how many it counts)
    years = [{k: y.get(k) for k in ("year", "sales", "profit", "opm", "debt", "cfo")} for y in (nums.get("years") or [])[-5:]]
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
    # a bank or lender (its results have no operating margin), or an insurer or other financial: EBITDA margin and debt to
    # equity mean nothing for them, and the page leaves them out (DK-023: LICI showed both)
    financial = bool(nums.get("bank")) or _financial(p, nums, symbol)
    # no daily candles: the year's range is the fundamentals source's, in whole rupees cut down (TCS ₹1,976 against the
    # exchange's 1,976.80), which the exchange's 52-week report replaces when the page is served (DK-028)
    whole_range = _num(prices.get("low52")) is None and _num(snap.get("low52")) is not None
    name = public_text(p.get("name") or symbol)
    if region == "US":
        name = strip_registration(name)
    return {
        "v": FACTS_VERSION, **{k: checks[k] for k in ("sales_usd", "cap_unverified", "not_company", "divs_paid", "pe_basis", "pe_end", "eps",
                                                      "foreign", "profit_usd", "annual_unread", "annual_filed", "no_numbers", "cap_why",
                                                      "type_unread", "eps_q", "no_interest", "pe_oneoff")
                               if checks.get(k) is not None},
        "region": region, "symbol": symbol, "name": name, "exchange": exchange,
        "industry": _dedupe(public_text(str(x)) for x in (p.get("industry_path") or []) if x)[:4],
        "currency": "USD" if region == "US" else "INR", "unit": nums.get("unit") or ("$ million" if region == "US" else "₹ crore"),
        "price": prices.get("price"), "price_at": prices.get("price_at"),
        "price_basis": prices.get("price_basis"),
        "high52": prices.get("high52") or snap.get("high52"), "low52": prices.get("low52") or snap.get("low52"),
        **({"range_whole": True} if whole_range else {}),
        **({"range_since": prices["range_since"]} if prices.get("range_since") else {}),
        "market_cap": snap.get("market_cap_cr"), "market_cap_unit": "$ million" if region == "US" else "₹ crore", "pe": snap.get("pe"), "roe": snap.get("roe"), "roce": snap.get("roce"),
        "div_yield": snap.get("div_yield"), "div_special": snap.get("div_special"), "profit_ttm": _ttm_profit(p),
        "net_margin": snap.get("net_margin"), "opm": opm, "debt": snap.get("debt_cr"), "debt_equity": snap.get("debt_equity"),
        "bank": financial, "years": years, "currency_note": p.get("currency_note"), "basis": nums.get("basis"),
        "growth": {k: (nums.get("growth") or {}).get(k) for k in ("sales_cagr_3y", "profit_cagr_3y", "sales_cagr_5y", "profit_cagr_5y")},
        "stage": (trend or {}).get("stage"), "stage_days": (trend or {}).get("stage_days"),
        "st_up": (trend or {}).get("st_up"), "st_days": (trend or {}).get("st_days"),
        "filings": listed_filings(filings)[:6],
        "red_flags": red_flags, "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


_EMPTY_SUBJECTS = {"update", "updates", "general update", "general updates", "other", "others", "miscellaneous"}
_EMPTY_LABELS = {"other update", "general update", "update"}
# filings that are routine paperwork, not news (DK-018: "Copy of Newspaper Publication" and its like filled RELIANCE's list)
FILING_NOISE = re.compile(r"newspaper|trading window|(?:loss|duplicate)\b.{0,30}\bcertificate|investor complaints|regulation 74\s*\(5\)|"
                          r"depositories and participants|compliance certificate", re.I)
# "Reliance Industries Limited has informed the Exchange regarding …": the part before what the filing is about
_FILING_LEAD = re.compile(r"^.{0,140}?\b(?:has|have|had)\s+(?:informed|intimated|apprised|submitted|filed|enclosed)\s+(?:the\s+)?"
                          r"(?:stock\s+)?exchanges?\b[,.]?\s*(?:(?:about|regarding|that|on|of|the|with respect to|in respect of)\s+)*", re.I)
FILING_SUMMARY_MAX = 110


def filing_title(t: str) -> str:
    """A filing's "type: subject" with the part that says nothing left out: "Credit rating: Credit Rating" and "Other
    update: Updates" read as the type alone, "Other update: Copy of Newspaper Publication" as the subject alone
    (R91-004: RELIANCE's list was hard to scan)."""
    label, sep, rest = str(t or "").partition(": ")
    if not sep:
        return str(t or "")
    lab, sub = label.strip(), rest.strip()
    if not sub or sub.lower() == lab.lower() or sub.lower() in _EMPTY_SUBJECTS:
        return lab
    if lab.lower() in _EMPTY_LABELS:
        return sub
    return f"{lab}: {sub}"


def filing_summary(text: str, label: str = "") -> str:
    """What a filing is about, from the exchange's summary of it: the first sentence without the company's "has informed
    the Exchange regarding" lead, at most FILING_SUMMARY_MAX characters; "" when nothing but the type is left."""
    t = re.sub(r"\s+", " ", str(text or "")).strip()
    m = _FILING_LEAD.match(t)
    if m:
        t = t[m.end():]
    t = t.strip(" .:-–")
    if label and t.lower().startswith(label.lower()):
        t = t[len(label):].lstrip(" .:-–,")
    t = re.split(r"(?<=[a-z0-9\)])\.\s+(?=[A-Z])", t, maxsplit=1)[0].rstrip(" .")
    if len(t) < 6 or t.lower() in _EMPTY_SUBJECTS or t.lower() == label.lower():
        return ""
    if len(t) > FILING_SUMMARY_MAX:
        t = t[:FILING_SUMMARY_MAX].rsplit(" ", 1)[0].rstrip(" ,;:-–") + "…"
    return t[:1].upper() + t[1:]


def filing_entry(x: dict) -> dict | None:
    """One filing as the page lists it, {at, title, name, url}: `name` says what the filing is (the exchange's subject, or
    its summary when the subject is a generic "Updates"), `url` is the document on the exchange or the SEC. None for
    routine paperwork (FILING_NOISE) and for an "Other update" that says nothing (DK-018: "Other update", "Credit
    rating" and "Copy of Newspaper Publication" as bare text with no document behind them). A row that has a name
    already is returned as it is; one stored before names were kept is worked out from its title."""
    if x.get("name"):
        return x
    title = str(x.get("title") or "").strip()
    text = str(x.get("text") or "")
    lab, sep, sub = title.partition(": ")
    lab, sub = lab.strip(), sub.strip()
    generic = bool(sep) and (not sub or sub.lower() == lab.lower() or sub.lower() in _EMPTY_SUBJECTS)
    if FILING_NOISE.search(title) or (generic and FILING_NOISE.search(text[:240])):
        return None
    if not sep:
        name = title
    elif not generic:
        name = filing_title(title)
    else:
        about = filing_summary(text, lab)
        if lab.lower() in _EMPTY_LABELS:
            name = about
        else:
            name = f"{lab}: {about}" if about else lab
    if not name:
        return None
    url = str(x.get("url") or "")
    return {"at": str(x.get("at") or "")[:10], "title": title, "name": name, **({"url": url} if url.startswith("https://") else {})}


def listed_filings(rows: list[dict]) -> list[dict]:
    """The filings a page lists: each with a name and a link (filing_entry), routine paperwork left out, a repeat
    (the same date and name) shown once. Public text only: no data source is named."""
    out = []
    for x in rows or []:
        y = filing_entry({**x, "title": public_text(str(x.get("title") or ""))[:200], "text": public_text(str(x.get("text") or ""))[:600]}) if isinstance(x, dict) else None
        if y:
            out.append({**y, "name": public_text(y["name"])})
    return unique_filings(out)


def unique_filings(rows: list[dict]) -> list[dict]:
    """Filing rows with an exact repeat (the same date and title) dropped, as the exchange lists a general update twice
    (R26-009: RELIANCE's "14 Oct 2026 Other update: General Updates" in a row twice)."""
    seen, out = set(), []
    for x in rows or []:
        k = (str(x.get("at") or "")[:10], re.sub(r"\s+", " ", str(x.get("name") or x.get("title") or "")).strip().lower())
        if k not in seen:
            seen.add(k)
            out.append(x)
    return out


_REGISTRATION = re.compile(r"\s*/\s*(?:[A-Za-z]{2}|NEW)\s*/?\s*$")


def strip_registration(name: str | None) -> str | None:
    """A US filer's name without the state of incorporation or the re-registration mark its filing appends: "Rivian
    Automotive, Inc. / DE", "APPLIED MATERIALS INC /DE/", "COSTCO WHOLESALE CORP /NEW" (DK-024)."""
    if not name:
        return name
    out = str(name).strip()
    for _ in range(2):
        out = _REGISTRATION.sub("", out).strip() or out
    return out


def _financial(p: dict, nums: dict, symbol: str) -> bool:
    """Whether the company is a lender, insurer or other financial, by the industry it is filed under: EBITDA margin and
    debt to equity aren't measures of such a business (DK-023)."""
    try:
        from . import industry
        return industry.classify(p, nums, symbol)["group"] in FINANCIAL_GROUPS
    except Exception:
        return False


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
    if (stored["facts"].get("annual_unread") or stored["facts"].get("type_unread") or annual_behind(stored["facts"])) \
            and now - ts >= UNREAD_FRESH:
        return False                     # built without its latest annual report, which couldn't be read then (R8V-003, R10V-002)
    settled = last_close(region, datetime.fromtimestamp(now, timezone.utc))[1].timestamp() + settle(region)
    # its own build, or the price job's re-read of its price, came after the market's latest settled close
    return ts >= settled or (stored.get("price_ts") or 0) >= settled


BUILT_KEY = "stocks:built:"          # stocks:built:<region> = {"at", "pages": every stored page, "shown": those with something to show}
FOREIGN_OTC = re.compile(r"^[A-Z]{4}[FY]$")      # a foreign company's US over-the-counter line: it rarely files results here


def has_content(f: dict | None) -> bool:
    """Whether a page has something to show and may be indexed: facts of a company. A listed company the sources had
    nothing on (no price and no numbers) is a short noindex page, and a fund or a note filed under a company's name a
    404 (see render)."""
    return bool(f) and not f.get("not_company") and not f.get("no_numbers")


def sitemap_ok(f: dict | None) -> bool:
    """Whether a stored page may be listed in the sitemap: it has something to show (has_content), and the build knew
    what the ticker is, so it can't turn out to be a fund's 404 when next built (R12-013: GSMT). A page whose build
    couldn't read that is built again within the hour when opened, like one whose annual report couldn't be read."""
    return has_content(f) and not (f or {}).get("type_unread")


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


LONG_STALE_DAYS = 10           # a page whose own close is older than this (calendar days) is read after the rest


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
        facts = (stored or {}).get("facts") or None
        if facts and fresh(stored, region):
            self.mem.set(key, facts, 600)            # what _get keeps for a fresh stored page, so the next view skips the parse
        return facts

    adjust = None              # (region, symbol, facts) -> facts as served: the exchange's 52-week report taken in (R10O-007)

    def get(self, region: str, symbol: str, co: dict) -> dict | None:
        """The company's facts as served: stored or built (see `_get`), with `adjust` applied."""
        f = self._get(region, symbol, co)
        if f and self.adjust:
            try:
                return self.adjust(region, symbol, f) or f
            except Exception as ex:                  # the page as stored rather than none
                print("stock pages: adjust failed:", region, symbol, str(ex)[:120])
        return f

    def _get(self, region: str, symbol: str, co: dict) -> dict | None:
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

        def long_stale(stored: dict) -> int:
            try:
                return int((day - date.fromisoformat(str(stored["facts"].get("price_at") or "")[:10])).days > LONG_STALE_DAYS)
            except ValueError:
                return 1
        with memguard.heavy("page-prices"):         # the pass parses every stored page of the market, one after another
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
                # only the sort key and the stored text are kept: parsed, thousands of due pages were some 70 MB held for the few
                # hundred a run reads (MEM-001); a page is parsed again when its turn comes
                due.append(((tries.get(symbol, 0), long_stale(stored), -(shown_cap(stored["facts"]) or 0)), symbol, raw))
        # the largest companies first, and a page the source had no newer close for at an earlier try after the rest; a
        # page whose own last close is weeks old (a suspended or delisted company) after those a close or two behind: the
        # tries start again at every deploy, and such pages took every pass (R90-002: "0 updated" for 17 hours, the pages
        # read being 504375 and IDREAM at 29 Sep, WBD at 5 Oct, ICICIPRULI and QRVO with no candles at all)
        due.sort(key=lambda x: x[0])
        done = failed = errors = 0     # errors: reads that raised, of the failed (the rest had no newer close yet)
        behind: list[str] = []         # a few pages read with no newer close: "SYMBOL (last candle 2026-10-21)", for Admin
        stopped = 0             # pages not tried because the source is down for every one of them
        ok: set[str] = set()
        for i, (_, symbol, raw) in enumerate(due[:limit]):
            if i and gap:
                sleep(gap)
            stored = db.json_value(raw, {}) if not isinstance(raw, dict) else raw
            try:
                with memguard.heavy("page-prices"):       # a page's candles are read in its turn, not through the pause between pages
                    bars = closed_bars(bars_of(region, symbol) or [], region, now)
            except Exception as ex:                   # no prices for this one today: tried again at its next build
                failed += 1
                errors += 1
                print("stock pages: price refresh failed:", region, symbol, str(ex)[:120])
                if _source_down(ex):
                    # the broker's login has ended (overnight): every other page would fail the same way, one a second;
                    # they are left for the next run instead of tried and logged one by one
                    stopped = len(due[:limit]) - i - 1
                    break
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
                if len(behind) < 5:
                    behind.append(f"{symbol} (last candle {str(bars[-1].get('t') or '')[:10] if bars else 'none'})")
            _put(prefix + symbol, stored)
            self.mem.pop(prefix + symbol)
            self.mem.pop(f"html:{region}:{symbol}")
        retry = sum(1 for _, s, _raw in due[:limit] if s not in ok and 0 < tries.get(s, 0) < self.MAX_TRIES)
        if not stopped and len(due) <= limit and not retry and (official_ready is None or official_ready(day.isoformat())):
            self.prices_done[region] = day.isoformat()            # a page still behind is tried again at its next build
        return {"refreshed": done, "left": max(0, len(due) - limit) + stopped, "failed": failed, "errors": errors,
                **({"behind": behind} if behind else {}),
                **({"source_down": True} if stopped else {}), **({"retry": retry} if retry else {}),
                **({"official": swapped} if official else {})}

    def html(self, region: str, symbol: str, co: dict) -> str:
        """The rendered page, kept in memory for ten minutes (the sector links read the screens' index)."""
        key = f"html:{region}:{symbol}"
        hit = self.mem.get(key)
        if hit is None:
            f = self.get(region, symbol, co)
            hit = render(f, region, symbol, co["name"], faq_extras(region, symbol) if has_content(f) else None)
            self.mem.set(key, hit, html_ttl(region))      # never served past the next close's settle point (R13-006)
        return hit


# ---------- companies in the same industry ----------
def _index_rows(region: str) -> list[dict]:
    from . import screens               # the screens' index of stored pages: names, industries and market values
    try:
        return screens.load_index(region).get("rows") or []
    except Exception:                    # no index yet, or storage down: StratLab's own sector lists instead
        return []


def _row_cap(region: str, r: dict | None):
    """An index row's market value, None when it fails what cap_problem can check from the row (CAP_CEILING, and for
    India the share count the value and price imply): a row stored before those checks existed never ranks on a value
    its page wouldn't show."""
    r = r or {}
    cap = _num(r.get("market_cap"))
    if cap is None or cap <= 0 or cap_problem({"region": region, "market_cap": cap, "price": r.get("price")}):
        return None
    return cap


def _sized(region: str) -> list[dict]:
    """The index's companies whose market value passed its checks, largest first. A US row must come from an index
    built after the checks existed ("cap_checked"); any row whose value fails the checks a row allows (_row_cap) is left
    out whatever its age."""
    cos = companies(region)
    out = []
    for r in _index_rows(region):
        if r.get("symbol") not in cos or _row_cap(region, r) is None:
            continue
        if region == "US" and not r.get("cap_checked"):
            continue
        out.append(r)
    return sorted(out, key=lambda r: -_num(r["market_cap"]))


LARGE_CAP = {"US": 10_000.0, "IN": 20_000.0}       # $ million, ₹ crore: a large company, whose peers should be of its size
PEER_MIN_SHARE = 0.01                               # a large company's industry peers outside its index group: 1% of its value or more
# an industry named like a catch-all (SIC "...NEC", "Miscellaneous...", business services): its members are not close peers
BROAD_INDUSTRY = re.compile(r"\bnec\b|not elsewhere classified|business services|miscellaneous|blank check|holding", re.I)
PEER_STALE_DAYS = 7                               # a peer whose last price is older than this (before the newest) is left out


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
    tidy = proper_name if region == "US" else (lambda n: n)
    say = plain_industry if region == "US" else (lambda t: t)          # the SEC's industry titles, worded for a reader (DK-024)
    name = lambda r: str(tidy(r.get("name") or cos[r["symbol"]]["name"] or r["symbol"]))        # noqa: E731
    out: list[dict] = []
    same_ind = [r for r in rows if ind and str(r.get("industry") or "").lower() == ind[-1].lower()]
    large = bool(cap and cap >= LARGE_CAP.get(region, float("inf")))
    if large:
        # a large company's industry is its own size's business, not every filer under the same code (R8V-012: Apple's
        # "Same industry" listed Omnicell, Zepp and Socket Mobile; Visa's, under "business services", Uber, Accenture
        # and DoorDash): an S&P 500 company keeps the S&P 500 members of its own sector, and companies outside the
        # S&P 500 of at least PEER_MIN_SHARE of its value; an Indian company keeps those of that size
        # ...and, when the industry is one of the broad catch-all codes (SIC 7389, "Services-Business Services, NEC", holds
        # Visa and also Alibaba, MercadoLibre, RELX, RB Global and Grab: R10V-007), only the S&P 500's members of its
        # sector count, never a company outside the index; and a company outside the S&P 500 must be of the same kind as
        # this one, a US filer beside a US filer, a foreign filer beside a foreign filer
        sp = _sp500_sectors() if region == "US" else {}
        mine = sp.get(symbol)
        broad = bool(ind) and bool(BROAD_INDUSTRY.search(ind[-1]))
        me = next((r for r in sized if r.get("symbol") == symbol), None) or {}

        def peer(r):
            if mine and r["symbol"] in sp:
                return sp[r["symbol"]] == mine
            if mine and broad:
                return False
            if r.get("foreign") is not None and me.get("foreign") is not None and bool(r["foreign"]) != bool(me["foreign"]):
                return False
            return (_num(r.get("market_cap")) or 0) >= cap * PEER_MIN_SHARE
        same_ind = [r for r in same_ind if peer(r)]
    same_ind = same_ind[:PEERS]
    big = [r for r in same_ind if cap and (_num(r.get("market_cap")) or 0) >= cap / 10]
    coarse: list[dict] = []
    if large and len(big) < 3:
        # the wider sector's list leaves out the companies already listed under the industry, which is the closer list:
        # a company shows once (R10V-007: Dell was under both "Same sector" and "Same industry" on Apple's page)
        have = {r["symbol"] for r in same_ind}
        if region == "US" and symbol in _sp500_sectors():
            where = _sp500_sectors()[symbol]
            coarse = [r for r in rows if _sp500_sectors().get(r["symbol"]) == where and r["symbol"] not in have][:PEERS]
        elif region == "IN" and ind:
            where = ind[0]
            coarse = [r for r in rows if str(r.get("sector") or "").lower() == where.lower() and r["symbol"] not in have][:PEERS]
        if coarse:
            out.append({"title": "Same sector", "rows": [(r["symbol"], name(r)) for r in coarse],
                        "caption": f"The largest companies in the wider sector ({where}), by market value."})
    if same_ind:
        out.append({"title": "Same industry", "rows": [(r["symbol"], name(r)) for r in same_ind],
                    "caption": f"The largest companies in the same industry ({say(ind[-1])}), by market value."})
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
    index_cap = {r["symbol"]: _row_cap(region, r) for r in rows}
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
    """Companies whose symbol or name matches what was typed, best first: the exact symbol, then those whose symbol or
    name starts with it, then those with a word of the name starting with it, then names that contain it; within each
    group the larger company (by checked market value) first, then the rest alphabetically (DK-025: "reli" listed
    RELAXO and RELIABLE before Reliance Industries). A company listed on both exchanges is one result. At most `n` (ask
    for one more to know whether the list was cut)."""
    q = re.sub(r"\s+", " ", (q or "").strip()).upper()[:40]
    if not q:
        return []
    cos = companies(region)
    rows = {r["symbol"]: r for r in _index_rows(region) if r.get("symbol")}
    names = {s: str(r.get("name") or "") for s, r in rows.items()}
    cap = {s: _row_cap(region, r) or 0.0 for s, r in rows.items()}
    name_of = lambda s: (names.get(s) or cos[s].get("name") or "").upper()          # noqa: E731
    hit = find(region, q)
    exact = [hit[0]] if hit else []
    first, word, inside = [], [], []
    for s in cos:
        if s in exact:
            continue
        nm = name_of(s)
        if s.startswith(q) or nm.startswith(q):
            first.append(s)
        elif any(w.startswith(q) for w in re.split(r"[^A-Z0-9&]+", nm) if w):
            word.append(s)
        elif q in nm:
            inside.append(s)
    largest_first = lambda s: (-cap.get(s, 0.0), s)          # noqa: E731
    ordered = exact + sorted(first, key=largest_first) + sorted(word, key=largest_first) + sorted(inside, key=largest_first)
    return [(s, names.get(s) or cos[s]["name"] or s) for s in ordered[:n]]


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


def small_digits(*values) -> int:
    """Decimals for a set of reported amounts shown together: none for amounts in the hundreds and up, two when the
    largest is under 100, so a small company's "2, 2, 2, 2, 3" revenue doesn't sit beside a profit of 0.43 (DK-024)."""
    vals = [abs(x) for x in (_num(v) for v in values) if x is not None]
    return 2 if vals and max(vals) < 100 else 0


def _amount(f: dict, v, digits: int = 0) -> str:
    """A reported figure as _fmt writes it, with Indian digit grouping on an Indian page (₹ crore: 2,67,021, as its
    market cap and the app write it, never 267,021: R10C-007)."""
    text = _fmt(v, digits)
    if (f.get("region") or ("US" if f.get("currency") == "USD" else "IN")) != "IN" or text == "–":
        return text
    sign, rest = (text[0], text[1:]) if text[0] in "-−" else ("", text)
    whole, dot, frac = rest.partition(".")
    return sign + _inr_group(float(whole.replace(",", ""))) + dot + frac


def _pct(v, whole: bool = False) -> str:
    """A percentage; with `whole`, figures the source gives in whole percent show none of the ".0" they don't have. One
    beyond ±NOT_MEANINGFUL is "n/m" (not meaningful): revenue near zero, not a margin (DK-024: Rivian's -7,314.5%)."""
    v = _num(v)
    if v is None:
        return "–"
    if abs(v) > NOT_MEANINGFUL:
        return "n/m"
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


def usd_text(v: float) -> str:
    """An amount in $ million in the words people use: "$4.87T", "$85.8B", "$950M", "<$1M"."""
    if round(v / 1e3, 1) >= 1e3:                         # the unit is chosen after rounding
        return f"${v / 1e6:,.2f}T"
    if round(v) >= 1e3:                                  # $999.5M is "$1.0B", not "$1,000M" (RC4-009)
        return f"${v / 1e3:,.1f}B"
    # $0.5M rounds to "$0M" (TAOP, R6V-011): anything under a whole million is "<$1M"
    return f"${v:,.0f}M" if round(v) >= 1 else "<$1M"


def inr_text(v: float) -> str:
    """An amount in ₹ crore: "₹7.70 lakh crore", "₹20,345 crore", "<₹1 crore"."""
    if round(v) >= 1e5:
        return f"₹{v / 1e5:,.2f} lakh crore"
    return f"₹{_inr_group(v)} crore" if round(v) >= 1 else "<₹1 crore"


def cap_text(f: dict) -> str:
    """Market value in the words people use: "$4.87T", "$85.8B", "$950M", "<$1M"; "₹7.70 lakh crore", "₹20,345 crore".
    "–" when there is none or it failed its checks (cap_problem)."""
    v = shown_cap(f)
    if v is None:
        return "–"
    return usd_text(v) if f.get("currency") == "USD" else inr_text(v)         # stored in $ million, ₹ crore


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


DESCRIPTION_MAX = 160            # a search result shows about this much of a page's description (R10V-005)


def description(f: dict) -> str:
    """The search result's snippet: what the page holds, in facts, in at most DESCRIPTION_MAX characters. The longest
    closing sentence that fits is used; the price range is dropped before the name is cut."""
    head = f"{f['name']} ({f['symbol']})"
    price = ""
    if _num(f.get("price")) is not None:
        word = "last price" if behind(f) or not is_close(f) else "last close"
        price = f"{word} {_money(f, f['price'])}" + (f" on {_date(f['price_at'])}" if f.get("price_at") else "")
    rng = ((f"range since listing {_money(f, f['low52'])} to {_money(f, f['high52'])}" if f.get("range_since")
            else f"1-year range {_money(f, f['low52'])} to {_money(f, f['high52'])}")
           if _num(f.get("low52")) is not None and _num(f.get("high52")) is not None else "")
    tails = (["Price, 1-year range and recent filings, from reported data.", "Price and recent filings."] if f.get("no_numbers")
             else ["Revenue and profit trend, margins, debt, recent filings and the price trend, from reported data.",
                   "Revenue, profit, margins, debt and filings, from reported data.", "Results and filings, from reported data."])
    for bits in ([head, price, rng], [head, price], [head]):
        lead = ", ".join(b for b in bits if b)
        for tail in tails:
            if len(lead) + 2 + len(tail) <= DESCRIPTION_MAX:
                return f"{lead}. {tail}"
    out = f"{head}. {tails[-1]}"
    return out if len(out) <= DESCRIPTION_MAX else out[:DESCRIPTION_MAX - 1].rstrip() + "…"


# the site's own look (frontend/src/styles.css): paper and ink, one blue, Fraunces headings and IBM Plex text. The fonts
# are the site's own files (the frontend build copies them to /fonts), so a slow or missing font only falls back
STYLE = """
@font-face{font-family:"Fraunces";font-style:normal;font-weight:400;font-display:optional;src:url(/fonts/fraunces-latin-400-normal.woff2) format("woff2")}
@font-face{font-family:"Fraunces";font-style:normal;font-weight:600;font-display:optional;src:url(/fonts/fraunces-latin-600-normal.woff2) format("woff2")}
@font-face{font-family:"IBM Plex Sans";font-style:normal;font-weight:400;font-display:optional;src:url(/fonts/ibm-plex-sans-latin-400-normal.woff2) format("woff2")}
@font-face{font-family:"IBM Plex Sans";font-style:normal;font-weight:500;font-display:optional;src:url(/fonts/ibm-plex-sans-latin-500-normal.woff2) format("woff2")}
@font-face{font-family:"IBM Plex Sans";font-style:normal;font-weight:600;font-display:optional;src:url(/fonts/ibm-plex-sans-latin-600-normal.woff2) format("woff2")}
@font-face{font-family:"Montserrat";font-style:normal;font-weight:300;font-display:optional;src:url(/fonts/montserrat-latin-300-normal.woff2) format("woff2")}
@font-face{font-family:"Montserrat";font-style:normal;font-weight:800;font-display:optional;src:url(/fonts/montserrat-latin-800-normal.woff2) format("woff2")}
:root{--paper:#F5F1E8;--card:#FFFDF8;--ink:#1D1B17;--ink-2:#2E2B25;--muted:#5C574D;--line:#E2DAC8;--line-2:#D8CFBA;--chip:#ECE6D8;
--blue:#1F4FB5;--blue-ink:#163A87;--on-ink:#F5F1E8;--orange:#B4500F;--orange-ink:#8A3A0A;--orange-soft:#F8E7D9;--up:#0F7452;--down:#B23B3B;color-scheme:light;
--serif:"Fraunces",Georgia,serif;--sans:"IBM Plex Sans",system-ui,-apple-system,"Segoe UI",sans-serif;--mono:"IBM Plex Mono",ui-monospace,"SF Mono",Menlo,monospace}
@media (prefers-color-scheme:dark){:root{--paper:#141311;--card:#1F1D1A;--ink:#EFE9DC;--ink-2:#D8D1C2;--muted:#B3AC9C;--line:#34312A;
--line-2:#413D34;--chip:#2A2823;--blue:#7EA0F0;--blue-ink:#A9C0F6;--on-ink:#141311;--orange:#E88A4C;--orange-ink:#F2A877;--orange-soft:#3A2416;--up:#3CC48F;--down:#EE7B70;color-scheme:dark}}
*{box-sizing:border-box}html,body{margin:0}
body{background:var(--paper);color:var(--ink);font:15px/1.55 var(--sans);-webkit-font-smoothing:antialiased;font-variant-numeric:tabular-nums;display:flex;flex-direction:column;min-height:100vh}
a{color:var(--blue)}a:hover{color:var(--blue-ink)}:focus-visible{outline:2px solid var(--blue);outline-offset:2px}
main:focus,[data-ads]:focus{outline:none}
.skip{position:absolute;left:-9999px;padding:12px 16px}.skip:focus{left:16px;top:8px;z-index:2;background:var(--card);border-radius:10px}
.nav{display:flex;align-items:center;padding:18px max(clamp(16px,4vw,48px),calc((100% - 960px)/2 + clamp(16px,4vw,32px)));border-bottom:1px solid var(--line)}
.brand{display:inline-flex;align-items:center;gap:8px;text-decoration:none;color:var(--ink);min-height:44px;font-size:16.8px}
.brand svg{height:40px;width:auto}.word{font-family:"Montserrat",var(--sans);font-weight:300;letter-spacing:-.035em}.word b{font-weight:800;letter-spacing:-.045em}
.nav nav{display:flex;gap:22px;margin-left:auto;margin-right:16px}.nav nav a{display:inline-flex;align-items:center;min-height:36px;color:var(--ink-2);text-decoration:none;font-weight:500;font-size:14.5px}
.nav nav a:hover{color:var(--ink)}
.btn{display:inline-flex;align-items:center;justify-content:center;min-height:44px;padding:10px 18px;border-radius:10px;border:1px solid var(--ink);
background:var(--ink);color:var(--on-ink);text-decoration:none;font-weight:600;font-size:15px}.btn:hover{color:var(--on-ink);filter:brightness(1.12)}
.btn.ghost{background:transparent;color:var(--ink)}.btn.ghost:hover{background:var(--card);color:var(--ink);filter:none}
.btn.sm{min-height:36px;padding:0 12px;font-size:14px}
main{flex:1 0 auto;width:100%;max-width:960px;margin:0 auto;padding:36px clamp(16px,4vw,32px) 64px}
h1{font-family:var(--serif);font-weight:400;font-size:clamp(32px,4vw,46px);line-height:1.1;letter-spacing:-.02em;margin:4px 0 8px;text-wrap:balance}
h2{font-family:var(--serif);font-weight:600;font-size:22px;line-height:1.25;letter-spacing:-.01em;margin:40px 0 12px;text-wrap:balance}h3{font-size:16px;font-weight:600;margin:14px 0 4px}
main>p{max-width:72ch}.faq p{margin:0 0 6px;color:var(--ink-2)}.muted{color:var(--muted)}.small{font-size:14px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px 20px;margin:12px 0}
.sub{margin:0 0 14px;font-size:15px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}h1>.muted{font-size:.5em;font-weight:400;white-space:nowrap}
.px{margin:0 0 6px}.px p{margin:0}.px-line{display:flex;flex-wrap:wrap;align-items:baseline;gap:2px 14px}.px-line b{font-size:clamp(34px,5vw,44px);line-height:1.1;font-weight:600;letter-spacing:-.01em}
.px-chg{font-size:18px;font-weight:600}.px-chg[data-dir=up]{color:var(--up)}.px-chg[data-dir=down]{color:var(--down)}.px-chg[hidden]{display:none}
/* the key figures: even tiles, four across (three when that leaves fewer empty places, two on a phone); a tile is its label, its value and a small line for its unit or period, and the values of a row
   share one baseline whatever their labels' length (PUB-2: labels wrapping to one, two and three lines left the values at different heights) */
.figs{padding:18px 20px 6px}.tiles{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:0 24px}.tiles.c3{grid-template-columns:repeat(3,minmax(0,1fr))}.tiles.c2{grid-template-columns:repeat(2,minmax(0,1fr))}
.stat{min-width:0;margin:0 0 14px;padding-top:10px;border-top:1px solid var(--line)}.stat span{display:block;font-size:13.5px;line-height:1.35;color:var(--muted)}
.stat b{display:block;font-size:22px;line-height:1.25;font-weight:600;white-space:nowrap}.stat.long b{font-size:18px;line-height:1.5}.stat.fill2{grid-column:span 2}.stat.fill3{grid-column:span 3}.stat small{display:block;font-size:12.5px;line-height:1.35;color:var(--muted)}
@supports (grid-template-rows:subgrid){.stat{display:grid;grid-row:span 3;grid-template-rows:subgrid;gap:0 0;align-content:start}.stat span{align-self:end}}
.range{padding-bottom:14px;margin-bottom:4px}.range-name{margin:0 0 2px;font-size:13.5px;color:var(--muted)}.rbar{display:block;overflow:visible;padding:0 6px;box-sizing:border-box;font-family:var(--sans);max-width:100%}
.rb-track{stroke:var(--line-2);stroke-width:6;stroke-linecap:round}.rb-dot{fill:var(--blue);stroke:var(--card);stroke-width:2}.rb-now{fill:var(--ink-2);font-size:13px;font-weight:600}
.range-ends{display:flex;justify-content:space-between;gap:12px;margin:0;font-size:15px}.range-ends small{font-size:12.5px;color:var(--muted)}.range-ends b{font-weight:600}
.note{border-left:3px solid var(--line-2);padding:4px 0 4px 12px;margin:10px 0;font-size:14px;color:var(--ink-2);max-width:72ch}
.note.warn{border-color:var(--orange-ink);background:var(--orange-soft);padding:8px 12px;border-radius:0 10px 10px 0}
details.how summary{cursor:pointer;min-height:44px;display:flex;align-items:center;gap:10px;font-weight:600;list-style:none}details.how li{margin:6px 0}
details.how summary::-webkit-details-marker{display:none}
details.how summary::before{content:"";flex:none;width:9px;height:9px;border-right:2px solid var(--blue);border-bottom:2px solid var(--blue);transform:rotate(-45deg);transition:transform .15s}
details.how[open] summary::before{transform:rotate(45deg)}
details.how summary::after{content:"Show";margin-left:auto;color:var(--blue);font-weight:400;font-size:14px}
details.how[open] summary::after{content:"Hide"}
details.how summary:hover{color:var(--blue-ink)}details.how summary:focus-visible{outline:2px solid var(--blue);outline-offset:2px;border-radius:8px}
.tbl{overflow-x:auto;direction:rtl;scroll-snap-type:x proximity;scroll-padding-left:124px}.tbl table{direction:ltr}
.tbl th:not(:first-child),.tbl td:not(:first-child){scroll-snap-align:end}
table{border-collapse:collapse;width:100%;font-size:15px}th,td{text-align:right;padding:9px 8px;border-bottom:1px solid var(--line);white-space:nowrap}
th{font-weight:600;color:var(--ink-2)}
th:first-child,td:first-child{text-align:left;position:sticky;left:0;background:var(--card);box-sizing:border-box;min-width:124px}
.scroll-cue{display:none;font-size:13px;color:var(--muted);margin:0 0 6px}
/* on a phone the years are cut to whole columns beside the label column: three at a time where the card is wide enough for them, else two,
   whatever the phone's width, so no year is cut by the edge or by the label column laid over it (VR4-009: "24", "35" and "88" showed
   where "Mar 2024" slid under the labels) */
@media (max-width:640px){.tbl.fin{container-type:inline-size;scroll-padding-left:110px}.fin table{font-size:13px}.fin th,.fin td{padding:9px 4px}
.fin th:first-child,.fin td:first-child{min-width:110px;width:110px}
.fin th:not(:first-child),.fin td:not(:first-child){min-width:calc((100cqw - 110px) / 2);width:calc((100cqw - 110px) / 2)}
@container (min-width:340px){.fin th:not(:first-child),.fin td:not(:first-child){min-width:calc((100cqw - 110px) / 3);width:calc((100cqw - 110px) / 3)}}}
.nav details.menu{display:none;position:relative;margin-left:auto;margin-right:12px}
.nav details.menu summary{display:inline-flex;align-items:center;min-height:44px;padding:0 14px;border:1px solid var(--line-2);border-radius:10px;font-weight:600;color:var(--ink);cursor:pointer;list-style:none}
.nav details.menu summary::-webkit-details-marker{display:none}
.nav details.menu nav{display:flex;flex-direction:column;gap:0;margin:0;position:absolute;right:0;top:calc(100% + 8px);z-index:30;min-width:190px;padding:6px;background:var(--card);border:1px solid var(--line-2);border-radius:12px;box-shadow:0 12px 32px rgba(29,27,23,.14)}
.nav details.menu nav a{display:flex;align-items:center;min-height:44px;padding:0 12px;border-radius:8px;color:var(--ink)}.nav details.menu nav a:hover{background:var(--chip)}
@media (max-width:1000px){.nav>nav{display:none}.nav details.menu{display:block}}
@media (max-width:640px){.nav{justify-content:space-between}.nav .btn.sm{min-height:44px}.scroll-cue{display:block}}

.card>h2:first-child{margin-top:0}.surv{margin:2px 0}.surv summary{cursor:pointer;min-height:44px;display:flex;align-items:center;flex-wrap:wrap;gap:2px 10px}.surv p{margin:0 0 8px}
.badge{display:inline-block;border:1px solid var(--orange-ink);color:var(--orange-ink);background:var(--orange-soft);border-radius:999px;padding:2px 10px;font-size:13px;font-weight:600}
ul.plain{list-style:none;padding:0;margin:0}ul.plain li{padding:10px 0;border-bottom:1px solid var(--line)}ul.plain li:last-child{border-bottom:0}
.ctas{display:flex;flex-wrap:wrap;gap:10px;margin-top:12px}
ul.dir{list-style:none;padding:0;margin:16px 0;display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,290px),1fr));gap:8px}
ul.dir li{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:0 14px;background:var(--card);border:1px solid var(--line);border-radius:12px}
ul.dir li:hover{border-color:var(--line-2)}ul.dir a{display:flex;align-items:center;flex:1;min-width:0;min-height:48px;line-height:1.3;color:var(--ink);text-decoration:none}
ul.dir a:hover{color:var(--blue)}ul.dir .muted{flex:none;font-size:13px}nav.links{margin:12px 0 6px}
.links{display:flex;flex-wrap:wrap;gap:8px}.links a{display:inline-flex;align-items:center;min-height:40px;padding:4px 14px;border:1px solid var(--line);border-radius:999px;text-decoration:none;background:var(--card);color:var(--ink-2)}
.links a:hover{border-color:var(--line-2);color:var(--ink)}nav.links[data-az] a{min-width:44px;min-height:44px;justify-content:center;padding:4px 10px}
/* VR6-022: A to Z in two rows of thirteen on a wide screen, not nineteen and an orphan row of seven (44 px taps, A11Y-2) */
@media (min-width:641px){nav.links[data-az]{display:grid;grid-template-columns:repeat(13,44px)}}
/* VR7-003: on a phone the same letters fill the row (a 44 px box each, the row as wide as the screen) in as many columns as leave the last row nearly
   full (data-c7 for a screen 375px and wider, data-c6 for a narrower one), not a last row of one or two letters */
nav.links[data-c7="1"]{--az7:1}nav.links[data-c7="2"]{--az7:2}nav.links[data-c7="3"]{--az7:3}nav.links[data-c7="4"]{--az7:4}nav.links[data-c7="5"]{--az7:5}nav.links[data-c7="6"]{--az7:6}nav.links[data-c7="7"]{--az7:7}
nav.links[data-c6="1"]{--az6:1}nav.links[data-c6="2"]{--az6:2}nav.links[data-c6="3"]{--az6:3}nav.links[data-c6="4"]{--az6:4}nav.links[data-c6="5"]{--az6:5}nav.links[data-c6="6"]{--az6:6}
@media (max-width:640px){nav.links[data-az]{display:grid;grid-template-columns:repeat(var(--az7,7),minmax(0,1fr))}nav.links[data-az] a{min-width:0;padding:4px 0}}
@media (max-width:374px){nav.links[data-az]{grid-template-columns:repeat(var(--az6,6),minmax(0,1fr))}}
.links a[aria-current=page]{background:var(--ink);border-color:var(--ink);color:var(--on-ink)}
[data-crumbs]{margin:0 0 6px}[data-crumbs] a{color:var(--muted)}h1+.muted{font-size:16px;max-width:64ch;margin:0 0 14px}
form.find{display:flex;gap:8px;flex-wrap:nowrap;margin:16px 0}form.find select,form.find button{flex:none}form.find input,form.find select{min-height:44px;border:1px solid var(--line-2);border-radius:10px;padding:0 12px;background:var(--card);color:var(--ink);font:inherit}
form.find input{flex:1;min-width:0}form.find button{cursor:pointer;font:inherit}
footer.site{border-top:1px solid var(--line);margin-top:24px}footer.site .in{max-width:960px;margin:0 auto;padding:24px clamp(16px,4vw,32px) 40px;font-size:13.5px;color:var(--muted)}
footer.site p{max-width:72ch;margin:0 0 8px}footer.site nav{display:flex;flex-wrap:wrap;gap:4px 18px}footer.site nav a{color:var(--muted);display:inline-block;padding:8px 0}footer.site nav a:hover{color:var(--ink)}
/* VR6-027: the line under the name wraps on a phone. VR6-003: no forced full row for a long tile: the merge of PUB-2 kept the older rule here
   (.grid, .stat.long{grid-column:1/-1}), so a market cap took a row of its own beside tiles that are two to a row, and the last-child rule below
   then stranded the tile before it; the long tile is half a row at 17px, as PUB-2 drew it */
@media (max-width:640px){.sub{white-space:normal;overflow:visible}}
@media (max-width:640px){ul.dir[data-short]{grid-template-columns:repeat(2,minmax(0,1fr))}ul.dir[data-short] li{padding:0 12px}}
/* VR5-008: the two buttons of "Go further" were 246px and 206px wide, left-aligned: one width on a phone */
@media (max-width:640px){.ctas{flex-direction:column}.ctas .btn{justify-content:center;text-align:center}}
@media (max-width:640px){.tiles,.tiles.c3,.tiles.c4{grid-template-columns:repeat(2,minmax(0,1fr));gap:0 16px}.tiles>.stat:last-child:nth-child(odd){grid-column:1/-1}.stat.fill2,.stat.fill3{grid-column:auto}.stat.long b{font-size:17px}.stat b{font-size:20px}.figs{padding:16px 16px 4px}.card{padding:16px}h2{margin-top:32px}}
@media (max-width:640px){footer.site nav a{padding:12px 0;min-height:44px;min-width:44px}.links a{min-height:44px}ul.dir a{min-height:48px}a[href^="mailto:"]{display:inline-block;padding:12px 0;min-height:44px}}
.sr-only{position:absolute;width:1px;height:1px;margin:-1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
@media (prefers-reduced-motion:reduce){*,*::before,*::after{transition:none!important;animation:none!important;scroll-behavior:auto!important}}
.chart-top{display:flex;flex-wrap:wrap;align-items:flex-end;justify-content:space-between;gap:10px 16px;margin-bottom:6px;min-height:52px}
.chg{margin:0}.chg b{font-size:22px;font-weight:600;font-variant-numeric:tabular-nums}.chg b[data-dir=up]{color:var(--up)}.chg b[data-dir=down]{color:var(--down)}.chg .small{display:block;max-width:46ch}
.seg{display:inline-flex;gap:2px;padding:3px;border-radius:12px;background:var(--chip)}.seg[hidden],.seg button[hidden]{display:none}
.seg button{font:inherit;font-weight:600;font-size:14px;min-width:48px;min-height:40px;padding:0 10px;border:0;border-radius:9px;background:transparent;color:var(--ink-2);cursor:pointer}
.seg button:hover:not(:disabled){color:var(--ink)}.seg button[aria-pressed=true]{background:var(--card);color:var(--ink);box-shadow:0 0 0 1px var(--line-2)}
.seg button:disabled{opacity:.4;cursor:default}.seg button:focus-visible{outline:2px solid var(--blue);outline-offset:1px}
.plot{position:relative;height:280px}[data-empty] .plot{height:96px}.plot svg{display:block;overflow:visible;max-width:100%;user-select:none;-webkit-user-select:none;-webkit-tap-highlight-color:transparent;font-family:var(--sans);font-variant-numeric:tabular-nums}
.plot svg:focus{outline:none}.plot svg:focus-visible{outline:2px solid var(--blue);outline-offset:2px;border-radius:6px}
.plot-note{position:absolute;inset:0;display:flex;flex-wrap:wrap;gap:8px;align-items:center;justify-content:center;text-align:center;margin:0;padding:0 16px}.plot-note[hidden]{display:none}
.tip{position:absolute;z-index:3;pointer-events:none;display:flex;flex-direction:column;gap:2px;min-width:128px;background:var(--card);border:1px solid var(--line-2);border-radius:8px;padding:7px 10px;font-size:14px;box-shadow:0 8px 24px rgba(29,27,23,.14)}
.tip[hidden]{display:none}.tip span{color:var(--muted);font-size:12.5px;white-space:nowrap}.tip b{font-weight:600}
.chart [data-summary]{margin:10px 0 0;max-width:72ch}.chart .how{margin-top:4px}.tbl2{overflow-x:auto}.tbl2 td:last-child,.tbl2 th:last-child{text-align:right}
@media (max-width:640px){.plot{height:210px}.seg button{min-height:44px;min-width:52px}.chg b{font-size:20px}.chart-top{min-height:0}}
.by{margin:0 0 6px}.by-key{display:flex;flex-wrap:wrap;gap:4px 18px;font-size:13px;color:var(--ink-2);margin-bottom:26px}
.by-key .sw{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:7px}.sw.rev,.by-bar.rev{background:var(--blue)}.sw.pro,.by-bar.pro{background:var(--orange)}
.by-plot{position:relative;height:180px;margin:0 0 30px 56px}.by-line{position:absolute;left:0;right:0;height:0;border-top:1px solid var(--line)}
.by-tick{position:absolute;right:calc(100% + 8px);transform:translateY(50%);font-size:12px;line-height:1;color:var(--muted);white-space:nowrap;font-variant-numeric:tabular-nums}
.by-cols{position:absolute;inset:0;display:flex}.by-col{position:relative;flex:1;min-width:0;border-radius:6px;outline-offset:-2px}.by-col:focus-visible{outline:2px solid var(--blue)}
.by-bar{position:absolute;width:min(20px,40%);border-radius:4px 4px 0 0;transition:opacity .12s}.by-bar.neg{border-radius:0 0 4px 4px}
.by-bar.rev{left:calc(50% - min(21px,41%))}.by-bar.pro{left:calc(50% + 1px)}
.by-cols:hover .by-col:not(:hover) .by-bar{opacity:.45}
.by-x{position:absolute;top:calc(100% + 8px);left:0;right:0;text-align:center;font-size:12px;color:var(--muted);white-space:nowrap}
.by-tip{display:none;position:absolute;z-index:3;left:50%;bottom:100%;transform:translateX(-50%);flex-direction:column;gap:2px;min-width:150px;margin-bottom:4px;background:var(--card);border:1px solid var(--line-2);border-radius:8px;padding:7px 10px;font-size:13px;box-shadow:0 8px 24px rgba(29,27,23,.14);pointer-events:none;white-space:nowrap}
.by-col:first-child .by-tip{left:0;transform:none}.by-col:last-child .by-tip{left:auto;right:0;transform:none}
.by-col:hover .by-tip,.by-col:focus .by-tip{display:flex}.by-tip .k{color:var(--muted);font-size:12px;margin-top:2px}
@media (max-width:640px){.by-plot{margin-left:50px;height:160px}}
@media (max-width:640px){input,select,textarea,form.find input,form.find select{font-size:16px}}
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


def _head(title: str, desc: str, canonical: str, extra: str = "", robots: str = "index,follow", og_type: str = "website") -> str:
    # a page kept out of search results names no canonical address: it would point a search engine at a page it was told
    # not to list (R10V-005: the 404 for a company that doesn't exist said its canonical address was /stocks)
    site = settings.PUBLIC_SITE_URL
    indexed = not robots.startswith("noindex")
    link = f'<link rel="canonical" href="{e(canonical)}">\n' if indexed else ""
    og_url = f'<meta property="og:url" content="{e(canonical)}">' if indexed else ""
    # the heading's and the text's fonts asked for first, so they are in before the first paint where they can be, not
    # swapped in after it, moving the list and the search under a heading that rewraps (R75-002: /stocks' layout shift)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="google-adsense-account" content="ca-pub-8125241692814953">
<link rel="preload" href="/fonts/fraunces-latin-400-normal.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="/fonts/ibm-plex-sans-latin-400-normal.woff2" as="font" type="font/woff2" crossorigin>
<title>{e(title)}</title>
<meta name="description" content="{e(desc)}">
<meta name="robots" content="{robots}">
{link}<link rel="icon" href="{site}/favicon.svg" type="image/svg+xml">
<meta name="theme-color" content="#F5F1E8" media="(prefers-color-scheme: light)"><meta name="theme-color" content="#141311" media="(prefers-color-scheme: dark)">
<meta property="og:type" content="{og_type}"><meta property="og:site_name" content="StratLab">
<meta property="og:title" content="{e(title)}"><meta property="og:description" content="{e(desc)}">
{og_url}<meta property="og:image" content="{site}/og-image.png">
<meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="{e(title)}"><meta name="twitter:description" content="{e(desc)}"><meta name="twitter:image" content="{site}/og-image.png">
{extra}<style>{STYLE}</style></head>"""


def _ld(obj) -> str:
    """JSON-LD for search engines; "<" is written as \\u003c so no value can open or close a tag inside it."""
    return '<script type="application/ld+json">' + json.dumps(obj, ensure_ascii=False).replace("<", "\\u003c") + "</script>"


def _links(region: str, rows: list[tuple[str, str]]) -> str:
    # US names come from filings in capitals ("COSTCO WHOLESALE CORP /NEW"); Indian ones are kept as listed ("ITC Ltd",
    # whose acronyms title case would spoil)
    tidy = proper_name if region.lower() == "us" else (lambda n: n)
    return '<div class="links">' + "".join(f'<a href="{e(path(region, s))}">{e(n if n == s else f"{tidy(n)} ({s})")}</a>' for s, n in rows) + "</div>"


def _top(sign_in: str | None = None) -> str:
    """The site's header: the logo home, the landing page's sections, company search, and Sign in. Sign in opens the
    app's own address for what the visitor is looking at (a company's page in the app), whose "Sign in to see …" screen
    signs in with Google and comes back to it."""
    site = settings.PUBLIC_SITE_URL
    sign_in = sign_in or f"{site}/mine"
    # the landing page's own sections, in its order, then company search (R43B-007: the two menus differed)
    links = "".join(f'<a href="{site}/#{k}">{v}</a>' for k, v in (("trade", "Trade"), ("invest", "Invest"), ("money", "Money"), ("alerts", "Alerts")))
    # the strategy library beside Companies, as on the landing page and the other public pages (DK-008)
    menu = f'{links}<a href="{site}/pricing">Plans</a><a href="{site}/#faq">FAQ</a><a href="{site}/library">Library</a><a href="/stocks">Companies</a><a href="/blog">Blog</a>'
    return (f'<a class="skip" href="#main">Skip to main content</a><header class="nav"><a class="brand" href="{site}/" aria-label="StratLab home">'
            f'{LOGO}<span class="word"><b>Strat</b>Lab</span></a><nav aria-label="Site">{menu}</nav>'
            f'<details class="menu"><summary>Menu</summary><nav aria-label="Site (menu)">{menu}</nav></details>'
            f'<a class="btn ghost sm" href="{e(sign_in)}">Sign in</a></header>')


INSTAGRAM = "https://www.instagram.com/stratlab.studio/"      # the same address as the app's footers (content/seo.ts)


def _foot() -> str:
    site = settings.PUBLIC_SITE_URL
    explore = "".join(f'<a href="{site}{p}">{t}</a>' for p, t in (("/library", "Strategy library"), ("/stocks", "Companies"), ("/blog", "Blog"), ("/pricing", "Plans")))
    policies = "".join(f'<a href="{site}{p}">{t}</a>' for p, t in (("/terms", "Terms of service"), ("/privacy", "Privacy policy"),
                                                                   ("/refunds", "Cancellation and refunds"), ("/contact", "Contact us")))
    policies += f'<a href="{INSTAGRAM}" rel="me noopener">Instagram</a>'
    return (f'<footer class="site"><div class="in"><p>Research and paper trading only. No real orders are placed. StratLab shows '
            "facts from reported data for research and education; nothing here is investment advice or a recommendation, and "
            f"past prices don't predict future returns. © {datetime.now(timezone.utc).year} StratLab.</p>"
            f'<nav aria-label="Explore">{explore}</nav><nav aria-label="Policies">{policies}</nav></div></footer>')


def _page(head: str, sign_in: str | None, body: str) -> str:
    return head + "<body>" + _top(sign_in) + f'<main id="main">{body}</main>' + _foot() + "</body></html>"


def _find_form(region: str | None, q: str = "") -> str:
    r = (region or "IN").lower()
    opts = "".join(f'<option value="{k}"{" selected" if k == r else ""}>{v}</option>' for k, v in (("in", "India"), ("us", "US")))
    return (f'<form class="find" action="/stocks" method="get" role="search"><label class="skip" for="q">Company name or symbol</label>'
            f'<input id="q" name="q" value="{e(q[:40])}" placeholder="Company or symbol" autocomplete="off">'
            f'<label class="skip" for="m">Market</label><select id="m" name="m">{opts}</select>'
            '<button class="btn" type="submit">Find</button></form>')


_KEEP_UPPER = {"IBM", "AMD", "AIG", "UPS", "PNC", "PPG", "ICE", "CME", "USA", "US", "UK", "LLC", "LP", "NV", "SA", "AG", "SE", "ETF",
               "REIT", "ADR", "II", "III", "IV", "NVIDIA", "ASML", "HSBC", "UBS", "BHP", "SAP", "TSMC", "KLA", "CSX", "AT&T"}
# words title case gets wrong, as the companies write them
_SPELLED = {"JPMORGAN": "JPMorgan", "PAYPAL": "PayPal", "MCDONALDS": "McDonalds", "EBAY": "eBay", "BLACKROCK": "BlackRock",
            "FEDEX": "FedEx", "MASTERCARD": "Mastercard", "SALESFORCE": "Salesforce", "SERVICENOW": "ServiceNow",
            # brands written in mixed case (R80-016: "Conocophillips")
            "CONOCOPHILLIPS": "ConocoPhillips", "PEPSICO": "PepsiCo", "ABBVIE": "AbbVie", "NVIDIA": "NVIDIA", "AUTOZONE": "AutoZone",
            "MCKESSON": "McKesson", "MCCORMICK": "McCormick", "DOORDASH": "DoorDash", "CROWDSTRIKE": "CrowdStrike",
            "MONGODB": "MongoDB", "DUPONT": "DuPont", "GODADDY": "GoDaddy", "HUBSPOT": "HubSpot", "DEXCOM": "DexCom",
            "NETAPP": "NetApp", "ONEOK": "ONEOK", "IDEXX": "IDEXX", "BIOGEN": "Biogen"}


def proper_name(name: str | None) -> str | None:
    """A company name that arrives in capitals from a filing ("MICROSOFT CORP") in title case ("Microsoft Corp"); acronyms
    (IBM, AT&T, a short run of consonants like CVS) and a name that already has lower case are left as they are; a filing's
    state suffix ("APPLIED MATERIALS INC /DE", "REALTY /MD/") or a re-registration mark ("COSTCO WHOLESALE CORP /NEW") is
    dropped. A capitals name with a mixed-case ending ("ELI LILLY & Co") counts as capitals."""
    if name:
        name = strip_registration(name) or name
    core = re.sub(r"\s+(?:Co|Inc|Corp|Ltd)\.?$", "", name or "")
    if not name or core != core.upper() or not re.search(r"[A-Z]{2}", core):
        return name

    def word(w: str) -> str:
        core = re.sub(r"[^A-Za-z&]", "", w)
        if core in _SPELLED:
            return w.replace(core, _SPELLED[core])
        if core in ("LTD", "CO", "INC", "CORP"):
            return w[:1] + w[1:].lower()
        if core in _KEEP_UPPER or (len(core) <= 4 and not re.search(r"[AEIOUY]", core)) or re.search(r"[A-Za-z]&[A-Za-z]", w):
            return w
        return "-".join(x[:1] + x[1:].lower() for x in w.split("-"))
    return re.sub(r"\bAmazon Com\b", "Amazon.com", " ".join(word(w) for w in name.split(" ")))


# ---------- a company's own words: one short paragraph and the questions its page can answer (SEO-1) ----------
# Every company page had the same sentences round different numbers, which Google calls thin. These are sentences built from the
# page's own figures (nothing new is fetched or made up), worded as facts: no buy, sell, hold or target (SEBI's research analyst
# rules), no data vendor's name.
ADVICE_WORDS = re.compile(r"\b(buy|sell|hold|accumulate|avoid|target|undervalued|overvalued|recommend\w*|outperform\w*|upgrade\w*|downgrade\w*)\b", re.I)
FAQ_HOLDERS = 3                  # named holders the shareholders answer lists


def report_amount(f: dict, v, digits: int = 0) -> str | None:
    """A reported figure in the unit the page's table uses, in words: "₹2,67,021 crore", "$391.0B"; a foreign filer's own
    currency as "12,345 EUR million". None without a figure. `digits` 2 is the precision the page's table or key figures use
    for a small company's amounts (small_digits): "₹0.31 crore", "$12.34M", as shown there, never "<₹1 crore" beside a 0.31
    (RC4-002: 50 of 410 sampled Indian pages said "net profit of <₹1 crore" and "revenue of ₹41 crore" for 41.37)."""
    v = _num(v)
    if v is None:
        return None
    unit = f.get("unit") or ""
    if digits >= 2 and unit in ("$ million", "₹ crore") and abs(v) < 100:
        sign = "-" if v < 0 else ""
        n = _fmt(abs(v), 2)
        return f"{sign}${n}M" if unit == "$ million" else f"{sign}₹{n} crore"
    if unit == "$ million":
        return usd_text(v)
    if unit == "₹ crore":
        return inr_text(v)
    return f"{_amount(f, v)} {unit}".strip()


def listed_on(f: dict, region: str, symbol: str) -> str:
    """"on NSE and BSE", "on BSE", "in the US": where the company's shares are listed, as far as the app knows."""
    if region == "US":
        return "in the US"
    ex = str(f.get("exchange") or "NSE")
    return "on NSE and BSE" if ex == "NSE" and symbol in set(nse_twins().values()) else f"on {ex}"


def about_text(f: dict, region: str, symbol: str, name: str) -> str:
    """The sentences of about_parts as one paragraph (the text the checks of SEO-1 read)."""
    return " ".join(about_parts(f, region, symbol, name))


def about_parts(f: dict, region: str, symbol: str, name: str) -> list[str]:
    """The company's own sentences, one to an item, from the company's own figures: its sector, where it is listed, its year's range and last close, the
    latest reported year's revenue and profit, the last 12 months' profit and its market value. Each sentence is left out when
    its figures are n/a on the page (the same checks the page's figures pass)."""
    out = []
    ind = shown_industry(f.get("industry"), plain=region == "US")
    where = ""
    if region == "IN" and ind:
        where = f"is in the {ind[0]} sector" + (f", in the {ind[-1]} industry," if len(ind) > 1 and ind[-1] != ind[0] else ",")
    elif ind:
        where = f"is in the {ind[-1]} industry,"
    out.append(f"{name} {where} listed {listed_on(f, region, symbol)}.".replace(" ,", ",") if where else f"{name} is listed {listed_on(f, region, symbol)}.")
    price = _num(f.get("price"))
    if price is not None:
        word = "last price" if behind(f) or not is_close(f) else "last close"
        when = f" on {_date(f['price_at'])}" if _date(f.get("price_at")) else ""
        bit = f"Its {word} was {_money(f, price)}{when}"
        if _num(f.get("low52")) is not None and _num(f.get("high52")) is not None:
            span = (f"since its listing on {_date(f['range_since'])}" if f.get("range_since") and _date(f.get("range_since"))
                    else "over the last 12 months")
            bit += f"; {span} its share price traded between {_money(f, f['low52'])} and {_money(f, f['high52'])} (intraday)"
        out.append(bit + ".")
    ys = [y for y in f.get("years") or [] if y.get("year")]
    if ys:
        y = ys[-1]
        # the precision the page's own table uses for these years (see _table), so a small company's figure reads as there
        dy = small_digits(*[x.get(k) for x in f.get("years") or [] for k in (("sales", "profit") if f.get("bank") else ("sales", "profit", "debt"))])
        sales, profit = report_amount(f, y.get("sales"), dy), _num(y.get("profit"))
        bits = []
        if sales and _num(y.get("sales")) is not None and _num(y["sales"]) > 0:
            bits.append(f"revenue of {sales}")
        if profit is not None:
            bits.append(f"a net loss of {report_amount(f, -profit, dy)}" if profit < 0 else f"net profit of {report_amount(f, profit, dy)}")
        if bits:
            g = f.get("growth") or {}
            grow = [w for w in (growth_words("revenue", g.get("sales_cagr_3y")), growth_words("net profit", g.get("profit_cagr_3y"))) if w]
            out.append(f"In its latest reported year ({y['year']}) it reported " + " and ".join(bits)
                       + (f"; over three years, compounded, its {', and its '.join(grow)}" if grow else "") + ".")
    ttm, owners = _num(f.get("profit_ttm")), owners_profit(f)
    dt = small_digits(ttm, owners)              # as the key figures show them (_stats)
    if owners is not None or ttm is not None:
        # the page's own two lines for an Indian company whose table profit includes minority holders (_stats): the shareholders'
        if owners is not None:
            text = f"profit to its shareholders over the last 12 months was {report_amount(f, owners, dt)}"
        else:
            text = (f"it made a net loss of {report_amount(f, -ttm, dt)} over the last 12 months" if ttm < 0
                    else f"its net profit over the last 12 months was {report_amount(f, ttm, dt)}")
        out.append(text[0].upper() + text[1:] + " (the four latest reported quarters).")
    if cap_text(f) != "–":
        pe = shown_pe(f)
        out.append(f"Its market value is {cap_text(f)}" + (f", with a P/E of {_fmt(pe)}" if pe is not None else "") + ".")
    return out


def faq_extras(region: str, symbol: str) -> dict:
    """What the company's page can say that is stored apart from its facts, read without asking any source: its next results
    date (the results calendar) and the named holders above 1% in its latest shareholding pattern (India). Empty parts when
    nothing is stored."""
    got: dict = {}
    try:
        from . import results
        cal = results.load(region)
        nxt = results.lookup(region, symbol)["next"] if cal["rows"] else None
        if nxt:
            got["results"] = {"date": nxt["date"], "when": nxt.get("when"), "purpose": nxt.get("purpose"), "as_of": str(cal.get("at") or "")[:10]}
    except Exception as ex:                      # the calendar unreadable: no such question
        print("stock pages: results date not read:", symbol, str(ex)[:120])
    if region == "IN":
        try:
            from . import shareholders
            view = shareholders.company_view(symbol)
            if view and view.get("holders"):
                top = sorted(view["holders"], key=lambda h: -h["pct"])[:FAQ_HOLDERS]
                got["holders"] = {"quarter": view["quarter"], "holders": [{"name": h["name"], "pct": h["pct"], "group": h["group"]} for h in top]}
        except Exception as ex:
            print("stock pages: holders not read:", symbol, str(ex)[:120])
    return got


def faq_items(f: dict, region: str, symbol: str, name: str, extras: dict | None = None) -> list[tuple[str, str]]:
    """[(question, answer)] the page answers from facts it holds: its market value, its next results date and its largest named
    holders. A question whose answer isn't known is left out, never answered with "not available"."""
    out = []
    cap = cap_text(f)
    if cap != "–":
        pe = shown_pe(f)
        # the price the value rests on is named as the page names it: a close, or the last price when it is older than the market's
        # latest close or isn't a close ("as of 5 Oct 2026 (the last price this page has; …): the last close times…" was neither)
        # (RC4-007)
        close = _num(f.get("price")) is not None and is_close(f) and not behind(f)
        basis = "the last close" if close or _num(f.get("price")) is None else "the last price this page has"
        when = as_of_text(f) if close or not _date(f.get("price_at")) else _date(f["price_at"])
        out.append((f"What is {name}'s market value?",
                    f"{name}'s market value is {cap} as of {when}: {basis} times the shares in issue."
                    + (f" Its P/E is {_fmt(pe)}, {basis} over earnings per share for the last four reported quarters." if pe is not None else "")))
    nxt = (extras or {}).get("results")
    if nxt and _date(nxt.get("date")):
        purpose = str(nxt.get("purpose") or "").strip()
        purpose = "" if ADVICE_WORDS.search(purpose) else purpose
        from . import results
        when = results.WHEN.get(nxt.get("when") or "")
        out.append((f"When are {name}'s next results?",
                    f"{name}'s next results are listed for {_date(nxt['date'])}" + (f", {when}" if when else "")
                    + (f" (the exchange's notice: {purpose})" if purpose else "") + "."
                    + (f" Dates are as the company announced them, on the list of {_date(nxt['as_of'])}." if _date(nxt.get("as_of")) else "")))
    hold = (extras or {}).get("holders")
    if hold and hold.get("holders") and _date(hold.get("quarter")):
        # a holder's name as the pattern files it ("DSP SMALLCAP FUND , DSP MIDCAP FUND"): a space before a comma is closed up, and
        # a semicolon in it is a comma, since the answer separates holders with one (RC4-008)
        tidy = lambda n: re.sub(r"\s+", " ", re.sub(r"\s+,", ",", str(n or "").replace(";", ","))).strip()      # noqa: E731
        names = "; ".join(f"{tidy(h['name'])} ({'promoter group' if h['group'] == 'promoter' else 'public'}) {h['pct']:g}%" for h in hold["holders"])
        out.append((f"Who are {name}'s largest named shareholders?",
                    f"In the shareholding pattern for the quarter ended {_date(hold['quarter'])}, the largest named holders above 1% were: {names}. "
                    "Percentages are of all shares."))
    return out


def faq_html(items: list[tuple[str, str]], name: str) -> str:
    if not items:
        return ""
    return (f'<h2>Questions about {e(name)}</h2><div class="card faq" data-faq>'
            + "".join(f"<h3>{e(q)}</h3><p>{e(a)}</p>" for q, a in items) + "</div>")


def faq_ld(items: list[tuple[str, str]]) -> list[dict]:
    """The FAQPage structured data for the questions the page shows, word for word."""
    if not items:
        return []
    return [{"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in items]}]


def render(f: dict | None, region: str, symbol: str, name: str | None, extras: dict | None = None) -> str:
    """The page. `f` is None when the sources had nothing on a listed company: a short page, kept out of the index. `extras` is
    what faq_extras read from the stores (the next results date, the named holders), for the questions it answers."""
    site = settings.PUBLIC_SITE_URL
    canonical = site + path(region, symbol)
    name = (f or {}).get("name") or name or symbol
    if region == "US":                    # filings' capitals; Indian names are kept as listed ("ITC Ltd", not "Itc Ltd")
        name = proper_name(name)
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
    desc = description({**f, "name": name})          # the tidied name, as in the title and the h1 (a filing's capitals stay out of the snippet)
    as_of = as_of_text(f)
    questions = faq_items(f, region, symbol, name, extras) if has_content(f) else []
    ld = _ld([{"@context": "https://schema.org", "@type": "Corporation", "name": name, "tickerSymbol": symbol,
               "url": canonical, **({"industry": (plain_industry if region == "US" else str)(f["industry"][-1])} if f.get("industry") else {})},
              {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
                  {"@type": "ListItem", "position": 1, "name": "StratLab", "item": site + "/"},
                  {"@type": "ListItem", "position": 2, "name": name, "item": canonical}]}, *faq_ld(questions)])
    ind = " · ".join(shown_industry(f.get("industry"), plain=region == "US"))
    notes = _notes(f)
    # PUB-2: the name, one quiet line, the price; then the chart; then the key figures; the explanations come last
    parts = [f"""<h1>{e(name)} <span class="muted">({e(symbol)})</span></h1>
{_sub_line(f.get("exchange") or country, ind)}{_price_block(f, as_of)}
<p class="small muted" data-advice>Facts from reported results and exchange filings. Not investment advice.</p>"""]
    parts.append(price_chart_html(f, region, symbol))       # PUB-1: the share price, drawn in the browser from the cached closes
    parts.append(_figures(f))
    parts += [n for n in notes if not _is_basis(n)]
    parts.append(_trend(f))
    parts.append(_table(f))
    shown = [y for y in (filing_entry(x) for x in unique_filings(f.get("filings"))) if y]
    if shown:
        # each filing by what it is, with the document itself behind it when the exchange or the SEC has one (DK-018)
        parts.append("<h2>Recent filings</h2><div class=\"card\"><ul class=\"plain\">" + "".join(
            f'<li><span class="muted small">{e(_date(x["at"]))}</span><br>'
            + (f'<a href="{e(x["url"])}" rel="noopener nofollow">{e(x["name"])}</a>' if x.get("url") else e(x["name"]))
            + "</li>" for x in unique_filings(shown)) + "</ul></div>")
    parts.append(faq_html(questions, name))
    parts.append(_cta(symbol, test, deep))
    about = about_parts(f, region, symbol, name) if has_content(f) else []
    if about:
        # SEO-1: this company's own sentences, from the figures above, one to a line (PUB-2: not one dense paragraph)
        parts.append(f'<h2>About {e(name)}</h2><div class="card"><ul class="plain" data-about>' + "".join(f"<li>{e(x)}</li>" for x in about) + "</ul></div>")
    for sec in peer_sections(region, symbol, f.get("industry") or [], shown_cap(f)):
        parts.append(f'<h2>{e(sec["title"])}</h2><p class="small muted" data-peers>{e(sec["caption"])}</p>' + _links(region, sec["rows"]))
    parts.append(browse_block(region, symbol))        # SEO-1: the companies before and after it A to Z, its letter's list and its indexes
    parts.append(_how(f, [n for n in notes if _is_basis(n)]))       # PUB-2: how each figure is worked out, last and folded
    # a company with a price but no reported numbers to show (a filer whose results aren't filed as data) is a short page
    # for a visitor who looks it up, kept out of search results and the sitemap (see has_content)
    return _page(_head(title, desc, canonical, ld, robots="noindex,follow" if f.get("no_numbers") else "index,follow"), app, "".join(parts))


def _cta(symbol: str, test: str, deep: str) -> str:
    return f"""<div class="card"><h2>Go further with {e(symbol)}</h2>
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
    if cap == "–" and (cap_problem(f) or cap_missing_reason(f)):
        cap = "n/a"                               # a value that failed its checks, or that can't be worked out: said, not hidden (see _notes)
    pe, dy = shown_pe(f), shown_yield(f)
    # the key figures that are the newest year's own: n/a when that year ended more than 15 months before the price,
    # the rule P/E has (R10V-002)
    old = figures_stale(f)
    year = lambda text: "n/a" if old else text      # noqa: E731
    # beside the last twelve months' profit (and a P/E on it), the figures that are the newest year's own name that year,
    # so no reader takes a year's margin for the twelve months' (R12-007: Katapult's "Net profit, last 12 months $16M",
    # "P/E 1.4" and "Net margin 0.5%", the last its year to Dec 2025's)
    # ...and on every page alike, whether or not it has a last-12-months profit (DK-024: MSFT's carried no year, KPLT's did)
    end = figures_end(f)
    of_year = f" (year to {_date(end)[-8:]})" if end and _date(end) else ""
    out = [(price_label(f), _money(f, f.get("price"))),
           # the range is the year's highest and lowest trade, not closes (R6V-014)
           (f"Range since listing on {_date(f['range_since'])} (intraday)" if f.get("range_since") and _date(f["range_since"]) else "1-year range (intraday)",
            f"{_money(f, f.get('low52'))} to {_money(f, f.get('high52'))}"
            if _num(f.get("low52")) is not None and _num(f.get("high52")) is not None else "–"),
           ("Market cap", cap), (pe_label(f), _fmt(pe) if pe is not None else "n/a")]
    ttm, owners = f.get("profit_ttm"), owners_profit(f)
    digits = small_digits(ttm, owners)
    if owners is not None:
        # the table's profit includes minority shareholders' share of subsidiaries, which P/E leaves out: both are shown,
        # each named, so the profit line and the P/E agree (DK-021: RELIANCE's 88,167 beside a P/E on 74,727)
        out += [(f"Profit to shareholders, last 12 months ({unit})", _amount(f, owners, digits)),
                (f"Net profit incl. minority interests, last 12 months ({unit})", _amount(f, ttm, digits))]
    else:
        out.append((f"Net profit, last 12 months ({unit})", _amount(f, ttm, digits)))
    out.append((f"Return on equity{of_year}", year(_pct(f.get("roe")))))
    if not f.get("bank"):
        out += [(f"EBITDA margin{of_year}", year(_pct(f.get("opm"), whole))), ("Debt to equity", year(_fmt(f.get("debt_equity"), 2)))]
    out += [(f"Net margin{of_year}", year(_pct(f.get("net_margin")))),
            ("Dividend yield", (_fmt(dy, 2, "%") + (f" (incl. a special dividend of {'$' if f.get('currency') == 'USD' else '₹'}{_num(f['div_special']):,.2f})".replace(".00)", ")") if _num(f.get("div_special")) else "")) if dy is not None else "n/a")]
    return [(k, v) for k, v in out if v != "–"]


# ---------- the top of a company's page (PUB-2) ----------
TILE_LABEL_MAX = 24            # a tile's label is one short line (two on a phone), never three: the longer wording is its title and the notes at the foot


def _sub_line(exchange: str, industry: str) -> str:
    """One quiet line under the name: where it is listed, its sector and industry, in sentence case; the whole of it is the line's title,
    for when a long industry is cut short by the page's edge."""
    ind = industry[:1] + industry[1:].lower() if industry.isupper() else industry
    text = " · ".join([exchange] + ([ind] if ind else []))
    return f'<p class="sub muted" title="{e(text)}">{e(text)}</p>\n'


def _price_block(f: dict, as_of: str) -> str:
    """The last close, large, what it moved on its day (the chart's script fills that in from the closes it reads, so a page
    with no script has none) and the session it is from, small. With no price, the page says so."""
    price = _num(f.get("price"))
    if price is None:
        return ("<p class=\"small muted\" data-as-of>No recent share price is available for this company."
                f"{' Page built ' + e(as_of) + '.' if as_of else ''}</p>")
    return (f'<div class="px"><p class="px-line"><b data-price>{e(_money(f, price))}</b><span class="px-chg" data-day hidden></span></p>'
            f'<p class="small muted" data-as-of>As of {e(as_of)}.</p></div>')


def _short_amount(unit: str, text: str) -> str:
    """A reported amount with its unit as one short value: "₹29,678 cr", "$128,930M", "INR 16.19M"."""
    sign, text = ("-", text[1:]) if text[:1] in "-−" else ("", text)
    parts = unit.split()
    if unit == "₹ crore":
        return f"{sign}₹{text} cr"
    if unit.startswith("$") and len(parts) == 2 and parts[1] in ("million", "billion"):
        return f"{sign}${text}{parts[1][0].upper()}"
    if len(parts) == 2 and parts[1] in ("million", "billion"):
        return f"{sign}{parts[0]} {text}{parts[1][0].upper()}"
    return f"{sign}{text} {unit}".strip()


def _tiles(f: dict) -> list[dict]:
    """The key figures as tiles: a short label, the value, and a small line under it for its unit or period. Built from _stats
    (the same figures, the same checks), leaving out the price (the header's) and the range (its own row) and any figure that is
    n/a, so a company with fewer figures has fewer tiles and no gaps; why a figure isn't there is in the notes."""
    unit = f.get("unit") or ""
    end = figures_end(f)
    year = f"year to {_date(end)[-8:]}" if end and _date(end) else "latest reported year"
    out = []
    for label, val in _stats(f):
        if val == "n/a" or label.startswith(("Last ", "1-year range", "Range since")):
            continue
        line = ""
        if label == "Market cap":
            short, line = "Market cap", "last close × shares"
        elif label.startswith("P/E"):
            short = "P/E"
            # LIVE1B-076: said as what it is, reported earnings of the last four quarters, not a vague "last 12 months"
            line = "on " + (label[label.index("(") + 1:-1] + " profit" if "(" in label else "reported profit, last four quarters")
        elif label.startswith("Profit to shareholders"):
            short, line, val = "Profit, last 12 months", "to shareholders", _short_amount(unit, val)
        elif label.startswith("Net profit incl."):
            short, line, val = "Profit incl. minorities", "last 12 months", _short_amount(unit, val)
        elif label.startswith("Net profit"):
            short, line, val = "Net profit", "last 12 months", _short_amount(unit, val)
        elif label.startswith("Dividend yield"):
            short, line = "Dividend yield", "last 12 months"
            special = re.match(r"^(.*?) \(incl\. a special dividend of (.*)\)$", val)
            if special:
                val, line = special.group(1), f"last 12 months, with a {special.group(2)} special dividend"
        else:
            short = re.sub(r" \(year to .*\)$", "", label)
            line = year
        out.append({"label": short, "value": val, "line": line, "title": label, "long": len(val) > 12})
    return out


def _range_row(f: dict) -> str:
    """The year's lowest and highest price as a bar with the last close marked on it, the two ends named (intraday: the range is
    the year's highest and lowest trade, not closes). Empty when the page has no range."""
    low, high, price = _num(f.get("low52")), _num(f.get("high52")), _num(f.get("price"))
    if low is None or high is None:
        return ""
    label = f"Range since listing on {_date(f['range_since'])} (intraday)" if f.get("range_since") and _date(f["range_since"]) else "1-year range (intraday)"
    lo, hi = _money(f, low), _money(f, high)
    marker = ""
    said = f"From a low of {lo} to a high of {hi}"
    if price is not None:
        at = 50.0 if high <= low else max(0.0, min(100.0, (price - low) / (high - low) * 100))
        anchor = "start" if at < 22 else "end" if at > 78 else "middle"
        now = _money(f, price)
        said += f", with the last close at {now}"
        marker = (f'<text class="rb-now" x="{at:.1f}%" y="13" text-anchor="{anchor}">Last close {e(now)}</text>'
                  f'<circle class="rb-dot" cx="{at:.1f}%" cy="32" r="6"/>')
    return (f'<div class="range" data-range><p class="range-name">{e(label)}</p>'
            f'<svg class="rbar" width="100%" height="44" role="img" aria-label="{e(said)}"><line class="rb-track" x1="0" x2="100%" y1="32" y2="32"/>{marker}</svg>'
            f'<p class="range-ends"><span><small>Low</small> <b>{e(lo)}</b></span><span><small>High</small> <b>{e(hi)}</b></span></p></div>')


def _figures(f: dict) -> str:
    """The key figures: the range, then even tiles (four across, three when that leaves fewer empty places; two on a phone). When the
    last row is short, its last tile takes the places that are left, so the grid has no hole. A page with neither has no card."""
    tiles, rng = _tiles(f), _range_row(f)
    n = len(tiles)
    if not tiles and not rng:
        return ""
    cols = min(4 if (-n) % 4 <= (-n) % 3 else 3, max(n, 2))
    rest = (-n) % cols
    cells = "".join(f'<div class="stat{" long" if t["long"] else ""}{f" fill{rest + 1}" if rest and i == n - 1 else ""}" title="{e(t["title"])}">'
                    f'<span>{e(t["label"])}</span><b>{e(t["value"])}</b><small>{e(t["line"])}</small></div>' for i, t in enumerate(tiles))
    return f'<h2>Key figures</h2><div class="card figs">{rng}' + (f'<div class="tiles c{cols}">{cells}</div>' if tiles else "") + "</div>"


def _is_basis(note: str) -> bool:
    """The two notes that work out a figure (P/E against the profit shown, the last 12 months against the year): they sit at the foot of the page
    with how every figure is worked out, not between the figures and the chart's neighbours."""
    return "data-pe-basis" in note or "data-ttm-basis" in note


def pe_profit_gap(f: dict):
    """(P/E shown, market cap over the table's last-12-months net profit, that profit) for an Indian company whose two
    differ by more than 10%; None otherwise (R16-004: P/E 21.3 beside a market cap and profit that give 18.0)."""
    if f.get("region") != "IN":
        return None
    pe, cap, profit = shown_pe(f), shown_cap(f), _num(f.get("profit_ttm"))
    if pe is None or not cap or not profit or profit <= 0:
        return None
    implied = cap / profit
    return (pe, implied, profit) if abs(implied - pe) > 0.1 * pe else None


def owners_profit(f: dict):
    """The last 12 months' profit that belongs to the company's shareholders, for an Indian company whose table's net
    profit (which includes the share of minority shareholders) doesn't agree with its P/E (pe_profit_gap): market cap
    over P/E, the profit the P/E is on (DK-021). None otherwise."""
    gap = pe_profit_gap(f)
    cap = shown_cap(f)
    return cap / gap[0] if gap and cap else None


def ttm_year_gap(f: dict) -> tuple[float, float, str] | None:
    """(last 12 months' net profit, the newest year's, that year) when they differ by more than 5%, for a page with no
    P/E note to say why: the trailing figure is the four latest quarters (R91-005: AAPL's "last 12 months 128,930"
    beside the table's FY Sep 2025 112,010, with nothing on the page saying how both can be right)."""
    ttm = _num(f.get("profit_ttm"))
    years = [y for y in f.get("years") or [] if isinstance(y, dict) and y.get("year") and _num(y.get("profit")) is not None]
    if ttm is None or not years or pe_profit_gap(f):
        return None
    last = years[-1]
    p = _num(last.get("profit"))
    if not p or abs(ttm - p) <= 0.05 * abs(p):
        return None
    return ttm, p, str(last.get("year"))


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
    if cap_problem(f) and f.get("region") == "IN":
        out.append('<p class="note warn" data-cap-check>Market cap unavailable: the value worked out from the share count and '
                   "the price doesn't agree with the company's reported figures, so it isn't shown, nor is P/E, and the "
                   "company is left out of lists ranked by size.</p>")
    elif cap_problem(f):
        out.append('<p class="note warn" data-cap-check>The market value worked out from the share count and the price '
                   "doesn't agree with the company's own reported figures (it may count ordinary shares against a "
                   "depositary share's price), so it isn't shown, nor is P/E, and the company is left out of lists "
                   "ranked by size.</p>")
    why = cap_missing_reason(f)
    if why == "shares":
        out.append('<p class="note" data-cap-missing>Market cap isn\'t shown: the number of shares in issue couldn\'t be read from '
                   "this company's filings, so the price can't be multiplied by it.</p>")
    elif why == "no_numbers":
        out.append(f'<p class="note" data-cap-missing>Market cap and reported figures aren\'t shown: {e(public_text(str(f.get("no_numbers"))))}</p>')
    elif why == "unknown":
        out.append('<p class="note" data-cap-missing>Market cap isn\'t shown: this page has no count of the shares in issue to '
                   "multiply the price by.</p>")
    if figures_stale(f):
        out.append(f'<p class="note" data-figures-old>Return on equity, margins and debt to equity aren\'t shown: the newest year in '
                   f'the table ended on {e(_date(figures_end(f)))}, more than 15 months before this price, and a newer annual '
                   "report's figures aren't on the page yet.</p>")
    if pe_stale(f) and _num(f.get("pe")) is not None:
        out.append(f'<p class="note" data-pe-old>P/E isn\'t shown: the latest reported earnings on this page are for the '
                   f'year to {e(_date(pe_period(f)[1]))}, more than 15 months before this price, and a newer annual '
                   "report's figures aren't on the page yet.</p>")
    gap = pe_profit_gap(f)
    if gap:
        pe, implied, profit = gap
        out.append(f'<p class="note" data-pe-basis>P/E {pe:,.1f} is the close over earnings per share, the profit that belongs to the '
                   f'company\'s shareholders (market cap divided by P/E: {_amount(f, owners_profit(f))} crore for the last 12 months, shown above). '
                   f'The net profit including the share owned by minority shareholders of subsidiaries is {_amount(f, profit)} crore; '
                   f'market cap divided by that gives {implied:,.1f}. '
                   "The last 12 months are the four latest reported quarters, so their profit can differ from the newest year's in "
                   'the table below.</p>')
    if f.get("pe_oneoff") and shown_pe(f) is not None:
        # a gain booked in one of the four quarters is in the earnings behind the P/E (RC6-012: TMPV's 1.2): said, as a fact
        out.append(f'<p class="note" data-pe-oneoff>P/E {shown_pe(f):,.1f} is on the last four reported quarters. {e(str(f["pe_oneoff"]))}, '
                   "so that income is in the earnings behind the figure.</p>")
    if ttm_year_gap(f):
        out.append('<p class="note" data-ttm-basis>The net profit for the last 12 months is the four latest reported quarters, so it '
                   "can differ from the newest year's in the table below.</p>")
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
           "by the net profit shown (a different share count, or the profit before minority interests; where they differ by more than 10%, a note under the figures gives both). A company that "
           "reports only once a year has its latest year's earnings, and the P/E names that year; when that year ended "
           "more than about 15 months before the close, P/E is n/a. A loss has no P/E. Above 1,000 it is n/a.")
YIELD_NOTE = ("Dividend yield: every dividend per share with an ex-date in the 12 months to the last close, special "
              "dividends included, as a share of that close. n/a when the company's dividends couldn't be read.")


def _how(f: dict, notes: list[str] | None = None) -> str:
    """How each figure is worked out, so a reader can check one against another. Folded at the foot of the page; its text is in the page for
    anyone who reads it all, with the notes that work a figure out against another (`notes`)."""
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
        "Net margin: net profit as a share of revenue in the latest reported period. Return on equity, the margins and debt to "
        "equity each use inputs from that one year; if one input is missing for it, the figure is n/a. When that year ended more "
        "than about 15 months before the close, they are n/a too.",
        YIELD_NOTE,
        f"n/m: not meaningful. A margin or return beyond ±{NOT_MEANINGFUL:,.0f}% comes from revenue or equity near zero, so it is "
        "not shown as a number.",
    ]
    return ('<details class="card how" data-how><summary>How these figures are worked out</summary>' + "".join(notes or [])
            + '<ul class="small">' + "".join(f"<li>{e(t)}</li>" for t in items) + "</ul></details>")


def _trading_days(n) -> str:
    """"1 trading day", "16 trading days" (VR6: the page said "for 1 trading days")."""
    return f"{n} trading {'day' if n == 1 else 'days'}"


def _trend(f: dict) -> str:
    s = f.get("stage")
    if not s and f.get("st_up") is None:
        return ""
    bits = []
    if s in STAGE:
        days = f.get("stage_days")
        bits.append(f"<li><b>{STAGE[s]}</b>: {STAGE_WHY[s]}{', for ' + _trading_days(days) if days else ''}.</li>")
    if f.get("st_up") is not None:
        side = "above" if f["st_up"] else "below"
        d = f.get("st_days")
        bits.append(f"<li><b>Supertrend (10, 3)</b>: the price has closed {side} the line{' for ' + _trading_days(d) if d else ''}.</li>")
    return '<h2>Price trend</h2><div class="card"><ul class="plain">' + "".join(bits) + "</ul></div>"


# ---------- the charts on a company's page (PUB-1) ----------
# The share-price chart is drawn in the visitor's browser by one small script (stock_chart.js, served as /stocks/chart.js)
# from a cached list of daily closes (/stocks/<market>/<symbol>/prices.json): the page's stored facts hold no series, and
# putting five years of closes into 13,000 stored pages was never worth the memory. The page itself says the same facts in
# words (the last close, the 1-year range) so a crawler, or a visitor without the script, loses only the picture.
# Revenue and profit are drawn on the server from the years the page already stores: plain HTML and CSS, no script.
CHART_JS = (Path(__file__).with_name("stock_chart.js")).read_text(encoding="utf-8")
CHART_JS_V = hashlib.sha1(CHART_JS.encode()).hexdigest()[:8]
CHART_READ_DAYS = 1850         # five years of daily candles, and a little over, read for the longest range
CHART_DAILY_DAYS = 372         # the last year (a little over) is kept day by day; before it, the last close of each week
CHART_SERIES_CACHE = "public, max-age=300, s-maxage=3600, stale-while-revalidate=21600"
CHART_MISSING_CACHE = "public, max-age=60, s-maxage=300"      # no series (a new listing, a source down): asked again in minutes, not at every view


def chart_series(bars: list[dict]) -> dict:
    """Daily candles as the chart's list of closes: {"t": [days since 1970-01-01], "c": [closes]}, oldest first. The last
    CHART_DAILY_DAYS days are every session; before them, the last close of each week (some 460 points for five years, about
    6 KB, and a line no different to the eye). Rounded to the cent, to four decimals under 10 cents. {} when there are
    fewer than two closes."""
    rows: dict[str, float] = {}
    for b in bars or []:
        c, d = _num(b.get("c")), str(b.get("t") or "")[:10]
        if c is None or c <= 0 or len(d) != 10:
            continue
        try:
            date.fromisoformat(d)
        except ValueError:
            continue
        rows[d] = c
    if len(rows) < 2:
        return {}
    days = sorted(rows)
    cut = (date.fromisoformat(days[-1]) - timedelta(days=CHART_DAILY_DAYS)).isoformat()
    keep, week = [], None
    for d in days:
        if d >= cut:
            keep.append(d)
            continue
        iso = date.fromisoformat(d).isocalendar()[:2]
        if keep and week == iso:
            keep[-1] = d                                  # a later close of the same week replaces the earlier one
        else:
            keep.append(d)
            week = iso
    epoch = date(1970, 1, 1)
    return {"t": [(date.fromisoformat(d) - epoch).days for d in keep],
            "c": [round(rows[d], 4 if rows[d] < 0.1 else 2) for d in keep]}


CHART_ADJ_MAX = 6              # splits, bonus issues and demergers named under the chart (the newest)


def chart_adjustments(rows, first_day: str, last_day: str, region: str = "IN") -> list[dict]:
    """[{"d": ex-date, "k": "split" | "bonus" | "demerger", "t": the action in words}] for the stored corporate actions whose ex-date
    falls inside the chart's dates, oldest first: what the chart's note says about them. The price sources' earlier closes are
    adjusted for a split or a bonus issue (no jump, but not the prices that traded) and not for an Indian demerger (a step by the
    value that moved to the new company). Nothing is read from a source: `rows` is what the app already keeps (RC4-006)."""
    out = []
    for a in rows or []:
        if not isinstance(a, dict):
            continue
        ex = str(a.get("ex_date") or "")[:10]
        if not (first_day < ex <= last_day):
            continue
        from .corp_actions import adjusts
        if adjusts(a):
            out.append({"d": ex, "k": a["kind"], "t": str(a.get("short") or a["kind"])[:60]})
        elif a.get("kind") == "demerger" and region == "IN" and a.get("label") == "Demerger":
            out.append({"d": ex, "k": "demerger"})
    return sorted(out, key=lambda x: x["d"])[-CHART_ADJ_MAX:]


def price_chart_html(f: dict, region: str, symbol: str) -> str:
    """The share-price card: the change over the chosen range, the 1M / 6M / 1Y / 5Y switch, the chart's place (its height is
    kept, so nothing moves when it is drawn), the same facts as text, and the closes as a table. Only for a page whose price
    is a close (a last trade from a quote has no daily series behind it)."""
    if _num(f.get("price")) is None or not is_close(f) or not f.get("price_at"):
        return ""
    low, high = _num(f.get("low52")), _num(f.get("high52"))
    text = f"Last close {_money(f, f.get('price'))} on {_date(f.get('price_at'))}."
    if low is not None and high is not None:
        since = f" since listing on {_date(f['range_since'])}" if f.get("range_since") and _date(f["range_since"]) else " over the last 12 months"
        text += f" The share price traded between {_money(f, low)} and {_money(f, high)} (intraday){since}."
    src = f"/stocks/{region.lower()}/{quote(symbol, safe='')}/prices.json"
    buttons = "".join(f'<button type="button" data-r="{k}" aria-pressed="{"true" if k == "1y" else "false"}">{v}</button>'
                      for k, v in (("1m", "1M"), ("6m", "6M"), ("1y", "1Y"), ("5y", "5Y")))
    buttons += '<button type="button" data-r="all" aria-pressed="false" hidden>All</button>'
    return (f'<h2>Share price</h2><div class="card chart" data-chart data-src="{e(src)}" data-currency="{"USD" if region == "US" else "INR"}" data-price="{_num(f.get("price"))}" data-price-at="{e(str(f.get("price_at"))[:10])}">'
            f'<div class="chart-top"><p class="chg"><b data-change></b><span data-change-note class="muted small"></span></p>'
            f'<div class="seg" role="group" aria-label="Chart range" hidden>{buttons}</div></div>'
            '<div class="plot"><p class="plot-note muted small" data-status role="status">Prices load here as you scroll to them.</p>'
            '<div class="tip" hidden></div></div>'
            f'<p class="small muted" data-summary>{e(text)}</p><p class="small muted" data-adjust hidden></p>'
            '<details class="how" data-table><summary>The closes as a table</summary>'
            '<p class="small muted" data-rows></p><div class="tbl2"><table><thead><tr><th scope="col">Date</th><th scope="col">Close</th></tr></thead><tbody></tbody></table></div></details>'
            '<p class="sr-only" aria-live="polite" data-live></p>'
            f'<noscript><p class="small muted">The chart needs JavaScript. The close and the 1-year range are above.</p></noscript></div>'
            f'<script src="/stocks/chart.js?v={CHART_JS_V}" defer></script>')


def nice_ticks(lo: float, hi: float, count: int = 4) -> list[float]:
    """Round axis values reaching from at or below `lo` to at or above `hi`: steps of 1, 2, 2.5 or 5 times a power of ten."""
    span = (hi - lo) or abs(hi) or 1.0
    raw = span / count
    p = 10 ** math.floor(math.log10(raw))
    step = next(m for m in (1, 2, 2.5, 5, 10) if raw / p <= m + 1e-9) * p
    first, last = math.floor(lo / step + 1e-9), math.ceil(hi / step - 1e-9)
    return [round(i * step, 10) for i in range(first, last + 1)]


def tick_digits(ticks: list[float]) -> int:
    """Decimals that write every axis value exactly: none for 0, 250 or 1,000, one for 2.5, two for 0.25. An axis of a small
    company's amounts (₹ crore under 10: ticks of 0.2 or 2.5) was labelled in whole numbers, so 0.6 and 0.8 both read "1" and
    2.5 read "2" (RC4-001)."""
    for d in range(5):
        if all(abs(t - round(t, d)) < 1e-9 for t in ticks):
            return d
    return 4


def _short_year(label: str) -> str:
    """"Mar 2026" as "Mar ’26": a column's label that fits five to a phone's width."""
    return re.sub(r"\s\d\d(\d\d)$", r" ’\1", label)


def bars_chart_html(f: dict, digits: int = 0) -> str:
    """Revenue and net profit by year as columns, from the years the page stores: HTML and CSS only, each year a focusable
    group whose figures show on hover or focus, and the table below says the same in numbers. One scale for both (the same
    unit), a baseline at zero, and a loss below it."""
    ys = [y for y in (f.get("years") or []) if _num(y.get("sales")) is not None or _num(y.get("profit")) is not None]
    if len(ys) < 2:
        return ""
    vals = [v for y in ys for v in (_num(y.get("sales")), _num(y.get("profit"))) if v is not None]
    top, bottom = max(max(vals), 0.0), min(min(vals), 0.0)
    ticks = nice_ticks(bottom, top, 4)
    hi, lo = ticks[-1], ticks[0]
    span = (hi - lo) or 1.0
    pct = lambda v: (v - lo) / span * 100             # noqa: E731  position from the plot's bottom, in percent
    num = lambda x: f"{x:.2f}".rstrip("0").rstrip(".")           # noqa: E731  a style value: "0", "33.33"
    at = lambda v: num(pct(v))                                    # noqa: E731
    td = tick_digits(ticks)
    grid = "".join(f'<i class="by-line" style="bottom:{at(t)}%"></i><span class="by-tick" style="bottom:{at(t)}%">{e(_amount(f, t, td) if t else "0")}</span>'
                   for t in ticks)
    cols = []
    for y in ys:
        sales, profit = _num(y.get("sales")), _num(y.get("profit"))
        label = str(y.get("year") or "")
        said = ", ".join(x for x in (f"revenue {_amount(f, sales, digits)}" if sales is not None else "",
                                     f"net profit {_amount(f, profit, digits)}" if profit is not None else "") if x)
        bars = ""
        for cls, v in (("rev", sales), ("pro", profit)):
            if v is None:
                continue
            a, b = sorted((pct(0.0), pct(v)))
            bars += f'<i class="by-bar {cls}{" neg" if v < 0 else ""}" style="bottom:{num(a)}%;height:{num(max(b - a, 0.4))}%"></i>'
        cols.append(f'<div class="by-col" tabindex="0" role="img" aria-label="{e(label)}: {e(said)} ({e(f.get("unit") or "")})">{bars}'
                    f'<span class="by-tip"><b>{e(label)}</b>' + (f'<span class="k rev">Revenue</span> {e(_amount(f, sales, digits))}' if sales is not None else "")
                    + (f'<span class="k pro">Net profit</span> {e(_amount(f, profit, digits))}' if profit is not None else "")
                    + f'</span><span class="by-x">{e(_short_year(label))}</span></div>')
    return (f'<figure class="by" aria-label="Revenue and net profit by year, in {e(f.get("unit") or "")}">'
            '<div class="by-key"><span><i class="sw rev"></i>Revenue</span><span><i class="sw pro"></i>Net profit</span>'
            f'<span class="muted">{e(f.get("unit") or "")}</span></div>'
            f'<div class="by-plot">{grid}<div class="by-cols">{"".join(cols)}</div></div></figure>')


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
    # one precision for the amounts in the table: two decimals when they are all small, so "2, 2, 2" doesn't sit beside 0.43
    digits = small_digits(*[y.get(k) for y in ys for k in (("sales", "profit") if f.get("bank") else ("sales", "profit", "debt"))])
    rows = [("Revenue", "sales", lambda v: _amount(f, v, digits)), ("Net profit", "profit", lambda v: _amount(f, v, digits))]
    if not f.get("bank"):
        rows += [("EBITDA margin", "opm", lambda v: _pct(v, whole)), ("Borrowings", "debt", lambda v: _amount(f, v, digits))]
    head = "".join(f"<th>{e(str(y.get('year') or ''))}</th>" for y in ys)
    body = "".join(f"<tr><td>{label}</td>" + "".join(f"<td>{fmt(y.get(k))}</td>" for y in ys) + "</tr>"
                   for label, k, fmt in rows if any(_num(y.get(k)) is not None for y in ys))
    growth = [w for w in (growth_words("revenue", g.get("sales_cagr_3y")), growth_words("net profit", g.get("profit_cagr_3y"))) if w]
    note = f'<p class="small muted">{e(f.get("unit") or "")}{". Over three years, compounded: " + ", ".join(growth) if growth else ""}.</p>'
    cue = '<p class="scroll-cue" aria-hidden="true">Newest year on the right. Swipe for earlier years →</p>' if len(ys) > 2 else ""
    return (f'<h2>Revenue and profit</h2><div class="card">{bars_chart_html(f, digits)}{cue}<div class="tbl fin" tabindex="0" role="region" aria-label="Revenue and profit by year">'
            f'<table><tr><th scope="col">Year</th>{head}</tr>{body}</table></div>{note}</div>')


def surveillance_html(flags: list[dict]) -> str:
    """The stock's exchange surveillance flags as small badges, each opening to what the exchange's measure is and
    the date of the list. The badge's colours are the page's theme tokens, so it reads in dark mode too (R8V-009: a
    fixed dark amber on the dark card was 2.37:1). A heading like the page's other sections, and no grey paragraph of its own:
    that the measures are facts about trading rules, not a view, is said inside each flag when it is opened (VR6-002)."""
    if not flags:
        return ""
    items = "".join(
        f'<details class="surv"><summary><span class="badge">{e(f["short"])}</span> {e(f["label"])}</summary>'
        f'<p class="small">{e(f["text"])}'
        f'{" List as of " + e(_date(f["as_of"])) + "." if f.get("as_of") else ""}'
        " From the exchange's published surveillance lists: a measure the exchange applies for a time. It is a fact about trading rules, not a view on the company.</p></details>"
        for f in flags)
    return f'<h2>Exchange surveillance</h2><div class="card" data-surveillance>{items}</div>'


def with_surveillance(page: str, flags: list[dict]) -> str:
    """A stored page with today's surveillance flags added (the lists change daily; the page is kept until the next close).
    They come after the name, the price, the chart and the key figures, before the sections of detail (VR6-002: a heading and a
    grey explanation sat between the price and the chart)."""
    block = surveillance_html(flags)
    if not block:
        return page
    for anchor in ('<h2>Price trend</h2>', '<h2>Revenue and profit</h2>', '<h2>Recent filings</h2>', '<h2>Questions about', '<div class="card"><h2>Go further',
                   '<h2>About '):
        i = page.find(anchor)
        if i >= 0:
            return page[:i] + block + page[i:]
    return page


def with_ref(page: str, code: str) -> str:
    """A page whose links into the app (sign up, test, deep dive) carry an invite code, for someone who arrived from
    a shared card. Links to other company pages and the /stocks list, and the canonical address, stay as they are."""
    site = re.escape(settings.PUBLIC_SITE_URL)

    def add(m):
        return f'{m.group(1)}{m.group(2)}{"&amp;" if "?" in m.group(2) else "?"}ref={code}"'
    return re.sub(rf'(<a [^>]*?href=")({site}/(?!stocks(?:/|"))[^"#]*)"', add, page)


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
    # a market's own page says its market: "Company pages" with "India and the US" under it, above a list of India only, said two things (VR4-002)
    where = {"IN": "India (NSE and BSE)", "US": "the US"}.get(region or "", "India (NSE and BSE) and the US")
    heading = {"IN": "Companies listed in India", "US": "Companies listed in the US"}.get(region or "", "Company pages")
    body = [f'<h1>{heading}</h1><p class="muted">Every company listed in {where}: its last close, '
            "reported results, margins, debt and recent filings. Facts, not advice.</p>", _find_form(region, q)]
    crumbs = ld = ""
    if region and not q:
        crumbs, ld = _crumbs([("Companies", "/stocks"), ("India" if region == "IN" else "US", f"/stocks/{region.lower()}")])
        body.insert(0, crumbs)
    elif not q:
        # /stocks itself had no structured data (LIVE1A-066): its place in the site, as the market pages have theirs
        ld = _crumbs([("Companies", "/stocks")])[1]
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
                # (not `where`: this loop used to overwrite the page's own `where`, so /stocks' description read "listed in US", LIVE1A-065)
                place = "India" if r == "IN" else "US"
                head = (f"{place}: the largest companies" if ranked else f"{place}: some of the companies")
                cap = ('<p class="small muted">By market value, among companies whose value passed StratLab\'s checks against '
                       "their reported figures. Funds and notes are left out.</p>" if ranked else "")
                body.append(f"<h2>{head}</h2>{cap}{_links(r.lower(), big)}")
            body.append(az_nav(r))                    # SEO-1: every company a click or two from here
    canonical = site + (f"/stocks/{region.lower()}" if region else "/stocks")
    return _page(_head({"IN": "Company pages: India · StratLab", "US": "Company pages: US · StratLab"}.get(region or "", "Company pages: India and US · StratLab"),
                       f"Find any company listed in {where.replace(' (NSE and BSE)', '').replace('India and the US', 'India or the US')}: price, results, "
                       "margins, debt and filings, from reported data.", canonical, ld, robots="noindex,follow" if q else "index,follow"),
                 None, "".join(body))


# ---------- company directories: A-Z and by index, so every page is a few links from the home page (SEO-1) ----------
# Google found the sitemaps' addresses and judged 13,131 of them not worth crawling yet, partly because almost nothing linked to
# them. These pages link every company that has a page: /stocks/in/browse/s (companies by the first letter of their name, in
# pages of DIR_PAGE links) and /stocks/in/index/nifty-50 (an index's members), from /stocks, the exchange pages, the home page
# and each company's own page. Built from the list the app already holds (companies) and the stored pages' marks (listable),
# never from the data sources, and kept as lists of symbols: a few hundred KB for both markets.
DIR_PAGE = 400                  # company links on one directory page
DIR_FRESH = 3600                # a built directory is kept this long (the companies list itself is kept an hour)
LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
OTHER = "0-9"                   # names that start with a digit or with nothing a Latin letter can stand for
MIN_INDEX = 10                  # an index list with fewer pages than this is a broken read, not shown
# {region: [(address part, name, where the app keeps its members, key)]}; an index the app holds no members for is not listed
INDEX_LISTS = {
    "IN": [("nifty-50", "NIFTY 50", "preset", "nifty50"), ("nifty-bank", "NIFTY Bank", "preset", "banknifty"),
           ("nifty-500", "NIFTY 500", "breadth", "nifty500"), ("nifty-midcap-150", "NIFTY Midcap 150", "breadth", "midcap150"),
           ("nifty-smallcap-250", "NIFTY Smallcap 250", "breadth", "smallcap250")],
    "US": [("sp-500", "S&P 500", "sp500", "sp500")],
}
_dir: dict[str, tuple[float, object, dict]] = {}          # {region: (built at, the companies list it was built from, directory)}
_dir_index: dict[str, tuple[float, object, dict]] = {}    # {region: (built at, companies list, {address part: (name, [page symbols], as of)})}
_dir_lock = threading.Lock()


def _fold(name) -> str:
    """A name as it sorts in the directory: lower case, accents dropped, without leading punctuation ("3M" and "&Co" aside)."""
    t = unicodedata.normalize("NFKD", str(name or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"^[^a-z0-9]+", "", t)


def letter_of(name) -> str:
    """The directory page a name belongs on: its first letter, or OTHER."""
    first = _fold(name)[:1]
    return first.upper() if first.isalpha() else OTHER


def label_of(region: str, symbol: str, co: dict | None = None) -> str:
    """A company's name as the directory lists and sorts it: tidy case for US filings' capitals, the symbol for a company
    with no name."""
    co = co if co is not None else companies(region).get(symbol) or {}
    name = co.get("name")
    return str((proper_name(name) if region == "US" else name) or symbol)


def directory(region: str) -> dict:
    """{"order": every company that is listed, A to Z by name, "pos": {symbol: index in order}, "start": {letter: its first
    index in order}, "count": {letter: companies}}. The companies are those whose page is in the sitemap (listable), so the
    directory never links a page that is kept out of search results."""
    cos = companies(region)
    with _dir_lock:
        hit = _dir.get(region)
        if hit and hit[1] is cos and time.time() - hit[0] < DIR_FRESH:
            return hit[2]
    known = listing(region)
    keyed = sorted((_fold(label_of(region, s, v)), s) for s, v in cos.items() if listable(region, s, known))
    order = [s for _, s in keyed]
    start: dict[str, int] = {}
    count: dict[str, int] = {}
    for i, (key, _s) in enumerate(keyed):
        letter = key[:1].upper() if key[:1].isalpha() else OTHER
        start.setdefault(letter, i)
        count[letter] = count.get(letter, 0) + 1
    out = {"order": order, "pos": {s: i for i, s in enumerate(order)}, "start": start, "count": count}
    with _dir_lock:
        _dir[region] = (time.time(), cos, out)
    return out


def _members(region: str, kind: str, key: str) -> tuple[list[str], str | None]:
    """(member symbols, the day the list is of) of an index list, from what the app already keeps: the ready-made group, the
    breadth run's last good list, or the committed S&P 500 list. Nothing is fetched."""
    if kind == "preset":
        p = universes.current(next(q for q in universes.PRESETS[region] if q["id"] == key))
        return list(p["symbols"]), p.get("as_of")
    if kind == "breadth":
        from . import breadth
        got = db.json_value(db.get_setting(breadth.MEMBERS_KEY + key), [])
        return [s for s in got if isinstance(s, str)], None
    doc = universes.sp500_doc()
    return [r[0] for r in doc["rows"]], doc.get("as_of")


def index_lists(region: str) -> dict[str, tuple[str, list[str], str | None]]:
    """{address part: (name, page symbols A to Z by name, as of)} for each index list of the market with enough listed
    companies (MIN_INDEX)."""
    cos = companies(region)
    with _dir_lock:
        hit = _dir_index.get(region)
        if hit and hit[1] is cos and time.time() - hit[0] < DIR_FRESH:
            return hit[2]
    known = listing(region)
    out = {}
    for slug, name, kind, key in INDEX_LISTS.get(region, []):
        try:
            syms, as_of = _members(region, kind, key)
        except Exception as ex:                  # storage down, or no list yet: the index is left out for now
            print("stock directory: members of", name, str(ex)[:120])
            continue
        pages = {}
        for s in syms:
            hit_ = find(region, str(s))
            if hit_ and listable(region, hit_[0], known):
                pages[hit_[0]] = _fold(label_of(region, hit_[0], hit_[1]))
        if len(pages) >= MIN_INDEX:
            out[slug] = (name, sorted(pages, key=lambda s: (pages[s], s)), as_of)
    with _dir_lock:
        _dir_index[region] = (time.time(), cos, out)
    return out


def letter_path(region: str, letter: str, page: int = 1) -> str:
    return f"/stocks/{region.lower()}/browse/{letter.lower()}" + (f"/{page}" if page > 1 else "")


def index_path(region: str, slug: str, page: int = 1) -> str:
    return f"/stocks/{region.lower()}/index/{slug}" + (f"/{page}" if page > 1 else "")


def pages_of(n: int) -> int:
    return max(1, -(-n // DIR_PAGE))


def _crumbs(trail: list[tuple[str, str]]) -> tuple[str, str]:
    """(the visible breadcrumb line, its BreadcrumbList JSON-LD) for [(name, address)]; the last is the page itself."""
    site = settings.PUBLIC_SITE_URL
    line = " › ".join(f'<a href="{e(a)}">{e(n)}</a>' for n, a in trail[:-1]) + (" › " if len(trail) > 1 else "") + e(trail[-1][0])
    ld = _ld({"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": i + 1, "name": n, "item": a if a.startswith("http") else site + a}
        for i, (n, a) in enumerate([("StratLab", site + "/")] + trail)]})
    return f'<p class="small muted" data-crumbs>{line}</p>', ld


def _pager(base, pages: int, page: int) -> str:
    """Links to the other pages of a long list: `base(n)` is page n's address."""
    if pages <= 1:
        return ""
    items = "".join((f'<a href="{e(base(n))}" aria-current="page">{n}</a>' if n == page
                     else f'<a href="{e(base(n))}">{n}</a>') for n in range(1, pages + 1))
    return f'<nav class="links" aria-label="Pages" data-pager>{items}</nav>'


def index_links(region: str) -> str:
    """The market's index lists as links, or nothing when the app holds no members for any."""
    idx = index_lists(region)
    if not idx:
        return ""
    where = "India" if region == "IN" else "US"
    return (f'<h2>{where} companies by index</h2><nav class="links" aria-label="{where} index lists" data-by-index>'
            + "".join(f'<a href="{index_path(region, slug)}">{e(name)}</a>' for slug, (name, _s, _d) in idx.items()) + "</nav>")


def _az_cols(n: int, widest: int) -> int:
    """How many columns of 44px letter boxes (at most `widest`) leave the last row of `n` letters nearest to full: 26 letters are 7, 7, 7 and 5 in
    seven columns, not 6, 6, 6, 6 and 2 in six (VR7-003). The wider is taken when two fill the same."""
    return max(range(max(2, widest - 2), widest + 1), key=lambda c: ((n % c or c) / c, c)) if n > widest else max(n, 1)


def _az_style(n: int) -> str:
    """The columns as two attributes (the page's body carries no inline style): data-c7 for a screen 375px and wider, data-c6 for a narrower one."""
    return f' data-c7="{_az_cols(n, 7)}" data-c6="{_az_cols(n, 6)}"'


def az_nav(region: str) -> str:
    """The market's A-Z letters (those with companies) and its index lists, as links: on /stocks, the exchange pages and the
    letter pages."""
    r = region.lower()
    d = directory(region)
    where = "India" if region == "IN" else "US"
    letters = "".join(f'<a href="{letter_path(region, L)}">{"0–9" if L == OTHER else L}</a>' for L in [*LETTERS, OTHER] if d["count"].get(L))
    n = sum(1 for L in [*LETTERS, OTHER] if d["count"].get(L))
    out = f'<h2>Browse {where} companies A to Z</h2><nav class="links" aria-label="{where} companies by first letter" data-az{_az_style(n)}>{letters}</nav>' if letters else ""
    return out + index_links(region)


def _span_text(region: str, syms: list[str]) -> str:
    """"from Sagar Cements Ltd to Szabo Ltd" for a list of page symbols, or "" for none."""
    if not syms:
        return ""
    first, last = (label_of(region, syms[0]), label_of(region, syms[-1]))
    return f"from {first} to {last}" if first != last else f"({first})"


def letter_page(region: str, letter: str, page: int = 1) -> str | None:
    """/stocks/in/browse/s and its later pages: the companies whose name starts with the letter, A to Z, each linked. None
    for a letter with no companies or a page past the last."""
    letter = letter.upper()
    d = directory(region)
    n = d["count"].get(letter, 0)
    if not n or page < 1 or page > pages_of(n):
        return None
    site = settings.PUBLIC_SITE_URL
    where = "India" if region == "IN" else "US"
    # VR6-021: "listed in US (the US)": the US has no exchange to name in brackets (India's two are named)
    place = "India (NSE and BSE)" if region == "IN" else "the US"
    show = "0–9" if letter == OTHER else letter
    syms = d["order"][d["start"][letter]:d["start"][letter] + n][(page - 1) * DIR_PAGE:page * DIR_PAGE]
    pages = pages_of(n)
    of = f", page {page} of {pages}" if pages > 1 else ""
    what = "starting with a digit or a symbol" if letter == OTHER else f"starting with {letter}"
    title = f"{where} listed companies {what}{of} · StratLab"
    desc = (f"{n:,} companies listed in {place} {what}{of}, {_span_text(region, syms)}. Each links to its price, "
            "results and filings.")
    if len(desc) > DESCRIPTION_MAX:
        desc = f"{n:,} companies listed in {where} {what}{of}. Each links to its price, results and filings."
    canonical = site + letter_path(region, letter, page)
    crumbs, ld = _crumbs([("Companies", "/stocks"), (where, f"/stocks/{region.lower()}"), (f"A to Z: {show}", letter_path(region, letter, page))])
    body = (f"{crumbs}<h1>{where} companies {e(what)}</h1>"
            f'<p class="muted">{n:,} companies listed in {place} {e(what)}{e(of)}, A to Z by name. Each links to its price, '
            "reported results and recent filings. Facts, not advice.</p>"
            f'<nav class="links" aria-label="Letters" data-az{_az_style(sum(1 for L in [*LETTERS, OTHER] if d["count"].get(L)))}>' + "".join(
                f'<a href="{letter_path(region, L)}"' + (' aria-current="page"' if L == letter else "") + f'>{"0–9" if L == OTHER else L}</a>'
                for L in [*LETTERS, OTHER] if d["count"].get(L)) + "</nav>"
            + _dir_list(region, syms)
            + _pager(lambda k: letter_path(region, letter, k), pages, page)
            + index_links(region))
    return _page(_head(title, desc, canonical, ld), None, body)


def _dir_list(region: str, syms: list[str]) -> str:
    """A directory page's companies: name, then the symbol, one link each, in the order given."""
    cos = companies(region)
    tidy = (lambda s: label_of(region, s, cos.get(s)))
    # VR5-009: a list of bare symbols (no company name to show) went one per row on a phone, a 58px box each for "AARTIIND": two across
    short = " data-short" if syms and all(len(tidy(s)) <= 14 for s in syms) else ""
    return f'<ul class="dir" data-companies{short}>' + "".join(
        f'<li><a href="{e(path(region, s))}">{e(tidy(s))}</a>' + ("" if tidy(s) == s else f' <span class="muted small">{e(s)}</span>') + "</li>"
        for s in syms) + "</ul>"


def index_page_of_list(region: str, slug: str, page: int = 1) -> str | None:
    """/stocks/in/index/nifty-50: the index's members that have a page, A to Z by name. None when the app holds no list for it."""
    got = index_lists(region).get(slug)
    if not got:
        return None
    name, syms, as_of = got
    pages = pages_of(len(syms))
    if page < 1 or page > pages:
        return None
    site = settings.PUBLIC_SITE_URL
    where = "India" if region == "IN" else "US"
    of = f", page {page} of {pages}" if pages > 1 else ""
    when = f" The list is as of {as_of}." if as_of else ""
    shown = syms[(page - 1) * DIR_PAGE:page * DIR_PAGE]
    title = f"{name} companies: all {len(syms):,} members{of} · StratLab"
    desc = f"The {len(syms):,} companies in the {name} that have a StratLab page{of}, A to Z, each with its price, results and filings."
    canonical = site + index_path(region, slug, page)
    crumbs, ld = _crumbs([("Companies", "/stocks"), (where, f"/stocks/{region.lower()}"), (name, index_path(region, slug, page))])
    body = (f"{crumbs}<h1>{e(name)} companies</h1>"
            f'<p class="muted">The {len(syms):,} members of the {e(name)} that have a page here, A to Z by name.{e(when)} '
            "An index's members change from time to time. Each links to its price, reported results and recent filings. Facts, not advice.</p>"
            + _dir_list(region, shown) + _pager(lambda k: index_path(region, slug, k), pages, page)
            + az_nav(region))
    return _page(_head(title, desc, canonical, ld), None, body)


def dir_not_found(region: str | None) -> str:
    """A directory address with no list behind it: a letter with no companies, a page past the last, an index the app holds no
    members for. Kept out of search results."""
    site = settings.PUBLIC_SITE_URL
    body = ('<h1>No such list</h1><p class="muted">There is no list of companies at this address. Find the company by its name, '
            f'or <a href="/stocks{"/" + region.lower() if region else ""}">browse the companies</a>.</p>' + _find_form(region))
    return _page(_head("List not found · StratLab", "No such list of companies.", site + "/stocks", robots="noindex,follow"), None, body)


def indexes_of(region: str, symbol: str) -> list[tuple[str, str]]:
    """[(address part, name)] of the index lists a company is in."""
    return [(slug, name) for slug, (name, syms, _d) in index_lists(region).items() if symbol in syms]


def browse_block(region: str, symbol: str) -> str:
    """A company page's way on to the rest of the directory: the companies before and after it A to Z, its letter's list and the
    index lists it is in. Empty for a company that isn't in the directory (a page kept out of search results)."""
    d = directory(region)
    i = d["pos"].get(symbol)
    if i is None:
        return ""
    order = d["order"]
    letter = letter_of(label_of(region, symbol))
    start = d["start"].get(letter)
    where = "India" if region == "IN" else "US"
    links = []
    if i > 0:
        links.append(f'<a rel="prev" href="{e(path(region, order[i - 1]))}">← {e(label_of(region, order[i - 1]))}</a>')
    if i + 1 < len(order):
        links.append(f'<a rel="next" href="{e(path(region, order[i + 1]))}">{e(label_of(region, order[i + 1]))} →</a>')
    if start is not None:
        links.append(f'<a href="{e(letter_path(region, letter, (i - start) // DIR_PAGE + 1))}">'
                     f'All {where} companies starting with {"a digit or symbol" if letter == OTHER else e(letter)}</a>')
    links += [f'<a href="{e(index_path(region, slug))}">{e(name)} companies</a>' for slug, name in indexes_of(region, symbol)]
    links.append(f'<a href="/stocks/{region.lower()}">All {where} companies</a>')
    return ('<h2>Browse companies</h2><p class="small muted" data-browse>The companies before and after this one, A to Z, '
            "and the lists it is in.</p>" f'<nav class="links" aria-label="Browse companies">{"".join(links)}</nav>')


# ---------- robots and sitemaps ----------
# SEO-tool and scraper crawlers bring no visitors and walk every company page (the hosting's monthly request
# allowance): they're asked to stay out. Search engines are welcome. Kept the same as frontend/public/robots.txt.
SCRAPER_BOTS = ("AhrefsBot", "SemrushBot", "MJ12bot", "DotBot", "DataForSeoBot", "BLEXBot", "serpstatbot", "Barkrowler",
                "PetalBot", "Bytespider")
SCRAPERS = "".join(f"User-agent: {b}\n" for b in SCRAPER_BOTS) + "Disallow: /\n\n"


def robots() -> str:
    site = settings.PUBLIC_SITE_URL
    return SCRAPERS + f"User-agent: *\nAllow: /\nAllow: /blog\nDisallow: /admin\nDisallow: /account\n\nSitemap: {site}/sitemap.xml\n"


def sitemap_index() -> str:
    site = settings.PUBLIC_SITE_URL
    names = ["pages", "blog", "directory"] + [f"stocks-{r}-{i + 1}" for r, R in REGIONS.items() for i in range(max(1, -(-len(companies(R)) // CHUNK)))]
    def day(n: str) -> str:
        if n == "pages":
            return max(d for _, d in site_pages.PAGES)
        if n == "blog":                   # the day the newest post changed (BLOG-1); none when the posts can't be read
            try:
                return blog.latest_day()
            except Exception as ex:
                print("sitemap: the blog's day couldn't be read:", str(ex)[:120])
                return ""
        if n == "directory":              # the A-Z and index lists change with the companies list (SEO-1)
            return max((str(((_setting(f"stocks:list:{R}") or {}).get("at")) or "")[:10] for R in REGIONS.values()), default="")
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
    strategies), "blog" (the blog's lists and posts) or "stocks-in-1", "stocks-us-2"… (companies whose page has facts to show; the day is when the list of
    listed companies was last refreshed); None for any other name."""
    site = settings.PUBLIC_SITE_URL
    if name == "pages":
        # /stocks is the API's own list of company pages, not one of the site's pages: it changes with the companies list
        listed = max((str(((_setting(f"stocks:list:{R}") or {}).get("at")) or "")[:10] for R in REGIONS.values()), default="")
        return _urlset([(site + p, d) for p, d in site_pages.PAGES] + [(site + p, listed or max(d for _, d in site_pages.PAGES)) for p in ["/stocks"] + [f"/stocks/{r}" for r in REGIONS]]
                       + [(site + p, d) for p, d in site_pages.library_pages()])
    if name == "blog":                   # the blog's lists and posts (BLOG-1), each with the day it last changed
        return _urlset(blog.sitemap_urls(site))
    if name == "directory":              # the A-Z and index lists that link every company page (SEO-1)
        return _urlset(directory_urls())
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


def directory_urls() -> list[tuple[str, str | None]]:
    """(address, day) of every directory page: each market's letter pages (and their later pages) and index lists. The day is
    that of the companies list, which these pages change with."""
    site = settings.PUBLIC_SITE_URL
    out = []
    for r, R in REGIONS.items():
        day = str(((_setting(f"stocks:list:{R}") or {}).get("at")) or "")[:10] or None
        d = directory(R)
        for L in [*LETTERS, OTHER]:
            out += [(site + letter_path(R, L, k), day) for k in range(1, pages_of(d["count"].get(L, 0)) + 1) if d["count"].get(L)]
        for slug, (_name, syms, _as_of) in index_lists(R).items():
            out += [(site + index_path(R, slug, k), day) for k in range(1, pages_of(len(syms)) + 1)]
    return out


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
