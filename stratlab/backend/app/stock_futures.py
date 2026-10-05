"""The F&O stock futures desk: for every stock with futures, the day's price and open-interest change and what they
did together (the market's buildup terms), open interest by expiry, the share rolled to later expiries, the futures'
premium over the share price (the basis, also annualised), and how much of the market-wide position limit (MWPL) the
open interest uses.

Two of the exchange's evening files, read by the stock desks' job (exchange_days.py):
- the F&O common bhavcopy (every contract's close, previous close, underlying close and open interest), and
- the combined open interest across exchanges (each stock's MWPL, its futures-equivalent (delta-based) open interest
  and whether new positions are allowed the next day).
The share price is the underlying close the bhavcopy states, else the cash market's close.

Facts and arithmetic only. The buildup words describe what price and open interest did on the day; nothing here says
what they mean for the price next, and nothing is ranked."""
import re
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, Query

from . import exchange_days as X
from .auth import current_profile
from .intel.net import num
from .plans import FEATURE_PLAN, PLANS, allows
from .responses import err, ok

PREFIX = "fnostk:"
FO_BHAV = X.ARCHIVE + "/content/fo/BhavCopy_NSE_FO_0_0_0_{ymd}_F_0000.csv.zip"
COMBINE_OI = X.ARCHIVE + "/archives/nsccl/mwpl/combineoi_{dmy}.zip"
KEEP = 260                   # trading days kept: about a year
BAN_AT, FREE_AT, WATCH_AT = 95.0, 80.0, 80.0
ROLL_WINDOW = 5              # trading days before the near expiry when the share in later expiries is the rollover
RANGES = {"1m": 31, "3m": 92, "6m": 183, "1y": 366}
SYMBOL = re.compile(r"^[A-Z0-9&\-]{1,20}$")
SOURCE = "the exchange's F&O bhavcopy and its combined open interest file (MWPL)"
NOTE = ("Exchange data as published after the close, and arithmetic on it. The buildup words describe what price and "
        "open interest did together on the day; they say nothing about what the price will do next.")
# the market's own terms for price and open interest moving together: code -> (label, what it means)
BUILDUP = {
    "LB": ("Long buildup", "The futures price rose and open interest rose: new positions were opened as the price went up."),
    "SB": ("Short buildup", "The futures price fell and open interest rose: new positions were opened as the price went down."),
    "SC": ("Short covering", "The futures price rose and open interest fell: positions were closed as the price went up."),
    "LU": ("Long unwinding", "The futures price fell and open interest fell: positions were closed as the price went down."),
}
ABOUT = {
    "oi": "Open interest: the futures contracts open at the close, in shares, across every expiry.",
    "rollover": f"The share of futures open interest in the next and far expiries. In the last {ROLL_WINDOW} trading days "
                "before the near expiry it's read as the rollover: positions moved on to a later expiry.",
    "basis": "The near futures' close against the share's close, as a percent of the share price. Annualised: that "
             "percent over the calendar days left to expiry, scaled to a year.",
    "mwpl": "Futures-equivalent (delta-based) open interest across exchanges as a percent of the stock's market-wide "
            "position limit (MWPL). From 95% the stock is in the F&O ban period: no new positions until it is back "
            "under 80%.",
}


# ---------- reading the files ----------
def _day(v: str) -> str | None:
    """An ISO day from the exchange's ways of writing one: 2026-10-01, 01-OCT-2026, 01-10-2026."""
    s = str(v or "").strip()
    for fmt in ("%Y-%m-%d", "%d-%b-%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def contracts(text: str) -> tuple[str | None, dict[str, list[dict]]]:
    """The F&O common bhavcopy's stock futures (FinInstrmTp STF): (trade day, {symbol: [contract, ...] by expiry}),
    each contract {"expiry", "close", "prev", "under", "oi", "oi_chg", "vol", "lot"}."""
    rows = X.rows_of(text)
    if rows and "FinInstrmTp" not in rows[0]:
        raise ValueError("not the F&O bhavcopy")
    out: dict[str, list[dict]] = {}
    day = None
    for r in rows:
        if r.get("FinInstrmTp") != "STF":
            continue
        sym, exp = r.get("TckrSymb", "").upper(), _day(r.get("XpryDt"))
        if not sym or not exp:
            continue
        day = day or _day(r.get("TradDt"))
        out.setdefault(sym, []).append({
            "expiry": exp, "close": num(r.get("ClsPric")) or num(r.get("SttlmPric")), "prev": num(r.get("PrvsClsgPric")),
            "under": num(r.get("UndrlygPric")), "oi": int(num(r.get("OpnIntrst")) or 0), "oi_chg": int(num(r.get("ChngInOpnIntrst")) or 0),
            "vol": int(num(r.get("TtlTradgVol")) or 0), "lot": int(num(r.get("NewBrdLotQty")) or 0) or None})
    for cs in out.values():
        cs.sort(key=lambda c: c["expiry"])
    return day, out


def mwpl_rows(text: str) -> tuple[str | None, dict[str, dict]]:
    """The combined open interest file: (its day, {symbol: {"mwpl", "oi", "feq", "pct", "ban"}}). "No Fresh
    Positions" in the limit column is the ban for the next day."""
    rows = X.rows_of(text)
    if rows and not any("MWPL" in k for k in rows[0]):
        raise ValueError("not the combined open interest file")
    out, day = {}, None
    for r in rows:
        r = {re.sub(r"\s+", " ", k).strip().lower(): v for k, v in r.items()}
        sym = (r.get("nse symbol") or r.get("symbol") or "").upper()
        mwpl = num(r.get("mwpl"))
        if not sym or not mwpl:
            continue
        day = day or _day(r.get("date"))
        feq = num(r.get("future equivalent open interest"))
        oi = num(r.get("open interest"))
        limit = str(r.get("limit for next day") or "")
        out[sym] = {"mwpl": int(mwpl), "oi": int(oi) if oi is not None else None, "feq": round(feq) if feq is not None else None,
                    "pct": round(100 * (feq if feq is not None else oi or 0) / mwpl, 2),
                    "ban": "fresh" in limit.lower()}
    return day, out


# ---------- the arithmetic (engine/indicators.py holds the definitions a rule can use) ----------
def buildup(price_chg: float | None, oi_chg: float | None) -> str | None:
    """The market's term for the day's price and open-interest change together; None when either didn't move."""
    if not price_chg or not oi_chg:
        return None
    if oi_chg > 0:
        return "LB" if price_chg > 0 else "SB"
    return "SC" if price_chg > 0 else "LU"


def trading_days_to(day: str, expiry: str) -> int:
    """Trading days after `day` up to and including the expiry (0 on expiry day)."""
    d, e, n = date.fromisoformat(day), date.fromisoformat(expiry), 0
    while d < e and n < 80:
        d += timedelta(days=1)
        n += X.trading(d)
    return n


def stock_row(day: str, cs: list[dict], mw: dict | None, cash: dict | None) -> dict | None:
    """One stock's day from its contracts (near first), its MWPL line and its cash close."""
    from .engine.indicators import basis_pct, oi_change_pct, rollover_pct
    cs = [c for c in cs if c["expiry"] >= day]
    if not cs:
        return None
    near = cs[0]
    total = sum(c["oi"] for c in cs)
    chg = sum(c["oi_chg"] for c in cs)
    spot = near.get("under") or (cash or {}).get("close")
    pc = round(100 * (near["close"] / near["prev"] - 1), 2) if near.get("close") and near.get("prev") else None
    oc = oi_change_pct(total, total - chg)
    oc = round(oc, 2) if oc is not None else None
    # on expiry day the near contract's price is the settlement: the basis is read off the next one
    lead = cs[1] if near["expiry"] == day and len(cs) > 1 else near
    days = (date.fromisoformat(lead["expiry"]) - date.fromisoformat(day)).days
    bp = basis_pct(lead.get("close"), spot)
    row = {"px": near.get("close"), "pc": pc, "oi": total, "oc": oc, "b": buildup(pc, oc),
           "n": near["oi"], "x": cs[1]["oi"] if len(cs) > 1 else 0, "f": sum(c["oi"] for c in cs[2:]),
           "e": near["expiry"], "td": trading_days_to(day, near["expiry"]), "r": None, "s": spot,
           "bp": round(bp, 3) if bp is not None else None,
           "ba": round(bp * 365 / days, 2) if bp is not None and days > 0 else None, "be": lead["expiry"],
           "vol": sum(c["vol"] for c in cs), "lot": near.get("lot"), "m": None, "ban": False}
    r = rollover_pct(near["oi"], total)
    row["r"] = round(r, 2) if r is not None else None
    if mw:
        row.update(m=mw["pct"], ban=bool(mw["ban"]), mwpl=mw["mwpl"], feq=mw.get("feq"))
    return row


def point(row: dict) -> list:
    """What a stock's history keeps for a day: price, its change, OI, its change, the buildup, rollover, annualised
    basis, MWPL use, the share price."""
    return [row.get("px"), row.get("pc"), row.get("oi"), row.get("oc"), row.get("b"), row.get("r"), row.get("ba"),
            row.get("m"), row.get("s")]


POINT = ("px", "pc", "oi", "oc", "b", "r", "ba", "m", "s")


def streak(series: list[list], code: str | None) -> int:
    """Stored days in a row, ending with the newest, with the same buildup."""
    if not code:
        return 0
    n = 0
    for p in reversed(series):
        if len(p) > 5 and p[5] == code:
            n += 1
        else:
            break
    return n


# ---------- the desk ----------
class Desk(X.Desk):
    name = "fno"
    what = "F&O bhavcopy and combined open interest file"
    ready_at = "19:30"
    backfill_days = 130
    store = X.DayStore(PREFIX, KEEP, point)

    def read(self, files: X.Files, day: date):
        text = files.text(FO_BHAV.format(ymd=day.strftime("%Y%m%d")))
        if text is None:
            return None
        got_day, cs = contracts(text)
        if got_day and got_day != day.isoformat():
            return None
        if not cs:
            raise ValueError("no stock futures in the file")
        mw_text = files.text(COMBINE_OI.format(dmy=X.dmy(day)))
        mw_day, mw = mwpl_rows(mw_text) if mw_text else (None, {})
        if mw_day and mw_day != day.isoformat():
            mw = {}
        cash = None
        if any(not (c and c[0].get("under")) for c in cs.values()):
            cash = X.cash_closes(files, day)
        rows = {}
        for sym, c in cs.items():
            r = stock_row(day.isoformat(), c, mw.get(sym), (cash or {}).get(sym))
            if r:
                rows[sym] = r
        return rows, {"mwpl": bool(mw), "stocks": len(rows)}

    def after(self, day: str, rows: dict, prev: dict | None) -> list[dict]:
        """MWPL use crossing 80% either way since the stored day before."""
        if not prev:
            return []
        out = []
        for sym, r in rows.items():
            now, was = r.get("m"), (prev.get(sym) or {}).get("m")
            if now is None or was is None:
                continue
            if was < WATCH_AT <= now:
                way = "up"
            elif now < WATCH_AT <= was:
                way = "down"
            else:
                continue
            ban = " The stock is in the F&O ban period for the next day." if r.get("ban") else ""
            out.append({"kind": "mwpl", "symbol": sym, "day": day, "id": f"{day}:{sym}:mwpl:{way}", "pct": now,
                        "text": f"MWPL use {'rose to' if way == 'up' else 'fell to'} {now:.1f}% on {X.day_words(day)} (from {was:.1f}%).{ban}"})
        return out


DESK = Desk()


# ---------- views ----------
def _view(sym: str, r: dict, ser: list[list] | None, banned: set[str]) -> dict:
    out = {"symbol": sym, **{k: r.get(k) for k in ("px", "pc", "oi", "oc", "b", "n", "x", "f", "e", "td", "r", "s", "bp", "ba",
                                                   "be", "vol", "lot", "m", "mwpl", "feq")}}
    out["ban_next"] = bool(r.get("ban"))
    out["ban_now"] = sym in banned
    out["roll_window"] = r.get("td") is not None and r["td"] <= ROLL_WINDOW
    out["streak"] = streak(ser or [], r.get("b")) if ser is not None else None
    return out


def _banned() -> set[str]:
    try:
        from . import surveillance
        return {s for s, cs in surveillance.snapshot()["flags"].items() if "fo_ban" in cs}
    except Exception:
        return set()


def table() -> dict:
    """Every F&O stock's newest day, alphabetical (the page sorts and filters it)."""
    got = DESK.store.latest()
    out = {"status": X.status(DESK), "rows": [], "as_of": None, "prev": None, "labels": {k: v[0] for k, v in BUILDUP.items()},
           "about": {**ABOUT, **{k: v[1] for k, v in BUILDUP.items()}}, "note": NOTE, "source": SOURCE,
           "ban_at": BAN_AT, "free_at": FREE_AT, "watch_at": WATCH_AT, "roll_window": ROLL_WINDOW}
    if not got:
        return out
    day, rec = got
    sers = DESK.store.all_series()
    banned = _banned()
    out["rows"] = [_view(s, r, [p for p in sers.get(s, []) if p[0] <= day], banned) for s, r in sorted((rec.get("rows") or {}).items())]
    out["as_of"] = day
    prev = DESK.store.latest(before=day)
    out["prev"] = prev[0] if prev else None
    out["mwpl_file"] = bool((rec.get("meta") or {}).get("mwpl"))
    return out


def row_for(symbol: str) -> dict | None:
    """One stock's newest day, for a company page or a holdings line; None when it has no futures."""
    got = DESK.store.latest()
    if not got:
        return None
    r = (got[1].get("rows") or {}).get(symbol)
    if not r:
        return None
    ser = [p for p in DESK.store.series(symbol) if p[0] <= got[0]]
    return {**_view(symbol, r, ser, _banned()), "as_of": got[0]}


def detail(symbol: str, full: bool, rng: str = "6m") -> dict | None:
    sym = symbol.upper()
    row = row_for(sym)
    if row is None:
        return None
    out = {"row": row, "full": full, "history": None, "range": rng, "labels": {k: v[0] for k, v in BUILDUP.items()}}
    if full:
        since = (date.fromisoformat(row["as_of"]) - timedelta(days=RANGES[rng])).isoformat()
        out["history"] = [dict(zip(("day", *POINT), p)) for p in DESK.store.series(sym, since)]
        out["stored"] = len(DESK.store.days())
    return out


# ---------- the routes ----------
router = APIRouter(prefix="/trade/stock-futures", tags=["trade"])


@router.get("")
def stock_futures(profile=Depends(current_profile)):
    """Every F&O stock's newest day: price and OI change, buildup, OI by expiry, rollover, basis and MWPL use."""
    full = allows(profile["_plan"], "stock_futures")
    return ok({**table(), "full": full, "plan_needed": PLANS[FEATURE_PLAN["stock_futures"]]["name"]})


@router.get("/{symbol}")
def stock_future(symbol: str, range: str = Query("6m"), profile=Depends(current_profile)):
    """One stock's newest day, and on Basic its stored history."""
    sym = str(symbol or "").upper()
    if not SYMBOL.match(sym):
        err(400, "bad_symbol", "That doesn't look like a stock symbol.")
    if range not in RANGES:
        err(400, "bad_range", f"Pick a range of {', '.join(RANGES)}.")
    full = allows(profile["_plan"], "stock_futures")
    got = detail(sym, full, range)
    if got is None:
        err(404, "no_futures", f"{sym} has no stock futures in the newest F&O file StratLab has read.")
    return ok({**got, "plan_needed": PLANS[FEATURE_PLAN["stock_futures"]]["name"], "note": NOTE, "about": ABOUT})


def enrich(symbol: str, bars: list[dict]) -> list[dict]:
    """Daily candles of an Indian F&O stock with each stored day's F&O facts as extra columns (fo_oi: open interest,
    fo_near: the near expiry's part of it, fo_fut: the near futures' close, fo_spot: the share's close), for the rule
    values in engine/indicators.py. Days without stored facts are left without them (the rule reads them as blank)."""
    by_day = {p[0]: dict(zip(POINT, p[1:])) for p in DESK.store.series(str(symbol).upper())}
    if not by_day:
        return bars
    out = []
    for b in bars:
        f = by_day.get(str(b.get("t") or "")[:10])
        if f:
            near = f["oi"] * (1 - f["r"] / 100) if f.get("oi") is not None and f.get("r") is not None else None
            b = {**b, "fo_oi": f.get("oi"), "fo_near": near, "fo_fut": f.get("px"), "fo_spot": f.get("s")}
        out.append(b)
    return out
