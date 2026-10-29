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
    tiles = {t["label"]: t for t in stock_pages._tiles({**f, "region": "IN", "basis": "consolidated"})}
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
