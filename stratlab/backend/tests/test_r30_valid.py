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
                x["debt"] = x["years"][-1]["sales"] * k
    return region, m, f, market


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
    assert deck_of(region, m, f)[0]["chain"]["highest"]


def test_capital_per_revenue_and_the_threefold_rule(monkeypatch):
    # R31: a test of the ranking rules on fixtures of 3 or 4 companies a layer, run at the marks' floor (COMPARE_MIN); the headline floor
    # of 5 (HEADLINE_MIN) on the same fixtures is tested in tests/test_r31_bound.py
    monkeypatch.setattr("app.intel.theme_data.HEADLINE_MIN", 3)
    assert D.capital_per_revenue(1000, 2.0, 500, None, 1000) == 1.0         # equity 500 + debt 500 over revenue 1,000
    assert D.capital_per_revenue(None, None, 600, 2.0, 300) == 3.0          # equity from debt over debt to equity
    assert D.capital_per_revenue(1000, -1.0, None, None, 1000) is None and D.capital_per_revenue(1000, 2.0, 0, None, 0) is None
    rows = [("A", 30.0, 3, 3, None, "full", 0.5), ("B", 10.0, 3, 3, None, "full", 1.4)]
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
    assert r["net"] is None and not r["one_off"] and r["roe"] is None
    assert r["held"]["net"]["value"] == 82.2
    assert r["held"]["net"]["checks"] == [D.CHECKS["sign"], D.CHECKS["net_unusual"]]
    assert r["held"]["roe"]["checks"] == [D.CHECKS["neg_equity"]]


def test_other_income_sign_and_ebitda_checks():
    r = _row(profits=[1, 1, 1, 9000], roce=5.0, other_income=6000)         # 20% net, of which income outside operations is two thirds
    assert r["net"] is None and r["held"]["net"]["checks"] == [D.CHECKS["other_income"]]
    assert _row(profits=[1, 1, 1, 9000], roce=5.0, other_income=1000)["net"] == 20.0
    r = _row(profits=[1, 1, 1, 9000], roce=5.0, net_margin=-4.0)
    assert r["held"]["net"]["checks"] == [D.CHECKS["sign_page"]]
    a, b = {"symbol": "A", "ebitda": 95.0}, {"symbol": "B", "ebitda": 95.0}
    D.validate_model(a, "services")
    D.validate_model(b, "royalties")
    assert a["ebitda"] is None and a["held"]["ebitda"]["checks"] == [D.CHECKS["ebitda_unusual"]] and b["ebitda"] == 95.0


def test_a_held_figure_leaves_medians_and_is_named_on_the_data_confidence_page():
    region, m, f, market = S.telecom_in()
    sym = m["value_chain"][0]["companies"][0]["ticker"]
    f[sym].update(roce=-1.7, book_value=-3.3)
    f[sym]["years"][-1]["profit"] = f[sym]["years"][-1]["sales"] * 0.77
    v, slides = deck_of(region, m, f, index_rows=lambda: market)
    held = v["checks"]["held"]
    assert [x["key"] for x in held if x["symbol"] == sym] == ["net", "roe"]
    lay = v["layers"][0]
    assert all(c.get("net") != 77.0 for c in lay["companies"]) and lay["stats"]["net"]["n"] == len(lay["companies"]) - 1
    conf = next(s for s in slides if s.title == "Data confidence")
    row = next(r for b in conf.blocks if b["kind"] == "table" for r in b["rows"] if r[0] == "Figure checks")
    assert "net margin 77%" in row[1] and D.CHECKS["sign"] in row[1] and deck.ANOMALY_WHY in row[2]
    assert not any(w in row[1] + row[2] for w in ("because", "due to", "one-off gain"))


# ---------- 3. coverage: one table, four kinds ----------
def test_every_synthetic_deck_has_the_coverage_table_and_it_reconciles():
    for name, v, slides in S.decks():
        conf = next(s for s in slides if s.title == "Data confidence")
        tab = next(b for b in conf.blocks if b["kind"] == "table" and b.get("head") == deck.COVERAGE_HEAD)
        kinds = [r[0] for r in tab["rows"]]
        assert kinds[0] == "Companies, by count" and "Each figure" in kinds and "Each layer" in kinds, name
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
    assert len(calls) == 1 and len(calls[0]) == B.REASK_MAX and "T0" not in calls[0] and "T49" not in calls[0]
    assert all(out[s] == "property" and conf[s] for s in calls[0]) and reasked == sorted(calls[0])
    again = B.reask_unknown(out, {}, conf, reasked, list(models), about.get, {}, ev, _ask(calls), "Telecom")[3]
    assert len(calls) == 2 and not set(calls[1]) & set(calls[0]) and set(again) >= set(reasked)
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
    monkeypatch.setattr(B, "place_rest", lambda out, theme, about, ask=None, kept=None, facts_of=None: (got.update(kept=kept), (out, kept))[1])
    T.placed("IN", "Telecom", {"generated_at": 1.0}, {"value_chain": []}, ask=None)
    assert seen == [B.RULES, B.RULES - 1] and got["kept"]["assign"]["X"]["layer"] == "L"


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
    assert got["models"] and "MS2" not in got["models"] and "reasked" not in got
    calls = []

    def later(system, text):
        assert system == C.MODEL_SYSTEM, "only the unknown models are asked"
        body = json.loads(text.split("EVIDENCE:\n", 1)[1])
        calls.append(sorted(c["symbol"] for c in body["companies"]))
        return {"models": {"MS2": "manufacturing", "SH2": "manufacturing"}}
    _, got2 = B.place_rest(mapped(), "Defence", ABOUT.get, ask=later, kept=got)
    assert len(calls) == 1 and "MS2" in calls[0] and "EL2" not in calls[0]
    assert got2["models"]["MS2"] == "manufacturing" and set(got2["reasked"]) == set(calls[0])
    B.place_rest(mapped(), "Defence", ABOUT.get, ask=lambda s, t: pytest.fail("asked again"), kept=got2)
