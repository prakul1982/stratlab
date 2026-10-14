"""Rules that can't work: a comparison whose answer is the same on every candle (R18-002: "Price is below 0" sat in an
"any of these" list, never true, while "Volume is above Avg volume 20" alone opened 3,014 trades).

Each value has the range it can take (a price is above 0, RSI is 0 to 100, a volume above 0); a rule that compares it
with a fixed number outside that range, or with itself, is decided before any candle is read. A rule that is never true
is refused when the strategy is run; one that is always true is only said (it may be written that way on purpose)."""
import math

from .engine.core import cond_text

INF = math.inf
# value ranges: (lowest, lowest excluded, highest, highest excluded)
PRICE = (0.0, True, INF, False)
UNIT = (0.0, False, 100.0, False)
FROM_ZERO = (0.0, False, INF, False)
RANGES = {
    "price": PRICE, "open": PRICE, "high": PRICE, "low": PRICE, "prev_close": PRICE, "day_open": PRICE, "day_high": PRICE,
    "day_low": PRICE, "sma": PRICE, "ema": PRICE, "vwap": PRICE, "supertrend": PRICE, "dc_upper": PRICE, "dc_lower": PRICE,
    "rsi": UNIT, "stoch_k": UNIT, "adx": UNIT, "stage": (1.0, False, 4.0, False),
    "volume": FROM_ZERO, "vol_sma": FROM_ZERO,             # a candle with no trades has volume 0 (indices, quiet FX)
    "atr": FROM_ZERO, "atr_pct": FROM_ZERO, "body": FROM_ZERO, "upper_wick": FROM_ZERO, "lower_wick": FROM_ZERO, "range": FROM_ZERO,
}
FLIP = {"gt": "lt", "lt": "gt", "xa": "xb", "xb": "xa", "eq": "eq"}


def _scaled(ref) -> tuple | None:
    """The range of a rule value, scaled by its multiplier; None when it has no known range."""
    r = RANGES.get(ref.t)
    if r is None:
        return None
    k = getattr(ref, "k", None)
    return (r[0] * k, r[1], r[2] * k, r[3]) if k else r


def _against(op: str, rng: tuple, c: float) -> str | None:
    """"never" or "always" for a value in `rng` compared (`op`) with the fixed number `c`; None when it can go either way."""
    lo, lo_open, hi, hi_open = rng
    if op == "gt":
        if hi <= c:
            return "never"
        return "always" if lo > c or (lo == c and lo_open) else None
    if op == "lt":
        if lo >= c:
            return "never"
        return "always" if hi < c or (hi == c and hi_open) else None
    if op == "eq":
        return "never" if c < lo or c > hi or (c == lo and lo_open) or (c == hi and hi_open) else None
    if op == "xa":      # was at or below c, is above it
        return "never" if hi <= c or lo > c or (lo == c and lo_open) else None
    return "never" if lo >= c or hi < c or (hi == c and hi_open) else None      # xb: was at or above c, is below it


def _constant(op: str, a: float, b: float) -> str:
    if op == "gt":
        return "always" if a > b else "never"
    if op == "lt":
        return "always" if a < b else "never"
    if op == "eq":
        return "always" if abs(a - b) < 1e-9 else "never"
    return "never"          # a fixed number never crosses another


def _same(a, b) -> bool:
    keep = lambda r: {k: v for k, v in r.model_dump().items() if v is not None}       # noqa: E731
    return keep(a) == keep(b)


def verdict_of(c) -> str | None:
    """"never" when the rule can't be true on any candle, "always" when it's true on every candle that has values, else None."""
    l, r = c.l, c.r
    if l.t == "num" and r.t == "num":
        return None if l.v is None or r.v is None else _constant(c.op, l.v, r.v)
    if _same(l, r):
        return "always" if c.op == "eq" else "never"
    for val, num, op in ((l, r, c.op), (r, l, FLIP[c.op])):
        if num.t == "num" and num.v is not None and val.t != "num":
            rng = _scaled(val)
            if rng is not None:
                return _against(op, rng, float(num.v))
    return None


def problems(strategy) -> dict[str, list[str]]:
    """The strategy's rules that can't work, each as it reads ("Price is below 0"): {"never": [...], "always": [...]}."""
    out: dict[str, list[str]] = {"never": [], "always": []}
    for c in strategy.all_conds():
        v = verdict_of(c)
        if v:
            out[v].append(cond_text(c))
    return out
