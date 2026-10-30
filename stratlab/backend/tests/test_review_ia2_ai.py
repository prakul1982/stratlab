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
    # the catalog no longer starts Cerebras on the ids it retired
    assert not {"llama-3.3-70b", "qwen-3-235b-a22b-instruct-2507"} & set(PROVIDERS["cerebras"].defaults)
    keys(monkeypatch, "cerebras")
    asked = []

    def handler(req: httpx.Request):
        model = json.loads(req.content)["model"]
        asked.append(model)
        if model == "gpt-oss-120b":
            return httpx.Response(404, json=GONE)
        return httpx.Response(200, json={"choices": [{"message": {"content": GOOD}, "finish_reason": "stop"}]})
    assert "entry" in P.complete("s", "t", transport=httpx.MockTransport(handler))
    assert asked == ["gpt-oss-120b", "llama3.1-8b"]
    assert R.retired("cerebras", "gpt-oss-120b") and "gpt-oss-120b" not in R.in_use("cerebras")
    # long after its breaker would have closed, it is still not asked
    R.stats("cerebras", "gpt-oss-120b").open_until = 0
    asked.clear()
    assert "entry" in P.complete("s", "t2", transport=httpx.MockTransport(handler))
    assert asked == ["llama3.1-8b"]
    # the same list of models keeps it retired; a new list frees it to be measured once more
    assert R.list_changed("cerebras", ["gpt-oss-120b", "llama3.1-8b"]) and not R.retired("cerebras", "gpt-oss-120b")
    R.status("cerebras").retired["gpt-oss-120b"] = R.status("cerebras").list_sig
    assert not R.list_changed("cerebras", ["llama3.1-8b", "gpt-oss-120b"]) and R.retired("cerebras", "gpt-oss-120b")
    assert R.list_changed("cerebras", ["gpt-oss-120b", "llama3.1-8b", "zai-glm-4.7"]) and not R.retired("cerebras", "gpt-oss-120b")
    # kept across a restart
    R.status("cerebras").retired["gpt-oss-120b"] = R.status("cerebras").list_sig
    R.save("cerebras")
    saved = json.loads(R.STORE.get_all()["ai:rank:cerebras"])
    assert saved["retired"] == {"gpt-oss-120b": R.status("cerebras").list_sig} and saved["list_sig"] == R.status("cerebras").list_sig
