"""Round 11 review of the core strategy product (9 Oct 2026): paper sessions stopped with a position open, the trade list,
the group checks, the verdict's words, the AI builder's rules checked against the sentence, options on USDINR, stored trend
scans, chart candles, share links and labels. Nothing here depends on the time of day: every clock is a fixed instant."""
import json
from datetime import date, datetime, timedelta, timezone

import pytest

from app import main  # noqa: F401, I001  (first: the app loads its jobs before the modules built on them)
from app import ai_writer, breadth, group_live, importer, library_seed, live, official_close, public, research, scan_presets
from app.engine import portfolio, verdict as V, walkforward  # noqa: F401
from app.kite_service import KiteService
from app.models import Strategy
from app.options import data as opt_data, engine as opt_engine
from tests.test_live_polling import make_manager

IST = timezone(timedelta(hours=5, minutes=30))
P = {"t": "price"}


def num(v):
    return {"t": "num", "v": v}


# ---------- R11C-002: a session stopped with a position open keeps it, valued at the last price ----------
ALWAYS = {"name": "R test AAPL paper 5m", "tf": "5m", "side": "long", "entryJoin": "all",
          "entry": [{"l": P, "op": "gt", "r": num(1)}], "exit": [],
          "risk": {"capital": 10000, "riskPct": 1, "maxAlloc": 100, "sl": 1, "sizing": "capital", "perTrade": 9800, "leverage": 1,
                   "brokerage": 0, "slippage": 0.05}}


def _session(mgr, reg):
    inst = reg.resolve("CRYPTO:BTC-USD")[1]
    row = {"id": "s1", "user_id": "u", "name": ALWAYS["name"], "strategy": ALWAYS, "instrument": inst,
           "started_at": "2026-10-09T13:30:00+00:00"}
    return live.LiveSession(mgr, row), row


def test_stopping_with_a_position_open_keeps_it_valued_at_the_last_price(monkeypatch):
    mgr, reg = make_manager()
    monkeypatch.setattr(mgr, "on_order", lambda s, ev: None)
    s, row = _session(mgr, reg)
    s._on_candle({"t": "2999-01-01T14:00:00+00:00", "o": 335.0, "h": 335.4, "l": 334.8, "c": 335.18, "v": 1})
    e = s.engine
    assert e.qty > 0 and e.cash < 1000                                       # nearly all of the $10,000 is in the position
    s.last_price = 335.88
    mgr.sessions[s.id] = s
    saved = {}
    monkeypatch.setattr(live.db, "update_session", lambda sid, **k: saved.update(k))
    mgr.stop(s.id, "Stopped by you.")
    st = saved["state"]
    assert st["qty"] == e.qty and st["last_price"] == 335.88 and st["bars"]
    snap = live.stopped_snapshot({**row, "status": "stopped", "stop_reason": "Stopped by you.", "state": st})
    a = snap["account"]
    worth = st["cash"] + e.qty * 335.88
    assert a["qty"] == e.qty and a["equity"] == pytest.approx(worth) and a["valued_at"] == 335.88
    assert a["equity"] > 9900 and a["equity"] / 10000 - 1 > -0.05                # never "-97%": the shares are counted
    assert a["unrealised"] == pytest.approx(e.qty * (335.88 - e.entry))
    assert snap["equity_curve"][-1]["eq"] == pytest.approx(round(worth, 2))     # the curve ends where the account is
    assert snap["bars"] and snap["last_price"] == 335.88                        # and the chart stays


def test_a_session_stopped_before_the_last_price_was_kept_is_valued_where_its_curve_ends():
    st = {"cash": 274.87, "qty": 29, "entry": 335.35, "dir": 1, "trades": [], "events": [],
          "equity_curve": [{"t": "2026-10-09T14:05:00-04:00", "eq": 10016.39}]}
    row = {"id": "s1", "name": "x", "status": "stopped", "instrument": {"symbol": "AAPL"}, "strategy": ALWAYS,
           "started_at": "2026-10-09T13:30:00+00:00", "state": st}
    a = live.stopped_snapshot(row)["account"]
    assert a["qty"] == 29 and a["equity"] == pytest.approx(10016.39)          # not the $275 of cash alone
    assert a["valued_at"] == pytest.approx((10016.39 - 274.87) / 29)


def test_a_group_stopped_with_positions_open_keeps_them():
    st = {"members": {"IN:1": {"qty": 10, "dir": 1, "entry": 100.0, "entry_cost": 2.0, "last_price": 110.0, "trades": [{"pnl": 50.0}],
                               "symbol": "TCS", "events": []},
                      "IN:2": {"qty": 0, "dir": 1, "entry": 0.0, "trades": [{"pnl": -20.0}], "symbol": "INFY", "events": []}},
          "equity_curve": [{"t": "2026-10-09T15:30:00+05:30", "eq": 100128.0}]}
    row = {"id": "g1", "name": "g", "status": "stopped", "strategy": {"risk": {"capital": 100000}},
           "instrument": {"maxOpen": 2, "names": {}}, "started_at": "2026-10-09T09:15:00+05:30", "state": st}
    snap = group_live.stopped_snapshot(row)
    a = snap["account"]
    assert a["open"] == 1 and a["unrealised"] == pytest.approx(98.0) and a["equity"] == pytest.approx(100000 + 30 + 98)
    held = [m for m in snap["members"] if m["position"]]
    assert held[0]["symbol"] == "TCS" and held[0]["price"] == 110.0


def test_the_stop_dialog_says_the_position_stays_open():
    words = open("../frontend/src/lib/paperText.ts").read()
    assert "Open paper positions stay open, valued at the last price before the stop" in words


# ---------- R11C-003: "Every trade" is the newest 200 of all, and the rest is accounted for ----------
def test_trades_beyond_the_newest_200_are_counted_with_their_pnl():
    closed = [{"pnl": float(i - 100), "exit_t": f"t{i}"} for i in range(250)]
    out = research.omitted(closed)
    assert out == {"trades_omitted": 50, "omitted_pnl": round(sum(i - 100 for i in range(50)), 2)}
    assert research.omitted(closed[:200]) == {}
    slimmed = research.slim([{"trades": [{"pnl": 1.0}] * 40}] + [{"trades": []}] * research.KEEP_FULL)
    assert slimmed[0]["trades_trimmed"] == 10 and slimmed[0]["trimmed_pnl"] == 10.0


# ---------- R11C-014 and R11C-010: a group's members and its bad-luck check ----------
def _datasets(n_stocks=3, days=120):
    out = []
    for k in range(n_stocks):
        bars, t0 = [], datetime(2026, 1, 1, tzinfo=IST)
        for i in range(days):
            c = 100 + 10 * ((i * (k + 3)) % 7) + i * 0.1
            bars.append({"t": (t0 + timedelta(days=i)).isoformat(), "o": c, "h": c * 1.01, "l": c * 0.99, "c": c, "v": 1})
        out.append({"inst": {"symbol": f"S{k}", "id": f"IN:{k}"}, "bars": bars, "start": 20, "lot": 1, "kind": "flat"})
    return out


GROUP = Strategy(name="g", tf="1d", entry=[{"l": P, "op": "gt", "r": num(1)}], exit=[],
                 risk={"capital": 100000, "riskPct": 1, "maxAlloc": 30, "sl": 0, "maxBars": 7, "sizing": "capital",
                       "perTrade": 30000, "brokerage": 0, "slippage": 0.05})


def test_a_groups_members_add_up_to_its_total_with_open_positions_marked():
    res = portfolio.run(_datasets(), GROUP, 3)
    assert res["open_trades"]                                              # something is still open at the end
    total = res["equity"][-1] - 100000
    assert sum(m["pnl"] for m in res["members"]) == pytest.approx(total, abs=0.05)
    opened = [m for m in res["members"] if m["open"]]
    assert opened and all(m["open_pnl"] != 0 for m in opened)


def test_a_groups_bad_luck_check_reshuffles_its_days_not_one_overlapping_stretch():
    res = portfolio.run(_datasets(), GROUP, 3)
    v = V.evaluate_portfolio(None, res, GROUP, 100, 3650)
    c = next(x for x in v["checks"] if x["id"] == "shuffle")
    assert c["data"]["by"] == "days"
    d = c["data"]
    assert not (d["p95"] == d["worst"] == d["yours"])                     # R11C-010: all three equal to 15 digits
    # a reshuffle with nothing to move proves nothing: not run, never "Passed"
    one = V.check_shuffle([{"pnl": 1.0}] * 10, 100000, paths=[[1.0, -2.0, 3.0]])
    assert one["status"] == "skip"
    flat = V.check_shuffle([{"pnl": 1.0}] * 10, 100000, steps=[0.0] * 30 + [5.0, -3.0])
    assert flat["status"] == "skip"


# ---------- R11C-009 and R11C-006: the verdict states facts ----------
def test_the_headline_is_facts_like_the_library_card():
    checks = [{"id": "unseen", "status": "pass"}, {"id": "nearby", "status": "skip"}, {"id": "shuffle", "status": "pass"},
              {"id": "sample", "status": "pass"}]
    head = V.fact_headline("edge", checks, 250, 55.8, 172.9)
    assert head == "117.1 points behind buy and hold after costs; passed all 3 checks run."
    for words in V.HEADLINES.values():
        assert not any(x in words for x in ("Likely", "real edge", "Probably", "luck"))


def test_a_verdict_stored_with_a_claim_is_shown_with_its_facts(monkeypatch):
    v = {"verdict": "edge", "headline": "Likely a real edge.", "checks": [{"id": "unseen", "status": "pass"}, {"id": "nearby", "status": "skip"},
                                                                         {"id": "shuffle", "status": "pass"}, {"id": "sample", "status": "pass"}]}
    got = V.restated(v, {"n": 250, "ret": 55.8, "buy_hold_ret": 172.9})
    assert got["headline"] == "117.1 points behind buy and hold after costs; passed all 3 checks run."
    assert V.restated({**v, "headline": "Something new."}, {})["headline"] == "Something new."     # only the old claims
    monkeypatch.setattr(public.db, "get_setting", lambda k: json.dumps({"question": "", "verdict": v, "stats": {"n": 250, "ret": 55.8, "buy_hold_ret": 172.9}}))
    assert public.load("NlpCFMRAhSA")["verdict"]["headline"].startswith("117.1 points behind")
    import inspect
    assert "verdict_restated(e.get(\"verdict\"), e.get(\"stats\"))" in inspect.getsource(main.read_notebook)


def test_no_trades_is_said_plainly_with_no_comparison_or_lucky_fit():
    checks = [{"id": "unseen", "status": "warn"}, {"id": "nearby", "status": "skip"}, {"id": "shuffle", "status": "skip"},
              {"id": "sample", "status": "fail"}]
    v = V.decide(checks, 0, 0.0, GROUP, 1825, 3650, -41.5)
    assert v["verdict"] == "not_enough" and v["headline"] == "No trades in this period."
    assert "No trades happened" in v["summary"] and "more than buying and holding" not in v["summary"]
    assert "−41.5%" in v["summary"]
    from app.engine.core import Ctx
    bars = _datasets(1, 260)[0]["bars"]
    strat = Strategy(name="x", tf="1d", entry=[{"l": {"t": "rsi", "p": 14}, "op": "lt", "r": num(30)},
                                               {"l": P, "op": "xa", "r": {"t": "sma", "p": 200}}], exit=[])
    near = V.check_nearby(bars, strat, 210, 1, "flat", Ctx(bars, False), False)
    assert near["status"] == "skip" and "made no trades" in near["detail"] and "lucky" not in near["detail"]


def test_no_check_text_predicts_or_instructs():
    """Every string the checks can show (docstrings and comments aside) is free of claims and instructions."""
    import ast
    import inspect
    from app import basket, journal, library
    for mod in (V, walkforward, basket, journal, library):
        tree = ast.parse(inspect.getsource(mod))
        docs = {id(n.value) for n in ast.walk(tree) if isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)}
        # (the old claims are listed once, in OLD_HEADLINES, to be worded again from the facts: never shown)
        shown = " ".join(n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)
                         and id(n) not in docs and n.value not in V.OLD_HEADLINES)
        for phrase in ("Treat the backtest return as optimistic", "lucky fit", "hard to sit through", "Likely a real edge",
                       "Probably luck", "doesn't rescue it", "survives without hindsight", "could still be chance",
                       "Treat it as a maybe", "It travels", "Even with worse luck"):
            assert phrase not in shown, (mod.__name__, phrase)


# ---------- R11C-004 and R11C-005: the AI builder's rules, checked against the sentence ----------
def test_rsi_set_against_the_price_is_read_again_from_the_words():
    out = {"entry": [{"l": P, "op": "gt", "r": {"t": "sma", "p": 20}}, {"l": P, "op": "gt", "r": {"t": "rsi", "p": 14}}],
           "exit": [], "side": "long", "risk": {}, "mentioned": [], "notes": []}
    got = ai_writer.check_against_text(out, "On 15 minute candles, buy when the price closes above the 20-period SMA and RSI 14 is above 55.")
    assert {"l": {"t": "rsi", "p": 14}, "op": "gt", "r": {"t": "num", "v": 55.0}} in got["entry"]
    assert not any(c["r"].get("t") == "rsi" and c["l"]["t"] == "price" for c in got["entry"])
    assert any("read again" in n for n in got["notes"])


def test_a_junk_exit_is_left_out_and_after_15_bars_is_a_time_exit():
    out = {"entry": [{"l": {"t": "rsi", "p": 14}, "op": "lt", "r": num(30)}],
           "exit": [{"l": {"t": "rsi", "p": 14}, "op": "gt", "r": num(55)}, {"l": P, "op": "xb", "r": num(0)}],
           "side": "long", "risk": {}, "mentioned": ["exit"], "notes": []}
    got = ai_writer.check_against_text(out, "Buy when RSI 14 is below 30. Sell when RSI above 55 or after 15 bars.")
    assert got["exit"] == [{"l": {"t": "rsi", "p": 14}, "op": "gt", "r": num(55)}]
    assert got["risk"]["maxBars"] == 15 and "maxBars" in got["mentioned"]
    assert any("price with 0" in n for n in got["notes"])


def test_sell_is_the_way_out_unless_short_is_said():
    sma = lambda p: {"t": "sma", "p": p}                                   # noqa: E731
    out = {"entry": [{"l": sma(20), "op": "xa", "r": sma(50)}], "exit": [],
           "shortEntry": [{"l": sma(20), "op": "xb", "r": sma(50)}], "shortExit": [], "side": "both", "risk": {}, "mentioned": [], "notes": []}
    got = ai_writer.check_against_text(json.loads(json.dumps(out)), "Buy when SMA20 crosses above SMA50. Sell when it crosses below. Use no stop loss.")
    assert got["side"] == "long" and got["shortEntry"] == [] and got["exit"] == [{"l": sma(20), "op": "xb", "r": sma(50)}]
    assert got["risk"]["sl"] == 0 and "sl" in got["mentioned"]                # "no stop loss" is said, so never asked
    short = ai_writer.check_against_text(json.loads(json.dumps(out)), "Buy when SMA20 crosses above SMA50. Sell short when it crosses below.")
    assert short["side"] == "both"
    import inspect
    assert "ai_writer.check_against_text(out, req.text)" in inspect.getsource(main.ai_strategy)


# ---------- R11C-013: a group notebook's export brings its group back, and an export asks nothing again ----------
def test_an_export_with_its_group_imports_the_group_and_asks_nothing():
    s = {"name": "R test group", "tf": "1d", "entry": [{"l": P, "op": "gt", "r": {"t": "sma", "p": 50}}], "exit": [],
         "risk": {"capital": 500000, "riskPct": 1, "sl": 2, "tgt": 0}}
    group = {"id": "banknifty", "name": "NIFTY Bank", "market": "IN", "maxOpen": 5, "members": [{"symbol": "HDFCBANK"}, {"symbol": "KOTAKBANK"}]}
    out = importer.from_json(json.dumps({"format": "stratlab-strategy-v1", "instrument": None, "group": group, "strategy": s}))
    assert out["group"]["name"] == "NIFTY Bank" and len(out["group"]["members"]) == 2 and out["instrument_id"] is None
    assert {"riskPct", "sl", "tgt", "tf", "exit", "instrument"} <= set(out["mentioned"])
    import inspect
    assert 'payload["group"] = group_body(req.group)' in inspect.getsource(main.export_strategy)


# ---------- R11C-017: run labels and library cards ----------
def test_a_rerun_on_the_same_candles_isnt_called_newer():
    base = {"instrument": {"id": "IN:1", "symbol": "TCS"}, "days": 1825, "strategy": {"tf": "1d", "risk": {}},
            "range": {"from": "2021-10-08", "to": "2026-10-09"}, "candles": 1236}
    assert research.describe_change(base, json.loads(json.dumps(base))) == "Same setup, same candles"
    newer = {**base, "range": {"from": "2021-10-11", "to": "2026-10-12"}}
    assert research.describe_change(base, newer) == "Same setup, newer candles"


def test_a_library_card_says_the_stop_and_the_cap():
    spec = library_seed.STRATEGIES["supertrend"]
    assert library_seed.risk_text(spec, {"market": "US", "maxOpen": 10}) == "A 12% stop loss; at most 10% of the capital in one stock, up to 10 at once."
    orb = library_seed.STRATEGIES["orb-15m"]                              # its words already give the stop
    assert library_seed.risk_text(orb, {"market": "IN", "maxOpen": 5}) == "At most 20% of the capital in one stock, up to 5 at once."


# ---------- R11C-015 and R11C-016: share links ----------
def test_a_dead_share_link_opens_the_page_that_says_so(monkeypatch):
    from fastapi.testclient import TestClient
    monkeypatch.setattr(public.db, "get_setting", lambda k: None)
    r = TestClient(main.app).get("/v/NlpCFMRAhSA", follow_redirects=False)
    assert r.status_code in (302, 307) and r.headers["location"].endswith("/verdict/NlpCFMRAhSA")


def test_a_shared_page_keeps_the_rules_out_of_its_question():
    auto = 'Does "buy TCS when the 20-day SMA crosses above the 50-day SMA, sell when…" work?'
    assert public.own_question(auto) == ""
    assert public.own_question('Does "RSI dips" work on NIFTY 50?') == ""
    assert public.own_question("Does buying RSI dips beat holding NIFTY?") == "Does buying RSI dips beat holding NIFTY?"


# ---------- R11C-007: USDINR options ----------
def test_currency_options_keep_their_quarter_paise_and_their_lots():
    q = {"bid": None, "ask": None, "ltp": 0.1125}
    assert opt_engine.fill_price(q, "sell", 0, opt_engine.tick_for("CDS")) == 0.1125         # not 0.11
    assert opt_engine.fill_price(q, "sell", 1, opt_engine.tick_for("CDS")) == 0.11
    assert opt_engine.from_last(q, "sell") and not opt_engine.from_last({"bid": 0.1, "ask": 0.12, "ltp": 0.11}, "sell")
    assert opt_data.broker_qty("CDS:USDINR26OCT96CE", 1000) == 1 and opt_data.broker_qty("NFO:NIFTY26OCT22500CE", 65) == 65


def test_a_credit_above_the_wings_is_flagged_as_impossible():
    fly = [{"side": "sell", "opt": "CE", "strike": 96.0, "fill": 0.9, "qty": 1000},
           {"side": "sell", "opt": "PE", "strike": 96.0, "fill": 0.9, "qty": 1000},
           {"side": "buy", "opt": "CE", "strike": 97.0, "fill": 0.1, "qty": 1000},
           {"side": "buy", "opt": "PE", "strike": 95.0, "fill": 0.3, "qty": 1000}]                # 1.4 credit over a 1.0 wing
    assert "at every price" in main.impossible(fly)
    fine = [{**fly[0], "fill": 0.3}, {**fly[1], "fill": 0.3}, fly[2], fly[3]]
    assert main.impossible(fine) is None


def test_the_nearest_expiry_named_is_the_one_priced(monkeypatch):
    od = opt_data.OptionsData(kite=None)
    today = opt_data.ist_date().isoformat()
    later = (opt_data.ist_date() + timedelta(days=7)).isoformat()
    od._day = today
    od._rows = {"CDS": [{"symbol": f"USDINR{e}CE", "name": "USDINR", "type": "CE", "strike": 96.0, "expiry": e, "lot": 1000,
                         "exchange": "CDS"} for e in (today, later)], "NFO": [], "BFO": [], "MCX": []}
    monkeypatch.setattr(opt_data, "keep_listed", lambda ex, name, xs: xs)
    monkeypatch.setattr(opt_data, "expired_today", lambda exch, now=None: exch == "CDS")      # after 12:30 on expiry day
    und = next(u for u in od.underlyings() if u["name"] == "USDINR")
    assert und["expiries"][0] == later == od.pick_expiry("CDS", "USDINR", "current")


# ---------- R11C-008: stored trend scans ----------
def test_a_stored_match_read_on_the_last_trade_says_so_beside_the_official_close(monkeypatch):
    got = {"as_of": "2026-10-09", "at": "2026-10-09T13:27:00+00:00", "checked": 500, "counts": {},
           "rows": [{"symbol": "CPPLUS", "price": 4244.3, "chg": 6.85, "as_of": "2026-10-09", "days_ago": 0, "day": "2026-10-09",
                     "detail": "Closed at 4,244.30, above the previous 252-day high of 4,188.90"}]}
    monkeypatch.setattr(scan_presets, "stored_view", lambda group, preset: got)
    monkeypatch.setattr(main, "with_nse_close", lambda region, rows, k, c: [{**r, "price": 4185.2, "chg": 5.36, "price_source": "NSE"} for r in rows])
    monkeypatch.setattr(main, "_scan_names", lambda region, syms: {})
    row = main._stored_scan({"id": "u"}, "IN", "nifty500", "high52", "NIFTY 500")["rows"][0]
    assert row["price"] == 4185.2 and "Closed at 4,244.30" not in row["detail"]
    assert "Last traded at 4,244.30" in row["detail"] and "official close, 4,185.20" in row["detail"]


def test_the_daily_scans_are_read_again_once_the_official_closes_are_in(monkeypatch):
    runs = []

    class Runner:
        def run(self, region, now):
            runs.append(region)
            return {"ok": True}
    job = breadth.Job(Runner(), ready=lambda region: region == "IN")
    marked = []
    monkeypatch.setattr(job, "due", lambda name, now, tz, at, region=None: date(2026, 10, 9))
    monkeypatch.setattr(job, "mark", lambda name, day: marked.append(day))
    now = datetime(2026, 10, 9, 18, 57, tzinfo=IST)
    monkeypatch.setattr(official_close, "waiting", lambda day, now=None: True)
    assert job.tick(now) == 1 and runs == ["IN"] and marked == []          # read, and not done until the closes land
    job.retry.clear()
    monkeypatch.setattr(official_close, "waiting", lambda day, now=None: False)
    job.tick(now + timedelta(minutes=30))
    assert runs == ["IN", "IN"] and marked == [date(2026, 10, 9)]


# ---------- R11C-012: every range of a chart ends on the same candle ----------
def test_an_answer_that_ends_before_candles_already_seen_keeps_them():
    k = KiteService()
    day = lambda d, c: {"t": f"2026-10-{d:02d}T00:00:00+05:30", "o": c, "h": c, "l": c, "c": c, "v": 1.0}      # noqa: E731
    one_year = [day(d, 2000 + d) for d in range(1, 10)]
    assert k._with_tail(256265, "1d", one_year, note=True) == one_year
    five_years = [day(d, 2000 + d) for d in range(1, 9)]                    # the source's older copy: ends on 8 Oct
    got = k._with_tail(256265, "1d", five_years, note=True)
    assert got[-1]["t"].startswith("2026-10-09") and got[-1]["c"] == 2009
    assert k._with_tail(256265, "1d", five_years)[-1]["t"].startswith("2026-10-09")
    assert k._with_tail(256265, "5m", five_years)[-1]["t"].startswith("2026-10-08")       # another candle size: its own


# ---------- R11C-011: candle times and the candle still forming ----------
def test_a_backtest_never_decides_on_a_candle_still_forming():
    bars = [{"t": f"2026-10-09T13:{m:02d}:00-04:00", "o": 1, "h": 1, "l": 1, "c": 1, "v": 1} for m in (25, 30, 35)]
    now = datetime(2026, 10, 9, 13, 37, tzinfo=timezone(timedelta(hours=-4)))
    assert research.closed_only(bars, "5m", "US", now)[-1]["t"].endswith("13:30:00-04:00")
    assert research.closed_only(bars, "5m", "US", now + timedelta(minutes=3)) == bars
    assert research.closed_only(bars, "1d", "US", now) == bars
    last_hour = [{"t": "2026-10-09T15:15:00+05:30", "o": 1, "h": 1, "l": 1, "c": 1, "v": 1}]      # 15:15 to the 15:30 close
    assert research.closed_only(last_hour, "1h", "IN", datetime(2026, 10, 9, 15, 31, tzinfo=IST)) == last_hour
    assert research.closed_only(last_hour, "1h", "IN", datetime(2026, 10, 9, 15, 29, tzinfo=IST)) == []


def test_a_paper_accounts_value_is_stamped_when_its_candle_closed(monkeypatch):
    assert live.candle_end({"t": "2026-10-09T14:00:00-04:00"}, "5m") == "2026-10-09T14:05:00-04:00"
    assert live.candle_end({"t": "2026-10-09T15:15:00+05:30", "end": "2026-10-09T15:30:00+05:30"}, "1h") == "2026-10-09T15:30:00+05:30"
    assert live.candle_end({"t": "2026-10-09T00:00:00+05:30"}, "1d") == "2026-10-09T00:00:00+05:30"
    mgr, reg = make_manager()
    monkeypatch.setattr(mgr, "on_order", lambda s, ev: None)
    s, _ = _session(mgr, reg)
    s._on_candle({"t": "2999-01-01T14:00:00+00:00", "o": 335.0, "h": 335.4, "l": 334.8, "c": 335.18, "v": 1})
    assert s.equity_curve[-1]["t"] == "2999-01-01T14:05:00+00:00"
    b = live.CandleBuilder("5m")
    b.cur = {"start": datetime(2026, 10, 9, 15, 25, tzinfo=IST), "end": datetime(2026, 10, 9, 15, 30, tzinfo=IST),
             "o": 1, "h": 1, "l": 1, "c": 1, "v": 0}
    assert b._close()["end"] == "2026-10-09T15:30:00+05:30"
