"""Problems the stress tests found, each pinned so it can't come back."""
import time

import httpx
import pytest

from app.intel.yahoo import Yahoo
from tests import world


@pytest.fixture
def w(monkeypatch):
    built = world.build(monkeypatch)
    yield built
    built["close"]()


def test_a_mistyped_indian_symbol_is_answered_at_once(w):
    c, h = w["client"], world.headers("pro-token")
    for sym in ["NOPE", "-1", "NULL", "1E309", "XYZ123"] * 3:           # well past the company source's per-minute allowance
        t = time.monotonic()
        r = c.get(f"/research/company/IN/{sym}", headers=h)
        assert time.monotonic() - t < 1.5 and r.status_code in (400, 404, 502), (sym, r.status_code, r.text)
    assert c.get("/research/company/IN/TATAMOTORS", headers=h).status_code in (200, 502)    # a known rename still resolves


def test_granting_a_plan_to_no_one_is_a_404(w):
    r = w["client"].post("/admin/users/not-a-user/plan", headers=world.headers("admin-token"), json={"plan": "pro", "days": 30})
    assert r.status_code == 404 and r.json()["detail"]["code"] == "no_user"


def test_webhook_errors_use_the_same_shape_as_everything_else(w):
    d = w["client"].post("/billing/webhook", content=b"{}").json()["detail"]
    assert d["code"] == "webhook_not_set" and d["message"]


def test_a_us_lookup_and_its_backtest_share_one_download():
    calls = []

    def handler(r):
        calls.append(r.url.params.get("period1"))
        n = 760
        t0 = 1700000000
        return httpx.Response(200, json={"chart": {"result": [{
            "meta": {"symbol": "AAPL", "currency": "USD", "regularMarketPrice": 200.0, "chartPreviousClose": 150.0 if len(calls) == 1 else 198.0,
                     "longName": "Apple", "exchangeTimezoneName": "America/New_York", "instrumentType": "EQUITY"},
            "timestamp": [t0 + i * 86400 for i in range(n)],
            "indicators": {"quote": [{"open": [1.0] * n, "high": [1.0] * n, "low": [1.0] * n, "volume": [1] * n,
                                        "close": [1.0] * (n - 2) + ([1.5, 2.0] if len(calls) == 1 else [199.0, 200.0])}]}}]}})
    y = Yahoo(transport=httpx.MockTransport(handler))
    y.chart("AAPL", "1d", Yahoo.WINDOW)
    y.chart("AAPL", "1d", 420)
    y.chart("AAPL", "1d", 220)
    assert len(calls) == 1                                  # the backtest windows were cut from the lookup's download
    assert y.meta("AAPL")["prev_close"] == 199.0 and len(calls) == 2   # the day's change never uses a year-old close


def test_a_source_that_is_down_is_skipped_for_a_minute_not_waited_on():
    from app.intel.net import Source, SourceError
    calls = []

    def down(r):
        calls.append(1)
        raise httpx.ConnectError("refused", request=r)
    s = Source("https://example.com", per_minute=6, burst=1, transport=httpx.MockTransport(down))
    s.name = "X"
    t = time.monotonic()
    for i in range(20):
        with pytest.raises(SourceError) as e:
            s.fetch(f"/a{i}")
        assert e.value.busy
    assert len(calls) <= 3 and time.monotonic() - t < 1     # three tries, then instant answers instead of rate-limit waits


def test_a_block_page_is_not_remembered_as_a_missing_company():
    from app.intel.net import SourceError
    from app.intel.screener import Screener
    from tests.fake_intel import SCREENER_HTML
    state = {"blocked": True}

    def handler(r):
        if state["blocked"]:
            return httpx.Response(200, text="<html><body>Verify you are human</body></html>")
        return httpx.Response(200, text=SCREENER_HTML)
    scr = Screener(transport=httpx.MockTransport(handler))
    with pytest.raises(SourceError) as e:
        scr.company("RELIANCE")
    assert e.value.busy
    state["blocked"] = False
    scr._down_until = 0                                     # the minute has passed
    assert scr.company("RELIANCE")["name"]


def test_database_or_sign_in_down_is_said_plainly(w):
    c = w["client"]
    w["db"].fail = httpx.ConnectError("[Errno 111] Connection refused")
    from app import auth, db
    auth._cache.clear()
    db._profiles.clear()
    r = c.get("/me", headers=world.headers("pro-token"))
    assert r.status_code == 503 and r.json()["detail"]["code"] == "auth_unavailable"      # not "your session expired"
    w["db"].fail = None
    c.get("/me", headers=world.headers("pro-token"))                                       # signed in, profile cached
    db._profiles.clear()
    w["db"].fail = httpx.ConnectError("[Errno 111] Connection refused")
    w["db"].auth.get_user = lambda token: type("R", (), {"user": type("U", (), {"id": "u-pro", "email": "pro@example.com",
                                                                                 "email_confirmed_at": "x"})()})()
    r = c.get("/me", headers=world.headers("pro-token"))
    assert r.status_code == 503 and r.json()["detail"]["code"] == "database_unavailable" and "Nothing you saved is lost" in r.text


def test_junk_from_the_crypto_source_is_an_error_not_a_crash(w):
    from tests.test_stress_fuzz import seed
    ctx = seed(w)
    w["faults"]["crypto"].mode = "garbage"
    r = w["client"].post(f"/notebooks/{ctx['nid']}/experiments", headers=world.headers("pro-token"), json={"days": 5})
    assert r.status_code in (400, 502, 503) and "Try again" in r.json()["detail"]["message"]


def test_a_broker_failure_while_starting_paper_trading_starts_nothing(w):
    from tests import stress_requests
    inst = w["kite"].by_symbol("RELIANCE")["id"]
    w["kite"].kite.fail = RuntimeError("unexpected reply")
    r = w["client"].post("/live/sessions", headers=world.headers("pro-token"), json={"strategy": stress_requests.EMA, "instrument": inst})
    assert r.status_code == 503 and r.json()["detail"]["code"] == "prices_unavailable"
    assert not w["manager"].sessions and all(x["status"] == "stopped" for x in w["db"].tables.get("live_sessions", []))
