"""24 Oct 2026 deep audit of notebooks after a run (DA-030 .. DA-041): similar coins over a shorter window aren't counted,
a shared link's own card picture and a real 404 when it's off, the library sorted by the gap to buy and hold with its
repeated sentence gone, its group named as today and its dates kept fresh, and a run's trades as a CSV file on Pro."""
import csv
import io
from datetime import datetime, timedelta, timezone

import pytest

from app import basket, db, library, library_seed as S, main, universes
from tests.pngmaker import png_b64
from tests.test_breadth import w  # noqa: F401  (fixture)
from tests.test_notebooks import EMA, api  # noqa: F401  (fixture)

PNG = png_b64(data_url=False)


@pytest.fixture
def store(monkeypatch):
    kv = {}
    monkeypatch.setattr(db, "set_setting", lambda k, v: kv.__setitem__(k, v))
    monkeypatch.setattr(db, "get_setting", lambda k: kv.get(k))
    monkeypatch.setattr(db, "delete_setting", lambda k: kv.pop(k, None))
    return kv


# ---------- DA-030: a similar instrument whose prices start late is listed, not counted ----------
def test_a_history_that_starts_well_into_the_period_is_short():
    now = datetime(2026, 10, 24, tzinfo=timezone.utc)
    five_years = 1825
    assert basket.short_history("2023-07-12T00:00:00+00:00", five_years, now) is True          # XRP/USD on a five-year test
    assert basket.short_history("2021-10-27T00:00:00+00:00", five_years, now) is False         # a weekend's gap is nothing
    assert basket.short_history("2026-09-29T00:00:00+00:00", 30, now) is False                 # a month's test: under ten days
    assert basket.short_history("2026-10-12T00:00:00+00:00", 30, now) is True


def test_the_count_is_like_for_like(monkeypatch):
    rows = {f"CRYPTO:{s}": {"id": f"CRYPTO:{s}", "symbol": s, "ret": r, "buy_hold": 1.0, "n": 5, "win": 50, "mdd": -5,
                            "from": "2021-10-25", "short": False} for s, r in (("ETH/USD", 5), ("SOL/USD", 8), ("ADA/USD", -3), ("LTC/USD", 2))}
    rows["CRYPTO:XRP/USD"] = {**rows["CRYPTO:ETH/USD"], "id": "CRYPTO:XRP/USD", "symbol": "XRP/USD", "ret": 40, "from": "2023-07-12", "short": True}
    monkeypatch.setattr(basket, "_ids", lambda registry, market, exclude: list(rows))
    monkeypatch.setattr(basket, "_one", lambda registry, strategy, iid, days: rows[iid])

    class Prov:
        def ready(self):
            return True

    class Reg:
        def provider(self, m):
            return Prov()
    out = basket.run(Reg(), None, "CRYPTO", "CRYPTO:BTC-USD", 1825)
    assert out["tested"] == 4 and out["profitable"] == 3 and out["headline"] == "Profitable on 3 of 4 similar instruments."
    assert out["shorter"] == [{"symbol": "XRP/USD", "from": "2023-07-12"}]
    assert any(r["symbol"] == "XRP/USD" for r in out["rows"])                                  # still listed, with its own dates
    assert out["median_ret"] == 3.5                                                             # of the four alike


def test_each_row_says_where_its_prices_start(api):  # noqa: F811
    nb = api.post("/notebooks", json={"name": "Trend follower", "strategy": EMA, "instrument": "CRYPTO:BTC-USD"}).json()
    api.post(f"/notebooks/{nb['id']}/experiments", json={"days": 400})
    b = api.post(f"/notebooks/{nb['id']}/experiments/1/basket").json()["basket"]
    tested = [r for r in b["rows"] if "error" not in r]
    assert tested and all(len(r["from"]) == 10 and isinstance(r["short"], bool) for r in tested)
    assert "shorter" in b


# ---------- DA-034, DA-035: the shared page names its own card; a link turned off is gone at once ----------
def test_the_public_verdict_says_whether_it_keeps_a_card_picture(api, store):  # noqa: F811
    nb = api.post("/notebooks", json={"name": "T", "strategy": EMA, "instrument": "CRYPTO:BTC-USD"}).json()
    api.post(f"/notebooks/{nb['id']}/experiments", json={"days": 400})
    token = api.post(f"/notebooks/{nb['id']}/experiments/1/share", json={"image": "data:image/png;base64," + PNG}).json()["token"]
    assert api.get(f"/public/v/{token}").json()["image"] is True
    page = api.get(f"/v/{token}")
    assert page.headers["cache-control"] == "no-cache" and f"/v/{token}.png" in page.text
    api.delete(f"/notebooks/{nb['id']}/experiments/1/share")
    gone = api.get(f"/v/{token}", follow_redirects=False)
    assert gone.status_code == 404 and "isn't available" in gone.text


# ---------- DA-037: sorted by the gap to buy and hold; the repeated sentence and the old group name gone ----------
def entry(name, ret, hold, verdict="edge", **kw):
    return {"name": name, "verdict": {"verdict": verdict, "passed": 4, "total": 4}, "stats": {"ret": ret, "buy_hold": hold, "trades": 20, "unseen": 1},
            "published_at": "2026-10-01", "copies": 0, **kw}


def test_the_library_leads_with_the_strategy_furthest_ahead_of_buy_and_hold(api):  # noqa: F811
    rows = [entry("supertrend", 20, 128.5), entry("donchian", 30, 25, verdict="mixed"), entry("idle", 0, 10)]
    rows[2]["stats"]["trades"] = 0                                     # never traded: no gap to go by
    assert [r["name"] for r in library.search(rows, sort="hold")] == ["donchian", "supertrend", "idle"]
    assert [r["name"] for r in library.search(rows, sort="best")] == ["supertrend", "donchian", "idle"]      # by checks, still offered
    import inspect
    assert inspect.signature(main.browse_library).parameters["sort"].default == "hold"
    assert inspect.signature(main.public_library).parameters["sort"].default == "hold"


def test_stratlabs_own_entries_drop_the_sentence_every_card_repeated_and_use_todays_group_name():
    e = entry("Supertrend flip · 20 US large caps", 20, 128.5, official=True, question="How did Supertrend flip do on 20 US large caps?",
              description=f"Buys on a flip. A 12% stop loss. {library.SEED_NOTE}", group={"name": "20 US large caps", "members": []},
              seed={"universe": "us_mega", "market": "US"})
    out = library.public(e)
    assert out["description"] == "Buys on a flip. A 12% stop loss."
    now = next(p["name"] for p in universes.PRESETS["US"] if p["id"] == "us_mega")
    assert out["group"]["name"] == now and out["name"] == f"Supertrend flip · {now}" and now in out["question"]
    mine = library.public({**e, "official": False})                     # a reader's own words are theirs
    assert library.SEED_NOTE in mine["description"] and mine["group"]["name"] == "20 US large caps"


# ---------- DA-038: StratLab's own entries are run again once their dates are a week old ----------
def test_entries_tested_over_a_week_ago_are_stale():
    now = datetime(2026, 10, 24, tzinfo=timezone.utc)
    assert S.stale([{"range": {"from": "2021-10-13", "to": "2026-10-13"}}], now) is True
    assert S.stale([{"range": {"to": "2026-10-13"}}, {"range": {"to": "2026-10-22T00:00:00+00:00"}}], now) is False
    assert S.stale([{"id": "seed-x"}], now) is False                     # no dates: nothing to go by


def test_start_up_runs_a_stale_library_again(w, monkeypatch):  # noqa: F811
    seeds, waits = [], []
    old = (datetime.now(timezone.utc) - timedelta(days=11)).date().isoformat()
    monkeypatch.setattr(S, "seeded", lambda: [{"id": "seed-x", "range": {"from": "2021-10-13", "to": old}}])
    monkeypatch.setattr(S, "seed", lambda registry, **kw: seeds.append(1) or {"published": [], "failed": []})
    monkeypatch.setattr(main.kite, "ready", lambda: True)
    main.library_seed_once(sleep=waits.append)
    assert seeds == [1] and waits == [main.SEED_FIRST_WAIT]


# ---------- DA-041: a run's trades as CSV, on the plan whose export promises them ----------
def test_a_runs_trades_download_as_csv_on_pro(api):  # noqa: F811
    nb = api.post("/notebooks", json={"name": "Trend follower", "strategy": EMA, "instrument": "CRYPTO:BTC-USD"}).json()
    exp = api.post(f"/notebooks/{nb['id']}/experiments", json={"days": 1500}).json()["experiment"]
    r = api.get(f"/notebooks/{nb['id']}/experiments/1/trades.csv")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert 'filename="Trend-follower-v1-trades.csv"' in r.headers["content-disposition"]
    rows = list(csv.reader(io.StringIO(r.text)))
    assert tuple(rows[0]) == main.TRADE_COLUMNS and len(rows) - 1 == len(exp["trades"]) > 0
    first, t = rows[1], exp["trades"][0]
    assert first[2] == t["entry_t"] and float(first[7]) == pytest.approx(t["pnl"], abs=0.01)
    assert api.get(f"/notebooks/{nb['id']}/experiments/9/trades.csv").status_code == 404
    api.profile["_plan"] = "free"
    try:
        locked = api.get(f"/notebooks/{nb['id']}/experiments/1/trades.csv")
        assert locked.status_code == 402 and "Pro" in locked.json()["detail"]["message"]
    finally:
        api.profile["_plan"] = "pro"


def test_a_cell_a_spreadsheet_would_run_is_written_as_text():
    out = main.trades_csv({"instrument": {"symbol": "AAPL"}, "trades": [
        {"entry_t": "2026-01-02", "exit_t": "2026-01-05", "qty": 2, "entry": 100, "exit": 110, "pnl": 19.5, "why": "=HYPERLINK(1)"},
        {"entry_t": "2026-02-02", "exit_t": None, "qty": 1, "entry": 100, "exit": 90, "pnl": -10, "why": ""}]})
    rows = list(csv.reader(io.StringIO(out)))
    assert rows[1][-1] == "'=HYPERLINK(1)" and rows[1][0] == "AAPL" and rows[1][8] == "9.75"
    assert rows[2][3] == "" and rows[2][-1].startswith("Still open") and rows[2][7] == "-10"
