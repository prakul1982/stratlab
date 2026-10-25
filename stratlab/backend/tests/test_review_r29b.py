"""Round 29B (owner pass): the Kite token alert once per event, weekly summary times, and the other fixes of the round."""
import threading
from datetime import datetime, timezone

import pytest

from app import db, kite_auto
from tests import world


@pytest.fixture
def w(monkeypatch):
    built = world.build(monkeypatch)
    yield built
    built["close"]()


def test_the_kite_cancelled_alert_goes_once_per_event_and_once_when_two_calls_are_refused_together():
    from app.kite_service import KiteService, IST
    k = KiteService.__new__(KiteService)
    told = []
    k.access_token, k.token_day, k.invalid_reason, k.on_invalid = "T", datetime.now(IST).date().isoformat(), None, told.append
    k.ready = lambda: not k.invalid_reason
    ts = [threading.Thread(target=k._token_rejected, args=(RuntimeError("TokenException"),)) for _ in range(6)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert len(told) == 1


def test_alert_once_dedupes_an_event_within_ten_minutes_across_containers(w, monkeypatch):
    a = kite_auto.AutoLogin.__new__(kite_auto.AutoLogin)
    sent = []
    monkeypatch.setattr(kite_auto.AutoLogin, "_alert", lambda self, text: sent.append(text))
    assert a.alert_once("kite-token-cancelled:2026-10-15", "x", now=1000.0)
    assert not a.alert_once("kite-token-cancelled:2026-10-15", "x", now=1001.0)      # the second container, the same second
    assert not a.alert_once("kite-token-cancelled:2026-10-15", "x", now=1500.0)
    assert a.alert_once("kite-token-cancelled:2026-10-15", "x", now=1700.0)          # a later event
    assert a.alert_once("other-event", "y", now=1001.0)
    assert len(sent) == 3


def test_weekly_summary_times_carry_ist():
    from datetime import timedelta
    from app import weekly
    IST = timezone(timedelta(hours=5, minutes=30))
    now = datetime(2026, 10, 12, 9, 0, tzinfo=IST)
    assert weekly._when("2026-10-07T04:00:00+00:00", now) == " (Wed 7 Oct, 09:30 IST)"


# ---------- R29B-008: the rule builder's 52-week low and a rule against the entry price ----------
def _ai(entry, exit_=()):
    return {"entry": entry, "exit": list(exit_), "entryJoin": "all", "side": "long", "shortEntry": [], "shortExit": [], "risk": {},
            "mentioned": [], "notes": [], "tf": "1d"}


def test_a_yearly_low_is_the_252_candle_low_and_zero_is_never_kept():
    from app import ai_writer
    dead = {"l": {"t": "price"}, "op": "lt", "r": {"t": "num", "v": 0}}
    for words in ("Buy when it touches its 12-month low", "Buy when it touches its yearly low", "Buy when it touches its 52 week low"):
        out = ai_writer.check_against_text(_ai([dead]), words)
        assert out["entry"] == [{"l": {"t": "low"}, "op": "lt", "r": {"t": "dc_lower", "p": 252}}], words
    out = ai_writer.check_against_text(_ai([dead]), "Buy when it touches its all-time low")     # no level to read: left out, and said
    assert out["entry"] == [] and any("left out" in n for n in out["notes"])


def test_a_rule_against_a_multiple_of_the_price_becomes_a_target_or_a_stop():
    from app import ai_writer
    price = {"t": "price"}
    out = ai_writer.check_against_text(_ai([{"l": price, "op": "gt", "r": {"t": "sma", "p": 20}}],
                                           [{"l": price, "op": "gt", "r": {"t": "price", "k": 1.05}}]), "Buy above the 20-day average, sell at 5% profit")
    assert out["exit"] == [] and out["risk"]["tgt"] == 5.0 and "tgt" in out["mentioned"]
    assert any("profit target of 5% over the entry price" in n for n in out["notes"])


# ---------- R29B-015: 234B's due date is the tax report's 31 October when an audit applies ----------
def test_234b_runs_to_the_audit_cases_due_date():
    from app import money_advance_tax as adv, tax_total
    from datetime import date
    assert adv.return_due(2025, True, True) == date(2026, 11, 21)            # as CBDT Circular 7/2026 extended it (DH-001)
    assert adv.return_due(2025, True, False) == date(2026, 8, 31)
    assert adv.return_due(2025, False, False) == date(2026, 7, 31)
    assert tax_total.audit_applies(2025, 39.7e7, True) and not tax_total.audit_applies(2025, 39.7e7, False)
    assert not tax_total.audit_applies(2025, 5e7, True)            # between 1 and 10 crore: depends on cash receipts
    s = adv.schedule(2025, 100000.0, [0, 0, 0, 100000.0], 0.0, [], date(2026, 10, 15), True, True)
    assert [v for k, v in s.items() if isinstance(v, dict) and "return_by" in v][0]["return_by"] == "2026-11-21"


# ---------- R29B-016: the weekly brief's headlines are from the week it covers ----------
def test_a_weekly_brief_takes_headlines_from_its_trading_week_only(monkeypatch):
    from datetime import date
    from app.newsletter import content
    monkeypatch.setattr(content, "is_trading_day", lambda region, d: d.weekday() < 5)
    assert content.week_window("IN", date(2026, 10, 10)) == ("2026-10-05", "2026-10-09")        # Saturday's issue: Mon to Fri
    rows = [{"headline": "Sensex ends the week higher on bank buying", "at": "2026-10-07T09:00:00+05:30", "source": "x"},
            {"headline": "Nifty hits fresh 52-week low as selling deepens", "at": "2026-10-02T09:00:00+05:30", "source": "y"},
            {"headline": "Markets set for a quiet open on Monday", "at": "2026-10-10T06:00:00+05:30", "source": "z"}]
    got = content.pick_headlines("IN", rows, *content.week_window("IN", date(2026, 10, 10)))
    assert [h["headline"] for h in got] == ["Sensex ends the week higher on bank buying"]


# ---------- R29B-013: one EPS and labelled debt-to-equity ----------
def test_payout_line_uses_the_eps_ttm_the_page_shows(monkeypatch):
    from app.intel import routes
    seen = []
    monkeypatch.setattr(routes, "with_public_eps", lambda region, c: seen.append("eps") or {**c, "eps_done": True})
    monkeypatch.setattr(routes, "with_dividend_yield", lambda c, d, today: seen.append("div") or c)
    monkeypatch.setattr(routes, "stored_dividends", lambda r, s: [])
    monkeypatch.setattr(routes, "per_share_checked", lambda c: c)
    import app.intel.company as company
    monkeypatch.setattr(company, "with_today_range", lambda c: c)
    out = routes.page_figures("US", {"symbol": "AAPL"})
    assert seen == ["eps", "div"] and out["eps_done"]


def test_key_facts_say_which_debt_to_equity_they_show():
    from app.intel import key_facts
    c = {"metrics": [{"title": "Financial health", "items": [{"label": "Long-term debt / equity", "value": 0.66}]}]}
    row = key_facts.debt_and_cash(c, None, None, {})
    assert row["items"][0] == {"label": "Long-term debt / equity", "text": "0.66"}
    c = {"metrics": [{"title": "Returns and quality", "items": [{"label": "Total debt / equity", "value": 1.34}]}]}
    assert key_facts.debt_and_cash(c, None, None, {})["items"][0] == {"label": "Total debt / equity", "text": "1.34"}
    assert key_facts.debt_and_cash({}, None, None, {"debt_equity": 0.4})["items"][0]["label"] == "Total debt / equity"


# ---------- R29B-022: account identifiers hidden in provider error text on Admin ----------
def test_redact_ids_hides_account_identifiers_and_keeps_the_message():
    from app.connect.redact import redact_ids
    text = ("Provider refused the call: account 7f3a9c21b4 is over its quota (org_ab12cd34ef56, "
            "user 3f2b8c1e-1111-4d2a-9c3e-0123456789ab, ref 123456789012). Try again later.")
    out = redact_ids(text)
    for leaked in ("7f3a9c21b4", "org_ab12cd34ef56", "3f2b8c1e-1111-4d2a-9c3e-0123456789ab", "123456789012"):
        assert leaked not in out
    assert "Provider refused the call" in out and "over its quota" in out and "Try again later." in out
    assert redact_ids("Prices: IN took 45 seconds") == "Prices: IN took 45 seconds"
    assert redact_ids(None) is None


def test_a_job_row_on_admin_shows_its_error_without_ids():
    from app import admin_jobs
    row = admin_jobs._row("x", "X", "daily", "2026-10-15T10:00:00", "refused for account 7f3a9c21b4", ["customer id: cus_ABCDEF123456"])
    assert "7f3a9c21b4" not in row["error"] and "ABCDEF123456" not in row["log"][0]
