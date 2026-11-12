"""File imports take turns (guard.UPLOADS): each holds its whole file and the rows read from it, so a burst of them at once
must not stack their memory on the one server. They have their own gate, apart from the heavy work's."""
import asyncio
import re

from fastapi.routing import APIRoute

from app import main
from app.guard import HEAVY, UPLOADS, HeavyGate
from app.route_list import declared, every_route

# POST routes that read a file someone sends: a statement, a tradebook, a holdings or dividends file
FILE_ROUTE = re.compile(r"/(import|import-tax|statement)$")
NOT_A_FILE = {"/import/strategy"}       # a strategy's JSON, a few KB, validated by its model


def _posts() -> list[str]:
    out = []
    for r in every_route(main.app.routes):
        if isinstance(declared(r), APIRoute) and "POST" in r.methods and getattr(r.endpoint, "__module__", "").startswith("app."):
            out.append(r.path)
    return out


def _gated(path: str, routes) -> bool:
    return any(m == "POST" and rx.match(path) for m, rx in routes)


def test_every_file_import_takes_turns_in_a_gate():
    posts = _posts()
    files = [p for p in posts if FILE_ROUTE.search(p) and p not in NOT_A_FILE]
    assert len(files) >= 6, files
    loose = [p for p in files if not (_gated(p, HEAVY) or _gated(p, UPLOADS))]
    assert not loose, loose
    # and no pattern in the upload gate names a route that doesn't exist (a renamed route would slip out of it unseen)
    for _, rx in UPLOADS:
        assert any(rx.match(p) for p in posts), rx.pattern


def test_the_app_runs_the_upload_gate_apart_from_the_heavy_one():
    gates = [m for m in main.app.user_middleware if m.cls is HeavyGate]
    routes = [m.kwargs.get("routes") for m in gates]
    assert UPLOADS in routes and None in routes, routes     # the heavy gate (its default routes) and the upload gate


def test_uploads_take_turns_and_dont_wait_behind_heavy_work():
    started, release = [], asyncio.Event()

    async def app(scope, receive, send):
        started.append(scope["path"])
        await release.wait()

    uploads = HeavyGate(app, slots=2, max_wait=5, routes=UPLOADS)
    heavy = HeavyGate(uploads, slots=1, max_wait=5)

    async def go():
        busy = asyncio.create_task(heavy({"type": "http", "method": "POST", "path": "/research/scan"}, None, None))
        files = [asyncio.create_task(heavy({"type": "http", "method": "POST", "path": "/tax/import"}, None, None)) for _ in range(3)]
        await asyncio.sleep(0.05)
        # the scan holds the heavy gate's one slot; two imports run beside it and the third waits for an upload slot
        assert started.count("/research/scan") == 1 and started.count("/tax/import") == 2 and uploads.waiting == 1
        release.set()
        await asyncio.gather(busy, *files)
        assert started.count("/tax/import") == 3
    asyncio.run(go())


def test_an_upload_that_waits_too_long_is_told_the_server_is_busy():
    sent = []

    async def app(scope, receive, send):
        await asyncio.sleep(1)

    async def send(m):
        sent.append(m)

    gate = HeavyGate(app, slots=1, max_wait=0.1, routes=UPLOADS)

    async def go():
        first = asyncio.create_task(gate({"type": "http", "method": "POST", "path": "/holdings/import"}, None, send))
        await asyncio.sleep(0.02)
        await gate({"type": "http", "method": "POST", "path": "/holdings/import"}, None, send)
        await first
    asyncio.run(go())
    assert sent and sent[0]["status"] == 503
