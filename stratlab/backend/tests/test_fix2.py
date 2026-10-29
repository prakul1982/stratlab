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
