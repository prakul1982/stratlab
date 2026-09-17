"""Supabase login check. The frontend sends the Supabase access token as a Bearer token."""
import threading
import time
from fastapi import Header, HTTPException

from . import db
from .plans import effective_plan

_cache: dict[str, tuple[float, str, str]] = {}
_lock = threading.Lock()


def current_profile(authorization: str | None = Header(None)) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, {"code": "login_required", "message": "Sign in to continue."})
    token = authorization.split(" ", 1)[1].strip()
    now = time.time()
    with _lock:
        hit = _cache.get(token)
    if hit and hit[0] > now:
        uid, email = hit[1], hit[2]
    else:
        try:
            user = db.sb().auth.get_user(token).user
        except Exception:
            user = None
        if not user:
            raise HTTPException(401, {"code": "login_required", "message": "Your session expired. Sign in again."})
        uid, email = user.id, user.email
        with _lock:
            if len(_cache) > 5000:
                _cache.clear()
            _cache[token] = (now + 60, uid, email)
    profile = db.get_profile(uid, email)
    profile["_plan"] = effective_plan(profile)
    return profile
