"""Round 94 (24 Oct 2026): Admin's "Company pages' prices" row keeps its last run across a restart, like the other jobs,
instead of "Not run yet" on Check until the next market's close."""
from app import admin_jobs, db, job_status, main


def test_the_page_price_job_keeps_its_last_run_across_a_restart(monkeypatch):
    store: dict = {}
    monkeypatch.setattr(db, "set_setting", lambda k, v: store.__setitem__(k, v))
    monkeypatch.setattr(db, "get_setting", lambda k: store.get(k))
    monkeypatch.setattr(job_status, "_written", {})
    ran = {"last_run": "2026-10-23T21:05:00+00:00", "IN": {"refreshed": 900, "left": 0, "failed": 3, "errors": 0},
           "US": {"refreshed": 2400, "left": 0, "failed": 0, "errors": 0}}
    job_status.kept("page-prices", dict(ran))                 # the job ran before the deploy
    monkeypatch.setattr(main, "price_refresh_status", {"last_run": None, "IN": None, "US": None})   # a fresh server
    st = job_status.kept("page-prices", dict(main.price_refresh_status))
    assert st["last_run"] == ran["last_run"] and st.get("before_restart") is True
    row = next(r for r in admin_jobs.rows() if r.get("id") == "page-prices")
    assert row["state"] != "check" and row.get("last_run") == ran["last_run"], row
