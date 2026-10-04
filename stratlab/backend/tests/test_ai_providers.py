"""The AI layer: every request answered by the best working free model, with fake providers (no network)."""
import json
import time

import httpx
import pytest

from app import ai_clients as C
from app import ai_providers as P
from app import ai_rank as R
from app.ai_catalog import PROVIDERS
from app.config import settings

GOOD = json.dumps({"entry": [{"l": {"t": "price"}, "op": "gt", "r": {"t": "sma", "p": 50}}], "mentioned": []})
KEYS = [p.key_env for p in PROVIDERS.values()] + ["CLOUDFLARE_ACCOUNT_ID"]


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    for k in KEYS:
        monkeypatch.setattr(settings, k, "")
    for p in PROVIDERS.values():
        if p.name != "anthropic":
            monkeypatch.setattr(settings, p.model_env, "auto")
    monkeypatch.setattr(settings, "AI_PROVIDERS", "auto")
    monkeypatch.setattr(settings, "AI_PROVIDERS_RESEARCH", "auto")
    monkeypatch.setattr(settings, "AI_PROVIDER", "gemini")
    monkeypatch.setattr(P, "_sleep", lambda s: None)


def keys(monkeypatch, *names):
    for n in names:
        monkeypatch.setattr(settings, PROVIDERS[n].key_env, "k-" + n)


def chat(content=GOOD, finish="stop", **msg):
    return httpx.Response(200, json={"choices": [{"message": {"content": content, **msg}, "finish_reason": finish}]})


def fake(models=("m-70b",), reply=GOOD, status=200, seen=None, reject_json_mode=False, headers=None):
    """An OpenAI-style provider: lists `models`, answers every chat with `reply` (or the error `status`)."""
    def handler(req: httpx.Request):
        if seen is not None:
            seen.append(req)
        if req.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": m} for m in models]})
        body = json.loads(req.content)
        if reject_json_mode and "response_format" in body:
            return httpx.Response(400, text="response_format is not supported")
        if status != 200:
            return httpx.Response(status, headers=headers or {}, json={"error": {"message": "nope"}})
        return httpx.Response(200, headers=headers or {}, json={"choices": [{"message": {"content": reply}, "finish_reason": "stop"}]})
    return httpx.MockTransport(handler)


def bodies(seen):
    return [json.loads(r.content) for r in seen if r.url.path.endswith("/chat/completions")]


# ---------- set-up and order ----------
def test_no_keys_is_a_clear_error_that_names_no_provider():
    with pytest.raises(P.AIConfig) as e:
        P.complete("s", "t")
    assert str(e.value) == "The AI isn't set up on the server yet." and "GROQ_API_KEY" in e.value.detail


def test_order_uses_only_configured_providers(monkeypatch):
    keys(monkeypatch, "gemini", "groq")
    assert P.order() == ["groq", "gemini"]
    monkeypatch.setattr(settings, "AI_PROVIDERS", "gemini, groq, bogus")
    assert P.order() == ["gemini", "groq"]
    monkeypatch.setattr(settings, "AI_PROVIDERS", "auto")
    keys(monkeypatch, "anthropic")
    assert P.order()[-1] == "anthropic"                         # paid: always last
    monkeypatch.setattr(settings, "AI_PROVIDER", "anthropic")   # the older setting puts Claude first
    assert P.order()[0] == "anthropic"


def test_research_uses_its_own_order(monkeypatch):
    keys(monkeypatch, "groq", "cerebras", "mistral", "gemini")
    assert P.order()[0] == "groq"                                 # quick jobs: fastest first
    assert P.order("research")[-1] == "groq"                      # long reads keep Groq's small daily token cap
    monkeypatch.setattr(settings, "AI_PROVIDERS", "gemini,groq")
    assert P.order("research") == ["gemini", "groq"]              # falls back to AI_PROVIDERS
    monkeypatch.setattr(settings, "AI_PROVIDERS_RESEARCH", "mistral")
    assert P.order("research") == ["mistral"] and P.order() == ["gemini", "groq"]
    ranks = {h["name"]: (h["quick_rank"], h["research_rank"]) for h in P.health()}
    assert ranks["mistral"] == (None, 1) and ranks["gemini"] == (1, None)


def test_prototype_only_providers_come_after_every_production_one(monkeypatch):
    keys(monkeypatch, "github", "nvidia", "huggingface", "anthropic")
    o = P.order()
    assert o[0] == "huggingface" and set(o[1:3]) == {"github", "nvidia"} and o[3] == "anthropic"


def test_cloudflare_needs_its_account_id_too(monkeypatch):
    keys(monkeypatch, "cloudflare")
    assert P.order() == []
    monkeypatch.setattr(settings, "CLOUDFLARE_ACCOUNT_ID", "acc1")
    seen = []
    assert "entry" in P.complete("s", "t", transport=fake(seen=seen))
    assert seen[0].url.path == "/client/v4/accounts/acc1/ai/v1/chat/completions"


def test_env_forgives_pasting_mistakes(monkeypatch):
    from app.config import _env
    monkeypatch.setenv("X_KEY", ' "gsk_abc" ')
    assert _env("X_KEY") == "gsk_abc"
    monkeypatch.setenv("X_KEY", "X_KEY=gsk_abc")
    assert _env("X_KEY") == "gsk_abc"


# ---------- calling ----------
def test_groq_answers_with_its_best_default_model(monkeypatch):
    keys(monkeypatch, "groq")
    seen = []
    out = P.complete("s", "t", transport=fake(seen=seen))
    assert json.loads(out)["entry"]
    assert seen[0].headers["authorization"] == "Bearer k-groq" and seen[0].url.path.endswith("/chat/completions")
    body = bodies(seen)[0]
    assert body["response_format"] == {"type": "json_object"} and body["model"] == "llama-3.3-70b-versatile"
    assert P.status("groq").model == "llama-3.3-70b-versatile"


def test_retries_without_json_mode(monkeypatch):
    keys(monkeypatch, "cerebras")
    assert "entry" in P.complete("s", "t", transport=fake(reject_json_mode=True))


def test_json_validation_failure_retries_without_json_mode(monkeypatch):
    keys(monkeypatch, "groq")
    calls = []

    def handler(req):
        body = json.loads(req.content)
        calls.append("response_format" in body)
        if "response_format" in body:
            return httpx.Response(400, json={"error": {"code": "json_validate_failed", "message": "Failed to generate JSON"}})
        return chat()
    assert json.loads(P.complete("s", "t", transport=httpx.MockTransport(handler)))["entry"]
    assert calls == [True, False]


def test_falls_through_to_next_provider_and_cools_down(monkeypatch):
    keys(monkeypatch, "cerebras", "gemini")
    monkeypatch.setattr(settings, "AI_PROVIDERS", "cerebras,gemini")
    out = P.complete("s", "t", gemini=lambda s, t, **k: "```json\n" + GOOD + "\n```", transport=fake(status=429))
    assert "entry" in out
    assert P.status("cerebras").cooldown_until > time.time() and "rate limited" in P.status("cerebras").last_error
    seen = []                                                    # while cooling down, Cerebras isn't even asked
    P.complete("s", "t2", gemini=lambda s, t, **k: GOOD, transport=fake(seen=seen))
    assert seen == []


def test_bad_keys_everywhere_give_a_busy_error_without_provider_names(monkeypatch):
    keys(monkeypatch, "groq", "gemini")
    with pytest.raises(P.AIBusy) as e:
        P.complete("s", "t", gemini=lambda s, t, **k: "sorry, I can't", transport=fake(status=401))
    assert "Groq" not in str(e.value) and "Gemini" not in str(e.value)
    assert "rejected the key" in e.value.detail and "Google Gemini" in e.value.detail
    assert P.status("groq").config_error and P.last_failure["detail"].startswith("No AI model could answer")


def test_openrouter_rate_limit_on_one_free_model_tries_the_next(monkeypatch):
    keys(monkeypatch, "openrouter")
    tried = []

    def handler(req):
        model = json.loads(req.content)["model"]
        tried.append(model)
        if model == "meta-llama/llama-3.3-70b-instruct:free":
            return httpx.Response(429, json={"error": {"message": "rate limited"}})
        return chat()
    P.complete("s", "t", transport=httpx.MockTransport(handler))
    assert tried == ["meta-llama/llama-3.3-70b-instruct:free", "openai/gpt-oss-120b:free"]


def test_an_unknown_model_is_skipped_for_hours_and_the_next_one_asked(monkeypatch):
    keys(monkeypatch, "groq")
    tried = []

    def handler(req):
        model = json.loads(req.content)["model"]
        tried.append(model)
        if model == "llama-3.3-70b-versatile":
            return httpx.Response(404, json={"error": {"message": "model decommissioned"}})
        return chat()
    P.complete("s", "t", transport=httpx.MockTransport(handler))
    assert tried == ["llama-3.3-70b-versatile", "openai/gpt-oss-120b"]
    assert R.ready("groq", "llama-3.3-70b-versatile") > 5 * 3600


def test_a_prompt_too_long_for_a_model_moves_on_without_blaming_it(monkeypatch):
    keys(monkeypatch, "groq")
    calls = []

    def handler(req):
        calls.append(json.loads(req.content)["model"])
        if len(calls) == 1:
            return httpx.Response(413, json={"error": {"message": "Request too large for model"}})
        return chat()
    P.complete("s", "t", transport=httpx.MockTransport(handler))
    assert len(calls) == 2 and R.ready("groq", calls[0]) == 0 and not R.stats("groq", calls[0]).live


def test_long_documents_skip_models_whose_context_is_too_small(monkeypatch):
    keys(monkeypatch, "github", "gemini")
    doc = "x" * 60000                                             # ~17,000 tokens: more than GitHub's 8,000
    assert [n for n, _ in P.plan("long", int(len(doc) / 3.5))] == ["gemini"] * 3
    assert "github" in [n for n, _ in P.plan("long", 500)]


# ---------- reasoning models ----------
def test_empty_reply_gets_one_second_chance_with_more_room_then_the_next_model(monkeypatch):
    keys(monkeypatch, "cerebras")
    seen = []

    def handler(req: httpx.Request):
        body = json.loads(req.content)
        seen.append(body)
        if body["model"] == "llama-3.3-70b":
            return chat(None, "length")
        if body["model"] == "gpt-oss-120b":
            return chat("Sure thing!")
        return chat()
    out = P.complete("s", "t", transport=httpx.MockTransport(handler))
    assert "entry" in out and [b["model"] for b in seen] == ["llama-3.3-70b", "llama-3.3-70b", "gpt-oss-120b", "qwen-3-235b-a22b-instruct-2507"]
    assert seen[1]["max_tokens"] >= 8000                          # it ran out of room while reasoning: more room
    thinker = next(b for b in seen if b["model"] == "gpt-oss-120b")
    assert thinker["reasoning_effort"] == "low" and thinker["max_tokens"] >= 4000


def test_a_reasoning_model_that_json_mode_stops_is_asked_again_without_it(monkeypatch):
    # Cerebras qwen-3.8 and SambaNova gemma-4 finish at once with nothing when JSON mode won't let them reason first
    keys(monkeypatch, "sambanova")
    R.pin("sambanova", "gemma-4-31B-it")
    seen = []

    def handler(req: httpx.Request):
        body = json.loads(req.content)
        seen.append(body)
        if "response_format" in body:
            return chat("", "stop")
        return chat("<think>{a: 1} hmm</think>\n" + GOOD)
    out = P.complete("s", "t", transport=httpx.MockTransport(handler))
    assert "entry" in out and "<think>" not in out and len(seen) == 2 and "response_format" not in seen[1]


@pytest.mark.parametrize("message", [
    {"content": GOOD},                                                                          # a plain string
    {"content": [{"type": "text", "text": GOOD[:20]}, {"type": "text", "text": GOOD[20:]}]},    # a list of parts
    {"content": [{"type": "thinking", "thinking": [{"text": "hmm {\"x\": 1}"}]}, {"type": "text", "text": GOOD}]},  # Mistral
    {"content": "<think>draft {\"a\": 1}</think>" + GOOD},                                      # inline <think>
    {"content": "<thinking>maybe</thinking>\n" + GOOD},
    {"content": "the template opened the thought, so only its end shows</think>\n" + GOOD},    # a lone </think>
    {"content": "◁think▷kimi style◁/think▷" + GOOD},
    {"content": None, "reasoning": "The user wants JSON. Let me write it.\nFinal answer: " + GOOD},
    {"content": "", "reasoning_content": "thinking about rules</think>" + GOOD},
    {"content": None, "reasoning": "hmm <answer>" + GOOD + "</answer>"},
])
def test_every_reply_shape_reasoning_models_send_is_read(monkeypatch, message):
    keys(monkeypatch, "cerebras")
    out = P.complete("s", "t", transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"choices": [{"message": message, "finish_reason": "stop"}]})))
    assert json.loads(out)["entry"]


def test_raw_reasoning_without_a_marked_answer_is_never_used(monkeypatch):
    # an unmarked trace may hold a draft JSON object: it must not be passed off as the answer
    keys(monkeypatch, "cerebras")
    with pytest.raises(P.AIBusy) as e:
        P.complete("s", "t", transport=httpx.MockTransport(lambda r: chat(None, reasoning="Maybe " + GOOD + " or not.")))
    assert "empty reply" in e.value.detail
    assert P._answer({"message": {"content": [{"type": "image_url", "image_url": {}}]}}) == ""
    assert P._answer({"message": {"content": {"odd": 1}}}) == ""
    assert P._answer({"message": {"content": "<think>still going " + GOOD}}) == ""     # cut off mid-thought


def test_reasoning_models_are_asked_to_think_little_with_room_to_answer():
    cer = C.body_for("cerebras", "qwen-3.8-27b", "s", "t", 1500, True)
    assert cer["reasoning_effort"] == "none" and cer["max_tokens"] >= 3000 and cer["messages"][1]["content"].endswith("/no_think")
    assert C.body_for("groq", "openai/gpt-oss-120b", "s", "t", 1500, True)["reasoning_effort"] == "low"
    sam = C.body_for("sambanova", "gemma-4-31B-it", "s", "t", 1500, True)
    assert sam["chat_template_kwargs"] == {"enable_thinking": False} and sam["max_tokens"] >= 3000
    assert C.body_for("nvidia", "deepseek-ai/deepseek-v3.1-terminus-reasoning", "s", "t", 100, True)["chat_template_kwargs"] == {"thinking": False}
    assert C.body_for("zai", "glm-4.7-flash", "s", "t", 1500, True)["thinking"] == {"type": "disabled"}
    assert C.body_for("openrouter", "minimax/minimax-m3:free", "s", "t", 1500, True)["reasoning"] == {"effort": "low", "exclude": True}
    assert C.body_for("nvidia", "nvidia/llama-3.3-nemotron-super-49b-v1.5", "s", "t", 1500, True)["messages"][0]["content"].startswith("/no_think")
    assert C.body_for("github", "openai/o4-mini", "s", "t", 1500, True)["max_tokens"] <= 4000     # GitHub's reply cap
    plain = C.body_for("sambanova", "Meta-Llama-3.3-70B-Instruct", "s", "t", 1500, True)
    assert "chat_template_kwargs" not in plain and plain["max_tokens"] == 1500 and plain["messages"][1]["content"] == "t"


def test_a_provider_that_refuses_a_setting_is_asked_without_it(monkeypatch):
    keys(monkeypatch, "github")
    R.pin("github", "openai/o4-mini")
    seen = []

    def handler(req: httpx.Request):
        body = json.loads(req.content)
        seen.append(body)
        if "max_tokens" in body:
            return httpx.Response(400, json={"error": {"message": "Unsupported parameter: 'max_tokens'. Use 'max_completion_tokens' instead."}})
        if "temperature" in body:
            return httpx.Response(400, json={"error": {"message": "Unsupported value: 'temperature' does not support 0.1"}})
        if "reasoning_effort" in body:
            return httpx.Response(400, json={"error": {"message": "unknown field reasoning_effort"}})
        return chat()
    assert "entry" in P.complete("s", "t", transport=httpx.MockTransport(handler))
    assert set(seen[-1]) >= {"max_completion_tokens"} and "temperature" not in seen[-1] and "reasoning_effort" not in seen[-1]
    assert C.repair({"max_tokens": 9000}, "max_tokens must be less than or equal to `8192`", set()) is True


# ---------- rate limits and quota ----------
def test_rate_limit_headers_are_read_in_every_form():
    now = 1_800_000_000.0
    assert C.wait_from({"retry-after": "3"}, now=now) == 3
    assert C.wait_from({"x-ratelimit-remaining-tokens": "0", "x-ratelimit-reset-tokens": "1m30.5s",
                        "x-ratelimit-remaining-requests": "999", "x-ratelimit-reset-requests": "2s"}, now=now) == 90.5
    assert C.wait_from({"x-ratelimit-reset": str(int(now + 40))}, now=now) == 40            # a Unix time
    assert C.wait_from({"x-ratelimit-reset": str(int((now + 40) * 1000))}, now=now) == 40   # in milliseconds
    assert C.wait_from({"anthropic-ratelimit-requests-remaining": "0",
                        "anthropic-ratelimit-requests-reset": "2027-01-15T08:00:20Z"}, now=1_800_000_000) > 0
    assert C.wait_from({}, '{"error": {"details": [{"retryDelay": "13s"}]}}') == 13          # Google's way
    assert C.wait_from({"retry-after": "Wed, 21 Oct 2099 07:28:00 GMT"}) > 1e9
    assert C.wait_from({}) is None
    from app.ai_reply import duration
    assert duration("500ms") == 0.5 and duration("1h2m") == 3720 and duration("soon") is None


def test_a_429_with_reset_headers_skips_just_that_model_until_the_reset(monkeypatch):
    keys(monkeypatch, "groq")                                     # Groq's limits are per model
    tried = []

    def handler(req):
        model = json.loads(req.content)["model"]
        tried.append(model)
        if model == "llama-3.3-70b-versatile":
            return httpx.Response(429, headers={"x-ratelimit-remaining-tokens": "0", "x-ratelimit-reset-tokens": "2m"},
                                  json={"error": {"message": "Rate limit reached on tokens per minute (TPM)"}})
        return chat()
    P.complete("s", "t", transport=httpx.MockTransport(handler))
    assert tried == ["llama-3.3-70b-versatile", "openai/gpt-oss-120b"]
    assert 100 < R.ready("groq", "llama-3.3-70b-versatile") <= 120 and R.ready("groq", "openai/gpt-oss-120b") == 0


def test_a_used_up_daily_quota_reads_as_a_pause_with_its_reset_time(monkeypatch):
    keys(monkeypatch, "mistral")
    res = P.test_all(transport=fake(status=429, headers={"retry-after": "7200"}))
    assert res[0]["quota"] and not res[0]["ok"] and res[0]["error"] == P.QUOTA_TEXT
    assert next(h for h in P.health() if h["name"] == "mistral")["quota"]
    view = next(p for p in P.admin_view()["providers"] if p["name"] == "mistral")
    assert view["state"] == "warn" and view["quota"]["limited"] and 7000 < view["quota"]["reset_at"] - time.time() <= 7200
    P.reset()
    other = P.test_all(transport=fake(status=401))
    assert not other[0]["quota"] and "rejected" in other[0]["error"]


def test_when_the_provider_says_nothing_is_left_it_is_not_asked_until_the_reset(monkeypatch):
    keys(monkeypatch, "mistral")
    seen = []
    t = fake(seen=seen, headers={"x-ratelimit-remaining-requests": "0", "x-ratelimit-reset-requests": "5m"})
    P.complete("s", "t", transport=t)
    assert 290 < P.status("mistral").cooldown_until - time.time() <= 300
    with pytest.raises(P.AIBusy):
        P.complete("s", "another question", transport=t)
    assert len(seen) == 1
    assert next(p for p in P.admin_view()["providers"] if p["name"] == "mistral")["quota"]["remaining"] == {"requests": 0}


def test_a_short_rate_limit_is_waited_out_instead_of_failing(monkeypatch):
    keys(monkeypatch, "mistral")
    calls, slept = [], []
    clock = [time.time()]
    monkeypatch.setattr(P.time, "time", lambda: clock[0])
    monkeypatch.setattr(P, "_sleep", lambda s: (slept.append(s), clock.__setitem__(0, clock[0] + s)))

    def handler(req: httpx.Request):
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(429, headers={"retry-after": "3"}, json={"error": "slow down"})
        return chat()
    out = P.complete("s", "t", transport=httpx.MockTransport(handler))
    assert "entry" in out and len(calls) == 2 and 3 <= slept[0] <= 4      # waited the 3 s asked for, then answered


def test_a_long_rate_limit_fails_fast(monkeypatch):
    keys(monkeypatch, "mistral")
    monkeypatch.setattr(P, "_sleep", lambda s: (_ for _ in ()).throw(AssertionError("should not wait")))
    with pytest.raises(P.AIBusy):
        P.complete("s", "t", transport=fake(status=429, headers={"retry-after": "90"}))
    assert 80 < P.status("mistral").cooldown_until - time.time() <= 90


# ---------- time budget, timeouts and circuit breakers ----------
def test_timeouts_move_on_and_the_time_budget_caps_the_wait(monkeypatch):
    keys(monkeypatch, "groq", "cerebras", "mistral", "sambanova")
    clock = [time.time()]
    monkeypatch.setattr(P.time, "time", lambda: clock[0])
    calls = []

    def slow(req):
        calls.append(req.url.host)
        clock[0] += min(14, req.extensions["timeout"]["read"])   # each provider takes 14 s (or until the time-out)
        raise httpx.ReadTimeout("slow", request=req)
    t0 = clock[0]
    with pytest.raises(P.AIBusy) as e:
        P.complete("s", "t", transport=httpx.MockTransport(slow))
    assert clock[0] - t0 <= P.BUDGET["quick"] and 1 < len(calls) <= 3 and "timed out" in e.value.detail


def test_a_model_that_keeps_failing_is_skipped_and_a_success_closes_its_breaker(monkeypatch):
    keys(monkeypatch, "mistral")
    R.pin("mistral", "mistral-small-latest")
    state = {"reply": ""}
    t = httpx.MockTransport(lambda r: chat(state["reply"], "stop"))
    for q in ("a", "b"):
        with pytest.raises(P.AIBusy):
            P.complete("s", q, transport=t)
    assert R.ready("mistral", "mistral-small-latest") > 60            # open after two empty answers in a row
    s = R.stats("mistral", "mistral-small-latest")
    s.open_until = 0                                                  # time passes: half-open, one more try
    state["reply"] = GOOD
    assert "entry" in P.complete("s", "c", transport=t)
    assert s.fails == 0 and R.ready("mistral", "mistral-small-latest") == 0


def test_a_provider_that_keeps_erroring_is_paused(monkeypatch):
    keys(monkeypatch, "mistral")
    for q in ("a", "b", "c"):
        with pytest.raises(P.AIBusy):
            P.complete("s", q, transport=fake(status=503))
    assert P.status("mistral").cooldown_until > time.time()


# ---------- the cache ----------
def test_the_same_question_is_answered_once_per_job(monkeypatch):
    keys(monkeypatch, "mistral")
    seen = []
    t = fake(seen=seen)
    a = P.complete("sys", "same question", transport=t)
    b = P.complete("sys", "same question", transport=t)
    assert a == b and len(seen) == 1 and P.cache.hits == 1
    P.complete("sys", "same question", transport=t, kind="research")      # a different job: its own answer
    P.complete("sys", "same question", transport=t, use_cache=False)
    assert len(seen) == 3
    key = P.AnswerCache.key("quick", "sys", "same question", 1500, True)
    P.cache.items[key] = (time.time() - 1, "old")                          # expired
    P.complete("sys", "same question", transport=t)
    assert len(seen) == 4


def test_failures_are_never_cached(monkeypatch):
    keys(monkeypatch, "mistral")
    with pytest.raises(P.AIBusy):
        P.complete("s", "q", transport=fake(reply="not json"))
    assert not P.cache.items


# ---------- discovering and measuring models ----------
def test_model_lists_are_filtered_to_usable_english_chat_models():
    listed = [{"id": m} for m in ("allam-2-7b", "llama-3.3-70b-versatile", "whisper-large-v3", "meta-llama/llama-guard-4-12b",
                                  "llama-3.1-8b-instant", "groq/compound-mini", "playai-tts", "gemma-3n-e4b-it",
                                  "deepseek-r1-distill-llama-70b", "nomic-embed-text", "qwen-2.5-coder-32b", "openai/gpt-oss-120b",
                                  "moonshotai/kimi-k2-instruct")]
    cands, skipped, _ = R.candidates("groq", listed)
    assert cands[:2] == ["llama-3.3-70b-versatile", "openai/gpt-oss-120b"]       # curated defaults still listed: first
    assert set(cands) == {"llama-3.3-70b-versatile", "openai/gpt-oss-120b", "llama-3.1-8b-instant", "moonshotai/kimi-k2-instruct"}
    assert skipped == {"not English-first": 1, "not a chat model": 5, "too small": 1, "thinks too long": 1, "specialist": 1}
    assert R.candidates("openrouter", [{"id": "a/model"}, {"id": "b/model-70b:free"}])[0] == ["b/model-70b:free"]
    assert R.candidates("zai", [{"id": "glm-4.7-flash"}, {"id": "glm-4.7-flashx"}, {"id": "glm-4.7"}, {"id": "glm-4.6v-flash"}])[0] == ["glm-4.7-flash"]
    assert R.candidates("gemini", [{"id": "gemini-2.5-pro"}, {"id": "gemini-3.8-flash"}, {"id": "gemini-2.5-flash-native-audio"}])[0] == ["gemini-3.8-flash"]
    from app.ai_catalog import size_b
    assert (size_b("qwen3-30b-a3b"), size_b("Meta-Llama-3.3-70B-Instruct"), size_b("gemma-3n-e4b-it"), size_b("gpt-4.1")) == (30, 70, 4, None)


@pytest.mark.parametrize("provider,model,why", [
    ("mistral", "mistral-ocr-latest", "not a chat model"), ("mistral", "voxtral-small-latest", "not a chat model"),
    ("mistral", "ministral-3b-latest", "too small"), ("mistral", "pixtral-large-latest", "not a chat model"),
    ("mistral", "codestral-latest", "specialist"), ("mistral", "mistral-small-latest", None), ("mistral", "ministral-8b-latest", None),
    ("sambanova", "E5-Mistral-7B-Instruct", "not a chat model"), ("sambanova", "DeepSeek-R1-0528", "thinks too long"),
    ("sambanova", "Meta-Llama-3.3-70B-Instruct", None), ("groq", "openai/gpt-oss-safeguard-20b", "not a chat model"),
    ("gemini", "gemini-2.5-flash-preview-tts", "not for this job"), ("gemini", "gemini-embedding-001", "not a chat model"),
    ("gemini", "gemma-3-1b-it", "too small"), ("gemini", "gemma-3-27b-it", None),
    ("openrouter", "qwen/qwen2.5-vl-72b-instruct:free", "not a chat model"), ("nvidia", "nvidia/llama-3.1-nemoguard-8b-content-safety", "not a chat model"),
    ("cloudflare", "@cf/meta/llama-3.3-70b-instruct-fp8-fast", None), ("cloudflare", "@cf/baai/bge-m3", "not a chat model"),
])
def test_one_model_at_a_time(provider, model, why):
    from app.ai_catalog import unusable
    assert unusable(provider, model) == why


def test_every_providers_model_list_format_is_read():
    assert C.parse_models({"data": [{"id": "a", "context_window": 131072}, {"id": "b", "context_length": 8192}]}) == \
        [{"id": "a", "ctx": 131072}, {"id": "b", "ctx": 8192}]
    cf = {"result": [{"name": "@cf/meta/llama-3.3-70b-instruct-fp8-fast", "properties": [{"property_id": "context_window", "value": "24000"}]}]}
    assert C.parse_models(cf) == [{"id": "@cf/meta/llama-3.3-70b-instruct-fp8-fast", "ctx": 24000}]
    gm = {"models": [{"name": "models/gemini-3.8-flash", "supportedGenerationMethods": ["generateContent"], "inputTokenLimit": 1048576},
                     {"name": "models/text-embedding-004", "supportedGenerationMethods": ["embedContent"]}]}
    assert C.parse_models(gm) == [{"id": "gemini-3.8-flash", "ctx": 1048576}]
    gh = [{"id": "openai/gpt-4.1-mini", "supported_output_modalities": ["text"], "limits": {"max_input_tokens": 8000}},
          {"id": "openai/text-embedding-3-small", "supported_output_modalities": ["embeddings"]}]
    assert C.parse_models(gh) == [{"id": "openai/gpt-4.1-mini", "ctx": 8000}]
    hf = {"data": [{"id": "meta-llama/Llama-3.3-70B-Instruct", "providers": [{"provider": "x", "context_length": 32768}, {"provider": "y", "context_length": 131072}]}]}
    assert C.parse_models(hf)[0]["ctx"] == 131072
    assert C.parse_models({"data": [{"id": "v/embed", "type": "embedding"}, {"id": "openai/gpt-oss-120b", "type": "language"}]}) == [{"id": "openai/gpt-oss-120b", "ctx": None}]


def _measured_provider(answers: dict, listed: list[str], seen: list | None = None):
    """A provider whose models answer the fixed test as `answers` says: "good", "slow", "wrong", "empty" or "404"."""
    def handler(req: httpx.Request):
        if req.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": m, "context_window": 32000} for m in listed]})
        body = json.loads(req.content)
        if seen is not None:
            seen.append(body["model"])
        kind = answers.get(body["model"], "good")
        if kind == "404":
            return httpx.Response(404, json={"error": {"message": "no such model"}})
        if kind == "empty":
            return chat("")
        sys_text = body["messages"][0]["content"]
        if "17 + 25" in sys_text:
            reply = {"ok": True, "sum": 42 if kind != "wrong" else 41, "word": "blue"}
        else:
            reply = {"answer": "Revenue is the money a company earns from selling its goods and services.",
                     "term": "debt" if kind != "wrong" else "equity"}
        if kind == "slow":
            time.sleep(0.05)
        return chat(json.dumps(reply))
    return httpx.MockTransport(handler)


def test_rerank_measures_the_models_keeps_the_best_and_stores_them(monkeypatch):
    keys(monkeypatch, "groq")
    listed = ["llama-3.3-70b-versatile", "openai/gpt-oss-120b", "allam-2-7b", "llama-3.1-8b-instant", "qwen/qwen3-32b", "whisper-large-v3"]
    t = _measured_provider({"llama-3.3-70b-versatile": "wrong", "openai/gpt-oss-120b": "empty", "qwen/qwen3-32b": "slow"}, listed)
    P.rerank(["groq"], transport=t, wait=True)
    st = P.status("groq")
    assert st.order == ["qwen/qwen3-32b", "llama-3.1-8b-instant"]          # measured: the ones that answered right
    assert st.discovered == 6 and st.skipped == {"not English-first": 1, "not a chat model": 1}
    assert R.stats("groq", "llama-3.3-70b-versatile").probe_error == "wrong answer to the test question"
    assert R.stats("groq", "openai/gpt-oss-120b").probe_error == "empty reply"
    assert "allam-2-7b" not in st.models or not R.stats("groq", "allam-2-7b").probe_tries
    assert P.plan("quick")[0] == ("groq", "qwen/qwen3-32b")
    stored = json.loads(R.STORE.data["ai:rank:groq"])
    assert stored["order"] == st.order and stored["models"]["qwen/qwen3-32b"]["probe_ok"] == 2
    R._status.clear()                                                        # a restart: what was learnt comes back
    assert R.in_use("groq") == ["qwen/qwen3-32b", "llama-3.1-8b-instant"] and R.stats("groq", "qwen/qwen3-32b").ctx == 32000


def test_rerank_stops_early_when_the_key_is_rejected(monkeypatch):
    keys(monkeypatch, "groq")
    t = httpx.MockTransport(lambda r: httpx.Response(401, json={"error": {"message": "Invalid API Key"}}))
    P.rerank(["groq"], transport=t, wait=True)
    st = P.status("groq")
    assert st.config_error and "rejected the key" in st.rank_error and st.order == []
    assert R.in_use("groq")[0] == "llama-3.3-70b-versatile"                 # a cold start is never empty


def test_scores_favour_measured_success_then_speed_and_route_by_job(monkeypatch):
    keys(monkeypatch, "groq", "mistral", "github")
    fast, strong = R.stats("groq", "llama-3.1-8b-instant"), R.stats("mistral", "mistral-large-latest")
    fast.probe_ok, fast.probe_tries, fast.probe_ms, fast.probe_json, fast.probe_len = 2, 2, [300, 400], 2, 2
    strong.probe_ok, strong.probe_tries, strong.probe_ms, strong.probe_json, strong.probe_len = 2, 2, [2500, 2600], 2, 2
    P.status("groq").order, P.status("mistral").order = ["llama-3.1-8b-instant"], ["mistral-large-latest"]
    assert P.plan("quick")[0] == ("groq", "llama-3.1-8b-instant")          # quick jobs: the fast one
    assert P.plan("research")[0] == ("mistral", "mistral-large-latest")    # research: the strong one
    assert P.plan("quick")[-1][0] == "github"                              # prototype-only: after every other
    for _ in range(6):
        fast.live.append((False, 0.0))
    assert P.plan("quick")[0] == ("mistral", "mistral-large-latest")       # failures in real use count too


def test_a_provider_whose_models_are_all_gone_is_measured_again(monkeypatch):
    keys(monkeypatch, "groq")
    started = []
    monkeypatch.setattr(R, "AUTO", True)
    monkeypatch.setattr(R, "start_rerank", lambda names, transport=None: started.append(names))
    with pytest.raises(P.AIBusy):
        P.complete("s", "t", transport=fake(status=404))
    assert started == [["groq"]]
    with pytest.raises(P.AIBusy):
        P.complete("s", "t2", transport=fake(status=404))
    assert started == [["groq"]]                                           # at most every half hour


def test_pin_and_block_choose_the_models_and_are_saved(monkeypatch):
    keys(monkeypatch, "groq")
    seen = []
    P.pin("groq", "qwen/qwen3-32b")
    P.complete("s", "t", transport=fake(seen=seen))
    assert [b["model"] for b in bodies(seen)] == ["qwen/qwen3-32b"]
    assert json.loads(R.STORE.data["ai:prefs"])["pins"] == {"groq": "qwen/qwen3-32b"}
    P.block("groq", "qwen/qwen3-32b")                                      # blocking the pinned model unpins it
    assert R.pins() == {} and "qwen/qwen3-32b" not in R.in_use("groq")
    P.block("groq", "llama-3.3-70b-versatile")
    assert R.in_use("groq")[0] == "openai/gpt-oss-120b"
    R._status.clear()
    assert R.blocks() == ["groq/llama-3.3-70b-versatile", "groq/qwen/qwen3-32b"]
    P.block("groq", "llama-3.3-70b-versatile", on=False)
    assert R.in_use("groq")[0] == "llama-3.3-70b-versatile"


def test_a_database_that_cant_be_read_means_defaults_now_and_another_read_later(monkeypatch):
    class Down:
        calls = 0

        def get_all(self):
            Down.calls += 1
            return None

        def set(self, key, value):
            pass
    monkeypatch.setattr(R, "STORE", Down())
    keys(monkeypatch, "groq")
    assert R.in_use("groq")[0] == "llama-3.3-70b-versatile"
    R.in_use("groq")
    assert Down.calls == 1                                                 # not asked again on every request
    store = R.MemoryStore()
    store.data["ai:prefs"] = json.dumps({"pins": {"groq": "llama-3.1-8b-instant"}, "blocks": []})
    monkeypatch.setattr(R, "STORE", store)
    R._prefs["retry_at"] = 0                                               # a minute later
    assert R.in_use("groq") == ["llama-3.1-8b-instant"]


def test_each_provider_is_re_ranked_on_its_own_schedule(monkeypatch):
    keys(monkeypatch, "groq", "huggingface", "anthropic")
    assert R.stale("groq") and R.stale("huggingface") and not R.stale("anthropic")    # the paid one: only when asked
    P.status("groq").ranked_at = P.status("huggingface").ranked_at = time.time() - 7 * 3600
    assert R.stale("groq") and not R.stale("huggingface")                  # its tiny credit: every 3 days
    assert not R.stale("gemini")                                           # no key


def test_a_model_pinned_in_railway_is_used_alone(monkeypatch):
    keys(monkeypatch, "groq")
    monkeypatch.setattr(settings, "GROQ_MODEL", "llama-3.1-8b-instant")
    assert R.in_use("groq") == ["llama-3.1-8b-instant"]
    view = next(p for p in P.admin_view()["providers"] if p["name"] == "groq")
    assert view["pinned"] == "llama-3.1-8b-instant" and view["pinned_by"] == "railway"


# ---------- Google's and Anthropic's own APIs ----------
def test_gemini_native_turns_thinking_off_and_reads_the_answer(monkeypatch):
    keys(monkeypatch, "gemini")
    seen = []

    def handler(req: httpx.Request):
        body = json.loads(req.content)
        seen.append((req.url.path, body))
        assert req.headers["x-goog-api-key"] == "k-gemini"
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "thinking…", "thought": True}, {"text": GOOD}]},
                                                         "finishReason": "STOP"}]})
    assert "entry" in P.complete("s", "t", transport=httpx.MockTransport(handler))
    path, body = seen[0]
    assert path.endswith("/models/gemini-2.5-flash:generateContent")
    assert body["generationConfig"]["thinkingConfig"] == {"thinkingBudget": 0} and body["generationConfig"]["responseMimeType"] == "application/json"


def test_gemma_through_gemini_gets_its_instructions_in_the_message(monkeypatch):
    keys(monkeypatch, "gemini")
    R.pin("gemini", "gemma-3-27b-it")
    seen = []

    def handler(req: httpx.Request):
        body = json.loads(req.content)
        seen.append(body)
        if "systemInstruction" in body:
            return httpx.Response(400, json={"error": {"message": "Developer instruction is not enabled for models/gemma-3-27b-it"}})
        if "thinkingConfig" in body["generationConfig"]:
            return httpx.Response(400, json={"error": {"message": "Thinking is not supported for this model"}})
        if "responseMimeType" in body["generationConfig"]:
            return httpx.Response(400, json={"error": {"message": "JSON mode is not enabled for models/gemma-3-27b-it"}})
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "```json\n" + GOOD + "\n```"}]}}]})
    assert "entry" in P.complete("sys", "t", transport=httpx.MockTransport(handler))
    assert seen[-1]["contents"][0]["parts"][0]["text"].startswith("sys\n\nt")


def test_gemini_cut_off_at_the_length_limit_is_retried_with_room(monkeypatch):
    keys(monkeypatch, "gemini")
    calls = []

    def handler(req):
        calls.append(json.loads(req.content)["generationConfig"]["maxOutputTokens"])
        if len(calls) == 1:
            return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": '{"entry": [{"l"'}]}, "finishReason": "MAX_TOKENS"}]})
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": GOOD}]}, "finishReason": "STOP"}]})
    assert "entry" in P.complete("s", "t", transport=httpx.MockTransport(handler))
    assert calls[1] > calls[0]


def test_anthropic_is_asked_last_and_read(monkeypatch):
    keys(monkeypatch, "anthropic", "mistral")
    hosts = []

    def handler(req: httpx.Request):
        hosts.append(req.url.host)
        if req.url.host == "api.mistral.ai":
            return httpx.Response(529 if False else 503, json={"error": "overloaded"})
        assert req.headers["x-api-key"] == "k-anthropic" and req.headers["anthropic-version"]
        return httpx.Response(200, json={"content": [{"type": "text", "text": GOOD}], "stop_reason": "end_turn"})
    assert "entry" in P.complete("s", "t", transport=httpx.MockTransport(handler))
    assert hosts[0] == "api.mistral.ai" and hosts[-1] == "api.anthropic.com"


def test_the_apps_wrappers_use_the_layer_itself(monkeypatch):
    from app import ai_writer
    keys(monkeypatch, "gemini")
    assert ai_writer._gemini._builtin and ai_writer._candidates()[0].startswith("gemini")
    seen = []
    t = httpx.MockTransport(lambda r: (seen.append(r), httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": GOOD}]}}]}))[1])
    assert "entry" in P.complete("s", "t", gemini=ai_writer._gemini, transport=t)     # not treated as a replacement
    assert seen and seen[0].url.host == "generativelanguage.googleapis.com"


# ---------- the Admin page ----------
def test_health_and_admin_view_cover_every_provider(monkeypatch):
    keys(monkeypatch, "groq")
    h = {p["name"]: p for p in P.health()}
    assert set(h) == set(PROVIDERS) and h["groq"]["configured"] and h["groq"]["in_use"] and not h["gemini"]["configured"]
    view = P.admin_view()
    rows = {p["name"]: p for p in view["providers"]}
    assert rows["groq"]["state"] == "idle" and rows["cloudflare"]["missing"] == ["CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID"]
    assert rows["github"]["terms"] == "prototype" and rows["nvidia"]["key_url"].startswith("https://build.nvidia.com")
    assert [s["provider"] for s in view["routes"]["quick"]["steps"]] == ["groq"] * 3
    assert view["routes"]["long"]["budget_s"] == P.BUDGET["long"]


def test_test_all_reports_every_provider_and_tries_the_next_model(monkeypatch):
    keys(monkeypatch, "groq", "gemini")

    def gemini(system, text, **k):
        raise P.AIConfig("bad", detail="Google rejected GEMINI_API_KEY.")
    calls = []

    def handler(req):
        calls.append(json.loads(req.content)["model"])
        return chat('{"ok": true}') if len(calls) > 1 else httpx.Response(404, json={"error": {"message": "gone"}})
    out = P.test_all(gemini=gemini, transport=httpx.MockTransport(handler))
    assert [(r["name"], r["ok"]) for r in out] == [("groq", True), ("gemini", False)]
    assert out[0]["model"] == "openai/gpt-oss-120b" and out[1]["error"] == "Google rejected GEMINI_API_KEY."


def test_test_all_ignores_cooldown(monkeypatch):
    keys(monkeypatch, "mistral")
    P.status("mistral").cooldown_until = 1e12
    out = P.test_all(transport=fake(reply='{"ok": true}'))
    assert out[0]["ok"] and P.status("mistral").cooldown_until == 0


@pytest.fixture
def admin_client(monkeypatch):
    from fastapi.testclient import TestClient
    from app import main
    monkeypatch.setattr(settings, "ADMIN_EMAILS", "owner@x.com")
    who = {"profile": {"id": "u1", "email": "owner@x.com", "_plan": "pro", "_email_verified": True}}
    main.app.dependency_overrides[main.current_profile] = lambda: who["profile"]
    yield TestClient(main.app), who
    main.app.dependency_overrides.clear()


def test_admin_ai_endpoints(monkeypatch, admin_client):
    client, who = admin_client
    keys(monkeypatch, "groq")
    view = client.get("/admin/ai").json()
    assert {p["name"] for p in view["providers"]} == set(PROVIDERS) and "routes" in view
    assert client.post("/admin/ai/pin", json={"provider": "groq", "model": "llama-3.1-8b-instant"}).json()["routes"]["quick"]["steps"][0]["model"] == "llama-3.1-8b-instant"
    assert client.post("/admin/ai/pin", json={"provider": "groq", "model": None}).status_code == 200 and R.pins() == {}
    r = client.post("/admin/ai/block", json={"provider": "groq", "model": "llama-3.3-70b-versatile"}).json()
    assert next(p for p in r["providers"] if p["name"] == "groq")["blocked"] == ["llama-3.3-70b-versatile"]
    assert client.post("/admin/ai/block", json={"provider": "nope", "model": "x"}).status_code == 400
    assert client.post("/admin/ai/rerank", json={"provider": "gemini"}).status_code == 400        # no key
    started = []
    monkeypatch.setattr(R, "start_rerank", lambda names, transport=None: started.append(names) or names)
    assert client.post("/admin/ai/rerank", json={}).json()["started"] == ["groq"] and started == [["groq"]]
    monkeypatch.setattr(P, "test_all", lambda **k: [{"name": "groq", "ok": True}])
    assert client.post("/admin/ai/test").json()["providers"] == [{"name": "groq", "ok": True}]
    who["profile"] = {"id": "u2", "email": "someone@x.com", "_plan": "pro", "_email_verified": True}
    assert client.get("/admin/ai").status_code == 403
    assert client.post("/admin/ai/pin", json={"provider": "groq", "model": "x"}).status_code == 403
