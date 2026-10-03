"""Companies listed only on BSE work like NSE ones: search, company page, chart, quotes, filings and red flags,
the deep dive's documents, price trend, backtests and the audit."""
from app import main, platform_check
from app.intel import filings


def test_bse_only_stocks_join_the_instrument_list_but_dual_listings_stay_nse(monkeypatch):
    from tests import world as W
    w = W.build(monkeypatch)
    try:
        k = main.kite
        tiny = k.equity("TINYCO")
        assert tiny["exchange"] == "BSE" and tiny["bse_code"] == "543210" and tiny["type"] == "EQ"
        assert k.equity("543210")["token"] == tiny["token"]                      # by BSE code too
        assert k.equity("RELIANCE")["exchange"] == "NSE"                          # on both: the NSE one
        assert not [r for r in k._inst if r["exchange"] == "BSE" and r["symbol"] in ("RELIANCE", "GSEC2030")]
        assert [r["symbol"] for r in k.search("543210", False, 5)][:1] == ["TINYCO"]
        assert k.quote(["TINYCO", "RELIANCE"]).keys() == {"TINYCO", "RELIANCE"}
        assert main.bse_code("TINYCO") == "543210" and main.bse_code("543210") == "543210" and main.bse_code("RELIANCE") is None
        h = W.headers("pro-token")
        found = w["client"].get("/research/search?q=TINY&region=IN", headers=h).json()
        assert [(r["symbol"], r["exchange"]) for r in found] == [("TINYCO", "BSE")]
    finally:
        w["close"]()


def test_bse_only_company_page_chart_and_filings(monkeypatch):
    from tests import world as W
    w = W.build(monkeypatch)
    try:
        h = W.headers("pro-token")
        for asked in ("TINYCO", "543210"):
            c = w["client"].get(f"/research/company/IN/{asked}", headers=h).json()
            assert c["symbol"] == "TINYCO" and c["exchange"] == "BSE" and c["bse_code"] == "543210", asked
            assert c["name"] == "Tiny Co Ltd" and c["quote"]["price"] and c["testable"] and c["instrument_id"]
            assert c["facts"][0]["value"] == "BSE only · 543210"
            assert any("bseindia.com" in l["url"] for l in c["links"])
        assert w["client"].get("/research/chart/IN/TINYCO?range=1y", headers=h).json()["candles"]
        f = w["client"].get("/research/filings/TINYCO", headers=h).json()
        assert [i["category"] for i in f["items"]] == ["presentation", "concall", "pledge"]
        assert f["summary"]["red"] == 1                                          # the promoter pledge
        assert f["items"][0]["url"] == "https://www.bseindia.com/xml-data/corpfiling/AttachLive/abc-123.pdf"
        assert f["items"][1]["url"].endswith("/AttachHis/def-456.pdf") and f["items"][2]["url"] is None
        assert w["client"].get("/research/filings/RELIANCE", headers=h).json()["items"][0]["url"].startswith("https://nsearchives")
    finally:
        w["close"]()


def test_bse_only_deep_dive_reads_its_bse_documents(monkeypatch):
    from tests import world as W
    w = W.build(monkeypatch)
    try:
        h = W.headers("pro-token")
        d = w["client"].get("/research/deep/543210", headers=h).json()
        assert d["symbol"] == "TINYCO" and d["name"] == "Tiny Co Ltd" and d["numbers"]["years"]
        assert {x["kind"] for x in d["documents"]} == {"presentation", "transcript"}
        assert all("bseindia.com" in x["url"] for x in d["documents"]) and d["doc_note"] is None
        assert d["trend"] is not None and d["filings"]["red"] == 1
        r = w["client"].post("/research/deep/TINYCO/read", headers=h).json()
        assert r["symbol"] == "TINYCO" and r["reads"]                          # read from the BSE documents
    finally:
        w["close"]()


def test_bse_only_stock_backtests_and_joins_the_market_audit(monkeypatch):
    from app import universes
    from tests import world as W
    w = W.build(monkeypatch)
    try:
        ids, missing = universes.resolve(main.markets, "IN", [{"symbol": "TINYCO"}, {"symbol": "543210"}, {"symbol": "NOPE"}])
        assert ids == [main.kite.equity("TINYCO")["id"]] and missing == ["NOPE"]
        row = main._market_check("BSE:543210")
        assert row["symbol"] == "BSE:543210" and row["name"] == "Tiny Co Ltd"
        assert not [i for i in row["issues"] if i["level"] == "error"], row["issues"]
        assert not any("aren't read" in i["detail"] for i in row["issues"])
    finally:
        w["close"]()


def test_bse_rows_and_the_daily_check(monkeypatch):
    rows = filings.bse_rows([{"NEWSID": "x", "DissemDT": "2026-09-01T10:00:00.1", "NEWSSUB": "A Ltd - 500001 - Outcome of Board Meeting",
                              "SUBCATNAME": "", "HEADLINE": "Financial results", "ATTACHMENTNAME": "../evil.pdf"}, "junk"])
    assert rows == [{"seq_id": "x", "sort_date": "2026-09-01 10:00:00", "desc": "Outcome of Board Meeting",
                     "attchmntText": "Outcome of Board Meeting. Financial results", "attchmntFile": ""}]   # no path tricks
    from tests import world as W
    w = W.build(monkeypatch)
    try:
        assert platform_check.check_bse_filings(main.filings_feed.bse)["state"] == "pass"
    finally:
        w["close"]()
