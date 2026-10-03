"""Stock screens: companies filtered by plain facts (sector, size, growth, margins, debt, returns, yield, P/E, Stage,
where the price sits against its 52-week high, red-flag filings) and shown as a table.

Facts only. Nothing here ranks companies as better or worse, scores them or calls one cheap: a screen keeps the
companies that meet the user's own conditions, sorted alphabetically or by a column the user picks.

The numbers come only from what is already stored: the public company pages (stock_pages) keep each company's
facts for a day, and a background job gathers them into one index per market (screens:index:<region>). Running a
screen reads that index from memory; it never calls a data source or AI. The same job tops the stored pages up a
few at a time, through the pages' own per-minute ration, so the index grows without a burst on any source.

Saved screens live in one app_settings row per user (screens:user:<uid>). A saved screen can send a weekly note of the
companies that newly match it, through the newsletter's schedule (run markers, so a restart never sends twice), the
newsletter's confirmed-address rule and the stock alerts' per-user message limits."""
import json
import math
import re
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone
from html import escape

from . import db, sector_members, stock_pages
from .newsletter import job as news_job

INDEX_KEY = "screens:index:"          # screens:index:IN = {"at", "rows": [...]}
KEY = "screens:user:"                 # screens:user:<uid> = {"uid", "items": [...], "sent": [...]}
REGIONS = ("IN", "US")
RED_DAYS = 90                         # "recent" red-flag filings: the last three months
MEMORY = 600                          # the index is read from storage at most every ten minutes
MAX_ROWS = 500                        # rows one request can page through at a time
MAX_NAME = 60
MAX_SECTORS = 40
LIMIT_NUM = 1e7                       # any bound beyond this is a typo, not a condition

# the number filters: id -> (plain label, unit, help). The help text is what the (i) next to the filter says.
RANGES = {
    "sales_cagr_3y": ("Revenue growth, 3 years (a year)", "%",
                      "How fast revenue grew each year, on average, over the last three reported years (compounded)."),
    "net_margin": ("Net profit margin", "%", "Net profit as a share of revenue in the last reported year."),
    "opm": ("Operating margin", "%", "Operating profit (before interest, tax and depreciation) as a share of revenue. "
                                      "Banks and lenders don't report one."),
    "debt_equity": ("Debt to equity", "x", "Borrowings divided by shareholders' equity. 0.5 means half as much debt as equity."),
    "roe": ("Return on equity (ROE)", "%", "Net profit as a share of shareholders' equity in the last reported year."),
    "roce": ("Return on capital employed (ROCE)", "%",
             "Operating profit as a share of the capital the business uses: equity plus borrowings."),
    "div_yield": ("Dividend yield", "%", "Dividends paid over the last year as a share of today's share price."),
    "pe": ("P/E (price to earnings)", "x", "Share price divided by earnings per share over the last twelve months. "
                                          "Companies with a loss have no P/E."),
    "from_high": ("Price vs 52-week high", "%", "How far the last price is from the highest price of the last year. "
                                                "-10 means 10% below the high; 0 means at the high."),
}
# market-cap bands, in the unit each market's numbers are in (₹ crore, $ million): id -> (label, low, high)
CAP_BANDS = {
    "IN": {"large": ("Large (₹20,000 crore and up)", 20000, None), "mid": ("Mid (₹5,000 to 20,000 crore)", 5000, 20000),
           "small": ("Small (₹500 to 5,000 crore)", 500, 5000), "micro": ("Micro (under ₹500 crore)", None, 500)},
    "US": {"large": ("Large ($10 billion and up)", 10000, None), "mid": ("Mid ($2 to 10 billion)", 2000, 10000),
           "small": ("Small ($300 million to 2 billion)", 300, 2000), "micro": ("Micro (under $300 million)", None, 300)},
}
STAGES = {1: "Stage 1 (basing)", 2: "Stage 2 (advancing)", 3: "Stage 3 (topping)", 4: "Stage 4 (declining)"}
HELP = {
    "market": "India (NSE and BSE) or the US.",
    "sector": "The company's sector, from its industry classification.",
    "cap": "The company's market value: share price times shares. Bands are fixed amounts, not a ranking.",
    "stage": "Where the price sits against its 150-day average. " + "; ".join(
        f"{v}: {stock_pages.STAGE_WHY[k]}" for k, v in STAGES.items()) + ".",
    "red_flags": "Filings in the last three months that match fixed red-flag rules: fund raises (QIP, preferential, "
                 "rights, warrants), promoter pledges, auditor resignations, defaults, insolvency, regulator action "
                 "and rating downgrades. India only.",
}
# the table's columns; sorting is allowed on any of them
COLUMNS = ("name", "symbol", "sector", "market_cap", "price", "from_high", "sales_cagr_3y", "net_margin", "opm",
           "debt_equity", "roe", "roce", "div_yield", "pe", "stage", "red_flags")


class ScreenError(ValueError):
    """A screen that can't be run or saved; the message says why in plain words."""


class LimitReached(Exception):
    def __init__(self, limit: int):
        super().__init__(limit)
        self.limit = limit


def _num(v):
    if isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _json(raw, default):
    try:
        v = json.loads(raw or "null")
    except (ValueError, TypeError):
        return default
    return v if isinstance(v, type(default)) else default


# ---------- the index ----------
def _red_count(f: dict) -> int | None:
    """Red-flag filings in the last three months: stored with the page, or worked out from its filings list for a
    page built before the count was kept."""
    if f.get("red_flags") is not None:
        return int(_num(f["red_flags"]) or 0)
    if f.get("region") == "US":
        return None
    from .intel.filings import classify
    try:
        built = datetime.fromisoformat(str(f.get("built_at"))[:19])
    except ValueError:
        return None
    cut = (built - timedelta(days=RED_DAYS)).date().isoformat()
    return sum(1 for x in f.get("filings") or [] if str(x.get("at") or "") >= cut and classify(str(x.get("title") or ""), "")[1] == "red")


def _sector(region: str, symbol: str, f: dict) -> str | None:
    ind = [str(x) for x in f.get("industry") or [] if x]
    if ind:
        return ind[0][:80]
    for name, members in sector_members.BY_MARKET.get(region, {}).items():
        if symbol in members:
            return name.replace("NIFTY ", "").title()
    return None


def row(region: str, symbol: str, f: dict) -> dict | None:
    """One company's line in the index, from its stored page facts; None when there's nothing to screen on."""
    if not isinstance(f, dict) or not f:
        return None
    price, high = _num(f.get("price")), _num(f.get("high52"))
    g = f.get("growth") if isinstance(f.get("growth"), dict) else {}
    out = {"symbol": symbol, "name": str(f.get("name") or symbol)[:120], "sector": _sector(region, symbol, f),
           "industry": str((f.get("industry") or [None])[-1] or "")[:80] or None,
           "market_cap": _num(f.get("market_cap")), "price": price,
           "from_high": round((price / high - 1) * 100, 2) if price and high and high > 0 else None,
           "sales_cagr_3y": _num(g.get("sales_cagr_3y")), "net_margin": _num(f.get("net_margin")),
           "opm": None if f.get("bank") else _num(f.get("opm")), "debt_equity": None if f.get("bank") else _num(f.get("debt_equity")),
           "roe": _num(f.get("roe")), "roce": _num(f.get("roce")), "div_yield": _num(f.get("div_yield")), "pe": _num(f.get("pe")),
           "stage": int(f["stage"]) if _num(f.get("stage")) in STAGES else None,
           "red_flags": _red_count(f) if region == "IN" else None,
           "price_at": str(f.get("price_at") or "")[:10] or None, "built_at": f.get("built_at")}
    return out


def build_index(region: str, store: bool = True) -> dict:
    """Every stored company page in a market, gathered into the screens' index (and saved)."""
    prefix = f"stocks:page:{region}:"
    rows, ages = [], {}
    for key, raw in db.all_settings_with_prefix(prefix):
        stored = _json(raw, {})
        sym = key[len(prefix):]
        ages[sym] = stored.get("ts") or 0
        r = row(region, sym, stored.get("facts") or {})
        if r:
            rows.append(r)
    rows.sort(key=lambda r: (r["name"].lower(), r["symbol"]))
    index = {"region": region, "at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "rows": rows}
    if store:
        db.set_setting(INDEX_KEY + region, json.dumps(index))
        _mem.pop(region, None)
    index["_ages"] = ages
    return index


_mem: dict[str, tuple[float, dict]] = {}
_mem_lock = threading.Lock()


def load_index(region: str) -> dict:
    """The market's index: from memory, else storage. Empty (no rows) before the first build."""
    with _mem_lock:
        hit = _mem.get(region)
        if hit and time.time() - hit[0] < MEMORY:
            return hit[1]
    try:
        index = _json(db.get_setting(INDEX_KEY + region), {})
    except Exception:            # storage down: an empty index, tried again next time
        return {"region": region, "at": None, "rows": []}
    index = {"region": region, "at": index.get("at"), "rows": [r for r in index.get("rows") or [] if isinstance(r, dict) and r.get("symbol")]}
    with _mem_lock:
        _mem[region] = (time.time(), index)
    return index


def as_of(index: dict) -> str | None:
    """When the index's prices are from: the latest close any company in it shows, else when it was built."""
    days = [r["price_at"] for r in index.get("rows") or [] if r.get("price_at")]
    return max(days) if days else index.get("at")


# ---------- the conditions ----------
def clean(region, filters) -> dict:
    """A screen's conditions, checked: raises ScreenError with a plain reason when one doesn't make sense."""
    region = str(region or "").upper()
    if region not in REGIONS:
        raise ScreenError("Screens cover India (IN) and US companies.")
    if filters is None:
        filters = {}
    if not isinstance(filters, dict):
        raise ScreenError("Those filters didn't arrive in a form StratLab can read.")
    out: dict = {"sector": [], "cap": [], "stage": [], "red_flags": None, "ranges": {}}
    sectors = filters.get("sector") or []
    if not isinstance(sectors, list) or len(sectors) > MAX_SECTORS or not all(isinstance(s, str) and 0 < len(s) <= 80 for s in sectors):
        raise ScreenError("Pick sectors from the list.")
    out["sector"] = sorted(set(sectors))
    caps = filters.get("cap") or []
    if not isinstance(caps, list) or not all(isinstance(c, str) and c in CAP_BANDS[region] for c in caps):
        raise ScreenError("Pick company sizes from the list.")
    out["cap"] = [c for c in CAP_BANDS[region] if c in caps]
    stages = filters.get("stage") or []
    if not isinstance(stages, list) or not all(_num(s) is not None and int(s) == s and int(s) in STAGES for s in stages):
        raise ScreenError("Pick Stage 1, 2, 3 or 4.")
    out["stage"] = sorted({int(s) for s in stages})
    red = filters.get("red_flags")
    if red not in (None, "", "any", "yes", "no"):
        raise ScreenError("Recent red-flag filings: choose yes, no or either.")
    out["red_flags"] = red if red in ("yes", "no") and region == "IN" else None
    ranges = filters.get("ranges")
    ranges = {} if ranges is None else ranges
    if not isinstance(ranges, dict):
        raise ScreenError("Those number filters didn't arrive in a form StratLab can read.")
    for k, v in ranges.items():
        if k not in RANGES:
            raise ScreenError("One of the number filters isn't one StratLab knows.")
        if not isinstance(v, dict):
            raise ScreenError(f"{RANGES[k][0]}: enter a lowest and highest value, or leave them empty.")
        lo, hi = v.get("min"), v.get("max")
        bounds = []
        for b in (lo, hi):
            if b is None or b == "":
                bounds.append(None)
                continue
            n = _num(b)
            if n is None or isinstance(b, str) or abs(n) > LIMIT_NUM:
                raise ScreenError(f"{RANGES[k][0]}: enter plain numbers.")
            bounds.append(n)
        if bounds[0] is not None and bounds[1] is not None and bounds[0] > bounds[1]:
            raise ScreenError(f"{RANGES[k][0]}: the lowest value is above the highest.")
        if bounds != [None, None]:
            out["ranges"][k] = {"min": bounds[0], "max": bounds[1]}
    return out


def _in_band(region: str, cap, bands: list[str]) -> bool:
    if cap is None:
        return False
    for b in bands:
        _, lo, hi = CAP_BANDS[region][b]
        if (lo is None or cap >= lo) and (hi is None or cap < hi):
            return True
    return False


def matches(region: str, r: dict, f: dict) -> bool:
    """The company meets every condition. A number the company doesn't report never meets a condition on it."""
    if f["sector"] and r.get("sector") not in f["sector"]:
        return False
    if f["cap"] and not _in_band(region, _num(r.get("market_cap")), f["cap"]):
        return False
    if f["stage"] and r.get("stage") not in f["stage"]:
        return False
    if f["red_flags"]:
        n = r.get("red_flags")
        if n is None or (f["red_flags"] == "yes") != (n > 0):
            return False
    for k, b in f["ranges"].items():
        v = _num(r.get(k))
        if v is None or (b["min"] is not None and v < b["min"]) or (b["max"] is not None and v > b["max"]):
            return False
    return True


def run(region: str, filters: dict, sort: str = "name", desc: bool = False, limit: int = 100, offset: int = 0,
        index: dict | None = None) -> dict:
    """The companies that meet the conditions, sorted by the column picked (alphabetically by default). Companies
    without a value in the sort column come last, whichever way it's sorted."""
    f = clean(region, filters)
    region = region.upper()
    if sort not in COLUMNS:
        raise ScreenError("Sort by one of the table's columns.")
    index = index or load_index(region)
    hit = [r for r in index["rows"] if matches(region, r, f)]
    text = sort in ("name", "symbol", "sector")
    have = [r for r in hit if r.get(sort) is not None]
    rest = sorted((r for r in hit if r.get(sort) is None), key=lambda r: r["name"].lower())
    have.sort(key=lambda r: r["name"].lower())                       # ties stay alphabetical either way
    have.sort(key=(lambda r: str(r[sort]).lower()) if text else (lambda r: r[sort]), reverse=bool(desc))
    rows = have + rest
    limit, offset = max(1, min(MAX_ROWS, int(limit or 100))), max(0, int(offset or 0))
    return {"region": region, "filters": f, "sort": sort, "desc": bool(desc), "total": len(rows), "offset": offset,
            "rows": [{k: v for k, v in r.items() if k != "built_at"} for r in rows[offset:offset + limit]],
            "indexed": len(index["rows"]), "as_of": as_of(index), "index_at": index.get("at")}


def meta(region: str) -> dict:
    """What the filters offer in a market: the sectors in the index, the size bands and every label's help."""
    region = region.upper() if str(region).upper() in REGIONS else "IN"
    index = load_index(region)
    return {"region": region, "sectors": sorted({r["sector"] for r in index["rows"] if r.get("sector")}),
            "cap": [{"id": k, "label": v[0]} for k, v in CAP_BANDS[region].items()],
            "stages": [{"id": k, "label": v} for k, v in STAGES.items()],
            "ranges": [{"id": k, "label": v[0], "unit": v[1], "help": v[2]} for k, v in RANGES.items()],
            "help": HELP, "red_flags": region == "IN", "columns": list(COLUMNS),
            "indexed": len(index["rows"]), "as_of": as_of(index), "index_at": index.get("at")}


def describe(region: str, f: dict) -> list[str]:
    """The conditions in words: "Sector: Energy", "P/E between 5 and 20"."""
    out = []
    if f["sector"]:
        out.append("Sector: " + ", ".join(f["sector"]))
    if f["cap"]:
        out.append("Size: " + ", ".join(CAP_BANDS[region][c][0].split(" (")[0] for c in f["cap"]))
    for k, b in f["ranges"].items():
        label, unit = RANGES[k][0], RANGES[k][1]
        u = "%" if unit == "%" else ""
        n = lambda x: f"{x:g}{u}"           # noqa: E731
        if b["min"] is not None and b["max"] is not None:
            out.append(f"{label} between {n(b['min'])} and {n(b['max'])}")
        elif b["min"] is not None:
            out.append(f"{label} at least {n(b['min'])}")
        else:
            out.append(f"{label} at most {n(b['max'])}")
    if f["stage"]:
        out.append("Stage " + " or ".join(str(s) for s in f["stage"]))
    if f["red_flags"]:
        out.append("Red-flag filings in the last 3 months" if f["red_flags"] == "yes" else "No red-flag filings in the last 3 months")
    return out


# ---------- saved screens ----------
_lock = threading.Lock()
_ID = re.compile(r"^[0-9a-f]{6,24}$")


def _read(uid: str) -> dict:
    try:
        row_ = _json(db.get_setting(KEY + uid), {})
    except Exception:
        row_ = {}
    items = row_.get("items")
    row_["items"] = [s for s in items if isinstance(s, dict) and s.get("id")] if isinstance(items, list) else []
    row_["sent"] = row_.get("sent") if isinstance(row_.get("sent"), list) else []
    row_["uid"] = uid
    return row_


def _write(uid: str, row_: dict) -> None:
    db.set_setting(KEY + uid, json.dumps(row_))


def items(uid: str) -> list[dict]:
    return _read(uid)["items"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _clean_saved(req: dict) -> dict:
    name = re.sub(r"\s+", " ", str(req.get("name") or "")).strip()[:MAX_NAME]
    if not name:
        raise ScreenError("Give the screen a name.")
    region = str(req.get("region") or "").upper()
    f = clean(region, req.get("filters"))
    sort = req.get("sort") or "name"
    if sort not in COLUMNS:
        raise ScreenError("Sort by one of the table's columns.")
    return {"name": name, "region": region, "filters": f, "sort": sort, "desc": bool(req.get("desc")), "notify": bool(req.get("notify"))}


def _symbols(region: str, f: dict) -> list[str]:
    return sorted(r["symbol"] for r in load_index(region)["rows"] if matches(region, r, f))


def save(uid: str, req: dict, limit: int, sid: str | None = None) -> dict | None:
    """Add a screen (or change one, when `sid` is given; None if it's gone). The companies matching now are noted,
    so the weekly note only lists the ones that match later."""
    s = _clean_saved(req)
    with _lock:
        row_ = _read(uid)
        if sid:
            old = next((x for x in row_["items"] if x["id"] == sid), None)
            if not old:
                return None
            changed = old.get("filters") != s["filters"] or old.get("region") != s["region"]
            old.update(s, updated_at=_now())
            if changed:
                old["matched"] = _symbols(s["region"], s["filters"])
            _write(uid, row_)
            return old
        if len(row_["items"]) >= limit:
            raise LimitReached(limit)
        s.update(id=secrets.token_hex(6), created_at=_now(), updated_at=None, matched=_symbols(s["region"], s["filters"]),
                 last_sent_at=None)
        row_["items"].append(s)
        _write(uid, row_)
        return s


def delete(uid: str, sid: str) -> bool:
    with _lock:
        row_ = _read(uid)
        keep = [x for x in row_["items"] if x["id"] != sid]
        if len(keep) == len(row_["items"]):
            return False
        row_["items"] = keep
        _write(uid, row_)
    return True


def mute(uid: str) -> None:
    """Turn off every weekly note (the email's unsubscribe link)."""
    with _lock:
        row_ = _read(uid)
        if any(x.get("notify") for x in row_["items"]):
            for x in row_["items"]:
                x["notify"] = False
            _write(uid, row_)


def view(s: dict) -> dict:
    """A saved screen for the page: its conditions in words, without the stored match list."""
    return {**{k: v for k, v in s.items() if k != "matched"}, "conditions": describe(s["region"], s["filters"]),
            "matched_count": len(s.get("matched") or [])}


def valid_id(sid: str) -> bool:
    return bool(_ID.match(sid or ""))


# ---------- the weekly note ----------
def note(parts: list[tuple[dict, list[dict]]], index_as_of: str | None) -> tuple[str, str, str]:
    """(subject, text, html): for each of a user's screens, the companies that newly match it. One message a week,
    however many screens. Facts only: what matched, under which conditions, and when the numbers are from."""
    from .newsletter import write
    total = sum(len(new) for _, new in parts)
    many = f"{total} compan{'y newly matches' if total == 1 else 'ies newly match'}"
    subject = (f"StratLab: {many} your screen \u201c{parts[0][0]['name']}\u201d" if len(parts) == 1
               else f"StratLab: {many} {len(parts)} of your screens")[:150]
    when = _when(index_as_of)
    text, body = [subject, ""], []
    for screen, new in parts:
        region, shown = screen["region"], new[:25]
        conds = "; ".join(describe(region, screen["filters"]) or ["Every company in the market"])
        lines = [(f"{r['name']} ({r['symbol']})", write.stock_url(region, r["symbol"])) for r in shown]
        more = f"and {len(new) - len(shown)} more in StratLab" if len(new) > len(shown) else None
        text += [screen["name"].upper(), f"Conditions: {conds}"] + [f"- {ln}: {url}" for ln, url in lines] + ([more] if more else []) + [""]
        body.append(f'<h2 style="font-size:16px;margin:16px 0 4px">{escape(screen["name"])}</h2>'
                    f'<p style="margin:0 0 8px;color:#374151;font-size:14px">Conditions: {escape(conds)}</p>'
                    '<ul style="margin:0;padding-left:18px">'
                    + "".join(f'<li style="margin:6px 0">{write.link(url, ln)}</li>' for ln, url in lines) + "</ul>"
                    + (f'<p style="margin:8px 0 0">{more}</p>' if more else ""))
    if when:
        text.append(f"Numbers as of {when}.")
        body.append(f'<p style="margin:16px 0 0;font-size:13px;color:#6b7280">Numbers as of {escape(when)}.</p>')
    text += ["These companies meet the conditions you set. Facts, not advice.", f"Turn off screen emails: {write.UNSUBSCRIBE}"]
    footer = (f"These companies meet the conditions you set. Facts, not advice.<br>"
              f'<a href="{write.UNSUBSCRIBE}" style="color:#6b7280">Turn off screen emails</a>')
    return subject, "\n".join(text), write.frame(subject, body, footer)


def _when(iso: str | None) -> str | None:
    if not iso:
        return None
    try:
        d = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return None
    return f"{d.day} {d:%b %Y}" + (f", {d:%H:%M} UTC" if len(str(iso)) > 10 else "")


def deliver(profile: dict, subject: str, text: str, html: str) -> list[str]:
    """Email to the confirmed newsletter address (with one-click unsubscribe), and a two-line teaser by phone or
    Telegram for those who set them up. Returns the channels reached."""
    from . import alerts
    sent = []
    to = alerts.newsletter_email(profile)
    if to and alerts.email_ready() and alerts.email_confirmed(profile):
        unsub = alerts.unsubscribe_url(profile["id"], "screens")
        try:
            alerts.send_email(to, subject, text.replace("{unsubscribe_url}", unsub), html=html.replace("{unsubscribe_url}", unsub),
                              headers=alerts.list_unsubscribe_headers(profile["id"], "screens"))
            sent.append("email")
        except Exception as e:
            print("screen email failed:", str(e)[:160])
    quiet = {**profile, "alert_email": None, "email": None}          # never a second email
    try:
        sent += alerts.notify(quiet, subject, subject, url="/research/screens")
    except Exception as e:
        print("screen teaser failed:", str(e)[:160])
    return sent


def weekly(now: datetime, profile_fn, limit_fn, send=deliver) -> int:
    """For each user with a weekly note on: the companies that match their screens now and didn't last week, in one
    message, within the stock alerts' per-user message limits. A note held back by the limits leaves the screens as
    they were, so those companies are still new next week. Returns notes sent."""
    from .stock_alerts import may_send
    sent = 0
    for key, raw in db.all_settings_with_prefix(KEY):
        uid = key[len(KEY):]
        if not any(isinstance(s, dict) and s.get("notify") for s in _json(raw, {}).get("items") or []):
            continue
        try:
            profile = profile_fn(uid)
        except Exception:
            continue
        allowed = limit_fn(profile)
        with _lock:
            row_ = _read(uid)
            if not may_send(row_["sent"], now):
                continue
            parts, matched, at = [], {}, None
            for s in sorted(row_["items"], key=lambda x: x.get("created_at") or "")[:allowed]:   # over the plan: the oldest
                try:
                    f = clean(s["region"], s.get("filters"))
                except (ScreenError, KeyError):
                    continue
                index = load_index(s["region"])
                if not index["rows"]:
                    continue
                now_match = [r for r in index["rows"] if matches(s["region"], r, f)]
                before = set(s.get("matched") or [])
                matched[s["id"]] = sorted(r["symbol"] for r in now_match)
                new = [r for r in now_match if r["symbol"] not in before]
                if s.get("notify") and new:
                    parts.append((s, new))
                    at = max(filter(None, (at, as_of(index))), default=None)
            msg = note(parts, at) if parts else None
        if msg and not send(profile, *msg):
            continue                                # nowhere to send it: the matches stay new for next week
        with _lock:
            row_ = _read(uid)
            for s in row_["items"]:
                if s["id"] in matched:
                    s["matched"] = matched[s["id"]]
                    if msg and any(p["id"] == s["id"] for p, _ in parts):
                        s["last_sent_at"] = now.isoformat()
            if msg:
                row_["sent"] = [t for t in row_["sent"] if _recent(t, now)] + [now.isoformat()]
                sent += 1
            _write(uid, row_)
    return sent


def _recent(t: str, now: datetime) -> bool:
    try:
        return now - datetime.fromisoformat(t) < timedelta(days=1)
    except (ValueError, TypeError):
        return False


# ---------- the background job ----------
class Indexer:
    """Every half hour: top up a few stored company pages (through the pages' own ration), then gather every stored
    page into each market's index. `warm(region, symbol, company)` builds one page; it may raise when a source is
    busy, which only means trying again next time."""

    def __init__(self, warm=None, every: float = 1800, warm_per_run: int = 12, gap: float = 10.0):
        self.warm, self.every, self.warm_per_run, self.gap = warm, every, warm_per_run, gap
        self.status = {"last_run": None, "rows": {}, "warmed": 0, "last_error": None}

    def _due(self, region: str, ages: dict) -> list[tuple[str, dict]]:
        """Companies to build next: those with no stored page (the sector lists' first), then the stalest."""
        cos = stock_pages.companies(region)
        seeds = stock_pages._seeds(region)
        missing = sorted((s for s in cos if s not in ages), key=lambda s: (s not in seeds, s))
        stale = sorted((s for s, t in ages.items() if s in cos and time.time() - t > stock_pages.FRESH), key=lambda s: ages[s])
        return [(s, cos[s]) for s in (missing + stale)[:self.warm_per_run]]

    def run_once(self, sleep=time.sleep) -> dict:
        warmed = 0
        for region in REGIONS:
            try:
                index = build_index(region, store=False)
                if self.warm:
                    for i, (sym, co) in enumerate(self._due(region, index["_ages"])):
                        if i:
                            sleep(self.gap)              # leave room in the ration for people opening pages
                        try:
                            self.warm(region, sym, co)
                            warmed += 1
                        except Exception as e:           # busy or down: next run
                            self.status["last_error"] = f"{region} {sym}: {str(e)[:120] or e.__class__.__name__}"
                            break
                index = build_index(region)
                self.status["rows"][region] = len(index["rows"])
            except Exception as e:
                self.status["last_error"] = f"{region}: {str(e)[:160]}"
                print("screens index failed:", region, str(e)[:160])
        self.status.update(last_run=_now(), warmed=warmed)
        return self.status

    def loop(self):
        time.sleep(300)                          # after startup traffic and the company lists
        while True:
            self.run_once()
            time.sleep(self.every)


class Job(news_job.Job):
    """The weekly notes, on Saturday morning (India time) after the weekly newsletter. Uses the newsletter job's run
    markers (newsjob:screens), so a restart never sends a week's notes twice."""
    AT = ("Asia/Kolkata", 5, "09:00")

    def __init__(self, profile_fn, limit_fn):
        super().__init__()
        self.profile_fn, self.limit_fn = profile_fn, limit_fn

    def start(self):
        threading.Thread(target=self._loop, daemon=True, name="screen-notes").start()

    def tick(self, now: datetime) -> int:
        tz, weekday, at = self.AT
        day = self.due("screens", now, tz, at, weekday=weekday)
        if not day:
            return 0
        self.mark("screens", day)
        sent = weekly(now, self.profile_fn, self.limit_fn)
        self.status.update(last_run=now.isoformat(), sent=sent, last_error=None)
        return sent
