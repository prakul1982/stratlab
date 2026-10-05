"""Option Greeks and the value of a position before expiry: model estimates from today's prices.

The model is Black's 1976 formula on the forward, the same maths positioning.py uses for the at-the-money IV:
- The forward comes from put-call parity at the strike nearest the spot (strike + (call − put) grown at the rate),
  so index dividends and the futures basis are in it without being guessed. With no prices at that strike, the spot
  stands in for it, and the model says so.
- Each option's implied volatility is solved from its bid-ask middle (the last price when there's no two-sided
  quote). When an option's price is outside what any volatility gives, the at-the-money IV stands in, flagged.
- RATE is the yearly rate the premiums are discounted at. On the forward it only discounts, so for a weekly option it
  moves a premium by about 0.1%. The positioning page's ATM IV keeps a rate of zero, so its history stays comparable;
  at the money the two differ by a few hundredths of a vol point.
- Time runs to the moment the expiry's settlement price is fixed (data/sessions.py: 15:30 India time, when the
  closing auction's order entry ends since 3 Aug 2026, and the end of the last-30-minute VWAP before; contracts keep
  trading to 15:40 but their value is settled by then), in years of 365 calendar days. Theta is per calendar day.
- Delta and gamma are per point of the forward (which moves point for point with the underlying, give or take the
  carry), vega per 1 vol point, theta per calendar day with the forward held still.

What-if (the frontend's src/lib/greeks.ts is a port of this part, tested against fixtures this module writes):
- the underlying moves to a price S, the forward with it (forward / spot held at its ratio, shrinking towards 1 as
  expiry nears: carry is proportional to the time left);
- every option's IV shifts by the same number of vol points, sticky by strike (floored at MIN_VOL);
- days pass, and an option at or past expiry is worth its intrinsic value.

Model outputs only: they describe today's prices under stated inputs. Real prices can differ."""
import math
from datetime import date, datetime
from zoneinfo import ZoneInfo

from ..data import sessions

IST = ZoneInfo("Asia/Kolkata")
RATE = 0.055                 # near the 91-day T-bill cut-off yield (RBI auction 30 Sep 2026: 5.52%; repo 5.25%), checked 5 Oct 2026
MIN_VOL = 0.005              # a what-if IV shift can't take an option below 0.5% volatility
NOTE = ("Model estimates: Black's formula on the forward, IV from each option's bid-ask middle. Real prices can "
        "differ.")


# ---------- Black-76 ----------
def ncdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def npdf(x: float) -> float:
    return math.exp(-x * x / 2) / math.sqrt(2 * math.pi)


def black76(f: float, k: float, t: float, sigma: float, kind: str, r: float = 0.0) -> float:
    """An option's price on a forward `f`, discounted at `r` for `t` years: Black's 1976 formula. At or past expiry
    (or with no volatility) it is the intrinsic value."""
    if t <= 0 or sigma <= 0:
        return max(0.0, f - k) if kind == "CE" else max(0.0, k - f)
    sd = sigma * math.sqrt(t)
    d1 = (math.log(f / k) + sd * sd / 2) / sd
    d2 = d1 - sd
    disc = math.exp(-r * t)
    return disc * (f * ncdf(d1) - k * ncdf(d2) if kind == "CE" else k * ncdf(-d2) - f * ncdf(-d1))


def implied_vol(price: float, f: float, k: float, t: float, kind: str, r: float = 0.0) -> float | None:
    """The volatility (a year, as a fraction) at which Black's formula gives `price`, by bisection; None when the price
    is outside what any volatility gives (below the intrinsic value, or above the forward or strike)."""
    if not all(isinstance(x, (int, float)) and math.isfinite(x) for x in (price, f, k, t, r)) or min(f, k, t) <= 0 or price <= 0:
        return None
    lo, hi = 1e-4, 5.0
    if price <= black76(f, k, t, lo, kind, r) or price >= black76(f, k, t, hi, kind, r):
        return None
    for _ in range(80):
        mid = (lo + hi) / 2
        if black76(f, k, t, mid, kind, r) < price:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def greeks(f: float, k: float, t: float, sigma: float, kind: str, r: float = RATE) -> dict:
    """Price, delta and gamma (per point of the forward), theta (per calendar day) and vega (per vol point) of one
    option. At or past expiry: the intrinsic value, delta 1, 0 or −1, and no gamma, theta or vega."""
    px = black76(f, k, t, sigma, kind, r)
    if t <= 0 or sigma <= 0:
        itm = f > k if kind == "CE" else f < k
        return {"price": px, "delta": (1.0 if kind == "CE" else -1.0) if itm else 0.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0}
    sd = sigma * math.sqrt(t)
    d1 = (math.log(f / k) + sd * sd / 2) / sd
    disc = math.exp(-r * t)
    n1 = npdf(d1)
    return {
        "price": px,
        "delta": disc * ncdf(d1) if kind == "CE" else -disc * ncdf(-d1),
        "gamma": disc * n1 / (f * sd),
        "theta": (r * px - disc * f * n1 * sigma / (2 * math.sqrt(t))) / 365,
        "vega": disc * f * n1 * math.sqrt(t) / 100,
    }


def years_to(expiry: str, at: datetime) -> float:
    """Time from `at` to when the expiry's settlement price is fixed (15:30 India time), in years of 365 days."""
    day = date.fromisoformat(expiry)
    end = datetime.combine(day, sessions.settle_at(day), IST)
    if at.tzinfo is None:
        at = at.replace(tzinfo=IST)
    return (end - at).total_seconds() / (365 * 86400)


def parity_forward(k: float, call: float, put: float, t: float, r: float = RATE) -> float:
    """The forward put-call parity gives at strike k: call − put = discount × (forward − strike)."""
    return k + math.exp(r * t) * (call - put)


# ---------- what-if ----------
# a model leg: {"side": "buy"|"sell", "opt": "CE"|"PE", "strike", "qty" (units of the underlying), "fill" (price paid
# or received), "iv" (a fraction), "t" (years left now), "basis" (forward / spot now)}
def _sign(leg: dict) -> int:
    return 1 if leg["side"] == "buy" else -1


def leg_inputs(leg: dict, spot: float, days: float = 0.0, iv_shift: float = 0.0) -> tuple[float, float, float]:
    """(forward, years left, volatility) for a leg with the underlying at `spot`, `days` calendar days on and its IV
    moved by `iv_shift` vol points."""
    t0 = leg["t"]
    t = t0 - days / 365
    if t <= 1e-12:
        return spot, 0.0, 0.0
    b = leg["basis"] ** (t / t0) if t0 > 0 else 1.0
    return spot * b, t, max(MIN_VOL, leg["iv"] + iv_shift / 100)


def scenario(legs: list[dict], spot: float, days: float = 0.0, iv_shift: float = 0.0, r: float = RATE) -> dict:
    """The position's profit (model value less what was paid, before charges) and its net Greeks, in rupees: delta
    and gamma per point, theta per day, vega per vol point."""
    out = {"pnl": 0.0, "value": 0.0, "delta": 0.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0}
    for lg in legs:
        f, t, sigma = leg_inputs(lg, spot, days, iv_shift)
        g = greeks(f, lg["strike"], t, sigma, lg["opt"], r)
        n = _sign(lg) * lg["qty"]
        out["value"] += n * g["price"]
        out["pnl"] += n * (g["price"] - lg["fill"])
        for key in ("delta", "gamma", "theta", "vega"):
            out[key] += n * g[key]
    return out


def curve(legs: list[dict], xs: list[float], days: float = 0.0, iv_shift: float = 0.0, r: float = RATE) -> list[float]:
    """The position's model profit with the underlying at each price in `xs`."""
    return [scenario(legs, x, days, iv_shift, r)["pnl"] for x in xs]


# ---------- from quotes ----------
def mid(q: dict | None) -> float | None:
    """The bid-ask middle, else the last price: what an option's IV is solved from."""
    if not q:
        return None
    bid, ask, ltp = q.get("bid"), q.get("ask"), q.get("ltp")
    if bid and ask and ask >= bid > 0:
        return (bid + ask) / 2
    return ltp if ltp and ltp > 0 else None


def model(spot: float | None, expiry: str, atm: float | None, call: dict | None, put: dict | None, at: datetime,
          r: float = RATE) -> dict | None:
    """The inputs every option of one expiry shares: the forward (from parity at the at-the-money strike, else the
    spot), time to expiry, the rate and the at-the-money IV. None when there's no spot or the expiry has passed."""
    if not spot or spot <= 0:
        return None
    t = years_to(expiry, at)
    if t <= 0:
        return None
    c, p = mid(call), mid(put)
    f = parity_forward(atm, c, p, t, r) if atm and c and p else None
    src = "parity"
    if not f or f <= 0 or abs(f / spot - 1) > 0.2:      # a stale or crossed quote gives a forward nowhere near the spot
        f, src = spot, "spot"
    ivs = [v for v in (implied_vol(c, f, atm, t, "CE", r) if c and atm else None,
                       implied_vol(p, f, atm, t, "PE", r) if p and atm else None) if v]
    return {"expiry": expiry, "spot": spot, "forward": round(f, 4), "basis": f / spot, "forward_from": src, "atm": atm,
            "t": t, "days": round(t * 365, 4), "rate": r, "atm_iv": sum(ivs) / len(ivs) if ivs else None,
            "as_of": at.astimezone(IST).isoformat(timespec="seconds")}


def option(q: dict | None, k: float, kind: str, m: dict) -> dict:
    """One option's IV and Greeks under a model: {"mid", "iv", "iv_from": "price"|"atm"|None, "delta", ...}. When its
    own price gives no IV the at-the-money IV stands in; with neither, only the mid."""
    px = mid(q)
    iv = implied_vol(px, m["forward"], k, m["t"], kind, m["rate"]) if px else None
    src = "price" if iv else None
    if iv is None and m.get("atm_iv"):
        iv, src = m["atm_iv"], "atm"
    out = {"mid": px, "iv": iv, "iv_from": src}
    if iv:
        g = greeks(m["forward"], k, m["t"], iv, kind, m["rate"])
        out.update(delta=g["delta"], gamma=g["gamma"], theta=g["theta"], vega=g["vega"], model_price=g["price"])
    return out


def _round(g: dict) -> dict:
    """Numbers to 8 significant figures: a gamma of 0.00105812 keeps its digits, a theta of ₹1,310.64 its paise."""
    return {k: (float(f"{v:.8g}") if isinstance(v, float) else v) for k, v in g.items()}


def public_model(m: dict) -> dict:
    """A model as the API shows it."""
    return {**m, "t": round(m["t"], 8), "basis": round(m["basis"], 8),
            "atm_iv": round(m["atm_iv"], 6) if m.get("atm_iv") else None}


def model_leg(leg: dict, g: dict, m: dict) -> dict | None:
    """The what-if inputs of a priced leg ({side, opt, strike, qty, fill}), or None without an IV."""
    if not g.get("iv") or leg.get("fill") is None:
        return None
    return {"side": leg["side"], "opt": leg["opt"], "strike": float(leg["strike"]), "qty": leg["qty"], "fill": leg["fill"],
            "iv": g["iv"], "t": m["t"], "basis": m["basis"]}


def position(legs: list[dict], m: dict) -> dict:
    """Each leg's IV and Greeks (per option) and the position's net Greeks (× quantity, sold legs negative). Legs are
    {side, opt, strike, qty, fill, quote}. `complete` is False when a leg has no IV, so the net leaves it out."""
    per, mlegs = [], []
    for lg in legs:
        g = option(lg.get("quote"), float(lg["strike"]), lg["opt"], m)
        per.append(_round(g))
        ml = model_leg(lg, g, m)
        if ml:
            mlegs.append(ml)
    net = scenario(mlegs, m["spot"], r=m["rate"]) if mlegs else None
    return {"legs": per, "model_legs": [_round(x) for x in mlegs], "complete": len(mlegs) == len(legs),
            "net": _round({k: net[k] for k in ("delta", "gamma", "theta", "vega", "pnl")}) if net else None}


def net(legs: list[dict], per: list[dict]) -> dict:
    """Net Greeks from each leg's per-option Greeks (legs of different expiries can be added up this way): × quantity,
    sold legs negative. A leg without an IV is left out."""
    out = {"delta": 0.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0}
    for lg, g in zip(legs, per):
        if g and g.get("iv"):
            for k in out:
                out[k] += _sign(lg) * lg["qty"] * g[k]
    return _round(out)


def add_to_chain(chain: dict, at: datetime) -> dict:
    """IV and Greeks for every strike of a chain from OptionsData.chain, beside its quotes (ce_g, pe_g), and the
    model they share."""
    rows = chain.get("rows") or []
    atm = chain.get("atm")
    row = next((r for r in rows if r["strike"] == atm), None)
    m = model(chain.get("spot"), chain["expiry"], atm, row and row.get("ce"), row and row.get("pe"), at) if chain.get("expiry") else None
    chain["model"] = public_model(m) if m else None
    for r in rows:
        r["ce_g"] = _round(option(r.get("ce"), r["strike"], "CE", m)) if m else None
        r["pe_g"] = _round(option(r.get("pe"), r["strike"], "PE", m)) if m else None
    return chain


# ---------- with the live feed ----------
def live_model(data, contracts, spot: float | None, at: datetime) -> dict | None:
    """The model for one expiry's contracts, quoting the at-the-money pair."""
    if not contracts or not spot:
        return None
    atm = contracts.atm(spot)
    keys = [contracts.key("CE", atm), contracts.key("PE", atm)]
    q = data.quotes([k for k in keys if k])
    return model(spot, contracts.expiry, atm, q.get(keys[0]) if keys[0] else None, q.get(keys[1]) if keys[1] else None, at)
