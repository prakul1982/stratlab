"""LIVE5-005: an AI read's "What to watch: No ex-dividend date or shareholder meeting date is given in the FACTS." showed the prompt's
own word to people. Every AI reply goes through ai_text.clean_reply."""
import json

from app import ai_providers
from app.ai_text import clean_reply, has_jargon


def test_a_sentence_about_the_prompt_is_taken_out_of_a_json_reply():
    reply = json.dumps({"summary": "HDFC Bank's loans grew 12% a year. Its deposits grew 14%.",
                        "watch": ["What to watch: No ex-dividend date or shareholder meeting date is given in the FACTS.",
                                  "Results are due on 18 Jan. The data provided does not include a dividend date."]})
    got = json.loads(clean_reply(reply))
    assert got["summary"] == "HDFC Bank's loans grew 12% a year. Its deposits grew 14%."
    assert got["watch"][0] == ""
    assert got["watch"][1].strip() == "Results are due on 18 Jan."
    assert not has_jargon(json.dumps(got))


def test_plain_text_replies_and_rupees():
    text = "FIIs bought shares worth Rs 14,975 crore and DIIs sold Rs. 10,445 crore. As per the FACTS, nothing else is known."
    out = clean_reply(text)
    assert out == "FIIs bought shares worth ₹14,975 crore and DIIs sold ₹10,445 crore."
    assert clean_reply("Revenue rose 12% (Rs 4,120 crore).") == "Revenue rose 12% (₹4,120 crore)."


def test_ordinary_text_is_left_alone():
    for t in ["The facts of the quarter: sales rose 9%.", "Mrs. Rao chairs the board.", '{"a": "Facts only."}', "", "RSI is 61."]:
        assert clean_reply(t) == t


def test_complete_passes_every_reply_through_it(monkeypatch):
    monkeypatch.setattr(ai_providers, "_complete", lambda *a, **k: '{"watch": ["No meeting date is given in the FACTS."], "x": "Rs 5 crore"}')
    got = json.loads(ai_providers.complete("s", "t"))
    assert got == {"watch": [""], "x": "₹5 crore"}


def test_a_flow_row_about_the_other_institutions_is_dropped_and_names_keep_their_capital():
    """LIVE5-009: "FIIs net buyers on Nov 5 | inflow | Domestic institutions were net sellers…"; "Main story: sensex Nifty rally"."""
    from app.intel import grounding
    from app.intel.ai import same_side
    assert not same_side("FIIs net buyers on Nov 5", "Domestic institutions were net sellers of ₹10,445 crore.")
    assert same_side("FIIs net buyers on Nov 5", "Foreign investors bought ₹14,975 crore; DIIs sold.")
    assert same_side("Broad sector gains", "Metals and banks rose.")
    assert not same_side("DIIs keep buying", "FPIs sold shares worth ₹3,000 crore.")
    titles = ["Sensex, Nifty rally as banks gain", "Markets: Sensex Nifty rally on FII buying", "Gold steady"]
    st = grounding.story_of("Sensex Nifty rally", titles)
    assert st and st["label"].startswith("Sensex")
    assert grounding.story_of("crude oil", ["Crude oil jumps", "Crude oil at a high", "x"])["label"] == "crude oil"
