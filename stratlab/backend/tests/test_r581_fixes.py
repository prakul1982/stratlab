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


# ---- 6. the live R58 decks (deck_check on the 24 live decks) ----
def test_a_quote_ends_after_an_acronym_s_full_stop():
    from app.intel.theme_changes import first_sentence
    q = first_sentence("SBI Cards and Payment Services Limited is a non-deposit accepting systemically important nonbanking financial company "
                       "registered with the RBI. The Company is engaged in issuing credit cards to consumers.")
    assert q.endswith("registered with the RBI") and "The Company" not in q          # R58: ran on into "... credit cards to"
    assert first_sentence("It sells to the U.S. Army and others. Then more.") == "It sells to the U.S. Army and others"      # (guard)


def test_a_line_says_the_words_that_place_it_in_its_layer():
    pb = ("PB Fintech Ltd, popularly known as Policy Bazar is India's largest online platform for insurance and lending products through its "
          "flagship brands Business Model PB Fintech runs an asset-light, digital-first model for distributing and servicing financial products. "
          "It does not underwrite insurance.")
    assert B.layer_line("PB Fintech Ltd, popularly known as Policy Bazar is India's largest online platform for insurance", pb, "PB Fintech Limited",
                        "Distribution and aggregation") == \
        "PB Fintech runs an asset-light, digital-first model for distributing and servicing financial products"
    bio = ("Biocon is engaged in the business of manufacture of biotechnology products and research services.(Source : Annual Report) Business "
           "Segments: a) Biosimilars (60% in FY26): Biocon Biologics Ltd develops and markets a range of 20 biosimilars including insulins, "
           "monoclonal antibodies, and conjugated recombinant proteins.")
    got = B.layer_line("Biocon is engaged in the business of manufacture of biotechnology products and research services.", bio, "Biocon Limited",
                       "Biologics and novel drug developers")
    assert got == "Biocon Biologics Ltd develops and markets a range of 20 biosimilars including insulins"
    # (guard) a line that already says its layer's word stays
    assert B.layer_line("It provides endpoint security, threat intelligence", "It provides endpoint security. It also detects threats.",
                        "CrowdStrike", "Endpoint and detection platforms") == "It provides endpoint security, threat intelligence"


def test_a_filing_s_bracket_defining_its_own_name_is_no_line():
    got = B.own_words("(together with its consolidated subsidiaries, as appropriate, “SailPoint,” the “Company,” “our,” or “we”) delivers "
                      "solutions to enable adaptive identity security for the enterprise", "SailPoint, Inc.")
    assert got == "Delivers solutions to enable adaptive identity security for the enterprise"


def test_a_layer_emptied_by_companies_leaving_the_theme_says_why():
    from app import deck
    got = deck.removed_said({"from": ["Identity access and broad enterprise software (larger)"], "n": 6,
                             "went": {"": 5, "Identity access and broad enterprise software": 1}})
    assert got.endswith(", its companies out of the theme each removed with its own reason, 5 of its 6 companies")
    # (guard) a removal with the placement's own reason keeps it
    assert deck.removed_said({"from": ["X"], "n": 5, "went": {"Y": 5}, "why": "renamed"}).endswith(", renamed")


def test_a_layer_kept_from_the_published_version_is_back_not_added():
    from app.intel import theme_changes as TC
    was = {"layers": ["Life insurance"], "cos": {"A": ["A", 0, 2025, 1.0, 1.0, "e"], "P": ["P", 0, 2025, 1.0, 1.0, "e"]}}
    now = {"layers": ["Life insurance", "Distribution and aggregation"], "cos": {"A": ["A", 0, 2025, 1.0, 1.0, "e"], "P": ["P", 1, 2025, 1.0, 1.0, "e"]},
           "kept_layers": {"Distribution and aggregation": "a layer of the published version, kept with its one member: its own words say its name"}}
    ev, _ = TC._layer_events(was, now)
    add = [e for e in ev if e["kind"] == "added"]
    assert add and add[0]["back"].startswith("a layer of the published version")
    snap = TC.snapshot({"layers": [{"layer": "Distribution and aggregation", "single_kept": "kept", "companies": [{"symbol": "P", "name": "P"}]}]})
    assert snap["kept_layers"] == {"Distribution and aggregation": "kept"}


def test_the_deck_check_reads_a_row_s_lines_above_its_layer_cell_as_the_layer_s():
    import deck_check as K
    page = "\n".join([
        " Layer                            Company                  What it does                     Revenue",
        "",
        "                                                           It provides endpoint security, threat",
        " Endpoint and detection           CrowdStrike Holdings,",
        "                                                           intelligence, and cyberattack       $4.81 bn",
        " platforms                        Inc.",
        "",
        "                                  SentinelOne, Inc.        for monitoring personal computers   $1.00 bn",
        "",
        "                                                           It provides cloud software that",
        " Identity and access              Okta, Inc.               helps companies manage identity     $2.92 bn",
        " software",
        ""])
    got = dict(K._small_layer_chunks(page))
    assert "endpoint security" in got["Endpoint and detection platforms"] and "SentinelOne" in got["Endpoint and detection platforms"]
    assert "cloud software" in got["Identity and access software"] and "cloud software" not in got["Endpoint and detection platforms"]


# ---- P0: a bank's revenue line below its net profit, from a page stored before R58, never reaches a deck ----
def _bank_theme():
    from tests.fake_theme_structures import _theme, _us

    def fact(i, sym, name, ind):
        f = _us(i, sym, name, "National Commercial Banks")
        f["bank"] = True
        if i == 0:                      # Fifth Third's stored pre-R58 page: $80 m of lessor income read as revenue, $2,522 m net profit
            f["years"][-1] = {**f["years"][-1], "sales": 80.0, "profit": 2522.0}
            f["v"] = 10
        return f
    return _theme("Regional banks", "US", [("Deposit-funded retail and commercial banks", "BK", "National Commercial Banks", 4, None)], fact)


def test_a_stored_pre_r58_bank_row_is_withheld_on_the_real_deck_path():
    from app import deck
    from app.intel import theme_data as D
    from app.intel import theme_routes as T
    from tests.test_export import plain
    from tests.test_r18_deck import NOW
    from tests.test_theme1 import TODAY
    m, f = _bank_theme()
    dive = D.build("US", "Regional banks", m, D.Sources(TODAY, facts=f.get))
    row = next(r for b in dive["layers"] for r in b["companies"] if r["symbol"] == "BK0")
    assert row["revenue"] is None and row["net"] is None and "above its revenue" in row["figure_errors"][0]
    other = next(r for b in dive["layers"] for r in b["companies"] if r["symbol"] == "BK1")
    assert other["revenue"] and other["net"] is not None and not other.get("figure_errors")          # (guard) a sound bank row is kept
    v = T.deck_view("US", m, dive)
    slides = deck.theme_plan(v, now=NOW)[0]
    text = " ".join(str(c) for s in slides for b in s.blocks if b.get("kind") == "table" for r in plain(b["rows"]) for c in r)
    assert "3152" not in text.replace(",", "") and "3,152" not in text and "$80 m" not in text


def test_a_mismatched_financial_page_is_built_again_and_its_theme_piece_taken_again(monkeypatch):
    from app import stock_pages as SP
    from app.intel import theme_routes as T
    from app.intel import routes as RR
    old = {"v": 10, "bank": True, "industry": ["National Commercial Banks"], "years": [{"year": "Dec 2025", "sales": 80.0, "profit": 2522.0}]}
    new = {"v": 10, "bank": True, "industry": ["National Commercial Banks"], "years": [{"year": "Dec 2025", "sales": 9017.0, "profit": 2522.0}]}
    assert SP.financial_mismatch(old) and not SP.financial_mismatch(new)
    assert not SP.financial_mismatch({**old, "bank": False, "industry": ["Services-Prepackaged Software"]})      # (guard) not a financial
    put = {}
    monkeypatch.setattr(T.computed, "get", lambda kind, key: {"value": old, "at": 1.0})
    monkeypatch.setattr(T.computed, "put", lambda kind, key, value, **k: put.update(v=value) or {"at": 2.0})
    monkeypatch.setattr(RR, "public_facts", lambda r, s: new)
    got, at = T.facts_piece("US", "FITB")
    assert got is new and put["v"] is new and at == 2.0
    monkeypatch.setattr(RR, "public_facts", lambda r, s: old)          # its page not rebuilt yet: the piece kept, the dive withholds
    assert T.facts_piece("US", "FITB")[0] is old


def test_deck_check_fails_a_bank_net_margin_above_100_percent():
    import deck_check as K
    cover = "     StratLab\n\nUS · THEME DEEP DIVE\nRegional banks\nBanks take deposits."
    page = ("Company                       Revenue        Net margin        ROE    Year\n"
            " Fifth Third Bancorp             $80 m          3152.5%†        11.6%     Dec 2025\n"
            " Truist Financial Corp        $59.9 bn $30.4 bn     +125.5%          16.3%       7.6%\n")
    got = K.check_text(cover + "\f" + page)
    assert got["counts"]["financial margin"] == 1 and "3152.5%" in got["findings"][[f["kind"] for f in got["findings"]].index("financial margin")]["text"]
    # (guards) a non-financial theme's 132% return on capital, and a share "228% of the net profit", are no bank margin
    it = "     StratLab\n\nINDIA · THEME DEEP DIVE\nIT services\nFirms serve global banks."
    assert K.check_text(it + "\f" + " Ksolves India Ltd ₹505 cr ₹163 cr +19.0% 30.1% 20.9% 132.0% 14.1x\n")["counts"]["financial margin"] == 0
    assert K.check_text(cover + "\f" + " Its other income of ₹1,200 crore is 228% of the net profit\n")["counts"]["financial margin"] == 0


def test_release_gate_fails_a_bank_net_margin_above_100_percent():
    d = {"theme": "Regional banks", "facts": {"FITB": {"industry": "National Commercial Banks"}, "SAFE": {"industry": "National Commercial Banks"}},
         "figures": {"FITB": {"revenue": 80.0, "net": 3152.5}, "SAFE": {"revenue": 9017.0, "net": 28.0}}, "evidence": {}}
    vc = [{"layer": "Deposit-funded retail and commercial banks", "companies": [
        {"ticker": "FITB", "name": "Fifth Third Bancorp", "industry": "National Commercial Banks"},
        {"ticker": "SAFE", "name": "Safe Bank", "industry": "National Commercial Banks"}]}]
    got = [x for x in G.checks(d, vc, {}) if x["fail"] == "financial margin"]
    assert [x["subject"] for x in got] == ["Fifth Third Bancorp (FITB)"]


def test_a_company_kept_in_the_theme_on_its_words_carries_the_placement_s_reason():
    from app.intel import theme_data as D
    c = {"ticker": "CMA", "name": "Comerica Inc", "verified": False, "base": True, "basis": "words", "industry": "", "placed": "words",
         "kept_member": True, "theme": {"why": "the map's check said no for “Commercial lenders” only, one layer's answer; its own words say the "
                                               "theme's work"}}
    got = D.theme_record(c, "core", "")
    assert got["by"] == "words" and got["why"].startswith("the map's check said no for “Commercial lenders”")       # R58: "filed under an official industry"
