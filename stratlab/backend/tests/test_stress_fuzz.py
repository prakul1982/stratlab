"""Stress: every API route called with valid, odd and hostile input, signed out and as each kind of user, and with
the AI answering well, badly or not at all. Nothing may crash (a 500), hang, or answer with something that isn't
JSON. A clear 4xx, or a 503 saying a source is busy, is the right answer to bad input or a missing source."""
import math
import time
from urllib.parse import quote

import pytest

from app import main
from tests import stress_requests, world

HOSTILE_STR = ["", " ", "a" * 5000, "../../etc/passwd", "%00", "\x00", "😀📈", "' OR 1=1 --", "<script>alert(1)</script>",
               "NaN", "-1", "0", "1e309", "IN:RELIANCE", "CRYPTO:BTC-USD", "US:AAPL", "nope:nope", "{}", "null"]
HOSTILE_NUM = [0, -1, -10**12, 10**12, 1.5, float("nan"), float("inf"), "12", None, True, [], {}]
TOKENS = [None, "garbage-token", "free-token", "pro-token", "admin-token"]
SKIP = {("POST", "/admin/kite/auto-login-now"), ("POST", "/admin/fixture/prices")}   # drive a browser / pull 2 years of data


def resolve(schema: dict, spec: dict) -> dict:
    while "$ref" in (schema or {}):
        name = schema["$ref"].split("/")[-1]
        schema = spec["components"]["schemas"][name]
    if "anyOf" in (schema or {}):
        opts = [s for s in schema["anyOf"] if s.get("type") != "null"]
        schema = opts[0] if opts else {}
    if "allOf" in (schema or {}):
        schema = schema["allOf"][0]
    return schema or {}


def valid(schema: dict, spec: dict, depth: int = 0):
    """A plausible value for a schema (the shape the frontend sends)."""
    s = resolve(schema, spec)
    if "default" in s and s["default"] is not None:
        return s["default"]
    if "enum" in s:
        return s["enum"][0]
    if "const" in s:
        return s["const"]
    t = s.get("type")
    if t == "object" or "properties" in s:
        if depth > 4:
            return {}
        return {k: valid(v, spec, depth + 1) for k, v in (s.get("properties") or {}).items()}
    if t == "array":
        return [valid(s.get("items") or {}, spec, depth + 1)] if depth < 4 else []
    if t == "integer":
        return max(s.get("minimum", 1), min(s.get("maximum", 10), 10))
    if t == "number":
        return float(max(s.get("minimum", 1), min(s.get("maximum", 10), 10)))
    if t == "boolean":
        return True
    return "RELIANCE"


def mutants(value, rng, n: int):
    """Copies of a valid body with one field at a time broken."""
    out = [None, {}, [], "text", 12, {"unexpected": "field"}]
    paths = []

    def walk(v, path):
        if isinstance(v, dict):
            for k, x in v.items():
                paths.append(path + [k])
                walk(x, path + [k])
        elif isinstance(v, list) and v:
            paths.append(path + [0])
            walk(v[0], path + [0])
    walk(value, [])
    for _ in range(n):
        if not paths:
            break
        import copy
        body = copy.deepcopy(value)
        path = rng.choice(paths)
        node = body
        for k in path[:-1]:
            node = node[k]
        node[path[-1]] = rng.choice(HOSTILE_STR + HOSTILE_NUM)
        out.append(body)
    return out


def _json_safe(v):
    """Values a JSON body can carry (NaN and infinity are sent as strings, as a hostile client might)."""
    if isinstance(v, float) and not math.isfinite(v):
        return str(v)
    if isinstance(v, dict):
        return {k: _json_safe(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_json_safe(x) for x in v]
    return v


def operations():
    spec = main.app.openapi()
    for path, ops in spec["paths"].items():
        for method, op in ops.items():
            if (method.upper(), path) in SKIP or path.startswith("/__") or path in ("/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"):
                continue
            yield method.upper(), path, op, spec


@pytest.fixture
def w(monkeypatch):
    built = world.build(monkeypatch)
    yield built
    built["close"]()


def seed(w):
    """Real things to point ids at: a notebook with an experiment, a shared link, a library entry, a paper session."""
    c, h = w["client"], world.headers("pro-token")
    k = w["kite"]
    ctx = {"in_stock": k.by_symbol("RELIANCE")["id"], "in_index": k.by_symbol("NIFTY 50")["id"]}
    nb = c.post("/notebooks", headers=h, json={"name": "Seed", "strategy": stress_requests.EMA, "instrument": "CRYPTO:BTC-USD"}).json()
    nid = nb.get("id", "missing")
    c.post(f"/notebooks/{nid}/experiments", headers=h, json={"days": 400})
    share = c.post(f"/notebooks/{nid}/experiments/1/share", headers=h, json={}).json()
    lib = c.post(f"/notebooks/{nid}/experiments/1/library", headers=h, json={"description": "x"}).json()
    sess = c.post("/live/sessions", headers=h, json={"strategy": stress_requests.EMA, "instrument": "CRYPTO:BTC-USD"}).json()
    ctx.update(nid=nid, version="1", symbol="RELIANCE", region="IN", inst_id="CRYPTO:BTC-USD", user_id="u-free",
               token=(share.get("token") or share.get("url", "x").rsplit("/", 1)[-1]), eid=str(lib.get("id") or "x"),
               sid=str(sess.get("id") or "x"))
    return ctx


def fill(v, ctx):
    """Swap "{name}" placeholders in a request for the seeded ids."""
    if isinstance(v, str) and v.startswith("{") and v.endswith("}") and v[1:-1] in ctx:
        return ctx[v[1:-1]]
    if isinstance(v, dict):
        return {k: fill(x, ctx) for k, x in v.items()}
    if isinstance(v, list):
        return [fill(x, ctx) for x in v]
    return v


def test_no_route_crashes_on_any_input(w):
    rng, c = w["rng"], w["client"]
    real = seed(w)
    reals = stress_requests.real_requests(real)
    crashes, slow = [], []
    for method, path, op, spec in operations():
        _reset(w)
        if "{nid}" in path or "{eid}" in path or "{token}" in path or "{sid}" in path:
            real = seed(w)                          # a fresh notebook, link and session: an earlier delete may have removed them
            reals = stress_requests.real_requests(real)
        params = [p for p in op.get("parameters", [])]
        body_schema = (((op.get("requestBody") or {}).get("content") or {}).get("application/json") or {}).get("schema")
        good = [(q, fill(b, real)) for q, b in reals.get((method, path), [])]
        if not good:
            good = [({}, valid(body_schema, spec) if body_schema else None)]
        cases = []
        for q, b in good:
            cases.append(("pro-token", {}, q, b))
        for token in TOKENS:
            cases.append((token, {}, good[0][0], good[0][1]))
        for _ in range(10):
            pv = {p["name"]: (real.get(p["name"]) if rng.random() < 0.4 and p["name"] in real else rng.choice(HOSTILE_STR))
                  for p in params if p["in"] == "path"}
            qv = {**good[0][0], **{p["name"]: rng.choice(HOSTILE_STR + [str(x) for x in HOSTILE_NUM]) for p in params
                                   if p["in"] == "query" and rng.random() < 0.7}}
            cases.append((rng.choice(TOKENS[2:]), pv, qv, rng.choice(good)[1]))
        for q, b in good[:3]:
            if isinstance(b, (dict, list)):
                for m in mutants(b, rng, 12):
                    cases.append((rng.choice(TOKENS[2:]), {}, q, m))
        for i, (token, pv, qv, body) in enumerate(cases):
            w["ai"].mode = "ok" if i < len(good) else ["ok", "garbage", "fail", "busy"][i % 4]
            pv = {p["name"]: pv.get(p["name"], real.get(p["name"], "x")) for p in params if p["in"] == "path"}
            url = path
            for k, v in pv.items():
                url = url.replace("{" + k + "}", quote(str(v), safe="") or "%20")
            hdr = world.headers(token) if token else {}
            if path.startswith("/admin") and token == "pro-token":
                hdr = world.headers("admin-token")
            t0 = time.monotonic()
            r = c.request(method, url, params=qv or None, headers=hdr,
                          json=_json_safe(body) if body is not None and method in ("POST", "PUT", "PATCH", "DELETE") else None)
            took = time.monotonic() - t0
            STATS.setdefault(f"{method} {path}", []).append(r.status_code)
            if i < len(good) and r.status_code >= 400:
                REAL_FAILS.append(f"{method} {url[:80]} q={str(qv)[:80]} body={str(body)[:160]} -> {r.status_code} {r.text[:220]}")
            if r.status_code >= 500 and not (r.status_code in (502, 503) and _clear(r)):
                crashes.append(f"{method} {url[:80]} q={str(qv)[:80]} body={str(body)[:120]} ai={w['ai'].mode} -> {r.status_code} {r.text[:200]}")
            elif r.headers.get("content-type", "").startswith("application/json"):
                try:
                    r.json()
                except ValueError:
                    crashes.append(f"{method} {url[:80]} -> {r.status_code} sent broken JSON")
            if took > 10:
                slow.append(f"{method} {url[:80]} q={str(qv)[:100]} body={str(body)[:100]} took {took:.1f}s")
    import os
    if os.environ.get("STRESS_REPORT"):
        for k, v in sorted(STATS.items()):
            print(f"REPORT {sum(1 for x in v if x < 300):3d}/{len(v):3d} ok  {k}  {sorted(set(v))}")
        for f in REAL_FAILS:
            print("REALFAIL", f)
    assert not crashes, f"{len(crashes)} crashes:\n" + "\n".join(dict.fromkeys(crashes))
    assert not slow, "\n".join(slow)


def _reset(w):
    """Between routes: a fresh per-minute request allowance, and no paper sessions left over from the last route
    (each plan caps how many run at once)."""
    from app.guard import Guard
    node = getattr(main.app, "middleware_stack", None)
    while node is not None:
        if isinstance(node, Guard):
            node.window._d.clear()
        node = getattr(node, "app", None)
    for sid in list(w["manager"].sessions):
        try:
            w["manager"].stop(sid, "test")
        except Exception:
            w["manager"].sessions.pop(sid, None)


REAL_FAILS: list[str] = []
STATS: dict[str, list[int]] = {}


def _clear(r) -> bool:
    try:
        d = r.json()["detail"]
        return bool(d.get("code") and d.get("message"))
    except Exception:
        return False
