"""Round-trip charges and breakevens after costs for an options structure, checked against numbers worked by hand."""
from pytest import approx

from app.options import charges

# a NIFTY short straddle, one lot of 65 at 22,400: call sold at 150, put sold at 120
STRADDLE = [{"side": "sell", "opt": "CE", "strike": 22400, "fill": 150.0, "qty": 65},
            {"side": "sell", "opt": "PE", "strike": 22400, "fill": 120.0, "qty": 65}]


def test_short_straddle_charges_line_by_line():
    # call: 65 x 150 = 9,750 of premium each way; put: 65 x 120 = 7,800
    rt = charges.round_trip(STRADDLE, "in_opt", 20, 1800)
    it = rt["items"]
    assert rt["orders"] == 4                                        # open and close, two legs, one slice each
    assert it["brokerage"] == approx(80)                            # 4 orders x ₹20
    assert it["stt"] == approx(14.625 + 11.70)                      # 0.15% on the two sells only
    assert it["exchange"] == approx(2 * 3.425175 + 2 * 2.740140)    # 0.03513% both ways
    assert it["sebi"] == approx(2 * 0.00975 + 2 * 0.0078)           # ₹10 a crore both ways
    assert it["stamp"] == approx(0.2925 + 0.234)                    # 0.003% on the two buys only
    # 18% GST on brokerage + exchange + SEBI fee, per order
    assert it["gst"] == approx(2 * 0.18 * (20 + 3.434925) + 2 * 0.18 * (20 + 2.74794))
    assert rt["total"] == approx(135.843061)


def test_short_straddle_breakevens_and_shares():
    s = charges.summary(STRADDLE, "in_opt", 20, 1800)
    assert s["total"] == 135.84 and s["credit"] and s["premium"] == 17550
    assert s["premium_after"] == approx(17550 - 135.84, abs=0.01)
    assert s["max_profit"] == 17550 and s["max_profit_after"] == approx(17414.16, abs=0.01)
    assert s["pct_of_max_profit"] == 0.77 and s["pct_of_premium"] == 0.77   # 135.84 / 17,550
    assert s["breakevens"] == [22130, 22670]                                 # 22,400 ± 270
    # the payoff drops ₹135.84 everywhere: 135.843061 / 65 = 2.09 points nearer the strike on each side
    assert s["breakevens_after"] == [22132.09, 22667.91]
    assert [i["label"] for i in s["items"]] == ["Brokerage", "STT", "Exchange charges", "SEBI fee", "Stamp duty", "GST"]


def test_orders_above_the_freeze_limit_pay_brokerage_per_slice():
    big = [{**STRADDLE[0], "qty": 65 * 30}]                                  # 1,950 units, freeze 1,800: two slices
    rt = charges.round_trip(big, "in_opt", 20, 1800)
    assert rt["orders"] == 4 and rt["items"]["brokerage"] == approx(80)
    assert charges.round_trip(big, "in_opt", 20, 0)["orders"] == 2         # no freeze limit: one order each way


def test_long_call_has_no_ceiling_and_breaks_even_higher_after_costs():
    leg = [{"side": "buy", "opt": "CE", "strike": 22500, "fill": 100.0, "qty": 65}]
    s = charges.summary(leg, "in_opt", 20, 1800)
    # value 6,500: brokerage 40, STT 9.75 on the close, exchange 4.5669, SEBI 0.013, stamp 0.195,
    # GST 0.18 x (40 + 4.5669 + 0.013) = 8.024382
    assert s["total"] == approx(62.55, abs=0.01) and not s["credit"] and s["premium_after"] is None
    assert s["max_profit"] is None and s["pct_of_max_profit"] is None
    assert s["pct_of_premium"] == approx(0.96, abs=0.01)                    # 62.55 / 6,500
    assert s["breakevens"] == [22600]
    assert s["breakevens_after"] == [approx(22600 + 62.549282 / 65, abs=0.01)]


def test_a_spread_whose_costs_eat_the_profit_never_breaks_even():
    # bull call spread 100 points wide, paid 99.5 net: at most ₹0.5 x 65 = ₹32.50 before costs
    legs = [{"side": "buy", "opt": "CE", "strike": 22400, "fill": 150.0, "qty": 65},
            {"side": "sell", "opt": "CE", "strike": 22500, "fill": 50.5, "qty": 65}]
    s = charges.summary(legs, "in_opt", 20, 1800)
    assert s["max_profit"] == approx(32.5) and s["breakevens"] == [22499.5]
    assert s["breakevens_after"] == [] and s["max_profit_after"] < 0 and s["pct_of_max_profit"] > 100


def test_put_side_payoff_is_bounded_at_zero():
    leg = [{"side": "buy", "opt": "PE", "strike": 22400, "fill": 120.0, "qty": 65}]
    s = charges.summary(leg, "in_opt", 0, 0)
    assert s["max_profit"] == approx((22400 - 120) * 65) and s["breakevens"] == [22280]


def test_commodity_options_are_labelled_ctt_and_currency_options_pay_none():
    mcx = charges.summary([{**STRADDLE[0], "qty": 100}], "in_mcx_opt", 20, 0)
    assert "CTT" in [i["label"] for i in mcx["items"]]
    cds = charges.summary([{**STRADDLE[0], "qty": 1000, "fill": 0.25}], "in_cds_opt", 20, 0)
    assert not any(i["key"] == "stt" for i in cds["items"])
    assert charges.kind_for("BFO") == "in_bse_opt" and charges.kind_for("NFO") == "in_opt"
