"""The per-stock market desks: stock futures (OI buildup, rollover, basis, MWPL use), stock lending fees and
margin-funded positions. Reading the exchange's real files (trimmed samples in fixtures/stock_desks), the arithmetic,
the shared day store and runner (a file not published yet, an outage, the archive walk), the alerts, the routes and
their plan gates, and no advice or provider names anywhere."""
import io
import json
import re
import zipfile
from datetime import date, datetime

import httpx
import pandas as pd
import pytest

from app import db, main  # noqa: F401  (main first: it sets up the import order the desks rely on)
from app import exchange_days as X, mtf, slb, stock_alerts, stock_desks, stock_futures as F
from app.config import settings
from app.intel.filings import NSEFilings
from app.intel.net import SourceError
from app.positioning import Feed
from tests import fake_stock_desks as FS
from tests import world as W
from tests.fake_db import headers

FIX = FS.FIXTURES
PROVIDERS = re.compile(r"kite|zerodha|yahoo|screener|finnhub|nseindia|nsearchives", re.I)
ADVICE = re.compile(r"\b(buy now|sell now|bullish|bearish|should|accumulate|avoid|target|risky|overleveraged|good|bad)\b", re.I)
IST = X.IST


@pytest.fixture
def w(monkeypatch):
    world = W.build(monkeypatch)
    yield world
    world["close"]()
    X.clear_cache()


@pytest.fixture
def paid(monkeypatch):
    monkeypatch.setattr(settings, "RAZORPAY_KEY_ID", "rzp_live_x")
    monkeypatch.setattr(settings, "RAZORPAY_KEY_SECRET", "secret")
    monkeypatch.setattr(settings, "RAZORPAY_PLAN_BASIC", "plan_b")
    monkeypatch.setattr(settings, "RAZORPAY_PLAN_PRO", "plan_p")


def fill(today: date | None = None, step: int = 30):
    """Every desk's recent days, as the evening job and the archive walk would have stored them from the fake exchange."""
    for d in stock_desks.DESKS:
        stock_desks.runner.catch_up(d)
        stock_desks.runner.backfill(d, today or X.ist_now().date(), step=step)


# ---------- the exchange's files, as published ----------
def test_reads_the_real_fo_bhavcopy_and_mwpl_file():
    day, cs = F.contracts((FIX / "fo_bhav_01102026.csv").read_text())
    assert day == "2026-10-01" and set(cs) == {"360ONE", "AMBUJACEM", "BANDHANBNK", "HDFCBANK", "RELIANCE", "SAIL"}
    rel = cs["RELIANCE"]
    assert [c["expiry"] for c in rel] == ["2026-10-27", "2026-11-23", "2026-12-29"]          # nearest first
    assert rel[0] == {"expiry": "2026-10-27", "close": 1175.8, "prev": 1191.8, "under": 1167.21, "oi": 146855000,
                      "oi_chg": 1423000, "vol": 19717, "lot": 500}
    mday, mw = F.mwpl_rows((FIX / "combineoi_01102026.csv").read_text())
    assert mday == "2026-10-01"
    assert mw["AMBUJACEM"] == {"mwpl": 102300439, "oi": 116700000, "feq": 98975596, "pct": 96.75, "ban": True}
    assert mw["RELIANCE"]["pct"] == 25.51 and mw["RELIANCE"]["ban"] is False
    with pytest.raises(ValueError):
        F.contracts((FIX / "combineoi_01102026.csv").read_text())          # the wrong file
    with pytest.raises(ValueError):
        F.mwpl_rows((FIX / "cm_bhav_01102026.csv").read_text())


def test_a_stock_day_by_hand():
    day, cs = F.contracts((FIX / "fo_bhav_01102026.csv").read_text())
    _, mw = F.mwpl_rows((FIX / "combineoi_01102026.csv").read_text())
    r = F.stock_row(day, cs["RELIANCE"], mw["RELIANCE"], None)
    total = 146855000 + 16451500 + 390000
    assert r["oi"] == total and (r["n"], r["x"], r["f"]) == (146855000, 16451500, 390000)
    assert r["pc"] == round(100 * (1175.8 / 1191.8 - 1), 2) == -1.34
    assert r["oc"] == round(100 * (total / (total - (1423000 + 902000 + 259500)) - 1), 2)
    assert r["b"] == "SB"                                                   # price down, open interest up
    assert r["r"] == round(100 * (1 - 146855000 / total), 2)
    assert r["bp"] == round(100 * (1175.8 / 1167.21 - 1), 3)
    assert r["ba"] == round(100 * (1175.8 / 1167.21 - 1) * 365 / 26, 2)    # 26 calendar days to 27 Oct
    assert r["td"] == 16 and r["m"] == 25.51 and r["ban"] is False


def test_buildup_words_cover_the_four_cases_and_no_move():
    assert [F.buildup(p, o) for p, o in ((1, 1), (-1, 1), (1, -1), (-1, -1), (0, 2), (1, 0), (None, 1))] == \
        ["LB", "SB", "SC", "LU", None, None, None]
    assert set(F.BUILDUP) == {"LB", "SB", "SC", "LU"}
    for label, text in F.BUILDUP.values():
        assert not ADVICE.search(label + text)


def test_expiry_day_reads_the_basis_off_the_next_contract():
    cs = [{"expiry": "2026-10-27", "close": 100.0, "prev": 99.0, "under": 100.0, "oi": 10, "oi_chg": 0, "vol": 1, "lot": 1},
          {"expiry": "2026-11-24", "close": 101.0, "prev": 100.0, "under": 100.0, "oi": 90, "oi_chg": 5, "vol": 1, "lot": 1}]
    r = F.stock_row("2026-10-27", cs, None, None)
    assert r["be"] == "2026-11-24" and r["bp"] == 1.0 and r["ba"] == round(1.0 * 365 / 28, 2)
    assert r["td"] == 0 and r["r"] == 90.0 and r["m"] is None
    assert F.stock_row("2026-10-28", cs[:1], None, None) is None            # every contract expired


def test_reads_the_cash_bhavcopy_and_the_slb_bhavcopy():
    cash = X.cash_rows((FIX / "cm_bhav_01102026.csv").read_text())
    assert cash["RELIANCE"] == {"close": 1167.7, "prev": 1187.0, "series": "EQ"}
    assert "SGBJUN28" not in cash                                            # a gold bond, not a share
    day, lines = slb.bhav_rows((FIX / "SLBM_BC_01102026.DAT").read_text())
    assert day == "2026-10-01"
    assert lines["RELIANCE"][1] == ["XN", "2026-11-03", 0.49, 0.75, 0.49, 0.75, 80900, 60014.05, 9]
    fee = slb.avg_fee(lines["RELIANCE"][1])
    assert fee == round(60014.05 / 80900, 4)
    assert slb.annualised(fee, 1167.7, day, "2026-11-03") == round(100 * fee / 1167.7 * 365 / 33, 2)
    assert slb.annualised(fee, 1167.7, day, "2026-10-01") is None and slb.annualised(None, 1.0, day, "2026-11-03") is None
    assert slb.eligible_rows((FIX / "SLB_ELG_SEC_01102026.csv").read_text()) >= {"RELIANCE", "HDFCBANK", "ACC"}


def test_reads_the_margin_trading_disclosure_and_shares_issued():
    day, totals, rows = mtf.disclosure((FIX / "mrg_trading_30092026.csv").read_text())
    assert day == "2026-09-30"
    assert totals == {"start": 15083812.8, "fresh": 347239.5, "liquidated": 317653.87, "end": 15113398.43}
    assert rows["RELIANCE"] == [22099832, 288640.02] and rows["HDFCBANK"] == [42743410, 328238.15]
    sh = mtf.shares_rows((FIX / "NSE_CM_security_01102026.csv").read_text())
    assert sh["RELIANCE"] == 13532538722 and sh["HDFCBANK"] == 15416700168
    assert mtf.pct_shares(22099832, sh["RELIANCE"]) == round(100 * 22099832 / 13532538722, 3)
    assert mtf.pct_mcap(288640.02, sh["RELIANCE"], 1167.7) == round(100 * 288640.02e5 / (13532538722 * 1167.7), 3)
    with pytest.raises(ValueError):
        mtf.disclosure("<html>please wait</html>")


def test_unpacks_zip_gzip_and_plain():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("readme.txt", "no")
        z.writestr("a.csv", "x,y\n1,2\n")
    assert X.unpack(buf.getvalue()) == "x,y\n1,2\n"
    import gzip
    assert X.unpack(gzip.compress("ﬁle".encode())) == "ﬁle"
    assert X.unpack(b"\xef\xbb\xbfplain") == "plain" and X.unpack(None) is None and X.unpack(b"PKnot a zip") is None


# ---------- the rule values ----------
def test_rule_values_on_numbers_and_series():
    from app.engine.indicators import basis_pct, compute, oi_change_pct, rollover_pct
    from app.models import Ref
    assert oi_change_pct(110, 100) == pytest.approx(10) and oi_change_pct(1, 0) is None
    assert rollover_pct(25, 100) == pytest.approx(75) and rollover_pct(1, None) is None
    assert basis_pct(101, 100) == pytest.approx(1) and basis_pct(None, 100) is None
    df = pd.DataFrame({"c": [1.0, 1, 1], "fo_oi": [100.0, 110, None], "fo_near": [50.0, 55, None],
                       "fo_fut": [101.0, 102, None], "fo_spot": [100.0, 100, None]})
    oc = compute(Ref(t="oi_change_pct"), df, False)
    assert oc.isna()[0] and oc[1] == pytest.approx(10) and oc.isna()[2]
    assert list(compute(Ref(t="rollover_pct"), df, False)[:2]) == pytest.approx([50, 50])
    assert list(compute(Ref(t="basis_pct"), df, False)[:2]) == pytest.approx([1, 2])
    assert compute(Ref(t="basis_pct"), pd.DataFrame({"c": [1.0, 2.0]}), False).isna().all()   # not an F&O stock


def test_a_backtest_gets_the_stored_facts_by_day(w):
    fill()
    from app import research
    from app.models import Strategy
    ser = F.DESK.store.series("RELIANCE")
    bars = [{"t": f"{p[0]}T00:00:00+05:30", "o": 1, "h": 1, "l": 1, "c": 1, "v": 1} for p in ser] + [{"t": "2030-01-01", "c": 1}]
    s = Strategy.model_validate({"name": "x", "entry": [{"l": {"t": "oi_change_pct"}, "op": "gt", "r": {"t": "num", "v": 0}}],
                                 "exit": [], "risk": {}})
    got = research._with_fo(s, {"id": "IN:1", "symbol": "RELIANCE"}, bars)
    assert got[-2]["fo_oi"] == ser[-1][3] and got[-2]["fo_fut"] == ser[-1][1] and "fo_oi" not in got[-1]
    assert research._with_fo(s, {"id": "US:AAPL", "symbol": "AAPL"}, bars) is bars
    plain = Strategy.model_validate({"name": "x", "entry": [{"l": {"t": "price"}, "op": "gt", "r": {"t": "num", "v": 0}}],
                                     "exit": [], "risk": {}})
    assert research._with_fo(plain, {"id": "IN:1", "symbol": "RELIANCE"}, bars) is bars


# ---------- the day store, the feed and the runner ----------
def test_day_store_keeps_days_and_each_stocks_points(w):
    st = X.DayStore("tstore:", keep=3, shards=2)
    for i, d in enumerate(("2026-09-28", "2026-09-29", "2026-09-30")):
        st.put(d, {"AAA": [i, i * 2], "BBB": [i]})
    assert st.days() == ["2026-09-28", "2026-09-29", "2026-09-30"]
    assert st.series("AAA") == [["2026-09-28", 0, 0], ["2026-09-29", 1, 2], ["2026-09-30", 2, 4]]
    assert st.latest()[0] == "2026-09-30" and st.latest(before="2026-09-30")[0] == "2026-09-29"
    st.put_many([("2026-10-01", {"AAA": [9, 9]}, {}), ("2026-09-25", {"BBB": [7]}, {})])     # an older day comes in late
    assert st.days() == ["2026-09-29", "2026-09-30", "2026-10-01"]                         # the oldest drop off
    assert [p[0] for p in st.series("AAA")] == ["2026-09-29", "2026-09-30", "2026-10-01"]
    assert st.get("2026-09-28") is None and db.get_setting("tstore:d:2026-09-28") is None
    assert st.series("CCC") == [] and set(st.all_series()) == {"AAA", "BBB"}


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


def files(answers, sleeps=None):
    c = Counter(answers)
    nse = NSEFilings(transport=httpx.MockTransport(c), sleep=lambda s: None)
    sl = sleeps.append if sleeps is not None else (lambda s: None)
    return X.Files(Feed(nse, sleep=sl), sleep=sl, pace=1.5), c


def test_files_read_a_zip_say_when_it_isnt_published_and_pace_themselves():
    d = date(2026, 10, 1)
    sleeps = []
    f, c = files([(r"BhavCopy_NSE_FO", lambda r: httpx.Response(200, content=FS.answer(r.url.path, d)[1])),
                  (r"SLBM_BC", httpx.Response(200, text="<html>wait</html>"))], sleeps)
    assert F.contracts(f.text(F.FO_BHAV.format(ymd="20261001")))[0] == "2026-10-01"
    assert f.text(slb.SLB_BHAV.format(dmy="01102026")) is None              # a page instead of the file
    assert f.text(mtf.MTF_FILE.format(dmy="011026")) is None                # 404: not published
    assert sleeps == [1.5, 1.5] and any("nsearchives" in u for u in c.seen)
    f, _ = files([(r"BhavCopy", httpx.Response(503))])
    with pytest.raises(SourceError) as e:
        f.text(F.FO_BHAV.format(ymd="20261001"))
    assert e.value.busy


def test_catch_up_reads_recent_days_and_counts_a_day_not_published(w, monkeypatch):
    now = datetime(2026, 10, 1, 20, 0, tzinfo=IST)
    assert X.expected(now, "19:30") == date(2026, 10, 1) and X.expected(now, "19:30", lag=1) == date(2026, 9, 30)
    assert X.expected(datetime(2026, 10, 3, 9, 0, tzinfo=IST), "19:30") == date(2026, 10, 1)      # a Saturday
    monkeypatch.setattr(FS, "trading", lambda d: X.trading(d) and d != date(2026, 9, 29))        # that day's file is late
    res = stock_desks.runner.catch_up(F.DESK, now)
    assert res["2026-10-01"] == "ok" and res["2026-09-29"] == "missing"
    assert F.DESK.store.latest()[0] == "2026-10-01" and "2026-09-29" not in F.DESK.store.days()
    assert F.DESK.store.state()["tries"]["2026-09-29"] == 1
    st = X.status(F.DESK, now)
    assert st["status"] == "ok" and st["as_of"] == "2026-10-01" and st["reason"] is None


def test_an_outage_stops_the_run_and_says_why(w):
    w["faults"]["exchange"].mode = "500"
    now = datetime(2026, 10, 1, 20, 0, tzinfo=IST)
    res = stock_desks.runner.catch_up(slb.DESK, now)
    assert list(res.values()) and "refused" in list(res.values())[0]
    st = X.status(slb.DESK, now)
    assert st["status"] == "none" and "didn't get it" in st["reason"] and not PROVIDERS.search(st["reason"])
    w["faults"]["exchange"].mode = None


def test_backfill_walks_back_a_few_days_at_a_time_and_finishes(w):
    today = date(2026, 10, 1)
    bf = stock_desks.runner.backfill(slb.DESK, today, step=5, days=20)
    assert bf["read"] == 5 and not bf.get("done") and len(slb.DESK.store.days()) == 5
    for _ in range(10):
        bf = stock_desks.runner.backfill(slb.DESK, today, step=5, days=20)
    assert bf["done"] and len(slb.DESK.store.days()) >= 20
    assert stock_desks.runner.backfill(slb.DESK, today)["done"]            # finished: nothing more is read


def test_the_job_catches_up_then_walks_back_outside_market_hours(w, monkeypatch):
    job = X.Job(stock_desks.runner)
    calls = []
    monkeypatch.setattr(stock_desks.runner, "catch_up", lambda d, now=None: calls.append(("catch", d.name)) or {})
    monkeypatch.setattr(stock_desks.runner, "backfill", lambda d, today, **k: calls.append(("back", d.name)) or {})
    job.tick(datetime(2026, 10, 1, 20, 0, tzinfo=IST))
    assert [c for c in calls if c[0] == "catch"] == [("catch", "fno"), ("catch", "slb"), ("catch", "mtf")]
    calls.clear()
    job.tick(datetime(2026, 10, 1, 20, 5, tzinfo=IST))                   # tried a moment ago: the walk instead
    assert calls == [("back", "fno"), ("back", "slb"), ("back", "mtf")]
    calls.clear()
    job._tried = {k: 9e12 for k in ("fno", "slb", "mtf")}
    job.tick(datetime(2026, 10, 1, 11, 0, tzinfo=IST))                   # market hours: neither
    assert calls == []


# ---------- the views ----------
def test_the_stock_futures_table_and_one_stocks_history(w):
    fill()
    t = F.table()
    rows = {r["symbol"]: r for r in t["rows"]}
    assert [r["symbol"] for r in t["rows"]] == sorted(rows)                 # alphabetical: no ranking
    assert set(rows) == set(FS.STOCKS)
    rel = rows["RELIANCE"]
    assert rel["b"] == "LB" and rel["streak"] == len(F.DESK.store.days())   # rose with OI every stored day
    assert rows["AMBUJACEM"]["ban_next"] is True and rows["AMBUJACEM"]["m"] > 95
    assert t["status"]["status"] in ("ok", "pending") and t["labels"]["LB"] == "Long buildup"
    d = F.detail("RELIANCE", True, "1m")
    assert d["history"] and d["history"][-1]["day"] == t["as_of"] and d["history"][-1]["b"] == "LB"
    assert F.detail("RELIANCE", False)["history"] is None and F.detail("WIPRO", True) is None


def test_mwpl_crossing_80_either_way_makes_an_event():
    prev = {"A": {"m": 79.0}, "B": {"m": 85.0}, "C": {"m": 50.0}, "D": {"m": None}}
    rows = {"A": {"m": 81.2, "ban": False}, "B": {"m": 70.0}, "C": {"m": 60.0}, "D": {"m": 90.0}}
    ev = F.DESK.after("2026-10-01", rows, prev)
    assert [(e["symbol"], e["id"]) for e in ev] == [("A", "2026-10-01:A:mwpl:up"), ("B", "2026-10-01:B:mwpl:down")]
    assert ev[0]["text"] == "MWPL use rose to 81.2% on 1 Oct 2026 (from 79.0%)."
    assert F.DESK.after("2026-10-01", rows, None) == []


def test_lending_summaries_and_eligibility(w):
    fill()
    rel = slb.for_symbol("RELIANCE")
    s30, s90 = rel["summaries"]
    assert rel["eligible"] is True and s30["days"] == 30 and s30["traded_days"] >= 15
    assert s30["ann_low"] <= s30["ann_avg"] <= s30["ann_high"] and s30["last"]["day"] == rel["as_of"]
    assert rel["trades"][0]["day"] == rel["as_of"] and {t["series"] for t in rel["trades"]} == {"X1", "X2"}
    tcs = slb.for_symbol("TCS")
    assert tcs["eligible"] is True and tcs["summaries"][0]["traded_days"] == 0 and tcs["trades"] == []
    assert slb.for_symbol("ZZZZ")["eligible"] is False


def test_margin_funding_for_a_stock_and_the_market(w):
    fill()
    r = mtf.for_symbol("RELIANCE", full=True)
    assert r["funded"] and r["crore"] > 0 and r["issued"] == FS.STOCKS["RELIANCE"][3]
    assert r["pct_shares"] == mtf.pct_shares(r["shares"], r["issued"]) and r["day"]["shares"] > 0     # grows each day
    assert r["d30"]["from"] < r["as_of"] and r["history"][-1]["day"] == r["as_of"]
    assert mtf.for_symbol("NOSUCH")["funded"] is False
    m = mtf.market(full=True)
    assert m["end"] and m["history"][-1]["end"] == m["end"] and m["stocks"] == len(FS.STOCKS) + len(FS.CASH_ONLY)
    assert mtf.screen_values()["SBIN"] == pytest.approx(1.2, abs=0.01)


def test_the_cost_of_an_mtf_position_by_hand():
    r = mtf.cost(mtf.CostReq(buy=1000, qty=100, margin_pct=25, rate_pct=15, days=60, charges=50, price=1100, maint_pct=20))
    interest = 75000 * 0.15 * 60 / 365
    assert r["value"] == 100000 and r["funded"] == 75000 and r["own"] == 25000
    assert r["interest"] == round(interest, 2) and r["costs"] == round(interest + 50, 2)
    assert r["breakeven"] == round(1000 + (interest + 50) / 100, 2)
    assert r["breach_price"] == round((75000 + interest) / (100 * 0.8), 2)
    assert r["breach_fall_pct"] == round(100 * (1 - r["breach_price"] / 1100), 2)
    assert r["margin_now_pct"] == round(100 * (110000 - 75000 - interest) / 110000, 2)
    assert r["pnl"] == round(10000 - interest - 50, 2)
    plain = mtf.cost(mtf.CostReq(buy=10, qty=1, margin_pct=50, rate_pct=0, days=0))
    assert plain["interest"] == 0 and "breach_price" not in plain and "pnl" not in plain


# ---------- the alerts ----------
def test_alert_kinds_are_checked_and_described():
    a = stock_alerts.clean({"region": "IN", "symbol": "sail", "kind": "mwpl"})
    assert a["kind"] == "mwpl" and stock_alerts.describe(a) == "MWPL use crosses 80%, either way"
    m = stock_alerts.clean({"region": "IN", "symbol": "RELIANCE", "kind": "mtf", "op": "above", "value": 1.5})
    assert stock_alerts.describe(m) == "Margin-funded shares cross above 1.5% of shares issued"
    for bad in ({"kind": "mtf", "op": "either", "value": 1}, {"kind": "mtf", "op": "above", "value": 0}, {"kind": "mtf", "op": "above", "value": 80},
                {"kind": "mwpl", "region": "US"}):
        with pytest.raises(stock_alerts.AlertError):
            stock_alerts.clean({"region": "IN", "symbol": "RELIANCE", **bad})


def test_an_mtf_level_fires_on_crossing_only():
    a = {"kind": "mtf", "symbol": "X", "op": "above", "value": 1.0, "created_at": "2026-09-01"}
    ev = lambda day, pct, was=None: [{"kind": "mtf", "symbol": "X", "day": day, "pct": pct, "was": was, "crore": 12.5}]   # noqa: E731
    text, st = stock_alerts.evaluate_event(a, ev("2026-09-29", 0.8))
    assert text is None and st["side"] == "below"
    text, st = stock_alerts.evaluate_event({**a, "state": st}, ev("2026-09-29", 1.2))     # the same day again: nothing
    assert text is None
    text, st = stock_alerts.evaluate_event({**a, "state": st}, ev("2026-09-30", 1.2))
    assert text.startswith("X: margin-funded shares were 1.20% of shares issued on 2026-09-30") and "above your 1% level" in text
    assert not ADVICE.search(text) and not PROVIDERS.search(text)
    text, st = stock_alerts.evaluate_event({**a, "state": st}, ev("2026-10-01", 1.3))     # still above: once
    assert text is None
    text, _ = stock_alerts.evaluate_event(a, ev("2026-10-01", 1.3, was=0.9))             # first day, crossed from the day before
    assert text


def test_mwpl_events_reach_the_alerts_of_users_on_a_plan_with_them(w, paid, monkeypatch):
    sent = []
    for tok in ("basic-token", "free-token"):
        uid = "u-basic" if tok == "basic-token" else "u-free"
        db.set_setting(f"stockalerts:{uid}", json.dumps({"items": [{"id": "a1", "region": "IN", "symbol": "SAIL", "kind": "mwpl",
                                                                    "status": "active", "created_at": "2026-09-01T00:00:00+00:00", "rev": 1}]}))
    ev = [{"kind": "mwpl", "symbol": "SAIL", "day": "2026-10-01", "id": "2026-10-01:SAIL:mwpl:up", "text": "MWPL use rose to 81.0% on 1 Oct 2026 (from 79.0%)."}]
    n = stock_alerts.fire_events(ev, datetime(2026, 10, 1, 20, 0, tzinfo=IST), lambda p: 25,
                                 send=lambda p, s, t: sent.append((p["id"], t)) or ["push"], kind_ok=__import__("app.main").main._alert_kind_ok)
    assert n == 1 and [s[0] for s in sent] == ["u-basic"] and "SAIL: MWPL use rose to 81.0%" in sent[0][1]


# ---------- the routes ----------
def test_routes_answer_with_the_plan_gates(w, paid):
    fill()
    c = w["client"]
    assert c.get("/trade/stock-futures").status_code == 401
    free = c.get("/trade/stock-futures", headers=headers("free-token")).json()
    assert free["full"] is False and free["rows"] and free["plan_needed"] == "Basic"
    one = c.get("/trade/stock-futures/RELIANCE", headers=headers("free-token")).json()
    assert one["row"]["symbol"] == "RELIANCE" and one["history"] is None
    basic = c.get("/trade/stock-futures/reliance?range=1m", headers=headers("basic-token")).json()
    assert basic["history"] and basic["full"] is True
    assert c.get("/trade/stock-futures/WIPRO", headers=headers("basic-token")).status_code == 404
    assert c.get("/trade/stock-futures/BAD SYMBOL!", headers=headers("basic-token")).status_code == 400
    assert c.get("/trade/stock-futures/RELIANCE?range=10y", headers=headers("basic-token")).status_code == 400

    m = c.get("/invest/margin-funding/RELIANCE", headers=headers("free-token")).json()
    assert m["funded"] and "history" not in m and m["full"] is False
    assert c.get("/invest/margin-funding/RELIANCE", headers=headers("basic-token")).json()["history"]
    assert c.get("/invest/margin-funding/x$y", headers=headers("basic-token")).status_code == 400
    ok = c.post("/invest/margin-funding/cost", headers=headers("free-token"),
                json={"buy": 500, "qty": 10, "margin_pct": 30, "rate_pct": 14, "days": 30})
    assert ok.status_code == 200 and ok.json()["funded"] == 3500
    for bad in ({}, {"buy": -1, "qty": 1, "margin_pct": 30, "rate_pct": 1, "days": 1},
                {"buy": 1, "qty": 1, "margin_pct": 100, "rate_pct": 1, "days": 1}, {"buy": "x", "qty": 1, "margin_pct": 1, "rate_pct": 1, "days": 1},
                {"buy": 1, "qty": 1, "margin_pct": 30, "rate_pct": 1, "days": 1, "maint_pct": 100}):
        assert c.post("/invest/margin-funding/cost", headers=headers("free-token"), json=bad).status_code == 422

    db.set_setting("watchlist:u-free", json.dumps({"items": [{"region": "IN", "symbol": "TCS"}, {"region": "IN", "symbol": "RELIANCE"}]}))
    lend = c.get("/invest/stock-lending", headers=headers("free-token")).json()
    assert [r["symbol"] for r in lend["rows"]] == ["TCS", "RELIANCE"] and lend["facts"] and lend["rows"][1]["watched"]
    assert c.get("/invest/stock-lending/RELIANCE", headers=headers("free-token")).json()["trades"]
    assert c.get("/invest/stock-lending/a b", headers=headers("free-token")).status_code == 400
    mf = c.get("/invest/margin-funding", headers=headers("free-token")).json()
    assert [r["symbol"] for r in mf["rows"]] == ["TCS", "RELIANCE"] and mf["market"]["end"] and "history" not in mf["market"]

    # alerts: MWPL and margin-funding levels are Basic and up
    r = c.post("/alerts", headers=headers("free-token"), json={"region": "IN", "symbol": "SAIL", "kind": "mwpl"})
    assert r.status_code == 402 and "Basic plan" in r.json()["detail"]["message"]
    r = c.post("/alerts", headers=headers("basic-token"), json={"region": "IN", "symbol": "SAIL", "kind": "mwpl"})
    assert r.status_code == 200 and "MWPL use was" in r.json()["note"]
    assert c.post("/alerts", headers=headers("basic-token"), json={"region": "IN", "symbol": "WIPRO", "kind": "mwpl"}).status_code == 400
    r = c.post("/alerts", headers=headers("basic-token"), json={"region": "IN", "symbol": "RELIANCE", "kind": "mtf", "op": "above", "value": 2})
    assert r.status_code == 200 and "of shares issued" in r.json()["note"]
    assert c.post("/alerts", headers=headers("free-token"), json={"region": "IN", "symbol": "RELIANCE", "kind": "mtf", "op": "above", "value": 2}).status_code == 402

    # admin
    assert c.get("/admin/stock-desks", headers=headers("pro-token")).status_code in (401, 403)
    a = c.get("/admin/stock-desks", headers=headers("admin-token")).json()
    assert set(a["desks"]) == {"fno", "slb", "mtf"}
    assert c.post("/admin/stock-desks/nope/run", headers=headers("admin-token")).status_code == 404


def test_no_advice_or_provider_names_in_what_the_pages_say(w):
    fill()
    c = w["client"]
    db.set_setting("watchlist:u-basic", json.dumps({"items": [{"region": "IN", "symbol": "SBIN"}]}))
    for path in ("/trade/stock-futures", "/trade/stock-futures/SAIL", "/invest/stock-lending", "/invest/stock-lending/RELIANCE",
                 "/invest/margin-funding", "/invest/margin-funding/SBIN"):
        text = json.dumps(c.get(path, headers=headers("basic-token")).json())
        assert not PROVIDERS.search(text), path
        words = " ".join(v for v in re.findall(r'"([^"]{25,})"', text))
        assert not ADVICE.search(words), (path, ADVICE.search(words))
