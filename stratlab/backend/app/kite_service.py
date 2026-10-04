"""Zerodha Kite Connect: daily login, instruments, historical candles, live ticks.

NOTE: this uses ONE Kite subscription for the whole app. Check Zerodha's API terms and
exchange data rules before serving this data to paying users. All data access goes
through this file so it can be swapped for a licensed vendor later."""
import math
import secrets
import threading
import re
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from kiteconnect import KiteConnect, KiteTicker
from kiteconnect.exceptions import TokenException

from .config import settings
from . import db

IST = ZoneInfo("Asia/Kolkata")
# our timeframe -> (kite interval, max days per request, candles per trading day)
INTERVALS = {"1d": ("day", 1900, 1), "1h": ("60minute", 380, 7), "15m": ("15minute", 190, 25), "5m": ("5minute", 95, 75)}
DEFAULT_SYMBOLS = [("NSE", "NIFTY 50"), ("NSE", "NIFTY BANK")]


NSE_SERIES = ("BE", "BZ", "SM", "ST", "SZ")     # trade-to-trade, z-group and SME series, on the broker as SYMBOL-BE…
UNIT_SERIES = ("GB", "RR", "IV")                # gold bonds, REITs and InvITs, when a file gives the symbol without them


def norm_name(n: str | None) -> str:
    """A company name for matching across exchanges: lower case, without Ltd, Limited, India and the like."""
    n = re.sub(r"[^a-z0-9 ]", " ", (n or "").lower())
    return " ".join(w for w in n.split() if w not in ("ltd", "limited", "the", "co", "company", "india", "inds", "industries"))


def bse_only_rows(raw: list[dict], nse_rows: list[dict]) -> list[dict]:
    """BSE equities that aren't on NSE too (a company on both is the NSE one): matched by symbol and by name."""
    syms = {r["symbol"].upper() for r in nse_rows if r["exchange"] == "NSE"}
    names = {norm_name(r["name"]) for r in nse_rows if r["exchange"] == "NSE" and r["type"] == "EQ"}
    out = []
    for x in raw:
        ts, code = str(x.get("tradingsymbol") or ""), str(x.get("exchange_token") or "")
        if x.get("instrument_type") != "EQ" or x.get("segment") != "BSE" or not ts or not code.isdigit():
            continue
        if ts.upper() in syms or norm_name(x.get("name")) in names:
            continue
        if int(code) >= 600000 or norm_name(x.get("name")) in ("", code):
            continue                            # 6xxxxx-9xxxxx are bonds, bills and other debt, not companies
        if not_company(x.get("name")):
            continue                            # ETFs, mutual fund units, REITs and InvITs trade like shares but aren't companies
        out.append(x)
    return out


# names of what BSE lists as equity but isn't a company: exchange-traded funds ("Nifty 50 ETF", "...Momen.Quali. 100ETF",
# "Gold Exchange Traded Fund", "...BeES"), mutual fund units, and real-estate and infrastructure trusts
NOT_COMPANY = re.compile(r"(?<![a-z])ETFs?\b|exchange traded|\bBeES\b|\bmutual fund\b|\bMF\b|fund of funds|\bFoF\b|"
                         r"\bInvIT\b|\bREIT\b|investment trust|real estate trust|infrastructure trust|\btrust\s*$", re.I)


def not_company(name) -> bool:
    """A fund or trust by its name; anything named "... Ltd" is a company whatever else it says ("Rajkot Investment
    Trust Ltd")."""
    n = str(name or "").strip()
    return bool(NOT_COMPANY.search(n)) and not re.search(r"\b(?:ltd|limited)\.?$", n, re.I)


def today_ist() -> str:
    return datetime.now(IST).date().isoformat()


def ist_date():
    """Today in India. The server's own clock is UTC, where "today" is still yesterday until 5:30 am IST."""
    return datetime.now(IST).date()


RESET_HOUR = 6        # Zerodha expires every token at about 6 am India time the next morning


def token_valid(token_day: str | None, now: datetime | None = None) -> bool:
    """Today's token, or yesterday's until the 6 am reset (so the app doesn't go offline at midnight)."""
    now = (now or datetime.now(IST)).astimezone(IST)
    if not token_day:
        return False
    if token_day == now.date().isoformat():
        return True
    return now.hour < RESET_HOUR and token_day == (now.date() - timedelta(days=1)).isoformat()


class KiteNotReady(Exception):
    pass


class _Guarded:
    """KiteConnect, noticing when Zerodha has cancelled the access token mid-day."""

    def __init__(self, inner, on_token_error):
        self._inner, self._on = inner, on_token_error

    def __getattr__(self, name):
        attr = getattr(self._inner, name)
        if not callable(attr) or name in ("generate_session", "login_url", "set_access_token"):
            return attr

        def call(*a, **kw):
            try:
                return attr(*a, **kw)
            except TokenException as e:
                self._on(e)
                raise
        return call


class KiteService:
    def __init__(self):
        self.kite = _Guarded(KiteConnect(api_key=settings.KITE_API_KEY), self._token_rejected)
        self.invalid_reason: str | None = None
        self.on_invalid = None        # called once with a message when the token is cancelled
        self.access_token: str | None = None
        self.token_day: str | None = None
        self._lock = threading.Lock()
        self._last_call = 0.0
        self._inst: list[dict] = []
        self._by_token: dict[int, dict] = {}
        self._inst_day: str | None = None
        self._idx: dict = {}
        self._idx_of: list | None = None
        self._cache: dict = {}
        self.login_state: str | None = None

    # ---------- auth ----------
    def load_saved_token(self):
        tok, day = db.get_setting("kite_access_token"), db.get_setting("kite_token_day")
        if tok and token_valid(day):
            self._set_token(tok, day)

    def _set_token(self, tok: str, day: str):
        self.access_token, self.token_day = tok, day
        self.invalid_reason = None
        self.kite.set_access_token(tok)

    def _token_rejected(self, e):
        """Zerodha refused today's token, usually because the account logged in to this API key somewhere else.
        Go offline rather than failing every request, and don't log in again automatically: that would cancel
        the other login's token in turn."""
        if not self.ready():
            return
        self.invalid_reason = (f"Zerodha cancelled today's Kite token at {datetime.now(IST):%H:%M}. This usually means the "
                               "same Zerodha account logged in to this Kite Connect app somewhere else (another bot or "
                               "script using the same API key). Log in again from the admin page.")
        print("Kite token rejected:", e)
        if self.on_invalid:
            try:
                self.on_invalid(self.invalid_reason)
            except Exception as x:
                print("token alert failed:", x)

    def ready(self) -> bool:
        return bool(self.access_token) and token_valid(self.token_day) and not self.invalid_reason

    def login_url(self) -> str:
        self.login_state = secrets.token_urlsafe(16)
        from urllib.parse import quote
        return self.kite.login_url() + "&redirect_params=" + quote(f"state={self.login_state}")

    def complete_login(self, request_token: str, state: str | None):
        if not self.login_state or not secrets.compare_digest(str(state or "").encode(), self.login_state.encode()):
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
        if self.invalid_reason:
            raise KiteNotReady("Indian market data is offline: the broker login was cancelled. The admin needs to log in again.")
        if not self.ready():
            raise KiteNotReady("Market data is offline. The admin needs to complete today's data login.")

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
        for exch in ("NSE", "NFO", "BSE"):
            self._throttle()
            try:
                raw = self.kite.instruments(exch)
            except Exception as e:
                if exch != "BSE":
                    raise
                print("BSE instruments unavailable:", e)       # NSE and F&O still work
                continue
            if exch == "BSE":
                raw = bse_only_rows(raw, rows)
            for x in raw:
                itype = x.get("instrument_type")
                if exch == "NSE" and itype != "EQ" and x.get("segment") != "INDICES":
                    continue
                token, lot = int(x["instrument_token"]), int(x.get("lot_size") or 1)
                rows.append({
                    "id": f"IN:{token}",
                    "token": token,
                    "symbol": x["tradingsymbol"],
                    "name": x.get("name") or x["tradingsymbol"],
                    "exchange": exch,
                    "type": "INDEX" if x.get("segment") == "INDICES" else itype,
                    "lot": lot,
                    "step": lot if exch == "NFO" else 1,
                    "expiry": x["expiry"].isoformat() if x.get("expiry") else None,
                    "strike": x.get("strike") or None,
                    "fno": exch == "NFO",
                    "market": "IN", "currency": "INR", "tz": "Asia/Kolkata",
                    **({"bse_code": str(x["exchange_token"])} if exch == "BSE" else {}),
                })
        self._inst = rows
        self._by_token = {r["token"]: r for r in rows}
        self._inst_day = today_ist()

    def instruments_of(self, exchange: str) -> list[dict]:
        """Kite's raw instrument list for one exchange (MCX commodities), fetched once a day."""
        key = ("instruments", exchange, today_ist())
        hit = self._cache.get(key)
        if hit:
            return hit[1]
        self._require()
        self._throttle()
        rows = self.kite.instruments(exchange)
        self._cache[key] = (time.time(), rows)
        return rows

    def ltp_key(self, key: str) -> float | None:
        """Last price for an "EXCHANGE:SYMBOL" key."""
        self._require()
        self._throttle()
        v = self.kite.ltp([key]).get(key)
        return v["last_price"] if v else None

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
            if sym == q or r.get("bse_code") == q:
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

    def equity(self, symbol: str) -> dict | None:
        """A listed company's stock: on NSE by symbol (also when it trades in a restricted or SME series, which the
        broker lists as SYMBOL-BE, -BZ, -SM…), or listed only on BSE, by its BSE symbol or six-digit code."""
        hit = self.by_symbol(symbol)
        if hit and hit["type"] == "EQ":
            return hit
        symbol = symbol.strip().upper()
        for series in NSE_SERIES + UNIT_SERIES:
            hit = self.by_symbol(f"{symbol}-{series}")
            if hit and hit["type"] == "EQ":
                return hit
        idx = self._index()
        return idx["sym"].get(("BSE", symbol)) or idx["bse"].get(symbol)

    def equity_by_name(self, name: str) -> dict | None:
        """A listed company's stock by its name as a broker writes it ("Reliance Industries Ltd"): NSE first, then
        listed only on BSE. Only an exact match after dropping Ltd, Limited, India and the like."""
        want = norm_name(name)
        if not want:
            return None
        idx = self._index()
        return idx["name"].get(("NSE", want)) or idx["name"].get(("BSE", want))

    def equities(self) -> list[dict]:
        """Every company's stock in the day's list: NSE (any series), then those listed only on BSE."""
        self._load_instruments()
        return [r for r in self._inst if r["type"] == "EQ" and r["exchange"] in ("NSE", "BSE")]

    def by_symbol(self, symbol: str, exchange: str = "NSE") -> dict | None:
        """The cash stock or index with this trading symbol."""
        return self._index()["sym"].get((exchange, symbol.strip().upper()))

    def _index(self) -> dict:
        """The day's instrument list by (exchange, symbol), BSE code and (exchange, company name) for equities, the
        first in the list winning as before. Built once per list: walking ~100,000 instruments (F&O included) for every
        lookup let a file of made-up holdings lines tie up the server for minutes."""
        self._load_instruments()
        inst = self._inst
        if self._idx_of is not inst:
            sym, bse, name = {}, {}, {}
            for r in inst:
                sym.setdefault((r["exchange"], r["symbol"]), r)
                if r.get("bse_code"):
                    bse.setdefault(r["bse_code"], r)
                if r["type"] == "EQ" and r["exchange"] in ("NSE", "BSE"):
                    name.setdefault((r["exchange"], norm_name(r["name"])), r)
            self._idx, self._idx_of = {"sym": sym, "bse": bse, "name": name}, inst
        return self._idx

    def quote(self, symbols: list[str]) -> dict[str, dict]:
        """Last price, day range and previous close for stocks (NSE symbols, or BSE-only symbols or codes), in one
        call (Kite allows 500). Answers are keyed by the symbol asked for."""
        self._require()
        self._load_instruments()
        keys: dict[str, str] = {}
        for s in symbols[:500]:
            s = s.strip().upper()
            if not s:
                continue
            hit = self.equity(s)
            keys[f"{hit['exchange']}:{hit['symbol']}" if hit and hit["exchange"] == "BSE" else f"NSE:{s}"] = s
        if not keys:
            return {}
        self._throttle()
        data = self.kite.quote(list(keys))
        out = {}
        for k, v in data.items():
            ohlc = v.get("ohlc") or {}
            prev = ohlc.get("close") or None
            last = v.get("last_price")
            out[keys.get(k, k.split(":", 1)[1])] = {
                "price": last, "prev_close": prev, "open": ohlc.get("open"), "high": ohlc.get("high"),
                "low": ohlc.get("low"), "volume": v.get("volume"),
                "change": (last - prev) if last is not None and prev else None,
                "change_pct": ((last / prev - 1) * 100) if last is not None and prev else None,
            }
        return out

    # ---------- historical candles ----------
    def history(self, token: int, tf: str, days: int, continuous: bool | None = None, ttl: float | None = None,
                store: bool = True) -> list[dict]:
        """Candles for a token. Futures on daily candles use Kite's continuous series unless told otherwise;
        `ttl` overrides how long a cached answer is reused (live polling wants fresh candles). `store=False` leaves
        the answer out of the cache (a whole-market read would push everything else out of it)."""
        self._require()
        interval, chunk, _ = INTERVALS[tf]
        now = datetime.now(IST)
        if ttl is None:
            ttl = 6 * 3600 if tf == "1d" else 300
        if continuous is None:
            inst = self._by_token.get(int(token)) or {}
            continuous = inst.get("type") == "FUT" and tf == "1d"
        key = (token, tf, days, continuous)
        hit = self._cache.get(key)
        if hit and time.time() - hit[0] < ttl:
            return hit[1]
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
        if not store:
            return dedup
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
        self._full: set[str] = set()      # listeners that need the order book (bid and ask) in each tick
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
            full = self._full_tokens()
            if [t for t in toks if t not in full]:
                ws.set_mode(ws.MODE_QUOTE, [t for t in toks if t not in full])
            if full:
                ws.set_mode(ws.MODE_FULL, sorted(full))

    def _full_tokens(self) -> set[int]:
        with self._lock:
            return {tok for lid, (tok, _) in self.listeners.items() if lid in self._full}

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

    def add(self, lid: str, token: int, cb, full: bool = False):
        with self._lock:
            self.listeners[lid] = (token, cb)
            if full:
                self._full.add(lid)
        if not self.started:
            self.start()
        elif self.connected and self.ws:
            self.ws.subscribe([token])
            full_tok = token in self._full_tokens()
            self.ws.set_mode(self.ws.MODE_FULL if full_tok else self.ws.MODE_QUOTE, [token])

    def remove(self, lid: str):
        with self._lock:
            item = self.listeners.pop(lid, None)
            self._full.discard(lid)
            still = item and any(t == item[0] for t, _ in self.listeners.values())
        if item and not still and self.connected and self.ws:
            self.ws.unsubscribe([item[0]])
