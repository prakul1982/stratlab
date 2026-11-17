"""r64e (R64): the last flags of the live R63 decks (US Steel and metals' mostly-left-out layer, the Electric utilities deck_diff
"one-company layer", Our Bond in Telecom US "Network equipment makers"), and what a read of the 34 decks found, each fix generic
(India and US), each test failing before the fix and passing after it."""
import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from app.intel import theme_base as B


def _rows(vc):
    return {c["ticker"]: (v["layer"], c) for v in vc for c in v.get("companies") or []}


# ---------- 1. US Steel and metals p.25: the map's service centers left out of a layer named for them ----------
def _metals(name: str, dist_words: dict, dist_model: str = "distribution"):
    miners = [{"ticker": f"M{i}", "name": f"Miner {i} Corp", "industry": "Metal Mining", "placed": "words"} for i in range(3)]
    dists = [{"ticker": s, "name": f"Service {s} Inc", "industry": "Wholesale-Metals Service Centers & Offices", "verified": True}
             for s in dist_words]
    vc = [{"layer": name, "description": "Metals service centers buy metal from mills, process it and deliver it; the layer also holds miners.",
           "companies": miners + dists},
          {"layer": "Steel makers", "description": "Integrated steel mills.",
           "companies": [{"ticker": f"S{i}", "name": f"Steel {i} Corp", "industry": "Steel Works"} for i in range(3)]}]
    ev = {**{f"M{i}": "Miner Corp mines silver and zinc and sells its concentrates to smelters." for i in range(3)},
          **{f"S{i}": "Steel Corp makes steel in its integrated mills." for i in range(3)}, **dist_words}
    models = {**{f"M{i}": "commodity_mining" for i in range(3)}, **{s: dist_model for s in dist_words}, **{f"S{i}": "manufacturing" for i in range(3)}}
    conf = {s: "high" for s in models}
    # (the service centers were in this layer in the version before: they keep it, as the live ones did)
    return B.by_model(copy.deepcopy(vc), models, "Steel and metals", confidence=conf, evidence_of=lambda s: ev.get(s, ""),
                      previous={s: name for s in dist_words})


def test_1_a_layer_named_for_distributors_takes_its_distributors_in_its_figures():
    """Fails before: Reliance and Ryerson, the map's own "Metals service centers", listed in "Metals distributors and mining developers" and
    left out of its figures as "different revenue model (distribution and trading, the layer's miners ...)" once miners placed by their
    words outnumbered them: 2 of 5 in the layer's calculations. A layer whose name states distributors takes a distributor whose words say so."""
    out = _metals("Metals distributors and mining developers",
                  {"RS": "We distribute a full line of over 100,000 metal products from approximately 310 locations.",
                   "RY": "We are a leading value-added processor and distributor of industrial metals."})
    got = _rows(out)
    for s in ("RS", "RY"):
        assert "model_out" not in got[s][1] and got[s][1].get("by_words"), got[s][1]
    v = next(v for v in out if v["layer"].startswith("Metals distributors"))
    assert v["model"]["out"] == 0 and "a way of earning the layer's own name states too" in v["model"]["line"]


def test_1b_a_name_saying_distribution_alone_takes_no_reseller():
    # (guard) "Transmission and distribution": a grid's distribution is no resale, so a reseller read there stays out of its figures
    out = _metals("Transmission and distribution utilities", {"RS": "We distribute electricity products to contractors."})
    assert _rows(out)["RS"][1].get("model_out"), _rows(out)["RS"][1]


# ---------- 2. Electric utilities deck_diff: "8 of 10" read whole ----------
def test_2_a_count_running_past_its_cell_is_read_whole():
    """Fails before: the live R63 Electric utilities deck's "Competitive power generation   8 of 10", the "10" past the cell's edge, was read
    as "8 of 1", a layer of one company, and deck_diff failed it as a one-company layer (Constellation Energy alone)."""
    import deck_diff as DD
    head = " Layer" + " " * 50 + "Companies          Revenue    EBITDA margin"
    page = "\n".join(["The value chain by layer (1 of 2)", "", head, "",
                      " Competitive power generation" + " " * 35 + "8 of 10    $55.8 bn   21.9% (7 of 8)", "",
                      " Wildfire-exposed western utilities" + " " * 34 + "3     $49.6 bn   – (2 of 3)", "",
                      " Regulated vertically integrated" + " " * 54 + "37.5% (14 of",
                      " " * 60 + "16 of 23      $155.9 bn",
                      " utilities" + " " * 77 + "16)", "",
                      "StratLab · Electric utilities · Theme deep dive"])
    got = DD.layer_counts([page])
    assert got["Competitive power generation"] == 10, got
    assert got["Wildfire-exposed western utilities"] == 3 and got["Regulated vertically integrated utilities"] == 23, got


# ---------- 3. Telecom US: a map pick whose own words say no word of its layer ----------
def _telecom(o_words: str):
    words = {"E": "Ericsson provides mobile network equipment, radio access networks and network software to operators.",
             "C": "Ciena makes optical networking equipment and network software for network operators.",
             "O": o_words}
    out = [{"layer": "Network equipment makers", "description": "Makers of network and access equipment.",
            "companies": [{"ticker": t, "name": n, "industry": ind} for t, n, ind in
                          (("E", "Ericsson", "Communications Equipment"), ("C", "Ciena", "Communications Equipment"),
                           ("O", "Our Bond, Inc.", "Services-Prepackaged Software"))]},
           {"layer": "Tower owners", "description": "Owners of towers.", "companies": [{"ticker": "T", "name": "Towers Co"}]},
           {"layer": "Other telecom companies", "description": "", "official": True, "basis": "rest", "companies": []}]
    words["T"] = "Towers Co owns and leases wireless towers."
    placed = {"E": "Network equipment makers", "C": "Network equipment makers", "O": "Network equipment makers", "T": "Tower owners"}
    # (its layer in the version before is one this placement did not make: nowhere to go back to)
    # (how each earns, as read: the equipment makers make, Our Bond sells software and services)
    fams = {"E": "making", "C": "making", "O": "software", "T": "capacity"}
    fam = lambda c: fams.get(c.get("ticker"), "")      # noqa: E731
    main = lambda cos: __import__("collections").Counter(fam(c) for c in cos if fam(c)).most_common(1)[0][0] if any(fam(c) for c in cos) else ""      # noqa: E731
    return B.sold_what(out, placed, lambda v: False, main, fam, lambda c: words.get(c.get("ticker"), ""),
                       B.kind_stems("Telecom"), "Telecom", {"O": "Software products and subscriptions"}, None, {})


def test_3_a_map_pick_whose_words_say_no_word_of_its_layer_goes_to_other():
    """Fails before: Our Bond, "We provide preventative personal security powered by AI ...", the map's old pick for "Network and access
    equipment makers", was put back into "Network equipment makers" once the layer it was published in was not made ("the map placed it in
    ... and its own words say what no other layer sells") and printed there, in the layer's figures. Its words, official industry and name
    say no word of the layer: it goes to "Other", with the reason."""
    got = _rows(_telecom("We provide preventative personal security powered by AI. Once activated, the cloud-based platform provides users "
                         "with remote protective services via phone app and 24/7 support from our personal security agents."))
    lay, c = got["O"]
    assert lay == "Other telecom companies", (lay, c)
    assert "say no word of “Network equipment makers”" in c["refit"]["why"], c["refit"]


def test_3b_a_map_pick_whose_words_say_a_word_of_its_layer_stays():
    # (guard) r582: one whose words are silent on what the layer sells but say a word of it (networks) stays as the map placed it
    got = _rows(_telecom("We design and sell fiber management and fiber protection solutions used across broadband networks."))
    assert got["O"][0] == "Network equipment makers", got["O"]


# ---------- 6. the 34 decks' text: the universe line's sources add up ----------
def test_6_a_company_listed_twice_is_said_in_the_universe_line_so_the_sources_add_up():
    """Fails before: the live R63 US Steel and metals deck, "180 companies (177 in the exchange's industry list, 6 added by the AI)", 183
    sources for 180 companies, three of them a second listing of a company counted once (Electric utilities "128 companies (131 in the
    exchange's industry list)", Biotech, REITs, Software, Regional banks and four more the same); Telecom US printed "1 more, their source
    not kept with this read" for two kept on their own words less one listed twice."""
    from app import deck
    twice = [{"ticker": t, "name": t, "kept": "K"} for t in ("A1", "A2", "A3")]
    got = deck.membership_words({"placements": {"base": 177, "named": 0, "added": 6, "same_company": twice}}, 180)
    assert got.startswith("180 companies (177 in the exchange's industry list, 6 added by the AI, less 3 listed twice under another symbol, "
                          "counted once)"), got
    got = deck.membership_words({"placements": {"base": 131, "named": 0, "added": 0, "same_company": twice}}, 128)
    assert got.startswith("128 companies (131 in the exchange's industry list, less 3 listed twice under another symbol, counted once)"), got
    v = {"placements": {"base": 90, "named": 0, "added": 9, "same_company": twice[:1]},
         "members": [{"symbol": "NOK", "name": "Nokia Corp", "source": "words"}, {"symbol": "CSCO", "name": "Cisco Systems, Inc.", "source": "words"}]}
    got = deck.membership_words(v, 100)
    assert got.startswith("100 companies (90 in the exchange's industry list, 9 added by the AI, 2 kept on their own words from other industries "
                          "(Nokia Corp, Cisco Systems, Inc.), less 1 listed twice under another symbol, counted once)"), got
    assert "source not kept" not in got


def test_6b_a_stored_reason_ends_on_a_whole_word_and_closes_its_quote():
    """Fails before: the live R63 decks' change logs printed reasons cut where the stored text was cut: US Steel and metals "and “Additionally,
    Ferroglobe currently has (i) quart)" and "nothing of “Makers of thei)", Insurance "... Policybazaar and Paisab;"."""
    from app.intel import theme_changes as TC
    why = ("its own words: “Ferroglobe is one of the world’s largest producers of silicon metal, silicon-based alloys and manganese-based "
           "alloys.” (what “Mini-mill steel, pipe and alloy makers” is), and “Additionally, Ferroglobe currently has (i) quartz mines in Spain")
    dive = {"layers": [{"layer": "Mini-mill steel, pipe and alloy makers", "companies": [
        {"symbol": "GSM", "name": "Ferroglobe plc", "refit": {"from": "Raw material mining", "to": "Mini-mill steel", "why": why}}]},
        {"layer": "Distribution and aggregation", "single_kept": "one company, its own words: “PB Fintech Ltd, popularly known as Policy "
                                                                "Bazar is India’s largest online platform for insurance and lending products "
                                                                "through its flagship brands - Policybazaar and Paisabazaar.”",
         "companies": [{"symbol": "PB", "name": "PB Fintech"}]}]}
    snap = TC.snapshot(dive, ["GSM", "PB"])
    got = snap["mwhy"]["GSM"]
    assert len(got) <= 240 and got.endswith("…”") and "quart…" not in got and got.count("“") == got.count("”"), got
    kept = snap["kept_layers"]["Distribution and aggregation"]
    assert len(kept) <= 200 and kept.endswith("…”") and not kept.endswith("Paisab…”"), kept
    assert TC.clip_words("a short reason", 200) == "a short reason"


def test_6c_a_layer_renamed_in_the_change_log_says_why():
    """Fails before: the live R63 Fertilizers deck's "“Urea and nitrogen producers” renamed “Urea producers and mixed chemicals makers”" and
    US Steel and metals' four renames, printed with no reason (deck_diff: "(no reason)"): the AI's name, or the placement's own reason."""
    from datetime import date
    from app import deck
    e = {"d": "2026-11-17", "layers": [{"kind": "renamed", "from": ["Urea and nitrogen producers"], "to": ["Urea producers and mixed chemicals makers"], "n": 9},
                                       {"kind": "renamed", "from": ["Regional integrated producers"], "to": ["Cement integrated producers"], "n": 12}]}
    v = {"changes": {"entries": [e]}, "coverage": {},
         "placements": {"contract": {"layers": [{"layer": "Regional integrated producers", "renamed": "Cement integrated producers (larger)",
                                                 "why": "none of its companies' own words say a word of “Regional integrated producers”"}]}}}
    row = deck.cohort_row(v, date(2026, 11, 17))[2]
    assert "“Urea and nitrogen producers” renamed “Urea producers and mixed chemicals makers” (the AI's name for the companies it holds, 9 of them in it before)" in row, row
    assert "renamed “Cement integrated producers” (none of its companies' own words say a word of “Regional integrated producers”)" in row, row
    import deck_diff as DD
    log = DD.log_rows(row)
    assert all(why for _, why in log["layers"]), log["layers"]


def test_3c_a_layer_none_of_whose_companies_say_its_name_keeps_the_map_s_picks():
    # (guard) the live R60 Cement "Regional integrated producers", a name none of its twelve companies' words say: the in-place rename's case
    # (truthful_layers: "Cement integrated producers"), never an empty layer
    words = {f"C{i}": f"Cement {i} Ltd manufactures and sells cement and clinker from its plants." for i in range(4)}
    out = [{"layer": "Regional integrated producers", "description": "", "companies": [{"ticker": t, "name": f"Cement {t} Ltd",
                                                                                       "industry": "Cement & Cement Products"} for t in words]},
           {"layer": "Pan-India producers", "description": "", "companies": [{"ticker": "P", "name": "Pan Ltd"}]},
           {"layer": "Other cement companies", "description": "", "official": True, "basis": "rest", "companies": []}]
    words["P"] = "Pan Ltd makes cement across India."
    placed = {t: "Regional integrated producers" for t in words if t != "P"} | {"P": "Pan-India producers"}
    got = _rows(B.sold_what(out, placed, lambda v: False, lambda cos: "", lambda c: "", lambda c: words.get(c.get("ticker"), ""),
                            B.kind_stems("Cement"), "Cement", {t: "Cements integrated producers" for t in words if t != "P"}, None, {}))
    assert all(got[t][0] == "Regional integrated producers" for t in words if t != "P"), got


def test_1c_the_page_s_line_keeps_the_way_the_layer_s_name_states_counted_over_its_page():
    """Fails before: the replay of the live R63 US Steel and metals input put Reliance and Ryerson in the layer's figures, and the page's line
    (counted over the companies shown) said only the miners' way of earning."""
    out = _metals("Metals distributors and mining developers",
                  {"RS": "We distribute a full line of over 100,000 metal products.", "RY": "We are a leading processor and distributor of metals."})
    v = next(v for v in out if v["layer"].startswith("Metals distributors"))
    rows = [{"model": c.get("model"), "model_tags": [], "model_out": c.get("model_out")} for c in v["companies"] if c["ticker"] != "M2"]
    got = B.shown_model(v["model"], rows)
    assert got["of"] == 4 and "2 of them earn from the margin on goods bought from makers and sold on to businesses, a way of earning the " \
        "layer's own name states too, and are in its figures by their own words." in got["line"], got["line"]


def test_3d_a_map_pick_of_the_layer_s_own_way_of_earning_whose_short_words_say_no_word_of_it_stays():
    # (guard) Alphabet and Snap in "Consumer internet, games and advertising", Howmet in "Materials, castings and forgings": a general
    # description of a company read to earn the layer's way is silent on the layer, never a contradiction (r582 stands)
    got = _rows(_telecom("Our Bond, Inc. is a technology company. We believe the camera presents the greatest opportunity."))
    assert got["O"][0] == "Other telecom companies"          # (read as software beside makers: apart)
    words = {"E": "Ericsson provides mobile network equipment and network software.", "C": "Ciena makes optical networking equipment.",
             "O": "Our company is a technology company with a long history."}
    out = [{"layer": "Network equipment makers", "description": "", "companies": [{"ticker": t, "name": t} for t in "ECO"]},
           {"layer": "Other telecom companies", "description": "", "official": True, "basis": "rest", "companies": []}]
    fam = lambda c: "making"      # noqa: E731
    got = _rows(B.sold_what(out, {t: "Network equipment makers" for t in "ECO"}, lambda v: False, lambda cos: "making", fam,
                            lambda c: words.get(c.get("ticker"), ""), B.kind_stems("Telecom"), "Telecom", {"O": "Gone layer"}, None, {}))
    assert got["O"][0] == "Network equipment makers", got["O"]
