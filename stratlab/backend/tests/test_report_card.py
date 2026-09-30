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
    out = rc.clean(AI, CALLS)
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
        return json.dumps({"guidance": [{"metric": "margin", "low": 20, "period": "FY27", "what": "20% margin", "quote": "about 20%", "source": "S1"}]})
    monkeypatch.setattr(rc, "complete", complete)
    who["p"] = {"id": "u1", "plan": "pro", "_plan": "pro"}
    assert c.get("/research/deep/ACME").json()["card"] is None
    v = c.post("/research/deep/ACME/card").json()
    row = v["card"]["rows"][0]
    assert row["result"] == "pending" and row["source"]["title"] == "Q1 FY27 call transcript" and usage == ["research_ai"]
    assert v["card"]["problems"] and not v["card_stale"] and v["calls"] == 2
    c.post("/research/deep/ACME/card")                       # fresh: no new AI call
    assert len(seen) == 1 and len(usage) == 1
    c.post("/research/deep/ACME/card?refresh=true")
    assert c.post("/research/deep/ACME/card?refresh=true").status_code == 429
