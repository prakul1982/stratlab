"""Release 42 live decks: a figure printed as a multiple uses the real minus, and one that rounds to zero has no sign (the live
Defence deck's balance-sheet tiles printed "Range -0.00x to 2.64x": a company's debt to equity a hair below zero, through a
formatter of its own with a hyphen)."""
from app import deck


def test_a_multiple_uses_the_real_minus_and_a_zero_has_no_sign():
    assert deck._times(-0.001, 2) == "0.00x"
    assert deck._times(0.004, 2) == "0.00x"
    assert deck._times(-18.44, 2) == "−18.44x"
    assert deck._times(2.64, 2) == "2.64x"
    assert deck._times(-0.36) == "−0.4x"
    assert deck._times(None) == "–"


def test_the_debt_to_equity_range_never_prints_a_hyphen_minus():
    st = {"min": -0.001, "max": 2.64, "median": 0.4}
    text = deck._span(st, lambda x: deck._times(x, 2))
    assert text == "0.00x to 2.64x"
    assert "-" not in text
    src = open(deck.__file__).read()
    assert 'lambda x: f"{x:.2f}x"' not in src                  # the balance-sheet tile goes through _times
