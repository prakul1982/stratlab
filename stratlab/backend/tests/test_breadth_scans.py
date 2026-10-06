"""The trend scans' daily results ride on the breadth run: one read of each stock's candles feeds both. Here on the same
made-up three-stock market as test_breadth: what is stored for the big groups, that a scan problem never costs the
breadth counts, and that the run's own clock for the scans is kept."""
from app import breadth, db, scan_presets, universes
from tests.test_breadth import IST_OPEN, LAST, market, mem, runner  # noqa: F401  (mem is a fixture)


def test_the_run_stores_each_big_groups_preset_matches(mem):
    out = runner().run("IN", IST_OPEN)
    assert out["ok"]
    doc = scan_presets.load("nifty500")
    assert doc["as_of"] == LAST and doc["checked"] == 3                      # the half-made candle after LAST is not used
    by = {r["s"]: r["m"] for r in doc["rows"]}
    assert "high52" in by["FLAT"] and by["FLAT"]["high52"][0] == 0 and by["FLAT"]["high52"][1] == LAST    # FLAT's 5% jump crossed its 252-day high
    assert "st_s2" in by["UP"] and set(by["DOWN"]) == {"near_low52"}         # a steady riser is in Stage 2 above its Supertrend; a faller is at its low
    assert doc["counts"]["st_s2"] == 1 and doc["counts"]["golden_cross"] == 1 and "golden_cross" in by["FLAT"]   # FLAT's jump also lifted its 50-day average over its 200-day
    view = scan_presets.stored_view("nifty500", "st_s2")
    assert [r["symbol"] for r in view["rows"]] == ["UP"] and "Stage 2" in view["rows"][0]["detail"]
    for other in ("nifty50", "nse_all", "midcap150"):                        # only the groups the scans are offered for are stored
        assert scan_presets.load(other) is None


def test_the_scan_clock_and_count_are_kept_in_the_runs_status(mem):
    runner().run("IN", IST_OPEN)
    st = breadth.status()["IN"]
    assert st["scan_stocks"] == 3 and isinstance(st["scan_seconds"], float) and st["scan_seconds"] < 30


def test_a_scan_that_fails_leaves_the_breadth_counts_alone(mem, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("scan broke")
    monkeypatch.setattr(scan_presets, "evaluate", boom)
    out = runner().run("IN", IST_OPEN)
    assert out["ok"] and out["loaded"] == 3
    assert breadth.view("nifty500", "all")["today"]["adv"]["value"] == 2
    doc = scan_presets.load("nifty500")
    assert doc["checked"] == 0 and doc["rows"] == []                          # nothing stored as matching, and nothing claimed as checked


def test_the_us_run_stores_the_sp500_from_the_committed_list(mem, monkeypatch):
    monkeypatch.setattr(universes, "sp500_symbols", lambda: ["UP", "DOWN", "FLAT"])
    monkeypatch.setattr(breadth, "us_large", lambda: ["UP"])
    monkeypatch.setattr(breadth, "sector_map", lambda region: {})
    assert breadth.members("sp500") == ["UP", "DOWN", "FLAT"]
    out = runner().run("US", IST_OPEN)
    assert out["ok"]
    assert scan_presets.load("sp500")["checked"] == 3 and scan_presets.load("nifty500") is None
    assert "sp500" in {g["id"] for g in breadth.groups_list()} and breadth.view("sp500", "all")["today"]["stocks"]["value"] == 3


def test_the_real_sp500_group_is_the_committed_list():
    assert breadth.members("sp500") == universes.sp500_symbols() and len(breadth.members("sp500")) > 480
    assert breadth.GROUPS["sp500"]["region"] == "US"
    assert breadth.sector_map("US")["AAPL"] == "Technology"
