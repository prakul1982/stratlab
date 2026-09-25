"""Testable strategy ideas for anything someone types into search: a market, a stock, a style or a question.

Ideas come from the AI chain (cached, so the same question is answered once for everyone) and fall back
to a built-in set when the AI can't be reached. Every idea is a plain-English rule the idea builder can
turn into a notebook: an entry, an exit and a stop, on a named market."""
import re

MARKETS = {"IN", "US", "UK", "EU", "JP", "CRYPTO", "FX"}
TFS = {"1d", "1h", "15m", "5m"}

SYSTEM = """You suggest trading strategy ideas someone can test in a backtester. Reply with JSON only:
{"ideas":[{"title":"short name","text":"the rule in plain English: what to trade, when to buy (or sell short), when to exit, the stop loss",
"why":"one sentence on the reasoning, honest, no promises","market":"IN|US|UK|EU|JP|CRYPTO|FX","symbol":"ticker or null","tf":"1d|1h|15m|5m"}]}
Give 4 varied ideas that fit the request (trend, mean reversion, breakout, momentum as fits). Use only price, moving averages,
RSI, MACD, Bollinger Bands, VWAP, Supertrend, ADX, ATR, volume and the day's open/high/low. Indian stocks use NSE symbols
(RELIANCE, HDFCBANK, NIFTY 50). Crypto uses pairs like BTC-USD. Never claim an idea works; it is there to be tested."""

FALLBACK = [
    {"title": "Trend with a 20/50 EMA cross", "text": "Buy when the 20 EMA crosses above the 50 EMA, sell when it crosses back below, with a 3% stop loss.",
     "why": "A classic way to ride trends and step aside when they fade.", "tf": "1d"},
    {"title": "Buy the RSI dip", "text": "Buy when RSI(14) drops below 30, sell when it rises above 55, with a 4% stop loss.",
     "why": "Tests whether sharp pullbacks tend to bounce.", "tf": "1d"},
    {"title": "20-day breakout", "text": "Buy when the price closes above the highest high of the last 20 days, exit when it closes below the 10-day low, 2 ATR stop.",
     "why": "Donchian-style breakouts catch the start of big moves.", "tf": "1d"},
    {"title": "Opening-range momentum", "text": "On 15-minute candles, buy when the price breaks above the first 15-minute high with VWAP rising, exit at 15:15 or on a 1% stop.",
     "why": "Tests whether early strength carries through the day.", "tf": "15m"},
]

# words that point at a market when someone doesn't name one
HINTS = [("CRYPTO", r"\b(crypto|bitcoin|btc|eth|ethereum|sol|coin|coins)\b"), ("US", r"\b(us|usa|nasdaq|nyse|s&p|spy|qqq|apple|tesla|nvidia)\b"),
         ("FX", r"\b(forex|fx|eurusd|usdjpy|gbpusd|currency|currencies)\b"), ("UK", r"\b(uk|ftse|london)\b"),
         ("EU", r"\b(europe|dax|xetra|euronext)\b"), ("JP", r"\b(japan|nikkei|tokyo)\b")]


def guess_market(q: str) -> str:
    low = q.lower()
    return next((m for m, pat in HINTS if re.search(pat, low)), "IN")


def clean(raw: dict | list | None, q: str) -> list[dict]:
    items = raw.get("ideas") if isinstance(raw, dict) else raw
    out = []
    for it in items or []:
        if not isinstance(it, dict) or not str(it.get("text") or "").strip():
            continue
        market = str(it.get("market") or "").upper()
        tf = str(it.get("tf") or "1d")
        sym = it.get("symbol")
        out.append({"title": str(it.get("title") or "An idea")[:80], "text": str(it["text"]).strip()[:500],
                    "why": str(it.get("why") or "")[:240], "market": market if market in MARKETS else guess_market(q),
                    "symbol": str(sym)[:40] if sym and str(sym).lower() not in ("null", "none") else None,
                    "tf": tf if tf in TFS else "1d"})
    return out[:5]


def fallback(q: str) -> list[dict]:
    m = guess_market(q)
    return [{**i, "market": m, "symbol": None} for i in FALLBACK]


def build(ask_json, q: str) -> dict:
    from .ai_providers import AIError
    ideas = clean(ask_json(SYSTEM, q[:300], 1800), q)
    if not ideas:
        raise AIError("The AI didn't return any usable ideas.")
    return {"ideas": ideas}


def key(q: str) -> tuple:
    return (re.sub(r"\s+", " ", q.strip().lower())[:200],)
