"""LIVE6 (the live review of Release 34's theme page and deck): the theme's price periods, the latest news, the companies' own words,
one market value per company, and the deck's tables and charts."""
from datetime import date, timedelta

from app.intel import theme_prices as P


def _bars(start: date, end: date, f):
    out, d = [], start
    while d <= end:
        if d.weekday() < 5:
            out.append({"t": d.isoformat(), "c": f(d)})
        d += timedelta(days=1)
    return out


# ---------- LIVE6-002: calendar periods to the last close, a line that never runs past it ----------
def test_one_month_is_the_close_on_or_before_the_same_day_a_month_back():
    assert P.months_back(date(2026, 11, 10), 1) == date(2026, 10, 10)
    assert P.months_back(date(2026, 5, 31), 1) == date(2026, 4, 30) and P.months_back(date(2026, 3, 31), 3) == date(2025, 12, 31)
    assert P.months_back(date(2026, 11, 10), 36) == date(2023, 11, 10)
    # a close every weekday at its day-of-month: the 1M change is from the 9 Oct close (10 Oct 2026 is a Saturday) to the 10 Nov close
    bars = _bars(date(2026, 1, 1), date(2026, 11, 10), lambda d: 100.0 + d.toordinal() - date(2026, 1, 1).toordinal())
    r = P.reduce_bars(bars)
    last = 100.0 + (date(2026, 11, 10) - date(2026, 1, 1)).days
    base = 100.0 + (date(2026, 10, 9) - date(2026, 1, 1)).days
    assert r["ret"]["1M"] == round((last / base - 1) * 100, 1)
    base3 = 100.0 + (date(2026, 8, 10) - date(2026, 1, 1)).days
    assert r["ret"]["3M"] == round((last / base3 - 1) * 100, 1)


def test_the_theme_and_its_index_over_the_same_calendar_periods_and_the_line_ends_on_the_last_close():
    end = date(2026, 11, 10)                      # a Tuesday: the week isn't over
    start = date(2022, 1, 3)
    a = P.reduce_bars(_bars(start, end, lambda d: 100 + (d - start).days * 0.05))
    b = P.reduce_bars(_bars(start, end, lambda d: 50 + (d - start).days * 0.02))
    idx = P.reduce_bars(_bars(start, end, lambda d: 400 + (d - start).days * 0.1))
    out = P.compute([("A", "A Co"), ("B", "B Co")], {"A": a, "B": b}, idx, "SPY")
    weeks = out["line"]["weeks"]
    assert weeks[-1] == "2026-11-10" and max(weeks) <= "2026-11-10"            # never a Friday after the last close
    assert out["returns_to"] == "2026-11-10"
    # the index's 1M on the weekly line: from the last week ending on or before 10 Oct (Fri 9 Oct) to the last close
    days = [date.fromisoformat(w) for w in weeks]
    bench = out["line"]["bench"]
    i0 = max(i for i, d in enumerate(days) if d <= date(2026, 10, 10))
    assert days[i0] == date(2026, 10, 9)
    assert out["returns"]["1M"]["bench"] == round((bench[-1] / bench[i0] - 1) * 100, 1)
    i3 = max(i for i, d in enumerate(days) if d <= date(2026, 8, 10))
    assert out["returns"]["3M"]["bench"] == round((bench[-1] / bench[i3] - 1) * 100, 1)


# ---------- LIVE6-018: only articles with a source and a headline; no quote pages or click-bait ----------
def test_quote_pages_click_bait_and_rows_with_no_source_are_not_headlines():
    from app.intel.theme_data import headline_kept
    co = {"company": "CrowdStrike", "kind": "news"}
    assert not headline_kept({**co, "headline": "PANW Stock Quote Price and Forecast | CNN", "source": "CNN"}, "US")
    assert not headline_kept({**co, "headline": "If You Invested $1000 In CrowdStrike A Decade Ago, This Is How Much It Would Be Worth Now",
                              "source": "Benzinga"}, "US")
    assert not headline_kept({**co, "headline": "CrowdStrike stock forecast 2027", "source": "Site"}, "US")
    assert not headline_kept({**co, "headline": "CrowdStrike wins a federal contract", "source": ""}, "US")            # no source
    assert not headline_kept({**co, "headline": "", "source": "Reuters"}, "US")
    assert headline_kept({**co, "headline": "CrowdStrike wins a federal contract", "source": "Reuters"}, "US")
    assert headline_kept({"kind": "filing", "headline": "Annual report", "source": "SEC filing", "company": "X"}, "US")


def test_a_news_list_kept_before_the_rules_is_served_by_them(monkeypatch):
    from app.intel import theme_routes as T
    kept = {"items": [{"at": "2026-11-09", "headline": "PANW Stock Quote Price and Forecast | CNN", "company": "Palo Alto", "source": "CNN", "kind": "news"},
                      {"at": "2026-11-09", "headline": "Palo Alto buys a startup", "company": "Palo Alto", "source": "", "kind": "news"},
                      {"at": "2026-11-08", "headline": "Palo Alto buys a startup", "company": "Palo Alto", "source": "Reuters", "kind": "news"}], "as_of": "x"}

    class R:
        @staticmethod
        def theme_map(profile, region, q):
            return "US", q, {"generated_at": 1, "value_chain": [], "sub_themes": []}, None

        @staticmethod
        def ok(x):
            return x
    monkeypatch.setattr(T, "_routes", lambda: R)
    monkeypatch.setattr(T, "checked", lambda r, t, m: m)
    monkeypatch.setattr(T.theme_base, "for_figures", lambda m: (m, None))
    monkeypatch.setattr(T.computed, "get", lambda kind, key, **k: {"value": kept})
    out = T.theme_dive_news("Cyber", "US", profile=None)
    assert [i["source"] for i in out["items"]] == ["Reuters"]
