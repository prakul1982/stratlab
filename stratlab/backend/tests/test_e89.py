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
