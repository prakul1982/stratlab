"""Load candles for a test, run the backtest and the verdict, and pack the result
into an experiment record small enough to keep in a notebook."""
import json
from datetime import datetime, timedelta, timezone

from .data.calendar import trading_bars
from .engine import costs as C
from .engine.core import backtest
from .engine.verdict import evaluate

MAX_POINTS = 240       # chart points kept per experiment
MAX_TRADES = 200
KEEP_FULL = 10         # the newest experiments in a notebook keep every trade; older ones keep their last few
OLD_TRADES = 30
MIN_BARS = 30


class ResearchError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message

    def __reduce__(self):                  # sent back from a backtest worker process intact
        return (ResearchError, (self.status, self.code, self.message))


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
    # a weekday market is only ever tested on the days it trades, whatever the feed sent
    bars = trading_bars(inst.get("market"), prov.history(inst, tf, days + prov.warmup_days(tf)), tf)
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


def _with_fo(strategy, inst: dict | None, bars: list[dict]) -> list[dict]:
    """An Indian stock's daily candles with its stored F&O facts by day (stock_futures.enrich), when a rule uses one of
    the F&O values (OI change, rollover, basis); other candles as they are."""
    from .engine.indicators import FO_REFS
    try:
        text = json.dumps(strategy.model_dump()) if hasattr(strategy, "model_dump") else ""
    except (TypeError, ValueError):
        return bars
    if not inst or not any(f'"{t}"' in text for t in FO_REFS) or not str(inst.get("id") or "").startswith("IN:"):
        return bars
    from . import stock_futures
    return stock_futures.enrich(str(inst.get("symbol") or ""), bars)


def run(strategy, data: dict) -> dict:
    """Backtest plus verdict."""
    bars, start = data["bars"], data["start"]
    bars = _with_fo(strategy, data.get("inst"), bars)
    out = backtest(bars, strategy, start, data["lot"], data["kind"])
    out["verdict"] = evaluate(bars, strategy, start, out, data["lot"], data["kind"], data["days"], data["max_days"])
    for k in ("_paths", "_split"):           # the checks' working, not part of the result
        out.pop(k, None)
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
    base.pop("_paths", None)
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


def slim(experiments: list[dict]) -> list[dict]:
    """Keep storage in check: experiments older than the newest KEEP_FULL keep their verdict, stats and chart but
    only their last OLD_TRADES trades (the count trimmed is noted, so the page can say so)."""
    out = []
    cut = len(experiments) - KEEP_FULL
    for i, e in enumerate(experiments):
        trades = e.get("trades") or []
        if i < cut and len(trades) > OLD_TRADES:
            e = {**e, "trades": trades[-OLD_TRADES:], "trades_trimmed": e.get("trades_trimmed", 0) + len(trades) - OLD_TRADES}
        out.append(e)
    return out


# ---------- what changed between two experiments ----------
_SKIP_KEYS = ("name", "text")          # renaming the notebook or re-wording the idea changes nothing tested


def _setup(strategy: dict | None) -> dict:
    return {k: v for k, v in (strategy or {}).items() if k not in _SKIP_KEYS}


def unchanged(experiments: list[dict], strategy, inst_id: str | None, days: int, now: str) -> int | None:
    """The version of the last experiment when running again would repeat it exactly: the same rules, instrument and
    period, run today (on a later day there are newer candles, so that run is a new one). None when something differs."""
    if not experiments:
        return None
    last = experiments[-1]
    if str(last.get("created_at") or "")[:10] != now[:10]:
        return None
    if _setup(last.get("strategy")) != _setup(strategy.model_dump()):
        return None
    if (last.get("instrument") or {}).get("id") != inst_id or last.get("days") != days:
        return None
    return last.get("v")


def period_name(days: int) -> str:
    """As the pages write a test period: "6 months", "1 year", "5 years", "45 days"."""
    if days >= 365 and days % 365 < 5:
        y = round(days / 365)
        return f"{y} year{'s' if days >= 730 else ''}"
    if days >= 28:
        m = round(days / 30.4)
        return f"{m} month{'' if m == 1 else 's'}"
    return f"{days} day{'' if days == 1 else 's'}"


TF_NAMES = {"1d": "daily", "1h": "1-hour", "15m": "15-minute", "5m": "5-minute"}
SIDES = {"long": "long only", "short": "short only", "both": "both ways"}
JOINS = {"all": "all rules", "any": "any rule", "score": "a score"}
RISK_LABELS = {"capital": "Capital", "riskPct": "Risk per trade", "maxAlloc": "Most in one trade", "sl": "Stop loss",
               "tgt": "Target", "brokerage": "Brokerage", "slippage": "Slippage", "trail": "Trailing stop",
               "maxBars": "Time exit", "sizing": "Sizing", "perTrade": "Per trade", "leverage": "Leverage"}
SYMBOLS = {"INR": "₹", "USD": "$", "EUR": "€", "GBP": "£", "JPY": "¥"}


def _amount(v, cur: str) -> str:
    from .email_kit import indian
    v = float(v or 0)
    dp = 0 if v.is_integer() else 2
    sym = SYMBOLS.get(cur or "INR", "")
    return f"{sym}{indian(v, dp)}" if (cur or "INR") == "INR" else f"{sym}{v:,.{dp}f}"


def _risk_text(key: str, v, cur: str, r: dict) -> str:
    if key in ("capital", "perTrade", "brokerage"):
        return _amount(v, cur)
    if key == "sl":
        kind = r.get("stopType")
        return ("off" if not v else f"{v:g} points" if kind == "points" else f"{v:g}× ATR" if kind == "atr"
                else f"{v:g}-candle swing" if kind == "swing" else f"{v:g}%")
    if key == "tgt":
        kind = r.get("tgtType")
        return "off" if not v else f"{v:g} points" if kind == "points" else f"{v:g}R" if kind == "r" else f"{v:g}%"
    if key == "trail":
        return "off" if not v else f"{v:g}%"
    if key == "maxBars":
        return "off" if not v else f"{v} candles"
    if key == "leverage":
        return f"{v:g}×"
    if key in ("riskPct", "maxAlloc", "slippage"):
        return f"{v:g}%"
    return str(v)


def _rule_changes(old: list | None, new: list | None, what: str) -> list[str]:
    from .engine.core import cond_text
    from .engine.indicators import ref_name
    from .models import Cond
    if (old or []) == (new or []):
        return []
    try:
        a, b = [Cond(**c) for c in old or []], [Cond(**c) for c in new or []]
    except Exception:
        return [f"{what} rules changed"]
    if len(a) != len(b):
        return [f"{what} rules: {len(a)} → {len(b)}"]
    out = []
    for x, y in zip(a, b):
        if x.model_dump() == y.model_dump():
            continue
        if x.op == y.op:
            out += [f"{ref_name(p)} → {ref_name(q)}" for p, q in ((x.l, y.l), (x.r, y.r)) if p.model_dump() != q.model_dump()]
        else:
            out.append(f"{cond_text(x)} → {cond_text(y)}")
    return out


def describe_change(prev: dict | None, rec: dict) -> str:
    """A short label for an experiment that says what differs from the one before: the instrument, the period, the
    candles, the rules and the money settings, in that order. The first experiment is "First run"."""
    if not prev:
        return "First run"
    bits: list[str] = []
    pi, ni = prev.get("instrument") or {}, rec.get("instrument") or {}
    if pi.get("id") != ni.get("id"):
        bits.append(f"{pi.get('symbol') or 'No market'} → {ni.get('symbol') or 'another market'}")
    if prev.get("days") and rec.get("days") and prev["days"] != rec["days"]:
        bits.append(f"{period_name(prev['days'])} → {period_name(rec['days'])}")
    ps, ns = prev.get("strategy") or {}, rec.get("strategy") or {}
    if ps.get("tf") != ns.get("tf"):
        bits.append(f"{TF_NAMES.get(ps.get('tf'), ps.get('tf'))} → {TF_NAMES.get(ns.get('tf'), ns.get('tf'))} candles")
    if ps.get("side") != ns.get("side"):
        bits.append(f"{SIDES.get(ps.get('side'), ps.get('side'))} → {SIDES.get(ns.get('side'), ns.get('side'))}")
    if ps.get("entryJoin") != ns.get("entryJoin") or ps.get("minScore") != ns.get("minScore"):
        bits.append(f"enter on {JOINS.get(ps.get('entryJoin'), 'all rules')} → {JOINS.get(ns.get('entryJoin'), 'all rules')}")
    for key, what in (("entry", "Entry"), ("exit", "Exit"), ("shortEntry", "Short entry"), ("shortExit", "Short exit")):
        bits += _rule_changes(ps.get(key), ns.get(key), what)
    pr, nr = ps.get("risk") or {}, ns.get("risk") or {}
    cur = ni.get("currency") or "INR"
    for key, label in RISK_LABELS.items():
        if key in nr and pr.get(key) != nr.get(key):
            bits.append(f"{label} {_risk_text(key, pr.get(key), cur, pr)} → {_risk_text(key, nr.get(key), cur, nr)}")
    if pr.get("stopType") != nr.get("stopType") and pr.get("sl") == nr.get("sl"):
        bits.append("Stop type changed")
    if pr.get("tgtType") != nr.get("tgtType") and pr.get("tgt") == nr.get("tgt"):
        bits.append("Target type changed")
    if ps.get("session") != ns.get("session"):
        bits.append("Session limits changed")
    if ps.get("product") != ns.get("product"):
        bits.append(f"Product: {ps.get('product')} → {ns.get('product')}")
    if not bits:
        return "Same setup, newer candles"
    text = "; ".join(bits)
    return text if len(text) <= 120 else text[:117].rsplit("; ", 1)[0] + " …"
