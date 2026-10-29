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
import zlib
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from . import corp_actions, db, exchange_days as X
from .auth import current_profile
from .intel.net import num
from .packed import pack, unpack
from .plans import FEATURE_PLAN, PLANS, allows
from .responses import err, ok

PREFIX = "mtf:"
MTF_FILE = X.ARCHIVE + "/content/equities/mrg_trading_{dmy}.zip"           # dmy as DDMMYY
SECURITY = X.ARCHIVE + "/content/cm/NSE_CM_security_{dmy}.csv.gz"
SHARES_KEY = PREFIX + "shares"            # {"as_of", "shares": {symbol: shares issued}}
SHARES_EVERY = 7                          # days between reads of the security file
KEEP = 260                                # trading days kept: about a year
MAX_SYMBOLS = 120
RANGES = {"3m": 92, "6m": 183, "1y": 366, "3y": 1096, "5y": 1830, "all": None}
# O2 (29 Oct): the history beyond the daily window. The exchange's archive has the margin trading disclosure back to 1 Dec 2021, so
# the market's totals (one row a day) and each stock's weekly point are read from it once, on the desks' job, and kept
LONG_KEY = PREFIX + "long"                # {"days": {day: [start, fresh, liquidated, end]}} in ₹ lakh, every trading day from DEEP_FROM
WEEK_PREFIX = PREFIX + "w:"              # w:<n> = packed {symbol: [[day ordinal, shares funded, amount ₹ lakh], ...]}: each week's last trading day
WEEK_SHARDS = 24
DEEP_FROM = "2021-12-01"                 # the first file the archive has
DEEP_STEP = 25                           # days one run of the job reads
DEEP_MISSES = 3                          # tries for an old day the archive answers "not there" before it's passed by
DEEP_STATE = PREFIX + "deep"
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


def _cells(line: str) -> list[str]:
    import csv
    try:
        return [c.strip() for c in next(csv.reader([line]))]
    except (StopIteration, csv.Error):
        return [c.strip() for c in line.split(",")]


def disclosure(text: str) -> tuple[str | None, dict, dict[str, list]]:
    """The margin trading disclosure: (its day, the market's totals {"start", "fresh", "liquidated", "end"} in ₹ lakh,
    {symbol: [shares funded, amount funded in ₹ lakh]}).

    Two layouts come from the exchange. The usual file has one table of totals and one of stocks. A file revised for late
    member submissions ("Data Revised for reporting date …") holds two side by side, the first as first reported (all zero
    in 18 Aug 2026's) and the second "as on current date", with the late submissions in: the second is the day's figures
    (LIVE2: the back-fill stopped on that day for good, "no stock lines", and the chart's history began on 19 Aug)."""
    lines = [ln for ln in str(text or "").splitlines() if ln.strip()]
    if not lines or "<html" in lines[0].lower():
        raise ValueError("not the margin trading disclosure")
    day = _day(" ".join(lines[:3]))
    totals: dict[str, float | None] = {}
    names = (("beginning", "start"), ("fresh", "fresh"), ("liquidated", "liquidated"), ("end of the day", "end"))
    rows: dict[str, list] = {}
    heads: list[int] = []
    for ln in lines:
        c = _cells(ln)
        low = [x.lower() for x in c]
        if not heads and any(x == "symbol" for x in low):
            heads = [i for i, x in enumerate(low) if x == "symbol"]
            continue
        if not heads:
            # a totals line: the "Particulars" label with its figure after it; in the revised layout the right-hand set wins
            for i, x in enumerate(low):
                for word, key in names:
                    if word in x and i > 0 and c[i - 1].isdigit():
                        v = num(c[i + 1]) if i + 1 < len(c) else None
                        if v is not None:
                            totals[key] = v
            continue
        # a stock line: the last group of columns with a symbol in it (the revised file's second), else the first
        for h in reversed(heads):
            g = c[h:h + 4]
            if len(g) >= 4 and g[0]:
                sym = g[0].upper()
                qty, amt = num(g[2]), num(g[3])
                if SYMBOL.match(sym) and qty is not None and amt is not None:
                    rows[sym] = [int(qty), round(amt, 2)]
                    break
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


# ---------- the long history (O2) ----------
def long_days() -> dict:
    """Every trading day's market totals from DEEP_FROM: {day: [start, fresh, liquidated, end]} in ₹ lakh."""
    return (X._load(LONG_KEY, {}).get("days")) or {}


def week_end(d: date) -> bool:
    """Whether `d` is its week's last trading day (the next trading day falls in another week)."""
    n = d
    for _ in range(10):
        n += timedelta(days=1)
        if X.trading(n):
            return n.isocalendar()[:2] != d.isocalendar()[:2]
    return True


def _week_shard(symbol: str) -> str:
    return f"{WEEK_PREFIX}{zlib.crc32(symbol.encode()) % WEEK_SHARDS}"


def weekly_series(symbol: str) -> list[list]:
    """One stock's weekly points, oldest first: [[day, shares funded, amount ₹ lakh], ...]."""
    key = _week_shard(symbol.upper())
    shard = X._cache.get(("w", key))
    if shard is None:
        shard = unpack(db.get_setting(key))
        X._cache.set(("w", key), shard, 300)
    return [[date.fromordinal(o).isoformat(), q, a] for o, q, a in shard.get(symbol.upper()) or []]


def record_long(items: list[tuple[str, dict, dict | None]]):
    """Keep days read from the archive: each day's market totals, and (on a week's last trading day, with its stock lines) every
    stock's point. `items`: [(day, totals, rows or None)], rows as disclosure() gives them."""
    if not items:
        return
    with X._lock:
        cur = db.json_value(db.get_setting(LONG_KEY), {})
        days = dict(cur.get("days") or {})
        by_shard: dict[str, dict[str, list]] = {}
        for day, totals, rows in items:
            if all(totals.get(k) is not None for k in ("start", "fresh", "liquidated", "end")):
                days[day] = [totals["start"], totals["fresh"], totals["liquidated"], totals["end"]]
            if rows and week_end(date.fromisoformat(day)):
                o = date.fromisoformat(day).toordinal()
                for sym, (q, a) in rows.items():
                    by_shard.setdefault(_week_shard(sym), {}).setdefault(sym, []).append([o, int(q), a])
        for key, add_ in sorted(by_shard.items()):
            have = unpack(db.get_setting(key))
            for sym, pts in add_.items():
                old = {p[0]: p for p in have.get(sym) or []}
                old.update({p[0]: p for p in pts})
                have[sym] = [old[o] for o in sorted(old)]
            db.set_setting(key, pack(have))
            X._cache.set(("w", key), have, 300)
        X._save(LONG_KEY, {"days": {d: days[d] for d in sorted(days)}})


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

    def deep(self, files: X.Files, today: date, now: datetime | None = None, step: int = DEEP_STEP) -> dict:
        """Read up to `step` days the long history lacks, newest first, back to DEEP_FROM: the archive's margin file alone (not the cash
        closes), keeping the day's totals and, on a week's last day, every stock's point. A day the archive says isn't there is asked
        DEEP_MISSES times and passed by; six in a row is the archive turning us away, and the run stops until the next one. A file this
        reader can't make sense of twice is passed by the same way."""
        now = now or X.ist_now()
        st = X._load(DEEP_STATE, {}, 60)
        tries = dict(st.get("tries") or {})
        exp = X.expected(now, self.ready_at, self.lag)
        if not exp:
            return st
        have = long_days()
        recent = (exp - timedelta(days=10)).isoformat()
        batch: list[tuple[str, dict, dict | None]] = []
        d, misses, err_ = exp, 0, None
        while d.isoformat() >= DEEP_FROM and len(batch) + misses < step:
            key = d.isoformat()
            if X.trading(d) and key not in have and (key >= recent or tries.get(key, 0) < DEEP_MISSES):
                try:
                    text = files.text(MTF_FILE.format(dmy=d.strftime("%d%m%y")))
                    got = disclosure(text) if text is not None else None
                except X.SourceError as e:
                    err_ = str(e)[:200]
                    break
                except (ValueError, KeyError, TypeError):
                    got = False
                if got:
                    if got[0] and got[0] != key:
                        got = None
                    else:
                        batch.append((key, got[1], got[2]))
                        misses = 0
                if not got:
                    if key < recent:
                        tries[key] = tries.get(key, 0) + 1
                    misses += 1
                    if misses >= X.MISS_RUN:
                        err_ = f"The archive had none of {X.MISS_RUN} trading days in a row from {X.day_words(key)}; trying again later."
                        break
            d -= timedelta(days=1)
        if not (batch or err_ or tries != (st.get("tries") or {})):
            return st                          # nothing to read, nothing new to say: no write
        record_long(batch)
        left = d.isoformat() >= DEEP_FROM
        st = {"tries": {k: v for k, v in tries.items() if v}, "read": st.get("read", 0) + len(batch), "next": d.isoformat(),
              "done": not left and not err_, "error": err_, "at": now.isoformat(timespec="minutes")}
        X._save(DEEP_STATE, st)
        return st

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
        doc = shares()
        sh = doc.get("shares") or {}
        moved = _split_since_shares(doc, day)
        out = []
        for sym, r in rows.items():
            n = None if sym in moved else sh.get(sym)
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


def _splits(sym: str) -> list[str]:
    """Ex-dates of the splits and bonuses stored for the stock (read from what is stored, nothing fetched)."""
    return [a["ex_date"] for a in corp_actions.actions_for("IN", sym, fetch=False) if corp_actions.adjusts(a)]


def _split_since_shares(sh: dict, day: str, sym_splits: list[str] | None = None) -> set[str] | bool:
    """Shares issued is re-read only every SHARES_EVERY days, but the funded share count is of the shares after a split or
    bonus from its ex-date: until the shares file is read again, a percent of shares issued would divide new shares by old.
    With `sym_splits` (one stock's ex-dates): whether one fell after the file's date; otherwise the set of symbols it did."""
    as_of = str(sh.get("as_of") or "")
    if sym_splits is not None:
        return any(as_of < d <= day for d in sym_splits)
    try:
        frm = date.fromisoformat(as_of) + timedelta(days=1)
        return {a["symbol"] for a in corp_actions.between("IN", frm, date.fromisoformat(day)) if corp_actions.adjusts(a)}
    except ValueError:
        return set()


def _chg(now: list, then: list | None, splits: list[str] = ()) -> dict | None:
    if not then:
        return None
    cut = any(then[0] < d <= now[0] for d in splits)          # a split or bonus between: raw share counts don't compare
    return {"from": then[0], "shares": None if cut else now[1] - then[1], "crore": round((now[2] - then[2]) / 100, 2),
            "pct": round(100 * (now[2] / then[2] - 1), 2) if then[2] else None}


def for_symbol(symbol: str, full: bool = False, rng: str = "all") -> dict:
    sym = symbol.upper()
    got = DESK.store.latest()
    out = {"symbol": sym, "as_of": got[0] if got else None, "funded": False}
    if not got:
        return out
    day, rec = got
    r = (rec.get("rows") or {}).get(sym)
    if not r:
        return out
    doc = shares()
    issued = (doc.get("shares") or {}).get(sym)
    ser = DESK.store.series(sym)
    sp = _splits(sym)
    if _split_since_shares(doc, day, sp):
        issued = None                      # not the figure for today's shares until the file is read again
    now = [day, r[0], r[1], r[2]]
    out.update(funded=True, shares=r[0], crore=round(r[1] / 100, 2), close=r[2], issued=issued,
               pct_shares=pct_shares(r[0], issued), pct_mcap=pct_mcap(r[1], issued, r[2]),
               d30=_chg(now, _back(ser, day, 30), sp), d90=_chg(now, _back(ser, day, 90), sp))
    prev = [p for p in ser if p[0] < day]
    out["day"] = _chg(now, prev[-1], sp) if prev else None
    if full:
        # the daily points, and before the first of them the week's last day's point from the long history (O2)
        first = ser[0][0] if ser else None
        pts = [w for w in weekly_series(sym) if not first or w[0] < first] + ser
        since = None if RANGES[rng] is None else (date.fromisoformat(day) - timedelta(days=RANGES[rng])).isoformat()
        out["history"] = [{"day": p[0], "shares": p[1], "crore": round(p[2] / 100, 2), "close": p[3] if len(p) > 3 else None,
                           "pct_shares": None if any(p[0] < d for d in sp) else pct_shares(p[1], issued)} for p in pts if since is None or p[0] >= since]
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
        # every trading day from DEEP_FROM (the long history), and any day only the daily store has yet
        pts = dict(long_days())
        for d in days[-KEEP:]:
            if d in pts:
                continue
            tt = ((DESK.store.get(d) or {}).get("meta") or {}).get("totals") or {}
            if tt.get("end"):
                pts[d] = [tt.get("start"), tt.get("fresh"), tt.get("liquidated"), tt["end"]]
        out["history"] = [{"day": d, "end": cr(v[3]), "fresh": cr(v[1]), "liquidated": cr(v[2])} for d, v in sorted(pts.items())]
    return out


def screen_values() -> dict[str, float]:
    """Every funded stock's shares funded as a percent of shares issued, on the newest day (the screens' filter)."""
    got = DESK.store.latest()
    if not got:
        return {}
    doc = shares()
    sh = doc.get("shares") or {}
    moved = _split_since_shares(doc, got[0])
    return {s: v for s, r in (got[1].get("rows") or {}).items() if s not in moved and (v := pct_shares(r[0], sh.get(s))) is not None}


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
def margin_funding_one(symbol: str, range: str = Query("all"), profile=Depends(current_profile)):
    """One stock's margin-funded amount now, and on Basic each stored day's."""
    sym = str(symbol or "").upper()
    if not SYMBOL.match(sym):
        err(400, "bad_symbol", "That doesn't look like a stock symbol.")
    if range not in RANGES:
        err(400, "bad_range", f"Pick a range of {', '.join(RANGES)}.")
    full = _full(profile)
    return ok({**for_symbol(sym, full, range), "full": full, "status": X.status(DESK), "about": ABOUT, "note": NOTE,
               "plan_needed": PLANS[FEATURE_PLAN["mtf"]]["name"]})
