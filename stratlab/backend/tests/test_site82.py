"""Lane site82: the LIVE19A / LIVE19B site findings (live review after Release 81, Fri 20 Nov 2026)."""
import json
import re
from pathlib import Path

from app import main  # noqa: F401, I001  (first: the app loads its jobs before the modules built on them)
from app import db, shareholders
from app.intel import mood

FRONT = Path(__file__).resolve().parents[2] / "frontend"


# ---------- LIVE19A-006: an index's points are weighed by free float, not whole market value ----------
# 20 Nov 13:05 IST, the live card: HDFC Bank +2.79% "added about 44 points" and Reliance −1.03% "took about 24 points off". The share count
# behind HDFC's ₹12.69 lakh cr was already the post-bonus one (₹12.69 lakh cr / ₹821.8 = 15.4 bn shares); the weight was its value over the
# whole index's value, where the exchange weighs only the shares outside the promoter group (HDFC Bank: none; Reliance: about half).
NIFTY = 25514.30
CAPS = {"RELIANCE": 18.62, "HDFCBANK": 12.69, "BHARTIARTL": 13.39, "SBIN": 10.68, "OTHERS": 150.0}       # ₹ lakh cr; OTHERS = the rest
PROMOTERS = {"RELIANCE": 50.1, "HDFCBANK": 0.0, "BHARTIARTL": 54.0, "SBIN": 57.4, "OTHERS": 45.0}
MOVES = {"RELIANCE": -1.03, "HDFCBANK": 2.79, "BHARTIARTL": 0.74, "SBIN": -0.35, "OTHERS": 0.9}


def _members(caps):
    return [{"symbol": s, "name": s, "market_cap": caps[s], "change_pct": MOVES[s]} for s in caps]


def test_live19a_006_whole_market_value_halves_a_company_that_is_all_free_float():
    before = mood.index_movers(_members(CAPS), NIFTY, "NIFTY 50")
    hdfc = next(r for r in before["adding"] if r["symbol"] == "HDFCBANK")
    weights, ff = mood.float_caps(CAPS, PROMOTERS)
    assert ff
    after = mood.index_movers(_members(weights), NIFTY, "NIFTY 50", free_float=True)
    hdfc2 = next(r for r in after["adding"] if r["symbol"] == "HDFCBANK")
    rel, rel2 = (next(r for r in m["taking"] if r["symbol"] == "RELIANCE") for m in (before, after))
    # by whole value HDFC weighed 12.69 / 205.38 = 6.2%; by free float 12.69 / 112.3 = 11.3%: its points almost double
    assert round(hdfc["points"]) == 44
    assert hdfc2["points"] > 1.7 * hdfc["points"]
    # and against Reliance (half held by its promoters) it now weighs what the exchange gives it: about 1.4 times Reliance's weight, not 0.7
    w = lambda s: weights[s] / sum(weights.values())          # noqa: E731
    assert 1.2 < w("HDFCBANK") / w("RELIANCE") < 1.6
    assert abs(rel2["points"]) < abs(hdfc2["points"]) / 2.5
    assert after["basis"] == "free_float" and "free-float" in after["note"] and "promoter group" in after["note"]
    assert before["basis"] == "market_value"


def test_live19a_006_free_float_needs_enough_holdings_and_fills_a_gap_with_the_median():
    # every company with a holding but one: that one takes the median free float of the others
    some = {k: v for k, v in PROMOTERS.items() if k != "OTHERS"}
    w, ff = mood.float_caps(CAPS, some)
    assert ff and w["OTHERS"] == CAPS["OTHERS"] * sorted((100 - v) / 100 for v in some.values())[len(some) // 2]
    # fewer than half with a stored holding: the whole values stand and the note says so
    w, ff = mood.float_caps(CAPS, {"HDFCBANK": 0.0})
    assert not ff and w == CAPS
    assert mood.index_movers(_members(w), NIFTY, "NIFTY 50", free_float=ff)["note"] == mood.FULL_NOTE


def test_live19a_006_the_promoter_share_is_the_newest_filings_total_else_its_promoter_rows(monkeypatch):
    store = {
        shareholders.KEY + "RELIANCE": {"name": "Reliance", "q": {"2026-06-30": {"ppct": 50.39, "rows": []},
                                                                   "2026-09-30": {"ppct": 50.07, "rows": []}}},
        shareholders.KEY + "OLDREAD": {"q": {"2026-09-30": {"rows": [["A Family Trust", "Individual", "promoter", 100, 30.5],
                                                                     ["B Holdings", "Company", "promoter", 50, 12.25],
                                                                     ["A Fund", "Mutual fund", "public", 10, 5.0]]}}},
        shareholders.KEY + "NOPROMOTER": {"q": {"2026-09-30": {"ppct": 0.0, "rows": [["A Fund", "Mutual fund", "public", 10, 5.0]]}}},
    }
    monkeypatch.setattr(db, "get_setting", lambda k: json.dumps(store[k]) if k in store else None)
    shareholders.forget()
    try:
        assert shareholders.promoter_share("RELIANCE") == 50.07
        assert shareholders.promoter_share("OLDREAD") == 42.75
        assert shareholders.promoter_share("NOPROMOTER") == 0.0
        assert shareholders.promoter_share("UNKNOWN") is None
    finally:
        shareholders.forget()


def test_live19a_006_the_mood_weighs_the_nifty_by_free_float_and_the_us_by_market_value(monkeypatch):
    m = mood.Mood(hub=None)
    monkeypatch.setattr(m, "_promoters", lambda region, syms: {s: PROMOTERS.get(s) for s in syms} if region == "IN" else {})
    w, ff = m._float_caps("IN", CAPS, list(CAPS))
    assert ff and w["HDFCBANK"] == CAPS["HDFCBANK"] and w["RELIANCE"] < CAPS["RELIANCE"] * 0.5
    w, ff = m._float_caps("US", CAPS, list(CAPS))
    assert not ff and w == CAPS


def test_live19a_006_the_points_card_says_its_basis_from_the_payload():
    src = (FRONT / "src/pages/PulseMood.tsx").read_text()
    assert "${m.note ||" in src


# ---------- LIVE19A-007: "Moved by" names what moved the sector its way ----------
def test_live19a_007_a_rising_sector_is_moved_by_its_risers():
    # Nifty Healthcare +0.72% at 13:05 IST: its two largest (Sun Pharma −0.64%, Divi's −0.74%) fell; the rise came from others
    rows = [{"symbol": "SUNPHARMA", "change_pct": -0.64}, {"symbol": "DIVISLAB", "change_pct": -0.74},
            {"symbol": "CIPLA", "change_pct": 1.9}, {"symbol": "APOLLOHOSP", "change_pct": 2.4}, {"symbol": "DRREDDY", "change_pct": 0.3}]
    caps = {"SUNPHARMA": 4.0, "DIVISLAB": 1.6, "CIPLA": 1.2, "APOLLOHOSP": 1.0, "DRREDDY": 1.0}
    got = mood.moved_by(rows, caps, 0.72)
    assert [r["symbol"] for r in got] == ["APOLLOHOSP", "CIPLA"]
    assert all(r["change_pct"] > 0 for r in got)
    # a falling sector by its fallers, largest pull first
    assert [r["symbol"] for r in mood.moved_by(rows, caps, -0.4)] == ["SUNPHARMA", "DIVISLAB"]
    # none of the members read moved its way: nothing named
    assert mood.moved_by([r for r in rows if r["change_pct"] < 0], caps, 0.72) == []
    # flat to two decimals: the largest pulls either way
    assert [r["symbol"] for r in mood.moved_by(rows, caps, 0.0)] == ["SUNPHARMA", "APOLLOHOSP"]


def test_live19a_007_more_of_each_sector_is_read_so_its_movers_can_be_found():
    assert mood.SECTOR_MEMBERS["IN"] >= 8 and mood.SECTOR_MEMBERS["US"] >= 5
    src = (FRONT / "src/pages/PulseMood.tsx").read_text()
    assert "moved it most in the direction it moved" in src


# ---------- LIVE19A-021 / LIVE18B-011: a main-board issue only BSE's list names gets its NSE page (lot and bids) ----------
def test_live19a_021_a_bse_only_main_board_issue_being_bid_for_is_looked_up_on_nse(monkeypatch):
    from datetime import datetime, timezone
    from app import ipo as I
    from app.intel import ipo_sources as S
    from tests import fake_ipo as F

    class Nse:
        asked: list = []

        def ipo_detail(self, symbol, series="EQ"):
            self.asked.append(symbol)
            if symbol == "JPL":
                return F.file("nse_detail_JPL.json")
            raise I.SourceError("nse", "no such page")

    class Feed:
        nse = Nse()

    now = datetime(2026, 10, 22, 6, 0, tzinfo=timezone.utc)          # 11:30 IST, bidding open (21-23 Oct)
    row = {"id": "in-bse-544999", "market": "IN", "segment": "mainboard", "name": "Jio Platforms Limited", "symbol": None, "bse_code": "544999",
           "open": "2026-10-21", "close": "2026-10-23", "exchanges": ["BSE"], "currency": "INR", "nkey": S.name_key("Jio Platforms Limited")}
    sme = {**row, "id": "in-bse-1", "bse_code": "1", "segment": "sme", "name": "Jio Platforms Limited"}
    rows = I.find_issue_pages([dict(row), dict(sme)], Feed(), now, [], sleep=lambda s: None)
    got = next(r for r in rows if r["id"] == "in-bse-544999")
    assert got["symbol"] == "JPL" and got["series"] == "EQ" and "NSE" in got["exchanges"]
    assert got["id"] == "in-bse-544999"                                   # follows and alerts are by the row's id
    # the row now has an NSE page: the list says so, and the detail read (lot, bids) takes it
    assert I.list_row({**got, "low": 1065.0, "high": 1119.0}, now)["page"] is True
    # an SME issue on BSE's own platform is never on NSE: not looked for
    assert next(r for r in rows if r["id"] == "in-bse-1").get("symbol") is None
    # tried once a day: a second run the same day asks nothing more
    n = len(Nse.asked)
    miss = {**row, "id": "in-bse-2", "bse_code": "2", "name": "Nowhere Issue Limited", "nkey": S.name_key("Nowhere Issue Limited")}
    first = I.find_issue_pages([miss], Feed(), now, [], sleep=lambda s: None)
    assert first[0].get("symbol") is None and first[0]["probe_at"] == "2026-10-22"
    asked = len(Nse.asked)
    I.find_issue_pages(first, Feed(), now, [], sleep=lambda s: None)
    assert len(Nse.asked) == asked and asked > n
