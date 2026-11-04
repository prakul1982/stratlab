"""LIVE3 (live review of production, 4 Nov), the FIXB lane's backend checks."""
from app import platform_check as P


def test_a_candle_check_ignores_float_noise_and_shows_enough_decimals_to_tell():
    """LIVE3-008: "Check every feature" failed two days on a EUR/USD candle shown as o 1.12 h 1.12 l 1.12 c 1.12: float noise is not a
    fault, and a real fault in a currency pair is printed to four places so it can be seen which side is out."""
    flat = {"o": 1.12, "h": 1.12, "l": 1.12, "c": 1.12}
    assert P.candle_sane(flat)
    assert P.candle_sane({"o": 1.1200000000000003, "h": 1.12, "l": 1.12, "c": 1.12})          # one float step above its high
    assert not P.candle_sane({"o": 1.12051, "h": 1.12034, "l": 1.11902, "c": 1.12010})        # a real fault: the open above the high
    assert not P.candle_sane({"o": 100.0, "h": 101.0, "l": 0.0, "c": 100.5})
    assert P._px(1.12051) == "1.1205" and P._px(24123.456) == "24,123.46"
