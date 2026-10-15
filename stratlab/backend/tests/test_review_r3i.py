"""Review 3i (engine and importers): a group's slots taken in list order, said on the verdict; the offline Pine reader
keeps the script's logic or says what it left out; a higher timeframe's "candles ago"; live and backtest agree at a
higher timeframe's close; F&O values in every run; the warm-up sized from the rules; the daily loss cap from the day's
start; a group's buy and hold with a late member; the importers' format checks; the AI builder's dropped rules; and the
smaller engine items (session end, ADX, flat RSI, India's last hour candle, cash shorts on daily candles)."""
import json
import math
import threading
import time
from datetime import date, datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest
import time_machine

from app import main  # noqa: F401  (the app's modules load in their own order; stock_futures alone loops)
from app import ai_writer, basket, importer, research, stock_futures, universes
from app.engine import portfolio, walkforward
from app.engine.core import Ctx, Engine, bar_clock
from app.engine.indicators import adx, rsi
from app.models import Ref, Strategy
from app.options import importer as oi
from tests.test_engine_intraday import cond, day, run, S

NOW = datetime(2026, 3, 2, 12, 0, tzinfo=timezone.utc)      # a Monday, after India's close


def daily(closes, d0=date(2025, 1, 6), extra=None):
    """Daily candles from closes, every calendar day (the engine doesn't mind weekends)."""
    out, prev = [], closes[0]
    for i, c in enumerate(closes):
        b = {"t": (d0 + timedelta(days=i)).isoformat(), "o": prev, "h": max(prev, c) * 1.001, "l": min(prev, c) * 0.999, "c": c, "v": 1000.0}
        if extra:
            b.update(extra(i))
        out.append(b)
        prev = c
    return out


def ds(sym, bars, start=0, kind="flat"):
    return {"inst": {"symbol": sym, "id": "X:" + sym}, "bars": bars, "start": start, "lot": 1, "kind": kind}


# ---------- 1. a group's slots: the members listed first take them, said on the verdict ----------
UP = daily([100] * 5 + [103 + 3 * i for i in range(25)])
DOWN = daily([100] * 5 + [103 - 1 * i for i in range(25)])
CROSS = Strategy(tf="1d", entry=[{"l": {"t": "price"}, "op": "xa", "r": {"t": "num", "v": 102}}], exit=[],
                 risk={"capital": 100000, "sl": 0, "brokerage": 0, "slippage": 0, "sizing": "capital", "perTrade": 100000, "maxBars": 0})


def test_same_candle_signals_take_the_slots_in_list_order_every_time():
    ab = [portfolio.run([ds("A", UP), ds("B", DOWN)], CROSS, max_open=1) for _ in range(3)]
    assert [t["symbol"] for t in ab[0]["open_trades"]] == ["A"] and ab[0]["crowded"] == 1
    assert all(o["trades"] == ab[0]["trades"] and o["open_trades"] == ab[0]["open_trades"] and o["equity"] == ab[0]["equity"] for o in ab)
    ba = portfolio.run([ds("B", DOWN), ds("A", UP)], CROSS, max_open=1)
    assert [t["symbol"] for t in ba["open_trades"]] == ["B"]          # the order is the group's: B listed first takes it
    # a free slot for each: nobody is turned away, and nothing is said
    assert portfolio.run([ds("A", UP), ds("B", DOWN)], CROSS, max_open=2)["crowded"] == 0


def test_the_verdict_says_the_members_listed_first_took_the_slots():
    out = research.run_group([ds("A", UP), ds("B", DOWN)], CROSS, {"maxOpen": 1}, 30, 30)
    line = "When more members signalled on the same candle than there were free slots, the members listed first in the group took them (1 entry found no free slot)."
    assert out["verdict"]["notes"] == [line] and out["verdict"]["summary"].endswith(line)
    assert "notes" not in research.run_group([ds("A", UP), ds("B", DOWN)], CROSS, {"maxOpen": 2}, 30, 30)["verdict"]


def test_members_load_in_the_groups_order_however_long_each_takes(monkeypatch):
    def slow_load(registry, strategy, req):
        time.sleep({"A": 0.15, "B": 0.0, "C": 0.05}[req.instrument])          # A finishes last
        return {"inst": {"id": req.instrument}}
    monkeypatch.setattr(universes, "load", slow_load)
    for _ in range(2):
        got, _ = universes.load_all(None, CROSS, ["A", "B", "C"], 30)
        assert [d["inst"]["id"] for d in got] == ["A", "B", "C"]


# ---------- 2. the offline Pine reader ----------
HEAD = '''//@version=5
strategy("T", overlay=true)
fast = ta.sma(close, 10)
slow = ta.sma(close, 30)
r = ta.rsi(close, 14)
'''
X10_30 = {"l": {"t": "sma", "p": 10}, "op": "xa", "r": {"t": "sma", "p": 30}}
U10_30 = {"l": {"t": "sma", "p": 10}, "op": "xb", "r": {"t": "sma", "p": 30}}


def rsi_rule(op, v):
    return {"l": {"t": "rsi", "p": 14}, "op": op, "r": {"t": "num", "v": float(v)}}


def test_pine_several_entry_statements_are_any_of():
    out = importer.pine(HEAD + "if ta.crossover(fast, slow)\n    strategy.entry(\"L1\", strategy.long)\nif r < 30\n    strategy.entry(\"L2\", strategy.long)\n")
    assert out["entryJoin"] == "any" and out["entry"] == [X10_30, rsi_rule("lt", 30)]


def test_pine_entry_statements_that_need_and_as_well_are_refused():
    out = importer.pine(HEAD + "if ta.crossover(fast, slow) and r < 60\n    strategy.entry(\"L1\", strategy.long)\nif r < 30\n    strategy.entry(\"L2\", strategy.long)\n")
    assert out["entry"] == [] and any("2 entry statements" in n and "left out" in n for n in out["notes"])


def test_pine_exit_with_and_is_refused_not_split():
    out = importer.pine(HEAD + "if ta.crossover(fast, slow)\n    strategy.entry(\"L\", strategy.long)\nif r > 70 and close < fast\n    strategy.close(\"L\")\n")
    assert out["entry"] == [X10_30] and out["exit"] == []
    assert any("r > 70 and close < fast" in n and "that exit was left out" in n for n in out["notes"])
    # an exit with or is any-of, as StratLab's exits are
    out = importer.pine(HEAD + "if ta.crossover(fast, slow)\n    strategy.entry(\"L\", strategy.long)\nif r > 70 or ta.crossunder(fast, slow)\n    strategy.close(\"L\")\n")
    assert out["exit"] == [rsi_rule("gt", 70), U10_30] and out["notes"] == []


def test_pine_mixed_and_or_is_refused_with_a_note():
    out = importer.pine(HEAD + "if (fast > slow and r < 70) or r < 20\n    strategy.entry(\"L\", strategy.long)\n")
    assert out["entry"] == [] and any("mix and with or" in n for n in out["notes"])
    # the same op inside brackets is no mix
    out = importer.pine(HEAD + "if (fast > slow and r < 70) and close > slow\n    strategy.entry(\"L\", strategy.long)\n")
    assert out["entryJoin"] == "all" and len(out["entry"]) == 3


def test_pine_nested_ifs_keep_the_outer_conditions():
    out = importer.pine(HEAD + "if fast > slow\n    if r < 40\n        strategy.entry(\"L\", strategy.long)\n")
    assert out["entryJoin"] == "all"
    assert out["entry"] == [{"l": {"t": "sma", "p": 10}, "op": "gt", "r": {"t": "sma", "p": 30}}, rsi_rule("lt", 40)]
    # under an else the condition is false: that can't be a rule
    out = importer.pine(HEAD + "if fast > slow\n    strategy.entry(\"L\", strategy.long)\nelse\n    strategy.close(\"L\")\n")
    assert out["entry"] == [{"l": {"t": "sma", "p": 10}, "op": "gt", "r": {"t": "sma", "p": 30}}] and out["exit"] == []
    assert any("else" in n for n in out["notes"])


def test_pine_several_statements_under_one_if_keep_its_condition():
    out = importer.pine(HEAD + '''if ta.crossover(fast, slow)
    strategy.close("S")
    strategy.entry("L", strategy.long)
if ta.crossunder(fast, slow)
    strategy.close("L")
    strategy.entry("S", strategy.short)
''')
    # the entry under the close keeps the if's condition; the close of the short closes the short, not the long
    assert out["side"] == "long" and out["entry"] == [X10_30] and out["exit"] == [U10_30]


def test_pine_nested_calls_split_on_their_own_commas():
    out = importer.pine('''//@version=5
strategy("T")
if ta.crossover(ta.sma(close, 10), ta.sma(close, 30))
    strategy.entry("L", strategy.long)
if ta.crossunder(ta.sma(close, 10), ta.sma(close, 30))
    strategy.close("L")
''')
    assert out["entry"] == [X10_30] and out["exit"] == [U10_30] and out["notes"] == []


def test_pine_at_or_above_is_read_as_above_with_a_note():
    out = importer.pine(HEAD + "if fast >= slow and r <= 60\n    strategy.entry(\"L\", strategy.long)\n")
    assert out["entry"] == [{"l": {"t": "sma", "p": 10}, "op": "gt", "r": {"t": "sma", "p": 30}}, rsi_rule("lt", 60)]
    notes = " ".join(out["notes"])
    assert '"fast >= slow" was read as "is above"' in notes and '"r <= 60" was read as "is below"' in notes
    assert 'no "at or above"' in notes and 'no "at or below"' in notes


def test_pine_settings_it_cannot_use_are_named():
    code = HEAD.replace('strategy("T", overlay=true)', 'strategy("T", overlay=true, pyramiding=3, process_orders_on_close=true, '
                                                       'commission_type=strategy.commission.percent, commission_value=0.1)')
    out = importer.pine(code + "if ta.crossover(fast, slow)\n    strategy.entry(\"L\", strategy.long)\n")
    notes = " ".join(out["notes"])
    assert "pyramiding = 3 was not imported" in notes and "process_orders_on_close was not imported" in notes
    assert "commission was not imported" in notes
    assert importer.pine(HEAD + "if ta.crossover(fast, slow)\n    strategy.entry(\"L\", strategy.long)\n")["notes"] == []


# ---------- 3. a higher timeframe's "candles ago" counts that timeframe's candles ----------
THREE_DAYS = (day("2026-01-05", [100, 101, 102, 103, 104, 105, 106, 107]) + day("2026-01-06", [110, 111, 112, 113, 114, 115, 116, 117])
              + day("2026-01-07", [120, 121, 122, 123, 124, 125, 126, 127]))


def test_yesterdays_daily_close_is_one_daily_candle_ago():
    ctx = Ctx(THREE_DAYS, True)
    ago = ctx.series(Ref(t="price", tf="1d", ago=1))
    assert list(ago[16:23]) == [107] * 7                    # on day 3, before its close: day 1's close (day 2 is yesterday's)
    assert list(ctx.series(Ref(t="price", tf="1d"))[16:23]) == [117] * 7
    assert ago[15] == 107 and np.isnan(ago[8])               # day 2's last candle closes day 2: one before it is day 1


# ---------- 4. live and backtest agree on the candle that closes a higher timeframe's candle ----------
def test_the_candle_that_closes_the_hour_reads_the_hour_live_as_in_the_backtest():
    bars = day("2026-01-05", [100, 101, 102, 103, 104, 105, 106, 107])
    full = Ctx(bars, True).series(Ref(t="price", tf="1h"))
    for n in range(1, len(bars) + 1):                        # live: the newest closed candle is the last row
        live = Ctx(bars[:n], True, base_min=15).series(Ref(t="price", tf="1h"))
        assert (np.isnan(live[-1]) and np.isnan(full[n - 1])) or live[-1] == full[n - 1], n
    assert full[3] == 103


def test_the_days_last_candle_closes_the_day_live_as_in_the_backtest():
    full = Ctx(THREE_DAYS, True).series(Ref(t="price", tf="1d"))
    live = Ctx(THREE_DAYS[:16], True, base_min=15).series(Ref(t="price", tf="1d"))
    assert live[15] == full[15] == 117                       # the session is over at day 2's last candle
    assert Ctx(THREE_DAYS[:15], True, base_min=15).series(Ref(t="price", tf="1d"))[14] == full[14] == 107


# ---------- 5. F&O values in a group, the walk-forward and the similar-instruments check ----------
FO_STRAT = Strategy(tf="1d", entry=[{"l": {"t": "oi_change_pct"}, "op": "gt", "r": {"t": "num", "v": 0}},
                                    {"l": {"t": "price"}, "op": "gt", "r": {"t": "sma", "p": 5}}],
                    exit=[{"l": {"t": "price"}, "op": "lt", "r": {"t": "sma", "p": 5}}], risk={"capital": 100000, "sl": 0})


class FakeProv:
    max_days = {"1d": 3650, "15m": 365}

    def __init__(self, bars):
        self.bars, self.asked = bars, []

    def ready(self):
        return True

    @staticmethod
    def warmup_days(tf, candles=210):
        return math.ceil(candles * 7 / 5) + 10 if tf == "1d" else math.ceil(candles / 25 * 7 / 5) + 3

    def history(self, inst, tf, days):
        self.asked.append((tf, days))
        return self.bars


class FakeReg:
    def __init__(self, prov):
        self.prov = prov

    def resolve(self, iid):
        return self.prov, {"id": iid, "symbol": iid.split(":")[1], "market": "IN", "type": "EQ", "exchange": "NSE", "lot": 1}

    def provider(self, market):
        return self.prov


def weekdays(n, end=date(2026, 2, 27)):
    out, d = [], end
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d -= timedelta(days=1)
    return out[::-1]


def fo_bars():
    return [{"t": f"{d.isoformat()}T00:00:00+05:30", "o": 100 + i % 20, "h": 101 + i % 20, "l": 99 + i % 20, "c": 100 + i % 20, "v": 1000.0}
            for i, d in enumerate(weekdays(420))]


@pytest.fixture
def stored_fo(monkeypatch):
    """The stored F&O facts by day: open interest rising every day."""
    def enrich(symbol, bars):
        return [{**b, "fo_oi": 1000 + 10 * i, "fo_near": 800, "fo_fut": b["c"] + 1, "fo_spot": b["c"]} for i, b in enumerate(bars)]
    monkeypatch.setattr(stock_futures, "enrich", enrich)
    with time_machine.travel(NOW, tick=False):
        yield


def test_a_group_with_an_oi_rule_trades(stored_fo):
    reg = FakeReg(FakeProv(fo_bars()))
    datasets, problems = universes.load_all(reg, FO_STRAT, ["IN:1", "IN:2"], 365)
    assert problems == [] and all("fo_oi" in d["bars"][-1] for d in datasets)
    out = research.run_group(datasets, FO_STRAT, {"maxOpen": 2}, 365, 3650)
    assert len(out["trades"]) > 0


def test_the_walk_forward_and_the_similar_instruments_read_the_oi_rule(stored_fo):
    reg = FakeReg(FakeProv(fo_bars()))
    data = research.load(reg, FO_STRAT, basket._Req("IN:1", 365))
    wf = walkforward.run(data["bars"], FO_STRAT, data["start"], data["lot"], data["kind"])
    assert wf["status"] != "skip" and sum(w["trades"] for w in wf["windows"]) > 0
    assert basket._one(reg, FO_STRAT, "IN:1", 365)["n"] > 0


# ---------- 6. the warm-up sized from the rules ----------
def strat(tf, *refs):
    return Strategy(tf=tf, entry=[{"l": {"t": "price"}, "op": "gt", "r": r} for r in refs], exit=[])


def test_warm_up_from_the_longest_rule():
    assert research.warmup_need(strat("1d", {"t": "ema", "p": 20})) == (200, 0)              # never under 200
    assert research.warmup_need(strat("1d", {"t": "sma", "p": 300})) == (320, 0)
    assert research.warmup_need(strat("1d", {"t": "dc_upper", "p": 252, "ago": 3})) == (275, 0)
    assert research.warmup_need(strat("15m", {"t": "sma", "p": 100, "tf": "1h"})) == (420, 0)   # 4 candles an hour
    assert research.warmup_need(strat("15m", {"t": "sma", "p": 50, "tf": "1d"})) == (200, 70)   # days, for a daily rule
    assert research.warmup_need(strat("5m", {"t": "sma", "p": 500, "tf": "1h"})) == (research.WARMUP_CAP, 0)


def test_the_history_asked_for_covers_the_rule_and_short_warm_up_is_flagged(stored_fo):
    prov = FakeProv(fo_bars())
    long_rule = strat("1d", {"t": "sma", "p": 300})
    data = research.load(FakeReg(prov), long_rule, basket._Req("IN:1", 365))
    assert prov.asked[-1] == ("1d", 365 + FakeProv.warmup_days("1d", 330))
    assert data["warmup"] == 320
    out = research.run(long_rule, data)
    assert out["warmup_short"] is (data["start"] < 320)
    assert research.run(long_rule, {**data, "start": 250})["warmup_short"] is True
    assert research.run(strat("1d", {"t": "sma", "p": 20}), {**data, "start": 250, "warmup": 200})["warmup_short"] is False


def test_a_daily_rule_on_intraday_candles_short_of_history_is_noted():
    bars = THREE_DAYS * 1
    s = strat("15m", {"t": "sma", "p": 50, "tf": "1d"})
    data = {"inst": {"id": "CSV:upload"}, "bars": bars, "start": 16, "lot": 1, "kind": "flat", "days": 1, "max_days": 1,
            "warmup": 200, "warmup_days": 70}
    notes = research.run_notes(s, data)
    assert notes == ["A rule on daily candles needs 70 days of history before the test starts; the 15-minute candles "
                     "available reached back 2 days, so that rule had no value on the test's first 68 trading days."]
    assert research.run_notes(s, {**data, "warmup_days": 2}) == []


# ---------- 7. the daily loss cap counts the day's loss, from the previous close ----------
TWO_DAYS = day("2026-01-05", [100, 100, 100, 98.5, 98.2, 98.2, 98.2, 98.2]) + day("2026-01-06", [98.2, 98.2, 97.3, 97.3, 97.3, 97.3, 97.3, 97.3])
CAP_RISK = {"capital": 100000, "sl": 0, "tgt": 0, "brokerage": 0, "slippage": 0, "sizing": "capital", "perTrade": 100000}


def test_yesterdays_loss_does_not_count_toward_todays_cap():
    s = S(entry=[cond({"t": "price"}, "gt", {"t": "num", "v": 0})], exit=[], session={"dailyLossPct": 2.5}, risk=CAP_RISK)
    eng, _ = run(s, TWO_DAYS)
    assert [e["why"] for e in eng.events] == ["Entry rule"]          # -1.8% on day 1, -0.9% on day 2: neither reaches 2.5%
    # a day's own fall past the cap still closes it
    eng, _ = run(S(entry=s.entry, exit=[], session={"dailyLossPct": 0.8}, risk=CAP_RISK), TWO_DAYS)
    closes = [e for e in eng.events if e["why"] == "Daily loss cap"]
    assert len(closes) == 2 and closes[0]["t"].startswith("2026-01-05") and closes[1]["t"].startswith("2026-01-06T09:45")


def test_a_groups_cap_counts_the_days_loss_from_the_previous_close():
    s = S(entry=[cond({"t": "price"}, "gt", {"t": "num", "v": 0})], exit=[], session={"dailyLossPct": 2.5},
          risk={**CAP_RISK, "perTrade": 50000})
    other = day("2026-01-05", [100, 100, 100, 98.5, 98.2, 98.2, 98.2, 98.2]) + day("2026-01-06", [98.2, 98.2, 97.3, 97.3, 97.3, 97.3, 97.3, 97.3])
    out = portfolio.run([ds("A", TWO_DAYS), ds("B", other)], s, max_open=2)
    assert all(t["why"] != "Daily loss cap" for t in out["trades"]) and len(out["open_trades"]) == 2


# ---------- 8. a group's buy and hold with a member that starts late ----------
def test_group_buy_and_hold_buys_a_late_member_with_its_share():
    a = daily([100 * (1.01 ** i) for i in range(60)])
    b = daily([50.0] * 30, d0=date(2025, 1, 6) + timedelta(days=30))
    none = Strategy(tf="1d", entry=[{"l": {"t": "price"}, "op": "gt", "r": {"t": "num", "v": 10 ** 9}}], risk={"capital": 100000, "sl": 0})
    out = portfolio.run([ds("A", a), ds("B", b)], none, max_open=2)
    h, t = out["buy_hold"], out["times"]
    i = t.index(b[1]["t"] + "T00:00:00") if b[1]["t"] + "T00:00:00" in t else next(k for k, x in enumerate(t) if x.startswith(b[1]["t"]))
    # half the capital in A from its start, half waiting until B starts, then in B (flat): no jump on B's first day
    for k in (i - 1, i, i + 1):
        want = 50000 * a[k + 1]["c"] / a[1]["c"] + 50000
        assert h[k] == pytest.approx(want, rel=1e-6)


# ---------- 9. the options importer reads detect()'s own name for plain words ----------
def test_an_options_idea_in_plain_words_is_recognised_with_detects_format():
    text = "Sell a short straddle on NIFTY at 9:20 with 30% stop"
    fmt = importer.detect(text, "")
    assert fmt == "text" and oi.is_options(text, fmt)
    assert not oi.is_options("Buy RELIANCE when the 20 EMA crosses the 50 EMA; atm call", importer.detect("x = 1", "a.py"))


# ---------- 10. detect: the extension first, an export only when it holds a strategy ----------
def test_detect_reads_the_extension_first_and_guards_the_json():
    py = 'import pandas as pd\nimport ta\ndef strategy(df):\n    df["rsi"] = ta.momentum.rsi(df.close, 14)\n    return df\n'
    assert importer.detect(py, "my.py") == "python"
    assert importer.detect("import pandas as pd\ndef strategy(df):\n    return df\n", "") == "python"
    assert importer.detect("anything at all", "a.MQ5") == "mql" and importer.detect("Buy = 1;", "x.afl") == "afl"
    assert importer.detect('{"format": 3, "strategy": {"entry": []}}') == "stratlab"         # a number for the format
    assert importer.detect('{"format": 3}') == "json"
    assert importer.detect('{"strategy": "golden cross"}') == "json"                          # a word, not an export
    assert importer.detect('{"format": "stratlab-strategy-v1"}') == "stratlab"
    assert importer.detect("[1, 2]") == "text"


# ---------- 11. the AI builder says what it dropped ----------
def test_ai_writer_notes_every_rule_it_drops(monkeypatch):
    good = {"l": {"t": "rsi", "p": 14}, "op": "lt", "r": {"t": "num", "v": 30}}
    reply = {"entry": [good, {"l": {"t": "made_up"}, "op": "gt", "r": {"t": "num", "v": 1}}] + [good] * 11,
             "exit": [], "side": "long", "shortEntry": [good], "shortExit": [good]}
    monkeypatch.setattr(ai_writer, "complete", lambda *a, **k: json.dumps(reply))
    out = ai_writer.write_strategy("x", pro=True)
    notes = " ".join(out["notes"])
    assert len(out["entry"]) == 10 and out["shortEntry"] == []
    assert "One entry rule couldn't be read" in notes and "made_up" in notes
    assert "Only the first 10 of the 12 entry rules were kept." in notes
    assert "The short rules were left out" in notes
    reply2 = {"entry": [good], "exit": [], "side": "both", "shortEntry": [], "shortExit": [good]}
    monkeypatch.setattr(ai_writer, "complete", lambda *a, **k: json.dumps(reply2))
    out = ai_writer.write_strategy("x", pro=True)
    assert out["side"] == "long" and "short exit rules were left out" in " ".join(out["notes"])


# ---------- 12. smaller engine items ----------
def test_a_signal_on_the_candle_closing_at_the_session_end_fills_as_live():
    prices = [100, 100, 100, 101, 101, 101, 101, 101]           # crosses on the 10:00 candle, which closes at 10:15
    got = {}
    for end in ("10:00", "10:15", ""):
        eng, _ = run(S(entry=[cond({"t": "price"}, "xa", {"t": "num", "v": 100.5})], session={"end": end} if end else {}),
                     day("2026-01-05", prices))
        got[end] = [e["t"][11:16] for e in eng.events if e["side"] == "buy"]
    # live enters at 10:15, when that candle closes: allowed with the last entry at 10:15, not at 10:00
    assert got == {"10:00": [], "10:15": ["10:15"], "": ["10:15"]}


def test_adx_is_blank_until_it_has_its_candles_and_rsi_of_a_flat_series_is_50():
    df = pd.DataFrame({"h": np.arange(40) + 1.0, "l": np.arange(40) - 1.0, "c": np.arange(40) * 1.0})
    a = adx(df, 14)
    assert a.iloc[:26].isna().all() and a.iloc[26] == pytest.approx(100)
    assert rsi(pd.Series([100.0] * 30), 14).iloc[14:].tolist() == [50.0] * 16
    assert rsi(pd.Series([100.0 + i for i in range(30)]), 14).iloc[-1] == 100.0


def test_indias_last_hour_candle_closes_at_15_30():
    eng = Engine(Strategy(tf="1h", entry=[], exit=[]), cost_kind="in_eq")
    assert bar_clock("2026-01-05T15:15:00+05:30", 60, eng.close_min) == ("2026-01-05", 15 * 60 + 30)
    assert bar_clock("2026-01-05T14:15:00+05:30", 60, eng.close_min) == ("2026-01-05", 15 * 60 + 15)
    assert Engine(Strategy(tf="1h", entry=[], exit=[]), cost_kind="us").close_min is None
    assert bar_clock("2026-01-05T15:15:00+05:30", 60) == ("2026-01-05", 16 * 60 + 15)


def test_an_indian_cash_short_on_daily_candles_is_noted():
    bars = daily([100 - 0.2 * i for i in range(80)])
    short = Strategy(tf="1d", side="short", entry=[{"l": {"t": "price"}, "op": "lt", "r": {"t": "sma", "p": 5}}], exit=[],
                     risk={"capital": 100000, "sl": 0})
    data = {"inst": {"id": "IN:1", "symbol": "X", "market": "IN"}, "bars": bars, "start": 20, "lot": 1, "kind": "in_eq",
            "days": 60, "max_days": 3650}
    note = ("Indian shares can be sold short only within the day (intraday); this test held its shorts on daily candles, "
            "overnight, which the cash market does not allow.")
    assert note in research.run(short, data)["verdict"]["notes"]
    assert "notes" not in research.run(short, {**data, "kind": "in_fut"})["verdict"]


# ---------- 13. a same-day rerun on intraday candles once newer candles have closed ----------
def test_an_intraday_rerun_is_refused_only_until_a_new_candle_closes():
    s = Strategy(tf="15m", entry=[{"l": {"t": "price"}, "op": "gt", "r": {"t": "num", "v": 1}}], exit=[])
    last = {"v": 3, "created_at": "2026-03-02T05:00:00+00:00", "strategy": s.model_dump(), "instrument": {"id": "IN:1", "market": "IN"},
            "days": 30, "req_days": 30, "range": {"from": "2026-02-01T09:15:00+05:30", "to": "2026-03-02T10:15:00+05:30"}}
    # the 10:15 candle's run: the 10:30 candle closes at 10:45 IST (05:15 UTC)
    assert research.unchanged([last], s, "IN:1", 30, "2026-03-02T05:14:00+00:00") == 3
    assert research.unchanged([last], s, "IN:1", 30, "2026-03-02T05:15:00+00:00") is None
    # after the close: the 15:15 candle was the day's last, so a rerun that evening repeats it
    eod = {**last, "range": {**last["range"], "to": "2026-03-02T15:15:00+05:30"}}
    assert research.unchanged([eod], s, "IN:1", 30, "2026-03-02T15:00:00+00:00") == 3
    daily_s = Strategy(**{**s.model_dump(), "tf": "1d"})
    assert research.unchanged([{**last, "strategy": daily_s.model_dump()}], daily_s, "IN:1", 30, "2026-03-02T09:00:00+00:00") == 3
