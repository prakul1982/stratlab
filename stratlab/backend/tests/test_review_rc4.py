"""RC-4 (28 Oct 2026): a correctness review of what shipped on 27-28 Oct (the company pages' paragraph and questions, the charts,
the blog's research posts, the IPO tracker behind one of them). One test or more for each thing it found and fixed."""
import re
from datetime import date, timedelta

import pytest

from app import main, stock_pages
from tests import world

FACTS = {"region": "IN", "symbol": "ACME", "name": "Acme Ltd", "exchange": "NSE", "industry": ["Industrials"], "currency": "INR", "unit": "₹ crore",
         "price": 2000.0, "price_at": "2026-10-27", "price_basis": "close", "high52": 2400.0, "low52": 1600.0, "market_cap": 770345.0, "pe": 14.3,
         "roe": 12.0, "opm": 28.0, "net_margin": 19.4, "debt_equity": 0.1, "div_yield": 1.1, "filings": [], "built_at": "2026-10-28T05:00:00+00:00",
         "growth": {"sales_cagr_3y": 6.4, "profit_cagr_3y": 1.0},
         "years": [{"year": f"Mar 202{i}", "sales": 100.0 * (i - 1), "profit": 20.0 + i, "opm": 26.0, "debt": 1.0} for i in range(2, 7)]}


def facts(**kw) -> dict:
    return {**FACTS, **kw}


def small(**kw) -> dict:
    """A small company: every figure of its table is under ₹100 crore, so the table shows two decimals."""
    years = [{"year": "Mar 2025", "sales": 0.52, "profit": 0.07, "opm": 4.0, "debt": 0.0}, {"year": "Mar 2026", "sales": 0.19, "profit": -0.03, "opm": -9.0, "debt": 0.0}]
    return facts(years=years, market_cap=12.0, pe=None, profit_ttm=0.31, **kw)


@pytest.fixture
def w(monkeypatch):
    built = world.build(monkeypatch)
    stock_pages._thin.clear()
    yield built
    built["close"]()


# ---------- RC4-001: the revenue and profit chart's scale ----------
def test_a_small_companys_axis_labels_each_tick_as_it_is():
    f = small()
    chart = stock_pages.bars_chart_html(f, 2)
    ticks = re.findall(r'class="by-tick" style="bottom:[\d.]+%">([^<]+)<', chart)
    values = [float(t.replace("−", "-").replace(",", "")) for t in ticks]
    assert len(set(ticks)) == len(ticks), ticks                                    # 0.6 and 0.8 were both "1"
    assert values == stock_pages.nice_ticks(-0.03, 0.52, 4) and values == sorted(values)
    assert "0" in ticks and any("." in t for t in ticks)


@pytest.mark.parametrize("ticks,digits", [([0, 250, 500], 0), ([-5, 0, 5, 10], 0), ([0, 2.5, 5, 7.5, 10], 1), ([0, 0.25, 0.5, 0.75, 1.0], 2),
                                          ([0.005, 0.01, 0.015], 3), ([1000, 2000], 0)])
def test_tick_digits_are_the_decimals_that_write_every_tick_exactly(ticks, digits):
    assert stock_pages.tick_digits(ticks) == digits


def test_a_big_companys_axis_is_unchanged():
    chart = stock_pages.bars_chart_html(facts(years=[{"year": "Mar 2025", "sales": 500.0, "profit": 60.0}, {"year": "Mar 2026", "sales": 450.0, "profit": -120.0}]))
    assert re.findall(r'class="by-tick"[^>]*>([^<]+)<', chart) == ["-200", "0", "200", "400", "600"]
    assert not re.search(r'by-tick"[^>]*>[^<]*\.\d', chart)                         # whole numbers, no decimals


# ---------- RC4-002: the paragraph's figures are the table's ----------
def test_a_small_companys_paragraph_gives_the_figures_its_table_gives():
    f = small()
    text = stock_pages.about_text(f, "IN", "ACME", "Acme Ltd")
    assert "revenue of ₹0.19 crore and a net loss of ₹0.03 crore" in text
    assert "<₹1" not in text and "₹1 crore" not in text
    assert "It made a net loss" not in text and "net profit over the last 12 months was ₹0.31 crore" in text
    table = stock_pages._table(f)
    assert ">0.19<" in table and ">-0.03<" in table
    us = stock_pages.about_text(facts(region="US", currency="USD", unit="$ million", years=[{"year": "Dec 2025", "sales": 12.3456, "profit": 0.39, "debt": 1.0}]),
                                "US", "ACME", "Acme Inc")
    assert "revenue of $12.35M and net profit of $0.39M" in us


def test_a_larger_companys_paragraph_is_in_the_words_it_was():
    f = facts(years=[{"year": "Mar 2025", "sales": 1200.0, "profit": 35.5, "debt": 1.0}, {"year": "Mar 2026", "sales": 1300.0, "profit": -35.5, "debt": 1.0}])
    text = stock_pages.about_text(f, "IN", "ACME", "Acme Ltd")
    assert "revenue of ₹1,300 crore and a net loss of ₹36 crore" in text            # the table's own rounding, as before
    # a company whose latest year is small but whose table has a large year keeps the table's whole numbers
    mixed = facts(years=[{"year": "Mar 2025", "sales": 450.0, "profit": 20.0, "debt": 1.0}, {"year": "Mar 2026", "sales": 40.0, "profit": 4.0, "debt": 1.0}])
    assert "revenue of ₹40 crore and net profit of ₹4 crore" in stock_pages.about_text(mixed, "IN", "ACME", "Acme Ltd")


# ---------- RC4-011: the 1-year range always holds the last close ----------
def test_the_exchanges_range_never_brings_a_candle_inside_its_own_close():
    """A closing auction can print beyond the continuous session's high or low; the exchange's 52-week figure leaves it out, and the page
    showed "Last close ₹161.69" over a range of ₹127.40 to ₹161.00 (ZETWERK, 27 Oct) and "₹680.20" over a low of ₹681.90 (HDFCBANK)."""
    up = [{"t": "2026-10-26", "o": 150, "h": 155, "l": 148, "c": 153}, {"t": "2026-10-27", "o": 155, "h": 161.69, "l": 154, "c": 161.69, "official": True}]
    got = stock_pages.fit_to_exchange_range(up, [161.0, "2026-10-27", 127.4, "2026-10-01"], "2026-10-27")
    assert got[-1]["h"] == 161.69 and stock_pages.price_facts(got)["high52"] == 161.69
    down = [{"t": "2026-10-26", "o": 700, "h": 705, "l": 690, "c": 695}, {"t": "2026-10-27", "o": 690, "h": 692, "l": 679.0, "c": 680.2}]
    got = stock_pages.fit_to_exchange_range(down, [1017.5, "2026-01-01", 681.9, "2026-10-27"], "2026-10-27")
    assert got[-1]["l"] == 679.0 or got[-1]["l"] <= 680.2
    assert stock_pages.price_facts(got)["low52"] <= 680.2
    # a stray print is still brought back to the exchange's figure when the close is inside it
    stray = [{"t": "2026-10-26", "o": 100, "h": 101, "l": 99, "c": 100}, {"t": "2026-10-27", "o": 100, "h": 104, "l": 99, "c": 101}]
    assert stock_pages.fit_to_exchange_range(stray, [102.0, "2026-10-20", 90.0, "2026-09-01"], "2026-10-27")[-1]["h"] == 102.0


# ---------- RC4-009: a dollar amount's unit is chosen after rounding ----------
def test_999_5_million_is_a_billion_not_1000_million():
    assert [stock_pages.usd_text(v) for v in (999.4, 999.5, 999.96, 1000, 999_949, 999_950)] == ["$999M", "$1.0B", "$1.0B", "$1.0B", "$999.9B", "$1.00T"]
    assert [stock_pages.inr_text(v) for v in (99_999.4, 99_999.5, 100_000)] == ["₹99,999 crore", "₹1.00 lakh crore", "₹1.00 lakh crore"]


# ---------- RC4-007: the market value answer names the price it rests on ----------
def test_the_market_value_answer_says_close_or_last_price_as_the_page_does():
    # the market's latest completed session, whatever day the suite runs (it read "27 Oct" as the latest until the 28th's close)
    last = stock_pages.last_close("IN")[0]
    close = stock_pages.faq_items(facts(price_at=last.isoformat()), "IN", "ACME", "Acme Ltd")[0][1]
    assert close.startswith(f"Acme Ltd's market value is ₹7.70 lakh crore as of {last.day} {last:%b %Y} close: the last close times the shares in issue.")
    assert "the last close over earnings per share" in close
    old = stock_pages.faq_items(facts(price_at="2026-10-05"), "IN", "ACME", "Acme Ltd")[0][1]
    assert "as of 5 Oct 2026: the last price this page has times the shares in issue." in old
    assert "the market has closed since" not in old and "the last close times" not in old
    assert "the last price this page has over earnings per share" in old
    last = stock_pages.faq_items(facts(price_basis="last"), "IN", "ACME", "Acme Ltd")[0][1]
    assert "as of 27 Oct 2026: the last price this page has times" in last


# ---------- RC4-008: holders' names ----------
def test_a_holders_name_is_closed_up_and_holds_no_separator():
    extras = {"holders": {"quarter": "2026-09-30", "holders": [
        {"name": "DSP SMALLCAP FUND , DSP MIDCAP FUND", "pct": 9.12, "group": "public"},
        {"name": "Alpha;  Beta  Trust", "pct": 5.0, "group": "promoter"}]}}
    answer = stock_pages.faq_items(facts(), "IN", "ACME", "Acme Ltd", extras)[-1][1]
    assert "DSP SMALLCAP FUND, DSP MIDCAP FUND (public) 9.12%; Alpha, Beta Trust (promoter group) 5%" in answer
    assert " ," not in answer


# ---------- RC4-006: what the share-price chart says about a split, a bonus issue or a demerger ----------
ROWS = [{"id": "A|split|2024-03-14|10-2", "kind": "split", "ex_date": "2024-03-14", "factor": 5.0, "short": "split (5 for 1)", "label": "Split"},
        {"id": "A|bonus|2025-06-02|1:1", "kind": "bonus", "ex_date": "2025-06-02", "factor": 2.0, "short": "1:1 bonus", "label": "Bonus 1:1"},
        {"id": "A|demerger|2025-10-14|", "kind": "demerger", "ex_date": "2025-10-14", "label": "Demerger", "short": "demerger"},
        {"id": "A|dividend|2025-08-01|", "kind": "dividend", "ex_date": "2025-08-01", "amount": 5.0, "label": "Dividend", "short": "dividend"},
        {"id": "A|split|2019-01-01|", "kind": "split", "ex_date": "2019-01-01", "factor": 2.0, "short": "split", "label": "Split"},
        {"id": "A|rights|2025-09-01|", "kind": "rights", "ex_date": "2025-09-01", "label": "Rights", "short": "rights"}]


def test_the_chart_names_the_splits_bonus_issues_and_demergers_inside_its_dates():
    got = stock_pages.chart_adjustments(ROWS, "2021-10-01", "2026-10-27", "IN")
    assert got == [{"d": "2024-03-14", "k": "split", "t": "split (5 for 1)"}, {"d": "2025-06-02", "k": "bonus", "t": "1:1 bonus"}, {"d": "2025-10-14", "k": "demerger"}]
    # a dividend or a rights issue moves no price series; an action before the first date or after the last is not in the chart
    assert stock_pages.chart_adjustments(ROWS, "2025-06-02", "2025-10-13", "IN") == []
    assert [x["k"] for x in stock_pages.chart_adjustments(ROWS, "2025-06-01", "2025-10-14", "IN")] == ["bonus", "demerger"]
    # a US price-history adjustment (labelled so) is not called a demerger, and nothing is read from a bad row
    us = [{"id": "x", "kind": "demerger", "ex_date": "2025-10-01", "label": "Price adjustment"}, "junk", None, {"kind": "split"}]
    assert stock_pages.chart_adjustments(us, "2021-10-01", "2026-10-27", "US") == []
    many = [{"id": f"s{i}", "kind": "split", "ex_date": f"2024-0{i}-01", "factor": 2.0, "short": f"split {i}"} for i in range(1, 9)]
    assert len(stock_pages.chart_adjustments(many, "2021-01-01", "2026-01-01")) == stock_pages.CHART_ADJ_MAX


def test_the_prices_carry_the_stored_actions_and_the_page_holds_the_note(w):
    from app import corp_actions
    c = w["client"]
    first = c.get("/stocks/in/RELIANCE/prices.json").json()
    assert "adj" not in first                                                       # nothing stored: nothing said
    main.chart_cache._d.clear()
    day = (date(1970, 1, 1) + timedelta(days=first["t"][len(first["t"]) // 2])).isoformat()
    corp_actions.hist_save("IN", "RELIANCE", [{"id": f"RELIANCE|bonus|{day}|1:1", "kind": "bonus", "sub": "1:1", "label": "Bonus 1:1", "short": "1:1 bonus",
                                                "text": "Bonus 1:1", "ex_date": day, "factor": 2.0, "ratio": [1, 1], "region": "IN", "symbol": "RELIANCE"}])
    j = c.get("/stocks/in/RELIANCE/prices.json").json()
    assert j["adj"] == [{"d": day, "k": "bonus", "t": "1:1 bonus"}] and j["t"] == first["t"] and j["c"] == first["c"]
    page = c.get("/stocks/in/RELIANCE").text
    assert 'data-adjust hidden' in page and page.index("data-summary") < page.index("data-adjust")
    assert "Closes before" in stock_pages.CHART_JS and "not the prices traded then" in stock_pages.CHART_JS


def test_the_older_closes_are_as_traded_like_the_recent_year(w, monkeypatch):
    """The broker scales every candle before an extraordinary dividend's ex-date; the page's year has that undone, so the chart's older
    closes must too, or the line steps by the dividend's share where the two meet a year back (RC4-006)."""
    c = w["client"]
    base = c.get("/stocks/in/RELIANCE/prices.json").json()
    epoch = date(1970, 1, 1)
    i = len(base["t"]) // 4                                                         # a weekly point well before the last year
    day = (epoch + timedelta(days=base["t"][i])).isoformat()
    assert base["t"][i] < base["t"][-1] - stock_pages.CHART_DAILY_DAYS
    amount = round(base["c"][i - 1] * 0.1, 2)                                       # 10% of the price: the broker adjusted for it
    main.chart_cache._d.clear()
    monkeypatch.setattr(main, "india_page_dividends", lambda *a, **k: [{"date": day, "amount": amount}])
    got = c.get("/stocks/in/RELIANCE/prices.json").json()
    assert got["t"] == base["t"]
    k = got["c"][i - 1] / base["c"][i - 1]
    assert 1.05 < k < 1.15                                                          # (price + dividend) / price
    assert all(abs(got["c"][j] / base["c"][j] - k) < 0.002 for j in range(0, i))   # every earlier close scaled alike
    assert got["c"][i:] == base["c"][i:]                                            # the ex-date and after as they were
    # the same line for a market with no such scaling
    us = c.get("/stocks/us/AAPL/prices.json").json()
    main.chart_cache._d.clear()
    assert c.get("/stocks/us/AAPL/prices.json").json() == us
