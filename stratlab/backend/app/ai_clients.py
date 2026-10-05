"""Talking to each AI provider: one request to one model, and listing a provider's models.

Three kinds of API: the OpenAI-style chat API (most providers), Google's own Gemini API, and Anthropic's. Each call
returns a Reply or raises CallError saying what went wrong in a way the router can act on (try the next model, skip
the provider until its quota resets, …). Nothing here decides which model to use: that's ai_rank.py and
ai_providers.py."""
import re
import time
from dataclasses import dataclass, field

import httpx

from .ai_catalog import PROVIDERS, base_url, family, key_for, setting, thinks
from .ai_reply import answer, is_daily, strip_thinking, too_big, wait_from


@dataclass
class Reply:
    text: str
    finish: str | None
    ms: float
    headers: dict = field(default_factory=dict)


class CallError(Exception):
    """One request failed. kind says how to react:
    auth      the key is wrong or missing a permission: skip the provider until it's fixed
    credit    the free credit is used up (402): skip the provider for hours
    rate      rate limited (429): skip the model or provider until `wait` seconds pass
    model     this model can't be used (unknown, retired, not on this plan): skip it for hours
    forbidden this key may not use this model (403): skip the model for hours
    context   the prompt is too long for this model: skip it for this request only
    transient timeout, network or server error: count towards the circuit breaker
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
        k = key_for(p.name)
        if k and len(k) >= 6:
            text = text.replace(k, "[key]")
    return _TOKENS.sub(lambda m: m.group(1) + m.group(2) + "[key]", text)


def _short(r: httpx.Response) -> str:
    """The provider's own error message, short and without any key, for the Admin page."""
    return redact(_short_raw(r))[:160]


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


def classify(name: str, r: httpx.Response, model: str) -> CallError:
    """What an error status means for the router."""
    p, code, body = PROVIDERS[name], r.status_code, r.text or ""
    msg = _short(r)
    if code == 401:
        return CallError("auth", f"rejected the key ({msg})" if msg else "rejected the key", scope="provider")
    if code == 402 or re.search(r"credit balance|insufficient (credit|balance|quota)|out of credits|payment required", body, re.I):
        return CallError("credit", "the free credit is used up", wait=6 * 3600, scope="provider", daily=True)
    if code == 429:
        wait, daily = wait_from(r.headers, body), is_daily(body)
        scope = "provider" if p.limit_scope == "provider" or re.search(r"free-models-per-day|account|organization", body, re.I) else "model"
        return CallError("rate", "rate limited" + (" (daily free quota)" if daily else ""), wait=wait, scope=scope,
                         daily=daily or (wait or 0) > 600)
    if too_big(code, body):
        return CallError("context", "the prompt is too long for this model")
    if code == 403:
        if name == "gemini" and re.search(r"api key|permission", body, re.I):
            return CallError("auth", f"rejected the key ({msg})", scope="provider")
        return CallError("forbidden", f"this key can't use {model} ({msg})")
    if code in (404, 400, 422, 405):
        if name == "gemini" and code == 400 and re.search(r"api key not valid|api_key_invalid", body, re.I):
            return CallError("auth", "rejected the key", scope="provider")
        return CallError("model", f"couldn't use {model} ({code}: {msg})")
    if code == 408 or code >= 500:
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

    def call(self, model: str, system: str, text: str, max_tokens: int, json_mode: bool, deadline: float) -> Reply:
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
            choice = r.json()["choices"][0]
            msg = choice.get("message") or {}
        except (KeyError, IndexError, ValueError, TypeError, AttributeError):
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
            raise CallError("auth", "rejected the key while listing models", scope="provider")
        if r.status_code >= 400:
            raise CallError("transient", f"couldn't list models ({r.status_code})", scope="provider")
        try:
            return parse_models(r.json())
        except (ValueError, TypeError, AttributeError):
            raise CallError("transient", "sent something that isn't a model list", scope="provider") from None


def _ctx(item: dict) -> int | None:
    """The context window a model list gives, in whichever field that provider uses."""
    for k in ("context_window", "context_length", "max_context_length", "max_model_len", "inputTokenLimit"):
        v = item.get(k)
        if isinstance(v, (int, float)) and v > 0:
            return int(v)
    limits = item.get("limits")
    if isinstance(limits, dict) and isinstance(limits.get("max_input_tokens"), (int, float)):
        return int(limits["max_input_tokens"])
    for prop in item.get("properties") or []:
        if isinstance(prop, dict) and prop.get("property_id") == "context_window":
            try:
                return int(float(prop.get("value")))
            except (TypeError, ValueError):
                pass
    sizes = [x.get("context_length") for x in item.get("providers") or [] if isinstance(x, dict)]
    sizes = [int(s) for s in sizes if isinstance(s, (int, float))]
    return max(sizes) if sizes else None


def parse_models(data) -> list[dict]:
    """[{"id", "ctx"}] from any provider's model list: OpenAI-style {"data": […]}, Cloudflare's {"result": […]},
    Google's {"models": […]} or GitHub's plain list."""
    items = (data.get("data") or data.get("result") or data.get("models") or []) if isinstance(data, dict) else data
    out = []
    for it in items if isinstance(items, list) else []:
        if not isinstance(it, dict):
            continue
        mid = str(it.get("id") or it.get("name") or "")
        if mid.startswith("models/"):
            mid = mid[len("models/"):]
        methods = it.get("supportedGenerationMethods")
        if methods is not None and "generateContent" not in methods:
            continue                                        # a Gemini model that can't write text
        outs = it.get("supported_output_modalities")
        if isinstance(outs, list) and outs and "text" not in outs:
            continue                                        # a GitHub model that doesn't write text
        if it.get("type") not in (None, "language", "chat", "llm", "text"):
            continue                                        # Vercel: embedding and image models
        if mid:
            out.append({"id": mid, "ctx": _ctx(it)})
    return out


# ---------- Google's Gemini API ----------
class GeminiNative:
    """Gemini and Gemma through Google's own API, which (unlike its OpenAI-style one) lets thinking be switched off."""

    def __init__(self, name: str = "gemini", transport: httpx.BaseTransport | None = None):
        self.name, self.p, self.transport = name, PROVIDERS[name], transport

    def _client(self, deadline: float) -> httpx.Client:
        return httpx.Client(base_url=base_url(self.name), headers={"x-goog-api-key": key_for(self.name)},
                            timeout=_timeout(deadline), transport=self.transport)

    def call(self, model: str, system: str, text: str, max_tokens: int, json_mode: bool, deadline: float) -> Reply:
        gen = {"temperature": 0.1, "maxOutputTokens": max(max_tokens, 8192),
               # these are extraction jobs: thinking only spends the reply budget (and the free quota)
               "thinkingConfig": {"thinkingBudget": 0}}
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
            if r.status_code == 400 and "thinking" in low and "thinkingConfig" in gen and "think" not in done:
                gen.pop("thinkingConfig")                   # a model that must think (or can't): let it decide
                done.add("think")
                continue
            if r.status_code == 400 and ("json mode" in low or "mime" in low) and "responseMimeType" in gen and "json" not in done:
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
            raise CallError("auth", "rejected the key while listing models", scope="provider")
        if r.status_code >= 400:
            raise CallError("transient", f"couldn't list models ({r.status_code})", scope="provider")
        try:
            return parse_models(r.json())
        except (ValueError, TypeError, AttributeError):
            raise CallError("transient", "sent something that isn't a model list", scope="provider") from None


# ---------- Anthropic ----------
class AnthropicHTTP:
    """Claude through the Messages API. Paid, so always asked last."""

    def __init__(self, name: str = "anthropic", transport: httpx.BaseTransport | None = None):
        self.name, self.transport = name, transport

    def call(self, model: str, system: str, text: str, max_tokens: int, json_mode: bool, deadline: float) -> Reply:
        body = {"model": model, "max_tokens": max_tokens, "temperature": 0.1, "system": system,
                "messages": [{"role": "user", "content": text}]}
        t0 = time.time()
        try:
            with httpx.Client(base_url=base_url(self.name), timeout=_timeout(deadline), transport=self.transport,
                              headers={"x-api-key": key_for(self.name), "anthropic-version": "2023-06-01"}) as c:
                r = c.post("/messages", json=body)
        except httpx.TimeoutException:
            raise CallError("transient", "timed out") from None
        except httpx.HTTPError as e:
            raise CallError("transient", f"couldn't be reached ({e.__class__.__name__})", scope="provider") from None
        ms = (time.time() - t0) * 1000
        if r.status_code != 200:
            raise classify(self.name, r, model)
        try:
            data = r.json()
            out = "".join(b.get("text", "") for b in data.get("content") or [] if isinstance(b, dict) and b.get("type") == "text")
        except (ValueError, TypeError, AttributeError):
            return Reply("", None, ms, dict(r.headers))
        return Reply(out, "length" if data.get("stop_reason") == "max_tokens" else data.get("stop_reason"), ms, dict(r.headers))

    def models(self, deadline: float) -> list[dict]:
        return []


def client(name: str, transport: httpx.BaseTransport | None = None):
    kind = PROVIDERS[name].kind
    return GeminiNative(name, transport) if kind == "gemini" else AnthropicHTTP(name, transport) if kind == "anthropic" \
        else OpenAIStyle(name, transport)
