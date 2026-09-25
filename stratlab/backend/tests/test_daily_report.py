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


def single(uid, name, market, trades, qty=0, unreal=0.0, equity=10500.0):
    eng = SimpleNamespace(trades=trades)
    snap = {"kind": "single", "account": {"capital": 10000, "equity": equity, "qty": qty, "unrealised": unreal}}
    return SimpleNamespace(user_id=uid, name=name, market=market, inst={"currency": "INR"}, engine=eng, snapshot=lambda: snap)


def utc(*a):
    return datetime(*a, tzinfo=timezone.utc)


def test_due_times():
    assert R.due("IN", utc(2026, 9, 24, 10, 15)) == "2026-09-24"   # 15:45 IST on a Thursday
    assert R.due("IN", utc(2026, 9, 24, 9, 0)) is None              # 14:30 IST, still open
    assert R.due("IN", utc(2026, 9, 24, 14, 0)) is None             # 19:30 IST, past the window
    assert R.due("IN", utc(2026, 9, 26, 10, 15)) is None            # Saturday
    assert R.due("CRYPTO", utc(2026, 9, 26, 23, 56)) == "2026-09-26"  # crypto reports on weekends too
    assert R.due("US", utc(2026, 9, 24, 20, 15)) == "2026-09-24"    # 16:15 New York
    assert R.due("CSV", utc(2026, 9, 24, 10, 15)) is None


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
    assert subj == "StratLab daily report: India"
    assert "2 trades closed (1 won), +200 INR" in body and "1 open, +120 INR on paper" in body
    assert "Since start: +500 INR (+5.0%)" in body
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
