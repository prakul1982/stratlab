"""IPOs: no issue falls between two lists (IPO-001 to IPO-003). Saved real answers of 25 Oct 2026: NSE's upcoming, open and past lists and
Jio Platforms' own issue page (JPL), SEBI's draft list (all 13 pages the backfill reads) and red herring list, EDGAR's final prospectuses
of the last 30 days and the filing lists of the companies among them. On that day Jio Platforms (closed 23 Oct, listing 28 Oct) was on none
of NSE's three lists nor BSE's (the lists drop an issue when it closes, and NSE's past list takes it up after allotment), and its draft of
19 Jun is on page 6 of SEBI's 91."""
import gzip
import json
from datetime import timedelta

import httpx
import pytest

from app import db, ipo as I
from app.intel import ipo_sources as S
from app.intel.net import SourceError
from tests import fake_ipo as F
from tests.fake_db import headers
from tests.test_ipo import NOW, TODAY, at, by_id, w  # noqa: F401  (the fake world and its clock)


def job_read(w, now=NOW, past="nse_past_full.json", market="IN"):
    w["feed"].nse.past = past
    job = I.Job(sleep=lambda s: None)
    job.read(market, now)
    return job


def jio(rows):
    got = [r for r in rows if r.get("nkey") == "jioplatforms"]
    assert len(got) == 1, [r["id"] for r in got]                      # one row for the company, never a filing row beside its issue row
    return got[0]


# ---------- the cause: an issue between its close and its listing ----------
def test_on_25_oct_no_exchange_list_has_jio_platforms_but_its_issue_page_and_sebi_do(w):
    nse = w["feed"].nse
    for what in (S.nse_upcoming(nse.ipo_upcoming()), S.nse_current(nse.ipo_current()), S.nse_past(F.file("nse_past_full.json")), S.bse_issues(w["feed"].bse.ipo_issues())):
        assert not any("jio" in r["name"].lower() for r in what)
    assert not any(b["code"] for b in S.bse_issues(w["feed"].bse.ipo_issues()) if "jio" in b["name"].lower())
    d = S.nse_detail(F.file("nse_detail_JPL.json"))
    assert (d["company"], d["symbol"], d["open"], d["close"], d["low"], d["high"], d["lot"]) == ("Jio Platforms Limited", "JPL", "2026-10-21", "2026-10-23", 1065.0, 1119.0, 12)
    assert d["fresh"] == 270000000 and d["ofs"] is None and d["total_cr"] is None              # (not the 500 crore of its employee portion)
    assert d["subscription"]["times"] == 22.19 and d["docs"][0]["kind"] == "RHP"
    rhp = [e for e in S.sebi_listing(F.file("sebi_red_herring_list.html")) if "jio" in e["company"].lower()]
    assert [(e["kind"], e["date"]) for e in rhp] == [("rhp", "2026-10-15")]
    page6 = S.sebi_listing(json.load(gzip.open(F.DIR / "sebi_draft_pages.json.gz", "rt", encoding="utf8"))["5"])
    assert [(e["kind"], e["date"], e["company"]) for e in page6 if "jio" in e["company"].lower()] == [("drhp", "2026-06-19", "Jio Platforms Ltd")]


def test_jio_platforms_is_closed_awaiting_listing_with_both_its_documents(w):
    job_read(w)
    row = jio(I.load("IN")["rows"])
    assert row["id"] == "in-jpl" and row["symbol"] == "JPL" and row["segment"] == "mainboard" and row["exchanges"] == ["NSE"]
    assert I.stage_of(row, NOW) == "closed"
    pub = I.public(row, NOW)
    assert (pub["open"], pub["close"], pub["low"], pub["high"], pub["lot"]) == ("2026-10-21", "2026-10-23", 1065.0, 1119.0, 12)
    assert (pub["allotment"], pub["allotment_expected"], pub["listing"], pub["listing_expected"]) == ("2026-10-26", True, "2026-10-28", True)
    assert pub["min_amount"] == 13428.0 and pub["size"] == 30213.0 and pub["size_basis"] == "shares at the top of the price band"       # 27 crore new shares
    assert {(d["kind"], d["source"]) for d in row["docs"]} == {("RHP", "sebi"), ("RHP", "nse"), ("DRHP", "sebi")}       # the draft of 19 Jun beside both copies of the red herring prospectus
    assert any(d["kind"] == "DRHP" and d["date"] == "2026-06-19" for d in row["docs"])
    assert row["sub"]["times"] == 22.19


def test_the_closed_tab_and_the_issue_page_show_jio_platforms(w):
    job_read(w)
    c = w["client"]
    d = c.get("/invest/ipos?market=IN", headers=headers("free-token")).json()
    assert [x["id"] for x in d["tabs"]["closed"] if x["id"] == "in-jpl"] == ["in-jpl"] and not any(x["id"] == "in-jpl" for x in d["tabs"]["filed"])
    page = c.get("/invest/ipos/in-jpl", headers=headers("free-token")).json()
    assert page["ipo"]["stage"] == "closed" and {x["kind"] for x in page["documents"]} == {"RHP", "DRHP"}
    assert page["documents"][0]["kind"] == "RHP" and page["subscription"]["times"] == 22.19


def test_it_moves_to_recently_listed_on_its_listing_day(w):
    job_read(w)
    past = F.file("nse_past_full.json")
    # NSE's past list takes the issue up after its allotment, with the listing day (a row shaped like the real ones)
    past.append({"company": "Jio Platforms Limited", "htmSym": "JPL", "ipoEndDate": "23-OCT-2026", "ipoStartDate": "21-OCT-2026", "issuePrice": "1119",
                 "linkRemovalDate": "-", "listingDate": "28-OCT-2026", "priceRange": "Rs.1065 to Rs.1119", "securityType": "EQ", "symbol": "JPL"})
    w["feed"].nse.ipo_past = lambda frm, to: past
    job = I.Job(sleep=lambda s: None)
    job.read("IN", at(2026, 10, 27, 20, 10))
    row = jio(I.load("IN")["rows"])
    assert row["id"] == "in-jpl" and row["listing"] == "2026-10-28" and row["price"] == 1119.0 and I.stage_of(row, at(2026, 10, 27, 20, 10)) == "closed"
    assert I.stage_of(row, at(2026, 10, 28, 8, 0)) == "listed"                                   # on the day, with no further read
    job.read("IN", at(2026, 10, 28, 20, 10))
    row = jio(I.load("IN")["rows"])
    assert {d["kind"] for d in row["docs"]} == {"RHP", "DRHP"} and I.stage_of(row, at(2026, 10, 28, 20, 10)) == "listed"


def test_an_issue_the_lists_dropped_stays_until_nse_takes_it_up(w):
    """The cause for every issue: seen open, gone from the open list at the close, not yet on the past list."""
    cur = [{"companyName": "Zenith Test Limited", "issueEndDate": "23-Oct-2026", "issuePrice": "Rs.153 to Rs.162", "issueSize": "17000000",
            "issueStartDate": "21-Oct-2026", "series": "EQ", "status": "Active", "symbol": "ZZTEST"}]
    w["feed"].nse.ipo_current = lambda: cur
    w["feed"].nse.ipo_upcoming = lambda: []
    job = I.Job(sleep=lambda s: None)
    job.read("IN", at(2026, 10, 22, 20, 10))
    assert I.stage_of(by_id("IN")["in-zztest"], at(2026, 10, 22, 20, 10)) == "open"
    cur.clear()
    job.read("IN", at(2026, 10, 25, 7, 40))
    row = by_id("IN")["in-zztest"]
    assert row["open"] == "2026-10-21" and I.stage_of(row, at(2026, 10, 25, 7, 40)) == "closed"


# ---------- SEBI's draft list, a few pages a run ----------
def test_the_draft_list_is_read_back_a_few_pages_a_run_and_then_only_the_newest(w):
    sebi = w["sebi"]
    job = I.Job(sleep=lambda s: None)
    drafts = lambda: I.db.json_value(db.get_setting(I.SEBI_KEY + "draft"), {})       # noqa: E731
    job.read("IN", NOW)
    assert [p for k, p in sebi.calls if k == "draft"] == [0, 1, 2, 3, 4, 5] and drafts()["done"] is False
    assert any("jio-platforms" in e["url"] for e in drafts()["entries"])                  # page 6 holds Jio's draft of 19 Jun
    job.read("IN", NOW + timedelta(hours=12))
    job.read("IN", NOW + timedelta(days=1))
    st = drafts()
    assert st["done"] is True and min(e["date"] for e in st["entries"]) >= "2025-09-20"       # 400 days back, and no further
    before = len(sebi.calls)
    job.read("IN", NOW + timedelta(days=2))
    assert [p for k, p in sebi.calls[before:] if k == "draft"] == [0, 1]                      # done: the newest two pages, each run
    assert [p for k, p in sebi.calls if k == "red_herring"] == [0, 1] * 4                     # (its list is only ever read at the front)
    assert len({e["url"] for e in st["entries"]}) == len(st["entries"])


def test_sebi_down_leaves_the_stored_pages_and_waits(w):
    job = I.Job(sleep=lambda s: None)
    job.read("IN", NOW)
    n = len(json.loads(db.get_setting(I.SEBI_KEY + "draft"))["entries"])
    w["sebi"].down = {"sebi"}
    job.read("IN", NOW + timedelta(hours=12))
    st = json.loads(db.get_setting(I.SEBI_KEY + "draft"))
    assert len(st["entries"]) == n and st["done"] is False and st["next"] == 6          # it picks up where it was
    assert any("draft offer documents" in p for p in job.status["problems"])


def test_a_filing_row_hands_its_drafts_to_the_issue_row_of_the_same_company():
    today = TODAY
    draft = {"kind": "DRHP", "label": "Acme Limited - DRHP", "url": "https://www.sebi.gov.in/filings/public-issues/jun-2026/acme-limited-drhp_1.html", "date": "2026-06-19", "source": "sebi"}
    old = [{"id": "in-f-1", "market": "IN", "name": "Acme Limited", "nkey": "acme", "exchanges": [], "currency": "INR", "filed": "2026-06-19", "docs": [draft]}]
    nse = {"upcoming": [{"symbol": "ACME", "name": "Acme Limited", "series": "EQ", "segment": "mainboard", "open": "2026-10-28", "close": "2026-10-30", "low": 10.0, "high": 12.0,
                         "size_shares": 1000000}], "current": [], "past": []}
    rows = I.merge_india(old, nse, [], [], [], [], today)           # (SEBI's pages no longer show the draft)
    assert [r["id"] for r in rows] == ["in-acme"] and rows[0]["docs"] == [draft]


def test_an_issue_bse_says_listed_that_no_issue_list_gave_is_a_listed_row():
    perf = [{"name": "ALPHA TECH LIMITED", "short": "ALPHA", "issue_price": 100.0, "listed": "2026-10-20", "day_close": 110.0, "latest": 112.0,
             "url": "https://www.bseindia.com/stock-share-price/alpha-tech-ltd/alpha/544950/"},
            {"name": "Old Co Limited", "short": "OLD", "issue_price": 50.0, "listed": "2026-03-02", "day_close": 55.0, "latest": 60.0,
             "url": "https://www.bseindia.com/stock-share-price/old-co-ltd/old/544100/"}]
    rows = I.merge_india([], {"upcoming": [], "current": [], "past": []}, [], perf, [], [], TODAY)
    assert [(r["id"], r["name"], r["listing"], r["price"]) for r in rows] == [("in-bse-544950", "Alpha Tech Limited", "2026-10-20", 100.0)]       # (the March one is out of the window)
    assert I.stage_of(rows[0], NOW) == "listed"


# ---------- the check: a gap is seen the day it happens ----------
def test_a_red_herring_prospectus_no_page_can_be_found_for_is_a_gap_in_admin(w):
    w["feed"].nse.hidden = {"JPL"}                                         # NSE has no page under any symbol we can guess
    job = job_read(w)
    missing = I.state()["IN"]["missing"]
    assert any("Jio Platforms Limited filed a red herring prospectus with SEBI on 2026-10-15" in m for m in missing)
    assert job.status["last_error"] and job.status["problems"][0].startswith("Missing (India): ")
    row = next(r for r in I.load("IN")["rows"] if r.get("nkey") == "jioplatforms")
    assert row["id"].startswith("in-f-") and I.stage_of(row, NOW) == "filed" and row["probe_at"] == "2026-10-25"       # kept, and looked for again tomorrow
    guesses = {f"detail:{g}" for g in S.symbol_guesses("Jio Platforms Limited")}
    assert guesses <= set(w["feed"].nse.calls)                              # the symbols its name suggests were asked
    n = len(w["feed"].nse.calls)
    job.read("IN", NOW + timedelta(hours=10))                              # the same day: not asked again
    assert not guesses & set(w["feed"].nse.calls[n:])
    w["feed"].nse.hidden = set()
    job.read("IN", NOW + timedelta(days=1))                                # the page is there: the gap closes
    assert jio(I.load("IN")["rows"])["id"] == "in-jpl" and not any("Jio" in m for m in I.state()["IN"]["missing"])


def test_the_check_names_what_an_exchange_has_that_ours_does_not(w):
    nse = {"upcoming": S.nse_upcoming(F.file("nse_upcoming.json")), "current": [], "past": S.nse_past(F.file("nse_past_full.json"))}
    bse = S.bse_issues(F.file("bse_issues.json"))
    perf = S.bse_performance(F.file("bse_listed.json"))
    red = S.sebi_listing(F.file("sebi_red_herring_list.html"))
    rows = I.merge_india([], nse, bse, perf, [], red, TODAY)
    assert [m for m in I.india_gaps(rows, nse, bse, perf, red, TODAY, NOW) if "Jio" not in m and "Paras" not in m] == []       # every list's issue has its row
    for rid in ("in-mksons", "in-bse-4907", "in-tonbo"):         # one from each list: NSE upcoming, BSE SME, NSE past
        gone = [r for r in rows if r["id"] != rid]
        lines = I.india_gaps(gone, nse, bse, perf, red, TODAY, NOW)
        assert any(("not in our list" in m) for m in lines), (rid, lines)
    only_perf = I.merge_india([], {"upcoming": [], "current": [], "past": []}, [], perf, [], [], TODAY)
    assert I.india_gaps([], {"upcoming": [], "current": [], "past": []}, [], perf, [], TODAY, NOW) == [f"{p['name']} is listed on BSE ({p['listed']}), not in our list." for p in perf if p["listed"] >= "2026-08-26"]
    assert len(only_perf) >= 10 and I.india_gaps(only_perf, {"upcoming": [], "current": [], "past": []}, [], perf, [], TODAY, NOW) == []     # BSE's table of listed issues
    gaps = I.india_gaps([r for r in rows if r["id"] != "in-tonbo"], nse, bse, perf, red, TODAY, NOW)
    assert "Tonbo Imaging India Limited is on NSE's past issues, not in our list." in gaps
    assert any(m.startswith("Jio Platforms Limited filed a red herring prospectus") for m in gaps)
    assert not any("withdrawn" in m.lower() for m in gaps)                          # an issue that did not go ahead is not a gap


def test_the_admin_jobs_page_shows_the_gap(w):
    w["feed"].nse.hidden = {"JPL"}
    I.job.sleep = lambda s: None
    I.job.read("IN", NOW)                                                    # (the page reads the module's job)
    row = next(j for j in w["client"].get("/admin/jobs", headers=headers("admin-token")).json()["jobs"] if j["id"] == "ipo")
    assert row["state"] == "bad" and "missing from ours" in row["error"]
    assert any("Jio Platforms Limited filed a red herring prospectus" in x for x in row["log"])


# ---------- the sources ----------
def test_sebi_later_pages_come_from_the_list_request_with_its_page_number():
    seen = []
    pages = json.load(gzip.open(F.DIR / "sebi_draft_pages.json.gz", "rt", encoding="utf8"))

    def handler(req: httpx.Request):
        seen.append(req)
        if req.method == "POST":
            form = dict(x.split("=") for x in req.content.decode().split("&"))
            return httpx.Response(200, text=pages[form["doDirect"]])
        return httpx.Response(200, text=F.file("sebi_draft_list.html"))

    sebi = S.Sebi(transport=httpx.MockTransport(handler))
    first = sebi.listing("draft")
    assert len(first) == 25 and sebi.pages["draft"] == 91
    later = sebi.listing("draft", 5)
    assert later[0]["date"] == "2026-07-01" and any(e["company"] == "Jio Platforms Ltd" for e in later)             # (single-quoted markup)
    post = seen[-1]
    assert post.url.path == "/sebiweb/ajax/home/getnewslistinfo.jsp" and b"doDirect=5" in post.content and b"smid=10" in post.content
    assert post.headers["x-requested-with"] == "XMLHttpRequest" and "smid=10" in post.headers["referer"]


def test_sebi_turning_the_page_request_away_is_a_busy_source_not_an_empty_list():
    blocked = httpx.MockTransport(lambda req: httpx.Response(200, text="<HTML><TITLE>Unauthorized Request Blocked</TITLE></HTML>"))
    with pytest.raises(SourceError) as e:
        S.Sebi(transport=blocked).listing("draft", 3)
    assert e.value.busy


def test_symbol_guesses_and_the_company_name_on_an_issue_page():
    assert S.symbol_guesses("Jio Platforms Limited")[0] == "JPL" and "JIO" in S.symbol_guesses("Jio Platforms Limited")
    assert S.symbol_guesses("Tonbo Imaging India Limited")[0] == "TIIL"
    assert [S.nse_detail(F.file(f"nse_detail_{s}.json"))["company"] for s in ("BONFIG", "MKSONS", "RAVITA")] == [
        "Bonfiglioli Transmissions Limited", "M. K. Sons Fine Jewels Limited", "Ravita Engineering Services Limited"]


# ---------- the US ----------
def test_a_company_with_a_final_prospectus_as_its_first_offering_is_priced(w):
    rows, problems = I.refresh_us(w["cal"], w["edgar"], TODAY, NOW)
    lyca = next(r for r in rows if r["nkey"] == "lyciatherapeutics")
    assert problems == [] and lyca["priced"] == "2026-10-23" and lyca["priced_from"] == "sec" and I.stage_of(lyca, NOW) == "listed"
    names = {r["nkey"] for r in rows}
    assert not names & {"sunshinebiopharma", "weshop", "darkiris", "baselmedical", "citrotech", "newgenivf", "starfashionculture"}       # already reporting: more shares, not an IPO
    assert "1806540" in w["edgar"].ciks and "1402328" in w["edgar"].ciks
    asked = len(w["edgar"].ciks)
    I.save("US", rows, {})
    rows, _ = I.refresh_us(w["cal"], w["edgar"], TODAY, NOW)
    assert len(w["edgar"].ciks) == asked                                       # each company is asked about once


def test_a_first_offering_the_calendar_never_listed_gets_a_row(w):
    cal = w["cal"]
    ipos = cal.ipos
    cal.ipos = lambda m: [r for r in ipos(m) if "iambic" not in r["name"].lower()]       # the calendar without Iambic Therapeutics
    rows, problems = I.refresh_us(cal, w["edgar"], TODAY, NOW)
    iam = [r for r in rows if r["nkey"] == "iambictherapeutics"]
    assert len(iam) == 1 and iam[0]["id"] == "us-sec-1997038" and iam[0]["priced"] == "2026-10-15" and I.stage_of(iam[0], NOW) == "listed"


def test_a_deal_the_calendar_lists_as_priced_and_as_filed_is_priced(w):
    rows, _ = I.refresh_us(w["cal"], w["edgar"], TODAY, NOW)
    got = {r["nkey"]: r for r in rows}
    assert (got["accelevation"]["priced"], got["adarxpharmaceuticals"]["priced"]) == ("2026-09-30", "2026-09-25")
    assert I.stage_of(got["accelevation"], NOW) == "listed" and got["accelevation"]["price"]


def test_the_sec_check_names_a_final_prospectus_it_could_not_settle(w, monkeypatch):
    monkeypatch.setattr(I, "FIRST_LOOKUPS", 1)
    missing = []
    I.refresh_us(w["cal"], w["edgar"], TODAY, NOW, check=missing)
    assert missing and all("final prospectus with the SEC" in m for m in missing)


def test_the_sec_down_loses_nothing(w):
    w["edgar"].down = {"edgar"}
    rows, problems = I.refresh_us(w["cal"], w["edgar"], TODAY, NOW)
    assert any("final prospectuses" in p for p in problems) and next(r for r in rows if r["nkey"] == "lyciatherapeutics").get("priced") is None
