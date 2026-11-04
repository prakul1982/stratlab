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
    monkeypatch.setattr(kite_auto.os, "_exit", lambda code: exits.append(code))
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
    assert order == ["step done", "lease"] and exits == [3]
    assert memguard.TURNS.name == "restart after the Kite login"     # kept: nothing heavy starts before the exit
    assert memguard.TURNS.acquire("a later job", 0.05) is False
    memguard.TURNS._owner = memguard.TURNS.name = memguard.TURNS.since = None   # (this test's process goes on)
    memguard.TURNS._depth = 0
