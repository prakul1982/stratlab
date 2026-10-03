"""Load test: many users at once against the real server (uvicorn, one worker, as on Railway), on the fake world so
it measures StratLab itself, not the data sources' limits.

    python -m tests.load_test --users 50 --seconds 60

Each simulated user loops through what people actually do (open pages, run a backtest, scan, look at the option chain,
watch a paper session) with a short think time. Reports, per kind of request, how many ran, the median, the 95th
percentile and the slowest time, and every error; and whether quick pages stayed quick while heavy work ran."""
import argparse
import asyncio
import random
import statistics
import sys
import threading
import time
from collections import defaultdict

import httpx
import pytest
import uvicorn

sys.path.insert(0, ".")
from app import main  # noqa: E402
from tests import stress_requests, world  # noqa: E402

QUICK = {"me", "markets", "notebooks", "live overview", "plans", "library"}


def mix(ctx):
    """(weight, label, method, path, json): roughly how often each thing happens."""
    nb = ctx["nid"]
    return [
        (10, "me", "GET", "/me", None),
        (6, "markets", "GET", "/markets", None),
        (8, "notebooks", "GET", "/notebooks", None),
        (5, "notebook", "GET", f"/notebooks/{nb}", None),
        (6, "live overview", "GET", "/live/overview", None),
        (4, "live session", "GET", f"/live/sessions/{ctx['sid']}", None),
        (3, "plans", "GET", "/plans", None),
        (3, "library", "GET", "/library", None),
        (4, "backtest 1y", "POST", f"/notebooks/{nb}/experiments", {"days": 365}),
        (1, "backtest 10y", "POST", f"/notebooks/{nb}/experiments", {"days": 3650}),
        (2, "scan", "POST", "/research/scan", {"region": "IN", "set": "nifty50"}),
        (2, "rotation", "GET", "/research/rotation?region=IN&set=sectors", None),
        (3, "option chain", "GET", "/options/chain?exchange=NFO&underlying=NIFTY", None),
        (3, "company page", "GET", "/research/company/IN/RELIANCE", None),
        (2, "deep dive", "GET", "/research/deep/RELIANCE", None),
        (3, "search", "GET", "/instruments/search?q=rel&market=IN", None),
    ]


def start_server(port: int):
    config = uvicorn.Config(main.app, host="127.0.0.1", port=port, log_level="warning", workers=1)
    server = uvicorn.Server(config)
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(100):
        if server.started:
            return server
        time.sleep(0.05)
    raise RuntimeError("server didn't start")


WARM = True              # fill caches before users arrive, as the server does after its broker login
TIMELINE: list = []      # (start, seconds, label) of every request, to see when slow ones happened
THINK = (0.2, 1.0)        # seconds between a user's clicks; --think raises it to what real people do


async def user(n, c, tokens, plan, until, results, errors):
    rng = random.Random(n)
    weights = [w for w, *_ in plan]
    token = tokens[n % len(tokens)]
    hdr = {"Authorization": f"Bearer {token}", "X-Real-IP": f"10.0.{n // 250}.{n % 250}"}
    await asyncio.sleep(rng.uniform(0, 3))                   # people arrive over a few seconds, not in one instant
    if True:
        while time.monotonic() < until:
            _, label, method, path, body = rng.choices(plan, weights)[0]
            t = time.monotonic()
            try:
                r = await c.request(method, path, json=body, headers=hdr)
                took = time.monotonic() - t
                results[label].append(took)
                TIMELINE.append((t, took, label))
                if r.status_code >= 500 or r.status_code == 429:
                    errors[label].append(f"{r.status_code} {r.text[:120]}")
            except Exception as e:
                results[label].append(time.monotonic() - t)
                errors[label].append(f"{e.__class__.__name__}: {str(e)[:120]}")
            await asyncio.sleep(rng.uniform(*THINK))             # think time


def report(results, errors, seconds, users) -> dict:
    if TIMELINE:
        t0 = min(t for t, _, _ in TIMELINE)
        print("\nby 10 seconds: requests, median, slowest (quick pages only)")
        for b in range(0, seconds + 10, 10):
            xs = sorted(d for t, d, lbl in TIMELINE if b <= t - t0 < b + 10 and lbl in QUICK)
            if xs:
                print(f"  {b:3d}-{b + 10:3d}s {len(xs):5d} {statistics.median(xs):6.2f}s {xs[-1]:6.2f}s")
    rows = []
    total = sum(len(v) for v in results.values())
    for label, times in sorted(results.items(), key=lambda kv: -statistics.median(kv[1])):
        q = sorted(times)
        p95 = q[min(len(q) - 1, int(len(q) * 0.95))]
        rows.append({"what": label, "n": len(q), "median": statistics.median(q), "p95": p95, "max": q[-1], "errors": len(errors.get(label, []))})
    print(f"\n{users} users for {seconds}s: {total} requests ({total / seconds:.1f}/s)")
    print(f"{'request':16} {'count':>6} {'median':>8} {'p95':>8} {'max':>8} {'errors':>7}")
    for r in rows:
        print(f"{r['what']:16} {r['n']:6d} {r['median']:7.2f}s {r['p95']:7.2f}s {r['max']:7.2f}s {r['errors']:7d}")
    for label, es in errors.items():
        for e in list(dict.fromkeys(es))[:3]:
            print(f"  {label}: {e}")
    return {r["what"]: r for r in rows}


def serve(port: int, ready):
    """The server's own process (as in production, the users' requests come from elsewhere): the fake world,
    one notebook and one paper session to look at, then uvicorn."""
    mp = pytest.MonkeyPatch()
    w = world.build(mp)
    from tests.test_stress_fuzz import seed
    ctx = seed(w)
    sess = w["client"].post("/live/sessions", headers=world.headers("pro-token"),
                            json={"strategy": stress_requests.EMA, "instrument": "CRYPTO:BTC-USD"}).json()
    ctx["sid"] = sess.get("id", ctx.get("sid"))
    if WARM:
        from app import main as m
        m.warm_caches()
    start_server(port)
    ready.put(ctx)
    while True:
        time.sleep(3600)


def run(users: int, seconds: int, port: int = 8765) -> dict:
    import multiprocessing as mpr
    ctx_mp = mpr.get_context("spawn")      # a fresh process, like a real server: nothing inherited from the caller
    q = ctx_mp.Queue()
    proc = ctx_mp.Process(target=serve, args=(port, q), daemon=True)
    proc.start()
    ctx = q.get(timeout=120)
    results, errors = defaultdict(list), defaultdict(list)
    until = time.monotonic() + seconds

    async def go():
        # one client for every simulated user (as many browsers would be many machines): building 300 clients would
        # cost the load generator itself seconds of CPU and show up as server time
        # idle connections are dropped before the server's 5-second keep-alive ends: reusing one the server is closing
        # at that moment gives a ReadError that a browser would retry, which isn't a server failure
        limits = httpx.Limits(max_connections=users, max_keepalive_connections=users, keepalive_expiry=3)
        async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}", timeout=120, limits=limits) as c:
            await asyncio.gather(*(user(n, c, [f"load-{i}" for i in range(users)], mix(ctx), until, results, errors)
                                   for n in range(users)))
    try:
        asyncio.run(go())
    finally:
        proc.terminate()
    return report(results, errors, seconds, users), errors


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--users", type=int, default=50)
    ap.add_argument("--seconds", type=int, default=60)
    ap.add_argument("--think", type=float, nargs=2, default=None, help="min and max seconds between clicks")
    ap.add_argument("--cold", action="store_true", help="don't warm the caches first")
    a = ap.parse_args()
    if a.think:
        THINK = tuple(a.think)
    WARM = not a.cold
    run(a.users, a.seconds)
