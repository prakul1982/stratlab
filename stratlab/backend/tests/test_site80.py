"""Lane site80: the LIVE17A / LIVE17B site findings (live review after Release 79, Thu 19 Nov 2026)."""
import json
import threading
import time
from datetime import date, datetime
from zoneinfo import ZoneInfo

from app import main  # noqa: F401, I001  (first: the app loads its jobs before the modules built on them)
from app import breadth, db, heatmap, movers
from app.intel import ai as A, mood, routes as research_routes

NY = ZoneInfo("America/New_York")


def _mem(monkeypatch) -> dict:
    store: dict = {}
    monkeypatch.setattr(db, "get_setting", lambda k: store.get(k))
    monkeypatch.setattr(db, "set_setting", lambda k, v: store.__setitem__(k, v))
    return store


# 18 Nov's US rows as stored from the 10:52 ET copy (TJX $143.09 +10.20%), and the settled closes (TJX $140.30)
ROWS = {"TJX": [143.09, 10.2, 0, 0, 0, 0, 0, 9e6, 5e6], "SPY": [730.2, -0.31, 0, 0, 0, 0, 0, 8e7, 7e7]}
SETTLED = {"TJX": 140.30, "SPY": 730.2}


def _read(s: str) -> list[dict]:
    return [{"t": "2026-11-17T00:00:00-05:00", "c": 1.0}, {"t": "2026-11-18T00:00:00-05:00", "c": SETTLED[s]},
            {"t": "2026-11-19T00:00:00-05:00", "c": 2.0}]          # today's bar, in session: not the stored day's


class _Runner:
    running = None

    def __init__(self, fix: bool):
        self.fix, self.runs = fix, []

    def run(self, region, now):
        self.runs.append((region, now))
        if self.fix:                       # the run stores the day's settled closes
            heatmap.save("US", "2026-11-18", {s: [SETTLED[s], *r[1:]] for s, r in ROWS.items()})
        return {"ok": True}


# ---------- LIVE17A-001: the stored day is checked at the first chance after a start, whatever the hour ----------
def test_live17a_001_the_first_check_after_a_start_reads_the_stored_day_again_in_session(monkeypatch):
    _mem(monkeypatch)
    heatmap.save("US", "2026-11-18", dict(ROWS))
    runner, moods = _Runner(fix=True), []
    job = breadth.Job(runner, check_read=lambda r, s: _read(s), after_repair=moods.append)
    in_session = datetime(2026, 11, 19, 13, 30, tzinfo=NY)          # the reviewer's 13:24 ET: hours before today's run and its check
    assert job.repair("US", in_session) == ["TJX"]
    assert [r for r, _ in runner.runs] == ["US"] and moods == ["US"]
    assert heatmap.load("US")["stocks"]["TJX"][0] == 140.30 and heatmap.load("US")["unsettled"] == []
    # not again until the day's own check, two hours after the run time
    assert job.repair("US", datetime(2026, 11, 19, 14, 0, tzinfo=NY)) == [] and len(runner.runs) == 1


def test_live17a_001_rows_still_off_after_the_run_are_never_called_closes(monkeypatch):
    _mem(monkeypatch)
    heatmap.save("US", "2026-11-18", dict(ROWS))
    job = breadth.Job(_Runner(fix=False), check_read=lambda r, s: _read(s))
    assert job.repair("US", datetime(2026, 11, 19, 13, 30, tzinfo=NY)) == ["TJX"]
    assert heatmap.load("US")["unsettled"] == ["TJX"]
    assert heatmap.view("US")["unsettled"] is True
    assert movers.view("US")["unsettled"] is True
    # the public movers page doesn't say "at the close of"
    page = movers.public_page("US")
    assert "at the close of" not in page and "at prices read during that session" in page
    # a later run that stores the settled closes clears it (save writes a fresh document)
    heatmap.save("US", "2026-11-18", {s: [SETTLED[s], *r[1:]] for s, r in ROWS.items()})
    assert heatmap.load("US")["unsettled"] == [] and heatmap.view("US")["unsettled"] is False


def test_live17a_001_a_right_stored_day_is_left_alone_and_any_old_mark_cleared(monkeypatch):
    _mem(monkeypatch)
    heatmap.save("US", "2026-11-18", {s: [SETTLED[s], *r[1:]] for s, r in ROWS.items()})
    heatmap.mark_unsettled("US", ["TJX"])
    runner = _Runner(fix=True)
    job = breadth.Job(runner, check_read=lambda r, s: _read(s))
    assert job.repair("US", datetime(2026, 11, 19, 13, 30, tzinfo=NY)) == [] and runner.runs == []
    assert heatmap.load("US")["unsettled"] == []


# ---------- LIVE17A-003: the movers' sentence is whole, its unit and index named ----------
def test_live17a_003_a_day_with_only_a_taker_reads_as_a_whole_sentence():
    p = {"movers": [{"index": "S&P 500", "adding": [], "taking": [{"name": "Amazon.com", "points": -8.2}]}]}
    assert mood.lines_of(p) == ["Amazon.com took about 8 points off the S&P 500."]
    p = {"movers": [{"index": "NIFTY 50", "adding": [{"name": "Maruti Suzuki India", "points": 40.1}], "taking": [{"name": "Tata Consultancy Services", "points": -16.0}]}]}
    assert mood.lines_of(p) == ["Maruti Suzuki India added about 40 points to the NIFTY 50 and Tata Consultancy Services took about 16 points off it."]
    p = {"movers": [{"index": "S&P 500", "adding": [{"name": "NVIDIA", "points": 12.0}], "taking": []}]}
    assert mood.lines_of(p) == ["NVIDIA added about 12 points to the S&P 500."]


# ---------- LIVE17A-006: the headlines read is never "being written" for hours ----------
def _open_market(monkeypatch, store):
    from app.intel import company as C
    q = {"price": 7230.18, "change_pct": -1.28, "prev_close": 7323.63, "at": "2026-11-19T18:32:00+00:00"}
    monkeypatch.setattr(research_routes, "_levels_now", lambda r, wait: ([C.index_level("S&P 500", q, "US")], None))
    monkeypatch.setattr(research_routes, "market_open", lambda r, now=None: True)
    monkeypatch.setattr(A, "get", lambda kind, key: store.get(repr((kind, key))))
    monkeypatch.setattr(A, "peek", lambda kind, key: repr((kind, key)) in store)

    def keep(kind, key, out, ttl, persist=True):
        store[repr((kind, key))] = json.loads(json.dumps(out))
        return out
    monkeypatch.setattr(A, "keep", keep)
    research_routes._pulse_failed.clear()
    research_routes._pulse_running.clear()


def _wait_idle():
    for _ in range(100):
        if not research_routes._pulse_running:
            return
        time.sleep(0.02)


def test_live17a_006_a_failed_background_read_is_not_said_to_be_being_written(monkeypatch):
    store, calls = {}, []
    _open_market(monkeypatch, store)
    ok = threading.Event()
    ok.set()

    def call(profile, kind, key, ttl, refresh, build, **k):
        calls.append(key)
        if not ok.is_set():
            from fastapi import HTTPException
            raise HTTPException(422, {"code": "ai_failed", "message": "no"})
        return {"tone": f"read {len(calls)}", "hot": [], "flows": [], "themes": [], "generated_at": 100.0 + len(calls)}
    monkeypatch.setattr(research_routes, "ai_call", call)
    first = json.loads(research_routes.pulse_ai("US", "", False, {"id": "u1"}).body)
    assert first["tone"] == "read 1"
    ok.clear()                                                    # the AI fails from here on
    monkeypatch.setattr(research_routes, "mood_key", lambda indices, is_open: ("an hour later",))
    second = json.loads(research_routes.pulse_ai("US", "", False, {"id": "u2"}).body)
    assert second["updating"] is True                             # a write is under way: said so
    _wait_idle()
    third = json.loads(research_routes.pulse_ai("US", "", False, {"id": "u3"}).body)
    assert third["tone"] == "read 1" and not third.get("updating")      # it failed: the read is shown plainly, not "being written"
    assert len(calls) == 2                                       # and not tried again at once


def test_live17a_006_a_background_read_once_written_is_the_sessions_latest_at_once(monkeypatch):
    store, calls = {}, []
    _open_market(monkeypatch, store)

    def call(profile, kind, key, ttl, refresh, build, **k):
        calls.append(key)
        out = {"tone": f"read {len(calls)}", "hot": [], "flows": [], "themes": [], "generated_at": 100.0 + len(calls)}
        store[repr((kind, key))] = out
        return out
    monkeypatch.setattr(research_routes, "ai_call", call)
    research_routes.pulse_ai("US", "", False, {"id": "u1"})
    monkeypatch.setattr(research_routes, "mood_key", lambda indices, is_open: ("next band",))
    research_routes.pulse_ai("US", "", False, {"id": "u2"})
    _wait_idle()
    # the key moves on again before anyone asks: the newer read is shown, not the first one marked "being written"
    monkeypatch.setattr(research_routes, "mood_key", lambda indices, is_open: ("a third band",))
    monkeypatch.setattr(research_routes, "pulse_behind", lambda key, write: False)
    got = json.loads(research_routes.pulse_ai("US", "", False, {"id": "u3"}).body)
    assert got["tone"] == "read 2" and not got.get("updating")


def test_live17a_006_a_stuck_background_read_stops_being_said_to_be_written(monkeypatch):
    research_routes._pulse_running.clear()
    research_routes._pulse_running.add("k")
    research_routes._pulse_started["k"] = time.time()
    assert research_routes.pulse_writing("k")
    research_routes._pulse_started["k"] = time.time() - research_routes.PULSE_WRITE_MAX - 1
    assert not research_routes.pulse_writing("k")
    research_routes._pulse_running.discard("k")


# ---------- LIVE17A-007: an issue's first open read on its first session, from the intraday candles ----------
class _Yahoo:
    def __init__(self, daily, intraday):
        self.daily, self.intraday, self.asked = daily, intraday, []

    def chart(self, sym, tf, days, **k):
        self.asked.append(tf)
        return {"candles": self.daily if tf == "1d" else self.intraday, "meta": {}}


def test_live17a_007_the_first_sessions_open_comes_from_the_intraday_candles():
    from app import ipo as I
    row = {"id": "us-ant", "market": "US", "symbol": "ANT", "priced": "2026-11-18", "price": 83.0}
    y = _Yahoo([], [{"t": "2026-11-19T09:30:00-05:00", "o": 111.5, "h": 112, "l": 95, "c": 97.7, "v": 1}])
    now = datetime(2026, 11, 19, 13, 35, tzinfo=NY)
    p = I.performance(row, y, date(2026, 11, 19), now)
    assert p["listing_price"] == 111.5 and p["listing_change_pct"] == round((111.5 / 83 - 1) * 100, 2)
    assert p["day_close"] is None and "5m" in y.asked
    # an older issue with its daily candles reads no intraday candles
    old = {"id": "us-old", "market": "US", "symbol": "OLD", "priced": "2026-10-01", "price": 10.0}
    y2 = _Yahoo([{"t": "2026-10-02", "o": 12.0, "h": 12, "l": 11, "c": 11.5, "v": 1}, {"t": "2026-11-18", "o": 13, "h": 13, "l": 13, "c": 13, "v": 1}], [])
    assert I.performance(old, y2, date(2026, 11, 19), now)["listing_price"] == 12.0 and "5m" not in y2.asked


def test_live17a_007_the_list_reads_the_opening_price_on_the_first_session(monkeypatch):
    from app import ipo as I
    row = {"id": "us-ant", "market": "US", "name": "Anthropic, PBC", "symbol": "ANT", "priced": "2026-11-19", "price": 83.0}
    now = datetime(2026, 11, 19, 13, 35, tzinfo=NY)
    assert I.listing_session_now(row, now) and not I.listing_session_now({**row, "priced": "2026-11-01"}, now)
    monkeypatch.setattr(I, "public", lambda r, n: {"stage": "listed", **r})
    monkeypatch.setattr(I, "perf_for", lambda r, ttl=600: {"issue_price": 83.0, "listing_price": 111.5, "listing_change_pct": 34.34, "listed": "2026-11-19"})
    monkeypatch.setattr(I, "doc_links", lambda r: [])
    assert I.list_row(row, now)["perf"]["listing_price"] == 111.5
