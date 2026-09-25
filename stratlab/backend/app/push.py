"""Phone and browser notifications (Web Push), a channel like Telegram and email.

Each device that turns notifications on sends its push subscription, kept in app_settings under
"push:<user id>". Needs a VAPID key pair in the environment; generate one with
`python -m app.push keys`. Without keys, the feature stays off and the button explains why."""
import json

from . import db
from .config import settings

PREFIX = "push:"
MAX_DEVICES = 10


def enabled() -> bool:
    return bool(settings.VAPID_PUBLIC_KEY and settings.VAPID_PRIVATE_KEY)


def devices(uid: str) -> list[dict]:
    try:
        subs = json.loads(db.get_setting(PREFIX + uid) or "[]")
        return subs if isinstance(subs, list) else []
    except Exception:
        return []


def _save(uid: str, subs: list[dict]):
    if subs:
        db.set_setting(PREFIX + uid, json.dumps(subs[-MAX_DEVICES:]))
    else:
        db.delete_setting(PREFIX + uid)


def add(uid: str, sub: dict):
    subs = [s for s in devices(uid) if s.get("endpoint") != sub["endpoint"]]
    _save(uid, subs + [sub])


def remove(uid: str, endpoint: str):
    _save(uid, [s for s in devices(uid) if s.get("endpoint") != endpoint])


def send(uid: str, title: str, body: str, url: str = "/", tag: str | None = None) -> int:
    """Send to every device the user turned on. Devices that have gone away are forgotten. Returns how many got it."""
    if not enabled():
        return 0
    from pywebpush import WebPushException, webpush
    subs = devices(uid)
    sent, gone = 0, []
    payload = json.dumps({"title": title[:120], "body": body[:600], "url": url, "tag": tag})
    for s in subs:
        try:
            webpush(subscription_info=s, data=payload, vapid_private_key=settings.VAPID_PRIVATE_KEY,
                    vapid_claims={"sub": settings.VAPID_SUBJECT or "mailto:admin@stratlab.studio"}, ttl=3600)
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
        _save(uid, [s for s in subs if s.get("endpoint") not in gone])
    return sent


if __name__ == "__main__":   # python -m app.push keys
    import base64
    import sys

    from cryptography.hazmat.primitives import serialization
    from py_vapid import Vapid01

    if sys.argv[1:] != ["keys"]:
        raise SystemExit("usage: python -m app.push keys")
    v = Vapid01()
    v.generate_keys()
    raw_pub = v.public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    raw_priv = v.private_key.private_numbers().private_value.to_bytes(32, "big")
    b64 = lambda b: base64.urlsafe_b64encode(b).rstrip(b"=").decode()
    print(f"VAPID_PUBLIC_KEY={b64(raw_pub)}\nVAPID_PRIVATE_KEY={b64(raw_priv)}\nVAPID_SUBJECT=mailto:you@example.com")
