"""Release 44 (lane v1, the outside review of the live R43 decks): no figure is dropped by a cutoff alone. An unusual figure is reconciled with
the company's own stored figures for the same year and unit and given one of three states (verified_extreme, kept; unverified_extreme,
shown and left out with its reason; invalid, "–" and left out), one record per company, read the same way by every page that counts them;
and the coverage says once how many of the companies placed are in an informative layer.

Permanent regression from a real filing: Micron Technology's fiscal 2026 (year to September 2026) annual report, net income of $84,969
million on revenue of $133,188 million, a net margin of 63.8% (the live R43 Semiconductors deck left it out under a ±60% rule); its 81.7%
EBITDA margin is the stored page's, as the live R41 deck's appendix printed it. Every other company here is synthetic."""
import re

from app import deck
from app.intel import theme_data as D
from app.intel import theme_routes as T
from scripts import deck_check
from tests.test_export import texts
from tests.test_r18_deck import deck_of
from tests.test_theme1 import facts

MU_SALES, MU_PROFIT, MU_EBITDA = 133188.0, 84969.0, 81.7          # Micron FY2026 (10-K, fiscal year ended Sep 2026), $ million


def us(f, labels=("Sep 2023", "Sep 2024", "Sep 2025", "Sep 2026")):
    f.update(region="US", unit="$ million")
    for y, lab in zip(f["years"], labels[-len(f["years"]):]):
        y["year"] = lab
    return f


def micron():
    # earlier years as filed (FY2023 a loss: revenue $15,540 million, net loss $5,833 million; FY2024 $25,111m / $778m; FY2025 $37,378m / $8,539m)
    return us(facts("MU", "Micron Technology Inc", [15540, 25111, 37378, MU_SALES], [-1.0, 32.0, 45.0, MU_EBITDA], [-5833, 778, 8539, MU_PROFIT],
                    cap=780700, pe=9.3, roce=44.3, industry=("Semiconductors",)))


def chip(sym, name, net, ebitda=30.0, sales=20000.0):
    return us(facts(sym, name, [sales * 0.8, sales * 0.9, sales * 0.95, sales], [ebitda] * 4, [sales * net / 100 * k for k in (0.8, 0.9, 0.95, 1)],
                    cap=sales * 4, industry=("Semiconductors",)))


def semis_map(extra=()):
    cos = [{"name": "Micron Technology Inc", "ticker": "MU", "what": "makes memory chips"}] + \
          [{"name": f"Chip {i} Inc", "ticker": f"CH{i}", "what": "makes memory chips"} for i in range(4)] + list(extra)
    return {"sector": "Semiconductors", "value_chain": [{"layer": "Memory makers", "description": "Makes memory chips.", "companies": cos}],
            "sub_themes": [], "placements": {"checked": True, "pending": 0, "left_out": 0, "placed": len(cos)}}


def semis_facts():
    f = {"MU": micron()}
    for i, n in enumerate((10.0, 14.0, 18.0, 22.0)):
        f[f"CH{i}"] = chip(f"CH{i}", f"Chip {i} Inc", n)
    return f


def conf_rows(slides):
    conf = next(s for s in slides if s.title == "Data confidence")
    return {r[0]: r for b in conf.blocks if b["kind"] == "table" for r in b["rows"]}


# ---------- 1. Micron FY2026: kept and marked verified, never suppressed by a generic threshold ----------
def test_micron_fy2026_net_margin_is_verified_against_its_own_filing_and_kept(monkeypatch):
    r = D.company_row("US", "MU", micron())
    assert r["net"] == 63.8 and not r["one_off"] and "net" not in (r.get("held") or {})
    rec = r["verify"]["net"]
    assert rec["state"] == D.VERIFIED and rec["checks"] == [D.CHECKS["net_unusual"]]
    assert rec["why"] == "net profit $84,969 million over revenue $133,188 million, Sep 2026: 63.8%; at or below its 81.7% EBITDA margin"
    for cut in (60.0, 30.0, 10.0):       # the threshold only decides what is checked, never what is kept
        monkeypatch.setattr(D, "NET_UNUSUAL", cut)
        assert D.company_row("US", "MU", micron())["net"] == 63.8 and D.in_median(D.company_row("US", "MU", micron()), "net") == 63.8


def test_the_semis_deck_counts_micron_in_the_net_margin_median_and_says_it_is_verified():
    v, slides = deck_of("US", semis_map(), semis_facts())
    lay = v["layers"][0]
    assert lay["stats"]["net"]["n"] == 5 and lay["stats"]["net"]["max"] == 63.8 and lay["stats"]["net"]["median"] == 18.0
    assert v["sections"]["medians"]["net"]["n"] == 5 and v["sections"]["medians"]["net"]["max"] == 63.8
    ch = v["checks"]
    assert [(x["symbol"], x["state"]) for x in ch["states"]] == [("MU", D.VERIFIED)] and [x["symbol"] for x in ch["verified"]] == ["MU"]
    assert not ch["held"] and not ch["one_off"]
    row = conf_rows(slides)["Verified figures"]
    assert row[1].startswith("1 unusual figure verified against its own filed figures: Micron Technology Inc, net margin 63.8% (net profit "
                             "$84,969 million over revenue $133,188 million, Sep 2026")
    assert row[2] == "Kept in every median and ranking."
    t = texts(slides)
    assert "63.8%†" not in t and "63.8%" in t                 # the appendix shows it, unmarked


# ---------- 2. the synthetic cases: unit mismatch (invalid), missing component (not reconciled), net above EBITDA with other income ----------
def test_a_unit_mismatch_is_invalid():
    # the revenue filed in billions beside a profit in millions: 84,969 on 133.188, a net margin of 63,796%
    f = us(facts("UNIT", "Unit Slip Inc", [120.0, 125.0, 130.0, 133.188], [30.0] * 4, [80.0, 82.0, 84.0, MU_PROFIT], cap=500000))
    r = D.company_row("US", "UNIT", f)
    assert r["net"] is None and r["verify"]["net"]["state"] == D.INVALID and r["held"]["net"]["checks"] == [D.CHECKS["unit_gap"]]
    assert "net profit $84,969 million on revenue $133 million" in r["verify"]["net"]["why"]
    # a year's revenue 1,000 times the year before's: (updated on purpose, R48) no longer invalid, since the margin is the year's own net
    # profit over its own revenue, which a unit change between years doesn't touch; above its EBITDA margin with no stored line to cover
    # it, the 69.2% is not reconciled: shown with †, out of the medians
    g = us(facts("YEAR", "Year Slip Inc", [100.0, 110.0, 120.0, 130000.0], [30.0] * 4, [10.0, 11.0, 12.0, 90000.0], cap=500000))
    r = D.company_row("US", "YEAR", g)
    assert r["net"] == 69.2 and r["one_off"] and r["verify"]["net"]["state"] == D.UNVERIFIED and "net" not in (r.get("held") or {})
    # a margin on revenue of zero or below is impossible
    z = facts("ZERO", "Zero Co", [100, 100, 100, -5], [10, 10, 10, 12], [5, 5, 5, 1])
    r = D.company_row("IN", "ZERO", z)
    assert r["ebitda"] is None and r["verify"]["ebitda"]["state"] == D.INVALID and r["held"]["ebitda"]["checks"] == [D.CHECKS["no_revenue"]]


def test_a_missing_component_leaves_the_figure_not_reconciled_shown_and_out_of_the_median():
    f = chip("MISS", "Missing Part Inc", 70.0)
    for y in f["years"]:
        y["opm"] = None
    f["opm"] = None
    r = D.company_row("US", "MISS", f)
    assert r["net"] == 70.0 and r["one_off"] and D.in_median(r, "net") is None
    assert r["verify"]["net"]["state"] == D.UNVERIFIED and r["verify"]["net"]["why"] == "no EBITDA margin is stored for the year to check it against"
    m = semis_map([{"name": "Missing Part Inc", "ticker": "MISS", "what": "makes memory chips"}])
    v, slides = deck_of("US", m, {**semis_facts(), "MISS": f})
    assert v["layers"][0]["stats"]["net"]["n"] == 5 and v["layers"][0]["net_all"]["n"] == 6
    row = conf_rows(slides)["Net margin not reconciled"]
    assert "Missing Part Inc (70.0% net: no EBITDA margin is stored for the year to check it against)" in row[1]
    assert row[2].startswith("Marked † and left out of net-margin medians")
    assert "70.0%†" in texts(slides)


def realty(sym, name, other):
    """A developer's year: 25% net on a 12% EBITDA margin (₹250 crore of net profit on ₹1,000 crore of revenue, EBITDA ₹120 crore)."""
    f = facts(sym, name, [800, 850, 900, 1000], [12, 12, 12, 12], [60, 65, 70, 250], industry=("Realty",))
    if other is not None:
        f["years"][-1]["other_income"] = other
    return f


def test_net_above_ebitda_explained_by_stored_other_income_is_verified_and_kept():
    ok = D.company_row("IN", "RE1", realty("RE1", "Estate One Ltd", 200))
    assert ok["net"] == 25.0 and not ok["one_off"] and ok["verify"]["net"]["state"] == D.VERIFIED
    assert ok["verify"]["net"]["checks"] == [D.CHECKS["net_above_ebitda"], D.CHECKS["other_income"]]
    assert "above its 12% EBITDA margin by ₹130 crore, covered by income outside operations of ₹200 crore" in ok["verify"]["net"]["why"]
    short = D.company_row("IN", "RE2", realty("RE2", "Estate Two Ltd", 50))
    assert short["one_off"] and short["verify"]["net"]["state"] == D.UNVERIFIED
    assert "income outside operations of ₹50 crore covers part of it" in short["verify"]["net"]["why"]
    none = D.company_row("IN", "RE3", realty("RE3", "Estate Three Ltd", None))
    assert none["one_off"] and "no income outside operations, exceptional gain, tax credit or share of associates is stored" in none["verify"]["net"]["why"]
    # the layer's net median counts the verified one, not the other two; the theme's net margin over time keeps it too
    b = D.layer_block("Developers", [ok, short, none], set())
    assert b["stats"]["net"]["n"] == 1 and b["net_all"]["n"] == 3 and b["one_off"] == ["RE2", "RE3"]
    h = D.layer_history([ok, short, none])
    assert h["net_n"] == 1 and h["one_off"] == ["RE2", "RE3"]


def test_a_margin_beyond_100_percent_is_judged_on_its_own_year_and_its_state_said():
    # an earlier year's margin beyond ±100% no longer blanks the latest year's margins, ROE and EV/EBITDA (stock_pages.extreme)
    f = facts("OLDX", "Old Extreme Ltd", [10, 500, 900, 1000], [-300, 15, 16, 18], [-40, 40, 70, 90])
    r = D.company_row("IN", "OLDX", f)
    assert r["ebitda"] == 18.0 and r["net"] == 9.0 and r["roe"] == 12.0 and "verify" not in r
    hi = D.company_row("IN", "HI", facts("HI", "High Co", [100, 100, 100, 100], [20, 20, 20, 130], [5, 5, 5, 6]))
    # (updated on purpose, R48): above 100% with no operating profit stored to check it, not reconciled ("–" in tables, out of every median);
    # invalid only when the year's stored operating profit over revenue doesn't give it (tests/test_r48_reconcile.py)
    assert hi["ebitda"] is None and hi["verify"]["ebitda"]["state"] == D.UNVERIFIED
    lo = D.company_row("IN", "LO", facts("LO", "Low Co", [100, 100, 100, 100], [20, 20, 20, -250], [5, 5, 5, -300]))
    assert lo["ebitda"] == -250.0 and lo["verify"]["ebitda"]["state"] == D.VERIFIED


# ---------- 3. one record, the same counts everywhere ----------
def test_every_page_counts_the_same_records():
    f = {**semis_facts(), "MISS": chip("MISS", "Missing Part Inc", 70.0), "UNIT": us(facts("UNIT", "Unit Slip Inc", [120.0, 125.0, 130.0, 133.188],
                                                                                          [30.0] * 4, [80.0, 82.0, 84.0, MU_PROFIT], cap=500000))}
    for y in f["MISS"]["years"]:
        y["opm"] = None
    m = semis_map([{"name": "Missing Part Inc", "ticker": "MISS", "what": "makes memory chips"}, {"name": "Unit Slip Inc", "ticker": "UNIT", "what": "makes memory chips"}])
    v, slides = deck_of("US", m, f)
    ch = v["checks"]
    by = {x["symbol"]: x["state"] for x in ch["states"]}
    assert by == {"MU": D.VERIFIED, "MISS": D.UNVERIFIED, "UNIT": D.INVALID}
    assert [x["symbol"] for x in ch["verified"]] == ["MU"] and [x["symbol"] for x in ch["one_off"]] == ["MISS"]
    assert [(x["symbol"], x["state"]) for x in ch["held"]] == [("UNIT", D.INVALID)]
    rows = conf_rows(slides)
    assert rows["Verified figures"][1].startswith("1 unusual figure") and rows["Net margin not reconciled"][1].startswith("1 net margin")
    assert rows["Figure checks"][1].startswith("1 figure failed a check: Unit Slip Inc, net margin") and "(invalid: " in rows["Figure checks"][1]
    t = texts(slides)
    assert t.count("70.0%†") >= 1 and "63.8%†" not in t
    lay = v["layers"][0]
    assert lay["stats"]["net"]["n"] == 5            # Micron and the four chips; not the one not reconciled, not the invalid one


# ---------- 4. coverage: "In informative layers: N of M (P%)", said once ----------
def test_the_coverage_says_the_share_in_informative_layers_once_and_deck_check_reads_it():
    checked = {"value_chain": [{"layer": "Makers", "companies": [{"ticker": "A"}, {"ticker": "B"}, {"ticker": "C"}]},
                               {"layer": "Other x", "official": True, "basis": "rest", "companies": [{"ticker": "D"}, {"ticker": "E", "unread": True}]}]}
    assert D.layer_coverage(checked) == {"informative": 3, "placed": 5, "share": 60, "other": 2, "unread": 1, "other_name": "Other x"}
    v, slides = deck_of("US", semis_map(), semis_facts())
    assert v["coverage"] == {"informative": 5, "placed": 5, "share": 100, "other": 0, "unread": 0, "other_name": ""}
    # tx2 (R46, updated on purpose): with the screening row the coverage table can need a page of its own (d1): read wherever it is
    cov = next(r for s in slides if s.title in ("Data confidence", "Coverage") for b in s.blocks if b["kind"] == "table"
               and b["head"] == deck.COVERAGE_HEAD for r in b["rows"] if r[0] == "In informative layers")
    assert cov[1:] == ["5 of 5 (100%)", "every company in a layer the map names"]
    view = {"members": [{"symbol": s, "layer": "Makers"} for s in "ABC"] + [{"symbol": "D", "layer": "Other x", "rest": True},
                                                                          {"symbol": "E", "layer": "Other x", "rest": True, "unread": True}], "layers": []}
    rows = deck.coverage_table(view, {"total": 5, "n": 5})
    row = next(r for r in rows if r[0] == "In informative layers")
    assert row[1] == "3 of 5 (60%)" and len(re.findall(r"\d+ of \d+", " ".join(row[1:]))) == 1
    assert row[2].startswith("in a layer the map names; the other 2 in “Other x”, listed, never compared: 1 fit none of the map's layers; "
                             "1 not checked yet")
    page = f"In informative layers   {row[1]}   {row[2]}"
    assert deck_check.check_pages([page])["counts"]["other>40%"] == 0            # 2 of 5 outside: 40%, not over it # gl50 (R50, updated on purpose): every company outside informative layers counts, the not checked yet too
    hi = "In informative layers   40 of 100 (40%)   in a layer the map names; the other 60 in “Other”, listed, never compared: 45 fit none of the map's layers; 15 not checked yet"
    got = deck_check.check_pages([hi])
    assert got["counts"]["other>40%"] == 1 and "In informative layers 40 of 100 (40%); 60 outside them (60%)" in got["findings"][0]["text"]          # gl50 (R50, updated on purpose): every company outside informative layers counts, the not checked yet too


def test_the_dive_and_the_deck_take_the_coverage_of_the_whole_map():
    m = {"sector": "Pumps", "value_chain": [{"layer": "Makers", "companies": [{"ticker": "A"}, {"ticker": "B"}]},
                                            {"layer": "Other pump companies", "official": True, "basis": "rest", "companies": [{"ticker": "C"}]}],
         "sub_themes": [{"name": "S", "companies": [{"ticker": "D", "name": "D Co"}]}]}
    want = {"informative": 2, "placed": 4, "share": 50, "other": 2, "unread": 0, "other_name": "Other pump companies"}
    assert T.map_coverage(m) == want and T.deck_view("IN", m, {})["coverage"] == want      # a sub-theme-only company is in "Other" (d1)


def test_deck_check_reads_the_count_when_its_cell_wraps_around_the_label():
    def page(fit):
        return ("                                                         in a layer the map names; the other 115 in “Other”, listed, never "
                f"compared: {fit} fit none of the map's\n                               137 of 252\n"
                f" In informative layers                                   layers; {115 - fit} not checked yet\n                               (54%)\n")
    # gl50 (R50, updated on purpose): every company outside informative layers counts, the not checked yet too: 115 of 252 outside is 46%, whatever the split
    for fit in (60, 110):
        got = deck_check.check_pages([page(fit)])
        assert got["counts"]["other>40%"] == 1 and "In informative layers 137 of 252 (54%); 115 outside them (46%)" in got["findings"][0]["text"]


# ---------- R44.1: the reasons print a loss with the real minus, as every other figure in the deck (the live R44 decks: "-81.4%") ----------
def test_a_verified_loss_is_said_with_the_real_minus_in_its_reason_and_in_the_deck():
    loss = chip("LOSS", "Loss Chip Inc", -81.4, ebitda=-43.0)
    deep = chip("DEEP", "Deep Loss Inc", -300.0, ebitda=-250.0)
    r, d = D.company_row("US", "LOSS", loss), D.company_row("US", "DEEP", deep)
    assert r["verify"]["net"]["state"] == D.VERIFIED and d["verify"]["ebitda"]["state"] == D.VERIFIED
    assert r["verify"]["net"]["why"].endswith("Sep 2026: −81.4%; at or below its −43% EBITDA margin")
    assert d["verify"]["ebitda"]["why"] == "a loss at both levels, −250% EBITDA and −300.0% net, Sep 2026"
    extra = [{"name": "Loss Chip Inc", "ticker": "LOSS", "what": "makes memory chips"},
             {"name": "Deep Loss Inc", "ticker": "DEEP", "what": "makes memory chips"}]
    f = semis_facts() | {"LOSS": loss, "DEEP": deep}
    v, slides = deck_of("US", semis_map(extra), f)
    row = conf_rows(slides)["Verified figures"]
    assert "−81.4%" in row[1] and not re.search(r"(?<![\w.])-\d", row[1])
    assert deck_check.check_pages([texts(slides)])["counts"]["hyphen minus"] == 0
