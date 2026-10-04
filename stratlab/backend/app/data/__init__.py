"""Market data from any source, behind one interface.

Instrument ids are "<MARKET>:<key>": "IN:256265" (a Kite token), "CRYPTO:BTC-USD".
A bare number is treated as a Kite token, for older saved strategies."""
from datetime import datetime
from zoneinfo import ZoneInfo

from ..kite_service import KiteService
from .coinbase import CoinbaseProvider, DataError
from . import calendar
from .markets import BY_ID, MARKETS
from .cds import CDSProvider
from .mcx import MCXProvider
from .yahoo_markets import YahooProvider

KITE_MAX_DAYS = {"1d": 3650, "1h": 730, "15m": 365, "5m": 120}


class KiteProvider:
    market = "IN"
    max_days = KITE_MAX_DAYS

    def __init__(self, kite: KiteService):
        self.kite = kite

    def ready(self) -> bool:
        return self.kite.ready()

    def instrument(self, key: str) -> dict | None:
        try:
            return self.kite.instrument(int(key))
        except ValueError:
            return None

    def defaults(self) -> list[dict]:
        return self.kite.defaults()

    def search(self, q: str, allow_fno: bool = True, limit: int = 25) -> list[dict]:
        return self.kite.search(q, allow_fno=allow_fno, limit=limit)

    def equity(self, symbol: str) -> dict | None:
        """A listed company's stock by its exact symbol (any NSE series) or BSE code."""
        return self.kite.equity(symbol)

    def ltp(self, inst: dict) -> float | None:
        return self.kite.ltp(inst["token"])

    @staticmethod
    def warmup_days(tf: str, candles: int = 210) -> int:
        return KiteService.warmup_days(tf, candles)

    def history(self, inst: dict, tf: str, days: int) -> list[dict]:
        return self.kite.history(inst["token"], tf, days)


def split_id(inst_id: str) -> tuple[str, str]:
    inst_id = str(inst_id).strip()
    if ":" not in inst_id:
        return "IN", inst_id
    market, key = inst_id.split(":", 1)
    return market.upper(), key


class Registry:
    def __init__(self, kite: KiteService, crypto: CoinbaseProvider | None = None, yahoo=None):
        from ..intel.yahoo import Yahoo
        yahoo = yahoo or Yahoo()
        self.providers = {"IN": KiteProvider(kite), "CRYPTO": crypto or CoinbaseProvider(),
                          **{m: YahooProvider(m, yahoo) for m in ("US", "UK", "EU", "JP", "FX", "CMDTY")},
                          "MCX": MCXProvider(kite), "CDS": CDSProvider(kite)}

    def provider(self, market: str):
        return self.providers.get(market)

    def resolve(self, inst_id: str):
        """(provider, instrument) for an id; either may be None."""
        market, key = split_id(inst_id)
        prov = self.providers.get(market)
        return prov, (prov.instrument(key) if prov else None)

    def search(self, q: str, market: str | None, allow_fno: bool) -> list[dict]:
        markets = [market] if market else list(self.providers)
        out = []
        for m in markets:
            prov = self.providers.get(m)
            if prov and prov.ready():
                try:
                    out += prov.search(q, allow_fno=allow_fno, limit=25 if market else 12)
                except Exception as e:  # one source being down shouldn't break search in the others
                    if market:
                        raise
                    print("search failed:", m, e)
        return out

    def defaults(self) -> list[dict]:
        out = []
        for prov in self.providers.values():
            if prov.ready():
                try:
                    out += prov.defaults()
                except Exception as e:  # one source being down shouldn't hide the others
                    print("defaults failed:", prov.market, e)
        return out

    def markets(self) -> list[dict]:
        out = []
        for m in MARKETS:
            prov = self.providers.get(m["id"])
            if m["provider"] == "csv":
                status = "live"
            elif prov is None:
                status = "soon"
            else:
                status = "live" if prov.ready() else "offline"
            local = datetime.now(ZoneInfo(m["tz"])).date()
            public = {k: v for k, v in m.items() if k != "provider"}     # which data provider is internal
            out.append({**public, "status": status, "max_days": getattr(prov, "max_days", None),
                        "holidays": calendar.holidays(m["id"], local)})
        return out


__all__ = ["Registry", "DataError", "BY_ID", "MARKETS", "split_id"]
