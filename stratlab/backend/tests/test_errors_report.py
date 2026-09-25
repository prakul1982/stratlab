import sentry_sdk
from fastapi.testclient import TestClient

from app import errors


class Capture(sentry_sdk.transport.Transport):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.events = []

    def capture_envelope(self, envelope):
        for item in envelope.items:
            if item.type == "event":
                self.events.append(item.payload.json)


def test_report_is_quiet_without_sentry():
    errors.report(ValueError("x"), where="t")   # no DSN set: does nothing, raises nothing
    errors.note("hello")


def test_crash_reaches_sentry_with_its_ref(monkeypatch):
    from app import main
    t = Capture()
    sentry_sdk.init(dsn="https://k@o1.ingest.sentry.io/1", transport=t, default_integrations=False)
    try:
        @main.app.get("/_boom_for_test")
        def boom():
            raise RuntimeError("kaboom")
        r = TestClient(main.app).get("/_boom_for_test")
        assert r.status_code == 500
        ref = r.json()["detail"]["message"].split("ref ")[1][:6]
        sentry_sdk.flush()
        ev = t.events[-1]
        assert ev["tags"]["ref"] == ref and ev["tags"]["path"] == "GET /_boom_for_test"
        assert ev["exception"]["values"][-1]["value"] == "kaboom"
        errors.note("Kite login failed")
        sentry_sdk.flush()
        assert t.events[-1]["message"] == "Kite login failed"
    finally:
        sentry_sdk.init(dsn=None)
        main.app.router.routes = [r for r in main.app.router.routes if getattr(r, "path", "") != "/_boom_for_test"]
