"""Review 4d, the data layer: an announced split that hasn't happened yet, stored official closes and the 52-week report read
back from the database, a 52-week report on the basis before a split, the BSE listing of an NSE company in every process,
and the book value per share beside a price on a new basis. Every clock here is a fixed instant."""
from datetime import date, datetime, timedelta, timezone

import pytest

from app import main  # noqa: F401, I001  (first: the app loads the newsletter job before the modules built on it)
from app import corp_actions, db, kite_service as ks, official_close as oc, stock_pages
from app.intel.company import at_live_price

IST = timezone(timedelta(hours=5, minutes=30))
NOW = datetime(2026, 10, 10, 11, 0, tzinfo=IST)          # Saturday: the 9th's closes are final


@pytest.fixture
def mem(monkeypatch):
    store: dict = {}
    monkeypatch.setattr(db, "get_setting", lambda k: store.get(k))
    monkeypatch.setattr(db, "set_setting", lambda k, v: store.__setitem__(k, v))
    monkeypatch.setattr(db, "delete_setting", lambda k: store.pop(k, None))
    monkeypatch.setattr(db, "all_settings_with_prefix", lambda p, *a: [(k, v) for k, v in sorted(store.items()) if k.startswith(p)])
    oc.forget()
    yield store
    oc.forget()


BARS = [{"t": "2026-10-08T00:00:00+05:30", "o": 100, "h": 102, "l": 99, "c": 101.0},
        {"t": "2026-10-09T00:00:00+05:30", "o": 101, "h": 103, "l": 100, "c": 102.5}]


def _split(ex: date, kind="split", factor=10.0, text="Split 10 to 1"):
    corp_actions.save("IN", [corp_actions.row("IN", "ABC", {"kind": kind, "label": kind.title(), "text": text, "factor": factor}, ex)])


# ---------- 1: an ex-date still ahead changes nothing yet ----------
def test_an_announced_split_still_ahead_keeps_the_official_close(mem):
    _split(date(2026, 11, 20))                                   # announced; the calendar reads two months ahead
    oc.save("2026-10-09", {"ABC": 103.0})
    assert not oc.before_ex_date("ABC", "2026-10-09", NOW)
    assert oc.official("ABC", "2026-10-09", use_quote=False, now=NOW) == 103.0
    assert oc.overlay_bars(BARS, "ABC", False, NOW)[-1]["c"] == 103.0
    assert oc.history_close(BARS, "ABC", "cas", "NSE", now=NOW)[-1]["c"] == 103.0
    assert oc.day_close("ABC", "2026-10-09", now=NOW, fetch=False) == 103.0
    # once that day comes, the days before it are on the old basis
    after = datetime(2026, 11, 20, 11, 0, tzinfo=IST)
    assert oc.before_ex_date("ABC", "2026-10-09", after) and not oc.before_ex_date("ABC", "2026-11-20", after)


def test_a_past_bonus_still_blocks_with_a_later_one_announced(mem):
    # a 1:4 bonus went ex on the 9th (within the 12 days of closes kept), another is announced for December
    corp_actions.save("IN", [corp_actions.row("IN", "ABC", {"kind": "bonus", "label": "Bonus", "text": "Bonus 1:4", "ratio": [1, 4],
                                                            "factor": 1.25}, date(2026, 10, 9)),
                             corp_actions.row("IN", "ABC", {"kind": "split", "label": "Split", "text": "Split 2 to 1", "factor": 2.0},
                                              date(2026, 12, 4))])
    oc.save("2026-10-08", {"ABC": 900.0})
    oc.save("2026-10-09", {"ABC": 815.0})
    assert oc.before_ex_date("ABC", "2026-10-08", NOW) and not oc.before_ex_date("ABC", "2026-10-09", NOW)
    assert oc.official("ABC", "2026-10-08", use_quote=False, now=NOW) is None
    assert oc.official("ABC", "2026-10-09", use_quote=False, now=NOW) == 815.0
    bars = [{**BARS[0], "c": 810.0, "h": 812.0, "l": 800.0}, {**BARS[1], "c": 812.0, "h": 813.0, "l": 805.0}]
    assert [b["c"] for b in oc.history_close(bars, "ABC", "cas", "NSE", now=NOW)] == [810.0, 815.0]


# ---------- 2: what is stored is read back ----------
def test_stored_closes_are_read_back_from_the_database(mem):
    oc.save("2026-10-08", {"ABC": 101.5})
    oc.save("2026-10-09", {"ABC": 103.0})
    oc.forget()                                     # what the six-hour memory expiry or a restart leaves: the database alone
    assert oc.stored("2026-10-08") == {"ABC": 101.5}
    assert [b["c"] for b in oc.history_close(BARS, "ABC", "cas", "NSE", now=NOW)] == [101.5, 103.0]
    mem["closes:IN:2026-10-07"] = "[1, 2]"           # damaged or another kind: nothing
    assert oc.stored("2026-10-07") is None


def test_the_52_week_report_is_read_back_from_the_database(mem):
    oc.save_ranges("2026-10-09", {"ABC": [120.0, "2026-10-08", 90.0, "2026-01-02"]})
    oc.forget()
    assert oc.ranges() == {"day": "2026-10-09", "rows": {"ABC": [120.0, "2026-10-08", 90.0, "2026-01-02"]}}


# ---------- 2, side effect: a stored report from before a split is on the old basis ----------
def test_a_52_week_report_from_before_a_split_is_not_laid_over_adjusted_candles(mem):
    # a 1:4 bonus (factor 1.25) went ex on the 9th; the report stored is the 8th's, on the old basis, 1.25 times the candles
    corp_actions.save("IN", [corp_actions.row("IN", "ABC", {"kind": "bonus", "label": "Bonus", "text": "Bonus 1:4", "ratio": [1, 4],
                                                            "factor": 1.25}, date(2026, 10, 9))])
    oc.save_ranges("2026-10-08", {"ABC": [127.5, "2026-10-08", 90.0, "2026-01-02"]})
    oc.forget()
    rep = oc.ranges()
    assert oc.range_row("ABC", rep, NOW) is None
    assert oc.widen_to_range(BARS, "ABC", rep, NOW) is BARS
    assert stock_pages.fit_to_exchange_range(BARS, oc.range_row("ABC", rep, NOW), rep["day"]) is BARS
    # the next evening's report, on the new basis, is used
    oc.save_ranges("2026-10-09", {"ABC": [102.5, "2026-10-08", 90.0, "2026-01-02"]})
    assert oc.widen_to_range(BARS, "ABC", oc.ranges(), NOW)[0]["h"] == 102.5
    # a report with no day (an older store) is used as before
    assert oc.range_row("ABC", {"rows": {"ABC": [1, "", 1, ""]}}, NOW) == [1, "", 1, ""]


def test_a_variable_default_never_hides_a_stored_value(mem):
    # exchange_days and positioning read with the caller's default: every caller passes a dict
    from app import exchange_days, positioning
    mem["k:x"] = '{"a": 1}'
    assert exchange_days._load("k:x", {}) == {"a": 1}
    assert positioning._load("k:x", {}) == {"a": 1}


# ---------- 4: the full BSE list in every process ----------
RAW_BSE = [{"instrument_type": "EQ", "segment": "BSE", "tradingsymbol": "RELIANCE", "exchange_token": 500325, "instrument_token": 1,
            "name": "Reliance Industries Ltd"}]
RAW_NSE = [{"instrument_type": "EQ", "segment": "NSE", "tradingsymbol": "RELIANCE", "exchange_token": 2885, "instrument_token": 2,
            "name": "Reliance Industries Ltd"}]


def _kite(monkeypatch, day):
    k = ks.KiteService()
    calls = []
    monkeypatch.setattr(k, "_require", lambda: None)
    monkeypatch.setattr(k, "_throttle", lambda: None)
    monkeypatch.setattr(k.kite, "instruments", lambda ex: calls.append(ex) or (RAW_BSE if ex == "BSE" else RAW_NSE if ex == "NSE" else []))
    monkeypatch.setattr(ks, "today_ist", lambda: day[0])
    return k, calls


def test_the_daily_instrument_load_keeps_the_full_bse_list(monkeypatch):
    day = ["2026-10-14"]
    k, calls = _kite(monkeypatch, day)
    k._load_instruments()
    assert k.instruments_cached("BSE") == RAW_BSE
    assert k.instruments_of("BSE") == RAW_BSE and calls == ["NSE", "NFO", "BSE"]       # no second read of the same list
    day[0] = "2026-10-15"                                                             # IST midnight: read again with the day
    assert k.instruments_cached("BSE") is None
    k._load_instruments()
    assert k.instruments_cached("BSE") == RAW_BSE


def test_bse_twin_finds_the_bse_listing_without_the_stock_list_pass(monkeypatch):
    k, _ = _kite(monkeypatch, ["2026-10-14"])
    monkeypatch.setattr(k, "ready", lambda: True)
    monkeypatch.setattr(main, "kite", k)                     # a follower: no instruments_of("BSE") has run here
    assert main.bse_twin("RELIANCE") == "500325"


# ---------- d: the book value per share beside a price on a new basis ----------
def test_book_value_per_share_is_left_out_when_a_split_blocks_repricing(monkeypatch):
    monkeypatch.setattr(corp_actions, "actions_for", lambda *a, **k: [{"kind": "split", "factor": 2.0, "ex_date": "2026-10-10"}])
    s = {"price": 1000.0, "pe": 25.0, "book_value": 400.0, "face_value": 10.0, "market_cap_cr": 100000.0, "div_yield": 1.0}
    out = at_live_price(s, 505.0, "X", "2026-10-09T05:00+00:00")
    assert out["price"] == 505.0 and out["pb"] is None and out["book_value"] is None
    assert out["face_value"] is None                                         # per share on the old count too (owner, 15 Oct)
    assert at_live_price(s, 200.0)["book_value"] is None                    # a move too large for a day's
    ok = at_live_price(s, 1010.0, "X", "2026-10-11T05:00+00:00")            # no split since: re-priced, book value as read
    assert ok["book_value"] == 400.0 and ok["pb"] == pytest.approx(1010.0 / 400.0)
    assert ok["face_value"] == 10.0
