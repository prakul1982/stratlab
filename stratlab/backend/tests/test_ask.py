from app import ask


def test_word_rules_pick_a_sensible_action():
    g = lambda q: ask.guess(q)["action"]
    assert g("buy reliance when rsi drops below 30, sell above 55") == "test"
    assert g("paper trade EMA 20/50 cross on BTC") == "paper"
    assert ask.guess("paper trade EMA 20/50 cross on BTC")["text"].startswith("EMA 20/50")
    assert g("what is RSI?") == "answer"
    assert g("how does walk forward work") == "answer"
    assert g("momentum ideas for bank stocks") == "ideas"
    assert g("nifty iron condor") == "options"
    assert g("library rsi") == "library"
    assert g("reliance fundamentals") == "research"
    assert ask.guess("reliance fundamentals")["symbol"] == "reliance"
    assert g("paper") == "open" and ask.guess("open plans")["page"] == "plans"
    assert g("gold") == "ideas"                                          # anything else: ideas, never nothing


def test_ai_answers_are_checked_and_bad_ones_fall_back():
    ok = ask.clean({"action": "test", "text": "Buy BTC when...", "market": "crypto", "symbol": "BTC-USD", "title": "Test it"}, "q")
    assert ok["action"] == "test" and ok["market"] == "CRYPTO" and ok["symbol"] == "BTC-USD"
    assert ask.clean({"action": "hack"}, "what is rsi?")["action"] == "answer"         # unknown action → word rules
    assert ask.clean({"action": "answer", "answer": ""}, "buy x when rsi < 30 then sell")["action"] == "test"
    assert ask.clean({"action": "open", "page": "../admin"}, "gold")["action"] == "ideas"
    assert ask.clean({"action": "research", "symbol": "null"}, "banks")["action"] == "ideas"
    assert ask.clean({"action": "answer", "answer": "RSI measures..." * 200}, "q")["answer"].__len__() == 1200
    assert ask.looks_like_code("//@version=5\nstrategy('x')") and not ask.looks_like_code("buy when rsi < 30")


def test_ask_key_covers_exactly_the_text_the_ai_is_sent():
    assert ask.key("z" * 350 + "a") != ask.key("z" * 350 + "b")            # both inside the 400 sent
    assert ask.key("z" * 400 + "a") == ask.key("z" * 400 + "b")


def test_answer_drops_advice_sentences():
    a = ask.clean({"action": "answer", "answer": "RSI measures recent gains against losses. You should buy the stock when it dips. "
                                                 "It runs from 0 to 100."}, "what is rsi?")["answer"]
    assert a == "RSI measures recent gains against losses. It runs from 0 to 100."
    # nothing left once the advice is out: the word rules answer instead
    assert ask.clean({"action": "answer", "answer": "Buy the stock now."}, "buy x when rsi < 30 then sell")["action"] == "test"


def test_cached_answer_is_built_from_the_keyed_text_only():
    head = "x" * 400
    a = ask.build(lambda s, t, n: {"action": "test", "text": ""}, head + " secret tail one")
    assert a["text"] == head and ask.key(head + " one") == ask.key(head + " two")


# ---------- acct4: an answer explaining how trading works is kept; only a recommendation is dropped ----------
SHORT = "Short selling means borrowing shares and selling them first. You buy them back later to return them."
BREAKOUT = ("A breakout strategy enters when the price closes above a recent range. Breakouts that fail are common, "
            "so a stop is usual.")


def test_an_answer_about_how_trading_works_is_kept_whole():
    assert ask.clean({"action": "answer", "answer": SHORT}, "what is short selling?")["answer"] == SHORT
    assert ask.clean({"action": "answer", "answer": BREAKOUT}, "how does a breakout strategy work?")["answer"] == BREAKOUT


def test_a_recommendation_about_a_named_stock_or_a_target_is_still_dropped():
    a = ask.clean({"action": "answer", "answer": "A target is where a trade is closed. Buy RELIANCE now, target 3000. "
                                                 "TCS is undervalued."}, "what is a target?")["answer"]
    assert a == "A target is where a trade is closed."
    import pytest
    from app.ai_reply import AIError
    with pytest.raises(AIError):                       # nothing left: the AI's reply failed, it isn't an answer to keep
        ask.build(lambda s, t, n: {"action": "answer", "answer": "Buy RELIANCE now, target 3000."}, "should I buy reliance?")


def test_an_emptied_answer_is_neither_counted_nor_cached(monkeypatch):
    from app import db, main
    from tests import fake_db, world
    w = world.build(monkeypatch)
    try:
        replies = [{"action": "answer", "answer": "Buy RELIANCE now, target 3000."}, {"action": "answer", "answer": SHORT}]
        monkeypatch.setattr(main, "ask_json", lambda s, t, n=700: replies.pop(0))
        c, H = w["client"], fake_db.headers("free-token")
        first = c.post("/ask", json={"q": "what is short selling?"}, headers=H).json()
        assert first["fallback"] is True and "answer" not in first
        assert db.count_usage("u-free", "search_ai", "2000-01-01") == 0
        again = c.post("/ask", json={"q": "what is short selling?"}, headers=H).json()      # not cached: asked afresh
        assert again["answer"] == SHORT and again["fallback"] is False
        assert db.count_usage("u-free", "search_ai", "2000-01-01") == 1
    finally:
        w["close"]()


# ---------- rev7b: a recommendation about any named company, in any case, is dropped ----------
def test_advice_about_any_named_company_is_dropped():
    for s in ("Tata Motors is a strong buy.", "Consider buying SBI before results.", "Go long on Apple now.",
              "Reliance looks like a bargain at this level.", "Nifty will hit 25000 by December.",
              "Many analysts say Infosys is undervalued.", "Analysts say Apple could double from here."):
        assert ask.recommends(s), s


def test_education_answers_still_pass_the_ask_filter():
    for s in (SHORT, BREAKOUT, "Buy and hold means keeping shares for years.", "RSI above 70 is often read as overbought.",
              "In StratLab you can backtest a rule on Indian stocks.", "A stop loss sells a position when price falls to a set level.",
              "Your money will double in about 72 divided by the rate years."):
        assert not ask.recommends(s), s
    a = ask.clean({"action": "answer", "answer": "RSI runs from 0 to 100. Tata Motors is a strong buy."}, "what is rsi?")["answer"]
    assert a == "RSI runs from 0 to 100."
