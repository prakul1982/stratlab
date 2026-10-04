"""Reading an AI reply: the answer without any reasoning, whether it's complete, and how long a rate limit lasts.

Also the shared error types. An error's text (str(e)) is what users may see, so it never names a provider; the
details for the Admin page are in `e.detail`."""
import json
import re
import time
from email.utils import parsedate_to_datetime
from datetime import datetime


class AIError(Exception):
    """The AI couldn't give a usable answer. str(e) is safe to show users; e.detail is for the Admin page."""

    def __init__(self, msg: str = "The AI couldn't answer just now. Try again in a minute.", detail: str | None = None):
        super().__init__(msg)
        self.detail = detail or msg


class AIBusy(AIError):
    """Quota or rate limit hit, or the service is down: try the next provider."""

    def __init__(self, msg: str = "The AI is busy right now. Try again in a minute.", detail: str | None = None):
        super().__init__(msg, detail)


class AIConfig(AIError):
    """A setting is wrong (bad key, unknown model): skip this provider until it's fixed."""


class RateLimited(AIBusy):
    """A 429 that may say how long to wait."""

    def __init__(self, msg: str = "The AI is busy right now. Try again in a minute.", wait: float | None = None, detail: str | None = None):
        super().__init__(msg, detail)
        self.wait = wait


# ---------- the answer text ----------
def text_of(content) -> str:
    """A message's text: a plain string, or the text parts of a list of parts (some models send those; Mistral's
    "thinking" parts are left out)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [p if isinstance(p, str) else p.get("text") if isinstance(p, dict) and p.get("type", "text") in ("text", "output_text") else None
                 for p in content]
        return "".join(p for p in parts if isinstance(p, str))
    return ""


_THINK = re.compile(r"<(think|thinking|reasoning)>.*?</\1>|◁think▷.*?◁/think▷", flags=re.S | re.I)
_OPEN = re.compile(r"<(think|thinking|reasoning)>|◁think▷", flags=re.I)
_CLOSE = re.compile(r"</(think|thinking|reasoning)>|◁/think▷", flags=re.I)
# where a reasoning model sometimes leaves its final answer inside the reasoning: only after a clear marker
_FINAL = re.compile(r"</think>|<answer>|^\s*\**final answer\**\s*:\**", flags=re.I | re.M)


def strip_thinking(text: str) -> str:
    """The reply without reasoning written inline: <think>…</think> blocks go; a block left open means the model was
    cut off mid-thought (nothing usable after it); a lone </think> (the opening tag was in the prompt template)
    means only what follows it is the answer."""
    out = _THINK.sub("", text or "")
    opened = _OPEN.search(out)
    if opened:
        out = out[:opened.start()]
    closes = list(_CLOSE.finditer(out))
    if closes:
        out = out[closes[-1].end():]
    return out.strip()


def from_reasoning(text: str) -> str:
    """The final answer from a reasoning trace, only when it is clearly marked off (after </think>, inside
    <answer>…</answer>, or after a "Final answer:" line). An unmarked trace may hold a draft, so it is never used."""
    marks = list(_FINAL.finditer(text or ""))
    if not marks:
        return ""
    out = text[marks[-1].end():]
    return out.split("</answer>")[0].strip()


def answer(message: dict) -> str:
    """The answer in an OpenAI-style message. Reasoning models put their thinking in `reasoning` /
    `reasoning_content` and may leave `content` empty: only then, and only a clearly marked final answer there,
    counts (the last resort)."""
    msg = message if isinstance(message, dict) else {}
    out = strip_thinking(text_of(msg.get("content")))
    if not out:
        for k in ("reasoning_content", "reasoning"):
            out = from_reasoning(text_of(msg.get(k)))
            if out:
                break
    return out


# ---------- is the reply usable? ----------
class BadReply(Exception):
    """A reply we can't use: why is "empty", "truncated" or "not_json"."""

    def __init__(self, why: str, text: str = ""):
        super().__init__(why)
        self.why, self.text = why, text


def check(text: str, finish: str | None, want_json: bool) -> str:
    """The reply if it's complete and usable, else BadReply. A reply cut off by the length limit is incomplete even
    when it reads as JSON, unless the JSON object is whole."""
    if not (text or "").strip():
        raise BadReply("truncated" if finish in ("length", "max_tokens", "MAX_TOKENS") else "empty")
    if want_json:
        try:
            extract_json(text)
        except AIError:
            raise BadReply("truncated" if finish in ("length", "max_tokens", "MAX_TOKENS") else "not_json", text) from None
    elif finish in ("length", "max_tokens", "MAX_TOKENS"):
        raise BadReply("truncated", text)
    return text


def extract_json(raw: str) -> dict:
    """The JSON object in a reply, even if it's wrapped in ``` fences or a sentence."""
    text = re.sub(r"^```(?:json)?|```$", "", strip_thinking(raw or ""), flags=re.M).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        a, b = text.find("{"), text.rfind("}")
        if a < 0 or b <= a:
            raise AIError("The AI reply couldn't be read. Try rephrasing the idea.") from None
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


# ---------- rate limits ----------
def duration(value: str, now: float | None = None) -> float | None:
    """Seconds until a reset, from any of the forms providers send: "7.66s", "2m59.56s", "1h", "500ms", "30" (seconds),
    a Unix time in seconds or milliseconds, an ISO time ("2026-10-04T10:00:00Z") or an HTTP date."""
    v = (value or "").strip()
    if not v:
        return None
    now = time.time() if now is None else now
    if re.fullmatch(r"\d+(\.\d+)?", v):
        n = float(v)
        if n > 1e12:                                # Unix time in milliseconds
            return max(0.0, n / 1000 - now)
        if n > 1e9:                                 # Unix time in seconds
            return max(0.0, n - now)
        return n
    parts = re.findall(r"(\d+(?:\.\d+)?)(ms|h|m|s)", v)
    if parts and re.fullmatch(r"(\d+(?:\.\d+)?(ms|h|m|s))+", v):
        mult = {"ms": 0.001, "s": 1, "m": 60, "h": 3600}
        return sum(float(n) * mult[u] for n, u in parts)
    try:
        return max(0.0, datetime.fromisoformat(v.replace("Z", "+00:00")).timestamp() - now)
    except ValueError:
        pass
    try:
        return max(0.0, parsedate_to_datetime(v).timestamp() - now)
    except (TypeError, ValueError, IndexError):
        return None


_RESET_HEADERS = ("retry-after", "x-ratelimit-reset-requests", "x-ratelimit-reset-tokens", "x-ratelimit-reset",
                  "anthropic-ratelimit-requests-reset", "anthropic-ratelimit-tokens-reset",
                  "x-ratelimit-reset-requests-day", "x-ratelimit-reset-tokens-minute")


def wait_from(headers, body: str = "", now: float | None = None) -> float | None:
    """How long a rate limit lasts: Retry-After or the reset headers (the longest one that ran out), or Google's
    retryDelay in the body. None if nothing says."""
    waits = []
    h = {k.lower(): v for k, v in (headers or {}).items()}
    ra = duration(h.get("retry-after", ""), now)
    if ra is not None:
        return ra
    for name in _RESET_HEADERS[1:]:
        if name not in h:
            continue
        rem = h.get(name.replace("reset", "remaining"))
        if rem is not None and rem.strip() not in ("0", "0.0"):
            continue                                # that limit isn't the one that ran out
        d = duration(h[name], now)
        if d is not None:
            waits.append(d)
    m = re.search(r'"retryDelay"\s*:\s*"(\d+(?:\.\d+)?)s"', body or "")
    if m:
        waits.append(float(m.group(1)))
    return max(waits) if waits else None


def remaining(headers) -> dict:
    """What's left of the free allowance, when the provider says: {"requests": n, "tokens": n, "reset": seconds}."""
    h = {k.lower(): v for k, v in (headers or {}).items()}
    out = {}
    for kind in ("requests", "tokens"):
        for name in (f"x-ratelimit-remaining-{kind}", f"anthropic-ratelimit-{kind}-remaining", f"x-ratelimit-remaining-{kind}-day"):
            if name in h:
                try:
                    out[kind] = int(float(h[name]))
                except ValueError:
                    pass
                reset = duration(h.get(name.replace("remaining", "reset"), ""))
                if reset is not None:
                    out[f"{kind}_reset"] = reset
                break
    if "requests" not in out and "x-ratelimit-remaining" in h:
        try:
            out["requests"] = int(float(h["x-ratelimit-remaining"]))
        except ValueError:
            pass
        reset = duration(h.get("x-ratelimit-reset", ""))
        if reset is not None:
            out["requests_reset"] = reset
    return out


def is_daily(body: str) -> bool:
    """A 429 that says the day's free allowance is used up (rather than a per-minute burst)."""
    return bool(re.search(r"per[ -_]?day|perday|daily|free-models-per-day|quota exceeded|exceeded your current quota|RPD|TPD",
                          body or "", re.I))


def too_big(status: int, body: str) -> bool:
    """The prompt is longer than this model takes: not the model's fault, just the wrong model for this request."""
    if status == 413:
        return True
    return status in (400, 422) and bool(re.search(
        r"context.?length|maximum context|context window|too many (input )?tokens|prompt is too long|reduce the length|"
        r"request too large|input.{0,20}too long|exceeds? the (model'?s )?(max|context)", body or "", re.I))
