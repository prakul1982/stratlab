"""Live prices for open charts and Market Watch lists, tick by tick (MW-1).

One connection to the broker's feed already runs for paper trading (kite_service.TickHub); a viewer never opens another.
While a chart or the panel is open, the instruments in view are added to that connection as listeners, and the page reads
them over a server-sent-events stream: one HTTP response per open page, an event at most twice a second for any symbol, each
carrying the last price and the day's traded volume so the page can build the forming candle itself. A symbol is
subscribed when its first viewer arrives and dropped a short while after its last one leaves (GRACE, so a chart switched
from 1m to 5m, or a reload, doesn't unsubscribe and resubscribe). Nothing runs when nobody is watching.

Instruments the broker's feed doesn't carry (US and other markets' stocks, forex, commodities, crypto) are not streamed:
the page reads them every few seconds through the quotes, as the same panel did before.

Bounded: MAX_TOKENS instruments across all viewers (the ticker allows 3,000), MAX_PER_CONN in one stream, CONNS_PER_USER
streams per person, and a stream is closed after MAX_AGE so the page signs in again. The state kept per viewer is a few
small dicts. Facts only: prices as the exchange printed them."""
import asyncio
import threading
import time
from datetime import datetime, timezone

MAX_TOKENS = 250            # instruments streamed at once, for everyone
MAX_PER_CONN = 40           # instruments in one stream
CONNS_PER_USER = 3          # open streams per person (a few tabs)
MIN_GAP = 0.5               # seconds between events on one stream: a symbol moves at most twice a second
GRACE = 20.0                # seconds an instrument stays subscribed after its last viewer leaves
HEARTBEAT = 15.0            # a comment this often keeps proxies from closing a quiet stream
MAX_AGE = 20 * 60           # a stream is closed after this long; the page opens another
WS_LISTENER = "watch:"      # prefix of the listener ids this module adds to the tick hub


class Conn:
    """One open stream: the instruments it follows (key -> token), which of them have a newer tick, and its wake-up."""

    def __init__(self, cid: str, user: str, keys: dict, loop):
        self.id, self.user, self.by_token, self.loop = cid, user, {t: k for k, t in keys.items()}, loop
        self.dirty: set[int] = set()
        self.event = asyncio.Event()
        self.woken = False                     # a wake-up is already on its way: more ticks need not send another
        self.closed = False
        self.opened = time.monotonic()


class StreamHub:
    def __init__(self, ticks, resolve, clock=time.monotonic, start_timer=None):
        """`ticks`: the shared TickHub (add, remove, started, start); `resolve(key)`: the broker's token for a chart key such
        as "IN:RELIANCE", or None when the broker's feed doesn't carry it. `clock` and `start_timer` can be replaced by a test."""
        self.ticks, self.resolve, self.clock = ticks, resolve, clock
        self.start_timer = start_timer or self._timer
        self.lock = threading.Lock()
        self.conns: dict[str, Conn] = {}
        self.refs: dict[int, set[str]] = {}            # token -> the streams following it
        self.idle: dict[int, float] = {}               # token -> when its last viewer left
        self.latest: dict[int, dict] = {}              # token -> its last tick, as sent
        self.sweeping = False
        self.n = 0

    # ---------- viewers ----------
    def open(self, user: str, keys: list[str], loop) -> tuple[Conn | None, list[str], list[str]]:
        """Start following `keys` for a viewer: (the stream, the keys streamed, the keys left to the page's own polling).
        None when this person already has CONNS_PER_USER streams open."""
        resolved: dict[str, int] = {}
        for k in dict.fromkeys(keys):
            if len(resolved) >= MAX_PER_CONN:
                break
            try:
                tok = self.resolve(k)
            except Exception:
                tok = None
            if tok:
                resolved[k] = int(tok)
        with self.lock:
            if sum(1 for c in self.conns.values() if c.user == user) >= CONNS_PER_USER:
                return None, [], list(keys)
            fresh = {t for t in resolved.values() if t not in self.refs}
            room = MAX_TOKENS - len(self.refs)
            if len(fresh) > room:                               # past the cap, the newest instruments stay with the page's polling
                drop = {t for t in sorted(fresh)[max(room, 0):]}
                resolved = {k: t for k, t in resolved.items() if t not in drop}
            self.n += 1
            conn = Conn(f"c{self.n}", user, resolved, loop)
            self.conns[conn.id] = conn
            added = []
            for t in conn.by_token:
                self.idle.pop(t, None)
                if t not in self.refs:
                    self.refs[t] = set()
                    added.append(t)
                self.refs[t].add(conn.id)
        for t in added:
            self.ticks.add(f"{WS_LISTENER}{t}", t, lambda tick, tok=t: self.on_tick(tok, tick))
        return conn, list(resolved), [k for k in keys if k not in resolved]

    def close(self, conn: Conn) -> None:
        """A viewer left. An instrument nobody else follows is dropped after GRACE."""
        start = False
        with self.lock:
            conn.closed = True
            if self.conns.pop(conn.id, None) is None:
                return
            for t in conn.by_token:
                refs = self.refs.get(t)
                if refs is not None:
                    refs.discard(conn.id)
                    if not refs:
                        self.idle[t] = self.clock()
            start = bool(self.idle) and not self.sweeping
            if start:
                self.sweeping = True
        if start:
            self.start_timer(GRACE + 0.5, self.sweep)

    def _timer(self, after: float, fn) -> None:
        t = threading.Timer(after, fn)
        t.daemon = True
        t.start()

    def sweep(self, now: float | None = None) -> int:
        """Drop the instruments whose last viewer left GRACE seconds ago or more; how many went. Runs once after the last
        viewer leaves, and again while some are still waiting out their grace."""
        now = self.clock() if now is None else now
        gone, again = [], False
        with self.lock:
            for t, since in list(self.idle.items()):
                if now - since >= GRACE and not self.refs.get(t):
                    self.idle.pop(t, None)
                    self.refs.pop(t, None)
                    self.latest.pop(t, None)
                    gone.append(t)
            again = bool(self.idle)
            self.sweeping = again
        for t in gone:
            self.ticks.remove(f"{WS_LISTENER}{t}")
        if again:
            self.start_timer(GRACE / 2, self.sweep)
        return len(gone)

    # ---------- ticks ----------
    def on_tick(self, token: int, tick: dict) -> None:
        """A tick from the broker's feed (its own thread): keep the latest and wake the streams following the instrument."""
        price = tick.get("last_price")
        if price is None:
            return
        ts = tick.get("exchange_timestamp") or tick.get("last_trade_time")
        at = ts.isoformat() if hasattr(ts, "isoformat") else datetime.now(timezone.utc).isoformat(timespec="seconds")
        row = {"p": float(price), "v": tick.get("volume_traded"), "t": at}
        with self.lock:
            self.latest[token] = row
            targets = [self.conns[c] for c in self.refs.get(token, ()) if c in self.conns]
            for c in targets:
                c.dirty.add(token)
        for c in targets:
            if c.woken:
                continue
            c.woken = True
            try:
                c.loop.call_soon_threadsafe(c.event.set)
            except RuntimeError:                         # its loop has closed: the stream is gone
                pass

    def take(self, conn: Conn) -> list[dict]:
        """The newest price of each instrument that ticked since the last call, keyed as the page asked: [{"k", "p", "v", "t"}]."""
        with self.lock:
            toks, conn.dirty = list(conn.dirty), set()
            return [{"k": conn.by_token[t], **self.latest[t]} for t in toks if t in self.latest and t in conn.by_token]

    def snapshot(self, conn: Conn) -> list[dict]:
        """The last price of every instrument the stream follows that has ticked, to start the page off."""
        with self.lock:
            return [{"k": k, **self.latest[t]} for t, k in conn.by_token.items() if t in self.latest]

    # ---------- the response ----------
    async def feed(self, conn: Conn, hello: dict, request=None):
        """The stream's events as text: `hello` once, a `tick` event at most every MIN_GAP seconds while prices move, a comment
        every HEARTBEAT seconds when they don't, and `bye` after MAX_AGE (the page opens another). Ends when the viewer goes."""
        import json

        def event(name: str, data) -> str:
            return f"event: {name}\ndata: {json.dumps(data, separators=(',', ':'))}\n\n"
        try:
            yield event("hello", hello)
            first = self.snapshot(conn)
            if first:
                yield event("tick", first)
            last = 0.0
            while not conn.closed:
                try:
                    await asyncio.wait_for(conn.event.wait(), HEARTBEAT)
                except asyncio.TimeoutError:
                    if time.monotonic() - conn.opened > MAX_AGE:
                        yield event("bye", {"reason": "reopen"})
                        return
                    if request is not None and await request.is_disconnected():
                        return
                    yield ": keep-alive\n\n"
                    continue
                conn.event.clear()
                conn.woken = False                       # a tick from here on wakes it again; what came before is taken below
                gap = MIN_GAP - (time.monotonic() - last)
                if gap > 0:
                    await asyncio.sleep(gap)
                rows = self.take(conn)
                if rows:
                    last = time.monotonic()
                    yield event("tick", rows)
                if request is not None and await request.is_disconnected():
                    return
        finally:
            self.close(conn)

    # ---------- what is held ----------
    def stats(self) -> dict:
        with self.lock:
            return {"streams": len(self.conns), "instruments": len(self.refs), "waiting": len(self.idle), "kept": len(self.latest)}
