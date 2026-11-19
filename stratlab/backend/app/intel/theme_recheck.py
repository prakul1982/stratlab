"""Every stored theme checked again after a version change (r66e, LIVE12A-001/002/006).

The theme library keeps a theme's checked read under the membership rules' version (theme_library.key_of) and its dive under the rules', the
dive text's and the sector figures' versions (theme_routes.dive_key). A deploy that bumps one of them made every stored read and dive miss, and
nothing made them again until someone opened that theme: the app's and the public theme pages kept showing maps stored on 7, 8 and 13 Nov
after three engine releases had shipped, the first visit after a deploy waited on a whole re-check (Semiconductors "Checking each company
against its own description…" for 90 s, Private banks ready in 57 s), and the engine's fixes never reached a page nobody opened.

Now, when the versions a theme's read rests on change (`mark`: the rules, the dive text, the sector figures' rules and the deck's), every stored
theme is queued (`queue`), and one background job (`Job`) works through the queue one theme at a time, in the memory guard's turn, with a
pause between themes: a theme already current under today's versions (its library entry and its dive both stored) is skipped; any other has
its stored AI map checked again under today's rules, kept in the library, and its dive worked out and kept (`rebuild`). The queue is kept in
the database, so a restart goes on where it stopped; a theme whose check is not finished is tried again later, at most TRIES times. A page
that serves a theme's older read meanwhile moves that theme to the front of the queue (`ask`) and says it is being checked again.

Bounded: one theme at a time, no AI map is ever written by the job (a theme whose map is not stored is left with the reason), and only the
leader container runs it."""
import json
import threading
import time

from .. import computed, db

STATE_KEY = "theme:recheck"
TRIES = 4                  # a theme whose check is not finished yet is tried again at most this many times (at the end of the queue)
FIRST_WAIT = 180.0         # seconds after the start before the first theme (the server warms its caches first)
GAP = 60.0                 # seconds between two themes while the queue holds more
IDLE = 900.0               # seconds between two looks at an empty queue (a version bump is a deploy, so a start looks at once)
ASK_EVERY = 60.0           # a page asking for the same theme again within this long is not written down again
# r69e (live R68 logs, 10:50-11:30 UTC: "US restaurant: failed (its checks are not finished yet)" every ~4 min, each page view moving it to
# the front; nine themes "failed (its dive was not kept)" put back on the queue again and again, the queue staying at 25-27): a theme whose
# checks are not finished waits for them, WAIT_FIRST seconds and twice as long each time after (at most WAIT_MAX), never retried at once,
# WAIT_TRIES times; a theme that fails the same way twice is left, with why, until the next version change
WAIT_FIRST = 600.0
WAIT_MAX = 3600.0
WAIT_TRIES = 6
YIELD_WAIT = 30.0          # r69e: seconds a phase of a rebuild waits for the memory guard's turn to be free of every other job, else it yields
# fix20 (LIVE14A-002/-005: Semiconductors, Software and REITs served "the new read is being worked out" for 10 hours on 12-13 Nov prices while
# the US market was open): a busy server never left the memory guard's turn free for YIELD_WAIT seconds, so the most-read theme yielded at the
# front of the queue again and again and no theme behind it moved. After YIELD_MAX yields in a row a theme's rebuild waits for its turn as any
# other heavy job does (memguard.heavy, as the page's own behind-read does) instead of giving way once more
YIELD_MAX = 3
_force: dict = {}          # {"on": True} while a rebuild that yielded YIELD_MAX times runs in the plain turn
SYSTEM = {"id": "", "_plan": "pro", "plan": "pro", "email": None}      # the job, not a person: counts against nobody, never starts an AI map
_lock = threading.Lock()
_asked: dict = {}          # (market, name) -> when a page last asked for it
_running: dict = {}        # {"theme": [market, name]} while one is being worked out


def mark() -> str:
    """The versions a stored theme's read and dive rest on, as one string: a change in any of them queues every stored theme."""
    from .. import deck
    from . import sector_metrics, theme_base, theme_data
    return f"r{theme_base.RULES}.td{theme_data.DIVE_TEXT}.sm{sector_metrics.VERSION}.dk{deck.THEME_DECK_VERSION}"


def _load() -> dict:
    try:
        st = db.json_value(db.get_setting(STATE_KEY), {}) or {}
    except Exception:
        st = {}
    return st if isinstance(st, dict) else {}


def _save(st: dict) -> None:
    try:
        db.set_setting(STATE_KEY, json.dumps(st, separators=(",", ":"), default=str))
    except Exception as e:
        print("theme re-check: queue not kept:", type(e).__name__, str(e)[:120])


def stored_themes() -> list[list[str]]:
    """[[market, name]] of every theme the library keeps (the newest entry of each, under today's rules or older ones, as the public pages
    list them), the most read first."""
    from . import theme_base, theme_library
    best: dict = {}
    for e in (computed.index(theme_library.KIND).get("entries") or {}).values():
        m = e.get("meta") or {}
        if e.get("region") not in ("IN", "US") or not isinstance(m.get("rules"), int) or m["rules"] > theme_base.RULES or not m.get("q"):
            continue
        k = (e["region"], str(m["q"]))
        hits = int(e.get("hits") or 0)
        if k not in best or hits > best[k]:
            best[k] = max(hits, best.get(k, 0))
    return [list(k) for k, _ in sorted(best.items(), key=lambda x: (-x[1], x[0]))]


def queue(now: float | None = None) -> int:
    """Every stored theme queued when the versions changed since the queue was last made (`mark`); how many were queued (0: no change)."""
    with _lock:
        st = _load()
        if st.get("mark") == mark():
            return 0
        todo = stored_themes()
        _save({"mark": mark(), "todo": todo, "done": 0, "current": 0, "failed": {}, "left": {},
               "queued_at": time.time() if now is None else now, "from": st.get("mark")})
        print(f"theme re-check: {len(todo)} stored themes queued under {mark()} (was {st.get('mark') or 'none'})")
        return len(todo)


def queued(region: str, name: str) -> bool:
    """Whether a theme is in the queue or being worked out now."""
    if _running.get("theme") == [region, name]:
        return True
    return [region, name] in (_load().get("todo") or [])


def ask(region: str, name: str, now: float | None = None) -> bool:
    """A page served this theme's older read: it goes to the front of the queue (queued first if it isn't) and the job is woken. Whether
    the theme is queued or being worked out."""
    now = time.time() if now is None else now
    k = (region, name)
    if now - _asked.get(k, 0.0) < ASK_EVERY:
        return True
    _asked[k] = now
    if len(_asked) > 500:
        _asked.clear()
    if _running.get("theme") == [region, name]:
        return True
    with _lock:
        st = _load()
        if st.get("mark") != mark():
            st = {"mark": mark(), "todo": stored_themes(), "done": 0, "current": 0, "failed": {}, "left": {}, "queued_at": now, "from": st.get("mark")}
        k = f"{region}|{name}"
        # r69e: a theme left after its tries (failed the same way twice, or its checks never finished) or waiting for its checks is not
        # moved by a page's view: each view put it first and it was tried again at once, every few minutes
        if k in (st.get("left") or {}):
            return False
        if float((st.get("wait") or {}).get(k) or 0) > now:
            return True
        todo = [x for x in st.get("todo") or [] if x != [region, name]]
        st["todo"] = [[region, name]] + todo
        _save(st)
    job.wake.set()
    return True


def page_key(region: str, name: str) -> list | None:
    """r69e (live R68: nine themes "failed (its dive was not kept)" each pass, rebuilt and kept every time): the key a theme's dive is kept
    and read under, worked out as the page and the rebuild work it out: the library's stored read (by its own name) with today's market
    values (theme_routes.checked: the figures' window, and so the key's count of described companies, follows them). The re-check read the
    key off the stored read without them, a key no dive was ever kept under. None when no read is stored under today's rules."""
    from . import theme_library, theme_routes
    hit = theme_library.stored(region, name)
    if hit is None or not isinstance(hit.get("payload"), dict):
        return None
    theme = " ".join(str(name).split())[:80]
    try:
        m = theme_routes.with_descriptions(region, theme_routes.checked(region, theme, {**hit["payload"], "_library": hit["name"]}))
        return theme_routes.dive_key(region, theme, m)
    except Exception:
        return None


def current(region: str, name: str) -> bool:
    """Whether a theme's read is stored under today's rules and its dive under today's versions (under the key its page reads)."""
    from . import theme_library
    from . import theme_routes
    key = page_key(region, name)
    # e81 (item 6): the store's index says whether the dive is kept; the dive itself (up to 4 MB) is not read for that
    return key is not None and (computed.has(theme_library.DIVE, key) or theme_routes.unkept_dive(key) is not None)


class NotDone(Exception):
    """The theme could not be made current on this try (its checks still running, its map not stored). `later`: its checks are not
    finished, so it waits for them (r69e)."""

    def __init__(self, why: str, final: bool = False, later: bool = False):
        super().__init__(why)
        self.final = final
        self.later = later


class Yielded(Exception):
    """r69e: a phase of the rebuild gave the memory guard's turn to the jobs waiting for it (the user-facing price jobs first); the theme
    stays at the front of the queue, its tries not counted."""


@__import__("contextlib").contextmanager
def _turn(phase: str):
    """r69e: one phase of a rebuild in the memory guard's turn, taken only when no other job holds or waits for it (memguard.heavy_idle),
    so the background re-check never stands in front of a page's price job; Yielded when the turn stayed busy for YIELD_WAIT seconds."""
    from .. import memguard
    if _force.get("on"):                  # fix20: yielded YIELD_MAX times in a row: it waits for its turn instead
        with memguard.heavy(f"theme re-check: {phase}"):
            yield
        return
    with memguard.heavy_idle(f"theme re-check: {phase}", YIELD_WAIT) as got:
        if not got:
            raise Yielded(f"the {phase} gave way to other jobs")
        yield


def _queries(region: str, name: str) -> list[str]:
    """The searches a theme's stored map may be kept under: the one its newest entry was kept from, its name, its label and its aliases."""
    from . import theme_library
    out: list[str] = []
    best = None
    for hk, e in (computed.index(theme_library.KIND).get("entries") or {}).items():
        m = e.get("meta") or {}
        if e.get("region") == region and m.get("q") == name and isinstance(m.get("rules"), int):
            rank = (m["rules"], float(e.get("at") or 0))
            if best is None or rank > best[0]:
                best = (rank, hk, e)
    if best:
        got = computed.get_hk(theme_library.KIND, best[1]) or {}
        out.append(str((got.get("value") or {}).get("q") or ""))
        out += [str(best[2].get("label") or "")] + [str(a) for a in (best[2].get("meta") or {}).get("aliases") or []]
    out.append(name)
    return [q for q in dict.fromkeys(" ".join(x.split())[:80] for x in out) if len(q) >= 2]


def rebuild(region: str, name: str) -> None:
    """The theme checked again under today's rules from its stored AI map (no new map is written), kept in the library, and its dive worked
    out and kept. Raises NotDone when it can't be finished on this try."""
    from . import ai as A
    from . import routes as R
    from . import theme_library, theme_routes
    q = next((x for x in _queries(region, name) if A.peek("sector", (region, x.lower()))), None)
    cur = theme_library.stored(region, name)
    if cur is None:
        if q is None:
            raise NotDone("its AI map is not stored, so it is checked again when someone opens it", final=True)
        with _turn("check"):
            payload = R.sector_payload(SYSTEM, region, q, False, wait=True)
            if not theme_library.keep(region, q, payload):
                raise NotDone("its checks are not finished yet", later=True)
    r, theme, m, _ = R.theme_map(SYSTEM, region, name)
    if not m.get("_library") or m.get("_older"):
        raise NotDone("its read is not kept under today's rules")
    m = theme_routes.with_descriptions(r, theme_routes.checked(r, theme, m))
    if not (m.get("placements") or {}).get("checked"):
        raise NotDone("its checks are not finished yet", later=True)          # a dive is kept only for a checked map
    with _turn("dive"):
        theme_routes.dive_of(r, theme, m, rebuild=True)
    return theme_routes.dive_key(r, theme, m)


def release() -> None:
    """e81 (item 6, the live R79 re-check peaking at 1.92 GB of a 2 GB limit): after each theme, the objects its rebuild freed are collected
    and the C heap's free pages returned to the system (glibc's malloc_trim), so one theme's dive (a few MB of JSON, tens of MB as objects)
    is never still held by the process while the next is built. Nothing else is touched; a system without it does nothing."""
    import gc
    gc.collect()
    try:
        import ctypes
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except Exception:
        pass


def _due(st: dict, now: float) -> list | None:
    """The first theme of the queue not waiting for its checks (r69e), or None."""
    wait = st.get("wait") or {}
    return next((x for x in st.get("todo") or [] if float(wait.get(f"{x[0]}|{x[1]}") or 0) <= now), None)


def step(work=None, now: float | None = None) -> dict | None:
    """The first theme of the queue that is due made current (or skipped when it is), taken off the queue. r69e: one whose checks are not
    finished waits for them (WAIT_FIRST, doubling, WAIT_TRIES times, then left); one that fails the same way twice is left with why; one
    whose rebuild gave the memory guard's turn to other jobs stays first, not counted. {"theme", "outcome", "why"}, or None when no theme
    of the queue is due (an empty queue, or every one waiting)."""
    now = time.time() if now is None else now
    st = _load()
    due = _due(st, now)
    if due is None:
        return None
    region, name = due
    k = f"{region}|{name}"
    why = ""
    _running["theme"] = [region, name]
    if int((st.get("yields") or {}).get(k) or 0) >= YIELD_MAX:
        _force["on"] = True
    try:
        if current(region, name):
            outcome = "current"
        else:
            key = (work or rebuild)(region, name)
            from . import theme_library
            kept = isinstance(key, list) and computed.has(theme_library.DIVE, key)          # e81: from the index, never the dive read
            outcome = "rebuilt" if kept or current(region, name) else "failed"
            big = computed.last_unkept.get(theme_library.DIVE)
            # e80 (LIVE16A-003): why it was not kept, when the store refused it as too big
            why = "" if outcome == "rebuilt" else "its dive was not kept" + (f" (too big: {big:,} bytes)" if big else "")
    except Yielded as e:
        outcome, why = "yielded", str(e)
    except NotDone as e:
        outcome, why = ("left" if e.final else "waiting" if e.later else "failed"), str(e)
    except Exception as e:
        outcome, why = "failed", f"{type(e).__name__}: {str(e)[:120]}"
        print("theme re-check:", region, name, why)
    finally:
        _running.pop("theme", None)
        _force.pop("on", None)
        release()               # e81 (item 6): what the theme's rebuild left freed is given back before the next one
    with _lock:
        st = _load()                 # a page may have asked meanwhile
        if outcome == "yielded":     # its place kept at the front, nothing counted (fix20: its yields in a row counted)
            st["todo"] = [[region, name]] + [x for x in st.get("todo") or [] if x != [region, name]]
            st.setdefault("yields", {})[k] = int((st.get("yields") or {}).get(k) or 0) + 1
        else:
            st["todo"] = [x for x in st.get("todo") or [] if x != [region, name]]
            (st.get("yields") or {}).pop(k, None)
        st.setdefault("wait", {}).pop(k, None)
        if outcome == "current":
            st["current"] = int(st.get("current") or 0) + 1
        elif outcome == "rebuilt":
            st["done"] = int(st.get("done") or 0) + 1
            st.get("failed", {}).pop(k, None)
        elif outcome != "yielded":
            before = (st.get("failed") or {}).get(k) or {}
            tries = int(before.get("n") or 0) + 1
            st.setdefault("failed", {})[k] = {"n": tries, "why": why}
            if outcome == "waiting" and tries < WAIT_TRIES:
                st["todo"].append([region, name])
                st["wait"][k] = now + min(WAIT_MAX, WAIT_FIRST * 2 ** (tries - 1))
            elif outcome == "failed" and tries < TRIES and before.get("why") != why:
                st["todo"].append([region, name])
            else:
                if outcome == "failed" and before.get("why") == why:
                    why = f"failed the same way twice: {why}"
                    print(f"theme re-check: {region} {name}: stopped, {why}")
                st.setdefault("left", {})[k] = why
        st["last"] = {"theme": [region, name], "outcome": outcome, "why": why, "at": now}
        _save(st)
    print(f"theme re-check: {region} {name}: {outcome}{(' (' + why + ')') if why else ''}; {len(st['todo'])} left")
    return {"theme": [region, name], "outcome": outcome, "why": why}


class Job:
    def __init__(self, work=None):
        self.work = work
        self.wake = threading.Event()
        self.status = {"last_run": None, "last_error": None}

    def start(self):
        import os
        if os.environ.get("THEME_RECHECK", "1").strip().lower() in ("0", "false", "no", "off"):
            return
        threading.Thread(target=self._loop, daemon=True, name="theme-recheck").start()

    def tick(self) -> dict | None:
        """One pass: the queue made when the versions changed, then one theme of it, in the memory guard's turn."""
        queue()
        if not _load().get("todo"):
            return None
        # r69e: no turn held around the whole theme: each phase of the rebuild takes the memory guard's turn only when no other job holds
        # or waits for it (_turn), so a page's price job never waits behind the re-check
        out = step(self.work)
        self.status["last_run"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        return out

    def _loop(self):
        from .. import leader
        self.wake.wait(FIRST_WAIT)
        while True:
            more = False
            try:
                if leader.leading():
                    more = self.tick() is not None
            except Exception as e:
                self.status["last_error"] = str(e)[:200]
                print("theme re-check job:", type(e).__name__, str(e)[:160])
            self.wake.clear()
            self.wake.wait(GAP if more else IDLE)


job = Job()


def state() -> dict:
    """The queue as Admin and the pages read it: the versions, how many are left, done, current already, left with a reason."""
    st = _load()
    return {"mark": st.get("mark"), "now": mark(), "todo": len(st.get("todo") or []), "done": st.get("done") or 0,
            "current": st.get("current") or 0, "left": st.get("left") or {}, "last": st.get("last"),
            "running": _running.get("theme")}
