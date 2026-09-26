"""Supabase login check. The frontend sends the Supabase access token as a Bearer token."""
import threading
import time
from fastapi import Header, HTTPException

from . import db
from .plans import effective_plan

_cache: dict[str, tuple[float, str, str, bool]] = {}
_lock = threading.Lock()


def current_profile(authorization: str | None = Header(None)) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, {"code": "login_required", "message": "Sign in to continue."})
    token = authorization.split(" ", 1)[1].strip()
    now = time.time()
    with _lock:
        hit = _cache.get(token)
    if hit and hit[0] > now:
        uid, email, verified = hit[1], hit[2], hit[3]
    else:
        try:
            user = db.sb().auth.get_user(token).user
        except Exception:
            user = None
        if not user:
            raise HTTPException(401, {"code": "login_required", "message": "Your session expired. Sign in again."})
        uid, email = user.id, user.email
        # Google sign-in always verifies the address; only a verified one is trusted for admin access
        verified = bool(getattr(user, "email_confirmed_at", None))
        with _lock:
            if len(_cache) > 5000:
                _cache.clear()
            _cache[token] = (now + 60, uid, email, verified)
    profile = db.cached_profile(uid, email)
    profile["_plan"] = effective_plan(profile)
    profile["_email_verified"] = verified
    return profile
