"""Round 64 (19 Oct 2026): the owner's money pages — the backend side, on the reviewer's own example."""
from app import main  # noqa: F401  (loads the app's modules in their order)
from app.intel import grounding as G


def test_a_share_of_holders_moves_in_percentage_points():
    # R64-009: "Share of FIIs fell by 2.41% to 9.07%" beside "9.1% −2.4 pts" in the Who owns it card
    assert G.holding_points("Share of FIIs fell by 2.41% to 9.07%.") == "Share of FIIs fell by 2.41 percentage points to 9.07%."
    assert G.holding_points("FIIs' share rose by 1.2% this quarter.") == "FIIs' share rose by 1.2 percentage points this quarter."
    # a share's price is not a holding
    for t in ("The share fell by 2% today.", "The share price rose by 3% in a week.", "Its share of profit fell by 4%."):
        assert G.holding_points(t) == t
