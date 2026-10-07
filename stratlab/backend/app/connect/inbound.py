"""The statement inbox: each user's private forwarding address, and the webhook the mail service posts incoming mail to.

Mail provider. The app already sends with Brevo (alerts.py), and Brevo has inbound parsing (MX records to its servers, a
webhook with the parsed mail), so that is the default adapter. Brevo does not sign its webhooks, so the secret
INBOUND_WEBHOOK_SECRET is part of the webhook URL (?k=...) and compared in constant time. The second adapter, "signed",
takes JSON signed with HMAC-SHA256 (header X-StratLab-Signature: t=<unix>,v1=<hex of HMAC(secret, "<t>.<body>")>), for
any forwarder the owner prefers (an email worker on the receiving domain, for example). Adding a provider is one more
Adapter class.

The endpoint answers every well-formed, authenticated post with 200 whatever it did with the mail, so an address that
doesn't exist can't be told from one that does. A bad signature is 401."""
import base64
import hashlib
import hmac
import json
import re
import secrets
import threading
import time
from dataclasses import dataclass, field
from email.utils import getaddresses
from typing import Callable, Mapping

import httpx

from ..config import settings
from .. import db
from . import state, statements, vault
from .redact import mask

LOCAL_RX = re.compile(r"^u-[a-z2-7]{20}$")
MAX_ATTACHMENTS = 6
MAX_MAILS_PER_DAY = 30               # per address: a statement or two a month is normal
MAX_POSTS_PER_MINUTE = 120           # to the endpoint as a whole (the mail service's own few addresses)
SIGNATURE_TOLERANCE = 300
BREVO_API = "https://api.brevo.com/v3"
FORWARD_CONFIRM_RX = re.compile(r"(?i)(?:confirmation code[^0-9]{0,20}|\(#)(\d{6,12})")


@dataclass
class Attachment:
    name: str
    content_type: str
    size: int
    load: Callable[[], bytes]


@dataclass
class Mail:
    recipients: list[str]
    sender: str = ""
    subject: str = ""
    text: str = ""
    message_id: str = ""
    attachments: list[Attachment] = field(default_factory=list)


class BadRequest(Exception):
    """An authentic post whose body isn't mail."""


# ---------- addresses ----------
def configured() -> bool:
    """The inbox works once the owner has set the receiving domain, the webhook secret and the encryption key."""
    return bool(settings.INBOUND_DOMAIN and settings.INBOUND_WEBHOOK_SECRET and vault.ready())


def _new_local() -> str:
    return "u-" + base64.b32encode(secrets.token_bytes(13)).decode().lower().rstrip("=")[:20]


def address_of(local: str) -> str:
    return f"{local}@{settings.INBOUND_DOMAIN}"


def ensure_address(uid: str) -> str | None:
    """The user's forwarding address (made on first use); None while the inbox isn't set up."""
    if not configured():
        return None
    box = state.section(uid, "inbox")
    if box.get("local"):
        return address_of(box["local"])
    with state._lock:
        box = state.section(uid, "inbox")
        if box.get("local"):
            return address_of(box["local"])
        for _ in range(5):
            local = _new_local()
            if not db.get_setting(state.INDEX + local):
                break
        db.set_setting(state.INDEX + local, uid)
        state.update(uid, "inbox", local=local, created_at=state.now())
    return address_of(local)


def new_address(uid: str) -> str | None:
    """A new address for a user, the old one stops working (if it leaked, or the filter should start again)."""
    if not configured():
        return None
    old = state.section(uid, "inbox").get("local")
    if old:
        db.delete_setting(state.INDEX + old)
        state.update(uid, "inbox", local=None)
    return ensure_address(uid)


def user_for(recipients: list[str]) -> str | None:
    dom = settings.INBOUND_DOMAIN
    for r in recipients:
        local, _, host = r.strip().lower().rpartition("@")
        if host == dom and LOCAL_RX.match(local):
            uid = db.get_setting(state.INDEX + local)
            if uid:
                return uid
    return None


# ---------- providers ----------
def _addr(v) -> list[str]:
    """Addresses out of a string, a {"Address"} object or a list of either."""
    out: list[str] = []
    for x in v if isinstance(v, list) else [v]:
        if isinstance(x, dict):
            a = x.get("Address") or x.get("address") or x.get("email")
            if a:
                out.append(str(a))
        elif isinstance(x, str):
            out += [a for _, a in getaddresses([x]) if a]
    return out


class Adapter:
    name = ""

    def verify(self, headers: Mapping[str, str], query: Mapping[str, str], body: bytes) -> bool:
        raise NotImplementedError

    def parse(self, body: bytes) -> list[Mail]:
        raise NotImplementedError


class BrevoAdapter(Adapter):
    """Brevo inbound parsing: {"items": [{From, To, Cc, Subject, ExtractedMarkdownMessage, MessageId, Attachments:
    [{Name, ContentType, ContentLength, DownloadToken}]}]}. An attachment is fetched with its DownloadToken from
    Brevo's API using BREVO_API_KEY."""
    name = "brevo"

    def __init__(self, transport: httpx.BaseTransport | None = None):
        self.transport = transport

    def verify(self, headers, query, body) -> bool:
        secret = settings.INBOUND_WEBHOOK_SECRET
        return bool(secret) and hmac.compare_digest(str(query.get("k", "")).encode(), secret.encode())

    def _fetch(self, token: str) -> bytes:
        if not settings.BREVO_API_KEY:
            raise BadRequest("no Brevo key")
        try:
            with httpx.Client(transport=self.transport, timeout=30, follow_redirects=False) as c:
                r = c.get(f"{BREVO_API}/inbound/attachments/{token}", headers={"api-key": settings.BREVO_API_KEY})
                r.raise_for_status()
                return r.content
        except httpx.HTTPError as e:
            raise BadRequest("attachment download failed: " + mask(type(e).__name__)) from None

    def parse(self, body: bytes) -> list[Mail]:
        try:
            data = json.loads(body)
        except ValueError:
            raise BadRequest("not JSON") from None
        items = data.get("items") if isinstance(data, dict) else None
        if not isinstance(items, list):
            raise BadRequest("no items")
        out = []
        for it in items[:20]:
            if not isinstance(it, dict):
                continue
            atts = []
            for a in it.get("Attachments") or []:
                if isinstance(a, dict) and a.get("DownloadToken"):
                    tok = str(a["DownloadToken"])
                    atts.append(Attachment(str(a.get("Name") or "")[:120], str(a.get("ContentType") or ""),
                                           int(a.get("ContentLength") or 0), lambda tok=tok: self._fetch(tok)))
            out.append(Mail(recipients=_addr(it.get("To")) + _addr(it.get("Cc")) + _addr(it.get("Bcc")),
                            sender=(_addr(it.get("From")) or [""])[0], subject=str(it.get("Subject") or "")[:300],
                            text=str(it.get("ExtractedMarkdownMessage") or it.get("RawTextBody") or "")[:5000],
                            message_id=str(it.get("MessageId") or "")[:200], attachments=atts))
        return out


class SignedAdapter(Adapter):
    """JSON signed with HMAC-SHA256: {"to": [...], "from", "subject", "text", "message_id", "attachments": [{"name",
    "content_type", "data_b64"}]}."""
    name = "signed"

    def verify(self, headers, query, body) -> bool:
        secret = settings.INBOUND_WEBHOOK_SECRET
        raw = {k.lower(): v for k, v in headers.items()}.get("x-stratlab-signature", "")
        parts = dict(p.split("=", 1) for p in raw.split(",") if "=" in p)
        try:
            stamp = int(parts.get("t", ""))
        except ValueError:
            return False
        if not secret or abs(time.time() - stamp) > SIGNATURE_TOLERANCE:
            return False
        want = hmac.new(secret.encode(), f"{stamp}.".encode() + body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(want, parts.get("v1", ""))

    def parse(self, body: bytes) -> list[Mail]:
        try:
            d = json.loads(body)
        except ValueError:
            raise BadRequest("not JSON") from None
        if not isinstance(d, dict):
            raise BadRequest("not an object")
        atts = []
        for a in d.get("attachments") or []:
            if not isinstance(a, dict) or not isinstance(a.get("data_b64"), str):
                continue
            raw = a["data_b64"]
            atts.append(Attachment(str(a.get("name") or "")[:120], str(a.get("content_type") or ""), len(raw) * 3 // 4,
                                   lambda raw=raw: base64.b64decode(raw, validate=False)))
        return [Mail(recipients=_addr(d.get("to")), sender=(_addr(d.get("from")) or [""])[0], subject=str(d.get("subject") or "")[:300],
                     text=str(d.get("text") or "")[:5000], message_id=str(d.get("message_id") or "")[:200], attachments=atts)]


ADAPTERS: dict[str, Callable[[], Adapter]] = {"brevo": BrevoAdapter, "signed": SignedAdapter}


def adapter_for(name: str) -> Adapter | None:
    """The adapter for a provider named in the URL, only when it is the one the owner configured."""
    if name != settings.INBOUND_PROVIDER or name not in ADAPTERS:
        return None
    return ADAPTERS[name]()


# ---------- rate limits ----------
_posts: dict[int, int] = {}
_per_user: dict[tuple[str, str], int] = {}
_lock = threading.Lock()


def _allow_post() -> bool:
    minute = int(time.time() // 60)
    with _lock:
        for k in [k for k in _posts if k != minute]:
            del _posts[k]
        _posts[minute] = _posts.get(minute, 0) + 1
        return _posts[minute] <= MAX_POSTS_PER_MINUTE


def _allow_user(uid: str) -> bool:
    day = time.strftime("%Y-%m-%d", time.gmtime())
    with _lock:
        for k in [k for k in _per_user if k[1] != day]:
            del _per_user[k]
        _per_user[(uid, day)] = _per_user.get((uid, day), 0) + 1
        return _per_user[(uid, day)] <= MAX_MAILS_PER_DAY


def forget_limits() -> None:
    with _lock:
        _posts.clear()
        _per_user.clear()


# ---------- handling ----------
def is_pdf(a: Attachment) -> bool:
    return a.name.lower().endswith(".pdf") or "pdf" in a.content_type.lower()


def _forwarding_code(mail: Mail) -> str | None:
    """Gmail asks the receiving address to confirm a forwarding address: the code is in the subject and the text."""
    if "forwarding-noreply@google.com" not in mail.sender.lower() and "forwarding confirmation" not in mail.subject.lower():
        return None
    m = FORWARD_CONFIRM_RX.search(mail.subject + "\n" + mail.text)
    return m.group(1) if m else None


def handle_mail(mail: Mail) -> dict:
    """One incoming mail for one user (unknown recipients are dropped): what happened, for the tests. Never raises."""
    uid = user_for(mail.recipients)
    if not uid:
        return {"handled": False}
    if not _allow_user(uid):
        return {"handled": False}
    box = state.section(uid, "inbox")
    if mail.message_id:
        seen = box.get("seen") or []
        if mail.message_id in seen:
            return {"handled": False}
        state.update(uid, "inbox", seen=(seen + [mail.message_id])[-30:])
    code = _forwarding_code(mail)
    if code:
        state.update(uid, "inbox", confirm={"code": code, "at": state.now()})
        return {"handled": True, "confirm": True}
    pdfs = [a for a in mail.attachments if is_pdf(a)][:MAX_ATTACHMENTS]
    if not pdfs:
        state.update(uid, "inbox", last={"at": state.now(), "status": "no_pdf", "kind": None, "via": "email",
                                         "detail": "An email arrived with no PDF statement attached."})
        return {"handled": True, "pdfs": 0}
    results = []
    for a in pdfs:
        if a.size and a.size > statements.MAX_PDF * 2:
            state.update(uid, "inbox", last={"at": state.now(), "status": "too_big", "kind": None, "via": "email",
                                             "detail": "The attached PDF is larger than a statement should be."})
            results.append({"ok": False, "status": "too_big"})
            continue
        try:
            data = a.load()
        except Exception as e:
            state.update(uid, "inbox", last={"at": state.now(), "status": "unreadable", "kind": None, "via": "email",
                                             "detail": "The attached PDF couldn't be downloaded."})
            results.append({"ok": False, "status": "unreadable", "detail": mask(str(e))[:100]})
            continue
        results.append(statements.process(uid, data, a.name, via="email"))
        data = b""
    return {"handled": True, "pdfs": len(pdfs), "results": results}


def receive(provider: str, headers: Mapping[str, str], query: Mapping[str, str], body: bytes) -> int:
    """The webhook: the HTTP status to answer with. 404 while off or for another provider, 429 over the limit, 401 for a
    bad signature or secret, 400 for a body that isn't mail, else 200."""
    ad = adapter_for(provider)
    if ad is None or not configured():
        return 404
    if not _allow_post():
        return 429
    if not ad.verify(headers, query, body):
        return 401
    try:
        mails = ad.parse(body)
    except BadRequest:
        return 400
    for m in mails:
        try:
            handle_mail(m)
        except Exception as e:                      # one bad mail never fails the post (the service would retry it)
            print("inbox: a mail could not be handled:", mask(type(e).__name__))
    return 200
