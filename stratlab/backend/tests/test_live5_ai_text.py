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


def test_the_history_credits_a_re_run_only_when_it_went_through():
    """LIVE5-011: "Re-ran the job at 6 Nov 11:44 AM IST — fixed" when that re-run had failed ("No route /admin/ipos/refresh")."""
    from datetime import datetime, timedelta, timezone
    from app import autofix
    t0 = datetime(2026, 11, 6, 6, 0, tzinfo=timezone.utc)
    chk = lambda problem: autofix.Check(id="job:ipo", name="IPOs", problem=problem, fix=lambda: None, fix_text="re-ran the job")   # noqa: E731
    run = lambda c: (False, "No route /admin/ipos/refresh")                                                                       # noqa: E731
    st = autofix.sweep([chk("IPOs: the exchange's page failed")], t0, autofix._empty(), lambda s, t: True, run)
    st = autofix.sweep([chk("IPOs: the exchange's page failed")], t0 + timedelta(minutes=16), st, lambda s, t: True, run)
    assert st["open"]["job:ipo"]["tried"][0]["error"]
    st = autofix.sweep([chk(None)], t0 + timedelta(minutes=40), st, lambda s, t: True, run)
    text = st["history"][0]["text"]
    assert st["history"][0]["event"] == "fixed" and "re-ran the job at" not in text and "had failed" in text
    assert autofix.fixed_text("re-ran the job", [{"at": "2026-11-06T06:16:00+00:00"}]).startswith("re-ran the job at ")
    assert autofix.fixed_text("re-ran the job", []) == "the check passes now: cleared by itself"


def test_a_company_website_is_its_own_home_page_never_a_rating_pdf_or_an_encyclopaedia():
    """LIVE5-011: RELIANCE's website field held a rating agency's PDF, TCS's an old annual report, INFY's a CRISIL page."""
    from app.intel.screener import own_site
    assert own_site("https://www.ril.com/") == "https://www.ril.com/"
    assert own_site("https://www.tcs.com/investor-relations") == "https://www.tcs.com/"
    assert own_site("https://www.tcs.com/content/dam/annual-report-2019-20.pdf") is None
    assert own_site("https://www.crisil.com/mnt/winshare/Ratings/RatingList/RatingDocs/Infosys.html") is None
    assert own_site("https://www.careratings.com/upload/CompanyFiles/PR/Titan.pdf") is None
    assert own_site("https://en.wikipedia.org/wiki/Reliance_Industries") is None
    assert own_site("https://www.icra.in/Rationale/ShowRationaleReport?Id=1") is None
    assert own_site("mailto:ir@ril.com") is None and own_site("") is None and own_site(None) is None


def test_one_rounding_for_the_compounded_rates_of_a_row():
    """LIVE4-013 partial: "3Y CAGR +7.1% · 5Y +7.8% · 10Y CAGR +7%" on HAL's page."""
    from app.intel.company import _item, same_rounding
    row = same_rounding([_item("Latest YoY", 16.14, "%±"), _item("3Y CAGR", 7.1, "%±"), _item("5Y CAGR", 7.8, "%±"), _item("10Y CAGR", "7%", "%±")])
    assert [i.get("dp") for i in row] == [None, 0, 0, 0]
    keep = same_rounding([_item("3Y CAGR", 7.1, "%±"), _item("5Y CAGR", 7.8, "%±")])
    assert all(i.get("dp") is None for i in keep)


def test_a_block_deal_party_is_written_out_in_full_and_title_case():
    """LIVE4-021 partial: "The MTBJ Ltd. as TRST for Govrnmnt Pension Invstmnt Fund"."""
    from app.deals import tidy_party
    want = "The Master Trust Bank of Japan Ltd. as Trust for Government Pension Investment Fund"
    assert tidy_party("THE MTBJ LTD. AS TRST FOR GOVRNMNT PENSION INVSTMNT FUND MUTB400045794") == want
    assert tidy_party("The MTBJ Ltd. as TRST for Govrnmnt Pension Invstmnt Fund") == want
    assert tidy_party("SOCIETE GENERALE") == "Societe Generale"


def test_the_ipo_posts_table_lists_every_issue_and_pages_them_on_a_phone():
    """LIVE4-019 partial: "the latest 50 of 85 are shown"."""
    from app import blog
    rows = [[f"Issue {i}", "1 Nov", "₹100", "+1%", "+2%", "3x"] for i in range(85)]
    html = blog.blocks_html([{"t": "table", "caption": "IPO listing day", "head": ["Issue", "Listed", "Issue price", "Open", "Close", "Subscribed"],
                              "rows": rows, "align": "lrrrrr", "page": 20}])
    assert html.count("<tr>") == 86                                   # every issue (and the head)
    assert '<tbody class="pg-more">' in html and "Show all 85 rows" in html and 'class="pg-all"' in html
    first = html.split('<tbody class="pg-more">')[0]
    assert first.count("<tr>") == 21
    plain = blog.blocks_html([{"t": "table", "head": ["A", "B"], "rows": [["x", "1"]] * 3, "page": 20}])
    assert "pg-more" not in plain and "Show all" not in plain
    from app import blog_research
    assert blog_research.IPO_ROWS_SHOWN >= 150
