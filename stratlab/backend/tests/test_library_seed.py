"""StratLab's own strategies in the public library: built from the rules engine, run through the app's own backtest and
verdict on small stand-ins for the standard groups (fake data), published as StratLab with a badge, every verdict kept
as the engine gave it, idempotent, and worded as facts."""
import json
import re

import pytest

from app import library, library_seed as S, universes
from app.models import Strategy
from tests.fake_db import headers
from tests.test_breadth import w  # noqa: F401  (fixture)

ADVICE = re.compile(r"\b(buy now|sell now|recommend\w*|you should|should buy|worth paper trading|best|guaranteed|will (?:rise|fall|make|earn))\b", re.I)
PROVIDERS = re.compile(r"kite|zerodha|yahoo|screener|finnhub|gemini|anthropic", re.I)


@pytest.fixture
def small(monkeypatch):
    """Six stocks (or coins' worth of US names) in each standard group, and a shorter period, so the seed runs in seconds."""
    for market, pid, syms in (("IN", "nifty50", ["RELIANCE", "TCS", "INFY", "HDFCBANK", "SBIN", "ITC"]),
                              ("IN", "fno_liquid", ["RELIANCE", "TCS", "INFY", "SBIN"]),
                              ("US", "us_mega", ["AAPL", "MSFT", "NVDA", "AMZN"])):
        monkeypatch.setattr(universes, "PRESETS", {**universes.PRESETS, market: [
            {**p, "symbols": syms} if p["id"] == pid else p for p in universes.PRESETS[market]]})
    monkeypatch.setattr(S, "DAYS", {"1d": 700, "15m": 40})


def test_every_strategy_is_a_valid_rule_set():
    assert 8 <= len(S.STRATEGIES) <= 12
    for slug, spec in S.STRATEGIES.items():
        s = S.strategy_of(spec, spec["name"])
        assert isinstance(s, Strategy) and s.entry, slug
        assert not ADVICE.search(spec["name"] + spec["text"]), slug
        for market, pid in spec["groups"]:
            assert S.preset_of(market, pid)["symbols"]
        assert len(S.entry_id(slug, "fno_liquid")) <= 24 and library.ID.match(S.entry_id(slug, "fno_liquid"))
    assert len({S.entry_id(s, p) for s, v in S.STRATEGIES.items() for _, p in v["groups"]}) == sum(len(v["groups"]) for v in S.STRATEGIES.values())
    names = " ".join(s["name"] for s in S.STRATEGIES.values())
    for need in ("ST S2", "20/50 EMA", "RSI(2)", "52-week", "Bollinger", "Opening-range", "Golden cross", "Donchian"):
        assert need in names, need
    # ST S2 is the app's own rule set
    from app import scan
    assert S.strategy_of(S.STRATEGIES["st-s2"], "x").entry[0].l.t == scan.ST_S2["entry"][0]["l"]["t"]


def test_seed_publishes_honest_verdicts_as_stratlab(w, small):
    out = S.seed(main_markets(), gap=0)
    assert not out["failed"], out["failed"]
    assert len(out["published"]) == sum(len(s["groups"]) for s in S.STRATEGIES.values())
    entries = S.seeded()
    assert len(entries) == len(out["published"])
    verdicts = {e["verdict"]["verdict"] for e in entries}
    assert verdicts <= set(library.RANK)
    for e in entries:
        assert e["author"] == "StratLab" and e["badge"] == "StratLab" and e["official"] is True and e["owner"] == S.OWNER
        assert e["group"]["name"] and e["strategy"]["entry"] and e["stats"]["trades"] is not None
        assert e["verdict"]["headline"] and e["verdict"]["summary"]
        assert not ADVICE.search(json.dumps(e)), e["id"]
        assert not PROVIDERS.search(json.dumps(library.public(e)))
    # every verdict is kept, including the ones that say there is nothing there
    assert any(v in verdicts for v in ("no_edge", "luck", "not_enough", "mixed", "edge"))


def test_the_page_lists_them_with_the_badge(w, small):
    S.seed(main_markets(), only=["golden-cross"], gap=0)
    r = w["client"].get("/library", headers=headers("free-token")).json()
    rows = [e for e in r["entries"] if e.get("official")]
    assert sorted(e["id"] for e in rows) == ["seed-golden-cross-in", "seed-golden-cross-us"]
    assert all(e["badge"] == "StratLab" and e["mine"] is False and "owner" not in e for e in rows)
    one = w["client"].get(f"/library/{rows[0]['id']}", headers=headers("free-token")).json()
    assert one["author"] == "StratLab" and one["verdict"]["headline"]
    # people can copy the rules and report them like any entry, but only the site's owner can take one down
    assert w["client"].delete(f"/library/{rows[0]['id']}", headers=headers("pro-token")).status_code in (403, 404)


def test_seeding_again_changes_nothing_but_keeps_counts_and_moderation(w, small):
    S.seed(main_markets(), only=["ema-20-50"], gap=0)
    eid = "seed-ema-20-50-in"
    e = library.load(eid)
    e["copies"], e["hidden"], e["hidden_by"], e["reports"] = 4, True, "admin", {"u": {"reason": "other", "at": "x"}}
    library.save(e)
    S.seed(main_markets(), only=["ema-20-50"], gap=0)
    again = library.load(eid)
    assert again["copies"] == 4 and again["hidden"] is True and again["published_at"] == e["published_at"]
    assert len([x for x in library.all_entries() if x["id"] == eid]) == 1
    assert len(S.seeded()) == 2


def test_a_group_without_data_is_reported_and_the_rest_publish(w, small, monkeypatch):
    real = S.run_group

    def flaky(registry, strat, market, preset, now, max_open=10):
        if market == "US":
            raise S.SeedError("Fewer than two stocks of US had data.")
        return real(registry, strat, market, preset, now, max_open)
    monkeypatch.setattr(S, "run_group", flaky)
    out = S.seed(main_markets(), only=["golden-cross"], gap=0)
    assert [p["id"] for p in out["published"]] == ["seed-golden-cross-in"]
    assert out["failed"][0]["id"] == "seed-golden-cross-us" and "Fewer than two" in out["failed"][0]["error"]


def test_the_summary_is_a_finding_not_a_suggestion():
    assert S.plain("It made money after costs. Worth paper trading before real money.") == "It made money after costs."
    assert S.plain("Only 3 trades.") == "Only 3 trades."


def test_start_up_seed_waits_for_market_data_instead_of_giving_up(w, monkeypatch):
    """A night-time deploy starts before the day's broker login: the one start-up check used to find market data down
    and never look again until the next deploy, so the library stayed empty."""
    from app import main
    seeds, waits, ready = [], [], iter([False, False, True])
    monkeypatch.setattr(S, "seeded", lambda: [])
    monkeypatch.setattr(S, "seed", lambda registry, **kw: seeds.append(1) or {"published": [], "failed": []})
    monkeypatch.setattr(main.kite, "ready", lambda: next(ready))
    main.library_seed_once(sleep=waits.append)
    assert seeds == [1] and waits == [main.SEED_FIRST_WAIT, main.SEED_RECHECK, main.SEED_RECHECK]


def test_start_up_seed_does_nothing_when_the_library_has_them_and_stops_after_a_day(w, monkeypatch):
    from app import main
    seeds, waits = [], []
    monkeypatch.setattr(S, "seed", lambda registry, **kw: seeds.append(1) or {})
    monkeypatch.setattr(S, "seeded", lambda: [{"id": "seed-x"}])
    main.library_seed_once(sleep=waits.append)
    assert seeds == [] and waits == [main.SEED_FIRST_WAIT]                  # a deploy costs one cheap check
    monkeypatch.setattr(S, "seeded", lambda: [])
    monkeypatch.setattr(main.kite, "ready", lambda: False)
    waits.clear()
    main.library_seed_once(sleep=waits.append)
    assert seeds == [] and len(waits) == 1 + main.SEED_TRIES                 # market data never came: it gives up after a day


def test_admin_route_runs_it_in_the_background(w, small, monkeypatch):
    called = []
    monkeypatch.setattr(S, "seed", lambda registry, only=None, **kw: called.append(only) or {"published": [], "failed": []})
    c = w["client"]
    assert c.post("/admin/library/seed", headers=headers("free-token")).status_code == 403
    r = c.post("/admin/library/seed?only=golden-cross,nope", headers=headers("admin-token"))
    assert r.status_code == 200 and r.json()["strategies"] == ["golden-cross"]
    for _ in range(50):
        st = c.get("/admin/library/seed", headers=headers("admin-token")).json()
        if not st["running"]:
            break
        import time
        time.sleep(0.1)
    assert called == [["golden-cross"]] and st["result"] == {"published": [], "failed": []}


def main_markets():
    from app import main
    return main.markets
