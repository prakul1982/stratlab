"""Lane rv51 (Release 51), the outside review of the live Release 49 decks (avg 9.07; Consumer retail US 8.8 -> 8.4, IT services 9.3 -> 9.1).

P0 Consumer retail (p.3, 9-11, 49-51): four ranked layers became two. "Online stock-holding retailers" was shown, not ranked, as "a different
   business model: platforms and marketplaces (the map's name for the layer)" and "Store retailers of home, auto and beauty goods" as "parts,
   component and ingredient makers": labels read from the map's earlier names for the layers ("Online marketplaces"; "Home improvement, auto
   parts and beauty"), not from the layers as the deck names and fills them. A layer's business model now comes from its own records
   (theme_check.layer_business, theme_data.named_fit); deck_check fails both reasons (biz label, biz making).
P0 IT services (p.4-5): Black Box Ltd was screened out ("own words describe other work") on its first sentence, which tells its history and
   names its former parent "Tata Telecom". A company of the theme's industries whose principal disclosed business fits the theme stays in
   it (theme_data.principal_business, membership). The 139 -> 132 fall of companies in informative layers: an answer asked for 2 new
   companies replaced the kept answer's layer names and its two extra layers (theme_base.with_earlier, theme_routes.kept_placement).
P1 a bank's other income in its own terms; "verified" apart from "arithmetic reproduced"; a layer's net median with its † companies.
P2 the companies added, removed or moved into "Other" since the previous version (deck.cohort_row).

The live inputs are tests/fixtures/themes_live/inputs_r49 (the owner's read-only placement inputs of 13 Nov; "earlier" in it.json is the
answer kept under rules 44, from the live Release 46 inputs). Every figure is synthetic."""
import copy
import json
import pathlib
import sys

import pytest

from app import computed, deck
from app.intel import theme_base as B, theme_check as T, theme_data as D, theme_routes as TR
from tests import test_exact_replay as X
from tests.test_export import texts
from tests.test_r18_deck import deck_of
from tests.test_r48_compare import chem
from tests.test_r48_reconcile import co

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import deck_check  # noqa: E402

LIVE = pathlib.Path(__file__).parent / "fixtures" / "themes_live" / "inputs_r49"
ONLINE, STORES = "Online stock-holding retailers", "Store retailers of home, auto and beauty goods"
# the live layers' median EBITDA margins on the R49 deck (p.3), each company's figure about its layer's
OPM = {"Off-price": 12.6, "Warehouse": 6.1, "Online": 1.3, "Store": 14.8, "Platforms": -2.8, "Apparel": 9.0}


def inputs(key: str) -> dict:
    d = json.loads((LIVE / f"{key}.json").read_text())
    return d.get("data", d)


def replay(d: dict, key: str, kept=None, ask=None) -> tuple[dict, dict]:
    origin = dict(X.RECOVERED["origin"].get(key) or {})
    for v in d["value_chain"]:
        for c in v["companies"]:
            if c.get("moved") and not c.get("placed") and c["ticker"] not in origin:
                origin[c["ticker"]] = "?" + c["ticker"]
    m = X.pre_map(d, origin, X.RECOVERED["description"].get(key))
    kept = d["kept"] if kept is None else kept
    return B.place_rest(m, d["theme"], lambda s: d["evidence"].get(s), ask=ask, kept=kept, facts_of=lambda s: d["facts"].get(s) or {},
                        carried=d["kept_version"] != B.RULES, previous=d.get("previous") or {})


def retail_deck():
    d = inputs("retail")
    out, _ = replay(d, "retail")
    f = {}
    for v in out["value_chain"]:
        base = next((x for k, x in OPM.items() if v["layer"].startswith(k)), 8.0)
        for i, c in enumerate(v["companies"]):
            sales = 1000.0 + 37 * i
            f[c["ticker"]] = co(c["ticker"], c.get("name") or c["ticker"], sales, base + (i % 3) - 1, sales * (base - 4) / 100)
    return out, deck_of("US", {**out, "sector": d["theme"], "sub_themes": out.get("sub_themes") or []}, f, theme=d["theme"])


# ---------- P0 Consumer retail: a layer's business model from its own records ----------
def test_the_live_retail_layers_are_compared_on_how_their_companies_earn_not_on_the_map_s_old_labels():
    """Fails before: theme_data.named_fit didn't exist; the deck kept "platforms and marketplaces" and "parts, component and ingredient
    makers" (the map's name for the layer) and ranked two layers of four."""
    out, (v, slides) = retail_deck()
    vc = {x["layer"]: x for x in out["value_chain"]}
    # by_model still reads the map's earlier names ("Online marketplaces"; "Home improvement, auto parts and beauty" before the rename) ...
    assert vc[ONLINE]["was"] == "Online marketplaces" and vc[ONLINE]["model"]["named"] == "platform"
    assert vc[STORES]["model"]["named"] == "components" and vc[STORES]["model"]["family"] == "resale"
    # ... but neither is the layer's own: its name states retail, its companies resell, its description says "the margin on goods that others make"
    assert "named" not in D.named_fit(vc[ONLINE]["model"], vc[ONLINE]) and "named" not in D.named_fit(vc[STORES]["model"], vc[STORES])
    ch = v["chain"]
    assert ch["highest"] == STORES and ch["lowest"] == ONLINE and len(ch["compared"]) == 4          # the R48 deck's four layers again
    t = texts(slides)
    assert "a different business model" not in t and "the map's name for the layer" not in t
    assert {x["layer"]: x["why"] for x in ch["basis"]["left"]} == {
        "Apparel and consumer brand owners": "a different kind of business", "Platforms and marketplaces": "fewer than 5 companies with the figure",
        "Other consumer retail companies": "companies outside the map's layers"}
    got = deck_check.check_text(t)["counts"]
    assert got["biz label"] == 0 and got["biz making"] == 0


def test_a_business_model_is_kept_only_where_the_layer_s_own_name_or_definition_states_it():
    lb = T.layer_business
    # the same layer: its own name states it (Chemicals' custom synthesis layer, a contract maker's model beside makers of their own products)
    assert lb("contract_manufacturing", "Custom synthesis manufacturers", family="making") == ("contract_manufacturing", "name")
    assert lb("contract_manufacturing", "Custom synthesis and agrochemicals", family="making") == ("contract_manufacturing", "name")
    # a map label for a renamed layer: used only when the layer's own description states the same model
    assert lb("platform", "Commission marketplaces", was="Online marketplaces",
              description="These platforms earn commissions and listing fees from third-party sellers.", family="resale")[0] == "platform"
    assert lb("platform", ONLINE, was="Online marketplaces", description="They sell goods they buy and hold.", family="resale") == ("", "")
    # a making model is never a seller's or a service firm's, whatever its name names (auto parts are what the store sells)
    assert lb("components", "Home improvement, auto parts and beauty", family="resale") == ("", "")
    assert lb("contract_manufacturing", "Custom synthesis services", family="services") == ("", "")
    # a name stating another way of earning contradicts it; an unknown model is nothing
    assert lb("platform", "Online retailers and marketplaces", family="resale") == ("", "")
    assert lb("unknown", "Anything") == ("", "")


def test_the_chemicals_custom_synthesis_layer_says_its_model_is_read_from_its_own_name():
    """(updated on purpose from ex49's "(the map's name for the layer)": the same layer, read from its own name)."""
    make = {"id": "manufacturing", "family": "making", "known": 6, "of": 6}
    m, f = chem(model=make)
    m["value_chain"][0]["model"] = {**make, "named": "contract_manufacturing"}
    v, slides = deck_of("IN", m, f)
    left = {x["layer"]: x["why"] for x in v["chain"]["basis"]["left"]}
    assert left["Custom synthesis manufacturers"] == "a different business model: contract manufacturing (stated by the layer's own name)"
    assert v["chain"]["highest"] == "Chlor-alkali and soda ash producers"           # kept: the manufacturing-only comparison
    assert deck_check.check_text(texts(slides))["counts"]["biz label"] == 0


# the live R49 Consumer retail deck, p.3 and p.9 (pdftotext -layout), and the live R49 Chemicals deck's reason
LIVE_RETAIL = """Among the 2 layers with at least 5 companies with the figure and one kind of business, median EBITDA margin is highest
in Off-price, dollar and discount store chains (12.6%) and lowest in Warehouse clubs and mass merchants (6.1%), a gap
of 6.5 points; among the map's layers, the "Other" group left out. Shown, not ranked: Online stock-holding retailers
(1.3%), a different business model: platforms and marketplaces (the map's name for the layer); Store retailers of home,
auto and beauty goods (14.8%), a different business model: parts, component and ingredient makers (the map's name for
the layer); Platforms and marketplaces (−2.8%), fewer than 5 companies with the figure."""
LIVE_CHEM = ("Shown, not ranked: Custom synthesis and agrochemicals (21.0%), a different business model: contract manufacturing (the map's name "
             "for the layer); Specialty ingredients (14.0%), fewer than 5 companies with the figure.")


def test_deck_check_fails_a_business_model_the_layer_s_own_records_do_not_state():
    """Fails before: deck_check had no "biz label" or "biz making" column, and the live R49 retail deck passed every column but other>40%."""
    got = deck_check.check_text(LIVE_RETAIL)
    assert got["counts"]["biz label"] == 2 and got["counts"]["biz making"] == 1
    assert any("Store retailers of home, auto and beauty goods: parts, component and ingredient makers" in x["text"]
               for x in got["findings"] if x["kind"] == "biz making")
    assert deck_check.check_text(LIVE_CHEM)["counts"]["biz label"] == 0           # a custom synthesis layer's own name states contract making
    assert deck_check.failed(got) and "biz label" in deck_check.FAIL and "biz making" in deck_check.FAIL


# ---------- P0 IT services: a principal business that fits keeps a company in the theme ----------
def test_black_box_stays_in_the_it_theme_on_its_principal_business():
    """Fails before: membership read only its first sentence ("incorporated in 1986 by Tata Telecom Pvt. Ltd. to manufacture
    telecommunication equipment") and screened it out as other work."""
    d = inputs("it")
    words = D.theme_words(d, d["theme"])
    bbox = next(c for v in d["value_chain"] for c in v["companies"] if c["ticker"] == "BBOX")
    about = d["evidence"]["BBOX"]
    assert D.membership(bbox, words, principal=False) == "unverified"                                  # the check as it was
    assert D.membership(bbox, words, about, d["facts"]["BBOX"].get("segments")) == "core"
    where, said = D.principal_business(bbox, about)
    assert where == "description" and said.startswith("Over the years, AGC evolved into an information and communication (ICT) solutions provider")
    # its largest reported segment, where one is stored, is its principal business
    assert D.principal_business(bbox, about, [{"name": "System integration", "share_pct": 70.0}, {"name": "Other", "share_pct": 30.0}]) == \
        ("segment", "System integration")
    # a stem-cell clinic network filed under retail stays screened out: its principal business is other work
    r = inputs("retail")
    rmtg = next(c for v in r["value_chain"] for c in v["companies"] if c["ticker"] == "RMTG")
    assert D.membership(rmtg, D.theme_words(r, r["theme"]), r["evidence"]["RMTG"], []) == "unverified"


def test_black_box_s_theme_record_says_why_it_stays():
    d = inputs("it")
    bbox = next(c for v in d["value_chain"] for c in v["companies"] if c["ticker"] == "BBOX")
    m = {"sector": d["theme"], "value_chain": d["value_chain"], "sub_themes": [], "placements": d["placements"]}
    f = {"BBOX": co("BBOX", "Black Box Ltd", 6322.0, 9.0, 215.0)}
    dive = D.build("IN", d["theme"], m, D.Sources(__import__("datetime").date(2026, 11, 13), facts=f.get, about=d["evidence"].get))
    row = next(c for b in dive["layers"] for c in b["companies"] if c["symbol"] == "BBOX")
    assert row["status"] == "core" and row["theme"]["in"]
    assert row["theme"]["why"].endswith("its own words name other work, but its principal business (the first sentence of its description that "
                                        "says what it does now) fits the theme, so it stays in the theme")


def test_a_description_s_history_and_other_companies_names_are_not_its_business():
    s = D.business_sentence
    assert s("AGC Networks Ltd. (AGC), incorporated in 1986 by Tata Telecom Pvt. Ltd. to manufacture telecommunication equipment.") == ""
    assert s("Incorporated in 2011, GVP Infotech Ltd is in the business of IT Services.") == \
        "Incorporated in 2011, another company is in the business of IT Services."
    assert s("It is currently held by Essar Telecom Ltd. Over the years, it evolved into a solutions provider.") == \
        "Over the years, it evolved into a solutions provider."
    assert s("The Company was established in 1981.") == ""


# ---------- P0 IT services: 139 -> 132 in informative layers ----------
def fake_answer(rename_to: str):
    """The live R49 answer: COFORGE and MPHASIS into "Digital engineering and consulting projects", that layer renamed, no extra layer."""
    def ask(system, text):
        if system != T.PLACE_SYSTEM2:
            return {}
        pay = json.loads(text.split("\n", 1)[1])
        lid = next(k for k, x in pay["layers"].items() if x["name"] == "Digital engineering and consulting projects")
        return {"place": [{"symbol": s_, "layer": lid} for s_ in ("COFORGE", "MPHASIS") if any(c["symbol"] == s_ for c in pay["companies"])],
                "rename": [{"layer": lid, "name": rename_to, "description": "These firms sell project-based software and cloud work."}], "extra": []}
    return ask


def test_an_answer_for_two_new_companies_keeps_the_kept_answer_s_extra_layers_and_names():
    """Fails before: the answer's rename and its empty extra list replaced the kept answer's, and the 17 companies of the two extra layers
    left them (139 -> 132 companies in informative layers on the live IT services deck)."""
    d = inputs("it")
    early = d["earlier"]
    kept = {**copy.deepcopy(d["kept"]), "assign": early["assign"], "rename": early["rename"], "extra": early["extra"]}      # the R46 answer
    assert "COFORGE" not in kept["assign"] and len(kept["extra"]) == 2
    out, got = replay(d, "it", kept=kept, ask=fake_answer("Mid-tier digital engineering and cloud services"))
    assert got["assign"]["COFORGE"]["layer"] == "Digital engineering and consulting projects"
    assert [x["name"] for x in got["extra"]] == ["IT infrastructure, cloud and systems integration", "Healthcare and digital business process services"]
    assert got["rename"]["Software product licences and platforms"]["name"] == "Software products and SaaS platforms"
    assert got["rename"]["Digital engineering and consulting projects"]["name"] == "Mid-tier digital engineering and cloud services"
    lay = {c["ticker"]: v["layer"] for v in out["value_chain"] for c in v["companies"]}
    assert lay["BBOX"] == "IT infrastructure, cloud and systems integration" and lay["SAGILITY"] == "Healthcare and digital business process services"
    assert sum(1 for v in out["value_chain"] if not v.get("official") for _ in v["companies"]) >= 139


def test_the_live_r49_it_inputs_with_the_earlier_answer_place_as_the_r48_deck_did():
    """The exact replay of the live R49 placement inputs: 132 of 252 in informative layers as kept; with the earlier answer's names and extra
    layers (what kept_placement now joins to it) 140, every company of R48's 139 in its R48 layer (a rename aside) and GVP Infotech, whose
    description is newly kept, in a layer too."""
    d = inputs("it")
    out, _ = replay(d, "it")
    inf = lambda o: {c["ticker"] for v in o["value_chain"] if not v.get("official") for c in v["companies"]}          # noqa: E731
    assert len(inf(out)) == 132
    early = d["earlier"]
    out2, _ = replay(d, "it", kept=B.with_earlier(d["kept"], early))
    assert len(inf(out2)) == 140 and inf(out) < inf(out2)
    back = {"BBOX", "BLSE", "GENESYS", "IKS", "IVALUE", "ORIENTTECH", "PROTEAN", "SAGILITY"}
    assert back <= inf(out2) and not back & inf(out)


def test_kept_placement_joins_the_nearest_earlier_answer_of_the_same_map(monkeypatch):
    early = {"assign": {"A": {"layer": "L", "by": "ai"}}, "rename": {"L": {"name": "Old name"}}, "extra": [{"name": "Extra", "symbols": ["X", "Y"]}]}
    newer = {"assign": {"A": {"layer": "L", "by": "ai"}, "B": {"layer": "L", "by": "ai"}}, "rename": {"M": {"name": "New name"}}, "extra": []}
    store = {TR.PLACE_CARRY[B.RULES]: newer, 44: early}
    seen = []

    def get(kind, key):
        seen.append(key[-1])
        return {"value": store[key[-1]]} if key[-1] in store else None
    monkeypatch.setattr(computed, "get", get)
    kept, version = TR.kept_placement("IN", "IT services", {"generated_at": 1.0})
    assert version == TR.PLACE_CARRY[B.RULES]
    assert kept["extra"] == early["extra"] and kept["rename"] == {"M": {"name": "New name"}, "L": {"name": "Old name"}}
    assert set(kept["assign"]) == {"A", "B"}
    assert seen[-1] == 44 and len(seen) == len(set(seen))
    # with no earlier answer, the walk stops after EARLIER_MAX versions
    store.pop(44)
    seen.clear()
    TR.kept_placement("IN", "IT services", {"generated_at": 1.0})
    assert len(seen) <= 2 + TR.EARLIER_MAX


def test_versions():
    assert B.RULES == 50 and TR.PLACE_CARRY[50] == 49 and deck.THEME_DECK_VERSION == 61 and D.DIVE_TEXT == 21


# ---------- P1: a financial company's other income; verified against arithmetic reproduced; † medians ----------
def bank_row(sym="HDFCBANK", name="HDFC Bank Limited"):
    from tests.test_r18_deck import bank_facts
    f = bank_facts(sym, name, [300000.0, 320000.0, 335000.0, 348615.0], [60000.0, 68000.0, 74000.0, 79219.0], 1500000.0, 14.0, 2.5, 1.3, 0.4, 3.1, 1.8)
    f["years"][-1].update({"other_income": 146848.0, "interest": 185491.0, "dep": 4195.0, "pbt": 102141.0, "tax_pct": 22.0})
    f["basis"] = "consolidated"
    return D.company_row("IN", sym, f)


def test_a_bank_s_other_income_is_never_called_income_outside_operations():
    """Fails before: twelve verified cases on the live Private banks deck said "income outside operations of ₹146,848 crore"."""
    r = bank_row()
    rec = r["verify"]["net"]
    assert rec["state"] == D.VERIFIED and "outside operations" not in rec["why"] and "outside operations" not in " ".join(rec["checks"])
    assert "non-interest income (other income: fees, commissions and treasury gains) of ₹146,848 crore is 185% of the net profit" in rec["why"]
    assert D.other_income_words({"profile": "other"}) == "income outside operations"
    assert D.other_income_words({"profile": "insurer", "bank": True}) == "other income"


def test_a_figure_whose_arithmetic_alone_was_reproduced_is_not_called_verified():
    """Fails before: every kept case was "verified", the bank's whose large other income nothing explained included."""
    r = bank_row()
    st = D.figure_states([{**r, "status": "core", "source": {"document": "annual results, consolidated", "period": "Mar 2026"}}])
    assert st[0]["checked"] == "arithmetic" and deck.only_arithmetic(st[0]) and deck.state_word(st[0]) == "arithmetic reproduced"
    row = deck.verified_row(st)
    assert row[1].startswith("1 unusual figure, arithmetic reproduced (net profit over revenue worked out again, nothing more checked): HDFC Bank "
                             "Limited, net margin 22.7% (net profit ₹79,219 crore over revenue ₹348,615 crore, Mar 2026: 22.7%")
    # a net margin above EBITDA covered by its statement lines is verified: the calculation, its basis and the lines
    lines = {"other_income": 400.0, "interest": 20.0, "dep": 30.0, "pbt": 450.0, "tax_pct": 25.0, "op": 100.0}
    x = D.company_row("IN", "G", co("G", "Gain Co Ltd", 1000.0, 10.0, 337.5, lines=lines))
    sx = D.figure_states([{**x, "status": "core", "source": {"document": "annual results, consolidated"}}])[0]
    assert sx["state"] == D.VERIFIED and sx["checked"] == "lines" and deck.state_word(sx) == "verified"
    # with no accounting basis stored, the arithmetic alone
    assert deck.state_word({**sx, "source": {"document": "annual results (consolidated or standalone is not stored on the page)"}}) == "arithmetic reproduced"
    both = deck.verified_row([sx] + st)
    assert both[1].startswith("2 unusual figures checked: 1 verified against their own filed figures, 1 arithmetic reproduced only: Gain Co Ltd")


def test_a_layer_page_gives_its_net_median_with_the_dagger_companies_when_leaving_them_out_moves_it():
    m, f = chem()
    lay = m["value_chain"][0]
    for c in lay["companies"][:3]:
        x = f[c["ticker"]]
        x["years"][-1]["profit"] = x["years"][-1]["sales"] * 0.6                # net 60% against an EBITDA margin about 22%: †, no line covers it
        x["net"] = 60.0
    v, slides = deck_of("IN", m, f)
    b = next(x for x in v["layers"] if x["layer"] == lay["layer"])
    assert len(b["one_off"]) == 3
    page = next(s for s in slides if s.title.endswith("· " + lay["layer"]))
    assert "with the 3 † companies" in page.subtitle


# ---------- P2: the cohort since the previous version ----------
def test_every_deck_lists_the_companies_added_removed_or_moved_into_other_since_the_previous_version():
    """Fails before: no deck said what changed in its cohort; the change log was on the theme's page only."""
    e = {"d": "2026-11-12", "cause": "rules", "counts": {"added": 1, "removed": 1, "moved": 2},
         "added": [{"symbol": "GVPTECH", "name": "GVP Infotech Ltd", "layer": "Engineering R&D services"}],
         "removed": [{"symbol": "Z", "name": "Zed Ltd", "layer": "L", "why": "another business (filed under IT Enabled Services)"}],
         "moved": [{"symbol": "BBOX", "name": "Black Box Ltd", "from": "IT infrastructure, cloud and systems integration", "to": "Other IT service companies"},
                   {"symbol": "C", "name": "Cee Ltd", "from": "A", "to": "B"}]}
    v = {"changes": {"entries": [e]}, "coverage": {"other_name": "Other IT service companies"}}
    row = deck.cohort_row(v)
    assert row[0] == "Since the previous version" and row[1] == "3"
    assert row[2] == ("On 12 Nov 2026, against the version stored before it, after a re-check under new placement rules: added 1: GVP Infotech Ltd; "
                      "removed 1: Zed Ltd (another business (filed under IT Enabled Services)); moved into “Other IT service companies” 1: Black Box Ltd "
                      "(from “IT infrastructure, cloud and systems integration”).")
    assert deck.cohort_row({"changes": {"entries": []}})[2] == "No earlier stored version of this theme's figures to compare with."
    assert deck.cohort_row({}) is None
