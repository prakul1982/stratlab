"""Zerodha Kite Connect: daily login, instruments, historical candles, live ticks.

NOTE: this uses ONE Kite subscription for the whole app. Check Zerodha's API terms and
exchange data rules before serving this data to paying users. All data access goes
through this file so it can be swapped for a licensed vendor later."""
import math
import secrets
import threading
import time
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo

from kiteconnect import KiteConnect, KiteTicker

from .config import settings
from . import db

IST = ZoneInfo("Asia/Kolkata")
# our timeframe -> (kite interval, max days per request, candles per trading day)
INTERVALS = {"1d": ("day", 1900, 1), "1h": ("60minute", 380, 7), "15m": ("15minute", 190, 25), "5m": ("5minute", 95, 75)}
DEFAULT_SYMBOLS = [("NSE", "NIFTY 50"), ("NSE", "NIFTY BANK")]


def today_ist() -> str:
    return datetime.now(IST).date().isoformat()


class KiteNotReady(Exception):
    pass


class KiteService:
    def __init__(self):
        self.kite = KiteConnect(api_key=settings.KITE_API_KEY)
        self.access_token: str | None = None
        self.token_day: str | None = None
        self._lock = threading.Lock()
        self._last_call = 0.0
        self._inst: list[dict] = []
        self._by_token: dict[int, dict] = {}
        self._inst_day: str | None = None
        self._cache: dict = {}
        self.login_state: str | None = None

    # ---------- auth ----------
    def load_saved_token(self):
        tok, day = db.get_setting("kite_access_token"), db.get_setting("kite_token_day")
        if tok and day == today_ist():
            self._set_token(tok, day)

    def _set_token(self, tok: str, day: str):
        self.access_token, self.token_day = tok, day
        self.kite.set_access_token(tok)

    def ready(self) -> bool:
        # Kite tokens expire every morning, so yesterday's token counts as offline
        return bool(self.access_token) and self.token_day == today_ist()

    def login_url(self) -> str:
        self.login_state = secrets.token_urlsafe(16)
        from urllib.parse import quote
        return self.kite.login_url() + "&redirect_params=" + quote(f"state={self.login_state}")

    def complete_login(self, request_token: str, state: str | None):
        if not self.login_state or state != self.login_state:
            raise PermissionError("Login state did not match. Start the login again.")
        self.login_state = None
        return self.accept_request_token(request_token)

    def accept_request_token(self, request_token: str) -> dict:
        """Swap a request token (from the manual or automatic login) for today's access token and save it."""
        data = self.kite.generate_session(request_token, api_secret=settings.KITE_API_SECRET)
        day = today_ist()
        self._set_token(data["access_token"], day)
        db.set_setting("kite_access_token", data["access_token"])
        db.set_setting("kite_token_day", day)
        self._inst_day = None
        return data

    def _require(self):
        if not self.ready():
            raise KiteNotReady("Market data is offline. The admin needs to complete today's Kite login.")

    def _throttle(self):
        # Kite allows about 3 requests per second on most endpoints
        with self._lock:
            wait = 0.36 - (time.time() - self._last_call)
            if wait > 0:
                time.sleep(wait)
            self._last_call = time.time()

    # ---------- instruments ----------
    def _load_instruments(self):
        if self._inst_day == today_ist() and self._inst:
            return
        self._require()
        rows = []
        for exch in ("NSE", "NFO"):
            self._throttle()
            for x in self.kite.instruments(exch):
                itype = x.get("instrument_type")
                if exch == "NSE" and itype != "EQ" and x.get("segment") != "INDICES":
                    continue
                rows.append({
                    "token": int(x["instrument_token"]),
                    "symbol": x["tradingsymbol"],
                    "name": x.get("name") or x["tradingsymbol"],
                    "exchange": exch,
                    "type": "INDEX" if x.get("segment") == "INDICES" else itype,
                    "lot": int(x.get("lot_size") or 1),
                    "expiry": x["expiry"].isoformat() if x.get("expiry") else None,
                    "strike": x.get("strike") or None,
                    "fno": exch == "NFO",
                })
        self._inst = rows
        self._by_token = {r["token"]: r for r in rows}
        self._inst_day = today_ist()

    def instrument(self, token: int) -> dict | None:
        self._load_instruments()
        return self._by_token.get(int(token))

    def defaults(self) -> list[dict]:
        self._load_instruments()
        out = []
        for exch, sym in DEFAULT_SYMBOLS:
            out += [r for r in self._inst if r["exchange"] == exch and r["symbol"] == sym][:1]
        return out

    ALIASES = {
        # Tata Motors demerged in 2025; the old symbol was replaced
        "TATAMOTORS": ["TMPV", "TMCV"], "TATA MOTORS": ["TMPV", "TMCV"],
        "BANKNIFTY": ["NIFTY BANK"], "BANK NIFTY": ["NIFTY BANK"], "NIFTY": ["NIFTY 50"], "NIFTY50": ["NIFTY 50"],
        "SBI": ["SBIN"], "STATE BANK": ["SBIN"], "HDFC": ["HDFCBANK"], "ICICI": ["ICICIBANK"], "KOTAK": ["KOTAKBANK"],
        "AIRTEL": ["BHARTIARTL"], "BHARTI AIRTEL": ["BHARTIARTL"], "L&T": ["LT"], "LARSEN": ["LT"], "M&M": ["M&M"],
        "MAHINDRA": ["M&M"], "BAJAJ FINANCE": ["BAJFINANCE"], "ASIAN PAINTS": ["ASIANPAINT"], "SUN PHARMA": ["SUNPHARMA"],
        "HUL": ["HINDUNILVR"], "HINDUSTAN UNILEVER": ["HINDUNILVR"], "MARUTI": ["MARUTI"], "ZOMATO": ["ETERNAL"],
    }

    def search(self, q: str, allow_fno: bool, limit: int = 25) -> list[dict]:
        self._load_instruments()
        q = q.strip().upper()
        alias_hits = []
        for sym in self.ALIASES.get(q, []):
            alias_hits += [r for r in self._inst if r["symbol"] == sym and not r["fno"]]
        if len(q) < 2:
            return []
        scored = []
        for r in self._inst:
            if r["fno"] and not allow_fno:
                continue
            sym, name = r["symbol"].upper(), r["name"].upper()
            if sym == q:
                score = 0
            elif sym.startswith(q):
                score = 1
            elif name.startswith(q):
                score = 2
            elif q in sym or q in name:
                score = 3
            else:
                continue
            # indices and cash stocks first, then nearest expiry
            score = score * 10 + (0 if r["type"] == "INDEX" else 1 if r["type"] == "EQ" else 2 if r["type"] == "FUT" else 3)
            scored.append((score, r["expiry"] or "", r["symbol"], r))
        scored.sort(key=lambda x: x[:3])
        seen = {r["token"] for r in alias_hits}
        return (alias_hits + [x[3] for x in scored if x[3]["token"] not in seen])[:limit]

    def ltp(self, token: int) -> float | None:
        self._require()
        inst = self.instrument(token)
        key = f"{inst['exchange']}:{inst['symbol']}" if inst else str(token)
        self._throttle()
        data = self.kite.ltp([key])
        v = data.get(key) or data.get(str(token)) or next(iter(data.values()), None)
        return v["last_price"] if v else None

    # ---------- historical candles ----------
    def history(self, token: int, tf: str, days: int) -> list[dict]:
        self._require()
        interval, chunk, _ = INTERVALS[tf]
        now = datetime.now(IST)
        ttl = 6 * 3600 if tf == "1d" else 300
        key = (token, tf, days)
        hit = self._cache.get(key)
        if hit and time.time() - hit[0] < ttl:
            return hit[1]
        inst = self._by_token.get(int(token)) or {}
        continuous = inst.get("type") == "FUT" and tf == "1d"
        start = now - timedelta(days=days)
        out, frm = [], start
        while frm < now:
            to = min(frm + timedelta(days=chunk), now)
            self._throttle()
            rows = self.kite.historical_data(token, frm.replace(tzinfo=None), to.replace(tzinfo=None),
                                             interval, continuous=continuous)
            for r in rows:
                d = r["date"]
                if d.tzinfo is None:
                    d = d.replace(tzinfo=IST)
                out.append({"t": d.isoformat(), "o": float(r["open"]), "h": float(r["high"]),
                            "l": float(r["low"]), "c": float(r["close"]), "v": float(r.get("volume") or 0)})
            frm = to + timedelta(seconds=1)
        seen, dedup = set(), []
        for b in out:
            if b["t"] not in seen:
                seen.add(b["t"]); dedup.append(b)
        self._cache[key] = (time.time(), dedup)
        if len(self._cache) > 300:
            self._cache.pop(next(iter(self._cache)))
        return dedup

    @staticmethod
    def warmup_days(tf: str, candles: int = 210) -> int:
        per_day = INTERVALS[tf][2]
        return math.ceil(candles / per_day * 7 / 5) + 10


class TickHub:
    """One KiteTicker connection shared by every live session.
    KiteTicker runs on Twisted, which cannot be restarted inside the same process,
    so after the daily Kite login the server must be restarted if the ticker was already running."""

    def __init__(self, kite: KiteService):
        self.kite = kite
        self.ws: KiteTicker | None = None
        self.started = False
        self.connected = False
        self.listeners: dict[str, tuple[int, callable]] = {}
        self._lock = threading.Lock()

    def start(self):
        if self.started or not self.kite.ready():
            return
        self.ws = KiteTicker(settings.KITE_API_KEY, self.kite.access_token)
        self.ws.on_ticks = self._on_ticks
        self.ws.on_connect = self._on_connect
        self.ws.on_close = lambda ws, code, reason: setattr(self, "connected", False)
        self.ws.on_error = lambda ws, code, reason: setattr(self, "connected", False)
        self.ws.connect(threaded=True)
        self.started = True

    def _tokens(self) -> list[int]:
        with self._lock:
            return sorted({tok for tok, _ in self.listeners.values()})

    def _on_connect(self, ws, response):
        self.connected = True
        toks = self._tokens()
        if toks:
            ws.subscribe(toks)
            ws.set_mode(ws.MODE_QUOTE, toks)

    def _on_ticks(self, ws, ticks):
        with self._lock:
            items = list(self.listeners.values())
        for tick in ticks:
            tok = tick.get("instrument_token")
            for ltok, cb in items:
                if ltok == tok:
                    try:
                        cb(tick)
                    except Exception as e:  # never let one session break the feed
                        print("tick handler error:", e)

    def add(self, lid: str, token: int, cb):
        with self._lock:
            self.listeners[lid] = (token, cb)
        if not self.started:
            self.start()
        elif self.connected and self.ws:
            self.ws.subscribe([token])
            self.ws.set_mode(self.ws.MODE_QUOTE, [token])

    def remove(self, lid: str):
        with self._lock:
            item = self.listeners.pop(lid, None)
            still = item and any(t == item[0] for t, _ in self.listeners.values())
        if item and not still and self.connected and self.ws:
            self.ws.unsubscribe([item[0]])
