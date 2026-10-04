"""Management report card: periods parsed, targets pulled from calls cleaned (sourced, forward-looking only), checked
against the reported numbers, repeats counted once, and the endpoint gated, stored and limited like the other reads."""
import json
from datetime import date

from app import deepdive, report_card as rc
from tests.test_deepdive import FakeDocs, api, company  # noqa: F401  (api is a fixture)


def test_periods():
    assert rc.parse_period("FY26") == {"kind": "FY", "fy": 2026}
    assert rc.parse_period("FY 2025-26") == {"kind": "FY", "fy": 2026}
    assert rc.parse_period("fy'27") == {"kind": "FY", "fy": 2027}
    assert rc.parse_period("2025-26") == {"kind": "FY", "fy": 2026}
    assert rc.parse_period("Q2 FY26") == rc.parse_period("2QFY26") == rc.parse_period("Q2FY2026") == {"kind": "Q", "fy": 2026, "q": 2}
    assert rc.parse_period("next year") is None and rc.parse_period(None) is None
    assert rc.period_end({"kind": "Q", "fy": 2026, "q": 2}) == date(2025, 9, 30)
    assert rc.period_end({"kind": "Q", "fy": 2026, "q": 4}) == date(2026, 3, 31)
    assert rc._table_label({"kind": "Q", "fy": 2026, "q": 3}) == "Dec 2025" and rc._table_label({"kind": "FY", "fy": 2025}) == "Mar 2025"


CALLS = {"S1": {"title": "Q4 FY24 call transcript", "at": "2024-05-10T10:00", "url": "u-old", "kind": "transcript"},
         "S2": {"title": "Q2 FY25 call transcript", "at": "2024-11-10T10:00", "url": "u-mid", "kind": "transcript"}}


def g(metric, low, period, source="S1", high=None, what="target"):
    return {"metric": metric, "low": low, "high": high, "period": period, "what": what, "quote": "we expect", "source": source}


AI = {"guidance": [g("revenue_growth", 15, "FY25", high=18), g("margin", 21, "FY25"), g("capex", "25", "FY25"),
                   g("profit growth", 30, "FY25"), g("revenue_growth", 20, "FY27"), g("other", None, None, what="Start the new plant"),
                   g("revenue_growth", 12, "FY24"),                  # FY24 had ended when this was said: a result, not a promise
                   g("margin", 20, "FY25", source="S9"),             # not one of the calls read
                   g("revenue_growth", 15, "FY25", source="S2", high=18),   # repeated: counted once
                   g("margin", 19.5, "FY25", source="s2"),           # lowered later: shown as a revision
                   g("margin", None, "FY26", what="better margins")]}  # no figure: kept as a qualitative promise


def test_clean_keeps_sourced_forward_targets():
    out = rc.clean(AI, CALLS)              # no texts given: quotes aren't checked here (see the next tests)
    assert len(out) == 9
    assert not any(x["period"] == "FY24" for x in out) and all(x["source"]["url"] in ("u-old", "u-mid") for x in out)
    capex = next(x for x in out if x["metric"] == "capex")
    assert capex["low"] == 25.0 and capex["period"] == "FY25"
    assert next(x for x in out if x["what"] == "better margins")["metric"] == "other"
    assert any(x["metric"] == "profit_growth" for x in out)


def test_checked_against_the_numbers():
    nums = deepdive.numbers(company())    # FY25: sales 200 (+17.6%), profit 25 (+25%), OPM 19, capex 23
    card = rc.view({"guidance": rc.clean(AI, CALLS), "read": [], "at": "x"}, nums, today=date(2026, 9, 30))
    by = {(r["metric"], r["period"]): r for r in card["rows"]}
    assert by[("revenue_growth", "FY25")]["result"] == "met" and by[("revenue_growth", "FY25")]["actual"] == 17.6
    assert by[("margin", "FY25")]["result"] == "missed" and by[("margin", "FY25")]["revised"]["low"] == 19.5
    assert by[("capex", "FY25")]["result"] == "met" and by[("capex", "FY25")]["unit"] == "crore"     # 23 vs 25: within 10%
    assert by[("profit_growth", "FY25")]["result"] == "missed"
    assert by[("revenue_growth", "FY27")]["result"] == "pending"
    assert sum(r["metric"] == "revenue_growth" and r["period"] == "FY25" for r in card["rows"]) == 1
    assert (card["met"], card["missed"], card["pending"], card["unchecked"], card["score"]) == (2, 2, 1, 2, 50)


def test_quarterly_targets_use_the_quarter_a_year_earlier():
    nums = {"years": [], "quarters": [{"quarter": q, "sales": s, "profit": 5, "opm": o} for q, s, o in
                                      [("Jun 2024", 40, 18), ("Sep 2024", 45, 19), ("Dec 2024", 50, 19), ("Mar 2025", 52, 20),
                                       ("Jun 2025", 48, 19), ("Sep 2025", 54, 20)]]}
    row = rc.check({"metric": "revenue_growth", "low": 18.0, "high": None, "period": "Q2 FY26"}, nums, date(2026, 1, 1))
    assert row["actual"] == 20.0 and row["result"] == "met"
    assert rc.check({"metric": "margin", "low": 21.0, "high": None, "period": "Q2 FY26"}, nums)["result"] == "missed"
    assert rc.check({"metric": "revenue_growth", "low": 18.0, "high": None, "period": "Q3 FY26"}, nums, date(2026, 1, 20))["result"] == "pending"


def test_calls_spread_over_two_years():
    docs = [{"kind": "transcript", "at": f"2026-{m:02d}-01", "title": str(m), "url": str(m)} for m in range(1, 10)]
    docs.append({"kind": "presentation", "at": "2026-09-05", "title": "p", "url": "p"})
    picked = rc.pick_calls(docs)
    assert len(picked) == rc.MAX_CALLS and picked[0]["at"] == "2026-09-01" and picked[-1]["at"] == "2026-01-01"


def test_endpoint_reads_calls_once_and_counts_toward_the_limit(api, monkeypatch):  # noqa: F811
    c, who, _calls, usage = api
    seen = []

    def complete(system, text, **kw):
        seen.append(text)
        return json.dumps({"guidance": [{"metric": "margin", "low": 20, "period": "FY27", "what": "20% margin", "quote": "capex of Rs 500 crore", "source": "S1"}]})
    monkeypatch.setattr(rc, "complete", complete)
    who["p"] = {"id": "u1", "plan": "pro", "_plan": "pro"}
    assert c.get("/research/deep/ACME").json()["card"] is None
    v = c.post("/research/deep/ACME/card").json()
    row = v["card"]["rows"][0]
    assert row["result"] == "pending" and row["source"]["title"] == "Q1 FY27 call transcript" and usage.count("research_ai") == 1
    assert v["card"]["problems"] and not v["card_stale"] and v["calls"] == 2
    c.post("/research/deep/ACME/card")                       # fresh: no new AI call
    assert len(seen) == 1 and usage.count("research_ai") == 1
    c.post("/research/deep/ACME/card?refresh=true")
    assert c.post("/research/deep/ACME/card?refresh=true").status_code == 429


def test_relative_periods_resolve_from_the_call_date():
    said = date(2025, 8, 10)                                    # in FY26
    assert rc.fy_of(said) == 2026 and rc.fy_of(date(2026, 2, 1)) == 2026 and rc.fy_of(date(2026, 4, 1)) == 2027
    assert rc.parse_period("next year", said) == {"kind": "FY", "fy": 2027}
    assert rc.parse_period("this fiscal", said) == {"kind": "FY", "fy": 2026}
    assert rc.parse_period("current financial year", said) == {"kind": "FY", "fy": 2026}
    assert rc.parse_period("Q3 FY26", said) == {"kind": "Q", "fy": 2026, "q": 3}
    assert rc.parse_period("next year") is None                 # without a date it can't be pinned down
    out = rc.clean({"guidance": [g("revenue_growth", 15, None, what="15% growth next year")]},
                   {"S1": {"title": "Call", "at": "2025-08-10T10:00", "url": "u"}})
    assert out[0]["period"] == "FY27"


def test_made_up_quotes_and_analyst_numbers_are_dropped():
    text = ("Analyst: Would margins reach 25%? CFO: We are confident EBITDA margin will be about 21% for the full year. "
            "We plan capex of Rs 1,200 crore in FY27 for new beds.")
    items = {"guidance": [
        {"metric": "margin", "low": 21, "period": "FY26", "what": "21% margin", "quote": "EBITDA margin will be about 21% for the full year", "source": "S1"},
        {"metric": "margin", "low": 25, "period": "FY26", "what": "25% margin", "quote": "margins will reach 25% by the end of the year", "source": "S1"},
        {"metric": "capex", "low": 1200, "period": "FY27", "what": "Capex", "quote": "capex of Rs 1,200 crore in FY27", "source": "S1"}]}
    labels = {"S1": {"title": "Call", "at": "2025-08-10T10:00", "url": "u"}}
    out = rc.clean(items, labels, {"S1": text})
    assert [x["low"] for x in out] == [21.0, 1200.0]          # the 25% "quote" isn't in the call


def test_each_call_is_read_on_its_own_and_a_cut_off_reply_keeps_what_is_complete(monkeypatch):
    calls = [{"kind": "transcript", "at": f"2025-{m:02d}-10T10:00", "title": f"Call {m}", "url": f"u{m}"} for m in (5, 8, 11)]
    texts = {"u5": "We expect revenue growth of 15% in FY26.", "u8": "EBITDA margin should be 22% in FY27.", "u11": "x"}
    seen = []

    def complete(system, text, **kw):
        seen.append(text)
        if "Call 8" in text:      # cut off after the first complete item
            return '{"guidance": [{"metric": "margin", "low": 22, "period": "FY27", "what": "22% margin", "quote": "EBITDA margin should be 22% in FY27", "source": "S1"}, {"metric": "capex", "lo'
        if "Call 11" in text:
            raise rc.AIError("busy")
        return json.dumps({"guidance": [{"metric": "revenue_growth", "low": 15, "period": "FY26", "what": "15% growth",
                                         "quote": "revenue growth of 15% in FY26", "source": "S1"}]})
    monkeypatch.setattr(rc, "complete", complete)
    out = rc.read("ACME", "Acme", calls, FakeDocs(texts), (None, None))
    assert len(seen) == 3 and all(t.count("[S1]") == 1 for t in seen) and "CALL DATE: 2025-08-10 (that is FY26)" in seen[1]
    assert sorted(x["low"] for x in out["guidance"]) == [15.0, 22.0]
    assert [r["title"] for r in out["read"]] == ["Call 11", "Call 8", "Call 5"][1:] and any("Call 11" in p for p in out["problems"])
    monkeypatch.setattr(rc, "complete", lambda *a, **k: (_ for _ in ()).throw(rc.AIError("down")))
    import pytest
    with pytest.raises(rc.AIError):
        rc.read("ACME", "Acme", calls, FakeDocs(texts), (None, None))


def test_targets_are_settled_from_what_the_company_said_later(monkeypatch):
    from datetime import date
    g0 = {"metric": "other", "low": 85, "high": 90, "period": "FY26", "what": "Loan-to-deposit ratio 85-90%", "unit": "%",
          "quote": "", "said_at": "2025-01-20", "source": {}}
    out = {"problems": [], "guidance": [
        dict(g0),
        {"metric": "other", "low": 60, "high": None, "period": "FY26", "what": "Retail mix about 60%", "unit": "%",
         "quote": "", "said_at": "2025-01-20", "source": {}},
        {"metric": "other", "low": 40, "high": None, "period": "Q3 FY26", "what": "CASA ratio 40%", "unit": "%",
         "quote": "", "said_at": "2025-01-20", "source": {}},
        {"metric": "other", "low": 40, "high": None, "period": "FY28", "what": "CASA ratio 40%", "unit": "%",
         "quote": "", "said_at": "2025-01-20", "source": {}}]}
    feb = {"title": "Q3 FY26 call", "at": "2026-02-10T10:00", "url": "https://x/q3.pdf", "kind": "transcript"}
    may = {"title": "Q4 FY26 call", "at": "2026-05-20T10:00", "url": "https://x/q4.pdf", "kind": "transcript"}
    pairs = [(feb, "Our loan to deposit ratio is at 95% this quarter and we will bring it down. CASA ratio was 38% in the quarter. " * 30),
             (may, "For the full year FY26 the loan to deposit ratio came in at 88% as we guided. Retail mix ended the year at 55%. " * 30)]
    seen = {}

    def fake(system, text, **k):
        seen["text"] = text
        return json.dumps({"results": [
            {"id": "T1", "actual": 95, "met": False, "quote": "Our loan to deposit ratio is at 95% this quarter", "source": "S1"},  # before FY26 ended
            {"id": "T1", "actual": 88, "met": True, "quote": "the loan to deposit ratio came in at 88% as we guided", "source": "S2"},
            {"id": "T2", "actual": 61, "met": True, "quote": "Retail mix ended the year at 55%", "source": "S2"},     # number not in the quote
            {"id": "T3", "actual": 38, "met": False, "quote": "CASA ratio was 38% in the quarter", "source": "S1"},
            {"id": "T3", "actual": 41, "met": True, "quote": "CASA ratio of 41% achieved", "source": "S2"}]})          # not in the document
    monkeypatch.setattr(rc, "complete", fake)
    rc.settle(out, pairs, (None, None), "Bank", 3, today=date(2026, 10, 3))
    g = out["guidance"]
    assert g[0]["doc_check"]["actual"] == 88 and g[0]["doc_check"]["met"] and g[0]["doc_check"]["source"]["title"] == "Q4 FY26 call"
    assert "doc_check" not in g[1]                     # the quoted number isn't the one claimed
    assert g[2]["doc_check"]["actual"] == 38 and g[2]["doc_check"]["met"] is False
    assert "doc_check" not in g[3] and "FY28" not in seen["text"]          # FY28 hasn't ended: not even asked
    row = rc.check(g[0], {"years": [], "quarters": []}, date(2026, 10, 3))
    assert row["result"] == "met" and row["actual"] == 88 and row["settled_by"]["quote"].startswith("the loan")
    assert rc.check(g[2], {"years": [], "quarters": []}, date(2026, 10, 3))["result"] == "missed"
    assert rc.calls_for(1) == 4 and rc.calls_for(2) == 6 and rc.calls_for(5) == 12
