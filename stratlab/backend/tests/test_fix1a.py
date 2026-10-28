"""FIX-1A: the findings of the live-site review LIVE-1A that the backend answers."""
from datetime import datetime
from zoneinfo import ZoneInfo

from app import db, main  # noqa: F401, I001  (main first: it loads the modules in the order they need)
from app import ipo as I

NY, UTC = ZoneInfo("America/New_York"), ZoneInfo("UTC")


def _bars():
    return [{"t": "2026-10-27T00:00:00-04:00", "o": 4.1, "h": 6.0, "l": 4.0, "c": 5.5, "v": 1.0},
            {"t": "2026-10-28T00:00:00-04:00", "o": 4.1, "h": 6.2, "l": 4.0, "c": 6.07, "v": 1.0}]


def test_a_us_session_still_going_on_is_not_a_close():
    """LIVE1A-060: the 12:00 ET read put a midday price under "Close 28 Oct" (AMRO $6.07; the close was $5.86)."""
    row = {"market": "US", "symbol": "AMRO", "priced": "2026-10-27"}
    mid = datetime(2026, 10, 28, 12, 0, tzinfo=NY).astimezone(UTC)
    bars, first = I._settle(row, _bars(), _bars()[0], mid)
    assert [b["t"][:10] for b in bars] == ["2026-10-27"] and first["t"][:10] == "2026-10-27"
    # the listing day itself still going on: no first session yet
    one = _bars()[1:]
    bars, first = I._settle(row, one, one[0], mid)
    assert bars == [] and first is None
    # after the close and the closing print, the day's candle is its close
    late = datetime(2026, 10, 28, 16, 30, tzinfo=NY).astimezone(UTC)
    bars, first = I._settle(row, _bars(), _bars()[0], late)
    assert [b["t"][:10] for b in bars] == ["2026-10-27", "2026-10-28"] and bars[-1]["c"] == 6.07


def test_the_us_list_is_read_again_after_the_new_york_close():
    names = [n for n, _ in I.Job.SLOTS]
    assert "us-close" in names
    at = dict(I.Job.SLOTS)["us-close"]
    assert "02:30" < at < "06:00"           # IST: after 16:00 ET in summer and in winter time


def test_an_issue_size_with_both_parts_in_rupees_gives_the_parts():
    """LIVE1A-030: "Issue size" did not say whether it was all new shares or new shares plus a sale by existing holders."""
    row = {"market": "IN", "fresh_cr": 300.0, "ofs_cr": 368.0, "high": 330.0}
    sz = I.sizes(row)
    assert sz["amount"] == 668.0 and sz["basis"] == "stated" and sz["parts"]["fresh_cr"] == 300.0 and sz["parts"]["ofs_cr"] == 368.0
    only = I.sizes({"market": "IN", "fresh_cr": 179.0, "high": 150.0})
    assert only["amount"] == 179.0 and "parts" not in only


def test_the_after_the_close_read_runs_in_the_small_hours_only(monkeypatch):
    from datetime import timedelta
    monkeypatch.setattr(I, "run_marker", lambda name: None)
    job = I.Job(sleep=lambda s: None)
    base = datetime(2026, 10, 29, 3, 40, tzinfo=ZoneInfo("Asia/Kolkata")).astimezone(UTC)
    assert job.due("us-close", "03:30", base) == "2026-10-29"
    assert job.due("us-close", "03:30", base - timedelta(hours=1)) is None                   # 02:40 IST: not yet
    assert job.due("us-close", "03:30", base + timedelta(hours=3)) is None                   # 06:40 IST: past the window


def test_a_coin_sessions_today_is_the_utc_day_in_the_roll_up_too():
    """LIVE1A-044: the roll-up counted a crypto session's day from 00:00 IST, its page from 00:00 UTC: "Today $5" against "Today $33"."""
    import time_machine
    from app import risk
    snap = {"id": "s1", "name": "Ride the trend", "kind": "group", "instrument": {"market": "CRYPTO", "currency": "USD"},
            "account": {"capital": 10000.0, "equity": 10163.0, "realised": 0.0, "trades": 0}, "members": [],
            "day_equity": {"2026-10-27": 9900.0, "2026-10-28": 10100.0}, "closed": [], "equity_curve": []}
    with time_machine.travel(datetime(2026, 10, 28, 21, 0, tzinfo=UTC), tick=False):      # 02:30 IST on the 29th, still the 28th in UTC
        row = risk.summary([snap])["sessions"][0]
    assert row["today"] == 263.0 and row["session_pnl"] is None
    # a share session keeps India's day
    share = {**snap, "id": "s2", "instrument": {"market": "IN", "currency": "INR", "symbol": "TCS"}, "day_equity": {"2026-10-27": 9900.0, "2026-10-28": 10100.0}}
    with time_machine.travel(datetime(2026, 10, 28, 21, 0, tzinfo=UTC), tick=False):
        assert risk.summary([share])["sessions"][0]["today"] == 63.0


def test_a_sessions_chart_holds_enough_candles_for_its_longest_average():
    """LIVE1A-012: "price above SMA 200" on a chart of 150 daily candles had no line (the legend read "SMA 200 -")."""
    from app import live
    from app.models import Strategy
    s = Strategy(name="t", entry=[{"l": {"t": "price"}, "op": "gt", "r": {"t": "sma", "p": 200}}], exit=[{"l": {"t": "price"}, "op": "xb", "r": {"t": "sma", "p": 20}}])
    assert live.chart_window(s, 1000) == 300
    assert live.chart_window(s, 250) == 250                               # never more than it has
    short = Strategy(name="t", entry=[{"l": {"t": "price"}, "op": "gt", "r": {"t": "sma", "p": 20}}])
    assert live.chart_window(short, 1000) == 150
    huge = Strategy(name="t", entry=[{"l": {"t": "price"}, "op": "gt", "r": {"t": "sma", "p": 500}}])
    assert live.chart_window(huge, 5000) == live.CHART_BARS_MAX


def test_a_journal_with_real_trades_shows_them_by_default_not_the_replay_practice():
    """LIVE1A-059: after an upload the page stayed on "Both", so a practice trade from the chart replay counted in the stats and the verdict."""
    from pathlib import Path
    from app import journal as J
    from tests import world
    from tests.test_journal import PRO, manual
    import pytest as _p
    mp = _p.MonkeyPatch()
    built = world.build(mp)
    try:
        J._paired.clear()
        c = built["client"]
        assert manual(c).status_code == 200
        j = c.get("/trade/journal", headers=PRO).json()
        assert j["show"] == "all" and j["count"] == 1                    # no practice trade: nothing to filter
        uid = c.get("/me", headers=PRO).json()["id"]
        data = J.load(uid)
        data["practice"] = [{**data["manual"][0], "id": "practice-1", "symbol": "TCS", "entry_price": 3000, "exit_price": 2900}]
        J.save(uid, data)
        J._paired.clear()
        j = c.get("/trade/journal", headers=PRO).json()
        assert j["show"] == "real" and j["count"] == 1 and j["practice_count"] == 1 and j["real_count"] == 1
        # a person's own pick stands
        j = c.put("/trade/journal/settings", headers=PRO, json={"show": "all"}).json()
        assert j["show"] == "all" and j["count"] == 2
    finally:
        J._paired.clear()
        built["close"]()
        mp.undo()


def test_news_of_a_partnership_or_a_regulation_30_update_is_not_a_business_update():
    """LIVE1A-064: Reliance's "business updates" listed a Regulation 30 update, a media release and a franchise partnership."""
    from app import biz_updates as B
    url = "https://nsearchives.nseindia.com/corporate/RELIANCE_28102026.pdf"
    for subject in ("Update to disclosures dated 24-03-2017 and 05-11-2020 under Regulation 30 of SEBI (LODR)",
                    "Reliance and Surrey announce their partnership in Oval Invincibles franchise in The Hundred"):
        assert not B.is_update({"subject": subject, "text": "", "url": url})
    assert B.is_update({"subject": "Monthly Business Update for September 2026", "text": "", "url": url})
    # an update word far down a long description of something else does not count
    assert not B.is_update({"subject": "General Updates", "text": "x" * 500 + " sales volumes rose", "url": url})


def test_the_company_directory_names_both_markets_and_carries_structured_data():
    """LIVE1A-065/066: /stocks' description read "listed in US" (a loop overwrote the page's own wording), and the page had no JSON-LD."""
    from app import stock_pages
    page = stock_pages.index_page(None, "")
    assert 'content="Find any company listed in India or the US: price, results, margins, debt and filings, from reported data."' in page
    assert "application/ld+json" in page and "BreadcrumbList" in page
    assert "listed in US:" not in page
    # a search stays out of the index and carries none
    assert "application/ld+json" not in stock_pages.index_page(None, "tata")
