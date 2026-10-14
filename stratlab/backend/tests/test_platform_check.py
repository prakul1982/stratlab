"""Admin → Check every feature: on a healthy world every check passes; with a source down, that feature's checks
fail with a reason and the rest still run."""
import pytest

from tests import world


@pytest.fixture
def w(monkeypatch):
    from pathlib import Path
    from app import money_mf_ter as ter
    built = world.build(monkeypatch)
    # the TER disclosure, from the fund costs fixture (made-up schemes), read here rather than in a thread
    html = (Path(__file__).parent / "fixtures" / "mf" / "ter_disclosure.html").read_text()
    monkeypatch.setattr(ter, "fetch_month", lambda m, y: html)
    for k, v in (("MIN_ROWS", 1), ("PAUSE", 0), ("BACKGROUND", False), ("CHECK_SCHEMES", 3)):
        monkeypatch.setattr(ter, k, v)
    ter.forget()
    yield built
    built["close"]()
    ter.forget()


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
    assert checks["Prices: IN"]["state"] == "fail" and "1 Jan was a trading day" in checks["Prices: IN"]["detail"]


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


def test_prices_are_judged_by_the_markets_own_date(monkeypatch):
    """At 03:30 in India New York is still in the day before, whose candle isn't finished: not a stale feed."""
    from datetime import date, datetime, timezone

    from app import platform_check as pc
    late = datetime(2026, 10, 14, 22, 0, tzinfo=timezone.utc)           # Wednesday 18:00 New York, Thursday 03:30 IST

    class Fixed(datetime):
        @classmethod
        def now(cls, tz=None):
            return late.astimezone(tz) if tz else late.replace(tzinfo=None)
    monkeypatch.setattr(pc, "datetime", Fixed)
    assert pc.market_today("US") == date(2026, 10, 14) and pc.market_today("IN") == date(2026, 10, 15)

    class Prov:
        def ready(self):
            return True

        def defaults(self):
            return [{"symbol": "SPY"}]

        def history(self, inst, tf, days):
            return [{"t": "2026-10-13T00:00:00", "o": 1, "h": 2, "l": 0.5, "c": 1.5}]

    class Reg:
        def provider(self, market):
            return Prov()
    assert pc.check_market(Reg(), "US")["state"] == "pass"
    assert pc.check_market(Reg(), "US", date(2026, 10, 15))["state"] == "fail"       # judged by India's date, as before


def test_a_scan_has_the_time_a_cold_read_of_its_stocks_needs(monkeypatch):
    """The evening run reads 50 stocks' candles from the rate-limited sources (R14): a scan that takes longer than any
    other check's limit still passes, while a slow check of another area still fails at the usual one."""
    import time
    from app import platform_check as pc
    monkeypatch.setattr(pc, "TIMEOUT", 0.2)
    monkeypatch.setattr(pc, "TIMEOUTS", {"Scans": 2})
    slow = lambda: (time.sleep(0.5), pc._result("slow", "a", "pass", "ok"))[1]
    out = pc.run_all([("Prices: slow", "Prices", slow), ("Scan: slow", "Scans", slow)])["checks"]
    assert [c["state"] for c in out] == ["fail", "pass"] and out[0]["name"] == "Prices: slow"
    assert "Took longer than 0.2 seconds" in out[0]["detail"]


def test_the_scan_limit_covers_the_broker_rate_limit_twice_over():
    from app import platform_check as pc, scan
    assert pc.TIMEOUTS["Scans"] >= scan.MAX * 0.36 * 2 and pc.TIMEOUTS["Scans"] > pc.TIMEOUT


def test_a_check_keeps_the_name_it_was_run_under():
    """A scan's result was named "Scan: NIFTY 50 stocks" while it ran as "Scan: NIFTY 50": a scan that failed on its
    coverage was never found again for the retry, and the history listed two names for one check."""
    from app import platform_check as pc
    out = pc.run_all([("Scan: NIFTY 50 stocks", "Scans", lambda: pc._result("Scan: other", "Scans", "fail", "x"))])["checks"]
    assert out[0]["name"] == "Scan: NIFTY 50 stocks"


def test_the_limit_counts_from_when_a_check_starts(monkeypatch):
    """Six slow checks of another area hold every worker past their own limit: the scan queued behind them is timed
    from its start, not failed while it hasn't begun."""
    import threading
    from app import platform_check as pc
    monkeypatch.setattr(pc, "TIMEOUT", 0.05)
    monkeypatch.setattr(pc, "TIMEOUTS", {"Scans": 1})
    gate = threading.Event()
    held = lambda: (gate.wait(10), pc._result("held", "a", "pass", "ok"))[1]
    order = [(f"Prices: {k}", "Prices", held) for k in range(6)]
    scan_ran = []
    quick = lambda: (scan_ran.append(1), pc._result("q", "Scans", "pass", "ok"))[1]
    timer = threading.Timer(2.5, gate.set)     # the slow checks finish well after the scan's turn comes
    timer.start()
    out = pc.run_all(order + [("Scan: q", "Scans", quick)])["checks"]
    timer.cancel()
    assert [c["state"] for c in out[:6]] == ["fail"] * 6 and "timed out" in out[0]["detail"]
    assert out[6]["state"] == "pass" and scan_ran


def test_a_check_error_says_it_was_an_error():
    from app import platform_check as pc

    def boom():
        raise RuntimeError("source said no")
    out = pc.run_all([("Prices: X", "Prices", boom)])["checks"][0]
    assert out["state"] == "fail" and out["detail"].startswith("Error (RuntimeError): source said no")


class _Reg:
    def __init__(self, ready=True):
        self.ok = ready

    def provider(self, market):
        reg = self

        class P:
            def ready(self):
                return reg.ok

            def instrument(self, key):
                return {"symbol": key}
        return P()


def _scan_out(monkeypatch, out):
    from app import scan
    monkeypatch.setattr(scan, "run", lambda reg, market, members, budget=None: out)


def test_a_slow_scan_says_how_far_it_got(monkeypatch):
    from app import platform_check as pc
    _scan_out(monkeypatch, {"rows": [{}] * 30, "missing": [], "problems": [], "late": [f"S{k}" for k in range(20)]})
    r = pc.check_scan(_Reg(), "IN", "nifty50")
    assert r["state"] == "fail" and r["name"] == "Scan: NIFTY 50 stocks"
    assert r["detail"].startswith("30 of 50 stocks scanned") and "timed out on 20 still being read after 120 s" in r["detail"]


def test_a_refused_or_empty_scan_says_so(monkeypatch):
    from app import platform_check as pc
    _scan_out(monkeypatch, {"rows": [], "missing": [], "late": [],
                            "problems": ["AAPL: Yahoo Finance is busy (our rate limit). Try again in a minute."] * 20})
    r = pc.check_scan(_Reg(), "US", "us_mega")
    assert r["state"] == "fail" and r["detail"].startswith("Empty: no stock scanned")
    assert "20 refused by the price source (rate limit or outage)" in r["detail"]
    _scan_out(monkeypatch, {"rows": [], "missing": [], "problems": [], "late": []})
    assert pc.check_scan(_Reg(), "US", "us_mega")["detail"].startswith("Empty: the scan returned no rows")
    assert pc.check_scan(_Reg(ready=False), "IN", "nifty50")["state"] == "warn"


def test_a_scan_with_a_budget_leaves_out_what_it_could_not_read(monkeypatch):
    """scan.run stops waiting at its budget: the stocks still being read are listed as late, the rest are scanned."""
    import threading
    from app import scan
    stuck = threading.Event()
    monkeypatch.setattr(scan.universes, "resolve", lambda reg, market, members: ([f"IN:{m['symbol']}" for m in members], []))

    def bars(reg, iid):
        if iid == "IN:SLOW":
            stuck.wait(10)
        return [{"t": "2026-01-01", "o": 1, "h": 1, "l": 1, "c": 1}]
    monkeypatch.setattr(scan, "_bars", bars)
    monkeypatch.setattr(scan, "analyse", lambda b: {"signal": None, "chg": 0})
    try:
        out = scan.run(_Reg(), "IN", [{"symbol": "A"}, {"symbol": "SLOW"}, {"symbol": "B"}], budget=0.3)
    finally:
        stuck.set()
    assert sorted(r["symbol"] for r in out["rows"]) == ["A", "B"] and out["late"] == ["SLOW"]
    assert "late" not in scan.run(_Reg(), "IN", [{"symbol": "A"}])


def test_bad_candles_are_named_with_their_prices():
    from datetime import date
    from app import platform_check as pc

    class Prov:
        def ready(self):
            return True

        def defaults(self):
            return [{"symbol": "ISF.L", "token": "ISF.L"}]

        def history(self, inst, tf, days):
            good = [{"t": f"2026-10-{d:02d}T00:00:00+01:00", "o": 8.0, "h": 8.2, "l": 7.9, "c": 8.1} for d in (12, 13)]
            return good + [{"t": "2026-10-14T00:00:00+01:00", "o": 8.1, "h": 8.15, "l": 8.0, "c": 8.3}]

    class Reg:
        def provider(self, m):
            return Prov()
    r = pc.check_market(Reg(), "UK", date(2026, 10, 14))
    assert r["state"] == "fail"
    assert "14 Oct (o 8.10 h 8.15 l 8.00 c 8.30), today's candle while the session is still trading" in r["detail"]
