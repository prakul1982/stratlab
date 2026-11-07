"""The two-year IPO history (ipo_history.py): the admin-run import on synthetic exchange answers, its bounds and that running it again
changes nothing, the daily job keeping it current, and the admin routes."""
from datetime import date, datetime, timedelta

import pytest
import time_machine

from app import (  # noqa: F401  (main first: it loads the modules in the order they need)
    db,
    main,
)
from app import ipo as I
from app import ipo_history as H
from tests.fake_db import headers
from tests.test_ipo import (  # noqa: F401  (w: the IPO tests' world)
    NOW,
    TODAY,
    FakeYahoo,
    bar,
    read_all,
    w,
)


def past(symbol, company, series, start, end, listing, price):
    return {"symbol": symbol, "company": company, "securityType": series, "ipoStartDate": start, "ipoEndDate": end, "listingDate": listing,
            "issuePrice": str(price), "priceRange": f"Rs.{price - 5} to Rs.{price}"}


PAST = [past("ALPHA", "Alpha Limited", "EQ", "03-MAR-2025", "05-MAR-2025", "10-MAR-2025", 100),
        past("BETA", "Beta Foods Limited", "SME", "28-APR-2026", "30-APR-2026", "05-MAY-2026", 50),
        past("OLDCO", "Old Company Limited", "EQ", "20-AUG-2024", "22-AUG-2024", "27-AUG-2024", 300),          # before the 24 months
        past("GONE", "Gone Limited - Withdrawn", "EQ", "10-JUN-2025", "12-JUN-2025", "17-JUN-2025", 80),      # did not go ahead
        past("BONDS", "Bond Issuer Limited", "DEBT", "10-JUN-2025", "12-JUN-2025", "17-JUN-2025", 1000)]       # not shares

DETAIL = {"ALPHA": {"metaInfo": {"industry": "Capital Goods", "listingDate": "10-Mar-2025"},
                    "issueInfo": {"dataList": [{"title": "Alpha Limited", "value": ""}, {"title": "Symbol", "value": "ALPHA"},
                                               {"title": "Issue Period", "value": "03-Mar-2025 to 05-Mar-2025"},
                                               {"title": "Issue Size", "value": "Fresh issue of Rs. 300 crore and offer for sale of Rs. 200 crore"},
                                               {"title": "Price Range", "value": "Rs. 95 to Rs. 100 per Equity Share"},
                                               {"title": "Bid Lot", "value": "150 Equity Shares"}]},
                    "bidDetails": [{"srNo": "1", "category": "Qualified Institutional Buyers(QIBs)", "noOfSharesOffered": "1000000", "noOfsharesBid": "80000000", "noOfTime": "80"},
                                   {"srNo": "2", "category": "Non Institutional Investors", "noOfSharesOffered": "750000", "noOfsharesBid": "30000000", "noOfTime": "40"},
                                   {"srNo": "3", "category": "Retail Individual Investors(RIIs)", "noOfSharesOffered": "1750000", "noOfsharesBid": "105000000", "noOfTime": "60"},
                                   {"srNo": None, "category": "Total", "noOfSharesOffered": "3500000", "noOfsharesBid": "215000000", "noOfTime": "61.43"}]}}


class Feed:
    """NSE's past issues by closing day and its issue pages; BSE's listed-issue table by year. `calls` records every read."""

    def __init__(self, bse_down=False):
        self.calls, self.bse_down = [], bse_down
        outer = self

        class NSE:
            def ipo_past(self, frm, to):
                outer.calls.append(("past", frm.date(), to.date()))
                return [r for r in PAST if frm.date() <= datetime.strptime(r["ipoEndDate"], "%d-%b-%Y").date() <= to.date()]

            def ipo_detail(self, symbol, series="EQ"):
                outer.calls.append(("detail", symbol))
                return DETAIL.get(symbol, {"issueInfo": {"dataList": []}})

        class BSE:
            def ipo_listed(self, year):
                outer.calls.append(("bse", year))
                if outer.bse_down:
                    raise I.SourceError("the exchange", "isn't answering.", busy=True)
                return {2025: {"Table": [
                    {"CompanyName": "Alpha Limited", "IssuePrice": 100.0, "ListedOn": "2025-03-10T00:00:00", "ListingDayClose": 120.0, "CurrentPrice": 90.0,
                     "IMAGE": "https://www.bseindia.com/stock-share-price/alpha-ltd/alpha/544001/"},
                    {"CompanyName": "Gamma Industries Ltd", "IssuePrice": 200.0, "ListedOn": "2025-06-02T00:00:00", "ListingDayClose": 210.0, "CurrentPrice": 260.0,
                     "IMAGE": "https://www.bseindia.com/stock-share-price/gamma-industries-ltd/gamma/543210/"}]}}.get(year, {"Table": []})

        self.nse, self.bse = NSE(), BSE()


@pytest.fixture
def hist(monkeypatch):
    with time_machine.travel(NOW, tick=False):
        from tests import world as W
        world = W.build(monkeypatch)
        yield world
        world["close"]()


YAHOO = {"ALPHA.NS": [bar("2025-03-10", 115.0, 121.0), bar("2026-10-23", 92.0, 91.0)],
         "BETA-SM.NS": [bar("2026-05-05", 60.0, 63.0), bar("2026-10-23", 40.0, 41.0)]}


def test_the_import_reads_two_years_a_quarter_at_a_time_and_keeps_only_listed_shares_in_the_window(hist):
    feed = Feed()
    run = H.backfill(feed, TODAY, FakeYahoo(YAHOO), sleep=lambda s: None, now=NOW)
    windows = [c for c in feed.calls if c[0] == "past"]
    assert windows[0][1] == H.cutoff(TODAY) == date(2024, 10, 25) and windows[-1][2] == TODAY
    assert all((t - f).days < H.WINDOW_DAYS for _k, f, t in windows)
    assert all(b[1] == a[2] + timedelta(days=1) for a, b in zip(windows, windows[1:]))        # no gap, no overlap
    assert [c[1] for c in feed.calls if c[0] == "bse"] == [2024, 2025, 2026]
    rows = {r["id"]: r for r in H.load()["rows"]}
    assert set(rows) == {"in-alpha", "in-beta", "in-bse-543210"}                  # not the old one, the withdrawn one or the debt issue
    assert rows["in-alpha"]["segment"] == "mainboard" and rows["in-beta"]["segment"] == "sme" and rows["in-bse-543210"]["segment"] == "mainboard"
    a = rows["in-alpha"]
    assert a["price"] == 100 and a["listing"] == "2025-03-10" and a["industry"] == "Capital Goods"
    assert a["fresh_cr"] == 300 and a["ofs_cr"] == 200 and a["bse_code"] == "544001" and a["exchanges"] == ["BSE", "NSE"]
    assert next(x for x in a["sub"]["rows"] if x["label"] == "Retail individual investors")["times"] == 60
    assert a["perf"]["listing_change_pct"] == 15.0 and a["perf"]["day_change_pct"] == 21.0 and a["perf"]["change_pct"] == -9.0
    assert rows["in-beta"]["perf"]["day_change_pct"] == 26.0                      # an SME stock's prices, under its SME symbol
    assert rows["in-bse-543210"]["bse_perf"]["latest"] == 260.0 and rows["in-bse-543210"]["price"] == 200.0
    assert run["rows"] == 3 and run["added"] == 3 and run["detailed"] == 1 and run["pending_details"] == 0 and not run["problems"]


def test_running_the_import_again_adds_nothing_and_reads_no_issue_page_twice(hist):
    H.backfill(Feed(), TODAY, FakeYahoo(YAHOO), sleep=lambda s: None, now=NOW)
    first = H.load()["rows"]
    feed = Feed()
    run = H.backfill(feed, TODAY, FakeYahoo(YAHOO), sleep=lambda s: None, now=NOW)
    assert run["added"] == 0 and run["detailed"] == 0 and not [c for c in feed.calls if c[0] == "detail"]
    strip = lambda rows: [{k: v for k, v in r.items() if k != "perf"} for r in rows]
    assert strip(H.load()["rows"]) == strip(first)
    assert len(H.load()["runs"]) == 2


def test_the_import_is_bounded_per_run_and_a_failing_source_leaves_the_rest(hist):
    run = H.backfill(Feed(bse_down=True), TODAY, None, details=0, sleep=lambda s: None, now=NOW)
    assert run["rows"] == 2 and run["detailed"] == 0 and run["pending_details"] == 2 and run["pending_prices"] is None
    assert any("listed issues of 2025" in p for p in run["problems"])
    feed = Feed()
    run = H.backfill(feed, TODAY, None, details=1, sleep=lambda s: None, now=NOW)
    assert run["rows"] == 3 and len([c for c in feed.calls if c[0] == "detail"]) == 1 and run["pending_details"] == 1


def test_a_page_that_gave_nothing_is_tried_again_only_after_a_week(hist):
    H.backfill(Feed(), TODAY, None, sleep=lambda s: None, now=NOW)
    beta = next(r for r in H.load()["rows"] if r["id"] == "in-beta")
    assert beta["detail_tried"] == TODAY.isoformat() and not beta.get("detail_at")
    assert not H.wants_detail(beta, TODAY) and H.wants_detail(beta, date(2026, 11, 2))


def test_the_daily_job_keeps_the_history_current(w):     # noqa: F811
    read_all(w)
    live = {r["id"]: r for r in I.load("IN")["rows"] if I.stage_of(r, NOW) == "listed"}
    rows = {r["id"]: r for r in H.load()["rows"]}
    assert live and set(live) <= set(rows)
    assert "in-bonfig" in rows and rows["in-bonfig"]["perf"]["listing_change_pct"] is not None
    assert all(r["listing"] <= TODAY.isoformat() for r in rows.values())
    assert not any(k in r for r in rows.values() for k in H.DROP)                 # the history keeps the facts, not the documents
    assert H.absorb(I.load("IN")["rows"], TODAY, NOW) == 0                         # nothing new: nothing written


def test_the_history_lives_in_the_market_data_store():
    from app import market_store
    assert H.HIST_KEY.startswith(market_store.MARKET_PREFIXES)


def test_the_admin_routes(hist, monkeypatch):
    monkeypatch.setitem(I._wire, "feed", lambda: Feed())
    monkeypatch.setitem(I._wire, "yahoo", lambda: FakeYahoo(YAHOO))
    started = []
    monkeypatch.setattr(H, "_spawn", lambda fn: (started.append(1), fn()))
    c = hist["client"]
    assert c.post("/admin/ipos/history/backfill", headers=headers("basic-token")).status_code in (401, 403)
    assert c.get("/admin/ipos/history", headers=headers("basic-token")).status_code in (401, 403)
    assert c.post("/admin/ipos/history/backfill", headers=headers("admin-token")).json()["started"] is True and started
    got = c.get("/admin/ipos/history", headers=headers("admin-token")).json()
    assert got["rows"] == 3 and got["segments"] == {"mainboard": 2, "sme": 1, "not recorded": 0} and got["last_runs"][-1]["detailed"] == 1
    # the stored rows, for the study (python -m app.ipo_study --rows FILE): admin only
    assert c.get("/admin/ipos/history/rows", headers=headers("basic-token")).status_code in (401, 403)
    rows = c.get("/admin/ipos/history/rows", headers=headers("admin-token")).json()
    assert len(rows["rows"]) == 3 and all(r.get("id") for r in rows["rows"]) and rows["as_of"]
    from app import admin_jobs
    row = next(r for r in admin_jobs.rows() if r["id"] == "ipo")
    assert {"label": "Import two-year history", "path": "/admin/ipos/history/backfill"} in row["run"]


def test_an_nse_sme_stock_is_priced_under_its_sme_symbol():
    assert I.yahoo_symbol({"market": "IN", "segment": "sme", "symbol": "RAVITA"}) == "RAVITA-SM.NS"
    assert I.yahoo_symbol({"market": "IN", "segment": "mainboard", "symbol": "TONBO"}) == "TONBO.NS"
