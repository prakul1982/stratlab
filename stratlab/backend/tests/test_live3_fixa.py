"""LIVE3 review (live, 4 Nov), the FIXA lane: themes, closes, the parser's periods, names, and stuck jobs."""
import json
from datetime import datetime, timedelta, timezone

import pytest

from app import db, screens, stock_pages
from tests import world
from tests.test_review_r6v import us


@pytest.fixture
def w(monkeypatch):
    built = world.build(monkeypatch)
    yield built
    built["close"]()


# ---------- LIVE3-003: the index (themes, screens, peers) takes each page's newest close as the price job moves it ----------
def test_the_price_job_moves_the_index_rows_with_the_pages_so_a_theme_shows_the_pages_market_value(w, monkeypatch):
    now = datetime.now(timezone.utc)
    day = now.date()
    iso = lambda back: (day - timedelta(days=back)).isoformat()          # noqa: E731
    monkeypatch.setattr(stock_pages, "last_close", lambda region, n=None: (day, now - timedelta(hours=3)))
    built = now.timestamp() - 5 * 3600
    pages_in = {"NVDA": us(symbol="NVDA", name="Nvidia", price=100.0, price_at=iso(1), market_cap=4_000_000.0, pe=50.0),
                "AMD": us(symbol="AMD", name="AMD", price=200.0, price_at=iso(1), market_cap=300_000.0, pe=40.0)}
    for s, f in pages_in.items():
        db.set_setting(f"stocks:page:US:{s}", json.dumps({"ts": built, "facts": f}))
    # the index as gathered before the close: the old prices, for every company in it
    db.set_setting(screens.INDEX_KEY + "US", json.dumps({"at": now.isoformat(), "rows": [screens.row("US", s, f) for s, f in pages_in.items()]}))
    screens._mem.clear(), screens._priced.clear()
    assert {r["symbol"]: r["market_cap"] for r in screens.load_index("US")["rows"]} == {"NVDA": 4_000_000.0, "AMD": 300_000.0}

    def bars_of(region, sym):
        c = 110.0 if sym == "NVDA" else 190.0
        return [{"t": iso(1) + "T00:00:00-04:00", "o": 1, "h": c, "l": c, "c": pages_in[sym]["price"]}, {"t": iso(0) + "T00:00:00-04:00", "o": 1, "h": c, "l": c, "c": c}]
    pages = stock_pages.Pages(lambda r, c: None)
    pages.on_priced = screens.note_price
    assert pages.refresh_prices("US", bars_of, gap=0, now=now)["refreshed"] == 2
    rows = {r["symbol"]: r for r in screens.load_index("US")["rows"]}
    # every company the job moved, at once: the page's own price, date, market value and P/E
    for s in pages_in:
        page = json.loads(db.get_setting(f"stocks:page:US:{s}"))["facts"]
        assert (rows[s]["price"], rows[s]["price_at"], rows[s]["market_cap"], rows[s]["pe"]) == (page["price"], iso(0), page["market_cap"], page["pe"])
    assert rows["NVDA"]["market_cap"] == 4_400_000.0
    # and still after the index is read again from storage (gathered before the close), until the next gathering has them
    screens._mem.clear()
    assert {r["symbol"]: r["market_cap"] for r in screens.load_index("US")["rows"]} == {"NVDA": 4_400_000.0, "AMD": 285_000.0}


def test_a_theme_map_kept_for_a_day_shows_the_market_values_the_index_has_now():
    from app.intel import theme_routes
    kept = {"value_chain": [{"layer": "Defence", "companies": [{"ticker": "BDL", "cap": 37205}, {"ticker": "GRSE", "cap": 24422}, {"ticker": "GONE", "cap": 5}]}],
            "sub_themes": [{"name": "Missiles", "companies": [{"ticker": "BDL", "cap": 37205}]}]}
    now = [{"symbol": "BDL", "market_cap": 39327}, {"symbol": "GRSE", "market_cap": 24570}]
    got = theme_routes.with_caps(kept, now)
    assert [c["cap"] for c in got["value_chain"][0]["companies"]] == [39327, 24570, 5] and got["sub_themes"][0]["companies"][0]["cap"] == 39327
    assert kept["value_chain"][0]["companies"][0]["cap"] == 37205          # the kept map itself isn't changed
