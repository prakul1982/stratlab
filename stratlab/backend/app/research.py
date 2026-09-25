"""Load candles for a test, run the backtest and the verdict, and pack the result
into an experiment record small enough to keep in a notebook."""
from datetime import datetime, timedelta, timezone

from .engine import costs as C
from .engine.core import backtest
from .engine.verdict import evaluate

MAX_POINTS = 240       # chart points kept per experiment
MAX_TRADES = 200
MIN_BARS = 30


class ResearchError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def parse_t(t: str) -> datetime:
    d = datetime.fromisoformat(str(t).strip().replace("Z", "+00:00").replace(" ", "T", 1))
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def upload_instrument(meta) -> dict:
    return {"id": "CSV:upload", "token": None, "symbol": meta.name, "name": meta.name, "exchange": "Your data",
            "type": "CSV", "market": "CSV", "currency": meta.currency or "", "step": meta.step, "lot": 1,
            "fno": False, "expiry": None, "strike": None, "tz": "UTC"}


def clean_upload(raw) -> list[dict]:
    rows = {}
    for b in raw:
        try:
            t = parse_t(b.t)
        except ValueError:
            raise ResearchError(400, "bad_upload", f"Couldn't read the date '{b.t[:25]}'. Use a format like 2024-03-15 or 2024-03-15T09:15:00.")
        if min(b.o, b.h, b.l, b.c) <= 0 or b.h < b.l:
            continue
        rows[t] = {"t": t.isoformat(), "o": b.o, "h": b.h, "l": b.l, "c": b.c, "v": b.v}
    bars = [rows[k] for k in sorted(rows)]
    if len(bars) < MIN_BARS:
        raise ResearchError(400, "bad_upload", f"The file needs at least {MIN_BARS} valid candles; it had {len(bars)}.")
    return bars


def load(registry, strategy, req) -> dict:
    """Candles and settings for one test. Raises ResearchError for anything the user can fix."""
    tf = strategy.tf
    if req.bars:
        bars = clean_upload(req.bars)
        inst = upload_instrument(req.upload or _default_meta())
        start = min(200, len(bars) // 5)
        days = max(1, (parse_t(bars[-1]["t"]) - parse_t(bars[start]["t"])).days)
        return {"inst": inst, "bars": bars, "start": start, "days": days, "max_days": days,
                "lot": inst["step"], "kind": "flat"}
    if not req.instrument:
        raise ResearchError(400, "no_instrument", "Pick an instrument or upload candles first.")
    prov, inst = registry.resolve(req.instrument)
    if prov is None:
        raise ResearchError(400, "market_unavailable", "That market isn't connected yet.")
    if not prov.ready():
        raise ResearchError(503, "data_offline", "Market data for this market is offline right now. Try again soon.")
    if inst is None:
        raise ResearchError(404, "instrument_not_found", "That instrument was not found. Search again.")
    max_days = prov.max_days[tf]
    days = min(req.days, max_days)
    bars = prov.history(inst, tf, days + prov.warmup_days(tf))
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    start = next((i for i, b in enumerate(bars) if parse_t(b["t"]) >= cutoff), len(bars))
    if len(bars) - start < 10:
        raise ResearchError(400, "not_enough_data", "Not enough price history for this period. Pick a longer period or another instrument.")
    lot = inst.get("step") or (inst["lot"] if inst.get("fno") else 1)
    return {"inst": inst, "bars": bars, "start": start, "days": days, "max_days": max_days,
            "lot": lot, "kind": C.kind_of(inst)}


def _default_meta():
    from .models import UploadMeta
    return UploadMeta()


def run(strategy, data: dict) -> dict:
    """Backtest plus verdict."""
    bars, start = data["bars"], data["start"]
    out = backtest(bars, strategy, start, data["lot"], data["kind"])
    out["verdict"] = evaluate(bars, strategy, start, out, data["lot"], data["kind"], data["days"], data["max_days"])
    out.update({"instrument": data["inst"], "lot": data["lot"], "days": data["days"], "warmup_short": start < 200})
    return out


def _pick(n: int) -> list[int]:
    if n <= MAX_POINTS:
        return list(range(n))
    step = (n - 1) / (MAX_POINTS - 1)
    return sorted({round(i * step) for i in range(MAX_POINTS)})


def record(result: dict, strategy, label: str, version: int, now: str) -> dict:
    """The compact, storable form of one experiment: everything the verdict page draws."""
    bars = result["bars"]
    idx = _pick(len(bars))
    ds = lambda xs: [xs[i] for i in idx]
    split = next((c["data"]["split_index"] for c in result["verdict"]["checks"]
                  if c["id"] == "unseen" and c.get("data")), None)
    split_ds = None if split is None else min(range(len(idx)), key=lambda k: abs(idx[k] - split))
    inst = result["instrument"]
    trades = list(result["trades"][-MAX_TRADES:])
    if result.get("open_trade"):
        trades.append(result["open_trade"])
    return {
        "v": version, "label": label or f"Experiment v{version}", "created_at": now,
        "strategy": strategy.model_dump(),
        "instrument": {k: inst.get(k) for k in ("id", "symbol", "name", "market", "currency", "exchange", "type", "lot", "step", "fno", "tz")},
        "days": result["days"], "tf": strategy.tf, "candles": len(bars),
        "range": {"from": bars[0]["t"], "to": bars[-1]["t"]},
        "stats": result["stats"], "costs": result["costs"], "verdict": result["verdict"],
        "series": {"t": ds([b["t"] for b in bars]), "close": ds([b["c"] for b in bars]),
                   "equity": ds(result["equity"]), "buy_hold": ds(result["buy_hold"]),
                   "overlays": {k: ds(v) for k, v in list(result["overlays"].items())[:4]},
                   "split": split_ds},
        "trades": trades,
    }


def summary(experiments: list[dict]) -> dict:
    last = experiments[-1] if experiments else None
    return {"experiments": len(experiments),
            "last_verdict": last["verdict"]["verdict"] if last else None,
            "last_label": last["label"] if last else None}


def run_group(datasets: list[dict], strategy, group: dict, days: int, max_days: int) -> dict:
    """A portfolio backtest over a group of instruments, with its verdict."""
    from .engine import portfolio
    from .engine.verdict import evaluate_portfolio
    max_open = max(1, int(group.get("maxOpen") or len(datasets)))
    go = lambda t_from=None, t_to=None: portfolio.run(datasets, strategy, max_open, t_from, t_to)  # noqa: E731
    base = go()
    base["verdict"] = evaluate_portfolio(go, base, strategy, days, max_days)
    base["days"], base["max_open"] = days, max_open
    return base


def record_group(result: dict, strategy, label: str, version: int, now: str, group: dict, datasets: list[dict], problems: list[str]) -> dict:
    """The storable form of a group experiment: equity rather than one price chart, plus each member's result."""
    times = result["times"]
    idx = _pick(len(times)) if times else []
    ds = lambda xs: [xs[i] for i in idx]
    split = next((c["data"]["split_index"] for c in result["verdict"]["checks"] if c["id"] == "unseen" and c.get("data")), None)
    split_ds = None if split is None or not idx else min(range(len(idx)), key=lambda k: abs(idx[k] - split))
    first = datasets[0]["inst"] if datasets else {}
    trades = list(result["trades"][-MAX_TRADES:]) + result["open_trades"]
    return {
        "v": version, "label": label or f"Experiment v{version}", "created_at": now,
        "strategy": strategy.model_dump(),
        "instrument": {"id": f"GROUP:{group.get('id') or 'custom'}", "symbol": group.get("name") or "My group", "name": group.get("name"),
                       "market": group.get("market") or first.get("market"), "currency": first.get("currency"), "tz": first.get("tz"),
                       "type": "GROUP"},
        "days": result["days"], "tf": strategy.tf, "candles": len(times),
        "range": {"from": times[0] if times else now, "to": times[-1] if times else now},
        "stats": result["stats"], "costs": result["costs"], "verdict": result["verdict"],
        "series": {"t": ds(times), "close": [], "equity": ds(result["equity"]), "buy_hold": ds(result["buy_hold"]),
                   "overlays": {}, "split": split_ds},
        "trades": trades,
        "group": {"name": group.get("name"), "members": result["members"], "max_open": result["max_open"],
                  "most_open": result["most_open"], "skipped": problems},
    }
