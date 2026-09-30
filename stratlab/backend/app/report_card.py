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
from .ai_providers import complete, extract_json
from .deepdive import KEEP, RULES, _excerpts

MAX_CALLS = 6                  # earnings calls read, spread over the last two years

GUIDANCE = """You pull out the targets an Indian listed company's management gave on its earnings calls: what they said a
number WOULD be for a future year or quarter. Examples: "revenue growth of 15-18% in FY26", "EBITDA margin of about 20%
next year", "capex of Rs 1,500 crore in FY25".
Return {"guidance": [{"metric": "revenue_growth | profit_growth | margin | capex | other",
  "low": number or null, "high": number or null, "unit": "% | crore",
  "period": "FY26 or Q2 FY26 (Indian financial year ending in March)", "what": "the target in one short line",
  "quote": "short exact quote", "source": "S1"}]}
- Only forward-looking targets for a period that had NOT ended when it was said. Not past results.
- "margin" is an EBITDA or operating margin in %. Growth is year-on-year in %. Capex is in Rs crore.
- A single figure goes in "low" with "high" null; "about 20%" is low 20. A range fills both.
- Qualitative promises (a launch, a plant start, debt reduction) use metric "other" with low and high null.
- Up to 15 items. "source" is the label of the excerpt it came from.
""" + RULES

GUIDANCE_WORDS = [r"guidance", r"we expect", r"we are targeting", r"target", r"going forward", r"next year", r"this year",
                  r"FY ?'?\d\d", r"outlook", r"margin", r"growth of", r"capex", r"crore", r"double[- ]digit", r"aspir"]

METRICS = {"revenue_growth": "Revenue growth", "profit_growth": "Profit growth", "margin": "Operating margin",
           "capex": "Capex", "other": "Other promise"}
TOLERANCE = {"revenue_growth": 1.0, "profit_growth": 2.0, "margin": 0.5}      # percentage points; capex uses 10%
Q_END = {1: (6, 30), 2: (9, 30), 3: (12, 31), 4: (3, 31)}
Q_LABEL = {1: "Jun", 2: "Sep", 3: "Dec", 4: "Mar"}


# ---------- periods ----------
def _fy(s: str) -> int | None:
    n = int(s)
    return 2000 + n if n < 100 else n if 2000 <= n <= 2100 else None


def parse_period(text: str | None) -> dict | None:
    """'FY26', 'FY2025-26', 'Q2 FY26', '2QFY26', 'Q2FY2026' → {"kind": "FY"|"Q", "fy": 2026, "q": 2}."""
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


def period_end(p: dict) -> date:
    if p["kind"] == "FY":
        return date(p["fy"], 3, 31)
    mo, d = Q_END[p["q"]]
    return date(p["fy"] if p["q"] == 4 else p["fy"] - 1, mo, d)


def period_label(p: dict) -> str:
    return f"FY{p['fy'] % 100:02d}" if p["kind"] == "FY" else f"Q{p['q']} FY{p['fy'] % 100:02d}"


def _table_label(p: dict) -> str:
    """The column label the fundamentals tables use: 'Mar 2026', 'Sep 2025'."""
    if p["kind"] == "FY":
        return f"Mar {p['fy']}"
    return f"{Q_LABEL[p['q']]} {p['fy'] if p['q'] == 4 else p['fy'] - 1}"


# ---------- the AI read ----------
def _f(v):
    try:
        f = float(str(v).replace(",", ""))
        return f if abs(f) < 1e7 else None
    except (TypeError, ValueError):
        return None


def clean(d: dict, labels: dict) -> list[dict]:
    out = []
    for g in (d.get("guidance") or [])[:15]:
        if not isinstance(g, dict):
            continue
        src = labels.get(str(g.get("source") or "").strip().upper())
        per = parse_period(g.get("period"))
        what = str(g.get("what") or "").strip()
        if not src or not what:
            continue                                    # every promise must come from a call we read
        metric = str(g.get("metric") or "other").lower().replace(" ", "_")
        metric = metric if metric in METRICS else "other"
        low, high = _f(g.get("low")), _f(g.get("high"))
        if low is None and high is not None:
            low, high = high, None
        if low is not None and high is not None and high < low:
            low, high = high, low
        if metric != "other" and low is None:
            metric = "other"
        if per and period_end(per) <= date.fromisoformat(src["at"][:10]):
            continue                                    # said after the period ended: a result, not a promise
        out.append({"metric": metric, "low": low, "high": high, "period": period_label(per) if per else None,
                    "what": what[:200], "quote": str(g.get("quote") or "")[:300], "said_at": src["at"],
                    "source": {"title": src["title"], "at": src["at"], "url": src["url"]}})
    return out


def pick_calls(docs_list: list[dict], n: int = MAX_CALLS) -> list[dict]:
    """Up to n call transcripts spread over the two years, so older promises (now checkable) are included."""
    calls = sorted([d for d in docs_list if d["kind"] == "transcript"], key=lambda d: d["at"], reverse=True)
    if len(calls) <= n:
        return calls
    return [calls[round(i * (len(calls) - 1) / (n - 1))] for i in range(n)]


def read(symbol: str, name: str, docs_list: list[dict], docs_api, ai) -> dict:
    calls = pick_calls(docs_list)
    out = {"guidance": [], "problems": [], "read": [{"kind": d["kind"], "at": d["at"], "title": d["title"]} for d in calls]}
    text, labels, probs = _excerpts(docs_api, calls, GUIDANCE_WORDS, 5000)
    out["problems"] = probs
    if text:
        head = f"COMPANY: {name} ({symbol}, NSE)\nEach excerpt shows the date of the call.\n\nEXCERPTS:\n"
        raw = complete(GUIDANCE, head + text, gemini=ai[0], anthropic=ai[1], max_tokens=2500, kind="long")
        out["guidance"] = clean(extract_json(raw), labels)
    return out


# ---------- checking against the numbers ----------
def _actual(metric: str, per: dict, nums: dict) -> float | None:
    label = _table_label(per)
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
    today = today or date.today()
    per = parse_period(g.get("period"))
    res = {**g, "actual": None, "result": "unchecked", "unit": "crore" if g["metric"] == "capex" else "%"}
    if g["metric"] == "other" or not per:
        return res
    a = _actual(g["metric"], per, nums)
    if a is None:
        # quarterly results come out within ~45 days of the quarter, annual ones within ~60
        res["result"] = "pending" if (today - period_end(per)).days < 75 else "unchecked"
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
            "problems": stored_card.get("problems") or [], "at": stored_card.get("at")}


# ---------- stored reads ----------
def _key(symbol: str) -> str:
    return f"deep:card:v1:{symbol}"


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
