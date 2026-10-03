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
    p["pl"]["rows"]["OPM %"][3] = 140              # the page's own margin: a gap to look at, not our mistake
    assert "Numbers: The company page shows an operating margin above 100% in" in " ".join(issues(run(p, monkeypatch), "gap"))
    assert audit.check_numbers({"pl": {"cols": ["Mar 2025", "TTM"], "rows": {"Sales": [1, 2]}}},
                               {"years": [], "quarters": [{"sales": 1}] * 4}, {}) == [
        audit._issue("gap", "Numbers", "Only 0 years of annual results")]   # 2 cr vs 4 cr: whole-crore rounding
    assert "Industry: No industry classification" in " ".join(issues(row, "gap"))


def test_a_failing_source_is_an_error_row_not_a_crash(monkeypatch):
    def boom(sym):
        raise main.HTTPException(503, {"code": "source_busy", "message": "The company data source is busy."})
    row = audit.audit_company("ACME", boom, main.deep_view)
    assert issues(row) == ["Company page: The company data source is busy."]
    shell = audit.audit_company("SPAC", lambda s: (_ for _ in ()).throw(main.HTTPException(
        404, {"code": "x", "message": "The SEC has no annual results filed in XBRL for this company."})), main.deep_view)
    assert shell["issues"][0]["level"] == "gap"                          # nothing to show, not something broken
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
    monkeypatch.setattr(main, "audit_one", lambda s, docs, exchange=None, region="IN": {"symbol": s, "name": s, "seconds": 0, "issues": []})
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
        monkeypatch.setattr(main, "audit_one", lambda s, docs, exchange=None, region="IN": {"symbol": s, "name": s, "seconds": 0, "issues": []})
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


def _clean(sym):
    return {"symbol": sym, "name": sym, "seconds": 0.1, "issues": []}


def _recent(*syms, days=0):
    from datetime import date, timedelta
    return [{"symbol": s, "name": s, "listed": (date.today() - timedelta(days=days)).isoformat()} for s in syms]


def test_whole_market_audit_reads_the_exchange_list_and_checks_only_new_listings(monkeypatch):
    from tests import world as W
    w = W.build(monkeypatch)
    try:
        monkeypatch.setattr(main, "audit_one", lambda s, docs, exchange=None, region="IN": {**_clean(s), "issues": [{"level": "gap", "area": "Numbers", "detail": "x"}] if s == "NEWCO" else []})
        h = W.headers("admin-token")
        assert w["client"].get("/admin/audit/market", headers=h).json()["enabled"] is False
        assert main.market_audit.step() is None                                          # off: does nothing
        r = w["client"].post("/admin/audit/market", headers=h, json={"on": True}).json()
        assert r["enabled"] is True
        assert main.market_audit.step() == "NEWCO"                                       # listed today
        assert main.market_audit.step() is None                                          # the rest are long listed: not re-run
        s = w["client"].get("/admin/audit/market", headers=h).json()
        assert s["listed"] == 122 and s["checked"] == 1 and s["due"] == 0                # the bond series is left out
        assert s["new_listings"][0]["symbol"] == "NEWCO" and s["new_listings"][0]["checked"]
        assert [r["symbol"] for r in s["rows"]] == ["NEWCO"]                             # only rows with something to show
        assert w["client"].post("/admin/audit/market", headers=W.headers("pro-token"), json={"on": False}).status_code == 403
    finally:
        w["close"]()


def test_whole_market_audit_survives_a_restart_and_drops_delisted_companies(monkeypatch):
    from tests import world as W
    w = W.build(monkeypatch)
    try:
        listing = _recent("AAA", days=1) + _recent("BBB", days=2) + _recent("CCC", days=3)
        a = audit.MarketAudit(lambda: listing, _clean, pause=0)
        a.set_enabled(True)
        assert [a.step(), a.step()] == ["AAA", "BBB"]                                   # newest listing first
        b = audit.MarketAudit(lambda: listing, _clean, pause=0)                          # the server restarted
        assert b.status()["checked"] == 2 and b.step() == "CCC" and b.step() is None     # carries on, then nothing due
        listing.pop(0)                                                                   # AAA delisted
        b.refresh_list(force=True)
        assert b.status()["checked"] == 2 and "AAA" not in b.rows
        assert audit.MarketAudit(lambda: listing, _clean).status()["listed"] == 2       # and that was saved
        listing.append({"symbol": "OLD", "name": "OLD", "listed": "2001-01-01"})
        b.refresh_list(force=True)
        assert b.status()["due"] == 0 and b.step() is None                               # listed long ago: not checked
        listing.append({"symbol": "FRESH", "name": "FRESH", "listed": None})
        b.refresh_list(force=True)
        assert b.step() == "FRESH"                                                       # no date, but new on the list
    finally:
        w["close"]()


def test_whole_market_audit_keeps_the_last_list_and_gives_way_to_a_hand_started_audit(monkeypatch):
    from tests import world as W
    w = W.build(monkeypatch)
    try:
        calls, busy = [0], [True]

        def listing():
            calls[0] += 1
            if calls[0] > 1:
                raise RuntimeError("refused")
            return _recent("AAA")
        a = audit.MarketAudit(listing, _clean, busy_fn=lambda: busy[0], pause=0)
        a.set_enabled(True)
        assert a.step() is None and calls[0] == 0                                        # an audit by hand is running
        busy[0] = False
        assert a.step() == "AAA"
        a.refresh_list(force=True)
        s = a.status()
        assert s["listed"] == 1 and "refused" in s["list_error"]                         # the last good list stays
    finally:
        w["close"]()


def test_us_companies_are_audited_from_their_sec_filings(monkeypatch):
    from tests import world as W
    w = W.build(monkeypatch)
    try:
        monkeypatch.setattr(deepdive, "stored", lambda s: None)
        monkeypatch.setattr(report_card, "stored", lambda s: None)
        h = W.headers("admin-token")
        sets = w["client"].get("/admin/audit?region=US", headers=h).json()["sets"]
        assert {s["id"] for s in sets} == {"us_mega", "sectors"}
        r = w["client"].post("/admin/audit", headers=h, json={"region": "US", "symbols": ["aapl", "ZZZZ"]}).json()
        assert r["region"] == "US" and r["total"] == 2
        for _ in range(200):
            if not main.audit_runner.status()["running"]:
                break
            time.sleep(0.02)
        rows = {x["symbol"]: x for x in main.audit_runner.status()["rows"]}
        apple = [f"{i['area']}: {i['detail']}" for i in rows["AAPL"]["issues"]]
        assert not any(i["level"] == "error" for i in rows["AAPL"]["issues"]), apple
        assert not any("presentation" in x or "transcript" in x for x in apple)        # US filings, not Indian documents
        assert rows["ZZZZ"]["issues"][0]["level"] == "gap" and "SEC" in rows["ZZZZ"]["issues"][0]["detail"]    # not a filer: not covered
        # the whole US market: the SEC's own list of companies
        w["client"].post("/admin/audit/market", headers=h, json={"region": "US", "on": True})
        assert main.market_audit_us.step() is None                                       # the first list read isn't "new"
        s = w["client"].get("/admin/audit/market?region=US", headers=h).json()
        assert s["listed"] == 2 and s["checked"] == 0 and s["new_listings"] == []
        assert w["client"].get("/admin/audit/market", headers=h).json()["checked"] == 0    # India's is separate
    finally:
        w["close"]()


def test_whole_market_audit_retries_a_company_whose_source_was_down(monkeypatch):
    from datetime import datetime, timedelta, timezone
    from tests import world as W
    w = W.build(monkeypatch)
    try:
        listing = _recent("AAA", days=1) + _recent("BBB", days=2)
        down = {"AAA": True}

        def check(sym):
            if down.get(sym):
                return {**_clean(sym), "issues": [{"level": "error", "area": "Company page", "detail": "source busy"}]}
            return _clean(sym)
        a = audit.MarketAudit(lambda: listing, check, pause=0)
        a.set_enabled(True)
        assert [a.step(), a.step(), a.step()] == ["AAA", "BBB", None]          # AAA failed: not straight away again
        old = (datetime.now(timezone.utc) - timedelta(hours=audit.RETRY_HOURS + 1)).isoformat()
        a.rows["AAA"]["at"] = old                                               # six hours on
        assert a.queue() == ["AAA"] and a.step() == "AAA" and a.rows["AAA"]["tries"] == 2
        a.rows["AAA"]["at"] = old
        assert a.step() == "AAA" and a.rows["AAA"]["tries"] == 3
        a.rows["AAA"]["at"] = old
        assert a.queue() == []                                                  # three tries: left as it is
        assert audit._transient({"issues": [{"level": "mismatch", "area": "Numbers"}]}) is False   # wrong data isn't retried
    finally:
        w["close"]()


def test_india_whole_market_adds_bse_only_companies(monkeypatch):
    import json
    from app import db
    from tests import world as W
    w = W.build(monkeypatch)
    try:
        nse = main.filings_feed.all_equities()
        dual = nse[0]
        bse = [{"instrument_type": "EQ", "segment": "BSE", "tradingsymbol": dual["symbol"], "exchange_token": 500001,
                "instrument_token": 9001, "name": dual["name"]},                                   # on NSE too
               {"instrument_type": "EQ", "segment": "BSE", "tradingsymbol": "TINYCO", "exchange_token": 543210,
                "instrument_token": 9002, "name": "Tiny Co Ltd"}]
        bse += [{"instrument_type": "EQ", "segment": "BSE", "tradingsymbol": f"SMALL{i}", "exchange_token": 530000 + i,
                 "instrument_token": 10000 + i, "name": f"Small {i} Ltd"} for i in range(120)]
        bse += [{"instrument_type": "EQ", "segment": "BSE", "tradingsymbol": "BOND1", "exchange_token": 700001, "instrument_token": 1,
                 "name": "x", "segment_x": 1}]
        bse[-1]["instrument_type"] = "DEBT"
        monkeypatch.setattr(main.kite, "ready", lambda: True)
        monkeypatch.setattr(main.kite, "instruments_of", lambda ex: bse if ex == "BSE" else [])
        listing = main.india_listing()
        syms = [r["symbol"] for r in listing]
        assert "BSE:543210" in syms and "BSE:500001" not in syms and "BSE:700001" not in syms
        assert len([s for s in syms if s.startswith("BSE:")]) == 121
        assert all(r["old"] for r in listing if r["symbol"].startswith("BSE:"))           # first time: not new listings
        # the broker offline: the last good BSE list stands in, so nothing looks delisted
        monkeypatch.setattr(main.kite, "ready", lambda: False)
        assert len([r for r in main.india_listing() if r["symbol"].startswith("BSE:")]) == 121
        # a BSE IPO later is a new listing
        monkeypatch.setattr(main.kite, "ready", lambda: True)
        bse.append({"instrument_type": "EQ", "segment": "BSE", "tradingsymbol": "NEWIPO", "exchange_token": 543999,
                    "instrument_token": 9999, "name": "New IPO Ltd"})
        new = {r["symbol"]: r for r in main.india_listing()}
        assert new["BSE:543999"]["old"] is False and new["BSE:543210"]["old"] is False
        assert json.loads(db.get_setting(main.BSE_ONLY))["543999"]["ts"] == "NEWIPO"
        # one BSE-only company checked: numbers by BSE code, price from BSE's own quote
        page = main.research_hub.screener.company("RELIANCE")
        monkeypatch.setattr(main.research_hub.screener, "company", lambda code: page if code == "543210" else (_ for _ in ()).throw(KeyError(code)))
        monkeypatch.setattr(main.kite, "ltp_key", lambda key: {"BSE:TINYCO": page["ratios"] and 1300.0}.get(key))
        monkeypatch.setattr(main.kite, "history", lambda token, tf, days, **k: [])
        row = main._market_check("BSE:543210")
        assert row["symbol"] == "BSE:543210" and row["name"]
        assert not [i for i in row["issues"] if i["area"] == "Company page"]
        assert audit._shard("BSE:543210") == "audit:market:rows:bse0" or audit._shard("BSE:543210").endswith("rows:bse0")
    finally:
        w["close"]()


def test_one_full_check_of_every_company_then_new_listings_only(monkeypatch):
    from tests import world as W
    w = W.build(monkeypatch)
    try:
        listing = [{"symbol": s, "name": s, "listed": "2001-01-01"} for s in ("AAA", "BBB", "DONE")] + _recent("NEWCO")
        a = audit.MarketAudit(lambda: listing, _clean, pause=0)
        a.set_enabled(True)
        a.refresh_list(force=True)
        a.rows["DONE"] = {**_clean("DONE"), "at": "2026-01-01T00:00:00+00:00"}           # checked before: not repeated
        assert a.queue() == ["NEWCO"]                                                    # nothing started yet
        a.full_once()                                                                    # the first start: the rest
        assert a.status()["full"]["running"] and not a.status()["full"]["everything"]
        assert a.queue() == ["NEWCO", "AAA", "BBB"]                                      # new listings still go first
        assert [a.step(), a.step(), a.step()] == ["NEWCO", "AAA", "BBB"]
        assert a.step() is None
        st = a.status()
        assert not st["full"]["running"] and st["full"]["done_at"] and st["checked"] == 4
        a.full_once()                                                                    # once only: never again by itself
        assert a.queue() == []
        a.start_full()                                                                   # by hand: everything once more
        assert sorted(a.queue()) == ["AAA", "BBB", "DONE", "NEWCO"]
        assert audit.MarketAudit(lambda: listing, _clean).status()["full"]["running"]   # survives a restart
        h = W.headers("admin-token")
        r = w["client"].post("/admin/audit/market", headers=h, json={"full": True}).json()
        assert r["full"]["running"]
    finally:
        w["close"]()


def test_market_sheet_fixes_us(monkeypatch):
    """From the US audit sheet: total revenue includes lease income, foreign filers aren't asked for 10-Qs, US amounts
    aren't in crore, penny-stock rounding isn't a mismatch, and each company is listed once."""
    from app.intel import sec
    def fact(v, start="2024-01-01", end="2024-12-31"):
        return {"start": start, "end": end, "val": v, "form": "10-K", "filed": "2025-02-01"}
    facts = {"us-gaap": {
        "RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"USD": [fact(300)]}},     # a part only
        "Revenues": {"units": {"USD": [fact(1000)]}}}}                                              # the total
    assert sec.revenue(facts, "annual") == {"2024-12-31": 1000.0}
    docs = [{"kind": "annual_report", "form": "20-F"}]
    view = {"region": "US", "documents": docs, "checklist": {"checks": []}, "valuation": {"metrics": []}}
    assert not any("10-Q" in i["detail"] for i in audit.check_view(view))
    view["documents"] = [{"kind": "annual_report", "form": "10-K"}]
    assert any("10-Q" in i["detail"] for i in audit.check_view(view))
    assert audit.check_prices({"price": 0.04}, {"price": 0.05}, None) == []                       # a cent on a penny stock
    p = {"region": "US", "pl": {"cols": ["Dec 2024", "TTM"], "rows": {"Sales": [100, 300]}}}
    found = audit.check_numbers(p, {"years": [], "quarters": [{"sales": 50}] * 4}, {})
    assert any("$m300 vs last four quarters $m200" in i["detail"] for i in found)
    from tests import world as W
    w = W.build(monkeypatch)
    try:
        monkeypatch.setattr(main.sec_feed, "tickers", lambda: {"AHL": {"cik": 1, "name": "Aspen"}, "AHL-PD": {"cik": 1, "name": "Aspen"},
                                                               "ACONW": {"cik": 2, "name": "Aclarion"}, "ACON": {"cik": 2, "name": "Aclarion"}})
        assert [c["symbol"] for c in main._sec_companies()] == ["AHL", "ACONW"]
    finally:
        w["close"]()


def test_stored_findings_are_read_with_todays_rules():
    old = [audit._issue("mismatch", "Numbers", "Operating margin above 100% in Mar 2017"),
           audit._issue("mismatch", "Numbers", "Trailing revenue 2 cr vs last four quarters 2 cr"),
           audit._issue("mismatch", "Numbers", "Trailing revenue 260 cr vs last four quarters 204 cr"),
           audit._issue("mismatch", "Prices", "Last close 0.04 vs 0.04 on the company page"),
           audit._issue("error", "Company page", "the fundamentals source has nothing for that.")]
    now = [audit.restate(i) for i in old]
    assert now[0]["level"] == "gap" and "company page shows" in now[0]["detail"]
    assert now[1] is None and now[2] == old[2] and now[3] is None and now[4]["level"] == "gap"
    us = audit.restate(audit._issue("mismatch", "Numbers", "Trailing revenue 900 cr vs last four quarters 700 cr"), us=True)
    assert us["detail"] == "Trailing revenue $m900 vs last four quarters $m700"
