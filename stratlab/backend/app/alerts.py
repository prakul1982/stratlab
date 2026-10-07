"""Trade alerts and the daily report: phone notifications, Telegram and email.

A channel the server isn't set up for (no Telegram bot token, no email settings) is skipped rather than failing
the others, and the Account page doesn't offer it."""
import smtplib
import threading
from email.message import EmailMessage
import httpx
from .config import settings


def telegram_ready() -> bool:
    return bool(settings.TELEGRAM_BOT_TOKEN)


def email_ready() -> bool:
    return bool(settings.BREVO_API_KEY or settings.RESEND_API_KEY
                or (settings.SMTP_HOST and settings.SMTP_USER and settings.SMTP_PASSWORD))


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


def _send_brevo(to: str, subject: str, body: str, html: str | None = None, headers: dict | None = None) -> None:
    msg = {"sender": {"name": "StratLab", "email": _brevo_sender()}, "to": [{"email": to}], "subject": subject,
           "textContent": body}
    if html:
        msg["htmlContent"] = html
    if headers:
        msg["headers"] = headers
    r = httpx.post("https://api.brevo.com/v3/smtp/email", timeout=15,
                   headers={"api-key": settings.BREVO_API_KEY, "accept": "application/json"}, json=msg)
    if r.status_code >= 400:
        raise _refused("Brevo", r)


def ready_channels() -> dict:
    from . import push
    return {"push": push.enabled(), "telegram": telegram_ready(), "email": email_ready()}


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
    headers = {k: one_line(v) for k, v in (headers or {}).items()} or None
    if settings.BREVO_API_KEY:
        _send_brevo(to, subject, body, html, headers)
        return
    if settings.RESEND_API_KEY:
        _send_resend(to, subject, body, html, headers)
        return
    if not (settings.SMTP_HOST and settings.SMTP_USER):
        raise RuntimeError("Email isn't set up on the server (SMTP settings are missing).")
    msg = EmailMessage()
    msg["From"] = settings.ALERT_FROM_EMAIL or settings.SMTP_USER
    msg["To"] = to
    msg["Subject"] = subject
    for k, v in (headers or {}).items():
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


def send_message(to: str, subject: str, text: str, path: str = "/account", label: str = "Alert",
                 why: str = "You get this because you turned on notifications in StratLab.", button_label: str | None = None,
                 headers: dict | None = None) -> None:
    """Email a plain-lines message (subject and text, as a phone notification would carry them) in the shared email
    design, with a button to `path` on the site and a Manage emails link. The text version is the lines themselves."""
    from . import email_kit as kit
    html, plain = kit.message(subject, text, path, label, why, button_label=button_label,
                              date=kit.today_label())
    send_email(to, subject, plain, html=html, headers=headers)


def email_for(profile: dict) -> str | None:
    """Where a user's email alerts go: the address they set in Account, or for an admin, the address they sign in with."""
    if profile.get("alert_email"):
        return profile["alert_email"]
    from .admin import admin_emails
    own = (profile.get("email") or "").strip().lower()
    return own if own and own in admin_emails() else None


CONFIRMED = "email-confirmed:"          # app_settings key prefix: the address the user confirmed
NEWSLETTER_NAMES = {"market_in": "the India market email", "market_us": "the US market email",
                    "my_stocks": "the My stocks email", "tips": "tips and reminders emails",
                    "screens": "the weekly emails from your saved stock screens",
                    "advance_tax": "the advance tax reminders",
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


def unsubscribe_url(uid: str, what: str) -> str:
    """A link that turns off one newsletter (or "all") without signing in."""
    from . import mail_tokens
    return f"{settings.PUBLIC_API_URL}/unsubscribe?t={mail_tokens.make(uid, 'unsubscribe', what)}"


def list_unsubscribe_headers(uid: str, what: str) -> dict:
    """The headers that give mail apps their own one-click unsubscribe button."""
    return {"List-Unsubscribe": f"<{unsubscribe_url(uid, what)}>", "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"}


def confirm_url(uid: str, address: str) -> str:
    """A link (good for 3 days) that confirms this address for the user's newsletters."""
    from . import mail_tokens
    return f"{settings.PUBLIC_API_URL}/email/confirm?t={mail_tokens.make(uid, 'confirm', address)}"


def tell_admins(subject: str, text: str) -> int:
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
                if notify(rows[0], subject, text, background=False, url="/admin"):
                    reached += 1
            elif email_ready():
                send_message(email, subject, text, "/admin", "Admin alert", "You get this because you are a StratLab admin.")
                reached += 1
        except Exception as e:
            print("admin alert failed:", e)
    return reached


def jobs_for(profile: dict, subject: str, text: str, url: str = "/paper") -> list[tuple[str, object]]:
    """(channel, send) for every channel the user set up that the server can use."""
    from . import push
    jobs = []
    if profile.get("id") and push.enabled() and push.devices(profile["id"]):
        jobs.append(("push", lambda: push.send(profile["id"], subject, text, url)))
    if profile.get("telegram_chat_id") and telegram_ready():
        jobs.append(("telegram", lambda: send_telegram(profile["telegram_chat_id"], text)))
    to = email_for(profile)
    if to and email_ready() and email_confirmed(profile):      # only an address its owner confirmed from a link
        jobs.append(("email", lambda: send_message(to, subject, text, url, "Alert")))
    return jobs


def notify(profile: dict, subject: str, text: str, background: bool = True, url: str = "/paper") -> list[str]:
    """Send to every usable channel the user set up. Returns the channels attempted."""
    pairs = jobs_for(profile, subject, text, url)
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


def test(profile: dict) -> tuple[list[str], dict[str, str]]:
    """Send a test on each channel separately: which worked, and why the others didn't."""
    sent, failed = [], {}
    for channel, job in jobs_for(profile, "StratLab test alert", "StratLab test alert: your alerts are working.", "/account"):
        try:
            job()
            sent.append(channel)
        except Exception as e:
            failed[channel] = str(e)[:200]
    return sent, failed
