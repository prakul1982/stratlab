"""The daily readers (holidays, exchange rates, the company lists) ask again in about an hour when a read failed, not tomorrow."""
from app import main  # noqa: F401, I001  (first: the app loads the modules in the order they need)
from app import leader, pricing, stock_pages


def test_the_wait_after_a_pass():
    assert main.next_pass_in(False, 0) == 24 * 3600
    assert main.next_pass_in(True, 1) == main.RETRY_AFTER_FAIL == 3600
    assert main.next_pass_in(True, main.QUICK_RETRIES) == 3600
    assert main.next_pass_in(True, main.QUICK_RETRIES + 1) == 24 * 3600          # a source that stays down is asked daily again


def test_a_failed_holiday_read_is_asked_again_soon(monkeypatch):
    monkeypatch.setattr(leader, "leading", lambda: True)
    results = {"IN": {"days": [], "error": "busy"}, "CDS": {"days": [], "error": None}}
    monkeypatch.setattr(main.trading_calendar, "refresh_from_exchange", lambda fetch, market="IN": results[market])
    assert main.holiday_pass() is True
    results["IN"] = {"days": ["2026-10-02"], "error": None}
    assert main.holiday_pass() is False
    monkeypatch.setattr(main.trading_calendar, "refresh_from_exchange", lambda fetch, market="IN": (_ for _ in ()).throw(RuntimeError("db down")))
    assert main.holiday_pass() is True
    monkeypatch.setattr(leader, "leading", lambda: False)             # another container reads them: nothing was read (None), not "done"
    assert main.holiday_pass() is None


def test_a_rate_read_with_errors_is_asked_again_soon(monkeypatch):
    monkeypatch.setattr(leader, "leading", lambda: True)
    monkeypatch.setattr(pricing, "refresh_rates", lambda fetch: {"rates": {}, "errors": ["USD: down"]})
    assert main.rates_pass() is True
    monkeypatch.setattr(pricing, "refresh_rates", lambda fetch: {"rates": {"USD": 83.0}, "errors": []})
    assert main.rates_pass() is False
    monkeypatch.setattr(pricing, "refresh_rates", lambda fetch: (_ for _ in ()).throw(RuntimeError("down")))
    assert main.rates_pass() is True


def test_a_failed_company_list_is_asked_again_alone(monkeypatch):
    monkeypatch.setattr(leader, "leading", lambda: True)
    saved, asked = [], []

    def india():
        asked.append("IN")
        raise RuntimeError("exchange busy")

    def us():
        asked.append("US")
        return [{"symbol": "AAPL", "name": "Apple"}]
    monkeypatch.setattr(main, "india_listing", india)
    monkeypatch.setattr(main, "_sec_companies", us)
    monkeypatch.setattr(stock_pages, "save_list", lambda region, rows: saved.append(region))
    assert main.stock_list_pass() == ["IN"] and saved == ["US"]
    asked.clear()
    assert main.stock_list_pass(("IN",)) == ["IN"] and asked == ["IN"]        # the retry reads only the one that failed
    monkeypatch.setattr(main, "india_listing", lambda: [{"symbol": "TCS", "name": "TCS"}])
    assert main.stock_list_pass(("IN",)) == [] and saved == ["US", "IN"]


def test_a_pass_skipped_while_not_leading_is_asked_again_in_a_minute_not_a_day(monkeypatch):
    monkeypatch.setattr(leader, "leading", lambda: False)
    assert main.rates_pass() is None and main.holiday_pass() is None and main.stock_list_pass() is None
    for skipped in (main.rates_pass(), main.holiday_pass(), main.stock_list_pass()):
        assert main.next_pass_in(skipped, 0) == main.FOLLOWER_RETRY == 60
    assert main.next_pass_in(False, 0) == 24 * 3600                   # a pass that ran is still daily


def test_the_stock_list_loop_keeps_its_retry_list_while_it_is_not_leading(monkeypatch):
    class Stop(Exception):
        pass
    answers, naps = iter([["IN"], None, []]), []
    monkeypatch.setattr(main, "stock_list_pass", lambda only=None: next(answers))
    seen = []
    real = main.stock_list_pass

    def pass_(only=None):
        seen.append(only)
        return real(only)
    monkeypatch.setattr(main, "stock_list_pass", pass_)

    def nap(s):
        naps.append(s)
        if len(naps) == 4:
            raise Stop()
    monkeypatch.setattr(main.time, "sleep", nap)
    try:
        main.stock_list_job()
    except Stop:
        pass
    assert seen[:3] == [None, ("IN",), ("IN",)] and naps[:4] == [240, 3600, 60, 86400]


def test_the_platform_check_runs_after_a_restart_past_its_time_once_a_day(monkeypatch):
    from datetime import datetime
    from tests import world as W
    w = W.build(monkeypatch)
    try:
        ran = []
        monkeypatch.setattr(main, "daily_platform_check", lambda *a, **k: ran.append(1) or {})
        monkeypatch.setattr(leader, "leading", lambda: True)
        IST = main.IST
        assert main.platform_pass(datetime(2026, 10, 5, 16, 40, tzinfo=IST)) is False and ran == []     # not yet due
        monkeypatch.setattr(leader, "leading", lambda: False)
        assert main.platform_pass(datetime(2026, 10, 5, 17, 5, tzinfo=IST)) is None and ran == []        # not leading: asked again
        monkeypatch.setattr(leader, "leading", lambda: True)
        assert main.platform_pass(datetime(2026, 10, 5, 17, 5, tzinfo=IST)) is False and ran == [1]      # a restart just after 16:50
        assert main.platform_pass(datetime(2026, 10, 5, 17, 35, tzinfo=IST)) is False and ran == [1]     # and not again that day
        assert main.platform_pass(datetime(2026, 10, 6, 16, 51, tzinfo=IST)) is False and ran == [1, 1]
        monkeypatch.setattr(main, "daily_platform_check", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
        assert main.platform_pass(datetime(2026, 10, 7, 17, 0, tzinfo=IST)) is True               # failed: not marked, asked again
        monkeypatch.setattr(main, "daily_platform_check", lambda *a, **k: ran.append(1) or {})
        assert main.platform_pass(datetime(2026, 10, 7, 18, 0, tzinfo=IST)) is False and len(ran) == 3
    finally:
        w["close"]()
