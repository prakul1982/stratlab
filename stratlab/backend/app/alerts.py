"""Trade alerts and the daily report: phone notifications, Telegram and email.

A channel the server isn't set up for (no Telegram bot token, no SMTP settings) is skipped rather than failing
the others, and the Account page doesn't offer it."""
import smtplib
import threading
from email.message import EmailMessage
import httpx
from .config import settings


def telegram_ready() -> bool:
    return bool(settings.TELEGRAM_BOT_TOKEN)


def email_ready() -> bool:
    return bool(settings.SMTP_HOST and settings.SMTP_USER and settings.SMTP_PASSWORD)


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


def send_email(to: str, subject: str, body: str) -> None:
    if not to:
        return
    if not (settings.SMTP_HOST and settings.SMTP_USER):
        raise RuntimeError("Email isn't set up on the server (SMTP settings are missing).")
    msg = EmailMessage()
    msg["From"] = settings.ALERT_FROM_EMAIL or settings.SMTP_USER
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    ssl_port = settings.SMTP_PORT == 465
    with (smtplib.SMTP_SSL if ssl_port else smtplib.SMTP)(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as s:
        if not ssl_port:  # 587 and others: upgrade the connection with STARTTLS
            s.starttls()
        s.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        s.send_message(msg)


def jobs_for(profile: dict, subject: str, text: str, url: str = "/paper") -> list[tuple[str, object]]:
    """(channel, send) for every channel the user set up that the server can use."""
    from . import push
    jobs = []
    if profile.get("id") and push.enabled() and push.devices(profile["id"]):
        jobs.append(("push", lambda: push.send(profile["id"], subject, text, url)))
    if profile.get("telegram_chat_id") and telegram_ready():
        jobs.append(("telegram", lambda: send_telegram(profile["telegram_chat_id"], text)))
    if profile.get("alert_email") and email_ready():
        jobs.append(("email", lambda: send_email(profile["alert_email"], subject, text)))
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
