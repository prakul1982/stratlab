"""MO-5b: StratLab's own library samples for every market the backtester reads, seeded once in the background like the first
ones, listed under a market filter that offers only the markets that have samples."""
import json
import re

import pytest

from app import library, library_seed as S, research, universes
from app.data.markets import MARKETS
from tests.fake_db import headers
from tests.test_breadth import w  # noqa: F401  (fixture)
from tests.test_library_seed import ADVICE, PROVIDERS, main_markets

OPEN_MARKETS = {"US", "UK", "EU", "JP", "CRYPTO", "FX", "CMDTY"}      # read from sources that need no broker login


@pytest.fixture
def tiny(monkeypatch):
    """Four members in every ready-made group and a shorter period, so every market seeds in seconds."""
    monkeypatch.setattr(universes, "PRESETS", {m: [{**p, "symbols": p["symbols"][:4]} for p in ps] for m, ps in universes.PRESETS.items()})
    monkeypatch.setattr(S, "DAYS", {"1d": 700, "15m": 40})


def test_every_market_the_backtester_reads_has_samples():
    readable = {m["id"] for m in MARKETS if m["provider"] != "csv"}
    by_market: dict[str, set[str]] = {}
    for slug, spec in S.STRATEGIES.items():
        for market, pid in spec["groups"]:
            assert universes.presets(market) and S.preset_of(market, pid)["symbols"], (market, pid)
            by_market.setdefault(market, set()).add(slug)
    assert set(by_market) == readable == {"IN", "US", "UK", "EU", "JP", "CRYPTO", "FX", "MCX", "CDS", "CMDTY"}
    # a few classic rule sets each, a trend-following one and a mean-reverting one among them
    for market in readable - {"IN", "US"}:
        assert len(by_market[market]) >= 3, market
        assert by_market[market] & {"ema-20-50", "golden-cross", "donchian-20-10", "macd-cross", "supertrend", "ema-20-50-ls"}, market
        assert by_market[market] & {"rsi2-revert", "bb-revert"}, market
    from app.main import markets as registry
    assert all(registry.provider(m) is not None for m in readable)


def test_the_samples_are_run_through_the_pipeline_for_each_market(w, tiny, monkeypatch):
    ran = []
    real = research.run_group

    def spy(datasets, strategy, group, days, max_days):
        out = real(datasets, strategy, group, days, max_days)
        ran.append((group["market"], out["stats"]["ret"], out["stats"]["n"]))
        return out
    monkeypatch.setattr(research, "run_group", spy)
    out = S.seed(main_markets(), gap=0)
    assert not out["failed"], out["failed"]
    entries = {e["id"]: e for e in S.seeded()}
    assert set(entries) == set(S.wanted()) and len(entries) == len(ran)
    assert {e["market"] for e in entries.values()} == {m["id"] for m in MARKETS if m["provider"] != "csv"}
    # every figure on a card is what the backtest returned for that run: nothing made up, nothing typed in
    assert sorted((e["market"], e["stats"]["ret"], e["stats"]["trades"]) for e in entries.values()) == sorted(ran)
    for eid, e in entries.items():
        assert e["official"] is True and e["author"] == "StratLab" and e["owner"] == S.OWNER and e["group"]["market"] == e["market"]
        assert e["verdict"]["verdict"] in library.RANK and e["range"]["from"] and e["range"]["to"] and e["stats"]["trades"] is not None
        assert len(eid) <= 24 and library.ID.match(eid)
        assert not ADVICE.search(json.dumps(e)) and not PROVIDERS.search(json.dumps(library.public(e))), eid


def test_each_market_is_run_in_its_own_money_and_contract_sizes():
    for market, brokerage in (("IN", 20), ("MCX", 20), ("CDS", 20), ("US", 0), ("UK", 0), ("EU", 0), ("JP", 0), ("CRYPTO", 0), ("FX", 0), ("CMDTY", 0)):
        assert S.risk_of(S.STRATEGIES["ema-20-50"], market)["brokerage"] == brokerage, market
    # a contract's lot costs more than a tenth of the stock default capital, so those markets are run on a larger pot
    for market in ("MCX", "CDS"):
        r = S.risk_of(S.STRATEGIES["donchian-20-10"], market)
        assert r["capital"] >= 5000000 and r["maxAlloc"] == 20
    assert S.risk_of(S.STRATEGIES["st-s2"], "IN")["maxAlloc"] == 20 and S.risk_of(S.STRATEGIES["supertrend"], "US")["sl"] == 12
    # the sentence about one position's size names what the market trades
    for market, noun in (("US", "stock"), ("CRYPTO", "coin"), ("FX", "pair"), ("CDS", "pair"), ("MCX", "commodity"), ("CMDTY", "commodity")):
        assert f"in one {noun}," in S.risk_text(S.STRATEGIES["bb-revert"], {"market": market, "maxOpen": 5}), market


def test_the_long_and_short_rule_set_trades_both_ways(w, tiny):
    S.seed(main_markets(), only=["ema-20-50-ls"], gap=0)
    e = library.load("seed-ema-20-50-ls-fx")
    assert e["side"] == "both" and e["strategy"]["shortEntry"] and e["stats"]["trades"] > 0
    assert library.public(e)["side"] == "both"


def test_the_list_offers_only_markets_with_samples_and_filters_by_them(w, tiny):
    S.seed(main_markets(), only=["donchian-20-10", "rsi2-revert"], gap=0)
    c, h = w["client"], headers("free-token")
    got = c.get("/library", headers=h).json()
    counts = {m: sum(1 for e in S.seeded() if e["market"] == m) for m in ("IN", "US", "UK", "EU", "JP", "CRYPTO", "FX", "MCX", "CDS", "CMDTY")}
    assert got["markets"] == {m: n for m, n in counts.items() if n} and "CDS" in got["markets"] and "EU" in got["markets"]
    for m in ("JP", "mcx", "CRYPTO"):
        r = c.get(f"/library?market={m}", headers=h).json()
        assert r["entries"] and {e["market"] for e in r["entries"]} == {m.upper()}
        assert r["markets"] == got["markets"]                      # the choices don't shrink to the one picked
    assert c.get("/library?market=FX&official=true", headers=h).json()["total"] == counts["FX"]
    pub = c.get("/public/library").json()
    assert pub["markets"] == got["markets"]
    assert {e["market"] for e in c.get("/public/library?market=UK").json()["entries"]} == {"UK"}
    assert c.get("/library?market=XX", headers=h).json()["entries"] == []


def test_a_market_added_later_is_seeded_alone_and_without_the_brokers_login(w, tiny, monkeypatch):
    from app import main
    S.seed(main_markets(), gap=0)
    have = S.seeded()
    for e in have:                                                  # the library as it was before the UK and Japan samples
        if e["market"] in ("UK", "JP"):
            library.remove(e["id"])
    have = S.seeded()
    todo = S.lacking(have)
    assert set(todo.values()) == {"UK", "JP"} and len(todo) == 6
    got = S.seed(main_markets(), gap=0, ids=set(todo))
    assert sorted(p["id"] for p in got["published"]) == sorted(todo) and not got["failed"]
    assert not S.lacking(S.seeded())

    # start-up: fresh entries are not run again, only what is missing; open sources need no wait for the broker
    for i in todo:
        library.remove(i)
    seeds, waits = [], []
    monkeypatch.setattr(S, "seed", lambda registry, **kw: seeds.append(kw) or {"published": [], "failed": []})
    monkeypatch.setattr(main.kite, "ready", lambda: False)
    monkeypatch.setattr(S, "stale", lambda entries, now=None: False)
    main.library_seed_once(sleep=waits.append)
    assert seeds == [{"ids": set(todo)}] and waits == [main.SEED_FIRST_WAIT]
    # a missing Indian entry does wait for the login, and then runs alone
    gone = "seed-supertrend-in"
    library.remove(gone)
    seeds.clear(); waits.clear()
    ready = iter([False, True])
    monkeypatch.setattr(main.kite, "ready", lambda: next(ready))
    monkeypatch.setattr(S, "lacking", lambda have: {gone: "IN"})
    main.library_seed_once(sleep=waits.append)
    assert seeds == [{"ids": {gone}}] and waits == [main.SEED_FIRST_WAIT, main.SEED_RECHECK]


def test_the_sites_own_page_list_has_every_sample():
    src = (re.sub(r"\s+", " ", open(__file__.replace("backend/tests/test_review_mo5.py", "frontend/src/content/seo.ts")).read()))
    for eid in S.wanted():
        assert f'["{eid}", ' in src, eid
