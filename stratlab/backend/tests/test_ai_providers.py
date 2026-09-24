import json

import httpx
import pytest

from app import ai_providers as P
from app.config import settings

GOOD = json.dumps({"entry": [{"l": {"t": "price"}, "op": "gt", "r": {"t": "sma", "p": 50}}], "mentioned": []})


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    for k in ("GROQ_API_KEY", "CEREBRAS_API_KEY", "OPENROUTER_API_KEY", "GEMINI_API_KEY", "ANTHROPIC_API_KEY"):
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
    out = P.complete("s", "t", gemini=lambda s, t: "```json\n" + GOOD + "\n```", transport=fake(["m-70b"], status=429))
    assert "entry" in out
    assert P.status("groq").cooldown_until > 0 and "busy" in P.status("groq").last_error
    # while cooling down, groq isn't even asked
    seen = []
    P.complete("s", "t", gemini=lambda s, t: GOOD, transport=fake(["m-70b"], seen=seen))
    assert seen == []


def test_bad_key_and_unreadable_replies_move_on(monkeypatch):
    monkeypatch.setattr(settings, "GROQ_API_KEY", "q")
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "g")
    with pytest.raises(P.AIBusy) as e:
        P.complete("s", "t", gemini=lambda s, t: "sorry, I can't", transport=fake(["m-70b"], status=401))
    assert "rejected the API key" in str(e.value) and "Google Gemini" in str(e.value)


def test_extract_json_from_chatty_reply():
    assert P.extract_json('Sure! Here it is: {"a": 1} Hope that helps.') == {"a": 1}
    with pytest.raises(P.AIError):
        P.extract_json("[1, 2]")


def test_health_lists_every_provider(monkeypatch):
    monkeypatch.setattr(settings, "GROQ_API_KEY", "q")
    h = {p["name"]: p for p in P.health()}
    assert h["groq"]["configured"] and h["groq"]["in_use"] and not h["gemini"]["configured"]
