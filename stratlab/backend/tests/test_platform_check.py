"""Admin → Check every feature: on a healthy world every check passes; with a source down, that feature's checks
fail with a reason and the rest still run."""
import pytest

from tests import world


@pytest.fixture
def w(monkeypatch):
    built = world.build(monkeypatch)
    yield built
    built["close"]()


def run(w):
    r = w["client"].post("/admin/platform/check", headers=world.headers("admin-token"))
    assert r.status_code == 200, r.text
    return {c["name"]: c for c in r.json()["checks"]}, r.json()["counts"]


def test_everything_passes_when_everything_works(w):
    checks, counts = run(w)
    bad = {k: (c["state"], c["detail"]) for k, c in checks.items() if c["state"] == "fail"}
    assert not bad, bad
    for name in ("Prices: IN", "Prices: CRYPTO", "Prices: US", "Backtest: IN", "Backtest: MCX", "Scan: NIFTY 50 stocks",
                 "Sector rotation: IN", "Option chain: NIFTY", "Exchange filings", "Company page: RELIANCE", "Database"):
        assert name in checks
    assert checks["Backtest: CRYPTO"]["state"] == "pass" and "verdict" in checks["Backtest: CRYPTO"]["detail"]
    assert counts["pass"] >= 20


def test_a_broken_source_fails_its_checks_and_nothing_else(w):
    w["faults"]["crypto"].mode = "down"
    w["faults"]["exchange"].mode = "garbage"
    checks, _ = run(w)
    assert checks["Prices: CRYPTO"]["state"] == "fail" and checks["Backtest: CRYPTO"]["state"] == "fail"
    assert checks["Exchange filings"]["state"] == "fail" and checks["Exchange filings"]["detail"]
    assert checks["Prices: IN"]["state"] == "pass" and checks["Database"]["state"] == "pass"
    assert "coinbase" in checks["Prices: CRYPTO"]["detail"].lower() or checks["Prices: CRYPTO"]["detail"]


def test_stale_prices_are_caught(w, monkeypatch):
    from app import platform_check
    from datetime import date
    monkeypatch.setattr(platform_check, "last_session", lambda m, today: date(2099, 1, 1))
    checks, _ = run(w)
    assert checks["Prices: IN"]["state"] == "fail" and "2099-01-01 was a trading day" in checks["Prices: IN"]["detail"]


def test_only_the_admin_can_run_it(w):
    assert w["client"].post("/admin/platform/check", headers=world.headers("pro-token")).status_code == 403


def test_daily_check_retries_and_only_tells_admins_about_what_still_fails(monkeypatch):
    from app import main, platform_check as pc
    from tests import world as W
    w = W.build(monkeypatch)
    try:
        tries = {"flaky": 0}

        def flaky():
            tries["flaky"] += 1
            return pc._result("Flaky source", "Research", "fail" if tries["flaky"] == 1 else "pass", "busy once")
        monkeypatch.setattr(main, "platform_checks", lambda: [
            ("Flaky source", "Research", flaky),
            ("Broken source", "Research", lambda: pc._result("Broken source", "Research", "fail", "down")),
            ("Fine", "Server", lambda: pc._result("Fine", "Server", "pass", "ok"))])
        told = []
        monkeypatch.setattr(main, "tell_admins", lambda subject, text: told.append((subject, text)) or 1)
        out = main.daily_platform_check(retry_after=0.01)
        assert out["counts"] == {"pass": 2, "warn": 0, "fail": 1} and tries["flaky"] == 2
        assert told and "1 check failing" in told[0][0] and "Broken source" in told[0][1] and "Flaky" not in told[0][1]
        c = w["client"]
        last = c.get("/admin/platform/last", headers=W.headers("admin-token")).json()
        assert last["last"]["auto"] and last["history"][-1]["failed"] == ["Broken source"]
        assert c.get("/admin/platform/last", headers=W.headers("pro-token")).status_code == 403
        told.clear()
        monkeypatch.setattr(main, "platform_checks", lambda: [("Fine", "Server", lambda: pc._result("Fine", "Server", "pass", "ok"))])
        main.daily_platform_check(retry_after=0.01)
        assert told == []                                                    # all well: nobody is bothered
    finally:
        w["close"]()
