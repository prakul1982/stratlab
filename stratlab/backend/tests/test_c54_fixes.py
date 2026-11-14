"""Lane c54 (Release 53 review, the owner's review of the live R53 decks): classification semantics and taxonomy stability, proven on exact
replays of the live R53 placement inputs (GET /research/theme-dive/placement-inputs, read 14 Nov 2026 under RULES 52 with kept version 52:
tests/fixtures/themes_live/inputs_r53/<theme>.json; the moves each theme's stored change log recorded on its last re-check, as the live
decks print them, in inputs_r53/moved.json).

1 P0 a company joins a layer by how it earns only on evidence that it sells what the layer's name defines (theme_base.sells_layer, sold_what):
  Intel (chips) is no chip-equipment maker, Indo National (batteries, torches) no packaged-foods maker, UFP Technologies (contract
  manufacturing, components, packaging) no surgical-robotics maker; the golden replays move no company (test_exact_replay, the golden tests).
2 P0 lenders, contractors, laboratories and primary producers are adjacent participants of a theme whose name doesn't state them
  (theme_data.SCOPE_KINDS): Bajaj Finance in Automotive, the card lenders in Payments, the tea growers' layer in FMCG.
3 P1 a named layer of five or more companies the previous version had comes back when a re-check would lose it (restore_vanished: Metals'
  "Aluminium", 14 companies), and the change log says where a lost layer's companies went and why.
4 P1 a member with no stored figures stays in its layer, "figures not available"; a symbol merged as the same company is said so in the log.
5 one company's figures under two symbols whose stored description names the other (Novartis India / Evonile Pharma) are kept once.
"""
import json
import pathlib
import re
import sys

import pytest

from app.intel import theme_base as B
from app.intel import theme_changes as C
from app.intel import theme_data as D
from tests import test_exact_replay as X

LIVE = pathlib.Path(__file__).parent / "fixtures" / "themes_live" / "inputs_r53"
MOVED = json.loads((LIVE / "moved.json").read_text())
# the map layer each map pick the split moved was named in (the one whose replay gives every company its live layer; test_exact_replay's way)
ORIGIN = {"semis": {"MU": "Design software and IP licensing"}, "metals": {"JSL": "Specialty steel and fabricated steel products"},
          "payments": {"FLYW": "Card networks"}}
STALE = ("out_why", "on_industry", "refit", "own_goods", "by_words", "unfit", "sold_by")
EQUIP, MAKERS = "Chip equipment and subsystem suppliers", "Makers of their own products"
FOODS, ROBOTS = "Branded packaged foods manufacturing", "Surgical robotics systems"
ALUMINIUM = ["ARFIN", "MAANALU", "MANAKALUCO", "HINDALUMI", "MMP", "BMAL", "JIVIAL", "KANISHK", "MAITRI", "MSAFE", "PALCO", "PGFOILQ", "SACHEMT",
             "SUDAI"]                 # the 14 companies of "Aluminium" on the live R52 Metals deck (its R53 change log names where each went)
_CACHE: dict = {}

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import deck_check  # noqa: E402


def inputs(key: str) -> dict:
    if key not in _CACHE:
        d = json.loads((LIVE / f"{key}.json").read_text())
        d = d.get("data", d)
        for v in d["value_chain"]:
            v["companies"] = [{k: x for k, x in c.items() if k not in STALE} for c in v["companies"]]
        _CACHE[key] = d
    return json.loads(json.dumps(_CACHE[key]))


def replay(key: str, moved: bool = True, previous: dict | None = None) -> dict:
    """The live R53 placement placed again from its live inputs, as theme_routes.placed feeds it (no AI), with the stored change log's moves."""
    d = inputs(key)
    m = X.pre_map(d, ORIGIN.get(key, {}), {})
    out, _ = B.place_rest(m, d["theme"], lambda s: d["evidence"].get(s), ask=None, kept=d["kept"], facts_of=lambda s: d["facts"].get(s) or {},
                          carried=d["kept_version"] != B.RULES, previous=d["previous"] if previous is None else previous,
                          off_before=d.get("off_before") or {}, moved_before=MOVED.get(key, {}) if moved else {})
    return out


def layers(vc) -> dict:
    return {c["ticker"]: ("Other" if v.get("official") else X._HALF.sub("", v["layer"])) for v in vc for c in v["companies"]}


def live(key: str) -> dict:
    return layers(inputs(key)["value_chain"])


def row(out, sym):
    return next(c for v in out["value_chain"] for c in v["companies"] if c["ticker"] == sym)


# ---------- 1 P0 the layer-definition test ----------
def test_intel_and_the_other_makers_are_back_with_the_makers_on_the_live_r53_semiconductors_inputs():
    """Fails before: the live R53 deck (p.6/8/14) had Intel, $52.9 bn of revenue, a third of "Chip equipment and subsystem suppliers", moved by
    the re-check from "Makers of their own products" with Applied Optoelectronics, Netlist, nLight and SemiLEDs, joined on two words their
    descriptions share with the layer's prose ("chip", "components"). Now none of them joins: no words of theirs say chip equipment or
    subsystems (a subsystem only with the equipment it is part of), so each is back with the makers, with the reason. Every other company of
    the theme keeps its live layer."""
    want = live("semis")
    assert all(want[s] == EQUIP for s in ("INTC", "AAOI", "NLST", "LASR", "LEDS"))
    out = replay("semis")
    got = layers(out["value_chain"])
    for s_ in ("INTC", "AAOI", "NLST", "LASR", "LEDS"):
        assert got[s_] == MAKERS, s_
        r = row(out, s_)["refit"]
        assert r["from"] == EQUIP and r["to"] == MAKERS and "don't say it sells what “Chip equipment and subsystem suppliers” is" in r["why"]
    assert {s for s in want if got.get(s) != want[s]} == {"INTC", "AAOI", "NLST", "LASR", "LEDS"}
    # the equipment makers whose words say it stay: KLA "makes wafer fab equipment"
    assert got["KLAC"] == EQUIP and got["AMAT"] == EQUIP


def test_battery_and_home_care_makers_leave_packaged_foods_on_the_live_r53_fmcg_inputs():
    """Fails before: Indo National ("manufactures and markets batteries, torches, LED products ...") and Jyothy Labs (household and personal
    care), moved by the re-check from "Other" into "Branded packaged foods manufacturing" (live deck p.6/37). Neither says it sells food: both
    back in "Other" with the reason; Adani Wilmar (AWL), moved into it the same day, sells foods and stays."""
    assert live("fmcg")["NIPPOBATRY"] == FOODS
    out = replay("fmcg")
    got = layers(out["value_chain"])
    assert got["NIPPOBATRY"] == "Other" and got["JYOTHYLAB"] == "Other" and got["AWL"] == FOODS
    assert "(“foods”)" in row(out, "NIPPOBATRY")["refit"]["why"]
    assert "sells what" in row(out, "AWL")["sold_by"]          # new to the layer, with what shows it


def test_ufp_technologies_is_not_a_surgical_robotics_maker_on_the_live_r53_medical_devices_inputs():
    """Fails before: UFP Technologies, a contract and components maker, newly in "Surgical robotics systems" (live deck p.4-5/8/16). Now in
    "Other", its words saying no robotics; no other company moves."""
    want = live("meddev")
    out = replay("meddev")
    got = layers(out["value_chain"])
    assert want["UFPT"] == ROBOTS and got["UFPT"] == "Other"
    assert {s for s in want if got.get(s) != want[s]} == {"UFPT"}
    assert "“robotics”" in row(out, "UFPT")["refit"]["why"]


def test_without_a_move_to_judge_the_live_placement_stands():
    """The check reads only companies new to a layer: without the stored log's moves (and with the previous version that already holds
    them), the live R53 Semiconductors and Medical devices placements are replayed exactly, every company in its live layer."""
    for key in ("semis", "meddev"):
        assert layers(replay(key, moved=False)["value_chain"]) == live(key), key


def test_what_a_layer_sells_is_read_in_a_company_s_own_words_of_what_it_sells():
    equip = {"layer": EQUIP, "description": "These companies build the lithography, etch, deposition, inspection and test machines that fabs and "
                                             "test houses use, plus the subsystems and components that go into those tools."}
    tw = B.kind_stems("Semiconductors")
    said = lambda t, v=equip, ind="", model="": B.sells_layer(v, [v], B.sold_text(t), ind, tw, model)      # noqa: E731
    assert said("Intel Corporation is an American multinational technology company. It designs, manufactures, and sells computer components "
                "such as central processing units (CPUs) and related products.") is False
    assert said("KLA Corporation is an American company that makes wafer fab equipment. It supplies process control systems.") is True
    assert said("Netlist designs and sells high-performance SSDs and modular memory subsystems to enterprise customers.") is False
    assert said("We design and manufacture optical communications products, from components and modules to complete turn-key equipment.") is False
    assert said("The company manufactures testing equipment used in semiconductor test houses.") is True
    foods = {"layer": FOODS, "description": "These companies make biscuits, noodles, snacks and dairy in their own plants and sell under brands."}
    tw = B.kind_stems("FMCG")
    assert B.sells_layer(foods, [foods], B.sold_text("Indo National manufactures and markets batteries, torches, LED products and razors."),
                         "Household Products", tw) is False
    assert B.sells_layer(foods, [foods], B.sold_text("Britannia is one of India's leading food companies."), "", tw) is True
    assert B.sells_layer(foods, [foods], "", "Packaged Foods", tw) is True               # its official industry names the layer's product
    # a layer selling the theme's own product only qualified ("Specialty and performance chemicals" in Chemicals) is not judged
    assert B.sells_layer({"layer": "Specialty and performance chemicals"}, [], "pesticides", "", B.kind_stems("Chemicals")) is None
    # a name stating the way of earning the company's evidence shows
    assert B.sells_layer({"layer": "Fabless chip design"}, [], "makes graphics processors", "", B.kind_stems("Semiconductors"), "fabless") is True


# ---------- 2 P0 scope boundaries ----------
def deck(key: str, **kw):
    from tests.test_export import texts
    from tests.test_r18_deck import deck_of
    from tests.test_r48_reconcile import co
    d = inputs(key)
    out = replay(key, **kw)
    f = {}
    for li, v in enumerate(out["value_chain"]):
        base = 6.0 + 3.3 * (li % 7)
        for i, c in enumerate(v["companies"]):
            sales = 1000.0 + 37 * i
            f[c["ticker"]] = co(c["ticker"], c.get("name") or c["ticker"], sales, base + (i % 3) - 1, sales * (base - 4) / 100)
    v, slides = deck_of(d["region"], {**out, "sector": d["theme"], "sub_themes": out.get("sub_themes") or []}, f, theme=d["theme"],
                        about=d["evidence"].get)
    return v, "\f".join(texts([s]) for s in slides)


def test_the_vehicle_financiers_are_adjacent_in_the_automotive_theme_on_the_live_r53_inputs():
    """Fails before: Bajaj Finance, a diversified lender (NBFC), the largest company of the live Automotive deck's market-value table at
    14.7% as a "vehicle financier", counted among its core members. Now the three lenders are adjacent participants, their layer an adjacent
    layer (shown, never ranked, in no theme total), and the theme's size is of its core members."""
    v, text = deck("auto")
    adj = {x["symbol"]: x for x in v["adjacent"]}
    assert set(adj) == {"BAJFINANCE", "SHRIRAMFIN", "M&MFIN"} and adj["BAJFINANCE"]["kind"] == "lenders and financiers"
    assert next(b for b in v["layers"] if b["layer"] == "Vehicle financiers")["adjacent"]["kind"] == "lenders and financiers"
    assert "183 core members (the 3 adjacent participants apart)" in text and "Core and adjacent" in text
    assert not deck_check.check_text(text)["counts"]["scope core"]


def test_card_lenders_and_digital_banks_are_adjacent_in_payments_and_the_tea_growers_in_fmcg():
    v, _ = deck("payments")
    assert {x["symbol"] for x in v["adjacent"]} == {"AXP", "COF", "SYF", "AFRM", "DAVE"}         # Coinbase, an exchange, is not a lender
    v, _ = deck("fmcg")
    assert {x["layer"] for x in v["adjacent"]} == {"Mining, oil, gas and farming"}
    assert next(b for b in v["layers"] if b["layer"] == "Mining, oil, gas and farming")["adjacent"]["kind"] == "miners, drillers and growers"


def test_a_scope_kind_is_core_where_the_theme_names_it():
    nbfc = {"industry": "Non Banking Financial Company (NBFC)"}
    assert D.scope_adjacent(nbfc, "Automotive")["kind"] == "lenders and financiers"
    assert D.scope_adjacent(nbfc, "Private banks") is None and D.scope_adjacent(nbfc, "Consumer finance") is None
    broad = {"industry": "Finance Services"}
    assert D.scope_adjacent(broad, "Payments and fintech", about="American Express is a bank holding company and card issuer.")
    assert D.scope_adjacent(broad, "Payments and fintech", about="We are building a trusted platform for the crypto economy.") is None
    assert D.scope_adjacent({"industry": "Civil Construction"}, "Real estate")["kind"] == "construction and engineering contractors"
    assert D.scope_adjacent({"industry": "Civil Construction"}, "Capital goods") is None
    assert D.scope_adjacent({"industry": "Tea & Coffee"}, "FMCG", about="It owns tea plantations in Assam.", model="resources",
                            confidence="medium")["kind"] == "miners, drillers and growers"
    assert D.scope_adjacent({"industry": "Tea & Coffee"}, "FMCG", about="It sells packaged tea.", model="manufacturing", confidence="high") is None


# ---------- 3 P1 taxonomy stability ----------
def r52_previous() -> dict:
    """The previous live version of the Metals map as the live R52 deck had it: the R53 snapshot (inputs' "previous"), with the 14 companies
    the R53 change log says came from "Aluminium" back in it and Southern Magnesium back in "Other"."""
    prev = dict(inputs("metals")["previous"])
    prev.update({s_: "Aluminium" for s_ in ALUMINIUM})
    prev["SOUTHMG"] = "Other metals and mining companies"
    return prev


def test_the_aluminium_layer_comes_back_with_its_companies_that_still_fit_on_the_live_metals_inputs():
    """Fails before: the re-check under R53's rules lost "Aluminium" (14 companies on the R52 deck) to "Other" and the pipe makers, 51 of 66
    informative to 41 of 66, the log saying only "removed". Now, against the previous version that had it, the layer comes back with those of
    its companies whose words or official industry ("Aluminium") still say what it sells and that no other layer's name says they sell, and
    the placement lists it ("layers_gone") with where its companies went."""
    before = layers(replay("metals", previous={}, moved=False)["value_chain"])
    assert "Aluminium" not in set(before.values())
    out = replay("metals", previous=r52_previous())
    got = layers(out["value_chain"])
    back = [s_ for s_ in ALUMINIUM if got[s_] == "Aluminium"]
    assert len(back) >= 12 and {"HINDALUMI", "MAANALU", "MANAKALUCO", "BMAL"} <= set(back)
    gone = out["placements"]["layers_gone"]
    assert gone[0]["layer"] == "Aluminium" and gone[0]["before"] == 14 and gone[0]["restored"] == len(back)
    assert sum(gone[0]["to"].values()) == 14
    inf = lambda rows: sum(1 for x in rows.values() if x != "Other")      # noqa: E731
    assert inf(got) - inf(before) == sum(1 for s_ in back if before[s_] == "Other") >= 10          # the rest came back from the pipe makers


def test_the_layer_the_live_r53_version_already_lost_comes_back_from_its_change_log():
    """The live R53 Metals snapshot (the inputs' "previous") no longer has "Aluminium"; its change log moved its 14 companies out (11 into
    "Other", 3 to the pipe makers). Read from the log's moves, the next re-check restores the layer, as against the R52 version itself."""
    assert "Aluminium" not in set(inputs("metals")["previous"].values())
    out = replay("metals")
    got = layers(out["value_chain"])
    want = layers(replay("metals", previous=r52_previous())["value_chain"])
    assert [s_ for s_ in ALUMINIUM if got[s_] == "Aluminium"] == [s_ for s_ in ALUMINIUM if want[s_] == "Aluminium"]
    assert out["placements"]["layers_gone"][0]["before"] == 14


def test_a_layer_of_fewer_than_five_or_with_no_company_that_fits_stays_lost_and_says_why():
    vc = [{"layer": "Steel makers", "description": "", "companies": [{"ticker": "A", "name": "A Ltd", "industry": "Iron & Steel"}]},
          {"layer": "Other metals companies", "official": True, "basis": "rest",
           "companies": [{"ticker": s_, "name": f"{s_} Ltd", "industry": "Diversified"} for s_ in "BCDEF"]}]
    prev = {s_: "Aluminium" for s_ in "BCDEF"}
    out, gone = B.restore_vanished(json.loads(json.dumps(vc)), prev, lambda s: "", "Metals")
    assert gone and gone[0]["restored"] == 0 and "none restored" in gone[0]["why"] and gone[0]["to"] == {"Other": 5}
    out, gone = B.restore_vanished(json.loads(json.dumps(vc)), {s_: "Aluminium" for s_ in "BCD"}, lambda s: "", "Metals")
    assert gone == []


def test_the_change_log_says_where_a_lost_layer_s_companies_went_and_reads_back_its_moves():
    was = {"layers": ["Aluminium", "Pipes", "Other metals companies"], "cos": {"A": ["A", 0, None], "B": ["B", 0, None], "C": ["C", 0, None], "P": ["P", 1, None]},
           "off": {}, "map": ["A", "B", "C", "P"]}
    now = {"layers": ["Pipes", "Other metals companies"], "cos": {"A": ["A", 1, None], "B": ["B", 1, None], "C": ["C", 0, None], "P": ["P", 0, None]}, "off": {},
           "map": ["A", "B", "C", "P"], "gone": [{"layer": "Aluminium", "why": "none restored: 1 of its 3 companies' own words ..."}],
           "mwhy": {"C": "its own words say it sells what “Pipes” is"}}
    d = C.diff(was, now)
    ev = next(x for x in d["layers"] if x["kind"] == "removed")
    assert ev["went"] == {"Other metals companies": 2, "Pipes": 1} and ev["why"].startswith("none restored")
    assert next(x for x in d["moved"] if x["symbol"] == "C")["why"].startswith("its own words say")
    from app import deck as K
    said = K.removed_said(ev)
    assert said.startswith("“Aluminium” removed (3 companies: 2 to “Other metals companies”, 1 to “Pipes”)") and "none restored" in said
    assert not deck_check.check_text(f"Since the previous version: layers changed 1: {said}.")["counts"]["layer lost unsaid"]
    log = {"log": [{"moved": [{"symbol": "INTC", "from": MAKERS, "to": EQUIP}]}, {"moved": [{"symbol": "X", "from": "A", "to": "B"}]}]}
    assert C.move_memory(log) == {"INTC": [MAKERS, EQUIP], "X": ["A", "B"]}
    from app.intel import theme_workbook as WB
    _, rows, _, _ = WB.changes({"entries": [{"d": "2026-11-14", "cause": "rules", **d}]}, "IN")
    assert [str(r[7])[:67] for r in rows if r[2] == "Layer removed"] == ["3 companies: 2 to Other metals companies; 1 to Pipes; none restored"]
    assert any(len(r) == 8 and r[7].startswith("its own words say") for r in rows if r[2] == "Company moved")


# ---------- 4 P1 missing figures, a merged symbol ----------
def test_a_member_with_no_stored_figures_stays_in_its_layer_and_a_merged_symbol_is_said_so_in_the_log():
    """Fails before: a member whose page figures aren't stored was in no layer, and the log said it was "removed (no figures stored for it)"
    (the live R53 Insurance deck said so of ICICI Prudential Life, which d53 kept once as the same company as ICICI Life)."""
    from tests.test_r18_deck import deck_of
    from tests.test_r48_reconcile import co
    m = {"sector": "Insurance", "value_chain": [{"layer": "Life insurers", "description": "", "companies": [
        {"ticker": t, "name": f"{t} Life Insurance Ltd", "verified": True, "industry": "Life Insurance"} for t in ("AA", "BB", "CC", "DD")]}]}
    f = {t: co(t, f"{t} Life Insurance Ltd", 1000.0 + 10 * i, 10.0, 80.0) for i, t in enumerate(("AA", "BB", "CC"))}
    v, _ = deck_of("IN", m, f, theme="Insurance")
    rows = {c["symbol"]: c for b in v["layers"] for c in b["companies"]}
    assert "DD" in rows and rows["DD"]["figures"] == "not_available" and not D.has_figures(rows["DD"])
    assert {x["symbol"] for x in v.get("without_figures") or []} >= {"DD"} or rows["DD"]["revenue"] is None
    now = {"layers": ["Life insurers"], "cos": {"ICICILIFE": ["ICICI Life Insurance Ltd", 0]}, "off": {}, "map": ["ICICILIFE", "ICICIPRULI"],
           "dups": {"ICICIPRULI": "ICICI Life Insurance Ltd"}}
    assert C._why_removed("ICICIPRULI", now) == "the same company as ICICI Life Insurance Ltd, listed under two symbols: kept once"
    assert C._why_removed("OTHER", now) == "no longer in the theme's map"


# ---------- 5 the same company's figures under two symbols ----------
def test_figures_under_a_symbol_whose_description_names_the_other_company_are_kept_once():
    """Fails before: the live R53 Pharma deck's "Evonile Pharma Ltd" row was Novartis India's (₹354 crore, −0.6%, 27%, 26.3%), its stored
    description "Novartis India Ltd is primarily engaged ..."; the names share no word, so both stayed and deck_check failed the deck."""
    rows = [{"symbol": "EVONILE", "name": "Evonile Pharma Ltd", "year": "Mar 2026", "revenue": 354.0, "profit": 93.0, "cap": 5319.0},
            {"symbol": "NOVARTIND", "name": "Novartis India Ltd", "year": "Mar 2026", "revenue": 354.0, "profit": 93.0, "cap": 4134.0},
            {"symbol": "OTHER1", "name": "Maker 1 Ltd", "year": "Mar 2026", "revenue": 500.0, "profit": 50.0},
            {"symbol": "OTHER2", "name": "Maker 2 Ltd", "year": "Mar 2026", "revenue": 500.0, "profit": 50.0}]
    about = {"EVONILE": "Novartis India Ltd is primarily engaged in the Business of Wholesale of pharmaceuticals and medical goods.",
             "NOVARTIND": "Novartis AG is a Swiss multinational pharmaceutical corporation based in Basel."}
    assert D.same_company(rows) == {}                                     # before: names sharing no word were never merged
    assert D.same_company(rows, about=about.get) == {"EVONILE": "NOVARTIND"}
    assert D.same_company(rows, about=lambda s: "") == {}                 # no description naming the other: two companies


# ---------- deck_check ----------
R53 = pathlib.Path("/nonexistent")


def test_deck_check_finds_moves_without_a_reason_scope_layers_counted_core_and_lost_layers():
    move = ("On 14 Nov 2026, against the version stored before it, after a re-check under new placement rules: moved between layers 1: "
            "Intel Corp (from “Makers of their own products” to “Chip equipment and subsystem suppliers”).")
    got = deck_check.check_text(move)
    assert got["counts"]["move unexplained"] == 1
    fixed = move.replace("suppliers”).", "suppliers”: its own words say it sells what “Chip equipment and subsystem suppliers” is).")
    assert not deck_check.check_text(fixed)["counts"]["move unexplained"]
    into_how = move.replace("“Makers of their own products” to “Chip equipment and subsystem suppliers”", "“Fabless” to “Makers of their own products”")
    assert not deck_check.check_text(into_how)["counts"]["move unexplained"]
    lost = "Since the previous version: layers changed 1: “Aluminium” removed (14 companies)."
    assert deck_check.check_text(lost)["counts"]["layer lost unsaid"] == 1
    scope = "Automotive\nIndia (NSE and BSE) · Theme deep dive\nx\fLayer 6 · Vehicle financiers\nBajaj Finance"
    assert deck_check.check_text(scope)["counts"]["scope core"] == 1
    assert not deck_check.check_text(scope + "\fCore and adjacent\n3 companies ... adjacent participants")["counts"]["scope core"]
    assert not deck_check.check_text(scope.replace("Automotive", "Consumer finance"))["counts"]["scope core"]
    assert not deck_check.check_text(scope.replace("Vehicle financiers", "Agri-processing and edible oil refining"))["counts"]["scope core"]


def test_the_rules_version_and_the_new_inputs():
    from app import deck as K
    from app.intel import theme_routes as TR
    assert B.RULES == 53 and TR.PLACE_CARRY[53] == 52 and K.THEME_DECK_VERSION == 64 and D.DIVE_TEXT == 24
    assert "moved_before" in B.place_rest.__code__.co_varnames
    assert re.search(r'"moved_before": moved_before\(r, theme, m\)', pathlib.Path(TR.__file__).read_text())


@pytest.mark.parametrize("key", ["semis", "meddev"])
def test_the_live_r53_inputs_replay_exactly_with_the_check_off(key, monkeypatch):
    """The inputs replay the live placement exactly (every company in its live layer) once the check is off: the replays above differ from
    live by the check alone."""
    monkeypatch.setattr(B, "sold_what", lambda out, *a, **k: out)
    assert layers(replay(key)["value_chain"]) == live(key)
