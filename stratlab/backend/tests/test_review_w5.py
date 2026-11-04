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
