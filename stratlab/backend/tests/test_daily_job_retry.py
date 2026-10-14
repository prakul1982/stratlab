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
    monkeypatch.setattr(leader, "leading", lambda: False)             # another container reads them
    assert main.holiday_pass() is False


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
