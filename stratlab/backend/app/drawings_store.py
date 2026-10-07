"""Each user's chart drawings and chart layout, per region and symbol (GET/PUT /me/drawings/{region}/{symbol}).

One settings row per user and symbol holds the drawings (lines, boxes, notes the person drew themselves, anchored to a
time and a price) and the layout (timeframe, indicators shown). A small index row per user lists the symbols that have
a row, so the oldest can be dropped past a cap and everything can be removed in one call. Facts only: nothing here
reads or scores a drawing."""
import json
import re
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from . import chart_data, db

KEY = "drawings:"            # drawings:{uid}:{REGION}:{SYMBOL}
INDEX = "drawings_idx:"      # drawings_idx:{uid}  -> {"REGION:SYMBOL": saved-at}
MAX_DRAWINGS = 300           # drawings per symbol
MAX_POINTS = 400             # points in one brush stroke
MAX_BYTES = 96 * 1024        # one symbol's stored JSON
MAX_SYMBOLS = 500            # symbols with drawings per user; the oldest drop off
REGION = re.compile(r"^[A-Za-z][A-Za-z0-9]{1,11}$")
SYMBOL = chart_data.SYMBOL
ID = re.compile(r"^[A-Za-z0-9_-]{1,40}$")

KINDS = ("trend", "ray", "hline", "hray", "vline", "rect", "channel", "fib", "long", "short",
         "measure", "prange", "drange", "text", "arrow", "brush")
# how many points each kind is made of (a brush has as many as its stroke)
POINTS = {"trend": 2, "ray": 2, "hline": 1, "hray": 1, "vline": 1, "rect": 2, "channel": 3, "fib": 2, "long": 3, "short": 3,
          "measure": 2, "prange": 2, "drange": 2, "text": 1, "arrow": 2}
COLORS = ("ink", "blue", "orange", "green", "magenta", "grey")
STUDIES = ("sma", "ema", "rsi", "vwap", "supertrend", "stage", "bb", "macd", "hl52")
TFS = ("5m", "15m", "1h", "1d", "1w", "1mo")
CHART_TYPES = ("candles", "hollow", "heikin", "bars", "line", "area", "baseline")


class Point(BaseModel):
    model_config = ConfigDict(extra="ignore")
    t: float = Field(..., allow_inf_nan=False, ge=-1e15, le=1e15)       # time, ms since 1970
    p: float = Field(..., allow_inf_nan=False, ge=-1e15, le=1e15)       # price


class Drawing(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    kind: Literal[KINDS]
    points: list[Point] = Field(..., min_length=1, max_length=MAX_POINTS)
    text: str | None = Field(None, max_length=200)
    color: Literal[COLORS] | None = None
    dash: Literal["solid", "dashed", "dotted"] | None = None
    locked: bool = False
    hidden: bool = False
    born: float | None = Field(None, allow_inf_nan=False, ge=-1e15, le=1e15)      # last candle's time when drawn (chart replay)
    risk: float | None = Field(None, allow_inf_nan=False, ge=0, le=1e12)        # a position's risk amount

    @field_validator("id")
    @classmethod
    def _id(cls, v: str) -> str:
        if not ID.match(v):
            raise ValueError("a drawing id is letters, digits, - and _ (up to 40)")
        return v

    @model_validator(mode="after")
    def _points(self):
        want = POINTS.get(self.kind)
        n = len(self.points)
        if want is not None and n != want:
            raise ValueError(f"a {self.kind} drawing has {want} point{'s' if want > 1 else ''}")
        if want is None and n < 2:
            raise ValueError("a brush stroke has at least 2 points")
        return self


class Study(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(..., pattern=r"^[A-Za-z0-9_.:,-]{1,60}$")
    type: Literal[STUDIES]
    params: list[float] = Field(default_factory=list, max_length=4)
    slot: int = Field(0, ge=0, le=40)

    @field_validator("params")
    @classmethod
    def _finite(cls, v: list[float]) -> list[float]:
        if any(x != x or abs(x) > 1e6 for x in v):
            raise ValueError("indicator settings must be ordinary numbers")
        return v


class Layout(BaseModel):
    model_config = ConfigDict(extra="ignore")
    tf: Literal[TFS] | None = None
    range: str | None = Field(None, pattern=r"^(1D|5D|1M|6M|YTD|1Y|5Y|All)$")
    type: Literal[CHART_TYPES] | None = None
    volume: bool | None = None
    hide_drawings: bool | None = None
    studies: list[Study] | None = Field(None, max_length=12)


class Payload(BaseModel):
    model_config = ConfigDict(extra="ignore")
    drawings: list[Drawing] = Field(default_factory=list, max_length=MAX_DRAWINGS)
    layout: Layout | None = None


def region_of(region: str) -> str | None:
    return region.upper() if REGION.match(region or "") else None


def symbol_of(symbol: str) -> str | None:
    return symbol.upper() if SYMBOL.match(symbol or "") else None


def _row(uid: str, region: str, symbol: str) -> str:
    return f"{KEY}{uid}:{region}:{symbol}"


def _index(uid: str) -> dict:
    try:
        v = json.loads(db.get_setting(INDEX + uid) or "{}")
    except (ValueError, TypeError):
        return {}
    return v if isinstance(v, dict) else {}


def load(uid: str, region: str, symbol: str) -> dict:
    """What is saved for this symbol: {"drawings": [...], "layout": {...} | None, "updated_at": iso | None}. A symbol
    with nothing under the new row falls back to what the older chart saved for it ("REGION:SYMBOL")."""
    try:
        got = json.loads(db.get_setting(_row(uid, region, symbol)) or "null")
    except (ValueError, TypeError):
        got = None
    if isinstance(got, dict):
        return {"drawings": got.get("drawings") or [], "layout": got.get("layout"), "updated_at": got.get("at")}
    old = chart_data.drawings(uid, f"{region}:{symbol}")
    return {"drawings": old, "layout": None, "updated_at": None}


def body_size(payload: Payload) -> int:
    return len(json.dumps(payload.model_dump(exclude_none=True, mode="json"), separators=(",", ":")))


def save(uid: str, region: str, symbol: str, payload: Payload) -> dict:
    """Replace this symbol's drawings and layout. Nothing left (no drawings, no layout) removes the row."""
    data = payload.model_dump(exclude_none=True, mode="json")
    layout = data.get("layout") or None
    body = {"drawings": data.get("drawings", []), "layout": layout}
    idx = _index(uid)
    name = f"{region}:{symbol}"
    if not body["drawings"] and not layout:
        db.delete_setting(_row(uid, region, symbol))
        idx.pop(name, None)
        _write_index(uid, idx)
        return {"drawings": [], "layout": None, "updated_at": None}
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    body["at"] = now
    db.set_setting(_row(uid, region, symbol), json.dumps(body, separators=(",", ":")))
    idx.pop(name, None)
    idx[name] = now
    for old in sorted(idx, key=lambda k: str(idx[k]))[:max(0, len(idx) - MAX_SYMBOLS)]:      # the oldest drop off
        idx.pop(old)
        r, _, s = old.partition(":")
        db.delete_setting(_row(uid, r, s))
    _write_index(uid, idx)
    return {"drawings": body["drawings"], "layout": layout, "updated_at": now}


def _write_index(uid: str, idx: dict) -> None:
    if idx:
        db.set_setting(INDEX + uid, json.dumps(idx, separators=(",", ":")))
    else:
        db.delete_setting(INDEX + uid)


def forget_symbol(uid: str, region: str, symbol: str) -> None:
    idx = _index(uid)
    idx.pop(f"{region}:{symbol}", None)
    db.delete_setting(_row(uid, region, symbol))
    _write_index(uid, idx)


def forget(uid: str) -> int:
    """Every saved drawing and layout of one user (the delete-all button; the hook for deleting an account)."""
    idx = _index(uid)
    for name in idx:
        r, _, s = name.partition(":")
        db.delete_setting(_row(uid, r, s))
    db.delete_setting(INDEX + uid)
    return len(idx)
