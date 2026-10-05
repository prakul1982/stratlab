"""The price chart's data: which window of candles to read for a timeframe and range, older history for scrolling
back (lazy loading), and each user's chart drawings per symbol.

Facts only: candles as the market printed them, and lines the user drew themselves."""
import json
import re
from datetime import datetime, timezone

from . import db

TFS = ("5m", "15m", "1h", "1d")
# the first read for each timeframe when no range is asked for: enough candles to fill a screen and warm up indicators
FIRST = {"5m": 10, "15m": 30, "1h": 120, "1d": 366}
# each older page read when the chart is scrolled back
PAGE = {"5m": 10, "15m": 30, "1h": 120, "1d": 1100}
RANGES = {"1d": 4, "5d": 8, "1m": 31, "3m": 93, "6m": 186, "ytd": None, "1y": 366, "3y": 1100, "5y": 1830, "max": 3650 * 3}

KEY = "chart_drawings:"
MAX_SYMBOLS = 200          # symbols with drawings kept per user; the oldest drop off
MAX_DRAWINGS = 100         # drawings per symbol
MAX_BYTES = 256 * 1024     # one user's stored drawings, all symbols; the oldest symbols drop off past it
SYMBOL = re.compile(r"^[A-Za-z0-9:^&._=-]{1,40}$")


def parse_before(before: str | None) -> datetime | None:
    """An ISO date or time, made timezone-aware (UTC when it has none); None when blank or unreadable."""
    if not before:
        return None
    text = before.strip().replace("Z", "+00:00")
    if "T" in text and " " in text:          # an unescaped "+05:30" in a query string arrives as " 05:30"
        text = text.replace(" ", "+")
    try:
        t = datetime.fromisoformat(text)
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def window(tf: str, rng: str | None, before: datetime | None, max_days: int | None, now: datetime | None = None) -> tuple[int, bool]:
    """(days to read back from now, whether older candles exist beyond them) for one chart read."""
    now = now or datetime.now(timezone.utc)
    cap = max_days or 3650
    if before is not None:
        days = max(1, (now - before).days + 1) + PAGE[tf]
    elif rng in RANGES and tf == "1d":
        days = RANGES[rng] if rng != "ytd" else (now.date() - now.date().replace(month=1, day=1)).days + 8
    else:
        days = FIRST[tf]
    return min(days, cap), days < cap


def older(candles: list[dict], before: datetime | None) -> list[dict]:
    """Only the candles that start before a time: the page of history the chart doesn't have yet."""
    if before is None:
        return candles
    out = []
    for b in candles:
        t = parse_before(b.get("t"))
        if t is not None and t < before:
            out.append(b)
    return out


# ---------- drawings ----------
def _all(uid: str) -> dict:
    try:
        v = json.loads(db.get_setting(KEY + uid) or "{}")
    except (ValueError, TypeError):
        return {}
    return v if isinstance(v, dict) else {}


def drawings(uid: str, symbol: str) -> list[dict]:
    got = (_all(uid).get(symbol) or {}).get("items")
    return got if isinstance(got, list) else []


def _num(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and abs(x) < 1e15 and x == x


def clean(items: list) -> list[dict]:
    """Keep only well-formed drawings: a known kind, one to two points of (time in ms, price), short text."""
    out = []
    for d in items[:MAX_DRAWINGS]:
        if not isinstance(d, dict) or d.get("kind") not in ("trend", "hline", "ray", "rect", "fib", "text"):
            continue
        pts = [p for p in (d.get("points") or []) if isinstance(p, dict) and _num(p.get("t")) and _num(p.get("p"))][:2]
        if not pts:
            continue
        out.append({"id": str(d.get("id") or "")[:40], "kind": d["kind"],
                    "points": [{"t": float(p["t"]), "p": float(p["p"])} for p in pts],
                    "text": str(d.get("text") or "")[:200]})
    return out


def save(uid: str, symbol: str, items: list) -> list[dict]:
    """Replace one symbol's drawings; an empty list removes the symbol."""
    data = _all(uid)
    kept = clean(items)
    data.pop(symbol, None)
    if kept:
        data[symbol] = {"items": kept, "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    oldest = [k for k in sorted(data, key=lambda k: str(data[k].get("at", ""))) if k != symbol]
    while len(data) > MAX_SYMBOLS and oldest:
        data.pop(oldest.pop(0))
    size = {k: len(json.dumps(k)) + len(json.dumps(v, separators=(",", ":"))) + 2 for k, v in data.items()}
    total = sum(size.values()) + 2
    while total > MAX_BYTES and oldest:         # many full charts: keep the stored row small, newest kept
        k = oldest.pop(0)
        total -= size[k]
        data.pop(k)
    raw = json.dumps(data, separators=(",", ":"))
    if data:
        db.set_setting(KEY + uid, raw)
    else:
        db.delete_setting(KEY + uid)
    return kept


def forget(uid: str) -> None:
    db.delete_setting(KEY + uid)
