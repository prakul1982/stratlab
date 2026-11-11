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


# ---------- LIVE6-007: a company's own words only when they say what it does ----------
OWN_CASES = [  # (text, name, shown)
    ("From its own filings: Annual report (20-F).", "Check Point Software", False),
    ("Annual report (20-F)", "Check Point Software", False),
    ("Fortinet, Inc.", "Fortinet, Inc.", False),
    ("Fortinet, Inc. is an American multinational corporation headquartered in Sunnyvale, California", "Fortinet, Inc.", False),
    ("Rapid7 is an American cybersecurity company headquartered in Boston, Massachusetts", "Rapid7, Inc.", False),
    ("Fortinet provides cybersecurity solutions to enterprises and service providers", "Fortinet, Inc.", True),
    ("Tata Motors Limited is a leading global automobile manufacturer", "Tata Motors Ltd", True),
    ("The company is engaged in the business of manufacturing auto components", "Uno Minda Ltd", True),
    ("It manufactures steel wheels for cars", "Steel Strips Wheels Ltd", True),
]


def test_a_line_is_shown_as_its_own_words_only_when_it_says_what_the_company_does():
    from app.intel.theme_base import own_words
    for text, name, shown in OWN_CASES:
        assert bool(own_words(text, name)) is shown, text
    from app import deck
    assert deck._what("Fortinet, Inc.", "Fortinet, Inc.") == "" and deck.NO_WORDS == "No description in its own words yet"
    from app.intel import theme_routes as T
    m = T.with_caps({"value_chain": [{"companies": [{"ticker": "CHKP", "name": "Check Point", "what": "From its own filings: Annual report (20-F)."},
                                                    {"ticker": "FTNT", "name": "Fortinet", "what": "Fortinet provides network security products"}]}],
                     "sub_themes": []}, [])
    assert [c["what"] for c in m["value_chain"][0]["companies"]] == ["", "Fortinet provides network security products"]


# ---------- LIVE6-006: one market value per company, one date format ----------
def test_the_deck_and_csv_take_one_market_value_per_company_and_write_dates_one_way():
    from app.intel import theme_routes as T
    from app import deck
    m = {"value_chain": [{"layer": "L", "companies": [{"ticker": "PANW", "name": "Palo Alto Networks", "cap": 267000.0}]}], "sub_themes": []}
    dive = {"layers": [{"companies": [{"symbol": "PANW", "name": "Palo Alto Networks", "cap": 256700.0}]}], "subs": []}
    assert [x["cap"] for x in T.members_of(m, dive)] == [256700.0]
    pp = {"theme": 40.0, "peers": 30.0, "n": 5, "premium": 33.3, "as_of": "2026-11-10"}
    assert "prices at the 10 Nov 2026 close" in deck.pe_peer_line(pp)
    assert "2026-11" not in deck.peer_moved_line({"moved": {"from": 19.2, "to": 18.4, "on": "2026-11-08", "at": "2026-11-09"}})


# ---------- LIVE6-008: no line through under 4 points, no row of dashes, no table mostly dashes; the gate catches each ----------
def test_a_line_needs_four_points_a_measure_row_a_figure_and_a_table_more_than_dashes():
    from app import deck as D
    s = D.Slide("Valuation", "x", eyebrow="Numbers")
    s.add("table", (D.M, D.TOP, 7.0, 2.0), head=["Measure", "Theme median", "Range"], rows=[["P/E", "43.0x", "10x to 90x"], ["Interest cover", "–", "–"]],
          widths=[2.6, 1.3, 1.8])
    s.add("lines", (D.M + 7.4, D.TOP, D.CW - 7.4, 4.0), title="weekly", cats=["06 Nov", "13 Nov"], series=[("P/E", [125.4, 43.0], D.BLUE)], fmt="x")
    t = D.Slide("Balance sheet", "y", eyebrow="Numbers")
    t.add("table", (D.M, D.TOP, D.CW, 2.0), head=["Measure", "Median", "Range", "Peers", "Companies"],
          rows=[["A", "– (2)", "–", "–", "2"], ["B", "– (1 of 6)", "–", "n/a", "6"], ["C", "–", "–", "–", "5"]], widths=[3, 1, 1, 1, 1])
    flags = D.complete_flags([s, t])
    assert {"a line chart through 2 points", "a table mostly dashes"} <= {f["why"] for f in flags}
    done = D.tidy_tables([s, t])
    assert [b["kind"] for b in s.blocks] == ["table"] and s.blocks[0]["box"][2] == D.CW          # the table takes the chart's room
    assert [r[0] for r in s.blocks[0]["rows"]] == ["P/E"]                                          # the row of dashes is dropped
    assert t.blocks[0]["kind"] == "text" and t.blocks[0]["paras"][0] == "Left out here, as most of their figures aren't stored yet: A, B, C."
    assert len(done) == 3
    assert not [f for f in D.complete_flags([s, t]) if f["why"] in ("a line chart through 2 points", "a table mostly dashes")]
    # a list of companies keeps every row, whatever its cells
    u = D.Slide("Layer 1 · X", "z", eyebrow="Layers")
    u.add("table", (D.M, D.TOP, D.CW, 2.0), head=["Company", "Revenue"], rows=[["A Co (no figures)", "–"], ["B Co", "–"]], widths=[3, 1])
    D.tidy_tables([u])
    assert len(u.blocks[0]["rows"]) == 2
    # a page whose one table has one row is caught
    one = D.Slide("New listings", "w", eyebrow="Numbers")
    one.add("table", (D.M, D.TOP, D.CW, 1.0), head=["Issue", "Stage"], rows=[["X", "Coming"]], widths=[3, 1])
    assert "a page for a table of one row" in {f["why"] for f in D.complete_flags([one])}
