"""The REVIEW lane (Wed 4 Nov): the LIVE2 re-check's open findings, fixed at the root."""
import re

from app import stock_pages


def test_a_loss_year_axis_uses_the_true_minus():
    # LIVE2-017: the revenue-and-profit chart's ticks below zero read "-2,500" (RPOWER) while every other negative on the page is "−"
    f = {"region": "IN", "years": [{"label": "Mar 2025", "end": "2025-03-31", "sales": 8000.0, "profit": -2100.0},
                                   {"label": "Mar 2026", "end": "2026-03-31", "sales": 9000.0, "profit": 400.0}]}
    html = stock_pages.bars_chart_html(f)
    ticks = re.findall(r'class="by-tick"[^>]*>([^<]+)<', html)
    assert ticks and any(t.startswith("−") for t in ticks), ticks
    assert not any(t.startswith("-") for t in ticks), ticks


def test_every_figure_the_company_page_writes_takes_the_true_minus():
    # LIVE2-017 as a class: _fmt is where every reported figure on a company page and its cards is written (tables, tiles, the
    # chart's ticks and tips), so a negative is "−" everywhere, never "-"
    assert stock_pages._fmt(-1234.5, 1) == "−1,234.5" and stock_pages._fmt(-0.04, 0) == "−0.04" and stock_pages._fmt(5, 0, "%") == "5%"
    f = {"region": "IN", "years": [{"year": "Mar 2025", "sales": 800.0, "profit": -210.0}, {"year": "Mar 2026", "sales": 900.0, "profit": 40.0}]}
    html = stock_pages.bars_chart_html(f) + stock_pages._table({**f, "currency": "INR"})
    assert "−210" in html and not re.search(r">-\d", html) and not re.search(r"[ (]-\d", re.sub(r"<[^>]+>", " ", html))


def test_a_steep_three_year_rate_names_the_year_it_started_from():
    # RC4-015 for every company page: a rate of 50% a year or more says its first year's figure (a merger year, a one-off), a usual one doesn't
    assert stock_pages.growth_words("net profit", 213.2, "₹1,105 cr in Mar 2023") == "net profit grew 213.2% a year, from ₹1,105 cr in Mar 2023"
    assert stock_pages.growth_words("revenue", 6.4, "₹100 cr in Mar 2023") == "revenue grew 6.4% a year"
    ys = [{"year": f"Mar {y}", "sales": s, "profit": p} for y, s, p in ((2022, 900.0, 5.0), (2023, 1000.0, 10.0), (2024, 1100.0, 60.0), (2025, 1200.0, 200.0), (2026, 1300.0, 300.0))]
    html = stock_pages._table({"region": "IN", "unit": "₹ crore", "years": ys, "growth": {"sales_cagr_3y": 9.1, "profit_cagr_3y": 210.7}})
    assert "net profit grew 210.7% a year, from 10 in Mar 2023" in html and "revenue grew 9.1% a year," in html


def test_an_issue_whose_final_bids_were_missed_is_read_again_weekly_after_the_newer_ones():
    # RC4-020 for every listed issue: missed final bids are tried again once a week for half a year, after the current ones
    from datetime import datetime, timezone
    from app import ipo
    now = datetime(2026, 11, 4, 6, 0, tzinfo=timezone.utc)
    old = {"market": "IN", "symbol": "OLDCO", "series": "EQ", "open": "2026-08-01", "close": "2026-08-05", "listing": "2026-08-10"}
    assert ipo._wants_detail(old, now)                                                    # 86 days, no bids stored: read
    assert not ipo._wants_detail({**old, "detail_at": "2026-11-01T10:00:00+05:30"}, now)  # read this week already
    assert ipo._wants_detail({**old, "detail_at": "2026-10-20T10:00:00+05:30"}, now)      # a week and more ago: again
    assert not ipo._wants_detail({**old, "sub": {"times": 12.5}}, now)                     # its bids are in: done
    assert not ipo._wants_detail({**old, "listing": "2026-04-01", "open": "2026-03-20", "close": "2026-03-25"}, now)   # over half a year
