"""Group (portfolio) backtests: shared slots, a portfolio-wide daily loss cap, the API."""
import itertools
import pandas as pd
import pytest

from app.engine import portfolio
from app.models import Strategy
from tests.test_engine_intraday import day
from tests.test_notebooks import EMA, api  # noqa: F401  (fixture)

ALWAYS = [{"l": {"t": "price"}, "op": "gt", "r": {"t": "num", "v": 0}}]


def ds(sym, bars):
    return {"inst": {"symbol": sym, "id": f"X:{sym}"}, "bars": bars, "start": 0, "lot": 1, "kind": "flat"}


def S(**kw):
    base = {"tf": "15m", "entry": ALWAYS, "exit": [], "risk": {"capital": 100000, "sl": 0, "tgt": 0, "brokerage": 0, "slippage": 0,
                                                                "sizing": "capital", "perTrade": 20000, "maxBars": 2}}
    base.update(kw)
    return Strategy(**base)


def test_slots_are_shared():
    a = day("2026-01-05", [100 + i for i in range(12)])
    b = day("2026-01-05", [50 + i for i in range(12)])
    out = portfolio.run([ds("A", a), ds("B", b)], S(), max_open=1)
    assert out["most_open"] == 1
    # both instruments get turns, but never at the same time
    spans = sorted((t["entry_t"], t["exit_t"]) for t in out["trades"])
    assert all(spans[k][1] <= spans[k + 1][0] for k in range(len(spans) - 1))
    assert {t["symbol"] for t in out["trades"]} <= {"A", "B"} and len(out["members"]) == 2
    both = portfolio.run([ds("A", a), ds("B", b)], S(), max_open=2)
    assert both["most_open"] == 2 and len(both["trades"]) > len(out["trades"])


def test_portfolio_loss_cap_closes_everything():
    a = day("2026-01-05", [100, 100, 95, 90, 85, 80])
    b = day("2026-01-05", [100, 100, 99, 98, 97, 96])
    s = S(risk={"capital": 100000, "sl": 0, "tgt": 0, "brokerage": 0, "slippage": 0, "sizing": "capital", "perTrade": 50000},
          session={"dailyLossPct": 3})
    out = portfolio.run([ds("A", a), ds("B", b)], s, max_open=2)
    whys = {t["why"] for t in out["trades"]}
    assert whys == {"Daily loss cap"} and len(out["trades"]) == 2 and not out["open_trades"]
    assert out["stats"]["ret"] < 0


def _notional(out):
    return sum(t["qty"] * t["entry"] for t in out["open_trades"])


def test_one_pot_funds_every_position():
    # 4 flat stocks, the default risk sizing (1% risk at a 2% stop is 50,000 a trade): the four separate accounts
    # used to open 2,00,000 of stock on a 1,00,000 account
    flat = [day("2026-01-05", [100.0] * 8) for _ in range(4)]
    s = S(risk={"capital": 100000, "brokerage": 0, "slippage": 0})
    out = portfolio.run([ds(f"S{k}", b) for k, b in enumerate(flat)], s, max_open=4)
    # each position is held to its slot's share since R38-003 (Rs1,00,000 over 4 slots: Rs25,000), so all four open;
    # this expected two Rs50,000 positions and the other two shut out
    assert len(out["open_trades"]) == 4 and out["most_open"] == 4 and {t["qty"] for t in out["open_trades"]} == {250}
    assert _notional(out) <= 100000
    # with 3x leverage the pot carries all four, up to 3x its cash
    lev = portfolio.run([ds(f"S{k}", b) for k, b in enumerate(flat)], S(risk={"capital": 100000, "brokerage": 0, "slippage": 0,
                                                                             "leverage": 3}), max_open=4)
    assert len(lev["open_trades"]) == 4 and _notional(lev) <= 300000


def test_later_entries_get_what_is_left():
    # 70,000 a trade: the second stock gets the 30,000 the first leaves free
    a = day("2026-01-05", [100.0] * 6)
    b = day("2026-01-05", [50.0] * 6)
    s = S(risk={"capital": 100000, "sl": 0, "tgt": 0, "brokerage": 0, "slippage": 0, "sizing": "capital", "perTrade": 70000})
    out = portfolio.run([ds("A", a), ds("B", b)], s, max_open=2)
    qty = {t["symbol"]: t["qty"] for t in out["open_trades"]}
    assert qty == {"A": 700, "B": 600}


def test_entries_are_sized_from_the_pot():
    # A's 100 shares double; B's next trade is sized from the whole pot (1,00,000 + A's 10,000), not B's own account
    a = day("2026-01-05", [100, 100, 100, 100, 200, 200, 200, 200])     # A trades 09:45 and 10:15, when it doubles
    b = day("2026-01-05", [10] * 8)                           # B's 10:45 trade is sized after that close (not its 10:15)
    s = S(risk={"capital": 100000, "sl": 0, "tgt": 0, "brokerage": 0, "slippage": 0, "sizing": "risk", "maxAlloc": 10, "maxBars": 1})
    out = portfolio.run([ds("A", a), ds("B", b)], s, max_open=2)
    qty = [t["qty"] for t in sorted(out["trades"] + out["open_trades"], key=lambda t: t["entry_t"]) if t["symbol"] == "B"]
    assert qty[0] == 1000                    # 10% of 1,00,000 at 10
    assert qty[-1] == 1100                   # 10% of 1,10,000 once A is up 10,000


def test_group_cagr_uses_the_calendar():
    # two coins rising 0.1% a day for a year, held throughout: CAGR is the year's return
    days = [{"t": f"{d.date()}T00:00:00+00:00", "o": 100 * 1.001 ** k, "h": 100 * 1.001 ** k, "l": 100 * 1.001 ** k,
             "c": 100 * 1.001 ** k, "v": 1.0} for k, d in enumerate(pd.date_range("2025-01-01", periods=366))]
    s = S(tf="1d", risk={"capital": 100000, "sl": 0, "tgt": 0, "brokerage": 0, "slippage": 0, "sizing": "capital", "perTrade": 50000})
    out = portfolio.run([ds("A", days), ds("B", days)], s, max_open=2)
    st = out["stats"]
    assert st["ret"] > 40 and st["cagr"] == pytest.approx(st["ret"], rel=0.02)


def test_group_notebook_api(api):  # noqa: F811
    nb = api.post("/notebooks", json={"name": "Coins", "strategy": EMA, "instrument": "CRYPTO:BTC-USD"}).json()
    presets = api.get("/groups", params={"market": "CRYPTO"}).json()
    assert presets[0]["id"] == "top_coins" and presets[0]["count"] == 10
    r = api.put(f"/notebooks/{nb['id']}", json={"group": {"id": "top_coins", "name": "10 large coins", "market": "CRYPTO", "maxOpen": 2,
                                                          "members": [{"symbol": s} for s in presets[0]["symbols"]]}})
    assert r.status_code == 200 and r.json()["group"]["maxOpen"] == 2
    listed = api.get("/notebooks").json()[0]
    assert listed["instrument"]["symbol"] == "10 large coins (10)"
    e = api.post(f"/notebooks/{nb['id']}/experiments", json={"days": 400}).json()["experiment"]
    g = e["group"]
    assert e["instrument"]["type"] == "GROUP" and g["max_open"] == 2 and g["most_open"] <= 2
    assert {m["symbol"] for m in g["members"]} == {"BTC/USD", "ETH/USD", "SOL/USD"}      # the fake exchange lists three
    assert len(g["skipped"]) == 7 and any("not listed" in x for x in g["skipped"])
    assert len(e["series"]["t"]) == len(e["series"]["equity"]) and e["series"]["close"] == []
    assert {c["id"]: c["status"] for c in e["verdict"]["checks"]}["nearby"] == "skip"
    assert all("symbol" in t for t in e["trades"])
    assert api.post(f"/notebooks/{nb['id']}/experiments/1/walkforward").status_code == 400
    # picking one instrument again replaces the group
    api.put(f"/notebooks/{nb['id']}", json={"instrument": "CRYPTO:ETH-USD"})
    assert not api.get(f"/notebooks/{nb['id']}").json().get("group")


@pytest.mark.parametrize("order", [("A", "B"), ("B", "A")])
def test_slot_freed_inside_a_candle_is_not_free_at_its_open(order):
    # one slot, A and B signal on the same close; A fills at 10:00's open (100) and its 1% stop is hit inside that
    # candle: B can't also open at 10:00 (two positions at that open), whichever stock steps first
    bars = {"A": day("2026-01-05", [100, 100, 95, 95, 95, 95]), "B": day("2026-01-05", [50.0] * 6)}
    s = S(risk={"capital": 100000, "sl": 1, "tgt": 0, "brokerage": 0, "slippage": 0, "sizing": "capital", "perTrade": 20000},
          session={"maxTradesDay": 1})
    out = portfolio.run([ds(k, bars[k]) for k in order], s, max_open=1)
    held = sorted((t["entry_t"], t["exit_t"] or "~", t["symbol"]) for t in out["trades"] + out["open_trades"])
    assert held[0][0] == bars[order[0]][2]["t"]          # the first in line takes the slot at 10:00's open
    assert all(held[k][1] < held[k + 1][0] for k in range(len(held) - 1))


@pytest.mark.parametrize("order", [("A", "B"), ("B", "A")])
def test_entry_at_the_open_is_sized_on_the_pot_at_the_last_close(order):
    # A doubles on 10:00's close; B fills at 10:00's open, so its 10% is of the pot then (1,00,000), whichever steps first
    bars = {"A": day("2026-01-05", [100, 100, 100, 200, 200]), "B": day("2026-01-05", [10, 10, 11, 11, 11])}
    s = S(entry=[{"l": {"t": "price"}, "op": "gt", "r": {"t": "num", "v": 10.5}}],
          risk={"capital": 100000, "sl": 0, "tgt": 0, "brokerage": 0, "slippage": 0, "sizing": "risk", "maxAlloc": 10, "maxBars": 0})
    out = portfolio.run([ds(k, bars[k]) for k in order], s, max_open=2)
    qty = {t["symbol"]: t["qty"] for t in out["open_trades"]}
    assert qty == {"A": 100, "B": 909}


def _daily(closes):
    return [{"t": f"2026-01-{5 + i:02d}", "o": c, "h": c, "l": c, "c": c, "v": 1} for i, c in enumerate(closes)]


def _dds(sym, bars, start):
    return {**ds(sym, bars), "start": start}


def test_an_exit_at_the_open_frees_its_slot_whatever_the_order():
    # max 2: A's exit rule fires on the 4th close and fills at the 5th open, where B and C also enter
    low = [{"l": {"t": "price"}, "op": "lt", "r": {"t": "num", "v": 95}}]
    s = S(tf="1d", exit=low, risk={"capital": 100000, "sl": 0, "tgt": 0, "brokerage": 0, "slippage": 0,
                                   "sizing": "capital", "perTrade": 20000, "maxBars": 0})
    data = {"A": _dds("A", _daily([100, 100, 100, 90, 90, 90, 90]), 0), "B": _dds("B", _daily([100] * 7), 2),
            "C": _dds("C", _daily([100] * 7), 2)}
    seen = set()
    for order in itertools.permutations("ABC"):
        out = portfolio.run([data[k] for k in order], s, max_open=2)
        assert out["most_open"] <= 2
        seen.add(str(sorted((t["symbol"], t["entry_t"]) for t in out["trades"] + out["open_trades"])))
    assert len(seen) == 1
    assert sum(1 for t in out["open_trades"] if t["symbol"] in "BC") == 2


def test_a_time_exit_on_a_flat_candle_does_not_free_a_slot_at_the_open():
    # flat bars: a close exit has the same price as the open, but the slot was still held at that open
    s = S(tf="1d", exit=[], risk={"capital": 100000, "sl": 0, "tgt": 0, "brokerage": 0, "slippage": 0,
                                  "sizing": "capital", "perTrade": 20000, "maxBars": 2})
    flat = _daily([100] * 10)
    out = portfolio.run([_dds(k, flat, i) for i, k in enumerate("XAB")], s, max_open=2)
    assert out["most_open"] <= 2
    assert all(t["at_open"] is False for t in out["trades"] if t["why"] == "Time exit")


def test_risk_sizing_in_a_group_takes_a_slots_share_not_one_share():
    # R38-003: NIFTY 50 group, Rs5,00,000, risk 1% a trade at a 2% stop, up to 10 open: 1% of Rs5,00,000 is Rs5,000 over
    # a Rs8 stop on a Rs400 stock = 625 shares (Rs2,50,000), so the first two positions took the whole pot and the rest
    # opened with 1 share (BEL, HDFCBANK, TATACONSUM at qty 1). Each position is held to its slot: Rs5,00,000 / 10 =
    # Rs50,000, that is 125 shares at Rs400
    flat = [day("2026-01-05", [400.0] * 8) for _ in range(10)]
    s = S(risk={"capital": 500000, "riskPct": 1, "sl": 2, "tgt": 0, "brokerage": 0, "slippage": 0, "sizing": "risk"})
    out = portfolio.run([ds(f"S{k}", b) for k, b in enumerate(flat)], s, max_open=10)
    assert len(out["open_trades"]) == 10 and {t["qty"] for t in out["open_trades"]} == {125}
    assert _notional(out) == 500000
    # with real charges every position still gets its slot's worth (less what its charges take), never 1 share
    q = portfolio.run([{**ds(f"S{k}", b), "kind": "in_eq"} for k, b in enumerate(flat)], s, max_open=10)
    assert len(q["open_trades"]) == 10 and min(t["qty"] for t in q["open_trades"]) >= 120


def test_a_position_cut_to_the_pots_free_cash_says_so():
    # R38-003: a trade sized to the cash left (the pot tied up in the other positions) is marked, so the list can say why
    flat = [day("2026-01-05", [400.0] * 8) for _ in range(3)]
    s = S(risk={"capital": 100000, "brokerage": 0, "slippage": 0, "sizing": "capital", "perTrade": 45000})
    out = portfolio.run([ds(f"S{k}", b) for k, b in enumerate(flat)], s, max_open=3)
    qty = sorted(t["qty"] for t in out["open_trades"])
    assert qty == [26, 112, 112]                         # Rs45,000 twice (112 shares), then the Rs10,400 left: 26 shares
    assert [bool(t.get("cash_short")) for t in sorted(out["open_trades"], key=lambda t: t["qty"])] == [True, False, False]
