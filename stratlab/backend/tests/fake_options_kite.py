"""A stand-in for Kite's option instruments, quotes and margins, for tests and the local demo server only."""
import math
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
UNDERLYINGS = {  # (exchange, name): (spot key, spot, strike gap, lot)
    ("NFO", "NIFTY"): ("NSE:NIFTY 50", 25000.0, 50, 75),
    ("NFO", "BANKNIFTY"): ("NSE:NIFTY BANK", 55000.0, 100, 35),
    ("BFO", "SENSEX"): ("BSE:SENSEX", 82000.0, 100, 20),
    ("MCX", "CRUDEOIL"): ("MCX:CRUDEOILFUT", 5600.0, 50, 100),
    ("CDS", "USDINR"): ("CDS:USDINRFUT", 88.0, 0.25, 1),      # Kite lists currency lots as 1 (1,000 dollars)
    ("NFO", "FINNIFTY"): ("NSE:NIFTY FIN SERVICE", 26000.0, 50, 65),
    ("NFO", "MIDCPNIFTY"): ("NSE:NIFTY MID SELECT", 13000.0, 25, 140),
}
TOKENS = {sk: 900001 + i for i, (sk, *_) in enumerate(UNDERLYINGS.values())}


def _expiries(lingering: bool = False):
    """Weekly Tuesday expiries in India's date, moved to the trading day before when Tuesday is a holiday (as the
    exchange does). `lingering` adds the contract that expired in the last two days: the broker's instrument list
    keeps it until its morning refresh, so the app has to drop it by date."""
    from app.data.calendar import is_trading_day
    today = datetime.now(IST).date()
    out, d = [], today - timedelta(days=2) if lingering else today
    while len(out) < 4:
        if d.weekday() == 1:
            e = d
            while not is_trading_day("IN", e):
                e -= timedelta(days=1)
            if e >= today or (lingering and e not in out and e >= today - timedelta(days=2)):
                out.append(e)
        d += timedelta(days=1)
    return out


class _Inner:
    def __init__(self, outer):
        self.o = outer

    def instruments(self, exch):
        rows = []
        for (ex, name), (_, spot, gap, lot) in UNDERLYINGS.items():
            if ex != exch:
                continue
            for e in _expiries(lingering=True):
                for i in range(-30, 31):
                    k = round(spot / gap) * gap + i * gap
                    for t in ("CE", "PE"):
                        rows.append({"tradingsymbol": f"{name}{e:%y%m%d}{k:g}{t}", "name": name, "instrument_type": t,
                                     "strike": float(k), "expiry": e, "lot_size": lot})
            if exch in ("MCX", "CDS"):
                rows.append({"tradingsymbol": f"{name}FUT", "name": name, "instrument_type": "FUT", "strike": 0,
                             "expiry": _expiries()[-1], "lot_size": lot})
        return rows

    def quote(self, keys):
        now = self.o.clock()
        out = {}
        for key in keys:
            px = self.o.price(key, now)
            if px is None:
                continue
            spread = 0 if self.o.spot(key, now) is not None else max(0.05, round(px * 0.004 / 0.05) * 0.05)
            out[key] = {"last_price": px, "timestamp": now.replace(tzinfo=None) if self.o.live else now.replace(tzinfo=None) - timedelta(days=3),
                        "oi": self.o.open_interest(key), "volume": self.o.open_interest(key) // 20,
                        "depth": {"buy": [{"price": round(px - spread / 2, 2)}], "sell": [{"price": round(px + spread / 2, 2)}]}}
        return out

    def ltp(self, keys):
        return {k: {"instrument_token": TOKENS[k], "last_price": self.o.spot(k, self.o.clock())} for k in keys if k in TOKENS}

    def basket_order_margins(self, orders, consider_positions=False, mode="compact"):
        sold = sum(o["quantity"] for o in orders if o["transaction_type"] == "SELL")
        hedged = any(o["transaction_type"] == "BUY" for o in orders)
        per = 1500 if hedged else 4000
        return {"initial": {"total": sold * per * 1.1}, "final": {"total": sold * per}}


class FakeOptionsKite:
    """Spot moves in a slow wave so demos show P&L changing; `live=False` makes every quote days old."""

    def __init__(self, live=True, drift=None, clock=None, vix=13.8):
        self.live = live
        self.vix = vix              # India VIX (NSE:INDIA VIX); None leaves it unquoted
        self.clock = clock or (lambda: datetime.now(IST))      # tests can pin the feed's time to the session's
        self.drift = drift          # fixed spot offsets per spot key, for tests
        self.kite = _Inner(self)

    def ready(self):
        return True

    def _require(self):
        pass

    def _throttle(self):
        pass

    def history(self, token, tf, days):
        """Candles of the spot's wave in market hours, for rules that drive option trades."""
        key = next(k for k, v in TOKENS.items() if v == token)
        step = {"5m": 5, "15m": 15, "1h": 60}[tf]
        now = self.clock()
        out = []
        for d in range(min(days, 30), -1, -1):
            day = (now - timedelta(days=d)).replace(hour=9, minute=15, second=0, microsecond=0)
            if day.weekday() >= 5:
                continue
            t = day
            while t < day.replace(hour=15, minute=30) and t <= now:
                prices = [self.spot(key, t + timedelta(minutes=m)) for m in range(0, step + 1, max(1, step // 5))]
                out.append({"t": t.isoformat(), "o": prices[0], "h": max(prices), "l": min(prices), "c": prices[-1], "v": 0})
                t += timedelta(minutes=step)
        return out

    def open_interest(self, key) -> int:
        """Open interest that peaks a few strikes out of the money (calls above the spot, puts below), like a real
        chain's, fixed per contract so the positioning page has a shape to show."""
        ex, sym = key.split(":", 1)
        for (uex, name), (_, spot, gap, _) in UNDERLYINGS.items():
            if uex == ex and sym.startswith(name) and sym[-2:] in ("CE", "PE") and sym[len(name):len(name) + 6].isdigit():
                k = float(sym[len(name) + 6:-2])
                peak = spot + (4 if sym.endswith("CE") else -3) * gap
                bump = math.exp(-((k - peak) / (5 * gap)) ** 2)
                return int(20000 + (300000 if sym.endswith("CE") else 260000) * bump)
        return 100000

    def spot(self, key, now):
        for (_, _), (sk, spot, gap, _) in UNDERLYINGS.items():
            if sk == key:
                if self.drift is not None:
                    return spot + self.drift.get(key, 0.0)
                return round(spot * (1 + 0.004 * math.sin(now.timestamp() / 600)), 2)
        return None

    def price(self, key, now):
        if key == "NSE:INDIA VIX":
            return self.vix
        s = self.spot(key, now)
        if s is not None:
            return s
        ex, sym = key.split(":", 1)
        for (uex, name), (sk, _, gap, _) in UNDERLYINGS.items():
            if uex == ex and sym.startswith(name) and sym[-2:] in ("CE", "PE") and sym[len(name):len(name) + 6].isdigit():
                strike = float(sym[len(name) + 6:-2])
                spot = self.spot(sk, now)
                intrinsic = max(0.0, spot - strike) if sym.endswith("CE") else max(0.0, strike - spot)
                time_value = max(0.05, spot * 0.006 * math.exp(-((spot - strike) / (spot * 0.02)) ** 2))
                return round((intrinsic + time_value) / 0.05) * 0.05
        return None
