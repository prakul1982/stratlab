"""Round 67 (19 Oct 2026): India's close before the Tue 20 Oct holiday — the backend side, each on the reviewer's own example."""
from datetime import date

from app import main  # noqa: F401  (loads the app's modules in their order)
from app import alerts, market_events as M
from app.newsletter import content, write


def test_the_calendar_keeps_todays_moved_expiry_after_the_close():
    # R67-002: after 15:30 the exchange's list drops today's contract, and the NIFTY weekly on Mon 19 Oct went missing
    listed = lambda ex, name: ["2026-10-27", "2026-11-03"] if ex == "NFO" else ["2026-10-22", "2026-10-29"]  # noqa: E731
    evs = M.expiry_events(date(2026, 10, 19), listed, date(2026, 10, 1), date(2026, 10, 31))
    nifty = [e for e in evs if e["title"] == "NIFTY weekly expiry"]
    assert [e["date"] for e in nifty] == ["2026-10-06", "2026-10-13", "2026-10-19"]
    # Tuesday's rule date isn't put back beside it: that week's expiry moved to the Monday
    assert "2026-10-20" not in {e["date"] for e in evs}
    assert "Tuesday 20 Oct is a market holiday" in nifty[-1]["detail"]


def test_past_and_listed_puts_back_past_rule_days_and_today_once_it_left_the_list():
    rule = M._rule_weekly(date(2026, 10, 10), date(2026, 10, 31), 1)            # the holiday moves 20 Oct to Mon 19 Oct
    assert rule == [date(2026, 10, 13), date(2026, 10, 19), date(2026, 10, 27)]
    # during the day the list still has today's contract; after the close only the rule has it
    assert M._past_and_listed(rule, ["2026-10-19", "2026-10-27"], date(2026, 10, 19)) == set(rule)
    assert M._past_and_listed(rule, ["2026-10-27"], date(2026, 10, 19)) == set(rule)
    # a future rule day is the list's to give: a week whose contract the list doesn't have stays empty
    assert M._past_and_listed(rule, ["2026-11-03"], date(2026, 10, 19)) == {date(2026, 10, 13), date(2026, 10, 19), date(2026, 11, 3)}
    assert M._past_and_listed(rule, [], date(2026, 10, 19)) == set(rule)       # no list: the rule alone


def test_the_last_brief_before_a_holiday_says_the_market_is_shut():
    # R67-001: Monday's India brief said nothing of Tuesday's holiday
    shut = content.closures_after("IN", date(2026, 10, 19))
    assert shut[0]["day"] == "2026-10-20" and shut[-1] == {"next_open": "2026-10-21"}
    assert content.closures_after("IN", date(2026, 10, 15)) == []              # Friday follows: nothing to say
    f = {"kind": "market", "region": "IN", "weekly": False, "day": "2026-10-19", "closures": shut}
    sec = next(s for s in write.market_sections(f) if s["title"] == "Market holiday")
    assert sec["items"][0]["text"].startswith("The India market is closed on Tue 20 Oct")
    assert sec["items"][0]["text"].endswith("The next session is Wed 21 Oct.")
    # a named holiday carries its name (US Thanksgiving)
    us = content.closures_after("US", date(2026, 11, 25))
    text = write.market_sections({**f, "region": "US", "closures": us})[-1]["items"][0]["text"]
    assert "Thu 26 Nov (Thanksgiving)" in text and "Fri 27 Nov" in text


def test_the_unsubscribe_link_and_its_page_use_the_same_words():
    # R67-009: "Unsubscribe from India briefs" in the email opened "Unsubscribe from the India market email?"
    assert alerts.NEWSLETTER_NAMES["market_in"] == "the India market brief"
    assert alerts.NEWSLETTER_NAMES["market_us"] == "the US market brief"
