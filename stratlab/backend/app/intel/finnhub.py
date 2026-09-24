"""US company data from Finnhub (free tier: 60 calls a minute).

Set FINNHUB_API_KEY on the server. Everything is cached, so a popular ticker costs
one set of calls however many people open it."""
from datetime import date, timedelta

import httpx

from ..config import settings
from .net import Source, SourceError


class Finnhub(Source):
    name = "Finnhub"

    def __init__(self, transport: httpx.BaseTransport | None = None):
        super().__init__("https://finnhub.io/api/v1", per_minute=55, burst=25, transport=transport)

    def ready(self) -> bool:
        return bool(settings.FINNHUB_API_KEY)

    def check(self, r: httpx.Response):
        if r.status_code in (401, 403):
            raise SourceError(self.name, "Finnhub rejected FINNHUB_API_KEY, or this data needs a paid plan.")
        super().check(r)

    def get(self, path: str, ttl: float = 300, **params):
        if not self.ready():
            raise SourceError(self.name, "US company data needs FINNHUB_API_KEY on the server (free at finnhub.io).")
        return self.fetch(path, {**params, "token": settings.FINNHUB_API_KEY}, ttl=ttl)

    # ---------- endpoints ----------
    def profile(self, sym: str) -> dict:
        return self.get("/stock/profile2", ttl=24 * 3600, symbol=sym) or {}

    def quote(self, sym: str) -> dict:
        return self.get("/quote", ttl=60, symbol=sym) or {}

    def metrics(self, sym: str) -> dict:
        return (self.get("/stock/metric", ttl=6 * 3600, symbol=sym, metric="all") or {}).get("metric") or {}

    def news(self, sym: str, days: int = 30) -> list:
        today = date.today()
        return self.get("/company-news", ttl=1800, symbol=sym, **{"from": (today - timedelta(days=days)).isoformat(),
                                                                 "to": today.isoformat()}) or []

    def peers(self, sym: str) -> list:
        return self.get("/stock/peers", ttl=24 * 3600, symbol=sym) or []

    def recommendation(self, sym: str) -> list:
        return self.get("/stock/recommendation", ttl=12 * 3600, symbol=sym) or []

    def earnings(self, sym: str) -> list:
        return self.get("/stock/earnings", ttl=12 * 3600, symbol=sym) or []

    def financials(self, sym: str) -> dict:
        return self.get("/stock/financials-reported", ttl=24 * 3600, symbol=sym, freq="annual") or {}

    def insider(self, sym: str) -> dict:
        return self.get("/stock/insider-transactions", ttl=12 * 3600, symbol=sym) or {}

    def earnings_calendar(self, sym: str) -> list:
        today = date.today()
        r = self.get("/calendar/earnings", ttl=12 * 3600, symbol=sym,
                     **{"from": today.isoformat(), "to": (today + timedelta(days=120)).isoformat()}) or {}
        return r.get("earningsCalendar") or []

    def search(self, q: str) -> list:
        return (self.get("/search", ttl=24 * 3600, q=q) or {}).get("result") or []

    def market_news(self) -> list:
        return self.get("/news", ttl=900, category="general") or []
