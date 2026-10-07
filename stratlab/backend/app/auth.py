"""Supabase login check. The frontend sends the Supabase access token as a Bearer token."""
import threading
import time
from fastapi import Header, HTTPException

from . import db
from .plans import access_plan, effective_plan

_cache: dict[str, tuple[float, str, str, bool, str | None]] = {}     # token -> (until, id, email, verified, sign-in method)
_rejected: dict[str, float] = {}          # tokens the sign-in service just refused, until when
_lock = threading.Lock()


def _unreachable(e: Exception) -> bool:
    """A sign-in check that failed because the service couldn't be reached, not because the token is bad."""
    try:
        from supabase_auth.errors import AuthApiError, AuthRetryableError
    except ImportError:                              # older client names
        return False
    if isinstance(e, AuthRetryableError):
        return True
    if isinstance(e, AuthApiError):
        return False
    import httpx
    return isinstance(e, (httpx.TransportError, ConnectionError, TimeoutError))


def current_profile(authorization: str | None = Header(None)) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, {"code": "login_required", "message": "Sign in to continue."})
    token = authorization.split(" ", 1)[1].strip()
    now = time.time()
    with _lock:
        hit = _cache.get(token)
        bad = _rejected.get(token)
    if bad and bad > now:                           # the same made-up or expired token again: no sign-in service call
        raise HTTPException(401, {"code": "login_required", "message": "Your session expired. Sign in again."})
    if hit and hit[0] > now:
        uid, email, verified, method = hit[1], hit[2], hit[3], hit[4]
    else:
        try:
            user = db.sb().auth.get_user(token).user
        except Exception as e:
            if _unreachable(e):                     # the sign-in service is down: don't tell people they're signed out
                raise HTTPException(503, {"code": "auth_unavailable", "message": "Sign-in isn't answering right now. "
                                          "You're still signed in; try again in a minute."}) from None
            user = None
        if not user:
            with _lock:
                if len(_rejected) > 20000:
                    _rejected.clear()
                _rejected[token] = now + 60
            raise HTTPException(401, {"code": "login_required", "message": "Your session expired. Sign in again."})
        uid, email = user.id, user.email
        # only an address proven by Google sign-in is trusted for admin access: Supabase's own email sign-up can be
        # called by anyone with the public key, and whether it confirms addresses is a dashboard setting
        meta = getattr(user, "app_metadata", None) or {}
        providers = set(meta.get("providers") or []) | {meta.get("provider")}
        verified = bool(getattr(user, "email_confirmed_at", None)) and "google" in providers
        method = meta.get("provider") or next((p for p in meta.get("providers") or [] if p), None)   # how they signed in, for Account
        with _lock:
            if len(_cache) > 5000:
                _cache.clear()
            _cache[token] = (now + 60, uid, email, verified, method)
    profile = db.cached_profile(uid, email)
    profile["_paid_plan"] = effective_plan(profile)
    profile["_plan"] = access_plan(profile)       # Pro for everyone during the launch offer
    # the profile keeps the address from sign-up; trust it only while it's still the one Google just proved
    same = (profile.get("email") or "").strip().lower() == (email or "").strip().lower()
    profile["_email_verified"] = verified and same
    profile["_signed_in_with"] = method if isinstance(method, str) else None
    # the site owner uses every feature (what they pay for is unchanged); only a Google-proved admin address counts
    from . import admin
    if admin.is_admin(profile):
        profile["_plan"] = "pro"
    return profile
