from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
import time_machine

from app import live
from app.data import Registry
from app.data.coinbase import CoinbaseProvider
from app.kite_service import KiteService, TickHub
from tests.test_notebooks import EMA, wavy_coinbase


@pytest.fixture(autouse=True)
def pinned_clock():
    """The candles below are dated 12 Oct 2026 from 09:30 UTC; the clock is pinned to that afternoon so they have closed
    whatever the real date and time are."""
    with time_machine.travel(datetime(2026, 10, 12, 15, 0, tzinfo=timezone.utc), tick=False):
        yield


def make_manager():
    kite = KiteService()
    reg = Registry(kite, CoinbaseProvider(transport=wavy_coinbase()))
    return live.LiveManager(kite, TickHub(kite), reg), reg


def test_crypto_session_polls_closed_candles(monkeypatch):
    mgr, reg = make_manager()
    inst = reg.resolve("CRYPTO:BTC-USD")[1]
    row = {"id": "s1", "user_id": "u", "name": "BTC trend", "strategy": {**EMA, "tf": "5m"}, "instrument": inst,
           "started_at": datetime.now(timezone.utc).isoformat()}
    s = live.LiveSession(mgr, row)
    assert s.polled and s.engine.qty_step == 1e-8 and s.engine.kind == "crypto"
    # every bar it starts from has closed
    assert all(live._closed(b, "5m") for b in s.bars)

    # a new closed candle shows up on the next poll
    newer = {"t": "2999-01-01T00:00:00+00:00", "o": 1, "h": 1, "l": 1, "c": 1, "v": 0}
    monkeypatch.setattr(s.prov, "closed_candles", lambda inst, tf, since: [newer])
    n = len(s.bars)
    s.on_timer(datetime.now(timezone.utc))
    assert len(s.bars) == n + 1 and s.bars[-1] is newer
    assert s.last_price == 30000 and s.poll_ok
    snap = s.snapshot()
    assert snap["feed_connected"] is True and snap["forming"] is None
    # no second poll within the interval
    s.on_timer(datetime.now(timezone.utc))
    assert len(s.bars) == n + 1


def test_india_sessions_wait_for_kite_login(monkeypatch):
    mgr, _ = make_manager()
    attached = []
    monkeypatch.setattr(live.db, "running_sessions", lambda: [
        {"id": "a", "instrument": {"market": "IN", "token": 1}},
        {"id": "b", "instrument": {"market": "CRYPTO"}},
    ])
    monkeypatch.setattr(mgr, "_attach", lambda row: attached.append(row["id"]))
    mgr.resume()
    assert attached == ["b"]   # India waits: Kite isn't logged in


def test_a_transient_error_resuming_leaves_the_session_running_and_a_permanent_one_stops_it(monkeypatch):
    mgr, _ = make_manager()
    writes = []
    monkeypatch.setattr(live.db, "update_session", lambda sid, **f: writes.append((sid, f)))
    rows = [{"id": "a", "instrument": {"market": "CRYPTO"}}]
    fail = [RuntimeError("503 service unavailable")]

    def attach(row):
        if fail:
            raise fail[0]
    monkeypatch.setattr(mgr, "_attach", attach)
    for _ in range(live.RESUME_TRIES - 1):
        mgr.resume(rows)
    assert writes == []                         # still running: the next reconcile tries again
    fail.clear()
    mgr.resume(rows)                            # it attaches: the count starts over
    fail.append(RuntimeError("timeout"))
    for _ in range(live.RESUME_TRIES - 1):
        mgr.resume(rows)
    assert writes == []
    mgr.resume(rows)                            # the tenth failure in a row stops it, with the reason
    assert len(writes) == 1 and writes[0][0] == "a" and writes[0][1]["status"] == "stopped"
    assert "10 tries" in writes[0][1]["stop_reason"] and "timeout" in writes[0][1]["stop_reason"]
    # what the builders raise for good stops it at once
    writes.clear()
    fail[:] = [ValueError("That market isn't connected.")]
    mgr.resume(rows)
    assert len(writes) == 1 and writes[0][1]["stop_reason"] == "Could not resume after restart: That market isn't connected."


def test_a_manual_paper_order_is_stamped_in_the_markets_own_zone(monkeypatch):
    """A US position opened at 15:00 New York is dated the 13th in India (00:30 IST), but its candles are dated the 12th:
    stamped in India's zone it looked a day old and was squared off at the next candle's open."""
    from zoneinfo import ZoneInfo
    from app.engine.core import Ctx
    mgr, reg = make_manager()
    strat = {**STOP1, "session": {"start": "09:30", "end": "15:30", "squareoff": "15:55"}}
    row = {"id": "s1", "user_id": "u", "name": "US", "strategy": strat, "instrument": reg.resolve("CRYPTO:BTC-USD")[1],
           "started_at": "2026-10-12T09:00:00+00:00"}
    with time_machine.travel(datetime(2026, 10, 12, 19, 0, tzinfo=timezone.utc), tick=False):     # 15:00 in New York, 00:30 the next day in India
        s = live.LiveSession(mgr, row)
        assert s._stamp() == "2026-10-12T19:00:00+00:00"                  # a coin's candles are in UTC
        s.inst = {**s.inst, "tz": "America/New_York", "market": "US"}
        s.market = "US"
        assert s._stamp() == "2026-10-12T15:00:00-04:00"
        ny = ZoneInfo("America/New_York")
        bars = [{"t": datetime(2026, 10, 12, 15, m, tzinfo=ny).isoformat(), "o": 100.0, "h": 100.0, "l": 100.0, "c": 100.0, "v": 1}
                for m in (0, 5)]
        s.engine.open_manual(s._stamp(), 100.0, 1, 10, "by hand")
        s.engine.step(bars, Ctx(bars, intraday=True), 1)                  # the next candle, still the same trading day
    assert s.engine.qty == 10 and not s.engine.trades


# ---------- restarts: the state is saved with each order, and candles closed while down are caught up on ----------
STOP1 = {"name": "Always in", "tf": "5m", "side": "long", "entryJoin": "all",
         "entry": [{"l": {"t": "price"}, "op": "gt", "r": {"t": "num", "v": 1}}], "exit": [],
         "risk": {"capital": 10000, "riskPct": 1, "maxAlloc": 100, "sl": 1, "sizing": "capital", "perTrade": 5000,
                  "leverage": 1, "brokerage": 0, "slippage": 0}}


def bar5(i, c=100.0, lo=None):
    t = datetime(2026, 10, 12, 9, 30, tzinfo=timezone.utc).timestamp() + i * 300
    return {"t": datetime.fromtimestamp(t, timezone.utc).isoformat(), "o": c, "h": c, "l": lo or c, "c": c, "v": 1}


class Now:
    """Runs a background thread at once, so its writes can be checked."""
    def __init__(self, target, daemon=None):
        self.target = target

    def start(self):
        self.target()


def run_threads_now(monkeypatch):
    import threading
    monkeypatch.setattr(live, "threading", SimpleNamespace(Thread=Now, Lock=threading.Lock))


def offline_world(monkeypatch, mgr, history):
    calls = []
    prov = mgr.markets.provider("CRYPTO")
    monkeypatch.setattr(prov, "history", lambda inst, tf, days, ttl=None: list(history))
    run_threads_now(monkeypatch)
    monkeypatch.setattr(live.db, "get_profile", lambda uid: {"id": uid, "alerts_enabled": True})
    monkeypatch.setattr(live, "alerts_on", lambda p: True)
    monkeypatch.setattr(live, "notify", lambda p, subj, body, **k: calls.append(("alert", subj, body)))
    monkeypatch.setattr(live.db, "add_order", lambda o: calls.append(("order", o["side"], o["reason"])))
    monkeypatch.setattr(live.db, "update_session", lambda sid, **k: calls.append(("save", k.get("state"))))
    return calls


def test_an_order_saves_the_session_before_it_is_logged_or_alerted(monkeypatch):
    mgr, reg = make_manager()
    calls = offline_world(monkeypatch, mgr, [bar5(i) for i in range(40)])
    row = {"id": "s1", "user_id": "u", "name": "Always in", "strategy": STOP1, "instrument": reg.resolve("CRYPTO:BTC-USD")[1],
           "started_at": "2026-10-12T09:00:00+00:00"}
    s = mgr._attach(row)
    s._on_candle(bar5(40))
    assert [c[0] for c in calls] == ["save", "alert"]          # saved at once, not up to 30 seconds later (a coin's
    # fractional quantity isn't in the whole-number orders table)
    assert calls[0][1]["qty"] > 0 and calls[0][1]["last_bar_t"] == bar5(40)["t"]


def test_a_restart_runs_the_candles_that_closed_while_the_server_was_down(monkeypatch):
    mgr, reg = make_manager()
    hist = [bar5(i) for i in range(40)]
    offline_world(monkeypatch, mgr, hist)
    row = {"id": "s1", "user_id": "u", "name": "Always in", "strategy": STOP1, "instrument": reg.resolve("CRYPTO:BTC-USD")[1],
           "started_at": "2026-10-12T09:00:00+00:00"}
    s = live.LiveSession(mgr, row)
    assert not s.engine.events                        # a new session runs no history
    s._on_candle(bar5(40))
    assert s.engine.qty > 0 and s.engine.sl == 99.0
    saved = s.state()
    # down for three candles: the second one's low crosses the stop; the history now reaches past the saved candle
    calls = offline_world(monkeypatch, mgr, hist + [bar5(40), bar5(41), bar5(42, lo=98.0), bar5(43)])
    mgr.sessions["s1"] = s2 = live.LiveSession(mgr, {**row, "state": saved})
    e = s2.engine
    stop = next(t for t in e.trades if t["why"] == "Stop loss")
    assert stop["exit_t"] == bar5(42)["t"] and stop["exit"] == 99.0
    # the 10:00 candle saved before the restart isn't run again: one entry before it, one after the stop
    assert [ev["t"] for ev in e.events if ev["side"] == "buy"] == [bar5(40)["t"], bar5(43)["t"]]
    assert s2.bars[-1]["t"] == bar5(43)["t"] and s2.state()["last_bar_t"] == bar5(43)["t"]
    alerts = [c for c in calls if c[0] == "alert"]               # one alert for the caught-up orders, not one each
    assert len(alerts) == 1 and "2 paper trades while offline" in alerts[0][1]
    assert "SELL" in alerts[0][2] and "Stop loss" in alerts[0][2] and "Entry rule" in alerts[0][2]
    # restarting again from the caught-up state runs nothing more
    calls.clear()
    s3 = live.LiveSession(mgr, {**row, "state": s2.state()})
    assert len(s3.engine.events) == len(e.events) and not [c for c in calls if c[0] == "alert"]


def test_a_poll_without_a_price_leaves_the_last_one_ageing(monkeypatch):
    mgr, reg = make_manager()
    offline_world(monkeypatch, mgr, [bar5(i) for i in range(40)])
    row = {"id": "s1", "user_id": "u", "name": "Always in", "strategy": STOP1, "instrument": reg.resolve("CRYPTO:BTC-USD")[1],
           "started_at": "2026-10-12T09:00:00+00:00"}
    s = live.LiveSession(mgr, row)
    monkeypatch.setattr(s.prov, "closed_candles", lambda inst, tf, since: [])
    monkeypatch.setattr(s.prov, "ltp", lambda inst: None)
    s.on_timer(datetime.now(timezone.utc))
    assert s.poll_ok and s.last_tick_at is None                   # no price came, so none is fresh
    monkeypatch.setattr(s.prov, "ltp", lambda inst: 101.0)
    s.next_poll = 0
    s.on_timer(datetime.now(timezone.utc))
    assert s.last_price == 101.0 and s.last_tick_at


def test_a_tick_is_as_fresh_as_its_own_time():
    from app.kite_service import IST
    now = datetime.now(IST)
    old = now.replace(microsecond=0) - live.timedelta(days=1)
    assert live.tick_time(old) == old.isoformat()                 # yesterday's close sent on subscribe stays yesterday's
    assert datetime.fromisoformat(live.tick_time(now + live.timedelta(seconds=5))) <= datetime.now(IST)   # never ahead


# ---------- corporate actions on an open position (corp_actions.PaperActions) ----------
CORP = {**STOP1, "risk": {**STOP1["risk"], "capital": 100000, "perTrade": 10000}}
SPLIT = {"id": "ACME|split|2026-01-06|2:1", "symbol": "ACME", "kind": "split", "label": "Split", "factor": 2.0, "ex_date": "2026-01-06"}
BONUS = {"id": "ACME|bonus|2026-01-06|1:3", "symbol": "ACME", "kind": "bonus", "label": "Bonus 1:3", "ratio": [1, 3],
         "factor": 4 / 3, "ex_date": "2026-01-06"}
DIV = {"id": "ACME|dividend|2026-01-06|dividend", "symbol": "ACME", "kind": "dividend", "label": "Dividend", "amount": 5.0,
       "ex_date": "2026-01-06"}


def sbar(day, i, c, lo=None):
    t = datetime(2026, 1, day, 14, 30, tzinfo=timezone.utc).timestamp() + i * 300
    return {"t": datetime.fromtimestamp(t, timezone.utc).isoformat(), "o": c, "h": c, "l": lo or c, "c": c, "v": 10}


def stock_world(monkeypatch, history, acts, symbol="ACME"):
    """A US stock paper session on a fake feed, with `acts` as the stored corporate actions (no network: asserted)."""
    from app import corp_actions
    from app.intel.net import TTLCache
    mgr, reg = make_manager()
    prov = reg.provider("CRYPTO")
    monkeypatch.setitem(reg.providers, "US", prov)
    monkeypatch.setattr(prov, "history", lambda inst, tf, days, ttl=None: [dict(b) for b in history])
    monkeypatch.setattr(corp_actions, "_paper", TTLCache())

    def stored(region, sym, sources=None, today=None, fetch=True, **k):
        assert sources is None and not fetch and region == "US"
        return [a for a in acts if a["symbol"] == sym]
    monkeypatch.setattr(corp_actions, "actions_for", stored)
    inst = {**reg.resolve("CRYPTO:BTC-USD")[1], "id": f"US:{symbol}", "symbol": symbol, "market": "US", "type": "EQ", "step": 1}
    row = {"id": "s1", "user_id": "u", "name": "Always in", "strategy": CORP, "instrument": inst, "started_at": "2026-01-05T09:00:00+00:00"}
    return mgr, row


def corp_events(e):
    return [ev for ev in e.events if ev.get("kind") == "corp"]


def test_a_split_rescales_the_open_long_and_its_stop_without_a_false_stop_out(monkeypatch):
    mgr, row = stock_world(monkeypatch, [sbar(5, i, 1000.0) for i in range(40)], [SPLIT])
    s = live.LiveSession(mgr, row)
    s._on_candle(sbar(5, 40, 1000.0))
    e = s.engine
    assert (e.qty, e.entry, e.sl) == (10, 1000.0, 990.0)
    cash = e.cash
    # the first candle after the ex-date is in the new prices (the feed's older candles aren't: the jump says so)
    s._on_candle(sbar(6, 0, 500.0, lo=496.0))
    assert (e.qty, e.entry, e.sl, e.best, e.init_sl) == (20, 500.0, 495.0, 500.0, 495.0)
    assert not e.trades and e.cash == cash                     # no stop-out at 496, no cash for a whole split
    assert [ev["why"] for ev in corp_events(e)] == ["Split 1:2 applied: 10 shares at $1,000 are now 20 at $500"]
    assert s.bars[0]["c"] == 500.0 and s.bars[-2]["c"] == 500.0 and s.bars[0]["v"] == 20
    assert e.equity(500.0) == cash + 20 * 500.0
    assert s.state()["corp_applied"] == [SPLIT["id"]]
    assert "side" not in corp_events(e)[0]                     # a log line, not an order


def test_a_bonus_pays_the_fractional_share_in_cash(monkeypatch):
    mgr, row = stock_world(monkeypatch, [sbar(5, i, 1000.0) for i in range(40)], [BONUS])
    s = live.LiveSession(mgr, row)
    s._on_candle(sbar(5, 40, 1000.0))
    e, cash = s.engine, s.engine.cash
    s.last_price = 1000.0
    s._corp_day("2026-01-06", timer=True)                     # the day's check, before its first candle
    # 10 shares with 1 new for every 3 held: 13.33, so 13 shares and a third of one paid at the adjusted 750
    assert e.qty == 13 and e.entry == 750.0 and e.sl == 742.5 and s.last_price == 750.0
    assert round(e.cash - cash, 2) == 250.0
    assert corp_events(e)[0]["why"] == ("Bonus 1:3 applied: 10 shares at $1,000 are now 13 at $750, "
                                        "$250 paid for the fractional share")
    s._corp_day("2026-01-06", timer=True)                     # once a day
    assert len(corp_events(e)) == 1


def test_a_dividend_is_paid_to_a_long_and_by_a_short(monkeypatch):
    for side, sign, word in (("long", 1, "credited for {} shares"), ("short", -1, "paid for {} shares short")):
        mgr, row = stock_world(monkeypatch, [sbar(5, i, 1000.0) for i in range(40)], [DIV])
        s = live.LiveSession(mgr, {**row, "strategy": {**CORP, "side": side}})
        s._on_candle(sbar(5, 40, 1000.0))
        e, cash, q = s.engine, s.engine.cash, s.engine.qty
        assert q > 0 and e.dir == sign
        s._on_candle(sbar(6, 0, 995.0))
        assert e.cash == cash + sign * 5.0 * q and e.qty == q and e.entry == 1000.0
        assert corp_events(e)[0]["why"] == f"Dividend $5 a share: ${5 * q} " + word.format(q)


def test_an_action_is_applied_once_across_restarts(monkeypatch):
    day1 = [sbar(5, i, 1000.0) for i in range(41)]
    mgr, row = stock_world(monkeypatch, day1[:40], [SPLIT])
    s = live.LiveSession(mgr, row)
    s._on_candle(day1[40])
    s._on_candle(sbar(6, 0, 500.0))
    saved = s.state()
    # the broker's intraday candles aren't adjusted, Yahoo's are: either way the position stays as it is
    for hist in (day1 + [sbar(6, 0, 500.0)], [{**b, "o": 500.0, "h": 500.0, "l": 500.0, "c": 500.0} for b in day1] + [sbar(6, 0, 500.0)]):
        mgr, row = stock_world(monkeypatch, hist, [SPLIT])
        s2 = live.LiveSession(mgr, {**row, "state": saved})
        s2._on_candle(sbar(6, 1, 500.0))
        e = s2.engine
        assert (e.qty, e.entry, e.sl) == (20, 500.0, 495.0) and not e.trades and len(corp_events(e)) == 1
        assert all(b["c"] == 500.0 for b in s2.bars)


def test_a_split_while_the_server_was_down_is_applied_before_the_missed_candles(monkeypatch):
    day1 = [sbar(5, i, 1000.0) for i in range(41)]
    mgr, row = stock_world(monkeypatch, day1[:40], [SPLIT])
    s = live.LiveSession(mgr, row)
    s._on_candle(day1[40])
    saved = s.state()
    assert "corp_applied" in saved and not saved["corp_applied"]
    # back the next day: the feed's history is adjusted back in time, and two candles closed while down
    adj = [{**b, "o": 500.0, "h": 500.0, "l": 500.0, "c": 500.0} for b in day1]
    mgr, row = stock_world(monkeypatch, adj + [sbar(6, 0, 500.0, lo=497.0), sbar(6, 1, 501.0)], [SPLIT])
    s2 = live.LiveSession(mgr, {**row, "state": saved})
    e = s2.engine
    assert (e.qty, e.entry, e.sl) == (20, 500.0, 495.0) and not e.trades and s2.dirty
    assert s2.bars[-1]["c"] == 501.0 and len(corp_events(e)) == 1


def test_futures_options_commodities_and_crypto_are_left_alone(monkeypatch):
    from app import corp_actions
    assert corp_actions.paper_region({"market": "IN", "type": "EQ", "exchange": "NSE"}) == "IN"
    assert corp_actions.paper_region({"market": "US", "type": "ETF"}) == "US"
    for inst in ({"market": "IN", "fno": True, "exchange": "NFO", "type": "FUT"}, {"market": "IN", "exchange": "NFO", "type": "CE"},
                 {"market": "MCX", "type": "FUT"}, {"market": "CDS", "type": "FUT"}, {"market": "CRYPTO", "type": "CRYPTO"},
                 {"market": "IN", "type": "INDEX"}):
        assert corp_actions.paper_region(inst) is None
    # a coin session never looks actions up, so a row under its symbol changes nothing
    mgr, reg = make_manager()
    monkeypatch.setattr(mgr.markets.provider("CRYPTO"), "history", lambda inst, tf, days, ttl=None: [sbar(5, i, 1000.0) for i in range(40)])
    monkeypatch.setattr(corp_actions, "actions_for", lambda *a, **k: (_ for _ in ()).throw(AssertionError("looked up")))
    row = {"id": "c1", "user_id": "u", "name": "Coin", "strategy": CORP, "instrument": reg.resolve("CRYPTO:BTC-USD")[1],
           "started_at": "2026-01-05T09:00:00+00:00"}
    s = live.LiveSession(mgr, row)
    s._on_candle(sbar(5, 40, 1000.0))
    q = s.engine.qty
    s._on_candle(sbar(6, 0, 1000.0))
    assert s.engine.qty == q and not corp_events(s.engine)


def test_a_long_catch_up_alert_lists_20_orders_and_counts_the_rest(monkeypatch):
    from types import SimpleNamespace
    mgr, reg = make_manager()
    calls = offline_world(monkeypatch, mgr, [])
    s = SimpleNamespace(user_id="u", name="Always in", id="s1", inst={"symbol": "BTC-USD"}, replaying=None)
    evs = [{"side": "buy", "qty": 1, "px": 100.0, "why": "Entry rule", "t": f"2026-10-12T09:{i:02d}:00"} for i in range(30)]
    mgr.replay(s, lambda: s.replaying.extend(evs))
    (_, subject, text), = [c for c in calls if c[0] == "alert"]
    assert "30 paper trades" in subject and text.count("BUY") == 20 and text.endswith("and 10 more on the session page")
    assert len(text) < 4096


def test_trade_alerts_are_capped_per_user_per_day_on_email_and_telegram(monkeypatch):
    sent = []
    monkeypatch.setattr(live, "TRADE_ALERTS_PER_DAY", 3)
    monkeypatch.setattr(live, "notify", lambda p, subj, body, **k: sent.append(("all", subj)) or ["email"])
    monkeypatch.setattr(live.db, "update_setting", lambda key, fn: store.update(v=fn(store.get("v"))))
    store = {}
    monkeypatch.setattr(live.alerts, "jobs_for", lambda p, subj, text, url="/paper": [
        ("push", lambda: sent.append(("push", subj))), ("telegram", lambda: sent.append(("telegram", subj))),
        ("email", lambda: sent.append(("email", subj)))])
    p = {"id": "u"}
    for i in range(6):
        live.trade_notify(p, f"trade {i}", "text", url="/paper/s1")
    assert [x for x in sent if x[0] == "all"] == [("all", f"trade {i}") for i in range(3)]           # under the cap: as before
    over = [x for x in sent if x[0] != "all"]
    assert [x for x in over if x[0] == "push"] == [("push", "trade 3"), ("push", "trade 4"), ("push", "trade 5")]
    assert [x for x in over if x[0] != "push"] == [("telegram", "StratLab: trade alert limit for today"),
                                                   ("email", "StratLab: trade alert limit for today")]     # one last message


def test_a_follower_shows_running_sessions_from_their_saved_state_and_passes_a_stop_on(monkeypatch):
    from app import leader, main  # noqa: F401
    from tests import world as W
    from tests.test_mcp_server import PRO, start_session
    built = W.build(monkeypatch)
    try:
        c, mgr = built["client"], built["manager"]
        sid = start_session(c)
        mgr.persist(only_dirty=False)
        mgr.drop_all()                                          # this container lost the lease: another one runs it
        monkeypatch.setattr(leader, "leading", lambda: False)
        rows = c.get("/live/sessions", headers=PRO).json()
        assert [r["status"] for r in rows if r["id"] == sid] == ["running"]          # not "paused"
        ov = c.get("/live/overview", headers=PRO).json()
        assert [x["id"] for x in ov["sessions"]] == [sid]
        snap = c.get(f"/live/sessions/{sid}", headers=PRO).json()
        assert snap["status"] == "running" and snap["notice"].startswith("Updating")
        assert c.post(f"/live/sessions/{sid}/stop", headers=PRO).json() == {"stopped": True}
        rows = c.get("/live/sessions", headers=PRO).json()
        assert [r["status"] for r in rows if r["id"] == sid] == ["stopped"]          # the leader's next reconcile detaches it
    finally:
        built["close"]()
