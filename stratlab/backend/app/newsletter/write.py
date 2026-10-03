"""Turning the facts into an issue: the sections, an optional short AI summary, and the email (HTML and text).

The newsletters report facts only, as India's research-analyst rules require of anything that isn't registered
research: no buy, sell or hold, no targets, no picks, no outlook. The AI summary is held to that in code: it may
only restate the facts, and a word filter drops it if it slips, in favour of a plain template."""
import hashlib
import json
import re
from datetime import date, datetime, timedelta
from html import escape

from ..ai_providers import AIError, complete, extract_json
from ..config import settings
from ..intel.net import TTLCache

FOOTER = "Facts from exchange filings, company documents and market data. Not investment advice."
UNSUBSCRIBE = "{unsubscribe_url}"           # the sender fills this in per reader
REGION_NAME = {"IN": "India", "US": "US"}
STAGE_NAME = {1: "Stage 1 (basing)", 2: "Stage 2 (advancing)", 3: "Stage 3 (topping)", 4: "Stage 4 (declining)"}

# words that turn a fact into advice, a forecast or hype; any of them drops the AI text (and a headline)
BANNED = [r"\bbuy", r"\bsell", r"\bhold\b", r"\bholding on\b", r"\baccumulat", r"\btarget", r"\boutperform", r"\bunderperform",
          r"\brecommend", r"\bshould (invest|consider|look)", r"\binvest in\b", r"\bmultibagger", r"\btop picks?\b", r"\bpicks?\b",
          r"\bhot\b", r"\bbullish", r"\bbearish", r"\boutlook", r"\bforecast", r"\bpredict", r"\bexpect", r"\blikely\b",
          r"\bwill (rise|fall|go|climb|drop|rally|gain|continue)", r"\bupside", r"\bdownside", r"\bstop[- ]?loss", r"\bundervalued",
          r"\bovervalued", r"\bopportunit", r"\bguarantee", r"\bmust\b", r"\brally ahead", r"\bbreakout candidate", r"\bsure[- ]shot"]
_BANNED = re.compile("|".join(BANNED), re.I)
ALLOWED_CAPS = {"US", "IN", "IST", "AI", "NSE", "BSE", "ST", "S2", "IPO", "QIP", "GDP", "RBI", "SEBI", "FII", "DII", "ETF"}
_cache = TTLCache(max_items=200)


def banned(text: str) -> bool:
    return bool(_BANNED.search(text or ""))


def origin() -> str:
    return (settings.FRONTEND_ORIGINS or [""])[0].rstrip("/")


def stock_url(region: str, symbol: str) -> str:
    return f"{origin()}/research/{region}/{symbol}"


def _pct(x) -> str:
    return "" if x is None else f"{x:+.2f}%"


def _num(x) -> str:
    return "" if x is None else f"{x:,.2f}"


def _day(iso: str) -> str:
    try:
        return date.fromisoformat(iso[:10]).strftime("%a %d %b")
    except ValueError:
        return iso


# ---------- sections ----------
def _item(text: str, url: str | None = None, lines: list | None = None) -> dict:
    return {"text": text, "url": url, "lines": lines or []}


def market_sections(f: dict) -> list[dict]:
    region, span = f["region"], "over the week" if f["weekly"] else "on the day"
    out = []
    if f.get("indices"):
        out.append({"title": "Indices", "items": [
            _item(f"{i['name']}: {_num(i['price'])}" + (f", {_pct(i['change_pct'])} {span}" if i.get("change_pct") is not None else ""))
            for i in f["indices"]]})
    if f.get("rotation"):
        out.append({"title": "Sector rotation", "items": [
            _item(f"{r['sector']} moved from {r['from'].title()} to {r['to'].title()} on the rotation chart", f"{origin()}/research/rotation")
            for r in f["rotation"]]})
    scan = f.get("scan") or {}
    if scan.get("st_s2") or scan.get("stage2"):
        items = [_item(f"{r['symbol']} matches the Stage 2 rule with the price above its Supertrend (ST S2)", stock_url(region, r["symbol"]))
                 for r in scan.get("st_s2") or []]
        items += [_item(f"{r['symbol']} moved into Stage 2 (matches the Stage 2 rule)", stock_url(region, r["symbol"]))
                  for r in scan.get("stage2") or []]
        out.append({"title": f"New on the Stage 2 scan ({scan['group']})", "items": items})
    heads = [h for h in f.get("headlines") or [] if not banned(h["headline"])]
    if heads:
        out.append({"title": "Headlines", "items": [_item(h["headline"], h.get("url")) for h in heads]})
    return out


def stock_lines(r: dict, since: str) -> list[dict]:
    lines = []
    if r.get("change_pct") is not None:
        lines.append({"text": f"Price {_num(r['price'])}, {_pct(r['change_pct'])} since {_day(since)}", "url": None})
    if r.get("stage_changed"):
        lines.append({"text": f"Now {STAGE_NAME.get(r['stage'], 'Stage ' + str(r['stage']))}, was {STAGE_NAME.get(r['stage_before'], 'Stage ' + str(r['stage_before']))}", "url": None})
    elif r.get("stage"):
        lines.append({"text": f"Still {STAGE_NAME.get(r['stage'], 'Stage ' + str(r['stage']))}", "url": None})
    if r.get("st_s2"):
        lines.append({"text": "Matches the Stage 2 rule with the price above its Supertrend (ST S2)", "url": None})
    for i in r.get("filings") or []:
        lines.append({"text": f"New filing ({'red flag' if i['severity'] == 'red' else 'worth a look'}): {i['label']}. {i['subject']}".strip(), "url": i.get("url")})
    for d in r.get("deals") or []:
        lines.append({"text": f"New disclosure. {d['text']}", "url": d.get("url")})
    for h in r.get("headlines") or []:
        if not banned(h["headline"]):
            lines.append({"text": h["headline"], "url": h.get("url")})
    return lines


def result_item(r: dict) -> dict:
    """One results date, or once filed, the filing and the numbers it states."""
    o = r.get("out")
    if o:
        lines = [{"text": f"{n['label']}: {n['value']} (as stated in the filing)", "url": None} for n in o.get("numbers") or []]
        return _item(f"{r['symbol']}: results filed {_day(str(o.get('at') or r['date']))}. {o.get('title') or ''}".strip(),
                     o.get("url") or stock_url(r["region"], r["symbol"]), lines)
    when = f", {r['when']}" if r.get("when") else ""
    return _item(f"{r['symbol']}: {r['purpose']} on {_day(r['date'])}{when}", stock_url(r["region"], r["symbol"]))


def action_item(r: dict) -> dict:
    """One corporate action: what it is, its ex-date and record date, as announced."""
    rec = f", record date {_day(r['record_date'])}" if r.get("record_date") else ""
    return _item(f"{r['symbol']}: {r['text']}, ex-date {_day(r['ex_date'])}{rec}", stock_url(r["region"], r["symbol"]))


def stock_sections(f: dict) -> list[dict]:
    out = []
    if f.get("stocks"):
        out.append({"title": "What changed for your stocks", "items": [
            _item(r["symbol"], stock_url(r["region"], r["symbol"]), stock_lines(r, f["since"])) for r in f["stocks"]]})
    if f.get("results"):
        out.append({"title": "Results this week", "items": [result_item(r) for r in f["results"]]})
    if f.get("actions"):
        out.append({"title": "Corporate actions", "items": [action_item(r) for r in f["actions"]]})
    if f.get("unchanged"):
        out.append({"title": "No change", "items": [_item(", ".join(f["unchanged"]))]})
    if f.get("paper"):
        cur = lambda p: f" {p['currency']}" if p.get("currency") else ""
        out.append({"title": "Your paper trading", "items": [
            _item(f"{p['name']}: {p['closed']} trade{'s' if p['closed'] != 1 else ''} closed today ({p['pnl']:+,.0f}{cur(p)}), "
                  f"{p['total']:+,.0f}{cur(p)} since start" + (f" ({p['total_pct']:+.1f}%)" if p.get("total_pct") is not None else ""),
                  f"{origin()}/paper") for p in f["paper"]]})
    return out


def sections(f: dict) -> list[dict]:
    return market_sections(f) if f["kind"] == "market" else stock_sections(f)


def subject(f: dict) -> str:
    when = f"week to {date.fromisoformat(f['day']).strftime('%d %b')}" if f["weekly"] else _day(f["day"])
    if f["kind"] == "market":
        lead = next(iter(f.get("indices") or []), None)
        tail = f": {lead['name']} {_pct(lead['change_pct'])}" if lead and lead.get("change_pct") is not None else ""
        return f"Market Brief {REGION_NAME[f['region']]}, {when}{tail}"
    n = len(f.get("stocks") or [])
    k = len({r["symbol"] for r in f.get("results") or []})
    if not n and k:
        return f"My Stocks, {when}: results this week for {k} of your stocks"
    m = len({r["symbol"] for r in f.get("actions") or []})
    if not n and m:
        return f"My Stocks, {when}: ex-dates this week for {m} of your stocks"
    return f"My Stocks, {when}: {n} of your stocks {'has' if n == 1 else 'have'} news"


# ---------- the summary ----------
def template(f: dict) -> str:
    """A few plain sentences straight from the facts: the fallback when the AI can't answer or its text is refused."""
    span = "over the week" if f["weekly"] else "today"
    if f["kind"] == "market":
        parts = []
        moves = [i for i in f.get("indices") or [] if i.get("change_pct") is not None]
        if moves:
            parts.append("; ".join(f"{i['name']} {_pct(i['change_pct'])}" for i in moves) + f" {span}.")
        if f.get("rotation"):
            n = len(f["rotation"])
            parts.append(f"{n} sector{'s' if n != 1 else ''} moved to another quadrant on the rotation chart.")
        scan = f.get("scan") or {}
        if scan.get("st_s2"):
            n = len(scan["st_s2"])
            parts.append(f"{n} stock{'s' if n != 1 else ''} from the {scan['group']} newly matched the ST S2 rule.")
        return " ".join(parts) or f"Here is the {REGION_NAME[f['region']]} market {span}."
    n = len(f.get("stocks") or [])
    flags = sum(len(r.get("filings") or []) for r in f.get("stocks") or [])
    parts = [f"{n} of your stocks had something new {span}."] if n or not (f.get("results") or f.get("actions")) else []
    if flags:
        parts.append(f"{flags} new filing{'s' if flags != 1 else ''} to look at.")
    trades = sum(len(r.get("deals") or []) for r in f.get("stocks") or [])
    if trades:
        parts.append(f"{trades} new deal{'s' if trades != 1 else ''} or insider trade{'s' if trades != 1 else ''} disclosed.")
    due = len({r["symbol"] for r in f.get("results") or [] if not r.get("out")})
    filed = len({r["symbol"] for r in f.get("results") or [] if r.get("out")})
    if due:
        parts.append(f"{due} of your stocks {'has' if due == 1 else 'have'} a results date this week.")
    if filed:
        parts.append(f"{filed} filed {'its' if filed == 1 else 'their'} results.")
    ex = len({r["symbol"] for r in f.get("actions") or []})
    if ex:
        parts.append(f"{ex} of your stocks {'has' if ex == 1 else 'have'} an ex-date this week (a dividend, bonus, split or other corporate action).")
    return " ".join(parts)


def grounded(text: str, f: dict) -> bool:
    """Every ticker-like word in the text is in the facts, and no advice, forecast or hype words."""
    if not text or banned(text):
        return False
    hay = json.dumps(f, ensure_ascii=False, default=str).upper()
    for word in re.findall(r"\b[A-Z][A-Z0-9&\-]{1,14}\b", text):
        if word not in ALLOWED_CAPS and word not in hay:
            return False
    return True


SYSTEM = """You write the two-to-three sentence summary at the top of a market newsletter for retail readers.
Use ONLY the FACTS given. Restate what happened; never say what to do or what may happen next.
Never: buy, sell, hold or accumulate; targets or price levels to watch; picks, "hot" names or favourites; outlook,
forecasts, expectations or predictions; any company or ticker that is not in the facts; numbers not in the facts.
Plain English, no markdown, no emojis. Reply with ONLY this JSON: {"summary": "..."}"""


def ai_summary(f: dict) -> str | None:
    from ..ai_writer import _anthropic, _gemini
    facts = {k: v for k, v in f.items() if k not in ("uid",)}
    try:
        raw = complete(SYSTEM, "FACTS:\n" + json.dumps(facts, ensure_ascii=False, default=str), gemini=_gemini,
                       anthropic=_anthropic, max_tokens=500, kind="research")
        text = str(extract_json(raw).get("summary") or "").strip()
    except (AIError, ValueError, AttributeError, TypeError):
        return None
    text = re.sub(r"\s+", " ", text)[:700]
    return text if grounded(text, f) else None


def summary(f: dict) -> dict:
    """{"text", "ai"}: the AI's summary when it passes the checks, else the template. The Market Brief's is made once
    per region and day and shared by every reader; My Stocks uses the template, never a per-reader AI call."""
    if f["kind"] != "market":
        return {"text": template(f), "ai": False}
    # the facts are part of the key, so a preview built before the close never stands in for the real issue
    key = (f["kind"], f["region"], f["day"], f["weekly"], hashlib.sha1(json.dumps(f, sort_keys=True, default=str).encode(),
                                                                          usedforsecurity=False).hexdigest())
    hit = _cache.get(key)
    if hit is not None:
        return hit
    text = ai_summary(f)
    out = {"text": text, "ai": True} if text else {"text": template(f), "ai": False}
    _cache.set(key, out, 24 * 3600)
    return out


# ---------- the email ----------
def _a(url: str | None, text: str) -> str:
    """A link, or plain text when the url isn't a web address (a feed's javascript: or data: link never gets in)."""
    t = escape(text)
    ok = isinstance(url, str) and url.lower().startswith(("https://", "http://"))
    return f'<a href="{escape(url)}" style="color:#1a56db;text-decoration:none">{t}</a>' if ok else t


link = _a            # for the other emails built in this style (app/lifecycle.py)


def frame(title: str, body: list[str], footer: str) -> str:
    """An email around its body: inline styles only, no images or web fonts, one column that fits a phone. `body` and
    `footer` are HTML, already escaped."""
    return ('<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f"<title>{escape(title)}</title></head>"
            '<body style="margin:0;padding:0;background:#f4f5f7">'
            '<div style="max-width:600px;margin:0 auto;padding:16px;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;'
            'color:#1f2328;font-size:15px;line-height:1.5">'
            '<div style="background:#ffffff;border-radius:8px;padding:20px">'
            '<div style="font-size:12px;color:#6b7280;letter-spacing:.04em;text-transform:uppercase">StratLab</div>'
            f'<h1 style="font-size:20px;line-height:1.3;margin:4px 0 12px">{escape(title)}</h1>'
            + "".join(body) + "</div>"
            f'<p style="font-size:12px;color:#6b7280;margin:16px 4px">{footer}</p>'
            "</div></body></html>")


def as_of(iso: str | None) -> str | None:
    """When an issue's numbers were gathered, in words: "3 Oct 2026, 16:15 IST"."""
    try:
        d = datetime.fromisoformat(str(iso))
    except (TypeError, ValueError):
        return None
    zone = "IST" if d.utcoffset() == timedelta(hours=5, minutes=30) else "UTC" if d.utcoffset() == timedelta(0) else ""
    return f"{d.day} {d:%b %Y}, {d:%H:%M}" + (f" {zone}" if zone else "")


def render(issue: dict) -> tuple[str, str]:
    """(html, text) for one issue. The footer carries the {unsubscribe_url} placeholder for the sender."""
    view = f"{origin()}/news/{issue['id']}" if issue.get("id") else None
    html = []
    text = [issue["subject"], ""]
    if issue.get("summary"):
        html.append(f'<p style="margin:0 0 16px">{escape(issue["summary"])}</p>')
        text += [issue["summary"], ""]
    when = as_of(issue.get("at"))
    if when:
        html.append(f'<p style="margin:0 0 12px;font-size:13px;color:#6b7280">Prices and numbers as of {escape(when)}</p>')
        text += [f"Prices and numbers as of {when}", ""]
    for sec in issue.get("sections") or []:
        html.append(f'<h2 style="font-size:16px;margin:20px 0 8px;padding-top:12px;border-top:1px solid #e5e7eb">{escape(sec["title"])}</h2>'
                    '<ul style="margin:0;padding-left:18px">')
        text.append(sec["title"].upper())
        for it in sec["items"]:
            sub = "".join(f'<li style="margin:2px 0;color:#374151">{_a(ln.get("url"), ln["text"])}</li>' for ln in it.get("lines") or [])
            html.append(f'<li style="margin:6px 0">{_a(it.get("url"), it["text"])}'
                        + (f'<ul style="margin:4px 0 0;padding-left:16px;font-size:14px">{sub}</ul>' if sub else "") + "</li>")
            text.append(f"- {it['text']}" + (f" ({it['url']})" if it.get("url") else ""))
            text += [f"    {ln['text']}" + (f" ({ln['url']})" if ln.get("url") else "") for ln in it.get("lines") or []]
        html.append("</ul>")
        text.append("")
    if view:
        html.append(f'<p style="margin:20px 0 0">{_a(view, "Read this in StratLab")}</p>')
        text += [f"Read this in StratLab: {view}", ""]
    footer = f'{escape(FOOTER)}<br><a href="{UNSUBSCRIBE}" style="color:#6b7280">Unsubscribe or change how often</a>'
    text += [FOOTER, f"Unsubscribe or change how often: {UNSUBSCRIBE}"]
    return frame(issue["subject"], html, footer), "\n".join(text)
