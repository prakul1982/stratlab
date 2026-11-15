"""y57 (Release 57, the full audit of the 24 live R56 decks): counts and labels that contradict across pages (RC8), unusual values and headline
ranges (RC9), the sub-theme picker (RC11), presentation gaps deck_check missed (RC13), change-log and statement hygiene (RC14), and deck_check
rules that catch every P0 of the audit a text rule can. The deck_check tests read pages of the live R56 deck texts
(tests/fixtures/decks_r56/pages.json, pdftotext -layout output as the audit read it): each rule fails the R56 page and passes the page as the
fixed engine words it. Synthetic themes for the engine; no company or theme name in app code."""
import copy
import importlib.util
import json
import os
import pathlib
import re
import shutil
from datetime import date

from app import deck
from app.intel import theme_data as D
from tests.test_r17_fixes import NOW, deck_of, theme_a

PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts", "deck_check.py")
spec = importlib.util.spec_from_file_location("deck_check_y57", PATH)
DC = importlib.util.module_from_spec(spec)
spec.loader.exec_module(DC)

PAGES = json.loads((pathlib.Path(__file__).parent / "fixtures" / "decks_r56" / "pages.json").read_text(encoding="utf-8"))


def r56(deck_key: str, edit=None) -> list[str]:
    """The kept pages of one R56 deck, in order (`edit`: a function applied to each page's text, the fixed engine's words)."""
    got = [PAGES[deck_key][k] for k in sorted(PAGES[deck_key], key=int)]
    return [edit(p) for p in got] if edit else got


def found(pages: list[str], kind: str) -> list[str]:
    return [f["text"] for f in DC.check_pages(pages)["findings"] if f["kind"] == kind]


# ---------- 1. deck_check: the P0s a text rule can show, on the R56 texts ----------
def test_deck_check_catches_the_audit_p0s_a_text_rule_can_on_the_r56_texts():
    """Fails before: R56's deck_check caught none of the audit's 12 P0s. A text rule shows 8 of them (PAY-1, BIO-1, BIO-2, BIO-23, SW-1,
    IT-1, AUTO-1, TEL-1); SW-2, MD-1, MD-2 and RET-1 need what the companies do or which listed companies exist, which no deck text holds."""
    p0 = {"PAY-1": ("payments", "reason layer", "Card issuers and lenders"),
          "BIO-1": ("biotech", "reason layer", "Commercial specialty biotechs"),
          "BIO-2": ("biotech", "largest left out", "Eli Lilly"),
          "BIO-23": ("biotech", "empty table", "Specialty and clinical-stage biotechs"),
          "SW-1": ("software", "thin layer", "Hotels, travel and consumer services"),
          "IT-1": ("it", "largest left out", "Inventurus Knowledge Solutions"),
          "AUTO-1": ("auto", "largest left out", "Mahindra & Mahindra"),
          "TEL-1": ("telecom", "duplicate member", "HFCL")}
    for pid, (key, kind, said) in p0.items():
        assert any(said in t for t in found(r56(key), kind)), (pid, found(r56(key), kind))
        assert DC.failed(DC.check_pages(r56(key))), pid


def test_a_removal_reason_naming_a_layer_the_deck_does_not_have_fails_and_one_naming_its_layer_passes():
    """PAY-1, BIO-1: "don't show the work of “Card issuers and lenders”" for the deck's “Card issuers and consumer lenders”."""
    assert found(r56("payments"), "reason layer") and found(r56("biotech"), "reason layer")
    fixed = r56("payments", lambda p: p.replace("“Card issuers and lenders”", "“Card issuers and consumer lenders”"))
    assert not found(fixed, "reason layer")


def test_the_theme_s_largest_or_a_layer_s_largest_left_out_for_insufficient_evidence_fails():
    """BIO-2 (Eli Lilly, the theme's largest, "another business"), AUTO-1 (Mahindra & Mahindra, "insufficient evidence"), IT-1 (Inventurus and
    Sagility, worth more than every company in their layer's calculations, "insufficient evidence")."""
    it = found(r56("it"), "largest left out")
    assert any("Inventurus" in t for t in it) and any("Sagility" in t for t in it)
    fixed = r56("auto", lambda p: p.replace("Tata Motors Passenger Vehicles. Left out (1): insufficient evidence (how it earns read only weakly):",
                                            "Tata Motors Passenger Vehicles, Mahindra & Mahindra. Left out (0):"))
    assert not any("Mahindra" in t for t in found(fixed, "largest left out"))


def test_one_company_in_and_left_out_of_a_layer_s_calculations_fails():
    """TEL-1: "In the layer's calculations (6 of 9): Sterlite Technologies, HFCL and 4 more. Left out (3): no figure stored: HFCL, Sterlite
    Technologies and 1 more"."""
    got = found(r56("telecom"), "duplicate member")
    assert sorted(t.split(":")[0] for t in got) == ["HFCL", "Sterlite Technologies"]
    fixed = r56("telecom", lambda p: p.replace("no figure stored: HFCL, Sterlite Technologies and 1 more", "no figure stored: Tamilnadu Telecommunication"))
    assert not found(fixed, "duplicate member")
    rows = ["X · APPENDIX\nEvery company's figures\n2 companies with figures, one row each\n Company      Layer     Market value   Revenue\n"
            " HFCL Ltd           Fibre     ₹31,521 cr     ₹4,949 cr\n HFCL Limited       Fibre     ₹31,500 cr     ₹4,900 cr\n"]
    assert found(rows, "duplicate member") == ["HFCL Limited and HFCL Ltd: one name but for its legal form, on two rows"]


def test_a_layer_table_with_its_heading_and_no_row_fails():
    """BIO-23: the largest layer's table printed its heading and no company row (R55 and R56); deck_check's empty page and cut text missed it."""
    assert found(r56("biotech"), "empty table") == ["Specialty and clinical-stage biotechs: its table's heading and no company row"]
    row = (" Eli Lilly & Co                     $65.2 bn          45.1%                  31.0%                 40.2%          –          –         Dec 2025\n")
    fixed = r56("biotech", lambda p: p.replace("Year\n\n\n\n\nIn the layer's calculations", "Year\n" + row + "\nIn the layer's calculations"))
    assert not found(fixed, "empty table")


def test_a_layer_added_with_under_three_companies_fails():
    """SW-1: "“Hotels, travel and consumer services” added (1 companies)", Duolingo its only member."""
    assert found(r56("software"), "thin layer") == ["“Hotels, travel and consumer services” added (1 companies)"]
    assert not found(r56("software", lambda p: p.replace("added (1 companies)", "added (4 companies)")), "thin layer")


# ---------- 2. deck_check: counts that contradict (RC8) ----------
def test_layer_counts_header_and_membership_differ_without_stored_in_all():
    """BIO-12: "43 companies" beside "Membership of its 214 companies"."""
    got = found(r56("biotech"), "layer counts")
    assert any("43 companies" in t and "214" in t for t in got)
    fixed = r56("biotech", lambda p: re.sub(r"Membership of its (\d[\d,]*) companies: (.*?) \(figures read for this page's (\d[\d,]*)\)\.",
                                            r"Membership of its \1 companies stored in all (figures read for the header's \3): \2.", p))
    assert not found(fixed, "layer counts")


def test_a_layer_header_that_does_not_start_with_its_companies_fails():
    """FMCG-11: "1 figure is the whole company's (it runs other businesses too) and left out of the medians.; 31 in this group in all"."""
    assert found(r56("fmcg"), "layer header")
    fixed = r56("fmcg", lambda p: p.replace("1 figure is the whole company's (it runs other businesses too) and left out of the medians.; 31",
                                            "11 companies, revenue ₹5,000 cr together; 31"))
    assert not found(fixed, "layer header")


def test_a_pe_count_and_loss_makers_over_the_companies_fail():
    """SW-11: "P/E of 78 of the 100 companies, 29 loss-makers with none"."""
    assert found(r56("software"), "pe partition") == ["P/E of 78 of the 100 companies, 29 loss-makers with none"]
    fixed = r56("software", lambda p: p.replace("29 loss-makers with none", "15 loss-makers with none, 7 with a profit in the latest year and no P/E stored"))
    assert not found(fixed, "pe partition")


def test_a_profitable_row_with_no_pe_under_none_for_a_loss_maker_fails():
    """BIO-13, PAY-11: Gilead (net margin 28.9%), Fiserv (16.4%) with no P/E under "P/E on the last four quarters (none for a loss-maker)"."""
    assert any(t.startswith("Gilead Sciences") for t in found(r56("biotech"), "loss-maker profit"))
    assert len(found(r56("payments"), "loss-maker profit")) == 3
    fixed = r56("payments", lambda p: p.replace("(none for a loss-maker)", "(–: a loss over them, or no four quarters stored)"))
    assert not found(fixed, "loss-maker profit")


def test_two_checked_counts_of_one_total_fail():
    """BIO-11: "membership checked for 313 of the theme's 820" (p.3) against "membership checked 423 of 820" (p.4)."""
    assert found(r56("biotech"), "checked counts") == ["membership checked 423 of 820 (p.2) against 313 of 820 (p.1)"]
    assert not found(r56("biotech", lambda p: p.replace("checked for 313 of the theme's 820", "checked for 423 of the theme's 820")), "checked counts")


def test_the_cover_and_appendix_with_figures_counts_differ_without_core():
    """PAY-9: the cover's "With figures 14" against the appendix's "18 companies with figures"."""
    assert found(r56("payments"), "figures count")
    fixed = r56("payments", lambda p: p.replace("18 companies with figures (18 description-verified, 0 industry-supported), one row each",
                                                "18 companies with figures (18 description-verified, 0 industry-supported): 14 core members and 4 "
                                                "adjacent participants, one row each"))
    assert not found(fixed, "figures count")


def test_none_screened_out_beside_a_removal_on_business_membership_fails():
    """PAY-15: "19 considered, none screened out as another business" beside Capital One "removed 1: ... (business membership: ...)"."""
    assert found(r56("payments"), "none screened")
    fixed = r56("payments", lambda p: p.replace("none screened out as another business: 19 members", "none screened out as another business: 19 members; "
                                                "1 removed by the membership re-check since the previous version, with its reason in the change log"))
    assert not found(fixed, "none screened")


# ---------- 3. deck_check: presentation and hygiene (RC13, RC14) ----------
def test_a_layer_page_under_five_rows_with_no_continuation_fails():
    """BIO-24, SW-18, MD-13, HOS-12: "The largest 1 of 12 by market value"."""
    assert any("The largest 1 of 12" in t for t in found(r56("software"), "few rows"))
    fixed = r56("software", lambda p: re.sub(r"The (largest|first) (\d+) of (\d+)", lambda m: f"The {m.group(1)} {min(5, int(m.group(3)))} of {m.group(3)}", p))
    assert not found(fixed, "few rows")


def test_one_name_said_twice_fails():
    """RET-7: "Leslie's, Inc. is Leslie's, Inc."."""
    assert found(r56("retail"), "same name") == ["Leslie's, Inc. is Leslie's, Inc"]
    fixed = r56("retail", lambda p: p.replace("Leslie's, Inc. is Leslie's, Inc.", "Leslie's, Inc. under two symbols (LESL and LESL.X)"))
    assert not found(fixed, "same name")
    assert found(["A: AppLovin Corp; IonQ, Inc.; IonQ, Inc.; and 5 more."], "same name")


def test_a_change_log_carried_from_an_earlier_day_must_say_so():
    """DEF-7, IT-7: "On 14 Nov 2026, against the version stored before it" in a deck of 15 Nov 2026."""
    assert found(r56("defence"), "carried log") == ["a change log of 14 Nov 2026 in a deck of 15 Nov 2026, not said to be carried"]
    fixed = r56("defence", lambda p: p.replace("On 14 Nov 2026, against", "On 14 Nov 2026, the latest change (no change since), against"))
    assert not found(fixed, "carried log")


def test_the_r56_texts_fail_the_new_rules_where_the_audit_found_the_defect():
    """Every new rule fails on the live R56 text where the audit found its defect, in the decks it named."""
    want = {"layer counts": ("biotech", "software"), "layer header": ("fmcg",), "pe partition": ("software",), "loss-maker profit": ("biotech", "payments"),
            "checked counts": ("biotech",), "figures count": ("payments",), "none screened": ("payments",), "empty table": ("biotech",),
            "few rows": ("software", "biotech"), "same name": ("retail",), "carried log": ("defence",), "reason layer": ("payments", "biotech"),
            "thin layer": ("software",), "largest left out": ("biotech", "auto", "it"), "duplicate member": ("telecom",)}
    assert set(want) == set(DC.FAIL[-15:])
    for kind, keys in want.items():
        for key in keys:
            assert found(r56(key), kind), (kind, key)


# ---------- 4. the engine: the fixed words ----------
def _stress(heavy: bool = False):
    """theme_a with its 14-company layer given long names, a long description and a mark on every row (the R56 layer pages that showed 1 to
    4 rows); `heavy`: every company left out, with its reason (a two-line roll)."""
    region, m, f = theme_a()
    m = copy.deepcopy(m)
    conv = m["value_chain"][1]
    conv["description"] = ("These companies convert plastic film, paper and foil into flexible pouches, folding cartons, labels and sleeves for food, "
                           "drink, home care and pharmaceutical brands, earning from long supply contracts and from short runs of printed packs. "
                           "A few larger groups in this layer also run film lines, ink plants and machine shops, and sell to export customers.")
    for c in conv["companies"]:
        c["name"] = c["name"].replace(" Ltd", " Flexible Packaging and Specialty Converting Industries Limited")
    v, _ = deck_of(region, m, f)
    v = copy.deepcopy(v)
    lay = next(b for b in v["layers"] if b["layer"] == "Converters")
    for c in lay["companies"]:
        c["by_words"] = True
    if heavy:
        for c in lay["companies"][:9]:
            c["by_words"] = False
            c["calc"] = {"in": False, "why": "way of earning not shown", "kind": "insufficient evidence",
                         "label": "insufficient evidence (its words don't state how it earns)", "detail": "its own words don't state how it earns"}
        for i, c in enumerate(lay["companies"][9:]):
            c["calc"] = {"in": False, "why": "other business", "kind": "another business", "label": "another business than the layer's",
                         "detail": f"its own words describe making {i} other goods for other industries"}
        lay["description"] = lay["description"] + " " + lay["description"]
    return v


def _drawn(s) -> int:
    tb = next(b for b in s.blocks if b["kind"] == "table")
    x, y, w, h = tb["box"]
    lay = deck.table_layout(tb, w, h)
    return sum(1 for r in lay["rows"] if not str(r[0] if not isinstance(r[0], dict) else r[0].get("text")).startswith(("Median", "Range", "Together")))


def test_a_crowded_layer_page_shows_five_rows_and_sends_its_notes_to_a_notes_page():
    """Fails before: the stressed layer's page showed "The largest 4 of 14" (3 of 14 when every company is left out), its notes under them."""
    for heavy in (False, True):
        slides = deck.theme_plan(_stress(heavy), now=NOW)[0]
        i = next(k for k, s in enumerate(slides) if s.title == "Layer 2 · Converters")
        page, nxt = slides[i], slides[i + 1]
        assert _drawn(page) >= 5, (heavy, _drawn(page))
        assert nxt.title == "Layer 2 · Converters (notes)"
        said = " ".join(p for b in nxt.blocks if b["kind"] == "text" for p in b["paras"])
        assert "Membership of its 14 companies" in said
        assert ("In the layer's calculations (0 of 14)" in said) == heavy
        assert not any(p.startswith("Membership of its") for b in page.blocks if b["kind"] == "text" for p in b["paras"])
        # one record behind every count: the notes page's roll is of the same layer (lane m1's check; the heavy case's records are set by hand)
        assert heavy or not deck.layer_count_flags(slides)
        if shutil.which("pdftotext"):
            path = os.path.join(os.environ.get("TMPDIR", "/tmp"), f"y57-{os.getpid()}-{int(heavy)}.pdf")
            with open(path, "wb") as fh:
                fh.write(deck._render(slides, "foot", "t", pdf=True))
            try:
                r = DC.check_pages(DC.pages_of(path))
            finally:
                os.remove(path)
            assert not [f for f in r["findings"] if f["kind"] in DC.FAIL[-15:]], [f for f in r["findings"] if f["kind"] in DC.FAIL[-15:]]


def test_a_layer_header_starts_with_its_companies_when_it_holds_a_whole_company_figure():
    """Fails before (FMCG-11): the layer's line replaced the header, "1 figure is the whole company's ... medians.; 31 in this group in all"."""
    v = _stress()
    v["layers"] = [{**b, "line": "1 figure is the whole company's (it runs other businesses too) and left out of the medians."} if b["layer"] == "Converters"
                   else b for b in v["layers"]]
    slides = deck.theme_plan(v, now=NOW)[0]
    page = next(s for s in slides if s.title == "Layer 2 · Converters")
    assert re.match(r"14 companies, revenue ", page.subtitle) and page.subtitle.endswith("left out of the medians.") and ".;" not in page.subtitle


def test_a_membership_count_other_than_the_header_s_says_stored_in_all():
    """Fails before (BIO-12): "Membership of its 214 companies ... (figures read for this page's 43)" under "43 companies"."""
    v = copy.deepcopy(_stress())
    v["members"] = list(v["members"]) + [{"symbol": f"XTRA{i}", "name": f"Extra {i} Ltd", "layer": "Converters", "what": None, "cap": 1.0}
                                         for i in range(6)]
    line = deck.layer_evidence(v, next(b for b in v["layers"] if b["layer"] == "Converters"),
                               next(b for b in v["layers"] if b["layer"] == "Converters")["companies"])
    assert line.startswith("Membership of its 20 companies stored in all (figures read for the header's 14): ")
    assert not DC.check_text(f"X · THE VALUE CHAIN\nLayer 2 · Converters\n14 companies, revenue ₹1 cr together\n{line}\n")["counts"]["layer counts"]


def test_the_pe_partition_counts_a_profitable_company_with_no_pe_apart_from_loss_makers():
    """Fails before (SW-11, BIO-13): losses counted every annual loss, with a P/E or not, and a profitable company with no P/E read as a
    loss-maker: 78 + 29 of 100."""
    rows = [{"symbol": f"S{i}", "pe": pe, "profit": p, "ev_ebitda": None, "cap": 100.0}
            for i, (pe, p) in enumerate(((20.0, 10.0), (30.0, -5.0), (None, -3.0), (None, 8.0), (None, None)))]
    val = D.valuation_section(rows, [])
    assert (val["pe"]["n"], val["losses"], val["no_pe_profit"], val["n"]) == (2, 1, 2, 5)
    assert val["pe"]["n"] + val["losses"] + val["no_pe_profit"] == val["n"]


def test_the_appendix_says_what_no_pe_means_and_a_headline_range_is_its_10th_to_90th_percentile():
    """Fails before: "P/E on the last four quarters (none for a loss-maker)" over profitable rows; IT's headline "P/E 1.8x to 886.6x"."""
    v = _stress()
    slides = deck.theme_plan(v, now=NOW)[0]
    apx = next(s for s in slides if s.title.startswith("Every company's figures"))
    note = " ".join(p for b in apx.blocks if b["kind"] == "text" for p in b["paras"])
    assert "(–: a loss over them, or no four quarters stored)" in note and "none for a loss-maker" not in note
    st = D.stat_mid([1.8] + [20.0 + i for i in range(18)] + [886.6])
    assert (st["min"], st["max"]) == (1.8, 886.6) and 20.0 < st["p10"] < st["p90"] < 40.0
    line = deck.descriptive_line({"pe": st, "peers": {"pe": {"n": 0}}})
    assert "10th to 90th percentile" in line and "886.6x" not in line and "1.8x" not in line


def test_the_partial_map_counts_the_deck_s_one_tally():
    """Fails before (BIO-11): the partial map counted the unread companies placed in "Other" as unchecked too, 313 of 820 against the
    tally's 423."""
    v = {"members": [{"symbol": f"S{i}", "unread": i < 60} for i in range(100)],
         "membership_evidence": {"description_verified": 30, "industry_code_supported": 15, "membership_unverified": 55}}
    said = deck.partial_map(v, {"total": 100})
    assert said.startswith("A partial map: membership checked for 45 of the theme's 100 companies (45%); 55 are not checked yet")


def test_the_cover_and_appendix_say_core_members_with_adjacent_participants_apart():
    """Fails before (PAY-9): the cover's "With figures 14" beside the appendix's "18 companies with figures", 4 adjacent with figures."""
    v = copy.deepcopy(_stress())
    adj = next(b for b in v["layers"] if b["layer"] == "Film")
    v["adjacent"] = [{"symbol": c["symbol"], "name": c["name"], "layer": "Film", "kind": "film makers"} for c in adj["companies"]]
    adj["adjacent"] = {"kind": "film making", "theme": "packaging"}
    slides = deck.theme_plan(v, now=NOW)[0]
    cover = {it[0]: it for b in slides[0].blocks if b["kind"] == "stats" for it in b["items"]}
    assert "Core with figures" in cover and "With figures" not in cover
    apx = next(s for s in slides if s.title.startswith("Every company's figures"))
    assert re.search(r"companies with figures \([^)]*\): \d+ core members and 4 adjacent participants, one row each", apx.subtitle), apx.subtitle


def test_the_screening_row_says_a_removal_on_business_membership():
    """Fails before (PAY-15): "none screened out as another business" beside a removal on business membership in the change log."""
    v = copy.deepcopy(_stress())
    v["changes"] = {"entries": [{"d": "2026-11-15", "cause": "rules", "removed": [{"symbol": "GONE", "name": "Gone Ltd",
                                                                                   "why": "business membership: its own words were checked"}]}]}
    row = deck.screening_row(v, deck.coverage(v))
    assert "1 removed by the membership re-check since the previous version, with its reason in the change log" in row[2]


def test_a_carried_change_log_says_no_change_since_and_layer_counts_say_one_company():
    """Fails before (DEF-7, IT-7): "On 14 Nov 2026, against the version stored before it" in a deck of 15 Nov; (SW-1) "added (1 companies)"."""
    v = {"changes": {"entries": [{"d": "2026-11-14", "cause": "rules", "layers": [{"kind": "added", "to": ["New layer"], "n": 1},
                                                                                   {"kind": "removed", "from": ["Old layer"], "n": 1}]}]}}
    row = deck.cohort_row(v, date(2026, 11, 15))
    assert row[2].startswith("On 14 Nov 2026, the latest change (no change since), against the version stored before it")
    assert "“New layer” added (1 company)" in row[2] and "“Old layer” removed (1 company)" in row[2]
    assert not deck.cohort_row(v, date(2026, 11, 14))[2].count("no change since")
    assert not DC.check_text(f"Since the previous version {row[2]}\nX · Theme deep dive · 15 Nov 2026\n")["counts"]["carried log"]


def test_one_name_under_two_symbols_and_a_company_with_two_verified_figures_are_said_once():
    """Fails before: RET-7 "Leslie's, Inc. is Leslie's, Inc."; SW-14 "AppLovin Corp; IonQ, Inc.; IonQ, Inc."."""
    v = {"duplicates": [{"symbol": "AAA", "name": "Same Name, Inc.", "kept": "AAA.B", "kept_name": "Same Name, Inc."}], "checks": {}, "layers": [],
         "members": [], "placements": {"total": 2}}
    rows = deck.confidence_rows(v, {"total": 2, "n": 2}, date(2026, 11, 15))
    said = next(r[1] for r in rows if r[0] == "Same company twice")
    assert "Same Name, Inc. under two symbols (AAA and AAA.B)" in said and " is Same Name" not in said
    vf = [{"name": "Two Figures, Inc.", "key": "net", "state": "verified"}, {"name": "Two Figures, Inc.", "key": "ebitda", "state": "verified"},
          {"name": "One Figure Corp", "key": "net", "state": "verified"}]
    row = deck.verified_row(vf, short=True)
    assert "Two Figures, Inc. (2 figures); One Figure Corp" in row[1] and "Two Figures, Inc.; Two Figures, Inc." not in row[1]


def test_a_verified_net_margin_above_ebitda_is_a_gain_outside_the_business_out_of_the_net_median():
    """Fails before (AUTO-3, CHEM-6, CG-7: Tata Motors PV's 151.3% net on 4.5% EBITDA, covered by a demerger gain the filed lines show, kept
    unmarked in medians while a US deck's like case is marked † and left out)."""
    r = {"net": 151.3, "ebitda": 4.5, "filed": {"sales": 1000.0, "profit": 1513.0, "opm": 4.5, "other_income": 1600.0, "unit": "₹ crore"}}
    D.verify_net(r)
    assert r["verify"]["net"]["state"] == D.VERIFIED and r["gain"] and not r["one_off"]
    assert D.in_median(r, "net") is None and deck.co_cell(r, "net", str) == "151.3%‡"
    plain = {"net": 9.0, "ebitda": 15.0, "filed": {"sales": 1000.0, "profit": 90.0, "opm": 15.0, "unit": "₹ crore"}}
    D.verify_net(plain)
    assert not plain.get("gain") and D.in_median(plain, "net") == 9.0


def test_a_fiscal_quarter_within_two_months_is_the_latest_never_earlier():
    """Fails before (SW-16, CYB-6): Oracle, Salesforce, Palo Alto and 33 more "still on an earlier quarter", on fiscal quarters ending in
    August or October."""
    rows = [{"symbol": f"S{i}", "name": f"S{i}", "quarter": {"of": "Sep 2026 vs Sep 2025", "sales": 5.0, "profit": 1.0}} for i in range(6)]
    rows += [{"symbol": "AUG", "name": "Aug Co", "quarter": {"of": "Aug 2026 vs Aug 2025", "sales": 3.0, "profit": 1.0}},
             {"symbol": "OCT", "name": "Oct Co", "quarter": {"of": "Oct 2026 vs Oct 2025", "sales": 4.0, "profit": 1.0}},
             {"symbol": "JUN", "name": "Jun Co", "quarter": {"of": "Jun 2026 vs Jun 2025", "sales": 2.0, "profit": 1.0}}]
    q = D.quarter_section(rows)
    assert q["quarter"] == "Sep 2026" and q["fiscal"] == 2 and len(q["companies"]) == 8 and [x["symbol"] for x in q["earlier"]] == ["JUN"]


def test_a_sub_theme_lists_only_companies_with_words_its_layer_s_members_and_those_its_text_names():
    """Fails before (PAY-14, BIO-20, HOS-11): a sub-theme company with no description under the footnote that says each has one; Viking
    alone in an obesity sub-theme whose text names two members; 1 of a 26-company layer."""
    layers = [{"layer": "Regional and mid-sized hospital operators", "companies": [{"ticker": f"H{i}", "name": f"Hosp {i} Ltd", "what": "runs hospitals"}
                                                                                    for i in range(5)]},
              {"layer": "Large drug makers", "companies": [{"ticker": "LLY", "name": "Eli Lilly & Co", "what": "makes medicines"},
                                                           {"ticker": "NVO", "name": "Novo Nordisk A/S", "what": "makes medicines"}]},
              {"layer": "Clinical-stage developers", "companies": [{"ticker": "VKTX", "name": "Viking Therapeutics", "what": "develops drugs"},
                                                                   {"ticker": "WQ", "name": "Wordless Corp", "what": ""}]}]
    sub = {"name": "Regional and mid-sized hospitals", "detail": "Hospital chains outside the metros.", "companies": [{"ticker": "H0", "name": "Hosp 0 Ltd",
                                                                                                                    "what": "runs hospitals"}]}
    assert {c["ticker"] for c in D.sub_picked(sub, layers)} == {f"H{i}" for i in range(5)}
    obesity = {"name": "Metabolic and obesity drugs", "detail": "GLP-1 drugs from Lilly and Novo Nordisk lead the market.",
               "companies": [{"ticker": "VKTX", "name": "Viking Therapeutics", "what": "develops drugs"}, {"ticker": "WQ", "name": "Wordless Corp", "what": ""}]}
    assert {c["ticker"] for c in D.sub_picked(obesity, layers)} == {"VKTX", "LLY", "NVO"}


def test_no_listed_company_is_said_only_after_no_member_s_words_name_the_layer():
    """Fails before (SW-6): "No listed company is shown for ... Payment networks and processors" while a member in "Other" processes payments."""
    v = {"members": [{"symbol": "BLK", "name": "Square Block, Inc.", "layer": "Other software companies", "cap": 50.0,
                      "what": "Operates payment networks and processes card payments for sellers"},
                     {"symbol": "ZZZ", "name": "Zed Corp", "layer": "Data", "cap": 5.0, "what": "Sells database software"}]}
    assert deck.words_naming("Payment networks and processors", v) == [("Square Block, Inc.", "Other software companies")]
    assert deck.words_naming("Small finance banks", v) == []


def test_a_claim_naming_members_is_tagged_to_their_layers():
    """Fails before (PAY-16): "Software platforms such as Toast and Block bundle payments" tagged to two layers neither company is in."""
    members = [{"name": "Toast, Inc.", "layer": "Software products and subscriptions"}, {"name": "Block, Inc.", "layer": "Merchant acquiring and processing"},
               {"name": "PayPal Holdings, Inc.", "layer": "Payment platforms and crypto exchanges"}]
    layers = ["Payment platforms and crypto exchanges", "Cross-border and B2B payments", "Software products and subscriptions", "Merchant acquiring and processing"]
    text = "Software platforms such as Toast and Block bundle payments, lending and payroll for merchants."
    assert deck.claim_layers(text, layers, members) == ["Software products and subscriptions", "Merchant acquiring and processing"]


# ---------- 5. second wave: CEM-11 and TEL-5 ----------
def test_a_line_chart_s_year_labels_never_run_into_each_other():
    """Fails before (CEM-11): a small layer page's "Margins by year" chart printed "Mar 2022Mar 2023Mar 2024..." (every label, whole, in
    slots narrower than the labels)."""
    cats = ["Mar 2022", "Mar 2023", "Mar 2024", "Mar 2025", "Mar 2026"]
    for w in (1.0, 1.5, 2.2, 2.6, 3.0, 4.5, 8.0):
        got = deck.axis_labels(cats, w, 10)
        at = [i for i, c in enumerate(got) if c]
        assert at[0] == 0 and at[-1] == len(cats) - 1 and len(got) == len(cats), (w, got)
        slot = w / len(cats)
        for a, b in zip(at, at[1:]):            # two neighbouring shown labels: each half of each fits the room between their centres
            assert (deck._width(got[a], 10) + deck._width(got[b], 10)) / 2 + deck.AXIS_GAP <= (b - a) * slot + 1e-9, (w, got)
    assert deck.axis_labels(cats, 8.0, 10) == cats                             # room for every label whole: each as it is
    assert deck.axis_labels(cats, 2.6, 10) == ["Mar 22", "Mar 23", "Mar 24", "Mar 25", "Mar 26"]          # short before any is left off
    if shutil.which("pdftotext"):
        s = deck.Slide("Layer 1 · Small", "3 companies, revenue ₹1 cr together", eyebrow="X · The value chain")
        s.add("lines", (deck.M + 8.0, deck.TOP, 3.3, 3.0), title="Margins by year, the same 3 companies", cats=cats,
              series=[("EBITDA margin", [10.0, 11.0, 12.0, 13.0, 14.0], deck.BLUE), ("Net margin", [5.0, 6.0, 5.5, 7.0, 8.0], deck.ORANGE)], fmt="pct")
        path = os.path.join(os.environ.get("TMPDIR", "/tmp"), f"y57-axis-{os.getpid()}.pdf")
        with open(path, "wb") as fh:
            fh.write(deck._render([deck.Slide("X", "y", dark=True), s], "foot", "t", pdf=True))
        try:
            text = "\f".join(DC.pages_of(path))
        finally:
            os.remove(path)
        assert not re.search(r"(?:Mar ?\d{2,4}){2}", text.replace(" ", "")) or not re.search(r"\d{2}Mar", text), text[-400:]
        assert not re.search(r"20\d\dMar", text)


def test_a_company_under_insolvency_or_with_a_loss_over_revenue_on_negative_equity_is_out_of_every_median_with_why():
    """Fails before (TEL-5): Reliance Communications, in insolvency, "net margin −3543.0%" in a 3-company layer median, its range
    "−3543.0% to 5.8%"."""
    now = {"what": "The company has been under Corporate Insolvency Resolution Process since June 2023, with the Committee of Creditors in charge."}
    assert D.distress_of(now) == "under an insolvency or resolution process, by its own words"
    for past in ("It underwent CIRP and has since emerged under new management.", "In Feb 2023 the NCLT approved the resolution plan; it was under "
                 "CIRP before.", "Following insolvency proceedings, it was acquired in 2022.", "It shut down in 2009 after filing for bankruptcy."):
        assert D.distress_of({"what": past}) == "", past
    shell = {"what": "Provides telecom services.", "neg_equity": True, "net": -3543.0}
    assert D.distress_of(shell) == "negative equity and a net loss larger than its revenue"
    assert D.distress_of({**shell, "net": -40.0}) == "" and D.distress_of({**shell, "neg_equity": False}) == ""      # a loss-maker alone is no shell
    # in the dive: out of the layer's medians and range, and the theme's, and said with why
    region, m, f = theme_a()
    m = copy.deepcopy(m)
    m["value_chain"][1]["companies"][3]["what"] = now["what"]
    dive = D.build(region, m["sector"], m, D.Sources(date(2026, 10, 5), facts=f.get))
    conv = next(b for b in dive["layers"] if b["layer"] == "Converters")
    hit = next(r for r in conv["companies"] if r.get("distress"))
    assert hit["symbol"] == "CONV03" and D.in_median(hit, "net") is None and D.in_median(hit, "ebitda") is None
    assert conv["stats"]["net"]["n"] == conv["n"] - 1 and conv["distress"] == [hit["name"]]
    assert [x["symbol"] for x in dive["distress"]] == ["CONV03"]
    from app.intel import theme_routes as T
    v = T.deck_view(region, m, dive)
    slides = deck.theme_plan(v, now=NOW)[0]
    rows = {r[0]: r for s in slides for b in s.blocks if b["kind"] == "table" for r in b.get("rows") or [] if not isinstance(r, dict)}
    assert rows["In distress"][1] == f"1 company in distress: {deck.clean_name(hit['name'])} (under an insolvency or resolution process, by its own words)."
    said = " ".join(t for s in slides if s.title.startswith("Layer 2 · Converters") for b in s.blocks if b["kind"] == "text" for t in b["paras"])
    page = next(s for s in slides if s.title == "Layer 2 · Converters")
    names = [str(r[0]) for b in page.blocks if b["kind"] == "table" for r in b["rows"] if not isinstance(r, dict)]
    if any("(in distress)" in n for n in names):
        assert "(in distress): " in said and "left out of every median and range" in said
    else:
        assert "margins and returns apart (under an insolvency or resolution process" in said
