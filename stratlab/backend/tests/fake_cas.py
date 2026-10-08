"""The exchange's closing auction (CAS) data for the closing auction desk's tests and the browser tests' world.

The idle answers (outside the auction: no rows, the eligible symbols, the indices with no indicative close) are real,
trimmed, read on 5 Oct 2026 (fixtures/closing_auction). The in-auction answer follows the field names the exchange's
CAS page reads; its numbers are made up:
RELIANCE's IEP 0.50% above its reference price, TCS 1.20% below, INFY at its reference, NOPRICE with nothing yet;
NIFTY 50 at 25,000 with an indicative close of 25,075 (0.30% above). The browser tests' world (answer, seed) puts the
same gaps at the demo world's own closes (fake_prices), so the auction agrees with every other page."""
import json
from datetime import date, timedelta
from pathlib import Path

FIX = Path(__file__).parent / "fixtures" / "closing_auction"
PATH = "/api/NextApi/apiClient/casApi"


def idle_stocks() -> dict:
    return json.loads((FIX / "cas_stocks_idle_2026-10-05.json").read_text())


def closed_stocks() -> dict:
    """The real answer after the auction of 5 Oct 2026, three stocks (order books left out)."""
    return json.loads((FIX / "cas_stocks_closed_2026-10-05.json").read_text())


def closed_indices() -> list:
    return json.loads((FIX / "cas_indices_closed_2026-10-05.json").read_text())


def idle_indices() -> list:
    return json.loads((FIX / "cas_indices_idle_2026-10-05.json").read_text())


def _row(sym, ref, iep, ieq, final=None, final_qty=None, imb=0):
    return {"symbol": sym, "refrencePrice": ref, "lowerBand": round(ref * 0.97, 2) if ref else None,
            "upperBand": round(ref * 1.03, 2) if ref else None, "IEP": iep, "totTradedQty": ieq, "finalPrice": final,
            "finalQuantity": final_qty, "iiqAtEP": imb, "iiqAtMO": 0, "bestBidQty": 100, "bestBidPrice": iep,
            "bestAskPrice": iep, "bestAskQty": 120, "totalBuyQuantity": ieq, "totalSellQuantity": ieq, "change": None, "perChange": None}


# each stock's indicative price against its reference price in the auction: RELIANCE 0.50% above, TCS 1.20% below
GAPS = {"RELIANCE": 0.005, "TCS": -0.012, "INFY": 0.0}


def _levels(levels: dict | None) -> dict:
    """{symbol: (reference price, indicative or final price)}: the fixed made-up ones, or, from `levels` (each stock's
    close), the reference price that puts the close at the stock's gap."""
    if not levels:
        return {"RELIANCE": (1400.0, 1407.0), "TCS": (3000.0, 2964.0), "INFY": (1500.0, 1500.0)}
    return {s: (round(levels[s] / (1 + g), 2), levels[s]) for s, g in GAPS.items()}


def auction_stocks(final: bool = False, levels: dict | None = None) -> dict:
    """In the auction (or, with `final`, just after it: final prices out). `levels`: each stock's close (the demo
    world's price table), else the fixed made-up prices."""
    lv = _levels(levels)
    rows = [_row("RELIANCE", lv["RELIANCE"][0], lv["RELIANCE"][1], 250000, lv["RELIANCE"][1] if final else None, 260000 if final else None, 1200),
            _row("TCS", lv["TCS"][0], lv["TCS"][1], 90000, lv["TCS"][1] if final else None, 91000 if final else None, -800),
            _row("INFY", lv["INFY"][0], lv["INFY"][1], 120000, lv["INFY"][1] if final else None, 120000 if final else None),
            _row("NOPRICE", None, None, None),
            {"symbol": "bad symbol!", "refrencePrice": 10}]
    return {"totalValue": 0, "totalQuantity": 0, "statusMsg": None, "data": rows, "indicativeTotalQuantity": 0,
            "indicativeTotalValue": 0, "symbols": ["INFY", "RELIANCE", "TCS"], "timestamp": None, "status": None}


def auction_indices(final: bool = False, levels: dict | None = None) -> list:
    """The indices in the auction, or just after it. `levels`: {index: (close, the close before)} from the demo world's
    price table, else the fixed made-up ones."""
    if levels:
        return [{"indexName": n, "currentPrice": close, "closePrice": before, "indicativeClose": 0, "icStatus": "CLOSE",
                 "change": round(close - before, 2), "perChange": round((close / before - 1) * 100, 2), "icChange": 0,
                 "icPerChange": 0, "indexTime": None} for n, (close, before) in levels.items()]
    return [{"indexName": "NIFTY 50", "currentPrice": 25075.0 if final else 25000.0, "closePrice": 24900.0,
             "indicativeClose": 0 if final else 25075.0, "icStatus": "CLOSE" if final else "OPEN", "change": 0, "perChange": 0,
             "icChange": 0, "icPerChange": 0, "indexTime": None},
            {"indexName": "NIFTY BANK", "currentPrice": 54500.0, "closePrice": 54450.75, "indicativeClose": 0 if final else 54400.0,
             "icStatus": "OPEN", "change": 0, "perChange": 0, "icChange": 0, "icPerChange": 0, "indexTime": None}]


class Feed:
    """What the exchange client's cas_stocks / cas_indices return."""

    def __init__(self, final: bool = False, fail: bool = False):
        self.final, self.fail, self.calls = final, fail, 0

    def cas_stocks(self):
        self.calls += 1
        if self.fail:
            raise RuntimeError("exchange down")
        return auction_stocks(self.final)

    def cas_indices(self):
        return auction_indices(self.final)


def answer(path: str, params) -> dict | list | None:
    """The fake exchange's answer to the CAS calls (the world's): the latest auction is over, its final prices out, at
    the demo world's close of that day (fake_prices), the same prices every other page shows for it."""
    if path != PATH:
        return None
    from tests import fake_prices as P
    close = last_auction_close()
    if params.get("functionName") == "getCASData":
        return auction_stocks(True, {s: P.price(s, close) for s in GAPS})
    before = P.previous_close("IN", close + timedelta(hours=1))
    return auction_indices(True, {n: (P.price(n, close), P.price(n, before)) for n in ("NIFTY 50", "NIFTY BANK")})


def last_auction_close():
    """The close of the latest closing auction that is over: the latest close at least six minutes old (the auction ends at
    15:35, five minutes after the close), so a page opened through the day's trading shows the auction before it, never a
    "final" price from one that has not happened."""
    from datetime import datetime
    from tests import fake_prices as P
    return P.last_close("IN", datetime.now(P.IST) - timedelta(minutes=6))


def seed(today: date):
    """The browser tests' world: the latest auction done, and the 8 trading days before it stored, each day's final
    prices the demo world's closes (fake_prices) with the reference prices a little off them."""
    from datetime import datetime
    from app import closing_auction as CA, db
    from tests import fake_prices as P
    import json as _j
    CA.forget()
    d, n = P.last_close("IN").date(), 0
    while n < 8:
        d -= timedelta(days=1)
        if not P.trading_day("IN", d):
            continue
        n += 1
        k = n * 0.1
        close = {s: P.price(s, datetime(d.year, d.month, d.day, 15, 30, tzinfo=P.IST)) for s in ("RELIANCE", "TCS", "INFY", "NIFTY 50")}
        db.set_setting(CA.DAY_KEY + d.isoformat(), _j.dumps({
            "stocks": {"RELIANCE": [round(close["RELIANCE"] / (1 + k / 100), 2), close["RELIANCE"], 200000],
                       "TCS": [round(close["TCS"] / (1 - k / 100), 2), close["TCS"], 80000], "INFY": [close["INFY"], close["INFY"], 100000]},
            "indices": {"NIFTY 50": [round(close["NIFTY 50"] / (1 + k / 200), 2), close["NIFTY 50"]]}}))
    CA.forget()
