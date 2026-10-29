"""FIX-2: the findings of the live-site review LIVE-2 (data first)."""
from app import audit, stock_pages
from app.intel import screener
from app.intel.screener import checked_pe, market_cap, summary


def _page(eps_ttm, np_ttm, price, cap, own_pe=None, equity=100.0, face=10.0, balance_end="Mar 2026"):
    ratios = {"Current Price": str(price), "Market Cap": f"₹ {cap:,.0f} Cr.", "Face Value": f"₹ {face}"}
    if own_pe is not None:
        ratios["Stock P/E"] = str(own_pe)
    return {"ratios": ratios, "region": "IN",
            "pl": {"cols": ["Mar 2025", "Mar 2026", "TTM"], "rows": {"Net Profit": [10.0, 30.0, np_ttm], "EPS in Rs": [1.0, 3.0, eps_ttm]}},
            "balance": {"cols": ["Mar 2025", balance_end], "rows": {"Equity Capital": [equity, equity]}}}


# ---- LIVE2-025: a figure the audit flags is not published -----------------------------------------------------------
def test_pe_that_two_bases_disagree_on_is_not_shown_with_its_reason():
    """QUINT: price over EPS gives 21.3, market value over the 31 cr profit 9.3, the source has no P/E of its own."""
    p = _page(2.87, 31.0, 62.0, 293.0, equity=47.0)
    pe, why = checked_pe(p, 62.0, 293.0)
    assert pe is None and "21.6" in why and "9.5" in why
    s = summary(p)
    assert s["pe"] is None and s["pe_why"] == why


def test_the_sources_own_pe_settles_a_stale_eps_row():
    """BLUECLOUDS: the EPS row counts fewer shares than are in issue now (28.5), the source's own P/E (40.5) is market value over profit."""
    p = _page(0.65, 42.0, 18.5, 1704.0, own_pe=40.5)
    assert checked_pe(p, 18.5, 1704.0) == (40.5, None)


def test_a_minority_share_the_source_agrees_with_keeps_the_eps_pe():
    """RELIANCE-like: profit incl. minorities 88,167 vs the P/E on shareholders' profit; the source's own P/E is that same figure."""
    p = _page(48.0, 88167.0, 1000.0, 1589261.0, own_pe=21.3)
    pe, why = checked_pe(p, 1000.0, 1589261.0)
    assert why is None and pe == round(1000.0 / 48.0, 1)


def test_pe_that_agrees_or_has_no_trailing_profit_is_as_before():
    assert checked_pe(_page(3.0, 30.0, 45.0, 450.0), 45.0, 450.0) == (15.0, None)          # 450 / 30 = 15: one figure
    no_ttm = _page(3.0, 30.0, 45.0, 450.0)
    no_ttm["pl"] = {"cols": ["Mar 2025", "Mar 2026"], "rows": {"EPS in Rs": [1.0, 3.0], "Net Profit": [10.0, 30.0]}}
    assert checked_pe(no_ttm, 45.0, 99999.0) == (15.0, None)                          # no trailing column to set it against
    assert checked_pe(_page(-1.0, -5.0, 45.0, 450.0), 45.0, 450.0) == (None, None)        # a loss has no P/E and nothing to explain


def test_the_audit_and_the_page_hold_one_tolerance():
    assert audit.PE_TOLERANCE == screener.PE_AGREE and audit.PE_ROUNDING == screener.PE_ROUNDING


def test_a_share_listed_since_the_balance_sheet_takes_the_sources_share_count():
    """JPL and TONBO: share capital of Mar 2026 lacks the shares the issue added, so price x that count was 3-4% short."""
    src = 13_000_000.0
    p = _page(30.0, 3000.0, 1000.0, src, equity=0.971 * src / 1000.0 * 10, face=10.0)
    # the balance-sheet count is 2.9% under the source's: used (a buyback) unless the listing came after the balance sheet
    shares_eq = 0.971 * src / 1000.0 * 10          # equity crore giving 97.1% of the source's shares
    assert market_cap(src, 1000.0, shares_eq, 10.0) == round(1000.0 * shares_eq / 10, 2)
    assert market_cap(src, 1000.0, shares_eq, 10.0, issued_since=True) == src
    assert summary(p, "2026-07-01")["market_cap_cr"] == 13_000_000.0
    assert screener.balance_ends_before(p, "2026-07-01") and not screener.balance_ends_before(p, "2026-03-15")


def test_the_public_page_says_why_a_pe_is_missing():
    f = {"region": "IN", "symbol": "QUINT", "name": "Quint", "currency": "INR", "unit": "₹ crore", "market_cap_unit": "₹ crore",
         "price": 62.0, "market_cap": 293.0, "pe": None, "pe_why": "Price over earnings per share gives 21.6, market value over the last 12 months' net profit gives 9.5, and no third figure settles which is right",
         "profit_ttm": 31.0, "price_at": "2026-10-28", "years": [], "basis": "consolidated"}
    notes = " ".join(stock_pages._notes(f))
    assert "data-pe-why" in notes and "P/E isn't shown: price over earnings per share gives 21.6" in notes
    loss = {**f, "pe_why": None, "profit_ttm": -4.0}
    assert "data-pe-loss" in " ".join(stock_pages._notes(loss))


def test_negative_figures_use_the_true_minus_and_a_nonpayer_says_none():
    assert stock_pages._true_minus("-₹317 cr") == "−₹317 cr" and stock_pages._true_minus("-0.9%") == "−0.9%"
    assert stock_pages._true_minus("1-year range") == "1-year range"
    f = {"region": "US", "currency": "USD", "unit": "$ million", "market_cap_unit": "$ million", "price": 500.0, "market_cap": 1_000_000.0,
         "div_yield": 0.0, "price_at": "2026-10-28", "years": [], "profit_ttm": 100.0, "pe": 20.0}
    assert dict(stock_pages._stats(f))["Dividend yield"] == "none"
    # (an Indian P/E far from its market value over profit is left out, LIVE1C-019: the made-up figures agree, 2,000 over 100 is a P/E of 20)
    tiles = {t["label"]: t for t in stock_pages._tiles({**f, "region": "IN", "basis": "consolidated", "market_cap": 2000.0})}
    assert tiles["P/E"]["line"].endswith("consolidated")


# ---- O2: the margin-funding history (LIVE2: "All" reached only 19 Aug) -------------------------------------------------
import pytest
from datetime import date, datetime

from app import db, main  # noqa: F401,E402  (main first: it sets up the import order the desks rely on)
from app import exchange_days as X, mtf, stock_desks  # noqa: E402
from tests import world as W  # noqa: E402

REVISED = """,,,,,,Data Revised for reporting date 18-AUG-2026 to include late member submissions,,,
SEBI REPORT AS ON 18-AUG-2026,,,,,,,,,
,,As on Reporting Date 18-AUG-2026,,,,,,As on Current Date 20-AUG-2026 for reporting date 18-AUG-2026,
,Sr.No.,Particulars,Rs. In Lakhs ,,,,Sr.No.,Particulars,Rs. In Lakhs
,1,Scripwise Total Outstanding on the beginning of the day,0.00,,,,1,Scripwise Total Outstanding on the beginning of the day,14161539.77
,2,Fresh Exposure taken during the day,0.00,,,,2,Fresh Exposure taken during the day,444597.91
,3,Exposure liquidated during the day,0.00,,,,3,Exposure liquidated during the day,423644.73
,4,Net scripwise outstanding at the end of the day,0.00,,,,4,Net scripwise outstanding at the end of the day,14182492.95
,,,,,,,,,
Symbol,Name,Qty Fin by all the members(No.of Shares),Amt Fin by all the members(Rs. In Lakhs),,,Symbol,Name,Qty Fin by all the members(No.of Shares),Amt Fin by all the members(Rs. In Lakhs)
,,,,,,20MICRONS,20 MICRONS LTD,313213,624.35
 * Figures are rounded to the nearest decimal. ,,,,,,360ONE,360 ONE WAM LIMITED,565286,6483.54
,,,,,,3IINFOLTD,3I INFOTECH LIMITED,43970,11.09
"""


def test_a_revised_disclosure_is_read_from_its_current_figures():
    """18 Aug 2026's file holds two tables side by side; the first (as first reported) is zero. The back-fill stopped on it for good."""
    day, totals, rows = mtf.disclosure(REVISED)
    assert day == "2026-08-18"
    assert totals == {"start": 14161539.77, "fresh": 444597.91, "liquidated": 423644.73, "end": 14182492.95}
    assert rows == {"20MICRONS": [313213, 624.35], "360ONE": [565286, 6483.54], "3IINFOLTD": [43970, 11.09]}
    plain = "SEBI REPORT AS ON Reporting date 02-JAN-2025,,,\n,,,\nSr.No.,Particulars,Rs. In Lakhs ,\n1,Scripwise Total Outstanding on the beginning of the day,8306559.85,\n4,Net scripwise outstanding at the end of the day,8307796.85,\n\nSymbol,Name,Qty Fin by all the members(No.of Shares),Amt Fin by all the members(Rs. In Lakhs)\n20MICRONS,20 MICRONS LTD,500,1.65\n"
    d2, t2, r2 = mtf.disclosure(plain)
    assert d2 == "2025-01-02" and t2["end"] == 8307796.85 and r2 == {"20MICRONS": [500, 1.65]}


@pytest.fixture
def w(monkeypatch):
    world = W.build(monkeypatch)
    yield world
    world["close"]()
    X.clear_cache()


def test_the_walk_back_passes_a_day_it_cannot_read_twice_and_goes_on(w, monkeypatch):
    today = date(2026, 10, 1)
    bad = date(2026, 9, 25)
    real = mtf.DESK.read

    def read(files, day):
        if day == bad:
            raise ValueError("no stock lines")
        return real(files, day)
    monkeypatch.setattr(mtf.DESK, "read", read)
    seen = None
    for _ in range(8):
        seen = stock_desks.runner.backfill(mtf.DESK, today, step=6, days=20)
        if seen.get("done"):
            break
    assert seen.get("done") and seen["bad"] == {"2026-09-25": 2} and "2026-09-25" not in mtf.DESK.store.days()
    assert len(mtf.DESK.store.days()) >= 15


def test_the_long_history_reads_the_archive_back_and_keeps_totals_and_weekly_points(w, monkeypatch):
    monkeypatch.setattr(mtf, "DEEP_FROM", "2026-08-03")
    now = datetime(2026, 10, 2, 20, 0, tzinfo=X.IST)
    st = {}
    for _ in range(12):
        st = stock_desks.runner.deep(mtf.DESK, now.date(), now)
        if st.get("done"):
            break
    assert st.get("done") and not st.get("error")
    days = mtf.long_days()
    assert min(days) == "2026-08-03" and max(days) == "2026-09-30"
    assert all(len(v) == 4 and v[3] > 0 for v in days.values())
    weekly = mtf.weekly_series("RELIANCE")
    assert weekly and all(date.fromisoformat(d).weekday() < 5 for d, _, _ in weekly)
    assert all(mtf.week_end(date.fromisoformat(d)) for d, _, _ in weekly)
    assert len({date.fromisoformat(d).isocalendar()[:2] for d, _, _ in weekly}) == len(weekly)          # one a week
    # nothing more to read: a run writes nothing and reads nothing
    before = db.get_setting(mtf.DEEP_STATE)
    assert stock_desks.runner.deep(mtf.DESK, now.date(), now)["done"] and db.get_setting(mtf.DEEP_STATE) == before


def test_the_page_history_joins_the_long_history_to_the_daily_window(w, monkeypatch):
    monkeypatch.setattr(mtf, "DEEP_FROM", "2026-08-03")
    now = datetime(2026, 10, 2, 20, 0, tzinfo=X.IST)
    for _ in range(12):
        if stock_desks.runner.deep(mtf.DESK, now.date(), now).get("done"):
            break
    stock_desks.runner.catch_up(mtf.DESK, now)
    stock_desks.runner.backfill(mtf.DESK, now.date(), step=4, days=6)           # a short daily window: the rest is the long history's
    m = mtf.market(True)
    hist = [h["day"] for h in m["history"]]
    assert hist == sorted(set(hist)) and hist[0] == "2026-08-03" and hist[-1] == m["as_of"]
    one = mtf.for_symbol("RELIANCE", True, "all")
    days = [h["day"] for h in one["history"]]
    assert days == sorted(set(days)) and days[0] < mtf.DESK.store.series("RELIANCE")[0][0]       # weekly points before the daily ones
    assert mtf.for_symbol("RELIANCE", True, "3m")["history"][0]["day"] >= "2026-07-01"
    assert set(mtf.RANGES) >= {"3m", "6m", "1y", "3y", "5y", "all"}


# ---- O1: ETF price against NAV, five years -------------------------------------------------------------------------
from datetime import timedelta  # noqa: E402

from app import etf_nav as E, money_mf_nav  # noqa: E402
from tests import fake_etf as FE  # noqa: E402


@pytest.fixture
def ew(monkeypatch):
    world = W.build(monkeypatch)
    monkeypatch.setattr(E, "navs", lambda: FE.navs(date(2026, 10, 2)))
    yield world
    world["close"]()
    E.forget()


class _Feed:
    def etf_list(self):
        return FE.answer()

    def etf_securities(self):
        return FE.isins()


def test_the_oldest_day_rows_roll_into_the_long_series_and_nothing_is_lost(ew, monkeypatch):
    monkeypatch.setattr("app.data.calendar.is_trading_day", lambda region, d: d.weekday() < 5)
    today = date(2026, 10, 2)
    FE.seed_history(today, 80)
    E.refresh(_Feed())
    E.record_close(today, E.load_live(), FE.navs(today))              # 81 day rows: past ROLL_AT, so the oldest roll over
    rows = [k for k, _ in db.all_settings_with_prefix(E.DAY_KEY)]
    assert len(rows) == E.ROW_DAYS
    series = E.series_rows("SILVERBEES")
    assert len(series) == 81 - E.ROW_DAYS and series[0][0] < sorted(r[-10:] for r in rows)[0]
    h = E.long_history("SILVERBEES")
    assert len(h) == 81 and [x["day"] for x in h] == sorted({x["day"] for x in h})
    assert len(E.history("SILVERBEES")) == E.KEEP_DAYS                     # the list's 30-day column is as before
    assert E.detail("SILVERBEES")["history"][0]["day"] == h[0]["day"]


def test_the_back_fill_reads_five_years_once_per_etf_and_leaves_no_one_twice(ew, monkeypatch):
    today = date(2026, 10, 2)
    monkeypatch.setattr("app.data.calendar.is_trading_day", lambda region, d: d.weekday() < 5)
    E.refresh(_Feed())
    calls = {"nav": [], "px": []}
    first = date(2021, 11, 1)
    days = [first + timedelta(days=i) for i in range(0, 1800) if (first + timedelta(days=i)).weekday() < 5 and first + timedelta(days=i) < today]

    def nav_history(code, start, end):
        calls["nav"].append(code)
        return {d.isoformat(): 100.0 + i * 0.01 for i, d in enumerate(days)}

    def closes(sym):
        calls["px"].append(sym)
        return [{"t": f"{d.isoformat()}T00:00:00+05:30", "c": 100.0 + i * 0.01 + 0.5} for i, d in enumerate(days)]
    monkeypatch.setattr(E, "nav_history", nav_history)
    E.setup_history(closes)
    data = FE.navs(today)
    live = E.load_live()["rows"]
    with_nav = [s for s, r in live.items() if r.get("isin") and money_mf_nav.find(data, isin=r["isin"])]
    done = E.backfill_step(data, today, limit=3)           # BANKBEES (first) has no NAV scheme: a failure, the other two done
    assert done == 2 and len(calls["nav"]) == 2 and E.backfill_state()["fail"]["BANKBEES"][0] == 1
    sym = calls["px"][0]
    ser = E.series_rows(sym)
    assert len(ser) > 1000 and ser[0][0] >= "2021-10-01" and ser[-1][0] < today.isoformat() and all(c and n for _, c, n in ser)
    assert E.load_series(sym).get("bf") == 1
    # the rest, then a run that reads nothing more
    for _ in range(len(live)):
        E.backfill_step(data, today, limit=5)
    n_calls = len(calls["nav"])
    assert n_calls == len(with_nav) and sorted(E.backfill_state()["done"]) == sorted(with_nav)
    assert E.backfill_step(data, today) == 0 and len(calls["nav"]) == n_calls
    # an ETF whose NAV scheme isn't found is tried three times, then left alone for a week
    gone = [s for s in live if s not in with_nav]
    if gone:
        assert gone[0] in E.backfill_state()["fail"] and E.backfill_state()["fail"][gone[0]][0] >= 1
    h = E.long_history(sym)
    assert len(h) > 1000 and h[0]["gap"] is not None and abs(h[0]["gap"]) < 1.0


def test_the_back_fill_is_small_enough_to_keep(ew, monkeypatch):
    """About 1,250 trading days of close and NAV for one ETF is a few KB packed: 360 ETFs are a few MB."""
    first = date(2021, 11, 1)
    days = [first + timedelta(days=i) for i in range(1800) if (first + timedelta(days=i)).weekday() < 5]
    import random
    r = random.Random(3)
    c = n = 100.0
    rows = {}
    for d in days:
        n *= 1 + r.uniform(-0.01, 0.0105)
        c = n * (1 + r.uniform(-0.002, 0.002))
        rows[d.isoformat()] = (round(c, 2), round(n, 4))
    E.save_series("TESTETF", rows, backfilled=True)
    size = len(db.get_setting(E.SERIES_KEY + "TESTETF"))
    assert size < 16_000, size              # 360 ETFs x this = under 6 MB
    assert len(E.series_rows("TESTETF")) == len(days) and E.series_rows("TESTETF")[0] == (days[0].isoformat(), *rows[days[0].isoformat()])


# ---- O3: the participant history goes back five years --------------------------------------------------------------
from app import positioning as P  # noqa: E402


def test_a_walk_that_finished_at_a_year_goes_on_to_the_new_depth(w):
    r = P.Runner(lambda: main.filings_feed, sleep=lambda s: None, pace=0)
    today = date(2026, 10, 5)
    for _ in range(10):
        bf = r.backfill(today, step=5, days=30)
    assert bf["done"] and bf["target"] == 30
    n = len(P.history("part"))
    bf = r.backfill(today, step=5, days=60)                    # the target was raised: the walk reopens from its oldest day
    assert not bf["done"] and bf["target"] == 60 and len(P.history("part")) > n
    for _ in range(10):
        bf = r.backfill(today, step=5, days=60)
    assert bf["done"] and min(d for d, _ in P.history("part")) <= (today - timedelta(days=58)).isoformat()
    assert P.BACKFILL_DAYS >= 1800


# ---- O5, O6, LIVE2-029: the briefs as tables, as a PDF, and written again after a deploy -----------------------------
import io  # noqa: E402

from app.newsletter import job, pdf as news_pdf, tables as news_tables, write  # noqa: E402
from tests.fake_db import headers  # noqa: E402

OLD_ISSUE = {   # a brief as it was stored before tables: item texts only
    "id": "market.IN.2026-10-28", "kind": "market", "region": "IN", "day": "2026-10-28", "weekly": False, "subject": "Market Brief India, Wed 28 Oct: NIFTY 50 −0.22%",
    "summary": "NIFTY 50 −0.22%; SENSEX −0.20% today.", "at": "2026-10-28T16:00+05:30",
    "indices": [{"name": "NIFTY 50", "price": 22698.85, "change_pct": -0.22, "from_high_pct": -14.6}],
    "sections": [
        {"title": "Indices", "items": [{"text": "NIFTY 50: 22,698.85, −0.22% on the day"}, {"text": "SENSEX: 73,246.03, −0.20% on the day"}, {"text": "INDIA VIX: 11.20, +1.50% on the day"}]},
        {"title": "Sector rotation", "items": [{"text": "Nifty IT moved from Weakening to Leading on the rotation chart (weekly, against the NIFTY 500)", "url": "https://stratlab.studio/research/rotation?region=IN"}]},
        {"title": "Newly matched Stage 2 + Supertrend today (NIFTY 50)", "items": [
            {"text": "TCS matches the Stage 2 rule with the price above its Supertrend (ST S2)", "url": "https://stratlab.studio/research/IN/TCS"}]},
        {"title": "Newly in Stage 2, Supertrend not up (NIFTY 50)", "items": [
            {"text": "INFY moved into Stage 2 (matches the Stage 2 rule; its Supertrend isn't up)", "url": "https://stratlab.studio/research/IN/INFY"}]},
        {"title": "Headlines", "items": [{"text": "Sensex ends lower on profit taking", "url": "https://example.com/a", "source": "Example Wire"},
                                         {"text": "Rupee steady", "url": "https://example.com/b", "source": "Example Daily"}]},
    ]}


def test_a_brief_stored_before_tables_is_read_into_tables():
    tabs = {t["title"]: t for t in news_tables.of(OLD_ISSUE)}
    idx = tabs["Indices"]
    assert idx["head"] == ["Index", "Close", "Day %", "From 52-week high"] and idx["align"] == "lrrr"
    assert idx["rows"][0][:2] == ["NIFTY 50", "22,698.85"] and idx["rows"][0][2] == {"t": "▼ −0.22%", "tone": "down"} and idx["rows"][0][3] == "14.6% below"
    assert idx["rows"][2][2]["tone"] == "flat"                                   # a rise in the VIX is not good news: an arrow, no green
    rot = tabs["Sector rotation"]
    assert rot["head"] == ["Sector", "From → To"] and rot["rows"] == [["Nifty IT", "Weakening → Leading"]] and rot["link"]["href"].endswith("/research/rotation?region=IN")
    st = tabs["Newly matched Stage 2 + Supertrend today (NIFTY 50)"]
    assert st["head"] == ["Stock", "Stage", "Supertrend"]                          # a column none of the old rows can fill is left out, not left empty
    assert st["rows"][0] == [{"t": "TCS", "href": "https://stratlab.studio/research/IN/TCS"}, "Stage 2 (advancing)", "Up"]
    assert tabs["Newly in Stage 2, Supertrend not up (NIFTY 50)"]["rows"][0][2] == "Not up"
    hd = tabs["Headlines"]
    assert hd["head"] == ["Headline", "Source"] and hd["rows"][0][1] == {"t": "Example Wire", "href": "https://example.com/a", "ext": True}
    assert "ST S2" not in news_tables.plain(st["rows"][0][0]) and "ST S2" not in str(tabs)


def test_a_new_brief_carries_close_day_move_stage_supertrend_and_the_time_of_a_headline():
    issue = {**OLD_ISSUE, "sections": [
        {"title": "Newly matched Stage 2 + Supertrend today (NIFTY 50)", "items": [
            {"text": "TCS matches the Stage 2 rule with the price above its Supertrend (ST S2)", "url": "https://stratlab.studio/research/IN/TCS",
             "price": 2478.0, "change_pct": 0.73, "stage": 2, "stage_days": 3, "st_up": True, "st_since": "2026-10-27", "matched_on": "2026-10-27"}]},
        {"title": "Headlines", "items": [{"text": "Sensex ends lower", "url": "https://example.com/a", "source": "Example Wire", "at": "2026-10-28T10:05:00+05:30"}]}]}
    st, hd = news_tables.of(issue)
    assert st["head"] == ["Stock", "Close", "Day %", "Stage", "Supertrend", "Since"] and st["align"] == "lrrlll"
    assert st["rows"][0][1:] == ["₹2,478.00", {"t": "▲ +0.73%", "tone": "up"}, "Stage 2 (advancing), 3 days", "Up since Tue 27 Oct", "Tue 27 Oct"]
    assert hd["head"] == ["Time", "Headline", "Source"] and hd["rows"][0][0] == "10:05 IST"


def test_my_stocks_results_actions_and_paper_are_tables_and_prose_stays_prose():
    f = {"kind": "my_stocks", "uid": "u", "day": "2026-10-28", "weekly": False, "since": "2026-10-27",
         "stocks": [{"symbol": "TCS", "region": "IN", "price": 2478.0, "change_pct": 0.73, "filings": [{"label": "Results", "subject": "Q2", "severity": "info", "url": "https://example.com/f"}]}],
         "results": [{"symbol": "INFY", "region": "IN", "date": "2026-10-29", "purpose": "Quarterly results", "when": "after the close"}],
         "actions": [{"symbol": "ITC", "region": "IN", "text": "Dividend ₹7.50", "ex_date": "2026-11-05", "record_date": "2026-11-06"}],
         "unchanged": ["HDFCBANK", "SBIN"]}
    tabs = {t["title"]: t for t in news_tables.of({"region": None, "weekly": False, "sections": write.sections(f)})}
    ch = tabs["What changed for your stocks"]
    assert ch["head"] == ["Stock", "Close", "Change", "What changed"] and ch["rows"][0][1] == "₹2,478.00" and ch["rows"][0][2]["t"] == "▲ +0.73%"
    assert ch["rows"][0][3]["lines"][0]["t"].startswith("New filing: Results")
    assert tabs["Results this week"]["rows"][0][1:] == ["Quarterly results", "Thu 29 Oct", "after the close"]
    assert tabs["Corporate actions"]["rows"][0][1:] == ["Dividend ₹7.50", "Thu 5 Nov", "Fri 6 Nov"]
    assert tabs["No change"]["kind"] == "text"


def test_the_email_draws_the_tables_with_a_one_column_fallback_on_a_phone():
    html, text = write.render(OLD_ISSUE)
    assert "<th" not in html and html.count("hide-sm") >= 10 and "@media (max-width:480px)" in html and ".hide-sm{display:none!important" in html
    assert 'class="show-sm' in html and "Close 22,698.85 · Day % ▼ −0.22%" in html            # the phone's one line under the first cell
    assert ">NIFTY 50<" in html and ">TCS</a>" in html and ">Example Wire</a>" in html and ">Open the rotation chart</a>" in html
    assert "(ST S2)" not in html and "(ST S2)" not in text
    assert "INDICES\nIndex  Close  Day %  From 52-week high\n- NIFTY 50  22,698.85  ▼ −0.22%  14.6% below" in text
    assert "Headline  Source" in text and "Sensex ends lower on profit taking  Example Wire (https://example.com/a)" in text


def _pdf_text(data: bytes) -> str:
    from pypdf import PdfReader
    r = PdfReader(io.BytesIO(data))
    return "\n".join(p.extract_text() for p in r.pages)


def test_the_brief_pdf_has_the_tables_the_date_the_name_the_disclaimer_and_links():
    data = news_pdf.build(OLD_ISSUE)
    assert data[:5] == b"%PDF-"
    text = _pdf_text(data)
    for want in ("Market brief · India · Wed 28 Oct", "Prices and numbers as of", "NIFTY 50", "22,698.85", "▼ −0.22%", "Day %", "Close", "Index",
                 "Nifty IT", "Weakening → Leading", "Stage 2 (advancing)", "Example Wire", "Not investment advice", "StratLab", "Page 1"):
        assert want in text, want
    from pypdf import PdfReader
    links = {str(a.get_object().get("/A", {}).get("/URI")) for p in PdfReader(io.BytesIO(data)).pages for a in (p.get("/Annots") or [])}
    assert {"https://example.com/a", "https://example.com/b", "https://stratlab.studio/research/IN/TCS"} <= links          # headline sources stay clickable
    assert news_pdf.filename(OLD_ISSUE) == "stratlab-market-brief-india-2026-10-28.pdf"
    assert news_pdf.filename({"kind": "my_stocks", "day": "2026-10-28", "weekly": True}) == "stratlab-my-stocks-2026-10-28-weekly.pdf"


def test_the_pdf_route_is_open_to_whoever_can_read_the_brief(w):
    c = w["client"]
    c.get("/me", headers=headers("free-token"))
    job.save({**OLD_ISSUE, "html": "<p>{unsubscribe_url}</p>", "text": "x"})
    mine = {"id": "my_stocks.u-pro.2026-10-28", "kind": "my_stocks", "uid": "u-pro", "region": None, "day": "2026-10-28", "weekly": False,
            "subject": "My Stocks", "summary": "1 of your stocks had news.", "at": "2026-10-28T16:20", "html": "<p>x {unsubscribe_url}</p>", "text": "x",
            "sections": [{"title": "What changed for your stocks", "items": [{"text": "TCS", "url": "https://stratlab.studio/research/IN/TCS", "price": 2478.0, "currency": "INR", "region": "IN",
                                                                         "change_pct": 0.5, "since": "since Tue 27 Oct", "lines": []}]}]}
    job.save(mine)
    r = c.get("/news/market.IN.2026-10-28/pdf", headers=headers("free-token"))             # a market brief: every plan
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf" and "attachment" in r.headers["content-disposition"]
    assert "22,698.85" in _pdf_text(r.content) and "Index" in _pdf_text(r.content)
    assert r.headers["cache-control"] == "private, no-store"
    assert c.get("/news/my_stocks.u-pro.2026-10-28/pdf", headers=headers("free-token")).status_code == 404          # another reader's: not found
    mine_pdf = c.get("/news/my_stocks.u-pro.2026-10-28/pdf", headers=headers("pro-token"))
    assert mine_pdf.status_code == 200 and "Stock" in _pdf_text(mine_pdf.content) and "TCS" in _pdf_text(mine_pdf.content)
    assert c.get("/news/market.IN.2026-10-28/pdf").status_code in (401, 403)                                         # signed out: no
    assert c.get("/news/market.IN.1999-01-01/pdf", headers=headers("free-token")).status_code == 404
    page = c.get("/news/market.IN.2026-10-28", headers=headers("free-token")).json()
    assert [t["title"] for t in page["tables"]][:2] == ["Indices", "Sector rotation"]


def test_stored_brief_posts_are_written_again_once_after_a_change_to_how_they_are_written(w, monkeypatch):
    from app import blog
    old_post = blog.brief_post(OLD_ISSUE)
    old_post["blocks"] = [{"t": "ul", "items": ["TCS matches the Stage 2 rule (ST S2)"]}]            # as stored before the fix
    old_post.pop("gen")
    assert blog.add_once(old_post)
    assert "ST S2" in blog.plain_text(blog.get(old_post["slug"])["body"]["blocks"])
    out = blog.refresh_briefs([OLD_ISSUE])
    assert out == {"updated": 1, "added": 0, "same": 0}
    row = blog.get(old_post["slug"])
    assert row["body"]["gen"] == blog.BRIEF_GEN and "ST S2" not in blog.plain_text(row["body"]["blocks"])
    assert any(b["t"] == "table" and b["head"][:2] == ["Index", "Close"] for b in row["body"]["blocks"])
    assert row["published_at"] == old_post["published_at"] and row["published"] is True                 # its first date, and whether it was hidden
    assert blog.refresh_briefs([OLD_ISSUE]) == {"updated": 0, "added": 0, "same": 1}                      # once


def test_the_research_posts_are_written_again_at_the_first_check_after_a_deploy(w, monkeypatch):
    from app import blog_research
    runs = []
    monkeypatch.setattr(blog_research, "generate", lambda now=None, builders=None: runs.append(1) or {"made": [], "problems": []})
    now = datetime(2026, 10, 29, 12, 0, tzinfo=X.IST)
    assert blog_research.stale(now) and blog_research.run_if_stale(now) is not None and runs == [1]
    assert not blog_research.stale(now) and blog_research.run_if_stale(now) is None and runs == [1]        # once for a version
    monkeypatch.setattr(blog_research, "GEN", blog_research.GEN + 1)                                        # a deploy that changed the builders
    assert blog_research.stale(now) and blog_research.run_if_stale(now) is not None and runs == [1, 1]
    # a run that had problems is tried again an hour later, three times at most
    monkeypatch.setattr(blog_research, "generate", lambda now=None, builders=None: runs.append(1) or {"made": [], "problems": ["x"]})
    monkeypatch.setattr(blog_research, "GEN", blog_research.GEN + 1)
    blog_research.run_if_stale(now)
    assert not blog_research.stale(now + timedelta(minutes=30)) and blog_research.stale(now + timedelta(hours=2))


# ---- O7: the offer document read into tables by fixed rules ---------------------------------------------------------
def _sfc():
    from tests import fake_ipo as F
    return F.pages_of("sfc_rhp")


def test_the_objects_table_has_each_object_with_its_amount_from_the_document():
    from app import ipo_docs as D
    u = D.utilisation(_sfc())
    assert u["unit"] == "₹ crore" and u["page"] == 168
    amounts = {r["label"].split(" ")[0]: r["amount"] for r in u["rows"]}
    assert amounts["Prepayment"] == 42.23 and amounts["Funding"] == 74.92
    assert u["rows"][-1]["label"] == "General corporate purposes" and u["rows"][-1]["amount"] is None      # no amount given: none shown, none guessed


def test_the_risks_are_the_documents_own_numbered_headings_with_their_pages():
    from app import ipo_docs as D
    r = D.risk_headings(_sfc())
    assert [x["n"] for x in r[:3]] == [3, 4, 5] and r[0]["page"] == 31 and r[0]["text"].startswith("We derive a significant part of our revenue from our top 10 customers")
    assert all(x["page"] >= 30 and 40 <= len(x["text"]) <= 700 for x in r) and len(r) <= 12
    assert D.risk_headings([""] * 20) == []


def test_the_key_indicators_sit_beside_the_listed_peers_per_period():
    from app import ipo_docs as D
    k = D.kpis(_sfc())
    assert k["peers"] == ["Thermax", "Praj", "Ion"] and k["unit"] == "₹ crore"
    first = k["periods"][0]
    assert first["label"].startswith("the three months ending June 30, 2026")
    assert first["values"]["revenue"] == 133.94 and first["values"]["order_book"] == 1570.07
    assert first["peers"]["revenue"] == [2302.73, 715.82, 700.46] and first["peers"]["roe"] == [None, None, None]
    labels = [x["label"] for x in k["periods"]]
    assert len(labels) == len(set(labels)) and labels[2:] == ["Fiscal 2026", "Fiscal 2025", "Fiscal 2024"]      # a period the document gives in two tables is one
    f26 = k["periods"][2]
    assert f26["values"]["revenue"] == 803.63 and f26["values"]["roe"] == 21.55 and f26["peers"]["roe"] == [13.7, 1.77, 11.2]
    assert D.kpis([""] * 5) is None


def test_the_holders_before_the_offer_keep_their_groups_and_sub_totals():
    from app import ipo_docs as D
    h = D.shareholding(_sfc())
    rows = h["rows"]
    promoters = [r for r in rows if r["group"] == "Promoters" and not r["total"]]
    assert [r["name"] for r in promoters][0] == "Sandeep Sudhakar Asolkar" and promoters[0]["shares"] == 13_500_000 and promoters[0]["pct"] == 14.45
    sub = next(r for r in rows if r["name"] == "Sub-total (A)")
    assert sub["total"] and sub["shares"] == 40_019_595 and sub["pct"] == 42.84
    assert sum(r["shares"] for r in promoters) == sub["shares"]                                        # the rows add to the document's own sub-total
    assert rows[-1]["name"].startswith("Sub-total") and any(r["name"] == "Public shareholders" for r in rows)


def test_the_peer_ratios_and_the_earnings_per_share_are_read_from_their_tables():
    from app import ipo_docs as D
    p = D.peer_table(_sfc())
    assert p["price_on"] == "October 16, 2026" and p["company"]["eps"] == 16.52 and p["company"]["revenue"] == 803.63
    assert [x["name"] for x in p["peers"]] == ["Thermax Limited", "Praj Industries Limited", "Ion Exchange (India) Limited"]
    assert p["peers"][0]["pe"] == 52.01 and p["peers"][1]["pe"] == 220.77
    e = D.eps_rows(_sfc())
    assert [r["period"] for r in e["rows"][:3]] == ["March 31, 2026", "March 31, 2025", "March 31, 2024"] and e["rows"][0]["basic"] == 16.52
    assert e["rows"][-1]["basic"] == -0.14 and D.peer_table([""] * 4) is None and D.eps_rows([""] * 4) is None


def test_the_issue_size_counts_the_whole_issue_and_says_what_the_bid_table_covers():
    from app import ipo as I
    got = I.sizes({"market": "IN", "fresh": 17_000_000, "ofs": 0, "size_shares": 14_000_000, "high": 150.0})
    assert got["amount"] == 255.0 and got["in_bids"] == 210.0                                           # (LIVE2-022) ₹255 cr, of which ₹210 cr is in the bid table
    assert I.sizes({"market": "IN", "total_cr": 300.0}) == {"amount": 300.0, "basis": "stated"}


def test_a_read_document_gives_every_table_to_the_page(monkeypatch):
    from app import ipo_docs as D, ipo as I
    assert D.READER >= 2 and D.SUMMARY_READER >= 2                       # raised: documents read before are read again for the new tables
    keys = ("utilisation", "risks", "kpis", "holding", "peers", "eps")
    stored = {"kind": "RHP", "promoters": ["A"], "pages_read": 3, "excerpt": "words", "reader": D.READER, **{k: {"page": 1} for k in keys}}
    monkeypatch.setattr(I, "doc_to_read", lambda row: {"kind": "RHP", "url": "u", "source": "nse"})
    monkeypatch.setattr(I, "facts_of", lambda d: stored)
    got = I.facts_view({"market": "IN", "id": "x"})
    assert got["state"] == "ready" and all(got[k] == {"page": 1} for k in keys) and "excerpt" not in got


def test_the_refund_and_credit_day_is_the_timetables_t_plus_2_while_it_is_ahead():
    from datetime import datetime
    from app import ipo as I
    now = datetime.fromisoformat("2026-10-28T12:00:00+05:30")
    row = {"market": "IN", "id": "x", "name": "X", "stage": "open", "open": "2026-10-26", "close": "2026-10-28"}
    pub = I.public(row, now)
    assert pub["allotment"] == "2026-10-29" and pub["credit"] == "2026-10-30" and pub["credit_expected"] and pub["listing"] == "2026-11-02"
    old = I.public({**row, "close": "2026-10-20", "open": "2026-10-16"}, now)
    assert "credit" not in old                                       # a day that has passed is not given from the timetable: it may have moved
    assert "credit" not in I.public({"market": "US", "id": "u", "name": "U", "stage": "upcoming"}, now)


# ---- LIVE2-001: a company under the wrong market is offered under the right one; NYSE:/NASDAQ: prefixes work --------------------------------
def test_a_symbol_under_the_wrong_market_names_the_right_one_and_exchange_prefixes_resolve(monkeypatch):
    from tests import world
    w = world.build(monkeypatch)
    try:
        c = w["client"]
        r = c.get("/stocks/in/AAPL")
        assert r.status_code == 404 and "is listed in the US" in r.text and 'href="/stocks/us/AAPL"' in r.text and 'value="AAPL"' in r.text
        r = c.get("/stocks/us/RELIANCE")
        assert r.status_code == 404 and "is listed in India" in r.text and 'href="/stocks/in/RELIANCE"' in r.text
        assert "is listed in" not in c.get("/stocks/in/ZZZZNOPE").text                                # no company anywhere: nothing offered
        for u in ("/stocks/us/NASDAQ:AAPL", "/stocks/us/NYSE%3AAAPL", "/stocks/us/nasdaq:aapl"):
            r = c.get(u, follow_redirects=False)
            assert r.status_code == 301 and r.headers["location"] == "/stocks/us/AAPL", (u, r.status_code)
        s = c.get("/stocks?q=AAPL&m=in")
        assert "is listed in the US" in s.text and "/stocks/us/AAPL" in s.text
        from app import name_search
        assert name_search._listing_affix.sub("", "NYSE:JPM") == "JPM" and name_search._listing_affix.sub("", "NSE:TCS") == "TCS"
    finally:
        w["close"]()


def test_a_description_is_cut_at_a_word_to_what_a_search_result_shows():
    from app import stock_pages as sp
    long = "Tata Consultancy Services share price, results, margins, debt and filings from reported data. " * 3
    cut = sp.clamp_desc(long)
    assert len(cut) <= sp.DESC_MAX and cut.endswith("…") and " …" not in cut
    assert sp.clamp_desc("Short one.") == "Short one."
    page = sp._head("T", long, "https://x.test/")
    assert f'content="{cut}"' in page and long.strip() not in page


def test_the_a_to_z_with_its_zero_to_nine_pill_is_two_rows_and_the_pill_keeps_one_line():
    from app import stock_pages as sp
    assert 'data-cd="13"' in sp._az_style(26) and 'data-cd="14"' in sp._az_style(27) and 'data-cd="13"' in sp._az_style(7)      # (LIVE2-019)
    src = open(sp.__file__, encoding="utf8").read()
    assert 'nav.links[data-cd="14"]{--azd:14}' in src and "repeat(var(--azd,13),44px)" in src and "white-space:nowrap;padding:4px 6px" in src


def test_a_year_of_stock_series_does_not_keep_a_year_of_whole_day_records(w):
    from app import db, exchange_days as X
    store = X.DayStore("zz1:", 20, lambda row: [row["px"]], shards=2, rows_keep=5)
    days = [(date(2026, 9, 1) + timedelta(days=i)).isoformat() for i in range(30)]
    store.put_many([(d, {"AAA": {"px": 10.0 + i}}, {}) for i, d in enumerate(days[:12])])          # an older stretch first (the archive walk)
    store.put_many([(d, {"AAA": {"px": 20.0 + i}}, {}) for i, d in enumerate(days[12:])])
    kept = store.days()
    assert len(kept) == 20 and kept[-1] == days[-1]                                            # the series go back `keep` days
    assert len(store.series("AAA")) == 20
    assert [d for d in kept if store.get(d)] == kept[-5:]                                      # whole records only for the newest five
    assert store.latest()[0] == days[-1] and store.latest(before=days[-1])[0] == days[-2]
    assert db.get_setting(f"zz1:d:{days[0]}") is None
    old = X.DayStore("zz2:", 20, lambda row: [row["px"]], shards=2)                            # a store that kept every record (before the change)...
    old.put_many([(d, {"AAA": {"px": 1.0}}, {}) for d in days[10:]])
    assert all(old.get(d) for d in old.days())
    new = X.DayStore("zz2:", 20, lambda row: [row["px"]], shards=2, rows_keep=5)               # ...drops the old ones at its next write
    new.put_many([(days[-1], {"AAA": {"px": 2.0}}, {})])
    assert [d for d in new.days() if new.get(d)] == new.days()[-5:]
    from app import stock_futures
    assert stock_futures.DESK.store.rows_keep == stock_futures.ROWS_KEEP < stock_futures.KEEP and stock_futures.DESK.backfill_days == stock_futures.KEEP


def test_indian_company_names_are_one_style():
    from app.stock_pages import tidy_in_name as t
    assert t("National Stock Exchange Of India Ltd") == "National Stock Exchange of India Ltd"
    assert t("TATA CONSUMER PRODUCTS LIMITED") == "Tata Consumer Products Limited"
    assert t("HDFC BANK LIMITED") == "HDFC Bank Limited" and t("ONGC LIMITED") == "ONGC Limited" and t("LARSEN & TOUBRO LIMITED") == "Larsen & Toubro Limited"
    assert t("Tata Communications Limited") == "Tata Communications Limited" and t("ITC Ltd") == "ITC Ltd" and t(None) is None
    assert t("Bank of Baroda") == "Bank of Baroda" and t("OF INDIA FUND") == "Of India Fund"                 # the first word keeps its capital


# ---- O7: the same tables from the other documents' layouts (live red herring prospectuses read on 29 Oct, the key pages kept) ------------------
def _variant(name: str) -> list[str]:
    import gzip
    import json as _json
    from tests import fake_ipo as F
    got = _json.load(gzip.open(F.DIR / "rhp_variants_pages.json.gz", "rt", encoding="utf8"))[name]
    out = [""] * got["count"]
    for i, t in got["pages"].items():
        out[int(i)] = t
    return out


def test_the_summary_financials_are_read_whatever_the_header_and_the_unit_say():
    from app import ipo_docs as D
    cases = {"BLSPOLY": ("lakhs, 4 columns", [349.43, 328.44, 296.36], [27.01, 21.14, 7.52]),
             "BCSSL": ("million, a restated heading", [1266.82, 1055.71, 755.26], [30.54, 28.67, 21.14]),
             "JPL": ("million, bare fiscal years", [146885.3, 128218.4, 109558.1], [30052.7, 26120.3, 21434.0]),
             "PARASHLTH": ("day-first dates, losses", [1605.95, 1294.06, 1129.04], [43.83, -57.98, -15.33]),
             "TONBO": ("one date and two bare years", [362.65, 469.08, 428.19], [50.88, 72.76, 68.54])}
    for name, (_, revenue, profit) in cases.items():
        f = D.financials(_variant(name))
        by = {r["key"]: r["values"] for r in f["rows"]}
        assert f["years"] == ["Mar 2026", "Mar 2025", "Mar 2024"], name
        assert by["revenue"] == revenue and by["profit"] == profit, (name, by)             # the profit is the profit line, not the revenue the heading ran into


def test_the_objects_table_is_found_under_either_heading_and_ends_at_the_net_proceeds():
    from app import ipo_docs as D
    u = D.utilisation(_variant("PARASHLTH"))
    assert [r["amount"] for r in u["rows"]] == [320.9, 54.1, None]
    assert u["rows"][0]["label"].startswith("Prepayment or scheduled re-payment") and u["rows"][1]["label"].startswith("Investment in our wholly owned Subsidiary")
    assert u["rows"][2]["label"] == "General corporate purposes"
    b = D.utilisation(_variant("BCSSL"))
    assert [r["amount"] for r in b["rows"]] == [125.0, 15.77, None] and b["rows"][-1]["label"] == "General corporate purposes"       # no "Sr. No." or note mark left on a label
    assert [r["amount"] for r in D.utilisation(_variant("BLSPOLY"))["rows"]] == [77.56, 89.5, None]


def test_the_peer_table_columns_are_found_from_its_own_header():
    from app import ipo_docs as D
    t = D.peer_table(_variant("BCSSL"))
    assert t["price_on"] == "October 21, 2026" and t["company"] == {"revenue": 1266.82, "eps": 7.64, "nav": 30.41, "ronw": 25.12}
    assert [(x["name"], x["price"], x["pe"], x["ronw"]) for x in t["peers"]][0] == ("BMW Industries Limited", 51.17, 14.98, 10.15)
    t = D.peer_table(_variant("TONBO"))                          # another order of columns, a basis column, "NA" where the document has none
    assert t["company"]["eps"] == 9.19 and t["company"]["ronw"] == 9.75 and t["company"]["nav"] == 96.57
    assert t["peers"][0]["name"] == "Paras Defence and Space Technologies Limited" and t["peers"][0]["pe"] == 117.74 and t["peers"][0]["ronw"] is None
    assert t["peers"][1]["ronw"] == 17.0 and t["peers"][1]["revenue"] == 924.77
    assert D.peer_table(_variant("JPL")) is None                 # a document with no such table gives nothing, not a guess


def test_the_issue_page_carries_the_refund_day_and_the_bid_table_note(monkeypatch):
    from tests import world, fake_ipo
    from tests.fake_db import headers
    w = world.build(monkeypatch)
    try:
        fake_ipo.seed()
        c = w["client"]
        d = c.get("/invest/ipos/in-mksons", headers=headers("free-token")).json()["ipo"]
        assert d["credit_expected"] and d["credit"] > d["allotment"] and d["credit"] < d["listing"]
        b = c.get("/invest/ipos/in-blspoly", headers=headers("free-token")).json()["ipo"]
        assert b["size"] == 255.0 and b["size_in_bids"] == 178.5 and b["anchor_shares"] == 5_100_000
    finally:
        w["close"]()
