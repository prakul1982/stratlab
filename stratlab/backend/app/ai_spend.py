"""What Claude costs this calendar month (UTC), and which Claude model a job may use while the monthly credit lasts.

Owner, 4 Nov: the account gets $100 of Anthropic credit a month; use it where quality shows and never spend past it.
So every Claude reply's `usage` is priced here (input, output, cache writes at 1.25x input, cache reads at 0.1x
input), added to this month's total, and saved in app_settings ("ai:spend:YYYY-MM", one small row a month), so a
restart doesn't forget what was spent. Before each request the dearest it could cost is reserved, and the request
isn't sent if that could take the month past the cap. Every figure is rounded up, so the meter never under-counts.

Routing (ai_providers.plan): research reads and long documents ask Claude Sonnet 5.5 first while the month's spend is
under ANTHROPIC_SONNET_UNTIL_USD, then Claude Haiku 5.5 until ANTHROPIC_MONTHLY_CAP_USD; quick jobs ask Haiku after the
free providers named in AI_QUICK_BEFORE_CLAUDE. At the cap Claude is skipped entirely until the month turns.

A second key (owner, 12 Nov): ANTHROPIC_API_KEY_2 has its own $100 of credit a month. While it is set and not spent it is
asked first, for every Claude request, with its own meter ("ai:spend2:YYYY-MM") and its own limit ANTHROPIC_2_CREDIT_USD
(default 100); research reads and long documents may use Sonnet for its whole credit (background jobs still Haiku only).
It is spent for the month once its meter reaches that limit (less than KEY2_LAST_USD left), or when the API answers it with used-up credit, a billing
problem or a rejected key; then requests go to ANTHROPIC_API_KEY under the rules above. Its spend never counts toward the
first key's cap or Sonnet/Haiku tier. The record keeps a short hash of the key (never the key), so a new key value starts
afresh; the month turning starts both keys afresh. Without ANTHROPIC_API_KEY_2 nothing here changes."""
import hashlib
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

KEY1_ENV, KEY2_ENV = "ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY_2"

_lock = threading.RLock()
_write_lock = threading.Lock()
_state: dict = {"month": None, "data": None, "store": None, "retry_at": 0.0, "pending": {}, "next": 0}     # the first key
_state2: dict = {"month": None, "data": None, "store": None, "retry_at": 0.0, "pending": {}, "sig": None}  # the second key


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


def credit2_usd() -> float:
    """What the second key may spend a month (its free credit)."""
    return float(getattr(settings, "ANTHROPIC_2_CREDIT_USD", 100) or 0)


# Every request is held back at the most it could cost, so the meter itself stops just short of the credit: with less than
# this left the second key counts as spent (no request is refused on it again and again while the first key waits)
KEY2_LAST_USD = 0.5


def _key2_done(data: dict) -> bool:
    return bool(data.get("spent")) or data["micros"] >= (credit2_usd() - KEY2_LAST_USD) * 1e6


def key1() -> str:
    return (getattr(settings, KEY1_ENV, "") or "").strip()


def key2() -> str:
    return (getattr(settings, KEY2_ENV, "") or "").strip()


def _sig(key: str) -> str:
    """A short one-way hash of a key: tells a new key value from the old one in the saved record. Never the key itself."""
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def fingerprint(key: str) -> str | None:
    """How Admin names a key: its last four characters at most, nothing more."""
    if not key:
        return None
    return "…" + key[-4:] if len(key) >= 12 else "set"


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


def _load(st: dict, prefix: str, sig: str | None = None) -> dict | None:
    """One key's totals this month, read once from the store (again after a month turns, the store changes or, for the
    second key, its value changes). None while the store can't be read."""
    m, store = month(), _store()
    with _lock:
        same = st["month"] == m and st["store"] is store and st.get("sig") == sig
        if same and st["data"] is not None:
            return st["data"]
        if same and time.time() < st["retry_at"]:
            return None
        try:
            raw = store.get(f"{prefix}:{m}")
        except Exception:  # noqa: BLE001  (database down: try again in a minute)
            st.update(month=m, store=store, data=None, retry_at=time.time() + 60)
            if sig is not None:
                st["sig"] = sig
            return None
        data = _empty(m) if sig is None else _empty2(m, sig)
        try:
            saved = json.loads(raw) if raw else {}
            if sig is not None and saved.get("key") != sig:
                saved = {}                      # a new key value: its own credit, counted from nothing
            for k in ("micros", "requests", "input", "output", "cache_write", "cache_read", "refusals"):
                if isinstance(saved.get(k), int) and saved[k] >= 0:
                    data[k] = saved[k]
            data["models"] = {str(k): {"micros": int(v.get("micros") or 0), "requests": int(v.get("requests") or 0)}
                              for k, v in (saved.get("models") or {}).items() if isinstance(v, dict)}
            if sig is not None and isinstance(saved.get("spent"), dict):
                data["spent"] = {"why": str(saved["spent"].get("why") or "")[:300], "at": float(saved["spent"].get("at") or 0)}
        except (ValueError, TypeError, AttributeError):
            pass
        st.update(month=m, store=store, data=data, retry_at=0.0)
        if sig is not None:
            st["sig"] = sig
        return data


def _empty2(m: str, sig: str) -> dict:
    return {**_empty(m), "key": sig, "spent": None}


def _current() -> dict | None:
    """The first key's totals this month. None while the store can't be read: then nobody knows what was spent, so
    Claude isn't asked (never past the cap)."""
    return _load(_state, "ai:spend")


def _current2() -> dict | None:
    """The second key's totals this month; None without a second key or while the store can't be read."""
    k = key2()
    return _load(_state2, "ai:spend2", _sig(k)) if k else None


def spent_usd() -> float | None:
    data = _current()
    return None if data is None else data["micros"] / 1e6


def key2_active() -> bool:
    """The second key is set, its month can be read, and it isn't spent: it is asked first."""
    data = _current2()
    return bool(data is not None and not _key2_done(data))


def reserve(est_micros: int, key: int = 1) -> int | None:
    """Hold back the most a request can cost on this key. None when that could take this month past the key's limit
    (the cap for the first key, its credit for the second; or the month's spend can't be read, or the second key is
    spent): then the request mustn't be sent with it."""
    if key == 2:
        data, st, limit = _current2(), _state2, credit2_usd()
        if data is None or data.get("spent"):
            return None
    else:
        data, st, limit = _current(), _state, cap_usd()
        if data is None:
            return None
    with _lock:
        held = sum(st["pending"].values())
        if data["micros"] + held + est_micros > limit * 1e6:
            return None
        _state["next"] += 1
        st["pending"][_state["next"]] = est_micros
        return _state["next"]


def release(token: int | None):
    with _lock:
        _state["pending"].pop(token, None)
        _state2["pending"].pop(token, None)


def _save(prefix: str, data: dict):
    snap = json.dumps(data)
    try:
        _store().set(f"{prefix}:{data['month']}", snap)     # under the write lock: the newest total lands last
    except Exception:  # noqa: BLE001
        pass


def record(model: str, usage: dict | None, refusal: bool = False, key: int = 1) -> int:
    """Add one billed reply to this month's total for the key that sent it, and save it. Returns what it cost
    (millionths of a dollar)."""
    micros = cost_micros(model, usage or {})
    if key == 2:
        data, st, prefix = _current2(), _state2, "ai:spend2"
        if data is None:
            k = key2()
            data = _empty2(month(), _sig(k) if k else "")
            with _lock:
                st.update(month=data["month"], store=_store(), data=data, retry_at=time.time() + 60, sig=data["key"])
    else:
        data, st, prefix = _current(), _state, "ai:spend"
        if data is None:
            data = _empty(month())          # the store couldn't be read: still count it in memory until it can
            with _lock:
                st.update(month=data["month"], store=_store(), data=data, retry_at=time.time() + 60)
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
            if key == 2 and _key2_done(data) and not data.get("spent"):
                data["spent"] = {"why": f"its ${credit2_usd():.0f} credit for this month is spent", "at": time.time()}
            snap = dict(data)
        _save(prefix, snap)
    return micros


def mark_spent(why: str):
    """The API said the second key can't be used (credit used up, a billing problem, a rejected key): it is spent until
    the month turns or the key value changes, and the first key answers. `why` must already have any key taken out."""
    k = key2()
    if not k:
        return
    data = _current2()
    with _write_lock:
        with _lock:
            if data is None:
                data = _empty2(month(), _sig(k))
                _state2.update(month=data["month"], store=_store(), data=data, retry_at=time.time() + 60, sig=data["key"])
            data["spent"] = {"why": str(why or "the API refused it")[:300], "at": time.time()}
            snap = dict(data)
        _save("ai:spend2", snap)


def key1_allows(model: str, pinned: str = "") -> bool:
    """Whether the first key's Sonnet/Haiku tier this month lets this model be asked (its cap is reserve()'s to check):
    a request planned on the second key's budget falls back to the first only where the first key's own rules allow."""
    if model == pinned or model != SONNET:
        return True
    s = spent_usd()
    return s is not None and s < sonnet_until_usd()


def claude_models(task: str, pinned: str = "", bulk: bool = False) -> list[str]:
    """The Claude models this job may ask now, best first; [] once this month's spend reached the cap (or can't be
    read). A model pinned in Railway (ANTHROPIC_MODEL) or on the Admin page is used alone, still under the cap. While the
    second key is active its credit decides instead (Sonnet first for research and long, whatever the first key spent).
    `bulk`: a background or batch job (the daily filing reader, the IPO catch-up, the newsletter) asks Haiku only, so
    the Sonnet share goes to the reads a person is waiting for (owner, 4 Nov)."""
    if key2_active():
        # the second key's own credit: Sonnet for research reads and long documents until it is spent (owner, 12 Nov)
        if pinned:
            return [pinned]
        return [HAIKU] if task == "quick" or bulk else [SONNET, HAIKU]
    if key2() and not key1():
        return []                       # the second key is spent (or unreadable) and there is no first key
    spent = spent_usd()
    if spent is None or spent >= cap_usd():
        return []
    if pinned:
        return [pinned]
    if task == "quick" or bulk:
        return [HAIKU]
    return [SONNET, HAIKU] if spent < sonnet_until_usd() else [HAIKU]


def _usd(micros: int) -> float:
    return round(micros / 1e6, 4)


def keys_view() -> list[dict]:
    """Both keys side by side for Admin: set or not, the last four characters at most, this month's spend against its
    limit, and which one answers now. No key value ever."""
    k1, k2 = key1(), key2()
    d1, d2 = _current(), _current2()
    two = key2_active()
    cap = cap_usd()
    if not k1:
        s1, t1 = "off", "Not set."
    elif d1 is None:
        s1, t1 = "unknown", "This month's spend can't be read right now."
    elif d1["micros"] >= cap * 1e6:
        s1, t1 = "spent", f"Reached its ${cap:.0f} cap: skipped until the month turns."
    elif two:
        s1, t1 = "standby", "Waiting: the second key answers until its credit is spent."
    else:
        s1, t1 = "active", "Answering Claude requests."
    one = {"slot": 1, "variable": KEY1_ENV, "configured": bool(k1), "fingerprint": fingerprint(k1),
           "usd": None if d1 is None else _usd(d1["micros"]), "credit_usd": cap,
           "requests": None if d1 is None else d1["requests"], "state": s1, "state_text": t1}
    credit = credit2_usd()
    if not k2:
        s2, t2 = "off", "Not set."
    elif d2 is None:
        s2, t2 = "unknown", "This month's spend can't be read right now, so it isn't asked until it can."
    elif _key2_done(d2):
        why = (d2.get("spent") or {}).get("why") or f"its ${credit:.0f} credit for this month is spent"
        s2, t2 = "spent", f"Spent for this month ({why}); the first key answers until the month turns."
    else:
        s2, t2 = "active", "Answering Claude requests first, Sonnet for research and long documents, until its credit is spent."
    spent2 = (d2 or {}).get("spent") or None
    two_row = {"slot": 2, "variable": KEY2_ENV, "configured": bool(k2), "fingerprint": fingerprint(k2),
               "usd": None if d2 is None else _usd(d2["micros"]), "credit_usd": credit,
               "requests": None if d2 is None else d2["requests"], "state": s2, "state_text": t2,
               "spent_reason": spent2["why"] if spent2 else None, "spent_at": spent2["at"] if spent2 else None,
               "models": {} if d2 is None else {m: {"usd": _usd(v["micros"]), "requests": v["requests"]} for m, v in d2["models"].items()}}
    return [one, two_row]


def view() -> dict:
    """This month's Claude spend, for the Admin page: the first key's meter (as before), and both keys side by side."""
    data = _current()
    cap, until = cap_usd(), sonnet_until_usd()
    keys = keys_view()
    active = next((k["slot"] for k in keys if k["state"] == "active"), None)
    on = [k for k in keys if k["configured"]]
    extra = {"keys": keys, "active_key": active,
             "budget_usd": round(sum(k["credit_usd"] for k in on), 2) if on else cap,
             "budget_spent_usd": None if any(k["usd"] is None for k in on) else round(sum(k["usd"] for k in on), 4)}
    if data is None:
        return {"month": month(), "known": False, "usd": None, "cap_usd": cap, "sonnet_until_usd": until, **extra}
    prompt = data["input"] + data["cache_write"] + data["cache_read"]
    usd = data["micros"] / 1e6
    return {"month": data["month"], "known": True, "usd": round(usd, 4), "cap_usd": cap, "sonnet_until_usd": until,
            "requests": data["requests"], "input_tokens": data["input"], "output_tokens": data["output"],
            "cache_write_tokens": data["cache_write"], "cache_read_tokens": data["cache_read"],
            "cache_hit_share": round(data["cache_read"] / prompt, 3) if prompt else None, "refusals": data["refusals"],
            "models": {k: {"usd": round(v["micros"] / 1e6, 4), "requests": v["requests"]} for k, v in data["models"].items()},
            "tier": "off" if usd >= cap else "sonnet" if usd < until else "haiku", "resets_at": month_end(), **extra}


def reset():
    """Forget the month read and any reservations (tests)."""
    with _lock:
        _state.update(month=None, data=None, store=None, retry_at=0.0, pending={}, next=0)
        _state2.update(month=None, data=None, store=None, retry_at=0.0, pending={}, sig=None)
