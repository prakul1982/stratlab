"""R60 (lane r60a): the owner's outside review of the live R59 decks, classification: a valid business role is never hidden. Each test
fails on 92711df (R59) and passes after, unless marked a guard.
Fixtures: tests/fixtures/themes_live/r60, the placement inputs of six themes as production served them on 16 Nov 2026 (R59, rules 62), with
the map layers the R58.2/R59 rules emptied put back as the live map still has them (the same map: an older input of the same map's
`generated_at` holds them; a member the R58.2/R59 rules sent to "Other" back in its map layer), so the replay starts where live does."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))

from app.intel import theme_base as B  # noqa: E402
from app.intel import theme_check as C  # noqa: E402
from app.intel import theme_changes as TC  # noqa: E402
import deck_check as DC  # noqa: E402
import release_gate as G  # noqa: E402

LIVE = pathlib.Path(__file__).parent / "fixtures" / "themes_live" / "r60"
_ENGINE: dict = {}


def _engine(key):
    if key not in _ENGINE:
        d = G.load(LIVE / f"{key}.json")
        with G.offline():
            _ENGINE[key] = (d, G.engine(d)[0])
    return _ENGINE[key]


def _where(out, sym):
    return next(((v, c) for v in out["value_chain"] for c in v["companies"] if c["ticker"] == sym), (None, None))


# ---------- rule 2: layer semantics, not literal words ----------
def test_concepts_say_a_layer_by_its_meaning():
    # the reviewer's pairs: each company's words say its layer's concept though no literal word of the layer's name
    pairs = [("Cable and satellite distribution", "providing Direct to Home television and Teleport services"),
             ("Reinsurance", "engaged in the business of reinsurance"),
             ("Distribution and aggregation", "India's largest online platform for insurance and lending products"),
             ("Distribution and aggregation", "an insurance broking company"),
             ("Analog and power integrated device makers", "makes power management ICs and embedded processing chips"),
             ("Memory makers", "a producer of DRAM and NAND"),
             ("Semiconductor equipment", "develops photolithography systems used to produce integrated circuits"),
             ("Oilfield services and equipment makers", "provides offshore drilling services with jack-up rigs"),
             ("Security platforms", "a cybersecurity company selling firewalls"),
             ("Off-price, dollar and value retailers", "a Chinese retailer and variety store chain")]
    for layer, words in pairs:
        assert B.concept_said(layer, words), (layer, words)
        assert B.layer_line("", words + ".", "", layer), (layer, words)          # the line printed is the sentence that places it
    # never a concept by chance: no concept of a layer whose name and description give none
    assert not B.concept_said("Television broadcasting", "providing Direct to Home television")
    assert not B.concept_said("Life insurance underwriting", "an insurance broking company")
    # a layer's own description gives its concept too
    assert B.concept_said("Pay television distributors", "Direct to Home services",
                          "These firms carry channels to homes through cable or satellite and bill subscribers.")


def test_release_gate_reads_a_layer_by_its_concept():
    # deck_diff's and the gate's "layer words" read words as the placement does
    assert G.shares("Cable and satellite distribution", "Direct to Home television and Teleport services") is True
    assert G.shares("Print publishing", "Direct to Home television and Teleport services") is False


# ---------- rule 1: evidence-backed singleton layers are kept ----------
def test_single_layer_kept_on_its_company_words_and_folded_without():
    words = {"R": "R is engaged in the business of reinsurance.", "X": "X is a holding company with interests in hotels."}
    vc = [{"layer": "Reinsurance", "description": "Reinsurers take on portions of risk from primary insurers.",
           "companies": [{"ticker": "R", "name": "R"}]},
          {"layer": "Cold chain operators", "companies": [{"ticker": "X", "name": "X"}]},
          {"layer": "Life insurance underwriting", "companies": [{"ticker": t, "name": t} for t in "ABC"]},
          {"layer": "Other insurance companies", "official": True, "basis": "rest", "companies": []}]
    got, rows = B.single_layers(vc, lambda s: words.get(s, ""), "Insurance")
    re_ = next(v for v in got if v["layer"] == "Reinsurance")
    assert [c["ticker"] for c in re_["companies"]] == ["R"]
    assert "one company" in re_["single_kept"] and "reinsurance" in re_["single_kept"] and "no median" in re_["single_kept"]
    assert len(re_["single_kept"]) <= 200                      # the change log keeps 200 characters of it
    # a guard: a layer of one company whose words don't say it still folds, with the reason
    assert not any(v["layer"] == "Cold chain operators" for v in got)
    assert [r["ticker"] for r in rows] == ["X"]


def test_insurance_reinsurance_and_distribution_kept():
    # live R59 p.6: GIC Re out of "Reinsurance" and PB Fintech out of "Distribution and aggregation", both to "Other", 12 of 15 informative
    d, out = _engine("insurance")
    v, c = _where(out, "GICRE")
    assert v["layer"] == "Reinsurance" and len(v["companies"]) == 1 and v.get("single_kept")
    v, c = _where(out, "POLICYBZR")
    assert v["layer"] == "Distribution and aggregation" and v.get("single_kept")
    rows = {c["ticker"]: v["layer"] for v in out["value_chain"] for c in v["companies"]}
    n, of = B._informative(rows)
    assert n >= 13 and of == 15, (n, of)


def test_media_dish_tv_in_satellite_distribution():
    # live R59 p.8: Dish TV ("direct-to-home (DTH) ... and Teleport services") sent to "Other"
    d, out = _engine("media")
    v, c = _where(out, "DISHTV")
    assert v["layer"] == "Cable and satellite distribution", v["layer"]
    line = B.layer_line("", B.own_text(d["evidence"]["DISHTV"]), c["name"], v["layer"], v.get("description") or "")
    assert "Direct to Home" in line or "direct-to-home" in line.lower(), line
    # the R59 fix holds: the layer is not mostly left out of its figures
    figs = d.get("figures") or {}
    out_ = [x for x in v["companies"] if x.get("model_out") or isinstance(x.get("unfit"), dict) or not (figs.get(x["ticker"]) or {}).get("revenue")]
    assert len(out_) * 2 <= len(v["companies"]), [x["ticker"] for x in out_]


def test_defence_hal_and_midhani_in_their_layers():
    # independent review of the live R59 Defence deck: HAL ("designs, manufactures ... aircraft, helicopters") and MIDHANI ("manufactures
    # superalloys, titanium, special purpose steel") in "Other defence companies", each the one company of its map layer
    d, out = _engine("defence")
    assert _where(out, "HAL")[0]["layer"] == "Aircraft and helicopter manufacturing"
    assert _where(out, "MIDHANI")[0]["layer"] == "Specialty alloys and forged components"


# ---------- the checks: a one-company layer fails only on missing evidence or a statistic ----------
def test_gate_one_company_layer_fails_only_without_words():
    # updated on purpose: the owner's R59 review P0 (r582 failed every layer of one company)
    def gate(words):
        d = {"theme": "Insurance", "evidence": {"R": words}, "facts": {}, "placements": {},
             "value_chain": [{"layer": "Reinsurance", "companies": [{"ticker": "R", "name": "R Corp"}]},
                             {"layer": "Other insurance companies", "official": True, "basis": "rest", "companies": [{"ticker": "D", "name": "D"}]}]}
        return [f for f in G.checks(d, d["value_chain"], {}) if f["fail"] == "one-company layer"]
    assert not gate("R Corp is engaged in the business of reinsurance for primary insurers.")
    assert [f["subject"] for f in gate("R Corp is a holding company with interests in hotels.")] == ["“Reinsurance”"]


def test_deck_check_thin_layer_reads_the_printed_words():
    page = ("Smaller layers\n"
            " Layer                 Company                What it does                                 Revenue      Net margin\n"
            "\n"
            " Reinsurance           General Insurance      General Insurance Corporation of India is    ₹52,986 cr   18.2%\n"
            "                       Corporation of India   engaged in the business of Reinsurance\n"
            "\n"
            " Cold chain operators  Snowman Logistics      Snowman Logistics is a holding company        ₹500 cr      2.0%\n"
            "\n"
            "Each of these layers has one member company, so it has no median, range or ranking.\n")
    rows = DC.small_rows([page])
    assert [r[0] for r in rows] == ["Reinsurance", "Cold chain operators"]
    assert DC.says_layer("Reinsurance", rows[0][2]) and not DC.says_layer("Cold chain operators", rows[1][2])
    assert DC.says_layer("Cable and satellite distribution", "Dish TV provides Direct to Home television")
    table = " Reinsurance                                1          ₹52,986 cr      –                   – (1)             –\n"
    assert DC.thin_stat([table], "Reinsurance") == ""
    assert DC.thin_stat([" Reinsurance                                1          ₹52,986 cr      18.2%\n"], "Reinsurance")


def test_deck_check_flags_a_thin_layer_only_without_evidence():
    # updated on purpose: the owner's R59 review P0 ("“X” added (2 companies)" failed whatever the companies' words said)
    def fails(what, stat="–"):
        page = ("Since the previous version: layers changed 1: “Reinsurance” added (1 company).\n\n"
                " Layer                    Companies     Revenue        Net margin\n"
                f" Reinsurance                      1     ₹52,986 cr     {stat}\n\n"
                "Smaller layers\n"
                " Layer          Company          What it does                                    Revenue\n\n"
                f" Reinsurance    GIC Re           {what:46}  ₹52,986 cr\n\n"
                "Each of these layers has one member company, so it has no median, range or ranking.\n")
        return [x for x in DC.check_text(page)["findings"] if x["kind"] == "thin layer"]
    assert not fails("engaged in the business of Reinsurance")
    assert fails("a holding company of hotels")
    assert fails("engaged in the business of Reinsurance", stat="18.2%")          # a statistic printed for one company


# ---------- P1: retail format apart from brand ownership ----------
def test_retail_miniso_stays_with_the_value_retailers():
    # live R59 p.8: MINISO, "a Chinese retailer and variety store chain", moved into "Apparel and consumer brand owners"
    d, out = _engine("retail")
    assert _where(out, "MNSO")[0]["layer"] == "Off-price, dollar and value retailers"


def test_format_moves_a_store_chain_out_of_the_brand_owners():
    words = {"M": "M is a Chinese retailer and variety store chain that specializes in household goods featuring IP design.",
             "N": "N designs and markets branded apparel and footwear sold through wholesale partners."}
    vc = [{"layer": "Apparel and consumer brand owners", "companies": [{"ticker": t, "name": t} for t in "MNPQ"]},
          {"layer": "Off-price, dollar and value retailers", "companies": [{"ticker": t, "name": t} for t in "AB"]},
          {"layer": "Single-category specialty retailers", "companies": [{"ticker": t, "name": t} for t in "CD"]}]
    got, rows = B.format_moves(vc, lambda s: words.get(s, ""), "Consumer retail")
    assert [(r["ticker"], r["to"]) for r in rows] == [("M", "Off-price, dollar and value retailers")]
    assert "variety store chain" in rows[0]["why"] and "brand" in rows[0]["why"]


# ---------- P1: established pharmaceutical companies apart from biotechs ----------
def test_kind_apart_takes_established_pharma_out_of_the_biotechs():
    words = {"MRK": "Merck is an American multinational pharmaceutical company.",
             "JNJ": "J&J is an American multinational pharmaceutical, biotechnology, and medical technologies corporation.",
             "AMGN": "Amgen is an American multinational biopharmaceutical company.",
             "GILD": "Gilead is an American biopharmaceutical company.",
             "REGN": "Regeneron is an American biotechnology company."}
    vc = [{"layer": "Large commercial biotechs", "companies": [{"ticker": t, "name": t} for t in words]},
          {"layer": "Other biotech companies", "official": True, "basis": "rest", "companies": []}]
    got, rows = B.kind_apart(vc, lambda s: words.get(s, ""), "Biotech")
    pharma = next(v for v in got if v["layer"] == "Established pharmaceutical companies")
    assert sorted(c["ticker"] for c in pharma["companies"]) == ["JNJ", "MRK"]
    assert sorted(c["ticker"] for c in got[0]["companies"]) == ["AMGN", "GILD", "REGN"]
    assert all("pharmaceutical" in r["why"] for r in rows)
    # a guard: in a theme of another kind nothing moves
    assert not B.kind_apart([dict(v, companies=list(v["companies"])) for v in vc], lambda s: words.get(s, ""), "Pharma")[1]


# ---------- Textiles: a way of earning never takes a company out of a layer its words name ----------
def test_textiles_vedant_with_the_branded_apparel_companies():
    # live R59 p.7: "Resale and distribution" (2 companies) added by how they earn; Vedant Fashions' words ("a diverse portfolio of brands")
    # say nothing of it
    d, out = _engine("textiles")
    v, c = _where(out, "MANYAVAR")
    assert v["layer"] == "Branded apparel companies", v["layer"]
    assert not any(x["layer"] == "Resale and distribution" and len(x["companies"]) <= 2 for x in out["value_chain"])


def test_by_how_back_never_moves_a_company_whose_words_say_its_group():
    # a guard: an electronics manufacturing services company stays in a contract manufacturing group by how it earns
    words = {"E": "E is a leading Electronic Manufacturing Services (EMS) company with box-build capabilities for defence electronics."}
    vc = [{"layer": "Contract manufacturing", "by_model": True, "companies": [{"ticker": t, "name": t} for t in "EF"]},
          {"layer": "Defence electronics makers", "companies": [{"ticker": t, "name": t} for t in "AB"]}]
    got, rows = B.by_how_back(vc, lambda s: words.get(s, ""), "Defence")
    assert not rows


# ---------- membership: companies of another business ----------
def test_semis_hydrogen_panel_maker_is_another_business():
    # independent review of the live R59 Semiconductors deck: SunHydrogen, filed under semiconductors, sells hydrogen panels
    ev = ("Industry: Semiconductors & Related Devices. We may sell hydrogen panels to customers who own and operate them, sell hydrogen "
          "produced by systems we own or operate, license our technology to manufacturers.")
    assert C.off_industry(ev)
    assert not C.off_industry("Industry: Semiconductors & Related Devices. We design analog integrated circuits and microcontrollers.")


def test_defence_ship_breaker_is_out_of_scope():
    # independent review of the live R59 Defence deck: Hariyana Ship Breakers, a member by its official industry (Ship Building & Allied
    # Services), "in the business of ship breaking, trading and investment"
    about = ("Incorporated in 1981, Hariyana Ship Breakers Ltd is in the business of ship breaking, trading and investment activities. "
             "HSBL is engaged in ship breaking at Alang-Sosiya, Gujarat.")
    theme_text = "Defence Naval shipbuilding Explosives and missile makers Electronics and sub-systems"
    got = C.off_scope(about, theme_text, "Hariyana Ship Breakers Ltd")
    assert got and got["kind"] == "ship breaking and recycling"
    # a guard: a shipbuilder is of the theme
    assert not C.off_scope("Cochin Shipyard Limited is a leading player in construction of all kinds of vessels.", theme_text, "Cochin Shipyard")


# ---------- a fall in the informative share is said with why ----------
def test_coverage_fall_says_why_when_the_snapshot_is_the_new_placement():
    # live R59 Defence p.5 (91% -> 86%) and Insurance p.6 (93% -> 80%): "share fall unsaid"
    dive = {"layers": [{"layer": "Life insurance underwriting", "companies": [{"symbol": "A"}]},
                       {"layer": "Other insurance companies", "companies": [
                           {"symbol": "G", "refit": {"from": "Reinsurance", "to": "", "why": "a layer of one company"}}]}]}
    snap = {"cover": [1, 2], "cover_was": [2, 2], "cos": {"A": ["A", 0], "G": ["G", 1]}, "layers": ["Life insurance underwriting", "Other"]}
    got = TC.coverage_control({"informative": 1, "placed": 2}, snap, dive)
    assert got["fell"]["why"] and "Reinsurance" in next(iter(got["fell"]["why"]))
    assert "Why:" in TC.control_line({"informative": 1, "placed": 2, "control": got})


# ---------- LIVE9A-006: the largest companies placed, banks by their business, royalty owners named by what they own ----------
def test_oilgas_reliance_never_taken_out_of_every_layer_on_an_audit_quote():
    # live R59 Oil and gas (IN): Reliance Industries, the theme's largest company, in "Other oil and gas companies" on an audit quote about
    # the retail subsidiaries it holds
    d, out = _engine("oilgas")
    v, c = _where(out, "RELIANCE")
    assert not v["layer"].startswith("Other "), v["layer"]


def test_usoil_royalty_trusts_named_by_what_they_own():
    # live R59 US Oil and gas: royalty trusts in a layer named "Designs licensed for royalties"
    d, out = _engine("usoil")
    v, c = _where(out, "PRT")
    assert v["layer"] != "Designs licensed for royalties" and "royalty" in v["layer"].lower(), v["layer"]


def test_an_operating_company_is_no_holding_company_of_a_small_listed_subsidiary():
    # live R59 Automotive: Mahindra & Mahindra left out of its layer as a "holding company of other members" (52.5% of M&M Financial)
    from app.intel import theme_data as D
    rows_ = {"MM": {"symbol": "MM", "name": "Mahindra & Mahindra Ltd", "revenue": 160000.0, "status": "core"},
             "MMFIN": {"symbol": "MMFIN", "name": "M&M Financial Services Ltd", "revenue": 17000.0, "status": "core"}}
    parents = {"MMFIN": {"parent": "MM", "parent_name": "Mahindra & Mahindra Ltd", "pct": 52.5, "quarter": "2026-09"}}
    rows_["MMFIN"]["parent"] = parents["MMFIN"]
    D.holding_across(rows_, parents, {"MM": "Passenger vehicles", "MMFIN": "Vehicle finance"}, {"MM"}, "Automotive")
    assert not rows_["MM"].get("adjacent") and rows_["MM"]["holds_elsewhere"][0]["symbol"] == "MMFIN"


# ---------- LIVE9A-004: description-verified never beside "no description" ----------
def test_a_description_verified_company_with_no_line_is_said_apart():
    from app import deck
    small = [{"layer": "Reinsurance", "companies": [{"symbol": "R", "name": "R Corp", "what": "", "evidence": "description_verified",
                                                     "revenue": 100.0, "cap": 5.0}]},
             {"layer": "Cold chain operators", "companies": [{"symbol": "S", "name": "S Corp", "what": "", "evidence": "industry_code_supported",
                                                              "revenue": 50.0, "cap": 2.0}]}]
    slides = []
    deck._smaller_layers(slides, small, lambda x: "–" if x is None else f"{x:g}", "The value chain")
    rows = [r for s_ in slides for b in s_.blocks if b["kind"] == "table" for r in b["rows"]]
    cells = {r[1]: r[2] for r in rows}
    assert cells["R Corp"] == deck.READ_NO_LINE and cells["S Corp"] == deck.NO_WORDS
    note = " ".join(p for s_ in slides for b in s_.blocks if b["kind"] == "text" for p in b["paras"])
    assert "no median, range or ranking" in note


# ---------- no flip-flop: the last re-check's moves are not undone on no words, and a published member is no newcomer ----------
def test_one_the_last_recheck_moved_out_on_no_words_is_not_put_back():
    # the R60 replay of the live R59 IT services and Logistics inputs: Infronics, Netlink and Aspinwall, moved out of their layers by R59 on
    # no word of their own, placed in them again by the next check
    words = {"N": "N is in the business of web site design, domain booking and exhibition management services.",
             **{t: f"{t} provides engineering research and development services to manufacturers." for t in "ABC"}}
    vc = [{"layer": "Engineering R&D services", "companies": [{"ticker": t, "name": t} for t in "ABC"] + [{"ticker": "N", "name": "N", "placed": "ai"}]},
          {"layer": "Other IT service companies", "official": True, "basis": "rest", "companies": []}]
    got, rows = B.listed_out(vc, lambda s: words.get(s, ""), "IT services", {"N": ["Engineering R&D services", "Other IT service companies"]})
    assert [(r["ticker"], r["to"]) for r in rows] == [("N", "")] and "the last re-check moved it out" in rows[0]["why"]
    # a guard: one whose words say the layer stays
    vc[0]["companies"][-1] = {"ticker": "A2", "name": "A2", "placed": "ai"}
    words["A2"] = "A2 provides engineering research and development services."
    got, rows = B.listed_out(vc, lambda s: words.get(s, ""), "IT services", {"A2": ["Engineering R&D services", "Other IT service companies"]})
    assert not rows


def test_a_published_member_is_no_newcomer_to_its_layer():
    # the R60 replay of the live R59 IT services input: some twenty companies the R59 re-check moved into "Mid-tier digital engineering and
    # cloud services", published there, judged new again on the change log and sent to "Other" (80% -> 73% informative)
    words = {"X": "X develops custom software applications for enterprises.", "A": "A offers digital engineering and cloud services.",
             "B": "B offers digital engineering services.", "C": "C offers cloud services."}
    def run(published):
        out = [{"layer": "Mid-tier digital engineering and cloud services", "description": "",
                "companies": [{"ticker": t, "name": t, "industry": "Computers - Software"} for t in "ABCX"]},
               {"layer": "Engineering R&D services", "description": "", "companies": [{"ticker": t, "name": t} for t in "DE"]},
               {"layer": "Other IT service companies", "description": "", "official": True, "basis": "rest", "companies": []}]
        got = B.sold_what(out, {}, lambda v: False, lambda cos: "", lambda c: "", lambda c: words.get(c.get("ticker"), ""),
                          B.kind_stems("IT services"), "IT services", {}, None,
                          {"X": ["Engineering R&D services", "Mid-tier digital engineering and cloud services"]}, published)
        return next(v["layer"] for v in got for c in v["companies"] if c["ticker"] == "X")
    assert run({"X": "Mid-tier digital engineering and cloud services"}) == "Mid-tier digital engineering and cloud services"
