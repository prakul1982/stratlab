"""Company suggestions while a symbol or name is typed: listed companies in India (NSE, else BSE-only by its code) and
US common stocks, matched on the symbol, the BSE code, the ISIN, a short name ("RIL", "Google") or the name
("HDFC Bank", "apollo hosp"), with room for a typo (name_search).

Each market's list is gathered once (the broker's instrument list, the SEC's list of filers, or the stock pages
already stored when those are offline) and indexed in memory, so a keystroke is a few lookups."""
import re
import threading
import time

from . import name_search

LIMIT = 8
MEMORY = 1800                          # seconds a market's list is kept before it's gathered again
MEMORY_SHORT = 120                     # ...when it came from the fallbacks: the full list may be back soon
MARKETS = ("IN", "US")


def _entry(symbol: str, name: str, exchange: str, market: str, code: str | None = None, ident: str | None = None,
           isin: str | None = None) -> dict:
    """One company as the list keeps it: what's shown, what's filled in when picked (`id`), and what's matched."""
    name = str(name or symbol).strip() or symbol
    return {"symbol": symbol, "id": ident or symbol, "name": name[:120], "exchange": exchange, "market": market,
            "_sym": symbol.upper(), "_code": code or "", "_isin": (isin or "").upper()}


def us_common(ticker: str, listed: set[str]) -> bool:
    """A US company's common shares: not a preferred share (BAC-PL), warrant, right or unit (ACONW, ALFUU beside
    ALFU, XYZ-WT, XYZ-UN). A share class with one letter (BRK-B, BF-A) is common stock and stays."""
    t = ticker.upper()
    if not re.fullmatch(r"[A-Z][A-Z0-9]{0,5}(?:[-.][A-Z]{1,3})?", t):
        return False
    if "-" in t or "." in t:
        cls = re.split(r"[-.]", t, maxsplit=1)[1]
        return len(cls) == 1 and cls not in "PWUR"
    return not (len(t) == 5 and t[-1] in "WUR" and t[:4] in listed)


def index(rows: list[dict], market: str | None = None, boost: set | None = None) -> name_search.NameIndex:
    """The rows (from _entry) indexed by symbol, BSE code, ISIN, name and the market's short names."""
    return name_search.NameIndex(rows, symbol=lambda r: r["_sym"], name=lambda r: r["name"],
                                 codes=lambda r: (r["_code"], r["_isin"], r["id"]), boost=boost,
                                 aliases=name_search.ALIASES.get(market or "", {}))


def rank(q: str, rows: list[dict] | name_search.NameIndex, limit: int = LIMIT) -> list[dict]:
    """The best `limit` rows for what's typed: the exact symbol, code or ISIN first, then a short name or the whole
    name, symbols starting with it (shorter first), names starting with it, names with a word starting with each word
    typed, then the same allowing a typo (name_search)."""
    return [shown(r) for _, r in ranked(q, rows, limit)]


def ranked(q: str, rows: list[dict] | name_search.NameIndex, limit: int = LIMIT) -> list[tuple[int, dict]]:
    if not (q or "").strip():
        return []
    if not isinstance(rows, name_search.NameIndex):
        rows = index(rows, rows[0].get("market") if rows else None)
    return rows.search(q, limit)


def shown(r: dict) -> dict:
    return {k: v for k, v in r.items() if not k.startswith("_")}


# ---------- each market's list ----------
def india_rows(equities: list[dict], listed: dict | None = None) -> list[dict]:
    """From the broker's equities: NSE stocks by symbol (a restricted series under its plain symbol), and companies
    listed only on BSE, picked by their six-digit code. `listed` is the exchange's list of companies ({isin: [symbol,
    name]}): its full name is shown, and its ISIN found, instead of the broker's shortened name."""
    full = {str(v[0]).upper(): (v[1], isin) for isin, v in (listed or {}).items()
            if isinstance(v, (list, tuple)) and len(v) == 2 and v[0]}
    out, seen = [], set()
    for r in equities:
        if r.get("exchange") == "NSE":
            base, _, series = r["symbol"].partition("-")
            sym = base if series else r["symbol"]
            if sym in seen:
                continue
            seen.add(sym)
            name, isin = full.get(sym.upper(), (None, None))
            out.append(_entry(sym, name or r.get("name") or sym, "NSE", "IN", isin=isin))
        elif r.get("exchange") == "BSE" and r.get("bse_code"):
            out.append(_entry(r["symbol"], r.get("name") or r["symbol"], "BSE", "IN", code=r["bse_code"], ident=r["bse_code"]))
    return out


def us_rows(companies: list[dict]) -> list[dict]:
    """From the list of US companies ([{symbol, name}]): common shares only."""
    listed = {str(c.get("symbol") or "").upper() for c in companies}
    return [_entry(t, c.get("name") or t, "US", "US") for c in companies
            if (t := str(c.get("symbol") or "").upper()) and us_common(t, listed)]


def plain_rows(market: str, listed: dict[str, dict]) -> list[dict]:
    """From the stored list of companies with a page ({symbol: {name, bse}}): a BSE-only company by its code."""
    out = []
    for sym, v in listed.items():
        sym, name, code = str(sym or "").strip().upper(), (v or {}).get("name"), (v or {}).get("bse")
        if not sym or (market == "US" and not us_common(sym, set())):
            continue
        if code:
            out.append(_entry(sym, name or sym, "BSE", "IN", code=str(code), ident=str(code)))
        else:
            out.append(_entry(sym, name or sym, "NSE" if market == "IN" else "US", market))
    return out


def well_known(market: str) -> set[str]:
    """Symbols that come first among equal matches: NIFTY 50 and the most traded F&O stocks; the S&P 500."""
    try:
        from . import universes
        out = {s for p in universes.PRESETS.get(market, []) for s in p["symbols"]}
        if market == "US":
            out |= set(universes.sp500_symbols())
        return out
    except Exception:
        return set()


class Suggester:
    """Keeps each market's list. `sources[market]` gives the full list's rows (and may raise when its source is
    down); `fallbacks[market]` gives the stored list of companies with a page, {symbol: {name, bse}}."""

    def __init__(self, sources: dict, fallbacks: dict):
        self.sources, self.fallbacks = sources, fallbacks
        self._mem: dict[str, tuple[float, float, list[dict], name_search.NameIndex]] = {}
        self._lock = threading.Lock()

    def _get(self, market: str) -> tuple[list[dict], name_search.NameIndex]:
        hit = self._mem.get(market)
        if hit and time.time() - hit[0] < hit[1]:
            return hit[2], hit[3]
        with self._lock:
            hit = self._mem.get(market)
            if hit and time.time() - hit[0] < hit[1]:
                return hit[2], hit[3]
            got, keep = [], MEMORY
            try:
                got = self.sources[market]() or []
            except Exception as e:             # the full list is down: what's stored, tried again sooner
                print("suggestions: list unavailable,", market, e)
            if not got:
                keep = MEMORY_SHORT
                try:
                    got = plain_rows(market, self.fallbacks[market]() or {})
                except Exception as e:
                    print("suggestions: no fallback,", market, e)
                    got = []
            idx = index(got, market, well_known(market))
            self._mem[market] = (time.time(), keep, got, idx)
            return got, idx

    def rows(self, market: str) -> list[dict]:
        return self._get(market)[0]

    def search(self, q: str, market: str | None = None, limit: int = LIMIT) -> list[dict]:
        return [shown({k: v for k, v in r.items() if k != "match"}) for r in self.search_ranked(q, market, limit)]

    def search_ranked(self, q: str, market: str | None = None, limit: int = LIMIT) -> list[dict]:
        """Like search, each row (still with its matching keys) with `match`: its group in name_search."""
        markets = [market] if market in MARKETS else list(MARKETS)
        # each market ranked on its own, then merged by how well they match (India first on a tie)
        both = [(t, n, k, r) for n, m in enumerate(markets) for k, (t, r) in enumerate(ranked(q, self._get(m)[1], limit))]
        both.sort(key=lambda x: x[:3])
        return [{**r, "match": t} for t, _, _, r in both[:limit]]

    def find(self, symbol: str, market: str) -> dict | None:
        """The row for an exact symbol (or BSE code), or None."""
        s = (symbol or "").strip().upper()
        return next((shown(r) for r in self.rows(market) if r["_sym"] == s or (r["_code"] and r["_code"] == s)), None)

    def clear(self):
        self._mem.clear()
