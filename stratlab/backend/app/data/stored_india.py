"""India's stored daily closes, for the hours the broker's data login is off (nights, early mornings, weekends).

LIVE11B-013: "₹ India (offline)" blocked every Indian backtest from the end of the broker's session until the 08:00 IST data login,
though a daily test reads only past closes, which StratLab keeps for every listed company (the company pages' charts). This provider
gives those closes to a daily test of a stock, an ETF or a main index while the broker is offline; intraday timeframes, futures and
options still need the live data. Instrument ids are the broker's ("IN:<token>", named from the notebook's own record or the last
instrument list held) or by symbol ("IN:RELIANCE", from the company search while offline)."""
from __future__ import annotations

from typing import Callable

from .. import instrument_kinds

STORED_MAX_DAYS = {"1d": 3650}
# the main indices by the broker's symbol, as the company pages' charts read them
INDEX_SYMBOLS = {"NIFTY 50": "^NSEI", "NIFTY BANK": "^NSEBANK", "SENSEX": "^BSESN"}


class StoredIndia:
    market = "IN"
    max_days = STORED_MAX_DAYS
    stored = True

    def __init__(self, bars_fn: Callable[[str], list[dict]], kept_fn: Callable[[int], dict | None] | None = None,
                 known_fn: Callable[[str], dict | None] | None = None):
        """`bars_fn(symbol)`: a stock's (or an index's chart symbol's) stored daily candles, oldest first. `kept_fn(token)`: the broker's
        instrument from the last list held in memory, whatever its day. `known_fn(symbol)`: the stored company list's entry."""
        self.bars_fn, self.kept_fn, self.known_fn = bars_fn, kept_fn, known_fn

    def ready(self) -> bool:
        return True

    @staticmethod
    def warmup_days(tf: str, candles: int = 210) -> int:
        from ..kite_service import KiteService
        return KiteService.warmup_days(tf, candles)

    def resolve(self, key: str, hint: dict | None = None) -> dict | None:
        """The instrument for a stored daily test, or None when it can't be named or isn't a stock, an ETF or a main index."""
        key = str(key or "").strip()
        base = None
        if key.isdigit():
            if hint and str(hint.get("id") or "") == f"IN:{key}" and hint.get("symbol"):
                base = hint
            elif self.kept_fn:
                try:
                    base = self.kept_fn(int(key))
                except Exception:
                    base = None
        elif key:
            base = {"symbol": key.upper()}
        sym = str((base or {}).get("symbol") or "").strip().upper()
        if not sym:
            return None
        kind = str((base or {}).get("type") or "").upper()
        if kind in ("FUT", "CE", "PE", "OPTIONS") or (base or {}).get("fno"):
            return None
        index = kind == "INDEX" or sym in INDEX_SYMBOLS
        if index and sym not in INDEX_SYMBOLS:
            return None
        known = None
        if not index and self.known_fn:
            try:
                known = self.known_fn(sym)
            except Exception:
                known = None
            if not known and not (base or {}).get("name"):
                return None                       # not a company StratLab keeps closes for
        name = (base or {}).get("name") or (known or {}).get("name") or sym
        if index:
            t = "INDEX"
        else:
            t = "ETF" if instrument_kinds.base(instrument_kinds.classify(sym, None, name)) == "etf" else "EQ"
        return {"id": f"IN:{key}" if key.isdigit() else f"IN:{sym}", "token": int(key) if key.isdigit() else None, "symbol": sym, "name": name,
                "exchange": (base or {}).get("exchange") or ("BSE" if sym.isdigit() or sym == "SENSEX" else "NSE"), "type": t,
                "lot": 1, "step": 1, "expiry": None, "strike": None, "fno": False, "market": "IN", "currency": "INR", "tz": "Asia/Kolkata",
                "stored": True}

    def history(self, inst: dict, tf: str, days: int, ttl: float | None = None) -> list[dict]:
        if tf != "1d":
            return []
        sym = INDEX_SYMBOLS.get(inst["symbol"], inst["symbol"])
        return list(self.bars_fn(sym) or [])
