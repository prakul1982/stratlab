"""One research hub over all the sources: search, company profiles, charts, quotes,
index levels and headlines, in the same shape for India and the US.

Every call is made in parallel and every source can fail on its own: the profile
carries a `sources` list saying which ones answered, so the page can show what's
missing instead of breaking."""
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from .. import name_search
from ..kite_service import KiteService
from .finnhub import Finnhub
from .net import NotFound, SourceError, num
from .news import GoogleNews, Wikipedia, mentions, plain_headline
from .screener import Screener, clean_profile, summary as scr_summary
from .yahoo import Yahoo
from ..kite_service import ist_date

US_EXCHANGES = {"NMS", "NYQ", "NGM", "NCM", "ASE", "PCX", "BTS", "NASDAQ", "NYSE", "NYSEArca"}
INDICES = {
    "IN": [("NIFTY 50", "^NSEI"), ("SENSEX", "^BSESN"), ("NIFTY BANK", "^NSEBANK")],
    "US": [("S&P 500", "^GSPC"), ("NASDAQ", "^IXIC"), ("DOW JONES", "^DJI")],
}
# India's indices on the broker's feed, as its quotes name them: the live level and the day's candle come from there, the
# way the option chains read NIFTY's spot (R7T-003: the other source's SENSEX stayed at the 8 Oct close after 9 Oct's open)
KITE_INDEX = {"^NSEI": "NSE:NIFTY 50", "^BSESN": "BSE:SENSEX", "^NSEBANK": "NSE:NIFTY BANK"}
_pool = ThreadPoolExecutor(max_workers=16, thread_name_prefix="intel")


def market_open(region: str, now: datetime | None = None) -> bool:
    """Whether a market is trading now (its hours, on one of its trading days)."""
    from zoneinfo import ZoneInfo
    from ..data.calendar import is_trading_day
    from ..data.markets import BY_ID
    m = BY_ID.get(region)
    if not m or not m.get("hours"):
        return False
    local = (now or datetime.now(timezone.utc)).astimezone(ZoneInfo(m["tz"]))
    return is_trading_day(region, local.date()) and m["hours"]["open"] <= local.strftime("%H:%M") < m["hours"]["close"]


def market_today(region: str, now: datetime | None = None) -> str:
    """The market's own calendar day now (India's or New York's), as an ISO date."""
    from zoneinfo import ZoneInfo
    from ..data.markets import BY_ID
    tz = (BY_ID.get(region) or {}).get("tz") or "UTC"
    return (now or datetime.now(timezone.utc)).astimezone(ZoneInfo(tz)).date().isoformat()


def session_day(at, region: str) -> str | None:
    """The trading day (in the market's own zone) a quote's time falls on; None without a readable time."""
    from zoneinfo import ZoneInfo
    from ..data.markets import BY_ID
    try:
        t = datetime.fromisoformat(str(at).replace("Z", "+00:00")) if at else None
    except ValueError:
        return None
    if t is None:
        return None
    tz = ZoneInfo((BY_ID.get(region) or {}).get("tz") or "UTC")
    return (t if t.tzinfo else t.replace(tzinfo=tz)).astimezone(tz).date().isoformat()


def index_level(name: str, q: dict, region: str, now: datetime | None = None) -> dict:
    """One index's tile: its level and change with the session they are of. `stale`: the market is open today and this
    quote is still a previous session's, so its change is that session's and is never shown as today's (R7T-003: SENSEX
    "−1.44% today" after 9 Oct's open was 8 Oct's move); `live`: the quote is today's while the market trades."""
    day = session_day(q.get("at"), region)
    is_open = market_open(region, now)
    today = market_today(region, now)
    hi = q.get("high52")
    price = q["price"]
    if hi and q.get("high") and q["high"] > hi:
        hi = q["high"]                          # today's high above the year's: the year's high is today's
    return {"name": name, "price": price, "change_pct": q.get("change_pct"), "high52": hi, "low52": q.get("low52"),
            "from_high_pct": ((price / hi - 1) * 100) if hi else None, "at": q.get("at"), "day": day,
            "live": bool(is_open and day == today), "stale": bool(is_open and (day is None or day < today))}


def _fy(label: str) -> str:
    m = re.search(r"(\d{4})", str(label))
    return f"FY{m.group(1)[2:]}" if m else str(label)


def _series(cols: list, vals: list, n: int = 8) -> list[dict]:
    out = [{"y": _fy(c), "v": v} for c, v in zip(cols, vals) if v is not None and "TTM" not in str(c)]
    return out[-n:]


def inr(v: float) -> str:
    """Indian digit grouping: 1905432 -> 19,05,432."""
    s = f"{abs(v):.0f}"
    head, tail = s[:-3], s[-3:]
    while len(head) > 2:
        tail = head[-2:] + "," + tail
        head = head[:-2]
    return ("-" if v < 0 else "") + (head + "," + tail if head else tail)


def _item(label, value, unit="x"):
    """One Key numbers figure. A percentage the source gives in whole numbers ("-12%": its compounded growth rates
    and price returns) says so with `dp` 0, so it is never shown as a precise "-12.0%"."""
    out = {"label": label, "value": num(value), "unit": unit}
    if unit in ("%", "%±") and isinstance(value, str) and re.fullmatch(r"\s*[-+−]?\d+\s*%?\s*", value):
        out["dp"] = 0
    return out


def _groups(*groups) -> list[dict]:
    out = []
    for title, items in groups:
        items = [i for i in items if i["value"] is not None]
        if items:
            out.append({"title": title, "items": items})
    return out


def at_live_price(s: dict, live: float | None) -> dict:
    """The fundamentals summary re-priced at the live price, so the market value, P/E, P/B and dividend yield on a
    company's page agree with the price at the top of it. The fundamentals source prices its ratios once a day; the
    reported numbers behind them (earnings, book value, dividend) don't move with the price, so each ratio scales with it."""
    old = s.get("price")
    if not live or live <= 0 or not old or old <= 0:
        return s
    k = live / old
    out = dict(s, price=live)
    if s.get("pe") is not None:
        out["pe"] = s["pe"] * k
    if s.get("book_value"):
        out["pb"] = live / s["book_value"]
    if s.get("div_yield") is not None:
        out["div_yield"] = s["div_yield"] / k
    if s.get("market_cap_cr") is not None:
        out["market_cap_cr"] = s["market_cap_cr"] * k
    return out


def with_dividend_yield(c: dict, divs: list[dict], today: str) -> dict:
    """The page's dividend yield as the dividends a share with an ex-date in the last twelve months (the corporate
    actions on the same page) over the price, saying what it includes: a special dividend is counted and named, with
    the yield without it beside (TCS, 8 Oct 2026: 3.1% shown beside "Rs111 a share in the last 12 months", the Rs46
    special left out without a word). Without those dividends the source's figure stays, labelled as its own."""
    price = num(((c.get("quote") or {}).get("price")))
    from datetime import date, timedelta
    try:
        year_ago = (date.fromisoformat(today) - timedelta(days=365)).isoformat()
    except ValueError:
        return c
    rows = [d for d in divs or [] if d.get("kind") == "dividend" and num(d.get("amount")) and year_ago <= str(d.get("ex_date")) < today]
    if not rows or not price:
        what = "From the last reported year's dividends" if c.get("region", "IN") == "IN" else "From the company's stated yearly dividend"
        note = what if any(i["label"] == "Div yield" for g in c.get("metrics") or [] for i in g["items"]) else None
        return _set_metric(c, "Div yield", None, note) if note else c
    cur = "₹" if c.get("region", "IN") == "IN" else "$"
    total = sum(num(d["amount"]) for d in rows)
    special = sum(num(d["amount"]) for d in rows if d.get("sub") == "special")
    y = round(total / price * 100, 2)
    amount = f"{total:,.2f}" if cur == "₹" else f"{total:,.3f}".rstrip("0").rstrip(".") if total < 10 else f"{total:,.2f}"
    note = f"{cur}{amount} a share in the last 12 months".replace(".00 ", " ")
    if special:
        note += f", including a {cur}{special:,.2f} special dividend; {(total - special) / price * 100:.1f}% without it".replace(".00 ", " ")
    if any(d.get("converted") for d in rows):
        note += "; payments missing from the US listing's history are converted from the home listing's at that day's rate"
    out = _set_metric(c, "Div yield", y, note)
    if isinstance(out.get("summary"), dict):
        out["summary"] = {**out["summary"], "div_yield": y}
    return out


def _set_metric(c: dict, label: str, value: float | None, note: str | None) -> dict:
    """A copy of the page with one Key numbers item given a new value (None keeps it) and a note."""
    groups = []
    for g in c.get("metrics") or []:
        items = [{**i, **({"value": value} if value is not None else {}), **({"note": note} if note else {})} if i["label"] == label else i
                 for i in g["items"]]
        groups.append({**g, "items": items})
    return {**c, "metrics": groups}


def reported_growth(scr: dict | None, bars: list[dict] | None) -> dict:
    """Sales and profit compounded over the last 3 and 5 reported years (the deep dive's and the AI read facts' own
    sums), and the price's change over a year of daily candles. Empty for what can't be worked out."""
    out: dict = {}
    if scr:
        try:
            from ..deepdive import numbers
            out.update({k: v for k, v in (numbers(scr).get("growth") or {}).items() if v is not None})
        except Exception:                 # a page that can't be read this way keeps the source's own figures
            pass
    if bars:
        from .key_facts import _year_ago
        then, last = _year_ago(bars), num(bars[-1].get("c"))
        if then and last:
            out["price_1y"] = (last / then - 1) * 100
    return out


US_VENUE = re.compile(r"NASDAQ|NYSE|NEW YORK|AMEX|ARCA|BATS|CBOE|OTC|\bUS\b", re.I)
FOREIGN_TICKER = re.compile(r"\.(MI|L|PA|DE|F|AS|BR|SW|TO|V|AX|HK|T|KS|SS|SZ|NS|BO|MC|LS|VI|ST|OL|CO|HE|IR|SA|MX|JO|TA|SI|KL|BK|JK|NZ|TW)$")   # a home-market ticker (ENI.MI)


def _fx(frm: str, to: str) -> float | None:
    """Units of `to` per unit of `frm`, from the day's stored rates (rupees per unit of each); None when either is
    missing."""
    if frm == to:
        return 1.0
    try:
        from ..pricing import rates
        got = rates()
        a, b = got.get(frm) if frm != "INR" else 1.0, got.get(to) if to != "INR" else 1.0
        return float(a) / float(b) if a and b else None
    except Exception:
        return None


def us_listing(profile: dict, listing: dict | None, metrics: dict, fx=_fx) -> dict:
    """One listing per US symbol: the US one the page's price, chart and dividends are of. A foreign company's US
    ticker (an ADR: Eni's E) has a profile of its home listing (AIM Italia, in euros), so its exchange, currency and
    52-week range come from the US listing instead, its market value is converted at the day's rate (left out without
    one), and `foreign` says the results are in another currency (Eni, 8 Oct 2026: "Last close EUR53.96", the ADR's
    dollars, with a 52-week range of EUR14.54 to EUR25.02 from Milan)."""
    lst = listing or {}
    home = (profile.get("currency") or "USD").upper()
    cur = (lst.get("currency") or "USD").upper()
    foreign = home != cur
    ex = profile.get("exchange")
    if lst.get("exchange") and (foreign or not US_VENUE.search(ex or "")):
        ex = lst["exchange"]
    lo, hi = num(metrics.get("52WeekLow")), num(metrics.get("52WeekHigh"))
    # the listed symbol's own range when the fundamentals' range is another listing's: an ADR's home market, or another
    # class of the same company (R7T-001: BRK-B's page showed Class A's $698,000-$806,102 beside a $511 price)
    own_lo, own_hi, px = num(lst.get("low52")), num(lst.get("high52")), num(lst.get("price"))
    if foreign or lo is None or hi is None or (px and not plausible_range(px, lo, hi) and plausible_range(px, own_lo, own_hi)):
        lo, hi = own_lo, own_hi
    cap = profile.get("marketCapitalization")
    rate = fx(home, cur) if cap else None
    return {"exchange": ex, "currency": cur, "reporting_currency": home, "foreign": foreign,
            "range52": {"low": lo, "high": hi}, "market_cap": cap * 1e6 * rate if cap and rate else None}


def plausible_range(price, low, high) -> bool:
    """Whether a 52-week range can be this share's: the price within a third below its low or half above its high (a
    range from another class of shares, or another listing, is off by far more)."""
    p, lo, hi = num(price), num(low), num(high)
    if not p or p <= 0 or lo is None or hi is None or lo <= 0 or hi < lo:
        return False
    return lo * 0.67 <= p <= hi * 1.5


def with_today_range(c: dict) -> dict:
    """The page's 52-week range checked against its price and taking in today's high and low: a range that can't be this
    share's is left out (R7T-001), and one the day has already traded beyond is widened to the day's high or low, so the
    price never sits below the year's low (R7T-007: RELIANCE "52-wk low ₹1,160.80" with the day's low at ₹1,160.20)."""
    rng, q = c.get("range52") or {}, c.get("quote") or {}
    px, lo, hi = num(q.get("price")), num(rng.get("low")), num(rng.get("high"))
    if lo is None and hi is None:
        return c
    if px and not plausible_range(px, lo, hi):
        return {**c, "range52": {"low": None, "high": None}}
    d_lo, d_hi = num(q.get("low")), num(q.get("high"))
    for v in (d_lo, d_hi, px):
        if v and v > 0:
            lo = v if lo is None else min(lo, v)
            hi = v if hi is None else max(hi, v)
    return {**c, "range52": {"low": lo, "high": hi}}


US_LENDERS = ("bank","banking", "financial services", "insurance", "capital markets", "thrift", "credit", "mortgage", "lending")


def is_lender(scr: dict | None = None, industry: str | None = None) -> bool:
    """A bank, lender or insurer: its reported tables have "Financing Profit" or "Financing Margin" lines (India), or
    its industry says so (the US). EBITDA and debt-to-equity don't describe such a business (R7O-001)."""
    if scr:
        if scr.get("bank"):
            return True
        for table in ("pl", "quarters"):
            if any(str(k).lower().startswith("financing") for k in ((scr.get(table) or {}).get("rows") or {})):
                return True
    low = str(industry or "").lower()
    return bool(low) and any(w in low for w in US_LENDERS)


def class_move_note(rows: list[dict]) -> str | None:
    """A note when two holder classes moved by about the same amount in opposite directions over the year (ICICIBANK,
    Jun 2026: FIIs -13.0 and Public +14.6 points while a depositary bank, 16.03%, appeared among the named holders):
    that is how a holder reclassified from one class to another shows, not buying or selling of that size (R7O-012)."""
    moved = [r for r in rows or [] if isinstance(r.get("change"), (int, float)) and abs(r["change"]) >= 5]
    for i, a in enumerate(moved):
        for b in moved[i + 1:]:
            if (a["change"] > 0) != (b["change"] > 0) and abs(a["change"] + b["change"]) <= max(2.5, 0.2 * abs(a["change"])):
                down, up = (a, b) if a["change"] < 0 else (b, a)
                return (f"{down['label']} {down['change']:+.1f} and {up['label']} {up['change']:+.1f} points almost offset each other. "
                        "That is how a holder moved from one class to the other in the company's filings shows (for example a "
                        "depositary bank holding the shares behind its depositary receipts), not buying or selling of that size. "
                        "The named holders list shows who.").replace("-", "−")
    return None


def us_pe(price, eps_ttm, source_pe):
    """A US company's P/E as the page's price over the page's own EPS TTM, so the two figures on the page agree
    (R6O-008: AAPL "P/E 37.98" beside "EPS TTM $8.72" at $339.37, which is 38.9). Within 1% of each other the
    source's figure stands (the same EPS, a price a few cents apart); without both, the source's P/E."""
    p, e, src = num(price), num(eps_ttm), num(source_pe)
    if p and e and e > 0:
        mine = round(p / e, 2)
        return src if src and abs(src / mine - 1) <= 0.01 else mine
    return source_pe


def insider_view(ins: list[dict], n: int = 8) -> dict | None:
    """The latest insider trades and their net: the net is the sum of exactly the rows shown, so the header and the
    table agree (AAPL, 8 Oct 2026: "Net +2,08,772 shares" over 40 filings above 8 rows that all sold, -1,39,005)."""
    rows = [{"name": t.get("name"), "change": num(t.get("change")), "date": t.get("filingDate") or t.get("transactionDate")}
            for t in ins if num(t.get("change"))][:n]
    if not rows:
        return None
    return {"net": sum(r["change"] for r in rows), "count": len(rows), "rows": rows}


def _public(row: dict) -> dict:
    return {k: v for k, v in row.items() if k != "_t"}


def _yahoo_in(sym: str) -> str:
    """Yahoo's ticker for an Indian stock: NSE symbol.NS, or a BSE code.BO."""
    return f"{sym}.BO" if sym.isdigit() else f"{sym}.NS"


def us_peers(sym: str, listed: list) -> list[str]:
    """Similar US companies: for one of the largest US companies, the others of that size in its sector first (Apple:
    Microsoft, NVIDIA, Broadcom); then the data source's peers in its narrow industry that are in the S&P 500 (a stray
    or delisted ticker is left out); at most 8 (R5O-020: Apple's were only storage and server makers)."""
    from .. import universes
    try:
        rows = {r[0]: r[2] for r in universes.sp500_doc()["rows"]}
    except Exception:
        rows = {}
    big = next((p["symbols"] for p in universes.PRESETS.get("US", []) if p["id"] == "us_mega"), [])
    same_size = [s for s in big if s != sym and sym in big and rows.get(s) and rows.get(s) == rows.get(sym)]
    narrow = [x for x in listed if isinstance(x, str) and x and x != sym and (not rows or x in rows)]
    return list(dict.fromkeys(same_size + narrow))[:8]


class Research:
    def __init__(self, kite: KiteService | None, finnhub=None, yahoo=None, screener=None, news=None, wiki=None):
        self.kite = kite
        self.finnhub = finnhub or Finnhub()
        self.yahoo = yahoo or Yahoo()
        self.screener = screener or Screener()
        self.news = news or GoogleNews()
        self.wiki = wiki or Wikipedia()

    # ---------- helpers ----------
    def _kite(self) -> bool:
        return bool(self.kite and self.kite.ready())

    @staticmethod
    def _run(tasks: dict) -> tuple[dict, list[dict]]:
        """Run {name: (source_name, fn)} in parallel; returns results and a per-source status list."""
        futures = {k: (src, _pool.submit(fn)) for k, (src, fn) in tasks.items()}
        results, status = {}, {}
        for k, (src, f) in futures.items():
            try:
                results[k] = f.result(timeout=25)
                status.setdefault(src, {"source": src, "ok": True, "error": None})
            except SourceError as e:
                results[k] = None
                status[src] = {"source": src, "ok": False, "error": str(e)}
            except Exception as e:  # a parsing surprise in one source mustn't sink the page
                results[k] = None
                status[src] = {"source": src, "ok": False, "error": f"Unexpected error ({e.__class__.__name__})."}
        return results, list(status.values())

    # ---------- search ----------
    # the app's own lists of companies: (q, region) -> [{symbol, name, exchange, match}], best first. Set by main.
    local_search = None

    def search(self, q: str, region: str) -> list[dict]:
        """Up to 10 companies for what's typed: a symbol, a name or a short name ("HDFC Bank", "Infy", "Apple"). India
        from the exchanges' lists (the broker's, else the companies stored); the US from the list of US companies,
        topped up by the search sources and ranked the same way (name_search)."""
        q = q.strip()
        if len(q) < 1:
            return []
        if region == "IN":
            if self._kite():
                rows = [r for r in self.kite.search(q, allow_fno=False, limit=15) if r["type"] == "EQ"]
                return [{"symbol": r["symbol"], "name": r["name"], "exchange": r["exchange"], "region": "IN"} for r in rows[:10]]
            local = self._local(q, "IN")
            if local:
                return [_public(r) for r in local]
            rows = [x for x in self.yahoo.search(q) if str(x["symbol"]).endswith((".NS", ".BO"))
                    and x.get("quoteType") == "EQUITY"]
            return [{"symbol": x["symbol"].rsplit(".", 1)[0], "name": x.get("longname") or x.get("shortname"),
                     "exchange": "NSE" if x["symbol"].endswith(".NS") else "BSE", "region": "IN"} for x in rows[:10]]
        local = self._local(q, "US")
        if local and local[0]["_t"] <= name_search.NAME:      # the name or symbol itself: no need to ask anyone else
            return [_public(r) for r in local]
        found = []
        if self.finnhub.ready():
            try:
                rows = [x for x in self.finnhub.search(q) if "." not in x.get("symbol", "")
                        and x.get("type") in ("Common Stock", "ETP", "ADR", "")]
                found = [{"symbol": x["symbol"], "name": x.get("description") or x["symbol"], "exchange": "US",
                          "region": "US"} for x in rows]
            except SourceError:
                pass
        if not found:
            try:
                rows = [x for x in self.yahoo.search(q) if x.get("exchange") in US_EXCHANGES
                        and x.get("quoteType") in ("EQUITY", "ETF")]
            except SourceError:
                if not local:
                    raise
                rows = []
            found = [{"symbol": x["symbol"], "name": x.get("longname") or x.get("shortname") or x["symbol"],
                      "exchange": x.get("exchDisp") or "US", "region": "US"} for x in rows]
        mine = {r["symbol"] for r in local}
        found = [{**r, "_t": name_search.tier_of(q, r["symbol"], r["name"], "US")} for r in found if r["symbol"] not in mine]
        both = sorted(local + found, key=lambda r: r["_t"])        # stable: each source's own order among equals
        return [_public(r) for r in both[:10]]

    def _local(self, q: str, region: str) -> list[dict]:
        """The app's own list's answers, each with its group in `_t`; none when the list isn't available."""
        if not self.local_search:
            return []
        try:
            got = self.local_search(q, region) or []
        except Exception as e:                  # the list is down: the search sources still answer
            print("research search: own list unavailable,", region, e)
            return []
        return [{"symbol": r["symbol"], "name": r.get("name") or r["symbol"], "exchange": r.get("exchange") or region,
                 "region": region, "_t": r.get("match", name_search.WORDS)} for r in got[:10]]

    # ---------- quotes ----------
    def quotes(self, region: str, symbols: list[str]) -> dict[str, dict]:
        symbols = [s.strip().upper() for s in symbols if s.strip()][:24]
        if not symbols:
            return {}
        if region == "IN" and self._kite():
            try:
                return self.kite.quote(symbols)
            except Exception:
                pass
        out = {}

        def one(sym):
            # Yahoo first: peers and watchlists would use up Finnhub's 60 calls a minute
            try:
                return self.yahoo.meta(_yahoo_in(sym) if region == "IN" else sym)
            except SourceError:
                if region == "US" and self.finnhub.ready():
                    q = self.finnhub.quote(sym)
                    if q.get("c"):
                        return {"price": q.get("c"), "change": q.get("d"), "change_pct": q.get("dp"),
                                "prev_close": q.get("pc"), "high": q.get("h"), "low": q.get("l"), "open": q.get("o")}
                raise
        futures = {s: _pool.submit(one, s) for s in symbols}
        for s, f in futures.items():
            try:
                out[s] = f.result(timeout=20)
            except Exception:
                out[s] = None
        return out

    # ---------- charts ----------
    def chart(self, region: str, symbol: str, rng: str = "1y", tf: str = "1d", before: str = "") -> dict:
        """Candles for the price chart: a range of daily ones, a recent window of intraday ones, or (with
        `before`) the page of older candles before a time. `more` says whether older candles exist."""
        from ..chart_data import older, parse_before, window
        symbol = symbol.strip().upper()
        until = parse_before(before)
        # while the market trades, today's daily candle is still forming: read again within a minute, not a copy kept
        # for hours (R7T-006: the 1Y chart had no 9 Oct candle 17 minutes after the open, while 1M and 6M did)
        forming = tf == "1d" and until is None and market_open(region)
        if region == "IN" and self._kite():
            inst = self._kite_index(symbol) if symbol in KITE_INDEX else self.kite.equity(symbol) or self.kite.by_symbol(symbol)
            if inst:
                from ..data import KITE_MAX_DAYS
                days, more = window(tf, rng, until, KITE_MAX_DAYS.get(tf))
                try:
                    bars = older(self.kite.history(inst["token"], tf, days, ttl=60 if forming else None), until)
                    return {"currency": "INR", "source": "Kite", "tf": tf, "more": more,
                            "candles": self._with_today(region, symbol, bars) if forming else bars}
                except Exception:
                    pass
        from .yahoo import INTERVAL
        days, more = window(tf, rng, until, INTERVAL[tf][1])
        ysym = _yahoo_in(symbol) if region == "IN" and not symbol.startswith("^") else symbol
        c = self.yahoo.chart(ysym, tf, days, ttl=60 if forming else None)
        bars = older(c["candles"], until)
        return {"currency": c["meta"].get("currency") or ("INR" if region == "IN" else "USD"),
                "source": "Yahoo Finance", "tf": tf, "more": more, "candles": self._with_today(region, symbol, bars) if forming else bars}

    def _kite_index(self, symbol: str) -> dict | None:
        """An Indian index on the broker's feed ({"token"}), by the chart symbol the pages use (^NSEI, ^BSESN)."""
        key = KITE_INDEX.get(symbol)
        if not key:
            return None
        ex, name = key.split(":", 1)
        try:
            row = self.kite.by_symbol(name, ex)
            if row:
                return row
            tok = self.kite.index_token(key)
        except Exception:
            return None
        return {"token": tok} if tok else None

    def _live_quote(self, region: str, symbol: str) -> dict | None:
        """The quote of a symbol now: an Indian index from the broker's feed, else the page's own quotes."""
        try:
            if region == "IN" and symbol in KITE_INDEX and self._kite():
                return self.kite.index_quotes([KITE_INDEX[symbol]]).get(KITE_INDEX[symbol])
            if symbol.startswith("^"):
                return self.yahoo.meta(symbol)
            return (self.quotes(region, [symbol]) or {}).get(symbol)
        except Exception:
            return None

    def _with_today(self, region: str, symbol: str, bars: list[dict]) -> list[dict]:
        """Daily candles with today's, from the quote, when the source's last one is a previous session's while the market
        trades (R7T-003: SENSEX's chart had no 9 Oct candle at 09:39 IST)."""
        today = market_today(region)
        if bars and str(bars[-1].get("t", ""))[:10] >= today:
            return bars
        q = self._live_quote(region, symbol)
        px = num((q or {}).get("price"))
        if not px or session_day((q or {}).get("at"), region) != today:
            return bars
        from zoneinfo import ZoneInfo
        from ..data.markets import BY_ID
        t = datetime.fromisoformat(today).replace(tzinfo=ZoneInfo(BY_ID[region]["tz"])).isoformat()
        o = num(q.get("open")) or px
        hi, lo = max(x for x in (num(q.get("high")), o, px) if x), min(x for x in (num(q.get("low")), o, px) if x)
        return [*bars, {"t": t, "o": o, "h": hi, "l": lo, "c": px, "v": num(q.get("volume")) or 0.0}]

    # ---------- market pulse ----------
    def indices(self, region: str, now: datetime | None = None) -> list[dict]:
        """The market's index levels, each with the session it is of (see index_level). India's levels and day moves are
        the broker's live ones, the way NIFTY's spot is read for the option chains; the other source gives the 52-week
        range, and the level itself when the broker is offline."""
        out = []
        futures = [(name, sym, _pool.submit(self.yahoo.meta, sym)) for name, sym in INDICES.get(region, [])]
        live: dict = {}
        if region == "IN" and self._kite():
            try:
                live = self.kite.index_quotes([KITE_INDEX[s] for _, s in INDICES["IN"]])
            except Exception as e:
                print("index levels: broker quotes unavailable,", str(e)[:120])
        for name, sym, f in futures:
            try:
                m = f.result(timeout=20)
            except Exception:
                m = {}
            k = live.get(KITE_INDEX.get(sym, "")) or {}
            if k.get("price") is not None:
                m = {**m, **{x: k.get(x) for x in ("price", "change_pct", "high", "low", "at")}}
            if m.get("price") is None:
                continue
            out.append(index_level(name, m, region, now))
        return out

    def sector_moves(self, region: str) -> dict | None:
        """How the market's main sector indices (India: the NSE sector indices the rotation page shows first; the US: the
        S&P 500 sector funds) moved on the day, counted from StratLab's own quotes: {"up", "down", "unchanged", "of",
        "rows"}. None when they can't be read. The market mood may say how many sectors rose or fell only from this
        (R8B-004: "as all sectoral indices turned green" while NIFTY OIL & GAS closed lower)."""
        from ..rotation import CORE_IN, SECTORS, US_NAMES
        rows = []
        try:
            if region == "IN":
                if not self._kite():
                    return None
                names = sorted(CORE_IN | {"NIFTY OIL AND GAS", "NIFTY HEALTHCARE", "NIFTY CONSR DURBL", "NIFTY PVT BANK"})
                got = self.kite.index_quotes([f"NSE:{n}" for n in names])
                rows = [{"name": n, "change_pct": (got.get(f"NSE:{n}") or {}).get("change_pct")} for n in names]
            elif region == "US":
                syms = SECTORS["US"]["members"]
                got = self.quotes("US", syms)
                rows = [{"name": US_NAMES.get(s, s), "change_pct": (got.get(s) or {}).get("change_pct")} for s in syms]
        except Exception as e:
            print("sector moves unavailable:", region, str(e)[:120])
            return None
        rows = [{**r, "change_pct": round(float(r["change_pct"]), 2)} for r in rows if r.get("change_pct") is not None]
        if len(rows) < 5:
            return None
        return {"up": sum(1 for r in rows if r["change_pct"] > 0), "down": sum(1 for r in rows if r["change_pct"] < 0),
                "unchanged": sum(1 for r in rows if r["change_pct"] == 0), "of": len(rows), "rows": rows}

    def headlines(self, region: str, focus: str = "") -> list[dict]:
        """The market's headlines for Pulse and the briefs: stories only, never a site's own title or a third party's
        buying worded as advice ("We're buying the dip in a stock…", R7O-005)."""
        if region == "US" and self.finnhub.ready() and not focus:
            try:
                return [{"headline": n.get("headline"), "url": n.get("url"), "source": n.get("source"),
                         "at": datetime.fromtimestamp(n["datetime"], timezone.utc).isoformat() if n.get("datetime") else None}
                        for n in self.finnhub.market_news()[:20] if n.get("headline") and plain_headline(n["headline"])][:14]
            except SourceError:
                pass
        q = (focus + " " if focus else "") + ("Nifty Sensex India stock market" if region == "IN" else "US stock market")
        return [h for h in self.news.search(q, region, limit=20) if plain_headline(h.get("headline"))][:14]

    # ---------- company profiles ----------
    def company(self, region: str, symbol: str) -> dict:
        symbol = symbol.strip().upper()
        return self._company_in(symbol) if region == "IN" else self._company_us(symbol)

    def _company_us(self, sym: str) -> dict:
        fh = self.finnhub
        p = fh.profile(sym)
        if not p.get("name"):
            raise NotFound("Finnhub", f"No US company found for {sym}. Use the exact ticker, like NVDA or AAPL.")
        r, sources = self._run({
            "listing": ("Yahoo Finance", lambda: self.yahoo.meta(sym)),
            "q": ("Finnhub", lambda: fh.quote(sym)), "m": ("Finnhub", lambda: fh.metrics(sym)),
            "news": ("Finnhub", lambda: fh.news(sym)), "peers": ("Finnhub", lambda: fh.peers(sym)),
            "rec": ("Finnhub", lambda: fh.recommendation(sym)), "earn": ("Finnhub", lambda: fh.earnings(sym)),
            "fin": ("Finnhub", lambda: fh.financials(sym)), "ins": ("Finnhub", lambda: fh.insider(sym)),
            "cal": ("Finnhub", lambda: fh.earnings_calendar(sym)), "wiki": ("Wikipedia", lambda: self.wiki.company(p["name"])),
        })
        q, M = r["q"] or {}, r["m"] or {}
        # the yearly results are in the currency the company reports in (Eni: euros), not the US listing's dollars
        trend = self._us_trend(r["fin"], (p.get("currency") or "USD").upper())
        earn = [e for e in (r["earn"] or []) if e.get("actual") is not None and e.get("estimate") is not None][:4][::-1]
        ins = (r["ins"] or {}).get("data") or []
        today = ist_date().isoformat()
        nxt = sorted([e for e in (r["cal"] or []) if e.get("date", "") >= today], key=lambda e: e["date"])
        rec = (r["rec"] or [None])[0]
        one = us_listing(p, r.get("listing"), M)
        lender = is_lender(None, p.get("finnhubIndustry"))
        return {
            "region": "US", "symbol": sym, "name": p.get("name"), "exchange": one["exchange"],
            "currency": one["currency"], "reporting_currency": one["reporting_currency"],
            "logo": p.get("logo") or None, "website": p.get("weburl") or None,
            "facts": [{"label": k, "value": v} for k, v in (("Industry", p.get("finnhubIndustry")), ("Country", p.get("country")),
                                                            ("Listed since", p.get("ipo")), ("Exchange", one["exchange"]),
                                                            ("Results reported in", one["reporting_currency"] if one["foreign"] else None)) if v],
            "industry": p.get("finnhubIndustry"), "bank": lender,
            "market_cap": one["market_cap"],
            "quote": {"price": q.get("c"), "change": q.get("d"), "change_pct": q.get("dp"), "open": q.get("o"),
                      "high": q.get("h"), "low": q.get("l"), "prev_close": q.get("pc"),
                      # the time of the last trade (the close, out of hours), for the page's "as of", never the moment of asking
                      "at": datetime.fromtimestamp(q["t"], timezone.utc).isoformat(timespec="seconds") if isinstance(q.get("t"), (int, float)) and q["t"] > 0 else None,
                      } if q.get("c") else None,
            "range52": one["range52"],
            "margins": {"gross": num(M.get("grossMarginTTM")), "operating": num(M.get("operatingMarginTTM")),
                        "net": num(M.get("netProfitMarginTTM"))},
            "metrics": _groups(
                ("Valuation", [_item("P/E", us_pe(q.get("c"), None if one["foreign"] else M.get("epsTTM"), M.get("peTTM"))), _item("Fwd P/E", M.get("forwardPE")),
                               _item("P/S", M.get("psTTM")), _item("P/B", M.get("pb")),
                               _item("EV/EBITDA", None if lender else M.get("evEbitdaTTM")), _item("EV/FCF", M.get("currentEv/freeCashFlowTTM")),
                               _item("PEG (fwd)", M.get("forwardPEG"))]),
                ("Profitability", [_item("Gross margin", M.get("grossMarginTTM"), "%"),
                                   _item("Operating margin", M.get("operatingMarginTTM"), "%"),
                                   _item("Net margin", M.get("netProfitMarginTTM"), "%"), _item("ROE", M.get("roeTTM"), "%"),
                                   _item("ROA", M.get("roaTTM"), "%")]),
                ("Growth", [_item("Revenue YoY", M.get("revenueGrowthTTMYoy"), "%±"),
                            _item("EPS YoY", M.get("epsGrowthTTMYoy"), "%±"),
                            _item("Revenue 3Y", M.get("revenueGrowth3Y"), "%±"),
                            _item("Revenue 5Y", M.get("revenueGrowth5Y"), "%±"), _item("EPS 5Y", M.get("epsGrowth5Y"), "%±")]),
                ("Financial health", [_item("Current ratio", M.get("currentRatioQuarterly")),
                                      _item("LT debt / equity", M.get("longTermDebt/equityQuarterly")),
                                      _item("Interest coverage", M.get("netInterestCoverageTTM")),
                                      _item("Asset turnover", M.get("assetTurnoverTTM"))]),
                # per-share money in the results' currency is per home-market share, not per US share (an ADR can be 2)
                ("Per share and returns", [_item("EPS TTM", None if one["foreign"] else M.get("epsTTM"), "money"), _item("Beta", M.get("beta")),
                                           _item("1Y return", M.get("52WeekPriceReturnDaily"), "%±"),
                                           _item("Div yield", M.get("dividendYieldIndicatedAnnual"), "%"),
                                           _item("Payout ratio", M.get("payoutRatioTTM"), "%")]),
            ),
            "trend": trend,
            "earnings": [{"period": e.get("period"), "actual": e["actual"], "estimate": e["estimate"],
                          "surprise_pct": e.get("surprisePercent") if e.get("surprisePercent") is not None else
                          ((e["actual"] - e["estimate"]) / abs(e["estimate"]) * 100 if e["estimate"] else 0)} for e in earn],
            "next_earnings": {"date": nxt[0]["date"], "eps_estimate": nxt[0].get("epsEstimate")} if nxt else None,
            "analysts": {k: rec.get(k, 0) for k in ("strongBuy", "buy", "hold", "sell", "strongSell")} | {"period": rec.get("period")} if rec else None,
            "insider": insider_view(ins),
            # US listings only (ENI.MI is in euros), the same-size names in its sector first
            "peers": us_peers(sym, [x for x in (r["peers"] or []) if isinstance(x, str) and not FOREIGN_TICKER.search(x)]),
            # the company's own news: a headline (or its summary) that names it, not the day's market stories the feed
            # files under every big ticker (R5O-020)
            "news": [{"headline": n.get("headline"), "url": n.get("url"), "source": n.get("source"),
                      "at": datetime.fromtimestamp(n["datetime"], timezone.utc).isoformat() if n.get("datetime") else None}
                     for n in (r["news"] or []) if n.get("headline") and plain_headline(n["headline"])
                     and (mentions(p["name"], sym, n["headline"]) or mentions(p["name"], sym, str(n.get("summary") or "")[:400]))][:8],
            "about": {"wiki": r["wiki"], "profile": None},
            "sources": sources, "links": [{"label": "Yahoo Finance", "url": f"https://finance.yahoo.com/quote/{sym}"}],
            "testable": True, "instrument_id": f"US:{sym}",
        }

    @staticmethod
    def _us_trend(rep, unit: str = "USD") -> dict | None:
        by_year = {}
        for f in (rep or {}).get("data") or []:
            y = str(f.get("year") or str(f.get("endDate", ""))[:4])
            if not y or y in by_year:
                continue
            rev = ni = None
            for it in ((f.get("report") or {}).get("ic") or []):
                lab, con = str(it.get("label", "")).lower(), str(it.get("concept", ""))
                if rev is None and (lab in ("revenue", "revenues", "total revenue", "net sales", "total revenues")
                                    or con.endswith("Revenues") or "RevenueFromContractWithCustomer" in con):
                    rev = num(it.get("value"))
                if ni is None and (lab in ("net income", "net income loss", "net income (loss)")
                                   or con in ("us-gaap_NetIncomeLoss", "us-gaap_ProfitLoss")):
                    ni = num(it.get("value"))
            by_year[y] = (rev, ni)
        years = sorted(by_year)[-6:]
        rev = [{"y": f"FY{y[2:]}", "v": by_year[y][0]} for y in years if by_year[y][0] is not None]
        ni = [{"y": f"FY{y[2:]}", "v": by_year[y][1]} for y in years if by_year[y][1] is not None]
        return {"unit": unit, "revenue": rev, "profit": ni, "revenue_label": "Revenue", "profit_label": "Net income"} \
            if len(rev) > 1 or len(ni) > 1 else None

    def _company_in(self, sym: str) -> dict:
        kite_ok = self._kite()
        inst = (self.kite.equity(sym) or self.kite.by_symbol(sym)) if kite_ok else None
        if kite_ok and not inst:
            # the exchanges' own lists have every listed stock: a symbol that isn't there (bar a known rename) is a typo,
            # answered now instead of spending the company-data source's per-minute allowance on it
            renamed = [h for h in self.kite.search(sym, False, 3) if not h.get("fno") and h.get("type") == "EQ"
                       and sym in getattr(self.kite, "ALIASES", {})]
            if not renamed:
                raise NotFound("Research", f"Couldn't find {sym}. Use the NSE symbol (like RELIANCE or TCS), or the BSE code for a company listed only on BSE.")
            sym, inst = renamed[0]["symbol"], renamed[0]
        # listed only on BSE: the company page is under its six-digit BSE code
        code = inst.get("bse_code") if inst and inst["exchange"] == "BSE" else (sym if sym.isdigit() and len(sym) == 6 else None)
        if inst and code:
            sym = inst["symbol"]
        exchange = "BSE" if code else "NSE"
        tasks = {"scr": ("Screener.in", lambda: self.screener.company(code or sym))}
        if inst:
            tasks["kq"] = ("Kite", lambda: self.kite.quote([sym]).get(sym))
            tasks["k1y"] = ("Kite", lambda: self.kite.history(inst["token"], "1d", 370))
        else:
            tasks["y"] = ("Yahoo Finance", lambda: self.yahoo.meta(_yahoo_in(code or sym)))
        r, sources = self._run(tasks)
        scr = r.get("scr")
        if not scr and not r.get("kq") and not r.get("y"):
            raise SourceError("Research", f"Couldn't find {sym}. Use the NSE symbol (like RELIANCE or TCS), or the BSE code for a company listed only on BSE.")
        s = scr_summary(scr) if scr else {}
        name = (scr or {}).get("name") or (inst or {}).get("name") or (r.get("y") or {}).get("name") or sym
        clean = re.sub(r"\s+(Ltd|Limited)\.?$", "", name, flags=re.I).strip()
        r2, sources2 = self._run({
            "news": ("Google News", lambda: self.news.search(f"{clean} share price", "IN")),
            "wiki": ("Wikipedia", lambda: self.wiki.company(clean)),
        })
        quote, lo52, hi52 = None, s.get("low52"), s.get("high52")
        if r.get("kq"):
            quote = r["kq"]
        elif r.get("y"):
            y = r["y"]
            quote = {k: y.get(k) for k in ("price", "change", "change_pct", "high", "low", "prev_close", "volume")}
            lo52, hi52 = y.get("low52") or lo52, y.get("high52") or hi52
        if r.get("k1y"):
            bars = r["k1y"][-252:]
            if bars:
                lo52, hi52 = min(b["l"] for b in bars), max(b["h"] for b in bars)
        if quote is None and s.get("price"):
            quote = {"price": s["price"]}
        s = at_live_price(s, num((quote or {}).get("price")))
        g = (scr or {}).get("growth", {})
        gs, gp, gpr = g.get("sales", {}), g.get("profit", {}), g.get("price", {})
        # one value per figure on the page: growth compounded over the reported years (as the AI read's facts and the
        # deep dive work it out), and the price's year from the same daily candles as the chart
        mine = reported_growth(scr, r.get("k1y"))
        gs = {**gs, **{k: v for k, v in (("3 Years", mine.get("sales_cagr_3y")), ("5 Years", mine.get("sales_cagr_5y"))) if v is not None}}
        gp = {**gp, **{k: v for k, v in (("3 Years", mine.get("profit_cagr_3y")), ("5 Years", mine.get("profit_cagr_5y"))) if v is not None}}
        if mine.get("price_1y") is not None:
            gpr = {**gpr, "1 Year": mine["price_1y"]}
        pl = (scr or {}).get("pl")
        trend = None
        if pl:
            cols = pl["cols"]
            sales = next((v for k, v in pl["rows"].items() if k.lower().startswith(("sales", "revenue"))), [])
            profit = next((v for k, v in pl["rows"].items() if k.lower().startswith("net profit")), [])
            trend = {"unit": "₹ Cr", "revenue": _series(cols, sales), "profit": _series(cols, profit),
                     "revenue_label": "Sales", "profit_label": "Net profit"}
        qt = (scr or {}).get("quarters")
        quarters = None
        if qt:
            def row(*prefixes):
                return next((v for k, v in qt["rows"].items() if k.lower().startswith(prefixes)), [])
            quarters = {"cols": qt["cols"][-8:], "sales": row("sales", "revenue")[-8:],
                        "profit": row("net profit")[-8:], "opm": row("opm", "financing margin")[-8:]}
        sh = (scr or {}).get("shareholding")
        holding = None
        if sh and sh["cols"]:
            holding = {"as_of": sh["cols"][-1], "rows": []}
            for k in ("Promoters", "FIIs", "DIIs", "Government", "Public"):
                vals = next((v for lab, v in sh["rows"].items() if lab.lower().startswith(k.lower())), None)
                if vals and vals[-1] is not None:
                    prev = vals[-5] if len(vals) >= 5 else vals[0]
                    holding["rows"].append({"label": k, "value": vals[-1],
                                            "change": (vals[-1] - prev) if prev is not None else None})
            holding["note"] = class_move_note(holding["rows"])
        lender = is_lender(scr)
        return {
            "region": "IN", "symbol": sym, "name": name, "exchange": exchange, "currency": "INR", "logo": None,
            "website": (scr or {}).get("website"), "industry": None, "bse_code": code,
            "facts": [{"label": "Listed", "value": f"BSE only · {code}" if code else f"NSE · {sym}"}] + ([{"label": "Market cap", "value": f"₹{inr(s['market_cap_cr'])} Cr"}] if s.get("market_cap_cr") else []),
            "market_cap": s["market_cap_cr"] * 1e7 if s.get("market_cap_cr") else None,
            "quote": quote, "range52": {"low": lo52, "high": hi52},
            "margins": None,
            "metrics": _groups(
                ("Valuation", [_item("P/E", s.get("pe")), _item("P/B", s.get("pb")),
                               _item("Div yield", s.get("div_yield"), "%"), _item("Book value", s.get("book_value"), "money"),
                               _item("Face value", s.get("face_value"), "money")]),
                # a bank's or lender's "operating profit" is after interest paid, so an EBITDA margin (ICICIBANK -20.0%)
                # and a debt-to-equity mean nothing for it: left out, as on its public page (R7O-001)
                ("Returns and quality", [_item("ROCE", s.get("roce"), "%"), _item("ROE", s.get("roe"), "%"),
                                         _item("Net margin", s.get("net_margin"), "%"),
                                         _item("EBITDA margin", None if lender else s.get("opm"), "%"),
                                         _item("Debt", s.get("debt_cr"), "cr"), _item("Debt / equity", None if lender else s.get("debt_equity"))]),
                ("Sales growth", [_item("Latest YoY", s.get("sales_yoy"), "%±"), _item("3Y CAGR", gs.get("3 Years"), "%±"),
                                  _item("5Y CAGR", gs.get("5 Years"), "%±"), _item("10Y CAGR", gs.get("10 Years"), "%±")]),
                ("Profit growth", [_item("Latest YoY", s.get("profit_yoy"), "%±"), _item("3Y CAGR", gp.get("3 Years"), "%±"),
                                   _item("5Y CAGR", gp.get("5 Years"), "%±"), _item("10Y CAGR", gp.get("10 Years"), "%±")]),
                ("Stock price CAGR", [_item("1Y", gpr.get("1 Year"), "%±"), _item("3Y", gpr.get("3 Years"), "%±"),
                                      _item("5Y", gpr.get("5 Years"), "%±"), _item("10Y", gpr.get("10 Years"), "%±")]),
            ),
            "trend": trend, "quarters": quarters, "shareholding": holding,
            # no "strengths and concerns" from the fundamentals source: its lines judge ("poor sales growth of 10.2%")
            # and work figures out again at their own price ("7.20 times its book value" beside a P/B of 7.01)
            "pros": [], "cons": [],
            "earnings": [], "next_earnings": None, "analysts": None, "insider": None, "peers": [],
            # a name search also brings the market's and other companies' headlines: only the ones about this company
            "news": [n for n in (r2.get("news") or []) if mentions(clean, sym, n.get("headline") or "") and plain_headline(n.get("headline"))],
            "about": {"wiki": r2.get("wiki"), "profile": clean_profile((scr or {}).get("about"))},
            "sources": sources + sources2,
            "links": [{"label": "Screener.in", "url": (scr or {}).get("url") or f"https://www.screener.in/company/{code or sym}/"}]
                     + ([{"label": "BSE", "url": f"https://www.bseindia.com/stock-share-price/x/x/{code}/"}] if code else []),
            "summary": s, "numbers_at": (scr or {}).get("fetched_at"), "bank": lender,
            "testable": bool(inst) or not kite_ok,
            "instrument_id": inst["id"] if inst else None,
        }
