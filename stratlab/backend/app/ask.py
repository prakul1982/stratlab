"""Ask StratLab: one line typed into search, turned into one thing to do.

The AI reads the line and picks an action; the app then does it end to end (build the rules, create the
notebook, run the test, start paper trading, open research, answer a question). When the AI can't be
reached, simple word rules pick the action instead, so the box always does something sensible."""
import re

from .ideas import MARKETS, guess_market

ACTIONS = ("test", "paper", "research", "ideas", "answer", "library", "options", "open")
PAGES = {"paper": "/paper", "options": "/options", "library": "/library", "research": "/research", "import": "/import",
         "notebooks": "/", "new": "/new", "account": "/account", "plans": "/plans", "themes": "/research/themes",
         "pulse": "/research/pulse", "watchlist": "/research/watchlist", "holdings": "/holdings"}

SYSTEM = """You turn one line typed into StratLab (a trading backtester and paper-trading app) into ONE action. Reply with JSON only:
{"action":"test|paper|research|ideas|answer|library|options|open","text":"...","market":"IN|US|UK|EU|JP|CRYPTO|FX|null",
"symbol":"ticker or null","page":"paper|options|library|research|import|notebooks|new|account|plans|themes|pulse|watchlist|holdings|null",
"answer":"...","title":"what you'll do, under 60 characters"}
- test: they describe trading rules or ask to backtest/test one. "text" = the full rule in plain English (what to buy, when, exit, stop).
- paper: they want to paper trade / run live / forward test a rule. "text" = the rule, like test.
- research: they name a company or stock to look into (fundamentals, news, "tell me about", "analyse"). Set symbol and market.
- ideas: they want strategy ideas or suggestions ("momentum ideas for banks", "what works on gold"). "text" = the request.
- answer: a question about trading, indicators or how StratLab works. "answer" = 2-4 plain sentences, honest, no advice to buy or sell.
- library: they want strategies other people published. "text" = search words.
- options: straddles, strangles, iron fly/condor, option selling. "text" = the request.
- open: they name a page of the app. Set "page".
Indian stocks use NSE symbols (RELIANCE, HDFCBANK, NIFTY 50); crypto pairs like BTC-USD. Never promise returns."""

CODE = re.compile(r"(//@version|strategy\(|\bdef |\bimport |=>|\{[\s\S]*\"entry\")")
RULE = re.compile(r"\b(buy|sell|short|long|cross(es|ing)?|above|below|rsi|ema|sma|macd|vwap|supertrend|bollinger|breakout|stop ?loss|target)\b", re.I)
PAPER = re.compile(r"\b(paper ?trade|paper trading|forward ?test|run (it )?live|go live|live test)\b", re.I)
QUESTION = re.compile(r"\?|^(what|how|why|when|is|are|does|do|can|should|explain)\b", re.I)
IDEAS = re.compile(r"\b(ideas?|suggest(ions?)?|strateg(y|ies) for|what works)\b", re.I)
OPTIONS = re.compile(r"\b(straddle|strangle|iron ?(fly|condor)|option selling|options?)\b", re.I)
LIBRARY = re.compile(r"\b(library|published|community|others'? strateg)", re.I)
RESEARCH = re.compile(r"\b(research|fundamentals?|news|about|analy[sz]e|results|valuation)\b", re.I)


def guess(q: str) -> dict:
    """Word rules for when the AI is unavailable."""
    t = q.strip()
    low = t.lower()
    for name, path in PAGES.items():
        if low in (name, f"open {name}", f"go to {name}"):
            return {"action": "open", "page": name, "title": f"Open {name}"}
    if PAPER.search(t) and RULE.search(t):
        return {"action": "paper", "text": PAPER.sub("", t).strip(" ,.:"), "market": guess_market(t), "title": "Build it and start paper trading"}
    if OPTIONS.search(t):
        return {"action": "options", "text": t, "title": "Open options paper trading"}
    if LIBRARY.search(t):
        return {"action": "library", "text": LIBRARY.sub("", t).strip(), "title": "Search the strategy library"}
    if IDEAS.search(t):
        return {"action": "ideas", "text": t, "title": "Get testable ideas"}
    if QUESTION.search(t):                  # "what is RSI?" is a question even though it names an indicator
        return {"action": "answer", "text": t, "title": "Answer the question"}
    if RULE.search(t) and len(t.split()) >= 3:
        return {"action": "test", "text": t, "market": guess_market(t), "title": "Build the rules and run the test"}
    if RESEARCH.search(t):
        return {"action": "research", "symbol": RESEARCH.sub("", t).strip() or None, "market": guess_market(t), "title": "Open research"}
    return {"action": "ideas", "text": t, "title": "Get testable ideas"}


def clean(raw, q: str) -> dict:
    """Keep only well-formed fields; anything odd falls back to the word rules."""
    if not isinstance(raw, dict) or raw.get("action") not in ACTIONS:
        return guess(q)
    out = {"action": raw["action"], "title": str(raw.get("title") or "")[:80] or None}
    text = str(raw.get("text") or "").strip()
    out["text"] = (text or q.strip())[:500]
    market = str(raw.get("market") or "").upper()
    out["market"] = market if market in MARKETS else None
    sym = raw.get("symbol")
    out["symbol"] = str(sym).strip()[:40] if sym and str(sym).lower() not in ("null", "none", "") else None
    page = raw.get("page")
    out["page"] = page if page in PAGES else None
    if out["action"] == "open" and not out["page"]:
        return guess(q)
    if out["action"] == "answer":
        ans = str(raw.get("answer") or "").strip()
        if not ans:
            return guess(q)
        out["answer"] = ans[:1200]
    if out["action"] == "research" and not out["symbol"]:
        out["action"] = "ideas"
    return out


def build(ask_json, q: str) -> dict:
    return clean(ask_json(SYSTEM, q[:400], 700), q)


def key(q: str) -> tuple:
    return (re.sub(r"\s+", " ", q.strip().lower())[:300],)


def looks_like_code(q: str) -> bool:
    return q.count("\n") >= 2 or bool(CODE.search(q))
