"""Business updates read into numbers: finding them among real filings, reading real documents (redrawn as PDFs) with
the model's reply checked quote by quote, the series and its changes, the sector view, the job and alert, the routes."""
import json
import re
from datetime import datetime, timezone

import httpx
import pytest

from app import main  # noqa: F401,I001  (first: the app wires the modules)
from app import biz_updates as B, db, stock_alerts as sa
from app.config import settings
from app.docs import Docs
from tests import fake_biz as FB
from tests import world as W
from tests.fake_db import headers
from tests.pdfmaker import make_pdf_pages

ADVICE = re.compile(r"\b(buy|sell|accumulate|avoid|beat|miss|estimate[sd]?|expectations?|cheap|expensive)\b", re.I)
PROVIDERS = re.compile(r"kite|zerodha|yahoo|screener|finnhub|gemini|anthropic", re.I)


class Feed:
    def __init__(self, extra=None):
        self.extra, self.calls = extra or {}, 0

    def announcements(self, symbol, days=365):
        self.calls += 1
        return FB.announcements(symbol) + self.extra.get(symbol, [])


def docs_api(extra=None):
    return Docs(transport=FB.docs_transport(extra), check_host=lambda h: True, ocr=lambda d: "")


@pytest.fixture
def w(monkeypatch):
    world = W.build(monkeypatch)
    monkeypatch.setattr(B, "complete", FB.ai)
    feed = Feed()
    B.setup(lambda: feed, lambda: docs_api(), lambda: None)
    world["feed"] = feed
    yield world
    world["close"]()
    B.forget()
    B.setup(lambda: main.filings_feed, lambda: main.deep_docs, lambda: (None, None))


@pytest.fixture
def paid(monkeypatch):
    for k, v in (("RAZORPAY_KEY_ID", "rzp_live_x"), ("RAZORPAY_KEY_SECRET", "s"), ("RAZORPAY_PLAN_BASIC", "plan_b"), ("RAZORPAY_PLAN_PRO", "plan_p")):
        monkeypatch.setattr(settings, k, v)


# ---------- finding updates among real filings ----------
def test_finds_updates_in_real_filings():
    m = B.updates(FB.announcements("MARUTI"))
    titles = " ".join(u["title"] for u in m)
    assert "Production Volume: September 2026" in titles and "Maruti Suzuki sales in September 2026" in titles
    assert all("Transcript" not in u["title"] and "Schedule of meet" not in u["title"] for u in m)
    t = B.updates(FB.announcements("TVSMOTOR"))
    assert t and all("Monthly Business Updates" in u["title"] for u in t)
    h = B.updates(FB.announcements("HDFCBANK"))         # a generic subject: the file name says it
    assert [u["url"].rsplit("/", 1)[-1] for u in h][0] == "HDFCBANK_04102026220033_initial_Final_disclosure_Sep2026.pdf"
    assert len(h) == 4 and all(u["at"][5:7] in ("01", "04", "07", "10") for u in h)


def test_maybe_updates():
    pr = {"id": "1", "at": "2026-10-01T15:42", "subject": "Press Release", "text": "Please find enclosed a copy of the Press Release.",
          "url": "https://nsearchives.nseindia.com/corporate/HERO_PR.pdf"}
    assert not B.is_update(pr) and B.maybe_update(pr)
    assert not B.maybe_update({**pr, "at": "2026-10-15T10:00"})                     # mid-month: not a sales release
    assert not B.maybe_update({**pr, "subject": "Acquisition"})
    assert not B.is_update({**pr, "subject": "General Updates", "text": "Sale of equity shares of a subsidiary"})
    assert B.is_update({**pr, "text": 'titled "Tata Motors Limited Monthly Sales - August 2026"'})
    assert B.is_update({**pr, "subject": "General Updates", "text": "Production, Sales and Export figures for the month of August 2026"})


# ---------- reading a document ----------
def test_reads_real_documents_and_drops_unchecked_figures(w):
    d = docs_api()
    for sym, n in (("MARUTI", 3), ("TVSMOTOR", 2), ("HDFCBANK", 2)):
        item = next(u for u in B.updates(FB.announcements(sym)) if u["url"].endswith(FB.FILES[sym]))
        r = B.read_one(sym, item, d, None, [])
        assert r["problem"] is None and r["period"] == "2026-09", sym
        assert len(r["figures"]) == n, (sym, [f["metric"] for f in r["figures"]])
    m = B.read_one("MARUTI", next(u for u in B.updates(FB.announcements("MARUTI")) if u["url"].endswith(FB.FILES["MARUTI"])), d, None, [])
    names = [f["metric"] for f in m["figures"]]
    assert names == ["Total sales", "Domestic passenger vehicles", "Exports"]          # year to date, a wrong number, a made-up quote: gone
    tot = m["figures"][0]
    assert (tot["value"], tot["prior"], tot["page"], tot["headline"]) == (236013, 189665, 2, True)
    h = B.read_one("HDFCBANK", next(u for u in B.updates(FB.announcements("HDFCBANK")) if u["url"].endswith(FB.FILES["HDFCBANK"])), d, None, [])
    assert h["span"] == "quarter" and h["figures"][0]["unit"] == "₹ billion" and h["figures"][0]["basis"] == "period end"


def test_number_checks():
    assert B.number_in(236013, "Total Sales 236,013 189,665")
    assert B.number_in(1900000, "sales of 1.9 million units") and B.number_in(31872, "₹ 31,872 billion")
    assert not B.number_in(236014, "Total Sales 236,013") and not B.number_in(5, "no numbers")
    assert B._period("2026-09", "2026-10-01T12:00") == "2026-09"
    assert B._period("2026-11", "2026-10-01T12:00") is None and B._period("2020-01", "2026-10-01T12:00") is None
    assert B._period("Sept 2026", "2026-10-01") is None and B.shift("2026-01", -12) == "2025-01" and B.shift("2026-01", -1) == "2025-12"


def test_bad_replies_and_documents(w, monkeypatch):
    d = docs_api({"EMPTY.pdf": make_pdf_pages([[""]]), "NOTPDF.pdf": b"<html>busy</html>"})
    item = {"id": "x", "at": "2026-10-01T12:00", "title": "Monthly Business Updates", "url": "https://nsearchives.nseindia.com/corporate/EMPTY.pdf"}
    assert B.read_one("X", item, d, None, [])["problem"]
    assert "PDF" in B.read_one("X", {**item, "url": "https://nsearchives.nseindia.com/corporate/NOTPDF.pdf"}, d, None, [])["problem"]
    assert B.read_one("X", {**item, "url": "https://nsearchives.nseindia.com/corporate/GONE.pdf"}, d, None, [])["problem"]
    good = {**item, "url": "https://nsearchives.nseindia.com/corporate/" + FB.FILES["TVSMOTOR"]}
    for reply in ("not json", "[]", json.dumps({"period": "2026-09", "figures": "x"}), json.dumps({"period": None, "figures": []}),
                  json.dumps({"period": "2026-09", "figures": [None, 3, {"metric": "x", "value": "abc"}]})):
        monkeypatch.setattr(B, "complete", lambda *a, _r=reply, **k: _r)
        B.forget()
        r = B.read_one("TVSMOTOR", good, d, None, [])
        assert r["figures"] == [] and r["problem"], reply


def test_a_press_release_is_checked_before_it_counts(w):
    letter = make_pdf_pages([["Please find enclosed the press release on our new plant in Gujarat."]])
    sales = make_pdf_pages([["Cover letter"], ["Hero sold 6,87,220 units in September 2026 against 6,37,050 units in September 2025."]])
    rows = [{"id": "p1", "at": "2026-10-01T15:42", "subject": "Press Release", "text": "Press release", "url": "https://nsearchives.nseindia.com/corporate/HERO1.pdf"},
            {"id": "p2", "at": "2026-09-02T15:42", "subject": "Press Release", "text": "Press release", "url": "https://nsearchives.nseindia.com/corporate/HERO2.pdf"}]
    d = docs_api({"HERO1.pdf": sales, "HERO2.pdf": letter})
    got = B.read_new("HEROMOTOCO", rows, d, None)
    reads = B.stored("HEROMOTOCO")
    assert reads["p2"].get("skip") and not reads["p1"].get("skip") and got["read"] == 1
    v = B.view("HEROMOTOCO", rows, True)
    assert [f["id"] for f in v["filings"]] == ["p1"] and v["unread"] == 0


# ---------- the series ----------
def test_series_and_changes():
    reads = FB.sample_reads()
    ms = B.series(reads)
    tot = ms[0]
    assert tot["metric"] == "Total sales" and tot["headline"] and tot["latest"]["period"] == "2026-09" and tot["latest"]["value"] == 126000
    assert tot["prev"]["period"] == "2026-08" and tot["change_prev"] == round((126000 / 124000 - 1) * 100, 1)
    # the year-ago month has a filing of its own, which wins over the figure a later filing states for it
    assert tot["year_ago"] == {**tot["year_ago"], "period": "2025-09", "value": 102000, "filed_later": False}
    assert tot["change_year"] == round((126000 / 102000 - 1) * 100, 1)
    # before the first filing, the year-ago figures the filings state fill the chart
    assert tot["points"][0]["filed_later"] and tot["points"][0]["value"] == 93000
    assert len(tot["points"]) == B.CHART_MONTHS and tot["points"][0]["period"] == "2024-10"
    assert tot["step"] == "month"
    exp = next(m for m in ms if m["metric"] == "Exports")
    assert exp["change_year"] == round((23900 / 20300 - 1) * 100, 1) and exp["year_ago"]["value"] == 20300
    w = B.words(B.headline(ms))
    assert w.startswith("Total sales 1,26,000 units in Sep 2026: up ") and "on Sep 2025" in w and not ADVICE.search(w)
    assert B.change(30.5, 29.0, "%") == 1.5 and B.change(10, 0, "units") is None and B.change(None, 1, "x") is None
    assert B.fmt_value(33275, "₹ billion") == "₹33,275 billion" and B.fmt_value(34.25, "%") == "34.25%"
    assert B._month("2026-09", "quarter") == "Q2 FY27" and B._month("2027-03", "quarter") == "Q4 FY27"


def test_the_previous_period_is_the_period_just_before():
    """"On the previous" is last month's (or last quarter's) figure; a month with no figure, or a year-ago figure a filing states,
    is not it (R4-013: Maruti showed +24.4% on the previous beside a blank August)."""
    reads = {k: v for k, v in FB.sample_reads().items() if v.get("period") != "2026-08"}
    ms = B.series(reads)
    assert ms
    for m in ms:
        if m["prev"] is not None:
            gap = (int(m["latest"]["period"][:4]) * 12 + int(m["latest"]["period"][5:])) - (int(m["prev"]["period"][:4]) * 12 + int(m["prev"]["period"][5:]))
            assert gap == 1 or (m["step"] == "quarter" and gap == 3), (m["metric"], m["latest"]["period"], m["prev"]["period"])
        else:
            assert m["change_prev"] is None, m["metric"]
    assert ms[0]["latest"]["period"] == "2026-09" and ms[0]["prev"] is None and ms[0]["change_year"] is not None


def test_series_from_a_real_quarter(w):
    item = next(u for u in B.updates(FB.announcements("HDFCBANK")) if u["url"].endswith(FB.FILES["HDFCBANK"]))
    B.save("HDFCBANK", item["id"], B.read_one("HDFCBANK", item, docs_api(), None, []))
    ms = B.series(B.stored("HDFCBANK"))
    dep = ms[0]
    assert dep["metric"] == "Period-end deposits" and dep["change_year"] == 18.8 and dep["year_ago"]["filed_later"]
    assert B.words(dep) == "Period-end deposits ₹33,275 billion in Q2 FY27: up 18.8% on Q2 FY26"
    # only the year-ago figure is known: that is not "the previous" quarter, so there is no change on the previous (R4-013)
    assert dep["prev"] is None and dep["change_prev"] is None


# ---------- the routes ----------
def test_company_route_and_reading(w, paid):
    c = w["client"]
    r = c.get("/research/business-updates/MARUTI", headers=headers("free-token"))
    assert r.status_code == 200
    body = r.json()
    assert body["allowed"] is False and body["metrics"] == [] and body["unread"] >= 8 and body["filings"][0]["url"]
    assert c.post("/research/business-updates/MARUTI/read", headers=headers("free-token")).status_code == 402
    r = c.post("/research/business-updates/MARUTI/read", headers=headers("basic-token"))
    assert r.status_code == 200
    body = r.json()
    assert body["just_read"] >= 1 and body["metrics"][0]["metric"] == "Total sales"
    assert body["headline"] == "Total sales 2,36,013 units in Sep 2026: up 24.4% on Sep 2025"
    text = json.dumps(body)
    assert not PROVIDERS.search(text) and not ADVICE.search(body["note"] + body["headline"])
    # the free view lists the read filings with their months, without the numbers
    free = c.get("/research/business-updates/MARUTI", headers=headers("free-token")).json()
    assert free["metrics"] == [] and any(f["read"] for f in free["filings"])
    for bad in ("x" * 40, "A;B", "-x"):
        assert c.get(f"/research/business-updates/{bad}", headers=headers("free-token")).status_code in (400, 404)
    assert c.get("/research/business-updates/MARUTI").status_code == 401


def test_routes_when_sources_fail(w, paid, monkeypatch):
    c = w["client"]

    def down(*a, **k):
        from app.intel.net import SourceError
        raise SourceError("the exchange", "The exchange feed is busy (500).", busy=True)
    real = w["feed"].announcements
    w["feed"].announcements = down
    r = c.get("/research/business-updates/MARUTI", headers=headers("basic-token"))
    assert r.status_code == 200 and r.json()["problems"]
    assert c.post("/research/business-updates/MARUTI/read", headers=headers("basic-token")).status_code == 503
    w["feed"].announcements = real
    monkeypatch.setattr(B, "complete", lambda *a, **k: (_ for _ in ()).throw(B.AIError("The AI couldn't answer.")))
    r = c.post("/research/business-updates/TVSMOTOR/read", headers=headers("basic-token"))
    assert r.status_code == 200 and r.json()["just_read"] == 0 and r.json()["problems"]


def test_sector_route(w, paid):
    c = w["client"]
    assert c.get("/invest/business-updates", headers=headers("free-token")).status_code == 402
    assert c.get("/invest/business-updates?sector=nope", headers=headers("basic-token")).status_code == 404
    for sym in ("MARUTI", "TVSMOTOR"):
        item = next(u for u in B.updates(FB.announcements(sym)) if u["url"].endswith(FB.FILES[sym]))
        B.save(sym, item["id"], B.read_one(sym, item, docs_api(), None, []))
    r = c.get("/invest/business-updates?sector=autos", headers=headers("basic-token"))
    assert r.status_code == 200
    rows = r.json()["rows"]
    names = [x["name"] for x in rows]
    assert names == sorted(names, key=str.upper)                       # alphabetical, never ranked
    m = next(x for x in rows if x["symbol"] == "MARUTI")
    assert (m["value"], m["change_year"], m["period"]) == (236013, 24.4, "2026-09")
    assert next(x for x in rows if x["symbol"] == "TVSMOTOR")["change_year"] == 24.3
    assert next(x for x in rows if x["symbol"] == "ASHOKLEY")["value"] is None
    assert "alphabetically" in r.json()["note"]


# ---------- the job and the alert ----------
def test_alert_kind():
    a = sa.clean({"region": "IN", "symbol": "MARUTI", "kind": "bizupdate"})
    assert sa.describe(a) == "Files a monthly or quarterly business update"
    with pytest.raises(sa.AlertError):
        sa.clean({"region": "US", "symbol": "AAPL", "kind": "bizupdate"})


def test_alert_route_is_basic(w, paid, monkeypatch):
    monkeypatch.setattr(main, "alert_quotes", lambda r, s: {x: {"price": 100.0} for x in s})
    c = w["client"]
    body = {"region": "IN", "symbol": "MARUTI", "kind": "bizupdate"}
    assert c.post("/alerts", json=body, headers=headers("free-token")).status_code == 402
    r = c.post("/alerts", json=body, headers=headers("basic-token"))
    assert r.status_code == 200 and r.json()["alert"]["text"] == "Files a monthly or quarterly business update"


def test_job_reads_and_fires(w, monkeypatch):
    sa.create("u-basic", {"region": "IN", "symbol": "TVSMOTOR", "kind": "bizupdate"}, 10)
    sa.create("u-free", {"region": "IN", "symbol": "TVSMOTOR", "kind": "bizupdate"}, 10)
    rows = db.json_value(db.get_setting(sa.KEY + "u-basic"), {})
    for a in rows["items"]:
        a["created_at"] = "2026-09-01T00:00:00+00:00"
    db.set_setting(sa.KEY + "u-basic", json.dumps(rows))
    sent = []
    fire = lambda rs, now: sa.fire_events(rs, now, lambda p: 10, send=lambda p, s, t: sent.append((p["id"], t)) or ["push"],   # noqa: E731
                                          profile=lambda uid: {"id": uid}, kind_ok=lambda p, k: p["id"] != "u-free")
    job = B.Job(fire, B.alert_symbols)
    assert B.alert_symbols() == ["TVSMOTOR"]
    early = datetime(2026, 10, 2, 8, 0, tzinfo=timezone.utc)                 # 13:30 in India: not yet
    assert job.tick(early) is None
    now = datetime(2026, 10, 2, 14, 30, tzinfo=timezone.utc)                 # 20:00 in India
    out = job.tick(now)
    assert out["read"] >= 3 and B.stored("TVSMOTOR") and B.stored("MARUTI")
    assert [u for u, _ in sent] == ["u-basic"]
    assert sent[0][1].startswith("TVSMOTOR filed a business update: Total sales 6,72,790 units in Sep 2026: up 24.3% on Sep 2025")
    assert job.tick(now) is None                                             # once a day
    assert not ADVICE.search(sent[0][1])
