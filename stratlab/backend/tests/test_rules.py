"""Rates and rules: the values checked on 4 and 5 Oct 2026 (trading costs, freeze limits, return due dates, the 2025 Act's
section numbers), the dated register and its platform-check row, and the daily watch of the official sources."""
from datetime import date, datetime, timezone

import pytest

from app import db, money_advance_tax as A, money_calendar as MC, rules, rules_watch as W, tax_total as T
from app.engine import costs as C
from app.options import data as O
from tests import world
from tests.fake_db import FakeSupabase


@pytest.fixture
def fdb(monkeypatch):
    fake = FakeSupabase()
    monkeypatch.setattr(db, "_client", fake)
    return fake


# ---------- the values ----------
def test_us_fees_are_the_2026_ones():
    c = C.order_costs("us", "sell", 1000, 50.0, 0)
    assert c["sec"] == pytest.approx(50000 * 20.60 / 1e6)                # $20.60 a million from 4 Apr 2026
    assert c["finra"] == pytest.approx(1000 * 0.000195)
    assert C.order_costs("us", "sell", 1_000_000, 1.0, 0)["finra"] == 9.79   # capped
    assert "sec" not in C.order_costs("us", "buy", 1000, 50.0, 0)


def test_nse_charges_include_the_ipft_contribution():
    eq = C.order_costs("in_eq", "buy", 100, 1000.0, 0)                   # ₹1 lakh
    assert eq["exchange"] == pytest.approx(1e5 * (307 + 10) / 1e7)        # ₹307 + SEBI ₹10 a crore
    assert C.order_costs("in_fut", "buy", 1, 1e7, 0)["exchange"] == pytest.approx(183 + 10)
    assert C.order_costs("in_opt", "buy", 1, 1e7, 0)["exchange"] == pytest.approx(3513 + 10)


def test_bse_options_have_their_own_charge():
    assert C.kind_of({"market": "IN", "type": "CE", "exchange": "BFO"}) == "in_bse_opt"
    assert C.kind_of({"market": "IN", "type": "PE", "exchange": "NFO"}) == "in_opt"
    assert C.kind_of({"market": "IN", "type": "FUT", "exchange": "BFO"}) == "in_fut"
    b = C.order_costs("in_bse_opt", "sell", 1, 1e7, 0)
    assert b["exchange"] == pytest.approx(3250 + 10) and b["stt"] == pytest.approx(1e7 * 0.0015)
    assert C.tax_estimate("in_bse_opt", [])["amount"] is None


def test_options_engine_charges_bse_options_at_the_bse_rate():
    from app.options.engine import OptionsEngine
    from tests.test_options import straddle
    assert OptionsEngine(straddle(exchange="BFO", underlying="SENSEX")).kind == "in_bse_opt"
    assert OptionsEngine(straddle()).kind == "in_opt"


def test_freeze_limits_switch_on_the_day_nse_set():
    assert O.freeze("NIFTY", "2026-10-04") == 1800 and O.freeze("NIFTY", "2026-10-05") == 3510
    assert O.freeze("BANKNIFTY", "2026-10-05") == 1440 and O.freeze("MIDCPNIFTY", "2026-12-01") == 5760
    assert O.freeze("SENSEX", "2026-10-05") == 1000 and O.freeze("UNKNOWN", "2026-10-05") == 0


def test_freeze_limits_before_and_from_5_oct_2026_match_the_nse_circulars():
    """NSE/FAOP/68834 (from 1 Jul 2025) until 4 Oct 2026, NSE/FAOP/76693 from 5 Oct 2026 (checked 5 Oct 2026)."""
    before = {"NIFTY": 1800, "BANKNIFTY": 600, "FINNIFTY": 1800, "MIDCPNIFTY": 2800, "NIFTYNXT50": 600, "NIFTYFPI": 8500}
    after = {"NIFTY": 3510, "BANKNIFTY": 1440, "FINNIFTY": 3240, "MIDCPNIFTY": 5760, "NIFTYNXT50": 1125, "NIFTYFPI": 53900}
    assert {k: O.freeze(k, "2026-10-04") for k in before} == before
    assert {k: O.freeze(k, "2026-10-05") for k in after} == after
    assert "NIFTYFPI" in W.INDICES
    freeze = next(r for r in rules.registry() if r["id"] == "freeze")
    assert "NSE/FAOP/76693" in freeze["source"] and "NIFTYFPI 53,900" in freeze["value"]


def test_return_due_dates_follow_the_finance_act_2026():
    facts = " ".join(T.filing_facts(2025, 1e6, True))
    assert "31 August" in facts and "31 October" in facts and "31 March" in facts
    assert "31 July after the year ends without an audit" in " ".join(T.filing_facts(2024, 1e6, True))
    assert T.NEW_ACT_NOTE in T.filing_facts(2026, 1e6, True) and T.NEW_ACT_NOTE not in T.filing_facts(2025, 1e6, True)
    assert "111A is now 196" in T.NEW_ACT_NOTE and "112A is now 198" in T.NEW_ACT_NOTE and "87A is now 156" in T.NEW_ACT_NOTE


def test_234b_counts_to_31_august_with_business_income():
    assert A.return_due(2025, True) == date(2026, 8, 31) and A.return_due(2025, False) == date(2026, 7, 31)
    assert A.return_due(2024, True) == date(2025, 7, 31)                  # before the Finance Act 2026
    plain = A.schedule(2026, 100000, [100000] * 4, 0, [], date(2027, 4, 2))["b234"]
    biz = A.schedule(2026, 100000, [100000] * 4, 0, [], date(2027, 4, 2), business=True)["b234"]
    assert plain["until"] == "2027-07-31" and plain["months"] == 4
    assert biz["until"] == "2027-08-31" and biz["months"] == 5 and biz["interest"] == 5000


def test_calendar_uses_the_new_section_numbers_from_fy_2026():
    late = next(e for e in MC.tax_dates(2026) if e["kind"] == "itr_late")
    assert "263(4)" in late["detail"]
    assert "139(4)" in next(e for e in MC.tax_dates(2025) if e["kind"] == "itr_late")["detail"]


# ---------- the register ----------
def test_register_reads_the_values_the_app_uses():
    reg = {r["id"]: r for r in rules.registry()}
    assert reg["sec_fee"]["value"].startswith("$20.60")
    assert "0.05%" in reg["stt_futures"]["value"] and "0.15%" in reg["stt_options"]["value"]
    assert "NIFTY 3,510" in reg["freeze"]["value"]
    assert reg["ppf"]["value"].startswith("7.1%") and reg["epf"]["value"].startswith("8.25%")
    for r in reg.values():
        assert r["area"] in rules.AREAS and r["source"] and r["where"] and r["value"], r["id"]
    assert set(rules.REVIEWED) == set(rules.AREAS)
    assert {r["area"] for r in reg.values()} == set(rules.AREAS)


def test_register_follows_a_changed_constant(monkeypatch):
    monkeypatch.setattr(C, "US_SEC_FEE", 0.0000278)
    assert next(r for r in rules.registry() if r["id"] == "sec_fee")["value"].startswith("$27.80")


def test_review_is_due_after_90_days_or_a_known_change_day():
    fresh = {a: "2026-10-04" for a in rules.AREAS}
    assert rules.check(date(2026, 10, 20), fresh)["state"] == "pass"
    c = rules.check(date(2027, 1, 2), fresh)
    assert c["state"] == "warn" and "Interest rates" in c["detail"] and "January to March" in c["detail"]
    old = {**{a: "2026-12-20" for a in rules.AREAS}, "tax": "2026-06-01"}
    c = rules.check(date(2026, 12, 21), old)
    assert c["state"] == "warn" and "Income tax" in c["detail"] and "over 90 days" in c["detail"]
    # 1 April passes: tax and trading costs are due even when reviewed recently
    c = {r["area"]: r for r in rules.review_status(date(2027, 4, 1), {a: "2027-03-20" for a in rules.AREAS})}
    assert c["tax"]["due"] and c["trading_costs"]["due"] and c["interest_rates"]["due"] and not c["surveillance"]["due"]
    assert c["surveillance"]["next"] is None or c["surveillance"]["next"]["date"] > "2027-04-01"


def test_next_known_day_and_the_sec_fiscal_year():
    assert rules.next_known("trading_costs", date(2026, 9, 30))["date"] == "2026-10-01"
    assert rules.next_known("trading_costs", date(2026, 10, 1))["date"] == "2027-01-01"
    assert [d["date"] for d in rules.known_since("interest_rates", date(2026, 3, 31), date(2026, 10, 1))] == \
        ["2026-04-01", "2026-07-01", "2026-10-01"]


def test_a_change_waiting_at_the_source_warns():
    fresh = {a: "2026-10-04" for a in rules.AREAS}
    watch = {"sources": [{"name": "SEC fee rate", "pending": {"why": "differs"}}]}
    c = rules.check(date(2026, 10, 5), fresh, watch)
    assert c["state"] == "warn" and "SEC fee rate" in c["detail"]


# ---------- reading the sources ----------
def test_read_freeze_and_lots():
    assert W.read_freeze("SYMBOL,VOL_FRZ_QTY\nNIFTY,3510\nBANKNIFTY,\"1,440\"\nRELIANCE,9000\n") == {"NIFTY": 3510, "BANKNIFTY": 1440}
    assert W.read_freeze("SYMBOL,VOL_FRZ_QTY\nNIFTYFPI,\"53,900\"\n") == {"NIFTYFPI": 53900}
    with pytest.raises(ValueError):
        W.read_freeze("\xd0\xcf\x11\xe0\x00\x00binary")
    with pytest.raises(ValueError):
        W.read_freeze("<html>Not found</html>")
    csv = ("UNDERLYING,SYMBOL,OCT-26,NOV-26,DEC-26\nNIFTY 50,NIFTY,65,65,65\nNIFTY BANK,BANKNIFTY,30,30,30\n"
           "Derivatives on Individual Securities,,,\nRELIANCE INDUSTRIES,RELIANCE,500,500,500\n")
    assert W.read_lots(csv) == {"NIFTY": 65, "BANKNIFTY": 30}


def test_read_sec_ppf_and_circulars():
    page = "<h2>Fee Rate Advisory #2 for Fiscal Year 2026</h2><p>the rate will be <b>$20.60 per million</b> from April 4</p><p>$0.00 per million</p>"
    assert W.read_sec_fee(page) == 20.60
    with pytest.raises(ValueError):
        W.read_sec_fee("<p>nothing here</p>")
    ppf = "<tr><td>Public Provident Fund Scheme, 1968</td><td>01.10.2026</td><td>7.1</td></tr>"
    assert W.read_ppf(ppf) == 7.1
    with pytest.raises(ValueError):
        W.read_ppf("<p>Senior Citizens 8.2</p>")
    data = {"data": [{"sub": "Revision in Transaction Charges", "cirDisplayDate": "27-Feb-2026", "circFilelink": "https://x/FA1.pdf"},
                     {"sub": "Listing of new securities", "cirDisplayDate": "27-Feb-2026"},
                     {"sub": "Quantity Freeze Limits for Indices", "cirDisplayDate": "30-Sep-2026"}]}
    got = W.read_circulars(data)
    assert [c["subject"] for c in got] == ["Revision in Transaction Charges", "Quantity Freeze Limits for Indices"]
    assert got[0]["url"] == "https://x/FA1.pdf" and got[0]["id"] != got[1]["id"]


# ---------- the daily watch ----------
class FakeFetch:
    def __init__(self, answers):
        self.answers = answers

    def get(self, src, today):
        a = self.answers.get(src["id"])
        if isinstance(a, Exception):
            raise a
        return a


GOOD = {
    "nse_freeze": "SYMBOL,QTY\nNIFTY,3510\nBANKNIFTY,1440\nFINNIFTY,3240\nMIDCPNIFTY,5760\nNIFTYNXT50,1125\n",
    "nse_lots": "U,SYMBOL,OCT\nX,NIFTY,65\nY,BANKNIFTY,30\n",
    "sec_fee": "<p>$20.60 per million</p>",
    "ppf": "<td>Public Provident Fund</td><td>7.1</td>",
    "nse_circulars": {"data": [{"sub": "Revision in Transaction Charges", "date": "27-Feb-2026"}]},
}
NOW = datetime(2026, 10, 6, 3, 0, tzinfo=timezone.utc)
TODAY = date(2026, 10, 6)


def test_first_run_learns_and_matching_values_raise_nothing(fdb):
    assert W.run(FakeFetch(GOOD), TODAY, NOW) == []
    st = {s["id"]: s for s in W.state()["sources"]}
    assert st["sec_fee"]["shown"] == "20.6" and st["sec_fee"]["expected"] == "20.6" and not st["sec_fee"]["pending"]
    assert st["nse_lots"]["value"] == {"NIFTY": 65, "BANKNIFTY": 30}
    assert W.run(FakeFetch(GOOD), TODAY, NOW) == []                      # the same again: still nothing


def test_a_new_sec_rate_alerts_once_and_stays_until_seen(fdb):
    W.run(FakeFetch(GOOD), TODAY, NOW)
    moved = {**GOOD, "sec_fee": "<p>$22.10 per million</p>"}
    lines = W.run(FakeFetch(moved), TODAY, NOW)
    assert len(lines) == 1 and "SEC fee rate" in lines[0] and "22.1" in lines[0] and "20.6" in lines[0]
    assert W.run(FakeFetch(moved), TODAY, NOW) == []                     # not twice for the same value
    st = {s["id"]: s for s in W.state()["sources"]}
    assert st["sec_fee"]["pending"]["why"] == "differs from what StratLab uses"
    assert rules.check(TODAY, watch=W.state())["state"] == "warn"
    assert W.mark_seen("sec_fee") and not W.mark_seen("sec_fee")
    assert not {s["id"]: s for s in W.state()["sources"]}["sec_fee"]["pending"]
    assert W.run(FakeFetch(moved), TODAY, NOW) == []                     # seen: the same value never alerts again


def test_pending_clears_when_the_code_catches_up(fdb, monkeypatch):
    W.run(FakeFetch({**GOOD, "ppf": "<td>PPF</td><td>7.4</td>"}), TODAY, NOW)
    assert {s["id"]: s for s in W.state()["sources"]}["ppf"]["pending"]
    from app import money_networth
    monkeypatch.setattr(money_networth, "PPF_RATE", 7.4)
    W.run(FakeFetch({**GOOD, "ppf": "<td>PPF</td><td>7.4</td>"}), TODAY, NOW)
    assert not {s["id"]: s for s in W.state()["sources"]}["ppf"]["pending"]


def test_lot_change_alerts_against_the_last_copy(fdb):
    W.run(FakeFetch(GOOD), TODAY, NOW)
    lines = W.run(FakeFetch({**GOOD, "nse_lots": "U,SYMBOL,OCT\nX,NIFTY,75\nY,BANKNIFTY,30\n"}), TODAY, NOW)
    assert len(lines) == 1 and "NIFTY 75" in lines[0] and "NIFTY 65" in lines[0]


def test_new_circulars_alert_after_the_first_run(fdb):
    W.run(FakeFetch(GOOD), TODAY, NOW)
    more = {**GOOD, "nse_circulars": {"data": GOOD["nse_circulars"]["data"] + [{"sub": "Quantity Freeze Limits for Indices", "date": "1-Oct-2026"}]}}
    lines = W.run(FakeFetch(more), TODAY, NOW)
    assert lines == ["- NSE circular 1-Oct-2026: Quantity Freeze Limits for Indices"]
    assert W.run(FakeFetch(more), TODAY, NOW) == []
    assert {s["id"]: s for s in W.state()["sources"]}["nse_circulars"]["pending"]["items"][0]["subject"].startswith("Quantity")


def test_a_failing_source_keeps_its_value_and_counts(fdb):
    W.run(FakeFetch(GOOD), TODAY, NOW)
    W.run(FakeFetch({**GOOD, "sec_fee": RuntimeError("refused (403)")}), TODAY, NOW)
    s = {s["id"]: s for s in W.state()["sources"]}["sec_fee"]
    assert s["error"] == "refused (403)" and s["fails"] == 1 and s["value"] == 20.6


def test_job_runs_once_a_day_after_the_hour_and_tells_admins(fdb):
    told = []
    job = W.Job(tell=lambda subject, text: told.append((subject, text)), fetcher=FakeFetch(GOOD))
    assert job.tick(datetime(2026, 10, 6, 1, 0, tzinfo=timezone.utc)) == 0          # 06:30 IST: too early
    assert job.tick(datetime(2026, 10, 6, 3, 0, tzinfo=timezone.utc)) == 0 and not told   # ran, nothing changed
    job.fetcher = FakeFetch({**GOOD, "sec_fee": "<p>$9.90 per million</p>"})
    assert job.tick(datetime(2026, 10, 6, 5, 0, tzinfo=timezone.utc)) == 0          # already ran today
    assert job.tick(datetime(2026, 10, 7, 3, 0, tzinfo=timezone.utc)) == 1
    subject, text = told[0]
    assert "1 rate or rule change" in subject and "Nothing in StratLab changes by itself" in text


# ---------- Admin ----------
@pytest.fixture
def w(monkeypatch):
    built = world.build(monkeypatch)
    yield built
    built["close"]()


def test_admin_sees_the_register_and_can_run_and_mark_seen(w, monkeypatch):
    from app import main
    c, admin = w["client"], world.headers("admin-token")
    assert c.get("/admin/rules", headers=world.headers("pro-token")).status_code == 403
    r = c.get("/admin/rules", headers=admin)
    assert r.status_code == 200, r.text
    body = r.json()
    assert any(x["id"] == "sec_fee" for x in body["rules"]) and len(body["areas"]) == len(rules.AREAS)
    assert body["check"]["name"] == "Rates and rules last reviewed"
    told = []
    monkeypatch.setattr(main, "tell_admins", lambda subject, text: told.append(subject) or 1)
    monkeypatch.setattr(main.rules_watch_job, "fetcher", FakeFetch({**GOOD, "sec_fee": "<p>$30.00 per million</p>"}))
    monkeypatch.setattr(main.rules_watch_job, "tell", lambda s, t: main.tell_admins(s, t))
    r = c.post("/admin/rules/watch/run", headers=admin)
    assert r.status_code == 200 and told
    sec = next(s for s in r.json()["watch"]["sources"] if s["id"] == "sec_fee")
    assert sec["pending"]["now"] == "30"
    assert c.post("/admin/rules/watch/sec_fee/seen", headers=admin).status_code == 200
    assert c.post("/admin/rules/watch/sec_fee/seen", headers=admin).status_code == 404
    assert c.post("/admin/rules/watch/run", headers=world.headers("pro-token")).status_code == 403


def test_platform_check_has_the_rules_row(w):
    r = w["client"].post("/admin/platform/check", headers=world.headers("admin-token"))
    row = next(x for x in r.json()["checks"] if x["name"] == "Rates and rules last reviewed")
    assert row["area"] == "Rules" and row["state"] in ("pass", "warn")
