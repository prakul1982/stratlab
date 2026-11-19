"""Lane site79: the LIVE16A / LIVE16B site findings (live review after Release 78, Thu 19 Nov 2026)."""
import time
from datetime import datetime, timezone

import httpx
import pytest

from app import main  # noqa: F401, I001  (first: the app loads its jobs before the modules built on them)
from app.intel import yahoo as Y

# 18 Nov 2026 (New York on EST): the session 09:30-16:00 ET = 14:30-21:00 UTC; the copy the source's edge kept has its last trade at 10:52 ET
OPEN = datetime(2026, 11, 18, 14, 30, tzinfo=timezone.utc).timestamp()
CLOSE = datetime(2026, 11, 18, 21, 0, tzinfo=timezone.utc).timestamp()
KEPT = datetime(2026, 11, 18, 15, 52, 49, tzinfo=timezone.utc).timestamp()
PREV_DAY = datetime(2026, 11, 17, 14, 30, tzinfo=timezone.utc).timestamp()
RUN = datetime(2026, 11, 18, 21, 55, tzinfo=timezone.utc).timestamp()          # the evening breadth run, 16:55 ET
NEXT_DAY = datetime(2026, 11, 19, 14, 16, tzinfo=timezone.utc).timestamp()     # the reviewer's 09:16 ET, before the next open


def _answer(symbol: str, prev: float, price: float, last: float, kind: str = "EQUITY") -> dict:
    return {"chart": {"result": [{
        "meta": {"symbol": symbol, "currency": "USD", "exchangeTimezoneName": "America/New_York", "instrumentType": kind,
                 "regularMarketPrice": price, "regularMarketTime": int(last), "chartPreviousClose": prev,
                 "currentTradingPeriod": {"regular": {"start": int(OPEN), "end": int(CLOSE)}}},
        "timestamp": [int(PREV_DAY), int(OPEN)],
        "indicators": {"quote": [{"open": [prev, price], "high": [prev, price], "low": [prev, price], "close": [prev, price],
                                  "volume": [1000, 2000]}]}}], "error": None}}


def _yahoo(fresh: tuple[float, float] | None):
    """A source whose first host sends the 10:52 ET copy (TJX $143.09) and whose second sends `fresh` (price, last trade time), or the
    same copy when None."""
    seen = []

    def reply(r: httpx.Request):
        seen.append(r.url.host)
        if r.url.host == "query2.finance.yahoo.com" and fresh:
            return httpx.Response(200, json=_answer("TJX", 129.85, fresh[0], fresh[1]))
        return httpx.Response(200, json=_answer("TJX", 129.85, 143.09, KEPT))
    return Y.Yahoo(transport=httpx.MockTransport(reply)), seen


# ---------- LIVE16A-001: every stored US close is the settled one, never a copy the source's edge kept ----------
def test_live16a_001_a_kept_copy_still_counts_as_one_the_day_after_its_session():
    meta = _answer("TJX", 129.85, 143.09, KEPT)["chart"]["result"][0]["meta"]
    assert not Y.stale_edge(meta, NEXT_DAY)                       # the old bound: six hours after the close it can't be told
    assert Y.stale_edge(meta, NEXT_DAY, after=None)               # a closing read: the copy still names 18 Nov's session, kept at 10:52
    assert not Y.stale_edge({**meta, "regularMarketTime": int(CLOSE) + 2}, NEXT_DAY, after=None)    # the close's own last trade


def test_live16a_001_a_closing_read_the_next_morning_refuses_the_kept_copy():
    y, _ = _yahoo(None)
    assert y.closing_chart("TJX", 30, now=NEXT_DAY) is None
    y, seen = _yahoo((140.30, CLOSE + 1))
    assert y.closing_chart("TJX", 30, now=NEXT_DAY)["candles"][-1]["c"] == 140.30
    assert seen == ["query1.finance.yahoo.com", "query2.finance.yahoo.com"]


def test_live16a_001_the_breadth_runs_daily_reads_are_settled_closes(monkeypatch):
    from app.data.yahoo_markets import YahooProvider
    from app.data import DataError
    prov = main.markets.provider("US")
    assert isinstance(prov, YahooProvider)
    y, _ = _yahoo(None)
    monkeypatch.setattr(prov, "yahoo", y)
    monkeypatch.setattr(time, "time", lambda: RUN)
    with pytest.raises(DataError):
        main.breadth_load("US", "TJX", 30)          # both addresses send the 10:52 copy: no close, the stock is read again later
    with pytest.raises(DataError):
        main.breadth_index("US", "TJX", 30)
    y, _ = _yahoo((140.30, CLOSE + 1))
    monkeypatch.setattr(prov, "yahoo", y)
    bars = main.breadth_load("US", "TJX", 30)
    assert bars[-1]["c"] == 140.30


def test_live16a_001_a_quote_that_is_still_a_kept_copy_is_marked_and_not_kept_as_the_close(monkeypatch):
    from app.intel import company
    y, _ = _yahoo(None)
    monkeypatch.setattr(time, "time", lambda: RUN)
    q = y.meta("TJX")
    assert q["edge_stale"] is True
    y2, _ = _yahoo((140.30, CLOSE + 1))
    assert "edge_stale" not in y2.meta("TJX")
    company.forget_closed_quotes()
    monkeypatch.setattr(main.research_hub, "yahoo", y)
    monkeypatch.setattr(company, "market_open", lambda region, now=None: False)
    got, _ = main.research_hub.quotes_pending("US", ["TJX"])
    assert got["TJX"]["edge_stale"] is True
    assert company._closed_quote("US", "TJX") is None              # read again by the next page, not served for 12 hours


def test_live16a_001_moods_headline_is_never_worded_from_a_level_older_than_the_close():
    from app.intel import mood
    p = {"region": "US", "is_open": False, "session": "2026-11-18", "sectors": {"rows": [1]},
         "breadth": {"day": "2026-11-18"}, "pre_close": ["S&P 500"]}
    assert "closes of S&P 500" in mood.missing_parts(p)
    assert not mood.is_final(p)
    del p["pre_close"]
    assert mood.is_final(p)
    src = open(mood.__file__).read()
    assert 'fresh = [i for i in levels if not i.get("delayed") and not i.get("pre_close")]' in src


def test_live16a_001_moods_tables_leave_out_a_kept_copy(monkeypatch):
    from app.intel import mood
    hub = type("H", (), {"quotes": lambda self, region, syms: {"TJX": {"price": 143.09, "change_pct": 10.2, "edge_stale": True},
                                                               "PANW": {"price": 339.92, "change_pct": 9.9}}})()
    m = mood.Mood.__new__(mood.Mood)
    m.hub = hub
    assert set(m._quotes("US", ["TJX", "PANW"])) == {"PANW"}


def test_live16a_001_stored_closes_that_differ_from_the_settled_ones_run_the_market_again(monkeypatch):
    from app import breadth, heatmap
    doc = {"day": "2026-11-18", "stocks": {"TJX": [143.09, 10.2, 0, 0, 0, 0, 0, 9e6, 5e6], "SPY": [668.0, -0.53, 0, 0, 0, 0, 0, 8e7, 7e7],
                                           "TINY": [10.0, 1.0, 0, 0, 0, 0, 0, 10, 10]}}
    monkeypatch.setattr(heatmap, "load", lambda region: doc)
    settled = {"TJX": 140.30, "SPY": 668.0, "TINY": 10.0}
    read = lambda s: [{"t": "2026-11-17T00:00:00-05:00", "c": 1.0}, {"t": "2026-11-18T00:00:00-05:00", "c": settled[s]}]
    assert breadth.stored_close_drift("US", read) == ["TJX"]
    settled["TJX"] = 143.09
    assert breadth.stored_close_drift("US", read) == []

    runs, moods = [], []

    class R:
        running = None

        def run(self, region, now):
            runs.append(region)
            return {"ok": True}
    settled["TJX"] = 140.30
    job = breadth.Job(R(), check_read=lambda r, s: read(s), after_repair=moods.append)
    from zoneinfo import ZoneInfo
    ny = ZoneInfo("America/New_York")
    early = datetime(2026, 11, 18, 17, 30, tzinfo=ny)                 # before the run time plus two hours: not yet
    assert job.repair("US", early) == [] and runs == []
    late = datetime(2026, 11, 18, 19, 0, tzinfo=ny)
    assert job.repair("US", late) == ["TJX"]
    assert runs == ["US"] and moods == ["US"]
    assert job.repair("US", datetime(2026, 11, 18, 20, 0, tzinfo=ny)) == []      # once a day
    assert runs == ["US"]


# ---------- LIVE16A-005: a foreign filer's results in the currency it reports in, the dollars beside them ----------
def test_live16a_005_reported_figures_of_a_foreign_filer_are_in_its_own_currency_with_dollars():
    from app import results as R
    nums = R.reported({"epsActual": 8.07, "revenueActual": 270e9})
    assert nums == [{"label": "EPS", "value": "$8.07"}, {"label": "Revenue", "value": "$270.00 billion"}]
    got = R.in_currency(nums, "CNY", 0.14)
    assert got[0]["value"] == "CNY 8.07 (about $1.13)" and got[0]["currency"] == "CNY"
    assert got[1]["value"] == "CNY 270.00 billion (about $37.80 billion)"
    hk = R.in_currency([{"label": "Revenue", "value": "$6.69 billion"}, {"label": "EPS", "value": "-$0.40"}], "HKD", 0.128)
    assert hk[0]["value"] == "HKD 6.69 billion (about $856.3 million)"
    assert hk[1]["value"] == "-HKD 0.40 (about -$0.05)"
    assert R.in_currency(nums, "USD", None) == nums and R.in_currency(nums, None, None) == nums
    assert R.in_currency(nums, "CNY", None)[1]["value"] == "CNY 270.00 billion"          # no rate: no dollar figure, never a guess
    assert R.in_currency(got, "CNY", 0.14) == got                                          # already converted: as it is


def test_live16a_005_the_results_page_converts_stored_rows_and_the_screener_row_carries_the_currency(monkeypatch):
    from app import results as R, screens
    f = {"name": "Alibaba Group Holding", "price": 150.0, "report_currency": "CNY", "fx": {"rate": 0.14, "at": "2026-11-19"}, "foreign": True}
    row = screens.row("US", "BABA", f)
    assert row["report_currency"] == "CNY" and row["fx_usd"] == 0.14
    assert "report_currency" not in screens.row("US", "AAPL", {"name": "Apple", "price": 200.0})
    assert "report_currency" not in screens.row("IN", "TCS", {"name": "TCS", "price": 2342.7, "report_currency": "INR"})
    assert R._report_currency("BABA", {"BABA": row}) == ("CNY", 0.14)
