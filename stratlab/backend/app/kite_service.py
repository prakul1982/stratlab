"""Zerodha Kite Connect: daily login, instruments, historical candles, live ticks.

NOTE: this uses ONE Kite subscription for the whole app. Check Zerodha's API terms and
exchange data rules before serving this data to paying users. All data access goes
through this file so it can be swapped for a licensed vendor later."""
import math
import secrets
from bisect import bisect_left
import threading
import re
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from kiteconnect import KiteConnect, KiteTicker
from kiteconnect.exceptions import TokenException

from .config import settings
from . import db, name_search

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


_NO_NAMES: dict = {}


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
    # the exchange's list of companies, () -> {isin: [symbol, name]}, for search by full name and ISIN. Set by main.
    names_fn = None

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
        self._names_of: tuple | None = None
        self._names_idx: dict = {}
        from .intel.net import SizedDict
        self._cache = SizedDict(max_items=300, max_bytes=96 * 1024 * 1024)   # candles: bounded, the market audit reads every company
        self._tails: dict[tuple, tuple[float, list[dict]]] = {}   # (token, tf) -> the newest candles seen, so no answer ends before them
        self.login_state: str | None = None
        self.session_close: dict[int, str] = {}   # token -> "HH:MM" IST when its segment closes (commodity and currency futures)

    def set_session_close(self, token: int, hhmm: str | None):
        """A futures contract whose segment closes later than the stock market (currency 17:00, commodity 23:30 IST):
        its daily candle is read again after its own close, not the stock market's (R9R-005: a CDS candle read before
        17:00 was kept for six hours, so the check after the close still saw the day before)."""
        if hhmm:
            self.session_close[int(token)] = hhmm
        else:
            self.session_close.pop(int(token), None)

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
        self.invalid_reason = (f"Zerodha cancelled today's Kite token at {datetime.now(IST):%H:%M} IST. Zerodha does that when the "
                               "same account logs in to this Kite Connect app somewhere else (another bot or script using the "
                               "same API key), and when its own daily reset ends the login. To log in again, open Admin → Data "
                               "and jobs and press \"Run the automatic login now\" (or log in by hand there).")
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

    def derivative_names(self) -> set[str]:
        """The underlyings the derivatives segment lists today (stock symbols and index names). A stock in this set
        closes through the closing auction (data/sessions.py)."""
        self._load_instruments()
        if getattr(self, "_deriv_of", None) is not self._inst:
            self._deriv, self._deriv_of = {str(r["name"]).upper() for r in self._inst if r["fno"]}, self._inst
        return self._deriv

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

    ALIASES = name_search.ALIASES["IN"]      # short names people use ("RIL", "Airtel"), and renamed symbols
    INDEX_DERIVATIVES = {"NIFTY 50": "NIFTY", "NIFTY BANK": "BANKNIFTY", "NIFTY FIN SERVICE": "FINNIFTY",
                         "NIFTY MID SELECT": "MIDCPNIFTY"}

    def _names(self) -> "name_search.NameIndex":
        """The day's stocks, indices and BSE-only companies by symbol, name, short name, BSE code and ISIN. The
        exchange's own list of companies (`names_fn`: {isin: [symbol, name]}) adds each company's full name and ISIN
        beside the broker's shortened one ("APOLLO HOSPITALS ENTER. L"). Rebuilt when either list changes."""
        self._load_instruments()
        try:
            listed = (self.names_fn() if self.names_fn else None) or _NO_NAMES
        except Exception:
            listed = _NO_NAMES
        if not self._names_of or self._names_of[0] is not self._inst or self._names_of[1] is not listed:
            full = {}
            for isin, v in listed.items():
                if isinstance(v, (list, tuple)) and len(v) == 2 and v[0]:
                    full[str(v[0]).upper()] = (str(v[1] or ""), str(isin).upper())
            from . import universes
            boost = {s for p in universes.PRESETS["IN"] for s in p["symbols"]}
            rows = [r for r in self._inst if not r["fno"]]
            base = lambda r: r["symbol"].split("-")[0] if r["exchange"] == "NSE" else r["symbol"]    # noqa: E731
            idx = name_search.NameIndex(
                rows, names=lambda r: [full[base(r)][0]] if base(r) in full and r["type"] == "EQ" else [],
                codes=lambda r: [r.get("bse_code"), full[base(r)][1] if base(r) in full and r["type"] == "EQ" else None],
                rank=lambda r: 0 if r["type"] == "INDEX" else 1 if r["type"] == "EQ" else 2, boost=boost, aliases=self.ALIASES)
            fno = sorted((r["symbol"].upper(), r["expiry"] or "", r["token"]) for r in self._inst if r["fno"])
            by_name: dict[str, list[dict]] = {}
            for r in self._inst:
                if r["fno"]:
                    by_name.setdefault(str(r["name"]).upper(), []).append(r)
            self._names_idx = {"idx": idx, "fno": fno, "by_name": by_name,
                               "full": {s: v[0] for s, v in full.items() if v[0]}}
            self._names_of = (self._inst, listed)
        return self._names_idx

    def company_name(self, symbol: str) -> str | None:
        """The company's full name from the exchange's list ("Apollo Hospitals Enterprise Limited"), when it's known."""
        return self._names()["full"].get(symbol.split("-")[0].upper())

    def search(self, q: str, allow_fno: bool, limit: int = 25) -> list[dict]:
        """Stocks, indices and (when allowed) futures and options for what's typed, best first (name_search's groups),
        each a copy with `match` (its group) and the company's full name where the exchange's list has it. Contracts
        come after the stock or index they're on: by symbol, or by the company's name ("hdfc bank" → HDFCBANK futures)."""
        q = q.strip()
        if len(q) < 2:
            return []
        n = self._names()
        hits = n["idx"].search(q, limit)
        full = n["full"]

        def shown(r, t):
            name = full.get(r["symbol"].split("-")[0].upper()) if r["type"] == "EQ" and r["exchange"] == "NSE" else None
            return {**r, "match": t, **({"name": name} if name else {})}
        out = [(t, 0, (k,), shown(r, t)) for k, (t, r) in enumerate(hits)]
        if allow_fno:
            qs = q.upper()
            seen = set()
            ranked = {"FUT": 2}                 # futures before options, as before
            j = bisect_left(n["fno"], (qs,))
            while j < len(n["fno"]) and n["fno"][j][0].startswith(qs):
                tok = n["fno"][j][2]
                seen.add(tok)
                r = self._by_token[tok]
                t = name_search.EXACT if n["fno"][j][0] == qs else name_search.SYMBOL
                out.append((t, 1, (ranked.get(r["type"], 3), r["expiry"] or "", r["symbol"]), shown(r, t)))
                j += 1
            if hits and hits[0][0] <= name_search.NAME:
                top = hits[0][1]
                under = self.INDEX_DERIVATIVES.get(top["symbol"], top["symbol"]) if top["type"] == "INDEX" else top["symbol"]
                for r in n["by_name"].get(under.upper(), []):
                    if r["token"] not in seen:
                        out.append((hits[0][0], 1, (ranked.get(r["type"], 3), r["expiry"] or "", r["symbol"]), shown(r, hits[0][0])))
        out.sort(key=lambda x: x[:3])
        return [x[3] for x in out[:limit]]

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
            traded = v.get("last_trade_time")
            if hasattr(traded, "tzinfo") and traded.tzinfo is None:
                traded = traded.replace(tzinfo=IST)          # the broker's clock is India's: say so, so no reader's zone moves it
            out[keys.get(k, k.split(":", 1)[1])] = {
                "price": last, "prev_close": prev, "open": ohlc.get("open"), "high": ohlc.get("high"),
                "low": ohlc.get("low"), "volume": v.get("volume"), "at": traded.isoformat() if hasattr(traded, "isoformat") else None,
                "change": (last - prev) if last is not None and prev else None,
                "change_pct": ((last / prev - 1) * 100) if last is not None and prev else None,
            }
        return out

    def index_quotes(self, keys: list[str]) -> dict[str, dict]:
        """Indices' live levels by their quote keys ("NSE:NIFTY 50", "BSE:SENSEX"): the level, the day's range, the previous
        close and the change against it, and the time of the reading. BSE's indices aren't in the day's instrument list
        (only BSE-only companies are kept), so each answer's instrument token is kept for its candles (index_token)."""
        self._require()
        self._throttle()
        data = self.kite.quote(list(keys))
        tokens = self.__dict__.setdefault("_index_tokens", {})
        out = {}
        for k, v in data.items():
            if v.get("instrument_token"):
                tokens[k] = int(v["instrument_token"])
            ohlc = v.get("ohlc") or {}
            prev = ohlc.get("close") or None
            last = v.get("last_price")
            at = v.get("timestamp") or v.get("last_trade_time")
            if hasattr(at, "tzinfo") and at.tzinfo is None:
                at = at.replace(tzinfo=IST)
            out[k] = {"price": last, "prev_close": prev, "open": ohlc.get("open"), "high": ohlc.get("high"), "low": ohlc.get("low"),
                      "at": at.isoformat() if hasattr(at, "isoformat") else None, "token": v.get("instrument_token"),
                      "change": (last - prev) if last is not None and prev else None,
                      "change_pct": ((last / prev - 1) * 100) if last is not None and prev else None}
        return out

    def index_token(self, key: str) -> int | None:
        """The instrument token of an index by its quote key, from a quote of it (kept for the day's process)."""
        tokens = self.__dict__.setdefault("_index_tokens", {})
        if key not in tokens:
            self.index_quotes([key])
        return tokens.get(key)

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
        own = self.session_close.get(int(token))
        out_at = self._close_out(now) if not own else self._close_out_at(now, own)
        if hit and time.time() - hit[0] < ttl and not (tf == "1d" and hit[0] < out_at <= time.time()):
            return self._official_days(token, tf, self._with_tail(token, tf, hit[1], continuous=continuous))
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
        dedup = self._with_tail(token, tf, dedup, note=True, continuous=continuous)
        if not store:
            return self._official_days(token, tf, dedup)
        self._cache[key] = (time.time(), dedup)
        if len(self._cache) > 300:
            self._cache.pop(next(iter(self._cache)))
        return self._official_days(token, tf, dedup)

    TAIL = 200        # candles kept per token and timeframe: a day and more of 5-minute candles
    TAIL_FOR = 12 * 3600   # ...and for how long they count

    def _with_tail(self, token, tf: str, bars: list[dict], note: bool = False, continuous: bool = False) -> list[dict]:
        """Candles that end no earlier than the newest ones already seen for this token and timeframe. For a while around
        midnight India time the broker's history service answered some ranges from an older copy: TCS's 5-year, all-time
        and intraday candles ended on 8 Oct while the 1-year range, read earlier, had 9 Oct (R11C-012). An answer that ends
        before candles already seen keeps those newer candles, so every range and candle size ends on the same day; with
        `note`, the answer (a fresh one) also becomes the newest seen when it is. The list given is never changed."""
        key = (str(token), tf, bool(continuous))
        kept = self._tails.get(key)
        tail = kept[1] if kept and time.time() - kept[0] < self.TAIL_FOR else None
        if bars and tail and str(tail[-1]["t"]) > str(bars[-1]["t"]):
            last = str(bars[-1]["t"])
            bars = [*bars, *(b for b in tail if str(b["t"]) > last)]
        if note and bars and (not tail or str(bars[-1]["t"]) >= str(tail[-1]["t"])):
            if len(self._tails) > 2000:
                self._tails.clear()
            self._tails[key] = (time.time(), [dict(b) for b in bars[-self.TAIL:]])
        return bars

    @staticmethod
    def _close_out(now: datetime) -> float:
        """When today's official closes are all out (a couple of minutes after the closing auction matches), as a
        timestamp: a daily candle read before it is read again after it (R8B-001)."""
        from .data import sessions as S
        local = now.astimezone(IST)
        return (S.at(local.date(), S.close_known("cas", local.date())) + timedelta(minutes=2)).timestamp()

    @staticmethod
    def _close_out_at(now: datetime, hhmm: str) -> float:
        """Today's close of a segment that closes at `hhmm` IST, plus two minutes, as a timestamp."""
        local = now.astimezone(IST)
        h, m = (int(x) for x in hhmm.split(":"))
        return (local.replace(hour=h, minute=m, second=0, microsecond=0) + timedelta(minutes=2)).timestamp()

    def _official_days(self, token, tf: str, bars: list[dict]) -> list[dict]:
        """A stock's daily candles with each recent day's close the exchange's official close (R8B-001: the broker's
        candle kept the last trade before the closing auction, TCS 2,171.50 against the official 2,156.00)."""
        # the exchange's official close of a stock's day (official_close.history_close), set on the app's broker by main:
        # (candles, symbol, kind, exchange) -> candles; none set, the broker's candles as they are
        fn = self.__dict__.get("day_close")
        if tf != "1d" or not fn or not bars:
            return bars
        inst = self._by_token.get(int(token)) if str(token).isdigit() else None
        if not inst or inst.get("type") != "EQ" or inst.get("exchange") not in ("NSE", "BSE"):
            return bars
        try:
            from .data import sessions as S
            kind = S.kind_of(inst, self.derivative_names())
            return fn(bars, inst["symbol"], kind, inst["exchange"])
        except Exception as e:                       # the broker's candles rather than none
            print("official close for candles:", inst.get("symbol"), str(e)[:120])
            return bars

    def day_quotes(self) -> dict[str, dict]:
        """Every NSE stock's quote ({symbol: {"price", "at"}}), in batches of 500: read once after the close for the
        day's official closes until the exchange's file is out."""
        self._require()
        rows = [r for r in self.equities() if r["exchange"] == "NSE"]
        out: dict[str, dict] = {}
        for i in range(0, len(rows), 500):
            part = {f"NSE:{r['symbol']}": r["symbol"] for r in rows[i:i + 500]}
            self._throttle()
            for k, v in (self.kite.quote(list(part)) or {}).items():
                traded = v.get("last_trade_time")
                if hasattr(traded, "tzinfo") and traded.tzinfo is None:
                    traded = traded.replace(tzinfo=IST)
                out[part.get(k, k.split(":", 1)[-1])] = {"price": v.get("last_price"),
                                                         "at": traded.isoformat() if hasattr(traded, "isoformat") else None}
        return out

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
