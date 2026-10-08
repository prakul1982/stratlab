"""The AI layer every feature uses: ask a question, get a checked JSON answer from whichever free model can give one.

How a request is answered:
1. The same question for the same job within a few hours is answered from the cache (no quota spent).
2. The models to ask come from measurement (ai_rank.py), best first for this kind of job: quick jobs (the idea
   builder, the ask bar) favour fast models; research reads and long documents favour strong ones, and skip models
   whose context window the document wouldn't fit.
3. Each reply is checked: not empty, not cut off, and holding a JSON object. A bad reply moves straight on to the
   next model; a provider that's down, out of quota or has a bad key is skipped for the rest of the request (and
   for as long as its rate limit lasts).
4. The whole request has a time budget per job, so nobody waits more than about BUDGET seconds.

Providers and models are described in ai_catalog.py, requests are sent by ai_clients.py. Error texts never name a
provider (users may see them); the details are on the Admin page."""
import hashlib
import json
import threading
import time
from collections import OrderedDict

from .ai_catalog import PROVIDERS, TASK_LABELS, TASKS, configured, missing, model_setting, thinks
from .ai_clients import CallError
from .ai_reply import (AIBusy, AIConfig, AIError, BadReply, RateLimited, check, extract_json, salvage_items)  # noqa: F401
from .ai_reply import answer as _message_answer
from . import ai_rank as R
from .ai_rank import _status, status  # noqa: F401  (status: the provider state other modules read)
from .config import settings

LABELS = {n: p.label for n, p in PROVIDERS.items()}
DEFAULT_ORDER = sorted(PROVIDERS, key=lambda n: PROVIDERS[n].prior[0])

BUDGET = {"quick": 30.0, "research": 60.0, "long": 120.0}       # seconds a whole request may take, at most
PER_CALL = {"quick": 18.0, "research": 40.0, "long": 80.0}      # seconds one model may take
MAX_TRIES = 8                                                   # models asked per request, at most
WAIT_FOR_COOLDOWN = 10.0        # when every model is briefly rate limited, wait this long at most for the first
CACHE_TTL = {"quick": 6 * 3600, "research": 3600, "long": 12 * 3600}
CACHE_MAX = 400


def _answer(choice: dict) -> str:
    """The answer text in an OpenAI-style choice (kept for callers of the old helper)."""
    return _message_answer((choice or {}).get("message") or {})


# ---------- the answer cache ----------
class AnswerCache:
    """Identical questions for the same job, answered once per TTL. Only checked answers are kept."""

    def __init__(self, max_items: int = CACHE_MAX):
        self.max, self.items, self.hits, self.misses = max_items, OrderedDict(), 0, 0
        self.lock = threading.Lock()

    @staticmethod
    def key(task: str, system: str, text: str, max_tokens: int, want_json: bool) -> str:
        raw = json.dumps([task, system, text, max_tokens, want_json], ensure_ascii=False)
        return hashlib.sha256(raw.encode()).hexdigest()

    def get(self, key: str) -> str | None:
        with self.lock:
            hit = self.items.get(key)
            if hit and hit[0] > time.time():
                self.items.move_to_end(key)
                self.hits += 1
                return hit[1]
            self.items.pop(key, None)
            self.misses += 1
            return None

    def set(self, key: str, value: str, ttl: float):
        with self.lock:
            self.items[key] = (time.time() + ttl, value)
            self.items.move_to_end(key)
            while len(self.items) > self.max:
                self.items.popitem(last=False)

    def clear(self):
        with self.lock:
            self.items.clear()
            self.hits = self.misses = 0


cache = AnswerCache()
last_failure: dict = {}


def reset():
    """Forget everything learnt and cached (tests)."""
    _status.clear()
    cache.clear()
    last_failure.clear()


# ---------- which providers ----------
def _names(task: str) -> tuple[list[str], bool]:
    """Providers with a key for this job, and whether their order is fixed by a setting. AI_PROVIDERS (and
    AI_PROVIDERS_RESEARCH for research and long reads) can name an order; "auto" lets measurement decide."""
    raw = (settings.AI_PROVIDERS or "auto").strip().lower()
    if task in ("research", "long"):
        own = (getattr(settings, "AI_PROVIDERS_RESEARCH", "") or "auto").strip().lower()
        raw = own if own != "auto" else raw
    if raw == "auto":
        names, fixed = list(PROVIDERS), False
    else:
        names, fixed = [n.strip() for n in raw.split(",") if n.strip() in PROVIDERS], True
    return [n for n in names if configured(n)], fixed


def plan(task: str = "quick", need_tokens: int = 0) -> list[tuple[str, str]]:
    """(provider, model) in the order a request for this job would ask them right now."""
    names, fixed = _names(task)
    pairs = R.route(task, names, need_tokens, fixed)
    if not fixed and (getattr(settings, "AI_PROVIDER", "") or "").lower() == "anthropic":   # older setting: Claude first
        pairs = [x for x in pairs if x[0] == "anthropic"] + [x for x in pairs if x[0] != "anthropic"]
    return pairs


def order(kind: str = "quick") -> list[str]:
    """Providers in the order a request for this job asks them first."""
    task = kind if kind in TASKS else "quick"
    return list(dict.fromkeys(n for n, _ in plan(task)))


# ---------- asking ----------
def _override(fn, name: str, system: str, text: str, max_tokens: int, want_json: bool) -> str:
    """A provider replaced by a plain function (the tests do this): same checks and bookkeeping."""
    t0 = time.time()
    try:
        out = fn(system, text, max_tokens=max_tokens)
        out = check(out, None, want_json)
    except RateLimited as e:
        err = CallError("rate", e.detail, wait=e.wait, scope="provider")
    except AIConfig as e:
        err = CallError("auth", e.detail, scope="provider")
    except AIBusy as e:
        err = CallError("rate", e.detail, scope="provider")
    except AIError as e:
        err = CallError("model", e.detail)
    except BadReply as e:
        R.record_fail(name, "default", e)
        raise
    else:
        R.record_ok(name, "default", (time.time() - t0) * 1000)
        return out
    R.record_fail(name, "default", err)
    raise err


def complete(system: str, text: str, gemini=None, anthropic=None, transport=None, max_tokens: int = 1500,
             kind: str = "quick", want_json: bool = True, use_cache: bool = True) -> str:
    """Ask the best available models in turn and return the first checked reply (a JSON object, unless
    want_json=False). `kind` is the job: "quick", "research" or "long". `gemini`/`anthropic` replace those
    providers with a plain function (tests); the app's own wrappers are marked `_builtin` and ignored."""
    task = kind if kind in TASKS else "quick"
    names, _ = _names(task)
    if not names:
        raise AIConfig("The AI isn't set up on the server yet.",
                       detail="No AI provider has a key. Add a free one such as GROQ_API_KEY or GEMINI_API_KEY in Railway → Variables.")
    key = AnswerCache.key(task, system, text, max_tokens, want_json)
    if use_cache:
        hit = cache.get(key)
        if hit is not None:
            return hit
    overrides = {n: f for n, f in (("gemini", gemini), ("anthropic", anthropic)) if callable(f) and not getattr(f, "_builtin", False)}
    need = int((len(system) + len(text)) / 3.5) + max_tokens
    pairs, seen = [], set()
    for name, model in plan(task, need):
        if name in overrides:
            if name in seen:
                continue
            seen.add(name)
            model = "default"
        pairs.append((name, model))
    if not pairs:
        raise AIBusy(detail="No AI model in use can take a document this long.")
    deadline = time.time() + BUDGET[task]
    errors, tries, gone, failed = [], 0, {}, set()
    for attempt in (0, 1):
        cooling, skip = [], set()
        for name, model in pairs:
            now = time.time()
            if name in skip or (name, model) in failed or tries >= MAX_TRIES or deadline - now < 2:
                continue
            wait = R.ready(name, model, now)
            if wait > 0:
                cooling.append(wait)
                if attempt == 0:
                    errors.append(f"{LABELS[name]} · {model}: waiting {wait:.0f}s ({R.status(name).cool_reason or R.stats(name, model).open_reason or 'rate limit'})")
                continue
            tries += 1
            try:
                if name in overrides:
                    out = _override(overrides[name], name, system, text, max_tokens, want_json)
                else:
                    out = R.ask_model(name, model, system, text, max_tokens, want_json, min(deadline, now + PER_CALL[task]), transport)
            except CallError as e:
                errors.append(f"{LABELS[name]} · {model}: {e.detail}")
                if e.scope == "provider" or e.kind in ("auth", "credit", "transient"):
                    skip.add(name)                      # down, out of quota or slow: its other models would be too
                if e.kind == "rate":
                    left = R.ready(name, model)
                    if left > 0:
                        cooling.append(left)
                else:
                    failed.add((name, model))           # asked once in this request is enough
                gone.setdefault(name, []).append(e.kind in ("model", "forbidden"))
                continue
            except BadReply as e:
                errors.append(f"{LABELS[name]} · {model}: {e.why.replace('_', ' ')} reply")
                failed.add((name, model))
                gone.setdefault(name, []).append(True)
                continue
            if use_cache:
                cache.set(key, out, CACHE_TTL[task])
            return out
        # every model failed: if one is only briefly rate limited, wait for it once rather than give up
        soonest = min(cooling) if cooling else None
        if attempt == 0 and soonest is not None and soonest <= min(WAIT_FOR_COOLDOWN, deadline - time.time() - 5):
            _sleep(soonest + 0.5)
            continue
        break
    for name, fails in gone.items():                    # every model asked there is gone: measure that provider again
        if fails and all(fails) and len(fails) >= min(len(R.in_use(name)), 2):
            R.heal(name)
    detail = "No AI model could answer. " + " · ".join(dict.fromkeys(errors)) if errors else "Every AI model is cooling down."
    last_failure.update(at=time.time(), task=task, detail=detail[:1500])
    raise AIBusy(detail=detail)


def _sleep(seconds: float):
    time.sleep(seconds)


def ask_provider(name: str, system: str, text: str, max_tokens: int = 1500, transport=None, want_json: bool = True) -> str:
    """One provider only, its models in turn (the app's `_gemini` / `_anthropic` wrappers)."""
    if not configured(name):
        raise AIConfig("The AI isn't set up on the server yet.", detail=f"{PROVIDERS[name].key_env} is missing.")
    last: Exception | None = None
    deadline = time.time() + BUDGET["research"]
    for model in R.in_use(name):
        if R.ready(name, model) > 0:
            continue
        try:
            return R.ask_model(name, model, system, text, max_tokens, want_json, deadline, transport)
        except (CallError, BadReply) as e:
            last = e
            if isinstance(e, CallError) and e.scope == "provider":
                break
    raise AIBusy(detail=f"{LABELS[name]}: {getattr(last, 'detail', None) or getattr(last, 'why', 'no model ready')}")


# ---------- the Admin page ----------
QUOTA_TEXT = "Free quota used up for now; it resets on its own."
TEST_SYSTEM = 'Reply with ONLY this JSON object and nothing else: {"ok": true}'


def test_all(gemini=None, anthropic=None, transport=None) -> list[dict]:
    """Send a tiny request to every provider that has a key, ignoring breakers and cooldowns, and report each
    result. A provider's next model is tried when the first fails, so this shows whether the provider works."""
    overrides = {n: f for n, f in (("gemini", gemini), ("anthropic", anthropic)) if callable(f) and not getattr(f, "_builtin", False)}
    names = [n for n in order() if configured(n)]
    names += [n for n in DEFAULT_ORDER if configured(n) and n not in names]
    out = []
    for name in names:
        t0, error, model, quota = time.time(), None, None, False
        models = ["default"] if name in overrides else R.in_use(name)[:2]
        for m in models:
            try:
                if name in overrides:
                    _override(overrides[name], name, TEST_SYSTEM, "ping", 200, True)
                else:
                    R.ask_model(name, m, TEST_SYSTEM, "ping", 200, True, time.time() + 20, transport, live=False)
                model, error = m, None
                break
            except CallError as e:
                error, quota = e.detail, e.kind in ("rate", "credit")
                if e.scope == "provider":
                    break
            except BadReply as e:
                error = f"{e.why.replace('_', ' ')} reply ({m})"
        if quota:
            error = QUOTA_TEXT
        out.append({"name": name, "label": LABELS[name], "ok": error is None, "error": error, "quota": quota,
                    "model": model, "ms": round((time.time() - t0) * 1000)})
    return out


def health() -> list[dict]:
    """Every provider, for the Admin overview and the public "is AI on" flag."""
    ranks = {t: order(t) for t in ("quick", "research")}
    out, now = [], time.time()
    for name in DEFAULT_ORDER:
        st = status(name)
        q, r = ranks["quick"], ranks["research"]
        # the same reading as the provider's own row in Admin → System: whether it can answer now, and why not, in
        # the provider's own words (status code and message, keys taken out) (R5O-016)
        view = _provider_view(name, now) if configured(name) else None
        answering = None if view is None else view["answering"]
        out.append({"name": name, "label": LABELS[name], "configured": configured(name), "in_use": name in q,
                    "quick_rank": q.index(name) + 1 if name in q else None,
                    "research_rank": r.index(name) + 1 if name in r else None,
                    "model": st.model or (R.in_use(name)[:1] or [None])[0] if configured(name) else None,
                    "last_ok": st.last_ok, "last_error": st.last_error, "quota": st.quota,
                    "answering": answering, "state": view["state"] if view else "off",
                    "state_text": view["state_text"] if view else None,
                    "paused_models": view["paused_models"] if view else 0,
                    "quota_used": bool(view and view["quota"]["limited"])})
    return out


def _provider_view(name: str, now: float) -> dict:
    p, st = PROVIDERS[name], status(name)
    is_on = configured(name)
    use = R.in_use(name) if is_on else []
    pin_admin = R.pins().get(name)
    pin_env = model_setting(name) if name != "anthropic" else ""
    listed = list(dict.fromkeys(use + list(st.order) + [m for m, s in st.models.items() if s.probe_tries or s.live]))
    models = []
    for m in listed[:12]:
        s = R.stats(name, m)
        ok, tries = s.counts()
        med = s.median_ms()
        models.append({"id": m, "in_use": m in use, "rank": use.index(m) + 1 if m in use else None,
                       "success": round(ok * 100 / tries) if tries else None, "tries": tries,
                       "median_ms": round(med) if med is not None else None,
                       "probe": {"ok": s.probe_ok, "tries": s.probe_tries, "at": s.probe_at or None, "error": s.probe_error},
                       "last_error": s.last_error, "last_error_at": s.last_error_at,
                       "open_until": s.open_until if s.open_until > now else None, "open_reason": s.open_reason if s.open_until > now else None,
                       "blocked": R.blocked(name, m), "pinned": m == (pin_admin or pin_env), "ctx": s.ctx, "thinks": thinks(m)})
    cooling = st.cooldown_until > now
    all_closed = bool(use) and all(R.ready(name, m, now) > 0 for m in use)
    if not is_on:
        state, text = "off", "No key yet."
    elif st.config_error and cooling:
        state, text = "fail", f"The key was rejected: {st.last_error or 'check it in Railway'}. Fix the key, then press Test."
    elif st.quota and (cooling or all_closed):
        state, text = "warn", QUOTA_TEXT
    elif cooling or all_closed:
        state, text = "warn", f"Paused for now: {st.cool_reason or st.last_error or 'its models keep failing'}. The others take over."
    elif st.last_error and (st.last_error_at or 0) >= (st.last_ok or 0) and st.last_error_kind == "rate":
        # a short rate limit on one model or the key: it answers again in a moment, so it isn't "down" (R5O-016)
        state, text = "ok", f"Working; rate limited for a moment on the last try ({st.last_error})."
    elif st.last_error and (st.last_error_at or 0) >= (st.last_ok or 0) and st.last_error_kind in ("model", "forbidden") \
            and st.last_ok and any(R.ready(name, m, now) == 0 for m in use):
        # one listed model isn't served to this key; the ones in use answer
        state, text = "ok", f"Working; one other model isn't available to this key ({st.last_error})."
    elif st.last_error and (st.last_error_at or 0) >= (st.last_ok or 0):
        state, text = "warn", f"Last try failed: {st.last_error}"
    elif st.last_ok or st.order:
        state, text = "ok", "Working."
    else:
        state, text = "idle", "Key set. Press Test to check it, or Re-rank to measure its models."
    pin = pin_admin or pin_env
    if pin and R.pin_gone(name, pin):
        text += (f" The pinned model {pin} isn't available any more ({R.stats(name, pin).last_error}), so the measured models "
                 f"answer instead: " + (f"remove {p.model_env} in Railway." if pin_env and not pin_admin else "unpin it here."))
    # can it answer now: a short rate limit (it answers again in a moment) counts as yes; a used-up free quota, a
    # paused provider, a rejected key or a model gone does not (R5O-016; R6O-003: "12 of 12 answering" beside a paused
    # provider and one whose free credit was used up)
    answering = None if not is_on else state in ("ok", "idle") or (state == "warn" and st.last_error_kind == "rate" and not st.quota)
    paused_models = sum(1 for m in models if m["in_use"] and m["open_until"])
    reset_at = st.quota_reset if (st.quota_reset or 0) > now else (st.cooldown_until if cooling else None)
    return {"name": name, "label": p.label, "configured": is_on, "missing": missing(name), "key_url": p.key_url,
            "free": p.free, "terms": p.terms, "note": p.note, "variables": [p.key_env, *p.extra_env], "model_variable": p.model_env,
            "state": state, "state_text": text, "answering": answering, "paused_models": paused_models,
            "quota": {"limited": bool(st.quota and (cooling or all_closed)), "reset_at": reset_at,
                      "remaining": {k: v for k, v in st.remaining.items() if k in ("requests", "tokens")} or None,
                      "remaining_at": st.remaining.get("at")},
            "last_ok": st.last_ok, "last_error": st.last_error, "last_used_model": st.model,
            "pinned": pin_admin or pin_env or None, "pinned_by": "admin" if pin_admin else "railway" if pin_env else None,
            "ranked_at": st.ranked_at or None, "rank_error": st.rank_error, "discovered": st.discovered, "skipped": st.skipped,
            "probing": st.probing, "models": models,
            "blocked": [b.split("/", 1)[1] for b in R.blocks() if b.startswith(name + "/")]}


def admin_view() -> dict:
    """Everything the Admin page's AI panel shows."""
    now = time.time()
    names = [n for n in DEFAULT_ORDER if configured(n)] + [n for n in DEFAULT_ORDER if not configured(n)]
    routes = {}
    for task in TASKS:
        routes[task] = {"label": TASK_LABELS[task], "budget_s": BUDGET[task],
                        "steps": [{"provider": n, "label": LABELS[n], "model": m, "ready": R.ready(n, m, now) == 0}
                                  for n, m in plan(task)][:10]}
    return {"providers": [_provider_view(n, now) for n in names], "routes": routes,
            "cache": {"entries": len(cache.items), "hits": cache.hits, "misses": cache.misses},
            "rerank_every_hours": R.RERANK_EVERY / 3600, "last_failure": dict(last_failure) or None}


def rerank(names: list[str] | None = None, transport=None, wait: bool = False) -> list[str]:
    """Measure providers' models again (all free ones with a key, or just these). In the background unless `wait`."""
    names = [n for n in (names or [n for n in PROVIDERS if PROVIDERS[n].terms != "paid"]) if n in PROVIDERS and configured(n)]
    if wait:
        R.rerank_many(names, transport)
        return names
    return R.start_rerank(names, transport)


def pin(name: str, model: str | None):
    R.pin(name, model)


def block(name: str, model: str, on: bool = True):
    R.block(name, model, on)


job = R.RerankJob()
