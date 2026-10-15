"""Connect once: the encrypted vault, log redaction, reading synthetic CAMS / NSDL / CDSL statements, the statement inbox
webhook (secret and signature, unknown recipients, wrong passwords, limits), the uploads, Zerodha login and Interactive Brokers
(both against fakes), the EPF / NPS / AIS uploads, the 40-day reminder, deleting a connection, and that no user sees another's.
Every statement here is made up; no real file is used."""
import base64
import hashlib
import hmac
import io
import json
import logging
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from cryptography.fernet import Fernet
from reportlab.pdfgen import canvas

from app import db, holdings, journal, money_mf, money_networth, plans, money_advance_tax as adv, money_dividends as divs
from app.config import settings
from app.connect import docs, ibkr, inbound, jobs, kite_user, redact, state, statements, sync, vault
from tests import world
from tests.casmaker import make_cas
from tests.cdslmaker import make_cdsl
from tests.nsdlmaker import make_nsdl

PAN = "ABCDE1234F"
PRO, BASIC, FREE, ADMIN = (world.headers(t) for t in ("pro-token", "basic-token", "free-token", "admin-token"))
PRO_ID, BASIC_ID = "u-pro", "u-basic"
SECRET = "hook-secret-0123456789"
DOMAIN = "in.example.test"
DEMAT_PASSWORD = "S3cretPassw0rd!"


@pytest.fixture
def w(monkeypatch):
    built = world.build(monkeypatch)
    inbound.forget_limits()
    yield built
    built["close"]()


@pytest.fixture
def on(monkeypatch):
    """Everything configured: the encryption key, the inbox domain and webhook secret."""
    monkeypatch.setattr(settings, "CONNECT_SECRET_KEY", Fernet.generate_key().decode())
    monkeypatch.setattr(settings, "INBOUND_DOMAIN", DOMAIN)
    monkeypatch.setattr(settings, "INBOUND_WEBHOOK_SECRET", SECRET)
    monkeypatch.setattr(settings, "INBOUND_PROVIDER", "brevo")
    monkeypatch.setattr(settings, "BREVO_API_KEY", "brevo-api-key-123456")


def cams(password=PAN, **kw) -> bytes:
    scheme = {"code": "X12G", "name": "Example Flexi Cap Fund - Direct Plan - Growth", "isin": "INF000X01AB1",
              "rows": [("10-Jan-2018", "Purchase - via Internet", "10,000.00", "1,000.000", "10.0000", "1,000.000"),
                       ("05-Feb-2019", "Systematic Investment Purchase Instalment No 1", "5,000.00", "400.000", "12.5000", "1,400.000")],
              "close": "1,400.000", "nav": "25.0000", "nav_date": "30-Sep-2026", "cost": "15,000.00", "value": "35,000.00"}
    return make_cas(password, [{"amc": "Example Mutual Fund", "folio": "1234567 / 89", "schemes": [scheme]}], **kw)


def nsdl(password=PAN, shares=10) -> bytes:
    return make_nsdl(password, [{"broker": "EXAMPLE BROKING LTD", "dp_id": "IN300001", "client_id": "12345678",
                                 "equities": [("INE009A01021", "INFY", "Infosys Limited", shares, 1500.5),
                                              ("INE154A01025", "ITC", "ITC Limited", 25.5, 400.0)]}])


def cdsl(password=PAN) -> bytes:
    return make_cdsl(password, [{"broker": "EXAMPLE BROKING LTD", "dp_id": "12345678", "client_id": "87654321",
                                 "equities": [("INE467B01029", "Tata Consultancy Services Limited", 40, 3500.25)]}])


def b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode()


def state_text(uid: str) -> str:
    """Everything stored for a user's connections, as the database holds it."""
    return json.dumps(db.get_setting(state.KEY + uid) or "")


# ---------- the vault ----------
def test_vault_seals_and_opens(on):
    sealed = vault.seal("my-password")
    assert "my-password" not in sealed and sealed != vault.seal("my-password")      # a fresh nonce each time
    assert vault.unseal(sealed) == "my-password"
    assert vault.unseal("") is None and vault.unseal("not a token") is None


def test_vault_needs_a_key_and_a_changed_key_cannot_open(on, monkeypatch):
    sealed = vault.seal("x")
    monkeypatch.setattr(settings, "CONNECT_SECRET_KEY", Fernet.generate_key().decode())
    assert vault.unseal(sealed) is None
    monkeypatch.setattr(settings, "CONNECT_SECRET_KEY", "")
    assert not vault.ready() and vault.unseal(sealed) is None
    with pytest.raises(vault.VaultError):
        vault.seal("x")
    monkeypatch.setattr(settings, "CONNECT_SECRET_KEY", "not-a-key")
    assert not vault.ready()


def test_vault_rotation_opens_old_secrets(monkeypatch):
    old, new = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    monkeypatch.setattr(settings, "CONNECT_SECRET_KEY", old)
    sealed = vault.seal("keep")
    monkeypatch.setattr(settings, "CONNECT_SECRET_KEY", f"{new},{old}")
    assert vault.unseal(sealed) == "keep"
    assert vault.unseal(vault.seal("fresh")) == "fresh"


# ---------- log redaction ----------
@pytest.mark.parametrize("raw,gone", [
    ("GET /SendRequest?t=1234567890123456789&q=42&v=3", "1234567890123456789"),
    ("GET https://x/inbound/email/brevo?k=hook-secret-0123456789 200", "hook-secret-0123456789"),
    ("headers {'Authorization': 'Bearer abcdefghijklmnop'}", "abcdefghijklmnop"),
    ("password=S3cretPassw0rd! failed", "S3cretPassw0rd!"),
    ("PAN ABCDE1234F opened it", "ABCDE1234F"),
    ("token: gAAAAABmZ2xvYmFsX3NlY3JldF92YWx1ZV9oZXJlX2xvbmc=", "gAAAAABmZ2xvYmFsX3NlY3JldF92YWx1ZV9oZXJlX2xvbmc"),
    ("api-key: brevo-api-key-123456", "brevo-api-key-123456"),
])
def test_mask_hides_secrets(raw, gone):
    assert gone not in redact.mask(raw)


def test_log_filter_masks_what_a_handler_prints():
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.addFilter(redact.SecretFilter())
    lg = logging.getLogger("connect-test")
    lg.addHandler(handler)
    lg.setLevel(logging.INFO)
    lg.info("calling %s", "https://h/GetStatement?t=SECRETTOKEN123&q=1")
    try:
        raise RuntimeError("password=hunter2hunter2")
    except RuntimeError:
        lg.exception("failed")
    out = stream.getvalue()
    lg.removeHandler(handler)
    assert "SECRETTOKEN123" not in out and "hunter2hunter2" not in out and "?t=***" in out


# ---------- reading statements ----------
def test_reads_a_cams_statement(on):
    got = statements.read(cams(), [PAN])
    assert got.kind == "mf" and got.asof == "2026-09-30"
    assert [s["name"] for s in got.mf["schemes"]] == ["Example Flexi Cap Fund - Direct Plan - Growth"] and len(got.mf["txns"]) >= 2
    assert "INVESTOR" not in json.dumps(got.mf) and PAN not in json.dumps(got.mf)       # the person isn't copied


def test_reads_nsdl_and_cdsl_statements():
    n = statements.read(nsdl(), [PAN])
    assert n.kind == "demat" and n.asof == "2026-09-30"
    assert {(r["isin"], r["qty"]) for r in n.rows} == {("INE009A01021", 10.0), ("INE154A01025", 25.5)}
    assert PAN not in json.dumps(n.rows)
    c = statements.read(cdsl(), [PAN])
    assert c.kind == "demat" and [(r["isin"], r["qty"]) for r in c.rows] == [("INE467B01029", 40.0)]


def test_password_is_tried_in_capitals_too():
    assert statements.read(nsdl(), [PAN.lower()]).kind == "demat"


@pytest.mark.parametrize("make,pws,code", [
    (nsdl, ["WRONGPASS1"], "wrong_password"), (nsdl, [], "no_password"), (cams, ["nope"], "wrong_password"),
])
def test_statement_failures_have_a_code(make, pws, code):
    with pytest.raises(statements.StatementError) as e:
        statements.read(make(), pws)
    assert e.value.code == code


def test_not_a_statement():
    from tests.pdfmaker import make_pdf
    with pytest.raises(statements.StatementError) as e:
        statements.read(make_pdf(["Hello, this is not a statement."]), [PAN])
    assert e.value.code == "not_a_statement"
    with pytest.raises(statements.StatementError) as e:
        statements.read(b"MZ not a pdf", [PAN])
    assert e.value.code == "not_a_statement"
    with pytest.raises(statements.StatementError) as e:
        statements.read(b"%PDF-" + b"0" * (statements.MAX_PDF + 1), [PAN])
    assert e.value.code == "too_big"


# ---------- the upload (the inbox's fallback) ----------
def upload(c, raw, password=PAN, headers=PRO, **kw):
    return c.post("/connect/statement", headers=headers, json={"filename": "cas.pdf", "data": b64(raw), "password": password, **kw})


def test_upload_a_mutual_fund_statement(w, on):
    r = upload(w["client"], cams())
    assert r.status_code == 200, r.text
    assert r.json()["kind"] == "mf" and r.json()["added"] >= 2
    assert len(money_mf.load(PRO_ID)["schemes"]) == 1
    again = upload(w["client"], cams()).json()
    assert again["added"] == 0 and again["duplicates"] >= 2                      # the same statement adds nothing
    assert PAN not in state_text(PRO_ID)                                         # a password typed for one upload isn't kept


def test_upload_a_demat_statement_sets_holdings(w, on):
    r = upload(w["client"], nsdl())
    assert r.status_code == 200, r.text
    items = {i["symbol"]: i for i in holdings.load(PRO_ID)["items"]}
    assert items["INFY"]["qty"] == 10 and items["INFY"]["via"] == "cas" and items["ITC"]["qty"] == 25.5
    upload(w["client"], nsdl(shares=12))                                          # a newer statement sets, never adds
    assert {i["symbol"]: i["qty"] for i in holdings.load(PRO_ID)["items"]}["INFY"] == 12
    assert holdings.load(PRO_ID)["source"] == "Statement"


def test_an_older_statement_leaves_holdings_alone(w, on):
    upload(w["client"], nsdl(shares=12))
    old = make_nsdl(PAN, [{"broker": "EXAMPLE BROKING LTD", "dp_id": "IN300001", "client_id": "12345678",
                           "equities": [("INE009A01021", "INFY", "Infosys Limited", 5, 1400.0)]}], period=("01-Jun-2026", "30-Jun-2026"))
    r = upload(w["client"], old)
    assert r.status_code == 200 and "older" in r.json()["detail"]
    assert {i["symbol"]: i["qty"] for i in holdings.load(PRO_ID)["items"]}["INFY"] == 12


def test_a_future_dated_statement_is_ignored_and_blocks_nothing(w, on):
    def dated(shares, end):
        return make_nsdl(PAN, [{"broker": "EXAMPLE BROKING LTD", "dp_id": "IN300001", "client_id": "12345678",
                                "equities": [("INE009A01021", "INFY", "Infosys Limited", shares, 1500.5)]}], period=("01-Sep-2026", end))
    upload(w["client"], nsdl(shares=12))
    r = upload(w["client"], dated(99, "31-Dec-2099"))
    assert r.status_code == 400 and state.section(PRO_ID, "inbox")["last"]["status"] == "future_dated"
    assert {i["symbol"]: i["qty"] for i in holdings.load(PRO_ID)["items"]}["INFY"] == 12
    assert set(state.section(PRO_ID, "inbox")["cas_asof_by"].values()) == {"2026-09-30"}   # the far date was not recorded
    assert upload(w["client"], dated(15, "10-Oct-2026")).status_code == 200      # a real later statement still applies
    assert {i["symbol"]: i["qty"] for i in holdings.load(PRO_ID)["items"]}["INFY"] == 15
    assert set(state.section(PRO_ID, "inbox")["cas_asof_by"].values()) == {"2026-10-10"}


def test_upload_wrong_password_and_garbage(w, on):
    r = upload(w["client"], nsdl(), password="WRONGPASS1")
    assert r.status_code == 400 and r.json()["detail"]["code"] == "wrong_password"
    assert state.section(PRO_ID, "inbox")["last"]["status"] == "wrong_password"
    assert holdings.load(PRO_ID)["items"] == []
    r = w["client"].post("/connect/statement", headers=PRO, json={"filename": "x.pdf", "data": "%%%", "password": ""})
    assert r.status_code == 400
    assert upload(w["client"], b"%PDF-1.4 junk", password=PAN).json()["detail"]["code"] == "bad_file"


def test_upload_uses_the_stored_password(w, on):
    assert w["client"].put("/connect/inbox/password", headers=PRO, json={"password": PAN}).status_code == 200
    r = w["client"].post("/connect/statement", headers=PRO, json={"filename": "cas.pdf", "data": b64(nsdl()), "password": ""})
    assert r.status_code == 200 and r.json()["kind"] == "demat"


def test_etf_in_a_demat_account_becomes_a_holding(monkeypatch):
    from casparser.types import DematAccount, MutualFund, NSDLCASData
    cas = NSDLCASData.model_construct(
        accounts=[DematAccount.model_construct(name="B", type="NSDL Demat Account", dp_id="", client_id="", folios=1, balance=0, owners=[],
                                               equities=[], bonds=[], mutual_funds=[
            MutualFund.model_construct(name="Example Nifty 50 ETF", isin="INF000X01AA3", balance=100, nav=250, value=25000),
            MutualFund.model_construct(name="Example Debt Fund", isin="INF000X01AB1", balance=50, nav=10, value=500)])],
        statement_period=type("P", (), {"to": "30-Sep-2026"})(), nps=None)
    monkeypatch.setattr(statements, "open_statement", lambda data, pws: cas)
    got = statements.read(b"%PDF-", [PAN])
    assert [(r["isin"], r["qty"]) for r in got.rows] == [("INF000X01AA3", 100.0)] and got.other == 1


def test_nps_balance_on_a_depository_statement_goes_to_net_worth(w, on, monkeypatch):
    from casparser.types import NPSAccount, NPSScheme, NSDLCASData
    sch = lambda tier, v: NPSScheme.model_construct(scheme="S", tier=tier, units=1, nav=1, value=v)
    cas = NSDLCASData.model_construct(accounts=[], statement_period=type("P", (), {"to": "30-Sep-2026"})(),
                                      nps=NPSAccount.model_construct(value=300000, schemes=[sch("I", 250000), sch("II", 50000)]))
    monkeypatch.setattr(statements, "open_statement", lambda data, pws: cas)
    r = upload(w["client"], b"%PDF-1.4 fake")
    assert r.status_code == 200, r.text
    nps = [i for i in money_networth.load(PRO_ID)["items"] if i["kind"] == "nps"]
    assert len(nps) == 1 and nps[0]["tier1"] == 250000 and nps[0]["tier2"] == 50000 and nps[0]["auto"] == "statement"
    upload(w["client"], b"%PDF-1.4 fake")                                         # again: updated, not doubled
    assert len([i for i in money_networth.load(PRO_ID)["items"] if i["kind"] == "nps"]) == 1


def test_a_typed_nps_entry_is_not_overwritten(w, on, monkeypatch):
    money_networth.save(PRO_ID, [{"id": "aa", "kind": "nps", "name": "NPS", "tier1": 1.0, "as_of": "2026-01-01"}])
    note = statements.save_nps(PRO_ID, {"tier1": 5.0, "tier2": 0.0}, "2026-09-30", "pro")
    assert "already have" in note and money_networth.load(PRO_ID)["items"][0]["tier1"] == 1.0


# ---------- holdings from several sources ----------
def test_a_live_broker_wins_over_a_statement_and_sold_stocks_leave(w, on):
    c = w["client"]
    upload(c, nsdl())                                                             # INFY 10, ITC 25.5 from a statement
    rows = [{"symbol": "INFY", "isin": "INE009A01021", "name": "INFY", "qty": 99.0, "avg": 1400.0}]
    profile = sync.profile_for(PRO_ID)
    sync.sync_holdings(profile, rows, "kite", "Zerodha Kite")
    items = {i["symbol"]: i for i in holdings.load(PRO_ID)["items"]}
    assert items["INFY"]["qty"] == 99 and items["INFY"]["via"] == "kite" and items["INFY"]["avg"] == 1400.0
    upload(c, nsdl(shares=3))                                                     # the statement can't override the broker
    assert {i["symbol"]: i for i in holdings.load(PRO_ID)["items"]}["INFY"]["qty"] == 99
    got = sync.sync_holdings(profile, [], "kite", "Zerodha Kite")                 # an empty reply is a failed read, not "sold everything"
    assert got["empty"] and "failed read" in sync.note(got, "Zerodha")
    assert {i["symbol"]: i for i in holdings.load(PRO_ID)["items"]}["INFY"]["qty"] == 99
    sync.sync_holdings(profile, [{"symbol": "ITC", "isin": "INE154A01025", "name": "ITC", "qty": 1.0, "avg": None}], "kite", "Zerodha Kite")
    assert "INFY" not in {i["symbol"] for i in holdings.load(PRO_ID)["items"]}  # a whole read without it: sold


def test_a_read_with_an_unmatched_line_keeps_what_the_source_gave_before(w, on, monkeypatch):
    profile = sync.profile_for(PRO_ID)
    infy = {"symbol": "INFY", "isin": "INE009A01021", "name": "INFY", "qty": 10.0, "avg": 1400.0}
    itc = {"symbol": "ITC", "isin": "INE154A01025", "name": "ITC", "qty": 5.0, "avg": 380.0}
    sync.sync_holdings(profile, [infy, itc], "kite", "Zerodha Kite")
    real = holdings.Matcher.match                    # ITC's line comes back but can't be matched this time
    monkeypatch.setattr(holdings.Matcher, "match", lambda self, r: (None, "offline") if r.get("symbol") == "ITC" else real(self, r))
    got = sync.sync_holdings(profile, [{**infy, "qty": 12.0}, {**itc, "qty": 7.0}], "kite", "Zerodha Kite")
    items = {i["symbol"]: i for i in holdings.load(PRO_ID)["items"]}
    assert items["INFY"]["qty"] == 12 and items["ITC"]["qty"] == 5 and items["ITC"]["avg"] == 380.0   # kept as it was
    assert got["unmatched_count"] == 1 and got["kept"] == 1 and "ITC" in sync.note(got, "Zerodha")


def test_a_sync_over_the_limit_after_a_downgrade_deletes_nothing(w, on, monkeypatch):
    profile = sync.profile_for(PRO_ID)
    infy = {"symbol": "INFY", "isin": "INE009A01021", "name": "INFY", "qty": 10.0, "avg": 1400.0}
    itc = {"symbol": "ITC", "isin": "INE154A01025", "name": "ITC", "qty": 5.0, "avg": 380.0}
    sync.sync_holdings(profile, [infy, itc], "kite", "Zerodha Kite")
    monkeypatch.setitem(plans.PLANS[profile["_plan"]], "holdings", 1)
    rel = {"symbol": "RELIANCE", "isin": "INE002A01018", "name": "RELIANCE", "qty": 3.0, "avg": None}
    got = sync.sync_holdings(profile, [{**infy, "qty": 12.0}, {**itc, "qty": 7.0}, rel], "kite", "Zerodha Kite")
    items = {i["symbol"]: i for i in holdings.load(PRO_ID)["items"]}
    assert set(items) == {"INFY", "ITC"} and items["INFY"]["qty"] == 12 and items["ITC"]["qty"] == 7
    assert got["over_limit"] == ["RELIANCE"]


def test_a_line_that_never_matches_doesnt_stop_a_sold_stock_leaving(w, on):
    profile = sync.profile_for(PRO_ID)
    infy = {"symbol": "INFY", "isin": "INE009A01021", "name": "INFY", "qty": 10.0, "avg": 1400.0}
    itc = {"symbol": "ITC", "isin": "INE154A01025", "name": "ITC", "qty": 5.0, "avg": 380.0}
    odd = {"symbol": "QQZZNOPE", "isin": None, "name": "QQZZNOPE", "qty": 2.0, "avg": None}     # never matches anything
    sync.sync_holdings(profile, [infy, itc, odd], "kite", "Zerodha Kite")
    got = sync.sync_holdings(profile, [infy, odd], "kite", "Zerodha Kite")                # ITC was sold
    assert {i["symbol"] for i in holdings.load(PRO_ID)["items"]} == {"INFY"}
    assert got["unmatched_count"] == 1 and got["kept"] == 0 and "QQZZNOPE" in sync.note(got, "Zerodha")


def test_an_nps_balance_from_two_kinds_of_statement_is_one_entry(w, on):
    assert statements.save_nps(PRO_ID, {"tier1": 100.0, "tier2": 0.0}, "2026-09-30", "pro") == ""                   # from the CAS
    assert statements.save_nps(PRO_ID, {"tier1": 120.0, "tier2": 0.0}, "2026-10-05", "pro", how="nps_statement") == ""
    nps = [i for i in money_networth.load(PRO_ID)["items"] if i["kind"] == "nps"]
    assert len(nps) == 1 and nps[0]["tier1"] == 120
    note = statements.save_nps(PRO_ID, {"tier1": 90.0, "tier2": 0.0}, "2026-08-31", "pro")                      # an older one
    assert "newer" in note and [i["tier1"] for i in money_networth.load(PRO_ID)["items"] if i["kind"] == "nps"] == [120]


def test_an_older_statement_leaves_the_nps_balance_alone(w, on, monkeypatch):
    from casparser.types import NPSAccount, NPSScheme, NSDLCASData
    sch = NPSScheme.model_construct(scheme="S", tier="I", units=1, nav=1, value=5000)
    old = NSDLCASData.model_construct(accounts=[], statement_period=type("P", (), {"to": "30-Jun-2026"})(),
                                      nps=NPSAccount.model_construct(value=5000, schemes=[sch]))
    upload(w["client"], nsdl())                                                   # as of 30 Sep 2026
    statements.save_nps(PRO_ID, {"tier1": 9000.0, "tier2": 0.0}, None, "pro")
    monkeypatch.setattr(statements, "open_statement", lambda data, pws: old)
    upload(w["client"], b"%PDF-1.4 fake")
    assert [i["tier1"] for i in money_networth.load(PRO_ID)["items"] if i["kind"] == "nps"] == [9000]


def test_a_statement_dates_its_holdings_by_its_own_last_day(w, on):
    upload(w["client"], nsdl())                                                   # the period ends 30 Sep 2026
    items = {i["symbol"]: i for i in holdings.load(PRO_ID)["items"]}
    assert items["INFY"]["since"] == "2026-09-30"                                 # a split after that day is still offered


def test_a_sync_keeps_the_average_price_the_user_has(w, on):
    profile = sync.profile_for(PRO_ID)
    sync.sync_holdings(profile, [{"symbol": "ITC", "isin": "INE154A01025", "name": "ITC", "qty": 5.0, "avg": 380.0}], "kite", "Zerodha Kite")
    sync.sync_holdings(profile, [{"symbol": "ITC", "isin": "INE154A01025", "name": "ITC", "qty": 5.0, "avg": None}], "kite", "Zerodha Kite")
    assert holdings.load(PRO_ID)["items"][0]["avg"] == 380.0                     # the same quantity: the same average
    sync.sync_holdings(profile, [{"symbol": "ITC", "isin": "INE154A01025", "name": "ITC", "qty": 8.0, "avg": None}], "kite", "Zerodha Kite")
    it = holdings.load(PRO_ID)["items"][0]
    assert it["qty"] == 8 and it["avg"] is None                                  # 3 more at an unknown price: no known average


# ---------- two demat accounts ----------
def cdsl_infy(shares=4, period=("01-Sep-2026", "30-Sep-2026")) -> bytes:
    """A second demat account (CDSL) that also holds Infosys."""
    return make_cdsl(PAN, [{"broker": "OTHER BROKING LTD", "dp_id": "12345678", "client_id": "87654321",
                            "equities": [("INE009A01021", "Infosys Limited", shares, 1500.0),
                                         ("INE467B01029", "Tata Consultancy Services Limited", 40, 3500.25)]}], period=period)


def nsdl_itc_only(period=("01-Oct-2026", "10-Oct-2026")) -> bytes:
    return make_nsdl(PAN, [{"broker": "EXAMPLE BROKING LTD", "dp_id": "IN300001", "client_id": "12345678",
                            "equities": [("INE154A01025", "ITC", "ITC Limited", 25.5, 400.0)]}], period=period)


def qtys() -> dict:
    return {i["symbol"]: i["qty"] for i in holdings.load(PRO_ID)["items"]}


@pytest.mark.parametrize("first,second", [(nsdl, cdsl_infy), (cdsl_infy, nsdl)])
def test_two_demat_accounts_both_stay_and_a_shared_stock_adds_up(w, on, first, second):
    assert upload(w["client"], first()).status_code == 200
    assert upload(w["client"], second()).status_code == 200
    assert qtys() == {"INFY": 14, "ITC": 25.5, "TCS": 40}
    items = {i["symbol"]: i for i in holdings.load(PRO_ID)["items"]}
    assert sorted(items["INFY"]["accts"].values()) == [4, 10] and len(items["TCS"]["accts"]) == 1
    assert not any("12345678" in a or "IN300001" in a for a in items["INFY"]["accts"])     # the account ids aren't stored
    upload(w["client"], second())                                                # the same statement again: nothing doubles
    assert qtys() == {"INFY": 14, "ITC": 25.5, "TCS": 40}


def test_a_later_statement_takes_out_only_its_own_accounts_part(w, on):
    c = w["client"]
    upload(c, nsdl())                                                            # NSDL, 30 Sep: INFY 10, ITC 25.5
    r = upload(c, cdsl_infy(period=("01-Aug-2026", "31-Aug-2026")))              # CDSL, older but its first: applied
    assert r.status_code == 200 and "older" not in r.json()["detail"]
    assert qtys() == {"INFY": 14, "ITC": 25.5, "TCS": 40}
    upload(c, nsdl_itc_only())                                                   # NSDL, 31 Oct: INFY sold there
    assert qtys() == {"INFY": 4, "ITC": 25.5, "TCS": 40}
    r = upload(c, cdsl_infy(shares=9, period=("01-Jul-2026", "31-Jul-2026")))   # older than CDSL's last: left alone
    assert "older" in r.json()["detail"] and qtys() == {"INFY": 4, "ITC": 25.5, "TCS": 40}
    upload(c, cdsl_infy(shares=0, period=("01-Oct-2026", "10-Oct-2026")))        # CDSL sold its INFY too: gone
    assert qtys() == {"ITC": 25.5, "TCS": 40}


def test_statement_holdings_saved_before_accounts_were_kept_are_replaced_as_before(w, on):
    holdings.save(PRO_ID, [{"symbol": "INFY", "exchange": "NSE", "name": "Infosys", "qty": 7.0, "avg": None, "via": "cas"},
                           {"symbol": "RELIANCE", "exchange": "NSE", "name": "Reliance", "qty": 3.0, "avg": None, "via": "cas"}], "Statement")
    state.update(PRO_ID, "inbox", cas_asof="2026-10-05")                         # the single day kept before: every account's
    r = upload(w["client"], nsdl())
    assert "older" in r.json()["detail"] and qtys() == {"INFY": 7, "RELIANCE": 3}
    state.update(PRO_ID, "inbox", cas_asof="2026-08-31")
    upload(w["client"], nsdl())
    assert qtys() == {"INFY": 10, "ITC": 25.5}                                   # replaced, as one statement did before
    upload(w["client"], cdsl_infy())
    assert qtys() == {"INFY": 14, "ITC": 25.5, "TCS": 40}


def test_a_hand_edit_clears_the_accounts_and_the_next_statement_sets_it(w, on):
    c = w["client"]
    upload(c, nsdl())
    upload(c, cdsl_infy())
    r = c.put("/holdings", headers=PRO, json={"items": [{"symbol": "INFY", "qty": 20}, {"symbol": "ITC", "qty": 25.5}, {"symbol": "TCS", "qty": 40}]})
    assert r.status_code == 200, r.text
    items = {i["symbol"]: i for i in holdings.load(PRO_ID)["items"]}
    assert items["INFY"]["qty"] == 20 and "accts" not in items["INFY"] and items["TCS"]["accts"]   # no hidden second quantity
    upload(c, cdsl_infy(shares=5, period=("01-Oct-2026", "10-Oct-2026")))        # as before: a statement sets what it reads
    assert qtys() == {"INFY": 5, "ITC": 25.5, "TCS": 40}


def test_a_statement_over_the_plan_limit_says_how_many_were_not_saved(w, on, monkeypatch):
    monkeypatch.setattr(plans, "holdings_limit", lambda plan: 1)
    r = upload(w["client"], nsdl())
    assert r.status_code == 200 and "1 not saved: your plan keeps 1 stock." in r.json()["detail"] and r.json()["not_saved"] == 1
    assert len(holdings.load(PRO_ID)["items"]) == 1


def test_a_wrong_password_to_remember_never_replaces_the_stored_one(w, on):
    c = w["client"]
    assert upload(c, nsdl(), password="WRONGPASS1", remember=True).status_code == 400
    assert not state.section(PRO_ID, "inbox").get("pw")                          # nothing stored from a wrong password
    assert upload(c, nsdl(), password=PAN, remember=True).status_code == 200
    assert upload(c, nsdl(), password="WRONGPASS1", remember=True).status_code == 200   # opened with the stored one
    assert vault.unseal(state.section(PRO_ID, "inbox")["pw"]) == PAN


# ---------- the inbox: addresses ----------
def test_nothing_is_made_until_the_user_turns_the_inbox_on(w, on):
    v = w["client"].get("/connect", headers=PRO).json()["inbox"]
    assert v["ready"] is True and v["address"] is None
    assert db.get_setting(state.KEY + PRO_ID) is None


def test_not_set_up_until_configured(w, monkeypatch):
    monkeypatch.setattr(settings, "CONNECT_SECRET_KEY", "")
    monkeypatch.setattr(settings, "INBOUND_DOMAIN", "")
    v = w["client"].get("/connect", headers=PRO).json()
    assert v["inbox"]["ready"] is False and v["inbox"]["address"] is None and v["storage_ready"] is False
    assert w["client"].put("/connect/inbox/password", headers=PRO, json={"password": PAN}).status_code == 503
    assert w["client"].post("/connect/inbox/new-address", headers=PRO).status_code == 503


def test_each_user_gets_their_own_private_address(w, on):
    a = w["client"].post("/connect/inbox", headers=PRO).json()["inbox"]
    b = w["client"].post("/connect/inbox", headers=BASIC).json()["inbox"]
    assert a["address"].endswith("@" + DOMAIN) and a["address"] != b["address"]
    assert a["address"].startswith("u-") and len(a["address"].split("@")[0]) == 22
    assert w["client"].post("/connect/inbox", headers=PRO).json()["inbox"]["address"] == a["address"]      # stable
    assert w["client"].get("/connect", headers=PRO).json()["inbox"]["address"] == a["address"]
    assert inbound.user_for([a["address"]]) == PRO_ID and inbound.user_for([b["address"]]) == BASIC_ID
    assert inbound.user_for([a["address"].upper()]) == PRO_ID                                       # case never matters


def test_a_new_address_stops_the_old_one(w, on):
    c = w["client"]
    old = address_of(c)
    new = c.post("/connect/inbox/new-address", headers=PRO).json()["inbox"]["address"]
    assert new != old and inbound.user_for([old]) is None and inbound.user_for([new]) == PRO_ID


def test_nobody_sees_anothers_connections(w, on):
    c = w["client"]
    c.put("/connect/inbox/password", headers=PRO, json={"password": PAN})
    upload(c, nsdl())
    other = c.get("/connect", headers=BASIC).json()
    assert other["inbox"]["has_password"] is False and other["inbox"]["last"] is None
    assert holdings.load(BASIC_ID)["items"] == []
    assert c.get("/connect").status_code == 401


def test_password_is_stored_sealed_and_never_returned(w, on):
    r = w["client"].put("/connect/inbox/password", headers=PRO, json={"password": DEMAT_PASSWORD})
    assert r.status_code == 200 and DEMAT_PASSWORD not in r.text and r.json()["inbox"]["has_password"] is True
    assert DEMAT_PASSWORD not in state_text(PRO_ID) and DEMAT_PASSWORD not in json.dumps(w["client"].get("/connect", headers=PRO).json())
    assert vault.unseal(state.section(PRO_ID, "inbox")["pw"]) == DEMAT_PASSWORD
    assert w["client"].delete("/connect/inbox/password", headers=PRO).json()["inbox"]["has_password"] is False
    assert "pw" not in state.section(PRO_ID, "inbox")


def test_turning_the_inbox_off_deletes_the_address_and_password(w, on):
    c = w["client"]
    addr = address_of(c)
    c.put("/connect/inbox/password", headers=PRO, json={"password": PAN})
    off = c.delete("/connect/inbox", headers=PRO).json()["inbox"]
    assert off["address"] is None and off["has_password"] is False
    assert inbound.user_for([addr]) is None and db.get_setting(state.KEY + PRO_ID) is None
    assert db.get_setting(state.INDEX + addr.split("@")[0]) is None


def test_delete_everything(w, on, monkeypatch):
    c = w["client"]
    address_of(c)
    c.put("/connect/inbox/password", headers=PRO, json={"password": PAN})
    state.update(PRO_ID, "ibkr", token=vault.seal("TOKEN12345"), query="1")
    state.update(PRO_ID, "kite", token=vault.seal("ACCESS"), day="2020-01-01")
    assert c.delete("/connect", headers=PRO).json() == {"deleted": True}
    assert db.get_setting(state.KEY + PRO_ID) is None
    assert [k for k, _ in db.all_settings_with_prefix("connect")] == []


# ---------- the webhook ----------
def brevo_body(to, attachments=(), subject="Your CAS", sender="nsdl@example.test", mid="m1", text=""):
    return {"items": [{"MessageId": mid, "From": {"Address": sender}, "To": [{"Address": a} for a in to], "Subject": subject,
                       "ExtractedMarkdownMessage": text,
                       "Attachments": [{"Name": n, "ContentType": "application/pdf", "ContentLength": 10, "DownloadToken": t}
                                       for n, t in attachments]}]}


@pytest.fixture
def brevo(monkeypatch, on):
    """Brevo's attachment download, faked: token -> PDF bytes."""
    files: dict[str, bytes] = {}
    calls = []

    def handler(req: httpx.Request):
        calls.append(req)
        tok = req.url.path.rsplit("/", 1)[-1]
        assert req.headers["api-key"] == "brevo-api-key-123456"
        return httpx.Response(200, content=files[tok]) if tok in files else httpx.Response(404)
    t = httpx.MockTransport(handler)
    monkeypatch.setitem(inbound.ADAPTERS, "brevo", lambda: inbound.BrevoAdapter(transport=t))
    files["calls"] = calls
    return files


def post(c, body, k=SECRET, provider="brevo"):
    return c.post(f"/inbound/email/{provider}" + (f"?k={k}" if k is not None else ""), json=body)


def address_of(c, headers=PRO):
    return c.post("/connect/inbox", headers=headers).json()["inbox"]["address"]


def test_a_statement_by_email_is_read_and_saved(w, brevo):
    c = w["client"]
    c.put("/connect/inbox/password", headers=PRO, json={"password": PAN})
    brevo["tok1"] = nsdl()
    r = post(c, brevo_body([address_of(c)], [("cas.pdf", "tok1")]))
    assert r.status_code == 200 and r.content == b""
    assert {i["symbol"] for i in holdings.load(PRO_ID)["items"]} == {"INFY", "ITC"}
    last = state.section(PRO_ID, "inbox")["last"]
    assert last["status"] == "ok" and last["kind"] == "demat" and last["via"] == "email"
    v = c.get("/connect", headers=PRO).json()["inbox"]["last"]
    assert v["status"] == "ok" and v["at"]
    # a mutual fund statement in the same way
    brevo["tok2"] = cams()
    post(c, brevo_body([address_of(c)], [("cams.pdf", "tok2")], mid="m2"))
    assert len(money_mf.load(PRO_ID)["schemes"]) == 1


def test_the_pdf_is_not_kept_anywhere(w, brevo, tmp_path, monkeypatch):
    import os
    c = w["client"]
    c.put("/connect/inbox/password", headers=PRO, json={"password": PAN})
    brevo["tok1"] = nsdl()
    import tempfile
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))     # its own temp folder: other processes write to /tmp too
    pdfs = lambda: {f for f in os.listdir("/tmp") if f.lower().endswith(".pdf")}
    before = pdfs()
    post(c, brevo_body([address_of(c)], [("cas.pdf", "tok1")]))
    assert os.listdir(tmp_path) == [] and pdfs() == before
    assert "%PDF" not in json.dumps([v for _, v in db.all_settings_with_prefix("")], default=str)


def test_wrong_stored_password_is_a_quiet_status_not_an_error(w, brevo, caplog, capsys):
    c = w["client"]
    c.put("/connect/inbox/password", headers=PRO, json={"password": "NOTMYPAN12"})
    brevo["tok1"] = nsdl()
    with caplog.at_level(logging.DEBUG):
        r = post(c, brevo_body([address_of(c)], [("cas.pdf", "tok1")]))
    assert r.status_code == 200
    last = state.section(PRO_ID, "inbox")["last"]
    assert last["status"] == "wrong_password" and "password" in last["detail"].lower()
    assert holdings.load(PRO_ID)["items"] == []
    out = capsys.readouterr()
    for secret in ("NOTMYPAN12", PAN):
        assert secret not in caplog.text and secret not in out.out and secret not in out.err and secret not in last["detail"]


def test_no_password_yet(w, brevo):
    c = w["client"]
    brevo["tok1"] = nsdl()
    post(c, brevo_body([address_of(c)], [("cas.pdf", "tok1")]))
    assert state.section(PRO_ID, "inbox")["last"]["status"] == "no_password"


def test_unknown_recipient_is_dropped_quietly(w, brevo):
    c = w["client"]
    mine = address_of(c)
    brevo["tok1"] = nsdl()
    for to in ("u-aaaaaaaaaaaaaaaaaaaa@" + DOMAIN, "someone@" + DOMAIN, mine.replace(DOMAIN, "other.example"), "x@y.z"):
        r = post(c, brevo_body([to], [("cas.pdf", "tok1")], mid=to))
        assert r.status_code == 200 and r.content == b""          # the same answer as for a real address
    assert brevo["calls"] == [] and state.section(PRO_ID, "inbox").get("last") is None


def test_each_mail_goes_to_the_right_user_only(w, brevo):
    c = w["client"]
    c.put("/connect/inbox/password", headers=PRO, json={"password": PAN})
    c.put("/connect/inbox/password", headers=BASIC, json={"password": PAN})
    brevo["tok1"] = nsdl()
    post(c, brevo_body([address_of(c, BASIC)], [("cas.pdf", "tok1")]))
    assert holdings.load(PRO_ID)["items"] == [] and len(holdings.load(BASIC_ID)["items"]) == 2


def test_bad_or_missing_secret_is_refused(w, brevo):
    c = w["client"]
    body = brevo_body([address_of(c)], [("cas.pdf", "tok1")])
    assert post(c, body, k="wrong").status_code == 401
    assert post(c, body, k=None).status_code == 401
    assert post(c, body, k=SECRET + "x").status_code == 401
    assert brevo["calls"] == []


def test_other_providers_and_not_set_up_answer_404(w, brevo, monkeypatch):
    c = w["client"]
    body = brevo_body([address_of(c)])
    assert post(c, body, provider="signed").status_code == 404 and post(c, body, provider="nope").status_code == 404
    monkeypatch.setattr(settings, "INBOUND_WEBHOOK_SECRET", "")
    assert post(c, body, k="").status_code == 404


def test_a_body_that_is_not_mail(w, brevo):
    c = w["client"]
    assert c.post(f"/inbound/email/brevo?k={SECRET}", content=b"not json").status_code == 400
    assert c.post(f"/inbound/email/brevo?k={SECRET}", json={"nothing": 1}).status_code == 400


def test_mail_without_a_pdf_and_junk_attachments(w, brevo):
    c = w["client"]
    post(c, brevo_body([address_of(c)], mid="a"))
    assert state.section(PRO_ID, "inbox")["last"]["status"] == "no_pdf"
    brevo["t"] = b"%PDF-1.4 junk"
    c.put("/connect/inbox/password", headers=PRO, json={"password": PAN})
    post(c, brevo_body([address_of(c)], [("x.pdf", "t")], mid="b"))
    assert state.section(PRO_ID, "inbox")["last"]["status"] == "not_a_statement"
    post(c, brevo_body([address_of(c)], [("missing.pdf", "gone")], mid="c"))
    assert state.section(PRO_ID, "inbox")["last"]["status"] == "unreadable"


def test_the_same_mail_twice_is_read_once(w, brevo):
    c = w["client"]
    c.put("/connect/inbox/password", headers=PRO, json={"password": PAN})
    brevo["tok1"] = nsdl()
    body = brevo_body([address_of(c)], [("cas.pdf", "tok1")], mid="same")
    post(c, body)
    post(c, body)
    assert len(brevo["calls"]) == 1


def test_gmail_forwarding_confirmation_code_is_shown(w, brevo):
    c = w["client"]
    post(c, brevo_body([address_of(c)], subject="(#123456789) Gmail Forwarding Confirmation - Receive Mail from a.b@gmail.com",
                       sender="forwarding-noreply@google.com", text="a.b@gmail.com has requested to forward mail. Confirmation code: 123456789"))
    v = c.get("/connect", headers=PRO).json()["inbox"]
    assert v["forwarding_code"]["code"] == "123456789"
    assert v["last"] is None


def test_an_address_takes_a_limited_number_of_mails_a_day(w, brevo, monkeypatch):
    c = w["client"]
    to = address_of(c)
    monkeypatch.setattr(inbound, "MAX_MAILS_PER_DAY", 3)
    for i in range(6):
        post(c, brevo_body([to], mid=f"id{i}"))
    assert len(state.section(PRO_ID, "inbox")["seen"]) == 3


def test_the_endpoint_is_rate_limited(w, brevo, monkeypatch):
    c = w["client"]
    monkeypatch.setattr(inbound, "MAX_POSTS_PER_MINUTE", 4)
    codes = [post(c, brevo_body(["x@y.z"], mid=str(i))).status_code for i in range(7)]
    assert codes[:4] == [200] * 4 and set(codes[4:]) == {429}


def signed(body: dict, secret=SECRET, at=None, mutate=lambda b: b):
    raw = json.dumps(body).encode()
    t = int(at if at is not None else time.time())
    sig = hmac.new(secret.encode(), f"{t}.".encode() + raw, hashlib.sha256).hexdigest()
    return mutate(raw), {"X-StratLab-Signature": f"t={t},v1={sig}", "Content-Type": "application/json"}


def test_signed_adapter_checks_the_signature(w, on, monkeypatch):
    monkeypatch.setattr(settings, "INBOUND_PROVIDER", "signed")
    c = w["client"]
    c.put("/connect/inbox/password", headers=PRO, json={"password": PAN})
    msg = {"to": [address_of(c)], "from": "x@example.test", "subject": "CAS", "message_id": "s1",
           "attachments": [{"name": "cas.pdf", "content_type": "application/pdf", "data_b64": b64(nsdl())}]}
    raw, h = signed(msg)
    assert c.post("/inbound/email/signed", content=raw, headers=h).status_code == 200
    assert len(holdings.load(PRO_ID)["items"]) == 2
    # tampered body, wrong secret, old timestamp, no header, malformed header
    raw, h = signed({**msg, "message_id": "s2"}, mutate=lambda b: b.replace(b"s2", b"s3"))
    assert c.post("/inbound/email/signed", content=raw, headers=h).status_code == 401
    raw, h = signed({**msg, "message_id": "s4"}, secret="other-secret")
    assert c.post("/inbound/email/signed", content=raw, headers=h).status_code == 401
    raw, h = signed({**msg, "message_id": "s5"}, at=time.time() - 3600)
    assert c.post("/inbound/email/signed", content=raw, headers=h).status_code == 401
    assert c.post("/inbound/email/signed", content=raw).status_code == 401
    assert c.post("/inbound/email/signed", content=raw, headers={"X-StratLab-Signature": "garbage"}).status_code == 401
    assert c.post("/inbound/email/brevo", content=raw, headers=h).status_code == 404


# ---------- the 40-day reminder ----------
def test_reminder_rules():
    now = datetime(2026, 10, 7, tzinfo=timezone.utc)
    iso = lambda days: (now - timedelta(days=days)).isoformat()
    assert not jobs.reminder_due({}, now)                                                     # no inbox
    assert not jobs.reminder_due({"local": "u-x", "created_at": iso(10)}, now)
    assert jobs.reminder_due({"local": "u-x", "created_at": iso(41)}, now)                     # never got one
    assert not jobs.reminder_due({"local": "u-x", "created_at": iso(100), "last": {"at": iso(5), "status": "ok"}}, now)
    assert jobs.reminder_due({"local": "u-x", "created_at": iso(100), "last": {"at": iso(45), "status": "ok"}}, now)
    assert jobs.reminder_due({"local": "u-x", "created_at": iso(100), "last": {"at": iso(1), "status": "wrong_password"}}, now)
    assert not jobs.reminder_due({"local": "u-x", "created_at": iso(100), "reminded_at": iso(3)}, now)
    assert jobs.reminder_due({"local": "u-x", "created_at": iso(100), "reminded_at": iso(41)}, now)
    # a statement read 5 days ago, then a mail without one: the last read counts, not the last mail
    assert not jobs.reminder_due({"local": "u-x", "created_at": iso(100), "ok_at": iso(5), "last": {"at": iso(1), "status": "no_pdf"}}, now)
    assert jobs.reminder_due({"local": "u-x", "created_at": iso(100), "ok_at": iso(45), "last": {"at": iso(1), "status": "no_pdf"}}, now)


def test_the_last_good_read_is_kept_apart_from_the_last_mail(w, on):
    assert upload(w["client"], nsdl()).status_code == 200
    assert state.section(PRO_ID, "inbox")["ok_at"]
    state.update(PRO_ID, "inbox", ok_at="2026-09-01T00:00:00+00:00")
    assert upload(w["client"], b"%PDF-1.4 junk").status_code == 400
    box = state.section(PRO_ID, "inbox")
    assert box["ok_at"] == "2026-09-01T00:00:00+00:00" and box["last"]["status"] != "ok"


def test_one_users_failing_reminder_doesnt_stop_the_others(monkeypatch):
    now = datetime(2026, 10, 7, tzinfo=timezone.utc)
    box = {"local": "x", "created_at": (now - timedelta(days=41)).isoformat()}
    sent = []
    monkeypatch.setattr(jobs.state, "everyone", lambda: [("u-bad", {"inbox": box}), ("u-ok", {"inbox": box})])

    def profile_for(uid):
        if uid == "u-bad":
            raise RuntimeError("the profile read failed")
        return {"id": uid}
    monkeypatch.setattr(jobs.state, "update", lambda uid, part, **kw: None)
    monkeypatch.setattr(jobs.sync, "profile_for", profile_for)
    monkeypatch.setattr(jobs.alerts, "notify", lambda profile, subject, text, background=True, url="": sent.append(profile["id"]) or True)
    assert jobs.run_reminders(now) == 1 and sent == ["u-ok"]


def test_reminder_goes_out_once(w, on, monkeypatch):
    c = w["client"]
    address_of(c)
    sent = []
    monkeypatch.setattr(jobs.alerts, "notify", lambda profile, subject, text, background=True, url="": sent.append((profile["id"], subject, url)) or ["push"])
    later = datetime.now(timezone.utc) + timedelta(days=41)
    assert jobs.run_reminders(later) == 1 and jobs.run_reminders(later) == 0
    assert sent == [(PRO_ID, jobs.REMINDER_SUBJECT, "/settings#accounts")]
    assert jobs.run_reminders(datetime.now(timezone.utc)) == 0


def test_a_reminder_with_no_usable_channel_is_not_marked(w, on, monkeypatch):
    address_of(w["client"])
    monkeypatch.setattr(jobs.alerts, "notify", lambda *a, **k: [])
    later = datetime.now(timezone.utc) + timedelta(days=41)
    assert jobs.run_reminders(later) == 0
    assert not state.section(PRO_ID, "inbox").get("reminded_at")
    monkeypatch.setattr(jobs.alerts, "notify", lambda *a, **k: ["push"])
    assert jobs.run_reminders(later) == 1


# ---------- Zerodha ----------
class TokenException(Exception):
    pass


class FakeKite:
    log: list = []
    holdings_rows: list = []
    positions_rows: list = []
    fail = None

    def __init__(self, key):
        self.key, self.token = key, None

    def login_url(self):
        return f"https://kite.example/connect/login?v=3&api_key={self.key}"

    def generate_session(self, request_token, api_secret):
        FakeKite.log.append(("session", request_token, api_secret))
        if request_token != "good-request-token":
            raise Exception("bad token")
        return {"access_token": "ACCESS-TOKEN-SECRET-1", "user_id": "AB1234"}

    def set_access_token(self, t):
        self.token = t

    def holdings(self):
        if FakeKite.fail:
            raise FakeKite.fail
        return FakeKite.holdings_rows

    def positions(self):
        return {"net": FakeKite.positions_rows, "day": []}

    def invalidate_access_token(self, t):
        FakeKite.log.append(("invalidate", t))


@pytest.fixture
def kite(monkeypatch, on):
    FakeKite.log, FakeKite.fail = [], None
    FakeKite.holdings_rows = [{"tradingsymbol": "INFY", "exchange": "NSE", "isin": "INE009A01021", "quantity": 8, "t1_quantity": 2,
                               "collateral_quantity": 0, "average_price": 1400.0},
                              {"tradingsymbol": "ITC", "exchange": "NSE", "isin": "INE154A01025", "quantity": 0, "t1_quantity": 0,
                               "collateral_quantity": 30, "average_price": 380.0},
                              {"tradingsymbol": "ZERO", "exchange": "NSE", "isin": "", "quantity": 0, "t1_quantity": 0, "average_price": 1}]
    FakeKite.positions_rows = [{"tradingsymbol": "TCS", "exchange": "NSE", "product": "CNC", "quantity": 4, "average_price": 3400.0},
                               {"tradingsymbol": "INFY", "exchange": "NSE", "product": "CNC", "quantity": 2, "average_price": 1.0},
                               {"tradingsymbol": "NIFTY26OCTFUT", "exchange": "NFO", "product": "NRML", "quantity": 50, "average_price": 1.0}]
    monkeypatch.setattr(kite_user, "factory", FakeKite)
    monkeypatch.setattr(settings, "KITE_API_KEY", "appkey")
    monkeypatch.setattr(settings, "KITE_API_SECRET", "appsecret-value")
    monkeypatch.setattr(settings, "KITE_MULTIUSER_APPROVED", False)
    monkeypatch.setattr(settings, "ADMIN_EMAILS", "owner@example.com")
    monkeypatch.setattr(settings, "PUBLIC_SITE_URL", "https://site.example")


def kite_state(c, headers=ADMIN):
    from urllib.parse import unquote
    url = c.get("/connect/kite/login", headers=headers).json()["url"]
    return unquote(url.split("redirect_params=")[1]).split("state=", 1)[1]


def kite_login(c, headers=ADMIN, request_token="good-request-token", path="/connect/kite/callback"):
    """Zerodha's round trip as the app's Settings page does it: back at the callback, then the signed-in page confirms.
    Answers as the old one-step callback did (a redirect to ?kite=ok or failed)."""
    from types import SimpleNamespace
    from urllib.parse import parse_qs, urlparse
    st = kite_state(c, headers)
    r = c.get(path, params={"request_token": request_token, "status": "success", "state": st}, follow_redirects=False)
    loc = r.headers.get("location", "")
    if "kite=confirm" not in loc:
        return r
    q = parse_qs(urlparse(loc).query)
    done = c.post("/connect/kite/confirm", headers=headers, json={"state": q["ks"][0], "claim": q["kc"][0]})
    return SimpleNamespace(status_code=303, headers={"location": "https://site.example/settings?kite=" + ("ok" if done.status_code == 200 else "failed") + "#accounts"})


def test_zerodha_is_closed_to_users_until_approved(w, kite):
    c = w["client"]
    assert c.get("/connect", headers=PRO).json()["kite"]["available"] is False
    assert c.get("/connect/kite/login", headers=PRO).status_code == 403
    assert c.post("/connect/kite/refresh", headers=PRO).status_code == 403
    assert c.get("/connect", headers=ADMIN).json()["kite"]["available"] is True        # the owner can already use it


def test_zerodha_opens_for_everyone_with_the_flag(w, kite, monkeypatch):
    monkeypatch.setattr(settings, "KITE_MULTIUSER_APPROVED", True)
    assert w["client"].get("/connect/kite/login", headers=PRO).status_code == 200


def test_zerodha_needs_the_encryption_key(w, kite, monkeypatch):
    monkeypatch.setattr(settings, "KITE_MULTIUSER_APPROVED", True)
    monkeypatch.setattr(settings, "CONNECT_SECRET_KEY", "")
    assert w["client"].get("/connect/kite/login", headers=PRO).status_code == 403


def test_zerodha_login_reads_holdings_and_keeps_the_token_sealed(w, kite):
    c = w["client"]
    r = kite_login(c)
    assert r.status_code == 303 and r.headers["location"] == "https://site.example/settings?kite=ok#accounts"
    assert ("session", "good-request-token", "appsecret-value") in FakeKite.log
    admin_id = "u-admin"
    items = {i["symbol"]: i for i in holdings.load(admin_id)["items"]}
    # settled and T+1, plus today's delivery buy of 2 (B9: a day's trade in a stock already held counts)
    assert items["INFY"]["qty"] == 12 and items["INFY"]["avg"] == pytest.approx((1400.0 * 10 + 1.0 * 2) / 12)
    assert items["ITC"]["qty"] == 30                                                         # pledged shares still count
    assert items["TCS"]["qty"] == 4 and "ZERO" not in items and "NIFTY26OCTFUT" not in items  # today's buy; no futures
    assert all(i["via"] == "kite" for i in items.values()) and holdings.load(admin_id)["source"] == "Zerodha Kite"
    raw = state_text(admin_id)
    assert "ACCESS-TOKEN-SECRET-1" not in raw and vault.unseal(state.section(admin_id, "kite")["token"]) == "ACCESS-TOKEN-SECRET-1"
    v = c.get("/connect", headers=ADMIN).json()["kite"]
    assert v["connected"] and v["live"] and not v["expired"] and v["refreshed_label"].startswith("today ")
    assert "ACCESS-TOKEN" not in json.dumps(v)


def test_zerodha_refresh_and_a_sold_stock(w, kite):
    c = w["client"]
    kite_login(c)
    FakeKite.holdings_rows = FakeKite.holdings_rows[:1]
    FakeKite.positions_rows = []
    r = c.post("/connect/kite/refresh", headers=ADMIN)
    assert r.status_code == 200, r.text
    assert {i["symbol"] for i in holdings.load("u-admin")["items"]} == {"INFY"}


def test_zerodha_login_ends_next_morning(w, kite):
    c = w["client"]
    kite_login(c)
    state.update("u-admin", "kite", day="2020-01-01")
    r = c.post("/connect/kite/refresh", headers=ADMIN)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "login_needed"
    v = c.get("/connect", headers=ADMIN).json()["kite"]
    assert v["connected"] and v["expired"] and not v["live"]


def test_zerodha_cancelling_the_token_mid_day(w, kite):
    c = w["client"]
    kite_login(c)
    FakeKite.fail = TokenException("expired")
    r = c.post("/connect/kite/refresh", headers=ADMIN)
    assert r.status_code == 409 and state.section("u-admin", "kite")["status"] == "expired"


def test_zerodha_callback_refuses_bad_state_and_cancel(w, kite):
    c = w["client"]
    for params in ({"request_token": "good-request-token", "status": "success", "state": "u1.forged.value"},
                   {"request_token": "good-request-token", "status": "success", "state": "plain"},
                   {"request_token": "", "status": "cancelled", "state": ""}):
        r = c.get("/connect/kite/callback", params=params, follow_redirects=False)
        assert r.status_code == 303 and "kite=ok" not in r.headers["location"]
    assert db.get_setting(state.KEY + "u-admin") is None
    assert kite_login(c, request_token="wrong").headers["location"].endswith("kite=failed#accounts")


def test_zerodha_state_is_for_one_user_and_expires(w, kite, monkeypatch):
    c = w["client"]
    url = c.get("/connect/kite/login", headers=ADMIN).json()["url"]
    from urllib.parse import unquote
    st = unquote(url.split("redirect_params=")[1]).split("state=", 1)[1]
    assert kite_user.uid_from_state(st) == "u-admin"
    monkeypatch.setattr(time, "time", lambda: time.monotonic() * 0 + 4_000_000_000)
    assert kite_user.uid_from_state(st) is None


def test_the_admin_callback_hands_user_logins_over(w, kite):
    r = kite_login(w["client"], path="/admin/kite/callback")
    assert r.status_code == 303 and r.headers["location"].endswith("kite=ok#accounts")


def test_disconnecting_a_shared_zerodha_login_keeps_the_data_login(w, kite):
    state.update("u-admin", "kite", token=vault.seal("DATA-LOGIN-TOKEN"), day=kite_user.today_ist(), shared=True)
    w["client"].delete("/connect/kite", headers=ADMIN)
    assert not [e for e in FakeKite.log if e[0] == "invalidate"]                  # only the stored copy is dropped
    assert db.get_setting(state.KEY + "u-admin") is None


def test_disconnecting_zerodha_deletes_the_token(w, kite):
    c = w["client"]
    kite_login(c)
    c.delete("/connect/kite", headers=ADMIN)
    assert ("invalidate", "ACCESS-TOKEN-SECRET-1") in FakeKite.log
    assert db.get_setting(state.KEY + "u-admin") is None
    assert len(holdings.load("u-admin")["items"]) > 0                                   # what was read stays


# ---------- Interactive Brokers ----------
FLEX_OK = """<FlexQueryResponse queryName="StratLab" type="AF"><FlexStatements count="1"><FlexStatement accountId="U1234567">
<OpenPositions>
<OpenPosition assetCategory="STK" symbol="AAPL" description="APPLE INC" currency="USD" position="10" costBasisPrice="150.5" markPrice="190"/>
<OpenPosition assetCategory="STK" symbol="MSFT" description="MICROSOFT CORP" currency="USD" position="4" costBasisPrice="300" markPrice="400"/>
<OpenPosition assetCategory="OPT" symbol="AAPL 261016C00200000" currency="USD" position="1" costBasisPrice="5"/>
<OpenPosition assetCategory="STK" symbol="SAP" currency="EUR" position="3" costBasisPrice="100"/>
</OpenPositions>
<Trades>
<Trade assetCategory="STK" symbol="AAPL" currency="USD" buySell="BUY" quantity="10" tradePrice="150" tradeDate="20260105" dateTime="20260105;103000" ibCommission="-1" tradeID="T1"/>
<Trade assetCategory="STK" symbol="AAPL" currency="USD" buySell="SELL" quantity="-4" tradePrice="180" tradeDate="20260210" dateTime="20260210;143000" ibCommission="-1" tradeID="T2"/>
<Trade assetCategory="STK" symbol="AAPL" currency="USD" buySell="SELL" quantity="-6" tradePrice="190" tradeDate="20260301" dateTime="20260301;143000" ibCommission="-1.5" tradeID="T3"/>
<Trade assetCategory="STK" symbol="TSLA" currency="USD" buySell="SELL" quantity="-5" tradePrice="200" tradeDate="20260120" dateTime="20260120;143000" ibCommission="-1" tradeID="T4"/>
<Trade assetCategory="OPT" symbol="AAPL 261016C00200000" currency="USD" buySell="BUY" quantity="1" tradePrice="5" tradeDate="20260105" tradeID="T5"/>
</Trades></FlexStatement></FlexStatements></FlexQueryResponse>"""
TOKEN = "123456789012345678901234"


def flex_transport(statement=FLEX_OK, ready_after=0, send_error=None):
    calls = []

    def handler(req: httpx.Request):
        calls.append(str(req.url))
        if req.url.path.endswith("SendRequest"):
            if send_error:
                return httpx.Response(200, text=f"<FlexStatementResponse><Status>Fail</Status><ErrorCode>{send_error}</ErrorCode><ErrorMessage>x</ErrorMessage></FlexStatementResponse>")
            return httpx.Response(200, text="<FlexStatementResponse><Status>Success</Status><ReferenceCode>REF1</ReferenceCode><Url>u</Url></FlexStatementResponse>")
        n = sum(1 for u in calls if "GetStatement" in u)
        if n <= ready_after:
            return httpx.Response(200, text="<FlexStatementResponse><Status>Warn</Status><ErrorCode>1019</ErrorCode></FlexStatementResponse>")
        return httpx.Response(200, text=statement)
    t = httpx.MockTransport(handler)
    t.calls = calls
    return t


@pytest.fixture
def flex(monkeypatch, on):
    t = flex_transport()
    monkeypatch.setattr(ibkr, "transport", t)
    monkeypatch.setattr(ibkr, "sleep", lambda s: None)
    monkeypatch.setattr(sync.deps, "us_find", lambda s: {"symbol": s, "name": s})
    return t


def connect_ibkr(c, headers=PRO, token=TOKEN, query="987654"):
    return c.put("/connect/ibkr", headers=headers, json={"token": token, "query_id": query})


def test_ibkr_connect_reads_positions_and_trades(w, flex):
    c = w["client"]
    r = connect_ibkr(c)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["positions"] == 2 and body["left_out"] == 2 and body["trades_added"] == 2
    items = {i["symbol"]: i for i in holdings.load(PRO_ID)["items"]}
    assert items["AAPL"]["market"] == "US" and items["AAPL"]["qty"] == 10 and items["AAPL"]["avg"] == 150.5 and items["AAPL"]["via"] == "ibkr"
    assert "SAP" not in items and holdings.load(PRO_ID)["source"] == "Interactive Brokers"
    trades = [m for m in journal.load(PRO_ID)["manual"] if m.get("via") == "ibkr"]
    assert sorted((t["xd"], t["qty"], t["entry"], t["exit"], t["side"], t["segment"]) for t in trades) == [
        ("2026-02-10", 4.0, 150.0, 180.0, "long", "us"), ("2026-03-01", 6.0, 150.0, 190.0, "long", "us")]
    first = min(trades, key=lambda t: t["xd"])
    assert first["charges"] == pytest.approx(0.4 + 1.0)                    # its share of both commissions
    # the TSLA sale has no purchase in the data: left out, never guessed
    assert all(t["sym"] != "TSLA" for t in trades)


def test_ibkr_token_is_stored_sealed_and_never_returned_or_logged(w, flex, caplog, capsys):
    c = w["client"]
    with caplog.at_level(logging.DEBUG):
        r = connect_ibkr(c)
        v = c.get("/connect", headers=PRO).json()
        c.post("/connect/ibkr/refresh", headers=PRO)
    assert r.status_code == 200
    assert TOKEN not in state_text(PRO_ID) and TOKEN not in r.text and TOKEN not in json.dumps(v)
    assert vault.unseal(state.section(PRO_ID, "ibkr")["token"]) == TOKEN
    out = capsys.readouterr()
    assert TOKEN not in caplog.text and TOKEN not in out.out and TOKEN not in out.err
    assert v["ibkr"]["connected"] and v["ibkr"]["synced_at"] and v["ibkr"]["positions"] == 2


def test_ibkr_a_second_read_adds_nothing_twice(w, flex):
    c = w["client"]
    connect_ibkr(c)
    again = c.post("/connect/ibkr/refresh", headers=PRO).json()
    assert again["trades_added"] == 0 and len(holdings.load(PRO_ID)["items"]) == 2
    assert len([m for m in journal.load(PRO_ID)["manual"] if m.get("via") == "ibkr"]) == 2


def test_ibkr_waits_for_a_statement_that_is_being_made(w, on, monkeypatch):
    t = flex_transport(ready_after=2)
    monkeypatch.setattr(ibkr, "transport", t)
    monkeypatch.setattr(ibkr, "sleep", lambda s: None)
    monkeypatch.setattr(sync.deps, "us_find", lambda s: {"symbol": s, "name": s})
    assert connect_ibkr(w["client"]).status_code == 200
    assert sum("GetStatement" in u for u in t.calls) == 3


@pytest.mark.parametrize("code,status", [("1012", "token_expired"), ("1015", "token_invalid"), ("1014", "query_invalid"), ("9999", "failed")])
def test_ibkr_errors_in_plain_words_and_nothing_is_kept(w, on, monkeypatch, code, status):
    monkeypatch.setattr(ibkr, "transport", flex_transport(send_error=code))
    r = connect_ibkr(w["client"])
    assert r.status_code == 400 and r.json()["detail"]["code"] == status and TOKEN not in r.text
    assert db.get_setting(state.KEY + PRO_ID) is None


def test_ibkr_unreachable_does_not_leak_the_token(w, on, monkeypatch, caplog):
    def boom(req):
        raise httpx.ConnectError("could not connect to " + str(req.url), request=req)
    monkeypatch.setattr(ibkr, "transport", httpx.MockTransport(boom))
    with caplog.at_level(logging.DEBUG):
        r = connect_ibkr(w["client"])
    assert r.status_code == 400 and r.json()["detail"]["code"] == "unreachable"
    assert TOKEN not in r.text and TOKEN not in caplog.text


def test_ibkr_input_is_checked(w, flex):
    c = w["client"]
    assert connect_ibkr(c, token="short").status_code == 422
    assert connect_ibkr(c, query="abc").status_code == 422
    assert c.put("/connect/ibkr", headers=PRO, json={"token": "has spaces and <b>", "query_id": "1"}).status_code == 422
    assert c.put("/connect/ibkr", json={"token": TOKEN, "query_id": "1"}).status_code == 401


def test_ibkr_needs_the_encryption_key(w, flex, monkeypatch):
    monkeypatch.setattr(settings, "CONNECT_SECRET_KEY", "")
    assert connect_ibkr(w["client"]).status_code == 503


def test_ibkr_daily_job(w, flex, monkeypatch):
    connect_ibkr(w["client"])
    box = state.section(PRO_ID, "ibkr")
    ist = ibkr.IST
    morning = datetime.now(ist).replace(hour=9, minute=0)
    assert not ibkr.due(box, morning)                                                     # read today already
    assert not ibkr.due(box, morning.replace(hour=6))
    assert ibkr.due(box, morning + timedelta(days=1))
    assert not ibkr.due({}, morning) and not ibkr.due({"token": "x"}, morning)
    flex.calls.clear()
    out = ibkr.run_daily(morning + timedelta(days=1))
    assert out == {"users": 1, "ok": 1, "failed": 0} and flex.calls
    # a failed read is tried again the next day, not every half hour
    monkeypatch.setattr(ibkr, "transport", flex_transport(send_error="1012"))
    nxt = morning + timedelta(days=2)
    assert ibkr.run_daily(nxt) == {"users": 1, "ok": 0, "failed": 1}
    assert state.section(PRO_ID, "ibkr")["status"] == "token_expired"
    state.update(PRO_ID, "ibkr", tried_at=nxt.isoformat())                              # the job's clock is the test's clock
    assert ibkr.run_daily(nxt + timedelta(minutes=30)) == {"users": 0, "ok": 0, "failed": 0}
    assert ibkr.run_daily(nxt + timedelta(days=1))["users"] == 1


def test_ibkr_a_crash_while_saving_is_one_failed_try_not_a_read_every_half_hour(w, flex, monkeypatch):
    connect_ibkr(w["client"])
    day = datetime.now(ibkr.IST).replace(hour=9, minute=0) + timedelta(days=3)

    def boom(*a, **k):
        raise RuntimeError("storage went away")
    monkeypatch.setattr(ibkr, "ingest", boom)
    flex.calls.clear()
    assert ibkr.run_daily(day) == {"users": 1, "ok": 0, "failed": 1}
    box = state.section(PRO_ID, "ibkr")
    assert box["status"] == "failed" and box["tried_at"]
    state.update(PRO_ID, "ibkr", tried_at=day.isoformat())                              # the job's clock is the test's clock
    assert ibkr.run_daily(day + timedelta(minutes=30)) == {"users": 0, "ok": 0, "failed": 0}
    assert ibkr.run_daily(day + timedelta(days=1))["users"] == 1


def test_ibkr_an_empty_statement_keeps_the_us_holdings(w, flex, monkeypatch):
    c = w["client"]
    connect_ibkr(c)
    empty = FLEX_OK.split("<OpenPositions>")[0] + FLEX_OK.split("</OpenPositions>")[1]
    monkeypatch.setattr(ibkr, "transport", flex_transport(empty))
    assert c.post("/connect/ibkr/refresh", headers=PRO).status_code == 200
    assert {"AAPL", "MSFT"} <= {i["symbol"] for i in holdings.load(PRO_ID)["items"]}
    box = state.section(PRO_ID, "ibkr")
    assert box["status"] == "partial" and "failed read" in box["detail"]


def test_ibkr_disconnect_deletes_the_token_and_keeps_what_was_read(w, flex):
    c = w["client"]
    connect_ibkr(c)
    v = c.delete("/connect/ibkr", headers=PRO).json()
    assert v["ibkr"]["connected"] is False and db.get_setting(state.KEY + PRO_ID) is None
    assert len(holdings.load(PRO_ID)["items"]) == 2


def test_ibkr_fifo_pairs_shorts_and_partial_fills():
    fs = [{"id": "a", "sym": "X", "side": "S", "qty": 10, "price": 50.0, "d": "2026-01-01", "t": "10:00:00", "fee": 1.0, "oc": "O"},
          {"id": "b", "sym": "X", "side": "B", "qty": 4, "price": 40.0, "d": "2026-01-02", "t": "10:00:00", "fee": 0.4, "oc": "C"},
          {"id": "c", "sym": "X", "side": "B", "qty": 6, "price": 45.0, "d": "2026-01-03", "t": "10:00:00", "fee": 0.6, "oc": "C"}]
    got = ibkr.closed_trades(fs)
    assert [(t["side"], t["qty"], t["entry"], t["exit"]) for t in got] == [("short", 4.0, 50.0, 40.0), ("short", 6.0, 50.0, 45.0)]
    assert sum(t["charges"] for t in got) == pytest.approx(2.0)
    assert len({t["id"] for t in got}) == 2 and got == ibkr.closed_trades(fs)             # ids don't change between reads


def test_ibkr_fifo_counts_a_split_between_the_buy_and_the_sale():
    fs = [{"id": "a", "sym": "X", "side": "B", "qty": 10, "price": 400.0, "d": "2026-01-01", "t": "10:00:00", "fee": 1.0},
          {"id": "b", "sym": "X", "side": "S", "qty": 40, "price": 110.0, "d": "2026-03-01", "t": "10:00:00", "fee": 4.0}]
    root = ET.fromstring('<FlexStatement><CorporateActions>'
                         '<CorporateAction assetCategory="STK" symbol="X" type="FS" dateTime="20260210;202500" reportDate="20260211" '
                         'actionDescription="X(US0000000001) SPLIT 4 FOR 1 (X, X INC, US0000000001)"/>'
                         '<CorporateAction assetCategory="STK" symbol="X" type="TC" dateTime="20260110;202500" actionDescription="X MERGED"/>'
                         '</CorporateActions></FlexStatement>')
    sp = ibkr.splits(root)
    assert sp == {"X": [("2026-02-11", 4.0)]}                         # the day it takes effect (reportDate)
    assert [(t["side"], t["qty"], t["entry"], t["exit"]) for t in ibkr.closed_trades(fs, sp)] == [("long", 40.0, 100.0, 110.0)]
    assert sum(t["charges"] for t in ibkr.closed_trades(fs, sp)) == pytest.approx(5.0)
    assert ibkr.closed_trades(fs, sp) == ibkr.closed_trades(fs, sp) and ibkr.closed_trades(fs)[0]["qty"] == 10.0     # without the data, as before
    assert ibkr.closed_trades(fs, {"X": [("2026-03-02", 4.0)]})[0]["qty"] == 10.0                  # a split after the sale changes nothing


SPLIT_FS = [{"id": "a", "sym": "X", "side": "B", "qty": 10, "price": 400.0, "d": "2026-01-01", "t": "10:00:00", "fee": 0.0},
            {"id": "b", "sym": "X", "side": "S", "qty": 5, "price": 400.0, "d": "2026-02-10", "t": "10:00:00", "fee": 0.0},
            {"id": "c", "sym": "X", "side": "S", "qty": 20, "price": 110.0, "d": "2026-03-01", "t": "10:00:00", "fee": 0.0}]


def split_action(attrs: str) -> str:
    return (f'<CorporateActions><CorporateAction assetCategory="STK" symbol="X" type="FS" {attrs} '
            'actionDescription="X(US0000000001) SPLIT 4 FOR 1 (X, X INC, US0000000001)"/></CorporateActions>')


@pytest.mark.parametrize("attrs", ['dateTime="20260210;202500" reportDate="20260211"', 'dateTime="20260210;202500"',
                                   'reportDate="20260211"'])
def test_ibkr_a_fill_on_the_day_a_split_is_booked_is_in_the_old_shares(attrs):
    # IBKR books the split the evening before it takes effect: that day's sale is at the old price, of the old shares
    sp = ibkr.splits(ET.fromstring(f"<FlexStatement>{split_action(attrs)}</FlexStatement>"))
    assert sp == {"X": [("2026-02-11", 4.0)]}
    got = ibkr.closed_trades(SPLIT_FS, sp)
    assert [(t["xd"], t["qty"], t["entry"], t["exit"]) for t in got] == [("2026-02-10", 5, 400.0, 400.0), ("2026-03-01", 20, 100.0, 110.0)]
    # a fill on the day it takes effect is in the new shares
    fs = SPLIT_FS[:1] + [{**SPLIT_FS[2], "d": "2026-02-11", "qty": 40}]
    assert [(t["qty"], t["entry"]) for t in ibkr.closed_trades(fs, sp)] == [(40, 100.0)]


def test_ibkr_trades_read_before_a_split_was_counted_are_replaced_not_doubled(w, flex):
    trades = ("<Trades>" + "".join(
        f'<Trade assetCategory="STK" symbol="X" currency="USD" buySell="{s}" quantity="{q}" tradePrice="{p}" tradeDate="{d}" '
        f'dateTime="{d};100000" ibCommission="0" tradeID="{i}"/>'
        for s, q, p, d, i in (("BUY", 10, 400, "20260105", "X1"), ("SELL", -40, 110, "20260301", "X2"))) + "</Trades>")
    action = split_action('dateTime="20260210;202500" reportDate="20260211"')
    root = ET.fromstring(f"<FlexQueryResponse><FlexStatements><FlexStatement>{trades}{action}</FlexStatement></FlexStatements></FlexQueryResponse>")
    # what an earlier read saved without the split: 10 shares from 400 to 110; and two trades the statement doesn't cover
    ibkr.save_trades(PRO_ID, ibkr.closed_trades(ibkr.fills(root)))
    older = {"id": "ibolder", "sym": "X", "segment": "us", "side": "long", "ed": "2025-06-02", "xd": "2025-07-01", "qty": 3,
             "entry": 300.0, "exit": 320.0, "charges": 0.0, "via": "ibkr"}
    other = {**older, "id": "ibother", "sym": "Y", "ed": "2026-01-06", "xd": "2026-03-02"}
    j = journal.load(PRO_ID)
    j["manual"] += [older, other]
    journal.save(PRO_ID, j)
    got = ibkr.ingest(PRO_ID, root)
    mine = sorted(((m["sym"], m["ed"], m["qty"], m["entry"], m["exit"]) for m in journal.load(PRO_ID)["manual"] if m.get("via") == "ibkr"))
    assert mine == [("X", "2025-06-02", 3, 300.0, 320.0), ("X", "2026-01-05", 40, 100.0, 110.0), ("Y", "2026-01-06", 3, 300.0, 320.0)]
    assert got["trades_added"] == 1
    assert ibkr.ingest(PRO_ID, root)["trades_added"] == 0                       # read again: nothing changes
    assert len([m for m in journal.load(PRO_ID)["manual"] if m.get("via") == "ibkr"]) == 3


# ---------- EPF, NPS, AIS ----------
def text_pdf(lines: list[str]) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    y = 800
    for ln in lines:
        c.drawString(40, y, ln)
        y -= 14
    c.save()
    return buf.getvalue()


def read_doc(c, kind, raw, name="f.pdf", headers=PRO, password=""):
    return c.post("/connect/docs/read", headers=headers, json={"kind": kind, "filename": name, "data": b64(raw), "password": password})


EPF_PDF = ["Member Passbook", "Establishment: EXAMPLE PRIVATE LIMITED  Member Id: XXXX0000000001",
           "Closing Balance as on 31/03/2026 1,50,000 1,20,000 40,000",
           "Establishment: OLDER EMPLOYER LIMITED  Member Id: XXXX0000000002",
           "Closing Balance as on 31/03/2024 20,000.50 20,000 0"]


def test_epf_passbook_figures_are_read_then_confirmed(w, on):
    c = w["client"]
    r = read_doc(c, "epf", text_pdf(EPF_PDF))
    assert r.status_code == 200, r.text
    figs = {f["key"]: f for f in r.json()["figures"]}
    assert figs["balance"]["value"] == 310000.5 and figs["balance"]["found"] and figs["as_of"]["value"] == "2026-03-31"
    assert money_networth.load(PRO_ID)["items"] == []                                      # reading saves nothing
    ok = c.post("/connect/docs/confirm", headers=PRO, json={"kind": "epf", "figures": {"balance": "3,10,000.5", "as_of": "2026-03-31"}})
    assert ok.status_code == 200, ok.text
    epf = [i for i in money_networth.load(PRO_ID)["items"] if i["kind"] == "epf"]
    assert len(epf) == 1 and epf[0]["balance"] == 310000.5 and epf[0]["as_of"] == "2026-03-31"
    c.post("/connect/docs/confirm", headers=PRO, json={"kind": "epf", "figures": {"balance": 320000}})
    assert [i["balance"] for i in money_networth.load(PRO_ID)["items"] if i["kind"] == "epf"] == [320000]


def test_a_typed_epf_entry_is_not_replaced(w, on):
    money_networth.save(PRO_ID, [{"id": "aa", "kind": "epf", "name": "EPF", "balance": 1.0, "as_of": "2026-01-01"}])
    r = w["client"].post("/connect/docs/confirm", headers=PRO, json={"kind": "epf", "figures": {"balance": 5}})
    assert "already have" in r.json()["detail"] and money_networth.load(PRO_ID)["items"][0]["balance"] == 1.0


def test_epf_passbook_that_cannot_be_read_leaves_the_figures_to_type(w, on):
    r = read_doc(w["client"], "epf", text_pdf(["Nothing useful here"]))
    assert r.status_code == 200 and r.json()["found"] == 0 and all(not f["found"] for f in r.json()["figures"])
    bad = w["client"].post("/connect/docs/confirm", headers=PRO, json={"kind": "epf", "figures": {"balance": "abc"}})
    assert bad.status_code == 400


def test_nps_statement(w, on):
    c = w["client"]
    r = read_doc(c, "nps", text_pdf(["NPS Transaction Statement as on 31/03/2026", "Tier I Total Holding Value 2,50,000.45",
                                     "Tier II Total Holding Value 50,000.00"]))
    figs = {f["key"]: f["value"] for f in r.json()["figures"]}
    assert figs == {"tier1": 250000.45, "tier2": 50000.0, "as_of": "2026-03-31"}
    c.post("/connect/docs/confirm", headers=PRO, json={"kind": "nps", "figures": figs})
    nps = [i for i in money_networth.load(PRO_ID)["items"] if i["kind"] == "nps"]
    assert nps[0]["tier1"] == 250000.45 and nps[0]["tier2"] == 50000.0


AIS = {"financialYear": "2025-26", "partB": [
    {"informationDescription": "Dividend", "sourceName": "Alpha Industries Ltd", "dateOfPayment": "12/06/2025", "amount": "1,200.00", "tdsDeducted": "0"},
    {"informationDescription": "Dividend", "sourceName": "Beta Bank Ltd", "dateOfPayment": "20/12/2025", "amount": "30000", "tdsDeducted": "3000"},
    {"informationDescription": "Interest from savings bank", "sourceName": "Example Bank", "amount": "8,500"},
    {"informationDescription": "TDS", "sourceName": "Employer", "amount": "10", "tdsDeducted": "55,000"}]}


def test_ais_json_figures_and_what_they_feed(w, on):
    c = w["client"]
    r = read_doc(c, "ais", json.dumps(AIS).encode(), name="ais.json")
    assert r.status_code == 200, r.text
    figs = {f["key"]: f["value"] for f in r.json()["figures"]}
    assert figs["fy"] == 2025 and figs["dividend"] == 31200.0 and figs["interest"] == 8500.0 and figs["tds"] == 58000.0
    assert len(r.json()["lines"]) == 2
    ok = c.post("/connect/docs/confirm", headers=PRO, json={"kind": "ais", "figures": figs, "apply_tds": True, "lines": r.json()["lines"]})
    assert ok.status_code == 200, ok.text
    assert adv.load(PRO_ID)["years"][2025]["tds"] == 58000.0
    rows = divs.load(PRO_ID)["rows"]
    assert sorted((x["d"], x["amount"]) for x in rows) == [("2025-06-12", 1200.0), ("2025-12-20", 30000.0)]
    c.post("/connect/docs/confirm", headers=PRO, json={"kind": "ais", "figures": figs, "lines": r.json()["lines"]})
    assert len(divs.load(PRO_ID)["rows"]) == 2                                               # no doubling
    assert c.get("/connect", headers=PRO).json()["docs"]["ais"]["2025"]["tds"] == 58000.0


def test_ais_tds_is_applied_only_when_asked(w, on):
    w["client"].post("/connect/docs/confirm", headers=PRO, json={"kind": "ais", "figures": {"fy": 2025, "tds": 100}})
    assert adv.load(PRO_ID)["years"].get(2025) is None


def test_ais_pdf_is_typed_not_guessed(w, on):
    r = read_doc(w["client"], "ais", text_pdf(["Annual Information Statement 2025-26"]))
    figs = {f["key"]: f for f in r.json()["figures"]}
    assert figs["fy"]["value"] == 2025 and not figs["dividend"]["found"] and not figs["tds"]["found"]
    assert w["client"].post("/connect/docs/confirm", headers=PRO, json={"kind": "ais", "figures": {"tds": 5}}).status_code == 400


def test_doc_uploads_are_checked(w, on):
    c = w["client"]
    assert read_doc(c, "epf", b"plain text").status_code == 400
    assert read_doc(c, "ais", b"{broken", name="a.json").status_code == 400
    assert c.post("/connect/docs/read", headers=PRO, json={"kind": "other", "filename": "x", "data": b64(b"x")}).status_code == 422
    assert c.post("/connect/docs/confirm", headers=PRO, json={"kind": "epf", "figures": {"balance": -5}}).status_code == 400
    from reportlab.lib.pdfencrypt import StandardEncryption
    buf = io.BytesIO()
    cv = canvas.Canvas(buf, encrypt=StandardEncryption("pw12345", canPrint=1))
    cv.drawString(40, 700, "Closing Balance as on 31/03/2026 10 20 0")
    cv.save()
    assert read_doc(c, "epf", buf.getvalue(), password="bad").json()["detail"]["code"] == "wrong_password"
    assert read_doc(c, "epf", buf.getvalue(), password="pw12345").json()["figures"][0]["value"] == 30.0


# ---------- nothing sensitive in logs, across every flow ----------
def test_no_flow_writes_a_secret_to_the_logs(w, brevo, flex, caplog, capsys):
    c = w["client"]
    secrets_ = [DEMAT_PASSWORD, TOKEN, SECRET, "brevo-api-key-123456", PAN]
    with caplog.at_level(logging.DEBUG):
        c.put("/connect/inbox/password", headers=PRO, json={"password": DEMAT_PASSWORD})
        brevo["t"] = nsdl(password=DEMAT_PASSWORD)
        post(c, brevo_body([address_of(c)], [("cas.pdf", "t")]))
        post(c, brevo_body([address_of(c)], [("cas.pdf", "t")], mid="again"), k="wrong")
        upload(c, nsdl(), password="WRONGPASS1")
        connect_ibkr(c)
        c.post("/connect/ibkr/refresh", headers=PRO)
    out = capsys.readouterr()
    for s in secrets_:
        assert s not in caplog.text and s not in out.out and s not in out.err, s
    assert holdings.load(PRO_ID)["items"]


def test_stored_values_never_hold_a_plain_secret(w, brevo, flex):
    c = w["client"]
    c.put("/connect/inbox/password", headers=PRO, json={"password": DEMAT_PASSWORD})
    connect_ibkr(c)
    raw = "".join(v for _, v in db.all_settings_with_prefix(""))
    for s in (DEMAT_PASSWORD, TOKEN):
        assert s not in raw


# ---------- Zerodha: a login link passed to someone else can't link their account ----------
def kite_back(c, st, request_token="good-request-token"):
    """Zerodha sends the browser back to the callback: (claim, state) the landing page gets."""
    from urllib.parse import parse_qs, urlparse
    r = c.get("/connect/kite/callback", params={"request_token": request_token, "status": "success", "state": st}, follow_redirects=False)
    q = parse_qs(urlparse(r.headers["location"]).query)
    return r, q


def test_the_callback_alone_links_nothing(w, kite, monkeypatch):
    monkeypatch.setattr(settings, "KITE_MULTIUSER_APPROVED", True)
    c = w["client"]
    st = kite_state(c, PRO)
    r, q = kite_back(c, st)
    assert r.headers["location"].startswith("https://site.example/settings?kite=confirm&ks=") and q["ks"] == [st]
    assert db.get_setting(state.KEY + PRO_ID) is None                              # a signed token on a link is not a sign-in
    assert not c.get("/connect", headers=PRO).json()["kite"]["connected"]


def test_a_victims_login_through_the_attackers_link_is_not_attached(w, kite, monkeypatch):
    monkeypatch.setattr(settings, "KITE_MULTIUSER_APPROVED", True)
    c = w["client"]
    st = kite_state(c, PRO)                                                          # the attacker's link
    _, q = kite_back(c, st)                                                          # the victim finishes it at Zerodha
    # the victim's own sign-in, or the attacker who knows the state but never saw the claim
    assert c.post("/connect/kite/confirm", headers=BASIC, json={"state": st, "claim": q["kc"][0]}).status_code == 400
    assert c.post("/connect/kite/confirm", headers=PRO, json={"state": st, "claim": "guessed"}).status_code == 400
    assert c.post("/connect/kite/confirm", headers=PRO, json={"state": st, "claim": ""}).status_code == 400
    assert db.get_setting(state.KEY + PRO_ID) is None and db.get_setting(state.KEY + BASIC_ID) is None
    assert c.post("/connect/kite/confirm", headers=PRO, json={"state": st, "claim": q["kc"][0]}).status_code == 200   # the right browser still can
    assert state.section(PRO_ID, "kite")["kite_user"] == "AB1234"


def test_a_zerodha_login_state_works_once(w, kite, monkeypatch):
    monkeypatch.setattr(settings, "KITE_MULTIUSER_APPROVED", True)
    c = w["client"]
    st = kite_state(c, PRO)
    _, q = kite_back(c, st)
    assert c.post("/connect/kite/confirm", headers=PRO, json={"state": st, "claim": q["kc"][0]}).status_code == 200
    assert c.post("/connect/kite/confirm", headers=PRO, json={"state": st, "claim": q["kc"][0]}).status_code == 400   # confirmed once
    n = len(FakeKite.log)
    r, _ = kite_back(c, st)                                                          # the callback again with the same state
    assert r.headers["location"].endswith("kite=failed#accounts") and not any(x[0] == "session" for x in FakeKite.log[n:])


def test_a_staged_zerodha_login_expires(w, kite, monkeypatch):
    monkeypatch.setattr(settings, "KITE_MULTIUSER_APPROVED", True)
    c = w["client"]
    st = kite_state(c, PRO)
    _, q = kite_back(c, st)
    real = time.time()
    monkeypatch.setattr(time, "time", lambda: real + kite_user.PENDING_TTL + 5)
    r = c.post("/connect/kite/confirm", headers=PRO, json={"state": st, "claim": q["kc"][0]})
    assert r.status_code == 400 and db.get_setting(state.KEY + PRO_ID) is None


def test_confirming_a_zerodha_login_needs_signing_in(w, kite):
    assert w["client"].post("/connect/kite/confirm", json={"state": "u1.x", "claim": "y"}).status_code == 401


def _acct(sym, q, a):
    return {"symbol": sym, "exchange": "NSE", "qty": q, "avg": None, "accts": {a: q}}


@pytest.mark.parametrize("first,second", [("NSDL:abc", "NSDL"), ("NSDL", "NSDL:abc")])
def test_an_account_whose_key_changes_is_not_counted_twice(first, second):
    s = sync.merge_sync([], [_acct("INFY", 10, first)], "cas", True, {first})[0]
    items, _ = sync.merge_sync(s, [_acct("INFY", 10, second)], "cas", True, {second})
    assert items[0]["qty"] == 10 and items[0]["accts"] == {second: 10}


def test_different_ids_of_one_depository_stay_two_accounts():
    assert not sync.same_account("NSDL:abc", "NSDL:def") and sync.same_account("CDSL", "CDSL:x")
    assert not sync.same_account("NSDL", "CDSL:x")


# ---------- review round 3: parsers and connections ----------
def test_a_mail_that_could_not_be_read_yet_is_read_when_sent_again(w, brevo):
    c = w["client"]
    brevo["tok1"] = nsdl()
    body = brevo_body([address_of(c)], [("cas.pdf", "tok1")], mid="same")
    post(c, body)
    assert state.section(PRO_ID, "inbox")["last"]["status"] == "no_password"
    assert "same" not in (state.section(PRO_ID, "inbox").get("seen") or [])                  # a retryable outcome is not "seen"
    c.put("/connect/inbox/password", headers=PRO, json={"password": PAN})
    post(c, body)                                                                             # the same mail, sent again
    assert state.section(PRO_ID, "inbox")["last"]["status"] == "ok" and {i["symbol"] for i in holdings.load(PRO_ID)["items"]} == {"INFY", "ITC"}
    assert "same" in state.section(PRO_ID, "inbox")["seen"]
    n = len(brevo["calls"])
    post(c, body)
    assert len(brevo["calls"]) == n                                                           # now it is read once


def test_a_mail_with_a_permanent_result_is_marked_seen(w, brevo):
    c = w["client"]
    c.put("/connect/inbox/password", headers=PRO, json={"password": PAN})
    brevo["t"] = b"%PDF-1.4 junk"
    post(c, brevo_body([address_of(c)], [("x.pdf", "t")], mid="junk"))
    assert state.section(PRO_ID, "inbox")["last"]["status"] == "not_a_statement" and "junk" in state.section(PRO_ID, "inbox")["seen"]


def ais_line(**kw):
    return {"d": "2025-06-12", "sym": "ALPHA", "name": "Alpha Industries Ltd", "amount": 1200.0, "tds": None, "cur": "INR", "src": "AIS", "isin": "", **kw}


def test_confirmed_ais_lines_must_be_numbers_and_always_keep_their_source(w, on):
    c = w["client"]
    for bad in ({"amount": "lots"}, {"tds": "abc"}, {"amount": None}, {"amount": True}, {"amount": "-5"}, {"tds": "1e999"}):
        r = c.post("/connect/docs/confirm", headers=PRO, json={"kind": "ais", "figures": {"fy": 2025, "tds": 5}, "apply_tds": True, "lines": [ais_line(**bad)]})
        assert r.status_code == 400, bad
    assert divs.load(PRO_ID)["rows"] == [] and adv.load(PRO_ID)["years"].get(2025) is None          # nothing was saved
    sent = ais_line(amount="1,200.50", tds="120", src="statement", cur="USD", isin="INE000A01010")
    assert c.post("/connect/docs/confirm", headers=PRO, json={"kind": "ais", "figures": {"fy": 2025}, "lines": [sent]}).status_code == 200
    got = divs.load(PRO_ID)["rows"]
    assert [(r["amount"], r["tds"], r["src"], r["cur"], r["isin"]) for r in got] == [(1200.5, 120.0, "AIS", "INR", "")]


def test_ais_lines_do_not_add_to_a_year_the_brokers_sheet_covers(w, on):
    c = w["client"]
    divs.add(PRO_ID, [{**ais_line(sym="ALPHA", src="statement")}], "tax.xlsx", "statement")
    c.post("/connect/docs/confirm", headers=PRO, json={"kind": "ais", "figures": {"fy": 2025}, "lines": [ais_line(sym="ALPHA INDUSTRIES LTD")]})
    assert len(divs.load(PRO_ID)["rows"]) == 2                                                    # both kept, with their sources
    y = next(y for y in c.get("/money/dividends", headers=PRO).json()["years"] if y["fy"] == 2025)
    assert y["total"] == 1200.0 and y["ais_set_aside"] == 1 and "AIS" in y["ais_note"]


def test_a_zerodha_read_without_holdings_keeps_what_was_read_before(w, kite):
    c = w["client"]
    kite_login(c)
    before = {i["symbol"] for i in holdings.load("u-admin")["items"]}
    assert before >= {"INFY", "ITC", "TCS"}
    FakeKite.holdings_rows = []                                                                    # the holdings call answered with nothing
    FakeKite.positions_rows = [{"tradingsymbol": "TCS", "exchange": "NSE", "product": "CNC", "quantity": 4, "average_price": 3400.0}]
    assert c.post("/connect/kite/refresh", headers=ADMIN).status_code == 200
    assert {i["symbol"] for i in holdings.load("u-admin")["items"]} == before                       # today's position alone took nothing out
    assert "no holdings" in state.section("u-admin", "kite")["detail"]


def test_deleting_everything_deletes_a_waiting_zerodha_login_too(w, kite, monkeypatch):
    monkeypatch.setattr(settings, "KITE_MULTIUSER_APPROVED", True)
    c = w["client"]
    kite_back(c, kite_state(c, PRO))                                                               # finished at Zerodha, not yet confirmed
    other = kite_state(c, BASIC)
    kite_back(c, other)
    assert len(db.all_settings_with_prefix(kite_user.PENDING)) == 2
    assert c.delete("/connect", headers=PRO).json() == {"deleted": True}
    left = [db.json_value(v, {}).get("uid") for _, v in db.all_settings_with_prefix(kite_user.PENDING)]
    assert left == [BASIC_ID]                                                                      # theirs only


FLEX_LEVELS = """<FlexQueryResponse><FlexStatements><FlexStatement>
<OpenPositions>
<OpenPosition assetCategory="STK" symbol="AAPL" currency="USD" position="10" costBasisPrice="150" levelOfDetail="SUMMARY"/>
<OpenPosition assetCategory="STK" symbol="AAPL" currency="USD" position="4" costBasisPrice="140" levelOfDetail="LOT"/>
<OpenPosition assetCategory="STK" symbol="AAPL" currency="USD" position="6" costBasisPrice="156.6667" levelOfDetail="LOT"/>
</OpenPositions>
<Trades>
<Trade assetCategory="STK" symbol="AAPL" currency="USD" buySell="BUY" quantity="10" tradePrice="150" tradeDate="20260105" dateTime="20260105;103000" tradeID="T1" levelOfDetail="EXECUTION" openCloseIndicator="O"/>
<Trade assetCategory="STK" symbol="AAPL" currency="USD" buySell="SELL" quantity="-10" tradePrice="180" tradeDate="20260210" dateTime="20260210;143000" tradeID="T2" levelOfDetail="EXECUTION" openCloseIndicator="C"/>
<Trade assetCategory="STK" symbol="AAPL" currency="USD" buySell="SELL" quantity="-10" tradePrice="180" tradeDate="20260210" dateTime="20260210;143000" tradeID="T2" levelOfDetail="CLOSED_LOT" openDateTime="20260105;103000"/>
<Trade assetCategory="STK" symbol="TSLA" currency="USD" buySell="SELL" quantity="-5" tradePrice="200" tradeDate="20260120" dateTime="20260120;143000" tradeID="T4" levelOfDetail="EXECUTION" openCloseIndicator="C"/>
<Trade assetCategory="STK" symbol="TSLA" currency="USD" buySell="BUY" quantity="5" tradePrice="180" tradeDate="20260220" dateTime="20260220;143000" tradeID="T5" levelOfDetail="EXECUTION" openCloseIndicator="O"/>
</Trades></FlexStatement></FlexStatements></FlexQueryResponse>"""


def test_ibkr_counts_each_position_and_trade_once_whatever_the_levels_of_detail(w, monkeypatch, on):
    monkeypatch.setattr(ibkr, "transport", flex_transport(FLEX_LEVELS))
    monkeypatch.setattr(ibkr, "sleep", lambda s: None)
    monkeypatch.setattr(sync.deps, "us_find", lambda s: {"symbol": s, "name": s})
    r = connect_ibkr(w["client"])
    assert r.status_code == 200, r.text
    assert {i["symbol"]: i["qty"] for i in holdings.load(PRO_ID)["items"]} == {"AAPL": 10}
    trades = [m for m in journal.load(PRO_ID)["manual"] if m.get("via") == "ibkr"]
    assert [(t["sym"], t["qty"], t["side"]) for t in trades] == [("AAPL", 10.0, "long")]            # TSLA's sale before the window is no short


# ---------- review rev5a ----------
def test_a_days_delivery_trades_in_a_held_stock_count():
    """B9: today's net delivery (CNC) position is added to a held stock's quantity (a sale makes it negative), a stock
    whose total comes to 0 or less is left out, and intraday and F&O positions are never holdings."""
    held = [{"tradingsymbol": "INFY", "exchange": "NSE", "isin": "INE009A01021", "quantity": 10, "t1_quantity": 0, "average_price": 1400.0},
            {"tradingsymbol": "TCS", "exchange": "NSE", "isin": "INE467B01029", "quantity": 5, "t1_quantity": 0, "average_price": 3000.0},
            {"tradingsymbol": "ITC", "exchange": "NSE", "isin": "INE154A01025", "quantity": 20, "t1_quantity": 0, "average_price": 400.0}]
    pos = [{"tradingsymbol": "INFY", "exchange": "NSE", "product": "CNC", "quantity": 5, "average_price": 1500.0},     # bought more
           {"tradingsymbol": "TCS", "exchange": "NSE", "product": "CNC", "quantity": -5, "average_price": 3100.0},     # sold all
           {"tradingsymbol": "ITC", "exchange": "NSE", "product": "CNC", "quantity": -4, "average_price": 410.0},      # sold some
           {"tradingsymbol": "ITC", "exchange": "NSE", "product": "MIS", "quantity": 100, "average_price": 405.0},     # intraday
           {"tradingsymbol": "SBIN", "exchange": "NSE", "product": "NRML", "quantity": 50, "average_price": 800.0},
           {"tradingsymbol": "LT", "exchange": "NSE", "product": "CNC", "quantity": 2, "average_price": 3500.0}]       # new today
    rows = {r["symbol"]: r for r in kite_user.rows_from(held, pos)}
    assert set(rows) == {"INFY", "ITC", "LT"}
    assert rows["INFY"]["qty"] == 15 and rows["INFY"]["avg"] == pytest.approx((10 * 1400 + 5 * 1500) / 15)
    assert (rows["ITC"]["qty"], rows["ITC"]["avg"]) == (16, 400.0) and (rows["LT"]["qty"], rows["LT"]["avg"]) == (2, 3500.0)


def test_an_epf_passbook_of_two_years_is_its_latest_balance():
    """Item c: a passbook with a closing line for each of two years is the later one's balance, not their sum; two member
    ids still add up, each at its latest."""
    two_years = "\n".join(["Member Id: XXXX0000000001", "Closing Balance as on 31/03/2025 1,00,000 80,000 30,000",
                           "Closing Balance as on 31/03/2026 1,50,000 1,20,000 40,000"])
    assert docs.read_epf(two_years) == {"balance": 270000.0, "as_of": "2026-03-31", "passbooks": 1}
    got = docs.read_epf(two_years + "\nMember Id: XXXX0000000002\nClosing Balance as on 31/03/2024 20,000.50 20,000 0")
    assert got["balance"] == 310000.5 and got["as_of"] == "2026-03-31"
    assert docs.read_epf("Closing Balance as on 31/03/2025 10 20 0\nClosing Balance as on 31/03/2026 30 40 0")["balance"] == 70
