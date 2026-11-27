"""Lane t56 (Release 55 review, the owner's review of the live R55 decks): taxonomy regression protection, and listing apart from business
membership, proven on exact replays of the live inputs (GET /research/theme-dive/placement-inputs, read 15 Nov 2026 under RULES 54, kept
version 54: tests/fixtures/themes_live/inputs_r55/<theme>.json, Metals and mining IN, Consumer retail US, Payments and fintech US).

The inputs hold the R55 placement as stored, its snapshot ("previous") and the change log's moves ("moved_before"). The R55 re-check itself
is replayed from them with `previous` set back to the R54 snapshot (the R55 log's moves undone, as the live R55 decks' "Since the previous
version" rows print them: inputs_r55/moved.json "r55_moves") and `moved_before` as the log stood before R55 (the R55 entry's moves replaced
by the R54 entry's, which moved those companies back into the restored layer from where R53 had put them: "r54_src"). The split's layer
names the kept answer holds are applied as on live (their key is a signature of the members the live split saw).

1 P0 the taxonomy guard: a named layer of five or more companies that a re-check would lose comes back with its companies that still fit,
  as the last step after every rule that moves companies; a fall of five points or more in the informative share is guarded; every removal
  of an established category is said with where its companies went (change log, deck, Admin).
  Why c54's guard did not hold on R55: it read every logged move back, so the R54 restore's own moves INTO "Aluminium" (and "Catalog and
  mail-order houses") counted its companies as of "Other": the layer had no companies in the version before, and was lost again.
2 P1 listing eligibility apart from business membership: a company the map's check leaves out says it was a business-membership decision
  (its own words checked), its listing line said apart; a removal for a listing reason has its own heading.
"""
import json
import pathlib
import sys

import pytest

from app.intel import theme_base as B
from app.intel import theme_changes as C
from app.intel import theme_check as TC
from tests import test_exact_replay as X

LIVE = pathlib.Path(__file__).parent / "fixtures" / "themes_live" / "inputs_r55"
MOVED = json.loads((LIVE / "moved.json").read_text())
ORIGIN = {"metals": {"JSL": "Specialty steel and fabricated steel products"}, "payments": {"FLYW": "Card networks"}}
STALE = ("out_why", "on_industry", "refit", "own_goods", "by_words", "unfit")
ALUMINIUM = ["BMAL", "HINDALUMI", "JIVIAL", "KANISHK", "MAANALU", "MAITRI", "MMP", "MSAFE", "PALCO", "PGFOILQ", "SACHEMT", "SUDAI",
             "MANAKALUCO"]          # the 13 of "Aluminium" on the live R54 Metals deck, removed by the R55 re-check (its log's rows)
CATALOG = ["CAHO", "DDL", "LVLU", "LUXE", "NXH", "QVCG"]      # the 6 of "Catalog and mail-order houses" on the live R54 Consumer retail deck
REST = {"metals": "Other metals and mining companies", "retail": "Other consumer retail companies"}
LOST = {"metals": "Aluminium", "retail": "Catalog and mail-order houses"}
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


def r55_inputs(key: str) -> dict:
    """The inputs the live R55 re-check read: the R54 snapshot, and the log's moves before the R55 entry."""
    d = inputs(key)
    prev, mb = dict(d["previous"]), dict(d["moved_before"])
    for s_, (a, b) in MOVED["r55_moves"][key].items():
        assert prev.get(s_) == b, (s_, prev.get(s_), b)          # the R55 snapshot holds each move as the R55 deck prints it
        prev[s_] = a
        if a == LOST[key]:
            mb[s_] = [MOVED["r54_src"][key][s_], a]              # the R54 restore's move back into the layer
        else:
            mb.pop(s_, None)
    d["previous"], d["moved_before"] = prev, mb
    return d


def place(d: dict, key: str, monkeypatch, **over) -> dict:
    sig = ((d.get("kept") or {}).get("model_names") or {}).get("sig")
    if sig:
        monkeypatch.setattr(B, "model_names_signature", lambda layers: sig)
    m = X.pre_map(json.loads(json.dumps(d)), ORIGIN.get(key, {}), {})
    kw = dict(previous=d["previous"], off_before=d.get("off_before") or {}, moved_before=d.get("moved_before") or {})
    kw.update(over)
    out, _ = B.place_rest(m, d["theme"], lambda s: d["evidence"].get(s), ask=None, kept=d["kept"], facts_of=lambda s: d["facts"].get(s) or {},
                          figures_of=lambda s: (d.get("figures") or {}).get(s) or {}, carried=d["kept_version"] != B.RULES, **kw)
    return out


def layers(vc) -> dict:
    return {c["ticker"]: ("Other" if v.get("official") and v.get("basis") == "rest" else X._HALF.sub("", v["layer"])) for v in vc for c in v["companies"]}


def _c54_previous(previous, moved_before):
    """c54's reading of the version before (theme_base.restore_vanished on R55): every logged move read back."""
    prev = dict(previous or {})
    for s_, mv in (moved_before or {}).items():
        if isinstance(mv, (list, tuple)) and len(mv) == 2 and mv[0] and B._HALF_RX.sub("", str(prev.get(s_) or mv[1])) == B._HALF_RX.sub("", str(mv[1])):
            prev[s_] = mv[0]
    return prev


# ---------- 1 P0 the taxonomy guard ----------
@pytest.mark.parametrize("key,members", [("metals", ALUMINIUM), ("retail", CATALOG)])
def test_the_lost_layer_comes_back_on_the_live_r55_re_check(key, members, monkeypatch):
    """Fails before: the live R55 re-check lost Metals' "Aluminium" (13 companies, 12 to "Other", Manaksia Aluminium to the steel pipe
    makers; informative 52 of 66 to 39 of 66) and Consumer retail's "Catalog and mail-order houses" (6, to "Other"; 75 of 98 to 69 of 98),
    the very layers the R54 re-check had restored. Replayed on the inputs the R55 re-check read, the layer comes back with all of them."""
    d = r55_inputs(key)
    live = layers(inputs(key)["value_chain"])
    assert LOST[key] not in set(live.values()) and all(live[s_] != LOST[key] for s_ in members)
    out = place(d, key, monkeypatch)
    got = layers(out["value_chain"])
    assert sorted(s_ for s_, x in got.items() if x == LOST[key]) == sorted(members)
    gone = next(x for x in out["placements"]["layers_gone"] if x["layer"] == LOST[key])
    assert gone["before"] == len(members) and gone["restored"] == len(members) and gone["why"].startswith("restored:")
    if key == "metals":                                        # back from the steel pipe makers it had joined on a word ("supplies to the Steel")
        assert live["MANAKALUCO"] == "Steel and alloy pipe and tube makers" and got["MANAKALUCO"] == "Aluminium"
        assert got["ARFIN"] == "Steel and alloy pipe and tube makers"          # not of R54's "Aluminium": not brought in


@pytest.mark.parametrize("key,members", [("metals", ALUMINIUM), ("retail", CATALOG)])
def test_the_cause_c54_read_the_r54_restore_s_own_moves_back(key, members):
    """The cause, on the inputs the R55 re-check read: c54's reading of the version before (every logged move read back) took the R54
    restore's moves into the layer ("Other" -> "Aluminium") as moves out of it, so the layer had none of its R54 companies: only those an
    older re-check (R53) had moved out (Retail: the live R55 "layers_gone" row, "before" 5, none restored). Read now, it has its R54 ones."""
    d = r55_inputs(key)
    c54 = _c54_previous(d["previous"], d["moved_before"])
    now = B.previous_published(d["previous"], d["moved_before"], theme=d["theme"])
    assert sorted(s_ for s_, x in now.items() if x == LOST[key]) == sorted(members)
    # Metals: only Arfin India (an R53 move out of the layer), one company, under five: no layer to restore; Retail: the five online
    # retailers R53 had moved out, all kept elsewhere by their words: none restored
    assert sorted(s_ for s_, x in c54.items() if x == LOST[key]) == (["ARFIN"] if key == "metals" else ["AKA", "HOUR", "LITB", "RVLV", "SFIX"])
    if key == "retail":
        assert inputs(key)["placements"]["layers_gone"][0]["before"] == 5 and inputs(key)["placements"]["layers_gone"][0]["restored"] == 0
        assert not set(members) & {s_ for s_, x in c54.items() if x == LOST[key]}


@pytest.mark.parametrize("key,members", [("metals", ALUMINIUM), ("retail", CATALOG)])
def test_the_next_re_check_of_the_live_inputs_restores_the_layer_from_the_log(key, members, monkeypatch):
    """The live inputs as served (the R55 snapshot no longer has the layer): with the moves of the one re-check that removed it
    (theme_changes.lost_moves, the R55 entry's rows), the next re-check restores it with exactly its R54 companies: never Arfin India or the
    five online retailers an older re-check (R53) had moved out and later versions kept elsewhere."""
    d = inputs(key)
    out = place(d, key, monkeypatch, moved_out=MOVED["r55_moves"][key])
    got = layers(out["value_chain"])
    assert sorted(s_ for s_, x in got.items() if x == LOST[key]) == sorted(members)
    log = {"snap": {"layers": sorted(set(d["previous"].values()))},
           "log": [{"moved": [{"symbol": s_, "from": a, "to": b} for s_, (a, b) in MOVED["r55_moves"][key].items()]}]}
    older = [{"moved": [{"symbol": "ARFIN", "from": "Aluminium", "to": "Steel and alloy pipe and tube makers"}] if key == "metals" else
              [{"symbol": "AKA", "from": "Catalog and mail-order houses", "to": "Online stock-holding retailers"}]}]
    lost = C.lost_moves({**log, "log": older + log["log"]})
    assert lost == {s_: [a, b] for s_, (a, b) in MOVED["r55_moves"][key].items() if a == LOST[key]}


def test_previous_published_never_reads_a_move_into_a_layer_back_as_a_move_out():
    """The R54 restore logged "Other" -> "Aluminium" for each company it brought back; read back, the company was of "Other" and the layer
    had none. A logged move is read back only out of a layer the snapshot no longer has."""
    prev = {"A": "Aluminium", "B": "Aluminium", "P": "Pipes"}
    mb = {"A": ["Other metals and mining companies", "Aluminium"], "B": ["Pipes", "Aluminium"], "P": ["Aluminium", "Pipes"]}
    assert B.previous_published(prev, mb, theme="Metals and mining") == prev
    snap = {"A": "Other metals and mining companies", "P": "Pipes"}               # the snapshot lost "Aluminium"
    assert B.previous_published(snap, {"A": ["Aluminium", "Other metals and mining companies"], "P": ["Aluminium", "Pipes"]},
                                theme="Metals and mining") == {"A": "Aluminium", "P": "Aluminium"}
    assert B.previous_published(snap, {"A": ["Aluminium", "Other metals and mining companies"], "P": ["Aluminium", "Pipes"]},
                                moved_out={"A": ["Aluminium", "Other metals and mining companies"]}, theme="Metals and mining") == \
        {"A": "Aluminium", "P": "Pipes"}


def _co(s_, **k):
    return {"ticker": s_, "name": f"{s_} Ltd", "industry": k.pop("industry", "Aluminium"), **k}


def test_a_renamed_layer_is_not_lost_and_a_verified_or_rule_placed_company_stays():
    """A layer whose companies went, half or more, to one layer new to this version was renamed by the map: nothing restored, no duplicate.
    A member whose words were checked for its new layer, or that a rule moved there with its reason, stays; one a word match moved does not."""
    vc = [{"layer": "Aluminium makers", "description": "", "companies": [_co(s_) for s_ in "ABCDE"]},
          {"layer": "Other metals companies", "official": True, "basis": "rest", "companies": []}]
    out, gone = B.restore_vanished(json.loads(json.dumps(vc)), {s_: "Aluminium" for s_ in "ABCDE"}, lambda s: "", "Metals")
    assert gone == [] and [v["layer"] for v in out] == ["Aluminium makers", "Other metals companies"]
    pipes = {"layer": "Steel pipes", "description": "", "companies": [
        _co("V", verified=True, placed="ai", moved=True), _co("R", placed="ai", refit={"from": "X", "to": "Steel pipes", "why": "w"}),
        _co("W", placed="ai", moved=True), _co("P", industry="Iron & Steel Products")]}
    rest = {"layer": "Other metals companies", "official": True, "basis": "rest", "companies": [_co(s_) for s_ in "FGH"]}
    prev = {s_: "Aluminium" for s_ in "VRWFGH"}
    prev["P"] = "Steel pipes"
    out, gone = B.restore_vanished(json.loads(json.dumps([pipes, rest])), prev, lambda s: "", "Metals")
    got = layers(out)
    assert sorted(s_ for s_, x in got.items() if x == "Aluminium") == ["F", "G", "H", "W"]
    assert got["V"] == got["R"] == got["P"] == "Steel pipes"
    assert gone[0]["stayed"] == {"its own words were checked to show the work of the layer it is in": 1,
                                 "a rule moved it to the layer it is in, with its reason": 1}
    assert "(the others: " in gone[0]["why"]


def test_a_fall_of_five_points_sends_back_the_companies_whose_own_words_say_their_layer():
    """share_guard: 6 of 8 informative before, 3 of 8 now; of the three in "Other" whose layer is still there, the one whose own words say
    what it sells goes back, the one a rule moved there with its reason stays, and one filed under the layer's industry whose own words say
    another business stays (its industry label alone is no evidence)."""
    words = {"A": "A Ltd makes ferro manganese and silico manganese alloys.", "B": "B Ltd makes ferro manganese alloys.",
             "C": "C Ltd now trades coal and runs warehouses."}
    vc = [{"layer": "Ferro alloys", "description": "", "companies": [_co("F1", industry="Ferro"), _co("F2", industry="Ferro"), _co("F3", industry="Ferro")]},
          {"layer": "Other metals companies", "official": True, "basis": "rest",
           "companies": [_co("A", industry="Ferro"), _co("B", industry="Ferro", refit={"from": "Ferro alloys", "to": "", "why": "w"}),
                         _co("C", industry="Ferro"), _co("O1"), _co("O2")]}]
    prev = {s_: "Ferro alloys" for s_ in ("F1", "F2", "F3", "A", "B", "C")}
    prev.update({"O1": "Other metals companies", "O2": "Other metals companies"})
    out, row = B.share_guard(json.loads(json.dumps(vc)), prev, lambda s: words.get(s, ""), "Metals")
    got = layers(out)
    assert got["A"] == "Ferro alloys" and got["B"] == got["C"] == "Other"
    assert row["before"] == [6, 8] and row["after"] == [3, 8] and row["now"] == [4, 8] and row["returned"] == 1
    assert row["stayed"] == {"a rule moved it to “Other”, with its reason": 1, "its own words don't say what its layer sells": 1}
    prev2 = dict(prev, A="Other metals companies", B="Other metals companies", C="Other metals companies")      # 3 of 8 before: no fall
    assert B.share_guard(json.loads(json.dumps(vc)), prev2, lambda s: words.get(s, ""), "Metals") == (vc, None)


FIXTURES = sorted(p for p in (LIVE.parent).glob("inputs_r*/*.json") if p.name not in ("moved.json", "recovered.json"))


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: f"{p.parent.name}/{p.stem}")
def test_the_guard_moves_no_company_of_any_stored_input_against_its_own_previous_version(path, monkeypatch):
    """Golden safety: every stored placement-input fixture (inputs_r39 to inputs_r55, both markets) placed with its own previous version
    gives every company the layer it gets with the guard's new steps off (the R55 losses aside: their inputs' previous version is the R55
    snapshot itself, which no longer has the layer, so nothing is restored without the R55 log's moves)."""
    d = json.loads(path.read_text())
    d = d.get("data", d)
    for v in d["value_chain"]:
        v["companies"] = [{k: x for k, x in c.items() if k not in STALE + ("sold_by",)} for c in v["companies"]]
    moved = [c["ticker"] for v in d["value_chain"] for c in v["companies"] if c.get("moved") and not c.get("placed")]

    def run():
        m = X.pre_map(json.loads(json.dumps(d)), {s_: "?" + s_ for s_ in moved}, {})
        out, _ = B.place_rest(m, d["theme"], lambda s: (d.get("evidence") or {}).get(s), ask=None, kept=d.get("kept") or {},
                              facts_of=lambda s: (d.get("facts") or {}).get(s) or {}, figures_of=lambda s: (d.get("figures") or {}).get(s) or {},
                              carried=d.get("kept_version") != B.RULES, previous=d.get("previous") or {}, off_before=d.get("off_before") or {})
        return layers(out["value_chain"])
    now = run()
    with monkeypatch.context() as mp:
        mp.setattr(B, "share_guard", lambda vc, *a, **k: (vc, None))
        mp.setattr(B, "restore_vanished", lambda vc, *a, **k: (vc, []))
        off = run()
    assert now == off


def test_every_removal_of_an_established_category_is_said_with_where_its_companies_went_and_a_fall_with_why():
    """The coverage control (the deck's coverage flag and the Admin check): a layer of five or more gone is said wherever its companies
    went, with where; a fall of five points or more (eight before) with why."""
    was = C.snapshot({"layers": [{"layer": "Aluminium", "companies": [{"symbol": s_} for s_ in "ABCDEF"]},
                                 {"layer": "Pipes", "companies": [{"symbol": "P"}]},
                                 {"layer": "Online", "companies": [{"symbol": "Q"}]}], "coverage": {"informative": 8, "placed": 10}}, [])
    now = {"layers": [{"layer": "Pipes", "companies": [{"symbol": "P"}, {"symbol": "A"}, {"symbol": "B"}, {"symbol": "C"}]},
                      {"layer": "Online", "companies": [{"symbol": "Q"}, {"symbol": "D"}]},
                      {"layer": "Other metals companies", "companies": [{"symbol": "E"}, {"symbol": "F", "refit": {"from": "x", "why": "y"}}]}],
           "placements": {"layers_gone": [{"layer": "Aluminium", "before": 6, "restored": 0, "why": "none restored: 2 of its 6 ..."}]}}
    lost = C.lost_layers(was, now)
    assert lost == [{"layer": "Aluminium", "n": 6, "went": {"Pipes": 3, "Online": 1, "Other metals companies": 2}}]
    cov = {"informative": 6, "placed": 10, "share": 60}
    ctl = C.coverage_control(cov, was, now)
    assert ctl["fell"]["why"] == {"its layer “Aluminium” is gone": 2}
    line = C.control_line({**cov, "control": ctl})
    assert "20 points fewer, a fall of 5 or more. Why: its layer “Aluminium” is gone: 2." in line
    assert "“Aluminium” (6 companies: 3 to “Pipes”, 2 to “Other metals companies”, 1 to “Online”; none restored: 2 of its 6 ...)" in line
    assert not deck_check.check_text(f"Coverage flag {line}")["counts"]["share fall unsaid"]
    assert not deck_check.check_text(f"Coverage flag {line}")["counts"]["layer vanished"]


# ---------- deck_check ----------
def test_deck_check_fails_the_live_r55_metals_retail_and_payments_lines():
    """The live R55 deck lines (pdftotext of the decks): Metals' lost "Aluminium" said with no restore or reason, and its fall with no why;
    Retail's "removed (6 companies ...), none restored: 0 of its 5" (a reason of another count); Payments' Adyen "no longer in the theme's
    map" (neither a listing nor a business reason)."""
    metals = ("Coverage flag 59% 39 of 66 companies placed (59%) are in informative layers, against 52 of 66 (79%) in the previous live "
              "placement: 20 points fewer, a fall of 8 or more. Layers of the previous live placement gone, their companies taken by no new "
              "layer: “Aluminium” (13 companies). Since the previous version 14 On 14 Nov 2026, against the version stored before it: layers "
              "changed 1: “Aluminium” removed (13 companies: 12 to “Other metals and mining companies”, 1 to “Steel and alloy pipe and tube makers”).")
    r = deck_check.check_text(metals)["counts"]
    assert r["layer vanished"] == 2 and r["share fall unsaid"] == 1 and r["layer lost unsaid"] == 0       # c54's rule passed it
    retail = ("Since the previous version 6 On 14 Nov 2026, against the version stored before it: layers changed 1: “Catalog and mail-order "
              "houses” removed (6 companies: 6 to “Other consumer retail companies”), none restored: 0 of its 5 companies' own words or official "
              "industry still say what it sells, fewer than 3.")
    assert deck_check.check_text(retail)["counts"]["layer vanished"] == 1
    payments = ("Since the previous version 1 On 14 Nov 2026, against the version stored before it, after a re-check under new placement "
                "rules: removed 1: Adyen Nv-Unspon ADR (no longer in the theme's map).")
    assert deck_check.check_text(payments)["counts"]["removal unnamed"] == 1
    fixed = payments.replace("(no longer in the theme's map)", "(" + C.dropped_why({"said": "no", "groups": ["Merchant acquiring and processing"],
                                                                                 "listing": "listed as an unsponsored depositary receipt of Adyen",
                                                                                 "issuer": "Adyen"}) + ")")
    assert deck_check.check_text(fixed)["counts"]["removal unnamed"] == 0
    named = ("Since the previous version: removed 2: High Energy Batteries (India) Ltd, Indo National Ltd (outside the theme's definition: "
             "batteries); X Ltd (another business (filed under Y)).")
    assert deck_check.check_text(named)["counts"]["removal unnamed"] == 0


# ---------- 2 P1 listing apart from business membership ----------
ADYEN_WORDS = ("Adyen N.V. is a Dutch payment company with the status of an acquiring bank that allows businesses to accept e-commerce, "
               "mobile, and point-of-sale payments.")          # a representative encyclopedia opening: the stored words aren't served


def _map():
    return {"sector": "Payments and fintech", "value_chain": [
        {"layer": "Merchant acquiring and processing", "description": "Processing card payments for merchants.",
         "companies": [{"name": "Adyen Nv-Unspon ADR", "ticker": "ADYEY"}, {"name": "Fiserv Inc", "ticker": "FISV"}]}], "sub_themes": []}


def _ask(yes: dict):
    def ask(system, text):
        body = json.loads(text.split("CHECKS:\n", 1)[1])
        return {"checks": [{"id": f"{g}|{c['symbol']}", "does": f"{g}|{c['symbol']}" in yes, "quote": yes.get(f"{g}|{c['symbol']}", "")}
                           for c in body["companies"] for g in c["check_groups"]]}
    return ask


def test_a_company_the_map_s_check_leaves_out_says_it_was_a_business_decision_its_listing_line_apart():
    """Fails before: the check's "no" left Adyen out with no record, and the change log said "no longer in the theme's map". Now the check
    records it ("dropped": what it said, the groups, its listing line and issuer), the snapshot keeps the reason and the log's removal says
    it is a business-membership decision of its own words, the listing line said apart as removing nothing."""
    ev = lambda syms: ({"ADYEY": {"about": ADYEN_WORDS, "industry": ""}, "FISV": {"about": "Fiserv provides payment processing for merchants.",
                                                                              "industry": ""}}, set())
    out = TC.check_placements(_map(), ev, _ask({"L0|FISV": "provides payment processing for merchants"}), "Payments and fintech")
    assert [c["ticker"] for c in out["value_chain"][0]["companies"]] == ["FISV"]
    drop = out["placements"]["dropped"]
    # p57 (R56 review, updated on purpose): its words ("an acquiring bank") use the group's terms, recorded so its reason never says they
    # don't show that work
    assert drop == [{"ticker": "ADYEY", "name": "Adyen Nv-Unspon ADR", "groups": ["Merchant acquiring and processing"], "said": "no",
                     "words_name": ["Merchant acquiring and processing"],
                     "listing": "listed as an unsponsored depositary receipt of Adyen", "issuer": "Adyen"}]
    was = C.snapshot({"layers": [{"layer": "Merchant acquiring and processing", "companies": [{"symbol": "ADYEY", "name": "Adyen Nv-Unspon ADR"},
                                                                                            {"symbol": "FISV", "name": "Fiserv"}]}]}, ["ADYEY", "FISV"])
    now = C.snapshot({"layers": [{"layer": "Merchant acquiring and processing", "companies": [{"symbol": "FISV", "name": "Fiserv"}]}],
                      "placements": out["placements"]}, ["FISV"])
    why = C.diff(was, now)["removed"][0]["why"]
    assert why == ("business membership: the check's answer on its own words (read as Adyen's) was no for “Merchant acquiring and "
                   "processing”, though its words use that group's terms; listing: listed as an unsponsored depositary receipt of Adyen, "
                   "which removes no company")          # p57 (updated on purpose): the answer said as an answer, its words naming the work
    # a "yes" its words don't back is told apart from a "no"
    out = TC.check_placements(_map(), ev, _ask({"L0|ADYEY": "processes payments for the largest merchants worldwide",
                                                "L0|FISV": "provides payment processing for merchants"}), "Payments and fintech")
    assert out["placements"]["dropped"][0]["said"] == "unbacked"


def test_a_previous_member_is_kept_when_the_check_s_yes_only_lacked_backing_words():
    """keep_confirmed: a member of the previous version (Adyen, added by R54) stays, not confirmed this time and saying why, when this
    check's "yes" wasn't backed by its words (no evidence against it); a clear "no", or a company never a member, stays out with its reason."""
    m = _map()
    out = {"value_chain": [{**m["value_chain"][0], "companies": [{"ticker": "FISV", "name": "Fiserv Inc", "verified": True}]}], "sub_themes": [],
           "placements": {"left_out": 1, "placed": 1, "unconfirmed": 0,
                          "dropped": [{"ticker": "ADYEY", "name": "Adyen Nv-Unspon ADR", "groups": ["Merchant acquiring and processing"], "said": "unbacked"}]}}
    got = B.keep_confirmed(json.loads(json.dumps(out)), m, {"ADYEY": "member", "FISV": "confirmed"})
    adyen = next(c for c in got["value_chain"][0]["companies"] if c["ticker"] == "ADYEY")
    assert adyen["verified"] is False and adyen["kept_member"].startswith("the version before had it as a member;") and "removes nothing" in adyen["kept_member"]
    assert B.keep_confirmed(json.loads(json.dumps(out)), m, {"ADYEY": "confirmed"})["placements"]["kept_members"][0]["why"].startswith(
        "the version before had its own words checked")
    assert "dropped" not in got["placements"] and got["placements"]["placed"] == 2 and got["placements"]["left_out"] == 0
    assert B.keep_confirmed(json.loads(json.dumps(out)), m, {}) == out
    no = json.loads(json.dumps(out))
    no["placements"]["dropped"][0]["said"] = "no"
    assert B.keep_confirmed(no, m, {"ADYEY": "member"}) == no


def test_a_removal_for_a_listing_reason_has_its_own_heading_in_the_deck_s_change_log():
    from app import deck as K
    v = {"coverage": {"other_name": "Other payments companies"},
         "changes": {"entries": [{"d": "2026-11-16", "cause": "rules", "counts": {"removed": 2, "added": 0, "moved": 0, "layers": 0, "restated": 0},
                                  "removed": [{"symbol": "ADYEY", "name": "Adyen Nv-Unspon ADR", "why": C.dropped_why({"said": "no", "groups": ["M"]})},
                                              {"symbol": "XO", "name": "X OTC line", "why": "listing: an over-the-counter line with no filings"}],
                                  "added": [], "moved": [], "layers": []}]}}
    row = K.cohort_row(v)
    assert row[1] == "2"
    assert "removed for a listing reason 1: X OTC line (an over-the-counter line with no filings)" in row[2]
    assert "removed 1: Adyen Nv-Unspon ADR (business membership: its own words were checked and don't show the work of “M”)" in row[2]
    assert not deck_check.check_text("Since the previous version " + row[2])["counts"]["removal unnamed"]


def test_payments_live_inputs_replay_unchanged_by_the_guard(monkeypatch):
    """The live R55 Payments inputs: no layer of the previous version is lost and the guard moves no company (the replay's own two
    differences, COIN and PYPL, were there before, v55); Adyen is not in the inputs (the check left it out on R55, as the deck's log says)."""
    d = inputs("payments")
    assert "ADYEY" not in {c["ticker"] for v in d["value_chain"] for c in v["companies"]}
    out = place(d, "payments", monkeypatch)
    assert "layers_gone" not in (out.get("placements") or {}) and not (out["placements"].get("share_guard") or {}).get("returned")
    with monkeypatch.context() as mp:
        mp.setattr(B, "share_guard", lambda vc, *a, **k: (vc, None))
        mp.setattr(B, "restore_vanished", lambda vc, *a, **k: (vc, []))
        assert layers(place(d, "payments", mp)["value_chain"]) == layers(out["value_chain"])


def test_the_rules_version_and_the_new_inputs():
    from app import deck as K
    from app.intel import theme_data as D
    from app.intel import theme_routes as TR
    assert B.RULES == 80 and TR.PLACE_CARRY[78] == 77 and TR.PLACE_CARRY[77] == 76 and TR.PLACE_CARRY[76] == 75 and TR.PLACE_CARRY[75] == 74 and TR.PLACE_CARRY[74] == 73 and TR.PLACE_CARRY[73] == 72 and TR.PLACE_CARRY[72] == 71 and TR.PLACE_CARRY[71] == 70 and TR.PLACE_CARRY[70] == 69 and TR.PLACE_CARRY[69] == 68 and TR.PLACE_CARRY[68] == 67 and TR.PLACE_CARRY[67] == 66 and TR.PLACE_CARRY[66] == 65 and TR.PLACE_CARRY[65] == 64 and TR.PLACE_CARRY[64] == 63 and TR.PLACE_CARRY[63] == 62 and TR.PLACE_CARRY[62] == 61 and TR.PLACE_CARRY[61] == 60 and TR.PLACE_CARRY[60] == 59 and TR.PLACE_CARRY[59] == 58 and TR.PLACE_CARRY[58] == 57 and TR.PLACE_CARRY[57] == 56 and TR.PLACE_CARRY[56] == 55 and TR.PLACE_CARRY[55] == 54 and K.THEME_DECK_VERSION == 97 and D.DIVE_TEXT == 58 and TR.EARLIER_MAX == 35  # data100 (changed on purpose, company data wrong at the source, 27 Nov: dive text 58, deck 97); deck99 (changed on purpose, the deck96 audit's open items, 27 Nov: dive text 57, deck 96); rel98 (fix98 and map98 together, 27 Nov: dive text 56, deck 95, changed on purpose); map98 (a company of the map's own layers whose own first business sentence states another principal business listed as other work); fix98 (changed on purpose, members no longer listed: dive text 55, deck 94); deck96 (changed on purpose, every live theme deck checked 26 Nov: dive text 54, deck 93); e90 (changed on purpose, the live R90 alcobev deck: dive text 53 so the kept dives carry the demerger and revenue-basis fixes); deck89 (changed on purpose, owner 25 Nov: the theme deck remade as research): deck 92; e89 (the owner's Alcoholic beverages deck, 25 Nov): RULES 80, PLACE_CARRY[80] = 79, EARLIER_MAX 35, dive text 52 (changed on purpose, e89); e85 (LIVE21A, the R84 decks): deck 91, dive text 51 (updated on purpose); e84 (LIVE20A, the R82 decks): RULES 79, PLACE_CARRY[79] = 78, EARLIER_MAX 34, deck 90, dive text 50, blog GEN 12 (updated on purpose); e83 (LIVE19A, the R81 decks): RULES 78, PLACE_CARRY[78] = 77, EARLIER_MAX 33, deck 89, dive text 49, blog GEN 11 (updated on purpose); e82 (LIVE18A, the R80 decks): RULES 77, PLACE_CARRY[77] = 76, EARLIER_MAX 32, deck 88, dive text 48 (updated on purpose); e81 (LIVE17A, the R79 decks): RULES 76, PLACE_CARRY[76] = 75, EARLIER_MAX 31, deck 87, dive text 47 (updated on purpose); e80 (LIVE16A, the R78 decks): RULES 75, PLACE_CARRY[75] = 74, EARLIER_MAX 30, deck 86, dive text 46 (updated on purpose); e79 (the live R77 decks): RULES 74, PLACE_CARRY[74] = 73, EARLIER_MAX 29, deck 85, dive text 45 (updated on purpose); e78 (the live R76 decks): RULES 73, PLACE_CARRY[73] = 72, EARLIER_MAX 28, deck 84, dive text 44 (updated on purpose); e77 (the live R76 decks): RULES 72, PLACE_CARRY[72] = 71, EARLIER_MAX 27, deck 83, dive text 43 (updated on purpose); fix20 (the live R75 decks): RULES 71 kept, deck 82, dive text 42 (updated on purpose); r69e (R69): RULES 71, PLACE_CARRY[71] = 70, EARLIER_MAX 26, deck 81, dive text 41 (updated on purpose); r68e (R68): RULES 70, PLACE_CARRY[70] = 69, EARLIER_MAX 25, deck 80, dive text 40 (updated on purpose); r67e (R67): RULES 69, PLACE_CARRY[69] = 68, EARLIER_MAX 24, deck 79, dive text 39 (updated on purpose); r66e (R66): RULES 68, PLACE_CARRY[68] = 67, EARLIER_MAX 23, deck 78, dive text 38 (updated on purpose); r65e (R65): RULES 67, PLACE_CARRY[67] = 66, EARLIER_MAX 22, deck 77, dive text 37 (updated on purpose); r64e (R64): RULES 66, PLACE_CARRY[66] = 65, EARLIER_MAX 21, deck 76, dive text 36 (updated on purpose); r63e (R63): RULES 65, PLACE_CARRY[65] = 64, EARLIER_MAX 20, deck 75, dive text 35 (updated on purpose); r62 (R62): RULES 64, PLACE_CARRY[64] = 63, EARLIER_MAX 19, deck 74, dive text 34 (updated on purpose); r60 (R60): RULES 63, PLACE_CARRY[63] = 62, EARLIER_MAX 18, deck 73, dive text 33 (updated on purpose); r59 (R59): RULES 62, PLACE_CARRY[62] = 61, EARLIER_MAX 17, deck 72, dive text 32 (updated on purpose); r582 (R58.2): RULES 61, PLACE_CARRY[61] = 60, EARLIER_MAX 16, deck 71, dive text 31 (updated on purpose); r581 (R58.1): RULES 60, PLACE_CARRY[60] = 59, EARLIER_MAX 15, deck 70, dive text 30 (updated on purpose); r58 (R58): RULES 59, PLACE_CARRY[59] = 58, EARLIER_MAX 14, deck 69, dive text 29 (updated on purpose); r572 (R57.2): RULES 58, PLACE_CARRY[58] = 57, EARLIER_MAX 13, deck 68, dive text 28 (updated on purpose)
    assert "moved_out" in B.place_rest.__code__.co_varnames
