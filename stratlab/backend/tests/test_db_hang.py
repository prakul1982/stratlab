"""15 Oct: slow database reads froze the signed-in API. The real database client against a fake Supabase on 127.0.0.1
(tests/db_hang_probe.py), with the lanes' waits made short: unrelated signed-in routes stay fast while jobs' reads hang,
a database that hangs for everything gives a quick 503, an invalid token never waits, and all is well once reads are
fast again."""
import httpx
import pytest

from app import db, http_retry
from tests import db_hang_probe as probe

HANG = 4.0


@pytest.fixture
def short_waits(monkeypatch):
    monkeypatch.setattr(db, "REQUEST_TIMEOUT", httpx.Timeout(1.0, connect=1.0, pool=0.5))
    monkeypatch.setattr(db, "REQUEST_DEADLINE", 1.5)
    monkeypatch.setattr(db, "SIGNIN_TIMEOUT", httpx.Timeout(1.0, connect=1.0, pool=0.5))
    monkeypatch.setattr(db, "JOB_TIMEOUT", httpx.Timeout(HANG + 5, connect=2.0))
    monkeypatch.setattr(http_retry, "RETRY_PAUSE", 0.01)
    monkeypatch.setattr(db, "RETRY_PAUSE", 0.01)


def test_signed_in_routes_stay_fast_while_jobs_hold_hanging_reads(monkeypatch, short_waits):
    """Before: 40 job reads held the one pool of 40 connections, so a page waited the whole hang (7.8 s for an 8 s
    hang) and an invalid token 7.7 s for its 401."""
    out = probe.run(monkeypatch.setattr, hang=HANG, jobs=40)
    assert out["page_codes"] == [200] and out["page_s"] < 1.0, out
    assert out["invalid_token_code"] == 401 and out["invalid_token_s"] < 0.5, out
    assert out["health_s"] < 0.5, out
    assert out["after_codes"] == [200] and out["after_s"] < 1.0, out


def test_a_database_hanging_for_everything_gives_a_quick_503_and_recovers(monkeypatch, short_waits):
    """Before: the page's dozen calls each read the profile in turn behind the one in flight (17 s for an 8 s hang),
    and a timed-out read was sent again."""
    out = probe.run(monkeypatch.setattr, hang=HANG, jobs=10, all_slow=True)
    assert out["page_codes"] == [503], out
    assert out["page_s"] < 2.5, out                          # one request-lane wait, not one per call or a retry
    assert out["invalid_token_code"] == 401 and out["invalid_token_s"] < 0.5, out
    assert out["health_s"] < 0.5, out
    assert out["after_codes"] == [200] and out["after_s"] < 1.0, out


def test_the_503_says_the_database_is_unreachable(monkeypatch, short_waits):
    server, client = probe.setup(monkeypatch.setattr)
    try:
        assert client.get("/notebooks", headers={"Authorization": f"Bearer {probe.GOOD}"}).status_code == 200
        db._profiles.clear()
        server.all_hang = HANG
        r = client.get("/notebooks", headers={"Authorization": f"Bearer {probe.GOOD}"})
        assert r.status_code == 503 and r.headers["Retry-After"] == "5"
        assert r.json()["detail"] == {"code": "db_unavailable", "message": "Couldn't reach the database, try again."}
    finally:
        server.close()


class _Hangs(httpx.BaseTransport):
    def __init__(self):
        self.calls = 0

    def handle_request(self, request):
        self.calls += 1
        raise httpx.ReadTimeout("timed out", request=request)


def test_a_request_lane_timeout_is_not_sent_again_but_a_jobs_is(monkeypatch):
    monkeypatch.setattr(http_retry, "RETRY_PAUSE", 0.0)
    monkeypatch.setattr(db, "RETRY_PAUSE", 0.0)
    made = []
    lanes = db.Lanes(network=lambda n: made.append(_Hangs()) or made[-1])
    request_lane, signin_lane, job_lane = made
    client = httpx.Client(transport=lanes, base_url="http://127.0.0.1:1")
    token = db._in_request.set(True)
    try:
        with pytest.raises(db.DatabaseUnavailable):
            client.get("/rest/v1/profiles")
        with pytest.raises(db.DatabaseUnavailable):
            client.get("/auth/v1/user")
    finally:
        db._in_request.reset(token)
    with pytest.raises(httpx.ReadTimeout) as e:
        client.get("/rest/v1/job_rows")
    assert not isinstance(e.value, db.DatabaseUnavailable)
    assert (request_lane.calls, signin_lane.calls, job_lane.calls) == (1, 1, 2)


def test_the_lanes_have_their_own_pools_and_waits():
    lanes = db.Lanes()
    pools = {id(t.inner._pool) for t, _ in (lanes.request, lanes.signin, lanes.job)}
    assert len(pools) == 3
    req = httpx.Request("GET", "http://x/rest/v1/profiles")
    assert lanes.lane(req) is lanes.job                            # no request around it: a job
    token = db._in_request.set(True)
    try:
        assert lanes.lane(req) is lanes.request
        assert lanes.lane(httpx.Request("GET", "http://x/auth/v1/user")) is lanes.signin
        assert lanes.request[1].read <= 8 and lanes.job[1].read == 30
    finally:
        db._in_request.reset(token)
    lanes.close()
