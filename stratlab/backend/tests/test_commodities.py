from datetime import date, datetime, timezone

from app import daily_report
from app.data import calendar
from app.data.mcx import MCXProvider, front
from app.data.yahoo_markets import YahooProvider, fits
from app.engine.costs import kind_of, order_costs


class FakeKite:
    def __init__(self):
        self.calls = []

    def ready(self):
        return True

    def instruments_of(self, exch):
        assert exch == "MCX"
        rows = []
        for name, token, exp in [("GOLDM", 1, "2026-10-03"), ("GOLDM", 2, "2026-11-05"), ("CRUDEOIL", 3, "2026-10-19"),
                                 ("GOLD", 4, "2026-12-04"), ("SOMETHINGELSE", 5, "2026-10-30")]:
            rows.append({"instrument_token": token, "tradingsymbol": f"{name}26X", "name": name, "instrument_type": "FUT",
                         "expiry": date.fromisoformat(exp)})
        rows.append({"instrument_token": 9, "tradingsymbol": "GOLDM26OCT80000CE", "name": "GOLDM", "instrument_type": "CE",
                     "expiry": date(2026, 10, 3)})
        return rows

    def history(self, token, tf, days, continuous=None, ttl=None):
        self.calls.append((token, tf, days, continuous))
        return []


def test_mcx_front_month_rolls_before_expiry():
    cs = [{"expiry": date(2026, 10, 3), "token": 1}, {"expiry": date(2026, 11, 5), "token": 2}]
    assert front(cs, date(2026, 9, 26))["token"] == 1
    assert front(cs, date(2026, 9, 30))["token"] == 2          # 3 days to expiry: rolled to next month
    assert front(cs, date(2026, 12, 1)) is None


def test_mcx_instruments_are_whole_lots_in_rupees(monkeypatch):
    import app.data.mcx as mcx
    monkeypatch.setattr(mcx, "date", type("D", (date,), {"today": staticmethod(lambda: date(2026, 9, 26))}))
    p = MCXProvider(FakeKite())
    g = p.instrument("GOLDM")
    assert g["id"] == "MCX:GOLDM" and g["token"] == 1 and g["market"] == "MCX" and g["currency"] == "INR"
    assert g["step"] == 10 and g["unit"] == "10 g" and "Oct 2026 contract" in g["name"]   # 1 lot = 100 g = 10 price units
    assert p.instrument("crude")["symbol"] == "CRUDEOIL" and p.instrument("crude")["step"] == 100
    assert p.instrument("SOMETHINGELSE") is None and p.instrument("NICKEL") is None
    assert [i["symbol"] for i in p.search("gold")][:2] == ["GOLD", "GOLDM"]
    p.history(g, "1d", 3000)
    p.history(g, "5m", 400)
    assert p.kite.calls == [(1, "1d", 3000, True), (1, "5m", 60, False)]    # stitched daily; intraday only this contract


def test_global_commodities_are_separate_futures_in_dollars():
    assert fits("CMDTY", {"symbol": "GC=F", "quoteType": "FUTURE"})
    assert not fits("CMDTY", {"symbol": "GLD", "quoteType": "ETF"}) and not fits("US", {"symbol": "GC=F", "quoteType": "FUTURE"})
    p = YahooProvider("CMDTY", yahoo=None)
    gold = p.instrument("gold")
    assert gold["id"] == "CMDTY:GC=F" and gold["type"] == "FUT" and gold["currency"] == "USD" and gold["step"] == 1
    assert [i["token"] for i in p.search("crude")] == ["CL=F", "BZ=F"]
    assert p._scale(gold, {"currency": "USX"}) == 0.01                        # corn in cents becomes dollars


def test_costs_differ_by_market():
    mcx = order_costs(kind_of({"market": "MCX", "type": "FUT"}), "sell", 100, 7000, 20)
    assert kind_of({"market": "MCX"}) == "in_mcx_fut" and round(mcx["stt"], 2) == 70.0          # CTT 0.01% on sells
    assert order_costs("in_mcx_fut", "buy", 100, 7000, 20)["stt"] == 0 and order_costs("in_mcx_fut", "buy", 100, 7000, 20)["stamp"] > 0
    g = order_costs(kind_of({"market": "CMDTY"}), "buy", 10, 2600, 0)
    assert kind_of({"market": "CMDTY"}) == "cmdty" and round(g["spread"], 2) == 5.2 and "stt" not in g


def test_hours_holidays_and_report_times():
    assert not calendar.is_trading_day("MCX", date(2025, 10, 2))            # follows NSE holidays
    assert not calendar.is_trading_day("CMDTY", date(2025, 12, 25))         # follows US holidays
    assert not calendar.is_trading_day("CMDTY", date(2025, 9, 28))          # Sunday's evening open counts for Monday
    assert daily_report.due("MCX", datetime(2025, 10, 3, 18, 16, tzinfo=timezone.utc)) == "2025-10-03"   # 23:46 IST
    assert daily_report.due("CMDTY", datetime(2025, 10, 3, 21, 12, tzinfo=timezone.utc)) == "2025-10-03"  # 17:12 New York
