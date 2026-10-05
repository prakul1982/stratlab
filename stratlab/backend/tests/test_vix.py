"""India VIX: reading the exchange's real answers (trimmed fixtures), the stored history in 90-day pieces, the panel,
the job, the routes, the "india_vix" rule values in backtests, and the verdict's nearby check nudging a VIX cut-off."""
import json
import re
from datetime import date, datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from app import main  # noqa: I001  (first: the app loads the newsletter job before the modules built on it)
from app import db, vix as V
from app.engine import indicators as I
from app.engine.verdict import _param_keys, _values, _with
from app.models import Strategy
from tests import fake_vix as FV
from tests import world as W
from tests.fake_db import headers

IST = timezone(timedelta(hours=5, minutes=30))
PROVIDERS = re.compile(r"kite|zerodha|yahoo|screener|finnhub|amfi|nseindia|bseindia", re.I)
ADVICE = re.compile(r"\b(buy|sell|hold|avoid|cheap|expensive|bullish|bearish|expected move|probability)\b", re.I)


@pytest.fixture
def w(monkeypatch):
    world = W.build(monkeypatch)
    V.forget()
    yield world
    world["close"]()
    V.forget()


class Nse:
    """The exchange client's _get, answering from fake_vix, counting calls."""
    def __init__(self, fail=False):
        self.calls, self.fail = [], fail

    def _get(self, path, params, referer=None, circuit="main"):
        self.calls.append((path, dict(params)))
        if self.fail:
            from app.intel.net import SourceError
            raise SourceError("the exchange", "down", busy=True)
        return FV.answer(path, params)


# ---------- the exchange's answers (real, trimmed) ----------
def test_parse_real_history():
    rows = V.parse_history(FV.fixture("vixhistory.json"))
    assert list(rows)[:2] == ["2026-09-01", "2026-09-02"] and rows["2026-09-01"] == [11.19, 12.1225, 9.2475, 11.49]
    assert V.parse_history({"data": [{"EOD_TIMESTAMP": "junk", "EOD_CLOSE_INDEX_VAL": 3}, "x", {}]}) == {}
    assert V.parse_history(None) == {} and V.parse_history({"data": "nope"}) == {}


def test_parse_real_quote():
    q = V.parse_quote(FV.fixture("allIndices.json"))
    assert q["value"] == 15.03 and q["prev_close"] == 14.46 and q["change"] == 0.57 and q["change_pct"] == 3.94
    assert q["as_of"] == "2026-10-05T12:04+05:30" and q["year_high"] == 28.91 and q["source"] == "exchange"
    assert V.parse_quote({"data": [{"index": "NIFTY 50", "last": 22448.6}]}) is None and V.parse_quote([]) is None


def test_parse_real_graph_drops_the_pre_open():
    pts = V.parse_graph(FV.fixture("graph.json"))
    assert pts and pts[0]["t"] == "2026-10-05T09:08+05:30" and pts[-1] == {"t": "2026-10-05T12:07+05:30", "v": 15.21}
    assert len({p["t"] for p in pts}) == len(pts) and all(p["t"] >= "2026-10-05T09:08" for p in pts)
    assert V.parse_graph({"data": {"grapthData": [["x", 1], [1, "bad"]]}}) == [] and V.parse_graph(None) == []


# ---------- storage and reading ----------
def test_fetch_reads_in_pieces_and_stores_by_year(w):
    nse = Nse()
    got = V.fetch(date(2025, 11, 1), date(2026, 3, 1), nse, sleep=lambda s: None)
    assert len(nse.calls) == 2 and nse.calls[0][1] == {"from": "01-11-2025", "to": "29-01-2026"}
    assert nse.calls[1][1]["from"] == "30-01-2026"
    assert "2025-12-31" in got and "2026-02-27" in got
    assert db.get_setting("vix:daily:2025") and db.get_setting("vix:daily:2026")
    assert V.closes()["2026-02-27"] == FV.close_on(date(2026, 2, 27))
    assert [d for d, _ in V.daily("2026-02-25", date(2026, 3, 1))] == ["2026-02-25", "2026-02-26", "2026-02-27"]


def test_percentile():
    past = [float(x) for x in range(10, 110)]
    p = V.percentile(60, past)
    assert p["percentile"] == 50.0 and p["low"] == 10 and p["high"] == 109
    assert V.percentile(60, past[:20])["percentile"] is None and V.percentile(None, past)["percentile"] is None


def test_panel(w, monkeypatch):
    today = datetime.now(IST).date()
    V.fetch(today - timedelta(days=370), today, Nse(), sleep=lambda s: None)
    p = V.panel(main.options_data, feed=Nse())
    assert p["value"] == 15.03 and p["quote"]["change"] == 0.57 and p["intraday"]
    assert 200 < len(p["history"]) < 270 and p["percentile"]["percentile"] is not None
    assert p["stored"]["days"] >= len(p["history"]) and p["stored"]["last"] == p["history"][-1]["day"]
    assert "nifty_iv" in p and isinstance(p["nifty_iv"]["series"], list)
    # the exchange down: the feed's India VIX quote stands in, with the change from the stored close
    V.forget()
    monkeypatch.setattr(main.options_data, "ready", lambda: True)
    monkeypatch.setattr(main.options_data, "quotes", lambda keys: {"NSE:INDIA VIX": {"ltp": 16.0, "ts": "2026-10-05T12:00:00"}})
    p = V.panel(main.options_data, feed=Nse(fail=True))
    assert p["quote"]["source"] == "feed" and p["value"] == 16.0 and p["quote"]["prev_close"] is not None
    assert p["intraday"] == []


def test_routes(w):
    c = w["client"]
    r = c.get("/trade/vix", headers=headers("free-token"))
    assert r.status_code == 200
    body = r.json()
    assert body["value"] == 15.03 and body["note"]
    text = json.dumps(body)
    assert not PROVIDERS.search(text) and not ADVICE.search(text)
    assert c.get("/trade/vix/history?range=1y", headers=headers("free-token")).status_code == 200
    assert c.get("/trade/vix/history?range=10y", headers=headers("free-token")).status_code == 400
    assert c.get("/trade/vix").status_code == 401


def test_job_first_year_then_close_then_backfill(w, monkeypatch):
    nse = Nse()
    job = V.Job(lambda: nse, sleep=lambda s: None)
    from app.data import calendar
    monkeypatch.setattr(calendar, "is_trading_day", lambda region, d: d.weekday() < 5)
    noon = datetime(2026, 10, 5, 12, 0, tzinfo=IST)
    assert job.tick(noon.astimezone(timezone.utc)) > 200            # nothing stored: the last year at once
    n = len(nse.calls)
    job.tick((noon + timedelta(minutes=5)).astimezone(timezone.utc))
    assert len(nse.calls) == n                                       # in market hours, nothing more
    job.tick(datetime(2026, 10, 5, 15, 55, tzinfo=IST).astimezone(timezone.utc))
    assert db.get_setting("newsjob:vix-close") == "2026-10-05" and len(nse.calls) == n + 1
    job.tick(datetime(2026, 10, 5, 20, 0, tzinfo=IST).astimezone(timezone.utc))
    st = V.state()
    assert len(nse.calls) == n + 1 + V.STEP and st["back"] < "2025-10-01" and not st["done"]
    assert V.daily(st["back"], date(2026, 10, 5))[0][0] >= st["back"]


def test_job_survives_the_exchange_being_down(w):
    job = V.Job(lambda: Nse(fail=True), sleep=lambda s: None)
    with pytest.raises(Exception):
        job.tick(datetime(2026, 10, 5, 12, 0, tzinfo=IST).astimezone(timezone.utc))
    assert not V.daily()      # nothing half-stored; the loop logs the error and tries again later


# ---------- India VIX in rules ----------
CLOSES = {"2026-09-28": 12.0, "2026-09-29": 15.0, "2026-09-30": 18.0}


def test_rule_values_on_daily_and_intraday_candles():
    daily = pd.DataFrame({"t": pd.to_datetime(["2026-09-28", "2026-09-29", "2026-09-30", "2026-10-01"])})
    v = I.market_values(daily, "india_vix", False, CLOSES).tolist()
    assert v == [12.0, 15.0, 18.0, 18.0]                            # a day it doesn't have: the last close before it
    chg = I.market_values(daily, "india_vix_chg", False, CLOSES).to_numpy()
    assert np.isnan(chg[0]) and chg[1] == pytest.approx(25.0) and chg[2] == pytest.approx(20.0)
    intra = pd.DataFrame({"t": pd.to_datetime(["2026-09-29 09:15", "2026-09-29 15:15", "2026-09-30 09:15"])})
    assert I.market_values(intra, "india_vix", True, CLOSES).tolist() == [12.0, 12.0, 15.0]   # the previous day's close
    early = pd.DataFrame({"t": pd.to_datetime(["2026-09-01"])})
    assert np.isnan(I.market_values(early, "india_vix", False, CLOSES)[0])
    assert np.isnan(I.market_values(daily, "india_vix", False, {})).all()


def test_backtest_rule_reads_the_stored_history(monkeypatch):
    monkeypatch.setattr(V, "closes", lambda: CLOSES)
    from app.engine.core import Ctx
    from app.models import Ref
    bars = [{"t": d, "o": 1, "h": 1, "l": 1, "c": 1, "v": 0} for d in CLOSES]
    ctx = Ctx(bars, intraday=False)
    assert ctx.val(Ref(t="india_vix"), 2) == 18.0 and I.ref_name(Ref(t="india_vix_chg")) == "India VIX change %"


def test_nearby_check_nudges_the_vix_cut_off():
    s = Strategy(**{"name": "x", "tf": "1d", "entry": [{"l": {"t": "india_vix"}, "op": "lt", "r": {"t": "num", "v": 17}},
                                                       {"l": {"t": "price"}, "op": "xa", "r": {"t": "sma", "p": 20}}],
                    "exit": [{"l": {"t": "price"}, "op": "xb", "r": {"t": "sma", "p": 20}}]})
    keys = _param_keys(s)
    assert keys == [("india_vix", 17.0), ("sma", 20)]
    assert _values(keys[0]) == [10.0, 13.5, 17.0, 20.5, 24.0]
    assert _values(("india_vix_chg", 5.0)) == [3.0, 4.0, 5.0, 6.0, 7.0]
    s2 = _with(s, {("india_vix", 17.0): 20.5})
    assert s2.entry[0].r.v == 20.5 and s.entry[0].r.v == 17
