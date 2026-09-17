"""AI strategy writer (Pro): plain English -> validated rule JSON."""
import json
import re
import anthropic
from pydantic import ValidationError
from .config import settings
from .models import Cond, Risk

SYSTEM = """You turn an Indian retail trader's strategy description into JSON rules for a backtesting engine.
The engine is LONG ONLY: it buys, then sells to close. Reply with ONLY a JSON object, no prose, no code fences.

Schema:
{
  "name": short strategy name,
  "tf": "1d" | "1h" | "15m" | "5m",
  "entryJoin": "all" | "any",
  "entry": [Cond, ...],
  "exit": [Cond, ...],
  "risk": {"sl": stop loss %, "tgt": target % (0 = none), "riskPct": % of capital risked per trade, "capital": rupees},
  "notes": list of short strings: anything you could not express, assumptions you made, or parts ignored (e.g. short selling)
}
Cond = {"l": Ref, "op": "xa" | "xb" | "gt" | "lt", "r": Ref}   (xa = crosses above, xb = crosses below)
Ref  = {"t": type, "p": period, "m": second parameter, "v": number}
types: "price" (close), "num" (a constant in v), "sma", "ema", "rsi" (p = length),
       "macd", "macd_signal", "macd_hist" (p = fast length, default 12; m = slow length, default 26; signal is 9),
       "bb_upper", "bb_mid", "bb_lower" (p = length, m = std-devs),
       "vwap" (p = length for daily candles), "supertrend" (p = ATR length, m = multiplier).
Only include risk fields the user mentioned. Only include tf if the user mentioned a timeframe.
If nothing can be expressed, return {"entry": [], "exit": [], "notes": ["reason"]}."""


class AIError(Exception):
    pass


def write_strategy(text: str) -> dict:
    if not settings.ANTHROPIC_API_KEY:
        raise AIError("The AI writer is not configured on the server.")
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    msg = client.messages.create(
        model=settings.ANTHROPIC_MODEL, max_tokens=1500, system=SYSTEM,
        messages=[{"role": "user", "content": text}],
    )
    raw = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.M).strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise AIError("The AI reply could not be read. Try rephrasing the strategy.")
    out = {"notes": [str(n) for n in data.get("notes", [])][:8]}
    try:
        out["entry"] = [Cond(**c).model_dump(exclude_none=True) for c in data.get("entry", [])][:10]
        out["exit"] = [Cond(**c).model_dump(exclude_none=True) for c in data.get("exit", [])][:10]
    except ValidationError:
        raise AIError("The AI produced rules the engine can't run. Try describing it more simply.")
    if data.get("entryJoin") in ("all", "any"):
        out["entryJoin"] = data["entryJoin"]
    if data.get("tf") in ("1d", "1h", "15m", "5m"):
        out["tf"] = data["tf"]
    if isinstance(data.get("name"), str):
        out["name"] = data["name"][:80]
    risk = {k: v for k, v in (data.get("risk") or {}).items() if k in Risk.model_fields}
    try:
        Risk(**risk)
        out["risk"] = risk
    except ValidationError:
        out["notes"].append("Some risk settings were out of range and were skipped.")
    return out
