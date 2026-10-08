"""Round 5, the owner's review on the live site (8 Oct 2026): each test is built on the real example the reviewer saw."""
import json

from app import db, investor
from tests.test_deepdive import api  # noqa: F401  (a fixture)


# ---------- R5O-003: the watchlist's two tabs read one price, with its time ----------
def test_at_a_glance_takes_the_list_tabs_quote_not_a_cached_candle():
    # 8 Oct 15:01 IST: the cached daily candle said TCS 2,106.70 +1.3%; the List tab's quote said 2,061.30 -0.91%
    trend = {"price": 2106.70, "chg": 1.27, "stage": 4, "t": "2026-10-08T00:00:00+05:30"}
    quote = {"price": 2061.30, "change_pct": -0.91, "at": "2026-10-08T15:01:12+05:30"}
    got = investor.price_of(quote, trend)
    assert got == {"price": 2061.30, "chg": -0.91, "price_at": "2026-10-08T15:01:12+05:30"}
    # no quote: the candle stands in, dated by its day only (never passed off as the price of the moment)
    assert investor.price_of(None, trend) == {"price": 2106.70, "chg": 1.27, "price_at": "2026-10-08"}
    assert investor.price_of({"price": None}, None) == {"price": None, "chg": None, "price_at": None}


def test_investor_endpoint_uses_the_quotes_call(api, monkeypatch):  # noqa: F811
    from app import main
    c, who, _calls, _usage = api
    who["p"] = {"id": "u1", "plan": "pro", "_plan": "pro"}
    db.set_setting("watchlist:u1", json.dumps({"items": [{"region": "IN", "symbol": "ACME"}]}))
    asked = []

    def quotes(region, syms):
        asked.append((region, list(syms)))
        return {"ACME": {"price": 2061.30, "change_pct": -0.91, "at": "2026-10-08T15:01:00+05:30"}}
    monkeypatch.setattr(main.research_hub, "quotes", quotes)
    monkeypatch.setattr(main, "price_trend", lambda s, m="IN": {"price": 2106.70, "chg": 1.3, "stage": 2, "st_up": True, "t": "2026-10-08"})
    row = c.get("/research/investor").json()["rows"][0]
    assert asked == [("IN", ["ACME"])]
    assert (row["price"], row["chg"], row["price_at"]) == (2061.30, -0.91, "2026-10-08T15:01:00+05:30") and row["stage"] == 2
