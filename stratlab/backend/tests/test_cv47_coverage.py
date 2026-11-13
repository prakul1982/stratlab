"""Lane cv47 (Release 47, the live Release 46 decks): Utilities and Consumer retail coverage, on the live Release 46 placement inputs.

The inputs are what GET /research/theme-dive/placement-inputs returned on 13 Nov 2026 under Release 46 (RULES 45), with each company's
stored facts and the previous live layers (tests/fixtures/themes_live/inputs_r46/<theme>.json). Under RULES 45 both replay exactly: every
company has its live layer.

1. Utilities (78 of 114 in informative layers on live): the cable and electrical equipment makers' layers (c1, R44, from_other 3) formed on
   every replay without the companies' facts and never on live. The facts carry the titles of each company's filings ("From its own filings:
   Analysts/Institutional Investor Meet..."), and own_text counted them as the company's own words: their "own" said the name "Makers of
   their own products", so KEI (and BBL) read as placed in that layer by their words, sat "elsewhere" with words of their way of earning, and
   no layer of their industry formed. RULES 46: filing titles are no words of its own (own_text, no_words).
2. Consumer retail (58 of 98): no placement differs from the live one. The bump to RULES 45 asked the AI's industry pick again, as a pick kept
   under older rules was; the new pick has "Retail Stores, Nec" (22 members, 15 of them in "Other") in place of "Family Clothing
   Stores" (8 apparel chains, every one in a layer, and the layer that also took three chains by their words). A pick kept under PICK_RULES
   or later rules is now kept, so a change of the placement rules never redraws a theme's universe."""
import json
import pathlib

from app.intel import theme_base as B
from tests import test_exact_replay as X
from tests import test_tx2_taxonomy as T

R46 = pathlib.Path(__file__).parent / "fixtures" / "themes_live" / "inputs_r46"
CABLES, EQUIPMENT, MAKERS = "Electrical cables", "Heavy electrical equipment", "Makers of their own products"


def r46(key: str) -> dict:
    d = json.loads((R46 / f"{key}.json").read_text())
    return d.get("data", d)


def replay46(key: str) -> dict:
    """The live Release 46 placement placed again from its inputs as theme_routes.placed fed them: the map, the kept answer (carried when
    kept under earlier rules), each company's stored description and facts, and the previous live layers; no AI."""
    d = r46(key)
    m = X.pre_map(d, X.RECOVERED["origin"].get(key), X.RECOVERED["description"].get(key))
    out, _ = B.place_rest(m, d["theme"], lambda s: d["evidence"].get(s), ask=None, kept=d["kept"], facts_of=lambda s: d["facts"].get(s) or {},
                          carried=d["kept_version"] != B.RULES, previous=d["previous"])
    return out


def shown(vc) -> dict:
    return {c["ticker"]: ("Other" if v.get("official") else X._HALF.sub("", v["layer"])) for v in vc for c in v["companies"]}


def informative(layers: dict) -> int:
    return sum(1 for x in layers.values() if x != "Other")


def test_filing_titles_are_no_words_of_the_company_s_own():
    """Fails on RULES 45: "From its own filings: ..." was read as the company's words, its "own" saying "Makers of their own products"."""
    tw = B.kind_stems("Utilities")
    titles = "Industry: Cables - Electricals. From its own filings: Board meeting: Outcome. Order or contract: Award of Order."
    assert B.own_text(titles) == "" and B.no_words(titles)
    assert not B.name_says(MAKERS, B.own_text(titles), tw)[1]
    assert not B.name_says("Engineering and construction contracts", B.own_text(titles), tw)[1]
    words = "Industry: Cables - Electricals. The company manufactures wires and cables. From its own filings: Earnings call: Con. Call Updates."
    assert B.own_text(words) == "The company manufactures wires and cables." and not B.no_words(words)
    assert B.own_text("Industry: Zinc. Makers of zinc.") == "Makers of zinc."          # no filing titles: the words as they were
    assert B.no_words("") and B.no_words("Industry: Zinc.")


def test_utilities_cable_and_electrical_equipment_layers_form_on_the_live_release_46_inputs():
    """Fails on RULES 45: the replay was the live map (43 in "Makers of their own products", 36 in "Other"). Now c1's two layers of one
    official industry form, exactly the companies test_exact_replay approves for them, and 91 of 114 are in informative layers."""
    d = r46("utilities")
    live, now = shown(d["value_chain"]), shown(replay46("utilities")["value_chain"])
    assert informative(live) == 78 and len(live) == 114
    assert sum(1 for x in now.values() if x == CABLES) == 18 and sum(1 for x in now.values() if x == EQUIPMENT) == 34
    assert sum(1 for x in now.values() if x == "Other") == 23 and informative(now) == 91
    moved = {s_: now[s_] for s_ in live if now[s_] != live[s_]}
    assert len(moved) == 52
    for s_, layer in moved.items():                        # every move is one c1's exact replay approves, with its reason
        assert X.APPROVED[f"utilities:{s_}"][0] == layer, s_
    assert {live[s_] for s_ in moved} == {MAKERS, "Other"}
    assert set(now) == set(live)                           # nobody leaves the theme


def test_every_utilities_move_carries_evidence_against_the_previous_live_layer():
    """tx2's guard: every company whose layer changes against the live Release 46 placement has its official industry (or its own words)
    for its new layer: here a layer made of its official industry and named by it."""
    d = r46("utilities")
    out = replay46("utilities")
    assert T.unexplained(d["value_chain"], out["value_chain"], d["evidence"], d["theme"], T.backs(d["kept"])) == {}
    groups = [v for v in out["value_chain"] if v.get("industry_group")]
    assert sorted(v["layer"] for v in groups) == [CABLES, EQUIPMENT]
    for v in groups:                                       # one official industry each
        assert len({B.key(c.get("industry")) for c in v["companies"]}) == 1, v["layer"]


def test_consumer_retail_replays_exactly_on_the_live_release_46_inputs():
    """The placement rules change moves no retailer: the coverage gap is the universe, not the placement (58 of 98 on live and here)."""
    d = r46("retail")
    live, now = shown(d["value_chain"]), shown(replay46("retail")["value_chain"])
    assert now == live and informative(now) == 58 and len(now) == 98
    p = d["placements"]
    assert "Retail-Retail Stores, Nec" in p["industries"] and "Retail-Family Clothing Stores" not in p["industries"]
    nec = [c["ticker"] for v in d["value_chain"] for c in v["companies"] if c.get("industry") == "Retail-Retail Stores, Nec"]
    assert len(nec) == 22 and sum(1 for s_ in nec if live[s_] == "Other") == 15


def _pick(stored: dict, asked: list) -> dict:
    return B.industries_for("US", "Consumer retail", [{"symbol": "A", "industry": "Retail-Family Clothing Stores"},
                                                       {"symbol": "B", "industry": "Retail-Retail Stores, Nec"}],
                            lambda s, t: asked.append(1) or {"industries": ["Retail-Retail Stores, Nec"]}, stored.get, stored.__setitem__)


def test_an_industry_pick_kept_under_earlier_rules_is_kept_when_the_pick_itself_has_not_changed():
    """Fails on RULES 45: a pick kept under the rules before was asked again (the live Release 46 Consumer retail pick)."""
    assert B.PICK_RULES < B.RULES
    key = "theme:industries:US:consumer-retail"
    from datetime import datetime, timezone
    at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    stored = {key: json.dumps({"at": at, "industries": ["Retail-Family Clothing Stores"], "rules": B.PICK_RULES})}
    asked: list = []
    assert _pick(stored, asked)["industries"] == ["Retail-Family Clothing Stores"] and asked == []
    # one kept under rules older than PICK_RULES, or under rules later than these (a rollback), is made again
    for rules in (B.PICK_RULES - 1, B.RULES + 1):
        stored = {key: json.dumps({"at": at, "industries": ["Retail-Family Clothing Stores"], "rules": rules})}
        asked = []
        assert _pick(stored, asked)["industries"] == ["Retail-Retail Stores, Nec"] and asked == [1]
        assert json.loads(stored[key])["rules"] == B.RULES
