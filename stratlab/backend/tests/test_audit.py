"""The data audit: each company's numbers, prices, checks and documents compared against their sources, with every
mismatch and gap written down and a failing source never stopping the run."""
import time

from app import audit, deepdive, main, report_card
from tests.test_deepdive import company


def base_for(p, trend=None, docs=None, doc_note=None):
    return lambda sym: {"p": p, "docs": docs or [], "doc_note": doc_note, "filings": None, "trend": trend}


def run(p, monkeypatch, **kw):
    monkeypatch.setattr(deepdive, "stored", lambda s: None)
    monkeypatch.setattr(report_card, "stored", lambda s: None)
    base = base_for(p, kw.pop("trend", None), kw.pop("docs", None), kw.pop("doc_note", None))
    return audit.audit_company("ACME", base, main.deep_view, **kw)


def issues(row, level=None):
    return [f"{i['area']}: {i['detail']}" for i in row["issues"] if level in (None, i["level"])]


def test_a_consistent_company_only_shows_its_gaps(monkeypatch):
    p = company()
    p["ratios"] = {"Market Cap": "520", "Stock P/E": "20", "Current Price": "100"}     # 520 / 26 trailing profit = 20
    p["industry_path"] = ["Capital Goods", "Industrial Machinery"]
    docs = [{"kind": "presentation", "title": "Deck", "at": "2026-08-01", "url": "u1"}]
    row = run(p, monkeypatch, trend={"price": 101.0}, docs=docs, exchange_price=lambda s: 100.5)
    assert issues(row, "mismatch") == [] and issues(row, "error") == []
    assert "Documents: No call transcript filed in the last two years" in issues(row, "gap")
    assert row["name"] == "Acme Industries" and row["seconds"] >= 0


def test_mismatches_against_the_source_are_caught(monkeypatch):
    p = company()
    p["ratios"] = {"Market Cap": "520", "Stock P/E": "35", "Current Price": "100"}
    p["pl"]["rows"]["Sales"][-1] = 260              # trailing revenue far from the last four quarters (204)
    p["pl"]["rows"]["Net Profit"][2] = 140          # profit above revenue in one year
    row = run(p, monkeypatch, trend={"price": 100.0}, exchange_price=lambda s: 92.0)
    found = " | ".join(issues(row, "mismatch"))
    assert "P/E 35.0 on the company page, 20.0" in found
    assert "Trailing revenue 260 cr vs last four quarters 204 cr" in found
    assert "Profit above revenue in Mar 2018" in found or "Profit above revenue" in found
    assert "Last close 100.00 vs 92.00 on the exchange" in found
    assert "Industry: No industry classification" in " ".join(issues(row, "gap"))


def test_a_failing_source_is_an_error_row_not_a_crash(monkeypatch):
    def boom(sym):
        raise main.HTTPException(503, {"code": "source_busy", "message": "The company data source is busy."})
    row = audit.audit_company("ACME", boom, main.deep_view)
    assert issues(row) == ["Company page: The company data source is busy."]
    p = company()
    row = run(p, monkeypatch, trend=None, doc_note="The exchange feed is busy.",
              exchange_price=lambda s: (_ for _ in ()).throw(RuntimeError("timeout")))
    assert "Prices: Exchange price unavailable: timeout" in issues(row, "error")
    assert "Documents: The exchange feed is busy." in issues(row, "error")
    assert "Prices: No daily prices, so no trend or stage" in issues(row, "gap")


def test_unreadable_documents_are_listed(monkeypatch):
    docs = [{"kind": "presentation", "title": "Deck", "at": "2026-08-01", "url": "u1"},
            {"kind": "transcript", "title": "Call", "at": "2026-08-05", "url": "u2"}]

    def read(cands, problems):
        if cands[0]["kind"] == "transcript":
            problems.append("a 900-character letter with no link")
            return []
        return [(cands[0], "text")]
    row = run(company(), monkeypatch, docs=docs, read=read)
    assert "Documents: No readable call transcript: a 900-character letter with no link" in issues(row, "gap")
    assert not any("presentation" in x for x in issues(row, "gap"))


def test_sets_and_the_background_runner(monkeypatch):
    ids = {s["id"] for s in audit.sets()}
    assert {"nifty50", "banknifty", "sectors"} <= ids
    every = audit.symbols_for("sectors")
    assert len(every) == len(set(every)) > 100 and "APOLLOHOSP" in every
    assert audit.symbols_for("nifty50", [" infy", "INFY", "tcs "]) == ["INFY", "TCS"]
    saved = {}
    monkeypatch.setattr(audit.db, "set_setting", lambda k, v: saved.update({k: v}))
    r = audit.Runner()
    check = lambda s: {"symbol": s, "name": s, "seconds": 0.1,
                       "issues": [{"level": "gap", "area": "Documents", "detail": "x"}] if s == "B" else []}
    r.start(["A", "B", "C"], "Test set", check, False)
    for _ in range(100):
        if not r.status()["running"]:
            break
        time.sleep(0.02)
    s = r.status()
    assert s["done"] == 3 and s["summary"]["clean"] == 2 and s["summary"]["by_area"]["Documents"]["gap"] == 1
    assert audit.KEY in saved


def test_admin_audit_endpoint_runs_and_reports(monkeypatch):
    from fastapi.testclient import TestClient
    from app import admin
    monkeypatch.setattr(main, "audit_runner", audit.Runner())
    monkeypatch.setattr(audit.db, "set_setting", lambda k, v: None)
    monkeypatch.setattr(main, "audit_one", lambda s, docs: {"symbol": s, "name": s, "seconds": 0, "issues": []})
    main.app.dependency_overrides[admin.admin_profile] = lambda: {"id": "a", "role": "admin"}
    try:
        c = TestClient(main.app)
        assert c.post("/admin/audit", json={"set": "nope"}).status_code == 400
        r = c.post("/admin/audit", json={"set": "banknifty"}).json()
        assert r["label"] == "NIFTY Bank stocks" and r["total"] == 12
        for _ in range(100):
            s = c.get("/admin/audit").json()
            if not s["running"]:
                break
            time.sleep(0.02)
        assert s["done"] == 12 and s["summary"]["clean"] == 12 and any(x["id"] == "sectors" for x in s["sets"])
    finally:
        main.app.dependency_overrides.clear()
