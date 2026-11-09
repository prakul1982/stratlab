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
    return " ".join(p for s in slides if s.title.startswith(f"{deck.SECTOR_TITLE}: {page}") for b in s.blocks if b["kind"] == "text" for p in b["paras"])


# ---------- 1. one registry ----------
def test_every_figure_a_deck_shows_is_in_the_registry_with_its_definition_period_source_limit_and_whom_it_applies_to():
    assert set(S.KEYS) <= set(R.BY_ID) and set(deck.METRIC_NOTES) <= set(R.BY_ID)
    for m in R.METRICS:
        assert m.label and m.definition and m.source and m.limit and m.applies and m.unit in ("pct", "chg", "x", "amt", "days"), m.id
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
    assert chip[head.index("RPO growth")] == "n/a" and chip[head.index("Capex / revenue")] == "15%" and chip[head.index("Inventory days")].endswith(" days")
    assert byname["Chip IP 0 Inc"][head.index("RPO growth")].startswith("+") and byname["Chip IP 0 Inc"][head.index("Inventory days")] == "n/a"
    t = texts(slides)
    card = next(c for s in slides if s.title == "Key findings" for b in s.blocks if b["kind"] == "cards" for c in b["items"] if c["title"] == "Sector operating figures")
    assert "RPO" not in " ".join(card["lines"]) and "deferred" not in " ".join(card["lines"]) and "capex / revenue" in " ".join(card["lines"])
    assert "Median RPO growth" not in t                                                # no question built on a figure that doesn't headline
    assert R.LEGEND in sector_note(slides, "US companies")
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
    assert reins[head.index("Combined ratio")] == "– (1 of 1)"     # one reinsurer: its own figure, no median (R29: "N of M" in every sector median cell)
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
    assert "n.c.: not comparable" in " ".join(p for b in lay.blocks if b["kind"] == "text" for p in b["paras"])
    txt = texts(slides)
    assert "NII / assets" in txt and not re.search(r"\bNIM\b(?! and CASA)(?!\))", txt.replace("Not the bank's own net interest margin (NIM)", "")
                                                    .replace("not the bank's own NIM", ""))
    notes = {r[0]: r for s in slides if s.title.startswith(deck.NOTES_TITLE) for b in s.blocks if b["kind"] == "table" for r in plain(b["rows"])}
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
        assert any([m.label, m.definition, m.source] == r[:3] for m in by_label[r[0]]), (name, r)


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
    assert deck.THEME_DECK_VERSION == 37 and S.VERSION == 2          # R33 bumped the deck version (updated on purpose)


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
    assert "rpo growth +551.6%, from $120 m to $782 m" in sector_note(slides, "US companies").replace("RPO", "rpo")
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
