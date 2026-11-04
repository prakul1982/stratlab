"""IA-2 item 45 (owner, 30 Oct: Admin's AI panel showed Cerebras failing with "couldn't use llama-3.3-70b (404: Model does not exist…)"
and the same for qwen-3-235b-a22b-instruct-2507): the retired ids are gone from the catalog, and a model the provider says does not
exist is retired: not asked again until the provider's list of models changes."""
import json

import httpx

from app import ai_providers as P
from app import ai_rank as R
from app.ai_catalog import PROVIDERS
from tests.test_ai_r5o import GOOD, clean, keys  # noqa: F401  (clean: the autouse fixture that clears the keys and settings)

GONE = {"message": "Model does not exist or you do not have access to it.", "type": "not_found_error", "code": "model_not_found"}


def test_a_model_the_provider_says_does_not_exist_is_not_asked_again_until_its_list_changes(monkeypatch):
    # Cerebras, whose retired ids started this check, was removed on 4 Nov (no free allowance left); the same rule on SambaNova
    assert "cerebras" not in PROVIDERS
    keys(monkeypatch, "sambanova")
    asked = []

    def handler(req: httpx.Request):
        model = json.loads(req.content)["model"]
        asked.append(model)
        if model == "Meta-Llama-3.3-70B-Instruct":
            return httpx.Response(404, json=GONE)
        return httpx.Response(200, json={"choices": [{"message": {"content": GOOD}, "finish_reason": "stop"}]})
    assert "entry" in P.complete("s", "t", transport=httpx.MockTransport(handler))
    assert asked == ["Meta-Llama-3.3-70B-Instruct", "DeepSeek-V3.1"]
    assert R.retired("sambanova", "Meta-Llama-3.3-70B-Instruct") and "Meta-Llama-3.3-70B-Instruct" not in R.in_use("sambanova")
    # long after its breaker would have closed, it is still not asked
    R.stats("sambanova", "Meta-Llama-3.3-70B-Instruct").open_until = 0
    asked.clear()
    assert "entry" in P.complete("s", "t2", transport=httpx.MockTransport(handler))
    assert asked == ["DeepSeek-V3.1"]
    # the same list of models keeps it retired; a new list frees it to be measured once more
    assert R.list_changed("sambanova", ["Meta-Llama-3.3-70B-Instruct", "DeepSeek-V3.1"]) and not R.retired("sambanova", "Meta-Llama-3.3-70B-Instruct")
    R.status("sambanova").retired["Meta-Llama-3.3-70B-Instruct"] = R.status("sambanova").list_sig
    assert not R.list_changed("sambanova", ["DeepSeek-V3.1", "Meta-Llama-3.3-70B-Instruct"]) and R.retired("sambanova", "Meta-Llama-3.3-70B-Instruct")
    assert R.list_changed("sambanova", ["Meta-Llama-3.3-70B-Instruct", "DeepSeek-V3.1", "zai-glm-4.7"]) and not R.retired("sambanova", "Meta-Llama-3.3-70B-Instruct")
    # kept across a restart
    R.status("sambanova").retired["Meta-Llama-3.3-70B-Instruct"] = R.status("sambanova").list_sig
    R.save("sambanova")
    saved = json.loads(R.STORE.get_all()["ai:rank:sambanova"])
    assert saved["retired"] == {"Meta-Llama-3.3-70B-Instruct": R.status("sambanova").list_sig} and saved["list_sig"] == R.status("sambanova").list_sig


def test_a_model_the_provider_says_is_gone_410_is_retired_on_every_provider_and_the_next_model_answers(monkeypatch):
    """Live, 4 Nov: SambaNova's test failed with "unexpected answer 410 (The requested model (DeepSeek-V3.1) is no longer available)",
    and the model stayed in use. A 410, or a 404/400 that says the model is gone, retires that model (not asked again until the
    provider's list changes) on every provider, and the request goes on to the provider's next model."""
    from app.ai_clients import classify
    req = httpx.Request("POST", "https://example.test/v1/chat/completions")
    for name in PROVIDERS:
        model = f"{name}-old-model"
        for code, body in ((410, {"error": {"message": f"The requested model ({model}) is no longer available"}}),
                           (404, {"error": {"message": "model not found"}}), (410, {})):
            e = classify(name, httpx.Response(code, json=body, request=req), model)
            assert e.kind == "model" and e.scope != "provider", (name, code, e.kind, e.detail)
            R.status(name).retired.pop(model, None)
            R.record_fail(name, model, e, live=False)
            assert R.retired(name, model), (name, code, e.detail)
    # SambaNova end to end: the gone model is asked once, the next one answers, and the gone one isn't asked again
    keys(monkeypatch, "sambanova")
    asked = []
    first = R.in_use("sambanova")[0]

    def handler(req: httpx.Request):
        model = json.loads(req.content)["model"]
        asked.append(model)
        if model == first:
            return httpx.Response(410, json={"error": {"message": f"The requested model ({first}) is no longer available"}})
        return httpx.Response(200, json={"choices": [{"message": {"content": GOOD}, "finish_reason": "stop"}]})
    assert "entry" in P.complete("s", "t410", transport=httpx.MockTransport(handler))
    assert asked[0] == first and len(asked) == 2 and R.retired("sambanova", first) and first not in R.in_use("sambanova")
    asked.clear()
    R.stats("sambanova", first).open_until = 0
    assert "entry" in P.complete("s", "t410-again", transport=httpx.MockTransport(handler))
    assert first not in asked
