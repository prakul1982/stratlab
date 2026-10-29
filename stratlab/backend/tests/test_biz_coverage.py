"""Business updates: the coverage audit, the 'looked through, none filed' mark, the category total, the series read API and the new
categories (RES-1 follow-up)."""
import json
from datetime import date, datetime, timezone

import pytest

from app import main  # noqa: F401,I001  (first: the app wires the modules)
from app import biz_updates as B, db
from app.config import settings
from tests import fake_biz as FB
from tests import world as W
from tests.fake_db import headers
from tests.test_biz_updates import Feed, docs_api

TODAY = date(2026, 10, 20)


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


def store(sym, months=14, end="2026-09", scale=1, drop_year_ago=False):
    """Made-up monthly updates stored for a company, the figures scaled."""
    for fid, r in FB.sample_reads(months, end).items():
        r = json.loads(json.dumps(r))
        for f in r["figures"]:
            f["value"] *= scale
            if f.get("prior"):
                f["prior"] = None if drop_year_ago else f["prior"] * scale
        B.save(sym, f"{sym}-{fid}", r)


def row_of(cov, cat, sym):
    return next(r for c in cov["categories"] if c["category"] == cat for r in c["rows"] if r["symbol"] == sym)


# ---------- the audit ----------
def test_the_audit_says_where_each_company_stands(w):
    store("MARUTI")                                                        # a figure for Sep 2026, filed 1 Oct
    store("TVSMOTOR", months=4, end="2026-02")                             # the newest figure is March's filing: months old
    B.mark_checked("ASHOKLEY", 0, datetime(2026, 10, 19, tzinfo=timezone.utc))        # looked through: no update among its filings
    B.mark_checked("HEROMOTOCO", 3, datetime(2026, 10, 19, tzinfo=timezone.utc))      # three updates found, none read yet
    cov = B.coverage(TODAY)
    assert cov["as_of"] == "2026-10-20" and cov["history"] == {"look_back_days": 800, "backfill_months": 25, "keep_reads": 60}
    m = row_of(cov, "autos", "MARUTI")
    assert (m["status"], m["last_period"], m["first_period"], m["periods"], m["newest_filed"], m["days_since_filed"]) == ("current", "2026-09", "2024-10", 24, "2026-10-01", 19)
    assert m["months_back"] == 24 and m["year_ago_filled"] is True and m["filings_read"] == 14 and m["with_figures"] == 14
    t = row_of(cov, "autos", "TVSMOTOR")
    assert t["status"] == "behind" and t["last_period"] == "2026-02" and t["days_since_filed"] > 50
    a, h, b = row_of(cov, "autos", "ASHOKLEY"), row_of(cov, "autos", "HEROMOTOCO"), row_of(cov, "autos", "BAJAJ-AUTO")
    assert (a["status"], a["filings_found"], a["filings_read"], a["last_period"]) == ("none_filed", 0, 0, None)
    assert (h["status"], h["filings_found"]) == ("reading", 3)
    assert b["status"] == "unchecked" and b["checked_at"] is None
    autos = next(c for c in cov["categories"] if c["category"] == "autos")
    assert (autos["current"], autos["behind"], autos["reading"], autos["none_filed"]) == (1, 1, 1, 1)
    assert autos["unchecked"] == autos["companies"] - 4 and autos["with_year_ago"] == 2 and autos["filings_read"] == 18
    assert "Current: the newest figure was filed within 50 days (monthly) or 130 days (quarterly)" in cov["rule"]


def test_a_quarterly_filer_is_current_for_longer(w):
    for fid, r in FB.sample_reads(8, "2026-06").items():
        r = json.loads(json.dumps(r))
        r["span"] = "quarter"
        r["at"] = "2026-07-12T12:00"
        B.save("TITAN", f"t{fid}", {**r, "period": {"s0": "2024-09", "s1": "2024-12", "s2": "2025-03", "s3": "2025-06", "s4": "2025-09", "s5": "2025-12", "s6": "2026-03", "s7": "2026-06"}[fid]})
    r = row_of(B.coverage(date(2026, 10, 20)), "retail", "TITAN")
    assert r["status"] == "current" and r["days_since_filed"] == 100                         # 12 July to 20 October: inside 130 days
    assert row_of(B.coverage(date(2026, 12, 1)), "retail", "TITAN")["status"] == "behind"


def test_the_job_notes_which_companies_were_looked_through(w):
    class Quiet(Feed):
        def announcements(self, symbol, days=365):
            return [] if symbol in ("ASHOKLEY", "ATULAUTO") else super().announcements(symbol, days)

    feed = Quiet()
    B.setup(lambda: feed, lambda: docs_api(), lambda: None)
    job = B.Job(lambda rows, now: 0, lambda: [])
    now = datetime(2026, 10, 2, 14, 30, tzinfo=timezone.utc)
    job.run(now)
    a, m = B.checked("ASHOKLEY"), B.checked("MARUTI")
    assert a == {"at": "2026-10-02T14:30:00+00:00", "found": 0} and m["found"] >= 2
    assert B.status_of("ASHOKLEY", B.stored("ASHOKLEY")) == "none_filed"
    assert B.status_of("MARUTI", B.stored("MARUTI")) == "read"
    # a read keeps the note
    B.save("ASHOKLEY", "x", {"at": "2026-10-01T10:00", "title": "t", "url": "https://x/y.pdf", "period": None, "figures": []})
    assert B.checked("ASHOKLEY")["found"] == 0


def test_the_sector_rows_carry_the_status_and_the_lists_have_more_filers(w, paid):
    B.mark_checked("ASHOKLEY", 0)
    r = w["client"].get("/invest/business-updates?sector=autos", headers=headers("basic-token")).json()
    status = {x["symbol"]: x["status"] for x in r["rows"]}
    assert status["ASHOKLEY"] == "none_filed" and status["MARUTI"] == "unchecked"
    assert {"VSTTILLERS", "SMLISUZU", "OLAELEC"} <= set(status)
    assert "realty" in B.SECTORS and {s for s, _ in B.SECTORS["realty"]["symbols"]} >= {"GODREJPROP", "LODHA", "PRESTIGE"}
    assert w["client"].get("/invest/business-updates?sector=realty", headers=headers("basic-token")).status_code == 200
    assert {"JSWINFRA"} <= {s for s, _ in B.SECTORS["airlines"]["symbols"]} and {"MOIL", "NATIONALUM"} <= {s for s, _ in B.SECTORS["metals"]["symbols"]}
    assert {"ICICIBANK", "AXISBANK"} <= {s for s, _ in B.SECTORS["lenders"]["symbols"]}
    names = [n for sec in B.SECTORS.values() for _, n in sec["symbols"]]
    assert len(names) == len(set(names)), "a company is on one list once"


# ---------- the category total ----------
def row(sym, value, unit="units", period="2026-09", ago=None):
    return {"symbol": sym, "name": sym.title(), "value": value, "unit": unit, "period": period, "points": [{"period": "2025-09", "value": ago}] if ago is not None else []}


def test_the_total_is_only_where_the_figures_add_up():
    rows = [row("A", 100, ago=80), row("B", 200, ago=150), row("C", 300, ago=270), row("D", None)]
    t = B.category_total(rows)
    assert t == {"period": "2026-09", "unit": "units", "value": 600, "companies": 3, "of": 3, "names": ["A", "B", "C"], "year_ago": 500, "change_year": 20.0}
    # one company's year-ago figure missing: the change would compare different companies
    t = B.category_total([row("A", 100, ago=80), row("B", 200), row("C", 300, ago=270)])
    assert t["value"] == 600 and t["year_ago"] is None and t["change_year"] is None
    assert B.category_total([row("A", 1), row("B", 2)]) is None                                   # two companies are not a total
    assert B.category_total([row("A", 10, "%"), row("B", 20, "%"), row("C", 30, "%")]) is None    # a percent is not summed
    mixed = B.category_total([row("A", 1, "units"), row("B", 2, "₹ crore"), row("C", 3, "units"), row("D", 4, "units")])
    assert mixed["unit"] == "units" and mixed["companies"] == 3 and mixed["of"] == 4              # only those in the same unit
    other = B.category_total([row("A", 1), row("B", 2), row("C", 3), row("D", 9, period="2026-08"), row("E", 9, period="2026-08"), row("F", 9, period="2026-08")])
    assert other["period"] == "2026-09" and other["companies"] == 3                                 # the newest period wins a tie


def test_the_sector_view_has_a_total_and_chart_points(w, paid):
    for sym, k in (("MARUTI", 3), ("TVSMOTOR", 2), ("HEROMOTOCO", 1), ("BAJAJ-AUTO", 1)):
        store(sym, scale=k)
    r = w["client"].get("/invest/business-updates?sector=autos", headers=headers("basic-token")).json()
    t = r["total"]
    assert t["companies"] == 4 and t["period"] == "2026-09" and t["unit"] == "units" and t["value"] == 126000 * (3 + 2 + 1 + 1) and t["change_year"] is not None
    assert r["months"] == 24
    m = next(x for x in r["rows"] if x["symbol"] == "MARUTI")
    assert len(m["points"]) == 24 and m["points"][-1] == {"period": "2026-09", "value": 378000.0}


# ---------- the read API ----------
def test_the_series_api_gives_category_company_series(w, paid):
    store("MARUTI", scale=3)
    store("TVSMOTOR", scale=2)
    c = w["client"]
    assert c.get("/invest/business-updates/series/autos", headers=headers("free-token")).status_code == 402
    assert c.get("/invest/business-updates/series/nope", headers=headers("basic-token")).status_code == 404
    assert c.get("/invest/business-updates/series/autos?symbol=TCS", headers=headers("basic-token")).status_code == 404       # not on that list
    assert c.get("/invest/business-updates/series/autos?symbol=%27%3Bdrop", headers=headers("basic-token")).status_code == 400
    assert c.get("/invest/business-updates/series/autos").status_code == 401
    r = c.get("/invest/business-updates/series/autos", headers=headers("basic-token"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["category"] == "autos" and body["span"] == "month" and body["months"] == 24 and body["total"] is None      # two companies: no total
    maruti = next(x for x in body["companies"] if x["symbol"] == "MARUTI")
    assert maruti["status"] == "read" and maruti["metric"] == "Total sales" and maruti["unit"] == "units" and maruti["step"] == "month"
    p = maruti["points"][-1]
    assert p["period"] == "2026-09" and p["value"] == 378000.0 and p["filed"] == "2026-10-01" and p["url"].endswith("SAMPLE_2026-09.pdf") and p["year_change"] is not None
    assert len(maruti["points"]) == 24 and maruti["points"][0]["period"] == "2024-10"
    ola = next(x for x in body["companies"] if x["symbol"] == "OLAELEC")
    assert ola == {"symbol": "OLAELEC", "name": "Ola Electric Mobility", "status": "unchecked", "metric": None, "unit": None, "step": None, "points": []}
    one = c.get("/invest/business-updates/series/autos?symbol=MARUTI&months=6&every=true", headers=headers("basic-token")).json()
    assert [x["symbol"] for x in one["companies"]] == ["MARUTI"] and len(one["companies"][0]["points"]) == 6 and one["companies"][0]["measures"][0]["metric"] == "Total sales"
    assert len(c.get("/invest/business-updates/series/autos?months=500", headers=headers("basic-token")).json()["companies"][0]["points"]) <= 24


def test_the_admin_audit_is_for_the_admin(w):
    c = w["client"]
    assert c.get("/admin/business-updates/coverage", headers=headers("basic-token")).status_code == 403
    r = c.get("/admin/business-updates/coverage", headers=headers("admin-token"))
    assert r.status_code == 200 and {x["category"] for x in r.json()["categories"]} == set(B.SECTORS) and "rule" in r.json()
