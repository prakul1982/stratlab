"""Trend scan presets: named rule sets over the indicators the rules engine already has, and the stored results of the
daily run.

A preset is a short list of the same conditions the strategy builder uses (every one must hold) plus, for the
Bollinger squeeze, one check on the width of the bands. A scan says only what was true of the chart: "matches <rule>
as of <date>", with the numbers. It never says to buy or sell.

Where the answers come from:
- Small groups (a watchlist, the 20 to 50 stocks of a ready-made group) are read live, from the daily candles the
  Stage 2 + Supertrend scan already caches (scan.run_preset).
- Large groups (NIFTY 500, S&P 500) are worked out once a day by the breadth run, which already reads every member's
  candles after the close; the matches of every preset are stored beside its counts (scanres:<group>), so a scan of
  500 stocks is one read, not 500 chart requests."""
import json
import math
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np

from . import db
from .engine.core import Ctx, eval_cond
from .engine.indicators import compute
from .models import Cond, Ref

KEY = "scanres:"                   # scanres:<group> = {"as_of", "at", "checked", "counts", "rows"}
MIN_BARS = 60                      # fewer daily candles than this and nothing is worked out
MAX_BARS = 330                     # only the latest candles matter (the longest rule looks back 253): older ones are left out for speed
YEAR = 252                         # trading days in 52 weeks
SQUEEZE_DAYS, SQUEEZE_PCT = 120, 0.2
# groups whose results the daily run stores (the group ids of breadth.GROUPS)
STORED = {"IN": "nifty500", "US": "sp500"}


def _c(l: dict, op: str, r: dict) -> dict:
    return {"l": l, "op": op, "r": r}


def _num(v: float) -> dict:
    return {"t": "num", "v": v}


PRICE = {"t": "price"}
PRESETS: list[dict] = [
    {"id": "st_s2", "name": "Stage 2 + Supertrend", "within": 1,
     "text": "The price is above a rising 150-day average (Stage 2) and above the Supertrend (10 days, 3 times the average daily range).",
     "rules": [_c({"t": "stage", "p": 150, "m": 20}, "eq", _num(2)), _c(PRICE, "gt", {"t": "supertrend", "p": 10, "m": 3})]},
    {"id": "high52", "name": "52-week high breakout", "within": 3,
     "text": "The close went above the highest high of the previous 252 trading days (about 52 weeks).",
     "rules": [_c(PRICE, "xa", {"t": "dc_upper", "p": YEAR})]},
    {"id": "golden_cross", "name": "Golden cross (50/200)", "within": 5,
     "text": "The 50-day average crossed above the 200-day average.",
     "rules": [_c({"t": "sma", "p": 50}, "xa", {"t": "sma", "p": 200})]},
    {"id": "rsi_bounce", "name": "RSI oversold bounce", "within": 3,
     "text": "The 14-day RSI crossed back above 30, after closing at or below it.",
     "rules": [_c({"t": "rsi", "p": 14}, "xa", _num(30))]},
    {"id": "volume_surge", "name": "Volume surge", "within": 1,
     "text": "Volume was more than 2 times its average of the 20 days before, and the close was above the previous close.",
     "rules": [_c({"t": "volume"}, "gt", {"t": "vol_sma", "p": 20, "ago": 1, "k": 2}), _c(PRICE, "gt", {"t": "price", "ago": 1})]},
    {"id": "bb_squeeze", "name": "Bollinger squeeze breakout", "within": 3,
     "text": f"The close went above the upper Bollinger band (20 days, 2 standard deviations) the day after the bands' width was in the narrowest {int(SQUEEZE_PCT * 100)}% of the last {SQUEEZE_DAYS} days.",
     "rules": [_c(PRICE, "xa", {"t": "bb_upper", "p": 20, "m": 2})], "squeeze": True},
    {"id": "near_low52", "name": "Near 52-week low", "within": 1,
     "text": "The close is within 5% of the lowest low of the previous 252 trading days, or below it.",
     "rules": [_c(PRICE, "lt", {"t": "dc_lower", "p": YEAR, "k": 1.05})]},
    {"id": "pullback", "name": "Pullback in an uptrend", "within": 1,
     "text": "The 50-day average is above the 200-day average and the close is above the 50-day, but below the 20-day average.",
     "rules": [_c({"t": "sma", "p": 50}, "gt", {"t": "sma", "p": 200}), _c(PRICE, "gt", {"t": "sma", "p": 50}),
               _c(PRICE, "lt", {"t": "ema", "p": 20})]},
]
for _p in PRESETS:
    _p["conds"] = [Cond.model_validate(r) for r in _p["rules"]]
BY_ID = {p["id"]: p for p in PRESETS}
DEFAULT = "high52"


def listing() -> list[dict]:
    """What the page shows for each preset: id, name, the rule in words, and how recent a match counts."""
    from .engine.core import cond_text
    out = []
    for p in PRESETS:
        words = [cond_text(c) for c in p["conds"]]
        if p.get("squeeze"):
            words.append(f"the bands' width the day before was in the narrowest {int(SQUEEZE_PCT * 100)}% of the last {SQUEEZE_DAYS} days")
        out.append({"id": p["id"], "name": p["name"], "text": p["text"], "rules": words, "within": p["within"]})
    return out


# ---------- working one stock out ----------
def _squeeze_flags(ctx: Ctx) -> np.ndarray:
    """True on a day when the day before had one of the narrowest band widths of the last SQUEEZE_DAYS."""
    df = ctx.df
    upper, lower, mid = (compute(Ref(t=t, p=20, m=2), df, False) for t in ("bb_upper", "bb_lower", "bb_mid"))
    width = ((upper - lower) / mid.where(mid > 0)).shift(1)
    narrow = width <= width.rolling(SQUEEZE_DAYS).quantile(SQUEEZE_PCT)
    return narrow.fillna(False).to_numpy(dtype=bool)


def _f(v: float) -> str:
    return f"{v:,.2f}"


def _detail(pid: str, ctx: Ctx, i: int, live: bool = False) -> str:
    """The numbers behind a match on one candle, as plain text. `live`: read just now, when the newest candle may be
    today's, still trading, so its price is the last price, not a close (R5O-023)."""
    px = ctx.val(Ref(t="price"), i)
    newest = i == len(ctx.df) - 1
    at, word = ("Last price", "last price") if live and newest else ("Closed at", "close")

    def val(t, **kw):
        return ctx.val(Ref(t=t, **kw), i)
    try:
        if pid == "high52":
            return f"{at} {_f(px)}, above the previous 252-day high of {_f(val('dc_upper', p=YEAR))}"
        if pid == "golden_cross":
            return f"50-day average {_f(val('sma', p=50))} crossed above the 200-day average {_f(val('sma', p=200))}"
        if pid == "rsi_bounce":
            return f"14-day RSI is {val('rsi', p=14):.1f}, back above 30 from {ctx.val(Ref(t='rsi', p=14), i - 1):.1f}"
        if pid == "volume_surge":
            v, avg = val("volume"), val("vol_sma", p=20, ago=1)
            return f"Volume {v:,.0f} is {v / avg:.1f} times the 20-day average of {avg:,.0f}; the {word} {_f(px)} is above the previous close"
        if pid == "bb_squeeze":
            return f"{at} {_f(px)}, above the upper band of {_f(val('bb_upper', p=20, m=2))}, after a squeeze"
        if pid == "near_low52":
            low = val("dc_lower", p=YEAR)
            return f"{at} {_f(px)}, {(px / low - 1) * 100:.1f}% above the previous 252-day low of {_f(low)}" if px >= low \
                else f"{at} {_f(px)}, below the previous 252-day low of {_f(low)}"
        if pid == "pullback":
            return f"{at} {_f(px)}: above the 50-day average {_f(val('sma', p=50))}, below the 20-day {_f(val('ema', p=20))}; 50-day above 200-day {_f(val('sma', p=200))}"
        if pid == "st_s2":
            return f"Stage 2, and the {word} {_f(px)} is above the Supertrend {_f(val('supertrend', p=10, m=3))}"
    except (TypeError, ValueError, ZeroDivisionError):
        pass
    return ""


def evaluate(bars: list[dict], through: str | None = None, only: list[str] | None = None, live: bool = False) -> dict | None:
    """Every preset's answer for one stock's daily candles (up to the day `through`, "YYYY-MM-DD"):
    {"as_of", "price", "chg", "matches": {id: {"days_ago", "day", "detail"}}}. None when there are too few candles.
    A preset matches when all its conditions held on one of its last `within` candles; the latest such candle counts."""
    rows = [b for b in bars or [] if isinstance(b, dict) and (through is None or str(b.get("t"))[:10] <= through)]
    if len(rows) < MIN_BARS:
        return None
    rows = rows[-MAX_BARS:]
    try:
        ctx = Ctx(rows, False)
    except (KeyError, ValueError, TypeError):
        return None
    df = ctx.df
    last = len(df) - 1
    close, prev = float(df["c"].iloc[-1]), float(df["c"].iloc[-2])
    if not (math.isfinite(close) and close > 0):
        return None
    out = {"as_of": str(rows[-1]["t"])[:10], "price": close, "chg": (close / prev - 1) * 100 if prev > 0 else None, "matches": {}}
    for p in PRESETS:
        if only is not None and p["id"] not in only:
            continue
        try:
            squeeze = _squeeze_flags(ctx) if p.get("squeeze") else None
            for back in range(min(p["within"], last)):
                i = last - back
                if squeeze is not None and not squeeze[i]:
                    continue
                if all(eval_cond(ctx, c, i) for c in p["conds"]):
                    out["matches"][p["id"]] = {"days_ago": back, "day": str(rows[i]["t"])[:10], "detail": _detail(p["id"], ctx, i, live)}
                    break
        except Exception as e:      # one preset's data problem leaves the others' answers standing
            print("scan preset:", p["id"], str(e)[:100])
    return out


# ---------- the daily results ----------
def build(per_stock: dict[str, dict], now: datetime | None = None) -> dict:
    """The stored shape for one group from {symbol: evaluate() answer}: only stocks that match something get a row."""
    rows, counts = [], {p["id"]: 0 for p in PRESETS}
    for sym in sorted(per_stock):
        r = per_stock[sym]
        if not r:
            continue
        for pid in r["matches"]:
            counts[pid] += 1
        if r["matches"]:
            rows.append({"s": sym, "p": round(r["price"], 4), "c": None if r["chg"] is None else round(r["chg"], 2), "d": r["as_of"],
                         "m": {pid: [m["days_ago"], m["day"], m["detail"]] for pid, m in r["matches"].items()}})
    checked = [r for r in per_stock.values() if r]
    return {"as_of": max((r["as_of"] for r in checked), default=None), "at": (now or datetime.now(ZoneInfo("UTC"))).isoformat(timespec="seconds"),
            "checked": len(checked), "counts": counts, "rows": rows}


def save(group: str, doc: dict):
    db.set_setting(KEY + group, json.dumps(doc, separators=(",", ":")))


def load(group: str) -> dict | None:
    try:
        raw = db.json_value(db.get_setting(KEY + group), {})
    except Exception:
        return None
    return raw if isinstance(raw, dict) and isinstance(raw.get("rows"), list) else None


def stored_view(group: str, preset: str) -> dict | None:
    """The stored matches of one preset in one group, most recent first: {"as_of", "at", "checked", "rows": [{symbol, price,
    chg, as_of, days_ago, day, detail}]}. None when the daily run hasn't stored this group yet."""
    doc = load(group)
    if doc is None or preset not in BY_ID:
        return None
    rows = []
    for r in doc["rows"]:
        m = (r.get("m") or {}).get(preset)
        if m:
            rows.append({"symbol": r["s"], "price": r.get("p"), "chg": r.get("c"), "as_of": r.get("d"),
                         "days_ago": m[0], "day": m[1], "detail": m[2]})
    rows.sort(key=lambda x: (x["days_ago"], x["symbol"]))
    return {"as_of": doc.get("as_of"), "at": doc.get("at"), "checked": doc.get("checked", 0), "rows": rows,
            "counts": doc.get("counts") or {}}
