"""Round 62 (19 Oct 2026): the full owner pass on a laptop — the backend side, each on the reviewer's own example."""
from app import library_seed as S, main


def test_a_us_notebook_does_not_start_with_rupee_capital_and_brokerage():
    # R62-004: a new AAPL notebook opened with ₹5,00,000 of capital and a flat 20 brokerage, read as $20 a trade
    nb = {"instrument": {"symbol": "AAPL", "currency": "USD"}, "strategy": {"tf": "1d", "risk": {"capital": 500000, "brokerage": 20, "sl": 8}}}
    risk = main.risk_in_currency(nb)["strategy"]["risk"]
    assert (risk["capital"], risk["brokerage"], risk["sl"]) == (10000.0, 0.0, 8)


def test_numbers_someone_typed_and_rupee_notebooks_are_left_alone():
    typed = {"instrument": {"symbol": "AAPL", "currency": "USD"}, "strategy": {"risk": {"capital": 25000, "brokerage": 1}}}
    assert main.risk_in_currency(typed)["strategy"]["risk"] == {"capital": 25000, "brokerage": 1}
    india = {"instrument": {"symbol": "TCS", "currency": "INR"}, "strategy": {"risk": {"capital": 500000, "brokerage": 20}}}
    assert main.risk_in_currency(india)["strategy"]["risk"] == {"capital": 500000, "brokerage": 20}
    assert main.risk_in_currency({"strategy": {"risk": {"capital": 500000, "brokerage": 20}}})["strategy"]["risk"]["brokerage"] == 20


def test_the_library_s_us_strategies_charge_no_flat_rupee_brokerage():
    spec = next(s for s in S.STRATEGIES.values() if any(m == "US" for m, _ in s["groups"]))
    assert S.strategy_of(spec, spec["name"], "US").risk.brokerage == 0
    assert S.strategy_of(spec, spec["name"], "IN").risk.brokerage == S.RISK["brokerage"]
