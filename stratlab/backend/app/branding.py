"""What users see about where data comes from: plain labels, never the provider names.

StratLab's data partners are fine with being used but not named publicly, so every message and research
payload that leaves the API goes through here. Admin-only pages and logs keep the real names."""
import re

# research "sources" rows and chart sources: provider name -> what the page shows
LABELS = {
    "Kite": "Live prices", "Yahoo Finance": "Market data", "Screener.in": "Fundamentals", "Finnhub": "Company data",
    "Google News": "News", "Wikipedia": "Wikipedia", "Research": "Research",
}
# outside links to provider sites are dropped; Wikipedia stays (its licence asks for the link)
HIDDEN_LINKS = ("yahoo.", "screener.in", "finnhub.", "zerodha.", "kite.")

_WORDS = [
    (r"Kite Connect", "the live feed"), (r"Zerodha(?:'s)? Kite", "the live feed"), (r"Zerodha", "the broker"),
    (r"\bKite(?:'s)?\b", "the live feed"), (r"Yahoo Finance", "the market data source"), (r"\bYahoo\b", "the market data source"),
    (r"Screener\.in", "the fundamentals source"), (r"\bScreener\b", "the fundamentals source"),
    (r"FINNHUB_API_KEY", "a server key"), (r"finnhub\.io", "the provider"), (r"\bFinnhub\b", "the company data source"),
    (r"Google News", "the news source"), (r"SEC EDGAR", "The SEC"), (r"\bEDGAR\b", "the SEC's filing system"),
]
_RX = [(re.compile(p), r) for p, r in _WORDS]


def public_text(s):
    """A message with provider names replaced by plain words. Non-strings pass through."""
    if not isinstance(s, str):
        return s
    for rx, r in _RX:
        s = rx.sub(r, s)
    return s


def public_research(obj):
    """Research payloads: relabel sources, drop links to provider sites, reword source errors. Recursive."""
    if isinstance(obj, list):
        return [public_research(x) for x in obj]
    if not isinstance(obj, dict):
        return obj
    out = {}
    for k, v in obj.items():
        if k == "sources" and isinstance(v, list):
            out[k] = [{**s, "source": LABELS.get(s.get("source"), "Data"), "error": public_text(s.get("error"))}
                      if isinstance(s, dict) else s for s in v]
        elif k == "links" and isinstance(v, list):
            out[k] = [l for l in v if not (isinstance(l, dict) and any(h in str(l.get("url", "")) for h in HIDDEN_LINKS))]
        elif k == "source" and isinstance(v, str) and v in LABELS and "candles" in obj:
            out[k] = LABELS[v]       # a chart's source; a news item's "source" is the publisher and stays
        else:
            out[k] = public_research(v)
    return out
