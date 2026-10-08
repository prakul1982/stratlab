"""Test a stock or ETF SIP before setting one up (Invest + Money): a fixed amount (or a fixed number of shares) every
day, week or month into one Indian stock or ETF or a split across up to 10, with an optional yearly step-up and an
optional dip rule, run over past daily closes with the real charges of each purchase (STT, exchange and SEBI fees,
stamp duty, GST and the user's brokerage, from engine/costs.py).

Results: money put in, value, XIRR, the deepest fall of the pot, the longest time the pot was worth less than the money
put in, charges, and the same money as one lump sum on day one. The verdict's twist (Basic, with the dip rules): the same
SIP from every start month in the price history, as the spread of XIRRs, and for a dip rule how often it beat the plain
SIP. History of the user's own rule, labelled as such: no "best day" or "best dip level" anywhere."""
import math
from datetime import date, timedelta

from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from .auth import current_profile
from .engine import costs as C
from .money_mf import xirr
from .plans import FEATURE_PLAN, PLANS, allows
from .responses import err, ok

MAX_LEGS = 10
MAX_YEARS = 10
HISTORY_DAYS = 3650             # the daily closes read: ten years, the most the market data keeps
MAX_STARTS = 120                # start months in the spread (every month up to ten years)
LOOKBACKS = (20, 60, 125, 252)  # trading days for the "recent high" of a dip rule
FREQS = ("daily", "weekly", "monthly")
RULES = ("plain", "only_dips", "extra_on_dips")
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday")

DISCLAIMER = ("History of the rule you set, on past prices with today's charges. Past results don't tell you what a SIP "
              "will do next. Not investment advice, and not a suggestion to start or change a SIP.")
ASSUMPTIONS = [
    "Each instalment is invested at that day's close (or the next trading day's when the market was shut), in whole shares; "
    "what can't pay for a whole share waits and joins the next instalment.",
    "Charges are today's for delivery purchases: STT, exchange and SEBI fees, stamp duty and GST, plus your brokerage per "
    "order. No sale is made, so no selling charges or tax are counted.",
    "Value is the shares at the last close plus any cash waiting. XIRR treats each instalment as money in and the value as "
    "money out on the last day.",
    "Deepest fall: the largest drop of the pot from a high, leaving out the instalments themselves (a time-weighted index). "
    "Longest underwater: the longest stretch the pot was worth less than the money put in so far.",
    "A step-up raises the instalment by the same share on each anniversary of the first instalment.",
    "Only on dips: each instalment waits as cash until a close at least the set fall below the highest close of the chosen "
    "number of trading days, then all the waiting cash is invested. Extra on dips: an instalment due on such a day is raised by the "
    "set share.",
    "The lump sum puts all the money the SIP put in, on the SIP's first day, into the same split.",
    "Closes come from the market data source and may not be adjusted for every corporate action; dividends aren't added.",
]


# ---------- the arithmetic ----------
def _day(t) -> str:
    return str(t)[:10]


def charge_rate() -> float:
    """Charges on a delivery purchase as a share of its value, before brokerage (STT, fees, stamp duty, GST on fees)."""
    r = C.IN_EQUITY
    return r["stt"] + (r["exchange"] + r["sebi"]) * (1 + C.GST) + r["stamp_buy"]


def buy(cash: float, price: float, brokerage: float, kind: str = "in_eq") -> tuple[int, float, float]:
    """Whole shares `cash` buys at `price` with charges: (shares, money spent with charges, stamp duty)."""
    if price <= 0 or cash <= brokerage * (1 + C.GST):
        return 0, 0.0, 0.0
    q = int(max(0.0, cash - brokerage * (1 + C.GST)) // (price * (1 + charge_rate())))
    while q > 0:
        c = C.order_costs(kind, "buy", q, price, brokerage)
        spent = q * price + C.total(c)
        if spent <= cash + 1e-9:
            return q, spent, c.get("stamp", 0.0)
        q -= 1
    return 0, 0.0, 0.0


def schedule(days: list[str], start: str, end: str, freq: str, dom: int = 1, weekday: int = 0) -> list[str]:
    """The trading days instalments fall on: every trading day; or the first trading day on or after each week's
    `weekday` (0 Monday) or each month's day `dom`."""
    days = [d for d in days if start <= d <= end]
    if freq == "daily":
        return days
    targets, a, b = [], date.fromisoformat(start), date.fromisoformat(end)
    if freq == "weekly":
        t = a + timedelta(days=(weekday - a.weekday()) % 7)
        while t <= b:
            targets.append(t.isoformat())
            t += timedelta(days=7)
    else:
        y, m = a.year, a.month
        while True:
            t = date(y, m, min(dom, 28))
            if t > b:
                break
            if t >= a:
                targets.append(t.isoformat())
            y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    out, i = [], 0
    for t in targets:
        while i < len(days) and days[i] < t:
            i += 1
        if i < len(days) and (not out or days[i] != out[-1]):
            out.append(days[i])
    return out


def anniversaries(first: str, d: str) -> int:
    """Whole years from `first` to `d`."""
    n = int(d[:4]) - int(first[:4])
    return n - 1 if d[5:] < first[5:] else n


def drawdown(index: list[float]) -> float:
    peak, worst = 0.0, 0.0
    for v in index:
        peak = max(peak, v)
        if peak > 0:
            worst = min(worst, v / peak - 1)
    return worst


def underwater(days: list[str], values: list[float], invested: list[float]) -> tuple[int, str | None, str | None]:
    """The longest stretch (calendar days) with the pot below the money put in so far, and its first and last day."""
    best, best_a, best_b, a = 0, None, None, None
    for d, v, i in zip(days, values, invested):
        if i > 0 and v < i - 1e-6:
            a = a or d
            n = (date.fromisoformat(d) - date.fromisoformat(a)).days
            if n > best:
                best, best_a, best_b = n, a, d
        else:
            a = None
    return best, best_a, best_b


def simulate(legs: list[dict], plan: dict, start: str, end: str, keep: bool = True) -> dict | None:
    """One run. legs: [{"symbol", "weight", "closes": {day: close}, "days": [sorted days], "high": {day: recent high}}];
    plan: {"mode", "amount", "qty", "freq", "dom", "weekday", "step_up", "rule", "dip", "extra", "brokerage"}."""
    cal = sorted({d for leg in legs for d in leg["days"] if start <= d <= end})
    if len(cal) < 2:
        return None
    sched = set(schedule(cal, start, end, plan["freq"], plan["dom"], plan["weekday"]))
    if not sched:
        return None
    first = min(sched)
    n = len(legs)
    units, pots, spent_leg, buys = [0] * n, [0.0] * n, [0.0] * n, [0] * n
    last = [None] * n
    flows, invested, charges, stamp = [], 0.0, 0.0, 0.0
    index, idx_v, values, put_in, days = [], 1.0, [], [], []
    prev_value = 0.0
    rule, dip = plan["rule"], plan["dip"]

    def is_dip(leg, d):
        hi = leg["high"].get(d)
        return hi is not None and leg["closes"][d] <= hi * (1 - dip)
    for d in cal:
        add = 0.0
        if d in sched:
            years = anniversaries(first, d)
            grow = (1 + plan["step_up"]) ** years
            for j, leg in enumerate(legs):
                if plan["mode"] == "qty":
                    if d in leg["closes"]:
                        q = max(1, round(plan["qty"] * leg["weight"] * grow)) if leg["weight"] else 0
                        if q:
                            c = C.order_costs("in_eq", "buy", q, leg["closes"][d], plan["brokerage"])
                            cost = q * leg["closes"][d] + C.total(c)
                            units[j] += q
                            spent_leg[j] += cost
                            buys[j] += 1
                            add += cost
                            charges += C.total(c)
                            stamp += c.get("stamp", 0.0)
                    continue
                part = plan["amount"] * grow * leg["weight"]
                if rule == "extra_on_dips" and d in leg["closes"] and is_dip(leg, d):
                    part *= 1 + plan["extra"]
                pots[j] += part
                add += part
            if add:
                invested += add
                flows.append((d, -add))
        if plan["mode"] == "amount":
            for j, leg in enumerate(legs):
                if d not in leg["closes"] or pots[j] <= 0:
                    continue
                if rule == "only_dips" and not is_dip(leg, d):
                    continue
                q, cost, st = buy(pots[j], leg["closes"][d], plan["brokerage"])
                if q:
                    units[j] += q
                    pots[j] -= cost
                    spent_leg[j] += cost
                    buys[j] += 1
                    charges += cost - q * leg["closes"][d]
                    stamp += st
        for j, leg in enumerate(legs):
            if d in leg["closes"]:
                last[j] = leg["closes"][d]
        value = sum(units[j] * (last[j] or 0) for j in range(n)) + sum(pots)
        if prev_value > 0:
            idx_v *= (value - add) / prev_value
        prev_value = value
        index.append(idx_v)
        values.append(value)
        put_in.append(invested)
        days.append(d)
    if invested <= 0:
        return None
    value = values[-1]
    x = xirr(flows + [(days[-1], value)])
    uw, uw_a, uw_b = underwater(days, values, put_in)
    out = {"start": first, "end": days[-1], "instalments": len(flows), "invested": round(invested, 2), "value": round(value, 2),
           "gain": round(value - invested, 2), "gain_pct": round((value - invested) / invested * 100, 2), "xirr": x,
           "deepest_fall_pct": round(drawdown(index) * 100, 2), "underwater_days": uw, "underwater_from": uw_a, "underwater_to": uw_b,
           "charges": round(charges, 2), "stamp": round(stamp, 2), "cash_waiting": round(sum(pots), 2)}
    if keep:
        out["legs"] = [{"symbol": leg["symbol"], "weight": round(leg["weight"] * 100, 2), "units": units[j], "buys": buys[j],
                        "spent": round(spent_leg[j], 2), "avg_price": round((spent_leg[j]) / units[j], 2) if units[j] else None,
                        "last": last[j], "value": round(units[j] * (last[j] or 0), 2), "cash_waiting": round(pots[j], 2)}
                       for j, leg in enumerate(legs)]
        step = max(1, len(days) // 160)
        pick = list(range(0, len(days), step))
        if pick[-1] != len(days) - 1:
            pick.append(len(days) - 1)
        out["series"] = [{"d": days[i], "invested": round(put_in[i], 2), "value": round(values[i], 2)} for i in pick]
    return out


def _once(legs, plan, first, end):
    """A run whose only instalment is on `first` (the lump sum)."""
    cal = sorted({d for leg in legs for d in leg["days"] if first <= d <= end})
    n = len(legs)
    units, pots, last = [0] * n, [0.0] * n, [None] * n
    charges = stamp = 0.0
    index, idx_v, prev, values, days = [], 1.0, 0.0, [], []
    for d in cal:
        add = 0.0
        if d == first:
            for j, leg in enumerate(legs):
                pots[j] += plan["amount"] * leg["weight"]
            add = plan["amount"]
        for j, leg in enumerate(legs):
            if d in leg["closes"] and pots[j] > 0:
                q, cost, st = buy(pots[j], leg["closes"][d], plan["brokerage"])
                if q:
                    units[j] += q
                    pots[j] -= cost
                    charges += cost - q * leg["closes"][d]
                    stamp += st
            if d in leg["closes"]:
                last[j] = leg["closes"][d]
        value = sum(units[j] * (last[j] or 0) for j in range(n)) + sum(pots)
        if prev > 0:
            idx_v *= (value - add) / prev
        prev = value
        index.append(idx_v)
        values.append(value)
        days.append(d)
    if not days:
        return None
    x = xirr([(first, -plan["amount"]), (days[-1], values[-1])])
    return {"invested": round(plan["amount"], 2), "value": round(values[-1], 2), "gain": round(values[-1] - plan["amount"], 2),
            "xirr": x, "deepest_fall_pct": round(drawdown(index) * 100, 2), "charges": round(charges, 2),
            "series": [{"d": days[i], "value": round(values[i], 2)} for i in range(0, len(days), max(1, len(days) // 160))]}


def _months(a: str, b: str) -> list[str]:
    """The first day of each month from `a`'s month to `b`'s."""
    y, m = int(a[:4]), int(a[5:7])
    out = []
    while f"{y:04d}-{m:02d}" <= b[:7]:
        out.append(f"{y:04d}-{m:02d}-01")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def _add_years(d: str, years: int) -> str:
    a = date.fromisoformat(d)
    try:
        return a.replace(year=a.year + years).isoformat()
    except ValueError:
        return a.replace(year=a.year + years, day=28).isoformat()


def spread(legs: list[dict], plan: dict, years: int, first_day: str, last_day: str, also: tuple[str, ...] = ()) -> dict | None:
    """The same SIP, for `years`, from every start month the history allows: the XIRRs' worst, median and best, and,
    for a dip rule, how often it beat the plain SIP over the same months. `also` adds start days of their own (the
    page's own window), so its lowest and highest include the run shown above them (NIFTYBEES, 8 Oct 2026: the run
    starting Nov 2021 gave 3.7% while "the lowest" said 4.2%, as the month starts stopped at Oct 2021). Each run is
    named by the month of its first instalment."""
    starts = [m for m in _months(first_day, last_day) if m >= first_day and _add_years(m, years) <= last_day]
    extra = [d for d in also if d >= first_day and _add_years(d, years) <= last_day and d not in starts]
    if len(starts) + len(extra) < 2:
        return None
    # many legs, or a dip rule run beside the plain SIP, cost more per start: take every second or third month then
    cap = max(24, min(MAX_STARTS, 600 // (len(legs) * (2 if plan["rule"] != "plain" else 1))))
    step = math.ceil(len(starts) / cap) if len(starts) > cap else 1
    starts = sorted(starts[::step] + extra)
    runs = []
    plain = {**plan, "rule": "plain"}
    for s in starts:
        e = _add_years(s, years)
        r = simulate(legs, plan, s, e, keep=False)
        if not r or r["xirr"] is None:
            continue
        row = {"start": str(r.get("start") or s)[:7], "xirr": r["xirr"], "deepest_fall_pct": r["deepest_fall_pct"]}
        if plan["rule"] != "plain":
            p = simulate(legs, plain, s, e, keep=False)
            row["plain_xirr"] = p["xirr"] if p else None
        runs.append(row)
    if len(runs) < 2:
        return None
    xs = sorted(r["xirr"] for r in runs)
    worst = min(runs, key=lambda r: r["xirr"])
    best = max(runs, key=lambda r: r["xirr"])
    out = {"years": years, "count": len(runs), "every_months": step, "worst": worst, "best": best, "median": round(xs[len(xs) // 2] if len(xs) % 2 else
                                                                                               (xs[len(xs) // 2 - 1] + xs[len(xs) // 2]) / 2, 6),
           "below_zero": sum(1 for x in xs if x < 0), "runs": runs}
    if plan["rule"] != "plain":
        both = [r for r in runs if r.get("plain_xirr") is not None]
        diffs = sorted(r["xirr"] - r["plain_xirr"] for r in both)
        out["dip"] = {"compared": len(both), "beat": sum(1 for x in diffs if x > 1e-6),
                      "median_diff_pp": round(diffs[len(diffs) // 2] * 100, 2) if diffs else None,
                      "worst_diff_pp": round(diffs[0] * 100, 2) if diffs else None, "best_diff_pp": round(diffs[-1] * 100, 2) if diffs else None}
    return out


def words(plan: dict, legs: list[dict]) -> str:
    """The rule in plain words, for a broker's SIP form."""
    split = ", ".join(f"{round(leg['weight'] * 100)}% {leg['symbol']}" for leg in legs) if len(legs) > 1 else legs[0]["symbol"]
    when = {"daily": "Every trading day", "weekly": f"Every {WEEKDAYS[plan['weekday']]} (or the next trading day)",
            "monthly": f"On day {plan['dom']} of every month (or the next trading day)"}[plan["freq"]]
    what = (f"invest ₹{plan['amount']:,.0f}" if plan["mode"] == "amount" else f"purchase {plan['qty']} share{'s' if plan['qty'] != 1 else ''}")
    s = f"{when}, {what} in {split}" + (" (split by these weights)" if len(legs) > 1 and plan["mode"] == "amount" else "") + "."
    if plan["step_up"]:
        s += f" Raise the amount by {plan['step_up'] * 100:g}% each year."
    if plan["rule"] == "only_dips":
        s += (f" Hold each instalment as cash and invest it only on a close at least {plan['dip'] * 100:g}% below the highest close of "
              f"the last {plan['lookback']} trading days, with all the cash waiting.")
    elif plan["rule"] == "extra_on_dips":
        s += (f" When an instalment falls on a close at least {plan['dip'] * 100:g}% below the highest close of the last "
              f"{plan['lookback']} trading days, add {plan['extra'] * 100:g}% to it.")
    return s


# ---------- the route ----------
class Leg(BaseModel):
    inst_id: str = Field(..., min_length=1, max_length=60)
    weight: float = Field(100, gt=0, le=100)


class SipReq(BaseModel):
    legs: list[Leg] = Field(..., min_length=1, max_length=MAX_LEGS)
    mode: str = Field("amount", pattern="^(amount|qty)$")
    amount: float = Field(10000, gt=0, le=1e8)
    qty: int = Field(1, ge=1, le=100000)
    freq: str = Field("monthly", pattern="^(daily|weekly|monthly)$")
    dom: int = Field(1, ge=1, le=28)
    weekday: int = Field(0, ge=0, le=4)
    step_up: float = Field(0, ge=0, le=50)                  # % a year
    years: int = Field(5, ge=1, le=MAX_YEARS)
    start: str | None = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    rule: str = Field("plain", pattern="^(plain|only_dips|extra_on_dips)$")
    dip: float = Field(10, gt=0, le=60)                      # % below the recent high
    lookback: int = Field(252)
    extra: float = Field(50, gt=0, le=500)                   # % added on a dip day
    brokerage: float = Field(0, ge=0, le=1000)               # ₹ an order
    spread: bool = True


def _m():
    from . import main
    return main


def closes_of(prov, inst: dict) -> tuple[dict[str, float], list[str]]:
    bars = prov.history(inst, "1d", HISTORY_DAYS) or []
    closes = {}
    for b in bars:
        c = b.get("c")
        if isinstance(c, (int, float)) and math.isfinite(c) and c > 0:
            closes[_day(b.get("t"))] = float(c)
    return closes, sorted(closes)


def recent_highs(closes: dict[str, float], days: list[str], n: int) -> dict[str, float]:
    """Each day's highest close over the last `n` trading days, today included (from the n-th day on)."""
    from collections import deque
    out, q = {}, deque()
    for i, d in enumerate(days):
        c = closes[d]
        while q and closes[days[q[-1]]] <= c:
            q.pop()
        q.append(i)
        if q[0] <= i - n:
            q.popleft()
        if i >= n - 1:
            out[d] = closes[days[q[0]]]
    return out


def run(req: SipReq, profile: dict) -> dict:
    full = allows(profile["_plan"], "sip_luck")
    if req.rule != "plain" and not full:
        _m().upgrade(f"Dip rules are on the {PLANS[FEATURE_PLAN['sip_luck']]['name']} plan.")
    if req.mode == "qty" and req.rule != "plain":
        err(400, "bad_rule", "Dip rules work with an amount each time, not a number of shares.")
    if req.lookback not in LOOKBACKS:
        err(400, "bad_lookback", "Pick 20, 60, 125 or 252 trading days for the recent high.")
    ids = [leg.inst_id for leg in req.legs]
    if len(set(ids)) != len(ids):
        err(400, "duplicate", "Each stock or ETF can be in the split once.")
    total_w = sum(leg.weight for leg in req.legs)
    if len(req.legs) > 1 and abs(total_w - 100) > 0.5:
        err(400, "bad_weights", "The split's shares must add up to 100%.")
    m = _m()
    legs = []
    for leg in req.legs:
        prov, inst = m.get_instrument(leg.inst_id)
        if inst.get("market") != "IN" or inst.get("type") not in ("EQ", "ETF") or inst.get("exchange") in ("NFO", "BFO", "MCX", "CDS"):
            err(400, "not_a_stock", f"{inst.get('symbol') or 'That instrument'} isn't an Indian stock or ETF. A SIP test takes shares and ETFs only.")
        closes, days = closes_of(prov, inst)
        if len(days) < 30:
            err(400, "no_history", f"There isn't enough price history for {inst.get('symbol')} yet.")
        legs.append({"symbol": inst.get("symbol") or leg.inst_id, "name": inst.get("name") or "", "inst_id": leg.inst_id,
                     "weight": (leg.weight / total_w) if len(req.legs) > 1 else 1.0, "closes": closes, "days": days,
                     "high": recent_highs(closes, days, req.lookback) if req.rule != "plain" else {}})
    first_day = max(leg["days"][0] for leg in legs)              # every leg has prices from here
    last_day = min(leg["days"][-1] for leg in legs)
    if req.start:
        start = max(req.start, first_day)
    else:
        start = max(first_day, _add_years(last_day, -req.years))
    end = min(last_day, _add_years(start, req.years))
    if start >= end:
        err(400, "bad_dates", "There's no price history in that window. Pick an earlier start.")
    plan = {"mode": req.mode, "amount": req.amount, "qty": req.qty, "freq": req.freq, "dom": req.dom, "weekday": req.weekday,
            "step_up": req.step_up / 100, "rule": req.rule, "dip": req.dip / 100, "extra": req.extra / 100,
            "brokerage": req.brokerage, "lookback": req.lookback}
    res = simulate(legs, plan, start, end)
    if not res:
        err(400, "no_instalments", "No instalment falls in that window. Pick a longer window or a more frequent SIP.")
    lump = _once([dict(leg) for leg in legs], {**plan, "amount": res["invested"]}, res["start"], end)
    plain = simulate(legs, {**plan, "rule": "plain"}, start, end, keep=False) if req.rule != "plain" else None
    years = max(1, round((date.fromisoformat(end) - date.fromisoformat(start)).days / 365))
    out = {"result": res, "lump_sum": lump, "plain": plain, "full": full, "plan": PLANS[FEATURE_PLAN["sip_luck"]]["name"],
           "legs": [{"symbol": leg["symbol"], "name": leg["name"], "inst_id": leg["inst_id"], "weight": round(leg["weight"] * 100, 2)} for leg in legs],
           "history": {"from": first_day, "to": last_day}, "window": {"from": start, "to": end, "years": years},
           "words": words(plan, legs), "assumptions": ASSUMPTIONS, "disclaimer": DISCLAIMER, "spread": None}
    if full and req.spread and req.mode == "amount":
        out["spread"] = spread(legs, plan, years, first_day, last_day, also=(start,))
    return out


router = APIRouter(prefix="/invest/sip-test", tags=["invest"])


@router.post("")
async def sip_test(req: SipReq, profile=Depends(current_profile)):
    """A SIP into Indian stocks or ETFs over past closes, with charges and a lump sum beside it (everyone); dip rules and
    the spread of results over every start month (Basic and up)."""
    _m().throttle(profile, "sip_test", 60, 3600, "That's a lot of SIP tests in an hour. Try again a little later.")
    return ok(await run_in_threadpool(run, req, profile))
