"""Lane n2-evidence (11 Nov): the outside review of the live R33 decks.
1. A 20-F filer's business is read from its Item 4 (TSMC, UMC): the letter of "Business overview" is not always there, a paragraph set one
   printed line a line is one paragraph, and a part with no sentence of what the company does gives way to the next. A US description
   that doesn't say what the company does gets its annual report read; a kept model of low confidence is read again from the evidence.
2. A services company whose words show its family's way of earning (Wipro: consulting) is in its layer's figures at "medium".
3. A retailer whose words say only that it runs a marketplace on commission is a platform; one with stores and a marketplace stays a retailer.
4. A top-line figure filed a thousand times too large (Tigo Energy) is never the revenue, and a theme row whose revenue is out of scale with
   its market value and its own profit is held out of every sum.
5. The encyclopedia reader returns no article about another company or about no company, for every caller (Ichor, TOYO)."""
import json
import types

import httpx
import pytest

from app.intel import news, sec
from app.intel import theme_base as B
from app.intel import theme_check as C
from app.intel import theme_data as D
from app.intel import theme_routes as TR

SEMI = "Industry: Manufacturing > Semiconductors & Related Devices. "


# ---------- 1. the 20-F's Item 4 ----------
def _twenty_f(history: str, overview_head: str, overview: str) -> str:
    """A 20-F as report_lines gives it: a contents page, then Item 4 with its history part and its business overview, each paragraph set
    one printed line a line."""
    pad = "<p>Our fabs operate around the clock and our yields have stayed among the highest in the industry over the year.</p>" * 30
    return ("<p>ITEM 4.</p><p>INFORMATION ON THE COMPANY</p><p>14</p><p>ITEM 5.</p><p>OPERATING AND FINANCIAL REVIEW</p><p>40</p>"
            + "<p>ITEM 3. KEY INFORMATION</p>" + "<p>Risks relating to our business may affect the price of our shares a great deal.</p>" * 20
            + "<p>ITEM 4. INFORMATION ON THE COMPANY</p><p>A. History and Development of the Company</p>" + history
            + f"<p>{overview_head}</p>" + overview + pad + "<p>ITEM 4A. UNRESOLVED STAFF COMMENTS</p><p>None.</p>")


def test_a_20f_without_the_letter_and_with_broken_lines_gives_its_business():
    tsmc = _twenty_f(
        "<p>Our legal and commercial name is Taiwan Semiconductor Manufacturing Company Limited. We were founded in 1987 as a joint venture.</p>",
        "Business Overview of the Company",
        "<div>As a foundry, we manufacture semiconductors using our manufacturing processes for our customers based on</div>"
        "<div>proprietary integrated circuit designs provided by them. We offer a comprehensive range of wafer fabrication</div>"
        "<div>processes, including processes to manufacture CMOS logic and mixed-signal chips.</div>")
    got = sec.business_opening(sec.report_lines(tsmc))
    assert got.startswith("As a foundry, we manufacture semiconductors using our manufacturing processes for our customers based on proprietary")
    assert C.model_confidence("manufacturing", SEMI + got) == "high" and C.model_supported("contract_manufacturing", SEMI + got)


def test_a_business_overview_that_never_says_what_the_company_does_gives_way_to_item_4s_history():
    umc = _twenty_f(
        "<p>Our legal and commercial name is United Microelectronics Corporation. We were incorporated under the Company Law in May 1980. "
        "We are one of the world’s largest independent semiconductor foundries and a leader in semiconductor manufacturing process "
        "technologies. Our primary business is the manufacture of semiconductors for others.</p>",
        "B. Business Overview",
        "<p>To maintain a leading position in the foundry business, we have placed great emphasis on achieving a high standard of quality.</p>"
        "<p>Process technology is a set of specifications and parameters that we implement for manufacturing the circuitry of chips.</p>")
    got = sec.business_opening(sec.report_lines(umc))
    assert got.startswith("We are one of the world’s largest independent semiconductor foundries")
    assert C.model_from_words(SEMI + got) == "contract_manufacturing"


def test_a_10k_is_read_as_before_and_a_part_with_no_work_sentence_still_stands_alone():
    ten_k = ("<p>Item 1. Business</p>" + "<p>Acme Corp is a maker of power chips for cars and factories, sold to makers of vehicles worldwide.</p>"
             + "<p>Our plants ran at full capacity during the year and we added a second line for chips in the fourth quarter.</p>" * 20
             + "<p>Item 1A. Risk Factors</p>")
    assert sec.business_opening(sec.report_lines(ten_k)).startswith("Acme Corp is a maker of power chips")
    plain = ("<p>B. Business Overview</p>" + "<p>Our plants ran at full capacity during the year and we added a second line for chips in the quarter.</p>" * 20
             + "<p>C. Organizational Structure</p>")
    assert sec.business_opening(sec.report_lines(plain)).startswith("Our plants ran at full capacity")


@pytest.fixture
def store(monkeypatch):
    kept: dict = {}
    monkeypatch.setattr(TR.db, "get_setting", lambda k: kept.get(k))
    monkeypatch.setattr(TR.db, "set_setting", lambda k, v: kept.__setitem__(k, v))
    monkeypatch.setattr(TR, "own_filings", lambda region, sym: "")
    monkeypatch.setattr(TR, "filing_reads", TR.Window())
    TR.EVIDENCE_CACHE.clear()
    yield kept
    TR.EVIDENCE_CACHE.clear()


UMC_WIKI = ("United Microelectronics Corporation is a Taiwanese company based in Hsinchu, Taiwan. It was founded as Taiwan's first semiconductor "
            "company in 1980 as a spin-off of the government-sponsored Industrial Technology Research Institute (ITRI).")
UMC_20F = "We are one of the world’s largest independent semiconductor foundries and a leader in semiconductor manufacturing process technologies."


def test_a_full_article_that_says_nothing_of_the_business_gets_the_annual_report_too(store, monkeypatch):
    hub = types.SimpleNamespace(wiki=types.SimpleNamespace(company=lambda name: {"title": "United Microelectronics Corporation", "extract": UMC_WIKI}),
                                screener=None)
    monkeypatch.setattr(TR, "_routes", lambda: types.SimpleNamespace(hub=hub, public_facts=None))
    reads = []
    monkeypatch.setattr(TR, "_business_read", lambda sym: reads.append(sym) or UMC_20F)
    assert len(UMC_WIKI.split()) >= TR.ABOUT_WORDS and not TR.says_work(UMC_WIKI) and TR.says_work(UMC_20F)
    got, _ = TR.evidence_reader("US", {"UMC": "United Microelectronics Corp"})(["UMC"])
    assert reads == ["UMC"] and got["UMC"]["about"].endswith(UMC_20F) and got["UMC"]["about"].startswith("United Microelectronics")
    # stored in the old format, it is read once more; in this format it keeps its time
    assert TR.ABOUT_V == 4 and TR.thin_about({"at": "2026-11-01T00:00:00+00:00", "about": UMC_WIKI, "v": 3}, "US")
    assert not TR.thin_about({"at": "2026-11-01T00:00:00+00:00", "about": UMC_WIKI, "v": TR.ABOUT_V}, "US")
    assert not TR.thin_about({"at": "2026-11-01T00:00:00+00:00", "about": UMC_WIKI, "v": 3}, "IN")


def test_the_check_reads_again_the_weak_models_stored_descriptions_and_no_others(store, monkeypatch):
    old = {"at": "2026-11-01T00:00:00+00:00", "about": "", "v": 3}
    for s_ in ("TSM", "UMC", "INTC", "NEW"):
        store[f"theme:evidence:US:{s_}"] = json.dumps(old)
    out = {"value_chain": [{"layer": "Foundry", "companies": [{"ticker": t, "cap": c} for t, c in (("TSM", 9), ("UMC", 3), ("INTC", 5), ("NEW", 1))]}]}
    kept = {"models": {"TSM": "manufacturing", "UMC": "manufacturing", "INTC": "manufacturing"},
            "model_confidence": {"TSM": "low", "UMC": "low", "INTC": "high"}}
    asked = []
    monkeypatch.setattr(TR, "evidence_reader", lambda region, names: (lambda syms: asked.append(list(syms)) or ({}, [])))
    assert TR.reread_weak("US", out, {}, kept) == ["TSM", "UMC", "NEW"] and asked == [["TSM", "UMC", "NEW"]]
    store["theme:evidence:US:TSM"] = json.dumps({**old, "v": TR.ABOUT_V})            # read in this format already: not again
    assert TR.reread_weak("US", out, {}, kept) == ["UMC", "NEW"]


def test_a_kept_model_of_low_confidence_rises_with_the_evidence_read_since():
    ev = {"TSM": SEMI + "As a foundry, we manufacture semiconductors for our customers based on designs provided by them.", "X": SEMI}
    models, conf = B.refine_kept({"TSM": "manufacturing", "X": "manufacturing"}, {"TSM": "low", "X": "low"}, lambda s_: ev[s_], ["TSM", "X"])
    # q1 (changed on purpose): foundry words make TSMC a contract maker, its confidence read from its own words, never above "medium"
    assert models["TSM"] == "contract_manufacturing" and conf["TSM"] == "medium" and conf["X"] == "low"      # lifted, never above "medium"
    assert B.RULES == 38 and TR.PLACE_CARRY[35] == 34 and TR.PLACE_CARRY[36] == 35 and TR.PLACE_CARRY[38] == 37     # lane r2, lane r1 and q1 bumped RULES (updated on purpose)


# ---------- 2. a services company's family ----------
def test_a_services_companys_family_words_put_it_in_the_figures_at_medium():
    wipro = "Industry: Information Technology > IT - Software > Computers - Software & Consulting. Wipro Ltd is a global Information technology, consulting and business process services (BPS) company."
    assert C.model_confidence("managed_services", wipro) == "medium" and C.family_shown("managed_services", wipro)
    ltts = "Industry: Information Technology > IT - Services. An engineering and technology services company, providing design, development and testing services."
    assert C.model_confidence("project_services", ltts) == "high"
    # another family's words never lift it, and "low" stays low with no words of the family
    assert C.model_confidence("managed_services", "Industry: IT. It operates hotels and resorts across India.") == "low"
    assert not C.family_shown("software", "We make and sell pumps.") and not C.family_shown("unknown", "consulting")


# ---------- 3. retailers and marketplaces ----------
def test_a_marketplace_on_commission_is_a_platform_and_a_retailer_with_one_stays_a_retailer():
    market = "Industry: Retail. Acme runs an online marketplace that connects sellers and buyers and earns commission income on each order."
    shop = "Industry: Retail. We serve consumers through our online and physical stores. Third-party sellers use our online marketplace."
    assert C.refine_model("retail", market) == "platform" and C.refine_model("retail", shop) == "retail"
    assert C.model_supported("platform", "Industry: Retail. We believe we are one of the leading commerce platforms in Turkey.")
    assert "retail" in B.R31_REFINE
    models, conf = B.refine_kept({"M": "retail", "S": "retail"}, {"M": "medium", "S": "high"}, {"M": market, "S": shop}.get, ["M", "S"])
    assert models == {"M": "platform", "S": "retail"} and C.model_family(models["M"]) != C.model_family(models["S"])


# ---------- 4. a figure filed at the wrong scale ----------
def _facts(rows: dict) -> dict:
    return {"us-gaap": {c: {"units": {"USD": [{"start": f"{y}-01-01", "end": f"{y}-12-31", "val": v, "form": "10-K", "fp": "FY",
                                              "filed": f"{y + 1}-03-01", "accn": f"a{y}"} for y, v in vals.items()]}} for c, vals in rows.items()}}


def test_a_top_line_filed_a_thousand_times_too_large_is_not_the_revenue():
    tigo = _facts({"RevenueFromContractWithCustomerExcludingAssessedTax": {2024: 54014000000, 2025: 103536000000},
                   "Revenues": {2024: 54014000, 2025: 103536000}, "CostOfRevenue": {2024: 58170000, 2025: 59185000}})
    assert sec.revenue(tigo, "annual") == {"2024-12-31": 54014000.0, "2025-12-31": 103536000.0}
    alone = _facts({"RevenueFromContractWithCustomerExcludingAssessedTax": {2025: 103536000000}, "CostOfRevenue": {2025: 59185000}})
    assert sec.revenue(alone, "annual") == {"2025-12-31": 103536000.0}
    # a part beside the whole, and a real business with costs to match, stay as they were
    reit = _facts({"Revenues": {2025: 900000000}, "RevenueFromContractWithCustomerExcludingAssessedTax": {2025: 120000000}})
    assert sec.revenue(reit, "annual") == {"2025-12-31": 900000000.0}
    assert sec.top_line([5e9], 3e9) == 5e9 and sec.top_line([2e9, 2e6]) == 2e6 and sec.top_line([7e9, 6.9e3]) == 7e9 and sec.top_line([7e9, 7e3]) == 7e3


def test_a_theme_row_whose_revenue_is_out_of_scale_is_held_out_of_every_sum():
    def row(rev, cap, profits):
        return {"symbol": "T", "name": "Tigo Energy, Inc.", "revenue": rev, "cap": cap, "profit": profits[-1], "ebitda": -0.0, "net": -0.0,
                "capital_rev": 0.0, "years": [{"year": f"Dec {2022 + i}", "sales": rev, "profit": p} for i, p in enumerate(profits)]}
    r = D.validate_row(row(103536.0, 57.02, [-7.04, -0.98, -62.75, -1.88]), {}, None)
    assert r["revenue"] is None and r["capital_rev"] is None and r["held_revenue"]["value"] == 103536.0
    assert set(r["held"]) == {"ebitda", "net"} and D.CHECKS["revenue_scale"] in r["held"]["ebitda"]["checks"]
    blk = D.layer_block("Makers", [{**r, "status": "core"}], set())
    assert blk["revenue"] is None
    # a thin-margin trader with a small market value and losses to match its size is left as it is
    ok = D.validate_row(row(10000.0, 40.0, [-120.0, 15.0]), {}, None)
    assert ok["revenue"] == 10000.0 and "held_revenue" not in ok
    assert not D.revenue_out_of_scale(row(500.0, 57.0, [-1.0]))


# ---------- 5. the encyclopedia's article ----------
def _wiki(pages: dict, search: dict):
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/w/api.php":
            q = req.url.params.get("srsearch", "")
            hit = next((v for k, v in search.items() if q.startswith(k)), None)
            return httpx.Response(200, json={"query": {"search": [{"title": hit}] if hit else []}})
        title = req.url.path.rsplit("/", 1)[-1].replace("_", " ")
        p = pages.get(title)
        return httpx.Response(200, json={"title": title, **p}) if p else httpx.Response(404, json={})
    return news.Wikipedia(transport=httpx.MockTransport(handler))


def test_the_company_page_never_shows_an_article_about_another_company_or_about_no_company():
    w = _wiki({"Ichor": {"description": "Blood of gods in Greek mythology",
                         "extract": "In Greek mythology, ichor is the ethereal fluid making up the blood of the gods and/or immortals."},
               "Toyo Tires": {"description": "Japanese tire company",
                              "extract": "Toyo Tire Corporation, commonly known as Toyo Tires, is a multinational tire and rubber products company."},
               "Marvell Technology": {"description": "American semiconductor company",
                                      "extract": "Marvell Technology, Inc. is an American company which develops and produces semiconductors."}},
              {"Ichor": "Ichor", "TOYO": "Toyo Tires", "Marvell": "Marvell Technology"})
    assert w.company("Ichor Holdings, Ltd.") is None
    assert w.company("TOYO Co., Ltd") is None
    assert w.company("Marvell Technology, Inc.")["title"] == "Marvell Technology"
    # a wrong answer kept from before is checked again as it is read: the page's cached read (the deck's cover) never shows it either
    assert w.company("Ichor Holdings, Ltd.", cached=True) is None and w.company("Marvell Technology, Inc.", cached=True)["title"] == "Marvell Technology"
