"""Stock quotes read once and shared by everyone who asks for them within a few seconds (LIVE-1).

Pages that show prices read them again each minute while the market trades (frontend lib/liveRefresh). Without this, each
of those reads was one request to the broker's feed for each person with a page open, and the feed allows about three a
second for the whole app. A symbol's quote is kept for `SHARE_FOR` seconds, whoever asked first; a request asks the feed
only for the symbols not kept (one batched call). A symbol the feed did not answer is kept as unanswered for as long, so a
delisted or mistyped one is not asked for again by every page. Bounded: the oldest entries go first."""
import threading
import time

SHARE_FOR = 15.0           # seconds a quote is reused: well under the pages' minute
MAX_ITEMS = 6000           # a bit over every NSE and BSE equity; a row is a small dict

_lock = threading.Lock()
_kept: dict = {}           # (feed, symbol) -> (read at, quote or None)


def read(feed, symbols: list[str], fetch=None, ttl: float = SHARE_FOR) -> dict:
    """{symbol: quote} for `symbols` from `fetch(missing)` (default: `feed.quote`), reusing quotes read within `ttl` seconds.
    `feed` is the object the quotes come from, so two feeds (a test's fake and the real one) never share. Symbols without a
    quote are left out of the answer, as `fetch` leaves them out. Raises what `fetch` raises, keeping nothing."""
    fetch = fetch or feed.quote
    now = time.monotonic()
    out, missing = {}, []
    with _lock:
        for s in symbols:
            hit = _kept.get((feed, s))
            if hit and now - hit[0] < ttl:
                if hit[1] is not None:
                    out[s] = dict(hit[1])
            else:
                missing.append(s)
    if not missing:
        return out
    got = fetch(missing) or {}
    at = time.monotonic()
    with _lock:
        for s in missing:
            row = got.get(s)
            _kept[(feed, s)] = (at, dict(row) if row is not None else None)
            if row is not None:
                out[s] = row
        if len(_kept) > MAX_ITEMS:              # the oldest go first, down to half: not one pass for each new symbol
            for k in sorted(_kept, key=lambda k: _kept[k][0])[: len(_kept) - MAX_ITEMS // 2]:
                _kept.pop(k, None)
    return out


def forget() -> None:
    with _lock:
        _kept.clear()
