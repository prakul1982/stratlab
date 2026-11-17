"""fix13 (LIVE11A, 17-18 Nov 2026): the scored live review of Release 66. Each test fails before its fix and passes after."""
from app import main  # noqa: F401, I001
from app.intel import mood


def _sectors():
    rows = [{"name": f"S{i}", "label": f"Sector {i}", "change_pct": round(1.95 - i * 0.19, 2)} for i in range(16)]
    return {"up": 12, "down": 4, "unchanged": 0, "of": 16, "rows": rows}


def _closed(**kw):
    p = {"region": "IN", "is_open": False, "today": "2026-11-18", "session": "2026-11-17",
         "moves": [{"name": "NIFTY 50", "change_pct": 0.38}, {"name": "SENSEX", "change_pct": 0.52}, {"name": "NIFTY BANK", "change_pct": 1.13}],
         "compare": {"index": "NIFTY 50", "avg_abs": 0.6, "days": 20, "ratio": 0.6, "words": "a smaller move than usual"},
         "breadth": {"group": "NIFTY 500", "live": False, "day": "2026-11-17", "adv": 261, "dec": 238, "unch": 1, "stocks": 500, "pct50": 58.0},
         "sectors": _sectors(), "movers": None,
         "flows": {"as_of": "2026-11-17", "rows": [{"day": "2026-11-17", "fii": 4195, "dii": 197}]},
         "risk": None, "global": None, "calendar": None}
    p.update(kw)
    p["headline"] = mood.headline_of(p["moves"], p["sectors"], p["compare"], mood.same_session(p["breadth"], p["session"]))
    p["lines"] = mood.lines_of(p)
    return p


# ---------- LIVE11A-001: a closed session's re-read never drops a section; its final read is served as it is ----------
def test_a_later_read_of_a_closed_session_keeps_the_sectors_an_earlier_read_had():
    old = _closed(flows={"as_of": "2026-11-16", "rows": [{"day": "2026-11-16", "fii": 4865, "dii": -3519}]})
    assert "12 of 16 sector indices up" in old["headline"]
    new = _closed(sectors=None)                         # 04:35 IST: the broker's quotes off for the night, no sector quotes
    assert "sector" not in new["headline"]
    got = mood.carry_over(old, new)
    assert got["sectors"] == old["sectors"] and "12 of 16 sector indices up" in got["headline"]
    assert any(line.startswith("12 of 16 sector indices rose") for line in got["lines"])
    assert got["flows"]["as_of"] == "2026-11-17"        # the newer flows row the re-read added stays
    assert not mood.verify(got)
    # an older breadth day never replaces a newer one; a read of another session carries nothing
    assert mood.carry_over(old, _closed(breadth={**old["breadth"], "day": "2026-11-16"}))["breadth"]["day"] == "2026-11-17"
    assert mood.carry_over(old, _closed(session="2026-11-18", sectors=None))["sectors"] is None
    assert mood.carry_over({**old, "is_open": True}, new)["sectors"] is None


def test_the_final_read_of_a_closed_session_is_served_without_a_read_on_visit(monkeypatch):
    from app.intel import company
    m = mood.Mood(hub=None)
    m._seeded.add("IN")
    final = _closed()
    assert mood.is_final(final) and mood.missing_parts(final) == []
    m.payloads.put("IN", final, 0.0)                     # read long ago: past every freshness limit
    monkeypatch.setattr(m, "_session_now", lambda region: "2026-11-17")
    monkeypatch.setattr(company, "market_open", lambda region, now=None: False)
    monkeypatch.setattr(m, "_build_kept", lambda region, force=False: (_ for _ in ()).throw(AssertionError("read again on a visit")))
    got, at = m.get("IN", wait=0)
    assert got["final"] is True and not got.get("refreshing") and got["sectors"] == final["sectors"] and at == 0.0


def test_a_read_that_is_not_final_yet_is_read_again_and_keeps_every_section(monkeypatch):
    m = mood.Mood(hub=None)
    m._seeded.add("IN")
    early = _closed(breadth={"group": "NIFTY 500", "live": True, "day": "2026-11-17", "adv": 261, "dec": 238, "unch": 1, "stocks": 500})
    assert "breadth of 2026-11-17" in mood.missing_parts(early)[0]          # the live round, not the evening's count
    m.payloads.put("IN", early, 0.0)
    monkeypatch.setattr(m, "build", lambda region: _closed(sectors=None))
    monkeypatch.setattr(m, "_keep", lambda region, value: None)
    got = m._build_kept("IN")
    assert got["sectors"] == early["sectors"] and got["final"] is True and got["carried"] == ["sectors"]


# ---------- LIVE11A-002: the US read waits for the breadth count of the session that closed ----------
def test_the_after_close_read_is_done_only_with_that_sessions_breadth(monkeypatch):
    from app import mood_job
    from app.intel import routes
    behind = _closed(region="US", breadth={"group": "S&P 500", "live": False, "day": "2026-11-16", "adv": 145, "dec": 353, "unch": 2, "stocks": 500})
    assert mood.tables_of(behind) == "2026-11-17 without that session's breadth count"

    class Hub:
        def __init__(self, value):
            self.value, self.reads = value, 0
            self.payloads = mood.Mood(hub=None).payloads

        def refresh_now(self, region):
            self.reads += 1
            self.payloads.put(region, self.value)
            return self.value
    hub = Hub(behind)
    monkeypatch.setattr(routes, "mood_hub", lambda: hub)
    hub.payloads.put("US", behind)
    assert mood_job._mood_payload("US", "2026-11-17") != "2026-11-17" and hub.reads == 1     # read again, not done
    hub.value = _closed(region="US", breadth={**behind["breadth"], "day": "2026-11-17", "adv": 75, "dec": 424})
    assert mood_job._mood_payload("US", "2026-11-17") == "2026-11-17" and hub.reads == 2
    assert mood_job._mood_payload("US", "2026-11-17") == "2026-11-17" and hub.reads == 2      # kept and complete: no read


# ---------- LIVE11A-015: a price both cards show is at its newest close on both ----------
def test_a_price_both_markets_show_is_at_its_newest_close_on_both():
    ten = {"label": "US 10-year yield", "symbol": "^TNX", "tag": "yield", "price": 5.12, "change_pct": -0.6, "day": "2026-11-16", "same_day": False, "change_bp": -3}
    vix = {"label": "India VIX", "symbol": "^INDIAVIX", "tag": "vol", "price": 15.52, "change_pct": 1.0, "day": "2026-11-17", "same_day": True}
    india = _closed(risk={"rows": [vix, ten]})
    us = {"risk": {"rows": [{**ten, "price": 5.10, "change_bp": -2, "change_pct": -0.4, "day": "2026-11-17"}]}}
    got = mood.newest_rows(india, us)
    assert got["risk"]["rows"][1]["price"] == 5.10 and got["risk"]["rows"][1]["day"] == "2026-11-17" and got["risk"]["rows"][0] == vix
    assert mood.newest_rows(india, {"risk": {"rows": [{**ten, "day": "2026-11-13"}]}})["risk"]["rows"][1]["price"] == 5.12


# ---------- LIVE11A-006: listing prices from the listing day's bhavcopy; every latest close the newest official one, dated ----------
def test_a_stored_listing_price_from_a_later_candle_is_not_shown(monkeypatch):
    from datetime import datetime, timezone
    from app import ipo
    monkeypatch.setattr(ipo, "_official", lambda sym, d, now, fetch: None)
    row = {"market": "IN", "symbol": "VPFL", "listing": "2026-11-09", "price": 94.0,
           "perf": {"issue_price": 94.0, "listing_price": 76.65, "listing_change_pct": -18.46, "day_close": 76.65, "day_change_pct": -18.46,
                    "latest": 69.25, "latest_date": "2026-11-17", "change_pct": -26.33, "listed": "2026-11-13", "basis": "prices"}}
    out = ipo.list_row(row, datetime(2026, 11, 17, 22, 0, tzinfo=timezone.utc))
    assert "listing_price" not in out["perf"] and out["perf"]["latest"] == 69.25


def test_the_listing_days_bhavcopy_gives_the_listing_price(monkeypatch):
    from datetime import datetime, timezone
    from app import exchange_days, ipo, official_close
    text = ("TradDt,TckrSymb,SctySrs,OpnPric,HghPric,LwPric,ClsPric,LastPric,PrvsClsgPric\n"
            "2026-11-09,VPFL,ST,94.00,95.00,88.00,89.30,89.30,94.00\n")
    assert exchange_days.cash_rows(text)["VPFL"]["open"] == 94.0
    reads = []
    monkeypatch.setattr(official_close, "_src", {**official_close._src, "files": lambda: "files"})
    monkeypatch.setattr(exchange_days, "cash_closes", lambda files, day: reads.append(day) or exchange_days.cash_rows(text))
    monkeypatch.setattr(ipo, "_official", lambda sym, d, now, fetch: None)
    now = datetime(2026, 11, 17, 14, 40, tzinfo=timezone.utc)
    row = {"market": "IN", "symbol": "VPFL", "listing": "2026-11-09", "price": 94.0}
    assert ipo.listing_day_prices(row, now) == {"day": "2026-11-09", "open": 94.0, "close": 89.3}
    assert ipo.listing_day_prices(row, now)["open"] == 94.0 and len(reads) == 1           # kept on the row: read once
    got = ipo.with_listing_day(row, {"issue_price": 94.0, "listing_price": 76.65, "latest": 69.25, "latest_date": "2026-11-17",
                                     "change_pct": -26.33, "listed": "2026-11-09", "basis": "prices"})
    assert got["listing_price"] == 94.0 and got["listing_change_pct"] == 0.0 and got["day_close"] == 89.3 and got["latest"] == 69.25
    # a pass reads at most its budget of listing days
    budget = [0]
    assert ipo.listing_day_prices({"market": "IN", "symbol": "X", "listing": "2026-11-05"}, now, budget) is None and len(reads) == 1


def test_a_main_board_rows_latest_close_is_the_newest_official_close_with_its_date(monkeypatch):
    from datetime import datetime, timezone
    from app import ipo
    closes = {("BCSSL", "2026-11-17"): 83.41}
    monkeypatch.setattr(ipo, "_official", lambda sym, d, now, fetch: closes.get((sym, d)))
    row = {"market": "IN", "symbol": "BCSSL", "listing": "2026-11-05", "price": 82.0,
           "perf": {"issue_price": 82.0, "listing_price": None, "day_close": None, "latest": 89.88, "latest_date": None, "change_pct": 9.61,
                    "listed": "2026-11-05", "basis": "exchange"}}
    out = ipo.list_row(row, datetime(2026, 11, 17, 22, 0, tzinfo=timezone.utc))
    assert out["perf"]["latest"] == 83.41 and out["perf"]["latest_date"] == "2026-11-17" and out["perf"]["change_pct"] == 1.72


# ---------- LIVE11A-013: the app's "Ready to open" lists every stored theme the public pages list ----------
def test_the_theme_library_lists_every_stored_theme_with_nothing_typed(monkeypatch):
    from app import computed
    from app.intel import theme_base, theme_library
    R = theme_base.RULES
    entries = {f"h{i}": {"region": "IN", "label": f"Theme {i}", "hits": i, "meta": {"q": f"theme {i}", "rules": R if i % 2 else R - 1, "generated_at": 1.7e9}}
               for i in range(9)}
    entries["old"] = {"region": "IN", "label": "Theme 3", "hits": 0, "meta": {"q": "theme 3", "rules": R - 2, "generated_at": 1.6e9}}
    entries["us"] = {"region": "US", "label": "Chips", "hits": 0, "meta": {"q": "chips", "rules": R, "generated_at": 1.7e9}}
    entries["new"] = {"region": "IN", "label": "Later", "hits": 0, "meta": {"q": "later", "rules": R + 1, "generated_at": 1.7e9}}
    monkeypatch.setattr(computed, "index", lambda kind: {"entries": entries})
    got = theme_library.suggest("IN", "")
    assert sorted(r["name"] for r in got) == [f"Theme {i}" for i in range(9)]           # old-rules maps too, one each; none newer than the rules
    assert len(theme_library.suggest("IN", "theme")) == 8                                # typed: the first few


# ---------- LIVE11A-019: a stored US row's fiscal quarter is said as one ----------
def test_a_stored_us_results_row_says_its_quarter_is_fiscal(monkeypatch):
    import json
    from app import results
    rows = [{"region": "US", "symbol": "WSM", "date": "2026-11-19", "purpose": "Quarterly results (Q3 2027)"},
            {"region": "IN", "symbol": "TCS", "date": "2026-11-19", "purpose": "Quarterly results (Q3 2027)"}]
    monkeypatch.setattr(results.db, "get_setting", lambda k: json.dumps({"rows": rows}))
    got = results.load("US")["rows"]
    assert got[0]["purpose"] == "Quarterly results (fiscal Q3 2027)" and got[1]["purpose"] == "Quarterly results (Q3 2027)"


# ---------- LIVE11A-004: a theme's prices answer within a few seconds; the companies not read in time are read behind the request ----------
def test_theme_prices_answer_at_once_and_the_rest_are_read_behind(monkeypatch):
    import time as _time
    from app.intel import theme_routes as T
    T.PRICE_CACHE.clear()
    T._behind.clear()
    monkeypatch.setattr(T, "PRICE_BEHIND", True)
    monkeypatch.setattr(T.price_reads, "hit", lambda *a, **k: True)
    bars = [{"t": f"2026-11-{d:02d}", "c": 100.0 + d} for d in range(2, 18)]

    def slow(sym):
        _time.sleep(0.4)                       # a busy price source: 40 companies would take 16 s inside the request
        return bars

    def no_bench():
        raise RuntimeError("offline")
    members = [(f"S{i}", f"S{i}") for i in range(40)]
    t0 = _time.monotonic()
    out = T.gather_prices("US", members, slow, no_bench, daily=({}, None, {}))
    assert _time.monotonic() - t0 < T.PRICE_BUDGET + 1.5 and out["pending"] > 0
    deadline = _time.monotonic() + 30
    while _time.monotonic() < deadline and any(T.PRICE_CACHE.get(f"US:{s}") is None for s, _ in members):
        _time.sleep(0.2)
    assert all(T.PRICE_CACHE.get(f"US:{s}") is not None for s, _ in members)       # read behind it, one worker
    assert T.gather_prices("US", members, slow, no_bench, daily=({}, None, {}))["pending"] == 0
    T.PRICE_CACHE.clear()


# ---------- LIVE11A-007: the sector chart is made with the session that just closed, not only three hours after India's close ----------
def test_the_india_sector_chart_is_behind_once_the_session_has_closed(monkeypatch):
    from datetime import datetime, timedelta, timezone
    from app import main as M
    from app.data import calendar
    monkeypatch.setattr(calendar, "is_trading_day", lambda region, d: d.weekday() < 5)
    ist = timezone(timedelta(hours=5, minutes=30))
    at = lambda h, m=0: datetime(2026, 11, 17, h, m, tzinfo=ist)        # noqa: E731
    v = M.rotation.VERSION
    assert M.rotation_day("IN", at(15, 50)) == "2026-11-17" and M.rotation_day("IN", at(15, 35)) == "2026-11-16"
    assert M.rotation_behind({"as_of": "2026-11-16", "v": v}, "IN", at(16, 0)) is True       # before: current until 18:30 IST
    assert M.rotation_behind({"as_of": "2026-11-17", "v": v, "settled": False}, "IN", at(17, 0)) is False
    assert M.rotation_behind({"as_of": "2026-11-17", "v": v, "settled": False}, "IN", at(19, 0)) is True     # once more, settled
    assert M.rotation_behind({"as_of": "2026-11-17", "v": v, "settled": True}, "IN", at(19, 0)) is False
    assert M.rotation_behind({"as_of": "2026-11-17", "v": v}, "IN", at(19, 0)) is False                      # a copy kept before this


# ---------- LIVE11A-017: a public theme page's revenue keeps its value and period together in a phone's stacked row ----------
def test_public_theme_revenue_value_and_period_are_one_box(monkeypatch):
    import re
    from tests.test_review_live10a import _theme_view
    _, page = _theme_view(monkeypatch, {"BIG": (12_345.0, "Mar 2026", "₹ crore")})
    cell = re.search(r'<td data-label="Revenue">(.*?)</td>', page).group(1)
    assert cell.startswith("<span>") and cell.endswith("</span>") and "Mar 2026" in cell     # one flex item beside the label


# ---------- LIVE11A-023: US names in one punctuation ----------
def test_us_names_end_in_one_punctuation():
    from app.results import display_name
    assert [display_name("US", n) for n in ("Apple Inc.", "Amazon.com Inc", "Meta Platforms, Inc.", "MICROSOFT CORP")] == \
        ["Apple Inc", "Amazon.com Inc", "Meta Platforms Inc", "Microsoft Corp"]
    assert display_name("IN", "Larsen & Toubro Ltd.") == "Larsen & Toubro Ltd."          # India's names as the exchange lists them
