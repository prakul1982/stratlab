"""16 Oct 2026 live review: NIFTY 22,938, 3.25 days, 5.5%. The wing theta/vega and the forward were checked against
Black-76 with each leg's own implied volatility."""
import math

from app.options import greeks as g

SPOT, T, R = 22938.0, 3.25 / 365, 0.055
LEGS = [(23750, "CE", 2.40), (22150, "PE", 5.10), (22950, "CE", 131.25), (22950, "PE", 103.25)]


def test_forward_from_parity_is_above_spot():
    f = g.parity_forward(22950, 131.25, 103.25, T, R)
    assert f == 22950 + math.exp(R * T) * 28
    assert abs(f - SPOT * math.exp(R * T)) < 50          # the 22,978 these prices give; a few points of carry + skew
    assert f > SPOT


def test_wing_uses_its_own_iv_and_reprices_to_its_premium():
    f = g.parity_forward(22950, 131.25, 103.25, T, R)
    for k, kind, px in LEGS:
        iv = g.implied_vol(px, f, k, T, kind, R)
        assert iv and abs(g.greeks(f, k, T, iv, kind, R)["price"] - px) < 1e-6


def test_wing_theta_is_the_instantaneous_rate_and_matches_finite_difference():
    f = SPOT * math.exp(R * T)
    iv = g.implied_vol(2.40, f, 23750, T, "CE", R)
    x = g.greeks(f, 23750, T, iv, "CE", R)
    h = 1e-4
    fd = (g.black76(f, 23750, T, iv, "CE", R) - g.black76(f, 23750, T - h / 365, iv, "CE", R)) / h
    assert abs(-x["theta"] - fd) < 0.01
    assert 2.3 < -x["theta"] < 2.7 and 0.85 < x["vega"] < 1.05      # ≈ ₹2.5 a day, ₹0.94 a vol point per unit
    one_day = g.black76(f, 23750, T, iv, "CE", R) - g.black76(f, 23750, T - 1 / 365, iv, "CE", R)
    assert one_day < 2.40                                             # a whole day's decay is under the premium
    assert 2.4 / 3.25 < -x["theta"] < 2.4 * 1.5                      # convex decay: first-instant rate above the average
