"""The whole app wired to fakes: an in-memory database with signed-in users, fake market data for every market,
fake company, news, exchange and document sources, and a fake AI whose answers can be good, malformed or failing.
Real network calls are refused, so anything not faked behaves like a source that is down. Used by the stress tests."""
import json
import random
import sys

import httpx
from fastapi.testclient import TestClient

from app import ai_providers, db, main
from app.config import settings
from app.data import Registry
from app.data.coinbase import CoinbaseProvider
from app.intel import routes
from app.intel.company import Research
from app.intel.filings import NSEFilings
from app.intel.finnhub import Finnhub
from app.intel.news import GoogleNews, Wikipedia
from app.intel.screener import Screener
from app.intel.yahoo import Yahoo
from app.kite_service import TickHub
from app.live import LiveManager
from app.options.data import OptionsData
from app.options.session import IST
from datetime import datetime
from tests import fake_kite
from tests.fake_options_kite import FakeOptionsKite
from tests.fake_db import FakeSupabase, headers
from tests.fake_intel import fake_finnhub, fake_news, fake_screener, fake_wiki
from tests.fake_yahoo import fake_yahoo
from tests.pdfmaker import make_pdf
from tests.test_notebooks import wavy_coinbase

AI_SHAPES = [
    lambda: {"summary": "A company.", "segments": [], "capex": [], "outlook": [], "guidance": [], "measures": []},
    lambda: {"name": "Idea", "tf": "1d", "entry": [], "exit": [], "risk": {}},
    lambda: {},
    lambda: [],
    lambda: {"summary": None, "segments": "not a list", "capex": [{"what": None}], "guidance": [{"metric": 5, "low": "x"}]},
    lambda: {"scores": {"moat": "high"}, "composite": "NaN", "ideas": [None, 3, {"text": 7}]},
]


class FakeAI:
    """mode: "ok" (shapes in turn), "garbage" (not JSON), "fail" (provider error), "busy" (all providers busy)."""

    def __init__(self):
        self.mode, self.i, self.calls = "ok", 0, 0

    def __call__(self, system, text, **kw):
        self.calls += 1
        if self.mode == "fail":
            raise ai_providers.AIError("The AI couldn't answer.")
        if self.mode == "busy":
            raise ai_providers.AIBusy("Every AI provider is busy.")
        if self.mode == "garbage":
            return "Sure! Here is the answer: {not json"
        self.i += 1
        return json.dumps(AI_SHAPES[self.i % len(AI_SHAPES)]())


def _nse():
    rows = [{"symbol": "RELIANCE", "desc": "Investor Presentation", "attchmntText": "Investor presentation for Q1 FY27",
             "sort_date": "2026-08-01 18:10:05", "seq_id": "1", "attchmntFile": "https://nsearchives.nseindia.com/p.pdf"},
            {"symbol": "RELIANCE", "desc": "Analysts/Institutional Investor Meet/Con. Call Updates",
             "attchmntText": "Transcript of the earnings call", "sort_date": "2026-08-05 18:10:05", "seq_id": "2",
             "attchmntFile": "https://nsearchives.nseindia.com/t.pdf"},
            {"symbol": "RELIANCE", "desc": "Qualified Institutions Placement", "attchmntText": "QIP opened",
             "sort_date": "2026-09-20 18:10:05", "seq_id": "3", "attchmntFile": "https://nsearchives.nseindia.com/q.pdf"}]

    def handler(r: httpx.Request):
        if r.url.path == "/":
            return httpx.Response(200, text="<html></html>", headers={"set-cookie": "nsit=abc; Path=/"})
        if r.url.path == "/api/corporate-announcements":
            return httpx.Response(200, json=rows)
        if r.url.path == "/api/quote-equity":
            return httpx.Response(200, json={"industryInfo": {"macro": "Energy", "industry": "Refineries"},
                                             "priceInfo": {"lastPrice": 2900.5}})
        return httpx.Response(200, text="<html></html>")
    return NSEFilings(transport=httpx.MockTransport(handler))


def _docs():
    pdf = make_pdf(["Investor presentation. Revenue grew 12%. We expect EBITDA margin of 24% in FY27."] * 60)
    return main.Docs(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=pdf)), check_host=lambda h: True)


def _no_network(self, request):
    raise httpx.ConnectError("network disabled in tests", request=request)


def build(monkeypatch) -> dict:
    """Wire the app to fakes. Returns handles the tests use: the client, the fake AI, the fake database."""
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", _no_network)
    fake_db = FakeSupabase()
    monkeypatch.setattr(db, "_client", fake_db)
    db._profiles.clear()
    from app import auth
    auth._cache.clear()
    monkeypatch.setattr(settings, "ADMIN_EMAILS", "owner@example.com")
    monkeypatch.setattr(settings, "FINNHUB_API_KEY", "k")
    kite = fake_kite.online()
    markets = Registry(kite, CoinbaseProvider(transport=wavy_coinbase()), yahoo=Yahoo(transport=fake_yahoo()))
    ticks = TickHub(kite)
    monkeypatch.setattr(ticks, "start", lambda: None)
    options = OptionsData(FakeOptionsKite(live=True, drift={}, clock=lambda: datetime.now(IST).replace(hour=12, minute=0)))
    manager = LiveManager(kite, ticks, markets, options)
    for name, v in (("kite", kite), ("hub", ticks), ("markets", markets), ("options_data", options), ("manager", manager)):
        monkeypatch.setattr(main, name, v)
    hub = Research(kite, finnhub=Finnhub(transport=fake_finnhub()), yahoo=Yahoo(transport=fake_yahoo()),
                   screener=Screener(transport=fake_screener()), news=GoogleNews(transport=fake_news()),
                   wiki=Wikipedia(transport=fake_wiki()))
    monkeypatch.setattr(main, "research_hub", hub)
    routes.setup(hub, None, None)
    monkeypatch.setattr(main, "filings_feed", _nse())
    monkeypatch.setattr(main, "deep_docs", _docs())
    import importlib
    for m in ("app.intel.ai", "app.ask", "app.ideas", "app.deepdive", "app.report_card", "app.ai_writer", "app.importer"):
        importlib.import_module(m)              # load them now, so their copy of `complete` is swapped below
    ai, real_complete = FakeAI(), ai_providers.complete
    for name, mod in list(sys.modules.items()):
        if name.startswith("app.") and getattr(mod, "complete", None) is real_complete:
            monkeypatch.setattr(mod, "complete", ai)
    from app.intel import ai as intel_ai
    intel_ai._cache.clear()
    client = TestClient(main.app, raise_server_exceptions=False)
    return {"client": client, "ai": ai, "db": fake_db, "rng": random.Random(7), "headers": headers, "kite": kite,
            "manager": manager}
