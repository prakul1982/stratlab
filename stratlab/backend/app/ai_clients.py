"""Talking to each AI provider: one request to one model, and listing a provider's models.

Three kinds of API: the OpenAI-style chat API (most providers), Google's own Gemini API, and Anthropic's. Each call
returns a Reply or raises CallError saying what went wrong in a way the router can act on (try the next model, skip
the provider until its quota resets, …). Nothing here decides which model to use: that's ai_rank.py and
ai_providers.py."""
import re
import time
from dataclasses import dataclass, field

import httpx

from . import ai_spend
from .ai_catalog import PROVIDERS, base_url, family, key_for, keys_for, setting, thinks
from .ai_reply import answer, is_daily, strip_thinking, too_big, wait_from


@dataclass
class Reply:
    text: str
    finish: str | None
    ms: float
    headers: dict = field(default_factory=dict)
    usage: dict | None = None          # what a paid provider billed for this reply (Anthropic's `usage`), for the spend meter


class CallError(Exception):
    """One request failed. kind says how to react:
    auth      the key is wrong or missing a permission: skip the provider until it's fixed
    credit    the free credit is used up (402): skip the provider for hours
    rate      rate limited (429): skip the model or provider until `wait` seconds pass
    model     this model can't be used (unknown, retired, not on this plan): skip it for hours
    forbidden this key may not use this model (403): skip the model for hours
    context   the prompt is too long for this model: skip it for this request only
    refusal   the model declined this request (Claude's stop_reason "refusal"): ask the next model, no breaker
    tier      this request may not go with any Claude key right now at this model (the second key's credit left is
              too little for it, or the first key is past its Sonnet limit): ask the next model, no breaker
    transient timeout, network or server error: count towards the circuit breaker
    busy      this one model is overloaded right now ("high demand"): ask the provider's next model, breaker as transient
    """

    def __init__(self, kind: str, detail: str, wait: float | None = None, scope: str = "model", daily: bool = False):
        super().__init__(detail)
        self.kind, self.detail, self.wait, self.scope, self.daily = kind, detail, wait, scope, daily


def _timeout(deadline: float) -> httpx.Timeout:
    left = deadline - time.time()
    if left < 1.0:
        raise CallError("transient", "ran out of time", scope="model")
    return httpx.Timeout(left, connect=min(6.0, left))


_TOKENS = re.compile(r"(?i)\b(bearer|key|token|api[_-]?key)(\s*[:=]?\s*)[A-Za-z0-9._~+/=-]{12,}")


def redact(text: str) -> str:
    """Error text with every configured key taken out, and anything after "Bearer", "key=" or "token:" that looks like
    one: a provider that echoes the key it was sent mustn't put it on the Admin page or in the logs."""
    for p in PROVIDERS.values():
        for k in keys_for(p.name):
            if len(k) >= 6:
                text = text.replace(k, "[key]")
    return _TOKENS.sub(lambda m: m.group(1) + m.group(2) + "[key]", text)


def clip(text: str, n: int = 160) -> str:
    """Text cut to about `n` characters at a word, with "…" when cut: a provider's error never ends mid-word on Admin
    (DJ-036: "…and impro)", "…(OTPM): Lim)")."""
    text = str(text or "")
    if len(text) <= n:
        return text
    cut = text[:n - 1]
    space = cut.rfind(" ")
    return (cut[:space] if space > n // 2 else cut).rstrip(" ,;:(") + "…"


def _short(r: httpx.Response) -> str:
    """The provider's own error message, short and without any key, for the Admin page."""
    return clip(redact(_short_raw(r)), 160)


def not_a_reply(r: httpx.Response) -> str:
    """What came back instead of the JSON asked for: its type and the start of it, keys taken out."""
    kind = (r.headers.get("content-type") or "no content type").split(";")[0]
    return f"{kind}: {_short(r) or 'nothing'}"


def _short_raw(r: httpx.Response) -> str:
    try:
        data = r.json()
        err = data.get("error") if isinstance(data, dict) else None
        msg = (err.get("message") if isinstance(err, dict) else err) or (data.get("message") if isinstance(data, dict) else None) \
            or (data.get("detail") if isinstance(data, dict) else None)
        if isinstance(msg, (dict, list)):
            msg = str(msg)
        if msg:
            return str(msg)[:2000]
    except ValueError:
        pass
    return re.sub(r"\s+", " ", r.text or "")[:2000]


# a model that's overloaded right now (its capacity, not this key's allowance)
_BUSY = re.compile(r"high demand|overloaded|over capacity|at capacity|capacity (?:is )?(?:exhausted|reached)|model is busy", re.I)


# a refusal of this one model on this plan, said by the provider itself
_MODEL_NOT_FREE = re.compile(r"(this |the )?model (is )?not (included|available|part of)[^.]{0,40}\b(free|plan|tier|usage)|"
                             r"not included in your (free )?(plan|usage|tier)|model requires (a )?(paid|pro|premium)", re.I)


def classify(name: str, r: httpx.Response, model: str) -> CallError:
    """What an error status means for the router."""
    p, code, body = PROVIDERS[name], r.status_code, r.text or ""
    msg = _short(r)
    # every message carries the status code and the provider's own words, so Admin tells a rejected key from a bug
    if code == 401:
        return CallError("auth", f"rejected the key (401: {msg})" if msg else "rejected the key (401)", scope="provider")
    if code != 429 and re.search(r"credit card|payment method on file|billing (details|information)", body, re.I):
        # an account setting, not a used-up allowance: nothing resets on its own (a gateway that wants a card on file)
        return CallError("auth", f"the account needs a payment method on file ({code}: {msg})", scope="provider")
    if code == 402 or re.search(r"credit balance|insufficient (credit|balance|quota)|out of credits|payment required", body, re.I):
        said = f" ({code}: {msg})" if msg else f" ({code})"
        # a 402 that names the model, not the account ("this model is not included in your free usage", Ollama Cloud, 5 Nov): only
        # that model is off for this key; the provider's free models still answer (it paused all of Ollama for six hours)
        if p.mixed_catalog or _MODEL_NOT_FREE.search(body):
            # a provider that lists paid models beside its free ones (Z.ai: glm-5.3-flash answers "Insufficient balance"
            # while glm-4.7-flash is free): that model isn't free for this key, the provider's free ones still answer
            return CallError("forbidden", f"{model} isn't free for this key{said}")
        # the provider's own words go with it, so Admin tells a used-up trial from a daily cap (owner, 4 Nov)
        return CallError("credit", "the free credit is used up" + said, wait=6 * 3600, scope="provider", daily=True)
    if code == 429:
        wait, daily = wait_from(r.headers, body), is_daily(body)
        # Groq's 429 always names the organization though the cap is the model's: only a plainly account-wide limit pauses all
        whole = re.search(r"free-models-per-day|(account|organi[sz]ation)\b[^.]{0,40}\b(restricted|suspended|disabled|blocked)", body, re.I)
        # "<model> is currently experiencing high demand" (SambaNova's 429) is that model being busy, not the key's limit
        scope = "provider" if (p.limit_scope == "provider" and not _BUSY.search(body)) or whole else "model"
        return CallError("rate", "rate limited" + (" (daily free quota)" if daily else "") + (f" (429: {msg})" if msg else " (429)"), wait=wait, scope=scope,
                         daily=daily or (wait or 0) > 600)
    if too_big(code, body):
        return CallError("context", "the prompt is too long for this model")
    if code == 403:
        if name == "gemini" and re.search(r"api key|permission", body, re.I):
            return CallError("auth", f"rejected the key (403: {msg})", scope="provider")
        return CallError("forbidden", f"this key can't use {model} (403: {msg})")
    if code in (404, 400, 422, 405, 410):          # 410: "the requested model ... is no longer available" (SambaNova, 4 Nov)
        if name == "gemini" and code == 400 and re.search(r"api key not valid|api_key_invalid", body, re.I):
            return CallError("auth", f"rejected the key (400: {msg})", scope="provider")
        return CallError("model", f"couldn't use {model} ({code}: {msg})")
    if code == 408 or code >= 500:
        # "This model is currently experiencing high demand" (Gemini's 503, most of its failures on 4 Nov): that one model
        # is overloaded, the provider's other models still answer, so only the model is skipped for this request
        if _BUSY.search(body):
            return CallError("busy", f"server error {code}" + (f" ({msg})" if msg else ""), scope="model")
        return CallError("transient", f"server error {code}" + (f" ({msg})" if msg else ""), scope="provider")
    return CallError("model", f"unexpected answer {code} ({msg})")


# ---------- the OpenAI-style chat API ----------
def body_for(name: str, model: str, system: str, text: str, max_tokens: int, json_mode: bool) -> dict:
    """The request. A reasoning model gets room to think and still answer, and is asked to think little or not at
    all, in whichever way that provider accepts (anything it rejects is taken out again by `repair`):
    gpt-oss and OpenAI's o-series take reasoning_effort "low"; Cerebras and Groq turn Qwen and GLM thinking off with
    reasoning_effort "none"; Z.ai with thinking.type "disabled"; SambaNova, NVIDIA, Hugging Face and Cloudflare run
    the open models' chat template, which takes enable_thinking; OpenRouter has its own `reasoning` object; Qwen also
    obeys "/no_think" in the message and Nemotron in the system prompt."""
    p = PROVIDERS[name]
    reasoning, fam = thinks(model), family(model)
    room = min(p.max_out, max(max_tokens * 2, 4000)) if reasoning else min(p.max_out, max_tokens)
    sys_text, user_text = system, text
    body: dict = {"model": model, "temperature": 0.1, "max_tokens": room}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    if reasoning:
        if name == "openrouter":
            body["reasoning"] = {"effort": "low", "exclude": True}
        elif fam in ("gpt-oss", "openai-reasoning"):
            body["reasoning_effort"] = "low"
        elif name in ("cerebras", "groq"):
            body["reasoning_effort"] = "none"
        elif name == "zai":
            body["thinking"] = {"type": "disabled"}
        elif name in ("sambanova", "nvidia", "huggingface", "cloudflare"):
            body["chat_template_kwargs"] = {"thinking": False} if fam == "deepseek" else {"enable_thinking": False}
        else:
            body["reasoning_effort"] = "low"
        if fam == "qwen":
            user_text = text + "\n\n/no_think"
        if fam == "nemotron":
            sys_text = "/no_think\n" + system
    body["messages"] = [{"role": "system", "content": sys_text}, {"role": "user", "content": user_text}]
    return body


_REPAIRS = (   # (setting, words in the provider's complaint that mean it doesn't take that setting)
    ("reasoning_effort", ("reasoning_effort", "reasoning effort")),
    ("chat_template_kwargs", ("chat_template_kwargs", "enable_thinking", "chat_template")),
    ("reasoning", ("reasoning",)),
    ("thinking", ("thinking",)),
    ("response_format", ("response_format", "json_object", "json mode", "json_validate", "failed to generate json", "json")),
    ("temperature", ("temperature",)),
)


def repair(body: dict, error: str, done: set) -> bool:
    """Take out (or rename) the one setting a 400 complains about, so the request can be sent again. False when
    there's nothing left to try."""
    e = (error or "").lower()
    if "max_tokens" in body and "max_completion_tokens" in e and "rename" not in done:
        body["max_completion_tokens"] = body.pop("max_tokens")
        done.add("rename")
        return True
    m = re.search(r"max_(?:completion_)?tokens.{0,60}?(?:<=|less than or equal to|at most|maximum(?: value)?(?: is| of)?|up to)\s*`?(\d+)", e)
    if m and "cap" not in done:
        k = "max_tokens" if "max_tokens" in body else "max_completion_tokens"
        if k in body and int(m.group(1)) < body[k]:
            body[k] = int(m.group(1))
            done.add("cap")
            return True
    for key, words in _REPAIRS:
        if key in body and key not in done and any(w in e for w in words):
            body.pop(key)
            done.add(key)
            return True
    return False


class OpenAIStyle:
    def __init__(self, name: str, transport: httpx.BaseTransport | None = None):
        self.name, self.p, self.transport = name, PROVIDERS[name], transport

    def _client(self, deadline: float) -> httpx.Client:
        headers = {"Authorization": f"Bearer {key_for(self.name)}", **self.p.headers}
        return httpx.Client(base_url=base_url(self.name), headers=headers, timeout=_timeout(deadline), transport=self.transport)

    def call(self, model: str, system: str, text: str, max_tokens: int, json_mode: bool, deadline: float,
             task: str = "quick") -> Reply:
        body = body_for(self.name, model, system, text, max_tokens, json_mode)
        done: set = set()
        t0 = time.time()
        while True:
            try:
                with self._client(deadline) as c:
                    r = c.post("/chat/completions", json=body)
            except httpx.TimeoutException:
                raise CallError("transient", "timed out") from None
            except httpx.HTTPError as e:
                raise CallError("transient", f"couldn't be reached ({e.__class__.__name__})", scope="provider") from None
            if r.status_code in (400, 422) and not too_big(r.status_code, r.text) and repair(body, r.text, done):
                continue
            break
        ms = (time.time() - t0) * 1000
        if r.status_code != 200:
            raise classify(self.name, r, model)
        try:
            data = r.json()
        except ValueError:
            data = None
        if not isinstance(data, dict) or not isinstance(data.get("choices"), list):
            # a 200 that isn't a chat reply at all (a gateway's page, an error in another shape): say what came back,
            # so Admin shows the provider's own words instead of "empty reply" (R5O-016)
            raise CallError("transient", f"answered {r.status_code} without a chat reply ({not_a_reply(r)})", scope="provider")
        try:
            choice = data["choices"][0]
            msg = choice.get("message") or {}
        except (KeyError, IndexError, TypeError, AttributeError):
            return Reply("", None, ms, dict(r.headers))
        return Reply(answer(msg), choice.get("finish_reason"), ms, dict(r.headers))

    def models(self, deadline: float) -> list[dict]:
        url = (self.p.models_url or "").replace("{account}", setting("CLOUDFLARE_ACCOUNT_ID"))
        try:
            with self._client(deadline) as c:
                r = c.get(url)
        except httpx.HTTPError as e:
            raise CallError("transient", f"couldn't list models ({e.__class__.__name__})", scope="provider") from None
        if r.status_code in (401, 403):
            raise CallError("auth", f"rejected the key while listing models ({r.status_code}: {_short(r)})", scope="provider")
        if r.status_code >= 400:
            raise CallError("transient", f"couldn't list models ({r.status_code}: {_short(r)})", scope="provider")
        if r.is_redirect:
            raise CallError("transient", f"couldn't list models ({r.status_code}: moved to {redact(r.headers.get('location', '?'))[:120]})",
                            scope="provider")
        try:
            data = r.json()
            self.aliases = parse_aliases(data)           # R7M-008: a UUID Cloudflare lists beside the model's usable name
            return parse_models(data)
        except (ValueError, TypeError, AttributeError):
            raise CallError("transient", f"sent something that isn't a model list ({r.status_code}, {not_a_reply(r)})",
                            scope="provider") from None


def _ctx(item: dict) -> int | None:
    """The context window a model list gives, in whichever field that provider uses."""
    for k in ("context_window", "context_length", "max_context_length", "max_model_len", "inputTokenLimit"):
        v = item.get(k)
        if isinstance(v, (int, float)) and v > 0:
            return int(v)
    for prop in item.get("properties") or []:
        if isinstance(prop, dict) and prop.get("property_id") == "context_window":
            try:
                return int(float(prop.get("value")))
            except (TypeError, ValueError):
                pass
    sizes = [x.get("context_length") for x in item.get("providers") or [] if isinstance(x, dict)]
    sizes = [int(s) for s in sizes if isinstance(s, (int, float))]
    return max(sizes) if sizes else None


_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)


def parse_aliases(data) -> dict[str, str]:
    """{UUID: usable name} for the models a list gives under a UUID `id` with the name beside it (Cloudflare's)."""
    items = (data.get("data") or data.get("result") or data.get("models") or []) if isinstance(data, dict) else data
    out = {}
    for it in items if isinstance(items, list) else []:
        if isinstance(it, dict) and _UUID.match(str(it.get("id") or "")) and str(it.get("name") or "").startswith(("@cf/", "@hf/")):
            out[str(it["id"])] = str(it["name"])
    return out


# A model list's `type` that is never a chat model. Anything else counts as one: Mistral types every model "base" or
# "fine-tuned" (a list that kept only "language"/"chat" types dropped all of them: "listed no models when asked", 4 Nov).
_NOT_TEXT_TYPES = {"embedding", "embeddings", "image", "video", "audio", "speech", "transcription", "tts", "rerank",
                   "reranking", "moderation", "classification", "ocr"}


def parse_models(data) -> list[dict]:
    """[{"id", "ctx"}] from any provider's model list: OpenAI-style {"data": […]}, Cloudflare's {"result": […]},
    Google's {"models": […]} or a plain list."""
    items = (data.get("data") or data.get("result") or data.get("models") or []) if isinstance(data, dict) else data
    out = []
    for it in items if isinstance(items, list) else []:
        if not isinstance(it, dict):
            continue
        mid = str(it.get("id") or it.get("name") or "")
        name = str(it.get("name") or "")
        if name.startswith(("@cf/", "@hf/")) or (_UUID.match(mid) and name):
            # Cloudflare lists each model under a UUID `id` and its usable name ("@cf/meta/…") in `name`; the chat API
            # wants the name ("No such model <uuid>", code 5007, otherwise)
            mid = name
        if mid.startswith("models/"):
            mid = mid[len("models/"):]
        methods = it.get("supportedGenerationMethods")
        if methods is not None and "generateContent" not in methods:
            continue                                        # a Gemini model that can't write text
        if str(it.get("type") or "").lower() in _NOT_TEXT_TYPES:
            continue                                        # Vercel: embedding and image models
        caps = it.get("capabilities")
        if isinstance(caps, dict) and caps.get("completion_chat") is False:
            continue                                        # Mistral: a model that can't chat (OCR, embeddings, moderation)
        if it.get("archived") is True:
            continue                                        # Mistral: a retired model still listed
        if mid:
            out.append({"id": mid, "ctx": _ctx(it)})
    return out


# ---------- Google's Gemini API ----------
def gemini_thinking(model: str) -> dict:
    """How little a Gemini model is asked to think. Gemini 3 and later take a level, not a token budget: sent
    thinkingBudget 0 they either rejected the request (400 "invalid argument", gemini-3.5-flash-lite) or thought at
    their default level, which ran past the time allowed ("timed out", gemini-3.8-flash; 4 Nov). "low" is the least
    every Gemini 3 model takes ("minimal" isn't offered on 3.8 Flash). Older Gemini and Gemma keep the budget of 0."""
    m = re.match(r"gemini-(\d+)", model or "")
    return {"thinkingLevel": "low"} if m and int(m.group(1)) >= 3 else {"thinkingBudget": 0}


class GeminiNative:
    """Gemini and Gemma through Google's own API, which (unlike its OpenAI-style one) lets thinking be switched off."""

    def __init__(self, name: str = "gemini", transport: httpx.BaseTransport | None = None):
        self.name, self.p, self.transport = name, PROVIDERS[name], transport

    def _client(self, deadline: float) -> httpx.Client:
        return httpx.Client(base_url=base_url(self.name), headers={"x-goog-api-key": key_for(self.name)},
                            timeout=_timeout(deadline), transport=self.transport)

    def call(self, model: str, system: str, text: str, max_tokens: int, json_mode: bool, deadline: float,
             task: str = "quick") -> Reply:
        gen = {"temperature": 0.1, "maxOutputTokens": max(max_tokens, 8192),
               # these are extraction jobs: thinking only spends the reply budget (and the free quota)
               "thinkingConfig": gemini_thinking(model)}
        if json_mode:
            gen["responseMimeType"] = "application/json"
        body = {"systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": text}]}], "generationConfig": gen}
        done: set = set()
        t0 = time.time()
        while True:
            try:
                with self._client(deadline) as c:
                    r = c.post(f"/models/{model}:generateContent", json=body)
            except httpx.TimeoutException:
                raise CallError("transient", "timed out") from None
            except httpx.HTTPError as e:
                raise CallError("transient", f"couldn't be reached ({e.__class__.__name__})", scope="provider") from None
            low = (r.text or "").lower()
            vague = "invalid argument" in low               # Google's 400 that names no field (gemini-3.5-flash-lite, 4 Nov)
            if r.status_code == 400 and ("thinking" in low or vague) and "thinkingConfig" in gen and "think" not in done:
                gen.pop("thinkingConfig")                   # a model that must think (or can't): let it decide
                done.add("think")
                continue
            if r.status_code == 400 and ("json mode" in low or "mime" in low or vague) and "responseMimeType" in gen and "json" not in done:
                gen.pop("responseMimeType")
                done.add("json")
                continue
            if r.status_code == 400 and "instruction" in low and "systemInstruction" in body and "system" not in done:
                body.pop("systemInstruction")               # Gemma takes no system prompt: put it in the message
                body["contents"][0]["parts"][0]["text"] = system + "\n\n" + text
                done.add("system")
                continue
            break
        ms = (time.time() - t0) * 1000
        if r.status_code != 200:
            raise classify(self.name, r, model)
        try:
            cand = r.json()["candidates"][0]
            parts = (cand.get("content") or {}).get("parts") or []
        except (KeyError, IndexError, ValueError, TypeError, AttributeError):
            return Reply("", None, ms, dict(r.headers))
        out = "".join(p.get("text", "") for p in parts if isinstance(p, dict) and not p.get("thought"))
        finish = cand.get("finishReason")
        return Reply(strip_thinking(out), "length" if finish == "MAX_TOKENS" else finish, ms, dict(r.headers))

    def models(self, deadline: float) -> list[dict]:
        try:
            with self._client(deadline) as c:
                r = c.get("/models", params={"pageSize": 1000})
        except httpx.HTTPError as e:
            raise CallError("transient", f"couldn't list models ({e.__class__.__name__})", scope="provider") from None
        if r.status_code in (400, 401, 403):
            raise CallError("auth", f"rejected the key while listing models ({r.status_code}: {_short(r)})", scope="provider")
        if r.status_code >= 400:
            raise CallError("transient", f"couldn't list models ({r.status_code}: {_short(r)})", scope="provider")
        if r.is_redirect:
            raise CallError("transient", f"couldn't list models ({r.status_code}: moved to {redact(r.headers.get('location', '?'))[:120]})",
                            scope="provider")
        try:
            return parse_models(r.json())
        except (ValueError, TypeError, AttributeError):
            raise CallError("transient", f"sent something that isn't a model list ({r.status_code}, {not_a_reply(r)})",
                            scope="provider") from None


# ---------- Anthropic ----------
# How hard Claude thinks per job (output_config.effort). Thinking is on by default on the current models and can't be
# switched off there (thinking "disabled" and budget_tokens answer 400), so effort is the only dial: quick jobs (the
# idea builder, the ask bar) low; research reads and long documents medium.
EFFORT = {"quick": "low", "research": "medium", "long": "medium"}


# what the API says when a key can't be used at all (credit gone, a billing problem, the account's own usage limit reached):
# the second key is spent for the month
_KEY_GONE = re.compile(r"credit balance|insufficient (credit|balance|funds)|out of credits|billing|payment|usage limits?\b", re.I)


class AnthropicHTTP:
    """Claude through the Messages API. Paid: which model a job may use, and whether this month's credit allows the
    request at all, is decided by ai_spend; every reply's usage is priced and added to the month's spend here.

    Two keys (owner, 12 Nov): with ANTHROPIC_API_KEY_2 set and not spent, the request goes with it first, held against
    its own credit. If the API answers that key with used-up credit, a billing problem or a rejected key, it is marked
    spent for the month and the same request is sent at once with ANTHROPIC_API_KEY, under that key's own cap and tier.
    The key sent is never logged or put in an error."""

    def __init__(self, name: str = "anthropic", transport: httpx.BaseTransport | None = None):
        self.name, self.transport = name, transport

    def call(self, model: str, system: str, text: str, max_tokens: int, json_mode: bool, deadline: float,
             task: str = "quick") -> Reply:
        # thinking shares max_tokens with the answer: leave it room, so a thought-out answer isn't cut off (only the
        # tokens actually written are billed)
        room = min(PROVIDERS[self.name].max_out, max(max_tokens * 2, max_tokens + 4000))
        # no temperature/top_p/top_k (the current models answer 400 to sampling settings) and no assistant prefill.
        # The system prompt is one cached block: a job that repeats its instructions reads them from the cache at a
        # tenth of the price (a prompt under the model's minimum is simply not cached).
        body = {"model": model, "max_tokens": room,
                "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                "messages": [{"role": "user", "content": text}],
                "output_config": {"effort": EFFORT.get(task, "low")}}
        est = ai_spend.estimate_micros(model, len(system) + len(text), room)
        if ai_spend.key2_active():
            held = ai_spend.reserve(est, key=2)
            if held is not None:
                try:
                    return self._send(2, held, model, body, deadline)
                except CallError as e:
                    if not (e.kind in ("credit", "auth") or (e.kind != "rate" and _KEY_GONE.search(e.detail or ""))):
                        raise                           # a rate limit, a busy model, a timeout: the router's, as for one key
                    ai_spend.mark_spent(redact(e.detail))
        if ai_spend.key2():
            # a second key is set: the first key answers only under its own month's rules
            from .ai_rank import pinned
            if ai_spend.key2_active():
                # still active, but this request could pass what's left of its credit: the next (cheaper) model may fit
                if not key_for(self.name) or not ai_spend.key1_allows(model, pinned(self.name)):
                    raise CallError("tier", f"this request could pass what is left of the second Claude key's credit ({model})")
            elif not key_for(self.name):
                raise CallError("credit", "the second Claude key's credit is spent for this month and ANTHROPIC_API_KEY isn't set; "
                                "the free models answer until the month turns", wait=max(60.0, ai_spend.month_end() - time.time()),
                                scope="provider")
            elif not ai_spend.key1_allows(model, pinned(self.name)):
                raise CallError("tier", f"{model} is past the first Claude key's Sonnet limit this month; its next model answers")
        held = ai_spend.reserve(est)
        if held is None:
            cap = ai_spend.cap_usd()
            raise CallError("credit", f"this month's Claude budget (${cap:.0f}) is used up or can't be read; the free models "
                            "answer until it resets", wait=max(60.0, ai_spend.month_end() - time.time()), scope="provider")
        return self._send(1, held, model, body, deadline)

    def _send(self, slot: int, held: int, model: str, body: dict, deadline: float) -> Reply:
        """One request with key `slot` (1: ANTHROPIC_API_KEY, 2: ANTHROPIC_API_KEY_2), its reply billed to that key."""
        key = ai_spend.key2() if slot == 2 else key_for(self.name)
        t0 = time.time()
        try:
            with httpx.Client(base_url=base_url(self.name), timeout=_timeout(deadline), transport=self.transport,
                              headers={"x-api-key": key, "anthropic-version": "2023-06-01"}) as c:
                r = c.post("/messages", json=body)
        except httpx.TimeoutException:
            raise CallError("transient", "timed out") from None
        except httpx.HTTPError as e:
            raise CallError("transient", f"couldn't be reached ({e.__class__.__name__})", scope="provider") from None
        finally:
            ai_spend.release(held)
        ms = (time.time() - t0) * 1000
        if r.status_code != 200:
            raise classify(self.name, r, model)
        try:
            data = r.json()
        except ValueError:
            data = None
        if not isinstance(data, dict):
            raise CallError("transient", f"answered {r.status_code} without a message ({not_a_reply(r)})", scope="provider")
        usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
        stop = data.get("stop_reason")
        ai_spend.record(model, usage, refusal=stop == "refusal", key=slot)     # billed whatever the answer says
        if stop == "refusal":
            # Claude's safeguards declined this request: another model (or provider) may answer it; this one isn't broken
            raise CallError("refusal", f"{model} declined this request")
        # only "text" blocks are the answer: "thinking" blocks (empty by default) are the model's reasoning
        out = "".join(b.get("text", "") for b in data.get("content") or [] if isinstance(b, dict) and b.get("type") == "text")
        return Reply(out, "length" if stop == "max_tokens" else stop, ms, dict(r.headers), usage=usage)

    def models(self, deadline: float) -> list[dict]:
        return []


def client(name: str, transport: httpx.BaseTransport | None = None):
    kind = PROVIDERS[name].kind
    return GeminiNative(name, transport) if kind == "gemini" else AnthropicHTTP(name, transport) if kind == "anthropic" \
        else OpenAIStyle(name, transport)
