import math

import pytest

from app.engine import costs as C
from app.engine.core import backtest
from app.models import Strategy
from tests.test_engine import bars_from


def test_india_equity_buy_and_sell_charges():
    buy = C.order_costs("in_eq", "buy", 100, 1000, 20)      # ₹1,00,000 of stock
    assert buy["stt"] == pytest.approx(100)                  # 0.1%
    assert buy["stamp"] == pytest.approx(15)                 # 0.015%, buy only
    assert buy["gst"] == pytest.approx(0.18 * (20 + buy["exchange"]))
    sell = C.order_costs("in_eq", "sell", 100, 1000, 20)
    assert sell["stamp"] == 0 and sell["stt"] == pytest.approx(100)


def test_india_futures_stt_only_on_sell():
    assert C.order_costs("in_fut", "buy", 75, 20000, 20)["stt"] == 0
    assert C.order_costs("in_fut", "sell", 75, 20000, 20)["stt"] == pytest.approx(75 * 20000 * 0.0005)    # Budget 2026: 0.05%
    assert C.order_costs("in_opt", "sell", 75, 100, 20)["stt"] == pytest.approx(75 * 100 * 0.0015)       # 0.15% of premium
    assert C.order_costs("in_opt", "buy", 75, 100, 20)["stt"] == 0


def test_us_fees_only_on_sell_and_finra_is_capped():
    assert set(C.order_costs("us", "buy", 10, 100, 0)) == {"brokerage"}
    sell = C.order_costs("us", "sell", 1_000_000, 1, 0)
    assert sell["finra"] == C.US_FINRA_CAP


def test_crypto_fee_each_side():
    assert C.order_costs("crypto", "buy", 0.5, 60000, 0)["fee"] == pytest.approx(30)


def test_kind_of_instruments():
    assert C.kind_of({"market": "IN", "type": "EQ"}) == "in_eq"
    assert C.kind_of({"market": "IN", "type": "FUT"}) == "in_fut"
    assert C.kind_of({"market": "IN", "type": "CE"}) == "in_opt"
    assert C.kind_of({"market": "CRYPTO"}) == "crypto"
    assert C.kind_of({"market": "CSV"}) == "flat"
    assert C.kind_of(None) == "in_eq"


def test_floor_to_steps():
    assert C.floor_to(454.9, 1) == 454 and isinstance(C.floor_to(454.9, 1), int)
    assert C.floor_to(160, 75) == 150
    assert C.floor_to(0.123456, 0.0001) == 0.1234
    assert C.floor_to(math.inf, 1) == 0


def test_india_tax_estimate_short_and_long_term():
    trades = [{"entry_t": "2024-01-01T00:00:00+05:30", "exit_t": "2024-03-01T00:00:00+05:30", "pnl": 10000},
              {"entry_t": "2023-01-01T00:00:00+05:30", "exit_t": "2024-06-01T00:00:00+05:30", "pnl": 225000}]
    tax = C.tax_estimate("in_eq", trades)
    assert tax["amount"] == pytest.approx(10000 * 0.20 + (225000 - 125000) * 0.125)
    assert C.tax_estimate("crypto", trades)["amount"] is None


def test_backtest_costs_add_up():
    s = Strategy(entry=[{"l": {"t": "price"}, "op": "xa", "r": {"t": "sma", "p": 5}}],
                 exit=[{"l": {"t": "price"}, "op": "xb", "r": {"t": "sma", "p": 5}}],
                 risk={"capital": 100000, "riskPct": 1, "sl": 5, "brokerage": 20, "slippage": 0})
    closes = [100 + 10 * math.sin(i / 8) for i in range(300)]
    out = backtest(bars_from(closes), s, start=50, cost_kind="in_eq")
    c = out["costs"]
    assert c["total"] > 0
    assert c["gross_pnl"] - c["total"] == pytest.approx(c["net_pnl"], abs=0.02)
    assert c["net_pnl"] == pytest.approx(out["equity"][-1] - 100000, abs=0.02)
    assert sum(i["amount"] for i in c["items"]) == pytest.approx(c["total"], abs=0.1)
    # each closed trade's P&L is after its own costs
    assert all("costs" in t and t["costs"] > 0 for t in out["trades"])


def test_fractional_crypto_quantity():
    s = Strategy(entry=[{"l": {"t": "price"}, "op": "xa", "r": {"t": "num", "v": 60500}}],
                 risk={"capital": 10000, "riskPct": 1, "sl": 5, "brokerage": 0, "slippage": 0})
    out = backtest(bars_from([60000.0] * 20 + [61000.0] * 5), s, start=5, lot=0.0001, cost_kind="crypto")
    qty = out["events"][0]["qty"]
    assert 0 < qty < 1 and round(qty, 4) == qty
