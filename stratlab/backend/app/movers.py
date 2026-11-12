"""Market movers: a group's biggest gainers and losers of the last close, the most traded by value, the volume spikes (the day's volume
against its 20-session average) and the stocks that made a 52-week high or low that day, India and the US.

Nothing here reads a price source. The daily breadth run already reduces every stock's candles to the heatmap's row (heatmap.heat_row:
the last close, the day's change, the day's volume and its 20-session average) and, as it goes, to one short mark kept here (`mark_row`:
the day of the last candle, the highest high and lowest low of the last 52 weeks, and whether that day set a new 52-week high or low by
the breadth count's own rule). The page asks for a group and gets every list at once from those two stored reads, joined to the names and
market values the screens keep; the answer is shared by everyone for two minutes. A stock whose last candle is older than the run's day
(suspended, or no trade that day) is left out of the day's lists.

The same lists are a public page per market (/stocks/in/movers, /stocks/us/movers), written as plain HTML like the company pages, so a
visitor or a search engine reads them without the app.

Plans (owner, 12 Nov: the free part shows the feature is real, nothing more): Basic and up get every list in full (TOP rows), any of the
market's groups, a smallest market value and the CSV on the page (the "movers" feature in plans.py); Free and the public page get the top
TEASER rows of each list for the market's default index, with the plan that opens the rest.

Facts only: a list is sorted by a figure, and that is all. Nothing here ranks a stock as good or bad or says what to do."""
from __future__ import annotations

import json
import math
import time
from datetime import date

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse

from . import db, heatmap
from .auth import current_profile
from .intel.net import TTLCache
from .responses import err, ok

KEY = "movers:marks:"                 # movers:marks:<region> = {"day", "at", "stocks": {symbol: [last day, 52w high, 52w low, new high, new low]}}
LISTS = ("gainers", "losers", "traded", "spikes", "highs", "lows")
TOP = 50                              # rows each list carries on Basic and up (the "movers" feature)
TEASER = 5                            # rows each list carries for Free and on the public page: the default index only, no filters
MAX_CAP = 1e9                         # a smallest market value beyond this is a typo
VIEW_FOR = 120                        # seconds one group's answer is shared by everyone (the rows change once a day)
_views = TTLCache(max_items=60, max_bytes=8 * 1024 * 1024)


def _num(v) -> float | None:
    if isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


# ---------- the daily run's mark of one stock ----------
def mark_row(flags, base) -> list | None:
    """[the day of the last candle, the 52-week high, the 52-week low, 1 when that day set a new 52-week high else 0, the same for a low]
    from the breadth run's own work on the stock: its day-by-day flags (breadth.stock_flags, whose "hi" and "lo" are the count's rule: a
    day's high above every high of the 251 sessions before it) and its base row (breadth.base_row: the highest high and lowest low of the
    last 251 sessions, None when the stock has fewer). None when there is nothing to mark."""
    if flags is None or not len(flags):
        return None
    try:
        last = flags.iloc[-1]
        day = str(flags.index[-1])[:10]
        hi = _num(base[5]) if base and len(base) > 6 else None
        lo = _num(base[6]) if base and len(base) > 6 else None
        return [day, hi, lo, 1 if float(last.get("hi", 0) or 0) > 0 else 0, 1 if float(last.get("lo", 0) or 0) > 0 else 0]
    except Exception:
        return None


def save_marks(region: str, day: str, marks: dict[str, list]) -> None:
    doc = {"day": day, "at": int(time.time()), "stocks": marks}
    db.set_setting(KEY + region, json.dumps(doc, separators=(",", ":")))
    _views.clear()


def load_marks(region: str) -> dict:
    """{"day", "stocks"}: the marks of the market's last run, {"day": None, "stocks": {}} before the first run that kept them."""
    try:
        raw = db.json_value(db.get_setting(KEY + region), {})
    except Exception:                    # storage down: the 52-week lists wait, the rest still shows
        raw = {}
    stocks = raw.get("stocks") if isinstance(raw.get("stocks"), dict) else {}
    return {"day": raw.get("day"), "stocks": {s: m for s, m in stocks.items() if isinstance(m, list) and len(m) == 5}}


def clear() -> None:
    _views.clear()


# ---------- the lists ----------
def row_of(symbol: str, heat: list, f: dict | None, mark: list | None) -> dict:
    """One stock in a list: s symbol, n name, cap market value (the market's unit), px last close, chg the day's change in percent, vol the
    day's volume, avg its 20-session average, vx the one over the other, tv the value traded (close times volume), hi and lo the 52-week
    high and low (None until the run has kept them)."""
    t = heatmap.tile(symbol, heat, f, None)
    vol, avg = _num(heat[-2]), _num(heat[-1])
    return {"s": t["s"], "n": t["n"], "cap": t["cap"], "px": t["px"], "chg": t["r"][0], "vol": vol, "avg": avg, "vx": t["vx"], "tv": t["tv"],
            "hi": _num(mark[1]) if mark else None, "lo": _num(mark[2]) if mark else None}


def _sorted(rows: list[dict], key, desc: bool) -> list[dict]:
    """Rows with a figure, by it (ties by the larger market value, then the symbol)."""
    have = [r for r in rows if key(r) is not None]
    return sorted(have, key=lambda r: ((-key(r) if desc else key(r)), -(r["cap"] or 0), r["s"]))


def lists_of(rows: list[dict], marks: dict[str, list] | None) -> dict[str, list[dict]]:
    """Every list, whole: gainers (a rise, largest first), losers (a fall, largest first), traded (value traded), spikes (volume against its
    average, among stocks that traded), highs and lows (a new 52-week high or low that day, by the day's change)."""
    marks = marks or {}
    up = _sorted([r for r in rows if (r["chg"] or 0) > 0], lambda r: r["chg"], True)
    down = _sorted([r for r in rows if (r["chg"] or 0) < 0], lambda r: r["chg"], False)
    traded = _sorted([r for r in rows if r["tv"]], lambda r: r["tv"], True)
    spikes = _sorted([r for r in rows if r["vx"] is not None and (r["vol"] or 0) > 0 and r["vx"] > 1], lambda r: r["vx"], True)
    highs = _sorted([r for r in rows if (marks.get(r["s"]) or [0, 0, 0, 0, 0])[3]], lambda r: r["chg"] if r["chg"] is not None else 0.0, True)
    lows = _sorted([r for r in rows if (marks.get(r["s"]) or [0, 0, 0, 0, 0])[4]], lambda r: r["chg"] if r["chg"] is not None else 0.0, False)
    return {"gainers": up, "losers": down, "traded": traded, "spikes": spikes, "highs": highs, "lows": lows}


def view(region: str, universe: str | None = None, min_cap: float | None = None, top: int = TOP) -> dict:
    """A group's lists, each its `top` rows with its whole count. `pending` is true until the daily run has stored the market's rows once;
    `marks` is false until a run has kept the 52-week marks of the same day (the 52-week lists are then empty, and say so)."""
    from . import breadth
    group = universe if universe in heatmap.UNIVERSES[region] else heatmap.DEFAULT[region]
    doc = heatmap.load(region)
    stocks, day = doc.get("stocks") or {}, doc.get("day")
    kept = load_marks(region)
    same_day = bool(kept["stocks"]) and kept["day"] == day
    marks = kept["stocks"] if same_day else {}
    g = breadth.GROUPS[group]
    out = {"market": region, "universe": group, "universe_name": g["name"], "universes": heatmap.universes(region), "as_of": day,
           "cap_unit": heatmap.CAP_UNIT[region], "pending": not stocks, "marks": same_day, "min_cap": min_cap, "top": top,
           "members": 0, "with_prices": 0, "matching": 0, "lists": {k: {"total": 0, "rows": []} for k in LISTS}}
    if not stocks:
        return out
    want = breadth.members(group)
    facts, _ = heatmap._facts(region)
    rows = []
    for s in want:
        heat = stocks.get(s)
        if not heat:
            continue
        mark = marks.get(s)
        if mark and day and mark[0] != day:          # no candle on the close's day (suspended, or no trade): not one of that day's movers
            continue
        rows.append(row_of(s, heat, facts.get(s), mark))
    out["members"], out["with_prices"] = len(want), len(rows)
    if min_cap:
        rows = [r for r in rows if r["cap"] is not None and r["cap"] >= min_cap]
    out["matching"] = len(rows)
    out["lists"] = {k: {"total": len(v), "rows": v[:top]} for k, v in lists_of(rows, marks).items()}
    return out


def cached(region: str, universe: str | None, min_cap: float | None, top: int = TOP) -> dict:
    key = (region, universe or heatmap.DEFAULT[region], min_cap or None, top)
    hit = _views.get(key)
    if hit is None:
        hit = view(region, universe, min_cap or None, top)
        _views.set(key, hit, VIEW_FOR)
    return hit


# ---------- the routes ----------
router = APIRouter(tags=["movers"])


@router.get("/invest/movers")
def movers(market: str = "IN", universe: str | None = None, min_cap: float | None = None, profile=Depends(current_profile)):
    """The movers of a group of a market (India or the US) at the last close: every list, each its top rows. Basic and up get TOP rows
    and the filters (the "movers" feature); Free gets the TEASER rows of the default index with `locked` (owner, 12 Nov: the free part only
    shows the feature is real), whatever filters were asked for, and `plan`, the plan that opens the rest."""
    from .plans import FEATURE_PLAN, PLANS, allows, plan_of
    region = (market or "").upper()
    if region not in heatmap.UNIVERSES:
        err(400, "bad_market", "Pick India or the US.")
    if universe is not None and universe not in heatmap.UNIVERSES[region]:
        err(404, "not_found", "Pick a group of stocks from the list.")
    if min_cap is not None and not (math.isfinite(min_cap) and 0 <= min_cap <= MAX_CAP):
        err(400, "bad_min_cap", "The smallest market value isn't a number the page offers.")
    if allows(plan_of(profile), "movers"):
        return ok({**cached(region, universe, min_cap), "locked": False})
    return ok({**cached(region, None, None, TEASER), "locked": True, "plan": PLANS[FEATURE_PLAN["movers"]]["name"]})


# ---------- the public page ----------
TITLES = {"gainers": "Gainers", "losers": "Losers", "traded": "Most traded", "spikes": "Volume spikes", "highs": "52-week highs", "lows": "52-week lows"}
WHAT = {"gainers": "the largest rises at the close", "losers": "the largest falls at the close",
        "traded": "the most value traded (closing price times volume)", "spikes": "the day's volume as a multiple of its average over the 20 sessions before",
        "highs": "a high above every high of the 52 weeks before", "lows": "a low below every low of the 52 weeks before"}
WHERE = {"IN": "India", "US": "US"}


def _money(v: float | None, region: str) -> str:
    """A price: "₹1,286.40", "$412.60"."""
    if v is None:
        return "–"
    return ("₹" if region == "IN" else "$") + f"{v:,.2f}"


def _big(v: float | None, region: str) -> str:
    """A large amount in the market's own words: "₹1,240 cr", "$3.4B"."""
    if not v:
        return "–"
    if region == "IN":
        cr = v / 1e7
        return f"₹{cr:,.0f} cr" if cr >= 10 else f"₹{cr:,.1f} cr"
    return f"${v / 1e9:,.1f}B" if v >= 1e9 else f"${v / 1e6:,.0f}M"


def _pct(v: float | None) -> str:
    if v is None:
        return "–"
    return ("+" if v > 0 else "−" if v < 0 else "") + f"{abs(v):.2f}%"


def _day(iso: str | None) -> str:
    try:
        d = date.fromisoformat(str(iso)[:10])
    except (TypeError, ValueError):
        return ""
    return f"{d.day} {d:%b %Y}"


def public_page(region: str) -> str:
    """/stocks/<in|us>/movers: the default group's lists, each linked to the companies' public pages where they have one."""
    from . import stock_pages as sp
    from .config import settings
    from html import escape as e
    v = cached(region, None, None, TEASER)
    r = region.lower()
    where = WHERE[region]
    site = settings.PUBLIC_SITE_URL
    canonical = f"{site}/stocks/{r}/movers"
    crumbs, ld = sp._crumbs([("Companies", "/stocks"), (where, f"/stocks/{r}"), ("Market movers", f"/stocks/{r}/movers")])
    try:
        pages = sp.companies(region)
    except Exception:
        pages = {}
    day = _day(v["as_of"])
    group = v["universe_name"]
    body = [crumbs, f"<h1>{where} market movers</h1>"]
    if v["pending"]:
        body.append('<p class="muted">The lists fill in after the next market close, once each stock\'s daily close has been stored.</p>')
    else:
        body.append(f'<p class="muted">{e(group)} at the close of <b>{e(day)}</b>: gainers, losers, the most traded, volume spikes and '
                    "52-week highs and lows, from each stock's daily close. Facts, not advice.</p>")
        body.append('<nav class="links" aria-label="Lists on this page">' + "".join(f'<a href="#{k}">{TITLES[k]}</a>' for k in LISTS) + "</nav>")

    def cell_name(row: dict) -> str:
        name = sp.proper_name(row["n"]) if region == "US" else sp.tidy_in_name(row["n"])
        same = not name or name.replace(" ", "").upper() == row["s"].upper()       # a name that is only its symbol is said once
        label = e(row["s"]) if same else f'{e(name)} <span class="muted">{e(row["s"])}</span>'
        return f'<a href="{e(sp.path(r, row["s"]))}">{label}</a>' if row["s"] in pages else label

    for k in LISTS if not v["pending"] else ():
        lst = v["lists"][k]
        rows = lst["rows"][:TEASER]
        extra = {"traded": "Value traded", "spikes": "Volume vs average", "highs": "52-week high", "lows": "52-week low"}.get(k, "Volume vs average")
        def extra_cell(row: dict) -> str:
            if k == "traded":
                return _big(row["tv"], region)
            if k == "highs":
                return _money(row["hi"], region)
            if k == "lows":
                return _money(row["lo"], region)
            return "–" if row["vx"] is None else f"{row['vx']:.1f}×"
        body.append(f'<h2 id="{k}">{TITLES[k]}</h2><p class="small muted">{WHAT[k][:1].upper() + WHAT[k][1:]}.'
                    + (f" The top {len(rows)} of {lst['total']:,}." if lst["total"] > len(rows) else "") + "</p>")
        if not rows:
            none = ("The 52-week highs and lows appear after the next daily close run." if k in ("highs", "lows") and not v["marks"]
                    else "None at this close.")
            body.append(f'<p class="muted">{none}</p>')
            continue
        trs = "".join(f'<tr><td>{cell_name(x)}</td><td>{_money(x["px"], region)}</td><td data-dir="{"up" if (x["chg"] or 0) > 0 else "down" if (x["chg"] or 0) < 0 else ""}">'
                      f'{_pct(x["chg"])}</td><td>{extra_cell(x)}</td></tr>' for x in rows)
        body.append(f'<div class="card tbl mv"><table><caption class="skip">{TITLES[k]}, {e(group)}, close of {e(day)}</caption>'
                    f'<thead><tr><th scope="col">Company</th><th scope="col">Close</th><th scope="col">1 day</th><th scope="col">{extra}</th></tr></thead>'
                    f"<tbody>{trs}</tbody></table></div>")
    other = "us" if r == "in" else "in"
    if not v["pending"]:
        body.append(f'<div class="card mv-cta"><p><b>Every row of each list, any index and a smallest market value, with a CSV download, are on '
                    f'the Basic plan.</b> <a class="btn" href="{site}/invest/movers?region={region}">See the full lists</a></p></div>')
    body.append(f'<p class="small">See the <a href="/stocks/{other}/movers">{WHERE["US" if r == "in" else "IN"]} market movers</a>. '
                f'<a href="{site}/status">When each dataset was last updated</a>.</p>')
    style = ("<style>.mv td[data-dir=up]{color:var(--up)}.mv td[data-dir=down]{color:var(--down)}.mv td:first-child{white-space:normal;min-width:180px}"
             "@media (min-width:641px){.mv table{table-layout:fixed}.mv th:first-child{width:46%}}.mv td:first-child .muted{font-size:13px;margin-left:4px}.links{display:flex;flex-wrap:wrap;gap:8px 18px;margin:12px 0}"
             ".links a{display:inline-flex;align-items:center;min-height:44px}.mv-cta p{margin:0;display:flex;flex-wrap:wrap;gap:12px;align-items:center}</style>")
    title = f"{where} market movers: gainers, losers, most traded · StratLab"
    desc = (f"{group} at the close of {day}: the top gainers and losers, the most traded stocks, volume spikes and 52-week highs and lows."
            if not v["pending"] else f"{where} stocks' gainers, losers, most traded, volume spikes and 52-week highs and lows at the close.")
    return sp._page(sp._head(title, desc, canonical, ld + style), None, "".join(body))


public_router = APIRouter(tags=["movers"])


@public_router.get("/stocks/{region}/movers", response_class=HTMLResponse)
def movers_page(region: str):
    """The public movers page of a market (India or the US), for visitors and search engines."""
    from . import stock_pages as sp
    from fastapi.responses import RedirectResponse
    reg = sp.REGIONS.get(region.lower())
    if not reg:
        return HTMLResponse(sp.dir_not_found(None), status_code=404)
    if region != region.lower():
        return RedirectResponse(f"/stocks/{region.lower()}/movers", status_code=301)
    return HTMLResponse(public_page(reg), headers={"Cache-Control": sp.edge_cache([reg])})


def sitemap_urls(site: str, day: str | None = None) -> list[tuple[str, str | None]]:
    """The public movers pages, with the day of the stored closes."""
    out = []
    for r, R in (("in", "IN"), ("us", "US")):
        out.append((f"{site}/stocks/{r}/movers", heatmap.load(R).get("day") or day))
    return out
