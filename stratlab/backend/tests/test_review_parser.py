"""57.1 (Instinct deep QA, 1 Nov, "the core promise"): the AI idea reader must never be silently wrong. The AI's answers below
are the ones the live site gave (the parsed-rule chips Instinct photographed, 3/3 and 2/2 identical: the cached answer), and
others as wrong; every phrasing must come out with exactly the rules its words state, whatever the AI said. With no
instrument named none is picked; what the reading supplied is said under "assumed"; the sides read from the words under
"confirmed"."""
import inspect
import json

import pytest

from app import ai_writer, idea_read, main
from tests.test_notebooks import api  # noqa: F401  (fixture)

P = {"t": "price"}


def ema(p):
    return {"t": "ema", "p": p}


def sma(p):
    return {"t": "sma", "p": p}


def num(v):
    return {"t": "num", "v": v}


def rule(l, op, r):
    return {"l": l, "op": op, "r": r}


RSI = {"t": "rsi", "p": 14}
HIGH52 = {"t": "dc_upper", "p": 252}


def _ai(entry, exit_=(), risk=None, instrument=None, market=None, mentioned=("exit",), tf=None):
    return {"name": "Idea", "instrument": instrument, "market": market, "tf": tf, "side": "long", "entryJoin": "all",
            "entry": list(entry), "exit": list(exit_), "risk": dict(risk or {}), "mentioned": list(mentioned), "notes": []}


# Instinct's own two answers, as the chips showed them
INSTINCT_NO_INSTRUMENT = _ai([rule(P, "xa", ema(20)), rule(P, "xa", ema(50))], [rule(P, "lt", ema(20)), rule(P, "lt", ema(50))],
                             risk={"sl": 3}, instrument="NIFTY 50", market="IN", mentioned=("exit", "sl"))
INSTINCT_NIFTY = _ai([rule(ema(20), "xa", ema(50))], [rule(ema(50), "xb", P)], instrument="NIFTY 50", market="IN",
                     mentioned=("exit", "instrument"), tf="1d")


def _swap(c):
    return {"l": c["r"], "op": c["op"], "r": c["l"]}


def wrong_answers(entry, exit_, instrument):
    """What a model has been seen to do with such words: the right buy rule with the sell rule's lines swapped, both
    sides' lines swapped, the price set against each line, and nothing at all."""
    out = [_ai(entry, [_swap(c) for c in exit_] or [rule(P, "lt", num(1))], instrument=instrument or "NIFTY 50", market="IN"),
           _ai([_swap(c) if c["r"]["t"] != "num" else c for c in entry], [_swap(c) for c in exit_], instrument=instrument),
           _ai([rule(P, "xa", ref) for c in entry for ref in (c["l"], c["r"]) if ref["t"] not in ("price", "num")] or [rule(P, "gt", num(5))],
               [rule(P, "lt", ref) for c in exit_ for ref in (c["l"], c["r"]) if ref["t"] not in ("price", "num")], instrument=instrument),
           _ai([], [], instrument=instrument)]
    return out


# (words, the buy rules, the sell rules, the risk the words give, the instrument they name)
MATRIX = [
    ("Buy when the 20 EMA crosses above the 50 EMA, sell when it crosses back below, 3% stop loss.",
     [rule(ema(20), "xa", ema(50))], [rule(ema(20), "xb", ema(50))], {"sl": 3}, None),
    ("Buy NIFTY 50 when the 20 EMA crosses above the 50 EMA, sell when it crosses back below.",
     [rule(ema(20), "xa", ema(50))], [rule(ema(20), "xb", ema(50))], {}, "NIFTY 50"),
    ("Buy RELIANCE when the price crosses above its 20-day average, and sell when it crosses back below.",
     [rule(P, "xa", sma(20))], [rule(P, "xb", sma(20))], {}, "RELIANCE"),
    ("buy when the 20 EMA crosses above the 50 EMA and sell when it crosses back below",
     [rule(ema(20), "xa", ema(50))], [rule(ema(20), "xb", ema(50))], {}, None),
    ("buy when RSI goes under 30, sell when it gets back above 70",
     [rule(RSI, "xb|lt", num(30))], [rule(RSI, "xa|gt", num(70))], {}, None),
    ("go long on a breakout above the 52-week high, exit if it falls 8%",
     [rule(P, "xa", HIGH52)], [], {"sl": 8}, None),
    ("buy when price closes above the 200 DMA, sell when it closes back under it",
     [rule(P, "gt", sma(200))], [rule(P, "lt", sma(200))], {}, None),
    # the same five on a named instrument, before and after the rules
    ("buy when the 20 EMA crosses above the 50 EMA and sell when it crosses back below on NIFTY",
     [rule(ema(20), "xa", ema(50))], [rule(ema(20), "xb", ema(50))], {}, "NIFTY 50"),
    ("buy when RSI goes under 30, sell when it gets back above 70 on RELIANCE",
     [rule(RSI, "xb|lt", num(30))], [rule(RSI, "xa|gt", num(70))], {}, "RELIANCE"),
    ("On NIFTY, go long on a breakout above the 52-week high, exit if it falls 8%",
     [rule(P, "xa", HIGH52)], [], {"sl": 8}, "NIFTY 50"),
    ("buy RELIANCE when price closes above the 200 DMA, sell when it closes back under it",
     [rule(P, "gt", sma(200))], [rule(P, "lt", sma(200))], {}, "RELIANCE"),
    ("On RELIANCE, buy when the 20 EMA crosses above the 50 EMA and sell when it crosses back below",
     [rule(ema(20), "xa", ema(50))], [rule(ema(20), "xb", ema(50))], {}, "RELIANCE"),
    ("Buy NIFTY when RSI goes under 30, sell when it gets back above 70",
     [rule(RSI, "xb|lt", num(30))], [rule(RSI, "xa|gt", num(70))], {}, "NIFTY 50"),
    ("go long on RELIANCE on a breakout above the 52-week high, exit if it falls 8%",
     [rule(P, "xa", HIGH52)], [], {"sl": 8}, "RELIANCE"),
    ("buy when price closes above the 200 DMA, sell when it closes back under it on NIFTY",
     [rule(P, "gt", sma(200))], [rule(P, "lt", sma(200))], {}, "NIFTY 50"),
    ("Buy NIFTY 50 when the 20 EMA crosses above the 50 EMA, sell when it crosses back below, 3% stop loss.",
     [rule(ema(20), "xa", ema(50))], [rule(ema(20), "xb", ema(50))], {"sl": 3}, "NIFTY 50"),
]


def _eq(got, want):
    """The rules got are the ones wanted, in any order, 20 and 20.0 being one length. An op written "xb|lt" is a move verb
    ("goes under 30"): read as a crossing, and an AI answer that took it as the state on the same two lines is kept."""
    ref = lambda r: json.dumps({k: float(v) if isinstance(v, (int, float)) else v for k, v in r.items()}, sort_keys=True)  # noqa: E731
    left = [(ref(c["l"]), c["op"], ref(c["r"])) for c in got]
    if len(left) != len(want) or any(set(c) - {"l", "op", "r"} for c in got):
        return False
    for c in want:
        hit = next((k for k in left if k[0] == ref(c["l"]) and k[2] == ref(c["r"]) and k[1] in c["op"].split("|")), None)
        if hit is None:
            return False
        left.remove(hit)
    return True


def _build(api, monkeypatch, words, answer):  # noqa: F811
    monkeypatch.setattr(ai_writer, "complete", lambda *a, **k: json.dumps(answer))
    r = api.post("/ai/strategy", json={"text": words})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.parametrize("words,entry,exit_,risk,named", MATRIX, ids=[m[0][:60] for m in MATRIX])
def test_every_phrasing_comes_out_exactly_as_its_words_say_whatever_the_ai_answered(api, monkeypatch, words, entry, exit_, risk, named):  # noqa: F811
    first = lambda rs: [{**c, "op": c["op"].split("|")[0]} for c in rs]      # noqa: E731
    entry_, exit_1 = first(entry), first(exit_)
    answers = [_ai(entry_, exit_1, risk=risk, instrument=named, market="IN" if named else None)] + wrong_answers(entry_, exit_1, named)
    if words.startswith("Buy when the 20 EMA crosses above the 50 EMA, sell when"):
        answers.append(INSTINCT_NO_INSTRUMENT)
    if words.startswith("Buy NIFTY 50 when the 20 EMA"):
        answers.append(INSTINCT_NIFTY)
    for answer in answers:
        got = _build(api, monkeypatch, words, answer)
        assert _eq(got["entry"], entry), (answer, got["entry"])
        assert _eq(got["exit"], exit_), (answer, got["exit"])
        assert got["entryJoin"] == "all" and got["side"] == "long"
        for k, v in risk.items():
            assert got["risk"][k] == v and k in got["mentioned"], (answer, got["risk"])
        # a way out was said (a sell rule, or the stop the words give): the notebook doesn't ask for one or add its own
        assert "exit" in got["mentioned"]
        assert set(got["confirmed"]) == {"entry", "exit"}
        if named is None:
            # no stock, index or coin in the words: none is picked, so the notebook asks "Which stock or index?"
            assert got["instrument"] is None and "instrument" not in got["mentioned"], answer
        elif answer["instrument"]:
            assert got["instrument"] == answer["instrument"]


def test_instincts_two_answers_are_corrected_and_said():
    words = "Buy when the 20 EMA crosses above the 50 EMA, sell when it crosses back below, 3% stop loss."
    got = ai_writer.check_against_text(json.loads(json.dumps(INSTINCT_NO_INSTRUMENT)), words)
    assert got["entry"] == [rule(ema(20), "xa", ema(50))] and got["exit"] == [rule(ema(20), "xb", ema(50))]
    assert got["instrument"] is None and got["risk"]["sl"] == 3
    assert "The buy rule was read from your words: EMA 20 crosses above EMA 50. The AI had read it differently." in got["notes"]
    assert "The sell rule was read from your words: EMA 20 crosses below EMA 50. The AI had read it differently." in got["notes"]
    assert any("name no stock, index or coin" in n for n in got["notes"])
    # with NIFTY 50 named: the buy rule was right; the sell rule's lines were the other way round ("EMA 50 crosses below Price")
    got = ai_writer.check_against_text(json.loads(json.dumps(INSTINCT_NIFTY)),
                                       "Buy NIFTY 50 when the 20 EMA crosses above the 50 EMA, sell when it crosses back below.")
    assert got["exit"] == [rule(ema(20), "xb", ema(50))] and got["instrument"] == "NIFTY 50"
    assert not any("buy rule was read" in n for n in got["notes"])          # what was right is left alone, and not said


def test_a_right_answer_is_left_alone_with_no_note():
    for words, entry, exit_, risk, named in MATRIX:
        for ops in (0, -1):                       # either reading of a move verb ("goes under 30": crosses, or is, below)
            pick = lambda rs: [{**c, "op": c["op"].split("|")[ops]} for c in rs]      # noqa: E731
            got = ai_writer.check_against_text(_ai(pick(entry), pick(exit_), risk=risk, instrument=named), words)
            assert _eq(got["entry"], pick(entry)) and _eq(got["exit"], pick(exit_)), words
            assert not any("read from your words" in n for n in got["notes"]), words


def test_what_the_reading_supplied_is_said_as_assumed():
    got = ai_writer.check_against_text(_ai([]), "buy when RSI goes under 30, sell when it gets back above 70")
    assert got["assumed"] == ["RSI is read over 14 candles, its usual length: your words give none."]
    got = ai_writer.check_against_text(_ai([]), "Buy RELIANCE when the price crosses above its 20-day average, and sell when it crosses back below.")
    assert any("simple moving average (SMA)" in a for a in got["assumed"])
    got = ai_writer.check_against_text(_ai([]), "buy when price closes above the 200 DMA, sell when it closes back under it")
    assert got["assumed"] == ['"200 DMA" is read as the 200-day simple moving average (SMA).']
    got = ai_writer.check_against_text(_ai([]), "go long on a breakout above the 52-week high, exit if it falls 8%")
    assert got["assumed"] == ['"it falls 8%" is read as a stop loss 8% under the price the trade was bought at.']
    # lengths the words give are not assumptions
    assert ai_writer.check_against_text(_ai([]), "Buy when RSI 14 drops below 30, sell when it rises above 55")["assumed"] == []


def test_a_pointing_back_sell_rule_that_could_mean_two_buy_rules_is_asked_not_guessed():
    words = "Buy when the 20 EMA crosses above the 50 EMA and the price crosses above the 200 SMA, sell when it crosses back below"
    got = ai_writer.check_against_text(_ai([rule(ema(20), "xa", ema(50)), rule(P, "xa", sma(200))], [rule(sma(200), "xb", P)]), words)
    assert got["exit"] == [] and "exit" not in got["mentioned"]               # the notebook's "When should it sell?" asks
    assert any("Pick the sell rule below" in n for n in got["notes"])


def test_a_sell_rule_pointing_back_is_held_to_the_ais_buy_rule_when_the_buy_words_arent_ours_to_read():
    # Stage 2 and the Supertrend are the AI's to read; "crosses back below" still takes the buy rule's own lines, in order
    words = "Buy when it's in Stage 2 and the price is above the Supertrend, sell when it crosses back below"
    st = {"t": "supertrend", "p": 10, "m": 3}
    got = ai_writer.check_against_text(_ai([rule({"t": "stage", "p": 150, "m": 20}, "eq", num(2)), rule(P, "gt", st)], [rule(st, "xb", P)]), words)
    assert got["exit"] == [rule(P, "xb", st)] and got["confirmed"] == ["exit"]
    assert len(got["entry"]) == 2                                            # the AI's buy rules stand


def test_a_sell_rule_the_words_never_give_is_left_out_and_asked():
    got = ai_writer.check_against_text(_ai([rule(ema(20), "xa", ema(50))], [rule(ema(20), "xb", ema(50))], risk={"sl": 2}),
                                       "Buy when the 20 EMA crosses above the 50 EMA, stop loss 2%")
    assert got["exit"] == [] and "exit" not in got["mentioned"] and got["risk"]["sl"] == 2
    assert any("give no sell rule" in n for n in got["notes"])


def test_words_it_cant_read_leave_the_ais_rules_as_they_are():
    for words in ("Short when the price falls below the lowest low of the last 20 days, with a 5% trailing stop",
                  "Buy when the MACD line crosses above its signal line, sell when it crosses back below",
                  "Buy when RSI is below 30 or the price is below the 20-day low",
                  "Buy the dip in a bull market"):
        answer = _ai([rule(P, "gt", num(1))], [rule(P, "lt", num(1))], instrument="NIFTY 50")
        got = ai_writer.check_against_text(json.loads(json.dumps(answer)), words)
        assert not any("read from your words" in n for n in got["notes"]), words
        assert got["confirmed"] == [] or "entry" not in got["confirmed"], words


def test_the_reader_covers_the_examples_the_app_offers_without_misreading_them():
    plain = lambda rs: [{k: v for k, v in c.items() if k != "soft"} for c in rs]      # noqa: E731
    # every example idea the builder offers, read word for word or left to the AI, never misread
    assert idea_read.read("Buy when the 20 EMA crosses above the 50 EMA, stop loss 2%")["entry"] == [rule(ema(20), "xa", ema(50))]
    got = idea_read.read("Buy when RSI drops below 30, sell when it goes back above 55")
    assert plain(got["entry"]) == [rule(RSI, "xb", num(30))] and plain(idea_read.resolve_exit(got["exit"], got["entry"])) == [rule(RSI, "xa", num(55))]
    got = idea_read.read("Buy when price is above the 200-day average and RSI crosses above 50")
    assert got["entry"] == [rule(P, "gt", sma(200)), rule(RSI, "xa", num(50))] and not got["said_exit"]
    assert idea_read.read("Short when the price falls below the lowest low of the last 20 days, with a 5% trailing stop") is None
    assert idea_read.read("Buy when it's in Stage 2 and the price is above the Supertrend, sell when it crosses back below")["entry"] is None
    got = idea_read.read("Buy when 20 EMA crosses above 50 EMA. Sell when 20 EMA crosses below 50 EMA. Stop loss 2%, target 6%, risk 1% of capital.")
    assert got["exit"] == [rule(ema(20), "xb", ema(50))] and got["risk"] == {"sl": 2, "tgt": 6}
    got = idea_read.read("Buy when the 20 EMA crosses above the 50 EMA and RSI is above 50, sell when it crosses back, 2% stop")
    assert idea_read.resolve_exit(got["exit"], got["entry"]) == [rule(ema(20), "xb", ema(50))]


def test_the_check_runs_after_the_ai_and_the_ai_stays_on_its_providers():
    assert "ai_writer.check_against_text(out, req.text)" in inspect.getsource(main.ai_strategy)
    assert "_from_the_words(out, text, notes)" in inspect.getsource(ai_writer.check_against_text)
    src = inspect.getsource(idea_read)
    assert "import" not in src.replace("import re", "")                  # no model, no network: the words alone
    assert "complete(system, text, gemini=_gemini, anthropic=_anthropic" in inspect.getsource(ai_writer.write_strategy)
