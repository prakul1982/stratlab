"""Round 5 visitor review, the public company pages: one price rule (the last close, dated) and a cache that follows the
market's close; margins named for what they are; missing figures shown as n/a; mixed currencies and extreme margins
said out loud; peers ranked by size; market caps in words; the site's own header and footer; and a helpful answer for
funds, indices, share classes, /stocks and a trailing slash."""
import json
import re
from datetime import datetime, timedelta, timezone

import pytest

from app import company_cards, db, main, screens, stock_pages
from tests import world

IST = timezone(timedelta(hours=5, minutes=30))


@pytest.fixture
def w(monkeypatch):
    built = world.build(monkeypatch)
    yield built
    built["close"]()


def _bars(last_day: str, n: int = 30) -> list[dict]:
    end = datetime.fromisoformat(last_day)
    return [{"t": (end - timedelta(days=n - 1 - i)).date().isoformat() + "T00:00:00+05:30", "o": 100 + i, "h": 101 + i,
             "l": 99 + i, "c": 100.5 + i} for i in range(n)]


def _facts(**kw) -> dict:
    base = {"region": "IN", "symbol": "ACME", "name": "Acme Ltd", "exchange": "NSE", "industry": ["Industrials"],
            "currency": "INR", "unit": "₹ crore", "price": 100.0, "price_at": "2026-10-07", "high52": 120.0, "low52": 80.0,
            "market_cap": 770345.0, "pe": 14.3, "roe": 12.0, "opm": 28.0, "net_margin": 19.4, "debt_equity": 0.1,
            "div_yield": 1.1, "years": [{"year": f"Mar 202{i}", "sales": 100.0 + i, "profit": 20.0, "opm": 26.0 + i % 2, "debt": 1.0}
                                        for i in range(2, 7)],
            "growth": {"sales_cagr_3y": 6.4, "profit_cagr_3y": 1.0}, "filings": [], "built_at": "2026-10-08T05:00:00+00:00"}
    return {**base, **kw}


# ---------- R5V-005: the last close, dated, and a cache that follows the close ----------
def test_a_session_still_trading_is_not_a_close():
    bars = _bars("2026-10-08")                                       # a Thursday: 8 Oct's candle is the live session
    during = datetime(2026, 10, 8, 14, 0, tzinfo=IST)
    got = stock_pages.price_facts(bars, "IN", during)
    assert got["price_at"] == "2026-10-07" and got["price"] == bars[-2]["c"] and got["price_basis"] == "close"
    just_shut = datetime(2026, 10, 8, 16, 0, tzinfo=IST)             # closed, but not yet settled
    assert stock_pages.price_facts(bars, "IN", just_shut)["price_at"] == "2026-10-07"
    # India's official close reaches the daily candles hours after the bell (R6V-002: a last trade was shown as the
    # close for an evening), so the day counts as closed only from 18:30 India time
    assert stock_pages.price_facts(bars, "IN", datetime(2026, 10, 8, 16, 20, tzinfo=IST))["price_at"] == "2026-10-07"
    after = datetime(2026, 10, 8, 18, 31, tzinfo=IST)
    assert stock_pages.price_facts(bars, "IN", after)["price_at"] == "2026-10-08"
    # New York: at 14:00 India time on 8 Oct the US session of 7 Oct closed hours ago (it was a session behind before)
    us = _bars("2026-10-07")
    assert stock_pages.price_facts(us, "US", during)["price_at"] == "2026-10-07"
    assert stock_pages.last_close("US", datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc))[0].isoformat() == "2026-10-09"   # a Saturday


def test_a_stored_page_is_rebuilt_once_its_market_closes_again():
    close = stock_pages.last_close("IN")[1].timestamp() + stock_pages.settle("IN")
    # pages of the current facts version: a page of an older one is rebuilt in either market whatever its time (R8O-001),
    # which isn't what this test is about
    built_after = {"ts": close + 60, "facts": {"price": 1, "v": stock_pages.FACTS_VERSION}}
    built_before = {"ts": close - 60, "facts": {"price": 1, "v": stock_pages.FACTS_VERSION}}
    assert stock_pages.fresh(built_after, "IN", now=close + 120) and not stock_pages.fresh(built_before, "IN", now=close + 120)
    assert not stock_pages.fresh({"ts": close + 60 - stock_pages.FRESH - 10, "facts": {"price": 1}}, "IN", now=close + 70)
    assert stock_pages.fresh({"ts": close - 60, "facts": None}, "IN", now=close + 120)   # nothing at the source: asked again
    assert not stock_pages.fresh({"ts": close - 60, "facts": None}, "IN", now=close + stock_pages.EMPTY_FOR)  # ...hours later


def test_the_page_says_last_close_and_the_cache_is_minutes_not_a_day(w):
    r = w["client"].get("/stocks/in/RELIANCE")
    cc = r.headers["cache-control"]
    assert int(re.search(r"s-maxage=(\d+)", cc).group(1)) <= 900 and int(re.search(r"max-age=(\d+)", cc).group(1)) <= 300
    assert int(re.search(r"stale-while-revalidate=(\d+)", cc).group(1)) <= 3600
    t = r.text
    assert "Last price" not in t and re.search(r"As of \d{1,2} \w{3} 20\d\d close", t) and re.search(r"Last close, \d{1,2} \w{3}", t)


def test_a_us_page_prices_its_ratios_at_the_close_it_shows(w):
    main.stock_page_store.mem.clear()
    co = stock_pages.find("US", "AAPL")[1]
    f = main.stock_page_facts("US", co)
    assert f["price_basis"] == "close" and f["price_at"]
    # P/E reconciles: market cap over the last twelve months' profit, both on the page
    assert f["pe"] == pytest.approx(f["market_cap"] / f["profit_ttm"], rel=0.01)
    assert f["div_yield"] is None or f["div_yield"] >= 0


def test_dividend_yield_from_the_years_dividends():
    divs = [{"date": "2026-03-01", "amount": 0.5}, {"date": "2025-12-01", "amount": 0.5}, {"date": "2025-06-01", "amount": 9.0}]
    assert stock_pages.dividend_yield(divs, 50, "2026-10-07") == 2.0          # the year to 7 Oct: two of them
    assert stock_pages.dividend_yield([], 50, "2026-10-07") == 0.0            # a history with none: a real 0
    assert stock_pages.dividend_yield(divs, None, "2026-10-07") is None


# ---------- R5V-004 and R5V-008: names, n/a, currency, extreme margins, wording ----------
def test_margins_are_called_ebitda_margin_and_whole_percent_shows_no_point_zero(w):
    page = stock_pages.render(_facts(), "IN", "ACME", None)
    assert "Operating margin" not in page and "EBITDA margin" in page
    assert "<b>28%</b>" in page and "28.0%" not in page and "<td>26%</td>" in page and "26.0%" not in page
    us = stock_pages.render(_facts(region="US", currency="USD", unit="$ million", opm=34.8), "US", "ACME", None)
    assert "34.8%" in us


def test_unknown_figures_are_na_never_zero(w):
    page = stock_pages.render(_facts(div_yield=None, pe=None), "IN", "ACME", None)
    assert "<span>Dividend yield</span><b>n/a</b>" in page and "<span>P/E</span><b>n/a</b>" in page
    assert "0.00%" not in page


def test_a_foreign_filer_says_which_currency_is_which(w):
    page = stock_pages.render(_facts(region="US", currency="USD", unit="EUR million", market_cap=85828.0), "US", "E", None)
    assert "data-currency-note" in page and "US dollars" in page and "EUR million" in page
    assert "data-currency-note" not in stock_pages.render(_facts(region="US", currency="USD", unit="$ million"), "US", "AAPL", None)


def test_extreme_margins_carry_a_caveat(w):
    tiny = _facts(opm=-1094.0, net_margin=-433.3, years=[{"year": "Mar 2026", "sales": 1.0, "profit": 26.0, "opm": -1300.0, "debt": 0}])
    assert "data-extreme" in stock_pages.render(tiny, "IN", "STLSTRINF", None)
    assert "data-extreme" not in stock_pages.render(_facts(), "IN", "ACME", None)


def test_growth_reads_grew_or_fell():
    assert stock_pages.growth_words("revenue", -14.7) == "revenue fell 14.7% a year"
    assert stock_pages.growth_words("revenue", 6.44) == "revenue grew 6.4% a year"
    assert stock_pages.growth_words("revenue", 0.0) == "revenue was flat"
    assert stock_pages.growth_words("revenue", None) is None


def test_a_sector_string_says_each_part_once(w):
    f = stock_pages.facts("IN", "TCS", {"name": "TCS", "industry_path": ["Information Technology", "Information Technology",
                                                                         "IT - Software", "Computers - Software & Consulting"]},
                          {"years": []}, {}, None, None, [], "NSE")
    assert f["industry"] == ["Information Technology", "IT - Software", "Computers - Software & Consulting"]
    page = stock_pages.render({**f, "industry": ["Information Technology", "Information Technology", "IT - Software"]}, "IN", "TCS", None)
    assert "Information Technology · Information Technology" not in page and "Information Technology · IT - Software" in page


def test_pe_is_the_price_over_the_pages_own_trailing_eps():
    from app.intel.screener import summary
    page = {"ratios": {"Stock P/E": "14.0", "Current Price": "₹ 2,075"},       # TCS, 8 Oct 2026: the source's 14.0 didn't reconcile
            "pl": {"cols": ["Mar 2025", "Mar 2026", "TTM"], "rows": {"Sales": [255324, 267021, 275859],
                                                                     "Net Profit": [48797, 49454, 50055], "EPS in Rs": [134.2, 136.01, 137.64]}}}
    assert summary(page)["pe"] == 15.1                                         # 2,075 / 137.64
    no_ttm = {**page, "pl": {"cols": ["Mar 2025", "Mar 2026"], "rows": {"Net Profit": [1, 2], "EPS in Rs": [134.2, 136.01]}}}
    assert summary(no_ttm)["pe"] == 15.3                                       # the latest year's
    loss = {**page, "pl": {"cols": ["Mar 2026", "TTM"], "rows": {"Net Profit": [-5, -4], "EPS in Rs": [-1.0, -0.8]}}}
    assert summary(loss)["pe"] is None
    assert summary({**page, "pl": {"cols": [], "rows": {}}})["pe"] == 14.0   # no EPS row: the source's own
    assert summary({**page, "region": "US"})["pe"] == 14.0                     # US ratios come from the filings as worked out


def test_the_page_explains_how_pe_is_worked_out(w):
    page = stock_pages.render(_facts(profit_ttm=49454.0), "IN", "ACME", None)
    assert "How these figures are worked out" in page and "earnings per share over the last four reported quarters" in page
    assert "Net profit, last 12 months" in page


# ---------- R5V-009: peers by size, full names, no alphabetical neighbours ----------
def test_peers_are_the_largest_in_the_industry_with_full_names(w):
    rows = [{"symbol": s, "name": n, "sector": "Information Technology", "industry": ind, "market_cap": cap}
            for s, n, ind, cap in (("INFY", "Infosys Limited", "Computers - Software & Consulting", 650000),
                                   ("WIPRO", "Wipro Limited", "Computers - Software & Consulting", 260000),
                                   ("HCLTECH", "HCL Technologies Limited", "Computers - Software & Consulting", 420000),
                                   ("TCS", "Tata Consultancy Services Limited", "Computers - Software & Consulting", 770000),
                                   ("TATAELXSI", "Tata Elxsi Limited", "IT Enabled Services", 40000))]
    db.set_setting(screens.INDEX_KEY + "IN", json.dumps({"at": "2026-10-08", "rows": rows}))
    screens._mem.clear()
    got, ranked = stock_pages.peers("IN", "TCS", ["Information Technology", "IT - Software", "Computers - Software & Consulting"])
    assert ranked and [s for s, _ in got][:3] == ["INFY", "HCLTECH", "WIPRO"]       # the industry, largest first
    assert ("HCLTECH", "HCL Technologies Limited") in got
    page = stock_pages.render(_facts(industry=["Information Technology", "Computers - Software & Consulting"]), "IN", "TCS", None)
    assert "Other companies" not in page and "Infosys Limited (INFY)" in page and "by market value" in page


# ---------- R5V-023: the site's header, footer and units ----------
def test_market_caps_read_in_words():
    assert stock_pages.cap_text({"currency": "USD", "market_cap": 4869056}) == "$4.87T"
    assert stock_pages.cap_text({"currency": "USD", "market_cap": 85828}) == "$85.8B"
    assert stock_pages.cap_text({"currency": "USD", "market_cap": 950}) == "$950M"
    assert stock_pages.cap_text({"currency": "INR", "market_cap": 770345}) == "₹7.70 lakh crore"
    assert stock_pages.cap_text({"currency": "INR", "market_cap": 20345}) == "₹20,345 crore"
    assert stock_pages.cap_text({"currency": "INR", "market_cap": None}) == "–"


def test_the_page_wears_the_sites_header_and_footer(w):
    r = w["client"].get("/stocks/in/RELIANCE")
    t = r.text
    csp = r.headers["content-security-policy"]                  # the site's fonts may load; still no script at all
    assert "font-src 'self'" in csp and "default-src 'none'" in csp and "script-src" not in csp
    for part in ('href="https://stratlab.studio/research/IN/RELIANCE">Sign in</a>', ">Contact us</a>", ">Cancellation and refunds</a>",
                 ">Terms of service</a>", ">Privacy policy</a>", 'href="https://stratlab.studio/pricing"', 'href="/stocks">Companies</a>',
                 "url(/fonts/fraunces-latin-400-normal.woff2)", "<span>Market cap</span><b>₹", " lakh crore</b>", 'id="main"'):
        assert part in t, part
    assert "Market cap (" not in t and "Sign up free" not in t
    # the table opens on the newest years on a phone, with a cue that there are earlier ones
    assert ".tbl{overflow-x:auto;direction:rtl}" in t and "scroll-cue" in t
    # dark mode: the button's text is the page's own on-ink colour, not white on a light green
    assert "#7CC4A6" not in t


def test_a_company_card_uses_the_same_words(w):
    c = company_cards.card(_facts(industry=["Energy", "Energy", "Refineries"], pe=None, roe=None, growth={}), "IN", "ACME")
    labels = dict(c["facts"])
    assert labels["Market cap"] == "₹7.70 lakh crore" and labels["EBITDA margin"] == "28%" and "Operating margin" not in labels
    assert c["sector"] == "Energy · Refineries"


# ---------- R5V-013: funds, indices, share classes, /stocks and a trailing slash ----------
def test_funds_and_indices_get_a_page_that_says_what_they_are(w):
    c = w["client"]
    for u, what, app in (("/stocks/in/NIFTYBEES", "an exchange-traded fund", "/research/IN/NIFTYBEES"),
                         ("/stocks/us/SPY", "an exchange-traded fund", "/research/US/SPY"),
                         ("/stocks/in/NIFTY", "an index", "/research/IN/NIFTY")):
        r = c.get(u)
        assert r.status_code == 404 and "noindex" in r.text, u
        assert what in r.text and app in r.text and "Company not found" not in r.text, u
    r = c.get("/stocks/in/ZZZZNOPE")
    assert r.status_code == 404 and 'action="/stocks"' in r.text and "No company page for ZZZZNOPE" in r.text


def test_share_classes_either_way_and_a_trailing_slash_redirect(w):
    c = w["client"]
    for u in ("/stocks/us/BRK.B", "/stocks/us/brk-b", "/stocks/us/BRK-B/"):
        r = c.get(u, follow_redirects=False)
        assert r.status_code == 301 and r.headers["location"] == "/stocks/us/BRK-B", u
    r = c.get("/stocks/in/RELIANCE/", follow_redirects=False)
    assert r.status_code == 301 and r.headers["location"] == "/stocks/in/RELIANCE"      # relative: stays on the site's host
    assert c.get("/stocks/in/NOPE/").status_code == 404


def test_stocks_is_a_page_with_search_not_raw_json(w):
    c = w["client"]
    for u in ("/stocks", "/stocks/", "/stocks/in", "/stocks/us/"):
        r = c.get(u)
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/html"), u
        assert "Company pages" in r.text and 'action="/stocks"' in r.text and '"detail"' not in r.text, u
    r = c.get("/stocks?q=reliance&m=in")
    assert r.status_code == 200 and 'href="/stocks/in/RELIANCE"' in r.text and "noindex" in r.text
    assert c.get("/stocks/xx").status_code == 404
    assert "https://stratlab.studio/stocks" in c.get("/sitemaps/pages.xml").text


# ---------- R5V-021: what the health check's feed means ----------
def test_health_says_the_feed_is_idle_without_a_live_session(w):
    h = w["client"].get("/health").json()
    assert h["feed"] == "idle" and h["feed_connected"] is False and "data_online" in h
