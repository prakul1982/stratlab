"""PUB-1: the charts on a company's public page. The share price is drawn in the browser by one small script from a cached,
rationed list of daily closes; revenue and profit are drawn on the server, as HTML and CSS, from the years the page stores.
Both say what they show in text, say nothing of the future, and name no source."""
import re
from datetime import date, timedelta

import pytest

from app import main, stock_pages
from tests import world

PROVIDERS = re.compile(r"kite|zerodha|yahoo|screener|finnhub|edgar|nseindia|bseindia", re.I)
ADVICE = re.compile(r"\b(buy|sell|hold|accumulate|avoid|target|undervalued|overvalued|recommend\w*|forecast|predict\w*)\b", re.I)


@pytest.fixture
def w(monkeypatch):
    built = world.build(monkeypatch)
    stock_pages._thin.clear()
    yield built
    built["close"]()


def _facts(**kw) -> dict:
    base = {"region": "IN", "symbol": "ACME", "name": "Acme Ltd", "exchange": "NSE", "industry": ["Industrials"], "currency": "INR",
            "unit": "₹ crore", "price": 100.0, "price_at": "2026-10-07", "price_basis": "close", "high52": 120.0, "low52": 80.0,
            "market_cap": 770345.0, "pe": 14.3, "roe": 12.0, "opm": 28.0, "net_margin": 19.4, "debt_equity": 0.1, "div_yield": 1.1,
            "years": [{"year": f"Mar 202{i}", "sales": 100.0 * (i - 1), "profit": 20.0 + i, "opm": 26.0, "debt": 1.0} for i in range(2, 7)],
            "growth": {"sales_cagr_3y": 6.4, "profit_cagr_3y": 1.0}, "filings": [], "built_at": "2026-10-08T05:00:00+00:00"}
    return {**base, **kw}


def _bars(days: list[str], start: float = 100.0) -> list[dict]:
    return [{"t": d + "T00:00:00+05:30", "o": start + i, "h": start + i + 1, "l": start + i - 1, "c": start + i} for i, d in enumerate(days)]


def _span(first: str, n: int) -> list[str]:
    d0 = date.fromisoformat(first)
    return [(d0 + timedelta(days=i)).isoformat() for i in range(n)]


# ---------- the closes: shape, thinning, honest gaps ----------
def test_a_series_is_every_session_of_the_last_year_and_a_close_a_week_before_it():
    days = _span("2020-01-01", 2200)                      # about six years, a candle every day
    got = stock_pages.chart_series(_bars(days))
    assert len(got["t"]) == len(got["c"]) and got["t"] == sorted(got["t"])
    last = (date.fromisoformat(days[-1]) - date(1970, 1, 1)).days
    assert got["t"][-1] == last and got["c"][-1] == round(100.0 + 2199, 2)
    cut = last - stock_pages.CHART_DAILY_DAYS
    recent = [t for t in got["t"] if t >= cut]
    assert len(recent) == stock_pages.CHART_DAILY_DAYS + 1                      # every day of the last year
    older = [t for t in got["t"] if t < cut]
    assert all(b - a >= 5 for a, b in zip(older[:-1], older[1:-1]))              # a week apart before it (the last may end a part week)
    assert len(got["t"]) < 700                                                  # about 6 KB, not six years of days


def test_the_closes_are_the_sources_own_numbers():
    days = _span("2026-09-01", 40)
    bars = _bars(days, 250.0)
    bars[10]["c"] = 251.239
    bars[11]["c"] = 0.05127
    got = stock_pages.chart_series(bars)
    epoch = date(1970, 1, 1)
    by_day = {(epoch + timedelta(days=t)).isoformat(): c for t, c in zip(got["t"], got["c"])}
    assert by_day[days[0]] == 250.0 and by_day[days[39]] == 289.0
    assert by_day[days[10]] == 251.24 and by_day[days[11]] == 0.0513            # to the cent; four decimals under 10 cents


def test_unreadable_rows_are_left_out_and_too_few_closes_make_no_series():
    bars = _bars(_span("2026-09-01", 5))
    bars[1]["c"] = None
    bars[2]["c"] = float("nan")
    bars[3]["c"] = -4
    bars[4]["t"] = "later"
    assert stock_pages.chart_series(bars) == {}                                  # one usable close is no line
    assert stock_pages.chart_series([]) == {} and stock_pages.chart_series(None) == {}


# ---------- the endpoint ----------
def test_prices_are_the_pages_price_and_the_pages_own_candles(w):
    r = w["client"].get("/stocks/in/RELIANCE/prices.json")
    assert r.status_code == 200
    j = r.json()
    assert j["currency"] == "INR" and len(j["t"]) == len(j["c"]) > 200
    page = w["client"].get("/stocks/in/RELIANCE").text
    assert j["c"][-1] == 1400.0 and "₹1,400.00" in page                          # the chart ends at the price the page shows
    last = date(1970, 1, 1) + timedelta(days=j["t"][-1])
    assert f"{last.day} {last:%b %Y} close" in page                               # ...on the day it says
    # every point of the last year is a close of the page's own candles, to the cent
    co = stock_pages.find("IN", "RELIANCE")[1]
    bars = {b["t"][:10]: b["c"] for b in stock_pages.closed_bars(main.stock_page_bars("IN", co), "IN")}
    recent = {(date(1970, 1, 1) + timedelta(days=t)).isoformat(): c for t, c in zip(j["t"], j["c"]) if t >= j["t"][-1] - 360}
    assert len(recent) > 230 and all(abs(bars[d] - c) < 0.006 for d, c in recent.items())
    # five years of history where the source has it (the fake broker has all it is asked for)
    assert j["t"][-1] - j["t"][0] >= 1700


def test_prices_are_kept_by_the_edge_and_the_series_by_the_server(w):
    c = w["client"]
    r = c.get("/stocks/in/TCS/prices.json")
    assert "s-maxage=3600" in r.headers["cache-control"] and "stale-while-revalidate" in r.headers["cache-control"]
    reads = []
    real = main.stock_page_series
    main.stock_page_series = lambda *a, **k: reads.append(a) or real(*a, **k)
    try:
        for _ in range(3):
            assert c.get("/stocks/in/TCS/prices.json").status_code == 200
    finally:
        main.stock_page_series = real
    assert reads == []                                                            # served from the small cache: no read of the sources
    assert len(main.chart_cache._d) <= 400 and main.chart_cache.max_bytes <= 8 * 1024 * 1024


def test_reads_of_the_sources_are_held_to_a_few_a_minute(w, monkeypatch):
    c = w["client"]
    monkeypatch.setattr(main, "CHART_BUILDS_PER_MINUTE", 2)
    assert c.get("/stocks/in/TCS/prices.json").status_code == 200
    assert c.get("/stocks/in/INFY/prices.json").status_code == 200
    busy = c.get("/stocks/in/SBIN/prices.json")
    assert busy.status_code == 503 and busy.headers["retry-after"] == "60" and busy.headers["cache-control"] == "no-store"
    assert c.get("/stocks/in/TCS/prices.json").status_code == 200                 # one already read costs no ration
    monkeypatch.setattr(main, "CHART_BUILDS_PER_MINUTE", 30)
    monkeypatch.setattr(main, "CHART_BUILDS_PER_ADDRESS", 1)
    main.chart_reads._d.clear()
    assert c.get("/stocks/in/ITC/prices.json").status_code == 200
    assert c.get("/stocks/in/WIPRO/prices.json").status_code == 503              # one address: one read of its own a minute


def test_a_company_with_no_page_or_no_prices_is_a_cached_404(w, monkeypatch):
    c = w["client"]
    for url in ("/stocks/in/NOSUCHCO/prices.json", "/stocks/xx/TCS/prices.json", "/stocks/in/tcs/prices.json"):
        r = c.get(url)
        assert r.status_code == 404 and r.json()["detail"]["code"] == "no_prices" and "s-maxage" in r.headers["cache-control"]
    monkeypatch.setattr(main, "stock_page_bars", lambda region, co: [])
    r = c.get("/stocks/in/ONGC/prices.json")
    assert r.status_code == 404 and "s-maxage=300" in r.headers["cache-control"]
    monkeypatch.setattr(main, "stock_page_bars", lambda region, co: (_ for _ in ()).throw(RuntimeError("a source is down")))
    assert c.get("/stocks/in/NTPC/prices.json").status_code == 404                # a failed read is the same, not a crash


def test_a_failed_long_read_leaves_the_last_year(w, monkeypatch):
    kite = main.markets.providers["IN"].kite
    real = kite.history

    def history(token, tf, days, *a, **k):
        if days >= stock_pages.CHART_READ_DAYS:
            raise RuntimeError("the long read failed")
        return real(token, tf, days, *a, **k)
    monkeypatch.setattr(kite, "history", history)
    j = w["client"].get("/stocks/in/RELIANCE/prices.json").json()
    assert j["c"][-1] == 1400.0 and 200 < len(j["t"]) < 450 and j["t"][-1] - j["t"][0] < 450         # the year and a bit; no 5-year range


def test_the_series_names_no_source_and_no_advice(w):
    r = w["client"].get("/stocks/us/AAPL/prices.json")
    assert r.status_code == 200 and r.json()["currency"] == "USD"
    assert not PROVIDERS.search(r.text) and not PROVIDERS.search(stock_pages.CHART_JS)
    assert not re.search(r"\b(buy|sell|hold|undervalued|overvalued|recommend\w*|forecast|predict\w*)\b", stock_pages.CHART_JS.replace("nothing is predicted, fitted or extended", ""), re.I)


# ---------- the page ----------
def test_the_page_has_the_chart_card_with_its_text_and_its_table(w):
    t = w["client"].get("/stocks/in/RELIANCE").text
    for part in ('<h2>Share price</h2>', 'data-chart', 'data-src="/stocks/in/RELIANCE/prices.json"', 'data-currency="INR"',
                 'data-r="1m"', 'data-r="6m"', 'data-r="1y"', 'data-r="5y"', 'aria-label="Chart range"', "data-change", "data-summary",
                 "Show the closes as a table", 'aria-live="polite"', "<noscript>", 'src="/stocks/chart.js?v=' + stock_pages.CHART_JS_V + '" defer'):
        assert part in t, part
    # the same facts as words, so a crawler or a visitor with no script reads them: the close and the year's range
    summary = re.search(r"<p class=\"small muted\" data-summary>(.*?)</p>", t).group(1)
    assert "Last close ₹1,400.00 on 27 Oct 2026." in summary and "traded between ₹1,201.43 and ₹1,551.90 (intraday)" in summary
    assert t.index("Share price</h2>") < t.index("Price trend</h2>")             # after the figures, before the numbers by year
    us = w["client"].get("/stocks/us/AAPL").text
    assert 'data-currency="USD"' in us and 'data-src="/stocks/us/AAPL/prices.json"' in us
    assert not ADVICE.search(re.sub(r"<[^>]*>", " ", re.sub(r"<(style|script)\b.*?</\1>", "", t, flags=re.S)).split("Not investment advice")[0].replace("Last close", ""))


def test_a_price_that_is_a_last_trade_has_no_chart_and_a_page_without_a_price_neither():
    page = stock_pages.render(_facts(price_basis="last"), "IN", "ACME", "Acme Ltd")
    assert "data-chart" not in page and "/stocks/chart.js" not in page and "Revenue and profit" in page
    assert "data-chart" not in stock_pages.render(_facts(price=None, price_at=None), "IN", "ACME", "Acme Ltd")
    assert "data-chart" in stock_pages.render(_facts(), "IN", "ACME", "Acme Ltd")


def test_a_company_page_may_run_the_sites_script_and_nothing_else(w):
    csp = w["client"].get("/stocks/in/RELIANCE").headers["content-security-policy"]
    assert "script-src 'self'" in csp and "connect-src 'self'" in csp and "'unsafe-inline'" not in csp.split("style-src")[0]
    assert "default-src 'none'" in csp and "frame-ancestors 'none'" in csp
    for url in ("/stocks", "/stocks/in", "/stocks/in/browse/r", "/stocks/in/index/nifty-50", "/blog"):
        other = w["client"].get(url).headers["content-security-policy"]
        assert "script-src" not in other and "connect-src" not in other, url      # every other page of the API stays script-free
    js = w["client"].get("/stocks/chart.js")
    assert js.status_code == 200 and js.headers["content-type"].startswith("text/javascript") and "s-maxage" in js.headers["cache-control"]
    assert js.text == stock_pages.CHART_JS


def test_the_script_is_a_chart_people_can_use():
    js = stock_pages.CHART_JS
    for part in ("IntersectionObserver", "pointermove", "pointerdown", "touchAction", "ArrowLeft", "aria-label", "Intl.NumberFormat",
                 "Highest close", "lowest close", "Price change only", "1m", "6m", "1y", "5y", "Not enough history", "Try again"):
        assert part in js, part
    assert "font-size\": 12" in js and "font-size\": 1" not in js.replace('"font-size": 12', "")      # no axis text under 12 px
    assert "XMLHttpRequest" not in js and "eval(" not in js and "innerHTML = body" in js            # the table's rows are numbers and dates the script made itself
    assert len(js) < 14000                                                                            # a small script, no library


# ---------- revenue and profit, drawn on the server ----------
def test_revenue_and_profit_columns_match_the_table_and_start_at_zero():
    f = _facts()
    page = stock_pages.render(f, "IN", "ACME", "Acme Ltd")
    chart = re.search(r'<figure class="by".*?</figure>', page, re.S).group(0)
    assert chart.count('class="by-col"') == 5 and chart.count("by-bar rev") == 5 and chart.count("by-bar pro") == 5
    # each column says its numbers: the labels are the table's own figures
    for y in f["years"]:
        assert f'aria-label="{y["year"]}: revenue {stock_pages._amount(f, y["sales"])}, net profit {stock_pages._amount(f, y["profit"])} (₹ crore)"' in chart
    heights = [float(h) for h in re.findall(r"by-bar rev\" style=\"bottom:[\d.]+%;height:([\d.]+)%", chart)]
    assert heights == sorted(heights) and heights[0] < heights[-1]
    top = max(y["sales"] for y in f["years"])
    # a column is its value's share of the tallest tick: 400 of the largest tick's height
    ticks = [float(x.replace(",", "")) for x in re.findall(r'class="by-tick"[^>]*>([\d,]+)<', chart)]
    assert ticks[0] == 0 and max(ticks) >= top and abs(heights[-1] - top / max(ticks) * 100) < 0.1
    assert "₹ crore" in chart and "<figcaption" not in chart


def test_a_loss_is_a_column_below_the_baseline():
    f = _facts(years=[{"year": "Mar 2025", "sales": 500.0, "profit": 60.0}, {"year": "Mar 2026", "sales": 450.0, "profit": -120.0}])
    chart = stock_pages.bars_chart_html(f)
    assert chart.count("by-bar pro neg") == 1 and chart.count("by-bar pro\"") == 1
    ticks = re.findall(r'class="by-tick" style="bottom:([\d.]+)%">([-−\d,]+)<', chart)
    assert any(t[1].startswith(("-", "−")) for t in ticks)                       # the axis reaches below zero
    zero = next(float(b) for b, v in ticks if v == "0")
    loss = re.search(r"by-bar pro neg\" style=\"bottom:([\d.]+)%;height:([\d.]+)%", chart)
    assert abs(float(loss.group(1)) + float(loss.group(2)) - zero) < 0.05          # it hangs from the baseline


def test_too_few_years_draw_no_columns_and_the_table_stays():
    page = stock_pages.render(_facts(years=[{"year": "Mar 2026", "sales": 5.0, "profit": 1.0}]), "IN", "ACME", "Acme Ltd")
    assert 'class="by"' not in page and "Revenue and profit" in page
    assert stock_pages.bars_chart_html(_facts(years=[])) == ""


def test_nice_ticks_are_round_numbers():
    assert stock_pages.nice_ticks(0, 964693, 4) == [0, 250000, 500000, 750000, 1000000]
    assert stock_pages.nice_ticks(-120, 500, 4) == [-200, 0, 200, 400, 600]
    assert stock_pages.nice_ticks(0, 0.9, 4) == [0, 0.25, 0.5, 0.75, 1.0]
    assert stock_pages.nice_ticks(0, 0, 4)[0] == 0
