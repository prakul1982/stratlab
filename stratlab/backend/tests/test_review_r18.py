"""Round 18 review of the core strategy product (R18): a rule that can't work, and an account that lost more than it had."""
import pytest

from app import ai_writer, library, public, rule_check
from app.engine import verdict as V
from app.engine.core import Engine, backtest, cost_summary
from app.models import Cond, Strategy
from tests.test_engine import bars_from
from tests.test_notebooks import EMA, api  # noqa: F401  (fixture)


def cond(l, op, r):
    return Cond(l=l, op=op, r=r)


def num(v):
    return {"t": "num", "v": v}


DEAD = {"l": {"t": "price"}, "op": "lt", "r": num(0)}                                     # "Price is below 0"
VOLUME = {"l": {"t": "volume"}, "op": "gt", "r": {"t": "vol_sma", "p": 20}}               # "Volume is above Avg volume 20"
LOW52 = "Buy when the price touches its 52-week low and the volume is above its 20-day average, with a 4% stop loss"


# ---------- R18-002: "52-week low" is a real value, and a rule that can never be true is not run ----------
def test_a_rule_comparing_the_price_with_zero_can_never_be_true():
    assert rule_check.verdict_of(cond({"t": "price"}, "lt", num(0))) == "never"
    assert rule_check.verdict_of(cond({"t": "price"}, "xb", num(0))) == "never"
    assert rule_check.verdict_of(cond(num(0), "gt", {"t": "price"})) == "never"          # 0 above the price, written the other way
    assert rule_check.verdict_of(cond({"t": "low"}, "lt", num(-5))) == "never"
    assert rule_check.verdict_of(cond({"t": "price"}, "gt", num(0))) == "always"          # said, not refused


def test_other_rules_that_decide_themselves():
    assert rule_check.verdict_of(cond({"t": "rsi", "p": 14}, "gt", num(100))) == "never"
    assert rule_check.verdict_of(cond({"t": "rsi", "p": 14}, "lt", num(0))) == "never"
    assert rule_check.verdict_of(cond({"t": "rsi", "p": 14}, "lt", num(101))) == "always"
    assert rule_check.verdict_of(cond({"t": "stage"}, "eq", num(5))) == "never"
    assert rule_check.verdict_of(cond({"t": "price"}, "gt", {"t": "price"})) == "never"
    assert rule_check.verdict_of(cond({"t": "sma", "p": 20}, "eq", {"t": "sma", "p": 20})) == "always"
    assert rule_check.verdict_of(cond(num(1), "gt", num(2))) == "never"


def test_rules_that_can_go_either_way_are_left_alone():
    for c in (cond({"t": "price"}, "xa", {"t": "dc_lower", "p": 252}), cond({"t": "price"}, "gt", num(50)),
              cond({"t": "rsi", "p": 14}, "lt", num(30)), cond({"t": "stage"}, "eq", num(2)),
              cond({"t": "volume"}, "gt", {"t": "vol_sma", "p": 20}), cond({"t": "price", "ago": 1}, "gt", {"t": "price"}),
              cond({"t": "macd"}, "gt", num(0)), cond({"t": "day_chg"}, "lt", num(-2))):
        assert rule_check.verdict_of(c) is None, c


def test_the_reviewed_notebook_is_refused_before_it_trades(api):  # noqa: F811
    """"Any of these": Price is below 0, Volume is above Avg volume 20. The first never holds, so the second alone opened
    3,014 trades. Saved as written (and said), but a run is refused with the rule named; no experiment is kept."""
    strategy = {**EMA, "entry": [DEAD, VOLUME], "entryJoin": "any"}
    nb = api.post("/notebooks", json={"name": "52-week low", "strategy": strategy, "instrument": "CRYPTO:BTC-USD"}).json()
    assert nb["rule_problems"] == {"never": ["Price is below 0"]}
    assert api.get(f"/notebooks/{nb['id']}").json()["rule_problems"]["never"] == ["Price is below 0"]
    r = api.post(f"/notebooks/{nb['id']}/experiments", json={"days": 400})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "rule_never_true"
    assert '"Price is below 0"' in r.json()["detail"]["message"] and "can never be true" in r.json()["detail"]["message"]
    assert api.get(f"/notebooks/{nb['id']}").json()["experiments"] == [] and api.usage == []
    # mended, it runs
    fixed = api.put(f"/notebooks/{nb['id']}", json={"strategy": {**strategy, "entry": [EMA["entry"][0], VOLUME]}}).json()
    assert "rule_problems" not in fixed
    assert api.post(f"/notebooks/{nb['id']}/experiments", json={"days": 400}).status_code == 200


def test_an_ordinary_notebook_carries_no_rule_problems(api):  # noqa: F811
    nb = api.post("/notebooks", json={"name": "Trend", "strategy": EMA, "instrument": "CRYPTO:BTC-USD"}).json()
    assert "rule_problems" not in nb


def test_without_the_guard_the_old_rules_traded_on_volume_alone():
    """The engine itself is unchanged: the guard is in front of it. The dead rule is never true, the other one fires on many days."""
    closes = [100 + (i % 7) for i in range(120)]
    bars = [{**b, "v": 1000.0 + (3000.0 if i % 3 == 0 else 0.0)} for i, b in enumerate(bars_from(closes))]
    s = Strategy(entry=[DEAD, VOLUME], entryJoin="any", exit=[], risk={"capital": 100000, "sl": 1, "brokerage": 0, "slippage": 0})
    out = backtest(bars, s, 30)
    assert out["diagnostics"]["entry"][0]["true_on"] == 0 and out["diagnostics"]["entry"][1]["true_on"] > 10
    assert out["stats"]["n"] > 5
    assert rule_check.problems(s)["never"] == ["Price is below 0"]


def _ai_out(entry, join="any", tf="1d"):
    return {"entry": entry, "exit": [], "entryJoin": join, "side": "long", "shortEntry": [], "shortExit": [], "risk": {},
            "mentioned": [], "notes": [], "tf": tf}


def test_a_52_week_low_the_builder_wrote_as_zero_is_read_as_the_low_of_252_candles():
    """R18-002: the idea's 52-week low had become the number 0. The sentence names the level, so the rule is read as it."""
    out = ai_writer.check_against_text(_ai_out([DEAD, VOLUME]), LOW52)
    assert out["entry"][0] == {"l": {"t": "low"}, "op": "lt", "r": {"t": "dc_lower", "p": 252}}
    assert out["entry"][1] == VOLUME
    assert any("lowest low of the last 252 candles (52 weeks)" in n for n in out["notes"])
    assert not any("left out" in n for n in out["notes"])


def test_a_52_week_high_and_other_wordings():
    high = ai_writer.check_against_text(_ai_out([{"l": {"t": "price"}, "op": "gt", "r": num(0)}], "all"), "Buy when price closes above its 52 week high")
    assert high["entry"] == [{"l": {"t": "price"}, "op": "gt", "r": {"t": "dc_upper", "p": 252}}]
    below = ai_writer.check_against_text(_ai_out([DEAD], "all"), "Buy when the price falls below the 52-wk low")
    assert below["entry"] == [{"l": {"t": "price"}, "op": "lt", "r": {"t": "dc_lower", "p": 252}}]
    reversed_ = ai_writer.check_against_text(_ai_out([{"l": num(0), "op": "gt", "r": {"t": "price"}}], "all"), "Buy at a 52-week low")
    assert reversed_["entry"][0]["op"] == "lt" and reversed_["entry"][0]["r"]["t"] == "dc_lower"


def test_a_52_week_low_on_intraday_candles_uses_the_daily_level():
    out = ai_writer.check_against_text(_ai_out([DEAD], "all", tf="15m"), "On 15-minute candles buy when price touches the 52-week low")
    assert out["entry"][0]["r"] == {"t": "dc_lower", "p": 252, "tf": "1d"}


def test_a_zero_with_no_year_level_in_the_words_is_still_left_out_and_the_rest_is_said():
    out = ai_writer.check_against_text(_ai_out([DEAD, VOLUME]), "Buy when volume is above its average")
    assert out["entry"] == [VOLUME]
    assert any("price with 0 was left out" in n for n in out["notes"])
    assert any("decide the entry on their own" in n for n in out["notes"])
    one = ai_writer.check_against_text(_ai_out([DEAD, VOLUME], "all"), "Buy when volume is above its average")
    assert not any("on their own" in n for n in one["notes"])


def test_the_builder_prompt_names_the_52_week_level():
    assert '"52-week low" / "52-week high" = dc_lower / dc_upper with p 252' in ai_writer.SYSTEM


def test_the_read_rule_is_a_valid_rule_that_runs():
    out = ai_writer.check_against_text(_ai_out([DEAD, VOLUME]), LOW52)
    s = Strategy(entry=out["entry"], entryJoin="any", exit=[], risk={"capital": 100000, "sl": 4, "brokerage": 0, "slippage": 0})
    assert rule_check.problems(s) == {"never": [], "always": []}
    closes = [100 + (i % 9) - i * 0.1 for i in range(400)]
    assert backtest(bars_from(closes), s, 300)["diagnostics"]["candles"] > 0


# ---------- R18-008 / R17-007: an account never loses more than it had ----------
CAP = 500000
LEGACY_PNL = -1763044.0


def legacy_experiment(group=False):
    """What was stored before accounts stopped at zero (R13S-001): -352.6%, "In your pocket" -Rs17,63,044, a value curve
    down to -Rs12.6 lakh and a worst fall past -100%."""
    ret = LEGACY_PNL / CAP * 100
    checks = [
        {"id": "unseen", "title": "Unseen data", "status": "fail", "detail": "It lost money on the part of the period it hadn't seen.",
         "data": {"built_ret": -40.0, "unseen_ret": -312.6, "split_index": 3}},
        {"id": "nearby", "title": "Nearby settings", "status": "fail", "detail": "Most settings near yours lost money.", "data": None},
        {"id": "shuffle", "title": "Bad-luck drawdown", "status": "fail",
         "detail": "Your backtest fell 336.6% at worst; in 95 of 100 reshuffles of the same trades the fall was up to 340.1%, 35% or more.",
         "data": {"yours": 336.6, "p95": 340.1, "worst": 350.2, "runs": 1000, "daily": True, "by": "trades"}},
        {"id": "sample", "title": "Enough trades", "status": "pass", "detail": "Enough trades to judge.", "data": {"trades": 40}},
    ]
    strat = Strategy(entry=EMA["entry"], risk={"capital": CAP})
    verdict = V.decide(checks, 40, ret, strat, 1500, 3000, 12.0)
    e = {"v": 1, "label": "First try", "strategy": strat.model_dump(), "days": 1500, "candles": 5,
         "instrument": {"id": "IN:X", "symbol": "X", "currency": "INR", "market": "IN"},
         "stats": {"ret": ret, "pnl": LEGACY_PNL, "cagr": 0.0, "mdd": -352.6, "sharpe": -1.2, "n": 40, "win": 20.0, "pf": 0.4,
                   "avg": -44076.1, "buy_hold_ret": 12.0, "skipped_size": 0},
         "costs": {"gross_pnl": -1700000.0, "total": 63044.0, "items": [], "net_pnl": LEGACY_PNL,
                   "tax": {"amount": 0.0, "note": ""}, "kept": LEGACY_PNL},
         "verdict": verdict,
         "series": {"t": ["2024-01-01", "2024-02-01", "2024-03-01", "2024-04-01", "2024-05-01"], "close": [100, 90, 70, 50, 40],
                    "equity": [500000.0, 200000.0, -100000.0, -700000.0, -1263044.0], "buy_hold": [500000.0] * 5, "overlays": {}, "split": 3},
         "trades": [{"symbol": "A", "entry_t": "2024-01-02", "exit_t": "2024-02-01", "qty": 10, "entry": 100.0, "exit": 70.0, "pnl": -300000.0, "costs": 10.0, "side": "long"},
                    {"symbol": "A", "entry_t": "2024-02-02", "exit_t": "2024-03-01", "qty": 10, "entry": 90.0, "exit": 0.0, "pnl": -900000.0, "costs": 10.0, "side": "long"},
                    {"symbol": "B", "entry_t": "2024-03-02", "exit_t": "2024-04-01", "qty": 10, "entry": 80.0, "exit": 20.0, "pnl": -563044.0, "costs": 10.0, "side": "long"}]}
    if group:
        e["group"] = {"name": "G", "max_open": 2, "most_open": 2,
                      "members": [{"symbol": "A", "pnl": -1200000.0}, {"symbol": "B", "pnl": -563044.0}]}
    return e


def test_the_stored_run_really_passes_minus_100_before_the_fix():
    e = legacy_experiment()
    assert e["stats"]["ret"] < -350 and e["stats"]["pnl"] < -CAP and min(e["series"]["equity"]) < 0 and e["costs"]["kept"] < -CAP
    assert "−352.6%" in e["verdict"]["summary"] and sum(t["pnl"] for t in e["trades"]) == LEGACY_PNL


def test_an_account_run_past_zero_is_held_to_what_it_had():
    e = V.restate_empty(legacy_experiment())
    st, costs = e["stats"], e["costs"]
    assert st["ret"] == -100.0 and st["pnl"] == -CAP and st["mdd"] == -100.0 and st["cagr"] == -100.0
    assert st["shown_ret"] == pytest.approx(-352.6088, abs=1e-3) and st["emptied_on"] == "2024-03-01"
    assert costs["net_pnl"] == -CAP and costs["kept"] == -CAP and costs["gross_pnl"] == -CAP + 63044
    assert min(e["series"]["equity"]) == 0.0 and e["series"]["equity"][:2] == [500000.0, 200000.0]
    # one set of figures: the return, the P&L, the curve and the trades all say the same loss
    assert st["ret"] == pytest.approx(st["pnl"] / CAP * 100) and e["series"]["equity"][-1] == CAP + st["pnl"]
    assert sum(t["pnl"] for t in e["trades"]) == pytest.approx(-CAP, abs=0.01)
    # the newest losses are cut back first, each noting how much
    assert [t["pnl"] for t in e["trades"]] == [-300000.0, -200000.0, 0.0]
    assert [t.get("capped_loss") for t in e["trades"]] == [None, 700000.0, 563044.0]


def test_the_verdict_of_a_restated_run_states_the_restated_figures():
    e = V.restate_empty(legacy_experiment())
    v = e["verdict"]
    assert "352" not in v["summary"] and "352" not in v["headline"]
    assert v["summary"].endswith("The strategy returned −100.0% after costs, less than buying and holding over the same period (+12.0%).")
    assert v["headline"].startswith("112.0 points behind buy and hold after costs")
    by = {c["id"]: c for c in v["checks"]}
    assert by["unseen"]["data"]["unseen_ret"] == -100.0 and by["unseen"]["data"]["built_ret"] == -40.0
    assert all(by["shuffle"]["data"][k] <= 100.0 for k in ("yours", "p95", "worst"))
    assert "336.6%" not in by["shuffle"]["detail"] and "340.1%" not in by["shuffle"]["detail"] and "100.0%" in by["shuffle"]["detail"]
    assert [c["status"] for c in v["checks"]] == ["fail", "fail", "fail", "pass"]          # the findings themselves stand


def test_a_group_run_past_zero_keeps_its_members_adding_up():
    e = V.restate_empty(legacy_experiment(group=True))
    assert sum(m["pnl"] for m in e["group"]["members"]) == pytest.approx(-CAP, abs=0.01)
    assert e["stats"]["ret"] == -100.0


def test_a_run_that_stayed_inside_its_account_is_returned_untouched():
    e = legacy_experiment()
    e["stats"].update(ret=-60.0, pnl=-300000.0, mdd=-70.0)
    e["series"]["equity"] = [500000.0, 400000.0, 300000.0, 250000.0, 200000.0]
    assert V.restate_empty(e) is e


def test_the_notebook_page_shows_a_stored_run_held_to_100_percent(api):  # noqa: F811
    nb = api.post("/notebooks", json={"name": "Old", "strategy": EMA, "instrument": "CRYPTO:BTC-USD"}).json()
    api.rows[nb["id"]]["body"]["experiments"] = [legacy_experiment()]
    shown = api.get(f"/notebooks/{nb['id']}").json()["experiments"][0]
    assert shown["stats"]["ret"] == -100.0 and shown["costs"]["kept"] == -CAP and min(shown["series"]["equity"]) == 0.0
    assert shown["stats"]["emptied_on"] == "2024-03-01" and shown["stats"]["shown_ret"] < -350
    assert api.rows[nb["id"]]["body"]["experiments"][0]["stats"]["ret"] < -350          # what is stored is not rewritten


def test_a_shared_or_published_stored_run_is_held_to_100_percent():
    nb = {"id": "n1", "name": "Old", "question": "Did it work?", "strategy": {}}
    snap = public.snapshot(nb, legacy_experiment())
    assert snap["stats"]["ret"] == -100.0 and snap["stats"]["mdd"] == -100.0 and min(snap["series"]["equity"]) >= 0
    entry = library.entry(nb, legacy_experiment(), "u1", "A", "d")
    assert entry["stats"]["ret"] == -100.0 and entry["stats"]["mdd"] == -100.0 and "352" not in entry["verdict"]["summary"]
    # a link or an entry made before this is read with the same limit
    old = {**snap, "stats": {"ret": -352.6, "buy_hold_ret": 12.0, "mdd": -336.6, "n": 40}}
    lib = library.public({**entry, "stats": {**entry["stats"], "ret": -352.6, "mdd": -336.6}})
    assert lib["stats"]["ret"] == -100.0 and lib["stats"]["mdd"] == -100.0 and old["stats"]["ret"] == -352.6


def test_what_is_left_after_tax_is_never_less_than_the_whole_account():
    """A short-term gain taxed beside a long-term loss: the tax came on top of a loss of the whole account."""
    s = Strategy(entry=EMA["entry"], risk={"capital": CAP})
    eng = Engine(s, cost_kind="in_eq")
    eng.trades = [{"entry_t": "2025-01-01", "exit_t": "2025-02-01", "pnl": 100000.0},
                  {"entry_t": "2022-01-01", "exit_t": "2025-03-01", "pnl": -600000.0}]
    out = cost_summary(eng, "in_eq", -CAP)
    assert out["tax"]["amount"] == 20000.0 and out["kept"] == -CAP
