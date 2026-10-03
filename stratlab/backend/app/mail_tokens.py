"""Signed links in emails: unsubscribe (never expires) and email confirmation (3 days).

A token carries the user id, what it's for and one extra value (which newsletter, which address), signed with
HMAC-SHA256, so the link works without signing in but can't be made up or changed."""
import base64
import hashlib
import hmac
import json
import os
import time

from .config import settings

EXPIRES = {"confirm": 3 * 86400}     # seconds; purposes not listed never expire
_fallback = os.urandom(32)            # only with no secret configured at all (local runs): links stop working on restart


def _secret() -> bytes:
    if settings.MAIL_TOKEN_SECRET:
        return settings.MAIL_TOKEN_SECRET.encode()
    if settings.SUPABASE_SERVICE_KEY:   # a separate key derived from it, so the service key itself never signs links
        return hashlib.sha256(b"stratlab-mail-tokens:" + settings.SUPABASE_SERVICE_KEY.encode()).digest()
    return _fallback


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _sign(payload: str) -> str:
    return _b64(hmac.new(_secret(), payload.encode(), hashlib.sha256).digest()[:20])


def make(uid: str, purpose: str, extra: str = "") -> str:
    payload = _b64(json.dumps([uid, purpose, extra, int(time.time())], separators=(",", ":")).encode())
    return f"{payload}.{_sign(payload)}"


def read(token: str, purpose: str) -> tuple[str, str] | None:
    """(uid, extra) from a token made for this purpose, or None if it's forged, for something else or expired."""
    try:
        payload, sig = (token or "").split(".")
        if not hmac.compare_digest(sig, _sign(payload)):
            return None
        uid, what, extra, at = json.loads(_unb64(payload))
    except (ValueError, TypeError, UnicodeDecodeError):
        return None
    if what != purpose or not isinstance(uid, str) or not uid or not isinstance(extra, str) or not isinstance(at, int):
        return None
    if purpose in EXPIRES and time.time() - at > EXPIRES[purpose]:
        return None
    return uid, extra
