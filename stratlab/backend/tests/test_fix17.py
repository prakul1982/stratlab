"""Lane fix17 (LIVE13B review of Release 71), the server's side.

- LIVE13B-010 / LIVE12B-014: the Golden-cross matches DRREDDY (18 Nov) and BHARTIARTL (16 Nov) were said to disagree with the
  exchange series. Read again from the live candles, both series hold the exchange's two special sessions of the year (the
  Budget-day Sunday, 1 Feb 2026, and Diwali's Muhurat trading, Sunday 8 Nov 2026), which the reviewer's price history leaves
  out; with those two left out the reviewer's figures come back to the paisa (DRREDDY 50-day 1,254.70 / 200-day 1,256.33,
  BHARTIARTL 16 Nov 1,891.84 / 1,892.23). The averages stand (the exchange held those sessions); the match now names them,
  and the live price is the last candle once, never on top of a candle of the same day.
- LIVE12B-015: ETERNAL's "vs 52-week high" read 0.0% at its 375.05 close under the day's 378.00 high: the exchange's report of
  17 Nov still ended on 16 Nov, and its figure cut the 17 Nov candle's high back to the close.

The series are made here, shaped like the real ones: nothing is read from the network."""
from datetime import date, timedelta

from app import main  # noqa: F401, I001  (first: the app loads its jobs before the modules built on them)
from app import official_close, scan_presets, stock_pages


def _days(end: date, n: int, extra: tuple[str, ...] = ()) -> list[str]:
    """n sessions ending on `end`: weekdays, and the special sessions in `extra`."""
    out, d = [], end
    while len(out) < n:
        if d.weekday() < 5 or d.isoformat() in extra:
            out.append(d.isoformat())
        d -= timedelta(days=1)
    return out[::-1]


def _bars(days: list[str], closes: list[float]) -> list[dict]:
    return [{"t": f"{d}T00:00:00+05:30", "o": c, "h": c + 1, "l": c - 1, "c": c, "v": 1000} for d, c in zip(days, closes)]


def _cross_series(extra: tuple[str, ...]):
    """231 sessions to 18 Nov 2026: a flat stretch, a dip, then a climb whose 50-day average crosses the 200-day on the last candle."""
    closes = ([100.0] * 150 + [90.0] * 60 + [100.0 + 0.9 * k for k in range(50)])[:231]
    return _days(date(2026, 11, 18), 231, extra), closes


# ---------- LIVE13B-010: the averages of a series with special sessions, named ----------
def test_a_golden_cross_names_the_special_sessions_its_averages_count():
    days, closes = _cross_series(("2026-11-08",))
    assert "2026-11-08" in days[-200:]
    got = scan_presets.evaluate(_bars(days, closes), only=["golden_cross"])
    m = got["matches"].get("golden_cross")
    assert m, got
    # the averages are the plain means of the series as given, special session included
    i = len(days) - 1 - m["days_ago"]
    s50, s200 = sum(closes[i - 49:i + 1]) / 50, sum(closes[i - 199:i + 1]) / 200
    assert f"50-day average {s50:,.2f} crossed above the 200-day average {s200:,.2f}" in m["detail"]
    assert "the averages count the exchange's special session of 8 Nov 2026, which some price histories leave out" in m["detail"]


def test_a_series_of_weekday_sessions_says_nothing_more():
    days, closes = _cross_series(())
    m = scan_presets.evaluate(_bars(days, closes), only=["golden_cross"])["matches"]["golden_cross"]
    assert "special session" not in m["detail"]


def test_two_special_sessions_are_both_named():
    days, closes = _cross_series(("2026-03-01", "2026-11-08"))
    m = scan_presets.evaluate(_bars(days, closes), only=["golden_cross"])["matches"]["golden_cross"]
    assert "special sessions of 1 Mar 2026 and 8 Nov 2026" in m["detail"]


def test_a_holiday_session_is_special_for_a_market_with_a_calendar(monkeypatch):
    from app.data import calendar
    monkeypatch.setattr(calendar, "is_trading_day", lambda market, d: d.isoformat() != "2026-11-10")
    assert scan_presets.special_sessions(["2026-11-09", "2026-11-10", "2026-11-14"], "IN") == ["2026-11-10", "2026-11-14"]
    assert scan_presets.special_sessions(["2026-11-09", "2026-11-10"]) == []          # no market: weekends only


def test_the_live_price_is_counted_once():
    # the forming candle of today is the series' last candle: the averages hold its price once (50 closes, not 51)
    days, closes = _cross_series(())
    bars = _bars(days, closes)
    got = scan_presets.evaluate(bars, only=["golden_cross"], live=True)
    m = got["matches"]["golden_cross"]
    assert got["price"] == closes[-1] and m["days_ago"] == 0
    assert f"{sum(closes[-50:]) / 50:,.2f}" in m["detail"]


# ---------- LIVE12B-015: a session after the 52-week report's figures keeps its own high ----------
def _eternal():
    days = _days(date(2026, 11, 17), 250)
    assert days[-1] == "2026-11-17" and days[-2] == "2026-11-16"
    bars = _bars(days, [350.0] * 250)
    bars[-2].update(h=372.5, c=371.1)
    bars[-1].update(h=378.0, l=369.15, c=375.05, official=True)
    return bars


def test_a_new_high_on_a_day_the_report_does_not_cover_stands():
    bars = _eternal()
    # the report of 17 Nov ends on 16 Nov: its high is 16 Nov's, and no row names 17 Nov
    report = {"day": "2026-11-17", "rows": {"ETERNAL": [372.5, "2026-11-16", 300.0, "2026-03-02"], "OTHER": [90.0, "2026-11-16", 50.0, "2026-04-01"]}}
    through = official_close.report_through(report)
    assert through == "2026-11-16"
    fitted = stock_pages.fit_to_exchange_range(bars, report["rows"]["ETERNAL"], report["day"], through)
    facts = stock_pages.price_facts(fitted)
    assert facts["high52"] == 378.0 and round((facts["price"] / facts["high52"] - 1) * 100, 1) == -0.8
    # before the fix (no `through`): the high was cut back to the close, 0.0%
    assert stock_pages.price_facts(stock_pages.fit_to_exchange_range(bars, report["rows"]["ETERNAL"], report["day"]))["high52"] == 375.05


def test_a_stray_print_on_a_covered_day_is_still_brought_back():
    bars = _eternal()
    bars[-5]["h"] = 371.0                     # a print the exchange's report (which covers that day) doesn't have
    report = {"day": "2026-11-17", "rows": {"ETERNAL": [365.0, "2026-10-01", 300.0, "2026-03-02"], "X": [1.0, "2026-11-17", 1.0, "2026-01-02"]}}
    through = official_close.report_through(report)
    assert through == "2026-11-17"
    fitted = stock_pages.fit_to_exchange_range(bars, report["rows"]["ETERNAL"], report["day"], through)
    assert fitted[-5]["h"] == 365.0
    assert official_close.report_through(None) is None and official_close.report_through({"day": "2026-11-17", "rows": {}}) is None


def test_the_public_pages_candles_pass_the_covered_session():
    src = open(main.__file__, encoding="utf-8").read()
    body = src[src.index("def stock_page_bars("):src.index("_class_pages: dict")]
    assert "official_close.report_through(rep)" in body


# ---------- LIVE13B-012: the Trade home's India VIX tile reads only what it shows ----------
def test_the_vix_tile_reads_the_quote_only_not_the_panels_line_history_or_iv(monkeypatch):
    from datetime import datetime, timezone
    from app import vix
    calls = []
    monkeypatch.setattr(vix, "quote_now", lambda feed=None: calls.append("quote") or {"value": 15.73, "change": 0.21, "as_of": "2026-11-18T14:20:00+05:30"})
    monkeypatch.setattr(vix, "intraday", lambda feed=None: calls.append("intraday") or [])
    monkeypatch.setattr(vix, "nifty_iv", lambda *a, **k: calls.append("iv") or {"today": None, "series": []})
    monkeypatch.setattr(vix, "daily", lambda since=None, today=None: [("2026-11-17", [15.0, 16.0, 15.0, 15.52])])
    now = datetime(2026, 11, 18, 8, 50, tzinfo=timezone.utc)
    got = vix.brief_panel(object(), now)
    assert got["quote"]["value"] == 15.73 and got["value"] == 15.73 and got["value_day"] is None
    assert calls == ["quote"]
    # no quote: the newest stored close, with its day
    monkeypatch.setattr(vix, "quote_now", lambda feed=None: None)
    monkeypatch.setattr(vix, "feed_quote", lambda o, t: None)
    got = vix.brief_panel(None, now)
    assert got["value"] == 15.52 and got["value_day"] == "2026-11-17"
    # the full panel still has everything
    calls.clear()
    monkeypatch.setattr(vix, "quote_now", lambda feed=None: calls.append("quote") or {"value": 15.73, "as_of": "2026-11-18T14:20:00+05:30"})
    full = vix.panel(object(), now)
    assert "intraday" in full and "history" in full and calls[:2] == ["quote", "intraday"]


# ---------- LIVE13B-007: a fund category with no " - " part is named in the allocation, not left blank ----------
def test_a_category_without_a_sub_part_names_itself():
    from app import money_mf
    assert money_mf.broad_of("Debt Scheme", "debt") == ("Debt", "Debt Scheme")
    assert money_mf.broad_of("Gilt Fund with 10 year constant duration", "debt") == ("Debt", "Gilt Fund with 10 year constant duration")
    assert money_mf.broad_of("Debt Scheme - Short Duration Fund", "debt") == ("Debt", "Short Duration Fund")      # as before
    assert money_mf.broad_of("", "hybrid") == ("Hybrid", "")
