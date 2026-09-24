"""Automatic daily Kite login using the account's user ID, password and TOTP secret.

Zerodha's Kite Connect terms expect the daily login to be done by hand; automating it risks
the API key being revoked. It is off unless KITE_USER_ID, KITE_PASSWORD and KITE_TOTP_SECRET
are all set. Credentials are only read from the environment and never logged.

Zerodha locks an account after repeated wrong passwords or codes, so a rejected login is
not retried until the next day. Network errors are retried a few times."""
import base64
import hashlib
import hmac
import os
import re
import struct
import threading
import time
from datetime import datetime
from urllib.parse import parse_qs, urljoin, urlparse

import httpx

from .config import settings
from .kite_service import IST, KiteService

BASE = "https://kite.zerodha.com"
RETRY_MINUTES = 5
MAX_ATTEMPTS = 6


def configured() -> bool:
    return bool(settings.KITE_USER_ID and settings.KITE_PASSWORD and settings.KITE_TOTP_SECRET)


class AutoLoginError(Exception):
    def __init__(self, message: str, retry: bool = True):
        super().__init__(message)
        self.retry = retry


def clean_secret(raw: str) -> str:
    """Accept the key as Zerodha shows it: spaced, lower case, quoted, or inside an otpauth:// link."""
    s = raw.strip().strip("\"'")
    if s.lower().startswith("otpauth://"):
        s = parse_qs(urlparse(s).query).get("secret", [""])[0]
    s = re.sub(r"[\s-]", "", s).upper().rstrip("=")
    if not re.fullmatch(r"[A-Z2-7]{16,}", s):
        hint = " That looks like a 6-digit code from the app." if re.fullmatch(r"\d{6}", s) else ""
        raise AutoLoginError("KITE_TOTP_SECRET isn't a valid TOTP secret." + hint + " Use the key shown under the QR "
                             "code when setting up 2FA in Kite: 16 or more letters A-Z and digits 2-7.", retry=False)
    return s


def totp(secret: str, at: float | None = None, step: int = 30, digits: int = 6) -> str:
    """RFC 6238 code, the same one an authenticator app shows for this secret."""
    s = clean_secret(secret)
    key = base64.b32decode(s + "=" * (-len(s) % 8))
    counter = int((time.time() if at is None else at) // step)
    mac = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    o = mac[-1] & 0x0F
    code = (struct.unpack(">I", mac[o:o + 4])[0] & 0x7FFFFFFF) % 10 ** digits
    return str(code).zfill(digits)


def _json(r: httpx.Response) -> dict:
    try:
        body = r.json()
    except ValueError:
        raise AutoLoginError(f"Unexpected reply from Zerodha ({r.status_code}).")
    return body if isinstance(body, dict) else {}


def fetch_request_token(login_url: str, transport: httpx.BaseTransport | None = None) -> str:
    clean_secret(settings.KITE_TOTP_SECRET)
    with httpx.Client(timeout=20, transport=transport, follow_redirects=False,
                      headers={"User-Agent": "Mozilla/5.0 (StratLab auto-login)"}) as c:
        c.get(login_url, follow_redirects=True)  # picks up Kite's session cookies
        body = _json(c.post(f"{BASE}/api/login",
                            data={"user_id": settings.KITE_USER_ID, "password": settings.KITE_PASSWORD}))
        if body.get("status") != "success":
            raise AutoLoginError(f"Zerodha rejected the user ID or password: {body.get('message', 'no reason given')}",
                                 retry=False)
        request_id = (body.get("data") or {}).get("request_id")
        if not request_id:
            raise AutoLoginError("Zerodha's login reply had no request ID.")
        if 30 - time.time() % 30 < 3:  # the current code is about to expire: wait for a fresh one
            time.sleep(4)
        body = _json(c.post(f"{BASE}/api/twofa", data={
            "user_id": settings.KITE_USER_ID, "request_id": request_id,
            "twofa_value": totp(settings.KITE_TOTP_SECRET), "twofa_type": "totp"}))
        if body.get("status") != "success":
            raise AutoLoginError(f"Zerodha rejected the TOTP code: {body.get('message', 'no reason given')}. "
                                 "Check KITE_TOTP_SECRET and the server clock.", retry=False)
        # With the session cookies set, the Connect login redirects to our callback with a request token
        url = login_url
        for _ in range(10):
            loc = c.get(url).headers.get("location")
            if not loc:
                break
            url = urljoin(url, loc)
            token = parse_qs(urlparse(url).query).get("request_token")
            if token:
                return token[0]
        raise AutoLoginError("Logged in, but Zerodha didn't hand back a request token. Log in once through "
                             "/admin/kite/login to authorise the app, then try again.", retry=False)


def login_due(now: datetime, token_day: str | None) -> bool:
    """A login is due once a day, after KITE_AUTO_LOGIN_AT, unless today's token is already saved."""
    if token_day == now.date().isoformat():
        return False
    try:
        hh, mm = (int(x) for x in settings.KITE_AUTO_LOGIN_AT.split(":"))
    except ValueError:
        hh, mm = 8, 0
    return (now.hour, now.minute) >= (hh, mm)


class AutoLogin:
    def __init__(self, kite: KiteService, on_login):
        self.kite, self.on_login = kite, on_login
        self.last = {"at": None, "ok": None, "message": "Not run yet." if configured() else "Not configured."}
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._day: str | None = None
        self._attempts = 0
        self._gave_up = False

    def start(self):
        if configured() and not self._thread:
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()

    def run_once(self) -> bool:
        if not configured():
            raise AutoLoginError("Set KITE_USER_ID, KITE_PASSWORD and KITE_TOTP_SECRET first.", retry=False)
        with self._lock:  # never run two logins at once
            try:
                request_token = fetch_request_token(self.kite.kite.login_url())
                self.kite.accept_request_token(request_token)
            except Exception as e:
                self._record(False, str(e))
                if isinstance(e, AutoLoginError) and not e.retry:
                    self._gave_up = True
                raise
            self._record(True, "Logged in to Kite.")
        self.on_login()
        return True

    def _record(self, ok: bool, message: str):
        self.last = {"at": datetime.now(IST).isoformat(), "ok": ok, "message": message}
        print("Kite auto-login:", message)

    def _alert(self, text: str):
        if settings.ADMIN_TELEGRAM_CHAT_ID:
            from .alerts import send_telegram
            try:
                send_telegram(settings.ADMIN_TELEGRAM_CHAT_ID, text)
            except Exception as e:
                print("admin alert failed:", e)

    def _loop(self):
        while True:
            now = datetime.now(IST)
            day = now.date().isoformat()
            if day != self._day:
                self._day, self._attempts, self._gave_up = day, 0, False
            if not self._gave_up and self._attempts < MAX_ATTEMPTS and login_due(now, self.kite.token_day):
                self._attempts += 1
                try:
                    self.run_once()
                except Exception as e:
                    if self._gave_up or self._attempts >= MAX_ATTEMPTS:
                        self._alert(f"StratLab: Kite auto-login failed and won't retry today. {e} "
                                    f"Log in by hand at /admin/kite/login.")
                    time.sleep(RETRY_MINUTES * 60)
                    continue
            time.sleep(30)


def restart_process(delay: float = 2.0):
    """KiteTicker can't reconnect with a new token inside one process, so exit and let the host restart us.
    A non-zero code makes Railway's ON_FAILURE policy (and most hosts) start a fresh process."""
    threading.Timer(delay, os._exit, args=(3,)).start()
