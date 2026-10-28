"""MW-1: candles of every timeframe. Built candles (3m, 10m, 30m, 2h, 4h, 1W, 1M) against figures worked out by hand, on each
exchange's own session clock; the 1-minute reads (the broker's blocks, shared and bounded), the pacing of the broker's
requests, and how the chart's two candle routes answer for every size, live or delayed."""
import time
from datetime import datetime, timedelta, timezone

import pytest

from app import bar_agg, chart_data as CD, chart_feed as CF
from tests import fake_kite, world

IST = timezone(timedelta(hours=5, minutes=30))
PRO = world.headers("pro-token")


def bar(t, o, h, l, c, v):
    return {"t": t, "o": o, "h": h, "l": l, "c": c, "v": v}


def india_hours(day="2026-10-23"):
    """One India session of hourly candles as the broker sends them: 09:15 to 15:15, seven of them, each with its own figures."""
    rows = [(100, 105, 99, 104, 10), (104, 108, 103, 107, 20), (107, 109, 101, 102, 30), (102, 104, 100, 103, 40),
            (103, 110, 102, 109, 50), (109, 111, 107, 108, 60), (108, 112, 106, 111, 70)]
    return [bar(f"{day}T{9 + i:02d}:15:00+05:30", *r) for i, r in enumerate(rows)]


def test_two_hour_candles_start_on_the_indian_session_clock():
    got = bar_agg.aggregate(india_hours(), "2h", "IN")
    assert [b["t"] for b in got] == ["2026-10-23T09:15:00+05:30", "2026-10-23T11:15:00+05:30", "2026-10-23T13:15:00+05:30",
                                     "2026-10-23T15:15:00+05:30"]
    # 09:15 + 10:15: open of the first, highest high, lowest low, close of the last, volumes added
    assert got[0] == bar("2026-10-23T09:15:00+05:30", 100, 108, 99, 107, 30)
    assert got[1] == bar("2026-10-23T11:15:00+05:30", 107, 109, 100, 103, 70)       # 11:15 + 12:15
    assert got[2] == bar("2026-10-23T13:15:00+05:30", 103, 111, 102, 108, 110)      # 13:15 + 14:15
    assert got[3] == bar("2026-10-23T15:15:00+05:30", 108, 112, 106, 111, 70)       # the last half hour's own candle


def test_four_hour_candles_are_two_a_session():
    got = bar_agg.aggregate(india_hours(), "4h", "IN")
    assert got[0] == bar("2026-10-23T09:15:00+05:30", 100, 109, 99, 103, 100)       # 09:15 to 12:15, four hourly candles
    assert got[1] == bar("2026-10-23T13:15:00+05:30", 103, 112, 102, 111, 180)      # 13:15, 14:15 and 15:15
    assert len(got) == 2


def test_a_candle_never_runs_across_two_sessions():
    two_days = india_hours("2026-10-22") + india_hours("2026-10-23")
    got = bar_agg.aggregate(two_days, "4h", "IN")
    assert [b["t"][:16] for b in got] == ["2026-10-22T09:15", "2026-10-22T13:15", "2026-10-23T09:15", "2026-10-23T13:15"]


def test_us_candles_start_at_half_past_nine_new_york():
    et = timezone(timedelta(hours=-4))
    hours = [bar((datetime(2026, 10, 23, 9, 30, tzinfo=et) + timedelta(hours=i)).isoformat(), 10 + i, 11 + i, 9 + i, 10.5 + i, 100) for i in range(7)]
    got = bar_agg.aggregate(hours, "2h", "US")
    assert [b["t"][11:16] for b in got] == ["09:30", "11:30", "13:30", "15:30"]
    assert got[0]["o"] == 10 and got[0]["c"] == 11.5 and got[0]["h"] == 12 and got[0]["l"] == 9 and got[0]["v"] == 200


def test_the_same_instants_in_another_zone_land_in_the_exchanges_candles():
    """A source that sends UTC times gets the same India candles: the session clock is the exchange's, not the sender's."""
    utc = [{**b, "t": datetime.fromisoformat(b["t"]).astimezone(timezone.utc).isoformat()} for b in india_hours()]
    got = bar_agg.aggregate(utc, "2h", "IN")
    assert [b["t"] for b in got][:2] == ["2026-10-23T09:15:00+05:30", "2026-10-23T11:15:00+05:30"]


def test_three_minute_and_ten_minute_candles():
    ones = [bar(f"2026-10-23T09:{15 + i:02d}:00+05:30", 100 + i, 101 + i, 99 + i, 100.5 + i, 10) for i in range(7)]
    three = bar_agg.aggregate(ones, "3m", "IN")
    assert [b["t"][11:16] for b in three] == ["09:15", "09:18", "09:21"]
    assert three[0] == bar("2026-10-23T09:15:00+05:30", 100, 103, 99, 102.5, 30)
    assert three[2] == bar("2026-10-23T09:21:00+05:30", 106, 107, 105, 106.5, 10)        # a lone minute: the forming candle
    fives = [bar(f"2026-10-23T09:{15 + 5 * i:02d}:00+05:30", 50 + i, 52 + i, 49 + i, 51 + i, 7) for i in range(4)]
    ten = bar_agg.aggregate(fives, "10m", "IN")
    assert [b["t"][11:16] for b in ten] == ["09:15", "09:25"]
    assert ten[0] == bar("2026-10-23T09:15:00+05:30", 50, 53, 49, 52, 14) and ten[1]["c"] == 54


def test_thirty_minute_candles_are_cut_from_the_session_open():
    quarters = [bar(f"2026-10-23T{9 + (15 + 15 * i) // 60:02d}:{(15 + 15 * i) % 60:02d}:00+05:30", 1 + i, 2 + i, i, 1.5 + i, 1) for i in range(6)]
    got = bar_agg.aggregate(quarters, "30m", "IN")
    assert [b["t"][11:16] for b in got] == ["09:15", "09:45", "10:15"]


def test_weekly_candles_run_monday_to_friday_and_are_stamped_with_their_first_day():
    days = [bar(f"2026-10-{d:02d}T00:00:00+05:30", d, d + 2, d - 1, d + 1, 1) for d in (15, 16, 19, 20, 21, 22, 23)]   # Thu, Fri, then Mon..Fri
    got = bar_agg.aggregate(days, "1w", "IN")
    assert [b["t"][:10] for b in got] == ["2026-10-15", "2026-10-19"]
    assert got[0] == bar("2026-10-15T00:00:00+05:30", 15, 18, 14, 17, 2)
    assert got[1] == bar("2026-10-19T00:00:00+05:30", 19, 25, 18, 24, 5)


def test_monthly_candles_are_the_calendar_month():
    days = [bar(f"2026-{m:02d}-{d:02d}T00:00:00+05:30", 10 * m + d, 10 * m + d + 5, 10 * m + d - 5, 10 * m + d + 1, 3)
            for m, d in ((9, 29), (9, 30), (10, 1), (10, 23))]
    got = bar_agg.aggregate(days, "1mo", "IN")
    assert [b["t"][:10] for b in got] == ["2026-09-29", "2026-10-01"]
    assert got[0]["o"] == 119 and got[0]["c"] == 121 and got[0]["h"] == 125 and got[0]["l"] == 114 and got[0]["v"] == 6


def test_crypto_candles_follow_the_utc_day_and_a_sent_size_is_returned_as_it_is():
    hours = [bar(f"2026-10-23T{h:02d}:00:00+00:00", h, h + 1, h - 1, h, 1) for h in range(0, 9)]
    got = bar_agg.aggregate(hours, "4h", "CRYPTO")
    assert [b["t"][11:16] for b in got] == ["00:00", "04:00", "08:00"]
    assert bar_agg.aggregate(hours, "1h", "CRYPTO") is hours
    assert bar_agg.aggregate([], "4h", "IN") == []


def test_every_timeframe_has_a_base_that_a_source_sends():
    for tf in bar_agg.TFS:
        assert bar_agg.base_of(tf) in bar_agg.NATIVE
    assert bar_agg.base_of("2h") == "1h" and bar_agg.base_of("3m") == "1m" and bar_agg.base_of("1w") == "1d"
    assert set(CD.FIRST) == set(CD.PAGE) == set(bar_agg.TFS)


def test_a_built_page_drops_its_short_first_day_when_older_candles_exist():
    two = india_hours("2026-10-22")[3:] + india_hours("2026-10-23")        # the read began part way through the 22nd
    full = CF.build(two, "IN", "2h", None, more=False)
    assert full[0]["t"].startswith("2026-10-22")
    paged = CF.build(two, "IN", "2h", None, more=True)
    assert paged[0]["t"].startswith("2026-10-23")
    # and with `until` only candles that start before it
    before = CF.build(india_hours("2026-10-22") + india_hours("2026-10-23"), "IN", "2h", datetime(2026, 10, 23, 9, 15, tzinfo=IST), more=False)
    assert before and all(b["t"].startswith("2026-10-22") for b in before)


def test_minute_windows_page_back_from_the_first_candle_not_from_now():
    now = datetime(2026, 10, 24, 12, tzinfo=timezone.utc)
    start, end, more = CF.minute_window("1m", "kite", None, now)
    assert (end - start).days == 3 and more and end > now
    until = datetime(2026, 9, 1, 4, tzinfo=timezone.utc)
    s2, e2, more2 = CF.minute_window("1m", "kite", until, now)
    assert e2 == until and (e2 - s2).days == 5 and more2                       # five days before it: no reread of the weeks between
    # the delayed source keeps a week: nothing older, and it says so
    s3, e3, more3 = CF.minute_window("1m", "delayed", datetime(2026, 10, 10, tzinfo=timezone.utc), now)
    assert more3 is False and s3 >= now - timedelta(days=7)
    assert CF.minute_window("3m", "kite", None, now)[0] == now + timedelta(minutes=1) - timedelta(days=5)


def test_delivery_says_live_only_for_the_brokers_and_the_crypto_exchanges_candles():
    assert CF.delivery("IN", True) == {"live": True, "delayed": False}
    assert CF.delivery("IN", False) == {"live": False, "delayed": True}      # no broker login today: never shown as live
    assert CF.delivery("US", True) == {"live": False, "delayed": True}
    assert CF.delivery("CRYPTO", False) == {"live": True, "delayed": False}
    assert CF.delivery("MCX", True)["live"] and CF.delivery("FX", True)["delayed"]
    assert CF.minute_kind("IN", False) == "delayed" and CF.minute_kind("IN", True) == "kite" and CF.minute_kind("CRYPTO") == "crypto"


# ---------- the broker's minute candles: blocks, sharing, pacing ----------
def kite_now(monkeypatch=None):
    return fake_kite.online()


def test_minute_blocks_are_shared_and_a_scroll_back_asks_for_one_more_block():
    k = kite_now()
    fake = k.kite
    inst = next(r for r in fake.rows["NSE"] if r["instrument_type"] == "EQ")
    tok = inst["instrument_token"]
    now = datetime.now(IST)
    a = k.history_range(tok, "1m", now - timedelta(days=3), now + timedelta(minutes=1))
    calls = fake.calls
    again = k.history_range(tok, "1m", now - timedelta(days=3), now + timedelta(minutes=1))
    assert a == again and fake.calls == calls                                      # a second viewer costs no request
    older = k.history_range(tok, "1m", now - timedelta(days=13), now - timedelta(days=8))
    assert fake.calls > calls and fake.calls - calls <= 3                           # five days back: one or two blocks, not the weeks between
    assert all(older[i]["t"] < older[i + 1]["t"] for i in range(len(older) - 1))
    assert all(b["t"] < (now - timedelta(days=8)).isoformat() for b in older)


def test_minute_blocks_are_bounded_by_bytes():
    k = kite_now()
    cache = k._blocks()
    assert cache.max_bytes == k.BLOCK_BYTES and cache.max == 400
    assert k.BLOCK_BYTES <= 16 * 1024 * 1024          # the minute blocks stay a small share of a $20/month server


def test_the_brokers_requests_are_paced_in_the_order_they_asked():
    k = fake_kite.online()
    k.GAP = 0.05
    k._throttle = type(k)._throttle.__get__(k)               # the real pacing, not the fake's no-op
    k._last_call = 0.0
    stamps = []
    for _ in range(4):
        k._throttle()
        stamps.append(time.time())
    gaps = [b - a for a, b in zip(stamps, stamps[1:])]
    assert all(g >= 0.045 for g in gaps), gaps


# ---------- the two candle routes ----------
@pytest.fixture
def w(monkeypatch):
    built = world.build(monkeypatch)
    yield built
    built["close"]()


def test_company_chart_serves_every_timeframe_and_says_how_current_it_is(w):
    c = w["client"]
    for tf in bar_agg.TFS:
        r = c.get(f"/research/chart/IN/INFY?tf={tf}", headers=PRO)
        assert r.status_code == 200, (tf, r.text[:200])
        got = r.json()
        assert got["tf"] == tf and got["candles"], tf
        assert got["live"] is True and got["delayed"] is False, tf        # the test world's broker is on
        ts = [b["t"] for b in got["candles"]]
        assert ts == sorted(ts) and len(set(ts)) == len(ts), tf
    us = c.get("/research/chart/US/AAPL?tf=2h", headers=PRO).json()
    assert us["delayed"] is True and us["live"] is False and us["candles"]
    assert c.get("/research/chart/IN/INFY?tf=7m", headers=PRO).status_code == 400


def test_a_two_hour_company_candle_is_the_two_hours_it_covers(w):
    c = w["client"]
    hours = c.get("/research/chart/IN/INFY?tf=1h", headers=PRO).json()["candles"]
    two = c.get("/research/chart/IN/INFY?tf=2h", headers=PRO).json()["candles"]
    by = {b["t"]: b for b in two}
    day = two[-1]["t"][:10]
    inside = [b for b in hours if b["t"][:10] == day and b["t"][11:16] in ("09:15", "10:15")]
    first = by.get(f"{day}T09:15:00+05:30")
    if first and len(inside) == 2:
        assert first["o"] == inside[0]["o"] and first["c"] == inside[1]["c"]
        assert first["h"] == max(b["h"] for b in inside) and first["l"] == min(b["l"] for b in inside)
        assert first["v"] == pytest.approx(sum(b["v"] for b in inside))


def test_the_brokers_login_off_the_company_chart_is_delayed_not_live(w, monkeypatch):
    c = w["client"]
    main = w["main"] if "main" in w else __import__("app.main", fromlist=["x"])
    monkeypatch.setattr(main.kite, "invalid_reason", "the login ended")
    got = c.get("/research/chart/IN/INFY?tf=1m", headers=PRO)
    assert got.status_code == 200
    body = got.json()
    assert body["live"] is False and body["delayed"] is True


def test_registry_candles_for_every_timeframe_and_an_older_page(w):
    c = w["client"]
    inst = c.get("/instruments/search?q=INFY&market=IN", headers=PRO).json()[0]
    for tf in ("1m", "3m", "10m", "30m", "2h", "4h", "1w", "1mo"):
        r = c.get(f"/chart/candles/{inst['id']}?tf={tf}", headers=PRO)
        assert r.status_code == 200, (tf, r.text[:200])
        assert r.json()["tf"] == tf and r.json()["live"] is True
    one = c.get(f"/chart/candles/{inst['id']}?tf=1m", headers=PRO).json()
    assert one["candles"] and one["more"] is True
    first = one["candles"][0]["t"]
    older = c.get(f"/chart/candles/{inst['id']}?tf=1m&before={first.replace('+', '%2B')}", headers=PRO).json()
    assert all(b["t"] < first for b in older["candles"])
    usd = c.get("/chart/candles/US:AAPL?tf=4h", headers=PRO).json()
    assert usd["delayed"] is True and usd["live"] is False


def test_crypto_minutes_and_hours_are_live_and_forex_is_delayed(w):
    c = w["client"]
    btc = c.get("/instruments/search?q=BTC&market=CRYPTO", headers=PRO).json()[0]
    one = c.get(f"/chart/candles/{btc['id']}?tf=1m", headers=PRO).json()
    assert one["live"] is True and one["candles"] and len(one["candles"]) <= 2000
    four = c.get(f"/chart/candles/{btc['id']}?tf=4h", headers=PRO).json()
    assert four["live"] is True and four["candles"][0]["t"][11:16] in ("00:00", "04:00", "08:00", "12:00", "16:00", "20:00")
    fx = c.get("/chart/candles/FX:EURUSD=X?tf=1m", headers=PRO)
    assert fx.status_code == 200 and fx.json()["delayed"] is True and fx.json()["live"] is False
