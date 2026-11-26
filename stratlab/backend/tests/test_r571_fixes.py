"""Lane r571 (Release 57.1): the live R57 decks' regressions, each proven on the live placement inputs read under RULES 56 on 15 Nov
2026 (tests/fixtures/themes_live/r571/: semis, software, meddev and defence as served, with a company the map's check dropped given its
stored words from the R56 inputs; retail with the R56 published memory the live R57 re-check read). The model's own R57 answers (the
misfit and the layer audit, kept with the placement) are replayed as the model's answer under the new rules: no other model call."""
import copy
import json
import pathlib

from app.intel import theme_base as B
from app.intel import theme_changes as C
from app.intel import theme_check as TC
from app.intel import theme_identity as TI
from tests import test_exact_replay as X

LIVE = pathlib.Path(__file__).parent / "fixtures" / "themes_live" / "r571"
ORIGIN = {"semis": {"MU": "Design software and IP licensing", "INTC": "Foundry and memory manufacturing"}}
STALE = ("out_why", "on_industry", "refit", "own_goods", "by_words", "unfit", "sold_by")


def inputs(key: str) -> dict:
    d = json.loads((LIVE / f"{key}.json").read_text())
    d = d.get("data", d)
    for v in d["value_chain"]:
        v["companies"] = [{k: x for k, x in c.items() if k not in STALE} for c in v["companies"]]
    return d


def stored_answers(d: dict):
    """The model as it answered on live: its kept misfit and audit answers, by layer name; nothing else."""
    def ask(system, text):
        if system == TC.AUDIT_SYSTEM:
            p = json.loads(text.split("AUDIT:\n", 1)[1])
            ids = {x["name"]: k for k, x in p["layers"].items()}
            moves = (d["kept"].get("audit") or {}).get("moves") or {}
            return {"moves": [{"symbol": s, "to": ids.get(x["to"], "other") if x["to"] else "other", "quote_new": x["quote_new"],
                               "quote_old": x["quote_old"]} for s, x in moves.items() if not x["to"] or x["to"] in ids]}
        if system == TC.FIT_SYSTEM:
            p = json.loads(text.split("MAP:\n", 1)[1])
            ids = {x["name"]: k for k, x in p["layers"].items()}
            moves = (d["kept"].get("fit") or {}).get("moves") or {}
            return {"moves": [{"symbol": s, "layer": ids.get(t, "other")} for s, t in moves.items()]}
        return {}
    return ask


def place(key: str, monkeypatch, published=None, answers: bool = True) -> dict:
    d = inputs(key)
    sig = ((d.get("kept") or {}).get("model_names") or {}).get("sig")
    if sig:
        monkeypatch.setattr(B, "model_names_signature", lambda layers: sig)
    pub = d.get("published") if published is None else published
    m = X.pre_map(copy.deepcopy(d), ORIGIN.get(key, {}), {})
    m["placements"] = dict(d["placements"])
    m = B.keep_published(m, pub, lambda s: d["evidence"].get(s), rename=B.answer_renames(d["kept"]))
    out, _ = B.place_rest(m, d["theme"], lambda s: d["evidence"].get(s), ask=stored_answers(d) if answers else None, kept=d["kept"],
                          facts_of=lambda s: d["facts"].get(s) or {}, figures_of=lambda s: (d.get("figures") or {}).get(s) or {},
                          carried=d["kept_version"] != B.RULES, previous=d["previous"], off_before=d.get("off_before") or {},
                          moved_before=d.get("moved_before") or {}, **({"moved_out": d["moved_out"]} if d.get("moved_out") else {}),
                          published=pub)
    return out


def where(out: dict) -> dict:
    return {c["ticker"]: ("Other" if v.get("official") and v.get("basis") == "rest" else X._HALF.sub("", v["layer"]), c)
            for v in out["value_chain"] for c in v["companies"]}


def test_1_the_peer_pull_adds_no_member_by_default(monkeypatch):
    """Fails before: with_peers pulled Adobe, Intuit and Salesforce into Semiconductors (live R57). Off by default; behind PEERS_ON."""
    out = {"value_chain": [{"layer": "Design software", "companies": [{"ticker": "SNPS", "verified": True, "base": False}]}],
           "placements": {"industries": ["Semiconductors"]}}
    rows = [{"symbol": "SNPS", "industry": "Software", "market_cap": 50.0}, {"symbol": "ADBE", "industry": "Software", "market_cap": 90.0}]
    assert TI.with_peers(copy.deepcopy(out), rows, lambda s: "Adobe makes design software.", "Semiconductors") == out
    assert TI.PEERS_ON is False


def test_2_a_check_s_verified_never_vouches_for_a_layer_it_was_not_asked_about(monkeypatch):
    """Fails before: Intel in "Chip equipment and subsystem suppliers", "its own words were checked to show it is of" it: the check had
    confirmed it for the map's foundry group, then the published memory (an R53 move) held it among the equipment makers."""
    got = where(place("semis", monkeypatch))
    lay, c = got["INTC"]
    assert lay != "Chip equipment and subsystem suppliers" and "were checked to show" not in str(c.get("sold_by") or "")


def test_3_a_renamed_published_layer_is_kept_not_undone(monkeypatch):
    """Fails before: "Single-category specialty retailers" (9 companies in R56), renamed by an answer to "Niche specialty and category
    retailers", was not made and all went to "Other"."""
    out = place("retail", monkeypatch)
    got = where(out)
    members = [s for s, (x, _) in got.items() if x == "Single-category specialty retailers"]
    assert len(members) >= 7 and {"WOOF", "BQ", "TITN"} <= set(members)


def test_4_the_live_audit_answer_moves_twilio_once_its_old_quote_is_read_like_a_stable_placement(monkeypatch):
    """Fails before: the model's own R57 answer moved Twilio to "Data and developer infrastructure software", refused because its quote
    "an American cloud communications company" said "cloud", one of its layer's three core words. Shopify's and Toast's quotes name nothing
    of their new layer: still refused (the model's answer, not the check's)."""
    got = where(place("software", monkeypatch))
    assert got["TWLO"][0] == "Data and developer infrastructure software"
    # r572 round 2 (updated on purpose): the audit still refuses Shopify's and Toast's moves, and the compute layer's fit then re-places them:
    # their own words ("a cloud e-commerce management platform", "cloud-based restaurant management software") say no computing, capacity,
    # hosting or data centres, and no other layer's name, so they go to the theme's "Other" group (theme_base.compute_fit)
    assert got["SHOP"][0] == "Other" and got["TOST"][0] == "Other"


def test_5_a_published_member_outside_the_map_s_groups_stays_in_the_theme():
    """Fails before: Bharat Forge, published in "Parts, component and ingredient makers" (a layer the split made, no map group), was judged
    against "Combat aircraft and helicopters", the first map group naming it, asked, and dropped from Defence."""
    words = inputs("defence")["evidence"]["BHARATFORG"]
    m = {"value_chain": [{"layer": "Combat aircraft and helicopters", "description": "Fighter jets and helicopters.",
                          "companies": [{"ticker": "BHARATFORG", "name": "Bharat Forge Limited"}]}]}
    asked = []

    def no(system, text):
        asked.append(1)
        return {"checks": [{"id": "L0|BHARATFORG", "does": False, "quote": ""}]}
    out = TC.check_placements(copy.deepcopy(m), lambda syms: ({"BHARATFORG": {"about": words, "industry": ""}}, set()), no, "Defence",
                              held={"BHARATFORG": ""})
    assert asked == [] and [c["ticker"] for c in out["value_chain"][0]["companies"]] == ["BHARATFORG"]
    dropped = {"value_chain": [{"layer": "Combat aircraft and helicopters", "description": "", "companies": []}],
               "placements": {"dropped": [{"ticker": "BHARATFORG", "name": "Bharat Forge Limited", "groups": ["Combat aircraft and helicopters"],
                                           "said": "no"}]}}
    back = B.keep_published(dropped, {"BHARATFORG": "Parts, component and ingredient makers"}, lambda s: words)
    assert [c["ticker"] for c in back["value_chain"][0]["companies"]] == ["BHARATFORG"]


def test_6_3m_leaves_medical_devices_and_no_thin_groups_layer_is_made(monkeypatch):
    """Fails before: 3M stayed in "Other" ("electrical" read as "electromedical"), and a 2-company "Diversified groups" layer was made."""
    out = place("meddev", monkeypatch)
    got = where(out)
    assert "MMM" not in got and any(x["ticker"] == "MMM" for x in out["placements"].get("off_industry") or [])
    assert not [v for v in out["value_chain"] if v["layer"] == "Diversified groups" and v["companies"]]
    assert not any(v["layer"].startswith("Surgical robotics") for v in out["value_chain"] if v["companies"])     # no return to a contradicted name


def test_7_a_layer_split_off_another_is_said_once_not_as_moves():
    mk = lambda cos: {"layers": [{"layer": n, "companies": [{"symbol": s, "name": s} for s in ss]} for n, ss in cos.items()]}      # noqa: E731
    was = C.snapshot(mk({"Ad-funded platforms": list("ABCDEFG")}), list("ABCDEFG"), 1, 56)
    now = C.snapshot(mk({"Ad-funded platforms": list("ABC"), "Consumer internet": list("DEFG")}), list("ABCDEFG"), 1, 57)
    d = C.diff(was, now)
    assert d["moved"] == [] and d["layers"] == [{"kind": "split", "from": ["Ad-funded platforms"], "to": ["Ad-funded platforms", "Consumer internet"],
                                                 "n": 4}]


def test_8_a_layer_s_notes_page_is_not_another_layer():
    import sys
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
    import deck_check as DC
    pages = ["Layer 1 · Cloud and AI compute providers\nrows", "Layer 1 · Cloud and AI compute providers (notes)\nmore", "Layer 2 · X (continued)"]
    assert DC._layer_names(pages) == {"Cloud and AI compute providers", "X"}


def test_9_rules_57_carries_56():
    from app.intel import theme_routes as TR
    assert B.RULES == 80 and TR.PLACE_CARRY[78] == 77 and TR.PLACE_CARRY[77] == 76 and TR.PLACE_CARRY[76] == 75 and TR.PLACE_CARRY[75] == 74 and TR.PLACE_CARRY[74] == 73 and TR.PLACE_CARRY[73] == 72 and TR.PLACE_CARRY[72] == 71 and TR.PLACE_CARRY[71] == 70 and TR.PLACE_CARRY[70] == 69 and TR.PLACE_CARRY[69] == 68 and TR.PLACE_CARRY[68] == 67 and TR.PLACE_CARRY[67] == 66 and TR.PLACE_CARRY[66] == 65 and TR.PLACE_CARRY[65] == 64 and TR.PLACE_CARRY[64] == 63 and TR.PLACE_CARRY[63] == 62 and TR.PLACE_CARRY[62] == 61 and TR.PLACE_CARRY[61] == 60 and TR.PLACE_CARRY[60] == 59 and TR.PLACE_CARRY[59] == 58 and TR.PLACE_CARRY[58] == 57 and TR.PLACE_CARRY[57] == 56 and TR.EARLIER_MAX == 35  # e89 (the owner's Alcoholic beverages deck, 25 Nov): RULES 80, PLACE_CARRY[80] = 79, EARLIER_MAX 35, dive text 52 (changed on purpose, e89); e84 (LIVE20A, the R82 decks): RULES 79, PLACE_CARRY[79] = 78, EARLIER_MAX 34, deck 90, dive text 50, blog GEN 12 (updated on purpose); e83 (LIVE19A, the R81 decks): RULES 78, PLACE_CARRY[78] = 77, EARLIER_MAX 33, deck 89, dive text 49, blog GEN 11 (updated on purpose); e82 (LIVE18A, the R80 decks): RULES 77, PLACE_CARRY[77] = 76, EARLIER_MAX 32, deck 88, dive text 48 (updated on purpose); e81 (LIVE17A, the R79 decks): RULES 76, PLACE_CARRY[76] = 75, EARLIER_MAX 31, deck 87, dive text 47 (updated on purpose); e80 (LIVE16A, the R78 decks): RULES 75, PLACE_CARRY[75] = 74, EARLIER_MAX 30, deck 86, dive text 46 (updated on purpose); e79 (the live R77 decks): RULES 74, PLACE_CARRY[74] = 73, EARLIER_MAX 29, deck 85, dive text 45 (updated on purpose); e78 (the live R76 decks): RULES 73, PLACE_CARRY[73] = 72, EARLIER_MAX 28, deck 84, dive text 44 (updated on purpose); e77 (the live R76 decks): RULES 72, PLACE_CARRY[72] = 71, EARLIER_MAX 27, deck 83, dive text 43 (updated on purpose); r69e (R69): RULES 71, PLACE_CARRY[71] = 70, EARLIER_MAX 26, deck 81, dive text 41 (updated on purpose); r68e (R68): RULES 70, PLACE_CARRY[70] = 69, EARLIER_MAX 25, deck 80, dive text 40 (updated on purpose); r67e (R67): RULES 69, PLACE_CARRY[69] = 68, EARLIER_MAX 24, deck 79, dive text 39 (updated on purpose); r66e (R66): RULES 68, PLACE_CARRY[68] = 67, EARLIER_MAX 23, deck 78, dive text 38 (updated on purpose); r65e (R65): RULES 67, PLACE_CARRY[67] = 66, EARLIER_MAX 22, deck 77, dive text 37 (updated on purpose); r64e (R64): RULES 66, PLACE_CARRY[66] = 65, EARLIER_MAX 21, deck 76, dive text 36 (updated on purpose); r63e (R63): RULES 65, PLACE_CARRY[65] = 64, EARLIER_MAX 20, deck 75, dive text 35 (updated on purpose); r62 (R62): RULES 64, PLACE_CARRY[64] = 63, EARLIER_MAX 19, deck 74, dive text 34 (updated on purpose); r60 (R60): RULES 63, PLACE_CARRY[63] = 62, EARLIER_MAX 18, deck 73, dive text 33 (updated on purpose); r59 (R59): RULES 62, PLACE_CARRY[62] = 61, EARLIER_MAX 17, deck 72, dive text 32 (updated on purpose); r582 (R58.2): RULES 61, PLACE_CARRY[61] = 60, EARLIER_MAX 16, deck 71, dive text 31 (updated on purpose); r581 (R58.1): RULES 60, PLACE_CARRY[60] = 59, EARLIER_MAX 15, deck 70, dive text 30 (updated on purpose); r58 (R58): RULES 59, PLACE_CARRY[59] = 58, EARLIER_MAX 14, deck 69, dive text 29 (updated on purpose); r572 (R57.2): RULES 58, PLACE_CARRY[58] = 57, EARLIER_MAX 13, deck 68, dive text 28 (updated on purpose)


def test_8b_deck_diff_counts_a_layer_from_its_page_and_never_its_notes_page():
    """Fails before: the live R57 Consumer retail deck read as 5 layers (rows the table's layout put off its column), and a "(notes)"
    page would read as a layer of its own."""
    import sys
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
    import deck_diff as DD
    pages = ["RETAIL · THE VALUE CHAIN\nLayer 3 · Catalog and mail-order houses\n6 companies, revenue $9 bn together\n",
             "Layer 3 · Catalog and mail-order houses (notes)\n6 companies are said here too\n"]
    assert DD.layer_counts(pages) == {"Catalog and mail-order houses": 6}


def test_10_a_large_commercial_company_joins_the_theme_s_scale_layer_by_its_revenue(monkeypatch):
    """Fails before (R56 audit BIO-2, still on the live R57 Biotech deck; the model's audit named none of them): Novo Nordisk, AbbVie,
    Amgen and Bristol Myers (revenue $37-61 bn, at or above the $17.3 bn median of "Large pharma and biotech portfolios") join it from
    "Specialty and clinical-stage biotechs"; Sarepta ($2.2 bn) and the clinical-stage developers stay."""
    d = json.loads((pathlib.Path(__file__).parent / "fixtures" / "themes_live" / "r571" / "biotech.json").read_text())
    d = d.get("data", d)
    out = copy.deepcopy(d["value_chain"])
    vc, rows = B.scale_moves(out, lambda s: d["evidence"].get(s), d["theme"], lambda s: d["figures"].get(s) or {})
    got = {c["ticker"]: (X._HALF.sub("", v["layer"]), c) for v in vc for c in v["companies"]}
    for s_ in ("NVO", "ABBV", "AMGN", "BMY"):
        assert got[s_][0] == "Large pharma and biotech portfolios", s_
        assert "at or above the median" in got[s_][1]["refit"]["why"]
    assert got["SRPT"][0] == "Specialty and clinical-stage biotechs"
    assert all(r["revenue"] >= r["median"] for r in rows)
    full = where(place("biotech", monkeypatch))          # the whole placement, with the published memory: the same four, reasons printed
    for s_ in ("NVO", "ABBV", "AMGN", "BMY"):
        # (updated on purpose, r60: a published member is no newcomer to its layer (sold_what), so a commercial company may reach the layer by
        # the stage rule on its own words before the scale rule on its revenue: either reason is its evidence)
        assert full[s_][0] == "Large pharma and biotech portfolios" and (full[s_][1]["refit"]["why"].startswith("revenue of $")
                                                                         or "commercial-stage company" in full[s_][1]["refit"]["why"]), s_
    assert full["SRPT"][0] == "Specialty and clinical-stage biotechs"
    assert not any(got[c["ticker"]][0] != "Clinical-stage gene editing and drug developers"
                   for v in d["value_chain"] if v["layer"] == "Clinical-stage gene editing and drug developers" for c in v["companies"])
