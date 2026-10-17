"""Round 47: headlines, the company profile text and the AI read's "what to watch"."""
from app.intel.ai import PAST_WATCH
from app.intel.news import plain_headline
from app.intel.screener import clean_profile
from app.newsletter.content import OFF_TOPIC


def test_advice_worded_and_clickbait_headlines_are_left_out():
    for t in ("We're downgrading this retail stock after a big comeback",
              "Apple's New Home Collection Gives Investors Another Reason to Remain Bullish",
              "$10,000 Invested in Apple Could Be Worth This Much by 2031",
              "Reliance shares rise; can Jio Platforms IPO aid the bounce back? Experts' views"):
        assert not plain_headline(t), t
    for t in ("'Everyone laughed' when he started a pumpkin farm—now it brings in $2 million a year",
              "Trump mocks popularity of the name Mohammad"):
        assert OFF_TOPIC.search(t), t
    for t in ("Reliance Q2 profit rises 9% on retail, Jio", "Apple shares fall after iPhone sales miss",
              "Analyst downgrades Nike on weak China sales", "Fed holds rates steady"):
        assert plain_headline(t) and not OFF_TOPIC.search(t), t


def test_a_heading_pasted_after_a_full_stop_is_taken_out_of_the_profile():
    assert clean_profile("Ambani holds about 50% in the conglomerate. Architecture Reliance Industries Limited holds stakes.") == \
        "Ambani holds about 50% in the conglomerate. Reliance Industries Limited holds stakes."
    assert clean_profile("The Architecture Firm Ltd designs homes.") == "The Architecture Firm Ltd designs homes."


def test_results_already_out_are_not_something_to_watch():
    assert PAST_WATCH.search("Jun 2026 (Q1 FY2027) results filed on 2026-06")
    assert PAST_WATCH.search("Sep quarter results were reported on 17 Oct")
    for t in ("The next results date isn't announced yet", "Results on 2026-11-02 for the Sep 2026 quarter",
              "Board meeting on 2026-10-24 to consider results"):
        assert not PAST_WATCH.search(t), t
