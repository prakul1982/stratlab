"""Automatic daily Kite login using the account's user ID, password and TOTP secret.

Zerodha's Kite Connect terms expect the daily login to be done by hand; automating it risks
the API key being revoked. It is off unless KITE_USER_ID, KITE_PASSWORD and KITE_TOTP_SECRET
are all set. Credentials are only read from the environment and never logged.

Zerodha locks an account after repeated wrong passwords or codes, so a rejected password is
not retried until the next day. A CAPTCHA demand is different: the password was right, but Zerodha wants a picture
puzzle for this session (it asks now and then for a fresh, unfamiliar session, most mornings on 27-28 Oct 2026). A new
session a little later goes through without one, so it is tried again with a fresh session: once after 30 s within
the run, then by the daily loop every few minutes, as a network error is. A rejected code gets exactly one more try with the next
30-second code: Zerodha refuses a code that was already used, which happens when another
program logs in to the same account in the same window. Network errors are retried a few times."""
import base64
import hashlib
import hmac
import json
import os
import re
import struct
import threading
import time
from datetime import datetime
from urllib.parse import parse_qs, urljoin, urlparse

import httpx

from . import leader
from .config import settings
from .kite_service import IST, KiteService

BASE = "https://kite.zerodha.com"
RETRY_MINUTES = 5
MAX_ATTEMPTS = 6
CAPTCHA_WAIT_S = 30
# Admin -> Data and jobs, which opens Zerodha's login page at once when it is reached from this link
LOGIN_LINK = "/admin/data?kite=login"
# a browser's own headers: a login that names itself a script is the kind Zerodha meets with a CAPTCHA
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
                         "Chrome/130.0.0.0 Safari/537.36",
           "Accept-Language": "en-IN,en;q=0.9", "X-Kite-Version": "3", "Origin": BASE, "Referer": f"{BASE}/"}


def is_captcha(message: str) -> bool:
    return "captcha" in (message or "").lower()


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


def fetch_request_token(login_url: str, transport: httpx.BaseTransport | None = None,
                        sleep=time.sleep) -> str:
    clean_secret(settings.KITE_TOTP_SECRET)
    for session in (1, 2):
        try:
            return _login_once(login_url, transport)
        except AutoLoginError as e:
            if not getattr(e, "captcha", False) or session == 2:
                raise
            sleep(CAPTCHA_WAIT_S)          # a new session in a moment usually goes through without the puzzle
    raise AssertionError("unreachable")


def _login_once(login_url: str, transport: httpx.BaseTransport | None) -> str:
    with httpx.Client(timeout=20, transport=transport, follow_redirects=False, headers=HEADERS) as c:
        c.get(login_url, follow_redirects=True)  # picks up Kite's session cookies
        body = _json(c.post(f"{BASE}/api/login",
                            data={"user_id": settings.KITE_USER_ID, "password": settings.KITE_PASSWORD}))
        if body.get("status") != "success":
            reason = body.get("message", "no reason given")
            if is_captcha(reason):
                # the password was accepted as far as Zerodha says; it wants a CAPTCHA for this session: try again later
                err = AutoLoginError("Zerodha asked for a CAPTCHA for this login session; trying again with a new "
                                     "session shortly.", retry=True)
                err.captcha = True
                raise err
            raise AutoLoginError(f"Zerodha rejected the user ID or password: {reason}", retry=False)
        request_id = (body.get("data") or {}).get("request_id")
        if not request_id:
            raise AutoLoginError("Zerodha's login reply had no request ID.")
        if 30 - time.time() % 30 < 3:  # the current code is about to expire: wait for a fresh one
            time.sleep(4)
        for attempt in (1, 2):
            body = _json(c.post(f"{BASE}/api/twofa", data={
                "user_id": settings.KITE_USER_ID, "request_id": request_id,
                "twofa_value": totp(settings.KITE_TOTP_SECRET), "twofa_type": "totp"}))
            if body.get("status") == "success":
                break
            if attempt == 1:
                # most often the code was just used by another login on this account: wait for the next one
                time.sleep(30 - time.time() % 30 + 2)
                continue
            raise AutoLoginError(f"Zerodha rejected the TOTP code twice: {body.get('message', 'no reason given')}. "
                                 "If another program logs in to this Zerodha account at about the same time, move "
                                 "KITE_AUTO_LOGIN_AT a few minutes away from it. Otherwise check KITE_TOTP_SECRET "
                                 "and the server clock.", retry=False)
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
                             "the Admin page (Log in to Kite) to authorise the app, then try again.", retry=False)


def login_time(now: datetime) -> datetime:
    """Today's automatic login time (KITE_AUTO_LOGIN_AT, India time)."""
    try:
        hh, mm = (int(x) for x in settings.KITE_AUTO_LOGIN_AT.split(":"))
    except ValueError:
        hh, mm = 8, 0
    return now.replace(hour=hh, minute=mm, second=0, microsecond=0)


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

    def next_login(self, now: datetime) -> datetime | None:
        """When Indian data will come back by itself: today's login time if it hasn't come yet."""
        if not configured():
            return None
        at = login_time(now)
        return at if now < at else None

    def start(self):
        if configured() and not self._thread:
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()

    def run_once(self, only_if_due: bool = False, now: datetime | None = None) -> bool:
        """Log in now (Admin's button). With `only_if_due` (the daily loop) a login another run finished while this one
        waited for the lock is not repeated: a second login cancels the first one's token."""
        if not configured():
            raise AutoLoginError("Set KITE_USER_ID, KITE_PASSWORD and KITE_TOTP_SECRET first.", retry=False)
        with self._lock:  # never run two logins at once
            if only_if_due and not login_due(now or datetime.now(IST), self.kite.token_day):
                return False
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
        try:  # kept in the database so a restart (the one after a manual login, say) doesn't lose it
            from . import db
            db.set_setting("kite_auto_login_last", json.dumps(self.last))
        except Exception as e:
            print("could not save the auto-login result:", e)

    def load_last(self):
        try:
            from . import db
            raw = db.get_setting("kite_auto_login_last")
            if raw and configured():
                self.last = json.loads(raw)
        except Exception as e:
            print("could not load the auto-login result:", e)

    ALERT_DEDUPE_S = 600

    def alert_once(self, event: str, text: str, now: float | None = None) -> bool:
        """`_alert` once per event within ALERT_DEDUPE_S, across containers (the last time is kept in app_settings): the token
        cancelled by Zerodha is seen by every container and every thread that calls Kite (R29B-006: two emails in the same
        second). False when the event was told a moment ago."""
        from . import db
        now = time.time() if now is None else now
        key = f"admin-alert-at:{event}"
        try:
            last = float(db.get_setting(key) or 0)
        except Exception:
            last = 0.0
        if 0 <= now - last < self.ALERT_DEDUPE_S:
            return False
        try:
            db.set_setting(key, str(now))
        except Exception as e:
            print("could not keep the alert time:", e)
        self._alert(text)
        return True

    def _alert(self, text: str, url: str = "/admin"):
        from .alerts import tell_admins
        from .errors import note
        note(text)
        try:
            tell_admins(text.split(". ")[0][:120], text, url=url)
        except Exception as e:
            print("admin alert failed:", e)
        if settings.ADMIN_TELEGRAM_CHAT_ID:
            from .alerts import send_telegram
            try:
                send_telegram(settings.ADMIN_TELEGRAM_CHAT_ID, text)
            except Exception as e:
                print("admin alert failed:", e)

    def login_now(self, now: datetime) -> bool:
        """Whether a login is due here. The saved token is read again first: a container that booted before another
        one's login today still holds yesterday's, and logging in again would cancel that one's token."""
        if not login_due(now, self.kite.token_day):
            return False
        try:
            self.kite.load_saved_token()
        except Exception as e:
            print("Kite auto-login: could not read the saved token:", str(e)[:160])
            return False
        if login_due(now, self.kite.token_day):
            return True
        try:                       # today's token, saved by the other container: bring data online with it
            self.on_login()
        except Exception as e:
            print("Kite auto-login: could not go online with the saved token:", str(e)[:160])
        return False

    def _loop(self):
        while True:
            now = datetime.now(IST)
            day = now.date().isoformat()
            if day != self._day:
                self._day, self._attempts, self._gave_up = day, 0, False
            # only the leading container logs in: a second login cancels the first one's token
            if not self._gave_up and self._attempts < MAX_ATTEMPTS and leader.leading() and self.login_now(now):
                self._attempts += 1
                try:
                    self.run_once(only_if_due=True)
                except Exception as e:
                    if self._gave_up or self._attempts >= MAX_ATTEMPTS:
                        # to every admin's phone and email: the link opens Zerodha's own login page in one tap
                        self._alert(f"StratLab: today's Zerodha login needs you. {e} Tap to log in to Zerodha "
                                    f"(about 10 seconds); Indian live data comes back as soon as you do.", url=LOGIN_LINK)
                    time.sleep(RETRY_MINUTES * 60)
                    continue
            time.sleep(30)


def restart_process(delay: float = 2.0):
    """KiteTicker can't reconnect with a new token inside one process, so exit and let the host restart us.
    A non-zero code makes Railway's ON_FAILURE policy (and most hosts) start a fresh process."""
    def leave():
        leader.current.release()   # the next container takes over now, not when the lease runs out
        os._exit(3)
    threading.Timer(delay, leave).start()
