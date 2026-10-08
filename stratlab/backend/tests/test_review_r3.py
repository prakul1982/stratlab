"""Round 3 review fixes: a company page shows only its own description and news, one price and one market value for a
company on every page, sane financial ratios, and a demo world that tells one consistent story."""
import httpx
import pytest

from app import main  # noqa: F401,I001  (first: the app wires the modules)
from app.intel import news as N
from app.intel.company import Research
from app.intel.screener import Screener
from tests import fake_kite
from tests.fake_intel import fake_finnhub, fake_screener
from tests.fake_yahoo import fake_yahoo


# ---------- R3-001: only the page company's text and news ----------
def test_a_description_must_name_the_company():
    assert N.is_about("Tata Consultancy Services", "Tata Consultancy Services")
    assert N.is_about("Reliance Industries Ltd", "Reliance Industries")
    assert N.is_about("Larsen & Toubro", "Larsen & Toubro")
    assert N.is_about("State Bank of India", "State Bank of India")
    assert not N.is_about("Tata Consultancy Services", "Tata Steel")                 # same group, another company
    assert not N.is_about("Tata Consultancy Services", "Reliance Industries")


def test_a_headline_counts_when_it_names_the_company():
    assert N.mentions("Tata Consultancy Services", "TCS", "TCS shares steady ahead of results")
    assert N.mentions("Infosys", "INFY", "Infosys sets a date for its board meeting")
    assert N.mentions("Reliance Industries", "RELIANCE", "Reliance shares rise after strong Jio numbers")
    assert not N.mentions("Tata Consultancy Services", "TCS", "Reliance shares rise after strong Jio numbers")
    assert not N.mentions("Tata Consultancy Services", "TCS", "Tata Steel falls on weak demand")    # the group's name alone
    assert not N.mentions("Tata Consultancy Services", "TCS", "Nifty ends higher as banks gain")


def _wiki(search_title: str, pages: dict) -> N.Wikipedia:
    def handler(req: httpx.Request):
        if req.url.path == "/w/api.php":
            return httpx.Response(200, json={"query": {"search": [{"title": search_title}]}})
        title = req.url.path.rsplit("/", 1)[1].replace("_", " ")
        if title in pages:
            return httpx.Response(200, json={"title": title, "extract": pages[title], "type": "standard"})
        return httpx.Response(404)
    return N.Wikipedia(transport=httpx.MockTransport(handler))


def test_wikipedia_never_gives_another_companys_article():
    pages = {"Reliance Industries": "Reliance Industries Limited is a conglomerate.",
             "Tata Consultancy Services": "Tata Consultancy Services is an IT services company."}
    # the search's top hit is another company: the article under the company's own name instead
    got = _wiki("Reliance Industries", pages).company("Tata Consultancy Services Ltd")
    assert got["title"] == "Tata Consultancy Services"
    # no article for this company at all: nothing, rather than someone else's
    assert _wiki("Reliance Industries", pages).company("Tiny Widgets Ltd") is None


def test_company_news_keeps_only_its_own_headlines():
    feed = """<?xml version="1.0"?><rss><channel>
<item><title>Reliance shares rise after strong Jio numbers - ET</title><link>https://e.x/1</link><source>ET</source></item>
<item><title>TCS shares steady ahead of results - Mint</title><link>https://e.x/2</link><source>Mint</source></item>
<item><title>Nifty ends higher - Mint</title><link>https://e.x/3</link><source>Mint</source></item>
</channel></rss>"""
    hub = Research(fake_kite.online(), finnhub=None, yahoo=None, screener=Screener(transport=fake_screener()),
                   news=N.GoogleNews(transport=httpx.MockTransport(lambda r: httpx.Response(200, text=feed))),
                   wiki=_wiki("Reliance Industries", {"Reliance Industries": "A conglomerate."}))
    c = hub.company("IN", "TCS")
    assert [n["headline"] for n in c["news"]] == ["TCS shares steady ahead of results"]
    assert c["about"]["wiki"] is None                    # Reliance's article is not TCS's description
    r = hub.company("IN", "RELIANCE")
    assert [n["headline"] for n in r["news"]] == ["Reliance shares rise after strong Jio numbers"]


@pytest.fixture
def w(monkeypatch):
    from tests import world as W
    world = W.build(monkeypatch)
    yield world
    world["close"]()


def H(token="pro-token"):
    from tests.fake_db import headers
    return headers(token)


# ---------- R3-005: no nonsense ratios ----------
def test_cash_against_a_tiny_profit_is_left_out():
    from app.intel import key_facts as K
    years = [{"year": f"Mar {2021 + i}", "cfo": 150000.0, "profit": p} for i, p in enumerate([20.0, 108.0, 122.0])]
    assert K._cash_vs_profit({"years": years}) is None                       # 1,46,000% of net profit says nothing
    years = [{"year": f"Mar {2021 + i}", "cfo": 110.0, "profit": 100.0} for i in range(3)]
    assert K._cash_vs_profit({"years": years}) == "110% of net profit over 3 years"


# ---------- R3-004 and R3-010: an AI read with nothing in it is "unavailable", never a blank or a failed request ----------
def test_an_empty_comparison_is_unavailable_not_blank(w):
    w["ai"].i = 2                                    # the fake AI's next answer is {} (no verdict)
    r = w["client"].get("/research/compare?region=IN&a=TCS&b=INFY", headers=H())
    assert r.status_code == 200
    got = r.json()
    assert got["ai"].get("error") and not got["ai"].get("verdict")
    assert got["b"]["name"] and got["b"]["quote"]["price"] > 0                # the numbers don't depend on it
    from app.intel.routes import market_open
    assert got["a"]["market_open"] is got["b"]["market_open"] is market_open("IN")       # last close or today, as on the company page


def test_the_market_read_answers_unavailable_instead_of_failing(w):
    w["ai"].mode = "garbage"
    for path in ("/research/pulse/ai?region=IN", "/research/pulse/ai?region=IN&focus="):
        r = w["client"].get(path, headers=H())
        assert r.status_code == 200 and r.json()["unavailable"] is True and r.json()["message"]
    w["ai"].mode = "ok"
    w["ai"].i = 2                                    # {}: no tone
    r = w["client"].get("/research/pulse/ai?region=IN&refresh=true", headers=H())
    assert r.status_code == 200 and r.json()["unavailable"] is True


# ---------- R3-003: out of hours the price is the last close, and the page is told so ----------
def test_market_open_follows_the_markets_hours():
    from datetime import datetime, timezone
    from app.intel.routes import market_open
    assert market_open("IN", datetime(2026, 10, 8, 6, 0, tzinfo=timezone.utc))          # Thursday 11:30 IST
    assert not market_open("IN", datetime(2026, 10, 8, 2, 0, tzinfo=timezone.utc))      # 07:30 IST, before the open
    assert not market_open("IN", datetime(2026, 10, 2, 6, 0, tzinfo=timezone.utc))      # Gandhi Jayanti
    assert market_open("US", datetime(2026, 10, 8, 15, 0, tzinfo=timezone.utc))         # 11:00 in New York
    assert not market_open("US", datetime(2026, 10, 10, 15, 0, tzinfo=timezone.utc))    # a Saturday


def test_company_page_says_whether_its_market_is_open(w):
    from app.intel.routes import market_open
    c = w["client"].get("/research/company/IN/RELIANCE", headers=H()).json()
    assert c["market_open"] is market_open("IN")


# ---------- R3-002: one price and one market value for a company everywhere (the real app's part) ----------
def test_screens_and_deep_dive_are_priced_at_the_last_close(w, monkeypatch):
    """The fundamentals source prices its ratios once a day; the public page (and so the screens) and the deep dive
    re-price them at the last close shown with them, as the company page does."""
    from app import main
    from app.intel.screener import summary
    co = {"sym": "RELIANCE", "bse": None}
    f = main.stock_page_facts("IN", co)
    page = main.research_hub.screener.company("RELIANCE")
    s = summary(page)
    assert f["price"] and f["price"] != s["price"]
    assert f["market_cap"] == pytest.approx(s["market_cap_cr"] * f["price"] / s["price"])
    assert f["pe"] == pytest.approx(s["pe"] * f["price"] / s["price"])
    live = w["client"].get("/research/company/IN/RELIANCE", headers=H()).json()
    # the same market value at the same price: the public page is priced at the last close (R5V-005: a session still
    # trading is never its price), the company page at the live price it shows with its time, so set at one price the
    # two agree exactly (the same shares, the same re-pricing)
    assert live["market_cap"] / 1e7 * f["price"] / live["quote"]["price"] == pytest.approx(f["market_cap"], rel=1e-6)


def test_replay_reads_enough_history_for_its_context_across_holidays():
    """The context before a replay's start is counted in sessions: the calendar days read allow for the exchange's
    holidays, so a start after a holiday-heavy stretch still has its 200 daily candles before it."""
    from datetime import date, timedelta
    from app import replay as R
    from app.data.calendar import is_trading_day
    today = date(2026, 10, 8)
    for start in (date(2025, 11, 20), date(2026, 3, 5), date(2026, 9, 1)):
        back = R.days_back("1d", start, today)
        first = today - timedelta(days=back)
        sessions = sum(is_trading_day("IN", first + timedelta(days=d)) for d in range((start - first).days))
        assert sessions >= R.CONTEXT["1d"], (start, sessions)
