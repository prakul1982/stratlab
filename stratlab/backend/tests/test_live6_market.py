"""LIVE6 market-data fixes: index candles, special sessions, IPO listing day, business-update dating, theme posts, slow reads."""
from types import SimpleNamespace

from app import main  # noqa: F401, I001  (first: the app loads the newsletter job before the modules built on it)
from app.intel import company as C
from tests.test_review_r7t import StubKite, frozen_yahoo


# ---------- LIVE6-004: an index's daily candle after the close ends on the closing level Mood shows ----------
def _sensex_hub(monkeypatch, quote_price=81879.40):
    monkeypatch.setattr(C, "market_open", lambda region, now=None: False)
    monkeypatch.setattr(C, "market_today", lambda region, now=None: "2026-11-11")
    bars = [{"t": "2026-11-10T00:00:00+05:30", "o": 80900.0, "h": 81200.0, "l": 80800.0, "c": 81107.0, "v": 0.0},
            # today's candle stored during the session, at 81,504
            {"t": "2026-11-11T00:00:00+05:30", "o": 81150.0, "h": 81560.0, "l": 81100.0, "c": 81504.0, "v": 0.0}]
    k = StubKite({"BSE:SENSEX": {"price": quote_price, "open": 81150.0, "high": 81900.0, "low": 81100.0,
                                 "at": "2026-11-11T15:30:00+05:30"}}, bars)
    return C.Research(k, finnhub=SimpleNamespace(ready=lambda: False), yahoo=frozen_yahoo()), k


def test_the_sensex_candle_after_the_close_is_the_close(monkeypatch):
    hub, k = _sensex_hub(monkeypatch)
    got = hub.chart("IN", "^BSESN", "1m", "1d")["candles"]
    assert len(got) == 2 and got[-1]["c"] == 81879.40 and got[-1]["h"] == 81879.40 and got[-1]["o"] == 81150.0
    assert round((got[-1]["c"] / got[-2]["c"] - 1) * 100, 2) == 0.95
    # the quote is kept a minute: a second visit doesn't ask the broker again
    k.quotes = {}
    assert hub.chart("IN", "^BSESN", "1m", "1d")["candles"][-1]["c"] == 81879.40


def test_the_pulse_level_mood_shows_is_the_one_the_candle_takes(monkeypatch):
    import time
    hub, k = _sensex_hub(monkeypatch, quote_price=1.0)
    levels, _ = hub._snaps()
    levels.put("IN", [{"name": "SENSEX", "price": 81879.40, "at": "2026-11-11T15:30:00+05:30", "pre_close": False}], time.time())
    assert hub.chart("IN", "^BSESN", "1m", "1d")["candles"][-1]["c"] == 81879.40
    # a pulse reading from before the close is not used: the live quote is
    levels.put("IN", [{"name": "SENSEX", "price": 81504.0, "at": "2026-11-11T14:10:00+05:30", "pre_close": True}], time.time())
    hub.__dict__.pop("_index_levels", None)
    k.quotes["BSE:SENSEX"]["price"] = 81879.40
    assert hub.chart("IN", "^BSESN", "1m", "1d")["candles"][-1]["c"] == 81879.40


def test_a_previous_sessions_quote_never_changes_todays_candles(monkeypatch):
    hub, k = _sensex_hub(monkeypatch)
    k.quotes["BSE:SENSEX"]["at"] = "2026-11-10T15:30:00+05:30"
    assert hub.chart("IN", "^BSESN", "1m", "1d")["candles"][-1]["c"] == 81504.0


def test_a_stock_candle_out_of_hours_is_left_as_read(monkeypatch):
    monkeypatch.setattr(C, "market_open", lambda region, now=None: False)
    monkeypatch.setattr(C, "market_today", lambda region, now=None: "2026-11-11")
    k = StubKite({}, [{"t": "2026-11-11T00:00:00+05:30", "o": 1.0, "h": 2.0, "l": 1.0, "c": 1.5, "v": 1.0}])
    k.quote = lambda syms: (_ for _ in ()).throw(AssertionError("no quote for a stock's candles out of hours"))
    hub = C.Research(k, finnhub=SimpleNamespace(ready=lambda: False), yahoo=frozen_yahoo())
    assert hub.chart("IN", "RELIANCE", "1y", "1d")["candles"][-1]["c"] == 1.5


# ---------- LIVE6-011: a special session (Muhurat, Sunday 8 Nov) is a session in the index series ----------
def test_a_muhurat_sunday_is_the_session_before_monday(monkeypatch):
    from datetime import date
    from app.data import calendar as cal
    from app.newsletter import content
    monkeypatch.setattr(cal, "_special", {"IN": (9e18, set())})          # nothing from the exchange's lists
    monkeypatch.setattr(cal, "_noted", {})
    assert content.previous_trading_day("IN", date(2026, 11, 9)) == date(2026, 11, 6)
    cal.note_session("IN", "2026-11-08")
    assert cal.had_session("IN", date(2026, 11, 8)) and not cal.is_trading_day("IN", date(2026, 11, 8))
    assert content.previous_trading_day("IN", date(2026, 11, 9)) == date(2026, 11, 8)
    assert not cal.had_session("US", date(2026, 11, 8))


def test_the_exchanges_weekend_candle_is_noted_as_a_session(monkeypatch):
    from app.data import calendar as cal
    from app.kite_service import KiteService
    monkeypatch.setattr(cal, "_noted", {})
    KiteService._note_sessions([{"t": "2026-11-06T00:00:00+05:30"}, {"t": "2026-11-08T00:00:00+05:30"}, {"t": "2026-11-09T00:00:00+05:30"}])
    assert cal._noted == {"IN": {"2026-11-08"}}


def test_the_brief_measures_monday_from_the_muhurat_close(monkeypatch):
    from datetime import date
    from app import main
    from app.data import calendar as cal
    from app.newsletter import content
    monkeypatch.setattr(cal, "_special", {"IN": (9e18, {"2026-11-08"})})
    monkeypatch.setattr(content, "_cache", type(content._cache)(max_items=10))
    yahoo = [{"t": f"{d}T00:00:00+05:30", "c": c} for d, c in (("2026-11-05", 24800.0), ("2026-11-06", 24928.0), ("2026-11-09", 25043.85))]
    kite = [{"t": f"{d}T00:00:00+05:30", "c": c} for d, c in (("2026-11-06", 24928.0), ("2026-11-08", 24986.40), ("2026-11-09", 25043.85))]
    monkeypatch.setattr(main.research_hub.yahoo, "chart", lambda *a, **k: {"meta": {}, "candles": list(yahoo)})
    monkeypatch.setattr(main.research_hub, "chart", lambda *a, **k: {"source": "Kite", "candles": list(kite)})
    got = content.index_close("^NSEI", date(2026, 11, 9), prev=content.previous_trading_day("IN", date(2026, 11, 9)).isoformat())
    assert got == {"price": 25043.85, "change_pct": 0.23}
    # the broker offline: the session before is missing, so no change is given (never one from 6 Nov)
    monkeypatch.setattr(main.research_hub, "chart", lambda *a, **k: {"source": "Yahoo Finance", "candles": list(yahoo)})
    assert content.index_close("^NSEI", date(2026, 11, 9), prev="2026-11-08") == {"price": 25043.85, "change_pct": None}


# ---------- LIVE6-010: an issue listing today shows its listing price from the open ----------
def test_an_issue_on_its_listing_day_has_its_listing_price_before_the_close():
    from datetime import date, datetime
    from zoneinfo import ZoneInfo
    from app import ipo as I
    bars = [{"t": "2026-11-11T00:00:00+05:30", "o": 52.80, "h": 53.0, "l": 50.0, "c": 50.16, "v": 1.0}]
    asked = []

    class Y:
        def chart(self, sym, tf, days):
            asked.append(sym)
            return {"candles": list(bars)}
    row = {"market": "IN", "symbol": None, "bse_code": "123", "bse_scrip": None, "listed_as": "ANTALA", "segment": "sme",
           "listing": "2026-11-11", "price": 66.0}
    noon = datetime(2026, 11, 11, 13, 40, tzinfo=ZoneInfo("Asia/Kolkata"))
    p = I.performance(row, Y(), date(2026, 11, 11), noon)
    assert asked == ["ANTALA.BO"]
    assert (p["listing_price"], p["listing_change_pct"], p["latest"], p["day_close"]) == (52.80, -20.0, None, None)
    # after the close the day's close is in
    eve = datetime(2026, 11, 11, 20, 10, tzinfo=ZoneInfo("Asia/Kolkata"))
    p = I.performance(row, Y(), date(2026, 11, 11), eve)
    assert (p["listing_price"], p["day_close"], p["latest"]) == (52.80, 50.16, 50.16)
    # the BSE scrip code, when kept, is the symbol as before
    assert I.yahoo_symbol({**row, "bse_scrip": "544700"}) == "544700.BO"


# ---------- LIVE6-009: business updates dated by their own fiscal year; implausible year-on-year moves held back ----------
def _read(at, period, figures, span="month"):
    return {"at": at, "title": "update", "url": f"https://nsearchives.nseindia.com/corporate/{at}.pdf", "read_at": at, "period": period,
            "span": span, "problem": None, "reader": 3,
            "figures": [{"segment": None, "unit": "units", "basis": "month", "prior": None, "headline": True, "quote": "q", "page": 1,
                         "own": True, **f} for f in figures]}


def test_a_figure_named_by_its_fiscal_year_is_dated_at_that_years_end():
    from app import biz_updates as B
    assert B.fy_period({"metric": "Consolidated revenue (FY 2024)"}, "2025-03") == "2024-03"
    assert B.fy_period({"metric": "Revenue FY2023-24"}, "2025-03") == "2024-03"
    assert B.fy_period({"metric": "Deposits", "segment": "Q2 FY27"}, "2026-10") == "2026-09"
    assert B.fy_period({"metric": "Total sales"}, "2026-10") == "2026-10"
    assert B.fy_period({"metric": "Revenue FY 2027"}, "2026-10") == "2026-10"          # a year not over by the filing: the filing's period
    ms = B.series({"r": _read("2025-04-25T18:00", "2025-03", [{"metric": "Consolidated revenue (FY 2024)", "value": 1000122, "unit": "Rs crore"}])})
    assert ms[0]["latest"]["period"] == "2024-03"


def test_an_implausible_year_on_year_move_waits_for_the_filing_to_confirm_it():
    from app import biz_updates as B
    ago = _read("2025-11-01T12:00", "2025-10", [{"metric": "Total sales", "value": 30000}])
    now = _read("2026-11-01T12:00", "2026-10", [{"metric": "Total sales", "value": 60300}])
    m = B.series({"a": ago, "b": now})[0]
    assert m["change_year"] is None and m["year_unconfirmed"] and m["year_ago"]["value"] == 30000
    assert "on Oct 2025" not in B.words(m)
    # the newest filing states the same year-ago figure: the move stands
    now["figures"][0]["prior"] = 30000
    m = B.series({"a": ago, "b": now})[0]
    assert m["change_year"] == 101.0 and not m["year_unconfirmed"]
    # a fall to a tenth, the filing's own year-ago figure another one: held back
    now["figures"][0].update(value=3180, prior=12000)
    assert B.series({"a": ago, "b": now})[0]["change_year"] is None
    # an ordinary move is shown as before
    now["figures"][0].update(value=33000, prior=None)
    assert B.series({"a": ago, "b": now})[0]["change_year"] == 10.0


def test_this_months_filing_is_read_before_older_rereads_for_a_company_short_of_months(monkeypatch):
    from datetime import date, timedelta
    from app import biz_updates as B
    today = date.today()
    items = [{"id": f"f{i}", "at": (today - timedelta(days=d)).isoformat() + "T12:00"} for i, d in enumerate((10, 40, 70, 100, 130))]
    old = {i["id"]: {**_read(i["at"], "2026-01", [{"metric": "Total", "value": 1}]), "reader": 1} for i in items[2:]}
    monkeypatch.setattr(B, "stored", lambda sym: dict(old))
    monkeypatch.setattr(B, "candidates", lambda its: list(its))
    monkeypatch.setattr(B, "_ai_budget", lambda: True)
    monkeypatch.setattr(B, "save", lambda *a: None)
    seen = []
    monkeypatch.setattr(B, "read_one", lambda sym, item, d, ai, known: seen.append(item["id"]) or _read(item["at"], "2026-10", [{"metric": "Total", "value": 2}]))
    B.read_new("MARUTI", items, None, None, limit=3)                      # no `since`: still short of its months
    assert seen == ["f0", "f1", "f2"]
