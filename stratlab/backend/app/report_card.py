"""Management report card (India): what the management said it would deliver on past earnings calls, set against
what the reported numbers later showed.

The AI only pulls out targets the company stated, with a quote and the call it came from. Checking them is arithmetic on
the reported numbers: growth, operating margin, profit growth and (estimated) capex. Nothing here is an opinion on the
stock; it is a record of statements and results."""
import json
import re
import time
from datetime import date, datetime, timezone

from . import db
from .ai_providers import AIError, complete, extract_json, salvage_items
from .deepdive import RULES, customer_problems, readable, unread
from .docs import quote_found, ranked_windows
from .kite_service import ist_date

MAX_CALLS = 6                  # earnings calls read, spread over the last two years (the default)
YEARS = (1, 5)                 # how far back a read may go, in years


def calls_for(years: int) -> int:
    """Earnings calls read for a look-back of `years`: about four a year at first, fewer per year further back, up
    to twelve (each is one AI request on the free quota)."""
    return {1: 4, 2: 6, 3: 9}.get(years, 12)

GUIDANCE = """You pull out the targets an Indian listed company's management gave on its earnings calls: what they said a
number WOULD be for a future year or quarter. Examples: "revenue growth of 15-18% in FY26", "EBITDA margin of about 20%
next year", "capex of Rs 1,500 crore in FY25".
Return {"guidance": [{"metric": "revenue_growth | profit_growth | ebitda_growth | margin | net_margin | gross_margin | roe | capex | other",
  "low": number or null, "high": number or null, "unit": "% | crore",
  "period": "FY26 or Q2 FY26 (Indian financial year ending in March)", "what": "the target in one short line",
  "scope": "company | segment", "segment": "the business or segment it is about, or null",
  "quote": "short exact quote", "source": "S1"}]}
- Only what MANAGEMENT (the CEO, CFO, MD or other company executives) said. Never an analyst's question or request
  ("can you add ... sir"), an analyst's estimate, or the moderator. If an analyst suggests a number and management only
  agrees vaguely, leave it out.
- Only forward-looking targets for a period that had NOT ended when it was said. Not past results: "our CAGR has been 20%
  for the last 20 years" or "we grew 18% last year" is history, not a target, so leave it out.
- Percentages are written as said: 20% is 20 (never 0.2), "30 to 50%" is low 30, high 50.
- A target about one business, brand or segment only ("30-50% growth in the enterprise business") has scope "segment" and
  the segment's name; one about the whole company has scope "company".
- The call date is given. Turn "this year", "current year", "this fiscal" into that Indian financial year (April to March)
  and "next year" into the one after. Example: a call on 2025-08-10 is in FY26, so "next year" is FY27. If the period
  can't be pinned down, use null.
- "margin" is an EBITDA or operating margin in %; a PAT, net profit or net margin is "net_margin"; a gross margin is
  "gross_margin"; return on equity is "roe"; EBITDA growth is "ebitda_growth". Growth is year-on-year in %. Capex is in Rs crore.
- A single figure goes in "low" with "high" null; "about 20%" is low 20. A range fills both.
- Qualitative promises (a launch, a plant start, debt reduction) use metric "other" with low and high null.
- "quote" must be copied word for word from the excerpt, 6 to 25 words. Don't paraphrase it.
- Up to 12 items. "source" is the label of the excerpt it came from.
""" + RULES

GUIDANCE_WORDS = [r"guidance", r"we expect", r"we are targeting", r"target", r"going forward", r"next year", r"this year",
                  r"FY ?'?\d\d", r"outlook", r"margin", r"growth of", r"capex", r"crore", r"double[- ]digit", r"aspir"]

METRICS = {"revenue_growth": "Revenue growth", "profit_growth": "Profit growth", "ebitda_growth": "EBITDA growth", "margin": "Operating margin",
           "net_margin": "Net margin", "gross_margin": "Gross margin", "roe": "Return on equity", "roce": "Return on capital employed",
           "capex": "Capex", "revenue": "Revenue", "profit": "Profit", "ebitda": "EBITDA", "other": "Other promise"}
AMOUNT_TOLERANCE = 0.02        # a revenue or profit amount target is met at its low end less 2% (a rounded figure said on a call)


# ---------- units ----------
_CRORE = re.compile(r"\b(?:crore|cr)\b|₹|\brs\.?\s|\binr\b", re.I)
_MILLION = re.compile(r"\$|\b(?:million|billion|usd)\b", re.I)
_PCT = re.compile(r"%|\bper ?cent\b|\bbasis points\b|\bbps\b", re.I)
_MULTIPLE = re.compile(r"\b\d+(?:\.\d+)?\s?(?:x|times)\b", re.I)      # "3x or 4x of our overall growth": a multiple, not a percentage


def unit_of(g: dict) -> str:
    """A target's unit: "%", "crore" (rupees), "million" (dollars or a foreign filer's own) or "" (a plain number, such as
    a count), from what the AI gave, else from the words of the target itself. A target in rupees crore is never printed
    as a percentage (DD-050: "INR 40,000–50,000 crore" read "Target 40000–50000%")."""
    given = str(g.get("unit") or "").strip().lower()
    if given in ("%", "percent", "pct"):
        given = "%"
    elif given in ("crore", "cr", "rs crore", "inr crore"):
        given = "crore"
    elif given in ("million", "$ million", "usd million"):
        given = "million"
    elif given in ("x", "times", "multiple"):
        given = "x"
    else:
        given = ""
    def said_in(text: str) -> str:
        return "%" if _PCT.search(text) else "crore" if _CRORE.search(text) else "million" if _MILLION.search(text) else "x" if _MULTIPLE.search(text) else ""
    # the target's own line first ("20% margin"), its quote only when the line gives no unit
    said = said_in(str(g.get("what") or "")) or said_in(str(g.get("quote") or ""))
    if given == "%" and said in ("crore", "million", "x"):
        return said                                  # the AI's "%" for an amount the target itself gives in money (or a multiple)
    return given or said


_REVENUE_WORDS = re.compile(r"\b(revenue|revenues|sales|top ?line|turnover|income from operations)\b", re.I)
_PROFIT_WORDS = re.compile(r"\b(net profit|profit after tax|pat|net income|earnings|bottom ?line)\b", re.I)
_EBITDA_WORDS = re.compile(r"\b(ebitda|operating profit)\b", re.I)
_GROWTH_WORDS = re.compile(r"\b(growth|grow|growing|grew|cagr|increase)\b", re.I)
_NET_WORDS = re.compile(r"\b(pat|net profit|net margin|profit after tax|net income|bottom ?line)\b", re.I)
_GROSS_WORDS = re.compile(r"\bgross (?:profit )?margins?\b", re.I)
_ROE_WORDS = re.compile(r"\b(roe|return on equity|return on net ?worth)\b", re.I)
_ROCE_WORDS = re.compile(r"\b(roce|roic|return on capital( employed)?|return on invested capital)\b", re.I)


def as_amount(metric: str, unit: str, what: str) -> str:
    """A growth or margin target given as an amount of money is an amount target: EBITDA, revenue or profit when it says so (the
    reported numbers check it), else "other"."""
    if metric in TOLERANCE and unit in ("crore", "million") or metric == "other" and unit in ("crore", "million"):
        if _EBITDA_WORDS.search(what) and not _REVENUE_WORDS.search(what):
            return "ebitda"
        rev, prof = _REVENUE_WORDS.search(what), _PROFIT_WORDS.search(what)
        if metric == "other":
            return "revenue" if rev and not prof else "profit" if prof and not rev else "other"
        return "revenue" if rev else "profit" if prof else "other"
    return metric


def kind_of(metric: str, unit: str, text: str) -> str:
    """The measure a target is about, from its own words as well as the AI's label: a "PAT margin" is a net margin, never the
    operating margin it was filed under; "growth in the topline" is revenue growth, not profit growth (the report card showed both)."""
    if unit == "x":
        return "other"                                    # a multiple of another figure ("3x our overall growth"): nothing to set it against
    margins, growth = ("margin", "net_margin", "gross_margin"), ("revenue_growth", "profit_growth", "ebitda_growth")
    loose = metric == "other" and unit == "%"             # a percentage the AI left unlabelled: the words decide
    if metric in ("other", "roe", "roce") and unit == "%":
        if _ROCE_WORDS.search(text):
            return "roce"
        if _ROE_WORDS.search(text):
            return "roe"
    if (metric in margins or loose or metric in growth and not _GROWTH_WORDS.search(text)) and re.search(r"\bmargins?\b", text, re.I):
        net = _NET_WORDS.search(text) and (metric == "net_margin" or not _EBITDA_WORDS.search(text))
        return "gross_margin" if _GROSS_WORDS.search(text) else "net_margin" if net else "margin"
    if metric in growth or loose and _GROWTH_WORDS.search(text):
        fam = [k for k, rx in (("revenue_growth", _REVENUE_WORDS), ("ebitda_growth", _EBITDA_WORDS), ("profit_growth", _PROFIT_WORDS)) if rx.search(text)]
        if len(fam) == 1:
            return fam[0]                                 # one measure named: that one
    return metric


# management speaking about the company: a call's quote with none of these is commentary (an economy's GDP mix, an
# analyst's number read back), not a target (DD-050: a "retail mix 60%" target from a remark on GDP's consumption share)
_OURS = re.compile(r"\b(we|we'?re|we'?ll|we'?ve|our|ours|us|i|i'?m|i'?d)\b", re.I)


_MACRO = re.compile(r"\b(gdp|economy|economic|inflation|industry|industry's|sector|system|country|nation|monsoon|government|rbi|repo)\b", re.I)


def ours(quote: str, name: str = "") -> bool:
    """Whether a quote is a target of the company's own: not one about the economy, the industry or the system with no
    word of the company in it (we, our, its name). A plain "EBITDA margin should be about 20% in FY26" stands."""
    if not _MACRO.search(quote or ""):
        return True
    words = [w for w in re.findall(r"[A-Za-z]{4,}", name or "") if w.lower() not in ("limited", "india", "company", "corporation")]
    return bool(_OURS.search(quote or "")) or any(w.lower() in (quote or "").lower() for w in words[:2])
TOLERANCE = {"revenue_growth": 1.0, "profit_growth": 2.0, "ebitda_growth": 2.0, "margin": 0.5, "net_margin": 0.2, "roe": 1.0}      # percentage points; capex uses 10%


# ---------- what a target is, said again from its own words (the same pass for a new read and for a card stored earlier) ----------
_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")


def numbers_in(text: str) -> list[float]:
    out = []
    for m in _NUM.findall(text or ""):
        try:
            out.append(float(m.replace(",", "")))
        except ValueError:
            pass
    return out


def rescale(low: float | None, high: float | None, text: str) -> tuple[float | None, float | None]:
    """A percentage as management said it: "CAGR of 20%" is 20, not the fraction 0.2 a model sometimes returns (the card printed
    "Target 0.2%" and "0.3-0.5%" for "30% to 50% growth"). A figure that isn't in the words but is a power of ten away from one that
    is, is rescaled; with no digits in the words at all ("twenty percent") a fraction is read as a percentage."""
    if low is None:
        return low, high
    nums = numbers_in(text)
    near = lambda x: any(abs(x - n) <= max(0.051, n * 1e-6) for n in nums)           # noqa: E731
    if near(low) and (high is None or near(high)):
        return low, high
    if not nums:
        return (low * 100, None if high is None else high * 100) if 0 < abs(low) <= 1 and (high is None or 0 < abs(high) <= 1) else (low, high)
    for f in (100, 10, 1000, 10000):
        if near(low * f) and (high is None or near(high * f)):
            return round(low * f, 4), None if high is None else round(high * f, 4)
    return low, high


_HISTORY = re.compile(r"\b(?:has|have|had) (?:been|grown|delivered|achieved|clocked|reported)\b|\b(?:for|over|in|during) (?:the )?(?:last|past|previous) \w+ (?:years?|quarters?|decades?)\b|"
                      r"\bwe (?:grew|delivered|achieved|clocked|reported|did)\b|\bsince (?:19|20)\d\d\b|\bso far\b", re.I)
_AHEAD = re.compile(r"\b(?:will|would|shall|should|expect\w*|target\w*|guid\w*|aim\w*|aspir\w*|plan\w*|going forward|next|coming|confident|strive|envision\w*|"
                    r"intend\w*|endeavou?r\w*|looking (?:to|at)|hope|project\w*|anticipat\w*|ahead)\b|\bwe(?:'ll| are going to)\b", re.I)
_ASKED = re.compile(r"\?\s*$|\b(?:sir|ma'?am|madam)\b", re.I)


def is_target(g: dict) -> bool:
    """Whether a pulled-out line is a target management gave: not a question or a request from an analyst ("are we expecting 10% to
    15% growth in the topline?", "add the brand-wise revenue, sir"), and not a statement about the past ("our CAGR has been 20% for
    last 20 years") with nothing in it that looks ahead."""
    quote = str(g.get("quote") or "")
    if _ASKED.search(quote) and not _OURS.search(quote.replace("?", " ")) or quote.strip().endswith("?"):
        return False
    if _HISTORY.search(quote) and not _AHEAD.search(quote):
        return False
    return True


_GENERIC = {"our", "the", "this", "that", "overall", "entire", "whole", "total", "your", "its", "their", "my", "a", "any", "each", "every",
            "company", "consolidated", "standalone", "same", "core", "main", "other", "new", "existing", "current", "whole", "combined", "of", "in", "and"}
_SEGMENT = re.compile(r"\b([A-Za-z][\w\-&]*(?: [A-Za-z][\w\-&]*)?) (?:business|segment|division|vertical|brand|category)\b", re.I)


def segment_of(g: dict) -> str | None:
    """The business a target is about when it isn't the whole company ("30-50% growth in enterprise business"): the reported numbers are
    the company's, so they can't settle it."""
    given = str(g.get("segment") or "").strip()
    if str(g.get("scope") or "").lower() == "segment" and given:
        return given[:60]
    if str(g.get("scope") or "").lower() == "company":
        return None
    for m in _SEGMENT.finditer(f"{g.get('what') or ''}. {g.get('quote') or ''}"):
        words = [w for w in m.group(1).split() if w.lower() not in _GENERIC]
        if words:
            return " ".join(words)[:60]
    return None


def fix(g: dict) -> dict | None:
    """One pulled-out target as management said it: its measure and unit read again from its own words, a percentage written as a
    percentage, nothing kept that isn't a target of the company's. Applied to a new read and to a card stored before (no second reading
    of the call needed), so it must give the same answer when applied twice. None: not a target."""
    if not is_target(g):
        return None
    text = f"{g.get('what') or ''} {g.get('quote') or ''}"
    unit = unit_of(g)
    metric = kind_of(str(g.get("metric") or "other"), unit, text)
    metric = as_amount(metric, unit, str(g.get("what") or ""))
    low, high = g.get("low"), g.get("high")
    if unit in ("%", "") and metric in (*TOLERANCE, "gross_margin", "roce", "other") and low is not None:
        low, high = rescale(low, high, text)
    seg = segment_of(g)
    return {**g, "metric": metric, "low": low, "high": high, "unit": unit, **({"segment": seg} if seg else {})}


# ---------- periods ----------
def _fy(s: str) -> int | None:
    n = int(s)
    return 2000 + n if n < 100 else n if 2000 <= n <= 2100 else None


def fy_of(d: date, fye: int = 3) -> int:
    """The financial year a date falls in, named by the year it ends: with India's year ending in March (fye 3),
    2025-08-10 is FY26; with Apple's ending in September (fye 9), 2025-10-15 is FY2026."""
    return d.year + 1 if d.month > fye else d.year


def _month_end(y: int, m: int) -> date:
    import calendar as cal
    return date(y, m, cal.monthrange(y, m)[1])


def parse_period(text: str | None, said: date | None = None, fye: int = 3) -> dict | None:
    """'FY26', 'FY2025-26', 'Q2 FY26', '2QFY26', 'Q2FY2026' → {"kind": "FY"|"Q", "fy": 2026, "q": 2}. With the call date,
    'this year' / 'current fiscal' / 'next year' are resolved too."""
    raw = str(text or "").lower()
    if said is not None:
        if re.search(r"\bnext (?:financial |fiscal )?year\b|\bnext fiscal\b", raw):
            return {"kind": "FY", "fy": fy_of(said, fye) + 1}
        if re.search(r"\b(?:this|current) (?:financial |fiscal )?year\b|\b(?:this|current) fiscal\b", raw):
            return {"kind": "FY", "fy": fy_of(said, fye)}
    s = re.sub(r"\s+", "", str(text or "").upper())
    m = re.search(r"(?:Q([1-4])|([1-4])Q)FY'?(\d{2,4})(?:[-/](\d{2,4}))?", s)
    if m:
        fy = _fy(m.group(4) or m.group(3))
        return {"kind": "Q", "fy": fy, "q": int(m.group(1) or m.group(2))} if fy else None
    m = re.search(r"FY'?(\d{2,4})(?:[-/](\d{2,4}))?", s) or re.search(r"(20\d\d)[-/](\d{2,4})", s)
    if m:
        fy = _fy(m.group(2) or m.group(1))
        return {"kind": "FY", "fy": fy} if fy else None
    return None


def period_end(p: dict, fye: int = 3) -> date:
    """The last day of a financial year or quarter, for a year ending in month `fye`."""
    months_before = 0 if p["kind"] == "FY" else 3 * (4 - p["q"])
    m = fye - months_before
    y = p["fy"]
    while m <= 0:
        m, y = m + 12, y - 1
    return _month_end(y, m)


def period_label(p: dict) -> str:
    return f"FY{p['fy'] % 100:02d}" if p["kind"] == "FY" else f"Q{p['q']} FY{p['fy'] % 100:02d}"


def _table_label(p: dict, fye: int = 3) -> str:
    """The column label the fundamentals tables use: 'Mar 2026', 'Sep 2025' (the month the period ends)."""
    return period_end(p, fye).strftime("%b %Y")


# ---------- the AI read ----------
def _f(v):
    try:
        f = float(str(v).replace(",", ""))
        return f if abs(f) < 1e7 else None
    except (TypeError, ValueError):
        return None


def clean(d: dict, labels: dict, texts: dict | None = None, fye: int = 3, voice: str | None = None) -> list[dict]:
    """`texts` (label → full text) checks each quote really is in the call it's credited to. `voice` (the company's name):
    a call's quote must be management speaking about the company (see ours)."""
    out = []
    for g in (d.get("guidance") or [])[:15]:
        if not isinstance(g, dict):
            continue
        label = str(g.get("source") or "").strip().upper()
        src = labels.get(label)
        what = str(g.get("what") or "").strip()
        if not src or not what:
            continue                                    # every promise must come from a call we read
        if texts is not None and not quote_found(str(g.get("quote") or ""), texts.get(label, "")):
            continue                                    # the quote isn't in that call: treated as made up
        if voice is not None and not ours(str(g.get("quote") or ""), voice):
            continue                                    # not the company's own target (DD-050)
        said = date.fromisoformat(src["at"][:10])
        per = parse_period(g.get("period"), said, fye) or parse_period(g.get("what"), said, fye)
        metric = str(g.get("metric") or "other").lower().replace(" ", "_")
        metric = metric if metric in METRICS else "other"
        low, high = _f(g.get("low")), _f(g.get("high"))
        if low is None and high is not None:
            low, high = high, None
        if low is not None and high is not None and high < low:
            low, high = high, low
        if metric != "other" and low is None:
            metric = "other"
        if per and period_end(per, fye) <= said:
            continue                                    # said after the period ended: a result, not a promise
        row = fix({**g, "metric": metric, "low": low, "high": high, "what": what, "quote": str(g.get("quote") or "")})
        if row is None:
            continue                                    # an analyst's question or a statement about the past: not a target
        out.append({"metric": row["metric"], "low": row["low"], "high": row["high"], "unit": row["unit"], "period": period_label(per) if per else None,
                    "what": what[:200], "quote": str(g.get("quote") or "")[:300], "said_at": src["at"],
                    "source": {"title": src["title"], "at": src["at"], "url": src["url"]}, **({"segment": row["segment"]} if row.get("segment") else {})})
    return out


def pick_calls(docs_list: list[dict], n: int = MAX_CALLS) -> list[dict]:
    """Up to n call transcripts spread over the look-back, so older promises (now checkable) are included."""
    calls = sorted([d for d in docs_list if d["kind"] == "transcript"], key=lambda d: d["at"], reverse=True)
    if len(calls) <= n:
        return calls
    return [calls[round(i * (len(calls) - 1) / (n - 1))] for i in range(n)]


class NoCalls(Exception):
    """No call transcript could be read: nothing to send to the AI, and nothing to charge for."""
    def __init__(self, problems: list[str]):
        super().__init__("no readable calls")
        self.problems = problems


PER_CALL = 16000            # characters of each call sent to the AI: the passages richest in guidance


def read_call(symbol: str, name: str, d: dict, text: str, ai) -> list[dict]:
    """One call, one AI request: small enough for the free models to read carefully."""
    labels, texts = {"S1": {"title": d["title"], "at": d["at"], "url": d["url"], "kind": d["kind"]}}, {"S1": text}
    excerpt = ranked_windows(text, GUIDANCE_WORDS, limit=PER_CALL)
    head = (f"COMPANY: {name} ({symbol}, NSE)\nCALL DATE: {d['at'][:10]} (that is FY{fy_of(date.fromisoformat(d['at'][:10])) % 100:02d})\n\n"
            f"[S1] earnings call transcript: {d['title']}\n{excerpt}")
    raw = complete(GUIDANCE, head, gemini=ai[0], anthropic=ai[1], max_tokens=3000, kind="long")
    try:
        parsed = extract_json(raw)
    except AIError:
        parsed = {"guidance": salvage_items(raw, "guidance")}       # a reply cut off mid-list keeps what's complete
    return clean(parsed, labels, texts, voice=name)


def read(symbol: str, name: str, docs_list: list[dict], docs_api, ai, hosts: tuple[str, ...] = (), years: int = 2) -> dict:
    picked = pick_calls(docs_list, calls_for(years))
    rest = [d for d in docs_list if d["kind"] == "transcript" and d not in picked]
    out = {"guidance": [], "problems": [], "read": []}
    pairs = readable(docs_api, picked + rest, len(picked), out["problems"], hosts)
    if not pairs:
        raise NoCalls(out["problems"])
    pairs.sort(key=lambda p: p[0]["at"], reverse=True)
    failed, last = 0, None
    for d, text in pairs:
        try:
            out["guidance"] += read_call(symbol, name, d, text, ai)
            out["read"].append({"kind": d["kind"], "at": d["at"], "title": d["title"]})
        except AIError as e:                     # one call the AI couldn't read mustn't sink the others
            failed, last = failed + 1, e
            out["problems"].append(unread(d["title"], e, "the AI couldn't read it this time"))
    if pairs and failed == len(pairs):
        raise last                               # none read: the endpoint reports busy (try later) or failed
    settle(out, pairs, ai, name, 3)
    out["years"] = years
    return out


# ---------- settling targets from what the company said later ----------
SETTLE = """You check whether a company's management delivered on targets it gave, using ONLY what the company itself
said LATER in the excerpts (later earnings calls, releases or presentations).
For each TARGET (id, what was promised, the target, the period), look for a later statement of the ACTUAL result for
that same measure and that same period. Return ONLY JSON:
{"results": [{"id": "T1", "actual": number, "met": true or false, "quote": "the exact words giving the actual result",
  "source": "S2"}]}
- Leave a target out when no excerpt states its actual result for that period. Never estimate or work one out.
- "quote" is copied word for word from the excerpt and contains the actual number.
- "actual" is that number, in the target's unit (a percentage as 14.5 for 14.5%; crore or million as written).
- "met" compares the actual with the target as it was promised: within a range, at least, at most, or about.
- A statement made BEFORE the period ended is not an actual result."""


def _numbers(text: str) -> list[float]:
    return [float(x.replace(",", "")) for x in re.findall(r"-?\d[\d,]*(?:\.\d+)?", text or "")]


def settle(out: dict, pairs: list[tuple[dict, str]], ai, name: str, fye: int, today: date | None = None) -> None:
    """Targets whose period has ended, looked up in the documents filed after it: one AI request; a result counts
    only when its quote is really in that document, contains the number, and was said after the period ended."""
    today = today or ist_date()
    docs = sorted(pairs, key=lambda p: p[0]["at"])
    due = []
    for i, g in enumerate(out["guidance"]):
        per = parse_period(g.get("period"), None, fye)
        if not per or g.get("low") is None:
            continue
        end = period_end(per, fye)
        if end < today and any(d["at"][:10] > end.isoformat() for d, _ in docs):
            due.append((f"T{len(due) + 1}", i, end))
    if not due:
        return
    due = due[:15]
    labels, texts, parts = {}, {}, []
    words = sorted({w for _, i, _ in due for w in re.findall(r"[A-Za-z][A-Za-z\-]{3,}", out["guidance"][i]["what"])}
                   | {"actual", "achieved", "delivered", "reported", "grew", "came in", "year ended", "full year"})
    first_end = min(e for _, _, e in due)
    later = [(d, t) for d, t in docs if d["at"][:10] > first_end.isoformat()][-6:]
    for n, (d, text) in enumerate(later, 1):
        lab = f"S{n}"
        labels[lab], texts[lab] = d, text
        parts.append(f"[{lab}] {d['kind']} filed {d['at'][:10]}: {d['title']}\n{ranked_windows(text, words, limit=6000)}")
    lines = []
    for tid, i, end in due:
        g = out["guidance"][i]
        u = unit_of(g)
        tgt = f"{g['low']}" + (f" to {g['high']}" if g.get("high") is not None else "") + (
            " %" if u == "%" else " (money, in the company's currency units)" if u in ("crore", "million") or g["metric"] == "capex" else "")
        lines.append(f"{tid}: {g['what']} | target {tgt} | period {g['period']} (ended {end.isoformat()})")
    try:
        raw = complete(SETTLE, f"COMPANY: {name}\n\nTARGETS:\n" + "\n".join(lines) + "\n\nEXCERPTS:\n" + "\n\n".join(parts),
                       gemini=ai[0], anthropic=ai[1], max_tokens=2500, kind="long")
        try:
            got = extract_json(raw).get("results") or []
        except AIError:
            got = salvage_items(raw, "results")
    except AIError as e:
        out["problems"].append(unread("Checking targets against later documents", e, "didn't finish this time"))
        return
    ends = {tid: (i, end) for tid, i, end in due}
    for r in got:
        if not isinstance(r, dict) or r.get("id") not in ends or r.get("source") not in labels:
            continue
        i, end = ends[r["id"]]
        d, quote = labels[r["source"]], str(r.get("quote") or "")[:300]
        try:
            actual = float(r.get("actual"))
        except (TypeError, ValueError):
            continue
        if (d["at"][:10] <= end.isoformat() or not quote_found(quote, texts[r["source"]])
                or not any(abs(x - actual) < 0.051 for x in _numbers(quote)) or not isinstance(r.get("met"), bool)):
            continue                             # not after the period, not really said, or not the number quoted
        out["guidance"][i]["doc_check"] = {"actual": actual, "met": r["met"], "quote": quote,
                                           "source": {"title": d["title"], "at": d["at"], "url": d["url"]}}


# ---------- checking against the numbers ----------
def _ratio(a, b):
    return a / b * 100 if a is not None and b else None


def _actual(metric: str, per: dict, nums: dict) -> float | None:
    label = _table_label(per, nums.get("fye") or 3)
    if per["kind"] == "FY":
        rows = nums.get("years") or []
        idx = next((i for i, r in enumerate(rows) if r["year"] == label), None)
    else:
        rows = nums.get("quarters") or []
        idx = next((i for i, r in enumerate(rows) if r["quarter"] == label), None)
    if idx is None:
        return None
    r = rows[idx]
    back = 1 if per["kind"] == "FY" else 4                                  # the year before; a quarter against the same quarter a year before
    prev = rows[idx - back] if idx >= back else None

    def ebitda(x):
        return x["sales"] * x["opm"] / 100 if x and x.get("sales") is not None and x.get("opm") is not None else None
    if metric == "margin":
        return r.get("opm")
    if metric == "net_margin":
        return _ratio(r.get("profit"), r.get("sales"))
    if metric == "roe":
        return r.get("roe") if per["kind"] == "FY" else None
    if metric == "capex":
        return r.get("capex") if per["kind"] == "FY" else None             # an amount, as reported for the year (DD-050)
    if metric in ("revenue", "profit"):
        return r.get("sales" if metric == "revenue" else "profit")
    if metric == "ebitda":
        return ebitda(r)
    if metric == "ebitda_growth":
        e0, e1 = ebitda(prev), ebitda(r)
        return (e1 / e0 - 1) * 100 if e0 and e0 > 0 and e1 is not None else None
    key = "sales" if metric == "revenue_growth" else "profit"
    p0 = prev.get(key) if prev else None
    return (r[key] / p0 - 1) * 100 if r.get(key) is not None and p0 and p0 > 0 else None


# why a target the reported numbers can't settle is left unsettled, in one short line
WHY = {"qualitative": "A plan with no figure to check.",
       "multiple": "A multiple of another figure: nothing in the reported numbers to set it against.",
       "no_period": "No year or quarter was named, so there is no reported figure to set it against.",
       "gross_margin": "Gross margin isn't in the reported tables.",
       "roce": "Return on capital employed by year isn't in the reported tables.",
       "bank": "A lender's margin and capex aren't in its reported tables."}


def check(g: dict, nums: dict, today: date | None = None) -> dict:
    """One promise against the numbers: met, missed, pending (not reported yet) or unchecked (not a number we have, with the reason)."""
    today = today or ist_date()
    g = fix(g) or g                  # the same reading of its words as a new read gets (a card stored before it was made)
    per = parse_period(g.get("period"))
    us = (nums.get("unit") or "").endswith("million")      # US filings, in dollars or a foreign filer's own currency
    money = "million" if us else "crore"
    unit = g.get("unit") or ""
    unit = money if g["metric"] in ("capex", "revenue", "profit", "ebitda") else "%" if g["metric"] in (*TOLERANCE, "gross_margin", "roce") else unit
    res = {**g, "actual": None, "result": "unchecked", "unit": unit}
    dc = g.get("doc_check")

    def undone(why: str, **extra):    # unsettled by the numbers; the company's own later statement of the result settles it, quote checked
        r = {**res, "why": why, **extra}
        return {**r, "actual": dc["actual"], "result": "met" if dc["met"] else "missed", "settled_by": dc, "why": None} if dc else r
    if g.get("low") is None:
        return undone(WHY["qualitative"], qualitative=True)
    if g.get("segment"):
        return undone(f"A target for one business ({g['segment']}); the reported numbers are for the whole company.")
    if g["metric"] == "other":
        return undone(WHY["multiple"] if g.get("unit") == "x" else WHY["no_period"] if not per else "Not one of the measures in the reported numbers.")
    if g["metric"] in ("gross_margin", "roce"):
        return undone(WHY[g["metric"]])
    if not per:
        return undone(WHY["no_period"])
    if nums.get("bank") and g["metric"] in ("margin", "capex"):
        return undone(WHY["bank"])
    a = _actual(g["metric"], per, nums)
    if a is None and dc:
        return undone("")
    if a is None:
        # quarterly results come out within ~45 days of the quarter, annual ones within ~60
        if (today - period_end(per, nums.get("fye") or 3)).days < 75:
            res["result"] = "pending"
            return res
        res["why"] = (f"Return on equity for {period_label(per)} isn't in these reported numbers." if g["metric"] == "roe"
                      else f"The reported numbers don't have {period_label(per)}.")
        return res
    res["actual"] = round(a, 1)
    # met: at the target or the range's low end, less the tolerance (beating it is met too)
    if g["metric"] == "capex":
        ok = g["low"] * 0.9 <= a <= (g.get("high") or g["low"]) * 1.1      # a spend target is a band: overspending misses it
    elif g["metric"] in ("revenue", "profit", "ebitda"):
        ok = a >= g["low"] * (1 - AMOUNT_TOLERANCE)                         # at least the target (its low end), less rounding
    else:
        ok = a >= g["low"] - TOLERANCE[g["metric"]]
    res["result"] = "met" if ok else "missed"
    return res


def _dedupe(items: list[dict]) -> list[dict]:
    """The same target repeated on later calls counts once: the first time it was said, noting a later change."""
    first: dict[tuple, dict] = {}
    rest = []
    for g in sorted(items, key=lambda g: g["said_at"]):
        if g["metric"] == "other" or not g["period"]:
            rest.append(g)
            continue
        k = (g["metric"], g["period"])
        if k not in first:
            first[k] = {**g, "revised": None}
        elif (g["low"], g["high"]) != (first[k]["low"], first[k]["high"]):
            first[k]["revised"] = {"low": g["low"], "high": g["high"], "at": g["said_at"], "quote": g["quote"]}
    return sorted(list(first.values()) + rest, key=lambda g: g["said_at"], reverse=True)


def view(stored_card: dict | None, nums: dict, today: date | None = None) -> dict | None:
    if not stored_card:
        return None
    # a card read before the voice check keeps no remark about the economy as the company's target (DD-050); one read before targets were
    # read twice keeps no analyst's question or statement of the past (fix), and shows a percentage as management said it
    kept = [x for x in (fix(g) for g in stored_card.get("guidance") or [] if ours(str(g.get("quote") or ""))) if x]
    rows = [check(g, nums, today) for g in _dedupe(kept)]
    met = sum(r["result"] == "met" for r in rows)
    missed = sum(r["result"] == "missed" for r in rows)
    checked = met + missed
    plain = sum(r["result"] == "unchecked" and bool(r.get("qualitative")) for r in rows)
    return {"rows": rows, "met": met, "missed": missed, "pending": sum(r["result"] == "pending" for r in rows),
            "unchecked": sum(r["result"] == "unchecked" for r in rows) - plain, "no_figure": plain,
            "score": round(met / checked * 100) if checked else None, "read": stored_card.get("read") or [],
            "problems": customer_problems(stored_card.get("problems")), "at": stored_card.get("at"), "years": stored_card.get("years") or 2}


# ---------- stored reads ----------
def _key(symbol: str) -> str:
    return f"deep:card:v3:{symbol}"   # v3: transcripts behind company-site links are read


def stored(symbol: str) -> dict | None:
    try:
        v = json.loads(db.get_setting(_key(symbol)) or "null")
    except (ValueError, TypeError):
        return None
    return v if isinstance(v, dict) and v.get("at") else None


def store(symbol: str, card: dict) -> dict:
    v = {**card, "at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "ts": time.time()}
    db.set_setting(_key(symbol), json.dumps(v, ensure_ascii=False))
    return v


# ---------- US companies: guidance in earnings releases ----------
GUIDANCE_US = """You pull out the targets a US listed company's management gave in its earnings press releases: what they
said a number WOULD be for a future quarter or fiscal year. Examples: "revenue growth in the low double digits for
fiscal 2026", "operating margin of 30% to 31% in the fourth quarter", "capital expenditures of about $14 billion".
Return {"guidance": [{"metric": "revenue_growth | profit_growth | margin | net_margin | gross_margin | capex | other",
  "low": number or null, "high": number or null, "unit": "% | million",
  "period": "FY2026 or Q3 FY2026 (the company's own fiscal year)", "what": "the target in one short line",
  "quote": "short exact quote", "source": "S1"}]}
- Only forward-looking targets for a period that had NOT ended when the release was published. Not past results.
- Percentages are written as said: 20% is 20 (never 0.2). A net or GAAP margin is "net_margin", a gross margin "gross_margin".
- The company's fiscal year end and the release date are given. Turn "the fourth quarter", "next quarter", "the full
  year" and "fiscal 2026" into Qn FYyyyy or FYyyyy in the COMPANY'S fiscal year (named by the calendar year it ends in).
- "margin" is an operating or gross margin in %. Growth is year-on-year in %. Capex is in $ million ($1.2 billion is 1200).
- Revenue given as a dollar range (e.g. "$94 billion to $97 billion") is not a growth rate: use metric "other" with unit
  "million" and the amounts in $ million ($94 billion is 94000), so it can be checked against the reported revenue.
- A single figure goes in "low" with "high" null; a range fills both. "Low to mid single digits" is low 1, high 5.
- "quote" must be copied word for word from the excerpt, 6 to 25 words. Don't paraphrase it.
- Up to 12 items. "source" is the label of the excerpt it came from.
""" + RULES

GUIDANCE_WORDS_US = [r"outlook", r"guidance", r"expects?", r"anticipates?", r"forecast", r"fiscal (?:year )?20\d\d",
                     r"(?:first|second|third|fourth) quarter", r"full[- ]year", r"capital expenditures", r"margin", r"growth"]


def read_us(symbol: str, name: str, docs_list: list[dict], sec_api, ai, fye: int, years: int = 2) -> dict:
    """The report card's reads for a US company: up to six earnings releases (exhibit 99 of the 8-K) over two years,
    one AI request each, with periods in the company's own fiscal year."""
    releases = sorted([d for d in docs_list if d["kind"] == "earnings_release"], key=lambda d: d["at"], reverse=True)
    n = calls_for(years)
    if len(releases) > n:
        releases = [releases[round(i * (len(releases) - 1) / (n - 1))] for i in range(n)]
    out = {"guidance": [], "problems": [], "read": []}
    pairs = []
    for d in releases:
        try:
            url, text = sec_api.release_doc(d)
        except Exception as e:
            out["problems"].append(unread(f"{d['title'][:48]} {d['at'][:10]}", e))
            continue
        if len(text) >= 400:
            pairs.append(({**d, "url": url}, text))
    if not pairs:
        raise NoCalls(out["problems"] or ["No earnings release was found in the last two years."])
    month = date(2000, fye, 1).strftime("%B")
    failed, last = 0, None
    for d, text in pairs:
        said = date.fromisoformat(d["at"][:10])
        labels, texts = {"S1": {"title": d["title"], "at": d["at"], "url": d["url"], "kind": d["kind"]}}, {"S1": text}
        head = (f"COMPANY: {name} ({symbol}, US). Its fiscal year ends in {month}.\nRELEASE DATE: {d['at'][:10]} (in FY{fy_of(said, fye)})\n\n"
                f"[S1] earnings release: {d['title']}\n{ranked_windows(text, GUIDANCE_WORDS_US, limit=PER_CALL)}")
        try:
            raw = complete(GUIDANCE_US, head, gemini=ai[0], anthropic=ai[1], max_tokens=3000, kind="long")
            try:
                parsed = extract_json(raw)
            except AIError:
                parsed = {"guidance": salvage_items(raw, "guidance")}
            out["guidance"] += clean(parsed, labels, texts, fye)
            out["read"].append({"kind": d["kind"], "at": d["at"], "title": d["title"]})
        except AIError as e:
            failed, last = failed + 1, e
            out["problems"].append(unread(d["title"], e, "the AI couldn't read it this time"))
    if failed == len(pairs):
        raise last
    settle(out, pairs, ai, name, fye)
    out["years"] = years
    return out
