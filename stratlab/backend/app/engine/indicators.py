"""Indicator maths on a candle DataFrame with columns t, o, h, l, c, v."""
import numpy as np
import pandas as pd

DEFAULTS = {
    "sma": (20, None), "ema": (20, None), "rsi": (14, None),
    "macd": (12, 26), "macd_signal": (12, 26), "macd_hist": (12, 26),
    "bb_upper": (20, 2), "bb_mid": (20, 2), "bb_lower": (20, 2),
    "vwap": (20, None), "supertrend": (10, 3),
    "adx": (14, None), "stoch_k": (14, 3), "atr_pct": (14, None),
    "dc_upper": (20, None), "dc_lower": (20, None), "volume": (None, None), "vol_sma": (20, None),
    "atr": (14, None), "stage": (150, 20),
}
# values that live on the candle or the trading day rather than being an indicator with a length
DAY = {"prev_close", "day_open", "day_high", "day_low", "day_chg"}
# drawn under the price chart rather than on it
OSCILLATORS = {"rsi", "macd", "macd_signal", "macd_hist", "adx", "stoch_k", "atr_pct", "volume", "vol_sma",
               "body", "upper_wick", "lower_wick", "range", "atr", "day_chg", "stage"}


def params(ref) -> tuple[int, float]:
    dp, dm = DEFAULTS.get(ref.t, (None, None))
    p = int(round(ref.p)) if ref.p else dp
    m = float(ref.m) if ref.m else dm
    return max(1, p or 1), m


def _ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False, min_periods=n).mean()


def rsi(c: pd.Series, n: int) -> pd.Series:
    d = c.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    out = 100 - 100 / (1 + up / dn.replace(0, np.nan))
    return out.where(~((dn == 0) & up.notna()), 100.0)


def supertrend(df: pd.DataFrame, n: int, mult: float) -> pd.Series:
    h, l, c = df.h.to_numpy(float), df.l.to_numpy(float), df.c.to_numpy(float)
    prev_c = np.roll(c, 1); prev_c[0] = c[0]
    tr = np.maximum.reduce([h - l, np.abs(h - prev_c), np.abs(l - prev_c)])
    atr = pd.Series(tr).ewm(alpha=1 / n, adjust=False, min_periods=n).mean().to_numpy()
    hl2 = (h + l) / 2
    ub, lb = hl2 + mult * atr, hl2 - mult * atr
    size = len(c)
    fu, fl, st = np.full(size, np.nan), np.full(size, np.nan), np.full(size, np.nan)
    for i in range(size):
        if np.isnan(atr[i]):
            continue
        if i == 0 or np.isnan(fu[i - 1]):
            fu[i], fl[i] = ub[i], lb[i]
            st[i] = lb[i] if c[i] >= hl2[i] else ub[i]
            continue
        fu[i] = ub[i] if (ub[i] < fu[i - 1] or c[i - 1] > fu[i - 1]) else fu[i - 1]
        fl[i] = lb[i] if (lb[i] > fl[i - 1] or c[i - 1] < fl[i - 1]) else fl[i - 1]
        if st[i - 1] == fu[i - 1]:
            st[i] = fu[i] if c[i] <= fu[i] else fl[i]
        else:
            st[i] = fl[i] if c[i] >= fl[i] else fu[i]
    return pd.Series(st, index=df.index)


FLAT = 0.01   # the average moving less than 1% over the look-back counts as flat


def stage(c: pd.Series, n: int = 150, look: int = 20) -> pd.Series:
    """Weinstein's market stage, 1 to 4, from the n-candle average (150 days is about 30 weeks) and its slope.

    2 (advancing): the average is rising and the price is above it.   4 (declining): falling, price below.
    3 (topping): the average stops rising, or the price breaks below a rising one.
    1 (basing): the average stops falling, or the price climbs above a falling one.
    A flat average keeps the story it came from: flat after an advance is a top (3), after a decline a base (1)."""
    avg = c.rolling(n).mean()
    prev_avg = avg.shift(look)
    slope = ((avg - prev_avg) / prev_avg).to_numpy(dtype=float)
    price, a = c.to_numpy(dtype=float), avg.to_numpy(dtype=float)
    out = np.full(len(c), np.nan)
    last = np.nan
    for i in range(len(c)):
        s = slope[i]
        if np.isnan(s) or np.isnan(a[i]):
            continue
        if s > FLAT:
            st = 2 if price[i] > a[i] else 3
        elif s < -FLAT:
            st = 4 if price[i] < a[i] else 1
        elif last in (2, 3):
            st = 3
        elif last in (4, 1):
            st = 1
        else:
            st = 1 if price[i] >= a[i] else 3
        out[i] = last = st
    return pd.Series(out, index=c.index)


def true_range(df: pd.DataFrame) -> pd.Series:
    prev = df.c.shift(1).fillna(df.c)
    return pd.concat([df.h - df.l, (df.h - prev).abs(), (df.l - prev).abs()], axis=1).max(axis=1)


def _wilder(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def atr_pct(df: pd.DataFrame, n: int) -> pd.Series:
    """Average true range as a % of price: how much it typically moves in one candle."""
    return _wilder(true_range(df), n) / df.c * 100


def adx(df: pd.DataFrame, n: int) -> pd.Series:
    """Trend strength, 0-100: above about 25 means a strong trend, whichever way."""
    up, down = df.h.diff(), -df.l.diff()
    plus = up.where((up > down) & (up > 0), 0.0)
    minus = down.where((down > up) & (down > 0), 0.0)
    tr = _wilder(true_range(df), n)
    pdi = 100 * _wilder(plus, n) / tr.replace(0, np.nan)
    mdi = 100 * _wilder(minus, n) / tr.replace(0, np.nan)
    dx = (100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)).fillna(0.0)
    return _wilder(dx, n).where(tr.notna())


def stoch_k(df: pd.DataFrame, n: int, smooth: int) -> pd.Series:
    """Slow stochastic %K, 0-100: where the close sits in the last n candles' range."""
    lo, hi = df.l.rolling(n).min(), df.h.rolling(n).max()
    raw = 100 * (df.c - lo) / (hi - lo).replace(0, np.nan)
    return raw.rolling(max(1, smooth)).mean()


def vwap(df: pd.DataFrame, n: int, intraday: bool) -> pd.Series:
    tp = (df.h + df.l + df.c) / 3
    vol = df.v.where(df.v > 0, 1.0)  # indices have no volume: fall back to equal weights
    if intraday:
        day = df.t.dt.date
        return (tp * vol).groupby(day).cumsum() / vol.groupby(day).cumsum()
    return (tp * vol).rolling(n).sum() / vol.rolling(n).sum()


def day_values(df: pd.DataFrame, t: str, intraday: bool) -> pd.Series:
    """Values of the trading day each candle belongs to. The day's high and low are so far, not the whole day."""
    if not intraday:
        prev = df.c.shift(1)
        day = {"prev_close": prev, "day_open": df.o, "day_high": df.h, "day_low": df.l}
    else:
        date = df.t.dt.date
        closes = df.groupby(date).c.last()
        prev = date.map(closes.shift(1))
        day = {"prev_close": prev, "day_open": df.groupby(date).o.transform("first"),
               "day_high": df.groupby(date).h.cummax(), "day_low": df.groupby(date).l.cummin()}
    if t == "day_chg":
        return (df.c / prev - 1) * 100
    return day[t].astype(float)


def higher_tf(df: pd.DataFrame, tf: str) -> tuple[pd.DataFrame, np.ndarray]:
    """Candles of a higher timeframe built from these ones, and for each original candle the index of the
    last higher-timeframe candle that had closed by then (-1 if none), so nothing peeks at the future."""
    if tf == "1d":
        key = df.t.dt.normalize()
    else:
        step = pd.Timedelta(minutes={"15m": 15, "1h": 60}[tf])
        day = df.t.dt.normalize()
        first = df.groupby(day).t.transform("min")          # buckets start at each session's open (09:15 in India)
        key = first + ((df.t - first) // step) * step
    codes, uniq = pd.factorize(key, sort=True)
    g = df.groupby(codes, sort=True)
    hdf = pd.DataFrame({"t": g.t.first(), "o": g.o.first(), "h": g.h.max(), "l": g.l.min(),
                        "c": g.c.last(), "v": g.v.sum()}).reset_index(drop=True)
    last_of_bucket = np.append(codes[1:] != codes[:-1], False)   # the final candle's bucket may still be open
    return hdf, np.where(last_of_bucket, codes, codes - 1)


def compute_full(ref, df: pd.DataFrame, intraday: bool) -> pd.Series:
    """compute(), plus the higher timeframe, "candles ago" and multiplier options a rule can add."""
    tf = getattr(ref, "tf", None)
    if tf and len(df):
        hdf, idx = higher_tf(df, tf)
        base = ref.model_copy(update={"tf": None, "ago": None, "k": None})
        vals = compute(base, hdf, intraday=tf != "1d").to_numpy(dtype=float)
        out = pd.Series(np.where(idx >= 0, vals[np.clip(idx, 0, None)], np.nan), index=df.index)
    else:
        out = compute(ref, df, intraday)
    if getattr(ref, "ago", None):
        out = out.shift(int(ref.ago))
    if getattr(ref, "k", None) and ref.t != "num":
        out = out * float(ref.k)
    return out


def compute(ref, df: pd.DataFrame, intraday: bool) -> pd.Series:
    t = ref.t
    c = df.c
    p, m = params(ref)
    if t == "price":
        return c
    if t == "sma":
        return c.rolling(p).mean()
    if t == "ema":
        return _ema(c, p)
    if t == "rsi":
        return rsi(c, p)
    if t.startswith("macd"):
        slow = int(m or 26)
        line = _ema(c, p) - _ema(c, slow)
        sig = line.ewm(span=9, adjust=False, min_periods=9).mean()
        return {"macd": line, "macd_signal": sig, "macd_hist": line - sig}[t]
    if t.startswith("bb_"):
        mid = c.rolling(p).mean()
        sd = c.rolling(p).std(ddof=0)
        k = m or 2
        return {"bb_upper": mid + k * sd, "bb_mid": mid, "bb_lower": mid - k * sd}[t]
    if t == "vwap":
        return vwap(df, p, intraday)
    if t == "supertrend":
        return supertrend(df, p, m or 3)
    if t == "stage":
        return stage(c, p, int(m or 20))
    if t == "adx":
        return adx(df, p)
    if t == "stoch_k":
        return stoch_k(df, p, int(m or 3))
    if t == "atr_pct":
        return atr_pct(df, p)
    if t == "dc_upper":        # the previous n candles' high, so "price crosses above" is a real breakout
        return df.h.rolling(p).max().shift(1)
    if t == "dc_lower":
        return df.l.rolling(p).min().shift(1)
    if t == "open":
        return df.o
    if t == "high":
        return df.h
    if t == "low":
        return df.l
    if t == "body":
        return (df.c - df.o).abs()
    if t == "upper_wick":
        return df.h - np.maximum(df.o, df.c)
    if t == "lower_wick":
        return np.minimum(df.o, df.c) - df.l
    if t == "range":
        return df.h - df.l
    if t == "atr":                 # average true range in price points
        return _wilder(true_range(df), p)
    if t in DAY:
        return day_values(df, t, intraday)
    if t in ("volume", "vol_sma"):
        vol = df.v.where(df.v > 0)        # indices have no volume: leave it blank rather than zero
        return vol if t == "volume" else vol.rolling(p).mean()
    raise ValueError(f"Unknown indicator {t}")


NAMES = {"open": "Open", "high": "High", "low": "Low", "body": "Candle body", "upper_wick": "Upper wick",
         "lower_wick": "Lower wick", "range": "Candle range", "prev_close": "Previous close", "day_open": "Day open",
         "day_high": "Day high", "day_low": "Day low", "day_chg": "Day change %"}
TF_WORD = {"15m": "15-min", "1h": "1-hour", "1d": "daily"}


def ref_name(ref) -> str:
    name = _base_name(ref)
    if getattr(ref, "tf", None):
        name += f" ({TF_WORD[ref.tf]})"
    if getattr(ref, "ago", None):
        name += f" {ref.ago} candle{'s' if ref.ago != 1 else ''} ago"
    if getattr(ref, "k", None) and ref.t != "num":
        name = f"{ref.k:g} × {name}"
    return name


def _base_name(ref) -> str:
    t = ref.t
    if t in NAMES:
        return NAMES[t]
    if t == "price":
        return "Price"
    if t == "num":
        return f"{ref.v:g}" if ref.v is not None else "value"
    p, m = params(ref)
    if t in ("sma", "ema", "rsi", "vwap"):
        return f"{t.upper()} {p}"
    if t.startswith("macd"):
        label = {"macd": "MACD", "macd_signal": "MACD signal", "macd_hist": "MACD histogram"}[t]
        return f"{label} {p},{int(m)}"
    if t.startswith("bb_"):
        return f"BB {t[3:]} {p},{m:g}"
    if t == "supertrend":
        return f"Supertrend {p},{m:g}"
    if t == "stage":
        return "Stage" if (p, int(m or 20)) == (150, 20) else f"Stage ({p}-candle average)"
    return {"adx": f"ADX {p}", "stoch_k": f"Stochastic {p}", "atr_pct": f"ATR% {p}", "dc_upper": f"Donchian high {p}",
            "dc_lower": f"Donchian low {p}", "volume": "Volume", "vol_sma": f"Volume SMA {p}", "atr": f"ATR {p}"}[t]
