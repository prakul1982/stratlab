"""The search box's AI calls have their own daily cap (a built-in answer past it), the market read takes no free-text
focus, and the daily AI-build cap comes back at midnight India time as the message says."""
import pytest
from fastapi import HTTPException

from app import db, main
from app.config import settings
from app.intel import ai as A, routes

FREE = {"id": "f", "email": "f@example.com", "plan": "free", "_plan": "free", "_paid_plan": "free"}


@pytest.fixture
def usage(monkeypatch):
    used: list[tuple[str, str]] = []
    monkeypatch.setattr(db, "count_usage", lambda u, k, since: sum(1 for uu, kk in used if uu == u and kk == k))
    monkeypatch.setattr(db, "add_usage", lambda u, k: used.append((u, k)))
    monkeypatch.setattr(settings, "RESEARCH_AI_PER_DAY", 2)
    monkeypatch.setattr(settings, "ADMIN_EMAILS", "")
    A._cache.clear()
    yield used
    A._cache.clear()


def test_search_ai_has_its_own_cap_and_falls_back(usage, monkeypatch):
    monkeypatch.setattr(routes, "SEARCH_AI_PER_DAY", 2)
    monkeypatch.setattr(main.ideas, "build", lambda ask_json, q: {"ideas": [{"title": q}]})
    monkeypatch.setattr(main.ask, "build", lambda ask_json, q: {"action": "answer", "answer": q, "title": "t"})
    assert main.search_ideas(main.IdeasReq(q="gold one"), FREE)["fallback"] is False
    assert main.ask_route(main.IdeasReq(q="what is two"), FREE)["fallback"] is False
    assert usage == [("f", "search_ai")] * 2                        # not the company reads' count
    assert main.search_ideas(main.IdeasReq(q="gold three"), FREE)["fallback"] is True      # 429 -> built-in ideas
    assert main.ask_route(main.IdeasReq(q="what is four"), FREE)["fallback"] is True
    assert main.search_ideas(main.IdeasReq(q="gold one"), FREE)["fallback"] is False       # a cached answer still opens
    assert routes.ai_reads_today(FREE) == 0                                                # company reads untouched
    assert routes.read_slot(FREE, routes.ai_cap(FREE)) is not None


def test_the_market_read_takes_no_focus(monkeypatch):
    with pytest.raises(HTTPException) as e:
        routes.pulse_ai("IN", "anything I like", False, FREE)
    assert e.value.status_code == 400 and e.value.detail["code"] == "bad_focus"
    import inspect
    assert "focused on" not in inspect.getsource(A.pulse)             # never in the system prompt


def test_the_daily_ai_build_message_says_when_it_comes_back(monkeypatch):
    monkeypatch.setattr(main, "AI_BUILDS_PER_DAY", 1)
    monkeypatch.setattr(db, "count_usage", lambda u, kind, since: 1 if since == routes.ai_day_start() else 0)
    with pytest.raises(HTTPException) as e:
        main.ai_allowance({"id": "p", "email": "p@x.com", "_plan": "pro"})
    assert e.value.detail["code"] == "ai_daily_limit" and "midnight India time" in e.value.detail["message"]


def test_at_the_search_limit_the_reader_gets_the_real_message(usage, monkeypatch):
    monkeypatch.setattr(routes, "SEARCH_AI_PER_DAY", 1)
    monkeypatch.setattr(main.ideas, "build", lambda ask_json, q: {"ideas": [{"title": q}]})
    monkeypatch.setattr(main.ask, "build", lambda ask_json, q: {"action": "answer", "answer": q, "title": "t"})
    main.ask_route(main.IdeasReq(q="what is one"), FREE)
    for out in (main.ask_route(main.IdeasReq(q="what is two"), FREE), main.search_ideas(main.IdeasReq(q="gold two"), FREE)):
        assert out["fallback"] is True and out["limit"] is True
        assert out["message"].startswith("You've used today's 1 AI answers") and "midnight India time" in out["message"]
    other = HTTPException(422, {"code": "ai_failed", "message": "No."})
    assert main.limit_notice(other) == {}                                   # another failure carries no limit message
