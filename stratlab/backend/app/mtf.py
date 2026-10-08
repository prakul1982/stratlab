"""Margin-funded (MTF) positions per stock, and what your own MTF position costs.

The exchange's daily Margin Trading Disclosure (published the trading day after the day it covers) gives, for every
stock bought under the margin trading facility, the shares funded and the amount funded by all brokers together at the
end of the day, and for the whole market the book at the start of the day, the fresh exposure taken, the exposure
liquidated and the book at the end (₹ lakh). The stock desks' job (exchange_days.py) keeps each day's file with the
cash market's close, and the exchange's security file gives each stock's shares issued.

From those, for a stock: the amount funded (₹ crore), the shares funded as a percent of shares issued, the amount as
a percent of the stock's market value that day, and the change over a day, 30 and 90 days. The calculator works out a
user's own MTF position: interest to date, the price needed to cover interest and charges, and how far the price can
fall before the broker's margin requirement is breached.

Dated facts and arithmetic. Nothing here calls a stock risky or a position overleveraged."""
import re
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from . import exchange_days as X
from .auth import current_profile
from .intel.net import num
from .plans import FEATURE_PLAN, PLANS, allows
from .responses import err, ok

PREFIX = "mtf:"
MTF_FILE = X.ARCHIVE + "/content/equities/mrg_trading_{dmy}.zip"           # dmy as DDMMYY
SECURITY = X.ARCHIVE + "/content/cm/NSE_CM_security_{dmy}.csv.gz"
SHARES_KEY = PREFIX + "shares"            # {"as_of", "shares": {symbol: shares issued}}
SHARES_EVERY = 7                          # days between reads of the security file
KEEP = 260                                # trading days kept: about a year
MAX_SYMBOLS = 120
RANGES = {"3m": 92, "6m": 183, "1y": 366}
SYMBOL = re.compile(r"^[A-Z0-9&\-]{1,20}$")
SOURCE = "the exchange's daily margin trading disclosure, its cash market closes and its security file (shares issued)"
NOTE = ("From the exchange's margin trading disclosure: what brokers together had funded under the margin trading "
        "facility at the end of each day, published the next trading day. Figures as of the date shown.")
ABOUT = {
    "amount": "The amount brokers together had lent against this stock under the margin trading facility at the end "
              "of the day, in ₹ crore.",
    "pct_shares": "The shares bought with margin funding as a percent of the company's shares issued.",
    "pct_mcap": "The amount funded as a percent of the stock's market value that day (shares issued × closing price). "
                "The amount was lent at the prices the shares were bought at, so the two percentages differ.",
    "book": "Every stock's margin-funded amount added up: the market's margin trading book at the end of the day.",
}


# ---------- reading the files ----------
def _day(text: str) -> str | None:
    from datetime import datetime
    m = re.search(r"(\d{1,2}-[A-Za-z]{3}-\d{4})", text or "")
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%d-%b-%Y").date().isoformat()
    except ValueError:
        return None


def disclosure(text: str) -> tuple[str | None, dict, dict[str, list]]:
    """The margin trading disclosure: (its day, the market's totals {"start", "fresh", "liquidated", "end"} in ₹ lakh,
    {symbol: [shares funded, amount funded in ₹ lakh]})."""
    lines = [ln for ln in str(text or "").splitlines() if ln.strip()]
    if not lines or "<html" in lines[0].lower():
        raise ValueError("not the margin trading disclosure")
    day = _day(" ".join(lines[:3]))
    totals: dict[str, float | None] = {}
    names = (("beginning", "start"), ("fresh", "fresh"), ("liquidated", "liquidated"), ("end of the day", "end"))
    rows: dict[str, list] = {}
    table = False
    for ln in lines:
        parts = [p.strip() for p in ln.split(",")]
        low = ln.lower()
        if not table and len(parts) >= 3 and parts[0].isdigit():
            for word, key in names:
                if word in parts[1].lower():
                    totals[key] = num(parts[2])
            continue
        if low.startswith("symbol,"):
            table = True
            continue
        if table and len(parts) >= 4:
            sym = parts[0].upper()
            qty, amt = num(parts[-2]), num(parts[-1])
            if SYMBOL.match(sym) and qty is not None and amt is not None:
                rows[sym] = [int(qty), round(amt, 2)]
    if not rows:
        raise ValueError("no stock lines")
    return day, totals, rows


def shares_rows(text: str) -> dict[str, int]:
    """Shares issued per equity, from the exchange's security file (IssdCptl on the EQ or BE line)."""
    out: dict[str, int] = {}
    for r in X.rows_of(text):
        sym, series = (r.get("TckrSymb") or "").upper(), (r.get("SctySrs") or "").upper()
        n = num(r.get("IssdCptl"))
        if SYMBOL.match(sym) and series in ("EQ", "BE", "BZ", "SM", "ST") and n and n > 0:
            if sym not in out or series == "EQ":
                out[sym] = int(n)
    return out


def shares() -> dict:
    return X._load(SHARES_KEY, {})


# ---------- the desk ----------
def point(row: list) -> list:
    """A stock's day: shares funded, amount funded (₹ lakh), the share's close."""
    return list(row[:3])


class Desk(X.Desk):
    name = "mtf"
    what = "margin trading disclosure"
    ready_at = "19:30"
    lag = 1                                  # the day's disclosure comes out the next trading day
    backfill_days = 250
    store = X.DayStore(PREFIX, KEEP, point, shards=24)

    def read(self, files: X.Files, day: date):
        text = files.text(MTF_FILE.format(dmy=day.strftime("%d%m%y")))
        if text is None:
            return None
        got_day, totals, lines = disclosure(text)
        if got_day and got_day != day.isoformat():
            return None
        cash = X.cash_closes(files, day) or {}
        rows = {s: [q, a, (cash.get(s) or {}).get("close")] for s, (q, a) in lines.items()}
        self._shares(files, day)
        return rows, {"totals": totals, "stocks": len(rows)}

    def _shares(self, files: X.Files, day: date):
        cur = shares()
        if cur.get("as_of") and str(cur["as_of"]) >= (day - timedelta(days=SHARES_EVERY)).isoformat():
            return
        try:
            text = files.text(SECURITY.format(dmy=X.dmy(day)))
        except Exception:
            return
        got = shares_rows(text) if text else {}
        if len(got) >= 100:                   # the real file has thousands; a stub is a broken answer
            X._save(SHARES_KEY, {"as_of": day.isoformat(), "shares": got})

    def after(self, day: str, rows: dict, prev: dict | None) -> list[dict]:
        """Each stock's funded share of shares issued on the new day, for the alerts that watch a level."""
        sh = shares().get("shares") or {}
        out = []
        for sym, r in rows.items():
            n = sh.get(sym)
            if n and r[0] is not None:
                was = (prev or {}).get(sym)
                out.append({"kind": "mtf", "symbol": sym, "day": day, "id": f"{day}:{sym}:mtf",
                            "pct": round(100 * r[0] / n, 3), "was": round(100 * was[0] / n, 3) if was else None,
                            "crore": round(r[1] / 100, 2)})
        return out


DESK = Desk()


# ---------- the arithmetic ----------
def pct_shares(qty, issued) -> float | None:
    return round(100 * qty / issued, 3) if qty is not None and issued else None


def pct_mcap(amount_lakh, issued, close) -> float | None:
    """The amount funded as a percent of the market value (shares issued × close)."""
    if amount_lakh is None or not issued or not close:
        return None
    return round(100 * amount_lakh * 1e5 / (issued * close), 3)


def _back(series: list[list], day: str, days: int) -> list | None:
    """The newest stored point on or before `days` calendar days back."""
    cut = (date.fromisoformat(day) - timedelta(days=days)).isoformat()
    older = [p for p in series if p[0] <= cut]
    return older[-1] if older else None


def _chg(now: list, then: list | None) -> dict | None:
    if not then:
        return None
    return {"from": then[0], "shares": now[1] - then[1], "crore": round((now[2] - then[2]) / 100, 2),
            "pct": round(100 * (now[2] / then[2] - 1), 2) if then[2] else None}


def for_symbol(symbol: str, full: bool = False, rng: str = "1y") -> dict:
    sym = symbol.upper()
    got = DESK.store.latest()
    out = {"symbol": sym, "as_of": got[0] if got else None, "funded": False}
    if not got:
        return out
    day, rec = got
    r = (rec.get("rows") or {}).get(sym)
    if not r:
        return out
    issued = (shares().get("shares") or {}).get(sym)
    ser = DESK.store.series(sym)
    now = [day, r[0], r[1], r[2]]
    out.update(funded=True, shares=r[0], crore=round(r[1] / 100, 2), close=r[2], issued=issued,
               pct_shares=pct_shares(r[0], issued), pct_mcap=pct_mcap(r[1], issued, r[2]),
               d30=_chg(now, _back(ser, day, 30)), d90=_chg(now, _back(ser, day, 90)))
    prev = [p for p in ser if p[0] < day]
    out["day"] = _chg(now, prev[-1]) if prev else None
    if full:
        since = (date.fromisoformat(day) - timedelta(days=RANGES[rng])).isoformat()
        out["history"] = [{"day": p[0], "shares": p[1], "crore": round(p[2] / 100, 2), "close": p[3] if len(p) > 3 else None,
                           "pct_shares": pct_shares(p[1], issued)} for p in ser if p[0] >= since]
    return out


def market(full: bool = False) -> dict:
    """The market's margin trading book (₹ crore) on the newest day, its change over the day and 30 days, and on Basic
    each stored day's."""
    days = DESK.store.days()
    if not days:
        return {"as_of": None}
    rec = DESK.store.get(days[-1]) or {}
    t = (rec.get("meta") or {}).get("totals") or {}
    cr = lambda v: round(v / 100, 2) if isinstance(v, (int, float)) else None        # noqa: E731
    out = {"as_of": days[-1], "end": cr(t.get("end")), "start": cr(t.get("start")), "fresh": cr(t.get("fresh")),
           "liquidated": cr(t.get("liquidated")), "stocks": (rec.get("meta") or {}).get("stocks")}
    cut = (date.fromisoformat(days[-1]) - timedelta(days=30)).isoformat()
    then = next((d for d in reversed(days) if d <= cut), None)
    if then:
        tt = ((DESK.store.get(then) or {}).get("meta") or {}).get("totals") or {}
        if tt.get("end") and t.get("end"):
            out["d30"] = {"from": then, "crore": cr(t["end"] - tt["end"]), "pct": round(100 * (t["end"] / tt["end"] - 1), 2)}
    if full:
        pts = []
        for d in days[-260:]:
            tt = ((DESK.store.get(d) or {}).get("meta") or {}).get("totals") or {}
            if tt.get("end"):
                pts.append({"day": d, "end": cr(tt["end"]), "fresh": cr(tt.get("fresh")), "liquidated": cr(tt.get("liquidated"))})
        out["history"] = pts
    return out


def screen_values() -> dict[str, float]:
    """Every funded stock's shares funded as a percent of shares issued, on the newest day (the screens' filter)."""
    got = DESK.store.latest()
    if not got:
        return {}
    sh = shares().get("shares") or {}
    return {s: v for s, r in (got[1].get("rows") or {}).items() if (v := pct_shares(r[0], sh.get(s))) is not None}


# ---------- your own MTF position ----------
class CostReq(BaseModel):
    buy: float = Field(..., gt=0, le=1e7)                 # price paid per share
    qty: float = Field(..., gt=0, le=1e8)
    margin_pct: float = Field(..., gt=0, lt=100)           # the part you paid yourself, % of the buy value
    rate_pct: float = Field(..., ge=0, le=60)             # the broker's interest, % a year
    days: int = Field(..., ge=0, le=3650)                 # days the funding has been open
    charges: float = Field(0, ge=0, le=1e8)               # pledge, unpledge and other charges in ₹, all told
    price: float | None = Field(None, gt=0, le=1e7)       # the price now, when known
    maint_pct: float = Field(0, ge=0, lt=100)             # the margin % the broker requires you to keep


def cost(req: CostReq) -> dict:
    """Plain arithmetic on one MTF position. Interest is charged daily on the funded amount (simple interest over the
    days given, as most brokers work it out); the price needed to cover costs is the buy price plus interest and
    charges per share; the margin is breached when (value − funded amount − interest) / value falls under the
    broker's margin %."""
    value = req.buy * req.qty
    funded = value * (1 - req.margin_pct / 100)
    own = value - funded
    interest = funded * req.rate_pct / 100 * req.days / 365
    costs = interest + req.charges
    need = req.buy + costs / req.qty
    out = {"value": round(value, 2), "funded": round(funded, 2), "own": round(own, 2), "interest": round(interest, 2),
           "interest_day": round(funded * req.rate_pct / 100 / 365, 2), "costs": round(costs, 2),
           # six places: rounding to three first made 0.92466 read "0.925" and then "+0.93%" on the page (R5O-033)
           "breakeven": round(need, 2), "breakeven_pct": round(100 * (need / req.buy - 1), 6),
           "cost_pct_own": round(100 * costs / own, 2) if own else None}
    owed = funded + interest
    if req.maint_pct:
        # value × (1 − m) = owed  →  the price at which the margin left is exactly the broker's %
        breach = owed / (req.qty * (1 - req.maint_pct / 100))
        ref = req.price or req.buy
        out.update(breach_price=round(breach, 2), breach_fall_pct=round(100 * (1 - breach / ref), 2), breach_from=ref)
    if req.price:
        now_value = req.price * req.qty
        out.update(price=req.price, now_value=round(now_value, 2),
                   margin_now_pct=round(100 * (now_value - owed) / now_value, 2),
                   pnl=round(now_value - value - costs, 2), pnl_pct_own=round(100 * (now_value - value - costs) / own, 2) if own else None)
    return out


# ---------- the routes ----------
router = APIRouter(prefix="/invest/margin-funding", tags=["invest"])


def _full(profile) -> bool:
    return allows(profile["_plan"], "mtf")


@router.get("")
def margin_funding(profile=Depends(current_profile)):
    """The market's MTF book and each stock you hold or watch: funded amount, shares of shares issued, changes."""
    held, watch = X.mine(profile["id"], MAX_SYMBOLS)
    full = _full(profile)
    rows = []
    for s in held + watch:
        r = for_symbol(s)
        r["held"], r["watched"] = s in held, s in watch
        rows.append(r)
    sh = shares()
    return ok({"market": market(full), "rows": rows, "status": X.status(DESK), "full": full, "about": ABOUT,
               "shares_as_of": sh.get("as_of"), "note": NOTE, "source": SOURCE,
               "plan_needed": PLANS[FEATURE_PLAN["mtf"]]["name"]})


@router.post("/cost")
def margin_cost(req: CostReq, profile=Depends(current_profile)):
    """Your MTF position worked out: interest to date, the price that covers the costs and the margin breach price."""
    return ok(cost(req))


@router.get("/{symbol}")
def margin_funding_one(symbol: str, range: str = Query("1y"), profile=Depends(current_profile)):
    """One stock's margin-funded amount now, and on Basic each stored day's."""
    sym = str(symbol or "").upper()
    if not SYMBOL.match(sym):
        err(400, "bad_symbol", "That doesn't look like a stock symbol.")
    if range not in RANGES:
        err(400, "bad_range", f"Pick a range of {', '.join(RANGES)}.")
    full = _full(profile)
    return ok({**for_symbol(sym, full, range), "full": full, "status": X.status(DESK), "about": ABOUT, "note": NOTE,
               "plan_needed": PLANS[FEATURE_PLAN["mtf"]]["name"]})
