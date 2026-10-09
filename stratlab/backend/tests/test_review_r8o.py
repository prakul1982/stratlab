"""Round 8 owner review of the live site (9 Oct 2026, India open), the server's side: TCS's public yield from a stored page
of an older definition, a hidden daily cap on AI reads that blocked the market mood, NCLT merger meetings read as
insolvency, AI captions that predict, BRK-B and Visa missing from lists by size, euro and pound prices beside a rupee
charge, Admin's AI tile and live price feed count, advice-style headlines, a "live" chain nine minutes old, and Eni's
market value on a share count that held treasury shares. tests/fixtures/sec_r8o holds the SEC's own public data for
Eni, trimmed to what the tests read."""
import json
import time
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException

from app import main  # noqa: F401, I001  (first: the app loads the newsletter job before the modules built on it)
from app import corp_actions, db, plans, positioning, pricing, redflags as R, screens, stock_pages
from app.config import settings
from app.intel import ai as A, filings as F, grounding as G, news, routes, sec

FIX = Path(__file__).parent / "fixtures" / "sec_r8o"
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def mem(monkeypatch):
    """The settings table in memory."""
    store: dict = {}
    monkeypatch.setattr(db, "get_setting", lambda k: store.get(k))
    monkeypatch.setattr(db, "set_setting", lambda k, v: store.__setitem__(k, v))
    monkeypatch.setattr(db, "delete_setting", lambda k: store.pop(k, None))
    monkeypatch.setattr(db, "all_settings_with_prefix", lambda p, *a: [(k, v) for k, v in sorted(store.items()) if k.startswith(p)])
    monkeypatch.setattr(db, "prefetch_settings", lambda keys: None)
    screens._mem.clear()
    screens._built.clear()
    yield store
    screens._mem.clear()
    screens._built.clear()


def us(**kw) -> dict:
    base = {"region": "US", "symbol": "ACME", "name": "Acme Inc", "exchange": "Listed in the US", "industry": ["Services", "Payments"],
            "currency": "USD", "unit": "$ million", "market_cap_unit": "$ million", "price": 50.0, "price_at": "2026-10-08",
            "price_basis": "close", "high52": 60.0, "low52": 40.0, "market_cap": 50_000.0, "pe": 20.0, "div_yield": 1.0,
            "net_margin": 10.0, "opm": 20.0, "years": [{"year": "Dec 2025", "sales": 40_000.0, "profit": 20_000.0, "opm": 60.0, "debt": 100.0}],
            "growth": {}, "filings": [], "built_at": "2026-10-09T05:00:00+00:00", "v": stock_pages.FACTS_VERSION, "sales_usd": 40_000.0}
    return {**base, **kw}


def india(**kw) -> dict:
    base = {**us(), "region": "IN", "symbol": "TCS", "name": "Tata Consultancy Services Ltd", "exchange": "NSE", "currency": "INR",
            "unit": "₹ crore", "market_cap_unit": "₹ crore", "industry": ["Information Technology", "IT - Software"], "price": 2076.0}
    base.pop("sales_usd")
    return {**base, **kw}


# ---------- R8O-001: TCS's public yield, 3.08% from a stored page of an older definition ----------
TCS_DIVS = [{"kind": "dividend", "sub": s, "amount": a, "ex_date": d} for d, a, s in
            (("2025-10-15", 11, "interim"), ("2026-01-16", 11, "interim"), ("2026-01-16", 46, "special"), ("2026-05-25", 31, "final"),
             ("2026-07-15", 12, "interim"), ("2025-07-17", 11, "interim"))]


def test_an_indian_page_of_an_older_facts_version_is_rebuilt_like_a_us_one():
    # the cause: PR 173's yield went live at 04:09 UTC on 9 Oct, and TCS's page, stored the evening before, stayed "fresh"
    # until India's next settled close, since only US pages were checked for their version
    assert stock_pages.FACTS_VERSION >= 5
    close = stock_pages.last_close("IN")[1].timestamp() + stock_pages.settle("IN")
    old = {"ts": close + 60, "facts": india(v=4, div_yield=3.08)}
    now = {"ts": close + 60, "facts": india()}
    assert not stock_pages.fresh(old, "IN", now=close + 120) and stock_pages.fresh(now, "IN", now=close + 120)


def test_a_stored_page_served_while_it_cant_be_rebuilt_takes_the_dividends_lists_yield(mem, monkeypatch):
    seen = {}
    monkeypatch.setattr(corp_actions, "actions_for", lambda r, s, src=None, today=None, fetch=True, **k: seen.update(fetch=fetch, src=src) or TCS_DIVS)
    monkeypatch.setattr(corp_actions, "hist_load", lambda r, s: {"at": "2026-10-08T12:00", "rows": TCS_DIVS})
    monkeypatch.setattr(main.research_hub.yahoo, "events", lambda *a: pytest.fail("a stored page's yield reads no source"))
    mem["stocks:page:IN:TCS"] = json.dumps({"ts": time.time() - 3600, "facts": india(v=4, div_yield=3.08, price_at="2026-10-08")})
    pages = stock_pages.Pages(lambda r, co: pytest.fail("no build allowed"), per_minute=0, older=main.stock_page_older_facts)
    f = pages.get("IN", "TCS", {"sym": "TCS", "bse": None})
    assert f["div_yield"] == 5.35 and seen == {"fetch": False, "src": None}          # ₹111 over ₹2,076, specials included
    # a build that fails serves the stored page the same way
    pages = stock_pages.Pages(lambda r, co: (_ for _ in ()).throw(RuntimeError("down")), per_minute=6, older=main.stock_page_older_facts)
    assert pages.get("IN", "TCS", {"sym": "TCS", "bse": None})["div_yield"] == 5.35
    # a page of today's version is left as it is
    assert main.stock_page_older_facts("IN", "TCS", india(div_yield=1.0))["div_yield"] == 1.0
    # no stored list and no source read: the stored page's own figure stays (never another definition worked out here)
    monkeypatch.setattr(corp_actions, "actions_for", lambda *a, **k: [])
    monkeypatch.setattr(corp_actions, "hist_load", lambda r, s: {"at": None, "rows": []})
    assert main.stock_page_older_facts("IN", "TCS", india(v=4, div_yield=3.08))["div_yield"] == 3.08


def test_a_page_built_now_takes_the_same_yield_as_the_app(monkeypatch):
    monkeypatch.setattr(corp_actions, "actions_for", lambda *a, **k: TCS_DIVS)
    monkeypatch.setattr(corp_actions, "hist_load", lambda r, s: {"at": "2026-10-08T12:00", "rows": TCS_DIVS})
    assert main.page_dividend_yield("IN", "TCS", 2076.0, "2026-10-08", {"sym": "TCS", "bse": None}) == 5.35
    # the app's own card at its own price: the same dividends (₹111) over ₹2,170
    assert round(111 / 2170 * 100, 1) == 5.1


def test_the_indexer_builds_an_older_indian_page_again_first(mem, monkeypatch):
    mem["stocks:page:IN:TCS"] = json.dumps({"ts": time.time(), "facts": india(v=4)})
    monkeypatch.setattr(screens, "with_ranks", lambda rows: rows)
    index = screens.build_index("IN", store=False)
    assert "TCS" in index["_empty"]


# ---------- R8O-002: a daily cap on fresh AI reads, said; none for admins and Pro; never on the market mood ----------
@pytest.fixture
def usage(monkeypatch):
    used: list[tuple[str, str]] = []
    monkeypatch.setattr(db, "count_usage", lambda u, k, since: sum(1 for uu, kk in used if uu == u and kk == k))
    monkeypatch.setattr(db, "add_usage", lambda u, k: used.append((u, k)))
    monkeypatch.setattr(settings, "RESEARCH_AI_PER_DAY", 2)
    monkeypatch.setattr(settings, "ADMIN_EMAILS", "owner@example.com")
    A._cache.clear()
    yield used
    A._cache.clear()


OWNER = {"id": "o", "email": "owner@example.com", "_email_verified": True, "plan": "free", "_plan": "pro", "_paid_plan": "free"}
PRO = {"id": "p", "email": "p@example.com", "plan": "pro", "plan_status": "active", "_plan": "pro", "_paid_plan": "pro"}
BASIC = {"id": "b", "email": "b@example.com", "plan": "basic", "plan_status": "active", "_plan": "pro", "_paid_plan": "basic"}
FREE = {"id": "f", "email": "f@example.com", "plan": "free", "_plan": "pro", "_paid_plan": "free"}      # Pro by the launch offer


def read(n=[0]):
    n[0] += 1
    return {"summary": f"read {n[0]}"}


def test_who_has_a_cap(usage):
    assert routes.ai_cap(OWNER) is None and routes.ai_cap(PRO) is None
    assert routes.ai_cap(BASIC) == 2 and routes.ai_cap(FREE) == 2               # the plan paid for, not the launch offer's Pro
    assert routes.ai_auto_counts(FREE) and not routes.ai_auto_counts(BASIC) and not routes.ai_auto_counts(OWNER)
    assert plans.ai_reads_per_day("pro") is None and plans.ai_reads_per_day("free") == 2
    assert plans.public_plans()["pro"]["ai_reads_per_day"] is None and plans.plan_info("basic")["ai_reads_per_day"] == 2


def test_the_owner_is_never_capped_and_free_is(usage):
    for i in range(5):
        routes.ai_call(OWNER, "sector", ("IN", f"t{i}"), 60, False, read)
    for i in range(2):
        routes.ai_call(FREE, "sector", ("IN", f"f{i}"), 60, False, read)
    with pytest.raises(HTTPException) as e:
        routes.ai_call(FREE, "sector", ("IN", "f9"), 60, False, read)
    assert e.value.detail["code"] == "research_ai_limit" and "midnight India time" in e.value.detail["message"]
    # a read already written costs nobody anything, past the cap too
    assert routes.ai_call(FREE, "sector", ("IN", "t1"), 60, False, read)["summary"]


def test_the_market_mood_never_counts_and_is_never_refused(usage):
    for i in range(2):
        routes.ai_call(FREE, "sector", ("IN", f"x{i}"), 60, False, read)
    assert routes.ai_reads_today(FREE) == 2
    got = routes.ai_call(FREE, "pulse", ("IN", "", "h", "k"), 60, False, read, counted=False, min_age=300)
    assert got["summary"] and routes.ai_reads_today(FREE) == 2
    # "Ask again" on a mood under five minutes old is that mood, not a new one written for everyone
    assert routes.ai_call(FREE, "pulse", ("IN", "", "h", "k"), 60, True, read, counted=False, min_age=300) == got


def test_the_pulse_and_company_routes_say_what_counts(usage, monkeypatch):
    calls = []

    def fake(profile, kind, key, ttl, refresh, build, counted=True, min_age=0):
        calls.append((kind, refresh, counted, min_age))
        return {"summary": "s", "bull": [], "bear": [], "watch": [], "ideas": []}
    monkeypatch.setattr(routes, "ai_call", fake)
    monkeypatch.setattr(routes, "hub", SimpleNamespace(indices=lambda r: [{"name": "NIFTY 50", "day": "2026-10-09", "change_pct": 1.18}]))
    monkeypatch.setattr(routes, "market_open", lambda r, now=None: True)
    routes.pulse_ai("IN", "", False, FREE)
    routes.company_ai("IN", "WIPRO", False, False, PRO)
    routes.company_ai("IN", "WIPRO", True, False, PRO)
    routes.company_ai("IN", "WIPRO", False, False, FREE)
    assert calls == [("pulse", False, False, 300), ("company", False, False, 0), ("company", True, True, 0), ("company", False, True, 0)]


def test_a_company_read_is_written_behind_the_page(usage, monkeypatch):
    monkeypatch.setattr(routes, "hub", SimpleNamespace(company=lambda r, s: {"symbol": s, "region": r, "name": s}))
    monkeypatch.setattr(routes, "page_figures", lambda r, c: c)
    monkeypatch.setattr(routes, "company_key_facts", lambda r, c: [])
    gate = __import__("threading").Event()

    def write(c, ai, pro, kf):
        gate.wait(5)
        return {"summary": "Writes software.", "facts": [], "bull": [], "bear": [], "watch": [], "ideas": [], "region": "IN"}
    monkeypatch.setattr(routes.A, "company", write)
    first = json.loads(routes.company_ai("IN", "WIPRO", False, True, PRO).body)
    assert first == {"pending": True}
    assert json.loads(routes.company_ai("IN", "WIPRO", False, True, PRO).body) == {"pending": True}    # written once
    gate.set()
    for _ in range(100):
        got = json.loads(routes.company_ai("IN", "WIPRO", False, True, PRO).body)
        if "pending" not in got:
            break
        time.sleep(0.05)
    assert got["summary"] == "Writes software."
    assert routes.ai_reads_today(PRO) == 0                     # Pro: a read written as the page opens doesn't count


def test_past_the_cap_the_page_hears_so_at_once(usage, monkeypatch):
    monkeypatch.setattr(routes, "hub", SimpleNamespace(company=lambda r, s: pytest.fail("no read past the cap")))
    for i in range(2):
        routes.ai_call(FREE, "sector", ("IN", f"y{i}"), 60, False, read)
    got = json.loads(routes.company_ai("IN", "WIPRO", False, True, FREE).body)
    assert got["unavailable"] and got["code"] == "research_ai_limit"


def test_account_shows_the_days_reads_against_the_cap(monkeypatch):
    from tests import world as W
    from tests.fake_db import headers
    w = W.build(monkeypatch)
    try:
        c = w["client"]
        free = c.get("/me", headers=headers("free-token")).json()["usage"]
        pro = c.get("/me", headers=headers("pro-token")).json()["usage"]
        owner = c.get("/me", headers=headers("admin-token")).json()["usage"]
        assert free["ai_reads_limit"] == settings.RESEARCH_AI_PER_DAY and free["ai_reads_today"] == 0
        assert pro["ai_reads_limit"] is None and owner["ai_reads_limit"] is None and owner["ai_reads_cap_for"] == "admin"
    finally:
        w["close"]()


def test_plans_page_copy_says_the_cap():
    import re
    ts = (ROOT / "frontend" / "src" / "lib" / "plans.ts").read_text(encoding="utf-8")
    limits = ts[ts.index("export const LIMITS"):ts.index("export const WHO")]
    shown = dict(re.findall(r"\b(free|basic|pro): \{[^}]*?ai_reads_per_day: (null|\d+)", limits, re.S))
    want = {p: plans.ai_reads_per_day(p) for p in plans.PLANS}
    assert {p: (None if v == "null" else int(v)) for p, v in shown.items()} == want == {"free": 60, "basic": 60, "pro": None}
    assert '"ai_reads_per_day", "Fresh AI reads a day' in ts


# ---------- R8O-003: "Insolvency proceedings" on merger meetings, voting results and a media clarification ----------
ROWS = [
    ("AMBUJACEM", "Shareholders meeting", "Ambuja Cements Limited has informed the Exchange regarding Outcome of NCLT convened meeting of the Equity Shareholders held on September 29, 2026.",
     "https://nsearchives.nseindia.com/corporate/AMBUJACEM_29092026204018_Outcome_NCLT_Meeting_ACL1.pdf"),
    ("AMBUJACEM", "Shareholders meeting", "Ambuja Cements Limited has informed the Exchange about the outcome of the meeting of the unsecured creditors convened as per the directions of the Hon'ble National Company Law Tribunal",
     "https://nsearchives.nseindia.com/corporate/AMBUJACEM_28092026210644_ACL__NCLT_OUTCOME_28092026.pdf"),
    ("ACC", "Shareholders meeting", "ACC Limited has informed the Exchange regarding outcome of the NCLT-convened meeting of the equity shareholders",
     "https://nsearchives.nseindia.com/corporate/ACC_1_29092026200638_ACC_Outcome_Cover_Final.pdf"),
    ("ORIENTCEM", "Shareholders meeting", "Orient Cement Limited has informed the Exchange regarding the meeting of equity shareholders convened pursuant to the order of the NCLT",
     "https://nsearchives.nseindia.com/corporate/ORIENTCEM_28092026202922_OCL_Outcome_28092026.pdf"),
    ("PRIVISCL", "Shareholders meeting", "Privi Speciality Chemicals Limited has informed the Exchange regarding Notice of meeting of equity shareholders convened as per the NCLT order",
     "https://nsearchives.nseindia.com/corporate/FAIRCHEMDP_24092026185207_LettertoSENoticeofShholdeMeeting.pdf"),
    ("JUBLCPL", "Shareholders meeting", "Jubilant Agri and Consumer Products Limited has informed the Exchange regarding voting results of the meeting of equity shareholders convened by the NCLT",
     "https://nsearchives.nseindia.com/corporate/JACPL_07092026000403_IntimationVotingResultsESHSigned.pdf"),
    ("LICHSGFIN", "Disclosure of material issue", "LIC Housing Finance Limited has informed the Exchange regarding Clarification on media news on an NCLT petition",
     "https://nsearchives.nseindia.com/corporate/LICHSGFIN_27082026174623_Clarification_on_Media_News_27082026.pdf"),
]


@pytest.mark.parametrize("sym,subject,text,url", ROWS)
def test_nclt_meetings_voting_results_and_clarifications_are_not_insolvency(sym, subject, text, url):
    cid, sev = F.classify(subject, text, url)
    assert cid != "insolvency" and sev == "info", (sym, cid)
    assert F.classify(subject, "NCLT", url)[0] != "insolvency"                 # "NCLT" alone is the tribunal, not a case


def test_the_companys_own_insolvency_case_still_is():
    t = "The Hon'ble NCLT has admitted the application filed by a financial creditor under Section 7 of the IBC against the Company and appointed an Interim Resolution Professional"
    assert F.classify("Corporate Insolvency Resolution Process", t) == ("insolvency", "red")
    assert F.classify("Updates", "Initiation of Corporate Insolvency Resolution Process (CIRP) against the company; moratorium declared")[0] == "insolvency"


def _row(sym, subject, url, text=None, n=0):
    r = {"id": f"{sym}|2026-09-29T20:4{n}|8f9b60ee", "symbol": sym, "company": f"{sym} Ltd", "at": "2026-09-29T20:41", "category": "insolvency",
         "label": "Insolvency proceedings", "severity": "red", "subject": subject, "url": url}
    return {**r, "text": text} if text is not None else r


def test_the_twelve_stored_rows_go_with_or_without_their_summary(mem):
    without = [_row(s, sub, u) for s, sub, _, u in ROWS]
    with_text = [_row(s, sub, u, t) for s, sub, t, u in ROWS]
    assert R.current("IN", without) == [] and R.current("IN", with_text) == []
    real = _row("XYZ", "Corporate Insolvency Resolution Process", None, "NCLT has admitted the petition against the Company; moratorium")
    assert [r["symbol"] for r in R.current("IN", [real])] == ["XYZ"]


def test_the_stored_list_is_reclassified_at_startup_under_the_new_rules_version(mem):
    assert F.RULES_VERSION >= 5
    R.flags.add("IN", [_row(s, sub, u, n=i) for i, (s, sub, _, u) in enumerate(ROWS)] + [{**_row("BGR", "Resignation of the Statutory Auditor", None),
                                                                     "category": "auditor_resign", "label": F.LABEL["auditor_resign"]}])
    R._set_state("IN", through="2026-10-08", rules=4, classified=4)
    assert R.reclassify_stored("IN", date(2026, 10, 9)) == len(ROWS)
    assert [r["symbol"] for r in json.loads(mem["redflags:IN:2026-09"])["items"]] == ["BGR"]


# ---------- R8O-004: captions state facts; a class move isn't selling; no "relatively high"; dates the app's way ----------
@pytest.mark.parametrize("why", [
    "Recent quarterly profit beat suggests upward momentum.",
    "The 50-day average sits above the 200-day, making a crossover a clear signal of a trend shift.",
    "Recent price declines of 5% over two days post Q1 results, making it suitable for testing oversold bounces.",
    "A low RSI would signal oversold conditions.",
])
def test_a_caption_that_predicts_is_dropped(why):
    out = G.polish_company({"ideas": [{"title": "Trend rider", "text": "Enter long when the 20-day EMA crosses above the 50-day EMA, 5% stop loss", "why": why}]})
    assert out["ideas"][0]["why"] == ""


@pytest.mark.parametrize("why", [
    "The price closed above its 50-day average on 8 Oct.",
    "MACD crossed above its signal line on 3 Oct.",            # a signal line is a fact, not a prediction
    "The final dividend went ex on 25 May.",                    # the month, not "may"
    "The 14-day RSI indicator is at 28.",
])
def test_a_caption_that_states_a_fact_stays(why):
    out = G.polish_company({"ideas": [{"title": "Trend rider", "text": "Enter long when the 20-day EMA crosses above the 50-day EMA, 5% stop loss", "why": why}]})
    assert out["ideas"][0]["why"] == why


def test_relatively_high_with_nothing_to_compare_is_dropped():
    assert not G.plain_ok("The P/B of 6.6 is relatively high.")
    assert not G.plain_ok("Valuation looks stretched.")
    assert G.plain_ok("The P/B is 6.6 and the P/E is 22.4.")


def test_a_class_move_is_told_as_the_page_tells_it():
    from app.intel import company as C
    rows = [{"label": "FIIs", "value": 33.8, "change": -12.98}, {"label": "DIIs", "value": 42.3, "change": -1.6},
            {"label": "Public", "value": 23.7, "change": 14.6}]
    move = G.class_move({"rows": rows, "note": C.class_move_note(rows)})
    assert move["classes"] == ["FIIs", "Public"]
    out = G.polish_company({"summary": "ICICI Bank is a private lender. FIIs cut their holding by 12.98 points over the year.",
                            "bear": ["FIIs shareholding fell by 12.98 points", "Net interest margin is 4.3%."], "class_move": move})
    assert "cut their holding" not in out["summary"] and "almost offset each other" in out["summary"]
    assert out["bear"] == ["Net interest margin is 4.3%."]


def test_dates_in_a_read_are_written_the_apps_way():
    assert G.app_dates("Results are due on 2026-10-17.", date(2026, 10, 9)) == "Results are due on Sat, 17 Oct."
    assert G.app_dates("The AGM was on 2025-08-01.", date(2026, 10, 9)) == "The AGM was on Fri, 1 Aug 2025."
    out = G.polish_company({"watch": ["Q2 results on 2026-10-17"]}, today=date(2026, 10, 9))
    assert out["watch"] == ["Q2 results on Sat, 17 Oct"]


# ---------- R8O-005: BRK-B and Visa in the screener and the largest list ----------
def test_a_page_built_is_in_the_index_and_the_largest_list_at_once(mem, monkeypatch):
    cos = {s: {"name": s, "sym": s, "bse": None} for s in ("V", "XOM", "WMT")}
    monkeypatch.setattr(stock_pages, "companies", lambda r: cos)
    monkeypatch.setattr(stock_pages.universes, "PRESETS", {"US": []})
    monkeypatch.setattr(screens, "with_us_red", lambda rows: rows)
    # Visa's stored page from before every class of shares was counted: no market value, so not in any list by size
    mem["stocks:page:US:V"] = json.dumps({"ts": time.time(), "facts": us(symbol="V", name="VISA INC.", market_cap=None, v=3)})
    mem["stocks:page:US:XOM"] = json.dumps({"ts": time.time(), "facts": us(symbol="XOM", name="Exxon", market_cap=693_000.0, sales_usd=300_000.0)})
    mem["stocks:page:US:WMT"] = json.dumps({"ts": time.time(), "facts": us(symbol="WMT", name="Walmart", market_cap=877_000.0, sales_usd=680_000.0)})
    screens.build_index("US")
    assert [r["symbol"] for r in screens.run("US", {})["rows"]][:2] == ["WMT", "XOM"]
    pages = stock_pages.Pages(lambda r, co: us(symbol="V", name="VISA INC.", market_cap=700_500.0), per_minute=6)
    pages.on_built = screens.note_page
    pages.get("US", "V", cos["V"])
    # the screener and "US: the largest companies", before the index is gathered again
    assert [r["symbol"] for r in screens.run("US", {})["rows"]] == ["WMT", "V", "XOM"]
    assert [s for s, _ in stock_pages.largest("US")[0]] == ["WMT", "V", "XOM"]
    # a row that already has a market value, and a company the index doesn't have yet, wait for the next gathering
    other = stock_pages.Pages(lambda r, co: us(symbol=co["sym"], name=co["sym"], market_cap=999_000.0, sales_usd=500_000.0), per_minute=6)
    other.on_built = screens.note_page
    other.get("US", "XOM", cos["XOM"])
    cos["NEW"] = {"name": "NEW", "sym": "NEW", "bse": None}
    other.get("US", "NEW", cos["NEW"])
    assert [(r["symbol"], r["market_cap"]) for r in screens.run("US", {})["rows"]] == [("WMT", 877_000.0), ("V", 700_500.0), ("XOM", 693_000.0)]
    # gathered again: the stored page is the row, and nothing is kept on top of it
    screens.build_index("US")
    assert [r["symbol"] for r in screens.load_index("US")["rows"] if r["symbol"] == "V"] == ["V"]


# ---------- R8O-006: euros and pounds charged as rupees say the rupee charge in their currency ----------
def test_a_fixed_price_charged_in_rupees_says_the_charge_today(mem):
    mem[pricing.RATES] = json.dumps({"rates": {"USD": 96.6, "EUR": 108.46, "GBP": 127.87, "SAR": 25.73}})
    pricing._rates_cache[0] = 0.0
    pricing.forget()
    pub = pricing.public()["currencies"]
    assert pub["EUR"]["basic"] == 8 and pub["EUR"]["charge_about"]["basic"] == round(699 / 108.46, 2) == 6.44
    assert pub["GBP"]["basic"] == 7 and pub["GBP"]["charge_about"]["basic"] == round(699 / 127.87, 2)
    assert pub["USD"]["charge_about"]["pro"] == round(1999 / 96.6, 2)
    assert "charge_about" not in pub["SAR"] and "charge_about" not in pub["INR"]          # already the rupee charge converted
    assert "rate" not in pub["EUR"]
    pricing._rates_cache[0] = 0.0


# ---------- R8O-008: Admin's AI tile and System read the same result ----------
def test_a_measuring_stopped_on_used_up_credit_is_out_of_credit_not_untested():
    from app import ai_providers as P
    st = SimpleNamespace(rank_error="stopped measuring: the free credit is used up", last_ok=None, last_error=None, last_error_at=None,
                         last_error_kind=None, quota=False, config_error=False)
    assert P.measured_result(st) == "quota"
    assert P.last_result("cerebras", st, True, False, False, [], time.time()) == "quota"
    assert P.measured_result(SimpleNamespace(rank_error="stopped measuring: the key was rejected (401)")) == "failed"
    assert P.measured_result(SimpleNamespace(rank_error="stopped measuring: rate limited (429)")) is None
    assert P.measured_result(SimpleNamespace(rank_error=None)) is None


# ---------- R8O-010: advice-style third-party headlines ----------
@pytest.mark.parametrize("title,ok", [
    ("Buy Tata Consultancy Services; target of Rs 2390: Prabhudas Lilladher", False),
    ("Should you book profit or invest more?", False),
    ("Up to 52% upside: ICICI Bank among the biggest bets for investors", False),
    ("We’re putting some of our large cash pile to work in a beaten-down consumer name", False),
    ("TCS announces Rs 18,000 crore buyback at Rs 4,150 a share", True),
    ("Reliance Retail adds 300 stores; targets 5,000 by FY28", True),
    ("TCS Q2 results: profit rises 5% to Rs 12,000 crore", True),
])
def test_company_news_and_pulse_drop_advice_style_headlines(title, ok):
    assert news.plain_headline(title) is ok


# ---------- R8O-011: Admin's live price feed counts running sessions, each once ----------
def test_the_feed_counts_running_sessions_once():
    a = SimpleNamespace(id="a", user_id="owner", kind="options", polled=True)
    b = SimpleNamespace(id="b", user_id="other", kind="options", polled=True)
    gone = SimpleNamespace(id="c", user_id="owner", kind="options", polled=True)
    live = main.running_now({"a": a, "b": b, "c": gone}, {"c"})
    assert [s.id for s in live] == ["a", "b"] and main.session_counts(live)["options_sessions"] == 2
    assert len(main.running_now({"a": a, "a2": a})) == 1


def test_the_overview_says_whose_options_sessions_they_are(monkeypatch):
    from tests import world as W
    from tests.fake_db import headers
    w = W.build(monkeypatch)
    try:
        monkeypatch.setattr(main.manager, "sessions", {"a": SimpleNamespace(id="a", user_id="u1", kind="options", polled=True),
                                                       "b": SimpleNamespace(id="b", user_id="u2", kind="options", polled=True)})
        sv = w["client"].get("/admin/overview", headers=headers("admin-token")).json()["server"]
        assert sv["options_sessions"] == 2 and sv["options_users"] == 2
    finally:
        w["close"]()


# ---------- R8O-012: a "live" chain is at most a couple of minutes old ----------
def test_a_stale_chain_no_longer_stands_in_for_ten_minutes():
    assert positioning.LIVE_STALE_FOR <= 180


# ---------- Eni: a 20-F cover page that counts treasury shares ----------
def eni():
    return json.loads((FIX / "eni-companyfacts.json").read_text()), json.loads((FIX / "eni-submissions.json").read_text())


def test_enis_treasury_shares_are_read_from_its_annual_report():
    text = (FIX / "eni-20f-2025-excerpt.txt").read_text(encoding="utf-8")
    # 189,083,769 held at the balance sheet date; not the 86,828,014 held after March's cancellation, the 102,255,755
    # bought in the year or the 118,782,928 cancelled
    assert sec.treasury_held(text) == 189_083_769


def test_enis_market_value_counts_its_shares_outstanding():
    facts, subs = eni()
    p = sec.build(facts, subs, symbol="E")
    assert p["shares"] == 3_146_765_114 and p["shares_from"] == "cover" and p["avg_shares"] == 3_024_753_353
    q = sec.with_ads(sec.net_of_treasury(p, 189_083_769), 2)
    assert q["shares"] == 2_957_681_345 and q["treasury_shares"] == 189_083_769
    assert round(q["shares"] / 2 * 55.62 / 1e9, 1) == 82.3            # $87.5bn on the cover page's count
    # a cover count already net of treasury shares (closer to the year's average outstanding) is left as it is
    net = {**p, "shares": 2_957_681_345.0}
    assert sec.net_of_treasury(net, 189_083_769)["shares"] == 2_957_681_345.0
    # a count the earnings imply instead of the cover page's, or no treasury figure: as it is
    assert sec.net_of_treasury({**p, "shares_from": None}, 189_083_769)["shares"] == p["shares"]
    assert sec.net_of_treasury(p, None)["shares"] == p["shares"]


def test_the_annual_report_read_carries_the_treasury_count():
    text = (FIX / "eni-20f-2025-excerpt.txt").read_text(encoding="utf-8")
    html = "<html><body><p>" + text.replace("\n\n", "</p><p>") + "</p></body></html>"
    s = sec.SEC(transport=httpx.MockTransport(lambda r: httpx.Response(200, text=html)))
    subs = {"cik": 1002242, "filings": {"recent": {"form": ["20-F"], "accessionNumber": ["0001554855-26-000390"], "primaryDocument": ["e-20251231.htm"]}}}
    got = s.ads(subs)
    assert got["treasury"] == 189_083_769 and got["ads"] is True and got["form"] == "20-F"
