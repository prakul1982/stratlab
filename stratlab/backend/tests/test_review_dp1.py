"""25 Oct 2026 deep audit of the builder, the plan limits and the locks on Free and Basic (DP1-001 .. DP1-028): a build that
makes no rules costs nothing, an idea on Basic's indicators is refused by name on Free before any build is used, the AI's
"any of these" and its own stop are checked against the words, a run of an earlier set-up is not run again, and a deck is
one per company."""
import json

from app import ai_writer, main, research
from app.models import Strategy
from tests.test_notebooks import EMA, api  # noqa: F401  (fixture)

RSI = {"l": {"t": "rsi", "p": 14}, "op": "lt", "r": {"t": "num", "v": 30}}


def _out(entry, exit_=(), join="all", risk=None, mentioned=("exit",), notes=()):
    return {"entry": list(entry), "exit": list(exit_), "entryJoin": join, "side": "long", "shortEntry": [], "shortExit": [],
            "risk": dict(risk or {}), "mentioned": list(mentioned), "notes": list(notes), "tf": "1d"}


def _free(api):  # noqa: F811
    api.profile.update({"_plan": "free", "plan": "free"})


# ---------- DP1-001: a build that makes no rules is not counted ----------
def test_a_sentence_that_is_not_a_strategy_costs_no_build(api, monkeypatch):  # noqa: F811
    monkeypatch.setattr(main, "write_strategy", lambda text, pro: _out([], notes=["No rules could be generated."]))
    r = api.post("/ai/strategy", json={"text": "what is the weather in Paris tomorrow"})
    assert r.status_code == 200 and r.json()["entry"] == []
    assert api.usage == [] and r.json()["usage"]["ai_used"] == 0           # nothing made, nothing counted, and the count says so


def test_a_build_that_makes_rules_is_counted_once(api, monkeypatch):  # noqa: F811
    monkeypatch.setattr(main, "write_strategy", lambda text, pro: _out([RSI]))
    r = api.post("/ai/strategy", json={"text": "Buy when RSI 14 is below 30"})
    assert r.status_code == 200 and api.usage == ["ai"] and r.json()["usage"]["ai_used"] == 1


def test_an_import_that_finds_no_entry_rule_costs_no_build(api, monkeypatch):  # noqa: F811
    monkeypatch.setattr(main, "write_strategy", lambda text, pro: {**_out([]), "locked": []})
    r = api.post("/import/strategy", json={"text": "Some notes about my week, nothing about trading at all"})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "nothing_imported" and api.usage == []


# ---------- DP1-006: the AI's notes about "the user" are its own reasoning ----------
def test_the_ais_third_person_notes_are_not_shown():
    assert not ai_writer.user_note("User asked about weather, not a trading strategy.")
    assert not ai_writer.user_note("The user wants a forecast.")
    assert ai_writer.user_note("Order types can't be tested, so that part was left out.")


# ---------- DP1-002, DP1-003: an idea on Basic's indicators is refused whole on Free, by name, for free ----------
def test_basic_indicators_named_in_the_words_are_found():
    assert ai_writer.locked_named("Buy Bitcoin when the MACD line crosses above its signal line") == ["MACD"]
    assert ai_writer.locked_named("Short Bitcoin when the price falls below the lowest low of the last 20 days, with a 5% trailing stop") \
        == ["the highest high or lowest low of past candles"]
    assert ai_writer.locked_named("Buy when it's in Stage 2 and the price is above the Supertrend") == ["Supertrend", "the market stage (Stage 2)"]
    assert ai_writer.locked_named("Buy when it touches its 52-week low") == ["the highest high or lowest low of past candles"]
    for text in ("Buy when the 20 EMA crosses above the 50 EMA, stop loss 2%", "Buy when RSI drops below 30, sell when it goes back above 55",
                 "Buy when price is above the 200-day average and RSI crosses above 50", "At this stage I want to buy dips"):
        assert ai_writer.locked_named(text) == [], text
    msg = ai_writer.locked_message(["MACD"])
    assert msg.startswith("MACD is on the Basic plan.") and "No AI build was used" in msg


def test_on_free_a_macd_idea_is_refused_by_name_before_any_build(api, monkeypatch):  # noqa: F811
    _free(api)
    asked = []
    monkeypatch.setattr(main, "write_strategy", lambda text, pro: asked.append(text) or _out([RSI]))
    r = api.post("/ai/strategy", json={"text": "Buy Bitcoin when the MACD line crosses above its signal line, sell when it crosses back below"})
    d = r.json()["detail"]
    assert r.status_code == 402 and d["code"] == "indicator_plan" and d["message"].startswith("MACD is on the Basic plan.")
    assert asked == [] and api.usage == []
    api.profile.update({"_plan": "basic", "plan": "basic"})      # Basic builds it
    assert api.post("/ai/strategy", json={"text": "Buy when the MACD line crosses above its signal line"}).status_code == 200


def test_on_free_rules_the_ai_made_with_a_basic_indicator_are_refused_not_charged(api, monkeypatch):  # noqa: F811
    _free(api)
    answer = {"entry": [{"l": {"t": "price"}, "op": "gt", "r": {"t": "open"}}], "exit": [], "entryJoin": "all", "mentioned": []}
    monkeypatch.setattr(ai_writer, "complete", lambda *a, **k: json.dumps(answer))
    out = ai_writer.write_strategy("Buy on a green candle", pro=False)
    assert out["entry"] == [] and out["locked"] == ["the candle's open, high, low and wicks"]
    r = api.post("/ai/strategy", json={"text": "Buy on a green candle"})
    assert r.status_code == 402 and r.json()["detail"]["code"] == "indicator_plan" and api.usage == []


# ---------- DP1-005: "and" means all of them, and no stop the words didn't ask for ----------
def test_rules_joined_by_and_all_have_to_hold():
    macd = {"l": {"t": "macd"}, "op": "xa", "r": {"t": "macd_signal"}}
    vwap = {"l": {"t": "price"}, "op": "gt", "r": {"t": "vwap", "p": 20}}
    out = ai_writer.check_against_text(_out([macd, vwap], join="any"), "Buy when MACD crosses above signal and price is above VWAP")
    assert out["entryJoin"] == "all" and any('join them with "and"' in n for n in out["notes"])
    kept = ai_writer.check_against_text(_out([macd, vwap], join="any"), "Buy when MACD crosses above signal or price is above VWAP")
    assert kept["entryJoin"] == "any"


def test_a_stop_the_words_never_asked_for_is_left_to_the_app():
    out = ai_writer.check_against_text(_out([RSI], risk={"sl": 2}, mentioned=["exit", "sl"]), "Buy when RSI 14 is below 30")
    assert "sl" not in out["risk"] and "sl" not in out["mentioned"]
    said = ai_writer.check_against_text(_out([RSI], risk={"sl": 2}, mentioned=["sl"]), "Buy when RSI 14 is below 30, 2% stop loss")
    assert said["risk"]["sl"] == 2 and "sl" in said["mentioned"]
    up = ai_writer.check_against_text(_out([RSI], risk={"tgt": 5}, mentioned=["tgt"]), "Buy when RSI 14 is below 30 and sell once it's up 5%")
    assert up["risk"]["tgt"] == 5                                # the number is in the words: a target they asked for


# ---------- DP1-011: a name as the person would write it ----------
def test_the_ais_name_has_no_underscores(monkeypatch):
    monkeypatch.setattr(ai_writer, "complete", lambda *a, **k: json.dumps({"name": "MACD_VWAP_BTC", "entry": [RSI], "exit": []}))
    assert ai_writer.write_strategy("Buy when RSI 14 is below 30", pro=True)["name"] == "MACD VWAP BTC"


# ---------- DP1-009: the same set-up as an earlier run of today is not run again ----------
def test_an_earlier_run_of_today_with_the_same_setup_is_named():
    s = Strategy(**EMA)
    other = Strategy(**{**EMA, "risk": {**EMA.get("risk", {}), "sl": 7}})
    now = "2026-10-25T10:00:00+05:30"
    e = lambda v, st: {"v": v, "created_at": now, "strategy": st.model_dump(), "instrument": {"id": "CRYPTO:BTC-USD"}, "days": 365}  # noqa: E731
    exps = [e(6, s), e(7, other), e(8, other)]
    assert research.unchanged(exps, s, "CRYPTO:BTC-USD", 365, now) == 6
    assert research.unchanged(exps, other, "CRYPTO:BTC-USD", 365, now) == 8
    assert research.unchanged(exps, s, "CRYPTO:ETH-USD", 365, now) is None
    assert research.unchanged([{**exps[0], "created_at": "2026-10-24T10:00:00+05:30"}], s, "CRYPTO:BTC-USD", 365, now) is None
