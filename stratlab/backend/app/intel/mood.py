"""The Market pulse's mood, worked out in code from figures the app already holds (MOOD-1).

The owner's screenshot (29 Oct): "15 of 16 sector indices up" beside "banks dragged the market", a "main story" no shown
headline carried, an AI line saying a company's purchase lifted the indices, the cards' levels said again in another
rounding, and only the FII number where the DII was in the note. The mood is no longer a sentence an AI wrote: it is a
set of tables (breadth, sectors, the stocks that moved the index, institutions' flows, volatility and currencies, other
markets, today's calendar) and a headline with three to five lines, each built from one of those tables' figures with
ONE rounding (fpct: two decimals, a sign, the minus sign), so a line and the table it comes from cannot disagree.
`verify` checks that again on the finished payload.

Cost: no job of its own. One `Mood` per process holds, for each of the two markets, the finished payload for a minute
while the market trades (a quarter hour after the close), and the sector indices' and the index's last daily closes for
hours; a page opening after that time starts the read behind itself (snapshot.py) and is answered with the last copy.
About 40 KB a market for the payload and 8 KB for the closes."""
from __future__ import annotations

import math
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .snapshot import Snapshot

MINUS = "−"
FRESH_OPEN, FRESH_SHUT = 60.0, 900.0      # seconds a finished payload is served from memory, market open / shut
CLOSES_FRESH = 4 * 3600.0                 # daily closes change once a day
TOP = 5                                   # stocks in each of "adding" and "taking" points
CHUNK = 24                                # hub.quotes reads at most this many symbols at once
SECTOR_MEMBERS = {"IN": 4, "US": 3}       # the largest members of a sector read to say what moved it
US_MOVERS_FROM = 24                       # the US index's biggest companies read for the points table
MIN_COVER = 0.8                           # the share of an index's companies that must be read for its points table
_pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="mood")

# the two markets' other prices: (label, Yahoo-style symbol, kind). `kind` decides how a move is worded.
RISK = {
    "IN": [("India VIX", "^INDIAVIX", "vol"), ("USD/INR", "INR=X", "fx"), ("Brent crude", "BZ=F", "oil"), ("Gold", "GC=F", "gold"),
           ("US 10-year yield", "^TNX", "yield"), ("Dollar index", "DX-Y.NYB", "fx")],
    "US": [("VIX", "^VIX", "vol"), ("US 10-year yield", "^TNX", "yield"), ("Dollar index", "DX-Y.NYB", "fx"), ("WTI crude", "CL=F", "oil"),
           ("Gold", "GC=F", "gold"), ("USD/INR", "INR=X", "fx")],
}
GLOBAL = {
    "IN": [("Nikkei 225", "^N225", "Asia"), ("Hang Seng", "^HSI", "Asia"), ("Kospi", "^KS11", "Asia"), ("FTSE 100", "^FTSE", "Europe"),
           ("DAX", "^GDAXI", "Europe"), ("S&P 500 futures", "ES=F", "US"), ("Nasdaq futures", "NQ=F", "US")],
    "US": [("Nikkei 225", "^N225", "Asia"), ("Hang Seng", "^HSI", "Asia"), ("Kospi", "^KS11", "Asia"), ("FTSE 100", "^FTSE", "Europe"),
           ("DAX", "^GDAXI", "Europe"), ("CAC 40", "^FCHI", "Europe"), ("NIFTY 50", "^NSEI", "India")],
}
# the breadth group each market's mood counts, and the index whose usual daily move and points it is held to
BREADTH_GROUP = {"IN": "nifty500", "US": "sp500"}
INDEX_SYMBOL = {"IN": ("NIFTY 50", "^NSEI"), "US": ("S&P 500", "^GSPC")}
# a short name for a sector index in a sentence, and the words a text may use for it (grounding.sector_direction_ok)
SECTOR_WORDS = {
    "NIFTY BANK": r"\bbank(?:s|ing)?\b", "NIFTY IT": r"\bit (?:sector|stocks?|shares|index|services)\b|\btech(?:nology)?\b|\bsoftware\b",
    "NIFTY AUTO": r"\bauto(?:s|mobiles?|motive)?\b|\bcar ?makers?\b", "NIFTY FMCG": r"\bfmcg\b|\bconsumer (?:goods|staples)\b",
    "NIFTY PHARMA": r"\bpharma(?:ceuticals?)?\b|\bdrug ?makers?\b", "NIFTY METAL": r"\bmetals?\b|\bsteel\b",
    "NIFTY REALTY": r"\brealty\b|\breal estate\b|\bproperty\b", "NIFTY ENERGY": r"\benergy\b|\bpower\b",
    "NIFTY MEDIA": r"\bmedia\b", "NIFTY PSU BANK": r"\bpsu banks?\b|\bpublic[- ]sector banks?\b",
    "NIFTY PVT BANK": r"\bprivate(?:[- ]sector)? banks?\b|\bpvt banks?\b", "NIFTY FIN SERVICE": r"\bfinancials?\b|\bfinancial (?:services|sector|stocks)\b|\bfinance\b",
    "NIFTY INFRA": r"\binfra(?:structure)?\b", "NIFTY OIL AND GAS": r"\boil (?:and|&) gas\b", "NIFTY HEALTHCARE": r"\bhealth ?care\b",
    "NIFTY CONSR DURBL": r"\bconsumer durables\b",
    "Technology": r"\btech(?:nology)?\b|\bsoftware\b|\bchip(?:s|makers?)?\b|\bsemiconductors?\b", "Financials": r"\bfinancials?\b|\bbank(?:s|ing)?\b",
    "Health care": r"\bhealth ?care\b|\bpharma(?:ceuticals?)?\b|\bbiotech\b", "Energy": r"\benergy\b|\boil\b",
    "Industrials": r"\bindustrials?\b", "Consumer discretionary": r"\bconsumer discretionary\b|\bretail(?:ers)?\b",
    "Consumer staples": r"\bconsumer staples\b", "Utilities": r"\butilit(?:y|ies)\b", "Materials": r"\bmaterials\b|\bminers?\b",
    "Real estate": r"\breal estate\b|\bproperty\b|\breits?\b", "Communication": r"\bcommunication(?:s)?\b|\btelecom\b",
}


# ---------- one wording of every figure ----------
def num(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) else None


def fpct(v, dp: int = 2, sign: bool = True) -> str:
    """A percentage as the whole page writes it: two decimals, the minus sign, a plus only when it is above zero."""
    v = num(v)
    if v is None:
        return "–"
    r = round(v, dp)
    body = f"{abs(r):.{dp}f}%"
    return body if not sign else ("+" if r > 0 else MINUS if r < 0 else "") + body


def sgn(v, dp: int = 2) -> int:
    """-1, 0 or 1 as the figure reads once rounded: a move that shows as 0.00% is neither up nor down."""
    v = num(v)
    r = round(v, dp) if v is not None else 0.0
    return (r > 0) - (r < 0)


def fnum(v, dp: int = 0) -> str:
    v = num(v)
    return "–" if v is None else f"{v:,.{dp}f}".replace("-", MINUS)


def fcr(v) -> str:
    """Rupees crore with Indian digit grouping, no decimals."""
    v = num(v)
    if v is None:
        return "–"
    s = f"{abs(round(v)):.0f}"
    head, tail = s[:-3], s[-3:]
    head = re.sub(r"(\d)(?=(\d\d)+$)", r"\1,", head) if head else ""
    return f"₹{head + ',' + tail if head else tail} crore"


def day_words(iso: str | None) -> str:
    try:
        d = date.fromisoformat(str(iso)[:10])
    except ValueError:
        return ""
    return f"{d.day} {d.strftime('%b')}"


# ---------- pure builders (every one testable from a fixture) ----------
def typical_move(closes: list) -> dict | None:
    """The index's usual daily move: the average absolute close-to-close change over the last 20 sessions in `closes`
    (completed sessions only, oldest first); None under 10 sessions."""
    c = [float(x) for x in closes if num(x) and x > 0][-21:]
    if len(c) < 11:
        return None
    moves = [abs(c[i] / c[i - 1] - 1) * 100 for i in range(1, len(c))]
    return {"avg_abs": round(sum(moves) / len(moves), 2), "days": len(moves)}


def size_words(ratio: float | None) -> str:
    """Today's move against the usual one, in words: the same ladder the headline and the line use."""
    if ratio is None:
        return ""
    if ratio < 0.4:
        return "a very quiet day"
    if ratio < 0.8:
        return "a quieter day than usual"
    if ratio <= 1.25:
        return "an ordinary day"
    if ratio <= 2.0:
        return "a bigger day than usual"
    return "a very large day"


def compare_today(name: str, change_pct, typ: dict | None) -> dict | None:
    """{"index", "avg_abs", "days", "ratio", "words"}: today's move of `name` against its 20-day average absolute move."""
    c = num(change_pct)
    if c is None or not typ or not typ.get("avg_abs"):
        return None
    ratio = round(abs(round(c, 2)) / typ["avg_abs"], 1)
    return {"index": name, "avg_abs": typ["avg_abs"], "days": typ["days"], "ratio": ratio, "words": size_words(ratio)}


def breadth_block(view_today: dict | None, live: dict | None, group_name: str, session_day: str | None) -> dict | None:
    """Advancers, decliners, unchanged, new 52-week highs and lows and the shares above the 20-, 50- and 200-day averages.
    While the market trades the live counts (a quarter-hourly round) are the figures; highs and lows come from the last
    close's count either way (the live round does not count them). `rows` is the table: measure, today, the day before,
    the change, with what it means in a few words."""
    t = view_today or None
    lv = live if live and live.get("adv") is not None else None
    if not t and not lv:
        return None

    def v(k):
        return num(((t or {}).get(k) or {}).get("value"))

    def prev(k):
        return num(((t or {}).get(k) or {}).get("prev"))
    adv, dec, unch = (num(lv["adv"]), num(lv["dec"]), num(lv.get("unch"))) if lv else (v("adv"), v("dec"), v("unch"))
    out = {"group": group_name, "live": bool(lv), "day": session_day if lv else (t or {}).get("day"), "close_day": (t or {}).get("day"),
           "prev_day": (t or {}).get("prev_day"), "adv": adv, "dec": dec, "unch": unch,
           "stocks": v("stocks") if not lv else (adv or 0) + (dec or 0) + (unch or 0),
           "highs": v("highs"), "lows": v("lows"),
           "pct20": num(lv.get("pct20")) if lv else v("pct20"), "pct50": num(lv.get("pct50")) if lv else v("pct50"),
           "pct200": num(lv.get("pct200")) if lv else v("pct200")}
    out["ratio"] = round(adv / dec, 2) if adv is not None and dec else None
    rows = []

    def row(key, label, now, before, kind, means, unit=""):
        rows.append({"key": key, "label": label, "now": now, "before": before, "kind": kind, "means": means, "unit": unit,
                     "change": round(now - before, 1 if unit == "%" else 0) if now is not None and before is not None else None})
    row("adv", "Stocks that rose", adv, prev("adv") if not lv else None, "count", "Stocks closing above the previous close.")
    row("dec", "Stocks that fell", dec, prev("dec") if not lv else None, "count", "Stocks closing below the previous close.")
    row("highs", "New 52-week highs", out["highs"], prev("highs"), "count", "Stocks at their highest price in a year.")
    row("lows", "New 52-week lows", out["lows"], prev("lows"), "count", "Stocks at their lowest price in a year.")
    row("pct50", "Above 50-day average", out["pct50"], prev("pct50") if not lv else None, "share", "Share of stocks priced above their 50-day average.", "%")
    row("pct200", "Above 200-day average", out["pct200"], prev("pct200") if not lv else None, "share", "Share of stocks priced above their 200-day average.", "%")
    out["rows"] = [r for r in rows if r["now"] is not None]
    return out


def sector_table(today: dict, closes: dict, movers: dict | None = None, label=lambda n: n) -> dict | None:
    """The sector indices' table. `today` is {name: {"price", "change_pct"}}; `closes` {name: [completed sessions' closes]}
    gives the week and month returns against the price now (5 and 21 sessions back); `movers` {name: [{"symbol",
    "change_pct"}]} the largest members' moves. Rows are sorted by today's move; the counts are the rows' own."""
    rows = []
    for name, q in today.items():
        c = num((q or {}).get("change_pct"))
        if c is None:
            continue
        cl = [x for x in (closes.get(name) or []) if num(x)]
        px = num((q or {}).get("price"))

        def back(n):
            return round((px / cl[-n] - 1) * 100, 2) if px and len(cl) >= n and cl[-n] else None
        rows.append({"name": name, "label": label(name), "change_pct": round(c, 2), "w1": back(5), "m1": back(21),
                     "movers": (movers or {}).get(name) or []})
    if len(rows) < 5:
        return None
    rows.sort(key=lambda r: (-r["change_pct"], r["name"]))
    up, down = sum(1 for r in rows if sgn(r["change_pct"]) > 0), sum(1 for r in rows if sgn(r["change_pct"]) < 0)
    return {"rows": rows, "up": up, "down": down, "unchanged": len(rows) - up - down, "of": len(rows),
            "leader": rows[0]["label"], "laggard": rows[-1]["label"]}


def index_movers(members: list[dict], prev_level: float | None, index_name: str, top: int = TOP, total: int | None = None) -> dict | None:
    """The stocks adding and taking the most points from an index, estimated from each company's market value:
    weight = value / the index's total value, points = weight x its move x the index's previous level. `members` are
    {"symbol", "name", "market_cap", "change_pct"}; `total` the market value of every company in the index when more
    were read than `members` (the US index's largest are read, the weights are over all). None when too few were read
    to say."""
    prev_level = num(prev_level)
    pool = [m for m in members if num(m.get("market_cap")) and num(m.get("change_pct")) is not None]
    whole = total or sum(m["market_cap"] for m in pool)
    if not prev_level or not whole or len(pool) < max(3, int(len(members) * MIN_COVER)):
        return None
    rows = [{"symbol": m["symbol"], "name": m.get("name") or m["symbol"], "change_pct": round(m["change_pct"], 2),
             "points": round(prev_level * (m["market_cap"] / whole) * m["change_pct"] / 100, 1)} for m in pool]
    adding = sorted((r for r in rows if sgn(r["points"], 0) > 0), key=lambda r: -r["points"])[:top]
    taking = sorted((r for r in rows if sgn(r["points"], 0) < 0), key=lambda r: r["points"])[:top]
    if not adding and not taking:
        return None
    return {"index": index_name, "adding": adding, "taking": taking, "of": len(pool),
            "note": "Points are estimated from each company's market value, so they differ a little from the exchange's own free-float figures."}


def flows_block(cash: dict | None, days: list[tuple[str, dict]]) -> dict | None:
    """FII and DII cash-market net buying (₹ crore) for the newest day and the last five: [{"day", "fii", "dii"}]."""
    if not cash or cash.get("status") != "ok" or not (cash.get("fii") and cash.get("dii")):
        return None
    rows = []
    for d, v in days[-5:]:
        f, i = num((v.get("fii") or {}).get("net")), num((v.get("dii") or {}).get("net"))
        if f is not None and i is not None:
            rows.append({"day": d, "fii": round(f), "dii": round(i)})
    if not rows or rows[-1]["day"] != cash.get("as_of"):         # the newest day always comes from the same figures the AI is held to
        f, i = num(cash["fii"].get("net")), num(cash["dii"].get("net"))
        if f is None or i is None:
            return None
        rows = [r for r in rows if r["day"] != cash.get("as_of")] + [{"day": cash.get("as_of"), "fii": round(f), "dii": round(i)}]
        rows = sorted(rows, key=lambda r: r["day"])[-5:]
    return {"as_of": cash.get("as_of"), "rows": rows, "fii_total": sum(r["fii"] for r in rows), "dii_total": sum(r["dii"] for r in rows),
            "note": "Provisional cash-market figures in ₹ crore; the final ones can differ a little."}


def quote_rows(spec: list[tuple], got: dict[str, dict | None], today: str, tzs: dict[str, str] | None = None) -> list[dict]:
    """Rows of {"label", "price", "change_pct", "day", "group"/"kind"} from the quotes read; a symbol with none is left out."""
    rows = []
    for item in spec:
        label, sym, tag = item
        q = got.get(sym)
        if not q or num(q.get("price")) is None:
            continue
        day = None
        if q.get("at"):
            try:
                at = datetime.fromisoformat(str(q["at"]).replace("Z", "+00:00"))
                zone = ZoneInfo(q.get("tz") or "UTC")
                day = at.astimezone(zone).date().isoformat()
            except Exception:
                day = None
        rows.append({"label": label, "symbol": sym, "tag": tag, "price": num(q["price"]), "change_pct": round(num(q.get("change_pct")), 2) if num(q.get("change_pct")) is not None else None,
                     "day": day, "same_day": day == today if day else None})
    return rows


# ---------- the words ----------
def headline_of(indices: list[dict], sectors: dict | None, cmp: dict | None) -> str:
    """One short headline the figures below justify: the day's tone from the index moves, how big a day it is against the
    usual, and (when there is a count) how many sector indices went the same way. No level and no move is repeated."""
    moves = [(str(i["name"]), float(i["change_pct"])) for i in indices if i.get("name") and num(i.get("change_pct")) is not None][:4]
    if not moves:
        return ""
    ups, downs = [n for n, c in moves if sgn(c) > 0], [n for n, c in moves if sgn(c) < 0]
    avg = sum(c for _, c in moves) / len(moves)
    sec = sectors if sectors and sectors.get("of") else None

    def names(xs):
        return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " and " + xs[-1]
    if ups and downs:
        out = f"Mixed: the {names(ups)} up and the {names(downs)} down on the day"
        if sec:
            out += f", with {sec['up']} of {sec['of']} sector indices up and {sec['down']} down"
        return out + "."
    count = {2: "both", 3: "all three", 4: "all four"}
    a = abs(round(avg, 2))
    up = avg > 0 or (round(avg, 2) == 0 and not downs)
    word = ("flat" if a < 0.25 else "mildly positive" if a < 1 and up else "mildly negative" if a < 1
            else "positive" if a < 2 and up else "negative" if a < 2 else "sharply positive" if up else "sharply negative")
    if not ups and not downs:
        return (f"Flat: {count.get(len(moves), 'the')} indices unchanged on the day" if len(moves) > 1 else "Flat on the day") + "."
    who = f"{count[len(moves)]} indices" if len(moves) in count else f"the {moves[0][0]}"
    way = "up" if up else "down"
    out = f"{word[:1].upper() + word[1:]}: {who} {way} on the day"
    if cmp and cmp.get("words"):
        out += f", {cmp['words']}"
    if sec:
        n = sec["up"] if up else sec["down"]
        out += f", with {n} of {sec['of']} sector indices {way}"
    return out + "."


def lines_of(p: dict) -> list[str]:
    """Three to five plain lines, each from one table of the payload, in this order of importance. No advice, no forecast."""
    out: list[tuple[str, str]] = []
    c = p.get("compare")
    if c:
        out.append(("compare", f"Today's move in the {c['index']} is {c['ratio']:.1f} times its 20-day average daily move ({fpct(c['avg_abs'], sign=False)})."))
    b = p.get("breadth")
    if b and b.get("adv") is not None and b.get("dec") is not None:
        when = "so far today" if b.get("live") else f"on {day_words(b.get('day'))}" if b.get("day") else ""
        tail = f"; {fpct(b['pct50'], 1, sign=False)} are above their 50-day average" if b.get("pct50") is not None else ""
        out.append(("breadth", f"{fnum(b['adv'])} of {fnum(b['stocks'])} {b['group']} stocks rose and {fnum(b['dec'])} fell {when}{tail}.".replace("  ", " ")))
    s = p.get("sectors")
    if s:
        lead, lag = s["rows"][0], s["rows"][-1]
        out.append(("sectors", f"{s['up']} of {s['of']} sector indices rose and {s['down']} fell; {lead['label']} led ({fpct(lead['change_pct'])}) and {lag['label']} lagged ({fpct(lag['change_pct'])})."))
    m = p.get("movers")
    if m and (m["adding"] or m["taking"]):
        bits = []
        if m["adding"]:
            a = m["adding"][0]
            bits.append(f"{a['name']} added about {fnum(a['points'])} points to the {m['index']}")
        if m["taking"]:
            t = m["taking"][0]
            bits.append(f"{t['name']} took off about {fnum(abs(t['points']))}")
        out.append(("movers", " and ".join(bits) + "."))
    f = p.get("flows")
    if f and f["rows"]:
        last = f["rows"][-1]
        way = lambda v: "net buyers" if v > 0 else "net sellers" if v < 0 else "flat"        # noqa: E731
        out.append(("flows", f"On {day_words(last['day'])} FIIs were {way(last['fii'])} of {fcr(abs(last['fii']))} and DIIs {way(last['dii'])} of {fcr(abs(last['dii']))} (provisional)."))
    r = p.get("risk")
    vol = next((x for x in (r or {}).get("rows") or [] if x.get("kind") == "vol"), None)
    if vol and vol.get("change_pct") is not None:
        out.append(("risk", f"{vol['label']} is {fnum(vol['price'], 2)}, {'up' if sgn(vol['change_pct']) > 0 else 'down' if sgn(vol['change_pct']) < 0 else 'unchanged'}"
                    + (f" {fpct(vol['change_pct'], sign=False)}" if sgn(vol["change_pct"]) else "") + " on the day."))
    return [t for _, t in out[:5]]


_PCT = re.compile(r"[+−-]?\d+(?:\.\d+)?%")


def verify(p: dict) -> list[str]:
    """What in a payload's headline and lines doesn't agree with its own tables: every percentage must be one of the
    payload's figures written the one way, and the sector counts, leader and laggard must be the sector table's.
    Empty when it all agrees."""
    problems = []
    allowed = set()
    c = p.get("compare")
    if c:
        allowed.add(fpct(c["avg_abs"], sign=False))
    b = p.get("breadth") or {}
    for k in ("pct20", "pct50", "pct200"):
        if b.get(k) is not None:
            allowed.add(fpct(b[k], 1, sign=False))
    s = p.get("sectors")
    for r in (s or {}).get("rows") or []:
        allowed.update({fpct(r["change_pct"]), fpct(r["change_pct"], sign=False)})
    for r in (p.get("risk") or {}).get("rows") or []:
        if r.get("change_pct") is not None:
            allowed.update({fpct(r["change_pct"]), fpct(r["change_pct"], sign=False)})
    texts = [p.get("headline") or ""] + list(p.get("lines") or [])
    for t in texts:
        for m in _PCT.findall(t):
            if m not in allowed:
                problems.append(f"{m} in \"{t}\" is not one of the page's figures")
        for up, of in re.findall(r"(\d+) of (\d+) sector indices", t):
            if not s or (int(of), int(up)) not in {(s["of"], s["up"]), (s["of"], s["down"])}:
                problems.append(f"\"{up} of {of} sector indices\" is not the sector table's count")
    if s:
        for t in p.get("lines") or []:
            if "led (" in t and (s["rows"][0]["label"] not in t or s["rows"][-1]["label"] not in t):
                problems.append(f"\"{t}\" doesn't name the table's leader and laggard")
    return problems


def tag_story(titles: list[str], rx: str) -> list[int]:
    return [i for i, t in enumerate(titles) if re.search(rx, t or "", re.I)]


# ---------- the data, read ----------
def _closes_of(candles: list[dict], today: str) -> list[float]:
    """Completed sessions' closes from daily candles: the one dated today (still forming, or today's) is left out."""
    out = []
    for c in candles or []:
        t, px = str(c.get("t") or "")[:10], num(c.get("c"))
        if px and t and t < today:
            out.append(px)
    return out


class Mood:
    """The finished payloads and the daily closes behind them, read behind the page and kept in memory."""

    def __init__(self, hub):
        self.hub = hub
        self.payloads = Snapshot(FRESH_OPEN, give_up=40)
        self.closes = Snapshot(CLOSES_FRESH, give_up=60)

    def forget(self):
        self.payloads = Snapshot(FRESH_OPEN, give_up=40)
        self.closes = Snapshot(CLOSES_FRESH, give_up=60)

    # -- sources, each bounded and each allowed to fail alone --
    def _quotes(self, region: str, symbols: list[str]) -> dict[str, dict]:
        symbols = list(dict.fromkeys(symbols))
        out: dict[str, dict] = {}
        for i in range(0, len(symbols), CHUNK):
            try:
                out.update({k: v for k, v in (self.hub.quotes(region, symbols[i:i + CHUNK]) or {}).items() if v})
            except Exception as e:
                print("mood quotes unavailable:", region, str(e)[:100])
        return out

    def _metas(self, spec: list[tuple]) -> dict[str, dict | None]:
        futs = {sym: _pool.submit(self.hub.yahoo.meta, sym) for _, sym, *_ in spec}
        got = {}
        for sym, f in futs.items():
            try:
                got[sym] = f.result(timeout=10)
            except Exception:
                got[sym] = None
        return got

    def _daily(self, region: str, symbol: str, today: str) -> list[float]:
        try:
            return _closes_of(self.hub.chart(region, symbol, "3m", "1d").get("candles"), today)
        except Exception:
            return []

    def _closes_for(self, region: str, names: list[str], today: str, tag: str) -> dict[str, list[float]]:
        """Each symbol's completed sessions' closes, read once per `CLOSES_FRESH` (a day's closes don't change in a day)."""
        def read():
            futs = {n: _pool.submit(self._daily, region, n, today) for n in names}
            out = {}
            for n, f in futs.items():
                try:
                    out[n] = f.result(timeout=45)
                except Exception:
                    out[n] = []
            return out
        got, _ = self.closes.get((region, tag, today), read, 45.0)
        return got or {}

    def sector_names(self, region: str) -> list[str]:
        from ..rotation import CORE_IN, SECTORS
        if region == "IN":
            return sorted(CORE_IN | {"NIFTY OIL AND GAS", "NIFTY HEALTHCARE", "NIFTY CONSR DURBL", "NIFTY PVT BANK"})
        return list(SECTORS["US"]["members"])

    def _sector_today(self, region: str) -> dict[str, dict]:
        from ..rotation import US_NAMES
        names = self.sector_names(region)
        if region == "IN":
            if not self.hub._kite():
                return {}
            got = self.hub.kite.index_quotes([f"NSE:{n}" for n in names])
            return {n: got.get(f"NSE:{n}") or {} for n in names}
        got = self._quotes("US", names)
        return {US_NAMES.get(s, s): got.get(s) or {} for s in names}

    def sector_moves(self, region: str) -> dict | None:
        """The sector indices' day, as the table has it ({"up", "down", "unchanged", "of", "rows"} with change_pct and name):
        the one count the mood, the table and the AI's read are held to."""
        try:
            tab = sector_table(self._sector_today(region), {})
        except Exception as e:
            print("sector moves unavailable:", region, str(e)[:120])
            return None
        return tab and {**tab, "rows": [{"name": r["name"], "label": r["label"], "change_pct": r["change_pct"]} for r in tab["rows"]]}

    def _label(self, region: str):
        from ..rotation import _label
        return lambda n: _label(region, n, None)

    def _sectors(self, region: str, today: str, caps: dict[str, float]) -> tuple[dict | None, dict]:
        """The sector table with each sector's largest members' moves, and every quote read for it (the index movers reuse them)."""
        from .. import sector_members
        from ..rotation import US_NAMES
        try:
            now = self._sector_today(region)
        except Exception as e:
            print("sector table unavailable:", region, str(e)[:120])
            return None, {}
        if not now:
            return None, {}
        names = self.sector_names(region)
        per = SECTOR_MEMBERS[region]
        members = {n: (sector_members.IN.get(n) if region == "IN" else sector_members.US.get(n)) or [] for n in names}
        syms = [s for n in names for s in members[n][:per]]
        quotes = self._quotes(region, syms)
        nm = self._names(region)
        moves = {}
        for n in names:
            key = US_NAMES.get(n, n) if region == "US" else n
            rows = [{"symbol": s, "name": nm.get(s) or s, "change_pct": round(num(quotes[s].get("change_pct")), 2)} for s in members[n][:per]
                    if s in quotes and num(quotes[s].get("change_pct")) is not None]
            if rows:
                moves[key] = sorted(rows, key=lambda r: -abs(r["change_pct"] * (caps.get(r["symbol"]) or 1.0)))[:2]
        closes = self._closes_for(region, names, today, "sectors")
        closes = {US_NAMES.get(n, n): v for n, v in closes.items()} if region == "US" else closes      # the table is keyed by the sector's name
        return sector_table(now, closes, moves, self._label(region)), quotes

    def _names(self, region: str) -> dict[str, str]:
        try:
            from .. import screens
            return {r["symbol"]: short_name(r.get("name") or r["symbol"]) for r in screens.load_index(region).get("rows") or []}
        except Exception:
            return {}

    def _caps(self, region: str) -> dict[str, float]:
        try:
            from .. import screens
            return {r["symbol"]: float(r["market_cap"]) for r in screens.load_index(region).get("rows") or [] if num(r.get("market_cap"))}
        except Exception:
            return {}

    def _movers(self, region: str, caps: dict[str, float], levels: list[dict], have: dict) -> dict | None:
        name, _sym = INDEX_SYMBOL[region]
        lvl = next((i for i in levels if i.get("name") == name), None)
        if not lvl or not num(lvl.get("prev_close")):
            return None
        names = {}
        total = None
        if region == "IN":
            from .. import universes
            syms = next((p["symbols"] for p in universes.PRESETS["IN"] if p["id"] == "nifty50"), [])
        else:
            from .. import universes
            sp = set(universes.sp500_symbols())
            ranked = sorted((s for s in caps if s in sp), key=lambda s: -caps[s])
            if len(ranked) < 0.9 * len(sp):                  # too few of the index's companies have a value to weigh by
                return None
            total = sum(caps[s] for s in ranked)
            syms = ranked[:US_MOVERS_FROM]
            try:
                names = universes.sp500_names()
            except Exception:
                names = {}
        quotes = {**have, **self._quotes(region, [s for s in syms if s not in have])}
        nm = self._names(region)
        members = [{"symbol": s, "name": nm.get(s) or short_name(names.get(s) or s), "market_cap": caps.get(s), "change_pct": (quotes.get(s) or {}).get("change_pct")}
                   for s in syms]
        return index_movers(members, lvl["prev_close"], name, total=total)

    def _flows(self) -> dict | None:
        try:
            from .. import positioning
            cash = positioning.cash_today()
            since = (datetime.now(timezone.utc) - timedelta(days=21)).date().isoformat()
            return flows_block(cash, positioning.history("cash", since))
        except Exception as e:
            print("flows unavailable:", str(e)[:100])
            return None

    def _calendar(self, region: str, today: date, caps: dict[str, float]) -> dict:
        out = {"results": [], "ipos": [], "events": []}
        end = today + timedelta(days=6)
        try:
            from .. import results
            rank = {s: i for i, s in enumerate(sorted(caps, key=lambda s: -caps[s]))}
            rows = [r for r in results.between(region, today, end) if r["symbol"] in rank and rank[r["symbol"]] < 100]
            rows.sort(key=lambda r: (r["date"], rank[r["symbol"]]))
            out["results"] = [{"symbol": r["symbol"], "name": short_name(r.get("name") or r["symbol"]), "date": r["date"], "purpose": r.get("purpose")} for r in rows[:6]]
        except Exception as e:
            print("results calendar unavailable:", str(e)[:100])
        try:
            from .. import ipo
            now = datetime.now(timezone.utc)
            for r in ipo.load(region).get("rows") or []:
                try:
                    stage = ipo.stage_of(r, now)
                except Exception:
                    continue
                if stage == "open":
                    out["ipos"].append({"name": r.get("name") or r.get("symbol"), "close": r.get("close"), "low": r.get("low"), "high": r.get("high"), "stage": stage})
            out["ipos"] = out["ipos"][:5]
        except Exception as e:
            print("ipo list unavailable:", str(e)[:100])
        try:
            from .. import market_events
            kinds = ("rbi", "india", "us", "budget") if region == "IN" else ("us", "rbi")
            evs = [e for e in market_events.events(today, frm=today, to=end) if e.get("kind") in kinds]
            if region == "US":
                evs = [e for e in evs if e.get("kind") == "us"]
            out["events"] = [{"date": e["date"], "time": e.get("time"), "title": e["title"], "kind": e["kind"]} for e in evs[:6]]
        except Exception as e:
            print("events unavailable:", str(e)[:100])
        return out

    # -- the whole payload --
    def build(self, region: str) -> dict:
        from .. import breadth, breadth_live
        from .company import market_open, market_today
        today_s = market_today(region)
        today = date.fromisoformat(today_s)
        levels, at = self.hub.indices_now(region, wait=8.0)
        levels = levels or []
        caps = self._caps(region)
        # every network read below starts now, side by side; each part that fails is left out and says so
        f_risk = _pool.submit(self._metas, RISK[region] + GLOBAL[region])
        f_flows = _pool.submit(self._flows) if region == "IN" else None
        f_cal = _pool.submit(self._calendar, region, today, caps)
        name, sym = INDEX_SYMBOL[region]
        f_typ = _pool.submit(self._closes_for, region, [sym], today_s, "index")
        sectors, have = self._sectors(region, today_s, caps)
        movers = None
        try:
            movers = self._movers(region, caps, levels, have)
        except Exception as e:
            print("index movers unavailable:", region, str(e)[:100])
        group = BREADTH_GROUP[region]
        try:
            vt = breadth.view(group, "3m", full=False, brief=True)
            live = None
            if region in breadth_live.LIVE_REGIONS:
                lv = breadth_live.settled(breadth_live.view(group, ready=self.hub._kite()), (vt.get("today") or {}).get("day"))
                live = (lv or {}).get("latest") if lv and lv.get("state") in ("live", "final") else None
            b = breadth_block(vt.get("today"), live, vt["group"]["name"], today_s)
        except Exception as e:
            print("breadth unavailable:", region, str(e)[:100])
            b = None
        typ = typical_move((f_typ.result(timeout=60) or {}).get(sym) or [])
        lvl = next((i for i in levels if i.get("name") == name), None)
        cmp = compare_today(name, (lvl or {}).get("change_pct"), typ)
        try:
            metas = f_risk.result(timeout=30)
        except Exception:
            metas = {}
        risk = quote_rows(RISK[region], metas, today_s)
        glob = quote_rows(GLOBAL[region], metas, today_s)
        flows = None
        try:
            flows = f_flows.result(timeout=30) if f_flows else None
        except Exception:
            flows = None
        try:
            cal = f_cal.result(timeout=30)
        except Exception:
            cal = {"results": [], "ipos": [], "events": []}
        p = {"region": region, "is_open": market_open(region), "today": today_s,
             "levels_at": max((i["at"] for i in levels if i.get("at")), default=None),
             "compare": cmp, "breadth": b, "sectors": sectors, "movers": movers, "flows": flows,
             "risk": {"rows": risk} if risk else None, "global": {"rows": glob} if glob else None,
             "calendar": cal if any(cal.values()) else None}
        p["headline"] = headline_of(levels, sectors, cmp)
        p["lines"] = lines_of(p)
        bad = verify(p)
        if bad:                           # a line the tables don't bear out is never shown (the tables still are)
            print("mood lines dropped:", bad[:3])
            p["headline"], p["lines"] = "", []
        return p

    def get(self, region: str, wait: float = 20.0) -> tuple[dict | None, float | None]:
        from .company import market_open
        self.payloads.fresh_for = FRESH_OPEN if market_open(region) else FRESH_SHUT
        return self.payloads.get(region, lambda: self.build(region), wait)


_SUFFIX = re.compile(r"\s+(?:limited|ltd\.?|inc\.?|corporation|corp\.?|company|co\.?|plc|holdings?)\s*$", re.I)


def short_name(name: str) -> str:
    """A company's name for a table cell: the legal ending off ("Reliance Industries Limited" -> "Reliance Industries")."""
    n = " ".join(str(name or "").split())
    return _SUFFIX.sub("", n).strip(" ,.") or n
