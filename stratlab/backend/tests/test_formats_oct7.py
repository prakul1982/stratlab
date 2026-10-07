"""Amounts that round up to the next unit are written in it."""
from app import deepdive


def test_a_figure_that_rounds_up_to_the_next_unit_is_written_in_it():
    assert deepdive.money(99999.7, "₹ crore") == "₹1.00 lakh cr"            # not ₹100,000 cr
    assert deepdive.money(999.6, "$ million") == "$1.00 bn"                  # not $1,000 m
    assert deepdive.money(-999.6, "$ million") == "-$1.00 bn"


def test_figures_that_do_not_round_up_keep_their_unit():
    assert deepdive.money(99999.4, "₹ crore") == "₹99,999 cr"
    assert deepdive.money(100000, "₹ crore") == "₹1.00 lakh cr"
    assert deepdive.money(999.4, "$ million") == "$999 m"
    assert deepdive.money(950, "$ million") == "$950 m"
    assert deepdive.money(1234, "₹ crore") == "₹1,234 cr"
