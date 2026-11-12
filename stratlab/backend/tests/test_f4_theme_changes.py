"""f4: a theme's change log ("What changed") and its Excel workbook. The log sets each stored read of a theme against the one stored before
it (companies added, removed with the stated reason, moved between layers; layers renamed, split or merged; latest-year figures restated),
dated, bounded, in the settings store; Free sees the latest refresh's counts and first rows, Basic the whole log. The workbook has a sheet
for each table of the page and deck, numbers as numbers with their formats, and is Basic and up, counted as the theme's deck of the month."""
import copy
import io
import json
from datetime import date, datetime, timezone

import pytest

from app import db, xlsx_write
from app.intel import theme_changes as TC
from app.intel import theme_data as D
from app.intel import theme_workbook as W
from tests.test_theme1 import CHECKED, FACTS, LAYERS, TODAY, facts

import openpyxl  # noqa: E402  (the test reader only: the CI installs it beside pytest, tests.yml; the app writes with xlsx_write)


def dive_of(checked=CHECKED, extra=None, changed=None):
    f = {**FACTS, **(extra or {}), **(changed or {})}
    return D.build("IN", "Test theme", checked, D.Sources(TODAY, facts=f.get, index_rows=lambda: [{"symbol": "X", "pe": 20.0}]))


def snap(dive, members=None, stamp=1, rules=43):
    members = members if members is not None else [c["symbol"] for b in dive["layers"] for c in b["companies"]]
    return TC.snapshot(dive, members, stamp, rules)


def with_layers(layers, placements=None):
    return {**CHECKED, "value_chain": layers, **({"placements": placements} if placements else {})}


def co(sym, name, what="does it"):
    return {"name": name, "ticker": sym, "what": what}


# ---------- the diff ----------
def test_companies_added_removed_with_the_stated_reason_moved_and_restated():
    v1 = dive_of()
    # v2: Mine B moved to Cells; Cell B dropped as another business (named on the coverage with its industry); Reliance no longer in the
    # map; a new miner; Mine A's latest year restated (revenue 1500 -> 1600)
    mines = {**LAYERS[0], "companies": [co("MINEA", "Mine A"), co("NEWMIN", "New Mine")]}
    cells = {**LAYERS[1], "companies": [co("CELLA", "Cell A"), co("MINEB", "Mine B")]}
    placements = {**CHECKED["placements"], "off_industry": [{"ticker": "CELLB", "name": "Cell B", "industry": "Solar Panels"}]}
    restated = facts("MINEA", "Mine A", [1000, 1100, 1300, 1600], [40, 42, 45, 50], [200, 220, 280, 360], cap=40000, pe=12)
    v2 = dive_of(with_layers([mines, cells], placements), extra={"NEWMIN": facts("NEWMIN", "New Mine", [10, 20, 30, 40], [5, 6, 7, 8], [1, 2, 3, 4])},
                 changed={"MINEA": restated})
    v2["placements"] = placements                  # as theme_routes.dive_of puts the checked map's placements on the dive
    d = TC.diff(snap(v1), snap(v2))
    assert d["counts"] == {"removed": 2, "added": 1, "moved": 1, "layers": 0, "restated": 1}
    assert d["added"] == [{"symbol": "NEWMIN", "name": "New Mine", "layer": "Mining"}]
    assert d["removed"] == [{"symbol": "CELLB", "name": "Cell B", "layer": "Cells", "why": "another business (filed under Solar Panels)"},
                            {"symbol": "RELIANCE", "name": "Reliance Industries", "layer": "Cells", "why": "no longer in the theme's map"}]
    assert d["moved"] == [{"symbol": "MINEB", "name": "Mine B", "from": "Mining", "to": "Cells"}]
    r = d["restated"][0]
    assert (r["symbol"], r["year"], r["revenue"], r["what"]) == ("MINEA", "Mar 2026", [1500.0, 1600.0], ["revenue"])


def test_a_company_still_in_the_map_but_without_figures_says_so():
    v1 = dive_of()
    v2 = dive_of(changed={"MINEB": None})
    d = TC.diff(snap(v1), snap(v2, members=["MINEA", "MINEB", "CELLA", "CELLB", "RELIANCE"]))
    assert d["removed"] == [{"symbol": "MINEB", "name": "Mine B", "layer": "Mining", "why": "no figures stored for it"}]


def test_small_moves_and_a_new_year_are_not_restatements():
    v1 = dive_of()
    small = facts("MINEA", "Mine A", [1000, 1100, 1300, 1515], [40, 42, 45, 50.8], [200, 220, 280, 360], cap=40000, pe=12)   # +1%, +0.8 points
    assert TC.diff(snap(v1), snap(dive_of(changed={"MINEA": small})))["counts"]["restated"] == 0
    margin = facts("MINEA", "Mine A", [1000, 1100, 1300, 1500], [40, 42, 45, 52], [200, 220, 280, 360], cap=40000, pe=12)       # +2 points
    r = TC.diff(snap(v1), snap(dive_of(changed={"MINEA": margin})))["restated"]
    assert [(x["what"], x["margin"], x["measure"]) for x in r] == [(["margin"], [50.0, 52.0], "EBITDA margin")]
    was = snap(v1)
    was["cos"]["MINEA"][2] = "Mar 2025"                       # the stored read was of the year before: a new year, not a restatement
    assert TC.diff(was, snap(dive_of(changed={"MINEA": margin})))["counts"]["restated"] == 0


def test_a_layer_renamed_is_one_change_not_a_move_of_each_company():
    v1 = dive_of()
    v2 = dive_of(with_layers([{**LAYERS[0], "layer": "Metal mining"}, LAYERS[1]]))
    d = TC.diff(snap(v1), snap(v2))
    assert d["layers"] == [{"kind": "renamed", "from": ["Mining"], "to": ["Metal mining"], "n": 2}] and d["moved"] == []


def test_a_layer_split_and_two_layers_merged():
    v1 = dive_of()
    split = [LAYERS[0], {**LAYERS[1], "layer": "Cell makers", "companies": LAYERS[1]["companies"][:2]},
             {"layer": "Groups", "description": "Groups.", "companies": [LAYERS[1]["companies"][2]]}]
    d = TC.diff(snap(v1), snap(dive_of(with_layers(split))))
    assert d["layers"] == [{"kind": "split", "from": ["Cells"], "to": ["Cell makers", "Groups"], "n": 3}] and d["moved"] == []
    merged = [{"layer": "Everything", "description": "All.", "companies": LAYERS[0]["companies"] + LAYERS[1]["companies"]}]
    d = TC.diff(snap(v1), snap(dive_of(with_layers(merged))))
    assert d["layers"] == [{"kind": "merged", "from": ["Mining", "Cells"], "to": ["Everything"], "n": 5}] and d["moved"] == []


def test_a_layer_added_or_removed():
    v1 = dive_of()
    one = [{**LAYERS[0], "companies": LAYERS[0]["companies"] + LAYERS[1]["companies"]}]
    d = TC.diff(snap(v1), snap(dive_of(with_layers(one))))
    assert d["layers"] == [{"kind": "removed", "from": ["Cells"], "to": [], "n": 3}] and len(d["moved"]) == 3


# ---------- the stored log ----------
def test_the_first_read_keeps_a_snapshot_an_unchanged_one_no_entry_and_a_change_a_dated_entry():
    s1 = snap(dive_of())
    at = datetime(2026, 11, 12, 6, tzinfo=timezone.utc)
    cur = TC.apply(None, s1, at=at)
    assert cur["log"] == [] and cur["since"] == "2026-11-12"
    assert TC.apply(cur, s1, refresh=True, at=at)["log"] == []
    v2 = dive_of(with_layers([{**LAYERS[0], "layer": "Metal mining"}, LAYERS[1]]))
    out = TC.apply(cur, snap(v2), refresh=True, at=at)
    e = out["log"][-1]
    assert (e["d"], e["cause"], e["counts"]["layers"]) == ("2026-11-12", "refresh", 1)
    assert TC.apply(cur, snap(v2, stamp=2), at=at)["log"][-1]["cause"] == "map"
    assert TC.apply(cur, snap(v2, rules=44), at=at)["log"][-1]["cause"] == "rules"
    assert TC.apply(cur, snap(v2), at=at)["log"][-1]["cause"] == "figures"


def test_the_log_is_bounded():
    s1, s2 = snap(dive_of()), snap(dive_of(with_layers([{**LAYERS[0], "layer": "Metal mining"}, LAYERS[1]])))
    cur = TC.apply(None, s1)
    for i in range(TC.KEEP + 5):
        cur = TC.apply(cur, s2 if i % 2 == 0 else s1)
    assert len(cur["log"]) == TC.KEEP
    big = {"layers": ["A"], "cos": {f"S{i}": [f"S{i}", 0, None, None, None, ""] for i in range(400)}, "off": {}, "map": [], "stamp": 1, "rules": 1}
    out = TC.apply(TC.apply(None, {**big, "cos": {}}), big)
    e = out["log"][-1]
    assert e["counts"]["added"] == 400 and len(e["added"]) == TC.ROWS_KEEP


@pytest.fixture
def store(monkeypatch):
    kept: dict = {}
    monkeypatch.setattr(db, "get_setting", lambda k: kept.get(k))
    monkeypatch.setattr(db, "update_setting", lambda k, fn: kept.__setitem__(k, fn(kept.get(k))) or kept[k])
    return kept


def test_record_and_the_view_by_plan(store):
    v1 = dive_of()
    TC.record("IN", "Test theme", v1, [c["symbol"] for b in v1["layers"] for c in b["companies"]], 1, 43)
    assert list(store) == ["theme:changes:IN:test"]           # the theme's normalised name ("theme" is a filler word)
    mines = {**LAYERS[0], "companies": [co("MINEA", "Mine A")]}
    v2 = dive_of(with_layers([mines, LAYERS[1]]))          # Mine B leaves the map
    TC.record("IN", "Test theme", v2, ["MINEA", "CELLA", "CELLB", "RELIANCE"], 1, 43, refresh=True)
    v3 = dive_of(with_layers([{**mines, "layer": "Miners"}, {**LAYERS[1], "companies": LAYERS[1]["companies"] + [co("MINEB", "Mine B")]}]))
    TC.record("IN", "Test theme", v3, ["MINEA", "MINEB", "CELLA", "CELLB", "RELIANCE"], 2, 43)
    full = TC.view("IN", "test THEME", True)                # however the theme is written
    assert full["full"] and [e["cause"] for e in full["entries"]] == ["map", "refresh"]          # newest first
    short = TC.view("IN", "Test theme", False)
    assert not short["full"] and short["older"] == 1 and len(short["entries"]) == 1
    assert short["entries"][0]["counts"] == full["entries"][0]["counts"]
    assert sum(len(short["entries"][0][k]) for k in TC.KINDS) <= TC.FREE_ROWS
    assert TC.served("IN", "Test theme", {"x": 1}, {"_plan": "basic"})["changes"]["full"] is True
    assert TC.served("IN", "Test theme", {"x": 1}, {"_plan": "free"})["changes"]["full"] is False


def test_the_free_view_keeps_five_rows_and_counts_the_rest():
    e = {"counts": {"removed": 3, "added": 4, "moved": 0, "layers": 0, "restated": 0},
         "removed": [{"symbol": str(i)} for i in range(3)], "added": [{"symbol": f"a{i}"} for i in range(4)], "moved": [], "layers": [], "restated": []}
    s = TC._short(e, TC.FREE_ROWS)
    assert len(s["removed"]) == 3 and len(s["added"]) == 2 and s["hidden"] == 2


def test_a_broken_store_never_breaks_the_page(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("down")
    monkeypatch.setattr(db, "update_setting", boom)
    monkeypatch.setattr(db, "get_setting", boom)
    TC.record("IN", "Test theme", dive_of(), ["MINEA"], 1, 43)
    assert TC.view("IN", "Test theme", True) == {"full": True, "since": None, "entries": [], "older": 0}


# ---------- the workbook ----------
def book(dive, region="IN", log=None):
    data = W.build(dive, region, "Test theme", log or {"entries": [], "since": None}, date(2026, 11, 12))
    return openpyxl.load_workbook(io.BytesIO(data))


def rows_of(ws):
    return [list(r) for r in ws.iter_rows(values_only=True)]


def test_the_workbook_has_a_sheet_for_each_table_and_numbers_as_numbers():
    v = dive_of()
    wb = book(v)
    assert wb.sheetnames == ["Companies", "Layer medians", "Peers", "Valuation", "Operating figures", "What changed", "Sources and method"]
    ws = wb["Companies"]
    head = rows_of(ws)[0]
    assert head[:7] == ["Company", "Symbol", "Layer", "In the layer's figures", "Market value (₹ crore)", "Year of the figures", "Revenue (₹ crore)"]
    body = {r[1]: dict(zip(head, r)) for r in rows_of(ws)[1:]}
    assert set(body) == set(FACTS)
    a = body["MINEA"]
    assert (a["Layer"], a["Market value (₹ crore)"], a["Revenue (₹ crore)"], a["EBITDA margin"], a["P/E"]) == ("Mining", 40000, 1500, 0.5, 12)
    assert body["RELIANCE"]["In the layer's figures"] == "Yes"
    assert isinstance(a["Price date"], datetime) and a["Price date"].date() == date(2026, 10, 5)
    col = {h: i + 1 for i, h in enumerate(head)}
    row = 1 + 1 + [r[1] for r in rows_of(ws)[1:]].index("MINEA")
    from app.deck import INDIAN_FORMAT
    assert ws.cell(row, col["Revenue (₹ crore)"]).number_format == INDIAN_FORMAT          # the decks' Indian grouping for rupees
    assert ws.cell(row, col["EBITDA margin"]).number_format == "0.0%"
    assert ws.cell(row, col["P/E"]).number_format == '0.0"x"'
    assert ws.cell(row, col["Price date"]).number_format == "d mmm yyyy"
    assert ws.cell(1, 1).font.b                                                             # the header bold


def test_the_layer_medians_peers_and_valuation_are_the_dive_s_own_numbers():
    v = dive_of()
    wb = book(v)
    lm = rows_of(wb["Layer medians"])
    head = lm[0]
    mining = dict(zip(head, lm[1]))
    assert mining["Layer"] == "Mining" and mining["EBITDA margin, median"] == pytest.approx(0.49) and mining["In its figures"] == 2
    assert lm[-1][0] == "The whole theme" and lm[-1][2] == v["members"]
    val = rows_of(wb["Valuation"])
    pe = next(r for r in val if r[0] == "P/E" and r[1] == "The theme")
    assert pe[2] == v["sections"]["valuation"]["pe"]["median"] and pe[5] == v["sections"]["valuation"]["pe"]["n"]
    assert any(r[1] == "Layer: Cells" for r in val)
    assert [r[0] for r in rows_of(wb["Peers"])[1:]] == ["P/E", "Revenue growth, 3 years a year", "ROCE"]
    method = dict((r[0], r[1]) for r in rows_of(wb["Sources and method"])[1:])
    assert "How a layer's median is built" in method and isinstance(method["Prices to the close of"], datetime)
    assert method["Figures"] == v["basis"] and "Indian way" in method["Money"]


def test_a_us_workbook_is_in_dollars_without_indian_grouping():
    v = {**dive_of(), "region": "US", "unit": "$ million"}
    ws = book(v, "US")["Companies"]
    head = rows_of(ws)[0]
    assert "Revenue ($ million)" in head and "Market value ($ million)" in head
    assert ws.cell(2, head.index("Revenue ($ million)") + 1).number_format == "#,##0"


def test_the_workbook_holds_the_change_log():
    s1 = snap(dive_of())
    cur = TC.apply(None, s1, at=datetime(2026, 11, 1, tzinfo=timezone.utc))
    margin = facts("MINEA", "Mine A", [1000, 1100, 1300, 1500], [40, 42, 45, 52], [200, 220, 280, 360], cap=40000, pe=12)
    v2 = dive_of(with_layers([{**LAYERS[0], "layer": "Metal mining"}, LAYERS[1]]), changed={"MINEA": margin})
    cur = TC.apply(cur, snap(v2), refresh=True, at=datetime(2026, 11, 12, tzinfo=timezone.utc))
    log = {"entries": cur["log"][::-1], "since": cur["since"]}
    ws = book(v2, log=log)["What changed"]
    rows = rows_of(ws)
    kinds = {r[2]: r for r in rows[1:]}
    assert set(kinds) == {"Layer renamed", "Figures restated"}
    assert kinds["Layer renamed"][5:7] == ["Mining", "Metal mining"] and kinds["Layer renamed"][1] == "Refresh"
    r = kinds["Figures restated"]
    assert r[3] == "Mine A" and r[8] == "Mar 2026" and (r[11], r[12]) == (0.5, 0.52) and isinstance(r[0], datetime)


def test_a_row_of_mixed_units_keeps_each_cell_s_format():
    data = xlsx_write.workbook([("S", [["a", "b"], [xlsx_write.Num(12.0, '0.0"x"'), xlsx_write.Num(0.1, "0.0%")]], {0}, {1: "0.00"})])
    ws = openpyxl.load_workbook(io.BytesIO(data))["S"]
    assert (ws["A2"].number_format, ws["B2"].number_format, ws["B2"].value) == ('0.0"x"', "0.0%", 0.1)
    plain = xlsx_write.workbook([("S", [["a"], [1.5]], {0})])          # a sheet with no formats is as it was
    assert b"numFmts" not in __import__("zipfile").ZipFile(io.BytesIO(plain)).read("xl/styles.xml")


# ---------- the routes and the plans ----------
from tests.test_research_api import api  # noqa: E402,F401  (the research API on the fake sources)


def test_the_dive_carries_the_log_as_the_plan_shows_it(api, monkeypatch):
    from app import main
    from app.intel import routes
    monkeypatch.setattr(routes, "public_facts", lambda region, sym: None)
    entry = {"at": "2026-10-04T06:00:00+00:00", "d": "2026-10-04", "cause": "refresh",
             "counts": {"removed": 7, "added": 0, "moved": 0, "layers": 0, "restated": 0},
             "removed": [{"symbol": f"S{i}", "name": f"S{i}", "layer": "Chips", "why": "no longer in the theme's map"} for i in range(7)],
             "added": [], "moved": [], "layers": [], "restated": []}
    kept = {TC.key_of("US", "AI data centers"): json.dumps({"snap": None, "log": [copy.deepcopy(entry), entry], "since": "2026-10-01"})}
    real = db.get_setting
    monkeypatch.setattr(db, "get_setting", lambda k: kept[k] if k in kept else real(k))
    d = api.get("/research/theme-dive?q=AI%20data%20centers&region=US").json()
    ch = d["changes"]
    assert ch["full"] is False and ch["older"] == 1 and len(ch["entries"][0]["removed"]) == 5 and ch["entries"][0]["hidden"] == 2
    assert ch["entries"][0]["counts"]["removed"] == 7
    main.app.dependency_overrides[main.current_profile] = lambda: {"id": "u1", "_plan": "basic", "plan": "basic"}
    ch = api.get("/research/theme-dive?q=AI%20data%20centers&region=US").json()["changes"]
    assert ch["full"] is True and len(ch["entries"]) == 2 and len(ch["entries"][0]["removed"]) == 7


def test_the_workbook_route_is_basic_and_up_and_counts_as_the_theme_s_deck(api, monkeypatch):
    from app import main
    from app.intel import routes
    monkeypatch.setattr(routes, "public_facts", lambda region, sym: None)
    r = api.get("/research/theme-dive/workbook?q=AI%20data%20centers&region=US")
    assert r.status_code == 402 and r.json()["detail"]["code"] == "upgrade_required" and "Basic" in r.json()["detail"]["message"]
    assert api.usage == []
    main.app.dependency_overrides[main.current_profile] = lambda: {"id": "u1", "_plan": "basic", "plan": "basic"}
    r = api.get("/research/theme-dive/workbook?q=AI%20data%20centers&region=US")
    assert r.status_code == 200 and r.content[:2] == b"PK"
    assert r.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert r.headers["content-disposition"].startswith('attachment; filename="StratLab - AI data centers theme (US) - ') and r.headers["content-disposition"].endswith('.xlsx"')
    wb = openpyxl.load_workbook(io.BytesIO(r.content))
    assert "Sources and method" in wb.sheetnames and "What changed" in wb.sheetnames
    assert [u for u in api.usage if u.startswith("deck")] == ["deck", "deck:theme:US:ai-data-centers"]
    # the same theme's slides this month: one deck with the workbook, not counted again
    r = api.get("/research/theme-dive/deck?q=AI%20data%20centers&region=US&format=pdf")
    assert r.status_code == 200 and api.usage.count("deck") == 1


def test_the_plans_name_both_features_on_basic_and_up():
    from app.plans import FEATURE_PLAN, allows
    for f in ("theme_changes", "theme_workbook"):
        assert FEATURE_PLAN[f] == "basic" and allows("basic", f) and allows("pro", f) and not allows("free", f)
