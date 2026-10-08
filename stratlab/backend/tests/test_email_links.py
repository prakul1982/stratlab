"""Every link in every email goes somewhere real: a page the frontend routes (with the anchor and the query keys that
page reads), or a route of this API (the address confirmation, the one-click unsubscribe). Built from the frontend's
own source, so a renamed page, a dropped card id or a new email with a made-up path fails here, not in a reader's inbox.

Links to other sites (a filing, a headline) are left alone, but an email never links to the app anywhere but the
public site."""
import re
from functools import lru_cache
from html import unescape
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from app import main  # noqa: F401  (the app imports its modules in a fixed order)
from app import email_kit as kit, email_previews as P, lifecycle
from app.config import settings

SRC = Path(__file__).resolve().parents[2] / "frontend" / "src"
KINDS = list(P.registry())


# ---------- the frontend, read from its source ----------
@lru_cache(maxsize=None)
def routes() -> list[tuple[re.Pattern, str]]:
    """(pattern, page component) for every <Route> in main.tsx and every public legal page. The catch-all "*" isn't
    a page: it sends an unknown address home."""
    main_tsx = (SRC / "main.tsx").read_text()
    out = []
    # a guard that wraps the page (<AdminOnly what="…"><AdminPage /></AdminOnly>) is skipped for the page inside it
    for path, comp in re.findall(r'<Route path="([^"]+)" element=\{<(?:AdminOnly\b[^>]*><)?(\w+)', main_tsx):   # AdminOnly only wraps the page
        if path == "*" or comp == "Navigate":
            continue
        rx = re.sub(r":\w+", r"[^/]+", path.replace("/*", "(?:/.*)?"))
        out.append((re.compile(f"^{rx}$"), comp))
    legal = (SRC / "components" / "LegalLinks.tsx").read_text()
    out += [(re.compile(f"^{re.escape(p)}$"), "LegalPage") for p in re.findall(r'path: "([^"]+)"', legal)]
    assert len(out) > 40, "couldn't read the frontend's routes"
    return out


@lru_cache(maxsize=None)
def component_file(name: str) -> Path | None:
    for f in SRC.rglob("*.tsx"):
        if re.search(rf"export (?:function|const) {name}\b", f.read_text()):
            return f
    return None


def _imports(f: Path) -> list[Path]:
    """The component files a page imports from this repo (one level: the cards a page is made of)."""
    out = []
    for rel in re.findall(r'from "(\.{1,2}/[^"]+)"', f.read_text()):
        for ext in (".tsx", ".ts"):
            p = (f.parent / (rel + ext)).resolve()
            if p.exists():
                out.append(p)
    return out


@lru_cache(maxsize=None)
def page_reads(comp: str) -> tuple[set[str], set[str]]:
    """(anchors, query keys) a page answers to: the ids on it and on the cards it imports, the sections it opens from
    the address's #hash (a Seg's values and their aliases), and the keys it reads with params.get("…")."""
    f = component_file(comp)
    assert f, f"no component {comp} in the frontend"
    files = [f, *_imports(f)]
    anchors, keys = set(), set()
    for x in files:
        src = x.read_text()
        anchors |= set(re.findall(r'\bid="([\w-]+)"', src))
        keys |= set(re.findall(r'\.get\("(\w+)"\)', src))
    src = f.read_text()
    if re.search(r"\b(?:loc|location)\.hash\b", src):
        anchors |= set(re.findall(r'\{ value: "([\w-]+)"', src))
        alias = re.search(r"const ALIAS[^=]*= \{([^}]*)\}", src)
        anchors |= set(re.findall(r"(\w+):", alias.group(1))) if alias else set()
    return anchors, keys


def page_for(path: str) -> str | None:
    return next((comp for rx, comp in routes() if rx.match(path)), None)


# ---------- the API ----------
def api_routes() -> list[re.Pattern]:
    return [re.compile("^" + re.sub(r"\{[^}]+\}", "[^/]+", r.path) + "$") for r in main.app.routes if hasattr(r, "methods")
            and "GET" in r.methods]


@lru_cache(maxsize=None)
def forwarded() -> frozenset[str]:
    """The exact paths the site's host (frontend/vercel.json) forwards to the API."""
    import json
    rewrites = json.loads((SRC.parent / "vercel.json").read_text()).get("rewrites") or []
    return frozenset(r["source"] for r in rewrites if r["destination"].startswith("http") and ":" not in r["source"])


# ---------- the check ----------
def links(html: str, text: str) -> set[str]:
    """Every address in the HTML's links and in the plain text."""
    found = {unescape(h) for h in re.findall(r'href="([^"]+)"', html)}
    found |= {u.rstrip(").,") for u in re.findall(r"https?://[^\s<>\"']+", text)}
    return found


def problem(url: str) -> str | None:
    """Why this link doesn't resolve, or None when it does."""
    site, api = settings.PUBLIC_SITE_URL.rstrip("/"), settings.PUBLIC_API_URL.rstrip("/")
    u = urlsplit(url)
    origin = f"{u.scheme}://{u.netloc}"
    if url == kit.UNSUBSCRIBE:
        return "the unsubscribe placeholder was never filled"
    if origin == api and api != site:
        return None if any(rx.match(u.path) for rx in api_routes()) else f"no API route {u.path}"
    if origin != site:
        own = {o.rstrip("/") for o in settings.FRONTEND_ORIGINS}
        return f"links to {origin}, not the public site" if origin in own else None    # another site: a source
    if u.path in forwarded():            # the site sends it on to the API: it must be an API page
        return None if any(rx.match(u.path) for rx in api_routes()) else f"no API route {u.path}"
    comp = page_for(u.path or "/")
    if not comp:
        return f"the app has no page {u.path} (an unknown address just goes home)"
    anchors, keys = page_reads(comp)
    if u.fragment and u.fragment not in anchors:
        return f"{comp} has no #{u.fragment}"
    missing = [k for k in parse_qs(u.query) if k not in keys]
    return f"{comp} doesn't read ?{', '.join(missing)}" if missing else None


def test_the_check_itself_catches_what_reviewers_found():
    site = settings.PUBLIC_SITE_URL
    assert problem(f"{site}/news/market.IN.2026-10-07")                 # not a page: it redirected home
    assert problem(f"{site}/account#newsletters") and problem(f"{site}/account#invite")
    assert problem(f"{site}/news?issue=x&tabs=IN")                     # a query key the page doesn't read
    assert problem(f"{site}/settings#nope")
    assert not problem(f"{site}/news?tab=US&issue=market.US.2026-10-07")
    assert not problem(f"{site}/settings#newsletters") and not problem(f"{site}/settings#emails")
    assert not problem(f"{site}/research/IN/TCS") and not problem(f"{site}/money/tax-tools?tab=advance")
    assert not problem(f"{settings.PUBLIC_API_URL}/email/confirm?t=x") and not problem("https://example.com/filing.pdf")


@pytest.mark.parametrize("kind", KINDS)
def test_every_link_in_every_email_resolves(kind):
    d = P.describe(kind, True)            # the unsubscribe link as sent is checked below
    found = links(d["html"], d["text"])
    assert found, kind
    bad = {u: problem(u) for u in found if problem(u)}
    assert not bad, f"{kind}: {bad}"


@pytest.mark.parametrize("what", ["market_in", "my_stocks", "tips", "screens", "advance_tax"])
def test_the_unsubscribe_link_as_sent_is_an_api_route(what):
    html, text = kit.render("T", [kit.para("x")], kit.Footer(why="why", unsubscribe="Unsubscribe"))
    _, t, headers = kit.finish(html, text, "u-1", what)
    unsub = re.search(r"https?://\S+/unsubscribe\?t=\S+", t).group(0)
    assert problem(unsub) is None and problem(headers["List-Unsubscribe"].strip("<>")) is None


@pytest.mark.parametrize("kind", list(lifecycle.EMAILS))
def test_lifecycle_emails_as_sent_link_to_real_pages(kind):
    from datetime import datetime, timezone
    _, html, text = lifecycle.build(kind, {"id": "u", "email": "x@example.com"}, lifecycle.sample(kind, datetime.now(timezone.utc)))
    html, text, _ = kit.finish(html, text, "u-1", None if lifecycle.EMAILS[kind][1] else lifecycle.CATEGORY)
    bad = {u: problem(u) for u in links(html, text) if problem(u)}
    assert not bad, f"{kind}: {bad}"


def test_newsletter_links_and_the_phone_teaser_open_the_issue_in_news():
    for iid in ("market.IN.2026-10-07", "market.US.2026-10-07", "market.IN.2026-10-03-weekly", "my_stocks.u-1.2026-10-07"):
        assert problem(kit.news_url(iid)) is None
        q = parse_qs(urlsplit(kit.news_url(iid)).query)
        assert q["issue"] == [iid] and q["tab"] == [{"market.IN": "IN", "market.US": "US"}.get(iid[:9], "mine")]
    assert kit.news_path("market.US.2026-10-07") == "/news?tab=US&issue=market.US.2026-10-07"


def test_the_buttons_of_plain_alerts_go_to_real_pages():
    for path in kit.BUTTONS:
        assert problem(kit.site(path)) is None, path
