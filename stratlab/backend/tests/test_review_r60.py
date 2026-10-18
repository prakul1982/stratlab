"""Round 60 (19 Oct 2026): money data, payments, the visitor on desktop and Admin — the backend side."""
from app.engine import verdict as V


def test_a_stored_headline_reads_in_todays_words():
    # R60-001: a run saved before R59 kept "…behind buy and hold after costs; lost money after costs."
    old = {"verdict": "no_edge", "headline": "5.3 points behind buy and hold after costs; lost money after costs.", "checks": []}
    assert V.restated(old, {"n": 40, "ret": -10.8, "buy_hold_ret": -5.5})["headline"] == "5.3 points behind buy and hold; lost money after costs."
    # R60-002: and its count as the library and the checks line give it
    two = {"verdict": "edge", "headline": "4.0 points ahead of buy and hold after costs; passed 2 of the 3 checks run.", "checks": []}
    assert V.restated(two, {})["headline"] == "4.0 points ahead of buy and hold after costs; 3 of 4 checks run · 2 passed."
    fine = {"verdict": "edge", "headline": "20.0 points ahead of buy and hold after costs; 3 of 4 checks run · all 3 passed.", "checks": []}
    assert V.restated(fine, {}) == fine                      # already in today's words: as it is
