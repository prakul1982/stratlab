"""fix11 (17 Nov 2026): open LIVE10A / LIVE10B / CX2 findings. Each test fails before its fix and passes after."""
from app import main  # noqa: F401, I001
from app.engine import costs as C


# ---------- LIVE10A-033: the backtest's tax estimate carries a year's loss on, and its note says so ----------
def test_tax_estimate_sets_a_years_loss_off_against_later_gains_and_says_so():
    t = lambda a, b, p: {"pnl": p, "qty": 0, "entry": 0, "exit": 0, "entry_t": a, "exit_t": b}  # noqa: E731
    trades = [t("2022-05-02", "2022-06-01", 23_300), t("2023-05-02", "2023-06-01", 18_200),
              t("2024-05-02", "2024-06-03", -2_000), t("2025-05-02", "2025-06-02", -1_500),
              t("2026-05-04", "2026-06-01", 2_900)]                         # FY27's +2,900 is absorbed by FY25/FY26's −3,500
    got = C.tax_estimate("in_eq", trades)
    assert got["amount"] == round(0.2 * (23_300 + 18_200), 2)
    assert "net loss is set off against the next years' gains" in got["note"]
    assert "Losses and your other income can change it" not in got["note"]


# ---------- LIVE10A-035 / CX2 #2: a loss is never "and returned more than buy and hold" ----------
def test_a_loss_smaller_than_buy_and_holds_leads_with_the_loss_and_says_both_returns():
    from app import library
    from app.engine import verdict as V
    e = {"verdict": {"verdict": "no_edge", "headline": "No edge here."}, "stats": {"ret": -4.1, "buy_hold": -7.3, "trades": 30}}
    head = library.restated(e)["fact_headline"]
    assert "returned more than buy and hold" not in head
    assert head.startswith("Lost money after costs (−4.1%); buying and holding lost more (−7.3%)")
    assert V.fact_headline("no_edge", [], 30, -4.1, -7.3) == "Lost money after costs (−4.1%); buying and holding lost more (−7.3%)."
    assert V.fact_headline("no_edge", [], 30, -4.1, -4.5) == "Lost money after costs (−4.1%), within a point of buying and holding (−4.5%)."
    # behind buy and hold the shortfall still leads (R6V-005)
    assert V.fact_headline("no_edge", [], 30, -4.1, 20.0) == "24.1 points behind buy and hold; lost money after costs."


# ---------- LIVE10A-036: the briefs list reads its issues in one database call ----------
def test_the_briefs_list_reads_its_issues_in_one_call(monkeypatch):
    import json
    from app import db
    from app.newsletter import job
    store = {"news-index:market:US": json.dumps(["market.US.2026-11-16", "market.US.2026-11-13"]),
             "news:market:US:2026-11-16": json.dumps({"id": "market.US.2026-11-16", "kind": "my_stocks", "day": "2026-11-16"}),
             "news:market:US:2026-11-13": json.dumps({"id": "market.US.2026-11-13", "kind": "my_stocks", "day": "2026-11-13"})}
    asked = []
    monkeypatch.setattr(db, "get_setting", store.get)
    monkeypatch.setattr(db, "prefetch_settings", lambda keys: asked.append(list(keys)))
    got = job.recent("market", "US", 20)
    assert [i["id"] for i in got] == ["market.US.2026-11-16", "market.US.2026-11-13"]
    assert asked == [["news:market:US:2026-11-16", "news:market:US:2026-11-13"]]


# ---------- LIVE10A-010: the Mood card is read once soon after each open, so a session's first visit gets that session ----------
def test_the_mood_card_is_read_once_after_each_open(monkeypatch):
    from datetime import datetime, timedelta, timezone
    from app import mood_job
    from app.data import calendar
    IST = timezone(timedelta(hours=5, minutes=30))
    monkeypatch.setattr(calendar, "is_trading_day", lambda region, d: d.weekday() < 5)
    store = {}
    monkeypatch.setattr(mood_job, "db", type("D", (), {"get_setting": staticmethod(store.get),
                                                       "set_setting": staticmethod(lambda k, v: store.__setitem__(k, v))}))
    calls = []
    job = mood_job.Job(lambda region: {"mood": "x"}, lambda region, day: day,
                       opening=lambda region: calls.append(region) or "2026-11-17")
    at = lambda h, m: datetime(2026, 11, 17, h, m, tzinfo=IST).astimezone(timezone.utc)  # noqa: E731
    assert job.tick_open(at(9, 20)) == {}                                   # before 09:30 IST nothing
    assert job.tick_open(at(9, 35)) == {"IN": "written"}
    assert job.tick_open(at(9, 40)) == {} and calls == ["IN"]               # once a session
    assert store["moodjob-open:IN"] == "2026-11-17"
    assert mood_job.job.opening is mood_job._mood_open                      # the clock's own job reads it
    assert mood_job.Job().opening is None                                   # a job made without it (tests) reads nothing


# ---------- LIVE10A-017: the stored 9 Nov brief is measured against the 8 Nov Muhurat session, in the app's list too ----------
def test_the_stored_9_nov_brief_is_measured_against_the_muhurat_session(monkeypatch):
    import json
    from datetime import date
    from app import blog, db, official_close
    from app.data import calendar as tc
    from app.newsletter import job
    files = {"2026-11-09": {"NIFTY 50": 25043.85}, "2026-11-08": {"NIFTY 50": 24986.40}, "2026-11-06": {"NIFTY 50": 25028.0}}
    monkeypatch.setattr(official_close, "index_closes", lambda d, fetch=False, now=None: files.get(d))
    # as production has it: the Sunday session is no trading day (usual hours), only a special session
    monkeypatch.setattr(tc, "is_trading_day", lambda m, d: d.weekday() < 5)
    monkeypatch.setattr(tc, "special_days", lambda m: {"2026-11-08"})
    fixed, changed = blog.official_changes("IN", date(2026, 11, 9), [{"name": "NIFTY 50", "price": 25043.85, "change_pct": 0.06}])
    assert changed and fixed[0]["change_pct"] == 0.23
    issue = {"id": "market.IN.2026-11-09", "kind": "market", "region": "IN", "day": "2026-11-09", "weekly": False,
             "subject": "India market brief, 9 Nov 2026: NIFTY 50 +0.06%", "summary": "NIFTY 50 +0.06%.",
             "indices": [{"name": "NIFTY 50", "price": 25043.85, "change_pct": 0.06}],
             "sections": [{"title": "Indices", "items": [{"text": "NIFTY 50: 25,043.85, +0.06% on the day"}]}]}
    store = {"news-index:market:IN": json.dumps([issue["id"]]), "news:market:IN:2026-11-09": json.dumps(issue)}
    monkeypatch.setattr(db, "get_setting", store.get)
    monkeypatch.setattr(db, "set_setting", lambda k, v: store.__setitem__(k, v))
    assert job.repair_official_changes("IN", days=3650) == 1
    kept = json.loads(store["news:market:IN:2026-11-09"])
    assert kept["indices"][0]["change_pct"] == 0.23
    assert "+0.23%" in kept["subject"] and "+0.06%" not in kept["subject"] + kept["summary"] + kept["text"]
    assert job.repair_official_changes("IN", days=3650) == 0                 # done once


# ---------- CX2: a board meeting on raising money through NCDs is a debt raise, not a red-flag fund raise ----------
def test_a_raise_through_ncds_is_a_debt_raise_not_a_fund_raise_flag():
    from app.intel import filings as F
    got = F.classify("Board Meeting Intimation", "The Board will consider raising of funds through issue of Non-Convertible Debentures on a private placement basis.")
    assert got == ("ncd", "amber")
    assert F.classify("Board Meeting Intimation", "The Board will consider raising of funds by way of issue of equity shares.") == ("fund_raise", "red")
    assert F.classify("Fund Raising", "Approved fund raising up to Rs 500 crore.")[0] == "fund_raise"


# ---------- CX2: an analyst or investor meeting filing is not labelled Financial results ----------
def test_an_investor_meet_filing_about_results_is_an_investor_meeting():
    from app.intel import filings as F
    cid, sev = F.classify("Analysts/Institutional Investor Meet/Con. Call Updates",
                          "Schedule of the analysts meet on 3 Nov 2026 to discuss the unaudited financial results for the quarter.")
    assert cid in ("investor_meet", "concall") and sev == "info"
    assert F.classify("Outcome of Board Meeting", "Approved the unaudited financial results for the quarter ended 30 Sep 2026.")[0] == "results"
