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


# account identifiers in a provider's error text: shown to nobody on Admin (R29B-022)
ID_PATTERNS = [
    (re.compile(r"(?i)\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b"), "[id]"),
    (re.compile(r"\b(?:acct|cus|org|usr|user|sk|pk|key|client|merchant)[_-][A-Za-z0-9]{6,}\b"), "[id]"),
    (re.compile(r"(?i)\b(account|acct|customer|organi[sz]ation|org|user|client|merchant|sender|member)(\s*(?:id|number|no\.?)?\s*[:=#]?\s*)(?=[\"']?[A-Za-z0-9_-]{6,})(?=[\"']?[A-Za-z0-9_-]*\d)[\"']?[A-Za-z0-9_-]{6,}[\"']?"), r"\1\2[id]"),
    (re.compile(r"\b\d{9,}\b"), "[id]"),
]


def redact_ids(text):
    """Error text with account identifiers hidden (UUIDs, prefixed ids like acct_..., "account 12ab34cd", long numbers), after
    the secrets mask. Non-strings pass through."""
    if not isinstance(text, str):
        return text
    s = mask(text)
    for rx, sub in ID_PATTERNS:
        s = rx.sub(sub, s)
    return s


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
