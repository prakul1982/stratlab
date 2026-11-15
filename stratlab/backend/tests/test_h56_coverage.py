"""h56 (Release 56, the owner's review of the live R55 decks): the membership check's history is kept from the one evidence tally the deck states
its counts from (Payments said "19 of 20 (95%)" beside "Checked share after each stored version: 100% → 100%"), its last point the deck's own
figure, a point without the tally's counts left out; the membership check and the description reads move faster for a large theme, still
bounded (Biotech 219 of 820 checked, Software 220 of 588); a company kept on its industry label is read and checked again by its own words
where a source has them (FMCG: 98 description-verified, 111 on labels); the description-verified share is said first; deck_check fails a
history that doesn't end on the row's share; the nightly customer and supplier map keeps an order win whose sentence cites the listing
regulations or a value "excluding GST". Synthetic data only; no company or theme name in app code."""
import copy
import importlib.util
import os
import shutil
from datetime import date

from app import deck
from app import supply_extract as X
from app.intel import theme_changes as TC
from app.intel import theme_data as D
from app.intel import theme_routes as TR
from tests.test_export import texts
from tests.test_r17_fixes import deck_of, theme_a

PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts", "deck_check.py")
spec = importlib.util.spec_from_file_location("deck_check_h56", PATH)
DC = importlib.util.module_from_spec(spec)
spec.loader.exec_module(DC)


def _map(n, cap0=10000.0):
    return {"value_chain": [{"layer": "Drug makers", "official": True, "basis": "industry",
                             "companies": [{"ticker": f"C{i:03d}", "name": f"Co {i}", "base": True, "basis": "industry", "cap": cap0 - i, "what": ""}
                                           for i in range(n)]}]}


# ---------- 1. the history from the one tally ----------
def test_the_history_point_is_the_tallys_count_never_the_windows_companies_not_checked():
    """Fails before: the point counted every company of the figures' window, the one whose check gave no answer too (20 of 20), while the
    deck's tally said 19 of 20."""
    m = _map(20)
    window = {f"C{i:03d}": "description_verified" for i in range(19)} | {"C019": "membership_unverified"}
    dive = {"evidence": window, "coverage": {"placed": 20}}
    got = TR.membership_check("Drug makers", m, m, dive, None, lambda s: None, date(2026, 11, 14))
    assert (got["checked"], got["total"]) == (19, 20) and got["history"] == [["2026-11-14", 19, 20, 19]]
    v = {"membership_evidence": D.evidence_counts(window), "membership_check": got}
    t = deck.evidence_tally(v, 20)
    assert (t["checked"], t["total"], t["description_verified"]) == (19, 20, 19)


def test_a_history_point_kept_without_the_tallys_counts_is_left_out_and_the_last_point_is_the_decks_own_figure():
    """Fails before: the live Payments row, "19 of 20 (95%)" beside "Checked share after each stored version: 100% (14 Nov 2026) → 100% (14
    Nov 2026)", the points kept from the window's count."""
    ev = {"description_verified": 19, "membership_unverified": 1}
    old = {"membership_evidence": ev, "membership_check": {"outside": {}, "history": [["2026-11-14", 20, 20], ["2026-11-14", 20, 20]]}}
    row = deck.progress_row(old, {"total": 20})
    assert row[1] == "19 of 20 (95%)" and "after each stored version" not in row[2] and "100% (14 Nov 2026)" not in row[2]
    # points with the tally's counts: the last one is this read's, said with the counts the row states
    new = {"membership_evidence": ev, "membership_check": {"outside": {}, "history": [["2026-11-07", 10, 20, 10], ["2026-11-14", 20, 20, 20]]}}
    row = deck.progress_row(new, {"total": 20})
    assert "Checked share after each stored version: 50% (07 Nov 2026) → 95% (14 Nov 2026)." in row[2]
    assert row[2].startswith("Description-verified 19 of 20 (95%); description-verified share after each stored version: 50% (07 Nov 2026) → "
                             "95% (14 Nov 2026). By state: 19 description-verified, 0 industry-supported, 1 not checked")
    # the snapshot keeps only such points, and the next read carries them on
    snap = TC.snapshot({"membership_check": {"outside": {}, "history": [["2026-11-07", 10, 20], ["2026-11-14", 19, 20, 19]]}, "layers": []}, [])
    assert snap["ev_hist"] == [["2026-11-14", 19, 20, 19]]


# ---------- 2. faster, still bounded ----------
def test_a_large_theme_is_checked_in_about_three_stored_reads_each_bounded():
    """Fails before: 60 a stored read whatever the theme, so Biotech's 601 companies not checked needed ten more reads."""
    assert D.membership_step(0) == D.MEMBERSHIP_STEP == 60 and D.membership_step(240) == 60
    assert D.membership_step(820) == 205 and D.membership_step(588) == 147 and D.membership_step(5000) == D.MEMBERSHIP_STEP_MAX == 300
    m = _map(820)
    window = {f"C{i:03d}": "industry_code_supported" for i in range(219)}
    dive = {"evidence": window, "coverage": {"placed": 820}}
    stored, seen = None, []
    for day in (7, 8, 9):
        looked = []
        mc = TR.membership_check("Drug makers", m, m, dive, stored, lambda s: looked.append(s), date(2026, 11, day))
        # stored lookups only (no AI, no source read): one a company checked, and one a company kept on a label (to check it again)
        assert mc["step"] <= 205 and len(looked) <= mc["step"] + min(D.RECHECK_LOOKS, 820 - 219 - mc["step"])
        seen.append(mc["checked"])
        stored = TC.apply({}, TC.snapshot({**dive, "membership_check": mc, "layers": []}, []))["snap"]
    assert seen == [424, 629, 820]          # the 601 past the window in three stored reads (60 a read before: ten)
    one = TR.membership_check("Drug makers", m, m, dive, None, lambda s: None, date(2026, 11, 7))
    v = {"membership_evidence": D.evidence_counts(window), "membership_check": one, "evidence": window}
    assert "396 not checked; the next 205 by market value checked each time the theme's figures are stored" in deck.progress_row(v, {"total": 820})[2]
    # a company the check reached that is still not checked (no answer, no words of its own) is never said to be among the next
    w2 = {f"C{i:03d}": "description_verified" for i in range(19)} | {"C019": "membership_unverified"}
    v2 = {"membership_evidence": D.evidence_counts(w2), "membership_check": {"outside": {}}, "evidence": w2}
    assert "1 not checked; each checked again once its own words are read" in deck.progress_row(v2, {"total": 20})[2]


def test_a_company_kept_on_its_label_is_checked_again_once_its_own_description_is_stored():
    """Fails before: a company an earlier read kept on its industry label stayed so for good, its own words read later or not."""
    m = _map(5)
    m["value_chain"][0]["description"] = "Makers of drugs and medicines."
    about = {"C003": "Co 3 makes generic drugs and medicines for hospitals."}.get
    before = {"ev": {"C003": "i", "C004": "i"}}
    dive = {"evidence": {f"C{i:03d}": "industry_code_supported" for i in range(3)}, "coverage": {"placed": 5}}
    got = TR.membership_check("Drug makers", m, m, dive, before, about, date(2026, 11, 14))
    assert got["outside"] == {"C003": "description_verified", "C004": "industry_code_supported"} and got["rechecked"] == 1
    assert got["history"][-1] == ["2026-11-14", 5, 5, 1]


def test_the_description_reads_cover_the_companies_kept_on_labels_and_grow_with_those_missing(monkeypatch):
    """Fails before: only companies not placed yet were read, PLACE_READS a check; a placed company with no words of its own stayed on its
    industry label."""
    assert TR.describe_reads(0) == TR.PLACE_READS and TR.describe_reads(300) == 100 and TR.describe_reads(10_000) == TR.PLACE_READS_MAX
    out = {"value_chain": [{"layer": "Drug developers", "companies": [{"ticker": "P0", "cap": 5.0}]},
                           {"layer": "Drug makers", "official": True, "basis": "industry",
                            "companies": [{"ticker": f"U{i:03d}", "cap": 100.0 - i} for i in range(3)]}]}
    kept = {"assign": {"U000": {"layer": "Drug developers", "by": "ai"}}}
    monkeypatch.setattr(TR, "_has_description", lambda region, s: s == "U001")
    asked = []
    monkeypatch.setattr(TR, "evidence_reader", lambda region, names: (lambda syms: asked.extend(syms) or ({}, set())))
    got = TR.describe_unplaced("IN", out, {}, kept)
    assert got == asked == ["U002", "U000", "P0"]          # the one to place first, then those placed with no words, largest first


# ---------- 3. the description-verified share first ----------
def _partial():
    region, m, f = theme_a()
    v, _ = deck_of(region, m, f)
    v = copy.deepcopy(v)
    first = max(v["layers"], key=lambda b: len(b["companies"]))["layer"]
    v["members"] = list(v["members"]) + [{"symbol": f"XTRA{i}", "name": f"Extra {i} Ltd", "layer": first, "official": False, "industry": None,
                                          "what": None, "cap": 10.0 - i, "revenue": None} for i in range(10)]
    v["placements"] = {**(v.get("placements") or {}), "total": 30}
    v["coverage"] = {"informative": 30, "placed": 30, "share": 100, "other": 0, "unread": 0, "other_name": ""}
    v["membership_check"] = {"outside": {"XTRA0": "description_verified", "XTRA1": "industry_code_supported"},
                             "history": [["2026-11-07", 20, 30, 3], ["2026-11-14", 22, 30, 4]]}
    return v


def test_the_coverage_and_the_universe_lead_with_the_description_verified_share():
    """Fails before: "Membership checked 22 of 30 (73%)" the only share, a larger checked count read as more verified."""
    v = _partial()
    slides = deck.theme_plan(v)[0]
    rows = [r for s in slides for b in s.blocks if b["kind"] == "table" for r in b.get("rows") or [] if not isinstance(r, dict)]
    mc = next(r for r in rows if r[0] == "Membership checked")          # (no row added: the coverage table keeps its length)
    assert mc[1] == "22 of 30 (73%)" and mc[2].startswith(
        "Description-verified 4 of 30 (13%); description-verified share after each stored version: 10% (07 Nov 2026) → 13% (14 Nov 2026). "
        "By state: 4 description-verified, 16 industry-supported, 2 own words describe other work, 8 not checked")
    uni = next(r for r in rows if r[0] == "Universe")
    assert "; description-verified 4 of 30 (13%); membership checked 22 of 30" in uni[1]
    assert "description-verified 4 of 30 (13%)" in texts(slides)
    if shutil.which("pdftotext"):          # the deck as a reader gets it: each history ends on its row's share
        path = os.path.join(os.environ.get("TMPDIR", "/tmp"), f"h56-{os.getpid()}.pdf")
        with open(path, "wb") as fh:
            fh.write(deck._render(slides, "foot", "t", pdf=True))
        try:
            r = DC.check_pages(DC.pages_of(path))
        finally:
            os.remove(path)
        assert r["counts"]["history end"] == 0 and r["counts"]["evidence counts"] == 0, [f for f in r["findings"] if f["kind"] in ("history end", "evidence counts")]


# ---------- 4. deck_check ----------
PAYMENTS_R55 = (
    "Coverage\n"
    " Coverage                     Covered                Of what\n"
    "                                                     19 description-verified, 0 industry-supported, 1 not checked; the next 60 by market value checked each time the theme's\n"
    " Membership checked           19 of 20 (95%)         figures are stored. Checked share after each stored version: 100% (14 Nov 2026) → 100% (14 Nov 2026). The membership\n"
    "                                                     check reads no figures: companies with figures 14, a separate count.\n"
    "\n"
    " Each figure                                         EBITDA margin 13 · net margin 14\n")
FMCG_R55 = (
    "Coverage\n"
    "                                                   98 description-verified, 111 industry-supported, 0 not checked; every company checked. Checked share after each stored\n"
    "                             209 of 209\n"
    " Membership checked                                version: 76% (14 Nov 2026) → 100% (15 Nov 2026). The membership check reads no figures: companies with figures 93, a\n"
    "                             (100%)\n"
    "                                                   separate count.\n")


def test_deck_check_fails_a_history_that_does_not_end_on_the_rows_share():
    """Fails before: no rule read the history against the row's count (the live R55 Payments deck passed)."""
    got = DC.check_text(PAYMENTS_R55)
    assert got["counts"]["history end"] == 1
    assert [f["text"] for f in got["findings"] if f["kind"] == "history end"] == [
        "Membership checked 19 of 20 (95%): its share after each stored version ends on 100% (14 Nov 2026)"]
    assert DC.check_text(FMCG_R55)["counts"]["history end"] == 0          # its columns interleaved: 209 of 209 is 100%, the last point 100%
    fixed = PAYMENTS_R55.replace("100% (14 Nov 2026) → 100% (14 Nov 2026)", "90% (07 Nov 2026) → 95% (14 Nov 2026)")
    assert DC.check_text(fixed)["counts"]["history end"] == 0
    dv = ("Coverage\n                              Description-verified 4 of 30 (13%); description-verified share after each stored version: 10%\n"
          " Membership checked           22 of 30 (73%)  (07 Nov 2026) → 20% (14 Nov 2026). By state: 4 description-verified.\n")
    assert DC.check_text(dv)["counts"]["history end"] == 1


# ---------- 5. the customer and supplier map ----------
def test_an_order_win_citing_the_listing_regulations_or_a_value_with_gst_or_rs_dot_keeps_its_buyer():
    """Fails before: "SEBI", "GST" and "Rs." stopped the rules (a sentence with "SEBI" or "GST" was taken for a regulator's order and closed
    without a link or an AI read; a full stop in "Rs. 450" or "45.6" stopped the trigger), so nightly reads kept no link."""
    cases = [("Pursuant to Regulation 30 of the SEBI (Listing Obligations and Disclosure Requirements) Regulations, 2015, we wish to inform you that "
              "the Company has received an order worth Rs 45.6 crore from Bharat Heavy Electricals Limited for supply of transformers.",
              "Bharat Heavy Electricals Limited"),
             ("Kalpataru Projects International Limited has informed the Exchange about receipt of orders worth Rs 1,050 crore (excluding GST) "
              "from Power Grid Corporation of India Limited.", "Power Grid Corporation of India Limited"),
             ("The Company has bagged an order worth Rs. 450 crore from M/s. Bharat Electronics Ltd. for supply of radars.", "Bharat Electronics Ltd.")]
    for text, buyer in cases:
        links, unsure = X.extract_order(text, "Some Filer Limited")
        assert [x["counterparty"] for x in links] == [buyer] and not unsure, text
    for text in ["The Company has received an order from the Office of the Commissioner of Income Tax raising a demand of Rs 12 crore.",
                 "The Company has received an order passed by SEBI under Section 11B.",
                 "The Company received an order from the GST department imposing a penalty.",
                 "XYZ received an assessment order from the Income Tax Department."]:
        assert X.extract_order(text, "Some Filer Limited")[0] == [], text
