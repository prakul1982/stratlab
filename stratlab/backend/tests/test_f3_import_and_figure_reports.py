"""Owner-approved features of 12 Nov (lane f3):

1. Import a watchlist: pasted lines or a file's column, each looked up with the app's own symbol search (found / to confirm with
   suggestions / not found); pasting on every plan, a file on Basic and up; the list's limits enforced where they always are.
2. "Report an error in this figure": a signed-in person's report of one figure, kept in the Feedback store as a data error with
   the figure's context, throttled per person; marking it fixed leaves the reporter a one-line note in the app (/me), and an
   email only when they already get alert emails."""
import base64
import json

import pytest

from app import alerts, db, feedback, main, watch_import
from tests import world as W

ADMIN, PRO, BASIC, FREE = (W.headers(t) for t in ("admin-token", "pro-token", "basic-token", "free-token"))


@pytest.fixture
def w(monkeypatch):
    built = W.build(monkeypatch)
    main.suggester.clear()
    with main._recent_lock:
        for k in [k for k in main._recent if k[1].startswith(("figure_report", "watch_import", "feedback"))]:
            del main._recent[k]
    monkeypatch.setattr(feedback, "SEND_IN_BACKGROUND", False)
    sent = []
    monkeypatch.setattr(alerts, "email_ready", lambda: True)
    monkeypatch.setattr(alerts, "send_email", lambda to, subject, body, html=None, headers=None: sent.append((to, subject, body)))
    built["sent"] = sent
    yield built
    main.suggester.clear()
    built["close"]()


def b64(text: str) -> str:
    return base64.b64encode(text.encode()).decode()


# ---------- 1. import a watchlist ----------
def test_pasted_lines_are_found_confirmed_or_not_found_by_the_symbol_search(w):
    c = w["client"]
    r = c.post("/watch/import/resolve", headers=FREE, json={"queries": ["RELIANCE", "tcs", " hdfcbank ", "infosys", "zzzq", "500325", "TCS", ""]})
    assert r.status_code == 200, r.text
    rows = {x["query"]: x for x in r.json()["rows"]}
    assert list(rows) == ["RELIANCE", "tcs", "hdfcbank", "infosys", "zzzq", "500325"]       # each line once, any case, blanks dropped
    assert (rows["RELIANCE"]["status"], rows["RELIANCE"]["item"]["id"]) == ("found", "IN:RELIANCE")
    assert rows["tcs"]["item"]["id"] == "IN:TCS" and rows["hdfcbank"]["item"]["id"] == "IN:HDFCBANK"
    assert rows["500325"]["item"]["id"] == "IN:RELIANCE"                 # a BSE code finds the company
    # a name is never taken on trust: it is offered to confirm, the best suggestion first
    assert rows["infosys"]["status"] == "confirm" and rows["infosys"]["suggestions"][0]["id"] == "IN:INFY" and rows["infosys"]["item"] is None
    assert rows["zzzq"]["status"] == "missing" and rows["zzzq"]["suggestions"] == []
    it = rows["RELIANCE"]["item"]
    assert set(it) == {"id", "market", "symbol", "name", "kind"} and it["kind"] == "stock" and it["name"]


def test_the_market_choice_narrows_the_search_and_us_names_resolve(w):
    c = w["client"]
    us = {x["query"]: x for x in c.post("/watch/import/resolve", headers=FREE, json={"queries": ["RELIANCE", "apple", "AAPL"], "market": "US"}).json()["rows"]}
    assert us["RELIANCE"]["status"] != "found"
    assert us["AAPL"]["status"] == "found" and us["AAPL"]["item"]["id"] == "US:AAPL"
    assert us["apple"]["status"] == "confirm" and us["apple"]["suggestions"][0]["id"] == "US:AAPL"
    assert c.post("/watch/import/resolve", headers=FREE, json={"queries": ["X"], "market": "JP"}).status_code == 422


def test_import_needs_a_sign_in_and_is_bounded(w):
    c = w["client"]
    assert c.post("/watch/import/resolve", json={"queries": ["TCS"]}).status_code == 401
    assert c.post("/watch/import/file", json={"data": b64("Symbol\nTCS\n")}).status_code == 401
    assert c.post("/watch/import/resolve", headers=PRO, json={"queries": ["A"] * (watch_import.MAX_QUERIES + 1)}).status_code == 422
    assert watch_import.clean('  "Tata   Consultancy, " ') == "Tata Consultancy"
    assert len(watch_import.clean("x" * 500)) == watch_import.QUERY_MAX


def test_a_file_is_basic_and_up_and_its_symbol_column_is_guessed(w):
    c = w["client"]
    csv = "Client ID,AB1234\nHoldings as on 12 Nov 2026\n\nInstrument,Qty.,Avg. cost\nRELIANCE,10,2400\nTCS,5,3000\nRELIANCE,1,2500\n"
    r = c.post("/watch/import/file", headers=FREE, json={"data": b64(csv), "filename": "holdings.csv"})
    assert r.status_code == 402 and r.json()["detail"]["code"] == "upgrade_required" and "Basic" in r.json()["detail"]["message"]
    r = c.post("/watch/import/file", headers=BASIC, json={"data": b64(csv), "filename": "holdings.csv"})
    assert r.status_code == 200, r.text
    got = r.json()
    assert got["named"] is True and [col["name"] for col in got["columns"]] == ["Instrument", "Qty.", "Avg. cost"]
    assert got["guess"] == 0 and got["columns"][0]["values"] == ["RELIANCE", "TCS"]          # each value once
    # a bare list with no column names: every line is a value, and a column of quantities is never the guess
    bare = c.post("/watch/import/file", headers=PRO, json={"data": b64("10,infy\n5,TCS\n"), "filename": "x.csv"}).json()
    assert bare["named"] is False and bare["guess"] == 1 and bare["columns"][1]["name"] == "Column 2"
    bad = c.post("/watch/import/file", headers=PRO, json={"data": b64("%PDF-1.4 x"), "filename": "x.pdf"})
    assert bad.status_code == 400 and "PDF" in bad.json()["detail"]["message"]
    assert c.post("/watch/import/file", headers=PRO, json={"data": "@@not base64@@"}).status_code == 400


def test_adding_what_was_found_keeps_the_plans_symbol_limit(w):
    c = w["client"]
    rows = c.post("/watch/import/resolve", headers=FREE, json={"queries": ["RELIANCE", "TCS", "HDFCBANK"]}).json()["rows"]
    items = [x["item"] for x in rows]
    r = c.put("/watch/lists/default/items", headers=FREE, json={"items": items})
    assert r.status_code == 200 and [i["id"] for i in r.json()["lists"][0]["items"]] == ["IN:RELIANCE", "IN:TCS", "IN:HDFCBANK"]
    cap = r.json()["limits"]["symbols"]
    many = items + [{"market": "IN", "symbol": f"S{i}", "name": f"S{i}"} for i in range(cap)]
    over = c.put("/watch/lists/default/items", headers=FREE, json={"items": many})
    assert over.status_code in (400, 402)


# ---------- 2. report an error in a figure ----------
FIG = {"text": "The annual report says 17.9%.", "path": "/research/IN/TCS?tab=x#co-numbers", "section": "Key numbers", "label": "EBITDA margin",
       "value": "18.4%", "period": "FY26", "source": "Annual report", "version": "abc", "browser": "Chrome 130 on Linux", "screen": "1440×1000"}


def test_a_figure_report_needs_a_sign_in_and_lands_in_feedback_as_a_data_error(w):
    c = w["client"]
    assert c.post("/feedback/figure", json=FIG).status_code == 401
    r = c.post("/feedback/figure", headers=PRO, json=FIG)
    assert r.status_code == 200 and r.json()["ok"] is True
    row = c.get("/admin/feedback?type=data_error", headers=ADMIN).json()["rows"][0]
    assert row["type"] == "data_error" and row["text"] == FIG["text"] and row["path"] == "/research/IN/TCS" and row["plan"] == "pro"
    assert row["figure"] == {"section": "Key numbers", "label": "EBITDA margin", "value": "18.4%", "period": "FY26", "source": "Annual report"}
    assert "user_id" not in row and row["status"] == "new"
    assert c.get("/admin/feedback", headers=ADMIN).json()["types"]["data_error"] == "Data error"
    (to, subject, body), = w["sent"]
    assert subject.startswith("[StratLab feedback] Data error:") and "Figure: EBITDA margin (FY26, 18.4%) in Key numbers" in body and "Source: Annual report" in body
    # the general form can't send one (a data error comes from its figure)
    assert c.post("/feedback", headers=PRO, json={**FIG, "type": "data_error"}).status_code == 422


def test_figure_reports_are_checked_and_throttled_per_person(w, monkeypatch):
    c = w["client"]
    assert c.post("/feedback/figure", headers=PRO, json={**FIG, "label": ""}).status_code == 422
    r = c.post("/feedback/figure", headers=PRO, json={**FIG, "text": " x "})
    assert r.status_code == 400 and "what looks wrong" in r.json()["detail"]["message"]
    for _ in range(feedback.FIGURE_HOUR):
        assert c.post("/feedback/figure", headers=PRO, json=FIG).status_code == 200
    r = c.post("/feedback/figure", headers=PRO, json=FIG)
    assert r.status_code == 429
    assert c.post("/feedback/figure", headers=FREE, json=FIG).status_code == 200      # another person has their own allowance


def test_marking_it_fixed_leaves_the_reporter_a_note_once(w):
    c = w["client"]
    c.post("/feedback/figure", headers=PRO, json=FIG)
    fid = c.get("/admin/feedback", headers=ADMIN).json()["rows"][0]["id"]
    assert c.get("/me", headers=PRO).json()["notes"] == []
    w["sent"].clear()
    assert c.put(f"/admin/feedback/{fid}", headers=ADMIN, json={"status": "fixed"}).status_code == 200
    notes = c.get("/me", headers=PRO).json()["notes"]
    assert [n["id"] for n in notes] == [fid] and notes[0]["path"] == "/research/IN/TCS"
    assert notes[0]["text"] == "Fixed: EBITDA margin (FY26, 18.4%) in Key numbers, which you reported. Thanks for telling us."
    assert w["sent"] == []                          # no alert address set: no email, the note only
    assert c.get("/me", headers=FREE).json()["notes"] == []        # nobody else's
    # set back and fixed again: still one note, never told twice
    c.put(f"/admin/feedback/{fid}", headers=ADMIN, json={"status": "seen"})
    c.put(f"/admin/feedback/{fid}", headers=ADMIN, json={"status": "fixed"})
    assert len(c.get("/me", headers=PRO).json()["notes"]) == 1
    # shown in the app: gone
    assert c.post("/feedback/notes/seen", headers=PRO, json={"ids": [fid]}).json()["notes"] == []
    assert c.get("/me", headers=PRO).json()["notes"] == []
    assert c.post("/feedback/notes/seen", json={"ids": [fid]}).status_code == 401


def test_the_fix_is_emailed_only_to_someone_who_already_gets_alert_emails(w):
    c = w["client"]
    uid = c.get("/me", headers=PRO).json()["id"]
    db.update_profile(uid, alert_email="pro-alerts@example.com")
    for _ in range(2):
        c.post("/feedback/figure", headers=PRO, json=FIG)
    a, b = [r["id"] for r in c.get("/admin/feedback", headers=ADMIN).json()["rows"]]
    w["sent"].clear()
    c.put(f"/admin/feedback/{a}", headers=ADMIN, json={"status": "fixed"})
    (to, subject, body), = w["sent"]
    assert to == "pro-alerts@example.com" and subject == "A figure you reported was fixed" and "EBITDA margin" in body
    alerts.set_alert_emails(uid, False)               # unsubscribed from alert emails: the note only
    w["sent"].clear()
    c.put(f"/admin/feedback/{b}", headers=ADMIN, json={"status": "fixed"})
    assert w["sent"] == [] and len(json.loads(db.get_setting(feedback.NOTE_KEY + uid))) == 2


def test_other_reports_marked_fixed_leave_no_note(w):
    c = w["client"]
    c.post("/feedback", headers=PRO, json={"type": "broken", "text": "The chart froze on 1h."})
    fid = c.get("/admin/feedback", headers=ADMIN).json()["rows"][0]["id"]
    c.put(f"/admin/feedback/{fid}", headers=ADMIN, json={"status": "fixed"})
    assert c.get("/me", headers=PRO).json()["notes"] == []


def test_a_visitors_public_company_page_says_to_sign_in_to_report_a_figure():
    from app import stock_pages
    f = {"name": "Example Ltd", "symbol": "EXAMPLE", "price": 100.0, "low52": 80.0, "high52": 120.0, "pe": 20.0, "market_cap": 1000.0}
    html = stock_pages.render(f, "IN", "EXAMPLE", "Example Ltd")
    assert "data-report" in html and "Sign in to report it" in html and "/research/IN/EXAMPLE#co-numbers" in html
    assert "data-report" not in stock_pages.render(None, "IN", "EXAMPLE", "Example Ltd")
