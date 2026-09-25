from datetime import date, datetime, timezone

from app import daily_report
from app.data import calendar
from app.kite_service import IST, token_valid
from app.options import recorder


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
