"""Market movers: the daily breadth run keeping each stock's last day and 52-week marks beside the heatmap's rows (no second read), the
lists worked out by hand from stored rows (gainers, losers, most traded, volume spikes, 52-week highs and lows), a stock with no candle on
the close's day left out, the smallest market value, the route's inputs and sign-in, and the public page per market with its links,
its address and its place in the sitemap. Facts only, no data source named."""
import json

import pytest

from app import breadth, db, heatmap, movers, screens
from tests import world as W
from tests.fake_db import headers
from tests.test_breadth import ADVICE, IST_OPEN, LAST, PROVIDERS, bars, market, mem, runner  # noqa: F401  (mem is a fixture)

DAY = "2026-10-27"


@pytest.fixture(autouse=True)
def fresh():
    heatmap.clear()
    movers.clear()
    yield
    heatmap.clear()
    movers.clear()


@pytest.fixture
def w(monkeypatch):
    world = W.build(monkeypatch)
    yield world
    world["close"]()


# ---------- the daily run ----------
def test_the_breadth_run_keeps_each_stocks_last_day_and_52_week_marks_with_no_extra_read(mem):
    calls = []
    out = runner(calls=calls).run("IN", IST_OPEN)
    assert out["ok"] and len(calls) == 3                        # one read a stock, as before: the marks come from the same candles
    doc = json.loads(mem[movers.KEY + "IN"])
    assert doc["day"] == LAST and set(doc["stocks"]) == {"UP", "DOWN", "FLAT"}
    up, down, flat = doc["stocks"]["UP"], doc["stocks"]["DOWN"], doc["stocks"]["FLAT"]
    # UP rises by 1 a day to 999: its last day is a new 52-week high, its range the last 251 sessions (749 to 999)
    assert up == [LAST, 999.0, 749.0, 1, 0]
    # DOWN falls by 1 a day to 101: a new 52-week low
    assert down == [LAST, 351.0, 101.0, 0, 1]
    # FLAT sits at 100 and jumps to 105 on the last day: above every high of the year before
    assert flat == [LAST, 105.0, 100.0, 1, 0]


def test_a_movers_problem_never_costs_the_breadth_counts_or_the_heatmap(mem, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("no")
    monkeypatch.setattr(movers, "save_marks", boom)
    out = runner().run("IN", IST_OPEN)
    assert out["ok"] and out["groups"]["nifty500"]["stocks"] == 3
    assert heatmap.KEY + "IN" in mem and movers.KEY + "IN" not in mem


def test_mark_row_needs_flags_and_reads_a_short_history_as_no_range():
    f = breadth.stock_flags(bars([100.0, 101.0, 102.0]))
    base = breadth.base_row(bars([100.0, 101.0, 102.0]))
    assert movers.mark_row(f, base) == [LAST, None, None, 0, 0]        # under a year of sessions: no range, no new high or low
    assert movers.mark_row(None, base) is None


# ---------- the lists ----------
def store(rows: dict, marks: dict | None = None, group="nifty500", region="IN", caps: dict | None = None, mark_day=DAY):
    """Stored heatmap rows ([close, 1d, 1w, 1m, 3m, ytd, 1y, volume, 20-session average]), marks, the group's members and the screens'
    names and market values."""
    heatmap.save(region, DAY, rows, {})
    if marks is not None:
        movers.save_marks(region, mark_day, marks)
    db.set_setting(breadth.MEMBERS_KEY + group, json.dumps(list(rows)))
    caps = caps or {}
    index = [{"symbol": s, "name": f"{s} Ltd", "sector": "Energy", "market_cap": caps.get(s, 1000.0)} for s in rows]
    db.set_setting(screens.INDEX_KEY + region, json.dumps({"at": DAY + "T12:00:00+00:00", "rows": index}))
    with screens._mem_lock:
        screens._mem.clear()


def row(close, chg, vol, avg):
    return [close, chg, 0.0, 0.0, 0.0, 0.0, 0.0, vol, avg]


def five():
    return {
        "AAA": row(100.0, 8.0, 5000.0, 1000.0),       # the top gainer, 5x its volume, value traded 500,000
        "BBB": row(50.0, 2.0, 30000.0, 20000.0),      # value traded 1,500,000: the most traded
        "CCC": row(200.0, -6.0, 1000.0, 2000.0),      # the top loser, under its average volume
        "DDD": row(10.0, -1.0, 100.0, None),          # no average: never a volume spike
        "EEE": row(30.0, 0.0, 0.0, 500.0),            # unchanged, no trade: on no list but the 52-week ones it may be in
    }


def test_each_list_is_sorted_by_its_own_figure(w):
    marks = {"AAA": [DAY, 100.0, 60.0, 1, 0], "BBB": [DAY, 60.0, 40.0, 0, 0], "CCC": [DAY, 300.0, 200.0, 0, 1],
             "DDD": [DAY, 20.0, 10.0, 0, 1], "EEE": [DAY, 40.0, 25.0, 0, 0]}
    store(five(), marks)
    v = w["client"].get("/invest/movers?market=IN", headers=headers("basic-token")).json()
    assert v["as_of"] == DAY and v["pending"] is False and v["marks"] is True and v["universe"] == "nifty500"
    L = {k: [r["s"] for r in x["rows"]] for k, x in v["lists"].items()}
    assert L["gainers"] == ["AAA", "BBB"] and L["losers"] == ["CCC", "DDD"]
    assert L["traded"] == ["BBB", "AAA", "CCC", "DDD"]                    # 1,500,000; 500,000; 200,000; 1,000 (EEE traded nothing)
    assert L["spikes"] == ["AAA", "BBB"]                                  # 5x and 1.5x; CCC is under its average, DDD has none
    assert L["highs"] == ["AAA"] and L["lows"] == ["CCC", "DDD"]          # the largest fall first
    assert v["lists"]["gainers"]["total"] == 2 and v["matching"] == 5
    a = v["lists"]["gainers"]["rows"][0]
    assert a == {"s": "AAA", "n": "AAA Ltd", "cap": 1000.0, "px": 100.0, "chg": 8.0, "vol": 5000.0, "avg": 1000.0, "vx": 5.0, "tv": 500000,
                 "hi": 100.0, "lo": 60.0}
    text = json.dumps(v)
    assert not PROVIDERS.search(text) and not ADVICE.search(text)


def test_a_stock_with_no_candle_on_the_closes_day_is_left_out(w):
    marks = {s: [DAY, 1.0, 1.0, 0, 0] for s in five()}
    marks["AAA"] = ["2026-10-20", 100.0, 60.0, 1, 0]                       # suspended since the 20th: its "change" is a week old
    store(five(), marks)
    v = w["client"].get("/invest/movers?market=IN", headers=headers("basic-token")).json()
    assert "AAA" not in [r["s"] for k in movers.LISTS for r in v["lists"][k]["rows"]]
    assert v["with_prices"] == 4 and v["members"] == 5


def test_before_the_marks_of_the_same_day_the_52_week_lists_are_empty_and_say_so(w):
    store(five(), {"AAA": ["2026-10-26", 100.0, 60.0, 1, 0]}, mark_day="2026-10-26")      # the day before's marks
    v = w["client"].get("/invest/movers?market=IN", headers=headers("basic-token")).json()
    assert v["marks"] is False and v["lists"]["highs"]["rows"] == [] and v["lists"]["lows"]["rows"] == []
    assert [r["s"] for r in v["lists"]["gainers"]["rows"]] == ["AAA", "BBB"]            # the rest still shows, no day's mark to filter by


def test_the_smallest_market_value_and_the_top_rows(w, monkeypatch):
    store(five(), {}, caps={"AAA": 50.0, "BBB": 9000.0, "CCC": 20000.0, "DDD": 7000.0, "EEE": 10.0})
    c, h = w["client"], headers("basic-token")
    v = c.get("/invest/movers?market=IN&min_cap=5000", headers=h).json()
    assert v["matching"] == 3 and [r["s"] for r in v["lists"]["gainers"]["rows"]] == ["BBB"] and v["min_cap"] == 5000
    monkeypatch.setattr(movers, "TOP", 1)
    movers.clear()
    v = movers.view("IN", None, None, movers.TOP)
    assert [r["s"] for r in v["lists"]["traded"]["rows"]] == ["BBB"] and v["lists"]["traded"]["total"] == 4


def test_before_the_first_run_the_page_says_pending_and_every_group_is_offered(w):
    v = w["client"].get("/invest/movers?market=US", headers=headers("basic-token")).json()
    assert v["pending"] is True and v["universe"] == "sp500" and v["as_of"] is None
    assert [u["id"] for u in v["universes"]] == list(heatmap.UNIVERSES["US"])
    assert all(v["lists"][k] == {"total": 0, "rows": []} for k in movers.LISTS)


def test_free_gets_the_top_5_of_the_default_index_whatever_it_asks_for_and_basic_gets_everything(w):
    rows = {f"S{i:02d}": row(100.0, 1.0 + i, 1000.0 * (i + 1), 500.0) for i in range(12)}
    store(rows, {s: [DAY, 1.0, 1.0, 1, 0] for s in rows}, caps={s: 1000.0 * (i + 1) for i, s in enumerate(rows)})
    c = w["client"]
    free = c.get("/invest/movers?market=IN&universe=nifty50&min_cap=5000", headers=headers("free-token")).json()
    assert free["locked"] is True and free["plan"] == "Basic"
    assert free["universe"] == "nifty500" and free["min_cap"] is None and free["top"] == movers.TEASER      # the filters wait for Basic
    assert all(len(free["lists"][k]["rows"]) <= 5 for k in movers.LISTS)
    assert [r["s"] for r in free["lists"]["gainers"]["rows"]] == ["S11", "S10", "S09", "S08", "S07"] and free["lists"]["gainers"]["total"] == 12
    assert len(free["lists"]["highs"]["rows"]) == 5                       # the 52-week lists too: their top 5 only
    full = c.get("/invest/movers?market=IN&min_cap=5000", headers=headers("basic-token")).json()
    assert full["locked"] is False and "plan" not in full and full["min_cap"] == 5000 and len(full["lists"]["gainers"]["rows"]) == 8
    assert c.get("/invest/movers?market=IN", headers=headers("pro-token")).json()["locked"] is False
    from app import plans
    assert plans.FEATURE_PLAN["movers"] == "basic" and "movers" in plans.FEATURES


def test_bad_input_and_sign_in(w):
    c, h = w["client"], headers("basic-token")
    assert c.get("/invest/movers?market=XX", headers=h).status_code == 400
    assert c.get("/invest/movers?market=IN&universe=sp500", headers=h).status_code == 404
    assert c.get("/invest/movers?market=IN&min_cap=-1", headers=h).status_code == 400
    assert c.get("/invest/movers?market=IN").status_code == 401


def test_one_answer_is_shared_until_the_next_run_stores_new_marks(w, monkeypatch):
    store(five(), {})
    c, h = w["client"], headers("basic-token")
    calls = []
    real = movers.view
    monkeypatch.setattr(movers, "view", lambda *a, **k: calls.append(a) or real(*a, **k))
    for _ in range(3):
        c.get("/invest/movers?market=IN", headers=h)
    assert len(calls) == 1
    movers.save_marks("IN", DAY, {"AAA": [DAY, 100.0, 60.0, 1, 0]})
    assert [r["s"] for r in c.get("/invest/movers?market=IN", headers=h).json()["lists"]["highs"]["rows"]] == ["AAA"] and len(calls) == 2


# ---------- the public page ----------
def test_the_public_page_lists_each_market_with_links_to_company_pages(w, monkeypatch):
    from app import stock_pages
    store(five(), {s: [DAY, 1.0, 1.0, 0, 0] for s in five()} | {"AAA": [DAY, 100.0, 60.0, 1, 0]})
    monkeypatch.setattr(stock_pages, "companies", lambda region: {"AAA": {"name": "AAA Ltd"}} if region == "IN" else {})
    r = w["client"].get("/stocks/in/movers")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
    assert "s-maxage" in r.headers["cache-control"]
    html = r.text
    assert "<h1>India market movers</h1>" in html and "27 Oct 2026" in html
    for k, title in movers.TITLES.items():
        assert f'<h2 id="{k}">{title}</h2>' in html
    assert '<a href="/stocks/in/AAA">AAA Ltd' in html                    # a company with a public page is linked to it
    assert '<a href="/stocks/in/BBB"' not in html                         # ...one without is named, not linked to a missing page
    assert "on the Basic plan" in html and "/invest/movers?region=IN" in html   # a teaser: the full lists are Basic
    assert 'rel="canonical" href="' in html and "/stocks/in/movers" in html
    assert '/status">Data status</a>' in html                           # the footer's way to the data status page
    assert not PROVIDERS.search(html) and not ADVICE.search(html)
    assert w["client"].get("/stocks/IN/movers", follow_redirects=False).status_code == 301
    assert w["client"].get("/stocks/xx/movers").status_code == 404
    us = w["client"].get("/stocks/us/movers")
    assert us.status_code == 200 and "<h1>US market movers</h1>" in us.text and "fill in after the next market close" in us.text


def test_the_sitemap_lists_the_movers_pages_and_the_data_status_page(w):
    store(five(), {})
    xml = w["client"].get("/sitemaps/pages.xml").text
    assert "/stocks/in/movers</loc><lastmod>2026-10-27</lastmod>" in xml and "/stocks/us/movers</loc>" in xml and "/status</loc>" in xml


def test_the_public_page_shows_only_the_top_5_of_each_list(w):
    rows = {f"S{i:02d}": row(100.0, 1.0 + i, 1000.0, 500.0) for i in range(12)}
    store(rows, {s: [DAY, 1.0, 1.0, 0, 0] for s in rows})
    html = w["client"].get("/stocks/in/movers").text
    gainers = html.split('<h2 id="gainers">')[1].split("<h2")[0]
    assert gainers.count("<tr>") == 1 + 5 and "The top 5 of 12." in gainers      # the header row and five
