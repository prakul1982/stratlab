"""fix14: the live review LIVE11B (Release 66/67): each finding's fix, tested so it fails before and passes after."""
import numpy as np
from fastapi.testclient import TestClient

from app import main, scan
from app.intel.net import SourceError
from tests.test_scan_presets import FakeRegistry, bars, noise


# ---------- LIVE11B-011: a scan asks again for the stocks a busy price source turned away, before reporting them ----------
def _busy_world(monkeypatch, fail_times: int):
    """Three stocks; BBB's and CCC's first `fail_times` reads are turned away as busy (our rate limit), AAA's never."""
    scan._cache.clear()
    monkeypatch.setattr(scan, "BUSY_PAUSE", 0.0)
    monkeypatch.setattr(scan, "session_day", lambda market, now=None: None)
    flat = list(100 + noise(280, 3, 0.4))
    top = max(flat[-252:])
    series = {"AAA": bars(flat + [top + 5]), "BBB": bars(flat + [top + 6]), "CCC": bars(flat + [top - 5])}
    tries: dict[str, int] = {}

    def read(registry, iid):
        sym = iid.split(":")[1]
        tries[sym] = tries.get(sym, 0) + 1
        if sym != "AAA" and tries[sym] <= fail_times:
            raise SourceError("prices", "prices is busy (our rate limit). Try again in a minute.", busy=True)
        return series[sym]

    monkeypatch.setattr(scan, "_bars", read)
    return FakeRegistry(series), tries


def test_a_preset_scan_reads_the_busy_stocks_again_before_reporting(monkeypatch):
    reg, tries = _busy_world(monkeypatch, fail_times=1)
    out = scan.run_preset(reg, "US", [{"symbol": "AAA"}, {"symbol": "BBB"}, {"symbol": "CCC"}], "high52")
    assert out["problems"] == [] and out["checked"] == 3
    assert sorted(r["symbol"] for r in out["rows"]) == ["AAA", "BBB"]
    assert tries == {"AAA": 1, "BBB": 2, "CCC": 2}            # only the turned-away ones were asked again
    scan._cache.clear()


def test_the_stage_scan_reads_the_busy_stocks_again_too(monkeypatch):
    reg, tries = _busy_world(monkeypatch, fail_times=1)
    out = scan.run(reg, "US", [{"symbol": "AAA"}, {"symbol": "BBB"}, {"symbol": "CCC"}])
    assert out["problems"] == [] and len(out["rows"]) == 3
    scan._cache.clear()


def test_a_source_still_busy_after_the_retries_is_reported_and_a_real_problem_is_not_retried(monkeypatch):
    reg, tries = _busy_world(monkeypatch, fail_times=99)
    out = scan.run_preset(reg, "US", [{"symbol": "AAA"}, {"symbol": "BBB"}, {"symbol": "CCC"}], "high52")
    assert out["checked"] == 1 and len(out["problems"]) == 2 and all("busy" in p for p in out["problems"])
    assert tries["BBB"] == 1 + scan.BUSY_RETRIES
    # too few prices is an answer, not a busy source: read once
    scan._cache.clear()
    calls = {"n": 0}

    def short(registry, iid):
        calls["n"] += 1
        return bars([100.0] * 10)

    monkeypatch.setattr(scan, "_bars", short)
    scan.run_preset(FakeRegistry({"DDD": []}), "US", [{"symbol": "DDD"}], "high52")
    assert calls["n"] == 1
    scan._cache.clear()


# ---------- LIVE11B-004: the data status is a public answer the app asks for as it starts ----------
def test_public_data_status_says_whether_india_is_online_and_its_note(monkeypatch):
    c = TestClient(main.app)
    monkeypatch.setattr(main.kite, "ready", lambda: False)
    got = c.get("/public/data-online").json()
    assert got["data_online"] is False and set(got["data_note"]) == {"closed", "back_at"}
    monkeypatch.setattr(main.kite, "ready", lambda: True)
    assert c.get("/public/data-online").json() == {"data_online": True, "data_note": None}


# ---------- LIVE11B-015: one figure once: the list's title, then the brief's table, without the same moves again ----------
def test_the_opening_index_moves_go_when_the_table_and_title_carry_them():
    from app.newsletter import write
    ind = [{"name": "NIFTY 50", "change_pct": 0.38}, {"name": "SENSEX", "change_pct": 0.31}, {"name": "NIFTY BANK", "change_pct": -0.12}]
    said = "NIFTY 50 +0.38%; SENSEX +0.31%; NIFTY BANK −0.12% today. 2 sectors moved to another quadrant on the rotation chart."
    assert write.without_moves(said, ind) == "2 sectors moved to another quadrant on the rotation chart."
    assert write.without_moves("NIFTY 50 +0.38%; SENSEX +0.31%; NIFTY BANK −0.12% on Tue 17 Nov. Breadth was firm.", ind) == "Breadth was firm."
    # a sentence that says more than the moves, a move that isn't the table's, or no moves known: left as it is
    assert write.without_moves("NIFTY 50 +0.38% and SENSEX +0.31% today, led by banks. More.", ind).startswith("NIFTY 50 +0.38%")
    assert write.without_moves("NIFTY 50 +0.40% today. More.", ind).startswith("NIFTY 50")
    assert write.without_moves("Markets rose. NIFTY 50 +0.38%.", ind) == "Markets rose. NIFTY 50 +0.38%."
    assert write.without_moves(said, []) == said and write.without_moves(None, ind) is None


def test_the_briefs_list_and_page_say_the_moves_once(monkeypatch):
    from tests import world as W
    from tests.fake_db import headers
    from app.newsletter import job
    world = W.build(monkeypatch)
    try:
        c = world["client"]
        iid = job.issue_id("market", "IN", "2026-11-17", False)
        job.save({"id": iid, "kind": "market", "region": "IN", "day": "2026-11-17", "weekly": False,
                  "subject": "Market Brief India, Tue 17 Nov: NIFTY 50 +0.38%", "title": "NIFTY 50 up 0.38%", "ai": False,
                  "summary": "NIFTY 50 +0.38%; SENSEX +0.31% today. 2 sectors moved to another quadrant on the rotation chart.",
                  "indices": [{"name": "NIFTY 50", "price": 25387.4, "change_pct": 0.38}, {"name": "SENSEX", "price": 82532.19, "change_pct": 0.31}],
                  "sections": [{"title": "Indices", "items": [{"text": "NIFTY 50: 25,387.40, +0.38% on the day", "url": None, "lines": []},
                                                              {"text": "SENSEX: 82,532.19, +0.31% on the day", "url": None, "lines": []}]},
                               {"title": "Sector rotation", "items": [{"text": "Nifty Bank moved from Weakening to Leading on the rotation chart (weekly)", "url": None, "lines": []},
                                                                      {"text": "Nifty IT moved from Lagging to Improving on the rotation chart (weekly)", "url": None, "lines": []}]}],
                  "at": "2026-11-17T16:30+05:30"})
        row = next(i for i in c.get("/news?kind=market&region=IN", headers=headers("pro-token")).json()["issues"] if i["id"] == iid)
        assert row["subject"].endswith("NIFTY 50 +0.38%") and "+0.38%" not in (row["preview"] or "")
        view = c.get(f"/news/{iid}", headers=headers("pro-token")).json()
        assert any(t["title"] == "Indices" for t in view["tables"])
        assert view["summary"].startswith("2 sectors moved") and "+0.38%" not in view["summary"]
    finally:
        world["close"]()


# ---------- LIVE11B-006: with the live feed offline, the F&O underlyings stay browsable from the last list it gave ----------
def test_the_last_underlyings_list_is_kept_and_listed_offline(monkeypatch):
    from datetime import datetime
    from app import db, positioning
    kv = {}
    monkeypatch.setattr(db, "set_setting", lambda k, v: kv.__setitem__(k, v))
    monkeypatch.setattr(db, "get_setting", lambda k: kv.get(k))
    monkeypatch.setattr(main, "_underlyings_kept", {"day": None})
    monkeypatch.setattr(positioning, "ist_now", lambda: datetime(2026, 11, 18, 6, 0, tzinfo=main.IST))
    rows = [{"exchange": "NFO", "name": "NIFTY", "lot": 75, "expiries": ["2026-11-17", "2026-11-23", "2026-12-01"],
             "lots": {"2026-11-17": 75, "2026-11-23": 65, "2026-12-01": 65}, "venue": "NSE", "popular": True, "freeze": 1800, "index": True},
            {"exchange": "NFO", "name": "TCS", "lot": 175, "expiries": ["2026-11-24", "2026-12-29"], "lots": {"2026-11-24": 175, "2026-12-29": 175},
             "venue": "NSE", "popular": False, "freeze": 0, "index": False},
            {"exchange": "NFO", "name": "GONE", "lot": 1, "expiries": ["2026-11-17"], "lots": {"2026-11-17": 1}, "venue": "NSE", "popular": False, "freeze": 0, "index": False}]
    main.keep_underlyings(rows)
    # the feed offline, NIFTY with a recorded chain, the rest from the kept list (expired dates and contracts out)
    monkeypatch.setattr(positioning, "recorded_chain", lambda name, expiry, day, now: None)
    got = main.options_recorded(profile={"id": "u"})
    by = {u["name"]: u for u in got}
    assert set(by) == {"NIFTY", "TCS"} and by["TCS"]["stored"] is True
    assert by["NIFTY"]["expiries"] == ["2026-11-23", "2026-12-01"] and by["NIFTY"]["lot"] == 65


# ---------- LIVE11B-007: the journal verdict says the coin sentence once ----------
def test_the_journal_verdict_says_the_coin_sentence_once():
    from app import journal as J
    nets = [9000.0, 4000, 3000, 2000, 800, 820, -1500, -1300, -842]     # 9 trades, 6 wins, net ₹15,978 as in the review
    ts = [{"net": v, "gross": v + 20, "charges": 20} for v in nets]
    v = J.verdict(ts)
    line = J.win_rate_line(9, 6)
    luck = next(c for c in v["checks"] if c["id"] == "luck")
    said = [v["summary"], v["headline"]] + [str(c.get("detail") or "") for c in v["checks"]]
    assert sum(t.count(line) for t in said) == 1
    assert luck["status"] == "warn" and line in luck["detail"]          # the check carries it, the summary doesn't repeat it
    # with too few trades for the luck check, the summary still carries it
    few = J.verdict([{"net": v, "gross": v, "charges": 0} for v in [100.0, 50.0, -20.0, 30.0]])
    assert J.win_rate_line(4, 3) in few["summary"]


# ---------- LIVE11B-008: one NAV date for the funds' total on Net worth and the Mutual funds page ----------
def test_net_worth_gives_the_funds_newest_nav_date_with_the_oldest_beside_it(monkeypatch):
    from app import money_mf as M, money_networth as NW
    monkeypatch.setattr(M, "load", lambda uid: {"txns": [1]})
    monkeypatch.setattr(M, "worked", lambda data: None)
    monkeypatch.setattr(M, "holdings", lambda data, w, today: {"schemes": [
        {"units": 10, "value": 40000.0, "invested": 30000, "nav_date": "2026-11-16"},
        {"units": 5, "value": 29764.0, "invested": 25000, "nav_date": "2026-11-17"}]})
    got = M.net_worth_value("u")
    assert got["as_of"] == "2026-11-17" and got["as_of_from"] == "2026-11-16"        # the funds page's "NAVs up to 17 Nov"
    mf = NW.mf_value("u")
    assert mf["as_of"] == "2026-11-17" and mf["as_of_from"] == "2026-11-16"


# ---------- LIVE11B-012: a page moved to the official close takes that session's high and low into its 52-week range ----------
def test_the_official_close_brings_the_sessions_high_into_the_52_week_range(monkeypatch):
    import json as _json
    from datetime import datetime
    from app import db, exchange_days, official_close, stock_pages
    text = ("TradDt,TckrSymb,SctySrs,OpnPric,HghPric,LwPric,ClsPric,LastPric,PrvsClsgPric\n"
            "2026-11-17,KOTAKBANK,EQ,494.00,499.90,492.10,497.25,497.30,495.00\n")
    row = exchange_days.cash_rows(text)["KOTAKBANK"]
    assert row["high"] == 499.9 and row["low"] == 492.1
    store = {}
    monkeypatch.setattr(db, "get_setting", lambda k: store.get(k))
    monkeypatch.setattr(db, "set_setting", lambda k, v: store.__setitem__(k, v))
    monkeypatch.setattr(db, "all_settings_with_prefix", lambda p: [(k, v) for k, v in sorted(store.items()) if k.startswith(p)])
    f = {"region": "IN", "symbol": "KOTAKBANK", "price": 497.3, "price_at": "2026-11-17", "high52": 497.9, "low52": 380.0}
    store["stocks:page:IN:KOTAKBANK"] = _json.dumps({"ts": 1.0, "facts": f})
    pages = stock_pages.Pages(lambda r, c: None)
    got = pages.refresh_prices("IN", lambda r, s: [], gap=0, now=datetime(2026, 11, 17, 20, 0, tzinfo=main.IST),
                               official=lambda s, d: 497.25, official_ready=lambda d: True, official_range=lambda s, d: (499.9, 492.1))
    new = _json.loads(store["stocks:page:IN:KOTAKBANK"])["facts"]
    assert got["official"] == 1 and new["price"] == 497.25 and new["high52"] == 499.9 and new["low52"] == 380.0
    from app import screens
    assert screens.row("IN", "KOTAKBANK", new)["from_high"] == round((497.25 / 499.9 - 1) * 100, 2)        # −0.53%, not −0.13%
    # a figure that can't be the session's (a high under the close, a basis far off) is left out
    assert stock_pages.with_day_range(f, 497.25, 490.0, 600.0)["high52"] == 497.9
    assert stock_pages.with_day_range(f, 497.25, 900.0, None)["high52"] == 497.9
    # day_range reads the day's file through the official close's source
    official_close.setup(lambda: object(), None, force=True)
    try:
        monkeypatch.setattr(exchange_days, "cash_closes", lambda files, day: {"KOTAKBANK": row})
        monkeypatch.setattr(official_close, "before_ex_date", lambda s, d, now=None: False)
        assert official_close.day_range("kotakbank", "2026-11-17") == (499.9, 492.1)
    finally:
        official_close.setup(None, None, force=True)


# ---------- LIVE11B (LIVE10B-039): the charges check doesn't pass on charges known to leave STT out ----------
def test_the_cost_check_is_not_passed_on_charges_that_leave_stt_out():
    from app import journal as J
    ts = [{"net": 1000.0, "gross": 1020.0, "charges": 20.0} for _ in range(6)]
    assert J.check_costs(ts)["status"] == "pass"
    marked = [{**t, "no_stt": i < 2} for i, t in enumerate(ts)]
    c = J.check_costs(marked)
    assert c["status"] == "warn" and "2 trades (marked *) have charges below the STT alone" in c["detail"] and c["data"]["no_stt"] == 2
    assert J.verdict(marked)["verdict"] != "edge"
