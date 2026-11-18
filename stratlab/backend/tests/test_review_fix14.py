"""fix14: the live review LIVE11B (Release 66/67): each finding's fix, tested so it fails before and passes after."""
import numpy as np
from fastapi.testclient import TestClient

from app import main, scan
from app.intel.net import SourceError
from tests.test_scan_presets import FakeRegistry, bars, noise


# ---------- LIVE11B-011: a scan asks again for the stocks a busy price source turned away, before reporting them ----------
def _busy_world(monkeypatch, fail_times: int):
    """Three stocks; BBB's and CCC's first `fail_times` reads are turned away as busy (our rate limit), AAA's never."""
    scan._cache.clear()
    monkeypatch.setattr(scan, "BUSY_PAUSE", 0.0)
    monkeypatch.setattr(scan, "session_day", lambda market, now=None: None)
    flat = list(100 + noise(280, 3, 0.4))
    top = max(flat[-252:])
    series = {"AAA": bars(flat + [top + 5]), "BBB": bars(flat + [top + 6]), "CCC": bars(flat + [top - 5])}
    tries: dict[str, int] = {}

    def read(registry, iid):
        sym = iid.split(":")[1]
        tries[sym] = tries.get(sym, 0) + 1
        if sym != "AAA" and tries[sym] <= fail_times:
            raise SourceError("prices", "prices is busy (our rate limit). Try again in a minute.", busy=True)
        return series[sym]

    monkeypatch.setattr(scan, "_bars", read)
    return FakeRegistry(series), tries


def test_a_preset_scan_reads_the_busy_stocks_again_before_reporting(monkeypatch):
    reg, tries = _busy_world(monkeypatch, fail_times=1)
    out = scan.run_preset(reg, "US", [{"symbol": "AAA"}, {"symbol": "BBB"}, {"symbol": "CCC"}], "high52")
    assert out["problems"] == [] and out["checked"] == 3
    assert sorted(r["symbol"] for r in out["rows"]) == ["AAA", "BBB"]
    assert tries == {"AAA": 1, "BBB": 2, "CCC": 2}            # only the turned-away ones were asked again
    scan._cache.clear()


def test_the_stage_scan_reads_the_busy_stocks_again_too(monkeypatch):
    reg, tries = _busy_world(monkeypatch, fail_times=1)
    out = scan.run(reg, "US", [{"symbol": "AAA"}, {"symbol": "BBB"}, {"symbol": "CCC"}])
    assert out["problems"] == [] and len(out["rows"]) == 3
    scan._cache.clear()


def test_a_source_still_busy_after_the_retries_is_reported_and_a_real_problem_is_not_retried(monkeypatch):
    reg, tries = _busy_world(monkeypatch, fail_times=99)
    out = scan.run_preset(reg, "US", [{"symbol": "AAA"}, {"symbol": "BBB"}, {"symbol": "CCC"}], "high52")
    assert out["checked"] == 1 and len(out["problems"]) == 2 and all("busy" in p for p in out["problems"])
    assert tries["BBB"] == 1 + scan.BUSY_RETRIES
    # too few prices is an answer, not a busy source: read once
    scan._cache.clear()
    calls = {"n": 0}

    def short(registry, iid):
        calls["n"] += 1
        return bars([100.0] * 10)

    monkeypatch.setattr(scan, "_bars", short)
    scan.run_preset(FakeRegistry({"DDD": []}), "US", [{"symbol": "DDD"}], "high52")
    assert calls["n"] == 1
    scan._cache.clear()


# ---------- LIVE11B-004: the data status is a public answer the app asks for as it starts ----------
def test_public_data_status_says_whether_india_is_online_and_its_note(monkeypatch):
    c = TestClient(main.app)
    monkeypatch.setattr(main.kite, "ready", lambda: False)
    got = c.get("/public/data-online").json()
    assert got["data_online"] is False and set(got["data_note"]) == {"closed", "back_at"}
    monkeypatch.setattr(main.kite, "ready", lambda: True)
    assert c.get("/public/data-online").json() == {"data_online": True, "data_note": None}
