"""Prices for Market Watch (MW-1): the last price and the day's change of any instrument on a list, and a small line of
recent closes for its row.

Every read goes through what the app already has, and is shared: an Indian or US stock is the company pages' own quote
(the broker's batched read, shared for 15 seconds by quote_share), an index is the market pulse's level, and any other
instrument (crypto, forex, commodities, other countries' stocks, MCX and currency futures) is read from its market's
provider once and kept 15 seconds for everyone (quote_share again), so five people watching bitcoin cost one request. The
row's line of closes is kept half an hour. Both caches are bounded.

Facts only: a price, what it changed by since the previous close, and when it was read."""
import threading
import time
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from . import quote_share
from .intel.net import TTLCache

MAX_IDS = 24                 # instruments in one read, like the company pages' quotes
READ_WITHIN = 8.0            # seconds a read may take: a symbol not back by then is left out and asked again next time
SPARK_POINTS = 30
SPARK_KEEP = 30 * 60
PUBLIC_KEEP = 10.0

# what a visitor who isn't signed in sees: one fixed board, so the public endpoint can't be used to read anything else
PUBLIC_BOARD = [
    ("IN:^NSEI", "NIFTY 50"), ("IN:^BSESN", "SENSEX"), ("IN:^NSEBANK", "NIFTY BANK"), ("US:^GSPC", "S&P 500"), ("US:^IXIC", "NASDAQ"),
    ("US:^DJI", "DOW JONES"), ("CRYPTO:BTC-USD", "Bitcoin"), ("CRYPTO:ETH-USD", "Ethereum"), ("FX:EURUSD=X", "EUR/USD"),
    ("CMDTY:GC=F", "Gold"), ("CMDTY:CL=F", "WTI crude oil"),
]

_pool = ThreadPoolExecutor(max_workers=6, thread_name_prefix="watch-quotes")
_sparks = TTLCache(max_items=3000, max_bytes=6 * 1024 * 1024)
_public = TTLCache(max_items=4, max_bytes=1024 * 1024)
_lock = threading.Lock()
_feed = object()             # the key quote_share keeps registry quotes under (one feed for all of them)


def _m():
    """The main module, for the research hub (company quotes, index levels, company candles) and the markets registry.
    Imported late (it imports this file) and read each time, so a test that swaps them in is followed."""
    from . import main
    return main


def split(ids: list[str]) -> tuple[dict[str, list[str]], list[tuple[str, str]], list[str]]:
    """The ids as three kinds of read: stocks by region, indices as (region, symbol), and registry instruments."""
    stocks: dict[str, list[str]] = {}
    indices: list[tuple[str, str]] = []
    registry: list[str] = []
    for i in dict.fromkeys(ids):
        market, _, sym = i.partition(":")
        if not sym:
            continue
        if market in ("IN", "US"):
            (indices.append((market, sym)) if sym.startswith("^") else stocks.setdefault(market, []).append(sym))
        else:
            registry.append(i)
    return stocks, indices, registry


def _row(q: dict | None, currency: str | None = None) -> dict | None:
    if not q or q.get("price") is None:
        return None
    return {"price": q.get("price"), "change": q.get("change"), "change_pct": q.get("change_pct"), "prev_close": q.get("prev_close"),
            "at": q.get("at"), "currency": currency or q.get("currency"), "stale": bool(q.get("stale"))}


def delayed(market: str) -> bool:
    """Whether a market's prices here can be behind the market: the broker's (Indian stocks, MCX, currency futures) and the
    crypto exchange's are live, the rest come from the delayed source. India without today's broker login is delayed too."""
    if market == "CRYPTO":
        return False
    if market in ("IN", "MCX", "CDS"):
        try:
            return not _m().kite.ready()
        except Exception:
            return True
    return True


def _index_quotes(items: list[tuple[str, str]]) -> dict[str, dict | None]:
    from .intel.company import INDICES
    out: dict[str, dict | None] = {}
    for region in dict.fromkeys(r for r, _ in items):
        levels, _ = _m().research_hub.indices_now(region, wait=4.0)
        by_name = {lv["name"]: lv for lv in levels or []}
        names = {sym: name for name, sym in INDICES.get(region, [])}
        for r, sym in items:
            lv = by_name.get(names.get(sym, ""))
            if r != region or not lv:
                continue
            price, prev = lv.get("price"), lv.get("prev_close")
            out[f"{r}:{sym}"] = _row({"price": price, "prev_close": prev, "at": lv.get("at"), "change_pct": None if lv.get("stale") else lv.get("change_pct"),
                                      "change": None if lv.get("stale") or price is None or not prev else price - prev, "stale": lv.get("stale")},
                                     "INR" if region == "IN" else "USD")
    return out


def registry_quote(id_: str) -> dict | None:
    """One non-company instrument: its last price and the change since the previous close, from its market's provider."""
    prov, inst = _m().markets.resolve(id_)
    if prov is None or inst is None or not prov.ready():
        return None
    if hasattr(prov, "yahoo"):          # the stock markets, forex and commodities of the delayed source: price, previous close, time
        m = prov.yahoo.meta(inst["token"])
        k = prov._scale(inst, {"currency": m.get("currency")})
        price, prev = m.get("price"), m.get("prev_close")
        if price is None:
            return None
        price, prev = price * k, (prev * k if prev else None)
        return _row({"price": price, "prev_close": prev, "at": m.get("at"), "change": (price - prev) if prev else None,
                     "change_pct": (price / prev - 1) * 100 if prev else None}, inst.get("currency"))
    price = prov.ltp(inst)
    if price is None:
        return None
    zone = ZoneInfo(inst.get("tz") or "UTC")
    today = datetime.now(zone).date().isoformat()
    prev = next((b["c"] for b in reversed(prov.history(inst, "1d", 10)) if str(b["t"])[:10] < today), None)
    return _row({"price": price, "prev_close": prev, "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                 "change": (price - prev) if prev else None, "change_pct": (price / prev - 1) * 100 if prev else None}, inst.get("currency"))


def _registry_batch(missing: list[str]) -> dict[str, dict]:
    futures = {i: _pool.submit(registry_quote, i) for i in missing}
    wait(list(futures.values()), timeout=READ_WITHIN)
    out = {}
    for i, f in futures.items():
        try:
            got = f.result(timeout=0) if f.done() else None
        except Exception:
            got = None
        if got:
            out[i] = got
    return out


def quotes(ids: list[str]) -> dict[str, dict | None]:
    """{id: {"price", "change", "change_pct", "prev_close", "at", "currency", "stale", "delayed"}} for up to MAX_IDS ids; None for
    one that has no price (unknown, or its source did not answer in time). `delayed`: the price can be behind the market."""
    ids = list(dict.fromkeys(ids))[:MAX_IDS]
    stocks, indices, registry = split(ids)
    out: dict[str, dict | None] = {i: None for i in ids}
    jobs = []
    for region, syms in stocks.items():
        jobs.append(("stock", region, _pool.submit(_m().research_hub.quotes, region, syms), syms))
    if indices:
        jobs.append(("index", "", _pool.submit(_index_quotes, indices), None))
    if registry:
        jobs.append(("registry", "", _pool.submit(quote_share.read, _feed, registry, _registry_batch), None))
    wait([j[2] for j in jobs], timeout=READ_WITHIN)
    for kind, region, f, syms in jobs:
        try:
            got = f.result(timeout=0) if f.done() else {}
        except Exception:
            got = {}
        if kind == "stock":
            for s in syms:
                out[f"{region}:{s}"] = _row((got or {}).get(s), "INR" if region == "IN" else "USD")
        else:
            for k, v in (got or {}).items():
                out[k] = v if kind == "index" else _row(v)
    for i, row in out.items():
        if row is not None:
            row["delayed"] = delayed(i.partition(":")[0])
    return out


# ---------- the line of closes in a row ----------
def _closes(id_: str) -> list[float]:
    market, _, sym = id_.partition(":")
    if market in ("IN", "US"):
        bars = _m().research_hub.chart(market, sym, "3m", "1d").get("candles") or []
    else:
        prov, inst = _m().markets.resolve(id_)
        bars = prov.history(inst, "1d", 95) if prov is not None and inst is not None and prov.ready() else []
    closes = [float(b["c"]) for b in bars if b.get("c") is not None]
    if len(closes) > SPARK_POINTS:
        step = len(closes) / SPARK_POINTS
        closes = [closes[min(len(closes) - 1, int(i * step))] for i in range(SPARK_POINTS - 1)] + [closes[-1]]
    return closes


def sparks(ids: list[str]) -> dict[str, list[float]]:
    """{id: recent daily closes, at most SPARK_POINTS, oldest first} for up to MAX_IDS ids, each read once in half an hour
    for everyone. An id whose candles couldn't be read is left out."""
    ids = list(dict.fromkeys(ids))[:MAX_IDS]
    out: dict[str, list[float]] = {}
    todo = []
    for i in ids:
        hit = _sparks.get(i)
        if hit is not None:
            out[i] = hit
        else:
            todo.append(i)
    futures = {i: _pool.submit(_closes, i) for i in todo}
    wait(list(futures.values()), timeout=READ_WITHIN)
    for i, f in futures.items():
        try:
            got = f.result(timeout=0) if f.done() else None
        except Exception:
            got = None
        if got:
            _sparks.set(i, got, SPARK_KEEP)
            out[i] = got
    return out


def public_board() -> list[dict]:
    """The fixed board a visitor sees: each instrument's name, price, day's change and line of closes. One read for every
    visitor, kept PUBLIC_KEEP seconds."""
    hit = _public.get("board")
    if hit is not None:
        return hit
    ids = [i for i, _ in PUBLIC_BOARD]
    q, s = quotes(ids), sparks(ids)
    rows = [{"id": i, "name": n, "market": i.split(":")[0], **(q.get(i) or {}), "spark": s.get(i, [])} for i, n in PUBLIC_BOARD]
    _public.set("board", rows, PUBLIC_KEEP)
    return rows


def forget() -> None:
    _sparks.clear()
    _public.clear()
    with _lock:
        pass
