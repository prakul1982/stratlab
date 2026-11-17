"""LIVE10A (17 Nov 2026): the scored live review of Release 60. Each test fails before its fix and passes after."""
from datetime import datetime, timedelta, timezone

from app import main  # noqa: F401, I001
from app import autofix, mood_job

IST = timezone(timedelta(hours=5, minutes=30))
ET = timezone(timedelta(hours=-5))


def _job(monkeypatch, read=None, mood=None):
    from app.data import calendar
    from app import stock_pages
    monkeypatch.setattr(calendar, "is_trading_day", lambda region, d: d.weekday() < 5)
    monkeypatch.setattr(stock_pages, "settling", lambda region, now=None: None)
    store = {}
    monkeypatch.setattr(mood_job, "db", type("D", (), {"get_setting": staticmethod(store.get),
                                                       "set_setting": staticmethod(lambda k, v: store.__setitem__(k, v))}))
    return mood_job.Job(read or (lambda region: {"mood": "x"}), mood or (lambda region, day: day))


# ---------- LIVE10A-001: the after-close mood read runs on the clock and a late one is seen ----------
def test_india_read_is_tried_once_the_closing_auction_is_done(monkeypatch):
    job = _job(monkeypatch)
    # 16:05 IST on 17 Nov: the reviewer's visit got the 14:47 intraday read; the job now has written the closing read by then
    assert job.tick(datetime(2026, 11, 17, 15, 50, tzinfo=IST).astimezone(timezone.utc)) == {"IN": "written"}
    assert job.tick(datetime(2026, 11, 17, 15, 40, tzinfo=IST).astimezone(timezone.utc)) == {}


def test_a_read_still_not_written_an_hour_after_its_time_is_a_self_healing_check(monkeypatch):
    job = _job(monkeypatch, mood=lambda region, day: "2026-11-13")          # the tables never reach the session that closed
    t = datetime(2026, 11, 16, 16, 45, tzinfo=ET).astimezone(timezone.utc)
    job.tick(t)
    assert job.late("US", t) is None                                        # five minutes in: not late yet
    later = datetime(2026, 11, 16, 17, 45, tzinfo=ET).astimezone(timezone.utc)
    job.tick(later)
    why = job.late("US", later)
    assert why and "2026-11-16" in why and "tables of 2026-11-13" in why
    checks = {c.id: c for c in job.checks(later)}
    assert checks["job:mood-read:US"].problem == why and checks["job:mood-read:US"].fix is not None
    # written: no longer late
    job.mood = lambda region, day: day
    job.tick(later)
    assert job.late("US", later) is None
    # the self-healing sweep lists both markets' checks
    ids = {c.id for src in autofix._sources if src.__module__ == "app.mood_job" for c in src()}
    assert {"job:mood-read:IN", "job:mood-read:US"} <= ids


def test_a_market_hours_copy_served_after_the_close_says_it_was_read_during_the_session(monkeypatch):
    from app.intel import mood
    m = mood.Mood(hub=None)
    m._seeded.add("IN")
    m.payloads.put("IN", {"session": "2026-11-17", "is_open": True, "headline": "x so far today", "lines": []}, 0.0)
    monkeypatch.setattr(m, "_session_now", lambda region: "2026-11-17")
    monkeypatch.setattr(m, "_build_kept", lambda region, force=False: {"session": "2026-11-17", "is_open": False})
    from app.intel import company
    monkeypatch.setattr(company, "market_open", lambda region, now=None: False)
    got, _ = m.get("IN", wait=0)
    assert got["during"] is True and got["is_open"] is False and got["refreshing"] is True


# ---------- LIVE10A-006: /themes cards: the name on its own line, the count line under it, one link per card ----------
def test_theme_directory_cards_put_the_name_above_its_count_line(monkeypatch):
    from app import public_themes as pt, stock_pages
    rows = [{"region": "IN", "slug": "fertilizers-and-agrochemicals", "label": "Fertilizers and agrochemicals", "name": "x", "at": 1763251200}]
    monkeypatch.setattr(pt, "entries", lambda region=None: rows)
    monkeypatch.setattr(pt, "card_line", lambda x: "India · 281 companies · 16 Nov")
    page = pt.directory(None)
    assert ('<ul class="dir" data-cards><li><a href="/themes/in/fertilizers-and-agrochemicals"><span class="nm">Fertilizers and agrochemicals</span>'
            '<span class="muted">India · 281 companies · 16 Nov</span></a></li></ul>') in page
    css = stock_pages.CSS if hasattr(stock_pages, "CSS") else page
    assert "ul.dir[data-cards] a{flex-direction:column" in css


# ---------- LIVE10A-007: public theme pages: revenue from the company pages when the dive isn't kept; no empty column; phone stacks ----------
def _theme_view(monkeypatch, sales):
    from app import public_themes as pt
    payload = {"value_chain": [{"layer": "Makers", "official": True, "companies": [
        {"ticker": "BIG", "name": "Big Ships Ltd", "verified": True, "what": "builds ships"},
        {"ticker": "SMALL", "name": "Small Ships Ltd", "verified": True, "what": "builds ships"}]}]}
    monkeypatch.setattr(pt, "_dive", lambda r, n, p: {})
    monkeypatch.setattr(pt, "_index_caps", lambda r: {"BIG": 90_000.0, "SMALL": 500.0})
    monkeypatch.setattr(pt, "_index_sales", lambda r: sales)
    monkeypatch.setattr(pt, "_price_day", lambda r, syms: "2026-11-16")
    monkeypatch.setattr(pt.stock_pages, "companies", lambda r: set())
    v = pt.view({"region": "IN", "name": "Ships", "label": "Ships", "slug": "ships", "at": None}, payload)
    return v, pt.render(v)


def test_revenue_comes_from_the_company_pages_when_the_theme_dive_is_not_kept(monkeypatch):
    v, page = _theme_view(monkeypatch, {"BIG": (12_345.0, "Mar 2026", "₹ crore")})
    big = next(c for c in v["layers"][0]["companies"] if c["symbol"] == "BIG")
    assert big["revenue"] and big["year"] == "Mar 2026"
    assert '<th scope="col">Revenue</th>' in page and 'data-label="Revenue"' in page


def test_a_page_with_no_revenue_has_no_revenue_column_and_stacks_on_a_phone(monkeypatch):
    _, page = _theme_view(monkeypatch, {})
    assert "Revenue</th>" not in page and 'data-label="Revenue"' not in page
    assert '<div class="cotbl" data-stack>' in page and 'data-label="Market value"' in page
    assert ".cotbl[data-stack] td[data-label]::before{content:attr(data-label)" in page


def test_the_screens_index_row_carries_the_newest_full_years_revenue():
    from app import screens
    f = {"name": "Big Ships", "price": 100.0, "unit": "₹ crore", "price_at": "2026-11-16",
         "years": [{"year": "Mar 2025", "sales": 10_000.0}, {"year": "Mar 2026", "sales": 12_345.0}, {"year": "TTM", "sales": 13_000.0}]}
    r = screens.row("IN", "BIG", f)
    assert (r["sales"], r["sales_year"], r["sales_unit"]) == (12_345.0, "Mar 2026", "₹ crore")


# ---------- LIVE10A-022: the public theme page's title keeps the market's capital ----------
def test_public_theme_title_says_in_india(monkeypatch):
    _, page = _theme_view(monkeypatch, {})
    assert "<title>Ships: listed companies in India by layer · StratLab</title>" in page


# ---------- LIVE10A-008: a kept dive behind a newer close is served at once and read again behind the page ----------
def test_a_stale_kept_dive_is_served_at_once_and_rebuilt_behind_the_page(monkeypatch):
    from app.intel import theme_routes as T, theme_base, sector_metrics
    from app import computed
    kept = {"value": {"dive": {"sector": "Ships", "metrics_pending": []}, "pieces": {}}, "at": "2026-11-16T00:00:00Z"}
    monkeypatch.setattr(theme_base, "for_figures", lambda m: (m, {}))
    monkeypatch.setattr(T, "dive_key", lambda r, t, m: ["IN", "ships", 1])
    monkeypatch.setattr(computed, "get", lambda kind, key, count=True: kept)
    monkeypatch.setattr(T, "pieces_moved", lambda r, p: False)
    monkeypatch.setattr(sector_metrics, "any_stored", lambda r, s: False)
    monkeypatch.setattr(T, "prices_moved", lambda r, k: True)          # a newer close since it was kept
    monkeypatch.setattr(T, "pages_rebuilt", lambda r, d: [])
    monkeypatch.setattr(T, "requeue", lambda r, d: None)
    queued = []
    monkeypatch.setattr(T, "_rebuild_behind", lambda r, t, m, key: queued.append(key) or True)
    monkeypatch.setattr(T, "BEHIND_ON", True)
    got = T.dive_of("IN", "Ships", {}, behind=True)
    assert got["updating"] is True and got["sector"] == "Ships" and queued == [["IN", "ships", 1]]
    # the worker's own read never takes the kept copy
    built = []
    monkeypatch.setattr(T, "sources", lambda r, t, fresh=False: built.append(t) or (_ for _ in ()).throw(RuntimeError("stop")))
    try:
        T.dive_of("IN", "Ships", {}, rebuild=True)
    except RuntimeError:
        pass
    assert built == ["Ships"]


def test_the_behind_queue_takes_a_theme_once_and_is_bounded(monkeypatch):
    from app.intel import theme_routes as T
    ran = []
    monkeypatch.setattr(T, "_BEHIND", type("P", (), {"submit": staticmethod(lambda fn: ran.append(fn))})())
    monkeypatch.setattr(T, "_behind_keys", set())
    assert T._rebuild_behind("IN", "Ships", {}, ["IN", "ships", 1]) is True
    assert T._rebuild_behind("IN", "Ships", {}, ["IN", "ships", 1]) is True and len(ran) == 1      # one read per theme at a time
    for i in range(T.BEHIND_MAX - 1):
        T._rebuild_behind("IN", f"T{i}", {}, ["IN", f"t{i}", 1])
    assert T._rebuild_behind("IN", "More", {}, ["IN", "more", 1]) is False                         # full: the page reads it itself


# ---------- LIVE10A-011: a kept rotation chart a close behind is served at once and worked out behind the page ----------
def test_a_rotation_copy_a_close_behind_is_served_at_once(monkeypatch):
    import json as _json
    from datetime import date as _date
    from fastapi.testclient import TestClient
    from app import db as _db
    from tests.fake_db import FakeSupabase
    monkeypatch.setattr(_db, "_client", FakeSupabase())
    monkeypatch.setattr(main.markets, "provider", lambda r: type("P", (), {"ready": lambda self: True})())
    monkeypatch.setattr(main.stock_pages, "last_close", lambda r, now=None: (_date(2026, 11, 16), None))
    monkeypatch.setattr(main, "heavy_read_throttle", lambda p: None)
    monkeypatch.setattr(main, "ROTATION_BEHIND", True)
    queued = []
    monkeypatch.setattr(main, "_rotation_pool", type("P", (), {"submit": staticmethod(lambda fn: queued.append(fn))})())
    monkeypatch.setattr(main, "_rotation_busy", set())
    monkeypatch.setattr(main.rotation, "run", lambda *a, **k: (_ for _ in ()).throw(AssertionError("read inside the request")))
    main._results.clear()
    _db.set_setting("rotation:last:US:sectors:weekly:5", _json.dumps({"rows": [{"kept": 1}], "skipped": [], "as_of": "2026-11-13", "v": main.rotation.VERSION}))
    main.app.dependency_overrides[main.current_profile] = lambda: {"id": "u1", "plan": "pro", "_plan": "pro"}
    try:
        v = TestClient(main.app).get("/research/rotation?region=US").json()
        assert v["rows"] == [{"kept": 1}] and v["updating"] is True and len(queued) == 1
    finally:
        main.app.dependency_overrides.clear()
        main._results.clear()


# ---------- LIVE10A-020: each results day says whether it is a session of the market ----------
def test_results_days_say_whether_they_are_sessions(monkeypatch):
    from app import results
    from app.data import calendar
    monkeypatch.setattr(calendar, "is_trading_day", lambda region, d: d.weekday() < 5 and d.isoformat() != "2026-11-26")
    assert results._session_day("US", "2026-11-19") is True
    assert results._session_day("US", "2026-11-22") is False and results._session_day("US", "2026-11-26") is False


# ---------- LIVE10A-038: heatmap and movers names in the one style ----------
def test_heatmap_and_movers_names_are_in_one_style():
    from app import heatmap, movers
    row = [100.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 1000.0, 900.0]
    assert heatmap.tile("TSN", row, {"name": "TYSON FOODS, INC."}, None, "US")["n"] == "Tyson Foods, Inc."
    assert heatmap.tile("MSFT", row, {"name": "MICROSOFT CORP"}, None, "US")["n"] == "Microsoft Corp"
    assert heatmap.tile("TSN", row, {"name": "TYSON FOODS, INC."}, None)["n"] == "TYSON FOODS, INC."      # no market given: as stored
    assert movers.row_of("CNC", row, {"name": "CENTENE CORP"}, None, "US")["n"] == "Centene Corp"


# ---------- LIVE10A-029: a placeholder symbol is no member of a breadth group ----------
def test_breadth_members_leave_out_exchange_placeholders(monkeypatch):
    import json as _json
    from app import breadth
    store = {}
    monkeypatch.setattr(breadth, "db", type("D", (), {"get_setting": staticmethod(store.get), "set_setting": staticmethod(lambda k, v: store.__setitem__(k, v)),
                                                      "json_value": staticmethod(lambda v, d: _json.loads(v) if v else d)}))
    names = [f"S{i}" for i in range(breadth.MIN_MEMBERS)] + ["DUMMYSAN"]
    got = breadth.members("nifty500", index_members=lambda n: names)
    assert "DUMMYSAN" not in got and len(got) == breadth.MIN_MEMBERS
    store[breadth.MEMBERS_KEY + "nifty500"] = _json.dumps(names)
    assert "DUMMYSAN" not in breadth.members("nifty500", index_members=lambda n: [])
