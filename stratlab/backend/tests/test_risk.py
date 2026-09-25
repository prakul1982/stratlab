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
