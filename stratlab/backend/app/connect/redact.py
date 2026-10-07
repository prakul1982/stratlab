"""Keeps secrets out of logs. A filter on every log handler masks token-like values (broker tokens in a URL, passwords,
authorization headers, a PAN) in what is printed, so a mistake elsewhere still can't write them out.

install() is called once at start-up; mask() is also used on error text before it is shown or stored."""
import logging
import re

PATTERNS = [
    (re.compile(r"(?i)([?&](?:t|token|access_token|request_token|api_key|apikey|key|k|password|pwd|secret)=)[^&\s'\"]+"), r"\1***"),
    (re.compile(r"(?i)((?:token|password|passwd|pwd|secret|authorization|api-key|x-api-key|access_token)['\"]?\s*[:=]\s*['\"]?)(?:Bearer\s+)?[^\s,'\"}&]+"), r"\1***"),
    (re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{8,}"), "Bearer ***"),
    (re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b"), "[PAN]"),
    (re.compile(r"\bgAAAA[A-Za-z0-9_=-]{20,}"), "***"),                  # a sealed value (Fernet tokens start like this)
]


def mask(text) -> str:
    s = str(text)
    for rx, sub in PATTERNS:
        s = rx.sub(sub, s)
    return s


class SecretFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            record.msg = mask(record.getMessage())
            record.args = ()
            if record.exc_info:
                record.exc_text = mask(logging.Formatter().formatException(record.exc_info))
                record.exc_info = None
        except Exception:
            pass
        return True


_filter = SecretFilter()


def install() -> None:
    """Mask secrets on the root logger's handlers and on the HTTP libraries' loggers (which print request URLs)."""
    root = logging.getLogger()
    for h in root.handlers:
        if _filter not in h.filters:
            h.addFilter(_filter)
    for name in ("httpx", "httpcore", "uvicorn.access", "uvicorn.error", "kiteconnect"):
        lg = logging.getLogger(name)
        if _filter not in lg.filters:
            lg.addFilter(_filter)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
