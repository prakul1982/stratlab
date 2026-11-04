"""AI strategy builder (all plans, monthly limits in plans.py).
Plain English -> validated rules, plus what the user did and didn't specify,
so the app can ask follow-up questions for the missing parts."""
import json
import re

from pydantic import ValidationError

from .models import Cond, Risk, Session

# the AI's notes are shown to the person: one about the reply's own workings ("No timeframe specified, left as null.")
# or about something the person simply didn't say (the app asks about that itself) is left out (R5O-010)
_INTERNAL = re.compile(r"\b(null|json|schema|entryjoin|tgttype|stoptype|minscore|defaulted)\b|\bleft as\b|\bset to (0|zero|false)\b", re.I)
_UNSAID = re.compile(r"\b(no|not|wasn.t|was not|isn.t|without)\b[^.]*\b(specif|give|stat|provid|mention|defin|set)\w*", re.I)
_ASKED = re.compile(r"\b(time ?frame|candle|interval|stop|target|take[- ]profit|exit|sell rule|instrument|symbol|stock|"
                    r"capital|risk|position size|sizing)\b", re.I)


# the AI talking about the person in the third person ("User asked about weather, not a trading strategy.") is its own
# reasoning, not a line for them to read (DP1-006)
_THIRD_PERSON = re.compile(r"^\W*(?:the\s+)?user(?:'s)?\b", re.I)


def user_note(note: str) -> bool:
    """Whether one of the AI's notes is for the person: not internal wording, not about what the app asks anyway."""
    if _INTERNAL.search(note) or _THIRD_PERSON.search(note):
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
  "name": short strategy name in plain words, max 6 words, never a code or abbreviation
          (e.g. "Reliance 20/50 average crossover", not "Rel20x50"),
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
       compute it on a higher timeframe than the strategy's candles; with "tf", "ago" counts that timeframe's
       closed candles: ago 0 = the last closed one (yesterday's close for "1d"), ago 1 = the one before}
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
  "52-week low" / "52-week high" = dc_lower / dc_upper with p 252 (a trading year of daily candles; on intraday candles
  add "tf": "1d"). "Touches its 52-week low" = low lt dc_lower p 252; "closes below the 52-week low" = price lt dc_lower
  p 252. Never stand in for a level you can't express with a number such as 0: leave the rule out and say so in notes.
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
from . import idea_read  # noqa: E402

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
    locked: list[str] = []

    def conds(items, what: str):
        res = []
        for c in items if isinstance(items, list) else []:
            try:
                cond = Cond(**c)
            except (ValidationError, TypeError):
                out["notes"].append(f"One {what} rule couldn't be read ({json.dumps(c, default=str)[:80]}), so it was left out.")
                continue
            if allowed and (cond.l.t not in allowed or cond.r.t not in allowed):
                out["notes"].append("Advanced indicators (MACD, Bollinger, VWAP, Supertrend, ADX, Stochastic, ATR, Donchian, volume) need the Basic plan or above, so that part was left out.")
                # what was left out, by name: the builder refuses such an idea whole rather than build the rest (DP1-002)
                locked.extend(TYPE_NAME.get(t, t) for t in (cond.l.t, cond.r.t) if t not in allowed)
                continue
            res.append(cond.model_dump(exclude_none=True))
        if len(res) > 10:
            out["notes"].append(f"Only the first 10 of the {len(res)} {what} rules were kept.")
        return res[:10]

    out["entry"] = conds(data.get("entry"), "entry")
    out["exit"] = conds(data.get("exit"), "exit")
    out["entryJoin"] = data.get("entryJoin") if data.get("entryJoin") in ("all", "any", "score") else "all"
    out["side"] = data.get("side") if data.get("side") in ("short", "both") else "long"
    out["shortEntry"] = conds(data.get("shortEntry"), "short entry") if out["side"] == "both" else []
    out["shortExit"] = conds(data.get("shortExit"), "short exit") if out["side"] == "both" else []
    if out["side"] != "both" and (data.get("shortEntry") or data.get("shortExit")):
        out["notes"].append("The short rules were left out: the strategy came back as one direction only "
                            f"({'short' if out['side'] == 'short' else 'long'}), which uses the entry and exit rules.")
    if out["side"] == "both" and not out["shortEntry"]:
        if out["shortExit"]:
            out["notes"].append("The short exit rules were left out: there was no short entry rule, so it trades long only.")
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
    # a name the way the person would write it: "MACD VWAP BTC", not "MACD_VWAP_BTC" (DP1-011)
    out["name"] = re.sub(r"\s+", " ", str(data.get("name") or "").replace("_", " ")).strip()[:80] or None
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
    out["locked"] = list(dict.fromkeys(locked))
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


# ---------- ideas the notebook can't test: option contracts and multi-leg positions (DA-001, DA-009) ----------
# A notebook tests rules on one price series (a stock, an index, a coin, a pair). A single option, a straddle or any
# multi-leg position is priced from its strikes, expiry and volatility, which no rule on the underlying holds: building
# "Buy a call option when RSI crosses above 60" from the underlying's price once dropped the RSI and said nothing.
_OPTIONS = re.compile(
    r"\b(?:straddles?|strangles?|iron\s+(?:condors?|fly|flies|butterfl(?:y|ies))|butterfl(?:y|ies)\s+spreads?|condors?|"
    r"(?:bull|bear)\s+(?:call|put)(?:\s+spreads?)?|(?:credit|debit|calendar|vertical|diagonal|ratio)\s+spreads?|"
    r"covered\s+calls?|protective\s+puts?|cash[- ]secured\s+puts?|"
    r"(?:call|put)\s+options?|options?\s+(?:strateg(?:y|ies)|contracts?|chains?|premiums?|legs?)|"
    r"(?:buy|sell|write|short|long|trade)\w*\s+(?:[\w&]+\s+){0,3}options?(?!\s+expir)|"   # "on options expiry day" is a date, not an option
    r"at[- ]the[- ]money|in[- ]the[- ]money|out[- ]of[- ]the[- ]money|atm|otm|itm)\b"
    r"|\b\d{4,6}\s?(?:ce|pe)\b", re.I)
OPTIONS_IDEA_MESSAGE = ("That idea trades options (a single option, a straddle or another multi-leg position). A notebook tests rules on "
                        "one price series, such as a stock, an index or a coin, so it can't test an option's premium or its legs. "
                        "Build it in the Options builder instead.")


def options_idea(text: str) -> bool:
    """Whether the sentence is an options strategy: refused up front, before any AI build is used."""
    return bool(_OPTIONS.search(text or ""))


# ---------- indicators beyond Free's price, SMA, EMA and RSI (DP1-002, DP1-003) ----------
# An idea built on one of these was built without it on Free: "Short Bitcoin when the price falls below the lowest low of
# the last 20 days" came back as "Price is below 20", and a MACD crossover as "That one is on our side". Such an idea is
# refused whole, by name and before any AI build is used, never built from what is left.
TYPE_NAME = {"macd": "MACD", "macd_signal": "MACD", "macd_hist": "MACD", "bb_upper": "Bollinger Bands", "bb_mid": "Bollinger Bands",
             "bb_lower": "Bollinger Bands", "vwap": "VWAP", "supertrend": "Supertrend", "stage": "the market stage (Stage 2)",
             "adx": "ADX", "stoch_k": "Stochastic", "atr_pct": "ATR", "atr": "ATR",
             "dc_upper": "the highest high or lowest low of past candles", "dc_lower": "the highest high or lowest low of past candles",
             "volume": "volume", "vol_sma": "volume", "open": "the candle's open, high, low and wicks", "high": "the candle's open, high, low and wicks",
             "low": "the candle's open, high, low and wicks", "body": "the candle's open, high, low and wicks",
             "upper_wick": "the candle's open, high, low and wicks", "lower_wick": "the candle's open, high, low and wicks",
             "range": "the candle's open, high, low and wicks", "prev_close": "the day's open, high, low and change",
             "day_open": "the day's open, high, low and change", "day_high": "the day's open, high, low and change",
             "day_low": "the day's open, high, low and change", "day_chg": "the day's open, high, low and change",
             "india_vix": "India VIX", "india_vix_chg": "India VIX"}
_NAMED_LOCKED = (
    ("MACD", r"\bmacd\b"),
    ("Bollinger Bands", r"\bbollinger\b"),
    ("VWAP", r"\bvwap\b"),
    ("Supertrend", r"\bsuper[- ]?trend\b"),
    ("the market stage (Stage 2)", r"\bstage[- ]?(?:[1-4]|one|two|three|four)\b|\bweinstein\b"),
    ("ADX", r"\badx\b"),
    ("Stochastic", r"\bstoch(?:astic)?\b"),
    ("ATR", r"\batr\b|\baverage true range\b"),
    ("the highest high or lowest low of past candles",
     r"\bdonchian\b|\b(?:highest|lowest)\s+(?:high|low|close)\b|\b\d+[- ]?(?:day|week|bar|candle|period|month)s?[- ]?(?:high|low)s?\b"
     r"|\b(?:52|fifty[- ]?two)[- ]?(?:weeks?|wks?|w)\b[- ]*(?:low|high)s?\b|\b(?:one|1)[- ]?year[- ]*(?:low|high)s?\b"),
    ("volume", r"\bvolumes?\b"),
    ("India VIX", r"\bvix\b"),
)


def locked_named(text: str) -> list[str]:
    """The indicators beyond price, SMA, EMA and RSI that the sentence names, in plain words (empty: none)."""
    return [name for name, pat in _NAMED_LOCKED if re.search(pat, text or "", re.I)]


def locked_message(names: list[str]) -> str:
    """Why the idea wasn't built on Free: what it uses and which plan has it ("MACD is on the Basic plan…"). The app adds the
    price beside it."""
    names = list(dict.fromkeys(names))
    said = names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}"
    said = said[0].upper() + said[1:]
    return (f"{said} {'is' if len(names) == 1 else 'are'} on the Basic plan. On Free, notebook rules use price, SMA, EMA and RSI, "
            "so this idea wasn't built: leaving that part out would test a different idea. No AI build was used.")


# ---------- the AI's rules checked against the sentence they came from (R11C-004, R11C-005) ----------
# values on the price's own scale: compared with a number, it must be a price above 0
FLIP = {"gt": "lt", "lt": "gt", "xa": "xb", "xb": "xa", "eq": "eq"}
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
_OR = re.compile(r"\b(?:or|either|any of|any one|one of)\b", re.I)
_STOP_WORDS = re.compile(r"\b(?:stop|stops|stop[- ]?loss(?:es)?|sl|cut (?:the |my )?loss(?:es)?|risk(?:ing)?)\b", re.I)
_TGT_WORDS = re.compile(r"\b(?:target|targets|tgt|take[- ]?profit|tp|profit|book|gain)\b", re.I)
_TRAIL_WORDS = re.compile(r"\btrail", re.I)
_CMP = r"(?:is |was |goes|moves |rises |falls |drops |crosses |closes )?(?:back )?(above|over|greater than|more than|>|below|under|less than|<)\s*(-?\d+(?:\.\d+)?)"


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


_OSC_NAME = {"rsi": "RSI", "stoch_k": "Stochastic", "adx": "ADX"}
# a note that says nothing could be made, kept only while no rule came out (DA-001: "no rules could be generated" over the
# rules it was shown beside)
_NO_RULES_NOTE = re.compile(r"\b(?:no|not any|none of the)\b[^.]*\brules?\b[^.]*\b(?:generat|creat|built|express|made|produc)|"
                            r"\bcan(?:'t|not) (?:be )?(?:expressed|generated|built)\b|\bnothing (?:can|could) be\b|"
                            r"\b(?:could not|couldn't|unable to) (?:generate|create|build|express)\b", re.I)


def _lost_subject(c: dict, text: str, periods: dict) -> tuple[dict, str] | None:
    """A rule of the price against a plain number between 0 and 100, when the sentence names one 0-100 indicator and that
    number, and never sets the price against it: the indicator is the rule's subject, lost on the way ("sell when it falls
    below 50" after "RSI crosses above 60" came back as "Price is below 50", DA-001). Read again with the indicator."""
    l, r = c.get("l") or {}, c.get("r") or {}
    for price, num, price_left in ((l, r, True), (r, l, False)):
        if price.get("t") != "price" or num.get("t") != "num" or price.get("k") not in (None, 1) or price.get("ago") or price.get("tf"):
            continue
        v = num.get("v")
        if v is None or not 0 < v <= 100:
            continue
        named = [k for k, pat in SCALED.items() if re.search(rf"\b{pat}\b", text, re.I)]
        if len(named) != 1:
            return None
        lit = rf"(?<![\d.]){v:g}(?![\d.])"
        if not re.search(lit, text) or re.search(rf"\b(?:price|close|closes|closing|ltp|stocks?|shares?|index|coin)\b[^.;,]{{0,30}}?{lit}", text, re.I):
            return None
        kind = named[0]
        p = periods.get(kind)
        if p is None:
            m = re.search(rf"\b{SCALED[kind]}\s*\(?\s*(\d{{1,3}})\b", text, re.I)
            p = int(m.group(1)) if m else None
        osc = {"t": kind, **({"p": p} if p else {})}
        op = c.get("op") if price_left else FLIP.get(c.get("op"), "gt")
        fixed = {"l": osc, "op": op, "r": {"t": "num", "v": v}, **({"w": c["w"]} if c.get("w") is not None else {})}
        say = {"gt": "is above", "lt": "is below", "xa": "crosses above", "xb": "crosses below", "eq": "is"}[op]
        name = _OSC_NAME[kind] + (f" {p}" if p else "")
        return fixed, f"\"Price {say} {v:g}\" was read as \"{name} {say} {v:g}\": the indicator your words name."
    return None


_W52 = re.compile(r"\b(?:52|fifty[- ]?two)[- ]?(?:weeks?|wks?|w)\b[- ]*(low|high)s?\b|\b(?:one|1)[- ]?year[- ]*(low|high)s?\b"
                  r"|\b(?:12|twelve)[- ]?months?[- ]*(low|high)s?\b|\b(?:yearly|annual)\s+(low|high)s?\b", re.I)
_TOUCH = re.compile(r"\b(?:touch(?:es|ed|ing)?|hit(?:s|ting)?|reach(?:es|ed|ing)?|mak(?:e|es|ing) a new)\b", re.I)


def _year_rule(c: dict, price: dict, price_on_left: bool, text: str, tf: str | None) -> dict | None:
    """A rule that set a price against 0 or less, read as the 52-week low or high the sentence names: the lowest low /
    highest high of the previous 252 daily candles (a daily one on intraday candles). "Touches" reads the candle's low or
    high; any other wording keeps the price the rule had. With both named, a rule that looks down takes the low."""
    found = {next(g for g in m.groups() if g).lower() for m in _W52.finditer(text)}
    if not found:
        return None
    op = c.get("op") if price_on_left else FLIP.get(c.get("op"), "gt")
    low = "low" in found and ("high" not in found or op in ("lt", "xb"))
    level = {"t": "dc_lower" if low else "dc_upper", "p": 252, **({"tf": "1d"} if tf in ("1h", "15m", "5m") else {})}
    if _TOUCH.search(text) and price.get("t") == "price":
        price, op = {"t": "low" if low else "high"}, "lt" if low else "gt"
    return {"l": price, "op": op, "r": level, **({"w": c["w"]} if c.get("w") is not None else {})}


# ---------- the AI's rules held to the words, for the phrasings read without it (57.1) ----------
_NAME = {"price": "Price", "ema": "EMA", "sma": "SMA", "rsi": "RSI", "dc_upper": "the highest high of the last", "dc_lower": "the lowest low of the last"}
_SAY = {"gt": "is above", "lt": "is below", "xa": "crosses above", "xb": "crosses below", "eq": "is"}


def _ref_words(r: dict) -> str:
    t = r.get("t")
    if t == "num":
        return f"{r.get('v'):g}"
    if t in ("dc_upper", "dc_lower"):
        return f"{_NAME[t]} {r.get('p', 20):g} candles"
    on = f" on {idea_read.TF_WORDS.get(r['tf'], r['tf'])} candles" if r.get("tf") else ""        # LIVE3-004: what runs, said
    return (f"{_NAME.get(t, t)} {r['p']:g}" if r.get("p") else _NAME.get(t, str(t))) + on


def rule_words(c: dict) -> str:
    """'EMA 20 crosses above EMA 50': a rule in the words the notes use."""
    return f"{_ref_words(c['l'])} {_SAY.get(c['op'], c['op'])} {_ref_words(c['r'])}"


_DIRECTION = {"gt": "up", "xa": "up", "lt": "down", "xb": "down", "eq": "eq"}


def _same_rules(ai: list | None, words: list | None) -> bool:
    """The AI's rules are the words' ones, in any order, 20 and 20.0 being one length. A rule the words give with a move verb
    ("falls below 50", marked soft) matches a state on the same two lines the same way ("is below 50"): that is a reading of the
    words, not a misreading."""
    ref = lambda r: json.dumps({k: float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else v      # noqa: E731
                                for k, v in (r or {}).items() if v is not None}, sort_keys=True)
    ai, words = list(ai or []), list(words or [])
    if len(ai) != len(words):
        return False
    left = [(ref(c.get("l")), c.get("op"), ref(c.get("r"))) for c in ai]
    for c in words:
        l, r = ref(c["l"]), ref(c["r"])
        hit = next((k for k in left if k[0] == l and k[2] == r and (k[1] == c["op"] or c.get("soft") and _DIRECTION.get(k[1]) == _DIRECTION[c["op"]])), None)
        if hit is None:
            return False
        left.remove(hit)
    return True


def _plain(rules: list[dict]) -> list[dict]:
    return [{k: v for k, v in c.items() if k != "soft"} for c in rules]


def _from_the_words(out: dict, text: str, notes: list[str]) -> None:
    """The buy and sell rules, held to what the words plainly say (57.1: "sell when it crosses back below" came back as "EMA 50
    crosses below Price", the lines the other way round, and with no instrument named the buy rule became two). For a long idea
    whose buy (or sell) clauses idea_read understands word for word, those rules are the ones used, said in the notes when the
    AI's differed; a sell clause that only points back ("it crosses back below") takes the buy rule's own two lines, in the
    same order, and is left for the person to pick when it could mean more than one. Also sets "confirmed" (the sides read from
    the words) and "assumed" (what the reading supplied that the words don't say), and leaves out an instrument the AI picked
    when the words name none (nobody guesses it: the notebook asks)."""
    out["confirmed"], out["assumed"] = [], []
    got = idea_read.read(text)
    if got is None or out.get("side", "long") != "long":
        return
    got = json.loads(json.dumps(got))
    mentioned = set(out.get("mentioned") or [])
    # LIVE3-004: the candles the words name are the ones used, and a length said in days or weeks is made what runs on them
    if got.get("tf"):
        if out.get("tf") and out["tf"] != got["tf"]:
            notes.append(f"Your words say {idea_read.TF_WORDS[got['tf']]} candles, so those are used.")
        out["tf"] = got["tf"]
        mentioned.add("tf")
    said = idea_read.on_timeframe(got, out.get("tf"))
    if said is None:
        notes.append(f"An average in your words is longer than {idea_read.MAX_LENGTH} trading days, the longest StratLab works out, so "
                     "it couldn't be set up as written. Pick a shorter one below.")
        out["entry"], out["exit"] = [], []
        out["mentioned"] = sorted(mentioned - {"exit"})
        return
    got["assumed"] = got["assumed"] + said
    if got["entry"] is not None:
        if not _same_rules(out.get("entry"), got["entry"]):
            had = bool(out.get("entry"))
            out.update(entry=_plain(got["entry"]), entryJoin="all", minScore=0)
            notes.append(f"The buy rule was read from your words: {' and '.join(map(rule_words, got['entry']))}."
                         + (" The AI had read it differently." if had else ""))
        elif out.get("entryJoin") != "all" and len(got["entry"]) > 1:
            out["entryJoin"] = "all"
        out["confirmed"].append("entry")
    if got["said_exit"] and got["exit"] is not None:
        # the pronouns in the words, resolved against the buy rules that are used (the words' own, or the AI's)
        got["exit"] = [{k: (idea_read.IT if v == idea_read.IT else v) for k, v in c.items()} for c in got["exit"]]
        rules = idea_read.resolve_exit(got["exit"], out.get("entry") or [])
        if rules is None:
            out["exit"] = []
            mentioned.discard("exit")
            notes.append("Your sell rule points back to the buy rule (\"it\"), and the buy rule has more than one part, so which one "
                         "it means isn't clear. Pick the sell rule below.")
        else:
            if not _same_rules(out.get("exit"), rules):
                had = bool(out.get("exit"))
                out["exit"] = rules = _plain(rules)
                if rules:
                    notes.append(f"The sell rule was read from your words: {' or '.join(map(rule_words, rules))}."
                                 + (" The AI had read it differently." if had else ""))
                elif had:
                    notes.append("Your words sell only at the stop loss or target, so the sell rule the AI added was left out.")
            mentioned.add("exit")           # a sell rule, or a stop or target as the way out ("exit if it falls 8%")
            out["confirmed"].append("exit")
    elif not got["said_exit"] and got["entry"] is not None and out.get("exit"):
        # the words give no sell rule: one the AI wrote is its own, and the notebook asks instead (the AI is told never to)
        out["exit"] = []
        mentioned.discard("exit")
        notes.append("Your words give no sell rule, so the one the AI added was left out. Pick one below.")
    risk = dict(out.get("risk") or {})
    for k, v in got["risk"].items():
        if risk.get(k) != v and (k != "sl" or risk.get("stopType", "pct") == "pct") and (k != "tgt" or risk.get("tgtType", "pct") == "pct"):
            if risk.get(k):
                notes.append(f"Your words give a {'stop loss' if k == 'sl' else 'target'} of {v:g}%, so that is the one used.")
            risk[k] = v
        mentioned.add(k)
    out["risk"] = risk
    if got["entry"] is not None and got["exit"] is not None:
        if not got["named"] and out.get("instrument") and not out.get("universe"):
            # every word was read and none names a stock, index or coin: the AI's pick is a guess, and the notebook asks
            out["instrument"] = None
            out["market"] = None
            mentioned.discard("instrument")
            notes.append("Your words name no stock, index or coin, so none was picked for you. Choose one below.")
    out["assumed"] = got["assumed"]
    out["mentioned"] = sorted(mentioned)


# ---------- the notebook's name (LIVE3-004, LIVE3-005) ----------
# The AI's name is kept only while every word of it is true of what runs: "BankNifty 200 EMA Long" over SMA rules, and "Relevance RSI
# Reversal" for RELIANCE (a word that is neither the instrument nor a rule), were not. Otherwise the name is made from the instrument
# and the rules: "RELIANCE RSI 30/70", "BANKNIFTY SMA 200 daily".
_KIND_WORDS = {"ema": {"ema", "exponential"}, "sma": {"sma", "dma", "simple"}, "rsi": {"rsi"}, "macd": {"macd"}, "macd_signal": {"macd"},
               "macd_hist": {"macd"}, "vwap": {"vwap"}, "supertrend": {"supertrend", "super"}, "adx": {"adx"}, "atr": {"atr"}, "atr_pct": {"atr"},
               "bb_upper": {"bollinger", "bb", "band", "bands"}, "bb_mid": {"bollinger", "bb", "band", "bands"}, "bb_lower": {"bollinger", "bb", "band", "bands"},
               "stoch_k": {"stochastic", "stoch"}, "dc_upper": {"donchian", "52", "week", "high", "highs", "breakout"},
               "dc_lower": {"donchian", "52", "week", "low", "lows"}, "volume": {"volume", "vol"}, "vol_sma": {"volume", "vol"}, "stage": {"stage"}}
_MA_WORDS = {"ma", "moving", "average", "averages", "dma", "crossover", "cross", "crossunder"}
_ALL_KIND_WORDS = set().union(*_KIND_WORDS.values()) | _MA_WORDS
_GENERIC_WORDS = {"long", "short", "strategy", "system", "idea", "trend", "trending", "following", "follower", "momentum", "reversal", "reversion",
                  "mean", "breakdown", "pullback", "bounce", "dip", "dips", "swing", "intraday", "daily", "weekly", "hourly", "minute", "min",
                  "golden", "death", "oversold", "overbought", "buy", "sell", "entry", "exit", "signal", "signals", "rider", "ride", "play", "setup",
                  "scalp", "scalper", "scalping", "the", "and", "of", "on", "with", "a", "an", "plus", "filter", "filtered", "stop", "target",
                  "trailing", "basic", "classic", "my", "new", "only", "candle", "candles", "bar", "bars", "close", "closes", "price", "above",
                  "below", "level", "levels", "zone", "back", "recovery", "rebound", "x", "vs", "to", "m", "h", "d", "day", "days", "period"}


def _refs(out: dict) -> list[dict]:
    return [r for c in (out.get("entry") or []) + (out.get("exit") or []) + (out.get("shortEntry") or []) + (out.get("shortExit") or [])
            for r in (c.get("l"), c.get("r")) if isinstance(r, dict)]


def _symbol_words(out: dict) -> str:
    inst = str(out.get("instrument") or "")
    return re.sub(r"^[A-Z]+:", "", inst).strip()


def name_fits(name: str | None, out: dict) -> bool:
    """Whether every word of a name is true of the strategy: the instrument (or part of its symbol), an indicator its rules use,
    a number they use, or a plain word for a kind of strategy."""
    if not name:
        return False
    refs = _refs(out)
    kinds = {r.get("t") for r in refs}
    numbers = {float(x) for r in refs for x in (r.get("p"), r.get("v")) if isinstance(x, (int, float))} | \
              {float(v) for v in (out.get("risk") or {}).values() if isinstance(v, (int, float))}
    ok_words = set().union(*(_KIND_WORDS.get(k, set()) for k in kinds)) | (_MA_WORDS if kinds & {"ema", "sma"} else set())
    sym = re.sub(r"[^a-z0-9]", "", _symbol_words(out).lower())
    for tok in re.findall(r"[a-z]+|\d+(?:\.\d+)?", name.lower()):
        if re.fullmatch(r"\d+(?:\.\d+)?", tok):
            if float(tok) not in numbers and not (sym and tok in sym):
                return False
        elif tok in ok_words or tok in _GENERIC_WORDS - _ALL_KIND_WORDS or (sym and len(tok) >= 3 and tok in sym):
            continue
        else:
            return False                    # an indicator the rules don't use, or a word that is neither the instrument nor a rule
    return True


def rule_name(out: dict) -> str | None:
    """A name made from the instrument and the rules: "RELIANCE RSI 30/70", "NIFTY 50 EMA 20/50", "BANKNIFTY SMA 200 daily"."""
    entry, exits = out.get("entry") or out.get("shortEntry") or [], out.get("exit") or out.get("shortExit") or []
    parts, seen = [], set()
    for kind in dict.fromkeys(r.get("t") for r in _refs(out)):
        if kind in ("price", "num", None) or kind in seen:
            continue
        seen.add(kind)
        refs = [r for r in _refs(out) if r.get("t") == kind]
        if kind in ("dc_upper", "dc_lower"):
            p = refs[0].get("p") or 20
            parts.append(("52-week " if p == 252 else f"{p:g}-candle ") + ("high" if kind == "dc_upper" else "low"))
            continue
        word = TYPE_NAME.get(kind) if kind in TYPE_NAME and " " not in TYPE_NAME[kind] else kind.upper().split("_")[0]
        lens = list(dict.fromkeys(f"{r['p']:g}" for r in refs if r.get("p")))
        levels = list(dict.fromkeys(f"{c[side]['v']:g}" for c in entry + exits for side in ("l", "r")
                                    if isinstance(c.get(side), dict) and c[side].get("t") == "num"
                                    and any(isinstance(c.get(o), dict) and c[o].get("t") == kind for o in ("l", "r"))))
        on = " daily" if any(r.get("tf") == "1d" for r in refs) and out.get("tf") not in (None, "1d") else ""
        parts.append(f"{word} {'/'.join(levels) if kind in _OSC_NAME and levels else '/'.join(lens)}".strip() + on)
    if not parts:
        return None
    return " ".join(x for x in [_symbol_words(out)] + parts if x)[:80]


def check_against_text(out: dict, text: str) -> dict:
    """The AI builder's rules, checked against the person's own sentence before anyone sees them. Each change is said in
    the notes, so nothing is fixed silently:
    - a rule that can never mean anything ("Price crosses below 0", a value against itself) is left out, unless the sentence
      names a 52-week low or high, which the rule was reaching for: it is then read as that level (R18-002);
    - a 0-100 value set against the price ("Price is above RSI 14" from "RSI 14 is above 55") is read again from the
      sentence, or left out when the sentence doesn't say it;
    - "sell" means selling what was bought: a short side only when the sentence says short ("sell short", "go short");
    - "no stop loss" is a stop of 0, said (and so never asked again), and "after 15 bars" is a time exit."""
    notes = list(out.get("notes") or [])
    risk0 = dict(out.get("risk") or {})            # a target or stop read from a rule against the entry price
    # the length each 0-100 indicator already has in the rules, for a rule that lost its indicator (DA-001)
    periods = {}
    for k in ("entry", "exit", "shortEntry", "shortExit"):
        for c in out.get(k) or []:
            for ref in (c.get("l") or {}, c.get("r") or {}):
                if ref.get("t") in SCALED and ref.get("p"):
                    periods.setdefault(ref["t"], ref["p"])

    def clean(conds: list[dict]) -> list[dict]:
        kept = []
        for c in conds:
            l, r = c.get("l") or {}, c.get("r") or {}
            if _same(l, r):
                notes.append("A rule that compared a value with itself was left out.")
                continue
            own = {k: v for k, v in r.items() if k != "k"}
            if r.get("k") not in (None, 1) and r.get("t") == l.get("t") and _same(own, {k: v for k, v in l.items() if k != "k"}) and l.get("k") in (None, 1):
                # "Price is above 1.05 × Price": the sentence means the trade's entry price, which a rule can't name; a stop or target can
                k = float(r["k"])
                up = c.get("op") in ("gt", "xa")
                if up and k > 1 and not risk0.get("tgt"):
                    risk0["tgt"] = round((k - 1) * 100, 2)
                    notes.append(f"\"Price above {k:g} × Price\" was read as a profit target of {risk0['tgt']:g}% over the entry price.")
                elif not up and 0 < k < 1 and not risk0.get("sl"):
                    risk0["sl"] = round((1 - k) * 100, 2)
                    notes.append(f"\"Price below {k:g} × Price\" was read as a stop loss of {risk0['sl']:g}% under the entry price.")
                else:
                    notes.append("A rule that compared the price with a multiple of itself was left out: it doesn't say what it is measured from. Use a stop loss or target instead.")
                continue
            bad = None
            for a, b in ((l, r), (r, l)):
                if a.get("t") in PRICE_LIKE and b.get("t") == "num" and (b.get("v") is None or b["v"] <= 0):
                    bad = f"A rule comparing the price with {b.get('v') or 0:g} was left out: it can't mean anything."
                    read = _year_rule(c, a, a is l, text, out.get("tf")) if a.get("t") in ("price", "open", "high", "low", "day_high", "day_low") else None
                    if read:
                        kept.append(read)
                        notes.append(f"A rule comparing the price with {b.get('v') or 0:g} was read as the "
                                     f"{'lowest low' if read['r']['t'] == 'dc_lower' else 'highest high'} of the last 252 candles "
                                     "(52 weeks), from your words.")
                        bad = "done"
                        break
                if a.get("t") in SCALED and b.get("t") == "num" and b.get("v") is not None and not 0 <= b["v"] <= 100:
                    bad = f"A rule comparing a 0-100 value with {b['v']:g} was left out: it can't mean anything."
            if bad == "done":
                continue
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
            lost = _lost_subject(c, text, periods)
            if lost:
                kept.append(lost[0])
                notes.append(lost[1])
                continue
            kept.append(c)
        return kept

    for k in ("entry", "exit", "shortEntry", "shortExit"):
        before = len(out.get(k) or [])
        out[k] = clean(list(out.get(k) or []))
        if k in ("entry", "shortEntry") and out[k] and len(out[k]) < before and out.get("entryJoin") in ("any", "score"):
            # the rest of an "any of these" list decides alone once a rule is gone (R18-002: volume alone opened 3,014 trades)
            notes.append("A rule was left out of the entry rules, so the ones left now decide the entry on their own. Check them before you run it.")
    # "MACD crosses above its signal and price is above VWAP" came back as "any of these" (DP1-005): rules the sentence
    # joins with "and" and never with "or" all have to hold at once
    if out.get("entryJoin") == "any" and (len(out.get("entry") or []) > 1 or len(out.get("shortEntry") or []) > 1) and not _OR.search(text):
        out["entryJoin"] = "all"
        notes.append('The entry rules all have to hold at once, as your words join them with "and". Say "or" to enter on any one of them.')
    if out.get("entry") or out.get("shortEntry"):
        notes = [n for n in notes if not _NO_RULES_NOTE.search(n)]       # rules came out: a note saying none could must not stand (DA-001)
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
    _from_the_words(out, text, notes)     # the phrasings people write most, read without the AI (57.1)
    risk = {**dict(out.get("risk") or {}), **{k: v for k, v in risk0.items() if k in ("tgt", "sl")}}
    mentioned = set(out.get("mentioned") or [])
    # a stop or target the sentence never asks for is the AI's own (DP1-005: a 2% stop nobody asked for, counted as said):
    # left out, so the notebook's default stop is shown as a default and the question about it is asked
    first = out.get("risk") or {}
    read_here = {k for k in ("tgt", "sl") if risk0.get(k) and risk0.get(k) != first.get(k)}     # read above from a rule
    for k, said in (("sl", _STOP_WORDS), ("tgt", _TGT_WORDS), ("trail", _TRAIL_WORDS)):
        v = risk.get(k)
        if v and isinstance(v, (int, float)) and k not in read_here and not said.search(text) and not re.search(rf"(?<![\d.]){v:g}\s*%", text):
            risk.pop(k)
            mentioned.discard(k)
    mentioned |= read_here              # a target or stop read from a rule counts as said
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
    if (out.get("entry") or out.get("shortEntry")) and not name_fits(out.get("name"), out):
        out["name"] = rule_name(out) or out.get("name")
    return out
