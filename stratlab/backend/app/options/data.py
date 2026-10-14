"""Option contracts, chains, live quotes and margins from Kite (NSE, BSE, MCX and NSE currency options)."""
import threading
import time
from datetime import date, timedelta

from .engine import Contracts
from ..kite_service import ist_date
from ..data.expiries import keep_listed
from ..data.calendar import is_trading_day
from ..data.markets import BY_ID

# when currency options stop trading on their expiry day, India time
CDS_EXPIRY_TIME = "12:30"
# how long after the expiry time the live price still counts as the settlement estimate
SETTLE_GRACE = timedelta(minutes=5)


def expiry_time(exchange: str, day=None) -> str | None:
    """When an exchange's options stop trading on their expiry day, India time ("HH:MM"). F&O follows the derivatives
    close (data/sessions.py). MCX closes at 23:30, and at 23:55 while US daylight saving is off (first Sunday of
    November to the second Sunday of March)."""
    from datetime import date, timedelta
    from ..data import sessions
    d = date.fromisoformat(str(day)[:10]) if day else ist_date()
    if exchange in ("NFO", "BFO"):
        return sessions.fo_close(d).strftime("%H:%M")
    if exchange == "CDS":
        return CDS_EXPIRY_TIME
    if exchange == "MCX":
        nov = date(d.year, 11, 1)
        nov += timedelta(days=(6 - nov.weekday()) % 7)       # first Sunday of November
        mar = date(d.year, 3, 1)
        mar += timedelta(days=(6 - mar.weekday()) % 7 + 7)   # second Sunday of March
        return "23:55" if d >= nov or d < mar else "23:30"
    return None


def expired_today(exchange: str, now=None) -> bool:
    """Whether today's expiry on this exchange has passed (its contracts stopped trading for good)."""
    from ..kite_service import IST
    from datetime import datetime
    local = (now or datetime.now(IST)).astimezone(IST)
    at = expiry_time(exchange, local.date())
    return bool(at) and local.strftime("%H:%M") >= at

# the index each index option settles against; stock options use the NSE cash stock
INDEX_SPOT = {
    ("NFO", "NIFTY"): "NSE:NIFTY 50", ("NFO", "BANKNIFTY"): "NSE:NIFTY BANK",
    ("NFO", "FINNIFTY"): "NSE:NIFTY FIN SERVICE", ("NFO", "MIDCPNIFTY"): "NSE:NIFTY MID SELECT",
    ("NFO", "NIFTYNXT50"): "NSE:NIFTY NEXT 50",
    ("BFO", "SENSEX"): "BSE:SENSEX", ("BFO", "BANKEX"): "BSE:BANKEX", ("BFO", "SENSEX50"): "BSE:SENSEX50",
}
POPULAR = [("NFO", "NIFTY"), ("NFO", "BANKNIFTY"), ("BFO", "SENSEX"), ("NFO", "FINNIFTY"), ("NFO", "MIDCPNIFTY"),
           ("BFO", "BANKEX"), ("MCX", "CRUDEOIL"), ("MCX", "NATURALGAS"), ("MCX", "GOLDM"), ("MCX", "SILVERM"), ("CDS", "USDINR")]
# most units allowed in one order (the exchange's quantity freeze limit); check your broker, these change. NSE
# revises its index limits every few months (rules.py lists the circular and the day it was checked).
# Before 5 Oct 2026: NSE/FAOP/68834 (30 Jun 2025, from 1 Jul 2025), BANKNIFTY 600; NIFTYFPI (Nifty India FPI 150,
# F&O from 12 Aug 2026) 8,500 from 1 Sep 2026. From 5 Oct 2026: NSE/FAOP/76693 (1 Oct 2026). Checked 5 Oct 2026.
FREEZE_BEFORE = {"NIFTY": 1800, "BANKNIFTY": 600, "FINNIFTY": 1800, "MIDCPNIFTY": 2800, "NIFTYNXT50": 600,
                 "NIFTYFPI": 8500, "SENSEX": 1000, "BANKEX": 900}
FREEZE_FROM = "2026-10-05"           # NSE's revised index limits apply from this day
FREEZE = {**FREEZE_BEFORE, "NIFTY": 3510, "BANKNIFTY": 1440, "FINNIFTY": 3240, "MIDCPNIFTY": 5760, "NIFTYNXT50": 1125,
          "NIFTYFPI": 53900}


def freeze(name: str, day: str | None = None) -> int:
    """The freeze limit for an underlying on a day (today in India by default); 0 when none is known."""
    table = FREEZE if (day or ist_date().isoformat()) >= FREEZE_FROM else FREEZE_BEFORE
    return table.get(name, 0)
EXCHANGE_NAME = {"NFO": "NSE", "BFO": "BSE", "MCX": "MCX", "CDS": "NSE currency"}
CDS_UNITS = 1000     # currency contracts are 1,000 units (JPYINR: 100,000 yen, quoted per 100); Kite lists the lot as 1
FRESH_SECONDS = 120
QUOTE_GAP = 1.05     # Kite allows one quote request a second per account, shared by every session
REFRESH = 1.0        # a quote older than this is refreshed when someone else's request goes out anyway
WANT_FOR = 30        # a contract asked for in the last 30 s rides along with everyone else's requests
BATCH = 450          # contracts per quote request (Kite allows 500)


def cds_hours() -> tuple[str, str]:
    """When NSE currency trades, India time (09:00-17:00)."""
    h = BY_ID["CDS"]["hours"]
    return h["open"], h["close"]


def cds_open(now) -> bool:
    """Whether NSE currency is trading at a moment."""
    from ..kite_service import IST
    local = now.astimezone(IST)
    lo, hi = cds_hours()
    return is_trading_day("CDS", local.date()) and lo <= local.strftime("%H:%M") <= hi


def broker_qty(key: str, units: float) -> int:
    """An order's quantity as the broker counts it: units of the underlying, except NSE currency contracts, which the
    broker counts in lots (one USDINR lot is 1,000 dollars; the app holds units, CDS_UNITS a lot). R11C-007: the margin
    asked for 1,000 lots of a one-lot USDINR condor, ₹10.3 lakh for a structure that could lose ₹30 to ₹400."""
    if str(key).startswith("CDS:"):
        return max(1, int(round(float(units) / CDS_UNITS)))
    return int(units)


def no_live_quote(q: dict | None) -> bool:
    """Whether a quote is no live quote at all: nothing to buy or sell at (no bid, no ask) and not one contract traded
    (volume 0), so its last price is whatever the contract last traded at, which can be weeks old. R13-002: every
    USDINR option on 9 Oct 2026 had bid and ask null, OI 0 and volume 0, the future's price 96.135 since 9 Sep, while
    the dollar was at 96.76. A quote that traded today, or has a bid or an ask, is live; one with no volume figure at all
    can't be judged here and counts as live (R11C-007's banner says when a fill is a last trade)."""
    if not q:
        return True
    if any((q.get(k) or 0) > 0 for k in ("bid", "ask")):
        return False
    vol = q.get("volume")
    return vol is not None and not vol


def frozen_series(bars: list[dict] | None, n: int = 5) -> bool:
    """Whether a run of daily candles is one standing price, not trading: the last `n` candles all have volume 0 and the
    same open, high, low and close (R13-002: USDINR's 1-day CDS candles were o=h=l=c=96.135, volume 0, every day from
    9 Sep to 9 Oct 2026)."""
    tail = [b for b in (bars or [])][-n:]
    if len(tail) < n:
        return False
    first = tail[0].get("c")
    return all(not (b.get("v") or 0) and b.get("o") == b.get("h") == b.get("l") == b.get("c") == first for b in tail)


# NSE currency options settle at the RBI reference rate, a spot rate: with no live future, the underlying is the spot
# pair's price (rupees per unit; JPYINR is quoted per 100 yen)
SPOT_PAIRS = {"USDINR": ("USDINR=X", 1.0), "EURINR": ("EURINR=X", 1.0), "GBPINR": ("GBPINR=X", 1.0), "JPYINR": ("JPYINR=X", 100.0)}
NO_LIVE = ("No live quote: {name}'s options on NSE currency have no bid or ask and nothing traded today, so the last prices "
           "shown can be weeks old. The structure isn't priced until there is a live quote.")


class OptionsData:
    def __init__(self, kite):
        self.kite = kite                 # KiteService
        self._rows: dict[str, list[dict]] = {}
        self._day = None
        self._lock = threading.Lock()
        self._qcache: dict[str, tuple[float, dict]] = {}
        self._qlock = threading.Lock()
        self._wanted: dict[str, float] = {}      # contract key -> when a session last asked for it
        self._last_quote = 0.0
        self.quote_calls = 0
        self.spot_source = None          # pair -> its price now ("USDINR=X" -> 96.76) or {"price", "at"}, set by main for currency options
        self.spot_close = None           # (pair, day) -> that day's close, set by main for currency options

    def ready(self) -> bool:
        return self.kite.ready()

    # ---------- contracts ----------
    def _load(self):
        today = ist_date().isoformat()
        with self._lock:
            if self._day == today and self._rows:
                return
            self.kite._require()
            rows: dict[str, list[dict]] = {}
            for exch in ("NFO", "BFO", "MCX", "CDS"):
                self.kite._throttle()
                out = []
                for x in self.kite.kite.instruments(exch):
                    t = x.get("instrument_type")
                    if t not in ("CE", "PE", "FUT") or not x.get("expiry"):
                        continue
                    if exch == "CDS" and not str(x.get("name") or "").upper().endswith("INR"):
                        continue                             # cross pairs (EURUSD…) are priced in dollars or yen: futures only
                    lot = int(x.get("lot_size") or 1)
                    if exch == "CDS" and lot < 100:          # a premium of ₹0.25 on USDINR is ₹250 a lot
                        lot *= CDS_UNITS
                    out.append({"symbol": x["tradingsymbol"], "name": x.get("name") or "", "type": t,
                                "strike": float(x.get("strike") or 0), "expiry": x["expiry"].isoformat(),
                                "lot": lot, "exchange": exch})
                rows[exch] = out
            self._rows, self._day = rows, today

    def underlyings(self) -> list[dict]:
        self._load()
        today = ist_date().isoformat()
        seen: dict[tuple, dict] = {}
        for exch, rows in self._rows.items():
            # today's expiry is gone once its contracts have stopped trading, as in expiries(): the "Nearest" the page names
            # is the one priced (R11C-007: "Nearest · Fri, 9 Oct" after USDINR's 12:30 expiry, priced on 16 Oct)
            gone = today if expired_today(exch) else None
            for r in rows:
                if r["type"] == "FUT" or r["expiry"] < today or r["expiry"] == gone:
                    continue
                k = (exch, r["name"])
                u = seen.setdefault(k, {"exchange": exch, "name": r["name"], "lot": r["lot"], "lot_expiry": r["expiry"],
                                        "expiries": set(), "lots": {}})
                if r["expiry"] < u["lot_expiry"]:        # the lot of the nearest listed expiry
                    u["lot"], u["lot_expiry"] = r["lot"], r["expiry"]
                u["expiries"].add(r["expiry"])
                u["lots"].setdefault(r["expiry"], r["lot"])
        rank = {k: i for i, k in enumerate(POPULAR)}
        out = []
        for k, u in seen.items():
            ex = keep_listed(u["exchange"], u["name"], sorted(u["expiries"]))
            # "lot" is the nearest expiry's; a later series can have another (an exchange revises lots at a series boundary), so
            # each listed expiry's own is in "lots"
            out.append({"exchange": u["exchange"], "name": u["name"], "lot": u["lot"], "expiries": ex[:6], "lots": {e: u["lots"][e] for e in ex[:6]},
                        "venue": EXCHANGE_NAME[u["exchange"]], "popular": k in rank, "freeze": freeze(u["name"]),
                        "index": k in INDEX_SPOT})
        out.sort(key=lambda u: (rank.get((u["exchange"], u["name"]), 99), u["exchange"] != "NFO", u["name"]))
        return out

    def expiries(self, exchange: str, name: str) -> list[str]:
        """The option's expiries still to come, as listed; a monthly-only index's list never carries a weekly date
        (data/expiries.py). Today's expiry is gone once its contracts have expired for the day (R6O-019: "SENSEX
        8 Oct · weekly" listed at 23:45 on 8 Oct)."""
        self._load()
        today = ist_date().isoformat()
        gone = today if expired_today(exchange) else None
        return keep_listed(exchange, name, sorted({r["expiry"] for r in self._rows.get(exchange, [])
                                                   if r["name"] == name and r["type"] != "FUT" and r["expiry"] >= today
                                                   and r["expiry"] != gone}))

    def pick_expiry(self, exchange: str, name: str, choice: str) -> str | None:
        ex = self.expiries(exchange, name)
        if not ex:
            return None
        if choice == "current":
            return ex[0]
        if choice == "next":
            return ex[1] if len(ex) > 1 else ex[0]
        if choice == "month":   # the last expiry of the nearest month
            month = ex[0][:7]
            return [e for e in ex if e[:7] == month][-1]
        return choice if choice in ex else None

    def contracts(self, exchange: str, name: str, choice: str) -> Contracts | None:
        e = self.pick_expiry(exchange, name, choice)
        if not e:
            return None
        rows = [{"opt": r["type"], "strike": r["strike"], "symbol": r["symbol"], "lot": r["lot"]}
                for r in self._rows.get(exchange, []) if r["name"] == name and r["expiry"] == e and r["type"] != "FUT"]
        if not rows:
            return None
        return Contracts(rows, rows[0]["lot"], e, exchange)

    def spot_key(self, exchange: str, name: str, expiry: str | None = None) -> str | None:
        if (exchange, name) in INDEX_SPOT:
            return INDEX_SPOT[(exchange, name)]
        if exchange in ("MCX", "CDS"):   # commodity and currency options follow the nearest future at or after expiry
            self._load()
            futs = sorted((r for r in self._rows.get(exchange, []) if r["name"] == name and r["type"] == "FUT"
                           and r["expiry"] >= (expiry or ist_date().isoformat())), key=lambda r: r["expiry"])
            return f"{exchange}:{futs[0]['symbol']}" if futs else None
        return f"NSE:{name}"

    # ---------- quotes ----------
    def quotes(self, keys: list[str], max_age: float = 3.0) -> dict[str, dict]:
        """Bid, ask, last price and quote time for each key.

        Every session shares one stream of quote requests, at most one a second (Kite's limit): a request carries
        what the caller needs plus every other session's recently wanted contracts that are going stale, so the
        next session to ask usually finds its prices already fresh. That keeps a hundred sessions under the limit
        where one request per session per poll would stop at two or three."""
        keys = [k for k in dict.fromkeys(keys) if k]
        with self._qlock:
            now = time.time()
            for k in keys:
                self._wanted[k] = now
            out, need = {}, []
            for k in keys:
                hit = self._qcache.get(k)
                if hit and now - hit[0] < max_age:
                    out[k] = hit[1]
                else:
                    need.append(k)
            if not need:
                return out
            self._wanted = {k: t for k, t in self._wanted.items() if t >= now - WANT_FOR}
            if len(self._qcache) > 5000:            # contracts nobody watches any more
                self._qcache = {k: v for k, v in self._qcache.items() if now - v[0] < 300}
            extra = [k for k in self._wanted if k not in out and k not in need
                     and (k not in self._qcache or now - self._qcache[k][0] >= REFRESH)]
            batch = need + extra[:max(0, BATCH - len(need) % BATCH)] if len(need) % BATCH else need
            for i in range(0, len(batch), BATCH):
                wait = self._last_quote + QUOTE_GAP - time.time()
                if wait > 0:
                    time.sleep(wait)
                self.kite._require()
                self.kite._throttle()
                data = self.kite.kite.quote(batch[i:i + BATCH])
                self._last_quote, self.quote_calls = time.time(), self.quote_calls + 1
                for k, v in data.items():
                    d = v.get("depth") or {}
                    bid = next((x["price"] for x in d.get("buy", []) if x.get("price")), None)
                    ask = next((x["price"] for x in d.get("sell", []) if x.get("price")), None)
                    ts = v.get("timestamp") or v.get("last_trade_time")
                    q = {"ltp": v.get("last_price"), "bid": bid, "ask": ask, "oi": v.get("oi"),
                         "volume": v.get("volume"), "ts": ts.isoformat() if hasattr(ts, "isoformat") else ts,
                         "close": (v.get("ohlc") or {}).get("close")}         # the previous session's close
                    self._qcache[k] = (self._last_quote, q)
            for k in need:
                if k in self._qcache:
                    out[k] = self._qcache[k][1]
            return out

    @staticmethod
    def fresh(q: dict | None, now) -> bool:
        """True when a quote is recent: False on holidays, after hours and on a dead feed."""
        if not q or not q.get("ts"):
            return False
        from datetime import datetime
        try:
            ts = datetime.fromisoformat(str(q["ts"]))
        except ValueError:
            return False
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=now.tzinfo)
        return abs((now - ts).total_seconds()) <= FRESH_SECONDS

    def spot(self, exchange: str, name: str, expiry: str | None = None) -> tuple[float | None, dict | None, str]:
        """(price, quote, where it came from) of an option's underlying. A currency option's future with no live quote
        (no bid or ask, nothing traded: R13-002's USDINR at a month-old 96.135) gives way to the spot pair, the rate the
        options settle against: "spot". Otherwise the future's or index's own quote: "quote"."""
        sk = self.spot_key(exchange, name, expiry)
        q = self.quotes([sk]).get(sk) if sk else None
        if exchange == "CDS" and no_live_quote(q) and name in SPOT_PAIRS and callable(self.spot_source):
            pair, per = SPOT_PAIRS[name]
            try:
                px = self.spot_source(pair)
            except Exception as e:                     # no spot either: the caller says the price can't be had
                print("currency spot unavailable:", pair, str(e)[:120])
                px = None
            at = None
            if isinstance(px, dict):                   # the price and when the source quoted it
                px, at = px.get("price"), px.get("at")
            if px:
                return round(float(px) * per, 4), {"ltp": round(float(px) * per, 4), "ts": at}, "spot"
            return None, q, "none"
        return (q or {}).get("ltp"), q, "quote"

    def chain(self, exchange: str, name: str, choice: str, around: int = 10) -> dict:
        c = self.contracts(exchange, name, choice)
        if not c:
            return {"expiry": None, "rows": [], "spot": None}
        spot, spot_q, spot_from = self.spot(exchange, name, c.expiry)
        mid = c.atm(spot) if spot else c.strikes[len(c.strikes) // 2]
        i = c.strikes.index(mid)
        strikes = c.strikes[max(0, i - around): i + around + 1]
        keys = [c.key(o, k) for k in strikes for o in ("CE", "PE")]
        q = self.quotes([k for k in keys if k])
        rows = [{"strike": k, "ce": q.get(c.key("CE", k)), "pe": q.get(c.key("PE", k))} for k in strikes]
        return {"exchange": exchange, "expiry": c.expiry, "expiries": self.expiries(exchange, name)[:6], "lot": c.lot, "spot": spot,
                "atm": mid, "step": c.step(mid), "rows": rows, "spot_ts": spot_q.get("ts") if spot_q else None,
                "spot_from": spot_from, "freeze": freeze(name)}

    def settlement_price(self, exchange: str, name: str, expiry: str) -> float | None:
        """The price NSE and BSE options settle at on their expiry day: the underlying's official close that day (the
        index close; for a stock, the auction close). Stock contracts settle at the volume-weighted average of the
        exchanges' closes; this uses the close on the exchange named here, nearly all the volume. None before the
        close is out. Commodity and currency options settle on other rules (the RBI reference rate, the futures'
        final settlement price) that aren't available here: they get the underlying's last price, an estimate; checked
        more than SETTLE_GRACE after the expiry time, the underlying's close on the expiry day, else None."""
        if exchange in ("MCX", "CDS"):
            from datetime import datetime, time as dtime
            from zoneinfo import ZoneInfo
            now = datetime.now(ZoneInfo("Asia/Kolkata"))
            end = datetime.combine(date.fromisoformat(expiry), dtime.fromisoformat(expiry_time(exchange, expiry)), now.tzinfo)
            if now - end <= SETTLE_GRACE:
                return self.spot(exchange, name, expiry)[0]
            from ..live import official_close
            key = self.spot_key(exchange, name, expiry)
            if exchange == "CDS":
                if now < datetime.combine(end.date(), dtime.fromisoformat(cds_hours()[1]), now.tzinfo):
                    return None                    # the day's bar is still forming: the engine holds the live estimate
                q = self.quotes([key]).get(key) if key else None
                if name in SPOT_PAIRS and no_live_quote(q) and callable(self.spot_close):
                    pair, per = SPOT_PAIRS[name]
                    try:
                        px = self.spot_close(pair, expiry)
                    except Exception as e:
                        print("currency spot close unavailable:", pair, str(e)[:120])
                        px = None
                    if px:
                        return round(float(px) * per, 4)
            try:
                inst = self.kite.by_symbol(*reversed(key.split(":", 1))) if key else None
            except Exception as e:
                print("settlement price: no instrument list:", e)
                inst = None
            return official_close(self.kite, inst, expiry) if inst else None
        if exchange not in ("NFO", "BFO"):
            return None
        from ..data import sessions
        from ..live import official_close, session_kind
        key = self.spot_key(exchange, name, expiry)
        if not key:
            return None
        ex, sym = key.split(":", 1)
        try:
            inst = self.kite.by_symbol(sym, ex)
        except Exception as e:
            print("settlement price: no instrument list:", e)
            inst = None
        if inst:
            kind = session_kind(self.kite, inst)
            from datetime import datetime
            from zoneinfo import ZoneInfo
            now = datetime.now(ZoneInfo("Asia/Kolkata"))
            if expiry == now.date().isoformat() and now.time() < sessions.close_known(kind, now.date()):
                return None
            return official_close(self.kite, inst, expiry)
        return None

    # ---------- margin ----------
    def margin(self, legs: list[dict]) -> float | None:
        """The broker's margin for a basket (hedge benefit included), or None if it can't be had."""
        orders = [{"exchange": l["key"].split(":", 1)[0], "tradingsymbol": l["key"].split(":", 1)[1],
                   "transaction_type": "SELL" if l["side"] == "sell" else "BUY", "variety": "regular",
                   "product": "NRML", "order_type": "MARKET", "quantity": broker_qty(l["key"], l["qty"]), "price": 0, "trigger_price": 0}
                  for l in legs]
        try:
            self.kite._throttle()
            r = self.kite.kite.basket_order_margins(orders, consider_positions=False, mode="compact")
            return float((r.get("final") or r.get("initial") or {}).get("total") or 0) or None
        except Exception as e:
            print("margin call failed:", e)
            return None
