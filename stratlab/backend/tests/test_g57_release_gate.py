"""Lane g57 (Release 57, the owner's review of the live R56 decks): the release gates run before decks go out.

scripts/release_gate.py replays the current placement engine offline on stored placement inputs and flags what must never ship;
scripts/deck_diff.py compares two folders of decks and flags the same classes from the decks' own text. Fixtures: the live R56 Payments
placement inputs (GET /research/theme-dive/placement-inputs, 15 Nov 2026), the live R56 Software and Biotech inputs trimmed to the
companies in question, and the pages of the live R55 and R56 Payments, Software and Biotech decks the deck gate reads (pdftotext -layout)."""
import copy
import json
import pathlib
import socket
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import deck_diff as D          # noqa: E402
import release_gate as G       # noqa: E402

FIX = pathlib.Path(__file__).parent / "fixtures" / "g57"
INPUTS = FIX / "inputs"
DECKS = FIX / "decks"


def _input(name: str) -> dict:
    return G.load(INPUTS / name)


def _fails(found, kind):
    return {f["subject"] for f in found if f["fail"] == kind}


def _company(s, name, words="", industry="", model=None, **kw):
    return {"ticker": s, "name": name, "what": words, "industry": industry, "basis": "industry", **({"model": model} if model else {}), **kw}


def _synthetic(layers: dict, dropped=(), industries=("Widgets",), evidence=None, facts=None) -> dict:
    return {"theme": "Widgets", "region": "US", "rules": 55, "kept_version": 55, "kept": {},
            "placements": {"industries": list(industries), "dropped": list(dropped)},
            "value_chain": [{"layer": k, **({"official": True} if k.startswith("Other ") else {}), "companies": v} for k, v in layers.items()],
            "evidence": evidence or {}, "facts": facts or {}}


# ---------- the placement gate: the owner's three R56 cases, from the live inputs ----------
def test_capital_one_removed_on_one_layers_mismatch_is_flagged():
    """Payments R56: Capital One left out because its words were read as not showing “Card issuers and lenders”: a layer's mismatch is
    a reason to place it elsewhere, never to remove it from the theme."""
    d = _input("payments.json")
    found = G.checks(d, d["value_chain"], d["placements"])
    removed = _fails(found, "layer-only removal")
    assert "Capital One Financial Corp (COF)" in removed
    assert {"JPMorgan Chase & Co (JPM)", "Nu Holdings Ltd. (NU)", "SoFi Technologies, Inc. (SOFI)"} <= removed
    # r58 (R58, the owner: "a category with one valid member can remain useful"): Dave's own words say "digital banking", so its one-company
    # layer is valid and no FAIL (updated on purpose; the FAIL for a member whose words don't say its layer is kept, below)
    assert "“Digital banks”" not in _fails(found, "one-company layer")


def test_duolingo_in_a_hotels_and_travel_layer_is_flagged():
    """Software R56: “Hotels, travel and consumer services” holds Duolingo and Coursera, whose own words speak of courses and
    languages; a layer whose name shares no word with its members' words is flagged, a layer that shares them is not."""
    d = _input("software_trim.json")
    found = G.checks(d, d["value_chain"], d["placements"])
    assert "“Hotels, travel and consumer services”" in _fails(found, "layer words")
    assert "“Security software subscriptions”" not in _fails(found, "layer words")


def test_sarepta_kept_by_its_industry_while_carrying_a_removal_is_flagged():
    """Biotech R56: Sarepta is in "Other biotech companies" by its official industry (Pharmaceutical Preparations) and also carries the
    check's "no" for “Commercial specialty biotechs”; the change log printed that as its removal when it left the deck's figures."""
    d = _input("biotech_trim.json")
    found = G.checks(d, d["value_chain"], d["placements"])
    assert "Sarepta Therapeutics, Inc. (SRPT)" in _fails(found, "member with removal")
    row = next(f for f in found if f["fail"] == "member with removal")
    assert "by its official industry (Pharmaceutical Preparations)" in row["detail"]
    kept = _synthetic({"Fabless chip design": [_company("N", "Nchip", "designs GPUs"), _company("M", "Mchip", "designs chips")]},
                      dropped=[{"ticker": "N", "name": "Nchip", "groups": ["Fabless chip design"], "said": "no"}])
    row = next(f for f in G.checks(kept, kept["value_chain"], kept["placements"]) if f["fail"] == "member with removal")
    assert row["subject"] == "Nchip (N)" and "in the very layer the removal names" in row["detail"]


# ---------- the placement gate: each class on its own ----------
def test_removal_without_reason_and_of_the_themes_own_industry():
    d = _synthetic({"Widget makers": [_company("A", "Alpha", "makes widgets"), _company("B", "Beta", "makes widgets")]},
                   dropped=[{"ticker": "X", "name": "Xeno"}, {"ticker": "Y", "name": "Yaw", "groups": ["Widget makers"], "said": "no"}],
                   facts={"Y": {"industry": "Industrials > Widgets"}})
    found = G.checks(d, d["value_chain"], d["placements"])
    assert "Xeno (X)" in _fails(found, "removal unreasoned")
    assert "Yaw (Y)" in _fails(found, "own industry out")
    assert "Yaw (Y)" in _fails(found, "layer-only removal")
    scoped = copy.deepcopy(d)
    scoped["placements"]["dropped"] = [{"ticker": "Y", "name": "Yaw", "said": "scope", "scope": "outside the theme's own scope"}]
    found = G.checks(scoped, scoped["value_chain"], scoped["placements"])
    assert not _fails(found, "own industry out") and not _fails(found, "layer-only removal")


def test_removal_reason_its_own_words_contradict():
    d = _synthetic({"Card issuers and lenders": [_company("A", "Alpha", "issues credit cards"), _company("B", "Beta", "a card lender")]},
                   dropped=[{"ticker": "C", "name": "Gamma", "groups": ["Card issuers and lenders"], "said": "no"}],
                   evidence={"C": "Gamma is a bank holding company whose largest business is its credit card lending."}, industries=())
    found = G.checks(d, d["value_chain"], d["placements"])
    assert "Gamma (C)" in _fails(found, "reason contradicted")


def test_one_company_layer_and_a_layer_name_with_no_word():
    d = _synthetic({"Reinsurance": [_company("A", "Alpha", "makes widget parts")],
                    "x": [_company("B", "Beta", "makes widgets"), _company("C", "Gamma", "makes widgets")],
                    "Other widget companies": [_company("D", "Delta")]})
    found = G.checks(d, d["value_chain"], d["placements"])
    # r58 (updated on purpose): a one-company layer fails when its member's own words don't say its name ("makes widget parts" under
    # "Reinsurance"); one whose words say it ("reinsures insurers") is a valid layer of one, with no median
    assert _fails(found, "one-company layer") == {"“Reinsurance”"}            # "Other ..." is no named layer
    d2 = _synthetic({"Reinsurance": [_company("A", "Alpha", "reinsures insurers")],
                     "Other widget companies": [_company("D", "Delta")]})
    assert _fails(G.checks(d2, d2["value_chain"], d2["placements"]), "one-company layer") == set()
    assert "“x”" in _fails(found, "layer words")


def test_printed_model_its_own_words_contradict_but_not_kin_or_customers():
    d = _synthetic({"Contract research": [_company("A", "Alpha", "a contract development and manufacturing organisation (CDMO)",
                                                   model="project_services"),
                                          _company("B", "Beta", "contract research services", model="project_services")],
                    "Primary steel": [_company("S", "Steelco", "manufactures steel from iron ore", model="commodity_mining"),
                                      _company("T", "Tubeco", "makes steel", model="commodity_mining")],
                    "Tower infrastructure": [_company("G", "Towerco", "owns telecom towers shared by the Wireless Telecom Operators",
                                                      model="property"),
                                             _company("H", "Mastco", "leases towers", model="property")]})
    found = _fails(G.checks(d, d["value_chain"], d["placements"]), "model contradicted")
    assert "Alpha (A)" in found                     # printed consulting, its words a contract manufacturer's
    assert "Steelco (S)" not in found               # a steelmaker "manufactures": the families of making are kin
    assert "Towerco (G)" not in found               # its customers' business is not its own


def test_layer_words_use_word_stems():
    assert G.shares("Card issuers and lenders", "a bank lending to consumers") is True
    assert G.shares("Hotels, travel and consumer services", "courses on 42 languages for consumers") is False
    assert G.shares("Other consumer services", "anything") is None          # no word of a business: not judged


# ---------- the placement gate: the diff against the stored placement ----------
def test_diff_lists_each_change_with_its_reason_and_a_rename_once():
    d = _synthetic({"Widget makers": [_company("A", "Alpha", "makes widgets"), _company("B", "Beta", "makes widgets"),
                                      _company("C", "Gamma", "makes widgets")],
                    "Gadget makers": [_company("E", "Eps", "makes gadgets"), _company("F", "Phi", "makes gadgets")],
                    "Other widget companies": [_company("D", "Delta")]})
    new = [{"layer": "Widget and part makers", "companies": [_company("A", "Alpha"), _company("B", "Beta"), _company("C", "Gamma")]},
           {"layer": "Gadget makers", "companies": [_company("E", "Eps", refit={"why": "its own words say it makes gadgets"}),
                                                    _company("D", "Delta", refit={"why": "its own words say it makes gadgets"})]},
           {"layer": "Other widget companies", "official": True, "companies": []}]
    rows = G.diff(d, new, {"dropped": [{"ticker": "F", "name": "Phi", "groups": ["Gadget makers"], "said": "no"}]})
    kinds = {(r["kind"], r["symbol"] or r["name"]) for r in rows}
    assert ("renamed", "“Widget makers” -> “Widget and part makers”") in kinds
    assert not any(r["kind"] == "moved" and r["symbol"] in "ABC" for r in rows)     # a rename is no move of its companies
    moved = next(r for r in rows if r["symbol"] == "D")
    assert (moved["kind"], moved["from"], moved["to"]) == ("moved", "Other widget companies", "Gadget makers")
    assert moved["reason"] == "its own words say it makes gadgets"
    left = next(r for r in rows if r["symbol"] == "F")
    assert left["kind"] == "left" and "don't show the work of “Gadget makers”" in left["reason"]


def test_gate_runs_the_engine_offline_on_the_live_inputs(monkeypatch):
    """The whole gate on the live R56 Payments inputs: no network (a connect is refused inside, put back after), the stub model answers
    nothing, every change carries a kind and a reason field, the stored side's FAILs are reported."""
    seen = []
    real = G.B.place_rest

    def spy(*a, **k):
        with pytest.raises(OSError):
            socket.create_connection(("example.com", 443), timeout=1)
        seen.append(k.get("ask"))
        return real(*a, **k)
    monkeypatch.setattr(G.B, "place_rest", spy)
    d = _input("payments.json")
    with G.offline():
        g = G.gate(d)
        n = len(seen)
        nomodel, asked = G.engine(d, "none")
    assert asked == 0 and nomodel.get("value_chain") and set(seen[n:]) == {None}          # --model none: no model at all
    assert seen[:n] and all(isinstance(x, G._NoAnswer) for x in seen[:n])
    assert socket.create_connection is not None and getattr(socket.create_connection, "__name__", "") != "refuse"
    assert all({"kind", "reason", "from", "to"} <= set(r) for r in g["changes"])
    assert g["share"]["stored"][1] == len(G.rows_of(d["value_chain"]))
    assert ("layer-only removal", "Capital One Financial Corp (COF)") in {(f["fail"], f["subject"]) for f in g["fails"]}


def test_exit_codes(tmp_path, monkeypatch, capsys):
    assert G.main([str(tmp_path / "missing")]) == 2
    assert G.main([str(tmp_path)]) == 2                         # no inputs in it
    (tmp_path / "payments.json").write_text((INPUTS / "payments.json").read_text())
    assert G.main([str(tmp_path)]) == 1                         # the live R56 Payments inputs hold FAILs
    assert "layer-only removal" in capsys.readouterr().out
    monkeypatch.setattr(G, "gate", lambda d, model="stub": {"theme": d["theme"], "region": "US", "rules": 55, "engine_rules": 55, "asked": 0,
                                                            "share": {"stored": [1, 1], "engine": [1, 1]}, "changes": [], "fails": []})
    assert G.main([str(tmp_path)]) == 0
    capsys.readouterr()
    assert G.main([str(tmp_path), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["payments"]["fails"] == []


# ---------- the deck gate: R55 against R56 must flag Capital One, Sarepta and Duolingo ----------
@pytest.fixture(scope="module")
def r55_r56():
    return {k: D.diff_theme(D.DC.pages_of(str(DECKS / "r55" / f"{k}.txt")), D.DC.pages_of(str(DECKS / "r56" / f"{k}.txt")))
            for k in ("payments", "software", "biotech")}


def test_deck_gate_flags_capital_one(r55_r56):
    g = r55_r56["payments"]
    assert "Capital One Financial Corp" in _fails(g["fails"], "layer-only removal")
    assert any(r["kind"] == "removed" and r["company"] == "Capital One Financial Corp" and "Card issuers and lenders" in r["reason"]
               for r in g["changes"])
    assert "“Digital banks”" in _fails(g["fails"], "one-company layer")


def test_deck_gate_flags_sarepta(r55_r56):
    g = r55_r56["biotech"]
    assert "Sarepta Therapeutics, Inc." in _fails(g["fails"], "layer-only removal")
    assert "Sarepta Therapeutics, Inc." in _fails(g["fails"], "own industry out")      # the R55 deck: filed under Pharmaceuticals


def test_deck_gate_flags_duolingo(r55_r56):
    g = r55_r56["software"]
    assert "“Hotels, travel and consumer services”" in _fails(g["fails"], "layer words")
    assert "“Hotels, travel and consumer services”" in _fails(g["fails"], "one-company layer")
    moved = [r for r in g["changes"] if r["kind"] == "moved" and r["company"] == "Duolingo, Inc."]
    assert moved and moved[0]["to"] == "Hotels, travel and consumer services"
    assert not any(r["kind"] == "table moved" and r["company"].startswith("Meta Platforms") for r in g["changes"])  # the renamed layer


def test_deck_gate_reads_the_decks_tables(r55_r56):
    pages = D.DC.pages_of(str(DECKS / "r56" / "payments.txt"))
    counts = D.layer_counts(pages)
    assert counts["Card issuers and consumer lenders"] == 3 and counts["Digital banks"] == 1     # a wrapped name, "(adjacent)" off
    table = D.appendix(D.DC.pages_of(str(DECKS / "r56" / "software.txt")))
    assert table["Duolingo, Inc."] == "Hotels, travel and consumer services"
    assert table["Elastic N.V."] == "Data and developer infrastructure software"                # a short name given in full
    rows = D.log_rows("On 1 Jan, against the version stored before it: removed 2: A Inc. (why one), B, Inc. (why two); moved between "
                      "layers 1: C Ltd (from “X” to “Y”: its words) and 3 more; layers changed 1: “X” renamed “Z”.")
    assert rows["removed"] == [("A Inc.", "why one"), ("B, Inc.", "why two")]
    assert rows["moved"] == [("C Ltd", "from “X” to “Y”: its words")] and rows["unnamed"] == [("moved", 3)]


def test_deck_gate_exit_codes(tmp_path):
    assert D.main([str(tmp_path / "a"), str(tmp_path / "b")]) == 2
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    assert D.main([str(tmp_path / "a"), str(tmp_path / "b")]) == 2
    for side in ("a", "b"):
        (tmp_path / side / "software.txt").write_text((DECKS / ("r55" if side == "a" else "r56") / "software.txt").read_text())
    assert D.main([str(tmp_path / "a"), str(tmp_path / "b")]) == 1
    (tmp_path / "b" / "software.txt").write_text((DECKS / "r55" / "software.txt").read_text())
    assert D.main([str(tmp_path / "a"), str(tmp_path / "b")]) == 0         # the R55 deck against itself: no FAIL
    g = D.diff_theme(*[D.DC.pages_of(str(DECKS / "r55" / "software.txt"))] * 2)
    assert g["fails"] == [] and not [r for r in g["changes"] if r["kind"].startswith(("table", "layer +", "layer -"))]
    assert [r["kind"] for r in g["changes"]] == ["layer"]                   # only the R55 deck's own change-log row (from R54)
