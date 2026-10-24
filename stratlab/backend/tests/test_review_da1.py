"""24 Oct 2026 deep audit of turning an idea into rules and running it (DA-001 .. DA-028): an options idea refused whole, a
rule that lost its indicator read again from the words, the verdict's yearly rate and its next step for a weak result, the
unseen part named for what it is, and a default stop said on the verdict."""
from app import ai_writer, main, research
from app.engine import verdict as V
from app.models import GapsReq, Strategy
from tests.test_notebooks import EMA, api  # noqa: F401  (fixture)


def num(v):
    return {"t": "num", "v": v}


RSI60 = {"l": {"t": "rsi", "p": 14}, "op": "xa", "r": num(60)}


def _out(entry, exit_, notes=()):
    return {"entry": entry, "exit": exit_, "entryJoin": "all", "side": "long", "shortEntry": [], "shortExit": [], "risk": {},
            "mentioned": ["exit"], "notes": list(notes), "tf": "1d"}


# ---------- DA-001 / DA-009: options ideas are refused whole, with the way on ----------
def test_options_ideas_are_told_apart_from_ideas_on_a_price():
    for text in ("Buy a Nifty at-the-money call option when RSI crosses above 60 and sell when it falls below 50",
                 "Sell a Bank Nifty ATM straddle every Thursday morning",
                 "Short a strangle on Nifty when VIX is above 17", "Buy the 24000 CE when the price crosses above the 20 EMA",
                 "Run an iron condor on Nifty each week", "Write covered calls on RELIANCE", "Sell a bull call spread when RSI is above 60"):
        assert ai_writer.options_idea(text), text
    for text in ("Buy NIFTY 50 when RSI crosses above 60 and sell when it falls below 50",
                 "Buy when the price is above the 50-day average, with a 2% stop loss and risk 1% of capital",
                 "Sell short when the price falls below the lowest low of the last 20 days, with a 5% trailing stop",
                 "Buy when volume is above its average and the spread is under 0.2%", ""):
        assert not ai_writer.options_idea(text), text


def test_an_options_idea_is_refused_before_any_ai_build_is_used(api, monkeypatch):  # noqa: F811
    asked = []
    monkeypatch.setattr(main, "write_strategy", lambda text, pro: asked.append(text) or {})
    r = api.post("/ai/strategy", json={"text": "Buy a Nifty at-the-money call option when RSI crosses above 60 and sell when it falls below 50"})
    d = r.json()["detail"]
    assert r.status_code == 422 and d["code"] == "options_idea" and "Options builder" in d["message"]
    assert asked == [] and api.usage == []                      # no AI was asked, and no build counted


# ---------- DA-001: a rule never loses its subject, and a note agrees with the rules shown ----------
def test_a_rule_that_lost_its_indicator_is_read_again_from_the_words():
    text = "Buy a Nifty when RSI crosses above 60 and sell when it falls below 50"
    out = ai_writer.check_against_text(_out([RSI60], [{"l": {"t": "price"}, "op": "lt", "r": num(50)}],
                                            ["No rules could be generated for this idea."]), text)
    assert out["exit"] == [{"l": {"t": "rsi", "p": 14}, "op": "lt", "r": num(50)}]
    assert any("Price is below 50" in n and "RSI 14 is below 50" in n for n in out["notes"])
    assert not any("No rules could be generated" in n for n in out["notes"])      # rules came out: the note must not say none did


def test_a_price_rule_the_words_really_give_is_kept():
    text = "Buy when RSI 14 is below 30 and the price falls below 50"
    out = ai_writer.check_against_text(_out([{"l": {"t": "rsi", "p": 14}, "op": "lt", "r": num(30)}], [{"l": {"t": "price"}, "op": "lt", "r": num(50)}]), text)
    assert out["exit"] == [{"l": {"t": "price"}, "op": "lt", "r": num(50)}]
    both = ai_writer.check_against_text(_out([RSI60], [{"l": {"t": "price"}, "op": "lt", "r": num(50)}]), "Buy when RSI and ADX cross above 60, sell below 50")
    assert both["exit"][0]["l"] == {"t": "price"}                # two indicators named: which one the rule meant isn't clear, so it stays as it came


def test_a_note_saying_nothing_could_be_built_stays_when_nothing_was():
    out = ai_writer.check_against_text(_out([], [], ["No rules could be generated for this idea."]), "Make me rich")
    assert out["notes"] == ["No rules could be generated for this idea."]


# ---------- DA-004: the stored questions know which market a name belongs to ----------
def test_the_questions_keep_the_market_of_the_name_they_could_not_find():
    assert GapsReq(instName="RELIANCE", instMarket="IN").model_dump()["instMarket"] == "IN"
    assert GapsReq().instMarket is None


# ---------- DA-006: a short idea's next steps say sell short ----------
class _S:
    def __init__(self, side="long", sl=2, trail=0, sl_type="pct", ops=("xa",)):
        from app.models import Cond, Ref
        self.side = side
        self.entry = [Cond(l=Ref(t="price"), op=o, r=Ref(t="sma", p=20)) for o in ops]
        self.risk = Strategy(risk={"sl": sl, "stopType": sl_type}).risk


def test_a_short_ideas_next_steps_say_sell_short():
    s = V.suggestions("no_edge", _S("short"), 365, 3650)
    assert {"action": "trend_filter", "text": "Only sell short below the 200-period average"} in s
    s = V.suggestions("not_enough", _S("short"), 365, 3650)
    assert {"action": "loosen_entry", "text": "Sell short whenever the condition holds, not only on the cross"} in s
    long = V.suggestions("no_edge", _S("long"), 365, 3650)
    assert {"action": "trend_filter", "text": "Only buy above the 200-period average"} in long


# ---------- DA-021: a profitable result that trails buying and holding, or earns little a year, says so ----------
PASSED = [{"id": "unseen", "status": "pass"}, {"id": "nearby", "status": "pass"}, {"id": "shuffle", "status": "pass"}, {"id": "sample", "status": "pass"}]


def test_a_small_yearly_return_is_stated_beside_buy_and_holds_and_is_not_led_by_paper_trading():
    got = V.decide(PASSED, 60, 4.1, _S(), 1825, 3650, 66.6, years=5.0)
    assert "A year at a time, that is about +0.8% (buying and holding: +10.7%)." in got["summary"]
    assert "under 5% a year is below what a savings account or fixed deposit usually pays" in got["summary"]
    assert got["verdict"] == "edge" and got["suggestions"][0]["action"] != "paper_trade"


def test_a_strong_result_still_leads_with_paper_trading_and_a_loss_has_no_yearly_line():
    got = V.decide(PASSED, 60, 120.0, _S(), 1825, 3650, 100.0, years=5.0)
    assert got["suggestions"][0]["action"] == "paper_trade"
    assert "A year at a time" in got["summary"] and "usually pays" not in got["summary"]
    lost = V.decide(PASSED, 60, -10.0, _S(), 1825, 3650, 50.0, years=5.0)
    assert "A year at a time" not in lost["summary"]
    short_test = V.decide(PASSED, 60, 4.1, _S(), 90, 3650, 6.0, years=0.25)           # under a year: no yearly rate at all
    assert "A year at a time" not in short_test["summary"]


def test_the_yearly_rate_compounds():
    assert round(V.yearly(100.0, 2.0), 2) == 41.42
    assert V.yearly(10.0, 0.5) is None and V.yearly(-100.0, 5.0) is None


# ---------- DA-024: the unseen part is named for what it is; fixed rules were never "tuned" ----------
def test_the_unseen_check_speaks_of_the_unseen_part_not_of_tuning():
    trades = [{"pnl": 100.0}] * 6
    ok = V.unseen_check(trades, [], 10000, [False] * 6, [False] * 6, ("2021", "2024", "2024", "2026"), 100)
    assert ok["detail"] == "It kept making money on the unseen part of the period." and "tuned" not in ok["detail"]
    port = V.unseen_check(trades, [], 10000, [False] * 6, [False] * 6, ("2021", "2024", "2024", "2026"), 100, who="The portfolio")
    assert "tuned" not in port["detail"] and "unseen part" in port["detail"]
    luck = V.decide([{"id": "unseen", "status": "fail"}, {"id": "nearby", "status": "pass"}, {"id": "shuffle", "status": "pass"},
                     {"id": "sample", "status": "pass"}], 60, 10.0, _S(), 1825, 3650, 5.0, years=5.0)
    assert "tuned" not in luck["summary"] and "unseen part of the period" in luck["summary"]


# ---------- DA-008: a stop the notebook applied on its own is said on the verdict ----------
def test_a_default_stop_is_named_and_a_stated_one_is_not():
    s = Strategy(risk={"sl": 2})
    note = research.assumed_stop_note({"mentioned": ["exit"], "answered": {}}, s)
    assert note and note.startswith("A 2% stop loss was applied by default")
    assert research.assumed_stop_note({"mentioned": ["sl"], "answered": {}}, s) is None
    assert research.assumed_stop_note({"mentioned": [], "answered": {"sl": "2% (middle)"}}, s) is None
    assert research.assumed_stop_note(None, s) is None
    assert research.assumed_stop_note({"mentioned": [], "answered": {}}, Strategy(risk={"sl": 0, "trail": 5})) is None


def test_a_run_of_a_notebook_whose_idea_set_no_stop_says_so_on_its_verdict(api):  # noqa: F811
    nb = api.post("/notebooks", json={"name": "x", "strategy": EMA, "instrument": "CRYPTO:BTC-USD",
                                      "gaps": {"mentioned": ["exit"], "notes": [], "usedAI": True, "fallback": ""}}).json()
    exp = api.post(f"/notebooks/{nb['id']}/experiments", json={"days": 400}).json()["experiment"]
    assert any("stop loss was applied by default" in n for n in exp["verdict"]["notes"])
    assert "stop loss was applied by default" in exp["verdict"]["summary"]
    said = api.post("/notebooks", json={"name": "y", "strategy": EMA, "instrument": "CRYPTO:BTC-USD",
                                        "gaps": {"mentioned": ["sl"], "notes": [], "usedAI": True, "fallback": ""}}).json()
    exp = api.post(f"/notebooks/{said['id']}/experiments", json={"days": 400}).json()["experiment"]
    assert not any("by default" in n for n in exp["verdict"].get("notes", []))
