"""Security review of 7 Oct 2026. Each test here failed before its fix: a PDF that unpacks to gigabytes, strangers using up the
statement inbox's webhook allowance, a path made from a mail's attachment token, a TER workbook with a DTD, a replayed
payment event with its id header dropped, secrets in the admin's list of crashes, unbounded confirmed figures, and the API's
route map open to everyone in production."""
import io
import json
import subprocess
import time
import zipfile
import zlib
from types import SimpleNamespace

import httpx
import pytest

from app import billing, main, money_mf, money_mf_ter
from app.config import api_docs_enabled, settings
from app.connect import inbound, pdfsandbox, state, statements
from tests.test_connect import PRO, PRO_ID, SECRET, b64, brevo, on, post, w  # noqa: F401  (fixtures)


# ---------- a PDF that unpacks to gigabytes ----------
def bomb_pdf(megabytes: int) -> bytes:
    """A small PDF whose one page's content stream is `megabytes` of zeros once unpacked."""
    c = zlib.compressobj(1)
    stream = b"".join(c.compress(b"\0" * 1024 * 1024) for _ in range(megabytes)) + c.flush()
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 600 800] /Contents 4 0 R /Resources << >> >>",
            b"<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(stream) + stream + b"\nendstream"]
    out, offs = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    x = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1) + b"".join(b"%010d 00000 n \n" % o for o in offs)
    return out + b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, x)


def test_a_pdf_that_unpacks_to_gigabytes_stops_a_child_process_not_the_server(monkeypatch):
    monkeypatch.setattr(pdfsandbox, "MEMORY_LIMIT", 512 * 1024 * 1024)
    pdf = bomb_pdf(800)
    assert len(pdf) < 5 * 1024 * 1024                              # inside the upload limit
    t = time.time()
    with pytest.raises(statements.StatementError) as e:
        statements.read(pdf, [""])
    assert e.value.code == "too_complex" and time.time() - t < 60
    with pytest.raises(money_mf.FileError, match="too large or complex"):
        money_mf.parse_cas(pdf, "")


def test_the_pdf_child_has_none_of_the_servers_secrets(monkeypatch):
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "service-key-should-not-travel")
    monkeypatch.setenv("CONNECT_SECRET_KEY", "vault-key-should-not-travel")
    seen = {}
    real = subprocess.Popen

    def spy(args, **kw):
        seen.update(kw)
        return real(args, **kw)
    monkeypatch.setattr(pdfsandbox.subprocess, "Popen", spy)
    with pytest.raises(pdfsandbox.SandboxError):
        pdfsandbox.run(b"%PDF-1.4 nothing", "pw-should-not-be-in-argv")
    assert "service-key-should-not-travel" not in json.dumps(seen["env"]) and "vault-key-should-not-travel" not in json.dumps(seen["env"])
    assert set(seen["env"]) <= {"PATH", "PYTHONIOENCODING"}
    assert seen["preexec_fn"] is not None and seen["stdin"] == subprocess.PIPE


# ---------- the statement inbox's webhook ----------
def test_strangers_cannot_use_up_the_webhooks_allowance(w, brevo, monkeypatch):
    c = w["client"]
    monkeypatch.setattr(inbound, "MAX_POSTS_PER_MINUTE", 5)
    for _ in range(12):
        assert post(c, {"items": []}, k="wrong-secret").status_code == 401
    assert post(c, {"items": []}).status_code == 200               # the real mail service still gets through
    for _ in range(5):
        post(c, {"items": []})
    assert post(c, {"items": []}).status_code == 429               # the allowance itself still holds for authentic posts


def test_an_attachment_token_cannot_walk_to_another_path_on_the_mail_service(monkeypatch, on):
    seen = []

    def handler(req: httpx.Request):
        seen.append(req.url.raw_path.decode())
        return httpx.Response(200, content=b"%PDF-1.4")
    ad = inbound.BrevoAdapter(transport=httpx.MockTransport(handler))
    ad._fetch("../../account?x=1#")
    assert seen == ["/v3/inbound/attachments/..%2F..%2Faccount%3Fx%3D1%23"]


def test_an_attachment_the_mail_understates_is_still_capped(monkeypatch, on):
    monkeypatch.setattr(statements, "MAX_PDF", 1000)
    ad = inbound.BrevoAdapter(transport=httpx.MockTransport(lambda req: httpx.Response(200, content=b"x" * 5000)))
    with pytest.raises(inbound.BadRequest):
        ad._fetch("tok")


# ---------- the TER workbook ----------
def workbook(sheet: bytes) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr("xl/worksheets/sheet1.xml", sheet)
    return out.getvalue()


def test_a_ter_workbook_with_a_document_type_declaration_is_refused():
    evil = (b'<?xml version="1.0"?><!DOCTYPE worksheet [<!ENTITY a "AAAA">]><worksheet><sheetData>'
            b'<row><c r="A1"><v>&a;</v></c></row></sheetData></worksheet>')
    with pytest.raises(ValueError, match="document type"):
        list(money_mf_ter._excel_rows(workbook(evil)))
    fine = b'<?xml version="1.0"?><worksheet><sheetData><row><c r="A1"><v>Scheme Name</v></c><c r="B1"><v>x</v></c></row></sheetData></worksheet>'
    assert list(money_mf_ter._excel_rows(workbook(fine))) == [["Scheme Name", "x"]]


# ---------- the payment webhook ----------
def test_a_signed_payment_event_replayed_without_its_id_header_does_nothing(monkeypatch):
    mem = {}
    monkeypatch.setattr(billing.db, "get_setting", lambda k: mem.get(k))
    monkeypatch.setattr(billing.db, "set_setting", lambda k, v: mem.__setitem__(k, v))
    monkeypatch.setattr(settings, "RAZORPAY_WEBHOOK_SECRET", "w")
    monkeypatch.setattr(billing, "_client", SimpleNamespace(utility=SimpleNamespace(verify_webhook_signature=lambda *a: True)))
    acted = []
    monkeypatch.setattr(billing, "_act", lambda event: acted.append(event["event"]))
    body = json.dumps({"event": "subscription.charged", "payload": {}}).encode()
    billing.handle_webhook(body, "sig", "evt_1")
    billing.handle_webhook(body, "sig")                            # the header dropped: a different key, handled once more
    billing.handle_webhook(body, "sig")                            # and now the body itself is known
    billing.handle_webhook(body, "sig", "evt_1")                   # the id is known too
    assert acted == ["subscription.charged", "subscription.charged"]


# ---------- the admin's list of crashes ----------
def test_a_crash_is_listed_without_the_secret_its_error_carried(w, monkeypatch):
    def boom():
        raise RuntimeError("GET https://api.example.test/v1?api_key=SUPERSECRETVALUE123&x=1 failed with token=ANOTHERSECRET456")
    main.app.add_api_route("/_boom_test", boom, methods=["GET"])
    try:
        from fastapi.testclient import TestClient
        r = TestClient(main.app, raise_server_exceptions=False).get("/_boom_test")
    finally:
        main.app.router.routes[:] = [x for x in main.app.router.routes if getattr(x, "path", "") != "/_boom_test"]
    assert r.status_code == 500
    listed = json.dumps(main.RECENT_ERRORS[-1])
    assert "SUPERSECRETVALUE123" not in listed and "ANOTHERSECRET456" not in listed and "RuntimeError" in listed


# ---------- confirmed figures ----------
def test_confirmed_figures_stay_small_and_dates_are_dates(w, on):
    c = w["client"]
    huge = {"kind": "epf", "figures": {"balance": "1000", "as_of": "x" * 100_000}}
    assert c.post("/connect/docs/confirm", headers=PRO, json=huge).status_code == 422
    many = {"kind": "epf", "figures": {f"k{i}": 1 for i in range(40)} | {"balance": 1000}}
    assert c.post("/connect/docs/confirm", headers=PRO, json=many).status_code == 422
    lines = {"kind": "ais", "figures": {"fy": "2025", "dividend": 10}, "lines": [{"d": "2025-06-01", "name": "y" * 5000, "amount": 1}]}
    assert c.post("/connect/docs/confirm", headers=PRO, json=lines).status_code == 422
    ok = c.post("/connect/docs/confirm", headers=PRO, json={"kind": "epf", "figures": {"balance": 1000, "as_of": "<script>alert(1)</script>"}})
    assert ok.status_code == 200
    assert state.section(PRO_ID, "docs")["epf"]["as_of"] is None and "script" not in json.dumps(state.section(PRO_ID, "docs"))
    ok = c.post("/connect/docs/confirm", headers=PRO, json={"kind": "epf", "figures": {"balance": 1000, "as_of": "2026-03-31"}})
    assert state.section(PRO_ID, "docs")["epf"]["as_of"] == "2026-03-31"


# ---------- the API's route map ----------
def test_the_apis_docs_and_route_map_are_off_on_railway_unless_asked_for():
    assert api_docs_enabled({}) is True                                           # a developer's machine
    assert api_docs_enabled({"RAILWAY_ENVIRONMENT": "production"}) is False
    assert api_docs_enabled({"RAILWAY_PUBLIC_DOMAIN": "x.up.railway.app"}) is False
    assert api_docs_enabled({"RAILWAY_ENVIRONMENT": "production", "API_DOCS": "true"}) is True
