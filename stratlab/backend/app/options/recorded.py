"""The options builder with the live feed offline (DB-001): an index's last recorded chain (recorder.py, read by
positioning.recorded_chain) stands in for the live one, so the chain, the payoff, the Greeks and the breakevens can be
shown as of that recording, said as such. Nothing is traded on it: a paper session still needs the live feed, and the
broker's margin isn't available.

Recorded rows are [strike, ce bid, ce ask, ce ltp, ce oi, pe bid, pe ask, pe ltp, pe oi, ce volume, pe volume]; older
recordings stop at the put's open interest."""
import math
from functools import reduce

from .engine import Contracts


def _at(r: list, i: int):
    return r[i] if len(r) > i else None


def lot_from_oi(rows: list[list]) -> int | None:
    """Shares in one contract, read off the open interest: every strike's open interest is a whole number of lots, so the
    greatest common divisor of them all is the lot (NIFTY's 65). None when too few strikes have any to tell."""
    ois = [int(v) for r in rows for v in (_at(r, 4), _at(r, 8)) if isinstance(v, (int, float)) and v > 0 and float(v).is_integer()]
    if len(ois) < 6:
        return None
    g = reduce(math.gcd, ois)
    return g if g > 1 else None


class Recorded:
    """One index's recorded chain behind the same calls the builder makes of the live feed (OptionsData)."""

    def __init__(self, exchange: str, name: str, rec: dict):
        self.exchange, self.name, self.rec = exchange, name, rec
        self.expiry = str(rec["expiry"])[:10]
        self.as_of = rec["taken_at"]
        self.rows = sorted((r for r in rec.get("chain") or [] if isinstance(r, list) and r), key=lambda r: r[0])
        self.lot = int(rec.get("lot") or 0) or lot_from_oi(self.rows) or 1
        self.lot_known = bool(rec.get("lot") or lot_from_oi(self.rows))
        # a key per contract, as the live feed's are "NFO:<tradingsymbol>"; never shown (the page gets no symbol)
        self._sym = lambda opt, k: f"{name}{self.expiry.replace('-', '')}{k:g}{opt}"
        self.contract = Contracts([{"opt": o, "strike": float(r[0]), "symbol": self._sym(o, float(r[0])), "lot": self.lot}
                                   for r in self.rows for o in ("CE", "PE")], self.lot, self.expiry, exchange) if self.rows else None
        self._q = {}
        for r in self.rows:
            for opt, j, vol in (("CE", 1, 9), ("PE", 5, 10)):
                self._q[f"{exchange}:{self._sym(opt, float(r[0]))}"] = {
                    "bid": _at(r, j), "ask": _at(r, j + 1), "ltp": _at(r, j + 2), "oi": _at(r, j + 3), "volume": _at(r, vol),
                    "ts": self.as_of}

    def ready(self) -> bool:
        return True

    def contracts(self, exchange: str, name: str, choice: str) -> Contracts | None:
        return self.contract if (exchange, name) == (self.exchange, self.name) else None

    def expiries(self, exchange: str, name: str) -> list[str]:
        return list(self.rec.get("expiries") or [self.expiry])

    def spot(self, exchange: str, name: str, expiry: str | None = None):
        px = self.rec.get("spot")
        return px, {"ltp": px, "ts": self.as_of}, "recorded"

    def quotes(self, keys: list[str], max_age: float = 3.0) -> dict[str, dict]:
        return {k: self._q[k] for k in keys if k in self._q}

    def margin(self, legs: list[dict]) -> float | None:
        return None                       # the broker's margin needs the live feed

    def chain(self, around: int = 10) -> dict:
        """The chain as OptionsData.chain gives it, marked as recorded and when."""
        c = self.contract
        spot = self.rec.get("spot")
        if not c:
            return {"expiry": None, "rows": [], "spot": None, "recorded": True, "as_of": self.as_of}
        mid = c.atm(spot) if spot else c.strikes[len(c.strikes) // 2]
        i = c.strikes.index(mid)
        strikes = c.strikes[max(0, i - around): i + around + 1]
        q = self.quotes([c.key(o, k) for k in strikes for o in ("CE", "PE")])
        from .data import freeze
        return {"exchange": self.exchange, "expiry": self.expiry, "expiries": self.expiries(self.exchange, self.name)[:6],
                "lot": self.lot if self.lot_known else None, "spot": spot, "atm": mid, "step": c.step(mid),
                "rows": [{"strike": k, "ce": q.get(c.key("CE", k)), "pe": q.get(c.key("PE", k))} for k in strikes],
                "spot_ts": self.as_of, "spot_from": "recorded", "freeze": freeze(self.name), "recorded": True, "as_of": self.as_of}

    def underlying(self) -> dict:
        """The index as /options/underlyings lists it, from its recording."""
        from .data import EXCHANGE_NAME, freeze
        ex = self.expiries(self.exchange, self.name)[:6]
        return {"exchange": self.exchange, "name": self.name, "lot": self.lot if self.lot_known else None, "expiries": ex,
                "lots": {self.expiry: self.lot} if self.lot_known else {}, "venue": EXCHANGE_NAME[self.exchange], "popular": True,
                "freeze": freeze(self.name), "index": True, "recorded": True, "as_of": self.as_of}
