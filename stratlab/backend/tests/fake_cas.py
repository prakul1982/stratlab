"""The exchange's closing auction (CAS) data for the closing auction desk's tests and the browser tests' world.

The idle answers (outside the auction: no rows, the eligible symbols, the indices with no indicative close) are real,
trimmed, read on 5 Oct 2026 (fixtures/closing_auction). The in-auction answer follows the field names the exchange's
CAS page reads; its numbers are made up:
RELIANCE's IEP 0.50% above its reference price, TCS 1.20% below, INFY at its reference, NOPRICE with nothing yet;
NIFTY 50 at 25,000 with an indicative close of 25,075 (0.30% above)."""
import json
from datetime import date, timedelta
from pathlib import Path

FIX = Path(__file__).parent / "fixtures" / "closing_auction"
PATH = "/api/NextApi/apiClient/casApi"


def idle_stocks() -> dict:
    return json.loads((FIX / "cas_stocks_idle_2026-10-05.json").read_text())


def idle_indices() -> list:
    return json.loads((FIX / "cas_indices_idle_2026-10-05.json").read_text())


def _row(sym, ref, iep, ieq, final=None, final_qty=None, imb=0):
    return {"symbol": sym, "refrencePrice": ref, "lowerBand": round(ref * 0.97, 2) if ref else None,
            "upperBand": round(ref * 1.03, 2) if ref else None, "IEP": iep, "totTradedQty": ieq, "finalPrice": final,
            "finalQuantity": final_qty, "iiqAtEP": imb, "iiqAtMO": 0, "bestBidQty": 100, "bestBidPrice": iep,
            "bestAskPrice": iep, "bestAskQty": 120, "change": None, "perChange": None}


def auction_stocks(final: bool = False) -> dict:
    """In the auction (or, with `final`, just after it: final prices out)."""
    rows = [_row("RELIANCE", 1400.0, 1407.0, 250000, 1407.0 if final else None, 260000 if final else None, 1200),
            _row("TCS", 3000.0, 2964.0, 90000, 2964.0 if final else None, 91000 if final else None, -800),
            _row("INFY", 1500.0, 1500.0, 120000, 1500.0 if final else None, 120000 if final else None),
            _row("NOPRICE", None, None, None),
            {"symbol": "bad symbol!", "refrencePrice": 10}]
    return {"totalValue": 0, "totalQuantity": 0, "statusMsg": None, "data": rows, "indicativeTotalQuantity": 0,
            "indicativeTotalValue": 0, "symbols": ["INFY", "RELIANCE", "TCS"], "timestamp": None, "status": None}


def auction_indices(final: bool = False) -> list:
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
    """The fake exchange's answer to the CAS calls (the world's): the auction just ended, final prices out."""
    if path != PATH:
        return None
    return auction_stocks(True) if params.get("functionName") == "getCASData" else auction_indices(True)


def seed(today: date):
    """The browser tests' world: today's auction done, and 8 past trading days stored."""
    from app import closing_auction as CA, db
    import json as _j
    CA.forget()
    d, n = today, 0
    while n < 8:
        d -= timedelta(days=1)
        if d.weekday() >= 5:
            continue
        n += 1
        k = n * 0.1
        db.set_setting(CA.DAY_KEY + d.isoformat(), _j.dumps({
            "stocks": {"RELIANCE": [1400.0, round(1400 * (1 + k / 100), 2), 200000], "TCS": [3000.0, round(3000 * (1 - k / 100), 2), 80000],
                       "INFY": [1500.0, 1500.0, 100000]},
            "indices": {"NIFTY 50": [25000.0, round(25000 * (1 + k / 200), 2)]}}))
    CA.forget()
