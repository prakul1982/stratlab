"""R59 (lane r59): the six flags left on the live R58.2 decks. Each test fails on 52e6f86 (R58.2) and passes after, unless marked a guard.
Fixtures: tests/fixtures/themes_live/r59, the placement inputs of six themes as production served them on 16 Nov 2026 (R58.2, rules 61)."""
import os
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))

from app.intel import theme_base as B  # noqa: E402
import release_gate as G  # noqa: E402

LIVE = pathlib.Path(__file__).parent / "fixtures" / "themes_live" / "r59"
_ENGINE: dict = {}


def _engine(key):
    if key not in _ENGINE:
        d = G.load(LIVE / f"{key}.json")
        with G.offline():
            _ENGINE[key] = (d, G.engine(d)[0])
    return _ENGINE[key]


def _layer(out, start):
    return next(v for v in out["value_chain"] if v["layer"].startswith(start))


def _where(out, sym):
    return next(((v, c) for v in out["value_chain"] for c in v["companies"] if c["ticker"] == sym), (None, None))


def _outside(d, v):
    """The companies of a layer outside its figures: left out, or with no stored revenue (what deck_check's "left out>50%" counts)."""
    figs = d.get("figures") or {}
    return [c["ticker"] for c in v["companies"] if c.get("model_out") or isinstance(c.get("unfit"), dict)
            or not (figs.get(c["ticker"]) or {}).get("revenue")]


def _never_mostly_out(key):
    d, out = _engine(key)
    for v in out["value_chain"]:
        if v.get("official") or v["layer"].startswith("Other ") or len(v["companies"]) < B.LISTED_MIN:
            continue
        assert len(_outside(d, v)) * 2 <= len(v["companies"]), (v["layer"], _outside(d, v))


# ---------- 1-3. a layer never mostly listed and left out of its figures ----------
def test_1_retail_resale_layer_lists_no_one_whose_words_say_none_of_it():
    # live R58.2 p.24: "Resale, rental and small digital commerce", 2 of 5 in its calculations; NaaS (EV charging) and RedCloud left out
    # as insufficient evidence, their words saying no word of the layer's name
    d, out = _engine("retail")
    _never_mostly_out("retail")
    for sym in ("NAAS", "RCT"):
        v, c = _where(out, sym)
        assert v["layer"].startswith("Other ") and "not listed in it" in c["refit"]["why"], (sym, v["layer"])
        assert "Resale, rental and small digital commerce" in c["refit"]["why"]
    v, c = _where(out, "RENT")              # its words say rental: it stays (a guard on the rule's reach)
    assert v["layer"] == "Resale, rental and small digital commerce"


def test_2_media_cable_layer_counts_the_operator_whose_words_say_cable():
    # live R58.2 p.17: "Cable and satellite distribution", 3 of 7; Hathway Bhawani ("Cable Television services") left out as "different
    # revenue model", Dish TV (direct-to-home words, no cable or satellite) as insufficient evidence
    d, out = _engine("media")
    _never_mostly_out("media")
    v = _layer(out, "Cable and satellite distribution")
    hb = next(c for c in v["companies"] if c["ticker"] == "HATHWAYB")
    # (updated on purpose, r60: Dish TV now stays in the layer on its direct-to-home words, so the layer is no longer mostly left out and
    # r59's rule, which counts a left-out member on its words only in such a layer, need not act; Hathway Bhawani stays listed in it)
    assert (not hb.get("model_out") and hb.get("by_words") and hb.get("words_over") == "other") or hb.get("model_out") == "other"
    # (updated on purpose, r60: the owner's R59 review P0, Dish TV's "Direct to Home television and Teleport services" say the layer's
    # concept, satellite distribution: it stays in the layer, counted on its words, never sent to "Other")
    w, c = _where(out, "DISHTV")
    assert w["layer"] == "Cable and satellite distribution" and not c.get("model_out")
    calc = [c["ticker"] for c in v["companies"] if c["ticker"] not in _outside(d, v)]
    assert len(calc) * 2 > len(v["companies"]), calc


def test_3_oilgas_services_layer_lists_only_members_whose_words_say_it():
    # live R58.2 p.17: "Oilfield services and equipment makers", 4 of 9, 5 left out as insufficient evidence
    d, out = _engine("oilgas")
    _never_mostly_out("oilgas")
    v = _layer(out, "Oilfield services and equipment makers")
    assert all(not c.get("model_out") for c in v["companies"]), [c["ticker"] for c in v["companies"] if c.get("model_out")]
    aak = next(c for c in v["companies"] if c["ticker"] == "AAKASH")          # "provides oilfield services": counted on its words
    assert aak.get("by_words")
    # (updated on purpose, r60: the owner's R59 review, offshore drilling and seismic services say the concept of oilfield services: Aban
    # Offshore and Alphageo are no longer sent to "Other" for lacking a literal word of the name; Vectras (EPC) and Duke Offshore still are)
    for sym in ("VECTRAS", "DUKEOFS"):
        w, c = _where(out, sym)
        assert w["layer"].startswith("Other ") and "Oilfield services and equipment makers" in c["refit"]["why"], sym
    for sym in ("ABAN", "ALPHAGEO"):
        assert not _where(out, sym)[0]["layer"].startswith("Other "), sym


def test_1_3_a_layer_keeps_two_companies():
    # the rule never leaves a layer with one company: nothing moves when it would
    words = {"A": "A sells second-hand phones.", "B": "B operates charging stations.", "C": "C is a holding company.", "D": "D builds roads."}
    vc = [{"layer": "Resale and rental", "companies": [{"ticker": "A", "name": "A"}] +
           [{"ticker": t, "name": t, "model_out": "unknown"} for t in "BCD"]},
          {"layer": "Other retail companies", "official": True, "basis": "rest", "companies": []}]
    got, rows = B.listed_out(vc, lambda s: words.get(s, ""), "Consumer retail")
    assert not rows and len(got[0]["companies"]) == 4


# ---------- 4. a groups layer of two or fewer is not made, after every rule ----------
def test_4_two_groups_layer_not_made_after_the_last_rule():
    # live R58.2 Medical devices p.9: "Diversified groups" added with 2 companies (OSR Health, Yubo), moved there after the rule that undoes
    # such a layer had run
    words = {"O": "As a global healthcare holding company, we operate in Korea.", "Y": "We are a U.S. holding company operating through subsidiaries."}
    vc = [{"layer": "Diversified groups", "by_model": True, "companies": [{"ticker": "O", "name": "O Inc"}, {"ticker": "Y", "name": "Y Ltd"}]},
          {"layer": "Other medical device companies", "official": True, "basis": "rest", "companies": []}]
    got, rows = B.listed_out(vc, lambda s: words.get(s, ""), "Medical devices")
    assert [v["layer"] for v in got] == ["Other medical device companies"]
    assert {r["ticker"] for r in rows} == {"O", "Y"} and all("not made" in r["why"] for r in rows)


def test_4_guard_meddev_groups_layer_gains_the_member_whose_words_say_diversified():
    # guard (passes before and after): on the live R58.2 input PAVmed ("a diversified commercial-stage life sciences company") joins the two,
    # so the layer has 3 and stands
    d, out = _engine("meddev")
    v = _layer(out, "Diversified groups")
    assert {c["ticker"] for c in v["companies"]} >= {"PAVM", "OSRH", "YBGJ"}


# ---------- 5-6. the printed line is the sentence that places a company, or it is not moved there ----------
def test_5_payments_jpmorgan_not_listed_in_card_issuers_on_no_line_of_its_words():
    # live R58.2: JPMorgan Chase moved from "Other" into "Card issuers and consumer lenders", listed there as another business, its line
    # ("It is the largest bank in the United States...") saying no word of the layer's name
    # e79 (LIVE15A-005, updated on purpose): an encyclopedia's ranking ("It is the largest bank in the United States", "the largest of the Big
    # Four banks") is no line of its own words now, so its line is its own sentence, "The Firm is a leader in investment banking, financial
    # services for consumers and small businesses ...", which says the layer's word: the map's placement stands on it, said so
    d, out = _engine("payments")
    v, c = _where(out, "JPM")
    assert v["layer"] == "Card issuers and consumer lenders", v["layer"]
    line = B.own_line(d["evidence"]["JPM"], "JPMorgan Chase & Co")
    assert "largest" not in line and "Big Four" not in line and "consumers" in line, line
    assert not c.get("unfit")


def test_6_pharma_window_adds_members_whose_line_says_the_layer():
    # live R58.2: CCME Global ("formerly Genesis IBRC India Ltd and SSK Lifestyles Ltd") added to "Distribution and trading" by the window,
    # its line saying no word of the layer's name, while members whose words say trading were left out of the window
    d, out = _engine("pharma")
    win = B.for_figures({**out, "sub_themes": out.get("sub_themes") or []})[0]
    v = _layer(win, "Distribution and trading")
    syms = [c["ticker"] for c in v["companies"]]
    assert "CCME" not in syms and len(syms) >= 2, syms
    full = _layer(out, "Distribution and trading")
    assert next(c for c in full["companies"] if c["ticker"] == "CCME").get("line_says") is False
    # every company the window adds has a line of the layer; Evonile (its stored words Novartis India's, merged into it by the deck) is in
    # the window by size, not added
    assert [c["ticker"] for c in v["companies"] if c.get("line_says") is False] == ["EVONILE"]
    for c in v["companies"]:
        text = B.own_text(d["evidence"].get(c["ticker"]) or "")
        if c["ticker"] != "EVONILE" and text.strip() and not B.no_words(text):
            assert B.layer_line("", text, c.get("name") or "", v["layer"]), c["ticker"]


def test_6_layer_line_is_the_same_on_every_run():
    # the line layer_line picked depended on the order of a set of the name's words: with "commerce" read first a sentence's clause that
    # says "commercial" early was printed, with "rental" read first the same clause was refused for the word's place past a table's width
    code = ("from app.intel import theme_base as B; print(repr(B.layer_line('', 'Over time, our commercial relationships with our brand "
            "partners have evolved towards more capital efficient forms of rental product acquisition.', 'Rent the Runway, Inc.', "
            "'Resale, rental and small digital commerce')))")
    root = pathlib.Path(__file__).resolve().parents[1]
    got = {subprocess.run([sys.executable, "-c", code], cwd=root, capture_output=True, text=True,
                          env={**os.environ, "PYTHONHASHSEED": str(seed)}).stdout.strip() for seed in range(12)}
    assert len(got) == 1 and got != {"''"}, got
