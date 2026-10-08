"""Round 3, builder B: weekend events say so, plan interest ("Tell me when plans open"), options premiums round alike."""
from datetime import date

import pytest

from app import db, main  # noqa: F401  (main first: it loads the modules in the order they need)
from app import market_events as M


def ev(kind, day, **kw):
    return {"id": "x", "kind": kind, "date": day, "title": "T", "detail": "Detail.", **kw}


def test_an_event_on_a_weekend_says_so_and_a_weekday_one_is_left_alone():
    sun = M.mark_weekend(ev("rbi", "2026-10-11"))
    assert sun["weekend"] == "Sunday"
    assert sun["detail"] == "Detail. This day is a Sunday, so the exchanges are closed."
    sat = M.mark_weekend(ev("india", "2026-10-17"))
    assert sat["weekend"] == "Saturday"
    mon = M.mark_weekend(ev("rbi", "2026-10-12"))
    assert "weekend" not in mon and mon["detail"] == "Detail."
    # holidays and expiries are about the calendar itself
    assert "weekend" not in M.mark_weekend(ev("holiday", "2026-10-11"))
    assert "weekend" not in M.mark_weekend(ev("expiry", "2026-10-17"))
    # a special session the owner added (a Saturday Budget) is not marked closed
    assert "weekend" not in M.mark_weekend(ev("budget", "2026-10-17", custom="abc"))


def test_the_dated_list_marks_a_weekend_minutes_due_date():
    st = {"rbi": {"meetings": [{"start": date(2026, 9, 27).isoformat(), "end": date(2026, 9, 27).isoformat()}]}}
    out = M.rbi_events(st["rbi"], date(2026, 9, 20))
    due = next(e for e in out if e["title"].endswith("(due)"))
    assert due["date"] == "2026-10-11"                    # the 14th day after a Sunday decision
    assert M.mark_weekend(dict(due))["weekend"] == "Sunday"


@pytest.fixture
def w(monkeypatch):
    from tests import world
    built = world.build(monkeypatch)
    yield built
    built["close"]()


def test_tell_me_when_plans_open_is_per_person_once_and_counted_for_admin(w):
    from app import plan_interest
    c, H = w["client"], w["headers"]
    free, pro, admin = H("free-token"), H("pro-token"), H("admin-token")
    assert c.get("/me/plan-interest").status_code in (401, 403)                      # signed in only
    assert c.get("/me/plan-interest", headers=free).json() == {"registered": False, "at": None}
    first = c.put("/me/plan-interest", headers=free, json={"source": "lock"}).json()
    assert first["registered"] and first["at"]
    again = c.put("/me/plan-interest", headers=free, json={"source": "plans"}).json()
    assert again == first                                                              # asking twice changes nothing
    assert c.get("/me/plan-interest", headers=pro).json()["registered"] is False      # someone else's is their own
    assert c.put("/me/plan-interest", headers=free, json={"source": "nonsense"}).status_code == 422
    c.put("/me/plan-interest", headers=pro, json={})
    assert plan_interest.count() == 2
    ov = c.get("/admin/overview", headers=admin).json()
    assert ov["stats"]["plan_interest"] == 2
    assert c.get("/admin/overview", headers=free).status_code in (401, 403)
    assert c.delete("/me/plan-interest", headers=free).json() == {"registered": False, "at": None}
    assert plan_interest.count() == 1


def test_the_list_goes_with_the_persons_data(w):
    from app import plan_interest, user_data
    c, H = w["client"], w["headers"]
    c.put("/me/plan-interest", headers=H("free-token"), json={"source": "inline"})
    uid = "u-free"
    assert plan_interest.get(uid)["registered"]
    user_data._prefs(uid)
    assert not plan_interest.get(uid)["registered"]


def test_the_scan_alert_spells_out_stage_2_plus_supertrend():
    from app import scan
    text = scan.alert_text("IN", [{"symbol": "TCS"}])
    assert text.startswith("Stage 2 + Supertrend on your India watchlist: TCS is in Stage 2")
    assert "ST S2" not in text
