"""AI strategy builder (all plans, monthly limits in plans.py).
Plain English -> validated rules, plus what the user did and didn't specify,
so the app can ask follow-up questions for the missing parts."""
import re
import time

import httpx
from pydantic import ValidationError

from .config import settings
from .models import Cond, Risk

BASIC_TYPES = '"price", "num", "sma", "ema", "rsi"'
PRO_TYPES = ('"price", "num", "sma", "ema", "rsi", "macd", "macd_signal", "macd_hist", '
             '"bb_upper", "bb_mid", "bb_lower", "vwap", "supertrend"')

SYSTEM = """You turn a retail trader's strategy idea into JSON rules for a backtesting engine.
The engine is LONG ONLY: it buys, then sells to close. Reply with ONLY a JSON object.

Schema:
{
  "name": short strategy name (max 6 words),
  "instrument": the stock, index or coin the user named: an NSE trading symbol or index name
                (e.g. "NIFTY 50", "NIFTY BANK", "RELIANCE"), or a crypto pair (e.g. "BTC-USD", "ETH-USD"),
                or null if not named,
  "market": "IN" for Indian stocks and indices, "CRYPTO" for coins, or null if unclear,
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


from .ai_providers import AIBusy, AIConfig, AIError, complete, extract_json  # noqa: E402  (shared error types)


_GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
_model_cache = {"name": None, "list": [], "at": 0.0}
_cooldown: dict[str, float] = {}   # model -> time until which we skip it after overload


def _version_key(name: str):
    nums = [float(x) for x in re.findall(r"(\d+(?:\.\d+)?)", name.split("/")[-1])[:1]] or [0.0]
    stable = 0 if re.search(r"preview|exp|latest", name) else 1
    return (stable, nums[0])


def gemini_models() -> list[str]:
    """Flash text models this key can use, best first (stable full Flash, then Lite, then previews)."""
    if _model_cache["list"] and time.time() - _model_cache["at"] < 6 * 3600:
        return _model_cache["list"]
    r = httpx.get(f"{_GEMINI_BASE}/models", params={"pageSize": 1000},
                  headers={"x-goog-api-key": settings.GEMINI_API_KEY}, timeout=20)
    if r.status_code >= 400:
        raise AIError("Couldn't list Gemini models for this key. Check GEMINI_API_KEY in Railway.")
    skip = ("image", "tts", "audio", "live", "embedding", "vision", "thinking", "robotics", "computer", "native")
    names = []
    for m in r.json().get("models", []):
        short = m.get("name", "").split("/")[-1]
        if "generateContent" in (m.get("supportedGenerationMethods") or []) and "flash" in short and not any(k in short for k in skip):
            names.append(short)
    if not names:
        raise AIError("This Gemini key has no Flash text models available.")
    full = sorted([n for n in names if "lite" not in n], key=_version_key, reverse=True)
    lite = sorted([n for n in names if "lite" in n], key=_version_key, reverse=True)
    ordered = full[:3] + lite[:2]
    _model_cache.update(list=ordered, name=ordered[0], at=time.time())
    return ordered


def _candidates() -> list[str]:
    configured = settings.GEMINI_MODEL.strip()
    try:
        auto = gemini_models()
    except AIError:
        if configured and configured.lower() != "auto":
            return [configured]
        raise
    lst = ([configured] if configured and configured.lower() != "auto" else []) + auto
    seen, out = set(), []
    for m in lst:
        if m not in seen:
            seen.add(m); out.append(m)
    now = time.time()
    ready = [m for m in out if _cooldown.get(m, 0) < now]
    return ready or out


def _gemini(system: str, text: str) -> str:
    if not settings.GEMINI_API_KEY:
        raise AIConfig("GEMINI_API_KEY is missing.")
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": text}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.1, "maxOutputTokens": 8192},
    }
    last_err = None
    for model in _candidates()[:4]:
        for attempt in range(2):
            try:
                r = httpx.post(f"{_GEMINI_BASE}/models/{model}:generateContent", json=body,
                               headers={"x-goog-api-key": settings.GEMINI_API_KEY}, timeout=60)
            except httpx.HTTPError:
                last_err = "network"
                time.sleep(1)
                continue
            if r.status_code in (429, 500, 502, 503, 504):
                last_err = r.status_code
                if attempt == 0:
                    time.sleep(1.5)
                    continue
                _cooldown[model] = time.time() + 120   # skip this model for 2 minutes
                break                                  # try the next model
            if r.status_code == 404:
                last_err = 404
                _model_cache.update(list=[], at=0)
                break
            if r.status_code >= 400:
                try:
                    detail = r.json().get("error", {}).get("message", "")
                except ValueError:
                    detail = r.text[:200]
                if r.status_code in (400, 403) and "key" in detail.lower():
                    raise AIConfig("Google rejected GEMINI_API_KEY.")
                raise AIError(f"The AI service returned an error ({r.status_code}) on model {model}: {detail[:160]}")
            try:
                parts = r.json()["candidates"][0]["content"]["parts"]
            except (KeyError, IndexError, ValueError):
                last_err = "empty"
                break
            _model_cache["name"] = model
            return "".join(p.get("text", "") for p in parts if not p.get("thought"))
    if last_err == "empty":
        raise AIError("The AI didn't return a strategy. Try rephrasing it.")
    raise AIBusy("Google's models are busy or out of free quota.")


def _anthropic(system: str, text: str) -> str:
    import anthropic
    if not settings.ANTHROPIC_API_KEY:
        raise AIError("The AI builder isn't configured on the server.")
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    try:
        msg = client.messages.create(model=settings.ANTHROPIC_MODEL, max_tokens=1500, system=system,
                                     messages=[{"role": "user", "content": text}])
    except (anthropic.RateLimitError, anthropic.APIConnectionError):
        raise AIBusy("The AI builder is busy right now.")
    except anthropic.AuthenticationError:
        raise AIConfig("Anthropic rejected ANTHROPIC_API_KEY.")
    except anthropic.APIStatusError as e:
        if e.status_code >= 500:  # overloaded (529) or a server error
            raise AIBusy("The AI builder is busy right now.")
        raise AIError(f"The AI service returned an error ({e.status_code}).")
    return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")


def write_strategy(text: str, pro: bool) -> dict:
    system = SYSTEM.replace("%TYPES%", PRO_TYPES if pro else BASIC_TYPES)
    data = extract_json(complete(system, text, gemini=_gemini, anthropic=_anthropic))
    raw_notes = data.get("notes") or []
    if isinstance(raw_notes, str):
        raw_notes = [raw_notes]
    elif not isinstance(raw_notes, list):
        raw_notes = []
    out = {"notes": [str(n).strip() for n in raw_notes if str(n).strip()][:8]}
    allowed = None if pro else {"price", "num", "sma", "ema", "rsi"}

    def conds(items):
        res = []
        for c in items if isinstance(items, list) else []:
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
    out["market"] = data.get("market") if data.get("market") in ("IN", "CRYPTO") else None
    raw_risk = data.get("risk") if isinstance(data.get("risk"), dict) else {}
    risk = {k: v for k, v in raw_risk.items()
            if k in ("sl", "tgt", "riskPct", "capital") and isinstance(v, (int, float)) and not isinstance(v, bool)}
    try:
        Risk(**risk)
        out["risk"] = risk
    except ValidationError:
        out["risk"] = {}
        out["notes"].append("Some risk numbers were out of range and were skipped.")
    valid = {"instrument", "tf", "exit", "sl", "tgt", "riskPct", "capital"}
    raw_m = data.get("mentioned") or []
    if isinstance(raw_m, str):
        raw_m = [x.strip() for x in raw_m.split(",")]
    mentioned = {m for m in raw_m if m in valid}
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
