"""Lane r68e (R68 deck engine): the owner's GPT review of the live R66 decks (vs R65).

P0-1 the core vs adjacent financial population is stable: the live R66 Payments deck folded its card issuers, consumer lenders and digital
     banks into the core figures (16 -> 21 with figures, 64% -> 100% of the value, P/E n 13 -> 18) because the re-check job worked the dive
     out under the theme library's normalised name ("payment and financial technology"), whose "financ" made lenders the theme's own kind.
     The rules now read the map's own name (theme_data.theme_name), the split is versioned (theme_data.POPULATION) and every company that
     joins or leaves the core members against the stored read before is named with why (theme_changes.population_change, the deck's
     "Core and adjacent" row).
"""
import pathlib
import sys

from app import deck
from app.intel import theme_changes as C
from app.intel import theme_data as D
from app.intel import theme_library as L
from tests import test_c54_fixes as K

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import deck_check  # noqa: E402


def payments_deck(theme: str):
    """The live R53 Payments placement replayed (test_c54_fixes) and built into a deck with the dive worked out under `theme`."""
    from tests.test_export import texts
    from tests.test_r18_deck import deck_of
    from tests.test_r48_reconcile import co
    d = K.inputs("payments")
    out = K.replay("payments")
    f = {}
    for li, v in enumerate(out["value_chain"]):
        for i, c in enumerate(v["companies"]):
            sales = 1000.0 + 37 * i
            f[c["ticker"]] = co(c["ticker"], c.get("name") or c["ticker"], sales, 6.0 + 3.3 * (li % 7), sales * 0.05)
    m = {**out, "sector": d["theme"], "sub_themes": out.get("sub_themes") or []}
    v, slides = deck_of(d["region"], m, f, theme=theme, about=d["evidence"].get)
    return v, "\f".join(texts([s]) for s in slides)


# ---------- P0-1 the core vs adjacent population ----------
def test_the_core_and_adjacent_split_is_the_same_whichever_search_reached_the_stored_map():
    """Fails before: worked out under the library's name for the theme ("payment and financial technology", as the re-check job does),
    the Payments dive had no adjacent participant: the card lenders and the digital bank counted as core members, and the deck named
    "Card issuers…" with no "Core and adjacent" row (deck_check's "scope core" on the live R66 deck). Now the split is the page's."""
    name = L.normalise("Payments and fintech", "US")
    assert "financ" in name
    v_page, _ = payments_deck("Payments and fintech")
    v_lib, text = payments_deck(name)
    page = {x["symbol"]: x["kind"] for x in v_page["adjacent"]}
    assert {"SYF", "AFRM", "DAVE"} <= set(page)
    assert {x["symbol"]: x["kind"] for x in v_lib["adjacent"]} == page
    assert v_lib["with_figures"] == v_page["with_figures"] and v_lib["sections"]["medians"] == v_page["sections"]["medians"]
    assert "Core and adjacent" in text and not deck_check.check_text(text)["counts"]["scope core"]
    assert v_lib["population_rule"] == D.POPULATION and D.POPULATION_RULE[D.POPULATION]


def test_theme_name_is_the_maps_own():
    assert D.theme_name("payment and financial technology", {"sector": "Payments and fintech"}) == "Payments and fintech"
    assert D.theme_name("fintech", {"sector": ""}) == "fintech"
    assert D.theme_name("x", None) == "x"


def _dive(adjacent: list, rule: int | None = None, extra: dict | None = None) -> dict:
    rule = getattr(D, "POPULATION", 1) if rule is None else rule
    cos = [{"symbol": s_, "name": n_, "revenue": 100.0, "ebitda": 10.0, "year": "Dec 2025", "official_industry": ind}
           for s_, n_, ind in (("COF", "Capital One Financial Corp", "Commercial banks"), ("SYF", "Synchrony Financial", "Finance Services"),
                               ("V", "Visa Inc", "Business services"))]
    for c in cos:
        c.update((extra or {}).get(c["symbol"], {}))
    by = {x[0]: x for x in adjacent}
    return {"layers": [{"layer": "Card issuers and consumer lenders", "companies": cos[:2]}, {"layer": "Card networks", "companies": cos[2:]}],
            "adjacent": [{"symbol": s_, "name": next(c["name"] for c in cos if c["symbol"] == s_), "kind": "lenders and financiers",
                          "where": "industry", "text": next(c["official_industry"] for c in cos if c["symbol"] == s_)} for s_ in by],
            "population_rule": rule}


def test_each_company_joining_or_leaving_the_core_members_is_named_with_why():
    """Fails before: R66's 16 -> 21 core members with figures named no company. Now, against the stored read before, each company that left
    the core members (now adjacent) or joined them (adjacent before) is named with its reason, and a change of the rules' version is said."""
    before = C.snapshot(_dive([("COF",), ("SYF",)]))
    assert before["pop"] == D.POPULATION and before["adj"] == {"COF": "lenders and financiers", "SYF": "lenders and financiers"}
    now = _dive([("COF",)], extra={"SYF": {"core_kept": "it runs several businesses, one of them the theme's: card payments"}})
    pc = C.population_change(before, now)
    assert pc["left"] == [] and [x["symbol"] for x in pc["joined"]] == ["SYF"] and "card payments" in pc["joined"][0]["why"]
    pc = C.population_change(C.snapshot(_dive([])), _dive([("COF",), ("SYF",)]))
    assert [x["symbol"] for x in pc["left"]] == ["COF", "SYF"] and "“Commercial banks”" in pc["left"][0]["why"] and "rule" not in pc
    pc = C.population_change(C.snapshot(_dive([("COF",)], rule=D.POPULATION - 1)), _dive([]))
    assert pc["rule"] == [D.POPULATION - 1, D.POPULATION] and "rules changed" in pc["joined"][0]["why"]
    assert "its official industry (Commercial banks)" in pc["joined"][0]["why"]
    # nothing moved, or a stored read of an older engine that keeps no split: nothing said
    assert C.population_change(C.snapshot(_dive([("COF",)])), _dive([("COF",)])) is None
    old = {k: v for k, v in C.snapshot(_dive([])).items() if k not in ("pop", "adj")}
    assert C.population_change(old, _dive([("COF",)])) is None
    # a read stored again unchanged keeps the change said (the split before the last change, as the coverage's "cover_was")
    log = C.apply(C.apply(None, C.snapshot(_dive([("COF",), ("SYF",)]))), C.snapshot(_dive([])))
    log = C.apply(log, C.snapshot(_dive([])))
    assert [x["symbol"] for x in C.population_change(log["snap"], _dive([]))["joined"]] == ["COF", "SYF"]


def test_the_deck_names_the_companies_that_joined_or_left_the_core_members():
    v = {"adjacent": [], "core_kind": "", "population_change": {"left": [], "joined": [
        {"symbol": "COF", "name": "Capital One Financial Corp", "was": "lenders and financiers", "why": "its official industry (Commercial banks) ..."}]}}
    row = deck.adjacent_row(v)
    assert row[0] == "Core and adjacent" and "Capital One Financial Corp (its official industry (Commercial banks)" in row[1]
    assert "1 company joined the core members against the previous stored version" in row[1]
    v = {"adjacent": [{"symbol": "COF", "name": "Capital One Financial Corp", "kind": "lenders and financiers"}],
         "population_change": {"left": [{"symbol": "COF", "name": "Capital One Financial Corp", "kind": "lenders and financiers",
                                         "why": "its principal business (its official industry, “Commercial banks”) is of lenders and financiers"}],
                               "joined": []}}
    row = deck.adjacent_row(v)
    assert "lenders and financiers 1 (Capital One Financial Corp)" in row[1] and "1 company left the core members" in row[1]
    assert deck.population_said(None) == ""
