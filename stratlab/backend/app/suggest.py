"""Company suggestions while a symbol is typed: listed companies in India (NSE, else BSE-only by its code) and US
common stocks, matched on the symbol, the BSE code or the start of any word of the name.

Each market's list is gathered once (the broker's instrument list, the SEC's list of filers, or the stock pages
already stored when those are offline) and kept in memory, so a keystroke is a walk over a few thousand rows."""
import re
import threading
import time

LIMIT = 8
MEMORY = 1800                          # seconds a market's list is kept before it's gathered again
MEMORY_SHORT = 120                     # ...when it came from the fallbacks: the full list may be back soon
MARKETS = ("IN", "US")
_WORD = re.compile(r"[A-Z0-9&]+")


def _entry(symbol: str, name: str, exchange: str, market: str, code: str | None = None, ident: str | None = None) -> dict:
    """One company as the list keeps it: what's shown, what's filled in when picked (`id`), and what's matched."""
    name = str(name or symbol).strip() or symbol
    return {"symbol": symbol, "id": ident or symbol, "name": name[:120], "exchange": exchange, "market": market,
            "_sym": symbol.upper(), "_code": code or "", "_name": name.upper(), "_words": _WORD.findall(name.upper())}


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


def rank(q: str, rows: list[dict], limit: int = LIMIT) -> list[dict]:
    """The best `limit` rows for what's typed: the exact symbol (or BSE code) first, then symbols starting with it,
    then names starting with it, then names with a word starting with each word typed. Shorter symbols, then names
    in order, break ties."""
    q = (q or "").strip().upper()
    if not q:
        return []
    words = _WORD.findall(q)
    scored = []
    for r in rows:
        if r["_sym"] == q or (r["_code"] and r["_code"] == q) or r["id"].upper() == q:
            s = 0
        elif r["_sym"].startswith(q):
            s = 1
        elif r["_name"].startswith(q):
            s = 2
        elif words and all(any(w.startswith(t) for w in r["_words"]) for t in words):
            s = 3
        else:
            continue
        scored.append((s, len(r["_sym"]) if s == 1 else 0, r["_name"], r["_sym"], r))
    scored.sort(key=lambda x: x[:4])
    return [shown(x[4]) for x in scored[:limit]]


def shown(r: dict) -> dict:
    return {k: v for k, v in r.items() if not k.startswith("_")}


# ---------- each market's list ----------
def india_rows(equities: list[dict]) -> list[dict]:
    """From the broker's equities: NSE stocks by symbol (a restricted series under its plain symbol), and companies
    listed only on BSE, picked by their six-digit code."""
    out, seen = [], set()
    for r in equities:
        if r.get("exchange") == "NSE":
            base, _, series = r["symbol"].partition("-")
            sym = base if series else r["symbol"]
            if sym in seen:
                continue
            seen.add(sym)
            out.append(_entry(sym, r.get("name") or sym, "NSE", "IN"))
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


class Suggester:
    """Keeps each market's list. `sources[market]` gives the full list's rows (and may raise when its source is
    down); `fallbacks[market]` gives the stored list of companies with a page, {symbol: {name, bse}}."""

    def __init__(self, sources: dict, fallbacks: dict):
        self.sources, self.fallbacks = sources, fallbacks
        self._mem: dict[str, tuple[float, float, list[dict]]] = {}
        self._lock = threading.Lock()

    def rows(self, market: str) -> list[dict]:
        hit = self._mem.get(market)
        if hit and time.time() - hit[0] < hit[1]:
            return hit[2]
        with self._lock:
            hit = self._mem.get(market)
            if hit and time.time() - hit[0] < hit[1]:
                return hit[2]
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
            self._mem[market] = (time.time(), keep, got)
            return got

    def search(self, q: str, market: str | None = None) -> list[dict]:
        markets = [market] if market in MARKETS else list(MARKETS)
        if len(markets) == 1:
            return rank(q, self.rows(markets[0]))
        # both markets: each ranked on its own, then merged by how well they match (India first on a tie)
        both = [(i, r) for i, m in enumerate(markets) for r in rank(q, self.rows(m))]
        return [r for _, r in sorted(both, key=lambda x: (_score(q, x[1]), x[0]))][:LIMIT]

    def find(self, symbol: str, market: str) -> dict | None:
        """The row for an exact symbol (or BSE code), or None."""
        s = (symbol or "").strip().upper()
        return next((shown(r) for r in self.rows(market) if r["_sym"] == s or (r["_code"] and r["_code"] == s)), None)

    def clear(self):
        self._mem.clear()


def _score(q: str, r: dict) -> int:
    """0 for the exact symbol, 1 for a symbol starting with what's typed, 2 for a name match."""
    q = q.strip().upper()
    sym = r["symbol"].upper()
    return 0 if sym == q or r["id"].upper() == q else 1 if sym.startswith(q) else 2
