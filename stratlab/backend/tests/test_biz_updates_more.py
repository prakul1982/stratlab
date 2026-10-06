"""Business updates, expanded: more sectors, filings from both exchanges (counted once), "My stocks", the month-by-month
comparison with the change on the year, and which companies read reliably."""
import json
import re

import pytest

from app import main  # noqa: F401,I001  (first: the app wires the modules)
from app import biz_updates as B, db, holdings
from app.intel import filings as F
from app.intel.net import SourceError
from tests import fake_biz as FB
from tests.fake_db import headers
from tests.test_biz_updates import ADVICE, PROVIDERS, docs_api, paid, w  # noqa: F401  (fixtures)

BSE_ARCHIVE = "https://www.bseindia.com/xml-data/corpfiling/AttachLive/"


def filing(fid, at, subject, text, url, exchange=None):
    row = {"id": fid, "at": at, "subject": subject, "text": text, "url": url, "category": "other", "label": "x", "severity": "info"}
    if exchange:
        row["exchange"] = exchange
    return row


# ---------- which filings count, by sector ----------
TITLES = {
    "autos": ["Monthly Business Update - Sales for September 2026", "Auto sales for the month of October 2026"],
    "cement": ["Cement sales volumes for Q2 FY27", "Production and sales volumes - Quarter ended September 2026"],
    "airlines": ["Passenger traffic for September 2026", "Monthly operational update", "Cargo volumes handled in September"],
    "power": ["Power generation figures for September 2026", "Electricity sales update", "Generation data for the month"],
    "telecom": ["Subscriber base and key operating metrics for the quarter"],
    "metals": ["Crude steel production and sales for September 2026", "Coal production and offtake - September", "Production and despatches update"],
    "retail": ["Q2 FY27 business update - store count and revenue growth", "Quarterly business update"],
    "banks": ["Provisional business update for the quarter ended 30th September 2026", "Deposits and advances as on 30 September 2026",
              "Assets under management as at September 30, 2026"],
}
NOT = ["Sale of shares by promoter", "Record date for dividend", "Trading window closure", "Transcript of analyst meet",
       "Slump sale of undertaking", "Sales tax order received"]


@pytest.mark.parametrize("sector,titles", sorted(TITLES.items()))
def test_every_sector_s_updates_are_found(sector, titles):
    for t in titles:
        assert B.is_update(filing("1", "2026-10-01T10:00", t, "", "https://nsearchives.nseindia.com/corporate/x.pdf")), t


def test_other_filings_are_not_updates():
    for t in NOT:
        assert not B.is_update(filing("1", "2026-10-01T10:00", t, "", "https://nsearchives.nseindia.com/corporate/x.pdf")), t


def test_sector_lists():
    assert {"autos", "cement", "airlines", "power", "telecom", "metals", "retail", "lenders"} <= set(B.SECTORS)
    for sid, s in B.SECTORS.items():
        syms = [x for x, _ in s["symbols"]]
        assert len(syms) == len(set(syms)) and all(B.SYMBOL.match(x) for x in syms), sid
        assert s["span"] in ("month", "quarter") and s["label"]


# ---------- both exchanges ----------
def test_a_filing_on_both_exchanges_counts_once_as_nses():
    n = filing("n1", "2026-10-01T10:00", "Monthly business update", "Sales for September", "https://nsearchives.nseindia.com/corporate/a.pdf", "NSE")
    b = filing("b1", "2026-10-01T11:00", "Company Update", "Sales update for September 2026", BSE_ARCHIVE + "a.pdf", "BSE")
    got = B.updates([b, n])
    assert [(u["id"], u["exchange"]) for u in got] == [("n1", "NSE")]
    later = filing("b2", "2026-11-01T11:00", "Company Update", "Sales update for October 2026", BSE_ARCHIVE + "b.pdf", "BSE")
    assert [(u["id"], u["exchange"]) for u in B.updates([later, n, b])] == [("b2", "BSE"), ("n1", "NSE")]
    # two different updates on one day on BSE, one on NSE: the second still shows
    b2 = filing("b3", "2026-10-01T12:00", "Company Update", "Production volumes for September 2026", BSE_ARCHIVE + "c.pdf", "BSE")
    assert len(B.updates([n, b, b2])) == 2


def test_feed_marks_each_row_with_its_exchange():
    class Nse:
        def announcements(self, s, d):
            return [filing("n", "2026-10-01T10:00", "Business update", "", "https://nsearchives.nseindia.com/corporate/a.pdf")]

    class Bse:
        def announcements(self, c, d):
            if c == "999":
                raise SourceError("the exchange", "busy")
            return [filing("b", "2026-10-02T10:00", "Business update", "", BSE_ARCHIVE + "a.pdf")]

    feed = F.IndiaFilings(Nse(), Bse(), lambda s: "543210" if s == "TINYCO" else None, lambda s: "500325" if s == "RELIANCE" else "999" if s == "BADTWIN" else None)
    both = feed.announcements_both("RELIANCE")
    assert [(r["id"], r["exchange"]) for r in both] == [("b", "BSE"), ("n", "NSE")]          # newest first
    assert [r["exchange"] for r in feed.announcements_both("TINYCO")] == ["BSE"]            # BSE-only
    assert [r["exchange"] for r in feed.announcements_both("ONLYNSE")] == ["NSE"]
    assert [r["exchange"] for r in feed.announcements_both("BADTWIN")] == ["NSE"]           # BSE busy: NSE's rows stand

    class Down(Nse):
        def announcements(self, s, d):
            raise SourceError("the exchange", "down")

    with pytest.raises(SourceError):
        F.IndiaFilings(Down(), Bse(), lambda s: None).announcements_both("X")
    assert [r["exchange"] for r in F.IndiaFilings(Down(), Bse(), lambda s: None, lambda s: "500325").announcements_both("X")] == ["BSE"]


def test_a_bse_filing_is_read_and_its_source_says_so(w):
    sym = "TVSMOTOR"
    src = next(u for u in B.updates(FB.announcements(sym)) if u["url"].endswith(FB.FILES[sym]))
    item = {**src, "exchange": "BSE"}
    r = B.read_one(sym, item, docs_api(), None, [])
    assert r["exchange"] == "BSE" and r["figures"]
    B.save(sym, item["id"], r)
    top = B.series(B.stored(sym))[0]
    assert top["latest"]["source"]["exchange"] == "BSE" and top["latest"]["source"]["url"].endswith(FB.FILES[sym])


# ---------- compare, month by month ----------
def seed_two():
    FB.seed(("MARUTI", "ASHOKLEY"))


def test_comparison_month_by_month_with_year_change_by_hand(w, paid):
    seed_two()
    cmp_ = B.compare_view("autos")
    assert cmp_["periods"][0] == "2026-09" and len(cmp_["periods"]) == 13 and cmp_["periods"][-1] == "2025-09"
    names = [c["name"] for c in cmp_["companies"]]
    assert names == ["Ashok Leyland", "Maruti Suzuki India"]                      # alphabetical, only those with figures
    assert "Hero MotoCorp" in cmp_["without"]
    a = cmp_["companies"][0]
    last, a_year = a["points"]["2026-09"], a["points"]["2025-09"]
    # the sample's 14th month: 100000 + 2000 x 13 = 126,000; a year earlier (its 2nd): 102,000 -> up 23.5%
    assert (last["value"], a_year["value"], last["year_change"]) == (126000.0, 102000.0, 23.5)
    assert a_year["year_change"] is None                                          # nothing a year before that in the sample
    assert last["url"].endswith("SAMPLE_2026-09.pdf") and last["exchange"] == "NSE" and last["filed"] == "2026-10-01"
    assert a["unit"] == "units" and a["metric"] == "Total sales"


def test_quarterly_companies_have_a_figure_only_in_quarter_end_months(w):
    reads = {}
    for i, p in enumerate(("2025-09", "2025-12", "2026-03", "2026-06", "2026-09")):
        v = 1000 + 100 * i
        reads[f"q{i}"] = {"at": f"{B.shift(p, 1)}-04T10:00", "title": f"Business update {p}", "url": FB.ARCHIVE + f"HDFCBANK_{p}.pdf",
                          "read_at": "x", "period": p, "span": "quarter", "problem": None, "exchange": "BSE",
                          "figures": [{"metric": "Period-end deposits", "segment": None, "value": float(v), "unit": "₹ billion", "basis": "period end",
                                       "prior": None, "headline": True, "quote": f"Deposits Rs {v} billion", "page": 1}]}
    for fid, r in reads.items():
        B.save("HDFCBANK", fid, r)
    c = B.compare_view("lenders")
    col = c["companies"][0]
    assert col["step"] == "quarter" and sorted(col["points"]) == ["2025-09", "2025-12", "2026-03", "2026-06", "2026-09"]
    assert col["points"]["2026-09"]["year_change"] == 40.0 and col["points"]["2026-09"]["exchange"] == "BSE"   # 1400 / 1000
    assert col["points"]["2026-06"]["year_change"] is None


def test_comparison_with_nothing_read(w):
    B.forget()
    c = B.compare_view("cement")
    assert c["periods"] == [] and c["companies"] == [] and len(c["without"]) == len(B.SECTORS["cement"]["symbols"])


# ---------- my stocks ----------
def test_my_stocks_lists_holdings_then_watchlist(w, paid):
    FB.seed(("RELIANCE", "MARUTI", "ASHOKLEY"))
    uid = "u-basic"
    holdings.save(uid, [{"symbol": "MARUTI", "qty": 10, "avg": 100.0}, {"symbol": "TCS", "qty": 5, "avg": 50.0}], "manual")
    db.set_setting(f"watchlist:{uid}", json.dumps({"items": [{"symbol": "RELIANCE", "region": "IN"}, {"symbol": "MARUTI", "region": "IN"},
                                                              {"symbol": "AAPL", "region": "US"}]}))
    v = B.my_view(uid)
    assert [(r["symbol"], r["kind"]) for r in v["rows"]] == [("MARUTI", "holding"), ("RELIANCE", "watchlist")]
    assert [(x["symbol"], x["kind"]) for x in v["without"]] == [("TCS", "holding")]
    r = w["client"].get("/invest/business-updates/mine", headers=headers("basic-token"))
    assert r.status_code == 200 and r.json()["rows"][0]["symbol"] == "MARUTI" and r.json()["rows"][0]["change_year"] is not None
    assert w["client"].get("/invest/business-updates/mine", headers=headers("free-token")).status_code == 402
    assert w["client"].get("/invest/business-updates/mine").status_code == 401


def test_my_stocks_with_nothing_saved(w, paid):
    v = w["client"].get("/invest/business-updates/mine", headers=headers("basic-token")).json()
    assert v["rows"] == [] and v["without"] == []


# ---------- the sector route carries the comparison ----------
def test_sector_route_has_compare_and_new_sectors(w, paid):
    seed_two()
    c = w["client"]
    r = c.get("/invest/business-updates?sector=autos", headers=headers("basic-token")).json()
    assert r["compare"]["periods"][0] == "2026-09" and {x["id"] for x in r["sectors"]} >= {"cement", "airlines", "power", "telecom", "metals", "retail"}
    row = next(x for x in r["rows"] if x["symbol"] == "MARUTI")
    assert row["exchange"] == "NSE" and row["page"] == 1 and row["reads"] == 14 and row["read_ok"] == 14
    for sid in B.SECTORS:
        assert c.get(f"/invest/business-updates?sector={sid}", headers=headers("basic-token")).status_code == 200
    assert not PROVIDERS.search(json.dumps(r)) and not ADVICE.search(json.dumps(r))


# ---------- which companies read reliably ----------
def test_reliability_by_company_and_sector(w, paid):
    FB.seed(("MARUTI",))
    for i in range(3):                                           # a company whose filings give nothing checkable
        B.save("ASHOKLEY", f"x{i}", {"at": f"2026-0{i + 1}-01T10:00", "title": "Sales", "url": FB.ARCHIVE + "A.pdf", "period": None,
                                     "figures": [], "problem": "No figure could be checked against the document."})
    B.save("TVSMOTOR", "p", {"at": "2026-05-01T10:00", "title": "Sales", "url": FB.ARCHIVE + "T.pdf", "skip": True, "figures": []})
    B.forget()
    rel = w["client"].get("/admin/business-updates/reliability", headers=headers("admin-token")).json()
    by = {c["symbol"]: c for c in rel["companies"]}
    assert by["MARUTI"]["verdict"] == "reads reliably" and by["MARUTI"]["share"] == 100
    assert by["ASHOKLEY"]["verdict"] == "does not read" and by["ASHOKLEY"]["problems"]
    assert by["TVSMOTOR"]["verdict"] == "not read yet" and by["TVSMOTOR"]["filings_read"] == 0     # a press release that wasn't one
    autos = next(s for s in rel["sectors"] if s["sector"] == "autos")
    assert autos["filings_read"] == 17 and autos["with_figures"] == 14 and autos["reliable"] == 1 and autos["share"] == 82
    assert w["client"].get("/admin/business-updates/reliability", headers=headers("free-token")).status_code == 403


# ---------- the job ----------
def test_job_reads_both_exchanges_and_users_stocks(w, monkeypatch):
    from datetime import datetime, timezone
    holdings.save("u-basic", [{"symbol": "ZZTEST", "qty": 1, "avg": 1.0}, {"symbol": "MARUTI", "qty": 1, "avg": 1.0}], "manual")
    assert B.user_symbols() == ["ZZTEST"]                         # MARUTI is on a sector list already
    seen = []

    class Both:
        def announcements_both(self, symbol, days=365):
            seen.append(symbol)
            return [dict(i, exchange="NSE") for i in FB.announcements(symbol)]

    B.setup(lambda: Both(), lambda: docs_api(), lambda: None)
    job = B.Job(lambda rows, now: 0, lambda: [])
    out = job.tick(datetime(2026, 10, 2, 14, 30, tzinfo=timezone.utc))
    assert "ZZTEST" in seen and "MARUTI" in seen and out["read"] >= 3
    assert B.stored("MARUTI") and all(r.get("exchange") == "NSE" for r in B.stored("MARUTI").values())


def test_wording_is_facts():
    text = B.NOTE + " ".join(s["label"] for s in B.SECTORS.values())
    assert not PROVIDERS.search(text) and not re.search(r"\b(buy|sell|recommend|should|best)\b", text, re.I)
