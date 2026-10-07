"""Finding a company by what people call it (F3-004, F3-005, R1-048): its name ("HDFC Bank", "Infosys", "Apollo
Hospitals"), a short name ("RIL", "Infy", "Tata Motors", "Apple"), its ISIN, or with a typo, the right company first
in every company box: the instrument search (notebook market picker, Ctrl K), the research search and the
suggestions."""
import time
from urllib.parse import quote

import pytest

from app import main, name_search
from app.name_search import CLOSE, EXACT, NAME, NAMED, SYMBOL, WORDS, NameIndex, tokens
from tests import world

PRO = world.headers("pro-token")

# how the broker writes names (short, upper case, cut off), with the exchange's full names beside some
BROKER = [("HDFCBANK", "HDFC BANK"), ("HDFCLIFE", "HDFC LIFE INS CO LTD"), ("HDFCAMC", "HDFC AMC"), ("INFY", "INFOSYS"),
          ("APOLLOHOSP", "APOLLO HOSPITALS ENTER. L"), ("APOLLOTYRE", "APOLLO TYRES"), ("APLAPOLLO", "APL APOLLO TUBES"),
          ("RELIANCE", "RELIANCE INDUSTRIES"), ("TMPV", "TATA MOTORS PASS VEH LTD"), ("TATASTEEL", "TATA STEEL"),
          ("TCS", "TATA CONSULTANCY SERV LT"), ("LT", "LARSEN & TOUBRO"), ("BAJAJ-AUTO", "BAJAJ AUTO"),
          ("DRREDDY", "DR. REDDY S LABORATORIES"), ("SBIN", "STATE BANK OF INDIA"), ("HINDUNILVR", "HINDUSTAN UNILEVER")]
ISINS = {"HDFCBANK": "INE040A01034", "INFY": "INE009A01021"}


def _index():
    rows = [{"symbol": s, "name": n, "isin": ISINS.get(s)} for s, n in BROKER]
    return NameIndex(rows, codes=lambda r: [r["isin"]], aliases=name_search.ALIASES["IN"])


def _top(idx, q, n=1):
    return [(r["symbol"], t) for t, r in idx.search(q, 10)][:n]


# ---------- the ranking ----------
def test_names_people_type_find_the_company_first():
    idx = _index()
    assert _top(idx, "hdfc bank") == [("HDFCBANK", EXACT)]           # the symbol written as words
    assert _top(idx, "HDFC Bank Ltd") == [("HDFCBANK", NAMED)]       # the legal form doesn't matter
    assert _top(idx, "infosys") == [("INFY", NAMED)]
    assert _top(idx, "Infosys Limited") == [("INFY", NAMED)]
    assert _top(idx, "apollo hospitals") == [("APOLLOHOSP", NAME)]   # the broker's name is cut short: still found
    assert _top(idx, "Apollo Hospitals Enterprise Ltd") == [("APOLLOHOSP", WORDS)]   # its "ENTER." is "Enterprise"
    assert _top(idx, "state bank of india") == [("SBIN", NAMED)]
    assert _top(idx, "bajaj auto") == [("BAJAJ-AUTO", EXACT)]
    assert _top(idx, "dr reddys") == [("DRREDDY", NAMED)] and _top(idx, "reddy") == [("DRREDDY", WORDS)]


def test_short_names_and_symbols():
    idx = _index()
    assert _top(idx, "infy") == [("INFY", EXACT)]
    assert _top(idx, "RIL") == [("RELIANCE", NAMED)]
    assert _top(idx, "tata motors") == [("TMPV", NAMED)]               # the 2025 demerger kept the listing as TMPV
    assert _top(idx, "l&t") == [("LT", NAMED)] and _top(idx, "hul") == [("HINDUNILVR", NAMED)]
    # a short name before symbols starting with it, symbols starting with it shorter first
    assert _top(idx, "hdfc", 3) == [("HDFCBANK", NAMED), ("HDFCAMC", SYMBOL), ("HDFCLIFE", SYMBOL)]


def test_order_symbol_then_name_then_words():
    idx = _index()
    got = _top(idx, "apollo", 5)
    # symbols starting with it, then names starting with it, then a later word starting with it
    assert got == [("APOLLOHOSP", SYMBOL), ("APOLLOTYRE", SYMBOL), ("APLAPOLLO", WORDS)]
    assert _top(idx, "hospitals apollo") == [("APOLLOHOSP", WORDS)]  # words in any order
    assert _top(idx, "tata cons") == [("TCS", NAME)]


def test_isin_finds_only_its_company():
    idx = _index()
    assert _top(idx, "INE009A01021", 5) == [("INFY", EXACT)]
    assert _top(idx, " ine040a01034 ", 5) == [("HDFCBANK", EXACT)]
    assert idx.search("INE999Z01011") == []                           # an ISIN nobody has: nothing, not a guess


def test_one_typo_is_forgiven():
    idx = _index()
    assert _top(idx, "infosis") == [("INFY", CLOSE)]
    assert _top(idx, "relaince") == [("RELIANCE", CLOSE)]
    assert _top(idx, "Apolo hospitals") == [("APOLLOHOSP", CLOSE)]
    assert _top(idx, "hdfc bnak") == [("HDFCBANK", CLOSE)]            # two letters swapped
    assert idx.search("xyzzy") == [] and idx.search("") == []
    # short words aren't guessed at: "tcs" is a symbol, "tvs" isn't a typo of it
    assert _top(idx, "tvs") == []


def test_names_lose_their_legal_form_and_punctuation():
    assert tokens("Amazon.com, Inc.") == ["amazon", "com"]
    assert tokens("Dr. Reddy's Laboratories Ltd") == ["dr", "reddys", "laboratories"]
    assert tokens("The Walt Disney Company") == ["walt", "disney"]
    assert tokens("APOLLO HOSPITALS ENTER. L") == ["apollo", "hospitals", "enter"]
    assert tokens("Larsen & Toubro Limited") == ["larsen", "toubro"] and tokens("L&T") == ["l&t"]


def test_a_keystroke_stays_fast_on_a_full_list():
    rows = [{"symbol": f"S{i}", "name": f"Company{i % 997} Word{i % 113} Thing{i}"} for i in range(12000)]
    t = time.time()
    idx = NameIndex(rows)
    built = time.time() - t
    t = time.time()
    for q in ("company5", "word1 thing", "compani51", "s11", "thing 99", "c"):
        idx.search(q, 25)
    assert built < 3 and (time.time() - t) / 6 < 0.05


def test_rows_from_elsewhere_are_ranked_the_same_way():
    assert name_search.tier_of("apple", "AAPL", "Apple Inc.") == NAMED
    assert name_search.tier_of("apple", "APLE", "Apple Hospitality REIT Inc") == NAME
    assert name_search.tier_of("apple", "NVDA", "NVIDIA Corp") == name_search.NOT_FOUND
    assert name_search.tier_of("google", "GOOGL", "Alphabet Inc", "US") == NAMED


# ---------- every company box, on the demo world ----------
@pytest.fixture
def w(monkeypatch):
    built = world.build(monkeypatch)
    main.suggester.clear()
    yield built
    main.suggester.clear()
    built["close"]()


def _inst(c, q, market="IN"):
    return c.get(f"/instruments/search?q={quote(q)}" + (f"&market={market}" if market else ""), headers=PRO).json()


def test_instrument_search_by_name(w):
    """The notebook market picker and the Ctrl K box."""
    c = w["client"]
    for q, sym in (("hdfc bank", "HDFCBANK"), ("HDFC Bank", "HDFCBANK"), ("infosys", "INFY"), ("Infy", "INFY"),
                   ("apollo hospitals", "APOLLOHOSP"), ("Apollo Hospitals", "APOLLOHOSP"), ("RIL", "RELIANCE"),
                   ("Tata Motors", "TMPV"), ("relaince", "RELIANCE"), ("Infosis", "INFY"), ("nifty", "NIFTY 50")):
        got = _inst(c, q)
        assert got and got[0]["symbol"] == sym, (q, [r["symbol"] for r in got[:3]])
    hdfc = _inst(c, "hdfc bank")[0]
    assert hdfc["name"] == "HDFC Bank" and hdfc["type"] == "EQ" and hdfc["match"] == EXACT


def test_isin_and_full_names_from_the_exchange_list(w):
    c = w["client"]
    main.isin_list()                            # the morning warm-up reads the exchange's list of companies
    got = _inst(c, "INE009A01021")
    assert got[0]["symbol"] == "INFY" and got[0]["name"] == "Infosys Limited"
    assert _inst(c, "Tata Consultancy Services Limited")[0]["symbol"] == "TCS"


def test_every_market_puts_the_named_company_first(w):
    """Ctrl K asks every market at once: the company named comes first wherever it trades."""
    c = w["client"]
    assert _inst(c, "infosys", None)[0]["symbol"] == "INFY"
    assert _inst(c, "hdfc bank", None)[0]["symbol"] == "HDFCBANK"
    apple = _inst(c, "apple", None)[0]
    assert (apple["symbol"], apple["market"]) == ("AAPL", "US")


def test_research_search_by_name(w):
    """The Invest home's company box: its own placeholder ("Apollo Hospitals") finds the company."""
    c = w["client"]
    for q, region, sym in (("Apollo Hospitals", "IN", "APOLLOHOSP"), ("HDFC Bank", "IN", "HDFCBANK"),
                           ("Infosys", "IN", "INFY"), ("Tata Motors", "IN", "TMPV"), ("Apple", "US", "AAPL"),
                           ("berkshire", "US", "BRK-B")):
        got = c.get(f"/research/search?q={quote(q)}&region={region}", headers=PRO).json()
        assert got and got[0]["symbol"] == sym, (q, got[:3])
    assert c.get("/research/search?q=Apollo%20Hospitals&region=IN", headers=PRO).json()[0]["name"] == "Apollo Hospitals Enterprise"


def test_suggestions_by_name(w):
    c = w["client"]
    for q, sym in (("hdfc bank", "HDFCBANK"), ("infosys", "INFY"), ("apollo hosp", "APOLLOHOSP"), ("apple", "AAPL")):
        rows = c.get(f"/suggest/companies?q={quote(q)}", headers=PRO).json()["rows"]
        assert rows and rows[0]["symbol"] == sym, (q, rows[:3])
