"""Lane site76: the LIVE14A / LIVE14B site findings (live review after Release 75, Wed 18 Nov 2026)."""
import time
from datetime import datetime, timezone

import httpx

from app import main  # noqa: F401, I001  (first: the app loads its jobs before the modules built on them)
from app.intel import yahoo as Y
from app.intel.company import index_level


def _answer(price: float, last: float, start: float, end: float) -> dict:
    return {"chart": {"result": [{
        "meta": {"symbol": "^IXIC", "currency": "USD", "exchangeTimezoneName": "America/New_York", "instrumentType": "INDEX",
                 "regularMarketPrice": price, "regularMarketTime": int(last),
                 "currentTradingPeriod": {"regular": {"start": int(start), "end": int(end)}}},
        "timestamp": [int(start)],
        "indicators": {"quote": [{"open": [price], "high": [price], "low": [price], "close": [price], "volume": [1]}]}}], "error": None}}


def test_live14a_001_a_copy_the_edge_kept_mid_session_is_asked_again_at_another_address_and_the_newer_stands():
    """LIVE14A-001: at 14:49 ET on 18 Nov the source's query2 host answered ^IXIC's 1-minute address with 24,322.707 at 15:52:50 UTC
    (10:52 ET), the level Mood showed for 3.7 h, while the other addresses had the live 24,411. The stale answer is detected by its
    own session (trading now, last trade 4 h old) and asked again at the other host with a window rounded to the minute."""
    now = time.time()
    start, end = now - 5 * 3600, now + 2 * 3600
    seen = []

    def reply(r: httpx.Request):
        seen.append(str(r.url))
        if r.url.host == "query2.finance.yahoo.com":
            return httpx.Response(200, json=_answer(24411.17, now - 20, start, end))
        return httpx.Response(200, json=_answer(24322.71, now - 4 * 3600, start, end))
    y = Y.Yahoo(transport=httpx.MockTransport(reply))
    m = y.meta("^IXIC")
    assert m["price"] == 24411.17
    assert len(seen) == 2 and "query2" in seen[1]
    # the fresh address's window ends on a minute, not on the hour the kept copy's does
    p2 = int(httpx.URL(seen[1]).params["period2"])
    assert p2 % 60 == 0 and p2 - now <= 60


def test_live14a_001_a_live_answer_is_not_asked_twice_and_a_thin_stock_is_not_asked_again_for_ten_minutes():
    now = time.time()
    start, end = now - 3600, now + 3600
    calls = []
    y = Y.Yahoo(transport=httpx.MockTransport(lambda r: (calls.append(r.url.host), httpx.Response(200, json=_answer(10.0, now - 30, start, end)))[1]))
    y.meta("^GSPC")
    assert calls == ["query1.finance.yahoo.com"]
    # a thin stock whose last trade really is old: one re-ask, then none for EDGE_MISS_FOR
    calls.clear()
    y2 = Y.Yahoo(transport=httpx.MockTransport(lambda r: (calls.append(r.url.host), httpx.Response(200, json=_answer(3.0, now - 7200, start, end)))[1]))
    y2.meta("THIN")
    y2.cache.clear()
    y2.meta("THIN")
    assert calls.count("query2.finance.yahoo.com") == 1


def test_live14a_001_stale_edge_rule():
    t0 = 1_795_000_000.0
    meta = {"currentTradingPeriod": {"regular": {"start": t0, "end": t0 + 6.5 * 3600}}, "regularMarketTime": t0 + 3600}
    assert not Y.stale_edge(meta, t0 + 3600 + 300)            # five minutes old: fine
    assert Y.stale_edge(meta, t0 + 3600 + 3 * 3600)           # three hours old in the session: a kept copy
    assert Y.stale_edge(meta, t0 + 7 * 3600)                   # after the close, a last trade from mid-session
    assert not Y.stale_edge({**meta, "regularMarketTime": t0 + 6.5 * 3600 - 1}, t0 + 7 * 3600)   # the close's own last trade
    assert not Y.stale_edge(meta, t0 - 60)                     # before the session
    assert not Y.stale_edge({"regularMarketTime": t0}, t0 + 99999)   # no period: can't be said
    assert not Y.stale_edge({**meta, "instrumentType": "CRYPTOCURRENCY"}, t0 + 5 * 3600)


def test_live14a_001_a_level_read_long_ago_in_the_session_is_delayed_not_live():
    """The index row at 14:35 ET read at 10:52 ET: `delayed`, never `live` (the page then says "as of 10:52 ET", not "today")."""
    now = datetime(2026, 11, 18, 19, 35, tzinfo=timezone.utc)           # 14:35 ET, Wed 18 Nov: NYSE open
    q = {"price": 24322.71, "prev_close": 24327.0, "at": "2026-11-18T15:52:50+00:00", "high52": 25000.0}
    lv = index_level("NASDAQ", q, "US", now)
    assert lv["delayed"] is True and lv["live"] is False and lv["stale"] is False and lv["day"] == "2026-11-18"
    fresh = index_level("NASDAQ", {**q, "at": "2026-11-18T19:33:00+00:00"}, "US", now)
    assert fresh["live"] is True and fresh["delayed"] is False
    # after the close the level is the close's, never delayed
    shut = index_level("NASDAQ", {**q, "at": "2026-11-18T21:00:00+00:00"}, "US", datetime(2026, 11, 18, 23, 0, tzinfo=timezone.utc))
    assert shut["delayed"] is False and shut["live"] is False


def test_live14a_001_the_mood_headline_rests_only_on_levels_read_in_the_last_minutes():
    from pathlib import Path
    src = Path(__file__).resolve().parents[1].joinpath("app/intel/mood.py").read_text()
    assert 'fresh = [i for i in levels if not i.get("delayed")]' in src
    assert 'headline_of(fresh, sectors, cmp' in src


def test_live14a_009_the_days_largest_companies_have_their_release_looked_for_tracked_or_not(monkeypatch):
    """LOW's release, filed before the open on 18 Nov, was not on its row 8 h later: only tracked companies were looked up. The window's
    largest companies are looked up too; a release found for one nobody tracks has nobody to tell (told=True)."""
    from app import results as R
    rows = [{"symbol": s, "date": "2026-11-18", "purpose": "Quarterly results"} for s in ("LOW", "TJX", "TINY", "PANW")]
    rows.append({"symbol": "OLD", "date": "2026-11-18", "out": {"at": "2026-11-18"}})
    monkeypatch.setattr(R, "_snap", lambda region: {"LOW": {"market_cap": 120e3}, "TJX": {"market_cap": 160e3}, "TINY": {"market_cap": 5.0},
                                                    "PANW": {"market_cap": 220e3}, "OLD": {"market_cap": 9e9}})
    assert R.largest_due("US", rows, "2026-11-16", "2026-11-18", n=3) == {"PANW", "TJX", "LOW"}
    store = {"rows": [dict(r) for r in rows]}
    monkeypatch.setattr(R, "load", lambda region: store)
    monkeypatch.setattr(R, "save", lambda region, rs: store.update(rows=rs))
    monkeypatch.setattr(R, "us_out", lambda fh, sec, r: {"at": r["date"], "title": "8-K", "url": None, "numbers": []} if r["symbol"] in ("LOW", "TJX") else None)
    from datetime import date
    found = R.check_out("US", {}, {"LOW", "TJX"}, date(2026, 11, 18), tracked={"TJX"})
    assert {r["symbol"] for r in found} == {"LOW", "TJX"}
    by = {r["symbol"]: r for r in store["rows"]}
    assert by["LOW"]["out"]["title"] == "8-K" and by["LOW"]["told"] is True           # nobody tracks LOW: nothing to send
    assert by["TJX"]["told"] is False                                                  # TJX's people are told by follow_up
    src = (__import__("pathlib").Path(R.__file__)).read_text()
    assert "look = symbols | largest_due(region, load(region)[\"rows\"], frm, day.isoformat())" in src


def test_live14a_013_an_indian_issue_row_says_whether_its_issue_page_was_found_and_when_it_was_read():
    from app import ipo
    now = datetime(2026, 11, 18, 19, 0, tzinfo=timezone.utc)
    base = {"id": "in-x", "market": "IN", "name": "Crystal Crop Protection Ltd", "open": "2026-11-18", "close": "2026-11-20", "low": 100.0, "high": 110.0,
            "currency": "INR", "segment": "mainboard"}
    no_page = ipo.list_row(dict(base), now)
    assert no_page["stage"] == "open" and no_page["page"] is False and "page_at" not in no_page
    read = ipo.list_row({**base, "symbol": "CRYSTAL", "series": "EQ", "detail_at": "2026-11-18T18:45:00+00:00"}, now)
    assert read["page"] is True and read["page_at"] == "2026-11-18T18:45:00+00:00"
    listed = ipo.list_row({**base, "open": "2026-10-01", "close": "2026-10-03", "listing": "2026-10-08", "symbol": "X", "series": "EQ"}, now)
    assert "page" not in listed


def test_live14b_006_the_share_capital_count_the_latest_quarters_eps_agrees_with_beats_a_source_count_off_by_under_the_drift():
    """TCS on 18 Nov: the source's ₹8,48,791 cr at ₹2,380 is 356.6 crore shares; the capital (₹362 cr of ₹1 shares) and the Sep 2026
    quarter (13,934 ÷ 38.37) both say ~362, so ₹8.61 lakh cr. Wipro: the source's 990 crore agrees with its Sep 2026 capital (₹1,981 cr of
    ₹2) and quarter (3,200 ÷ 3.23 = 991) after the year's buyback: it stands (the 20-F's 1,048.8 crore is of 31 Mar 2026, before it)."""
    from app.intel.screener import market_cap, quarter_shares
    tcs = market_cap(848791.0, 2380.0, 362.0, 1.0, False, (363.56, 0.05), None, 363.15)
    assert round(tcs) == 861560
    wipro = market_cap(183289.0, 185.0, 1981.0, 2.0, False, (1023.45, 0.05), None, 990.71)
    assert wipro == 183289.0
    # without a quarter's EPS the rule is as before (the source stands within SHARES_DRIFT)
    assert market_cap(848791.0, 2380.0, 362.0, 1.0, False, (363.56, 0.05), None, None) == 848791.0
    # a quarter count far from the capital's (a large minority share in the profit) decides nothing
    assert market_cap(848791.0, 2380.0, 362.0, 1.0, False, None, None, 420.0) == 848791.0
    p = {"quarters": {"cols": ["Jun 2026", "Sep 2026"], "rows": {"Net Profit": [13420.0, 13934.0], "EPS in Rs": [36.9, 38.37]}}}
    assert round(quarter_shares(p), 1) == 363.1
    assert quarter_shares({"quarters": {"cols": ["Sep 2026"], "rows": {"Net Profit": [None], "EPS in Rs": [1.0]}}}) is None


def test_live14a_008_a_public_theme_tables_membership_and_revenue_cells_wrap_so_the_table_fits_its_card():
    """LIVE14A-008: on the public Automotive page at 1280 three layer tables were 876-900 px in 854 px cards ("industry-supported (official
    industry only)" and "₹1,13,662 crore FY26" kept on one line). Measured on this render at 1280: 871 px before, 854 after."""
    from app import public_themes as P
    rows = [{"symbol": f"S{i}", "name": f"Samvardhana Motherson International Ltd {i}", "page": None, "cap": "₹1.23 lakh cr", "cap_v": 1.0,
             "revenue": "₹1,13,662 crore", "year": "FY26", "evidence": "industry_code_supported" if i % 2 else "description_verified"} for i in range(4)]
    v = {"region": "IN", "label": "Automotive", "slug": "automotive", "name": "automotive", "members": 4, "all": 4,
         "evidence": {"description_verified": 2, "industry_code_supported": 2}, "older": False, "rechecking": False, "summary": "",
         "prices": None, "day": None, "indexable": True, "layers": [{"name": "Auto components", "companies": rows, "evidence": {}}]}
    html = P.render(v)
    assert '.cotbl td[data-label="Membership"]{white-space:normal;min-width:8em}' in html
    assert '.cotbl td[data-label="Revenue"]{white-space:normal}' in html
    assert 'data-label="Membership">industry-supported (official industry only)</td>' in html


def test_live14b_002_the_vix_tile_reads_a_few_weeks_of_closes_and_its_answer_is_shared_while_the_market_is_shut(monkeypatch):
    """LIVE14B-002: /trade/vix?brief=true took 2.05 s against 0.4-0.7 s for the other tiles at 00:35 IST (market shut): it read five years of
    stored closes and the exchange's index list for a value and a change. Now BRIEF_DAYS of closes, and one answer shared for everyone."""
    from datetime import date as _date
    from app import vix
    vix.forget()
    asked, quotes = [], []
    monkeypatch.setattr(vix, "daily", lambda since=None, today=None: asked.append(since) or [("2026-11-18", [15.5, 16.0, 15.2, 15.57])])
    monkeypatch.setattr(vix, "quote_now", lambda feed=None: quotes.append(1) or {"value": 15.57, "change": 0.05, "as_of": "2026-11-18T15:30:00+05:30"})
    monkeypatch.setattr(vix, "official_close", lambda day, fetch=False: 15.57)
    monkeypatch.setattr(vix, "_trading", lambda now: False)
    a = vix.brief_panel(None)
    b = vix.brief_panel(None)
    assert a == b and a["value"] == 15.57
    assert len(quotes) == 1                                                          # the second visit is answered from the kept copy
    since = _date.fromisoformat(asked[0])
    assert (_date.today() - since).days <= vix.BRIEF_DAYS + 1                        # weeks of closes, not five years
    vix.forget()


def test_live14b_014_the_usage_table_counts_the_journals_trades(monkeypatch):
    """LIVE14B-014: "Journal trades kept – –" for an account whose journal held 9 trades. The count is the journal's closed trades,
    practice aside, as its page counts them."""
    from app import journal as J
    from app import main as M
    monkeypatch.setattr(J, "load", lambda uid: {"updated_at": "x"})
    monkeypatch.setattr(J, "trades", lambda uid, data, today: {"trades": [{"src": "tradebook"}] * 9 + [{"src": "practice"}] * 2})
    assert M._journal_count("u-1") == 9


def test_live14a_019_a_us_call_row_with_no_name_takes_the_stored_pages_name(monkeypatch):
    from datetime import date
    from app import concalls, results
    monkeypatch.setattr(results, "between", lambda region, frm, to: [{"symbol": "AGTX", "date": "2026-11-18", "name": None, "when": None},
                                                                      {"symbol": "ZZZ", "date": "2026-11-18", "name": None, "when": None}])
    monkeypatch.setattr(results, "_snap", lambda region: {"AGTX": {"name": "Agentix Corp"}})
    rows = {r["symbol"]: r for r in concalls.us_rows(date(2026, 11, 16), date(2026, 11, 20))}
    assert rows["AGTX"]["name"] == "Agentix Corp" and rows["ZZZ"]["name"] == "ZZZ"


def test_live14a_020_a_briefs_scan_line_names_the_group_once():
    """LIVE14A-020: "2 stocks from the NIFTY 50 stocks newly matched…" in the Briefs list."""
    from app.newsletter import write as W
    assert W.group_words("NIFTY 50 stocks") == "NIFTY 50" and W.group_words("S&P 500") == "S&P 500"
    assert W.group_words("20 of the largest US companies") == "20 of the largest US companies"
    src = (__import__("pathlib").Path(W.__file__)).read_text()
    assert "from the {group_words(scan['group'])} newly matched" in src
