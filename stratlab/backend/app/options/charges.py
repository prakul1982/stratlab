"""What a structure costs to open and close, and where it breaks even once those charges are paid.

Arithmetic only: every leg is opened and closed once at the fill price shown, so the payoff at expiry moves down by the
round-trip charges. The rates are engine/costs.py's (Budget 2026: STT on options 0.15% of premium on sells from
1 April 2026); brokerage is the user's own per-order amount, charged on every freeze-limit slice."""
import math

from ..engine import costs as C

RATES_AS_OF = "2026-04-01"
STT_LABEL = {"in_mcx_opt": "CTT"}       # commodity options pay commodity transaction tax, not STT


def kind_for(exchange: str) -> str:
    """The cost model for an exchange's options, the same one paper sessions use."""
    return {"MCX": "in_mcx_opt", "CDS": "in_cds_opt", "BFO": "in_bse_opt"}.get(exchange, "in_opt")


def round_trip(legs: list[dict], kind: str, brokerage: float, freeze: int) -> dict:
    """Itemised charges for opening and closing each leg once at its fill. Each leg is {side, qty, fill}; the open is
    on the leg's own side and the close on the other. An order larger than the freeze limit goes as several slices,
    each paying brokerage."""
    r = C.IN_RATES[kind]
    items = {"brokerage": 0.0, "stt": 0.0, "exchange": 0.0, "sebi": 0.0, "stamp": 0.0, "gst": 0.0}
    orders = 0
    for lg in legs:
        slices = max(1, math.ceil(lg["qty"] / freeze)) if freeze else 1
        for side in (lg["side"], "buy" if lg["side"] == "sell" else "sell"):
            c = C.order_costs(kind, side, lg["qty"], lg["fill"], slices * brokerage)
            sebi = lg["qty"] * lg["fill"] * r["sebi"]
            items["brokerage"] += c["brokerage"]
            items["stt"] += c["stt"]
            items["exchange"] += c["exchange"] - sebi
            items["sebi"] += sebi
            items["stamp"] += c["stamp"]
            items["gst"] += c["gst"]
            orders += slices
    return {"items": items, "total": sum(items.values()), "orders": orders}


def _payoff_at(legs: list[dict], x: float) -> float:
    """Profit at expiry with the underlying at x, before costs."""
    out = 0.0
    for lg in legs:
        intrinsic = max(0.0, x - lg["strike"]) if lg["opt"] == "CE" else max(0.0, lg["strike"] - x)
        out += (lg["fill"] - intrinsic if lg["side"] == "sell" else intrinsic - lg["fill"]) * lg["qty"]
    return out


def _slope_above(legs: list[dict]) -> float:
    """How fast the payoff changes per point above the highest strike: only calls still move there."""
    return sum((1 if lg["side"] == "buy" else -1) * lg["qty"] for lg in legs if lg["opt"] == "CE")


def breakevens(legs: list[dict], shift: float = 0.0) -> list[float]:
    """Prices at expiry where the payoff less `shift` crosses zero, exactly: the payoff is a straight line between
    strikes, so each crossing is found on its own segment. Prices run from zero up."""
    xs = [0.0] + sorted({float(lg["strike"]) for lg in legs})
    ys = [_payoff_at(legs, x) - shift for x in xs]
    out = []
    for i in range(1, len(xs)):
        if (ys[i - 1] < 0) != (ys[i] < 0):
            out.append(xs[i - 1] + (xs[i] - xs[i - 1]) * -ys[i - 1] / (ys[i] - ys[i - 1]))
    k = _slope_above(legs)
    if k and (ys[-1] < 0) != (k < 0):          # one more crossing past the top strike
        out.append(xs[-1] - ys[-1] / k)
    return [round(b, 2) for b in out]


def max_profit(legs: list[dict]) -> float | None:
    """The most the structure makes at expiry before costs, or None when it keeps rising with the price."""
    if _slope_above(legs) > 1e-9:
        return None
    xs = [0.0] + [float(lg["strike"]) for lg in legs]
    return max(_payoff_at(legs, x) for x in xs)


def summary(legs: list[dict], kind: str, brokerage: float, freeze: int) -> dict:
    """The round-trip charges with their share of the premium and of the most it can make, and the breakevens
    before and after them. Each leg is {side, opt, strike, qty, fill}."""
    rt = round_trip(legs, kind, brokerage, freeze)
    cost = rt["total"]
    net = sum((1 if lg["side"] == "sell" else -1) * lg["fill"] * lg["qty"] for lg in legs)
    premium = abs(net)
    best = max_profit(legs)
    labels = {"brokerage": "Brokerage", "stt": STT_LABEL.get(kind, "STT"), "exchange": "Exchange charges", "sebi": "SEBI fee",
              "stamp": "Stamp duty", "gst": "GST"}
    return {
        "total": round(cost, 2), "orders": rt["orders"], "brokerage_per_order": brokerage, "freeze": freeze or None,
        "items": [{"key": k, "label": labels[k], "amount": round(v, 2)} for k, v in rt["items"].items() if v > 0.0049],
        "credit": net > 0, "premium": round(premium, 2),
        "premium_after": round(net - cost, 2) if net > 0 else None,
        "pct_of_premium": round(cost / premium * 100, 2) if premium > 0 else None,
        "max_profit": round(best, 2) if best is not None else None,
        "max_profit_after": round(best - cost, 2) if best is not None else None,
        "pct_of_max_profit": round(cost / best * 100, 2) if best is not None and best > 0 else None,
        "breakevens": breakevens(legs), "breakevens_after": breakevens(legs, cost),
        "rates_as_of": RATES_AS_OF,
    }
