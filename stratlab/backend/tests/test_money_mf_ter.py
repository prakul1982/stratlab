"""Fund costs (Money: mutual funds): reading the TER disclosure (synthetic tables in each shape it can come in), the
stored latest TERs and history, matching funds by name, the rupee arithmetic, the plan gate and the page's route."""
import json
import time
from datetime import date
from pathlib import Path

import pytest

from app import db, money_mf_nav as N, money_mf_ter as T
from app.config import settings
from tests import world
from tests.test_money_mf import DAILY, GF2018, PRO, FREE, BASIC, debt, flexi, statement, upload

FIX = Path(__file__).parent / "fixtures" / "mf"
HTML = (FIX / "ter_disclosure.html").read_text()

OLD_HEADERS = ["Scheme Name", "Scheme Type", "Scheme Category", "TER Date",
               "Regular Plan - Base TER (%)", "Regular Plan - Additional expense as per Regulation 52(6A)(b) (%)",
               "Regular Plan - Additional expense as per Regulation 52(6A)(c) (%)", "Regular Plan - GST (%)", "Regular Plan - Total TER (%)",
               "Direct Plan - Base TER (%)", "Direct Plan - Additional expense as per Regulation 52(6A)(b) (%)",
               "Direct Plan - Additional expense as per Regulation 52(6A)(c) (%)", "Direct Plan - GST (%)", "Direct Plan - Total TER (%)"]


def table(headers, rows) -> str:
    tr = lambda cells, tag="td": "<tr>" + "".join(f"<{tag}>{c}</{tag}>" for c in cells) + "</tr>"     # noqa: E731
    return "<table><tr><td>Total Expense Ratio</td></tr>" + tr(headers, "th") + "".join(tr(r) for r in rows) + "</table>"


@pytest.fixture
def ter(monkeypatch):
    """The disclosure from the fixture for every month asked, counting the requests; no pauses, no thread."""
    calls = []

    def fetch(m, y):
        calls.append((y, m))
        return HTML
    monkeypatch.setattr(T, "fetch_month", fetch)
    monkeypatch.setattr(T, "MIN_ROWS", 1)
    monkeypatch.setattr(T, "PAUSE", 0)
    monkeypatch.setattr(T, "BACKGROUND", False)
    T.forget()
    yield calls
    T.forget()


@pytest.fixture
def navfiles(monkeypatch):
    monkeypatch.setattr(N, "fetch_text", lambda url: DAILY if url == N.DAILY_URL else GF2018)
    monkeypatch.setattr(N, "MIN_SCHEMES", 1)
    N.forget()
    yield
    N.forget()


@pytest.fixture
def w(monkeypatch, navfiles, ter):
    built = world.build(monkeypatch)
    yield built
    built["close"]()


@pytest.fixture
def paid(monkeypatch):
    for k, v in (("RAZORPAY_KEY_ID", "rzp_live_x"), ("RAZORPAY_KEY_SECRET", "s"), ("RAZORPAY_PLAN_BASIC", "pb"), ("RAZORPAY_PLAN_PRO", "pp")):
        monkeypatch.setattr(settings, k, v)


# ---------- reading the disclosure ----------
def test_reads_the_2026_split_with_brokerage_and_levies():
    p = T.parse(HTML)
    assert p["parts"] == ["base", "b30", "brokerage", "levies", "gst", "total"]
    r = [x for x in p["rows"] if x["name"] == "Example Flexi Cap Fund" and x["date"] == "2026-04-01"][0]
    assert r["reg"] == {"base": 1.5, "b30": 0.05, "brokerage": 0.08, "levies": 0.02, "gst": 0.15, "total": 1.8}
    assert r["dir"]["total"] == 0.52 and r["category"] == "Equity Scheme - Flexi Cap Fund" and r["type"] == "Open Ended"
    old = [x for x in p["rows"] if x["date"] == "2024-03-01"][0]
    assert "brokerage" not in old["reg"] and old["reg"]["total"] == 1.95      # blank cells are left out, not zero


def test_reads_the_older_layout_csv_and_json():
    rows = [["Alpha Large Cap Fund", "Open Ended", "Equity Scheme - Large Cap Fund", "05-Sep-2025", "1.5", "0.05", "0.05", "0.27", "1.87",
             "0.5", "0.05", "0.05", "0.1", "0.70"]]
    a = T.parse(table(OLD_HEADERS, rows))
    assert a["parts"] == ["base", "b30", "c", "gst", "total"] and a["rows"][0]["dir"]["c"] == 0.05
    csv_text = ",".join(f'"{h}"' for h in OLD_HEADERS) + "\n" + ",".join(f'"{c}"' for c in rows[0]) + "\n"
    assert T.parse(csv_text)["rows"] == a["rows"]
    recs = [dict(zip(OLD_HEADERS, rows[0]))]
    assert T.parse(json.dumps({"data": recs}))["rows"] == a["rows"]


def test_a_table_without_a_total_adds_the_parts():
    h = ["Scheme Name", "TER Date", "Regular Plan - Base TER (%)", "Regular Plan - GST (%)", "Direct Plan - Base TER (%)", "Direct Plan - GST (%)"]
    r = T.parse(table(h, [["Beta Liquid Fund", "2026-09-01", "0.2", "0.03", "0.1", "0.02"]]))["rows"][0]
    assert r["reg"]["total"] == 0.23 and r["dir"]["total"] == 0.12


def test_garbage_and_odd_cells_are_left_out():
    assert T.parse("")["rows"] == [] and T.parse("<html>Access denied</html>")["rows"] == []
    assert T.parse("{not json")["rows"] == [] and T.parse("[1, 2]")["rows"] == []
    rows = [["", "", "", "01-Jan-2026", "1", "1", "1", "1", "1", "1", "1", "1", "1", "1"],            # no name
            ["Gamma Fund", "", "", "not a date", "1", "1", "1", "1", "1", "1", "1", "1", "1", "1"],     # no date
            ["Delta Fund", "", "", "01-Jan-2026", "-", "N.A.", "", "", "", "", "", "", "", ""],         # no figure
            ["Eps Fund", "", "", "01-Jan-2026", "99", "", "", "", "-1", "", "", "", "", "0.5"]]         # out of range dropped
    p = T.parse(table(OLD_HEADERS, rows))
    assert [r["name"] for r in p["rows"]] == ["Eps Fund"] and p["rows"][0]["reg"] == {} and p["rows"][0]["dir"] == {"total": 0.5}


# ---------- storing and history ----------
def test_latest_moves_forward_and_history_keeps_changes_in_any_order(w):
    p = T.parse(HTML)
    newer = {"parts": p["parts"], "rows": [r for r in p["rows"] if r["date"] >= "2026-01-01"]}
    older = {"parts": p["parts"], "rows": [r for r in p["rows"] if r["date"] < "2026-01-01"]}
    T.ingest(newer)
    T.ingest(older)                                  # a month read later in the backfill
    T.ingest(newer)                                  # the same month read again changes nothing
    latest, hist = T._mem["latest"], T._mem["hist"]
    assert latest["s"]["Example Flexi Cap Fund"][0] == "2026-04-01"
    assert hist["Example Flexi Cap Fund"]["t"] == [["2024-03-01", 1.95, 0.6], ["2025-06-02", 1.95, 0.55], ["2026-04-01", 1.8, 0.52]]
    assert [c[1] for c in hist["Sample Short Duration Fund"]["c"]] == ["Debt Scheme - Short Duration Fund",
                                                                       "Debt Scheme - Short Duration Fund (Macaulay duration 1 to 3 years)"]


def test_new_parts_relay_stored_rows(w):
    T.forget()
    try:
        T.ingest(T.parse(table(OLD_HEADERS, [["Zeta Fund", "", "", "01-Jan-2025", "1", "0", "0.1", "0.2", "1.3", "0.5", "0", "0.1", "0.1", "0.7"]])))
        T.ingest(T.parse(HTML))
        latest = T._mem["latest"]
        parts = latest["parts"]
        assert parts[-1] == "total" and {"c", "brokerage", "levies"} <= set(parts)
        z = dict(zip(parts, latest["s"]["Zeta Fund"][3]))
        assert z["total"] == 1.3 and z["c"] == 0.1 and z["brokerage"] is None
    finally:
        T.forget()


def test_refresh_reads_two_months_then_one_older_a_run_and_saves(w, ter):
    assert T.refresh(date(2026, 10, 4))
    assert ter == [(2026, 9), (2026, 10), (2026, 8)]
    ter.clear()
    assert T.refresh(date(2026, 10, 4))
    assert ter == [(2026, 9), (2026, 10), (2026, 7)]     # August is stored, so the next older month
    saved = json.loads(db.get_setting(T.LATEST_KEY))
    assert "Example Flexi Cap Fund" in saved["s"] and json.loads(db.get_setting(T.MONTHS_KEY)).keys() >= {"2026-08", "2026-07"}
    T.forget()                                            # a restart reads the saved copy, without a request
    ter.clear()
    T._mem["tried"] = 0
    import time
    saved_at = json.loads(db.get_setting(T.LATEST_KEY))["at"]
    assert abs(saved_at - time.time()) < 60
    assert T.ensure()["s"] and ter == []


def test_a_failed_read_keeps_the_stored_copy(w, ter, monkeypatch):
    T.refresh(date(2026, 10, 4))
    before = dict(T._mem["latest"]["s"])

    def down(m, y):
        raise OSError("down")
    monkeypatch.setattr(T, "fetch_month", down)
    assert T.refresh(date(2026, 10, 4)) is False and T._mem["latest"]["s"] == before
    monkeypatch.setattr(T, "fetch_month", lambda m, y: "<html>maintenance</html>")
    monkeypatch.setattr(T, "MIN_ROWS", 5)
    assert T.refresh(date(2026, 10, 4)) is False and T._mem["latest"]["s"] == before


def test_ensure_waits_between_tries_when_reads_fail(w, monkeypatch):
    n = []
    monkeypatch.setattr(T, "fetch_month", lambda m, y: n.append(1) or "")
    T.forget()
    T.ensure()
    T.ensure()
    assert len(n) == 2                     # one try (two months), then nothing until RETRY passes


# ---------- matching and arithmetic ----------
def test_matching_by_name_ignores_plan_option_and_former_names(w):
    T.ingest(T.parse(HTML))
    T.ingest(T.parse(table(OLD_HEADERS, [["Example Flexi Cap Fund (Formerly known as Example Multi Cap Fund)", "", "", "01-Jan-2025",
                                          "1", "", "", "", "1", "1", "", "", "", "1"]])))
    assert T.match("Example Flexi Cap Fund - Direct Plan - Growth") == "Example Flexi Cap Fund"     # the newest of the two names
    assert T.match("Sample Short Duration Fund - Regular Plan - Monthly IDCW Payout") == "Sample Short Duration Fund"
    assert T.match("Something Else Entirely Fund - Direct Growth") is None and T.match("") is None
    assert T.plan_of("X Fund - Direct Plan - Growth") == "direct" and T.plan_of("X Fund Regular Growth") == "regular"
    assert T.plan_of("X Fund Growth") is None


def test_rupee_arithmetic_and_history_lookup():
    assert T.rupees(100000, 1.8) == 1800.0 and T.rupees(42500, 0.52) == 221.0 and T.rupees(None, 1) is None
    pts = [["2024-03-01", 1.95, 0.6], ["2025-06-02", 1.95, 0.55], ["2026-04-01", 1.8, 0.52]]
    assert T.at_or_before(pts, "2025-01-01", 2) == ("2024-03-01", 0.6)
    assert T.at_or_before(pts, "2026-04-01", 1) == ("2026-04-01", 1.8)
    assert T.at_or_before(pts, "2020-01-01", 1) is None


# ---------- the route ----------
def test_costs_on_the_page(w, ter):
    c = w["client"]
    assert upload(c, statement(flexi(), debt())).status_code == 200
    r = c.get("/money/mutual-funds/costs", headers=PRO)
    assert r.status_code == 200
    d = r.json()
    by = {s["matched"]: s for s in d["schemes"]}
    f = by["Example Flexi Cap Fund"]
    assert f["plan"] == "direct" and f["ter"] == 0.52 and f["value"] == 27500.0 and f["cost_year"] == 143.0
    assert f["direct"]["total"] == 0.52 and f["regular"]["total"] == 1.8 and f["gap_pp"] == 1.28 and f["gap_year"] == 352.0
    assert f["other_plan"] == "regular" and f["other_cost_year"] == 495.0
    assert [p["key"] for p in f["parts"]] == ["base", "b30", "brokerage", "levies", "gst"]
    assert sum(p["pct"] for p in f["parts"]) == pytest.approx(0.52)
    s = f["since"]           # first units still held bought 10 Jan 2018, before the history starts
    assert s["history_starts_late"] and s["from"] == "2024-03-01" and s["then"] == 0.6 and s["change_pp"] == -0.08 and s["count"] == 2
    debt_row = by["Sample Short Duration Fund"]
    assert debt_row["since"]["from"] == "2023-06-01" and not debt_row["since"]["history_starts_late"]
    assert debt_row["category_changes"] == [{"date": "2026-03-16", "from": "Debt Scheme - Short Duration Fund",
                                             "to": "Debt Scheme - Short Duration Fund (Macaulay duration 1 to 3 years)", "recat_2026": True}]
    assert d["total"]["cost_year"] == round(143.0 + 15000 * 0.28 / 100, 2) and d["total"]["funds"] == 2 and d["unmatched"] == []
    assert d["total"]["weighted_ter"] == round(d["total"]["cost_year"] / 42500 * 100, 4)
    assert d["read_at"] and d["assumptions"]
    text = json.dumps(d).lower()
    for word in ("switch", "better", "cheaper", "should", "recommend", "amfi"):
        assert word not in text


def test_free_sees_each_ter_and_the_total_basic_sees_everything(w, ter, paid):
    c = w["client"]
    assert upload(c, statement(flexi(), debt()), headers=FREE).status_code == 200
    d = c.get("/money/mutual-funds/costs", headers=FREE).json()
    assert d["full"] is False and d["plan"] == "Basic" and d["total"]["cost_year"] > 0
    f = d["schemes"][0]
    assert f["ter"] is not None and "cost_year" not in f and "regular" not in f and "since" not in f
    assert upload(c, statement(flexi(), debt()), headers=BASIC).status_code == 200
    d = c.get("/money/mutual-funds/costs", headers=BASIC).json()
    assert d["full"] is True and d["schemes"][0]["regular"] is not None


def test_no_funds_and_no_disclosure(w, ter, monkeypatch):
    c = w["client"]
    c.delete("/money/mutual-funds", headers=PRO)
    d = c.get("/money/mutual-funds/costs", headers=PRO).json()
    assert d["schemes"] == [] and d["total"] is None and ter == []           # nothing is read for a user without funds
    monkeypatch.setattr(T, "fetch_month", lambda m, y: "")
    T.forget()
    assert upload(c, statement(flexi())).status_code == 200
    d = c.get("/money/mutual-funds/costs", headers=PRO).json()
    # nothing could be read: "unavailable", not "not found" for every fund
    assert d["state"] == "unavailable" and d["schemes"] == [] and d["unmatched"] == [] and d["total"] is None


def test_a_fund_not_in_the_disclosure_is_listed(w, ter):
    c = w["client"]
    assert upload(c, statement({**flexi(), "name": "Other House Gilt Fund - Direct Plan - Growth", "isin": "INF999Z01AA1", "code": "Z1"})).status_code == 200
    d = c.get("/money/mutual-funds/costs", headers=PRO).json()
    assert d["state"] == "ok" and [u["name"] for u in d["unmatched"]] == ["Other House Gilt Fund - Direct Plan - Growth"]


def test_the_first_read_shows_as_reading(w, ter, monkeypatch):
    import threading
    go, asked = threading.Event(), threading.Event()

    def slow(m, y):
        asked.set()
        go.wait(10)
        return HTML
    monkeypatch.setattr(T, "fetch_month", slow)
    monkeypatch.setattr(T, "BACKGROUND", True)
    T.forget()
    c = w["client"]
    assert upload(c, statement(flexi())).status_code == 200
    d = c.get("/money/mutual-funds/costs", headers=PRO).json()
    assert d["state"] == "reading" and d["schemes"] == [] and d["unmatched"] == []
    assert asked.wait(5)
    go.set()
    for _ in range(100):
        if not T._mem["running"]:
            break
        time.sleep(0.05)
    d = c.get("/money/mutual-funds/costs", headers=PRO).json()
    assert d["state"] == "ok" and d["schemes"][0]["matched"] == "Example Flexi Cap Fund"


# ---------- the platform check and the admin button ----------
def test_check_fails_when_nothing_was_read_and_shows_the_error(w, ter, monkeypatch):
    def down(m, y):
        raise OSError("blocked by proxy 403")
    monkeypatch.setattr(T, "fetch_month", down)
    r = T.check()
    assert r["name"] == "Fund costs (TER)" and r["state"] == "fail" and "OSError: blocked by proxy 403" in r["detail"]


def test_check_passes_warns_when_stale_or_small(w, ter, monkeypatch):
    monkeypatch.setattr(T, "CHECK_SCHEMES", 3)
    r = T.check()                                      # the check starts the first read itself
    assert r["state"] == "pass" and "3 schemes read for" in r["detail"], r
    st = T.status()
    assert st["error"] is None and st["schemes"] == 3 and st["stored"] == 3 and st["month"]
    assert T.check(now=st["last_ok"] + 46 * 86400)["state"] == "warn"
    assert "Stale" in T.check(now=st["last_ok"] + 46 * 86400)["detail"]
    monkeypatch.setattr(T, "CHECK_SCHEMES", 500)
    r = T.check()
    assert r["state"] == "warn" and "Fewer than 500" in r["detail"]
    monkeypatch.setattr(T, "CHECK_SCHEMES", 3)       # a later failed try: still a pass on the stored copy, error shown
    monkeypatch.setattr(T, "fetch_month", lambda m, y: (_ for _ in ()).throw(OSError("down")))
    assert T.start(force=True)
    r = T.check()
    assert r["state"] == "pass" and "Last error: OSError: down" in r["detail"]
    T.forget()                                         # the status survives a restart
    assert T.status()["error"] == "OSError: down" and T.status()["last_ok"] == st["last_ok"]


def test_platform_check_lists_fund_costs(w, ter):
    from app import main
    assert ("Fund costs (TER)", "Money") in [(n, a) for n, a, _ in main.platform_checks()]
    r = w["client"].post("/admin/platform/check", headers=world.headers("admin-token"))
    row = next(x for x in r.json()["checks"] if x["name"] == "Fund costs (TER)")
    assert row["area"] == "Money" and row["state"] in ("pass", "warn", "fail")


def test_admin_can_force_a_read(w, ter):
    c, admin = w["client"], world.headers("admin-token")
    assert c.get("/admin/ter", headers=PRO).status_code == 403 and c.post("/admin/ter/read", headers=PRO).status_code == 403
    assert c.get("/admin/ter", headers=admin).json()["status"]["stored"] == 3        # the GET's check did the first read
    n = len(ter)
    r = c.post("/admin/ter/read", headers=admin)
    assert r.status_code == 200 and r.json()["started"] and len(ter) > n            # fresh copy, read again anyway
    T._mem["running"] = True
    assert c.post("/admin/ter/read", headers=admin).status_code == 409
    T._mem["running"] = False


def test_signed_out_is_refused(w):
    assert w["client"].get("/money/mutual-funds/costs").status_code == 401



def test_reads_the_months_workbook_and_retries_a_bad_answer(monkeypatch):
    """The month's disclosure is its Excel download: dates as day numbers, brokerage and transaction cost as two
    columns (one part here); an answer that isn't a workbook is asked again."""
    import httpx
    from app.xlsx_write import workbook
    head = ["NSDL Scheme Code", "Scheme Name", "Scheme Type", "Scheme Category", "TER Date",
            "Regular Plan - Base Expense Ratio (BER) (%)", "Regular Plan - Brokerage cost (%)",
            "Regular Plan - Transaction Cost incurred for the purpose of execution of trade (%)",
            "Regular Plan - Statutory Levies (including GST) (%)", "Regular Plan - Total TER (%)",
            "Direct Plan - Base Expense Ratio (BER) (%)", "Direct Plan - Brokerage cost (%)",
            "Direct Plan - Transaction Cost incurred for the purpose of execution of trade (%)",
            "Direct Plan - Statutory Levies (including GST) (%)", "Direct Plan - Total TER (%)"]
    row = ["X/O/E/1", "Asha Flexi Cap Fund", "Open Ended", "Equity Scheme - Flexi Cap Fund", 46266,
           1.09, 0.02, 0.01, 0.18, 1.3, 0.53, 0.02, 0, 0.21, 0.76]
    book = workbook([("TER", [head, row], None)])
    asked = []

    def answer(req: httpx.Request) -> httpx.Response:
        asked.append(dict(req.url.params))
        return httpx.Response(200, content=b"<html>busy</html>" if len(asked) == 1 else book)
    real = httpx.Client
    monkeypatch.setattr(T.httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(answer), **kw))
    monkeypatch.setattr(T, "PAUSE", 0)
    got = T.parse(T.fetch_month(9, 2026))
    assert asked[0] == {"MF_ID": "All", "Month": "09-2026", "strCat": "-1", "strType": "-1", "excel": "true"}
    assert len(asked) == 2
    assert got["parts"] == ["base", "brokerage", "levies", "total"]
    assert got["rows"] == [{"name": "Asha Flexi Cap Fund", "type": "Open Ended", "category": "Equity Scheme - Flexi Cap Fund",
                            "date": "2026-09-01", "reg": {"base": 1.09, "brokerage": 0.03, "levies": 0.18, "total": 1.3},
                            "dir": {"base": 0.53, "brokerage": 0.02, "levies": 0.21, "total": 0.76}}]


def test_never_a_workbook_is_an_error(monkeypatch):
    import httpx
    real = httpx.Client
    monkeypatch.setattr(T.httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(lambda r: httpx.Response(200, text="no")), **kw))
    monkeypatch.setattr(T, "PAUSE", 0)
    with pytest.raises(ValueError):
        T.fetch_month(9, 2026)
