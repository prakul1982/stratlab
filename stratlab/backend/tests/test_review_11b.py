"""Review 11B: scans and market-event pages (watchlist size, split-stale MTF percentages, earlier-day auction indices,
lagging stocks, results dates, percentage dividends, halt days, surveillance wording, F&O sources and tense, alert/fresh,
Fed and BLS release status). Every clock is fixed."""
import json
from datetime import date, datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from app import main  # noqa: F401  (first: the app loads the newsletter job before the modules built on it)
from app import closing_auction as CA, corp_actions, db, fo_changes as F, market_events as M, mtf, results, scan, scan_presets, surveillance
from tests import world as W
from tests.test_scan import FakeRegistry, bars_from, store  # noqa: F401  (fixture)

UP = list(np.linspace(100, 200, 300)) + list(np.linspace(200, 185, 12)) + list(np.linspace(185, 198, 4))


# ---------- 1. a watchlist of 80 is scanned whole ----------
def test_a_watchlist_of_eighty_is_scanned_whole(monkeypatch):
    series = {f"S{i}": bars_from(UP) for i in range(80)}
    reg = FakeRegistry(series)
    monkeypatch.setattr(scan, "_bars", lambda registry, iid: series[iid.split(":")[1]])
    members = [{"symbol": f"S{i}"} for i in range(80)]
    got = scan.run_preset(reg, "US", members, "st_s2")
    assert got["checked"] == 80 and got["asked"] == 80 and got["problems"] == []
    assert len(scan.run(reg, "US", members)["rows"]) == 80


def test_stocks_past_the_scan_limit_are_named_not_dropped_silently(monkeypatch):
    series = {f"S{i}": bars_from(UP) for i in range(103)}
    reg = FakeRegistry(series)
    monkeypatch.setattr(scan, "_bars", lambda registry, iid: series[iid.split(":")[1]])
    got = scan.run_preset(reg, "US", [{"symbol": f"S{i}"} for i in range(103)], "st_s2")
    assert got["asked"] == 103 and got["checked"] == 100 and len(got["problems"]) == 3 and "S102" in got["problems"][-1]


# ---------- 2. MTF percentages in the window after a split ----------
def test_mtf_percentages_are_blank_until_the_shares_file_is_read_after_a_split(monkeypatch):
    class S:
        def latest(self): return "2026-10-15", {"rows": {"AAA": [50_000, 2000.0, 100.0]}}
        def series(self, sym): return [["2026-10-13", 10_000, 2000.0, 500.0]]
    monkeypatch.setattr(mtf, "shares", lambda: {"as_of": "2026-10-09", "shares": {"AAA": 1_000_000}})
    monkeypatch.setattr(mtf.DESK, "store", S())
    monkeypatch.setattr(mtf, "_splits", lambda sym: ["2026-10-14"])
    r = mtf.for_symbol("AAA")
    assert r["pct_shares"] is None and r["pct_mcap"] is None
    monkeypatch.setattr(mtf, "shares", lambda: {"as_of": "2026-10-15", "shares": {"AAA": 5_000_000}})
    r = mtf.for_symbol("AAA")
    assert r["pct_shares"] == 1.0 and r["pct_mcap"] == 40.0


def test_mtf_screen_and_level_alerts_skip_a_stock_split_since_the_shares_file(monkeypatch):
    class S:
        def latest(self): return "2026-10-15", {"rows": {"AAA": [50_000, 2000.0, 100.0], "BBB": [50_000, 2000.0, 100.0]}}
    monkeypatch.setattr(mtf, "shares", lambda: {"as_of": "2026-10-09", "shares": {"AAA": 1_000_000, "BBB": 1_000_000}})
    monkeypatch.setattr(mtf.DESK, "store", S())
    split = {"id": "AAA|split|2026-10-14", "symbol": "AAA", "kind": "split", "factor": 5.0, "ex_date": "2026-10-14"}
    monkeypatch.setattr(corp_actions, "between", lambda region, frm, to, symbols=None: [split])
    assert mtf.screen_values() == {"BBB": 5.0}
    out = mtf.DESK.after("2026-10-15", S().latest()[1]["rows"], None)
    assert [x["symbol"] for x in out] == ["BBB"]


# ---------- 3. yesterday's indicative index close ----------
@pytest.fixture
def w(monkeypatch):
    world = W.build(monkeypatch)
    yield world
    world["close"]()
    CA.forget()


def test_an_earlier_days_indicative_index_close_is_not_shown_as_current(w):
    IST = timezone(timedelta(hours=5, minutes=30))
    CA.save_live("2026-10-14", {"as_of": None, "status": None, "message": None, "eligible": [], "rows": {}},
                 {"NIFTY 50": {"value": 25000.0, "indicative": 25080.0, "prev_close": 24900.0, "status": "open"}},
                 datetime(2026, 10, 14, 15, 39, tzinfo=IST))
    v = CA.view({"id": "u", "_plan": "pro"}, datetime(2026, 10, 15, 11, 0, tzinfo=IST))
    nifty = next(i for i in v["indices"] if i["name"] == "NIFTY 50")
    assert not v["fresh"] and nifty["indicative"] is None and nifty["gap"] is None and nifty["value"] == 25000.0


# ---------- 4. a stock that stopped trading isn't "on the latest close" ----------
def match(days_ago=0, day="2026-10-09"):
    return {"days_ago": days_ago, "day": day, "detail": "d"}


def test_a_lagging_stock_is_measured_against_the_groups_newest_session():
    per = {"AAA": {"as_of": "2026-10-14", "price": 100, "chg": 1, "matches": {"high52": match(0, "2026-10-14")}},
           "BBB": {"as_of": "2026-10-09", "price": 100, "chg": 1, "matches": {"high52": match(0, "2026-10-09"), "volume_surge": match()}}}
    doc = scan_presets.build(per)
    rows = {r["s"]: r for r in doc["rows"]}
    assert rows["AAA"]["m"]["high52"][0] == 0
    assert "BBB" not in rows                                          # 3 sessions behind: past high52's 3-candle window
    per["BBB"]["as_of"] = "2026-10-13"
    assert scan_presets.build(per)["rows"][1]["m"]["high52"][0] == 1   # one session behind: matched a session earlier
    assert doc["counts"]["high52"] == 1 and doc["counts"]["volume_surge"] == 0                          # a one-day match is not today's


def test_a_live_preset_scan_counts_the_lag_too(monkeypatch):
    live = bars_from(list(np.linspace(100, 300, 320)))                # a steady climb: in Stage 2 above its Supertrend
    late = live[:-3]                                                  # still matching on its own last candle, three days before the others'
    series = {"AAA": live, "BBB": late}
    reg = FakeRegistry(series)
    monkeypatch.setattr(scan, "_bars", lambda registry, iid: series[iid.split(":")[1]])
    got = scan.run_preset(reg, "US", [{"symbol": "AAA"}, {"symbol": "BBB"}], "st_s2")
    assert [r["symbol"] for r in got["rows"]] == ["AAA"] and got["checked"] == 2


# ---------- 5. results date ----------
def test_a_results_date_is_the_meetings_not_the_letters():
    items = [{"subject": "Board Meeting Intimation", "at": "2026-10-28T10:00:00",
              "text": "Date: October 28, 2026. A meeting of the Board of Directors will be held on November 5, 2026 to "
                      "consider the unaudited financial results for the quarter ended September 30, 2026."}]
    got = results.from_announcements("AAA", items, date(2026, 10, 28))
    assert [x["date"] for x in got] == ["2026-11-05"]
    items[0]["text"] = "Board meeting held today to consider financial results."
    items[0]["text"] += " Date: 28-10-2026"
    assert [x["date"] for x in results.from_announcements("AAA", items, date(2026, 10, 28))] == ["2026-10-28"]


# ---------- 6. percentage dividend ----------
def test_a_percentage_dividend_is_of_the_face_value_not_the_face_value():
    a = corp_actions.parse_purpose("Dividend - 50% (FV Rs 10)", 10)
    assert a[0]["amount"] == 5.0
    b = corp_actions.parse_purpose("Interim Dividend - 100% (on face value of Rs 5)", 10)
    assert b[0]["amount"] == 5.0
    assert corp_actions.parse_purpose("Interim Dividend - Rs 9 Per Share", 10)[0]["amount"] == 9.0


# ---------- 7. one halt day ----------
def test_a_zero_volume_day_does_not_blank_the_volume_surge_scan():
    t0 = datetime(2025, 1, 1)
    vol = [1000] * 60 + [5000]
    vol[50] = 0
    close = [100.0] * 60 + [101.0]
    bars = [{"t": (t0 + timedelta(days=i)).isoformat(), "o": c, "h": c * 1.01, "l": c * 0.99, "c": c, "v": v} for i, (c, v) in enumerate(zip(close, vol))]
    assert "volume_surge" in scan_presets.evaluate(bars)["matches"]


# ---------- 8. surveillance wording ----------
def test_a_stage_change_with_no_stage_on_one_side_says_no_stage_none():
    for was, now, want in (("asm_lt", "asm_lt:2", "moved to Stage 2 of"), ("asm_lt:2", "asm_lt", "no stage stated")):
        text = surveillance.change_text({"list": "asm_lt", "was": was, "now": now})
        assert "None" not in text and want in text


# ---------- 9. F&O lot sources ----------
def test_nameless_circulars_are_sources_only_when_the_sole_candidate():
    e = {"id": "lot:AAA", "kind": "lot", "symbol": "AAA", "effective": "2026-11-25", "series": "2026-12", "was": 100, "now": 80}
    c = lambda i, d, syms=(): {"id": i, "kind": "lot", "symbols": list(syms), "date": d, "subject": "s", "no": i, "url": "u"}   # noqa: E731
    assert F.sources_for(e, [c("c1", "2026-10-03"), c("c2", "2026-09-20")]) == []
    assert [x["no"] for x in F.sources_for(e, [c("c1", "2026-10-03")])] == ["c1"]
    assert [x["no"] for x in F.sources_for(e, [c("c1", "2026-10-03"), c("c2", "2026-10-04"), c("n", "2026-10-03", ["AAA"])])] == ["n"]


# ---------- small points ----------
def test_a_one_stock_group_with_a_suspended_stock_reads_stale_against_the_session(monkeypatch):
    live = bars_from(UP)
    series = {"AAA": live[:-40]}
    reg = FakeRegistry(series)
    monkeypatch.setattr(scan, "_bars", lambda registry, iid: series[iid.split(":")[1]])
    last = str(series["AAA"][-1]["t"])[:10]
    session = (date.fromisoformat(last) + timedelta(days=40)).isoformat()
    assert scan.run(reg, "US", [{"symbol": "AAA"}])["rows"]                       # alone, it is its own newest
    got = scan.run(reg, "US", [{"symbol": "AAA"}], session=session)
    assert got["rows"] == [] and got["problems"] == ["AAA: no recent daily prices"]
    got = scan.run_preset(reg, "US", [{"symbol": "AAA"}], "st_s2", session=session)
    assert got["rows"] == [] and got["problems"] == ["AAA: no recent daily prices"]


def test_the_alert_goes_out_once_per_flip_within_the_fresh_window(monkeypatch, store):
    # AAA flipped up three candles before the last: the page says fresh, so the alert says so too (once, not again next day)
    up = list(np.linspace(100, 200, 300)) + list(np.linspace(200, 180, 15)) + [199.0, 200.0, 201.0]
    bars = bars_from(up)
    for i, b in enumerate(bars):                                    # the last candle is the 1 Oct session the alert runs after
        b["t"] = (datetime(2026, 10, 1, tzinfo=timezone.utc) - timedelta(days=len(bars) - 1 - i)).isoformat()
    series = {"AAA": bars}
    reg = FakeRegistry(series)
    monkeypatch.setattr(scan, "_bars", lambda registry, iid: series["AAA"])
    row = scan.run(reg, "US", [{"symbol": "AAA"}])["rows"][0]
    assert row["signal"] == "fresh" and row["st_days"] > 1
    store["watchlist:u1"] = json.dumps({"items": [{"region": "US", "symbol": "AAA"}]})
    scan.set_alert("u1", True)
    monkeypatch.setattr(db, "get_profile", lambda uid: {"id": uid})
    monkeypatch.setattr("app.data.calendar.is_trading_day", lambda m, d: True)
    sent = []
    first = datetime(2026, 10, 1, 20, 55, tzinfo=timezone.utc)
    for n in range(2):
        job = scan.Alerts(reg, notify=lambda p, s, t, url: sent.append(t), can_alert=lambda p: True)
        job.tick(first + timedelta(days=n))
    assert len(sent) == 1 and "AAA" in sent[0]


def test_saved_day_and_included_agree_an_action_on_the_saved_day_is_still_pending():
    a = {"id": "T|bonus|2026-10-05|1:1", "kind": "bonus", "ratio": [1, 1], "factor": 2.0, "ex_date": "2026-10-05"}
    item = {"symbol": "T", "qty": 10}
    since = corp_actions.saved_day("2026-10-05T06:00:00+00:00", date(2026, 10, 6))
    assert since == "2026-10-05" and [x["id"] for x in corp_actions.pending(item, [a], since, date(2026, 10, 6))] == [a["id"]]
    assert "not in it yet" in corp_actions.saved_day.__doc__


def test_fed_and_bls_events_say_released_after_their_release_time():
    IST = timezone(timedelta(hours=5, minutes=30))
    fed = {"meetings": [{"start": "2026-10-13", "end": "2026-10-14", "low": 3.5, "high": 3.75, "statement_url": "https://x"}]}
    us = {"releases": [{"kind": "us_cpi", "date": "2026-10-14", "time": "08:30"}]}
    # 14 Oct: the Fed statement 14:00 New York = 23:30 India; CPI 08:30 New York = 18:00 India
    before = datetime(2026, 10, 14, 17, 0, tzinfo=IST)
    after = datetime(2026, 10, 14, 23, 45, tzinfo=IST)
    today = date(2026, 10, 14)
    assert [e["status"] for e in M.us_events(us, today, before)] == ["scheduled"]
    assert [e["status"] for e in M.us_events(us, today, after)] == ["released"]
    f = M.fed_events({"meetings": [{"start": "2026-10-13", "end": "2026-10-14", "statement_url": "https://x"}]}, today, after)
    assert [e["status"] for e in f] == ["released"]
    f = M.fed_events({"meetings": [{"start": "2026-10-13", "end": "2026-10-14"}]}, today, before)
    assert [e["status"] for e in f] == ["scheduled"]
    assert fed and us


def test_an_exit_after_the_last_expiry_is_in_the_past_tense():
    e = {"id": "exit:X", "kind": "exit", "symbol": "X", "series": "2026-11", "expiry": "2026-11-24"}
    assert F.text_of(e, date(2026, 11, 20)).startswith("X leaves F&O.")
    assert F.text_of(e, date(2026, 11, 25)).startswith("X left F&O.") and "expired" in F.text_of(e, date(2026, 11, 25))
    assert F.text_of(e).startswith("X leaves F&O.")
