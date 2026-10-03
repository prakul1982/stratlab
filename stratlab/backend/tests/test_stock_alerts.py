"""Stock alerts people set: each condition, the wording, firing once, repeating at most daily, the per-user message
limits, market hours, plan limits and the endpoints."""
import json
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from app import alerts, db, main, stock_alerts as sa
from app.config import settings
from app.plans import PLANS, plan_info
from tests import world as W
from tests.fake_db import headers

TODAY = "2026-10-01"
IN_OPEN = datetime(2026, 10, 1, 6, 0, tzinfo=timezone.utc)          # 11:30 in India, a Thursday
US_OPEN = datetime(2026, 10, 1, 15, 0, tzinfo=timezone.utc)         # 11:00 in New York


def bars_from(closes, end=TODAY):
    """Daily candles ending the day before `end`."""
    last = datetime.fromisoformat(end).replace(tzinfo=timezone.utc) - timedelta(days=1)
    n = len(closes)
    return [{"t": (last - timedelta(days=n - 1 - i)).isoformat(), "o": c, "h": c * 1.01, "l": c * 0.99, "c": c, "v": 1000}
            for i, c in enumerate(closes)]


def alert(**kw):
    a = sa.clean({"region": "IN", "symbol": "RELIANCE", **kw})
    return {**a, "id": "abc123", "status": "active", "rev": 1, "state": kw.get("state") or {}}


def snap(price, chg=None, bars=None, today=TODAY):
    return {"price": price, "change_pct": chg, "bars": bars, "today": today, "tz": "Asia/Kolkata"}


# ---------- wording ----------
def test_money_is_factual_and_grouped_the_local_way():
    assert sa.money(3000, "IN") == "₹3,000" and sa.money(3012.4, "IN") == "₹3,012.40"
    assert sa.money(123456.5, "IN") == "₹1,23,456.50" and sa.money(12345678, "IN") == "₹1,23,45,678"
    assert sa.money(187.25, "US") == "$187.25" and sa.money(1234567, "US") == "$1,234,567"


def test_describe_each_kind():
    assert sa.describe(alert(kind="price", op="above", value=3000)) == "Price crosses above ₹3,000"
    assert sa.describe(alert(kind="move", op="down", value=5)) == "Falls 5% or more in a day"
    assert sa.describe(alert(kind="ma", op="below", period=200)) == "Price crosses below its 200-day average"
    assert sa.describe(alert(kind="rsi", op="above", value=70)) == "14-day RSI crosses above 70"
    assert sa.describe(alert(kind="stage", value=2)) == "Enters Stage 2" and sa.describe(alert(kind="stage")) == "Stage changes"
    assert sa.describe(alert(kind="high52")) == "Makes a new 52-week high"


@pytest.mark.parametrize("bad", [
    {"region": "UK", "kind": "price", "op": "above", "value": 1}, {"symbol": "", "kind": "price", "op": "above", "value": 1},
    {"symbol": "../etc", "kind": "price", "op": "above", "value": 1}, {"kind": "nope"},
    {"kind": "price", "op": "up", "value": 1}, {"kind": "price", "op": "above", "value": -5},
    {"kind": "price", "op": "above", "value": float("nan")}, {"kind": "price", "op": "above", "value": float("inf")},
    {"kind": "price", "op": "above", "value": True}, {"kind": "move", "op": "up", "value": 0},
    {"kind": "move", "op": "above", "value": 5}, {"kind": "ma", "op": "above", "period": 7},
    {"kind": "rsi", "op": "above", "value": 120}, {"kind": "stage", "value": 5}, {"kind": "stage", "value": 2.5},
])
def test_clean_refuses_conditions_that_make_no_sense(bad):
    with pytest.raises(sa.AlertError):
        sa.clean({"region": "IN", "symbol": "RELIANCE", **bad})


# ---------- each condition ----------
def test_price_crossing_fires_only_on_the_cross_with_a_factual_message():
    a = alert(kind="price", op="above", value=3000)
    text, st = sa.evaluate(a, snap(2990))
    assert text is None and st["side"] == "below"                      # the first look only arms it
    text, st = sa.evaluate({**a, "state": st}, snap(3012))
    assert text == "RELIANCE crossed above ₹3,000 (now ₹3,012)"
    # already above when it was set: no alert until it goes below and back
    assert sa.evaluate({**a, "state": {"side": "above"}}, snap(3050))[0] is None
    b = alert(kind="price", op="below", value=2500, state={"side": "above"})
    assert sa.evaluate(b, snap(2499.5))[0] == "RELIANCE crossed below ₹2,500 (now ₹2,499.50)"
    assert sa.evaluate(b, snap(2500))[0] is None                         # exactly on the level isn't a cross


def test_day_move_up_down_and_either_way():
    up, down, either = alert(kind="move", op="up", value=5), alert(kind="move", op="down", value=5), alert(kind="move", op="either", value=3)
    assert sa.evaluate(up, snap(3150, 5.2))[0] == "RELIANCE is up 5.2% today (now ₹3,150)"
    assert sa.evaluate(up, snap(3150, 4.9))[0] is None and sa.evaluate(up, snap(2850, -6))[0] is None
    assert sa.evaluate(down, snap(2850, -6))[0] == "RELIANCE is down 6.0% today (now ₹2,850)"
    assert sa.evaluate(either, snap(2900, -3.1))[0] and sa.evaluate(either, snap(3100, 3.1))[0]
    assert sa.evaluate(either, snap(3000, None))[0] is None             # no change figure: nothing to say


def test_moving_average_crossing_uses_todays_price():
    a = alert(kind="ma", op="above", period=50)
    bars = bars_from([100.0] * 60)
    text, st = sa.evaluate(a, snap(99, bars=bars))
    assert text is None and st["side"] == "below"
    text, _ = sa.evaluate({**a, "state": st}, snap(110, bars=bars))
    assert text == "RELIANCE crossed above its 50-day average of ₹100.20 (now ₹110)"
    assert sa.evaluate(alert(kind="ma", op="above", period=200), snap(110, bars=bars))[0] is None   # too little history


def test_rsi_crossing():
    a = alert(kind="rsi", op="above", value=70)
    flat = bars_from(list(np.linspace(100, 101, 20)) + list(np.linspace(101, 95, 10)))
    text, st = sa.evaluate(a, snap(95, bars=flat))
    assert text is None and st["side"] == "below"
    rising = bars_from(list(np.linspace(80, 120, 40)))
    text, _ = sa.evaluate({**a, "state": st}, snap(125, bars=rising))
    assert text.startswith("RELIANCE's 14-day RSI crossed above 70 (now ") and "price ₹125" in text


def test_stage_change_fires_on_the_change_and_can_wait_for_one_stage():
    up = bars_from(list(np.linspace(100, 200, 300)))
    a = alert(kind="stage")
    text, st = sa.evaluate(a, snap(200, bars=up))
    assert text is None and st["stage"] == 2
    down = bars_from(list(np.linspace(100, 200, 300)) + list(np.linspace(200, 150, 40)))
    text, st2 = sa.evaluate({**a, "state": st}, snap(150, bars=down))
    assert text == f"RELIANCE moved from Stage 2 to Stage {st2['stage']} (now ₹150)" and st2["stage"] != 2
    only4 = alert(kind="stage", value=4, state={"stage": 2})
    if st2["stage"] != 4:
        assert sa.evaluate(only4, snap(150, bars=down))[0] is None       # a change, but not to the stage asked for


def test_52_week_high_and_low():
    year = bars_from([100.0 + (i % 7) for i in range(300)])             # highs up to 106 * 1.01, lows from 99
    hi, lo = alert(kind="high52"), alert(kind="low52")
    assert sa.evaluate(hi, snap(107, bars=year))[0] is None
    assert sa.evaluate(hi, snap(108, bars=year))[0] == "RELIANCE traded above its 52-week high of ₹107.06 (now ₹108)"
    assert sa.evaluate(lo, snap(98, bars=year))[0] == "RELIANCE traded below its 52-week low of ₹99 (now ₹98)"
    assert sa.evaluate(hi, snap(108, bars=year[:5]))[0] is None           # not enough history to say


def test_bad_numbers_never_fire_or_crash():
    for p in (None, 0, -1, float("nan"), float("inf"), "12"):
        for kind in ("price", "move", "ma", "rsi", "stage", "high52"):
            a = alert(kind=kind, op={"move": "up", "price": "above", "ma": "above", "rsi": "above"}.get(kind),
                      value={"price": 10, "move": 1, "rsi": 50}.get(kind), period=50 if kind == "ma" else None)
            assert sa.evaluate(a, snap(p, chg=p, bars=[]))[0] is None


# ---------- the checker ----------
@pytest.fixture
def store(monkeypatch):
    kv = {}
    monkeypatch.setattr(db, "set_setting", lambda k, v: kv.__setitem__(k, v))
    monkeypatch.setattr(db, "get_setting", lambda k: kv.get(k))
    monkeypatch.setattr(db, "all_settings_with_prefix", lambda p, page=1000: sorted((k, v) for k, v in kv.items() if k.startswith(p)))
    monkeypatch.setattr("app.data.calendar.is_trading_day", lambda m, d: d.weekday() < 5)
    return kv


class Market:
    def __init__(self):
        self.prices: dict[str, float] = {}
        self.calls = []

    def quotes(self, region, syms):
        self.calls.append((region, list(syms)))
        return {s: {"price": self.prices[s], "change_pct": 0.0} for s in syms if s in self.prices}


def checker(market, sent, limit=100):
    return sa.Checker(market.quotes, lambda r, s: [], lambda p: limit,
                      send=lambda p, subject, text: sent.append((p["id"], subject, text)) or ["push"],
                      profile=lambda uid: {"id": uid})


def test_an_alert_fires_once_then_is_marked_triggered(store):
    m, sent = Market(), []
    m.prices["RELIANCE"] = 2990
    sa.create("u1", {"region": "IN", "symbol": "RELIANCE", "kind": "price", "op": "above", "value": 3000}, 3, {"price": 2990})
    job = checker(m, sent)
    job.tick(IN_OPEN)
    assert sent == []
    m.prices["RELIANCE"] = 3012
    job.tick(IN_OPEN + timedelta(minutes=1))
    m.prices["RELIANCE"] = 2990
    job.tick(IN_OPEN + timedelta(minutes=2))
    m.prices["RELIANCE"] = 3020
    job.tick(IN_OPEN + timedelta(minutes=3))
    assert len(sent) == 1 and sent[0][1] == "StratLab alert: RELIANCE crossed above ₹3,000 (now ₹3,012)"
    assert "Facts, not advice" in sent[0][2]
    (a,) = sa.items("u1")
    assert a["status"] == "triggered" and a["fired"] == 1 and a["last_text"].endswith("(now ₹3,012)")


def test_a_repeating_alert_fires_at_most_once_a_day(store):
    m, sent = Market(), []
    m.prices["AAPL"] = 200
    sa.create("u1", {"region": "US", "symbol": "AAPL", "kind": "move", "op": "either", "value": 0.1, "repeat": True}, 3)
    m.quotes = lambda r, syms: {"AAPL": {"price": 200, "change_pct": 2.0}}
    job = checker(m, sent)
    for i in range(5):
        job.tick(US_OPEN + timedelta(minutes=i))
    assert len(sent) == 1 and sent[0][1] == "StratLab alert: AAPL is up 2.0% today (now $200)"
    job.tick(US_OPEN + timedelta(days=1))                                   # Friday: again
    assert len(sent) == 2 and sa.items("u1")[0]["status"] == "active" and sa.items("u1")[0]["fired"] == 2


def test_quotes_are_fetched_once_per_symbol_in_batches(store):
    m, sent = Market(), []
    for i in range(30):
        m.prices[f"S{i}"] = 100
    for uid in ("u1", "u2"):
        for i in range(30):
            sa.create(uid, {"region": "IN", "symbol": f"S{i}", "kind": "price", "op": "above", "value": 150}, 100)
    checker(m, sent).tick(IN_OPEN)
    assert [len(s) for _, s in m.calls] == [24, 6]                           # 60 alerts, 30 symbols, two calls


def test_only_open_markets_are_checked(store):
    m, sent = Market(), []
    sa.create("u1", {"region": "IN", "symbol": "TCS", "kind": "price", "op": "above", "value": 1}, 3)
    sa.create("u1", {"region": "US", "symbol": "AAPL", "kind": "price", "op": "above", "value": 1}, 3)
    job = checker(m, sent)
    job.tick(US_OPEN)                                                        # 20:30 in India: closed
    assert m.calls == [("US", ["AAPL"])]
    m.calls.clear()
    job.tick(datetime(2026, 10, 3, 6, 0, tzinfo=timezone.utc))               # a Saturday
    job.tick(datetime(2026, 10, 1, 2, 0, tzinfo=timezone.utc))               # 07:30 in India, before the open
    assert m.calls == []
    assert sa.market_open("IN", datetime(2026, 10, 1, 10, 3, tzinfo=timezone.utc)) == TODAY   # 15:33, just after the close


def test_one_user_cant_be_spammed_and_held_alerts_go_out_together(store):
    m, sent = Market(), []
    for i in range(8):
        m.prices[f"S{i}"] = 90
        sa.create("u1", {"region": "IN", "symbol": f"S{i}", "kind": "price", "op": "above", "value": 100}, 100, {"price": 90})
    job = checker(m, sent)
    t = IN_OPEN
    for i in range(8):                                                       # each minute, one more crosses
        m.prices[f"S{i}"] = 110
        job.tick(t + timedelta(minutes=i))
    assert len(sent) == sa.PER_HOUR                                          # 5 messages, then held back
    row = json.loads(store["stockalerts:u1"])
    assert len(row["pending"]) == 3 and all(a["status"] == "triggered" for a in row["items"])
    job.tick(t + timedelta(minutes=70))                                      # an hour on: the three go in one message
    assert len(sent) == sa.PER_HOUR + 1 and sent[-1][1] == "StratLab: 3 of your alerts fired"
    assert all(f"S{i} crossed above" in sent[-1][2] for i in (5, 6, 7))
    assert json.loads(store["stockalerts:u1"])["pending"] == []


def test_a_day_cap_too():
    now = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)
    spread = [(now - timedelta(hours=2 + i)).isoformat() for i in range(sa.PER_DAY)]
    assert not sa.may_send(spread, now) and sa.may_send(spread[:-1], now)
    assert sa.may_send(["garbage", None], now)


def test_alerts_over_the_plan_limit_wait(store):
    m, sent = Market(), []
    for i in range(5):
        m.prices[f"S{i}"] = 90
        sa.create("u1", {"region": "IN", "symbol": f"S{i}", "kind": "price", "op": "above", "value": 100}, 100)
    checker(m, sent, limit=3).tick(IN_OPEN)                                   # moved down to Free: the oldest three
    assert sorted(m.calls[0][1]) == ["S0", "S1", "S2"]


def test_an_edit_during_a_check_isnt_overwritten(store):
    m, sent = Market(), []
    a = sa.create("u1", {"region": "IN", "symbol": "TCS", "kind": "price", "op": "above", "value": 100}, 3, {"price": 90})
    m.prices["TCS"] = 120
    job = checker(m, sent)
    real = job.quotes

    def edit_then_quote(region, syms):
        sa.update("u1", a["id"], {"region": "IN", "symbol": "TCS", "kind": "price", "op": "above", "value": 500}, 3)
        return real(region, syms)
    job.quotes = edit_then_quote
    job.tick(IN_OPEN)
    (b,) = sa.items("u1")
    assert b["status"] == "active" and b["value"] == 500 and sent == []


def test_a_broken_row_or_source_doesnt_stop_the_others(store):
    m, sent = Market(), []
    store["stockalerts:broken"] = "{not json"
    store["stockalerts:odd"] = json.dumps({"items": [{"id": "x", "status": "active", "region": "IN", "symbol": "A", "kind": "price"}]})
    sa.create("u1", {"region": "IN", "symbol": "TCS", "kind": "price", "op": "above", "value": 100}, 3, {"price": 90})
    m.prices.update(TCS=120, A=5)
    checker(m, sent).tick(IN_OPEN)
    assert len(sent) == 1 and "TCS crossed above" in sent[0][1]
    failing = sa.Checker(lambda r, s: (_ for _ in ()).throw(RuntimeError("down")), lambda r, s: [], lambda p: 3,
                         send=lambda *a: [], profile=lambda uid: {"id": uid})
    failing.tick(IN_OPEN)
    assert failing.status["last_error"] == "down"


def test_limit_counts_only_active_alerts(store):
    body = {"region": "IN", "symbol": "TCS", "kind": "price", "op": "above", "value": 100}
    made = [sa.create("u1", body, 3) for _ in range(3)]
    with pytest.raises(sa.LimitReached):
        sa.create("u1", body, 3)
    row = json.loads(store["stockalerts:u1"])
    row["items"][0]["status"] = "triggered"
    store["stockalerts:u1"] = json.dumps(row)
    sa.create("u1", body, 3)                                                 # a fired one frees a place
    with pytest.raises(sa.LimitReached):                                     # turning the fired one back on doesn't
        sa.update("u1", made[0]["id"], body, 3)
    assert sa.update("u1", "nope", body, 3) is None


# ---------- delivery ----------
def test_email_goes_only_to_a_confirmed_address(monkeypatch):
    mail, phone = [], []
    monkeypatch.setattr(alerts, "email_ready", lambda: True)
    monkeypatch.setattr(alerts, "send_email", lambda to, subject, text, html=None, headers=None: mail.append((to, text)))
    monkeypatch.setattr(alerts, "jobs_for", lambda p, s, t, url="/paper": [("push", lambda: phone.append(t)), ("email", lambda: mail.append("raw"))])
    p = {"id": "u1", "email": "me@example.com"}
    monkeypatch.setattr(alerts, "email_confirmed", lambda prof: False)
    assert sa.deliver(p, "s", "RELIANCE crossed above ₹3,000 (now ₹3,012)") == ["push"] and mail == []
    monkeypatch.setattr(alerts, "email_confirmed", lambda prof: True)
    assert sa.deliver(p, "s", "x") == ["push", "email"]
    assert mail[0][0] == "me@example.com" and "/alerts" in mail[0][1] and "raw" not in mail


# ---------- plans ----------
def test_plan_limits(monkeypatch):
    assert (PLANS["free"]["stock_alerts"], PLANS["basic"]["stock_alerts"], PLANS["pro"]["stock_alerts"]) == (3, 20, 100)
    monkeypatch.setattr(settings, "RAZORPAY_KEY_ID", "")
    assert plan_info("free")["stock_alerts"] == 100                          # open to everyone until payments go live
    paid(monkeypatch)
    assert [plan_info(p)["stock_alerts"] for p in ("free", "basic", "pro")] == [3, 20, 100]


def paid(monkeypatch):
    monkeypatch.setattr(settings, "RAZORPAY_KEY_ID", "rzp_live_x")
    monkeypatch.setattr(settings, "RAZORPAY_KEY_SECRET", "secret")
    monkeypatch.setattr(settings, "RAZORPAY_PLAN_BASIC", "plan_b")
    monkeypatch.setattr(settings, "RAZORPAY_PLAN_PRO", "plan_p")


# ---------- the endpoints ----------
@pytest.fixture
def w(monkeypatch):
    world = W.build(monkeypatch)
    yield world
    world["close"]()


def test_create_edit_delete_through_the_api(w):
    c, h = w["client"], headers("pro-token")
    assert c.get("/alerts", headers=h).json()["active"] == []
    r = c.post("/alerts", headers=h, json={"region": "IN", "symbol": "reliance", "kind": "price", "op": "above", "value": 1})
    assert r.status_code == 200, r.text
    body = r.json()
    a = body["alert"]
    assert a["symbol"] == "RELIANCE" and a["text"] == "Price crosses above ₹1" and "state" not in a
    assert body["note"] and "already above ₹1" in body["note"] and body["count"] == 1
    r = c.put(f"/alerts/{a['id']}", headers=h, json={"region": "IN", "symbol": "RELIANCE", "kind": "ma", "op": "below", "period": 200})
    assert r.status_code == 200 and r.json()["alert"]["text"] == "Price crosses below its 200-day average"
    assert c.put("/alerts/ffffff", headers=h, json={"region": "IN", "symbol": "RELIANCE", "kind": "high52"}).status_code == 404
    assert c.post("/alerts", headers=h, json={"region": "IN", "symbol": "NOSUCHCO", "kind": "high52"}).json()["detail"]["code"] == "no_price"
    assert c.post("/alerts", headers=h, json={"region": "IN", "symbol": "TCS", "kind": "rsi", "op": "above", "value": 500}).status_code == 400
    assert c.delete(f"/alerts/{a['id']}", headers=h).json()["active"] == []
    assert c.delete(f"/alerts/{a['id']}", headers=h).status_code == 404
    assert c.delete("/alerts", headers=h).status_code == 200
    assert c.get("/alerts").status_code == 401


def test_the_free_plan_has_three_alerts(w, monkeypatch):
    paid(monkeypatch)
    c, h = w["client"], headers("free-token")
    body = {"region": "IN", "symbol": "TCS", "kind": "move", "op": "either", "value": 5}
    for _ in range(3):
        assert c.post("/alerts", headers=h, json=body).status_code == 200
    r = c.post("/alerts", headers=h, json=body)
    assert r.status_code == 402 and "3 active alerts" in r.json()["detail"]["message"] and "Basic" in r.json()["detail"]["message"]
    assert c.get("/alerts", headers=h).json()["limit"] == 3
    assert c.get("/me", headers=h).json()["plan_info"]["stock_alerts"] == 3


def test_the_watchlist_job_runs_the_stock_alert_check(monkeypatch):
    seen = []
    job = main.scan.Alerts(None, notify=None, can_alert=None, checks=[seen.append])
    assert job.checks == [seen.append]
    assert main.scan_alerts_job.checks                                     # the app's job carries the stock alert check
