"""Lane e89 (Release 89 engine): theme map hygiene from the owner's Alcoholic beverages deck (25 Nov) and the open engine items. Each test fails
on Release 88 (origin/main c5cce2b) and passes after, except those marked as guards. The companies' words and figures are the live ones of
the Alcoholic beverages dive read on 25 Nov 2026 (GET /research/theme-dive, region IN)."""
from app import main  # noqa: F401, I001  (main first: it loads the modules in the order they need)
from app.intel import theme_base as B
from app.intel import theme_data as D

BOROSIL = ("Borosil Renewables is engaged in manufacturing extra clear patterned glass and Low Iron Solar Glass for application in Photovoltaic "
           "panels, Flat plate collectors and Greenhouses")
AGI = ("Incorporated in 1960, AGI Greenpac Ltd manufactures and sells Container Glass bottles, PET bottles and Security Caps and Closures under "
       "Packaging Products.")


def _alco_vc() -> list[dict]:
    """The live Alcoholic beverages map's layers (17 Nov 2026), its "Other" group last."""
    return [{"layer": "Glass bottle and packaging manufacturing", "companies": [{"ticker": "AGI", "name": "AGI Greenpac Limited"}]},
            {"layer": "Grain distilling and extra neutral alcohol", "companies": [{"ticker": "GLOBUSSPR", "name": "Globus Spirits Limited"}]},
            {"layer": "Spirits brand owning and bottling (larger)", "companies": [{"ticker": "UNITDSPR", "name": "United Spirits Limited"}]},
            {"layer": "Beer brewing and sale", "companies": [{"ticker": "UBL", "name": "United Breweries Limited"}]},
            {"layer": "Wine making and sales", "companies": [{"ticker": "SULA", "name": "Sula Vineyards Limited"}]},
            {"layer": "Other alcoholic beverage companies", "official": True, "basis": "rest", "companies": []}]


# ---------- 1. Off-theme companies: one shared word of another trade keeps no company in the theme ----------
def test_a_solar_glass_maker_is_not_kept_in_the_theme_on_glass_and_extra():
    """Fails on R88: Borosil Renewables (solar glass, filed under Glass - Industrial), left out by the map's check for "Packaging inputs: glass
    bottles", was kept in "Other alcoholic beverage companies" as description-verified on "glass" (the bottle layer's) and "extra" (of "extra
    neutral alcohol"), its 28% margin in the Other group's medians."""
    pl = {"dropped": [{"ticker": "BORORENEW", "name": "Borosil Renewables Limited", "groups": ["Packaging inputs: glass bottles"], "said": "no"}]}
    vc, got = B.layer_answer_removals(_alco_vc(), pl, lambda s: BOROSIL, "Alcoholic beverages", lambda s: {"industry": "Glass - Industrial"})
    assert "BORORENEW" not in {c["ticker"] for v in vc for c in v["companies"]}
    assert [(x["ticker"], x["said"]) for x in got["dropped"]] == [("BORORENEW", "scope")]
    assert got["dropped"][0]["scope"].startswith("another business: its own words say “Borosil Renewables is engaged in manufacturing extra clear")
    assert not got.get("layer_no")
    assert B.layer_work_stems(B.kind_stems(B.own_text(BOROSIL)), _alco_vc(), "Alcoholic beverages") == set()


def test_guard_words_that_say_a_layers_work_or_the_theme_still_keep_a_company():
    """Guard: a glass-bottle maker's words ("Container Glass bottles") say the bottle layer's work, and words naming the theme ("alcoholic
    beverages") or two words of a layer ("extra neutral alcohol") keep a company against one layer's answer, quoted."""
    words = {"G": AGI, "A": "Ace Ltd makes alcoholic beverages for the domestic market.", "E": "Eno Ltd produces extra neutral alcohol from grain."}
    pl = {"dropped": [{"ticker": t, "name": t, "groups": ["Packaging inputs: glass bottles"], "said": "no"} for t in words]}
    vc, got = B.layer_answer_removals(_alco_vc(), pl, words.get, "Alcoholic beverages", lambda s: {})
    other = {c["ticker"]: c for c in vc[-1]["companies"]}
    assert set(other) == {"G", "A", "E"} and not got.get("dropped")
    assert "Container Glass bottles" in other["G"]["theme"]["why"] and "alcoholic beverages" in other["A"]["theme"]["why"]


# ---------- 6a. Semiconductors' missing own words: the annual-report reader finds Item 1 where it missed it ----------
def _openings() -> dict:
    import json
    import pathlib
    return json.loads((pathlib.Path(__file__).parent / "fixtures" / "sec_openings_e89.json").read_text())


def test_the_annual_report_reader_finds_the_opening_of_item_1_in_five_flagship_reports():
    """Fails on R88: Skyworks' and MACOM's contents pages print "ITEM 1A: RISK FACTORS." (a colon), so the contents page's Item 1 ran on and
    their cautionary notes were read as what they do; Intel's and McDonald's 10-Ks, set out of the form's order, gave nothing; Arm's 20-F
    gave "In today’s technology-driven world, semiconductors are ...". The texts are the reports' own lines (sec.report_lines) around the
    parts read, from their latest annual reports on the SEC's site (read 25 Nov 2026)."""
    from app.intel import sec
    got = {k: sec.business_opening(v) for k, v in _openings().items()}
    assert got["SWKS"].startswith("Skyworks Solutions, Inc., together with its consolidated subsidiaries")
    assert got["MTSI"].startswith("We design, develop and manufacture differentiated radio frequency")
    assert got["INTC"].startswith("We are a global designer and manufacturer of semiconductor products.")
    assert got["MCD"].startswith("The Company franchises and owns and operates McDonald’s restaurants")
    assert got["ARM"].startswith("The Company is a global leader in the semiconductor industry.")
    for k, v in got.items():
        assert B.has_own_line(B.quotable(v, "US") or ""), k          # each a line a page may quote about its work


def test_a_record_read_by_the_old_reader_with_no_line_to_quote_is_read_once_more():
    """Fails on R88: Intel's record, read under QUOTE_V 1 by a reader that found no opening, was marked read (qv 1) and never asked again, so
    it stayed "industry-supported (official industry only)"; the reads kept a month (sec.BUSINESS_KEY) are the new reader's too."""
    from datetime import datetime, timezone
    from app.intel import sec
    from app.intel import theme_routes as TR
    old = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "op": TR.OWN_PART_V, "v": TR.ABOUT_V, "bv": 5, "qv": 1,
           "about": "Intel Corporation is an American multinational technology company headquartered in Santa Clara, California.", "industry": ""}
    assert TR.quote_due(old, "US", "Intel Corp") and TR.thin_about(old, "US", "Intel Corp")
    assert not TR.quote_due({**old, "qv": TR.QUOTE_V}, "US", "Intel Corp")          # guard: read once by this reader, not again
    assert sec.BUSINESS_KEY[1] == 6 and TR.QUOTE_V == 2          # (changed on purpose, e89)
