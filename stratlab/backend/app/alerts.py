"""Trade alerts and the daily report: phone notifications, Telegram and email.

A channel the server isn't set up for (no Telegram bot token, no email settings) is skipped rather than failing
the others, and the Account page doesn't offer it."""
import hashlib
import hmac
import json
import secrets
import smtplib
import threading
import time
from email.message import EmailMessage
import httpx
from .config import settings


def telegram_ready() -> bool:
    return bool(settings.TELEGRAM_BOT_TOKEN)


def email_ready() -> bool:
    return email_service() is not None


def email_service() -> str | None:
    """Which service sends the server's email, in the order send_email tries them: "Brevo", "Resend", "SMTP", or None
    when none is set up. Admin shows it, so Overview and System name the same one."""
    if settings.BREVO_API_KEY:
        return "Brevo"
    if settings.RESEND_API_KEY:
        return "Resend"
    if settings.SMTP_HOST and settings.SMTP_USER and settings.SMTP_PASSWORD:
        return "SMTP"
    return None


# Resend's shared sender: it delivers only to the address the Resend account was made with, until a domain of your
# own is verified there (then set ALERT_FROM_EMAIL to an address on it)
RESEND_FROM = "StratLab <onboarding@resend.dev>"


def _refused(service: str, r) -> RuntimeError:
    try:
        why = str((r.json() or {}).get("message") or "")[:400]
    except ValueError:
        why = ""
    if service == "Brevo" and "IP address" in why:
        # Brevo's "Authorized IPs": the server's address changes with each deploy, so naming the switch beats the link
        why = ("Brevo only accepts emails from addresses you approved, and this server's address isn't one. In Brevo, "
               "open your name (top right) → Security → Authorized IPs and turn IP blocking off. " + why)
    return RuntimeError(f"{service} refused the email ({r.status_code}). {why}".strip())


def _send_resend(to: str, subject: str, body: str, html: str | None = None, headers: dict | None = None) -> None:
    msg = {"from": settings.ALERT_FROM_EMAIL or RESEND_FROM, "to": [to], "subject": subject, "text": body}
    if settings.REPLY_TO_EMAIL:
        msg["reply_to"] = settings.REPLY_TO_EMAIL
    if html:
        msg["html"] = html
    if headers:
        msg["headers"] = headers
    r = httpx.post("https://api.resend.com/emails", timeout=15,
                   headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"}, json=msg)
    if r.status_code >= 400:
        raise _refused("Resend", r)


def _brevo_sender() -> str:
    """Brevo sends only from an address verified in the Brevo account. ALERT_FROM_EMAIL names it; without it the
    first admin's address is used, since the owner usually signs up to Brevo with it (verified at sign-up)."""
    if settings.ALERT_FROM_EMAIL:
        return settings.ALERT_FROM_EMAIL
    first = next((e.strip() for e in settings.ADMIN_EMAILS.split(",") if e.strip()), "")
    if not first:
        raise RuntimeError("Email has no sender address: set ALERT_FROM_EMAIL to an address verified in Brevo.")
    return first


# Brevo's open and click tracking rewrites every link to its own sendibt2/3.com host and adds a pixel (R6V-016, R15-005,
# R23-001). Brevo reads these headers on a message (the transactional API's `headers` and its SMTP relay alike) to leave
# one untracked: X-Mailin-Track turns both off, the other two each one. The account's own tracking setting in Brevo is
# still the switch to check if a message ever arrives tracked.
NO_TRACKING = {"X-Mailin-Track": "0", "X-Mailin-Track-Clicks": "0", "X-Mailin-Track-Opens": "0"}


def manage_unsubscribe_headers() -> dict:
    """List-Unsubscribe for an email that has no unsubscribe of its own (receipts, plan changes, test emails, the
    confirm-your-address email, admin notes): StratLab's own Manage emails page, so the mail app's Unsubscribe button
    never falls back to the mail service's link, which would block the address there, receipts included (R23-001). No
    One-Click header: the page is where the reader chooses, nothing is turned off by the button alone."""
    from .email_kit import MANAGE_NEWSLETTERS
    return {"List-Unsubscribe": f"<{email_link_base()}{MANAGE_NEWSLETTERS}>"}


def _send_brevo(to: str, subject: str, body: str, html: str | None = None, headers: dict | None = None) -> None:
    msg = {"sender": {"name": "StratLab", "email": _brevo_sender()}, "to": [{"email": to}], "subject": subject,
           "textContent": body}
    if settings.REPLY_TO_EMAIL:
        msg["replyTo"] = {"email": settings.REPLY_TO_EMAIL}
    if html:
        msg["htmlContent"] = html
    msg["headers"] = {**(headers or {}), **NO_TRACKING}       # every StratLab email untracked (R23-001)
    r = httpx.post("https://api.brevo.com/v3/smtp/email", timeout=15,
                   headers={"api-key": settings.BREVO_API_KEY, "accept": "application/json"}, json=msg)
    if r.status_code >= 400:
        raise _refused("Brevo", r)


def ready_channels() -> dict:
    from . import push
    return {"push": push.enabled(), "telegram": telegram_ready(), "email": email_ready()}


TG_VERIFY = "tgverify:"        # per user: {"verified": chat, "pending": {chat, code_hash, expires, tries}}
TG_CODE_MINUTES = 15
TG_CODE_TRIES = 5


def _chat_key(chat) -> str:
    return (chat or "").strip().lower()


def _tg_state(uid: str) -> dict:
    from . import db
    try:
        st = json.loads(db.get_setting(TG_VERIFY + uid) or "{}")
        return st if isinstance(st, dict) else {}
    except Exception:
        return {}


def telegram_verified(profile: dict) -> bool:
    """The saved chat is the one whose code the user entered. A chat id saved before codes existed isn't verified."""
    chat = _chat_key(profile.get("telegram_chat_id"))
    return bool(chat and profile.get("id") and _chat_key(_tg_state(profile["id"]).get("verified")) == chat)


def _code_hash(uid: str, chat: str, code: str) -> str:
    return hashlib.sha256(f"{uid}:{_chat_key(chat)}:{code}".encode()).hexdigest()


def reset_telegram(uid: str) -> None:
    """Forget the verification and any code waiting (the chat id changed or was removed)."""
    from . import db
    db.update_setting(TG_VERIFY + uid, lambda raw: None if raw is None else json.dumps({}))


def send_telegram_code(uid: str, chat: str) -> None:
    """Send a new 6-digit code to the chat and remember its hash. Raises RuntimeError when it couldn't be sent."""
    from . import db
    code = f"{secrets.randbelow(10 ** 6):06d}"
    send_telegram(chat, f"Your StratLab code: {code}. Enter it on the Alerts settings page to turn on Telegram alerts. "
                        "If you didn't ask for this, ignore it.")
    pending = {"chat": _chat_key(chat), "code_hash": _code_hash(uid, chat, code),
               "expires": time.time() + TG_CODE_MINUTES * 60, "tries": 0}
    def go(raw):
        st = db.json_value(raw, {})
        return json.dumps({**st, "pending": pending})
    db.update_setting(TG_VERIFY + uid, go)


def confirm_telegram(profile: dict, code: str) -> str:
    """"ok", "wrong", "expired" (or no code waiting: ask for a new one), or "locked" after 5 wrong tries."""
    from . import db
    uid, result = profile["id"], ["expired"]
    def go(raw):
        st = db.json_value(raw, {})
        p = st.get("pending")
        if not isinstance(p, dict) or p.get("chat") != _chat_key(profile.get("telegram_chat_id")) or time.time() > p.get("expires", 0):
            result[0] = "expired"
            return None
        if p.get("tries", 0) >= TG_CODE_TRIES:
            result[0] = "locked"
            return None
        if hmac.compare_digest(p.get("code_hash", ""), _code_hash(uid, p["chat"], (code or "").strip())):
            result[0] = "ok"
            return json.dumps({"verified": p["chat"]})
        p["tries"] = p.get("tries", 0) + 1
        result[0] = "locked" if p["tries"] >= TG_CODE_TRIES else "wrong"
        return json.dumps({**st, "pending": p})
    db.update_setting(TG_VERIFY + uid, go)
    return result[0]


def send_telegram(chat_id: str, text: str) -> None:
    if not chat_id:
        return
    if not settings.TELEGRAM_BOT_TOKEN:
        raise RuntimeError("Telegram isn't set up on the server (TELEGRAM_BOT_TOKEN is missing).")
    try:
        r = httpx.post(f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage",
                       json={"chat_id": chat_id, "text": text}, timeout=10)
    except httpx.HTTPError:
        raise RuntimeError("Telegram couldn't be reached.") from None
    if r.status_code >= 400:
        # never surface httpx's own message: its URL contains the bot token
        try:
            detail = r.json().get("description", "")
        except ValueError:
            detail = ""
        raise RuntimeError(f"Telegram refused the message ({r.status_code}). {detail}".strip())


def send_email(to: str, subject: str, body: str, html: str | None = None, headers: dict | None = None) -> None:
    """Plain text, plus an HTML version and extra headers (like List-Unsubscribe) when given. Over HTTPS when a
    Brevo or Resend key is set (they work where outgoing mail ports are blocked), otherwise SMTP."""
    if not to:
        return
    from .email_kit import subject_line
    one_line = lambda v: " ".join(str(v).split())         # a line break in a header would start a new header
    subject = subject_line(one_line(subject))              # one rule for every email's subject: no "StratLab:" prefix
    headers = {k: one_line(v) for k, v in (headers or {}).items()}
    if not any(k.lower() == "list-unsubscribe" for k in headers):
        # an email with no unsubscribe of its own still names one: ours, never the mail service's (R23-001)
        headers.update(manage_unsubscribe_headers())
    # One-Click means a POST to the address turns something off: only a tokenised /unsubscribe link can do that, never a
    # page like Settings (R29B-007)
    own = next((v for k, v in headers.items() if k.lower() == "list-unsubscribe"), "")
    if "/unsubscribe?t=" not in own:
        headers = {k: v for k, v in headers.items() if k.lower() != "list-unsubscribe-post"}
    if settings.BREVO_API_KEY:
        _send_brevo(to, subject, body, html, headers)
        return
    if settings.RESEND_API_KEY:
        _send_resend(to, subject, body, html, headers)
        return
    if not (settings.SMTP_HOST and settings.SMTP_USER):
        raise RuntimeError("Email isn't set up on the server: no Brevo or Resend key, and no SMTP settings.")
    msg = EmailMessage()
    msg["From"] = settings.ALERT_FROM_EMAIL or settings.SMTP_USER
    msg["To"] = to
    msg["Subject"] = subject
    if settings.REPLY_TO_EMAIL:
        msg["Reply-To"] = settings.REPLY_TO_EMAIL
    smtp_brevo = any(w in (settings.SMTP_HOST or "").lower() for w in ("brevo", "sendinblue"))
    for k, v in {**(headers or {}), **(NO_TRACKING if smtp_brevo else {})}.items():      # Brevo's relay reads them too
        msg[k] = v
    msg.set_content(body)
    if html:
        msg.add_alternative(html, subtype="html")     # multipart/alternative: mail apps show the HTML, others the text
    ssl_port = settings.SMTP_PORT == 465
    with (smtplib.SMTP_SSL if ssl_port else smtplib.SMTP)(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as s:
        if not ssl_port:  # 587 and others: upgrade the connection with STARTTLS
            s.starttls()
        s.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        s.send_message(msg)


ALERT_EMAILS = "alert_emails"           # the unsubscribe category of every alert, reminder and admin note by email
ALERT_OFF = "alert-email-off:"          # app_settings key prefix: set while the person has turned alert emails off


def alert_emails_on(uid: str | None) -> bool:
    """False once the person pressed Unsubscribe on an alert email; saving an email address in Settings turns it back on.
    When the setting can't be read, False: an email isn't sent to someone who may have unsubscribed."""
    if not uid:
        return True
    from . import db
    try:
        return not db.get_setting(ALERT_OFF + uid)
    except Exception:
        return False


def set_alert_emails(uid: str, on: bool) -> None:
    from . import db
    db.set_setting(ALERT_OFF + uid, "" if on else "1")


# the pages where a reader chooses an email's alerts or reminders: its "Manage emails" opens that page, not Settings, which
# has no switch for them (R69-002: the advance tax reminder's "Manage emails" opened Settings → Alerts)
CHOSEN_ON = ("/alerts", "/money/calendar", "/money/tax-tools", "/research/screens", "/research/scan", "/research/filings",
             "/trade/events", "/trade/fo-changes", "/invest/holders")
# one email that has its own unsubscribe, instead of every alert email's (R69-003: the paper trading report's "Turn off
# alert emails" turned off every alert, reminder and admin note): its link's words
OWN_UNSUBSCRIBE = {"daily_report": "Turn off this report"}


def manage_path(path: str) -> str | None:
    """The page an email's "Manage emails" opens: the page its link goes to when the reader chose the alert there, else
    None (Settings → Notifications → Alerts)."""
    return path if any(path == p or path.startswith(p + "?") or path.startswith(p + "#") for p in CHOSEN_ON) else None


def send_message(to: str, subject: str, text: str, path: str = "/account", label: str = "Alert",
                 why: str = "You get this because you turned on notifications in StratLab.", button_label: str | None = None,
                 headers: dict | None = None, uid: str | None = None, unsub: str | None = None) -> None:
    """Email a plain-lines message (subject and text, as a phone notification would carry them) in the shared email
    design, with a button to `path` on the site and a Manage emails link. The text version is the lines themselves.
    With `uid` (the reader), the footer has a one-click unsubscribe and the email carries stratlab.studio's own
    List-Unsubscribe headers, so the mail service's tracking link isn't the one a mail app offers (R9P-001)."""
    from . import email_kit as kit
    what = unsub if unsub in OWN_UNSUBSCRIBE else ALERT_EMAILS
    html, plain = kit.message(subject, text, path, label, why, button_label=button_label, date=kit.today_label(),
                              unsubscribe=OWN_UNSUBSCRIBE.get(what, "Turn off alert emails") if uid else None, manage=manage_path(path))
    html, plain, own = kit.finish(html, plain, uid, what if uid else None)
    send_email(to, subject, plain, html=html, headers={**(own or {}), **(headers or {})} or None)


def email_for(profile: dict) -> str | None:
    """Where a user's email alerts go: the address they set in Account, or for an admin, the address they sign in with."""
    if profile.get("alert_email"):
        return profile["alert_email"]
    from .admin import admin_emails
    own = (profile.get("email") or "").strip().lower()
    return own if own and own in admin_emails() else None


CONFIRMED = "email-confirmed:"          # app_settings key prefix: the address the user confirmed
NEWSLETTER_NAMES = {"market_in": "the India market brief", "market_us": "the US market brief",
                    "my_stocks": "the My stocks email", "tips": "tips and reminders emails",
                    "screens": "the weekly emails from your saved stock screens",
                    "advance_tax": "the advance tax reminders",
                    "alert_emails": "alert emails (your alerts, reminders and the admin notes)",
                    "daily_report": "the daily paper trading report",
                    "all": "all StratLab newsletters, tips and reminders"}


def newsletter_email(profile: dict) -> str | None:
    """Where a user's newsletters go: their alert address from Account, or else the address they sign in with."""
    return email_for(profile) or (profile.get("email") or "").strip().lower() or None


def email_confirmed(profile: dict) -> bool:
    """The newsletter address was confirmed from a link sent to it. An admin's own sign-in address counts as
    confirmed, since the owner put it in ADMIN_EMAILS."""
    from . import db
    from .admin import admin_emails
    to = (newsletter_email(profile) or "").strip().lower()
    if not to:
        return False
    own = (profile.get("email") or "").strip().lower()
    # a signed-in request knows whether Google proved the address; a profile read from the database doesn't say
    if to == own and own in admin_emails() and profile.get("_email_verified", True):
        return True
    try:
        return bool(profile.get("id")) and (db.get_setting(CONFIRMED + profile["id"]) or "").strip().lower() == to
    except Exception:
        return False


EMAIL_PATHS = ("/unsubscribe", "/email/confirm")      # the site forwards these to the API (frontend/vercel.json)


def email_link_base() -> str:
    """Where links the server answers itself (unsubscribe, confirm an address) point: the public site, which forwards
    them to the API, so a reader sees stratlab.studio, never the API's own host (R6V-016)."""
    return settings.PUBLIC_SITE_URL.rstrip("/")


def unsubscribe_url(uid: str, what: str) -> str:
    """A link that turns off one newsletter (or "all") without signing in."""
    from . import mail_tokens
    return f"{email_link_base()}/unsubscribe?t={mail_tokens.make(uid, 'unsubscribe', what)}"


def list_unsubscribe_headers(uid: str, what: str) -> dict:
    """The headers that give mail apps their own one-click unsubscribe button."""
    return {"List-Unsubscribe": f"<{unsubscribe_url(uid, what)}>", "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"}


def confirm_url(uid: str, address: str) -> str:
    """A link (good for 3 days) that confirms this address for the user's newsletters."""
    from . import mail_tokens
    return f"{email_link_base()}/email/confirm?t={mail_tokens.make(uid, 'confirm', address)}"


# an admin email says why the admin gets it, not "you turned on notifications" (R6V-010)
ADMIN_WHY = "You get this because you are a StratLab admin. It goes to every admin address."


def tell_admins(subject: str, text: str, label: str = "Admin alert") -> int:
    """Something an admin should know (a daily check failing, the broker login failing): sent to each admin's email,
    plus any phone or Telegram they set in Account. Returns how many admins were reached."""
    from . import db
    from .admin import admin_emails
    reached = 0
    for email in sorted(admin_emails()):
        try:
            rows = db.sb().table("profiles").select("*").eq("email", email).limit(1).execute().data
        except Exception:
            rows = []
        try:
            if rows:
                if notify(rows[0], subject, text, background=False, url="/admin", why=ADMIN_WHY, label=label):
                    reached += 1
            elif email_ready():
                send_message(email, subject, text, "/admin", label, ADMIN_WHY)
                reached += 1
        except Exception as e:
            print("admin alert failed:", e)
    return reached


def jobs_for(profile: dict, subject: str, text: str, url: str = "/paper", why: str | None = None,
             label: str = "Alert", force_email: bool = False, unsub: str | None = None) -> list[tuple[str, object]]:
    """(channel, send) for every channel the user set up that the server can use. Email is skipped once the person
    unsubscribed from alert emails, except for a test they asked for (`force_email`). Telegram and email are Basic and
    up (the plan's "alerts"), so they stop after a downgrade to Free; the phone stays."""
    from . import push
    from .plans import allows, plan_of
    jobs = []
    if profile.get("id") and push.enabled() and push.devices(profile["id"]):
        jobs.append(("push", lambda: push.send(profile["id"], subject, text, url)))
    from .admin import admin_emails
    own = (profile.get("email") or "").strip().lower()
    if not allows(plan_of(profile), "alerts") and own not in admin_emails():      # an admin's notes aren't a plan's feature
        return jobs
    if profile.get("telegram_chat_id") and telegram_ready() and telegram_verified(profile):
        jobs.append(("telegram", lambda: send_telegram(profile["telegram_chat_id"], text)))
    to = email_for(profile)
    if to and email_ready() and email_confirmed(profile) and (force_email or alert_emails_on(profile.get("id"))):   # only an address its owner confirmed from a link
        jobs.append(("email", lambda: send_message(to, subject, text, url, label, uid=profile.get("id"), unsub=unsub, **({"why": why} if why else {}))))
    return jobs


def reached(channel: str, result) -> bool:
    """Whether a job from jobs_for got through: push.send returns how many devices it reached (0 when the push service
    failed or every device was gone), the other channels raise when they fail."""
    return not (channel == "push" and result == 0)


def notify(profile: dict, subject: str, text: str, background: bool = True, url: str = "/paper", why: str | None = None,
           label: str = "Alert", unsub: str | None = None) -> list[str]:
    """Send to every usable channel the user set up. Returns the channels attempted."""
    pairs = jobs_for(profile, subject, text, url, why, label, unsub=unsub)
    channels = [c for c, _ in pairs]
    jobs = [j for _, j in pairs]

    def run():
        for j in jobs:
            try:
                j()
            except Exception as e:
                print("alert failed:", e)

    if background:
        threading.Thread(target=run, daemon=True).start()
    else:
        run()
    return channels


def test(profile: dict, admin: bool = False) -> tuple[list[str], dict[str, str]]:
    """Send a test on each channel separately: which worked, and why the others didn't. The mail service's own words
    are for admins; everyone else gets a plain line."""
    sent, failed = [], {}
    for channel, job in jobs_for(profile, "StratLab test alert", "StratLab test alert: your alerts are working.", "/account", force_email=True):
        try:
            if reached(channel, job()):
                sent.append(channel)
            else:
                failed[channel] = "No phone received it. Check that notifications are on for this device."
        except Exception as e:
            # Telegram's own words say whether a chat id exists, and any chat id can be typed in: not passed on
            print(f"alert test on {channel} failed:", str(e)[:200])
            failed[channel] = ("Telegram couldn't deliver to that chat" if channel == "telegram"
                               else str(e)[:200] if admin else "The email couldn't be sent right now.")
    return sent, failed
