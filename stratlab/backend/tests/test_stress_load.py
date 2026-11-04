"""Stress: many people at once against the real server (in its own process, one worker as in production). A short
run on every change; `python -m tests.load_test --users 300 --think 3 10` for the full one."""
import asyncio
import socket


from app.guard import HeavyGate


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_forty_busy_users_get_quick_pages_and_no_errors():
    from tests import load_test
    alone = {}
    rows, errors = load_test.run(40, 20, port=_free_port(), baseline=alone)
    assert not any(errors.values()), {k: v[:2] for k, v in errors.items() if v}
    quick = [r for k, r in rows.items() if k in load_test.QUICK]
    # 3 s on a quiet machine, where a quick page alone takes about 0.08 s; a machine busy with other work (several test
    # suites at once) is slower for every request, so the budget grows with the quick pages' own time measured alone in
    # the same run: 36 times it, never under 3 s. The forty users still may not slow a page past that budget
    budget = max(3.0, 36 * alone["quick"])
    assert quick and max(r["p95"] for r in quick) < budget, (budget, alone, rows)


def test_heavy_work_takes_turns_and_ordinary_pages_dont_wait():
    """Two heavy requests run, the third waits; a page request goes straight through meanwhile."""
    started, release = [], asyncio.Event()

    async def app(scope, receive, send):
        started.append(scope["path"])
        if scope["path"] != "/me":
            await release.wait()

    gate = HeavyGate(app, slots=2, max_wait=5)

    async def go():
        heavy = [asyncio.create_task(gate({"type": "http", "method": "POST", "path": "/research/scan"}, None, None))
                 for _ in range(3)]
        await asyncio.sleep(0.05)
        assert started.count("/research/scan") == 2 and gate.waiting == 1
        await gate({"type": "http", "method": "GET", "path": "/me"}, None, None)
        assert "/me" in started
        release.set()
        await asyncio.gather(*heavy)
        assert started.count("/research/scan") == 3
    asyncio.run(go())


def test_a_heavy_request_that_waits_too_long_is_told_the_server_is_busy():
    sent = []

    async def app(scope, receive, send):
        await asyncio.sleep(1)

    async def send(m):
        sent.append(m)
    gate = HeavyGate(app, slots=1, max_wait=0.1)

    async def go():
        first = asyncio.create_task(gate({"type": "http", "method": "POST", "path": "/research/scan"}, None, send))
        await asyncio.sleep(0.01)
        await gate({"type": "http", "method": "POST", "path": "/research/scan"}, None, send)
        await first
    asyncio.run(go())
    assert sent[0]["status"] == 503 and b'"busy"' in sent[1]["body"]
