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


# ---------- LIVE3-002: a public page is never served past its market's next close ----------
def test_an_up_to_date_page_is_kept_by_the_edge_never_past_its_markets_next_settle_point_at_any_hour():
    """Every hour of a week, both markets: the edge copy (s-maxage) of a page at the latest close ends at or before the next settle
    point, and is never more than a day; a page cached on 3 Nov evening can't be served on 4 Nov evening."""
    import re
    start = datetime(2026, 11, 2, 0, 0, tzinfo=timezone.utc)
    for region in ("IN", "US"):
        for h in range(7 * 24):
            now = start + timedelta(hours=h, minutes=17)
            day = stock_pages.last_close(region, now)[0].isoformat()
            f = {"region": region, "price_at": day, "price_official": True}
            cc = stock_pages.cache_control(region, f, now)
            s = int(re.search(r"s-maxage=(\d+)", cc).group(1))
            nxt = stock_pages.next_settle(region, now)
            assert s <= 86400 and now + timedelta(seconds=s) <= max(nxt, now + timedelta(seconds=stock_pages.MIN_CACHE)), (region, now, cc)


def test_an_india_page_at_the_close_waits_for_the_official_close_a_quarter_of_an_hour_at_a_time():
    now = datetime(2026, 11, 4, 13, 30, tzinfo=timezone.utc)           # 19:00 IST: past the settle point, the official close not yet on the page
    day = stock_pages.last_close("IN", now)[0].isoformat()
    assert day == "2026-11-04"
    page = {"region": "IN", "price_at": day}
    assert stock_pages.cache_control("IN", page, now) == stock_pages.OFFICIAL_WAIT_CACHE
    assert stock_pages.cache_control("IN", {**page, "price_official": True}, now) != stock_pages.OFFICIAL_WAIT_CACHE
    # the next morning the official close is no longer waited for: the usual copy, to the next settle point
    assert stock_pages.cache_control("IN", page, datetime(2026, 11, 5, 4, 0, tzinfo=timezone.utc)) != stock_pages.OFFICIAL_WAIT_CACHE


def test_directory_pages_follow_the_same_bound(w):
    import re
    c = w["client"]
    for u in ("/stocks", "/stocks/in", "/stocks/us/index/sp-500"):
        s = int(re.search(r"s-maxage=(\d+)", c.get(u).headers["cache-control"]).group(1))
        regions = ["IN"] if u == "/stocks/in" else ["US"] if "/us" in u else ["IN", "US"]
        nxt = min(stock_pages.next_settle(r) for r in regions)
        assert s <= 86400 and datetime.now(timezone.utc) + timedelta(seconds=s - 5) <= nxt, (u, s)


def test_a_page_rendered_a_close_behind_keeps_the_minute_header_after_its_facts_leave_memory(w, monkeypatch):
    """The live cause: the rendered copy stayed in memory after the facts kept beside it had gone, and the header was worked out from
    nothing, so a page saying "the market has closed since" went out to the edge for a day."""
    from app import main
    c = w["client"]
    main.stock_page_store.mem.clear()
    monkeypatch.setattr(stock_pages, "behind", lambda f, now=None: bool(f.get("price_at")))      # every page a close behind
    first = c.get("/stocks/in/RELIANCE")
    assert "the market has closed since" in first.text and first.headers["cache-control"] == stock_pages.BEHIND_CACHE
    main.stock_page_store.mem.pop("stocks:page:IN:RELIANCE")                                     # the facts' own memory entry ends first
    again = c.get("/stocks/in/RELIANCE")
    assert "the market has closed since" in again.text and again.headers["cache-control"] == stock_pages.BEHIND_CACHE
