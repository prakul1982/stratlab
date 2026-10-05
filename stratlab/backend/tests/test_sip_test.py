"""Test a stock or ETF SIP: the instalment schedule, whole shares with real charges, cash waiting, step-ups, the dip
rules, the deepest fall and time underwater, the lump sum, the spread over start months, the plain-words rule, the plan
gate and the route's bad input."""
from datetime import date, timedelta

import pytest

from app import sip_test as S
from app.config import settings
from app.engine import costs as C
from tests import world

PRO, BASIC, FREE = world.headers("pro-token"), world.headers("basic-token"), world.headers("free-token")


def weekdays(start: str, n: int) -> list[str]:
    d, out = date.fromisoformat(start), []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def leg(prices: dict[str, float], symbol="AAA", weight=1.0, lookback=None) -> dict:
    days = sorted(prices)
    return {"symbol": symbol, "weight": weight, "closes": prices, "days": days,
            "high": S.recent_highs(prices, days, lookback) if lookback else {}}


def plan(**kw) -> dict:
    return {"mode": "amount", "amount": 10000, "qty": 1, "freq": "monthly", "dom": 1, "weekday": 0, "step_up": 0.0, "rule": "plain",
            "dip": 0.1, "extra": 0.5, "brokerage": 0.0, "lookback": 20, **kw}


@pytest.fixture
def w(monkeypatch):
    built = world.build(monkeypatch)
    yield built
    built["close"]()


@pytest.fixture
def paid(monkeypatch):
    for k, v in (("RAZORPAY_KEY_ID", "rzp_live_x"), ("RAZORPAY_KEY_SECRET", "s"), ("RAZORPAY_PLAN_BASIC", "pb"), ("RAZORPAY_PLAN_PRO", "pp")):
        monkeypatch.setattr(settings, k, v)


# ---------- the arithmetic ----------
def test_schedule_lands_on_the_next_trading_day():
    days = weekdays("2024-01-01", 70)                 # 1 Jan 2024 is a Monday
    m = S.schedule(days, "2024-01-01", days[-1], "monthly", dom=6)
    assert m[:3] == ["2024-01-08", "2024-02-06", "2024-03-06"]           # 6 Jan 2024 was a Saturday
    wk = S.schedule(days, "2024-01-03", "2024-01-31", "weekly", weekday=0)
    assert wk == ["2024-01-08", "2024-01-15", "2024-01-22", "2024-01-29"]
    assert S.schedule(days, "2024-01-01", "2024-01-05", "daily") == days[:5]
    assert S.schedule([], "2024-01-01", "2024-02-01", "monthly") == []


def test_whole_shares_with_charges_and_the_rest_waits():
    q, spent, stamp = S.buy(10000, 990.0, 0.0)
    assert q == 10 and spent == pytest.approx(9900 + C.total(C.order_costs("in_eq", "buy", 10, 990.0, 0)))
    assert stamp == pytest.approx(9900 * 0.00015) and spent <= 10000
    assert S.buy(10000, 999.0, 0.0)[0] == 9                     # ten would cost more than ₹10,000 with charges
    assert S.buy(500, 999.0, 0.0)[0] == 0                       # not enough for one share
    q, spent, _ = S.buy(10000, 999.0, 20.0)                     # ₹20 brokerage and its GST come out first
    assert q == 9 and spent <= 10000


def test_monthly_sip_on_a_flat_price_puts_in_and_keeps_its_value_less_charges():
    days = weekdays("2023-01-02", 260)
    r = S.simulate([leg({d: 100.0 for d in days})], plan(dom=2), days[0], days[-1])
    assert r["instalments"] == 12 and r["invested"] == 120000
    assert r["legs"][0]["units"] * 100 + r["charges"] + r["cash_waiting"] == pytest.approx(120000, abs=0.01) and r["value"] == pytest.approx(120000 - r["charges"], abs=0.01)
    assert r["charges"] > 0 and r["stamp"] == pytest.approx(r["legs"][0]["units"] * 100 * 0.00015, abs=0.01)
    assert -1 < r["deepest_fall_pct"] <= 0 and r["xirr"] < 0      # only the charges are lost
    assert r["series"][-1]["invested"] == 120000


def test_step_up_raises_each_year():
    days = weekdays("2020-01-01", 800)
    r = S.simulate([leg({d: 10.0 for d in days})], plan(step_up=0.10), days[0], days[-1])
    sched = S.schedule(days, days[0], days[-1], "monthly", 1)
    want = sum(10000 * 1.1 ** S.anniversaries(sched[0], d) for d in sched)
    assert r["invested"] == pytest.approx(want, abs=1)
    assert sum(1 for d in sched if S.anniversaries(sched[0], d) == 0) == 12      # the first year at ₹10,000
    assert S.anniversaries("2020-02-29", "2021-02-28") == 0 and S.anniversaries("2020-01-01", "2021-01-01") == 1


def test_split_across_two_and_quantity_mode():
    days = weekdays("2023-01-02", 130)
    a, b = leg({d: 100.0 for d in days}, "AAA", 0.6), leg({d: 50.0 for d in days}, "BBB", 0.4)
    r = S.simulate([a, b], plan(), days[0], days[-1])
    spent = [x["spent"] for x in r["legs"]]
    assert spent[0] / sum(spent) == pytest.approx(0.6, abs=0.01) and r["legs"][1]["units"] >= 5 * 79
    q = S.simulate([leg({d: 100.0 for d in days})], plan(mode="qty", qty=3), days[0], days[-1])
    assert q["legs"][0]["units"] == 3 * q["instalments"] and q["invested"] == pytest.approx(300 * q["instalments"] + q["charges"], abs=0.01)


def path_with_a_dip(days: list[str]) -> dict[str, float]:
    """100, falling to 80 over the middle third, back to 100."""
    n = len(days)
    out = {}
    for i, d in enumerate(days):
        if i < n // 3:
            p = 100.0
        elif i < n // 2:
            p = 100 - 20 * (i - n // 3) / (n // 2 - n // 3)
        else:
            p = 80 + 20 * (i - n // 2) / (n - n // 2)
        out[d] = round(p, 4)
    return out


def test_only_on_dips_waits_then_buys_with_all_the_cash():
    days = weekdays("2023-01-02", 260)
    prices = path_with_a_dip(days)
    r = S.simulate([leg(prices, lookback=20)], plan(rule="only_dips", dip=0.05), days[0], days[-1])
    p = S.simulate([leg(prices)], plan(), days[0], days[-1])
    assert r["invested"] == p["invested"]
    assert r["legs"][0]["buys"] < p["legs"][0]["buys"]
    assert r["legs"][0]["avg_price"] < p["legs"][0]["avg_price"]            # every buy came 5% below the 20-day high
    assert r["cash_waiting"] > 0                                           # the last instalments, no dip after them
    flat = S.simulate([leg({d: 100.0 for d in days}, lookback=20)], plan(rule="only_dips"), days[0], days[-1])
    assert flat["legs"][0]["units"] == 0 and flat["value"] == flat["invested"]   # never a dip: all cash


def test_extra_on_dips_adds_to_the_instalment():
    days = weekdays("2023-01-02", 260)
    prices = path_with_a_dip(days)
    r = S.simulate([leg(prices, lookback=20)], plan(rule="extra_on_dips", dip=0.03, extra=0.5, freq="weekly"), days[0], days[-1])
    p = S.simulate([leg(prices)], plan(freq="weekly"), days[0], days[-1])
    extra = r["invested"] - p["invested"]
    assert extra > 0 and extra % 5000 == pytest.approx(0, abs=0.01)


def test_deepest_fall_and_underwater():
    assert S.drawdown([1, 1.2, 0.9, 1.3]) == pytest.approx(-0.25)
    days = ["2024-01-01", "2024-01-10", "2024-02-01", "2024-03-01"]
    assert S.underwater(days, [100, 90, 95, 120], [100, 100, 100, 100]) == (22, "2024-01-10", "2024-02-01")
    assert S.underwater(days, [100, 100, 100, 100], [100, 100, 100, 100])[0] == 0


def test_recent_high_is_the_rolling_max():
    days = weekdays("2024-01-01", 6)
    closes = dict(zip(days, [5, 9, 7, 6, 8, 4]))
    h = S.recent_highs(closes, days, 3)
    assert days[0] not in h and h[days[2]] == 9 and h[days[4]] == 8 and h[days[5]] == 8


def test_spread_over_start_months_and_the_dip_check():
    days = weekdays("2018-01-01", 1700)
    prices = {d: 100 * (1 + 0.0004 * i) * (1 + 0.1 * ((i // 60) % 2 * -1)) for i, d in enumerate(days)}
    legs = [leg(prices, lookback=20)]
    s = S.spread(legs, plan(), 2, days[0], days[-1])
    assert s["count"] >= 30 and s["worst"]["xirr"] <= s["median"] <= s["best"]["xirr"] and "dip" not in s
    d = S.spread(legs, plan(rule="only_dips", dip=0.05), 2, days[0], days[-1])
    assert d["dip"]["compared"] == d["count"] and 0 <= d["dip"]["beat"] <= d["count"]
    assert S.spread(legs, plan(), 10, days[0], days[-1]) is None           # no full 10 years in the history


def test_plain_words():
    a, b = leg({}, "NIFTYBEES", 0.7), leg({}, "GOLDBEES", 0.3)
    t = S.words(plan(step_up=0.1, rule="only_dips", dip=0.08, lookback=60), [a, b])
    assert t.startswith("On day 1 of every month (or the next trading day), invest ₹10,000 in 70% NIFTYBEES, 30% GOLDBEES")
    assert "Raise the amount by 10% each year." in t and "8% below the highest close of the last 60 trading days" in t
    assert S.words(plan(mode="qty", qty=2, freq="weekly", weekday=2), [leg({}, "INFY")]).startswith("Every Wednesday (or the next trading day), purchase 2 shares in INFY.")


# ---------- the route ----------
def inst(c, q):
    return c.get(f"/instruments/search?q={q}&market=IN", headers=PRO).json()[0]["id"]


def test_route_runs_a_plain_sip_with_a_lump_sum_and_a_spread(w):
    c = w["client"]
    a, b = inst(c, "INFY"), inst(c, "TCS")
    r = c.post("/invest/sip-test", headers=PRO, json={"legs": [{"inst_id": a, "weight": 60}, {"inst_id": b, "weight": 40}], "amount": 10000,
                                                      "years": 3, "step_up": 5})
    assert r.status_code == 200, r.text
    d = r.json()
    res = d["result"]
    assert res["instalments"] >= 35 and res["invested"] > 360000 and res["value"] > 0 and res["charges"] > 0
    assert [x["symbol"] for x in res["legs"]] == ["INFY", "TCS"] and res["legs"][0]["weight"] == 60
    assert d["lump_sum"]["invested"] == res["invested"] and d["window"]["years"] == 3
    assert d["spread"] and d["spread"]["count"] >= 12 and d["full"] is True
    assert "60% INFY, 40% TCS" in d["words"] and d["plain"] is None
    dip = c.post("/invest/sip-test", headers=PRO, json={"legs": [{"inst_id": a}], "years": 2, "rule": "only_dips", "dip": 5, "lookback": 60}).json()
    assert dip["plain"]["invested"] == dip["result"]["invested"] and "dip" in dip["spread"]


def test_free_runs_the_plain_sip_and_dip_rules_are_basic(w, paid):
    c = w["client"]
    a = inst(c, "INFY")
    d = c.post("/invest/sip-test", headers=FREE, json={"legs": [{"inst_id": a}], "years": 2}).json()
    assert d["full"] is False and d["spread"] is None and d["result"]["invested"] > 0
    r = c.post("/invest/sip-test", headers=FREE, json={"legs": [{"inst_id": a}], "rule": "only_dips"})
    assert r.status_code == 402 and "Basic" in r.text
    assert c.post("/invest/sip-test", headers=BASIC, json={"legs": [{"inst_id": a}], "years": 1, "rule": "only_dips"}).status_code == 200


def test_bad_input_is_a_4xx(w):
    c = w["client"]
    a, b = inst(c, "INFY"), inst(c, "TCS")
    post = lambda body: c.post("/invest/sip-test", headers=PRO, json=body)       # noqa: E731
    assert post({"legs": []}).status_code == 422
    assert post({"legs": [{"inst_id": a}] * 11}).status_code == 422
    assert post({"legs": [{"inst_id": a}, {"inst_id": a}]}).status_code == 400
    assert post({"legs": [{"inst_id": a, "weight": 50}, {"inst_id": b, "weight": 20}]}).status_code == 400
    assert post({"legs": [{"inst_id": a}], "amount": -5}).status_code == 422
    assert post({"legs": [{"inst_id": a}], "freq": "yearly"}).status_code == 422
    assert post({"legs": [{"inst_id": a}], "lookback": 7, "rule": "only_dips"}).status_code == 400
    assert post({"legs": [{"inst_id": a}], "mode": "qty", "rule": "only_dips"}).status_code == 400
    assert post({"legs": [{"inst_id": "IN:999999999"}]}).status_code == 404
    assert post({"legs": [{"inst_id": a}], "start": "2099-01-01"}).status_code == 400
    fut = [r["id"] for r in c.get("/instruments/search?q=NIFTY&market=IN", headers=PRO).json() if r.get("type") == "FUT"]
    if fut:
        assert post({"legs": [{"inst_id": fut[0]}]}).status_code == 400
    assert c.post("/invest/sip-test", json={"legs": [{"inst_id": a}]}).status_code == 401
