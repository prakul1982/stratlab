"""Stocks, ETFs, forex and global commodity futures from Yahoo Finance: the US, UK, European, Japanese,
forex and global commodities markets.

Instrument ids use Yahoo's own symbols: "US:AAPL", "UK:VOD.L", "EU:SAP.DE", "JP:7203.T", "FX:EURUSD=X",
"CMDTY:GC=F". London prices come in pence and US grain futures in cents; both are converted.
Global commodities are the front-month futures series (Yahoo rolls it to the next contract as each expires),
sized per unit of the quote (an ounce, a barrel, a bushel) rather than per exchange contract."""
import math
import threading

from ..intel.net import SourceError
from ..intel.yahoo import INTERVAL, Yahoo
from .coinbase import DataError

US_EXCHANGES = {"NMS", "NYQ", "NGM", "NCM", "ASE", "PCX", "BTS"}
EU_SUFFIXES = (".DE", ".PA", ".AS", ".MI", ".MC", ".BR", ".LS", ".HE", ".VI", ".IR")
MARKET_INFO = {
    "US": {"currency": "USD", "tz": "America/New_York", "per_day": {"1h": 7, "15m": 26, "5m": 78}},
    "UK": {"currency": "GBP", "tz": "Europe/London", "per_day": {"1h": 9, "15m": 34, "5m": 102}},
    "EU": {"currency": "EUR", "tz": "Europe/Berlin", "per_day": {"1h": 9, "15m": 34, "5m": 102}},
    "JP": {"currency": "JPY", "tz": "Asia/Tokyo", "per_day": {"1h": 5, "15m": 20, "5m": 60}},
    "FX": {"currency": "USD", "tz": "Europe/London", "per_day": {"1h": 24, "15m": 96, "5m": 288}},
    "CMDTY": {"currency": "USD", "tz": "America/New_York", "per_day": {"1h": 23, "15m": 92, "5m": 276}},
}
DEFAULTS = {
    "US": [("SPY", "SPDR S&P 500 ETF", "ETF"), ("AAPL", "Apple", "EQ"), ("NVDA", "NVIDIA", "EQ"),
           ("MSFT", "Microsoft", "EQ"), ("TSLA", "Tesla", "EQ"), ("QQQ", "Invesco QQQ (Nasdaq 100)", "ETF")],
    "UK": [("ISF.L", "iShares Core FTSE 100 ETF", "ETF"), ("SHEL.L", "Shell", "EQ"), ("AZN.L", "AstraZeneca", "EQ"),
           ("HSBA.L", "HSBC", "EQ"), ("ULVR.L", "Unilever", "EQ")],
    "EU": [("SAP.DE", "SAP", "EQ"), ("ASML.AS", "ASML", "EQ"), ("MC.PA", "LVMH", "EQ"), ("SIE.DE", "Siemens", "EQ"),
           ("EXS1.DE", "iShares Core DAX ETF", "ETF")],
    "JP": [("7203.T", "Toyota Motor", "EQ"), ("6758.T", "Sony Group", "EQ"), ("9984.T", "SoftBank Group", "EQ"),
           ("1306.T", "TOPIX ETF", "ETF")],
    "FX": [("EURUSD=X", "Euro / US Dollar", "FX"), ("USDJPY=X", "US Dollar / Japanese Yen", "FX"),
           ("GBPUSD=X", "British Pound / US Dollar", "FX"), ("USDINR=X", "US Dollar / Indian Rupee", "FX")],
    "CMDTY": [("GC=F", "Gold futures (COMEX, $ per ounce)", "FUT"), ("CL=F", "WTI crude oil futures (NYMEX, $ per barrel)", "FUT"),
              ("SI=F", "Silver futures (COMEX, $ per ounce)", "FUT"), ("NG=F", "Natural gas futures (NYMEX, $ per mmBtu)", "FUT"),
              ("BZ=F", "Brent crude oil futures (ICE, $ per barrel)", "FUT"), ("HG=F", "Copper futures (COMEX, $ per pound)", "FUT"),
              ("PL=F", "Platinum futures (NYMEX, $ per ounce)", "FUT"), ("ZC=F", "Corn futures (CBOT, $ per bushel)", "FUT"),
              ("ZW=F", "Wheat futures (CBOT, $ per bushel)", "FUT"), ("ZS=F", "Soybean futures (CBOT, $ per bushel)", "FUT"),
              ("KC=F", "Coffee futures (ICE, $ per pound)", "FUT"), ("SB=F", "Sugar futures (ICE, $ per pound)", "FUT"),
              ("CC=F", "Cocoa futures (ICE, $ per tonne)", "FUT"), ("CT=F", "Cotton futures (ICE, $ per pound)", "FUT")],
}
CMDTY_ALIASES = {"GOLD": "GC=F", "SILVER": "SI=F", "CRUDE": "CL=F", "CRUDE OIL": "CL=F", "OIL": "CL=F", "WTI": "CL=F",
                 "BRENT": "BZ=F", "NATURAL GAS": "NG=F", "GAS": "NG=F", "COPPER": "HG=F", "PLATINUM": "PL=F", "CORN": "ZC=F",
                 "WHEAT": "ZW=F", "SOYBEANS": "ZS=F", "SOYBEAN": "ZS=F", "COFFEE": "KC=F", "SUGAR": "SB=F", "COCOA": "CC=F",
                 "COTTON": "CT=F"}
CENTS = ("USX", "USd")          # grains and softs are quoted in US cents


def fits(market: str, q: dict) -> bool:
    sym, qt = str(q.get("symbol", "")), q.get("quoteType")
    if market == "FX":
        return qt == "CURRENCY" and sym.endswith("=X")
    if market == "CMDTY":
        return qt == "FUTURE" and sym.endswith("=F")
    if qt not in ("EQUITY", "ETF"):
        return False
    if market == "US":
        return q.get("exchange") in US_EXCHANGES and "." not in sym
    if market == "UK":
        return sym.endswith(".L")
    if market == "EU":
        return sym.endswith(EU_SUFFIXES)
    if market == "JP":
        return sym.endswith(".T")
    return False


class YahooProvider:
    max_days = {tf: v[1] for tf, v in INTERVAL.items()}

    def __init__(self, market: str, yahoo: Yahoo):
        self.market, self.yahoo = market, yahoo
        self.info = MARKET_INFO[market]
        self._known: dict[str, dict] = {}
        self._lock = threading.Lock()
        for sym, name, t in DEFAULTS[market]:
            self._remember(self._make(sym, name, t))

    def ready(self) -> bool:
        return True

    # ---------- instruments ----------
    def _make(self, sym: str, name: str | None, itype: str, currency: str | None = None) -> dict:
        sym = sym.upper()
        if self.market == "FX":
            currency = currency or (sym[3:6] if len(sym) >= 8 else "USD")
            display = f"{sym[:3]}/{sym[3:6]}" if len(sym) >= 8 else sym
        else:
            display = sym
        return {"id": f"{self.market}:{sym}", "token": sym, "symbol": display, "name": name or display,
                "exchange": {"US": "US", "UK": "LSE", "EU": "Europe", "JP": "TSE", "FX": "Forex", "CMDTY": "Futures"}[self.market],
                "type": itype, "market": self.market, "currency": currency or self.info["currency"],
                "step": 1, "lot": 1, "fno": False, "expiry": None, "strike": None, "tz": self.info["tz"]}

    def _remember(self, inst: dict) -> dict:
        with self._lock:
            self._known[inst["token"]] = inst
        return inst

    def instrument(self, key: str) -> dict | None:
        key = key.strip().upper()
        if self.market == "CMDTY":
            key = CMDTY_ALIASES.get(key, key)
        hit = self._known.get(key)
        if hit:
            return hit
        try:      # the long daily window: the backtest or scan that usually follows reuses it
            raw = self.yahoo.chart(key, "1d", self.yahoo.WINDOW)["meta"]
        except SourceError:
            return None
        m = {"price": raw.get("regularMarketPrice"), "name": raw.get("longName") or raw.get("shortName"),
             "currency": raw.get("currency"), "type": raw.get("instrumentType")}
        if m.get("price") is None:
            return None
        itype = "FX" if self.market == "FX" else "FUT" if self.market == "CMDTY" else ("ETF" if m.get("type") == "ETF" else "EQ")
        currency = "GBP" if m.get("currency") in ("GBp", "GBX") else "USD" if m.get("currency") in CENTS else m.get("currency")
        return self._remember(self._make(key, m.get("name"), itype, currency))

    def defaults(self) -> list[dict]:
        return [self._known[s.upper()] for s, _, _ in DEFAULTS[self.market]]

    def search(self, q: str, allow_fno: bool = True, limit: int = 25) -> list[dict]:
        q = q.strip()
        if len(q) < 1:
            return []
        if self.market == "CMDTY":      # the usual names first: "gold" means COMEX gold, not a gold miner
            words = q.upper()
            hits = [i for s, name, _ in DEFAULTS["CMDTY"] if (i := self._known[s]) and
                    (words in name.upper() or words == s or CMDTY_ALIASES.get(words) == s)]
            if hits:
                return hits[:limit]
        try:
            rows = self.yahoo.search(q, limit=25)
        except SourceError as e:
            raise DataError(str(e)) from None
        out = []
        for x in rows:
            if not fits(self.market, x):
                continue
            itype = "FX" if self.market == "FX" else "FUT" if self.market == "CMDTY" else ("ETF" if x.get("quoteType") == "ETF" else "EQ")
            known = self._known.get(str(x["symbol"]).upper())
            out.append(known or self._remember(self._make(x["symbol"], x.get("longname") or x.get("shortname"), itype)))
            if len(out) >= limit:
                break
        return out

    # ---------- prices ----------
    def _scale(self, inst: dict, meta: dict) -> float:
        return 0.01 if meta.get("currency") in ("GBp", "GBX", *CENTS) else 1.0

    def ltp(self, inst: dict) -> float | None:
        try:
            m = self.yahoo.chart(inst["token"], "1d", 7, ttl=30)["meta"]
        except SourceError as e:
            raise DataError(str(e)) from None
        p = m.get("regularMarketPrice")
        return p * self._scale(inst, m) if p is not None else None

    def warmup_days(self, tf: str, candles: int = 210) -> int:
        if tf == "1d":
            return math.ceil(candles * 7 / 5) + 10
        per_day = self.info["per_day"][tf]
        return math.ceil(candles / per_day * 7 / 5) + 3

    def history(self, inst: dict, tf: str, days: int) -> list[dict]:
        try:
            c = self.yahoo.chart(inst["token"], tf, days)
        except SourceError as e:
            raise DataError(str(e)) from None
        k = self._scale(inst, c["meta"])
        if k == 1.0:
            return c["candles"]
        return [{**b, "o": b["o"] * k, "h": b["h"] * k, "l": b["l"] * k, "c": b["c"] * k} for b in c["candles"]]

    def closed_candles(self, inst: dict, tf: str, since: str | None) -> list[dict]:
        """Candles that have fully closed after `since`, for live paper trading."""
        from datetime import datetime
        import time as _time
        secs = {"1d": 86400, "1h": 3600, "15m": 900, "5m": 300}[tf]
        bars = self.history(inst, tf, 5 if tf != "1d" else 30)
        cutoff = datetime.fromisoformat(since).timestamp() if since else 0
        now = _time.time()
        out = []
        for b in bars:
            ts = datetime.fromisoformat(b["t"]).timestamp()
            if ts > cutoff and ts + secs <= now:
                out.append(b)
        return out
