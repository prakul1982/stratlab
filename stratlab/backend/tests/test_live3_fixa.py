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


# ---------- LIVE3-018: one rule for a ratio ----------
def test_debt_to_equity_reads_the_same_on_the_public_page_and_the_app_for_every_size():
    from app.intel import key_facts
    for v, want in ((0.0016, "<0.01"), (0.0, "0.00"), (0.21, "0.21"), (1.4699, "1.47"), (-0.002, "−<0.01"), (12.5, "12.50")):
        assert stock_pages.ratio_text(v) == want
        row = key_facts.debt_and_cash({}, None, {"years": []}, {"debt_equity": v})
        assert row["items"][0]["text"] == want, (v, row)
        # the public page's own table of figures
        shown = dict(stock_pages._stats(dict(us(symbol="HAL", debt_equity=v))))
        assert shown["Debt to equity"].startswith(want), (v, shown["Debt to equity"])


# ---------- LIVE3-004 / LIVE3-005: a length said in days stays days; the name is true of what runs ----------
from app import ai_writer  # noqa: E402


def _ai_answer(entry=(), exit_=(), tf=None, name="Idea", instrument=None):
    return {"name": name, "instrument": instrument, "market": "IN" if instrument else None, "tf": tf, "side": "long", "entryJoin": "all",
            "entry": list(entry), "exit": list(exit_), "risk": {}, "mentioned": ["exit"], "notes": []}


PX = {"t": "price"}


def test_the_reviewers_sentence_runs_a_200_day_average_on_daily_closes_with_15_minute_trades_and_says_so():
    words = "go long when price closes above the 200 day moving average, exit when it closes back under it, 15 minute candles on BANKNIFTY"
    ai = _ai_answer([{"l": PX, "op": "gt", "r": {"t": "sma", "p": 200}}], [{"l": PX, "op": "lt", "r": {"t": "sma", "p": 200}}],
                    tf="15m", name="BankNifty 200 EMA Long", instrument="BANKNIFTY")
    got = ai_writer.check_against_text(ai, words)
    day200 = {"t": "sma", "p": 200, "tf": "1d"}
    assert got["entry"] == [{"l": PX, "op": "gt", "r": day200}] and got["exit"] == [{"l": PX, "op": "lt", "r": day200}] and got["tf"] == "15m"
    assert "The 200-day SMA is worked out on daily candles (each completed day's close); the trades are on 15-minute candles." in got["assumed"]
    assert any("SMA 200 on daily candles" in n for n in got["notes"])
    assert got["name"] == "BANKNIFTY SMA 200 daily"                      # no "EMA": the name is made from the rules that run


@pytest.mark.parametrize("tf", ["5m", "15m", "1h"])
@pytest.mark.parametrize("said,unit_days", [("200 day moving average", 200), ("200-day average", 200), ("200 DMA", 200), ("200d sma", 200),
                                            ("50 day EMA", 50), ("20 week moving average", 100), ("10-week EMA", 50)])
def test_every_day_or_week_length_on_intraday_candles_runs_on_daily_candles(said, unit_days, tf):
    words = f"buy when price closes above the {said}, sell when it closes back under it, {idea_tf(tf)} candles"
    got = ai_writer.check_against_text(_ai_answer(tf=None), words)
    assert got["tf"] == tf
    ref = got["entry"][0]["r"]
    assert ref["p"] == unit_days and ref["tf"] == "1d" and "u" not in ref, (said, tf, ref)
    assert got["exit"][0]["r"] == ref
    assert any("worked out on daily candles" in a and idea_read_tf_words(tf) in a for a in got["assumed"]), got["assumed"]


@pytest.mark.parametrize("said,p", [("200 day moving average", 200), ("20 week moving average", 100), ("20 sma", 20)])
def test_on_daily_candles_a_day_length_is_left_as_it_is_and_a_week_is_five_days(said, p):
    got = ai_writer.check_against_text(_ai_answer(tf="1d"), f"buy when price closes above the {said}, sell when it closes back under it")
    ref = got["entry"][0]["r"]
    assert ref["p"] == p and "tf" not in ref and "u" not in ref


def test_a_length_with_no_unit_on_intraday_candles_is_said_in_candles_not_days():
    got = ai_writer.check_against_text(_ai_answer(tf="15m"), "buy when price closes above the 200 moving average, sell when it closes back under it, 15 minute candles")
    assert got["entry"][0]["r"] == {"t": "sma", "p": 200}
    assert got["assumed"] == ['"200 moving average" is read as the 200-candle simple moving average (SMA): your words don\'t say simple or exponential.']


def test_a_week_length_too_long_to_run_is_asked_not_shortened():
    got = ai_writer.check_against_text(_ai_answer([{"l": PX, "op": "gt", "r": {"t": "sma", "p": 200}}], tf="1d"),
                                       "buy when price closes above the 200 week moving average, sell when it closes back under it")
    assert got["entry"] == [] and any("longer than 500 trading days" in n for n in got["notes"])


def idea_tf(tf):
    return {"5m": "5 minute", "15m": "15 minute", "1h": "hourly"}[tf]


def idea_read_tf_words(tf):
    from app import idea_read
    return idea_read.TF_WORDS[tf]


def test_the_name_uses_the_instrument_and_the_rules_never_a_fuzzy_word():
    words = "Buy RELIANCE when RSI drops below 30 and sell when it goes back above 70"
    assert ai_writer.check_against_text(_ai_answer(name="Relevance RSI Reversal", instrument="RELIANCE"), words)["name"] == "RELIANCE RSI 30/70"
    # a name that is true of the strategy is the AI's to keep
    assert ai_writer.check_against_text(_ai_answer(name="Reliance RSI Reversal", instrument="RELIANCE"), words)["name"] == "Reliance RSI Reversal"
    cross = "Buy NIFTY 50 when the 50 EMA crosses above the 200 EMA, sell when it crosses back below"
    assert ai_writer.check_against_text(_ai_answer(name="Golden Cross", instrument="NIFTY 50", tf="1d"), cross)["name"] == "Golden Cross"
    # every way a name can be untrue: another indicator, another length, another instrument, a made-up word
    for wrong in ("NIFTY 50 SMA 50/200", "NIFTY 50 EMA 20/50", "BANKNIFTY EMA Cross", "Niftee EMA Cross", "MACD Momentum"):
        assert ai_writer.check_against_text(_ai_answer(name=wrong, instrument="NIFTY 50", tf="1d"), cross)["name"] == "NIFTY 50 EMA 50/200", wrong


# ---------- LIVE3-006 / LIVE3-007: a stuck job times out and runs again; Admin lists every job stuck or stalled ----------
from app import admin_jobs, breadth, job_status  # noqa: E402
from tests.test_breadth import mem, runner  # noqa: E402,F401


def test_every_job_row_running_past_the_limit_is_a_problem_with_how_long_whatever_the_job():
    import time
    job_status._seen_running.clear()
    for jid in ("breadth", "redflags", "positioning", "any-job"):
        fresh = admin_jobs._row(jid, "A job", "daily", "2026-11-04T00:00:00+00:00", running=True, started=time.time() - 600)
        assert fresh["state"] == "ok" and fresh["running_since"] and not fresh["error"]
        stuck = admin_jobs._row(jid, "A job", "daily", "2026-11-04T00:00:00+00:00", running=True, started=time.time() - 15 * 3600)
        assert stuck["state"] == "bad" and stuck["error"].startswith("Stuck: running for 15 h"), stuck
        done = admin_jobs._row(jid, "A job", "daily", "2026-11-04T00:00:00+00:00", running=False)
        assert done["state"] == "ok" and done["running_since"] is None
    # a runner that keeps no start time: timed from when Admin first saw it running
    first = admin_jobs._row("no-start", "A job", "daily", None, running=True)
    assert first["running_since"] and admin_jobs._row("no-start", "A job", "daily", None, running=True)["running_since"] == first["running_since"]


def test_a_breadth_run_whose_source_never_answers_is_stopped_and_the_next_run_takes_over(mem, monkeypatch):  # noqa: F811
    import threading
    import time
    from tests.test_breadth import IST_OPEN
    hang, entered = threading.Event(), threading.Event()
    r = runner()
    real_load = r.load

    def stuck_load(region, sym, days):
        if not hang.is_set():
            entered.set()
            hang.wait(20)                       # the source that never answered
            raise RuntimeError("gone")
        return real_load(region, sym, days)
    r.load = stuck_load
    first = threading.Thread(target=lambda: r.run("IN", IST_OPEN), daemon=True)
    first.start()
    assert entered.wait(5)
    assert r.run("IN", IST_OPEN) == {"ok": False, "error": "A breadth run is already going."}       # not yet past RUN_MAX
    r.started_at = time.time() - breadth.RUN_MAX - 1                                                 # ...and now it is
    hang.set()                                    # from here the source answers the new run (the old one's read still fails)
    got = r.run("IN", IST_OPEN)
    assert got["ok"] is True and breadth.view("nifty500")["today"]["adv"]["value"] == 2
    first.join(5)
    assert r.running is None and r.started_at is None


def test_the_breadth_job_gives_up_on_a_hung_run_and_tries_again_later(mem, monkeypatch):  # noqa: F811
    import threading
    from datetime import datetime, timezone
    monkeypatch.setattr(breadth, "RUN_MAX", -299.5)                       # bounded at RUN_MAX + 300 s: half a second here
    gate = threading.Event()

    class Hung:
        running, started_at = None, None

        def run(self, region, now):
            gate.wait(10)
            return {"ok": True}
    job = breadth.Job(Hung(), ready=lambda r: r == "IN")
    assert job.tick(datetime(2026, 9, 30, 13, 30, tzinfo=timezone.utc)) == 0
    gate.set()
    assert "ran longer than" in job.status["last_error"] and job.retry["breadth-IN"] > 0
    assert mem.get("newsjob:breadth-IN") is None                           # not marked done: the next turn runs it


def test_the_ipo_documents_catch_up_stalled_is_a_check_with_why():
    from datetime import datetime, timezone
    eve = datetime(2026, 11, 4, 13, 25, tzinfo=timezone.utc)              # 18:55 IST
    ai = {"scheduled": 0, "cap": 120, "asked": 0, "waiting": 67, "days": 1, "to_read": 73}
    failed = {"at": "2026-11-04T12:00:00+00:00", "read": 0, "summaries": 0, "waiting": 2, "error": "Acme Ltd: The AI couldn't answer."}
    assert admin_jobs.ipo_docs_check(failed, ai, eve) == ("Offer documents: no summary written today (67 waiting). The last pass failed: "
                                                         "Acme Ltd: The AI couldn't answer.")
    assert "hasn't run today" in admin_jobs.ipo_docs_check({"at": "2026-11-03T12:00:00+00:00"}, ai, eve)
    assert "hasn't run today" in admin_jobs.ipo_docs_check(None, ai, eve)
    assert admin_jobs.ipo_docs_check(None, ai, datetime(2026, 11, 4, 2, 0, tzinfo=timezone.utc)) is None     # 07:30 IST: early yet
    assert admin_jobs.ipo_docs_check(failed, {**ai, "scheduled": 4}, eve) is None                          # it is writing today
    assert admin_jobs.ipo_docs_check(failed, {**ai, "waiting": 0}, eve) is None
    row = admin_jobs._row("ipo", "IPOs", "daily", "2026-11-04T13:00:00+00:00", check=admin_jobs.ipo_docs_check(failed, ai, eve))
    assert row["state"] == "warn" and "no summary written today" in row["error"]


# ---------- LIVE3-025: an index's "final" level is the exchange's close once it is in ----------
INDEX_FILE = ("Index Name,Index Date,Open Index Value,High Index Value,Low Index Value,Closing Index Value,Points Change,Change(%)\n"
              "Nifty 50,04-11-2026,24100.00,24300.00,24050.00,24210.55,110.2,0.46\n"
              "Nifty 500,04-11-2026,22520.35,22800.00,22500.00,22769.20,248.85,1.11\n"
              "Nifty Midcap 150,04-11-2026,1.0,1.0,1.0,20111.05,1,1\n")


def test_the_exchanges_index_file_is_read_once_kept_and_each_index_takes_its_close(mem, monkeypatch):  # noqa: F811
    from datetime import datetime, timezone
    from app import official_close
    asked = []

    class Files:
        def text(self, url, want=".csv"):
            asked.append(url)
            return INDEX_FILE
    monkeypatch.setitem(official_close._src, "files", lambda: Files())
    official_close._asked.clear(), official_close._mem.clear()
    eve = datetime(2026, 11, 4, 13, 30, tzinfo=timezone.utc)
    assert official_close.index_close("NIFTY 500", "2026-11-04", now=eve) is None                    # a page never reads the file
    assert official_close.index_close("NIFTY 500", "2026-11-04", fetch=True, now=datetime(2026, 11, 4, 9, 0, tzinfo=timezone.utc)) is None  # 14:30 IST: not out
    assert official_close.index_close("NIFTY 500", "2026-11-04", fetch=True, now=eve) == 22769.2
    assert asked == ["https://nsearchives.nseindia.com/content/indices/ind_close_all_04112026.csv"]
    official_close._mem.clear()
    for name, close in (("NIFTY 50", 24210.55), ("NIFTY 500", 22769.2), ("NIFTY MIDCAP 150", 20111.05)):
        assert official_close.index_close(name, "2026-11-04") == close                               # kept: every index, no second read
    assert len(asked) == 1


def test_the_live_final_level_is_the_official_close_for_every_group_once_it_is_in(mem, monkeypatch):  # noqa: F811
    from datetime import datetime, timezone
    from app import breadth_live, official_close
    after = datetime(2026, 11, 4, 13, 20, tzinfo=timezone.utc)          # 18:50 IST
    official_close._mem.clear()
    for g, v in breadth.GROUPS.items():
        if v["region"] != "IN":
            continue
        point = ["15:30", 300, 180, 20, 250, 500, 240, 500, 230, 500, 22770.80, 500, 0]
        monkeypatch.setattr(breadth_live, "load", lambda group, day, p=point: {"points": [["15:15"] + p[1:10] + [22700.0, 500, 0], p]})
        mem.pop(official_close.INDEX_KEY + "2026-11-04", None)
        official_close._mem.clear()
        before = breadth_live.view(g, after)
        assert before["state"] == "final" and before["latest"]["idx"] == 22770.80 and not before.get("official")
        mem[official_close.INDEX_KEY + "2026-11-04"] = json.dumps({v["index"].upper(): 22769.2})
        official_close._mem.clear()
        got = breadth_live.view(g, after)
        assert got["latest"]["idx"] == 22769.2 and got["points"][-1][1 + breadth_live.FIELDS.index("idx")] == 22769.2 and got["official"], g
        assert got["points"][-1][1:10] == point[1:10] and got["points"][0][-3] == 22700.0                      # the counts and earlier rounds as they were


def test_the_daily_run_stores_each_recent_days_official_index_close(mem, monkeypatch):  # noqa: F811
    from app import official_close
    from tests.test_breadth import IST_OPEN, LAST
    official_close._mem.clear()
    mem[official_close.INDEX_KEY + LAST] = json.dumps({"NIFTY 500": 12345.65, "NIFTY 50": 23456.75})
    r = runner()
    r.run("IN", IST_OPEN)
    v = breadth.view("nifty500")
    assert v["history"]["index"][-1] == 12345.65                         # the candle's own close was 20,000-something
