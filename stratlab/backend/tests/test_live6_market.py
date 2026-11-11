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
