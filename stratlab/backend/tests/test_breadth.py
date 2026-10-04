"""Market breadth: each measure on a small made-up market with every number worked out by hand, the run (only final
candles, the first run's two years and later runs' recent months, a source that is down), the daily job's run
marker, the page's plan gate, and facts-only wording."""
import json
import re
from datetime import date, datetime, timedelta, timezone

import pytest

from app import breadth, db
from app.config import settings
from tests import world as W
from tests.fake_db import headers

PROVIDERS = re.compile(r"kite|zerodha|yahoo|screener|finnhub|edgar|nseindia|bseindia", re.I)
ADVICE = re.compile(r"\b(buy|sell|hold|accumulate|avoid|best|cheap|expensive|bullish|bearish|target|should)\b", re.I)
IST_OPEN = datetime(2026, 10, 1, 5, 0, tzinfo=timezone.utc)        # Thursday 1 Oct, 10:30 IST: the market is open
LAST = "2026-09-30"                                                 # so the last final candle is Wednesday's


def weekdays(end: str, n: int) -> list[str]:
    """The n weekdays up to and including `end`, oldest first."""
    d, out = date.fromisoformat(end), []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d -= timedelta(days=1)
    return out[::-1]


def bars(closes, end=LAST, highs=None, lows=None, vol=1000.0):
    days = weekdays(end, len(closes))
    return [{"t": f"{d}T00:00:00+05:30", "o": c, "h": (highs or closes)[i], "l": (lows or closes)[i], "c": c, "v": vol}
            for i, (d, c) in enumerate(zip(days, closes))]


N = 900                                                             # weekdays of made-up history: about 3.5 years


def market(end=LAST, partial=True):
    """Three stocks. UP rises by 1 a day, DOWN falls by 1 a day, FLAT sits at 100 and jumps 5% on the last day.
    With `partial`, each also has a half-made candle for the day after `end` (which must be ignored)."""
    up = [100.0 + i for i in range(N)]
    down = [1000.0 - i for i in range(N)]
    flat = [100.0] * (N - 1) + [105.0]
    out = {"UP": bars(up, end, vol=1000.0), "DOWN": bars(down, end, vol=3000.0), "FLAT": bars(flat, end, vol=500.0)}
    if partial:
        nxt = (date.fromisoformat(end) + timedelta(days=1)).isoformat()
        for s in out:
            out[s].append({"t": f"{nxt}T00:00:00+05:30", "o": 1, "h": 1, "l": 1, "c": 1.0, "v": 1})
    return out


@pytest.fixture
def mem(monkeypatch):
    """The in-memory database, the three-stock market as every NSE group, and a sector for each stock."""
    store: dict = {}
    monkeypatch.setattr(db, "get_setting", lambda k: store.get(k))
    monkeypatch.setattr(db, "set_setting", lambda k, v: store.__setitem__(k, v))
    monkeypatch.setattr(breadth, "MIN_MEMBERS", 1)
    monkeypatch.setattr(breadth, "MIN_SECTOR", 1)
    return store


def cut(rows, days):
    """What a source gives for `days` calendar days back from the last candle."""
    if not rows:
        return rows
    first = (date.fromisoformat(rows[-1]["t"][:10]) - timedelta(days=days)).isoformat()
    return [b for b in rows if b["t"][:10] >= first]


def runner(data=None, calls=None, index=None, fail=()):
    data = data or market()

    def load(region, sym, days):
        if calls is not None:
            calls.append((sym, days))
        if sym in fail:
            raise RuntimeError("source down")
        return cut(data[sym], days)

    def index_bars(region, sym, days):
        return cut(index if index is not None else bars([20000.0 + i for i in range(N)]), days)

    return breadth.Runner(load, index_bars, lambda name: ["UP", "DOWN", "FLAT"], lambda: [{"symbol": s} for s in ("UP", "DOWN", "FLAT")],
                          sectors=lambda region: {"UP": "Tech", "DOWN": "Tech", "FLAT": "Energy"}, gap=0)


# ---------- one stock ----------
def test_daily_moves_counted():
    f = breadth.stock_flags(bars([100.0, 105.0, 100.0, 100.0]))
    assert f["has"].tolist() == [0, 1, 1, 1]
    assert f["adv"].tolist() == [0, 1, 0, 0] and f["dec"].tolist() == [0, 0, 1, 0] and f["unch"].tolist() == [0, 0, 0, 1]
    assert f["up4"].tolist() == [0, 1, 0, 0]                    # +5%
    assert f["dn4"].tolist() == [0, 0, 1, 0]                    # 100/105 - 1 = -4.76%
    assert f["av"].tolist() == [0, 1000, 0, 0] and f["dv"].tolist() == [0, 0, 1000, 0]


def test_a_move_just_under_four_percent_is_not_counted():
    f = breadth.stock_flags(bars([100.0, 103.9, 100.0]))
    assert f["up4"].sum() == 0 and f["dn4"].sum() == 0


def test_moving_averages_need_their_days():
    f = breadth.stock_flags(bars([float(i) for i in range(1, 26)]))
    # day 19 (index 18): only 19 closes, no 20-day average yet; day 20 on: close above it (rising)
    assert f["n20"].iloc[18] == 0 and f["n20"].iloc[19] == 1
    assert f["a20"].iloc[24] == 1                               # 25 > mean(6..25) = 15.5
    assert f["n50"].sum() == 0 and f["n200"].sum() == 0


def test_close_below_its_average():
    closes = [100.0] * 49 + [90.0]                              # mean of the 50 = 99.8, close 90 under it
    f = breadth.stock_flags(bars(closes))
    assert f["n50"].iloc[-1] == 1 and f["a50"].iloc[-1] == 0


def test_52_week_high_and_low_need_a_full_year():
    up = breadth.stock_flags(bars([100.0 + i for i in range(260)]))
    assert up["n52"].iloc[250] == 0 and up["n52"].iloc[251] == 1        # 252 sessions make the window
    assert up["hi"].iloc[-1] == 1 and up["lo"].iloc[-1] == 0
    down = breadth.stock_flags(bars([500.0 - i for i in range(260)]))
    assert down["lo"].iloc[-1] == 1 and down["hi"].iloc[-1] == 0


def test_52_week_high_uses_the_days_high():
    closes = [100.0] * 260
    highs = [101.0] * 259 + [102.0]                             # the close is flat but the day's high is a new one
    f = breadth.stock_flags(bars(closes, highs=highs))
    assert f["hi"].iloc[-1] == 1 and f["hi"].iloc[-2] == 0


def test_stage_two_counted():
    f = breadth.stock_flags(bars([100.0 + i for i in range(300)]))
    assert f["ns"].iloc[-1] == 1 and f["s2"].iloc[-1] == 1
    g = breadth.stock_flags(bars([500.0 - i for i in range(300)]))
    assert g["ns"].iloc[-1] == 1 and g["s2"].iloc[-1] == 0


def test_bad_candles_are_dropped_and_later_days_cut():
    raw = bars([100.0, 101.0, 102.0])
    raw.insert(1, {"t": raw[0]["t"], "c": "x"})                 # unreadable
    raw.append({"t": "2026-10-01T00:00:00+05:30", "c": 0})     # a zero close
    f = breadth.stock_flags(raw, through=LAST)
    assert len(f) == 3 and f["adv"].sum() == 2
    assert breadth.stock_flags(bars([100.0])) is None
    assert breadth.stock_flags([]) is None


# ---------- the measures from the counts ----------
def rows_from(pairs, **extra):
    """Stored rows from (advances, declines) pairs; everything else zero unless given."""
    out = {}
    for i, (a, d) in enumerate(pairs):
        r = dict.fromkeys(breadth.COLS, 0)
        r.update(has=a + d, adv=a, dec=d, idx=None)
        for k, v in extra.items():
            r[k] = v[i]
        out[f"2026-01-{i + 1:02d}"] = [r[c] for c in breadth.COLS]
    return out


def test_ad_line_ratio_and_mcclellan_by_hand():
    s = breadth.series(rows_from([(3, 1), (1, 3), (2, 2)]))
    assert s["net"] == [2, -2, 0]
    assert s["ad_line"] == [2, 0, 0]
    assert s["ad_ratio"] == [3.0, 0.333, 1.0]
    # (adv - dec) / (adv + dec) x 1000 = 500, -500, 0
    # 19-day EMA (k = 0.1): 500, 400, 360; 39-day EMA (k = 0.05): 500, 450, 427.5
    assert s["mcclellan"] == [0.0, -50.0, -67.5]
    assert s["summation"] == [0.0, -50.0, -117.5]
    # 10-day EMA (k = 2/11) of adv / (adv + dec): .75, .65909, .63017
    assert s["thrust"] == [75.0, 65.91, 63.02]


def test_percent_measures_and_trin_by_hand():
    rows = rows_from([(2, 1), (0, 3)], a50=[2, 1], n50=[3, 3], a20=[1, 0], n20=[4, 4], a200=[0, 0], n200=[0, 0],
                     s2=[1, 1], ns=[3, 2], hi=[2, 0], lo=[1, 3], up4=[1, 0], dn4=[0, 2], av=[1500.0, 0.0], dv=[3000.0, 900.0])
    s = breadth.series(rows)
    assert s["pct50"] == [66.67, 33.33] and s["pct20"] == [25.0, 0.0]
    assert s["pct200"] == [None, None]                          # no stock with 200 days: no share at all, not 0%
    assert s["stage2"] == [33.33, 50.0]
    assert s["net_highs"] == [1, -3] and s["up4"] == [1, 0] and s["down4"] == [0, 2]
    assert s["trin"] == [4.0, None]                             # (2/1) / (1500/3000); no advances: no TRIN
    assert s["ad_ratio"][1] == 0.0


def test_thrust_days():
    assert breadth.thrusts(list("abcdef"), [35, 50, 62, 63, 30, 70]) == ["c", "f"]
    assert breadth.thrusts(list("abc"), [45, 55, 62]) == []     # never under 40% in the window


def test_today_with_change():
    t = breadth.today(breadth.series(rows_from([(3, 1), (1, 3)])))
    assert t["day"] == "2026-01-02" and t["prev_day"] == "2026-01-01"
    assert t["adv"] == {"value": 1, "prev": 3, "change": -2}
    assert t["mcclellan"]["change"] == -50.0
    assert breadth.today(breadth.series({})) is None


def test_half_loaded_days_left_out():
    import pandas as pd
    total = pd.DataFrame([[100] + [0] * 18, [98] + [0] * 18, [10] + [0] * 18], columns=list(breadth.FIELDS),
                         index=["2026-01-01", "2026-01-02", "2026-01-05"])
    assert list(breadth.rows_of(total)) == ["2026-01-01", "2026-01-02"]


def test_merge_keeps_old_days_before_the_lookback():
    old = {"2026-01-01": ["old"], "2026-01-02": ["old"]}
    new = {"2026-01-01": ["new"], "2026-01-02": ["new"], "2026-01-03": ["new"]}
    assert breadth.merge(old, new, "2026-01-02") == {"2026-01-01": ["old"], "2026-01-02": ["new"], "2026-01-03": ["new"]}


# ---------- the run ----------
def test_run_counts_the_made_up_market(mem):
    calls = []
    out = runner(calls=calls).run("IN", IST_OPEN)
    assert out["ok"] and out["as_of"] == LAST and out["loaded"] == 3
    assert {s for s, _ in calls} == {"UP", "DOWN", "FLAT"} and len(calls) == 3        # one read per stock, not per group
    assert all(d == breadth.BACKFILL_DAYS for _, d in calls)                          # the first run reads two years
    v = breadth.view("nifty500", "all")
    t = v["today"]
    assert t["day"] == LAST                                     # the half-made candle of 1 Oct is not counted
    got = {k: t[k]["value"] for k in ("adv", "dec", "unch", "up4", "down4", "stocks", "pct50", "pct200", "stage2", "trin")}
    # UP and FLAT rose (FLAT by 5%), DOWN fell; UP and FLAT (105 against an average of about 100) are above both
    # averages; only UP is in Stage 2 (FLAT's average is flat: Stage 1); TRIN = (2/1) / ((1000+500)/3000) = 4
    assert got == {"adv": 2, "dec": 1, "unch": 0, "up4": 1, "down4": 0, "stocks": 3, "pct50": 66.67, "pct200": 66.67,
                   "stage2": 33.33, "trin": 4.0}
    assert t["highs"]["value"] == 2 and t["lows"]["value"] == 1                       # UP and FLAT at highs; DOWN at a low
    assert t["adv"]["prev"] == 1 and t["dec"]["prev"] == 1 and t["unch"]["prev"] == 1   # the day before FLAT was unchanged
    h = v["history"]
    assert h["days"][0] >= (date.fromisoformat(LAST) - timedelta(days=breadth.BACKFILL_DAYS - breadth.LOOKBACK_DAYS)).isoformat()
    assert len(h["days"]) > 450                                 # about two years of days
    assert h["index"][-1] == 20000.0 + N - 1
    assert all(x is not None for x in h["pct200"])              # every stored day has its full lookback
    sec = v["sectors"]
    assert [c["label"] for c in sec["columns"]] == ["Today", "1 week ago", "1 month ago", "3 months ago"]
    by = {r["sector"]: r for r in sec["rows"]}
    assert by["Tech"]["stocks"] == 2 and by["Tech"]["values"][0] == 50.0              # UP above, DOWN below
    assert by["Energy"]["values"][0] == 100.0 and by["Energy"]["values"][1] == 0.0    # FLAT at 100 a week ago: not above
    for g in ("nse_all", "nifty50", "midcap150", "smallcap250"):
        assert breadth.view(g, "1y")["today"]["adv"]["value"] == 2
    st = breadth.status()["IN"]
    assert st["loaded"] == 3 and st["as_of"] == LAST


def test_later_runs_read_recent_months_and_keep_old_days(mem):
    runner().run("IN", IST_OPEN)
    first = breadth.load_hist("nifty500")
    calls = []
    later = datetime(2026, 10, 2, 14, 0, tzinfo=timezone.utc)                         # Friday evening IST
    runner(market("2026-10-02", partial=False), calls=calls).run("IN", later)
    assert all(d == breadth.RECENT_DAYS for _, d in calls)
    rows = breadth.load_hist("nifty500")
    assert max(rows) == "2026-10-02" and min(rows) == min(first)
    assert rows[min(first)] == first[min(first)]                # days before the recent window stand as stored


def test_a_failing_stock_is_left_out(mem):
    out = runner(fail={"DOWN"}).run("IN", IST_OPEN)
    assert out["failed"] == 1 and out["loaded"] == 2
    assert breadth.view("nifty500")["today"]["dec"]["value"] == 0


def test_source_down_keeps_the_stored_history(mem):
    runner().run("IN", IST_OPEN)
    before = mem[breadth.HIST_KEY + "nifty500"]
    with pytest.raises(RuntimeError):
        runner(fail={"UP", "DOWN", "FLAT"}).run("IN", IST_OPEN)
    assert mem[breadth.HIST_KEY + "nifty500"] == before


def test_index_unavailable_still_counts(mem):
    r = runner()
    r.index_bars = lambda *a: (_ for _ in ()).throw(RuntimeError("down"))
    r.run("IN", IST_OPEN)
    v = breadth.view("nifty500")
    assert v["today"]["adv"]["value"] == 2 and v["history"]["index"][-1] is None


def test_runs_one_at_a_time(mem):
    r = runner()
    r.lock.acquire()
    assert r.run("IN", IST_OPEN)["ok"] is False
    r.lock.release()


def test_members_fall_back_to_the_last_good_list(mem, monkeypatch):
    monkeypatch.setattr(breadth, "MIN_MEMBERS", 20)
    good = [f"S{i}" for i in range(30)]
    assert breadth.members("nifty500", lambda n: good) == good
    assert breadth.members("nifty500", lambda n: (_ for _ in ()).throw(RuntimeError("403"))) == good
    assert breadth.members("nifty500", lambda n: ["ONLY"]) == good                    # a short list is a broken answer
    assert len(breadth.members("nifty50", None)) == 50                                 # StratLab's own list
    assert breadth.members("midcap150", None) == []
    us = breadth.members("us_large")
    assert len(us) == len(set(us)) > 100 and "AAPL" in us


def test_last_complete_day():
    assert breadth.last_complete("IN", IST_OPEN) == LAST
    assert breadth.last_complete("IN", datetime(2026, 10, 1, 11, 0, tzinfo=timezone.utc)) == "2026-10-01"    # 16:30 IST
    assert breadth.last_complete("US", datetime(2026, 10, 1, 19, 0, tzinfo=timezone.utc)) == LAST           # 15:00 New York


# ---------- the daily job ----------
def test_job_fills_an_empty_market_then_runs_once_a_day_after_the_close(mem):
    calls = []
    job = breadth.Job(runner(calls=calls), ready=lambda r: r == "IN")
    morning = datetime(2026, 9, 30, 5, 0, tzinfo=timezone.utc)                         # Wednesday, 10:30 IST
    assert job.tick(morning) == 1 and len(calls) == 3                                  # nothing stored: filled at once
    assert job.tick(morning) == 0 and len(calls) == 3                                  # ...once
    assert mem.get("newsjob:breadth-IN") is None                                       # not the day's run
    evening = datetime(2026, 9, 30, 13, 30, tzinfo=timezone.utc)                       # 19:00 IST
    assert job.tick(evening) == 1 and len(calls) == 6
    assert mem["newsjob:breadth-IN"] == "2026-09-30"
    assert job.tick(evening + timedelta(minutes=5)) == 0 and len(calls) == 6
    restarted = breadth.Job(runner(calls=calls), ready=lambda r: r == "IN")           # a restart the same evening
    assert restarted.tick(evening + timedelta(minutes=10)) == 0 and len(calls) == 6


def test_job_skips_holidays_and_waits_for_the_data_login(mem):
    calls = []
    runner().run("IN", IST_OPEN)
    job = breadth.Job(runner(calls=calls), ready=lambda r: False)
    assert job.tick(datetime(2026, 9, 30, 13, 30, tzinfo=timezone.utc)) == 0 and not calls      # not logged in
    job = breadth.Job(runner(calls=calls), ready=lambda r: r == "IN")
    assert job.tick(datetime(2026, 10, 3, 13, 30, tzinfo=timezone.utc)) == 0 and not calls      # Saturday


def test_job_failure_is_retried_later_not_marked(mem, monkeypatch):
    job = breadth.Job(runner(fail={"UP", "DOWN", "FLAT"}), ready=lambda r: r == "IN")
    evening = datetime(2026, 9, 30, 13, 30, tzinfo=timezone.utc)
    assert job.tick(evening) == 0
    assert mem.get("newsjob:breadth-IN") is None and "IN" in job.status["last_error"]
    assert breadth.status()["IN"]["last_error"]
    calls = []
    job.runner = runner(calls=calls)
    assert job.tick(evening) == 0 and not calls                 # waits half an hour
    t = __import__("time").time()
    monkeypatch.setattr(breadth.time, "time", lambda: t + 1801)
    assert job.tick(evening) == 1 and len(calls) == 3
    assert mem["newsjob:breadth-IN"] == "2026-09-30"


# ---------- wording ----------
def test_help_is_plain_facts():
    text = " ".join(breadth.HELP.values()) + " ".join(g["name"] + g["index_name"] for g in breadth.GROUPS.values())
    assert not PROVIDERS.search(text)
    assert not ADVICE.search(text)


# ---------- the page ----------
@pytest.fixture
def w(monkeypatch):
    world = W.build(monkeypatch)
    yield world
    world["close"]()


def paid(monkeypatch):
    monkeypatch.setattr(settings, "RAZORPAY_KEY_ID", "rzp_live_x")
    monkeypatch.setattr(settings, "RAZORPAY_KEY_SECRET", "secret")
    monkeypatch.setattr(settings, "RAZORPAY_PLAN_BASIC", "plan_b")
    monkeypatch.setattr(settings, "RAZORPAY_PLAN_PRO", "plan_p")


def stored(group="nifty500"):
    breadth.save_hist(group, rows_from([(3, 1), (1, 3), (2, 2)], idx=[100.0, 101.0, 99.0]))
    db.set_setting(breadth.SECTOR_KEY + group, json.dumps({"days": ["2026-01-03"], "sectors": {"Tech": {"a": [3], "n": [6]}}}))


def test_page_today_for_everyone_history_on_basic(w, monkeypatch):
    paid(monkeypatch)
    stored()
    c = w["client"]
    free = c.get("/invest/breadth?group=nifty500&range=all", headers=headers("free-token")).json()
    assert free["locked"] is True and free["history"] is None and free["sectors"] is None
    assert free["today"]["adv"]["value"] == 2 and free["as_of"] == "2026-01-03" and free["plan_needed"] == "Basic"
    basic = c.get("/invest/breadth?group=nifty500&range=all", headers=headers("basic-token")).json()
    assert basic["locked"] is False and basic["history"]["ad_line"] == [2, 0, 0] and basic["history"]["index"] == [100.0, 101.0, 99.0]
    assert basic["sectors"]["rows"][0] == {"sector": "Tech", "stocks": 6, "values": [50.0]}
    short = c.get("/invest/breadth?group=nifty500&range=3m", headers=headers("pro-token")).json()
    assert len(short["history"]["days"]) == 3
    brief = c.get("/invest/breadth?group=nifty500&brief=true", headers=headers("pro-token")).json()
    assert brief["history"] is None and brief["today"]["day"] == "2026-01-03"
    assert {g["id"] for g in basic["groups"]} == set(breadth.GROUPS)
    assert not PROVIDERS.search(json.dumps(basic))


def test_page_before_the_first_run_and_bad_input(w):
    c, h = w["client"], headers("pro-token")
    empty = c.get("/invest/breadth?group=us_large", headers=h).json()
    assert empty["today"] is None and empty["history"] is None and empty["as_of"] is None
    assert c.get("/invest/breadth?group=nope", headers=h).status_code == 404
    assert c.get("/invest/breadth?range=10y", headers=h).status_code == 400
    assert c.get("/invest/breadth").status_code == 401


def test_admin_run_and_status(w, monkeypatch):
    started = []
    monkeypatch.setattr(W.main.breadth_runner, "run", lambda region, full=None: started.append((region, full)))
    c = w["client"]
    assert c.post("/admin/breadth/run?region=IN", headers=headers("free-token")).status_code == 403
    r = c.post("/admin/breadth/run?region=IN&full=true", headers=headers("admin-token"))
    assert r.status_code == 200 and r.json()["started"]
    assert c.post("/admin/breadth/run?region=XX", headers=headers("admin-token")).status_code == 400
    assert c.get("/admin/breadth", headers=headers("admin-token")).status_code == 200
    import time
    for _ in range(50):
        if started:
            break
        time.sleep(0.02)
    assert started == [("IN", True)]


def test_the_apps_own_loaders_on_the_fake_market(w, monkeypatch):
    """The run as the server wires it: the stock lists, candles and index from the (fake) sources, end to end."""
    m = W.main
    assert len(m.breadth_load("IN", "RELIANCE", 400)) > 200
    assert len(m.breadth_index("IN", "NIFTY 500", 400)) > 200
    assert len(m.breadth_load("US", "AAPL", 400)) > 200
    with pytest.raises(LookupError):
        m.breadth_load("IN", "NOSUCHCO", 400)
    monkeypatch.setattr(m.breadth_runner, "gap", 0)
    from app.intel.net import RateLimit
    monkeypatch.setattr(m.markets.provider("US").yahoo, "limit", RateLimit(10**7, 10**6))   # the source's pacing, off for the test
    out =m.breadth_runner.run("US", datetime(2026, 10, 1, 22, 0, tzinfo=timezone.utc))
    assert out["ok"] and out["loaded"] > 100
    v = w["client"].get("/invest/breadth?group=us_large&range=1y", headers=headers("pro-token")).json()
    assert v["today"]["stocks"]["value"] > 100 and v["history"]["index"][-1]
    assert v["sectors"]["rows"]


# ---------- alerts on the share above the 50-day average ----------
def share_day(group, day, a50, n50=10):
    rows = breadth.load_hist(group)
    r = dict.fromkeys(breadth.COLS, 0)
    r.update(has=n50, adv=1, dec=1, a50=a50, n50=n50, idx=None)
    rows[day] = [r[c] for c in breadth.COLS]
    breadth.save_hist(group, rows)


def test_alert_fires_once_on_a_cross_and_keeps_watching(mem, monkeypatch):
    from app import stock_alerts
    monkeypatch.setattr(db, "all_settings_with_prefix", lambda p: [(k, v) for k, v in mem.items() if k.startswith(p)])
    share_day("nifty500", "2026-09-29", 5)                      # 50% now
    a = breadth.add_alert("u1", "nifty500", 60)
    assert a["side"] == "below"
    sent = []
    send = lambda profile, subject, text: sent.append((subject, text)) or ["phone"]     # noqa: E731
    now = datetime(2026, 9, 30, 13, 30, tzinfo=timezone.utc)
    prof = lambda uid: {"id": uid}                              # noqa: E731
    assert breadth.check_alerts(["nifty500"], now, prof, lambda p: True, send) == 0     # still below: nothing
    share_day("nifty500", "2026-09-30", 7)                      # 70%: crossed above 60
    assert breadth.check_alerts(["nifty500"], now, prof, lambda p: True, send) == 1
    assert sent[0][0] == "StratLab alert: NIFTY 500: 70.0% of stocks closed above their 50-day average on 30 Sep, crossing above 60%"
    assert not ADVICE.search(sent[0][1]) and not PROVIDERS.search(sent[0][1])
    assert breadth.check_alerts(["nifty500"], now, prof, lambda p: True, send) == 0     # once per cross
    assert breadth.alerts_of("u1")[0]["side"] == "above" and breadth.alerts_of("u1")[0]["fired_at"]
    assert len(stock_alerts._read("u1")["sent"]) == 1           # counted against the user's alert message limits
    share_day("nifty500", "2026-10-01", 4)                      # back below, but the plan no longer has it: quiet...
    assert breadth.check_alerts(["nifty500"], now, prof, lambda p: False, send) == 0
    assert breadth.alerts_of("u1")[0]["side"] == "below"        # ...and it follows the share, so it can't fire late
    assert len(sent) == 1


def test_alert_rules(mem):
    with pytest.raises(breadth.AlertError):
        breadth.add_alert("u1", "nope", 50)
    for bad in (0, 100, float("nan"), True, "50"):
        with pytest.raises(breadth.AlertError):
            breadth.add_alert("u1", "nifty500", bad)
    a = breadth.add_alert("u1", "nifty500", 50)
    assert a["side"] is None                                    # no counts yet: the first stored day sets it, quietly
    with pytest.raises(breadth.AlertError, match="already"):
        breadth.add_alert("u1", "nifty500", 50)
    for lv in (10, 20, 30, 40):
        breadth.add_alert("u1", "nifty50", lv)
    with pytest.raises(breadth.AlertError, match="up to 5"):
        breadth.add_alert("u1", "nifty50", 60)
    assert breadth.delete_alert("u1", a["id"]) and not breadth.delete_alert("u1", a["id"])


def test_alert_endpoints(w, monkeypatch):
    c, h = w["client"], headers("pro-token")
    r = c.post("/invest/breadth/alerts", headers=h, json={"group": "nifty500", "level": 60})
    assert r.status_code == 200 and r.json()["items"][0]["level"] == 60
    assert c.post("/invest/breadth/alerts", headers=h, json={"group": "nope", "level": 60}).status_code == 400
    assert c.post("/invest/breadth/alerts", headers=h, json={"group": "nifty500", "level": 120}).status_code == 422
    aid = c.get("/invest/breadth/alerts", headers=h).json()["items"][0]["id"]
    assert c.delete(f"/invest/breadth/alerts/{aid}", headers=h).json()["items"] == []
    assert c.delete(f"/invest/breadth/alerts/{aid}", headers=h).status_code == 404
    paid(monkeypatch)
    r = c.post("/invest/breadth/alerts", headers=headers("free-token"), json={"group": "nifty500", "level": 60})
    assert r.status_code == 402 and "Basic" in r.text
