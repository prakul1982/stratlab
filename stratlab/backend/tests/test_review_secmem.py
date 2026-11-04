"""SECMEM lane (Wed 4 Nov): one account can't read, change or delete another account's things by id (item 1d).
Two Pro accounts (so no plan lock hides a hole behind a 402): A makes one of each, B tries every by-id route on it.
Each must refuse (404/403/422) and A's item must stay exactly as it was."""

import json

import pytest

from app import guard
from tests import stress_requests as SR, world as W

A, B = W.headers("pro-token"), W.headers("money-23")
REFUSED = (403, 404, 422)
BTC = "CRYPTO:BTC-USD"


@pytest.fixture(scope="module")
def c():
    mp = pytest.MonkeyPatch()
    w = W.build(mp)
    mp.setattr(guard, "BAD_TOKENS_PER_MINUTE", 10**6)
    yield w["client"]
    w["close"]()
    mp.undo()


def ok(r):
    assert r.status_code == 200, r.text[:300]
    return r.json()


def refused(c, tries):
    for method, url, body in tries:
        r = c.request(method, url, headers=B, json=body)
        assert r.status_code in REFUSED, f"{method} {url} as another account: {r.status_code} {r.text[:160]}"


def owner_can(c, tries):
    """The same calls, made by the owner, go through: so the refusals above came from whose item it is, not a bad body."""
    for method, url, body in tries:
        r = c.request(method, url, headers=A, json=body)
        assert r.status_code == 200, f"{method} {url} as the owner: {r.status_code} {r.text[:160]}"


def test_watchlists(c):
    lists = ok(c.post("/watch/lists", headers=A, json={"name": "A list"}))["lists"]
    lid = next(x["id"] for x in lists if x["name"] == "A list")
    ok(c.put(f"/watch/lists/{lid}/items", headers=A, json={"items": [{"id": "IN:RELIANCE"}]}))
    before = ok(c.get("/watch/lists", headers=A))["lists"]
    refused(c, [("PATCH", f"/watch/lists/{lid}", {"name": "Stolen"}), ("DELETE", f"/watch/lists/{lid}", None),
                ("PUT", f"/watch/lists/{lid}/items", {"items": [{"id": "IN:TCS"}]})])
    assert ok(c.get("/watch/lists", headers=A))["lists"] == before
    assert lid not in json.dumps(ok(c.get("/watch/lists", headers=B)))
    owner_can(c, [("PATCH", f"/watch/lists/{lid}", {"name": "Renamed"}), ("PUT", f"/watch/lists/{lid}/items", {"items": [{"id": "IN:TCS"}]})])


def test_stock_and_breadth_alerts(c):
    aid = ok(c.post("/alerts", headers=A, json={"region": "IN", "symbol": "RELIANCE", "kind": "deal"}))["alert"]["id"]
    refused(c, [("PUT", f"/alerts/{aid}", {"region": "IN", "symbol": "TCS", "kind": "deal"}), ("DELETE", f"/alerts/{aid}", None)])
    mine = ok(c.get("/alerts", headers=A))["active"]
    assert [(x["id"], x["symbol"]) for x in mine] == [(aid, "RELIANCE")]
    assert aid not in json.dumps(ok(c.get("/alerts", headers=B)))
    owner_can(c, [("PUT", f"/alerts/{aid}", {"region": "IN", "symbol": "TCS", "kind": "deal"})])
    got = ok(c.post("/invest/breadth/alerts", headers=A, json={"group": "nifty500", "level": 60}))
    bid = got["items"][0]["id"]
    refused(c, [("DELETE", f"/invest/breadth/alerts/{bid}", None)])
    assert [x["id"] for x in ok(c.get("/invest/breadth/alerts", headers=A))["items"]] == [bid]


def test_holdings_and_tax(c):
    ok(c.put("/holdings", headers=A, json={"items": [{"symbol": "RELIANCE", "qty": 5, "avg": 1200, "market": "IN"}]}))
    assert ok(c.get("/holdings", headers=B))["rows"] == []
    c.delete("/holdings", headers=B)                                        # B clearing their own holdings leaves A's
    assert [x["symbol"] for x in ok(c.get("/holdings", headers=A))["rows"]] == ["RELIANCE"]
    t = ok(c.post("/money/us-tax/trades", headers=A, json={"d": "2025-03-03", "side": "B", "sym": "AAPL", "qty": 2, "price": 150}))
    tid = t["trades"][0]["id"]
    refused(c, [("DELETE", f"/money/us-tax/trades/{tid}", None)])
    assert [x["id"] for x in ok(c.get("/money/us-tax", headers=A))["trades"]] == [tid]
    assert ok(c.get("/money/us-tax", headers=B))["trades"] == []


def test_journal_trades(c):
    body = {"symbol": "INFY", "side": "long", "entry_date": "2026-03-02", "exit_date": "2026-03-03", "qty": 10,
            "entry_price": 1500, "exit_price": 1510}
    tid = ok(c.post("/trade/journal/trades", headers=A, json=body))["trades"][0]["id"]
    refused(c, [("PUT", f"/trade/journal/trades/{tid}/note", {"notes": "stolen"}), ("DELETE", f"/trade/journal/trades/{tid}", None)])
    mine = ok(c.get("/trade/journal", headers=A))["trades"]
    assert [x["id"] for x in mine] == [tid] and not mine[0].get("notes")
    assert ok(c.get("/trade/journal", headers=B))["trades"] == []
    owner_can(c, [("PUT", f"/trade/journal/trades/{tid}/note", {"notes": "mine"})])


def test_paper_sessions_and_signal_webhooks(c):
    sid = ok(c.post("/live/sessions", headers=A, json={"strategy": SR.EMA, "instrument": BTC}))["id"]
    refused(c, [("GET", f"/live/sessions/{sid}", None), ("POST", f"/live/sessions/{sid}/stop", None), ("DELETE", f"/live/sessions/{sid}", None)])
    assert ok(c.get(f"/live/sessions/{sid}", headers=A))["status"] == "running"
    assert sid not in json.dumps(ok(c.get("/live/sessions", headers=B)))
    # a forward test fed by an outside signal: B can't read it, test it, or reach it through B's own webhook
    fid = ok(c.post("/trade/signals/sessions", headers=A, json={"instrument": BTC, "capital": 100000}))["id"]
    refused(c, [("GET", f"/trade/signals/sessions/{fid}", None), ("POST", f"/trade/signals/sessions/{fid}/test", {"action": "buy"})])
    path = ok(c.post("/trade/signals/hook", headers=B))["path"]
    r = c.post(path, content=json.dumps({"session": fid, "action": "buy", "qty": 1}).encode(), headers={"Content-Type": "application/json"})
    assert r.status_code in REFUSED, r.text
    assert not ok(c.get(f"/trade/signals/sessions/{fid}", headers=A)).get("trade_list")
    owner_can(c, [("POST", f"/trade/signals/sessions/{fid}/test", {"action": "buy", "qty": 1}), ("POST", f"/live/sessions/{sid}/stop", None)])


def test_notebook_runs_and_library(c):
    nid = ok(c.post("/notebooks", headers=A, json={"name": "Mine", "market": "IN"}))["id"]
    refused(c, [("GET", f"/notebooks/{nid}/experiments/1/trades.csv", None), ("POST", f"/notebooks/{nid}/experiments/1/walkforward", None),
                ("POST", f"/notebooks/{nid}/experiments/1/basket", None),
                ("POST", f"/notebooks/{nid}/experiments/1/library", {"title": "Stolen", "description": "x"}),
                ("DELETE", f"/notebooks/{nid}/experiments/1/share", None)])
    assert ok(c.get(f"/notebooks/{nid}", headers=A))["name"] == "Mine"


def test_money_items_events_screens_scans_follows_keys_replays(c):
    iid = ok(c.post("/money/net-worth/items", headers=A, json={"kind": "cash", "value": 50000}))["assets"]
    iid = next(x["id"] for x in iid if x["kind"] == "cash")
    refused(c, [("PUT", f"/money/net-worth/items/{iid}", {"kind": "cash", "value": 1}), ("DELETE", f"/money/net-worth/items/{iid}", None)])
    assert [x["value"] for x in ok(c.get("/money/net-worth", headers=A))["assets"] if x["id"] == iid] == [50000]
    owner_can(c, [("PUT", f"/money/net-worth/items/{iid}", {"kind": "cash", "value": 1})])

    ev = ok(c.post("/money/calendar/events", headers=A, json={"date": "2026-11-05", "title": "FD matures"}))
    eid = ev["own"][0]["id"]
    refused(c, [("PUT", f"/money/calendar/events/{eid}", {"date": "2026-11-06", "title": "Stolen"}), ("DELETE", f"/money/calendar/events/{eid}", None)])
    assert [(x["id"], x["title"]) for x in ok(c.get("/money/calendar", headers=A))["own"]] == [(eid, "FD matures")]
    owner_can(c, [("PUT", f"/money/calendar/events/{eid}", {"date": "2026-11-06", "title": "Renamed"})])

    screen = {"name": "Low debt", "region": "IN", "filters": {"sector": ["Energy"]}, "notify": True}
    sid = ok(c.post("/research/screens/saved", headers=A, json=screen))["screen"]["id"]
    refused(c, [("PUT", f"/research/screens/saved/{sid}", {**screen, "name": "Stolen"}), ("DELETE", f"/research/screens/saved/{sid}", None)])
    assert [x["name"] for x in ok(c.get("/research/screens/saved", headers=A))["items"]] == ["Low debt"]
    owner_can(c, [("PUT", f"/research/screens/saved/{sid}", {**screen, "name": "Renamed"})])

    rules = [{"l": {"t": "volume"}, "op": "gt", "r": {"t": "vol_sma", "p": 20, "ago": 1, "k": 2}}]
    cid = ok(c.put("/research/scan/custom", headers=A, json={"name": "Volume", "region": "IN", "rules": rules}))["items"][0]["id"]
    c.delete(f"/research/scan/custom/{cid}", headers=B)
    c.put("/research/scan/custom", headers=B, json={"name": "Stolen", "region": "IN", "rules": rules, "id": cid})
    assert [x["name"] for x in ok(c.get("/research/scan/custom", headers=A))["items"]] == ["Volume"]   # B's copy is B's own

    fid = ok(c.put("/invest/holders/follow", headers=A, json={"label": "Ashish Kacholia", "names": ["ASHISH KACHOLIA"]}))["follows"][0]["id"]
    refused(c, [("DELETE", f"/invest/holders/follow/{fid}", None)])
    assert [x["id"] for x in ok(c.get("/invest/holders", headers=A))["follows"]] == [fid]

    kid = ok(c.post("/me/assistant/keys", headers=A, json={"name": "Laptop"}))["key"]["id"]
    refused(c, [("DELETE", f"/me/assistant/keys/{kid}", None)])
    assert any(k["id"] == kid and not k.get("revoked_at") for k in ok(c.get("/me/assistant", headers=A))["keys"])

    rid = ok(c.post("/trade/replay", headers=A, json={"instrument": BTC, "tf": "1d", "start": "2025-01-06"}))["id"]
    refused(c, [("GET", f"/trade/replay/{rid}", None), ("POST", f"/trade/replay/{rid}/finish", {"cursor": 1}), ("DELETE", f"/trade/replay/{rid}", None)])
    assert ok(c.get(f"/trade/replay/{rid}", headers=A))["id"] == rid
    owner_can(c, [("DELETE", f"/trade/replay/{rid}", None), ("DELETE", f"/me/assistant/keys/{kid}", None),
                  ("DELETE", f"/invest/holders/follow/{fid}", None)])


# ---------- item 2: large PDFs are read in a short-lived process ----------
def test_a_large_pdf_is_read_in_a_child_process_with_the_same_text(monkeypatch):
    from app import biz_updates, docs, ipo_docs, pdf_proc
    from tests.pdfmaker import make_pdf_pages
    data = make_pdf_pages([["OBJECTS OF THE OFFER", "Rs 120 crore"], ["Second page"], ["Third page"]])
    here = pdf_proc.page_texts(data, 2)
    ran = []
    real = pdf_proc.subprocess.run
    monkeypatch.setattr(pdf_proc.subprocess, "run", lambda *a, **k: ran.append(a[0][1]) or real(*a, **k))
    monkeypatch.setattr(pdf_proc, "SUBPROCESS_BYTES", 0)                  # this small file counts as large
    assert pdf_proc.page_texts(data, 2) == here and here[1] == 3 and "OBJECTS OF THE OFFER" in here[0][0]
    assert ran == ["-I"]                                                  # in a child, isolated from the app's own files
    assert ipo_docs.pdf_pages(data)[1].strip() == "Second page"
    assert biz_updates.pdf_pages(data, 1) == ["OBJECTS OF THE OFFER\nRs 120 crore"]
    assert docs.pdf_text_pages(data)[1] == 3
    assert len(ran) == 4


def test_a_large_pdf_that_cant_be_read_or_needs_too_much_memory_fails_the_read_not_the_server(monkeypatch):
    from app import docs, pdf_proc
    from tests.pdfmaker import make_pdf
    monkeypatch.setattr(pdf_proc, "SUBPROCESS_BYTES", 0)
    with pytest.raises(pdf_proc.PdfUnreadable):
        pdf_proc.page_texts(b"%PDF-1.4 not really a pdf", 5)
    with pytest.raises(pdf_proc.PdfUnreadable):                           # the callers turn it into their "couldn't be read"
        docs.pdf_text_pages(b"%PDF-1.4 broken")
    monkeypatch.setattr(pdf_proc, "CHILD_MEMORY_MB", 40)                 # the cap holds: the child gives up, not this process
    with pytest.raises(pdf_proc.PdfUnreadable):
        pdf_proc.page_texts(make_pdf(["fine"]), 5)
    monkeypatch.setattr(pdf_proc.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(OSError("no processes left")))
    assert pdf_proc.page_texts(make_pdf(["fine"]), 5)[0][0].strip() == "fine"   # no child possible: read here


# ---------- item 5: the morning Kite login and the restart after it ----------
def test_a_restart_right_after_the_kite_login_keeps_the_token(monkeypatch):
    from types import SimpleNamespace as NS

    from app import db, kite_auto, memguard
    from app.kite_service import KiteService, today_ist
    w = W.build(monkeypatch)
    try:
        svc = KiteService()
        svc.kite._inner = NS(login_url=lambda: "https://kite.zerodha.com/connect/login?api_key=k",
                             generate_session=lambda rt, api_secret=None: {"access_token": "ACCESS-" + rt}, set_access_token=lambda t: None)
        monkeypatch.setattr(kite_auto, "configured", lambda: True)
        during = []
        monkeypatch.setattr(kite_auto, "fetch_request_token", lambda url: during.append(memguard.TURNS.name) or "RT1")
        seen = []
        # what after_login does with the live feed running: the process ends right here
        al = kite_auto.AutoLogin(svc, lambda: seen.append((db.get_setting("kite_access_token"), db.get_setting("kite_token_day"))))
        assert al.run_once(only_if_due=False)
        assert during == ["Kite login"]                        # no heavy job starts while the login saves the token
        assert seen == [("ACCESS-RT1", today_ist())]           # saved before the restart could happen
        assert memguard.TURNS.name is None                     # and the turn handed back
        fresh = KiteService()                                  # the process after the restart
        fresh.load_saved_token()
        assert (fresh.access_token, fresh.token_day) == ("ACCESS-RT1", today_ist())
    finally:
        w["close"]()


def test_the_restart_waits_for_the_running_heavy_step_and_starts_none_after_it(monkeypatch):
    import threading
    import time

    from app import kite_auto, leader, memguard
    exits, order = [], []
    monkeypatch.setattr(kite_auto.os, "_exit", lambda code: exits.append((code, memguard.TURNS.name)))
    monkeypatch.setattr(leader.current, "release", lambda: order.append("lease"))
    step_done = threading.Event()

    def job():
        with memguard.heavy("an offer document") as got:
            assert got
            time.sleep(0.4)
            order.append("step done")
        step_done.set()
    t = threading.Thread(target=job)
    t.start()
    time.sleep(0.1)
    kite_auto.restart_process(delay=0).join(5)
    t.join(5)
    assert order == ["step done", "lease"]
    assert exits == [(3, "restart after the Kite login")]           # the turn held at the exit: no heavy job started before it
    assert memguard.TURNS.name is None                               # (handed back only because this exit was stubbed out)


# ---------- item 6: the monthly audit's findings, fixed where they come from ----------
def test_a_new_us_listing_the_profile_source_doesnt_know_stands_on_its_listing(monkeypatch):
    """APXC, CHWM, DAVI, VNYR (1 Nov): "No US company found", though the market quotes each under its name."""
    from app import main
    hub = main.research_hub
    fh = hub.finnhub
    monkeypatch.setattr(fh, "profile", lambda s: {})
    for name in ("quote", "metrics", "peers", "recommendation", "earnings", "financials", "insider", "earnings_calendar", "news"):
        monkeypatch.setattr(fh, name, lambda *a, **k: None)
    monkeypatch.setattr(hub.yahoo, "meta", lambda s: {"name": "Apex Critical Metals Corp.", "currency": "USD", "exchange": "NCM", "price": 4.57})
    monkeypatch.setattr(hub, "_quiet_candles", lambda s: [])
    out = hub._company_us("APXC", lean=True)
    assert out["name"] == "Apex Critical Metals Corp." and out["currency"] == "USD"
    monkeypatch.setattr(hub.yahoo, "meta", lambda s: {})                  # nothing quotes it anywhere: still no page
    with pytest.raises(Exception, match="No US company found"):
        hub._company_us("ADVI", lean=True)


def test_a_us_ticker_no_market_quotes_yet_is_a_fact_not_a_broken_page(monkeypatch):
    """ADVI, GPOD, KBGHF, TPTI, TEGO (1 Nov): on the SEC's list, no price anywhere."""
    from app import audit, deepdive, main, report_card
    from app.intel.net import NotFound
    from tests.test_deepdive import company
    monkeypatch.setattr(deepdive, "stored", lambda s: None)
    monkeypatch.setattr(report_card, "stored", lambda s: None)
    p = {**company(), "region": "US"}

    def page(s):
        raise NotFound("Finnhub", f"No US company found for {s}. Use the exact ticker, like NVDA or AAPL.")

    def row(quote):
        base = lambda s: {"p": p, "docs": [], "doc_note": None, "filings": None, "trend": None, "trend_why": "new", "quote": quote}
        return [(i["level"], i["detail"]) for i in audit.audit_company("ADVI", base, main.deep_view, listing_fn=page)["issues"]
                if i["area"] == audit.LISTING]
    assert row(None) == [("fact", audit.NOT_QUOTED)]
    assert row({"price": 4.5})[0][0] == "error"                            # quoted somewhere, yet no page: still an error


def test_a_share_days_old_with_no_broker_candles_takes_its_first_day_from_the_listing(monkeypatch):
    """PARASHLTH (listed 26 Oct): its range wasn't marked as the range since listing on the company page."""
    from datetime import timedelta

    from app import main
    from app.intel.company import ist_date
    w = W.build(monkeypatch)
    try:
        hub = main.research_hub
        first = (ist_date() - timedelta(days=6)).isoformat()
        monkeypatch.setattr(hub.kite, "history", lambda *a, **k: [])
        monkeypatch.setattr(hub.yahoo, "meta", lambda s: {"name": "Reliance", "currency": "INR", "first_trade": first})
        asked = []
        real = hub._listing_or_none
        monkeypatch.setattr(hub, "_listing_or_none", lambda s: asked.append(s) or real(s))
        assert hub._company_in("RELIANCE", lean=True)["range52"].get("since") == first
        assert asked == ["RELIANCE.NS"]                                       # the broker's share, its candles empty: asked
        old = (ist_date() - timedelta(days=900)).isoformat()                 # an older share: no mark
        monkeypatch.setattr(hub.yahoo, "meta", lambda s: {"name": "Reliance", "currency": "INR", "first_trade": old})
        assert "since" not in hub._company_in("RELIANCE", lean=True)["range52"]
    finally:
        w["close"]()


def test_a_new_listing_checked_before_its_first_session_is_a_fact():
    """SFCTECH, BLSPOLY, BSE:545010: checked at 08:08 IST on 3 Nov, listing that morning."""
    from app import audit
    p = {"region": "IN", "balance": {"cols": ["Mar 2026"]}, "ratios": {}}
    got = audit.check_listing({"range52": {}, "quote": {}}, p, {"years": []}, {})
    assert [(i["level"], i["detail"]) for i in got] == [("fact", audit.NOT_TRADED_YET)]
    got = audit.check_listing({"range52": {"low": 1.0, "high": 2.0}, "quote": {"price": 1.5}}, p, {"years": []}, {})
    assert [i["level"] for i in got] == ["gap"]                              # trading, and still not marked: the gap stands


def _scr(np, eps, equity, cap, price, own, cols=("Mar 2025", "Mar 2026", "TTM")):
    """A company page's tables as the source gives them (the numbers read from its page on 4 Nov)."""
    return {"region": "IN", "pl": {"cols": list(cols), "rows": {"Sales": [10.0] * len(cols), "Net Profit": list(np), "EPS in Rs": list(eps)}},
            "balance": {"cols": ["Mar 2025", "Mar 2026"], "rows": {"Equity Capital": list(equity), "Reserves": [5.0, 5.0]}},
            "ratios": {"Market Cap": f"₹ {cap} Cr.", "Current Price": f"₹ {price}", "Stock P/E": str(own), "Face Value": "₹ 10.0"}}


def test_a_share_capital_bigger_than_the_shares_the_eps_counts_doesnt_set_the_market_value():
    """BSE:531572 and BSE:512477 (1 Nov): their market value came from share capital ÷ face value (42.6 and 20 lakh shares)
    though profit ÷ EPS counts 26.9 and 15.1 lakh, as the source does; the P/E check then failed (912.5 vs 1,555)."""
    from app.intel import screener as S
    ranjit = _scr([0.52, 0.07, 0.02], [1.93, 0.26, 0.08], [4.26, 4.26], 19.6, 73.0, 982)
    betex = _scr([2.0, 6.0, 6.0], [13.0, 37.8, 39.66], [2.0, 2.0], 77.1, 514.0, 13.0)
    assert S.summary(ranjit)["market_cap_cr"] == 19.6 and S.summary(ranjit)["pe"] == 912.5
    assert S.summary(betex)["market_cap_cr"] == 77.1 and S.summary(betex)["pe"] == 13.0
    # without an EPS row to say which count is right, a share capital that drifts from the source's count still sets it
    no_eps = _scr([0.52, 0.07, 0.02], [None, None, None], [4.26, 4.26], 19.6, 73.0, 982)
    assert S.summary(no_eps)["market_cap_cr"] == round(73.0 * 0.426, 2)


def test_a_source_pe_under_one_never_settles_the_pe():
    """SADBHIN (1 Nov): P/E 0.96 shown, the source's own, which agrees with market value ÷ a net profit that includes the
    minority holders' share; on the earnings per share its own shareholders have it is 2.8."""
    from app.intel import screener as S
    sadbhav = _scr([-34.0, 45.0, 115.0], [-2.13, -0.56, 1.07], [352.2, 352.2], 104, 2.95, 0.86)
    got = S.summary(sadbhav)
    assert got["pe"] is None and "2.8" in got["pe_why"] and "0.9" in got["pe_why"]      # held back, with both figures said


def test_the_audit_holds_a_tiny_profits_pe_to_the_range_its_rounding_allows():
    """BSE:531572: a trailing profit of 0.02 cr is 0.015 to 0.025, so on a 31.1 cr value any P/E from about 1,244 to 2,073."""
    from app import audit
    p = {"region": "IN", "pl": {"cols": ["Mar 2026", "TTM"], "rows": {"Net Profit": [0.07, 0.02]}}}
    nums = {"years": [{"year": "Mar 2026", "sales": 10.0, "profit": 0.07}]}
    mism = lambda pe: [i for i in audit.check_numbers(p, nums, {"pe": pe, "market_cap_cr": 31.1}, None) if i["level"] == "mismatch"]  # noqa: E731
    assert mism(1000.0) == []                                                # 56% from 1,555, yet within what 0.015-0.025 cr allows
    assert mism(400.0) and "P/E 400.0 on the company page" in mism(400.0)[0]["detail"]   # far outside it: still a mismatch


def test_a_finished_market_check_counts_only_listed_companies_as_checked(monkeypatch):
    """Admin › Quality (SECMEM 6): a row kept for a company no longer on the list isn't one of the listed companies checked."""
    from datetime import date, timedelta

    from app import audit
    w = W.build(monkeypatch)
    try:
        day = lambda n: (date.today() - timedelta(days=n)).isoformat()  # noqa: E731
        listing = [{"symbol": s, "name": s, "listed": day(n)} for s, n in (("AAA", 1), ("BBB", 2))]
        clean = lambda sym, *a, **k: {"symbol": sym, "name": sym, "seconds": 0.1, "issues": []}  # noqa: E731
        a = audit.MarketAudit(lambda: listing, clean, pause=0)
        a.set_enabled(True)
        while a.step():
            pass
        a.rows["GONE"] = {"symbol": "GONE", "name": "GONE", "seconds": 0.1, "at": "2026-10-01T00:00:00+00:00", "issues": []}   # kept from before
        s = a.status()
        assert (s["listed"], s["checked"], s["due"]) == (2, 2, 0)
    finally:
        w["close"]()


# ---------- item 4: Admin's IPO queue ----------
def test_admin_reads_the_ipo_queue_with_the_documents_still_to_read(monkeypatch):
    from app import db, ipo as I
    w = W.build(monkeypatch)
    try:
        day = I._ai_day()
        db.set_setting("ipo:ai:" + day, "37")
        db.set_setting("ipo:ai:asked:" + day, "4")
        rows = [{"name": "Acme", "docs": [{"url": "https://x/a.pdf"}]}, {"name": "Beta", "docs": [{"url": "https://x/b.pdf"}]}]
        monkeypatch.setattr(I, "load", lambda m: {"rows": rows if m == "IN" else []})
        monkeypatch.setattr(I, "doc_to_read", lambda r: r["docs"][0])
        monkeypatch.setattr(I, "stage_of", lambda r, now=None: "upcoming")
        monkeypatch.setattr(I, "summary_of", lambda d: None)
        kept = {"https://x/a.pdf": {"reader": I.D.READER, "excerpt": "read"}, "https://x/b.pdf": {"reader": I.D.READER - 1, "excerpt": "old"}}
        monkeypatch.setattr(I, "facts_of", lambda d: kept.get(d["url"]))
        r = w["client"].get("/admin/ipos/queue", headers=W.headers("admin-token"))
        assert r.status_code == 200, r.text
        assert r.json() == {"scheduled": 37, "cap": 120, "asked": 4, "waiting": 2, "days": 1, "to_read": 1, "per_pass": I.SMALL}
        assert w["client"].get("/admin/ipos/queue", headers=W.headers("pro-token")).status_code == 403
    finally:
        w["close"]()


def _facts(tax: str, concept: str, val: float, form: str = "10-K", unit: str = "USD") -> dict:
    """A company's SEC facts as filed (the companyfacts shape): one year's revenue line under `concept` and its net income."""
    row = lambda v: {"start": "2016-01-01", "end": "2016-12-31", "val": v, "fy": 2016, "fp": "FY", "form": form,  # noqa: E731
                     "filed": "2017-03-01", "accn": "0000000000-17-000001", "frame": "CY2016"}
    income = "ProfitLoss" if tax == "ifrs-full" else "NetIncomeLoss"
    return {"cik": 1, "entityName": "X", "facts": {tax: {concept: {"units": {unit: [row(val)]}}, income: {"units": {unit: [row(-5e6)]}}}}}


@pytest.mark.parametrize("tax,concept,sym", [
    ("us-gaap", "OilAndGasSalesRevenue", "CRK"), ("us-gaap", "HealthCareOrganizationPatientServiceRevenue", "EHSI"),
    ("us-gaap", "AdvertisingRevenue", "GWAV"), ("ifrs-full", "RevenueFromRenderingOfCargoAndMailTransportServices", "TRMD"),
    ("us-gaap", "RevenueRecognitionMilestoneMethodRevenueRecognized", "JSPR"), ("us-gaap", "RevenueNotFromContractWithCustomer", "CATX"),
    ("ifrs-full", "RevenueFromSaleOfSilver", "CRCUF"), ("us-gaap", "GoldProductsAndServicesRevenue", "XTGRF"),
    ("us-gaap", "ResultsOfOperationsRevenueFromOilAndGasProducingActivities", "GRVE"), ("ifrs-full", "OtherRevenue", "KZIA"),
])
def test_a_us_companys_only_revenue_line_is_read(tax, concept, sym):
    """The monthly audit's "Revenue or profit missing" (1 Nov): each of these filed its revenue only under this line."""
    from app.intel import sec
    p = sec.build(_facts(tax, concept, 175_706_000, "20-F" if tax == "ifrs-full" else "10-K"), None, symbol=sym)
    i = p["pl"]["cols"].index("Dec 2016")
    sales = (p["pl"]["rows"].get("Sales") or p["pl"]["rows"].get("Revenue"))[i]
    assert sales == pytest.approx(175.71, abs=0.01) and p["pl"]["rows"]["Net Profit"][i] == pytest.approx(-5.0)


# ---------- the US last-close mismatches: a quote that lags its own daily candles ----------
def _ts(day: str) -> int:
    from datetime import datetime, timezone
    return int(datetime.fromisoformat(day + "T20:00:00").replace(tzinfo=timezone.utc).timestamp())


def _bar(day, c, v, h=None, l=None):  # noqa: E741
    return {"t": f"{day}T00:00:00-04:00", "o": c, "h": h if h is not None else c, "l": l if l is not None else c, "c": c, "v": v}


@pytest.mark.parametrize("sym,meta_day,meta_px,bars,want", [
    # MVNC: the quote said 0.18 from 16 Oct; it traded at 0.12 on 29 Oct (the closes after carry it, with no volume)
    ("MVNC", "2026-10-16", 0.18, [_bar("2026-10-28", 0.18, 0), _bar("2026-10-29", 0.12, 118522), _bar("2026-10-30", 0.12, 0)], (0.12, 0.18, "2026-10-29")),
    # NGTF: 3.30 from 26 Oct beside sessions up to 5.70 on 2 Nov
    ("NGTF", "2026-10-26", 3.30, [_bar("2026-10-30", 5.22, 22599), _bar("2026-11-02", 5.70, 27096)], (5.70, 5.22, "2026-11-02")),
    # WSKEF: 12.50 on 16 Oct, a session that traded 9.06 to 9.75 and closed 9.23
    ("WSKEF", "2026-10-16", 12.5, [_bar("2026-10-15", 9.83, 55151), _bar("2026-10-16", 9.23, 33941, 9.75, 9.065)], (9.23, 9.83, "2026-10-16")),
])
def test_a_quote_that_lags_its_own_sessions_gives_way_to_the_newest_traded_close(monkeypatch, sym, meta_day, meta_px, bars, want):
    from app.intel import yahoo as Y
    meta = {"symbol": sym, "regularMarketPrice": meta_px, "regularMarketTime": _ts(meta_day), "exchangeTimezoneName": "America/New_York",
            "currency": "USD", "regularMarketDayHigh": meta_px, "regularMarketDayLow": meta_px}
    yh = Y.Yahoo.__new__(Y.Yahoo)
    asked = []
    monkeypatch.setattr(Y.Yahoo, "chart", lambda self, s, tf, days, **k: asked.append(days) or {"meta": meta, "candles": bars if days > 7 or sym != "WSKEF" else []})
    got = yh.meta(sym)
    assert (got["price"], got["prev_close"], got["at"]) == want
    assert asked == ([7, 40] if sym == "WSKEF" else [7])                    # a longer window only when the quote's session isn't in the short one


def test_a_quote_inside_its_own_session_or_after_the_last_candle_stands():
    from app.intel import yahoo as Y
    meta = {"regularMarketPrice": 9.5, "regularMarketTime": _ts("2026-10-16"), "exchangeTimezoneName": "America/New_York"}
    assert Y._session_close(meta, [_bar("2026-10-16", 9.23, 33941, 9.75, 9.065)]) is None          # within the day's range
    assert Y._session_close({**meta, "regularMarketTime": _ts("2026-10-19")}, [_bar("2026-10-16", 9.23, 33941)]) is None   # a later session
    assert Y._session_close(meta, [_bar("2026-10-16", 9.23, 0)]) is None                            # nothing traded: nothing to go by


def test_a_us_company_with_a_few_desks_of_plant_has_a_capex_fact_not_a_gap():
    """EOCN, RWAX (1 Nov): plant of $0.08 m and $0.01 m, no purchases filed in three years."""
    from app import audit
    years = [{"year": y, "sales": 1.0, "profit": -1.0, "capex": None} for y in ("Dec 2023", "Dec 2024", "Dec 2025")]
    p = {"region": "US", "unit": "$ million", "balance": {"cols": ["Dec 2022", "Dec 2023", "Dec 2024", "Dec 2025"],
                                                          "rows": {"Fixed Assets": [0.11, 0.08, None, None]}}}
    capex = lambda p: [(i["level"], i["detail"]) for i in audit.check_numbers(p, {"years": years}, {}, None) if i["area"] == "Capex"]  # noqa: E731
    got = capex(p)
    assert [lv for lv, _ in got] == ["fact"] and "at most $0.08 m" in got[0][1]
    p["balance"]["rows"]["Fixed Assets"] = [40.0, 38.0, 36.0, 35.0]             # real plant, no capex read: the gap stands
    assert [lv for lv, _ in capex(p)] == ["gap"]


# ---------- call transcripts: a notice of a call to come isn't a call held ----------
NSE_MEET = "Analysts/Institutional Investor Meet/Con. Call Updates"


def _filing(at, text, url, subject=NSE_MEET, category="concall"):
    return {"at": at, "subject": subject, "text": text, "url": url, "category": category}


def test_a_transcript_is_due_only_once_the_call_is_held(monkeypatch):
    """ANTELOPUS, PANACHE, BSE:544937 (checked 31 Oct-1 Nov): their notices of calls to come were counted as calls whose
    transcript was overdue; the transcripts were filed on 2 Nov, and NSE's call was on 3 Nov."""
    from datetime import datetime

    from app import deepdive
    from app.intel.filings import IST
    monkeypatch.setattr(deepdive, "ist_now", lambda: datetime(2026, 11, 1, 9, 0, tzinfo=IST))
    antelopus = [
        _filing("2026-10-22T18:00", "Antelopus Selan Energy Limited has informed the Exchange about Schedule of meet",
                "https://nsearchives.nseindia.com/corporate/SELAN_22102026_Intimation_of_schedule_of_Earning_call.pdf"),
        _filing("2026-10-26T21:09", "Antelopus Selan Energy Limited has informed the Exchange about Link of Recording",
                "https://nsearchives.nseindia.com/corporate/SELAN_26102026210939_Audio_Recording_letter.pdf")]
    nse = [_filing("2026-10-08T10:00", "Announcement under Regulation 30 (LODR)-Analyst / Investor Meet - Intimation. Schedule of conference call",
                   "https://www.bseindia.com/xml-data/corpfiling/AttachLive/37b84fd4.pdf", subject="Analyst / Investor Meet")]
    for items in (antelopus, nse):
        got = deepdive.meetings(items, "2024-11-01T00:00")
        assert got["calls"] >= 1 and got["calls_due"] == 0, got
    # a recording past the grace days with no transcript: due, as before
    monkeypatch.setattr(deepdive, "ist_now", lambda: datetime(2026, 11, 10, 9, 0, tzinfo=IST))
    assert deepdive.meetings(antelopus, "2024-11-01T00:00")["calls_due"] == 1
    # and a notice whose call never brought a transcript, once older than any call is ahead of its notice
    monkeypatch.setattr(deepdive, "ist_now", lambda: datetime(2026, 12, 20, 9, 0, tzinfo=IST))
    assert deepdive.meetings(nse, "2024-11-01T00:00")["calls_due"] == 1
