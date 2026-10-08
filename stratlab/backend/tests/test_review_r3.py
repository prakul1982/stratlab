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
