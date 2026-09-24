import os
from dotenv import load_dotenv

load_dotenv()


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def origins(value: str) -> list[str]:
    return [o.strip().rstrip("/") for o in value.split(",") if o.strip()]


class Settings:
    SUPABASE_URL = _env("SUPABASE_URL")
    SUPABASE_SERVICE_KEY = _env("SUPABASE_SERVICE_KEY")

    KITE_API_KEY = _env("KITE_API_KEY")
    KITE_API_SECRET = _env("KITE_API_SECRET")
    # Optional automatic daily login (see kite_auto.py). Leave empty to log in by hand.
    KITE_USER_ID = _env("KITE_USER_ID")
    KITE_PASSWORD = _env("KITE_PASSWORD")
    KITE_TOTP_SECRET = _env("KITE_TOTP_SECRET")
    KITE_AUTO_LOGIN_AT = _env("KITE_AUTO_LOGIN_AT", "08:00")        # IST, after Kite's ~6 am token reset
    KITE_RESTART_AFTER_LOGIN = _env("KITE_RESTART_AFTER_LOGIN", "true").lower() != "false"

    RAZORPAY_KEY_ID = _env("RAZORPAY_KEY_ID")
    RAZORPAY_KEY_SECRET = _env("RAZORPAY_KEY_SECRET")
    RAZORPAY_WEBHOOK_SECRET = _env("RAZORPAY_WEBHOOK_SECRET")
    RAZORPAY_PLAN_BASIC = _env("RAZORPAY_PLAN_BASIC")
    RAZORPAY_PLAN_PRO = _env("RAZORPAY_PLAN_PRO")

    AI_PROVIDER = _env("AI_PROVIDER", "gemini")          # "gemini" or "anthropic"
    GEMINI_API_KEY = _env("GEMINI_API_KEY")
    GEMINI_MODEL = _env("GEMINI_MODEL", "auto")        # "auto" picks the newest Flash model your key can use
    ANTHROPIC_API_KEY = _env("ANTHROPIC_API_KEY")
    ANTHROPIC_MODEL = _env("ANTHROPIC_MODEL", "claude-sonnet-5")

    TELEGRAM_BOT_TOKEN = _env("TELEGRAM_BOT_TOKEN")
    SMTP_HOST = _env("SMTP_HOST")
    SMTP_PORT = int(_env("SMTP_PORT", "465") or 465)
    SMTP_USER = _env("SMTP_USER")
    SMTP_PASSWORD = _env("SMTP_PASSWORD")
    ALERT_FROM_EMAIL = _env("ALERT_FROM_EMAIL")

    FRONTEND_ORIGIN = _env("FRONTEND_ORIGIN", "http://localhost:5500")
    # comma-separated, e.g. "https://stratlab.netlify.app,http://localhost:5500"
    FRONTEND_ORIGINS = origins(FRONTEND_ORIGIN)
    ADMIN_KEY = _env("ADMIN_KEY")
    ADMIN_TELEGRAM_CHAT_ID = _env("ADMIN_TELEGRAM_CHAT_ID")      # gets a message if the auto-login fails


settings = Settings()
