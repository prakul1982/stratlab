"""Round 77 (21 Oct 2026): India after the close and its brief, the first trading day after the 20 Oct holiday."""
from app import breadth
from app.newsletter import content


def test_a_finished_run_with_one_unread_stock_is_not_a_failed_update():
    # R77-002: at 16:30 IST on 21 Oct (the run is at 18:30) the page said "the 21 Oct update didn't finish", from the
    # 19 Oct run's last unread stock kept in last_error
    pending = {"day": "2026-10-21", "due": None}
    done = {"IN": {"as_of": "2026-10-19", "ran_at": "2026-10-19T13:05:00+00:00", "last_error": "XYZ: no data"}}
    assert not breadth.update_failed("IN", pending, done)
    # an old failure, before the due day, doesn't count either
    old = {"IN": {**done["IN"], "failed_at": "2026-10-16T13:01:00+00:00"}}
    assert not breadth.update_failed("IN", pending, old)
    # the due day's own run failed: it does
    failed = {"IN": {**done["IN"], "failed_at": "2026-10-21T13:02:00+00:00"}}
    assert breadth.update_failed("IN", pending, failed)
    # a run that finished after that failure: the day is in or still due, not failed
    later = {"IN": {**failed["IN"], "ran_at": "2026-10-21T13:40:00+00:00"}}
    assert not breadth.update_failed("IN", pending, later)


def test_a_preview_written_before_the_open_is_not_in_the_evening_brief():
    # R77-004
    for t in ("Stock Market Today: Gift Nifty, Jio IPO To Oil Prices; Five Key Factors That May Drive Sensex, Nifty 50 On October 21",
              "Stocks to watch: Reliance, TCS, HDFC Bank", "Trade setup for Thursday: Nifty support levels",
              "Gift Nifty indicates a flat start for Sensex"):
        assert content.early_story(t), t
    for t in ("Sensex, Nifty gives up gains to close lower", "Nifty ends 0.3% lower as banks drag", "Sensex falls 143 points"):
        assert not content.early_story(t), t
