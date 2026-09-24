"""Telegram and email trade alerts (Pro)."""
import smtplib
import threading
from email.message import EmailMessage
import httpx
from .config import settings


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


def notify(profile: dict, subject: str, text: str, background: bool = True) -> list[str]:
    """Send to every channel the user set up. Returns the channels attempted."""
    channels = []
    jobs = []
    if profile.get("telegram_chat_id"):
        channels.append("telegram")
        jobs.append(lambda: send_telegram(profile["telegram_chat_id"], text))
    if profile.get("alert_email"):
        channels.append("email")
        jobs.append(lambda: send_email(profile["alert_email"], subject, text))

    def run():
        for j in jobs:
            try:
                j()
            except Exception as e:
                print("alert failed:", e)

    if background:
        threading.Thread(target=run, daemon=True).start()
    else:
        for j in jobs:
            j()
    return channels
