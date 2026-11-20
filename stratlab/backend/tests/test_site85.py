"""Lane site85: the LIVE21B site findings (live review after Release 84, Fri 20 Nov 2026)."""
from datetime import date, timedelta

from app import main  # noqa: F401, I001  (first: the app loads its jobs before the modules built on them)
from app import corp_actions, scan, scan_presets, stock_pages


# ---------- LIVE21B-013: "Near 52-week low" missed ONGC, 2.3% above its 52-week low ----------
# 20 Nov 2026: NIFTY 50, "Near 52-week low" (the close within 5% of the previous 252 sessions' lowest low) matched nothing, while ONGC closed at
# ₹223.46 with its 52-week low ₹218.53 of 8 Oct on its own page and on the exchange's. The broker scales every candle before an extraordinary
# dividend's ex-date: ONGC's ₹8 of 9 Nov (3.4% of its ₹234.60 close the day before) took the 8 Oct low to ₹211.08, and 223.46 is 5.9% above that.
EX, DIV = "2026-11-09", 8.0


def _sessions(n: int, end: str = "2026-11-20") -> list[str]:
    out, d = [], date.fromisoformat(end)
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d -= timedelta(days=1)
    return out[::-1]


def _ongc_traded() -> list[dict]:
    """ONGC-like daily candles as the exchange printed them: a slide to the 8 Oct low of 218.53, then up, ₹234.60 the day before the ex-date,
    then the dividend off and a drift to the 223.46 close."""
    days, out = _sessions(300), []
    for i, d in enumerate(days):
        if d < "2026-10-08":
            c = 260 - (260 - 222) * i / max(1, days.index("2026-10-08"))
        elif d == "2026-10-08":
            c = 220.0
        elif d < EX:
            c = 222 + 9.5 * (days.index(d) - days.index("2026-10-08")) / max(1, days.index(EX) - 1 - days.index("2026-10-08"))
        else:
            c = 225.0 - 1.54 * (days.index(d) - days.index(EX)) / max(1, len(days) - 1 - days.index(EX))
        lo = 218.53 if d == "2026-10-08" else c - 1.2
        out.append({"t": f"{d}T00:00:00+05:30", "o": c, "h": c + 1.0, "l": lo, "c": c, "v": 1e7})
    out[-1].update(c=223.46, o=224.0, h=224.9, l=221.95)
    out[days.index(EX) - 1]["c"] = 234.6
    return out


def _broker(bars: list[dict]) -> list[dict]:
    """The broker's copy: every candle before the ex-date scaled by (P - D) / P, rounded."""
    i = next(k for k, b in enumerate(bars) if b["t"][:10] >= EX)
    k = (bars[i - 1]["c"] - DIV) / bars[i - 1]["c"]
    return [{**b, **{x: round(b[x] * k, 2) for x in "ohlc"}} if j < i else dict(b) for j, b in enumerate(bars)]


def _stored_dividend(monkeypatch, sym="ONGC", amount=DIV):
    rows = [{"id": f"{sym}-div", "symbol": sym, "kind": "dividend", "ex_date": EX, "amount": amount}]
    monkeypatch.setattr(corp_actions, "actions_for", lambda region, s, sources=None, fetch=True, **k: rows if s == sym else [])


def test_live21b_013_the_broker_scaled_low_is_what_hid_the_match():
    traded = _ongc_traded()
    broker = _broker(traded)
    low = min(b["l"] for b in broker[-253:-1])
    assert round(low, 2) == 211.08 and 223.46 / low > 1.05            # what the scan was given: 5.9% above a low no session had
    assert scan_presets.evaluate(broker, only=["near_low52"])["matches"] == {}
    m = scan_presets.evaluate(traded, only=["near_low52"])["matches"]["near_low52"]
    assert m["detail"] == "Closed at 223.46, 2.3% above the previous 252-day low of 218.53"


def test_live21b_013_the_scan_reads_the_brokers_candles_as_traded(monkeypatch):
    _stored_dividend(monkeypatch)
    broker = _broker(_ongc_traded())
    back = stock_pages.broker_as_traded(broker, "ONGC")
    assert min(b["l"] for b in back[-253:-1]) == 218.53
    assert broker[0]["c"] != back[0]["c"] and back[-1] == broker[-1]       # the candles before the ex-date, undone; after it, as they are

    class Kite:
        pass

    class Prov:
        kite = Kite()

        def instrument(self, token):
            return {"symbol": "ONGC", "type": "EQ", "currency": "INR"}

        def history(self, inst, tf, days, ttl=None):
            return broker

    class Reg:
        def provider(self, market):
            return Prov()

        def resolve(self, iid):
            return Prov(), Prov().instrument(iid)

    import app.universes as U
    monkeypatch.setattr(U, "resolve", lambda reg, market, members: (["IN:633601"], []))
    monkeypatch.setattr(scan, "company_name", lambda market, inst, iid: "Oil and Natural Gas Corporation")
    scan._cache.clear()
    out = scan.run_preset(Reg(), "IN", [{"symbol": "ONGC"}], "near_low52", session="2026-11-20")
    assert [r["symbol"] for r in out["rows"]] == ["ONGC"] and out["checked"] == 1
    assert out["rows"][0]["detail"].endswith("2.3% above the previous 252-day low of 218.53")
    # the 52-week high breakout reads the same candles: a scaled year's high is no breakout bar to clear
    scan._cache.clear()
    assert scan.run_preset(Reg(), "IN", [{"symbol": "ONGC"}], "high52", session="2026-11-20")["rows"] == []
    scan._cache.clear()


def test_live21b_013_the_public_price_history_is_left_as_it_is(monkeypatch):
    """The nights' and weekends' source (scan.LastCloseIndia, the public price history) prints the candles as traded: nothing is undone on it."""
    _stored_dividend(monkeypatch)
    traded = _ongc_traded()

    class Yahoo:
        def chart(self, sym, tf, days):
            return {"candles": traded}

    reg = scan.LastCloseIndia(Yahoo())
    import app.universes as U
    monkeypatch.setattr(U, "resolve", lambda r, market, members: (["IN:close:ONGC"], []))
    monkeypatch.setattr(scan, "company_name", lambda market, inst, iid: None)
    scan._cache.clear()
    out = scan.run_preset(reg, "IN", [{"symbol": "ONGC"}], "near_low52", session="2026-11-20")
    assert out["rows"][0]["detail"].endswith("2.3% above the previous 252-day low of 218.53")
    scan._cache.clear()


def test_live21b_013_the_breadth_run_reads_the_year_as_traded(monkeypatch):
    """The breadth run's candles (its 52-week highs and lows, the movers' marks, the stored scans of the 500-stock groups) are undone the same way."""
    _stored_dividend(monkeypatch)
    broker = _broker(_ongc_traded())
    monkeypatch.setattr(main.kite, "equity", lambda s: {"token": 633601, "symbol": "ONGC", "type": "EQ"})
    monkeypatch.setattr(main.kite, "history", lambda token, tf, days, store=True, **k: broker)
    got = main.breadth_load("IN", "ONGC", 400)
    assert min(b["l"] for b in got[-253:-1]) == 218.53
    assert "near_low52" in scan_presets.evaluate(got)["matches"]
