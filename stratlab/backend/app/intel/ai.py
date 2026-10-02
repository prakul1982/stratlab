"""AI reads for the research pages: a company scorecard (with strategy ideas StratLab
can test), sector maps, the market pulse and head-to-head comparisons.

All of them go through the same free provider chain as the idea builder. Answers are
cached and shared between users, so a popular stock or theme costs one AI call."""
import hashlib
import json
import time

from ..ai_providers import complete, extract_json
from .net import TTLCache
from ..kite_service import ist_date

_cache = TTLCache(max_items=2000)
BASICS = "price, simple moving average (SMA), exponential moving average (EMA) and RSI"
PRO = BASICS + ", MACD, Bollinger Bands, VWAP and Supertrend"

RULES = """Rules:
- Treat the FACTS as current and authoritative. Never contradict them, never claim the company is delisted or
  acquired, and don't invent precise figures that aren't in the facts. Mark anything you estimate as an estimate.
- Plain English a retail investor understands. No markdown, no emojis.
- Reply with ONLY one JSON object in exactly the shape asked for."""


def _key(*parts) -> str:
    return hashlib.sha1(json.dumps(parts, sort_keys=True, default=str).encode(), usedforsecurity=False).hexdigest()   # a cache key


def cached(kind: str, key_parts: tuple, ttl: float, refresh: bool, build) -> tuple[dict, bool]:
    """(result, fresh) where result carries generated_at; `build` runs only on a miss or refresh."""
    k = _key(kind, *key_parts)
    if not refresh:
        hit = _cache.get(k)
        if hit is not None:
            return hit, False
    out = build()
    out["generated_at"] = time.time()
    _cache.set(k, out, ttl)
    return out, True


def peek(kind: str, key_parts: tuple) -> bool:
    return _cache.get(_key(kind, *key_parts)) is not None


def _ask(system: str, facts: dict | str, ai, max_tokens: int) -> dict:
    text = facts if isinstance(facts, str) else "FACTS:\n" + json.dumps(facts, ensure_ascii=False, default=str)
    return extract_json(complete(system, text, gemini=ai[0], anthropic=ai[1], max_tokens=max_tokens, kind="research"))


def _clip(x, n: int, length: int = 400) -> list:
    return [str(i)[:length] for i in (x or []) if str(i).strip()][:n] if isinstance(x, list) else []


def _score(v) -> int | None:
    try:
        return max(0, min(100, int(round(float(v)))))
    except (TypeError, ValueError):
        return None


def company_facts(c: dict) -> dict:
    """The compact, factual view of a profile the model is allowed to reason from."""
    q = c.get("quote") or {}
    metrics = {i["label"]: i["value"] for g in c.get("metrics") or [] for i in g["items"]}
    facts = {"name": c["name"], "symbol": c["symbol"], "market": "India (NSE)" if c["region"] == "IN" else "United States",
             "currency": c.get("currency"), "industry": c.get("industry"), "price": q.get("price"),
             "day_change_pct": q.get("change_pct"), "range_52w": c.get("range52"), "market_cap": c.get("market_cap"),
             "metrics": metrics, "margins": c.get("margins"),
             "annual_trend": c.get("trend"), "earnings_surprises": c.get("earnings"),
             "analyst_ratings": c.get("analysts"), "shareholding": c.get("shareholding"),
             "screener_pros": c.get("pros"), "screener_cons": c.get("cons"),
             "about": ((c.get("about") or {}).get("wiki") or {}).get("extract") or (c.get("about") or {}).get("profile"),
             "recent_headlines": [n["headline"] for n in (c.get("news") or [])[:6]], "today": ist_date().isoformat()}
    return {k: v for k, v in facts.items() if v not in (None, [], {}, "")}


def company(c: dict, ai, pro: bool) -> dict:
    system = f"""You are a careful equity analyst writing for StratLab, a tool that tests trading ideas honestly.
Given FACTS about one listed company, return ONLY this JSON:
{{"summary": "2-3 sentences: what the business is and the single most important thing about it right now",
 "scores": {{"moat": 0, "growth": 0, "value": 0, "momentum": 0, "health": 0}},
 "composite": 0,
 "valuation": "CHEAP" | "FAIR" | "RICH",
 "valuation_note": "one sentence: why, versus its own history and peers",
 "bull": ["3-4 specific points"], "bear": ["3-4 specific risks"],
 "segments": [{{"label": "business segment", "share": 0}}],
 "position": "2 sentences on where it sits in its value chain and who it depends on",
 "watch": ["2-3 upcoming things that could move the stock"],
 "ideas": [{{"title": "3-6 words", "text": "one trading rule in plain English", "why": "one sentence"}}]}}
Scores are 0-100. Segment shares are estimates that add up to about 100.
"ideas" are exactly 3 trading ideas a trader could backtest on THIS stock, suited to how it behaves
(trend, mean reversion, breakout...). Each "text" must use only {PRO if pro else BASICS}, a timeframe
(daily candles unless intraday clearly suits it) and a stop loss, e.g.
"Buy {c['symbol']} when the 20-day EMA crosses above the 50-day EMA, sell when it crosses back below, 5% stop loss".
{RULES}"""
    r = _ask(system, company_facts(c), ai, 2500)
    scores = r.get("scores") if isinstance(r.get("scores"), dict) else {}
    ideas = []
    for i in r.get("ideas") or []:
        if isinstance(i, dict) and str(i.get("text", "")).strip():
            ideas.append({"title": str(i.get("title") or "Idea")[:60], "text": str(i["text"])[:400],
                          "why": str(i.get("why") or "")[:300]})
    segs = []
    for s in r.get("segments") or []:
        if isinstance(s, dict) and s.get("label") and _score(s.get("share")) is not None:
            segs.append({"label": str(s["label"])[:50], "share": _score(s["share"])})
    val = str(r.get("valuation", "")).upper()
    return {"summary": str(r.get("summary") or "")[:700],
            "scores": {k: _score(scores.get(k)) for k in ("moat", "growth", "value", "momentum", "health")},
            "composite": _score(r.get("composite")),
            "valuation": val if val in ("CHEAP", "FAIR", "RICH") else None,
            "valuation_note": str(r.get("valuation_note") or "")[:300],
            "bull": _clip(r.get("bull"), 5), "bear": _clip(r.get("bear"), 5), "segments": segs[:8],
            "position": str(r.get("position") or "")[:500], "watch": _clip(r.get("watch"), 4), "ideas": ideas[:3]}


def sector(q: str, region: str, ai) -> dict:
    where = ("INDIAN MARKET ONLY: every company must be listed on NSE/BSE (use NSE symbols as tickers), use rupees "
             "(crore/lakh) and Indian context; ETFs must be Indian." if region == "IN" else
             "US-listed companies (use US tickers) unless the theme is clearly global; use dollars.")
    system = f"""You are a sell-side analyst writing a specific, detailed picks-and-shovels dossier on a sector or theme.
{where}
Return ONLY this JSON:
{{"sector": "name", "summary": "3-4 sentences: what's happening, why now, who wins, the key dynamic",
 "market_size": "size with year", "cagr": 0, "cagr_note": "period",
 "etfs": [{{"ticker": "", "name": ""}}],
 "sub_themes": [{{"name": "", "detail": "2 specific sentences"}}],
 "core": "the point everything converges on",
 "clusters": [{{"name": "cluster", "companies": [{{"name": "", "ticker": ""}}]}}],
 "screen": [{{"name": "", "ticker": "", "layer": "value-chain layer", "composite": 0, "one_line": "why it's a shovel"}}],
 "value_chain": [{{"layer": "", "description": "3 sentences on its economics and where the margin sits",
                   "companies": [{{"name": "", "ticker": ""}}]}}],
 "tailwinds": ["specific sentences with numbers or names"], "risks": ["specific sentences with numbers or names"]}}
Sizes: 4-5 clusters of 4-6 real companies (empty ticker for private ones), 4 sub-themes, 6-8 ranked screen names
(composite 0-100), up to 4 ETFs, 4-5 value-chain layers of 3-5 companies, 4 tailwinds, 4 risks. Nothing generic.
{RULES}"""
    r = _ask(system, f"THEME: {q}\nTODAY: {ist_date().isoformat()}", ai, 6000)

    def cos(x):
        return [{"name": str(c.get("name") or "")[:60], "ticker": str(c.get("ticker") or "").upper()[:20]}
                for c in (x or []) if isinstance(c, dict) and c.get("name")][:8]
    return {
        "sector": str(r.get("sector") or q)[:80], "summary": str(r.get("summary") or "")[:900],
        "market_size": str(r.get("market_size") or "")[:80], "cagr": r.get("cagr"), "cagr_note": str(r.get("cagr_note") or "")[:40],
        "etfs": [{"ticker": str(e.get("ticker") or "")[:20], "name": str(e.get("name") or "")[:80]}
                 for e in (r.get("etfs") or []) if isinstance(e, dict)][:4],
        "sub_themes": [{"name": str(s.get("name") or "")[:80], "detail": str(s.get("detail") or "")[:400]}
                       for s in (r.get("sub_themes") or []) if isinstance(s, dict)][:6],
        "core": str(r.get("core") or "")[:120],
        "clusters": [{"name": str(c.get("name") or "")[:60], "companies": cos(c.get("companies"))}
                     for c in (r.get("clusters") or []) if isinstance(c, dict)][:6],
        "screen": sorted([{"name": str(s.get("name") or "")[:60], "ticker": str(s.get("ticker") or "").upper()[:20],
                           "layer": str(s.get("layer") or "")[:40], "composite": _score(s.get("composite")),
                           "one_line": str(s.get("one_line") or "")[:300]}
                          for s in (r.get("screen") or []) if isinstance(s, dict) and s.get("name")],
                         key=lambda s: -(s["composite"] or 0))[:8],
        "value_chain": [{"layer": str(v.get("layer") or "")[:60], "description": str(v.get("description") or "")[:600],
                         "companies": cos(v.get("companies"))} for v in (r.get("value_chain") or []) if isinstance(v, dict)][:6],
        "tailwinds": _clip(r.get("tailwinds"), 5), "risks": _clip(r.get("risks"), 5),
    }


def pulse(region: str, focus: str, indices: list[dict], headlines: list[dict], ai) -> dict:
    where = "Indian market only (NSE/BSE, Nifty/Sensex, rupees)." if region == "IN" else "US market (S&P 500, Nasdaq, Dow)."
    system = f"""You are a buy-side macro analyst writing today's market read{' focused on ' + focus if focus else ''}. {where}
Base everything ONLY on the live index levels and headlines given. Don't pull events or dates from memory.
Never say the market is at record highs unless an index's from_high_pct is above -0.5.
Return ONLY this JSON:
{{"tone": "3-4 sentences on the mood, what's driving it and which way risk leans, citing the live levels",
 "hot": [{{"name": "", "ticker": "", "why": "2 sentences"}}],
 "flows": [{{"title": "", "detail": "2 sentences", "direction": "INFLOW" | "OUTFLOW" | "ROTATION"}}],
 "themes": [{{"theme": "", "detail": "2 sentences", "example": "ticker"}}]}}
Exactly 4 hot names, 4 flows and 4 themes. Tickers are {'NSE symbols' if region == 'IN' else 'US tickers'}.
{RULES}"""
    facts = {"today": ist_date().isoformat(), "indices": indices,
             "headlines": [f"[{(h.get('at') or '')[:10]}] {h['headline']}" for h in headlines[:14]]}
    r = _ask(system, facts, ai, 2500)

    def rows(x, keys, n=4):
        return [{k: str(i.get(k) or "")[:400] for k in keys} for i in (x or []) if isinstance(i, dict)][:n]
    flows = rows(r.get("flows"), ("title", "detail", "direction"))
    for f in flows:
        f["direction"] = f["direction"].upper() if f["direction"].upper() in ("INFLOW", "OUTFLOW", "ROTATION") else "ROTATION"
    return {"tone": str(r.get("tone") or "")[:900], "hot": rows(r.get("hot"), ("name", "ticker", "why")),
            "flows": flows, "themes": rows(r.get("themes"), ("theme", "detail", "example"))}


def compare(a: dict, b: dict, ai) -> dict:
    system = f"""You are an equity analyst comparing two listed companies using ONLY the FACTS given.
Return ONLY this JSON:
{{"verdict": "2-3 sentences grounded in the numbers: which is stronger, and for what kind of investor",
 "winner": "the stronger ticker, or 'split'",
 "differences": ["3 short, specific contrasts"],
 "a": {{"composite": 0, "valuation": "CHEAP" | "FAIR" | "RICH"}},
 "b": {{"composite": 0, "valuation": "CHEAP" | "FAIR" | "RICH"}}}}
{RULES}"""
    r = _ask(system, {"A": company_facts(a), "B": company_facts(b)}, ai, 1500)

    def side(x):
        x = x if isinstance(x, dict) else {}
        v = str(x.get("valuation", "")).upper()
        return {"composite": _score(x.get("composite")), "valuation": v if v in ("CHEAP", "FAIR", "RICH") else None}
    winner = str(r.get("winner") or "").upper()
    return {"verdict": str(r.get("verdict") or "")[:700],
            "winner": winner if winner in (a["symbol"], b["symbol"]) else "SPLIT",
            "differences": _clip(r.get("differences"), 4), "a": side(r.get("a")), "b": side(r.get("b"))}
