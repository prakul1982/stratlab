"""Option contracts, chains, live quotes and margins from Kite (NSE, BSE, MCX and NSE currency options)."""
import threading
import time

from .engine import Contracts
from ..kite_service import ist_date
from ..data.expiries import keep_listed

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
            for r in rows:
                if r["type"] == "FUT" or r["expiry"] < today:
                    continue
                k = (exch, r["name"])
                u = seen.setdefault(k, {"exchange": exch, "name": r["name"], "lot": r["lot"], "expiries": set()})
                u["expiries"].add(r["expiry"])
        rank = {k: i for i, k in enumerate(POPULAR)}
        out = []
        for k, u in seen.items():
            ex = keep_listed(u["exchange"], u["name"], sorted(u["expiries"]))
            out.append({"exchange": u["exchange"], "name": u["name"], "lot": u["lot"], "expiries": ex[:6],
                        "venue": EXCHANGE_NAME[u["exchange"]], "popular": k in rank, "freeze": freeze(u["name"]),
                        "index": k in INDEX_SPOT})
        out.sort(key=lambda u: (rank.get((u["exchange"], u["name"]), 99), u["exchange"] != "NFO", u["name"]))
        return out

    def expiries(self, exchange: str, name: str) -> list[str]:
        """The option's expiries still to come, as listed; a monthly-only index's list never carries a weekly date
        (data/expiries.py)."""
        self._load()
        today = ist_date().isoformat()
        return keep_listed(exchange, name, sorted({r["expiry"] for r in self._rows.get(exchange, [])
                                                   if r["name"] == name and r["type"] != "FUT" and r["expiry"] >= today}))

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
                         "volume": v.get("volume"), "ts": ts.isoformat() if hasattr(ts, "isoformat") else ts}
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

    def chain(self, exchange: str, name: str, choice: str, around: int = 10) -> dict:
        c = self.contracts(exchange, name, choice)
        if not c:
            return {"expiry": None, "rows": [], "spot": None}
        sk = self.spot_key(exchange, name, c.expiry)
        spot_q = self.quotes([sk]).get(sk) if sk else None
        spot = spot_q.get("ltp") if spot_q else None
        mid = c.atm(spot) if spot else c.strikes[len(c.strikes) // 2]
        i = c.strikes.index(mid)
        strikes = c.strikes[max(0, i - around): i + around + 1]
        keys = [c.key(o, k) for k in strikes for o in ("CE", "PE")]
        q = self.quotes([k for k in keys if k])
        rows = [{"strike": k, "ce": q.get(c.key("CE", k)), "pe": q.get(c.key("PE", k))} for k in strikes]
        return {"expiry": c.expiry, "expiries": self.expiries(exchange, name)[:6], "lot": c.lot, "spot": spot,
                "atm": mid, "step": c.step(mid), "rows": rows, "spot_ts": spot_q.get("ts") if spot_q else None,
                "freeze": freeze(name)}

    def settlement_price(self, exchange: str, name: str, expiry: str) -> float | None:
        """The price NSE and BSE options settle at on their expiry day: the underlying's official close that day (the
        index close; for a stock, the auction close). Stock contracts settle at the volume-weighted average of the
        exchanges' closes; this uses the close on the exchange named here, nearly all the volume. None before the
        close is out, and for commodity and currency options (they settle on other rules)."""
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
                   "product": "NRML", "order_type": "MARKET", "quantity": int(l["qty"]), "price": 0, "trigger_price": 0}
                  for l in legs]
        try:
            self.kite._throttle()
            r = self.kite.kite.basket_order_margins(orders, consider_positions=False, mode="compact")
            return float((r.get("final") or r.get("initial") or {}).get("total") or 0) or None
        except Exception as e:
            print("margin call failed:", e)
            return None
