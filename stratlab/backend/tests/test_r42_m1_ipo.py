"""Release 42, lane m1: a listed IPO with no final issue price still shows its listing price and closes; a listed issue with no symbol to
read its prices under is looked for in the broker's list (LIVE7A-020)."""
from datetime import date, datetime
from zoneinfo import ZoneInfo

from app import ipo as I

IST = ZoneInfo("Asia/Kolkata")
BARS = [{"t": "2026-11-11T00:00:00+05:30", "o": 52.80, "h": 53.0, "l": 50.0, "c": 50.16, "v": 1.0},
        {"t": "2026-11-12T00:00:00+05:30", "o": 50.0, "h": 50.5, "l": 47.0, "c": 47.66, "v": 1.0}]


class Y:
    def __init__(self, bars):
        self.bars, self.asked = bars, []

    def chart(self, sym, tf, days):
        self.asked.append(sym)
        return {"candles": list(self.bars) if sym == "ANTALA.BO" else []}


def test_no_issue_price_still_gives_the_listing_price_and_the_closes():
    row = {"market": "IN", "symbol": None, "bse_code": "4950", "listed_as": "ANTALA", "segment": "sme", "listing": "2026-11-11",
           "price": None, "low": 62.0, "high": 66.0}
    p = I.performance(row, Y(BARS), date(2026, 11, 12), datetime(2026, 11, 12, 20, 0, tzinfo=IST))
    assert (p["listing_price"], p["day_close"], p["latest"], p["latest_date"]) == (52.80, 50.16, 47.66, "2026-11-12")
    assert p["issue_price"] is None and p["listing_change_pct"] is None and p["change_pct"] is None
    # with the issue price, the changes as before
    p = I.performance({**row, "price": 66.0}, Y(BARS), date(2026, 11, 12), datetime(2026, 11, 12, 20, 0, tzinfo=IST))
    assert (p["listing_change_pct"], p["change_pct"]) == (-20.0, -27.79)


def test_the_exchange_table_alone_gives_what_it_has():
    row = {"market": "IN", "symbol": None, "bse_code": "4950", "segment": "sme", "listing": "2026-11-11", "price": None,
           "bse_perf": {"listed": "2026-11-11", "latest": 47.66}}
    p = I.performance(row, Y([]), date(2026, 11, 12), datetime(2026, 11, 12, 20, 0, tzinfo=IST))
    assert (p["latest"], p["change_pct"], p["day_close"], p["basis"]) == (47.66, None, None, "exchange")


def test_a_listed_issue_with_nothing_to_read_its_prices_under_is_looked_for_in_the_brokers_list():
    now = datetime(2026, 11, 12, 20, 0, tzinfo=IST)
    row = {"id": "in-bse-4950", "market": "IN", "name": "Antala Industries Limited", "symbol": None, "segment": "sme", "exchanges": ["BSE"],
           "bse_code": "4950", "open": "2026-11-04", "close": "2026-11-06", "low": 62.0, "high": 66.0, "listing": "2026-11-11"}
    asked = []

    def lookup(r):
        asked.append(r["name"])
        return {"symbol": "ANTALA", "exchange": "BSE", "code": "544777", "first": "2026-11-11"}
    rows = [dict(row)]
    assert I.confirm_listings(rows, now, [], lookup=lookup) == 1
    assert rows[0]["bse_scrip"] == "544777" and rows[0]["listing"] == "2026-11-11" and I.yahoo_symbol(rows[0]) == "544777.BO"
    # once it has one, it isn't looked for again; an NSE issue with its symbol never is
    asked.clear()
    assert I.confirm_listings(rows, now, [], lookup=lookup) == 0 and asked == []
    assert I.confirm_listings([{**row, "symbol": "ANTALA"}], now, [], lookup=lookup) == 0 and asked == []
    # long after its listing, no more looks
    assert I.confirm_listings([dict(row)], datetime(2026, 12, 31, 20, 0, tzinfo=IST), [], lookup=lookup) == 0 and asked == []
