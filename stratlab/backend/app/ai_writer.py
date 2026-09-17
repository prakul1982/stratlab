"""AI strategy builder (all plans, monthly limits in plans.py).
Plain English -> validated rules, plus what the user did and didn't specify,
so the app can ask follow-up questions for the missing parts."""
import json
import re
import time

import httpx
from pydantic import ValidationError

from .config import settings
from .models import Cond, Risk

BASIC_TYPES = '"price", "num", "sma", "ema", "rsi"'
PRO_TYPES = ('"price", "num", "sma", "ema", "rsi", "macd", "macd_signal", "macd_hist", '
             '"bb_upper", "bb_mid", "bb_lower", "vwap", "supertrend"')

SYSTEM = """You turn an Indian retail trader's strategy idea into JSON rules for a backtesting engine.
The engine is LONG ONLY: it buys, then sells to close. Reply with ONLY a JSON object.

Schema:
{
  "name": short strategy name (max 6 words),
  "instrument": the stock or index the user named, as an NSE trading symbol or index name
                (e.g. "NIFTY 50", "NIFTY BANK", "RELIANCE", "TATAMOTORS"), or null if not named,
  "tf": "1d" | "1h" | "15m" | "5m" or null if the user gave no timeframe,
  "entryJoin": "all" | "any",
  "entry": [Cond, ...],
  "exit": [Cond, ...],
  "risk": {"sl": stop loss %, "tgt": target %, "riskPct": % of capital risked per trade, "capital": rupees}
          (include ONLY the fields the user actually stated),
  "mentioned": list of what the user explicitly specified, from:
               "instrument", "tf", "exit", "sl", "tgt", "riskPct", "capital",
  "notes": short plain-English notes on anything you could not express or had to assume
}
Cond = {"l": Ref, "op": "xa" | "xb" | "gt" | "lt", "r": Ref}
  xa = crosses above (true only on the crossing candle), xb = crosses below,
  gt = is above (true on every candle it stays above), lt = is below.
  Use "gt"/"lt" when the user says "above"/"below", and "xa"/"xb" only when they say cross/break/move above.
Ref = {"t": type, "p": period, "m": second parameter, "v": number}
Allowed types for this user: %TYPES%
  "price" = close price, "num" = a constant in "v", sma/ema/rsi use "p" as the length,
  macd types: p = fast (12), m = slow (26); bb types: p = length, m = std-devs; vwap: p = length;
  supertrend: p = ATR length, m = multiplier.
If the user asks for an indicator that is not allowed, leave it out and say so in notes.
Short selling is not supported: note it and ignore that part.
Never invent exits, stops or targets the user did not ask for; the app will ask them.
If nothing can be expressed, return {"entry": [], "exit": [], "mentioned": [], "notes": ["reason"]}."""


class AIError(Exception):
    pass


class AIBusy(AIError):
    """Quota or rate limit hit; the app falls back to the simple converter."""


def _gemini(system: str, text: str) -> str:
    if not settings.GEMINI_API_KEY:
        raise AIError("The AI builder isn't set up yet: GEMINI_API_KEY is missing in Railway.")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{settings.GEMINI_MODEL}:generateContent"
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": text}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.1, "maxOutputTokens": 2048},
    }
    for attempt in range(2):
        r = httpx.post(url, json=body, headers={"x-goog-api-key": settings.GEMINI_API_KEY}, timeout=45)
        if r.status_code == 429:
            if attempt == 0:
                time.sleep(2)
                continue
            raise AIBusy("The AI builder is busy right now.")
        if r.status_code >= 400:
            try:
                detail = r.json().get("error", {}).get("message", "")
            except ValueError:
                detail = r.text[:200]
            if r.status_code in (400, 403) and "key" in detail.lower():
                raise AIError("The Gemini API key on the server is invalid. Check GEMINI_API_KEY in Railway.")
            if r.status_code == 404:
                raise AIError(f"The Gemini model '{settings.GEMINI_MODEL}' isn't available for this key. Set GEMINI_MODEL in Railway to a model listed in AI Studio.")
            raise AIError(f"The AI service returned an error ({r.status_code}): {detail[:160]}")
        data = r.json()
        try:
            return "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"])
        except (KeyError, IndexError):
            raise AIError("The AI didn't return a strategy. Try rephrasing it.")
    raise AIBusy("The AI builder is busy right now.")


def _anthropic(system: str, text: str) -> str:
    import anthropic
    if not settings.ANTHROPIC_API_KEY:
        raise AIError("The AI builder isn't configured on the server.")
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    try:
        msg = client.messages.create(model=settings.ANTHROPIC_MODEL, max_tokens=1500, system=system,
                                     messages=[{"role": "user", "content": text}])
    except anthropic.RateLimitError:
        raise AIBusy("The AI builder is busy right now.")
    return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")


def write_strategy(text: str, pro: bool) -> dict:
    system = SYSTEM.replace("%TYPES%", PRO_TYPES if pro else BASIC_TYPES)
    raw = (_anthropic if settings.AI_PROVIDER == "anthropic" else _gemini)(system, text)
    raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.M).strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise AIError("The AI reply couldn't be read. Try rephrasing the idea.")
    out = {"notes": [str(n) for n in (data.get("notes") or [])][:8]}
    allowed = None if pro else {"price", "num", "sma", "ema", "rsi"}

    def conds(items):
        res = []
        for c in items or []:
            try:
                cond = Cond(**c)
            except (ValidationError, TypeError):
                continue
            if allowed and (cond.l.t not in allowed or cond.r.t not in allowed):
                out["notes"].append("Advanced indicators (MACD, Bollinger, VWAP, Supertrend) need the Pro plan, so that part was left out.")
                continue
            res.append(cond.model_dump(exclude_none=True))
        return res[:10]

    out["entry"] = conds(data.get("entry"))
    out["exit"] = conds(data.get("exit"))
    out["entryJoin"] = data.get("entryJoin") if data.get("entryJoin") in ("all", "any") else "all"
    out["tf"] = data.get("tf") if data.get("tf") in ("1d", "1h", "15m", "5m") else None
    out["name"] = str(data.get("name") or "")[:80] or None
    out["instrument"] = str(data["instrument"])[:40] if data.get("instrument") else None
    risk = {k: v for k, v in (data.get("risk") or {}).items() if k in ("sl", "tgt", "riskPct", "capital") and isinstance(v, (int, float))}
    try:
        Risk(**risk)
        out["risk"] = risk
    except ValidationError:
        out["risk"] = {}
        out["notes"].append("Some risk numbers were out of range and were skipped.")
    valid = {"instrument", "tf", "exit", "sl", "tgt", "riskPct", "capital"}
    mentioned = {m for m in (data.get("mentioned") or []) if m in valid}
    # keep "mentioned" honest with what was actually parsed
    mentioned |= {k for k in out["risk"]}
    if out["exit"]:
        mentioned.add("exit")
    if out["tf"]:
        mentioned.add("tf")
    if out["instrument"]:
        mentioned.add("instrument")
    out["mentioned"] = sorted(mentioned)
    out["notes"] = list(dict.fromkeys(out["notes"]))
    return out
