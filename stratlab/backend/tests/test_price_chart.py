"""The price chart: candle windows for timeframes and ranges, older pages when the chart scrolls back, drawings saved
per user and symbol, and the fixture the frontend's indicator port is checked against (it must match this engine)."""
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from app import chart_data as CD
from app.engine import indicators as I
from tests import world

FIXTURE = Path(__file__).resolve().parents[2] / "frontend" / "unit" / "fixtures" / "indicators.json"
PRO = world.headers("pro-token")
FREE = world.headers("free-token")


# ---------- the indicator fixture ----------
def fixture_bars() -> tuple[list[dict], list[dict]]:
    """Daily candles (320) and three days of 5-minute candles, wavy and deterministic, with a few zero volumes."""
    daily, intraday = [], []
    start = datetime(2024, 1, 1, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    for i in range(320):
        base = 100 + 0.08 * i + 9 * math.sin(i / 11) + 3 * math.sin(i / 3.3)
        o = base + 1.2 * math.sin(i * 1.7)
        c = base + 1.2 * math.cos(i * 1.3)
        h, l = max(o, c) + 0.6 + 0.4 * abs(math.sin(i)), min(o, c) - 0.6 - 0.4 * abs(math.cos(i))
        v = 0.0 if i % 37 == 5 else 1000 + 300 * math.sin(i / 5) ** 2
        daily.append({"t": (start + timedelta(days=i)).isoformat(), "o": round(o, 4), "h": round(h, 4), "l": round(l, 4),
                      "c": round(c, 4), "v": round(v, 2)})
    for d in range(3):
        day = start + timedelta(days=400 + d, hours=9, minutes=15)
        for k in range(75):
            j = d * 75 + k
            base = 200 + 4 * math.sin(j / 13) + 0.5 * math.sin(j)
            o, c = base, base + 0.7 * math.sin(j / 2.1)
            intraday.append({"t": (day + timedelta(minutes=5 * k)).isoformat(), "o": round(o, 4), "h": round(max(o, c) + 0.3, 4),
                             "l": round(min(o, c) - 0.3, 4), "c": round(c, 4), "v": float(500 + 40 * (k % 9))})
    return daily, intraday


CASES = [("sma", 20, None), ("ema", 20, None), ("rsi", 14, None), ("macd", 12, 26), ("macd_signal", 12, 26), ("macd_hist", 12, 26),
         ("bb_upper", 20, 2), ("bb_mid", 20, 2), ("bb_lower", 20, 2), ("vwap", 20, None), ("supertrend", 10, 3), ("stage", 150, 20),
         ("sma", 50, None), ("ema", 9, None), ("rsi", 7, None), ("bb_upper", 10, 1.5), ("supertrend", 7, 2)]


def _frame(bars: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(bars)
    df["t"] = pd.to_datetime(df["t"])
    return df


def _vals(s: pd.Series) -> list:
    return [None if not math.isfinite(float(x)) else round(float(x), 8) for x in s.to_numpy(dtype=float)]


def build_fixture() -> dict:
    daily, intraday = fixture_bars()
    df, idf = _frame(daily), _frame(intraday)
    out = {"daily": daily, "intraday": intraday, "cases": []}
    for t, p, m in CASES:
        ref = SimpleNamespace(t=t, p=p, m=m)
        out["cases"].append({"t": t, "p": p, "m": m, "intraday": False, "values": _vals(I.compute(ref, df, False))})
    for t, p, m in (("vwap", 20, None), ("ema", 20, None), ("rsi", 14, None)):
        ref = SimpleNamespace(t=t, p=p, m=m)
        out["cases"].append({"t": t, "p": p, "m": m, "intraday": True, "values": _vals(I.compute(ref, idf, True))})
    return out


def test_frontend_indicator_fixture_matches_the_engine():
    """The frontend's indicators are a port of app/engine/indicators.py, tested against this fixture. If the engine
    changes, regenerate it: python -m tests.test_price_chart (then the frontend's unit tests show what to port)."""
    assert FIXTURE.exists(), "run python -m tests.test_price_chart to write the fixture"
    saved = json.loads(FIXTURE.read_text())
    fresh = build_fixture()
    assert saved["daily"] == fresh["daily"] and saved["intraday"] == fresh["intraday"]
    assert len(saved["cases"]) == len(fresh["cases"])
    for a, b in zip(saved["cases"], fresh["cases"]):
        assert (a["t"], a["p"], a["m"], a["intraday"]) == (b["t"], b["p"], b["m"], b["intraday"])
        for x, y in zip(a["values"], b["values"]):
            assert (x is None) == (y is None), a["t"]
            if x is not None:
                assert x == pytest.approx(y, rel=1e-7, abs=1e-7), a["t"]


# ---------- windows ----------
NOW = datetime(2026, 3, 10, 12, tzinfo=timezone.utc)


def test_window_for_a_range_a_timeframe_and_an_older_page():
    assert CD.window("1d", "1y", None, 3650, NOW) == (366, True)
    assert CD.window("1d", "max", None, 3650, NOW) == (3650, False)       # all the source has: nothing older
    assert CD.window("1d", "ytd", None, 3650, NOW)[0] == 68 + 8
    assert CD.window("5m", "1y", None, 120, NOW) == (10, True)            # intraday ignores daily ranges
    before = NOW - timedelta(days=30)
    days, more = CD.window("1h", None, before, 730, NOW)
    assert days == 31 + CD.PAGE["1h"] and more
    assert CD.window("15m", None, NOW - timedelta(days=400), 59, NOW) == (59, False)


def test_older_keeps_only_candles_before_the_time():
    bars = [{"t": "2026-03-01T00:00:00+05:30"}, {"t": "2026-03-02T00:00:00+05:30"}, {"t": "bad"}]
    assert CD.older(bars, CD.parse_before("2026-03-02")) == bars[:2]       # 2 Mar 00:00 IST is before 2 Mar UTC
    assert CD.older(bars, None) is bars
    assert CD.parse_before("not a date") is None and CD.parse_before("") is None
    assert CD.parse_before("2026-03-02T10:00:00Z").tzinfo is not None
    assert CD.parse_before("2026-03-02T00:00:00 05:30") == CD.parse_before("2026-03-02T00:00:00+05:30")   # "+" unescaped


def test_drawings_are_cleaned():
    items = [{"id": "a", "kind": "trend", "points": [{"t": 1, "p": 2}, {"t": 3, "p": 4}, {"t": 5, "p": 6}]},
             {"kind": "nope", "points": [{"t": 1, "p": 2}]}, {"kind": "hline", "points": []}, "x",
             {"kind": "text", "points": [{"t": 1, "p": float("nan")}, {"t": True, "p": 1}, {"t": 2, "p": 3}], "text": "y" * 500}]
    out = CD.clean(items)
    assert [d["kind"] for d in out] == ["trend", "text"]
    assert len(out[0]["points"]) == 2 and out[1]["points"] == [{"t": 2.0, "p": 3.0}] and len(out[1]["text"]) == 200


# ---------- the API ----------
@pytest.fixture
def w(monkeypatch):
    built = world.build(monkeypatch)
    yield built
    built["close"]()


def test_company_chart_timeframes_and_older_pages(w):
    c = w["client"]
    r = c.get("/research/chart/US/AAPL?range=1y&tf=1d", headers=PRO).json()
    assert r["tf"] == "1d" and r["more"] is True and len(r["candles"]) > 200
    assert {"o", "h", "l", "c", "v"} <= set(r["candles"][0])
    assert r["source"] == "Market data"                                      # never the provider's name
    first = r["candles"][0]["t"]
    old = c.get(f"/research/chart/US/AAPL?tf=1d&before={first}", headers=PRO).json()
    assert old["candles"] and all(b["t"] < first for b in old["candles"])
    intra = c.get("/research/chart/US/AAPL?tf=15m", headers=PRO).json()
    assert intra["tf"] == "15m" and len(intra["candles"]) > 20
    india = c.get("/research/chart/IN/INFY?tf=1h", headers=PRO).json()
    assert india["currency"] == "INR" and india["candles"] and "Kite" not in json.dumps(india)
    assert c.get("/research/chart/US/AAPL?tf=2m", headers=PRO).status_code == 400
    assert c.get("/research/chart/US/AAPL?tf=1d&before=garbage", headers=PRO).status_code == 200


def test_instrument_candles_for_notebooks_and_paper(w):
    c = w["client"]
    inst = c.get("/instruments/search?q=INFY&market=IN", headers=PRO).json()[0]
    r = c.get(f"/chart/candles/{inst['id']}?tf=1d&range=6m", headers=PRO).json()
    assert r["tf"] == "1d" and len(r["candles"]) > 80 and r["more"] is True
    first = r["candles"][0]["t"]
    old = c.get(f"/chart/candles/{inst['id']}?tf=1d&before={first}", headers=PRO).json()["candles"]
    assert old and old[-1]["t"] < first
    assert c.get(f"/chart/candles/{inst['id']}?tf=5m", headers=PRO).json()["candles"]
    assert c.get("/chart/candles/US:AAPL?tf=1h", headers=PRO).json()["candles"]
    assert c.get(f"/chart/candles/{inst['id']}?tf=1w", headers=PRO).status_code == 400
    assert c.get("/chart/candles/IN:999999999?tf=1d", headers=PRO).status_code == 404


def test_drawings_per_user_and_symbol(w):
    c = w["client"]
    line = {"id": "d1", "kind": "trend", "points": [{"t": 1700000000000, "p": 100}, {"t": 1710000000000, "p": 120}]}
    assert c.get("/chart/drawings?symbol=IN:INFY", headers=PRO).json()["items"] == []
    saved = c.put("/chart/drawings", headers=PRO, json={"symbol": "in:infy", "items": [line]}).json()
    assert saved["symbol"] == "IN:INFY" and saved["items"][0]["kind"] == "trend"
    assert c.get("/chart/drawings?symbol=IN:INFY", headers=PRO).json()["items"][0]["id"] == "d1"
    assert c.get("/chart/drawings?symbol=IN:INFY", headers=FREE).json()["items"] == []      # someone else's
    c.put("/chart/drawings", headers=PRO, json={"symbol": "IN:INFY", "items": []})
    assert c.get("/chart/drawings?symbol=IN:INFY", headers=PRO).json()["items"] == []
    c.put("/chart/drawings", headers=PRO, json={"symbol": "AAPL", "items": [line]})
    assert c.delete("/chart/drawings", headers=PRO).json()["deleted"]
    assert c.get("/chart/drawings?symbol=AAPL", headers=PRO).json()["items"] == []
    assert c.get("/chart/drawings?symbol=../x", headers=PRO).status_code == 400
    assert c.get("/chart/drawings?symbol=IN:INFY").status_code == 401


if __name__ == "__main__":
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE.write_text(json.dumps(build_fixture(), separators=(",", ":")))
    print("wrote", FIXTURE)
