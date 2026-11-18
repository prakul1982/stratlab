"""Lane fix15 (LIVE12A site findings): each test fails before its fix and passes after."""
from datetime import datetime, timezone

from app import main  # noqa: F401, I001  (main first: it loads the modules in the order they need)
from app import exchange_days, ipo, official_close

HEAD = "TradDt,TckrSymb,SctySrs,OpnPric,HghPric,LwPric,ClsPric,LastPric,PrvsClsgPric\n"
# the listing days' cash bhavcopies (NSE, 3/5/6/9 Nov 2026: the opens LIVE12A-004 read in the exchange's own files)
FILES = {"2026-11-03": HEAD + "2026-11-03,SFCTECH,BE,355.10,360.00,330.00,340.20,340.20,321.00\n",
         "2026-11-05": HEAD + "2026-11-05,BCSSL,SM,91.00,92.00,84.00,85.10,85.10,82.00\n",
         "2026-11-06": HEAD + "2026-11-06,MAXENGS,ST,300.20,301.00,290.00,295.00,295.00,285.00\n"
                              "2026-11-06,HGSINDIALT,EQ,160.00,170.00,155.00,168.00,168.00,150.00\n",
         "2026-11-09": HEAD + "2026-11-09,VPFL,ST,94.00,95.00,88.00,89.30,89.30,94.00\n"}


def _rows():
    return [{"id": f"in-{s.lower()}", "market": "IN", "symbol": s, "listing": d, "price": p, "open": "2026-10-28", "close": "2026-10-30"}
            for s, d, p in (("SFCTECH", "2026-11-03", 321.0), ("BCSSL", "2026-11-05", 82.0), ("MAXENGS", "2026-11-06", 285.0),
                            ("HGSINDIALT", "2026-11-06", 150.0), ("VPFL", "2026-11-09", 94.0))]


# ---------- LIVE12A-004 / LIVE12B-020: the listing price of every recently listed issue, between the list reads ----------
def test_the_stored_recent_issues_take_their_listing_day_opens_without_waiting_for_the_evening_read(monkeypatch):
    stored = {"as_of": "2026-11-18T07:40:00+05:30", "rows": _rows(), "checked": {}}
    saved = []
    monkeypatch.setattr(ipo, "load", lambda m: stored)
    monkeypatch.setattr(ipo, "save", lambda m, rows, checked, as_of=None: saved.append(rows) or stored.update(rows=rows))
    monkeypatch.setattr(official_close, "_src", {**official_close._src, "files": lambda: "files"})
    reads = []
    monkeypatch.setattr(exchange_days, "cash_closes", lambda files, day: reads.append(day) or exchange_days.cash_rows(FILES[day.isoformat()]))
    monkeypatch.setattr(ipo, "_official", lambda sym, d, now, fetch: None)
    now = datetime(2026, 11, 18, 4, 10, tzinfo=timezone.utc)          # 09:40 IST, the morning after a deploy: no list read since
    job = ipo.Job(sleep=lambda s: None)
    assert job.fill_listing_days(now) == 5 and saved
    got = {r["symbol"]: ipo.list_row(r, now)["perf"]["listing_price"] for r in stored["rows"]}
    assert got == {"SFCTECH": 355.1, "BCSSL": 91.0, "MAXENGS": 300.2, "HGSINDIALT": 160.0, "VPFL": 94.0}
    assert ipo.list_row(stored["rows"][0], now)["perf"]["listing_change_pct"] == 10.62
    # read once: a later pass reads nothing more, and a file not out yet is tried again the next day, not every pass
    n = len(reads)
    assert job.fill_listing_days(now) == 0 and len(reads) == n


def test_a_us_issue_has_its_listing_price_from_its_first_session_after_the_pricing():
    class Yahoo:
        def chart(self, symbol, tf="1d", days=365, **kw):
            return {"candles": [{"t": "2026-11-13T00:00:00-05:00", "o": 92.0, "h": 99.0, "l": 90.0, "c": 95.0},
                                {"t": "2026-11-17T00:00:00-05:00", "o": 96.0, "h": 97.0, "l": 93.0, "c": 94.0}]}
    # priced Thursday 12 Nov after the close; its first session Friday 13 Nov
    row = {"market": "US", "symbol": "NEWCO", "priced": "2026-11-12", "price": 78.0}
    p = ipo.performance(row, Yahoo(), now=datetime(2026, 11, 18, 4, 0, tzinfo=timezone.utc))
    assert p["listing_price"] == 92.0 and p["listing_change_pct"] == 17.95 and p["day_close"] == 95.0 and p["latest"] == 94.0
    assert ipo.with_listing_day(row, p)["listing_price"] == 92.0            # kept by the stored-read check
    # a first candle long after the pricing (the early sessions missing) is still no listing price
    late = {**row, "priced": "2026-11-02"}
    assert ipo.performance(late, Yahoo(), now=datetime(2026, 11, 18, 4, 0, tzinfo=timezone.utc)) is None


# ---------- LIVE12A-003: the sector charts are brought to each close by their own job, soon after a start ----------
def test_the_sector_charts_are_brought_to_the_close_by_their_own_job_soon_after_a_start(monkeypatch):
    import pytest
    from app import main as M
    ran, slept = [], []

    class Stop(Exception):
        pass

    def sleep(s):
        slept.append(s)
        if len(slept) > 2:
            raise Stop

    monkeypatch.setattr(M, "rotation_after_close", lambda now=None: ran.append(len(slept)) or [])
    monkeypatch.setattr(M.leader, "leading", lambda: True)
    with pytest.raises(Stop):
        M.rotation_job(sleep=sleep)
    assert slept[0] <= 60 and ran[:2] == [1, 2] and slept[1] <= 5 * 60
    # the company pages' price pass no longer carries it (it waits minutes after a start and reads hundreds of pages first)
    monkeypatch.setattr(M.stock_page_store, "refresh_prices", lambda region, *a, **k: {"refreshed": 0, "left": 0})
    monkeypatch.setattr(M, "rotation_after_close", lambda now=None: ran.append("price pass"))
    M.stock_price_refresh_once(sleep=lambda s: None)
    assert "price pass" not in ran
