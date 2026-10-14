"""Round 20: the owner on Chrome, live."""
from datetime import datetime, timezone

from app import deck
from app.intel.news import plain_headline
from tests.test_investor import view_for_deck


def test_the_deck_footer_is_dated_in_ist_like_the_page():
    # 21:38 UTC on 14 Oct is 03:08 IST on 15 Oct: the page said 15 Oct, the footer 14 Oct (R20-016)
    _, footer = deck.plan(view_for_deck(), now=datetime(2026, 10, 14, 21, 38, tzinfo=timezone.utc))
    assert footer.endswith("· Deep dive · 15 Oct 2026")
    _, footer = deck.plan(view_for_deck(), now=datetime(2026, 10, 14, 10, 0, tzinfo=timezone.utc))
    assert footer.endswith("· 14 Oct 2026")


def test_headlines_that_tell_the_reader_to_buy_or_sell_are_not_shown():
    for t in ("Jim Cramer says this healthcare stock is still a buy. Plus, what to do with BNY",
              "Why this chipmaker is still a sell", "Analyst says the stock is a strong buy", "It's time to sell Tesla",
              "Time to buy: Apple dips", "Buy now before earnings", "Our top pick for 2027", "The stock is a buy at these levels"):
        assert not plain_headline(t), t
    for t in ("Wall Street stocks close higher as inflation cools", "Fed ends its bond buy-back programme", "Tech sell-off deepens, Nasdaq falls 2%",
              "Berkshire sells its stake in Apple", "Disney to buy rival for $5 billion", "Stocks rise as buy orders surge", "Sell in May is a market saying"):
        assert plain_headline(t), t
