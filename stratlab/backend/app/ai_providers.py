"""A chain of AI providers for the strategy builder: the first that answers wins.

The task is small (turn one sentence into JSON rules), so fast free-tier models do it
well. Providers with an OpenAI-style API (Groq, Cerebras, OpenRouter) share one client;
Gemini and Anthropic have their own. Each provider is used only when its key is set.

AI_PROVIDERS sets the order, e.g. "groq,gemini". Left as "auto", every provider with a
key is tried in the default order below. Each provider's model can be pinned with
<NAME>_MODEL; "auto" picks a suitable chat model from the provider's own list."""
import json
import re
import time
from dataclasses import dataclass, field

import httpx

from .config import settings

# Two orders, because the jobs differ. Quick jobs (turning one sentence into rules) want the fastest
# answer: Groq first. Research reads are long (several thousand tokens each), and Groq's free tier caps
# tokens per day on its big models, so research leads with the providers that give the most tokens free
# (Cerebras, Mistral) and keeps Groq's allowance for the quick jobs. Anthropic is paid, so always last.
DEFAULT_ORDER = ["groq", "cerebras", "gemini", "mistral", "sambanova", "openrouter", "anthropic"]
RESEARCH_ORDER = ["cerebras", "mistral", "gemini", "sambanova", "groq", "openrouter", "anthropic"]
LONG_ORDER = ["gemini", "mistral", "cerebras", "groq", "sambanova", "openrouter", "anthropic"]   # long documents: biggest context first

OPENAI_STYLE = {
    "groq": {"base": "https://api.groq.com/openai/v1", "label": "Groq"},
    "cerebras": {"base": "https://api.cerebras.ai/v1", "label": "Cerebras"},
    "sambanova": {"base": "https://api.sambanova.ai/v1", "label": "SambaNova"},
    "mistral": {"base": "https://api.mistral.ai/v1", "label": "Mistral"},
    "openrouter": {"base": "https://openrouter.ai/api/v1", "label": "OpenRouter", "free_only": True},
}
LABELS = {**{k: v["label"] for k, v in OPENAI_STYLE.items()}, "gemini": "Google Gemini", "anthropic": "Anthropic"}

# models that aren't general chat models
SKIP = ("whisper", "tts", "guard", "embed", "vision", "audio", "transcrib", "moderation", "image", "playai",
        "compound", "search", "safety", "rerank", "ocr", "codestral", "devstral", "voxtral", "pixtral", "-r1",
        "distill", "thinking", "reasoning")


class AIError(Exception):
    pass


class AIBusy(AIError):
    """Quota or rate limit hit, or the service is down: try the next provider."""


class AIConfig(AIError):
    """A setting is wrong (bad key, unknown model): skip this provider until it's fixed."""


REASONING = ("gptoss", "qwen3", "deepseekr", "magistral", "thinking", "gemma4", "glm4", "kimik2")


def _text(content) -> str:
    """A message's text: a plain string, or the text parts of a list of parts (some models send those)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [p if isinstance(p, str) else p.get("text") if isinstance(p, dict) and p.get("type", "text") in ("text", "output_text") else None
                 for p in content]
        return "".join(p for p in parts if isinstance(p, str))
    return ""


# where a reasoning model sometimes leaves its final answer inside the reasoning: only after a clear marker
_FINAL = re.compile(r"</think>|<answer>|^\s*\**final answer\**\s*:\**", flags=re.I | re.M)


def _from_reasoning(text: str) -> str:
    """The final answer from a reasoning trace, only when it is clearly marked off (after </think>, inside
    <answer>…</answer>, or after a "Final answer:" line). The reasoning itself is never shown to anyone."""
    marks = list(_FINAL.finditer(text or ""))
    if not marks:
        return ""
    out = text[marks[-1].end():]
    return out.split("</answer>")[0].strip()


def _answer(choice: dict) -> str:
    """The reply text without any reasoning a model wrote inline (<think>…</think>, or one left unclosed). Reasoning
    models (qwen-3.8, gemma-4) put their thinking in `reasoning` / `reasoning_content` and may leave `content` empty:
    then only a clearly marked final answer in there counts."""
    msg = choice.get("message") or {}
    out = _text(msg.get("content"))
    out = re.sub(r"<think>.*?</think>", "", out, flags=re.S)
    out = "" if "<think>" in out else out
    if not out.strip():
        for k in ("reasoning_content", "reasoning"):
            out = _from_reasoning(_text(msg.get(k)))
            if out.strip():
                break
    return out


def thinks(model: str) -> bool:
    """A model that reasons before answering (qwen-3.8, gpt-oss, gemma-4…): it needs room for both."""
    flat = re.sub(r"[^a-z0-9]", "", model.lower())
    return any(k in flat for k in REASONING)
COOL_DEFAULT, COOL_MAX = 30.0, 120.0     # seconds a provider is skipped after a rate limit, unless it says otherwise
WAIT_FOR_COOLDOWN = 20.0                 # when every provider is briefly busy, wait this long at most for the first


def _retry_after(r: httpx.Response) -> float | None:
    """How long the provider asked us to wait (Retry-After seconds, or the reset headers some send)."""
    for h in ("retry-after", "x-ratelimit-reset-requests", "x-ratelimit-reset-tokens"):
        v = r.headers.get(h)
        if not v:
            continue
        m = re.match(r"^\s*(\d+(?:\.\d+)?)(ms|s|m)?", v)
        if m:
            n = float(m.group(1))
            return n / 1000 if m.group(2) == "ms" else n * 60 if m.group(2) == "m" else n
    return None


class RateLimited(AIBusy):
    """A 429 that says how long to wait."""
    def __init__(self, msg: str, wait: float | None = None):
        super().__init__(msg)
        self.wait = wait


@dataclass
class Status:
    name: str
    last_ok: float | None = None
    last_error: str | None = None
    model: str | None = None
    cooldown_until: float = 0.0
    models: list[str] = field(default_factory=list)
    models_at: float = 0.0
    quota: bool = False          # the last failure was a rate limit (429): free quota used up for now


_status: dict[str, Status] = {}


def status(name: str) -> Status:
    return _status.setdefault(name, Status(name))


def key_for(name: str) -> str:
    return getattr(settings, f"{name.upper()}_API_KEY", "") or ""


def model_setting(name: str) -> str:
    return (getattr(settings, f"{name.upper()}_MODEL", "") or "auto").strip()


def order(kind: str = "quick") -> list[str]:
    """Providers to try, in order, for a "quick" job (the idea builder) or a "research" one (long reads).
    AI_PROVIDERS / AI_PROVIDERS_RESEARCH override the defaults; research falls back to AI_PROVIDERS."""
    raw = (settings.AI_PROVIDERS or "auto").strip().lower()
    if kind in ("research", "long"):
        own = (settings.AI_PROVIDERS_RESEARCH or "auto").strip().lower()
        raw = own if own != "auto" else raw
    if raw == "auto":
        names = list(LONG_ORDER if kind == "long" else RESEARCH_ORDER if kind == "research" else DEFAULT_ORDER)
        if settings.AI_PROVIDER == "anthropic":  # older setting: Claude first
            names.remove("anthropic")
            names.insert(0, "anthropic")
    else:
        names = [n.strip() for n in raw.split(",") if n.strip() in LABELS]
    return [n for n in names if key_for(n)]


def rank(model_id: str) -> int:
    """Lower is tried first: capable-but-fast models, then small ones as a fallback."""
    m = model_id.lower()
    if any(k in m for k in ("versatile", "70b", "llama-3.3", "llama3.3", "mistral-large", "mistral-medium")):
        return 0
    if any(k in m for k in ("scout", "maverick", "qwen", "mistral", "gemma", "deepseek", "gpt-oss")):
        return 1      # gpt-oss and some qwen models reason before answering: good, but slower and can run dry
    if any(k in m for k in ("instant", "8b", "mini", "flash", "lite", "small")):
        return 2
    return 3


def pick_models(name: str, ids: list[str]) -> list[str]:
    """Chat models worth trying, best first: models that answer straight away before ones that reason first."""
    ids = [i for i in ids if not any(s in i.lower() for s in SKIP)]
    if OPENAI_STYLE[name].get("free_only"):
        ids = [i for i in ids if i.endswith(":free")]
    return sorted(ids, key=lambda i: (thinks(i), rank(i), i))[:4]


def extract_json(raw: str) -> dict:
    """The JSON object in a reply, even if it's wrapped in ``` fences or a sentence."""
    text = re.sub(r"^```(?:json)?|```$", "", (raw or "").strip(), flags=re.M).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        a, b = text.find("{"), text.rfind("}")
        if a < 0 or b <= a:
            raise AIError("The AI reply couldn't be read. Try rephrasing the idea.")
        try:
            data = json.loads(text[a:b + 1])
        except json.JSONDecodeError:
            raise AIError("The AI reply couldn't be read. Try rephrasing the idea.") from None
    if not isinstance(data, dict):
        raise AIError("The AI reply couldn't be read. Try rephrasing the idea.")
    return data


def salvage_items(raw: str, key: str) -> list[dict]:
    """The complete objects in a reply's `key` list, even when the reply was cut off mid-list (long reads hit the
    output limit). Returns [] if nothing complete is there."""
    text = raw or ""
    i = text.find(f'"{key}"')
    if i < 0:
        return []
    i = text.find("[", i)
    out, depth, start, in_str, esc = [], 0, None, False, False
    for j in range(i + 1, len(text)):
        c = text[j]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c == "{":
            if depth == 0:
                start = j
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    obj = json.loads(text[start:j + 1])
                    if isinstance(obj, dict):
                        out.append(obj)
                except json.JSONDecodeError:
                    pass
                start = None
        elif c == "]" and depth == 0:
            break
    return out


class OpenAIStyle:
    def __init__(self, name: str, transport: httpx.BaseTransport | None = None):
        self.name = name
        self.base = OPENAI_STYLE[name]["base"]
        self.transport = transport

    def _client(self) -> httpx.Client:
        headers = {"Authorization": f"Bearer {key_for(self.name)}"}
        if self.name == "openrouter":
            headers.update({"HTTP-Referer": "https://stratlab.studio", "X-Title": "StratLab"})
        return httpx.Client(base_url=self.base, headers=headers, timeout=25, transport=self.transport)

    def models(self) -> list[str]:
        pinned = model_setting(self.name)
        if pinned.lower() != "auto":
            return [pinned]
        st = status(self.name)
        if st.models and time.time() - st.models_at < 6 * 3600:
            return st.models
        with self._client() as c:
            r = c.get("/models")
        if r.status_code in (401, 403):
            raise AIConfig(f"{LABELS[self.name]} rejected the API key.")
        if r.status_code >= 400:
            raise AIBusy(f"{LABELS[self.name]} couldn't list its models ({r.status_code}).")
        try:
            listed = r.json().get("data", [])
        except (ValueError, AttributeError):
            raise AIBusy(f"{LABELS[self.name]} sent something that isn't a model list.") from None
        ids = [m.get("id", "") for m in listed if isinstance(m, dict) and m.get("id")]
        st.models, st.models_at = pick_models(self.name, ids), time.time()
        if not st.models:
            raise AIConfig(f"{LABELS[self.name]} has no suitable free chat model for this key.")
        return st.models

    def _body(self, model: str, system: str, text: str, max_tokens: int) -> dict:
        """The request. A reasoning model gets room to think and still answer, and is asked to think little or not at
        all where the provider allows it: Cerebras takes reasoning_effort ("none" on qwen-3.8 and glm, "low" on
        gpt-oss), SambaNova turns thinking off through the chat template (enable_thinking)."""
        reasoning = thinks(model)
        room = max(max_tokens, 6000 if self.name in ("cerebras", "sambanova") else 4000) if reasoning else max_tokens
        body = {"model": model, "temperature": 0.1, "max_tokens": room,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": text}],
                "response_format": {"type": "json_object"}}
        if reasoning and self.name == "cerebras":
            flat = re.sub(r"[^a-z0-9]", "", model.lower())
            body["reasoning_effort"] = "none" if ("qwen" in flat or "glm" in flat) else "low"
        elif reasoning and self.name in ("groq", "openrouter"):
            body["reasoning_effort"] = "low"          # keep most of the reply for the answer itself
        elif reasoning and self.name == "sambanova":
            body["chat_template_kwargs"] = {"enable_thinking": False}
        return body

    def complete(self, system: str, text: str, max_tokens: int = 1500) -> str:
        last: AIError | None = None
        for model in self.models():
            body = self._body(model, system, text, max_tokens)
            try:
                with self._client() as c:
                    r = c.post("/chat/completions", json=body)
                    if r.status_code == 400 and ("reasoning_effort" in r.text or "chat_template_kwargs" in r.text or "enable_thinking" in r.text):
                        body.pop("reasoning_effort", None)
                        body.pop("chat_template_kwargs", None)
                        r = c.post("/chat/completions", json=body)
                    if r.status_code == 400 and ("response_format" in r.text or "json" in r.text.lower()):
                        body.pop("response_format")   # JSON mode unsupported, or the model's JSON failed validation
                        r = c.post("/chat/completions", json=body)
            except httpx.HTTPError as e:
                raise AIBusy(f"{LABELS[self.name]} couldn't be reached ({e.__class__.__name__}).") from None
            if r.status_code in (401, 403):
                raise AIConfig(f"{LABELS[self.name]} rejected the API key.")
            if r.status_code in (404, 400, 422):
                last = AIConfig(f"{LABELS[self.name]} couldn't use model {model} ({r.status_code}).")
                continue
            if r.status_code == 429 and self.name == "openrouter":
                last = AIBusy(f"{LABELS[self.name]} model {model} is rate limited (429).")
                continue   # free models there have their own limits: try the next one
            if r.status_code == 429:
                raise RateLimited(f"{LABELS[self.name]} is busy or out of free quota (429).", _retry_after(r))
            if r.status_code >= 500:
                raise AIBusy(f"{LABELS[self.name]} is busy or out of free quota ({r.status_code}).")
            try:
                choice = r.json()["choices"][0]
                out = _answer(choice)
            except (KeyError, IndexError, ValueError, TypeError, AttributeError):
                last = AIError(f"{LABELS[self.name]} sent an empty reply ({model}).")
                continue
            if not out.strip():
                # Either the model spent its whole reply reasoning (more room), or JSON mode stopped a reasoning model
                # before it could start (it finishes at once with nothing): once more without JSON mode, with room.
                if choice.get("finish_reason") != "length":
                    body.pop("response_format", None)
                body["max_tokens"] = min(16000, max(8000, body["max_tokens"] * 2))
                try:
                    with self._client() as c:
                        r2 = c.post("/chat/completions", json=body)
                    if r2.status_code == 200:
                        choice = r2.json()["choices"][0]
                        out = _answer(choice)
                except (httpx.HTTPError, KeyError, IndexError, ValueError, TypeError, AttributeError):
                    pass
            if not out.strip():                       # a reasoning model that ran out of room, or a filtered reply
                why = " (ran out of room while reasoning)" if choice.get("finish_reason") == "length" else ""
                last = AIError(f"{LABELS[self.name]} sent an empty reply ({model}){why}.")
                continue
            try:
                extract_json(out)                     # an unreadable reply from one model: try the provider's next one
            except AIError:
                last = AIError(f"{LABELS[self.name]}'s reply couldn't be read ({model}).")
                continue
            status(self.name).model = model
            return out
        raise last or AIError(f"{LABELS[self.name]} had no model to try.")


def complete(system: str, text: str, gemini=None, anthropic=None, transport=None, max_tokens: int = 1500,
             kind: str = "quick") -> str:
    """Ask each configured provider in turn and return the first reply that holds a JSON object."""
    names = order(kind)
    if not names:
        raise AIConfig("No AI provider is set up on the server. Add a free key such as GROQ_API_KEY or GEMINI_API_KEY.")
    for attempt in (0, 1):
        errors, cooling = [], []
        for name in names:
            left = status(name).cooldown_until - time.time()
            if left > 0:
                cooling.append(left)
                errors.append(f"{LABELS[name]}: cooling down after a rate limit ({left:.0f}s)")
                continue
            raw, error = _try(name, system, text, gemini, anthropic, transport, max_tokens)
            if error is None:
                return raw
            errors.append(f"{LABELS[name]}: {error}")
            left = status(name).cooldown_until - time.time()
            if left > 0:
                cooling.append(left)
        # every provider failed: if one is only briefly rate limited, wait for it once rather than give up
        soonest = min(cooling) if cooling else None
        if attempt == 0 and soonest is not None and soonest <= WAIT_FOR_COOLDOWN:
            _sleep(soonest + 0.5)
            continue
        break
    raise AIBusy("None of the AI providers could answer. " + " · ".join(errors))


def _sleep(seconds: float):
    time.sleep(seconds)


def _try(name, system, text, gemini, anthropic, transport, max_tokens: int = 1500) -> tuple[str | None, str | None]:
    """One provider, one request. Returns (reply, None) or (None, error) and records the outcome."""
    st = status(name)
    try:
        if name in OPENAI_STYLE:
            raw = OpenAIStyle(name, transport).complete(system, text, max_tokens)
        elif name == "gemini":
            raw = gemini(system, text, max_tokens=max_tokens)
        else:
            raw = anthropic(system, text, max_tokens=max_tokens)
        extract_json(raw)  # a reply we can't read counts as a failure: try the next provider
    except AIError as e:
        st.last_error, st.quota = str(e), isinstance(e, RateLimited)
        if isinstance(e, AIBusy):                     # the wait the provider asked for, within sensible bounds
            wait = getattr(e, "wait", None)
            st.cooldown_until = time.time() + (min(max(wait, 2.0), COOL_MAX) if wait else COOL_DEFAULT)
        return None, st.last_error
    except Exception as e:  # a provider bug must not break the chain
        st.last_error, st.quota = f"Unexpected error: {e.__class__.__name__}", False
        return None, st.last_error
    st.last_ok, st.last_error, st.cooldown_until, st.quota = time.time(), None, 0.0, False
    return raw, None


QUOTA_TEXT = "Free quota used up for now; it resets on its own."
TEST_SYSTEM = 'Reply with ONLY this JSON object and nothing else: {"ok": true}'


def test_all(gemini=None, anthropic=None, transport=None) -> list[dict]:
    """Send a tiny request to every provider that has a key, ignoring cooldowns, and report each result."""
    out = []
    for name in order():
        t0 = time.time()
        _, error = _try(name, TEST_SYSTEM, "ping", gemini, anthropic, transport)
        quota = error is not None and status(name).quota   # a rate limit is a pause, not a fault
        if quota:
            error = QUOTA_TEXT
        out.append({"name": name, "label": LABELS[name], "ok": error is None, "error": error, "quota": quota,
                    "model": status(name).model if error is None else None, "ms": round((time.time() - t0) * 1000)})
    return out


def health() -> list[dict]:
    names, research = order(), order("research")
    out = []
    for name in DEFAULT_ORDER:
        st = status(name)
        out.append({"name": name, "label": LABELS[name], "configured": bool(key_for(name)), "in_use": name in names,
                    "quick_rank": names.index(name) + 1 if name in names else None,
                    "research_rank": research.index(name) + 1 if name in research else None,
                    "model": st.model, "last_ok": st.last_ok, "last_error": st.last_error, "quota": st.quota})
    return out
