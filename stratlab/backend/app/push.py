"""Phone and browser notifications (Web Push), a channel like Telegram and email.

Each device that turns notifications on sends its push subscription, kept in app_settings under
"push:<user id>". Signing needs a VAPID key pair: the server makes one the first time it's needed and
keeps it in app_settings (the owner chose this over setting it by hand), so there's nothing to set up.
VAPID_PUBLIC_KEY / VAPID_PRIVATE_KEY in the environment take precedence if set."""
import json
from urllib.parse import urlsplit

from . import db
from .config import settings

PREFIX = "push:"
KEYS = "vapid:keys"
MAX_DEVICES = 10
PUSH_TIMEOUT = 10                  # seconds a push service gets to answer: one stalled endpoint must not hold the caller
_cache: dict = {}
# The browsers' own push services. A subscription pointing anywhere else is refused, so the server can't be
# made to send requests to an address of the user's choosing.
PUSH_HOSTS = ("fcm.googleapis.com", "android.googleapis.com", "updates.push.services.mozilla.com",
              "push.services.mozilla.com", "web.push.apple.com", ".push.apple.com", ".notify.windows.com")


def valid_endpoint(url: str) -> bool:
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" or not host or parts.username or parts.password or parts.port not in (None, 443):
        return False
    return any(host == h.lstrip(".") or (h.startswith(".") and host.endswith(h)) for h in PUSH_HOSTS)


def generate() -> tuple[str, str]:
    """A new key pair as base64url strings: the public key as an uncompressed point, the private key raw."""
    import base64

    from cryptography.hazmat.primitives import serialization
    from py_vapid import Vapid01

    v = Vapid01()
    v.generate_keys()
    raw_pub = v.public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    raw_priv = v.private_key.private_numbers().private_value.to_bytes(32, "big")
    b64 = lambda b: base64.urlsafe_b64encode(b).rstrip(b"=").decode()
    return b64(raw_pub), b64(raw_priv)


def keys() -> tuple[str, str] | None:
    """(public, private): from the environment if set, else the saved pair, else a new pair saved now."""
    if settings.VAPID_PUBLIC_KEY and settings.VAPID_PRIVATE_KEY:
        return settings.VAPID_PUBLIC_KEY, settings.VAPID_PRIVATE_KEY
    if "pair" in _cache:
        return _cache["pair"]
    try:
        saved = json.loads(db.get_setting(KEYS) or "null")
        if not (isinstance(saved, dict) and saved.get("public") and saved.get("private")):
            pub, priv = generate()
            db.set_setting(KEYS, json.dumps({"public": pub, "private": priv}))
            saved = json.loads(db.get_setting(KEYS) or "null") or {"public": pub, "private": priv}   # another worker may have won
        _cache["pair"] = (saved["public"], saved["private"])
        return _cache["pair"]
    except Exception as e:
        print("push keys unavailable:", str(e)[:200])
        return None


def public_key() -> str | None:
    k = keys()
    return k[0] if k else None


def enabled() -> bool:
    return keys() is not None


def devices(uid: str) -> list[dict]:
    try:
        subs = json.loads(db.get_setting(PREFIX + uid) or "[]")
        return subs if isinstance(subs, list) else []
    except Exception:
        return []


def _drop(uid: str, gone: set, add: dict | None = None):
    """Take the `gone` endpoints out of the user's list (and put `add` last), reading the list again at the moment of
    writing (db.update_setting), so a device added meanwhile is kept."""
    def go(cur):
        try:
            subs = json.loads(cur or "[]")
        except ValueError:
            subs = []
        subs = [s for s in subs if isinstance(s, dict) and s.get("endpoint") not in gone]
        if add:
            subs.append(add)
        return json.dumps(subs[-MAX_DEVICES:]) if subs else db.REMOVE
    db.update_setting(PREFIX + uid, go)


def add(uid: str, sub: dict):
    _drop(uid, {sub["endpoint"]}, sub)
    try:                  # a browser that signs in as someone else is still the same endpoint: the earlier user stops getting its pushes
        for key, raw in db.all_settings_with_prefix(PREFIX):
            other = key[len(PREFIX):]
            if other != uid and sub["endpoint"] in raw and any(isinstance(s, dict) and s.get("endpoint") == sub["endpoint"]
                                                               for s in json.loads(raw)):
                _drop(other, {sub["endpoint"]})
    except Exception as e:
        print("push: other users' copies of an endpoint not cleared:", str(e)[:200])


def remove(uid: str, endpoint: str):
    _drop(uid, {endpoint})


def send(uid: str, title: str, body: str, url: str = "/", tag: str | None = None) -> int:
    """Send to every device the user turned on. Devices that have gone away are forgotten. Returns how many got it."""
    k = keys()
    if not k:
        return 0
    from pywebpush import WebPushException, webpush
    subs = devices(uid)
    sent, gone = 0, []
    payload = json.dumps({"title": title[:120], "body": body[:600], "url": url, "tag": tag})
    for s in subs:
        if not valid_endpoint(s.get("endpoint") or ""):
            gone.append(s.get("endpoint"))
            continue
        try:
            webpush(subscription_info=s, data=payload, vapid_private_key=k[1],
                    vapid_claims={"sub": settings.VAPID_SUBJECT or "mailto:admin@stratlab.studio"}, ttl=3600,
                    timeout=PUSH_TIMEOUT)
            sent += 1
        except WebPushException as e:
            code = getattr(getattr(e, "response", None), "status_code", None)
            if code in (404, 410):
                gone.append(s.get("endpoint"))
            else:
                print("push failed:", code, str(e)[:200])
        except Exception as e:           # network trouble with one push service must not stop the others
            print("push failed:", str(e)[:200])
    if gone:
        _drop(uid, set(gone))
    return sent


if __name__ == "__main__":   # python -m app.push keys
    import sys

    if sys.argv[1:] != ["keys"]:
        raise SystemExit("usage: python -m app.push keys")
    pub, priv = generate()
    print(f"VAPID_PUBLIC_KEY={pub}\nVAPID_PRIVATE_KEY={priv}\nVAPID_SUBJECT=mailto:you@example.com")
