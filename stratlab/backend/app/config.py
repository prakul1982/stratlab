import os
from dotenv import load_dotenv

load_dotenv()


def _env(name: str, default: str = "") -> str:
    value = os.getenv(name, default).strip()
    # forgive common pasting mistakes: NAME=value, or the value wrapped in quotes
    if value.startswith(f"{name}="):
        value = value[len(name) + 1:].strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1].strip()
    return value


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

    # AI strategy builder: providers are tried in order until one answers (see ai_providers.py)
    AI_PROVIDERS = _env("AI_PROVIDERS", "auto")         # "auto" = every provider with a key, or e.g. "groq,gemini"
    AI_PROVIDERS_RESEARCH = _env("AI_PROVIDERS_RESEARCH", "auto")  # order for long research reads; "auto" = built-in order
    AI_PROVIDER = _env("AI_PROVIDER", "gemini")          # older setting: "anthropic" puts Claude first
    GROQ_API_KEY = _env("GROQ_API_KEY")
    GROQ_MODEL = _env("GROQ_MODEL", "auto")
    CEREBRAS_API_KEY = _env("CEREBRAS_API_KEY")
    CEREBRAS_MODEL = _env("CEREBRAS_MODEL", "auto")
    SAMBANOVA_API_KEY = _env("SAMBANOVA_API_KEY")
    SAMBANOVA_MODEL = _env("SAMBANOVA_MODEL", "auto")
    MISTRAL_API_KEY = _env("MISTRAL_API_KEY")
    MISTRAL_MODEL = _env("MISTRAL_MODEL", "auto")
    OPENROUTER_API_KEY = _env("OPENROUTER_API_KEY")
    OPENROUTER_MODEL = _env("OPENROUTER_MODEL", "auto")  # "auto" uses only models marked :free
    GEMINI_API_KEY = _env("GEMINI_API_KEY")
    GEMINI_MODEL = _env("GEMINI_MODEL", "auto")        # "auto" picks the newest Flash model your key can use
    ANTHROPIC_API_KEY = _env("ANTHROPIC_API_KEY")
    ANTHROPIC_MODEL = _env("ANTHROPIC_MODEL", "claude-sonnet-5")

    # Research: US company data (free key at finnhub.io). India uses Screener.in, Yahoo and Kite, no key needed.
    FINNHUB_API_KEY = _env("FINNHUB_API_KEY")
    RESEARCH_AI_PER_DAY = int(_env("RESEARCH_AI_PER_DAY", "60") or 60)   # fresh AI analyses per user per day

    TELEGRAM_BOT_TOKEN = _env("TELEGRAM_BOT_TOKEN")
    SMTP_HOST = _env("SMTP_HOST")
    SMTP_PORT = int(_env("SMTP_PORT", "465") or 465)
    SMTP_USER = _env("SMTP_USER")
    SMTP_PASSWORD = _env("SMTP_PASSWORD")
    ALERT_FROM_EMAIL = _env("ALERT_FROM_EMAIL")

    FRONTEND_ORIGIN = _env("FRONTEND_ORIGIN", "http://localhost:5500")
    # comma-separated, e.g. "https://stratlab.studio,http://localhost:5500"
    FRONTEND_ORIGINS = origins(FRONTEND_ORIGIN)
    ADMIN_KEY = _env("ADMIN_KEY")
    ADMIN_EMAILS = _env("ADMIN_EMAILS")                           # comma-separated Google emails that can open /admin
    ADMIN_TELEGRAM_CHAT_ID = _env("ADMIN_TELEGRAM_CHAT_ID")      # gets a message if the auto-login fails


settings = Settings()
