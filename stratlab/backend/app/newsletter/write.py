"""Turning the facts into an issue: the sections, an optional short AI summary, and the email (HTML and text).

The newsletters report facts only, as India's research-analyst rules require of anything that isn't registered
research: no buy, sell or hold, no targets, no picks, no outlook. The AI summary is held to that in code: it may
only restate the facts, and a word filter drops it if it slips, in favour of a plain template."""
import hashlib
import json
import re
from datetime import datetime, timedelta

from .. import email_kit as kit
from ..ai_providers import AIError, complete, extract_json
from ..config import settings
from ..intel.net import TTLCache

FOOTER = "Facts from exchange filings, company documents and market data. Not investment advice."
UNSUBSCRIBE = kit.UNSUBSCRIBE               # the sender fills this in per reader
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
    """The public site every email link points to (the same address as the email kit's buttons)."""
    return settings.PUBLIC_SITE_URL.rstrip("/")


def stock_url(region: str, symbol: str) -> str:
    return f"{origin()}/research/{region}/{symbol}"


def _pct(x) -> str:
    return "" if x is None else kit.pct(x)          # +0.62%, −0.34% (a real minus, as in the tiles)


def _num(x) -> str:
    return "" if x is None else kit.num(x)          # 1,23,456.75: Indian digit grouping


def _day(iso: str) -> str:
    """A day in the app's format: Wed 7 Oct."""
    return kit.fmt_date(str(iso), year=False, weekday=True)


# ---------- sections ----------
def _item(text: str, url: str | None = None, lines: list | None = None, **extra) -> dict:
    return {"text": text, "url": url, "lines": lines or [], **{k: v for k, v in extra.items() if v is not None}}


def market_sections(f: dict) -> list[dict]:
    region, span = f["region"], "over the week" if f["weekly"] else "on the day"
    out = []
    if f.get("indices"):
        out.append({"title": "Indices", "items": [
            _item(f"{i['name']}: {_num(i['price'])}" + (f", {_pct(i['change_pct'])} {span}" if i.get("change_pct") is not None else ""))
            for i in f["indices"]]})
    if f.get("rotation"):
        out.append({"title": "Sector rotation", "items": [
            _item(f"{r['sector']} moved from {r['from'].title()} to {r['to'].title()} on the rotation chart (weekly)", f"{origin()}/research/rotation")
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
    surv = r.get("surveillance") or {}
    for c in surv.get("changes") or []:
        lines.append({"text": f"Exchange surveillance: {c['text']} (list of {_day(c['day'])})", "url": None})
    if surv.get("now") and not surv.get("changes"):
        lines.append({"text": "On exchange surveillance lists: " + ", ".join(surv["now"]), "url": None})
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
            _item(r["symbol"], stock_url(r["region"], r["symbol"]), stock_lines(r, f["since"])[1 if r.get("change_pct") is not None else 0:], price=r.get("price"),
                  change_pct=r.get("change_pct"), since=f"since {_day(f['since'])}" if r.get("change_pct") is not None else None)
            for r in f["stocks"]]})
    if f.get("results"):
        out.append({"title": "Results this week", "items": [result_item(r) for r in f["results"]]})
    if f.get("actions"):
        out.append({"title": "Corporate actions", "items": [action_item(r) for r in f["actions"]]})
    if f.get("unchanged"):
        out.append({"title": "No change", "items": [_item(", ".join(f["unchanged"]))]})
    if f.get("paper"):
        cash = lambda v, p: kit.money(v, p.get("currency") or "INR", signed=True)  # noqa: E731
        out.append({"title": "Your paper trading", "items": [
            _item(f"{p['name']}: {p['closed']} trade{'s' if p['closed'] != 1 else ''} closed today ({cash(p['pnl'], p)}), "
                  f"{cash(p['total'], p)} since start" + (f" ({kit.pct(p['total_pct'], 1)})" if p.get("total_pct") is not None else ""),
                  f"{origin()}/paper") for p in f["paper"]]})
    return out


def sections(f: dict) -> list[dict]:
    return market_sections(f) if f["kind"] == "market" else stock_sections(f)


def subject(f: dict) -> str:
    when = f"week to {kit.fmt_date(f['day'], year=False)}" if f["weekly"] else _day(f["day"])
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
            parts.append(f"{n} stock{'s' if n != 1 else ''} from the {scan['group']} newly matched the Stage 2 + Supertrend rule.")
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


_WORDS_N = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
_SECTORS_MOVED = re.compile(r"[^.]*?\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten) sectors? (moved|shifted|changed|switched)[^.]*\.\s*", re.I)


def fix_counts(text: str, sections: list[dict]) -> str:
    """The summary's "N sectors moved" as the Sector rotation section has them (R6O-004: India 7 Oct said 6 and listed 2;
    US 7 Oct said 5 with no rotation section). Without the section the sentence goes."""
    n = len(next((s.get("items") or [] for s in sections or [] if s.get("title") == "Sector rotation"), []))

    def one(m):
        if not n:
            return ""
        said = m.group(1).lower()
        if _WORDS_N.get(said, int(said) if said.isdigit() else -1) == n:
            return m.group(0)
        return re.sub(r"\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten) sectors?\b",
                      f"{n} sector{'s' if n != 1 else ''}", m.group(0), count=1, flags=re.I)
    return _SECTORS_MOVED.sub(one, text or "").strip()


def grounded(text: str, f: dict) -> bool:
    """Every ticker-like word in the text is in the facts, every number is one of the facts' (R7O-001: the same number
    check as every AI read), and no advice, forecast or hype words."""
    if not text or banned(text):
        return False
    hay = json.dumps(f, ensure_ascii=False, default=str).upper()
    for word in re.findall(r"\b[A-Z][A-Z0-9&\-]{1,14}\b", text):
        if word not in ALLOWED_CAPS and word not in hay:
            return False
    from ..intel import grounding
    pool = grounding.fact_numbers(f)
    return all(grounding.number_backed(v, after, pool) for v, after in grounding._numbers(text))


WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
_WEEKDAY = re.compile(r"\b(" + "|".join(WEEKDAYS) + r")\b", re.I)


def own_weekday(text: str, f: dict) -> str:
    """The day of the week a brief names, from the brief's date, never the model's (R7O-005: the Thursday 8 Oct US brief
    said "mixed on Tuesday"). A daily brief's weekday is its own day's; a weekly brief names none, so a sentence that
    does is dropped."""
    if not text:
        return text
    try:
        day = datetime.fromisoformat(str(f.get("day"))[:10])
    except (TypeError, ValueError):
        return text
    if f.get("weekly"):
        return " ".join(x for x in re.split(r"(?<=[.!?])\s+", text) if x and not _WEEKDAY.search(x)).strip()
    return _WEEKDAY.sub(WEEKDAYS[day.weekday()], text)


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
    text = own_weekday(re.sub(r"\s+", " ", text)[:700], f)
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
link = kit.link            # a link in the kit's colours, plain text when the address isn't a web address
TYPE_LABEL = {"market": "Market brief", "my_stocks": "My stocks"}
DOT = " · "


def as_of(iso: str | None, region: str | None = None) -> str | None:
    """When an issue's numbers were gathered, in words: "3 Oct 2026, 16:15 IST". A US brief is in New York time, as its page
    writes it ("8 Oct 2026, 16:34 ET"), not India's (R7M-002: "9 Oct 2026, 02:04 IST" in the email beside "16:34 ET" on the page)."""
    try:
        d = datetime.fromisoformat(str(iso))
    except (TypeError, ValueError):
        return None
    if region == "US" and d.tzinfo is not None:
        from zoneinfo import ZoneInfo
        d = d.astimezone(ZoneInfo("America/New_York"))
        return f"{d.day} {d:%b %Y}, {d:%H:%M} ET"
    zone = "IST" if d.utcoffset() == timedelta(hours=5, minutes=30) else "UTC" if d.utcoffset() == timedelta(0) else ""
    return f"{d.day} {d:%b %Y}, {d:%H:%M}" + (f" {zone}" if zone else "")


def headline(f: dict) -> str:
    """The email's title: the lead index's move for a brief, what changed for My stocks."""
    if f["kind"] == "market":
        lead = next((i for i in f.get("indices") or [] if i.get("change_pct") is not None), None)
        span = " over the week" if f["weekly"] else ""
        if lead:
            c = lead["change_pct"]
            move = "flat" if round(c, 2) == 0 else f"{'up' if c > 0 else 'down'} {kit.pct_plain(c)}"
            return f"{lead['name']} {move}{span}"
        return f"{REGION_NAME[f['region']]} market{span}"
    tail = subject(f).split(": ", 1)[-1]
    return tail[:1].upper() + tail[1:]


def type_label(f: dict) -> str:
    if f["kind"] == "market":
        return f"{'Weekly brief' if f['weekly'] else 'Market brief'}{DOT}{REGION_NAME[f['region']]}"
    return "My stocks" + (f"{DOT}weekly" if f["weekly"] else "")


def unsubscribe_type(issue: dict) -> str:
    """The one-click unsubscribe category this issue goes out under."""
    if issue.get("kind") == "my_stocks":
        return "my_stocks"
    return "market_us" if issue.get("region") == "US" else "market_in"


def _tone(name: str) -> str:
    return "neutral" if "VIX" in name.upper() else "updown"      # a rise in fear is not good news, so no green


def _tiles(indices: list[dict], weekly: bool) -> list[kit.Tile]:
    out = []
    for i in indices[:3]:
        sub = "over the week" if weekly and i.get("change_pct") is not None else (
            f"{kit.pct_plain(i['from_high_pct'], 1)} below its 52-week high" if i.get("from_high_pct") else None)
        out.append(kit.Tile(i["name"], kit.num(i["price"]), i.get("change_pct"), sub=sub, tone=_tone(i["name"])))
    return out


def _row(it: dict) -> kit.Row:
    lines = tuple((ln["text"], ln.get("url")) for ln in it.get("lines") or [])
    if it.get("change_pct") is not None or it.get("price") is not None:
        return kit.Row(it["text"], value=kit.num(it["price"]) if it.get("price") is not None else None, change=it.get("change_pct"),
                       since=it.get("since"), url=it.get("url"), lines=lines)
    return kit.Row(it["text"], url=it.get("url"), lines=lines)


def render(issue: dict) -> tuple[str, str]:
    """(html, text) for one issue, in the shared email design. The footer carries the {unsubscribe_url} placeholder
    for the sender."""
    view = kit.news_url(issue["id"]) if issue.get("id") else None
    kind = issue.get("kind") or ("my_stocks" if str(issue.get("id", "")).startswith("my_stocks") else "market")
    weekly = bool(issue.get("weekly"))
    day = (f"Week to {_day(issue['day'])}" if weekly else _day(issue["day"])) if issue.get("day") else ""
    region = issue.get("region")
    label = issue.get("label") or (TYPE_LABEL.get(kind, "Newsletter") + (DOT + REGION_NAME[region] if region in REGION_NAME else ""))
    title = issue.get("title") or issue["subject"]
    blocks: list[kit.Block] = []
    indices = issue.get("indices") or []
    tiles = _tiles(indices, weekly)
    if tiles:
        blocks.append(kit.tiles(tiles))
        if indices[3:]:
            blocks.append(kit.card("Other indices", [kit.Row(i["name"], value=kit.num(i["price"]), change=i.get("change_pct"),
                                                             tone=_tone(i["name"]), since="over the week" if weekly else None)
                                                     for i in indices[3:]]))
    if issue.get("ai_summary"):
        # every brief opens with the same facts line; the AI's words, when they passed the checks, come under it (R8B-007)
        blocks.insert(0, kit.para(issue["ai_summary"]))
    for sec in issue.get("sections") or []:
        if tiles and sec["title"] == "Indices":
            continue                                         # already shown as tiles
        blocks.append(kit.card(sec["title"], [_row(it) for it in sec["items"]]))
    when = as_of(issue.get("at"), region)
    if when:
        blocks.append(kit.note(f"Prices and numbers as of {when}"))
    name = {"market_in": "India briefs", "market_us": "US briefs", "my_stocks": "My stocks"}[unsubscribe_type({**issue, "kind": kind, "region": region})]
    what = "My stocks email" if kind == "my_stocks" else f"{REGION_NAME.get(region, '')} market brief".strip()
    footer = kit.Footer(
        why=f"You get this {'weekly' if weekly else 'daily'} because you chose the {what} in StratLab.",
        frequency=("Switch to daily" if weekly else "Switch to weekly", kit.MANAGE_NEWSLETTERS),
        unsubscribe=f"Unsubscribe from {name}", legal=FOOTER, manage=kit.MANAGE_NEWSLETTERS)
    cta = (("Read the full brief" if kind == "market" else "See what changed"), view) if view else None
    return kit.render(title, blocks, footer, label=label, date=day, summary=issue.get("summary") or None, cta=cta,
                      subject=issue["subject"], preheader=kit.short_line(issue.get("summary") or title))
