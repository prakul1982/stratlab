"""A second Claude key (owner, 12 Nov): ANTHROPIC_API_KEY_2 has its own $100 of credit a month and is asked first, for every
Claude request, until its own meter reaches ANTHROPIC_2_CREDIT_USD or the API says its credit is gone; then
ANTHROPIC_API_KEY answers under today's rules. Fake transports only: no test reaches the real Anthropic API, and the keys
here are made-up strings."""
import json
import time

import httpx
import pytest

from app import ai_clients as C
from app import ai_providers as P
from app import ai_rank as R
from app import ai_spend as S
from app.ai_catalog import PROVIDERS, configured
from app.config import settings

GOOD = json.dumps({"entry": [{"l": {"t": "price"}, "op": "gt", "r": {"t": "sma", "p": 50}}], "mentioned": []})
KEYS = [p.key_env for p in PROVIDERS.values()] + ["CLOUDFLARE_ACCOUNT_ID", "ANTHROPIC_API_KEY_2"]
USAGE = {"input_tokens": 1000, "output_tokens": 500, "cache_creation_input_tokens": 2000, "cache_read_input_tokens": 4000}
K1 = "sk-test-first-key-0000000000aaaa"
K2 = "sk-test-second-key-000000000bbbb"
SONNET, HAIKU = "claude-sonnet-5-5", "claude-haiku-5-5"


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
    monkeypatch.setattr(settings, "ANTHROPIC_2_CREDIT_USD", 100.0)
    monkeypatch.setattr(settings, "AI_QUICK_BEFORE_CLAUDE", "groq")
    monkeypatch.setattr(P, "_sleep", lambda s: None)


def both(monkeypatch, one: bool = True, two: bool = True):
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", K1 if one else "")
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY_2", K2 if two else "")


def spent1(usd: float):
    S._current()["micros"] = round(usd * 1e6)


def spent2(usd: float):
    S._current2()["micros"] = round(usd * 1e6)


def claude(sent: list, answers: dict | None = None):
    """A fake Messages API: records which key each request carried (as "k1"/"k2") and its model; `answers` maps a key name
    to (status, body) for an error answer, else a good reply."""
    def handler(req: httpx.Request):
        who = {K1: "k1", K2: "k2"}.get(req.headers.get("x-api-key"), "other")
        sent.append((who, json.loads(req.content)["model"]))
        if answers and who in answers:
            code, body = answers[who]
            return httpx.Response(code, json=body)
        return httpx.Response(200, json={"content": [{"type": "text", "text": GOOD}], "stop_reason": "end_turn", "usage": USAGE})
    return httpx.MockTransport(handler)


def ask(transport, model=SONNET, task="research", system="s", max_tokens=100):
    return C.AnthropicHTTP(transport=transport).call(model, system, "t", max_tokens, True, time.time() + 20, task=task)


LOW_CREDIT = (400, {"type": "error", "error": {"type": "invalid_request_error",
                                               "message": "Your credit balance is too low to access the Anthropic API. "
                                                          "Please go to Plans & Billing to upgrade or purchase credits."}})


# ---------- without a second key nothing changes ----------
def test_without_a_second_key_everything_is_as_before(monkeypatch):
    both(monkeypatch, two=False)
    assert configured("anthropic") and not S.key2_active() and S._current2() is None
    assert P.plan("research")[:2] == [("anthropic", SONNET), ("anthropic", HAIKU)]
    spent1(80.0)
    assert P.plan("research")[0] == ("anthropic", HAIKU) and ("anthropic", SONNET) not in P.plan("long")
    sent = []
    ask(claude(sent), model=HAIKU)
    assert sent == [("k1", HAIKU)]
    assert not any(k.startswith("ai:spend2:") for k in R.STORE.data)                # nothing kept for a key that isn't set
    spent1(99.0)
    assert S.claude_models("research") == [] and all(n != "anthropic" for n, _ in P.plan("long"))
    with pytest.raises(C.CallError) as e:
        ask(claude(sent), model=HAIKU)
    assert e.value.kind == "credit" and "budget" in e.value.detail and len(sent) == 1
    v = S.view()
    assert v["active_key"] is None and v["budget_usd"] == 99.0 and v["keys"][1]["configured"] is False
    assert v["keys"][1]["state"] == "off" and v["keys"][0]["state"] == "spent"


def test_without_a_second_key_the_provider_still_needs_the_first():
    assert not configured("anthropic")


# ---------- the second key is asked first ----------
def test_the_second_key_answers_first_and_its_spend_is_its_own(monkeypatch):
    both(monkeypatch)
    sent = []
    out = P.complete("s", "t", kind="research", transport=claude(sent))
    assert "entry" in out and sent == [("k2", SONNET)]
    cost = S.cost_micros(SONNET, USAGE)
    stored = json.loads(R.STORE.data["ai:spend2:" + S.month()])
    assert stored["micros"] == cost and stored["requests"] == 1 and stored["key"] == S._sig(K2)
    assert K2 not in R.STORE.data["ai:spend2:" + S.month()]                            # a short hash, never the key
    assert S.spent_usd() == 0 and "ai:spend:" + S.month() not in R.STORE.data          # nothing billed to the first key


def test_the_second_key_uses_sonnet_whatever_the_first_key_spent(monkeypatch):
    both(monkeypatch)
    spent1(80.0)                                                                       # the first key is past its Sonnet limit
    for task in ("research", "long"):
        assert P.plan(task)[:2] == [("anthropic", SONNET), ("anthropic", HAIKU)]
    assert ("anthropic", SONNET) not in P.plan("quick")                                # quick jobs: Haiku, as before
    assert ("anthropic", SONNET) not in P.plan("long", bulk=True)                      # background jobs: Haiku only, as before
    spent1(99.0)                                                                       # even at the first key's cap
    sent = []
    ask(claude(sent))
    assert sent == [("k2", SONNET)] and S.view()["tier"] == "off"                    # the first key's tier is its own


def test_the_second_key_spend_never_counts_toward_the_first_keys_cap_or_tier(monkeypatch):
    both(monkeypatch)
    monkeypatch.setattr(settings, "ANTHROPIC_2_CREDIT_USD", 500.0)
    spent2(150.0)                                                                      # more than the first key's whole cap
    sent = []
    ask(claude(sent))
    assert sent == [("k2", SONNET)]
    v = S.view()
    assert v["usd"] == 0 and v["tier"] == "sonnet" and v["keys"][1]["usd"] > 150
    S.mark_spent("test")                                                               # now the first key: still Sonnet first
    assert S.claude_models("research") == [SONNET, HAIKU]
    ask(claude(sent))
    assert sent[-1] == ("k1", SONNET) and S.spent_usd() == S.cost_micros(SONNET, USAGE) / 1e6


# ---------- it switches to the first key ----------
@pytest.mark.parametrize("answer", [
    LOW_CREDIT,
    (401, {"type": "error", "error": {"type": "authentication_error", "message": "invalid x-api-key"}}),
    (402, {"type": "error", "error": {"type": "billing_error", "message": "Payment required"}}),
    (400, {"type": "error", "error": {"type": "invalid_request_error",
                                      "message": "You have reached your specified API usage limits. You will regain access on 2026-12-01."}}),
])
def test_out_of_credit_billing_or_a_rejected_second_key_switches_to_the_first_in_the_same_request(monkeypatch, answer):
    both(monkeypatch)
    sent = []
    t = claude(sent, {"k2": answer})
    out = P.complete("s", "t", kind="research", transport=t)
    assert "entry" in out and sent == [("k2", SONNET), ("k1", SONNET)]               # the same request, at once
    assert R.ready("anthropic", SONNET) == 0 and R.status("anthropic").cooldown_until < time.time()   # no breaker opened
    assert not S.key2_active()
    k2 = S.keys_view()[1]
    assert k2["state"] == "spent" and k2["spent_reason"] and K2 not in json.dumps(k2)
    assert S.spent_usd() == S.cost_micros(SONNET, USAGE) / 1e6                         # billed to the first key
    P.complete("s", "t2", kind="research", transport=t)
    assert sent[-1] == ("k1", SONNET) and len(sent) == 3                              # the second key isn't asked again


def test_a_rate_limit_or_server_error_on_the_second_key_does_not_spend_it(monkeypatch):
    both(monkeypatch)
    sent = []
    rate = (429, {"type": "error", "error": {"type": "rate_limit_error", "message": "rate limit; see billing docs"}})
    with pytest.raises(C.CallError) as e:
        ask(claude(sent, {"k2": rate}))
    assert e.value.kind == "rate" and S.key2_active() and sent == [("k2", SONNET)]
    with pytest.raises(C.CallError) as e:
        ask(claude(sent, {"k2": (529, {"type": "error", "error": {"type": "overloaded_error", "message": "Overloaded"}})}))
    assert S.key2_active() and sent[-1][0] == "k2"


def test_reaching_the_second_keys_credit_switches_to_the_first(monkeypatch):
    both(monkeypatch)
    spent2(99.4995)
    sent = []
    ask(claude(sent), model=HAIKU, task="quick")                                       # this reply leaves under 50 cents of $100
    assert sent == [("k2", HAIKU)] and not S.key2_active()
    assert "credit for this month is spent" in S.keys_view()[1]["state_text"]
    spent1(80.0)                                                                       # from here the first key's own tier
    assert P.plan("research")[0] == ("anthropic", HAIKU) and ("anthropic", SONNET) not in P.plan("research")
    ask(claude(sent), model=HAIKU)
    assert sent[-1] == ("k1", HAIKU)


def test_a_request_too_dear_for_what_is_left_goes_to_the_first_key_only_where_its_tier_allows(monkeypatch):
    both(monkeypatch)
    spent2(99.45)                                                                      # 55 cents left: active, but a long Sonnet read won't fit
    sent = []
    ask(claude(sent), system="s" * 400_000, max_tokens=8000)
    assert sent == [("k1", SONNET)]                                                    # the first key is under its Sonnet limit
    spent1(80.0)
    with pytest.raises(C.CallError) as e:
        ask(claude(sent), system="s" * 400_000, max_tokens=8000)
    assert e.value.kind == "tier" and len(sent) == 1                                  # not sent: Sonnet is past the first key's limit
    R.record_fail("anthropic", SONNET, e.value)
    assert R.ready("anthropic", SONNET) == 0                                           # and no breaker: Haiku is asked next
    P.complete("s" * 400_000, "t", kind="research", transport=claude(sent))
    assert sent[1:] == [("k2", HAIKU)]                                                # Haiku fits what's left of the second key
    S._state2["data"]["micros"] = round(99.0 * 1e6)
    sent.clear()
    P.complete("s" * 400_000, "t2", kind="research", transport=claude(sent))
    assert sent == [("k2", SONNET)]


def test_only_a_second_key_works_until_it_is_spent(monkeypatch):
    both(monkeypatch, one=False)
    assert configured("anthropic") and P.plan("research")[0] == ("anthropic", SONNET)
    sent = []
    ask(claude(sent))
    assert sent == [("k2", SONNET)]
    with pytest.raises(C.CallError) as e:
        ask(claude(sent, {"k2": LOW_CREDIT}))
    assert e.value.kind == "credit" and "ANTHROPIC_API_KEY isn't set" in e.value.detail
    assert S.claude_models("research") == [] and all(n != "anthropic" for n, _ in P.plan("research"))


# ---------- kept across restarts, for the month or until the key changes ----------
def test_the_second_keys_state_survives_a_restart_and_resets_with_the_month_or_a_new_key(monkeypatch):
    both(monkeypatch)
    sent = []
    ask(claude(sent))
    ask(claude(sent, {"k2": LOW_CREDIT}))
    before = S.keys_view()[1]
    assert before["state"] == "spent" and before["requests"] == 1
    S.reset()                                                                          # a restart
    after = S.keys_view()[1]
    assert after["state"] == "spent" and after["usd"] == before["usd"] and after["spent_reason"] == before["spent_reason"]
    assert not S.key2_active()
    now = time.time()
    with monkeypatch.context() as m:
        m.setattr(S.time, "time", lambda: S.month_end(now) + 5)                        # the month turns: fresh credit
        assert S.key2_active() and S.keys_view()[1]["usd"] == 0
    S.reset()
    assert not S.key2_active()                                                         # back in this month: still spent
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY_2", "sk-test-a-new-second-key-0cccc")  # a new key value: counted afresh
    assert S.key2_active() and S.keys_view()[1]["usd"] == 0 and S.keys_view()[1]["fingerprint"] == "…cccc"


# ---------- Admin shows both keys ----------
def test_admin_shows_both_keys_side_by_side_without_their_values(monkeypatch):
    both(monkeypatch)
    sent = []
    ask(claude(sent))
    spent1(10.0)
    view = P.admin_view()
    c = view["claude"]
    assert c["active_key"] == 2 and c["budget_usd"] == 199.0 and c["usd"] == 10.0
    k1, k2 = c["keys"]
    assert (k1["variable"], k1["state"], k1["fingerprint"], k1["credit_usd"]) == ("ANTHROPIC_API_KEY", "standby", "…aaaa", 99.0)
    assert (k2["variable"], k2["state"], k2["fingerprint"], k2["credit_usd"]) == ("ANTHROPIC_API_KEY_2", "active", "…bbbb", 100.0)
    assert k2["usd"] == round(S.cost_micros(SONNET, USAGE) / 1e6, 4) and k2["requests"] == 1 and SONNET in k2["models"]
    assert c["budget_spent_usd"] == round(10.0 + k2["usd"], 4)
    row = next(p for p in view["providers"] if p["name"] == "anthropic")
    assert row["keys"] == c["keys"] and "ANTHROPIC_API_KEY_2" in row["variables"]
    assert all(p["keys"] is None for p in view["providers"] if p["name"] != "anthropic")
    page = json.dumps(view)
    assert K1 not in page and K2 not in page and K1[:-4] not in page and K2[:-4] not in page
    S.mark_spent("credit balance is too low")
    c = P.admin_view()["claude"]
    assert c["active_key"] == 1 and [k["state"] for k in c["keys"]] == ["active", "spent"]


def test_an_error_that_echoes_the_second_key_never_shows_it(monkeypatch):
    both(monkeypatch)
    sent = []
    ask(claude(sent, {"k2": (401, {"type": "error", "error": {"type": "authentication_error",
                                                               "message": f"invalid x-api-key {K2}"}})}))
    assert sent[-1][0] == "k1"
    assert K2 not in json.dumps(P.admin_view()) and K2 not in json.dumps(dict(R.STORE.data))
