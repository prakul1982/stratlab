"""Send an error to Sentry when it's set up (SENTRY_DSN); otherwise do nothing."""


def report(e: BaseException, **tags) -> None:
    try:
        import sentry_sdk
        if not sentry_sdk.is_initialized():
            return
        with sentry_sdk.new_scope() as scope:
            for k, v in tags.items():
                scope.set_tag(k, str(v))
            sentry_sdk.capture_exception(e)
    except Exception:
        pass


def note(text: str) -> None:
    """An admin alert (Kite login failed, token rejected) as a Sentry message, so it can page you."""
    try:
        import sentry_sdk
        if sentry_sdk.is_initialized():
            sentry_sdk.capture_message(text, level="error")
    except Exception:
        pass


def enabled() -> bool:
    """Whether error alerts reach Sentry: SENTRY_DSN is set and the SDK started (app/main.py). Shown in Admin → System."""
    try:
        import sentry_sdk
        return bool(sentry_sdk.is_initialized())
    except Exception:
        return False


def test_message(text: str) -> bool:
    """One harmless message from Admin's "Send a test error", so the owner can see an alert arrive end to end.
    Returns whether Sentry was on (with it off nothing is sent: there is nowhere to send it)."""
    try:
        import sentry_sdk
        if not sentry_sdk.is_initialized():
            return False
        with sentry_sdk.new_scope() as scope:
            scope.set_tag("test", "admin")          # easy to filter out of the real errors
            sentry_sdk.capture_message(text, level="error")
        return True
    except Exception:
        return False
