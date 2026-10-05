"""Named large shareholders: reading the shareholding-pattern XBRL (real samples, trimmed), names and matching, the
stored quarters and their changes, the search across companies, following a holder, the job and the routes."""
import json
import re
from datetime import date, datetime, timezone

import pytest

from app import main  # noqa: F401,I001  (first: the app wires the modules)
from app import db, shareholders as S
from app.config import settings
from tests import fake_shp as F
from tests import world as W
from tests.fake_db import headers

ADVICE = re.compile(r"\b(buy|sell|accumulate|avoid|superstar|smart money|best|top investor|cheap|expensive)\b", re.I)
PROVIDERS = re.compile(r"kite|zerodha|yahoo|screener|finnhub|trendlyne", re.I)


def doc(name: str) -> bytes:
    return (F.DIR / name).read_bytes()


@pytest.fixture
def w(monkeypatch):
    world = W.build(monkeypatch)
    monkeypatch.setattr(S, "PAUSE", 0)
    yield world
    world["close"]()
    S.forget()


@pytest.fixture
def paid(monkeypatch):
    for k, v in (("RAZORPAY_KEY_ID", "rzp_live_x"), ("RAZORPAY_KEY_SECRET", "s"), ("RAZORPAY_PLAN_BASIC", "plan_b"), ("RAZORPAY_PLAN_PRO", "plan_p")):
        monkeypatch.setattr(settings, k, v)


# ---------- the XBRL document ----------
def test_parse_named_holders():
    p = S.parse_xbrl(doc("XPROINDIA_2026-06-30.xml"))
    assert (p["symbol"], p["quarter"], p["isin"]) == ("XPROINDIA", "2026-06-30", "INE445C01015") or p["symbol"] == "XPROINDIA"
    by = {h["name"]: h for h in p["holders"]}
    assert by["Ashish Kacholia"] == {"name": "Ashish Kacholia", "kind": "Individual", "group": "public", "shares": 918550, "pct": 3.91}
    assert by["Ipro Capital Limited"]["group"] == "promoter" and by["Ipro Capital Limited"]["pct"] == 18.79
    assert by["Malabar India Fund Limited"]["kind"] == "Foreign direct investor"
    assert by["Meenakshi Apoorva Bajaj"]["kind"] == "Director or relative"
    # below 1% (promoter-group members with 0.65%, a fund parked with the investor protection fund) is left out
    assert "Sidharth Kumar Birla" not in by and not any("Investor Education" in n for n in by)
    assert all(h["pct"] >= 1 for h in p["holders"]) and len(p["holders"]) == 9
    assert [h["pct"] for h in p["holders"]] == sorted((h["pct"] for h in p["holders"]), reverse=True)


def test_parse_skips_category_rows_and_depositories():
    p = S.parse_xbrl(doc("HDFCBANK_2026-06-30.xml"))
    names = [h["name"] for h in p["holders"]]
    assert "SBI NIFTY 50 ETF" in names and "LIFE INSURANCE CORPORATION OF INDIA" in names
    assert "FII" not in names and "Foreign Banks" not in names               # category totals, not holders
    assert "JP MORGAN CHASE BANK, NA" not in names                            # the ADR depository
    kinds = {h["name"]: h["kind"] for h in p["holders"]}
    assert kinds["GOVERNMENT OF SINGAPORE"] == "Foreign portfolio investor" and kinds["SBI NIFTY 50 ETF"] == "Mutual fund"
    assert all(h["group"] == "public" for h in p["holders"])


def test_parse_safari_kinds():
    p = S.parse_xbrl(doc("SAFARI_2026-06-30.xml"))
    k = {h["name"]: (h["kind"], h["group"]) for h in p["holders"]}
    assert k["SUDHIR MOHANLAL JATIA"] == ("Individual or HUF", "promoter")
    assert k["Lighthouse India Fund Iv AIF"] == ("Alternative investment fund", "public")
    assert k["RAJEEV CHITRABHANU HUF"] == ("HUF", "public")
    assert k["Shalini Sanjay Jatia"] == ("Promoter's relative", "public")


def test_parse_refuses_bad_documents():
    for bad in (b"<!DOCTYPE x [<!ENTITY a 'b'>]><x>&a;</x>", b"not xml at all", b"<xbrl></xbrl>"):
        with pytest.raises(S.BadFiling):
            S.parse_xbrl(bad)


def test_parse_adds_up_a_holder_named_twice():
    xml = (b'<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance" xmlns:s="http://x/in-bse-shp" xmlns:xbrldi="http://xbrl.org/2006/xbrldi">'
           b'<xbrli:context id="MainI"/>'
           + b"".join(b'<xbrli:context id="%s"><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfSharesHeldByBodiesCorporateAxis">'
                      b'<s:D>x</s:D></xbrldi:typedMember></xbrli:scenario></xbrli:context>' % c for c in (b"A", b"D_A", b"B", b"D_B"))
           + b'<s:DateOfReport contextRef="MainI">2026-06-30</s:DateOfReport><s:Symbol contextRef="MainI">ABC</s:Symbol>'
           b'<s:NameOfTheShareholder contextRef="D_A">Long  Horizon\nFund Ltd</s:NameOfTheShareholder>'
           b'<s:NumberOfShares contextRef="A">600</s:NumberOfShares><s:ShareholdingAsAPercentageOfTotalNumberOfShares contextRef="A">0.006</s:ShareholdingAsAPercentageOfTotalNumberOfShares>'
           b'<s:NameOfTheShareholder contextRef="D_B">LONG HORIZON FUND LIMITED</s:NameOfTheShareholder>'
           b'<s:NumberOfShares contextRef="B">500</s:NumberOfShares><s:ShareholdingAsAPercentageOfTotalNumberOfShares contextRef="B">0.005</s:ShareholdingAsAPercentageOfTotalNumberOfShares>'
           b'</xbrli:xbrl>')
    p = S.parse_xbrl(xml)
    assert p["holders"] == [{"name": "Long Horizon Fund Ltd", "kind": "Company", "group": "public", "shares": 1100, "pct": 1.1}]


# ---------- names ----------
def test_names():
    assert S.norm("Mr. Ashish R. Kacholia") == "ASHISH R KACHOLIA"
    assert S.norm("HDFC Trustee Co. Ltd") == "HDFC TRUSTEE COMPANY LIMITED"
    assert S.norm("M/s. Safari Commercial LLP") == "SAFARI COMMERCIAL LLP"
    assert S.norm("R&D Holdings") == "R AND D HOLDINGS"
    assert S.alike("ASHISH KACHOLIA", "ASHISH RAMESHCHANDRA KACHOLIA")
    assert not S.alike("ASHISH KACHOLIA", "ASHISH KUMAR") and not S.alike("KACHOLIA", "KACHOLIA FAMILY")
    assert S.matches("kach", "ASHISH KACHOLIA") and S.matches("ashish kach", "ASHISH KACHOLIA")
    assert not S.matches("kacholia ltd", "ASHISH KACHOLIA") and not S.matches("", "X")


# ---------- the exchange's list ----------
def test_list_rows_and_revisions():
    rows = S.list_rows(json.loads((F.DIR / "list.json").read_text()))
    assert {r["symbol"] for r in rows} >= {"XPROINDIA", "SAFARI", "HDFCBANK", "MARUTI"}
    x = next(r for r in rows if r["symbol"] == "XPROINDIA" and r["quarter"] == "2026-06-30")
    assert x["filed"] == "2026-07-15T16:00" and x["url"].startswith("https://nsearchives.nseindia.com/") and x["name"]
    later = {**x, "filed": "2026-08-01T10:00", "rec": "rev"}
    assert S.latest_per_quarter([x, later])[("XPROINDIA", "2026-06-30")]["rec"] == "rev"
    # rows that don't point at the exchange's archive, or have no date, are left out
    assert S.list_rows([{"symbol": "ABC", "date": "30-JUN-2026", "xbrl": "https://evil.example/x.xml"},
                        {"symbol": "ABC", "date": "", "xbrl": "https://nsearchives.nseindia.com/a.xml"}, "junk", None]) == []
    assert S.list_rows({"weird": 1}) == []


# ---------- stored quarters and the company view ----------
def test_company_view_changes(w):
    F.seed()
    v = S.company_view("SAFARI")
    assert v["quarter"] == "2026-06-30" and v["prev_quarter"] == "2026-03-31" and v["name"].startswith("SAFARI")
    by = {h["name"]: h for h in v["holders"]}
    assert by["Ashish Kacholia"]["change"] == "same" and by["Ashish Kacholia"]["prev_pct"] == 1.84
    assert by["Invesco India Flexi Cap Fund"]["change"] == "new" and by["Invesco India Flexi Cap Fund"]["prev_pct"] is None
    assert by["Icici Prudential Flexicap Fund"]["change"] == "up" and by["Icici Prudential Flexicap Fund"]["pct_change"] == 0.81
    assert by["Shalini Sanjay Jatia"]["change"] == "down"
    assert "HSBC MUTUAL FUND - HSBC SMALL CAP FUND" in [d["name"] for d in v["dropped"]]
    assert v["holders"][0]["group"] == "promoter"                   # the promoter group first, then by stake
    assert not ADVICE.search(json.dumps(v)) and not PROVIDERS.search(json.dumps(v))
    one = S.company_view("HDFCBANK")
    assert one["prev_quarter"] is None and all(h["change"] is None for h in one["holders"]) and one["dropped"] == []
    assert S.company_view("NOPE") is None


def test_store_keeps_four_quarters_and_ignores_older_revisions(w):
    parsed = S.parse_xbrl(doc("XPROINDIA_2026-06-30.xml"))
    for q in ("2025-06-30", "2025-09-30", "2025-12-31", "2026-03-31", "2026-06-30"):
        S.store("XPROINDIA", {"quarter": q, "rec": q, "url": "u", "filed": q + "T10:00", "name": "X"}, parsed)
    assert sorted(S.company("XPROINDIA")["q"]) == ["2025-09-30", "2025-12-31", "2026-03-31", "2026-06-30"]
    before, now = S.store("XPROINDIA", {"quarter": "2026-06-30", "rec": "old", "url": "u", "filed": "2026-01-01T00:00", "name": "X"}, parsed)
    assert before is None and now["rec"] == "2026-06-30"             # the stored (newer) filing stays


# ---------- the search ----------
def test_search_and_holdings(w):
    F.seed()
    groups = S.search("kacholia")
    assert len(groups) == 1 and groups[0]["label"].upper() == "ASHISH KACHOLIA" and groups[0]["companies"] == 2
    assert [n["key"] for n in groups[0]["names"]] == ["ASHISH KACHOLIA"]
    h = S.holdings(["Ashish Kacholia"])
    assert [r["symbol"] for r in h["rows"]] == ["SAFARI", "XPROINDIA"]                # alphabetical by company
    assert [r["pct"] for r in h["rows"]] == [1.84, 3.91] and all(r["change"] == "same" for r in h["rows"])
    hsbc = S.holdings(["HSBC MUTUAL FUND - HSBC SMALL CAP FUND"])
    assert hsbc["rows"][0]["change"] == "dropped" and hsbc["rows"][0]["pct"] is None and hsbc["dropped"] == 1 and hsbc["count"] == 0
    inv = S.holdings(["Invesco India Flexi Cap Fund"])
    assert inv["rows"][0]["change"] == "new" and inv["new"] == 1
    assert S.search("zzzz") == []
    # spellings that look like one holder are grouped, and each can be picked on its own
    S.store("ABC", {"quarter": "2026-06-30", "rec": "r", "url": "u", "filed": "2026-07-01T10:00", "name": "Abc Ltd"},
            {"name": "Abc Ltd", "isin": "", "holders": [{"name": "ASHISH RAMESHCHANDRA KACHOLIA", "kind": "Individual", "group": "public",
                                                       "shares": 100, "pct": 1.5}]})
    g = S.search("kacholia")
    assert len(g) == 1 and {n["key"] for n in g[0]["names"]} == {"ASHISH KACHOLIA", "ASHISH RAMESHCHANDRA KACHOLIA"} and g[0]["companies"] == 3
    assert len(S.holdings(["ASHISH RAMESHCHANDRA KACHOLIA"])["rows"]) == 1


# ---------- following and the job ----------
def test_follow_and_unfollow(w):
    item = S.follow("u-basic", "Ashish Kacholia", ["Ashish Kacholia", "ashish kacholia", "ASHISH RAMESHCHANDRA KACHOLIA"])
    assert item["names"] == ["ASHISH KACHOLIA", "ASHISH RAMESHCHANDRA KACHOLIA"]
    again = S.follow("u-basic", "A. Kacholia", ["ASHISH RAMESHCHANDRA KACHOLIA", "Ashish Kacholia"])
    assert again["id"] == item["id"] and len(S.follows("u-basic")) == 1 and again["label"] == "A. Kacholia"
    with pytest.raises(ValueError):
        S.follow("u-basic", "x", ["   ", "!!"])
    assert S.unfollow("u-basic", item["id"]) and S.follows("u-basic") == [] and not S.unfollow("u-basic", item["id"])


def test_job_backfills_then_tells_followers(w, monkeypatch):
    sent = []
    job = S.Job(lambda: main.filings_feed, notify=lambda p, subject, text, url: sent.append((p["id"], text)),
                can_alert=lambda p: p["id"] != "u-free", sleep=lambda s: None)
    # the first run lists about two filing seasons and reads every company's two newest quarters, quietly
    S.follow("u-basic", "HSBC Small Cap Fund", ["HSBC MUTUAL FUND - HSBC SMALL CAP FUND"])
    now = datetime(2026, 10, 5, 16, 0, tzinfo=timezone.utc)                     # 21:30 in India
    assert job.tick(now) == 5
    assert sorted(S.company("SAFARI")["q"]) == ["2026-03-31", "2026-06-30"] and S.company("HDFCBANK")["q"]
    assert sent == [] and db.json_value(db.get_setting(S.STATE_KEY), {})["queue"] == []
    assert job.tick(now) == 0 and not db.json_value(db.get_setting(S.STATE_KEY), {}).get("filling")
    # a new quarter later: the June filing read again as if it were new tells the follower what changed
    st = db.json_value(db.get_setting(S.STATE_KEY), {})
    co = json.loads(db.get_setting(S.KEY + "SAFARI"))
    del co["q"]["2026-06-30"]
    db.set_setting(S.KEY + "SAFARI", json.dumps(co))
    S.forget()
    S.follow("u-free", "HSBC Small Cap Fund", ["HSBC MUTUAL FUND - HSBC SMALL CAP FUND"])     # a free user isn't told
    row = next(r for r in S.list_rows(F.rows()) if r["symbol"] == "SAFARI" and r["quarter"] == "2026-06-30")
    S.enqueue([row], st)
    S._save_state(st)
    assert job.read_queue() == 1
    assert [u for u, _ in sent] == ["u-basic"]
    text = sent[0][1]
    assert "HSBC Small Cap Fund: no longer listed above 1% in SAFARI INDUSTRIES (INDIA) LIMITED (SAFARI), was 4.41%" in text
    assert "quarter to 30 Jun 2026" in text and not ADVICE.search(text) and not PROVIDERS.search(text)


def test_change_lines():
    assert S.change_line("X", "Co", "CO", None, {"pct": 1.5, "shares": 10}, "2026-06-30") == "X: new in Co (CO) at 1.50% (quarter to 30 Jun 2026)"
    assert "up in Co (CO) from 1.20% to 1.50%" in S.change_line("X", "Co", "CO", {"pct": 1.2, "shares": 8}, {"pct": 1.5, "shares": 10}, "2026-06-30")
    assert "down in" in S.change_line("X", "Co", "CO", {"pct": 1.5, "shares": 10}, {"pct": 1.2, "shares": 8}, "2026-06-30")
    assert S.change_line("X", "Co", "CO", {"pct": 1.5, "shares": 10}, {"pct": 1.5, "shares": 10}, "2026-06-30") is None


def test_job_waits_when_the_archive_refuses(w):
    st = {"backfilled": True, "listed_to": date.today().isoformat(), "queue": []}
    S.enqueue(S.list_rows(F.rows()), st)
    S._save_state(st)
    w["faults"]["exchange"].mode = "403"
    job = S.Job(lambda: main.filings_feed, notify=lambda *a: None, can_alert=lambda p: True, sleep=lambda s: None)
    assert job.read_queue() == 0 and job.status["last_error"]
    assert len(db.json_value(db.get_setting(S.STATE_KEY), {})["queue"]) == 5                  # kept for the next tick
    w["faults"]["exchange"].mode = None
    assert job.read_queue() == 5


# ---------- the routes ----------
def test_company_route_reads_on_demand(w):
    c = w["client"]
    r = c.get("/research/holders/xproindia", headers=headers("free-token"))
    assert r.status_code == 200
    body = r.json()
    assert body["quarter"] == "2026-06-30" and body["prev_quarter"] == "2026-03-31" and len(body["holders"]) == 9 and "search" in body
    assert "above 1%" in body["note"]
    assert c.get("/research/holders/RELIANCE", headers=headers("free-token")).status_code == 404
    for bad in ("x" * 40, "A;B", "..", "-x"):
        assert c.get(f"/research/holders/{bad}", headers=headers("free-token")).status_code in (400, 404)
    assert c.get("/research/holders/SAFARI").status_code == 401


def test_company_route_when_the_exchange_is_down(w):
    w["faults"]["exchange"].mode = "500"
    r = w["client"].get("/research/holders/SAFARI", headers=headers("free-token"))
    assert r.status_code == 503 and r.json()["detail"]["code"] == "holders_unavailable"
    w["faults"]["exchange"].mode = None
    F.seed()
    S.forget()
    w["faults"]["exchange"].mode = "500"           # stored already: the page still answers
    assert w["client"].get("/research/holders/SAFARI", headers=headers("free-token")).status_code == 200


def test_search_routes_and_plan_gate(w, paid):
    F.seed()
    c = w["client"]
    r = c.get("/invest/holders", params={"q": "kacholia"}, headers=headers("free-token"))
    assert r.status_code == 402 and r.json()["detail"]["code"] == "upgrade_required"
    r = c.get("/invest/holders", params={"q": "kacholia"}, headers=headers("basic-token"))
    assert r.status_code == 200
    body = r.json()
    assert body["groups"][0]["companies"] == 2 and body["coverage"]["companies"] == 3 and body["coverage"]["latest_quarter"] == "2026-06-30"
    assert c.get("/invest/holders", params={"q": "ab"}, headers=headers("basic-token")).status_code == 400
    assert c.get("/invest/holders", headers=headers("basic-token")).json()["groups"] == []
    r = c.post("/invest/holders/holdings", json={"names": ["ASHISH KACHOLIA"]}, headers=headers("basic-token"))
    assert r.status_code == 200 and [x["symbol"] for x in r.json()["rows"]] == ["SAFARI", "XPROINDIA"]
    for bad in ({"names": []}, {"names": ["!!"]}, {}, {"names": "x"}, {"names": ["a"] * 20}):
        assert c.post("/invest/holders/holdings", json=bad, headers=headers("basic-token")).status_code in (400, 422)
    assert c.post("/invest/holders/holdings", json={"names": ["X Y"]}, headers=headers("free-token")).status_code == 402
    r = c.put("/invest/holders/follow", json={"label": "Ashish Kacholia", "names": ["ASHISH KACHOLIA"]}, headers=headers("basic-token"))
    assert r.status_code == 200 and len(r.json()["follows"]) == 1
    fid = r.json()["item"]["id"]
    assert c.put("/invest/holders/follow", json={"label": "x", "names": ["ASHISH KACHOLIA"]}, headers=headers("free-token")).status_code == 402
    assert c.put("/invest/holders/follow", json={"label": "x", "names": ["!!"]}, headers=headers("basic-token")).status_code == 400
    assert c.put("/invest/holders/follow", json={"label": "", "names": []}, headers=headers("basic-token")).status_code == 422
    assert c.delete("/invest/holders/follow/zz;", headers=headers("basic-token")).status_code == 404
    assert c.delete(f"/invest/holders/follow/{fid}", headers=headers("basic-token")).json()["follows"] == []
    assert c.delete(f"/invest/holders/follow/{fid}", headers=headers("basic-token")).status_code == 404
    text = json.dumps(body)
    assert not ADVICE.search(text) and not PROVIDERS.search(text)
