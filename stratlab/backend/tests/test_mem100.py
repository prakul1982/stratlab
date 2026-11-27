"""mem100: memory held between deploys and slow crawled company pages.

- a company page due a rebuild is served its stored copy when the build outlasts BUILD_WAIT (the build finishes behind it, for the next
  view), builds run on at most BUILDERS threads, and two views of one page share one build;
- what every company page worked out from the market's whole index (its companies by checked value) is worked out once for the index as
  it is, and again as soon as the index changes;
- a company page reads the results calendar once;
- a theme's dive reads the index's revenues once, not once per company;
- the widths a deck measured are let go once it is made."""
import json
import sys
import threading
import time

import pytest

from app import db, deck, results, screens, stock_pages
from tests import world


@pytest.fixture
def w(monkeypatch):
    built = world.build(monkeypatch)
    yield built
    built["close"]()


def _stored(region, symbol, facts, ts=0):
    db.set_setting(f"stocks:page:{region}:{symbol}", json.dumps({"ts": ts, "facts": facts}))


def _in_request():
    return db._in_request.set(True)


def test_a_view_due_a_slow_rebuild_gets_the_stored_copy_and_the_build_finishes_behind_it(w, monkeypatch):
    monkeypatch.setattr(stock_pages, "BUILD_WAIT", 0.2)
    go, calls = threading.Event(), []
    assert w["client"].get("/stocks/in/RELIANCE").status_code == 200
    old = {**json.loads(db.get_setting("stocks:page:IN:RELIANCE"))["facts"], "price": 1000.0}

    def gather(region, co):
        calls.append(co["sym"])
        go.wait(10)
        return {**old, "price": 2000.0}
    store = stock_pages.Pages(gather, per_minute=10)
    _stored("IN", "RELIANCE", old)                          # a day old: due a rebuild
    co = {"sym": "RELIANCE", "bse": None, "name": "Reliance Industries"}
    token = _in_request()
    try:
        t0 = time.monotonic()
        got = store.get("IN", "RELIANCE", co)
        assert got["price"] == 1000.0 and time.monotonic() - t0 < 5          # the stored copy, after the wait, not the build's end
        page, _ = store.served("IN", "RELIANCE", co)
        assert store.mem.get("html:IN:RELIANCE") is None    # a copy shown while the build goes on is not kept as the page
        assert calls == ["RELIANCE"]                        # one build for both views
        go.set()
        store.inflight and list(store.inflight.values())[0].result(10)
        assert store.get("IN", "RELIANCE", co)["price"] == 2000.0           # the next view: the new build
        assert json.loads(db.get_setting("stocks:page:IN:RELIANCE"))["facts"]["price"] == 2000.0
        assert calls == ["RELIANCE"]
    finally:
        db._in_request.reset(token)
        go.set()


def test_a_page_with_nothing_stored_and_a_job_wait_for_the_whole_build(w, monkeypatch):
    monkeypatch.setattr(stock_pages, "BUILD_WAIT", 0.05)

    def gather(region, co):
        time.sleep(0.4)
        return {"name": co["name"], "price": 5.0, "v": stock_pages.FACTS_VERSION}
    store = stock_pages.Pages(gather, per_minute=10)
    token = _in_request()
    try:
        assert store.get("IN", "TCS", {"sym": "TCS", "bse": None, "name": "TCS"})["price"] == 5.0          # nothing stored to show
    finally:
        db._in_request.reset(token)
    _stored("IN", "INFY", {"name": "Infosys", "price": 1.0, "v": stock_pages.FACTS_VERSION})
    assert store.get("IN", "INFY", {"sym": "INFY", "bse": None, "name": "Infosys"})["price"] == 5.0      # a job (no request): the build


def test_builds_run_on_at_most_builders_threads_at_once(w, monkeypatch):
    monkeypatch.setattr(stock_pages, "BUILDERS", 2)
    now, most, lock = [0], [0], threading.Lock()

    def gather(region, co):
        with lock:
            now[0] += 1
            most[0] = max(most[0], now[0])
        time.sleep(0.2)
        with lock:
            now[0] -= 1
        return {"name": co["name"], "price": 1.0, "v": stock_pages.FACTS_VERSION}
    store = stock_pages.Pages(gather, per_minute=100)
    syms = [f"S{i}" for i in range(6)]
    threads = [threading.Thread(target=store.get, args=("IN", s, {"sym": s, "bse": None, "name": s})) for s in syms]
    [t.start() for t in threads]
    [t.join(10) for t in threads]
    assert most[0] == 2 and all(store.mem.get(f"stocks:page:IN:{s}") for s in syms)


def test_a_failed_build_behind_the_page_keeps_the_stored_copy(w, monkeypatch):
    monkeypatch.setattr(stock_pages, "BUILD_WAIT", 0.05)

    def gather(region, co):
        time.sleep(0.3)
        raise RuntimeError("source down")
    store = stock_pages.Pages(gather, per_minute=10)
    _stored("IN", "SBIN", {"name": "State Bank of India", "price": 7.0, "v": stock_pages.FACTS_VERSION})
    co = {"sym": "SBIN", "bse": None, "name": "State Bank of India"}
    token = _in_request()
    try:
        assert store.get("IN", "SBIN", co)["price"] == 7.0
        list(store.inflight.values())[0].result(5) if store.inflight else None
        assert store.get("IN", "SBIN", co)["price"] == 7.0
        assert json.loads(db.get_setting("stocks:page:IN:SBIN"))["facts"]["price"] == 7.0
    finally:
        db._in_request.reset(token)


def _rows(region):
    return [{"symbol": s, "name": s, "market_cap": cap, "price": 100.0, "price_at": "2026-10-27", "cap_checked": True} for s, cap in
            (("TCS", 1_000_000.0), ("INFY", 600_000.0), ("WIPRO", 300_000.0))]


def test_the_markets_companies_by_value_are_worked_out_once_for_the_index_as_it_is(w, monkeypatch):
    rows = _rows("IN")
    monkeypatch.setattr(stock_pages, "_index_rows", lambda region: rows)
    monkeypatch.setattr(stock_pages, "companies", lambda region, _c={"TCS": {}, "INFY": {}, "WIPRO": {}}: _c)
    checks = []
    real = stock_pages._row_cap
    monkeypatch.setattr(stock_pages, "_row_cap", lambda region, r: checks.append(r["symbol"]) or real(region, r))
    first = stock_pages._sized("IN")
    assert [r["symbol"] for r in first] == ["TCS", "INFY", "WIPRO"]
    n = len(checks)
    assert stock_pages._sized("IN") is first and len(checks) == n          # the second page: nothing worked out again
    rows[2]["market_cap"] = 1_200_000.0                                      # a page's new close, noted by the index in memory
    screens._changed("IN")
    assert [r["symbol"] for r in stock_pages._sized("IN")] == ["WIPRO", "TCS", "INFY"]


def test_a_new_close_noted_by_the_price_job_reorders_the_peers(w):
    index = {"region": "US", "at": "2026-10-27T06:00:00+00:00", "rows": _rows("US")}
    with screens._mem_lock:
        screens._mem["US"] = (time.time(), index)
    before = screens.version("US")
    screens.note_price("US", "WIPRO", {"region": "US", "symbol": "WIPRO", "name": "WIPRO", "price": 999.0, "price_at": "2026-10-28"})
    assert screens.version("US") == before + 1


def test_a_company_page_reads_the_results_calendar_once(w, monkeypatch):
    loads = []
    real = results.load
    monkeypatch.setattr(results, "load", lambda region: loads.append(region) or real(region))
    stock_pages.faq_extras("US", "AAPL")
    assert loads == ["US"]


def test_a_dive_reads_the_indexs_revenues_once_for_all_its_companies(w, monkeypatch):
    from app.intel import routes as R, theme_routes
    rows = [{"symbol": "TCS", "sales": 100.0, "sales_year": "Mar 2026", "sales_unit": "₹ crore"}]
    monkeypatch.setattr(R, "index_rows", lambda region: rows)
    a = theme_routes._index_sales("IN")
    assert theme_routes._index_sales("IN") is a and a["TCS"] == (100.0, "Mar 2026", "₹ crore")
    rows2 = rows + [{"symbol": "INFY", "sales": 50.0, "sales_year": "Mar 2026", "sales_unit": "₹ crore"}]
    monkeypatch.setattr(R, "index_rows", lambda region: rows2)
    assert set(theme_routes._index_sales("IN")) == {"TCS", "INFY"}          # another index: read again


def test_the_widths_a_deck_measured_are_let_go_once_it_is_made():
    deck._measure.cache_clear()
    with deck._one_deck():
        w1 = deck._width("Steel makers turn ore and coal into steel", 12)
        with deck._one_deck():                              # another deck made at the same time
            deck._width("Coal India", 12)
        assert deck._measure.cache_info().currsize == 2     # still being made: kept
        assert deck._width("Steel makers turn ore and coal into steel", 12) == w1
    assert deck._measure.cache_info().currsize == 0
    assert deck._width("Steel makers turn ore and coal into steel", 12) == w1      # the same width when asked again


def test_a_large_value_is_counted_at_least_at_what_it_holds():
    """Fails before: past the 20,000-node walk a value was counted from the part walked, scaled by the walk still waiting: a parsed tree of
    filings holding 12.8 MB counted as 1.7 MB, so the caches of such values held several times their bound."""
    import tracemalloc
    from app.intel import net
    text = json.dumps({"facts": {f"tag{i}": {"units": {"USD": [{"end": f"2024-12-{j % 28 + 1:02d}", "val": 10**6 + i * 40 + j, "fy": 2000 + j,
                                                                  "form": "10-K", "accn": f"0000320193-25-{i * 40 + j:06d}"} for j in range(40)]}}
                                 for i in range(300)}})
    tracemalloc.start()
    value = json.loads(text)
    real, _ = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    n = net.approx_size(value)
    assert real <= n <= 4 * real
    small = [{"t": i, "c": 1.5} for i in range(100)]
    assert net.approx_size(small) == 60 + 8 * 100 + 100 * (100 + 50 * 2 + 2 * 32 + 2 * sys.getsizeof("t"))      # a value walked whole: as before


def test_the_caches_are_brought_under_their_budget_when_they_pass_it_by_a_quarter(monkeypatch):
    from app.intel import net
    a, b = net.TTLCache(max_items=100, max_bytes=10_000_000), net.TTLCache(max_items=100, max_bytes=10_000_000)
    monkeypatch.setattr(net, "caches", lambda: [a, b])
    monkeypatch.setattr(net, "BUDGET", 1_000_000)
    for i in range(5):
        a.set(i, "x" * 200_000, 60)                          # 1.0 MB: within a quarter over
    assert a.bytes > 1_000_000 * 0.9
    b.set("big", "y" * 400_000, 60)                          # 1.4 MB in all: back under the budget at once
    assert a.bytes + b.bytes <= 1_000_000 and b.get("big") is not None


def test_a_rendered_page_is_kept_as_utf8_and_served_as_the_same_text(w, monkeypatch):
    from app import main
    from app.intel import net
    monkeypatch.setattr(net, "BUDGET", 0)                    # the caches other tests filled in this process don't push the page out here
    first = w["client"].get("/stocks/in/TCS")
    kept = main.stock_page_store.mem.get("html:IN:TCS")
    text = kept[0].decode("utf-8")
    assert isinstance(kept[0], bytes) and any(ord(ch) > 255 for ch in text)      # a page with a "₹", "–" or "·" in it
    assert len(kept[0]) < sys.getsizeof(text) * 0.6          # about half the memory of the same page as text
    again = w["client"].get("/stocks/in/TCS")
    assert again.text == first.text and again.headers["cache-control"] == first.headers["cache-control"]
