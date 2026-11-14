"""Lane l3-class (11 Nov): a company's layer and sub-theme follow its primary business, from the words it has.
1. A company's one line is never cut at its legal form ("Qnity Electronics, Inc" for a full description).
2. A description the profile and the encyclopedia leave thin gets the opening of the company's latest annual report (US), read through the
   SEC feed a few a minute, stored, never a burst; an encyclopedia article about another company or about no company is not used.
3. A sub-theme's word counts when said another way in the layer the sub-theme mostly sits in (mobile: wireless, cellular, telecommunication
   services with no narrower business named); a broadband-only company stays out.
4. A supplier of materials for chips is an ingredient maker its evidence shows, so it leaves the equipment makers' layer."""
import json
import types
from datetime import datetime, timezone

import httpx
import pytest

from app.intel import news, sec
from app.intel import theme_base as B
from app.intel import theme_check as C
from app.intel import theme_routes as TR
from app.intel.net import SourceError
from app.intel.theme_data import sub_members

# the opening of Qnity's annual report for 2025 (Item 1. Business), as filed
QNITY_10K = ("Qnity is one of the largest global leaders in materials and solutions for the semiconductor and electronics industries. We empower "
             "our customers’ technology roadmaps to enable advancements in megatrends such as artificial intelligence, high-performance "
             "computing and advanced connectivity. We partner with leading semiconductor and advanced device manufacturers to address complex "
             "challenges and develop solutions that facilitate next-generation technological innovations.")
SEMI = "Manufacturing > Semiconductors & Related Devices"


# ---------- 1. the one line ----------
@pytest.mark.parametrize("about, line", [
    ("Qnity Electronics, Inc. is a major provider of materials for the semiconductor manufacturing and electronics industries headquartered in "
     "Wilmington, Delaware. The company's Semiconductor Technologies segment produces products for chemical-mechanical polishing.",
     "Qnity Electronics, Inc. is a major provider of materials for the semiconductor manufacturing and electronics industries headquartered in "
     "Wilmington, Delaware"),
    ("Daqo New Energy Corp. (NYSE: DQ) is a Chinese company engaged in the manufacture of polysilicon. It sells to makers of solar cells.",
     "Daqo New Energy Corp. (NYSE: DQ) is a Chinese company engaged in the manufacture of polysilicon"),
    ("Acme Networks Ltd. provides mobile services in the U.S. and in India. It has 4 million subscribers.",
     "Acme Networks Ltd. provides mobile services in the U.S. and in India"),
    ("It leases tower space mainly to wireless telecom operators on a shared basis. It has 2 lakh towers.",
     "It leases tower space mainly to wireless telecom operators on a shared basis"),
])
def test_a_companys_line_is_never_cut_at_its_legal_form_or_an_initial(about, line):
    """Live R31.12 semis: seven companies' lines were only their names ("Qnity Electronics, Inc", "Marvell Technology, Inc", "Daqo New Energy
    Corp"): the full stop of "Inc." was read as the end of the sentence."""
    assert B.one_line(about) == line


# ---------- 2. the annual report's business part ----------
def _report(body: str, pad: int = 0) -> str:
    toc = "<table><tr><td>Item 1.</td><td>Business</td><td>5</td></tr><tr><td>Item 1A.</td><td>Risk Factors</td><td>12</td></tr></table>"
    return ("<html><head><style>p{color:red}</style></head><body><ix:header><ix:hidden>ctx1 ctx2 Item 1. Business hidden</ix:hidden></ix:header>"
            f"<p>FORM 10-K</p>{toc}<p>This report contains forward-looking statements.</p>"
            f"<div><span style='font-weight:bold'>Item 1.</span> <span>Business</span></div>{body}"
            "<div>Item 1A. Risk Factors</div><p>Our business faces many risks that could harm our results.</p>" + "<p>x</p>" * pad + "</body></html>")


BODY = ("<p><b>Overview</b></p>"
        "<p>This Annual Report on Form 10-K contains forward-looking statements that involve risks and uncertainties about our business.</p>"
        "<p>Unless the context otherwise requires, the terms we, us and our mean Acme Materials, Inc. and its subsidiaries taken together.</p>"
        "<p>We were incorporated in Delaware in 1998 and completed our initial public offering in 2004.</p>"
        "<p>Acme Materials, Inc. is a leading supplier of slurries, pads and <span>photoresists</span> used in&nbsp;semiconductor "
        "manufacturing. We sell our materials to chip makers in the U.S. and Asia. Our products are used in advanced logic and memory.</p>"
        + "<p>Segments</p>" + "<p>We report two segments, which are described in the paragraphs that follow this one in more detail.</p>" * 12)


def test_the_business_opening_is_the_first_prose_after_the_heading_in_the_companys_words():
    text = sec.report_lines(_report(BODY))
    assert "ctx1" not in text and "color:red" not in text and "\nItem 1. Business\n" in "\n" + text + "\n"
    got = sec.business_opening(text)
    # the contents page's "Item 1. Business", the cautions, the defined terms and the incorporation line are not the opening
    assert got.startswith("Acme Materials, Inc. is a leading supplier of slurries, pads and photoresists used in semiconductor manufacturing. "
                          "We sell our materials to chip makers in the U.S. and Asia.")
    assert "forward-looking" not in got and "incorporated" not in got and "Risk Factors" not in got and len(got) <= 700
    assert got.endswith(".")                                                        # whole sentences only
    assert sec.business_opening(sec.report_lines("<p>Item 1. Business</p><p>Short.</p><p>Item 1A. Risk Factors</p>")) == ""
    assert sec.business_opening("no such part here") == ""


def test_a_foreign_filers_business_overview_is_read_the_same_way():
    html = ("<p>Item 4. Information on the Company</p><p>B. Business Overview</p>"
            "<p>We are a provider of solar cells and modules, with plants in two countries, and we sell them to project developers.</p>"
            + "<p>Our plants ran at full capacity during the year and we added a second line for cells in the fourth quarter.</p>" * 20
            + "<p>C. Organizational Structure</p><p>We have nine subsidiaries.</p>")
    assert sec.business_opening(sec.report_lines(html)).startswith("We are a provider of solar cells and modules")


def _sec_with(pages: dict, calls: list):
    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(str(req.url))
        body = pages.get(str(req.url))
        return httpx.Response(200, content=body.encode()) if body is not None else httpx.Response(404)
    return sec.SEC(transport=httpx.MockTransport(handler))


def _subs(form="10-K"):
    return {"cik": 1234, "filings": {"recent": {"form": ["8-K", form, "10-Q"], "filingDate": ["2026-03-01", "2026-02-20", "2025-11-01"],
                                                "accessionNumber": ["0001-26-000009", "0001-26-000007", "0001-25-000005"],
                                                "primaryDocument": ["a8k.htm", "acme-10k.htm", "q.htm"]}}}


def test_the_feed_reads_the_front_of_the_latest_annual_report_once_and_keeps_only_the_lines(monkeypatch):
    url = "https://www.sec.gov/Archives/edgar/data/1234/000126000007/acme-10k.htm"
    calls: list = []
    feed = _sec_with({url: _report(BODY, pad=40000)}, calls)
    monkeypatch.setattr(sec, "BUSINESS_BYTES", 64 * 1024)                           # the report is longer than what is read of it
    got = feed.business(_subs())
    assert got["form"] == "10-K" and got["filed"] == "2026-02-20" and got["url"] == url
    assert got["text"].startswith("Acme Materials, Inc. is a leading supplier of slurries")
    assert feed.business(_subs()) == got and calls == [url]                         # kept: the report is read once
    assert len(json.dumps(feed.cache.get(sec.BUSINESS_KEY + (url,)))) < 2000                # the few lines, never the report
    none = {"cik": 1234, "filings": {"recent": {"form": ["8-K"], "filingDate": ["2026-03-01"], "accessionNumber": ["0001-26-000009"],
                                                "primaryDocument": ["a8k.htm"]}}}
    assert feed.business(none) is None and calls == [url]                           # no annual report on file: nothing is read


def test_a_report_whose_business_part_is_not_found_is_not_read_again():
    url = "https://www.sec.gov/Archives/edgar/data/1234/000126000007/acme-10k.htm"
    calls: list = []
    feed = _sec_with({url: "<html><body><p>Nothing of use here.</p></body></html>"}, calls)
    assert feed.business(_subs()) is None and feed.business(_subs()) is None and calls == [url]


# ---------- 2b. the article check ----------
def test_an_article_about_another_company_or_about_no_company_is_not_the_companys():
    myth = {"title": "Ichor", "description": "Blood of the gods in Greek mythology",
            "extract": "In Greek mythology, ichor is the ethereal fluid making up the blood of the gods and/or immortals."}
    tyres = {"title": "Toyo Tires", "description": "Japanese tire company",
             "extract": "Toyo Tire Corporation, commonly known as Toyo Tires, is a multinational tire and rubber products company based in Itami."}
    own = {"title": "Qnity Electronics", "description": "American electronics materials company",
           "extract": "Qnity Electronics, Inc. is a major provider of materials for the semiconductor manufacturing and electronics industries."}
    assert not news.fits_company("Ichor Holdings, Ltd.", myth)
    assert not news.fits_company("TOYO Co., Ltd", tyres)
    assert news.fits_company("Qnity Electronics, Inc.", own)
    assert news.fits_company("Bharti Airtel Ltd", {"title": "Bharti Airtel", "extract": "Bharti Airtel is an Indian multinational telecommunications company."})
    assert news.fits_company("Netlist Inc", {"title": "Netlist (company)", "extract": "Netlist, Inc. designs and sells memory subsystems."})
    assert news.fits_company("Kulicke & Soffa Industries Inc", {"title": "Kulicke & Soffa", "extract": "A maker of semiconductor assembly equipment."})
    assert not news.fits_company("Acme Inc", None) and not news.fits_company("Acme Inc", {"title": "Acme", "extract": ""})
    assert news.company_text("It provides broadband services") and not news.company_text(myth["extract"])


# ---------- 2c. the stored description ----------
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


def _hub(monkeypatch, wiki=None, profile=None):
    asked = {"wiki": [], "profile": []}
    hub = types.SimpleNamespace(
        wiki=types.SimpleNamespace(company=lambda name: asked["wiki"].append(name) or (wiki or {}).get(name)),
        screener=types.SimpleNamespace(company=lambda sym: asked["profile"].append(sym) or (profile or {}).get(sym) or {}))
    monkeypatch.setattr(TR, "_routes", lambda: types.SimpleNamespace(hub=hub, public_facts=None))
    return asked


def test_a_us_company_with_no_article_gets_its_annual_reports_opening_stored_once(store, monkeypatch):
    _hub(monkeypatch)
    reads = []
    monkeypatch.setattr(TR, "_business_read", lambda sym: reads.append(sym) or QNITY_10K)
    got, pending = TR.evidence_reader("US", {"Q": "Qnity Electronics, Inc."})(["Q"])
    assert got["Q"]["about"] == QNITY_10K and not pending and reads == ["Q"]
    rec = json.loads(store["theme:evidence:US:Q"])
    assert rec["about"] == QNITY_10K and rec["v"] == TR.ABOUT_V and "owed" not in rec
    TR.EVIDENCE_CACHE.clear()                                                       # a restart: the stored lines serve, nothing is read again
    assert TR.evidence_reader("US", {})(["Q"])[0]["Q"]["about"] == QNITY_10K and reads == ["Q"]
    assert TR._about_reader("US", {}, 0)("Q") == QNITY_10K


def test_a_full_article_needs_no_annual_report_and_a_wrong_article_is_replaced_by_it(store, monkeypatch):
    # gl52 (R52, updated on purpose): an article that has a sentence in the company's own words about its work (an encyclopedia's opening
    # alone is read with the annual report too: test_gl52_fixes)
    full = "Marvell Technology, Inc. is an American company. It develops and produces semiconductors and related technology for data centers. " * 3
    myth = "In Greek mythology, ichor is the ethereal fluid making up the blood of the gods and/or immortals. " * 3
    _hub(monkeypatch, wiki={"Marvell Technology": {"title": "Marvell Technology", "extract": full}, "Ichor": {"title": "Ichor", "extract": myth}})
    reads = []
    monkeypatch.setattr(TR, "_business_read", lambda sym: reads.append(sym) or "We are a leader in the design and manufacturing of fluid delivery subsystems for semiconductor capital equipment.")
    got, _ = TR.evidence_reader("US", {"MRVL": "Marvell Technology, Inc.", "ICHR": "Ichor Holdings, Ltd."})(["MRVL", "ICHR"])
    assert got["MRVL"]["about"] == C.clean_description(full) and reads == ["ICHR"]
    assert got["ICHR"]["about"].startswith("We are a leader in the design and manufacturing of fluid delivery subsystems") and "mythology" not in got["ICHR"]["about"]


def test_an_indian_company_keeps_its_profile_and_its_article_and_reads_no_annual_report(store, monkeypatch):
    line = "The company has created an ecosystem, comprising networks, devices, applications and content to provide seamless services"
    wiki = ("Jio Platforms Limited is an Indian multinational technology company, headquartered in Mumbai. Established in 2019, it acts as a holding "
            "company for India's largest mobile network operator, Jio, and other digital businesses of Reliance.")
    _hub(monkeypatch, wiki={"Jio Platforms": {"title": "Jio Platforms", "extract": wiki}}, profile={"JPL": {"about": line, "industry_path": ["Telecom", "Services"]}})
    monkeypatch.setattr(TR, "_business_read", lambda sym: pytest.fail("no annual report is read for an Indian company"))
    got, _ = TR.evidence_reader("IN", {"JPL": "Jio Platforms Ltd"})(["JPL"])
    assert got["JPL"]["about"] == f"{line} {wiki}" and got["JPL"]["industry"] == "Telecom > Services"
    assert TR.filed_business("IN", "JPL") == ("", False)


def test_annual_reports_are_read_a_few_a_minute_and_the_rest_are_owed_never_a_burst(store, monkeypatch):
    _hub(monkeypatch)
    reads = []
    monkeypatch.setattr(TR, "_business_read", lambda sym: reads.append(sym) or f"{sym} Corp is a maker of power chips for cars and factories, sold to makers of vehicles in thirty countries.")
    syms = [f"S{i:02d}" for i in range(20)]
    got, pending = TR.evidence_reader("US", {})(syms)
    assert len(reads) == TR.FILING_READS_PER_MINUTE == TR.DESCRIBE_READS and not pending
    owed = [s for s in syms if json.loads(store[f"theme:evidence:US:{s}"]).get("owed")]
    assert len(owed) == len(syms) - TR.FILING_READS_PER_MINUTE and set(owed) == set(syms) - set(reads)
    assert all(TR.thin_about(json.loads(store[f"theme:evidence:US:{s}"]), "US") for s in owed)
    assert all(TR.EVIDENCE_CACHE.get(f"theme:evidence:US:{s}") is None for s in owed)        # asked again in the next batch, not held for hours
    monkeypatch.setattr(TR, "filing_reads", TR.Window())                                     # the next minute
    again = owed[0]
    assert TR.evidence_reader("US", {})([again])[0][again]["about"].startswith(f"{again} Corp is a maker of power chips")
    assert "owed" not in json.loads(store[f"theme:evidence:US:{again}"]) and reads[-1] == again


def test_a_busy_feed_leaves_the_read_owed_and_a_company_that_files_none_is_not_asked_again(store, monkeypatch):
    def busy(sym):
        raise SourceError("The SEC", "busy", busy=True)

    def none(sym):
        raise SourceError("The SEC", "X isn't a company that files with the SEC.")
    assert TR.filed_business("US", "A", read=busy) == ("", True)
    assert TR.filed_business("US", "B", read=none) == ("", False)
    assert TR.filed_business("US", "C", read=lambda s: "") == ("", False)


def test_which_stored_descriptions_are_read_once_more():
    now = datetime.now(timezone.utc).isoformat()
    assert TR.thin_about({"at": now, "about": "", "v": 2}, "US")                                    # none kept before the annual-report source
    assert TR.thin_about({"at": now, "about": "Qnity Electronics, Inc", "v": 2}, "US")
    assert not TR.thin_about({"at": now, "about": "", "v": TR.ABOUT_V}, "US")                       # read in this format already: kept its time
    assert not TR.thin_about({"at": now, "about": " ".join(["word"] * 40), "v": 2}, "IN")
    myth = "In Greek mythology, ichor is the ethereal fluid making up the blood of the gods and/or immortals. " * 3
    assert TR.thin_about({"at": now, "about": myth, "v": 2}, "US") and not TR.thin_about({"at": now, "about": myth, "v": TR.ABOUT_V}, "US")
    full = "Lam Research Corporation is an American supplier of wafer-fabrication equipment and related services to the semiconductor industry. " * 2
    # gl52 (R52, updated on purpose): an encyclopedia's opening alone, kept before format 5, is read once more (its annual report added)
    assert TR.thin_about({"at": now, "about": full, "v": 2}, "US") and not TR.thin_about({"at": now, "about": full, "v": TR.ABOUT_V}, "US")
    own = full + "It sells etch and deposition systems to chip makers."
    assert not TR.thin_about({"at": now, "about": own, "v": 2}, "US")
    assert TR.thin_about({"at": now, "about": "", "v": TR.ABOUT_V, "owed": True}, "US")


# ---------- 3. sub-themes ----------
def _co(t, what):
    return {"ticker": t, "name": t, "what": what}


TELECOM = [
    {"layer": "Mobile and broadband operators", "companies": [
        _co("VI", "Vodafone Idea is one of the leading telecom service providers in India. The Company is engaged in the business of Mobility and Long Distance services"),
        _co("AIRTEL", "Bharti Airtel Ltd is one of the world’s leading providers of telecommunication services with presence in 18 countries"),
        _co("JIO", "The company has created an ecosystem, comprising networks, devices, applications and content to provide seamless services"),
        _co("HEXA", "Bharti Hexacom Ltd provides consumer mobile services, fixed-line telephone and broadband services in Rajasthan"),
        _co("TTML", "Tata Teleservices Ltd is engaged in the business of Wired and wireless telecommunication activities"),
        _co("QUAD", "Quadrant Televentures Ltd is a telecom service provider offering fixed line, broadband and leased line services in Punjab"),
        _co("CITY", "City Online Services Ltd is an internet service provider in Hyderabad"),
        _co("OLDGSM", "Old Circle Ltd provides broadband in Punjab. It discontinued its GSM mobile services in 2017"),
        _co("NOWORDS", "")]},
    {"layer": "Enterprise connectivity and messaging", "companies": [
        _co("ROUTE", "Route Mobile Limited is a cloud communications platform service provider catering to enterprises and mobile network operators"),
        _co("TCOM", "It delivers managed solutions to multinational companies and service providers")]},
    {"layer": "Other telecom companies", "official": True, "companies": [_co("HANDSET", "It distributes mobile handsets of reputed brands")]},
]
JIO_ABOUT = ("The company has created an ecosystem, comprising networks, devices, applications and content to provide seamless services. Jio Platforms "
             "Limited is an Indian multinational technology company. It acts as a holding company for India's largest mobile network operator, Jio.")


def test_a_sub_themes_word_said_another_way_counts_in_its_main_layer_and_broadband_only_stays_out():
    """GPT review of R31.9: Jio Platforms was not among "Mobile network operators" (its line: "networks, devices, applications"); Airtel's
    line says "telecommunication services"."""
    sub = {"name": "Mobile network operators", "companies": [{"ticker": "VI"}]}
    got = [c["ticker"] for c in sub_members(sub, TELECOM, {"JIO": JIO_ABOUT}.get)]
    assert got == ["VI", "AIRTEL", "JIO", "HEXA", "TTML"]
    # without its whole stored description Jio's line names no mobile service: left as the map has it, never guessed
    assert [c["ticker"] for c in sub_members(sub, TELECOM)] == ["VI", "AIRTEL", "HEXA", "TTML"]
    # a company of another layer (a messaging platform that serves mobile operators, a handset distributor) never joins by the word
    assert not {"ROUTE", "TCOM", "HANDSET"} & set(got) and not {"QUAD", "CITY", "OLDGSM", "NOWORDS"} & set(got)


def test_another_way_of_saying_it_counts_only_in_the_layer_that_holds_most_of_the_sub_theme():
    layers = [{"layer": "Operators", "companies": [_co("A", "x"), _co("B", "y"), _co("W1", "It offers cellular plans to four million subscribers")]},
              {"layer": "Enterprise", "companies": [_co("C", "z"), _co("W2", "It sells wireless backhaul to enterprises"), _co("M2", "It sells mobile plans to businesses")]}]
    sub = {"name": "Mobile operators", "companies": [{"ticker": "A"}, {"ticker": "B"}, {"ticker": "C"}]}
    assert [c["ticker"] for c in sub_members(sub, layers)] == ["A", "B", "C", "W1", "M2"]       # the word itself counts in either layer (R34)
    wide = {"name": "Mobile, tower and fibre operators", "companies": [{"ticker": "A"}]}
    assert [c["ticker"] for c in sub_members(wide, layers)] == ["A"]                              # three words that set it apart: left as the map has it
    assert sub_members({"name": "Mobile operators", "companies": []}, layers) == []


def test_a_us_wireless_sub_theme_takes_mobile_carriers_and_leaves_cable_broadband_out():
    layers = [{"layer": "Telecom carriers", "companies": [
        _co("VZW", "Verizon is an American telecommunications company that offers wireless services"),
        _co("TMOB", "T-Mobile US provides mobile voice, messaging and data services to 120 million customers"),
        _co("ATNT", "AT&T Inc. is a provider of telecommunications services in the United States"),
        _co("CABL", "Charter provides broadband internet, cable television and voice services over its cable network"),
        _co("FIBR", "Frontier is a telecommunications company offering fiber broadband to homes")]}]
    got = [c["ticker"] for c in sub_members({"name": "Wireless carriers", "companies": [{"ticker": "VZW"}]}, layers)]
    assert got == ["VZW", "TMOB", "ATNT"]


# ---------- 4. materials and equipment ----------
def test_the_annual_reports_words_make_a_chip_materials_supplier_an_ingredient_maker_its_evidence_shows():
    ev = C.model_evidence(SEMI, QNITY_10K, (), "From its own filings: Annual report (10-K). Quarterly report (10-Q).")
    for given in ("manufacturing", "unknown", ""):
        assert C.refine_model(given, ev) == "components", given
    assert C.model_confidence("components", ev, "") == "medium"                     # its own words name the materials: counted, not left out
    assert C.model_confidence("components", C.model_evidence(SEMI, "Sells things to people."), "") == "low"
    # customers named as equipment makers don't make a materials supplier an equipment maker; its own equipment does
    oem = "supplies chemicals and gases used in semiconductor manufacturing to chip makers and original equipment manufacturers"
    assert C.chip_materials(oem) and C.chip_materials("sells substrates for semiconductors to wafer fabs and equipment makers")
    assert not C.chip_materials("makes wafer fab equipment and the chemicals used in semiconductor cleaning tools")
    assert C.refine_model("manufacturing", C.model_evidence("Semiconductor Equipment", "makes wafer fab equipment and process tools")) == "manufacturing"
    assert C.refine_model("manufacturing", C.model_evidence("Specialty Chemicals", "makes dyes and pigments for textiles")) == "manufacturing"


def test_a_kept_placement_moves_the_materials_supplier_out_of_the_equipment_layer_once_its_words_are_kept():
    """Live R31.12 semis: Qnity sat in "Semiconductor equipment" as a maker of its own products."""
    about = {"Q": QNITY_10K, "MAT2": "AXT is a materials science company that develops and produces semiconductor substrates, also known as wafers.",
             "EQ1": "supplies equipment, services and software for the manufacture of semiconductor chips",
             "EQ2": "is a supplier of wafer-fabrication equipment and related services to the semiconductor industry",
             "EQ3": "makes wafer fab equipment for process control and yield management"}
    co = lambda t, cap: {"ticker": t, "name": t, "cap": cap, "industry": SEMI}       # noqa: E731
    m = {"value_chain": [{"layer": "Semiconductor equipment", "description": "Makers of the tools fabs use.", "companies": [co("EQ1", 9), co("EQ2", 8), co("EQ3", 7)]},
                         {"layer": "Semiconductors", "official": True, "basis": "industry", "companies": [co("Q", 5), co("MAT2", 4)]}]}
    kept = {"assign": {"Q": {"layer": "Semiconductor equipment", "by": "ai"}, "MAT2": {"layer": "Semiconductor equipment", "by": "ai"}},
            "models": {"EQ1": "manufacturing", "EQ2": "manufacturing", "EQ3": "manufacturing", "Q": "manufacturing", "MAT2": "unknown"},
            "model_confidence": {"EQ1": "high", "EQ2": "high", "EQ3": "high", "Q": "medium"}}
    out, got = B.place_rest(m, "Semiconductors", about.get, ask=None, kept=kept, facts_of=lambda s: {"industry": SEMI})
    where = {c["ticker"]: v["layer"] for v in out["value_chain"] for c in v["companies"]}
    assert got["models"]["Q"] == got["models"]["MAT2"] == "components"
    assert where["Q"] == where["MAT2"] != "Semiconductor equipment" and where["EQ1"] == where["EQ2"] == where["EQ3"] == "Semiconductor equipment"
    row = next(c for v in out["value_chain"] for c in v["companies"] if c["ticker"] == "Q")
    assert row["model"] == "components" and row["model_confidence"] == "medium"
    # before its words were kept (only its name), nothing could tell it from the equipment makers
    thin, _ = B.place_rest(m, "Semiconductors", {**about, "Q": "Qnity Electronics, Inc", "MAT2": ""}.get, ask=None, kept=kept, facts_of=lambda s: {"industry": SEMI})
    assert {c["ticker"]: v["layer"] for v in thin["value_chain"] for c in v["companies"]}["Q"] == "Semiconductor equipment"


def test_a_dive_reads_whole_descriptions_from_the_store_only_and_never_the_filings_lines(store, monkeypatch):
    now = datetime.now(timezone.utc).isoformat()
    store["theme:evidence:IN:JIO"] = json.dumps({"at": now, "about": JIO_ABOUT, "industry": "", "v": TR.ABOUT_V})
    store["theme:evidence:IN:NONE"] = json.dumps({"at": now, "about": "", "industry": "", "v": TR.ABOUT_V})
    monkeypatch.setattr(TR, "own_filings", lambda region, sym: "From its own filings: Launch of mobile plans.")
    monkeypatch.setattr(TR, "evidence_reader", lambda *a: pytest.fail("a dive reads no company page"))
    reads = []
    get = TR.db.get_setting
    monkeypatch.setattr(TR.db, "get_setting", lambda k: reads.append(k) or get(k))
    about = TR.kept_about("IN")
    assert about("JIO") == JIO_ABOUT and about("NONE") is None and about("NEVER") is None
    assert about("NEVER") is None and reads.count("theme:evidence:IN:NEVER") == 1          # looked up once a dive
