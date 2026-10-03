"""Deals and insider trades from exchange disclosures: reading each feed (and surviving one that is down or changes
shape), a company's table, the India checklist's insider line, the alerts on insider trades and bulk or block deals,
the screens' "a promoter or insider bought" filter, the evening job and the My Stocks newsletter's lines."""
import json
import re
from datetime import date, datetime, timedelta, timezone

import httpx
import pytest

from app import checklist, db, deals, main, screens, stock_alerts as sa
from app.intel import filings as F
from app.intel.net import SourceError
from tests import world as W
from tests.fake_db import headers

PROVIDERS = re.compile(r"kite|zerodha|yahoo|screener|finnhub|edgar|nseindia|bseindia", re.I)
ADVICE = re.compile(r"\b(buy|sell|hold|accumulate|avoid|signal|smart money|bullish|bearish)\b", re.I)
TODAY = date.today()


def ago(days: int) -> str:
    return (TODAY - timedelta(days=days)).isoformat()


@pytest.fixture
def w(monkeypatch):
    world = W.build(monkeypatch)
    deals._cache.clear()
    screens._mem.clear()
    yield world
    world["close"]()
    deals._cache.clear()
    screens._mem.clear()


def all_rows():
    raw = W.deal_rows()
    return F.sort_deals(F.insider_rows(raw["pit"]) + F.sast_rows(raw["sast"]) + F.block_rows(raw["bulk_deals"], "bulk")
                        + F.block_rows(raw["block_deals"], "block"))


# ---------- reading the feeds ----------
def test_insider_disclosures_become_plain_rows():
    rows = F.insider_rows(W.deal_rows()["pit"])
    assert len(rows) == 4                                       # the warrants row is left out
    by_who = {(d["who"], d["side"]): d for d in rows}
    buy = by_who[("Mukesh Shah Family Trust", "bought")]
    assert buy == {**buy, "kind": "insider", "symbol": "RELIANCE", "date": ago(20), "filed": ago(18), "relation": "promoter",
                   "mode": "market", "qty": 25000.0, "value": 72500000.0, "price": 2900.0, "pct_after": 50.12,
                   "url": "https://nsearchives.nseindia.com/corporate/xbrl/PIT_1.xml"}
    sale = by_who[("Asha Rao", "sold")]
    assert sale["relation"] == "director" and sale["mode"] == "market" and sale["url"] == F.DEAL_PAGES["insider"]
    pledge = by_who[("Mukesh Shah Family Trust", "pledged")]
    assert pledge["mode"] == "pledge" and pledge["value"] is None
    esop = by_who[("Ravi Kumar", "bought")]
    assert esop["mode"] == "esop" and esop["relation"] == "employee" and esop["value"] is None


def test_sast_bulk_and_block_rows():
    raw = W.deal_rows()
    s = F.sast_rows(raw["sast"])[0]
    assert (s["who"], s["side"], s["qty"], s["mode"], s["pct_after"], s["date"]) == ("Long Horizon Fund", "bought", 1500000.0, "market", 5.02, ago(30))
    b = F.block_rows(raw["bulk_deals"], "bulk")[0]
    assert (b["kind"], b["side"], b["qty"], b["price"], b["value"]) == ("bulk", "bought", 800000.0, 2901.5, 2321200000.0)
    k = F.block_rows(raw["block_deals"], "block")[0]
    assert (k["kind"], k["side"], k["label"]) == ("block", "sold", "Block deal")


@pytest.mark.parametrize("raw", [None, "junk", 12, {}, [None, 1, "x", [], {}], [{"symbol": "X"}], [{"acqName": "A", "tdpTransactionType": "Buy"}],
                                 [{"symbol": "X", "acqName": "A", "tdpTransactionType": "Gift?", "acqtoDt": "01-Oct-2026"}],
                                 [{"symbol": "X", "acqName": "A", "tdpTransactionType": "Buy", "acqtoDt": "not a date"}],
                                 [{"symbol": {"a": 1}, "acqName": ["x"], "tdpTransactionType": 5, "secAcq": {"n": 1}, "acqtoDt": None}]])
def test_odd_rows_are_dropped_not_crashed_on(raw):
    for read in (F.insider_rows, F.sast_rows, lambda r: F.block_rows(r, "bulk")):
        assert read(raw) == []


def test_numbers_and_dates_as_the_exchange_writes_them():
    row = {"symbol": "abc", "ACQNAME": "  A   B  ", "TDPTRANSACTIONTYPE": "Sell", "SECACQ": "1,23,456", "SECVAL": "NaN",
           "ACQMODE": "Market Sale", "ACQTODT": "2026-09-30 18:00:00", "xbrl": "javascript:alert(1)"}
    d = F.insider_rows([row])[0]
    assert (d["symbol"], d["who"], d["qty"], d["value"], d["date"]) == ("ABC", "A B", 123456.0, None, "2026-09-30")
    assert d["url"] == F.DEAL_PAGES["insider"]                 # never a link that isn't https


def transport(answers: dict, calls: list):
    """The exchange: a home page that sets a cookie, then each deal path's queued answers in turn."""
    def handler(req: httpx.Request):
        calls.append((req.url.path, dict(req.url.params)))
        if req.url.path == "/":
            return httpx.Response(200, text="<html></html>", headers={"set-cookie": "nsit=abc; Path=/"})
        key = req.url.params.get("optionType") or req.url.path
        got = answers.get(key)
        if isinstance(got, list) and got and isinstance(got[0], tuple):
            status, body = got.pop(0) if len(got) > 1 else got[0]
        else:
            status, body = 200, got
        if isinstance(body, str):
            return httpx.Response(status, text=body)
        return httpx.Response(status, json=body)
    return httpx.MockTransport(handler)


def test_client_asks_per_company_and_caches():
    calls = []
    raw = W.deal_rows()
    feed = F.NSEFilings(transport=transport({"/api/corporates-pit": {"data": raw["pit"]}, "bulk_deals": raw["bulk_deals"]}, calls))
    got = feed.insider_trades("RELIANCE")
    assert len(got) == 4 and got[0]["date"] >= got[-1]["date"]
    path, params = calls[-1]
    assert path == "/api/corporates-pit" and params["symbol"] == "RELIANCE" and params["index"] == "equities"
    assert set(params) >= {"from_date", "to_date"}
    assert feed.insider_trades("RELIANCE") == got and len(calls) == 2           # cached
    assert feed.bulk_deals("RELIANCE")[0]["who"] == "Index Fund One"            # a bare list is read too
    assert calls[-1][1]["optionType"] == "bulk_deals" and "from" in calls[-1][1]


@pytest.mark.parametrize("answer,busy", [((200, "<html>Access Denied</html>"), True), ((200, {"rows": []}), False),
                                         ((200, {"data": "x"}), False), ((503, "{}"), True), ((404, "{}"), False)])
def test_a_feed_that_is_down_or_changed_shape_is_a_clear_error(answer, busy):
    feed = F.NSEFilings(transport=transport({"/api/corporate-sast-reg29": [answer]}, []))
    with pytest.raises(SourceError) as e:
        feed.sast("RELIANCE")
    assert e.value.busy == busy and not PROVIDERS.search(str(e.value))


def test_a_broken_deal_feed_does_not_take_the_filings_down():
    calls = []
    feed = F.NSEFilings(transport=transport({"/api/corporates-pit": [(200, "<html>blocked</html>")],
                                             "/api/corporate-announcements": [{"data": []}]}, calls))
    for _ in range(4):
        with pytest.raises(SourceError):
            feed.insider_trades("RELIANCE", days=30 + _)                       # a new window each time: no cache
    assert feed.announcements("RELIANCE") == []                                # the filings' own breaker never tripped
    with pytest.raises(SourceError, match="isn't answering"):
        feed.insider_trades("RELIANCE", days=99)                               # the insider feed's own breaker did


def test_report_lists_every_kind_and_names_the_ones_that_are_down(w):
    rep = deals.report(main.filings_feed, "RELIANCE")
    assert {d["kind"] for d in rep["items"]} == {"insider", "sast", "bulk", "block"} and rep["problems"] == []
    assert rep["flow"]["bought"] == 25000 and rep["flow"]["sold"] == 4000 and rep["source"] == "exchange disclosures"
    w["faults"]["exchange"].mode = "down"
    main.filings_feed.nse.cache.clear()
    main.filings_feed.nse._circuits.clear()
    with pytest.raises(SourceError):
        deals.report(main.filings_feed, "RELIANCE")


def test_report_survives_one_feed_down():
    class Feed:
        def insider_trades(self, s, days=365, to=None):
            return all_rows()[:2]

        def sast(self, s, days=365, to=None):
            raise SourceError("the exchange", "busy", busy=True)
        bulk_deals = block_deals = sast
    rep = deals.report(Feed(), "RELIANCE")
    assert len(rep["items"]) == 2 and rep["problems"] == ["Substantial acquisition", "Bulk deal", "Block deal"]


def test_bse_only_companies_say_so(w, monkeypatch):
    monkeypatch.setattr(main, "bse_code", lambda s: "500001" if s == "BSEONLY" else None)
    with pytest.raises(SourceError, match="listed only on BSE"):
        main.filings_feed.insider_trades("BSEONLY")


# ---------- wording ----------
def test_sentences_are_facts_without_advice_or_provider_names():
    texts = [deals.describe(d) for d in all_rows()]
    assert any(t.startswith("Insider trade: Promoter Mukesh Shah Family Trust bought 25,000 shares on the open market (₹7.2 crore)") for t in texts)
    assert any("Block deal: Pension Plan Two sold 1,20,000 shares at ₹2,895.00" in t for t in texts)
    assert any("pledged 1,00,000 shares" in t for t in texts)
    for t in texts + [deals.flow_text(deals.flow(all_rows()))]:
        assert not ADVICE.search(t) and not PROVIDERS.search(t), t
    assert deals.flow_text(deals.flow(all_rows())) == "1 person bought 25,000 shares (₹7.2 crore) · 1 person sold 4,000 shares (₹1.2 crore)"
    assert deals.rupees(48000) == "₹48,000" and deals.rupees(3_500_000) == "₹35.0 lakh"


def test_flow_counts_only_open_market_trades_in_the_window():
    rows = all_rows()
    assert deals.flow(rows, days=30) == {"bought": 25000.0, "sold": 0.0, "bought_value": 72500000.0, "sold_value": 0.0,
                                         "buyers": 1, "sellers": 0, "days": 30}
    assert deals.flow([d for d in rows if d["mode"] != "market"]) is None
    assert deals.flow([], days=180) is None


# ---------- the checklist ----------
def checks(trades):
    p = {"name": "Reliance", "shareholding": None}
    out = checklist.evaluate(p, {"growth": {}, "years": [], "quarters": []}, None, None, None, "RELIANCE", trades)
    return [c for c in out["checks"] if c["group"] == "Insiders"]


def test_india_checklist_has_a_factual_insider_line():
    line = checks(all_rows())[0]
    assert line["label"] == "Promoter and insider buying and selling, 6 months" and line["state"] == "pass"
    assert line["value"].startswith("1 person bought 25,000 shares")
    sold = checks([d for d in all_rows() if d["side"] != "bought"])[0]
    assert sold["state"] == "watch" and "sold 4,000" in sold["value"]
    assert checks([])[0]["state"] == "na" and checks(None) == []
    for c in checks(all_rows()):
        assert not PROVIDERS.search(c["rule"] + c["value"])


def test_deep_dive_and_investor_home_show_the_line(w):
    c, h = w["client"], headers("pro-token")
    v = c.get("/research/deep/RELIANCE", headers=h).json()
    line = next(x for x in v["checklist"]["checks"] if x["group"] == "Insiders")
    assert line["state"] == "pass" and "bought 25,000" in line["value"]


# ---------- the endpoint ----------
def test_deals_endpoint(w):
    c = w["client"]
    assert c.get("/research/deals/RELIANCE").status_code == 401
    r = c.get("/research/deals/RELIANCE", headers=headers("free-token"))
    assert r.status_code == 200
    out = r.json()
    assert out["count"] == 7 and out["items"][0]["date"] >= out["items"][-1]["date"]
    assert out["flow_text"].startswith("1 person bought") and not PROVIDERS.search(json.dumps(out["flow_text"]))
    assert c.get("/research/deals/..%2F..", headers=headers("free-token")).status_code in (400, 404)
    assert c.get("/research/deals/" + "A" * 40, headers=headers("free-token")).status_code == 400
    w["faults"]["exchange"].mode = "down"
    main.filings_feed.nse.cache.clear()
    assert c.get("/research/deals/RELIANCE", headers=headers("free-token")).status_code in (502, 503)


# ---------- alerts ----------
def ev_alert(kind="insider", created=None, **kw):
    a = sa.clean({"region": "IN", "symbol": "RELIANCE", "kind": kind, **kw})
    return {**a, "id": "e1", "status": "active", "rev": 1, "state": {}, "created_at": created or f"{ago(60)}T00:00:00+00:00"}


def test_alert_kinds_are_india_only_and_described():
    assert sa.describe(ev_alert("insider")) == "A promoter or insider trade is disclosed"
    assert sa.describe(ev_alert("deal")) == "A bulk or block deal is reported"
    with pytest.raises(sa.AlertError, match="Indian stocks"):
        sa.clean({"region": "US", "symbol": "AAPL", "kind": "deal"})


def test_event_alert_fires_once_per_new_disclosure():
    rows = all_rows()
    text, st = sa.evaluate_event(ev_alert("deal"), rows)
    assert text.startswith("RELIANCE: Block deal: Pension Plan Two sold") and "and 1 more" in text and len(st["seen"]) == 2
    assert not ADVICE.search(text) and not PROVIDERS.search(text)
    again, _ = sa.evaluate_event({**ev_alert("deal"), "state": st}, rows)
    assert again is None
    text, st = sa.evaluate_event(ev_alert("insider"), rows)
    assert len(st["seen"]) == 5                                               # insider trades and the substantial acquisition
    late, _ = sa.evaluate_event(ev_alert("insider", created=f"{ago(1)}T00:00:00+00:00"), rows)
    assert late is None                                                       # filed before the alert was set


def test_fire_events_sends_within_limits_and_minute_checker_skips_them(w):
    sent = []
    a = sa.create("u-pro", {"region": "IN", "symbol": "RELIANCE", "kind": "insider"}, 10)
    sa.create("u-pro", {"region": "IN", "symbol": "TCS", "kind": "deal"}, 10)
    row = json.loads(db.get_setting(sa.KEY + "u-pro"))
    for x in row["items"]:
        x["created_at"] = f"{ago(90)}T00:00:00+00:00"
    db.set_setting(sa.KEY + "u-pro", json.dumps(row))
    now = datetime.now(timezone.utc)
    n = sa.fire_events(all_rows(), now, lambda p: 10, send=lambda p, s, t: sent.append((s, t)) or ["push"])
    assert n == 1 and "RELIANCE: " in sent[0][1] and "Facts, not advice" in sent[0][1]
    items = {x["symbol"]: x for x in sa.items("u-pro")}
    assert items["RELIANCE"]["status"] == "triggered" and items["TCS"]["status"] == "active"
    assert sa.fire_events(all_rows(), now, lambda p: 10, send=lambda p, s, t: sent.append(s) or ["push"]) == 0
    seen = []
    checker = sa.Checker(lambda r, s: seen.append(s) or {}, lambda r, s: [], lambda p: 10, send=lambda *x: ["push"])
    checker.tick(datetime(2026, 10, 1, 6, 0, tzinfo=timezone.utc))
    assert seen == [] and a["kind"] == "insider"                              # no quotes asked for deal alerts


def test_alert_endpoint_accepts_the_new_kinds(w):
    c, h = w["client"], headers("pro-token")
    r = c.post("/alerts", headers=h, json={"region": "IN", "symbol": "RELIANCE", "kind": "deal"})
    assert r.status_code == 200 and r.json()["alert"]["text"] == "A bulk or block deal is reported"
    r = c.post("/alerts", headers=h, json={"region": "US", "symbol": "AAPL", "kind": "insider"})
    assert r.status_code == 400 and "Indian" in r.json()["detail"]["message"]


# ---------- the evening job, the screens and the newsletter ----------
def test_evening_job_stores_days_buys_and_fires_alerts(w):
    fired = []
    job = deals.Job(lambda: main.filings_feed, lambda rows, now: fired.append(len(rows)) or 1)
    evening = datetime.combine(TODAY, datetime.min.time()).replace(hour=21, tzinfo=F.IST)
    assert job.tick(evening) == 1 and fired == [7]
    assert job.tick(evening) == 0 and fired == [7]                            # once a day
    st = deals.buys_state()
    assert st["buys"] == {"RELIANCE": ago(20)} and st["to"] == TODAY.isoformat()
    kept = db.json_value(db.get_setting(deals.DAY_KEY + ago(9)), [])
    assert [d["who"] for d in kept] == ["Ravi Kumar"]
    assert db.get_setting(deals.DAY_KEY + ago(18)) is None                    # past the days kept for the newsletter
    assert [d["kind"] for d in deals.recent_for("RELIANCE", ago(5))] == ["block"]
    assert deals.recent_for("RELIANCE", "junk") == [] and deals.recent_for("TCS", ago(9)) == []


def test_backfill_fills_a_year_a_month_at_a_time(w):
    steps = 0
    while deals.backfill_step(main.filings_feed, TODAY):
        steps += 1
        assert steps < 20
    st = deals.buys_state()
    assert steps == 13 and st["from"] <= ago(365) and st["buys"]["RELIANCE"] == ago(20)


def test_screen_filter_on_promoter_or_insider_buying(w):
    from tests.test_screens import store_pages
    store_pages()
    deals.note_buys([d for d in all_rows()], TODAY - timedelta(days=365), TODAY)
    idx = screens.build_index("IN")
    assert {r["symbol"]: r.get("insider_buy_at") for r in idx["rows"]}["RELIANCE"] == ago(20)
    run = lambda f: [r["symbol"] for r in screens.run("IN", f, index=idx)["rows"]]     # noqa: E731
    assert run({"insider_buy": "yes"}) == ["RELIANCE"]
    assert run({"insider_buy": "yes", "insider_days": 30}) == ["RELIANCE"]
    deals.note_buys([], TODAY, TODAY)
    old = [{**r, "insider_buy_at": ago(100)} if r["symbol"] == "RELIANCE" else r for r in idx["rows"]]
    assert [r["symbol"] for r in screens.run("IN", {"insider_buy": "yes"}, index={**idx, "rows": old})["rows"]] == []
    assert "RELIANCE" in [r["symbol"] for r in screens.run("IN", {"insider_buy": "yes", "insider_days": 180}, index={**idx, "rows": old})["rows"]]
    assert "RELIANCE" not in run({"insider_buy": "no"}) and len(run({"insider_buy": "no"})) == 3
    with pytest.raises(screens.ScreenError):
        screens.clean("IN", {"insider_buy": "maybe"})
    with pytest.raises(screens.ScreenError):
        screens.clean("IN", {"insider_buy": "yes", "insider_days": 7})
    assert screens.clean("US", {"insider_buy": "yes"})["insider_buy"] is None
    f = screens.clean("IN", {"insider_buy": "yes", "insider_days": 180})
    assert screens.describe("IN", f) == ["A promoter or insider bought on the open market in the last 180 days"]
    meta = screens.meta("IN")
    assert meta["insider"]["days"] == [30, 90, 180, 365] and "insider_buy" in meta["help"]
    assert screens.meta("US")["insider"] is None
    assert not PROVIDERS.search(meta["help"]["insider_buy"]) and not ADVICE.search(meta["help"]["insider_buy"])


def test_newsletter_lists_new_deals_for_the_users_stocks(w):
    from app.newsletter import write
    deals.store_days(all_rows(), TODAY)
    r = {"symbol": "RELIANCE", "price": 100.0, "change_pct": 0.5, "stage": 2, "deals": [
        {"text": deals.describe(d), "url": d["url"]} for d in deals.recent_for("RELIANCE", ago(4))]}
    lines = write.stock_lines(r, ago(4))
    assert any(ln["text"].startswith("New disclosure. Block deal: Pension Plan Two sold") for ln in lines)
    f = {"kind": "my_stocks", "weekly": False, "stocks": [r], "results": []}
    assert "1 new deal or insider trade disclosed." in write.template(f)
    for ln in lines:
        assert not ADVICE.search(ln["text"]) and not PROVIDERS.search(ln["text"])
