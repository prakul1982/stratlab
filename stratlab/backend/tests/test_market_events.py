"""Market events calendar: reading each official source (from real samples fetched on 5 Oct 2026 and trimmed, in
fixtures/market_events), the dated list with its published figures, index changes and their badges, expiries and
holidays from what the app keeps, a source that fails, the routes and their plan gate, the reminders, the Money
calendar opt-in and the twice-a-day job."""
import json
import re
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pytest

from app import db, main  # noqa: F401  (main first: it loads the modules in the order they need)
from app import market_events as M, market_events_routes as R
from app.config import settings
from app.intel.net import SourceError
from tests import world as W
from tests.fake_db import headers

SAMPLES = Path(__file__).parent / "fixtures" / "market_events"
TODAY = date(2026, 10, 5)
PROVIDERS = re.compile(r"kite|zerodha|yahoo|screener|finnhub|nseindia|bseindia|niftyindices|mospi\.gov|rbi\.org|bls\.gov", re.I)
ADVICE = re.compile(r"\b(buy|sell|accumulate|avoid|risky|bullish|bearish|expected to|likely to|should)\b", re.I)


def sample(name: str) -> str:
    return (SAMPLES / name).read_text()


@pytest.fixture
def w(monkeypatch):
    world = W.build(monkeypatch)
    R.forget()
    yield world
    world["close"]()
    R.forget()


@pytest.fixture
def paid(monkeypatch):
    monkeypatch.setattr(settings, "RAZORPAY_KEY_ID", "rzp_live_x")
    monkeypatch.setattr(settings, "RAZORPAY_KEY_SECRET", "secret")
    monkeypatch.setattr(settings, "RAZORPAY_PLAN_BASIC", "plan_b")
    monkeypatch.setattr(settings, "RAZORPAY_PLAN_PRO", "plan_p")


RBI_MARCH = ("<table><tr><td class=\"tableheader\" colspan=\"4\"><b>Mar 23, 2026<b></td></tr><tr><td><a class='link2' "
             "href=BS_PressReleaseDisplay.aspx?prid=62422>Meeting Schedule of the Monetary Policy Committee for 2026-2027</a></td></tr>"
             "<tr><td><a class='link2' href=BS_PressReleaseDisplay.aspx?prid=62423>RBI imposes monetary penalty on a bank</a></td></tr></table>")


class FakeWeb:
    """The official pages as the samples have them; `down` names sources that fail, `calls` counts the requests."""

    def __init__(self, down: set[str] | None = None):
        self.down = down or set()
        self.calls: list[str] = []

    def _check(self, what):
        self.calls.append(what)
        if any(d in what for d in self.down):
            raise SourceError(what, f"{what} isn't answering.", busy=True)

    def rbi_month(self, year, month, first=False):
        self._check(f"rbi:list:{year}-{month}")
        return {(2026, 8): sample("rbi_list_2026_08.html"), (2026, 3): RBI_MARCH}.get((year, month), "<table></table>")

    def text(self, url, ua=None):
        self._check(url)
        if url == M.RBI_PR.format("62422"):
            return sample("rbi_schedule_2026_27.html")
        if url == M.RBI_PR.format("63287"):
            return sample("rbi_statement_2026_08.html")
        if url == M.FED_CAL:
            return sample("fomc_calendar.html")
        if url.endswith("monetary20260916a.htm"):
            return sample("fed_statement_20260916.html")
        if url == M.BLS_ICS:
            assert ua == M.BLS_UA            # the bureau's file wants a named robot
            return sample("bls_schedule.ics")
        if url == M.INDEX_LIST:
            return sample("index_press_releases.html")
        raise SourceError(url, "not found")

    def json(self, url, body=None):
        self._check(url)
        if url.endswith("get-latest-release-calender"):
            return json.loads(sample("mospi_latest_arc.json"))
        if url.endswith("fetch-all-release-calender-Web"):
            assert body and body["year"] in (2026, 2025)
            return json.loads(sample("mospi_releases_2026.json")) if body["year"] == 2026 else {"data": []}
        raise SourceError(url, "not found")

    def pdf_text(self, url, pages=60):
        self._check(url)
        if "releaseCalender" in url:
            return sample("mospi_arc_2026_27.txt")
        if "CPI_for_August_2026" in url:
            return sample("mospi_cpi_2026_08.txt")
        if "IIP_Press_Release_August_2026" in url:
            return sample("mospi_iip_2026_08.txt")
        if "GDP_Estimates_for_Q1" in url:
            return sample("mospi_gdp_2026_q1.txt")
        if url.endswith("ind_prs10082026.pdf"):
            return sample("index_replacements_2026_09_30.txt")
        raise ValueError("Not a PDF.")


# ---------- reading each source ----------
def test_the_central_banks_schedule_statement_and_minutes():
    items = M.read_rbi_list(sample("rbi_list_2026_08.html"))
    mpc = [(i["prid"], i["date"], M._rbi_kind(i["title"])) for i in items if M._rbi_kind(i["title"])]
    assert mpc == [("63403", "2026-08-19", "minutes"), ("63287", "2026-08-05", "statement")]
    assert all(re.fullmatch(r"\d{4}-\d{2}-\d{2}", i["date"]) for i in items) and len(items) > 5
    sched = M.read_rbi_schedule(sample("rbi_schedule_2026_27.html"))
    assert [(s["start"], s["end"]) for s in sched] == [("2026-04-06", "2026-04-08"), ("2026-06-03", "2026-06-05"), ("2026-08-03", "2026-08-05"),
                                                       ("2026-10-05", "2026-10-07"), ("2026-12-02", "2026-12-04"), ("2027-02-03", "2027-02-05")]
    assert M.read_rbi_statement(sample("rbi_statement_2026_08.html")) == {"repo": 5.25, "move": "unchanged"}
    assert M.read_rbi_statement("the MPC voted to reduce the policy repo rate by 25 basis points to 5.00 per cent.") == {"repo": 5.0, "move": "cut"}
    assert M.read_rbi_statement("nothing about rates") is None
    assert M.meeting_span("September 29 to October 1, 2025") == (date(2025, 9, 29), date(2025, 10, 1))
    assert M.meeting_span("June 4 and 5, 2026") == (date(2026, 6, 4), date(2026, 6, 5))
    assert M.meeting_span("no dates here") is None and M.meeting_span("June 4 and 25, 2026") is None


def test_the_fomc_calendar_and_a_statement():
    meetings = M.read_fomc(sample("fomc_calendar.html"))
    assert len(meetings) == 16 and meetings[0]["start"] == "2026-01-27" and meetings[0]["end"] == "2026-01-28"
    sep = {m["end"]: m["sep"] for m in meetings}
    assert sep["2026-03-18"] is True and sep["2026-04-29"] is False and "2027-12-08" in sep
    assert meetings[0]["statement_url"].endswith("monetary20260128a.htm") and meetings[0]["minutes"] == "2026-02-18"
    assert M.read_fed_statement(sample("fed_statement_20260916.html")) == {"low": 3.75, "high": 4, "move": "raised"}
    held = "The Committee decided to maintain the target range for the federal funds rate at 3-1/2 to 3-3/4 percent."
    assert M.read_fed_statement(held) == {"low": 3.5, "high": 3.75, "move": "unchanged"}
    cross = ('<div class="panel panel-default"><h4>2027 FOMC Meetings</h4><div class="row fomc-meeting">'
             '<div class="fomc-meeting__month col"><strong>Apr/May</strong></div><div class="fomc-meeting__date col">30-1</div></div>'
             '<div class="row fomc-meeting"><div class="fomc-meeting__month col"><strong>August</strong></div>'
             '<div class="fomc-meeting__date col">22 (notation vote)</div></div></div>')
    assert [(m["start"], m["end"]) for m in M.read_fomc(cross)] == [("2027-04-30", "2027-05-01")]


def test_the_us_release_schedule_and_india_times():
    rows = M.read_bls_ics(sample("bls_schedule.ics"))
    assert {"kind": "us_cpi", "date": "2026-10-14", "time": "08:30"} in rows
    assert {"kind": "us_jobs", "date": "2026-11-06", "time": "08:30"} in rows
    assert {r["kind"] for r in rows} == {"us_cpi", "us_jobs"}              # producer prices and the rest are left out
    assert M.ist_time(date(2026, 10, 14), "08:30", M.NY) == (date(2026, 10, 14), "18:00")     # New York on summer time
    assert M.ist_time(date(2026, 11, 6), "08:30", M.NY) == (date(2026, 11, 6), "19:00")
    assert M.ist_time(date(2026, 12, 9), "14:00", M.NY) == (date(2026, 12, 10), "00:30")      # a Fed decision lands after midnight


def test_the_statistics_ministrys_calendar_releases_and_figures():
    arc = M.read_arc(sample("mospi_arc_2026_27.txt"))
    by = {(a["kind"], a["date"]): a for a in arc}
    assert by[("cpi", "2026-04-12")]["released"] == "2026-04-13"          # set for the 12th, came on the 13th
    assert by[("cpi", "2026-10-12")]["released"] is None and ("iip", "2026-11-28") in by
    assert by[("gdp", "2026-11-30")]["title"] == "Quarterly Estimates of GDP for Q2, FY 2026-27"
    assert ("gdp", "2027-01-07") in by and ("cpi", "2027-03-12") in by      # January to March are next year
    assert not any("PLFS" in a["title"] or "Services Production" in a["title"] for a in arc)
    rel = M.read_mospi_releases(json.loads(sample("mospi_releases_2026.json")))
    cpi = [r for r in rel if r["kind"] == "cpi" and r["date"] == "2026-09-14"]
    assert cpi and cpi[0]["pdf"].endswith("Press_Release_of_CPI_for_August_2026.pdf")
    assert M.read_india_figure("cpi", sample("mospi_cpi_2026_08.txt")) == {
        "label": "CPI inflation", "value": 4.82, "period": "August 2026", "previous": 4.45, "previous_label": "the month before"}
    assert M.read_india_figure("iip", sample("mospi_iip_2026_08.txt"))["value"] == 8.0
    assert M.read_india_figure("iip", sample("mospi_iip_2026_08.txt"))["previous_label"] == "July 2026"
    assert M.read_india_figure("iip", "The IIP growth rate for the month of May 2026 is (-) 1.2 percent which was 0.5 percent "
                                      "(Quick Estimate) in the month of April 2026.")["value"] == -1.2
    gdp = M.read_india_figure("gdp", sample("mospi_gdp_2026_q1.txt"))
    assert (gdp["value"], gdp["period"], gdp["previous"]) == (7.8, "Q1 FY 2026-27", 6.9)
    assert M.read_india_figure("cpi", "no numbers") is None and M.read_india_figure("wpi", "x") is None


def test_index_changes_from_the_providers_press_releases():
    items = M.read_index_list(sample("index_press_releases.html"))
    titles = [i["title"] for i in items]
    assert "Replacements in indices w.e.f. September 30, 2026" in titles
    assert not any("Nifty IPO" in t or "Fixed Income" in t or "launches" in t for t in titles)
    assert all(i["url"].startswith("https://") and i["url"].endswith(".pdf") for i in items)
    got = M.read_index_changes(sample("index_replacements_2026_09_30.txt"), "Replacements in indices w.e.f. September 30, 2026")
    assert got["effective"] == "2026-09-30"
    secs = {s["index"]: s for s in got["sections"]}
    assert secs["Nifty 50"] == {"index": "Nifty 50", "in": [["BSE", "BSE Ltd."]], "out": [["WIPRO", "Wipro Ltd."]]}
    assert len(secs["Nifty 500"]["in"]) == 27 and ["VAML", "Vedanta Aluminium Metal Ltd."] in secs["Nifty 500"]["in"]
    assert ["IDEA", "Vodafone Idea Ltd."] in secs["Nifty 100"]["in"] and "Nifty Next 50" in secs and "Nifty Auto" in secs


# ---------- the dated list ----------
def test_refresh_keeps_each_source_and_builds_the_list(w):
    web = FakeWeb()
    out = M.refresh(web, TODAY)
    assert out["problems"] == [] and set(out["read"]) == {"rbi", "fed", "us_data", "india_data", "index"}
    assert "rbi:list:2026-3" in web.calls                           # no schedule kept yet: looked back to March
    evs = M.events(TODAY, frm=date(2026, 8, 1), to=date(2026, 12, 31))
    by = {e["id"]: e for e in evs}
    aug = by["rbi:2026-08-05"]
    assert aug["figure"] == "Repo rate 5.25%, unchanged" and aug["status"] == "released" and aug["url"].endswith("prid=63287")
    assert by["rbi:2026-10-07"]["status"] == "scheduled" and by["rbi:2026-10-07"]["figure"] is None
    assert by["rbi-min:2026-08-05"]["date"] == "2026-08-19" and by["rbi-min:2026-10-07"]["date"] == "2026-10-21"
    fed = by["fomc:2026-09-16"]
    assert fed["date"] == "2026-09-16" and fed["time"] == "23:30" and fed["figure"] == "Target range 3.75% to 4.00%, raised"
    assert by["fomc:2026-12-09"]["date"] == "2026-12-10" and by["fomc:2026-12-09"]["time"] == "00:30"
    assert by["us_cpi:2026-10-14"]["time"] == "18:00" and by["us_cpi:2026-10-14"]["status"] == "scheduled"
    cpi = by["cpi:2026-09-12"]
    assert cpi["date"] == "2026-09-14" and cpi["figure"] == "CPI inflation 4.82% (August 2026)" and cpi["previous"] == "The month before: 4.45%"
    assert by["iip:2026-09-28"]["figure"] == "IIP growth 8.0% (August 2026)"
    sat = by["iip:2026-11-28"]                                      # a Saturday: the next working day
    assert sat["date"] == "2026-11-30" and "next working day" in sat["detail"] and sat["status"] == "scheduled"
    idx = [e for e in evs if e["kind"] == "index"]
    assert idx and idx[0]["date"] == "2026-09-30" and "BSE" in idx[0]["symbols"] and "Nifty 50: in BSE; out WIPRO" in idx[0]["detail"]
    assert [e["date"] for e in evs] == sorted(e["date"] for e in evs)
    words = " ".join(e["title"] + " " + e["detail"] + " " + (e["figure"] or "") for e in evs)
    assert not PROVIDERS.search(words) and not ADVICE.search(words)
    # a second run reads only the last two months of releases and nothing it read before
    web2 = FakeWeb()
    M.refresh(web2, TODAY)
    assert "rbi:list:2026-3" not in web2.calls and M.RBI_PR.format("62422") not in web2.calls
    assert not any("CPI_for_August" in c for c in web2.calls)       # figures are read once


def test_a_failing_source_keeps_its_last_copy(w):
    M.refresh(FakeWeb(), TODAY)
    out = M.refresh(FakeWeb(down={M.FED_CAL, "mospi"}), TODAY)
    assert len(out["problems"]) == 2 and "rbi" in out["read"]
    src = {s["id"]: s for s in M.sources()}
    assert src["fed"]["failed"] and src["india_data"]["failed"] and not src["rbi"]["failed"] and src["fed"]["as_of"] == "2026-10-05"
    ids = {e["id"] for e in M.events(TODAY)}
    assert "fomc:2026-10-28" in ids and "cpi:2026-10-12" in ids          # still listed from the last good copy


def test_badges_for_stocks_going_in_and_out_of_an_index(w):
    M.refresh(FakeWeb(), TODAY)
    before = M.badges(date(2026, 9, 20))
    assert before["BSE"][0]["short"] == "Joins NIFTY 50 from 30 Sep" and before["WIPRO"][0]["short"] == "Leaves NIFTY 50 from 30 Sep"
    assert "goes into the Nifty 50 index from 30 Sep 2026" in before["BSE"][0]["text"]
    after = M.badges(TODAY)
    assert after["BSE"][0]["short"] == "Joined NIFTY 50 on 30 Sep" and len(after["BSE"]) <= 2
    # one badge a direction, the first-listed index first: into the Next 50 (and the Nifty 100), out of the Midcap 150
    assert [(b["way"], b["index"]) for b in after["IDEA"]] == [("in", "Nifty Next 50"), ("out", "Nifty Midcap 150")]
    assert M.badges(date(2026, 11, 15)) == {}                       # gone a month after the change


def test_expiries_and_holidays_from_what_the_app_keeps(w):
    evs = M.expiry_events(TODAY, None, TODAY, date(2026, 11, 30))
    monthly = [e["date"] for e in evs if e["title"] == "Monthly F&O expiry"]
    assert monthly == ["2026-10-27", "2026-11-23"]                  # the last Tuesday by the rule (24 Nov is a holiday)
    weekly = [e["date"] for e in evs if e["title"] == "NIFTY weekly expiry"]
    assert "2026-10-06" in weekly and "2026-10-27" not in weekly and all(date.fromisoformat(d).weekday() <= 1 for d in weekly)
    listed = lambda ex, name: ["2026-10-06", "2026-10-13", "2026-10-26"]  # noqa: E731  (a holiday moved the month's last)
    evs = M.expiry_events(TODAY, listed, TODAY, date(2026, 10, 31))
    assert [e["date"] for e in evs if e["title"] == "Monthly F&O expiry"] == ["2026-10-26"]
    assert [e["date"] for e in evs if e["title"] == "NIFTY weekly expiry"] == ["2026-10-06", "2026-10-13"]
    hol = M.holiday_events(TODAY, date(2026, 9, 25), date(2026, 10, 3))
    assert [e["date"] for e in hol] == ["2026-10-02"] and "Gandhi Jayanti" in hol[0]["title"]


# ---------- the routes ----------
def test_routes_view_prefs_and_the_plan_gate(w, paid):
    c = w["client"]
    M.refresh(FakeWeb(), TODAY)
    assert c.get("/trade/events").status_code == 401
    r = c.get("/trade/events", headers=headers("free-token"))
    v = r.json()
    assert r.status_code == 200 and v["events"] and set(v["kinds"]) == set(M.KINDS) and v["prefs"]["allowed"] is False
    assert {s["id"] for s in v["sources"]} == set(M.SOURCES) and "results" in v["week"] and v["note"]
    assert not PROVIDERS.search(json.dumps({k: v[k] for k in ("note", "kinds")}))
    assert c.get("/trade/events/badges", headers=headers("free-token")).status_code == 200
    r = c.put("/trade/events/prefs", headers=headers("free-token"), json={"remind": True, "kinds": ["rbi"], "days": 1})
    assert r.status_code == 402 and "Basic plan" in r.json()["detail"]["message"]
    r = c.put("/trade/events/prefs", headers=headers("free-token"), json={"remind": False, "money_calendar": True})
    assert r.status_code == 200 and r.json()["money_calendar"] is True        # the Money calendar is for everyone
    r = c.put("/trade/events/prefs", headers=headers("basic-token"), json={"remind": True, "kinds": ["rbi", "us", "nope", "rbi"], "days": 0})
    assert r.status_code == 200 and r.json()["remind"] is True and r.json()["kinds"] == ["rbi", "us"] and r.json()["days"] == 0
    assert c.get("/trade/events", headers=headers("basic-token")).json()["prefs"]["remind"] is True
    assert c.put("/trade/events/prefs", headers=headers("basic-token"), json={"remind": True, "kinds": [], "days": 1}).status_code == 400
    assert c.put("/trade/events/prefs", headers=headers("basic-token"), json={"remind": True, "kinds": ["rbi"], "days": 3}).status_code == 400
    for bad in ({"remind": "maybe"}, {"days": "x"}, {"kinds": "rbi"}, {"days": 99}, {"kinds": ["x"] * 50}):
        assert c.put("/trade/events/prefs", headers=headers("basic-token"), json=bad).status_code == 422


def test_admins_add_and_remove_events_and_refresh(w, monkeypatch):
    c = w["client"]
    body = {"date": "2027-02-01", "kind": "budget", "title": "Union Budget 2027-28", "detail": "Presented in Parliament.",
            "time": "11:00", "url": "https://www.indiabudget.gov.in/"}
    assert c.post("/admin/events/custom", headers=headers("pro-token"), json=body).status_code in (401, 403)
    r = c.post("/admin/events/custom", headers=headers("admin-token"), json=body)
    assert r.status_code == 200 and len(r.json()["custom"]) == 1
    cid = r.json()["custom"][0]["id"]
    v = c.get("/trade/events", headers=headers("free-token")).json()
    bud = [e for e in v["events"] if e.get("custom") == cid]
    assert bud and bud[0]["kind"] == "budget" and bud[0]["time"] == "11:00" and bud[0]["date"] == "2027-02-01"
    for bad, code in (({**body, "date": "2027-02-30"}, 400), ({**body, "date": "1999-01-01"}, 400), ({**body, "url": "http://x.example/"}, 400),
                      ({**body, "url": "javascript:alert(1)"}, 400), ({**body, "kind": "holiday"}, 422), ({**body, "title": ""}, 422),
                      ({**body, "time": "25:00"}, 422), ({"title": "x"}, 422)):
        assert c.post("/admin/events/custom", headers=headers("admin-token"), json=bad).status_code == code, bad
    assert c.delete("/admin/events/custom/nope", headers=headers("admin-token")).status_code == 404
    assert c.delete(f"/admin/events/custom/{cid}", headers=headers("admin-token")).json()["custom"] == []
    monkeypatch.setattr(M, "Web", lambda: FakeWeb())
    assert c.post("/admin/events/refresh", headers=headers("basic-token")).status_code in (401, 403)
    r = c.post("/admin/events/refresh", headers=headers("admin-token"))
    assert r.status_code == 200 and r.json()["started"] is True
    assert R._refreshing.acquire(timeout=20)                      # the background read finished
    R._refreshing.release()
    assert M.load_state().get("fed")


# ---------- reminders, the Money calendar and the job ----------
def test_reminders_go_once_to_plans_that_have_them(w, paid):
    M.refresh(FakeWeb(), TODAY)
    M.save_prefs("u-basic", {**M.prefs("u-basic"), "remind": True, "kinds": ["rbi"], "days": 2})
    M.save_prefs("u-free", {**M.prefs("u-free"), "remind": True, "kinds": ["rbi"], "days": 2})
    M.save_prefs("u-pro", {**M.prefs("u-pro"), "remind": True, "kinds": ["us"], "days": 2})   # no US event on 7 Oct
    got = []
    send = lambda p, subject, text: got.append((p["id"], subject, text)) or ["push"]  # noqa: E731
    assert M.send_reminders(TODAY, R.reminders_allowed, send) == 1
    assert [g[0] for g in got] == ["u-basic"] and "RBI policy decision (MPC)" in got[0][1] and "in 2 days" in got[0][2]
    assert "Facts, not advice" in got[0][2] and not ADVICE.search(got[0][2].replace("Facts, not advice", ""))
    assert M.send_reminders(TODAY, R.reminders_allowed, send) == 0          # never twice
    assert len(M.prefs("u-basic")["sent"]) == 1


def test_events_go_into_the_money_calendar_only_when_asked(w):
    c = w["client"]
    M.refresh(FakeWeb(), TODAY)
    q = "/money/calendar?start=2026-10-01&end=2026-10-31"
    v = c.get(q, headers=headers("free-token")).json()
    assert not any(e["cat"] == "market" for e in v["events"]) and "market" not in [x["id"] for x in v["cats"]] and v["market_on"] is False
    c.put("/trade/events/prefs", headers=headers("free-token"), json={"money_calendar": True, "kinds": ["rbi", "us"]})
    v = c.get(q, headers=headers("free-token")).json()
    mk = [e for e in v["events"] if e["cat"] == "market"]
    assert any(e["title"] == "RBI policy decision (MPC)" and e["date"] == "2026-10-07" for e in mk)
    assert not any("India CPI" in e["title"] for e in mk) and "market" in [x["id"] for x in v["cats"]]
    assert "market" not in v["reminders"]["cats"]                   # the market events' own reminders, not these
    feed = c.post("/money/calendar/feed", headers=headers("free-token"), json={}).json()
    from app import money_calendar
    ics = money_calendar.to_ics(money_calendar.events("u-free", date(2026, 10, 1), date(2026, 10, 31)), False)
    assert "SUMMARY:RBI policy decision (MPC)" in ics and "CATEGORIES:Market events" in ics and feed["path"].endswith(".ics")


def test_the_job_reads_twice_a_day_and_reminds_in_the_morning(w):
    web, reminded = FakeWeb(), []
    job = M.Job(lambda: web, lambda day: reminded.append(day) or 0)
    morning = datetime(2026, 10, 5, 7, 30, tzinfo=ZoneInfo("Asia/Kolkata"))
    job.tick(morning)
    assert db.get_setting("newsjob:mktevents-am") == "2026-10-05" and M.load_state().get("rbi") and reminded == [date(2026, 10, 5)]
    job.tick(morning.replace(hour=19))
    assert db.get_setting("newsjob:mktevents-pm") == "2026-10-05" and reminded == [date(2026, 10, 5)]   # evening: no reminders
    n = len(web.calls)
    job.tick(morning.replace(hour=20))
    assert len(web.calls) == n                                      # once per run


# ---------- the web client ----------
def test_the_web_client_turns_failures_into_source_errors():
    pdf = b"%PDF-1.4 not really"
    hits = []

    def handler(r: httpx.Request):
        hits.append((r.method, str(r.url), r.headers.get("user-agent"), r.content))
        if r.url.path == "/gone":
            return httpx.Response(404)
        if r.url.path == "/busy":
            return httpx.Response(503)
        if r.url.path == "/waf":
            return httpx.Response(200, text="<html><title>Unauthorised Access </title></html>", headers={"content-type": "text/html"})
        if r.url.path == "/page.pdf":
            return httpx.Response(200, content=b"<html>not a pdf</html>")
        if r.url.path == "/real.pdf":
            return httpx.Response(200, content=pdf)
        if "BS_PressReleaseDisplay" in r.url.path and r.method == "GET":
            return httpx.Response(200, text='<input type="hidden" name="__VIEWSTATE" id="__VIEWSTATE" value="abc" />'
                                            '<input type="hidden" name="hdnYear" id="hdnYear" />', headers={"content-type": "text/html"})
        return httpx.Response(200, text="ok", headers={"content-type": "text/html"})
    web = M.Web(transport=httpx.MockTransport(handler), pause=0)
    assert web.text("https://example.org/x") == "ok"
    assert web.text("https://example.org/ics", ua=M.BLS_UA) == "ok" and hits[-1][2] == M.BLS_UA
    with pytest.raises(SourceError) as e:
        web.text("https://example.org/gone")
    assert not e.value.busy
    for path in ("/busy", "/waf"):
        with pytest.raises(SourceError) as e:
            web.text("https://example.org" + path)
        assert e.value.busy
    with pytest.raises(ValueError):
        web.pdf_text("https://example.org/page.pdf")
    with pytest.raises(ValueError):
        web.pdf_text("https://example.org/real.pdf")               # a damaged PDF is a ValueError too, never a crash
    assert web.rbi_month(2026, 3, first=True) == "ok"
    method, _, _, body = hits[-1]
    assert method == "POST" and b"__VIEWSTATE=abc" in body and b"hdnYear=2026" in body and b"hdnMonth=3" in body
