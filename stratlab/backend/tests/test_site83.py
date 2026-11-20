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
