"""Round 72 (19 Oct 2026): the US close and the US brief — the backend side, on the reviewer's own example."""
from app.newsletter import write


def test_a_stock_picking_services_stance_is_never_in_a_brief():
    # R72-002: "A CNBC article highlighted … a doctor survey that kept sentiment positive on Lilly"
    assert write.banned("Crushed tech stocks bounce — plus, new doctor survey keeps us positive on Lilly")
    assert write.banned("CNBC Investing Club: why we're cautious on Nvidia")
    assert not write.banned("Wall Street keeps US stocks near highs")        # "US" the country is not "us"
    assert not write.banned("S&P 500 rose 0.41% to 7,690.73")
