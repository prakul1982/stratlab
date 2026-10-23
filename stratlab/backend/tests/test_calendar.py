from datetime import date, datetime, timedelta, timezone

from app import daily_report
from app.data import calendar
from app.kite_service import IST, token_valid
from app.options import recorder


def test_every_market_says_where_its_holidays_come_from_and_how_far_ahead(monkeypatch):
    from app import platform_check
    calendar._extra.clear()
    monkeypatch.setattr(calendar, "extra_holidays", lambda m: set())
    monkeypatch.setattr(calendar, "auto_status", lambda m="IN": {})
    rows = {r["market"]: r for r in calendar.all_coverage(date(2026, 10, 4))}
    assert list(rows) == ["IN", "MCX", "CDS", "US", "UK", "EU", "JP", "CMDTY", "CRYPTO", "FX"]
    assert rows["IN"]["source"] == "Exchange's own list, read daily" and rows["CDS"]["source"] == rows["IN"]["source"]
    assert rows["US"]["source"] == "Built-in calendar rules"
    for m in ("CRYPTO", "FX"):
        assert rows[m]["source"] == "No exchange holidays (24/7 / weekdays)" and rows[m]["state"] == "none" and rows[m]["next"] is None
    us = rows["US"]
    assert us["state"] == "ok" and us["days_left"] >= 60 and us["next"] == "2026-11-26" and us["next_name"] == "Thanksgiving"
    assert rows["JP"]["next_name"] == "Health and Sports Day"           # the "(2022 onwards)" note is dropped
    assert rows["IN"]["known_until"] == calendar.known_until("IN").isoformat()
    # close to the end of what's known: a warning, with what to do about it
    late = calendar.coverage("US", calendar.known_until("US") - timedelta(days=30))
    assert late["state"] == "warn" and late["days_left"] == 30 and "exchange_calendars" in late["hint"]
    ind = calendar.coverage("IN", calendar.known_until("IN") - timedelta(days=10))
    assert ind["state"] == "warn" and "paste" in ind["hint"]
    # the platform check: one row, a warning naming the markets that run short
    near = calendar.known_until("IN") - timedelta(days=20)
    res = platform_check.check_calendar(near)
    assert res["state"] == "warn" and "India (NSE/BSE) (20 days)" in res["detail"] and "Crypto" not in res["detail"]
    assert platform_check.check_calendar(calendar.known_until("IN") - timedelta(days=200))["state"] == "pass"


def test_the_exchanges_list_extends_indias_coverage(monkeypatch):
    calendar._extra.clear()
    monkeypatch.setattr(calendar, "extra_holidays", lambda m: {"2027-03-22"})
    monkeypatch.setattr(calendar, "auto_status", lambda m="IN": {"days": ["2027-03-22", "2027-01-26"]} if m == "IN" else {})
    assert calendar.covered_until("IN") == date(2027, 12, 31) and calendar.covered_until("MCX") == date(2027, 12, 31)
    assert calendar.covered_until("US") == calendar.known_until("US")       # the exchange's list is India's only
    row = calendar.coverage("IN", date(2027, 3, 1))
    assert row["next"] == "2027-03-22" and row["state"] == "ok"
    assert calendar.coverage("IN", date(2027, 1, 20))["next_name"] == "Republic Day"
    calendar._holiday_cache.clear()


def test_exchange_holidays_weekends_and_always_open_markets():
    assert not calendar.is_trading_day("IN", date(2025, 10, 2))          # Gandhi Jayanti
    assert calendar.is_holiday("IN", date(2025, 10, 2))
    assert calendar.is_trading_day("IN", date(2025, 10, 3))
    assert not calendar.is_trading_day("US", date(2025, 12, 25))          # Christmas
    assert not calendar.is_trading_day("UK", date(2025, 12, 26))          # Boxing Day
    assert not calendar.is_trading_day("IN", date(2025, 9, 27))           # a Saturday
    assert not calendar.is_holiday("IN", date(2025, 9, 27))               # weekends aren't "holidays"
    assert calendar.is_trading_day("CRYPTO", date(2025, 9, 27))
    assert calendar.is_trading_day("FX", date(2025, 12, 25)) and not calendar.is_trading_day("FX", date(2025, 9, 27))
    assert "2025-10-02" in calendar.holidays("IN", date(2025, 9, 25), 30)
    assert calendar.is_trading_day("IN", date(2031, 6, 3))                # past the published calendar: weekdays count


def test_report_and_recorder_skip_holidays():
    holiday = datetime(2025, 10, 2, 10, 15, tzinfo=timezone.utc)             # 15:45 India time, report window
    assert daily_report.due("IN", holiday) is None
    assert daily_report.due("IN", datetime(2025, 10, 3, 10, 15, tzinfo=timezone.utc)) == "2025-10-03"
    assert daily_report.due("CRYPTO", datetime(2025, 10, 2, 23, 57, tzinfo=timezone.utc)) == "2025-10-02"
    assert not recorder.in_hours(datetime(2025, 10, 2, 6, 0, tzinfo=timezone.utc))      # 11:30 IST on the holiday
    assert recorder.in_hours(datetime(2025, 10, 3, 6, 0, tzinfo=timezone.utc))


def test_kite_token_lasts_until_the_6am_reset():
    at = lambda d, h, m=0: datetime(2025, 10, d, h, m, tzinfo=IST)
    assert token_valid("2025-10-03", at(3, 9))
    assert token_valid("2025-10-03", at(4, 0, 30))                           # just after midnight: still fine
    assert token_valid("2025-10-03", at(4, 5, 59))
    assert not token_valid("2025-10-03", at(4, 6, 0))                        # Zerodha's reset
    assert not token_valid("2025-10-02", at(4, 1))
    assert not token_valid(None, at(4, 1))


def test_next_login_says_when_indian_data_returns(monkeypatch):
    from app import kite_auto
    from app.config import settings
    for k in ("KITE_USER_ID", "KITE_PASSWORD", "KITE_TOTP_SECRET"):
        monkeypatch.setattr(settings, k, "x")
    monkeypatch.setattr(settings, "KITE_AUTO_LOGIN_AT", "08:10")
    al = kite_auto.AutoLogin(kite=None, on_login=lambda: None)
    assert al.next_login(datetime(2025, 10, 4, 6, 30, tzinfo=IST)) == datetime(2025, 10, 4, 8, 10, tzinfo=IST)
    assert al.next_login(datetime(2025, 10, 4, 9, 0, tzinfo=IST)) is None          # past it: if still offline, it failed
    monkeypatch.setattr(settings, "KITE_TOTP_SECRET", "")
    assert al.next_login(datetime(2025, 10, 4, 6, 30, tzinfo=IST)) is None          # no auto-login set up


def test_a_database_error_is_not_kept_as_no_holidays(monkeypatch):
    import time
    from app import db
    calendar._extra.clear()
    monkeypatch.setattr(db, "get_setting", lambda k: (_ for _ in ()).throw(RuntimeError("down")))
    assert calendar.extra_holidays("IN") == set()
    assert time.time() - calendar._extra["IN"][0] > 500        # asked again within about 30 s, not ten minutes
    monkeypatch.setattr(db, "get_setting", lambda k: '["2027-03-22"]' if k == calendar.SETTING + "IN" else None)
    calendar._extra["IN"] = (time.time() - 40 - 570, set())
    assert calendar.extra_holidays("IN") == {"2027-03-22"}
    calendar._extra.clear()


def test_a_fresh_exchange_list_replaces_the_days_inside_its_span(monkeypatch):
    import json
    from app import db
    store = {}
    monkeypatch.setattr(db, "get_setting", lambda k: store.get(k))
    monkeypatch.setattr(db, "set_setting", lambda k, v: store.__setitem__(k, v))
    store[calendar.AUTO + "IN"] = json.dumps({"days": ["2025-11-05", "2026-03-04", "2026-08-15", "2026-10-02"], "at": "x"})
    state = calendar.refresh_from_exchange(lambda: ["2026-01-26", "2026-03-03", "2026-10-02", "2026-12-25"], "IN")
    # 4 Mar and 15 Aug fall inside the span of the new list (26 Jan to 25 Dec) and are not in it: dropped (moved or withdrawn);
    # 5 Nov 2025 is before the span: kept
    assert state["days"] == ["2025-11-05", "2026-01-26", "2026-03-03", "2026-10-02", "2026-12-25"]
    assert json.loads(store[calendar.AUTO + "IN"])["days"] == state["days"]
    later = calendar.refresh_from_exchange(lambda: ["2027-01-26", "2027-03-22"], "IN")      # next year's list: this year's days stay
    assert later["days"] == state["days"] + ["2027-01-26", "2027-03-22"]


def test_an_empty_or_failed_exchange_list_keeps_the_last_good_one(monkeypatch):
    import json
    from app import db
    store = {calendar.AUTO + "IN": json.dumps({"days": ["2026-10-02"], "at": "x"})}
    monkeypatch.setattr(db, "get_setting", lambda k: store.get(k))
    monkeypatch.setattr(db, "set_setting", lambda k, v: store.__setitem__(k, v))
    for fetch in (lambda: [], lambda: (_ for _ in ()).throw(RuntimeError("busy"))):
        state = calendar.refresh_from_exchange(fetch, "IN")
        assert state["days"] == ["2026-10-02"] and state["error"]


def test_the_exchange_names_its_holidays_r84_014(monkeypatch):
    import json
    import httpx
    from app import db
    from app.intel.filings import NSEFilings
    body = {"CM": [{"tradingDate": "10-Nov-2026", "description": "Diwali-Balipratipada"},
                   {"tradingDate": "25-Dec-2026", "description": "Christmas"}]}
    t = httpx.MockTransport(lambda r: httpx.Response(200, json=body) if r.url.path.startswith("/api") else httpx.Response(200, text="<html></html>"))
    got = NSEFilings(transport=t).holidays(named=True)
    assert got == [("2026-11-10", "Diwali-Balipratipada"), ("2026-12-25", "Christmas")]
    store = {}
    monkeypatch.setattr(db, "get_setting", lambda k: store.get(k))
    monkeypatch.setattr(db, "set_setting", lambda k, v: store.__setitem__(k, v))
    state = calendar.refresh_from_exchange(lambda: got, "IN")
    assert state["days"] == ["2026-11-10", "2026-12-25"] and state["names"]["2026-11-10"] == "Diwali-Balipratipada"
    assert calendar.holiday_name("IN", date(2026, 11, 10)) == "Diwali-Balipratipada"
    assert calendar.holiday_name("MCX", date(2026, 11, 10)) == "Diwali-Balipratipada"
    # a later list of plain dates keeps the names of the days outside its span, and drops none it has
    later = calendar.refresh_from_exchange(lambda: ["2027-01-26"], "IN")
    assert later["names"] == {"2026-11-10": "Diwali-Balipratipada", "2026-12-25": "Christmas"}
    assert json.loads(store[calendar.AUTO + "IN"])["names"] == later["names"]
