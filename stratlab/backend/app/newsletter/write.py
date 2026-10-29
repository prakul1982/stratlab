"""Turning the facts into an issue: the sections, an optional short AI summary, and the email (HTML and text).

The newsletters report facts only, as India's research-analyst rules require of anything that isn't registered
research: no buy, sell or hold, no targets, no picks, no outlook. The AI summary is held to that in code: it may
only restate the facts, and a word filter drops it if it slips, in favour of a plain template."""
import hashlib
import json
import re
from datetime import date, datetime, timedelta

from .. import email_kit as kit
from ..ai_providers import AIError, complete, extract_json
from ..config import settings
from ..data.expiries import trading_on_or_before
from ..intel.net import TTLCache
from ..intel.news import aggregator_url, publisher_url

FOOTER = "Facts from exchange filings, company documents and market data. Not investment advice."
UNSUBSCRIBE = kit.UNSUBSCRIBE               # the sender fills this in per reader
REGION_NAME = {"IN": "India", "US": "US"}
STAGE_NAME = {1: "Stage 1 (basing)", 2: "Stage 2 (advancing)", 3: "Stage 3 (topping)", 4: "Stage 4 (declining)"}
# what the stage means, said once beside the first stage a stock's line names (round 39: "Stage 1 (basing)" alone told a reader nothing)
STAGE_WHY = {1: "the 150-day average has stopped falling, or the price has climbed above a falling average",
             2: "the price is above a rising 150-day average",
             3: "the 150-day average has stopped rising, or the price is below a rising one",
             4: "the price is below a falling 150-day average"}

# words that turn a fact into advice, a forecast or hype; any of them drops the AI text (and a headline)
BANNED = [r"\bbuy", r"\bsell", r"\bhold\b", r"\bholding on\b", r"\baccumulat", r"\btarget", r"\boutperform", r"\bunderperform",
          r"\brecommend", r"\bshould (invest|consider|look)", r"\binvest in\b", r"\bmultibagger", r"\btop picks?\b", r"\bpicks?\b",
          r"\bhot\b", r"\bbullish", r"\bbearish", r"\boutlook", r"\bforecast", r"\bpredict", r"\bexpect", r"\blikely\b",
          r"\bwill (rise|fall|go|climb|drop|rally|gain|continue)", r"\bupside", r"\bdownside", r"\bstop[- ]?loss", r"\bundervalued",
          r"\bovervalued", r"\bopportunit", r"\bguarantee", r"\bmust\b", r"\brally ahead", r"\bbreakout candidate", r"\bsure[- ]shot",
          # a stock-picking service's own stance ("keeps us positive on Lilly", CNBC Investing Club) is advice, not a fact (R72-002)
          r"\b(positive|negative|constructive|cautious) on\b", r"\binvesting club\b",
          # a trade idea ("Apple shares aren't cheap. Here's how to get long for less") is advice too (R76)
          r"\b(get|go|going|getting) (long|short)\b", r"\bhow to (play|trade)\b", r"\bways? to play\b"]
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


def rotation_url(region: str) -> str:
    """The rotation page in the brief's own market: without it the link opens the saved (US) view (R28-006)."""
    return f"{origin()}/research/rotation?region={region}"


def regional_links(issue: dict) -> dict:
    """The issue with each rotation link pointing at the issue's own market, whenever it was stored."""
    region = issue.get("region")
    if region not in ("IN", "US"):
        return issue
    bare = f"{origin()}/research/rotation"
    secs = [{**sec, "items": [{**i, "url": rotation_url(region)} if i.get("url") == bare else i for i in sec.get("items") or []]}
            if sec.get("title") == "Sector rotation" else sec for sec in issue.get("sections") or []]
    return {**issue, "sections": secs}


def _pct(x) -> str:
    return "" if x is None else kit.pct(x)          # +0.62%, −0.34% (a real minus, as in the tiles)


def _num(x) -> str:
    return "" if x is None else kit.num(x)          # 1,23,456.75: Indian digit grouping


CURRENCY = {"IN": "INR", "US": "USD"}


def _price(x, region: str | None) -> str:
    """A stock's price with its market's currency sign: ₹925.40, $341.27 (R23-006: "925.40" said neither)."""
    if x is None:
        return ""
    cur = CURRENCY.get(region or "")
    return kit.money(x, cur, 2) if cur else kit.num(x)


def past_today(text: str | None, issue: dict, today: str) -> str | None:
    """An issue's summary as read on a later day: its "today" is the issue's own day ("NASDAQ −0.21% on Fri 23 Oct"),
    as the Briefs list shows it on the weekend (R90-007: "… −1.23% today" under Friday's issue on Saturday). The issue
    as sent keeps its words; a weekly one names no day."""
    day = str(issue.get("day") or "")[:10]
    if not text or not day or issue.get("weekly") or day >= today:
        return text
    return re.sub(r"\btoday\b", f"on {_day(day)}", text)


def _day(iso: str) -> str:
    """A day in the app's format: Wed 7 Oct."""
    return kit.fmt_date(str(iso), year=False, weekday=True)


# ---------- sections ----------
def _item(text: str, url: str | None = None, lines: list | None = None, **extra) -> dict:
    return {"text": text, "url": url, "lines": lines or [], **{k: v for k, v in extra.items() if v is not None}}


def _scan_cols(r: dict) -> dict:
    """What the brief's table shows for a stock the scan named (O5): its close and day's change, stage, Supertrend and the day it newly matched."""
    keys = ("price", "change_pct", "stage", "stage_days", "st_up", "st_since", "matched_on")
    return {k: r[k] for k in keys if r.get(k) is not None}


def market_sections(f: dict) -> list[dict]:
    region, span = f["region"], "over the week" if f["weekly"] else "on the day"
    out = []
    if f.get("indices"):
        out.append({"title": "Indices", "items": [
            _item(f"{i['name']}: {_num(i['price'])}" + (f", {_pct(i['change_pct'])} {span}" if i.get("change_pct") is not None else ""))
            for i in f["indices"]]})
    if f.get("rotation"):
        out.append({"title": "Sector rotation", "items": [
            _item(f"{r['sector']} moved from {r['from'].title()} to {r['to'].title()} on the rotation chart {rotation_basis(region)}", rotation_url(region))
            for r in f["rotation"]]})
    scan = f.get("scan") or {}
    # the whole rule and Stage 2 alone are two lists, so the lead's count is the first list's (R13-003)
    if scan.get("st_s2"):
        out.append({"title": f"Newly matched Stage 2 + Supertrend {'in the last 5 days' if f['weekly'] else 'today'} ({scan['group']})", "items": [
            _item(f"{r['symbol']} matches the Stage 2 rule with the price above its Supertrend (ST S2)", stock_url(region, r["symbol"]), **_scan_cols(r))
            for r in scan["st_s2"]]})
    if scan.get("stage2"):
        out.append({"title": f"Newly in Stage 2, Supertrend not up ({scan['group']})", "items": [
            _item(f"{r['symbol']} moved into Stage 2 (matches the Stage 2 rule; its Supertrend isn't up)", stock_url(region, r["symbol"]), **_scan_cols(r))
            for r in scan["stage2"]]})
    # a week with a holiday says which session is missing, rather than skipping it in silence (DI-027)
    gaps = [h for h in f.get("holidays") or [] if h.get("day")] if f["weekly"] else []
    if gaps:
        out.append({"title": "No session", "items": [_item(f"The {REGION_NAME[region]} market was closed on "
                    + " and ".join(_day(h["day"]) + (f" ({h['name']})" if h.get("name") else "") for h in gaps)
                    + f", so the week had {5 - len(gaps)} session{'s' if 5 - len(gaps) != 1 else ''}.")]})
    shut = [c for c in f.get("closures") or [] if c.get("day")]
    reopen = next((c["next_open"] for c in f.get("closures") or [] if c.get("next_open")), None)
    if shut and reopen:
        days = " and ".join(_day(c["day"]) + (f" ({c['name']})" if c.get("name") else "") for c in shut)
        out.append({"title": "Market holiday", "items": [_item(f"The {REGION_NAME[region]} market is closed on {days}. "
                                                               f"The next session is {_day(reopen)}.")]})
    heads = [h for h in f.get("headlines") or [] if not banned(h["headline"])]
    if heads:
        # a week's headlines each say their day: two that say "today" with different Sensex falls read as a contradiction (R93-004)
        # (kept beside the title, so the stored title stays the source's own for the checks that re-read it)
        from .content import _local_day
        out.append({"title": "Headlines", "items": [_item(h["headline"], h.get("url"), source=h.get("source"), at=h.get("at"),
                    day=_day(d) if f["weekly"] and (d := _local_day(h.get("at"), region)) else None) for h in heads]})
    return out


# what the rotation chart measures each sector against (rotation.UNIVERSES): readers assumed NIFTY 50 (DI-027)
ROTATION_BENCH = {"IN": "NIFTY 500", "US": "S&P 500"}


def rotation_basis(region: str) -> str:
    bench = ROTATION_BENCH.get(region)
    return f"(weekly, against the {bench})" if bench else "(weekly)"


def _move_span(r: dict, since: str, day: str | None) -> str:
    """Over what a stock's move is: "since Wed 21 Oct" to the issue's own day, or, when the stock's last close is an
    earlier day's (a US stock in an issue sent before the US opens), both ends: "from Wed 21 Oct to the Thu 22 Oct
    close" (R90-006: NVDA's Thursday close read as Friday's under an issue dated Friday)."""
    start = _day(r.get("since_day") or since)
    end = r.get("price_day")
    if end and day and str(end)[:10] < str(day)[:10]:
        return f"from {start} to the {_day(end)} close"
    return f"since {start}"


def stock_lines(r: dict, since: str, day: str | None = None) -> list[dict]:
    lines = []
    if r.get("change_pct") is not None:
        lines.append({"text": f"Price {_price(r['price'], r.get('region'))}, {_pct(r['change_pct'])} {_move_span(r, since, day)}", "url": None})
    # what the stage means first, then its name: "The price is above a rising 150-day average: now Stage 2 (advancing), was Stage 1 (basing)",
    # not "Now Stage 2 (advancing) (the price is above …), was …" with a bracket inside a sentence of brackets (LIVE1C-032)
    if r.get("stage_changed"):
        now = STAGE_NAME.get(r['stage'], 'Stage ' + str(r['stage']))
        was = STAGE_NAME.get(r['stage_before'], 'Stage ' + str(r['stage_before']))
        lines.append({"text": (f"{STAGE_WHY[r['stage']][0].upper()}{STAGE_WHY[r['stage']][1:]}: now {now}, was {was}" if r['stage'] in STAGE_WHY else f"Now {now}, was {was}"), "url": None})
    elif r.get("stage"):
        now = STAGE_NAME.get(r['stage'], 'Stage ' + str(r['stage']))
        lines.append({"text": (f"{STAGE_WHY[r['stage']][0].upper()}{STAGE_WHY[r['stage']][1:]}: still {now}" if r['stage'] in STAGE_WHY else f"Still {now}"), "url": None})
    if r.get("st_s2"):
        lines.append({"text": "Matches the Stage 2 rule with the price above its Supertrend (ST S2)", "url": None})
    for i in r.get("filings") or []:
        lines.append({"text": f"New filing{' (red flag)' if i['severity'] == 'red' else ''}: {i['label']}. {i['subject']}".strip(), "url": i.get("url")})
    for d in r.get("deals") or []:
        lines.append({"text": f"New disclosure. {d['text']}", "url": d.get("url")})
    surv = r.get("surveillance") or {}
    for c in surv.get("changes") or []:
        lines.append({"text": f"Exchange surveillance: {c['text']} (list of {_day(c['day'])})", "url": None})
    if surv.get("now") and not surv.get("changes"):
        lines.append({"text": "On exchange surveillance lists: " + ", ".join(surv["now"]), "url": None})
    for h in r.get("headlines") or []:
        if not banned(h["headline"]):
            lines.append({"text": h["headline"] + (f" ({h['source']})" if h.get("source") else ""), "url": h.get("url")})
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
            _item(r["symbol"], stock_url(r["region"], r["symbol"]), stock_lines(r, f["since"], f.get("day"))[1 if r.get("change_pct") is not None else 0:], price=r.get("price"),
                  region=r.get("region"),
                  currency=CURRENCY.get(r.get("region") or ""),
                  change_pct=r.get("change_pct"), since=_move_span(r, f["since"], f.get("day")) if r.get("change_pct") is not None else None)
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
    # a weekly issue is dated its Saturday; its numbers run to Friday's close, and the subject says so, as the issue's
    # own header does (R90-004: "Market Brief India, week to 24 Oct" over figures as of the 23 Oct close)
    when = f"week to {kit.fmt_date(_week_end(f['day'], f.get('region') or 'IN'), year=False)}" if f["weekly"] else _day(f["day"])
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
            parts.append(f"{n} stock{'s' if n != 1 else ''} from the {scan['group']} newly matched the Stage 2 + Supertrend rule {'in the last 5 days' if f['weekly'] else 'today'}.")
        if scan.get("stage2"):
            n = len(scan["stage2"])
            parts.append(f"{n} {'other ' if scan.get('st_s2') else ''}stock{'s' if n != 1 else ''} newly entered Stage 2 {'in the last 5 days' if f['weekly'] else 'today'} without the Supertrend.")
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
A scan names its own fixed list of stocks: call it by that name, never "large caps" or the market, and never say a stock was the only one in the market.
The line above your summary already gives each index's move, and a list below gives each index's level: don't restate them. Say what else happened, as short prose a person would say: the sectors that moved on the rotation chart, how many stocks the scan newly named, the day's headlines in a few words. A stock a scan named is named for meeting its rule: never give its price move beside it. Numbers with thousands separators (22,520.45). Plain English, no markdown, no emojis. Reply with ONLY this JSON: {"summary": "..."}"""


# a restatement of the tiles ("The NIFTY 50 price is 22520.45 with a 0.44 percent change"): the facts line and the tiles
# already say it, so such a text is dropped rather than shown; so is a number without its separators (R19-003)
_ROBOTIC = re.compile(r"\bprice is\b|\bpercent change\b|\b\d{4,}\.\d+|\b\d{5,}\b")


def robotic(text: str) -> bool:
    return bool(_ROBOTIC.search(text or ""))


def ai_summary(f: dict) -> str | None:
    from ..ai_writer import _anthropic, _gemini
    facts = {k: v for k, v in f.items() if k not in ("uid",)}
    if f.get("weekly") and f.get("day"):             # the week ends at its last close, not the Saturday it is sent (R90-004)
        facts["day"] = _week_end(f["day"], f.get("region") or "IN")
    try:
        raw = complete(SYSTEM, "FACTS:\n" + json.dumps(facts, ensure_ascii=False, default=str), gemini=_gemini,
                       anthropic=_anthropic, max_tokens=500, kind="research")
        text = str(extract_json(raw).get("summary") or "").strip()
    except (AIError, ValueError, AttributeError, TypeError):
        return None
    text = close_date_words(day_first(no_scan_moves(not_the_indices(two_decimals(own_weekday(re.sub(r"\s+", " ", text)[:700], f)), f), scan_names(f))), f)
    return text if text and grounded(text, f) and not robotic(text) else None


def not_the_indices(text: str, f: dict) -> str:
    """The AI's words without a sentence that restates an index's move: the facts line above it and the Indices list below
    already give each one (DP2-037: the weekly brief said the same three index figures three times)."""
    moves = [(i["name"].lower(), f"{abs(i['change_pct']):.2f}") for i in f.get("indices") or [] if i.get("name") and i.get("change_pct") is not None]
    keep = [x for x in re.split(r"(?<=[.!?])\s+", text or "") if x and not any(n in x.lower() and m in x for n, m in moves)]
    return " ".join(keep).strip()


_SCAN_WORDS = re.compile(r"\bscan\b|\bstage 2\b|\bsupertrend\b", re.I)


def scan_names(f: dict) -> list[str]:
    """The symbols and names of the stocks the brief's scan named."""
    scan = f.get("scan") or {}
    return [x for r in (scan.get("st_s2") or []) + (scan.get("stage2") or []) for x in (r.get("symbol"), r.get("name")) if x]


def no_scan_moves(text: str | None, names=()) -> str:
    """The AI's words without a sentence that gives a price move for a stock the scan named: a scan names a stock for
    meeting its rule, and the move it carries is the last session's alone (RC2B-010: the weekly brief of 24 Oct said "In the
    scan of NIFTY 50 stocks, Tech Mahindra Limited dropped 2.14%", Thursday's fall in a week the stock ended where it began).
    A sentence is dropped when it has a percentage and speaks of the scan, Stage 2 or the Supertrend, or names a stock the
    scan named."""
    named = re.compile(r"\b(?:" + "|".join(re.escape(str(n)) for n in names if n) + r")\b", re.I) if any(names) else None
    keep = []
    for x in re.split(r"(?<=[.!?])\s+", text or ""):
        if x and re.search(r"%|\bper ?cent\b", x, re.I) and (_SCAN_WORDS.search(x) or (named and named.search(x))):
            continue
        keep.append(x)
    return " ".join(k for k in keep if k).strip()


_ONE_DP = re.compile(r"(?<![\d.,])(\d{1,3}(?:,\d{2,3})+)\.(\d)(?![\d%])")


def two_decimals(text: str) -> str:
    """A price the model wrote with one decimal ("jumped 8.48% to 1,790.0") with two, as every other price in the brief
    and on the site (R35); percentages and plain numbers stay as written."""
    return _ONE_DP.sub(lambda m: f"{m.group(1)}.{m.group(2)}0", text or "")


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
    # a written summary is kept the day; the template stands in for a failed AI call only for a few minutes, so a one-off
    # failure doesn't freeze it as the issue's summary
    _cache.set(key, out, 24 * 3600 if text else 10 * 60)
    return out


# ---------- the email ----------
link = kit.link            # a link in the kit's colours, plain text when the address isn't a web address
TYPE_LABEL = {"market": "Market brief", "my_stocks": "My stocks"}
DOT = " · "


CLOSE_AT = {"IN": "15:30 IST", "US": "16:00 ET"}


def close_stamp(issue: dict) -> str | None:
    """A Market Brief's numbers are the day's close, so its stamp names the close, not the moment it was built (R13-003:
    "Prices and numbers as of 9 Oct 2026, 16:32 ET" over the 16:00 ET close): "the 16:00 ET close of 9 Oct 2026". None for
    My Stocks, whose stamp stays its build time."""
    if issue.get("kind") != "market" or issue.get("region") not in CLOSE_AT or not issue.get("day"):
        return None
    try:
        d = datetime.fromisoformat(str(issue["day"])[:10])
    except ValueError:
        return None
    if issue.get("weekly"):                    # the weekly issue is dated its Saturday; the close is the last trading day before it
        d = datetime.combine(trading_on_or_before(d.date(), issue["region"]), d.time())
    return f"the {CLOSE_AT[issue['region']]} close of {d.day} {d:%b %Y}"


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
            f"{kit.pct_plain(i['from_high_pct'], 1)} below its 52-week high" if (i.get("from_high_pct") or 0) < 0 else None)
        out.append(kit.Tile(i["name"], kit.num(i["price"]), i.get("change_pct"), sub=sub, tone=_tone(i["name"])))
    return out


def _row(it: dict) -> kit.Row:
    lines = tuple((ln["text"], ln.get("url")) for ln in it.get("lines") or [])
    if it.get("change_pct") is not None or it.get("price") is not None:
        price = it.get("price")
        value = None if price is None else kit.money(price, it["currency"], 2) if it.get("currency") else kit.num(price)
        return kit.Row(it["text"], value=value, change=it.get("change_pct"),
                       since=it.get("since"), url=it.get("url"), lines=lines)
    return kit.Row(f"{it['day']}: {it['text']}" if it.get("day") else it["text"], url=it.get("url"), lines=lines, source=it.get("source"))


def link_path(issue_id: str, n: int) -> str:
    """A short address on the site for a brief's nth headline, which forwards to the story (main.news_link): the plain-text
    part prints it where the story's own address is a news aggregator's redirect of ~500 characters (R13-003: no address
    at all for the two Reuters headlines)."""
    return f"/news-link/{issue_id}/{n}"


def _headline_link(url):
    u = publisher_url(url)
    return None if aggregator_url(u) else u


def headline_urls(issue: dict) -> list[str | None]:
    """The brief's headline links in order, as link_path numbers them: the list frozen when the issue was first sent
    (`links`), else the issue's Headlines as they are now. A later headline rule that drops a story from a sent brief
    no longer moves the numbers its email links carry (R23-004)."""
    frozen = issue.get("links")
    if isinstance(frozen, list):
        return list(frozen)
    return [i.get("url") for s in issue.get("sections") or [] if s.get("title") == "Headlines" for i in s.get("items") or []]


_NUMBER = re.compile(r"(?<![\w.,])(\d{1,3}(?:,\d{2,3})+|\d+)(\.\d+)?(?![\w,]*\d)(?!%)")
_PERCENT = re.compile(r"(?<![\w.])([+\-\u2212]?)(\d+(?:\.\d+)?)%")


def house_numbers(text: str | None, indices: list[dict] | None) -> str | None:
    """The AI's words with the index numbers as the tiles print them (R23-007: "22,622.7 (-0.44%)" beside a tile of
    "22,622.70 ▼ 0.44%"): an index level it names to fewer places gets the tile's two decimals, a move it names gets
    two decimals too, and every minus before a number is a real one. Numbers that aren't an index's are left alone."""
    if not text:
        return text
    levels = [float(i["price"]) for i in indices or [] if isinstance(i.get("price"), (int, float))]
    moves = [abs(float(i["change_pct"])) for i in indices or [] if isinstance(i.get("change_pct"), (int, float))]

    def level(m: re.Match) -> str:
        whole, frac = m.group(1), m.group(2) or ""
        if not (frac or "," in whole):          # a plain small number ("October 14", "3 sectors") is not a level
            return m.group(0)
        v, places = float(whole.replace(",", "") + frac), max(len(frac) - 1, 0)
        if places >= 2:
            return m.group(0)
        hits = {p for p in levels if p >= 100 and round(p, places) == round(v, places)}
        return kit.num(hits.pop()) if len(hits) == 1 else m.group(0)

    def move(m: re.Match) -> str:
        sign, body = m.group(1), m.group(2)
        places = len(body.split(".")[1]) if "." in body else 0
        hits = {c for c in moves if places < 2 and round(c, places) == round(float(body), places)}
        body = f"{hits.pop():.2f}" if len(hits) == 1 else body      # two indices that round alike: left as written
        return ("\u2212" if sign in ("-", "\u2212") else sign) + body + "%"

    # an index named as its tile names it ("Nasdaq" beside the NASDAQ tile, DI-028)
    for i in indices or []:
        name = str(i.get("name") or "")
        if len(name) > 3:
            text = re.sub(r"\b" + re.escape(name) + r"\b", name, text, flags=re.I)
    out = _PERCENT.sub(move, _NUMBER.sub(level, text))
    return re.sub(r"(^|[\s(:;,])-(?=\d)", "\\1\u2212", out)


def _week_end(day: str, region: str | None = None) -> str:
    """The last trading day a weekend issue's numbers run to: Saturday's or Sunday's issue is the week to Friday's close
    ("Week to Sat 17 Oct" over figures as of the 16 Oct close read as a contradiction, R55-007), as the page says. With
    the market's `region`, a Friday holiday counts too: the week of Fri 2 Oct (Gandhi Jayanti) ran to Thursday's close
    (DI-026: "as of the 15:30 IST close of 2 Oct" over 1 Oct's figures)."""
    try:
        d = date.fromisoformat(str(day)[:10])
    except ValueError:
        return day
    d -= timedelta(days={5: 1, 6: 2}.get(d.weekday(), 0))
    return (trading_on_or_before(d, region) if region else d).isoformat()


def close_day(issue: dict) -> str | None:
    """The trading day a Market Brief's numbers are the close of: its own day, or a weekly one's last session."""
    if issue.get("kind") != "market" or not issue.get("day"):
        return None
    return _week_end(issue["day"], issue.get("region") or "IN") if issue.get("weekly") else str(issue["day"])[:10]


_MONTHS = ("Jan(?:uary)?", "Feb(?:ruary)?", "Mar(?:ch)?", "Apr(?:il)?", "May", "June?", "July?", "Aug(?:ust)?",
           "Sep(?:t|tember)?", "Oct(?:ober)?", "Nov(?:ember)?", "Dec(?:ember)?")
_US_DATE = re.compile(r"\b(" + "|".join(_MONTHS) + r")\.? (\d{1,2})(?:st|nd|rd|th)?\b(,? (\d{4}))?(?![\d,.]*%)")


def day_first(text: str | None) -> str | None:
    """A date the AI wrote in US order ("over the week ending Oct 24", "October 23, 2026") in the app's, day first
    ("24 Oct", "23 Oct 2026") (DI-026)."""
    if not text:
        return text
    return _US_DATE.sub(lambda m: f"{int(m.group(2))} {m.group(1)[:3]}" + (f" {m.group(4)}" if m.group(4) else ""), text)


def close_date_words(text: str | None, f: dict) -> str | None:
    """A weekly brief's own Saturday or Sunday written as the week's end ("over the week ending 24 Oct") as the last close's day, the
    Friday its header and its figures say ("Week to Fri 23 Oct"): one date in one brief (LIVE1C-031)."""
    if not text or not f.get("weekly") or not f.get("day"):
        return text
    try:
        sent = date.fromisoformat(str(f["day"])[:10])
        end = date.fromisoformat(_week_end(f["day"], f.get("region") or "IN"))
    except ValueError:
        return text
    return text if end == sent else re.sub(rf"\b0?{sent.day} {sent:%b}\b", f"{end.day} {end:%b}", text)


def render(issue: dict) -> tuple[str, str]:
    """(html, text) for one issue, in the shared email design. The footer carries the {unsubscribe_url} placeholder
    for the sender."""
    issue = regional_links(issue)
    view = kit.news_url(issue["id"]) if issue.get("id") else None
    kind = issue.get("kind") or ("my_stocks" if str(issue.get("id", "")).startswith("my_stocks") else "market")
    weekly = bool(issue.get("weekly"))
    day = (f"Week to {_day(_week_end(issue['day'], issue.get('region') or 'IN'))}" if weekly else _day(issue["day"])) if issue.get("day") else ""
    region = issue.get("region")
    label = issue.get("label") or (TYPE_LABEL.get(kind, "Newsletter") + (DOT + REGION_NAME[region] if region in REGION_NAME else ""))
    title = issue.get("title") or issue["subject"]
    blocks: list[kit.Block] = []
    indices = issue.get("indices") or []
    if issue.get("ai_summary"):
        # every brief opens with the same facts line; the AI's words, when they passed the checks, come under it (R8B-007),
        # with the index numbers printed as the tiles print them (R23-007)
        blocks.insert(0, kit.para(house_numbers(close_date_words(issue["ai_summary"], issue), indices)))
    n = 0
    frozen = issue.get("links") if isinstance(issue.get("links"), list) else None
    from . import tables
    # every section that lists figures is a table (O5); the headlines' links are numbered by the list frozen at the send, so the page
    # and the email agree (R23-004)
    secs = []
    base = issue.get("sections") or []
    if indices and not any(sec.get("title") == "Indices" for sec in base):
        # an issue kept with its index figures but no Indices section: the table is made from the figures
        base = market_sections({"region": region or "IN", "weekly": weekly, "indices": indices})[:1] + list(base)
    for sec in base:
        if sec["title"] == "Headlines" and kind == "market" and issue.get("id"):
            items = []
            for it in sec["items"]:
                k = frozen.index(it.get("url")) if frozen is not None and it.get("url") in frozen else n
                # the story's own address where an aggregator's redirect carries it; a redirect that doesn't is no link at all, as it
                # opens a blank page (R30-006): the headline stays plain text
                own = _headline_link(it.get("url"))
                # an aggregator's address that names no story opens the brief on the site, where its "Source" link works, so every
                # headline in the email can be opened (R49-003: India's were all plain text)
                it = {**it, "url": own or (view if it.get("url") else None)}
                if own and kit.safe_url(it.get("url")) and not kit.plain_url(it.get("url")):      # a long address: the short one in both parts
                    it = {**it, "url": kit.site(link_path(issue["id"], k))}
                n += 1
                items.append(it)
            sec = {**sec, "items": items}
        secs.append(sec)
    listed = [sec for sec in secs if isinstance(sec, dict) and sec.get("items")]
    for t, sec in zip(tables.of({**issue, "sections": secs}), listed):
        if t["kind"] == "table":
            blocks.append(kit.grid(t["title"], t["head"], t["rows"], t["align"], t.get("note"),
                                   (t["link"]["a"], t["link"]["href"]) if t.get("link") else None))
        else:
            blocks.append(kit.card(sec["title"], [_row(it) for it in sec["items"]]))        # prose: a holiday, "no change"
    # made-up figures (an Admin preview) carry no "as of" time: the moment they were built beside invented numbers read as a real reading (LIVE1C-032)
    when = None if issue.get("sample") else close_stamp({**issue, "kind": kind}) or as_of(issue.get("at"), region)
    if when:
        blocks.append(kit.note(f"Prices and numbers as of {when}"))
    # the link says what the page it opens asks about, in the words of the line above it (R67-009: "India briefs" in the
    # email, "the India market email" on the page)
    from ..alerts import NEWSLETTER_NAMES
    name = NEWSLETTER_NAMES[unsubscribe_type({**issue, "kind": kind, "region": region})]
    what = "My stocks email" if kind == "my_stocks" else f"{REGION_NAME.get(region, '')} market brief".strip()
    footer = kit.Footer(
        why=f"You get this {'weekly' if weekly else 'daily'} because you chose the {what} in StratLab.",
        frequency=("Switch to daily" if weekly else "Switch to weekly", kit.MANAGE_NEWSLETTERS),
        unsubscribe=f"Unsubscribe from {name}", legal=FOOTER, manage=kit.MANAGE_NEWSLETTERS)
    cta = (("Read the full brief" if kind == "market" else "See what changed"), view) if view else None
    return kit.render(title, blocks, footer, label=label, date=day, summary=issue.get("summary") or None, cta=cta,
                      subject=issue["subject"], preheader=kit.short_line(issue.get("summary") or title))
