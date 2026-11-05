"""Upstox and Dhan: a read-only holdings login for one user, the same shape as Zerodha's (kite_user.py).

The user taps "Connect", logs in at the broker, and the broker sends the browser back to /connect/<broker>/callback. That
address has no sign-in, so nothing is linked there: the login is swapped for a token (server side, with the app's secret),
kept aside sealed under a random reference, and the signed-in Settings page confirms it with a claim only the browser that
came back holds. The token is kept sealed (vault.py), never logged and never sent to the page; holdings are read into My
Holdings tagged with the broker (`via`), exactly as Zerodha's are.

Read-only: the only broker addresses this file may call are listed in READ_ONLY (log in, swap the login for a token, read
holdings). No order, funds or other write address is ever called; _http refuses anything else.

Who may connect: admins only until the broker's *_FOR_ALL flag is "true" (as KITE_MULTIUSER_APPROVED does for Zerodha).
Dhan's individual app works only for its owner's own account: until partner credentials are set, Dhan refuses anyone
else's login, and that ends on Settings in plain words.

How each login is bound to the person who started it: the login address carries a signed, 15-minute state naming the user
and the broker, and a start record (one per user and broker) holds its hash. Upstox returns the state and the callback
refuses a missing or different one. Dhan has none: there the callback stages the login without a user and the confirm needs the signed-in user's own
start record, made by their own Connect tap in the last 15 minutes (and used once)."""
import base64
import hashlib
import hmac
import json
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import httpx

from .. import admin, db, mail_tokens
from ..config import settings
from . import state, sync, vault

IST = ZoneInfo("Asia/Kolkata")
STATE_PREFIX = "b1."
PURPOSE = "broker-login"
PENDING = "broker-pending:"
START = "broker-start:"
PENDING_TTL = 600            # seconds a finished login waits for the signed-in person to confirm it
START_TTL = 900              # a Connect tap is good this long (the state's own life, mail_tokens.EXPIRES)
MAX_REPLY = 4 * 1024 * 1024
TIMEOUT = 20

UPSTOX_DIALOG = "https://api.upstox.com/v2/login/authorization/dialog"
UPSTOX_TOKEN = "https://api.upstox.com/v2/login/authorization/token"
UPSTOX_HOLDINGS = "https://api.upstox.com/v2/portfolio/long-term-holdings"
DHAN_CONSENT = "https://auth.dhan.co/app/generate-consent"
DHAN_LOGIN = "https://auth.dhan.co/login/consentApp-login"
DHAN_CONSUME = "https://auth.dhan.co/app/consumeApp-consent"
DHAN_PARTNER_CONSENT = "https://auth.dhan.co/partner/generate-consent"
DHAN_PARTNER_LOGIN = "https://auth.dhan.co/consent-login"
DHAN_PARTNER_CONSUME = "https://auth.dhan.co/partner/consume-consent"
DHAN_HOLDINGS = "https://api.dhan.co/v2/holdings"
# every broker address the server itself calls (the login pages are opened by the user's browser, not called here)
READ_ONLY = frozenset({UPSTOX_TOKEN, UPSTOX_HOLDINGS, DHAN_CONSENT, DHAN_CONSUME, DHAN_PARTNER_CONSENT,
                       DHAN_PARTNER_CONSUME, DHAN_HOLDINGS})

transport: httpx.BaseTransport | None = None        # tests and the e2e world swap in a fake broker
_lock = threading.Lock()


def _now() -> datetime:
    return datetime.now(timezone.utc)


class BrokerError(Exception):
    """`refused`: the broker itself didn't allow this login (Dhan's individual app and an account not its owner's), with
    `reason`, for the server's log only."""
    def __init__(self, message: str, expired: bool = False, refused: bool = False, reason: str = ""):
        super().__init__(message)
        self.message, self.expired, self.refused, self.reason = message, expired, refused, reason


def _http(method: str, url: str, *, headers: dict | None = None, params: dict | None = None,
          data: dict | None = None) -> tuple[int, Any]:
    """(status, parsed JSON or None). 0 when the broker can't be reached. Only addresses in READ_ONLY; nothing about the
    request (it carries a token) is ever logged or put in an error."""
    if url not in READ_ONLY:
        raise RuntimeError("not a read-only broker address")
    try:
        with httpx.Client(transport=transport, timeout=TIMEOUT, follow_redirects=False) as c:
            r = c.request(method, url, params=params, data=data,
                          headers={"Accept": "application/json", "User-Agent": "StratLab", **(headers or {})})
    except httpx.HTTPError:
        return 0, None
    if len(r.content) > MAX_REPLY:
        return r.status_code, None
    try:
        return r.status_code, r.json()
    except ValueError:
        return r.status_code, None


def _num(v) -> float:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return 0.0
    return x if x == x and abs(x) != float("inf") else 0.0


def _jwt_claims(tok: str) -> dict:
    """A JWT's payload, unverified (only to read its end time and account): {} when it isn't one."""
    try:
        part = tok.split(".")[1]
        got = json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))
        return got if isinstance(got, dict) else {}
    except (IndexError, ValueError, TypeError, UnicodeDecodeError):
        return {}


def _jwt_exp(tok: str) -> datetime | None:
    exp = _jwt_claims(tok).get("exp")
    try:
        return datetime.fromtimestamp(int(exp), timezone.utc) if exp else None
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _next_ist(at: datetime, hh: int, mm: int) -> datetime:
    """The next hh:mm India time after `at`."""
    local = at.astimezone(IST)
    t = local.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if t <= local:
        t += timedelta(days=1)
    return t.astimezone(timezone.utc)


def _earliest(*ts: datetime | None) -> datetime:
    return min(t for t in ts if t is not None)


def merge_rows(rows: list[dict]) -> list[dict]:
    """One row a stock (a broker can list it on NSE and BSE), the average weighted by quantity."""
    out: dict[str, dict] = {}
    for r in rows:
        k = r.get("isin") or r["symbol"]
        cur = out.get(k)
        if not cur:
            out[k] = dict(r)
            continue
        q = cur["qty"] + r["qty"]
        cur["avg"] = (cur["avg"] * cur["qty"] + r["avg"] * r["qty"]) / q if cur["avg"] and r["avg"] else None
        cur["qty"] = q
    return [{**r, "qty": round(r["qty"], 4)} for r in out.values() if r["qty"] > 1e-9]


def _row(symbol, isin, name, qty: float, avg) -> dict | None:
    sym = str(symbol or "").strip().upper()
    isin = str(isin or "").strip().upper() or None
    if qty <= 0 or not (sym or isin):
        return None
    a = _num(avg)
    return {"symbol": sym or isin, "isin": isin, "name": str(name or "").strip()[:120] or sym or isin, "qty": qty,
            "avg": a if a > 0 else None}


class Broker:
    key = ""
    name = ""
    source = ""
    state_back = "yes"           # whether the broker returns our state: "yes" or "no"

    def configured(self) -> bool:
        raise NotImplementedError

    def for_all(self) -> bool:
        raise NotImplementedError

    def allowed(self, profile: dict) -> bool:
        """Everyone once its *_FOR_ALL flag says so; until then only the admin."""
        return self.configured() and (self.for_all() or admin.is_admin(profile))

    def redirect_uri(self) -> str:
        return f"{settings.PUBLIC_API_URL}/connect/{self.key}/callback"

    def login_url(self, st: str) -> tuple[str, dict]:
        """(where the browser logs in, anything to keep with the start record)."""
        raise NotImplementedError

    def exchange(self, params: dict) -> dict:
        """The broker's return swapped for a token: {"token", "account", "expires_at" (datetime)}. Raises BrokerError."""
        raise NotImplementedError

    def fetch(self, token: str, account: str = "") -> list[dict]:
        """The raw holdings (`account`: the broker's id for the user, kept from the login). Raises BrokerError (expired=True when the login has ended)."""
        raise NotImplementedError

    def rows(self, raw: list[dict]) -> list[dict]:
        raise NotImplementedError

    def failed(self) -> BrokerError:
        return BrokerError(f"{self.name} didn't answer. Try again in a few minutes.")

    def ended(self) -> BrokerError:
        return BrokerError(f"Your {self.name} login has ended. Log in again.", expired=True)


# ---------- Upstox (OAuth 2) ----------
class Upstox(Broker):
    key, name, source = "upstox", "Upstox", "Upstox login"
    state_back = "yes"

    def configured(self) -> bool:
        return bool(settings.UPSTOX_API_KEY and settings.UPSTOX_API_SECRET and vault.ready())

    def for_all(self) -> bool:
        return settings.UPSTOX_FOR_ALL

    def login_url(self, st: str) -> tuple[str, dict]:
        q = {"response_type": "code", "client_id": settings.UPSTOX_API_KEY, "redirect_uri": self.redirect_uri(), "state": st}
        return f"{UPSTOX_DIALOG}?{urlencode(q)}", {}

    def exchange(self, params: dict) -> dict:
        code = str(params.get("code") or "")
        if not code or len(code) > 500:
            raise BrokerError("Upstox didn't accept that login. Try again.")
        status, body = _http("POST", UPSTOX_TOKEN, headers={"Content-Type": "application/x-www-form-urlencoded"},
                             data={"code": code, "client_id": settings.UPSTOX_API_KEY, "client_secret": settings.UPSTOX_API_SECRET,
                                   "redirect_uri": self.redirect_uri(), "grant_type": "authorization_code"})
        tok = body.get("access_token") if isinstance(body, dict) else None
        if status != 200 or not isinstance(tok, str) or not tok:
            raise BrokerError("Upstox didn't accept that login. Try again.")
        # Upstox ends every token at 03:30 India time the next morning, whenever it was made
        return {"token": tok, "account": str(body.get("user_id") or "")[:20],
                "expires_at": _earliest(_next_ist(_now(), 3, 30), _jwt_exp(tok))}

    def fetch(self, token: str, account: str = "") -> list[dict]:
        status, body = _http("GET", UPSTOX_HOLDINGS, headers={"Authorization": f"Bearer {token}"})
        codes = {str(e.get("errorCode") or e.get("error_code") or "") for e in (body or {}).get("errors") or [] if isinstance(e, dict)} \
            if isinstance(body, dict) else set()
        if status == 401 or codes & {"UDAPI100050", "UDAPI100016"}:
            raise self.ended()
        if status != 200 or not isinstance(body, dict) or body.get("status") != "success":
            raise self.failed()
        data = body.get("data")
        return [h for h in data if isinstance(h, dict)] if isinstance(data, list) else []

    def rows(self, raw: list[dict]) -> list[dict]:
        out = []
        for h in raw:
            # as Kite's (Upstox uses the same fields): settled, T+1 and pledged shares are all held
            qty = _num(h.get("quantity")) + _num(h.get("t1_quantity")) + _num(h.get("collateral_quantity"))
            r = _row(h.get("trading_symbol") or h.get("tradingsymbol"), h.get("isin"), h.get("company_name"), qty, h.get("average_price"))
            if r:
                out.append(r)
        return merge_rows(out)


# ---------- Dhan (DhanHQ v2 consent login) ----------
REFUSED = "Dhan didn't allow this login yet. Upload your holdings file or forward your statement instead."

class Dhan(Broker):
    key, name, source = "dhan", "Dhan", "Dhan login"
    state_back = "no"

    def partner(self) -> bool:
        return bool(settings.DHAN_PARTNER_ID and settings.DHAN_PARTNER_SECRET)

    def individual(self) -> bool:
        return bool(settings.DHAN_APP_ID and settings.DHAN_APP_SECRET and settings.DHAN_CLIENT_ID)

    def configured(self) -> bool:
        return (self.partner() or self.individual()) and vault.ready()

    def for_all(self) -> bool:
        # the owner's flag, as for the others. An individual app logs in only its owner's own account, so until partner
        # credentials are set Dhan refuses anyone else's login; that ends on Settings in plain words (exchange, routes.py)
        return settings.DHAN_FOR_ALL

    def creds(self) -> dict:
        if self.partner():
            return {"partner_id": settings.DHAN_PARTNER_ID, "partner_secret": settings.DHAN_PARTNER_SECRET}
        return {"app_id": settings.DHAN_APP_ID, "app_secret": settings.DHAN_APP_SECRET}

    def login_url(self, st: str) -> tuple[str, dict]:
        if self.partner():
            status, body = _http("POST", DHAN_PARTNER_CONSENT, headers=self.creds())
            cid = body.get("consentId") if isinstance(body, dict) else None
            where = DHAN_PARTNER_LOGIN + "?" + urlencode({"consentId": cid or ""})
        else:
            status, body = _http("POST", DHAN_CONSENT, headers=self.creds(), params={"client_id": settings.DHAN_CLIENT_ID})
            cid = body.get("consentAppId") if isinstance(body, dict) else None
            where = DHAN_LOGIN + "?" + urlencode({"consentAppId": cid or ""})
        if status != 200 or not isinstance(cid, str) or not cid or len(cid) > 200:
            raise self.failed()
        return where, {"consent": hashlib.sha256(cid.encode()).hexdigest()[:24]}

    def exchange(self, params: dict) -> dict:
        tid = str(params.get("tokenId") or params.get("tokenid") or "")
        if not tid or len(tid) > 500:
            raise BrokerError("Dhan didn't accept that login. Try again.")
        url = DHAN_PARTNER_CONSUME if self.partner() else DHAN_CONSUME
        status, body = _http("GET", url, headers=self.creds(), params={"tokenId": tid})
        tok = body.get("accessToken") if isinstance(body, dict) else None
        if status != 200 or not isinstance(tok, str) or not tok:
            if not self.partner() and 400 <= status < 500:
                code = str(body.get("errorCode") or "") if isinstance(body, dict) else ""
                raise BrokerError(REFUSED, refused=True, reason=f"consume answered {status} {code[:20]} (individual app, no partner credentials)")
            raise BrokerError("Dhan didn't accept that login. Try again.")
        account = str(body.get("dhanClientId") or "")[:20]
        if not self.partner() and account.strip() != settings.DHAN_CLIENT_ID.strip():
            raise BrokerError(REFUSED, refused=True, reason="the account isn't the app owner's (individual app, no partner credentials)")
        ends = None
        try:                                    # "2025-09-23T12:37:23", India time with no zone
            ends = datetime.fromisoformat(str(body.get("expiryTime") or "")).replace(tzinfo=IST).astimezone(timezone.utc)
        except ValueError:
            pass
        return {"token": tok, "account": account, "expires_at": ends or _jwt_exp(tok) or _now() + timedelta(hours=24)}

    def fetch(self, token: str, account: str = "") -> list[dict]:
        # Dhan's data calls take the account's client id beside the token (docs.dhanhq.co/api/v2; its own Python client
        # sends both). A read like this needs no static IP: Dhan asks for one only on order placement.
        heads = {"access-token": token, "Content-Type": "application/json"}
        if account or settings.DHAN_CLIENT_ID:
            heads["client-id"] = account or settings.DHAN_CLIENT_ID
        status, body = _http("GET", DHAN_HOLDINGS, headers=heads)
        if status == 200 and isinstance(body, list):
            return [h for h in body if isinstance(h, dict)]
        code = str(body.get("errorCode") or "") if isinstance(body, dict) else ""
        msg = str(body.get("errorMessage") or "") if isinstance(body, dict) else ""
        if status == 401 or code == "DH-901":
            raise self.ended()
        if code in ("DH-1111", "DH-907") and "holding" in msg.lower():       # "No holdings available"
            return []
        raise self.failed()

    def rows(self, raw: list[dict]) -> list[dict]:
        out = []
        for h in raw:
            # totalQty is "T1 qty + Delivered qty" (pledged shares are within it: availableQty is total less pledged)
            qty = _num(h.get("totalQty")) or (_num(h.get("dpQty")) + _num(h.get("t1Qty")))
            r = _row(h.get("tradingSymbol"), h.get("isin"), h.get("tradingSymbol"), qty, h.get("avgCostPrice"))
            if r:
                out.append(r)
        return merge_rows(out)


ALL: dict[str, Broker] = {b.key: b for b in (Upstox(), Dhan())}


# ---------- the login round trip ----------
def _h(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def _start_key(b: Broker, uid: str) -> str:
    return f"{START}{b.key}:{uid}"


def _pending_key(ref: str) -> str:
    return PENDING + _h(ref)[:40]


def read_state(st: str) -> tuple[str, str] | None:
    """(uid, broker) from a state this server made in the last 15 minutes; None if forged, expired or not one."""
    if not st.startswith(STATE_PREFIX):
        return None
    return mail_tokens.read(st[len(STATE_PREFIX):], PURPOSE)


def start(b: Broker, profile: dict) -> str:
    """Where to log in. Raises BrokerError when the broker didn't answer (Dhan asks for a login first)."""
    uid = profile["id"]
    st = STATE_PREFIX + mail_tokens.make(uid, PURPOSE, b.key)
    url, keep = b.login_url(st)
    db.set_setting(_start_key(b, uid), json.dumps({"st": _h(st), "at": time.time(), **keep}))
    return url


def _prune() -> None:
    for key, raw in db.all_settings_with_prefix(PENDING):
        if time.time() - float(db.json_value(raw, {}).get("at") or 0) > 3600:
            db.delete_setting(key)


def stage(b: Broker, params: dict) -> tuple[str, str]:
    """The broker's return, which anyone's browser can make: check the state, swap the login for a token, and keep it
    aside sealed (not on any account). (reference, claim) for the landing page. Raises BrokerError."""
    st = str(params.get("state") or "")
    uid = None
    if st:
        got = read_state(st)
        if not got or got[1] != b.key:
            raise BrokerError("This login link has expired. Start again from Settings.")
        uid = got[0]
        with _lock:
            rec = db.json_value(db.get_setting(_start_key(b, uid)), {})
            if not hmac.compare_digest(str(rec.get("st") or ""), _h(st)) or time.time() - float(rec.get("at") or 0) > START_TTL:
                raise BrokerError("This login link has already been used. Start again from Settings.")
            db.delete_setting(_start_key(b, uid))               # the state works once
    elif b.state_back == "yes":
        raise BrokerError("This login link has expired. Start again from Settings.")
    if not b.configured():
        raise BrokerError(f"{b.name} login isn't set up yet.")
    got = b.exchange(params)
    ref, claim = secrets.token_urlsafe(18), secrets.token_urlsafe(24)
    _prune()
    db.set_setting(_pending_key(ref), json.dumps({
        "broker": b.key, "uid": uid, "token": vault.seal(got["token"]), "account": got.get("account") or "",
        "expires_at": got["expires_at"].isoformat(timespec="seconds"), "claim": _h(claim), "at": time.time()}))
    return ref, claim


def confirm(b: Broker, profile: dict, ref: str, claim: str) -> dict:
    """Attach a staged login to the signed-in user: only the user it was started for (by the state, or else by their own
    Connect tap in the last 15 minutes), only with the claim the returning browser holds, and once. Raises BrokerError."""
    uid = profile["id"]
    if not b.allowed(profile):
        raise BrokerError(f"{b.name} login isn't open for this account yet.")
    with _lock:
        key = _pending_key(ref or "")
        rec = db.json_value(db.get_setting(key), {})
        ok = (rec.get("broker") == b.key and time.time() - float(rec.get("at") or 0) <= PENDING_TTL
              and hmac.compare_digest(str(rec.get("claim") or ""), _h(claim or "")))
        if ok and rec.get("uid"):
            ok = rec["uid"] == uid
        elif ok:                                                   # no state came back: the user's own tap must be fresh
            mine = db.json_value(db.get_setting(_start_key(b, uid)), {})
            ok = bool(mine) and 0 <= float(rec.get("at") or 0) - float(mine.get("at") or 0) <= START_TTL
            if ok:
                db.delete_setting(_start_key(b, uid))
        if not ok:
            raise BrokerError("This login has expired or isn't yours. Start again from Settings.")
        db.delete_setting(key)
    state.update(uid, b.key, token=rec["token"], account=rec.get("account") or "", expires_at=rec["expires_at"],
                 status="ok", detail=None, dead=None, connected_at=state.now())
    return refresh(b, uid)


def _ends(box: dict) -> datetime | None:
    try:
        return datetime.fromisoformat(str(box.get("expires_at") or ""))
    except ValueError:
        return None


def _live(box: dict) -> bool:
    ends = _ends(box)
    return bool(box.get("token")) and not box.get("dead") and ends is not None and _now() < ends


def refresh(b: Broker, uid: str) -> dict:
    """Read the holdings again with the stored token. Raises BrokerError(expired=True) when a login is needed."""
    box = state.section(uid, b.key)
    token = vault.unseal(box.get("token"))
    if not token:
        raise BrokerError(f"Connect {b.name} first.", expired=True)
    if not _live(box):
        state.update(uid, b.key, status="expired")
        raise b.ended()
    try:
        raw = b.fetch(token, str(box.get("account") or ""))
    except BrokerError as e:
        if e.expired:
            state.update(uid, b.key, status="expired", dead=True)
        else:
            state.update(uid, b.key, status="error", detail=e.message)
        raise
    rows = b.rows(raw)
    profile = sync.profile_for(uid)
    # an empty reply is a failed read, not "sold everything": what was read before stays
    got = sync.sync_holdings(profile, rows, b.key, b.source, replace=bool(raw))
    why = sync.note(got, b.name) or (None if raw or not rows else
                                     f"{b.name} returned no holdings, so the holdings read from it before are kept as they were.")
    state.update(uid, b.key, refreshed_at=state.now(), status="ok", detail=why, count=got["count"])
    return {"count": got["count"], "unmatched": got["unmatched_count"], "added": got["added"], "changed": got["changed"]}


def status(b: Broker, uid: str, profile: dict) -> dict:
    from .kite_user import when_label
    box = state.section(uid, b.key)
    live = _live(box)
    ends = _ends(box)
    return {"key": b.key, "name": b.name, "available": b.allowed(profile), "configured": b.configured(),
            "connected": bool(box.get("token")), "live": live, "expired": bool(box.get("token")) and not live,
            # when the broker ends this login by itself, so the card can say it
            "ends_at": ends.isoformat(timespec="minutes") if live and ends else None,
            "refreshed_at": box.get("refreshed_at"), "refreshed_label": when_label(box.get("refreshed_at")),
            "count": box.get("count"), "detail": box.get("detail"), "account": box.get("account") or None}


def statuses(uid: str, profile: dict) -> list[dict]:
    return [status(b, uid, profile) for b in ALL.values()]


def drop_pending(uid: str) -> None:
    """Delete the user's logins that wait to be confirmed and their Connect taps (a staged login holds a sealed token)."""
    for key, raw in db.all_settings_with_prefix(PENDING):
        if db.json_value(raw, {}).get("uid") == uid:
            db.delete_setting(key)
    for b in ALL.values():
        db.delete_setting(_start_key(b, uid))


def disconnect(b: Broker, uid: str) -> None:
    """Forget the connection: the stored token is deleted. The holdings it read stay, no longer tagged as the broker's
    (so a newer statement or file can replace them)."""
    state.drop(uid, b.key)
    db.delete_setting(_start_key(b, uid))
    from .. import holdings

    def untag(before):
        if not any(i.get("via") == b.key for i in before["items"]):
            return None
        return ([{k: v for k, v in i.items() if k != "via"} if i.get("via") == b.key else i for i in before["items"]],
                before.get("source") or b.source, True)
    holdings.update(uid, untag)


def read_summary(uid: str) -> list[dict]:
    """For My Holdings: each connected broker's last read ({key, name, live, count, read_at})."""
    out = []
    for b in ALL.values():
        box = state.section(uid, b.key)
        if box.get("token"):
            out.append({"key": b.key, "name": b.name, "live": _live(box), "count": box.get("count"), "read_at": box.get("refreshed_at")})
    return out
