"""Release 42, lane m1: the company AI read on its results day (LIVE7B-003), its small faults (LIVE7B-004), and a headline with no
source (LIVE7B-005)."""
from datetime import date

from app.intel import ai as A
from app.intel import company, grounding, key_facts


def _page(news=None, cal=None):
    return {"region": "IN", "quarters": {"cols": ["Jun 2026"]}, "news": news or [],
            "results_calendar": cal or {"next": {"date": "2026-11-12"}, "last": {"date": "2026-08-13"}}}


def test_results_filed_on_their_day_are_never_scheduled():
    today = date(2026, 11, 12)
    # nothing says they are out: still upcoming (today)
    assert A.results_status(_page(), today)["status"] == "upcoming"
    # the calendar found the filing
    got = A.results_status(_page(cal={"next": {"date": "2026-11-12", "out": {"title": "Results"}}}), today)
    assert got["status"] == "filed_not_read" and got["filed_on"] == "2026-11-12" and "next_results_date" not in got
    assert "not in these facts yet" in got["note"]
    # the day's headlines report them
    news = [{"headline": "Page Industries shares hit lower circuit after Q2 results", "at": "2026-11-12T10:05:00+05:30"}]
    assert A.results_status(_page(news=news), today)["status"] == "filed_not_read"
    # a headline about results ahead, or one from another day, isn't it
    ahead = [{"headline": "Page Industries Q2 results scheduled for today", "at": "2026-11-12T08:00:00+05:30"},
             {"headline": "Page Industries Q1 results: net profit up 10%", "at": "2026-08-13T15:00:00+05:30"}]
    assert A.results_status(_page(news=ahead), today)["status"] == "upcoming"


def test_a_kept_read_drops_its_scheduled_results_line_once_they_are_filed():
    read = {"watch": ["What to watch: Q2 FY2027 results are scheduled for Thu, 12 Nov.", "Ex-dividend date on 20 Nov."]}
    cal = {"next": {"date": "2026-11-12", "out": {"title": "Results"}}}
    got = A.filed_watch(read, cal, date(2026, 11, 12))
    assert got["watch"] == ["Results filed on 2026-11-12: their figures are not in this read yet.", "Ex-dividend date on 20 Nov."]
    assert A.filed_watch(read, {"next": {"date": "2026-11-12"}}, date(2026, 11, 12)) == read          # not found filed: as it was
    assert A.filed_watch(read, cal, date(2026, 11, 11)) == read                                       # before its day


def test_a_signed_figure_has_a_minus_sign_and_a_lender_has_no_sales():
    assert key_facts._pct(-22.04, True) == "−22.0%" and key_facts._pct(5.0, True) == "+5.0%" and key_facts._pct(-3.0) == "−3.0%"
    row = key_facts.growth({}, {"bank": True, "growth": {"sales_cagr_3y": 26.9}})
    assert [i["label"] for i in row["items"]] == ["Revenue, 3 years"]
    assert key_facts.growth({}, {"growth": {"sales_cagr_3y": 26.9}})["items"][0]["label"] == "Sales, 3 years"
    # a read kept from before: its rows put right as it goes out
    kept = {"lender": True, "facts": [{"id": "growth", "label": "Growth", "items": [{"label": "Sales, 3 years", "text": "26.9% a year"}]},
                                      {"id": "price", "label": "Price trend", "items": [{"label": "1-year price change", "text": "-22%"}]}],
            "bull": [], "bear": [], "watch": [], "ideas": [], "summary": "", "valuation_note": "", "position": ""}
    out = A.clean_company(kept)
    assert out["facts"][0]["items"][0]["label"] == "Revenue, 3 years" and out["facts"][1]["items"][0]["text"] == "−22%"
    assert key_facts.minus("Debt-to-equity 0.4, 3-year") == "Debt-to-equity 0.4, 3-year"          # hyphens in words stay


def test_a_one_off_note_is_said_once_in_the_read():
    facts = {"base_effect_items": [{"quarter": "Jun 2025", "text": "Tax rate 12% in Jun 2025 against about 25% usually: profit growth against it is moved by it"}]}
    seen = set()
    a = grounding.base_noted("Net profit grew 20% over Jun 2025.", facts, seen)
    b = grounding.base_noted("Sales rose 8% over Jun 2025.", facts, seen)
    assert "(Tax rate 12% in Jun 2025 against about 25% usually)" in a and b == "Sales rose 8% over Jun 2025."
    # a kept read with the note on two lines
    lines = ["Net profit grew 20% over Jun 2025 (Tax rate 12% in Jun 2025 against about 25% usually).",
             "Sales rose 8% over Jun 2025 (Tax rate 12% in Jun 2025 against about 25% usually)."]
    assert grounding.notes_once(lines) == [lines[0], "Sales rose 8% over Jun 2025."]


def test_a_headline_with_no_source_has_none():
    assert company.news_source("null") is None and company.news_source(" None ") is None and company.news_source("") is None
    assert company.news_source("Reuters") == "Reuters"
    got = company.grouped([{"headline": "Rapid7 names a new chief", "source": "null", "at": "2026-11-05T10:00:00+00:00"}])
    assert got[0]["source"] is None
