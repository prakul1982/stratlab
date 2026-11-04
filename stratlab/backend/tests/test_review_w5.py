"""The REVIEW lane (Wed 4 Nov): the LIVE2 re-check's open findings, fixed at the root."""
import re

from app import blog_research, stock_pages


def test_a_loss_year_axis_uses_the_true_minus():
    # LIVE2-017: the revenue-and-profit chart's ticks below zero read "-2,500" (RPOWER) while every other negative on the page is "−"
    f = {"region": "IN", "years": [{"label": "Mar 2025", "end": "2025-03-31", "sales": 8000.0, "profit": -2100.0},
                                   {"label": "Mar 2026", "end": "2026-03-31", "sales": 9000.0, "profit": 400.0}]}
    html = stock_pages.bars_chart_html(f)
    ticks = re.findall(r'class="by-tick"[^>]*>([^<]+)<', html)
    assert ticks and any(t.startswith("−") for t in ticks), ticks
    assert not any(t.startswith("-") for t in ticks), ticks
