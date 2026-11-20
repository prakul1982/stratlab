"""Lane site83: the LIVE20A / LIVE20B site findings (live review after Release 82, Fri 20 Nov 2026)."""
import inspect
import json
import time
from datetime import datetime, timezone

from app import main  # noqa: F401, I001  (first: the app loads its jobs before the modules built on them)
from app import db, mood_job
from app.intel import mood


# ---------- LIVE20A-002: a Mood card kept by an earlier release is read again as the server starts, never served ----------
# 20 Nov 18:44 IST, an hour after Release 82 (free-float points, "Moved by" in the sector's direction): the first visitor got the card read at
# 15:48 IST by Release 81 ("HDFC Bank added about 47 points", fallers under "Moved by") under the new (i) text; it was read again only then.
def _card(**kw):
    return {"region": "IN", "session": "2026-11-20", "today": "2026-11-20", "is_open": False, "headline": "Positive.", "lines": [],
            "movers": [{"index": "NIFTY 50", "adding": [{"symbol": "HDFCBANK", "name": "HDFC Bank", "change_pct": 2.94, "points": 46.8}],
                        "taking": [], "of": 50}], **kw}


def _store(monkeypatch, value):
    store = {mood.KEEP_KEY + "IN": json.dumps({"at": time.time() - 3 * 3600, "value": value})}
    monkeypatch.setattr(db, "get_setting", lambda k: store.get(k))
    monkeypatch.setattr(db, "set_setting", lambda k, v: store.__setitem__(k, v))
    return store


def test_live20a_002_a_card_kept_by_an_earlier_release_is_read_again_at_once_and_never_answered_with(monkeypatch):
    from app.intel import company
    _store(monkeypatch, _card())                                  # Release 82's card: no "method"
    monkeypatch.setattr(company, "market_open", lambda region, now=None: False)
    m = mood.Mood(hub=None)
    builds = []
    monkeypatch.setattr(m, "build", lambda region: builds.append(region) or _card(method=mood.METHOD, movers=[{"index": "NIFTY 50", "adding": [
        {"symbol": "HDFCBANK", "name": "HDFC Bank", "change_pct": 2.94, "points": 77.4}], "taking": [], "of": 50}]))
    monkeypatch.setattr(m, "_session_now", lambda region: "2026-11-20")
    m.warm("IN")                                                  # the job's first pass as the server starts
    for _ in range(100):
        if m.payloads.kept("IN"):
            break
        time.sleep(0.02)
    assert builds == ["IN"]
    value, _ = m.get("IN", 5.0)
    assert value["method"] == mood.METHOD and value["movers"][0]["adding"][0]["points"] == 77.4
    # and a visit before that read is back waits for it, never getting the old card
    _store(monkeypatch, _card(method=mood.METHOD - 1))
    m2 = mood.Mood(hub=None)
    monkeypatch.setattr(m2, "build", lambda region: (time.sleep(0.3), _card(method=mood.METHOD))[1])
    monkeypatch.setattr(m2, "_session_now", lambda region: "2026-11-20")
    got, _ = m2.get("IN", 5.0)
    assert got["method"] == mood.METHOD


def test_live20a_002_a_card_of_this_release_is_taken_up_and_answered_at_once(monkeypatch):
    from app.intel import company
    _store(monkeypatch, _card(method=mood.METHOD, final=True))
    monkeypatch.setattr(company, "market_open", lambda region, now=None: False)
    m = mood.Mood(hub=None)
    monkeypatch.setattr(m, "build", lambda region: (_ for _ in ()).throw(AssertionError("not read again")))
    monkeypatch.setattr(m, "_session_now", lambda region: "2026-11-20")
    monkeypatch.setattr(mood, "is_final", lambda p: True)
    m.warm("IN")
    value, _ = m.get("IN", 1.0)
    assert value["movers"][0]["adding"][0]["points"] == 46.8 and value["final"]


def test_live20a_002_every_new_read_says_its_method_and_the_job_warms_both_markets_once():
    assert '"method": METHOD' in inspect.getsource(mood.Mood.build)
    assert mood.of_method({"method": mood.METHOD}) and not mood.of_method({}) and not mood.of_method(None)
    warmed = []
    j = mood_job.Job(read=lambda r: {}, mood=lambda r, d=None: None, warm=warmed.append)
    now = datetime(2026, 11, 21, 3, 0, tzinfo=timezone.utc)      # a Saturday: nothing else is due
    j.tick(now)
    j.tick(now)
    assert warmed == ["IN", "US"]
    assert mood_job.job.warm is mood_job._mood_warm


# ---------- LIVE20A-006: each results row says how many earlier results days are kept (no usual move without one) ----------
def test_live20a_006_results_rows_carry_their_kept_earlier_results_days(monkeypatch):
    from datetime import date
    from app import results
    cal = {"rows": [results.row("US", "BJ", date(2026, 11, 20), "Quarterly results (fiscal Q3 2027)"),
                    results.row("US", "FRO", date(2026, 11, 20), "Quarterly results")]}
    monkeypatch.setattr(results, "load", lambda region: {**cal, "v": results.CAL_VERSION, "at": "2026-11-20T04:00:00+00:00"})
    monkeypatch.setattr(results, "_snap", lambda region: {})
    monkeypatch.setattr(results, "index_sets", lambda region: {})
    monkeypatch.setattr(results, "load_moves", lambda region: {})
    monkeypatch.setattr(results, "my_stocks", lambda uid, region: [])
    monkeypatch.setattr(results, "alerts_on", lambda uid: False)
    monkeypatch.setattr(results, "load_past", lambda region: {"at": None, "rows": {"BJ": ["2026-08-21", "2026-05-22"]}})
    got = results.view("US", "u-x", scope="all", today=date(2026, 11, 20))
    rows = {r["symbol"]: r for w in got["weeks"] for r in w["rows"]}
    assert rows["BJ"]["mv_days"] == 2 and rows["FRO"]["mv_days"] == 0


# ---------- LIVE20A-007: the IPO list says when it is read next (not "within the hour") ----------
def test_live20a_007_the_next_read_is_the_markets_next_slot_or_a_busy_retry():
    from app import ipo
    # 08:24 ET on Fri 20 Nov = 18:54 IST: the US list's next read is the 21:30 IST slot (11:00 ET), not within the hour
    now = datetime(2026, 11, 20, 13, 24, tzinfo=timezone.utc)
    assert ipo.next_read("US", now, ["SEC filings for Zeno42 Inc.: The SEC is having trouble (500)."], "2026-11-20T03:00:00+00:00") == "2026-11-20T21:30+05:30"
    # India at 20:30 IST: the next morning's 07:40 read
    assert ipo.next_read("IN", datetime(2026, 11, 20, 15, 0, tzinfo=timezone.utc)) == "2026-11-21T07:40+05:30"
    # after the 21:30 US read, the 03:30 IST close read (the small hours' slot)
    assert ipo.next_read("US", datetime(2026, 11, 20, 16, 30, tzinfo=timezone.utc)) == "2026-11-21T03:30+05:30"
    # a read that met a busy source is tried again 20 minutes later, when that comes first
    assert ipo.busy("NSE: busy (429)")
    got = ipo.next_read("IN", datetime(2026, 11, 20, 6, 0, tzinfo=timezone.utc), ["NSE: busy (429)"], "2026-11-20T05:55:00+00:00")
    assert got == "2026-11-20T11:45+05:30"                       # 11:25 IST read + 20 min, before the 11:50 slot


# ---------- LIVE20B-010: a sector's share is its value over the total, rounded once ----------
def test_live20b_010_sector_shares_are_rounded_once_and_one_stock_sectors_keep_their_stocks_weight():
    from app import holdings
    # free-2's sectors on 20 Nov (₹16,79,090 in all): Financial Services ₹1,16,435 was shown 6.8% (6.93%), FMCG ₹86,313 5.2% (5.14%) ...
    fin = [40000.0, 30000.0, 20000.0, 16435.0, 10000.0]
    fmcg = [50000.0, 36313.0]
    it = [157336.0]
    rest = [1679090.0 - sum(fin) - sum(fmcg) - sum(it)]
    got = holdings.nested_split([fin, fmcg, it, rest])
    sector = [round(sum(g), 1) for g in got]
    assert sector[0] == 6.9 and sector[1] == 5.1 and sector[2] == 9.4         # 6.93%, 5.14%, 9.37% each rounded once
    assert round(sum(sector), 1) == 100.0
    assert got[2] == [9.4]                                                     # a one-stock sector: its stock's weight is the sector's
    assert all(abs(w - v / 1679090 * 100) <= 0.1 + 1e-9 for g, vals in zip(got, [fin, fmcg, it, rest]) for w, v in zip(g, vals))
    assert holdings.nested_split([[0.0], [0.0]]) == [[0.0], [0.0]]
