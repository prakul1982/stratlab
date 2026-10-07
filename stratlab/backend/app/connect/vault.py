"""Encrypts the secrets users hand us (a statement password, a broker token) before they are stored.

Fernet (AES-128-CBC with an HMAC) with the key in CONNECT_SECRET_KEY: a url-safe base64 key from
`python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. Several keys, comma
separated, rotate it: the first encrypts, every one can decrypt. Without a key nothing is stored (ready() is False)."""
from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from ..config import settings


class VaultError(Exception):
    """No key is set, or a stored secret can't be opened with it."""


def _fernet() -> MultiFernet | None:
    keys = [k.strip() for k in (settings.CONNECT_SECRET_KEY or "").split(",") if k.strip()]
    if not keys:
        return None
    try:
        return MultiFernet([Fernet(k.encode()) for k in keys])
    except (ValueError, TypeError):
        return None


def ready() -> bool:
    return _fernet() is not None


def seal(secret: str) -> str:
    f = _fernet()
    if f is None:
        raise VaultError("CONNECT_SECRET_KEY is not set")
    return f.encrypt(str(secret).encode()).decode()


def unseal(token: str | None) -> str | None:
    """The secret, or None when there is none or it can't be opened (a changed key)."""
    if not token:
        return None
    f = _fernet()
    if f is None:
        return None
    try:
        return f.decrypt(str(token).encode()).decode()
    except (InvalidToken, ValueError, TypeError):
        return None
