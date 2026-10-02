"""Problems the stress tests found, each pinned so it can't come back."""
import time

import httpx
import pytest

from app.intel.yahoo import Yahoo
from tests import world


@pytest.fixture
def w(monkeypatch):
    return world.build(monkeypatch)


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
            "indicators": {"quote": [{"open": [1.0] * n, "high": [1.0] * n, "low": [1.0] * n, "close": [1.0] * n, "volume": [1] * n}]}}]}})
    y = Yahoo(transport=httpx.MockTransport(handler))
    y.chart("AAPL", "1d", Yahoo.WINDOW)
    y.chart("AAPL", "1d", 420)
    y.chart("AAPL", "1d", 220)
    assert len(calls) == 1                                  # the backtest windows were cut from the lookup's download
    assert y.meta("AAPL")["prev_close"] == 198.0 and len(calls) == 2   # the day's change never uses a year-old close
