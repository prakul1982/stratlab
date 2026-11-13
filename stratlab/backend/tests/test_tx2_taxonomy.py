"""Lane tx2 (Release 46, the outside review of the live Release 45 decks): the taxonomy regression guard.

P0 Automotive: Bosch and Asahi India Glass were in "Component and systems suppliers" on the live Release 43 and in "Battery, tractor and
mixed component makers" on the live Release 45. The live Release 45 placement inputs (tests/fixtures/themes_live/inputs_r45/auto.json,
GET /research/theme-dive/placement-inputs on 13 Nov 2026) replay exactly under RULES 44 (Bosch's map layer recovered as the component
suppliers' one, where the map named it): the map was being checked again under the new rules, so a tractor maker the Release 43 check had
moved out of "Commercial and three-wheeler vehicle makers" sat there again, unchecked; "Batteries and tractor makers" was then two of three
auto component makers, "mostly of their industry", and by_model.home_of sent every component maker read as a maker of its own products into
it (Bosch, Asahi India Glass, El Forge, Lakshmi Precision Screws), whatever their own words. Generic fixes (RULES 45):
- by_model: a company leaves a map layer mostly of its industry for another layer of its industry only on evidence of that layer (its own
  words say the layer's name, or the layer holds a larger share of its industry; `evidence_for`);
- place_rest `previous` (theme_routes.previous_layers: the previous live read's layers, theme_changes' snapshot of the same map): a company
  the split would move out of its previous live layer moves only on evidence of the new one, and an unchecked map pick whose previous live
  layer is another layer of the map keeps that layer unless it has evidence of the one it is in (held_to_previous).
The regression test: every company whose layer changes against the previous live placement carries evidence (its own words or its official
industry) for its new layer, on the Release 45 inputs against the live Release 43 placement and on every move the exact replay approves."""
import json
import pathlib
import re

from app.intel import theme_base as B
from tests import test_exact_replay as X

R45 = pathlib.Path(__file__).parent / "fixtures" / "themes_live" / "inputs_r45"
_HALF = re.compile(r" \((?:larger|smaller)\)$")
COMPONENT = "Component and systems suppliers"
BOSCH_ORIGIN = {"BOSCHLTD": COMPONENT}          # the map's own layer of Bosch (the endpoint shows only where the split moved it)


def r45(key: str) -> dict:
    d = json.loads((R45 / f"{key}.json").read_text())
    return d.get("data", d)


def replay45(key: str, previous: dict | None = None) -> dict:
    d = r45(key)
    m = X.pre_map(d, BOSCH_ORIGIN, X.RECOVERED["description"].get(key))
    out, _ = B.place_rest(m, d["theme"], lambda s: d["evidence"].get(s), ask=None, kept=d["kept"], carried=d["kept_version"] != B.RULES,
                          **({"previous": previous} if previous is not None else {}))
    return out


def live_layers(d: dict) -> dict:
    return {c["ticker"]: ("Other" if v.get("official") else v["layer"]) for v in d["value_chain"] for c in v["companies"]}


def layer_map(vc) -> dict:
    """{symbol: its layer dict} (halves of a layer split by market value as one layer, "Other" as "Other")."""
    out = {}
    for v in vc:
        for c in v["companies"]:
            out[c["ticker"]] = v
    return out


def name_of(v: dict, back: dict) -> str:
    if v.get("official"):
        return "Other"
    n = _HALF.sub("", v.get("was") or v["layer"])
    return back.get(n, n)


def backs(*kepts) -> dict:
    """{a shown name a kept answer gave a map layer: the map's own name} (theme_base.map_names_of, read back)."""
    out = {}
    for k in kepts:
        for ren in ((k or {}).get("rename"), ((k or {}).get("model_names") or {}).get("rename")):
            for name, x in (ren or {}).items():
                if isinstance(x, dict) and x.get("name"):
                    out.setdefault(x["name"], name)
    return out


def share(v: dict, ind: str) -> float:
    cos = v.get("companies") or []
    return sum(1 for c in cos if B.key(c.get("industry")) == ind) / max(1, len(cos))


def evidence_of_move(c: dict, words: str, old_v: dict, new_v: dict, theme: str, back: dict) -> str:
    """Why a company may be in `new_v` rather than `old_v`, its layer in the previous live placement: "" when nothing shows it. Its own
    words say what the new layer's name says; or its official industry: the layer is made of that industry, named by it, or holds a larger
    share of it than the old one. Leaving a layer for "Other" (no layer fits) claims nothing."""
    new = name_of(new_v, back)
    if new == "Other":
        return "fits none"
    ind = B.key(c.get("industry")) if c.get("industry") else ""
    tw = B.kind_stems(theme)
    if B.name_says(new, B.own_text(words), tw)[1]:
        return "its own words say the layer's name"
    if ind and new_v.get("industry_group") and B.key(new_v["companies"][0].get("industry")) == ind:
        return "a layer made of its official industry"
    if ind and B.industry_named(new, c.get("industry"), tw):
        return "a layer named by its official industry"
    if ind and share(new_v, ind) > share(old_v, ind):
        return "a layer holding more of its official industry"
    return ""


def unexplained(prev_vc, now_vc, evidence: dict, theme: str, back: dict) -> dict:
    was, now = layer_map(prev_vc), layer_map(now_vc)
    out = {}
    for s_, v in now.items():
        if s_ not in was or name_of(was[s_], back) == name_of(v, back):
            continue
        c = next(x for x in v["companies"] if x["ticker"] == s_)
        if not evidence_of_move(c, evidence.get(s_) or c.get("what") or "", was[s_], v, theme, back):
            out[s_] = (name_of(was[s_], back), name_of(v, back))
    return out


def test_bosch_and_asahi_keep_the_component_suppliers_layer_on_the_live_release_45_inputs():
    """Fails on RULES 44: the four component makers went to "Batteries and tractor makers" (renamed "Battery, tractor and mixed component
    makers" on live). Now they keep the map's component suppliers' layer: their words say neither batteries nor tractors, and that layer
    holds a smaller share of their industry (two of three) than the one they are in (all of it)."""
    got = X.layers_of(replay45("auto")["value_chain"])
    for s_ in ("BOSCHLTD", "ASAHIINDIA", "ELFORGE", "LAKPRE"):
        assert _HALF.sub("", got[s_]) == COMPONENT, s_
    # the makers of their own batteries and tractors keep their layer
    assert {got[s_] for s_ in ("EXIDEIND", "ARE&M", "ESCORTS")} == {"Batteries and tractor makers"}


def test_the_release_45_inputs_replay_the_live_layers_but_the_component_makers():
    """The exact replay: under the rules now every company of the live Release 45 Automotive inputs has its live layer (the AI's rename of
    the batteries layer, keyed by its members, aside) but the four component makers, back in the component suppliers' layer."""
    d = r45("auto")
    want = {s_: X.joined(v["layer"], v) for v in d["value_chain"] for c in v["companies"] for s_ in [c["ticker"]]}
    got = {c["ticker"]: X.joined(v["layer"], v) for v in replay45("auto")["value_chain"] for c in v["companies"]}
    back = backs(d["kept"])
    diffs = {s_: (want[s_], got.get(s_)) for s_ in want if back.get(want[s_], want[s_]) != back.get(got.get(s_), got.get(s_))}
    assert diffs == {s_: ("Battery, tractor and mixed component makers", COMPONENT) for s_ in ("BOSCHLTD", "ASAHIINDIA", "ELFORGE", "LAKPRE")}


def test_the_first_release_46_placement_reading_the_live_release_45_layers_puts_them_back():
    """What the first placement under RULES 45 reads on live: the Release 45 inputs with the live Release 45 layers as the previous ones.
    The wrong previous layer pins nothing: the component makers go back to the component suppliers' layer (evidence of it: it holds all of
    their industry, the batteries layer two of three), and no company is held."""
    d = r45("auto")
    out = replay45("auto", live_layers(d))
    got = X.layers_of(out["value_chain"])
    for s_ in ("BOSCHLTD", "ASAHIINDIA", "ELFORGE", "LAKPRE"):
        assert _HALF.sub("", got[s_]) == COMPONENT, s_
    assert not [c for v in out["value_chain"] for c in v["companies"] if c.get("held")]


def test_an_unchecked_pick_keeps_its_previous_live_layer_without_evidence_of_the_new_one():
    """V.S.T. Tillers Tractors: the map's own pick for "Commercial and three-wheeler vehicle makers", moved out by the check on the live
    Release 43 and placed with the batteries and tractor makers; on the Release 45 inputs the pick is not checked yet (verified False). Its
    words (power tillers, tractors) don't say the commercial vehicle layer's name and that layer holds less of its industry (Tractors), so
    with the previous live layers it keeps "Batteries and tractor makers"; without them the unchecked pick stands."""
    prev = live_layers(X.live("auto"))
    assert X.layers_of(replay45("auto", prev)["value_chain"])["VSTTILLERS"] == "Batteries and tractor makers"
    assert X.layers_of(replay45("auto")["value_chain"])["VSTTILLERS"] == "Commercial and three-wheeler vehicle makers"
    held = [c for v in replay45("auto", prev)["value_chain"] for c in v["companies"] if c.get("held")]
    assert [c["ticker"] for c in held] == ["VSTTILLERS"]


def test_every_move_against_the_previous_live_placement_carries_evidence_on_the_release_45_inputs():
    """The guard as a check: on the live Release 45 Automotive inputs placed under the rules now, with the live Release 43 layers as the
    previous placement, no company is in a new layer without its own words or its official industry for it (the tyre layer's rename is
    the same layer). Fails on RULES 44 (Bosch, Asahi India Glass, El Forge, Lakshmi Precision Screws, and V.S.T. Tillers)."""
    prev_d, d = X.live("auto"), r45("auto")
    out = replay45("auto", live_layers(prev_d))
    assert unexplained(prev_d["value_chain"], out["value_chain"], {**prev_d["evidence"], **d["evidence"]}, d["theme"],
                       backs(prev_d["kept"], d["kept"])) == {}


def test_the_guard_finds_the_release_45_regression():
    """The check itself catches the live Release 45 layers: against the live Release 43 placement, the four component makers and the
    tractor maker moved with no evidence of their new layers."""
    prev_d, d = X.live("auto"), r45("auto")
    got = unexplained(prev_d["value_chain"], d["value_chain"], {**prev_d["evidence"], **d["evidence"]}, d["theme"], backs(prev_d["kept"], d["kept"]))
    assert set(got) == {"BOSCHLTD", "ASAHIINDIA", "ELFORGE", "LAKPRE", "VSTTILLERS"}


def test_every_move_the_exact_replay_approves_carries_evidence():
    """On the 14 exact replay fixtures (the live Release 43 inputs), every company whose layer the rules now change against its live layer
    (APPROVED in test_exact_replay, each with its reason) has its own words or its official industry for its new layer: a rule change that
    moves a company with neither fails here as well as there."""
    bad = {}
    for key in X.THEMES:
        d = X.live(key)
        out, _ = X.replay(key, carried=d["kept_version"] != B.RULES)
        back = {**backs(d["kept"]), **X.name_only(d)}
        got = unexplained(d["value_chain"], out["value_chain"], d["evidence"], d["theme"], back)
        bad.update({f"{key}:{s_}": x for s_, x in got.items()})
    assert bad == {}


def test_a_previous_layer_is_read_only_for_the_same_map(monkeypatch):
    from app.intel import theme_changes, theme_routes
    snap = {"layers": ["A layer", "B layer"], "cos": {"X1": ["X One", 1, None, None, None, ""]}, "stamp": 1700000000}
    monkeypatch.setattr(theme_changes, "stored", lambda r, n: {"snap": snap})
    assert theme_routes.previous_layers("IN", "Theme", {"generated_at": 1700000000.4}) == {"X1": "B layer"}
    assert theme_routes.previous_layers("IN", "Theme", {"generated_at": 1700000999}) == {}          # another map: nothing carried
    monkeypatch.setattr(theme_changes, "stored", lambda r, n: {})
    assert theme_routes.previous_layers("IN", "Theme", {"generated_at": 1700000000}) == {}


def test_map_names_read_back_a_renamed_layer_and_a_half():
    kept = {"rename": {"Tyre manufacturers": {"name": "Tyre and rubber product makers"}},
            "model_names": {"rename": {"Batteries and tractor makers": {"name": "Battery, tractor and mixed component makers"}}}}
    got = B.map_names_of({"A": "Tyre and rubber product makers", "B": "Battery, tractor and mixed component makers",
                          "C": "Component and systems suppliers (smaller)"}, kept)
    assert got == {"A": "Tyre manufacturers", "B": "Batteries and tractor makers", "C": "Component and systems suppliers"}


# ---------- 3. explicit screening populations on every deck's coverage page ----------
def _with_off(v: dict, n: int) -> dict:
    import copy
    v = copy.deepcopy(v)
    v["placements"] = {**(v.get("placements") or {}),
                       "off_industry": [{"ticker": f"OFF{k}", "name": f"Propane Distributor {k} LP", "industry": "Retail-Miscellaneous Retail"}
                                        for k in range(n)]}
    return v


def _coverage_rows(slides) -> list:
    from app import deck
    return [r for s in slides if s.title.startswith(("Data confidence", "Coverage")) for b in s.blocks
            if b["kind"] == "table" and b.get("head") == deck.COVERAGE_HEAD for r in b["rows"]]


def test_every_deck_states_its_screening_populations_and_they_reconcile():
    """The outside review of the live Release 45 decks (Consumer retail p.5: 15 companies of another business, propane distributors among
    them; Semiconductors p.5: 7 solar companies): every deck's coverage says, in one row, how many companies were considered, how many were
    screened out as another business (candidates, never members), the members, the confirmed, those with figures, those in informative
    layers and those eligible for each metric; considered = screened out + members, and the screened-out row says plainly what they are."""
    from app import deck
    from tests import synthetic_themes_r27 as S
    for k, (name, v, _) in enumerate(S.decks()):
        v = _with_off(v, 3 * (k % 2))
        slides = deck.theme_plan(v)[0]
        rows = _coverage_rows(slides)
        scr = next(r for r in rows if r[0] == "Screening")
        cov = deck.coverage(v)
        c = deck.reconciled_counts(v, cov)
        assert c["considered"] == c["rejected"] + c["members"] and c["members"] == cov["total"] and c["rejected"] == 3 * (k % 2), name
        assert scr[1] == f"{c['considered']} considered", name
        if c["rejected"]:
            assert scr[2].startswith(f"{c['considered']} considered = 3 screened out as another business (candidates, never members) + "
                                     f"{c['members']} members"), name
            off = next(r for r in rows if r[0] == "Screened out: another business")
            assert off[1] == "3" and off[2].startswith("Candidates screened out, not members of the theme"), name
            line = next(x for s in slides for b in s.blocks if b["kind"] == "text" for x in b.get("paras") or [] if str(x).startswith("Counts:"))
            assert f"Considered {c['considered']} (3 screened out as another business, {c['members']} members)" in line, name
        else:
            assert scr[2].startswith(f"{c['considered']} considered, none screened out as another business: {c['members']} members"), name
        for part in ("with figures", "in informative layers", "eligible for each metric"):
            assert part in scr[2], (name, part)
        gate = deck.publication_gate(slides, v)
        assert not [d for d in gate["dropped"] if d.get("rule") == "reconcile"], name


def test_a_coverage_table_taller_than_a_page_goes_on_over_the_next():
    """The live Release 45 Consumer retail deck's coverage table ran past its page into the footer: a table taller than a page now goes on
    over as many pages as it needs ("Coverage, continued"), no table taller than the page."""
    from app import deck
    from tests import synthetic_themes_r27 as S
    name, v, _ = next(S.decks())
    v = _with_off(v, 60)
    slides = deck.theme_plan(v)[0]
    pages = [s for s in slides if s.title.startswith("Coverage")]
    assert [s.title for s in pages][:2] == ["Coverage", "Coverage, continued"]
    for s in pages:
        for b in s.blocks:
            if b["kind"] == "table":
                assert deck.table_height(deck.COVERAGE_HEAD, b["rows"], b["widths"], deck.CW) <= deck.BOT - deck.TOP + 1e-6
    assert sum(1 for r in _coverage_rows(slides) if r[0] == "Screening") == 1
