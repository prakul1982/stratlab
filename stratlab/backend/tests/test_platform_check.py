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
