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
                                                      "US": {"refreshed": 0, "left": 120, "failed": 300, "errors": 300}})
    rows = {r["name"]: r for r in admin_jobs.rows()}
    r = rows["Company pages' prices"]
    assert r["state"] == "bad" and "US: no page's price could be read in the last pass (300 tried)" in r["error"]
    assert any(x.startswith("US: 0 updated, 120 waiting, 0 without a newer close yet") and x.endswith("300 not read") for x in r["log"])


def test_companies_without_a_newer_close_are_not_a_problem(monkeypatch):
    # R82 (seen in Admin): 299 small India companies with no candle at the last close read as "no page could be read"
    from app import admin_jobs
    monkeypatch.setattr(main, "price_refresh_status", {"last_run": "2026-10-22T21:32:29+00:00",
                                                      "IN": {"refreshed": 1, "left": 1033, "failed": 299, "errors": 0},
                                                      "US": {"refreshed": 297, "left": 6018, "failed": 3, "errors": 3}})
    r = {r["name"]: r for r in admin_jobs.rows()}["Company pages' prices"]
    assert r["state"] == "ok" and r["error"] is None
    assert any(x.startswith("India: 1 updated, 1033 waiting, 299 without a newer close yet") for x in r["log"])


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


def test_an_options_trade_says_when_its_prices_paused():
    # R81-012: a stop came 50% late after 28 minutes without live prices; the trade's record now says why
    from tests.test_options import at, contracts, quotes, straddle
    from app.options.engine import OptionsEngine
    e, c = OptionsEngine(straddle()), contracts()
    e.step(at("09:30"), 25000, c, quotes(25000), True)
    e.step(at("12:25"), 25000, c, quotes(25000), False)                  # the prices stop
    e.step(at("12:40"), 25000, c, quotes(25000), False)
    e.step(at("12:53"), 25000, c, quotes(25000, bump=60), True)         # back, far past the stop
    t = e.trades[-1]
    assert t["why"] == "Stop loss"
    assert t["note"] == "No live prices from 12:25 to 12:53, so the stops and the daily loss cap were checked when they returned"


def test_a_short_blip_leaves_no_note():
    from tests.test_options import at, contracts, quotes, straddle
    from app.options.engine import OptionsEngine
    e, c = OptionsEngine(straddle()), contracts()
    e.step(at("09:30"), 25000, c, quotes(25000), True)
    e.step(at("10:00"), 25000, c, quotes(25000), False)
    e.step(at("10:01"), 25000, c, quotes(25000, bump=60), True)
    assert "note" not in e.trades[-1]


def test_a_gulf_markets_story_stays_out_of_the_us_and_india_briefs():
    # R81-010
    from app.newsletter.content import other_region
    t = "Gulf markets fall as fresh Houthi strikes on Saudi Arabia raise regional risk"
    assert other_region("US", t) and other_region("IN", t)
    assert not other_region("US", "Wall Street falls as Gulf markets slide")      # names this market too
    assert not other_region("US", "Oil jumps after Houthi strikes")


def test_a_brief_preview_ends_at_a_sentence_or_an_ellipsis():
    # R82-008: the Briefs list cut summaries mid-word ("…Stage 2 + S", "…without the Supe")
    from app import email_kit
    long = ("The S&P 500 fell 1.2% and the NASDAQ 2.6% on the week. " * 3) + "Twelve companies held Stage 2 without the Supertrend turning."
    out = email_kit.short_line(long, 200)
    assert len(out) <= 200 and (out.endswith(".") or out.endswith("…"))


def test_an_amount_in_an_email_stays_on_one_line():
    # R82-016: at phone width "−" split from "₹620" and "(+" from "₹3,250)"
    from app import email_kit
    html = email_kit.para("Today: 2 trades closed (1 won), −₹620; held (+₹3,250) and 1.2% <b>").html
    assert '<span style="white-space:nowrap">−₹620</span>' in html
    assert '<span style="white-space:nowrap">(+₹3,250)</span>' in html
    assert "&lt;b&gt;" in html                     # the rest is still escaped


def test_results_versus_expectations_has_one_row_per_quarter():
    # R84-001: NVDA showed "Jun 2026" twice with the same figures under "4 of 4 quarters beat"
    from app.intel.company import reported_quarters
    rows = [{"period": "2026-09-30", "actual": 2.22, "estimate": 2.14}, {"period": "2026-06-30", "actual": 1.87, "estimate": 1.79},
            {"period": "2026-06-30", "actual": 1.87, "estimate": 1.79}, {"period": "2026-03-31", "actual": 1.62, "estimate": 1.56},
            {"period": "2025-12-31", "actual": 1.5, "estimate": 1.4}, {"period": "2027-01-31", "actual": 9, "estimate": 9}]
    got = reported_quarters(rows, "2026-10-23")
    assert [r["period"] for r in got] == ["2025-12-31", "2026-03-31", "2026-06-30", "2026-09-30"]


def test_the_page_price_row_waits_for_the_broker_login_without_a_problem(monkeypatch):
    # R84-005: before the 08:00 IST login the row was a red Problem, "no page's price could be read (1 tried)"
    from app import admin_jobs
    monkeypatch.setattr(main, "price_refresh_status", {"last_run": "2026-10-23T01:00:00+00:00",
                                                      "IN": {"refreshed": 0, "left": 1300, "failed": 1, "errors": 1, "source_down": True},
                                                      "US": {"refreshed": 0, "left": 0, "failed": 0, "errors": 0}})
    r = {r["name"]: r for r in admin_jobs.rows()}["Company pages' prices"]
    assert r["state"] == "ok" and r["error"] is None
    assert any(x.startswith("India: waiting for the price source") for x in r["log"])


# R84-003: the kept India sector chart was a session behind after the evening logout
def test_rotation_after_close_brings_kept_copies_to_the_close(monkeypatch):
    import json as _json
    from datetime import date as _date, datetime as _dt, timezone as _tz
    from app import db as _db
    from tests.fake_db import FakeSupabase
    monkeypatch.setattr(_db, "_client", FakeSupabase())
    ran = []

    class Prov:
        def ready(self):
            return True
    monkeypatch.setattr(main.markets, "provider", lambda r: Prov())
    monkeypatch.setattr(main.stock_pages, "last_close", lambda r, now=None: (_date(2026, 10, 22), None))

    def run(markets, region, set_, members, interval, tail):
        ran.append((region, interval))
        return {"rows": [{"points": [{"t": "2026-10-22"}]}], "skipped": [], "as_of": "2026-10-22", "interval": interval, "tail": tail,
                "v": main.rotation.VERSION}
    monkeypatch.setattr(main.rotation, "run", run)
    _db.set_setting("rotation:last:IN:sectors:weekly:5", _json.dumps({"rows": [1], "as_of": "2026-10-21"}))
    _db.set_setting("rotation:last:US:sectors:weekly:5", _json.dumps({"rows": [1], "as_of": "2026-10-22", "v": main.rotation.VERSION}))
    done = main.rotation_after_close(_dt(2026, 10, 22, 12, 0, tzinfo=_tz.utc))
    assert done == ["IN weekly", "IN daily", "US daily"] and ran == [("IN", "weekly"), ("IN", "daily"), ("US", "daily")]
    kept = _db.json_value(_db.get_setting("rotation:last:IN:sectors:weekly:5"), {})
    assert kept["as_of"] == "2026-10-22" and kept["name"] == "NSE sector indices" and kept["market"] == "IN"
    ran.clear()
    assert main.rotation_after_close() == [] and ran == []            # already at the close: nothing re-run

