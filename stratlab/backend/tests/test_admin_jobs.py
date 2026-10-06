"""Admin -> Data and jobs: GET /admin/jobs lists every background job for admins only, one row each, with the routes that
run it now (each of which exists and is admin-only)."""
import re

import pytest

from app import main
from tests import world as W
from tests.fake_db import headers


@pytest.fixture
def w(monkeypatch):
    world = W.build(monkeypatch)
    yield world
    world["close"]()


def test_jobs_are_admin_only(w):
    c = w["client"]
    assert c.get("/admin/jobs").status_code in (401, 403)
    assert c.get("/admin/jobs", headers=headers("pro-token")).status_code in (401, 403)
    assert c.get("/admin/jobs", headers=headers("admin-token")).status_code == 200


def test_every_job_has_a_row_a_schedule_and_a_real_run_route(w):
    c = w["client"]
    jobs = c.get("/admin/jobs", headers=headers("admin-token")).json()["jobs"]
    ids = {j["id"] for j in jobs}
    assert {"breadth", "positioning", "etf", "ter", "holidays", "results", "corp", "events", "fo", "surveillance"} <= ids
    routes = {(m.upper(), p) for p, ms in main.app.openapi()["paths"].items() for m in ms}
    for j in jobs:
        assert j["name"] and j["state"] in ("ok", "warn", "bad") and isinstance(j["log"], list), j
        assert not (j["error"] or "").startswith("Couldn't read"), j
        for run in j["run"]:
            path = run["path"].split("?")[0]
            assert ("POST", path) in routes, run                       # the button points at a route that exists
            assert c.post(path, headers=headers("pro-token")).status_code in (401, 403)     # and only admins may press it


def test_job_rows_show_no_provider_names(w):
    text = str(w["client"].get("/admin/jobs", headers=headers("admin-token")).json())
    assert not re.search(r"yahoo|screener|finnhub|zerodha", text, re.I)
