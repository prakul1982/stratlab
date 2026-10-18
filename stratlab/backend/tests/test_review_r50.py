"""Round 50: ready-made index groups follow the index's announced changes, an AI read can't turn a rise between two
named years into a fall, negative percentages wear the minus sign, quote-page titles and screen lists aren't headlines,
and the official sources that keep failing are named on Overview."""
from datetime import date

from app import main  # noqa: F401, I001  (first: the app loads the newsletters' routes)
from app import market_events, rules_watch, universes
from app.intel.grounding import PageFacts, tidy_numbers
from app.intel.news import plain_headline

CHANGE = {"id": "c1", "announced": "2026-08-22", "effective": "2026-09-30", "sections": [
    {"index": "Nifty 50", "in": [["BSE", "BSE Ltd."]], "out": [["WIPRO", "Wipro Ltd."]]},
    {"index": "Nifty Next 50", "in": [["WIPRO", "Wipro Ltd."]], "out": [["BSE", "BSE Ltd."]]}]}


def test_the_nifty_50_group_takes_the_announced_change_once_it_is_effective(monkeypatch):
    monkeypatch.setattr(market_events, "index_changes", lambda today=None: [CHANGE])
    p = next(p for p in universes.PRESETS["IN"] if p["id"] == "nifty50")
    after = universes.current(p, date(2026, 10, 18))
    assert "BSE" in after["symbols"] and "WIPRO" not in after["symbols"] and len(after["symbols"]) == 50
    assert after["as_of"] == "30 Sep 2026"
    assert universes.current(p, date(2026, 9, 29))["symbols"] == p["symbols"]        # not before it takes effect
    assert "the list as of 30 Sep 2026" in universes.members_note({"market": "IN", "id": "nifty50"})
    us = next(p for p in universes.PRESETS["US"] if p["id"] == "us_mega")
    assert universes.current(us) is us                                               # a list that follows no index


def test_the_groups_stay_as_written_when_no_change_is_stored(monkeypatch):
    def boom(today=None):
        raise RuntimeError("no database")
    monkeypatch.setattr(market_events, "index_changes", boom)
    assert universes.symbols("IN", "nifty50") == next(p for p in universes.PRESETS["IN"] if p["id"] == "nifty50")["symbols"]


def test_a_rise_between_two_named_years_is_never_told_as_a_fall():
    f = {"symbol": "AAPL", "annual_trend": {"unit": "B", "profit": [{"y": "FY22", "v": 99.8}, {"y": "FY24", "v": 93.74}, {"y": "FY25", "v": 112.01}]}}
    page = PageFacts(f, "US", date(2026, 10, 18))
    assert not page.check("Net income fell from FY24 to FY25.")
    assert page.check("Net income rose from FY24 to FY25.") and page.check("Net income fell from FY22 to FY24.")


def test_negative_percentages_wear_the_minus_sign():
    assert tidy_numbers("1-year price change -17.0%, margins 20-30%") == "1-year price change −17.0%, margins 20-30%"


def test_quote_pages_and_screen_lists_are_not_headlines():
    for t in ("Tata Consultancy Services (TCS) Share Price Today & Chart", "TCS among 5 stocks showing RSI trending up",
              "Share Market Live, Share Market Today: Latest Share Market News on The Economic Times"):
        assert not plain_headline(t), t
    assert plain_headline("Sensex falls 400 points as IT drags")


def test_sources_unread_for_days_are_named_for_overview(monkeypatch):
    monkeypatch.setattr(rules_watch, "state", lambda: {"sources": [
        {"name": "PPF rate", "fails": 16, "error": "SSL", "pending": None},
        {"name": "SEC fee rate", "fails": 1, "error": "x", "pending": None},
        {"name": "NSE circulars", "fails": 0, "error": None, "pending": {"why": "new circular"}}]})
    got = main.rules_watch_summary()
    assert [x["name"] for x in got["failing"]] == ["PPF rate"] and got["pending"] == ["NSE circulars"]
