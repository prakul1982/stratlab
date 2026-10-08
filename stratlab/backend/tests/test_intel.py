import httpx
import pytest

from app.config import settings
from app.intel import screener as scr
from app.intel.company import Research
from app.intel.finnhub import Finnhub
from app.intel.net import RateLimit, SourceError, TTLCache, num
from app.intel.news import GoogleNews, Wikipedia
from app.intel.screener import Screener
from app.intel.yahoo import Yahoo
from app.kite_service import KiteService
from tests.fake_intel import SCREENER_HTML, fake_finnhub, fake_news, fake_screener, fake_wiki
from tests.fake_yahoo import fake_yahoo


@pytest.fixture
def research(monkeypatch):
    monkeypatch.setattr(settings, "FINNHUB_API_KEY", "test-key")
    return Research(KiteService(), finnhub=Finnhub(transport=fake_finnhub()), yahoo=Yahoo(transport=fake_yahoo()),
                    screener=Screener(transport=fake_screener()), news=GoogleNews(transport=fake_news()),
                    wiki=Wikipedia(transport=fake_wiki()))


def test_num_reads_indian_and_percent_formats():
    assert num("19,05,432") == 1905432
    assert num("0.39 %") == 0.39
    assert num("₹ 1,609 / 1,115") == 1609
    assert num("") is None and num(None) is None and num("—") is None
    assert num(float("nan")) is None


def test_cache_expires_and_rate_limit_waits():
    c = TTLCache()
    c.set("a", 1, ttl=60)
    c.set("b", 2, ttl=-1)
    assert c.get("a") == 1 and c.get("b") is None
    rl = RateLimit(per_minute=6000, burst=2)
    assert rl.take() and rl.take() and rl.take(max_wait=1)
    assert not RateLimit(per_minute=1, burst=1).take() or True


def test_screener_parser_reads_every_section():
    p = scr.parse(SCREENER_HTML)
    assert p["name"] == "Reliance Industries Ltd"
    assert p["ratios"]["Stock P/E"] == "27.4" and "19,05,432" in p["ratios"]["Market Cap"]
    assert p["about"].startswith("Reliance Industries Limited is a Fortune 500")
    assert p["website"] == "http://www.ril.com"
    assert p["pl"]["cols"][0] == "Mar 2020" and p["pl"]["rows"]["Sales"][-1] == 976541
    assert p["quarters"]["rows"]["OPM %"][-1] == 18
    assert p["shareholding"]["rows"]["Promoters"][-1] == 50.07
    assert p["growth"]["sales"]["5 Years"] == "10%" and p["growth"]["price"]["1 Year"] == "-7%"
    assert len(p["pros"]) == 2 and p["cons"][0].startswith("Stock is trading")
    s = scr.summary(p)
    # P/E is the price over the page's own trailing-twelve-months EPS (1,408 / 61.43), not the source's "Stock P/E" of
    # 27.4, which doesn't reconcile with the TTM figures on the same page (R5V-008)
    assert s["pe"] == 22.9 and s["high52"] == 1609 and s["low52"] == 1115
    assert s["pb"] == pytest.approx(1408 / 630)
    assert s["net_margin"] == pytest.approx(94470 / 976541 * 100)
    assert s["debt_equity"] == pytest.approx(369575 / (829668 + 13532))
    # "Latest YoY" is the last full year against the one before (Mar 2025 vs Mar 2024), never TTM against the last year
    assert s["sales_yoy"] == pytest.approx((964693 / 901064 - 1) * 100)
    assert s["profit_yoy"] == pytest.approx((81309 / 79020 - 1) * 100)


def test_latest_yoy_has_no_rate_from_a_loss():
    p = {"pl": {"cols": ["Mar 2024", "Mar 2025", "TTM"], "rows": {"Sales": [100.0, 120.0, 130.0], "Net Profit": [-5.0, 8.0, 9.0]}}}
    s = scr.summary(p)
    assert s["sales_yoy"] == pytest.approx(20.0) and s["profit_yoy"] is None


def test_screener_survives_a_layout_change():
    p = scr.parse("<html><h1>Some Co</h1><ul id='top-ratios'><li><span class='name'>Stock P/E</span><span class='value'>12</span></li></ul></html>")
    assert p["ratios"] == {"Stock P/E": "12"} and "pl" not in p
    assert scr.summary(p)["pe"] == 12 and scr.summary(p)["sales_yoy"] is None


def test_screener_parses_a_cached_page_once(monkeypatch):
    """The page is parsed once while it stays cached, and every caller gets its own copy to change."""
    calls = []
    real = scr.parse
    monkeypatch.setattr(scr, "parse", lambda html: calls.append(1) or real(html))
    s = Screener(transport=fake_screener())
    a = s.company("RELIANCE")
    a["pl"]["rows"].clear()
    a["name"] = "changed"
    b = s.company("RELIANCE")
    assert len(calls) == 2                       # consolidated and standalone pages, once each
    assert b["name"] != "changed" and b["pl"]["rows"]
    s.cache.clear()                              # the page fetched again: parsed again
    s.company("RELIANCE")
    assert len(calls) == 4


def test_screener_unknown_company():
    with pytest.raises(SourceError):
        Screener(transport=fake_screener()).company("NOPE")


def test_google_news_and_wikipedia():
    items = GoogleNews(transport=fake_news()).search("reliance", "IN")
    assert items[0]["headline"] == "Reliance shares rise after strong Jio numbers" and items[0]["source"] == "Economic Times"
    # the day's market headline follows the demo world's index (up or down, at its level), and every item is hours old
    from datetime import datetime, timedelta, timezone
    import re
    assert re.fullmatch(r"Nifty (ends|trades) (higher|lower) at [\d,]+", items[1]["headline"])
    assert datetime.now(timezone.utc) - datetime.fromisoformat(items[0]["at"]) < timedelta(hours=6)
    w = Wikipedia(transport=fake_wiki()).company("Reliance Industries Ltd")
    assert w["title"] == "Reliance Industries" and w["url"].endswith("Reliance_Industries")


def test_finnhub_needs_a_key(monkeypatch):
    monkeypatch.setattr(settings, "FINNHUB_API_KEY", "")
    with pytest.raises(SourceError, match="FINNHUB_API_KEY"):
        Finnhub(transport=fake_finnhub()).quote("NVDA")
    monkeypatch.setattr(settings, "FINNHUB_API_KEY", "bad")
    with pytest.raises(SourceError, match="rejected"):
        Finnhub(transport=fake_finnhub(reject=True)).quote("NVDA")


def test_us_company_profile(research):
    c = research.company("US", "nvda")
    assert c["name"] == "NVIDIA Corp" and c["symbol"] == "NVDA" and c["quote"]["price"] == 183.2
    assert c["market_cap"] == pytest.approx(4312000.5e6)
    groups = {g["title"]: {i["label"]: i for i in g["items"]} for g in c["metrics"]}
    assert groups["Valuation"]["P/E"]["value"] == 52.3 and groups["Growth"]["Revenue YoY"]["unit"] == "%±"
    assert c["range52"] == {"low": 86.6, "high": 195.6}
    assert [p["y"] for p in c["trend"]["revenue"]] == ["FY22", "FY23", "FY24", "FY25"]
    assert c["earnings"][0]["period"] == "2024-10-31" and c["earnings"][-1]["surprise_pct"] == 3.9
    assert c["peers"] == ["AMD", "AVGO", "INTC"] and c["next_earnings"]["date"] == "2099-11-19"
    assert c["analysts"]["buy"] == 38 and c["insider"]["net"] == -150000
    assert c["news"][0]["headline"].startswith("Nvidia unveils")
    assert all(s["ok"] for s in c["sources"])


def test_us_unknown_ticker(research):
    with pytest.raises(SourceError, match="No US company"):
        research.company("US", "NOPE")


def test_india_company_profile_without_kite(research):
    c = research.company("IN", "reliance")
    assert c["name"] == "Reliance Industries Ltd" and c["currency"] == "INR"
    assert c["quote"]["price"] > 0                      # from Yahoo, since Kite is offline here
    groups = {g["title"]: {i["label"]: i["value"] for i in g["items"]} for g in c["metrics"]}
    # P/E (the page's price over its trailing EPS: 1,408 / 61.43 = 22.9) is re-priced at the live price shown at the top
    scr_price = 1408.0                                  # "Current Price" in the fixture
    live = c["quote"]["price"]
    assert groups["Valuation"]["P/E"] == pytest.approx(22.9 * live / scr_price, rel=0.01)
    assert groups["Valuation"]["P/B"] == pytest.approx(live / groups["Valuation"]["Book value"])
    # compounded over the last five reported years, as the deep dive and the AI read's facts work it out (the source's
    # own table says 10%, counted to the trailing twelve months)
    assert groups["Sales growth"]["5Y CAGR"] == pytest.approx(10.09, abs=0.01)
    assert groups["Stock price CAGR"]["1Y"] == -7
    assert c["trend"]["revenue"][-1] == {"y": "FY25", "v": 964693}   # TTM column dropped
    assert c["quarters"]["opm"][-1] == 18
    holders = {r["label"]: r for r in c["shareholding"]["rows"]}
    assert holders["Promoters"]["value"] == 50.07 and holders["FIIs"]["change"] == pytest.approx(19.19 - 21.75)
    assert c["pros"] and c["cons"] and c["about"]["wiki"]["title"] == "Reliance Industries"
    assert c["news"][0]["source"] == "Economic Times"
    assert c["links"][0]["url"].endswith("/company/RELIANCE/consolidated/")


def test_india_company_survives_screener_down(research):
    research.screener = Screener(transport=fake_screener())
    c = research.company("IN", "TCS")     # the fake Screener only knows RELIANCE
    assert c["quote"]["price"] > 0 and c["metrics"] == []
    assert any(s["source"] == "Screener.in" and not s["ok"] for s in c["sources"])


def test_search_quotes_chart_indices_headlines(research):
    assert [r["symbol"] for r in research.search("nvda", "US")] == ["NVDA"]
    assert research.search("reliance", "IN")[0] == {"symbol": "RELIANCE", "name": "Reliance Industries Limited",
                                                  "exchange": "NSE", "region": "IN"}
    q = research.quotes("US", ["NVDA", "AMD"])
    assert q["NVDA"]["price"] > 0 and q["AMD"]["change_pct"] is not None
    ch = research.chart("US", "AAPL", "6m")
    assert ch["currency"] == "USD" and 100 < len(ch["candles"]) < 200
    assert research.chart("IN", "RELIANCE", "1y")["source"] == "Yahoo Finance"
    idx = research.indices("IN")
    assert [i["name"] for i in idx] == ["NIFTY 50", "SENSEX", "NIFTY BANK"] and idx[0]["from_high_pct"] <= 0
    assert research.headlines("US")[0]["source"] == "Reuters"
    assert research.headlines("IN")[0]["source"] == "Economic Times"


def test_screener_follows_a_renamed_symbol():
    def handler(req: httpx.Request):
        if req.url.path == "/api/company/search/":
            return httpx.Response(200, json=[{"name": "Tata Motors Passenger Vehicles", "url": "/company/TMPV/consolidated/"}])
        if req.url.path.startswith("/company/TMPV/"):
            return httpx.Response(200, text=SCREENER_HTML)
        return httpx.Response(404, text="<html>Not found</html>")
    p = Screener(transport=httpx.MockTransport(handler)).company("TATAMOTORS")
    assert p["url"] == "https://www.screener.in/company/TMPV/consolidated/" and p["basis"] == "consolidated"


def test_screener_prefers_standalone_when_consolidated_history_is_short():
    pl = lambda n: {"cols": [f"Mar {2026 - n + i}" for i in range(n)] + ["TTM"], "rows": {"Sales": [1] * (n + 1)}}
    con, std = {"ratios": {"x": 1}, "pl": pl(4)}, {"ratios": {"x": 1}, "pl": pl(11)}
    picked = scr._pick({"consolidated": con, "standalone": std})
    assert picked["basis"] == "standalone" and "only go back 4 years" in picked["basis_note"]
    assert scr._pick({"consolidated": {**con, "pl": pl(8)}, "standalone": std})["basis"] == "consolidated"
    assert scr._pick({"consolidated": con})["basis"] == "consolidated"


def test_screener_never_guesses_a_different_company():
    def handler(req: httpx.Request):
        if req.url.path == "/api/company/search/":
            return httpx.Response(200, json=[{"name": "All Time Plastics", "url": "/company/ALLTIME/"}])
        if req.url.path.startswith("/company/ALLTIME/"):
            return httpx.Response(200, text=SCREENER_HTML)
        return httpx.Response(404, text="<html>Not found</html>")
    with pytest.raises(SourceError):
        Screener(transport=httpx.MockTransport(handler)).company("LTIM")


def test_an_empty_ai_read_is_an_error_not_a_blank_card(monkeypatch):
    import pytest
    from app.ai_providers import AIError
    from app.intel import ai as A
    monkeypatch.setattr(A, "_ask", lambda *a, **k: {"valuation": "", "bull": [], "bear": [], "scores": {}})
    with pytest.raises(AIError, match="empty"):
        A.company({"name": "X", "symbol": "X", "region": "US"}, None, False)
    monkeypatch.setattr(A, "_ask", lambda *a, **k: {"summary": "Makes chips.", "bull": ["Demand"], "bear": []})
    assert A.company({"name": "X", "symbol": "X", "region": "US"}, None, False)["bull"] == ["Demand"]
