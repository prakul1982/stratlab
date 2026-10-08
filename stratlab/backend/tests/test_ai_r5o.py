"""Round 5, the owner's review (R5O-016): the seven AI providers Admin listed as down, each with its real cause,
replayed with the providers' own recorded answers (no network)."""
import json

import httpx
import pytest

from app import ai_clients as C
from app import ai_providers as P
from app import ai_rank as R
from app.ai_catalog import PROVIDERS, unusable
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


def view(name):
    return next(p for p in P.admin_view()["providers"] if p["name"] == name)


def health(name):
    return next(p for p in P.health() if p["name"] == name)


def chat(content=GOOD):
    return httpx.Response(200, json={"choices": [{"message": {"content": content}, "finish_reason": "stop"}]})


# ---------- Cloudflare: the model list's UUIDs were sent as model names ----------
CF_LIST = {"success": True, "result": [
    {"id": "02c16efa-29f5-4304-8e6c-3d188889f875", "name": "@cf/meta/llama-3.3-70b-instruct-fp8-fast", "task": {"name": "Text Generation"}},
    {"id": "4f154983-20bc-4ab4-922f-1d77b6f101b8", "name": "@cf/openai/gpt-oss-120b", "task": {"name": "Text Generation"}}]}


def test_cloudflare_models_are_called_by_name_not_by_their_uuid(monkeypatch):
    assert [m["id"] for m in C.parse_models(CF_LIST)] == ["@cf/meta/llama-3.3-70b-instruct-fp8-fast", "@cf/openai/gpt-oss-120b"]
    keys(monkeypatch, "cloudflare")
    monkeypatch.setattr(settings, "CLOUDFLARE_ACCOUNT_ID", "acc1")
    asked = []

    def handler(req):
        if "/models/search" in req.url.path:
            return httpx.Response(200, json=CF_LIST)
        model = json.loads(req.content)["model"]
        asked.append(model)
        if not model.startswith("@cf/"):
            return httpx.Response(400, json={"errors": [{"message": f"AiError: No such model: No such model {model} or task", "code": 5007}]})
        return chat()
    R.rerank("cloudflare", httpx.MockTransport(handler))
    assert asked and all(m.startswith("@cf/") for m in asked)
    assert R.in_use("cloudflare")[0].startswith("@cf/")


def test_a_stored_uuid_from_before_the_fix_is_never_used():
    R.status("cloudflare").order = ["02c16efa-29f5-4304-8e6c-3d188889f875", "@cf/openai/gpt-oss-120b"]
    assert R.in_use("cloudflare") == ["@cf/openai/gpt-oss-120b"]


# ---------- Gemini: pinned in Railway to a model Google retired ----------
RETIRED = {"error": {"code": 404, "status": "NOT_FOUND", "message": "This model models/gemini-2.5-flash is no longer available to new "
                     "users. Please update your code to use models/gemini-3.8-flash for the latest features and improvements."}}


def test_a_retired_pinned_model_gives_way_to_the_measured_ones(monkeypatch):
    keys(monkeypatch, "gemini")
    monkeypatch.setattr(settings, "GEMINI_MODEL", "gemini-2.5-flash")
    paths = []

    def handler(req):
        paths.append(req.url.path)
        if "gemini-2.5-flash:" in req.url.path:
            return httpx.Response(404, json=RETIRED)
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": GOOD}]}, "finishReason": "STOP"}]})
    with pytest.raises(Exception):
        P.complete("s", "t", transport=httpx.MockTransport(handler))     # the pin alone: it fails, and says why
    assert R.pin_gone("gemini", "gemini-2.5-flash")
    assert R.in_use("gemini")[0] == "gemini-3.5-flash"                     # the cold-start list no longer starts with it
    assert "entry" in P.complete("s", "t2", transport=httpx.MockTransport(handler))
    assert paths[-1].endswith("/models/gemini-3.5-flash:generateContent")
    v = view("gemini")
    assert v["state"] == "ok" and "remove GEMINI_MODEL in Railway" in v["state_text"] and "no longer available" in v["state_text"]
    assert health("gemini")["answering"] is True


def test_the_cold_start_list_has_no_retired_gemini_model():
    assert not {"gemini-2.5-flash", "gemini-2.5-flash-lite"} & set(PROVIDERS["gemini"].defaults)


# ---------- Vercel AI Gateway: the account needs a card on file ----------
CARD = {"error": {"message": "AI Gateway requires a valid credit card on file to service requests. Please visit "
                  "https://vercel.com/d?to=%2F%5Bteam%5D%2F%7E%2Fai%3Fmodal%3Dadd-credit-card to add a card and unlock your free credits.",
                  "type": "customer_verification_required"}}


def test_vercel_without_a_card_is_an_account_setting_not_a_model_fault(monkeypatch):
    keys(monkeypatch, "vercel")
    t = httpx.MockTransport(lambda req: httpx.Response(403, json=CARD))
    with pytest.raises(Exception):
        P.complete("s", "t", transport=t)
    v = view("vercel")
    assert v["state"] == "fail" and "payment method on file (403: AI Gateway requires a valid credit card" in v["state_text"]
    assert health("vercel")["answering"] is False


# ---------- GitHub Models: a 200 that isn't a chat reply ----------
def test_a_reply_that_is_not_a_chat_answer_shows_what_came_back(monkeypatch):
    keys(monkeypatch, "github")
    t = httpx.MockTransport(lambda req: httpx.Response(200, headers={"content-type": "text/html"}, text="<html><body>Sign in to GitHub</body></html>"))
    with pytest.raises(Exception):
        P.complete("s", "t", transport=t)
    text = view("github")["state_text"]
    assert "answered 200 without a chat reply (text/html: <html><body>Sign in to GitHub" in text
    assert "empty reply" not in text


def test_a_model_list_that_is_not_a_list_says_what_it_was(monkeypatch):
    keys(monkeypatch, "github")
    t = httpx.MockTransport(lambda req: httpx.Response(200, headers={"content-type": "text/plain"}, text="OK"))
    with pytest.raises(C.CallError) as e:
        C.client("github", t).models(9e18)
    assert e.value.detail == "sent something that isn't a model list (200, text/plain: OK)"


def test_a_redirected_model_list_says_where_it_went(monkeypatch):
    keys(monkeypatch, "github")
    t = httpx.MockTransport(lambda req: httpx.Response(301, headers={"location": "https://github.com/marketplace/models"}))
    with pytest.raises(C.CallError) as e:
        C.client("github", t).models(9e18)
    assert "301: moved to https://github.com/marketplace/models" in e.value.detail


# ---------- SambaNova and OpenRouter: rate limits aren't "down" ----------
def test_a_short_rate_limit_is_not_listed_as_down(monkeypatch):
    keys(monkeypatch, "openrouter")
    calls = []

    def handler(req):
        calls.append(1)
        if len(calls) == 1:
            return chat()
        return httpx.Response(429, json={"error": {"message": "Rate limit exceeded: limit_rpm/meta-llama/llama-3.3-70b-instruct:free"}})
    t = httpx.MockTransport(handler)
    P.complete("s", "t1", transport=t)
    with pytest.raises(Exception):
        P.complete("s", "t2", transport=t)
    h = health("openrouter")
    assert h["answering"] is True and "429: Rate limit exceeded" in h["state_text"]


# ---------- NVIDIA: catalog models the free account isn't served ----------
def test_nvidia_leaves_out_catalog_models_it_does_not_serve():
    for m in ("writer/palmyra-fin-70b-32k", "writer/palmyra-creative-122b", "meta/llama2-70b", "nvidia/llama3-chatqa-1.5-70b"):
        assert unusable("nvidia", m), m
    assert not unusable("nvidia", "meta/llama-3.3-70b-instruct")


def test_one_unserved_model_does_not_make_nvidia_down(monkeypatch):
    keys(monkeypatch, "nvidia")
    R.record_ok("nvidia", "meta/llama-3.3-70b-instruct", 900, live=False)
    R.record_fail("nvidia", "writer/palmyra-x", C.CallError("model", "couldn't use writer/palmyra-x (404: Function 'f': Not found for account 'a')"))
    h = health("nvidia")
    assert h["answering"] is True and "isn't available to this key" in h["state_text"]


# ---------- every error says its status code ----------
def test_errors_carry_the_status_code_and_the_providers_words(monkeypatch):
    keys(monkeypatch, "groq")
    r = httpx.Response(401, json={"error": {"message": "Invalid API Key k-groq"}})
    e = C.classify("groq", r, "m")
    assert e.kind == "auth" and e.detail == "rejected the key (401: Invalid API Key [key])"
    e = C.classify("groq", httpx.Response(429, json={"error": {"message": "slow down"}}), "m")
    assert e.detail.endswith("(429: slow down)")
    e = C.classify("groq", httpx.Response(403, json={"error": {"message": "model blocked"}}), "m")
    assert e.detail == "this key can't use m (403: model blocked)"
