"""A snapshot of real daily prices, for testing.

The admin downloads it from the Admin page; saved as `backend/tests/fixtures/real_prices.json.gz`, it lets the test
suite and the browser checks run on real market behaviour (32 sectors moving together, gaps, holidays) instead of
only on synthetic prices. It holds prices only: no user data and no credentials."""
import gzip
import json
from datetime import datetime, timezone

from . import rotation, sector_members, universes

DAYS = 520                     # about two years of trading days
PRESET_GROUPS = {"IN": ["nifty50", "banknifty"], "US": ["us_mega"]}


def _targets(registry, market: str) -> list[tuple[str, str, str]]:
    """(instrument id, symbol, kind) for everything in the snapshot."""
    out: list[tuple[str, str, str]] = []
    bench = rotation.benchmark_id(registry, market)
    out.append((bench[0], bench[1], "benchmark"))
    for set_id in rotation.index_sets(market):
        for iid, sym in rotation.resolve_sectors(registry, market, set_id)[0]:
            out.append((iid, sym, "index"))
    symbols = set()
    for pid in PRESET_GROUPS[market]:
        preset = next((p for p in universes.presets(market) if p["id"] == pid), None)
        symbols.update(preset["symbols"] if preset else [])
    for members in list(sector_members.BY_MARKET[market].values())[:6]:      # a few sectors' stocks, for drill-downs
        symbols.update(members)
    ids, _ = universes.resolve(registry, market, [{"symbol": s} for s in sorted(symbols)])
    out += [(i, i.split(":", 1)[1], "stock") for i in ids]
    seen, uniq = set(), []
    for t in out:
        if t[0] not in seen:
            seen.add(t[0])
            uniq.append(t)
    return uniq


def build(registry, markets=("IN", "US"), days: int = DAYS) -> dict:
    """{"generated_at", "days", "markets": {market: {symbol: {"id", "kind", "bars": [[t, o, h, l, c, v], ...]}}}, "problems"}."""
    snap = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "days": days, "markets": {}, "problems": []}
    for market in markets:
        prov = registry.provider(market)
        if prov is None or not prov.ready():
            snap["problems"].append(f"{market}: market data is offline")
            continue
        rows = {}
        for iid, sym, kind in _targets(registry, market):
            try:
                p, inst = registry.resolve(iid)
                bars = p.history(inst, "1d", days)
            except Exception as e:                     # one instrument's problem mustn't sink the snapshot
                snap["problems"].append(f"{sym}: {str(e)[:80]}")
                continue
            rows[sym] = {"id": iid, "kind": kind, "name": (inst or {}).get("name") or sym,
                         "bars": [[str(b["t"])[:10], b["o"], b["h"], b["l"], b["c"], b.get("v", 0)] for b in bars]}
        snap["markets"][market] = rows
    return snap


def pack(snap: dict) -> bytes:
    return gzip.compress(json.dumps(snap, separators=(",", ":")).encode(), compresslevel=9)


def load(path: str) -> dict:
    with gzip.open(path, "rt") as f:
        return json.load(f)


def bars(snap: dict, market: str, symbol: str) -> list[dict]:
    """A symbol's bars back in the app's own shape."""
    row = snap.get("markets", {}).get(market, {}).get(symbol)
    return [{"t": t, "o": o, "h": h, "l": lo, "c": c, "v": v} for t, o, h, lo, c, v in (row or {}).get("bars", [])]
