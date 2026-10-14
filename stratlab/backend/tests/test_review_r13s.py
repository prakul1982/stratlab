"""Round 13 Safari review (R13S): the account stops at zero."""
import math

from app.engine import portfolio
from app.engine.core import backtest
from app.engine.verdict import _trade_dd, evaluate_portfolio
from app.models import Strategy
from tests.test_engine import bars_from
from tests.test_engine_intraday import day
from tests.test_portfolio import ALWAYS, ds

CAP = 100000


def _group_strategy(**risk):
    r = {"capital": CAP, "sl": 0, "tgt": 0, "brokerage": 0, "slippage": 0, "sizing": "capital", "perTrade": CAP}
    r.update(risk)
    return Strategy(tf="15m", entry=ALWAYS, exit=[], risk=r)


def _crash(start):
    return day("2026-01-05", [start, start, start * 0.8, start * 0.5, start * 0.3, start * 0.2, start * 0.2, start * 0.2])


def test_group_account_stops_at_zero_not_below():
    """A leveraged position (the slots share one pot) can lose more than the account has."""
    data = [ds(s, _crash(100.0)) for s in "ABC"]
    out = portfolio.run(data, _group_strategy(leverage=3), max_open=3)
    assert out["stats"]["ret"] == -100.0
    assert min(out["equity"]) == 0.0 and out["equity"][-1] == 0.0
    assert out["stats"]["emptied_on"] == "2026-01-05"
    assert out["stats"]["mdd"] == -100.0
    # the trades add up to the account's change, so every figure derived from them agrees
    assert math.isclose(sum(t["pnl"] for t in out["trades"]), -CAP, abs_tol=0.01)
    assert out["costs"]["net_pnl"] == -CAP
    assert not out["open_trades"]
    assert any(t.get("capped_loss") for t in out["trades"])


def test_nothing_opens_after_the_account_is_empty():
    data = [ds(s, _crash(100.0) + day("2026-01-06", [100 + i for i in range(8)])) for s in "AB"]
    out = portfolio.run(data, _group_strategy(leverage=3), max_open=2)
    assert out["stats"]["emptied_on"] == "2026-01-05"
    assert all(t["entry_t"][:10] == "2026-01-05" for t in out["trades"])
    assert out["equity"][-1] == 0.0


def test_a_group_that_does_not_empty_has_no_empty_date():
    up = day("2026-01-05", [100 + i for i in range(10)])
    out = portfolio.run([ds("A", up)], _group_strategy(perTrade=20000), max_open=1)
    assert out["stats"]["emptied_on"] is None


def test_unseen_and_bad_luck_figures_never_pass_100_percent():
    data = [ds(s, _crash(100.0) + day("2026-01-06", [20 + i for i in range(40)])) for s in "ABC"]
    out = portfolio.run(data, _group_strategy(), max_open=3)
    v = evaluate_portfolio(lambda *a: out, out, _group_strategy(), 365, 3650)
    for c in v["checks"]:
        d = c.get("data") or {}
        for k in ("yours", "p95", "worst"):
            assert d.get(k) is None or d[k] <= 100.0
    assert _trade_dd([-90000, -90000], CAP) == 100.0


def test_short_squeeze_closes_the_account_at_zero():
    """A short can lose more than the account has: it is closed when the value reaches zero, and nothing re-opens."""
    closes = [100.0] * 6 + [150, 210, 260, 100, 100, 100, 100]
    s = Strategy(side="short", entry=ALWAYS, exit=[],
                 risk={"capital": CAP, "riskPct": 1, "sl": 0, "brokerage": 0, "slippage": 0, "sizing": "capital", "perTrade": CAP,
                       "leverage": 1})
    # sized on all of the capital, a short that more than doubles loses everything
    out = backtest(bars_from(closes), s, 1)
    assert out["stats"]["ret"] >= -100.0
    assert min(out["equity"]) >= 0.0
    assert out["stats"]["emptied_on"]
    assert any(t["why"] == "Account emptied" for t in out["trades"])
    assert math.isclose(out["equity"][-1], 0.0, abs_tol=0.01)
    assert not out["open_trade"]


# ---- R13S-002: the watchlist filings answer within a bound, and say which company they couldn't read ----

class _SlowFeed:
    """OK answers at once, SLOW waits until it is released, BAD (and every name once `fail` is set) fails."""

    def __init__(self):
        import threading
        from app.intel import filings as F
        self.release, self.cache, self.fail = threading.Event(), F.TTLCache(), False

    def announcements(self, sym, days=0):
        from app.intel.net import SourceError
        if sym == "SLOW":
            self.release.wait(10)
            return []
        if sym == "BAD" or self.fail:
            raise SourceError("the exchange", "The exchange feed isn't answering right now.", busy=True)
        return []


def test_filings_overview_does_not_wait_for_one_slow_company():
    from app.intel import filings as F
    feed = _SlowFeed()
    try:
        out = F.overview(feed, ["OK", "SLOW", "BAD"], wait=0.3)
    finally:
        feed.release.set()
    assert [r["symbol"] for r in out["rows"]] == ["OK"]
    assert sorted(p.split(":")[0] for p in out["problems"]) == ["BAD", "SLOW"]


def test_filings_overview_keeps_the_last_good_row_marked_stale():
    from app.intel import filings as F
    feed = _SlowFeed()
    first = F.overview(feed, ["OK"], wait=2)
    assert first["problems"] == [] and "stale" not in first["rows"][0]
    feed.fail = True
    again = F.overview(feed, ["OK"], wait=2)
    assert [r["symbol"] for r in again["rows"]] == ["OK"] and again["rows"][0]["stale"] is True
    assert again["problems"][0].startswith("OK:")
    assert F.overview(_SlowFeed(), ["BAD"], wait=2)["rows"] == []                # another feed has no last row to show


# ---- R13S-004: a block keeps who made it and when; a re-rank can be put back ----

def test_a_block_records_who_made_it_and_when():
    from app import ai_providers as P
    from app import ai_rank as R
    R.block("groq", "m-1", True, "owner@example.com")
    info = R.block_info("groq", "m-1")
    assert info["by"] == "owner@example.com" and info["at"] > 0
    assert P._provider_view("groq", 0.0)["blocked_info"]["m-1"]["by"] == "owner@example.com"
    R._status.clear()                                                            # a restart: the record comes back with the block
    assert R.block_info("groq", "m-1")["by"] == "owner@example.com"
    R.block("groq", "m-1", False, "owner@example.com")
    assert R.block_info("groq", "m-1") is None and "groq/m-1" not in R.blocks()


def test_a_block_made_before_it_was_recorded_has_no_who_or_when():
    import json
    from app import ai_providers as P
    from app import ai_rank as R
    R.STORE.data["ai:prefs"] = json.dumps({"pins": {}, "blocks": ["groq/old-model"]})
    R._status.clear()
    assert list(R.blocks()) == ["groq/old-model"] and R.block_info("groq", "old-model") is None
    assert P._provider_view("groq", 0.0)["blocked_info"] == {"old-model": {}}


def test_the_admin_block_and_rerank_routes_keep_the_admin_and_the_old_order(monkeypatch):
    from fastapi.testclient import TestClient
    from app import ai_rank as R
    from app import main
    from app.config import settings
    monkeypatch.setattr(settings, "ADMIN_EMAILS", "owner@x.com")
    monkeypatch.setattr(settings, "GROQ_API_KEY", "k")
    main.app.dependency_overrides[main.current_profile] = lambda: {"id": "u1", "email": "owner@x.com", "_plan": "pro", "_email_verified": True}
    c = TestClient(main.app)
    try:
        r = c.post("/admin/ai/block", json={"provider": "groq", "model": "m-1"}).json()
        g = next(p for p in r["providers"] if p["name"] == "groq")
        assert g["blocked_info"]["m-1"]["by"] == "owner@x.com"
        R.status("groq").order = ["m-a", "m-b"]
        R.status("groq").ranked_at = 111.0
        monkeypatch.setattr(R, "start_rerank", lambda names, transport=None: names)
        out = c.post("/admin/ai/rerank", json={"provider": "groq"}).json()
        assert out["undo"]["groq"]["order"] == ["m-a", "m-b"] and out["undo"]["groq"]["ranked_at"] == 111.0
        R.status("groq").order = ["m-z"]                                             # what the re-rank then measured
        back = c.post("/admin/ai/rank-restore", json={"ranks": out["undo"]}).json()
        assert back["restored"] == ["groq"] and R.status("groq").order == ["m-a", "m-b"] and R.status("groq").ranked_at == 111.0
        assert c.post("/admin/ai/rank-restore", json={"ranks": {"nope": {"order": ["x"]}}}).json()["restored"] == []
        main.app.dependency_overrides[main.current_profile] = lambda: {"id": "u2", "email": "other@x.com", "_plan": "pro", "_email_verified": True}
        assert c.post("/admin/ai/rank-restore", json={"ranks": {}}).status_code == 403
    finally:
        main.app.dependency_overrides.clear()


def test_a_rerank_that_finishes_after_an_undo_leaves_the_restored_order():
    from app import ai_rank as R
    st = R.status("groq")
    st.order, st.probing = ["m-new"], True
    R.restore_rank({"groq": {"order": ["m-old"], "ranked_at": 5.0, "rank_error": None}})
    assert st.order == ["m-old"] and st.keep_order is True
    st.probing = False
    R.restore_rank({"groq": {"order": ["m-old"], "ranked_at": 5.0, "rank_error": None}})
    assert st.keep_order is False


# ---- R13S-010: the platform check writes its dates the site's way, and index levels with Indian grouping ----

def test_the_platform_check_writes_days_and_levels_for_people():
    from datetime import date
    from app import platform_check as pc
    assert pc._day(date(2026, 10, 7)) == "7 Oct"
    assert pc._day("2026-10-13") == "13 Oct"
    assert pc._day("2026-10-12T18:10:05+05:30") == "12 Oct"
    assert pc._day("soon") == "soon"
    assert pc._level(22520.45) == "22,520.45"
    assert pc._level(1234567.5) == "12,34,567.50"
    assert pc._level(None) == "–"


# ---- R13S-015: the US screen's "sector" is the SEC's industry division, and says so ----

def test_the_us_screen_calls_its_sector_what_it_is():
    from app import screens
    f = {"sector": ["Manufacturing"], "cap": [], "stage": [], "ranges": {}, "red_flags": None, "insider_buy": None, "surv_lists": None}
    assert screens.describe("US", f)[0] == "Industry (SEC division): Manufacturing"
    assert screens.describe("IN", f)[0] == "Sector: Manufacturing"
    assert "not a market sector" in screens.meta("US")["help"]["sector"]
    assert screens.meta("IN")["help"]["sector"] == screens.HELP["sector"] and "SEC" not in screens.HELP["sector"]
