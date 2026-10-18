"""rev10a: paper accounts that change across a restart (the saved trade list keeps only the newest trades), corporate-
action cash on a single session, verdict wording when nothing has closed, and smaller points."""
import copy
from datetime import date, datetime, timedelta, timezone

import pytest

from app import group_live, live
from app.engine import costs as C
from app.engine import core
from app.engine import verdict as V
from app.engine import walkforward as W
from app.engine.core import Ctx, Engine, backtest
from app.models import Strategy


def bars(prices, start="2023-01-02"):
    d, out = date.fromisoformat(start), []
    for p in prices:
        out.append({"t": d.isoformat() + "T00:00:00+05:30", "o": p, "h": p, "l": p, "c": p, "v": 1})
        d += timedelta(days=1)
    return out


def gt(v):
    return [{"l": {"t": "price"}, "op": "gt", "r": {"t": "num", "v": v}}]


def lt(v):
    return [{"l": {"t": "price"}, "op": "lt", "r": {"t": "num", "v": v}}]


FLIP = dict(entry=gt(100.5), exit=lt(100.5),
            risk={"capital": 100000, "brokerage": 20, "slippage": 0.05, "sl": 0, "sizing": "capital", "perTrade": 10000})


def flipped(n=1300):
    """An engine that opened and closed a trade every other candle, live style: over 600 losing trades."""
    b = bars([100 + (i % 2) for i in range(n)])
    e = Engine(Strategy(**FLIP), cost_kind="in_eq")
    e.next_open = False
    ctx = Ctx(b, intraday=False)
    for i in range(1, len(b)):
        e.step(b, ctx, i)
    return e


# ---------- 1. a group's account value stays the same across a restart ----------
def test_group_equity_and_counts_hold_across_a_restart(monkeypatch):
    from tests.test_group_live import candle
    from tests.test_live_polling import make_manager
    import tests.test_group_live as T
    mgr, _ = make_manager()
    monkeypatch.setattr(mgr, "on_order", lambda s, ev: None)
    strat = copy.deepcopy(T.STRAT)
    strat["entry"], strat["exit"], strat["session"] = gt(100.5), lt(100.5), {}
    monkeypatch.setattr(T, "STRAT", strat)
    s = group_live.GroupLiveSession(mgr, T.row())
    m = s.members[0]
    t0 = datetime(2999, 1, 1, 0, 0, tzinfo=timezone.utc)
    for k in range(1100):
        s._on_candle(m, candle((t0 + timedelta(minutes=5 * k)).isoformat(), 101.0 if k % 2 == 0 else 100.0))
    n = len(m.engine.trades)
    assert n > 500
    before = s.snapshot()
    s2 = group_live.GroupLiveSession(mgr, T.row(s.state()))
    assert len(s2.members[0].engine.trades) == 500          # the saved list keeps the newest; the totals keep the rest
    after = s2.snapshot()
    for k in ("equity", "realised", "trades", "wins"):
        assert after["account"][k] == pytest.approx(before["account"][k], abs=0.01), k
    assert after["account"]["trades"] == n
    assert s2.funds()[0] == pytest.approx(s.funds()[0], abs=0.01)
    row = {**T.row(s.state()), "status": "stopped"}
    stopped = group_live.stopped_snapshot(row)
    assert stopped["account"]["realised"] == pytest.approx(before["account"]["realised"], abs=0.01)
    assert stopped["account"]["equity"] == pytest.approx(before["account"]["equity"], abs=0.01)
    assert stopped["account"]["trades"] == n


# ---------- 2. a single session's realised P&L and closed-trade count after a restart ----------
def test_engine_totals_survive_dump_and_load():
    e = flipped()
    assert len(e.trades) > 500 and e.trade_count == len(e.trades)
    assert e.realised_total == pytest.approx(sum(t["pnl"] for t in e.trades))
    e2 = Engine(Strategy(**FLIP), state=e.dump(), cost_kind="in_eq")
    assert len(e2.trades) == 500
    assert (e2.trade_count, e2.win_count) == (e.trade_count, e.win_count)
    assert e2.realised_total == pytest.approx(e.realised_total)
    assert e2.qty == 0 and e2.realised_total == pytest.approx(e2.cash - 100000)     # flat: realised is the return


def test_a_state_saved_before_the_totals_seeds_them_from_its_list_once():
    st = flipped(200).dump()
    st.pop("totals")
    listed = sum(t["pnl"] for t in st["trades"])
    e = Engine(Strategy(**FLIP), state=st, cost_kind="in_eq")
    assert e.realised_total == pytest.approx(listed) and e.trade_count == len(st["trades"])
    again = Engine(Strategy(**FLIP), state=e.dump(), cost_kind="in_eq")       # no double count on the next restart
    assert again.realised_total == pytest.approx(listed) and again.trade_count == len(st["trades"])


def test_single_session_realised_plus_unrealised_is_the_return_after_a_restart():
    e = flipped()
    st = e.dump()
    row = {"id": "s1", "name": "x", "status": "stopped", "instrument": {}, "strategy": {**FLIP, "tf": "1d"},
           "started_at": "2023-01-02", "state": st}
    acct = live.stopped_snapshot(row)["account"]
    assert acct["trades"] == e.trade_count and acct["wins"] == e.win_count
    assert acct["realised"] + acct["unrealised"] == pytest.approx(acct["equity"] - acct["capital"], abs=0.01)


def test_write_off_keeps_the_running_total_with_the_cash():
    e = Engine(Strategy(**FLIP), cost_kind="in_eq")
    e.trades = [{"pnl": -150000.0, "exit_t": "2023-01-03", "qty": 1, "entry": 1}]
    e.realised_total, e.trade_count, e.cash = -150000.0, 1, -50000.0
    e.check_empty({"t": "2023-01-03", "c": 100.0}, [])
    assert e.cash == 0 and e.realised_total == pytest.approx(-100000.0)


def test_signal_session_totals_survive_the_trimmed_list(monkeypatch):
    from app.signal_session import SignalSession, stopped_snapshot
    from tests.test_live_polling import stock_world
    mgr, row = stock_world(monkeypatch, [], [])
    s = SignalSession(mgr, {**row, "strategy": {"capital": 10000.0}, "state": {"last_price": 100.0}})
    for k in range(1100):
        s._fill("buy", 1, 100.0, "x", f"2026-01-05T{k:05d}")
        s._fill("sell", 1, 101.0 if k % 2 else 99.0, "x", f"2026-01-05T{k:05d}")
    assert len(s.trades) == 1000
    s2 = SignalSession(mgr, {**row, "strategy": {"capital": 10000.0}, "state": s.state()})
    acct = s2.snapshot()["account"]
    assert acct["trades"] == 1100 and acct["wins"] == 550
    assert acct["realised"] == pytest.approx(s2.cash - 10000.0)
    stopped = stopped_snapshot({**row, "status": "stopped", "strategy": {"capital": 10000.0}, "state": s.state()})["account"]
    assert stopped["trades"] == 1100 and stopped["realised"] == pytest.approx(acct["realised"])


# ---------- 3. corporate-action cash on a single session reconciles ----------
def test_single_session_dividend_is_in_realised_and_kept_across_a_restart(monkeypatch):
    from tests.test_live_polling import DIV, sbar, stock_world
    mgr, row = stock_world(monkeypatch, [sbar(5, i, 1000.0) for i in range(40)], [DIV])
    monkeypatch.setattr(mgr, "on_order", lambda s, ev: None)
    s = live.LiveSession(mgr, row)
    s._on_candle(sbar(5, 40, 1000.0))
    assert s.engine.qty > 0
    s.last_price = 1000.0
    s._corp_day("2026-01-06", timer=True)
    paid = 5.0 * s.engine.qty
    acct = s.snapshot()["account"]
    assert acct["corp_cash"] == pytest.approx(paid)
    assert acct["realised"] + acct["unrealised"] == pytest.approx(acct["equity"] - acct["capital"], abs=0.01)
    st = s.state()
    assert st["corp_cash"] == pytest.approx(paid)
    stopped = live.stopped_snapshot({**row, "status": "stopped", "state": st})["account"]
    assert stopped["corp_cash"] == pytest.approx(paid)
    assert stopped["realised"] + stopped["unrealised"] == pytest.approx(stopped["equity"] - stopped["capital"], abs=0.01)
    s2 = live.LiveSession(mgr, {**row, "state": st})
    assert s2.corp_cash == pytest.approx(paid)


# ---------- 4. verdict wording when nothing has closed ----------
def test_walkforward_with_no_trades_is_a_skip_not_a_loss():
    b = bars([100] * 400)
    st = Strategy(entry=[{"l": {"t": "price"}, "op": "gt", "r": {"t": "sma", "p": 20}}],
                  risk={"capital": 100000, "brokerage": 20, "slippage": 0.05})
    w = W.run(b, st, 30, kind="in_eq")
    assert w["trades"] == 0 and w["status"] == "skip"
    assert "no trades" in w["headline"].lower()
    assert "lost" not in (w["headline"] + w["detail"]).lower()


def test_verdict_with_one_open_trade_and_none_closed():
    b = bars([100] * 400)
    st = Strategy(entry=gt(50), risk={"capital": 100000, "brokerage": 20, "slippage": 0.05})
    res = backtest(b, st, 30, cost_kind="in_eq")
    assert res["open_trade"] and not res["trades"]
    v = V.evaluate(b, st, 30, res, cost_kind="in_eq")
    assert "No closed trades yet (1 still open)" in v["summary"]
    assert "no closed trades yet (1 still open)" in v["headline"]
    assert "Only 0" not in v["summary"] + v["headline"] and "no trades in this period" not in v["headline"]


# ---------- 5. smaller points ----------
def test_unseen_minimum_counts_closed_trades_only():
    closed = [{"pnl": 100.0}] * 4
    opened = [{"pnl": 100.0}]
    got = V.unseen_check(closed, opened, 100000, [False] * 5, [False] * 5, ("2020", "2022", "2022", "2023"), 10)
    assert got["data"]["unseen_trades"] == 4
    assert got["status"] == "warn" and "Only 4 trades closed" in got["detail"] and "1 still open" in got["detail"]
    ok = V.unseen_check([{"pnl": 100.0}] * 5, [], 100000, [False] * 5, [False] * 5, ("2020", "2022", "2022", "2023"), 10)
    assert ok["status"] == "pass"


def test_currency_derivatives_tax_note_and_stt_added_back():
    for kind in ("in_cds_fut", "in_cds_opt", "in_cds_fut_usd"):
        note = C.tax_estimate(kind, [])["note"]
        assert "business income" in note and "where you live" not in note
    t = {"entry_t": "2024-01-01T00:00:00+05:30", "exit_t": "2024-03-01T00:00:00+05:30", "qty": 100, "entry": 1000.0,
         "exit": 1100.0, "pnl": 9000.0}
    stt = 0.001 * 100 * (1000 + 1100)
    tax = C.tax_estimate("in_eq", [t])
    assert tax["amount"] == pytest.approx((9000 + stt) * 0.20)
    assert "estimate" in tax["note"].lower() and "STT" in tax["note"]


def test_preset_group_backtest_notes_todays_members():
    from app import research
    from app.universes import members_note
    from tests.test_review_rev10a import bars as mk
    st = Strategy(entry=gt(100.5), exit=lt(100.5), risk={"capital": 100000, "brokerage": 20, "slippage": 0.05})
    ds = [{"inst": {"symbol": s, "id": f"IN:{s}"}, "bars": mk([100 + (i % 2) for i in range(120)]), "start": 30, "lot": 1,
           "kind": "in_eq"} for s in ("TCS", "INFY")]
    got = research.run_group(ds, st, {"id": "nifty50", "name": "NIFTY 50 stocks", "market": "IN"}, 365, 3650)
    note = members_note({"id": "nifty50", "market": "IN"})
    assert note and "members on the day this test ran" in note and note in got["verdict"]["notes"]      # R52-001 wording
    custom = research.run_group(ds, st, {"id": "custom", "name": "Mine", "market": "IN"}, 365, 3650)
    assert not any("members on the day this test ran" in n for n in custom["verdict"].get("notes") or [])


def test_evaluate_walkforward_and_snapshot_pass_base_min(monkeypatch):
    seen = []

    class Rec(Ctx):
        def __init__(self, b, intraday, base_min=None):
            seen.append(base_min)
            super().__init__(b, intraday, base_min)
    b = bars([100 + (i % 7) for i in range(400)])
    st = Strategy(entry=[{"l": {"t": "price"}, "op": "gt", "r": {"t": "sma", "p": 20}}],
                  risk={"capital": 100000, "brokerage": 20, "slippage": 0.05})
    res = backtest(b, st, 30, cost_kind="in_eq")
    monkeypatch.setattr(V, "Ctx", Rec)
    monkeypatch.setattr(W, "Ctx", Rec)
    V.evaluate(b, st, 30, res, cost_kind="in_eq")
    W.run(b, st, 30, kind="in_eq")
    assert seen and all(x == core.TF_MIN["1d"] for x in seen)

    from tests.test_live_polling import sbar, stock_world
    mgr, row = stock_world(monkeypatch, [sbar(5, i, 1000.0) for i in range(40)], [])
    monkeypatch.setattr(mgr, "on_order", lambda s, ev: None)
    s = live.LiveSession(mgr, row)
    seen.clear()
    monkeypatch.setattr(live, "Ctx", Rec)
    s.snapshot()
    assert seen == [core.TF_MIN[s.tf]]


def test_members_note_carries_no_stale_year():
    # R38-004: in Oct 2026 the verdict said "NIFTY 50 stocks are today's members (as of 2025)": the year was written into
    # the sentence, not taken from the list. A list with a date says that date; one without gives no year
    from app import universes
    note = universes.members_note({"id": "nifty50", "market": "IN"})
    assert "2025" not in note and "on the day this test ran:" in note
    p = next(p for p in universes.PRESETS["IN"] if p["id"] == "nifty50")
    p["as_of"] = "Sep 2026"
    try:
        assert "on the day this test ran (the list as of Sep 2026):" in universes.members_note({"id": "nifty50", "market": "IN"})
    finally:
        p.pop("as_of")
