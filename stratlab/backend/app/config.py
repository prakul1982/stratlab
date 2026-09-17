import os
from dotenv import load_dotenv

load_dotenv()


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


class Settings:
    SUPABASE_URL = _env("SUPABASE_URL")
    SUPABASE_SERVICE_KEY = _env("SUPABASE_SERVICE_KEY")

    KITE_API_KEY = _env("KITE_API_KEY")
    KITE_API_SECRET = _env("KITE_API_SECRET")

    RAZORPAY_KEY_ID = _env("RAZORPAY_KEY_ID")
    RAZORPAY_KEY_SECRET = _env("RAZORPAY_KEY_SECRET")
    RAZORPAY_WEBHOOK_SECRET = _env("RAZORPAY_WEBHOOK_SECRET")
    RAZORPAY_PLAN_BASIC = _env("RAZORPAY_PLAN_BASIC")
    RAZORPAY_PLAN_PRO = _env("RAZORPAY_PLAN_PRO")

    ANTHROPIC_API_KEY = _env("ANTHROPIC_API_KEY")
    ANTHROPIC_MODEL = _env("ANTHROPIC_MODEL", "claude-sonnet-5")

    TELEGRAM_BOT_TOKEN = _env("TELEGRAM_BOT_TOKEN")
    SMTP_HOST = _env("SMTP_HOST")
    SMTP_PORT = int(_env("SMTP_PORT", "465") or 465)
    SMTP_USER = _env("SMTP_USER")
    SMTP_PASSWORD = _env("SMTP_PASSWORD")
    ALERT_FROM_EMAIL = _env("ALERT_FROM_EMAIL")

    FRONTEND_ORIGIN = _env("FRONTEND_ORIGIN", "http://localhost:5500")
    ADMIN_KEY = _env("ADMIN_KEY")


settings = Settings()
