"""Ask StratLab: one line typed into search, turned into one thing to do.

The AI reads the line and picks an action; the app then does it end to end (build the rules, create the
notebook, run the test, start paper trading, open research, answer a question). When the AI can't be
reached, simple word rules pick the action instead, so the box always does something sensible."""
import hashlib
import re

from .ai_reply import AIError
from .ideas import MARKETS, guess_market
from .intel.grounding import _SENT

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


# An answer explains how trading works, so the research reads' advice check (which drops "short sell", "buy them back",
# "breakout") would empty most of them. Here only a real recommendation is dropped: buy/sell/hold advice about a named
# stock, a target price, or a call worded as one ("you should buy", "worth buying", "good time to sell").
_ACTS = r"(buy|sell|hold|accumulate|avoid|short|exit|book profits?)"
RECOMMEND = re.compile(
    r"\b(target price|price target)s?\b|\btarget(s|ed)?\b[^.\d%]{0,14}(₹|rs\.?\s*|inr\s*|\$)?\d[\d,]{2,}"
    rf"|\b(should|ought to)\s+{_ACTS}\b|\brecommend|\bworth (buying|owning|selling)\b|\bmultibagger"
    r"|\b(good|great|right|ideal|best) time to (buy|sell|invest|enter|exit)\b|\bstocks? to (buy|watch|sell)\b"
    rf"|^\W*{_ACTS}\b[^.]*\b(now|today|immediately)\b"
    # a call on anyone, in any wording ("a strong buy", "go long on", "consider buying", "a bargain", "will hit 25000")
    r"|\b(strong|clear|outright) (buy|sell)\b|\b(looks?|is|are|rated|seems?) (like )?an? (buy|sell|hold|bargain)\b|\bgo(ing)? long\b"
    r"|\b(consider|think about|look at|time for)\s+(buying|selling|adding|accumulating|holding)\b|\b(buying|selling) (chances?|opportunit\w+)\b"
    r"|\baccumulate on\b|\b(will|could|may|might|should)\s+(hit|reach|touch|cross|surpass|top)\s+[₹$]?\d"
    r"|\b(top|better|best) picks?\b|\bsafer (choice|bet)\b|\b(better|best) (investment|bet)\b", re.I)
# what a named stock (a ticker in capitals) is advised or forecast to do
_CALL = re.compile(r"\b(buy|sell|hold|accumulate|avoid|short|undervalued|overvalued|upside|downside|cheap|expensive|target)\b"
                   r"|\b(will|could|may|might|is likely to|is set to|is poised to)\s+(rise|fall|rally|climb|drop|gain|"
                   r"outperform|underperform|recover|rebound|double)\b", re.I)
_TICKER = re.compile(r"\b[A-Z][A-Z0-9&]{1,}(?:-[A-Z]{1,3})?\b")
# a company named in ordinary case ("Tata Motors", "Apple", "Reliance"): a capitalised word that doesn't open the sentence
_NAME = re.compile(r"(?<=[a-z0-9,;:)] )[A-Z][a-z]{2,}[A-Za-z&.]*")
_NOT_NAMES = {"Indian", "American", "British", "European", "Japanese", "Chinese", "StratLab", "January", "February", "March", "April",
              "May", "June", "July", "August", "September", "October", "November", "December", "Monday", "Tuesday", "Wednesday",
              "Thursday", "Friday", "Saturday", "Sunday", "India", "Nifty", "Sensex", "Stop", "Loss", "Bollinger", "Bands", "Moving",
              "Average", "Relative", "Strength", "Index", "Fibonacci", "Dow", "Bank", "Fund", "Reserve", "Federal", "The", "This", "That"}
_NAMED_CALL = re.compile(r"\b(buy|buying|sell|selling|accumulate|accumulating|undervalued|overvalued|upside|downside|bargain|cheap|"
                         r"expensive|avoid|target)\b|\b(will|could|may|might|is likely to|is set to|is poised to)\s+"
                         r"(rise|fall|rally|climb|drop|gain|outperform|underperform|recover|rebound|double|triple|hit|reach)\b", re.I)
TERMS = {"RSI", "EMA", "SMA", "WMA", "MACD", "VWAP", "ATR", "ADX", "OBV", "CCI", "MFI", "ROC", "DMI", "NSE", "BSE", "NYSE",
         "NASDAQ", "LSE", "ETF", "ETFS", "IPO", "SIP", "FO", "PE", "EPS", "ROE", "ROCE", "GDP", "CPI", "RBI", "SEBI", "US",
         "UK", "EU", "USD", "INR", "OHLC", "AI", "API", "CSV", "PDF", "SL", "TP", "PNL", "FII", "DII", "OI", "PCR", "IV",
         "ITM", "OTM", "ATM", "CE", "F&O", "LTP", "MTM", "CAGR", "XIRR", "NAV", "AMC", "KYC", "GST", "TDS", "STT", "OK",
         "I", "A", "ID", "JSON", "FAQ", "FX", "IST", "UTC", "EOD", "DMA"}


def recommends(sentence: str) -> bool:
    """A sentence that tells the reader to buy, sell or hold a named stock, or gives a target price."""
    if RECOMMEND.search(sentence):
        return True
    named = [t for t in _TICKER.findall(sentence) if t.replace("-", "") not in TERMS]
    if named and _CALL.search(sentence):
        return True
    return any(n not in _NOT_NAMES for n in _NAME.findall(sentence)) and bool(_NAMED_CALL.search(sentence))


def clean(raw, q: str, strict: bool = False) -> dict:
    """Keep only well-formed fields; anything odd falls back to the word rules. `strict` (the AI's own reply): an answer
    left empty once recommendations are out raises AIError instead, so the call is neither counted nor cached and the
    search box shows its fallback."""
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
        # a sentence that recommends buying, selling or holding a named stock, or gives a target, never reaches the reader
        ans = " ".join(x for x in _SENT.split(" ".join(str(raw.get("answer") or "").split())) if x and not recommends(x))
        if not ans:
            if strict:
                raise AIError("No answer could be written for that. Try rephrasing the question.")
            return guess(q)
        out["answer"] = ans[:1200]
    if out["action"] == "research" and not out["symbol"]:
        out["action"] = "ideas"
    return out


def build(ask_json, q: str) -> dict:
    q = q[:400]                  # what the cache key covers: nothing past it may shape an answer another person gets
    return clean(ask_json(SYSTEM, q, 700), q, strict=True)


def key(q: str) -> tuple:
    """Keyed on the text the AI is sent (the first 400 characters), so a longer query never gets another's answer."""
    return (hashlib.sha1(re.sub(r"\s+", " ", q.strip()[:400].lower()).encode()).hexdigest(),)


def looks_like_code(q: str) -> bool:
    return q.count("\n") >= 2 or bool(CODE.search(q))
