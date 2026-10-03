import json

import httpx
import pytest

from app import ai_providers as P
from app.config import settings

GOOD = json.dumps({"entry": [{"l": {"t": "price"}, "op": "gt", "r": {"t": "sma", "p": 50}}], "mentioned": []})


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    for k in ("GROQ_API_KEY", "CEREBRAS_API_KEY", "SAMBANOVA_API_KEY", "MISTRAL_API_KEY", "OPENROUTER_API_KEY", "GEMINI_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.setattr(settings, k, "")
    for k in ("GROQ_MODEL", "CEREBRAS_MODEL", "OPENROUTER_MODEL"):
        monkeypatch.setattr(settings, k, "auto")
    monkeypatch.setattr(settings, "AI_PROVIDERS", "auto")
    monkeypatch.setattr(settings, "AI_PROVIDER", "gemini")
    P._status.clear()


def fake(models, reply=GOOD, status=200, seen=None, reject_json_mode=False):
    def handler(req: httpx.Request):
        if seen is not None:
            seen.append(req)
        if req.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": m} for m in models]})
        body = json.loads(req.content)
        if reject_json_mode and "response_format" in body:
            return httpx.Response(400, text="response_format is not supported")
        if status != 200:
            return httpx.Response(status, json={"error": "nope"})
        return httpx.Response(200, json={"choices": [{"message": {"content": reply}}]})
    return httpx.MockTransport(handler)


def test_no_keys_is_a_clear_error():
    with pytest.raises(P.AIConfig):
        P.complete("s", "t")


def test_order_uses_only_configured_providers(monkeypatch):
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "g")
    monkeypatch.setattr(settings, "GROQ_API_KEY", "q")
    assert P.order() == ["groq", "gemini"]
    monkeypatch.setattr(settings, "AI_PROVIDERS", "gemini, groq, bogus")
    assert P.order() == ["gemini", "groq"]
    monkeypatch.setattr(settings, "AI_PROVIDERS", "auto")
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "a")
    monkeypatch.setattr(settings, "AI_PROVIDER", "anthropic")
    assert P.order()[0] == "anthropic"


def test_auto_model_pick_skips_non_chat_and_prefers_capable_models():
    ids = ["whisper-large-v3", "llama-3.1-8b-instant", "llama-3.3-70b-versatile", "llama-guard-4-12b", "meta-llama/llama-4-scout"]
    assert P.pick_models("groq", ids)[:2] == ["llama-3.3-70b-versatile", "meta-llama/llama-4-scout"]
    assert "whisper-large-v3" not in P.pick_models("groq", ids)
    assert P.pick_models("openrouter", ["a/model", "b/model:free"]) == ["b/model:free"]


def test_groq_answers(monkeypatch):
    monkeypatch.setattr(settings, "GROQ_API_KEY", "q")
    seen = []
    out = P.complete("s", "t", transport=fake(["llama-3.3-70b-versatile"], seen=seen))
    assert json.loads(out)["entry"]
    chat = [r for r in seen if r.url.path.endswith("/chat/completions")][0]
    assert chat.headers["authorization"] == "Bearer q"
    assert json.loads(chat.content)["response_format"] == {"type": "json_object"}
    assert P.status("groq").model == "llama-3.3-70b-versatile"


def test_retries_without_json_mode(monkeypatch):
    monkeypatch.setattr(settings, "CEREBRAS_API_KEY", "c")
    out = P.complete("s", "t", transport=fake(["llama-3.3-70b"], reject_json_mode=True))
    assert "entry" in out


def test_falls_through_to_next_provider_and_cools_down(monkeypatch):
    monkeypatch.setattr(settings, "GROQ_API_KEY", "q")
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "g")
    out = P.complete("s", "t", gemini=lambda s, t, **k: "```json\n" + GOOD + "\n```", transport=fake(["m-70b"], status=429))
    assert "entry" in out
    assert P.status("groq").cooldown_until > 0 and "busy" in P.status("groq").last_error
    # while cooling down, groq isn't even asked
    seen = []
    P.complete("s", "t", gemini=lambda s, t, **k: GOOD, transport=fake(["m-70b"], seen=seen))
    assert seen == []


def test_bad_key_and_unreadable_replies_move_on(monkeypatch):
    monkeypatch.setattr(settings, "GROQ_API_KEY", "q")
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "g")
    with pytest.raises(P.AIBusy) as e:
        P.complete("s", "t", gemini=lambda s, t, **k: "sorry, I can't", transport=fake(["m-70b"], status=401))
    assert "rejected the API key" in str(e.value) and "Google Gemini" in str(e.value)


def test_extract_json_from_chatty_reply():
    assert P.extract_json('Sure! Here it is: {"a": 1} Hope that helps.') == {"a": 1}
    with pytest.raises(P.AIError):
        P.extract_json("[1, 2]")


def test_health_lists_every_provider(monkeypatch):
    monkeypatch.setattr(settings, "GROQ_API_KEY", "q")
    h = {p["name"]: p for p in P.health()}
    assert h["groq"]["configured"] and h["groq"]["in_use"] and not h["gemini"]["configured"]


def test_test_all_reports_every_provider(monkeypatch):
    monkeypatch.setattr(settings, "GROQ_API_KEY", "q")
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "g")

    def gemini(system, text, **k):
        raise P.AIConfig("Google rejected GEMINI_API_KEY.")
    out = P.test_all(gemini=gemini, transport=fake(["llama-3.3-70b-versatile"], reply='{"ok": true}'))
    assert [(r["name"], r["ok"]) for r in out] == [("groq", True), ("gemini", False)]
    assert out[0]["model"] == "llama-3.3-70b-versatile"
    assert out[1]["error"] == "Google rejected GEMINI_API_KEY."


def test_test_all_ignores_cooldown(monkeypatch):
    monkeypatch.setattr(settings, "GROQ_API_KEY", "q")
    P.status("groq").cooldown_until = 1e12
    out = P.test_all(transport=fake(["llama-3.3-70b-versatile"], reply='{"ok": true}'))
    assert out[0]["ok"] and P.status("groq").cooldown_until == 0


def test_json_validation_failure_retries_without_json_mode(monkeypatch):
    monkeypatch.setattr(settings, "GROQ_API_KEY", "q")
    calls = []

    def handler(req):
        if req.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "llama-3.3-70b-versatile"}]})
        body = json.loads(req.content)
        calls.append("response_format" in body)
        if "response_format" in body:
            return httpx.Response(400, json={"error": {"code": "json_validate_failed", "message": "Failed to generate JSON"}})
        return httpx.Response(200, json={"choices": [{"message": {"content": GOOD}}]})
    assert json.loads(P.complete("s", "t", transport=httpx.MockTransport(handler)))["entry"]
    assert calls == [True, False]


def test_openrouter_rate_limit_tries_next_free_model(monkeypatch):
    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", "o")
    tried = []

    def handler(req):
        if req.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "a/one:free"}, {"id": "b/two:free"}]})
        model = json.loads(req.content)["model"]
        tried.append(model)
        if model == "a/one:free":
            return httpx.Response(429, json={"error": "rate limited"})
        return httpx.Response(200, json={"choices": [{"message": {"content": GOOD}}]})
    P.complete("s", "t", transport=httpx.MockTransport(handler))
    assert tried == ["a/one:free", "b/two:free"]


def test_env_forgives_pasting_mistakes(monkeypatch):
    from app.config import _env
    monkeypatch.setenv("X_KEY", ' "gsk_abc" ')
    assert _env("X_KEY") == "gsk_abc"
    monkeypatch.setenv("X_KEY", "X_KEY=gsk_abc")
    assert _env("X_KEY") == "gsk_abc"
    monkeypatch.setenv("X_KEY", "gsk_abc")
    assert _env("X_KEY") == "gsk_abc"


def test_research_uses_its_own_order(monkeypatch):
    for k in ("GROQ", "CEREBRAS", "MISTRAL", "GEMINI"):
        monkeypatch.setattr(settings, f"{k}_API_KEY", "k")
    assert P.order() == ["groq", "cerebras", "gemini", "mistral"]              # quick jobs: fastest first
    assert P.order("research") == ["cerebras", "mistral", "gemini", "groq"]    # long reads: biggest free allowance first
    monkeypatch.setattr(settings, "AI_PROVIDERS", "gemini,groq")
    assert P.order("research") == ["gemini", "groq"]                            # falls back to AI_PROVIDERS
    monkeypatch.setattr(settings, "AI_PROVIDERS_RESEARCH", "mistral")
    assert P.order("research") == ["mistral"] and P.order() == ["gemini", "groq"]
    ranks = {h["name"]: (h["quick_rank"], h["research_rank"]) for h in P.health()}
    assert ranks["mistral"] == (None, 1) and ranks["gemini"] == (1, None)


def test_empty_or_unreadable_reply_tries_the_providers_next_model(monkeypatch):
    monkeypatch.setattr(settings, "CEREBRAS_API_KEY", "c")
    seen = []

    def handler(req: httpx.Request):
        if req.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "gpt-oss-120b"}, {"id": "llama-3.3-70b"}, {"id": "qwen-3-32b"}]})
        body = json.loads(req.content)
        seen.append(body)
        if body["model"] == "llama-3.3-70b":
            return httpx.Response(200, json={"choices": [{"message": {"content": None}, "finish_reason": "length"}]})
        if body["model"] == "gpt-oss-120b":
            return httpx.Response(200, json={"choices": [{"message": {"content": "Sure thing!"}}]})
        return httpx.Response(200, json={"choices": [{"message": {"content": GOOD}}]})
    out = P.complete("s", "t", transport=httpx.MockTransport(handler))
    # the empty reply is asked once more with twice the room, then the next model
    assert "entry" in out and [b["model"] for b in seen] == ["llama-3.3-70b", "llama-3.3-70b", "gpt-oss-120b", "qwen-3-32b"]
    assert seen[1]["max_tokens"] >= 8000
    assert P.thinks("qwen-3.8-27b") and P.thinks("gemma-4-31B-it") and P.thinks("openai/gpt-oss-120b") and not P.thinks("llama-3.3-70b")
    thinker = next(b for b in seen if b["model"] == "gpt-oss-120b")
    assert thinker["reasoning_effort"] == "low" and thinker["max_tokens"] >= 4000     # room to answer after reasoning


def test_a_reasoning_model_that_json_mode_stops_is_asked_again_without_it(monkeypatch):
    # Cerebras qwen-3.8 and SambaNova gemma-4 finish at once with nothing when JSON mode won't let them reason first
    monkeypatch.setattr(settings, "SAMBANOVA_API_KEY", "s")
    seen = []

    def handler(req: httpx.Request):
        if req.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "gemma-4-31B-it"}]})
        body = json.loads(req.content)
        seen.append(body)
        if "response_format" in body:
            return httpx.Response(200, json={"choices": [{"message": {"content": ""}, "finish_reason": "stop"}]})
        return httpx.Response(200, json={"choices": [{"message": {"content": "<think>{a: 1} hmm</think>\n" + GOOD}, "finish_reason": "stop"}]})
    out = P.complete("s", "t", transport=httpx.MockTransport(handler))
    assert "entry" in out and "<think>" not in out and len(seen) == 2 and "response_format" not in seen[1]
    assert P._answer({"message": {"content": "<think>still going"}}) == ""            # cut off mid-thought: nothing


def test_a_short_rate_limit_is_waited_out_instead_of_failing(monkeypatch):
    monkeypatch.setattr(settings, "GROQ_API_KEY", "q")
    calls, slept = [], []
    monkeypatch.setattr(P, "_sleep", lambda s: slept.append(s))

    def handler(req: httpx.Request):
        if req.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "llama-3.3-70b-versatile"}]})
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(429, headers={"retry-after": "3"}, json={"error": "slow down"})
        return httpx.Response(200, json={"choices": [{"message": {"content": GOOD}}]})
    import time as _t
    real = _t.time
    clock = [real()]
    monkeypatch.setattr(P.time, "time", lambda: clock[0])
    monkeypatch.setattr(P, "_sleep", lambda s: (slept.append(s), clock.__setitem__(0, clock[0] + s)))
    out = P.complete("s", "t", transport=httpx.MockTransport(handler))
    assert "entry" in out and len(calls) == 2 and 3 <= slept[0] <= 4      # waited the 3 s asked for, then answered


def test_a_long_rate_limit_still_fails_fast(monkeypatch):
    monkeypatch.setattr(settings, "GROQ_API_KEY", "q")
    monkeypatch.setattr(P, "_sleep", lambda s: (_ for _ in ()).throw(AssertionError("should not wait")))
    t = httpx.MockTransport(lambda req: httpx.Response(200, json={"data": [{"id": "m-70b"}]}) if req.url.path.endswith("/models")
                            else httpx.Response(429, headers={"retry-after": "90"}))
    with pytest.raises(P.AIBusy, match="cooling down|busy"):
        P.complete("s", "t", transport=t)
    assert 80 < P.status("groq").cooldown_until - __import__("time").time() <= 120
