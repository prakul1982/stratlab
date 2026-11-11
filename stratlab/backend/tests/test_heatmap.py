"""The stock heatmap (L4): each stock's row worked out by hand from made-up candles, the daily breadth run storing every row and
each group's index, the first fill of a market that has no rows yet, the page's answer (names, sectors and market values joined from
the screens' index, the smallest market value, the bound on tiles, a theme's list of symbols), and its inputs and wording."""
import json
from datetime import datetime, timedelta, timezone

import pytest

from app import breadth, db, heatmap, screens
from tests import world as W
from tests.fake_db import headers
from tests.test_breadth import ADVICE, IST_OPEN, LAST, PROVIDERS, bars, market, mem, runner, weekdays  # noqa: F401  (mem is a fixture)


@pytest.fixture(autouse=True)
def fresh():
    heatmap.clear()
    yield
    heatmap.clear()


@pytest.fixture
def w(monkeypatch):
    world = W.build(monkeypatch)
    yield world
    world["close"]()


# ---------- one stock ----------
def test_changes_over_each_period_by_hand():
    days = ["2025-11-10", "2025-12-31", "2026-08-10", "2026-10-09", "2026-11-03", "2026-11-09", "2026-11-10"]
    closes = [50.0, 80.0, 100.0, 125.0, 160.0, 190.0, 200.0]
    # the last close is 200 on 10 Nov 2026: a day before 190; a week before (3 Nov) 160; a month before (11 Oct) the 9 Oct close 125;
    # three months before (11 Aug) the 10 Aug close 100; the year so far from the 31 Dec close 80; a year before (10 Nov 2025) 50
    assert heatmap.changes(days, closes) == [5.26, 25.0, 60.0, 100.0, 150.0, 300.0]
    assert heatmap.PERIODS == ("1d", "1w", "1m", "3m", "ytd", "1y")


def test_a_period_the_candles_do_not_reach_back_to_has_no_change():
    days, closes = ["2026-11-02", "2026-11-09", "2026-11-10"], [90.0, 100.0, 110.0]
    assert heatmap.changes(days, closes) == [10.0, 22.22, None, None, None, None]
    assert heatmap.changes(["2026-11-10"], [110.0]) == [None] * 6


def test_row_has_the_close_the_changes_and_the_volume_against_its_average():
    closes = [100.0] * 29 + [110.0]
    b = bars(closes, vol=1000.0)
    b[-1]["v"] = 2500.0
    row = heatmap.heat_row(b, LAST)
    assert row[0] == 110.0 and row[1] == 10.0 and row[2] == 10.0 and row[3] == 10.0
    assert row[4:7] == [None, None, None]                       # six weeks of candles: no three months, year so far or year
    assert row[7] == 2500.0 and row[8] == 1000.0                # the last day's volume, the 20 sessions before it
    assert len(row) == len(heatmap.PERIODS) + 3
    short = heatmap.heat_row(bars([100.0, 101.0, 102.0]), LAST)
    assert short[8] is None                                     # under 20 sessions before the last: no average


def test_unfinished_and_stale_candles_are_left_out():
    b = bars([100.0, 110.0]) + [{"t": "2026-10-01T00:00:00+05:30", "c": 1.0, "v": 1}]
    assert heatmap.heat_row(b, LAST)[0] == 110.0                # the half-made candle after `through` is ignored
    old = bars([100.0, 110.0], end="2026-09-01")
    assert heatmap.heat_row(old, LAST) is None                  # last traded a month before the run's day: suspended
    assert heatmap.heat_row([], LAST) is None and heatmap.heat_row(bars([5.0]), LAST) is None


def test_index_row_from_closes_by_day():
    assert heatmap.index_row({"2026-11-09": 100.0, "2026-11-10": 102.0})[0] == 2.0
    assert heatmap.index_row({}) is None and heatmap.index_row({"2026-11-10": 5.0}) is None


# ---------- the daily run ----------
def test_the_breadth_run_stores_every_stocks_row_and_each_groups_index(mem):
    calls = []
    out = runner(calls=calls).run("IN", IST_OPEN)
    assert out["ok"] and len(calls) == 3                        # one read a stock: the heatmap asks for nothing more
    doc = json.loads(mem[heatmap.KEY + "IN"])
    assert doc["day"] == LAST and set(doc["stocks"]) == {"UP", "DOWN", "FLAT"}
    assert doc["stocks"]["FLAT"][:2] == [105.0, 5.0]            # 100 every day, 105 on the last
    up = doc["stocks"]["UP"]
    assert up[0] == 999.0 and up[1] == round((999 / 998 - 1) * 100, 2)
    assert up[7] == 1000.0 and up[8] == 1000.0
    idx = doc["index"]["nifty500"]                              # the index rises by 1 a day from 20000
    assert idx[0] == round((20899 / 20898 - 1) * 100, 2) and len(idx) == 6
    assert set(doc["index"]) == {g for g, v in breadth.GROUPS.items() if v["region"] == "IN"}


def test_a_heatmap_problem_never_costs_the_breadth_counts(mem, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("no")
    monkeypatch.setattr(heatmap, "heat_row", boom)
    out = runner().run("IN", IST_OPEN)
    assert out["ok"] and out["groups"]["nifty500"]["stocks"] == 3
    assert heatmap.KEY + "IN" not in mem


def test_a_market_with_history_but_no_heatmap_rows_is_read_once_at_the_first_chance(mem):
    calls = []
    runner().run("IN", IST_OPEN)                                # the history every group needs
    del mem[heatmap.KEY + "IN"]                                 # ...stored before the heatmap existed
    job = breadth.Job(runner(calls=calls), ready=lambda r: r == "IN")
    open_hours = datetime(2026, 10, 1, 5, 0, tzinfo=timezone.utc)                       # Thursday 10:30 IST: the market is open
    assert job.tick(open_hours) == 0 and len(calls) == 0                                # ...so no full read beside the live session
    job._heat_wait = {}                                                                 # (the quarter-hour wait over)
    morning = datetime(2026, 10, 1, 10, 30, tzinfo=timezone.utc)                        # 16:00 IST: after the close, before the day's run
    assert job.tick(morning) == 1 and len(calls) == 3
    assert heatmap.load("IN")["stocks"]
    assert job.tick(morning + timedelta(minutes=5)) == 0 and len(calls) == 3           # ...once
    again = breadth.Job(runner(calls=calls), ready=lambda r: r == "IN")                 # a restart: the rows are there
    assert again.tick(morning + timedelta(minutes=10)) == 0 and len(calls) == 3


# ---------- what the page shows ----------
def store(region="IN", n=3, group="nifty500"):
    syms = [f"S{i:03d}" for i in range(n)]
    rows = {s: [100.0 + i, 1.0 + i, 2.0, 3.0, 4.0, 5.0, 6.0, 2000.0, 1000.0] for i, s in enumerate(syms)}
    heatmap.save(region, "2026-10-27", rows, {group: [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]})
    db.set_setting(breadth.MEMBERS_KEY + group, json.dumps(syms))
    index = [{"symbol": s, "name": f"Company {i}", "sector": "Financial Services" if i % 2 else "Energy", "industry": "Banks" if i % 2 else "Refineries",
              "market_cap": 1000.0 * (n - i), "price": 100.0 + i} for i, s in enumerate(syms)]
    db.set_setting(screens.INDEX_KEY + region, json.dumps({"at": "2026-10-27T12:00:00+00:00", "rows": index}))
    with screens._mem_lock:
        screens._mem.clear()
    return syms


def test_before_the_first_run_the_page_says_pending(w):
    r = w["client"].get("/invest/heatmap?market=IN", headers=headers("free-token"))
    assert r.status_code == 200
    v = r.json()
    assert v["pending"] is True and v["tiles"] == [] and v["as_of"] is None
    assert v["universe"] == "nifty500" and [u["id"] for u in v["universes"]] == list(heatmap.UNIVERSES["IN"])
    assert w["client"].get("/invest/heatmap?market=US", headers=headers("free-token")).json()["universe"] == "sp500"


def test_tiles_join_the_rows_to_names_sectors_and_market_values(w):
    store()
    v = w["client"].get("/invest/heatmap?market=IN&universe=nifty500", headers=headers("free-token")).json()
    assert v["pending"] is False and v["as_of"] == "2026-10-27" and v["cap_unit"] == "₹ crore"
    assert v["index"] == {"name": "NIFTY 500", "r": [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]} and v["periods"] == list(heatmap.PERIODS)
    assert [t["s"] for t in v["tiles"]] == ["S000", "S001", "S002"]                    # the largest market value first
    t = v["tiles"][1]
    assert t == {"s": "S001", "n": "Company 1", "sec": "Financial Services", "ind": "Banks", "cap": 2000.0, "px": 101.0,
                 "r": [2.0, 2.0, 3.0, 4.0, 5.0, 6.0], "vx": 2.0, "tv": 202000}
    assert v["members"] == 3 and v["with_prices"] == 3 and v["shown"] == 3
    text = json.dumps(v)
    assert not PROVIDERS.search(text) and not ADVICE.search(text)


def test_smallest_market_value_and_the_bound_on_tiles(w, monkeypatch):
    store(n=12)
    c, h = w["client"], headers("free-token")
    v = c.get("/invest/heatmap?market=IN&universe=nifty500&min_cap=10000", headers=h).json()
    assert [t["s"] for t in v["tiles"]] == ["S000", "S001", "S002"] and v["matching"] == 3 and v["min_cap"] == 10000
    monkeypatch.setattr(heatmap, "MAX_TILES", 5)
    heatmap.clear()
    v = c.get("/invest/heatmap?market=IN&universe=nifty500", headers=h).json()
    assert v["shown"] == 5 and v["matching"] == 12 and [t["s"] for t in v["tiles"]] == [f"S{i:03d}" for i in range(5)]


def test_a_company_without_a_market_value_keeps_its_tile_and_sorts_last(w):
    syms = store()
    idx = json.loads(db.get_setting(screens.INDEX_KEY + "IN"))
    idx["rows"] = [r for r in idx["rows"] if r["symbol"] != "S000"]
    db.set_setting(screens.INDEX_KEY + "IN", json.dumps(idx))
    with screens._mem_lock:
        screens._mem.clear()
    v = w["client"].get("/invest/heatmap?market=IN", headers=headers("free-token")).json()
    assert [t["s"] for t in v["tiles"]] == ["S001", "S002", "S000"] and v["tiles"][-1]["cap"] is None and v["tiles"][-1]["n"] == "S000"
    assert len(syms) == 3


def test_a_themes_symbols_get_their_tiles_whatever_group_they_are_in(w):
    store()
    c, h = w["client"], headers("free-token")
    v = c.get("/invest/heatmap?market=IN&symbols=s002,NOPE,S000", headers=h).json()
    assert [t["s"] for t in v["tiles"]] == ["S000", "S002"] and v["members"] == 3 and v["with_prices"] == 2 and v["universe"] is None
    assert c.get("/invest/heatmap?market=IN&symbols=", headers=h).status_code == 400
    many = ",".join(f"X{i}" for i in range(heatmap.MAX_SYMBOLS + 1))
    assert c.get(f"/invest/heatmap?market=IN&symbols={many}", headers=h).status_code == 400


def test_bad_input_and_sign_in(w):
    c, h = w["client"], headers("free-token")
    assert c.get("/invest/heatmap?market=XX", headers=h).status_code == 400
    assert c.get("/invest/heatmap?market=IN&universe=sp500", headers=h).status_code == 404
    assert c.get("/invest/heatmap?market=IN&min_cap=-1", headers=h).status_code == 400
    assert c.get("/invest/heatmap?market=IN").status_code == 401


def test_one_answer_is_shared_until_the_next_run_stores_new_rows(w, monkeypatch):
    store()
    c, h = w["client"], headers("free-token")
    calls = []
    real = heatmap.view
    monkeypatch.setattr(heatmap, "view", lambda *a, **k: calls.append(a) or real(*a, **k))
    for _ in range(3):
        assert c.get("/invest/heatmap?market=IN", headers=h).json()["shown"] == 3
    assert len(calls) == 1
    heatmap.save("IN", "2026-10-28", {"S000": [1.0, 1, 1, 1, 1, 1, 1, 10.0, 10.0]}, {})
    assert c.get("/invest/heatmap?market=IN", headers=h).json()["as_of"] == "2026-10-28" and len(calls) == 2


# ---------- LIVE6-005: a theme's companies outside every stored group ----------
def _candles(last=110.0):
    """Daily candles over 400 calendar days to 27 Oct 2026, the last close `last`, so heat_row gives a full row."""
    end = datetime(2026, 10, 27)
    out = [{"t": (end - timedelta(days=d)).strftime("%Y-%m-%d"), "c": 100.0, "v": 1000.0} for d in range(400, 0, -1)
           if (end - timedelta(days=d)).weekday() < 5]
    return out + [{"t": "2026-10-27", "c": last, "v": 3000.0}]


def _outside(extra):
    """The screens' index with companies the stored rows don't have (the theme's non-index members), largest first."""
    idx = json.loads(db.get_setting(screens.INDEX_KEY + "IN"))
    idx["rows"] += extra
    db.set_setting(screens.INDEX_KEY + "IN", json.dumps(idx))
    with screens._mem_lock:
        screens._mem.clear()


def test_live6_005_theme_members_without_a_stored_row_are_read_on_demand_largest_first_and_kept(w, monkeypatch):
    store()
    _outside([{"symbol": "BIG", "name": "Big Co", "sector": "Technology", "market_cap": 90000.0, "price": 55.0},
              {"symbol": "MID", "name": "Mid Co", "sector": "Technology", "market_cap": 5000.0, "price": 20.0}])
    calls = []
    monkeypatch.setattr(heatmap, "_history", lambda r, s, d: calls.append((r, s, d)) or _candles())
    c, h = w["client"], headers("free-token")
    v = c.get("/invest/heatmap?market=IN&symbols=S000,MID,BIG", headers=h).json()
    assert [t["s"] for t in v["tiles"]] == ["BIG", "MID", "S000"]                   # the largest drawn first, none dropped
    assert v["members"] == 3 and v["with_prices"] == 3 and v["price_only"] == 0
    big = v["tiles"][0]
    assert big["px"] == 110.0 and big["r"][0] == 10.0 and big["n"] == "Big Co" and big["cap"] == 90000.0
    assert sorted(s for _, s, _ in calls) == ["BIG", "MID"] and all(d >= 380 for *_, d in calls)  # a year and more back
    c.get("/invest/heatmap?market=IN&symbols=S000,MID,BIG", headers=h)
    assert len(calls) == 2                                                           # kept: not read again before the next run


def test_live6_005_reads_are_bounded_and_a_company_still_without_closes_shows_its_last_price(w, monkeypatch):
    store()
    _outside([{"symbol": f"X{i:02d}", "name": f"Extra {i}", "market_cap": 1000.0 * (40 - i), "price": 10.0 + i} for i in range(30)]
             + [{"symbol": "GONE", "name": "Gone Co", "market_cap": 99999.0, "price": None}])
    calls = []

    def hist(r, s, d):
        calls.append(s)
        if s == "X00":
            raise RuntimeError("busy")                 # the source busy: not kept, tried again next time
        if s == "GONE":
            raise LookupError("not listed")
        return _candles()

    monkeypatch.setattr(heatmap, "_history", hist)
    monkeypatch.setattr(heatmap, "ON_DEMAND", 10)
    syms = ",".join(["GONE"] + [f"X{i:02d}" for i in range(30)])
    v = w["client"].get(f"/invest/heatmap?market=IN&symbols={syms}", headers=headers("free-token")).json()
    assert sorted(calls) == ["GONE"] + [f"X{i:02d}" for i in range(9)]               # at most ON_DEMAND reads, the largest ten
    assert v["members"] == 31 and v["with_prices"] == 8                               # X01..X08 read
    assert v["price_only"] == 22                                                      # X00 (busy) and X09..X29: their last price, grey
    grey = next(t for t in v["tiles"] if t["s"] == "X20")
    assert grey["px"] == 30.0 and grey["r"] == [None] * 6 and grey["vx"] is None
    assert "GONE" not in {t["s"] for t in v["tiles"]}                                 # no closes and no price: left out, counted
    v2 = w["client"].get(f"/invest/heatmap?market=IN&symbols={syms}", headers=headers("free-token")).json()
    assert sorted(calls[10:]) == ["X00"] + [f"X{i:02d}" for i in range(9, 18)]       # GONE kept as none; the next ten read
    assert v2["with_prices"] == 17


def test_live6_005_a_slow_source_never_holds_the_page_past_its_wait(w, monkeypatch):
    import time as _t
    store()
    _outside([{"symbol": "SLOW", "name": "Slow Co", "market_cap": 1.0, "price": 7.0}])
    monkeypatch.setattr(heatmap, "_history", lambda r, s, d: _t.sleep(1.5) or _candles())
    monkeypatch.setattr(heatmap, "ON_DEMAND_SECS", 0.2)
    began = _t.perf_counter()
    v = w["client"].get("/invest/heatmap?market=IN&symbols=S000,SLOW", headers=headers("free-token")).json()
    assert _t.perf_counter() - began < 1.2
    assert v["with_prices"] == 1 and v["price_only"] == 1
