"""The whole-market audit's controls from the admin page: reset and check everything again, start and pause with the
reason it is paused, the monthly full check (marked in the database so a restart doesn't repeat it), one company
re-checked by hand, and the slow hourly retries while BSE turns this server away. Also the platform check's BSE and
F&O ban fixes, and the US list without preferred shares."""
from datetime import date, datetime, timedelta, timezone

import httpx
import pytest

from app import audit, main, platform_check
from app.intel import filings as F
from app.intel import sec
from app.intel.net import SourceError


def _clean(sym):
    return {"symbol": sym, "name": sym, "seconds": 0.1, "issues": []}


def _refused(sym):
    return {"symbol": sym, "name": sym, "seconds": 0.1,
            "issues": [audit._later("Documents", main.BSE_WAIT)]}


def _old(*syms):
    return [{"symbol": s, "name": f"{s} Ltd", "listed": "2001-01-01"} for s in syms]


@pytest.fixture
def w(monkeypatch):
    from tests import world as W
    world = W.build(monkeypatch)
    yield world
    world["close"]()


# ---------- reset, start and pause ----------
def test_reset_clears_every_result_and_checks_everything_from_nothing(w):
    listing = _old("AAA", "BBB", "CCC")
    a = audit.MarketAudit(lambda: listing, _clean, pause=0)
    a.refresh_list(force=True)
    a.start_full()
    a.set_enabled(True)
    assert [a.step(), a.step(), a.step()] == ["AAA", "BBB", "CCC"]
    a.rows["BBB"]["issues"] = [audit._issue("error", "Numbers", "old finding")]
    a._save("BBB")
    a.set_enabled(False)
    a.reset()
    s = a.status()
    assert s["enabled"] and s["checked"] == 0 and s["summary"]["companies"] == 0 and s["reset_at"]
    assert s["full"]["running"] and s["full"]["checked"] == 0 and s["full"]["left"] == 3 and s["due"] == 3
    assert audit.MarketAudit(lambda: listing, _clean).status()["checked"] == 0          # cleared in the database too
    assert a.step() == "AAA"
    s = a.status()
    assert s["full"]["checked"] == 1 and s["rate_per_hour"] == 1 and s["eta_hours"] == 2.0   # 2 left at 1 an hour


def test_paused_says_why(w):
    busy = [False]
    a = audit.MarketAudit(lambda: _old("AAA"), _clean, busy_fn=lambda: busy[0], pause=0)
    assert a.status()["paused"] == "off"
    a.set_enabled(True)
    assert a.status()["paused"] is None
    busy[0] = True
    assert a.status()["paused"] == "busy"


def test_admin_routes_reset_pause_monthly_and_recheck(w):
    from tests import world as W
    h = W.headers("admin-token")
    c = w["client"]
    m = main.market_audit
    m.refresh_list(force=True)
    r = c.post("/admin/audit/market", headers=h, json={"on": True}).json()
    assert r["enabled"] and r["paused"] is None and r["monthly"]["on"] and r["monthly"]["next"]
    m.start_full()
    assert m.step()
    r = c.post("/admin/audit/market", headers=h, json={"on": False}).json()
    assert r["paused"] == "off" and r["checked"] == 1
    r = c.post("/admin/audit/market", headers=h, json={"reset": True}).json()
    assert r["enabled"] and r["checked"] == 0 and r["full"]["running"] and r["full"]["checked"] == 0
    r = c.post("/admin/audit/market", headers=h, json={"monthly": False}).json()
    assert r["monthly"] == {"on": False, "last": r["monthly"]["last"], "next": None}
    sym = sorted(m.listing)[0]
    r = c.post("/admin/audit/market", headers=h, json={"recheck": sym}).json()
    assert r["checked"] == 1 and m.rows[sym]["at"]
    assert c.post("/admin/audit/market", headers=h, json={"recheck": "NOT-LISTED"}).status_code == 404
    assert c.post("/admin/audit/market", headers=W.headers("pro-token"), json={"reset": True}).status_code == 403


def test_recheck_replaces_one_companys_result(w):
    listing = _old("AAA", "BBB")
    bad = {"AAA": True}
    a = audit.MarketAudit(lambda: listing, lambda s: {**_clean(s), "issues": [audit._issue("error", "Numbers", "x")]} if bad.get(s) else _clean(s), pause=0)
    a.refresh_list(force=True)
    a.recheck("AAA")
    assert a.rows["AAA"]["issues"][0]["level"] == "error"
    bad["AAA"] = False
    assert a.recheck("AAA")["issues"] == []
    with pytest.raises(KeyError):
        a.recheck("ZZZ")
    a.check_fn = lambda s: 1 / 0                                                      # a broken check is a finding
    assert a.recheck("BBB")["issues"][0]["area"] == "Audit"


# ---------- the monthly full check ----------
def test_monthly_full_check_runs_on_the_first_once(w):
    ist = audit.india_tz()
    listing = _old("AAA", "BBB")
    a = audit.MarketAudit(lambda: listing, _clean, pause=0)
    a.refresh_list(force=True)
    oct4 = datetime(2026, 10, 4, 9, tzinfo=ist)
    assert a.monthly(oct4) is False and a.state["monthly_run"] == "2026-10"           # first time: marks the month only
    assert not a.status()["full"]["running"]
    assert a.monthly(datetime(2026, 10, 31, 23, 59, tzinfo=ist)) is False
    nov1 = datetime(2026, 11, 1, 0, 5, tzinfo=ist)                                     # just after midnight in India
    assert a.monthly(nov1) is True and a.status()["full"]["running"] and a.status()["full"]["everything"]
    b = audit.MarketAudit(lambda: listing, _clean, pause=0)                            # the server restarted that day
    assert b.monthly(nov1) is False and b.state["monthly_run"] == "2026-11"
    b.set_monthly(False)
    assert b.monthly(datetime(2026, 12, 1, 1, tzinfo=ist)) is False and b.status()["monthly"]["next"] is None
    assert audit.next_month_start(datetime(2026, 12, 15)) == "2027-01-01"
    assert audit.next_month_start(oct4) == "2026-11-01"


def test_monthly_check_starts_even_while_paused_and_runs_when_started(w):
    ist = audit.india_tz()
    a = audit.MarketAudit(lambda: _old("AAA"), _clean, pause=0)
    a.refresh_list(force=True)
    a.monthly(datetime(2026, 10, 2, tzinfo=ist))
    a.rows["AAA"] = {**_clean("AAA"), "at": "2026-10-02T00:00:00+00:00"}
    a.monthly(datetime(2026, 11, 1, tzinfo=ist))
    assert a.step() is None and a.status()["full"]["left"] == 1                       # paused: waits, isn't lost
    a.set_enabled(True)
    assert a.step() == "AAA"


# ---------- slow retries while BSE refuses ----------
def test_refused_documents_retry_in_small_hourly_batches_with_backoff(w):
    listing = _old(*[f"BSE:5000{i:02d}" for i in range(30)])
    a = audit.MarketAudit(lambda: listing, _refused, pause=0)
    a.refresh_list(force=True)
    a.set_enabled(True)
    a.start_full()
    for _ in range(30):
        assert a.step()
    assert a.cool == 0                                                                # documents alone don't slow the rest
    assert a.step() is None and a.status()["full"]["done_at"]                          # through: they wait
    st = a.status()
    assert st["pending"] == 30 and st["retry"]["waiting"] == 30 and st["retry"]["due"] == 0
    hour_ago = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    for r in a.rows.values():
        r["at"] = hour_ago
    assert len(a.queue()) == audit.RETRY_BATCH                                          # a small batch, not all of them
    for _ in range(audit.RETRY_BATCH):
        a.step()
    assert a.queue() == [] and a.state["retry"]["gap"] == 2                             # all refused again: rests longer
    assert a.status()["retry"]["next"] > datetime.now(timezone.utc).isoformat()
    a.state["retry"]["next"] = hour_ago
    a.check_fn = _clean                                                               # BSE answers again
    for r in a.rows.values():
        r["at"] = hour_ago
    assert a.step() and a.state["retry"]["left"] == audit.RETRY_BATCH - 1
    for _ in range(audit.RETRY_BATCH - 1):
        a.step()
    assert a.state["retry"]["gap"] == audit.RETRY_GAP                                   # answered: back to hourly


def test_bse_refusing_leaves_documents_pending_and_the_panel_counts_them(w, monkeypatch):
    from tests import world as W

    def refuse(code, days=365):
        raise SourceError("the exchange", "The exchange feed refused the request (403). Try again later.", busy=True)
    monkeypatch.setattr(main.filings_feed.bse, "announcements", refuse)
    base = main.deep_base("TINYCO")
    assert base["doc_note"] == main.BSE_WAIT and base["meets"] is None
    row = main._market_check("BSE:543210")
    docs = [i for i in row["issues"] if i["area"] == "Documents"]
    assert docs and docs[0]["level"] == "pending" and "not available from BSE right now" in docs[0]["detail"]
    assert not [i for i in row["issues"] if i["level"] == "error"], row["issues"]
    a = audit.MarketAudit(lambda: _old("BSE:543210", "RELIANCE"), main._market_check, pause=0)
    a.refresh_list(force=True)
    a.recheck("BSE:543210")
    monkeypatch.setattr(main, "market_audit", a)
    main.filings_feed.bse._refused_at = 1.0
    s = w["client"].get("/admin/audit/market", headers=W.headers("admin-token")).json()
    assert s["bse"]["refusing"] and s["bse"]["waiting"] == 1
    # a company on NSE too reads NSE's filings, whatever BSE does
    assert main.deep_base("RELIANCE")["doc_note"] is None


# ---------- BSE's feed: browser headers, and a warning when it refuses ----------
def test_bse_api_calls_carry_the_headers_bses_own_site_sends():
    seen = []

    def handler(r):
        seen.append(r)
        return httpx.Response(200, text="<html></html>") if r.url.host == "www.bseindia.com" else httpx.Response(200, json={"Table": []})
    feed = F.BSEFilings(transport=httpx.MockTransport(handler), sleep=lambda s: None)
    feed.announcements("543210")
    page, api = seen[0], seen[1]
    assert page.url.host == "www.bseindia.com" and "origin" not in page.headers and page.headers["sec-fetch-mode"] == "navigate"
    assert api.url.host == "api.bseindia.com" and api.url.path == "/BseIndiaAPI/api/AnnSubCategoryGetData/w"
    h = api.headers
    assert h["origin"] == "https://www.bseindia.com" and h["referer"] == "https://www.bseindia.com/"
    assert h["accept"] == "application/json, text/plain, */*" and h["sec-fetch-site"] == "same-site" and h["sec-fetch-mode"] == "cors"
    assert "Chrome/128.0.0.0 Safari/537.36" in h["user-agent"] and '"Google Chrome";v="128"' in h["sec-ch-ua"]
    assert feed.state()["refusing"] is False and feed.state()["ok_at"]


def test_platform_check_warns_when_bse_refuses_this_server():
    feed = F.BSEFilings(transport=httpx.MockTransport(lambda r: httpx.Response(403)), sleep=lambda s: None)
    r = platform_check.check_bse_filings(feed)
    assert r["state"] == "warn" and "turning this server's requests away" in r["detail"] and "(403)" in r["detail"]
    assert "read their filings from NSE" in r["detail"] and feed.state()["refusing"]
    nothing = F.BSEFilings(transport=httpx.MockTransport(lambda r: httpx.Response(400)), sleep=lambda s: None)
    with pytest.raises(SourceError):                                                  # a real fault still fails
        platform_check.check_bse_filings(nothing)


# ---------- the F&O ban file's addresses ----------
def _nse(files: dict, asked: list):
    def handler(r):
        asked.append(r.url.path)
        if r.url.path in files:
            v = files[r.url.path]
            return httpx.Response(v) if isinstance(v, int) else httpx.Response(200, text=v)
        return httpx.Response(404)
    return F.NSEFilings(transport=httpx.MockTransport(handler), sleep=lambda s: None)


BAN = "Securities in Ban For Trade Date 05-OCT-2026:\n1,INFY\n"


def test_fo_ban_tries_each_known_address_in_turn():
    asked = []
    assert _nse({"/content/fo/fo_secban.csv": BAN}, asked).fo_ban() == ("2026-10-05", ["INFY"])
    assert asked == ["/content/fo/fo_secban.csv"]
    asked.clear()
    assert _nse({"/archives/fo/sec_ban/fo_secban.csv": BAN}, asked).fo_ban()[1] == ["INFY"]
    assert asked == ["/content/fo/fo_secban.csv", "/archives/fo/sec_ban/fo_secban.csv"]
    asked.clear()
    yesterday = (F.ist_now().date() - timedelta(days=1)).strftime("%d%m%Y")
    assert _nse({f"/archives/fo/sec_ban/fo_secban_{yesterday}.csv": BAN}, asked).fo_ban()[1] == ["INFY"]   # the dated copy
    assert asked[-1].endswith(f"fo_secban_{yesterday}.csv")
    asked.clear()
    with pytest.raises(SourceError, match="wasn't at any of its known addresses"):
        _nse({}, asked).fo_ban()
    assert len(asked) == len(F.fo_ban_urls())
    asked.clear()
    with pytest.raises(SourceError) as e:
        _nse({"/content/fo/fo_secban.csv": 503}, asked).fo_ban()                      # down: stops at once
    assert e.value.busy and asked == ["/content/fo/fo_secban.csv"]
    assert F.fo_ban_urls(date(2026, 10, 5))[2] == "https://nsearchives.nseindia.com/archives/fo/sec_ban/fo_secban_05102026.csv"


# ---------- the US list and prices ----------
def test_preferred_shares_warrants_units_and_rights_leave_the_us_list(w, monkeypatch):
    for t in ("AHL-PD", "AHL-P", "BAC.PRL", "ACON-W", "ALFU-U", "XYZ-RT", "ABC-WS", "ABC.U", "ABC-R"):
        assert sec.non_common(t), t
    for t in ("AHL", "BRK-B", "BRK-A", "AAPL", "GOOGL"):
        assert not sec.non_common(t), t
    monkeypatch.setattr(main.sec_feed, "tickers", lambda: {
        "AHL-PD": {"cik": 1, "name": "Aspen Insurance"}, "AHL-PE": {"cik": 1, "name": "Aspen Insurance"},   # preferred only
        "BRK-B": {"cik": 2, "name": "Berkshire"}, "BRK-A": {"cik": 2, "name": "Berkshire"},
        "ACONW": {"cik": 3, "name": "Aclarion"}, "ACON": {"cik": 3, "name": "Aclarion"}})
    assert [c["symbol"] for c in main._sec_companies()] == ["BRK-B", "ACON"]
    a = audit.MarketAudit(lambda: main._sec_companies(), _clean, pause=0, key="audit:market-us")
    a.listing = {"AHL-PD": {"name": "Aspen", "listed": None, "seen": None}}
    a.rows = {"AHL-PD": {**_clean("AHL-PD"), "issues": [audit._issue("mismatch", "Prices", "x")], "at": "2026-10-01"}}
    a.loaded = True
    a.refresh_list(force=True)
    assert "AHL-PD" not in a.rows and "AHL-PD" not in a.listing                       # the market audit drops it


def test_us_price_check_accepts_the_page_quotes_previous_close():
    trend = {"price": 1.01}
    assert audit.check_prices({"price": 1.23}, trend, None, None, (1.23, 1.01)) == []   # today's price vs yesterday's close
    found = audit.check_prices({"price": 1.23}, trend, None, None, (1.23, 1.20))
    assert found[0]["level"] == "mismatch" and "previous close 1.20" in found[0]["detail"]
    assert audit.check_prices({"price": 1.23}, trend, None)[0]["level"] == "mismatch"   # no quote: as before
