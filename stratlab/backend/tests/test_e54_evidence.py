"""Lane e54 (Release 54): evidence states and population reconciliation, from the owner's review of the live R53 decks.

1. P0 membership-evidence states, one each, the same on the deck, the app's theme page and the public page: "description_verified" (own
   words read and showing the work), "industry_code_supported" (kept on its official industry alone), "membership_unverified" (not checked
   yet); never "confirmed by their own description" for a company kept on its industry (Medical devices p.4: "100 confirmed by their own
   description" beside "18 companies with figures have no description in their own words yet"; Hospitals 98 vs 43). Counts add up.
2. P0 core vs adjacent populations: every count says which population it is of (Medical devices: "76 with figures" beside "Each layer" rows
   adding up to 100, the adjacent participants among them); the core's share of market value leaves the adjacent out.
3. P1 consolidated vs segment: a company whose whole-company figures, of another way of earning too, stand in a layer's figures says so on
   its row and in the layer's notes; layers of different ways of earning set side by side say why they are never ranked against each other.
4. P1 verified coverage: the membership check moves on through the companies not checked yet, a bounded step each stored read (Biotech
   "564 still not checked", Software 488: the check was always the same window), with the checked share after each version.
deck_check: "evidence state" and "population mismatch".

The live inputs are tests/fixtures/themes_live/inputs_r52 (the owner's read-only placement inputs of 14 Nov 2026); every figure is synthetic."""
import json
from datetime import date

from app import deck, public_themes
from app.intel import theme_changes as TC, theme_data as D, theme_routes as TR
from tests.test_d53_fixes import DC, inputs, replay, synthetic_deck

WORDS = D._stems("Medical devices implants catheters surgical instruments")


# ---------- 1. evidence states ----------
def test_each_company_has_one_evidence_state_and_an_industry_code_is_never_its_own_description():
    base = {"base": True, "basis": "industry", "industry": "Surgical & Medical Instruments"}
    assert D.evidence_state({**base, "ticker": "A", "name": "Alpha", "what": ""}, WORDS) == "industry_code_supported"
    # a line that is no words of its own about its work (an encyclopedia's lead) is no description either
    lead = {**base, "ticker": "B", "name": "Beta Corp", "what": "Beta Corp is an American company headquartered in Ohio"}
    assert D.evidence_state(lead, WORDS) == "industry_code_supported"
    assert D.evidence_state({**base, "ticker": "C", "name": "Gamma", "what": "We make catheters and surgical instruments."}, WORDS) == "description_verified"
    # its stored description read and found to say its layer's work (verified), with its own words there to show
    ver = {**base, "ticker": "D", "name": "Delta Ltd", "what": "", "verified": True}
    assert D.evidence_state(ver, WORDS, about="Delta Ltd makes orthopaedic implants for hospitals.") == "description_verified"
    assert D.evidence_state(ver, WORDS, about=None) == "industry_code_supported"          # nothing of its own to show: its industry
    assert D.evidence_state({"ticker": "E", "name": "Eps", "base": False, "verified": True, "what": "makes implants"}, WORDS) == "description_verified"
    assert D.evidence_state({"ticker": "F", "name": "Phi", "base": False, "verified": False, "what": ""}, WORDS) == "not_confirmed"
    assert D.evidence_state({**base, "ticker": "G", "name": "Gee", "what": "We operate a chain of hotels and restaurants."}, WORDS) == "not_confirmed"
    assert D.evidence_state({"ticker": "H", "name": "Aitch", "what": ""}, WORDS) == "membership_unverified"     # a map from before the checks
    assert D.evidence_state({"ticker": "I", "base": True, "basis": "list", "name": "Eye", "what": ""}, WORDS) == "list_supported"
    assert D.evidence_counts({"A": "description_verified", "B": "industry_code_supported"})["industry_code_supported"] == 1


def test_the_universe_line_never_says_an_industry_code_is_confirmed_by_its_own_description_and_its_counts_add_up():
    """Fails before: "100 checked (...): 100 confirmed by their own description, 0 not; 122 not checked yet" beside 18 companies with
    figures and no words of their own (the live R53 Medical devices deck, p.4)."""
    v = {"placements": {"base": 217, "added": 5}, "membership": {"placed": 100, "confirmed": 100, "not_confirmed": 0}, "membership_evidence": {"description_verified": 82, "industry_code_supported": 18}}
    said = deck.membership_words(v, 222)
    assert ("100 checked (the map's own picks, then the largest by market value): 82 confirmed by their own description, 18 kept on their "
            "official industry only, 0 whose own words describe other work; 122 not checked yet") in said
    # the companies the membership check reached beyond the figures' window are among those checked
    v2 = {**v, "membership_check": {"outside": {f"X{i}": "industry_code_supported" for i in range(50)} | {"Y": "description_verified"}}}
    said2 = deck.membership_words(v2, 222)
    assert "151 checked (the map's own picks, then the largest by market value, and 51 more reached by the membership check)" in said2
    assert "83 confirmed by their own description, 68 kept on their official industry only" in said2 and "71 not checked yet" in said2
    c = deck.reconciled_counts(v2, {"total": 222, "n": 76})
    assert (c["checked"], c["confirmed"], c["split"]) == (151, 151, (83, 68))
    assert deck.counts_words(c).startswith("Considered 222 · confirmed 151 (of 151 checked) · with figures 76")


def test_the_membership_row_counts_the_industry_only_companies_and_every_wordless_one_is_among_them():
    v = {"layers": [{"layer": "L", "companies": [{"symbol": "A", "name": "Alpha Inc", "status": "core", "revenue": 10.0, "what": "We make implants."},
                                                 {"symbol": "B", "name": "Beta Inc", "status": "core", "revenue": 12.0, "what": None}]}],
         "membership": {"placed": 2, "confirmed": 2, "not_confirmed": 0}, "membership_evidence": {"description_verified": 1, "industry_code_supported": 1}, "checks": {}}
    rows = {r[0]: r for r in deck.confidence_rows(v, {"total": 2}, date(2026, 11, 14))}
    assert rows["Membership"][1] == ("1 of the 2 checked are kept on their official industry only. "
                                     "1 company with figures have no description in their own words yet: Beta Inc.")
    assert "confirmed by their own description" not in rows["Universe"][1].split("1 confirmed by their own description")[1]


def test_on_the_live_r52_medical_devices_inputs_no_company_without_words_is_counted_as_confirmed_by_them():
    """Fails before: every confirmed company was "confirmed by their own description", 214 of them with no words of their own shown."""
    d = inputs("inputs_r52/meddev.json")
    v, slides = synthetic_deck(d, replay(inputs("inputs_r52/meddev.json")))
    ev = v["membership_evidence"]
    assert sum(ev.values()) == v["membership"]["placed"]
    wordless = deck.without_words(v)
    assert len(wordless) <= ev["industry_code_supported"] + ev["list_supported"]
    every = {c["symbol"]: c for b in v["layers"] for c in b["companies"]}
    for c in every.values():           # a company confirmed by its own description shows those words
        if c.get("evidence") == "description_verified":
            assert c.get("what"), c["name"]
    from tests.test_export import texts
    t = "\f".join(texts([s]) for s in slides)
    assert DC.check_text(t)["counts"]["evidence state"] == 0 and DC.check_text(t)["counts"]["population mismatch"] == 0


# ---------- 2. core vs adjacent populations ----------
def test_every_count_says_its_population_and_the_layers_add_up_to_core_plus_adjacent_on_the_live_r52_inputs():
    """Fails before: "Companies, by count 183 of 222" beside an "Each layer" row of 222 companies with figures, nothing said of the 39
    adjacent participants among them; the share of market value counted them in."""
    d = inputs("inputs_r52/meddev.json")
    v, slides = synthetic_deck(d, replay(inputs("inputs_r52/meddev.json")))
    pop = deck.population(v)
    assert pop["adjacent"] == 39 and pop["core"] == v["members_with_figures"]
    cov = deck.coverage(v)
    rows = {r[0]: r for r in deck.coverage_table(v, cov)}
    assert rows["Companies, by count"][2].endswith("the theme's core members only, the 39 adjacent participants with figures apart")
    assert rows["Each layer"][2].startswith(f"{pop['core']} core members + 39 adjacent participants = {pop['core'] + 39} with figures (adjacent layers: "
                                            "Diagnostic and genetic testing labs, Hospital and care facility operators); companies with figures:")
    assert "with figures 183 core members" in deck.counts_words(deck.reconciled_counts(v, cov))
    # the share of market value is the core members'
    adj = {x["symbol"] for x in v["adjacent"]}
    vs = deck.value_share(v)
    assert vs["value_with"] == sum(m.get("cap") or 0 for m in v["members"] if m["symbol"] not in adj and m.get("revenue") is not None
                                   and (v["status"].get(m["symbol"]) != "unverified"))
    names = [r[0] for s in slides if s.title.startswith(("The value chain by layer", "Layers side by side")) for b in s.blocks
             if b["kind"] == "table" for r in b["rows"] if not isinstance(r, dict)]
    assert "Hospital and care facility operators (adjacent)" in names and "Implantable devices" in names
    foot = " ".join(p for s in slides if s.title.startswith("The value chain by layer") for b in s.blocks if b["kind"] == "text" for p in b["paras"])
    assert deck.ADJACENT_NOTE in foot and f"The theme's totals are of its {pop['core']:,} core members with figures." in foot
    assert deck.layer_count_flags(slides) == []                    # a layer's mark never makes its counts look like another layer's


# ---------- 3. consolidated figures and ways of earning ----------
def _layer(name, fam, mid, cos):
    return {"layer": name, "model": {"id": mid, "family": fam, "line": ""}, "companies": cos}


def _c(sym, tags=(), **kw):
    return {"symbol": sym, "name": f"{sym.title()} Corp", "status": "core", "revenue": 100.0, "model_tags": list(tags), "calc": {"in": True}, **kw}


def test_whole_company_figures_of_another_way_of_earning_are_said_on_the_row_and_in_the_layers_notes():
    """Fails before: a card lender that also processes payments, and a software house that also runs platforms, stood in their layers'
    medians with nothing said (the live R53 Payments and Software decks)."""
    lend = _layer("Card issuers and consumer lenders", "lending", "lending", [_c("COF", ["payments"]), _c("SYF"), _c("AXP", ["payments"], company_wide=True)])
    got = deck.consolidated_of(lend)
    assert [(c["symbol"], t) for c, t in got] == [("COF", ["payments"])]          # a company already marked a whole company is said so by that mark
    note = deck.consolidated_note(got, True)
    assert note == ("(consolidated): Cof Corp also earns from fees on the value or number of payments they process. Its figures are the whole "
                    "company's, consolidated (no segment figures are stored), so the layer's medians include those other businesses.")
    assert deck.consolidated_layers([lend]) == [("Card issuers and consumer lenders", 1)]
    assert deck.consolidated_of(_layer("L", "lending", "lending", [_c("X", ["lending"])])) == []          # its own way of earning: nothing
    soft = _layer("Enterprise software", "software", "software", [_c("MSFT")])
    pay = _layer("Merchant acquiring and processing", "payments", "payments", [_c("FI")])
    note2 = deck.profiles_note([{"layer": x["layer"]} for x in (lend, soft, pay)], {x["layer"]: x for x in (lend, soft, pay)})
    assert note2.startswith("These layers earn in 3 different ways: interest on loans they make; licences and subscriptions for software they own; "
                            "fees on the value or number of payments they process.")
    assert "never ranked against each other: a ranking is made only among layers of one way of earning" in note2
    assert deck.profiles_note([{"layer": "Enterprise software"}], {"Enterprise software": soft}) == ""


# ---------- 4. the membership check moves on ----------
def _map(n):
    return {"value_chain": [{"layer": "Drug makers", "official": True, "basis": "industry",
                             "companies": [{"ticker": f"C{i:03d}", "name": f"Co {i}", "base": True, "basis": "industry", "cap": 1000.0 - i, "what": ""}
                                           for i in range(n)]}]}


def test_the_membership_check_moves_on_through_the_companies_not_checked_yet_a_bounded_step_each_time():
    """Fails before: the companies checked were always the same window (every company the AI named, then the largest by market value), so a
    theme of 821 showed the same 721 not checked yet after every check."""
    m = _map(250)
    about = {"C100": "Co 100 makes drugs for diabetes."}.get
    first = D.membership_round(m, {f"C{i:03d}" for i in range(100)}, D._stems("drug makers pharmaceuticals"), about, step=60)
    assert sorted(first) == [f"C{i:03d}" for i in range(100, 160)]          # the next 60 by market value
    assert first["C100"] == "description_verified" and first["C101"] == "industry_code_supported"
    second = D.membership_round(m, {f"C{i:03d}" for i in range(100)} | set(first), set(), about, step=60)
    assert sorted(second) == [f"C{i:03d}" for i in range(160, 220)]


def test_each_stored_read_keeps_what_was_checked_and_the_checked_share_after_it():
    m = _map(250)
    window = {f"C{i:03d}": "industry_code_supported" for i in range(100)}
    dive = {"evidence": window, "coverage": {"placed": 250}}
    one = TR.membership_check("Drug makers", m, m, dive, None, lambda s: None, date(2026, 11, 7))
    assert (one["checked"], one["total"], one["step"]) == (160, 250, 60) and one["history"] == [["2026-11-07", 160, 250]]
    snap = TC.snapshot({**dive, "membership_check": one, "layers": [{"layer": "Drug makers", "companies": [{"symbol": "C000", "name": "Co 0"}]}]}, ["C000"])
    assert len(snap["ev"]) == 60 and set(snap["ev"].values()) == {"i"} and snap["ev_hist"] == [["2026-11-07", 160, 250]]
    stored = TC.apply({}, snap)["snap"]
    two = TR.membership_check("Drug makers", m, m, dive, stored, lambda s: None, date(2026, 11, 14))
    assert (two["checked"], two["step"]) == (220, 60) and two["history"] == [["2026-11-07", 160, 250], ["2026-11-14", 220, 250]]
    # the deck says the progress, and the tally adds up to the theme's companies
    v = {"membership": {"placed": 100, "confirmed": 100, "not_confirmed": 0}, "membership_evidence": {"industry_code_supported": 100}, "membership_check": two}
    row = deck.progress_row(v, {"total": 250})
    assert row[0] == "Membership checked" and row[1] == "220 of 250 (88%)"
    assert "30 not checked yet, the next 60 by market value checked each time the theme's figures are stored" in row[2]
    assert row[2].endswith("Checked share after each stored version: 64% (07 Nov 2026) → 88% (14 Nov 2026).")
    t = deck.evidence_tally(v, 250)
    assert t["checked"] + t["membership_unverified"] == 250 and t["industry_code_supported"] == 220


# ---------- the public page and the deck gate ----------
def test_the_public_page_says_each_companys_evidence_state_from_the_stored_dive(monkeypatch):
    dive = {"evidence": {"A": "description_verified", "B": "industry_code_supported"}, "membership_check": {"outside": {"C": "industry_code_supported"}}}
    of = public_themes._evidence(dive)
    assert (of("A"), of("C"), of("D")) == ("description_verified", "industry_code_supported", "membership_unverified")
    assert public_themes._evidence({}) is None
    assert "confirm the work its layer names; a company of the theme's official industries is shown on that classification" in public_themes.METHOD
    payload = {"value_chain": [{"layer": "Ships", "companies": [{"ticker": "A", "name": "A Ltd", "verified": True, "what": "builds ships"},
                                                                {"ticker": "B", "name": "B Ltd", "base": True, "basis": "industry", "verified": False},
                                                                {"ticker": "D", "name": "D Ltd", "base": True, "basis": "industry", "verified": False}]}]}
    monkeypatch.setattr(public_themes, "_dive", lambda r, n, p: dive)
    monkeypatch.setattr(public_themes, "_index_caps", lambda r: {})
    monkeypatch.setattr(public_themes.stock_pages, "companies", lambda r: set())
    v = public_themes.view({"region": "IN", "name": "Ships", "label": "Ships", "slug": "ships", "at": None}, payload)
    assert v["evidence"] == {"description_verified": 1, "industry_code_supported": 1, "list_supported": 0, "membership_unverified": 1}
    page = public_themes.render(v)
    assert "Membership: 1 confirmed by their own description, 1 on their official industry only, 1 not checked yet." in page
    assert "B · official industry only" in page and "D · not checked yet" in page and "3 companies in 1 layer" in page


def test_a_coverage_table_continued_on_the_next_page_is_checked_as_one_table():
    """Fails before: the continued page alone lacked "Companies, by count", and the gate called the coverage unreconciled."""
    rows = [["Screening", "10 considered", "x"], ["Companies, by count", "8 of 10", "y"]]
    more = [["Each figure", "", "EBITDA margin 8"]]
    assert deck.coverage_table_flags(rows + more, {"members_with_figures": 8}, {"total": 10}) == []
    one, two = deck.Slide("Coverage", "x"), deck.Slide("Coverage, continued", "x")
    one.add("table", (0, 0, 1, 1), head=deck.COVERAGE_HEAD, rows=rows)
    two.add("table", (0, 0, 1, 1), head=deck.COVERAGE_HEAD, rows=more)
    v = {"members_with_figures": 8, "placements": {"total": 10}, "members": [], "with_figures": 8}
    got = deck.publication_gate([one, two], v)
    assert not [x for x in got["dropped"] if x.get("why") == "coverage does not reconcile"], got["dropped"]


def test_deck_check_finds_evidence_state_contradictions_and_population_mismatches():
    # the live R53 Medical devices deck's own words (pdftotext of scratchpad/lanes11/r53-decks), its two columns interleaved
    meddev = ("Data confidence\n                               222 companies (217 in the exchange's industry list, 5 added by the AI); 100 checked\n"
              "                                                                       Only confirmed companies count in a median\n"
              " Universe                      (the map's own picks, then the largest by market value): 100 confirmed by their own\n"
              "                                                                       or total.\n"
              "                               description, 0 not; 122 not checked yet.\n"
              " Membership                    18 companies with figures have no description in their own words yet: SS Innovations\n\f"
              "Coverage\n Companies, by count           76 of 222              companies: confirmed, with figures, of every company the deck lists\n"
              "                                                      companies with figures: Implantable devices 13 of 13 · Surgical robotics systems 25 of 25 · Orthopedic and surgical device\n"
              " Each layer                                           makers 14 of 14 · Home and wearable monitoring devices 12 of 12 · High-volume disposables and supplies 9 of 9 · Diagnostic\n"
              "                                                      and genetic testing labs 16 of 16 · Hospital and care facility operators 8 of 8 · Other medical device companies 3 of 3\n"
              "StratLab · Medical devices · Theme deep dive · 14 Nov 2026\n")
    got = DC.check_text(meddev)["counts"]
    assert got["evidence state"] == 1 and got["population mismatch"] == 1
    hosp = "Universe 98 companies; 98 confirmed by their own description, 0 not yet.\nMembership 43 companies with figures have no description in their own words yet: A.\n"
    assert DC.check_text(hosp)["counts"]["evidence state"] == 1
    fixed = ("Universe 222 companies; 100 checked (the map's own picks, then the largest by market value): 82 confirmed by their own description, 18 kept on "
             "their official industry only, 0 whose own words describe other work; 122 not checked yet.\n"
             "Membership 18 companies with figures have no description in their own words yet: A.\n\f"
             "Coverage\nCompanies, by count 76 of 222 companies: confirmed, with figures; the theme's core members only, the 24 adjacent participants with figures apart\n"
             "Each layer 76 core members + 24 adjacent participants = 100 with figures (adjacent layers: Labs, Hospitals); companies with figures: "
             "Implants 60 of 60 · Tools 16 of 16 · Labs 16 of 16 · Hospitals 8 of 8\n")
    got2 = DC.check_text(fixed)["counts"]
    assert got2["evidence state"] == 0 and got2["population mismatch"] == 0
    # more companies without words than the deck keeps on their official industry
    worse = fixed.replace("18 kept on", "10 kept on").replace("82 confirmed", "90 confirmed")
    assert DC.check_text(worse)["counts"]["evidence state"] == 2          # 90 + 18 above the 100 checked, and 18 without words above the 10 kept


def test_the_description_reads_move_on_past_the_largest_companies_once_those_are_described(monkeypatch):
    """Fails before: the candidates were cut to the largest PLACE_MAX (120) before the described ones were passed over, so once those had
    their words no company past them was read again (Biotech's 564 "not checked yet (no description of their own is kept)")."""
    out = {"value_chain": [{"layer": "Drug developers", "companies": [{"ticker": "AI1"}]},
                           {"layer": "Drug makers", "official": True, "basis": "industry",
                            "companies": [{"ticker": f"C{i:03d}", "cap": 1000.0 - i} for i in range(300)]}]}
    described = {f"C{i:03d}" for i in range(150)}
    monkeypatch.setattr(TR, "_has_description", lambda region, s: s in described)
    asked = []
    monkeypatch.setattr(TR, "evidence_reader", lambda region, names: (lambda syms: asked.extend(syms) or [{}]))
    got = TR.describe_unplaced("US", out, {}, None)
    assert got == [f"C{i:03d}" for i in range(150, 150 + TR.PLACE_READS)] and asked == got
