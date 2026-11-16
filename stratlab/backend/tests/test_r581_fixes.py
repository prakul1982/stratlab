"""R58.1 (lane r581): the open items after R58. Each test fails on de3273b (R58) and passes after."""
import sys
import pathlib
import types

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))

from app import ai_rank, ai_reply  # noqa: E402
from app.intel import theme_base as B  # noqa: E402
import release_gate as G  # noqa: E402


# ---- 1. AMS: a company the last re-check moved out of a layer is new to it again (sold_what) ----
def _sold(moved_before):
    words = {"X": "The company delivers radiation therapy through medical equipment leasing and direct patient services, its two "
                  "reportable segments, at sites in several countries.",
             "Y": "We run clinical diagnostic laboratories that perform genetic testing for physicians and hospitals."}
    out = [{"layer": "Diagnostic and genetic testing labs", "description": "", "companies": [
                {"ticker": "Y", "name": "Y Labs", "industry": "Services-Medical Laboratories"},
                {"ticker": "X", "name": "X Shared Services", "industry": "Services-Medical Laboratories", "moved": True}]},
           {"layer": "Implants and electrotherapy devices", "description": "", "companies": [{"ticker": "Z", "name": "Z Implants"}]},
           {"layer": "Other medical device companies", "description": "", "official": True, "basis": "rest", "companies": []}]
    got = B.sold_what(out, {}, lambda v: False, lambda cos: "", lambda c: "", lambda c: words.get(c.get("ticker"), ""),
                      B.kind_stems("Medical devices"), "Medical devices", {}, None, moved_before)
    return {c["ticker"]: (v["layer"], c.get("refit")) for v in got for c in v["companies"]}


def test_a_company_moved_out_by_the_last_recheck_is_judged_when_put_back():
    got = _sold({"X": ["Diagnostic and genetic testing labs", "Other medical device companies"]})
    assert got["X"][0] == "Other medical device companies"
    assert got["X"][1]["from"] == "Diagnostic and genetic testing labs" and "its own words don't say" in got["X"][1]["why"]
    assert got["Y"][0] == "Diagnostic and genetic testing labs"          # (guard) one never moved stays


def test_a_guard_no_memory_moves_nobody():
    assert _sold({})["X"][0] == "Diagnostic and genetic testing labs"


# ---- 1. TFSL, COLB, FLG: the replay hands a layer renamed in place on under the map's name the kept answer names ----
def test_a_layer_renamed_in_place_is_handed_on_under_its_map_name():
    d = {"theme": "Regional banks", "placements": {},
         "kept": {"assign": {"A": {"layer": "Real estate-focused lenders", "by": "ai"}, "B": {"layer": "Commercial lenders", "by": "ai"}}},
         "value_chain": [
             {"layer": "Real estate-focused lenders (bank)", "aka": ["Real estate-focused lenders"], "companies": [{"ticker": "A"}]},
             {"layer": "Commercial lenders", "companies": [{"ticker": "B"}]},
             {"layer": "Savings institutions", "official": True, "companies": []}]}
    names = [v["layer"] for v in G.pre_map(d)["value_chain"]]
    assert "Real estate-focused lenders" in names and "Real estate-focused lenders (bank)" not in names


def test_a_guard_an_aka_that_is_no_bracket_form_is_left():
    d = {"theme": "T", "placements": {}, "kept": {"assign": {"A": {"layer": "Old name", "by": "ai"}}},
         "value_chain": [{"layer": "New name", "aka": ["Old name"], "companies": [{"ticker": "A"}]}]}
    assert [v["layer"] for v in G.pre_map(d)["value_chain"]] == ["New name"]


# ---- 1. a name none of whose words would stay keeps the word in brackets ----
def test_a_name_with_no_word_left_is_not_renamed_in_place():
    banks = ["We are a bank holding company. The Bank takes deposits and makes loans.", "A savings bank with branches."]
    assert B.in_place_name("Real estate-focused lenders", "bank", banks) == ""             # R58: "Bank-focused"
    assert B.in_place_name("Commercial and business lenders", "bank", ["commercial bank serving business customers"]) == \
        "Commercial and business banks"                                                    # (guard) R58's own case
    assert B.in_place_name("Commercial airframe integration", "aircraft", ["commercial aircraft maker"]) == "Commercial aircraft"


# ---- 2. Cyber: a rename that only adds words most of its largest companies don't say is not made ----
def test_a_widened_rename_its_companies_dont_say_keeps_the_name_it_had():
    words = {"OKTA": "Okta is an identity and access management company. It provides cloud software that helps companies manage and "
                     "secure user authentication into applications.",
             "SAIL": "SailPoint delivers solutions to enable adaptive identity security for the enterprise, unifying identity data "
                     "across systems and access across identity types.",
             "CYBR": ""}
    vc = [{"layer": "Identity access and broad enterprise software", "was": "Identity and access software", "description": "",
           "companies": [{"ticker": s, "name": s, "cap": cap, "industry": "Services-Prepackaged Software"}
                         for s, cap in (("OKTA", 30000), ("SAIL", 12000), ("CYBR", None))]},
          {"layer": "Endpoint and detection platforms", "description": "", "companies": [{"ticker": "E", "name": "E", "cap": 1}]}]
    out, rows = B.truthful_layers(vc, {}, lambda s: words.get(s, ""), "Cybersecurity")
    assert out[0]["layer"] == "Identity and access software"
    assert any(r.get("renamed") == "Identity and access software" and "adds" in r["why"] for r in rows)


# ---- 4. Aerospace: a company kept on its own words against one layer's answer quotes them ----
def test_a_company_kept_on_its_words_quotes_the_sentence_that_says_the_theme():
    tw = B.kind_stems("Aerospace and defense")
    cw = ("Curtiss-Wright Corporation is a Delaware corporation, with its principal executive office in Davidson, North Carolina. "
          "Curtiss-Wright Corporation is a global integrated business that provides highly engineered products, solutions, and services "
          "mainly to Aerospace & Defense markets, as well as critical technologies in demanding commercial power, process, and industrial "
          "markets.")
    q = B.theme_clause(cw, "Curtiss Wright Corp", tw)
    assert "Aerospace & Defense" in q and len(q) <= 200
    # its own name's words are no words of its work
    assert B.theme_clause("Howmet Aerospace Inc. is a Delaware corporation with its principal office in Pittsburgh.", "Howmet Aerospace Inc.",
                          tw) == ""


def test_a_kept_company_s_reason_quotes_its_words():
    vc = [{"layer": "Defense electronics", "description": "", "companies": [{"ticker": "P", "name": "P"}]},
          {"layer": "Other aerospace and defense companies", "official": True, "basis": "rest", "companies": []}]
    pl = {"dropped": [{"ticker": "Q", "name": "Q Corp", "groups": ["Defense electronics"], "said": "no"}]}
    words = {"Q": "Q Corp is a Delaware corporation. It makes guidance systems for missiles used by defense customers worldwide."}
    out, _ = B.layer_answer_removals(vc, pl, lambda s: words.get(s, ""), "Aerospace and defense", lambda s: {})
    why = next(c["theme"]["why"] for v in out for c in v["companies"] if c["ticker"] == "Q")
    assert "“It makes guidance systems for missiles used by defense customers worldwide”" in why


# ---- 5. AI: "reply wasn't the JSON asked for" ----
def test_a_reply_with_a_line_break_inside_a_string_is_read():
    assert ai_reply.extract_json('{"name": "Spinning mills", "description": "They spin yarn.\nThey sell it to weavers."}')["name"] == \
        "Spinning mills"
    assert ai_reply.extract_json('Here it is: {"a": "x\ty"} as asked.') == {"a": "x\ty"}


def test_a_reply_that_isnt_json_says_which_call_it_was(monkeypatch, capsys):
    class C:
        def call(self, *a, **k):
            return types.SimpleNamespace(text="Sorry, I can't answer that as JSON.", finish="stop", headers={})
    monkeypatch.setattr(ai_rank, "client", lambda name, transport=None: C())
    monkeypatch.setattr(ai_rank, "record_fail", lambda *a, **k: "")
    try:
        ai_rank.ask_model("anthropic", "m", "You place companies in layers. Reply with ONLY JSON.", "x", 100, True, 1e12, task="research")
    except ai_reply.BadReply as e:
        assert e.why == "not_json"
    line = capsys.readouterr().out
    assert "reply wasn't the JSON asked for: anthropic m (research)" in line and "You place companies" in line and "Sorry" in line
