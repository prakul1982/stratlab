"""Release 27 (the owner's outside review of the eight R26 decks; Semiconductors fell to 8.0 because RPO and deferred revenue headlined for chip
makers): one registry of every operating and sector figure, whom each applies to and its four states (value, "–", "n/a", "n.c."), one legend
line; a figure headlines only where it applies to the main model and covers half the companies it applies to; makers' own figures (capex,
inventory days, R&D); insurers summarised by type; banks' NII / assets from the filings already read, never called NIM; an order book only where
a company's own update states it; unusual growth with its base; the notes page read from the registry. Generic: every synthetic theme, the new
structures (chemicals, real estate, telecom in India and the US, US retail, utilities, metals and mining) among them; synthetic data only."""
import re

import pytest

from app import deck
from app.intel import metric_registry as R
from app.intel import sector_metrics as S
from tests import fake_theme_structures as F
from tests.test_export import plain, texts
from tests.test_r20_deck import test_every_rule_holds_on_every_synthetic_theme as every_rule
from tests import test_r25_deck as R25

BUILT = {name: F.build(name) for name in list(F.STRUCTURES) + list(F.SECTOR_THEMES)}
IDS = list(BUILT)


def sector_table(slides, page):
    rows, head = [], None
    for s in slides:
        if s.title.startswith(f"{deck.SECTOR_TITLE}: {page}"):
            t = next(b for b in s.blocks if b["kind"] == "table")
            head = t["head"]
            rows += plain(t["rows"])
    return head, rows


def sector_note(slides, page):
    # deck89 (changed on purpose, owner 25 Nov: short footnotes): with the page's notes in full among the appendix's notes
    return deck.page_said(slides, f"{deck.SECTOR_TITLE}: {page}")


# ---------- 1. one registry ----------
def test_every_figure_a_deck_shows_is_in_the_registry_with_its_definition_period_source_limit_and_whom_it_applies_to():
    assert set(S.KEYS) <= set(R.BY_ID) and set(deck.METRIC_NOTES) <= set(R.BY_ID)
    for m in R.METRICS:
        # updated on purpose (m53, R53): a sector profile's count or per-unit price ("num", in the unit its label names: beds, MTPA, MW)
        assert m.label and m.definition and m.source and m.limit and m.applies and m.unit in ("pct", "chg", "x", "amt", "days", "num"), m.id
        assert m.period in R.STALE_MONTHS and set(m.regions) <= {"IN", "US"}
    assert len({R.MARK[s] for s in (R.UNAVAILABLE, R.NOT_APPLICABLE, R.NOT_COMPARABLE)}) == 3 and "0" not in R.MARK.values()
    assert R.LEGEND.count("–") == 1 and "n/a" in R.LEGEND and "n.c." in R.LEGEND
    # each family's own definitions are the registry's: sector_metrics reads them from there (one source of truth)
    assert all(S.BY_KEY[k][4].rstrip(".") == R.BY_ID[k].definition for k in S.KEYS)
    # every structure maps to a model family (theme_check.MODELS)
    from app.intel.theme_check import MODELS
    fams = {x[0] for x in MODELS.values()}
    assert {k for k, _ in R.STRUCTURES} == set(R.STRUCTURE_FAMILY) and set(R.STRUCTURE_FAMILY.values()) <= fams


def test_a_company_is_in_one_of_four_states_for_each_figure_and_medians_count_only_values_of_those_it_applies_to():
    rows = [{"symbol": "A", "rpo_growth": 10.0, "src": {"rpo_growth": {"period": "Dec 2025 on Dec 2024"}}},
            {"symbol": "B", "rpo_growth": None},
            {"symbol": "C", "rpo_growth": 900.0},                                          # a chip maker that files RPO
            {"symbol": "D", "rpo_growth": 5.0, "src": {"rpo_growth": {"period": "Mar 2024 on Mar 2023"}}},      # 21 months behind
            {"symbol": "E", "rpo_growth": 7.0, "nc": ["rpo_growth"]}]
    tg = [{"software", "us"}, {"software", "us"}, {"making", "semis", "us"}, {"royalties", "us"}, {"software", "us"}]
    st = R.states("rpo_growth", "US", rows, tg)
    assert st == [R.VALUE, R.UNAVAILABLE, R.NOT_APPLICABLE, R.NOT_COMPARABLE, R.NOT_COMPARABLE]
    from app.intel.theme_data import stat
    cov = R.coverage([r["rpo_growth"] for r in rows], st, stat)
    assert cov["n"] == 1 and cov["of"] == 4 and cov["median"] == 10.0                  # never the chip maker's, never a zero for B
    assert not R.applies("cet1", "IN", {"underwriting", "life"}) and R.applies("combined_ratio", "IN", {"health"})
    assert not R.applies("persistency_13", "IN", {"general"}) and not R.applies("rpo_growth", "US", {"making", "semis", "us"})
    assert R.applies("capex_share", "US", {"making", "us"}) and not R.applies("inventory_days", "US", {"capacity", "us"})
    assert not R.applies("sbc_share", "IN", {"us"})                                    # a US figure in an Indian theme: never


# ---------- 2. the headline rule ----------
def test_a_figure_headlines_only_where_it_applies_to_the_main_model_and_covers_half_the_companies_it_applies_to():
    assert R.HEADLINE_COVER == 0.5
    makers = [{"making", "semis", "us"}] * 6 + [{"royalties", "us"}] * 3
    assert R.main_family(makers) == "making"
    assert not R.fits_main("rpo_growth", "US", makers, "making") and R.fits_main("fcf_margin", "US", makers, "making")
    assert R.headline_ok("fcf_margin", {"n": 5, "of": 9}, True) and not R.headline_ok("fcf_margin", {"n": 4, "of": 9}, True)
    assert not R.headline_ok("fcf_margin", {"n": 2, "of": 2}, True)                    # under the base of 3
    assert not R.headline_ok("rpo_growth", {"n": 9, "of": 9}, False)                   # not the main model's figure
    assert not R.headline_ok("capex", {"n": 9, "of": 9}, True)                         # an amount never headlines
    assert not R.headline_ok("rpo_growth", {"n": 6, "of": 6}, True, extreme=2)         # unusual growth is a third of its values


def test_semiconductors_show_makers_own_figures_and_rpo_only_for_the_design_licensors_never_as_a_headline():
    v, slides = BUILT["semiconductors (US)"]
    us = v["sections"]["sector"]["families"]["us"]
    assert us["main"] == "making"
    assert {"capex_share", "inventory_days", "rd_share", "fcf_margin"} <= set(us["headline"])
    assert not {"rpo_growth", "rpo_cover", "deferred_growth"} & set(us["headline"])
    assert us["medians"]["rpo_growth"]["of"] == 3                                      # N of M: the 3 licensors it applies to
    head, rows = sector_table(slides, "US companies")
    byname = {r[0]: r for r in rows}
    chip = byname["Chip CH 0 Inc"]
    assert chip[head.index("RPO growth")] == "n/a" and chip[head.index("Capex / revenue")] == "15.0%" and chip[head.index("Inventory days")].endswith(" days")
    assert byname["Chip IP 0 Inc"][head.index("RPO growth")].startswith("+") and byname["Chip IP 0 Inc"][head.index("Inventory days")] == "n/a"
    t = texts(slides)
    # deck89 (changed on purpose, owner 25 Nov): the findings are one card of plain sentences; the sector's filed figures are lines of it
    card = {"lines": [ln for ln in deck.findings_lines(slides) if ln.startswith("Median of the") or "capex / revenue" in ln]}
    assert "RPO" not in " ".join(card["lines"]) and "deferred" not in " ".join(card["lines"]) and "capex / revenue" in " ".join(card["lines"])
    assert "Median RPO growth" not in t                                                # no question built on a figure that doesn't headline
    assert R.LEGEND in sector_note(deck.with_held(slides), "US companies")  # deck89 round 2 (changed on purpose, coordinator 25 Nov: the full records are kept with the deck, on the theme's page, not printed)
    # with no licensor filing RPO the column goes: no column of "n/a" and "–" only
    v2, slides2 = F.deck_of(*F.semis_us(ip_rpo=False)[:3], **F.semis_us(ip_rpo=False)[3])
    assert "RPO growth" not in sector_table(slides2, "US companies")[0]


def test_a_us_software_theme_still_headlines_rpo_where_it_is_the_main_models_figure():
    from tests.test_r25_deck import families
    v, slides = next((v, s) for n, (v, s) in families() if n.startswith("US software"))
    us = v["sections"]["sector"]["families"]["us"]
    assert {"rpo_growth", "deferred_growth"} <= set(us["headline"]) and "Median RPO growth" in texts(slides)


# ---------- 3. profiles by sector ----------
def test_us_company_facts_give_capex_inventory_days_and_rd_only_where_filed():
    got = S.us_figures(F.companyfacts(capex=100e6, inv=150e6, cost=600e6, rd=180e6))
    v = {k: x["v"] for k, x in got.items() if k != "_end"}
    assert v["capex_share"] == 10.0 and v["capex"] == 100.0 and v["inventory_days"] == round(150 / 600 * 365) and v["rd_share"] == 18.0
    assert got["inventory_days"]["period"] == "Dec 2025, over the fiscal year to Dec 2025"
    bare = S.us_figures(F.companyfacts())
    assert "inventory_days" not in bare and "rd_share" not in bare                     # not filed: unavailable, never a proxy


def test_insurers_are_summarised_by_type_never_one_median_across_types_and_reinsurance_on_its_own():
    v, slides = BUILT["insurers by type (IN)"]
    ins = v["sections"]["sector"]["families"]["insurer"]
    assert set(ins["types"]) == {"life", "general", "health", "reinsurance"} and ins["types"]["reinsurance"]["n"] == 1
    assert "combined_ratio" not in ins["medians"] and ins["headline"] == []
    assert ins["types"]["health"]["medians"]["combined_ratio"]["n"] == 3 and ins["types"]["general"]["medians"]["combined_ratio"]["median"] == 103.0
    assert "persistency_13" not in ins["types"]["general"]["keys"] and "claims_ratio" not in ins["types"]["life"]["keys"]
    head, rows = sector_table(slides, "insurers")
    assert head[1] == "Type"
    labels = [r[0] for r in rows if r[0].startswith("Median")]
    assert labels == ["Median, life insurers (companies)", "Median, general insurers (companies)", "Median, health insurers (companies)",
                      "Median, reinsurers (companies)"]
    life = next(r for r in rows if r[0] == "Life Cover 0 Ltd")
    assert life[head.index("Combined ratio")] == "n/a" and life[head.index("13th-month persistency")] == "85%"
    reins = next(r for r in rows if r[0] == "Median, reinsurers (companies)")
    # one reinsurer: its own figure, no median (R29: "N of M" in every sector median cell; deck89, changed on purpose, owner 25 Nov: no
    # placeholder cell, "–", the page's one note saying why)
    assert reins[head.index("Combined ratio")] == "–" and deck.FEW_NOTE in deck.page_said(slides, deck.SECTOR_TITLE)
    lines = deck.sector_lines({"sector": v["sections"]["sector"]})
    assert any(x.startswith("Median of the 3 health insurers with filed figures:") for x in lines)
    assert not any("reinsurer" in x for x in lines)


def test_banks_nii_over_assets_comes_from_the_filings_already_read_replaces_the_page_figure_and_is_never_called_nim():
    v, slides = BUILT["banks, NII / assets (IN)"]
    bank = v["sections"]["sector"]["families"]["bank"]
    assert "nii_assets_f" in bank["keys"] and bank["medians"]["nii_assets_f"]["n"] == 7
    want = round((3000 - 1800) * 2 * 12 / 6 / ((160000 + 140000) / 2) * 100, 2)
    row = next(c for x in v["layers"] for c in x["companies"] if c["symbol"] == "BK0")
    assert row["nii_assets"] == row["nii_assets_f"] == want
    # the bank with only its page's annual figure: another basis than the layer's filed ones, so "n.c." and out of the median
    lay = next(s for s in slides if s.title.startswith("Layer 2 ·"))
    t = next(b for b in lay.blocks if b["kind"] == "table")
    b4 = next(r for r in plain(t["rows"]) if r[0] == "Bank 4 Ltd")
    assert b4[t["head"].index("NII / assets")] == "n.c."
    assert v["layers"][1]["stats"]["nii_assets"]["n"] == 3 and v["layers"][0]["stats"]["nii_assets"]["n"] == 4
    assert "n.c.: not comparable" in deck.page_said(deck.with_held(slides), lay.title)          # deck89 (changed on purpose): the layer's notes in the appendix · deck89 round 2 (changed on purpose, coordinator 25 Nov: the full records are kept with the deck, on the theme's page, not printed)
    txt = texts(slides)
    assert "NII / assets" in txt and not re.search(r"\bNIM\b(?! and CASA)(?!\))", txt.replace("Not the bank's own net interest margin (NIM)", "")
                                                    .replace("not the bank's own NIM", ""))
    notes = {r[0]: r for s in deck.with_held(slides) if s.title.startswith(deck.NOTES_TITLE) for b in s.blocks if b["kind"] == "table" for r in plain(b["rows"])}   # deck89 round 2 (changed on purpose, coordinator 25 Nov: the full records are kept with the deck, on the theme's page, not printed)
    assert "NIM" in notes["NII / assets"][3]                                           # its limitation says it is not the NIM


def test_an_order_book_is_shown_only_where_a_companys_own_update_states_it_in_rupees_with_its_period():
    v, slides = BUILT["defence (IN)"]
    head, rows = sector_table(slides, "order books")
    assert head == ["Company", "Order book", "Order inflow", "Period"]
    byname = {r[0]: r for r in rows}
    assert byname["Defence DF 0 Ltd"][1] == "₹1.82 lakh cr" and byname["Defence DF 0 Ltd"][3] == "Sep 2026"
    assert byname["Defence DE 0 Ltd"][2] == "₹5,400 cr" and "Defence DE 1 Ltd" not in byname          # a dollar figure isn't taken
    assert "revenue" not in sector_note(slides, "order books").lower().replace("not revenue", "")
    _, s2 = F.deck_of(*F.defence_in(stated=False)[:3], **F.defence_in(stated=False)[3])
    assert not any(s.title.startswith(f"{deck.SECTOR_TITLE}: order books") for s in s2)
    for name, (v_, sl) in BUILT.items():                                               # never in a theme of another structure
        if not name.startswith("defence"):
            assert not any(s.title.startswith(f"{deck.SECTOR_TITLE}: order books") for s in sl), name


def test_indian_themes_of_the_new_structures_show_generic_figures_only():
    for name in ("chemicals (IN)", "real estate (IN)", "telecom (IN)", "utilities and power (IN)", "metals and mining (IN)"):
        v, slides = BUILT[name]
        assert v["sections"]["sector"] == {} and not any(s.title.startswith(deck.SECTOR_TITLE) for s in slides), name
    assert R.NOT_READ["pharma"] and R.NOT_READ["defence"]


# ---------- 4. unusual growth ----------
def test_unusual_growth_says_its_base_and_stays_out_of_a_headline_it_would_dominate():
    assert R.is_extreme(150.0) and R.is_extreme(-120.0) and not R.is_extreme(40.0) and R.is_extreme(40.0, 10.0, 1000.0)
    assert R.dominated([150.0, 10.0, 12.0]) and not R.dominated([150.0, 10.0, 12.0, 14.0])
    v, slides = BUILT["real estate (IN)"]
    app = " ".join(p for s in slides if s.title.startswith("Every company's figures") for b in s.blocks if b["kind"] == "text" for p in b["paras"])
    assert ("Revenue growth above 100% either way, or from a base under 5% of the median company's, with its base: Residential RD 0 Ltd +50%, "
            "from ₹50 cr to ₹75 cr.") in app
    # a sector growth figure from a small base, with its base
    fam = {"extreme": [{"name": "Chip CH 0 Inc", "key": "deferred_growth", "v": 212.5, "base": [100.0, 312.5], "unit": "USD million"}]}
    assert deck.extreme_line(fam).startswith("Unusual growth (above 100% either way, or from a small base), with its base: Chip CH 0 Inc, deferred "
                                             "revenue growth +212.5%, from $100 m to $312 m.")
    v2, slides2 = BUILT["semiconductors (US)"]
    us = v2["sections"]["sector"]["families"]["us"]
    # a chip maker's deferred revenue +200% doesn't apply to its model: "n/a", never listed or said as unusual growth
    assert us["extreme"] == [] and "Chip CH 0 Inc, deferred revenue growth" not in sector_note(slides2, "US companies")
    region, m, f, kw = F.telecom_us()
    pieces = {s_: kw["metrics"](s_, "us") for s_ in f}
    pieces["UE0"] = F.us_piece(F.companyfacts(rd=100e6))
    pieces["UE0"]["metrics"]["rpo_growth"] = {"v": 400.0, "period": "Dec 2025 on Dec 2024", "source": "Filed with the SEC", "base": [5.0, 25.0],
                                              "unit": "USD million"}
    v3, _ = F.deck_of(region, m, f, metrics=F.reader_of(pieces))
    assert v3["sections"]["sector"]["families"]["us"]["extreme"] == []                  # RPO doesn't apply to an equipment maker either


# ---------- 5. the notes page reads the registry ----------
@pytest.mark.parametrize("name", IDS)
def test_the_notes_page_rows_are_the_registrys_own(name):
    v, slides = BUILT[name]
    rows = [r for s in slides if s.title.startswith(deck.NOTES_TITLE) for b in s.blocks if b["kind"] == "table" for r in plain(b["rows"])]
    by_label = {}
    for m in R.METRICS:
        by_label.setdefault(m.label, []).append(m)
    for r in rows:
        if r[0] == deck.PEERS_ROW[0]:          # the peer rule is the deck's own method row (lane r27-quality), not a figure of the registry
            assert r == deck.PEERS_ROW, (name, r)
            continue
        # r60b (R60, updated on purpose): the Revenue row adds a bank's, lender's or insurer's revenue basis after the registry's own words
        assert any([m.label, m.source] == [r[0], r[2]] and (r[1] == m.definition or r[0] == "Revenue" and r[1].startswith(m.definition + ". "))
                   for m in by_label[r[0]]), (name, r)


# ---------- every rule on every new theme ----------
@pytest.mark.parametrize("name", IDS)
def test_every_deck_rule_holds_on_the_new_structures(name):
    v, slides = BUILT[name]
    every_rule(name, v, slides)
    R25.test_no_layer_is_called_highest_fastest_or_slowest_on_a_base_under_three_or_against_itself(name, v, slides)
    R25.test_every_count_beside_a_layer_figure_is_n_of_its_companies(name, v, slides)
    R25.test_the_notes_page_explains_only_the_figures_the_deck_shows_with_period_source_and_limits(name, v, slides)
    R25.test_every_table_row_is_drawn_so_a_figure_a_sentence_checks_against_is_on_the_page(name, v, slides)
    t = texts(slides)
    assert not re.search(r"(?<![\w.])0(?:\.0)?% \(\d+ of \d+", t)                       # a missing figure is never a zero


def test_the_deck_version_is_27():
    assert deck.THEME_DECK_VERSION == 97 and S.VERSION == 3          # deck101 (changed on purpose, every live R99 deck read again 27 Nov: dive text 58, deck 97); deck99 (changed on purpose, the deck96 audit's open items, 27 Nov: dive text 57, deck 96); rel98 (fix98 and map98 together, 27 Nov: dive text 56, deck 95, changed on purpose); map98 (a company of the map's own layers whose own first business sentence states another principal business listed as other work); fix98 (changed on purpose, members no longer listed: dive text 55, deck 94); deck96 (changed on purpose, every live theme deck checked 26 Nov: dive text 54, deck 93); deck89 (changed on purpose, owner 25 Nov: the theme deck remade as research): deck 92; e85 (LIVE21A, the R84 decks): deck 91, dive text 51 (updated on purpose); e84 (LIVE20A, the R82 decks): RULES 79, PLACE_CARRY[79] = 78, EARLIER_MAX 34, deck 90, dive text 50, blog GEN 12 (updated on purpose); e83 (LIVE19A, the R81 decks): RULES 78, PLACE_CARRY[78] = 77, EARLIER_MAX 33, deck 89, dive text 49, blog GEN 11 (updated on purpose); e82 (LIVE18A, the R80 decks): RULES 77, PLACE_CARRY[77] = 76, EARLIER_MAX 32, deck 88, dive text 48 (updated on purpose); e81 (LIVE17A, the R79 decks): RULES 76, PLACE_CARRY[76] = 75, EARLIER_MAX 31, deck 87, dive text 47 (updated on purpose); e80 (LIVE16A, the R78 decks): RULES 75, PLACE_CARRY[75] = 74, EARLIER_MAX 30, deck 86, dive text 46 (updated on purpose); e79 (the live R77 decks): RULES 74, PLACE_CARRY[74] = 73, EARLIER_MAX 29, deck 85, dive text 45 (updated on purpose); e78 (the live R76 decks): RULES 73, PLACE_CARRY[73] = 72, EARLIER_MAX 28, deck 84, dive text 44 (updated on purpose); e77 (the live R76 decks): RULES 72, PLACE_CARRY[72] = 71, EARLIER_MAX 27, deck 83, dive text 43 (updated on purpose); fix20 (the live R75 decks): RULES 71 kept, deck 82, dive text 42 (updated on purpose); r69e (R69): RULES 71, PLACE_CARRY[71] = 70, EARLIER_MAX 26, deck 81, dive text 41 (updated on purpose); r68e (R68): deck 80, dive text 40 (updated on purpose); r67e (R67): RULES 69, PLACE_CARRY[69] = 68, EARLIER_MAX 24, deck 79, dive text 39 (updated on purpose); r66e (R66): RULES 68, PLACE_CARRY[68] = 67, EARLIER_MAX 23, deck 78, dive text 38 (updated on purpose); r65e (R65): RULES 67, PLACE_CARRY[67] = 66, EARLIER_MAX 22, deck 77, dive text 37 (updated on purpose); r64e (R64): RULES 66, PLACE_CARRY[66] = 65, EARLIER_MAX 21, deck 76, dive text 36 (updated on purpose); r63e (R63): RULES 65, PLACE_CARRY[65] = 64, EARLIER_MAX 20, deck 75, dive text 35 (updated on purpose); r62 (R62): RULES 64, PLACE_CARRY[64] = 63, EARLIER_MAX 19, deck 74, dive text 34 (updated on purpose); r60 (R60): RULES 63, PLACE_CARRY[63] = 62, EARLIER_MAX 18, deck 73, dive text 33 (updated on purpose); r59 (R59): RULES 62, PLACE_CARRY[62] = 61, EARLIER_MAX 17, deck 72, dive text 32 (updated on purpose); r582 (R58.2): RULES 61, PLACE_CARRY[61] = 60, EARLIER_MAX 16, deck 71, dive text 31 (updated on purpose); r581 (R58.1): RULES 60, PLACE_CARRY[60] = 59, EARLIER_MAX 15, deck 70, dive text 30 (updated on purpose); r58 (R58): RULES 59, PLACE_CARRY[59] = 58, EARLIER_MAX 14, deck 69, dive text 29 (updated on purpose); r572 (R57.2): RULES 58, PLACE_CARRY[58] = 57, EARLIER_MAX 13, deck 68, dive text 28 (updated on purpose); dat57: sector figures VERSION 3 (updated on purpose); p57 (R56 review): RULES 56, PLACE_CARRY[56] = 55, deck 67, dive text 27 (updated on purpose); t56 (R55 review): RULES 55, PLACE_CARRY[55] = 54, deck 66, dive text 26 (updated on purpose); v55 (R55 review): RULES 54, PLACE_CARRY[54] = 53, deck 65, dive text 25 (updated on purpose); c54 (R53 review): RULES 53, PLACE_CARRY[53] = 52, deck 64, dive text 24 (updated on purpose); d53 (R53): RULES 52, PLACE_CARRY[52] = 51, deck 63, dive text 23 (updated on purpose); gl52 (R52): RULES 51, PLACE_CARRY[51] = 50, deck 62, dive text 22 (updated on purpose); rv51 (R51): RULES 50, PLACE_CARRY[50] = 49, deck 61, dive text 21 (updated on purpose); gl50 (R50): RULES 49, PLACE_CARRY[49] = 48, deck 60, dive text 20 (updated on purpose); ex49 (R49): RULES 48, PLACE_CARRY[48] = 47, deck 59, dive text 19, precise exclusion reasons, the business-model ranking rule (updated on purpose); vr48 (R48): figures reconciled with the year's lines before any is held, the comparison basis (updated on purpose); cl48 (R48): deck 58, dive text 18, the coverage flag row and who earns another way said in layer lines (updated on purpose); vf46 (R46): dive text 17, each checked figure's source record, net above EBITDA reconciled line by line (updated on purpose); tx2 (R45/R46): RULES 45, PLACE_CARRY[45] = 44, deck 57 (dive text 17 from vf46), the taxonomy regression guard and the screening populations (updated on purpose); c1 (R44): RULES 44, PLACE_CARRY[44] = 43, deck 56, dive text 16 (55 and 15 are R44.1's), classification coverage from evidence (updated on purpose); R44 (lane v1): deck 54, dive text 14, verification states (updated on purpose); lane d1: RULES 43, PLACE_CARRY[43] = 42, deck 53, dive text 12 (the outside review of the live R41 decks, updated on purpose); lane t1: deck 52, dive text 11 (LIVE7A, updated on purpose); R41: deck 51, coloured cells measured bold (updated on purpose); lane s3-r40: RULES 42, deck 50, dive text 10 (updated on purpose); R35 bumped the deck version (updated on purpose)


def test_a_software_companys_unusual_rpo_growth_is_listed_with_its_base_and_kept_out_of_the_headline_when_it_dominates():
    from tests.test_r20_deck import us_map_theme
    from tests.test_r23_metrics import companyfacts
    from tests.test_r18_deck import deck_of as deck18
    region, m, f = us_map_theme()
    pieces = {}
    for i, sym in enumerate(sorted(f)):
        got = S.us_figures(companyfacts())
        got.pop("_end")
        pieces[sym] = {"family": "us", "end": "2026-01-31", "metrics": got}
    soft = [s for s in sorted(f) if "Prepackaged" in next(c["industry"] for x in m["value_chain"] for c in x["companies"] if c["ticker"] == s)]
    pieces[soft[0]]["metrics"]["rpo_growth"] = {**pieces[soft[0]]["metrics"]["rpo_growth"], "v": 551.6, "base": [120.0, 781.9]}
    v, slides = deck18(region, m, f, metrics=lambda s, fam: pieces.get(s))
    us = v["sections"]["sector"]["families"]["us"]
    assert [(x["symbol"], x["v"]) for x in us["extreme"]] == [(soft[0], 551.6)] and "rpo_growth" in us["headline"]
    assert "rpo growth +551.6%, from $120 m to $782 m" in sector_note(deck.with_held(slides), "US companies").replace("RPO", "rpo")  # deck89 round 2 (changed on purpose, coordinator 25 Nov: the full records are kept with the deck, on the theme's page, not printed)
    for s in soft[1:3]:                     # three of the software companies' RPO growth unusual: a third of its values, so no headline
        pieces[s]["metrics"]["rpo_growth"] = {**pieces[s]["metrics"]["rpo_growth"], "v": 300.0, "base": [100.0, 400.0]}
    v2, slides2 = deck18(region, m, f, metrics=lambda s, fam: pieces.get(s))
    assert "rpo_growth" not in v2["sections"]["sector"]["families"]["us"]["headline"] and "Median RPO growth" not in texts(slides2)


def test_an_insurers_type_comes_from_its_own_words_then_its_filings_format():
    assert R.insurer_type({"name": "General Insurance Corporation", "map_what": "provides reinsurance to Indian insurers"}, "GI") == "reinsurance"
    assert R.insurer_type({"name": "Star Cover Ltd", "industry": ["Financial Services", "Insurance", "General Insurance"],
                           "map_what": "sells health insurance policies"}, "GI") == "health"
    assert R.insurer_type({"name": "Max Life Ltd", "map_what": "sells life and health cover"}, "LI") == "life"
    assert R.insurer_type({"name": "Lombard Ltd"}, "GI") == "general" and R.insurer_type({"name": "X Life Ltd"}) == "life"
