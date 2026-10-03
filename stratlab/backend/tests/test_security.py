"""Security sweep: every route refuses callers it shouldn't serve, users can't reach each other's things, and hostile
input can't escape into HTML, links or other hosts."""
import json

import pytest
from fastapi.routing import APIRoute

from app import main
from tests import world as W

PUBLIC = {"/health", "/plans", "/pricing", "/markets", "/public/v/{token}", "/v/{token}.png", "/v/{token}", "/billing/webhook",
          "/admin/kite/callback", "/unsubscribe", "/email/confirm",
          "/stocks/{region}/{symbol}", "/robots.txt", "/sitemap.xml", "/sitemaps/{name}.xml"}   # public company pages, for search engines


def _deps(d) -> set:
    out = set()
    for x in d.dependencies:
        out.add(getattr(x.call, "__name__", "")); out |= _deps(x)
    return out


def routes():
    for r in main.app.routes:
        # the app's own routes (other tests add throwaway ones, e.g. a route that crashes on purpose)
        if isinstance(r, APIRoute) and getattr(r.endpoint, "__module__", "").startswith("app."):
            for m in r.methods - {"HEAD", "OPTIONS"}:
                yield m, r.path, _deps(r.dependant)


def fill(path: str) -> str:
    for k, v in {"{nid}": "nb-x", "{version}": "1", "{sid}": "s-x", "{token}": "t-x", "{symbol}": "RELIANCE", "{region}": "IN",
                 "{user_id}": "u-free", "{year}": "2026-27", "{n}": "1", "{entry_id}": "e-x", "{inst_id}": "IN:RELIANCE",
                 "{key}": "k", "{id}": "x"}.items():
        path = path.replace(k, v)
    return path.replace("{", "").replace("}", "")


def test_only_the_intended_routes_are_open_without_signing_in():
    open_routes = {p for _, p, d in routes() if not d & {"current_profile", "current_user", "admin_profile"}}
    assert open_routes == PUBLIC, open_routes ^ PUBLIC


@pytest.fixture(scope="module")
def client():
    mp = pytest.MonkeyPatch()
    w = W.build(mp)
    yield w["client"]
    w["close"]()
    mp.undo()


def test_every_private_route_refuses_strangers_and_admin_routes_refuse_users(client):
    for method, path, deps in routes():
        if path in PUBLIC:
            continue
        url = fill(path)
        for token in (None, "garbage-token", "Bearer x.y.z"):
            h = {} if token is None else {"Authorization": token if token.startswith("Bearer") else f"Bearer {token}"}
            r = client.request(method, url, headers=h, json={})
            assert r.status_code == 401, f"{method} {path} with {token!r}: {r.status_code} {r.text[:120]}"
        if "admin_profile" in deps:
            for tok in ("free-token", "pro-token"):
                r = client.request(method, url, headers=W.headers(tok), json={})
                assert r.status_code == 403, f"{method} {path} as {tok}: {r.status_code} {r.text[:120]}"


def test_users_cannot_reach_each_others_notebooks_sessions_or_invoices(client):
    a, b = W.headers("pro-token"), W.headers("basic-token")
    nb = client.post("/notebooks", headers=a, json={"name": "Mine", "market": "IN"})
    assert nb.status_code == 200, nb.text
    nid = nb.json()["id"]
    for method, url, body in [("GET", f"/notebooks/{nid}", None), ("PUT", f"/notebooks/{nid}", {"name": "Stolen"}),
                              ("DELETE", f"/notebooks/{nid}", None), ("POST", f"/notebooks/{nid}/duplicate", {}),
                              ("POST", f"/notebooks/{nid}/experiments", {}), ("DELETE", f"/notebooks/{nid}/experiments/1", None),
                              ("POST", f"/notebooks/{nid}/experiments/1/share", {}), ("POST", f"/notebooks/{nid}/live", {})]:
        r = client.request(method, url, headers=b, json=body)
        assert r.status_code in (404, 403, 422), f"{method} {url} as another user: {r.status_code} {r.text[:120]}"
    assert client.get(f"/notebooks/{nid}", headers=a).json()["name"] == "Mine"          # untouched
    assert client.get("/billing/invoices/2026-27/1", headers=b).status_code in (403, 404)


def test_invoice_page_escapes_buyer_text_and_blocks_scripts():
    from app import invoices
    inv = {"number": "SL/2026-27/0001", "date": "2026-10-03", "payment_id": "pay_<x>", "seller": {"legal_name": "<b>S</b>"},
           "buyer": {"name": "<script>alert(1)</script>", "address": "\"><img src=x onerror=alert(1)>", "email": "a@b.c"},
           "item": {"description": "StratLab Pro", "sac": "998431", "taxable": 1.0}, "taxes": [], "total": 1.18,
           "currency": "INR", "place_of_supply": "Delhi", "note": "<i>n</i>", "supply": "Intra-state"}
    page = invoices.html(inv)
    assert "<script>alert" not in page and "<img src=x" not in page and "&lt;script&gt;" in page
    assert "default-src 'none'" in page and "script-src 'sha256-" in page


def test_documents_are_only_fetched_from_public_https_hosts_the_filing_names():
    from app import docs
    for url in ["http://nsearchives.nseindia.com/a.pdf", "https://169.254.169.254/latest/meta-data.pdf",
                "https://localhost/a.pdf", "https://nsearchives.nseindia.com.evil.com/a.pdf", "file:///etc/passwd",
                "https://evil.com/a.pdf", "javascript:alert(1)//.pdf"]:
        assert not docs.allowed(url), url
    for host in ("127.0.0.1", "10.1.2.3", "192.168.0.1", "169.254.169.254", "::1", "0.0.0.0"):
        assert not docs.public_host(host), host


def test_public_preview_escapes_the_shared_name():
    from app import public
    page = public.preview_html("tok", {"name": "\"><script>alert(1)</script>", "verdict": {"headline": "<b>x</b>"},
                                       "instrument": {"symbol": "<i>"}}, False)
    assert "<script>alert" not in page and "&lt;script&gt;" in page


def test_an_email_signup_with_the_admins_address_is_not_admin(client):
    assert client.get("/admin/overview", headers=W.headers("admin-token")).status_code == 200
    r = client.get("/admin/overview", headers=W.headers("email-signup-admin-token"))
    assert r.status_code == 403 and r.json()["detail"]["code"] == "not_admin"


def test_a_made_up_token_costs_one_sign_in_lookup_not_one_per_request(client, monkeypatch):
    from app import auth, db
    calls = []
    real = db.sb().auth.get_user
    monkeypatch.setattr(db.sb().auth, "get_user", lambda t: calls.append(t) or real(t))
    for _ in range(5):
        assert client.get("/me", headers={"Authorization": "Bearer made-up-123"}).status_code == 401
    assert calls == ["made-up-123"]
    auth._rejected.clear()
