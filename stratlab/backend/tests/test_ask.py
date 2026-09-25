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
