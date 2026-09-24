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
}
# drawn under the price chart rather than on it
OSCILLATORS = {"rsi", "macd", "macd_signal", "macd_hist", "adx", "stoch_k", "atr_pct", "volume", "vol_sma"}


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
    if t in ("volume", "vol_sma"):
        vol = df.v.where(df.v > 0)        # indices have no volume: leave it blank rather than zero
        return vol if t == "volume" else vol.rolling(p).mean()
    raise ValueError(f"Unknown indicator {t}")


def ref_name(ref) -> str:
    t = ref.t
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
    return {"adx": f"ADX {p}", "stoch_k": f"Stochastic {p}", "atr_pct": f"ATR% {p}", "dc_upper": f"Donchian high {p}",
            "dc_lower": f"Donchian low {p}", "volume": "Volume", "vol_sma": f"Volume SMA {p}"}[t]
