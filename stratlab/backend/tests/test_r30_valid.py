"""Release 30 (lane r30-valid): the owner's review of the live R28 decks. Headlines need comparable asset intensity, figures are checked
before use, coverage is one table of four kinds, unknown models of a kept placement are asked again once, and a layer page's header says
how many companies are in the figures. Synthetic only: no real company's name or figure."""
import copy

from app import deck
from app.intel import theme_base as B
from app.intel import theme_data as D
from app.intel import theme_routes as T
from tests import synthetic_themes_r27 as S
from tests.test_r18_deck import deck_of
from tests.test_r25_class import it_mixed
from tests.test_theme1 import facts


def _with_debt(fn, ratios: dict):
    """A synthetic theme whose companies carry debt (a multiple of the latest revenue, by symbol prefix), so their capital per unit of
    revenue is known: equity from debt over debt to equity, plus the debt."""
    region, m, f, market = fn()
    for s_, x in f.items():
        for p_, k in ratios.items():
            if s_.startswith(p_):
                # (updated on purpose, ex49: the debt of the revenue's own year is the one the capital proxy reads, theme_data.capital_inputs)
                x["debt"] = x["years"][-1]["debt"] = x["years"][-1]["sales"] * k
    from tests.gl50_read import read
    return region, read(m), f, market        # gl50 (R50, updated on purpose): the layers' way of earning read, so the capital rule is what decides


def _texts(slides):
    out = []
    for s in slides:
        for b in s.blocks:
            for it in b.get("items") or []:
                if isinstance(it, dict):
                    out += [str(x) for x in it.get("lines") or []]
            out += [str(x) for x in b.get("paras") or []]
    return out


# ---------- 1. a layer-vs-layer headline needs comparable asset intensity ----------
HEAVY_LIGHT = {"utilities": (S.utilities_in, {"PG": 3.0, "PT": 0.1, "PD": 1.0}),
               "telecom": (S.telecom_in, {"TS": 3.0, "TI": 2.0, "TE": 0.1}),
               "metals": (S.metals_mining_in, {"ST": 0.2, "AL": 0.3, "MN": 3.0, "VEDL": 1.0})}


def test_layers_of_very_different_capital_needs_are_described_never_ranked(monkeypatch):
    # R31: a test of the ranking rules on fixtures of 3 or 4 companies a layer, run at the marks' floor (COMPARE_MIN); the headline floor
    # of 5 (HEADLINE_MIN) on the same fixtures is tested in tests/test_r31_bound.py
    monkeypatch.setattr("app.intel.theme_data.HEADLINE_MIN", 3)
    for name, (fn, pbs) in HEAVY_LIGHT.items():
        region, m, f, market = _with_debt(fn, pbs)
        v, slides = deck_of(region, m, f, index_rows=lambda mk=market: mk)
        ch = v["chain"]
        assert ch["highest"] is None and ch["lowest"] is None, name
        assert ch["line"].startswith("Median EBITDA margin by layer: ") and "not ranked" in ch["line"] and "highest" not in ch["line"], name
        found = " ".join(_texts(slides))
        assert "Median EBITDA margin is highest" not in found and "Fastest revenue growth" not in found, name


def test_layers_alike_in_capital_needs_are_still_ranked(monkeypatch):
    # R31: a test of the ranking rules on fixtures of 3 or 4 companies a layer, run at the marks' floor (COMPARE_MIN); the headline floor
    # of 5 (HEADLINE_MIN) on the same fixtures is tested in tests/test_r31_bound.py
    monkeypatch.setattr("app.intel.theme_data.HEADLINE_MIN", 3)
    for name, (fn, pbs) in HEAVY_LIGHT.items():
        region, m, f, market = _with_debt(fn, {k: 1.0 for k in pbs})
        v, _ = deck_of(region, m, f, index_rows=lambda mk=market: mk)
        assert v["chain"]["highest"] and "highest" in v["chain"]["line"], name
    # no capital figure at all (no debt or price to book): nothing to compare, the R29 rules alone decide
    region, m, f, _ = S.utilities_in()
    from tests.gl50_read import read
    assert deck_of(region, read(m), f)[0]["chain"]["highest"]           # gl50 (updated on purpose): the way of earning read
    assert deck_of(region, m, f)[0]["chain"]["highest"] is None         # gl50 (R50): none read, none ranked


def test_capital_per_revenue_and_the_threefold_rule(monkeypatch):
    # R31: a test of the ranking rules on fixtures of 3 or 4 companies a layer, run at the marks' floor (COMPARE_MIN); the headline floor
    # of 5 (HEADLINE_MIN) on the same fixtures is tested in tests/test_r31_bound.py
    monkeypatch.setattr("app.intel.theme_data.HEADLINE_MIN", 3)
    assert D.capital_per_revenue(1000, 2.0, 500, None, 1000) == 1.0         # equity 500 + debt 500 over revenue 1,000
    assert D.capital_per_revenue(None, None, 600, 2.0, 300) == 3.0          # equity from debt over debt to equity
    assert D.capital_per_revenue(1000, -1.0, None, None, 1000) is None and D.capital_per_revenue(1000, 2.0, 0, None, 0) is None
    read_ = {"id": "manufacturing", "family": "making"}        # gl50 (R50, updated on purpose): a way of earning read, else nothing is ranked
    rows = [("A", 30.0, 3, 3, read_, "full", 0.5), ("B", 10.0, 3, 3, read_, "full", 1.4)]
    pick = dict(of=lambda t: t[3], model=lambda t: t[4], basis=lambda t: t[5], intensity=lambda t: t[6])
    assert D.rank_pair(rows, lambda t: t[1], lambda t: t[2], **pick)[0][0] == "A"
    assert D.rank_pair([rows[0], rows[1][:6] + (2.0,)], lambda t: t[1], lambda t: t[2], **pick) is None
    assert D.comparable_intensity([{"i": 1.0}, {"i": None}], lambda r: r["i"])


# ---------- 2. each figure checked before it is used ----------
def _row(**kw):
    f = facts("OPX", "Operator X Ltd", [42000, 43000, 44000, 45000], [41, 41, 42, 42], kw.pop("profits", [-30000, -29000, -27000, 37000]),
              roce=kw.pop("roce", -1.7), cap=50000)
    for k, x in kw.items():
        if k == "other_income":
            f["years"][-1]["other_income"] = x
        else:
            f[k] = x
    return D.company_row("IN", "OPX", f)


def test_a_net_profit_lifted_on_a_negative_return_and_negative_equity_is_held_with_its_checks():
    r = _row(book_value=-3.3)
    # (updated on purpose, R48: the outside review of the live R46 decks): a positive net profit beside a negative ROCE alone never makes the
    # net margin invalid. The stored lines give negative capital employed (book equity −₹1,650 crore, debt ₹100 crore), so the ROCE is the
    # figure with a calculation defect (invalid); the 82.2% net margin is checked as any unusual margin: above its EBITDA margin with no stored
    # line to cover it, it is shown with † and left out of the medians (not reconciled), never "–"
    assert r["net"] == 82.2 and r["one_off"] and r["roe"] is None and r["roce"] is None and "net" not in r["held"]
    assert r["verify"]["net"]["state"] == D.UNVERIFIED and D.CHECKS["sign"] in r["verify"]["net"]["checks"]
    assert r["verify"]["net"]["sign"]["kind"] == "negative_capital"
    assert r["held"]["roce"]["checks"] == [D.CHECKS["neg_capital"]] and r["verify"]["roce"]["state"] == D.INVALID
    assert r["held"]["roe"]["checks"] == [D.CHECKS["neg_equity"]]


def test_other_income_sign_and_ebitda_checks():
    r = _row(profits=[1, 1, 1, 9000], roce=5.0, other_income=6000)         # 20% net, of which income outside operations is two thirds
    # (updated on purpose, R44): income outside operations above half the net profit is a component that explains the margin, said, not
    # a cutoff: the 20% net margin is verified against the company's own filed figures and kept in the medians
    assert r["net"] == 20.0 and "net" not in (r.get("held") or {}) and r["verify"]["net"]["state"] == D.VERIFIED
    assert "income outside operations of ₹6,000 crore is 67% of the net profit" in r["verify"]["net"]["why"] and not r["one_off"]
    assert _row(profits=[1, 1, 1, 9000], roce=5.0, other_income=1000)["net"] == 20.0
    r = _row(profits=[1, 1, 1, 9000], roce=5.0, net_margin=-4.0)
    # (updated on purpose, R48): a net margin of the other sign from the page's own is reconciled with the stored years, never invalid for
    # the sign alone: no stored year gives the page's −4%, so it is not reconciled (shown with †, out of the medians)
    assert r["net"] == 20.0 and "net" not in (r.get("held") or {}) and r["verify"]["net"]["state"] == D.UNVERIFIED
    assert r["verify"]["net"]["checks"] == [D.CHECKS["sign_page"]] and "no stored year's net profit over revenue gives it" in r["verify"]["net"]["why"]
    a, b = {"symbol": "A", "ebitda": 95.0}, {"symbol": "B", "ebitda": 95.0}
    D.validate_model(a, "services")
    D.validate_model(b, "royalties")
    assert a["ebitda"] is None and a["held"]["ebitda"]["checks"] == [D.CHECKS["ebitda_unusual"]] and b["ebitda"] == 95.0
    assert a["verify"]["ebitda"]["state"] == D.UNVERIFIED and "no operating profit to check it against" in a["verify"]["ebitda"]["why"]


def test_a_held_figure_leaves_medians_and_is_named_on_the_data_confidence_page():
    region, m, f, market = S.telecom_in()
    sym = m["value_chain"][0]["companies"][0]["ticker"]
    f[sym].update(roce=-1.7, book_value=-3.3)
    f[sym]["years"][-1]["profit"] = f[sym]["years"][-1]["sales"] * 0.77
    v, slides = deck_of(region, m, f, index_rows=lambda: market)
    held = v["checks"]["held"]
    # (updated on purpose, R48): the positive net profit beside the negative ROCE is reconciled with the stored lines first: they give negative
    # capital employed, so the ROCE is held (invalid) and the 77% net margin, above its EBITDA margin with no line to cover it, is shown with
    # † and left out of the net-margin median, never held as "–" for the signs alone
    assert [x["key"] for x in held if x["symbol"] == sym] == ["roce", "roe"]
    lay = v["layers"][0]
    assert lay["stats"]["net"]["n"] == len(lay["companies"]) - 1 and sym in lay["one_off"]
    conf = next(s for s in slides if s.title == "Data confidence")
    row = next(r for b in conf.blocks if b["kind"] == "table" for r in b["rows"] if r[0] == "Figure checks")
    assert "ROCE −1.7%" in row[1] and D.CHECKS["neg_capital"] in row[1] and deck.ANOMALY_WHY in row[2]
    assert not any(w in row[1] + row[2] for w in ("because", "due to", "one-off gain"))


# ---------- 3. coverage: one table, four kinds ----------
def test_every_synthetic_deck_has_the_coverage_table_and_it_reconciles():
    for name, v, slides in S.decks():
        # R44 (updated on purpose): the checks' longer rows (verified figures, the coverage of informative layers) can need the room, and the
        # coverage then has a page of its own (d1); the table is checked wherever it is
        tab = next(b for s in slides if s.title in ("Data confidence", "Coverage") for b in s.blocks
                   if b["kind"] == "table" and b.get("head") == deck.COVERAGE_HEAD)
        kinds = [r[0] for r in tab["rows"]]
        # tx2 (R46, updated on purpose): the screening populations first (considered = screened out + members), then the companies by count
        assert kinds[:2] == ["Screening", "Companies, by count"] and "Each figure" in kinds and "Each layer" in kinds, name
        mv = next((r for r in tab["rows"] if r[0] == "Market value"), None)
        if mv:
            assert mv[1].endswith("%") and "market value" in mv[2] and "not of companies" in mv[2], name
        cov = deck.coverage(v)
        assert deck.coverage_table_flags(tab["rows"], v, cov) == [], name
        gate = deck.publication_gate(slides, v)
        assert not [d for d in gate["dropped"] if d["text"].startswith("coverage:")], name


def test_the_coverage_gate_catches_a_count_above_its_whole_and_value_said_as_companies():
    name, v, slides = next(S.decks())
    cov = deck.coverage(v)
    rows = deck.coverage_table(v, cov)
    bad = [["Companies, by count", f"{cov['total'] + 1} of {cov['total']}", "companies"]] + [
        [r[0], r[1] + " companies" if r[0] == "Market value" else r[1], r[2]] for r in rows[1:]]
    flags = deck.coverage_table_flags(bad, v, cov)
    assert any("above" in x for x in flags) and any("market value" in x for x in flags)
    assert deck.coverage_table_flags(rows[2:], v, cov)[0].startswith("no row")


# ---------- 4. unknown models of a kept placement asked again, once ----------
def _ask(calls):
    def ask(system, text):
        import json
        body = json.loads(text.split("EVIDENCE:\n", 1)[1])
        calls.append([c["symbol"] for c in body["companies"]])
        return {"models": {c["symbol"]: "property" for c in body["companies"]}}
    return ask


def test_unknown_models_with_descriptions_now_kept_are_asked_once_in_one_bounded_answer():
    about = {f"T{i}": "The company owns telecom towers and leases space on them to mobile operators for rent." for i in range(50)}
    about["T0"] = ""
    models = {f"T{i}": "unknown" for i in range(50)}
    models["T49"] = "capacity"
    ev = lambda s: about.get(s) or ""                     # noqa: E731
    calls = []
    out, _, conf, reasked = B.reask_unknown(models, {}, {}, [], list(models), about.get, {}, ev, _ask(calls), "Telecom")
    # gl50 (R50, updated on purpose): REASK_MAX a check (60), in answers of REASK_BATCH (20) each, never hundreds in one answer
    asked = [s for c in calls for s in c]
    assert all(len(c) <= B.REASK_BATCH for c in calls) and len(asked) == min(B.REASK_MAX, 48) and "T0" not in asked and "T49" not in asked
    assert all(out[s] == "property" and conf[s] for s in asked) and reasked == sorted(asked)
    n = len(calls)
    again = B.reask_unknown(out, {}, conf, reasked, list(models), about.get, {}, ev, _ask(calls), "Telecom")[3]
    assert not {s for c in calls[n:] for s in c} & set(asked) and set(again) >= set(reasked)
    calls.clear()
    B.reask_unknown(out, {}, conf, [f"T{i}" for i in range(50)], list(models), about.get, {}, ev, _ask(calls), "Telecom")
    assert calls == []                                    # every one asked before: never again


def test_a_placement_kept_under_the_rules_before_carries_over(monkeypatch):
    from app import computed
    seen = []

    def get(kind, key):
        seen.append(key[-1])
        return {"value": {"assign": {"X": {"layer": "L", "by": "ai"}}}} if key[-1] == T.PLACE_CARRY.get(B.RULES) else None
    monkeypatch.setattr(computed, "get", get)
    got = {}
    # tx2 (R45, updated on purpose): place_rest also takes the previous live layers (`previous`)
    monkeypatch.setattr(B, "place_rest", lambda out, theme, about, ask=None, kept=None, facts_of=None, carried=False, previous=None: (got.update(kept=kept), (out, kept))[1])
    T.placed("IN", "Telecom", {"generated_at": 1.0}, {"value_chain": []}, ask=None)
    # rv51 (R51, updated on purpose): once found, the walk goes on back for an earlier answer of the same map (at most EARLIER_MAX versions)
    assert seen[:2] == [B.RULES, T.PLACE_CARRY[B.RULES]] and got["kept"]["assign"]["X"]["layer"] == "L"
    assert len(seen) == 2 + T.EARLIER_MAX and len(seen) == len(set(seen))


# ---------- 5. a layer page's header ----------
def test_a_layer_header_says_how_many_are_in_the_figures():
    amt = lambda x: deck.money(x, "₹ crore")             # noqa: E731
    cos = [{"symbol": "A", "revenue": 32493.0}] + [{"symbol": s, "revenue": 900.0, "model_out": True} for s in "BCD"]
    assert deck.layer_head({"n": 1, "revenue": 32493.0}, cos, amt) == "4 companies (1 in the layer's calculations), revenue of those ₹32,493 cr"
    assert deck.layer_head({"n": 2, "revenue": 1800.0}, [{"symbol": "B", "revenue": 900.0}, {"symbol": "C", "revenue": 900.0}], amt) == "2 companies, revenue ₹1,800 cr together"


# ---------- 6. software product companies never sit in a services layer ----------
def test_no_licence_or_subscription_company_in_a_services_layer():
    region, m, f, models = it_mixed()
    mixed = copy.deepcopy(models)
    for v in m["value_chain"]:
        for c in (v.get("companies") or [])[:1]:
            mixed[c["ticker"]] = "software"
    vc = B.by_model(m["value_chain"], mixed, "IT services")
    for v in vc:
        if (v.get("model") or {}).get("family") == "services":
            assert not [c["ticker"] for c in v["companies"] if mixed.get(c["ticker"]) == "software"], v["layer"]


def test_a_kept_placement_asks_its_unknown_models_once_and_keeps_that_it_did():
    import json
    import pytest
    from app.intel import theme_check as C
    from tests.test_r21_deck import ABOUT, mapped

    def first(system, text):
        if system == C.MODEL_SYSTEM:
            return {"models": {}}
        return {"place": [{"symbol": "EL2", "layer": "L2"}, {"symbol": "MS2", "layer": "L0"}, {"symbol": "SH2", "layer": "L1"}, {"symbol": "XX1", "layer": "none"}],
                "models": {"EL2": "manufacturing"}}
    _, got = B.place_rest(mapped(), "Defence", ABOUT.get, ask=first)
    # R37 lane r2 (updated on purpose): Missile Two's own words state its model ("makes rocket propellants"); Ship Two's ("builds and repairs
    # naval ships") don't, so it is the one asked again
    assert got["models"]["MS2"] == "manufacturing" and "SH2" not in got["models"] and "reasked" not in got
    calls = []

    def later(system, text):
        assert system == C.MODEL_SYSTEM, "only the unknown models are asked"
        body = json.loads(text.split("EVIDENCE:\n", 1)[1])
        calls.append(sorted(c["symbol"] for c in body["companies"]))
        return {"models": {"MS2": "manufacturing", "SH2": "manufacturing"}}
    _, got2 = B.place_rest(mapped(), "Defence", ABOUT.get, ask=later, kept=got)
    assert len(calls) == 1 and "SH2" in calls[0] and "EL2" not in calls[0] and "MS2" not in calls[0]
    assert got2["models"]["SH2"] == "manufacturing" and set(got2["reasked"]) == set(calls[0])
    B.place_rest(mapped(), "Defence", ABOUT.get, ask=lambda s, t: pytest.fail("asked again"), kept=got2)


def test_a_placement_is_carried_back_past_versions_that_kept_none_of_their_own(monkeypatch):
    """R40 (the live Release 38 Utilities map): the version before kept no placement of its own (its own was carried), so the placement is
    looked for further back, never asked again from nothing; the placements of 39, asked again from nothing, are passed over."""
    from app import computed
    seen = []
    older = T.PLACE_CARRY[T.PLACE_CARRY[B.RULES]]

    def get(kind, key):
        seen.append(key[-1])
        return {"value": {"assign": {"X": {"layer": "L", "by": "ai"}}}} if key[-1] == older else None
    monkeypatch.setattr(computed, "get", get)
    got = {}
    # tx2 (R45, updated on purpose): place_rest also takes the previous live layers (`previous`)
    monkeypatch.setattr(B, "place_rest", lambda out, theme, about, ask=None, kept=None, facts_of=None, carried=False, previous=None:
                        (got.update(kept=kept, carried=carried), (out, kept))[1])
    T.placed("IN", "Utilities", {"generated_at": 1.0}, {"value_chain": []}, ask=None)
    # lane s2-exact bumped RULES to 41, carrying 40; lane s3-r40 to 42, carrying 41: found at 40 (updated on purpose)
    assert B.RULES == 50 and T.PLACE_CARRY[50] == 49 and T.PLACE_CARRY[49] == 48 and T.PLACE_CARRY[48] == 47 and T.PLACE_CARRY[47] == 46 and T.PLACE_CARRY[46] == 45 and T.PLACE_CARRY[45] == 44 and T.PLACE_CARRY[44] == 43 and T.PLACE_CARRY[43] == 42 and T.PLACE_CARRY[42] == 41 and T.PLACE_CARRY[41] == 40 and T.PLACE_CARRY[40] == 38 and 39 not in seen          # rv51 (R51): RULES 50, PLACE_CARRY[50] = 49 (updated on purpose); gl50 (R50): RULES 49, PLACE_CARRY[49] = 48, deck 60, dive text 20 (updated on purpose); ex49 (R49): RULES 48, PLACE_CARRY[48] = 47, deck 59, dive text 19, precise exclusion reasons, the business-model ranking rule (updated on purpose); cl48 (R48): RULES 47, PLACE_CARRY[47] = 46, deck 58, dive text 18, primary-business validation and the coverage control (updated on purpose); cv47 (R47): RULES 46, PLACE_CARRY[46] = 45, filing titles are no words of a company's own, the AI's industry pick kept across rules changes (PICK_RULES); deck and dive text unchanged (updated on purpose); tx2 (R45/R46): RULES 45, PLACE_CARRY[45] = 44, deck 57 (dive text stays 16), the taxonomy regression guard and the screening populations (updated on purpose); c1 (R44): RULES 44, PLACE_CARRY[44] = 43, deck 56, dive text 16 (55 and 15 are R44.1's), classification coverage from evidence (updated on purpose); lane d1: RULES 43, PLACE_CARRY[43] = 42, deck 53, dive text 12 (the outside review of the live R41 decks, updated on purpose); lane s3-r40: RULES 42, deck 50, dive text 10 (updated on purpose)
    assert seen[:3] == [50, 49, 48] and got["kept"]["assign"]["X"]["layer"] == "L" and got["carried"] is True          # rv51 (R51): RULES 50, found at 48, then the walk back for an earlier answer (updated on purpose); gl50 (R50): RULES 49, PLACE_CARRY[49] = 48, deck 60, dive text 20 (updated on purpose); ex49 (R49): from 48 (updated on purpose); cl48 (R47): from 47 (updated on purpose); cv47 (R46): from 46 (updated on purpose); tx2 (R45): from 45 (updated on purpose); c1 (R44): from 44 (updated on purpose); lane d1: from 43


def test_the_carry_back_stops_when_no_version_kept_a_placement(monkeypatch):
    from app import computed
    seen = []
    monkeypatch.setattr(computed, "get", lambda kind, key: seen.append(key[-1]) or None)
    # tx2 (R45, updated on purpose): place_rest also takes the previous live layers (`previous`)
    monkeypatch.setattr(B, "place_rest", lambda out, theme, about, ask=None, kept=None, facts_of=None, carried=False, previous=None: (out, kept))
    T.placed("IN", "Utilities", {"generated_at": 1.0}, {"value_chain": []}, ask=None)
    assert seen[0] == B.RULES and seen[-1] == min(T.PLACE_CARRY.values()) and len(seen) == len(set(seen))
