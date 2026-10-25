"""Corporate actions: dividends, bonus issues, splits, consolidations, buybacks, rights issues and demergers, with
their ex-dates and record dates, in India and the US; what they mean for the user's own holdings; and the messages to
the people who track the company.

India: the exchange's corporate-actions list (one call for the whole market, for a window of ex-dates), and each
company's own history from the same list (or BSE's, for companies listed only on BSE). When the list is down,
tracked companies' dividend, bonus and split notices are read from their announcements, with the record date as
the ex-date (India settles T+1, so the two are the same day).
US: the dividends and splits in each company's price history, for the whole US universe (the S&P 500 and StratLab's own
groups, one company at a time at a gentle pace) as well as the tracked ones. A price history holds ex-dates that have
already happened, so the dividends declared with an ex-date ahead come from the US market calendar, a day at a time
for the next four weeks (DE-028); splits ahead aren't in either.

Each region's calendar is stored as corpact:cal:<region>, a rolling window from four weeks back to two months
ahead; one company's history (three years) as corpact:hist:<region>:<symbol>. Facts only: the action as the company
announced it and the dates. Never a view on it."""
import json
import math
import re
import threading
import time
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import db, leader, results, run_marks
from .intel.net import SourceError, TTLCache
from .results import REGIONS, TZ, dates_in, local_today, parse_day

KEY = "corpact:cal:"                 # corpact:cal:<region> = {"at": ISO time, "rows": [...]}
HIST = "corpact:hist:"               # corpact:hist:<region>:<symbol> = {"at": ISO time (UTC), "rows": [...]}
ALERT_KEY = "corpactalert:"          # corpactalert:<uid> = "off" when someone turned the messages off
AHEAD_DAYS = 60                      # how far ahead each refresh asks for
BEHIND_DAYS = 7                      # ...and how far back
KEEP_DAYS = 28                       # past actions stay in the calendar this long
RECENT_DAYS = 14                     # ...and are listed on the page this long
HIST_DAYS = 3 * 366                  # one company's history goes back this far
HIST_MAX_AGE = 20 * 3600             # a stored history older than this is fetched again when asked for
MAX_ROWS = 4000
MAX_LOOKUPS = 80                     # per-company lookups in one refresh
US_AHEAD_DAYS = 28                   # US: the market calendar's declared dividends are read this far ahead (a day at a time)
UNIVERSE_AT = "06:20"                # US, local time: the whole universe's histories are read (several minutes), after the tracked refresh
UNIVERSE_PACE = 0.8                  # seconds between two companies: a steady pace under the price source's limit
UNIVERSE_GIVE_UP = 6                 # this many busy answers in a row: the read stops and the stored rows stay
NOTE = "Dates and amounts as the companies announced them. Not investment advice."
CUR = {"IN": "₹", "US": "$"}
KINDS = ("dividend", "bonus", "split", "buyback", "rights", "demerger")
_lock = threading.Lock()
_empty = TTLCache(max_items=2000)    # (region, symbol) looked up from a company page with nothing found


# ---------- reading what the exchange wrote ----------
_RS = r"(?:rs|re|inr|₹|\$|usd)\.?"
_NUM = r"(\d+(?:,\d{3})*(?:\.\d+)?)"
_AMOUNT = re.compile(_RS + r"\s*[-–:/]?\s*(?:[-–]\s*)?" + _NUM, re.I)
_RATIO = re.compile(r"(\d{1,4})\s*:\s*(\d{1,4})")
_FROM_TO = re.compile(r"from\s*" + _RS + r"?\s*" + _NUM + r".{0,40}?\bto\s*" + _RS + r"?\s*" + _NUM, re.I)
_PARTS = re.compile(r"\s+and\s+|\s*;\s*|\s*&\s*|/(?!-)", re.I)


def _f(s) -> float | None:
    try:
        v = float(str(s).replace(",", ""))
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def money(v: float, cur: str = "₹") -> str:
    """₹11, ₹5.50, $0.26: whole amounts without decimals."""
    if abs(v - round(v)) < 1e-9:
        return f"{cur}{v:,.0f}"
    return f"{cur}{v:,.2f}" if abs(v - round(v, 2)) < 1e-9 else f"{cur}{v:,.4f}".rstrip("0")


def _n(v: float) -> str:
    return f"{v:g}"


_DIST = re.compile(r"distribution\W*" + _RS + r"\s*" + _NUM + r"\s*per unit\s+consists?\s+of\s+(.*)$", re.I)
_DIST_PART = re.compile(_RS + r"\s*" + _NUM + r"\s*per unit\s+as\s+([a-z][a-z ]*?)\s*(?=/|,|;|$)", re.I)


def distribution(text: str, cur: str = "₹") -> dict | None:
    """A trust's distribution with its parts (DE-029): "Distribution - Rs 2.75 Per Unit Consist Of Re 0.60821 Per Unit
    As Interest/ Re 0.34940 Per Unit As Dividend/ Rs 1.78940 Per Unit As Capital Repayment/Re 0.00299 Per Unit As Other
    Income" is one payment of ₹2.75 a unit, not a distribution and a separate ₹0.3494 dividend. None for other text."""
    m = _DIST.search(re.sub(r"\s+", " ", str(text or ""))[:400])
    total = _f(m.group(1)) if m else None
    if not total or total <= 0:
        return None
    parts = [{"label": p.group(2).strip().lower(), "amount": _f(p.group(1))} for p in _DIST_PART.finditer(m.group(2))]
    parts = [p for p in parts if p["amount"] is not None]
    said = ", ".join(f"{money(p['amount'], cur)} {p['label']}" for p in parts)
    return {"kind": "dividend", "sub": "distribution", "label": "Distribution", "amount": total, "ratio": None, "factor": None, "premium": None,
            "parts": parts, "short": f"Distribution {money(total, cur)} a unit",
            "text": f"Distribution {money(total, cur)} a unit" + (f": {said}" if said else "")}


def parse_purpose(text: str, face_value: float | None = None, cur: str = "₹") -> list[dict]:
    """The actions in the exchange's purpose text: "Interim Dividend - Rs 9 Per Share", "Bonus 1:1", "Face Value
    Split (Sub-Division) - From Rs 10/- Per Share To Re 1/- Per Share", "Rights 1:5 @ Premium Rs 100/-", "Buy Back".
    Each is {kind, sub, label, text, short, amount, ratio, factor, premium}; anything else (meetings, interest
    payments, redemptions) is left out. A trust's distribution that lists its parts is one action (see distribution)."""
    whole = distribution(text, cur)
    if whole:
        return [whole]
    out = []
    for seg in _PARTS.split(re.sub(r"\s+", " ", str(text or ""))[:400]):
        seg = seg.strip(" -–:,.")
        low = seg.lower()
        if not seg:
            continue
        a = {"kind": None, "sub": "", "label": "", "text": "", "short": "", "amount": None, "ratio": None, "factor": None, "premium": None}
        if re.search(r"dividend|distribution", low):
            word = next((w for w in ("interim", "final", "special") if w in low), "")
            amt = _AMOUNT.search(seg)
            amount = _f(amt.group(1)) if amt else None
            pct = re.search(r"(\d+(?:\.\d+)?)\s*%", seg)
            if amt and pct and re.search(r"(?:face\s*value|\bf\.?\s?v\.?)(?:\s+of)?\W*$", seg[:amt.start()], re.I):
                # "50% (FV Rs 10)": the rupee figure is the face value the percentage is of, not the dividend
                face_value, amount = amount, None
            if amount is None and pct and face_value:
                amount = round(face_value * float(pct.group(1)) / 100, 4)
            label = "Distribution" if "distribution" in low and "dividend" not in low else f"{word.title()} dividend" if word else "Dividend"
            a.update(kind="dividend", sub=word or label.lower(), label=label, amount=amount if amount and amount > 0 else None,
                     text=f"{label} {money(amount, cur)} a {'unit' if 'unit' in low else 'share'}" if amount and amount > 0 else label)
            a["short"] = a["text"]
        elif "bonus" in low:
            m = _RATIO.search(seg)
            n, h = (int(m.group(1)), int(m.group(2))) if m else (0, 0)
            if n > 0 and h > 0:
                a.update(kind="bonus", sub=f"{n}:{h}", label=f"Bonus {n}:{h}", ratio=[n, h], factor=(n + h) / h, short=f"{n}:{h} bonus",
                         text=f"Bonus {n}:{h} ({n} new share{'s' if n != 1 else ''} for every {h} held)")
            else:
                a.update(kind="bonus", label="Bonus issue", text="Bonus issue", short="bonus issue")
        elif re.search(r"split|sub[- ]?division|consolidation", low):
            m = _FROM_TO.search(seg)
            fv_from, fv_to = (_f(m.group(1)), _f(m.group(2))) if m else (None, None)
            if fv_from and fv_to and fv_from != fv_to:
                factor = fv_from / fv_to
                if factor > 1:
                    a.update(kind="split", sub=f"{_n(fv_from)}-{_n(fv_to)}", label="Split", factor=factor, short=f"split ({_n(factor)} for 1)",
                             text=f"Split: face value {money(fv_from, cur)} to {money(fv_to, cur)} ({_n(factor)} shares for each one held)")
                else:
                    a.update(kind="split", sub=f"{_n(fv_from)}-{_n(fv_to)}", label="Consolidation", factor=factor, short=f"consolidation (1 for {_n(1 / factor)})",
                             text=f"Consolidation: face value {money(fv_from, cur)} to {money(fv_to, cur)} (1 share for every {_n(1 / factor)} held)")
            else:
                label = "Consolidation" if "consolidation" in low else "Split"
                a.update(kind="split", label=label, text=label, short=label.lower())
        elif re.search(r"\brights?\b", low):
            m = _RATIO.search(seg)
            prem = re.search(r"premium\s*(?:of\s*)?" + _RS + r"?\s*" + _NUM, seg, re.I)
            premium = _f(prem.group(1)) if prem else None
            if m and int(m.group(1)) > 0 and int(m.group(2)) > 0:
                n, h = int(m.group(1)), int(m.group(2))
                a.update(kind="rights", sub=f"{n}:{h}", label=f"Rights {n}:{h}", ratio=[n, h], premium=premium,
                         text=f"Rights issue {n}:{h} ({n} new share{'s' if n != 1 else ''} offered for every {h} held)"
                              + (f", at a premium of {money(premium, cur)}" if premium else ""))
            else:
                a.update(kind="rights", label="Rights issue", text="Rights issue", premium=premium)
            a["short"] = a["label"].lower()
        elif re.search(r"buy\s*-?\s*back", low):
            m = re.search(r"(?:at|@|price)\s*(?:of\s*)?" + _RS + r"\s*" + _NUM, seg, re.I)
            price = _f(m.group(1)) if m else None
            a.update(kind="buyback", label="Buyback", short="buyback", amount=price,
                     text=f"Buyback at {money(price, cur)} a share" if price else "Buyback")
        elif re.search(r"demerger|spin[- ]?off|scheme of arrangement", low):
            a.update(kind="demerger", label="Demerger", text="Demerger" if "demerger" in low else seg[:80], short="demerger")
        if a["kind"]:
            out.append(a)
    return out


def row(region: str, symbol: str, action: dict, ex: date, *, record: date | None = None, name=None, purpose="", src="exchange") -> dict:
    """One action on one company as a calendar row. The id stays the same when the feed is read again."""
    symbol = symbol.upper()
    return {"id": f"{symbol}|{action['kind']}|{ex.isoformat()}|{action.get('sub') or ''}"[:80], "region": region, "symbol": symbol,
            "name": name or None, "kind": action["kind"], "sub": action.get("sub") or "", "label": action["label"], "text": action["text"], "short": action.get("short") or action["label"],
            "amount": action.get("amount"), "ratio": action.get("ratio"), "factor": action.get("factor"), "premium": action.get("premium"),
            "currency": "INR" if region == "IN" else "USD", "ex_date": ex.isoformat(), "record_date": record.isoformat() if record else None,
            "purpose": str(purpose or "")[:200], "src": src, **({"parts": action["parts"]} if action.get("parts") else {})}


def is_special(d: dict) -> bool:
    """Whether a dividend row is a special dividend: by its kind's detail ("sub"), and for a row stored before rows kept
    it, by its label or id (DD-014: TCS's ₹46 special was counted in its yield without a word, the stored rows having no
    "sub")."""
    return d.get("sub") == "special" or str(d.get("label") or "").lower().startswith("special") or str(d.get("id") or "").endswith("|special")


def _rows(region, symbol, purpose, ex, record, name, fv=None, src="exchange") -> list[dict]:
    return [row(region, symbol, a, ex, record=record, name=name, purpose=purpose, src=src) for a in parse_purpose(purpose, fv, CUR[region])]


def india_rows(raw: list) -> list[dict]:
    """The exchange's corporate-actions rows (symbol, company, purpose, ex-date, record date, face value)."""
    out = []
    for r in raw if isinstance(raw, list) else []:
        if not isinstance(r, dict):
            continue
        sym = str(r.get("symbol") or "").strip().upper()
        purpose = str(r.get("subject") or r.get("purpose") or "").strip()
        rec = parse_day(r.get("recDate"))
        ex = parse_day(r.get("exDate")) or rec
        if not sym or not ex or not re.fullmatch(r"[A-Z0-9&\-._]{1,20}", sym):
            continue
        out += _rows("IN", sym, purpose, ex, rec, str(r.get("comp") or "").strip() or None, _f(r.get("faceVal")))
    return out


def bse_rows(raw: list, symbol: str) -> list[dict]:
    """BSE's corporate-actions rows for one company (Purpose, Ex_date, RD_Date), under the app's symbol for it."""
    out = []
    for r in raw if isinstance(raw, list) else []:
        if not isinstance(r, dict):
            continue
        rec = parse_day(r.get("RD_Date"))
        ex = parse_day(r.get("Ex_date")) or rec
        if not ex:
            continue
        out += _rows("IN", symbol, str(r.get("Purpose") or "").strip(), ex, rec,
                     str(r.get("long_name") or r.get("short_name") or "").strip() or None)
    return out


def us_rows(symbol: str, events: dict) -> list[dict]:
    """A US company's dividends and splits from its price history (ex-dates only: no record date is given)."""
    out = []
    for d in (events or {}).get("dividends") or []:
        ex, amt = parse_day(d.get("date")), _f(d.get("amount"))
        if ex and amt and amt > 0:
            out.append(row("US", symbol, {"kind": "dividend", "sub": "dividend", "label": "Dividend", "text": f"Dividend {money(amt, '$')} a share",
                                          "short": f"Dividend {money(amt, '$')} a share", "amount": round(amt, 4)}, ex, src="price history"))
    for s in (events or {}).get("splits") or []:
        ex, num, den = parse_day(s.get("date")), _f(s.get("numerator")), _f(s.get("denominator"))
        if not ex or not num or not den or num <= 0 or den <= 0 or num == den:
            continue
        f = num / den
        if not split_ratio(num, den):
            # DE-030: CTVA "Split 6665-for-1000" on 1 Oct was the price history's adjustment for its separation, not a
            # split: no share count changes, so it is never applied to a holding (adjusts() reads only bonus and split)
            text = (f"The price history was adjusted {f:.4g} for 1 on this day. That isn't a split ratio (a split is a ratio of "
                    "small whole numbers); a spin-off or a large special payment is recorded this way. The company's filing says which.")
            out.append(row("US", symbol, {"kind": "demerger", "sub": f"adj{_n(num)}:{_n(den)}", "label": "Price adjustment", "text": text,
                                          "short": "price adjustment"}, ex, src="price history"))
            continue
        label = "Split" if f > 1 else "Reverse split"
        text = f"{label} {_n(num)}-for-{_n(den)}"
        out.append(row("US", symbol, {"kind": "split", "sub": f"{_n(num)}:{_n(den)}", "label": label, "text": text, "short": text.lower(),
                                      "factor": f}, ex, src="price history"))
    return out


def split_ratio(num: float, den: float) -> bool:
    """A ratio a company splits (or reverse-splits) its shares by: whole numbers that, reduced, are both 100 or less
    (2-for-1, 3-for-2, 1-for-10, 1-for-50). The price history also records a spin-off as a "split" by the price's
    drop, which reduces to nothing like that (6665-for-1000 is 1333-for-200)."""
    if abs(num - round(num)) > 1e-9 or abs(den - round(den)) > 1e-9:
        return False
    a, b = int(round(num)), int(round(den))
    g = math.gcd(a, b) or 1
    return a // g <= 100 and b // g <= 100


def calendar_dividends(raw: list, universe: set[str], names: dict | None = None) -> list[dict]:
    """The dividends companies have declared with an ex-date ahead, from the US market calendar (DE-028), for the
    companies the US list covers. The row's id is the price history's for the same dividend, so the history's row
    replaces it once the ex-date has passed."""
    names = names or {}
    out = []
    for d in raw or []:
        sym, ex, amt = str(d.get("symbol") or "").upper(), parse_day(d.get("ex_date")), _f(d.get("amount"))
        if not sym or sym not in universe or not ex or not amt or amt <= 0:
            continue
        r = row("US", sym, {"kind": "dividend", "sub": "dividend", "label": "Dividend", "text": f"Dividend {money(amt, '$')} a share",
                            "short": f"Dividend {money(amt, '$')} a share", "amount": round(amt, 4)}, ex,
                record=parse_day(d.get("record_date")), name=names.get(sym) or results.us_name(d.get("name")),
                purpose=f"Declared {d['declared']}" if d.get("declared") else "", src="market calendar")
        if d.get("pay_date"):
            r["pay_date"] = d["pay_date"]
        out.append(r)
    return out


def us_declared(sources: dict, universe: set[str], today: date, problems: list) -> tuple[list[dict], set[str]]:
    """Every declared dividend going ex from today to US_AHEAD_DAYS ahead, and the days the calendar didn't answer."""
    from . import universes
    cal, rows, unread = sources.get("cal"), [], set()
    if cal is None:
        return rows, unread
    names = universes.sp500_names()
    for d in results.weekdays(today, today + timedelta(days=US_AHEAD_DAYS)):
        try:
            rows += calendar_dividends(cal.dividends(d), universe, names)
        except (SourceError, AttributeError) as e:
            unread.add(d.isoformat())
            problems.append(f"calendar {d.isoformat()}: {str(e)[:100]}")
    return rows, unread


def from_announcements(symbol: str, items: list[dict], today: date) -> list[dict]:
    """Dividends, bonus issues and splits read from a company's own notices that name a record date, for when the
    exchange's list is down. In India the ex-date is the record date (T+1 settlement)."""
    out = []
    for i in items or []:
        hay = f"{i.get('subject') or ''}. {i.get('text') or ''}"
        rd = re.search(r"record date", hay, re.I)
        if not rd or not re.search(r"dividend|bonus|split|sub-division", hay, re.I):
            continue
        filed = parse_day(str(i.get("at") or "")[:10])
        if not filed or (today - filed).days > 45:
            continue
        day = next((d for d in dates_in(hay[rd.start():]) if filed <= d <= filed + timedelta(days=90)), None)
        if not day or day < today - timedelta(days=KEEP_DAYS):
            continue
        for a in parse_purpose(hay[:rd.start()] or hay)[:2]:
            if a["kind"] in ("dividend", "bonus", "split"):
                r = row("IN", symbol, a, day, record=day, purpose=str(i.get("subject") or "")[:200], src="announcement")
                r["url"] = i.get("url") if str(i.get("url") or "").startswith("https://") else None
                out.append(r)
    seen, uniq = set(), []
    for r in out:                    # the newest notice wins (items come newest first)
        if r["id"] not in seen:
            seen.add(r["id"])
            uniq.append(r)
    return uniq


# ---------- storage ----------
CAL_MEMO_FOR = 60                    # seconds the parsed calendar is kept in memory for the pages that read it
_cal_memo: dict = {}                 # (region, id of the database client) -> (monotonic time read, the calendar as load() gives it)
_cal_memo_lock = threading.Lock()


def load_cached(region: str) -> dict:
    """load(), kept CAL_MEMO_FOR seconds for the company pages (a calendar of up to MAX_ROWS rows to read and parse on
    each); save() drops it. Read-modify-write paths use load()."""
    key = (region, id(db._client))      # (not db.sb(): that would connect where settings are read some other way)
    with _cal_memo_lock:
        hit = _cal_memo.get(key)
    if hit is not None and time.monotonic() - hit[0] < CAL_MEMO_FOR:
        cal = hit[1]
    else:
        cal = load(region)
        with _cal_memo_lock:
            _cal_memo[key] = (time.monotonic(), cal)
    return {**cal, "rows": list(cal["rows"])}


def forget_cached() -> None:
    with _cal_memo_lock:
        _cal_memo.clear()


def load(region: str) -> dict:
    cal = db.json_value(db.get_setting(KEY + region), {})
    cal = cal if isinstance(cal, dict) else {}
    return {"at": cal.get("at"), "universe_at": cal.get("universe_at"), "universe": cal.get("universe"),
            "rows": [r for r in cal.get("rows") or [] if isinstance(r, dict) and r.get("ex_date") and r.get("id")]}


def save(region: str, rows: list[dict], universe: int | None = None):
    """Store the calendar. `universe`: how many companies a whole-universe read covered (kept as it was when None)."""
    rows = sorted(rows, key=lambda r: (r["ex_date"], r["symbol"]))[:MAX_ROWS]
    now = datetime.now(ZoneInfo(TZ[region])).isoformat(timespec="minutes")
    doc = {"at": now, "rows": rows}
    if universe is not None:
        doc.update(universe_at=now, universe=universe)
    else:
        old = db.json_value(db.get_setting(KEY + region), {})
        doc.update({k: old.get(k) for k in ("universe_at", "universe") if old.get(k) is not None})
    try:
        db.set_setting(KEY + region, json.dumps(doc))
    finally:
        forget_cached()


def merge(old: list[dict], new: list[dict], frm: date, today: date, first: bool = False) -> list[dict]:
    """The stored rows from before the window just fetched, plus the fresh ones (which win inside the window, so a
    withdrawn action drops off). An action not seen before, with its ex-date still ahead, is marked `fresh` until
    its announcement message has gone out; nothing is marked on the very first build."""
    keep_from = (today - timedelta(days=KEEP_DAYS)).isoformat()
    prior = {r["id"]: r for r in old}
    out = {r["id"]: r for r in old if keep_from <= r["ex_date"] < frm.isoformat()}
    for r in new:
        p = prior.get(r["id"])
        if p is not None:
            r = {**r, "fresh": True} if p.get("fresh") else r
        elif not first and r["ex_date"] >= today.isoformat():
            r = {**r, "fresh": True}
        out[r["id"]] = r
    return list(out.values())


def prefetch(region: str, symbols) -> None:
    """The calendar and these companies' histories in one database read, for a page that goes through many holdings."""
    db.prefetch_settings([KEY + region] + [f"{HIST}{region}:{s.upper()}" for s in symbols])


def hist_load(region: str, symbol: str) -> dict:
    got = db.json_value(db.get_setting(f"{HIST}{region}:{symbol.upper()}"), {})
    got = got if isinstance(got, dict) else {}
    return {"at": got.get("at"), "rows": [r for r in got.get("rows") or [] if isinstance(r, dict) and r.get("ex_date") and r.get("id")]}


def hist_save(region: str, symbol: str, rows: list[dict]):
    db.set_setting(f"{HIST}{region}:{symbol.upper()}", json.dumps({"at": datetime.now(timezone.utc).isoformat(timespec="minutes"),
                                                                  "rows": sorted(rows, key=lambda r: r["ex_date"])[-200:]}))


def _stale(at: str | None) -> bool:
    try:
        return (datetime.now(timezone.utc) - datetime.fromisoformat(at)).total_seconds() > HIST_MAX_AGE
    except (TypeError, ValueError):
        return True


def fetch_history(region: str, symbol: str, sources: dict, today: date) -> list[dict]:
    """One company's actions over the last three years (and any ahead), straight from the feed."""
    symbol = symbol.upper()
    if region == "IN":
        where, raw = sources["in"].actions_of(symbol)
        rows = bse_rows(raw, symbol) if where == "bse" else [r for r in india_rows(raw) if r["symbol"] == symbol]
    else:
        rows = us_rows(symbol, sources["us"].events(symbol))
    frm = (today - timedelta(days=HIST_DAYS)).isoformat()
    return list({r["id"]: r for r in rows if r["ex_date"] >= frm}.values())


def history(region: str, symbol: str, sources: dict | None, today: date | None = None, fetch: bool = True,
            keep_empty: bool = True) -> list[dict]:
    """One company's stored history, fetched again first when it's older than a day (and fetching is allowed).
    A feed that fails leaves the stored history as it was. `keep_empty` False (any symbol someone types in): an
    empty answer is remembered in memory only, so made-up tickers can't fill the database."""
    today = today or local_today(region)
    got = hist_load(region, symbol)
    if fetch and sources is not None and _stale(got["at"]):
        if not keep_empty and not got["at"] and _empty.get((region, symbol.upper())):
            return []
        try:
            rows = fetch_history(region, symbol, sources, today)
            if rows or keep_empty or got["at"]:
                hist_save(region, symbol, rows)
            else:
                _empty.set((region, symbol.upper()), True, HIST_MAX_AGE)
            return rows
        except (SourceError, AttributeError, KeyError, TypeError) as e:
            print("corporate actions history:", symbol, str(e)[:120])
    return got["rows"]


def actions_for(region: str, symbol: str, sources: dict | None = None, today: date | None = None, fetch: bool = True,
                cal: list[dict] | None = None, keep_empty: bool = True) -> list[dict]:
    """Everything known for one company: its history and the calendar's rows, by ex-date."""
    symbol = symbol.upper()
    rows = {r["id"]: r for r in history(region, symbol, sources, today, fetch, keep_empty)}
    for r in (cal if cal is not None else load_cached(region)["rows"]):
        if r["symbol"] == symbol:
            rows[r["id"]] = r
    return sorted(rows.values(), key=lambda r: r["ex_date"])


def between(region: str, frm: date, to: date, symbols: set[str] | None = None) -> list[dict]:
    return [r for r in load_cached(region)["rows"] if frm.isoformat() <= r["ex_date"] <= to.isoformat()
            and (symbols is None or r["symbol"] in symbols)]


# ---------- refreshing ----------
def refresh(region: str, sources: dict, tracked: set[str] | None = None, today: date | None = None) -> dict:
    """Ask the feeds for the next two months of ex-dates (and the last week) and store the merged calendar.
    {"rows": n, "fresh": n, "problems": [...]}; the stored calendar is left alone when every source failed."""
    today = today or local_today(region)
    frm, to = today - timedelta(days=BEHIND_DAYS), today + timedelta(days=AHEAD_DAYS)
    tracked, rows, problems, whole = {s.upper() for s in tracked or ()}, [], [], False
    in_window = lambda r: frm.isoformat() <= r["ex_date"] <= to.isoformat()
    if region == "IN":
        feed = sources.get("in")
        try:
            rows += india_rows(feed.corporate_actions(datetime.combine(frm, datetime.min.time()), datetime.combine(to, datetime.min.time())))
            whole = bool(rows)           # two months with no action anywhere means the list didn't really answer
            if not whole:
                problems.append("The exchange's corporate-actions list came back empty.")
        except (SourceError, AttributeError, TypeError) as e:
            problems.append(str(e)[:160])
        code_of = getattr(feed, "code_of", lambda s: None)
        for sym in sorted(s for s in tracked if code_of(s))[:MAX_LOOKUPS]:      # listed only on BSE: BSE's own list
            try:
                rows += [r for r in fetch_history(region, sym, sources, today) if in_window(r)]
            except (SourceError, AttributeError, KeyError, TypeError) as e:
                problems.append(f"{sym}: {str(e)[:120]}")
        if not whole:
            for sym in sorted(s for s in tracked if not code_of(s))[:MAX_LOOKUPS]:
                try:
                    rows += from_announcements(sym, feed.announcements(sym, 60), today)
                except (SourceError, AttributeError) as e:
                    problems.append(f"{sym}: {str(e)[:120]}")
    else:
        for sym in sorted(tracked)[:MAX_LOOKUPS]:
            try:
                got = fetch_history(region, sym, sources, today)
                hist_save(region, sym, got)
                rows += [r for r in got if in_window(r)]
            except (SourceError, AttributeError, KeyError, TypeError) as e:
                problems.append(f"{sym}: {str(e)[:120]}")
        declared, unread = us_declared(sources, set(us_universe(tracked)), today, problems)
        have = {r["id"] for r in rows}
        rows += [r for r in declared if r["id"] not in have]
        if declared or unread:
            with _lock:
                old = load(region)["rows"]
            # the calendar's rows of the days it answered are its fresh list (a dividend withdrawn drops off); the other
            # days', and every company's own rows, stay as they were (merged below like any partial read)
            asked_days = {d.isoformat() for d in results.weekdays(today, today + timedelta(days=US_AHEAD_DAYS))} - unread
            stale = {r["id"] for r in old if r.get("src") == "market calendar" and r["ex_date"] in asked_days}
            rows += [r for r in old if r["id"] not in stale and r["id"] not in {x["id"] for x in rows}
                     and r["symbol"] not in tracked and r["ex_date"] >= frm.isoformat()]
            whole = bool(declared)
    if not whole and not rows and (problems or region == "IN"):
        return {"rows": None, "fresh": 0, "problems": problems}
    with _lock:
        cal = load(region)
        old, first = cal["rows"], not cal["at"]
        if not whole:                    # only some companies were asked: keep everyone else's rows as they were
            asked = {r["symbol"] for r in rows} | tracked
            rows += [r for r in old if r["symbol"] not in asked and r["ex_date"] >= frm.isoformat()]
        merged = merge(old, rows, frm, today, first)
        save(region, merged)
    return {"rows": len(merged), "fresh": sum(1 for r in merged if r.get("fresh")), "problems": problems}


def us_universe(tracked=()) -> list[str]:
    """Every US company the calendar covers: the S&P 500, StratLab's own groups and the companies people track."""
    from . import universes
    return sorted(set(universes.us_universe()) | {s.upper() for s in tracked})


def refresh_universe(sources: dict, tracked=(), today: date | None = None, pace: float | None = None, sleep=time.sleep,
                     symbols: list[str] | None = None) -> dict:
    """Read the dividends and splits of the whole US universe from each company's price history, one at a time, and
    store the calendar's window and each company's history. A company whose read fails keeps the rows it had; when
    the source is busy UNIVERSE_GIVE_UP times in a row the read stops with what it has. Names come from the S&P 500 list.
    {"rows", "read", "failed", "problems"}; the calendar is left alone when nothing could be read."""
    from . import universes
    region, today = "US", today or local_today("US")
    frm, to = today - timedelta(days=KEEP_DAYS), today + timedelta(days=AHEAD_DAYS)     # the whole kept window is read fresh
    names = universes.sp500_names()
    pace = UNIVERSE_PACE if pace is None else pace
    symbols = symbols if symbols is not None else us_universe(tracked)
    rows, done, problems, busy = [], set(), [], 0
    for i, sym in enumerate(symbols):
        if i and pace:
            sleep(pace)
        try:
            got = fetch_history(region, sym, sources, today)
        except SourceError as e:
            problems.append(f"{sym}: {str(e)[:100]}")
            busy = busy + 1 if getattr(e, "busy", False) else 0
            if busy >= UNIVERSE_GIVE_UP:
                break
            continue
        except (AttributeError, KeyError, TypeError) as e:
            problems.append(f"{sym}: {str(e)[:100]}")
            continue
        busy = 0
        done.add(sym)
        got = [{**r, "name": r.get("name") or names.get(sym)} for r in got]
        hist_save(region, sym, got)
        rows += [r for r in got if frm.isoformat() <= r["ex_date"] <= to.isoformat()]
    if not done:
        return {"rows": None, "read": 0, "failed": len(problems), "problems": problems[:10]}
    with _lock:
        cal = load(region)
        old, first = cal["rows"], not cal["at"]
        rows += [r for r in old if r["symbol"] not in done and r["ex_date"] >= frm.isoformat()]     # a failed company keeps its rows
        # a declared dividend still ahead isn't in any price history yet: the calendar's row stays (DE-028)
        have = {r["id"] for r in rows}
        rows += [r for r in old if r.get("src") == "market calendar" and r["ex_date"] >= today.isoformat() and r["id"] not in have]
        merged = merge(old, rows, frm, today, first)
        save(region, merged, universe=len(done))
    return {"rows": len(merged), "read": len(done), "failed": len(problems), "problems": problems[:10]}


def refresh_histories(region: str, sources: dict, symbols: set[str], today: date | None = None, budget: int = 150) -> int:
    """Fetch the stale histories of the companies people track or hold, up to `budget` of them. Stops at the first
    sign the feed is busy, so a rate limit isn't hammered."""
    n = 0
    for sym in sorted(symbols):
        if n >= budget:
            break
        if not _stale(hist_load(region, sym)["at"]):
            continue
        n += 1
        try:
            hist_save(region, sym, fetch_history(region, sym, sources, today or local_today(region)))
        except (SourceError, AttributeError, KeyError, TypeError) as e:
            if getattr(e, "busy", False):
                break
    return n


# ---------- what an action means for one holding ----------
def adjusts(a: dict) -> bool:
    """A bonus or split changes the number of shares and the price of each: the ones a holding is adjusted for."""
    f = a.get("factor")
    return a.get("kind") in ("bonus", "split") and isinstance(f, (int, float)) and math.isfinite(f) and f > 0 and abs(f - 1) > 1e-9


def _whole(q: float) -> bool:
    return abs(q - round(q)) < 1e-6


def adjusted(qty: float, avg: float | None, a: dict) -> tuple[float, float | None]:
    """The quantity and average price after a bonus or split. The total cost doesn't change, so the average is the
    old cost over the new quantity (the old average divided by the factor, unless a fraction was paid out). Whole shares only: a fractional entitlement is paid out in cash by the
    company, so it isn't added (a fractional holding is scaled exactly)."""
    f = a["factor"]
    if a.get("kind") == "bonus" and a.get("ratio"):
        n, h = a["ratio"]
        extra = qty * n / h
        new = qty + (math.floor(extra + 1e-9) if _whole(qty) else extra)
    else:
        new = qty * f
        new = math.floor(new + 1e-9) if _whole(qty) else new
    return round(new, 4), (round(qty * avg / new, 4) if avg and new > 0 else None)


def saved_day(stamp: str | None, today: date) -> str:
    """The India day a holdings file was saved on, from its stamp (UTC, as `updated_at` is kept), else today's: the day
    the quantity is as of. An action that went ex that day is not in it yet (the new shares are credited days after the
    ex-date, as holdings.saved_day says), so it is still offered; `_included` counts only the ones before it. A bare date
    is taken as it is."""
    s = str(stamp or "")
    try:
        t = datetime.fromisoformat(s) if len(s) > 10 else None
    except ValueError:
        t = None
    if t is None:
        return s[:10] or today.isoformat()
    return (t.astimezone(ZoneInfo("Asia/Kolkata")) if t.tzinfo else t).date().isoformat()


def _included(a: dict, item: dict, since: str) -> bool:
    """Whether the saved quantity already reflects an action: it was before the quantity was saved, or the user
    applied it, or said their broker's file already showed it."""
    return a["ex_date"] < since or a["id"] in (item.get("applied") or []) or a["id"] in (item.get("dismissed") or [])


def qty_before(day: str, item: dict, since: str, adj: list[dict]) -> float:
    """The shares held at the close before `day`, worked out from the saved quantity through the bonuses and splits
    in between, assuming no trades."""
    q = float(item["qty"])
    for a in adj:
        inc = _included(a, item, since)
        if not inc and a["ex_date"] < day:
            q *= a["factor"]
        elif inc and a["ex_date"] >= day:
            q /= a["factor"]
    return q


def pending(item: dict, actions: list[dict], since: str, today: date) -> list[dict]:
    """Bonuses and splits that went ex on or after the day the quantity was saved, not yet applied or set aside."""
    return [a for a in sorted(actions, key=lambda a: a["ex_date"]) if adjusts(a) and not _included(a, item, since)
            and a["ex_date"] <= today.isoformat()]


def _qty_text(q: float) -> str:
    return f"{q:,.0f}" if _whole(q) else f"{q:,.4f}".rstrip("0").rstrip(".")


def notice(item: dict, a: dict) -> dict:
    """The one-click offer for a bonus or split: what the quantity and average price become."""
    new_q, new_avg = adjusted(float(item["qty"]), item.get("avg"), a)
    avg = f", average price {money(new_avg)}" if new_avg else ""
    return {"symbol": item["symbol"], "id": a["id"], "kind": a["kind"], "label": a["label"], "text_action": a["text"], "ex_date": a["ex_date"],
            "from_qty": item["qty"], "to_qty": new_q, "from_avg": item.get("avg"), "to_avg": new_avg,
            "text": f"{item['symbol']} had a {a['short']} on {_day(a['ex_date'])}: your quantity is now {_qty_text(new_q)}{avg}."}


def holdings_view(items: list[dict], actions: dict[str, list[dict]], today: date, fallback_since: str | None) -> dict:
    """For the user's holdings: dividends ahead (amount a share × the shares that will be held on the ex-date), the
    dividends of the last twelve months (estimated with today's holding, worked back through any bonus or split),
    the bonuses and splits waiting to be applied, and the last adjustment of each stock (to undo)."""
    fallback = saved_day(fallback_since, today)
    year_ago = (today - timedelta(days=365)).isoformat()
    ahead, received, notices, undo = [], [], [], []
    from .tax_lots import fy_label, fy_of     # the financial-year slices use the tax tools' own rule: a dividend sits in the year of its record date
    this_fy = fy_of(today.isoformat())
    by_fy: dict[int, dict] = {y: {"fy": y, "label": fy_label(y), "total": 0.0, "count": 0} for y in (this_fy, this_fy - 1)}
    for i in items:
        acts = actions.get(i["symbol"]) or []
        since = str(i.get("since") or fallback)[:10]
        adj = sorted((a for a in acts if adjusts(a)), key=lambda a: a["ex_date"])
        for a in acts:
            if a.get("kind") != "dividend" or not a.get("amount"):
                continue
            q = qty_before(a["ex_date"], i, since, adj)
            line = {"symbol": i["symbol"], "label": a["label"], "ex_date": a["ex_date"], "record_date": a.get("record_date"),
                    "amount": a["amount"], "qty": round(q, 4), "total": round(q * a["amount"], 2)}
            if a["ex_date"] > today.isoformat():
                ahead.append(line)
            else:
                if a["ex_date"] >= year_ago:
                    received.append(line)
                if q > 0 and fy_of(a.get("record_date") or a["ex_date"]) in by_fy:
                    slot = by_fy[fy_of(a.get("record_date") or a["ex_date"])]
                    slot["total"] += line["total"]
                    slot["count"] += 1
        wait = pending(i, acts, since, today)
        if wait:
            n = notice(i, wait[0])
            if n["to_qty"] > 0:
                notices.append({**n, "more": len(wait) - 1})
        if i.get("adjusted"):
            last = i["adjusted"][-1]
            undo.append({"symbol": i["symbol"], "id": last.get("id"), "label": last.get("label") or "the adjustment",
                         "qty": last.get("qty"), "avg": last.get("avg")})
    ahead.sort(key=lambda x: (x["ex_date"], x["symbol"]))
    received.sort(key=lambda x: (x["ex_date"], x["symbol"]), reverse=True)
    return {"ahead": ahead, "ahead_total": round(sum(x["total"] for x in ahead), 2),
            "received": received, "received_total": round(sum(x["total"] for x in received), 2),
            "by_fy": [{**v, "total": round(v["total"], 2)} for _, v in sorted(by_fy.items(), reverse=True)],
            "notices": notices, "undo": undo, "today": today.isoformat()}


def apply(item: dict, a: dict) -> dict:
    """The holding after a bonus or split, remembering what it was so it can be undone."""
    q, avg = adjusted(float(item["qty"]), item.get("avg"), a)
    was = {"id": a["id"], "label": a["short"], "qty": item["qty"], "avg": item.get("avg")}
    out = {}
    if item.get("accts"):                 # each demat account gets its own entitlement; the quantity stays their sum
        out["accts"] = {k: adjusted(float(v), None, a)[0] for k, v in item["accts"].items()}
        q = round(sum(out["accts"].values()), 4)
        was["accts"] = item["accts"]
    return {**item, "qty": q, "avg": avg, **out, "applied": (item.get("applied") or []) + [a["id"]],
            "adjusted": ((item.get("adjusted") or []) + [was])[-10:]}


def dismiss(item: dict, a: dict) -> dict:
    """The user says their saved quantity already shows this action (their broker's file was made after it)."""
    return {**item, "dismissed": ((item.get("dismissed") or []) + [a["id"]])[-50:]}


def undo(item: dict) -> dict:
    """The holding as it was before its last adjustment."""
    if not item.get("adjusted"):
        return item
    last = item["adjusted"][-1]
    parts = last.get("accts")
    if not parts and item.get("accts"):   # an adjustment saved before parts were kept: scale them back
        f = last["qty"] / float(item["qty"]) if float(item["qty"]) else 1
        parts = {k: round(v * f, 4) for k, v in item["accts"].items()}
    return {**item, "qty": last["qty"], **({"accts": parts} if parts else {}), "avg": last.get("avg"), "adjusted": item["adjusted"][:-1],
            "applied": [x for x in item.get("applied") or [] if x != last.get("id")]}


# ---------- who wants the messages ----------
def alerts_on(uid: str) -> bool:
    return db.get_setting(ALERT_KEY + uid) != "off"


def set_alerts(uid: str, on: bool):
    db.set_setting(ALERT_KEY + uid, "on" if on else "off")


def can_alert(profile: dict) -> bool:
    from . import alerts
    return bool(profile.get("id")) and alerts_on(profile["id"]) and bool(alerts.jobs_for(results.quiet(profile), "", ""))


# ---------- the messages ----------
def _day(iso: str) -> str:
    try:
        d = date.fromisoformat(str(iso)[:10])
        return f"{d:%a} {d.day} {d:%b}"           # "Mon 5 Oct": day first, no leading zero, as the app writes dates
    except ValueError:
        return str(iso)


def next_trading_day(day: date, region: str = "IN") -> date:
    """The exchange's next session after `day`: weekends and its holidays skipped."""
    from .data.calendar import is_trading_day
    d = day + timedelta(days=1)
    for _ in range(14):
        if is_trading_day(region, d):
            break
        d += timedelta(days=1)
    return d


def announce_text(rows: list[dict]) -> str:
    parts = [f"{r['symbol']}: {r['text']}, ex-date {_day(r['ex_date'])}" for r in rows[:10]]
    more = f" and {len(rows) - 10} more" if len(rows) > 10 else ""
    return "New corporate actions for your stocks. " + "; ".join(parts) + more + ". " + NOTE


def eve_text(rows: list[dict], day: date) -> str:
    def when(r):
        return "tomorrow" if r["ex_date"] == (day + timedelta(days=1)).isoformat() else _day(r["ex_date"])
    parts = [f"{r['symbol']}: {r['text']}, ex-date {when(r)}" + (f" (record date {_day(r['record_date'])})" if r.get("record_date") else "")
             for r in rows[:10]]
    more = f" and {len(rows) - 10} more" if len(rows) > 10 else ""
    return ("Ex-dates coming up for your stocks. " + "; ".join(parts) + more
            + ". On the ex-date the shares start trading without the entitlement. " + NOTE)


# ---------- the schedule ----------
REFRESH_AT = {"IN": ("07:20", "18:40"), "US": ("06:10",)}
HISTORY_AT = {"IN": "07:40", "US": "06:30"}
EVE_AT = {"IN": "17:30", "US": "17:00"}


class Job:
    """Refreshes each region's calendar (twice a day for India), tells the people tracking a company when it
    announces an action, and the evening before an ex-date. Also keeps the histories of tracked and held companies
    fresh. Every run is marked in the database (the sending ones per recipient), so it happens once and a run a
    crash cut short resumes."""

    def __init__(self, sources, send=results.send, can_alert=can_alert):
        self.sources, self.send, self.can_alert = sources, send, can_alert
        self.last: dict[str, str] = {}
        self.status = {"last_run": None, "sent": 0, "last_error": None, "problems": []}
        self.universe_running, self.universe_retry = False, 0.0
        self.down: dict[str, str] = {}               # region -> why its last refresh read nothing (shown until one does)

    def start(self):
        threading.Thread(target=self._loop, daemon=True, name="corporate-actions").start()

    def _loop(self):
        while True:
            try:
                if leader.leading():      # another container leads: it runs this pass
                    self.tick(datetime.now(ZoneInfo("UTC")))
            except Exception as e:
                self.status["last_error"] = str(e)[:200]
                print("corporate actions:", e)
            time.sleep(300)

    def due(self, name: str, now: datetime, region: str, at: str) -> date | None:
        """The local day when `name` is due (at or after `at`) and hasn't run that day."""
        local = now.astimezone(ZoneInfo(TZ[region]))
        mark = local.strftime("%Y-%m-%d")
        if local.strftime("%H:%M") < at or self.last.get(name) == mark:
            return None
        if db.get_setting(f"corpactjob:{name}") == mark:          # already ran (before a restart)
            self.last[name] = mark
            return None
        self.last[name] = mark
        db.set_setting(f"corpactjob:{name}", mark)
        return local.date()

    def claim(self, name: str, now: datetime, region: str, at: str):
        """Like due(), for a run that sends: (local day, run marker), or (None, None) when it isn't due, is done or is
        being worked on. The marker records each recipient, so a run a crash cut short resumes without doubling."""
        local = now.astimezone(ZoneInfo(TZ[region]))
        mark = local.strftime("%Y-%m-%d")
        if local.strftime("%H:%M") < at or self.last.get(name) == mark:
            return None, None
        st = run_marks.status(f"corpactjob:{name}", mark)
        if st == "done":                                    # already ran (before a restart)
            self.last[name] = mark
        run = run_marks.claim(f"corpactjob:{name}", mark) if st is None else None
        return (local.date(), run) if run else (None, None)

    def tick(self, now: datetime) -> int:
        sent, ran = 0, False
        who = lambda: results.trackers(now=now)      # shared with the results job: read when a run needs it, and then once an hour
        for region in REGIONS:
            for at in REFRESH_AT[region]:
                day, run = self.claim(f"refresh-{region}-{at}", now, region, at)
                if day:
                    out = self.refresh(region, who(), day)
                    ran = True
                    if out["rows"] is None:      # every feed failed: not done, so the slot is resumed once its beat is stale
                        continue
                    sent += self.announce(region, day, who, run)
                    run.done()
            if region == "US" and self._universe_due(now):
                self.start_universe(who())
                ran = True
            day = self.due(f"history-{region}", now, region, HISTORY_AT[region])
            if day:
                refresh_histories(region, self.sources(), {s for (r, s) in who() if r == region}, day)
                ran = True
            day, run = self.claim(f"eve-{region}", now, region, EVE_AT[region])
            if day:
                sent, ran = sent + self.eve(region, day, who, run), True
                run.done()
        if ran:
            self.status.update(last_run=now.isoformat(), sent=sent, last_error=next(iter(self.down.values()), None))
            from . import job_status
            job_status.keep("corp", self)          # Admin shows this run after a restart too
        return sent

    def _universe_due(self, now: datetime) -> bool:
        """The whole US universe is read once a day from UNIVERSE_AT, and at the first chance when it never has been
        (a failed first read is tried again half an hour later)."""
        if self.universe_running or time.time() < self.universe_retry:
            return False
        if load("US").get("universe_at") is None:
            return True
        return self.due("universe-US", now, "US", UNIVERSE_AT) is not None

    def start_universe(self, who: dict, day: date | None = None, wait: bool = False):
        """Read the US universe in the background (it takes minutes), so the job's other checks go on meanwhile."""
        self.universe_running = True

        def work():
            try:
                out = refresh_universe(self.sources(), {s for (r, s) in who if r == "US"}, day)
                self.status["universe"] = {k: out[k] for k in ("rows", "read", "failed")}
                if not out["read"]:
                    self.universe_retry = time.time() + 1800
                self.status["problems"] = out["problems"][:10]
            except Exception as e:
                self.universe_retry = time.time() + 1800
                print("corporate actions universe:", str(e)[:160])
            finally:
                self.universe_running = False
        t = threading.Thread(target=work, daemon=True, name="corp-actions-universe")
        t.start()
        if wait:
            t.join()

    def refresh(self, region: str, who: dict | None = None, day: date | None = None) -> dict:
        who = who if who is not None else results.trackers()
        out = refresh(region, self.sources(), {s for (r, s) in who if r == region}, day)
        self.status["problems"] = out["problems"][:10]
        if out["rows"] is None:                      # no feed answered: Admin says so, not "OK"
            self.down[region] = f"{region}: {(out['problems'] or ['no feed answered'])[0]}"[:200]
        else:
            self.down.pop(region, None)
        self.status["last_error"] = next(iter(self.down.values()), None)
        return out

    def _send_each(self, per_user: dict[str, list[dict]], subject, text, url: str, run) -> int:
        sent = 0
        for uid, rows in per_user.items():
            if run.seen(uid):
                continue
            run.beat()
            try:
                profile = db.get_profile(uid)
                if not profile or not self.can_alert(profile):
                    continue
                run.record(uid)                # before the send: a kill in between drops one, never doubles
                self.send(profile, subject(rows), text(rows), url)
                sent += 1
            except Exception as e:             # one person's failure doesn't stop the rest
                print("corporate actions message failed:", uid, str(e)[:160])
        return sent

    def announce(self, region: str, day: date, who, run) -> int:
        """One message per person for the actions newly announced on their stocks; then the actions are unmarked.
        `who`: the trackers map, or a function that gives it (read only when there is something to tell)."""
        fresh = [r for r in load(region)["rows"] if r.get("fresh")]
        if not fresh:
            return 0
        who = results._get(who)
        per_user: dict[str, list[dict]] = {}
        for r in sorted(fresh, key=lambda r: (r["ex_date"], r["symbol"])):
            if r["ex_date"] < day.isoformat():
                continue
            for uid in who.get((region, r["symbol"]), []):
                per_user.setdefault(uid, []).append(r)
        sent = self._send_each(per_user, lambda rows: "StratLab: corporate action announced", announce_text,
                               f"/research/corporate-actions?region={region}", run)
        ids = {r["id"] for r in fresh}
        with _lock:                            # unmarked only once their messages went out, so a crash before still sends them
            rows = load(region)["rows"]
            for r in rows:
                if r["id"] in ids:
                    r.pop("fresh", None)
            save(region, rows)
        return sent

    def eve(self, region: str, day: date, who, run) -> int:
        """The evening before an ex-date (Friday for a Monday one): one message per person listing their stocks. Only on a
        trading day: a weekend or holiday evening would tell them again about the same next session."""
        from .data.calendar import is_trading_day
        if not is_trading_day(region, day):
            return 0
        nxt = next_trading_day(day, region)
        coming = between(region, day + timedelta(days=1), nxt)
        if not coming:
            return 0
        who = results._get(who)
        per_user: dict[str, list[dict]] = {}
        for r in coming:
            for uid in who.get((region, r["symbol"]), []):
                per_user.setdefault(uid, []).append(r)
        tomorrow = (day + timedelta(days=1)).isoformat()
        return self._send_each(per_user, lambda rows: "StratLab: ex-date tomorrow" if all(r["ex_date"] == tomorrow for r in rows)
                               else "StratLab: ex-dates coming up", lambda rows: eve_text(rows, day),
                               f"/research/corporate-actions?region={region}", run)


# ---------- the pages ----------
def _clean_q(q: str) -> str:
    return re.sub(r"[^A-Z0-9&.\- ]", "", (q or "").upper()).strip()[:30]


def ahead_known(region: str, rows: list[dict]) -> bool:
    """Whether the calendar knows the dates ahead: India's exchange list does; the US list does once the market
    calendar's declared dividends are in it (DE-028)."""
    return region == "IN" or any(r.get("src") == "market calendar" for r in rows)


def view(region: str, uid: str, scope: str = "mine", q: str = "", kind: str = "", today: date | None = None, limit: int = 400) -> dict:
    """Ex-dates from today on, and the last two weeks: the user's own stocks, or every company in the calendar."""
    today = today or local_today(region)
    cal = load(region)
    mine = set(results.my_stocks(uid, region))
    q, kind = _clean_q(q), kind if kind in KINDS else ""
    rows = [r for r in cal["rows"] if (scope == "all" or r["symbol"] in mine) and (not kind or r["kind"] == kind)
            and (not q or q in r["symbol"] or q in str(r.get("name") or "").upper())]
    recent_days = KEEP_DAYS if region == "US" else RECENT_DAYS      # the US list's past ex-dates are its fullest part: it reaches back further
    t, back = today.isoformat(), (today - timedelta(days=recent_days)).isoformat()
    ahead = sorted((r for r in rows if r["ex_date"] >= t), key=lambda r: (r["ex_date"], r["symbol"] not in mine, r["symbol"]))
    recent = sorted((r for r in rows if back <= r["ex_date"] < t), key=lambda r: (r["ex_date"], r["symbol"]), reverse=True)
    show = lambda rs: [{k: v for k, v in {**r, "mine": r["symbol"] in mine}.items() if k != "fresh"} for r in rs[:limit]]
    return {"region": region, "scope": scope, "kind": kind, "today": t, "updated_at": cal["at"], "ahead": show(ahead), "recent": show(recent),
            "more": max(0, len(ahead) - limit) + max(0, len(recent) - limit), "mine_count": len(mine), "alerts": alerts_on(uid),
            "kinds": list(KINDS), "ahead_known": ahead_known(region, cal["rows"]), "note": NOTE, "recent_days": recent_days,
            "universe": {"companies": cal.get("universe"), "updated_at": cal.get("universe_at")} if region == "US" else None}


# actions the backtests' prices don't adjust for: the broker's daily candles are adjusted for bonus issues and splits,
# not for a demerger, so the price drops by the value moved to the new company on its ex-date (R6O-010: RELIANCE's
# JioFin demerger in a five-year test read as part of buy and hold's -6.9%)
UNADJUSTED = ("demerger",)
_unadj = TTLCache(max_items=500)


def unadjusted(region: str, symbol: str, frm: str, to: str, sources: dict | None) -> list[dict]:
    """A company's actions between two days (YYYY-MM-DD) that the test's prices are not adjusted for, from the
    exchange's whole list for the company (not only the three years kept for the corporate actions card)."""
    symbol = symbol.upper()
    if region != "IN" or not sources or sources.get("in") is None:
        return []
    hit = _unadj.get(symbol)
    if hit is None:
        try:
            where, raw = sources["in"].actions_of(symbol)
            rows = bse_rows(raw, symbol) if where == "bse" else [r for r in india_rows(raw) if r["symbol"] == symbol]
        except (SourceError, AttributeError, KeyError, TypeError) as e:
            print("unadjusted actions:", symbol, str(e)[:120])
            rows = None
        hit = [r for r in rows or [] if r.get("kind") in UNADJUSTED] if rows is not None else []
        _unadj.set(symbol, hit, 12 * 3600 if rows is not None else 600)
    have = {r["id"]: r for r in hit}
    for r in history(region, symbol, None, fetch=False):          # what the card has stored, too
        if r.get("kind") in UNADJUSTED:
            have.setdefault(r["id"], r)
    return sorted((r for r in have.values() if frm <= r["ex_date"] <= to), key=lambda r: r["ex_date"])


# a foreign company's own (home) listing, by the end of its ticker: the exchanges a US depositary share is issued on
HOME_SUFFIX = (".MI", ".PA", ".DE", ".AS", ".MC", ".L", ".T", ".HK", ".SW", ".TO", ".AX", ".CO", ".ST", ".OL", ".HE",
               ".BR", ".LS", ".KS", ".TW", ".SA", ".MX", ".JO", ".NS", ".SS", ".SZ", ".IR", ".VI", ".TA", ".SI")
_home_fill = TTLCache(max_items=500)


def home_listing_dividends(symbol: str, rows: list[dict], yahoo, today: date) -> list[dict]:
    """The payments a US depositary share's price history leaves out, from its home listing (R6O-008: Eni's E has no
    Sep and Nov 2025 dividends, which ENI.MI has as EUR0.26 each). Each missing home payment is converted at that
    day's rate and the depositary ratio the two histories share (EUR0.27 to $0.628: 2 shares at 1.163), and is
    marked as converted. Nothing is added unless at least two payments pair up at one steady ratio."""
    key = (symbol.upper(), today.isoformat())
    hit = _home_fill.get(key)
    if hit is not None:
        return hit
    out: list[dict] = []
    try:
        out = _home_missing(symbol.upper(), rows, yahoo, today)
    except Exception as e:                     # a source down or an odd answer: the listed payments stand
        print("home listing dividends:", symbol, type(e).__name__, str(e)[:120])
    _home_fill.set(key, out, 12 * 3600)
    return out


def _home_missing(symbol: str, rows: list[dict], yahoo, today: date) -> list[dict]:
    from statistics import median
    from .intel.grounding import names_agree
    us = sorted((r for r in rows if r.get("kind") == "dividend" and r.get("amount")), key=lambda r: r["ex_date"])
    if len(us) < 2:
        return []
    # a depositary share's dividends are a home payment converted at the day's rate, so they change by fractions of a
    # cent from one to the next (Eni: 0.543, 0.52, 0.571, 0.614); a US company's are set in cents (Apple: 0.25, 0.26).
    # Only the first kind is looked up abroad, so a US company's page costs no extra reads.
    if not any(abs(r["amount"] * 100 - round(r["amount"] * 100)) > 0.05 for r in us[-4:]):
        return []
    name = (yahoo.meta(symbol) or {}).get("name")
    if not name:
        return []
    home = next((x["symbol"] for x in yahoo.search(name) if str(x.get("symbol", "")).upper().endswith(HOME_SUFFIX)
                 and x.get("quoteType") == "EQUITY" and names_agree(name, x.get("longname") or x.get("shortname"))), None)
    if not home:
        return []
    cur = str((yahoo.meta(home) or {}).get("currency") or "")
    scale = 0.01 if cur in ("GBp", "GBX", "ILA", "ZAc") else 1.0
    cur = {"GBp": "GBP", "GBX": "GBP", "ILA": "ILS", "ZAc": "ZAR"}.get(cur, cur).upper()
    if not cur or cur == "USD":
        return []
    fx = {b["t"][:10]: b["c"] for b in yahoo.chart(f"{cur}USD=X", "1d", HIST_DAYS + 30, ttl=12 * 3600).get("candles") or [] if b.get("c")}
    days = sorted(fx)

    def rate(d: str) -> float | None:
        before = [x for x in days if x <= d]
        return fx[before[-1]] if before else None
    frm = (today - timedelta(days=HIST_DAYS)).isoformat()
    theirs = [(d["date"], d["amount"] * scale) for d in yahoo.events(home).get("dividends") or [] if d.get("amount") and d["date"] >= frm]
    ratios, missing = [], []
    for day, amt in theirs:
        r = rate(day)
        if not r:
            continue
        near = [u for u in us if abs((date.fromisoformat(u["ex_date"]) - date.fromisoformat(day)).days) <= 10]
        if near:
            ratios.append(near[0]["amount"] / (amt * r))
        elif us[0]["ex_date"] <= day < today.isoformat():
            missing.append((day, amt, r))
    if len(ratios) < 2:
        return []
    k = median(ratios)
    if any(abs(x / k - 1) > 0.1 for x in ratios):
        return []                              # the two histories don't pair up at one ratio: nothing is guessed
    out = []
    for day, amt, r in missing:
        usd = amt * r * k
        a = {"kind": "dividend", "sub": "dividend", "label": "Dividend", "text": f"Dividend about {money(round(usd, 3), '$')} a share (converted)",
             "short": f"Dividend about {money(round(usd, 3), '$')} a share", "amount": round(usd, 4)}
        rw = row("US", symbol, a, date.fromisoformat(day), src="home listing",
                 purpose=f"Converted from the home listing's {cur} {amt:g} a share at that day's rate")
        out.append({**rw, "converted": True})
    return out


def company(region: str, symbol: str, sources: dict | None, today: date | None = None, fetch: bool = True,
            fetch_history: bool | None = None) -> dict:
    """One company's actions: those ahead, and the past ones (newest first), with the dividends a share of the
    last twelve months added up. A US depositary share's missing payments come from its home listing. `fetch_history`
    False: the stored history as it is, however old (the rest as `fetch` says)."""
    today = today or local_today(region)
    rows = actions_for(region, symbol, sources, today, fetch if fetch_history is None else fetch_history, keep_empty=False)
    if region == "US" and fetch and sources and sources.get("us") is not None:
        rows = sorted(rows + home_listing_dividends(symbol, rows, sources["us"], today), key=lambda r: r["ex_date"])
    t = today.isoformat()
    year_ago = (today - timedelta(days=365)).isoformat()
    rows = in_todays_shares(region, rows, t)
    divs = [r for r in rows if r["kind"] == "dividend" and r.get("amount") and year_ago < r["ex_date"] <= t]
    strip = lambda r: {k: v for k, v in r.items() if k != "fresh"}
    # the year's total in today's shares: a dividend declared before a bonus is per share of the old, fewer shares (DD-013)
    total = sum(r.get("now_amount") or r["amount"] for r in divs)
    return {"region": region, "symbol": symbol.upper(), "today": t, "ahead": [strip(r) for r in rows if r["ex_date"] > t],
            "past": [strip(r) for r in sorted((r for r in rows if r["ex_date"] <= t), key=lambda r: r["ex_date"], reverse=True)[:30]],
            "dividends_12m": {"amount": round(total, 4), "count": len(divs), "currency": CUR[region],
                              **({"adjusted": True} if any(r.get("now_amount") for r in divs) else {})} if divs else None,
            "ahead_known": ahead_known(region, load_cached(region)["rows"]) if region == "US" else True, "note": NOTE}


def in_todays_shares(region: str, rows: list[dict], today: str | None = None) -> list[dict]:
    """India's dividends with their amount in today's shares beside the declared one, when a bonus or split came after
    them: "now_amount" and "now_note" (DD-013: HDFC Bank's "₹22 (Jun 2025)" then "₹13 (Jun 2026)" read as a cut, though
    after its 1:1 bonus the ₹22 is ₹11 a share and the ₹13 a rise). The US history is adjusted already."""
    if region != "IN":
        return rows
    # only a bonus or split already gone ex changes today's shares; one still ahead hasn't yet
    later = sorted(((r["ex_date"], r) for r in rows if adjusts(r) and (today is None or r["ex_date"] <= today)), key=lambda x: x[0])
    if not later:
        return rows
    out = []
    for r in rows:
        after = [a for ex, a in later if ex > r["ex_date"]]
        f = math.prod(a["factor"] for a in after) if after else 1.0
        if r["kind"] == "dividend" and r.get("amount") and after and abs(f - 1) > 1e-9:
            day = lambda iso: (lambda d: f"{d.day} {d:%b %Y}")(date.fromisoformat(iso[:10]))     # noqa: E731
            what = " and ".join(f"the {a.get('short') or a['label'].lower()} of {day(a['ex_date'])}" for a in after)
            r = {**r, "now_amount": round(r["amount"] / f, 4),
                 "now_note": f"{money(r['amount'] / f, CUR[region])} a share in today's shares, after {what}"}
        out.append(r)
    return out


# ---------- open paper positions ----------
# A live paper position held over an ex-date is adjusted as the account would be: a bonus or split changes the
# quantity and every price level of the trade, a dividend pays cash to a long and is paid by a short.
_paper = TTLCache(max_items=2000)    # (region, symbol, day) -> the stored actions looked up for that day


def paper_region(inst: dict | None) -> str | None:
    """The region of a stock or ETF whose paper positions follow its corporate actions, or None: futures, options,
    commodities, currencies and crypto are left alone (the exchange adjusts a derivative contract itself)."""
    inst = inst or {}
    if inst.get("fno") or inst.get("exchange") in ("NFO", "BFO", "MCX", "CDS"):
        return None
    region = inst.get("market", "IN")
    return region if region in REGIONS and inst.get("type", "EQ") in ("EQ", "ETF") else None


def paper_actions(inst: dict, day: str) -> list[dict]:
    """The company's stored bonuses, splits and dividends with ex-dates up to `day`, looked up once a day from the
    stored history and calendar (never the network); nothing stored means nothing until the next day's look."""
    region, sym = paper_region(inst), str(inst.get("symbol") or "").upper()
    if not region or not sym:
        return []
    hit = _paper.get((region, sym, day))
    if hit is None:
        try:
            hit = [a for a in actions_for(region, sym, None, fetch=False) if a["ex_date"] <= day
                   and (adjusts(a) or (a["kind"] == "dividend" and (a.get("amount") or 0) > 0))]
        except Exception as e:
            print("paper corporate actions:", sym, str(e)[:120])
            hit = []
        _paper.set((region, sym, day), hit, 12 * 3600)
    return hit


def paper_due(acts: list[dict], entry_t, day: str, applied: list[str]) -> list[dict]:
    """The actions a position opened at `entry_t` hasn't had yet: ex-date after the day it opened, up to `day`."""
    since = str(entry_t or "")[:10]
    return [a for a in acts if since and since < a["ex_date"] <= day and a["id"] not in applied]


def _ratio_label(a: dict) -> str:
    if a["kind"] == "bonus" and a.get("ratio"):
        return a["label"]
    f = a["factor"]
    return f"{a['label']} 1:{_n(round(f, 4))}" if f > 1 else f"{a['label']} {_n(round(1 / f, 4))}:1"


def paper_apply(qty: float, d: int, entry: float, a: dict, region: str) -> tuple[float, float, float, str]:
    """What one action does to a position of `qty` shares (d 1 long, -1 short) at `entry`: (new quantity, the factor
    its prices are divided by, cash to the account, the event's text). A fraction of a share the company doesn't
    issue is paid in cash at the adjusted entry price."""
    cur = CUR[region]
    held = f"{_qty_text(qty)} share{'s' if qty != 1 else ''}{' short' if d == -1 else ''}"
    if a["kind"] == "dividend":
        cash = round(d * qty * a["amount"], 2)
        return qty, 1.0, cash, (f"Dividend {money(a['amount'], cur)} a share: {money(abs(cash), cur)} "
                                f"{'credited' if d == 1 else 'paid'} for {held}")
    f = a["factor"]
    new, _ = adjusted(qty, entry, a)
    px = entry / f
    cash = round(d * max(qty * f - new, 0.0) * px, 2)
    text = f"{_ratio_label(a)} applied: {held} at {money(round(entry, 2), cur)} are now {_qty_text(new)} at {money(round(px, 2), cur)}"
    if abs(cash) >= 0.005:
        text += f", {money(abs(cash), cur)} {'paid' if d == 1 else 'charged'} for the fractional share"
    return new, f, cash, text


def paper_event(a: dict, region: str, text: str, cash: float) -> dict:
    """The line in the session's log: at the start of the ex-date, not an order (no side)."""
    t = datetime.combine(date.fromisoformat(a["ex_date"]), datetime.min.time(), ZoneInfo(TZ[region]))
    return {"t": t.isoformat(), "kind": "corp", "why": text, "id": a["id"], "cash": cash}


def paper_bars(bars: list[dict], a: dict) -> bool | None:
    """The candles before a bonus or split's ex-date put in the prices after it, in place, when they aren't already:
    the broker's daily candles and Yahoo's come adjusted back in time, the broker's intraday candles and candles built
    from ticks don't. Told apart by the jump across the ex-date (nearer the factor than no jump: not adjusted). True
    when they were adjusted, False when nothing was needed, None while no candle on or after the ex-date is in yet."""
    i = next((k for k, b in enumerate(bars) if str(b["t"])[:10] >= a["ex_date"]), None)
    if i is None:
        return None
    f = a["factor"]
    prev, nxt = bars[i - 1]["c"] if i else 0, bars[i]["o"]
    if not prev or not nxt or prev <= 0 or nxt <= 0 or abs(math.log(prev / nxt / f)) >= abs(math.log(prev / nxt)):
        return False
    for k in range(i):                   # new dicts: the price source may keep the same ones in its cache
        b = bars[k]
        bars[k] = {**b, **{x: b[x] / f for x in ("o", "h", "l", "c")}, **({"v": b["v"] * f} if b.get("v") else {})}
    return True


class PaperActions:
    """One live position's corporate actions: the ids in effect (saved with the session, so none is applied twice), the
    day last looked at, and the bonuses and splits whose older candles wait for the first candle after the ex-date."""

    def __init__(self, inst: dict, state: dict | None = None):
        self.inst, self.region = inst, paper_region(inst)
        self.applied: list[str] = list((state or {}).get("corp_applied") or [])
        self.day: str | None = None
        self.waiting: list[dict] = []

    def dump(self) -> dict:
        return {"corp_applied": self.applied[-50:]}

    def today(self, now: datetime | None = None) -> str:
        """The market's own date."""
        return (now or datetime.now(timezone.utc)).astimezone(ZoneInfo(TZ[self.region or "IN"])).date().isoformat()

    def new_day(self, day: str) -> list[dict] | None:
        """The day's actions the first time `day` is seen (once a day, before its first candle), else None."""
        if not self.region or day == self.day:
            return None
        self.day = day
        return paper_actions(self.inst, day)

    def resume(self, bars: list[dict], day: str) -> list[dict]:
        """At a start or restart, before any missed candle is run: the fetched candles are put in today's prices, so
        every bonus and split up to the newest candle is in effect from here on. Returns those not yet applied (to the
        open position: see apply); all of them count as applied, so a position opened while catching up isn't adjusted
        again. One with its ex-date after the newest candle is left to the day's check."""
        if not self.region or not bars:
            return []
        acts = [a for a in paper_actions(self.inst, day) if adjusts(a)]
        self.bars(bars, acts)
        last = str(bars[-1]["t"])[:10]
        todo = [a for a in acts if a["id"] not in self.applied and a["ex_date"] <= last]
        self.applied += [a["id"] for a in todo]
        return todo

    def bars(self, bars: list[dict], acts: list[dict]):
        if bars:
            first = str(bars[0]["t"])[:10]
            for a in acts:
                if adjusts(a) and a["ex_date"] > first and a not in self.waiting and paper_bars(bars, a) is None:
                    self.waiting.append(a)

    def on_bar(self, bars: list[dict]):
        """A new candle is in: the older candles of a waiting bonus or split are checked against it."""
        self.waiting = [a for a in self.waiting if paper_bars(bars, a) is None]

    def apply(self, e, acts: list[dict], day: str, todo: bool = False) -> float:
        """Apply the actions due to the engine's open position (quantity, entry, stop, target, trailing levels) and log
        each. `todo`: the list resume returned, already marked applied. Returns the cash they pay (negative: paid out)
        and the factor the prices were divided by."""
        cash, moved = 0.0, 1.0
        for a in paper_due(acts, e.entry_t, day, [] if todo else self.applied) if e.qty > 0 else []:
            q, f, c, text = paper_apply(e.qty, e.dir, e.entry, a, self.region)
            e.qty = int(round(q)) if _whole(q) else q
            e.entry, e.sl, e.tg, e.best, e.init_sl = e.entry / f, e.sl / f, e.tg / f, e.best / f, e.init_sl / f
            e.day_mark = e.day_mark / f if e.day_mark is not None else None       # the day's loss is counted from it
            e.events.append(paper_event(a, self.region, text, c))
            if not todo:
                self.applied.append(a["id"])
            cash, moved = cash + c, moved * f
        return cash, moved
