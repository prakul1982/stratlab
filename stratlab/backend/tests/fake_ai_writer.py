"""The AI strategy builder's replies in the browser tests (57.1): the two answers the live site gave Instinct for its
EMA-cross sentences, wrong in the way it saw them, so the page shows the rules the server's check makes of them. Any other
sentence finds no AI, as before (the simple converter reads it)."""
import json

from app.ai_providers import AIConfig

P = {"t": "price"}


def _ema(p):
    return {"t": "ema", "p": p}


REPLIES = {
    # no instrument named: the price against each line, and a sell rule on both (and a NIFTY 50 nobody named)
    "Buy when the 20 EMA crosses above the 50 EMA, sell when it crosses back below, 3% stop loss.": {
        "name": "EMA crossover", "instrument": "NIFTY 50", "market": "IN", "tf": None, "side": "long", "entryJoin": "all",
        "entry": [{"l": P, "op": "xa", "r": _ema(20)}, {"l": P, "op": "xa", "r": _ema(50)}],
        "exit": [{"l": P, "op": "lt", "r": _ema(20)}, {"l": P, "op": "lt", "r": _ema(50)}],
        "risk": {"sl": 3}, "mentioned": ["exit", "sl"], "notes": []},
    # NIFTY 50 named: the sell rule's lines the other way round
    "Buy NIFTY 50 when the 20 EMA crosses above the 50 EMA, sell when it crosses back below.": {
        "name": "NIFTY 50 EMA crossover", "instrument": "NIFTY 50", "market": "IN", "tf": "1d", "side": "long", "entryJoin": "all",
        "entry": [{"l": _ema(20), "op": "xa", "r": _ema(50)}], "exit": [{"l": _ema(50), "op": "xb", "r": P}],
        "risk": {}, "mentioned": ["exit", "instrument", "tf"], "notes": []},
}


def complete(system, text, *a, **k):
    if text.strip() in REPLIES:
        return json.dumps(REPLIES[text.strip()])
    raise AIConfig("The AI isn't set up on the server yet.")
