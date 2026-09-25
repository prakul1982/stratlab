"""Runs a notebook's rules on the underlying's own candles, to tell an options session when to trade.

The candles come from Kite's history, fetched shortly after each one closes, so the rules see exactly
what a backtest of the notebook sees. Only the rules' decisions are used: their own position size and
costs don't matter, which is why they run on a notional account big enough never to round to zero."""
import time
from datetime import datetime

from ..engine.core import Ctx, Engine
from ..kite_service import KiteService
from ..models import Strategy

POLL_SECONDS = 20


class SignalFeed:
    def __init__(self, kite, rules: Strategy, spot_key: str, state: dict | None = None):
        self.kite, self.spot_key = kite, spot_key
        self.tf = rules.tf
        r = rules.model_copy(deep=True)
        rk = r.risk
        rk.capital, rk.maxAlloc, rk.brokerage, rk.slippage, rk.sizing, rk.perTrade, rk.leverage = 1e10, 100, 0, 0, "capital", 0, 1
        from ..live import drop_forming      # live imports the options package, so import here
        self._drop = drop_forming
        st = state or {}
        self.engine = Engine(r, 1, state=st.get("engine") or None)
        self.token = st.get("token") or self._token()
        self.bars = self._drop(kite.history(self.token, self.tf, KiteService.warmup_days(self.tf, 300)), self.tf)[-400:]
        if len(self.bars) < 30:
            raise ValueError("Not enough price history of the underlying to run the rules.")
        self.next_poll = 0.0
        self.ok = True

    def _token(self) -> int:
        self.kite._require()
        self.kite._throttle()
        q = self.kite.kite.ltp([self.spot_key]).get(self.spot_key)
        if not q or not q.get("instrument_token"):
            raise ValueError(f"Couldn't find {self.spot_key} to run the rules on.")
        return int(q["instrument_token"])

    def poll(self, now: datetime) -> list[dict]:
        """Feed any newly closed candles to the rules. Returns the rules' own events (for the log)."""
        if time.time() < self.next_poll:
            return []
        self.next_poll = time.time() + POLL_SECONDS
        try:
            fresh = self._drop(self.kite.history(self.token, self.tf, 4), self.tf)
            self.ok = True
        except Exception as e:
            self.ok = False
            print("signal candles failed:", self.spot_key, e)
            return []
        return self.feed([b for b in fresh if b["t"] > self.bars[-1]["t"]])

    def feed(self, new: list[dict]) -> list[dict]:
        out = []
        for c in new:
            self.bars.append(c)
            if len(self.bars) > 600:
                self.bars = self.bars[-500:]
            out += self.engine.step(self.bars, Ctx(self.bars, intraday=True), len(self.bars) - 1)
        return out

    def want(self) -> dict | None:
        e = self.engine
        if e.qty <= 0:
            return None
        return {"dir": "short" if e.dir == -1 else "long", "key": str(e.entry_t)}

    def dump(self) -> dict:
        return {"engine": self.engine.dump(), "token": self.token}

    def view(self) -> dict:
        w = self.want()
        return {"tf": self.tf, "position": w["dir"] if w else None, "since": w["key"] if w else None,
                "last_candle": self.bars[-1]["t"] if self.bars else None, "price": self.bars[-1]["c"] if self.bars else None,
                "ok": self.ok}
