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
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from cryptography.fernet import Fernet
from reportlab.pdfgen import canvas

from app import db, holdings, journal, money_mf, money_networth, money_advance_tax as adv, money_dividends as divs
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
    sync.sync_holdings(profile, [], "kite", "Zerodha Kite")                       # sold everything at the broker
    assert "INFY" not in {i["symbol"] for i in holdings.load(PRO_ID)["items"]}


def test_a_sync_keeps_the_average_price_the_user_has(w, on):
    profile = sync.profile_for(PRO_ID)
    sync.sync_holdings(profile, [{"symbol": "ITC", "isin": "INE154A01025", "name": "ITC", "qty": 5.0, "avg": 380.0}], "kite", "Zerodha Kite")
    sync.sync_holdings(profile, [{"symbol": "ITC", "isin": "INE154A01025", "name": "ITC", "qty": 8.0, "avg": None}], "kite", "Zerodha Kite")
    it = holdings.load(PRO_ID)["items"][0]
    assert it["qty"] == 8 and it["avg"] == 380.0


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
    before = set(os.listdir("/tmp"))
    post(c, brevo_body([address_of(c)], [("cas.pdf", "tok1")]))
    assert set(os.listdir("/tmp")) == before
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


def test_reminder_goes_out_once(w, on, monkeypatch):
    c = w["client"]
    address_of(c)
    sent = []
    monkeypatch.setattr(jobs.alerts, "notify", lambda profile, subject, text, background=True, url="": sent.append((profile["id"], subject, url)) or ["push"])
    later = datetime.now(timezone.utc) + timedelta(days=41)
    assert jobs.run_reminders(later) == 1 and jobs.run_reminders(later) == 0
    assert sent == [(PRO_ID, jobs.REMINDER_SUBJECT, "/settings#accounts")]
    assert jobs.run_reminders(datetime.now(timezone.utc)) == 0


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


def kite_login(c, headers=ADMIN, request_token="good-request-token", path="/connect/kite/callback"):
    url = c.get("/connect/kite/login", headers=headers).json()["url"]
    st = [p for p in url.split("%3D", 1)[1:]][0] if "%3D" in url else ""
    from urllib.parse import unquote
    st = unquote(url.split("redirect_params=")[1]).split("state=", 1)[1]
    return c.get(path, params={"request_token": request_token, "status": "success", "state": st}, follow_redirects=False)


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
    assert items["INFY"]["qty"] == 10 and items["INFY"]["avg"] == 1400.0                     # settled and T+1
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


def test_ibkr_disconnect_deletes_the_token_and_keeps_what_was_read(w, flex):
    c = w["client"]
    connect_ibkr(c)
    v = c.delete("/connect/ibkr", headers=PRO).json()
    assert v["ibkr"]["connected"] is False and db.get_setting(state.KEY + PRO_ID) is None
    assert len(holdings.load(PRO_ID)["items"]) == 2


def test_ibkr_fifo_pairs_shorts_and_partial_fills():
    fs = [{"id": "a", "sym": "X", "side": "S", "qty": 10, "price": 50.0, "d": "2026-01-01", "t": "10:00:00", "fee": 1.0},
          {"id": "b", "sym": "X", "side": "B", "qty": 4, "price": 40.0, "d": "2026-01-02", "t": "10:00:00", "fee": 0.4},
          {"id": "c", "sym": "X", "side": "B", "qty": 6, "price": 45.0, "d": "2026-01-03", "t": "10:00:00", "fee": 0.6}]
    got = ibkr.closed_trades(fs)
    assert [(t["side"], t["qty"], t["entry"], t["exit"]) for t in got] == [("short", 4.0, 50.0, 40.0), ("short", 6.0, 50.0, 45.0)]
    assert sum(t["charges"] for t in got) == pytest.approx(2.0)
    assert len({t["id"] for t in got}) == 2 and got == ibkr.closed_trades(fs)             # ids don't change between reads


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
