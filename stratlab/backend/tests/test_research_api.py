import json

import pytest
from fastapi.testclient import TestClient

from app import db, main
from app.config import settings
from app.intel import ai as A
from app.intel import routes
from app.intel.company import Research
from app.intel.finnhub import Finnhub
from app.intel.news import GoogleNews, Wikipedia
from app.intel.screener import Screener
from app.intel.yahoo import Yahoo
from app.kite_service import KiteService
from tests.fake_intel import fake_finnhub, fake_news, fake_screener, fake_wiki
from tests.fake_yahoo import fake_yahoo

COMPANY_AI = {"summary": "Makes the chips that train AI models.", "scores": {"moat": 90, "growth": 95, "value": 30, "momentum": 80, "health": 85},
              "composite": 78, "valuation": "rich", "valuation_note": "Priced for growth.", "bull": ["Demand", "Software moat"],
              "bear": ["Customer concentration"], "segments": [{"label": "Data centre", "share": 88}, {"label": "Gaming", "share": "9"}],
              "position": "Sells the shovels.", "watch": ["Next earnings"],
              "ideas": [{"title": "Trend rider", "text": "Buy NVDA when the 20-day EMA crosses above the 50-day EMA, 6% stop loss", "why": "Strong trends"},
                        {"title": "", "text": "  "}, "not a dict"]}
SECTOR_AI = {"sector": "AI data centers", "summary": "Power is the bottleneck.", "clusters": [{"name": "Chips", "companies": [{"name": "Nvidia", "ticker": "nvda"}]}],
             "screen": [{"name": "Vertiv", "ticker": "VRT", "composite": 70}, {"name": "Nvidia", "ticker": "NVDA", "composite": 90}],
             "tailwinds": ["Capex"], "risks": ["Rates"], "etfs": [{"ticker": "SMH", "name": "Semis"}]}
PULSE_AI = {"tone": "Calm.", "hot": [{"name": "Reliance", "ticker": "RELIANCE", "why": "Jio"}],
            "flows": [{"title": "FIIs", "detail": "Selling", "direction": "outflow"}, {"title": "x", "detail": "y", "direction": "weird"}],
            "themes": [{"theme": "Capex", "detail": "Rails", "example": "RVNL"}]}
COMPARE_AI = {"verdict": "NVDA is stronger.", "winner": "nvda", "differences": ["Margins"], "a": {"composite": 80, "valuation": "RICH"},
              "b": {"composite": 60, "valuation": "fair"}}


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setattr(settings, "FINNHUB_API_KEY", "k")
    monkeypatch.setattr(settings, "RESEARCH_AI_PER_DAY", 3)
    hub = Research(KiteService(), finnhub=Finnhub(transport=fake_finnhub()), yahoo=Yahoo(transport=fake_yahoo()),
                   screener=Screener(transport=fake_screener()), news=GoogleNews(transport=fake_news()),
                   wiki=Wikipedia(transport=fake_wiki()))
    routes.setup(hub, None, None)
    A._cache.clear()
    calls, usage, settings_store = [], [], {}

    def fake_complete(system, text, **kw):
        calls.append(system)
        if "picks-and-shovels" in system:
            return json.dumps(SECTOR_AI)
        if "market read" in system:
            return json.dumps(PULSE_AI)
        if "comparing two" in system:
            return json.dumps(COMPARE_AI)
        return json.dumps(COMPANY_AI)
    monkeypatch.setattr(A, "complete", fake_complete)
    monkeypatch.setattr(db, "count_usage", lambda u, kind, since: sum(1 for k in usage if k == kind))
    monkeypatch.setattr(db, "add_usage", lambda u, kind: usage.append(kind))
    monkeypatch.setattr(db, "get_setting", lambda k: settings_store.get(k))
    monkeypatch.setattr(db, "set_setting", lambda k, v: settings_store.__setitem__(k, v))
    main.app.dependency_overrides[main.current_profile] = lambda: {"id": "u1", "_plan": "free", "plan": "free"}
    c = TestClient(main.app)
    c.calls, c.usage = calls, usage
    yield c
    main.app.dependency_overrides.clear()


def test_company_and_chart_and_quotes(api):
    c = api.get("/research/company/us/nvda").json()
    assert c["name"] == "NVIDIA Corp" and c["instrument_id"] == "US:NVDA"
    india = api.get("/research/company/IN/RELIANCE").json()
    assert india["metrics"][0]["title"] == "Valuation"
    assert len(api.get("/research/chart/US/AAPL?range=1m").json()["candles"]) > 15
    assert api.get("/research/quotes?region=US&symbols=NVDA,AMD").json()["NVDA"]["price"] > 0
    assert api.get("/research/search?q=reliance&region=IN").json()[0]["symbol"] == "RELIANCE"


def test_bad_inputs(api):
    assert api.get("/research/company/XX/NVDA").status_code == 400
    assert api.get("/research/company/US/<script>").status_code in (400, 404)
    r = api.get("/research/company/US/NOPE")
    assert r.status_code == 502 and "No US company" in r.json()["detail"]["message"]


def test_company_ai_is_cleaned_cached_and_counted(api, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "RAZORPAY_KEY_ID", "rzp_test")        # payments live, so Pro is gated
    monkeypatch.setattr(settings, "RAZORPAY_KEY_SECRET", "s")
    r = api.get("/research/company/US/NVDA/ai").json()
    assert r["valuation"] == "RICH" and r["composite"] == 78 and r["segments"][1] == {"label": "Gaming", "share": 9}
    assert [i["title"] for i in r["ideas"]] == ["Trend rider"]          # blank and malformed ideas dropped
    assert "generated_at" in r and api.usage == ["research_ai"]
    assert "EMA" in api.calls[0] and "MACD" not in api.calls[0]          # free plan: basic indicators only
    api.get("/research/company/US/NVDA/ai")                              # cached: no new AI call, not counted
    assert len(api.calls) == 1 and api.usage == ["research_ai"]
    api.get("/research/company/US/NVDA/ai?refresh=true")
    assert len(api.calls) == 2 and len(api.usage) == 2


def test_daily_ai_allowance(api):
    for sym in ("NVDA", "AAPL", "MSFT"):
        assert api.get(f"/research/company/US/{sym}/ai").status_code == 200
    r = api.get("/research/sector?q=AI data centers&region=US")
    assert r.status_code == 429 and r.json()["detail"]["code"] == "research_ai_limit"
    assert api.get("/research/company/US/NVDA/ai").status_code == 200     # cached reads still work


def test_sector_pulse_compare(api):
    s = api.get("/research/sector?q=AI%20data%20centers&region=US").json()
    assert s["screen"][0]["ticker"] == "NVDA" and s["clusters"][0]["companies"][0]["ticker"] == "NVDA"
    p = api.get("/research/pulse?region=IN").json()
    assert p["indices"][0]["name"] == "NIFTY 50" and p["headlines"]
    pa = api.get("/research/pulse/ai?region=IN").json()
    assert pa["flows"][0]["direction"] == "OUTFLOW" and pa["flows"][1]["direction"] == "ROTATION"
    cmp = api.get("/research/compare?region=US&a=NVDA&b=AAPL").json()
    assert cmp["a"]["name"] == "NVIDIA Corp" and cmp["ai"]["winner"] == "NVDA" and cmp["ai"]["b"]["valuation"] == "FAIR"
    assert api.get("/research/compare?region=US&a=NVDA&b=nvda").status_code == 400


def test_watchlist_round_trip(api):
    assert api.get("/research/watchlist").json() == {"items": []}
    items = [{"region": "IN", "symbol": "reliance", "name": "Reliance"}, {"region": "US", "symbol": "NVDA"},
             {"region": "IN", "symbol": "RELIANCE"}]
    assert len(api.put("/research/watchlist", json={"items": items}).json()["items"]) == 2
    assert api.get("/research/watchlist").json()["items"][0]["symbol"] == "RELIANCE"
    assert api.put("/research/watchlist", json={"items": [{"region": "XX", "symbol": "A"}]}).status_code == 422
