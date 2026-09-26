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

ROLL_DAYS = 3

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
PER_DAY = {"1h": 15, "15m": 58, "5m": 174}           # 09:00 to 23:30


def front(contracts: list[dict], today: date) -> dict | None:
    """The contract to trade: the nearest one more than ROLL_DAYS from expiry."""
    live = sorted((c for c in contracts if c["expiry"] >= today), key=lambda c: c["expiry"])
    for c in live:
        if (c["expiry"] - today).days > ROLL_DAYS:
            return c
    return live[-1] if live else None


class MCXProvider:
    market = "MCX"
    max_days = {"1d": 3650, "1h": 180, "15m": 120, "5m": 60}

    def __init__(self, kite):
        self.kite = kite
        self._by_name: dict[str, list[dict]] = {}
        self._day: str | None = None

    def ready(self) -> bool:
        return self.kite.ready()

    def _load(self):
        today = date.today().isoformat()
        if self._day == today and self._by_name:
            return
        rows = self.kite.instruments_of("MCX")
        by: dict[str, list[dict]] = {}
        for x in rows:
            name = str(x.get("name") or "").upper()
            if x.get("instrument_type") != "FUT" or name not in CONTRACTS or not x.get("expiry"):
                continue
            exp = x["expiry"] if isinstance(x["expiry"], date) else date.fromisoformat(str(x["expiry"])[:10])
            by.setdefault(name, []).append({"token": int(x["instrument_token"]), "symbol": x["tradingsymbol"], "expiry": exp})
        self._by_name, self._day = by, today

    def _make(self, name: str, c: dict) -> dict:
        label, units, per = CONTRACTS[name]
        return {"id": f"MCX:{name}", "token": c["token"], "symbol": name, "contract": c["symbol"],
                "name": f"{label} futures ({c['expiry'].strftime('%b %Y')} contract, price per {per})",
                "exchange": "MCX", "type": "FUT", "market": "MCX", "currency": "INR", "tz": "Asia/Kolkata",
                "lot": 1, "step": units, "lot_units": units, "unit": per,
                "fno": False, "expiry": c["expiry"].isoformat(), "strike": None}

    def instrument(self, key: str) -> dict | None:
        name = ALIASES.get(key.strip().upper(), key.strip().upper())
        if name not in CONTRACTS:
            return None
        self._load()
        c = front(self._by_name.get(name, []), date.today())
        return self._make(name, c) if c else None

    def defaults(self) -> list[dict]:
        return [i for i in (self.instrument(n) for n in DEFAULTS) if i]

    def search(self, q: str, allow_fno: bool = True, limit: int = 25) -> list[dict]:
        q = q.strip().upper()
        if not q:
            return []
        q = ALIASES.get(q, q)
        hits = [n for n, (label, _, _) in CONTRACTS.items() if n.startswith(q) or q in label.upper()]
        hits.sort(key=lambda n: (n != q, len(n)))
        return [i for i in (self.instrument(n) for n in hits[:limit]) if i]

    def ltp(self, inst: dict) -> float | None:
        return self.kite.ltp_key(f"MCX:{inst['contract']}")

    def warmup_days(self, tf: str, candles: int = 210) -> int:
        if tf == "1d":
            return math.ceil(candles * 7 / 5) + 10
        return math.ceil(candles / PER_DAY[tf] * 7 / 5) + 3

    def history(self, inst: dict, tf: str, days: int) -> list[dict]:
        if tf != "1d":       # no continuous intraday series: only the current contract's own life
            days = min(days, self.max_days[tf])
        try:
            return self.kite.history(int(inst["token"]), tf, days, continuous=(tf == "1d"))
        except Exception as e:
            raise DataError(f"MCX prices couldn't be loaded: {e}") from None

    def closed_candles(self, inst: dict, tf: str, since: str | None) -> list[dict]:
        """Candles that have fully closed after `since`, for live paper trading."""
        secs = {"1d": 86400, "1h": 3600, "15m": 900, "5m": 300}[tf]
        bars = self.kite.history(int(inst["token"]), tf, 5 if tf != "1d" else 30, continuous=False, ttl=20)
        cutoff = datetime.fromisoformat(since).timestamp() if since else 0
        now = time.time()
        return [b for b in bars if cutoff < datetime.fromisoformat(b["t"]).timestamp() and
                datetime.fromisoformat(b["t"]).timestamp() + secs <= now]

