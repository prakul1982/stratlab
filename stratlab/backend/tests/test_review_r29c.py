"""Round 29C (live re-check): account ids in provider errors, the debt label, the platform check's failure detail, the outlook's
passed periods."""
from datetime import date, datetime, timedelta, timezone

from app import deepdive, main, weekly
from app.connect.redact import redact_ids


def test_redact_ids_hides_a_quoted_account_and_model_uuids():
    a = redact_ids("Function 'abc': Not found for account 'BlwSxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'")
    assert "BlwS" not in a and "Function 'abc': Not found for account" in a
    b = redact_ids("400: No such model 06455e78-aaaa-bbbb-cccc-1234567890ab or task 53595e8d-aaaa-bbbb-cccc-1234567890ab")
    assert "06455e78" not in b and "53595e8d" not in b and b.startswith("400: No such model")
    assert "AbCd1234EfGh5678IjKl9012MnOp3456" not in redact_ids("token AbCd1234EfGh5678IjKl9012MnOp3456 refused")
    assert redact_ids("Rate limit reached for the free tier") == "Rate limit reached for the free tier"
    assert redact_ids("the account 'savings' was refused") == "the account 'savings' was refused"


def test_a_provider_error_names_its_configured_model_and_hides_the_account():
    from app import ai_providers as P
    st = type("S", (), {"aliases": {"06455e78-aaaa-bbbb-cccc-1234567890ab": "@cf/meta/llama-3"}})()
    out = P.named(st, "No such model 06455e78-aaaa-bbbb-cccc-1234567890ab for account 'BlwSxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'")
    assert "@cf/meta/llama-3" in out and "BlwS" not in out and "06455e78" not in out


def test_the_deep_dive_checklist_says_total_debt_to_equity():
    from app import checklist
    src = open(checklist.__file__).read()
    assert '"Total debt / equity"' in src and '"Debt to equity"' not in src


def test_the_platform_history_keeps_each_failed_checks_detail(monkeypatch):
    from app import platform_check as pc
    saved = {}
    monkeypatch.setattr(main.db, "get_setting", lambda k: saved.get(k))
    monkeypatch.setattr(main.db, "set_setting", lambda k, v: saved.__setitem__(k, v))
    long = "scan read 3 of 50 stocks " + "x" * 400
    monkeypatch.setattr(main, "platform_checks", lambda: [("Scans", "Scans", lambda: pc._result("Scans", "Scans", "fail", long)),
                                                         ("Fine", "Server", lambda: pc._result("Fine", "Server", "pass", "ok"))])
    main.run_platform_check(retry_after=0)
    import json
    h = json.loads(saved[main.PLATFORM_HISTORY])[-1]
    assert h["failed"] == ["Scans"] and h["failed_detail"][0]["name"] == "Scans"
    assert h["failed_detail"][0]["detail"].startswith("scan read 3 of 50") and len(h["failed_detail"][0]["detail"]) == 300


def test_the_weekly_summary_lists_the_failure_detail_in_ist():
    IST = timezone(timedelta(hours=5, minutes=30))
    now = datetime(2026, 10, 12, 9, 0, tzinfo=IST)
    facts = {"stats": {"new": 0, "users": 1, "paid": {}, "experiments": 0, "ai": 0},
             "checks": [{"at": "2026-10-10T11:28:00+00:00", "fail": 1, "failed": ["Scans"],
                         "failed_detail": [{"name": "Scans", "detail": "read 3 of 50 stocks"}]}],
             "audits": {}, "errors": 0, "admin_url": None}
    _, text = weekly.summary(now, facts)
    assert "Scans (Sat 10 Oct, 16:58 IST)" in text and "Scans (Sat 10 Oct, 16:58 IST): read 3 of 50 stocks" in text


def test_the_admin_panel_shows_failed_run_detail():
    src = open(__file__.replace("backend/tests/test_review_r29c.py", "frontend/src/pages/admin/PlatformPanel.tsx")).read()
    assert "failed_detail" in src and "tz: IST" in src


def test_outlook_leaves_out_statements_whose_period_has_passed():
    today = date(2026, 10, 15)
    labels = {"S1": {"title": "Call", "at": "2023-10-12", "url": "u", "kind": "call"}, "S2": {"title": "Deck", "at": "2026-08-12", "url": "u", "kind": "deck"}}
    out = [{"statement": "Expects to commission the plant in October", "quote": "q", "source": "S1"},
           {"statement": "Will reach 20% growth in FY24", "quote": "q", "source": "S1"},
           {"statement": "Targets 15% margin by 2025", "quote": "q", "source": "S1"},
           {"statement": "Expects to commission the unit in December", "quote": "q", "source": "S2"},
           {"statement": "Will reach 20% growth in FY28", "quote": "q", "source": "S2"},
           {"statement": "Expects a launch in March", "quote": "q", "source": None}]
    got = [o["statement"] for o in deepdive.clean_plans({"outlook": out}, labels, today=today)["outlook"]]
    assert got == ["Expects to commission the unit in December", "Will reach 20% growth in FY28",
                   "Expects a launch in March"]       # a month with no year and no date said on: kept
    assert deepdive.period_passed("in October", date(2023, 10, 12), today) and not deepdive.period_passed("in October", None, today)
