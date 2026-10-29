"""FX-1: the RC2A findings (26 Oct 2026, live market hours) on IPOs, scans, events, the US company page and the trade pages. Every clock is fixed."""
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo


from app import main  # noqa: F401  (first: the app loads the newsletter job before the modules built on it)
from app import fo_changes, ipo as I, ipo_docs as D, market_events as M, official_close, scan, scan_presets, universes
from app.intel import ipo_sources as S
from app.intel import grounding as G
from tests import fake_ipo as F
from tests.test_ipo import FakeYahoo, bar, read_all, w  # noqa: F401  (fixture)

IST = ZoneInfo("Asia/Kolkata")
UTC = timezone.utc


def at(y, mo, d, h=10, mi=30):
    return datetime(y, mo, d, h, mi, tzinfo=IST).astimezone(UTC)


# ---------- RC2A-001: one row per issue ----------
def row(id_, name, **kw):
    r = {"id": id_, "market": "IN", "segment": "mainboard", "name": name, "symbol": None, "exchanges": ["BSE"], "currency": "INR", "nkey": S.name_key(name),
         "open": "2026-10-27", "close": "2026-10-29", "seen": "2026-10-24"}
    r.update(kw)
    return r


def test_an_issue_on_both_exchanges_lists_is_one_row_with_the_nse_size():
    nse = row("in-sfctech", "SFC Environmental Technologies Limited", symbol="SFCTECH", exchanges=["NSE"], series="EQ", detail_at="2026-10-26T07:40:00+00:00",
              fresh_cr=150.0, ofs=15682750, lot=45, high=330.0, low=313.0)
    twin = row("in-bse-4905", "SFC ENVIRONMENTAL TECHNOLOGIES LTD", bse_code="4905", size_shares=2050000, high=330.0, low=313.0)
    other = row("in-bse-4906", "Bls Polymers Limited", bse_code="4906", low=142.0, high=150.0)
    other_nse = row("in-blspoly", "BLS Polymers Limited", symbol="BLSPOLY", exchanges=["NSE"], series="EQ", size_shares=17000000)
    got = I.dedupe_india([twin, other, nse, other_nse])
    ids = {r["id"] for r in got}
    assert ids == {"in-sfctech", "in-blspoly"}
    sfc = next(r for r in got if r["id"] == "in-sfctech")
    assert sfc["exchanges"] == ["BSE", "NSE"] and sfc["bse_code"] == "4905" and sfc["size_shares"] == 2050000
    assert I.sizes(sfc)["amount"] == 150 + round(15682750 * 330 / 1e7, 2)          # the NSE page's parts, never the BSE twin's own figure
    assert sfc["lot"] == 45 and sfc["symbol"] == "SFCTECH"


def test_two_offers_of_one_name_months_apart_are_two_issues():
    a = row("in-a", "Acme Limited", symbol="ACME", open="2026-06-01", close="2026-06-03")
    b = row("in-bse-9", "ACME LTD", open="2026-10-27", close="2026-10-29")
    assert len(I.dedupe_india([a, b])) == 2


def test_merge_drops_the_row_stored_when_only_bse_named_the_issue():
    old = [row("in-bse-4905", "SFC Environmental Technologies Limited", bse_code="4905")]
    nse = {"upcoming": [{"symbol": "SFCTECH", "name": "SFC Environmental Technologies Limited", "series": "EQ", "segment": "mainboard", "open": "2026-10-27",
                         "close": "2026-10-29", "low": 313.0, "high": 330.0, "size_shares": None}]}
    bse = [{"code": "4905", "name": "SFC ENVIRONMENTAL TECHNOLOGIES LTD", "segment": "mainboard", "open": "2026-10-27", "close": "2026-10-29", "low": 313.0, "high": 330.0,
            "face_value": 2.0, "size_shares": 2050000}]
    rows = I.merge_india(old, nse, bse, [], [], [], date(2026, 10, 26))
    assert [r["id"] for r in rows] == ["in-sfctech"] and rows[0]["bse_code"] == "4905"


def test_the_stored_list_shows_one_row_even_before_the_next_read(w):
    I.save("IN", [row("in-bse-4905", "SFC Environmental Technologies Limited"), row("in-sfctech", "SFC Environmental Technologies Limited", symbol="SFCTECH", exchanges=["NSE"])], {})
    assert [r["id"] for r in I.load("IN")["rows"]] == ["in-sfctech"]


# ---------- RC2A-002: the latest close is the official close ----------
def test_the_latest_close_is_the_exchange_close_not_the_last_candle(w):
    day = "2026-10-23"
    row_ = {"id": "in-zetwerk", "market": "IN", "symbol": "ZETWERK", "listing": "2026-10-16", "price": 151.0, "exchanges": ["NSE"]}
    yahoo = FakeYahoo({"ZETWERK.NS": [bar("2026-10-16", 160.0, 150.0), bar(day, 142.0, 140.70)]})
    official_close.save(day, {"ZETWERK": 138.25})
    p = I.performance(row_, yahoo, date(2026, 10, 26), at(2026, 10, 26, 10, 30))
    assert p["latest"] == 138.25 and p["latest_date"] == day and p["change_pct"] == round((138.25 / 151 - 1) * 100, 2)
    # the stored figures of an earlier read are put right at read time, nothing fetched
    stale = {**row_, "perf": {"issue_price": 151.0, "latest": 140.70, "latest_date": day, "change_pct": -6.82, "day_close": 150.0, "listed": "2026-10-16",
                              "day_change_pct": -0.66, "basis": "prices"}}
    fixed = I.official_perf(stale, stale["perf"], at(2026, 10, 26, 10, 30))
    assert fixed["latest"] == 138.25 and fixed["change_pct"] == -8.44
    assert I.list_row({**stale, "stage": "listed"}, at(2026, 10, 26, 10, 30))["perf"]["latest"] == 138.25


def test_a_session_still_going_is_not_a_close(w):
    row_ = {"id": "in-x", "market": "IN", "symbol": "XYZ", "listing": "2026-10-20", "price": 100.0, "exchanges": ["NSE"]}
    yahoo = FakeYahoo({"XYZ.NS": [bar("2026-10-20", 105.0, 104.0), bar("2026-10-23", 104.0, 110.0), bar("2026-10-26", 110.0, 99.0)]})
    p = I.performance(row_, yahoo, date(2026, 10, 26), at(2026, 10, 26, 11, 0))
    assert p["latest_date"] == "2026-10-23" and p["latest"] == 110.0              # Monday's candle, 11:00, is a price so far, not a close


# ---------- RC2A-004: the bidding time is the exchange's ----------
def test_bidding_times_are_read_from_the_issue_page():
    got = {k: S.nse_detail(F.file(f"nse_detail_{k}.json")) for k in ("JPL", "MKSONS", "RAVITA")}
    assert (got["JPL"]["close_time"], got["JPL"]["open_time"]) == ("19:00", "09:00") and "7:00 pm" in got["JPL"]["hours"]
    assert (got["MKSONS"]["close_time"], got["MKSONS"]["open_time"]) == ("17:00", "10:00")
    assert "Bidding Timings on Issue Closure upto 4:00 P.M." in got["RAVITA"]["hours"]
    assert S.nse_detail({"issueInfo": {"dataList": [{"title": "Symbol", "value": "ABC"}, {"title": "Issue Period", "value": "21-Oct-2026 to 23-Oct-2026"}]}})["close_time"] is None


def test_an_issue_that_bids_to_seven_is_open_until_seven_and_says_so(w):
    jpl = {"id": "in-jpl", "market": "IN", "open": "2026-10-21", "close": "2026-10-23", "close_time": "19:00", "exchanges": ["NSE"], "symbol": "JPL", "name": "Jio", "currency": "INR"}
    assert I.stage_of(jpl, at(2026, 10, 23, 17, 30)) == "open" and I.stage_of(jpl, at(2026, 10, 23, 19, 0)) == "closed"
    assert I.stage_of({**jpl, "close_time": None}, at(2026, 10, 23, 17, 30)) == "closed"          # no time given: the usual five
    assert I.clock_text("19:00") == "7 PM" and I.clock_text("17:30") == "5:30 PM"
    ev = I.events_on([jpl], "IN", date(2026, 10, 23), at(2026, 10, 23, 8, 0))
    assert [e["text"] for e in ev if e["kind"] == "close"] == ["Jio closes for bidding today at 7 PM IST."]
    ev = I.events_on([{**jpl, "close_time": None}], "IN", date(2026, 10, 23), at(2026, 10, 23, 8, 0))
    assert [e["text"] for e in ev if e["kind"] == "close"] == ["Jio closes for bidding today."]          # no time is stated that the page did not give


# ---------- RC2A-006: the first bids, and the read's own time ----------
def test_the_first_bids_are_read_every_five_minutes_then_every_quarter_hour(w):
    r = {"id": "in-eaaa", "market": "IN", "segment": "mainboard", "name": "EAAA India Alternatives Limited", "symbol": "EAAA", "series": "EQ", "open": "2026-10-26",
         "close": "2026-10-28", "open_time": "10:00", "exchanges": ["NSE"], "currency": "INR", "nkey": "eaaaindiaalternatives"}
    I.save("IN", [r], {})
    job = I.Job(sleep=lambda s: None)
    t0 = at(2026, 10, 26, 10, 3)
    assert job.live_due(at(2026, 10, 26, 9, 40)) is False and job.live_due(t0) is True
    job._live_at = __import__("time").time() - 301
    assert job.live_due(t0) is True                                         # no bids stored yet: every five minutes
    I.save("IN", [{**r, "sub": {"times": 1.0, "rows": []}}], {})
    assert job.live_due(t0) is False                                        # bids in: a quarter hour
    job._live_at = __import__("time").time() - 901
    assert job.live_due(t0) is True


def test_a_read_that_met_a_busy_source_is_tried_again_twice_a_day_at_most(w):
    now = at(2026, 10, 26, 10, 30)
    job = I.Job(sleep=lambda s: None)
    I.save_state({"IN": {"read": (now - timedelta(minutes=30)).isoformat(), "problems": ["upcoming issues: The exchange feed is busy (our rate limit)."]}})
    assert job.retry_due(now) == "IN" and job.retry_due(now) == "IN" and job.retry_due(now) is None
    assert I.busy("upcoming issues: The exchange feed is busy (our rate limit).") and not I.busy("past issues: isn't answering")


def test_the_list_says_when_the_bids_were_read_and_when_its_problems_were_noted(w):
    from tests.fake_db import headers
    read_all(w)
    rows = I.load("IN")["rows"]
    for r in rows:
        if I.stage_of(r) == "open":
            r["sub_read"] = "2026-10-25T04:55:00+00:00"
            r["sub"] = {"times": 2.0, "rows": []}
    I.save("IN", rows, {"problems": ["upcoming issues: The exchange feed is busy (our rate limit)."], "read": "2026-10-25T02:10:00+00:00"})
    d = w["client"].get("/invest/ipos?market=IN", headers=headers("free-token")).json()
    assert d["bids_read"] == "2026-10-25T04:55:00+00:00" and d["problems_at"] == "2026-10-25T02:10:00+00:00"
    assert any(x.get("sub_read") for x in d["tabs"]["open"])


# ---------- RC2A-007: the offer document's words ----------
def test_a_text_is_cut_at_a_word_and_a_money_table_is_a_list():
    assert D.clip_words("one two three four five", 12) == "one two…"
    jio = ("Out of the Net Proceeds we propose to utilise: S. No. Particulars Total estimated amount to be utilised (in ₹ million) 1. Repayment of borrowings "
           "availed by our Company 275,000 275,000 2. General corporate purposes* [●] [●]")
    got = D.objects_view({"page": 1, "text": jio})
    assert got["table"]["unit"] == "million" and [x["label"] for x in got["table"]["rows"]] == ["Repayment of borrowings availed by our Company", "General corporate purposes*"]
    assert got["table"]["rows"][0]["figures"] == "275,000 275,000" and got["text"].endswith("utilise:")
    cut = D.objects_view({"page": 1, "text": ("word " * 130).strip() + " fo"})
    assert not cut["text"].endswith(" fo") and cut["text"].endswith("…")
    q = "x" * 299 + " shall not e"
    assert D.tidy_summary({"business": {"text": "t", "quote": q}})["business"]["quote"].endswith("…")


# ---------- RC2A-020: the index groups are the exchange's lists ----------
def test_the_nifty_groups_follow_the_exchanges_own_list(w):
    base = universes.symbols("IN", "nifty50")
    assert "BSE" in base and "INDIGO" in base and "MAXHEALTH" in base and "WIPRO" not in base and len(base) == 50
    assert "UNIONBANK" in universes.symbols("IN", "banknifty") and len(universes.symbols("IN", "banknifty")) == 14
    listed = [s for s in base if s != "TCS"] + ["WIPRO"]
    assert universes.keep_followed("nifty50", listed, date(2026, 10, 26)) is True
    assert "WIPRO" in universes.symbols("IN", "nifty50") and "TCS" not in universes.symbols("IN", "nifty50")
    assert next(p for p in universes.presets("IN") if p["id"] == "nifty50")["as_of"] == "26 Oct 2026"
    assert universes.keep_followed("nifty50", ["A", "B"], date(2026, 10, 27)) is False                  # a broken answer changes nothing
    assert universes.refresh_followed(lambda name: (_ for _ in ()).throw(RuntimeError("down"))) == []


# ---------- RC2A-021, 022: a scan row says one price; a volume rule is judged on a whole day ----------
def test_a_volume_rule_is_judged_on_the_last_whole_session_while_the_market_trades(monkeypatch):
    import numpy as np
    from tests.test_scan import FakeRegistry, bars_from
    closes = list(np.linspace(100, 120, 40))
    bars = bars_from(closes)
    for b in bars:
        b["v"] = 1000.0
    bars[-2]["v"] = 5000.0                                # yesterday: five times the average, and the close above the day before
    last_day = str(bars[-1]["t"])[:10]
    bars[-1]["v"] = 100.0                                 # today so far
    reg = FakeRegistry({"AAA": bars})
    monkeypatch.setattr(scan, "_bars", lambda registry, iid: bars)
    import app.intel.company as C
    monkeypatch.setattr(C, "market_today", lambda region, now=None: last_day)
    monkeypatch.setattr(scan_presets, "MIN_BARS", 30)
    live = scan.run_preset(reg, "US", [{"symbol": "AAA"}], "volume_surge", live=True)
    assert live["basis"] == "whole_session" and [r["symbol"] for r in live["rows"]] == ["AAA"] and "5.0 times" in live["rows"][0]["detail"]
    after = scan.run_preset(reg, "US", [{"symbol": "AAA"}], "volume_surge", live=False)
    assert "basis" not in after


# ---------- RC2A-025: the index notice is read ----------
def test_a_notice_with_lettered_parts_gives_each_part_its_own_index():
    text = Path(__file__).parent.joinpath("fixtures", "index_prs_23102026_1.txt").read_text()
    got = M.read_index_changes(text, "Replacements in indices w.e.f. October 30, 2026")
    by = {s["index"]: s for s in got["sections"]}
    assert got["effective"] == "2026-10-30" and set(by) == {"Nifty50 Shariah", "Nifty500 Shariah", "Nifty SME Emerge"}
    assert [x[0] for x in by["Nifty50 Shariah"]["out"]] == ["HINDALCO"] and len(by["Nifty500 Shariah"]["in"]) == 6 and len(by["Nifty500 Shariah"]["out"]) == 6
    assert [x[0] for x in by["Nifty SME Emerge"]["out"]] == ["ARHAM"]


def test_a_notice_that_failed_is_tried_again_the_next_day():
    calls = []

    class Web:
        def text(self, url):
            return ('<div data-date="Oct 23, 2026" hidden="true"><p>x</p><a href=\'/Press_Release/ind_prs23102026_1.pdf\'>Replacements in indices w.e.f. October 30, 2026</a></div>')

        def pdf_text(self, url):
            calls.append(url)
            raise ValueError("The PDF couldn't be read (X).")
    st = {}
    for _ in range(4):
        st = M.refresh_index(Web(), st, date(2026, 10, 26))
    assert len(calls) == 3                                                       # three tries in a day, then it waits
    st = M.refresh_index(Web(), st, date(2026, 10, 27))
    assert len(calls) == 4


# ---------- RC2A-026: a cause no headline reports is dropped; a one-off quarter is named ----------
def test_a_cause_without_a_headline_is_dropped_and_a_base_quarter_is_named():
    facts = {"symbol": "RELIANCE", "recent_headlines": ["Reliance shares edge up as markets rise"],
             "base_effect_items": [{"quarter": "Jun 2025", "text": "Jun 2025 had other income of ₹15,119 crore against a median of ₹3,900 crore: a change measured against Jun 2025 is against a quarter moved by them."}]}
    assert G.cause_backed("The most important current development is the rapid subscription of its Jio Platforms IPO, which has driven a recent 2% stock surge.", facts["recent_headlines"]) is False
    out = G.base_noted("Profit growth YoY June 2026 vs June 2025 is −24.6%.", facts)
    assert "Jun 2025 had other income of ₹15,119 crore" in out
    assert G.base_noted("Profit growth YoY June 2026 vs June 2025 is −24.6%, against a base moved by other income.", facts).count("15,119") == 0


# ---------- RC2A-035: a revision circular's lot starts with a series ----------
def test_a_lot_badge_names_the_series_a_revision_starts_with():
    e = {"kind": "lot", "symbol": "TCS", "was": 225, "now": 250, "effective": "2026-10-28", "series": "2027-01", "circ": True, "source": "circular_x"}
    b = fo_changes.badge_of(e, date(2026, 10, 26))
    assert b["short"] == "Lot 225→250 from Jan 2027"
    assert fo_changes.badge_of({**e, "circ": False}, date(2026, 10, 26))["short"] == "Lot 225→250 from 28 Oct"


# ---------- RC2A-027: a US company's page has its holders and flagged filings ----------
def test_a_us_company_page_has_holders_above_five_percent_and_flagged_filings_on_every_plan(w):
    from tests.fake_db import headers
    r = w["client"].get("/research/us-company/aapl", headers=headers("free-token"))
    assert r.status_code == 200
    d = r.json()
    assert d["symbol"] == "AAPL" and set(d["flags"]) >= {"items", "total", "from", "to"} and set(d["holders"]) >= {"items", "total", "unread"}
    assert "8-K" in d["note"] and not any(x in json.dumps(d).lower() for x in ("yahoo", "finnhub"))
    assert w["client"].get("/research/us-company/aapl").status_code in (401, 403)
