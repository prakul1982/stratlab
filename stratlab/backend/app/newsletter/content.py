"""The facts each newsletter reports, built from what the research pages already compute: index moves, sector
rotation, the Stage 2 and ST S2 scans, exchange filings, deals and insider trades, and headlines.

Facts only, never a view. Every source is optional: one that fails or is offline just drops its section. Data a
stock needs is fetched once per day and shared, so a hundred readers holding the same stock cost one lookup."""
import json
import re
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from .. import daily_report, db, deals, holdings, rotation, scan, universes
from ..data.calendar import is_trading_day
from ..intel.company import INDICES
from ..intel.net import TTLCache

REGIONS = ("IN", "US")
MAX_STOCKS = 25
HEADLINES = 6
MOVE = {False: 3.0, True: 5.0}       # a price move this big (%, daily or weekly) counts as news on its own
EQUITY = {None, "", "EQ", "ETF"}
CLOSE = {"IN": ("Asia/Kolkata", time(15, 30)), "US": ("America/New_York", time(16, 0))}
_cache = TTLCache(max_items=5000)


def _main():
    """The running app's data sources (imported late: main imports this package)."""
    from .. import main
    return main


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:
        return default


def closed(region: str, day: date, now: datetime | None = None) -> bool:
    """Whether `day`'s session is over in that market. Part of every cache key, so facts gathered during the day (an
    admin preview) are never reused for the issue after the close."""
    tz, at = CLOSE[region]
    local = (now or datetime.now(ZoneInfo(tz))).astimezone(ZoneInfo(tz))
    if region == "IN":
        # India's day is over once its closing auction has matched and derivatives have stopped trading (15:40 since
        # 3 Aug 2026): facts read between 15:30 and then held the stocks' pre-auction prices (R8B-001)
        from ..data import sessions as S
        at = max(at, S.fo_close(day), S.close_known("cas", day))
    return local.date() > day or (local.date() == day and local.time() >= at)


def previous_trading_day(region: str, day: date) -> date:
    d = day - timedelta(days=1)
    for _ in range(10):
        if is_trading_day(region, d):
            return d
        d -= timedelta(days=1)
    return d


def reference_day(region: str, day: date, weekly: bool) -> date:
    """What a change is measured from: the previous trading day, or a week back for the weekly issue."""
    return day - timedelta(days=7) if weekly else previous_trading_day(region, day)


def _pct(now: float | None, then: float | None) -> float | None:
    return round((now / then - 1) * 100, 2) if now and then else None


# ---------- the Market Brief ----------
def index_close(sym: str, day: date, since: str | None = None) -> dict | None:
    """An index's close on `day` and its change from the session before (or from the last close on or before `since`,
    for the week), read from the daily candles: the same numbers whenever the issue is built or rebuilt."""
    back = max(21, (date.today() - day).days + 14)        # far enough back to hold that day and the session before it
    candles = _safe(lambda: _main().research_hub.yahoo.chart(sym, "1d", back, ttl=300)["candles"], []) or []
    upto = [c for c in candles if c["t"][:10] <= day.isoformat()]
    if not upto or (not since and upto[-1]["t"][:10] != day.isoformat()):
        return None                                    # no candle for that day (yet); the week ends at its last close
    before = [c for c in upto if c["t"][:10] <= since] if since else upto[:-1]
    return {"price": round(upto[-1]["c"], 2), "change_pct": _pct(upto[-1]["c"], before[-1]["c"]) if before else None}


def index_moves(region: str, day: date, weekly: bool) -> list[dict]:
    """The main indices: level and change on the day (from the session before), or over the week."""
    since = reference_day(region, day, True).isoformat() if weekly else None
    live = {} if weekly else {r["name"]: r for r in _safe(lambda: _main().research_hub.indices(region), []) or []}
    out = []
    for name, sym in INDICES.get(region, []):
        got, now = index_close(sym, day, since), live.get(name)
        if got is None and now and not weekly:         # the day's candle isn't out yet: the live quote, same measure
            got = {"price": round(now["price"], 2), "change_pct": None if now.get("change_pct") is None else round(now["change_pct"], 2)}
        if got is None:
            continue
        if now and now.get("from_high_pct") is not None:
            got["from_high_pct"] = round(now["from_high_pct"], 1)
        out.append({"name": name, **got})
    return out


def rotation_shifts(region: str, weekly: bool, day: date | None = None) -> list[dict]:
    """Sectors that moved to another quadrant of the rotation page's chart (its weekly candles) since the session
    before (a daily brief) or the week before (a weekly one), as of the brief's day."""
    return [{"sector": r["sector"], "from": r["from"], "to": r["to"]}
            for r in rotation.shifts(_main().markets, region, day.isoformat() if day else None, weekly)]


def stage2_names(region: str, weekly: bool) -> dict:
    """Stocks in the region's broad group that newly match the ST S2 rule, and ones that newly entered Stage 2."""
    group = universes.PRESETS[region][0]
    res = scan.run(_main().markets, region, [{"symbol": s} for s in group["symbols"]])
    window = 5 if weekly else 1

    def row(r):
        return {"symbol": r["symbol"], "name": r.get("name"), "price": round(r["price"], 2),
                "change_pct": None if r.get("chg") is None else round(r["chg"], 2)}
    st_s2 = [row(r) for r in res["rows"] if r["signal"] == "fresh" and r["st_days"] <= window]
    named = {r["symbol"] for r in st_s2}
    stage2 = [row(r) for r in res["rows"] if r["stage"] == 2 and (r.get("stage_days") or 99) <= window and r["symbol"] not in named]
    return {"group": group["name"], "st_s2": st_s2[:12], "stage2": stage2[:12]}


# a Market Brief's headline is about that region's market, an index or its economy (R6O-004: a US brief carried "Former
# German spy chief arrested", "Gen Alpha kids are earning money" and Hollywood's financing)
MARKET_WORDS = {
    "IN": re.compile(r"\b(sensex|nifty|bse|nse|dalal street|stock markets?|stocks?|shares?|equit\w*|markets?|investors?|"
                     r"rupee|rbi|repo|inflation|cpi|gdp|economy|economic|fii|fiis|dii|diis|fpi|fpis|ipo|ipos|sebi|"
                     r"smallcap|midcap|small-cap|mid-cap|crude|bond yields?|m-cap|market cap|lakh crore|trade deficit)\b", re.I),
    "US": re.compile(r"\b(s&p|s&amp;p|dow|nasdaq|wall street|stock markets?|stocks?|shares?|equit\w*|markets?|investors?|"
                     r"fed(?!\s+up)|federal reserve|powell|treasur\w*|yields?|inflation|cpi|pce|jobs report|payrolls|unemployment|gdp|"
                     r"economy|economic|earnings|ipo|ipos|dollar|oil prices?|crude|tariffs?|recession|rate cuts?|rate hikes?)\b", re.I),
}
# a title the source cut off in the middle of a word ("... 7 key factors behind Rs 10 l")
_SHORT_OK = {"a", "an", "in", "on", "of", "to", "up", "by", "at", "is", "it", "as", "or", "and", "the", "for", "not", "off",
             "out", "yet", "now", "day", "pts", "bn", "cr", "mn", "us", "uk", "eu", "rbi", "fed", "ipo", "gdp", "cpi", "pm", "ai", "new"}


def tidy_title(t: str) -> str:
    """A headline as a whole: one cut off mid-word by its source ends at its last whole word, with an ellipsis."""
    t = " ".join(str(t or "").split())
    if len(t) >= 70 and not re.search(r"[.!?\"'’)\]…]$", t):
        last = t.rsplit(" ", 1)[-1]
        if re.fullmatch(r"[a-z]{1,3}", last) and last not in _SHORT_OK:
            return t.rsplit(" ", 1)[0].rstrip(" ,;:-–") + "…"
    return t


def title_key(t: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(t or "").lower()).strip()


def _local_day(iso: str | None, region: str) -> str | None:
    try:
        at = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if at.tzinfo is None:
        return at.date().isoformat()
    return at.astimezone(ZoneInfo(CLOSE[region][0])).date().isoformat()


# not a market story whatever market word it carries (R7O-005: "'I'm getting fed up': voters line up before dawn as
# early voting begins in Ohio")
OFF_TOPIC = re.compile(r"\b(voters?|early voting|ballots?|polling (station|booth)s?|campaign trail|spy chief|arrested|murder|"
                       r"kids|teens?|hollywood|celebrit\w*|weddings?|recipes?|horoscope|cricket|football)\b", re.I)
_MON = {m: i + 1 for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"))}
_TITLE_DATE = re.compile(r"\b(?:(\d{1,2})(?:st|nd|rd|th)?\s+(jan|feb|mar|apr|may|jun|jul|aug|sept?|oct|nov|dec)[a-z]*\.?"
                         r"|(jan|feb|mar|apr|may|jun|jul|aug|sept?|oct|nov|dec)[a-z]*\.?\s+(\d{1,2})(?:st|nd|rd|th)?)(?![\d,])", re.I)
# an index named with a move: "Sensex settles 685 pts higher", "Nifty 50 rises 220 pts", "Dow falls 300 points"
_IDX_WORDS = {"IN": [("NIFTY BANK", r"bank\s*nifty|nifty\s*bank"), ("SENSEX", r"sensex"), ("NIFTY 50", r"nifty(?:\s*50)?(?!\s*bank)")],
              "US": [("S&P 500", r"s&p(?:\s*500)?"), ("NASDAQ", r"nasdaq"), ("DOW JONES", r"\bdow(?:\s+jones)?")]}
_UP = r"(gains?|gained|rises?|rose|rising|soaring|jumps?|jumped|rall(?:y|ies|ied)|surges?|surged|climbs?|climbed|soars?|soared|settles?[^,;]{0,25}higher|ends?[^,;]{0,25}higher|up|higher|advances?|extends? gains)"
_DOWN = r"(falls?|fell|falling|drops?|dropped|tanks?|tanked|slumps?|slumped|crash(?:es|ed|ing)?|sinks?|sinking|sank|plunges?|plunged|slides?|slid|declines?|declined|tumbles?|tumbled|down|lower|sheds?|slips?|slipped|settles?[^,;]{0,25}lower|ends?[^,;]{0,25}lower)"


def title_dates(title: str, year: int) -> list[str]:
    """The days a headline names in its own words ("Stock Market Highlights, Sept 28", "Oct 6:"), in `year`."""
    out = []
    for m in _TITLE_DATE.finditer(title or ""):
        d, mon = (m.group(1), m.group(2)) if m.group(1) else (m.group(4), m.group(3))
        if mon.lower() == "may" and not mon.startswith("May"):
            continue                                  # "markets may 3x", not the month
        try:
            out.append(date(year, _MON[mon[:3].lower()], int(d)).isoformat())
        except (ValueError, KeyError):
            continue
    return out


def contradicts(title: str, region: str, indices: list[dict] | None) -> bool:
    """A headline whose index move disagrees with the brief's own close: the other way ("Sensex settles 685 pts higher"
    in a brief where it closed 0.59% lower), or by a number of points far from the day's. Such a headline is from
    another day or an earlier part of the session, not the day the brief reports."""
    if not indices:
        return False
    by = {i["name"].upper(): i for i in indices if i.get("name") and i.get("change_pct") is not None and i.get("price")}
    for name, rx in _IDX_WORDS.get(region, []):
        i = by.get(name)
        if not i:
            continue
        m = re.search(r"\b(?:" + rx + r")\b[^,;:|]{0,40}?\b" + "(?:" + _UP + "|" + _DOWN + r")\b", title, re.I)
        if not m:
            continue
        said = m.group(0)
        up = bool(re.search(r"\b" + _UP + r"\b", said, re.I)) and not re.search(r"\b" + _DOWN + r"\b", said, re.I)
        down = bool(re.search(r"\b" + _DOWN + r"\b", said, re.I)) and not up
        ch = float(i["change_pct"])
        if (up and ch < -0.05) or (down and ch > 0.05):
            return True
        pts = re.search(r"\b(?:" + rx + r")\b[^,;:|]{0,40}?\b([\d,]{2,6})\s*(?:pts|points)\b", title, re.I)
        if pts:
            try:
                n = float(pts.group(1).replace(",", ""))
            except ValueError:
                continue
            p = float(i["price"])
            actual = abs(p - p / (1 + ch / 100))
            if abs(n - actual) > max(60.0, 0.35 * actual):
                return True
    # the market as a whole: "India's stock market is sinking" in a brief where every index rose (6 Oct 2026, +0.98%)
    m = re.search(r"\b(stock markets?|markets?|stocks|shares|equities|dalal street|wall street)\b[^,;:|]{0,30}?\b(?:" + _UP + "|" + _DOWN + r")\b",
                  title, re.I)
    if m and by:
        said = m.group(0)
        up = bool(re.search(r"\b" + _UP + r"\b", said, re.I)) and not re.search(r"\b" + _DOWN + r"\b", said, re.I)
        down = bool(re.search(r"\b" + _DOWN + r"\b", said, re.I)) and not up
        moves = [float(i["change_pct"]) for i in by.values()]
        if (up and all(c < -0.3 for c in moves)) or (down and all(c > 0.3 for c in moves)):
            return True
    return False


def headline_ok(region: str, title: str, frm: str | None = None, to: str | None = None, indices: list[dict] | None = None) -> bool:
    """A headline a Market Brief may carry: a story about the region's market (not a site's own title, a third party's
    trades worded as advice, or politics that only mentions the Fed), naming no day outside the brief's, and not
    contradicting the brief's own index moves (R6O-004, R7O-005)."""
    from ..intel.news import plain_headline
    if not title or not MARKET_WORDS[region].search(title) or OFF_TOPIC.search(title) or not plain_headline(title):
        return False
    if frm and to:
        year = int(to[:4])
        if any(not (frm <= d <= to) for d in title_dates(title, year)):
            return False
    return not contradicts(title, region, indices)


def pick_headlines(region: str, rows: list[dict], frm: str, to: str, seen: set[str] | None = None, n: int = HEADLINES,
                   indices: list[dict] | None = None) -> list[dict]:
    """The brief's headlines (R6O-004, R7O-005): stories about the region's market, an index or its economy, never
    advice-style or a site's title; dated within the brief's day (from `frm`, the week's start for a weekly one, to
    `to`) in the market's own time zone, so an undated one is left out; naming no other day and agreeing with the
    brief's index moves; each title once and not one an earlier brief already carried (`seen`); never cut mid-word."""
    out, keys = [], set(seen or ())
    dated = frm > "0000-00-00" or to < "9999-99-99"
    for h in rows or []:
        title = tidy_title(h.get("headline"))
        if not headline_ok(region, title, frm if dated else None, to if dated else None, indices):
            continue
        day = _local_day(h.get("at"), region)
        if dated and (not day or not (frm <= day <= to)):
            continue
        k = title_key(title)
        if k in keys:
            continue
        keys.add(k)
        out.append({"headline": title, "url": h.get("url"), "at": h.get("at")})
    return out[:n]


def earlier_titles(region: str, day: date) -> set[str]:
    """The headline titles the region's daily briefs of the last few days carried, so a story isn't repeated."""
    try:
        from .job import ids, load
    except ImportError:
        return set()
    out: set[str] = set()
    for iid in ids("market", region)[:10]:
        issue = load(iid) or {}
        # the week's brief too: a story it already carried is older than this day (R7O-005: the 1 Oct "Sensex drops 571
        # points" in the 3 Oct weekly and again in the 7 Oct daily)
        if not (day - timedelta(days=7 if issue.get("weekly") else 4)).isoformat() <= str(issue.get("day") or "") < day.isoformat():
            continue
        for s in issue.get("sections") or []:
            if s.get("title") == "Headlines":
                out |= {title_key(i.get("text")) for i in s.get("items") or []}
    return out


def market_headlines(region: str, day: date | None = None, weekly: bool = False, indices: list[dict] | None = None) -> list[dict]:
    rows = [h for h in _main().research_hub.headlines(region) if h.get("headline")]
    if day is None:
        return pick_headlines(region, rows, "0000-00-00", "9999-99-99")
    frm = reference_day(region, day, True).isoformat() if weekly else day.isoformat()
    return pick_headlines(region, rows, frm, day.isoformat(), set() if weekly else _safe(lambda: earlier_titles(region, day), set()) or set(),
                          indices=None if weekly else indices)


def market_facts(region: str, day: date, weekly: bool = False) -> dict:
    """Everything the Market Brief reports for one region on one day (or the week to that day). Built once and shared."""
    key = ("market", region, day.isoformat(), weekly, closed(region, day))
    hit = _cache.get(key)
    if hit is not None:
        return hit
    facts = {"kind": "market", "region": region, "day": day.isoformat(), "weekly": weekly,
             "since": reference_day(region, day, weekly).isoformat()}
    for name, fn in (("indices", lambda: index_moves(region, day, weekly)), ("rotation", lambda: rotation_shifts(region, weekly, day)),
                     ("scan", lambda: stage2_names(region, weekly)),
                     ("headlines", lambda: market_headlines(region, day, weekly, facts.get("indices")))):
        got = _safe(fn)
        if got and (name != "scan" or got["st_s2"] or got["stage2"]):
            facts[name] = got
    if any(k in facts for k in ("indices", "rotation", "scan", "headlines")):
        _cache.set(key, facts, 6 * 3600)
    return facts


# ---------- My Stocks ----------
def _add(out: list, seen: set, region, symbol):
    region, symbol = str(region or "").upper(), str(symbol or "").strip().upper()
    if region in REGIONS and symbol and (region, symbol) not in seen and len(out) < MAX_STOCKS:
        seen.add((region, symbol))
        out.append((region, symbol))


def _instrument(out: list, seen: set, inst):
    if isinstance(inst, dict) and inst.get("type") in EQUITY:
        _add(out, seen, inst.get("market"), inst.get("symbol"))


def my_stocks(uid: str) -> list[tuple[str, str]]:
    """(region, symbol) for the user's watchlist, holdings, notebook instruments and running paper sessions, up to 25."""
    out, seen = [], set()
    try:
        items = json.loads(db.get_setting(f"watchlist:{uid}") or "{}").get("items") or []
    except (ValueError, TypeError, AttributeError):
        items = []
    for i in items:
        if isinstance(i, dict):
            _add(out, seen, i.get("region"), i.get("symbol"))
    for sym in _safe(lambda: holdings.symbols(uid), []) or []:     # holdings count like watchlist names (Indian stocks)
        _add(out, seen, "IN", sym)
    for nb in _safe(lambda: db.list_notebook_rows(uid), []) or []:
        _instrument(out, seen, nb.get("instrument"))
    for s in _safe(lambda: _main().manager.user_running(uid), []) or []:
        _instrument(out, seen, getattr(s, "inst", None))
        for m in getattr(s, "members", None) or []:
            _instrument(out, seen, getattr(m, "inst", None))
    return out


def _symbol_data(region: str, sym: str, day: date) -> dict:
    """One stock's daily candles, filings (India) and recent headlines: fetched once a day for every reader."""
    key = ("stock", region, sym, day.isoformat(), closed(region, day))
    hit = _cache.get(key)
    if hit is not None:
        return hit
    m = _main()

    def bars():
        ids, _ = universes.resolve(m.markets, region, [{"symbol": sym}])
        return scan._bars(m.markets, ids[0]) if ids else None
    data = {"bars": _safe(bars),
            "filings": _safe(lambda: m.filings_feed.announcements(sym, 30)) if region == "IN" else None,
            "news": _safe(lambda: m.research_hub.news.search(f"{sym} share price" if region == "IN" else f"{sym} stock", region, limit=6), [])}
    _cache.set(key, data, 12 * 3600)
    return data


def stock_row(region: str, sym: str, day: date, weekly: bool, since: str) -> dict | None:
    """What changed for one stock since `since` (an ISO date): price, stage, a fresh ST S2 signal, red or amber
    filings and a couple of headlines. None when there's no price data."""
    data = _symbol_data(region, sym, day)
    bars = data["bars"]
    if not bars:
        return None
    ref = reference_day(region, day, weekly).isoformat()
    now = scan.analyse(bars)
    before_bars = [b for b in bars if str(b["t"])[:10] <= ref]
    before = scan.analyse(before_bars) if before_bars else None
    if not now:
        return None
    change = _pct(now["price"], before_bars[-1]["c"] if before_bars else None)
    flags = [{"label": i["label"], "severity": i["severity"], "subject": i["subject"], "at": i["at"], "url": i.get("url")}
             for i in data["filings"] or [] if i["severity"] in ("red", "amber") and i["at"] > since][:4]
    news = [{"headline": n["headline"], "url": n.get("url"), "at": n.get("at")} for n in data["news"] or []
            if n.get("headline") and (not n.get("at") or str(n["at"])[:10] >= since[:10])][:2]
    trades = [{"text": deals.describe(d), "url": d.get("url"), "filed": d["filed"]}
              for d in (_safe(lambda: deals.recent_for(sym, since)) or [] if region == "IN" else [])][:4]
    surv = _safe(lambda: surveillance_lines(sym, since)) if region == "IN" else None
    stage_before = before["stage"] if before else None
    signal = now["signal"] == "fresh" and now["st_days"] <= (5 if weekly else 1)
    stage_moved = now["stage"] is not None and stage_before is not None and now["stage"] != stage_before
    changed = bool(stage_moved or signal or flags or trades or (surv or {}).get("changes") or (change is not None and abs(change) >= MOVE[weekly]))
    return {"symbol": sym, "region": region, "price": round(now["price"], 2), "change_pct": change, "stage": now["stage"],
            "stage_before": stage_before, "stage_changed": stage_moved, "st_s2": signal, "filings": flags, "deals": trades, "surveillance": surv, "headlines": news,
            "changed": changed}


def surveillance_lines(sym: str, since: str) -> dict | None:
    """The stock's exchange surveillance news since `since`: the lists it entered, left or moved stage on (with the
    list's date), and the lists it is on now. None when there is neither."""
    from .. import surveillance
    changes = [{"text": surveillance.change_text(c), "day": c.get("day")} for c in surveillance.changes_for(sym, since)][-4:]
    now = [f["label"] for f in surveillance.flags_for(sym)]
    return {"changes": changes, "now": now} if changes or now else None


def paper_lines(uid: str, day: date) -> list[dict]:
    """The user's running paper sessions: today's closed trades and the result since each started."""
    out = []
    for s in _safe(lambda: _main().manager.user_running(uid), []) or []:
        r = _safe(lambda: daily_report.summarise(s, day.isoformat()))
        if not r:
            continue
        total = r["equity"] - r["capital"]
        out.append({"name": r["name"], "currency": r["currency"], "closed": r["closed"], "pnl": round(r["pnl"], 2),
                    "total": round(total, 2), "total_pct": round(total / r["capital"] * 100, 2) if r["capital"] else None})
    return out


def results_week(uid: str, day: date, weekly: bool, since: str) -> list[dict]:
    """The user's stocks with results in the seven days from the issue's day (the week ahead, for Saturday's issue),
    from the stored results calendar, and ones whose results were filed since `since`."""
    from .. import results
    start = day + timedelta(days=1) if weekly else day
    end = start + timedelta(days=6)
    out = []
    for region in REGIONS:
        syms = {s for r, s in my_stocks(uid) if r == region}
        if not syms:
            continue
        for r in _safe(lambda: results.between(region, day - timedelta(days=results.OUT_DAYS + (5 if weekly else 0)), end, syms), []) or []:
            filed = (r.get("out") or {}).get("at")
            if r["date"] >= start.isoformat() or (filed and str(filed) > since):
                out.append({k: r.get(k) for k in ("symbol", "region", "date", "purpose", "when", "out")})
    return sorted(out, key=lambda r: (r["date"], r["symbol"]))


def actions_week(uid: str, day: date, weekly: bool) -> list[dict]:
    """The user's stocks with an ex-date (dividend, bonus, split, buyback, rights) in the seven days from the issue's
    day (the week ahead, for Saturday's issue), from the stored corporate-actions calendar."""
    from .. import corp_actions
    start = day + timedelta(days=1) if weekly else day
    out = []
    for region in REGIONS:
        syms = {s for r, s in my_stocks(uid) if r == region}
        if syms:
            out += [{k: r.get(k) for k in ("symbol", "region", "kind", "text", "ex_date", "record_date")}
                    for r in _safe(lambda: corp_actions.between(region, start, start + timedelta(days=6), syms), []) or []]
    return sorted(out, key=lambda r: (r["ex_date"], r["symbol"]))


def stock_facts(uid: str, day: date, weekly: bool = False, since: str | None = None) -> dict:
    """Everything My Stocks reports for one user. `since` is when their last issue went out (ISO); filings are
    counted from then, or from the reference day if that is later. `changed` is False when there is nothing to send."""
    floor = reference_day("IN", day, weekly).isoformat()
    since = max(since or floor, floor)
    rows = [r for r in (_safe(lambda: stock_row(region, sym, day, weekly, since)) for region, sym in my_stocks(uid)) if r]
    moved = [r for r in rows if r["changed"]]
    due = results_week(uid, day, weekly, since)
    # results count as news on their own when they're today or tomorrow (any day of the week ahead, weekly), or filed
    soon = (day + timedelta(days=7 if weekly else 1)).isoformat()
    news = [r for r in due if r.get("out") or r["date"] <= soon]
    acts = actions_week(uid, day, weekly)          # an ex-date counts as news on the same terms as a results date
    news += [r for r in acts if r["ex_date"] <= soon]
    return {"kind": "my_stocks", "uid": uid, "day": day.isoformat(), "weekly": weekly, "since": since,
            "stocks": moved, "unchanged": [r["symbol"] for r in rows if not r["changed"]],
            "results": due, "actions": acts, "paper": paper_lines(uid, day), "changed": bool(moved or news)}
