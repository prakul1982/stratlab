"""One retry for a read whose connection broke (R5O-002, R9R-009).

A client that keeps connections open meets a server that closed one while it sat idle ("Server disconnected without
sending a response", a bare ConnectionTerminated): the request fails although nothing is wrong. 22 of the 23 server
errors kept from before the 9 Oct restart were exactly that, on GET /me, /tax, /holdings, /research/results and
/admin/overview. Every long-lived HTTP client on a read path uses RetryReads, so such a read is sent once more, on a
new connection. A write is sent again only when it never left (the connection couldn't be opened): nothing is ever
saved twice."""
import time

import httpx

READ_METHODS = ("GET", "HEAD", "OPTIONS")
RETRY_PAUSE = 0.25            # seconds before the one retry, so a server that is restarting has a moment
KEEPALIVE_EXPIRY = 5.0        # an idle connection is closed after this long: inside the idle timeout of any server or proxy we talk to


class RetryReads(httpx.BaseTransport):
    """A read that fails because the connection broke is sent once more, on a new connection. A write is sent again
    only when it never left (the connection couldn't be opened), so nothing is ever saved twice."""

    def __init__(self, inner: httpx.BaseTransport):
        self.inner = inner

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        try:
            return self._send(request)
        except (httpx.ConnectError, httpx.ConnectTimeout) as e:
            print("http: connect failed, trying again:", type(e).__name__)
        except (httpx.RemoteProtocolError, httpx.ReadError, httpx.WriteError, httpx.ReadTimeout, httpx.PoolTimeout) as e:
            if request.method not in READ_METHODS:
                raise
            print("http: connection dropped during a read, trying again:", type(e).__name__)
            self._drop_idle()
        time.sleep(self._pause())
        return self._send(request)

    def _pause(self) -> float:
        return RETRY_PAUSE

    def _drop_idle(self) -> None:
        """Close the connections sitting idle in the pool, so the retry opens a new one: one connection the server closed
        means the others that sat as long probably are closed too, and a retry on one of them would fail the same way."""
        try:
            for c in list(self.inner._pool.connections):      # httpcore's pool; a transport without one has nothing to drop
                if c.is_idle():
                    c.close()
        except Exception:
            pass

    def _send(self, request: httpx.Request) -> httpx.Response:
        resp = self.inner.handle_request(request)
        try:
            resp.read()             # read the body here, so a connection that drops halfway is also caught above
        except BaseException:
            resp.close()
            raise
        return resp

    def close(self) -> None:
        self.inner.close()


def real_transport() -> httpx.BaseTransport:
    """The transport for a client that talks to the network: HTTP/1.1 connections with a short keep-alive, and the retry."""
    return RetryReads(httpx.HTTPTransport(http2=False, limits=httpx.Limits(
        max_connections=40, max_keepalive_connections=20, keepalive_expiry=KEEPALIVE_EXPIRY)))
