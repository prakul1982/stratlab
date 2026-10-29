"""MOOD-1 (owner, 29 Oct): the Market pulse's mood was very basic and contradicted itself ("15 of 16 sector indices up" beside
"banks and financial stocks dragged the market", a main story no shown headline carried, "Reliance bought shares, prompting a
lift in the indices", the cards' levels said again in another rounding, only the FII figure). The mood is now tables and a
headline with lines built from the same figures (app/intel/mood.py), and an AI line stands only on a headline or a figure."""
import json
from datetime import datetime, timezone

import pytest
import time_machine

from app import main  # noqa: F401,I001  (first: the app wires the modules)
from app.intel import ai as A
from app.intel import grounding, mood
from tests import fake_fundamentals
from tests import fake_prices as P
from tests import visual_server as V
from tests import world as W
from tests.fake_db import headers

H = headers("pro-token")
IN = [{"name": "NIFTY 50", "price": 22600.0, "prev_close": 22512.0, "change_pct": 0.39, "high52": 26277.35, "low52": 21743.65},
      {"name": "SENSEX", "price": 73737.34, "prev_close": 73450.0, "change_pct": 0.39, "high52": 85978.25, "low52": 71425.0},
      {"name": "NIFTY BANK", "price": 54559.4, "prev_close": 54266.0, "change_pct": 0.54, "high52": 60000.0, "low52": 50000.0}]
SEC_TODAY = {f"NIFTY {n}": {"price": 1000.0, "change_pct": c} for n, c in
             (("BANK", 0.54), ("IT", 1.2), ("AUTO", 0.3), ("FMCG", 0.1), ("PHARMA", 0.8), ("METAL", -0.4), ("REALTY", 0.2), ("ENERGY", 0.6))}
CLOSES = [100.0 + i * (1 if i % 2 else -0.5) for i in range(30)]


# ---------- one rounding for every figure ----------
def test_a_percentage_is_written_one_way():
    assert mood.fpct(0.545) == "+0.55%" and mood.fpct(-0.545) == "−0.55%" and mood.fpct(0.001) == "0.00%"
    assert mood.fpct(12.345, 1, sign=False) == "12.3%" and mood.fpct(None) == "–"
    # a move that shows as 0.00% is neither up nor down, in the words as in the colours
    assert mood.sgn(0.004) == 0 and mood.sgn(-0.006) == -1 and mood.sgn(0.006) == 1
    assert mood.fcr(-356900.4) == "₹3,56,900 crore" and mood.fcr(3569) == "₹3,569 crore"


# ---------- how today compares ----------
def test_a_day_is_held_to_the_usual_move_by_a_number():
    typ = mood.typical_move([100, 101, 100, 102, 101, 103, 102, 104, 103, 105, 104, 106])
    assert typ["days"] == 11 and typ["avg_abs"] == pytest.approx(1.42, abs=0.01)           # the mean of eleven absolute moves
    assert mood.typical_move([100, 101, 102]) is None                      # too few sessions to call anything usual
    c = mood.compare_today("NIFTY 50", 0.39, {"avg_abs": 0.62, "days": 20})
    assert c["ratio"] == 0.6 and c["words"] == "a smaller move than usual"
    assert mood.compare_today("NIFTY 50", -2.5, {"avg_abs": 0.62, "days": 20})["words"] == "a very large move"
    assert mood.compare_today("NIFTY 50", None, {"avg_abs": 0.62, "days": 20}) is None


# ---------- breadth from fixtures ----------
TODAY = {"day": "2026-10-28", "prev_day": "2026-10-27",
         "adv": {"value": 254, "prev": 359, "change": -105}, "dec": {"value": 244, "prev": 141, "change": 103},
         "unch": {"value": 2, "prev": 0, "change": 2}, "stocks": {"value": 500, "prev": 500, "change": 0},
         "highs": {"value": 7, "prev": 6, "change": 1}, "lows": {"value": 24, "prev": 24, "change": 0},
         "pct20": {"value": 26.6, "prev": 25.0, "change": 1.6}, "pct50": {"value": 19.2, "prev": 17.8, "change": 1.4},
         "pct200": {"value": 33.2, "prev": 33.8, "change": -0.6}}


def test_breadth_counts_the_close_and_then_the_live_round():
    b = mood.breadth_block(TODAY, None, "NIFTY 500", "2026-10-29")
    assert (b["adv"], b["dec"], b["unch"], b["stocks"], b["highs"], b["lows"]) == (254, 244, 2, 500, 7, 24)
    assert b["ratio"] == 1.04 and not b["live"] and b["day"] == "2026-10-28"
    rows = {r["key"]: r for r in b["rows"]}
    assert rows["pct50"]["now"] == 19.2 and rows["pct50"]["before"] == 17.8 and rows["pct50"]["change"] == 1.4
    assert rows["adv"]["change"] == -105 and rows["lows"]["change"] == 0
    # while the market trades the live round is the count; the 52-week highs and lows stay the last close's
    live = {"adv": 300, "dec": 180, "unch": 20, "pct20": 40.0, "pct50": 30.5, "pct200": 35.0}
    b = mood.breadth_block(TODAY, live, "NIFTY 500", "2026-10-29")
    assert b["live"] and b["adv"] == 300 and b["stocks"] == 500 and b["highs"] == 7 and b["day"] == "2026-10-29" and b["close_day"] == "2026-10-28"
    assert mood.breadth_block(None, None, "NIFTY 500", "2026-10-29") is None


# ---------- sectors from fixtures ----------
def test_the_sector_table_has_week_month_and_one_count():
    closes = {n: CLOSES for n in SEC_TODAY}
    t = mood.sector_table(SEC_TODAY, closes, {"NIFTY IT": [{"symbol": "TCS", "name": "TCS", "change_pct": 1.5}]})
    assert [r["name"] for r in t["rows"]][:2] == ["NIFTY IT", "NIFTY PHARMA"] and t["rows"][-1]["name"] == "NIFTY METAL"
    assert (t["up"], t["down"], t["of"], t["unchanged"]) == (7, 1, 8, 0)
    it = t["rows"][0]
    assert it["w1"] == round((1000.0 / CLOSES[-5] - 1) * 100, 2) and it["m1"] == round((1000.0 / CLOSES[-21] - 1) * 100, 2)
    assert it["movers"][0]["symbol"] == "TCS"
    assert mood.sector_table({"A": {"price": 1, "change_pct": 1.0}}, {}) is None          # fewer than five sectors say nothing


# ---------- the stocks that moved the index ----------
def test_the_index_movers_are_weighed_by_market_value():
    members = [{"symbol": s, "name": s, "market_cap": cap, "change_pct": ch}
               for s, cap, ch in (("A", 500.0, 1.0), ("B", 300.0, -2.0), ("C", 100.0, 0.5), ("D", 50.0, 0.0), ("E", 50.0, -1.0))]
    m = mood.index_movers(members, 20000.0, "NIFTY 50", top=2)
    # A: 50% of the index x 1.00% x 20,000 = 100 points; B: 30% x -2.00% x 20,000 = -120
    assert m["adding"][0]["symbol"] == "A" and m["adding"][0]["points"] == 100.0
    assert m["taking"][0]["symbol"] == "B" and m["taking"][0]["points"] == -120.0
    assert [r["symbol"] for r in m["adding"]] == ["A", "C"] and len(m["taking"]) == 2
    # the US index: the largest are read, the weights are over every company in it
    us = mood.index_movers(members[:3], 7000.0, "S&P 500", total=2000.0)
    assert us["adding"][0]["points"] == pytest.approx(7000 * (500 / 2000) * 0.01, abs=0.1)
    # too few read to say: no table, not a wrong one
    assert mood.index_movers(members[:2], 20000.0, "NIFTY 50") is None
    assert mood.index_movers(members, None, "NIFTY 50") is None


def test_a_points_table_that_does_not_add_up_to_the_index_is_left_out():
    # every company read and weighed: A +100, B -120, C +5 (members of the test above): the estimated total is -15, so an index that moved
    # -15 points agrees; one that moved +400 does not (a list a name or two out of date, a weight far off), and no table is better than a wrong one
    members = [{"symbol": s, "name": s, "market_cap": cap, "change_pct": ch}
               for s, cap, ch in (("A", 500.0, 1.0), ("B", 300.0, -2.0), ("C", 100.0, 0.5), ("D", 50.0, 0.0), ("E", 50.0, -1.0))]
    ok = mood.index_movers(members, 20000.0, "SENSEX", actual_points=-20.0)
    assert ok and ok["est_total"] == -20.0 and ok["actual"] == -20.0
    assert mood.index_movers(members, 20000.0, "SENSEX", actual_points=400.0) is None
    assert mood.index_movers(members, 20000.0, "SENSEX") is not None                      # no actual to check against: the estimate stands
    # the US index's largest only are read, so its points can't be added up to the index's: not checked
    assert mood.index_movers(members[:3], 7000.0, "S&P 500", total=2000.0, actual_points=900.0) is not None


def test_every_index_of_a_market_gets_a_table_and_no_unchecked_member_list(world):
    # the SENSEX has no movers table until its members come from BSE itself (a remembered list was already stale)
    assert [n for n, _ in mood.MOVER_INDICES["IN"]] == ["NIFTY 50"] and [n for n, _ in mood.MOVER_INDICES["US"]] == ["S&P 500"]
    assert not hasattr(mood, "SENSEX_30")
    from app.intel import routes
    from app import universes
    from unittest import mock
    with time_machine.travel(DAY, tick=False), mock.patch.object(mood, "MIN_COVER", 0.0), mock.patch.object(mood, "ADD_UP", 1e9):
        m = routes.mood_hub()
        levels, _ = routes.hub.indices_now("IN", wait=8.0)
        n50 = next(p["symbols"] for p in universes.PRESETS["IN"] if p["id"] == "nifty50")
        caps = {s: 1000.0 + i for i, s in enumerate(n50)}
        got = m._movers("IN", caps, levels, {})
        assert got and [b["index"] for b in got] == ["NIFTY 50"]


# ---------- the institutions' flows ----------
def test_flows_have_both_fii_and_dii_and_five_days():
    days = [(f"2026-10-{d}", {"fii": {"net": -100.0 * d}, "dii": {"net": 50.0 * d}}) for d in range(20, 29)]
    cash = {"status": "ok", "as_of": "2026-10-28", "fii": {"net": -2800.0}, "dii": {"net": 1400.0}}
    f = mood.flows_block(cash, days)
    assert [r["day"] for r in f["rows"]] == [f"2026-10-{d}" for d in range(24, 29)]
    assert f["rows"][-1] == {"day": "2026-10-28", "fii": -2800, "dii": 1400}
    assert f["fii_total"] == sum(r["fii"] for r in f["rows"]) and f["dii_total"] == sum(r["dii"] for r in f["rows"])
    assert mood.flows_block({"status": "none"}, days) is None


# ---------- the headline and lines never contradict the tables ----------
def full_payload():
    t = mood.sector_table(SEC_TODAY, {n: CLOSES for n in SEC_TODAY})
    p = {"region": "IN", "compare": mood.compare_today("NIFTY 50", 0.39, {"avg_abs": 0.62, "days": 20}),
         "breadth": mood.breadth_block(TODAY, None, "NIFTY 500", "2026-10-29"), "sectors": t,
         "movers": [mood.index_movers([{"symbol": "A", "name": "Reliance Industries", "market_cap": 500.0, "change_pct": 1.0},
                                      {"symbol": "B", "name": "HDFC Bank", "market_cap": 300.0, "change_pct": -2.0},
                                      {"symbol": "C", "name": "TCS", "market_cap": 100.0, "change_pct": 0.5}], 22512.0, "NIFTY 50")],
         "flows": mood.flows_block({"status": "ok", "as_of": "2026-10-28", "fii": {"net": -2800.0}, "dii": {"net": 1400.0}},
                                   [("2026-10-28", {"fii": {"net": -2800.0}, "dii": {"net": 1400.0}})]),
         "risk": {"rows": [{"label": "India VIX", "kind": "vol", "tag": "vol", "price": 13.2, "change_pct": 2.1}]}}
    p["headline"] = mood.headline_of(IN, t, p["compare"])
    p["lines"] = mood.lines_of(p)
    return p


def test_the_headline_and_lines_are_the_tables_figures_and_not_the_cards():
    p = full_payload()
    assert p["headline"] == "Mildly positive: all three indices up on the day, a smaller move than usual, with 7 of 8 sector indices up."
    assert 3 <= len(p["lines"]) <= 5
    text = " ".join([p["headline"], *p["lines"]])
    # the cards' levels are not said again, in any rounding
    for level in ("22,600", "22600", "73,737", "73737", "54,559", "54559"):
        assert level not in text
    assert "7 of 8 sector indices rose and 1 fell; Nifty IT" in text or "7 of 8 sector indices rose and 1 fell; NIFTY IT" in text or "led (+1.20%)" in text
    assert mood.verify(p) == []


def test_a_line_the_tables_do_not_bear_out_is_found():
    p = full_payload()
    assert mood.verify({**p, "lines": [*p["lines"], "15 of 16 sector indices rose."]}) == [
        "\"15 of 16 sector indices\" is not the sector table's count"]
    bad = mood.verify({**p, "lines": ["India VIX is 13.20, up 2.5% on the day."]})
    assert bad and "2.5%" in bad[0]
    assert mood.verify({**p, "lines": ["Nifty IT led (+9.99%) and Nifty Metal lagged (−0.40%)."]})


def test_a_mixed_day_names_who_went_which_way():
    mixed = [IN[0], {**IN[1], "change_pct": -0.2}]
    assert mood.headline_of(mixed, None, None) == "Mixed: the NIFTY 50 up and the SENSEX down on the day."
    assert mood.headline_of([], None, None) == ""
    assert grounding.mood_line(mixed) == mood.headline_of(mixed, None, None)       # one wording, wherever it is asked for


# ---------- an AI line stands on a headline or a figure, and agrees with the sector table ----------
SECTORS = {"up": 15, "down": 1, "unchanged": 0, "of": 16,
           "rows": [{"name": "NIFTY BANK", "label": "Nifty Bank", "change_pct": 0.54}, {"name": "NIFTY FIN SERVICE", "label": "Nifty Financial Services", "change_pct": 0.31},
                    {"name": "NIFTY IT", "label": "Nifty IT", "change_pct": -0.2}]}
HEADS = [{"headline": "Bank and financial stocks in focus as RBI meets"}, {"headline": "Reliance Industries opens new gigafactory in Jamnagar"},
         {"headline": "Sensex, Nifty close higher; crude oil eases"}]


def test_a_sector_never_dragged_when_its_index_rose():
    # the owner's screenshot: "Bank and financial sector drag: banks and financial stocks dragged the market"
    ai = {"tone": "", "hot": [], "themes": [],
          "flows": [{"title": "Bank and financial sector drag", "detail": "Banks and financial stocks dragged the market lower.", "direction": ""},
                    {"title": "IT stocks slip", "detail": "IT stocks fell on Tuesday.", "direction": ""}]}
    out = grounding.ground_pulse(ai, IN, HEADS, SECTORS)
    assert out["flows"] == [] or all("drag" not in f["detail"].lower() for f in out["flows"])
    assert not grounding.sector_direction_ok("Banks and financial stocks dragged the market.", SECTORS)
    assert not grounding.sector_direction_ok("Bank stocks fell while the market rose.", SECTORS)
    assert grounding.sector_direction_ok("Bank stocks gained and IT stocks fell.", SECTORS)            # each clause is held to its own sector
    assert grounding.sector_direction_ok("IT stocks fell.", SECTORS)
    assert not grounding.sector_direction_ok("IT stocks gained.", SECTORS)
    assert not grounding.sector_direction_ok("Most sectors fell.", SECTORS)                           # 15 of 16 rose
    assert grounding.sector_direction_ok("Most sectors rose.", SECTORS)


def test_a_company_line_the_headlines_do_not_carry_is_replaced_by_the_headline():
    ai = {"tone": "", "flows": [], "themes": [],
          "hot": [{"name": "Reliance Industries", "ticker": "RELIANCE", "why": "Reliance bought shares, prompting a lift in the indices."}]}
    out = grounding.ground_pulse(ai, IN, HEADS, SECTORS)
    assert out["hot"][0]["why"] == "Reliance Industries opens new gigafactory in Jamnagar"
    # a company no headline names is not listed at all
    ai["hot"].append({"name": "Zomato", "ticker": "ZOMATO", "why": "Zomato rose."})
    assert [h["name"] for h in grounding.ground_pulse(ai, IN, HEADS, SECTORS)["hot"]] == ["Reliance Industries"]
    # a line in the headline's own words stays
    ai = {"tone": "", "flows": [], "themes": [], "hot": [{"name": "Reliance Industries", "ticker": "RELIANCE", "why": "Reliance Industries opens a gigafactory in Jamnagar."}]}
    assert grounding.ground_pulse(ai, IN, HEADS, SECTORS)["hot"][0]["why"] == "Reliance Industries opens a gigafactory in Jamnagar."


def test_ungrounded_theme_and_tone_sentences_are_dropped_and_the_levels_are_not_recited():
    ai = {"tone": "Strong domestic demand and a weaker dollar supported sentiment. Crude oil eased.",
          "hot": [], "flows": [],
          "themes": [{"theme": "Space economy", "detail": "Satellite launches are rising worldwide.", "example": ""},
                     {"theme": "Crude", "detail": "Crude oil eased.", "example": ""}]}
    out = grounding.ground_pulse(ai, IN, HEADS, SECTORS)
    assert out["tone"] == "Crude oil eased."
    assert [t["theme"] for t in out["themes"]] == ["Crude"]
    assert "22,600" not in out["tone"]


def test_the_main_story_counts_headlines_that_can_be_pointed_at():
    titles = ["Sensex falls as crude oil climbs", "TCS Q2 profit up 5%", "Crude oil at $95 weighs on OMCs", "Oil prices surge on supply fears", "Gold at a record"]
    st = grounding.story_of("", titles)
    assert st["label"] == "crude oil prices" and (st["n"], st["of"]) == (3, 5) and st["indices"] == [0, 2, 3]
    assert grounding.story_of("", ["Gold at a record", "TCS profit up"]) is None


def test_the_read_carries_the_story_with_its_headlines_and_no_levels(monkeypatch):
    def fake(system, text, **k):
        assert "dragged or fell when its row is positive" in system and '"rows"' in text
        return json.dumps({"driver": "crude oil", "tone": "The NIFTY 50 closed at 22,600, up 0.39%.", "hot": [], "flows": [], "themes": []})
    monkeypatch.setattr(A, "complete", fake)
    heads = [{"headline": h} for h in ("Sensex rises as crude oil eases", "Crude oil slips", "Oil prices fall", "TCS profit up")]
    out = A.pulse("IN", "", IN, heads, (None, None), closed=True, sectors=SECTORS)
    assert out["story"]["label"] == "crude oil prices" and out["story"]["n"] == 3 and out["story"]["of"] == 4
    assert [out["story"]["headlines"][i] for i in out["story"]["indices"]] == ["Sensex rises as crude oil eases", "Crude oil slips", "Oil prices fall"]
    assert "mood" not in out


# ---------- the whole thing in the fake world, both markets ----------
DAY = datetime(2026, 10, 14, 6, 30, tzinfo=timezone.utc)       # a Wednesday, 12:00 IST: India open, the US closed


@pytest.fixture(scope="module")
def world():
    mp = pytest.MonkeyPatch()
    mp.setattr(P, "FROZEN", DAY)
    with time_machine.travel(DAY, tick=False):
        built = W.build(mp)
        fake_fundamentals.install(mp, main.research_hub.screener)
        V.screen_index()
        V.breadth(mp)
        yield built
        built["close"]()
    mp.undo()


@pytest.mark.parametrize("region,index", [("IN", "NIFTY 50"), ("US", "S&P 500")])
def test_the_mood_endpoint_gives_tables_and_lines_that_agree(world, region, index):
    with time_machine.travel(DAY, tick=False):
        c = world["client"]
        for _ in range(3):
            p = c.get(f"/research/pulse/mood?region={region}", headers=H).json()
            if not p.get("pending"):
                break
        assert p["region"] == region and p["compare"]["index"] == index
        s = p["sectors"]
        assert s["of"] >= 5 and s["up"] + s["down"] + s["unchanged"] == s["of"]
        assert s["rows"] == sorted(s["rows"], key=lambda r: (-r["change_pct"], r["name"]))
        assert all(r["w1"] is not None and r["m1"] is not None for r in s["rows"])           # the week and month, from the closes
        assert p["breadth"] and p["breadth"]["adv"] is not None and p["breadth"]["rows"]
        assert p["risk"]["rows"] and p["global"]["rows"]
        assert 3 <= len(p["lines"]) <= 5 and p["headline"]
        # every figure in the words is one of the tables'
        assert mood.verify(p) == []
        # the mood and the AI's sector count are held to the same table: one source of truth for "N of M sector indices"
        again = main.research_hub and routes_sectors(region)
        assert (again["up"], again["down"], again["of"]) == (s["up"], s["down"], s["of"])
        # the cards' levels (read by /pulse) are not repeated in the words
        for i in c.get(f"/research/pulse?region={region}", headers=H).json()["indices"]:
            assert f"{i['price']:,.0f}" not in " ".join([p["headline"], *p["lines"]])


def routes_sectors(region):
    from app.intel import routes
    return routes.mood_hub().sector_moves(region)


def test_the_mood_is_the_same_read_for_everyone_and_stays_small(world):
    with time_machine.travel(DAY, tick=False):
        from app.intel import routes
        c = world["client"]
        for r in ("IN", "US"):
            c.get(f"/research/pulse/mood?region={r}", headers=H)
        m = routes.mood_hub()
        # two payloads (one a market) and the daily closes of a sector table and an index: bounded by the markets, not by visitors
        sizes = {r: len(json.dumps(m.payloads.kept(r)[1])) for r in ("IN", "US")}
        assert max(sizes.values()) < 60_000, sizes
        assert len(m.payloads._kept) <= 2 and len(m.closes._kept) <= 4
        before = m.payloads.kept("IN")[0]
        c.get("/research/pulse/mood?region=IN", headers={"authorization": "Bearer free-token"})
        assert m.payloads.kept("IN")[0] == before                      # another person's look reads nothing again within the minute


# ---------- the rotation table's returns against the benchmark (MOOD-1) ----------
def test_relative_returns_are_points_over_the_benchmark_for_a_week_a_month_and_three_months():
    import pandas as pd
    from app import rotation
    idx = pd.bdate_range("2026-06-01", periods=70)
    bench = pd.Series([100.0 + i for i in range(70)], index=idx)                     # +1 a day
    member = pd.Series([100.0 * (1.01 ** i) for i in range(70)], index=idx)          # +1% a day
    r = rotation.relative_returns(member, bench)
    assert r["w1"] == round((1.01 ** 69 / 1.01 ** 64 - 1 - (169 / 164 - 1)) * 100, 2)
    assert r["m1"] == round((1.01 ** 69 / 1.01 ** 48 - 1 - (169 / 148 - 1)) * 100, 2)
    assert r["m3"] == round((1.01 ** 69 / 1.01 ** 6 - 1 - (169 / 106 - 1)) * 100, 2)
    # a member with fewer shared sessions than a span has none for it, never a made-up one
    short = rotation.relative_returns(member.tail(30), bench)
    assert short["w1"] is not None and short["m1"] is not None and short["m3"] is None
    assert rotation.relative_returns(member.tail(3), bench) == {"w1": None, "m1": None, "m3": None}


@pytest.mark.parametrize("region", ["IN", "US"])
def test_the_rotation_rows_carry_their_returns(world, region):
    with time_machine.travel(DAY, tick=False):
        c = world["client"]
        got = c.get(f"/research/rotation?region={region}&set=sectors&interval=weekly&tail=4", headers=H).json()
        assert got["v"] == 3 and len(got["rows"]) >= 5
        rows = [r for r in got["rows"] if r.get("ret")]
        assert rows and all(set(r["ret"]) == {"w1", "m1", "m3"} for r in rows)
        assert any(r["ret"]["m3"] is not None for r in rows)


def test_the_daily_closes_of_a_past_day_are_forgotten_so_the_cache_does_not_grow():
    from app.intel.snapshot import Snapshot

    class Hub:
        def chart(self, region, sym, rng, tf):
            return {"candles": [{"t": f"2026-10-{d:02d}", "c": 100.0 + d} for d in range(1, 14)]}
    m = mood.Mood(Hub())
    for day in ("2026-10-13", "2026-10-14", "2026-10-15"):
        got = m._closes_for("IN", ["NIFTY 50"], day, "index")
        assert got["NIFTY 50"][-1] == 100.0 + min(int(day[-2:]) - 1, 13)           # the session still trading is left out
        assert [k for k in m.closes.keys() if k[:2] == ("IN", "index")] == [("IN", "index", day)]
    assert isinstance(m.closes, Snapshot) and len(m.closes.keys()) == 1
