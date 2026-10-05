"""Forward-testing outside signals: the secret URL (made, replaced, turned off, stored only as a hash), the strict
signal format, the webhook's refusals (a wrong or turned-off URL, floods, a wrong address's guesses, huge or malformed
bodies, another user's session, a stopped one, a plan without it), fills at StratLab's own price with charges, the
signal log (late, stale, repeated, refused), lots, shorts and paper capital, the daily report, the verdict once there
are 30 trades, and plan gates on the page's API."""
import json
from datetime import datetime, timedelta, timezone

import pytest

from app import daily_report, db, guard, live, main, signal_session as SS, signals as SG
from app.config import settings
from app.engine import costs as C
from tests import world

PRO, BASIC, FREE = world.headers("pro-token"), world.headers("basic-token"), world.headers("free-token")
BTC = "CRYPTO:BTC-USD"              # crypto never closes, so these tests don't depend on the clock
LIVE = 30000.0                      # the fake exchange's last price


@pytest.fixture
def w(monkeypatch):
    built = world.build(monkeypatch)
    SG.limits.clear()
    yield built
    SG.limits.clear()
    built["close"]()


def payments_live(monkeypatch):
    for k, v in (("RAZORPAY_KEY_ID", "rzp_live_x"), ("RAZORPAY_KEY_SECRET", "s"), ("RAZORPAY_PLAN_BASIC", "b"), ("RAZORPAY_PLAN_PRO", "p")):
        monkeypatch.setattr(settings, k, v)


def url(c, headers=PRO) -> str:
    r = c.post("/trade/signals/hook", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["path"]


def session(c, headers=PRO, inst=BTC, **kw) -> dict:
    r = c.post("/trade/signals/sessions", headers=headers, json={"instrument": inst, "capital": 100000, **kw})
    assert r.status_code == 200, r.text
    return r.json()


def send(c, path, body, raw: bytes | None = None, **headers):
    data = raw if raw is not None else json.dumps(body).encode()
    return c.post(path, content=data, headers={"Content-Type": "application/json", **headers})


# ---------- the URL ----------
def test_a_url_is_stored_only_as_a_hash_and_replacing_or_turning_it_off_stops_it(w):
    c = w["client"]
    path = url(c)
    token = path.rsplit("/", 1)[1]
    assert SG.TOKEN.match(token) and SG.owner(token) == "u-pro"
    stored = json.dumps(w["db"].tables.get("app_settings", []))
    assert token not in stored and SG.digest(token) in stored                  # the database never holds a working URL
    shown = c.get("/trade/signals", headers=PRO).json()["hook"]
    assert shown["hint"] == token[:4] and "path" not in shown and token not in json.dumps(shown)
    new = url(c).rsplit("/", 1)[1]
    assert SG.owner(token) is None and SG.owner(new) == "u-pro"                # replaced: the old one stops at once
    assert c.delete("/trade/signals/hook", headers=PRO).json() == {"deleted": True}
    assert SG.owner(new) is None and c.get("/trade/signals", headers=PRO).json()["hook"] is None
    for bad in ("", "x" * 43 + "!", "short", "a" * 44, None, 5):
        assert SG.owner(bad) is None


# ---------- the format ----------
def test_a_good_signal_parses():
    sid = "6f1c1d1e-1111-4222-8333-944445555666"
    got = SG.parse(json.dumps({"session": sid.upper(), "action": " BUY ", "qty": 2, "symbol": "btc/usd", "id": "tv-1",
                               "price": 29990.5, "time": "2026-10-05T09:20:00Z", "note": "line\none\x07"}).encode())
    assert got == {"session": sid, "action": "buy", "qty": 2.0, "symbol": "BTC/USD", "id": "tv-1", "price": 29990.5,
                   "time": "2026-10-05T09:20:00+00:00", "note": "lineone"}
    assert SG.parse(json.dumps({"session": sid, "action": "exit", "time": 1791192000000}).encode())["time"] == "2026-10-05T09:20:00+00:00"
    assert SG.parse(json.dumps({"session": sid, "action": "exit", "time": 1791192000}).encode())["time"] == "2026-10-05T09:20:00+00:00"


@pytest.mark.parametrize("raw", [
    b"", b"   ", b"not json", b"[1,2]", b'"text"', b"null", b"\xff\xfe{}",
    b'{"session": "6f1c1d1e-1111-4222-8333-944445555666", "action": "buy", "qty": NaN}',
    b'{"session": "6f1c1d1e-1111-4222-8333-944445555666", "action": "buy", "qty": Infinity}',
    b'{"session": "6f1c1d1e-1111-4222-8333-944445555666", "action": "buy", "action": "sell", "qty": 1}',       # a duplicate key
    b'{"session": "6f1c1d1e-1111-4222-8333-944445555666", "action": "buy", "qty": 1, "cmd": "rm -rf /"}',      # an unknown key
    b'{"session": "6f1c1d1e-1111-4222-8333-944445555666", "action": "buy", "qty": {"$gt": 0}}',              # a nested value
    b'{"session": "6f1c1d1e-1111-4222-8333-944445555666", "action": "buy", "qty": true}',
    b'{"session": "6f1c1d1e-1111-4222-8333-944445555666", "action": "buy", "qty": "1"}',
    b'{"session": "6f1c1d1e-1111-4222-8333-944445555666", "action": "buy", "qty": 0}',
    b'{"session": "6f1c1d1e-1111-4222-8333-944445555666", "action": "buy", "qty": 1e12}',
    b'{"session": "6f1c1d1e-1111-4222-8333-944445555666", "action": "buy"}',
    b'{"session": "6f1c1d1e-1111-4222-8333-944445555666", "action": "exit", "qty": 1}',
    b'{"session": "6f1c1d1e-1111-4222-8333-944445555666", "action": "{{strategy.order.action}}", "qty": 1}',
    b'{"session": "../../etc/passwd", "action": "buy", "qty": 1}',
    b'{"session": 5, "action": "buy", "qty": 1}',
    b'{"action": "buy", "qty": 1}',
    b'{"session": "6f1c1d1e-1111-4222-8333-944445555666", "action": "buy", "qty": 1, "time": "yesterday"}',
    b'{"session": "6f1c1d1e-1111-4222-8333-944445555666", "action": "buy", "qty": 1, "time": "2026-10-05T09:20:00"}',
    b'{"session": "6f1c1d1e-1111-4222-8333-944445555666", "action": "buy", "qty": 1, "id": "has space"}',
    b'{"session": "6f1c1d1e-1111-4222-8333-944445555666", "action": "buy", "qty": 1, "price": -5}',
    b'{"session": "6f1c1d1e-1111-4222-8333-944445555666", "action": "buy", "qty": 1, "note": 7}',
    b'{"session": "6f1c1d1e-1111-4222-8333-944445555666", "action": "buy", "qty": 1, "symbol": ""}',
    b"[" * 5000 + b"]" * 5000,
])
def test_malformed_signals_are_refused(raw):
    with pytest.raises(SG.SignalError) as e:
        SG.parse(raw)
    assert e.value.status in (400, 413)


def test_a_body_over_the_cap_is_refused():
    with pytest.raises(SG.SignalError) as e:
        SG.parse(b'{"note": "' + b"x" * SG.MAX_BODY + b'"}')
    assert e.value.status == 413


# ---------- the webhook ----------
def test_a_signal_fills_at_stratlabs_price_with_charges(w):
    c = w["client"]
    path, s = url(c), session(c)
    r = send(c, path, {"session": s["id"], "action": "buy", "qty": 0.5, "price": 12345, "symbol": "BTC/USD", "id": "a1"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "filled" and r.json()["price"] == LIVE          # StratLab's price, not the alert's
    r = send(c, path, {"session": s["id"], "action": "exit", "id": "a2"})
    assert r.status_code == 200 and r.json()["status"] == "filled"
    snap = c.get(f"/trade/signals/sessions/{s['id']}", headers=PRO).json()
    fee = C.total(C.order_costs("crypto", "buy", 0.5, LIVE, 0)) + C.total(C.order_costs("crypto", "sell", 0.5, LIVE, 0))
    t, = snap["trade_list"]
    assert t["pnl"] == pytest.approx(-fee) and t["costs"] == pytest.approx(fee) and snap["account"]["trades"] == 1
    assert snap["account"]["equity"] == pytest.approx(100000 - fee) and snap["account"]["qty"] == 0
    log = snap["signals"]
    assert [x["status"] for x in log] == ["filled", "filled"] and log[0]["alert_px"] == 12345 and log[0]["px"] == LIVE
    assert [o["side"] for o in snap["orders"]] == ["sell", "buy"]
    assert snap["verdict"] == {"ready": False, "trades": 1, "need": 30}
    saved = db.get_session_row("u-pro", s["id"])["state"]
    assert len(saved["signals"]) == 2                                              # kept at once, not only every 30 s
    assert c.get("/trade/signals", headers=PRO).json()["hook"]["last_used"]


def test_wrong_turned_off_and_replaced_urls_are_refused_without_touching_anything(w):
    c = w["client"]
    path, s = url(c), session(c)
    body = {"session": s["id"], "action": "buy", "qty": 0.1}
    assert send(c, "/hooks/signal/" + "A" * 43, body).status_code == 404
    assert send(c, "/hooks/signal/short", body).status_code == 404
    assert send(c, path + "x", body).status_code == 404
    new = url(c)                                                                    # replaced
    assert send(c, path, body).status_code == 404
    c.delete("/trade/signals/hook", headers=PRO)                                    # turned off
    assert send(c, new, body).status_code == 404
    assert not (db.get_session_row("u-pro", s["id"]).get("state") or {}).get("signals")
    assert main.manager.sessions[s["id"]].signals == []
    assert c.get("/hooks/signal/" + new.rsplit("/", 1)[1]).status_code == 405        # only POST


def test_floods_are_cut_off_per_url(w):
    c = w["client"]
    path, s = url(c), session(c)
    codes = [send(c, path, {"session": s["id"], "action": "buy", "qty": 0.01}).status_code for _ in range(SG.PER_MINUTE + 5)]
    assert codes[:SG.PER_MINUTE] == [200] * SG.PER_MINUTE and set(codes[SG.PER_MINUTE:]) == {429}
    assert len(main.manager.sessions[s["id"]].signals) == SG.PER_MINUTE
    r = send(c, path, {"session": s["id"], "action": "buy", "qty": 0.01})
    assert r.status_code == 429 and r.headers["retry-after"] == "60"
    assert SG.limits.signal("other", now=0) is None                               # another URL isn't held up
    lim = SG.Limits()
    t = 1_000_000.0
    for i in range(SG.PER_DAY):                                                    # and a day's cap, spread over the day
        assert lim.signal("h", now=t + i * 61) is None or i >= SG.PER_DAY
    assert lim.signal("h", now=t + SG.PER_DAY * 61) is not None


def test_guessing_urls_from_one_address_is_cut_off(w):
    c = w["client"]
    path, s = url(c), session(c)
    for i in range(SG.MISSES_PER_MINUTE):
        assert send(c, f"/hooks/signal/{'B' * 42}{i % 10}", {"session": s["id"], "action": "exit"}).status_code == 404
    assert send(c, "/hooks/signal/" + "C" * 43, {}).status_code == 429
    assert send(c, path, {"session": s["id"], "action": "buy", "qty": 0.01}).status_code == 429   # that address waits a minute
    SG.limits.clear()
    assert send(c, path, {"session": s["id"], "action": "buy", "qty": 0.01}).status_code == 200


def test_huge_and_malformed_bodies_are_refused_and_logged(w):
    c = w["client"]
    path, s = url(c), session(c)
    r = send(c, path, None, raw=b"{" + b" " * 5000 + b"}")
    assert r.status_code == 413
    r = c.post(path, content=b"x" * (9 * 1024 * 1024), headers={"Content-Type": "text/plain"})
    assert r.status_code == 413
    assert send(c, path, None, raw=b"{bad json").status_code == 400
    r = send(c, path, {"session": s["id"], "action": "buy", "qty": 1, "eval": "__import__('os').system('id')"})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "unknown_key"
    r = send(c, path, None, raw=json.dumps({"session": s["id"], "action": "buy", "qty": 0.01}).encode(), **{"Content-Type": "text/plain"})
    assert r.status_code == 200                                                    # TradingView sends plain text
    misses = c.get("/trade/signals", headers=PRO).json()["misses"]
    assert [m["reason"][:16] for m in misses[:2]] == ["Unknown field: e", "The signal isn't"]
    assert len(main.manager.sessions[s["id"]].signals) == 1


def test_another_users_session_is_never_touched(w):
    c = w["client"]
    pro_url = url(c)
    theirs = session(c, headers=BASIC)
    r = send(c, pro_url, {"session": theirs["id"], "action": "buy", "qty": 0.5})
    assert r.status_code == 404 and r.json()["detail"]["code"] == "no_session"
    assert main.manager.sessions[theirs["id"]].signals == [] and main.manager.sessions[theirs["id"]].pos == 0
    assert c.get("/trade/signals", headers=PRO).json()["misses"][0]["reason"] == "No signal session with that id on this account."
    assert c.get("/trade/signals", headers=BASIC).json()["misses"] == []           # nothing shows on their side either
    assert c.get(f"/trade/signals/sessions/{theirs['id']}", headers=PRO).status_code == 404
    assert c.post(f"/trade/signals/sessions/{theirs['id']}/test", headers=PRO, json={"action": "buy", "qty": 1}).status_code == 404
    # an ordinary (rules) paper session of the same user isn't moved by signals either
    row = db.create_session({"user_id": "u-pro", "name": "Rules", "strategy": {"risk": {"capital": 1}}, "instrument": {"symbol": "X"}, "status": "stopped"})
    assert send(c, pro_url, {"session": row["id"], "action": "buy", "qty": 1}).status_code == 404


def test_a_stopped_session_refuses_signals(w):
    c = w["client"]
    path, s = url(c), session(c)
    assert c.post(f"/live/sessions/{s['id']}/stop", headers=PRO).status_code == 200
    r = send(c, path, {"session": s["id"], "action": "buy", "qty": 0.1})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "stopped"
    snap = c.get(f"/trade/signals/sessions/{s['id']}", headers=PRO).json()
    assert snap["status"] == "stopped" and snap["signals"] == []


def test_a_plan_without_it_refuses_signals(w, monkeypatch):
    c = w["client"]
    path, s = url(c), session(c)
    monkeypatch.setitem(main.PLANS["pro"], "features", main.PLANS["pro"]["features"] - {"signal_webhooks"})
    payments_live(monkeypatch)
    r = send(c, path, {"session": s["id"], "action": "buy", "qty": 0.1})
    assert r.status_code == 403 and main.manager.sessions[s["id"]].signals == []
    assert live.session_needs(main.manager.sessions[s["id"]], "pro") == "Forward-testing outside signals"


def test_the_signal_log_late_stale_repeat_and_refusals(w):
    c = w["client"]
    path, s = url(c), session(c, capital=20000, allow_short=False)
    sid = s["id"]
    now = datetime.now(timezone.utc)
    late = (now - timedelta(seconds=150)).isoformat()
    stale = (now - timedelta(minutes=20)).isoformat()
    future = (now + timedelta(minutes=10)).isoformat()
    replies = [send(c, path, b).json() if send else None for b in (
        {"session": sid, "action": "exit"},                                        # nothing open
        {"session": sid, "action": "buy", "qty": 0.5, "time": late, "id": "x1"},  # filled late
        {"session": sid, "action": "buy", "qty": 0.5, "id": "x1"},                # a repeat
        {"session": sid, "action": "buy", "qty": 0.1, "time": stale},             # too old
        {"session": sid, "action": "buy", "qty": 0.1, "time": future},
        {"session": sid, "action": "buy", "qty": 1},                              # 45,000 on 20,000 of paper capital
        {"session": sid, "action": "sell", "qty": 1},                             # would go short
        {"session": sid, "action": "buy", "qty": 0.1, "symbol": "ETH/USD"},       # the wrong instrument
        {"session": sid, "action": "buy", "qty": 0.000000001},                    # under the coin's step
    )]
    log = c.get(f"/trade/signals/sessions/{sid}", headers=PRO).json()["signals"]
    assert [x["status"] for x in log] == ["ignored", "late", "duplicate", "rejected", "rejected", "rejected", "rejected", "rejected", "rejected"]
    assert log[1]["delay_s"] == pytest.approx(150, abs=5) and "after the alert" in log[1]["reason"]
    assert "minutes old" in log[3]["reason"] and "future" in log[4]["reason"] and "paper capital" in log[5]["reason"]
    assert "short" in log[6]["reason"] and "ETH/USD" in log[7]["reason"] and "multiple" in log[8]["reason"]
    assert replies[0]["status"] == "ignored"
    assert main.manager.sessions[sid].pos == 0.5


def test_test_signals_from_the_page(w):
    c = w["client"]
    s = session(c, allow_short=True)
    r = c.post(f"/trade/signals/sessions/{s['id']}/test", headers=PRO, json={"action": "sell", "qty": 0.2})
    assert r.status_code == 200 and r.json()["status"] == "filled"
    snap = c.get(f"/trade/signals/sessions/{s['id']}", headers=PRO).json()
    assert snap["account"]["side"] == "short" and snap["account"]["qty"] == pytest.approx(0.2)
    assert snap["signals"][0]["note"] == "Test from the StratLab page"
    assert c.post(f"/trade/signals/sessions/{s['id']}/test", headers=PRO, json={"action": "pump"}).status_code == 422
    assert c.post(f"/trade/signals/sessions/{s['id']}/test", headers=PRO, json={"action": "buy", "qty": -1}).status_code == 422


def test_indian_futures_count_lots_and_fill_in_market_hours(w, monkeypatch):
    c = w["client"]
    main.kite._load_instruments()
    fut = next(r for r in main.kite._inst if r["type"] == "FUT")
    monkeypatch.setattr(SS, "market_open", lambda inst, now: True)
    s = session(c, inst=fut["id"], capital=10_000_000)
    sess = main.manager.sessions[s["id"]]
    sess.on_tick({"last_price": 25000.0})
    path = url(c)
    r = send(c, path, {"session": s["id"], "action": "buy", "qty": 1.5})
    assert r.status_code == 409 and "whole number" in r.json()["detail"]["message"]
    assert send(c, path, {"session": s["id"], "action": "buy", "qty": 2}).json()["price"] == 25000.0
    assert sess.pos == 2 * fut["lot"]
    sess.on_tick({"last_price": 25100.0})
    assert send(c, path, {"session": s["id"], "action": "sell", "qty": 3}).status_code == 200     # closes 2 lots, opens 1 short
    assert sess.pos == -fut["lot"] and len(sess.trades) == 1
    t = sess.trades[0]
    cost = C.total(C.order_costs("in_fut", "buy", 150, 25000, 20)) + C.total(C.order_costs("in_fut", "sell", 225, 25100, 20)) * 150 / 225
    assert t["pnl"] == pytest.approx(150 * 100 - cost) and t["qty"] == 150
    monkeypatch.setattr(SS, "market_open", lambda inst, now: False)
    r = send(c, path, {"session": s["id"], "action": "exit"})
    assert r.status_code == 409 and r.json()["detail"]["message"] == "The market was closed."


def test_market_hours():
    ist = timezone(timedelta(hours=5, minutes=30))
    nse = {"market": "IN"}
    assert SS.market_open(nse, datetime(2026, 10, 5, 10, 0, tzinfo=ist))           # a Monday
    assert not SS.market_open(nse, datetime(2026, 10, 5, 8, 0, tzinfo=ist))
    assert not SS.market_open(nse, datetime(2026, 10, 5, 15, 30, tzinfo=ist))
    assert not SS.market_open(nse, datetime(2026, 10, 4, 11, 0, tzinfo=ist))       # a Sunday
    assert SS.market_open({"market": "CRYPTO"}, datetime(2026, 10, 4, 3, 0, tzinfo=timezone.utc))
    assert not SS.market_open({"market": "NOPE"}, datetime(2026, 10, 5, 10, 0, tzinfo=ist))


def test_thirty_trades_bring_the_verdict_and_the_daily_report_counts_signals(w):
    c = w["client"]
    s = session(c, capital=1_000_000)
    sess = main.manager.sessions[s["id"]]
    for i in range(30):
        sess.last_price, sess._tick_ts = 30000.0 + (i % 3) * 50, 1e18
        sess.on_signal({"session": s["id"], "action": "buy", "qty": 1.0})
        sess.last_price = 30000.0 + (i % 3) * 50 + (80 if i % 4 else -60)
        sess.on_signal({"session": s["id"], "action": "exit"})
    v = c.get(f"/trade/signals/sessions/{s['id']}", headers=PRO).json()["verdict"]
    assert v["ready"] and v["trades"] == 30 and {x["id"] for x in v["checks"]} == {"sample", "luck", "shuffle", "costs"}
    day = datetime.now(timezone.utc).date().isoformat()
    row = daily_report.summarise(sess, day)
    assert row["closed"] == 30 and row["signals"] == {"received": 60, "late": 0, "refused": 0}
    sess.signals.append({"at": datetime.now(timezone.utc).isoformat(), "status": "rejected"})
    text = daily_report.text("Crypto", day, [daily_report.summarise(sess, day)])
    assert "Signals: 61 arrived (1 refused; see the session's signal log)" in text
    # the journal's paper-vs-real reads a signal session like any other
    from app import journal as J
    with sess.lock:
        assert len(J.paper_trades({"state": sess.state()})) == 30


def test_the_pages_api_plan_gates_and_bad_input(w, monkeypatch):
    c = w["client"]
    assert c.get("/trade/signals").status_code == 401
    assert c.post("/trade/signals/sessions", headers=PRO, json={"instrument": "CRYPTO:NOPE-USD"}).status_code == 404
    assert c.post("/trade/signals/sessions", headers=PRO, json={"instrument": BTC, "leverage": 50}).status_code == 422
    assert c.post("/trade/signals/sessions", headers=PRO, json={"instrument": BTC, "product": "margin"}).status_code == 422
    assert c.get("/trade/signals/sessions/not-a-uuid", headers=PRO).status_code == 404
    rel = main.markets.provider("IN").equity("RELIANCE")["id"]
    r = c.post("/trade/signals/sessions", headers=PRO, json={"instrument": rel, "allow_short": True, "product": "delivery"})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "no_delivery_short"
    s = session(c, inst=rel)
    assert s["kind"] == "signal" and s["instrument"]["signal"] is True and s["settings"]["allow_short"] is False
    rows = c.get("/trade/signals", headers=PRO).json()["sessions"]
    assert [r["id"] for r in rows] == [s["id"]]
    assert any(r["id"] == s["id"] for r in c.get("/live/sessions", headers=PRO).json())      # it's a paper session like the others
    payments_live(monkeypatch)
    assert c.post("/trade/signals/hook", headers=BASIC).status_code == 402
    assert c.post("/trade/signals/sessions", headers=BASIC, json={"instrument": BTC}).status_code == 402
    assert c.get("/trade/signals", headers=BASIC).json()["allowed"] is False


def test_guard_limits_hooks_per_url_not_per_shared_address():
    one = guard.caller({"path": "/hooks/signal/" + "a" * 43, "headers": [(b"x-real-ip", b"52.89.214.238")]})
    two = guard.caller({"path": "/hooks/signal/" + "b" * 43, "headers": [(b"x-real-ip", b"52.89.214.238")]})
    assert one[0].startswith("h:") and one[0] != two[0]
    assert guard.caller({"path": "/trade/signals", "headers": [(b"x-real-ip", b"1.2.3.4")]})[0] == "a:1.2.3.4"
