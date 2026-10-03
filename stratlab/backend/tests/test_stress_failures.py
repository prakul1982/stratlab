"""Stress: every data source, the broker feed, the database and the AI broken in each way they break in real life
(down, timing out, refusing, rate limiting, sending a page instead of data, sending nothing), one at a time, while
every page and action of the app is used. Each must answer with a clear message or with what it could still show:
never a crash, never broken data, never a provider's name, never a number that isn't a number.

STRESS_FULL=1 runs every failure mode; by default each source is tried down and sending junk."""
import math
import os
import re
from urllib.parse import quote

import pytest
from kiteconnect import exceptions as kx

from tests import stress_requests, world
from tests.test_stress_fuzz import _json_safe, fill, seed

FULL = bool(os.environ.get("STRESS_FULL"))
MODES = ["down", "timeout", "500", "429", "403", "garbage", "empty"] if FULL else ["down", "garbage"]
SOURCES = ["crypto", "market data", "us company data", "research market data", "fundamentals", "news", "wikipedia",
           "exchange", "documents"]
KITE_FAULTS = {"network": kx.NetworkException("Gateway timed out"), "token": kx.TokenException("Incorrect `api_key` or `access_token`."),
               "data": kx.DataException("Unknown content type"), "other": RuntimeError("boom")}
NAMES = re.compile(r"zerodha|\bkite\b|yahoo|screener|finnhub", re.I)
PAGES = [("GET", "/me", {}), ("GET", "/markets", {}), ("GET", "/notebooks", {}), ("GET", "/live/overview", {}),
         ("GET", "/live/sessions", {}), ("GET", "/options/underlyings", {}), ("GET", "/instruments/{in_stock}", {}),
         ("GET", "/instruments/CRYPTO:BTC-USD", {}), ("GET", "/instruments/US:AAPL", {}),
         ("GET", "/research/company/IN/RELIANCE", {}), ("GET", "/research/company/US/AAPL", {}),
         ("GET", "/research/chart/IN/RELIANCE", {}), ("GET", "/research/chart/US/AAPL", {}),
         ("GET", "/research/deep/RELIANCE", {}), ("GET", "/research/deep/RELIANCE/deck", {}),
         ("GET", "/research/filings/RELIANCE", {}), ("GET", "/research/filings", {}), ("GET", "/research/investor", {}),
         ("GET", "/research/watchlist", {}), ("GET", "/research/scan/sets", {"region": "IN"}),
         ("GET", "/notebooks/{nid}", {}), ("GET", "/library", {}), ("GET", "/groups", {}), ("GET", "/plans", {})]


def walk_numbers(v, path="$"):
    """Paths in a JSON answer holding a number that isn't one (NaN or infinity sent as a string)."""
    bad = []
    if isinstance(v, dict):
        for k, x in v.items():
            bad += walk_numbers(x, f"{path}.{k}")
    elif isinstance(v, list):
        for i, x in enumerate(v[:200]):
            bad += walk_numbers(x, f"{path}[{i}]")
    elif isinstance(v, float) and not math.isfinite(v):
        bad.append(path)
    elif isinstance(v, str) and v in ("NaN", "Infinity", "-Infinity", "nan", "inf"):
        bad.append(path)
    return bad


def texts(v):
    """The words a person can read in an answer: string values, not keys, links or ids."""
    if isinstance(v, dict):
        return [t for k, x in v.items() if k not in ("url", "logo", "id", "source_id") for t in texts(x)]
    if isinstance(v, list):
        return [t for x in v[:200] for t in texts(x)]
    if isinstance(v, str) and not v.startswith(("http://", "https://", "data:")):
        return [v]
    return []


def requests_for(ctx):
    out = [(m, p, q, None) for m, p, q in PAGES]
    for (m, p), cases in stress_requests.real_requests(ctx).items():
        for q, b in cases[:1]:              # the fuzz test covers every variant; here one of each, against each fault
            out.append((m, p, q, b))
    return out


def run_all(w, ctx, label, problems):
    c = w["client"]
    for method, path, q, body in requests_for(ctx):
        url = path
        for k, v in ctx.items():
            url = url.replace("{" + k + "}", quote(str(v), safe=":"))
        hdr = world.headers("admin-token" if path.startswith("/admin") else "pro-token")
        r = c.request(method, url, params=q or None, headers=hdr,
                      json=_json_safe(fill(body, ctx)) if body is not None else None)
        where = f"[{label}] {method} {url[:70]}"
        if r.status_code >= 500 and r.status_code not in (502, 503):
            problems.append(f"{where} -> {r.status_code} {r.text[:160]}")
            continue
        ctype = r.headers.get("content-type", "")
        if ctype.startswith("application/json"):
            try:
                data = r.json()
            except ValueError:
                problems.append(f"{where} -> broken JSON")
                continue
            if r.status_code >= 400:
                d = data.get("detail") if isinstance(data, dict) else None
                if not (isinstance(d, dict) and d.get("message")):
                    problems.append(f"{where} -> {r.status_code} without a message: {r.text[:120]}")
            bad = walk_numbers(data)
            if bad:
                problems.append(f"{where} -> not-a-number at {bad[:3]}")
            if not path.startswith("/admin"):
                hit = next((m for t in texts(data) if (m := NAMES.search(t))), None)
                if hit:
                    problems.append(f"{where} -> names a provider ({hit.group(0)}): {r.text[:160]}")


@pytest.fixture
def w(monkeypatch):
    built = world.build(monkeypatch)
    yield built
    built["close"]()


@pytest.mark.parametrize("source", SOURCES)
def test_each_source_failing(w, source):
    ctx = seed(w)
    problems = []
    for mode in MODES:
        w["faults"][source].mode = mode
        run_all(w, ctx, f"{source} {mode}", problems)
        w["faults"][source].mode = None
        _reset(w)
    assert not problems, "\n".join(dict.fromkeys(problems))


@pytest.mark.parametrize("fault", list(KITE_FAULTS) if FULL else ["network", "token"])
def test_broker_feed_failing(w, fault):
    ctx = seed(w)
    w["kite"].kite.fail = KITE_FAULTS[fault]
    w["kite"]._cache.clear()
    problems = []
    run_all(w, ctx, f"broker {fault}", problems)
    w["kite"].kite.fail = None
    assert not problems, "\n".join(dict.fromkeys(problems))


def test_broker_offline_before_login(w):
    """The morning before the day's broker login: Indian data is offline everywhere."""
    ctx = seed(w)
    w["kite"].access_token = None
    problems = []
    run_all(w, ctx, "broker logged out", problems)
    assert not problems, "\n".join(dict.fromkeys(problems))


def test_database_down(w):
    ctx = seed(w)
    import httpx
    w["db"].fail = httpx.ConnectError("[Errno 111] Connection refused")
    from app import auth, db
    auth._cache.clear()
    db._profiles.clear()
    problems = []
    run_all(w, ctx, "database down", problems)
    w["db"].fail = None
    assert not problems, "\n".join(dict.fromkeys(problems))


@pytest.mark.parametrize("mode", ["garbage", "fail", "busy"])
def test_ai_failing(w, mode):
    ctx = seed(w)
    w["ai"].mode = mode
    problems = []
    run_all(w, ctx, f"ai {mode}", problems)
    assert not problems, "\n".join(dict.fromkeys(problems))


def _reset(w):
    from tests.test_stress_fuzz import _reset as r
    r(w)
