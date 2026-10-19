import json
from datetime import datetime, timezone
from types import SimpleNamespace

from app import daily_report as R


class FakeDB:
    def __init__(self, profiles):
        self.settings, self.profiles = {}, profiles

    def get_setting(self, k):
        return self.settings.get(k)

    def set_setting(self, k, v):
        self.settings[k] = v

    def get_profile(self, uid):
        return self.profiles[uid]


def single(uid, name, market, trades, qty=0, unreal=0.0, equity=10500.0, tick="2026-09-24T15:20:00+05:30"):
    eng = SimpleNamespace(trades=trades)
    snap = {"kind": "single", "account": {"capital": 10000, "equity": equity, "qty": qty, "unrealised": unreal}}
    return SimpleNamespace(user_id=uid, name=name, market=market, inst={"currency": "INR"}, engine=eng, snapshot=lambda: snap,
                           last_tick_at=tick)


def utc(*a):
    return datetime(*a, tzinfo=timezone.utc)


def test_due_times():
    assert R.due("IN", utc(2026, 9, 24, 10, 15)) == "2026-09-24"   # 15:45 IST on a Thursday
    assert R.due("IN", utc(2026, 9, 24, 9, 0)) is None              # 14:30 IST, still open
    assert R.due("IN", utc(2026, 9, 24, 10, 14)) is None            # 15:44 IST: futures and options stop at 15:40
    assert R.due("IN", utc(2026, 9, 24, 14, 0)) is None             # 19:30 IST, past the window
    assert R.due("IN", utc(2026, 9, 26, 10, 15)) is None            # Saturday
    assert R.due("CRYPTO", utc(2026, 9, 26, 23, 56)) == "2026-09-26"  # crypto reports on weekends too
    assert R.due("US", utc(2026, 9, 24, 20, 15)) == "2026-09-24"    # 16:15 New York
    assert R.due("CSV", utc(2026, 9, 24, 10, 15)) is None


def ist(*a):
    from zoneinfo import ZoneInfo
    return datetime(*a, tzinfo=ZoneInfo("Asia/Kolkata"))


def test_the_mcx_report_follows_its_close_even_past_midnight():
    # October (Wed 14th): MCX closes 23:30, the report goes out from 23:40
    assert R.due("MCX", ist(2026, 10, 14, 23, 35)) is None
    assert R.due("MCX", ist(2026, 10, 14, 23, 40)) == "2026-10-14"
    assert R.due("MCX", ist(2026, 10, 14, 23, 46)) == "2026-10-14"
    assert R.due("MCX", ist(2026, 10, 15, 0, 5)) == "2026-10-14"        # the window doesn't collapse at midnight
    assert R.due("MCX", ist(2026, 10, 15, 1, 0)) == "2026-10-14"
    assert R.due("MCX", ist(2026, 10, 15, 2, 41)) is None               # past the 3 hours
    # from the first Sunday of November (1 Nov) MCX closes at 23:55 (options/data.py expiry_time): after it, past midnight
    assert R.due("MCX", ist(2026, 11, 11, 23, 40)) is None
    assert R.due("MCX", ist(2026, 11, 11, 23, 46)) is None              # the old 23:45 send came before the close
    assert R.due("MCX", ist(2026, 11, 11, 23, 59)) is None
    assert R.due("MCX", ist(2026, 11, 12, 0, 5)) == "2026-11-11"
    assert R.due("MCX", ist(2026, 11, 12, 1, 0)) == "2026-11-11"
    assert R.due("MCX", ist(2026, 11, 12, 3, 6)) is None
    # a Friday's report after midnight is on Saturday; there is none for the Saturday itself
    assert R.due("MCX", ist(2026, 11, 14, 0, 5)) == "2026-11-13"
    assert R.due("MCX", ist(2026, 11, 14, 23, 50)) is None and R.due("MCX", ist(2026, 11, 15, 0, 10)) is None


def test_the_crypto_report_runs_into_the_next_utc_day():
    assert R.due("CRYPTO", utc(2026, 10, 14, 23, 50)) is None
    assert R.due("CRYPTO", utc(2026, 10, 14, 23, 56)) == "2026-10-14"
    assert R.due("CRYPTO", utc(2026, 10, 15, 0, 10)) == "2026-10-14"
    assert R.due("CRYPTO", utc(2026, 10, 15, 1, 0)) == "2026-10-14"
    assert R.due("CRYPTO", utc(2026, 10, 15, 2, 56)) is None


def test_a_report_sent_after_midnight_still_counts_the_day_that_ended_and_goes_once():
    day = "2026-10-14"
    trades = [{"exit_t": f"{day}T10:15:00+00:00", "pnl": 300.0}, {"exit_t": "2026-10-15T00:02:00+00:00", "pnl": 999.0}]
    s = single("u1", "BTC", "CRYPTO", trades, tick="2026-10-15T00:09:30+00:00")      # prices already of the new day
    sent = []
    rep = R.Reporter(FakeDB({"u1": {}}))
    run = lambda now: rep.run([s], now, can_alert=lambda p: True, market_name=str, send=lambda p, subj, body: sent.append(body))
    assert run(utc(2026, 10, 14, 23, 56)) == [("u1", "CRYPTO")]
    assert "1 trade closed (1 won), +₹300" in sent[0]
    assert run(utc(2026, 10, 15, 0, 10)) == [] and len(sent) == 1
    late = R.Reporter(FakeDB({"u1": {}}))                                             # the server was down at 23:56
    assert late.run([s], utc(2026, 10, 15, 0, 10), can_alert=lambda p: True, market_name=str, send=lambda p, subj, body: sent.append(body)) \
        == [("u1", "CRYPTO")] and "+₹300" in sent[1]


def test_report_sent_once_with_the_days_numbers():
    day = "2026-09-24"
    trades = [{"exit_t": f"{day}T10:15:00+05:30", "pnl": 300.0}, {"exit_t": f"{day}T13:00:00+05:30", "pnl": -100.0},
              {"exit_t": "2026-09-23T13:00:00+05:30", "pnl": 999.0}]
    a = single("u1", "EMA on NIFTY", "IN", trades, qty=50, unreal=120.0)
    b = single("u1", "RSI on BTC", "CRYPTO", [])
    c = single("u2", "Quiet", "IN", [])
    db = FakeDB({"u1": {"alerts_enabled": True}, "u2": {"alerts_enabled": False}})
    sent = []
    rep = R.Reporter(db)
    run = lambda now: rep.run([a, b, c], now, can_alert=lambda p: p["alerts_enabled"], market_name=lambda m: {"IN": "India"}.get(m, m),
                              send=lambda p, subj, body: sent.append((subj, body)))
    assert run(utc(2026, 9, 24, 10, 15)) == [("u1", "IN")]          # only India is due, and u2 has alerts off
    subj, body = sent[0]
    assert subj == "StratLab daily report: India, Thu 24 Sep"          # the day in the subject (R69-006)
    assert "2 trades closed (1 won), +₹200" in body and "1 open, +₹120 on paper" in body      # ₹, as the app writes it
    assert "Since start: +₹500 (+5.0%)" in body
    assert run(utc(2026, 9, 24, 10, 20)) == []                     # not twice
    assert R.Reporter(db).run([a], utc(2026, 9, 24, 10, 25), can_alert=lambda p: True, market_name=str,
                              send=lambda *x: sent.append(x)) == []  # nor after a restart
    assert len(sent) == 1


def test_opt_out():
    db = FakeDB({"u1": {"alerts_enabled": True}})
    db.set_setting(R.PREFS + "u1", '{"daily_report": false}')
    out = R.Reporter(db).run([single("u1", "x", "IN", [])], utc(2026, 9, 24, 10, 15), can_alert=lambda p: True,
                             market_name=str, send=lambda *x: None)
    assert out == [] and R.wants_report(db, "u1") is False and R.wants_report(db, "nobody") is True


def test_group_and_options_sessions():
    day = "2026-09-24"
    m1 = SimpleNamespace(engine=SimpleNamespace(trades=[{"exit_t": day + "T10:00", "pnl": 50.0}]))
    m2 = SimpleNamespace(engine=SimpleNamespace(trades=[{"exit_t": day + "T11:00", "pnl": -20.0}]))
    g = SimpleNamespace(kind="group", name="Group", market="IN", inst={}, members=[m1, m2],
                        snapshot=lambda: {"kind": "group", "account": {"capital": 1000, "equity": 1030, "open": 2, "unrealised": 5}})
    r = R.summarise(g, day)
    assert (r["closed"], r["wins"], r["pnl"], r["open"], r["currency"]) == (2, 1, 30.0, 2, "INR")
    o = SimpleNamespace(name="Iron fly", market="IN", inst={"currency": "INR"},
                        engine=SimpleNamespace(trades=[{"closed": day + "T14:00:00+05:30", "pnl": 800.0}]),
                        snapshot=lambda: {"kind": "options", "position": None, "account": {"capital": 1000, "equity": 1800, "unrealised": 0}})
    r = R.summarise(o, day)
    assert (r["closed"], r["pnl"], r["open"]) == (1, 800.0, 0)


def test_no_report_on_a_holiday():
    db = FakeDB({"u1": {"alerts_enabled": True}})
    sent = []
    idle = single("u1", "EMA", "IN", [], tick="2026-09-23T15:20:00+05:30")     # last price was yesterday
    assert R.Reporter(db).run([idle], utc(2026, 9, 24, 10, 15), can_alert=lambda p: True, market_name=str,
                              send=lambda *x: sent.append(x)) == [] and not sent
    us = single("u1", "SPY dips", "US", [], tick="2026-09-24T20:05:00+00:00")   # 16:05 New York
    assert R.traded_today([us], "US", "2026-09-24") and not R.traded_today([us], "US", "2026-09-25")


def test_a_non_indian_session_without_a_currency_reports_in_dollars():
    s = single("u1", "US paper", "US", [])
    s.inst = {}
    assert R.summarise(s, "2026-09-24")["currency"] == "USD"
    s.market = "IN"
    assert R.summarise(s, "2026-09-24")["currency"] == "INR"


def test_a_report_isnt_sent_twice_after_the_lease_moves_between_containers(monkeypatch):
    db = FakeDB({"u1": {"id": "u1"}, "u2": {"id": "u2"}})
    sent = []
    kw = dict(can_alert=lambda p: True, send=lambda p, s, b: sent.append(p["id"]), market_name=lambda m: m)
    monkeypatch.setattr(R, "wants_report", lambda d, u: True)
    monkeypatch.setattr(R, "summarise", lambda s, day: {})
    monkeypatch.setattr(R, "text", lambda *a: "x")
    now = utc(2026, 10, 15, 20, 15)                                   # 16:15 New York
    sess = lambda uid: SimpleNamespace(user_id=uid, name=uid, market="US", last_tick_at=utc(2026, 10, 15, 20, 5).isoformat())
    a, b = R.Reporter(db), R.Reporter(db)
    a.run([sess("u1")], now, **kw)
    b.run([sess("u2")], now, **kw)
    a.run([sess("u1"), sess("u2")], now, **kw)                        # the lease is back with A
    assert sorted(sent) == ["u1", "u2"]
    assert set(json.loads(db.settings[R.SETTING])) == {"u1:US", "u2:US"}
