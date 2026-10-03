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


class Switch(httpx.BaseTransport):
    """A fake source's transport with a fault switch: "down", "timeout", "500", "429", "403", "garbage" (a page
    instead of data), "empty" (valid but empty data) or None (normal)."""

    def __init__(self, inner: httpx.BaseTransport):
        self.inner, self.mode = inner, None

    def handle_request(self, request):
        m = self.mode
        if m == "down":
            raise httpx.ConnectError("connection refused", request=request)
        if m == "timeout":
            raise httpx.ReadTimeout("timed out", request=request)
        if m in ("500", "429", "403"):
            return httpx.Response(int(m), text="error", request=request)
        if m == "garbage":
            return httpx.Response(200, text="<html><body>Access denied. Please verify you are human.</body></html>",
                                  headers={"content-type": "text/html"}, request=request)
        if m == "empty":
            return httpx.Response(200, json={}, request=request)
        return self.inner.handle_request(request)


def _nse(sw=None):
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
        if r.url.path == "/api/equity-stockIndices":
            idx = r.url.params.get("index", "")
            names = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ITC"] if idx == "NIFTY 500" else []
            return httpx.Response(200, json={"data": [{"symbol": idx, "priority": 1}] + [{"symbol": n} for n in names]})
        if r.url.path == "/content/equities/EQUITY_L.csv":
            lines = ["SYMBOL,NAME OF COMPANY, SERIES, DATE OF LISTING, PAID UP VALUE"]
            lines += [f"CO{i},Company {i} Limited,EQ,01-Jan-2010,10" for i in range(120)]
            lines += ["RELIANCE,Reliance Industries Limited,EQ,29-Nov-1995,10", "NEWCO,New Company Limited,EQ,"
                      + datetime.now().strftime("%d-%b-%Y") + ",10", "SOMEBOND,Some Bond,N1,01-Jan-2020,1000"]
            return httpx.Response(200, text="\n".join(lines))
        if r.url.path == "/api/holiday-master":
            return httpx.Response(200, json={"CM": [{"tradingDate": "26-Jan-2027", "weekDay": "Tuesday", "description": "Republic Day"},
                                                    {"tradingDate": "22-Mar-2027", "weekDay": "Monday", "description": "Holi"}],
                                             "FO": []})
        if r.url.path == "/api/quote-equity":
            return httpx.Response(200, json={"industryInfo": {"macro": "Energy", "industry": "Refineries"},
                                             "priceInfo": {"lastPrice": 2900.5}})
        return httpx.Response(200, text="<html></html>")
    t = httpx.MockTransport(handler)
    return NSEFilings(transport=sw(t) if sw else t)


def _docs(sw=None):
    pdf = make_pdf(["Investor presentation. Revenue grew 12%. We expect EBITDA margin of 24% in FY27."] * 60)
    t = httpx.MockTransport(lambda r: httpx.Response(200, content=pdf))
    return main.Docs(transport=sw(t) if sw else t, check_host=lambda h: True)


def _no_network(self, request):
    raise httpx.ConnectError("network disabled in tests", request=request)


def build(monkeypatch, real_clock: bool = False) -> dict:
    """Wire the app to fakes. Returns handles the tests use: the client, the fake AI, the fake database."""
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", _no_network)
    fake_db = FakeSupabase()
    monkeypatch.setattr(db, "_client", fake_db)
    db._profiles.clear()
    from app import auth
    auth._cache.clear()
    monkeypatch.setattr(settings, "ADMIN_EMAILS", "owner@example.com")
    monkeypatch.setattr(settings, "FINNHUB_API_KEY", "k")
    faults: dict[str, Switch] = {}

    def sw(name):
        def wrap(t):
            faults[name] = Switch(t)
            return faults[name]
        return wrap
    kite = fake_kite.online()
    markets = Registry(kite, CoinbaseProvider(transport=sw("crypto")(wavy_coinbase())),
                       yahoo=Yahoo(transport=sw("market data")(fake_yahoo(varied=True))))
    ticks = TickHub(kite)
    monkeypatch.setattr(ticks, "start", lambda: None)
    clock = (lambda: datetime.now(IST)) if real_clock else (lambda: datetime.now(IST).replace(hour=12, minute=0))
    options = OptionsData(FakeOptionsKite(live=True, drift={}, clock=clock))
    manager = LiveManager(kite, ticks, markets, options)
    for name, v in (("kite", kite), ("hub", ticks), ("markets", markets), ("options_data", options), ("manager", manager)):
        monkeypatch.setattr(main, name, v)
    hub = Research(kite, finnhub=Finnhub(transport=sw("us company data")(fake_finnhub())),
                   yahoo=Yahoo(transport=sw("research market data")(fake_yahoo(varied=True))),
                   screener=Screener(transport=sw("fundamentals")(fake_screener())), news=GoogleNews(transport=sw("news")(fake_news())),
                   wiki=Wikipedia(transport=sw("wikipedia")(fake_wiki())))
    monkeypatch.setattr(main, "research_hub", hub)
    routes.setup(hub, None, None)
    monkeypatch.setattr(main, "filings_feed", _nse(sw("exchange")))
    monkeypatch.setattr(main, "deep_docs", _docs(sw("documents")))
    from app.intel.sec import SEC
    from tests import fake_sec
    monkeypatch.setattr(main, "sec_feed", SEC(transport=sw("sec")(fake_sec.transport())))
    import importlib
    for m in ("app.intel.ai", "app.ask", "app.ideas", "app.deepdive", "app.report_card", "app.ai_writer", "app.importer"):
        importlib.import_module(m)              # load them now, so their copy of `complete` is swapped below
    ai, real_complete = FakeAI(), ai_providers.complete
    for name, mod in list(sys.modules.items()):
        if name.startswith("app.") and getattr(mod, "complete", None) is real_complete:
            monkeypatch.setattr(mod, "complete", ai)
    from app.intel import ai as intel_ai
    intel_ai._cache.clear()
    from app import audit
    runner = audit.Runner()
    monkeypatch.setattr(main, "audit_runner", runner)
    monkeypatch.setattr(main, "market_audit", audit.MarketAudit(lambda: main.filings_feed.all_equities(), main._market_check,
                                                                busy_fn=lambda: bool(runner.state.get("running")), pause=0))
    monkeypatch.setattr(main, "market_audit_us", audit.MarketAudit(lambda: main._sec_companies(), lambda s: main.audit_one(s, False, None, "US"),
                                                                   busy_fn=lambda: bool(runner.state.get("running")), pause=0,
                                                                   key="audit:market-us"))
    client = TestClient(main.app, raise_server_exceptions=False)

    def close():
        """Stop anything a test left running in the background: the audit, paper sessions."""
        runner.cancel()
        for sid in list(manager.sessions):
            try:
                manager.stop(sid, "test over")
            except Exception:
                manager.sessions.pop(sid, None)
    return {"client": client, "ai": ai, "db": fake_db, "rng": random.Random(7), "headers": headers, "kite": kite,
            "manager": manager, "faults": faults, "close": close}
