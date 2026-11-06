"""Indian commodity futures (MCX), through the same Kite login as Indian stocks, kept as a market of its own.

An instrument is a commodity, not one contract: "MCX:GOLD" means the front-month gold future. It resolves to the
nearest contract that isn't about to expire (contracts within ROLL_DAYS of expiry hand over to the next one).
- Backtests on daily candles use Kite's continuous series, which stitches expired contracts into years of history.
- Intraday candles exist only for the contract being traded, so intraday tests reach back to its listing.
- Quantities are in the units the price is quoted in, and always a whole number of lots: one gold lot is 1 kg,
  quoted per 10 g, so a lot is 100 price units. That keeps every rupee of profit and loss true to the exchange."""
import math
import time
from datetime import date, datetime

from .coinbase import DataError
from ..kite_service import ist_date
from ..candles import whole_candles

ROLL_DAYS = 3


def frozen_series(bars: list[dict] | None, n: int = 5) -> bool:
    """The last `n` daily candles one standing price with no volume: not trading (options/data.frozen_series)."""
    from ..options.data import frozen_series as frozen
    return frozen(bars, n)

# a stitched daily series whose last candle is this many days before today has stopped: the source's continuous series
# for that segment ends there (the currency futures' one stopped on 6 Jun 2023, so every rupee-pair library entry was
# tested only to that day while the others ran to the latest close)
STOPPED_AFTER_DAYS = 10


def ended_early(bars: list[dict] | None, today: date | None = None) -> bool:
    """Whether a daily series stops well before today (more than STOPPED_AFTER_DAYS days, so a long holiday isn't one)."""
    if not bars:
        return False
    try:
        last = date.fromisoformat(str(bars[-1]["t"])[:10])
    except (KeyError, TypeError, ValueError):
        return False
    return ((today or ist_date()) - last).days > STOPPED_AFTER_DAYS


# commodity: (name, price units in one lot, what one price unit is)
CONTRACTS = {
    "GOLD": ("Gold", 100, "10 g"), "GOLDM": ("Gold mini", 10, "10 g"), "GOLDPETAL": ("Gold petal", 1, "1 g"),
    "SILVER": ("Silver", 30, "kg"), "SILVERM": ("Silver mini", 5, "kg"), "SILVERMIC": ("Silver micro", 1, "kg"),
    "CRUDEOIL": ("Crude oil", 100, "barrel"), "CRUDEOILM": ("Crude oil mini", 10, "barrel"),
    "NATURALGAS": ("Natural gas", 1250, "mmBtu"), "NATGASMINI": ("Natural gas mini", 250, "mmBtu"),
    "COPPER": ("Copper", 2500, "kg"), "ZINC": ("Zinc", 5000, "kg"), "ZINCMINI": ("Zinc mini", 1000, "kg"),
    "ALUMINIUM": ("Aluminium", 5000, "kg"), "ALUMINI": ("Aluminium mini", 1000, "kg"),
    "LEAD": ("Lead", 5000, "kg"), "LEADMINI": ("Lead mini", 1000, "kg"),
}
DEFAULTS = ["GOLDM", "SILVERM", "CRUDEOIL", "NATURALGAS", "COPPER", "GOLD"]
ALIASES = {"GOLD MINI": "GOLDM", "SILVER MINI": "SILVERM", "CRUDE": "CRUDEOIL", "CRUDE OIL": "CRUDEOIL", "OIL": "CRUDEOIL",
           "NATURAL GAS": "NATURALGAS", "NATGAS": "NATURALGAS", "GAS": "NATURALGAS", "ALUMINUM": "ALUMINIUM"}
MINUTES = {"1h": 60, "15m": 15, "5m": 5}              # candles a day: the session's length (open to the day's close) over this


def front(contracts: list[dict], today: date) -> dict | None:
    """The contract to trade: the nearest one more than ROLL_DAYS from expiry."""
    live = sorted((c for c in contracts if c["expiry"] >= today), key=lambda c: c["expiry"])
    for c in live:
        if (c["expiry"] - today).days > ROLL_DAYS:
            return c
    return live[-1] if live else None


class MCXProvider:
    """Front-month futures on one Kite exchange. Currency futures (cds.py) are the same with other contracts."""
    market = exchange = "MCX"
    contracts, default_names, aliases = CONTRACTS, DEFAULTS, ALIASES
    noun = "MCX"
    max_days = {"1d": 3650, "1h": 180, "15m": 120, "5m": 60}

    def __init__(self, kite):
        self.kite = kite
        self._by_name: dict[str, list[dict]] = {}
        self._day: str | None = None

    def ready(self) -> bool:
        return self.kite.ready()

    def _load(self):
        today = ist_date().isoformat()
        if self._day == today and self._by_name:
            return
        rows = self.kite.instruments_of(self.exchange)
        by: dict[str, list[dict]] = {}
        for x in rows:
            name = str(x.get("name") or "").upper()
            if x.get("instrument_type") != "FUT" or name not in self.contracts or not x.get("expiry"):
                continue
            exp = x["expiry"] if isinstance(x["expiry"], date) else date.fromisoformat(str(x["expiry"])[:10])
            by.setdefault(name, []).append({"token": int(x["instrument_token"]), "symbol": x["tradingsymbol"], "expiry": exp})
        self._by_name, self._day = by, today

    def _make(self, name: str, c: dict) -> dict:
        label, units, per = self.contracts[name][:3]
        currency = self.contracts[name][3] if len(self.contracts[name]) > 3 else "INR"
        return {"id": f"{self.market}:{name}", "token": c["token"], "symbol": name, "contract": c["symbol"],
                "name": f"{label} futures ({c['expiry'].strftime('%b %Y')} contract, price per {per})",
                "exchange": self.exchange, "type": "FUT", "market": self.market, "currency": currency, "tz": "Asia/Kolkata",
                "lot": 1, "step": units, "lot_units": units, "unit": per,
                "fno": False, "expiry": c["expiry"].isoformat(), "strike": None}

    def instrument(self, key: str) -> dict | None:
        name = self.aliases.get(key.strip().upper(), key.strip().upper())
        if name not in self.contracts:
            return None
        self._load()
        c = front(self._by_name.get(name, []), ist_date())
        return self._make(name, c) if c else None

    def defaults(self) -> list[dict]:
        return [i for i in (self.instrument(n) for n in self.default_names) if i]

    def search(self, q: str, allow_fno: bool = True, limit: int = 25) -> list[dict]:
        q = q.strip().upper()
        if not q:
            return []
        q = self.aliases.get(q, q)
        hits = [n for n, c in self.contracts.items() if n.startswith(q) or q in c[0].upper()]
        hits.sort(key=lambda n: (n != q, len(n)))
        return [i for i in (self.instrument(n) for n in hits[:limit]) if i]

    def ltp(self, inst: dict) -> float | None:
        return self.kite.ltp_key(f"{self.exchange}:{inst['contract']}")

    def day_close(self, day=None) -> str | None:
        """When this segment's day ends, India time "HH:MM": from /markets' hours, so MCX's 23:55 winter close is followed
        (options/data.py expiry_time) and the same figure serves the daily candle's close, the candle counts and the labels."""
        from . import _hours
        from .markets import BY_ID
        return ((_hours(BY_ID[self.market], day or ist_date()) or {}).get("close"))

    def per_day(self, tf: str) -> int:
        """Candles in a trading day on this timeframe, from the segment's open to its close that day."""
        from .markets import BY_ID
        h = BY_ID[self.market]["hours"]
        mins = lambda hhmm: int(hhmm[:2]) * 60 + int(hhmm[3:])
        return math.ceil((mins(self.day_close()) - mins(h["open"])) / MINUTES[tf])

    def warmup_days(self, tf: str, candles: int = 210) -> int:
        if tf == "1d":
            return math.ceil(candles * 7 / 5) + 10
        return math.ceil(candles / self.per_day(tf) * 7 / 5) + 3

    @whole_candles
    def history(self, inst: dict, tf: str, days: int) -> list[dict]:
        if tf != "1d":       # no continuous intraday series: only the current contract's own life
            days = min(days, self.max_days[tf])
        else:                # the day's candle is read again after this segment's own close (17:00 currency, 23:30 commodity and 23:55 while US daylight saving is off)
            mark = getattr(self.kite, "set_session_close", None)
            if mark:
                mark(int(inst["token"]), self.day_close())
        own_read = False
        try:
            bars = self.kite.history(int(inst["token"]), tf, days, continuous=(tf == "1d"))
            frozen, stopped = tf == "1d" and frozen_series(bars), tf == "1d" and ended_early(bars)
            if tf == "1d" and (not bars or frozen or stopped):
                # the broker keeps no stitched series for some segments (currency futures): the current contract's own
                # daily prices instead, which go back to its listing (about a year for monthly currency contracts). A
                # stitched series that is one standing price with no volume (R13-002: USDINR o=h=l=c=96.135, volume 0,
                # every day for a month) is no series either: the contract's own candles are read, and kept when they move.
                # Nor is one that stopped long ago (the rupee pairs' ended on 6 Jun 2023): the contract's own candles, which
                # reach the latest close, are kept when they run later than it, so a test runs to today over a shorter span
                own = self.kite.history(int(inst["token"]), tf, days, continuous=False)
                own_read = True
                if own and (not bars or not frozen_series(own)) and \
                        (not bars or frozen or str(own[-1]["t"])[:10] > str(bars[-1]["t"])[:10]):
                    bars = own
            return self._caught_up(inst, bars, days, own_read) if tf == "1d" else bars
        except Exception as e:
            if tf == "1d":
                try:
                    bars = self.kite.history(int(inst["token"]), tf, days, continuous=False)
                    if bars:
                        return self._caught_up(inst, bars, days, True)
                except Exception:
                    pass
            raise DataError(f"{self.noun} prices couldn't be loaded: {e}") from None

    CATCH_UP_TTL = 120.0      # seconds a session's candle made from the quote is reused before the quote is asked again

    def _caught_up(self, inst: dict, bars: list[dict], days: int, own_read: bool) -> list[dict]:
        """Daily candles that end before this segment's latest completed session, topped up: first with the contract's
        own newer candles (the broker's stitched series is built after the day, so for hours after the close it ends on
        the session before), then, still short, with the session's candle from the contract's quote (its day's open,
        high, low and last price, which after the close is the close), as the stock market's candles are (R11: the
        currency check at 22:55 IST still saw 4 Nov as USDINR's newest, six hours after the 5 Nov close). The candles
        given are never changed; when nothing is newer they are returned as they are."""
        from .. import last_session
        if not bars or not last_session.behind(bars, self.market):
            return bars
        token = int(inst["token"])
        if not own_read:
            try:
                own = self.kite.history(token, "1d", days, continuous=False)
            except Exception:
                own = None
            last = str(bars[-1]["t"])[:10]
            if own and str(own[-1]["t"])[:10] > last:
                bars = [*bars, *(b for b in own if str(b["t"])[:10] > last)]
            if not last_session.behind(bars, self.market):
                return bars
        return last_session.with_quote_close(bars, self._session_quote(inst), self.market)

    def _session_quote(self, inst: dict) -> dict | None:
        """The contract's quote, kept CATCH_UP_TTL seconds; None when the broker has none or can't be asked."""
        ask = getattr(self.kite, "quote_key", None)
        if not inst.get("contract") or not callable(ask):
            return None
        key = f"{self.exchange}:{inst['contract']}"
        kept = self.__dict__.setdefault("_quotes", {}).get(key)
        if kept and time.time() - kept[0] < self.CATCH_UP_TTL:
            return kept[1]
        try:
            q = ask(key)
        except Exception as e:
            print("session candle from the quote:", key, str(e)[:120])
            q = None
        self._quotes[key] = (time.time(), q)
        return q

    def closed_candles(self, inst: dict, tf: str, since: str | None) -> list[dict]:
        """Candles that have fully closed after `since`, for live paper trading."""
        secs = {"1d": 86400, "1h": 3600, "15m": 900, "5m": 300}[tf]
        bars = self.kite.history(int(inst["token"]), tf, 5 if tf != "1d" else 30, continuous=False, ttl=20)
        cutoff = datetime.fromisoformat(since).timestamp() if since else 0
        now = time.time()
        return [b for b in bars if cutoff < datetime.fromisoformat(b["t"]).timestamp() and
                datetime.fromisoformat(b["t"]).timestamp() + secs <= now]

