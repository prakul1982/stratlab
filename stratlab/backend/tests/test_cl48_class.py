"""Lane cl48 (Release 48, the outside review of the live Release 46 decks): primary-business validation, the Consumer retail universe and
the taxonomy coverage control, on the live Release 46 placement inputs (tests/fixtures/themes_live/inputs_r46, read on 13 Nov 2026) and the
live Release 45 Consumer retail inputs (inputs_r45/retail.json).

1. P0 (lululemon, a designer of branded athletic apparel, in "Off-price, dollar and discount store chains"): the map placed it with the brand
   owners; read as a retailer, the split moved it to the largest layer of the retailers by default, a layer whose name ("off-price",
   "dollar") its own words don't say and which holds none of its industry. RULES 47: that layer takes a company leaving a map layer by
   default only when its words say the layer's name; else its map layer when its words say that one (listed there, out of its figures as
   another way of earning), else a layer of its family sharing two of its words, else "Other" (by_model.home_of). Torrid sat there by a
   chance word ("branched off" read as the "off" of "off-price"): a compound of a short word is one word (whole_stems, says_most_of).
2. The industry pick: an industry of a replaced pick most of whose companies were in informative layers stays in the new pick
   (industries_for `held`, theme_routes.held_industries): the eight family clothing chains of Release 45 would have stayed.
3. P1: a theme under 60% in informative layers, or 8 points or more fewer than its previous live placement, is said so on its coverage
   page and raised to the admins (theme_changes.coverage_control, the autofix sweep)."""
import json
import pathlib
import re
from datetime import datetime, timedelta, timezone

from app import deck
from app.intel import theme_base as B
from app.intel import theme_changes as C
from app.intel import theme_routes as TR
from tests import test_exact_replay as X

LIVE = pathlib.Path(__file__).parent / "fixtures" / "themes_live"
OFF = "Off-price, dollar and discount store chains"
BRANDS = "Apparel and consumer brand owners"


def inputs(rel: str, key: str) -> dict:
    d = json.loads((LIVE / rel / f"{key}.json").read_text())
    return d.get("data", d)


def replay46(key: str, extra=None, previous=None) -> dict:
    d = inputs("inputs_r46", key)
    m = X.pre_map(d, X.RECOVERED["origin"].get(key), X.RECOVERED["description"].get(key))
    words, facts = dict(d["evidence"]), dict(d["facts"])
    if extra:
        m["value_chain"].append(extra["group"])
        words.update(extra["evidence"])
    out, _ = B.place_rest(m, d["theme"], lambda s: words.get(s), ask=None, kept=d["kept"], facts_of=lambda s: facts.get(s) or {},
                          carried=d["kept_version"] != B.RULES, previous=d["previous"] if previous is None else previous)
    return out


def shown(vc) -> dict:
    return {c["ticker"]: ("Other" if v.get("official") else X._HALF.sub("", v["layer"])) for v in vc for c in v["companies"]}


def informative(layers: dict) -> int:
    return sum(1 for x in layers.values() if x != "Other")


BRANDED_APPAREL = re.compile(r"\b(?:designer|brand)\b[^.]{0,200}\b(?:apparel|clothing|footwear)\b|\b(?:apparel|clothing|footwear)\b[^.]{0,200}"
                             r"\b(?:brand|designer)\b", re.I)
OFF_PRICE_WORDS = re.compile(r"\boff-price\b|\bdiscount\b|\bdollar\b|\bvalue retailer\b|\bbelow full-price\b", re.I)


def test_no_branded_apparel_company_is_in_an_off_price_layer_on_the_live_release_46_inputs():
    """Fails on RULES 46: lululemon ("a designer, distributor, and retailer of technical athletic apparel ... under the lululemon brand")
    was in "Off-price, dollar and discount store chains". Now it is with the brand owners the map placed it with, listed there out of the
    layer's figures as a retailer, and no company whose own words describe branded apparel (and none of off-price selling) is in the
    off-price layer. Torrid, there by "branched off" alone, is in "Other". No other retailer moves."""
    d = inputs("inputs_r46", "retail")
    out = replay46("retail")
    live, now = shown(d["value_chain"]), shown(out["value_chain"])
    assert live["LULU"] == OFF and now["LULU"] == BRANDS
    lulu = next(c for v in out["value_chain"] for c in v["companies"] if c["ticker"] == "LULU")
    assert lulu["model"] == "retail" and lulu["model_out"] == "other"
    off = next(v for v in out["value_chain"] if v["layer"] == OFF)
    for c in off["companies"]:
        words = B.own_text(d["evidence"].get(c["ticker"]))
        assert not (BRANDED_APPAREL.search(words) and not OFF_PRICE_WORDS.search(words)), c["ticker"]
    assert {s_: (live[s_], now[s_]) for s_ in live if now[s_] != live[s_]} == {"LULU": (OFF, BRANDS), "CURV": (OFF, "Other")}
    assert informative(live) == 58 and informative(now) == 57 and len(now) == 98


def test_a_company_the_largest_layer_s_name_does_not_describe_leaves_it_by_its_own_words():
    """by_model.home_of, generic: a maker's layer the map placed a company in, the company read as a retailer: its words say the map layer's
    name, so it stays there (out of its figures); words that say neither go to "Other"; words that say the largest's name go there."""
    def placed(words: str) -> str:
        vc = [{"layer": "Off-price and dollar stores", "description": "Chains reselling others' goods at low prices.",
               "companies": [{"ticker": f"R{i}", "industry": "Retail-Variety Stores", "verified": True} for i in range(5)]},
              {"layer": "Footwear brand owners", "description": "Designers of branded footwear.",
               "companies": [{"ticker": f"M{i}", "industry": "Rubber & Plastics Footwear", "verified": True} for i in range(3)]
               + [{"ticker": "X", "industry": "Apparel & Other Finishd Prods Of  Fabrics & Similar Matl", "verified": True}]},
              {"layer": "Other consumer retail companies", "official": True, "basis": "rest", "companies": []}]
        models = {**{f"R{i}": "retail" for i in range(5)}, **{f"M{i}": "manufacturing" for i in range(3)}, "X": "retail"}
        ev = {**{f"R{i}": "A dollar store chain." for i in range(5)}, **{f"M{i}": "Designs branded footwear." for i in range(3)}, "X": words}
        out = B.by_model(vc, models, "Consumer retail", evidence_of=ev.get)
        return next("Other" if v.get("official") else v["layer"] for v in out for c in v["companies"] if c["ticker"] == "X")
    assert placed("A designer and retailer of athletic footwear.") == "Footwear brand owners"
    assert placed("A designer and retailer of yoga wear.") == "Other"
    assert placed("An off-price retailer of yoga wear.") == "Off-price and dollar stores"


def test_a_compound_of_a_short_word_is_one_word():
    """Fails on RULES 46: "branched off ... The store offers" said most of "Off-price and dollar stores" ("off" and "store")."""
    tw = B.kind_stems("Consumer retail")
    torrid = "the company branched off to become Torrid. The store offers plus-size clothing."
    assert not B.says_most_of("Off-price and dollar stores", torrid, tw)
    assert B.says_most_of("Off-price and dollar stores", "an off-price retailer with 400 stores", tw)
    assert "off" not in B.whole_stems("Off-price, dollar and discount store chains") and "off" in B.whole_stems("branched off")
    assert B.whole_stems("an off-price chain") & B.whole_stems("Off-price, dollar and discount store chains")


def test_a_layer_s_line_says_who_earns_another_way():
    """Fails on RULES 46: a company listed in its layer as another way of earning was said to have evidence that "doesn't show how it
    earns" (Arm in "Design software and IP licensing", the retailers among the brand owners)."""
    out = replay46("retail")
    line = next(v for v in out["value_chain"] if v["layer"] == BRANDS)["model"]["line"]
    assert "2 of 8 are listed but left out of this layer's figures and rankings, 1 as it earns another way than the layer's companies, 1 as " \
           "its evidence shows how it earns only weakly." in line
    assert B.out_line([{"ticker": "A"}], "of 3", {"A"}) == ("1 of 3 is listed but left out of this layer's figures and rankings, as it earns "
                                                          "another way than the layer's companies.")
    assert B.out_line([{"ticker": "A"}, {"ticker": "B", "model_out": "other"}], "the other") == (
        "the other 2 are listed but left out of this layer's figures and rankings, 1 as it earns another way than the layer's companies, "
        "1 as its evidence doesn't show how it earns.")
    assert B.out_line([{"ticker": "A"}], "of 3") == ("1 of 3 is listed but left out of this layer's figures and rankings, as its evidence "
                                                    "doesn't show how it earns.")          # as before


# ---------- 2. the industry pick ----------
def _pick(stored: dict, picked: list, held) -> dict:
    rows = [{"symbol": "A", "industry": "Retail-Family Clothing Stores"}, {"symbol": "B", "industry": "Retail-Retail Stores, Nec"},
            {"symbol": "C", "industry": "Retail-Variety Stores"}]
    return B.industries_for("US", "Consumer retail", rows, lambda s, t: {"industries": picked}, stored.get, stored.__setitem__, held=held)


def test_an_industry_of_the_replaced_pick_the_evidence_placed_stays_in_the_new_pick():
    """Fails before: a pick made again dropped "Family Clothing Stores", whose companies were all in an informative layer. Now an industry
    `held` names (most of its companies were in informative layers) stays; one it doesn't name goes, as before."""
    key = "theme:industries:US:consumer-retail"
    old = (datetime.now(timezone.utc) - timedelta(days=B.INDUSTRIES_DAYS + 1)).isoformat(timespec="seconds")
    seed = json.dumps({"at": old, "industries": ["Retail-Family Clothing Stores", "Retail-Variety Stores"], "rules": B.PICK_RULES})
    stored = {key: seed}
    got = _pick(stored, ["Retail-Variety Stores", "Retail-Retail Stores, Nec"], lambda dropped: list(dropped))
    assert got["industries"] == ["Retail-Variety Stores", "Retail-Retail Stores, Nec", "Retail-Family Clothing Stores"]
    assert json.loads(stored[key])["held"] == ["Retail-Family Clothing Stores"]
    stored = {key: seed}
    got = _pick(stored, ["Retail-Variety Stores", "Retail-Retail Stores, Nec"], lambda dropped: [])
    assert got["industries"] == ["Retail-Variety Stores", "Retail-Retail Stores, Nec"] and "held" not in json.loads(stored[key])
    stored = {key: seed}
    assert _pick(stored, ["Retail-Variety Stores"], None)["industries"] == ["Retail-Variety Stores"]     # no evidence asked: as before


def test_held_industries_on_the_live_release_45_placement(monkeypatch):
    """The live Release 45 Consumer retail placement as the previous one: "Family Clothing Stores" (10 of 10 in informative layers) is
    held; "Miscellaneous Retail" (1 of 13) and "Department Stores" (2 of 4, not most) are not."""
    d = inputs("inputs_r45", "retail")
    other = B.other_label("Consumer retail")
    prev = {c["ticker"]: (other if v.get("official") else v["layer"]) for v in d["value_chain"] for c in v["companies"]}
    rows = [{"symbol": c["ticker"], "industry": c.get("industry")} for v in d["value_chain"] for c in v["companies"]]
    monkeypatch.setattr(TR, "previous_layers", lambda region, theme, m: prev)
    dropped = ["Retail-Family Clothing Stores", "Retail-Miscellaneous Retail", "Retail-Department Stores"]
    assert TR.held_industries("US", "Consumer retail", {"generated_at": 1}, dropped, rows) == ["Retail-Family Clothing Stores"]
    monkeypatch.setattr(TR, "previous_layers", lambda region, theme, m: {})
    assert TR.held_industries("US", "Consumer retail", {"generated_at": 1}, dropped, rows) == []


def test_the_held_family_clothing_chains_form_their_layer_on_the_live_release_46_inputs():
    """Coverage with the held industry: the eight family clothing chains of the live Release 45 universe beside the live Release 46 one
    (their Release 45 descriptions) make "Family clothing stores" again with the three specialty chains and Torrid that their words place
    there: 69 of 106 in informative layers (65%), against 57 of 98 without them."""
    old = inputs("inputs_r45", "retail")
    fam = "Retail-Family Clothing Stores"
    have = set(shown(inputs("inputs_r46", "retail")["value_chain"]))
    gone = [c for v in old["value_chain"] if not v.get("official") for c in v["companies"] if c.get("industry") == fam and c["ticker"] not in have]
    assert sorted(c["ticker"] for c in gone) == ["AEO", "ANF", "BKE", "DXLG", "GAP", "LE", "PLCE", "URBN"]
    group = {"layer": B.plain_industry(fam), "description": "", "official": True, "basis": "industry",
             "companies": [{"ticker": c["ticker"], "name": c.get("name"), "what": "", "verified": False, "base": True, "basis": "industry",
                            "industry": fam, "cap": c.get("cap")} for c in sorted(gone, key=lambda c: -(c.get("cap") or 0))]}
    out = replay46("retail", extra={"group": group, "evidence": {c["ticker"]: old["evidence"].get(c["ticker"]) for c in gone}})
    now = shown(out["value_chain"])
    assert len(now) == 106 and informative(now) == 69
    assert sorted(s_ for s_, x in now.items() if x == "Family clothing stores") == sorted(
        [c["ticker"] for c in gone] + ["CURV", "DLTH", "TLYS", "ZUMZ"])


# ---------- 3. the coverage control ----------
def test_the_coverage_control_flags_a_low_share_and_a_fall():
    """Fails before (no control): under 60% in informative layers is flagged; so is a fall of 8 points or more against the previous live
    read, kept said while the read is stored again unchanged (cover_was), and the coverage page says it with both numbers."""
    cov = {"informative": 58, "placed": 98, "share": 59, "other": 40}
    assert C.coverage_control(cov, {}) == {"low": True}
    assert C.coverage_control({**cov, "informative": 66, "share": 67}, {}) is None
    snap = {"cover": [66, 85]}
    ctl = C.coverage_control(cov, snap)
    assert ctl == {"low": True, "fell": {"informative": 66, "placed": 85, "share": 78}}
    assert C.coverage_control({"informative": 80, "placed": 100, "share": 80}, {"cover": [87, 100]}) is None      # 7 points: not flagged
    # stored again: the snapshot now holds this read, and the coverage before the change is kept until it changes again
    was = C.apply({"snap": {"layers": ["L"], "cos": {"A": ["A", 0, None, None, None, ""]}, "cover": [66, 85]}},
                  C.snapshot({"layers": [{"layer": "L", "companies": [{"symbol": "A"}]}], "coverage": cov}))
    assert was["snap"]["cover"] == [58, 98] and was["snap"]["cover_was"] == [66, 85]
    again = C.apply(was, C.snapshot({"layers": [{"layer": "L", "companies": [{"symbol": "A"}]}], "coverage": cov}))
    assert again["snap"]["cover_was"] == [66, 85]
    assert C.coverage_control(cov, again["snap"]) == ctl
    line = C.control_line({**cov, "control": ctl})
    assert line == ("58 of 98 companies placed (59%) are in informative layers, against 66 of 85 (78%) in the previous live placement: "
                    "19 points fewer, a fall of 8 or more. 59% of the companies placed are in informative layers (58 of 98), under 60%.")
    rows = deck.coverage_table({"coverage": {**cov, "control": ctl, "other_name": "Other consumer retail companies"}, "layers": []}, {"total": 98, "n": 90})
    flag = [r for r in rows if r[0] == "Coverage flag"]
    assert flag == [["Coverage flag", "59%", line]]
    assert not [r for r in deck.coverage_table({"coverage": {**cov, "informative": 80, "share": 82, "other": 18}, "layers": []}, {"total": 98, "n": 90})
                if r[0] == "Coverage flag"]


def test_a_flagged_theme_is_an_admin_check(monkeypatch):
    """Fails before: the flag is kept for the admins (theme_changes.flag) and listed as an autofix check (Needs your attention, one mail an
    issue through the existing admin alert); it clears once the theme passes."""
    from app import autofix, db
    store: dict = {}

    def update(k, fn, tries=10):
        new = fn(store.get(k))
        if new is not None:
            store[k] = new
        return store.get(k)
    monkeypatch.setattr(db, "update_setting", update)
    monkeypatch.setattr(db, "get_setting", lambda k: store.get(k))
    cov = {"informative": 58, "placed": 98, "share": 59, "control": {"low": True}}
    C.flag("US", "Consumer retail", {"informative": 80, "placed": 98, "share": 82})          # never flagged: nothing kept
    assert C.FLAGS_KEY not in store
    C.flag("US", "Consumer retail", cov)
    checks = TR.coverage_checks()
    assert len(checks) == 1 and isinstance(checks[0], autofix.Check) and checks[0].fix is None
    assert checks[0].name == "Theme coverage: Consumer retail (US)" and checks[0].problem == C.control_line(cov)
    assert TR.coverage_checks in autofix._sources
    C.flag("US", "Consumer retail", {"informative": 80, "placed": 98, "share": 82})          # passes now: the check clears
    assert [c.problem for c in TR.coverage_checks()] == [None]
    st = autofix.sweep([checks[0]], now=datetime.now(timezone.utc), st=autofix._empty(), send=lambda s, t: True)
    assert checks[0].id in st["open"]
    st = autofix.sweep(TR.coverage_checks(), now=datetime.now(timezone.utc), st=st, send=lambda s, t: True)
    assert checks[0].id not in st["open"] and st["history"][0]["event"] == "fixed"


def test_the_deck_carries_the_dive_s_control_only_for_the_same_count(monkeypatch):
    m = {"sector": "Consumer retail"}
    monkeypatch.setattr(TR, "map_coverage", lambda m: {"informative": 58, "placed": 98, "share": 59})
    assert TR.coverage_of(m, {"coverage": {"informative": 58, "placed": 98, "control": {"low": True}}})["control"] == {"low": True}
    assert "control" not in TR.coverage_of(m, {"coverage": {"informative": 60, "placed": 98, "control": {"low": True}}})


def test_a_coverage_flag_is_listed_in_admin_and_never_mailed(monkeypatch):
    # the owner's choice (13 Nov): the coverage control shows on the deck and under Needs your attention, without an email
    from app import autofix, db
    store = {}

    def update(k, fn, tries=10):
        new = fn(store.get(k))
        if new is not None:
            store[k] = new
        return store.get(k)
    monkeypatch.setattr(db, "update_setting", update)
    monkeypatch.setattr(db, "get_setting", lambda k: store.get(k))
    C.flag("US", "Consumer retail", {"informative": 58, "placed": 98, "share": 59, "control": {"low": True}})
    checks = TR.coverage_checks()
    assert checks and all(c.mail is False for c in checks)
    sent = []
    st, now = autofix._empty(), datetime.now(timezone.utc)
    for later in (0, 3600 * 6, 3600 * 30):                           # past every escalation window, across two days
        st = autofix.sweep(checks, now=now + timedelta(seconds=later), st=st, send=lambda s, t: sent.append(s) or True)
    issue = st["open"][checks[0].id]
    assert sent == [] and issue.get("escalated") and not issue.get("mailed")
    assert autofix.Check(id="x", name="x", problem="p").mail is True      # every other check still mails as before
