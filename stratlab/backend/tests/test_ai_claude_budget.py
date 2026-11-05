"""Claude on the owner's monthly credit (owner, 4 Nov): the request current models accept, which model each job asks,
the spend meter and its cap, and the measuring that no longer spends the free quotas. Fake transports only: no test
reaches the real Anthropic API."""
import json
import time

import httpx
import pytest

from app import ai_clients as C
from app import ai_providers as P
from app import ai_rank as R
from app import ai_spend as S
from app.ai_catalog import PROVIDERS
from app.config import settings

GOOD = json.dumps({"entry": [{"l": {"t": "price"}, "op": "gt", "r": {"t": "sma", "p": 50}}], "mentioned": []})
KEYS = [p.key_env for p in PROVIDERS.values()] + ["CLOUDFLARE_ACCOUNT_ID"]
USAGE = {"input_tokens": 1000, "output_tokens": 500, "cache_creation_input_tokens": 2000, "cache_read_input_tokens": 4000}


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    R._auth_fails.clear()
    for k in KEYS:
        monkeypatch.setattr(settings, k, "")
    for p in PROVIDERS.values():
        monkeypatch.setattr(settings, p.model_env, "auto")
    monkeypatch.setattr(settings, "AI_PROVIDERS", "auto")
    monkeypatch.setattr(settings, "AI_PROVIDERS_RESEARCH", "auto")
    monkeypatch.setattr(settings, "AI_PROVIDER", "gemini")
    monkeypatch.setattr(settings, "ANTHROPIC_MONTHLY_CAP_USD", 99.0)
    monkeypatch.setattr(settings, "ANTHROPIC_SONNET_UNTIL_USD", 75.0)
    monkeypatch.setattr(settings, "AI_QUICK_BEFORE_CLAUDE", "groq")
    monkeypatch.setattr(P, "_sleep", lambda s: None)


def keys(monkeypatch, *names):
    for n in names:
        monkeypatch.setattr(settings, PROVIDERS[n].key_env, "k-" + n)


def spent(usd: float):
    """This month's Claude spend set to `usd` (as if earlier replies had cost it)."""
    S._current()["micros"] = round(usd * 1e6)


def claude(seen=None, stop="end_turn", content=None, usage=USAGE, status=200):
    def handler(req: httpx.Request):
        body = json.loads(req.content)
        if seen is not None:
            seen.append(body)
        if status != 200:
            return httpx.Response(status, json={"type": "error", "error": {"type": "overloaded_error", "message": "Overloaded"}})
        blocks = content if content is not None else [{"type": "thinking", "thinking": "", "signature": "x"},
                                                      {"type": "text", "text": GOOD}]
        return httpx.Response(200, json={"content": blocks, "stop_reason": stop, "usage": usage})
    return httpx.MockTransport(handler)


# ---------- the request current Claude models accept ----------
@pytest.mark.parametrize("task,effort", [("quick", "low"), ("research", "medium"), ("long", "medium")])
def test_the_claude_request_has_no_sampling_settings_and_an_effort_per_job(monkeypatch, task, effort):
    keys(monkeypatch, "anthropic")
    seen = []
    reply = C.AnthropicHTTP(transport=claude(seen)).call("claude-haiku-5-5", "sys", "q", 1500, True, time.time() + 20, task=task)
    body = seen[0]
    # current models answer 400 to temperature/top_p/top_k and to thinking "disabled"/budget_tokens: none is sent
    assert not {"temperature", "top_p", "top_k", "thinking"} & set(body)
    assert body["output_config"] == {"effort": effort}
    assert body["system"] == [{"type": "text", "text": "sys", "cache_control": {"type": "ephemeral"}}]
    assert body["messages"] == [{"role": "user", "content": "q"}]                    # no assistant prefill
    assert body["max_tokens"] >= 1500 + 4000                                         # room for thinking and the answer
    assert reply.text == GOOD and reply.usage == USAGE                               # only the text block, usage returned


def test_a_refusal_moves_to_the_next_model_without_opening_a_breaker(monkeypatch):
    keys(monkeypatch, "anthropic", "mistral")
    hosts = []

    def handler(req: httpx.Request):
        hosts.append(req.url.host)
        if req.url.host == "api.anthropic.com":
            return httpx.Response(200, json={"content": [], "stop_reason": "refusal", "usage": {"input_tokens": 10, "output_tokens": 1}})
        return httpx.Response(200, json={"choices": [{"message": {"content": GOOD}, "finish_reason": "stop"}]})
    assert "entry" in P.complete("s", "t", kind="research", transport=httpx.MockTransport(handler))
    # Sonnet declined, then Haiku declined, then the free provider answered
    assert hosts[:2] == ["api.anthropic.com"] * 2 and hosts[-1] == "api.mistral.ai"
    assert R.ready("anthropic", "claude-sonnet-5-5") == 0                     # a refusal is about the request, not the model
    assert S.view()["refusals"] == 2 and S.view()["requests"] == 2           # billed, so counted


# ---------- which Claude model each job asks ----------
def test_research_and_long_ask_sonnet_then_haiku_then_nothing_as_the_month_is_spent(monkeypatch):
    keys(monkeypatch, "anthropic", "groq", "mistral")
    for task in ("research", "long"):
        assert P.plan(task)[:2] == [("anthropic", "claude-sonnet-5-5"), ("anthropic", "claude-haiku-5-5")]
    spent(75.0)
    assert P.plan("research")[0] == ("anthropic", "claude-haiku-5-5") and ("anthropic", "claude-sonnet-5-5") not in P.plan("long")
    spent(98.99)
    assert P.plan("long")[0] == ("anthropic", "claude-haiku-5-5")
    spent(99.0)                                                                 # the cap: free models only until the month turns
    assert all(n != "anthropic" for task in ("quick", "research", "long") for n, _ in P.plan(task))


def test_quick_jobs_ask_groq_then_haiku_before_the_other_free_providers(monkeypatch):
    keys(monkeypatch, "anthropic", "groq", "gemini", "mistral", "nvidia")
    names = [n for n, _ in P.plan("quick")]
    first_other = min(names.index(n) for n in ("gemini", "mistral", "nvidia"))
    assert names[0] == "groq" and names.index("anthropic") < first_other
    assert ("anthropic", "claude-haiku-5-5") in P.plan("quick") and ("anthropic", "claude-sonnet-5-5") not in P.plan("quick")
    # with Groq paused, Claude Haiku answers first
    for m in R.in_use("groq"):
        R.stats("groq", m).open_until = time.time() + 600
    assert P.plan("quick")[0] == ("anthropic", "claude-haiku-5-5")


def test_a_pinned_claude_model_is_used_alone_and_still_stops_at_the_cap(monkeypatch):
    keys(monkeypatch, "anthropic")
    monkeypatch.setattr(settings, "ANTHROPIC_MODEL", "claude-sonnet-5")
    assert P.plan("quick") == [("anthropic", "claude-sonnet-5")] == P.plan("research")
    spent(99.5)
    assert P.plan("research") == []


def test_a_fixed_provider_order_keeps_claude_where_it_is_named(monkeypatch):
    keys(monkeypatch, "anthropic", "mistral")
    monkeypatch.setattr(settings, "AI_PROVIDERS_RESEARCH", "mistral,anthropic")
    assert [n for n, _ in P.plan("research")] == ["mistral"] * 3 + ["anthropic"] * 2


# ---------- the spend meter ----------
def test_cost_counts_cache_writes_and_reads_and_rounds_up():
    # Sonnet 5.5: $2 in, $10 out; cache writes 1.25x input, reads 0.1x input
    assert S.cost_micros("claude-sonnet-5-5", USAGE) == 1000 * 2 + 2000 * 2.5 + 4000 * 0.2 + 500 * 10      # 12,800 = $0.0128
    # Haiku 5.5: $0.10 / $0.50 up to 100K prompt tokens, $0.50 / $2.50 above
    assert S.cost_micros("claude-haiku-5-5", {"input_tokens": 1000, "output_tokens": 1000}) == 600
    assert S.cost_micros("claude-haiku-5-5", {"input_tokens": 100_001, "output_tokens": 1000}) == 52_501   # 50,000.5 + 2,500 → up
    assert S.cost_micros("claude-haiku-5-5", {"input_tokens": 3}) == 1                                       # 0.3 → rounded up
    assert S.cost_micros("claude-mystery-9", {"output_tokens": 1000}) == 50_000                              # unknown: dearest price
    # the estimate is never below what the same request can actually cost
    est = S.estimate_micros("claude-sonnet-5-5", 7000, 4000)
    assert est >= S.cost_micros("claude-sonnet-5-5", {"cache_creation_input_tokens": 3500, "output_tokens": 4000})


def test_every_claude_reply_is_added_to_the_month_and_survives_a_restart(monkeypatch):
    keys(monkeypatch, "anthropic")
    C.AnthropicHTTP(transport=claude()).call("claude-sonnet-5-5", "s", "t", 100, True, time.time() + 20, task="research")
    C.AnthropicHTTP(transport=claude()).call("claude-haiku-5-5", "s", "t", 100, True, time.time() + 20)
    v = S.view()
    assert v["usd"] == round((12_800 + S.cost_micros("claude-haiku-5-5", USAGE)) / 1e6, 4) and v["requests"] == 2
    assert v["input_tokens"] == 2000 and v["output_tokens"] == 1000 and v["cache_read_tokens"] == 8000
    assert v["cache_hit_share"] == round(8000 / (2000 + 4000 + 8000), 3) and v["tier"] == "sonnet"
    assert set(v["models"]) == {"claude-sonnet-5-5", "claude-haiku-5-5"}
    stored = json.loads(R.STORE.data["ai:spend:" + S.month()])
    assert stored["requests"] == 2
    S.reset()                                                                  # a restart: the month comes back from the store
    assert S.view()["requests"] == 2 and S.view()["usd"] == v["usd"]


def test_a_new_month_starts_from_nothing(monkeypatch):
    spent(98.0)
    now = time.time()
    monkeypatch.setattr(S.time, "time", lambda: S.month_end(now) + 5)
    assert S.spent_usd() == 0 and S.claude_models("research") == ["claude-sonnet-5-5", "claude-haiku-5-5"]


def test_a_request_that_could_pass_the_cap_is_not_sent(monkeypatch):
    keys(monkeypatch, "anthropic")
    seen = []
    spent(98.999)
    with pytest.raises(C.CallError) as e:
        C.AnthropicHTTP(transport=claude(seen)).call("claude-sonnet-5-5", "s" * 4000, "t", 2000, True, time.time() + 20)
    assert e.value.kind == "credit" and "budget" in e.value.detail and not seen
    assert S._state["pending"] == {}                                           # nothing left held back


def test_an_unreadable_spend_store_means_no_claude(monkeypatch):
    class Down(R.MemoryStore):
        def get(self, key):
            raise RuntimeError("database down")
    monkeypatch.setattr(R, "STORE", Down())
    S.reset()
    keys(monkeypatch, "anthropic", "mistral")
    assert S.claude_models("research") == [] and [n for n, _ in P.plan("research")] == ["mistral"] * 3
    assert S.view()["known"] is False


def test_admin_view_shows_claude_this_month(monkeypatch):
    keys(monkeypatch, "anthropic")
    spent(80.0)
    c = P.admin_view()["claude"]
    assert c["usd"] == 80.0 and c["cap_usd"] == 99.0 and c["sonnet_until_usd"] == 75.0 and c["tier"] == "haiku"
    assert c["resets_at"] > time.time()


def test_test_button_asks_haiku_one_tiny_question_and_respects_the_cap(monkeypatch):
    keys(monkeypatch, "anthropic")
    seen = []
    r = next(x for x in P.test_all(transport=claude(seen)) if x["name"] == "anthropic")
    assert r["ok"] and r["model"] == "claude-haiku-5-5" and len(seen) == 1 and seen[0]["output_config"] == {"effort": "low"}
    spent(99.0)
    r = next(x for x in P.test_all(transport=claude(seen)) if x["name"] == "anthropic")
    assert not r["ok"] and "budget" in r["error"] and len(seen) == 1


# ---------- measuring spends as little free quota as it can ----------
def test_the_paid_provider_is_never_measured(monkeypatch):
    keys(monkeypatch, "anthropic")
    seen = []
    R.rerank("anthropic", transport=claude(seen))
    assert not seen and not R.stale("anthropic")


def test_a_quota_limited_or_nearly_spent_provider_is_not_measured_on_schedule(monkeypatch):
    keys(monkeypatch, "mistral", "gemini")
    assert R.stale("mistral") and R.stale("gemini")
    st = R.status("mistral")
    st.quota, st.cooldown_until = True, time.time() + 3600                    # its free quota is used up right now
    assert not R.stale("mistral")
    st.quota, st.cooldown_until = True, time.time() - 5                       # reset since: due again
    assert R.stale("mistral")
    R.status("gemini").remaining = {"requests": 7, "requests_reset": 3600, "at": time.time()}
    assert not R.stale("gemini")                                               # its last requests are kept for answers
    R.status("gemini").remaining = {"requests": 7, "requests_reset": 60, "at": time.time() - 120}
    assert R.stale("gemini")                                                   # that window reset


def test_the_daily_pass_skips_models_real_requests_measured_today(monkeypatch):
    keys(monkeypatch, "mistral")
    asked = []

    def handler(req: httpx.Request):
        if req.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": m, "type": "base", "capabilities": {"completion_chat": True}}
                                                      for m in ("mistral-small-latest", "mistral-medium-latest")]})
        asked.append(json.loads(req.content)["model"])
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}]})
    s = R.stats("mistral", "mistral-small-latest")
    for _ in range(R.LIVE_ENOUGH):
        s.live.append((True, 900.0))
    s.last_ok_at = time.time()
    R.rerank("mistral", transport=httpx.MockTransport(handler), auto=True)
    assert "mistral-small-latest" not in asked and "mistral-medium-latest" in asked
    assert R.status("mistral").order == ["mistral-small-latest"]               # kept on its real record
    asked.clear()
    R.rerank("mistral", transport=httpx.MockTransport(handler))               # the Admin page's Re-rank measures every one
    assert "mistral-small-latest" in asked


# ---------- the free providers that kept giving up ----------
def test_mistral_models_typed_base_are_listed():
    # Mistral types every model "base" or "fine-tuned"; a list that kept only "language"/"chat" types was empty
    data = {"object": "list", "data": [
        {"id": "mistral-small-latest", "type": "base", "capabilities": {"completion_chat": True}, "max_context_length": 128000},
        {"id": "ft:open-mistral-7b:abc", "type": "fine-tuned", "capabilities": {"completion_chat": True}},
        {"id": "mistral-ocr-latest", "type": "base", "capabilities": {"completion_chat": False}},
        {"id": "mistral-old", "type": "base", "capabilities": {"completion_chat": True}, "archived": True},
        {"id": "v/embed", "type": "embedding"}]}
    assert C.parse_models(data) == [{"id": "mistral-small-latest", "ctx": 128000}, {"id": "ft:open-mistral-7b:abc", "ctx": None}]


def test_mistral_measuring_reaches_its_listed_models(monkeypatch):
    keys(monkeypatch, "mistral")

    def handler(req: httpx.Request):
        if req.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "mistral-small-latest", "type": "base"}]})
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}]})
    R.rerank("mistral", transport=httpx.MockTransport(handler))
    assert R.status("mistral").discovered == 1 and R.stats("mistral", "mistral-small-latest").probe_tries == 2


@pytest.mark.parametrize("model,cfg", [("gemini-3.8-flash", {"thinkingLevel": "low"}), ("gemini-3.5-flash-lite", {"thinkingLevel": "low"}),
                                       ("gemini-2.5-flash", {"thinkingBudget": 0}), ("gemma-3-27b-it", {"thinkingBudget": 0})])
def test_each_gemini_generation_is_asked_to_think_little_in_its_own_way(model, cfg):
    assert C.gemini_thinking(model) == cfg


def test_gemini_invalid_argument_is_retried_without_the_settings_it_may_reject(monkeypatch):
    keys(monkeypatch, "gemini")
    sent = []

    def handler(req: httpx.Request):
        gen = json.loads(req.content)["generationConfig"]
        sent.append(set(gen))
        if "thinkingConfig" in gen:
            return httpx.Response(400, json={"error": {"code": 400, "message": "Request contains an invalid argument.", "status": "INVALID_ARGUMENT"}})
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": GOOD}]}, "finishReason": "STOP"}]})
    r = C.GeminiNative(transport=httpx.MockTransport(handler)).call("gemini-3.5-flash-lite", "s", "t", 500, True, time.time() + 20)
    assert r.text == GOOD and "thinkingConfig" in sent[0] and "thinkingConfig" not in sent[1] and "responseMimeType" in sent[1]


@pytest.mark.parametrize("name,code,body", [
    ("gemini", 503, {"error": {"code": 503, "message": "This model is currently experiencing high demand. Spikes in demand are usually temporary."}}),
    ("sambanova", 429, {"error": {"message": "Meta-Llama-3.3-70B-Instruct is currently experiencing high demand. Please try again later!"}}),
    ("nvidia", 503, {"detail": "Service temporarily overloaded"}),
])
def test_a_busy_model_skips_only_that_model(name, code, body):
    e = C.classify(name, httpx.Response(code, json=body), "m")
    assert e.scope == "model" and e.kind in ("busy", "rate")
    assert C.classify(name, httpx.Response(code, json={"error": {"message": "nope"}}), "m").scope == "provider"


def test_gemini_moves_to_its_next_model_when_one_is_overloaded(monkeypatch):
    keys(monkeypatch, "gemini")
    asked = []

    def handler(req: httpx.Request):
        asked.append(req.url.path)
        if len(asked) == 1:
            return httpx.Response(503, json={"error": {"code": 503, "message": "This model is currently experiencing high demand."}})
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": GOOD}]}, "finishReason": "STOP"}]})
    assert "entry" in P.complete("s", "t", transport=httpx.MockTransport(handler))
    assert len(asked) == 2 and asked[0] != asked[1]                           # the same provider's next model, not given up


def test_a_paid_model_on_a_mixed_catalog_is_not_the_whole_key_out_of_credit(monkeypatch):
    insufficient = {"error": {"code": "1113", "message": "Insufficient balance or no resource package. Please recharge."}}
    e = C.classify("zai", httpx.Response(429, json=insufficient), "glm-5.3-flash")
    assert e.kind == "forbidden" and e.scope == "model" and "isn't free" in e.detail
    # a provider whose models are all free: its key's credit is used up, and the provider's own words go with it
    e = C.classify("huggingface", httpx.Response(402, json={"error": "You have exceeded your monthly included credits"}), "m")
    assert e.kind == "credit" and e.scope == "provider" and "402: You have exceeded" in e.detail


def test_cerebras_is_gone_and_ollama_cloud_is_a_provider():
    assert "cerebras" not in PROVIDERS
    o = PROVIDERS["ollama"]
    assert o.key_env == "OLLAMA_API_KEY" and o.terms == "prototype" and o.base == "https://ollama.com/v1"


def test_research_answers_are_kept_as_long_as_their_facts_are_the_same():
    assert P.CACHE_TTL["research"] >= 12 * 3600 and P.CACHE_MAX == 400
    k = P.AnswerCache.key("research", "sys", "FACTS: x", 2500, True)
    assert k == P.AnswerCache.key("research", "sys", "FACTS: x", 2500, True)      # nothing per call in the key


# ---------- background jobs ask Haiku only (coordinator, 4 Nov) ----------
def test_a_background_job_asks_claude_haiku_only_and_a_persons_read_keeps_sonnet(monkeypatch):
    keys(monkeypatch, "anthropic", "mistral")
    assert P.plan("long")[:2] == [("anthropic", "claude-sonnet-5-5"), ("anthropic", "claude-haiku-5-5")]
    for plan in (P.plan("long", bulk=True), P.plan("research", bulk=True)):
        assert plan[0] == ("anthropic", "claude-haiku-5-5") and ("anthropic", "claude-sonnet-5-5") not in plan
    seen = []
    with P.bulk():
        assert ("anthropic", "claude-sonnet-5-5") not in P.plan("long")
        P.complete("s", "t", kind="long", transport=claude(seen))
    P.complete("s", "t2", kind="long", transport=claude(seen))               # outside the block: a person's read again
    assert [b["model"] for b in seen] == ["claude-haiku-5-5", "claude-sonnet-5-5"]
    P.complete("s", "t3", kind="research", bulk=True, transport=claude(seen))
    assert seen[-1]["model"] == "claude-haiku-5-5"
    spent(99.0)
    assert all(n != "anthropic" for n, _ in P.plan("long", bulk=True))      # the cap still holds


def test_the_scheduled_callers_run_as_background_jobs():
    # one mechanism (bulk), used where a job reads, not where a person asked: biz updates' daily job, the IPO catch-up
    # pass and the newsletter; the user-triggered reads (business-updates read, opening an IPO, deep dive) keep Sonnet
    import inspect
    from app import biz_updates, ipo
    from app.newsletter import write
    assert "with AI.bulk():" in inspect.getsource(biz_updates.Job.run)
    assert inspect.getsource(biz_updates.business_updates_read).count("bulk") == 0
    src = inspect.getsource(ipo)
    assert src.count("with AI.bulk():") == 1 and "Today's catch-up limit" in src[:src.index("with AI.bulk():")][-1200:]
    assert "bulk=True" in inspect.getsource(write.ai_summary)


def test_a_402_that_names_the_model_turns_off_that_model_not_the_provider():
    # Ollama Cloud, 5 Nov: a new key answered gpt-oss:120b, then the ranking's probe of mistral-large-3:675b got "402: this model is
    # not included in your free usage" and all of Ollama was paused six hours as out of credit
    body = {"error": "this model is not included in your free usage, add usage credits to pay as you go: https://ollama.com/settings"}
    e = C.classify("ollama", httpx.Response(402, json=body), "mistral-large-3:675b")
    assert e.kind == "forbidden" and e.scope == "model" and "mistral-large-3:675b" in e.detail
    # a 402 about the account itself still pauses the provider
    e = C.classify("ollama", httpx.Response(402, json={"error": "you have used up your free credits"}), "gpt-oss:120b")
    assert e.kind == "credit" and e.scope == "provider"
