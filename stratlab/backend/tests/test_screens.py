"""Stock screens: the index built from stored company pages, every filter, sorting, facts-only wording, saved screens
and their plan limits, the weekly note of new matches (throttled, confirmed address only, run once), the endpoints,
and the "as of" lines on every page that shows company numbers. Plus a fuzz of the filters."""
import json
import random
import re
from datetime import datetime, timedelta, timezone

import pytest

from app import alerts, db, main, mail_tokens, screens, stock_pages
from app.config import settings
from app.plans import PLANS, plan_info
from tests import world as W
from tests.fake_db import headers

SATURDAY = datetime(2026, 10, 3, 4, 0, tzinfo=timezone.utc)          # 09:30 IST
PROVIDERS = re.compile(r"kite|zerodha|yahoo|screener|finnhub|edgar|nseindia|bseindia", re.I)
ADVICE = re.compile(r"\b(buy|sell|hold|accumulate|avoid|best|top picks?|undervalued|overvalued|cheap|expensive|score|target)\b", re.I)


def facts(sym, name, **kw):
    f = {"region": "IN", "symbol": sym, "name": name, "industry": [kw.pop("sector", "Energy"), "Oil"], "price": 100.0, "high52": 125.0,
         "low52": 80.0, "price_at": "2026-10-01", "market_cap": 25000, "pe": 20.0, "roe": 15.0, "roce": 18.0, "div_yield": 1.2,
         "net_margin": 10.0, "opm": 18.0, "debt_equity": 0.4, "bank": False, "growth": {"sales_cagr_3y": 12.0},
         "stage": 2, "red_flags": 0, "filings": [], "built_at": "2026-10-02T10:00:00+00:00"}
    f.update(kw)
    return f


ROWS = [
    facts("RELIANCE", "Reliance Industries"),
    facts("TCS", "Tata Consultancy", sector="Information Technology", pe=30.0, debt_equity=0.0, stage=3, market_cap=1200000,
          growth={"sales_cagr_3y": 8.0}, red_flags=2),
    facts("SMALLCO", "Small Co", sector="Information Technology", market_cap=900, pe=None, roe=-4.0, stage=4, price=50, high52=100,
          growth={"sales_cagr_3y": None}),
    facts("HDFCBANK", "HDFC Bank", sector="Financials", bank=True, opm=30.0, debt_equity=6.0, stage=1),
]


def store_pages(region="IN", rows=ROWS, ts=None):
    for f in rows:
        db.set_setting(f"stocks:page:{region}:{f['symbol']}", json.dumps({"ts": ts or 1e10, "facts": f}))


@pytest.fixture
def w(monkeypatch):
    world = W.build(monkeypatch)
    screens._mem.clear()
    yield world
    world["close"]()
    screens._mem.clear()


def paid(monkeypatch):
    monkeypatch.setattr(settings, "RAZORPAY_KEY_ID", "rzp_live_x")
    monkeypatch.setattr(settings, "RAZORPAY_KEY_SECRET", "secret")
    monkeypatch.setattr(settings, "RAZORPAY_PLAN_BASIC", "plan_b")
    monkeypatch.setattr(settings, "RAZORPAY_PLAN_PRO", "plan_p")


def syms(out):
    return [r["symbol"] for r in out["rows"]]


# ---------- the index ----------
def test_a_row_is_the_page_facts_in_plain_numbers(w):
    r = screens.row("IN", "SMALLCO", ROWS[2])
    assert r["from_high"] == -50.0 and r["sales_cagr_3y"] is None and r["pe"] is None and r["sector"] == "Information Technology"
    bank = screens.row("IN", "HDFCBANK", ROWS[3])
    assert bank["opm"] is None and bank["debt_equity"] is None          # banks don't report these the same way
    assert screens.row("IN", "X", {}) is None and screens.row("IN", "X", "junk") is None
    us = screens.row("US", "AAPL", facts("AAPL", "Apple", red_flags=3))
    assert us["red_flags"] is None                                       # red-flag filings are an India rule


def test_red_flags_are_counted_from_old_pages_filings(w):
    old = facts("OLD", "Old Page", filings=[{"at": "2026-09-20", "title": "QIP (fund raise): Approval of QIP"},
                                           {"at": "2026-01-01", "title": "Promoter pledge or encumbrance: pledge"},
                                           {"at": "2026-09-25", "title": "Financial results: Q1"}])
    old.pop("red_flags")
    assert screens.row("IN", "OLD", old)["red_flags"] == 1               # only the last three months count


def test_the_index_gathers_stored_pages_and_is_read_from_memory(w, monkeypatch):
    store_pages()
    db.set_setting("stocks:page:IN:EMPTY", json.dumps({"ts": 1, "facts": None}))     # a company the sources had nothing on
    db.set_setting("stocks:page:IN:BROKEN", "{not json")
    index = screens.build_index("IN")
    assert [r["symbol"] for r in index["rows"]] == ["HDFCBANK", "RELIANCE", "SMALLCO", "TCS"]   # alphabetical by name
    reads = []
    real = db.get_setting
    monkeypatch.setattr(db, "get_setting", lambda k: reads.append(k) or real(k))
    for _ in range(3):
        assert len(screens.load_index("IN")["rows"]) == 4
    assert reads.count("screens:index:IN") == 1
    assert screens.as_of(index) == "2026-10-01"


# ---------- the filters ----------
@pytest.fixture
def idx(w):
    store_pages()
    return screens.build_index("IN")


@pytest.mark.parametrize("filters,want", [
    ({}, ["HDFCBANK", "RELIANCE", "SMALLCO", "TCS"]),
    ({"sector": ["Information Technology"]}, ["SMALLCO", "TCS"]),
    ({"cap": ["large"]}, ["HDFCBANK", "RELIANCE", "TCS"]),
    ({"cap": ["micro", "small"]}, ["SMALLCO"]),
    ({"stage": [2, 3]}, ["RELIANCE", "TCS"]),
    ({"red_flags": "yes"}, ["TCS"]),
    ({"red_flags": "no"}, ["HDFCBANK", "RELIANCE", "SMALLCO"]),
    ({"ranges": {"sales_cagr_3y": {"min": 10}}}, ["HDFCBANK", "RELIANCE"]),
    ({"ranges": {"sales_cagr_3y": {"max": 10}}}, ["TCS"]),                  # no growth figure: not a match either way
    ({"ranges": {"pe": {"min": 10, "max": 25}}}, ["HDFCBANK", "RELIANCE"]),
    ({"ranges": {"debt_equity": {"max": 0.5}}}, ["RELIANCE", "SMALLCO", "TCS"]),
    ({"ranges": {"opm": {"min": 0}}}, ["RELIANCE", "SMALLCO", "TCS"]),
    ({"ranges": {"roe": {"max": 0}}}, ["SMALLCO"]),
    ({"ranges": {"roce": {"min": 18}, "div_yield": {"min": 1}}}, ["HDFCBANK", "RELIANCE", "SMALLCO", "TCS"]),
    ({"ranges": {"net_margin": {"min": 11}}}, []),
    ({"ranges": {"from_high": {"max": -30}}}, ["SMALLCO"]),
    ({"ranges": {"pe": {"min": None, "max": None}}}, ["HDFCBANK", "RELIANCE", "SMALLCO", "TCS"]),   # empty bounds: no condition
])
def test_each_filter(idx, filters, want):
    assert syms(screens.run("IN", filters, index=idx)) == want


def test_sort_by_any_column_with_missing_values_last(idx):
    assert syms(screens.run("IN", {}, "pe", index=idx)) == ["HDFCBANK", "RELIANCE", "TCS", "SMALLCO"]
    assert syms(screens.run("IN", {}, "pe", True, index=idx)) == ["TCS", "HDFCBANK", "RELIANCE", "SMALLCO"]
    assert syms(screens.run("IN", {}, "market_cap", True, index=idx))[0] == "TCS"
    assert syms(screens.run("IN", {}, "symbol", index=idx)) == ["HDFCBANK", "RELIANCE", "SMALLCO", "TCS"]
    page = screens.run("IN", {}, limit=2, offset=2, index=idx)
    assert page["total"] == 4 and syms(page) == ["SMALLCO", "TCS"]
    with pytest.raises(screens.ScreenError):
        screens.run("IN", {}, "score", index=idx)


def test_us_screens_have_no_red_flag_filter(w):
    store_pages("US", [facts("AAPL", "Apple", market_cap=3000000, red_flags=None)])
    screens.build_index("US")
    assert syms(screens.run("US", {"red_flags": "yes", "cap": ["large"]})) == ["AAPL"]   # ignored for the US
    with pytest.raises(screens.ScreenError):
        screens.clean("US", {"cap": ["mega"]})


@pytest.mark.parametrize("region,filters", [
    ("UK", {}), ("IN", "junk"), ("IN", {"sector": "Energy"}), ("IN", {"sector": [1]}), ("IN", {"sector": ["x" * 200]}),
    ("IN", {"cap": ["huge"]}), ("IN", {"stage": [5]}), ("IN", {"stage": [2.5]}), ("IN", {"stage": [True]}),
    ("IN", {"red_flags": "maybe"}), ("IN", {"ranges": []}), ("IN", {"ranges": {"score": {"min": 1}}}),
    ("IN", {"ranges": {"pe": 5}}), ("IN", {"ranges": {"pe": {"min": "5"}}}), ("IN", {"ranges": {"pe": {"min": float("nan")}}}),
    ("IN", {"ranges": {"pe": {"max": float("inf")}}}), ("IN", {"ranges": {"pe": {"min": 1e12}}}),
    ("IN", {"ranges": {"pe": {"min": 30, "max": 10}}}), ("IN", {"ranges": {"pe": {"min": True}}}),
])
def test_conditions_that_make_no_sense_are_refused_in_words(region, filters):
    with pytest.raises(screens.ScreenError) as e:
        screens.clean(region, filters)
    assert str(e.value) and not PROVIDERS.search(str(e.value))


def test_fuzz_the_filters_never_crash(idx):
    """Random junk in every shape: either a clean ScreenError or a result, never anything else."""
    rng = random.Random(11)
    junk = [None, "", "x", 0, -1, 1.5, 1e309, float("nan"), True, [], {}, [1, "a"], {"min": "x"}, {"min": 1, "max": 0},
            "<script>", "\x00", ["Energy"], [2], ["large"], "yes", {"min": -5}, 90, 365.0, "on", "off", ["asm", "t2t"], ["xyz"]]
    keys = ["sector", "cap", "stage", "red_flags", "insider_buy", "insider_days", "surveillance", "surv_lists", "ranges", "other"]
    for _ in range(600):
        f = {rng.choice(keys): rng.choice(junk) for _ in range(rng.randint(0, 4))}
        if rng.random() < 0.5:
            f["ranges"] = {rng.choice(list(screens.RANGES) + ["nope"]): rng.choice(junk) for _ in range(rng.randint(0, 3))}
        try:
            out = screens.run(rng.choice(["IN", "US", "in", "", "XX"]), f, rng.choice(list(screens.COLUMNS) + ["bad"]),
                              rng.random() < 0.5, rng.randint(-5, 900), rng.randint(-5, 9), index=idx)
        except screens.ScreenError:
            continue
        assert out["total"] >= len(out["rows"]) and json.dumps(out, allow_nan=False)


def test_labels_and_help_are_plain_facts_without_provider_names(w):
    m = screens.meta("IN")
    text = json.dumps(m)
    assert not PROVIDERS.search(text) and not ADVICE.search(text), (PROVIDERS.search(text) or ADVICE.search(text)).group(0)
    assert {r["id"] for r in m["ranges"]} == set(screens.RANGES) and all(r["help"] for r in m["ranges"])
    assert all(m["help"][k] for k in ("market", "sector", "cap", "stage", "red_flags"))
    assert screens.meta("US")["red_flags"] is False and screens.meta("nope")["region"] == "IN"


def test_conditions_in_words(w):
    f = screens.clean("IN", {"sector": ["Energy"], "cap": ["large"], "stage": [2], "red_flags": "no",
                             "ranges": {"pe": {"min": 5, "max": 20}, "roe": {"min": 15}, "debt_equity": {"max": 1}}})
    assert screens.describe("IN", f) == ["Sector: Energy", "Size: Large", "P/E (price to earnings) between 5 and 20",
                                         "Return on equity (ROE) at least 15%", "Debt to equity at most 1", "Stage 2",
                                         "No red-flag filings in the last 3 months"]


# ---------- the endpoints ----------
def test_run_and_meta_through_the_api_never_reach_a_source(w, monkeypatch):
    store_pages()
    screens.build_index("IN")
    calls = []
    monkeypatch.setattr(main.stock_page_store, "gather", lambda *a: calls.append(a))
    for name in w["faults"]:
        w["faults"][name].mode = "down"                  # every data source down: screens still answer
    c, h = w["client"], headers("free-token")
    r = c.post("/research/screens/run", headers=h, json={"region": "IN", "filters": {"sector": ["Energy"]}, "sort": "pe", "desc": True})
    assert r.status_code == 200, r.text
    body = r.json()
    assert [x["symbol"] for x in body["rows"]] == ["RELIANCE"] and body["as_of"] == "2026-10-01" and body["indexed"] == 4
    assert c.get("/research/screens/meta?region=IN", headers=h).json()["sectors"] == ["Energy", "Financials", "Information Technology"]
    assert c.post("/research/screens/run", headers=h, json={"region": "IN", "filters": {"stage": [9]}}).json()["detail"]["code"] == "bad_screen"
    assert c.post("/research/screens/run", json={"region": "IN"}).status_code == 401
    assert calls == [] and w["ai"].calls == 0


def test_saved_screens_through_the_api(w):
    store_pages()
    screens.build_index("IN")
    c, h = w["client"], headers("pro-token")
    assert c.get("/research/screens/saved", headers=h).json()["items"] == []
    body = {"name": "  Low debt   energy ", "region": "IN", "filters": {"sector": ["Energy"], "ranges": {"debt_equity": {"max": 1}}}, "notify": True}
    r = c.post("/research/screens/saved", headers=h, json=body)
    assert r.status_code == 200, r.text
    s = r.json()["screen"]
    assert s["name"] == "Low debt energy" and s["notify"] and s["matched_count"] == 1 and "matched" not in s
    assert s["conditions"] == ["Sector: Energy", "Debt to equity at most 1"]
    r = c.put(f"/research/screens/saved/{s['id']}", headers=h, json={**body, "name": "IT", "filters": {"sector": ["Information Technology"]}})
    assert r.status_code == 200 and r.json()["screen"]["name"] == "IT" and r.json()["screen"]["matched_count"] == 2
    assert c.put("/research/screens/saved/ffffff", headers=h, json=body).status_code == 404
    assert c.put("/research/screens/saved/..%2Fx", headers=h, json=body).status_code == 404
    assert c.post("/research/screens/saved", headers=h, json={**body, "filters": {"cap": ["giant"]}}).status_code == 400
    assert c.delete(f"/research/screens/saved/{s['id']}", headers=h).json()["items"] == []
    assert c.delete(f"/research/screens/saved/{s['id']}", headers=h).status_code == 404


def test_plan_limits_free_2_basic_10_pro_25(w, monkeypatch):
    assert (PLANS["free"]["screens"], PLANS["basic"]["screens"], PLANS["pro"]["screens"]) == (2, 10, 25)
    monkeypatch.setattr(settings, "RAZORPAY_KEY_ID", "")
    assert plan_info("free")["screens"] == 25                       # open to everyone until payments go live
    paid(monkeypatch)
    assert [plan_info(p)["screens"] for p in ("free", "basic", "pro")] == [2, 10, 25]
    c, h = w["client"], headers("free-token")
    body = {"name": "Mine", "region": "IN", "filters": {}}
    for _ in range(2):
        assert c.post("/research/screens/saved", headers=h, json=body).status_code == 200
    r = c.post("/research/screens/saved", headers=h, json=body)
    assert r.status_code == 402 and "2 saved screens." in r.json()["detail"]["message"] and "Basic" in r.json()["detail"]["message"]
    assert c.get("/research/screens/saved", headers=h).json()["limit"] == 2
    assert c.get("/me", headers=h).json()["plan_info"]["screens"] == 2


# ---------- the weekly note ----------
@pytest.fixture
def outbox(monkeypatch):
    sent = []
    monkeypatch.setattr(alerts, "email_ready", lambda: True)
    monkeypatch.setattr(alerts, "send_email", lambda to, subject, text, html=None, headers=None: sent.append(
        {"to": to, "subject": subject, "text": text, "html": html, "headers": headers}))
    return sent


def reader(uid, email, plan="pro", confirmed=True):
    db.get_profile(uid, email)
    db.update_profile(uid, plan=plan, plan_status="active", alert_email=email)
    if confirmed:
        db.set_setting(alerts.CONFIRMED + uid, email)


def test_the_weekly_note_lists_only_new_matches_once(w, outbox):
    store_pages(rows=ROWS[:2] + [facts("NEWCO", "New Co", stage=4)])
    screens.build_index("IN")
    reader("u-pro", "pro@example.com")
    s = screens.save("u-pro", {"name": "Stage 2 or 3", "region": "IN", "filters": {"stage": [2, 3]}, "notify": True}, 25)
    assert sorted(s["matched"]) == ["RELIANCE", "TCS"]
    limit = lambda p: 25                                   # noqa: E731
    assert screens.weekly(SATURDAY, db.get_profile, limit) == 0 and outbox == []      # nothing new yet
    store_pages(rows=[facts("NEWCO", "New Co", stage=2)])
    screens.build_index("IN")
    assert screens.weekly(SATURDAY, db.get_profile, limit) == 1
    m = outbox[0]
    assert m["to"] == "pro@example.com" and "1 company newly match" in m["subject"] and "Stage 2 or 3" in m["subject"]
    assert "New Co (NEWCO)" in m["text"] and "/research/IN/NEWCO" in m["text"] and "RELIANCE" not in m["text"]
    assert "Numbers as of 1 Oct 2026" in m["text"] and "Numbers as of" in m["html"]
    assert "/unsubscribe?t=" in m["headers"]["List-Unsubscribe"] and "{unsubscribe_url}" not in m["text"] + m["html"]
    for t in (m["text"], m["html"]):
        assert not PROVIDERS.search(t) and not ADVICE.search(re.sub(r"<[^>]+>", " ", t))
    assert screens.weekly(SATURDAY, db.get_profile, limit) == 0                       # the same match isn't sent twice


def test_the_weekly_note_goes_only_to_a_confirmed_address_in_one_message(w, outbox):
    store_pages(rows=ROWS[:1] + [facts("NEWCO", "New Co", stage=4)])
    screens.build_index("IN")
    reader("u-pro", "pro@example.com", confirmed=False)
    for i in range(3):
        screens.save("u-pro", {"name": f"S{i}", "region": "IN", "filters": {"stage": [1]}, "notify": i < 2}, 25)
    store_pages(rows=[facts("NEWCO", "New Co", stage=1)])
    screens.build_index("IN")
    assert screens.weekly(SATURDAY, db.get_profile, lambda p: 25) == 0 and outbox == []      # not confirmed: no email
    reader("u-pro", "pro@example.com")
    assert screens.weekly(SATURDAY, db.get_profile, lambda p: 25) == 1                       # still new: sent now
    m = outbox[0]
    assert "2 companies newly match 2 of your screens" in m["subject"] and "S0" in m["text"] and "S1" in m["text"]
    assert "S2" not in m["text"]                                                             # its note is off
    row = json.loads(db.get_setting(screens.KEY + "u-pro"))
    assert len(row["sent"]) == 1 and all("NEWCO" in s["matched"] for s in row["items"])
    assert screens.weekly(SATURDAY, db.get_profile, lambda p: 25) == 0


def test_the_weekly_note_keeps_to_the_message_limits_and_the_plan(w, outbox):
    store_pages(rows=ROWS[:1] + [facts("NEWCO", "New Co", stage=4)])
    screens.build_index("IN")
    reader("u-pro", "pro@example.com")
    screens.save("u-pro", {"name": "Old", "region": "IN", "filters": {"stage": [1]}, "notify": True}, 25)
    screens.save("u-pro", {"name": "Newer", "region": "IN", "filters": {"stage": [1]}, "notify": True}, 25)
    row = json.loads(db.get_setting(screens.KEY + "u-pro"))
    row["sent"] = [SATURDAY.isoformat()] * 5                 # five messages this hour already
    db.set_setting(screens.KEY + "u-pro", json.dumps(row))
    store_pages(rows=[facts("NEWCO", "New Co", stage=1)])
    screens.build_index("IN")
    assert screens.weekly(SATURDAY, db.get_profile, lambda p: 25) == 0 and outbox == []
    assert all("NEWCO" not in s["matched"] for s in screens.items("u-pro"))                  # held back, still new
    later = SATURDAY + timedelta(days=1, minutes=1)
    assert screens.weekly(later, db.get_profile, lambda p: 1) == 1                            # over the plan: the oldest only
    assert "\u201cOld\u201d" in outbox[0]["subject"]


def test_a_company_only_just_gathered_into_the_index_is_not_new(w, outbox):
    store_pages(rows=ROWS[:1] + [facts("OLDCO", "Old Co", stage=4)])
    screens.build_index("IN")
    reader("u-pro", "pro@example.com")
    screens.save("u-pro", {"name": "Stage 2", "region": "IN", "filters": {"stage": [2]}, "notify": True}, 25)
    assert screens.weekly(SATURDAY, db.get_profile, lambda p: 25) == 0
    store_pages(rows=[facts("JUSTIN", "Just Indexed", stage=2), facts("OLDCO", "Old Co", stage=2)])
    screens.build_index("IN")
    assert screens.weekly(SATURDAY + timedelta(days=7), db.get_profile, lambda p: 25) == 1
    assert "Old Co (OLDCO)" in outbox[0]["text"] and "JUSTIN" not in outbox[0]["text"]       # it was only gathered
    assert "JUSTIN" in screens.items("u-pro")[0]["matched"]                                   # and never reported later
    assert screens.weekly(SATURDAY + timedelta(days=14), db.get_profile, lambda p: 25) == 0


def test_one_users_trouble_doesnt_stop_the_others_notes(w, outbox):
    store_pages(rows=ROWS[:1] + [facts("NEWCO", "New Co", stage=4)])
    screens.build_index("IN")
    for uid in ("u-basic", "u-pro"):
        reader(uid, f"{uid}@example.com")
        screens.save(uid, {"name": "Stage 1", "region": "IN", "filters": {"stage": [1]}, "notify": True}, 25)
    store_pages(rows=[facts("NEWCO", "New Co", stage=1)])
    screens.build_index("IN")

    def limit(p):
        if p["id"] == "u-basic":
            raise RuntimeError("plan lookup failed")
        return 25
    assert screens.weekly(SATURDAY, db.get_profile, limit) == 1 and [m["to"] for m in outbox] == ["u-pro@example.com"]


def test_the_unsubscribe_link_turns_screen_notes_off(w):
    screens.save("u-pro", {"name": "A", "region": "IN", "filters": {}, "notify": True}, 25)
    token = mail_tokens.make("u-pro", "unsubscribe", "screens")
    c = w["client"]
    assert "saved stock screens" in c.get("/unsubscribe", params={"t": token}).text and screens.items("u-pro")[0]["notify"]
    assert c.post("/unsubscribe", params={"t": token}).status_code == 200
    assert not screens.items("u-pro")[0]["notify"]


def test_the_job_runs_once_on_saturday_morning(w, monkeypatch):
    runs = []
    monkeypatch.setattr(screens, "weekly", lambda now, pf, lf: runs.append(now) or 0)
    job = screens.Job(db.get_profile, lambda p: 25)
    assert job.tick(SATURDAY - timedelta(hours=1)) == 0 and runs == []        # 08:30 IST: not yet
    job.tick(SATURDAY)
    job.tick(SATURDAY + timedelta(minutes=5))
    screens.Job(db.get_profile, lambda p: 25).tick(SATURDAY + timedelta(minutes=10))   # after a restart: the marker holds
    assert len(runs) == 1
    assert screens.Job(db.get_profile, lambda p: 25).tick(SATURDAY + timedelta(days=1)) == 0 and len(runs) == 1   # Sunday


# ---------- the background index job ----------
def test_the_indexer_builds_missing_pages_through_the_ration_then_the_index(w, monkeypatch):
    built = []
    real = main.stock_page_facts
    listed = {"IN": ["INFY", "ONGC", "RELIANCE", "TCS"], "US": ["AAPL"]}
    monkeypatch.setattr(stock_pages, "companies", lambda region: {s: {"name": None, "sym": s, "bse": None} for s in listed[region]})
    monkeypatch.setattr(stock_pages, "_seeds", lambda region: {"RELIANCE", "TCS"})
    store = stock_pages.Pages(lambda r, co: built.append(co["sym"]) or real(r, co), per_minute=3)
    monkeypatch.setattr(main, "stock_page_store", store)
    job = screens.Indexer(main.screen_warm, warm_per_run=5, gap=0)
    status = job.run_once(sleep=lambda s: None)
    assert built == ["RELIANCE", "TCS", "INFY"]          # the sector lists' companies first; the ration stops the run
    assert status["rows"]["IN"] >= 1 and "Busy" in status["last_error"]
    index = screens.load_index("IN")
    assert {r["symbol"] for r in index["rows"]} <= set(built) and w["ai"].calls == 0
    r = next(r for r in index["rows"])
    assert r["price"] and r["name"] and not PROVIDERS.search(json.dumps(r))


def test_the_indexer_survives_storage_errors(w, monkeypatch):
    monkeypatch.setattr(db, "all_settings_with_prefix", lambda p, page=1000: (_ for _ in ()).throw(RuntimeError("db down")))
    status = screens.Indexer(None).run_once(sleep=lambda s: None)
    assert "db down" in status["last_error"]


def test_stored_pages_carry_roce_and_red_flags(w):
    c = w["client"]
    assert c.get("/stocks/in/RELIANCE").status_code == 200
    f = json.loads(db.get_setting("stocks:page:IN:RELIANCE"))["facts"]
    assert "roce" in f and isinstance(f["red_flags"], int)


# ---------- "as of" on every page with company numbers ----------
def test_as_of_on_company_deep_dive_holdings_and_newsletters(w):
    c, h = w["client"], headers("pro-token")
    co = c.get("/research/company/IN/RELIANCE", headers=h).json()
    assert datetime.fromisoformat(co["as_of"]) and co["numbers_at"]
    assert c.get("/research/company/US/AAPL", headers=h).json()["as_of"]
    deep = c.get("/research/deep/RELIANCE?region=IN", headers=h).json()
    assert deep["as_of"] and deep["numbers_at"] and deep["price_at"]
    assert "prices_at" in c.get("/holdings", headers=h).json()
    from app.newsletter import write
    issue = {"subject": "Market Brief India", "summary": "x", "sections": [], "id": "market.IN.2026-10-02",
             "at": "2026-10-02T16:15:00+05:30"}
    html, text = write.render(issue)
    assert "Prices and numbers as of 2 Oct 2026, 16:15 IST" in text and "as of 2 Oct 2026, 16:15 IST" in html
    for body in (json.dumps({k: co[k] for k in ("as_of", "numbers_at")}), text):
        assert not PROVIDERS.search(body)
