"""Which AI models to use, decided by measuring them, and what each one has done lately.

For every provider with a key: list its models, drop the ones that can't do the job (ai_catalog.unusable), ask each
of the rest two small fixed questions (a JSON-shaped answer, and a short English finance question) and keep the few
that answer correctly and fast. That is re-done every 6 hours, when the Admin page asks, and when a provider's models
stop working. Results are stored in app_settings ("ai:rank:<provider>"), so a restart doesn't start from nothing,
and the curated defaults in ai_catalog cover the very first start.

Every real request also counts: successes, failures and how long each took are kept per model, and a circuit
breaker per model and per provider skips whatever keeps failing, for longer each time. A rate limit skips the
provider (or just the model, where limits are per model) until the reset time the provider gave."""
import json
import os
import re
import statistics
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from .ai_catalog import PROVIDERS, TASKS, configured, model_setting, size_b, strength, thinks, unusable
from .ai_clients import CallError, client
from .ai_reply import BadReply, check, extract_json, remaining

RERANK_EVERY = 6 * 3600         # seconds between automatic re-ranks
IN_USE = 3                      # models kept per provider
HEAL_GAP = 30 * 60              # a provider whose models all stopped working is re-ranked at most this often
SAVE_GAP = 10 * 60              # live numbers are saved at most this often

# how much each second of waiting costs a model's score, and how much a model's size matters, per kind of job
LAT_W = {"quick": 6.0, "research": 2.0, "long": 1.0}
STRENGTH_W = {"quick": 2.0, "research": 8.0, "long": 10.0}


def _flag(name: str) -> bool:
    return os.environ.get(name, "1").strip().lower() not in ("0", "false", "no", "off")


AUTO = _flag("AI_AUTO_PROBE")   # background re-ranks and saving; the test suite turns it off (no network in tests)


# ---------- storage ----------
class DbStore:
    """app_settings through db.py. A storage problem means starting from the defaults (and reading again later)."""

    def get_all(self) -> dict | None:
        from . import db
        try:
            return dict(db.all_settings_with_prefix("ai:"))
        except Exception:  # noqa: BLE001  (no database configured, or it's down)
            return None

    def set(self, key: str, value: str) -> None:
        from . import db
        try:
            db.set_setting(key, value)
        except Exception:  # noqa: BLE001
            pass


class MemoryStore:
    def __init__(self):
        self.data: dict[str, str] = {}

    def get_all(self) -> dict:
        return dict(self.data)

    def set(self, key: str, value: str) -> None:
        self.data[key] = value


STORE = DbStore()


# ---------- state ----------
@dataclass
class ModelStats:
    provider: str
    model: str
    ctx: int | None = None
    probe_ok: int = 0
    probe_tries: int = 0
    probe_ms: list = field(default_factory=list)
    probe_json: int = 0
    probe_len: int = 0
    probe_at: float = 0.0
    probe_error: str | None = None
    live: deque = field(default_factory=lambda: deque(maxlen=30))     # (ok, ms) for recent real requests
    last_error: str | None = None
    last_error_at: float | None = None
    last_ok_at: float | None = None
    fails: int = 0               # failures in a row (circuit breaker)
    open_until: float = 0.0      # skipped until then
    open_reason: str | None = None

    def counts(self) -> tuple[int, int]:
        return self.probe_ok + sum(1 for ok, _ in self.live if ok), self.probe_tries + len(self.live)

    def median_ms(self) -> float | None:
        ms = list(self.probe_ms) + [m for ok, m in self.live if ok]
        return statistics.median(ms) if ms else None

    def dump(self) -> dict:
        return {"ctx": self.ctx, "probe_ok": self.probe_ok, "probe_tries": self.probe_tries, "probe_ms": self.probe_ms[-4:],
                "probe_json": self.probe_json, "probe_len": self.probe_len, "probe_at": self.probe_at,
                "probe_error": self.probe_error, "live": [[ok, round(ms)] for ok, ms in self.live],
                "last_error": self.last_error, "last_error_at": self.last_error_at, "last_ok_at": self.last_ok_at}

    @classmethod
    def load(cls, provider: str, model: str, d: dict) -> "ModelStats":
        s = cls(provider, model)
        for k in ("ctx", "probe_ok", "probe_tries", "probe_json", "probe_len", "probe_at", "probe_error", "last_error",
                  "last_error_at", "last_ok_at"):
            if k in d:
                setattr(s, k, d[k])
        s.probe_ms = [float(x) for x in d.get("probe_ms") or [] if isinstance(x, (int, float))]
        for item in d.get("live") or []:
            if isinstance(item, list) and len(item) == 2:
                s.live.append((bool(item[0]), float(item[1])))
        return s


@dataclass
class Status:
    name: str
    last_ok: float | None = None
    last_error: str | None = None
    last_error_at: float | None = None
    model: str | None = None             # the model that answered last
    cooldown_until: float = 0.0          # the provider is skipped until then (rate limit, bad key, repeated failures)
    cool_reason: str | None = None
    quota: bool = False                  # the free quota is used up for now (it resets on its own)
    quota_reset: float | None = None
    remaining: dict = field(default_factory=dict)   # what the provider said is left: requests, tokens, reset times
    fails: int = 0                       # provider-wide failures in a row
    config_error: bool = False           # the key was rejected
    models: dict = field(default_factory=dict)      # model id -> ModelStats
    order: list = field(default_factory=list)       # models in use, best first (empty until measured)
    ranked_at: float = 0.0
    rank_error: str | None = None
    discovered: int | None = None
    skipped: dict = field(default_factory=dict)     # why listed models were left out: reason -> count
    probing: bool = False
    healed_at: float = 0.0


class _Statuses(dict):
    """Status per provider. Clearing it (the tests do, between cases) forgets everything learnt."""

    def clear(self):
        super().clear()
        _prefs.update(pins={}, blocks=set(), loaded=False, retry_at=0)
        _saved.update(at=0.0, dirty=set())


_status: dict[str, Status] = _Statuses()
_prefs: dict = {"pins": {}, "blocks": set(), "loaded": False}
_saved: dict = {"at": 0.0, "dirty": set()}
_lock = threading.RLock()


def status(name: str) -> Status:
    with _lock:
        _ensure_loaded()
        return _status.setdefault(name, Status(name))


def stats(name: str, model: str) -> ModelStats:
    st = status(name)
    with _lock:
        return st.models.setdefault(model, ModelStats(name, model))


def _ensure_loaded():
    """Read what was learnt before the last restart, once (again a minute later if the database couldn't be read)."""
    if _prefs["loaded"] or time.time() < _prefs.get("retry_at", 0):
        return
    data = STORE.get_all()
    if data is None:
        _prefs["retry_at"] = time.time() + 60
        return
    _prefs["loaded"] = True
    try:
        prefs = json.loads(data.get("ai:prefs") or "{}")
        _prefs["pins"] = {k: v for k, v in (prefs.get("pins") or {}).items() if k in PROVIDERS and isinstance(v, str)}
        _prefs["blocks"] = {b for b in prefs.get("blocks") or [] if isinstance(b, str)}
    except (ValueError, AttributeError):
        pass
    for name in PROVIDERS:
        raw = data.get(f"ai:rank:{name}")
        if not raw:
            continue
        try:
            d = json.loads(raw)
            st = _status.setdefault(name, Status(name))
            st.ranked_at, st.rank_error = float(d.get("at") or 0), d.get("error")
            st.discovered, st.skipped = d.get("discovered"), d.get("skipped") or {}
            st.order = [m for m in d.get("order") or [] if isinstance(m, str)]
            for mid, md in (d.get("models") or {}).items():
                if isinstance(md, dict):
                    st.models[mid] = ModelStats.load(name, mid, md)
        except (ValueError, TypeError, AttributeError):
            continue


def save(name: str):
    st = status(name)
    with _lock:
        keep = set(st.order) | {m for m, s in st.models.items() if s.probe_tries or s.live}
        models = {m: st.models[m].dump() for m in list(keep)[:16] if m in st.models}
        value = json.dumps({"at": st.ranked_at, "error": st.rank_error, "discovered": st.discovered, "skipped": st.skipped,
                            "order": st.order, "models": models})
    STORE.set(f"ai:rank:{name}", value)


def save_prefs():
    with _lock:
        value = json.dumps({"pins": _prefs["pins"], "blocks": sorted(_prefs["blocks"])})
    STORE.set("ai:prefs", value)


def _save_soon(name: str):
    """Keep live numbers across restarts without a database write on every request."""
    _saved["dirty"].add(name)
    if not AUTO or time.time() - _saved["at"] < SAVE_GAP:
        return
    _saved["at"] = time.time()
    names, _saved["dirty"] = set(_saved["dirty"]), set()
    threading.Thread(target=lambda: [save(n) for n in names], daemon=True, name="ai-save").start()


# ---------- pins and blocks ----------
def _load():
    with _lock:
        _ensure_loaded()


def pins() -> dict:
    _load()
    return dict(_prefs["pins"])


def blocks() -> list[str]:
    _load()
    return sorted(_prefs["blocks"])


def blocked(name: str, model: str) -> bool:
    _load()
    return f"{name}/{model}" in _prefs["blocks"]


def pin(name: str, model: str | None):
    _load()
    with _lock:
        if model:
            _prefs["pins"][name] = model
            _prefs["blocks"].discard(f"{name}/{model}")
        else:
            _prefs["pins"].pop(name, None)
    save_prefs()


def block(name: str, model: str, on: bool = True):
    _load()
    with _lock:
        key = f"{name}/{model}"
        if on:
            _prefs["blocks"].add(key)
            if _prefs["pins"].get(name) == model:
                _prefs["pins"].pop(name)
        else:
            _prefs["blocks"].discard(key)
    save_prefs()


def pinned(name: str) -> str:
    """The model pinned on the Admin page, else in Railway (<NAME>_MODEL), else ""."""
    return pins().get(name) or model_setting(name)


# ---------- which models, in which order ----------
def in_use(name: str) -> list[str]:
    """The provider's models to try, best first: the pinned one alone, else the measured top few, else (before any
    measurement) the curated defaults. Blocked models never."""
    p = pinned(name)
    if p:
        return [p]
    st = status(name)
    order = [m for m in st.order if not blocked(name, m)]
    if order:
        return order[:IN_USE]
    return [m for m in PROVIDERS[name].defaults if not blocked(name, m)][:IN_USE]


def score(name: str, model: str, task: str) -> float:
    """Higher is tried first. Mostly the measured success rate, less the time it takes (which matters most for quick
    jobs); a model known to be strong gets a little more for research. Prototype-only providers come after every
    production-ready one, and the paid one last of all."""
    s, p = stats(name, model), PROVIDERS[name]
    ok, tries = s.counts()
    rate = (ok + 1) / (tries + 2)                                    # unmeasured models start at 50%
    med = s.median_ms()
    out = rate * 100 - (med if med is not None else 6000) / 1000 * LAT_W[task]
    if s.probe_tries:
        out -= (1 - s.probe_json / s.probe_tries) * 15 + (1 - s.probe_len / s.probe_tries) * 10
    out += strength(model) * STRENGTH_W[task]
    if p.terms == "prototype":
        out -= 60
    elif p.terms == "paid":
        out -= 300
    if p.tight_daily_tokens and task != "quick":
        out -= 12
    out -= p.prior[TASKS.index(task)] * (0.6 if not tries else 0.2)      # the old hand-made order, as a tie-break
    defaults = PROVIDERS[name].defaults
    if not tries and model in defaults:
        out -= defaults.index(model) * 2
    return round(out, 2)


def route(task: str, names: list[str], need_tokens: int = 0, fixed: bool = False) -> list[tuple[str, str]]:
    """(provider, model) pairs to try for this job, best first. With `fixed`, providers keep the given order (the
    AI_PROVIDERS setting) and only their models are sorted."""
    rows = []
    for name in names:
        for m in in_use(name):
            ctx = stats(name, m).ctx or PROVIDERS[name].ctx
            if need_tokens and ctx and need_tokens > ctx * 0.9:
                continue                                              # the document wouldn't fit
            rows.append((score(name, m, task), name, m))
    if fixed:
        rows.sort(key=lambda r: (names.index(r[1]), -r[0]))
    else:
        rows.sort(key=lambda r: -r[0])
    return [(n, m) for _, n, m in rows]


# ---------- circuit breakers ----------
def ready(name: str, model: str, now: float | None = None) -> float:
    """0 if this model can be asked now, else seconds until it can."""
    now = time.time() if now is None else now
    st, s = status(name), stats(name, model)
    return max(0.0, st.cooldown_until - now, s.open_until - now)


def _open_provider(st: Status, seconds: float, reason: str):
    st.cooldown_until = max(st.cooldown_until, time.time() + seconds)
    st.cool_reason = reason


def _open_model(s: ModelStats, seconds: float, reason: str):
    s.open_until = max(s.open_until, time.time() + seconds)
    s.open_reason = reason


def _backoff(fails: int, first: float, cap: float) -> float:
    return min(cap, first * 2 ** max(0, fails - 1))


def record_ok(name: str, model: str, ms: float, headers: dict | None = None, live: bool = True):
    st, s = status(name), stats(name, model)
    now = time.time()
    with _lock:
        if live:
            s.live.append((True, ms))
        # a good answer proves the model and the provider work: close their breakers
        s.fails, s.open_until, s.open_reason, s.last_ok_at = 0, 0.0, None, now
        st.fails, st.last_ok, st.model, st.config_error = 0, now, model, False
        st.cooldown_until, st.cool_reason, st.quota, st.quota_reset = 0.0, None, False, None
        left = remaining(headers or {})
        if left:
            st.remaining = {**left, "at": now}
            # quota awareness: when the provider says nothing is left, don't ask again until it resets
            scope_model = PROVIDERS[name].limit_scope == "model"
            for kind, low in (("requests", 0), ("tokens", 1500)):
                if kind in left and left[kind] <= low and left.get(f"{kind}_reset"):
                    wait = min(left[f"{kind}_reset"], 24 * 3600)
                    if scope_model:
                        _open_model(s, wait, f"no {kind} left until the reset")
                    else:
                        _open_provider(st, wait, f"no {kind} left until the reset")
                        st.quota, st.quota_reset = wait > 600, now + wait
    _save_soon(name)


def record_fail(name: str, model: str, err: Exception, live: bool = True) -> str:
    """Note a failure, open the right breaker, and return the text for the Admin page."""
    st, s = status(name), stats(name, model)
    now = time.time()
    kind = err.kind if isinstance(err, CallError) else "bad_reply"
    detail = err.detail if isinstance(err, CallError) else {
        "empty": f"empty reply ({model})", "not_json": f"reply wasn't the JSON asked for ({model})",
        "truncated": f"reply was cut off ({model})"}.get(getattr(err, "why", ""), f"unusable reply ({model})")
    with _lock:
        if kind == "context":
            return detail                                  # the wrong model for this prompt, not a fault
        if kind in ("rate", "credit"):
            wait = err.wait
            if kind == "credit":
                wait = wait or 6 * 3600
            elif wait is None:
                fails = (st.fails if err.scope == "provider" else s.fails) + 1
                wait = _backoff(fails, 30, 600)
            wait = min(max(wait, 2.0), 24 * 3600)
            if err.scope == "provider" or kind == "credit":
                st.fails += 1
                _open_provider(st, wait, detail)
                st.quota = err.daily or wait > 600
                st.quota_reset = now + wait
            else:
                s.fails += 1
                _open_model(s, wait, detail)
            st.last_error, st.last_error_at = detail, now
            return detail
        if live:
            s.live.append((False, 0.0))
        s.last_error, s.last_error_at, st.last_error, st.last_error_at = detail, now, detail, now
        if kind == "auth":
            st.config_error = True
            _open_provider(st, 30 * 60, detail)
        elif kind in ("model", "forbidden"):
            _open_model(s, 6 * 3600, detail)               # unknown, retired or not on this plan
        elif kind == "transient" and err.scope == "provider":
            st.fails += 1
            if st.fails >= 3:
                _open_provider(st, _backoff(st.fails - 2, 60, 900), detail)
        else:                                              # timeouts and unusable replies count against the model
            s.fails += 1
            if s.fails >= 2:
                _open_model(s, _backoff(s.fails - 1, 120, 6 * 3600), detail)
    _save_soon(name)
    return detail


# ---------- one request to one model ----------
def ask_model(name: str, model: str, system: str, text: str, max_tokens: int, want_json: bool, deadline: float,
              transport=None, live: bool = True) -> str:
    """Ask, check the reply, and record the outcome. An empty or cut-off reply gets one second chance with more
    room (and without JSON mode, which stops some reasoning models before they start). Raises CallError or BadReply."""
    c = client(name, transport)
    room, json_mode, t0 = max_tokens, want_json, time.time()
    for second in (False, True):
        try:
            reply = c.call(model, system, text, room, json_mode, deadline)
            out = check(reply.text, reply.finish, want_json)
        except BadReply as e:
            if not second and e.why in ("empty", "truncated") and deadline - time.time() > 4:
                json_mode = json_mode and e.why == "truncated"
                room = min(PROVIDERS[name].max_out, max(16000, room * 2))
                continue
            record_fail(name, model, e, live)
            raise
        except CallError as e:
            record_fail(name, model, e, live)
            raise
        record_ok(name, model, (time.time() - t0) * 1000, reply.headers, live)
        return out
    raise BadReply("empty")        # not reached


# ---------- measuring ----------
_FINANCE_WORDS = re.compile(r"\b(sales?|income|money|earn|earns|earned|sell|sells|selling|customers?|goods|services|revenue|business)\b", re.I)
_DEBT_WORDS = {"debt", "debts", "borrowings", "borrowing", "loans", "loan", "liabilities", "liability"}


def _english(s: str) -> bool:
    letters = [ch for ch in s if ch.isalpha()]
    return bool(letters) and sum(ch.isascii() for ch in letters) / len(letters) >= 0.95


def _check_sum(d: dict) -> bool:
    try:
        return d.get("ok") is True and float(d.get("sum")) == 42 and str(d.get("word", "")).strip().lower() == "blue"
    except (TypeError, ValueError):
        return False


def _check_finance(d: dict) -> bool:
    a = d.get("answer")
    return (isinstance(a, str) and _english(a) and bool(_FINANCE_WORDS.search(a))
            and str(d.get("term", "")).strip().strip(".").lower() in _DEBT_WORDS)


# The fixed test: a JSON shape with exact values, and a short English finance answer that keeps to the length asked
# ("short" says whether the reply kept to it).
PROBES = (
    {"system": 'Reply with ONLY a JSON object of exactly this shape: {"ok": true, "sum": <number>, "word": "<one word>"}. '
               '"sum" is 17 + 25. "word" is the colour of a clear daytime sky, in English, lower case.',
     "text": "Go.", "max_tokens": 200, "check": _check_sum, "short": lambda d, out: len(out) <= 200},
    {"system": "You explain finance terms to retail investors in plain English. Reply with ONLY a JSON object: "
               '{"answer": "<one short sentence, at most 25 words>", "term": "<one word>"}.',
     "text": 'What does a company\'s "revenue" mean? In "term", give the one-word name for the money a company owes '
             "to its lenders.", "max_tokens": 300, "check": _check_finance,
     "short": lambda d, out: len(str(d.get("answer", "")).split()) <= 40 and len(out) <= 600},
)


def probe(name: str, model: str, transport=None, per_call: float = 25.0) -> dict:
    """Ask one model the fixed test. Returns {"ok", "tries", "ms", "json", "length", "error", "stop"}; "stop" is set
    when the provider itself is unusable right now (bad key, quota), so the rest of its models aren't tried."""
    res = {"ok": 0, "tries": 0, "ms": [], "json": 0, "length": 0, "error": None, "stop": False}
    for t in PROBES:
        res["tries"] += 1
        t0 = time.time()
        try:
            out = ask_model(name, model, t["system"], t["text"], t["max_tokens"], True, time.time() + per_call, transport, live=False)
        except CallError as e:
            res["error"] = e.detail
            if e.scope == "provider" and e.kind in ("auth", "credit", "rate"):
                res["stop"] = True
                return res
            if e.kind in ("model", "forbidden", "rate"):
                return res                                  # nothing more to learn from this model now
            continue
        except BadReply as e:
            res["error"] = {"empty": "empty reply", "not_json": "reply wasn't JSON", "truncated": "reply was cut off"}.get(e.why, e.why)
            continue
        ms = (time.time() - t0) * 1000
        try:
            data = extract_json(out)
        except Exception:  # noqa: BLE001
            res["error"] = "reply wasn't JSON"
            continue
        res["json"] += 1
        res["length"] += bool(t["short"](data, out))
        if t["check"](data):
            res["ok"] += 1
            res["ms"].append(ms)
        else:
            res["error"] = "wrong answer to the test question"
    return res


def candidates(name: str, listed: list[dict] | None) -> tuple[list[str], dict, dict]:
    """(models to measure, why the others were left out, context sizes). The curated defaults the provider still
    lists come first, then the other usable models, larger and non-reasoning ones first."""
    p = PROVIDERS[name]
    skipped: dict[str, int] = {}
    ctx: dict[str, int] = {}
    if listed is None:
        ids = list(p.defaults)
    else:
        ids = []
        for item in listed:
            why = unusable(name, item["id"])
            if why:
                skipped[why] = skipped.get(why, 0) + 1
                continue
            ids.append(item["id"])
            if item.get("ctx"):
                ctx[item["id"]] = item["ctx"]
    ids = [m for m in dict.fromkeys(ids) if not blocked(name, m)]
    known = [m for m in p.defaults if m in ids]
    rest = sorted((m for m in ids if m not in known), key=lambda m: (-strength(m), thinks(m), -(size_b(m) or 30), m))
    return (known + rest)[:p.probe_max], skipped, ctx


def rerank(name: str, transport=None) -> Status:
    """Measure the provider's models now and keep the best few. Runs for up to a few minutes."""
    st = status(name)
    if not configured(name):
        return st
    with _lock:
        if st.probing:
            return st
        st.probing = True
    try:
        listed, st.rank_error = None, None
        if PROVIDERS[name].models_url:
            try:
                listed = client(name, transport).models(time.time() + 20)
            except CallError as e:
                if e.kind == "auth":
                    with _lock:
                        st.config_error, st.last_error, st.rank_error, st.last_error_at = True, e.detail, e.detail, time.time()
                        _open_provider(st, 30 * 60, e.detail)
                    return st
                st.rank_error = f"couldn't list models, measured the defaults ({e.detail})"
        p = pinned(name)
        cands, skipped, ctx = candidates(name, listed)
        if p and p not in cands:
            cands = [p] + cands[:PROVIDERS[name].probe_max - 1]
        st.discovered, st.skipped = (len(listed) if listed is not None else None), skipped
        for m in cands:
            s = stats(name, m)
            s.ctx = ctx.get(m) or s.ctx
            res = probe(name, m, transport)
            with _lock:
                s.probe_ok, s.probe_tries, s.probe_ms = res["ok"], res["tries"], res["ms"]
                s.probe_json, s.probe_len, s.probe_at, s.probe_error = res["json"], res["length"], time.time(), res["error"]
            if res["stop"]:
                st.rank_error = f"stopped measuring: {res['error']}"
                for later in cands[cands.index(m) + 1:]:
                    stats(name, later).probe_error = "not measured (provider unavailable)"
                break
        good = [m for m in cands if stats(name, m).probe_ok > 0]
        neutral = lambda m: (score(name, m, "quick") + score(name, m, "research")) / 2   # noqa: E731
        with _lock:
            if good:
                st.order = sorted(good, key=neutral, reverse=True)[:IN_USE]
            elif not st.order:
                st.order = []                               # nothing proven: the defaults stay in use
            st.ranked_at = time.time()
        save(name)
        return st
    finally:
        st.probing = False


def rerank_many(names: list[str], transport=None, workers: int = 4):
    names = [n for n in names if configured(n)]
    if not names:
        return
    with ThreadPoolExecutor(max_workers=min(workers, len(names))) as ex:
        list(ex.map(lambda n: rerank(n, transport), names))


def start_rerank(names: list[str], transport=None) -> list[str]:
    """Re-rank in the background; returns the providers being measured."""
    names = [n for n in names if configured(n) and not status(n).probing]
    if names:
        threading.Thread(target=rerank_many, args=(names, transport), daemon=True, name="ai-rerank").start()
    return names


def heal(name: str):
    """Every model in use failed in a way that says it's gone (retired, renamed, not on this plan): measure again
    soon, at most every half hour."""
    st = status(name)
    if AUTO and time.time() - st.healed_at > HEAL_GAP:
        st.healed_at = time.time()
        start_rerank([name])


def stale(name: str) -> bool:
    """Due for its automatic re-rank (every 6 hours; less often where measuring costs scarce credit; never for the
    paid provider, which is measured only when the Admin page asks)."""
    every = PROVIDERS[name].probe_every_h * 3600
    return configured(name) and every > 0 and time.time() - status(name).ranked_at > every


class RerankJob:
    """Re-ranks every provider with a key every 6 hours (checked every 10 minutes), starting shortly after boot."""

    def __init__(self, first_wait: float = 90, every: float = 600):
        self.first_wait, self.every, self.started = first_wait, every, False

    def start(self):
        if self.started or not AUTO:
            return
        self.started = True
        threading.Thread(target=self.loop, daemon=True, name="ai-rerank-job").start()

    def loop(self):
        time.sleep(self.first_wait)
        while True:
            try:
                rerank_many([n for n in PROVIDERS if stale(n)])
            except Exception:  # noqa: BLE001  (a bug here must not end the loop)
                pass
            time.sleep(self.every)
