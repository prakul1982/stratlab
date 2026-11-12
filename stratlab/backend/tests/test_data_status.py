"""Data status: each dataset's state worked out from its last update and its job's own clock (on time, updating within the run's usual
time, late past it, not updated yet, on request), a market's shut days never due, the answer built from the records Admin reads with
only safe facts in it (no job's internal name, no error text, no source or server named), the public page and its JSON for anyone,
shared for a minute, and the site's links to it."""
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app import breadth, data_status as D, db, heatmap, job_status
from tests import world as W
from tests.test_breadth import ADVICE, PROVIDERS

UTC = timezone.utc
# Thursday 12 Nov 2026, 14:00 UTC = 19:30 IST: India's 18:30 IST run is due an hour ago
THU_EVENING = datetime(2026, 11, 12, 14, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def fresh():
    D.clear()
    yield
    D.clear()


@pytest.fixture
def w(monkeypatch):
    world = W.build(monkeypatch)
    yield world
    world["close"]()


def ds(slots, grace=90, on_request=False):
    return D.Dataset("x", "X", "IN", "G", "f", lambda: (None, None), slots, grace=grace, on_request=on_request)


IN_RUN = [D.Slot(D.IST, "18:30", "IN")]


# ---------- the clock ----------
def test_updated_since_its_last_due_time_is_on_time_and_the_next_due_time_is_the_next_trading_day():
    last = datetime(2026, 11, 12, 13, 5, tzinfo=UTC)               # 18:35 IST today
    state, nxt = D.judge(ds(IN_RUN), last, THU_EVENING)
    assert state == "on_time" and nxt == datetime(2026, 11, 13, 18, 30, tzinfo=D.IST)


def test_within_the_runs_usual_time_it_is_updating_and_past_it_late():
    yesterday = datetime(2026, 11, 11, 13, 5, tzinfo=UTC)          # 18:35 IST on Wednesday
    assert D.judge(ds(IN_RUN, grace=150), yesterday, THU_EVENING)[0] == "updating"      # due 18:30, an hour ago, usually in by 21:00
    assert D.judge(ds(IN_RUN, grace=30), yesterday, THU_EVENING)[0] == "late"
    two_days = datetime(2026, 11, 10, 13, 5, tzinfo=UTC)          # Tuesday's: Wednesday's update was missed as well
    assert D.judge(ds(IN_RUN, grace=150), two_days, THU_EVENING)[0] == "late"


def test_a_markets_shut_days_are_never_due():
    sunday = datetime(2026, 11, 15, 14, 0, tzinfo=UTC)
    friday = datetime(2026, 11, 13, 13, 5, tzinfo=UTC)             # Friday's update, read on Sunday evening
    state, nxt = D.judge(ds(IN_RUN, grace=30), friday, sunday)
    assert state == "on_time" and nxt.date().isoformat() == "2026-11-16"
    every_day = ds([D.Slot(D.IST, "18:30")], grace=30)              # a dataset due every day is late on Sunday
    assert D.judge(every_day, friday, sunday)[0] == "late"


def test_never_updated_and_on_request():
    assert D.judge(ds(IN_RUN), None, THU_EVENING)[0] == "not_yet"
    assert D.judge(ds([], on_request=True), None, THU_EVENING) == ("on_request", None)


# ---------- the answer ----------
SECRET = "Couldn't reach www.nseindia.com via kite token abc (ConnectError) host stratlab-production.up.railway.app"


def seed():
    """Records as the jobs keep them: the breadth run's status (with an error text that must never reach the page), the heatmap's
    stored closes, the newsletters' per-market runs."""
    db.set_setting(breadth.STATUS_KEY, json.dumps({
        "IN": {"ran_at": "2026-11-12T13:02:00+00:00", "as_of": "2026-11-12", "loaded": 2100, "last_error": SECRET},
        "US": {"ran_at": "2026-11-11T22:05:00+00:00", "as_of": "2026-11-11", "failed_at": "2026-11-12T01:00:00+00:00", "last_error": SECRET}}))
    db.set_setting(heatmap.KEY + "IN", json.dumps({"day": "2026-11-12", "at": int(datetime(2026, 11, 12, 13, 3, tzinfo=UTC).timestamp()), "stocks": {}}))
    db.set_setting("jobstatus:newsletters", json.dumps({"last_run": "2026-11-12T10:50:00+00:00", "last_error": SECRET,
                                                        "regions": {"IN": {"day": "2026-11-12", "at": "2026-11-12T10:47:00+00:00", "sent": 3}}}))


def rows_of(v):
    return {r["id"]: r for g in v["groups"] for r in g["rows"]}


def test_the_answer_has_every_dataset_with_its_times_in_its_markets_zone(w):
    seed()
    v = D.build(THU_EVENING)
    rows = rows_of(v)
    assert {"closes-in", "closes-us", "breadth-in", "breadth-us", "flows-in", "filings-in", "filings-us", "results", "corporate-actions",
            "ipos", "brief-in", "brief-us", "themes"} <= set(rows)
    c = rows["closes-in"]
    assert c["name"] == "India closing prices" and c["market"] == "India" and c["zone"] == "IST"
    assert c["last_text"] == "12 Nov, 18:33 IST" and c["covers"] == "12 Nov 2026" and c["state"] == "on_time"
    assert c["next_text"] == "13 Nov, 18:30 IST"
    b = rows["breadth-us"]
    assert b["zone"] == "ET" and b["last_text"] == "11 Nov, 17:05 ET" and b["next_text"] == "12 Nov, 16:55 ET"
    assert rows["brief-in"]["last_text"] == "12 Nov, 16:17 IST" and rows["brief-in"]["state"] == "on_time"
    assert rows["closes-us"]["state"] == "not_yet" and rows["closes-us"]["last"] is None      # no stored closes for the US yet
    assert rows["themes"]["state"] == "on_request" and rows["themes"]["next_text"] == "When someone asks"
    assert v["late"] == sum(r["state"] == "late" for r in rows.values()) and v["total"] == len(rows)


def test_only_safe_facts_go_out(w):
    seed()
    text = json.dumps(D.build(THU_EVENING))
    assert "nseindia" not in text and "railway" not in text and "ConnectError" not in text and "Couldn't" not in text
    assert not PROVIDERS.search(text) and not ADVICE.search(text)
    # no job's internal name or key (newsletter_job, jobstatus:…, breadth-IN, newsjob:…), no counts of what was read or sent
    assert not re.search(r"_job|jobstatus|newsjob|breadth-IN|last_error|loaded|failed_at|\"sent\"", text)
    keys = {k for g in json.loads(text)["groups"] for r in g["rows"] for k in r}
    assert keys == {"id", "name", "market", "feeds", "zone", "last", "last_text", "covers", "next", "next_text", "state", "state_text"}


def test_a_record_that_cannot_be_read_is_not_updated_yet_never_an_error(w, monkeypatch):
    def boom():
        raise RuntimeError(SECRET)
    monkeypatch.setattr(breadth, "status", boom)
    rows = rows_of(D.build(THU_EVENING))
    assert rows["breadth-in"]["state"] == "not_yet" and "railway" not in json.dumps(rows)


def test_the_page_and_its_json_are_for_anyone_and_shared_for_a_minute(w, monkeypatch):
    seed()
    c = w["client"]
    calls = []
    real = D.build
    monkeypatch.setattr(D, "build", lambda now=None: calls.append(1) or real(now))
    r = c.get("/public/data-status")
    assert r.status_code == 200 and r.headers["cache-control"].startswith("public, max-age=60")
    assert r.json()["groups"][0]["rows"][0]["id"] == "closes-in"
    page = c.get("/status")
    assert page.status_code == 200 and "<h1>Data status</h1>" in page.text and len(calls) == 1      # one build for both
    assert "India time (IST)" in page.text and "New York time (ET)" in page.text
    assert 'data-id="closes-in"' in page.text and "India closing prices" in page.text
    assert "s-maxage=60" in page.headers["cache-control"]
    assert not PROVIDERS.search(page.text) and "railway" not in page.text.split("<footer")[0]
    assert c.head("/status").status_code == 200                      # a link checker's HEAD is answered


def test_the_site_links_to_the_page_and_its_host_forwards_it(w):
    from app import stock_pages
    assert '/status">Data status</a>' in stock_pages._foot()
    conf = json.loads((Path(__file__).resolve().parents[2] / "frontend" / "vercel.json").read_text())
    fwd = {r["source"]: r["destination"] for r in conf["rewrites"]}
    assert fwd["/status"].endswith(".railway.app/status")
    heads = {h["source"]: {x["key"]: x["value"] for x in h["headers"]} for h in conf["headers"]}
    assert heads["/status"] == {"x-vercel-enable-rewrite-caching": "1"}


def test_late_is_said_once_its_due_time_and_usual_run_have_passed(w):
    db.set_setting(heatmap.KEY + "IN", json.dumps({"day": "2026-11-10", "at": int(datetime(2026, 11, 10, 13, 3, tzinfo=UTC).timestamp()), "stocks": {}}))
    v = D.build(THU_EVENING)
    assert rows_of(v)["closes-in"]["state"] == "late" and v["late"] >= 1
    assert 'data-late="' in D.page_html(v) and "late." in D.page_html(v)
    job_status._written.clear()
