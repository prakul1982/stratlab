"""Round 49: headlines by today's rules on stored briefs, an India brief's headlines that can be opened, no alarm for the
morning's broker reset, one buy-and-hold figure signed in and out, and a fall without a second minus."""
from datetime import datetime

from app import main  # noqa: F401, I001  (first: the app loads the newsletters' routes)
from app import library
from app.intel.grounding import tidy_numbers
from app.intel.news import plain_headline
from app.kite_service import IST
from app.newsletter import job, write


def test_round_49_listicles_and_picks_between_stocks_are_left_out():
    for t in ("Sensex jumps over 1,500 points: 5 reasons why the stock market is rising today",
              "Three Reasons Why Markets Are Rising Today", "BYD or Tesla: Which Is a Better Stock?",
              "Why Are TCS, Infosys & Other IT Stocks Rising Today? Key Reasons Behind IT Rally"):
        assert not plain_headline(t), t
    for t in ("Reasons for the rupee fall: RBI data", "Tesla: Musk Proves He Can Deliver (Earnings Preview)"):
        assert plain_headline(t), t


def test_a_stored_brief_shows_its_headlines_by_todays_rules(monkeypatch):
    issue = {"id": "market.US.2026-10-16", "sections": [
        {"title": "Indices", "items": [{"text": "S&P 500 −1.09%"}]},
        {"title": "Headlines", "items": [{"text": "Wall Street's fear gauge is ripping. Traders see it going even higher"},
                                         {"text": "Stocks fall as yields climb"}]}]}
    monkeypatch.setattr(job.db, "get_setting", lambda k: __import__("json").dumps(issue))
    got = job.load("market.US.2026-10-16")
    heads = next(s for s in got["sections"] if s["title"] == "Headlines")["items"]
    assert [h["text"] for h in heads] == ["Stocks fall as yields climb"]
    assert got["sections"][0]["title"] == "Indices"


def test_an_india_headline_with_only_an_aggregator_link_opens_the_brief():
    issue = {"id": "market.IN.2026-10-16", "subject": "Market Brief India", "summary": "", "sections": [
        {"title": "Headlines", "items": [{"text": "Sensex, Nifty close higher", "url": "https://news.google.com/rss/articles/CBMiXYZ"}]}]}
    html, text = write.render(issue)
    assert "news.google.com" not in html
    assert "/news?tab=IN&amp;issue=market.IN.2026-10-16" in html and html.count("issue=market.IN.2026-10-16") >= 2


def test_the_morning_reset_before_the_automatic_login_sends_no_alert(monkeypatch):
    sent = []
    monkeypatch.setattr(main.auto_login, "alert_once", lambda k, m: sent.append(m))
    due = datetime.now(IST).replace(hour=23, minute=59)
    monkeypatch.setattr(main.auto_login, "next_login", lambda now: due)
    main._kite_cancelled("Zerodha cancelled today's Kite token")
    assert sent == [] and "nothing to do" in main.kite.invalid_reason and "23:59 IST" in main.kite.invalid_reason
    monkeypatch.setattr(main.auto_login, "next_login", lambda now: None)     # today's login has run: worth an email
    main._kite_cancelled("Zerodha cancelled today's Kite token")
    assert sent == ["StratLab: Zerodha cancelled today's Kite token"]
    main.kite.invalid_reason = None


def test_stratlabs_own_entry_sets_the_buy_and_hold_figure_signed_in_too():
    rng = {"from": "2021-10-18T00:00:00", "to": "2026-10-14T00:00:00"}
    base = {"group": {"id": "nifty50"}, "tf": "1d", "range": rng}
    mine = {**base, "id": "a-reader", "stats": {"buy_hold": 67.94}}
    seed = {**base, "id": "seed-st-in", "official": True, "stats": {"buy_hold": 67.96}}
    assert {e["id"]: e["stats"]["buy_hold"] for e in library.same_hold([mine, seed])} == {"a-reader": 67.96, "seed-st-in": 67.96}
    assert library.same_hold([seed])[0]["stats"]["buy_hold"] == 67.96


def test_a_fall_is_written_without_a_second_minus():
    assert tidy_numbers("The stock has fallen -17.0% in a year") == "The stock has fallen 17.0% in a year"
    assert tidy_numbers("It rose 3% and fell 2%") == "It rose 3% and fell 2%"
