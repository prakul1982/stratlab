"""AI strategy builder (all plans, monthly limits in plans.py).
Plain English -> validated rules, plus what the user did and didn't specify,
so the app can ask follow-up questions for the missing parts."""
import re
import time

import httpx
from pydantic import ValidationError

from .config import settings
from .models import Cond, Risk, Session

BASIC_TYPES = '"price", "num", "sma", "ema", "rsi"'
PRO_TYPES = ('"price", "num", "sma", "ema", "rsi", "macd", "macd_signal", "macd_hist", '
             '"bb_upper", "bb_mid", "bb_lower", "vwap", "supertrend", "adx", "stoch_k", "atr_pct", '
             '"dc_upper", "dc_lower", "volume", "vol_sma", "atr", "open", "high", "low", "body", "upper_wick", '
             '"lower_wick", "range", "prev_close", "day_open", "day_high", "day_low", "day_chg"')

SYSTEM = """You turn a trader's strategy (an idea in words, or code/config they already use) into JSON rules for a
backtesting engine. The engine holds one position at a time. A strategy can go long (buy, then sell), short (sell
first, then buy back), or both ways (long rules and separate short rules; whichever fires first).
Reply with ONLY a JSON object.

Schema:
{
  "name": short strategy name (max 6 words),
  "instrument": the stock, index, coin or currency pair the user named: an NSE trading symbol or index name
                (e.g. "NIFTY 50", "NIFTY BANK", "RELIANCE"), a crypto pair (e.g. "BTC-USD"), a US ticker
                (e.g. "AAPL", "SPY"), a London (e.g. "VOD.L"), European (e.g. "SAP.DE") or Tokyo (e.g. "7203.T")
                listing, a forex pair (e.g. "EURUSD=X"), an MCX commodity future by name (e.g. "GOLDM", "CRUDEOIL",
                "NATURALGAS") or a global commodity future (e.g. "GC=F" gold, "CL=F" WTI crude), or null if not named or if it's a whole universe,
  "market": "IN" (Indian stocks and indices), "MCX" (Indian commodity futures: only when MCX, rupees or an MCX contract
            name is mentioned), "CMDTY" (global commodity futures: gold, oil, grains in dollars), "CRYPTO", "US", "UK", "EU", "JP" or "FX", or null if unclear,
  "universe": when the strategy scans or trades a LIST of instruments at once (a watchlist, "F&O stocks", "NIFTY 50
              stocks", several coins): {"preset": "nifty50" | "banknifty" | "fno_liquid" (liquid F&O stocks) |
              "us_mega" | "top_coins" | null, "symbols": [trading symbols, when the source lists them],
              "maxOpen": most positions open at once (e.g. max_concurrent)}; otherwise omit,
  "tf": "1d" | "1h" | "15m" | "5m" or null if the user gave no timeframe,
  "side": "long" | "short" | "both",
  "entryJoin": "all" | "any" | "score",
  "minScore": with "score": the total weight needed to enter (each Cond may carry "w", default 1),
  "entry": [Cond, ...]        (long entry; for side "short" this is the short entry),
  "exit": [Cond, ...]         (long exit; for side "short" this is when to buy back),
  "shortEntry": [Cond, ...], "shortExit": [Cond, ...]   (only for side "both"),
  "session": {"start": "HH:MM" (no entries before), "end": "HH:MM" (no entries after), "squareoff": "HH:MM"
              (close everything), "maxTradesDay": int, "cooldown": candles to wait after a trade,
              "dailyLossPct": stop for the day after losing this % of capital}   (intraday only; exchange time),
  "product": "intraday" for Indian intraday (MIS) trading, else omit,
  "risk": {"sl": stop, "stopType": "pct" | "points" | "atr" (multiple of ATR 14) | "swing" (swing low/high of the
           last sl candles), "tgt": target, "tgtType": "pct" | "points" | "r" (multiple of the stop distance),
           "trail": trailing stop %, "maxBars": close after this many candles,
           "riskPct": % of capital risked per trade, "capital": amount,
           "sizing": "risk" | "capital", "perTrade": capital per trade, "leverage": 1-20}
          (include ONLY what the user actually stated),
  "mentioned": list of what the user explicitly specified, from:
               "instrument", "tf", "exit", "sl", "tgt", "trail", "maxBars", "riskPct", "capital",
  "notes": short plain-English notes on anything you could not express or had to assume
}
Cond = {"l": Ref, "op": "xa" | "xb" | "gt" | "lt", "r": Ref, "w": weight (only with entryJoin "score")}
  xa = crosses above (true only on the crossing candle), xb = crosses below,
  gt = is above (true on every candle it stays above), lt = is below.
  Use "gt"/"lt" when the user says "above"/"below", and "xa"/"xb" only when they say cross/break/move above.
Ref = {"t": type, "p": period, "m": second parameter, "v": number,
       "ago": the value this many candles ago, "k": multiply the value by this, "tf": "15m" | "1h" | "1d" to
       compute it on a higher timeframe than the strategy's candles}
Allowed types for this user: %TYPES%
  "price" = close price, "num" = a constant in "v", sma/ema/rsi use "p" as the length,
  macd types: p = fast (12), m = slow (26); bb types: p = length, m = std-devs; vwap: p = length;
  supertrend: p = ATR length, m = multiplier.
  adx: trend strength 0-100 (p = length); stoch_k: stochastic %K 0-100 (p = length, m = smoothing);
  atr_pct: average true range as % of price (p = length); atr: average true range in price points (p = length);
  dc_upper / dc_lower: highest high / lowest low of the previous p candles (use "price" "xa" "dc_upper" for a
  breakout); volume and vol_sma (p = length) compare volume with its average.
  The candle: "open", "high", "low", "body" (|close - open|), "upper_wick", "lower_wick", "range" (high - low).
  The trading day: "prev_close" (previous day's close), "day_open", "day_high", "day_low" (so far today),
  "day_chg" (% change from the previous day's close, e.g. -2 means down 2%).
Examples:
  "a green candle" = price gt open.  "the previous candle closed above the 7 EMA" = price ago 1 gt ema p 7 ago 1.
  "lower wick longer than 1.5 x the body" = lower_wick gt body k 1.5.  "1-hour close above the 1-hour 7 EMA" =
  price tf "1h" gt ema p 7 tf "1h".  "up 2% on the day" = day_chg gt num 2.  "long if up 2%, short if down 2%" =
  side "both", entry day_chg gt 2, shortEntry day_chg lt -2.
  A conviction score of weighted checks with a minimum = entryJoin "score" with "w" on each Cond and minScore.
For a universe strategy, write the rules as they apply to each instrument, and set "universe". A minimum price
filter is a rule (price gt num 50) in every entry list. A cooldown in minutes is converted to candles of the chosen
timeframe (30 min on 5m candles = 6). A daily loss cap in money is a % of capital. Pick "5m" for intraday
strategies that act on live ticks.
If the user asks for something that can't be expressed (options legs, position sizing ladders, spread filters,
order types), express the rest and explain what was left out in notes.
If the user asks for an indicator that is not allowed, leave it out and say so in notes.
Never invent exits, stops or targets the user did not ask for; the app will ask them.
If nothing can be expressed, return {"entry": [], "exit": [], "mentioned": [], "notes": ["reason"]}."""


from .ai_providers import AIBusy, AIConfig, AIError, complete, extract_json, status  # noqa: E402  (shared error types)


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


def _gemini(system: str, text: str, max_tokens: int = 8192) -> str:
    if not settings.GEMINI_API_KEY:
        raise AIConfig("GEMINI_API_KEY is missing.")
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": text}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.1, "maxOutputTokens": max(max_tokens, 8192)},
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
            status("gemini").model = model
            return "".join(p.get("text", "") for p in parts if not p.get("thought"))
    if last_err == "empty":
        raise AIError("The AI didn't return a strategy. Try rephrasing it.")
    raise AIBusy("Google's models are busy or out of free quota.")


def _anthropic(system: str, text: str, max_tokens: int = 1500) -> str:
    import anthropic
    if not settings.ANTHROPIC_API_KEY:
        raise AIError("The AI builder isn't configured on the server.")
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    try:
        msg = client.messages.create(model=settings.ANTHROPIC_MODEL, max_tokens=max_tokens, system=system,
                                     messages=[{"role": "user", "content": text}])
    except (anthropic.RateLimitError, anthropic.APIConnectionError):
        raise AIBusy("The AI builder is busy right now.")
    except anthropic.AuthenticationError:
        raise AIConfig("Anthropic rejected ANTHROPIC_API_KEY.")
    except anthropic.APIStatusError as e:
        if e.status_code >= 500:  # overloaded (529) or a server error
            raise AIBusy("The AI builder is busy right now.")
        raise AIError(f"The AI service returned an error ({e.status_code}).")
    status("anthropic").model = settings.ANTHROPIC_MODEL
    return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")


def write_strategy(text: str, pro: bool) -> dict:
    system = SYSTEM.replace("%TYPES%", PRO_TYPES if pro else BASIC_TYPES)
    data = extract_json(complete(system, text, gemini=_gemini, anthropic=_anthropic, max_tokens=3000))
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
                out["notes"].append("Advanced indicators (MACD, Bollinger, VWAP, Supertrend, ADX, Stochastic, ATR, Donchian, volume) need the Pro plan, so that part was left out.")
                continue
            res.append(cond.model_dump(exclude_none=True))
        return res[:10]

    out["entry"] = conds(data.get("entry"))
    out["exit"] = conds(data.get("exit"))
    out["entryJoin"] = data.get("entryJoin") if data.get("entryJoin") in ("all", "any", "score") else "all"
    out["side"] = data.get("side") if data.get("side") in ("short", "both") else "long"
    out["shortEntry"] = conds(data.get("shortEntry")) if out["side"] == "both" else []
    out["shortExit"] = conds(data.get("shortExit")) if out["side"] == "both" else []
    if out["side"] == "both" and not out["shortEntry"]:
        out["side"] = "long"
    if out["side"] == "both" and not out["entry"]:          # short-only after all
        out.update(side="short", entry=out["shortEntry"], exit=out["shortExit"], shortEntry=[], shortExit=[])
    ms = data.get("minScore")
    out["minScore"] = float(ms) if isinstance(ms, (int, float)) and not isinstance(ms, bool) and 0 <= ms <= 120 else 0
    try:
        sess = Session(**{k: v for k, v in (data.get("session") or {}).items()
                          if k in ("start", "end", "squareoff", "maxTradesDay", "cooldown", "dailyLossPct")})
        out["session"] = sess.model_dump()
    except (ValidationError, TypeError, AttributeError):
        out["session"] = Session().model_dump()
        out["notes"].append("Some session times couldn't be read and were left out.")
    out["product"] = "intraday" if data.get("product") == "intraday" else "auto"
    out["tf"] = data.get("tf") if data.get("tf") in ("1d", "1h", "15m", "5m") else None
    out["name"] = str(data.get("name") or "")[:80] or None
    out["instrument"] = str(data["instrument"])[:40] if data.get("instrument") else None
    out["market"] = data.get("market") if data.get("market") in ("IN", "CRYPTO", "US", "UK", "EU", "JP", "FX", "MCX", "CMDTY") else None
    out["universe"] = _universe(data.get("universe"))
    if out["universe"]:
        out["instrument"] = None
    raw_risk = data.get("risk") if isinstance(data.get("risk"), dict) else {}
    risk = {k: v for k, v in raw_risk.items()
            if k in ("sl", "tgt", "trail", "maxBars", "riskPct", "capital", "perTrade", "leverage") and isinstance(v, (int, float)) and not isinstance(v, bool)}
    for k, allowed in (("stopType", ("pct", "points", "atr", "swing")), ("tgtType", ("pct", "points", "r")), ("sizing", ("risk", "capital"))):
        if raw_risk.get(k) in allowed:
            risk[k] = raw_risk[k]
    if "maxBars" in risk:
        risk["maxBars"] = int(risk["maxBars"])
    try:
        Risk(**risk)
        out["risk"] = risk
    except ValidationError:
        out["risk"] = {}
        out["notes"].append("Some risk numbers were out of range and were skipped.")
    valid = {"instrument", "tf", "exit", "sl", "tgt", "trail", "maxBars", "riskPct", "capital"}
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


def ask_json(system: str, text: str, max_tokens: int = 2500):
    """Any JSON answer from the provider chain (used by the options importer)."""
    return extract_json(complete(system, text, gemini=_gemini, anthropic=_anthropic, max_tokens=max_tokens))


PRESET_IDS = ("nifty50", "banknifty", "fno_liquid", "us_mega", "top_coins")


def _universe(u) -> dict | None:
    """A group of instruments the strategy trades together, or None."""
    if not isinstance(u, dict):
        return None
    preset = u.get("preset") if u.get("preset") in PRESET_IDS else None
    symbols = [str(x).strip().upper()[:30] for x in (u.get("symbols") or []) if isinstance(x, str) and x.strip()][:50]
    if not preset and len(symbols) < 2:
        return None
    mo = u.get("maxOpen")
    max_open = int(mo) if isinstance(mo, (int, float)) and not isinstance(mo, bool) and mo >= 1 else None
    return {"preset": preset, "symbols": symbols, "maxOpen": max_open}
