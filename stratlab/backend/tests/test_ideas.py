from fastapi.testclient import TestClient

from app import db, ideas, main
from app.ai_providers import AIBusy
from app.intel import ai as A


def test_clean_and_market_guess():
    raw = {"ideas": [{"title": "T", "text": "Buy BTC when RSI < 30", "why": "w", "market": "crypto", "symbol": "BTC-USD", "tf": "4h"},
                     {"title": "x", "text": ""}, "junk", {"text": "Buy NIFTY on a 20/50 EMA cross", "symbol": "null"}]}
    out = ideas.clean(raw, "bitcoin dips")
    assert len(out) == 2 and out[0]["market"] == "CRYPTO" and out[0]["tf"] == "1d" and out[1]["symbol"] is None
    assert ideas.guess_market("momentum on nasdaq stocks") == "US" and ideas.guess_market("bank nifty") == "IN"
    assert ideas.key("  Bank   NIFTY ") == ideas.key("bank nifty")


def test_route_uses_ai_then_falls_back(monkeypatch):
    main.app.dependency_overrides[main.current_profile] = lambda: {"id": "u1", "_plan": "free", "plan": "free"}
    monkeypatch.setattr(db, "count_usage", lambda *a, **k: 0)
    monkeypatch.setattr(db, "add_usage", lambda *a, **k: None)
    A._cache.clear()
    calls = []
    monkeypatch.setattr(main, "ask_json", lambda s, t, n: calls.append(t) or {"ideas": [{"title": "EMA", "text": "Buy RELIANCE on a 20/50 EMA cross", "market": "IN", "symbol": "RELIANCE"}]})
    try:
        c = TestClient(main.app)
        r = c.post("/search/ideas", json={"q": "reliance swing ideas"}).json()
        assert not r["fallback"] and r["ideas"][0]["symbol"] == "RELIANCE"
        c.post("/search/ideas", json={"q": "Reliance  swing ideas"})
        assert len(calls) == 1                                  # cached for the same question

        def busy(*a):
            raise AIBusy("all providers busy")
        monkeypatch.setattr(main, "ask_json", busy)
        r = c.post("/search/ideas", json={"q": "crypto breakouts"}).json()
        assert r["fallback"] and len(r["ideas"]) == 4 and r["ideas"][0]["market"] == "CRYPTO"
    finally:
        main.app.dependency_overrides.clear()


def test_long_queries_sharing_a_prefix_get_their_own_answers():
    a, b = "x" * 300 + " semis", "x" * 300 + " banks"
    assert ideas.key(a) == ideas.key(b)                                    # the AI is sent only the first 300: the same text
    assert ideas.key("y" * 250 + "a") != ideas.key("y" * 250 + "b")        # but within them, different queries differ


def test_ideas_market_guess_ignores_text_past_the_cache_key():
    head = "momentum ideas " + "x" * 300
    out = ideas.build(lambda s, t, n: {"ideas": [{"text": "buy when rsi < 30"}]}, head + " bitcoin crypto")
    assert out["ideas"][0]["market"] == ideas.guess_market(head[:300]) and ideas.key(head + "a") == ideas.key(head + "b")
