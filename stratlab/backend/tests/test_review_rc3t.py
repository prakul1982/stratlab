"""RC3-T: a harsh correctness review of the Trade side. Plain asserts against hand-worked numbers."""
import pytest

from app.engine import costs as C
from app.engine.core import Engine, backtest
from app.models import Strategy
from tests.test_engine import bars_from

IST = "T00:00:00+05:30"


def _round_trips(closes):
    """Daily candles that make one entry on the first cross above 10 and leave on the first cross below it, twice."""
    s = Strategy(entry=[{"l": {"t": "price"}, "op": "xa", "r": {"t": "num", "v": 10}}],
                 exit=[{"l": {"t": "price"}, "op": "xb", "r": {"t": "num", "v": 10}}],
                 risk={"capital": 100000, "riskPct": 100, "maxAlloc": 50, "sl": 0, "brokerage": 20, "slippage": 0})
    return s, bars_from(closes)


# ---------- RC3T-001: an Indian ETF is not charged as a share ----------
def test_an_indian_etf_pays_the_fund_rates_not_the_share_rates():
    assert C.kind_of({"market": "IN", "type": "EQ", "exchange": "NSE", "symbol": "NIFTYBEES", "name": "NIPPON INDIA ETF NIFTY BEES"}) == "in_etf"
    assert C.kind_of({"market": "IN", "type": "EQ", "exchange": "NSE", "symbol": "GOLDBEES"}) == "in_etf"
    assert C.kind_of({"market": "IN", "type": "ETF", "exchange": "NSE", "symbol": "X"}) == "in_etf"
    # a company's shares, and an instrument with no exchange, stay shares
    assert C.kind_of({"market": "IN", "type": "EQ", "exchange": "NSE", "symbol": "RELIANCE", "name": "RELIANCE INDUSTRIES"}) == "in_eq"
    assert C.kind_of({"market": "IN", "type": "EQ"}) == "in_eq" and C.kind_of(None) == "in_eq"
    # a unit bought for delivery pays no STT; sold on the exchange 0.001% (Rs1,00,000 of units: Rs1)
    buy = C.order_costs("in_etf", "buy", 100, 1000, 0)
    sell = C.order_costs("in_etf", "sell", 100, 1000, 0)
    assert buy["stt"] == 0 and sell["stt"] == pytest.approx(1.0)
    share = C.order_costs("in_eq", "buy", 100, 1000, 0)["stt"]
    assert share == pytest.approx(100.0)          # what a backtest of NIFTYBEES used to pay on the buy alone


def test_an_etf_round_trip_costs_a_fraction_of_a_shares():
    s, bars = _round_trips([9.0] * 20 + [11.0] * 10 + [9.0] * 10)
    etf = backtest(bars, s, 5, cost_kind="in_etf")["costs"]
    share = backtest(bars, s, 5, cost_kind="in_eq")["costs"]
    assert etf["total"] < share["total"] / 2
    assert "Depository (DP) charge" in {i["label"] for i in etf["items"]}      # units sit in a demat account too
    assert "Tax on fund units" in etf["tax"]["note"] and etf["tax"]["amount"] is None


def test_an_etf_keeps_the_india_session_clock():
    from app.engine.core import INDIA_CLOSE
    s = Strategy(tf="1h", entry=[{"l": {"t": "price"}, "op": "gt", "r": {"t": "num", "v": 1}}], risk={"capital": 100000})
    assert Engine(s, cost_kind="in_etf").close_min == INDIA_CLOSE == Engine(s, cost_kind="in_eq").close_min


# ---------- RC3T-002: a delivery sale pays the depository charge ----------
def test_a_delivery_sale_pays_the_depository_charge_once_a_day():
    s, bars = _round_trips([9.0] * 20 + [11.0] * 10 + [9.0] * 10)
    out = backtest(bars, s, 5, cost_kind="in_eq")
    t, = out["trades"]
    sells = C.total(C.order_costs("in_eq", "sell", t["qty"], t["exit"], 20))
    buys = C.total(C.order_costs("in_eq", "buy", t["qty"], t["entry"], 20))
    assert t["costs"] == pytest.approx(buys + sells + C.dp_charge()) and C.dp_charge() == pytest.approx(15.34)
    dp = next(i for i in out["costs"]["items"] if i["label"] == "Depository (DP) charge")
    assert dp["amount"] == pytest.approx(15.34)
    assert t["pnl"] == pytest.approx(t["qty"] * (t["exit"] - t["entry"]) - t["costs"])
    assert out["costs"]["net_pnl"] == pytest.approx(out["equity"][-1] - 100000, abs=0.02)


def test_other_products_pay_no_depository_charge():
    s, bars = _round_trips([9.0] * 20 + [11.0] * 10 + [9.0] * 10)
    for kind in ("in_eq_mis", "in_fut", "us", "crypto", "flat"):
        out = backtest(bars, s, 5, cost_kind=kind)
        assert "Depository (DP) charge" not in {i["label"] for i in out["costs"]["items"]}, kind
    short = Strategy(side="short", entry=[{"l": {"t": "price"}, "op": "xa", "r": {"t": "num", "v": 10}}],
                     exit=[{"l": {"t": "price"}, "op": "xb", "r": {"t": "num", "v": 10}}],
                     risk={"capital": 100000, "riskPct": 100, "maxAlloc": 50, "sl": 0, "brokerage": 20, "slippage": 0})
    out = backtest(bars, short, 5, cost_kind="in_eq")
    assert out["trades"] and "Depository (DP) charge" not in {i["label"] for i in out["costs"]["items"]}     # a short sale has no demat debit


def test_the_depository_charge_is_not_paid_twice_on_one_day_and_survives_a_restart():
    s, _ = _round_trips([9.0])
    e = Engine(s, cost_kind="in_eq")
    e.day, e.dir = "2026-03-02", 1
    assert e.dp_for("2026-03-02") == C.dp_charge()
    e.dp_day = "2026-03-02"
    assert e.dp_for("2026-03-02") == 0 and e.dp_for("2026-03-03") == C.dp_charge()
    again = Engine(s, cost_kind="in_eq", state=e.dump())
    assert again.dp_day == "2026-03-02" and again.dp_for("2026-03-02") == 0


def test_the_cost_register_says_where_the_charge_applies():
    from app import rules
    row = next(r for r in rules.registry() if r["id"] == "dp_charge")
    assert "journal" in row["where"] and "backtests" in row["where"] and "chart replay" in row["where"]


# ---------- RC3T-003: the tax-free long-term gain is for each year ----------
def test_the_long_term_exemption_is_for_each_financial_year():
    # two years of long-term gains of Rs1,25,000 each: each year's is exactly the exempt amount, so nothing is due
    # (the estimate used to count the exemption once over the whole test: Rs15,625 on the second year's)
    trades = [{"entry_t": "2022-01-03" + IST, "exit_t": "2023-06-01" + IST, "pnl": 125000},
              {"entry_t": "2022-01-03" + IST, "exit_t": "2024-06-03" + IST, "pnl": 125000}]
    assert C.tax_estimate("in_eq", trades)["amount"] == 0
    # the same Rs2,50,000 in one year has one exemption
    one = [{**t, "exit_t": "2024-06-0%d" % (k + 3) + IST} for k, t in enumerate(trades)]
    assert C.tax_estimate("in_eq", one)["amount"] == pytest.approx((250000 - 125000) * 0.125)
    assert "each financial year" in C.tax_estimate("in_eq", trades)["note"]


def test_a_loss_carries_to_the_next_year_and_the_year_ends_in_march():
    # a short-term loss in FY 2023-24 (to 31 Mar 2024) is set off against the next year's gains
    trades = [{"entry_t": "2024-01-01" + IST, "exit_t": "2024-03-28" + IST, "pnl": -20000},
              {"entry_t": "2024-04-01" + IST, "exit_t": "2024-05-02" + IST, "pnl": 50000}]
    assert C.tax_estimate("in_eq", trades)["amount"] == pytest.approx(30000 * 0.20)
    # 31 March and 1 April are different years: a gain on each is taxed in its own year
    mar = {"entry_t": "2024-02-01" + IST, "exit_t": "2024-03-31" + IST, "pnl": 10000}
    apr = {"entry_t": "2024-02-01" + IST, "exit_t": "2024-04-01" + IST, "pnl": 10000}
    assert C.tax_estimate("in_eq", [mar, apr])["amount"] == pytest.approx(20000 * 0.20)
    # a long-term loss sets off only long-term gains
    lt_loss = {"entry_t": "2022-01-01" + IST, "exit_t": "2024-06-01" + IST, "pnl": -50000}
    st_gain = {"entry_t": "2024-05-01" + IST, "exit_t": "2024-06-02" + IST, "pnl": 40000}
    assert C.tax_estimate("in_eq", [lt_loss, st_gain])["amount"] == pytest.approx(40000 * 0.20)


# ---------- RC3T-002 in chart replay, and the page's running figure ----------
def test_replay_delivery_sales_pay_the_depository_charge_for_each_day_sold():
    from app import replay as R
    from tests.test_replay import day_bars, sim
    b = day_bars()
    # 100 shares in on day 1, half out on day 3 and the rest on day 5: two days of sales, two charges
    t, = sim(b, [{"i": 1, "action": "long", "qty": 100}, {"i": 3, "action": "short", "qty": 50}, {"i": 5, "action": "flat"}],
             kind="in_eq", brokerage=0)["trades"]
    fills = [("buy", 100, b[1]["c"]), ("sell", 50, b[3]["c"]), ("sell", 50, b[5]["c"])]
    assert t["charges"] == pytest.approx(sum(C.total(C.order_costs("in_eq", s, q, p, 0)) for s, q, p in fills) + 2 * C.dp_charge())
    # a short sale, and a fund's units, as the model says
    s, = sim(b, [{"i": 1, "action": "short", "qty": 100}, {"i": 5, "action": "flat"}], kind="in_eq", brokerage=0)["trades"]
    assert s["charges"] == pytest.approx(sum(C.total(C.order_costs("in_eq", sd, 100, p, 0)) for sd, p in (("sell", b[1]["c"]), ("buy", b[5]["c"]))))
    e, = sim(b, [{"i": 1, "action": "long", "qty": 100}, {"i": 5, "action": "flat"}], kind="in_etf", brokerage=0)["trades"]
    assert e["charges"] == pytest.approx(sum(C.total(C.order_costs("in_etf", sd, 100, p, 0)) for sd, p in (("buy", b[1]["c"]), ("sell", b[5]["c"]))) + C.dp_charge())
    assert R.rates("in_eq", 20)["in_eq"]["dp"] == C.dp_charge() and "dp" not in R.rates("in_eq", 20)["in_eq_mis"]
    assert R.rates("in_etf", 20)["in_etf"]["dp"] == C.dp_charge()


def test_a_signal_session_delivery_sale_pays_it_once_a_day(monkeypatch):
    from app import signal_session as SS
    s = SS.SignalSession.__new__(SS.SignalSession)
    s.inst, s.settings, s.cost_items, s.dp_day, s.pos = {"market": "IN", "exchange": "NSE", "type": "EQ", "symbol": "TCS"}, \
        {"product": "delivery", "brokerage": 20}, {}, None, 10.0
    first = s._pay("sell", 10, 100.0)
    assert s.cost_items["dp"] == C.dp_charge() and first == pytest.approx(C.total(C.order_costs("in_eq", "sell", 10, 100.0, 20)) + C.dp_charge())
    second = s._pay("sell", 5, 100.0)                                  # the same day: no second charge
    assert s.cost_items["dp"] == C.dp_charge() and second == pytest.approx(C.total(C.order_costs("in_eq", "sell", 5, 100.0, 20)))
    s.cost_items, s.pos, s.dp_day = {}, 0.0, None
    s._pay("buy", 5, 100.0)                                            # a purchase pays none
    assert "dp" not in s.cost_items
    s.settings["product"] = "intraday"
    s.cost_items, s.pos = {}, 5.0
    s._pay("sell", 5, 100.0)
    assert "dp" not in s.cost_items


# ---------- RC3T-006: a forward-test signal is judged on the instrument's own session ----------
def test_signals_follow_the_session_of_the_instrument():
    from datetime import datetime, timedelta, timezone
    from app.signal_session import market_open
    ist = timezone(timedelta(hours=5, minutes=30))
    at = lambda hm: datetime(2026, 10, 27, int(hm[:2]), int(hm[3:]), tzinfo=ist)       # a Tuesday
    fut = {"market": "IN", "exchange": "NFO", "type": "FUT", "fno": True, "symbol": "NIFTY26NOVFUT"}
    share = {"market": "IN", "exchange": "NSE", "type": "EQ", "symbol": "TINYCO"}
    cas = {"market": "IN", "exchange": "NSE", "type": "EQ", "symbol": "RELIANCE"}
    assert market_open(fut, at("15:35")) and not market_open(fut, at("15:40")) and not market_open(fut, at("09:10"))
    assert market_open(share, at("15:25")) and not market_open(share, at("15:30"))
    assert market_open(cas, at("15:10"), "cas") and not market_open(cas, at("15:20"), "cas")        # in the closing auction
    # MCX trades to 23:30, and to 23:55 while US daylight saving is off (from the first Sunday of November)
    mcx = {"market": "MCX", "exchange": "MCX", "type": "FUT", "symbol": "GOLDM"}
    nov = lambda hm: datetime(2026, 11, 3, int(hm[:2]), int(hm[3:]), tzinfo=ist)
    assert market_open(mcx, nov("23:40")) and not market_open(mcx, nov("23:56"))
    assert market_open(mcx, at("23:20")) and not market_open(mcx, at("23:40"))


def test_a_paper_order_by_hand_follows_the_session_of_the_instrument():
    """The AI assistant's paper orders (live.LiveSession.price_problem) use the same timetable: a NIFTY future trades to 15:40."""
    from datetime import datetime, timedelta, timezone
    from app.live import LiveSession
    ist = timezone(timedelta(hours=5, minutes=30))
    tue = lambda hm: datetime(2026, 10, 27, int(hm[:2]), int(hm[3:]), tzinfo=ist)

    class Stub:
        market, session_kind = "IN", "fo"
        last_tick_at = tue("15:34").isoformat()

    assert LiveSession.price_problem(Stub, tue("15:35")) is None
    assert "closed" in LiveSession.price_problem(Stub, tue("15:41"))

    class Stock(Stub):
        session_kind = "cas"
        last_tick_at = tue("15:12").isoformat()

    assert LiveSession.price_problem(Stock, tue("15:14")) is None
    assert "closed" in LiveSession.price_problem(Stock, tue("15:20"))        # the closing auction, not continuous trading


# ---------- RC3T-009: the closing auction history counts the stocks that have a gap ----------
def test_closing_auction_history_says_how_many_stocks_have_a_gap(monkeypatch):
    from app import closing_auction as CA
    day = {"stocks": {"AAA": [100.0, 101.0, 500], "BBB": [100.0, 100.0, 500], "CCC": [None, 50.0, 500], "DDD": [100.0, 99.0, 500]}, "indices": {}}
    monkeypatch.setattr(CA, "_days", lambda: {"2026-10-26": day})
    row = CA.history()["days"][0]
    assert (row["stocks"], row["compared"], row["up"], row["down"]) == (4, 3, 1, 1)      # CCC has no reference price: no gap, not "unchanged"


# ---------- RC3T-001 in the journal: a tradebook's ETF lines are charged as units ----------
def test_the_journal_charges_an_etf_as_units_when_the_file_lists_no_charges():
    from app import journal as J
    s = J.clean_settings({})
    assert J.classify("NIFTYBEES")["kind"] == "in_etf" and J.classify("GOLDBEES")["kind"] == "in_etf"
    assert J.classify("RELIANCE")["kind"] == "in_eq" and J.classify("NIFTY25OCT25000CE")["kind"] == "in_opt"

    def trade(sym, ed, xd):
        got = J.manual_trades([{"id": "m1", "sym": sym, "segment": "eq", "side": "long", "ed": ed, "xd": xd, "qty": 100, "entry": 1000.0, "exit": 1010.0}], s)
        return got[0]["charges"]
    brk = s["brokerage_delivery"]
    etf = trade("NIFTYBEES", "2026-09-01", "2026-10-01")
    want = C.total(C.order_costs("in_etf", "buy", 100, 1000.0, brk)) + C.total(C.order_costs("in_etf", "sell", 100, 1010.0, brk)) + C.dp_charge()
    assert etf == pytest.approx(want)
    assert trade("RELIANCE", "2026-09-01", "2026-10-01") - etf == pytest.approx(100 * 1000.0 * 0.001 + 100 * 1010.0 * (0.001 - 0.00001), rel=1e-6)
    # bought and sold on one day: no depository charge for the units, as for shares
    same = trade("NIFTYBEES", "2026-10-01", "2026-10-01")
    assert same == pytest.approx(C.total(C.order_costs("in_etf", "buy", 100, 1000.0, s["brokerage_other"]))
                                 + C.total(C.order_costs("in_etf", "sell", 100, 1010.0, s["brokerage_other"])))
