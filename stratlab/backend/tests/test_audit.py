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
    p["pl"]["rows"]["Net Profit"][2] = 140          # profit above revenue in one year (other income): not flagged
    row = run(p, monkeypatch, trend={"price": 100.0}, exchange_price=lambda s: 92.0)
    found = " | ".join(issues(row, "mismatch"))
    assert "Trailing revenue 260 cr vs last four quarters 204 cr" in found
    assert "Last close 100.00 vs 92.00 on the exchange" in found
    assert "Profit above revenue" not in found and "P/E" not in found      # real data, and a P/E gap the page explains
    nums = main.deep_view("ACME", base_for(p)("ACME"))["numbers"]
    assert any("P/E is based on" in n for n in nums["notes"])
    p["pl"]["rows"]["OPM %"][3] = 140
    assert "Numbers: Operating margin above 100% in" in " ".join(issues(run(p, monkeypatch), "mismatch"))
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

    def read(cands, problems, p):
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
    monkeypatch.setattr(main, "audit_one", lambda s, docs, exchange=None: {"symbol": s, "name": s, "seconds": 0, "issues": []})
    main.app.dependency_overrides[admin.admin_profile] = lambda: {"id": "a", "role": "admin"}
    try:
        c = TestClient(main.app)
        assert c.post("/admin/audit", json={"set": "nope"}).status_code == 400
        r = c.post("/admin/audit", json={"set": "banknifty"}).json()
        assert r["label"] == "NIFTY Bank stocks" and r["total"] == 12
        for _ in range(100):                      # wait on the runner itself: polling the API would spend the rate limit
            if not main.audit_runner.status()["running"]:
                break
            time.sleep(0.02)
        s = c.get("/admin/audit").json()
        assert s["done"] == 12 and s["summary"]["clean"] == 12 and any(x["id"] == "sectors" for x in s["sets"])
    finally:
        main.app.dependency_overrides.pop(admin.admin_profile, None)


def test_breaker_stops_after_repeated_refusals():
    calls = []

    def refuse(sym):
        calls.append(sym)
        raise RuntimeError("refused (403)")
    b = audit.Breaker(refuse, limit=2)
    rows = [audit.audit_company(s, lambda sym: (_ for _ in ()).throw(RuntimeError("x")), main.deep_view) for s in "AB"]
    assert rows                                   # a dead company source is one error row each, and the run goes on
    for s in "ABCD":
        try:
            b(s)
        except audit.Skipped:
            pass
        except RuntimeError:
            pass
    assert calls == ["A", "B"]


def test_loss_makers_get_a_reason_not_a_blank():
    from app import industry
    p = company()
    p["pl"]["rows"]["Net Profit"][-1] = -12
    v = industry.valuation(p, {"pe": None, "market_cap_cr": 500}, "general", "general")
    assert v["value"] is None and "made a loss over the last 12 months" in v["why"]
    p["balance"]["rows"]["Reserves"] = [80, 90, 100, 110, 120, 130]
    p["balance"]["rows"]["Equity Capital"] = [20] * 6
    assert industry.valuation(p, {"pb": None, "market_cap_cr": 450}, "lender", "lender")["value"] == 3.0   # 450 / 150


def test_exchange_quote_is_asked_like_its_own_page():
    import httpx
    from app.intel.filings import NSEFilings
    seen = []

    def handler(r):
        seen.append((r.url.path, r.headers.get("referer")))
        if r.url.path == "/api/quote-equity":
            if "get-quotes/equity?symbol=M%26M" not in (r.headers.get("referer") or ""):
                return httpx.Response(403)
            return httpx.Response(200, json={"priceInfo": {"lastPrice": 3120.5}})
        return httpx.Response(200, text="<html></html>")
    assert NSEFilings(transport=httpx.MockTransport(handler)).last_price("M&M") == 3120.5


def test_a_whole_index_comes_from_the_exchanges_list(monkeypatch):
    from tests import world as W
    w = W.build(monkeypatch)
    try:
        monkeypatch.setattr(main, "audit_one", lambda s, docs, exchange=None: {"symbol": s, "name": s, "seconds": 0, "issues": []})
        sets = {s["id"]: s for s in w["client"].get("/admin/audit", headers=W.headers("admin-token")).json()["sets"]}
        assert {"nifty500", "niftynext50", "midcap150", "smallcap250"} <= sets.keys()
        r = w["client"].post("/admin/audit", headers=W.headers("admin-token"), json={"set": "nifty500"}).json()
        assert r["total"] == 5 and "NIFTY 500" in r["label"]                         # the index row itself is left out
        for _ in range(100):
            if not main.audit_runner.status()["running"]:
                break
            time.sleep(0.02)
        w["faults"]["exchange"].mode = "down"
        w["filings"] = main.filings_feed
        main.filings_feed.cache.clear()
        r = w["client"].post("/admin/audit", headers=W.headers("admin-token"), json={"set": "midcap150"})
        assert r.status_code == 503 and r.json()["detail"]["code"] == "index_unavailable"
        assert audit.symbols_for("sectors") and len(audit.symbols_for("x", ["a"] * 700)) == 1
    finally:
        w["close"]()
