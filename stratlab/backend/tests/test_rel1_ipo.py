"""rel1 item 5 (CX1 problem 9): the IPO table left Crystal Crop's lot blank (Business Standard: 55 shares). The lot is read under any of
the names the exchanges give it, from the issue page or either exchange's list; still missing, the page says so in words."""
from datetime import date

from app import ipo
from app.intel import ipo_sources as S


def test_the_lot_is_read_under_any_of_its_names():
    assert S.lot_of({"bid lot": "55 Equity Shares and in multiples thereof"}) == 55
    assert S.lot_of({"minimum bid quantity": "55 Equity Shares"}) == 55
    assert S.lot_of({"min. order qty": "1,200 shares"}) == 1200
    assert S.lot_of({"bid lot size": "-", "market lot": "60"}) == 60
    assert S.lot_of({"price range": "259-272", "issue size": "8,00,000 shares"}) is None
    assert S.lot_in({"lotSize": "55"}) == 55 and S.lot_in({"Min_Bid_Qty": 55}) == 55 and S.lot_in({"issueSize": "1000"}) is None


def test_a_lot_on_an_exchange_list_reaches_the_row():
    nse = {"upcoming": S.nse_upcoming([{"symbol": "CRYSTAL", "companyName": "Crystal Crop Protection Limited", "series": "EQ",
                                        "issueStartDate": "18-Nov-2026", "issueEndDate": "20-Nov-2026", "issuePrice": "Rs.259 to Rs.272",
                                        "issueSize": "1000000"}])}
    bse = [{"code": "544999", "name": "Crystal Crop Protection Limited", "segment": "mainboard", "open": "2026-11-18", "close": "2026-11-20",
            "low": 259.0, "high": 272.0, "face_value": 1.0, "size_shares": 1000000, "status": "F", "lot": 55}]
    rows = ipo.merge_india([], nse, bse, [], [], [], date(2026, 11, 16))
    row = next(r for r in rows if r.get("symbol") == "CRYSTAL")
    assert row["lot"] == 55 and "BSE" in row["exchanges"]
