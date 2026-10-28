"""MWR-1: the review of Market Watch and the chart workspace. Candles of every built timeframe against an independent
count of the session's minutes (two exchanges, a holiday, a half week), a first day that is all there is, the charts a Free
person's limit counts, the broker's minute blocks kept small, and the crypto exchange's minute chunks shared."""
import random
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx
import pytest
import time_machine

from app import bar_agg, chart_feed as CF, drawings_store as DS
from app.data.coinbase import CoinbaseProvider
from tests import fake_kite, world

FREE = world.headers("free-token")
BASIC = world.headers("basic-token")


# ---------- candles: every built timeframe against an independent count ----------
def minutes_of(days, tz, open_hm, close_hm, holidays=()):
    """One-minute candles for each trading day (Monday to Friday, not a holiday): random but reproducible figures."""
    rnd, zone, out, price = random.Random(7), ZoneInfo(tz), [], 100.0
    for d in days:
        if d.weekday() >= 5 or d in holidays:
            continue
        t = datetime(d.year, d.month, d.day, *open_hm, tzinfo=zone)
        end = datetime(d.year, d.month, d.day, *close_hm, tzinfo=zone)
        while t < end:
            c = price + rnd.uniform(-0.5, 0.5)
            out.append({"t": t.isoformat(), "o": price, "h": max(price, c) + rnd.random() * 0.3, "l": min(price, c) - rnd.random() * 0.3, "c": c, "v": rnd.randint(1, 100)})
            price, t = c, t + timedelta(minutes=1)
    return out


def by_session(bars, minutes, market):
    """Independent: group each day's minutes by (day, minutes since the session's open // length), keeping the first open, the
    highest high, the lowest low, the last close and the volume of each group."""
    tz, open_min = bar_agg.SESSIONS[market]
    zone, groups = ZoneInfo(tz), {}
    for b in bars:
        d = datetime.fromisoformat(b["t"]).astimezone(zone)
        groups.setdefault((d.date(), (d.hour * 60 + d.minute - open_min) // minutes), []).append(b)
    return [(g[0]["t"], g[0]["o"], max(x["h"] for x in g), min(x["l"] for x in g), g[-1]["c"], sum(x["v"] for x in g)) for g in groups.values()]


@pytest.mark.parametrize("market,tz,open_hm,close_hm,holiday", [
    ("IN", "Asia/Kolkata", (9, 15), (15, 30), date(2026, 10, 20)),
    ("US", "America/New_York", (9, 30), (16, 0), date(2026, 10, 19)),
])
def test_every_built_timeframe_equals_the_sessions_own_minutes(market, tz, open_hm, close_hm, holiday):
    days = [date(2026, 10, 12) + timedelta(days=i) for i in range(25)]
    bars = minutes_of(days, tz, open_hm, close_hm, {holiday})
    # the sizes a source sends (5m, 15m, 1h) are the session's own too: build them the way the broker does, then derive the rest
    native = {"1m": bars, **{tf: [dict(zip("tohlcv", r)) for r in by_session(bars, bar_agg.MINUTES[tf], market)] for tf in ("5m", "15m", "1h")}}
    for tf in ("3m", "10m", "30m", "2h", "4h"):
        got = bar_agg.aggregate(native[bar_agg.BASE[tf]], tf, market)
        want = by_session(bars, bar_agg.MINUTES[tf], market)
        assert len(got) == len(want), tf
        for g, w in zip(got, want):
            assert (g["t"], g["o"], g["c"], g["v"]) == (w[0], w[1], w[4], w[5]), (tf, g, w)
            assert g["h"] == pytest.approx(w[2]) and g["l"] == pytest.approx(w[3])
        # no candle crosses a session, and each day's first candle starts at the open
        zone = ZoneInfo(bar_agg.SESSIONS[market][0])
        starts = [datetime.fromisoformat(b["t"]).astimezone(zone) for b in got]
        firsts = [s for i, s in enumerate(starts) if i == 0 or s.date() != starts[i - 1].date()]
        assert all((s.hour, s.minute) == open_hm for s in firsts), tf
        assert holiday not in {s.date() for s in starts}


def test_weekly_candles_are_monday_based_and_monthly_ones_are_calendar_months():
    ist = timezone(timedelta(hours=5, minutes=30))
    days = [datetime(2026, 9, 28, tzinfo=ist) + timedelta(days=i) for i in range(21) if (datetime(2026, 9, 28) + timedelta(days=i)).weekday() < 5]
    daily = [{"t": d.isoformat(), "o": 100 + i, "h": 110 + i, "l": 90 + i, "c": 101 + i, "v": 10} for i, d in enumerate(days)]
    weeks = bar_agg.aggregate(daily, "1w", "IN")
    assert [w["t"][:10] for w in weeks] == ["2026-09-28", "2026-10-05", "2026-10-12"]          # each week starts on its Monday and holds that week's five days, across a month's end
    assert weeks[0]["o"] == 100 and weeks[0]["c"] == 105 and weeks[0]["v"] == 50 and weeks[0]["h"] == 114 and weeks[0]["l"] == 90
    months = bar_agg.aggregate(daily, "1mo", "IN")
    assert [m["t"][:10] for m in months] == ["2026-09-28", "2026-10-01"]                      # September's last three days, then October
    assert months[0]["v"] == 30 and months[1]["o"] == 103


# ---------- a first day that is all there is stays (MWR1-006) ----------
def test_a_window_with_one_day_only_still_draws_its_candles():
    ist = ZoneInfo("Asia/Kolkata")
    t, raw = datetime(2026, 10, 26, 9, 15, tzinfo=ist), []
    while t < datetime(2026, 10, 26, 15, 30, tzinfo=ist):
        raw.append({"t": t.isoformat(), "o": 1, "h": 1, "l": 1, "c": 1, "v": 1})
        t += timedelta(minutes=1)
    # a Tuesday before the open: the three days read back hold one day of candles, and it was dropped as a "partial first day"
    assert len(CF.build(raw, "IN", "3m", None, True)) == 125
    assert len(CF.build(raw, "IN", "30m", None, True)) == 13
    # with an earlier day as well, the first (possibly short) day is still left out
    before = [{**b, "t": (datetime.fromisoformat(b["t"]) - timedelta(days=1)).replace(hour=11).isoformat()} for b in raw[:30]]
    got = CF.build(before + raw, "IN", "3m", None, True)
    assert got and all(b["t"].startswith("2026-10-26") for b in got)


# ---------- the charts a Free person's limit counts (MWR1-005) ----------
@pytest.fixture
def w(monkeypatch):
    built = world.build(monkeypatch)
    yield built
    built["close"]()


LINE = {"id": "d1", "kind": "trend", "points": [{"t": 1, "p": 1}, {"t": 2, "p": 2}]}


def test_changing_a_timeframe_does_not_use_up_a_chart_of_the_plans_limit(w):
    c = w["client"]
    c.delete("/me/drawings", headers=FREE)
    for sym in ("AAA", "BBB", "CCC", "DDD"):                                  # four charts looked at on another timeframe, nothing drawn
        assert c.put(f"/me/drawings/IN/{sym}", headers=FREE, json={"drawings": [], "layout": {"tf": "5m"}}).status_code == 200
    s = c.get("/me/drawings/summary?region=IN&symbol=EEE", headers=FREE).json()
    assert s["charts"] == 0 and s["limit"] == 3 and s["saved"] is False
    # three drawings on three charts: fine; the fourth is the one refused, in the plan's own words
    for sym in ("AAA", "BBB", "EEE"):
        assert c.put(f"/me/drawings/IN/{sym}", headers=FREE, json={"drawings": [LINE]}).status_code == 200, sym
    refused = c.put("/me/drawings/IN/FFF", headers=FREE, json={"drawings": [LINE]})
    assert refused.status_code == 402 and "keeps 3 charts" in refused.text
    # a chart that already holds a drawing stays editable, and a layout-only one is saved however many there are
    assert c.put("/me/drawings/IN/AAA", headers=FREE, json={"drawings": [LINE, {**LINE, "id": "d2"}]}).status_code == 200
    assert c.put("/me/drawings/IN/GGG", headers=FREE, json={"drawings": [], "layout": {"tf": "1h"}}).status_code == 200
    assert c.get("/me/drawings/summary?region=IN&symbol=AAA", headers=FREE).json() == {**c.get("/me/drawings/summary?region=IN&symbol=AAA", headers=FREE).json(), "charts": 3, "saved": True}
    # indicators count the same way: one on a layout makes it a chart that keeps something
    study = {"id": "s1", "type": "sma", "params": [20], "slot": 0}
    assert c.put("/me/drawings/IN/HHH", headers=FREE, json={"drawings": [], "layout": {"studies": [study]}}).status_code == 402
    # taking the last drawing off frees the chart's place
    assert c.put("/me/drawings/IN/BBB", headers=FREE, json={"drawings": [], "layout": {"tf": "5m"}}).status_code == 200
    assert c.put("/me/drawings/IN/HHH", headers=FREE, json={"drawings": [], "layout": {"studies": [study]}}).status_code == 200
    c.delete("/me/drawings", headers=FREE)


def test_a_chart_saved_before_the_marker_still_counts():
    idx = {"IN:OLD": "2026-10-01T00:00:00+00:00", "IN:NEW": "2026-10-02T00:00:00+00:00~"}
    assert DS.holds_work(idx, "IN:OLD") and not DS.holds_work(idx, "IN:NEW") and not DS.holds_work(idx, "IN:NONE")
    assert DS.kept_charts(idx) == 1


def test_drawings_are_private_to_their_owner(w):
    c = w["client"]
    c.put("/me/drawings/IN/PRIV", headers=BASIC, json={"drawings": [LINE]})
    assert c.get("/me/drawings/IN/PRIV", headers=FREE).json()["drawings"] == []
    assert c.get("/me/drawings/IN/PRIV", headers=BASIC).json()["drawings"][0]["id"] == "d1"
    assert c.delete("/me/drawings/IN/PRIV", headers=FREE).status_code == 200            # free's own (empty) row: basic's is untouched
    assert c.get("/me/drawings/IN/PRIV", headers=BASIC).json()["drawings"]
    c.delete("/me/drawings", headers=BASIC)


# ---------- the broker's minute blocks are kept small, so many charts fit (MWR1-009) ----------
def test_a_minute_block_is_kept_as_flat_numbers_and_comes_back_the_same():
    k = fake_kite.online()
    inst = next(r for r in k.kite.rows["NSE"] if r["instrument_type"] == "EQ")
    ist = ZoneInfo("Asia/Kolkata")
    now = datetime.now(ist)
    first = k.history_range(inst["instrument_token"], "1m", now - timedelta(days=3), now + timedelta(minutes=1))
    cache = k._blocks()
    assert first and all(set(b) == {"t", "o", "h", "l", "c", "v"} for b in first)
    kept = list(cache._d.values())
    assert kept and all(type(v[1]).__name__ == "array" for v in kept)
    per_candle = max(v[2] for v in kept) / max(1, len(next(iter(kept))[1]) // k.BLOCK_FIELDS)
    assert per_candle < 60                                                      # 48 bytes of numbers, not a dict of ~800
    assert k.history_range(inst["instrument_token"], "1m", now - timedelta(days=3), now + timedelta(minutes=1)) == first
    # a block of five days is a few thousand candles: well under a quarter of the budget, so 16 MB holds a hundred and more
    assert max(v[2] for v in kept) * 100 < k.BLOCK_BYTES


# ---------- the crypto exchange's minute chunks are shared, and bounded (MWR1-009) ----------
PRODUCTS = [{"id": "BTC-USD", "base_currency": "BTC", "quote_currency": "USD", "status": "online", "base_increment": "0.00000001"}]


def coinbase(state):
    def handler(r: httpx.Request):
        if r.url.path == "/products":
            return httpx.Response(200, json=PRODUCTS)
        if r.url.path.endswith("/candles"):
            state["asked"].append((r.url.params["start"], r.url.params["end"]))
            lo = datetime.fromisoformat(r.url.params["start"]).timestamp()
            hi = datetime.fromisoformat(r.url.params["end"]).timestamp()
            rows = [[int(t), 1, 2, 1.5, 1.8, 10] for t in range(int(lo // 60 * 60), int(hi), 60) if lo <= t < hi][:300]
            return httpx.Response(200, json=rows)
        return httpx.Response(404)
    return httpx.MockTransport(handler)


def test_two_reads_a_few_minutes_apart_share_the_exchanges_finished_chunks():
    state = {"asked": []}
    start = datetime(2026, 10, 24, 15, 7, 31, tzinfo=timezone.utc)
    with time_machine.travel(start, tick=False) as clock:
        p = CoinbaseProvider(transport=coinbase(state))
        inst = p.instrument("BTC-USD")
        now = datetime.now(timezone.utc)
        a = p.minute_history(inst, now - timedelta(hours=10), now)
        first = len(state["asked"])
        assert 2 <= first <= 3 and len(a) >= 598
        clock.shift(timedelta(minutes=3))                                       # the same chart opened three minutes later by someone else
        now = datetime.now(timezone.utc)
        b = p.minute_history(inst, now - timedelta(hours=10), now)
        assert len(state["asked"]) - first <= 1                                  # only the chunk holding the present is read again
        assert b[-1]["t"] > a[-1]["t"] and all(x["t"] < y["t"] for x, y in zip(b, b[1:]))
        # bounded: reading far more chunks than are kept leaves no more than MINUTE_CHUNKS
        for i in range(1, 80):
            p.minute_history(inst, now - timedelta(days=i), now - timedelta(days=i) + timedelta(hours=1))
        assert len(p.__dict__["_minutes"]) <= CoinbaseProvider.MINUTE_CHUNKS
