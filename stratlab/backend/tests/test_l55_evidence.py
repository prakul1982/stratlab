"""l55 (Release 55, the owner's review of the live R54 decks): every displayed count of the theme's members says its evidence states by name
(description-verified, industry-supported, not checked; own words describe other work where there are any), never one undifferentiated
"confirmed" total (FMCG "160 checked" was 97 confirmed by their own description + 63 kept on their official industry, MedDev 110 + 50); a
layer's companies and the informative layers' count say their evidence mix (Biotech: 242 in informative layers while 160 had the membership
check); the membership check's count is said apart from the count with figures; deck_check fails a "confirmed" count without its split and
evidence counts that differ between pages. Synthetic themes only; no company or theme name in app code."""
import copy
import importlib.util
import os
import re
from datetime import date

from app import deck, public_themes
from app.intel import theme_workbook as W
from tests.test_export import texts
from tests.test_r17_fixes import deck_of, theme_a

PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts", "deck_check.py")
spec = importlib.util.spec_from_file_location("deck_check_l55", PATH)
DC = importlib.util.module_from_spec(spec)
spec.loader.exec_module(DC)

CONFIRMED_COUNT = re.compile(r"(?<![Nn]ot )\bconfirmed \(?(?:of )?\d|(?<![\d,.])\d[\d,]* confirmed\b|\bconfirmed,? with (?:figures|the figure)", re.I)


def partial_view():
    """theme_a's 20 companies (3 description-verified, 15 industry-supported, 2 describe other work) with 10 more companies
    of its first layer that the figures' window never reached: 2 of them reached by the membership check (one by its own description, one
    on its industry), 8 not checked. 30 companies, 22 checked."""
    region, m, f = theme_a()
    v, _ = deck_of(region, m, f)
    v = copy.deepcopy(v)
    first = max(v["layers"], key=lambda b: len(b["companies"]))["layer"]          # (the layer with a page of its own)
    v["members"] = list(v["members"]) + [{"symbol": f"XTRA{i}", "name": f"Extra {i} Ltd", "layer": first, "official": False, "industry": None,
                                          "what": None, "cap": 10.0 - i, "revenue": None} for i in range(10)]
    v["placements"] = {**(v.get("placements") or {}), "total": 30}
    v["coverage"] = {"informative": 30, "placed": 30, "share": 100, "other": 0, "unread": 0, "other_name": ""}
    v["membership_check"] = {"outside": {"XTRA0": "description_verified", "XTRA1": "industry_code_supported"}, "checked": 22, "total": 30,
                             "history": [["2026-11-07", 20, 30, 3], ["2026-11-14", 22, 30, 4]]}          # h56: the tally's points (updated on purpose)
    return v, first


def test_every_count_of_the_members_says_its_evidence_states_and_none_says_confirmed():
    """Fails before: "Considered 30 · confirmed 20 (of 22 checked)", "confirmed, with figures", "18 confirmed companies with figures"."""
    v, _ = partial_view()
    slides = deck.theme_plan(v)[0]
    t = texts(slides)
    assert not CONFIRMED_COUNT.search(t), CONFIRMED_COUNT.findall(t)[:5]
    split = "membership checked 22 of 30: 4 description-verified, 16 industry-supported, 2 own words describe other work, 8 not checked"
    c = deck.reconciled_counts(v, deck.coverage(v))
    assert deck.counts_words(c) == (f"Considered 30 · {split} · with figures {c['with_figures']}"
                                    + (" · in each calculation: " + ", ".join(f"{a} {b}" for a, b in c["each"]) if c["each"] else ""))
    find = next(ln for s in slides if s.title == "Key findings" for b in s.blocks if b["kind"] == "cards" for it in b["items"]
                for ln in it["lines"] if ln.startswith("Considered"))
    conf = next(p for s in slides if s.title == "Data confidence" for b in s.blocks for p in b.get("paras") or [] if p.startswith("Counts:"))
    assert split in find and split in conf
    rows = {r[0]: r for s in slides for b in s.blocks if b["kind"] == "table" for r in b.get("rows") or [] if not isinstance(r, dict)}
    # h56 (R56, updated on purpose): the description-verified share first, then the membership check's count
    # r62 (updated on purpose: the owner's review of the live R60 decks, P1, the sources of the companies add up to them; the fixture's 10
    # members beyond its view carry no source)
    assert rows["Universe"][1].startswith("30 companies (20 in the exchange's industry list, 10 more, their source not kept with this read); "
                                          "description-verified 4 of 30 (13%); "
                                          "membership checked 22 of 30 (the map's own picks")
    assert rows["Universe"][1].endswith(": " + split.split(": ", 1)[1] + ".") and split in rows["Screening"][2]
    assert rows["Membership checked"][1] == "22 of 30 (73%)" and (      # h56 (R56): led by the description-verified share (updated on purpose)
        ". By state: 4 description-verified, 16 industry-supported, 2 own words describe other work, 8 not checked; ") in rows["Membership checked"][2]
    # the companies with figures by state, adding up to the deck's count (every median and total is of these)
    n = v["members_with_figures"]
    by = re.search(r"companies with figures, of every company the deck lists: (\d+) description-verified, (\d+) industry-supported", rows["Companies, by count"][2])
    assert by and int(by.group(1)) + int(by.group(2)) == n
    apx = next(s for s in slides if s.title.startswith("Every company's figures"))
    a = re.match(r"(\d+) companies with figures \((\d+) description-verified, (\d+) industry-supported\), one row each", apx.subtitle)
    assert a and int(a.group(2)) + int(a.group(3)) == int(a.group(1))
    # the cover: what isn't in the theme by its state's name
    cover = {it[0]: it[2] for b in slides[0].blocks if b["kind"] == "stats" for it in b["items"] if len(it) > 2}
    assert cover["Companies"].endswith("; 2 describe other work")          # fix20 (LIVE14B-005): a plain phrase (updated on purpose)
    # what each state means, once, on the notes page
    assert deck.EVIDENCE_KEY in t
    # and the gate finds nothing to fail
    assert not [d for d in slides[0].gate["dropped"] if "evidence" in d["why"] or "confirmed" in d["why"]], slides[0].gate["dropped"]


def test_the_informative_layers_and_each_layer_say_their_evidence_mix():
    """Fails before: "In informative layers 26 of 30" beside 22 checked, every layer's list reading as equally verified."""
    v, first = partial_view()
    slides = deck.theme_plan(v)[0]
    rows = {r[0]: r for s in slides for b in s.blocks if b["kind"] == "table" for r in b.get("rows") or [] if not isinstance(r, dict)}
    inf = rows["In informative layers"]
    k = int(re.match(r"(\d+) of 30", inf[1]).group(1))
    m = re.search(r"by membership evidence: (\d+) description-verified, (\d+) industry-supported, (?:(\d+) own words describe other work, )?(\d+) not checked", inf[2])
    assert m and sum(int(x) for x in m.groups() if x) == k and int(m.group(4)) == 8          # the 8 not checked are in a named layer
    page = next(s for s in slides if s.title.endswith(f"· {first}"))
    # (in the headline where its two lines hold it, else the page's first note)
    said = [page.subtitle] + [p for b in page.blocks if b["kind"] == "text" for p in b.get("paras") or []]
    line = next(re.search(r"[Mm]embership of its .*", p).group(0) for p in said if re.search(r"[Mm]embership of its ", p))
    # y57 (R57, BIO-12): a count other than the header's says it is of the layer's companies stored in all (updated on purpose)
    lm = re.match(r"[Mm]embership of its (\d+) companies stored in all \(figures read for the header's (?:\d+)\): (\d+) description-verified, "
                  r"(\d+) industry-supported, (?:(\d+) own words describe other work, )?(\d+) not checked", line)
    assert lm and int(lm.group(5)) == 8 and sum(int(x) for x in lm.groups()[1:5] if x) == int(lm.group(1))
    # a deck whose layers are all checked says so, and every layer page carries its line
    region, mm, f = theme_a()
    v2, s2 = deck_of(region, mm, f)
    pages = [s for s in s2 if s.title.startswith("Layer ")]
    assert pages and all(any(re.search(r"[Mm]embership of its \d+ compan(?:y|ies): \d+ description-verified, .*, 0 not checked", p)
                             for p in [s.subtitle] + [p for b in s.blocks if b["kind"] == "text" for p in b.get("paras") or []]) for s in pages)


def test_the_membership_check_is_said_apart_from_the_count_with_figures():
    """Fails before: "Membership checked 22 of 30" with nothing that says the check reads no figure, beside "with figures"."""
    v, _ = partial_view()
    row = deck.progress_row(v, deck.coverage(v))
    n = deck.coverage(v)["n"]
    assert row[2].endswith(f"The membership check reads no figures: companies with figures {n}, a separate count.")
    assert "Checked share after each stored version: 67% (07 Nov 2026) → 73% (14 Nov 2026)" in row[2]
    part = deck.partial_map({**v, "membership": {"placed": 5}, "membership_evidence": {"description_verified": 5}, "membership_check": {}}, {"total": 30})
    assert part.startswith("A partial map: membership checked for 5 of the theme's 30 companies (17%)")


def test_the_gate_fails_a_confirmed_count_and_evidence_counts_that_disagree():
    v, _ = partial_view()
    slides = deck.theme_plan(v)[0]
    counts = deck.reconciled_counts(v, deck.coverage(v))
    assert deck.evidence_gate_flags(slides, counts) == []
    bad = deck.Slide("Key findings", "Considered 30 · confirmed 20 (of 22 checked) · with figures 18")
    off = deck.Slide("Coverage", "membership checked 22 of 30: 5 description-verified, 15 industry-supported, 2 own words describe other work, 8 not checked")
    sums = deck.Slide("Notes", "membership checked 22 of 30: 4 description-verified, 16 industry-supported, 9 not checked")
    part = deck.Slide("Coverage", "in a layer the map names (by membership evidence: 9 description-verified, 1 industry-supported, 0 not checked)")
    got = deck.evidence_gate_flags([bad, off, sums, part], counts)
    assert [d["slide"] for d in got] == ["Key findings", "Coverage", "Notes", "Coverage"]
    assert "without its evidence states" in got[0]["why"] and all(d["rule"] == "reconcile" for d in got)
    assert all("evidence counts disagree" in d["why"] for d in got[1:])


# the live R54 FMCG deck's own words (pdftotext of scratchpad/lanes11/r54-decks/fmcg.pdf, pages 3-5), the two columns interleaved
FMCG_R54 = ("FMCG · FINDINGS\nKey findings\nHow far the figures go\n   Considered 211 · confirmed 160 (of 160     13 dated updates at 13 companies,\n"
            "   checked) · with figures 93 core members    picked by fixed rules\n"
            "StratLab · FMCG · Theme deep dive · 14 Nov 2026                Not investment advice · 3 / 50\n\f"
            "FMCG · FINDINGS\nData confidence\n"
            "                             211 in the exchange's industry list; 160 checked (the map's own picks, then the largest by\n"
            "                             market value, and 60 more reached by the membership check): 97 confirmed by their own            Only confirmed companies count in a median or\n"
            " Universe\n                             description, 63 kept on their official industry only, 0 whose own words describe other work;     total.\n"
            "                             51 not checked yet.\n"
            "Counts: Considered 211 · confirmed 160 (of 160 checked) · with figures 93 core members; confirmed, with figures (every median and total is of these) 93.\n"
            "StratLab · FMCG · Theme deep dive · 14 Nov 2026                Not investment advice · 4 / 50\n\f"
            "FMCG · APPENDIX\nEvery company's figures (1 of 8)\n95 confirmed companies with figures, one row each; Hindustan Unilever Limited is the largest\n"
            "StratLab · FMCG · Theme deep dive · 14 Nov 2026                Not investment advice · 32 / 50\n\f")


def test_deck_check_fails_every_confirmed_count_without_its_split_on_the_live_r54_words():
    r = DC.check_text(FMCG_R54)
    assert DC.failed(r) and r["counts"]["evidence unsplit"] >= 4
    assert {f["page"] for f in r["findings"] if f["kind"] == "evidence unsplit"} == {1, 2, 3}


def test_deck_check_passes_the_states_by_name_and_fails_counts_that_differ_between_pages():
    foot = "StratLab · X · Theme deep dive · 14 Nov 2026                Not investment advice · {} / 9\n"
    good = ("X · FINDINGS\nKey findings\nWhat the figures show\nConsidered 211 · membership checked 160 of 211: 97 description-verified, 63 industry-supported, 51 not checked · "
            "with figures 93\n" + foot.format(1) + "\f"
            "X · FINDINGS\nData confidence\n Universe     211 in the exchange's industry list; membership checked 160 of 211 (the map's own picks, then the largest by market\n"
            "              value, and 60 more reached by the membership check): 97 description-verified, 63 industry-supported, 51 not checked.\n"
            " In informative layers   176 of 211   in a layer the map names (by membership evidence: 90 description-verified, 60 industry-supported, 26 not checked)\n"
            + foot.format(2) + "\f"
            "X · THE VALUE CHAIN\nLayer 1 · Packaged foods\n44 companies, revenue ₹1 lakh cr\nMembership of its 44 companies: 40 description-verified, "
            "4 industry-supported, 0 not checked.\n" + foot.format(3) + "\f")
    r = DC.check_text(good)
    assert r["counts"]["evidence unsplit"] == 0 and r["counts"]["evidence counts"] == 0 and r["counts"]["empty page"] == 0, r["findings"]
    differ = good.replace("market\n              value, and 60 more reached by the membership check): 97 description-verified, 63",
                          "market\n              value, and 60 more reached by the membership check): 100 description-verified, 60")
    assert DC.check_text(differ)["counts"]["evidence counts"] == 1
    unsummed = good.replace("97 description-verified, 63 industry-supported, 51 not checked · ", "97 description-verified, 60 industry-supported, 51 not checked · ")
    assert DC.check_text(unsummed)["counts"]["evidence counts"] == 2          # 157 of 160 checked, and not the deck's other statement
    part = good.replace("90 description-verified, 60 industry-supported, 26 not checked", "99 description-verified, 51 industry-supported, 26 not checked")
    assert DC.check_text(part)["counts"]["evidence counts"] == 1
    # a "confirmed" count beside its states by name is no undifferentiated total
    assert DC.check_text("A\nB\nC\n confirmed 160 (97 description-verified, 63 industry-supported)\n")["counts"]["evidence unsplit"] == 0
    assert DC.check_text("A\nB\nC\n 110 confirmed by their own description and 50 kept on their official industry\n")["counts"]["evidence unsplit"] == 1


def test_deck_check_keeps_the_publication_preflight_and_finds_an_empty_page():
    foot = "StratLab · X · Theme deep dive · 14 Nov 2026                Not investment advice · {} / 3\n"
    deck_text = ("X · FINDINGS\nData confidence\nThe checks every figure went through\n Universe   12 in the exchange's industry list\n" + foot.format(1) + "\f"
                 "X · THE VALUE CHAIN\nLayer 2 · Tools\n" + foot.format(2) + "\f"
                 "X · APPENDIX\nEvery company's figures\n2 companies with figures (2 description-verified, 0 industry-supported), one row each\n"
                 " Company        Layer          Market value    Revenue\n"
                 " Alpha Ltd      –              ₹10 cr          ₹5 cr\n"
                 " Semiconductor equipm…  Tools  ₹9 cr  ₹4 cr\n" + foot.format(3) + "\f")
    r = DC.check_text(deck_text)
    assert r["counts"]["empty page"] == 1 and [f["page"] for f in r["findings"] if f["kind"] == "empty page"] == [2]
    assert r["counts"]["no layer"] == 1 and r["counts"]["cut text"] >= 1 and DC.failed(r)          # the earlier checks still run


def test_the_public_page_and_the_workbook_say_each_state_by_name_and_each_layer_its_mix(monkeypatch):
    dive = {"evidence": {"A": "description_verified", "B": "industry_code_supported"}, "membership_check": {"outside": {"C": "industry_code_supported"}},
            "membership_evidence": {"description_verified": 1, "industry_code_supported": 1}}
    payload = {"value_chain": [{"layer": "Ships", "companies": [{"ticker": "A", "name": "A Ltd", "verified": True, "what": "builds ships"},
                                                                {"ticker": "B", "name": "B Ltd", "base": True, "basis": "industry", "verified": False}]},
                               {"layer": "Ports", "companies": [{"ticker": "C", "name": "C Ltd", "base": True, "basis": "industry", "verified": False},
                                                                {"ticker": "D", "name": "D Ltd", "base": True, "basis": "industry", "verified": False}]}]}
    monkeypatch.setattr(public_themes, "_dive", lambda r, n, p: dive)
    monkeypatch.setattr(public_themes, "_index_caps", lambda r: {})
    monkeypatch.setattr(public_themes.stock_pages, "companies", lambda r: set())
    v = public_themes.view({"region": "IN", "name": "Ships", "label": "Ships", "slug": "ships", "at": None}, payload)
    page = public_themes.render(v)
    assert "Membership: 1 description-verified, 2 industry-supported, 1 not checked." in page
    assert page.count("data-layer-evidence") == 2 and "1 description-verified, 1 industry-supported, 0 not checked</p>" in page \
        and "0 description-verified, 1 industry-supported, 1 not checked</p>" in page
    assert "confirmed by its own description" not in page and "description-verified (its own description was checked" in public_themes.METHOD
    # the workbook: each company's state, and each layer's companies by state
    wdive = {"evidence": {"A": "description_verified", "B": "industry_code_supported"}, "unit": "₹ crore", "sections": {},
             "layers": [{"layer": "Ships", "companies": [{"symbol": "A", "name": "A Ltd"}, {"symbol": "B", "name": "B Ltd"}]}]}
    name, rows, _, _ = W.companies(wdive, "IN")
    assert rows[0][-1] == "Membership evidence" and [r[-1] for r in rows[1:]] == ["Description-verified", "Industry-supported (official industry only)"]
    name, rows, _, _ = W.layer_medians(wdive, "IN")
    head = rows[0]
    at = head.index("Companies listed: Description-verified")
    assert head[at:at + 5] == ["Companies listed: Description-verified", "Companies listed: Industry-supported", "Companies listed: List-supported",
                               "Companies listed: Own words describe other work", "Companies listed: Not checked"]
    assert rows[1][at:at + 5] == [1, 1, 0, 0, 0] and rows[-1][at:at + 5] == [1, 1, 0, 0, 0]
    method = dict(W.method(wdive, "IN", "Ships", date(2026, 11, 14), {})[1][1:])
    assert "confirmed" not in method["How a layer's median is built"] and "description-verified" in method["Membership evidence"]


def test_a_pick_whose_check_gave_no_answer_is_not_checked_on_every_page_from_one_tally():
    """l55b (R55, with v55: a map pick whose check gave no answer is "not checked yet", never "own words describe other work"): fails
    before: the membership's "placed" (every company, the unanswered ones too) was said as the companies checked beside the tally's states,
    "membership checked 20 of 20: 3 description-verified, 15 industry-supported, 2 not checked", and the gate failed the deck; the cover
    said the 2 were "own words: other work"."""
    region, m, f = theme_a()
    v, _ = deck_of(region, m, f)
    v = copy.deepcopy(v)
    two = [s_ for s_, x in v["evidence"].items() if x == "not_confirmed"]
    assert len(two) == 2 and v["membership"]["placed"] == 20          # status "unverified" for both: listed, in no figure
    v["evidence"] = {**v["evidence"], **{s_: "membership_unverified" for s_ in two}}
    v["membership_evidence"] = {**v["membership_evidence"], "not_confirmed": 0, "membership_unverified": 2}
    c = deck.reconciled_counts(v, deck.coverage(v))
    assert c["checked"] == 18 and deck.confirmed_words(c, 20) == "membership checked 18 of 20: 3 description-verified, 15 industry-supported, 2 not checked"
    slides = deck.theme_plan(v)[0]
    assert not [d for d in slides[0].gate["dropped"] if "evidence" in d["why"]], slides[0].gate["dropped"]
    cover = {it[0]: it[2] for b in slides[0].blocks if b["kind"] == "stats" for it in b["items"] if len(it) > 2}
    assert "other work" not in cover["Companies"] and deck.other_work(v, 20) == 0
    assert DC.check_text("\f".join(texts([s]) for s in slides))["counts"]["evidence counts"] == 0
