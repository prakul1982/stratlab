"""Company deep dive: growth, margins and capex from the reported numbers; document selection and reading; the AI
reads (business model, capex and growth plans) cleaned and stored; the endpoints and their limits."""
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app import db, deepdive, docs
from app.intel.net import SourceError
from tests.pdfmaker import make_pdf

YEARS = ["Mar 2020", "Mar 2021", "Mar 2022", "Mar 2023", "Mar 2024", "Mar 2025"]


def company():
    t = lambda rows, cols=YEARS: {"cols": cols, "rows": rows}
    return {
        "name": "Acme Industries", "about": "Acme makes industrial pumps for water utilities and oil refineries.",
        "pl": t({"Sales": [100, 110, 130, 150, 170, 200, 210], "OPM %": [15, 16, 17, 18, 18, 19, 19],
                 "Depreciation": [5, 6, 7, 8, 9, 10, 10], "Net Profit": [10, 12, 15, 18, 20, 25, 26]}, YEARS + ["TTM"]),
        "balance": t({"Fixed Assets": [50, 55, 60, 70, 80, 95], "CWIP": [5, 5, 10, 8, 12, 10], "Borrowings": [20, 22, 25, 30, 28, 26]}),
        "cashflow": t({"Cash from Operating Activity": [12, 14, 18, 20, 24, 30], "Cash from Investing Activity": [-8, -10, -15, -18, -22, -25]}),
        "quarters": {"cols": ["Q1", "Q2", "Q3", "Q4", "Q5", "Q6"], "rows": {"Sales": [40, 45, 50, 52, 48, 54], "OPM %": [18, 19, 19, 20, 19, 20],
                                                                         "Net Profit": [5, 6, 6, 7, 6, 7]}},
    }


def test_numbers_growth_capex_and_cash():
    n = deepdive.numbers(company())
    y = {r["year"]: r for r in n["years"]}
    assert "TTM" not in y and y["Mar 2025"]["sales"] == 200
    # capex FY25 = (95-80) fixed assets + (10-12) work in progress + 10 depreciation = 23
    assert y["Mar 2025"]["capex"] == 23 and y["Mar 2025"]["fcf"] == 7 and y["Mar 2025"]["capex_pct_sales"] == 11.5
    assert y["Mar 2020"]["capex"] is None                      # no earlier year to compare with
    assert round(n["growth"]["sales_cagr_5y"], 1) == 14.9 and n["growth"]["sales_cagr_3y"] is not None
    assert n["quarters"][4]["sales_yoy"] == 20.0 and n["quarters"][3]["sales_yoy"] is None
    assert n["capex_3y_total"] == 20 + 19 + 23


def test_numbers_survive_missing_tables():
    n = deepdive.numbers({"pl": {"cols": YEARS[:2], "rows": {"Sales": [1, 2]}}})
    assert n["years"][1]["capex"] is None and n["growth"]["sales_cagr_3y"] is None and n["quarters"] == []


def test_documents_picks_presentations_and_transcripts():
    items = [{"at": "2026-08-10T10:00", "category": "concall", "subject": "Analysts Meet", "text": "Transcript of the Q1 FY27 earnings call", "url": "https://nsearchives.nseindia.com/a.pdf"},
             {"at": "2026-08-01T10:00", "category": "presentation", "subject": "Investor Presentation", "text": "", "url": "https://nsearchives.nseindia.com/b.pdf"},
             {"at": "2026-07-01T10:00", "category": "concall", "subject": "Intimation of call", "text": "Schedule of analyst meet", "url": "https://nsearchives.nseindia.com/c.pdf"},
             {"at": "2026-06-01T10:00", "category": "presentation", "subject": "Investor Presentation", "text": "", "url": None}]
    assert [d["kind"] for d in deepdive.documents(items)] == ["transcript", "presentation"]


def test_document_reader_is_limited_to_exchange_pdfs():
    assert docs.allowed("https://nsearchives.nseindia.com/corporate/x.pdf")
    assert not docs.allowed("https://evil.example.com/x.pdf") and not docs.allowed("http://nsearchives.nseindia.com/x.pdf")
    assert not docs.allowed("https://nsearchives.nseindia.com/x.html")
    pdf = make_pdf(["Business overview", "We plan capex of Rs 500 crore for a new plant by FY28."])
    served = {"/ok.pdf": pdf, "/big.pdf": b"%PDF" + b"0" * (docs.MAX_BYTES + 10), "/page.pdf": b"<html>login</html>"}
    t = httpx.MockTransport(lambda r: httpx.Response(200, content=served[r.url.path]))
    d = docs.Docs(transport=t)
    assert "Rs 500 crore" in d.text("https://nsearchives.nseindia.com/ok.pdf")
    for bad, msg in (("https://nsearchives.nseindia.com/big.pdf", "too large"), ("https://nsearchives.nseindia.com/page.pdf", "didn't return a PDF"),
                     ("https://example.com/ok.pdf", "the exchange's or the company's own site")):
        with pytest.raises(SourceError) as e:
            d.text(bad)
        assert msg in str(e.value)


def test_windows_keep_the_passages_that_matter():
    text = "intro " * 500 + "Our CAPEX plan is Rs 900 crore. " + "filler " * 500 + "Guidance: 20% growth."
    w = docs.windows(text, [r"capex", r"guidance"], width=40, limit=400)
    assert "CAPEX plan" in w and "Guidance" in w and len(w) <= 420 and "\n…\n" in w
    assert docs.windows("no keywords here", [r"capex"], limit=5) == "no k" + "e"


FILLER = " Further discussion of the quarter." * 100       # real documents run to pages; cover letters don't


class FakeDocs:
    def __init__(self, texts, pad=True): self.texts, self.pad = texts, pad
    def text(self, url, extra_hosts=()):
        if url not in self.texts:
            raise SourceError("the exchange", "gone")
        return self.texts[url] + (FILLER if self.pad and not self.texts[url].startswith("COVER") else "")


DOCS = [{"kind": "transcript", "at": "2026-08-10T10:00", "title": "Q1 FY27 call transcript", "url": "u1"},
        {"kind": "presentation", "at": "2026-08-01T10:00", "title": "Investor Presentation", "url": "u2"},
        {"kind": "transcript", "at": "2026-05-10T10:00", "title": "Q4 FY26 call transcript", "url": "u3"}]


def fake_ai(calls):
    def complete(system, text, **kw):
        calls.append((system[:40], text, kw.get("kind")))
        if "makes money" in system:
            return json.dumps({"summary": "Acme sells pumps.", "segments": [{"name": "Water", "share_pct": 60, "what": "utilities"},
                                                                             {"name": "", "share_pct": 5}, {"name": "Oil", "share_pct": "40"}],
                               "customers": "Utilities", "drivers": ["Tenders"], "strengths": ["Brand"], "risks": ["Steel prices"]})
        return json.dumps({"capex": [{"what": "New plant", "amount": "Rs 500 crore", "timeline": "FY28", "status": "planned",
                                      "quote": "We plan capex of Rs 500 crore", "source": "S1"},
                                     {"what": "Odd", "status": "maybe", "source": "S9"}],
                           "outlook": [{"statement": "15% growth", "quote": "we expect 15%", "source": "s2"}]})
    return complete


def test_read_builds_clean_business_and_plans(monkeypatch):
    calls = []
    monkeypatch.setattr(deepdive, "complete", fake_ai(calls))
    d = FakeDocs({"u1": "We plan capex of Rs 500 crore for a new plant. We expect 15% growth.",
                  "u2": "Business overview: pumps. We plan capex of Rs 500 crore for a new plant."})
    out = deepdive.read("ACME", "Acme", "Pumps", DOCS, d, (None, None))
    assert all(c[2] == "long" for c in calls) and "[S1] presentation" in calls[0][1]
    b = out["business"]
    assert [s["name"] for s in b["segments"]] == ["Water", "Oil"] and b["segments"][1]["share_pct"] == 40.0
    assert b["sources"][0]["title"] == "Investor Presentation"
    p = out["plans"]
    assert p["capex"][0]["source"]["url"] == "u2" and len(p["capex"]) == 1        # "Odd" has no quote in any document: dropped
    assert p["outlook"][0]["source"]["url"] == "u1"            # labels are matched case-insensitively
    assert any("Q4 FY26" in x for x in out["problems"])         # an unreadable document is reported, not fatal


@pytest.fixture
def api(monkeypatch):
    from app import main
    from app.config import settings
    kv, usage = {}, []
    monkeypatch.setattr(db, "set_setting", lambda k, v: kv.__setitem__(k, v))
    monkeypatch.setattr(db, "get_setting", lambda k: kv.get(k))
    monkeypatch.setattr(db, "count_usage", lambda uid, kind, since: len(usage))
    monkeypatch.setattr(db, "add_usage", lambda uid, kind: usage.append(kind))
    for k, v in (("RAZORPAY_KEY_ID", "rzp_test_x"), ("RAZORPAY_KEY_SECRET", "s"), ("RAZORPAY_PLAN_BASIC", "b"), ("RAZORPAY_PLAN_PRO", "p")):
        monkeypatch.setattr(settings, k, v)
    monkeypatch.setattr(settings, "RESEARCH_AI_PER_DAY", 2)

    class Scr:
        def company(self, sym):
            if sym != "ACME":
                raise SourceError("Screener.in", "Screener.in has no page for that.")
            return company()

    class Feed:
        def announcements(self, sym, days=365):
            return [{"at": d["at"], "category": "concall" if d["kind"] == "transcript" else "presentation", "subject": d["title"],
                     "text": "transcript" if d["kind"] == "transcript" else "", "url": "https://nsearchives.nseindia.com/" + d["url"] + ".pdf", "severity": "info"}
                    for d in DOCS]
    monkeypatch.setattr(main.research_hub, "screener", Scr())
    monkeypatch.setattr(main, "filings_feed", Feed())
    monkeypatch.setattr(main, "deep_docs", FakeDocs({"https://nsearchives.nseindia.com/u1.pdf": "capex of Rs 500 crore", "https://nsearchives.nseindia.com/u2.pdf": "pumps. We plan capex of Rs 500 crore"}))
    calls = []
    monkeypatch.setattr(deepdive, "complete", fake_ai(calls))
    who = {"p": {"id": "u1", "plan": "free", "_plan": "free"}}
    main.app.dependency_overrides[main.current_profile] = lambda: who["p"]
    yield TestClient(main.app), who, calls, usage
    main.app.dependency_overrides.clear()


def test_endpoints_are_pro_store_reads_and_respect_the_daily_limit(api):
    c, who, calls, usage = api
    assert c.get("/research/deep/ACME").status_code == 402
    who["p"] = {"id": "u1", "plan": "pro", "_plan": "pro"}
    v = c.get("/research/deep/ACME").json()
    assert v["numbers"]["years"][-1]["capex"] == 23 and v["reads"] is None and len(v["documents"]) == 3
    err = c.get("/research/deep/NOPE").json()["detail"]["message"]
    assert "Screener" not in err                                    # the data source isn't named
    r = c.post("/research/deep/ACME/read").json()
    assert r["reads"]["business"]["summary"] == "Acme sells pumps." and not r["reads_stale"] and len(calls) == 2 and usage == ["research_ai"]
    c.post("/research/deep/ACME/read")                              # stored and fresh: no new AI call, nothing counted
    assert len(calls) == 2 and usage == ["research_ai"]
    assert c.get("/research/deep/ACME").json()["reads"]["plans"]["capex"][0]["amount"] == "Rs 500 crore"
    c.post("/research/deep/ACME/read?refresh=true")
    assert len(usage) == 2
    assert c.post("/research/deep/ACME/read?refresh=true").status_code == 429


def test_cover_letters_are_skipped_for_the_next_document():
    docs = [{"kind": "presentation", "at": "2026-08-05", "title": "Updates", "url": "c1"},
            {"kind": "presentation", "at": "2026-08-01", "title": "Investor Presentation", "url": "p1"}]
    problems = []
    got = deepdive.readable(FakeDocs({"c1": "COVER Please find enclosed the presentation.", "p1": "Business overview"}), docs, 1, problems)
    assert [d["url"] for d, _ in got] == ["p1"] and problems == []
    problems = []
    assert deepdive.readable(FakeDocs({"c1": "COVER only"}), docs[:1], 1, problems) == []
    assert "short letter" in problems[0] and "no link" in problems[1]


def test_banks_get_no_capex_or_operating_margin_checks():
    from app import checklist
    p = company()
    p["pl"]["rows"] = {"Revenue": p["pl"]["rows"]["Sales"], "Financing Profit": [1] * 7, "Financing Margin %": [-17] * 7,
                       "Depreciation": p["pl"]["rows"]["Depreciation"], "Net Profit": p["pl"]["rows"]["Net Profit"]}
    p["ratios"] = {"ROCE": "7 %", "ROE": "16.5 %"}
    n = deepdive.numbers(p)
    assert n["bank"] and all(y["capex"] is None and y["fcf"] is None for y in n["years"])
    labels = {c["label"]: c for c in checklist.evaluate(p, n)["checks"]}
    assert labels["Return on equity"]["state"] == "pass" and "Return on capital employed" not in labels
    assert not {"Operating margin holding up", "Debt to equity", "Free cash flow, 3 years", "Profit turning into cash"} & labels.keys()
    from app import report_card as rc
    assert rc.check({"metric": "margin", "low": 4.0, "high": None, "period": "FY25"}, n)["result"] == "unchecked"


def test_negative_capex_estimate_is_left_blank():
    p = company()
    p["balance"]["rows"]["Fixed Assets"][3] = 40          # FY23 assets fall (a write-down): estimate would be negative
    y = {r["year"]: r for r in deepdive.numbers(p)["years"]}
    assert y["Mar 2023"]["capex"] is None and y["Mar 2023"]["fcf"] is None and y["Mar 2025"]["capex"] == 23


def test_transcript_passages_rank_guidance_over_boilerplate():
    t = ("Safe harbour: this call may contain forward-looking statements; we expect nothing. " * 5 + "Small talk. " * 400
         + "CFO: For FY27 we expect revenue growth of 18% and EBITDA margin of 24%, with capex of Rs 1,500 crore." + " Other. " * 400)
    cut = docs.ranked_windows(t, deepdive.PLAN_WORDS, width=120, limit=600)
    assert "revenue growth of 18%" in cut and "Safe harbour" not in cut


def test_plans_survive_a_cut_off_reply_and_drop_misattributed_quotes(monkeypatch):
    def complete(system, text, **kw):
        if "makes money" in system:
            return json.dumps({"summary": "Pumps.", "segments": []})
        return ('{"capex": [{"what": "New plant", "amount": "Rs 500 crore", "status": "planned", "quote": "We plan capex of Rs 500 crore", "source": "S2"},'
                ' {"what": "Wrong doc", "status": "planned", "quote": "We plan capex of Rs 500 crore", "source": "S1"},'
                ' {"what": "Cut off", "amo')
    monkeypatch.setattr(deepdive, "complete", complete)
    d = FakeDocs({"u1": "We plan capex of Rs 500 crore for a new plant.", "u2": "Business overview: pumps."})
    p = deepdive.read("ACME", "Acme", "Pumps", DOCS, d, (None, None))["plans"]
    assert [c["what"] for c in p["capex"]] == ["New plant"] and p["capex"][0]["source"]["kind"] == "transcript"


def test_a_letter_pointing_to_the_company_website_is_followed():
    pdf = make_pdf(["Transcript of the Q1 FY27 earnings call."] + ["CFO: We expect EBITDA margin of 24% in FY27."] * 80)
    letter = make_pdf(["Dear Sir, the transcript of the earnings call is available at",
                       "https://www.apollohospitals.com/apollo_pdf/transcript-q1fy27.pdf"])
    seen = []

    def handler(r):
        seen.append(str(r.url))
        if r.url.host == "www.apollohospitals.com" and r.url.path == "/old.pdf":
            return httpx.Response(301, headers={"location": "/apollo_pdf/transcript-q1fy27.pdf"})
        if r.url.host == "www.apollohospitals.com":
            return httpx.Response(200, content=pdf)
        return httpx.Response(200, content=letter)
    d = docs.Docs(transport=httpx.MockTransport(handler), check_host=lambda h: h == "www.apollohospitals.com")
    cands = [{"kind": "transcript", "at": "2026-08-19", "title": "Con. Call Updates", "url": "https://nsearchives.nseindia.com/l1.pdf"}]
    problems = []
    got = deepdive.readable(d, cands, 1, problems, ("apollohospitals.com",))
    assert got and got[0][0]["url"].startswith("https://www.apollohospitals.com/") and got[0][0]["via"].endswith("l1.pdf")
    assert "margin of 24%" in got[0][1] and problems == []
    assert "margin of 24%" in d.text("https://www.apollohospitals.com/old.pdf", ("apollohospitals.com",))   # redirect within the site
    # a site the company's own filing names (a CDN, a separate investor site) is read too, but never a private address
    assert deepdive.readable(d, cands, 1, [], ())
    probs = []
    docs._cache.clear()                                    # downloaded text is cached by link
    assert deepdive.readable(docs.Docs(transport=httpx.MockTransport(handler), check_host=lambda h: False), cands, 1, probs, ()) == []
    assert "isn't reachable from here" in " ".join(probs)
    blocked = docs.Docs(transport=httpx.MockTransport(handler), check_host=lambda h: False)
    with pytest.raises(SourceError):
        blocked.text("https://www.apollohospitals.com/x.pdf", ("apollohospitals.com",))
    assert not docs.allowed("https://evil.example.com/x.pdf", ("apollohospitals.com",))
    assert not docs.allowed("https://apollohospitals.com.evil.io/x.pdf", ("apollohospitals.com",))
    assert not docs.public_host("127.0.0.1") and not docs.public_host("10.0.0.5")


def test_a_letter_pointing_to_an_investor_page_finds_the_pdf_there():
    pdf = make_pdf(["Transcript of the Q1 FY27 earnings call."] + ["CFO: We expect EBITDA margin of 24% in FY27."] * 80)
    letter = make_pdf(["Dear Sir, the transcript is available on our website at", "www.acme.co.in/investors/calls"])
    page = """<html><a href="/files/annual-report-2026.pdf">Annual report</a>
      <a href="https://cdn.acme-files.net/q1fy27/earnings-call-transcript.pdf">Q1 FY27 Earnings call transcript</a></html>"""
    seen = []

    def handler(r):
        seen.append(str(r.url))
        if r.url.host == "www.acme.co.in":
            return httpx.Response(200, text=page)
        if r.url.host == "cdn.acme-files.net":
            return httpx.Response(200, content=pdf)
        return httpx.Response(200, content=letter)
    d = docs.Docs(transport=httpx.MockTransport(handler), check_host=lambda h: True)
    cands = [{"kind": "transcript", "at": "2026-08-19", "title": "Con. Call Updates", "url": "https://nsearchives.nseindia.com/l2-page.pdf"}]
    got = deepdive.readable(d, cands, 1, [], ())
    assert got and got[0][0]["url"] == "https://cdn.acme-files.net/q1fy27/earnings-call-transcript.pdf"
    assert "https://www.acme.co.in/investors/calls" in seen and not any("annual-report" in u for u in seen)
    assert docs.page_pdfs(page, "https://www.acme.co.in/x", "presentation")[0].endswith("annual-report-2026.pdf")   # no match: page order
    assert docs.web_links("see www.acme.co.in/investors. Email ir@acme.co.in or https://x.co/a.pdf") == ["https://www.acme.co.in/investors"]


def test_rupee_sign_is_put_back():
    assert docs.fix_rupee("ARPP grew 8% to ¥186,630") == "ARPP grew 8% to ₹186,630"
    assert docs.fix_rupee("capex of `1,200 crore") == "capex of ₹1,200 crore"
    t = docs.fix_rupee("Revenue X 70,435 mio; Sarjapur X944; Varanasi % 640; margin 24%; Model X1")
    assert "₹70,435" in t and "₹944" in t and "₹640" in t and "24%" in t and "Model X1" in t
    assert docs.fix_rupee("growth to X 70,435 once") == "growth to X 70,435 once"     # once isn't a pattern


def test_no_readable_call_is_not_charged(api):
    c, who, _calls, usage = api
    from app import main
    main.deep_docs.texts = {}                       # every transcript fails to download
    who["p"] = {"id": "u1", "plan": "pro", "_plan": "pro"}
    r = c.post("/research/deep/ACME/card")
    assert r.status_code == 422 and r.json()["detail"]["code"] == "no_readable_calls" and usage == []


def test_capex_amounts_need_a_unit_and_outlook_is_the_future():
    labels = {"S1": {"title": "Deck", "at": "2026-08-12", "url": "u", "kind": "presentation"}}
    p = deepdive.clean_plans({"capex": [{"what": "Sarjapur", "amount": "%70", "size": "455 beds", "status": "planned"},
                                        {"what": "Chennai", "amount": "₹945", "status": "under way"},
                                        {"what": "Jubilee Hills", "amount": "2230", "status": "planned"},
                                        {"what": "Varanasi", "amount": "Rs 640 crore", "status": "planned"}],
                              "outlook": [{"statement": "Revenue grew by 21% to Rs 70,435 mio", "quote": "x"},
                                          {"statement": "Expects 20% growth next year", "quote": "y"}]}, labels)
    assert [(c["what"], c["amount"], c["size"]) for c in p["capex"]] == [("Sarjapur", None, "455 beds"), ("Chennai", "₹945", None),
                                                                        ("Jubilee Hills", None, None), ("Varanasi", "Rs 640 crore", None)]
    assert [o["statement"] for o in p["outlook"]] == ["Expects 20% growth next year"]


def test_what_companies_call_their_deck_and_links_split_across_lines():
    items = [{"at": "2026-07-10T10:00", "category": "", "subject": "Updates", "text": "Fact Sheet for the quarter ended June 30, 2026", "url": "u1"},
             {"at": "2026-07-11T10:00", "category": "", "subject": "Quarterly Report", "text": "", "url": "u2"},
             {"at": "2026-07-12T10:00", "category": "", "subject": "Investor Release", "text": "Q1 FY27", "url": "u3"},
             {"at": "2026-07-13T10:00", "category": "", "subject": "Outcome of Board Meeting", "text": "Financial results", "url": "u4"}]
    assert [d["kind"] for d in deepdive.documents(items)] == ["presentation"] * 3
    letter = "The transcript is on our website at https://www.maruti\nsuzuki.com/corporate/investors for reference."
    assert docs.web_links(letter) == ["https://www.marutisuzuki.com/corporate/investors"]
    assert docs.web_links("see https://www.acme.com/investors\nfor details") == ["https://www.acme.com/investors"]


def test_a_letter_linking_the_annual_report_first_reads_the_transcript():
    pdf = make_pdf(["Transcript of the Q1 FY27 earnings call."] + ["CFO: We expect EBITDA margin of 24% in FY27."] * 80)
    letter = make_pdf(["Annual report: https://www.lt.com/ar/AnnualReport2026.pdf",
                       "Call transcript: https://www.lt.com/calls/Q1FY27-Earnings-Call-Transcript.pdf"])
    seen = []

    def handler(r):
        seen.append(r.url.path)
        if r.url.path.endswith("Transcript.pdf"):
            return httpx.Response(200, content=pdf)
        if r.url.path.endswith("AnnualReport2026.pdf"):
            return httpx.Response(500)
        return httpx.Response(200, content=letter)
    d = docs.Docs(transport=httpx.MockTransport(handler), check_host=lambda h: True)
    cands = [{"kind": "transcript", "at": "2026-08-03", "title": "Con. Call Updates", "url": "https://nsearchives.nseindia.com/lt-letter.pdf"}]
    got = deepdive.readable(d, cands, 1, [], ())
    assert got and got[0][0]["url"].endswith("Transcript.pdf") and "/ar/AnnualReport2026.pdf" not in seen
