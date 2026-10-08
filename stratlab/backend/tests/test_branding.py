"""Data providers are never named to users: research payloads, errors and the market list."""
from fastapi.testclient import TestClient

from app import main
from app.branding import public_research, public_text

NAMES = ("Kite", "Zerodha", "Yahoo", "Screener", "Finnhub", "finnhub.io", "FINNHUB_API_KEY")


def test_messages_are_reworded():
    for msg in ["Market data is offline. The admin needs to complete today's Kite login.", "Yahoo has no prices for XYZ.",
                "Screener.in has no page for ABC.", "US company data needs FINNHUB_API_KEY on the server (free at finnhub.io).",
                "Zerodha cancelled today's Kite token", "Couldn't reach Yahoo Finance (ConnectError)."]:
        out = public_text(msg)
        assert not any(n in out for n in NAMES), out
    assert public_text("Kitex and kites") == "Kitex and kites"      # whole words only
    assert public_text(None) is None


def test_research_payload_is_relabelled():
    company = {"name": "Reliance", "sources": [{"source": "Screener.in", "ok": True, "error": None},
                                               {"source": "Yahoo Finance", "ok": False, "error": "Yahoo is busy (our rate limit)."}],
               "links": [{"label": "Screener.in", "url": "https://www.screener.in/company/RELIANCE/"},
                         {"label": "Yahoo Finance", "url": "https://finance.yahoo.com/quote/NVDA"},
                         {"label": "Wikipedia", "url": "https://en.wikipedia.org/wiki/Reliance"}],
               "news": [{"headline": "h", "source": "Yahoo Finance"}],
               "chart": {"source": "Kite", "candles": []}}
    out = public_research(company)
    assert [s["source"] for s in out["sources"]] == ["Fundamentals", "Market data"]
    assert "Yahoo" not in out["sources"][1]["error"]
    assert [l["label"] for l in out["links"]] == ["Company profile"]      # the link stays, under a plain label (R5O-020)
    assert out["chart"]["source"] == "Live prices"
    assert out["news"][0]["source"] is None       # a data provider standing in as the "publisher" is not named (R5O-020)


def test_market_list_does_not_name_the_provider():
    rows = TestClient(main.app).get("/markets").json()
    assert rows and all("provider" not in r for r in rows)
    assert not any(n in str(rows) for n in ("Kite", "Zerodha", "Yahoo", "Screener"))
