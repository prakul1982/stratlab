"""Account, user-data and admin fixes found in review (acct3): a hand-given plan kept after a halted subscription, admin
session routes and erase on a server that doesn't run the sessions, the erased user's Free Basic copy, invoice
numbering that never leaves an orphan or a gap, erase and export reaching past the row caps, billing in the export,
and a sign-in service that answers 429 or 5xx."""
import json
import time
from datetime import datetime, timedelta, timezone

import pytest
import time_machine

from app import admin, auth, billing, db, invoices, library, plans, user_data
from tests import fake_db, world

NOW = datetime(2026, 10, 14, 10, 0, tzinfo=timezone.utc)      # a fixed Wednesday midday, so no run depends on the date or the hour
ADMIN = world.headers("admin-token")
ME = "u-pro"


@pytest.fixture(autouse=True)
def _pinned_clock():
    with time_machine.travel(NOW, tick=True):
        yield


@pytest.fixture
def w(monkeypatch):
    built = world.build(monkeypatch)
    yield built
    built["close"]()


@pytest.fixture
def shared_db(monkeypatch):
    """A plain in-memory database for the invoices (no process lock: as if each call ran on its own server)."""
    monkeypatch.setattr(db, "_client", fake_db.FakeSupabase())
    return db.sb()


def setting_keys(prefix: str) -> list[str]:
    return sorted(r["key"] for r in db.sb().table("app_settings").select("key").execute().data if r["key"].startswith(prefix))


# ---------- 1. a hand-given plan survives the old subscription's late events ----------
def test_halted_then_set_plan_then_cancelled_event_keeps_the_grant(w):
    fake = w["db"]
    p = next(r for r in fake.tables["profiles"] if r["id"] == "u-basic")
    p.update(plan="free", plan_status="halted", razorpay_subscription_id="sub_H", pending_subscription_id="sub_P", current_period_end=None)
    db.forget_profile("u-basic")
    admin.set_plan("u-basic", "pro", 30)       # no 409: the subscription is halted, not live
    p = next(r for r in fake.tables["profiles"] if r["id"] == "u-basic")
    assert p["plan"] == "pro" and p["razorpay_subscription_id"] is None and p["pending_subscription_id"] is None
    ev = {"event": "subscription.cancelled", "payload": {"subscription": {"entity": {"id": "sub_H", "status": "cancelled", "notes": {"user_id": "u-basic"}}}}}
    billing._act(ev)
    p = next(r for r in fake.tables["profiles"] if r["id"] == "u-basic")
    assert p["plan"] == "pro" and p["plan_status"] == "active", "the hand-given plan was wiped"


def test_a_live_subscription_still_answers_409(w):
    p = next(r for r in w["db"].tables["profiles"] if r["id"] == "u-basic")
    p.update(plan="basic", plan_status="active", razorpay_subscription_id="sub_L")
    db.forget_profile("u-basic")
    with pytest.raises(Exception) as e:
        admin.set_plan("u-basic", "pro", 30)
    assert getattr(e.value, "status_code", None) == 409
    assert p["razorpay_subscription_id"] == "sub_L"


# ---------- 2. sessions run on the leader only ----------
def running_row(uid=ME, **kw) -> dict:
    return db.create_session({"user_id": uid, "name": "paper", "status": "running",
                              "instrument": {"symbol": "TCS", "market": "IN"}, "strategy": {"risk": {"capital": 100000}}, **kw})


def test_a_follower_stops_and_lists_a_session_from_the_database(w):
    from app import main
    main.manager.sessions.clear()               # this process isn't the one running sessions
    c = w["client"]
    row = running_row()
    listed = c.get("/admin/sessions", headers=ADMIN).json()
    assert [r["id"] for r in listed] == [row["id"]] and listed[0]["email"] == "pro@example.com" and listed[0]["capital"] == 100000
    r = c.post(f"/admin/sessions/{row['id']}/stop", headers=ADMIN)
    assert r.status_code == 200 and r.json() == {"ok": True}
    after = db.get_session_row(ME, row["id"])
    assert after["status"] == "stopped" and after["stop_reason"] == "Stopped by the site owner." and after["stopped_at"]
    assert c.post(f"/admin/sessions/{row['id']}/stop", headers=ADMIN).status_code == 404       # no longer running
    assert c.post("/admin/sessions/not-an-id/stop", headers=ADMIN).status_code == 404


def test_erase_marks_running_sessions_stopped_before_deleting_their_rows(w, monkeypatch):
    from app import main
    main.manager.sessions.clear()
    row = running_row()
    other = running_row("u-basic")
    seen = []
    real = fake_db.Query.execute

    def watch(self):
        if self.table == "live_sessions" and self.op == "delete":
            seen.append([(r["status"], r.get("stop_reason")) for r in self.db.tables["live_sessions"] if r["id"] == row["id"]])
        return real(self)
    monkeypatch.setattr(fake_db.Query, "execute", watch)
    got = user_data.erase(ME)
    assert got["failed"] == [] and {d["key"]: d["count"] for d in got["done"]}["live"] == 1
    assert seen == [[("stopped", "The account's data was deleted.")]]      # the leader follows the row, so it is stopped first
    assert db.get_session_row("u-basic", other["id"])["status"] == "running"


# ---------- 3. erase drops the 30 s Free Basic copy ----------
def test_erase_forgets_the_free_basic_copy(w):
    until = NOW + timedelta(days=20)
    db.set_setting(plans.FREE_KEY + ME, json.dumps({"until": until.isoformat(), "banked": 0}))
    plans.forget_free_basic()
    profile = {"id": ME, "plan": "free"}
    assert plans.free_basic_until(profile, NOW) is not None            # read, and kept for 30 s
    got = user_data.erase(ME)
    assert got["failed"] == []
    assert plans.free_basic_until(profile, NOW) is None and plans.free_basic(ME)["until"] is None
    assert db.get_setting(plans.FREE_KEY + ME) is None                 # and nothing saved it back


# ---------- 4. invoice numbering ----------
PAY = {"id": "pay_1", "amount": 99900, "currency": "INR", "created_at": 1791000000, "international": False, "status": "captured"}
SELLER = {"legal_name": "StratLab Studio", "address": "Pune", "state": "27", "gstin": "27ABCDE1234F1Z5", "pan": "ABCDE1234F",
          "lut_arn": "", "email": "billing@stratlab.studio", "prefix": "SL"}
U1 = {"id": "u1", "email": "a@b.c"}


def test_a_lost_claim_takes_no_number_and_saves_no_record(shared_db, monkeypatch):
    invoices.save_seller(SELLER)
    first = invoices.make(PAY, U1, "pro", "month")
    assert first["number"] == "SL/2026-27/0001"
    # another server claimed this payment between this call's first look and its claim: it is simulated by hiding the claim
    # from the first read only
    real = invoices._read
    seen = []

    def blind(key, default=None):
        if key == "invoice-of:pay_1" and not seen:
            seen.append(1)
            return None
        return real(key, default)
    monkeypatch.setattr(invoices, "_read", blind)
    again = invoices.make(PAY, U1, "pro", "month")
    assert again["number"] == first["number"]
    assert json.loads(db.get_setting("invoice:counter:2026-27")) == 1          # no second number taken
    assert setting_keys("invoice:SL/") == ["invoice:SL/2026-27/0001"]          # and no orphan record


def test_a_database_error_reading_the_buyer_issues_nothing(shared_db, monkeypatch):
    invoices.save_seller(SELLER)
    invoices.save_billing("u1", {"name": "Acme", "state": "27", "gstin": "27ABCDE1234F1Z5", "country": "IN"})
    real = db.get_setting
    down = [True]

    def get_setting(key):
        if key == "billing:u1" and down[0]:
            raise ConnectionError("blip")
        return real(key)
    monkeypatch.setattr(db, "get_setting", get_setting)
    with pytest.raises(ConnectionError):
        invoices.make(PAY, U1, "pro", "month")
    assert setting_keys("invoice") == ["invoice:seller"]       # no number, no claim, no record: the next try starts clean
    down[0] = False
    inv = invoices.make(PAY, U1, "pro", "month")
    assert inv["number"] == "SL/2026-27/0001" and inv["buyer"]["gstin"] == "27ABCDE1234F1Z5"


def test_a_database_error_reading_the_seller_issues_nothing(shared_db, monkeypatch):
    invoices.save_seller(SELLER)
    real = db.get_setting
    monkeypatch.setattr(db, "get_setting", lambda k: (_ for _ in ()).throw(ConnectionError("blip")) if k == invoices.SELLER else real(k))
    with pytest.raises(ConnectionError):
        invoices.make(PAY, U1, "pro", "month")
    monkeypatch.setattr(db, "get_setting", real)
    assert setting_keys("invoice") == ["invoice:seller"]


def test_a_failure_after_the_number_is_finished_by_the_next_call_under_the_same_number(shared_db, monkeypatch):
    invoices.save_seller(SELLER)
    real = db.set_setting

    def flaky(key, value):
        if key.startswith("invoice:SL/") and flaky.fail:
            flaky.fail = False
            raise ConnectionError("blip")
        return real(key, value)
    flaky.fail = True
    monkeypatch.setattr(db, "set_setting", flaky)
    with pytest.raises(ConnectionError):
        invoices.make(PAY, U1, "pro", "month")
    inv = invoices.make(PAY, U1, "pro", "month")                # the retry
    assert inv["number"] == "SL/2026-27/0001" and json.loads(db.get_setting("invoice:counter:2026-27")) == 1
    assert [i["number"] for i in invoices.of_user("u1")] == ["SL/2026-27/0001"] and len(invoices.of_year("2026-27")) == 1
    assert invoices.make({**PAY, "id": "pay_2"}, U1, "pro", "month")["number"] == "SL/2026-27/0002"


def test_a_failure_taking_the_number_lets_the_claim_go(shared_db, monkeypatch):
    invoices.save_seller(SELLER)
    real = db.update_setting

    def update(key, fn, tries=10):
        if key.startswith("invoice:counter:") and update.fail:
            update.fail = False
            raise ConnectionError("blip")
        return real(key, fn, tries)
    update.fail = True
    monkeypatch.setattr(db, "update_setting", update)
    with pytest.raises(ConnectionError):
        invoices.make(PAY, U1, "pro", "month")
    assert db.get_setting("invoice-of:pay_1") is None
    assert invoices.make(PAY, U1, "pro", "month")["number"] == "SL/2026-27/0001"


def test_a_claim_with_no_number_is_waited_for_then_taken_over(shared_db):
    invoices.save_seller(SELLER)
    db.set_setting("invoice-of:pay_1", json.dumps({"pending": "someone", "at": time.time()}))
    with pytest.raises(invoices.InvoiceBusy):
        invoices.make(PAY, U1, "pro", "month")
    with time_machine.travel(NOW + timedelta(seconds=invoices.PENDING_FOR + 5), tick=False):
        assert invoices.make(PAY, U1, "pro", "month")["number"] == "SL/2026-27/0001"


# ---------- 5, 6. erase and export past the row caps, in small pages ----------
def test_erase_finds_library_entries_past_the_newest_thousand(w):
    rows = w["db"].tables.setdefault("app_settings", [])
    rows.append({"key": library.PREFIX + "lib-mine", "value": json.dumps({"id": "lib-mine", "owner": ME}), "updated_at": "2020-01-01T00:00:00+00:00"})
    rows.extend({"key": library.PREFIX + f"lib-o{i:04d}", "value": json.dumps({"id": f"lib-o{i:04d}", "owner": "u-other"}),
                 "updated_at": f"2026-09-01T00:00:{i % 60:02d}+00:00"} for i in range(1005))
    assert not any(e.get("id") == "lib-mine" for e in library.all_entries())       # the newest 1000 don't reach it
    assert user_data.erase(ME)["failed"] == []
    assert library.load("lib-mine") is None and library.load("lib-o0000") is not None


def test_erase_and_export_read_in_small_pages_and_delete_without_rows_back(w, monkeypatch):
    uid = ME
    w["db"].tables.setdefault("strategies", []).extend({"id": f"s{i:05d}", "user_id": uid, "name": "n", "body": {}} for i in range(120))
    base = user_data.export(db.get_profile(uid))["usage"]                    # what the fake world already holds
    w["db"].tables.setdefault("usage_events", []).extend({"id": 1000 + i, "user_id": uid, "kind": "backtest" if i % 3 else "ai"} for i in range(130))
    w["db"].tables.setdefault("live_sessions", []).extend({"id": f"l{i:05d}", "user_id": uid, "name": "n", "status": "stopped"} for i in range(60))
    limits, deletes = [], []
    real = fake_db.Query.execute

    def watch(self):
        if self.op == "select" and self.table in ("strategies", "usage_events", "live_sessions", "live_orders"):
            limits.append((self.table, self._limit))
        if self.op == "delete" and self.table in ("strategies", "live_sessions", "live_orders"):
            deletes.append((self.table, self.returning))
        return real(self)
    monkeypatch.setattr(fake_db.Query, "execute", watch)
    out = user_data.export(db.get_profile(uid))
    assert out["not_included"] == [] and len(out["notebooks"]) == 120 and out["usage"] == {**base, "backtest": base.get("backtest", 0) + 86, "ai": base.get("ai", 0) + 44}
    assert len(out["sessions"]["sessions"]) == 60
    assert limits and all(n == user_data.PAGE for _, n in limits), limits
    limits.clear()
    got = user_data.erase(uid)
    counts = {d["key"]: d["count"] for d in got["done"]}
    assert got["failed"] == [] and counts["notebooks"] == 120 and counts["live"] == 60
    assert limits and all(n == user_data.PAGE for _, n in limits), limits
    assert sorted(set(deletes)) == [("live_orders", "minimal"), ("live_sessions", "minimal"), ("strategies", "minimal")]


# ---------- 7. the export holds billing, invoices and cards ----------
def test_export_has_billing_invoices_and_cards_and_no_secrets(w):
    invoices.save_seller(SELLER)
    invoices.save_billing(ME, {"name": "Acme Traders", "address": "12 MG Road, Pune", "state": "27", "gstin": "27ABCDE1234F1Z5", "country": "IN"})
    inv = invoices.make(PAY, {"id": ME, "email": "pro@example.com"}, "pro", "month")
    db.set_setting(f"cards:user:{ME}", json.dumps([{"t": "cardTokabc", "k": f"cardtok:{ME}:IN:TCS"}]))
    out = user_data.export(db.get_profile(ME))
    assert out["not_included"] == []
    assert out["billing"]["billing"] == {"name": "Acme Traders", "address": "12 MG Road, Pune", "state": "27", "gstin": "27ABCDE1234F1Z5", "country": "IN"}
    assert [i["number"] for i in out["invoices"]] == [inv["number"]] and out["invoices"][0]["buyer"]["address"] == "12 MG Road, Pune"
    assert out["company_cards"]["cards:user"][0]["t"] == "cardTokabc"
    # the erase keeps billing and invoices: payment records
    assert user_data.erase(ME)["failed"] == []
    assert db.get_setting(f"billing:{ME}") and invoices.of_user(ME)


def test_clean_drops_secret_names_and_names_holding_one_but_keeps_the_instrument_number():
    got = user_data._clean({"instrument_token": 408065, "token": "t", "access_token": "a", "inbox_password": "x", "api_key": "y",
                            "keys": {"p": 1}, "address": "inbox@x", "author": "z", "password": "p", "tokenizer": 1})
    assert got == {"instrument_token": 408065, "author": "z"}          # "tokenizer" holds "token": left out, safely
    assert user_data._clean({"address": "12 MG Road", "key": "k"}, {"address"}) == {"address": "12 MG Road"}


# ---------- 8. a rate-limited or failing sign-in service is not a refused token ----------
@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
def test_a_sign_in_service_that_answers_429_or_5xx_is_unavailable_not_a_refusal(w, monkeypatch, status):
    from fastapi import HTTPException
    from supabase_auth.errors import AuthApiError
    auth._cache.clear()
    auth._rejected.clear()

    def busy(token):
        raise AuthApiError("slow down", status, None)
    real = db.sb().auth.get_user
    monkeypatch.setattr(db.sb().auth, "get_user", busy)
    with pytest.raises(HTTPException) as e:
        auth.current_profile(authorization="Bearer pro-token")
    assert e.value.status_code == 503 and e.value.detail["code"] == "auth_unavailable"
    assert "pro-token" not in auth._rejected                       # not remembered as refused
    monkeypatch.setattr(db.sb().auth, "get_user", real)
    assert auth.current_profile(authorization="Bearer pro-token")["id"] == "u-pro"


def test_a_refused_token_is_still_a_401(w):
    from fastapi import HTTPException
    auth._cache.clear()
    auth._rejected.clear()
    with pytest.raises(HTTPException) as e:
        auth.current_profile(authorization="Bearer made-up")
    assert e.value.status_code == 401 and "made-up" in auth._rejected


def test_the_export_drops_any_name_with_a_secret_word_in_it_but_keeps_the_instrument_number():
    from app import user_data
    got = user_data._clean({"bot_token": "x", "kite_api_key": "k", "client_secret": "s", "private_key": "p",
                            "feed_token": "f", "instrument_token": 408065, "name": "TCS"})
    assert got == {"instrument_token": 408065, "name": "TCS"}


# ---------- acct4: a number given out and then lost is logged, not hidden ----------
def test_a_number_lost_to_a_takeover_is_logged_as_skipped(shared_db, monkeypatch, capsys):
    invoices.save_seller(SELLER)
    real = db.update_setting

    def slow(key, fn, tries=10):
        out = real(key, fn, tries)
        if key.startswith("invoice:counter:"):         # this call was slow: another took the claim over meanwhile
            db.set_setting("invoice-of:pay_1", json.dumps({"pending": "another", "at": time.time()}))
        return out
    monkeypatch.setattr(db, "update_setting", slow)
    with pytest.raises(invoices.InvoiceBusy):
        invoices.make(PAY, U1, "pro", "month")
    assert "invoice number skipped: SL/2026-27/0001 (payment pay_1)" in capsys.readouterr().out
    assert "Gaps are still possible" in invoices.make.__doc__


def test_a_follower_lists_options_and_group_sessions_by_their_kind(w):
    """acct4: the kind comes from the row's type, as the leader's session classes have it."""
    from app import main
    main.manager.sessions.clear()
    rules = running_row()
    opts = running_row(instrument={"type": "OPTIONS", "symbol": "NIFTY", "market": "IN"})
    group = running_row(instrument={"type": "GROUP", "symbol": "Banks", "market": "IN"})
    signal = running_row(strategy={"kind": "signal", "risk": {"capital": 1}})
    kinds = {r["id"]: r["kind"] for r in w["client"].get("/admin/sessions", headers=ADMIN).json()}
    assert kinds == {rules["id"]: "rules", opts["id"]: "options", group["id"]: "group", signal["id"]: "signal"}
