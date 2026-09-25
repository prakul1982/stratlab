"""Option contracts, chains, live quotes and margins from Kite (NSE, BSE and MCX)."""
import threading
import time
from datetime import date

from .engine import Contracts

# the index each index option settles against; stock options use the NSE cash stock
INDEX_SPOT = {
    ("NFO", "NIFTY"): "NSE:NIFTY 50", ("NFO", "BANKNIFTY"): "NSE:NIFTY BANK",
    ("NFO", "FINNIFTY"): "NSE:NIFTY FIN SERVICE", ("NFO", "MIDCPNIFTY"): "NSE:NIFTY MID SELECT",
    ("NFO", "NIFTYNXT50"): "NSE:NIFTY NEXT 50",
    ("BFO", "SENSEX"): "BSE:SENSEX", ("BFO", "BANKEX"): "BSE:BANKEX", ("BFO", "SENSEX50"): "BSE:SENSEX50",
}
POPULAR = [("NFO", "NIFTY"), ("NFO", "BANKNIFTY"), ("BFO", "SENSEX"), ("NFO", "FINNIFTY"), ("NFO", "MIDCPNIFTY"),
           ("BFO", "BANKEX"), ("MCX", "CRUDEOIL"), ("MCX", "NATURALGAS"), ("MCX", "GOLDM"), ("MCX", "SILVERM")]
# most units allowed in one order; check your broker, these change
FREEZE = {"NIFTY": 1800, "BANKNIFTY": 900, "FINNIFTY": 1800, "MIDCPNIFTY": 2800, "NIFTYNXT50": 600,
          "SENSEX": 1000, "BANKEX": 900}
EXCHANGE_NAME = {"NFO": "NSE", "BFO": "BSE", "MCX": "MCX"}
FRESH_SECONDS = 120


class OptionsData:
    def __init__(self, kite):
        self.kite = kite                 # KiteService
        self._rows: dict[str, list[dict]] = {}
        self._day = None
        self._lock = threading.Lock()
        self._qcache: dict[str, tuple[float, dict]] = {}

    def ready(self) -> bool:
        return self.kite.ready()

    # ---------- contracts ----------
    def _load(self):
        today = date.today().isoformat()
        with self._lock:
            if self._day == today and self._rows:
                return
            self.kite._require()
            rows: dict[str, list[dict]] = {}
            for exch in ("NFO", "BFO", "MCX"):
                self.kite._throttle()
                out = []
                for x in self.kite.kite.instruments(exch):
                    t = x.get("instrument_type")
                    if t not in ("CE", "PE", "FUT") or not x.get("expiry"):
                        continue
                    out.append({"symbol": x["tradingsymbol"], "name": x.get("name") or "", "type": t,
                                "strike": float(x.get("strike") or 0), "expiry": x["expiry"].isoformat(),
                                "lot": int(x.get("lot_size") or 1), "exchange": exch})
                rows[exch] = out
            self._rows, self._day = rows, today

    def underlyings(self) -> list[dict]:
        self._load()
        today = date.today().isoformat()
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
            ex = sorted(u["expiries"])
            out.append({"exchange": u["exchange"], "name": u["name"], "lot": u["lot"], "expiries": ex[:6],
                        "venue": EXCHANGE_NAME[u["exchange"]], "popular": k in rank, "freeze": FREEZE.get(u["name"], 0),
                        "index": k in INDEX_SPOT})
        out.sort(key=lambda u: (rank.get((u["exchange"], u["name"]), 99), u["exchange"] != "NFO", u["name"]))
        return out

    def expiries(self, exchange: str, name: str) -> list[str]:
        self._load()
        today = date.today().isoformat()
        return sorted({r["expiry"] for r in self._rows.get(exchange, [])
                       if r["name"] == name and r["type"] != "FUT" and r["expiry"] >= today})

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
        if exchange == "MCX":   # commodity options settle into the future; use the nearest one at or after expiry
            self._load()
            futs = sorted((r for r in self._rows.get("MCX", []) if r["name"] == name and r["type"] == "FUT"
                           and r["expiry"] >= (expiry or date.today().isoformat())), key=lambda r: r["expiry"])
            return f"MCX:{futs[0]['symbol']}" if futs else None
        return f"NSE:{name}"

    # ---------- quotes ----------
    def quotes(self, keys: list[str], max_age: float = 1.5) -> dict[str, dict]:
        """Bid, ask, last price and quote time for each key; shared for a moment across sessions."""
        now = time.time()
        out, need = {}, []
        for k in dict.fromkeys(k for k in keys if k):
            hit = self._qcache.get(k)
            if hit and now - hit[0] < max_age:
                out[k] = hit[1]
            else:
                need.append(k)
        for i in range(0, len(need), 450):
            self.kite._require()
            self.kite._throttle()
            data = self.kite.kite.quote(need[i:i + 450])
            for k, v in data.items():
                d = v.get("depth") or {}
                bid = next((x["price"] for x in d.get("buy", []) if x.get("price")), None)
                ask = next((x["price"] for x in d.get("sell", []) if x.get("price")), None)
                ts = v.get("timestamp") or v.get("last_trade_time")
                q = {"ltp": v.get("last_price"), "bid": bid, "ask": ask, "oi": v.get("oi"),
                     "volume": v.get("volume"), "ts": ts.isoformat() if hasattr(ts, "isoformat") else ts}
                self._qcache[k] = (now, q)
                out[k] = q
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
                "freeze": FREEZE.get(name, 0)}

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
