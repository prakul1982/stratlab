"""Indian currency futures (NSE's CDS segment): USDINR and the other rupee pairs, front month, whole lots, their
own costs, hours and holidays, and a backtest through the app."""
from datetime import date, datetime, timezone

from app import daily_report
from app.data import calendar
from app.data.cds import CDSProvider
from app.engine.costs import kind_of, order_costs


class FakeKite:
    def __init__(self):
        self.calls, self.asked = [], []

    def ready(self):
        return True

    def instruments_of(self, exch):
        self.asked.append(exch)
        return [{"instrument_token": t, "tradingsymbol": f"{n}26{m}FUT", "name": n, "instrument_type": "FUT", "expiry": date.fromisoformat(e)}
                for n, t, m, e in [("USDINR", 11, "OCT", "2026-10-28"), ("USDINR", 12, "NOV", "2026-11-26"),
                                   ("JPYINR", 13, "OCT", "2026-10-28"), ("EURUSD", 14, "OCT", "2026-10-28")]]

    def history(self, token, tf, days, continuous=None, ttl=None):
        self.calls.append((token, tf, days, continuous))
        return []

    def ltp_key(self, key):
        return {"CDS:USDINR26OCTFUT": 88.1234}.get(key)


def test_currency_pairs_are_front_month_lots_in_rupees(monkeypatch):
    import app.data.mcx as mcx
    monkeypatch.setattr(mcx, "ist_date", lambda: date(2026, 10, 3))
    p = CDSProvider(FakeKite())
    u = p.instrument("usd")
    assert u["id"] == "CDS:USDINR" and u["market"] == "CDS" and u["exchange"] == "CDS" and u["token"] == 11
    assert u["step"] == 1000 and u["lot_units"] == 1000 and u["unit"] == "US dollar" and "Oct 2026 contract" in u["name"]
    assert p.instrument("yen")["unit"] == "100 yen" and u["currency"] == "INR"
    e = p.instrument("eur/usd")                                                               # a cross pair: priced in dollars
    assert e["id"] == "CDS:EURUSD" and e["currency"] == "USD" and e["step"] == 1000 and "euro, in dollars" in e["name"]
    assert p.instrument("GBPUSD") is None                                                     # no contract listed
    assert p.ltp(u) == 88.1234 and p.kite.asked == ["CDS"]
    assert [i["symbol"] for i in p.defaults()] == ["USDINR", "JPYINR"]                      # only pairs with contracts
    p.history(u, "1d", 3000)
    p.history(u, "15m", 400)
    assert p.kite.calls == [(11, "1d", 3000, True), (11, "15m", 120, False)]
    monkeypatch.setattr(mcx, "ist_date", lambda: date(2026, 10, 26))                        # two days to expiry: rolled
    p2 = CDSProvider(FakeKite())
    assert p2.instrument("USDINR")["token"] == 12


def test_currency_costs_have_no_stt():
    c = order_costs(kind_of({"market": "CDS", "type": "FUT"}), "sell", 1000, 88, 20)
    assert kind_of({"market": "CDS"}) == "in_cds_fut" and c["stt"] == 0 and c["stamp"] == 0
    b = order_costs("in_cds_fut", "buy", 1000, 88, 20)
    assert round(b["stamp"], 4) == 0.088 and round(b["exchange"], 4) == round(88000 * (0.0000035 + 0.000001), 4)


def test_cross_pair_brokerage_is_converted_from_rupees(monkeypatch):
    from app.engine import costs
    monkeypatch.setattr("app.pricing.rates", lambda: {"USD": 80.0})
    assert kind_of({"market": "CDS", "currency": "USD"}) == "in_cds_fut_usd" and kind_of({"market": "CDS", "currency": "JPY"}) == "in_cds_fut_jpy"
    usd = order_costs("in_cds_fut_usd", "buy", 1000, 1.1, 20)
    assert usd["brokerage"] == 0.25 and round(usd["stamp"], 6) == round(1100 * 0.000001, 6)     # ₹20 is $0.25 at 80
    assert order_costs("in_cds_fut_jpy", "buy", 1000, 150, 20)["brokerage"] == 20 / costs.FALLBACK_RUPEES["JPY"]   # no JPY rate read yet


def test_currency_hours_holidays_and_report_time(monkeypatch):
    assert not calendar.is_trading_day("CDS", date(2025, 10, 2))                           # national holidays
    monkeypatch.setattr(calendar, "_stored", lambda key: {"2026-11-20"} if key == "CDS" else set())
    assert not calendar.is_trading_day("CDS", date(2026, 11, 20))                           # the segment's own list
    assert calendar.is_trading_day("IN", date(2026, 11, 20))                                 # equities unaffected
    assert daily_report.due("CDS", datetime(2025, 10, 3, 11, 46, tzinfo=timezone.utc)) == "2025-10-03"   # 17:16 IST


def test_currency_futures_backtest_through_the_app(monkeypatch):
    from tests import world as W
    w = W.build(monkeypatch)
    try:
        c, h = w["client"], W.headers("pro-token")
        found = c.get("/instruments/search?q=usd&market=CDS", headers=h).json()
        rows = found if isinstance(found, list) else found.get("results") or found.get("rows") or []
        assert any(r["id"] == "CDS:USDINR" for r in rows), found
        markets = c.get("/markets", headers=h).json()
        ms = markets if isinstance(markets, list) else markets.get("markets", [])
        cds = next(m for m in ms if m["id"] == "CDS")
        assert cds["hours"]["close"] == "17:00"
        from app import main, platform_check
        r = platform_check.check_backtest(main.markets, "CDS")
        assert r["state"] == "pass", r                                                         # a 2-year backtest, costs charged
    finally:
        w["close"]()


def test_exchange_holiday_list_by_segment():
    import httpx
    from app.intel.filings import NSEFilings
    body = {"CM": [{"tradingDate": "26-Jan-2027"}], "CD": [{"tradingDate": "26-Jan-2027"}, {"tradingDate": "19-Feb-2027"}]}
    t = httpx.MockTransport(lambda r: httpx.Response(200, json=body) if r.url.path.startswith("/api") else httpx.Response(200, text="<html></html>"))
    f = NSEFilings(transport=t)
    assert f.holidays() == ["2027-01-26"] and f.holidays("CD") == ["2027-01-26", "2027-02-19"]
