"""Lane p57 (Release 57, the owner's review of the live R56 decks): the placement contract.

Each release's re-check under new placement rules broke companies that were right before: Capital One out of Payments ("its own words
were checked and don't show the work of “Card issuers and lenders”", the same stored words the version before had checked to show it),
Sarepta out of Biotech (one narrow layer's "no", and out of the figures with it), Duolingo moved from "Other software companies" into a new
one-company layer "Hotels, travel and consumer services". The contract (theme_base.keep_published, hold_published, truthful_layers,
best_layer_moves; theme_check.check_placements `held`; theme_changes.published_members and the snapshot's "rest"; deck_check's three rules)
is generic: no company or theme name in the app's code, only here.

The live inputs are what GET /research/theme-dive/placement-inputs returned on 15 Nov 2026 for the R56 decks (lane g57):
tests/fixtures/themes_live/p57_r56/. The published memory the live placement reads (theme_routes.published_layers) is the inputs'
"previous" (the R56 snapshot) and the companies the R56/R55 re-checks removed on a check's answer alone, at the layer they were removed
from (the decks' "Since the previous version" rows: REMOVED)."""
import copy
import json
import pathlib
import sys

import pytest

from app.intel import theme_base as B
from app.intel import theme_changes as C
from app.intel import theme_check as TC
from tests import test_exact_replay as X

LIVE = pathlib.Path(__file__).parent / "fixtures" / "themes_live"
R56 = LIVE / "p57_r56"
ORIGIN = {"payments": {"XYZ": "Card issuers and lenders", "FLYW": "Card networks"}, "metals": {"JSL": "Specialty steel and fabricated steel products"}}
REMOVED = {"payments": {"COF": "Card issuers and consumer lenders", "ADYEY": "Merchant acquiring and processing"},
           "biotech": {"SRPT": "Specialty and clinical-stage biotechs"}}
STALE = ("out_why", "on_industry", "refit", "own_goods", "by_words", "unfit", "sold_by")
_CACHE: dict = {}

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import deck_check  # noqa: E402


def inputs(key: str) -> dict:
    if key not in _CACHE:
        d = json.loads((R56 / f"{key}.json").read_text())
        d = d.get("data", d)
        for v in d["value_chain"]:
            v["companies"] = [{k: x for k, x in c.items() if k not in STALE} for c in v["companies"]]
        _CACHE[key] = d
    return copy.deepcopy(_CACHE[key])


def r55_payments() -> dict:
    d = json.loads((LIVE / "inputs_r55" / "payments.json").read_text())
    return d.get("data", d)


def place(key: str, monkeypatch, contract: bool = True, ask=None) -> dict:
    """The live R56 inputs placed again under the rules now, the published memory read as live reads it (`contract`), else as a stored
    version is replayed (no memory)."""
    d = inputs(key)
    sig = ((d.get("kept") or {}).get("model_names") or {}).get("sig")
    if sig:
        monkeypatch.setattr(B, "model_names_signature", lambda layers: sig)
    info = {}
    if key == "payments":                       # Capital One's stored words and fields, as the R55 inputs hold them (the R56 map dropped it)
        old = r55_payments()
        d["evidence"].setdefault("COF", old["evidence"]["COF"])
        info = {c["ticker"]: {"name": c.get("name"), "industry": c.get("industry"), "cap": c.get("cap")} for v in old["value_chain"]
                for c in v["companies"]}
    m = X.pre_map(copy.deepcopy(d), ORIGIN.get(key, {}), {})       # the map layer a split moved a map pick out of (recovered, rep.origin_of)
    pub = {**d["previous"], **REMOVED.get(key, {})} if contract else None
    if contract:
        m["placements"] = dict(d["placements"])
        m = B.keep_published(m, pub, lambda s: d["evidence"].get(s), rename=B.answer_renames(d["kept"]), info_of=lambda s: info.get(s))
    out, _ = B.place_rest(m, d["theme"], lambda s: d["evidence"].get(s), ask=ask, kept=d["kept"], facts_of=lambda s: d["facts"].get(s) or {},
                          figures_of=lambda s: (d.get("figures") or {}).get(s) or {}, carried=d["kept_version"] != B.RULES,
                          previous=d["previous"], off_before=d.get("off_before") or {}, moved_before=d.get("moved_before") or {},
                          **({"moved_out": d["moved_out"]} if d.get("moved_out") else {}), published=pub)
    return out


def where(out: dict) -> dict:
    return {c["ticker"]: ("Other" if v.get("official") and v.get("basis") == "rest" else X._HALF.sub("", v["layer"]), c)
            for v in out["value_chain"] for c in v["companies"]}


# ---------- acceptance on the live R56 inputs ----------
def test_capital_one_and_adyen_are_back_in_payments_in_their_published_layers(monkeypatch):
    """Fails before (no published memory: the R56 map check's "no" on its unchanged words removed it): Capital One is in "Card issuers and
    consumer lenders", its own words quoted, its model a lender's, kept from the published version with why."""
    assert "COF" not in where(place("payments", monkeypatch, contract=False))
    got = where(place("payments", monkeypatch))
    lay, c = got["COF"]
    assert lay == "Card issuers and consumer lenders" and c["verified"] is True and "card" in c["what"].lower()
    assert c["model"] == "lending" and "kept from the published version" in c["kept_member"]
    assert got["ADYEY"][0] == "Merchant acquiring and processing"       # published in R54, removed in R55 on a check's answer alone


def test_sarepta_is_back_in_its_biotech_layer(monkeypatch):
    """Fails before: the R56 check's "no" for one narrow map layer sent Sarepta (a base company) to "Other", past the figures' window."""
    assert where(place("biotech", monkeypatch, contract=False))["SRPT"][0] == "Other"
    lay, c = where(place("biotech", monkeypatch))["SRPT"]
    assert lay == "Specialty and clinical-stage biotechs" and c["verified"] is True


def test_duolingo_is_in_no_travel_or_hotel_layer_and_software_has_none(monkeypatch):
    """Fails before: "Hotels, travel and consumer services" holding Duolingo and Coursera, whose own words name courses and education."""
    out = place("software", monkeypatch)
    got = where(out)
    assert got["DUOL"][0] == got["COUR"][0] == "Education and courses"
    assert not [v["layer"] for v in out["value_chain"] if v["companies"] and any(w in v["layer"].lower() for w in ("hotel", "travel"))]
    row = out["placements"]["contract"]["layers"][0]
    assert row["layer"] == "Hotels, travel and consumer services" and row["renamed"] == "Education and courses"


@pytest.mark.parametrize("key,layer,n", [("metals", "Aluminium", 13), ("retail", "Catalog and mail-order houses", 6)])
def test_the_restored_layers_hold(key, layer, n, monkeypatch):
    got = where(place(key, monkeypatch))
    assert sum(1 for x, _ in got.values() if x == layer) == n


@pytest.mark.parametrize("key", ["payments", "biotech", "software", "metals", "retail"])
def test_no_published_member_leaves_its_theme_and_each_move_carries_its_reason(key, monkeypatch):
    """The contract on every stored live input: every company of the stored placement is still in the theme, and each one placed in another
    layer than the stored one carries a printed reason (a rule's "refit", its kept or held reason) or is a rename of its layer."""
    d = inputs(key)
    live = {c["ticker"]: ("Other" if v.get("official") else X._HALF.sub("", v["layer"])) for v in d["value_chain"] for c in v["companies"]}
    plain = where(place(key, monkeypatch, contract=False))
    got = where(place(key, monkeypatch))
    assert set(live) <= set(got)
    for s_, (lay, c) in got.items():
        if s_ in live and lay != live[s_] and plain.get(s_, (None,))[0] != lay:
            assert c.get("refit") or c.get("kept_member") or c.get("held_published") or c.get("sold_by") or lay == "Education and courses", s_


# ---------- 1. stability: a rules bump with a model that answers wrongly ----------
def _map():
    return {"value_chain": [
        {"layer": "Card issuers and lenders", "description": "Banks and lenders that issue cards.", "companies": [
            {"ticker": "CI", "name": "Card Issuer Corp"}, {"ticker": "NEW", "name": "New Lender Inc"}]},
        {"layer": "Merchant acquiring", "description": "Process card payments for merchants.", "companies": [
            {"ticker": "ACQ", "name": "Acquirer Inc"}]}]}


WORDS = {"CI": "Card Issuer Corp issues credit cards to consumers and earns interest, interchange and fees on its card loans.",
         "NEW": "New Lender Inc makes consumer loans and issues credit cards through its bank.",
         "ACQ": "Acquirer Inc processes card payments for merchants and earns fees on each payment it processes."}


def _evidence(syms):
    return {s: {"about": WORDS[s], "industry": ""} for s in syms}, set()


def test_a_rules_bump_asks_no_published_member_again_and_a_wrong_answer_moves_none():
    """A re-check (the map's check run again, as on a rules bump) with a model that says "no" to everything: the published members that
    pass the contract are not asked at all and stay in their groups, their own words quoted; only the new company is asked (and the wrong
    answer leaves it out, as a new candidate)."""
    asked = []

    def wrong(system, text):
        payload = json.loads(text.split("CHECKS:\n", 1)[1])
        asked.extend(c["symbol"] for c in payload["companies"])
        return {"checks": [{"id": f"{g}|{c['symbol']}", "does": False, "quote": ""} for c in payload["companies"] for g in c["check_groups"]]}
    plain = TC.check_placements(_map(), _evidence, wrong, "Payments")
    assert {c["ticker"] for v in plain["value_chain"] for c in v["companies"]} == set()          # before: every company out
    asked.clear()
    out = TC.check_placements(_map(), _evidence, wrong, "Payments", held={"CI": "Card issuers and lenders", "ACQ": "Merchant acquiring"})
    assert asked == ["NEW"]
    got = {c["ticker"]: (v["layer"], c) for v in out["value_chain"] for c in v["companies"]}
    assert got["CI"][0] == "Card issuers and lenders" and got["CI"][1]["verified"] and "cards" in got["CI"][1]["what"]
    assert got["ACQ"][0] == "Merchant acquiring" and "kept from the published version" in got["ACQ"][1]["kept_member"]
    assert "NEW" not in got and out["placements"]["held"] == 2


def test_a_published_member_whose_own_words_contradict_its_group_is_asked_again():
    words = dict(WORDS, CI="The company runs hotels and resorts for holiday travellers across the coast and in inland towns.")
    asked = []

    def ask(system, text):
        payload = json.loads(text.split("CHECKS:\n", 1)[1])
        asked.extend(c["symbol"] for c in payload["companies"])
        return {"checks": [{"id": f"{g}|{c['symbol']}", "does": False, "quote": ""} for c in payload["companies"] for g in c["check_groups"]]}
    TC.check_placements(_map(), lambda syms: ({s: {"about": words[s], "industry": ""} for s in syms}, set()), ask, "Payments",
                        held={"CI": "Card issuers and lenders"})
    assert "CI" in asked


def test_keep_published_brings_back_a_member_the_check_dropped_and_leaves_a_contradicted_one_out():
    out = {"value_chain": [{"layer": "Card issuers and lenders", "description": "Banks and lenders that issue cards.", "companies": []}],
           "placements": {"dropped": [{"ticker": "CI", "name": "Card Issuer Corp", "groups": ["Card issuers and lenders"], "said": "no"},
                                      {"ticker": "HT", "name": "Hotel Co", "groups": ["Card issuers and lenders"], "said": "no"},
                                      {"ticker": "NEW", "name": "New Co", "groups": ["Card issuers and lenders"], "said": "no"}], "left_out": 3}}
    words = {"CI": WORDS["CI"], "HT": "Hotel Co runs hotels and resorts for holiday travellers across the coast and inland towns."}
    got = B.keep_published(out, {"CI": "Card issuers and consumer lenders", "HT": "Card issuers and consumer lenders"}, words.get,
                           rename={"Card issuers and lenders": {"name": "Card issuers and consumer lenders"}})
    cos = {c["ticker"]: c for c in got["value_chain"][0]["companies"]}
    assert set(cos) == {"CI"} and cos["CI"]["verified"] and cos["CI"]["kept_member"]
    assert {x["ticker"] for x in got["placements"]["dropped"]} == {"HT", "NEW"} and got["placements"]["left_out"] == 2


# ---------- 2. membership apart from the layer; the last step holds published layers ----------
def test_hold_published_puts_back_a_member_a_rule_moved_without_printed_evidence():
    vc = [{"layer": "Ferro alloys", "description": "", "companies": [{"ticker": "A", "name": "A Ltd"}]},
          {"layer": "Other metals companies", "official": True, "basis": "rest", "companies": [
              {"ticker": "B", "name": "B Ltd"}, {"ticker": "C", "name": "C Ltd", "refit": {"from": "Ferro alloys", "why": "its words say ..."}},
              {"ticker": "D", "name": "D Ltd", "refit": {"from": "Steel pipes", "why": "..."}}]}]
    pub = {"A": "Ferro alloys", "B": "Ferro alloys", "C": "Ferro alloys", "D": "Ferro alloys"}
    out, rows = B.hold_published(copy.deepcopy(vc), pub, lambda s: "", "Metals")
    got = {c["ticker"]: v["layer"] for v in out for c in v["companies"]}
    assert got == {"A": "Ferro alloys", "B": "Ferro alloys", "C": "Other metals companies", "D": "Ferro alloys"}
    assert {r["ticker"] for r in rows} == {"B", "D"}


# ---------- 3. semantic fit ----------
def test_a_way_of_earning_layer_is_named_by_what_its_companies_say_and_no_new_single_layer_is_made():
    vc = [{"layer": "Enterprise apps", "description": "", "companies": [{"ticker": "E", "name": "E"}]},
          {"layer": "Hotels, travel and consumer services", "by_model": True, "description": "", "companies": [
              {"ticker": "L1", "name": "L1"}, {"ticker": "L2", "name": "L2"}]},
          {"layer": "Payment networks and processors", "by_model": True, "description": "", "companies": [{"ticker": "P", "name": "P"}]}]
    words = {"L1": "L1 offers courses on forty languages through its learning app, with lessons for millions of learners.",
             "L2": "L2 runs an online education platform with courses and degrees from universities.",
             "P": "P processes card payments for merchants and earns a fee on each payment it processes."}
    out, rows = B.truthful_layers(copy.deepcopy(vc), {"P": "Other software companies"}, lambda s: words.get(s, ""), "Software")
    names = {v["layer"]: [c["ticker"] for c in v["companies"]] for v in out}
    assert names["Education and courses"] == ["L1", "L2"] and "Payment networks and processors" not in names
    assert [c["ticker"] for v in out if v.get("official") for c in v["companies"]] == ["P"]
    assert {r.get("renamed") or r.get("undone") for r in rows} == {"Education and courses", 1}


def test_a_misfit_goes_to_the_existing_layer_its_own_words_name_and_a_fitting_company_stays():
    vc = [{"layer": "Specialty and clinical-stage biotechs", "description": "Develop specialty medicines.", "companies": [
              {"ticker": "BIG", "name": "Big Co", "model": "manufacturing"}, {"ticker": "DEV", "name": "Dev Co", "model": "manufacturing"}]},
          {"layer": "Large pharma and biotech portfolios", "description": "", "companies": [
              {"ticker": "P1", "name": "P1", "model": "manufacturing"}, {"ticker": "P2", "name": "P2", "model": "manufacturing"}]}]
    words = {"BIG": "Big Co is an American multinational pharmaceutical company with offices in thirty countries and products in ninety.",
             "DEV": "Dev Co is a clinical-stage company developing a gene therapy for a rare muscle disease, its candidates in trials.",
             "P1": "P1 is a global pharmaceutical company selling medicines in a hundred countries.",
             "P2": "P2 is a large pharmaceutical group selling branded drugs worldwide."}
    out, rows = B.best_layer_moves(copy.deepcopy(vc), lambda s: words.get(s, ""), "Biotech", lambda s: words.get(s, ""))
    got = {c["ticker"]: v["layer"] for v in out for c in v["companies"]}
    assert got["BIG"] == "Large pharma and biotech portfolios" and got["DEV"] == "Specialty and clinical-stage biotechs"
    assert rows == [{"ticker": "BIG", "name": "Big Co", "from": "Specialty and clinical-stage biotechs", "to": "Large pharma and biotech portfolios",
                     "said": ["pharma"]}]


def test_the_contract_steps_run_only_with_the_published_memory_so_stored_versions_replay_as_before(monkeypatch):
    out = place("biotech", monkeypatch, contract=False)
    assert not (out.get("placements") or {}).get("contract", {}).get("fit")


# ---------- the change log: membership past the figures, the published memory ----------
def _dive(cos):
    return {"layers": [{"layer": lay, "companies": [{"symbol": s, "name": s} for s in syms]} for lay, syms in cos.items()]}


def test_a_member_leaving_the_figures_is_never_said_to_leave_the_theme():
    """Fails before: Jyoti Resins, Picard Medical, Meghna Infracon, Infineon ("no longer in the theme's map") and Sarepta were printed as
    removed while still members, only past the largest companies whose figures are worked out."""
    was = C.snapshot(_dive({"Layer A": ["X", "Y"]}), ["X", "Y"], 1, 55, everyone={"X": ["X", "Layer A"], "Y": ["Y", "Layer A"], "Z": ["Z", "Other"]})
    now = C.snapshot(_dive({"Layer A": ["X"]}), ["X"], 1, 56, everyone={"X": ["X", "Layer A"], "Y": ["Y", "Other"], "Z": ["Z", "Other"]})
    d = C.diff(was, now)
    assert d["removed"] == [] and d["added"] == []
    assert d["moved"] == [{"symbol": "Y", "name": "Y", "from": "Layer A", "to": "Other", "why": C.OUTSIDE_FIGURES}]
    gone = C.snapshot(_dive({"Layer A": ["X"]}), ["X"], 1, 56, everyone={"X": ["X", "Layer A"]})
    assert {r["symbol"] for r in C.diff(was, gone)["removed"]} == {"Y", "Z"}


def test_published_members_keep_a_company_removed_on_a_check_s_answer_alone():
    got = {"snap": {"layers": ["Card issuers"], "cos": {"AXP": ["AXP", 0]}, "rest": {"Z": ["Z", 0]}, "rest_layers": ["Other"]},
           "log": [{"cause": "rules", "removed": [
               {"symbol": "COF", "layer": "Card issuers", "why": "business membership: its own words were checked and don't show the work of “X”"},
               {"symbol": "OFF", "layer": "Card issuers", "why": "another business (filed under Banks)"}]}]}
    assert C.published_members(got) == {"COF": "Card issuers", "AXP": "Card issuers", "Z": "Other"}
    got["log"].append({"cause": "map", "removed": []})
    assert "COF" not in C.published_members(got)


def test_a_removal_reason_never_says_its_words_don_t_show_a_work_they_name():
    x = {"ticker": "COF", "groups": ["Card issuers and lenders"], "said": "no", "words_name": ["Card issuers and lenders"]}
    why = C.dropped_why(x)
    assert "don't show" not in why and "though its words use that group's terms" in why


# ---------- deck_check ----------
def _page(text: str) -> str:
    return text


def test_deck_check_fails_a_removal_on_a_group_the_deck_has_no_layer_of():
    deck = ("Layer 1 · Card issuers and consumer lenders\nAmerican Express Company   ...\n\f"
            "Since the previous version   On 15 Nov 2026, against the version stored before it, after a re-check under new placement rules: removed 1: "
            "Capital One Financial Corp (business membership: its own words were checked and don't show the work of “Card issuers and lenders”).\n")
    r = deck_check.check_text(deck)
    assert r["counts"]["removal unbacked"] == 1
    ok = deck.replace("“Card issuers and lenders”", "“Card issuers and consumer lenders”")
    assert deck_check.check_text(ok)["counts"]["removal unbacked"] == 0


def test_deck_check_fails_a_small_layer_whose_name_none_of_its_companies_says():
    page = ("Smaller layers\n\n Layer                            Company                   What it does                                    Revenue\n\n"
            "                                                            Duolingo offers courses on 42\n"
            " Hotels, travel and                Duolingo, Inc.                                                            $1.04 bn\n"
            " consumer services                                          languages, ranging from English, French\n\n"
            "                                                            DigitalOcean provides developers with cloud\n"
            " Data centres, hosting and         DigitalOcean Holdings     infrastructure, hosting and data centres        $901 m\n"
            " networks\n")
    r = deck_check.check_text(page)
    assert r["counts"]["layer words"] == 1 and "Hotels, travel and consumer services" in str(r["findings"])


def test_deck_check_fails_a_reason_that_says_words_don_t_show_a_work_the_deck_prints_them_naming():
    deck = ("Sarepta Therapeutics, Inc.   We are a commercial-stage biotech company with approved genetic medicines   $2.2 bn\n\f"
            "Layer 1 · Specialty and commercial biotechs\n\f"
            "Since the previous version   against the version stored before it: removed 1: Sarepta Therapeutics, Inc. (business membership: its own "
            "words were checked and don't show the work of “Commercial specialty biotechs”).\n")
    assert deck_check.check_text(deck)["counts"]["words contradict"] == 1


@pytest.mark.parametrize("key", ["payments", "biotech", "software", "metals", "retail"])
@pytest.mark.parametrize("rules", ["carried", "same"])
def test_an_empty_model_answer_moves_no_company(key, rules, monkeypatch):
    """Fails before (lane g57, the Payments inputs with the answer kept under the same rules: Block, PayPal, Coinbase and four more moved
    and a layer was renamed when the model answered nothing, while with no model the placement reproduced exactly): an empty answer is no
    answer, whether the kept answer is carried from earlier rules or kept under these."""
    if rules == "same":
        monkeypatch.setattr(B, "RULES", inputs(key)["kept_version"])
    calls = []

    def empty(system, text):
        calls.append(1)
        return {}
    a = {s: x[0] for s, x in where(place(key, monkeypatch)).items()}
    b = {s: x[0] for s, x in where(place(key, monkeypatch, ask=empty)).items()}
    assert a == b


def test_a_failing_company_is_asked_once_more_under_new_rules_and_no_more():
    """Fails before (x57: ADP in Software, asked once under earlier rules, its model still unknown, never asked again): with the published
    memory (every live placement), a company whose model is still unknown is asked once more under each rules version, bounded as before;
    one asked under these rules is not asked again, and a company with a model never is."""
    from app.intel import theme_check as C
    from tests.test_r21_deck import ABOUT, mapped

    def first(system, text):
        if system == C.MODEL_SYSTEM:
            return {"models": {}}
        return {"place": [{"symbol": "EL2", "layer": "L2"}, {"symbol": "MS2", "layer": "L0"}, {"symbol": "SH2", "layer": "L1"}, {"symbol": "XX1", "layer": "none"}],
                "models": {"EL2": "manufacturing"}}
    _, got = B.place_rest(mapped(), "Defence", ABOUT.get, ask=first)
    _, once = B.place_rest(mapped(), "Defence", ABOUT.get, ask=lambda s, t: {"models": {}}, kept=got, carried=True)
    assert "SH2" in once["reasked"] and "reasked_rules" not in once
    plain = []                                    # without the memory (a stored version replayed): never asked twice, as before
    B.place_rest(mapped(), "Defence", ABOUT.get, ask=lambda s, t: plain.append(t) or {"models": {}}, kept=once, carried=True)
    assert plain == []
    asked = []
    _, retried = B.place_rest(mapped(), "Defence", ABOUT.get, ask=lambda s, t: asked.append(t) or {"models": {}}, kept=once, carried=True,
                              published={})
    assert len(asked) == 1 and "SH2" in asked[0] and "EL2" not in asked[0] and retried["reasked_rules"] == B.RULES
    B.place_rest(mapped(), "Defence", ABOUT.get, ask=lambda s, t: pytest.fail("asked again"), kept=retried, carried=True, published={})
