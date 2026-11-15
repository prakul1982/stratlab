"""Release 57, lane e57: a red herring prospectus filed a few days ago, no exchange list naming the issue yet, is waiting for the
exchange's dates, not a failure (owner, 15 Nov: Crystal Crop Protection's RHP of 12 Nov made the IPO job "bad" in Admin, re-run three
times and mailed). Within the window (IPO_RHP_WAIT_DAYS, default 10) it is shown in Admin and the job stays ok, with no re-run and no
mail; still unlisted after the window it is a Check, which the self-healing follows up as before. Each test fails before the change."""
from datetime import timedelta

from app import main  # noqa: F401, I001  (main first: it loads the modules in the order they need)
from app import admin_jobs, ipo as I
from tests.fake_db import headers
from tests.test_ipo import NOW, TODAY, w  # noqa: F401  (the IPO tests' fake world and its clock)

EMPTY = {"upcoming": [], "current": [], "past": []}


def crystal(day: str) -> list[dict]:
    return [{"kind": "rhp", "date": day, "company": "Crystal Crop Protection Limited"}]


# ---------- the line: within the window it waits; after it, a Check ----------
def test_a_red_herring_prospectus_filed_three_days_ago_is_waiting_not_a_check():
    filed = (TODAY - timedelta(days=3)).isoformat()                       # the live case: filed 12 Nov, read 15 Nov
    lines = I.india_gaps([], EMPTY, [], [], crystal(filed), TODAY, NOW)
    assert len(lines) == 1 and I.waiting(lines[0]) and not I.awaits(lines[0])
    assert lines[0].startswith(f"Crystal Crop Protection Limited: red herring prospectus filed with SEBI on {filed} (3 days ago); "
                               "waiting for the exchange's dates")


def test_still_unlisted_after_the_window_it_is_a_check_again():
    filed = (TODAY - timedelta(days=I.RHP_WAIT_DAYS_DEFAULT)).isoformat()
    lines = I.india_gaps([], EMPTY, [], [], crystal(filed), TODAY, NOW)
    assert lines == [f"Crystal Crop Protection Limited filed a red herring prospectus with SEBI on {filed}; no exchange list names the issue "
                     "and our row has no dates."]
    assert I.awaits(lines[0]) and not I.waiting(lines[0])


def test_the_window_is_configurable(monkeypatch):
    filed = (TODAY - timedelta(days=12)).isoformat()
    assert I.awaits(I.india_gaps([], EMPTY, [], [], crystal(filed), TODAY, NOW)[0])
    monkeypatch.setenv("IPO_RHP_WAIT_DAYS", "14")
    assert I.rhp_wait_days() == 14 and I.waiting(I.india_gaps([], EMPTY, [], [], crystal(filed), TODAY, NOW)[0])
    monkeypatch.setenv("IPO_RHP_WAIT_DAYS", "not a number")
    assert I.rhp_wait_days() == I.RHP_WAIT_DAYS_DEFAULT


def test_an_issue_with_its_dates_or_a_prospectus_from_the_future_gives_no_line():
    filed = (TODAY - timedelta(days=2)).isoformat()
    row = {"nkey": "crystalcropprotection", "open": "2026-10-28"}
    assert I.india_gaps([row], EMPTY, [], [], crystal(filed), TODAY, NOW) == []
    assert I.india_gaps([], EMPTY, [], [], crystal((TODAY + timedelta(days=1)).isoformat()), TODAY, NOW) == []


# ---------- the job, Admin and the self-healing: both sides of the window ----------
def _ipo_row(w):
    return next(j for j in w["client"].get("/admin/jobs", headers=headers("admin-token")).json()["jobs"] if j["id"] == "ipo")


def test_within_the_window_the_job_is_ok_shown_in_admin_and_never_re_run_or_mailed(w, monkeypatch):  # noqa: F811
    # Jio Platforms' red herring prospectus of 15 Oct, no page for it on the exchange: 10 days old at NOW, inside a window of 14
    monkeypatch.setenv("IPO_RHP_WAIT_DAYS", "14")
    w["feed"].nse.hidden = {"JPL"}
    job = I.Job(sleep=lambda s: None)
    monkeypatch.setattr(I, "job", job)                                  # Admin reads the module's job
    job.read("IN", NOW)
    assert job.status["last_error"] is None and job.status["check"] is None
    assert not any("Jio" in p for p in job.status["problems"])
    assert any(x.startswith("Waiting (India): Jio Platforms Limited: red herring prospectus filed with SEBI on 2026-10-15 (10 days ago); "
                            "waiting for the exchange's dates") for x in job.status["waiting"])
    row = _ipo_row(w)
    assert row["state"] == "ok" and not row["error"]
    assert any("Jio Platforms Limited" in x and "waiting for the exchange's dates" in x for x in row["log"])
    assert "waiting for the exchange's dates (not a failure)" in row["note"]
    # the self-healing sees no problem: nothing to re-run, nothing to escalate by mail
    assert not [c for c in admin_jobs.job_checks() if c.id == "job:ipo" and c.problem]


def test_after_the_window_the_same_filing_is_a_check_the_self_healing_follows_up(w, monkeypatch):  # noqa: F811
    monkeypatch.setenv("IPO_RHP_WAIT_DAYS", "14")
    w["feed"].nse.hidden = {"JPL"}
    job = I.Job(sleep=lambda s: None)
    monkeypatch.setattr(I, "job", job)
    job.read("IN", NOW + timedelta(days=5))                             # 30 Oct: 15 days after its filing of 15 Oct
    assert not job.status["waiting"] or not any("Jio" in x for x in job.status["waiting"])
    assert any(p.startswith("To check (India): Jio Platforms Limited filed a red herring prospectus") for p in job.status["problems"])
    assert "no exchange listing yet" in job.status["check"]
    row = _ipo_row(w)
    assert row["state"] == "warn" and "no exchange listing yet" in row["error"]
    assert [c for c in admin_jobs.job_checks() if c.id == "job:ipo" and c.problem]
