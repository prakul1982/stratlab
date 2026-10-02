"""Company deep dive (India): growth, margins and capex from the reported numbers, and the business model and capex
plans read from the company's own investor presentations and earnings-call transcripts.

The numbers are arithmetic on reported figures. The document reads quote the company; nothing here is an opinion on
whether to buy. Reads are stored in the database and shared, so a company costs one AI read a week."""
import json
import re
import time
from datetime import datetime, timezone

from . import db
from .ai_providers import complete, extract_json
from .docs import windows

KEEP = 7 * 86400              # a document read is reused for a week
DOC_DAYS = 730                # filings searched for documents: two years


# ---------- numbers ----------
def _series(table: dict | None, *prefixes: str) -> list:
    if not table:
        return []
    for label, vals in table["rows"].items():
        if any(label.lower().startswith(p.lower()) for p in prefixes):
            return list(vals)
    return []


def _years(table: dict | None) -> list[str]:
    return [c for c in (table or {}).get("cols", [])]


def _cagr(vals: list, years: int) -> float | None:
    v = [x for x in vals if x is not None]
    if len(v) <= years or v[-1 - years] is None or v[-1 - years] <= 0 or v[-1] is None or v[-1] <= 0:
        return None
    return ((v[-1] / v[-1 - years]) ** (1 / years) - 1) * 100


def _align(cols_a: list[str], vals_a: list, cols_b: list[str]) -> list:
    """Values of series A at the columns of table B (None where A has no such year)."""
    m = dict(zip(cols_a, vals_a))
    return [m.get(c) for c in cols_b]


def numbers(p: dict) -> dict:
    """Growth, margins, estimated capex and free cash flow from the reported annual and quarterly tables."""
    pl, bal, cf, q = p.get("pl"), p.get("balance"), p.get("cashflow"), p.get("quarters")
    # banks and lenders report "Financing Profit / Margin"; capex, free cash flow and operating margin don't apply
    bank = any(k.lower().startswith("financing") for k in ((pl or {}).get("rows") or {}))
    ycols = [c for c in _years(pl) if c.upper() != "TTM"]
    n = len(ycols)
    sales = _series(pl, "Sales", "Revenue")[:n]
    profit = _series(pl, "Net Profit")[:n]
    opm = _series(pl, "OPM", "Financing Margin")[:n]
    dep = _series(pl, "Depreciation")[:n]
    bcols = _years(bal)
    fa = _align(bcols, _series(bal, "Fixed Assets", "Net Block"), ycols)
    cwip = _align(bcols, _series(bal, "CWIP", "Capital Work"), ycols)
    debt = _align(bcols, _series(bal, "Borrowings"), ycols)
    ccols = _years(cf)
    cfo = _align(ccols, _series(cf, "Cash from Operating"), ycols)
    cfi = _align(ccols, _series(cf, "Cash from Investing"), ycols)

    years = []
    for i, y in enumerate(ycols):
        capex = None          # estimated: growth in fixed assets and work in progress, plus the year's depreciation
        if not bank and i > 0 and fa[i] is not None and fa[i - 1] is not None:
            d_cwip = cwip[i] - cwip[i - 1] if cwip[i] is not None and cwip[i - 1] is not None else 0
            d_dep = dep[i] if i < len(dep) and dep[i] is not None else 0
            capex = (fa[i] - fa[i - 1]) + d_cwip + d_dep
            if capex < 0:     # assets sold, written down or reclassified that year: the estimate means nothing
                capex = None
        s = sales[i] if i < len(sales) else None
        c = cfo[i] if cfo else None
        years.append({"year": y, "sales": s, "profit": profit[i] if i < len(profit) else None, "opm": opm[i] if i < len(opm) else None,
                      "capex": round(capex, 1) if capex is not None else None,
                      "capex_pct_sales": round(capex / s * 100, 1) if capex is not None and s else None,
                      "cfo": c, "cfi": cfi[i] if cfi else None,
                      "fcf": round(c - capex, 1) if c is not None and capex is not None else None,
                      "debt": debt[i] if debt else None})
    qcols = _years(q)
    qs, qp, qo = _series(q, "Sales", "Revenue"), _series(q, "Net Profit"), _series(q, "OPM", "Financing Margin")
    quarters = []
    for i, c in enumerate(qcols):
        yoy = (qs[i] / qs[i - 4] - 1) * 100 if i >= 4 and i < len(qs) and qs[i] and qs[i - 4] else None
        quarters.append({"quarter": c, "sales": qs[i] if i < len(qs) else None, "profit": qp[i] if i < len(qp) else None,
                         "opm": qo[i] if i < len(qo) else None, "sales_yoy": round(yoy, 1) if yoy is not None else None})
    recent_capex = [y["capex"] for y in years[-3:] if y["capex"] is not None]
    return {
        "years": years[-10:], "quarters": quarters[-12:],
        "growth": {"sales_cagr_3y": _cagr(sales, 3), "sales_cagr_5y": _cagr(sales, 5),
                   "profit_cagr_3y": _cagr(profit, 3), "profit_cagr_5y": _cagr(profit, 5)},
        "capex_3y_total": round(sum(recent_capex), 1) if recent_capex else None,
        "unit": "₹ crore", "bank": bank,
    }


# ---------- which documents to read ----------
def documents(items: list[dict]) -> list[dict]:
    """Investor presentations and earnings-call transcripts among a company's filings, newest first, with a PDF link."""
    out = []
    for i in items:
        if not i.get("url"):
            continue
        hay = f"{i.get('subject', '')} {i.get('text', '')}".lower()
        if "transcript" in hay:
            kind = "transcript"
        elif i.get("category") == "presentation" or "investor presentation" in hay or "earnings presentation" in hay:
            kind = "presentation"
        elif "annual report" in hay:
            kind = "annual_report"
        else:
            continue
        out.append({"kind": kind, "at": i["at"], "title": i.get("subject") or kind, "url": i["url"]})
    return out


# ---------- the document reads ----------
RULES = """Rules:
- Use ONLY the company's own words in the EXCERPTS. If something isn't there, leave it out; never guess figures.
- Facts and the company's statements only: no opinion on the stock, no advice, no "buy" or "sell".
- Plain English a retail investor understands. No markdown.
- Reply with ONLY one JSON object in exactly the shape asked for."""

BUSINESS = """You explain how an Indian listed company makes money, from its own investor presentation and filings.
Return {"summary": "2-3 sentences: what it sells, to whom, and how it earns",
 "segments": [{"name": "...", "share_pct": number or null, "what": "one line"}],
 "customers": "who buys, in one line", "drivers": ["what moves revenue", ...],
 "strengths": ["advantages the company itself points to", ...], "risks": ["risks the company names", ...],
 "measures": [{"name": "the operating measure", "value": "as stated, with its unit", "period": "e.g. Q1 FY27", "change": "vs a year
  earlier if stated, else null", "quote": "short exact quote", "source": "S1"}]}
At most 6 segments and 5 items per list. For "measures", look for the INDUSTRY MEASURES listed with the company (the numbers
this industry is judged on, such as revenue per occupied bed for a hospital); include only those the excerpts state, up to 8.
""" + RULES

PLANS = """You pull out capacity, capex and growth plans an Indian listed company's management stated, from its investor
presentation and earnings-call transcripts.
Return {"capex": [{"what": "the project or expansion", "amount": "as stated, e.g. Rs 1,200 crore, or null",
  "timeline": "as stated or null", "status": "planned | under way | done | unclear", "quote": "short exact quote", "source": "S1"}],
 "outlook": [{"statement": "a growth, margin or demand statement, in one line", "quote": "short exact quote", "source": "S2"}]}
Up to 8 capex items and 6 outlook items. "source" is the label of the excerpt it came from.
""" + RULES

BUSINESS_WORDS = [r"business overview", r"segment", r"revenue mix", r"products?", r"customers?", r"market share",
                  r"we are", r"company overview", r"about us", r"leading"]
PLAN_WORDS = [r"capex", r"capital expenditure", r"capacity", r"expansion", r"greenfield", r"brownfield", r"new plant",
              r"commission", r"guidance", r"outlook", r"we expect", r"target", r"margin", r"growth of", r"crore"]


def _clip(x, n: int, length: int = 300) -> list:
    return [str(i)[:length] for i in (x or []) if str(i).strip()][:n] if isinstance(x, list) else []


def _num(v):
    try:
        f = float(v)
        return f if 0 <= f <= 100 else None
    except (TypeError, ValueError):
        return None


def clean_measures(d: dict, labels: dict) -> list[dict]:
    out = []
    for m in (d.get("measures") or [])[:8]:
        if isinstance(m, dict) and str(m.get("name") or "").strip() and str(m.get("value") or "").strip():
            out.append({"name": str(m["name"])[:80], "value": str(m["value"])[:60], "period": (str(m["period"])[:30] if m.get("period") else None),
                        "change": (str(m["change"])[:60] if m.get("change") else None), "quote": str(m.get("quote") or "")[:240],
                        "source": labels.get(str(m.get("source") or "").strip().upper())})
    return out


def clean_business(d: dict) -> dict:
    segs = []
    for s in (d.get("segments") or [])[:6]:
        if isinstance(s, dict) and str(s.get("name") or "").strip():
            segs.append({"name": str(s["name"])[:80], "share_pct": _num(s.get("share_pct")), "what": str(s.get("what") or "")[:200]})
    return {"summary": str(d.get("summary") or "")[:700], "segments": segs, "customers": str(d.get("customers") or "")[:300],
            "drivers": _clip(d.get("drivers"), 5), "strengths": _clip(d.get("strengths"), 5), "risks": _clip(d.get("risks"), 5)}


def clean_plans(d: dict, labels: dict) -> dict:
    def src(v):
        return labels.get(str(v or "").strip().upper())
    capex = []
    for c in (d.get("capex") or [])[:8]:
        if isinstance(c, dict) and str(c.get("what") or "").strip():
            status = str(c.get("status") or "unclear").lower()
            capex.append({"what": str(c["what"])[:200], "amount": (str(c["amount"])[:80] if c.get("amount") else None),
                          "timeline": (str(c["timeline"])[:80] if c.get("timeline") else None),
                          "status": status if status in ("planned", "under way", "done", "unclear") else "unclear",
                          "quote": str(c.get("quote") or "")[:300], "source": src(c.get("source"))})
    outlook = []
    for o in (d.get("outlook") or [])[:6]:
        if isinstance(o, dict) and str(o.get("statement") or "").strip():
            outlook.append({"statement": str(o["statement"])[:240], "quote": str(o.get("quote") or "")[:300], "source": src(o.get("source"))})
    return {"capex": capex, "outlook": outlook}


MIN_CHARS = 2500              # less than this is a cover letter or an intimation, not the document itself
MAX_TRIES = 8                 # documents downloaded at most per read, looking for real ones


def readable(docs_api, candidates: list[dict], need: int, problems: list[str]) -> list[tuple[dict, str]]:
    """The first `need` candidates whose PDF holds real text. Exchange filings often attach only a one-page cover
    letter under a "presentation" or "transcript" subject; those are skipped and the next candidate is tried."""
    out, short = [], 0
    for d in candidates[:max(MAX_TRIES, need * 2)]:
        if len(out) >= need:
            break
        try:
            text = docs_api.text(d["url"])
        except Exception as e:
            problems.append(f"{d['title'][:60]}: {str(e)[:80]}")
            continue
        if len(text) < MIN_CHARS:
            short += 1
            continue
        out.append((d, text))
    if short and len(out) < need:
        problems.append(f"{short} filing{'s' if short > 1 else ''} held only a short cover letter, not the document itself")
    return out


def _excerpts(pairs: list[tuple[dict, str]], words: list[str], per_doc: int, start: int = 1) -> tuple[str, dict]:
    """Labelled excerpts S1, S2… for the AI, and the label → document map."""
    parts, labels = [], {}
    for n, (d, text) in enumerate(pairs, start):
        label = f"S{n}"
        labels[label] = {"title": d["title"], "at": d["at"], "url": d["url"], "kind": d["kind"]}
        parts.append(f"[{label}] {d['kind']} filed {d['at'][:10]}: {d['title']}\n{windows(text, words, limit=per_doc)}")
    return "\n\n".join(parts), labels


def read(symbol: str, name: str, about: str, docs_list: list[dict], docs_api, ai, kpis: dict | None = None) -> dict:
    """Both document reads for one company. `ai` is (gemini, anthropic) for the provider chain."""
    out = {"business": None, "plans": None, "problems": [], "read": []}
    pres = readable(docs_api, [d for d in docs_list if d["kind"] == "presentation"], 1, out["problems"])
    trans = readable(docs_api, [d for d in docs_list if d["kind"] == "transcript"], 2, out["problems"])
    kpis = kpis or {}
    want = kpis.get("measures") or []
    head = (f"COMPANY: {name} ({symbol}, NSE)\nPROFILE: {about[:1200]}\n"
            f"INDUSTRY MEASURES ({kpis.get('label') or 'this company'}): {'; '.join(want)}\n\nEXCERPTS:\n")
    words = BUSINESS_WORDS + [re.escape(w.split(" (")[0]) for w in want if not w.startswith("The operating")]
    text, labels = _excerpts(pres, words, 14000)
    if want and trans:     # calls often state the operating measures the deck leaves out
        mtext, mlabels = _excerpts(trans, [re.escape(w.split(" (")[0]) for w in want if not w.startswith("The operating")] or [r"\d"],
                                   4000, start=len(labels) + 1)
        text, labels = (text + "\n\n" + mtext).strip(), {**labels, **mlabels}
    if text or about:
        raw = complete(BUSINESS, head + (text or "(no presentation available)"), gemini=ai[0], anthropic=ai[1], max_tokens=1500, kind="long")
        parsed = extract_json(raw)
        out["business"] = clean_business(parsed)
        out["business"]["measures"] = clean_measures(parsed, labels)
        out["business"]["industry"] = kpis.get("label")
        out["business"]["sources"] = list(labels.values())
    text, labels = _excerpts(pres + trans, PLAN_WORDS, 9000)
    if text:
        raw = complete(PLANS, head + text, gemini=ai[0], anthropic=ai[1], max_tokens=2000, kind="long")
        out["plans"] = clean_plans(extract_json(raw), labels)
        out["plans"]["sources"] = list(labels.values())
    out["read"] = [{"kind": d["kind"], "at": d["at"], "title": d["title"]} for d, _ in pres + trans]
    return out


# ---------- stored reads ----------
def _key(symbol: str) -> str:
    return f"deep:v1:{symbol}"


def stored(symbol: str) -> dict | None:
    try:
        v = json.loads(db.get_setting(_key(symbol)) or "null")
    except (ValueError, TypeError):
        return None
    return v if isinstance(v, dict) and v.get("at") else None


def store(symbol: str, reads: dict) -> dict:
    v = {**reads, "at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "ts": time.time()}
    db.set_setting(_key(symbol), json.dumps(v, ensure_ascii=False))
    return v


def fresh(v: dict | None) -> bool:
    return bool(v) and time.time() - float(v.get("ts") or 0) < KEEP


def safe_symbol(s: str) -> str:
    return re.sub(r"[^A-Z0-9&\-]", "", s.upper())[:20]
