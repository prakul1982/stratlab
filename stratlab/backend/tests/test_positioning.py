"""Derivatives positioning: reading the exchange's participant-wise files and FII/DII numbers (and surviving a file
that isn't out yet, a bot guard or an outage), the maths (PCR, max pain, implied volatility, its percentile and rank),
the evening job and its archive walk, the API and its plan gate, and no advice or provider names anywhere."""
import json
import math
import re
from datetime import date, datetime, timedelta, timezone

import httpx
import pytest

from app import db, main, positioning as P
from app.config import settings
from app.intel.filings import NSEFilings
from app.intel.net import SourceError
from tests import fake_positioning as FP
from tests import world as W
from tests.fake_db import headers

PROVIDERS = re.compile(r"kite|zerodha|yahoo|screener|finnhub|nseindia|nsearchives", re.I)
ADVICE = re.compile(r"\b(buy now|sell now|bullish|bearish|support|resistance|should|accumulate|avoid|target)\b", re.I)
FIX = FP.FIXTURES
IST = P.IST


@pytest.fixture
def w(monkeypatch):
    world = W.build(monkeypatch)
    yield world
    world["close"]()
    P.clear_cache()


@pytest.fixture
def paid(monkeypatch):
    monkeypatch.setattr(settings, "RAZORPAY_KEY_ID", "rzp_live_x")
    monkeypatch.setattr(settings, "RAZORPAY_KEY_SECRET", "secret")
    monkeypatch.setattr(settings, "RAZORPAY_PLAN_BASIC", "plan_b")
    monkeypatch.setattr(settings, "RAZORPAY_PLAN_PRO", "plan_p")


# ---------- the exchange's files ----------
def test_reads_the_participant_oi_file_as_published():
    got = P.participant_rows((FIX / "fao_participant_oi_03102026.csv").read_text())
    assert got["as_of"] == "2026-10-03"
    fii = got["rows"]["fii"]
    assert (fii["fut_idx_long"], fii["fut_idx_short"]) == (41052, 147218)
    assert (fii["opt_idx_call_long"], fii["opt_idx_put_long"], fii["opt_idx_call_short"], fii["opt_idx_put_short"]) == (322174, 264985, 193624, 165720)
    assert fii["fut_stk_short"] == 1010327 and fii["total_short"] == 1827304      # headers with stray tabs still match
    assert set(got["rows"]) == {"client", "dii", "fii", "pro", "total"} and got["rows"]["dii"]["opt_stk_call_short"] == 24


def test_reads_the_volume_file_and_the_generated_files():
    got = P.participant_rows((FIX / "fao_participant_vol_03102026.csv").read_text())
    assert got["as_of"] == "2026-10-03" and got["rows"]["pro"]["opt_idx_call_long"] == 30123456
    d = date(2026, 9, 29)
    for kind in ("oi", "vol"):
        g = P.participant_rows(FP.participant_csv(d, kind))
        assert g["as_of"] == d.isoformat() and g["rows"]["total"]["fut_idx_long"] == sum(g["rows"][p]["fut_idx_long"] for p in ("client", "dii", "fii", "pro"))


@pytest.mark.parametrize("text", ["", "<html><body>Access denied</body></html>", "Client Type,Future Index Long\nClient,5\n",
                                  "just,some\ncsv,text\n"])
def test_a_page_or_a_broken_file_is_not_a_participant_file(text):
    with pytest.raises(ValueError):
        P.participant_rows(text)


def test_reads_the_cash_numbers():
    got = P.cash_rows([{"category": "DII **", "date": "03-Oct-2026", "buyValue": "12,345.60", "sellValue": "10000.10", "netValue": "2345.50"},
                       {"category": "FII/FPI *", "date": "03-Oct-2026", "buyValue": "9000", "sellValue": "11000.25"}])
    assert got == {"as_of": "2026-10-03", "dii": {"buy": 12345.6, "sell": 10000.1, "net": 2345.5},
                   "fii": {"buy": 9000.0, "sell": 11000.25, "net": -2000.25}}          # net worked out when missing
    for bad in ({}, [], [{"category": "DII", "date": "x"}], "text"):
        with pytest.raises(ValueError):
            P.cash_rows(bad)


# ---------- the maths ----------
ROWS = [  # strike, ce bid, ask, ltp, oi, pe bid, ask, ltp, oi, ce vol, pe vol
    [100, 0, 0, 0, 10, 0, 0, 0, 50, 5, 20],
    [110, 0, 0, 0, 30, 0, 0, 0, 40, 10, 10],
    [120, 0, 0, 0, 60, 0, 0, 0, 10, 30, 0],
]


def test_pcr_by_open_interest_and_volume():
    p = P.pcr(ROWS)
    assert p["oi"] == round(100 / 100, 3) and p["vol"] == round(30 / 45, 3)
    assert (p["call_oi"], p["put_oi"], p["call_vol"], p["put_vol"]) == (100, 100, 45, 30)
    old = [r[:9] for r in ROWS]                         # recordings from before volumes were kept
    assert P.pcr(old)["vol"] is None and P.pcr(old)["oi"] == 1.0
    assert P.pcr([[100, 0, 0, 0, 0, 0, 0, 0, 5]])["oi"] is None     # no call open interest: no ratio


def test_max_pain_by_hand():
    # payout at 100: calls 0; puts 40*10 + 10*20 = 600 · at 110: calls 10*10 = 100; puts 10*10 = 100 -> 200
    # at 120: calls 10*20 + 30*10 = 500; puts 0 -> 500. The least is at 110.
    assert P.max_pain(ROWS) == 110
    assert P.max_pain([[100, 0, 0, 0, 0, 0, 0, 0, 0]]) is None
    assert P.max_pain([[100, 0, 0, 0, 5, 0, 0, 0, 5], [110, 0, 0, 0, 5, 0, 0, 0, 5]]) == 100      # a tie: the lower strike


def test_top_strikes_and_the_window():
    assert P.top_strikes(ROWS) == {"call": {"strike": 120, "oi": 60}, "put": {"strike": 100, "oi": 50}}
    rows = [[k, 0, 0, 0, 1, 0, 0, 0, 1] for k in range(0, 1000, 10)]
    win = P.near(rows, 503, 3)
    assert [r[0] for r in win] == [470, 480, 490, 500, 510, 520, 530]
    assert P.near(rows, None, 3) == rows


def test_implied_volatility_round_trip():
    for kind in ("CE", "PE"):
        for sigma in (0.08, 0.15, 0.4):
            price = P.black76(25000, 25100, 7 / 365, sigma, kind)
            assert P.implied_vol(price, 25000, 25100, 7 / 365, kind) == pytest.approx(sigma, abs=1e-6)
    assert P.implied_vol(0.0, 25000, 25000, 0.02, "CE") is None
    assert P.implied_vol(30000, 25000, 25000, 0.02, "CE") is None         # above the forward: no volatility gives it
    assert P.implied_vol(float("nan"), 25000, 25000, 0.02, "CE") is None


def test_atm_iv_from_the_chain():
    at = datetime(2026, 10, 1, 15, 25, tzinfo=IST)
    rows = FP.chain(25000, 0.13, "2026-10-06", at)
    got = P.atm_iv(rows, 25000, "2026-10-06", at)
    assert got["strike"] == 25000 and got["iv"] == pytest.approx(13.0, abs=0.4) and got["days"] == pytest.approx(5.0, abs=0.01)
    assert P.atm_iv(rows, 25000, "2026-10-01", datetime(2026, 10, 1, 16, 0, tzinfo=IST)) is None    # expired
    assert P.atm_iv([], 25000, "2026-10-06", at) is None and P.atm_iv(rows, None, "2026-10-06", at) is None


def test_iv_percentile_and_rank():
    past = [10.0 + i for i in range(20)]               # 10 … 29
    s = P.iv_stats(15.0, past)
    assert s["percentile"] == 25.0 and s["rank"] == pytest.approx(100 * 5 / 19, abs=0.1) and (s["low"], s["high"]) == (10.0, 29.0)
    assert P.iv_stats(40.0, past)["rank"] == 100.0 and P.iv_stats(5.0, past)["percentile"] == 0.0
    few = P.iv_stats(15.0, past[:5])
    assert few["percentile"] is None and few["days"] == 5 and few["need"] == P.IV_MIN_DAYS
    assert P.iv_stats(15.0, [12.0] * 25)["rank"] is None            # no range to place it in


def test_front_expiry_skips_the_expiry_day():
    assert P.front(["2026-10-06", "2026-10-13"], date(2026, 10, 6)) == "2026-10-13"
    assert P.front(["2026-10-06", "2026-10-13"], date(2026, 10, 5)) == "2026-10-06"
    assert P.front([], date(2026, 10, 5)) is None


# ---------- the feed ----------
class Counter:
    def __init__(self, answers):
        self.answers, self.seen = answers, []

    def __call__(self, r: httpx.Request):
        self.seen.append(str(r.url))
        if r.url.path == "/":
            return httpx.Response(200, text="<html></html>", headers={"set-cookie": "nsit=abc; Path=/"})
        for pat, resp in self.answers:
            if re.search(pat, str(r.url)):
                return resp(r) if callable(resp) else resp
        return httpx.Response(404, text="Not Found")


def feed(answers, sleeps=None):
    c = Counter(answers)
    nse = NSEFilings(transport=httpx.MockTransport(c), sleep=lambda s: None)
    return P.Feed(nse, sleep=(sleeps.append if sleeps is not None else (lambda s: None))), c


def test_feed_reads_a_day_and_says_when_it_isnt_published():
    d = date(2026, 10, 1)
    f, c = feed([(r"fao_participant_oi_01102026", httpx.Response(200, text=FP.participant_csv(d, "oi")))])
    assert f.participants("oi", d)["rows"]["fii"]["fut_idx_long"] > 0
    assert any("nsearchives" in u for u in c.seen)
    assert f.participants("vol", d) is None                # 404 at both addresses: not published (not an outage)
    assert sum("fao_participant_vol" in u for u in c.seen) == len(P.FILE_URLS)


def test_feed_falls_back_to_the_older_host_and_skips_another_days_file():
    d = date(2026, 10, 1)
    f, _ = feed([(r"nsearchives.*oi_01102026", httpx.Response(200, text=FP.participant_csv(d - timedelta(days=1)))),
                 (r"archives\.nseindia.*oi_01102026", httpx.Response(200, text=FP.participant_csv(d)))])
    assert f.participants("oi", d)["as_of"] == "2026-10-01"
    f, _ = feed([(r"oi_01102026", httpx.Response(200, text="<html>please wait</html>"))])
    assert f.participants("oi", d) is None                # a page instead of the file reads as not there


def test_feed_retries_a_bot_guard_with_fresh_cookies_then_gives_up():
    d = date(2026, 10, 1)
    tries = []

    def guard(r):
        tries.append(1)
        return httpx.Response(403) if len(tries) == 1 else httpx.Response(200, text=FP.participant_csv(d))
    sleeps = []
    f, c = feed([(r"oi_01102026", guard)], sleeps)
    assert f.participants("oi", d) is not None and sleeps == [2.0]
    assert sum(u.endswith("nseindia.com/") for u in c.seen) >= 2        # the website visited again for cookies
    f, _ = feed([(r"oi_01102026", httpx.Response(403))])
    with pytest.raises(SourceError) as e:
        f.participants("oi", d)
    assert e.value.busy


def test_feed_breaker_rests_after_three_outages():
    f, c = feed([(r"fao_participant", httpx.Response(503))])
    for _ in range(3):
        with pytest.raises(SourceError):
            f.participants("oi", date(2026, 10, 1))
    n = len(c.seen)
    with pytest.raises(SourceError) as e:
        f.participants("oi", date(2026, 10, 1))
    assert e.value.busy and len(c.seen) == n               # resting: nothing sent


def test_feed_reads_the_cash_numbers_with_a_fallback():
    d = date(2026, 10, 1)
    f, c = feed([(r"fiidiiTradeReact", httpx.Response(200, json={"weird": 1})),
                 (r"fiidiiTradeNse", httpx.Response(200, json=FP.cash_answer(d)))])
    got = f.cash()
    assert got["as_of"] == "2026-10-01" and got["fii"]["net"] == pytest.approx(got["fii"]["buy"] - got["fii"]["sell"], abs=0.01)
    assert any("fiidiiTradeNse" in u for u in c.seen)


# ---------- the run, the archive walk and the job ----------
def test_run_day_stores_both_files_and_the_cash(w):
    day = P.expected_day(datetime(2026, 10, 1, 19, 0, tzinfo=IST))
    assert day == date(2026, 10, 1)
    res = main.positioning_runner.run_day(day)
    assert res["participants"] == "ok"
    stored = P.latest("part")
    assert stored[0] == "2026-10-01" and set(stored[1]) == {"oi", "vol"}
    assert json.loads(db.get_setting("pos:part:2026"))["2026-10-01"]["oi"]["fii"]["fut_idx_long"] > 0
    assert P.latest("cash")[1]["fii"]["net"] is not None


def test_a_missing_file_is_not_published_yet(w, monkeypatch):
    monkeypatch.setattr(FP, "published", lambda d, today: d < date(2026, 10, 1))
    main.positioning_runner.run_day(date(2026, 9, 30))
    res = main.positioning_runner.run_day(date(2026, 10, 1))
    assert res["participants"] == "missing"
    st = P.state()["parts"]["participants"]
    assert st["missing"] == "2026-10-01" and st["error"] is None
    view = P.participants_today(datetime(2026, 10, 1, 19, 30, tzinfo=IST))
    assert view["status"] == "pending" and view["as_of"] == "2026-09-30" and view["expected"] == "2026-10-01"
    assert view["today"] == "pending"
    assert P.participants_today(datetime(2026, 10, 1, 12, 0, tzinfo=IST))["status"] == "ok"    # before 18:30 the 30th is the newest


def test_changes_are_against_the_day_before(w):
    for d in (date(2026, 9, 30), date(2026, 10, 1)):
        main.positioning_runner.run_day(d)
    view = P.participants_today(datetime(2026, 10, 1, 20, 0, tzinfo=IST))
    a = P.participant_rows(FP.participant_csv(date(2026, 10, 1)))["rows"]["fii"]
    b = P.participant_rows(FP.participant_csv(date(2026, 9, 30)))["rows"]["fii"]
    fii = next(r for r in view["oi"] if r["id"] == "fii")
    assert view["prev"] == "2026-09-30"
    assert fii["fut_idx_long_chg"] == a["fut_idx_long"] - b["fut_idx_long"]
    assert fii["fut_idx_net"] == a["fut_idx_long"] - a["fut_idx_short"]
    assert fii["fut_idx_net_chg"] == (a["fut_idx_long"] - a["fut_idx_short"]) - (b["fut_idx_long"] - b["fut_idx_short"])
    assert fii["fut_idx_long_pct"] == round(100 * a["fut_idx_long"] / (a["fut_idx_long"] + a["fut_idx_short"]), 1)
    assert [r["id"] for r in view["oi"]] == ["client", "dii", "fii", "pro", "total"] and view["vol"]


def test_backfill_walks_back_politely_and_finishes(w, monkeypatch):
    sleeps = []
    r = P.Runner(lambda: main.filings_feed, sleep=sleeps.append, pace=P.PACE)
    today = date(2026, 10, 5)
    bf = r.backfill(today, step=5, days=30)
    assert bf["read"] == 5 and not bf.get("done") and sleeps and set(sleeps) == {P.PACE}
    assert len(sleeps) == 10                                   # one pause after each of the two files a day
    stored = [d for d, _ in P.history("part")]
    assert len(stored) == 5 and max(stored) < today.isoformat()
    for _ in range(10):
        bf = r.backfill(today, step=5, days=30)
    assert bf["done"] and bf["next"] < (today - timedelta(days=30)).isoformat()
    from app.data.calendar import is_trading_day
    want = [d for d in (today - timedelta(days=n) for n in range(1, 31)) if is_trading_day("IN", d)]
    assert len(P.history("part")) == len(want)
    assert r.backfill(today)["done"]                           # finished for good: nothing more is read


def test_backfill_stops_on_an_outage_and_resumes(w, monkeypatch):
    w["faults"]["exchange"].mode = "500"
    r = P.Runner(lambda: main.filings_feed, sleep=lambda s: None, pace=0)
    bf = r.backfill(date(2026, 10, 5), step=5, days=30)
    assert bf.get("error") and not bf.get("read") and bf["next"] == "2026-10-01"     # the weekend and a holiday skipped; the 1st is retried
    w["faults"]["exchange"].mode = None
    r2 = P.Runner(lambda: main.filings_feed, sleep=lambda s: None, pace=0)
    bf = r2.backfill(date(2026, 10, 5), step=5, days=30)
    assert bf["read"] == 5 and "error" not in bf


def test_job_runs_after_publication_retries_and_keeps_its_marker(w, monkeypatch):
    runs = []

    class R:
        running = False

        def run_day(self, day, now=None):
            runs.append(day)
            return {"participants": "missing" if len(runs) == 1 else "ok", "cash": "ok", "chains": 0}

        def catch_up(self, now=None):
            return {}

        def backfill(self, today):
            return {"done": True}
    job = P.Job(R())
    utc = lambda h, m: datetime(2026, 10, 1, h, m, tzinfo=IST).astimezone(timezone.utc)     # noqa: E731
    job.tick(utc(18, 0))
    assert runs == []                                     # before the files are out
    job.tick(utc(18, 45))
    assert runs == [date(2026, 10, 1)] and db.get_setting("newsjob:positioning") is None     # missing: not done yet
    job.tick(utc(18, 50))
    assert len(runs) == 1                                 # waits twenty minutes between tries
    job._tried -= P.RETRY_MINUTES * 60
    job.tick(utc(19, 10))
    assert len(runs) == 2 and db.get_setting("newsjob:positioning") == "2026-10-01"
    again = P.Job(R())                                    # a restart: the marker says it's done
    again.tick(utc(19, 30))
    assert len(runs) == 2


def test_job_waits_while_an_admin_run_is_going(w):
    class R:
        running = True

        def run_day(self, day, now=None):
            raise AssertionError("ran twice at once")

        def catch_up(self, now=None):
            return {}

        def backfill(self, today):
            raise AssertionError("ran twice at once")
    P.Job(R()).tick(datetime(2026, 10, 1, 19, 0, tzinfo=IST).astimezone(timezone.utc))
    assert db.get_setting("newsjob:positioning") is None


def test_every_index_chain_is_read_in_a_few_requests_and_kept_a_minute(w):
    data = main.options_data
    before = data.quote_calls
    table = P.pcr_table(data)
    assert all(r["source"] == "live" for r in table)
    # one request for the five spots, then the contracts in batches of the feed's limit, never one index at a time
    assert data.quote_calls - before <= 3
    again = data.quote_calls
    P.pcr_table(data)
    P.chain_view(data, "SENSEX", "current")
    assert data.quote_calls == again                    # the same minute: from memory


def test_job_gives_up_for_the_day_at_the_end_of_the_window(w):
    class R:
        running = False

        def run_day(self, day, now=None):
            return {"participants": "missing", "cash": "missing", "chains": 0}

        def catch_up(self, now=None):
            return {}

        def backfill(self, today):
            return {"done": True}
    job = P.Job(R())
    job.tick(datetime(2026, 10, 1, 21, 35, tzinfo=IST).astimezone(timezone.utc))
    assert db.get_setting("newsjob:positioning") == "2026-10-01"


def test_job_skips_a_holiday(w):
    class R:
        running = False

        def run_day(self, day, now=None):
            raise AssertionError("ran on a holiday")

        def catch_up(self, now=None):
            return {}

        def backfill(self, today):
            return {"done": True}
    P.Job(R()).tick(datetime(2026, 10, 2, 19, 0, tzinfo=IST).astimezone(timezone.utc))    # Gandhi Jayanti


# ---------- the recorded chains ----------
def test_daily_summaries_from_recorded_chains(w):
    days = [date(2026, 9, 28), date(2026, 9, 29), date(2026, 9, 30)]
    FP.record_days(db.add_option_snapshot, "NIFTY", days, sigmas=[0.10, 0.12, 0.14])
    s = P.summarise_day("NIFTY", date(2026, 9, 29))
    assert s["front"] == "2026-10-06" and set(s["x"]) == {"2026-09-29", "2026-10-06"}     # the 29th is an expiry day: the next one is the front
    assert s["x"]["2026-10-06"]["atm_iv"] == pytest.approx(12.0, abs=0.5)
    assert P.summarise_day("NIFTY", date(2026, 9, 27)) is None
    r = P.Runner(lambda: main.filings_feed, pace=0)
    assert r.chains(date(2026, 9, 30)) == 1
    assert r.chain_backfill(date(2026, 10, 1), days=10) == 2
    series = P.chain_series("NIFTY")
    assert [p["day"] for p in series] == ["2026-09-28", "2026-09-29", "2026-09-30"]
    assert [round(p["atm_iv"]) for p in series] == [10, 12, 14] and all(p["pcr_oi"] and p["pcr_vol"] for p in series)


def test_chain_view_live_with_change_and_iv_stats(w):
    today = date.today()
    days = FP.weekdays_before(today, 25)
    FP.record_days(db.add_option_snapshot, "NIFTY", days)
    P.Runner(lambda: main.filings_feed, pace=0).chain_backfill(today, days=60)
    # one clock for both views (a live chain's IV moves with the time to expiry), set mid-session so that on an expiry
    # day the current series hasn't closed yet: after 15:30 there is no time left and no IV to work out
    now = P.ist_now().replace(hour=11, minute=0, second=0, microsecond=0)
    v = P.chain_view(main.options_data, "NIFTY", "current", full=True, now=now)
    assert v["source"] == "live" and v["spot"] and v["rows"] and v["max_pain"] and v["atm_iv"]
    assert v["top"]["call"]["strike"] > v["spot"] > v["top"]["put"]["strike"]
    assert v["iv"]["days"] >= P.IV_MIN_DAYS and v["iv"]["percentile"] is not None
    prev = P.recorded_before("NIFTY", v["expiry"], datetime.fromisoformat(v["as_of"]).date())
    if prev:                                         # the expiry was recorded the day before: change by strike
        row = next(r for r in v["rows"] if r["strike"] == v["atm"])
        was = next(r for r in prev["chain"] if r[0] == v["atm"])
        assert row["call_chg"] == row["call_oi"] - was[4]
    free = P.chain_view(main.options_data, "NIFTY", "current", full=False, now=now)
    assert free["iv"] is None and free["atm_iv"] == v["atm_iv"]


def test_chain_view_falls_back_to_the_newest_recording(w, monkeypatch):
    monkeypatch.setattr(main.options_data, "ready", lambda: False)
    today = date.today()
    FP.record_days(db.add_option_snapshot, "BANKNIFTY", FP.weekdays_before(today, 2), spot=55000.0, gap=100)
    v = P.chain_view(main.options_data, "BANKNIFTY", "next")
    assert v["source"] == "recorded" and v["expiry"] == v["expiries"][1] and v["rows"]
    assert P.chain_view(main.options_data, "FINNIFTY", "current")["source"] is None     # never recorded: nothing to show
    table = {r["name"]: r for r in P.pcr_table(main.options_data)}
    assert table["BANKNIFTY"]["source"] == "recorded" and table["SENSEX"]["source"] is None


# ---------- the API and the plan ----------
def test_api_today_is_for_everyone_history_is_basic(w, paid):
    c = w["client"]
    main.positioning_runner.run_day(P.expected_day(P.ist_now()) or date.today())
    for token in ("free-token", "basic-token"):
        s = c.get("/trade/positioning", headers=headers(token))
        assert s.status_code == 200
        d = s.json()
        assert d["participants"]["oi"] and d["cash"]["fii"] and [r["name"] for r in d["pcr"]] == list(P.NAMES)
        assert d["full"] == (token == "basic-token") and d["plan_needed"] == "Basic"
        ch = c.get("/trade/positioning/chain", params={"name": "NIFTY"}, headers=headers(token)).json()
        assert ch["rows"] and (ch["iv"] is None) == (token == "free-token")
    r = c.get("/trade/positioning/history", params={"kind": "participants"}, headers=headers("free-token"))
    assert r.status_code == 402 and "Basic" in r.json()["detail"]["message"]
    for kind in ("participants", "cash", "chain"):
        r = c.get("/trade/positioning/history", params={"kind": kind, "range": "1y"}, headers=headers("basic-token"))
        assert r.status_code == 200 and isinstance(r.json()["points"], list)
    brief = c.get("/trade/positioning", params={"brief": 1}, headers=headers("free-token")).json()
    assert [r["name"] for r in brief["pcr"]] == ["NIFTY"] and [r["id"] for r in brief["participants"]["oi"]] == ["fii"]


def test_api_rejects_bad_input(w):
    c, h = w["client"], headers("pro-token")
    assert c.get("/trade/positioning/chain", params={"name": "RELIANCE"}, headers=h).status_code == 400
    assert c.get("/trade/positioning/chain", params={"expiry": "soon"}, headers=h).status_code == 400
    assert c.get("/trade/positioning/history", params={"kind": "x"}, headers=h).status_code == 400
    assert c.get("/trade/positioning/history", params={"range": "9y"}, headers=h).status_code == 400
    assert c.get("/trade/positioning").status_code == 401
    assert c.post("/admin/positioning/run", headers=h).status_code == 403


def test_admin_run_and_status(w):
    c, h = w["client"], headers("admin-token")
    r = c.post("/admin/positioning/run", headers=h)
    assert r.status_code == 200 and r.json()["started"]
    import time
    for _ in range(50):
        if not main.positioning_runner.running and P.state().get("parts"):
            break
        time.sleep(0.1)
    st = c.get("/admin/positioning", headers=h).json()
    assert st["state"]["parts"]["participants"]["error"] is None


def test_nothing_names_a_provider_or_gives_advice(w):
    c, h = w["client"], headers("pro-token")
    main.positioning_runner.run_day(P.expected_day(P.ist_now()) or date.today())
    FP.record_days(db.add_option_snapshot, "NIFTY", FP.weekdays_before(date.today(), 3))
    texts = [c.get("/trade/positioning", headers=h).text, c.get("/trade/positioning/chain", headers=h).text]
    for t in texts:
        assert not PROVIDERS.search(t), PROVIDERS.search(t)
        assert not ADVICE.search(t), ADVICE.search(t)


def test_stored_numbers_are_finite_json(w):
    main.positioning_runner.run_day(P.expected_day(P.ist_now()) or date.today())
    for key in ("pos:part:", "pos:cash:"):
        for _, raw in db.all_settings_with_prefix(key):
            assert all(isinstance(v, (int, float, dict, type(None), str)) for v in json.loads(raw).values())
    assert math.isfinite(P.black76(100, 100, 0.1, 0.2, "CE"))


# ---------- both sides, the stock segments and how much is stored ----------
def test_long_and_short_shares_add_up_to_a_hundred():
    assert P.shares({"a": 8, "b": 92}, "a", "b") == (8.0, 92.0)
    assert P.shares({"a": 41052, "b": 147218}, "a", "b") == (21.8, 78.2)
    assert P.shares({"a": 1, "b": 2}, "a", "b") == (33.3, 66.7)
    for row in ({"a": 0, "b": 0}, {"a": None, "b": 5}, {"a": 5}, {"a": -1, "b": 3}):
        assert P.shares(row, "a", "b") == (None, None)


def test_the_view_has_both_sides_of_index_and_stock_futures_and_options(w):
    for d in (date(2026, 9, 30), date(2026, 10, 1)):
        main.positioning_runner.run_day(d)
    view = P.participants_today(datetime(2026, 10, 1, 20, 0, tzinfo=IST))
    fii = next(r for r in view["oi"] if r["id"] == "fii")
    a = P.participant_rows(FP.participant_csv(date(2026, 10, 1)))["rows"]["fii"]
    for seg, lo, sh in P.SEGMENTS:
        assert fii[seg + "_net"] == a[lo] - a[sh]
        assert fii[seg + "_long_pct"] + fii[seg + "_short_pct"] == pytest.approx(100)
        assert fii[seg + "_long_pct"] == round(100 * a[lo] / (a[lo] + a[sh]), 1)
        assert isinstance(fii[seg + "_long_pct_chg"], float)
    dii = next(r for r in view["oi"] if r["id"] == "dii")
    assert dii["opt_idx_call_long_pct"] is None                  # DIIs hold no index options in the file: no share, no 0/0
    assert next(r for r in view["vol"] if r["id"] == "fii")["fut_stk_short_pct"] is not None


def test_coverage_counts_the_stored_days_and_the_recorded_chains(w):
    r = P.Runner(lambda: main.filings_feed, sleep=lambda s: None, pace=0)
    r.backfill(date(2026, 10, 5), step=10, days=30)
    FP.record_days(db.add_option_snapshot, "NIFTY", [date(2026, 9, 29), date(2026, 9, 30)])
    r.chain_backfill(date(2026, 10, 1), days=5)
    cov = P.coverage()
    assert cov["participants"]["days"] == 10 and cov["participants"]["last"] == "2026-10-01"
    assert cov["participants"]["backfill_done"] is False and cov["participants"]["backfill_target"] == P.BACKFILL_DAYS
    assert cov["chains"]["NIFTY"] == {"days": 2, "first": "2026-09-29", "last": "2026-09-30"}
    assert cov["chains"]["FINNIFTY"] == {"days": 0, "first": None, "last": None}       # not recorded yet: said, not hidden
    assert P.chain_view(main.options_data, "FINNIFTY")["recorded"]["days"] == 0
    h = P.history_view("participants", None, "all", datetime(2026, 10, 5, 12, 0, tzinfo=IST))
    pt = h["points"][-1]["fii"]
    assert h["stored"]["days"] == 10 and 0 < pt["fut_idx_long_pct"] < 100 and pt["fut_stk_net"] is not None
    assert P.history_view("chain", "NIFTY", "all", datetime(2026, 10, 5, 12, 0, tzinfo=IST))["recorded"]["days"] == 2


def test_the_default_records_every_index_the_page_shows(monkeypatch):
    from app import config
    from app.options.recorder import parse_targets
    monkeypatch.delenv("OPTION_SNAPSHOTS", raising=False)
    assert set(parse_targets(config.Settings().OPTION_SNAPSHOTS)) == set(P.UNDERLYINGS)


# ---------- catching up: a server started on a Sunday, after a holiday ----------
SUNDAY = datetime(2026, 10, 4, 21, 4, tzinfo=IST)            # the owner's screenshot: the 2nd a holiday, the 3rd a Saturday


@pytest.fixture
def sunday(w, monkeypatch):
    real = FP.answer
    monkeypatch.setattr(FP, "answer", lambda path, today=None: real(path, date(2026, 10, 4)))
    return w


def test_cash_numbers_read_on_a_weekend_when_none_are_stored(sunday):
    r = P.Runner(lambda: main.filings_feed, sleep=lambda s: None, pace=0)
    r.backfill(date(2026, 10, 4), step=10, days=30)              # the archive walk reads the files, never the cash numbers
    before = P.cash_today(SUNDAY)
    assert before["status"] == "none" and "Not read yet" in before["reason"]
    assert P.participants_today(SUNDAY)["status"] == "ok" and P.participants_today(SUNDAY)["reason"] is None
    res = r.catch_up(SUNDAY)
    assert res == {"cash": "ok"}                                 # the files were there already: only the cash is read
    cash = P.cash_today(SUNDAY)
    assert cash["status"] == "ok" and cash["as_of"] == "2026-10-01" and cash["fii"]["net"] is not None and cash["reason"] is None
    assert r.catch_up(SUNDAY) == {}                              # nothing behind: nothing asked


def test_catch_up_reads_recent_files_the_evening_run_missed(sunday):
    r = P.Runner(lambda: main.filings_feed, sleep=lambda s: None, pace=0)
    res = r.catch_up(SUNDAY)
    assert res["participants"] == {"2026-10-01": "ok", "2026-09-30": "ok", "2026-09-29": "ok", "2026-09-28": "ok",
                                   "2026-09-25": "ok", "2026-09-24": "ok", "2026-09-23": "ok", "2026-09-22": "ok"}
    assert res["cash"] == "ok"
    assert P.participants_today(SUNDAY)["as_of"] == "2026-10-01"


def test_catch_up_gives_a_missing_recent_day_three_tries(sunday, monkeypatch):
    monkeypatch.setattr(FP, "published", lambda d, today: d != date(2026, 10, 1) and FP.trading(d))
    r = P.Runner(lambda: main.filings_feed, sleep=lambda s: None, pace=0)
    for _ in range(P.CATCH_UP_TRIES):
        assert r.catch_up(SUNDAY).get("participants", {}).get("2026-10-01") == "missing"
    assert "2026-10-01" not in r.catch_up(SUNDAY).get("participants", {})
    st = P.participants_today(SUNDAY)
    assert st["status"] == "pending" and st["reason"] == "The exchange hasn't published 1 Oct 2026's participant files yet."


def test_a_refused_cash_read_says_why(sunday, monkeypatch):
    def refuse(*a, **k):
        raise SourceError("the exchange", "The exchange feed refused the request (403). Try again later.", busy=True)
    monkeypatch.setattr(P.Feed, "cash", refuse)
    P.Runner(lambda: main.filings_feed, sleep=lambda s: None, pace=0).catch_up(SUNDAY)
    c = P.cash_today(SUNDAY)
    assert c["status"] == "none" and c["reason"].startswith("The last try (4 Oct 2026, 21:04 IST) didn't get them: ")
    assert "403" in c["reason"]


def test_the_job_catches_up_on_a_sunday_every_twenty_minutes(sunday):
    job = P.Job(P.Runner(lambda: main.filings_feed, sleep=lambda s: None, pace=0))
    utc = SUNDAY.astimezone(timezone.utc)
    job.tick(utc)
    assert job.status["catch_up"]["cash"] == "ok" and P.cash_today(SUNDAY)["as_of"] == "2026-10-01"
    calls = []
    job.runner.catch_up = lambda now=None: calls.append(now) or {}
    job.tick(utc + timedelta(minutes=5))
    assert calls == []                                           # caught up: the job walks the archive instead


def test_the_job_leaves_the_evening_window_to_the_evening_run(w):
    class R:
        running = False
        caught = 0

        def run_day(self, day, now=None):
            return {"participants": "missing", "cash": "missing", "chains": 0}

        def catch_up(self, now=None):
            R.caught += 1
            return {}

        def backfill(self, today):
            return {"done": True}
    job = P.Job(R())
    job.tick(datetime(2026, 10, 1, 19, 0, tzinfo=IST).astimezone(timezone.utc))
    job.tick(datetime(2026, 10, 1, 19, 5, tzinfo=IST).astimezone(timezone.utc))
    assert R.caught == 0


GAP = {date(2026, 9, d) for d in (14, 15, 16, 17, 18, 21, 22)}


def test_backfill_does_not_pass_by_days_the_archive_turned_away(w, monkeypatch):
    monkeypatch.setattr(FP, "published", lambda d, today: d not in GAP and FP.trading(d))
    r = P.Runner(lambda: main.filings_feed, sleep=lambda s: None, pace=0)
    bf = r.backfill(date(2026, 10, 5), step=40, days=40)
    assert bf["next"] == "2026-09-22" and "none of 5 trading days" in bf["error"] and not bf.get("done")
    monkeypatch.setattr(FP, "published", lambda d, today: FP.trading(d))     # the archive answers again
    bf = r.backfill(date(2026, 10, 5), step=40, days=40)
    assert bf["done"] and {d.isoformat() for d in GAP if FP.trading(d)} <= {d for d, _ in P.history("part")}


def test_backfill_takes_a_real_gap_after_three_tries(w, monkeypatch):
    monkeypatch.setattr(FP, "published", lambda d, today: d not in GAP and FP.trading(d))
    r = P.Runner(lambda: main.filings_feed, sleep=lambda s: None, pace=0)
    for _ in range(3):
        assert r.backfill(date(2026, 10, 5), step=40, days=40)["next"] == "2026-09-22"
    assert r.backfill(date(2026, 10, 5), step=40, days=40)["done"]


def test_api_says_how_much_is_stored_and_why_a_number_is_missing(sunday):
    c = sunday["client"]
    P.Runner(lambda: main.filings_feed, sleep=lambda s: None, pace=0).backfill(date(2026, 10, 4), step=3, days=30)
    d = c.get("/trade/positioning", params={"pcr": "false"}, headers=headers("pro-token")).json()
    assert d["coverage"]["participants"]["days"] == 3 and set(d["coverage"]["chains"]) == set(P.NAMES)
    assert d["cash"]["reason"] and "fii" not in d["cash"]
    brief = c.get("/trade/positioning", params={"brief": 1}, headers=headers("free-token")).json()
    assert brief["cash"]["reason"] and "coverage" not in brief
