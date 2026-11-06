"""One rule for every candle StratLab reads, whatever its source: its high and low hold its open and close.

A source now and then sends a candle that breaks it (5 Nov: EUR/USD's 2 Nov low a hair above its open and gold's forming
candle with its low above its open, from the global price source; 6 Nov: MCX gold-mini's 5 Nov candle from the broker). That
drew a broken bar, could skew a backtest's fills and failed the daily feature check, which emailed the owner. Every history
read (the broker's, the crypto exchange's, the global source's, MCX and CDS built from contracts or quotes) passes its candles
through `whole` so charts, backtests and the check all see the same corrected candle."""
from functools import wraps


def whole(b: dict) -> dict:
    """The candle with its high and low widened to hold its open and close (a whole candle is returned as it is)."""
    try:
        o, h, l, c = b["o"], b["h"], b["l"], b["c"]
        hi, lo = max(o, h, l, c), min(o, h, l, c)
    except (KeyError, TypeError):
        return b
    return b if (h, l) == (hi, lo) else {**b, "h": hi, "l": lo}


def whole_all(bars):
    """The list itself when every candle is whole (a cached list stays the same object, and nothing is copied), else a
    corrected copy."""
    if not isinstance(bars, list):
        return bars
    fixed = [whole(b) for b in bars]
    return bars if all(f is b for f, b in zip(fixed, bars)) else fixed


def whole_candles(fn):
    """For a method that returns a list of candles."""
    @wraps(fn)
    def run(*a, **k):
        return whole_all(fn(*a, **k))
    return run
