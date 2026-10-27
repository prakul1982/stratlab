"""RC2A-023: the first scan of a 50-stock list was slow. A scan reads each stock's candles and its stored company name; the
candles from the price source (paced by the source itself) and the names from the database, the names one round trip after
another once every price was in. The names are now read in each stock's own turn, beside the price reads, and eight stocks
are read at a time. The answer is the same."""
import time
from datetime import datetime, timedelta, timezone

import numpy as np

from app import scan, stock_pages

LATENCY, DB_LATENCY = 0.10, 0.05      # seconds a price answer and a database read take in the fake world
STOCKS = 50


def bars_from(closes):
    t0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
    return [{"t": (t0 + timedelta(days=i)).isoformat(), "o": c, "h": c * 1.01, "l": c * 0.99, "c": c, "v": 1000}
            for i, c in enumerate(closes)]


def series():
    out, rng = {}, np.random.default_rng(7)
    for i in range(STOCKS):
        n = 330
        drift = [0.35, -0.2, 0.0, 0.5][i % 4]
        closes = 100 + np.cumsum(rng.normal(drift, 1.0, n)) + np.linspace(0, drift * 40, n)
        closes = np.maximum(closes, 5.0)
        if i % 5 == 0:                                       # a new 52-week high on the last candle
            closes = np.concatenate([closes[:-1], [closes.max() + 5]])
        out[f"S{i:02d}"] = bars_from(list(closes))
    return out


class SlowProv:
    def __init__(self, data):
        self.data = data

    def ready(self): return True

    def instrument(self, key): return {"symbol": key, "name": key.title(), "currency": "USD"}

    def history(self, inst, tf, days, ttl=None):
        time.sleep(LATENCY)                                  # the price source answering
        return self.data[inst["symbol"]]


class SlowRegistry:
    def __init__(self, data): self.data, self.prov = data, SlowProv(data)
    def provider(self, m): return self.prov
    def resolve(self, iid):
        sym = iid.split(":")[1]
        return (self.prov, {"symbol": sym}) if sym in self.data else (self.prov, None)


def world(monkeypatch):
    data = series()
    monkeypatch.setattr(scan, "settled_at", lambda market, now=None: None)
    monkeypatch.setattr(scan, "session_day", lambda market, now=None: None)
    monkeypatch.setattr(stock_pages, "companies", lambda region: {})

    def stored(key):                                          # the stored page's facts: a database read
        time.sleep(DB_LATENCY)
        return {"facts": {"name": "Company " + key.rsplit(":", 1)[1]}}
    monkeypatch.setattr(stock_pages, "_setting", stored)
    scan._cache.clear()
    return SlowRegistry(data), [{"symbol": s} for s in data]


def reference_run(reg, market, members):
    """What scan.run answered before: every stock read and analysed, then each row's name read one after another."""
    rows = []
    for m in members:
        iid = f"{market}:{m['symbol']}"
        res = scan.analyse(scan._bars(reg, iid))
        inst = reg.provider(market).instrument(m["symbol"])
        rows.append({"id": iid, "symbol": inst["symbol"], "name": scan.company_name(market, inst, iid), "currency": inst["currency"], **res})
    rows.sort(key=lambda r: (scan.RANK.get(r["signal"], 3), -(r["chg"] or 0)))
    return rows


def test_a_cold_50_stock_scan_reads_prices_and_names_together_and_gives_the_same_rows(monkeypatch):
    reg, members = world(monkeypatch)
    want = reference_run(reg, "US", members)
    scan._cache.clear()
    t0 = time.monotonic()
    out = scan.run(reg, "US", members)
    took = time.monotonic() - t0
    assert out["rows"] == want and len(want) == STOCKS and not out["problems"]
    assert all(r["name"] and r["name"].startswith("Company ") and "_name" not in r for r in out["rows"])
    # one after another the same reads take 50 x (0.10 + 0.05) = 7.5 s on one thread, 3.75 s on the four the scan had;
    # eight at a time with the names beside the prices: about 1 s
    assert took < 2.2, took
    assert {k: v for k, v in out["counts"].items()} == {k: sum(1 for r in want if r["signal"] == k) for k in ("fresh", "st_s2", "stage2")}


def test_a_preset_scan_gives_the_same_matches_with_their_names(monkeypatch):
    reg, members = world(monkeypatch)
    from app import scan_presets
    want = []
    for m in members:
        iid = f"US:{m['symbol']}"
        res = scan_presets.evaluate(scan._bars(reg, iid), through=None, only=["high52"], live=True)
        hit = scan_presets.lagged(res["matches"].get("high52"), res["as_of"], res["as_of"], "high52") if res else None
        if hit:
            want.append((m["symbol"], "Company " + m["symbol"], hit["days_ago"], hit["detail"]))
    scan._cache.clear()
    t0 = time.monotonic()
    out = scan.run_preset(reg, "US", members, "high52", live=True)
    took = time.monotonic() - t0
    got = sorted((r["symbol"], r["name"], r["days_ago"], r["detail"]) for r in out["rows"])
    assert got == sorted(want) and len(got) >= 5 and out["checked"] == STOCKS
    assert took < 2.2, took


def test_a_stock_whose_candles_fail_is_still_a_named_problem_not_a_failed_scan(monkeypatch):
    reg, members = world(monkeypatch)
    reg.data["S03"] = reg.data["S03"][:10]                    # too few candles: "not enough daily prices yet"
    out = scan.run(reg, "US", members)
    assert len(out["rows"]) == STOCKS - 1 and any(p.startswith("S03:") for p in out["problems"])


def test_a_scan_with_a_budget_still_ends_its_wait_at_the_budget_and_names_the_rows(monkeypatch):
    reg, members = world(monkeypatch)
    want = reference_run(reg, "US", members)
    scan._cache.clear()
    out = scan.run(reg, "US", members, budget=30)
    assert out["rows"] == want and out["late"] == []
