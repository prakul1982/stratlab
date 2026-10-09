"""AI strategy builder (all plans, monthly limits in plans.py).
Plain English -> validated rules, plus what the user did and didn't specify,
so the app can ask follow-up questions for the missing parts."""
import re

from pydantic import ValidationError

from .models import Cond, Risk, Session

# the AI's notes are shown to the person: one about the reply's own workings ("No timeframe specified, left as null.")
# or about something the person simply didn't say (the app asks about that itself) is left out (R5O-010)
_INTERNAL = re.compile(r"\b(null|json|schema|entryjoin|tgttype|stoptype|minscore|defaulted)\b|\bleft as\b|\bset to (0|zero|false)\b", re.I)
_UNSAID = re.compile(r"\b(no|not|wasn.t|was not|isn.t|without)\b[^.]*\b(specif|give|stat|provid|mention|defin|set)\w*", re.I)
_ASKED = re.compile(r"\b(time ?frame|candle|interval|stop|target|take[- ]profit|exit|sell rule|instrument|symbol|stock|"
                    r"capital|risk|position size|sizing)\b", re.I)


def user_note(note: str) -> bool:
    """Whether one of the AI's notes is for the person: not internal wording, not about what the app asks anyway."""
    if _INTERNAL.search(note):
        return False
    return not (_UNSAID.search(note) and _ASKED.search(note))

BASIC_TYPES = '"price", "num", "sma", "ema", "rsi"'
PRO_TYPES = ('"price", "num", "sma", "ema", "rsi", "macd", "macd_signal", "macd_hist", '
             '"bb_upper", "bb_mid", "bb_lower", "vwap", "supertrend", "stage", "adx", "stoch_k", "atr_pct", '
             '"dc_upper", "dc_lower", "volume", "vol_sma", "atr", "open", "high", "low", "body", "upper_wick", '
             '"lower_wick", "range", "prev_close", "day_open", "day_high", "day_low", "day_chg", "india_vix", '
             '"india_vix_chg"')

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
                "NATURALGAS"), an Indian currency future (e.g. "USDINR", "EURINR") or a global commodity future (e.g. "GC=F" gold, "CL=F" WTI crude), or null if not named or if it's a whole universe,
  "market": "IN" (Indian stocks and indices), "MCX" (Indian commodity futures: only when MCX, rupees or an MCX contract
            name is mentioned), "CDS" (Indian currency futures: USDINR, EURINR, GBPINR, JPYINR), "CMDTY" (global commodity futures: gold, oil, grains in dollars), "CRYPTO", "US", "UK", "EU", "JP" or "FX", or null if unclear,
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
  "notes": short plain-English notes, shown to the user, on anything you could not express (never mention null,
           JSON or field names, and never note what the user left out: the app asks about that itself)
}
Cond = {"l": Ref, "op": "xa" | "xb" | "gt" | "lt" | "eq", "r": Ref, "w": weight (only with entryJoin "score")}
  xa = crosses above (true only on the crossing candle), xb = crosses below,
  gt = is above (true on every candle it stays above), lt = is below, eq = is (only for whole-number values
  like stage: "stage eq num 2").
  Use "gt"/"lt" when the user says "above"/"below", and "xa"/"xb" only when they say cross/break/move above.
Ref = {"t": type, "p": period, "m": second parameter, "v": number,
       "ago": the value this many candles ago, "k": multiply the value by this, "tf": "15m" | "1h" | "1d" to
       compute it on a higher timeframe than the strategy's candles}
Allowed types for this user: %TYPES%
  "price" = close price, "num" = a constant in "v", sma/ema/rsi use "p" as the length,
  macd types: p = fast (12), m = slow (26); bb types: p = length, m = std-devs; vwap: p = length;
  supertrend: p = ATR length, m = multiplier.
  stage: Weinstein market stage 1-4 from a p-candle average (150 on daily candles, about 30 weeks) and its slope
  over m candles (20): 1 basing, 2 advancing (average rising, price above it), 3 topping, 4 declining.
  "Stage 2" / "stage two" = stage eq num 2. "ST S2" = Supertrend + Stage 2: entry stage eq num 2 AND price gt
  supertrend (is above, not crosses: the Supertrend often turns up before Stage 2 starts); exit price xb supertrend. On intraday candles use stage with "tf": "1d".
  adx: trend strength 0-100 (p = length); stoch_k: stochastic %K 0-100 (p = length, m = smoothing);
  atr_pct: average true range as % of price (p = length); atr: average true range in price points (p = length);
  dc_upper / dc_lower: highest high / lowest low of the previous p candles (use "price" "xa" "dc_upper" for a
  breakout); volume and vol_sma (p = length) compare volume with its average.
  The candle: "open", "high", "low", "body" (|close - open|), "upper_wick", "lower_wick", "range" (high - low).
  The trading day: "prev_close" (previous day's close), "day_open", "day_high", "day_low" (so far today),
  "day_chg" (% change from the previous day's close, e.g. -2 means down 2%).
  The market: "india_vix" (India VIX's daily close; intraday candles see the previous day's close) and "india_vix_chg"
  (its % change from the close before). "VIX below 17" = india_vix lt num 17; "VIX up more than 5%" = india_vix_chg gt num 5.
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


from .ai_providers import AIBusy, AIConfig, AIError, ask_provider, complete, extract_json  # noqa: E402,F401  (shared error types)
from . import ai_rank  # noqa: E402

_GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"


def _candidates() -> list[str]:
    """Gemini models for reading scanned PDFs (ocr.py): the measured ones in use, Flash models only."""
    models = [m for m in ai_rank.in_use("gemini") if m.startswith("gemini")]
    return models or ["gemini-3.5-flash", "gemini-3.5-flash-lite"]


def _gemini(system: str, text: str, max_tokens: int = 8192) -> str:
    """Google Gemini alone, its measured models in turn (the AI layer asks it this way too)."""
    return ask_provider("gemini", system, text, max_tokens)


def _anthropic(system: str, text: str, max_tokens: int = 1500) -> str:
    """Claude alone (paid)."""
    return ask_provider("anthropic", system, text, max_tokens)


_gemini._builtin = _anthropic._builtin = True      # the AI layer uses its own clients instead of these wrappers


def write_strategy(text: str, pro: bool) -> dict:
    system = SYSTEM.replace("%TYPES%", PRO_TYPES if pro else BASIC_TYPES)
    data = extract_json(complete(system, text, gemini=_gemini, anthropic=_anthropic, max_tokens=3000))
    raw_notes = data.get("notes") or []
    if isinstance(raw_notes, str):
        raw_notes = [raw_notes]
    elif not isinstance(raw_notes, list):
        raw_notes = []
    out = {"notes": [n for n in (str(x).strip() for x in raw_notes) if n and user_note(n)][:8]}
    allowed = None if pro else {"price", "num", "sma", "ema", "rsi"}

    def conds(items):
        res = []
        for c in items if isinstance(items, list) else []:
            try:
                cond = Cond(**c)
            except (ValidationError, TypeError):
                continue
            if allowed and (cond.l.t not in allowed or cond.r.t not in allowed):
                out["notes"].append("Advanced indicators (MACD, Bollinger, VWAP, Supertrend, ADX, Stochastic, ATR, Donchian, volume) need the Basic plan or above, so that part was left out.")
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
    out["market"] = data.get("market") if data.get("market") in ("IN", "CRYPTO", "US", "UK", "EU", "JP", "FX", "MCX", "CDS", "CMDTY") else None
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


# ---------- the AI's rules checked against the sentence they came from (R11C-004, R11C-005) ----------
# values on the price's own scale: compared with a number, it must be a price above 0
PRICE_LIKE = {"price", "open", "high", "low", "prev_close", "day_open", "day_high", "day_low", "sma", "ema", "vwap",
              "bb_upper", "bb_mid", "bb_lower", "supertrend", "dc_upper", "dc_lower"}
# values on a 0-100 scale, and how a sentence names them
SCALED = {"rsi": r"rsi", "stoch_k": r"stoch(?:astic)?(?:\s*%?k)?", "adx": r"adx"}
_SHORT = re.compile(r"\b(sell(?:ing)? short|short[- ]?sell(?:ing)?|go(?:es|ing)? short|shorts?|shorting|short side|"
                    r"both ways|both directions|long (?:and|or) short)\b(?![- ]?term)", re.I)
_BUY = re.compile(r"\b(buy|buys|buying|go long|enter|long)\b", re.I)
_NO_STOP = re.compile(r"\b(no|without(?: an?| any)?|don'?t use(?: an?)?|not? use(?: an?)?)\s+(stop[- ]?loss(?:es)?|stops?|sl)\b", re.I)
_NO_TGT = re.compile(r"\b(no|without(?: an?| any)?)\s+(target|take[- ]?profit|profit target)s?\b", re.I)
_AFTER = re.compile(r"\b(?:after|hold(?:ing)? for|for at most|at most)\s+(\d+)\s+(bars?|candles?|days?|sessions?)\b", re.I)
_EXIT_WORDS = re.compile(r"\b(sell|sells|exit|close|square[- ]?off|cover|get out)\b", re.I)
_CMP = r"(?:is |was |goes |moves |rises |falls |drops |crosses |closes )?(?:back )?(above|over|greater than|more than|>|below|under|less than|<)\s*(-?\d+(?:\.\d+)?)"


def _same(a: dict, b: dict) -> bool:
    keep = lambda r: {k: v for k, v in r.items() if v is not None}       # noqa: E731
    return keep(a) == keep(b)


def _scaled_from_text(kind: str, period, text: str) -> dict | None:
    """'RSI 14 is above 55' read straight from the sentence: the 0-100 value, the comparison and its number."""
    p = int(period) if period else None
    before = rf"(?:{p}[- ]?(?:day|period|bar|candle)?s?[- ]?)?" if p else ""
    after = rf"(?:\s*\(?\s*{p}\s*\)?)?" if p else ""
    m = re.search(rf"\b{before}{SCALED[kind]}{after}\b[^.;,]*?\s{_CMP}", text, re.I)
    if not m:
        return None
    word, v = m.group(1).lower(), float(m.group(2))
    if not 0 <= v <= 100:
        return None
    op = "gt" if word in ("above", "over", "greater than", "more than", ">") else "lt"
    return {"l": {"t": kind, **({"p": period} if period else {})}, "op": op, "r": {"t": "num", "v": v}}


def check_against_text(out: dict, text: str) -> dict:
    """The AI builder's rules, checked against the person's own sentence before anyone sees them. Each change is said in
    the notes, so nothing is fixed silently:
    - a rule that can never mean anything ("Price crosses below 0", a value against itself) is left out;
    - a 0-100 value set against the price ("Price is above RSI 14" from "RSI 14 is above 55") is read again from the
      sentence, or left out when the sentence doesn't say it;
    - "sell" means selling what was bought: a short side only when the sentence says short ("sell short", "go short");
    - "no stop loss" is a stop of 0, said (and so never asked again), and "after 15 bars" is a time exit."""
    notes = list(out.get("notes") or [])

    def clean(conds: list[dict]) -> list[dict]:
        kept = []
        for c in conds:
            l, r = c.get("l") or {}, c.get("r") or {}
            if _same(l, r):
                notes.append("A rule that compared a value with itself was left out.")
                continue
            bad = None
            for a, b in ((l, r), (r, l)):
                if a.get("t") in PRICE_LIKE and b.get("t") == "num" and (b.get("v") is None or b["v"] <= 0):
                    bad = f"A rule comparing the price with {b.get('v', 0):g} was left out: it can't mean anything."
                if a.get("t") in SCALED and b.get("t") == "num" and b.get("v") is not None and not 0 <= b["v"] <= 100:
                    bad = f"A rule comparing a 0-100 value with {b['v']:g} was left out: it can't mean anything."
            if bad:
                notes.append(bad)
                continue
            mixed = next(((a, b) for a, b in ((l, r), (r, l)) if a.get("t") in SCALED and b.get("t") in PRICE_LIKE), None)
            if mixed:
                osc = mixed[0]
                fixed = _scaled_from_text(osc["t"], osc.get("p"), text)
                if fixed:
                    kept.append({**fixed, **({"w": c["w"]} if c.get("w") is not None else {})})
                    notes.append(f"A rule was read again from your words: {osc['t'].upper().replace('_K', '')} "
                                 f"{'above' if fixed['op'] == 'gt' else 'below'} {fixed['r']['v']:g}.")
                else:
                    notes.append("A rule comparing the price with a 0-100 value was left out: the two aren't on the same scale.")
                continue
            kept.append(c)
        return kept

    for k in ("entry", "exit", "shortEntry", "shortExit"):
        out[k] = clean(list(out.get(k) or []))
    # "Sell when it crosses below" is the way out of a buy, not a short sale (R11C-004)
    if out.get("side") in ("short", "both") and not _SHORT.search(text):
        if out["side"] == "both":
            if not out.get("exit"):
                out["exit"] = [c for c in out.get("shortEntry") or [] if not any(_same(c, e) for e in out.get("entry") or [])]
            out.update(side="long", shortEntry=[], shortExit=[])
            notes.append('"Sell" was read as selling what was bought, not as a short sale. Say "sell short" to trade short.')
        elif _BUY.search(text):
            out.update(side="long")
            notes.append('"Sell" was read as selling what was bought, not as a short sale. Say "sell short" to trade short.')
    risk = dict(out.get("risk") or {})
    mentioned = set(out.get("mentioned") or [])
    if _NO_STOP.search(text):
        risk["sl"] = 0                      # said: no stop, and so not asked again (R11C-005: it came back as a 2% stop)
        mentioned.add("sl")
    if _NO_TGT.search(text):
        risk["tgt"] = 0
        mentioned.add("tgt")
    if "maxBars" not in risk:
        for sentence in re.split(r"[.;\n]", text):
            m = _AFTER.search(sentence)
            if m and _EXIT_WORDS.search(sentence):
                risk["maxBars"] = int(m.group(1))
                mentioned.add("maxBars")
                break
    if out.get("exit"):
        mentioned.add("exit")
    elif "exit" in mentioned and not risk.get("maxBars") and not risk.get("sl") and not risk.get("tgt"):
        mentioned.discard("exit")           # no sell rule survived: the app asks for one
    out["risk"] = risk
    out["mentioned"] = sorted(mentioned)
    out["notes"] = list(dict.fromkeys(notes))[:10]
    return out
