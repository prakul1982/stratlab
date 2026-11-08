"""Release 22 (outside review of the live R21 decks): every money figure in one currency (a foreign filer's NT$ revenue shown as dollars), the
same metric with the same number and count wherever it is shown, layer names that fit the companies placed in them, extra layers when "Other"
is broad, the residual group never compared, counts never above their population, a contract-services company that fits a layer stays
confirmed, and a small base said beside a highest median. Generic: every sector, India and the US; synthetic data only."""
import re

import pytest

from app import deck
from app.intel import sec
from app.intel import theme_base as B
from app.intel import theme_data as D
from tests.test_deck_look import full_view
from tests.test_export import plain, table_of, texts
from tests.test_r18_deck import deck_of
from tests.test_r20_deck import ALL, test_every_rule_holds_on_every_synthetic_theme as every_rule
from tests.test_theme1 import facts


def co(sym, name, what="", industry="", base=True):
    return {"ticker": sym, "name": name, "what": what, "industry": industry, "base": base, "basis": "industry", "verified": True}


def foreign_theme(rate=True):
    """The US: chip makers in three of the map's layers, one of them a foreign filer reporting in TWD whose page states today's rate (an ADR of
    5 ordinary shares), its market value already in dollars."""
    spec = {"Chip design": [("D1", "Design One Inc"), ("D2", "Design Two Inc"), ("D3", "Design Three Inc")],
            "Foundries": [("FDRY", "Island Foundry Co Ltd"), ("F2", "Foundry Two Inc"), ("F3", "Foundry Three Inc")],
            "Equipment": [("E1", "Tool One Inc"), ("E2", "Tool Two Inc"), ("E3", "Tool Three Inc")]}
    m = {"sector": "Chips", "summary": "Chip designers, foundries and tool makers.", "sub_themes": [], "tailwinds": [], "risks": [], "generated_at": 1.0,
         "placements": {"checked": True, "pending": 0, "placed": 9, "total": 9, "base": 9, "named": 0, "added": 0, "confirmed": 0},
         "value_chain": [{"layer": k, "description": f"{k}.", "companies": [co(s, n, f"works in {k.lower()}") for s, n in v]} for k, v in spec.items()]}
    f = {}
    for k, v in spec.items():
        for i, (s, n) in enumerate(v):
            f[s] = {**facts(s, n, [1000, 1100, 1200, 1300 + i * 10], [30, 31, 32, 33], [200, 220, 240, 260], cap=50000 - i * 1000, pe=30.0),
                    "region": "US", "unit": "$ million"}
    twd = facts("FDRY", "Island Foundry Co Ltd", [2_200_000, 2_600_000, 3_000_000, 3_800_000], [60, 62, 64, 66], [900_000, 1_000_000, 1_200_000, 1_700_000],
                cap=1_900_000, pe=25.0)
    f["FDRY"] = {**twd, "region": "US", "unit": "TWD million", "report_currency": "TWD",
                 **({"fx": {"rate": 0.032, "pair": "TWD/USD", "at": "2026-11-06"}} if rate else {}),
                 "currency_note": "The company reports in New Taiwan Dollar (TWD): its figures here are in TWD million, as filed."}
    return "US", m, f


# ---------- 1. one currency ----------
def test_a_foreign_filers_money_figures_are_converted_to_the_themes_currency_at_the_stated_rate():
    region, m, f = foreign_theme()
    row = D.company_row("US", "FDRY", f["FDRY"])
    assert row["revenue"] == pytest.approx(3_800_000 * 0.032) and row["profit"] == pytest.approx(1_700_000 * 0.032)
    assert row["unit"] == "$ million" and row["currency"] == "TWD" and row["fx"] == {"rate": 0.032, "at": "2026-11-06"}
    assert row["net"] == pytest.approx(44.7, abs=0.1) and row["cap"] == 1_900_000                    # margins unchanged; market value already dollars
    v, slides = deck_of(region, m, f)
    foundries = next(x for x in v["layers"] if x["layer"] == "Foundries")
    assert foundries["revenue"] == pytest.approx(3_800_000 * 0.032 + 1310 + 1320)                      # the layer's sum in dollars
    cur = next(r for r in table_of(slides, "Data confidence")["rows"] if r[0] == "Currency")
    assert cur[1] == "Island Foundry Co Ltd reports in TWD, converted at 1 USD = 31.25 TWD (rate of 06 Nov 2026)." and "Every money figure in US dollars" in cur[2]
    assert "$3,800,000" not in texts(slides) and "$3.80 tn" not in texts(slides)


def test_with_no_rate_a_foreign_filers_money_figures_are_left_out_and_said():
    region, m, f = foreign_theme(rate=False)
    row = D.company_row("US", "FDRY", f["FDRY"])
    assert row["revenue"] is None and row["profit"] is None and row["net"] == pytest.approx(44.7, abs=0.1) and row["fx"] == {"rate": None, "at": None}
    v, slides = deck_of(region, m, f)
    cur = next(r for r in table_of(slides, "Data confidence")["rows"] if r[0] == "Currency")
    assert "No rate for Island Foundry Co Ltd: their revenue and other money figures are left out." in cur[1]
    # a rate written in the page's note is read when the page keeps no fx record
    noted = {**f["FDRY"], "currency_note": "The company reports in New Taiwan Dollar (TWD) ... to dollars at today's rate (1 USD = 32.00 TWD)."}
    assert D.report_fx(noted, "US")[1] == pytest.approx(1 / 32)
    # India: the app keeps no rupee rate for another currency, so such a company's money figures are left out there
    usd = {**facts("UX", "Dollar Reporter Ltd", [100, 110, 120, 130], [20, 20, 20, 20], [10, 11, 12, 13]), "unit": "USD million"}
    assert D.report_fx(usd, "IN") == ("USD", None, None) and D.company_row("IN", "UX", usd)["revenue"] is None


def test_an_adr_market_value_counts_adrs_not_ordinary_shares():
    assert sec.market_value({"shares": 25_000_000_000, "ads_ratio": 5}, 200.0) == pytest.approx(1_000_000)          # $ million
    assert sec.market_value({"shares": 25_000_000_000}, 40.0) == pytest.approx(1_000_000)


# ---------- 2. one number per metric per population ----------
def _measures(slides):
    out = {}
    for title, label_col, val_col, n_col in (("Growth and profitability", 0, 1, 2), ("Valuation", 0, 1, 3)):
        for s in slides:
            if s.title != title:
                continue
            for b in s.blocks:
                if b["kind"] != "table" or b["head"][0] not in ("Median", "Measure"):
                    continue
                for r in plain(b["rows"]):
                    out.setdefault(r[label_col], set()).add((r[val_col], r[n_col] if n_col < len(r) else ""))
    return out


@pytest.mark.parametrize("name,v,slides", [(n, v, s) for n, (v, s) in ALL] + [("foreign filer (US)", *deck_of(*foreign_theme()))],
                         ids=[n for n, _ in ALL] + ["foreign filer (US)"])
def test_any_metric_shown_twice_has_one_number_and_no_count_exceeds_its_population(name, v, slides):
    every_rule(name, v, slides)                                                     # every earlier rule, on this theme too
    for label, seen in _measures(slides).items():
        assert len(seen) == 1, (label, seen)
    val = (v.get("sections") or {}).get("valuation") or {}
    if val.get("n"):
        assert ((val.get("pe") or {}).get("n") or 0) + (val.get("losses") or 0) <= val["n"]
    q = (v.get("sections") or {}).get("quarter") or {}
    if q.get("sales"):
        assert q.get("sales_up", 0) + q.get("sales_down", 0) <= q["sales"]["n"] <= len(q.get("companies") or [])
    t = texts(slides)
    for a, b in re.findall(r"(\d+) of (\d+)\b", t):
        assert int(a) <= int(b), (a, b)


# ---------- 3, 4: layer names fit their companies; extra layers when "Other" is broad ----------
def mapped():
    own = [{"layer": "Raw materials and castings", "description": "Steel and rubber producers.", "companies": [{"ticker": "R1", "name": "Forge One", "verified": True}]},
           {"layer": "Vehicle makers", "description": "Make cars and trucks.", "companies": [{"ticker": "V1", "name": "Car One", "verified": True}]}]
    rest = [{"layer": "Auto components", "official": True, "basis": "industry", "description": "",
             "companies": [{"ticker": f"X{i}", "name": f"Part {i}", "industry": "Auto Components & Equipments", "cap": 100 - i, "base": True, "basis": "industry"}
                           for i in range(8)]}]
    return {"sector": "Automotive", "value_chain": own + rest, "sub_themes": []}


def test_one_answer_renames_a_layer_that_doesnt_fit_and_adds_layers_for_a_broad_other_group():
    def ask(system, text):
        return {"place": [{"symbol": "X0", "layer": "L0"}] + [{"symbol": f"X{i}", "layer": "none"} for i in range(1, 8)],
                "rename": [{"layer": "L0", "name": "Forgings, castings and metal components", "description": "Forge and machine metal parts for vehicle makers."},
                           {"layer": "L1", "name": "Makers 2026", "description": "x"}],                       # a name with a figure: dropped
                "extra": [{"name": "Electrical parts", "description": "Make wiring and lamps.", "symbols": ["X1", "X2", "X3"]},
                          {"name": "Interiors", "description": "Make seats.", "symbols": ["X4", "X5"]}, {"name": "Third", "symbols": ["X6", "X7"]}]}
    out, got = B.place_rest(mapped(), "Automotive", lambda s: None, ask=ask)
    names = [v["layer"] for v in out["value_chain"]]
    assert names == ["Forgings, castings and metal components", "Vehicle makers", "Electrical parts", "Interiors", "Other automotive companies"]
    first = out["value_chain"][0]
    assert first["was"] == "Raw materials and castings" and first["description"] == "Forge and machine metal parts for vehicle makers."
    assert [c["ticker"] for c in out["value_chain"][4]["companies"]] == ["X6", "X7"]                   # at most two extra layers
    assert all(c.get("fit") for v in out["value_chain"][:4] for c in v["companies"] if c.get("placed"))
    again, _ = B.place_rest(mapped(), "Automotive", lambda s: None, ask=lambda s, t: pytest.fail("asked again"), kept=got)
    assert again == out
    words, _ = B.place_rest(mapped(), "Automotive", lambda s: None)                                   # no AI: the map's names kept, no extra layer
    assert [v["layer"] for v in words["value_chain"]][:2] == ["Raw materials and castings", "Vehicle makers"]


def test_extra_layers_only_when_the_other_group_is_broad_and_the_word_reads_as_an_adjective():
    big = mapped()["value_chain"][1]
    big = {**big, "companies": [{"ticker": f"V{i}", "name": f"Car {i}", "verified": True} for i in range(20)]}    # 3 left over of 24: under a sixth
    small = {**mapped(), "value_chain": [mapped()["value_chain"][0], big, {**mapped()["value_chain"][2], "companies": mapped()["value_chain"][2]["companies"][:3]}]}
    ask = lambda s, t: {"place": [{"symbol": f"X{i}", "layer": "none"} for i in range(3)], "extra": [{"name": "Electrical parts", "symbols": ["X0", "X1"]}]}   # noqa: E731
    out, _ = B.place_rest(small, "Automotive", lambda s: None, ask=ask)
    assert [v["layer"] for v in out["value_chain"]][-1] == "Other automotive companies" and "Electrical parts" not in [v["layer"] for v in out["value_chain"]]
    for theme, want in (("Semiconductors", "Other semiconductor companies"), ("Private banks", "Other private bank companies"),
                        ("IT services", "Other IT service companies"), ("Defence", "Other defence companies"), ("Batteries", "Other battery companies"),
                        ("Glass", "Other glass companies"), ("EVs", "Other EVs companies")):
        assert B.other_label(theme) == want, theme


# ---------- 6, 10: the "Other" group never compared; a small base said ----------
def test_the_other_group_is_never_called_highest_and_a_small_base_says_its_count(monkeypatch):
    # R31: a test of the ranking rules on fixtures of 3 or 4 companies a layer, run at the marks' floor (COMPARE_MIN); the headline floor
    # of 5 (HEADLINE_MIN) on the same fixtures is tested in tests/test_r31_bound.py
    monkeypatch.setattr("app.intel.theme_data.HEADLINE_MIN", 3)
    blocks = [{"layer": "A", "n": 3, "revenue": 1, "official": False, "stats": {"ebitda": {"median": 22.0, "n": 3}}, "companies": []},
              {"layer": "B", "n": 6, "revenue": 1, "official": False, "stats": {"ebitda": {"median": 12.0, "n": 6}}, "companies": []},
              {"layer": "Other defence companies", "n": 9, "revenue": 1, "official": True, "basis": "rest", "stats": {"ebitda": {"median": 24.5, "n": 9}}, "companies": []}]
    c = D.chain_table(blocks)
    assert (c["highest"], c["lowest"]) == ("A", "B")
    assert c["line"] == ('Median EBITDA margin is highest in A (22.0%, 3 companies) and lowest in B (12.0%), a gap of 10.0 points; among the map\'s layers, '
                         'the "Other" group left out.')
    alone = D.chain_table([blocks[0], blocks[2]])                                   # one map layer and the residual: nothing compared
    assert alone["highest"] is None


# ---------- 8. a contract-services company that fits a layer stays confirmed ----------
def test_a_contract_research_company_that_fits_a_layer_is_not_flagged_by_the_other_work_list():
    words = D.theme_words({"sector": "Pharma", "placements": {"industries": ["Pharmaceuticals"]},
                           "value_chain": [{"layer": "Contract research and manufacturing", "description": "Run trials and make medicines for drug makers."}]}, "Pharma")
    cro = {"base": True, "basis": "industry", "what": "Syncro Labs provides integrated contract research and development services and consulting to biotech firms"}
    assert D.membership({**cro, "what": "Syncro Labs provides software and consulting services to hospitals"}, words) == "unverified"
    assert D.membership({**cro, "fit": True, "what": "Syncro Labs provides software and consulting services to hospitals"}, words) == "core"
    assert D.membership(cro, words) == "core"


def test_the_map_prompt_asks_for_mutually_exclusive_layers_and_sub_themes_that_follow_them():
    from app.intel import ai
    src = open(ai.__file__).read()
    assert "Each layer groups companies by their main business, so each company belongs to one layer" in src
    assert "never an activity every\ncompany of the theme does" in src and "The sub-themes follow the main layers" in src and "business models whose\neconomics differ stay apart" in src
