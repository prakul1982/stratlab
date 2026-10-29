"""The IPO section's readers, on the real public files saved in fixtures/ipo (fetched on 25 Oct 2026): NSE's public-issue pages
(upcoming, past, and each issue's own page with its bids by category), BSE's public-issue list and listed-issue table, SEBI's lists
of draft and red herring documents, the public IPO calendar, EDGAR's search and filing list; and the offer documents (four
Indian ones, as the pages the readers use, and a US prospectus's start): the facts a rule reads, the checked AI summary, the
downloads and the ZIP."""
import gzip
import io
import json
import re
import zipfile

import httpx
import pytest

from app import ipo_docs as D  # noqa: I001
from app.intel import ipo_sources as S
from app.intel import us_calendar as U
from app.intel.net import SourceError
from tests import fake_ipo as F

ADVICE = re.compile(r"\b(buy|sell|hold|accumulate|avoid|apply|subscribe|attractive|cheap|expensive|undervalued|grey market|gmp)\b", re.I)


# ---------- NSE ----------
def test_nse_upcoming_and_past_lists():
    up = S.nse_upcoming(F.file("nse_upcoming.json"))
    assert [r["symbol"] for r in up] == ["MKSONS", "SFCTECH", "BLSPOLY", "EDELALTS"]
    assert up[0] == {"symbol": "MKSONS", "name": "M. K. Sons Fine Jewels Limited", "series": "EQ", "segment": "mainboard", "open": "2026-10-28",
                     "close": "2026-10-30", "low": 153.0, "high": 162.0, "size_shares": 17000000}
    assert S.nse_upcoming({}) == [] and S.nse_upcoming([]) == [] and S.nse_upcoming(None) == []
    past = S.nse_past(F.file("nse_past.json"))
    assert len(past) == 55 and not any(r["series"] == "DEBT" for r in past)         # a debt issue is not shares
    bon = next(r for r in past if r["symbol"] == "BONFIG")
    assert (bon["open"], bon["close"], bon["listing"], bon["low"], bon["high"], bon["price"], bon["segment"]) == \
        ("2026-10-15", "2026-10-19", "2026-10-23", 558.0, 586.0, 586.0, "mainboard")
    assert {r["segment"] for r in past} == {"mainboard", "sme"}
    assert next(r for r in past if r["symbol"] == "RKFAL")["segment"] == "sme"
    unlisted = next(r for r in past if r["symbol"] == "NSE")                      # "-": the exchange has no listing date for it
    assert unlisted["listing"] is None


def test_nse_issue_page_terms_and_bids():
    d = S.nse_detail(F.file("nse_detail_BONFIG.json"))
    assert (d["isin"], d["industry"], d["listing"], d["open"], d["close"]) == ("INE28SO01013", "Industrial Products", "2026-10-23", "2026-10-15", "2026-10-19")
    assert (d["low"], d["high"], d["lot"], d["face_value"], d["retail_max"]) == (558.0, 586.0, 25, 10.0, 200000)
    assert d["fresh"] is None and d["ofs"] == 43239042                                   # a pure offer for sale
    assert d["lead_managers"][0] == "Axis Capital Limited" and d["registrar"].startswith("MUFG Intime")
    assert d["docs"] == [{"kind": "RHP", "label": "Red Herring Prospectus", "url": "https://nsearchives.nseindia.com/content/ipo/RHP_BONFIG.zip"}]
    sub = d["subscription"]
    assert sub["as_of"] == "2026-10-19 19:00" and sub["times"] == 46.06                    # both exchanges' bids together
    rows = {r["sr"]: r for r in sub["rows"]}
    assert rows["1"]["label"] == "Qualified institutional buyers" and rows["1"]["times"] == 120.78
    assert rows["2.1"]["label"] == "Non-institutional, bids over ₹10 lakh" and rows["2.2"]["label"] == "Non-institutional, bids of ₹2 lakh to ₹10 lakh"
    assert (rows["3"]["label"], rows["3"]["times"], rows["3"]["offered"], rows["3"]["bid"]) == ("Retail individual investors", 5.91, 15116165, 89271650)
    assert rows["total"]["bid"] == 1394656825 and "1(a)" not in rows and "3(a)" not in rows         # the sub-rows of a category are left out


def test_an_issue_not_yet_open_has_no_bids_and_the_lot_is_read():
    d = S.nse_detail(F.file("nse_detail_MKSONS.json"))
    assert d["subscription"] is None and d["lot"] == 91
    assert (d["fresh"], d["ofs"]) == (13600000, 3400000)
    assert d["docs"][0]["url"].endswith("RHP_MKSONS.zip")


def test_an_sme_issue_gives_bids_without_category_sizes():
    d = S.nse_detail(F.file("nse_detail_RAVITA.json"))
    assert d["lot"] == 1200 and d["fresh"] == 10362000                                   # "Lot Size", not "Bid Lot"
    sub = d["subscription"]
    assert sub["times"] == 6.68                                                           # the exchange's own count for the issue
    assert all(r["offered"] is None for r in sub["rows"]) and sub["rows"][0]["bid"] == 26012400


@pytest.mark.parametrize("sym,fresh,ofs,fresh_cr,ofs_cr,total_cr", [
    ("FUSIONCX", None, None, 500.0, 202.0, None),          # "Fresh Issue aggregating upto Rs. 5000 million and Offer for Sale ... Rs.2020 million"
    ("VINOD", 4556400, None, None, None, 42.83),           # "Initial Public Offer of 45,56,400 Equity Shares at the aggregating to 4,283.02 lakhs"
    ("PAPADMALJI", 2572800, 230400, None, None, None),
])
def test_how_the_issue_size_is_worded(sym, fresh, ofs, fresh_cr, ofs_cr, total_cr):
    d = S.nse_detail(F.file(f"nse_detail_{sym}.json"))
    assert (d["fresh"], d["ofs"], d["fresh_cr"], d["ofs_cr"], d["total_cr"]) == (fresh, ofs, fresh_cr, ofs_cr, total_cr)


def test_odd_answers_are_no_issue_page():
    assert S.nse_detail({}) == {} and S.nse_detail([]) == {} and S.nse_detail(None) == {}
    assert S.subscription([{"category": "Total", "noOfSharesOffered": "0.0", "noOfTime": "0.00", "noOfsharesBid": "0.0", "srNo": None}]) is None


def test_the_offer_document_inside_a_zip():
    assert S.nse_zip_pdf(["RHP_SAMPLE/", "RHP_SAMPLE/GID.pdf", "RHP_SAMPLE/RHP.pdf"]) == "RHP_SAMPLE/RHP.pdf"
    assert S.nse_zip_pdf(["RHP_BONFIG/Bonfiglioli Transmissions Limited  - Red Herring Prospectus.pdf", "RHP_BONFIG/BONFIGLIOLI_GID 6-10-2026.pdf"]) \
        == "RHP_BONFIG/Bonfiglioli Transmissions Limited  - Red Herring Prospectus.pdf"
    assert S.nse_zip_pdf(["a/GID.pdf"]) is None


# ---------- BSE and SEBI ----------
def test_bse_lists_only_initial_public_offers():
    got = S.bse_issues(F.file("bse_issues.json"))
    assert [r["name"] for r in got] == ["EAAA India Alternatives Limited", "Core4 Engineers Limited", "BLS POLYMERS LIMITED",
                                        "SFC Environmental Technologies Limited", "Wiscon Industries Limited", "M. K. SONS FINE JEWELS LIMITED"]   # no rights issue, buy-back or debt
    core = got[1]
    assert (core["code"], core["segment"], core["open"], core["close"], core["low"], core["high"], core["status"]) == ("4902", "sme", "2026-10-23", "2026-10-27", 88.0, 93.0, "L")
    perf = S.bse_performance(F.file("bse_listed.json"))
    aye = next(p for p in perf if p["short"] == "AYE")
    assert (aye["issue_price"], aye["listed"], aye["day_close"], aye["latest"]) == (129.0, "2026-02-16", 128.9, 134.55)
    assert aye["url"].startswith("https://www.bseindia.com/")


def test_sebi_lists_and_the_filing_page():
    draft = S.sebi_listing(F.file("sebi_draft_list.html"))
    assert len(draft) == 25 and draft[0] == {"date": "2026-10-21", "kind": "drhp", "company": "Hunger Pangs Limited", "title": "Hunger Pangs Limited – DRHP",
                                             "url": "https://www.sebi.gov.in/filings/public-issues/oct-2026/hunger-pangs-limited-drhp_105347.html"}
    assert {r["kind"] for r in draft} >= {"drhp", "addendum", "udrhp"}
    assert next(r for r in draft if "Tablespace" in r["company"])["company"] == "Tablespace Technologies Limited"
    red = S.sebi_listing(F.file("sebi_red_herring_list.html"))
    assert red[0]["kind"] == "rhp" and red[0]["company"] == "SFC Environmental Technologies Ltd." and red[0]["date"] == "2026-10-22"
    assert S.sebi_entry_pdf(F.file("sebi_entry_sfc_rhp.html")) == "https://www.sebi.gov.in/sebi_data/attachdocs/oct-2026/1792670149542.PDF"
    assert S.sebi_listing("") == [] and S.sebi_entry_pdf("<html></html>") is None


def test_sebi_source_reads_the_list_and_refuses_a_page_that_is_not_one():
    page = F.file("sebi_draft_list.html")
    seen = []

    def handler(req: httpx.Request):
        seen.append(dict(req.url.params))
        return httpx.Response(200, text=page if "smid" in req.url.query.decode() else "<html>maintenance</html>")

    src = S.Sebi(transport=httpx.MockTransport(handler))
    assert len(src.listing("draft")) == 25 and seen[0]["smid"] == "10"
    assert src.listing("red_herring") and seen[1]["smid"] == "11"
    bad = S.Sebi(transport=httpx.MockTransport(lambda req: httpx.Response(200, text="<html>maintenance</html>")))
    with pytest.raises(SourceError):
        bad.listing("draft")


# ---------- the US calendar and EDGAR ----------
def test_us_calendar_month():
    rows = U.ipo_rows(F.file("us_calendar_2026-10.json"))
    stages = [r["stage"] for r in rows]
    assert (stages.count("priced"), stages.count("filed"), stages.count("withdrawn"), stages.count("upcoming")) == (11, 21, 6, 0)
    iam = next(r for r in rows if r["symbol"] == "IAM")
    assert (iam["name"], iam["exchange"], iam["low"], iam["shares"], iam["amount"], iam["priced"]) == ("Iambic Therapeutics, Inc.", "NASDAQ Global Select", 16.0, 9375000, 150000000.0, "2026-10-15")
    gone = next(r for r in rows if r["stage"] == "withdrawn")
    assert gone["withdrawn"] == "2026-10-19" and gone["filed"] == "2021-08-31"
    assert U.ipo_rows({}) == [] and U.ipo_rows({"data": {"upcoming": {"upcomingTable": {"rows": None}}}}) == []


def test_us_upcoming_rows_take_the_calendars_own_column_names():
    """The calendar had no expected offering when its files were saved; its upcoming table names a row's columns as the priced
    table does (symbol, company, exchange, price, shares, amount) with the day it expects the price set."""
    raw = {"data": {"upcoming": {"upcomingTable": {"rows": [
        {"dealID": "1-2", "proposedTickerSymbol": "ABCD", "companyName": "Abcd Corp", "proposedExchange": "NYSE", "proposedSharePrice": "14.00-16.00",
         "sharesOffered": "10,000,000", "expectedPriceDate": "11/05/2026", "dollarValueOfSharesOffered": "$150,000,000"}]}}}}
    [r] = U.ipo_rows(raw)
    assert (r["stage"], r["symbol"], r["low"], r["high"], r["shares"], r["expected"], r["amount"]) == ("upcoming", "ABCD", 14.0, 16.0, 10000000, "2026-11-05", 150000000.0)


def test_edgar_search_and_filing_list():
    hits = S.efts_hits(F.file("edgar_search_iambic.json"))
    assert {h["name"] for h in hits} == {"Iambic Therapeutics, Inc.", "ADARx Pharmaceuticals, Inc."}
    assert next(h for h in hits if h["name"].startswith("Iambic"))["cik"] == "1997038"
    got = S.offering_docs(F.file("edgar_submissions_iambic.json"))
    assert (got["cik"], got["symbol"], got["industry"]) == ("1997038", "IAM", "Biological Products, (No Diagnostic Substances)")
    assert [d["form"] for d in got["docs"]] == ["424B4", "S-1/A", "S-1"]                      # the final prospectus first
    assert got["docs"][0]["url"] == "https://www.sec.gov/Archives/edgar/data/1997038/000119312526422865/iambic_inception_424b4.htm"
    assert got["docs"][0]["link"] == "https://www.sec.gov/Archives/edgar/data/1997038/000119312526422865/0001193125-26-422865-index.htm"


def test_edgar_source_matches_the_company_by_name_and_sends_its_own_user_agent():
    agents = []

    def handler(req: httpx.Request):
        agents.append(req.headers["user-agent"])
        if "efts" in req.url.host:
            return httpx.Response(200, json=F.file("edgar_search_iambic.json"))
        return httpx.Response(200, json=F.file("edgar_submissions_iambic.json"))

    from datetime import date
    ed = S.Edgar(transport=httpx.MockTransport(handler))
    got = ed.docs_for("Iambic Therapeutics, Inc.", date(2026, 10, 25))
    assert got["docs"][0]["form"] == "424B4" and all("StratLab" in a for a in agents)
    assert ed.docs_for("Nobody Corp", date(2026, 10, 25)) is None


# ---------- the offer documents ----------
@pytest.mark.parametrize("doc,promoters,selling,fin", [
    ("bonfig_rhp", ["Sonia Bonfiglioli", "Luciano Bonfiglioli", "Luisa Lusardi", "Bon-Fi S.r.l", "Bonfiglioli S.p.A"],
     [{"name": "Bonfiglioli S.p.A.", "kind": "Promoter"}],
     {"page": 72, "years": ["Dec 2025", "Dec 2024", "Dec 2023"], "revenue": [2013.53, 1854.18, 1687.33], "income": [2023.59, 1861.15, 1701.8], "profit": [237.87, 195.16, 148.49]}),
    ("sfc_rhp", ["Sandeep Sudhakar Asolkar", "Priya Sandeep Asolkar", "Prachiti Sandeep Asolkar", "Saketchandrasingh Pratapsingh Dhandoriya"], [],
     {"page": 94, "years": ["Mar 2026", "Mar 2025", "Mar 2024"], "revenue": [803.63, 697.86, 657.5], "income": [821.27, 726.96, 676.74], "profit": [160.21, 152.01, 144.17]}),
    ("hunger_drhp", ["Ankit Virendra Gupta", "Chirag Narendra Chhajer"],
     [{"name": "Ankit Virendra Gupta", "kind": "Promoter"}, {"name": "Chirag Narendra Chhajer", "kind": "Promoter"}, {"name": "Bbigplas Poly Private Limited", "kind": "Promoter Group"},
      {"name": "Negen Tech Opportunities Angel Fund", "kind": "Investor"}, {"name": "Venture Catalysts Angel Growth Fund", "kind": "Investor"},
      {"name": "L V Angel Fund", "kind": "Investor"}, {"name": "Nisarg Ajaykumar Vakharia", "kind": "Other"}, {"name": "Shweta Sharma", "kind": "Other"},
      {"name": "Mehul Kirit Mehta", "kind": "Other"}],
     {"page": 65, "years": ["Mar 2026", "Mar 2025", "Mar 2024"], "revenue": [155.5, 106.1, 71.92], "income": [156.96, 106.56, 72.17], "profit": [-15.37, -0.51, -5.69]}),
    ("mk_rhp", ["Ramchand Murlidhar Raimalani", "Neelam Ramchand Raimalani", "Kush Ramchand Raimalani"], [{"name": "Ramchand Murlidhar Raimalani", "kind": "Promoter"}],
     {"page": 69, "years": ["Mar 2026", "Mar 2025", "Mar 2024"], "revenue": [538.74, 351.28, 217.32], "income": [538.86, 351.32, 217.39], "profit": [51.8, 23.26, 8.17]}),
])
def test_facts_a_rule_reads_from_four_real_offer_documents(doc, promoters, selling, fin):
    pages = F.pages_of(doc)
    assert D.promoters(pages) == promoters
    assert D.selling_holders(pages) == selling
    got = D.financials(pages)
    assert got["unit"] == "₹ crore" and got["page"] == fin["page"] and got["years"] == fin["years"]
    by = {r["key"]: r["values"] for r in got["rows"]}
    assert by["revenue"] == fin["revenue"] and by["income"] == fin["income"] and by["profit"] == fin["profit"]


def test_objects_in_the_documents_own_words():
    bon = D.objects(F.pages_of("bonfig_rhp"))
    assert bon["page"] == 111 and bon["text"].startswith("The objects of the Offer are to (i) to carry out the Offer for Sale of up to 43,239,042 Equity Shares")
    hun = D.objects(F.pages_of("hunger_drhp"))
    assert hun["text"].startswith("We propose to utilise the Net Proceeds towards the following") and "General corporate purposes" in hun["text"]
    mk = D.objects(F.pages_of("mk_rhp"))
    assert "inventory costs" in mk["text"] and "Repayment" in mk["text"]
    sfc = D.objects(F.pages_of("sfc_rhp"))
    assert sfc["page"] == 168 and sfc["text"].startswith("Our Company proposes to utilise the Net Proceeds from the Fresh Issue")


def test_a_document_the_rules_cannot_read_gives_nothing_rather_than_a_guess():
    assert D.financials([""] * 10) is None and D.promoters([""] * 3) == [] and D.selling_holders(["no table here"]) == [] and D.objects([""] * 3) is None
    odd = ["SUMMARY OF FINANCIAL INFORMATION\n", "Summary profit and loss (₹ in million)\nFor the year ended March 31, 2026 March 31, 2025\nRevenue from operations 10 20\n"]
    assert D.financials(odd) is None                          # two years, not three; the columns are not the three years


def test_the_cover_pdf_is_read_and_a_zip_gives_its_prospectus():
    pdf = (F.DIR / "hunger_drhp_cover.pdf").read_bytes()
    pages = D.pdf_pages(pdf)
    assert len(pages) == 2 and D.promoters(pages) == ["Ankit Virendra Gupta", "Chirag Narendra Chhajer"]
    z = io.BytesIO()
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("RHP_X/GID.pdf", b"%PDF-1.4 general information document")
        f.writestr("RHP_X/RHP.pdf", pdf)
    assert D.pdf_from(z.getvalue()) == pdf and D.pdf_from(pdf) == pdf
    with pytest.raises(SourceError):
        D.pdf_from(b"<html>not a pdf</html>")
    with pytest.raises(SourceError):
        D.pdf_from(b"PK\x03\x04broken")


def test_downloads_stay_on_the_regulators_and_exchanges_own_sites():
    def handler(req: httpx.Request):
        if req.url.path == "/moved":
            return httpx.Response(302, headers={"location": "https://evil.example.com/x.pdf"})
        if req.url.path == "/big":
            return httpx.Response(200, content=b"x" * 5000)
        return httpx.Response(200, content=b"%PDF-1.4 ok", headers={"content-type": "application/pdf"})

    t = httpx.MockTransport(handler)
    assert D.download("https://www.sebi.gov.in/a.pdf", transport=t) == b"%PDF-1.4 ok"
    assert D.download("https://www.sec.gov/Archives/edgar/data/1/x.htm", transport=t, head=4) == b"%PDF"
    with pytest.raises(SourceError, match="isn't on"):
        D.download("https://example.com/a.pdf", transport=t)
    with pytest.raises(SourceError, match="isn't on"):
        D.download("https://www.sebi.gov.in/moved", transport=t)
    with pytest.raises(SourceError, match="too large"):
        D.download("https://www.sebi.gov.in/big", limit=100, transport=t)
    with pytest.raises(SourceError, match="404"):
        D.download("https://www.sebi.gov.in/x", transport=httpx.MockTransport(lambda r: httpx.Response(404)))


# ---------- a US prospectus ----------
@pytest.fixture(scope="module")
def iambic():
    return D.html_text(gzip.open(F.DIR / "iambic_424b4_head.htm.gz").read())


def test_us_offering_terms_from_the_real_final_prospectus(iambic):
    f = D.us_facts(iambic)
    assert (f["company_shares"], f["price"], f["symbol"]) == (9375000, 16.0, "IAM") and "Nasdaq Global Select" in f["listing"]
    assert f["proceeds"].startswith("We estimate that the net proceeds to us from the sale of shares of our common stock in this offering will be approximately $135.0 million")
    assert "selling_shares" not in f                                  # nothing is claimed that the cover doesn't say


def test_us_excerpt_has_the_summary_the_risks_and_the_figures(iambic):
    ex = D.us_excerpt(iambic)
    for part in ("[Cover]", "[Summary of the business]", "[Risks the summary lists]", "[The offering]", "[Summary financial data]"):
        assert part in ex, part
    assert "limited operating history" in ex and "Collaboration revenue" in ex and "9,375,000 shares" in ex


# ---------- the checked AI summary ----------
def test_a_summary_statement_stays_only_with_a_quote_really_in_the_document(iambic):
    ex = D.us_excerpt(iambic)
    good_q = "We have a limited operating history and have incurred significant losses and negative cash flows"
    assert good_q in ex
    parsed = {
        "business": {"text": "An AI-enabled drug discovery company with one program in a Phase 1/1b trial.", "quote": "Our most advanced program, IAM1363, is in an early-stage Phase 1/1b clinical trial"},
        "segments": [{"text": "Collaboration revenue was $9,426 thousand.", "quote": "Collaboration revenue $ 9,426 $ 1,194"},
                     {"text": "Revenue was $40 million.", "quote": "Collaboration revenue $ 9,426 $ 1,194"},                 # a figure the quote doesn't have
                     {"text": "Profit was strong.", "quote": "this sentence is not in the document at all anywhere"},          # an invented quote
                     {"text": "You should buy it now; it is an attractive opportunity.", "quote": good_q}],                   # advice words
        "risks": [{"text": "The company has a limited operating history.", "quote": good_q}],                                   # the rules read these: the AI's are dropped
    }
    got = D.clean_summary(parsed, ex)
    assert got["business"]["text"].startswith("An AI-enabled")
    assert [x["text"] for x in got["segments"]] == ["Collaboration revenue was $9,426 thousand."]
    assert set(got) == {"business", "segments"}                  # (O7) only the business and its segments come from the AI
    assert not ADVICE.search(json.dumps(got))


def test_summarise_asks_the_ai_once_and_checks_its_answer(iambic, monkeypatch):
    ex = D.us_excerpt(iambic)
    asked = []

    def ai(system, text, **kw):
        asked.append((system, text))
        return json.dumps({"business": {"text": "A drug discovery company.", "quote": "Our approach to drug discovery, which integrates AI with automated experimentation, is novel and unproven"},
                           "segments": []})

    monkeypatch.setattr(D, "complete", ai)
    got = D.summarise(ex, (None, None))
    assert got["business"]["text"] == "A drug discovery company." and len(asked) == 1
    assert "using ONLY the passages" in asked[0][0] and "[Cover]" in asked[0][1]
