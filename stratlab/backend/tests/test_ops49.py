"""Release 49, lane ops49 (operations and reliability): Admin alerts that opened on a part failing once and cleared on the retry
(owner, 13 Nov: "Admin alerts keep popping"; the IPO job's "2 company filing pages the SEC didn't answer just now" 8 times in 2 days,
"Company pages' prices" and "Feature check" cleared by themselves). Each test fails before the change and passes after."""
import json
from datetime import datetime, timedelta, timezone

from app import main  # noqa: F401, I001  (main first: it loads the modules in the order they need)
from app import admin_jobs, autofix, db, ipo as I, leader, platform_check as pc
from app.intel.net import SourceError
from tests.test_ipo import NOW, w  # noqa: F401  (the IPO tests' fake world and its clock)


# ---------- the rule: a part failing alone opens nothing until it fails two runs in a row; many at once open at once ----------
def test_streaks_count_runs_in_a_row_and_lasting_keeps_repeats_or_a_large_share():
    c1 = autofix.streaks(None, ["A"], ["B", "C"])
    assert c1 == {"A": 1} and autofix.lasting(["A"], c1, 3) == []                     # once: nothing
    c2 = autofix.streaks(c1, ["A"], ["B"])
    assert c2 == {"A": 2} and autofix.lasting(["A"], c2, 2) == ["A"]                  # twice in a row: a check
    assert autofix.streaks(c2, [], ["A"]) == {}                                       # read again: gone
    assert autofix.streaks(c2, ["B"], []) == {"B": 1, "A": 2}                         # not tried this run: kept as it was
    assert autofix.lasting(["A", "B", "C"], autofix.streaks(None, ["A", "B", "C"], []), 4) == ["A", "B", "C"]   # 3 of 4 at once
    assert autofix.lasting(["A", "B"], autofix.streaks(None, ["A", "B"], []), 2) == []                         # 2 is not "many"


# ---------- the IPO job: a company filing page that didn't answer once is read again at the next run, and is no check ----------
def _sec_down_for(monkeypatch, edgar, names):
    real = edgar.docs_for

    def docs_for(name, today):
        if any(n.lower() in name.lower() for n in names()):
            edgar.names.append(name)
            raise SourceError("The SEC", "The SEC is having trouble (500).", busy=True)
        return real(name, today)
    monkeypatch.setattr(edgar, "docs_for", docs_for)


def test_a_filing_page_that_did_not_answer_once_is_no_check_and_two_runs_running_is_one(w, monkeypatch):  # noqa: F811
    job = I.Job(sleep=lambda s: None)
    monkeypatch.setattr(I, "job", job)                                  # Admin reads the module's job: this one, not one another test left a gap in
    real = w["edgar"].docs_for
    _sec_down_for(monkeypatch, w["edgar"], lambda: ["iambic"])          # one company's page of the ten looked up
    job.read("US", NOW)
    assert any(p.startswith(I.MINOR_PREFIX + "Iambic") for p in job.status["problems"])                     # in the log
    assert job.status["check"] is None and job.status["last_error"] is None                                 # no check (it was one)
    row = admin_jobs._row("ipo", "IPOs", "x", NOW.isoformat(), job.status["last_error"], job.status["problems"], check=job.status["check"])
    assert row["state"] == "ok"
    assert not [c for c in admin_jobs.job_checks() if c.id == "job:ipo" and c.problem]
    # the page that didn't answer is looked up again at the next run (it was marked read and waited two days)
    w["edgar"].names.clear()
    job.read("US", NOW + timedelta(hours=1))
    assert any("Iambic" in n for n in w["edgar"].names)
    assert "1 company filing page the SEC didn't answer in 2 runs in a row (Iambic" in job.status["check"]
    assert "read again at the next run" in job.status["check"]
    # an India read in between keeps the US note (it said nothing of the US pages)
    job.read("IN", NOW + timedelta(hours=1, minutes=5))
    assert "Iambic" in (job.status["check"] or "")
    # it answers at the run after: the check is gone
    monkeypatch.setattr(w["edgar"], "docs_for", real)
    job.read("US", NOW + timedelta(hours=2))
    assert "company filing page" not in (job.status["check"] or "") and not (I.state()["US"].get("pages_failing") or {})


def test_many_filing_pages_failing_in_one_run_are_a_check_at_once(w, monkeypatch):  # noqa: F811
    w["edgar"].down = set()
    _sec_down_for(monkeypatch, w["edgar"], lambda: [""])                  # every company page
    job = I.Job(sleep=lambda s: None)
    job.read("US", NOW)
    assert "company filing pages the SEC didn't answer in the last run" in job.status["check"]


# ---------- Company pages' prices: one pass that read nothing is the next pass's to read; two in a row are a Problem ----------
def _price_row(monkeypatch, us: dict) -> dict:
    monkeypatch.setattr(main, "price_refresh_status", {"last_run": "2026-11-13T15:00:00+00:00", "IN": {"refreshed": 5, "left": 0, "failed": 0}, "US": us})
    return {r["name"]: r for r in admin_jobs.rows()}["Company pages' prices"]


def test_one_price_pass_that_read_nothing_is_no_problem_and_two_in_a_row_are(monkeypatch):
    r = _price_row(monkeypatch, {"refreshed": 0, "left": 120, "failed": 300, "errors": 300, "failed_passes": 1})
    assert r["state"] == "ok" and r["error"] is None
    assert any("no page's price could be read in the last pass (300 tried); read again at the next pass" in x for x in r["log"])
    r = _price_row(monkeypatch, {"refreshed": 0, "left": 120, "failed": 300, "errors": 300, "failed_passes": 2})
    assert r["state"] == "bad" and "US: no page's price could be read in the last 2 passes (300 tried)" in r["error"]
    r = _price_row(monkeypatch, {"error": "storage down", "failed_passes": 1})
    assert r["state"] == "ok" and any("US: storage down; read again at the next pass" in x for x in r["log"])
    r = _price_row(monkeypatch, {"error": "storage down", "failed_passes": 3})
    assert r["state"] == "bad" and "US: storage down" in r["error"]


def test_the_price_job_counts_the_passes_in_a_row_that_read_nothing(monkeypatch):
    got = {"US": {"refreshed": 0, "left": 10, "failed": 10, "errors": 10}, "IN": {"refreshed": 3, "left": 0, "failed": 0}}
    monkeypatch.setattr(main.stock_page_store, "refresh_prices", lambda region, *a, **k: dict(got[region]))
    monkeypatch.setattr(main, "rotation_after_close", lambda: None)
    monkeypatch.setattr(main, "price_refresh_status", {"last_run": None, "IN": None, "US": None})
    assert main.stock_price_refresh_once(sleep=lambda s: None)["US"]["failed_passes"] == 1
    st = main.stock_price_refresh_once(sleep=lambda s: None)
    assert st["US"]["failed_passes"] == 2 and st["IN"]["failed_passes"] == 0
    got["US"] = {"refreshed": 4, "left": 0, "failed": 6, "errors": 6}                   # some read: the source works
    assert main.stock_price_refresh_once(sleep=lambda s: None)["US"]["failed_passes"] == 0
    got["US"] = {"refreshed": 0, "left": 10, "source_down": True}                         # turned away before the login: not a failure
    assert main.stock_price_refresh_once(sleep=lambda s: None)["US"]["failed_passes"] == 0


# ---------- the feature check: a check failing in one run is run again an hour later; still failing then, the owner hears ----------
def _world(monkeypatch):
    from tests import world as W
    return W.build(monkeypatch)


def test_a_feature_check_failing_once_is_not_mailed_and_the_same_failure_next_run_is(monkeypatch):
    built = _world(monkeypatch)
    try:
        fails = {"Broken source"}
        monkeypatch.setattr(main, "platform_checks", lambda: [
            (n, "Research", (lambda n=n: pc._result(n, "Research", "fail" if n in fails else "pass", "down" if n in fails else "ok")))
            for n in ("Broken source", "Fine", "Also fine", "Third")])
        told = []
        monkeypatch.setattr(main, "tell_admins", lambda subject, text: told.append((subject, text)) or 1)
        main.daily_platform_check(retry_after=0.01)
        assert told == [] and main.platform_checks_failing()[0].problem is None
        assert "platform" not in autofix.load()["open"]
        main.daily_platform_check(retry_after=0.01)                                       # the run an hour later: still failing
        assert len(told) == 1 and "Broken source" in told[0][1]
        assert main.platform_checks_failing()[0].problem.startswith("1 check failing after a retry: Broken source")
        # a source's moment: failing once, passing at the run after, is never mailed
        told.clear()
        fails.clear()
        main.daily_platform_check(retry_after=0.01)
        fails.add("Fine")
        main.daily_platform_check(retry_after=0.01)
        fails.clear()
        main.daily_platform_check(retry_after=0.01)
        assert told == []
    finally:
        built["close"]()


def test_many_feature_checks_failing_at_once_are_mailed_at_once(monkeypatch):
    built = _world(monkeypatch)
    try:
        monkeypatch.setattr(main, "platform_checks", lambda: [
            (n, "Server", (lambda n=n: pc._result(n, "Server", "fail" if n != "Fine" else "pass", "down"))) for n in ("A", "B", "C", "Fine")])
        told = []
        monkeypatch.setattr(main, "tell_admins", lambda subject, text: told.append((subject, text)) or 1)
        main.daily_platform_check(retry_after=0.01)
        assert len(told) == 1 and "3 checks failing" in told[0][0]
    finally:
        built["close"]()


def test_an_unconfirmed_failure_is_checked_again_an_hour_later_once(monkeypatch):
    built = _world(monkeypatch)
    try:
        at = datetime(2026, 11, 13, 0, 25, tzinfo=timezone.utc)
        out = {"at": at.isoformat(), "auto": True, "build": None, "counts": {"pass": 1, "warn": 0, "fail": 1},
               "checks": [{"name": "News", "state": "fail", "detail": "down"}, {"name": "Fine", "state": "pass", "detail": "ok"}]}
        db.set_setting(main.PLATFORM_LAST, json.dumps(out))
        db.set_setting(main.PLATFORM_HISTORY, json.dumps([{"at": (at - timedelta(days=1)).isoformat(), "failed": []}, {"at": at.isoformat(), "failed": ["News"]}]))
        ran = []
        monkeypatch.setattr(main, "daily_platform_check", lambda *a, **k: ran.append(1) or {})
        monkeypatch.setattr(leader, "leading", lambda: True)
        monkeypatch.setattr(main, "platform_build_due", lambda now: None)
        assert main.platform_recheck_due(at + timedelta(minutes=30)) is None                 # not yet
        early = (at + timedelta(minutes=70)).astimezone(main.IST)                           # 07:05 IST, before the day's check
        assert main.platform_recheck_due(early) == at.isoformat()
        assert main.platform_pass(early) is False and ran == [1]
        assert main.platform_pass(early + timedelta(minutes=5)) is False and ran == [1]       # once for that run
        # a failure the run before had too is already an issue: no extra run
        db.set_setting(main.PLATFORM_HISTORY, json.dumps([{"at": (at - timedelta(days=1)).isoformat(), "failed": ["News"]}, {"at": at.isoformat(), "failed": ["News"]}]))
        assert main.platform_recheck_due(early) is None
    finally:
        built["close"]()


# ---------- owner ask (d): how far the company-page rebuild to the current facts version has got, per market, in Admin ----------
def test_the_rebuild_to_the_current_facts_version_is_counted_per_market_from_the_stored_pages(monkeypatch):
    from app import screens, stock_pages
    from tests.fake_db import headers
    from tests.test_screens import facts
    built = _world(monkeypatch)
    try:
        v = stock_pages.FACTS_VERSION
        pages = {"NEW1": facts("NEW1", "New One", v=v), "NEW2": facts("NEW2", "New Two", v=v), "OLD1": facts("OLD1", "Old One", v=v - 1),
                 "OLD2": facts("OLD2", "Old Two"),                                   # no version stamp: the first
                 "FUND": facts("FUND", "A Fund", v=v - 1, not_company=True)}          # nothing to show: not a page to rebuild
        for sym, f in pages.items():
            db.set_setting(f"stocks:page:IN:{sym}", json.dumps({"ts": 1e10, "facts": f}))
        db.set_setting("stocks:page:IN:EMPTY", json.dumps({"ts": 1e10, "facts": {}}))
        monkeypatch.setattr(stock_pages, "nse_twins", lambda: {})
        stock_pages._rebuild_mem.update(at=0.0, value=None)
        before = stock_pages.rebuild_progress(now=1.0)
        assert before["version"] == v and [m["counted"] for m in before["markets"]] == [False, False]      # not gathered yet
        screens.build_index("IN")
        assert stock_pages.rebuild_progress(now=2.0) is before                                             # kept a few minutes
        got = stock_pages.rebuild_progress(now=2.0 + stock_pages.REBUILD_MEMORY)
        india = got["markets"][0]
        assert (india["region"], india["counted"], india["current"], india["of"], india["pages"]) == ("IN", True, 2, 4, 6)
        assert got["markets"][1] == {"region": "US", "counted": False, "at": None}
        # a count kept at an earlier version is not this version's progress
        monkeypatch.setattr(stock_pages, "FACTS_VERSION", v + 1)
        stock_pages._rebuild_mem.update(at=0.0, value=None)
        assert stock_pages.rebuild_progress(now=5.0)["markets"][0]["counted"] is False
        monkeypatch.setattr(stock_pages, "FACTS_VERSION", v)
        stock_pages._rebuild_mem.update(at=0.0, value=None)
        c = built["client"]
        assert c.get("/admin/stock-pages/rebuild", headers=headers("pro-token")).status_code == 403
        r = c.get("/admin/stock-pages/rebuild", headers=headers("admin-token")).json()
        assert r["version"] == v and r["markets"][0]["current"] == 2 and r["markets"][0]["of"] == 4
    finally:
        stock_pages._rebuild_mem.update(at=0.0, value=None)
        built["close"]()


# ---------- the two server errors in the live list (refs 691A25 and 44AECE): fixed in later releases; each reproduced here ----------
def _shallow_stack(room: int = 150):
    """A recursion limit just above the current depth, so an endless recursion fails at once instead of after minutes."""
    import sys
    depth, f = 0, sys._getframe()
    while f:
        depth, f = depth + 1, f.f_back
    return depth + room


def test_691A25_a_close_under_a_hundredth_of_a_cent_never_divides_the_theme_line_by_zero():
    """ZeroDivisionError at theme_prices.py:98 in equal_weight's list comprehension (GET /research/theme-dive/prices, 12 Nov 17:20 IST, on
    Release 41): a share's weekly close rounded to four decimals became 0.0 and the next week's change was divided by it. Release 42
    keeps closes to six significant figures and skips a non-positive base (LIVE7A-002)."""
    from datetime import date
    from app.intel import theme_prices as P
    from tests.test_live7a_themes import _bars
    end, start = date(2026, 11, 10), date(2023, 1, 2)
    penny = P.reduce_bars(_bars(start, end, lambda d: 0.00003 + (d - start).days * 1e-8))
    big = P.reduce_bars(_bars(start, end, lambda d: 100 + (d - start).days * 0.05))
    weeks, line = P.equal_weight([penny, big])
    assert len(line) > 100 and all(v > 0 for v in line)
    # and a kept weekly close of 0 (as the old rounding left) is skipped as a base, not divided by
    zero = {**penny, "closes": [0.0] + penny["closes"][1:]}
    assert P.equal_weight([zero, big])[1][-1] > 0


def test_44AECE_paging_a_table_with_tall_rows_ends_without_a_recursion():
    """RecursionError at deck.py:80 in _width (GET /research/theme-dive/deck, 6 Nov 23:57 IST): table_pages evened its pages out by
    calling itself with the same number of rows a page, forever; each call measured the rows again, so the stack ran out while measuring.
    Fixed 7 Nov (R15): it evens out only to fewer rows a page than the pass before, so it ends."""
    import sys
    from app import deck
    rows = [[f"Company {i} Ltd (C{i})", "Auto parts", "₹1,000 cr", "“" + " ".join(["wheel"] * (100 if i in (2, 3) else 1)) + "”",
             "Added, not yet confirmed"] for i in range(5)]
    old = sys.getrecursionlimit()
    sys.setrecursionlimit(_shallow_stack())
    try:
        pages = deck.table_pages(deck.MEMBER_HEAD, rows, deck.MEMBER_WIDTHS, deck.W_IN - 2 * deck.M, deck.BOT - deck.TOP - 0.35, most=16)
    finally:
        sys.setrecursionlimit(old)
    assert [r for p in pages for r in p] == rows


def test_a_server_error_is_kept_with_the_build_it_happened_on(monkeypatch):
    from fastapi.testclient import TestClient
    from app import build_info
    saved = {}
    monkeypatch.setattr(db, "set_setting", lambda k, v: saved.__setitem__(k, v))
    monkeypatch.setattr(db, "get_setting", lambda k: saved.get(k))
    monkeypatch.setattr(build_info, "info", lambda env=None: {"short": "abc1234"})

    def boom49():
        raise KeyError("x")
    main.app.add_api_route("/__boom49", boom49)
    main.RECENT_ERRORS.clear()
    r = TestClient(main.app, raise_server_exceptions=False).get("/__boom49")
    assert r.status_code == 500 and main.RECENT_ERRORS[-1]["build"] == "abc1234"
    assert main.server_status()["recent_errors"][0]["build"] == "abc1234"
    main.RECENT_ERRORS.clear()
