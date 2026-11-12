"""Release 28 fixes (the owner's review of the live R27 decks), generic, on the synthetic sets:

  1. the four counts nest: with figures <= confirmed <= considered, every calculation's count <= with figures ("confirmed 59 (of 60 checked) ·
     with figures 60" counted an unconfirmed company among those with figures); the publication gate fails a deck whose counts don't nest
  2. a layer with one confirmed company has no page of its own: one row of the "Smaller layers" page after the layer pages, in the value
     chain's order; it stays in the value chain's table
"""
import pytest

from app import deck
from tests.synthetic_themes_r27 import THEMES, ai_map, co
from tests.test_export import plain, table_of, texts
from tests.test_r18_deck import deck_of
from tests.test_r20_deck import test_every_rule_holds_on_every_synthetic_theme as every_rule  # noqa: F401 (used as a helper)
from tests.test_r25_deck import EVERY
from tests.test_theme1 import facts


def with_unconfirmed(fn):
    """A synthetic theme with one more company in its first layer: from another industry, its own words showing other work, with figures
    (status "unverified": listed, never in the figures)."""
    region, m, f, market = fn()
    vc = [dict(x) for x in m["value_chain"]]
    vc[0]["companies"] = list(vc[0]["companies"]) + [co("XUNV", "Hotel Stays Ltd", "operates hotels and restaurants", "Hotels", base=False, verified=False)]
    p = m["placements"]
    m = {**m, "value_chain": vc, "placements": {**p, "placed": p["placed"] + 1, "total": p["total"] + 1, "added": p.get("added", 0) + 1}}
    unit = next(iter(f.values()))
    f = {**f, "XUNV": {**facts("XUNV", "Hotel Stays Ltd", [900, 950, 1000, 1100], [20, 21, 22, 23], [90, 95, 100, 110], cap=5000, industry=("Hotels",)),
                       "region": unit.get("region", "IN"), "unit": unit.get("unit", "₹ crore")}}
    return region, m, f, market


UNCONFIRMED = []
for _name, _fn in THEMES:
    _r, _m, _f, _mk = with_unconfirmed(_fn)
    _v, _s = deck_of(_r, _m, _f, index_rows=(lambda mk=_mk: mk))
    UNCONFIRMED.append((_name + " + unconfirmed", _v, _s))


def nest(c: dict) -> None:
    confirmed = c["confirmed"] if c["confirmed"] is not None else c["counted"]
    assert c["with_figures"] <= confirmed <= c["considered"], c
    assert all(k <= c["with_figures"] for _, k in c["each"]), c


# ---------- 1. the four counts nest ----------
@pytest.mark.parametrize("name,v,slides", UNCONFIRMED, ids=[n for n, _, _ in UNCONFIRMED])
def test_an_unconfirmed_company_with_figures_is_never_counted_with_figures(name, v, slides):
    assert v["status"]["XUNV"] == "unverified" and v["membership"]["not_confirmed"] >= 1
    cov = deck.coverage(v)
    c = deck.reconciled_counts(v, cov)
    nest(c)
    assert c["with_figures"] == v["members_with_figures"] == v["with_figures"]           # one count: the confirmed companies with figures
    assert deck.counts_flags(c) == []
    gate = {x["id"]: x for x in slides[0].gate["items"]}
    assert gate["reconcile"]["ok"], slides[0].gate["dropped"]
    words = deck.counts_words(c)
    assert f"with figures {c['with_figures']:,}" in texts(slides) and words in texts(slides)
    every_rule(name, v, slides)


@pytest.mark.parametrize("name,v,slides", EVERY, ids=[n for n, _, _ in EVERY])
def test_the_four_counts_nest_on_every_synthetic_theme_and_benchmark_family(name, v, slides):
    c = deck.reconciled_counts(v, deck.coverage(v))
    nest(c)
    assert deck.counts_flags(c) == []


def test_a_dive_kept_from_before_that_counted_unconfirmed_companies_with_figures_says_the_confirmed_count():
    name, v, _ = UNCONFIRMED[0]
    old = {**v, "with_figures": v["members_with_figures"] + 1}           # as a dive built under R27 counted it
    assert deck.coverage(old)["n"] == v["members_with_figures"]


def test_counts_that_dont_nest_fail_the_gate():
    assert deck.counts_flags({"considered": 15, "confirmed": 14, "with_figures": 15, "each": [("net margin", 14)]}) == ["with figures 15 above confirmed 14"]
    assert deck.counts_flags({"considered": 66, "confirmed": 55, "with_figures": 55, "each": [("P/E", 56)]}) == ["P/E 56 above with figures 55"]
    assert deck.counts_flags({"considered": 10, "confirmed": None, "counted": 8, "with_figures": 8, "each": []}) == []
    name, v, slides = UNCONFIRMED[0]
    bad = {**v, "membership": {**v["membership"], "confirmed": v["members_with_figures"] - 1}}
    g = deck.publication_gate(slides, bad)
    rec = next(x for x in g["items"] if x["id"] == "reconcile")
    assert not rec["ok"] and any(d["rule"] == "reconcile" and "above confirmed" in d["text"] for d in g["dropped"])


# ---------- 2. one-company layers: one "Smaller layers" page ----------
def small_layers_theme():
    """An AI map: two layers of three companies, two of one company (one with an unconfirmed company beside it), in that order."""
    spec = [("Formulation makers", "FM", 3, "makes branded generic formulations"), ("Biosimilar developers", "BS", 1, "develops and sells biosimilar insulin"),
            ("Bulk drug makers", "BD", 3, "manufactures active pharmaceutical ingredients"), ("Animal health makers", "AH", 1, "makes veterinary vaccines and medicines")]
    layers, f = {}, {}
    for layer, p_, n, what in spec:
        cos = [co(f"{p_}{i}", f"{layer.split()[0]} Pharma {i} Ltd", what, "Pharmaceuticals") for i in range(n)]
        layers[layer] = cos
        for i, c in enumerate(cos):
            f[c["ticker"]] = facts(c["ticker"], c["name"], [1000, 1100, 1200, 1300 + i * 50], [18, 19, 20, 21 + i], [100, 110, 120, 130 + i * 5],
                                   cap=50000 - len(f) * 3000, pe=30.0 - i, industry=("Healthcare", "Pharmaceuticals"))
    layers["Animal health makers"].append(co("XHOT", "Hotel Stays Ltd", "operates hotels and restaurants", "Hotels", base=False, verified=False))
    f["XHOT"] = facts("XHOT", "Hotel Stays Ltd", [900, 950, 1000, 1100], [20, 21, 22, 23], [90, 95, 100, 110], cap=4000, industry=("Hotels",))
    m = ai_map(layers, "Pharmaceuticals", "Formulation, bulk drug, biosimilar and animal health makers.")
    return "IN", m, f


def test_a_layer_with_one_confirmed_company_is_a_row_of_one_smaller_layers_page_after_the_layer_pages():
    v, slides = deck_of(*small_layers_theme())
    titles = [s.title for s in slides]
    layer_pages = [t for t in titles if t.startswith("Layer ")]
    assert layer_pages == ["Layer 1 · Formulation makers", "Layer 2 · Bulk drug makers"]             # numbered without a gap
    assert titles.count("Smaller layers") == 1 and titles.index("Smaller layers") == titles.index(layer_pages[-1]) + 1
    t = table_of(slides, "Smaller layers")
    assert t["head"][:3] == ["Layer", "Company", "What it does"] and "Revenue" in t["head"] and "EBITDA margin" in t["head"]
    rows = plain(t["rows"])
    assert [r[0] for r in rows] == ["Biosimilar developers", "Animal health makers"]                 # the value chain's order, never ranked
    assert rows[0][1] == "Biosimilar Pharma 0 Ltd" and "biosimilar" in rows[0][2].lower()
    assert rows[1][1].startswith("Animal Pharma 0 Ltd") and "not confirmed: Hotel Stays Ltd" in rows[1][1]
    assert all(r[t["head"].index("Revenue")] not in ("", "–") for r in rows)
    chain = [r[0] for r in table_of(slides, "The value chain by layer")["rows"]]
    assert {"Biosimilar developers", "Animal health makers", "Formulation makers", "Bulk drug makers"} <= set(chain)   # kept in the table
    small = next(s for s in slides if s.title == "Smaller layers")
    for word in ("highest", "lowest", "largest", "smallest", "fastest", "slowest", "rank"):
        assert word not in (small.subtitle or "").lower() + " ".join(str(c) for r in rows for c in r).lower()
    every_rule("smaller layers (IN)", v, slides)
    assert slides[0].checked == [] and deck.check_deck(slides) == []


# ---------- 3. the companies to place carry their own descriptions (bounded) ----------
def _place_map(n_rest=90):
    own = {"layer": "Engineering R&D services", "description": "", "companies": [{"ticker": "AI0", "name": "Named Co", "cap": 9e5}]}
    rest = {"layer": "IT - Software", "official": True, "basis": "industry",
            "companies": [{"ticker": f"SM{i:03d}", "name": f"Small {i}", "cap": 1000.0 * (n_rest - i)} for i in range(n_rest)]}
    return {"sector": "IT services", "value_chain": [own, rest]}


def test_the_companies_to_place_get_their_descriptions_read_once_largest_first_and_bounded(monkeypatch):
    from app.intel import theme_routes as TR
    stored = {"SM000", "SM002"}                                  # already kept: never read again
    asked = []
    monkeypatch.setattr(TR, "_has_description", lambda region, s: s in stored)
    monkeypatch.setattr(TR, "evidence_reader", lambda region, names: (lambda syms: asked.extend(syms) or ({}, set())))
    out = _place_map()
    got = TR.describe_unplaced("IN", out, {}, {"assign": {"SM001": {"layer": "Engineering R&D services", "by": "ai"}}})
    assert got == asked and len(got) == TR.PLACE_READS                                    # at most PLACE_READS a theme check
    assert got[:3] == ["SM003", "SM004", "SM005"]                                          # largest first; kept and placed ones skipped
    assert not {"SM000", "SM001", "SM002"} & set(got)
    assert TR.describe_unplaced("IN", {"value_chain": out["value_chain"][1:]}, {}, None) == []        # no layer of the map's own: nothing to place
    every = {"assign": {c["ticker"]: {"layer": "", "by": "words"} for c in out["value_chain"][1]["companies"]}}
    asked.clear()
    assert TR.describe_unplaced("IN", out, {}, every) == [] and asked == []               # a placement already kept: nothing read


def test_a_description_looked_for_lately_and_not_found_is_not_read_again(monkeypatch):
    from datetime import datetime, timedelta, timezone

    from app.intel import theme_routes as TR
    now = datetime.now(timezone.utc)
    rows = {"theme:evidence:IN:A": {"at": now.isoformat(), "about": "Makes software."},
            "theme:evidence:IN:B": {"at": now.isoformat(), "about": ""},
            "theme:evidence:IN:C": {"at": (now - timedelta(days=TR.NO_DESCRIPTION_DAYS + 1)).isoformat(), "about": ""}}
    monkeypatch.setattr(TR.db, "get_setting", lambda k: rows.get(k))
    monkeypatch.setattr(TR.db, "json_value", lambda v, d: v if v is not None else d)
    monkeypatch.setattr(TR, "EVIDENCE_CACHE", TR.TTLCache(max_items=10, max_bytes=10_000))      # nothing from an earlier test
    assert TR._has_description("IN", "A") and TR._has_description("IN", "B")
    assert not TR._has_description("IN", "C") and not TR._has_description("IN", "D")


def test_a_request_never_reads_descriptions_to_place_only_the_background_check_does(monkeypatch):
    from app.intel import theme_base as B
    from app.intel import theme_routes as TR
    calls = []
    monkeypatch.setattr(TR, "describe_unplaced", lambda *a, **k: calls.append(a) or [])
    monkeypatch.setattr(B, "place_rest", lambda out, theme, about, ask=None, kept=None, facts_of=None, carried=False: (out, {}))
    m = {"sector": "IT services", "generated_at": 1.0}
    TR.placed("IN", "IT services", m, _place_map(), ask=None)
    assert calls == []
    TR.placed("IN", "IT services", m, _place_map(), ask=lambda *a: {})
    assert len(calls) == 1


def test_the_how_they_earn_line_counts_the_companies_the_page_shows():
    """R28: the live R27 IT deck said "shown for only 6 of these 46 companies" on a page of 6 companies; the line now counts what is shown."""
    from app.intel.theme_base import shown_model
    model = {"id": "project_services", "family": "services", "known": 6, "of": 46, "out": 40, "sparse": True,
             "line": "How they earn is shown for only 6 of these 46 companies, mainly fees; the other 40 are listed but left out."}
    rows = [{"symbol": f"S{i}", "model": "project_services", "model_tags": [], "model_confidence": "high"} for i in range(4)] + \
           [{"symbol": "U1", "model": "", "model_tags": [], "model_confidence": "", "model_out": True}]
    got = shown_model(model, rows)
    assert got["of"] == 5 and got["known"] == 4 and got["out"] == 1 and not got.get("sparse")
    assert "46" not in got["line"] and got["line"].startswith("They earn mainly from ") and "1 of 5 is listed but left out" in got["line"]
    same = shown_model({**model, "of": 5}, rows)
    assert same["line"] == model["line"]                  # counts already agree: unchanged
    none = shown_model(model, [{"symbol": "U", "model": "", "model_out": True}] * 3)
    assert none["sparse"] and none["line"].startswith("None of these 3 companies")
