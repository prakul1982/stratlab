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
from .deepdive import KEEP, RULES, readable
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
Return {"guidance": [{"metric": "revenue_growth | profit_growth | margin | capex | other",
  "low": number or null, "high": number or null, "unit": "% | crore",
  "period": "FY26 or Q2 FY26 (Indian financial year ending in March)", "what": "the target in one short line",
  "quote": "short exact quote", "source": "S1"}]}
- Only what MANAGEMENT (the CEO, CFO, MD or other company executives) said. Never an analyst's question, an analyst's
  estimate, or the moderator. If an analyst suggests a number and management only agrees vaguely, leave it out.
- Only forward-looking targets for a period that had NOT ended when it was said. Not past results.
- The call date is given. Turn "this year", "current year", "this fiscal" into that Indian financial year (April to March)
  and "next year" into the one after. Example: a call on 2025-08-10 is in FY26, so "next year" is FY27. If the period
  can't be pinned down, use null.
- "margin" is an EBITDA or operating margin in %. Growth is year-on-year in %. Capex is in Rs crore.
- A single figure goes in "low" with "high" null; "about 20%" is low 20. A range fills both.
- Qualitative promises (a launch, a plant start, debt reduction) use metric "other" with low and high null.
- "quote" must be copied word for word from the excerpt, 6 to 25 words. Don't paraphrase it.
- Up to 12 items. "source" is the label of the excerpt it came from.
""" + RULES

GUIDANCE_WORDS = [r"guidance", r"we expect", r"we are targeting", r"target", r"going forward", r"next year", r"this year",
                  r"FY ?'?\d\d", r"outlook", r"margin", r"growth of", r"capex", r"crore", r"double[- ]digit", r"aspir"]

METRICS = {"revenue_growth": "Revenue growth", "profit_growth": "Profit growth", "margin": "Operating margin",
           "capex": "Capex", "other": "Other promise"}
TOLERANCE = {"revenue_growth": 1.0, "profit_growth": 2.0, "margin": 0.5}      # percentage points; capex uses 10%


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


def clean(d: dict, labels: dict, texts: dict | None = None, fye: int = 3) -> list[dict]:
    """`texts` (label → full text) checks each quote really is in the call it's credited to."""
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
        out.append({"metric": metric, "low": low, "high": high, "period": period_label(per) if per else None,
                    "what": what[:200], "quote": str(g.get("quote") or "")[:300], "said_at": src["at"],
                    "source": {"title": src["title"], "at": src["at"], "url": src["url"]}})
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
    return clean(parsed, labels, texts)


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
            out["problems"].append(f"{d['title'][:60]}: {str(e)[:80]}")
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
        tgt = f"{g['low']}" + (f" to {g['high']}" if g.get("high") is not None else "") + (" %" if g.get("unit") == "%" else f" {g.get('unit') or ''}")
        lines.append(f"{tid}: {g['what']} | target {tgt} | period {g['period']} (ended {end.isoformat()})")
    try:
        raw = complete(SETTLE, f"COMPANY: {name}\n\nTARGETS:\n" + "\n".join(lines) + "\n\nEXCERPTS:\n" + "\n\n".join(parts),
                       gemini=ai[0], anthropic=ai[1], max_tokens=2500, kind="long")
        try:
            got = extract_json(raw).get("results") or []
        except AIError:
            got = salvage_items(raw, "results")
    except AIError as e:
        out["problems"].append(f"Checking targets against later documents: {str(e)[:80]}")
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
def _actual(metric: str, per: dict, nums: dict) -> float | None:
    label = _table_label(per, nums.get("fye") or 3)
    if per["kind"] == "FY":
        rows = nums.get("years") or []
        idx = next((i for i, r in enumerate(rows) if r["year"] == label), None)
        if idx is None:
            return None
        r = rows[idx]
        if metric == "margin":
            return r.get("opm")
        if metric == "capex":
            return r.get("capex")
        key = "sales" if metric == "revenue_growth" else "profit"
        prev = rows[idx - 1].get(key) if idx > 0 else None
        return (r[key] / prev - 1) * 100 if r.get(key) is not None and prev and prev > 0 else None
    rows = nums.get("quarters") or []
    idx = next((i for i, r in enumerate(rows) if r["quarter"] == label), None)
    if idx is None or metric == "capex":
        return None
    r = rows[idx]
    if metric == "margin":
        return r.get("opm")
    key = "sales" if metric == "revenue_growth" else "profit"
    prev = rows[idx - 4].get(key) if idx >= 4 else None
    return (r[key] / prev - 1) * 100 if r.get(key) is not None and prev and prev > 0 else None


def check(g: dict, nums: dict, today: date | None = None) -> dict:
    """One promise against the numbers: met, missed, pending (not reported yet) or unchecked (not a number we have)."""
    today = today or ist_date()
    per = parse_period(g.get("period"))
    us = (nums.get("unit") or "").startswith("$")
    res = {**g, "actual": None, "result": "unchecked", "unit": ("million" if us else "crore") if g["metric"] == "capex" else "%"}
    dc = g.get("doc_check")

    def from_documents(r):            # the company's own later statement of the result, quote checked
        return {**r, "actual": dc["actual"], "result": "met" if dc["met"] else "missed", "settled_by": dc} if dc else r
    if g["metric"] == "other" or not per:
        return from_documents(res)
    if nums.get("bank") and g["metric"] in ("margin", "capex"):
        return from_documents(res)      # a lender's margin (NIM) and capex aren't in the reported tables
    a = _actual(g["metric"], per, nums)
    if a is None and dc:
        return from_documents(res)
    if a is None:
        # quarterly results come out within ~45 days of the quarter, annual ones within ~60
        res["result"] = "pending" if (today - period_end(per, nums.get("fye") or 3)).days < 75 else "unchecked"
        return res
    res["actual"] = round(a, 1)
    target = g["low"]
    if g["metric"] == "capex":
        ok = a >= target * 0.9
    else:
        ok = a >= target - TOLERANCE[g["metric"]]
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
    rows = [check(g, nums, today) for g in _dedupe(stored_card.get("guidance") or [])]
    met = sum(r["result"] == "met" for r in rows)
    missed = sum(r["result"] == "missed" for r in rows)
    checked = met + missed
    return {"rows": rows, "met": met, "missed": missed, "pending": sum(r["result"] == "pending" for r in rows),
            "unchecked": sum(r["result"] == "unchecked" for r in rows),
            "score": round(met / checked * 100) if checked else None, "read": stored_card.get("read") or [],
            "problems": stored_card.get("problems") or [], "at": stored_card.get("at"), "years": stored_card.get("years") or 2}


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


def fresh(v: dict | None) -> bool:
    return bool(v) and time.time() - float(v.get("ts") or 0) < KEEP


# ---------- US companies: guidance in earnings releases ----------
GUIDANCE_US = """You pull out the targets a US listed company's management gave in its earnings press releases: what they
said a number WOULD be for a future quarter or fiscal year. Examples: "revenue growth in the low double digits for
fiscal 2026", "operating margin of 30% to 31% in the fourth quarter", "capital expenditures of about $14 billion".
Return {"guidance": [{"metric": "revenue_growth | profit_growth | margin | capex | other",
  "low": number or null, "high": number or null, "unit": "% | million",
  "period": "FY2026 or Q3 FY2026 (the company's own fiscal year)", "what": "the target in one short line",
  "quote": "short exact quote", "source": "S1"}]}
- Only forward-looking targets for a period that had NOT ended when the release was published. Not past results.
- The company's fiscal year end and the release date are given. Turn "the fourth quarter", "next quarter", "the full
  year" and "fiscal 2026" into Qn FYyyyy or FYyyyy in the COMPANY'S fiscal year (named by the calendar year it ends in).
- "margin" is an operating or gross margin in %. Growth is year-on-year in %. Capex is in $ million ($1.2 billion is 1200).
- Revenue given as a dollar range (e.g. "$94 billion to $97 billion") is not a growth rate: use metric "other".
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
            out["problems"].append(f"{d['title'][:60]} {d['at'][:10]}: {str(e)[:80]}")
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
            out["problems"].append(f"{d['title'][:60]}: {str(e)[:80]}")
    if failed == len(pairs):
        raise last
    settle(out, pairs, ai, name, fye)
    out["years"] = years
    return out
