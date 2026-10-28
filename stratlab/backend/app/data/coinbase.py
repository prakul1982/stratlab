"""Crypto market data from Coinbase's public Exchange API (no key needed).

Chosen because it's free and reachable from US-hosted servers, where some other
exchanges block requests. Candles come 300 at a time, newest first."""
import math
import threading
import time
from datetime import datetime, timezone

import httpx

from ..http_retry import real_transport

BASE = "https://api.exchange.coinbase.com"
GRANULARITY = {"1d": 86400, "1h": 3600, "15m": 900, "5m": 300}
PER_DAY = {"1d": 1, "1h": 24, "15m": 96, "5m": 288}
MAX_DAYS = {"1d": 3650, "1h": 365, "15m": 90, "5m": 30}
QUOTES = ("USD", "USDT", "USDC", "EUR", "GBP")
RELOAD_AFTER_ERROR = 300        # seconds before the coin list is asked for again after a failed refresh (the old one stays)
DEFAULTS = ("BTC-USD", "ETH-USD", "SOL-USD")
NAMES = {
    "BTC": "Bitcoin", "ETH": "Ethereum", "SOL": "Solana", "XRP": "XRP", "DOGE": "Dogecoin", "ADA": "Cardano",
    "AVAX": "Avalanche", "LINK": "Chainlink", "DOT": "Polkadot", "LTC": "Litecoin", "BCH": "Bitcoin Cash",
    "SHIB": "Shiba Inu", "UNI": "Uniswap", "ATOM": "Cosmos", "NEAR": "NEAR", "POL": "Polygon", "XLM": "Stellar",
    "AAVE": "Aave", "SUI": "Sui", "APT": "Aptos", "ARB": "Arbitrum", "OP": "Optimism", "PEPE": "Pepe",
}
QUOTE_NAMES = {"USD": "US Dollar", "USDT": "Tether", "USDC": "USD Coin", "EUR": "Euro", "GBP": "British Pound"}


def _candles(data) -> list:
    """Coinbase candles are [time, low, high, open, close, volume] rows; anything else is a broken answer."""
    if not isinstance(data, list):
        raise DataError("Coinbase sent something that isn't price data. Try again in a minute.")
    out = []
    for c in data:
        try:
            if len(c) >= 6 and all(math.isfinite(float(x)) for x in c[:6]):
                out.append(c)
        except (TypeError, ValueError):
            continue
    return out


def _bar(c) -> dict:
    ts, low, high, open_, close, vol = c[:6]
    return {"t": _iso(ts), "o": float(open_), "h": float(high), "l": float(low), "c": float(close), "v": float(vol)}


class DataError(Exception):
    pass


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).isoformat()


class CoinbaseProvider:
    market = "CRYPTO"
    max_days = MAX_DAYS

    def __init__(self, transport: httpx.BaseTransport | None = None):
        self._http = httpx.Client(base_url=BASE, timeout=20, transport=transport or real_transport(),
                                  headers={"User-Agent": "StratLab (+https://stratlab.studio)"})
        self._lock = threading.Lock()
        self._last = 0.0
        self._products: list[dict] = []
        self._by_id: dict[str, dict] = {}
        self._loaded_at = 0.0
        self._retry_at = 0.0
        self._cache: dict = {}

    def ready(self) -> bool:
        return True

    def _get(self, path: str, **params):
        with self._lock:  # public limit is about 10 requests a second
            wait = 0.12 - (time.time() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.time()
        try:
            r = self._http.get(path, params=params)
        except httpx.HTTPError as e:
            raise DataError(f"Couldn't reach Coinbase: {e.__class__.__name__}") from None
        if r.status_code == 404:
            raise DataError("Coinbase doesn't list that pair.")
        if r.status_code >= 400:
            raise DataError(f"Coinbase returned an error ({r.status_code}).")
        try:
            return r.json()
        except ValueError:
            raise DataError("Coinbase sent a page instead of prices (it may be busy). Try again in a minute.") from None

    # ---------- instruments ----------
    def _load(self):
        now = time.time()
        if self._products and (now - self._loaded_at < 6 * 3600 or now < self._retry_at):
            return
        rows = []
        try:
            listed = self._get("/products")
            if not isinstance(listed, list):
                raise DataError("Coinbase sent something that isn't its list of coins. Try again in a minute.")
        except DataError:
            if self._products:          # keep the list we have, and ask again in a few minutes rather than on every call
                self._retry_at = now + RELOAD_AFTER_ERROR
                return
            raise
        for p in listed:
            if not isinstance(p, dict) or not p.get("id") or not p.get("base_currency"):
                continue
            if p.get("quote_currency") not in QUOTES or p.get("trading_disabled") or p.get("status") not in (None, "online"):
                continue
            base, quote = p["base_currency"], p["quote_currency"]
            rows.append({
                "id": f"CRYPTO:{p['id']}", "token": p["id"], "symbol": f"{base}/{quote}",
                "name": f"{NAMES.get(base, base)} / {QUOTE_NAMES.get(quote, quote)}",
                "exchange": "Coinbase", "type": "CRYPTO", "market": "CRYPTO", "currency": quote,
                "step": float(p.get("base_increment") or 0.00000001), "lot": 1, "fno": False,
                "expiry": None, "strike": None, "tz": "UTC",
            })
        if not rows and self._products:     # an empty list is a broken answer: keep what we have
            self._retry_at = now + RELOAD_AFTER_ERROR
            return
        self._products = rows
        self._by_id = {r["token"]: r for r in rows}
        self._loaded_at = time.time()

    def instrument(self, key: str) -> dict | None:
        self._load()
        return self._by_id.get(key.upper().replace("/", "-"))

    def defaults(self) -> list[dict]:
        self._load()
        return [self._by_id[k] for k in DEFAULTS if k in self._by_id]

    def search(self, q: str, allow_fno: bool = True, limit: int = 25) -> list[dict]:
        self._load()
        q = q.strip().upper().replace("/", "-")
        if len(q) < 2:
            return []
        scored = []
        for r in self._products:
            tok, name = r["token"], r["name"].upper()
            base = tok.split("-")[0]
            if tok == q or base == q:
                score = 0
            elif tok.startswith(q):
                score = 1
            elif name.startswith(q):
                score = 2
            elif q in tok or q in name:
                score = 3
            else:
                continue
            quote_rank = QUOTES.index(r["currency"]) if r["currency"] in QUOTES else 9
            scored.append((score, quote_rank, tok, r))
        scored.sort(key=lambda x: x[:3])
        return [x[3] for x in scored[:limit]]

    # ---------- prices ----------
    def ltp(self, inst: dict) -> float | None:
        data = self._get(f"/products/{inst['token']}/ticker")
        try:
            return float(data["price"])
        except (KeyError, TypeError, ValueError):
            return None

    @staticmethod
    def warmup_days(tf: str, candles: int = 210) -> int:
        return math.ceil(candles / PER_DAY[tf]) + 2

    def history(self, inst: dict, tf: str, days: int) -> list[dict]:
        g = GRANULARITY[tf]
        # a daily series is of its UTC day: the day's candle is forming, and tomorrow's request must not get today's list
        key = (inst["token"], tf, days, datetime.now(timezone.utc).date().isoformat() if tf == "1d" else None)
        hit = self._cache.get(key)
        if hit and time.time() - hit[0] < (3600 if tf == "1d" else 120):
            return hit[1]
        end = time.time()
        t = end - days * 86400
        rows: dict[int, dict] = {}
        while t < end:
            to = min(t + 300 * g, end)
            for c in _candles(self._get(f"/products/{inst['token']}/candles", granularity=g, start=_iso(t), end=_iso(to))):
                rows[int(c[0])] = _bar(c)
            t = to
        bars = [rows[k] for k in sorted(rows)]
        self._cache[key] = (time.time(), bars)
        if len(self._cache) > 200:
            self._cache.pop(next(iter(self._cache)))
        return bars

    def minute_history(self, inst: dict, start, end) -> list[dict]:
        """1-minute candles from `start` to `end` (aware times). The exchange sends 300 a request, so a day is five requests,
        paced like every other read here; a finished hour is kept for ten minutes and shared by everyone charting the pair,
        the hour still forming for 20 seconds (MW-1)."""
        rows: dict[int, dict] = {}
        t = start.timestamp()
        stop = min(end.timestamp(), time.time())
        while t < stop:
            to = min(t + 300 * 60, stop)
            key = (inst["token"], "1m", int(t // 60), int(to // 60))
            hit = self._cache.get(key)
            if hit and time.time() - hit[0] < (1200 if to < time.time() - 3600 else 20):
                got = hit[1]
            else:
                got = [_bar(c) for c in _candles(self._get(f"/products/{inst['token']}/candles", granularity=60, start=_iso(t), end=_iso(to)))]
                self._cache[key] = (time.time(), got)
                if len(self._cache) > 400:
                    self._cache.pop(next(iter(self._cache)))
            for b in got:
                rows[int(datetime.fromisoformat(b["t"]).timestamp())] = b
            t = to
        return [rows[k] for k in sorted(rows)]

    def closed_candles(self, inst: dict, tf: str, since: str | None) -> list[dict]:
        """Candles that have fully closed after `since`, for live paper trading."""
        g = GRANULARITY[tf]
        now = time.time()
        start = now - 50 * g
        out = []
        for c in _candles(self._get(f"/products/{inst['token']}/candles", granularity=g, start=_iso(start), end=_iso(now))):
            ts = int(c[0])
            if ts + g > now:  # still forming
                continue
            b = _bar(c)
            if since is None or b["t"] > since:
                out.append(b)
        return sorted(out, key=lambda b: b["t"])
