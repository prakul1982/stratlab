"""deck99 (owner, 27 Nov: "don't wait for me, just go"): what the deck96 audit of the 54 live theme decks left open, fixed as rules.

1. One issuer under two listings (Brookfield Renewable Partners L.P. and Brookfield Renewable Corp, US Electric utilities): kept once, under
   the listing with the larger latest revenue, the other listed under it. The replay on the 54 saved live dives merged that pair alone.
2. A member of the theme the map placed in a layer of another kind (Dominion Energy, a utility, among "Grid and power equipment makers"):
   out of that layer's figures as another business than the layer's, never "own words describe other work"; the theme's layer of its kind
   named.
3. The exchange's film industry takes a company only on words of the media (Purple Agrotech, an agro-technology company, in Media and
   entertainment's "Other"); the replay moved it alone of the industry's 14 companies in the live dive.
"""
import datetime as dt

from app import deck
from app.intel import theme_base as B
from app.intel import theme_data as D
from tests.test_theme1 import TODAY, facts

BEP_SAYS = ("Brookfield Renewable Partners L.P. operates one of the world's largest publicly traded platforms for renewable power; BEPC "
            "shares are exchangeable for units of the partnership")
BEPC_SAYS = ("While our operations are primarily located in the United States, Brazil, Colombia, and Europe, shareholders will, on economic "
             "terms, have exposure to all regions BEP operates in as a result of the exchange feature")


def _row(sym, name, rev, profit, cap, year="Dec 2025", **kw):
    return {"symbol": sym, "name": name, "revenue": rev, "profit": profit, "cap": cap, "year": year, **kw}


def test_one_issuer_under_two_listings_is_kept_once_under_the_larger():
    """Fails before: each one's words name the other's symbol, so the r63e rule (keep the one whose words don't) kept both."""
    bep = _row("BEP", "Brookfield Renewable Partners L.P.", 6407.0, -71.0, 8647.8)
    bepc = _row("BEPC", "Brookfield Renewable Corp", 3728.0, -2344.0, 4472.5)
    says = {"BEP": BEP_SAYS, "BEPC": BEPC_SAYS}
    assert D.same_company([bep, bepc], about=says.get) == {"BEPC": "BEP"}
    assert D.same_company([bepc, bep], about=says.get) == {"BEPC": "BEP"}          # whatever the order
    assert D.same_family(bepc, bep)
    # the map's line (read from its own words) names the other just as well
    assert D.same_company([bep, {**bepc, "map_what": BEPC_SAYS}], about={"BEP": "Brookfield Renewable operates renewable power plants",
                                                                          "BEPC": "Our group intends to generate this return"}.get) == {"BEPC": "BEP"}
    # (guards) no words naming the other: two companies; another year: two companies; names not one name but for entity words: two
    plain = {"BEP": "Brookfield Renewable operates renewable power plants", "BEPC": "Our group intends to generate this return"}
    assert D.same_company([bep, bepc], about=plain.get) == {}
    assert D.same_company([bep, {**bepc, "year": "Dec 2024"}], about=says.get) == {}
    lng = _row("LNG", "Cheniere Energy, Inc.", 19976.0, 3800.0, 50000, what="the largest producer of LNG in the US, ahead of VG")
    vg = _row("VG", "Venture Global, Inc.", 13769.0, 1200.0, 30000, what="unlike LNG, we build our plants in modules")
    assert D.same_company([lng, vg], about=lambda s: None) == {} and D.same_company([lng, vg], about={"LNG": lng["what"], "VG": vg["what"]}.get) == {}
    mpc = _row("MPC", "Marathon Petroleum Corp", 132699.0, 3000.0, 60000)
    mplx = _row("MPLX", "MPLX LP", 12998.0, 4000.0, 50000)
    assert D.same_company([mpc, mplx], about={"MPC": "MPC owns the general partner of MPLX", "MPLX": "MPLX was formed by MPC"}.get) == {}


def test_the_deck_says_another_listing_of_one_issuer_as_that():
    v = {"duplicates": [{"symbol": "BEPC", "name": "Brookfield Renewable Corp", "kept": "BEP", "kept_name": "Brookfield Renewable Partners L.P.",
                         "by": "family"}]}
    row = next(r for r in deck.confidence_rows(v, {"total": 2}, dt.date(2026, 11, 27)) if r[0] == "Same company twice")
    assert "Brookfield Renewable Corp (BEPC) is another listing of Brookfield Renewable Partners" in row[1], row
    assert "same latest year, revenue and net profit" not in row[1] and "larger latest revenue" in row[2], row
    # (guard) a pair with the same filed figures is said as before
    v["duplicates"].append({"symbol": "AILIH", "name": "Ameren Illinois Co", "kept": "AEE", "kept_name": "Ameren Corp"})
    row = next(r for r in deck.confidence_rows(v, {"total": 2}, dt.date(2026, 11, 27)) if r[0] == "Same company twice")
    assert "Ameren Illinois Co is Ameren Corp (the same latest year, revenue and net profit)" in row[1], row


def _build(theme, layers, what, ind):
    """A US dive of the map's own layers: layers = [(layer, [(sym, name, cap)])]."""
    cos = [(s, n, cap) for _, xs in layers for s, n, cap in xs]
    rows = [{"symbol": s, "name": n, "industry": ind[s], "market_cap": cap} for s, n, cap in cos]
    ai = {"sector": theme, "summary": "", "core": "", "sub_themes": [], "tailwinds": [], "risks": [], "generated_at": 0,
          "value_chain": [{"layer": lay, "description": "", "companies": [{"ticker": s, "name": n, "what": what[s], "verified": True} for s, n, _ in xs]}
                          for lay, xs in layers]}
    m = B.with_base(ai, {**ai, "placements": {"checked": True, "pending": 0}}, rows, [])
    f = {r["symbol"]: {**facts(r["symbol"], r["name"], [500, 600, 700, 800 + i * 20], [20.0, 21.0, 22.0, 18.0 + i], [50, 60, 70, 80 + i],
                               cap=r["market_cap"], pe=12.0, industry=(r["industry"],)), "region": "US", "unit": "$ million",
                       "annual_form": "10-K", "annual_filed": "2026-02-01"}
         for i, r in enumerate(rows)}
    return D.build("US", theme, m, D.Sources(TODAY, facts=f.get, about=lambda s: what.get(s)))


def _get(dive, sym):
    return next(c for v in dive["layers"] for c in v["companies"] if c["symbol"] == sym)


def test_a_member_in_a_layer_of_another_kind_is_out_of_that_layers_figures_never_other_work():
    """Fails before: Dominion Energy, a utility in Electric utilities, "not confirmed in the theme: its own words describe other work"
    (status unverified, evidence not confirmed), out of every figure of the theme and counted among the companies describing other work."""
    dom = "Dominion Energy’s mission is to provide the reliable, affordable and increasingly clean energy that powers its customers every day"
    what = {"DUK": "Duke Energy is one of the largest electric utility holding companies in the United States",
            "SO": "Southern Company is an electric utility holding company serving customers in the Southeast",
            "AEP": "American Electric Power is an electric utility holding company with operations in 11 states",
            "GEV": "GE Vernova makes power equipment for generation and the grid", "ETN": "Eaton makes electrical equipment and switchgear",
            "POWL": "Powell Industries makes switchgear and electrical equipment for industrial and utility customers", "D": dom}
    ut, eq = "Electric Services", "Electrical Industrial Apparatus, Nec"
    ind = {"DUK": ut, "SO": ut, "AEP": ut, "D": ut, "GEV": eq, "ETN": eq, "POWL": eq}
    dive = _build("Electric utilities", [("Regulated vertically integrated utilities", [("DUK", "Duke Energy Corp", 90000), ("SO", "Southern Co", 100000),
                                                                                           ("AEP", "American Electric Power Co Inc", 60000)]),
                                         ("Grid and power equipment makers", [("GEV", "GE Vernova Inc", 150000), ("ETN", "Eaton Corp Plc", 130000),
                                                                              ("POWL", "Powell Industries Inc", 3000), ("D", "Dominion Energy Inc", 59800)])],
                  what, ind)
    d = _get(dive, "D")
    assert d["status"] != "unverified" and d["evidence"] != "not_confirmed", (d["status"], d["evidence"])
    assert d["calc"]["in"] is False and d["calc"]["label"] == "another business than the layer's", d["calc"]
    said = d["calc"]["detail"] + " " + d["theme"]["why"] + " " + d["comparison"]
    assert "describe other work" not in said and "not confirmed" not in said, said
    assert "a different kind of business than its layer “Grid and power equipment makers” (power equipment making)" in d["calc"]["detail"]
    assert "so it is out of that layer's figures" in d["calc"]["detail"] and "powers its customers every day" in d["calc"]["detail"]
    assert "; the theme's layer “Regulated vertically integrated utilities” is of its kind (" in d["calc"]["detail"], d["calc"]["detail"]
    assert d["calc"]["detail"].endswith(" of its companies' own words state electric and gas utility)"), d["calc"]["detail"]
    lay = next(v for v in dive["layers"] if v["layer"] == "Grid and power equipment makers")
    assert "D" in lay["model_out"] and "D" not in lay["unverified"]
    assert "D" not in [x for xs in (lay.get("in_stats") or {}).values() for x in xs]
    # a member of the theme: counted among its companies with figures, never among those whose own words describe other work
    assert "D" in [x["symbol"] for x in dive["sections"]["size"]["biggest"]], dive["sections"]["size"]
    assert (dive.get("evidence") or {}).get("D") != "not_confirmed"
    # (guard) the utilities stay in their layer's figures (the equipment makers are as the scope rule leaves them: adjacent participants)
    for s in ("DUK", "SO", "AEP"):
        assert _get(dive, s)["calc"]["in"], (s, _get(dive, s)["calc"], _get(dive, s).get("status"), _get(dive, s).get("adjacent"))


def test_the_layer_of_a_kind_is_the_one_whose_companies_words_state_it_never_a_name_alone():
    from collections import Counter
    said = {"Independent power producers and generators": Counter({"electric and gas utility": 1}),
            "Regulated vertically integrated utilities": Counter({"electric and gas utility": 3}),
            "Grid and power equipment makers": Counter({"power equipment making": 2, "electric and gas utility": 1}),
            "Other electric utility companies": Counter({"electric and gas utility": 5})}
    assert D.kind_layers("electric and gas utility", said, "Grid and power equipment makers") == [("Regulated vertically integrated utilities", 3)]
    # Paccar among the railcar makers: the truckload carriers' layer is named for trucks but its companies are carriers, so no layer is named
    assert D.kind_layers("truck making", {"Asset-based truckload carriers": Counter(), "Railcar and rail equipment suppliers and lessors":
                                          Counter({"rail equipment making": 3, "truck making": 1})}, "Railcar and rail equipment suppliers and lessors") == []
    o = {"kind": "truck making", "layer": "Railcar and rail equipment suppliers and lessors (larger)", "layer_kind": "rail equipment making",
         "line": "The Truck segment includes the design and manufacture of trucks"}
    said_ = D.layer_other_detail(o, [])
    assert "its layer “Railcar and rail equipment suppliers and lessors” (rail equipment making)" in said_ and "of its kind" not in said_
    assert D.layer_other_detail(o, [("Truck makers", 2)]).endswith("the theme's layer “Truck makers” is of its kind (2 of its companies' own words state truck making)")


def test_a_film_industry_company_whose_words_say_no_work_of_the_media_is_not_of_media_and_entertainment():
    film = "Film Production, Distribution & Exhibition"
    agro = {"base": True, "industry": film, "what": "Business Overview: PAIL is currently engaged in the business of agro-technology"}
    assert D.not_of_kind("IN", "Media and entertainment", agro, "")
    for w in ("PVR INOX operates a cinema network of 1763 screens", "Tips Films Ltd is in the business of film production and distribution",
              "Diksat Transworld Ltd produces and broadcasts satellite television programming in Tamilnadu",
              "Media Matrix Worldwide Ltd specializes in Value Added Services for mobile and digital platforms",
              "UFO Moviez operates a network with advertising rights across 4,049 screens"):
        assert not D.not_of_kind("IN", "Media and entertainment", {**agro, "what": w}, ""), w
    assert not D.not_of_kind("IN", "Media and entertainment", {**agro, "what": ""}, "")          # no words read: never removed
    assert not D.not_of_kind("IN", "Media and entertainment", {**agro, "basis": "list"}, "")     # the theme's own list
    assert not D.not_of_kind("IN", "Media and entertainment", {**agro, "industry": "Media & Entertainment"}, "")   # another industry: as before
