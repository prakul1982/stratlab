from app import risk


def snap(sid, cur, cap, eq, curve, **kw):
    return {"id": sid, "name": sid, "instrument": {"currency": cur, "market": "IN" if cur == "INR" else "CRYPTO"},
            "account": {"capital": cap, "equity": eq, "trades": 3, **kw.pop("acct", {})}, "equity_curve": curve, **kw}


def test_totals_by_currency_today_worst_day_and_drawdown():
    a = snap("a", "INR", 100000, 103000, [{"t": "2026-09-22T15:00", "eq": 101000}, {"t": "2026-09-23T15:00", "eq": 99000},
                                         {"t": "2026-09-24T15:00", "eq": 104000}], acct={"qty": 10}, last_price=2500)
    b = snap("b", "INR", 50000, 50500, [{"t": "2026-09-23T15:00", "eq": 49000}, {"t": "2026-09-24T12:00", "eq": 50500}],
             kind="group", members=[{"price": 100, "position": {"qty": 20}}, {"price": 50, "position": None}])
    c = snap("c", "USD", 10000, 9800, [{"t": "2026-09-23T10:00", "eq": 9800}], kind="options",
             legs=[{"qty": 75, "mark": 12.0, "open": True}, {"qty": 75, "mark": 30.0, "open": False}])
    out = risk.summary([a, b, c], today="2026-09-24")
    inr = next(x for x in out["currencies"] if x["currency"] == "INR")
    usd = next(x for x in out["currencies"] if x["currency"] == "USD")
    assert inr["sessions"] == 2 and inr["pnl"] == 3500 and inr["open_value"] == 25000 + 2000
    assert inr["today"] == (103000 - 99000) + (50500 - 49000)
    # combined P&L by day: 22nd +1000, 23rd -1000 + -1000 = -2000, 24th +4000 + 500 = 4500
    assert [p["pnl"] for p in inr["curve"]] == [1000, -2000, 4500]
    assert inr["worst_day"] == {"date": "2026-09-23", "pnl": -3000} and inr["best_day"]["pnl"] == 6500
    assert inr["max_drawdown_pct"] < 0
    assert usd["open_value"] == 900 and usd["pnl"] == -200 and usd["worst_day"]["pnl"] == -200
    assert out["sessions"][0]["id"] == "a"                      # biggest open value first


def test_empty():
    assert risk.summary([]) == {"currencies": [], "sessions": []}


def test_deepest_fall_before_the_open_is_dated_the_last_session():
    # 02:50 IST on the 15th: the value is still the 14th's close, so the low is the 14th, not today
    s = snap("a", "INR", 100000, 94000, [{"t": "2026-10-13T15:00", "eq": 100000}, {"t": "2026-10-14T15:00", "eq": 94000}])
    out = risk.summary([s], today="2026-10-15")
    assert out["currencies"][0]["deepest_fall"]["date"] == "2026-10-14"


def test_deepest_fall_between_closes_is_said_as_intraday_and_the_line_stays_day_closes():
    # R31-010: a −3.55L low on the 15th that the close recovered: the summary and the chart must agree on what they claim.
    # R34-002: the line is the day closes (no point for the low, which read as a recovery on the next day); the summary
    # says the low was intraday, with its time and the day's close
    trades = [["2026-10-14T11:00:00+05:30", -300000.0], ["2026-10-15T10:00:00+05:30", -55330.0], ["2026-10-15T14:00:00+05:30", 60000.0]]
    s = snap("a", "INR", 5000000, 5000000 - 295330, [{"t": "2026-10-14T15:00", "eq": 4700000}, {"t": "2026-10-15T15:00", "eq": 4704670}],
             closed=trades, acct={"realised": -295330.0})
    c = risk.summary([s], today="2026-10-16")["currencies"][0]
    f = c["deepest_fall"]
    assert f["date"] == "2026-10-15" and f["pnl"] == -355330.0 and f["intraday"] is True and f["at"] == "10:00"
    assert f["day_close"] == -295330.0
    assert [p["t"][:10] for p in c["curve"]] == ["2026-10-14", "2026-10-15"]          # one point per day, the close
    assert min(p["pnl"] for p in c["curve"]) == -300000.0 and -355330.0 not in [p["pnl"] for p in c["curve"]]
    assert [p["pnl"] for p in c["curve"]][-1] == f["day_close"]                        # the day the summary names closes where it says


def test_deepest_fall_at_a_day_close_is_not_intraday():
    s = snap("a", "INR", 100000, 94000, [{"t": "2026-10-13T15:00", "eq": 100000}, {"t": "2026-10-14T15:00", "eq": 94000}])
    assert "intraday" not in risk.summary([s], today="2026-10-15")["currencies"][0]["deepest_fall"]


def test_the_deepest_fall_counts_the_account_now_not_the_curves_last_point():
    # R83-004: the curve's last point for today lagged the account, and the deepest fall was shallower than "since the start"
    s = snap("a", "INR", 1000000, 482605, [{"t": "2026-10-22T15:30", "eq": 485509}, {"t": "2026-10-23T09:45", "eq": 484945}])
    c = risk.summary([s], today="2026-10-23")["currencies"][0]
    assert c["pnl"] == -517395.0
    assert c["deepest_fall"]["pnl"] == -517395.0 and c["deepest_fall"]["date"] == "2026-10-23"
