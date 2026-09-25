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
