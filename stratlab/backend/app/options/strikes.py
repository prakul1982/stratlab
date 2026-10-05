"""Picking a leg's strike by a rule instead of a distance from the money.

A leg's `pick` (models.OptLeg) is one of:
- "offset": the distance from the at-the-money strike, in strikes or points (Contracts.strike_for);
- "delta": the strike whose model delta is nearest the number set (0.20 means +0.20 for a call, −0.20 for a put);
- "delta_range": the strike whose model delta lies between two numbers, nearest the middle of the range;
- "premium": the strike whose premium is nearest a rupee amount, or the cheapest at or above it ("gte"), or the dearest
  at or below it ("lte");
- "straddle_pct": the strike whose premium is nearest a share of the at-the-money straddle (call + put premium).

Premiums are each option's bid-ask middle (the last price without a two-sided quote). Deltas are the pricing model's
(greeks.py: Black's formula on the forward, IV from the option's own price), so a strike whose price gives no IV isn't
a candidate. A rule looks at WINDOW strikes either side of the money of the leg's own type. It is resolved on the quotes
of the moment it's used (the entry, a re-centre, a preview) and says why it picked what it did, for the order log.

A user-set selection rule and model estimates only: nothing here says a strike is a good one to trade."""
from . import greeks as G

WINDOW = 25            # strikes either side of the money a rule looks through
RULES = ("delta", "delta_range", "premium", "straddle_pct")


def uses_rules(legs) -> bool:
    return any(getattr(lg, "pick", "offset") != "offset" for lg in legs)


def needs_model(legs) -> bool:
    return any(getattr(lg, "pick", "offset") in ("delta", "delta_range") for lg in legs)


def window(contracts, atm: float, n: int = WINDOW) -> list[float]:
    s = contracts.strikes
    if atm not in s:
        return []
    i = s.index(atm)
    return s[max(0, i - n): i + n + 1]


def keys_for(contracts, atm: float, legs, n: int = WINDOW) -> list[str]:
    """The contracts a set of legs' rules need quoted: the at-the-money pair (the model's forward and IV, the straddle),
    and every strike in the window for each option type a rule leg uses."""
    if not uses_rules(legs):
        return []
    keys = [contracts.key("CE", atm), contracts.key("PE", atm)]
    for opt in sorted({lg.opt for lg in legs if getattr(lg, "pick", "offset") != "offset"}):
        keys += [contracts.key(opt, k) for k in window(contracts, atm, n)]
    return [k for k in dict.fromkeys(keys) if k]


def model_for(contracts, atm: float, spot: float | None, quotes: dict, at) -> dict | None:
    """The pricing model of the moment, from the at-the-money pair's quotes."""
    if not spot:
        return None
    ce, pe = contracts.key("CE", atm), contracts.key("PE", atm)
    return G.model(spot, contracts.expiry, atm, quotes.get(ce) if ce else None, quotes.get(pe) if pe else None, at)


def strike_text(k: float) -> str:
    return f"{k:,.0f}" if float(k).is_integer() else f"{k:g}"


def _rs(v: float) -> str:
    return f"₹{v:,.2f}"


def _d(v: float) -> str:
    return ("−" if v < 0 else "") + f"{abs(v):.2f}"


def _candidates(contracts, atm: float, opt: str, quotes: dict) -> list[tuple[float, float]]:
    """(strike, premium) for every quoted strike of one type in the window."""
    out = []
    for k in window(contracts, atm):
        key = contracts.key(opt, k)
        px = G.mid(quotes.get(key)) if key else None
        if px:
            out.append((k, px))
    return out


def pick(contracts, atm: float, leg, quotes: dict, m: dict | None) -> tuple[float | None, str]:
    """(strike, why) for one leg: why is what the order log shows ("PE 24,300 picked: model delta −0.21, nearest to
    −0.20"), or why nothing could be picked when the strike is None."""
    rule = getattr(leg, "pick", "offset")
    opt = leg.opt
    sign = 1 if opt == "CE" else -1
    cands = _candidates(contracts, atm, opt, quotes)
    near_atm = lambda k: abs(k - atm)                       # noqa: E731  (ties go to the strike nearer the money)
    if rule in ("delta", "delta_range"):
        if not m:
            return None, f"No pricing model yet for the {opt} delta rule (it needs prices at the at-the-money strike)."
        deltas = []
        for k, _ in cands:
            g = G.option(quotes.get(contracts.key(opt, k)), k, opt, m)
            if g.get("iv_from") == "price" and g.get("delta") is not None:
                deltas.append((k, g["delta"]))
        if not deltas:
            return None, f"No {opt} strike has a model delta yet (no prices that give an IV)."
        if rule == "delta":
            want = sign * leg.delta
            k, d = min(deltas, key=lambda x: (abs(x[1] - want), near_atm(x[0])))
            return k, f"{opt} {strike_text(k)} picked: model delta {_d(d)}, nearest to {_d(want)}"
        lo, hi = leg.delta, leg.deltaTo
        inside = [(k, d) for k, d in deltas if lo <= abs(d) <= hi]
        if not inside:
            return None, f"No {opt} strike's model delta is between {_d(sign * lo)} and {_d(sign * hi)} right now."
        mid = sign * (lo + hi) / 2
        k, d = min(inside, key=lambda x: (abs(x[1] - mid), near_atm(x[0])))
        return k, f"{opt} {strike_text(k)} picked: model delta {_d(d)}, inside {_d(sign * lo)} to {_d(sign * hi)}"
    if rule in ("premium", "straddle_pct"):
        if not cands:
            return None, f"No {opt} strike near the money has a price yet."
        if rule == "straddle_pct":
            ce, pe = (G.mid(quotes.get(contracts.key(o, atm))) for o in ("CE", "PE"))
            if not ce or not pe:
                return None, "No price yet for the at-the-money straddle the rule is measured against."
            target = leg.pct / 100 * (ce + pe)
            k, px = min(cands, key=lambda x: (abs(x[1] - target), near_atm(x[0])))
            return k, (f"{opt} {strike_text(k)} picked: premium {_rs(px)}, nearest to {leg.pct:g}% of the at-the-money "
                       f"straddle ({_rs(target)} of {_rs(ce + pe)})")
        target, op = leg.premium, leg.premiumOp
        if op == "gte":
            ok = [c for c in cands if c[1] >= target]
            if not ok:
                return None, f"No {opt} strike near the money is priced at or above {_rs(target)}."
            k, px = min(ok, key=lambda x: (x[1], near_atm(x[0])))
            return k, f"{opt} {strike_text(k)} picked: premium {_rs(px)}, the lowest at or above {_rs(target)}"
        if op == "lte":
            ok = [c for c in cands if c[1] <= target]
            if not ok:
                return None, f"No {opt} strike near the money is priced at or below {_rs(target)}."
            k, px = max(ok, key=lambda x: (x[1], -near_atm(x[0])))
            return k, f"{opt} {strike_text(k)} picked: premium {_rs(px)}, the highest at or below {_rs(target)}"
        k, px = min(cands, key=lambda x: (abs(x[1] - target), near_atm(x[0])))
        return k, f"{opt} {strike_text(k)} picked: premium {_rs(px)}, nearest to {_rs(target)}"
    return None, "Unknown strike rule."


def describe(leg, unit: str = "strikes") -> str:
    """A leg's rule in words, for the builder and the session page: "delta nearest 0.20", "premium ≥ ₹50"."""
    rule = getattr(leg, "pick", "offset")
    if rule == "delta":
        return f"model delta nearest {leg.delta:.2f}"
    if rule == "delta_range":
        return f"model delta {leg.delta:.2f} to {leg.deltaTo:.2f}"
    if rule == "premium":
        return {"near": "premium nearest ", "gte": "premium at or above ", "lte": "premium at or below "}[leg.premiumOp] + _rs(leg.premium)
    if rule == "straddle_pct":
        return f"premium nearest {leg.pct:g}% of the ATM straddle"
    off = leg.offset
    return "at the money" if off == 0 else f"{abs(off):g} {'points' if unit == 'points' else 'strikes'} {'out of' if off > 0 else 'in'} the money"
