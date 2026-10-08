"""AI reads for the research pages: a company read (with strategy ideas StratLab
can test), sector maps, the market pulse and head-to-head comparisons.

All of them go through the same free provider chain as the idea builder. Answers are
cached and shared between users, so a popular stock or theme costs one AI call."""
import hashlib
import json
import time

from ..ai_providers import AIError, complete, extract_json
from . import grounding
from .net import TTLCache
from ..kite_service import ist_date

_cache = TTLCache(max_items=2000)
BASICS = "price, simple moving average (SMA), exponential moving average (EMA) and RSI"
PRO = BASICS + ", MACD, Bollinger Bands, VWAP and Supertrend"

RULES = """Rules:
- Treat the FACTS as current and authoritative. Never contradict them, never claim the company is delisted or
  acquired, and don't invent precise figures that aren't in the facts. Mark anything you estimate as an estimate.
- Plain English a retail investor understands. No markdown, no emojis.
- Facts and analysis only, never advice: no buy, sell, hold, accumulate or avoid; no price targets; no "undervalued",
  "cheap", "expensive" or "worth buying"; no predictions of where a price will go; no ranking of stocks to own.
  Describe what the numbers and the company show, and let the reader decide.
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


def _share(v) -> int | None:
    try:
        return max(0, min(100, int(round(float(v)))))
    except (TypeError, ValueError):
        return None


def company_facts(c: dict) -> dict:
    """The compact, factual view of a profile the model is allowed to reason from."""
    q = c.get("quote") or {}
    # each figure under its group's name: India's "3Y CAGR" is in both Sales growth and Profit growth, and one
    # flat label kept only the profit one (R6O-001)
    metrics = {f"{g['title']}: {i['label']}": i["value"] for g in c.get("metrics") or [] for i in g["items"]}
    facts = {"name": c["name"], "symbol": c["symbol"], "market": "India (NSE)" if c["region"] == "IN" else "United States",
             "currency": c.get("currency"), "industry": c.get("industry"), "price": q.get("price"),
             "day_change_pct": q.get("change_pct"), "range_52w": c.get("range52"), "market_cap": c.get("market_cap"),
             "metrics": metrics, "margins": c.get("margins"),
             "annual_trend": c.get("trend"), "earnings_surprises": c.get("earnings"),
             "shareholding": c.get("shareholding"),
             "about": ((c.get("about") or {}).get("wiki") or {}).get("extract") or (c.get("about") or {}).get("profile"),
             "recent_headlines": [n["headline"] for n in (c.get("news") or [])[:6]], "today": ist_date().isoformat()}
    years = [p.get("y") for p in ((c.get("trend") or {}).get("revenue") or (c.get("trend") or {}).get("profit") or [])]
    if years:
        facts["latest_fiscal_year"] = (f"{years[-1]} is the latest full year reported; use it for the company's present. "
                                       "Every year in annual_trend is reported: none of them is estimated or upcoming.")
    qt = c.get("quarters") or {}
    if qt.get("cols"):
        facts["quarterly_results"] = {"quarters": qt["cols"], "sales": qt.get("sales"), "net_profit": qt.get("profit")}
    facts["results"] = results_status(c, ist_date())
    if c["region"] == "IN":
        fq, fy = grounding.fiscal_quarter(ist_date(), "IN")
        filed = (facts["results"] or {}).get("status") == "filed"
        facts["fiscal_now"] = (f"India's fiscal year runs April to March. The last quarter that ended is Q{fq} FY{fy}; "
                               + (f"its results are already filed and in quarterly_results." if filed
                                  else f"results due now are for Q{fq} FY{fy}."))
    return {k: v for k, v in facts.items() if v not in (None, [], {}, "")}


def results_status(c: dict, today) -> dict | None:
    """The latest quarter reported and whether its results are out (R6O-001, R6O-016): a results day on or before
    today whose quarter is already in the page's quarterly table is filed, not "due today"."""
    from datetime import date
    qt = c.get("quarters") or {}
    latest = (qt.get("cols") or [None])[-1]
    if not latest and c.get("earnings"):
        latest = max((str(e.get("period") or "") for e in c["earnings"]), default=None) or None
    end = grounding.quarter_end(latest or "")
    cal = c.get("results_calendar") or {}
    nxt = (cal.get("next") or {}).get("date") or (c.get("next_earnings") or {}).get("date")
    last = cal.get("last") or {}
    out: dict = {}
    if end:
        y, m = end
        end_day = date(y + (m == 12), m % 12 + 1, 1)          # the day after the quarter ended
        out["latest_quarter"] = latest + (f" ({grounding.india_label(end)})" if c.get("region") == "IN" and grounding.india_label(end) else "")
        out["latest_quarter_end"] = f"{y}-{m:02d}"
        if nxt:
            try:
                d = date.fromisoformat(str(nxt)[:10])
            except ValueError:
                d = None
            # the quarter before the results day is already in the table: those results are out
            if d and d <= today and 0 <= (d - end_day).days <= 75:
                nxt = None
    if nxt and str(nxt)[:10] >= today.isoformat():
        out["status"], out["next_results_date"] = "upcoming", str(nxt)[:10]
        out["note"] = f"The next results are on {str(nxt)[:10]}; the latest quarter reported is {out.get('latest_quarter') or 'not known'}."
    elif end:
        out["status"] = "filed"
        if last.get("date"):
            out["last_results_date"] = last["date"]
        out["note"] = (f"The results for {out['latest_quarter']} are already filed. No later results date is known: "
                       "do not call any results due, upcoming or today.")
    return out or None


SCORE_FIELDS = ("scores", "composite", "valuation", "rating", "grade")   # never sent, even from an old stored read


def company(c: dict, ai, pro: bool, key_facts: list[dict] | None = None) -> dict:
    """The AI's written read of one company. `key_facts` are the plain-number rows (growth, price trend, debt and
    cash, margins and returns) worked out without AI: the model reads them, and they go out with the read unchanged.
    No scores: a 0-100 number or a grade reads as a quality rating, which is advice."""
    system = f"""You are a careful research writer for StratLab, a tool that tests trading ideas honestly.
Given FACTS about one listed company, return ONLY this JSON:
{{"summary": "2-3 sentences: what the business is and the single most important thing about it right now",
 "valuation_note": "one sentence stating its valuation in numbers against its own history (e.g. P/E now vs its usual range), no judgement",
 "bull": ["3-4 specific strengths, as facts"], "bear": ["3-4 specific risks, as facts"],
 "position": "2 sentences on where it sits in its value chain and who it depends on",
 "watch": ["2-3 scheduled things ahead (the next results, a meeting, an ex-date), stated as facts with no view on the price"],
 "ideas": [{{"title": "3-6 words", "text": "one rule to test, in plain English", "why": "one sentence"}}]}}
No scores, ratings or grades of any kind: no 0-100 numbers, letter grades or stars, and no "strong", "weak", "good",
"poor", "healthy" or "excellent" labels on the business, its growth, its price trend or its balance sheet. State the
numbers instead, e.g. "operating margin has been 18-22% for five years" or "debt is 0.4 times equity".
"ideas" are exactly 3 trading ideas a trader could backtest on THIS stock, suited to how it behaves
(trend, mean reversion, breakout...). Each "text" must use only {PRO if pro else BASICS}, a timeframe
(daily candles unless intraday clearly suits it) and a stop loss, e.g.
"Enter long when the 20-day EMA crosses above the 50-day EMA, exit when it crosses back below, 5% stop loss". Write each as a rule
to test ("Enter long when …" or "Enter short when …"), never as an instruction to buy or sell the stock. Use only numbers
that are in the FACTS, copied as they are (a growth rate, yield or return is the FACTS' own figure, never your own
sum); label Indian fiscal quarters as the FACTS' fiscal_now does. Describe the present with latest_fiscal_year and the
results status in "results": a year or quarter the FACTS report is never "estimated", "upcoming" or "due". "watch"
lists only dates ahead that the FACTS give; with none, say the next results date isn't announced yet.
{RULES}"""
    facts = company_facts(c)
    if key_facts:
        facts["key_facts"] = {r["label"]: {i["label"]: i["text"] for i in r["items"]} for r in key_facts}
    r = _ask(system, facts, ai, 2500)
    ideas = []
    for i in r.get("ideas") or []:
        if isinstance(i, dict) and str(i.get("text", "")).strip():
            ideas.append({"title": str(i.get("title") or "Idea")[:60], "text": str(i["text"])[:400],
                          "why": str(i.get("why") or "")[:300]})
    if not str(r.get("summary") or "").strip() and not r.get("bull") and not r.get("bear"):
        raise AIError("The AI's reply was empty. Press Refresh to try again.")     # never cache a blank read
    read = {"summary": str(r.get("summary") or "")[:700], "facts": key_facts or [],
            "valuation_note": str(r.get("valuation_note") or "")[:300],
            # no revenue split: the model's guess isn't sourced (AAPL read "iPhone 100%, Services 0%, Mac 0%")
            "bull": _clip(r.get("bull"), 5), "bear": _clip(r.get("bear"), 5), "segments": [],
            "position": str(r.get("position") or "")[:500], "watch": _clip(r.get("watch"), 4), "ideas": ideas[:3]}
    # checked in code against the facts it was given: no advice or forecast, no number that isn't in them, the
    # right fiscal-quarter labels, ideas worded as rules to test (R5O-027)
    out = grounding.ground_company(read, facts, c.get("region") or "IN", ist_date())
    if not out["summary"] and not out["bull"] and not out["bear"]:
        raise AIError("The AI's read didn't hold up against the company's numbers. Press Refresh to try again.")
    return out


def clean_company(read: dict) -> dict:
    """A company read as it goes out: any score fields dropped (a read stored before scores were removed may
    still carry them), and an empty list of fact rows when it has none."""
    out = {k: v for k, v in read.items() if k not in SCORE_FIELDS}
    out["facts"] = out.get("facts") if isinstance(out.get("facts"), list) else []
    out["segments"] = []                        # a read stored with the model's unsourced revenue split shows none
    return out


def sector(q: str, region: str, ai) -> dict:
    where = ("INDIAN MARKET ONLY: every company must be listed on NSE/BSE (use NSE symbols as tickers), use rupees "
             "(crore/lakh) and Indian context; ETFs must be Indian." if region == "IN" else
             "US-listed companies (use US tickers) unless the theme is clearly global; use dollars.")
    system = f"""You are a research writer mapping a sector or theme: who does what, where the money is made, specific and detailed.
{where}
Return ONLY this JSON:
{{"sector": "name", "summary": "3-4 sentences: what's happening, why now, and the key dynamic",
 "market_size": "size with year", "cagr": 0, "cagr_note": "period",
 "etfs": [{{"ticker": "", "name": ""}}],
 "sub_themes": [{{"name": "", "detail": "2 specific sentences"}}],
 "core": "the point everything converges on",
 "clusters": [{{"name": "cluster", "companies": [{{"name": "", "ticker": ""}}]}}],
 "screen": [{{"name": "", "ticker": "", "layer": "value-chain layer", "one_line": "what it supplies to the theme, as a fact"}}],
 "value_chain": [{{"layer": "", "description": "3 sentences on its economics and where the margin sits",
                   "companies": [{{"name": "", "ticker": ""}}]}}],
 "tailwinds": ["specific sentences with numbers or names"], "risks": ["specific sentences with numbers or names"]}}
Sizes: 4-5 clusters of 4-6 real companies (empty ticker for private ones), 4 sub-themes, 6-8 screen names (listed
companies with the most direct link to the theme, in value-chain order, not ranked), up to 4 ETFs, 4-5 value-chain layers of 3-5 companies, 4 tailwinds, 4 risks. Nothing generic.
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
        "screen": [{"name": str(s.get("name") or "")[:60], "ticker": str(s.get("ticker") or "").upper()[:20],
                    "layer": str(s.get("layer") or "")[:40], "composite": None, "one_line": str(s.get("one_line") or "")[:300]}
                   for s in (r.get("screen") or []) if isinstance(s, dict) and s.get("name")][:8],
        "value_chain": [{"layer": str(v.get("layer") or "")[:60], "description": str(v.get("description") or "")[:600],
                         "companies": cos(v.get("companies"))} for v in (r.get("value_chain") or []) if isinstance(v, dict)][:6],
        "tailwinds": _clip(r.get("tailwinds"), 5), "risks": _clip(r.get("risks"), 5),
    }


def pulse(region: str, focus: str, indices: list[dict], headlines: list[dict], ai) -> dict:
    where = "Indian market only (NSE/BSE, Nifty/Sensex, rupees)." if region == "IN" else "US market (S&P 500, Nasdaq, Dow)."
    system = f"""You are a market reporter writing today's market read{' focused on ' + focus if focus else ''}. {where}
Base everything ONLY on the live index levels and headlines given. Don't pull events or dates from memory.
Never say the market is at record highs unless an index's from_high_pct is above -0.5. Describe where an index sits in its
52-week range only with from_low_pct and from_high_pct (above its low when from_low_pct is positive). Quote only numbers
from the FACTS. Mention a central bank, economic data, money flows or a sector only when a headline given names it.
Return ONLY this JSON:
{{"tone": "3-4 sentences on how the market moved today and what the headlines say is driving it, citing the live levels",
 "hot": [{{"name": "", "ticker": "", "why": "2 sentences: what the headlines report about it"}}],
 "flows": [{{"title": "", "detail": "2 sentences, as the headlines report it", "direction": "INFLOW" | "OUTFLOW" | "ROTATION"}}],
 "themes": [{{"theme": "", "detail": "2 sentences", "example": "ticker"}}]}}
"hot" are 4 companies named in today's headlines, with what the news says (not why to buy them). 4 flows, 4 themes.
No outlook: describe what happened, not what will happen. Tickers are {'NSE symbols' if region == 'IN' else 'US tickers'}.
{RULES}"""
    facts = {"today": ist_date().isoformat(), "indices": grounding.market_facts(indices),
             "headlines": [f"[{(h.get('at') or '')[:10]}] {h['headline']}" for h in headlines[:14]]}
    r = _ask(system, facts, ai, 2500)
    if not isinstance(r, dict) or not str(r.get("tone") or "").strip():     # never cache a read with nothing in it
        raise AIError("The AI didn't send a read of the market this time.")

    def rows(x, keys, n=4):
        return [{k: str(i.get(k) or "")[:400] for k in keys} for i in (x or []) if isinstance(i, dict)][:n]
    flows = rows(r.get("flows"), ("title", "detail", "direction"))
    for f in flows:
        f["direction"] = f["direction"].upper() if f["direction"].upper() in ("INFLOW", "OUTFLOW", "ROTATION") else "ROTATION"
    read = {"tone": str(r.get("tone") or "")[:900], "hot": rows(r.get("hot"), ("name", "ticker", "why")),
            "flows": flows, "themes": rows(r.get("themes"), ("theme", "detail", "example"))}
    # every claim checked in code against the index numbers and the headlines; what doesn't hold is dropped (R5O-018)
    return grounding.ground_pulse(read, indices, headlines)


def compare(a: dict, b: dict, ai) -> dict:
    system = f"""You are a research writer comparing two listed companies using ONLY the FACTS given.
Return ONLY this JSON:
{{"verdict": "2-3 sentences on how the two differ, grounded in the numbers, without saying which to own",
 "differences": ["3 short, specific contrasts in numbers"]}}
{RULES}"""
    r = _ask(system, {"A": company_facts(a), "B": company_facts(b)}, ai, 1500)
    verdict = str(r.get("verdict") or "").strip() if isinstance(r, dict) else ""
    if not verdict:                 # never cache (or show) a comparison with nothing in it
        raise AIError("The AI didn't send a comparison this time.")

    none = {"composite": None, "valuation": None}             # no scores or cheap/rich labels: that's advice
    return {"verdict": verdict[:700], "winner": "SPLIT",
            "differences": _clip(r.get("differences"), 4), "a": dict(none), "b": dict(none)}
