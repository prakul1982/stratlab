"""Admin → Social: the daily theme post on X and LinkedIn, posted by the server as the owner (social103, owner 28 Nov: "daily posting on
X and LinkedIn fully automated; I have no time to post").

Connecting: the owner presses Connect X or Connect LinkedIn in Admin → Social. The server makes a one-time state (and, for X, a PKCE
verifier), keeps them sealed for STATE_TTL seconds, and sends the browser to the network's own sign-in page; the network sends it back
to {PUBLIC_API_URL}/admin/social/<x|linkedin>/callback (the Kite login's pattern: the backend's own address, as the site's host serves
/admin as the app), where the state is checked and used up, the code is exchanged for tokens server-side, and the tokens are stored
sealed with the app's own vault (connect/vault.py, CONNECT_SECRET_KEY) under social:auth:<net>. No token is ever logged, put in an error,
sent to the browser or kept unsealed; Admin sees only the account's name and when the sign-in ends.

  - X: OAuth 2.0 Authorization Code with PKCE (S256), scopes tweet.read tweet.write users.read offline.access, a confidential client
    (X_CLIENT_ID / X_CLIENT_SECRET). The access token lasts two hours; before a post the server renews it with the refresh token, and X
    hands back a new refresh token each time, stored at once (the old one stops working).
  - LinkedIn: OAuth 2.0 (Sign In with LinkedIn using OpenID Connect + Share on LinkedIn), scopes openid profile w_member_social
    (LINKEDIN_CLIENT_ID / LINKEDIN_CLIENT_SECRET); the member's id from /v2/userinfo; posts through the Posts API as that member. Its
    token lasts about 60 days with no refresh: Admin shows the day it ends and Needs your attention says "reconnect LinkedIn" from
    LINKEDIN_WARN_DAYS days before.

Posting: once a day per network at RUN_AT India time, Monday to Saturday, when the network is connected and switched on (each is off until
the owner turns it on). The job (Job) sleeps until the next run time and does one bounded run: it picks the next theme (social_post.pick),
claims the day's slot in the post log with a compare-and-set (two runs, two containers or a restart never post twice: a slot already
claimed is left), sends, and writes what happened. A failure the network answered is tried once more RETRY_AFTER later; a second failure
stays failed and shows in Admin → Social, in Needs your attention and as the network's row under Data sources (source_health). A send
cut off without an answer (a timeout, a restart mid-send) is "unknown" and never tried again by itself: it may have gone out.

Nothing here runs in tests or the browser tests' fake world: the HTTP call refuses to leave the machine when SOCIAL_OFFLINE=1 or under
pytest, and tests replace HTTP with a fake."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
import threading
import time
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from . import admin, db, leader, social_post
from .config import settings
from .connect import vault
from .responses import err

IST = timezone(timedelta(hours=5, minutes=30))

NAMES = {"x": "X", "linkedin": "LinkedIn"}
VARS = {"x": ("X_CLIENT_ID", "X_CLIENT_SECRET"), "linkedin": ("LINKEDIN_CLIENT_ID", "LINKEDIN_CLIENT_SECRET")}
SCOPES = {"x": "tweet.read tweet.write users.read offline.access", "linkedin": "openid profile w_member_social"}
X_AUTHORIZE = "https://x.com/i/oauth2/authorize"
X_TOKEN = "https://api.x.com/2/oauth2/token"
X_ME = "https://api.x.com/2/users/me"
X_TWEETS = "https://api.x.com/2/tweets"
LI_AUTHORIZE = "https://www.linkedin.com/oauth/v2/authorization"
LI_TOKEN = "https://www.linkedin.com/oauth/v2/accessToken"
LI_ME = "https://api.linkedin.com/v2/userinfo"
LI_POSTS = "https://api.linkedin.com/rest/posts"

STATE_KEY = "social:oauth"           # {sha256(state): {"net", "verifier" (sealed), "at"}}: sign-ins under way
AUTH_KEY = "social:auth:"            # + net: the stored sign-in (tokens sealed)
CONF_KEY = "social:conf"             # {"x": {"enabled": bool}, "linkedin": {...}}
LOG_KEY = "social:log"               # the post log, newest last
STATE_TTL = 600                      # seconds a sign-in may take
STATES_MAX = 6
RUN_AT, RUN_UNTIL = "09:40", "13:40"  # India time: the day's post goes at RUN_AT; a retry or a late start no later than RUN_UNTIL
RUN_DAYS = (0, 1, 2, 3, 4, 5)        # Monday to Saturday
RETRY_AFTER = 15 * 60                # a failed post is tried once more this long after
SENDING_STALE = 10 * 60              # a "sending" row this old was cut off (a restart mid-send): unknown, never sent again by itself
MANUAL_GAP = 10 * 60                 # "Post now" at most once in this long per network (a double click is not two posts)
REFRESH_BEFORE = 5 * 60              # an X token this close to its end is renewed before use
LINKEDIN_WARN_DAYS = 7
LOG_KEEP = 100                       # rows kept (more than REPEAT_DAYS of both networks); the newest TEXT_KEEP keep their whole text
TEXT_KEEP = 30
SHOW = 20                            # rows Admin lists
PREVIEW_FOR = 600                    # seconds the next post's preview is kept
TIMEOUT = 20.0


class SocialError(Exception):
    """A step that didn't work, in words fit for Admin (never a token). `ambiguous`: the network may have acted (a timeout on a post)."""

    def __init__(self, message: str, status: int | None = None, ambiguous: bool = False, reconnect: bool = False):
        super().__init__(message)
        self.status, self.ambiguous, self.reconnect = status, ambiguous, reconnect


def offline() -> bool:
    return os.environ.get("SOCIAL_OFFLINE", "").strip() == "1" or "PYTEST_CURRENT_TEST" in os.environ


def _real_http(method: str, url: str, **kw) -> httpx.Response:
    if offline():
        raise SocialError("Posting is off on this machine (tests or the local fake world): no call to X or LinkedIn is made.")
    with httpx.Client(timeout=TIMEOUT) as c:
        return c.request(method, url, **kw)


HTTP = _real_http                    # tests put a fake here


_TOKENISH = re.compile(r"[A-Za-z0-9_\-.~+/=]{32,}")


def clean(text) -> str:
    """An error for Admin: one line, no long token-like strings, no query strings, at most 200 characters."""
    t = re.sub(r"\s+", " ", str(text or "")).strip()
    t = re.sub(r"https?://\S+", lambda m: re.sub(r"[?#].*$", "", m.group(0)), t)
    t = _TOKENISH.sub("…", t)
    return t[:200]


def _why(r: httpx.Response, who: str) -> str:
    """What the network said about a refused call, from its JSON (title, detail, error_description, message), never a header."""
    try:
        j = r.json()
    except Exception:
        j = {}
    bits = []
    if isinstance(j, dict):
        for k in ("title", "detail", "error_description", "error", "message"):
            v = j.get(k)
            if isinstance(v, str) and v and v not in bits:
                bits.append(v)
        errs = j.get("errors")
        if isinstance(errs, list) and errs and isinstance(errs[0], dict):
            m = errs[0].get("message") or errs[0].get("detail")
            if isinstance(m, str) and m not in bits:
                bits.append(m)
    said = clean("; ".join(bits)) or "no reason given"
    return f"{who} answered {r.status_code}: {said}"


def _call(method: str, url: str, who: str, **kw) -> httpx.Response:
    try:
        return HTTP(method, url, **kw)
    except SocialError:
        raise
    except (httpx.TimeoutException, httpx.RemoteProtocolError, httpx.ReadError) as e:
        raise SocialError(f"{who} didn't answer in time ({e.__class__.__name__}).", ambiguous=True)
    except httpx.HTTPError as e:
        raise SocialError(f"Couldn't reach {who} ({e.__class__.__name__}).")


# ---------- settings ----------
def _now() -> float:
    return time.time()


def _iso(t: float | None = None) -> str:
    return datetime.fromtimestamp(_now() if t is None else t, timezone.utc).isoformat(timespec="seconds")


def client(net: str) -> tuple[str, str]:
    a, b = VARS[net]
    return (getattr(settings, a, "") or "").strip(), (getattr(settings, b, "") or "").strip()


def configured(net: str) -> bool:
    return all(client(net))


def redirect_uri(net: str) -> str:
    return f"{settings.PUBLIC_API_URL}/admin/social/{net}/callback"


def auth(net: str) -> dict:
    return db.json_value(db.get_setting(AUTH_KEY + net), {})


def connected(net: str) -> bool:
    a = auth(net)
    return bool(a.get("access")) and not a.get("broken")


def conf() -> dict:
    c = db.json_value(db.get_setting(CONF_KEY), {})
    return {n: {"enabled": bool((c.get(n) or {}).get("enabled"))} for n in NAMES}


def enabled(net: str) -> bool:
    return conf()[net]["enabled"]


def set_enabled(net: str, on: bool) -> dict:
    def fn(raw):
        c = db.json_value(raw, {})
        c[net] = {**(c.get(net) or {}), "enabled": bool(on)}
        return json.dumps(c)
    db.update_setting(CONF_KEY, fn)
    return conf()


def rows() -> list[dict]:
    return [r for r in db.json_value(db.get_setting(LOG_KEY), []) if isinstance(r, dict)]


def _trim(rs: list[dict]) -> list[dict]:
    rs = rs[-LOG_KEEP:]
    for r in rs[:-TEXT_KEEP]:
        if r.get("status") in ("posted", "unknown", "failed") and r.get("parts"):
            r["first"] = (r["parts"][0] or "")[:140]
            r.pop("parts", None)
    return rs


def _update_rows(fn) -> list[dict]:
    """Change the log atomically: fn(rows) returns the new rows, or None to leave them. Returns the rows afterwards."""
    def wrap(raw):
        got = fn([r for r in db.json_value(raw, []) if isinstance(r, dict)])
        return None if got is None else json.dumps(_trim(got), separators=(",", ":"), ensure_ascii=False)
    return [r for r in db.json_value(db.update_setting(LOG_KEY, wrap), []) if isinstance(r, dict)]


def _patch(rid: str, **fields) -> dict | None:
    fields["updated"] = _iso()

    def fn(rs):
        for r in rs:
            if r.get("id") == rid:
                r.update(fields)
                return rs
        return None
    return next((r for r in _update_rows(fn) if r.get("id") == rid), None)


# ---------- connecting ----------
def _hash(state: str) -> str:
    return hashlib.sha256(state.encode()).hexdigest()


def challenge(verifier: str) -> str:
    """PKCE S256: base64url(sha256(verifier)) without padding."""
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")


def start(net: str) -> str:
    """The network's sign-in address for a new connection (state and PKCE kept sealed for STATE_TTL seconds)."""
    if net not in NAMES:
        raise SocialError("Unknown network.")
    if not configured(net):
        a, b = VARS[net]
        raise SocialError(f"{a} and {b} aren't set on the server: add them in Railway → Variables, then redeploy.")
    if not vault.ready():
        raise SocialError("CONNECT_SECRET_KEY isn't set on the server, so a sign-in can't be stored safely: add it in Railway → Variables.")
    state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(64)
    now = _now()

    def fn(raw):
        st = {k: v for k, v in db.json_value(raw, {}).items() if isinstance(v, dict) and now - float(v.get("at") or 0) < STATE_TTL}
        st[_hash(state)] = {"net": net, "verifier": vault.seal(verifier), "at": now}
        return json.dumps(dict(sorted(st.items(), key=lambda kv: kv[1]["at"])[-STATES_MAX:]))
    db.update_setting(STATE_KEY, fn)
    cid = client(net)[0]
    if net == "x":
        q = {"response_type": "code", "client_id": cid, "redirect_uri": redirect_uri(net), "scope": SCOPES[net], "state": state,
             "code_challenge": challenge(verifier), "code_challenge_method": "S256"}
        return f"{X_AUTHORIZE}?{urlencode(q)}"
    q = {"response_type": "code", "client_id": cid, "redirect_uri": redirect_uri(net), "scope": SCOPES[net], "state": state}
    return f"{LI_AUTHORIZE}?{urlencode(q)}"


def take_state(net: str, state: str) -> str | None:
    """The PKCE verifier of a sign-in under way for `net` with this state, used up (a state answers once); None when there is none, it
    is older than STATE_TTL or it was made for the other network."""
    if not state or len(state) > 200:
        return None
    h, now, got = _hash(state), _now(), {}

    def fn(raw):
        st = db.json_value(raw, {})
        hit = st.pop(h, None)
        got["hit"] = hit
        return json.dumps(st) if hit is not None else None
    db.update_setting(STATE_KEY, fn)
    hit = got.get("hit")
    if not isinstance(hit, dict) or hit.get("net") != net or now - float(hit.get("at") or 0) >= STATE_TTL:
        return None
    return vault.unseal(hit.get("verifier")) or None


def _store(net: str, tok: dict, account: dict, old: dict | None = None) -> dict:
    now = _now()
    access = tok.get("access_token")
    if not isinstance(access, str) or not access:
        raise SocialError(f"{NAMES[net]} sent no access token.")
    refresh = tok.get("refresh_token")
    a = {"access": vault.seal(access),
         "refresh": vault.seal(refresh) if isinstance(refresh, str) and refresh else (old or {}).get("refresh"),
         "expires_at": now + float(tok.get("expires_in") or (7200 if net == "x" else 60 * 86400)),
         "refresh_expires_at": now + float(tok["refresh_token_expires_in"]) if tok.get("refresh_token_expires_in") else (old or {}).get("refresh_expires_at"),
         "scope": str(tok.get("scope") or SCOPES[net])[:200], "account": account,
         "connected_at": (old or {}).get("connected_at") or _iso(now), "refreshed_at": _iso(now)}
    db.set_setting(AUTH_KEY + net, json.dumps(a))
    return a


def finish(net: str, code: str, state: str, error: str = "") -> str:
    """The network sent the owner back: check and use up the state, exchange the code, store the sign-in. Returns a short result word for
    the Admin page: connected, denied, expired, failed."""
    verifier = take_state(net, state)
    if verifier is None:
        return "expired"
    if error or not code:
        return "denied"
    cid, secret = client(net)
    try:
        if net == "x":
            r = _call("POST", X_TOKEN, "X", data={"code": code, "grant_type": "authorization_code", "redirect_uri": redirect_uri(net),
                                                  "code_verifier": verifier, "client_id": cid}, auth=(cid, secret))
            if r.status_code != 200:
                raise SocialError(_why(r, "X"))
            tok = r.json()
            me = _call("GET", X_ME, "X", headers={"Authorization": f"Bearer {tok.get('access_token')}"})
            d = (me.json() or {}).get("data") if me.status_code == 200 else None
            account = {"id": str((d or {}).get("id") or ""), "name": f"@{d['username']}" if d and d.get("username") else "your X account"}
        else:
            r = _call("POST", LI_TOKEN, "LinkedIn", data={"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri(net),
                                                         "client_id": cid, "client_secret": secret})
            if r.status_code != 200:
                raise SocialError(_why(r, "LinkedIn"))
            tok = r.json()
            me = _call("GET", LI_ME, "LinkedIn", headers={"Authorization": f"Bearer {tok.get('access_token')}"})
            u = me.json() if me.status_code == 200 else {}
            if not (isinstance(u, dict) and u.get("sub")):
                raise SocialError(_why(me, "LinkedIn") if me.status_code != 200 else "LinkedIn didn't say which member signed in.")
            account = {"id": str(u["sub"]), "name": str(u.get("name") or "your LinkedIn profile")[:80]}
        _store(net, tok, account)
    except (SocialError, ValueError) as e:
        _note_problem(net, f"Connecting failed: {clean(e)}")
        return "failed"
    _note_problem(net, None)
    return "connected"


def disconnect(net: str) -> None:
    """Forget the stored sign-in here (and switch the network off). The app stays allowed in the network's own settings until removed there."""
    db.delete_setting(AUTH_KEY + net)
    set_enabled(net, False)
    _note_problem(net, None)


PROBLEM_KEY = "social:problem:"


def _note_problem(net: str, text: str | None) -> None:
    try:
        if text:
            db.set_setting(PROBLEM_KEY + net, json.dumps({"text": clean(text), "at": _iso()}))
        else:
            db.delete_setting(PROBLEM_KEY + net)
    except Exception:
        pass


def problem(net: str) -> dict | None:
    p = db.json_value(db.get_setting(PROBLEM_KEY + net), {})
    return p if p.get("text") else None


# ---------- tokens ----------
_refresh_lock = threading.Lock()


def refresh_x() -> dict:
    """Renew X's access token with the stored refresh token; X hands back a new refresh token, stored at once (the old one is spent)."""
    with _refresh_lock:
        a = auth("x")
        if a.get("access") and float(a.get("expires_at") or 0) - _now() > REFRESH_BEFORE:
            return a                                     # another caller renewed it meanwhile
        rt = vault.unseal(a.get("refresh"))
        if not rt:
            raise SocialError("X's stored sign-in can't be renewed (no refresh token, or CONNECT_SECRET_KEY changed): press Connect X again.",
                              reconnect=True)
        cid, secret = client("x")
        r = _call("POST", X_TOKEN, "X", data={"refresh_token": rt, "grant_type": "refresh_token", "client_id": cid}, auth=(cid, secret))
        if r.status_code != 200:
            why = _why(r, "X")
            if r.status_code in (400, 401):
                db.set_setting(AUTH_KEY + "x", json.dumps({**a, "broken": why}))
                raise SocialError(f"X turned the stored sign-in down ({why}): press Connect X again.", status=r.status_code, reconnect=True)
            raise SocialError(why, status=r.status_code)
        return _store("x", r.json(), a.get("account") or {}, old=a)


def access_token(net: str) -> tuple[str, dict]:
    a = auth(net)
    if not a.get("access"):
        raise SocialError(f"{NAMES[net]} isn't connected: press Connect {NAMES[net]} in Admin → Social.", reconnect=True)
    if a.get("broken"):
        raise SocialError(f"{NAMES[net]} turned the stored sign-in down: press Connect {NAMES[net]} again.", reconnect=True)
    if net == "x" and float(a.get("expires_at") or 0) - _now() <= REFRESH_BEFORE:
        a = refresh_x()
    if net == "linkedin" and float(a.get("expires_at") or 0) <= _now():
        raise SocialError("LinkedIn's sign-in has run out (it lasts about 60 days): press Reconnect LinkedIn in Admin → Social.", reconnect=True)
    tok = vault.unseal(a.get("access"))
    if not tok:
        raise SocialError(f"The stored {NAMES[net]} sign-in can't be opened (CONNECT_SECRET_KEY changed?): press Connect {NAMES[net]} again.",
                          reconnect=True)
    return tok, a


# ---------- posting ----------
def li_version(today: date | None = None) -> str:
    """The LinkedIn-Version header: LINKEDIN_API_VERSION when set, else the month two months back (a version LinkedIn has published and
    still serves: each is served for a year)."""
    v = (os.environ.get("LINKEDIN_API_VERSION") or "").strip()
    if re.fullmatch(r"\d{6}", v):
        return v
    d = (today or datetime.now(IST).date()).replace(day=1) - timedelta(days=40)
    return d.strftime("%Y%m")


_LI_RESERVED = re.compile(r"([\\|{}@\[\]()<>#*_~])")


def li_escape(text: str) -> str:
    """LinkedIn's commentary is "little text": its reserved characters are escaped, or the post is cut off at the first one."""
    return _LI_RESERVED.sub(r"\\\1", text)


def send_x(parts: list[str], ids: list[str], on_part) -> list[str]:
    """Post the parts as a thread, each a reply to the one before, from where `ids` (parts already up) stops. on_part(ids) after each."""
    ids = list(ids)
    tok, a = access_token("x")
    renewed = False
    i = len(ids)
    while i < len(parts):
        body: dict = {"text": parts[i]}
        if ids:
            body["reply"] = {"in_reply_to_tweet_id": ids[-1]}
        r = _call("POST", X_TWEETS, "X", json=body, headers={"Authorization": f"Bearer {tok}"})
        if r.status_code == 401 and not renewed:          # ended early: renewed once, the same part sent again
            renewed = True
            db.set_setting(AUTH_KEY + "x", json.dumps({**auth("x"), "expires_at": 0}))
            tok, a = access_token("x")
            continue
        if r.status_code not in (200, 201):
            raise SocialError(_why(r, "X"), status=r.status_code)
        pid = str(((r.json() or {}).get("data") or {}).get("id") or "")
        if not pid:
            raise SocialError("X took the post but sent back no id.", ambiguous=True)
        ids.append(pid)
        on_part(ids)
        i += 1
    return ids


def x_url(a: dict, pid: str) -> str:
    name = str((a.get("account") or {}).get("name") or "").lstrip("@")
    return f"https://x.com/{name or 'i/web'}/status/{pid}"


def send_linkedin(text: str) -> str:
    tok, a = access_token("linkedin")
    who = (a.get("account") or {}).get("id")
    if not who:
        raise SocialError("LinkedIn's stored sign-in doesn't say which member it is: press Reconnect LinkedIn.", reconnect=True)
    body = {"author": f"urn:li:person:{who}", "commentary": li_escape(text), "visibility": "PUBLIC",
            "distribution": {"feedDistribution": "MAIN_FEED", "targetEntities": [], "thirdPartyDistributionChannels": []},
            "lifecycleState": "PUBLISHED", "isReshareDisabledByAuthor": False}
    r = _call("POST", LI_POSTS, "LinkedIn", json=body, headers={"Authorization": f"Bearer {tok}", "LinkedIn-Version": li_version(),
                                                               "X-Restli-Protocol-Version": "2.0.0"})
    if r.status_code not in (200, 201):
        raise SocialError(_why(r, "LinkedIn"), status=r.status_code, reconnect=r.status_code == 401)
    urn = r.headers.get("x-restli-id") or r.headers.get("x-linkedin-id") or ""
    return urn


def _health(net: str, ok: bool, error: str | None = None) -> None:
    try:
        from . import source_health
        source_health.record(net, ok, error)
    except Exception:
        pass


def deliver(row: dict) -> dict:
    """Send one claimed row (status "sending") and write how it went. Never raises."""
    net, rid = row["net"], row["id"]
    try:
        if net == "x":
            ids = send_x(row.get("parts") or [], row.get("ids") or [], lambda got: _patch(rid, ids=list(got)))
            out = _patch(rid, status="posted", ids=ids, url=x_url(auth("x"), ids[0]) if ids else None, error=None)
        else:
            urn = send_linkedin((row.get("parts") or [""])[0])
            out = _patch(rid, status="posted", ids=[urn] if urn else [], url=f"https://www.linkedin.com/feed/update/{urn}/" if urn else None,
                         error=None)
        _health(net, True)
        _note_problem(net, None)
        return out or row
    except SocialError as e:
        status = "unknown" if e.ambiguous else "failed"
        text = clean(e) + (" It may have gone out: look at the profile before posting again." if e.ambiguous else "")
        out = _patch(rid, status=status, error=text) or {**row, "status": status, "error": text}
        _health(net, False, clean(e))
        if e.reconnect:
            _note_problem(net, clean(e))
        return out
    except Exception as e:                                # a fault of ours: said, never a crash of the job
        text = clean(f"The post couldn't be sent ({e.__class__.__name__}).")
        _health(net, False, text)
        return _patch(rid, status="failed", error=text) or {**row, "status": "failed", "error": text}


def _new_row(net: str, kind: str, day: str, post: dict) -> dict:
    t = _iso()
    return {"id": secrets.token_hex(6), "net": net, "kind": kind, "day": day, "theme": post["theme"], "parts": post["parts"],
            "link": post["link"], "status": "sending", "attempts": 1, "ids": [], "url": None, "error": None, "at": t, "updated": t}


def claim_daily(net: str, day: str, post: dict) -> dict | None:
    """The day's slot for `net`, claimed atomically: the new row, or None when the day already has one (posted, failed or under way)."""
    row = _new_row(net, "daily", day, post)

    def fn(rs):
        if any(r.get("net") == net and r.get("kind") == "daily" and r.get("day") == day for r in rs):
            return None
        return rs + [row]
    return row if any(r.get("id") == row["id"] for r in _update_rows(fn)) else None


def _age(r: dict) -> float:
    try:
        return _now() - datetime.fromisoformat(str(r.get("updated") or r.get("at"))).timestamp()
    except ValueError:
        return 0.0


def claim_retry(net: str, day: str) -> dict | None:
    """The day's failed row, claimed for its one more try (RETRY_AFTER after the failure); None when there is none to try."""
    got: dict = {}

    def fn(rs):
        for r in rs:
            if r.get("net") == net and r.get("kind") == "daily" and r.get("day") == day and r.get("status") == "failed" \
                    and int(r.get("attempts") or 1) < 2 and _age(r) >= RETRY_AFTER:
                r.update(status="sending", attempts=int(r.get("attempts") or 1) + 1, updated=_iso())
                got["row"] = dict(r)
                return rs
        return None
    _update_rows(fn)
    return got.get("row")


def settle_stale() -> None:
    """A row left "sending" by a stopped server: unknown (it may have gone out), never sent again by itself."""
    def fn(rs):
        hit = False
        for r in rs:
            if r.get("status") == "sending" and _age(r) >= SENDING_STALE:
                r.update(status="unknown", updated=_iso(),
                         error="The server stopped while posting. Look at the profile to see whether it went out; it isn't sent again by itself.")
                hit = True
        return rs if hit else None
    _update_rows(fn)


_preview: dict = {}
_preview_lock = threading.Lock()


def _make(net: str, entry: dict) -> dict | None:
    from . import public_themes
    p = public_themes.payload(entry)
    if not p:
        return None
    v = public_themes.view(entry, p)
    if not v.get("indexable"):
        return None
    return social_post.build(net, v, settings.PUBLIC_SITE_URL)


def next_post(net: str, today: date | None = None, fresh: bool = False) -> dict | None:
    """The post `net` would send next (kept PREVIEW_FOR seconds for the Admin page; a send builds it afresh)."""
    from . import public_themes
    today = today or datetime.now(IST).date()
    rs = rows()
    key = (net, today.isoformat(), social_post.last_posted(rs, net), len(rs))
    with _preview_lock:
        hit = _preview.get(net)
        if not fresh and hit and hit[0] == key and _now() - hit[1] < PREVIEW_FOR:
            return hit[2]
    got = social_post.pick(net, public_themes.entries(), rs, today, lambda e: _make(net, e))
    with _preview_lock:
        _preview[net] = (key, _now(), got)
    return got


def no_post_note(net: str, today: date | None = None) -> str:
    """Why `net` has no next post, in words: no public theme yet, every one posted within REPEAT_DAYS, or none of the rest gives a fit post."""
    from . import public_themes
    today = today or datetime.now(IST).date()
    try:
        entries = public_themes.entries()
    except Exception:
        entries = []
    if not entries:
        return "No public theme page yet: the daily post starts once a theme is mapped and checked."
    skip = social_post.recent(rows(), net, today)
    left = [e for e in entries if social_post.theme_key(e) not in skip]
    if not left:
        return (f"Every public theme ({len(entries)}) was posted on {NAMES[net]} in the last {social_post.REPEAT_DAYS} days; the next one goes "
                f"once a theme is {social_post.REPEAT_DAYS} days past its post.")
    return (f"None of the {len(left)} public theme{'s' if len(left) != 1 else ''} not posted in the last {social_post.REPEAT_DAYS} days gives a post "
            "yet (its page needs at least two layers and eight checked companies).")


def forget_preview() -> None:
    with _preview_lock:
        _preview.clear()


def daily(net: str, today: date) -> dict | None:
    """The day's post for `net`: sent once; a failed one tried once more RETRY_AFTER later; None when there is nothing to do."""
    day = today.isoformat()
    settle_stale()
    mine = next((r for r in rows() if r.get("net") == net and r.get("kind") == "daily" and r.get("day") == day), None)
    if mine is None:
        post = next_post(net, today, fresh=True)
        if not post:                                     # nothing for the owner to do: Admin → Social's preview says why
            return None
        row = claim_daily(net, day, post)
        return deliver(row) if row else None
    row = claim_retry(net, day)
    return deliver(row) if row else None


def post_now(net: str) -> dict:
    """Admin's "Post now" (for testing): the next post, sent at once, retried once at once if the network refused it."""
    if not connected(net):
        raise SocialError(f"{NAMES[net]} isn't connected yet.")
    settle_stale()
    if any(r.get("net") == net and r.get("kind") == "manual" and r.get("status") in ("sending", "posted") and _age(r) < MANUAL_GAP
           for r in rows()):
        raise SocialError(f"A test post went to {NAMES[net]} in the last {MANUAL_GAP // 60} minutes: look at it there before sending another.")
    today = datetime.now(IST).date()
    post = next_post(net, today, fresh=True)
    if not post:
        raise SocialError(no_post_note(net, today))
    row = _new_row(net, "manual", today.isoformat(), post)
    _update_rows(lambda rs: rs + [row])
    out = deliver(row)
    if out.get("status") == "failed":
        _patch(row["id"], status="sending", attempts=2)
        out = deliver({**out, "status": "sending", "attempts": 2})
    forget_preview()
    return out


# ---------- the daily job ----------
def next_run(now: datetime) -> datetime:
    """The next RUN_AT on a posting day, India time, from `now` (today's when it is still ahead)."""
    local = now.astimezone(IST)
    h, m = (int(x) for x in RUN_AT.split(":"))
    for i in range(8):
        d = local.date() + timedelta(days=i)
        at = datetime(d.year, d.month, d.day, h, m, tzinfo=IST)
        if d.weekday() in RUN_DAYS and at > local:
            return at
    return local + timedelta(days=1)


def in_window(now: datetime) -> bool:
    local = now.astimezone(IST)
    return local.weekday() in RUN_DAYS and RUN_AT <= local.strftime("%H:%M") < RUN_UNTIL


class Job:
    """Sleeps until the next RUN_AT (at most an hour at a time), then one bounded pass per network: post, or retry once, and done."""

    def __init__(self):
        self.status = {"last_run": None, "last_error": None}
        self.lock = threading.Lock()

    def start(self):
        threading.Thread(target=self._loop, daemon=True, name="social-posts").start()

    def _loop(self):
        time.sleep(300)                                  # after startup traffic
        while True:
            now = datetime.now(timezone.utc)
            try:
                if leader.leading():
                    self.tick(now)
            except Exception as e:
                self.status["last_error"] = clean(e)
            now = datetime.now(timezone.utc)
            wait = 300.0 if in_window(now) else (next_run(now) - now).total_seconds() + 5
            time.sleep(max(60.0, min(wait, 3600.0)))

    def tick(self, now: datetime) -> dict:
        """One pass: for each network switched on and connected, the day's post (or its one retry) when it is posting time."""
        out: dict = {}
        if not in_window(now) or not self.lock.acquire(blocking=False):
            return out
        try:
            c = conf()
            today = now.astimezone(IST).date()
            for net in NAMES:
                if not c[net]["enabled"] or not connected(net):
                    continue
                try:
                    got = daily(net, today)
                    if got:
                        out[net] = got.get("status")
                except Exception as e:
                    self.status["last_error"] = clean(e)
                    out[net] = "error"
            self.status["last_run"] = _iso()
        finally:
            self.lock.release()
        return out


job = Job()


# ---------- what Admin reads ----------
def _days_left(a: dict) -> int | None:
    t = a.get("expires_at")
    if not t:
        return None
    return int((float(t) - _now()) // 86400)


def summary() -> list[dict]:
    """For Overview (Needs your attention): per network, whether it is connected and on, when LinkedIn's sign-in ends, a problem, and the
    newest post that failed for good (both tries) or may not have gone out, in the last two days."""
    out = []
    c = conf()
    try:
        rs = rows()
    except Exception:
        rs = []
    since = (datetime.now(IST).date() - timedelta(days=1)).isoformat()
    for net in NAMES:
        a = auth(net)
        last = next((r for r in reversed(rs) if r.get("net") == net), None)
        bad = last if last and str(last.get("day") or "") >= since and (
            last.get("status") == "unknown" or (last.get("status") == "failed" and int(last.get("attempts") or 1) >= 2)) else None
        p = problem(net)
        out.append({"key": net, "name": NAMES[net], "configured": configured(net), "connected": bool(a.get("access")) and not a.get("broken"),
                    "enabled": c[net]["enabled"], "expires_at": _iso(float(a["expires_at"])) if net == "linkedin" and a.get("expires_at") else None,
                    "days_left": _days_left(a) if net == "linkedin" and a.get("access") else None,
                    "problem": (a.get("broken") and f"{NAMES[net]} turned the stored sign-in down: press Connect {NAMES[net]} again.") or (p or {}).get("text"),
                    "failed": {"at": bad.get("updated") or bad.get("at"), "status": bad.get("status"), "error": bad.get("error"),
                               "day": bad.get("day")} if bad else None})
    return out


def _public_row(r: dict) -> dict:
    parts = r.get("parts") or ([r["first"]] if r.get("first") else [])
    return {"id": r.get("id"), "net": r.get("net"), "name": NAMES.get(str(r.get("net")), r.get("net")), "kind": r.get("kind"),
            "day": r.get("day"), "at": r.get("at"), "updated": r.get("updated"), "theme": (r.get("theme") or {}).get("label"),
            "region": (r.get("theme") or {}).get("region"), "link": r.get("link"), "status": r.get("status"),
            "attempts": int(r.get("attempts") or 1), "url": r.get("url"), "error": r.get("error"), "parts": len(r.get("ids") or []) or len(parts),
            "text": parts[0] if parts else ""}


def admin_view() -> dict:
    """Admin → Social: each network (set up, connected as whom, until when, on or off, the next post) and the last SHOW posts."""
    now = datetime.now(timezone.utc)
    nxt = next_run(now)
    when = f"{nxt.strftime('%a')} {nxt.day} {nxt.strftime('%b')}, {nxt.strftime('%I:%M %p').lstrip('0')} IST"
    nets = []
    s = {x["key"]: x for x in summary()}
    for net in NAMES:
        a = auth(net)
        try:
            preview = next_post(net)
            note = None if preview else no_post_note(net)
        except Exception as e:
            preview, note = None, clean(f"The preview couldn't be built ({e.__class__.__name__}).")
        nets.append({**s[net], "vars": list(VARS[net]), "callback": redirect_uri(net), "scopes": SCOPES[net],
                     "account": (a.get("account") or {}).get("name") if a.get("access") else None,
                     "connected_at": a.get("connected_at") if a.get("access") else None,
                     "renews": net == "x",
                     "next": {"at": when, "parts": preview["parts"], "theme": preview["theme"]["label"], "link": preview["link"]} if preview else None,
                     "next_note": note})
    posts = [_public_row(r) for r in reversed(rows())][:SHOW]
    return {"networks": nets, "posts": posts, "vault_ready": vault.ready(), "schedule": f"{RUN_AT_TEXT} India time, Monday to Saturday",
            "offline": offline()}


RUN_AT_TEXT = "9:40 AM"


# ---------- routes ----------
router = APIRouter(tags=["admin"])


def _net(net: str) -> str:
    if net not in NAMES:
        err(404, "unknown_network", "Unknown network: x or linkedin.")
    return net


class SwitchReq(BaseModel):
    enabled: bool


@router.get("/admin/social")
def admin_social(_=Depends(admin.admin_profile)):
    return admin_view()


@router.post("/admin/social/{net}/connect")
def admin_social_connect(net: str, _=Depends(admin.admin_profile)):
    try:
        return {"url": start(_net(net))}
    except SocialError as e:
        err(400, "not_set_up", str(e))


@router.put("/admin/social/{net}")
def admin_social_switch(net: str, req: SwitchReq, _=Depends(admin.admin_profile)):
    _net(net)
    if req.enabled and not connected(net):
        err(400, "not_connected", f"Connect {NAMES[net]} first: the switch turns on once it is connected.")
    set_enabled(net, req.enabled)
    return admin_view()


@router.post("/admin/social/{net}/post-now")
def admin_social_post_now(net: str, _=Depends(admin.admin_profile)):
    _net(net)
    try:
        row = post_now(net)
    except SocialError as e:
        err(400, "not_posted", str(e))
    return {"post": _public_row(row), **admin_view()}


@router.post("/admin/social/{net}/disconnect")
def admin_social_disconnect(net: str, _=Depends(admin.admin_profile)):
    disconnect(_net(net))
    return admin_view()


def _back(net: str, result: str) -> RedirectResponse:
    return RedirectResponse(f"{settings.PUBLIC_SITE_URL}/admin/social?{urlencode({'social': net, 'result': result})}", status_code=303,
                            headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})


# The networks send the owner back here (the address set in each app). Protected by the one-time state from start(), which only an admin
# can make (Admin → Social → Connect); the code is exchanged here and never reaches the browser's next page.
@router.get("/admin/social/x/callback", include_in_schema=False)
def x_callback(code: str = "", state: str = "", error: str = ""):
    return _back("x", finish("x", code, state, error))


@router.get("/admin/social/linkedin/callback", include_in_schema=False)
def linkedin_callback(code: str = "", state: str = "", error: str = ""):
    return _back("linkedin", finish("linkedin", code, state, error))
