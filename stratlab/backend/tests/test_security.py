"""Security sweep: every route refuses callers it shouldn't serve, users can't reach each other's things, and hostile
input can't escape into HTML, links or other hosts."""

import pytest
from fastapi.routing import APIRoute

from app import guard, main
from tests import world as W

PUBLIC = {"/health", "/version", "/plans", "/pricing", "/markets", "/public/v/{token}", "/v/{token}.png", "/v/{token}", "/c/{card}.png", "/c/{card}", "/billing/webhook",
          "/admin/kite/callback", "/unsubscribe", "/email/confirm",
          "/stocks/{region}/{symbol}", "/stocks/{region}/{symbol}/prices.json", "/stocks/chart.js",       # a company's chart: its script and its closes (PUB-1)
          "/robots.txt", "/sitemap.xml", "/sitemaps/{name}.xml",   # public company pages, for search engines
          "/stocks", "/stocks/", "/stocks/{region}", "/stocks/{region}/", "/stocks/{region}/{symbol}/",   # their search, and one address each
          # the A-Z and index lists that link every company page (SEO-1)
          "/stocks/{region}/browse/{letter}", "/stocks/{region}/browse/{letter}/{page}", "/stocks/{region}/index/{slug}", "/stocks/{region}/index/{slug}/{page}",
          "/public/company/{region}/{symbol}",      # a company's name and public page, for "Sign in to see …"
          "/public/library", "/public/library/{eid}",   # StratLab's own library strategies, read only, for visitors
          "/public/business",                       # the seller's name, address and email, for the policy pages
          # a Market Brief's headline from the plain-text email: forwards only to a link stored in that brief (R13-003)
          "/news-link/{iid}/{n}"}


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
    mp.setattr(guard, "BAD_TOKENS_PER_MINUTE", 10**6)     # this test sends a bad token to every route on purpose
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


def test_a_profile_still_holding_the_admins_signup_address_is_not_admin(client):
    """The profile keeps the address from sign-up. If the account now signs in with another address (changed after
    signing up), the old one in the profile proves nothing."""
    from app import db
    row = next(r for r in db.sb().tables["profiles"] if r["id"] == "u-pro")
    row["email"] = "owner@example.com"
    db.forget_profile("u-pro")
    try:
        r = client.get("/admin/overview", headers=W.headers("pro-token"))
        assert r.status_code == 403 and r.json()["detail"]["code"] == "not_admin"
    finally:
        row["email"] = "pro@example.com"
        db.forget_profile("u-pro")


def test_newsletter_links_are_only_web_addresses():
    from app.newsletter import write
    issue = {"id": "market.IN.2026-10-02", "subject": "S", "summary": "", "sections": [{"title": "Headlines", "items": [
        {"text": "<b>x</b>", "url": "javascript:alert(document.cookie)", "lines": [
            {"text": "y", "url": "data:text/html,<script>alert(1)</script>"}, {"text": "ok", "url": "https://example.com/a?b=1&c=2"}]}]}]}
    html, _ = write.render(issue)
    assert "javascript:" not in html and "data:text" not in html and "&lt;b&gt;x&lt;/b&gt;" in html
    assert 'href="https://example.com/a?b=1&amp;c=2"' in html


def test_email_subjects_and_headers_cannot_carry_line_breaks(monkeypatch):
    from app import alerts
    from app.config import settings
    sent = []

    class SMTP:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def starttls(self): pass
        def login(self, *a): pass
        def send_message(self, msg): sent.append(msg)
    for k in ("BREVO_API_KEY", "RESEND_API_KEY"):
        monkeypatch.setattr(settings, k, "")
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.example.com")
    monkeypatch.setattr(settings, "SMTP_USER", "bot@example.com")
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "pw")
    monkeypatch.setattr(settings, "SMTP_PORT", 587)
    monkeypatch.setattr(alerts.smtplib, "SMTP", SMTP)
    alerts.send_email("a@example.com", "Market Brief\r\nBcc: victim@example.com", "body",
                      headers={"List-Unsubscribe": "<https://x/u>\r\nBcc: v@example.com"})
    msg = sent[0]
    assert msg["Bcc"] is None and msg["Subject"] == "Market Brief Bcc: victim@example.com"
    assert "\n" not in msg["List-Unsubscribe"]


def test_kite_callback_with_an_odd_state_is_refused_not_a_crash(client, monkeypatch):
    from app import main
    monkeypatch.setattr(main.kite, "login_state", "expected-state")
    r = client.get("/admin/kite/callback", params={"status": "success", "request_token": "t", "state": "é"})
    assert r.status_code == 403


def test_the_apis_html_pages_run_no_script_and_json_is_left_alone(client):
    from app import guard
    page = client.get("/stocks/in/RELIANCE")
    csp = page.headers["content-security-policy"]
    # a company's page runs one script of the site's own, for its chart, and asks the site for prices: no inline script, no other origin (PUB-1)
    assert page.status_code == 200 and csp == guard.CHART_CSP[1].decode()
    assert "script-src 'self';" in csp and "connect-src 'self';" in csp and "'unsafe-inline'" not in csp.split("style-src")[0]
    assert "default-src 'none'" in csp and "frame-ancestors 'none'" in csp
    other = client.get("/stocks").headers["content-security-policy"]           # every other page of the API stays script-free
    assert other == guard.HTML_CSP[1].decode() and "script-src" not in other
    assert "content-security-policy" not in client.get("/plans").headers                     # JSON needs none
    gone = client.get("/unsubscribe", params={"t": "bad"})
    assert "form-action 'self'" in gone.headers.get("content-security-policy", "")           # its button still posts


def test_an_invoice_keeps_its_own_policy_so_its_print_button_works():
    from app import invoices
    page = invoices.html({"number": "SL/2026-27/0001", "date": "2026-10-03", "payment_id": "p", "seller": {},
                          "buyer": {"name": "B", "email": "a@b.c"}, "item": {"description": "StratLab Pro", "sac": "998431", "taxable": 1.0},
                          "taxes": [], "total": 1.0, "currency": "INR", "place_of_supply": "Delhi", "note": "", "supply": "Intra-state"})
    assert invoices.PRINT_HASH in invoices.CSP and invoices.CSP in page


@pytest.mark.parametrize("sym", ["..", ".", "-x", "_A", ".HIDDEN"])
def test_a_ticker_starts_with_a_letter_or_digit(sym):
    """Tickers go into data sources' addresses (/chart/<symbol>): ".." and the like are refused before they get there."""
    from fastapi import HTTPException
    from app.intel import routes as R
    with pytest.raises(HTTPException):
        R.symbol_of(sym)
    for ok in ("M&M", "BAJAJ-AUTO", "BRK.B", "^GSPC", "3MINDIA"):
        assert R.symbol_of(ok) == ok


# ---------- the AI allowance is held while the call runs ----------
def _slow_ai(monkeypatch, delay=0.15, fail=None):
    import time
    # a build that makes a rule: one that makes none is never counted (DP1-001)
    out = {"name": "x", "tf": "1d", "entry": [{"l": {"t": "rsi", "p": 14}, "op": "lt", "r": {"t": "num", "v": 30}}], "exit": [], "risk": {}, "notes": []}

    def write(text, pro):
        time.sleep(delay)
        if fail:
            raise fail
        return dict(out)
    monkeypatch.setattr(main, "write_strategy", write)
    monkeypatch.setattr(main.ai_writer, "check_against_text", lambda o, t: o)


def _burst(client, token, n=25):
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=n) as pool:
        return list(pool.map(lambda _: client.post("/ai/strategy", headers=W.headers(token), json={"text": "buy when rsi is low"}).status_code, range(n)))


def test_parallel_ai_builds_cannot_pass_the_monthly_limit(monkeypatch):
    from app import db
    w = W.build(monkeypatch)
    try:
        _slow_ai(monkeypatch)
        codes = _burst(w["client"], "free-token")
        assert codes.count(200) == 10 and codes.count(429) == 15                       # Free: 10 a month
        assert db.count_usage("u-free", "ai", "2000-01-01T00:00:00+00:00") == 10
    finally:
        w["close"]()


def test_parallel_ai_builds_cannot_pass_the_daily_cap(monkeypatch):
    from app import db
    w = W.build(monkeypatch)
    try:
        _slow_ai(monkeypatch)
        monkeypatch.setattr(main, "AI_BUILDS_PER_DAY", 7)
        codes = _burst(w["client"], "pro-token")
        assert codes.count(200) == 7 and codes.count(429) == 18
        assert db.count_usage("u-pro", "ai", "2000-01-01T00:00:00+00:00") == 7
    finally:
        w["close"]()


def test_a_failed_ai_build_does_not_use_up_the_allowance(monkeypatch):
    from app import db
    from app.ai_providers import AIBusy, AIError
    w = W.build(monkeypatch)
    try:
        c = w["client"]
        _slow_ai(monkeypatch, delay=0, fail=AIError("down"))
        assert [c.post("/ai/strategy", headers=W.headers("free-token"), json={"text": "buy low"}).status_code for _ in range(12)] == [422] * 12
        _slow_ai(monkeypatch, delay=0, fail=AIBusy("busy"))
        assert c.post("/ai/strategy", headers=W.headers("free-token"), json={"text": "buy low"}).status_code == 503
        _slow_ai(monkeypatch, delay=0, fail=ValueError("boom"))
        try:
            c.post("/ai/strategy", headers=W.headers("free-token"), json={"text": "buy low"})
        except ValueError:
            pass
        assert db.count_usage("u-free", "ai", "2000-01-01T00:00:00+00:00") == 0
        _slow_ai(monkeypatch, delay=0)
        assert [c.post("/ai/strategy", headers=W.headers("free-token"), json={"text": "buy low"}).status_code for _ in range(10)] == [200] * 10
        assert c.post("/ai/strategy", headers=W.headers("free-token"), json={"text": "buy low"}).status_code == 429
    finally:
        w["close"]()


def test_parallel_research_reads_cannot_pass_the_daily_cap(monkeypatch):
    import time
    from concurrent.futures import ThreadPoolExecutor
    from app import db
    from app.intel import routes as R
    w = W.build(monkeypatch)
    try:
        monkeypatch.setattr(R, "ai_cap", lambda profile: 3)
        profile = {"id": "u-free"}

        def read(i):
            try:
                return R.ai_call(profile, "t", (i,), 60, False, lambda: (time.sleep(0.1), {"i": i})[1])
            except Exception as e:
                return getattr(e, "status_code", e)
        with ThreadPoolExecutor(max_workers=10) as pool:
            got = list(pool.map(read, range(10)))
        assert sum(isinstance(g, dict) for g in got) == 3 and got.count(429) == 7
        assert db.count_usage("u-free", "research_ai", "2000-01-01T00:00:00+00:00") == 3
        # a read that fails is given back
        from app.ai_providers import AIError

        def bad():
            raise AIError("down")
        before = db.count_usage("u-free", "research_ai", "2000-01-01T00:00:00+00:00")
        monkeypatch.setattr(R, "ai_cap", lambda profile: 5)
        for i in range(6):
            assert getattr(__import__("pytest").raises(Exception, R.ai_call, profile, "t", ("f", i), 60, False, bad).value, "status_code") == 422
        assert db.count_usage("u-free", "research_ai", "2000-01-01T00:00:00+00:00") == before
    finally:
        w["close"]()

from app import ai_providers as _providers
REAL_COMPLETE = _providers.complete               # taken at import: the world swaps in a fake that never caches


def test_a_strategy_answer_from_the_cache_is_not_charged(monkeypatch):
    from app import ai_providers, db
    w = W.build(monkeypatch)
    try:
        calls = []
        out = '{"entry": [{"l": {"t": "price"}, "op": "gt", "r": {"t": "num", "v": 1}}]}'
        monkeypatch.setattr(main.ai_writer, "complete", REAL_COMPLETE)
        monkeypatch.setattr(ai_providers, "_names", lambda task: (["gemini"], []))
        monkeypatch.setattr(ai_providers, "plan", lambda task, need: [("gemini", "m")])
        monkeypatch.setattr(ai_providers.R, "ready", lambda *a, **k: 0)
        monkeypatch.setattr(ai_providers.R, "ask_model", lambda *a, **k: calls.append(1) or out)
        ai_providers.cache.clear()
        c = w["client"]
        body = [c.post("/ai/strategy", headers=W.headers("free-token"), json={"text": "buy when rsi is low"}).json() for _ in range(3)]
        assert len(calls) == 1
        assert [b["usage"]["ai_used"] for b in body] == [1, 1, 1]
        assert db.count_usage("u-free", "ai", "2000-01-01T00:00:00+00:00") == 1
    finally:
        w["close"]()
