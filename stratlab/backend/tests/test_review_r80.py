"""Round 80 (launch check, signed-out visitor, 22 Oct 2026)."""
from app import main  # noqa: F401  (loads the app first, as the other review tests do)
from app import library, stock_pages


def test_mixed_case_brands_keep_their_capitals():
    # R80-016: "CONOCOPHILLIPS" came out as "Conocophillips"
    assert stock_pages.proper_name("CONOCOPHILLIPS") == "ConocoPhillips"
    assert stock_pages.proper_name("PEPSICO INC") == "PepsiCo Inc"
    assert stock_pages.proper_name("ABBVIE INC.") == "AbbVie Inc."
    assert stock_pages.proper_name("CHEVRON CORP") == "Chevron Corp"


def test_a_losing_library_strategy_says_its_checks_ran():
    # R80-005: "the checks weren't run" sat above a list of the checks' results
    e = {"verdict": {"verdict": "no_edge", "checks": [{"id": "oos", "status": "fail"}]}, "stats": {"ret": -4.2, "trades": 40}}
    line = library.reason(e)
    assert "weren't run" not in line and "shown for reference" in line


def test_the_stocks_search_form_keeps_one_row_and_fonts_dont_shift_it():
    # R80-002 / R80-015: the form wrapped to two rows on a phone, then jumped to one; fonts swapped in late
    html = stock_pages.STYLE
    assert "font-display:swap" not in html and "font-display:optional" in html
    assert "form.find{display:flex;gap:8px;flex-wrap:nowrap" in html and "form.find input{flex:1;min-width:0}" in html
    assert 'placeholder="Company or symbol"' in stock_pages._find_form("IN")


def test_a_session_yahoo_sends_blank_is_rebuilt_from_its_hours():
    # R81-002 / R81-001: Yahoo sent NVDA's 21 Oct daily candle blank; the chart skipped the day and the day's change was
    # measured from 20 Oct (-1.7% instead of -4.1%)
    from datetime import datetime, timedelta, timezone
    from zoneinfo import ZoneInfo
    import httpx
    from app.intel.yahoo import Yahoo
    ny = ZoneInfo("America/New_York")
    today = datetime.now(ny).replace(hour=0, minute=0, second=0, microsecond=0)
    d0, d1, d2 = today - timedelta(days=2), today - timedelta(days=1), today

    def at(d, h=9, m=30):
        return int(d.replace(hour=h, minute=m).timestamp())

    def handler(r):
        p = dict(r.url.params)
        meta = {"symbol": "NVDA", "currency": "USD", "exchangeTimezoneName": "America/New_York", "regularMarketPrice": 212.8,
                "regularMarketTime": at(d2, 13, 50), "chartPreviousClose": 200.0}
        if p["interval"] == "60m":
            ts = [at(d1, 9, 30), at(d1, 10, 30), at(d1, 15, 30)]
            q = {"open": [217.0, 219.0, 221.0], "high": [219.5, 222.0, 222.6], "low": [216.5, 218.0, 220.4],
                 "close": [219.0, 221.0, 221.97], "volume": [10, 20, 30]}
        else:
            ts = [at(d0), at(d1), at(d2)]
            q = {"open": [215.0, None, 220.0], "high": [217.0, None, 221.0], "low": [214.0, None, 211.0],
                 "close": [216.47, None, 212.8], "volume": [100, None, 50]}
        return httpx.Response(200, json={"chart": {"result": [{"meta": meta, "timestamp": ts, "indicators": {"quote": [q]}}]}})

    y = Yahoo(transport=httpx.MockTransport(handler))
    bars = y.chart("NVDA", "1d", 10, exact=True)["candles"]
    assert [b["t"][:10] for b in bars] == [d0.date().isoformat(), d1.date().isoformat(), d2.date().isoformat()]
    assert bars[1]["c"] == 221.97 and bars[1]["o"] == 217.0 and bars[1]["h"] == 222.6 and bars[1]["l"] == 216.5
    assert y.meta("NVDA")["prev_close"] == 221.97


def test_admin_lists_the_company_pages_price_job(monkeypatch):
    # R81-005: the job that moves the public company pages to each close had no row in Admin → Data and jobs
    from app import admin_jobs
    monkeypatch.setattr(main, "price_refresh_status", {"last_run": "2026-10-22T21:00:00+00:00", "IN": {"refreshed": 0, "left": 0, "failed": 0},
                                                      "US": {"refreshed": 0, "left": 120, "failed": 300}})
    rows = {r["name"]: r for r in admin_jobs.rows()}
    r = rows["Company pages' prices"]
    assert r["state"] == "bad" and "US: no page's price could be read in the last pass (300 tried)" in r["error"]
    assert any("US: 0 updated, 120 waiting, 300 not read" in x for x in r["log"])


def test_wire_stories_about_conflict_and_religion_stay_out_of_market_headlines():
    # R81-006
    from app.newsletter.content import OFF_TOPIC
    assert OFF_TOPIC.search("Israeli settlers steal Palestinians' olives as attacks on harvest grow more violent - Reuters")
    assert OFF_TOPIC.search("As Trump's support slips, white evangelicals remain his Republican bedrock - Reuters")
    assert not OFF_TOPIC.search("Wall Street falls as tech stocks slide")
    assert not OFF_TOPIC.search("Oil prices rise as supply worries grow")


def test_best_verdict_puts_all_passed_above_some_passed():
    # R81-013
    mk = lambda i, p, t, unseen: {"id": i, "verdict": {"verdict": "edge", "passed": p, "total": t}, "stats": {"unseen": unseen, "ret": 10, "trades": 50}}
    rows = library.search([mk("a", 2, 3, 9.0), mk("b", 3, 3, 1.0), mk("c", 2, 3, 5.0)])
    assert [r["id"] for r in rows] == ["b", "a", "c"]
