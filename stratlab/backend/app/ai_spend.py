"""What Claude costs this calendar month (UTC), and which Claude model a job may use while the monthly credit lasts.

Owner, 4 Nov: the account gets $100 of Anthropic credit a month; use it where quality shows and never spend past it.
So every Claude reply's `usage` is priced here (input, output, cache writes at 1.25x input, cache reads at 0.1x
input), added to this month's total, and saved in app_settings ("ai:spend:YYYY-MM", one small row a month), so a
restart doesn't forget what was spent. Before each request the dearest it could cost is reserved, and the request
isn't sent if that could take the month past the cap. Every figure is rounded up, so the meter never under-counts.

Routing (ai_providers.plan): research reads and long documents ask Claude Sonnet 5.5 first while the month's spend is
under ANTHROPIC_SONNET_UNTIL_USD, then Claude Haiku 5.5 until ANTHROPIC_MONTHLY_CAP_USD; quick jobs ask Haiku after the
free providers named in AI_QUICK_BEFORE_CLAUDE. At the cap Claude is skipped entirely until the month turns."""
import json
import math
import threading
import time
from datetime import datetime, timezone
from decimal import Decimal

from .config import settings

SONNET = "claude-sonnet-5-5"
HAIKU = "claude-haiku-5-5"

# US dollars per million tokens: (input, output) for prompts up to LONG_PROMPT tokens, and above it (None: same price)
PRICES: dict[str, tuple[tuple[str, str], tuple[str, str] | None]] = {
    HAIKU: (("0.10", "0.50"), ("0.50", "2.50")),
    SONNET: (("2", "10"), None),
    "claude-sonnet-5": (("2", "10"), None),
    "claude-opus-5-5": (("4", "20"), None),
    "claude-opus-5": (("5", "25"), None),
}
UNKNOWN_PRICE = ("10", "50")        # a pinned model this table doesn't know: counted at the dearest current price
LONG_PROMPT = 100_000
CACHE_WRITE, CACHE_READ = Decimal("1.25"), Decimal("0.1")
CHARS_PER_TOKEN_LOW = 2.0           # for the reservation: fewer characters per token than any real text, so more tokens

_lock = threading.RLock()
_write_lock = threading.Lock()
_state: dict = {"month": None, "data": None, "store": None, "retry_at": 0.0, "pending": {}, "next": 0}


def _store():
    from . import ai_rank
    return ai_rank.STORE


def month(now: float | None = None) -> str:
    return datetime.fromtimestamp(time.time() if now is None else now, timezone.utc).strftime("%Y-%m")


def month_end(now: float | None = None) -> float:
    """When this calendar month (UTC) ends, as a timestamp."""
    d = datetime.fromtimestamp(time.time() if now is None else now, timezone.utc)
    nxt = datetime(d.year + (d.month == 12), d.month % 12 + 1, 1, tzinfo=timezone.utc)
    return nxt.timestamp()


def cap_usd() -> float:
    return float(getattr(settings, "ANTHROPIC_MONTHLY_CAP_USD", 99) or 0)


def sonnet_until_usd() -> float:
    return float(getattr(settings, "ANTHROPIC_SONNET_UNTIL_USD", 75) or 0)


def _price(model: str, prompt_tokens: int) -> tuple[Decimal, Decimal]:
    base, long = PRICES.get(model, (UNKNOWN_PRICE, None))
    pin, pout = long if (long and prompt_tokens > LONG_PROMPT) else base
    return Decimal(pin), Decimal(pout)


def _n(usage: dict, key: str) -> int:
    v = (usage or {}).get(key)
    return int(v) if isinstance(v, (int, float)) and v > 0 else 0


def cost_micros(model: str, usage: dict) -> int:
    """What one reply cost, in millionths of a dollar, rounded up."""
    inp, out = _n(usage, "input_tokens"), _n(usage, "output_tokens")
    cw, cr = _n(usage, "cache_creation_input_tokens"), _n(usage, "cache_read_input_tokens")
    pin, pout = _price(model, inp + cw + cr)
    # tokens x dollars per million tokens = millionths of a dollar
    return math.ceil(inp * pin + cw * pin * CACHE_WRITE + cr * pin * CACHE_READ + out * pout)


def estimate_micros(model: str, prompt_chars: int, max_out: int) -> int:
    """The most a request can cost: every prompt token written to the cache (the dearest way to send it), counted
    generously from its length, and every reply token the request allows."""
    prompt = math.ceil(prompt_chars / CHARS_PER_TOKEN_LOW) + 50
    return cost_micros(model, {"cache_creation_input_tokens": prompt, "output_tokens": max_out})


def _empty(m: str) -> dict:
    return {"month": m, "micros": 0, "requests": 0, "input": 0, "output": 0, "cache_write": 0, "cache_read": 0,
            "refusals": 0, "models": {}}


def _current() -> dict | None:
    """This month's totals, read once from the store (again after a month turns or the store changes). None while the
    store can't be read: then nobody knows what was spent, so Claude isn't asked (never past the cap)."""
    m, store = month(), _store()
    with _lock:
        if _state["month"] == m and _state["store"] is store and _state["data"] is not None:
            return _state["data"]
        if _state["store"] is store and _state["month"] == m and time.time() < _state["retry_at"]:
            return None
        try:
            raw = store.get(f"ai:spend:{m}")
        except Exception:  # noqa: BLE001  (database down: try again in a minute)
            _state.update(month=m, store=store, data=None, retry_at=time.time() + 60)
            return None
        data = _empty(m)
        try:
            saved = json.loads(raw) if raw else {}
            for k in ("micros", "requests", "input", "output", "cache_write", "cache_read", "refusals"):
                if isinstance(saved.get(k), int) and saved[k] >= 0:
                    data[k] = saved[k]
            data["models"] = {str(k): {"micros": int(v.get("micros") or 0), "requests": int(v.get("requests") or 0)}
                              for k, v in (saved.get("models") or {}).items() if isinstance(v, dict)}
        except (ValueError, TypeError, AttributeError):
            pass
        _state.update(month=m, store=store, data=data, retry_at=0.0)
        return data


def spent_usd() -> float | None:
    data = _current()
    return None if data is None else data["micros"] / 1e6


def reserve(est_micros: int) -> int | None:
    """Hold back the most a request can cost. None when that could take this month past the cap (or the month's
    spend can't be read): then the request mustn't be sent."""
    data = _current()
    if data is None:
        return None
    with _lock:
        held = sum(_state["pending"].values())
        if data["micros"] + held + est_micros > cap_usd() * 1e6:
            return None
        _state["next"] += 1
        _state["pending"][_state["next"]] = est_micros
        return _state["next"]


def release(token: int | None):
    with _lock:
        _state["pending"].pop(token, None)


def record(model: str, usage: dict | None, refusal: bool = False) -> int:
    """Add one billed reply to this month's total and save it. Returns what it cost (millionths of a dollar)."""
    micros = cost_micros(model, usage or {})
    data = _current()
    if data is None:
        data = _empty(month())          # the store couldn't be read: still count it in memory until it can
        with _lock:
            _state.update(month=data["month"], store=_store(), data=data, retry_at=time.time() + 60)
    with _write_lock:
        with _lock:
            data["micros"] += micros
            data["requests"] += 1
            data["input"] += _n(usage, "input_tokens")
            data["output"] += _n(usage, "output_tokens")
            data["cache_write"] += _n(usage, "cache_creation_input_tokens")
            data["cache_read"] += _n(usage, "cache_read_input_tokens")
            data["refusals"] += bool(refusal)
            per = data["models"].setdefault(model, {"micros": 0, "requests": 0})
            per["micros"] += micros
            per["requests"] += 1
            snap = json.dumps(data)
        try:
            _store().set(f"ai:spend:{data['month']}", snap)     # under the write lock: the newest total lands last
        except Exception:  # noqa: BLE001
            pass
    return micros


def claude_models(task: str, pinned: str = "", bulk: bool = False) -> list[str]:
    """The Claude models this job may ask now, best first; [] once this month's spend reached the cap (or can't be
    read). A model pinned in Railway (ANTHROPIC_MODEL) or on the Admin page is used alone, still under the cap.
    `bulk`: a background or batch job (the daily filing reader, the IPO catch-up, the newsletter) asks Haiku only, so
    the Sonnet share goes to the reads a person is waiting for (owner, 4 Nov)."""
    spent = spent_usd()
    if spent is None or spent >= cap_usd():
        return []
    if pinned:
        return [pinned]
    if task == "quick" or bulk:
        return [HAIKU]
    return [SONNET, HAIKU] if spent < sonnet_until_usd() else [HAIKU]


def view() -> dict:
    """This month's Claude spend, for the Admin page."""
    data = _current()
    cap, until = cap_usd(), sonnet_until_usd()
    if data is None:
        return {"month": month(), "known": False, "usd": None, "cap_usd": cap, "sonnet_until_usd": until}
    prompt = data["input"] + data["cache_write"] + data["cache_read"]
    usd = data["micros"] / 1e6
    return {"month": data["month"], "known": True, "usd": round(usd, 4), "cap_usd": cap, "sonnet_until_usd": until,
            "requests": data["requests"], "input_tokens": data["input"], "output_tokens": data["output"],
            "cache_write_tokens": data["cache_write"], "cache_read_tokens": data["cache_read"],
            "cache_hit_share": round(data["cache_read"] / prompt, 3) if prompt else None, "refusals": data["refusals"],
            "models": {k: {"usd": round(v["micros"] / 1e6, 4), "requests": v["requests"]} for k, v in data["models"].items()},
            "tier": "off" if usd >= cap else "sonnet" if usd < until else "haiku", "resets_at": month_end()}


def reset():
    """Forget the month read and any reservations (tests)."""
    with _lock:
        _state.update(month=None, data=None, store=None, retry_at=0.0, pending={}, next=0)
