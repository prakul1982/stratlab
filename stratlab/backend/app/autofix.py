"""Self-healing checks (owner, 4 Nov: "fix it so that in real time everything is fixed, and only if it's not able to, then bug me").

One mechanism for every check that can go wrong: each source lists its checks (a job that failed or is stuck, the exchange holidays
running out, an AI provider failing), each with a problem (None when fine) and a bounded remedy (re-run the job through its own Run now,
read the list again, measure the provider again). Every TICK the sweep:
  - tries the remedy of each problem whose next try is due: at most TRIES tries, spaced by the check's backoff, never an always-on loop;
  - when a problem is gone, writes "fixed" into a short history that Admin shows ("IPOs: re-ran the job at 23:15 IST — fixed");
  - when the tries are used up (or the check needs something only the owner can do: a key, a payment, a setting, a manual login),
    ESCALATES: one email to the admins, "[StratLab needs you] <check>: <what failed>", saying what was tried and the exact action,
    de-duplicated (one mail per issue until it changes) and capped per day; it is also listed in Needs your attention.

Hard limits: a remedy only re-runs StratLab's own reads (never a job that mails users or reads their accounts, never a payment or an
order, never Zerodha's login, which escalates through its own alert); mail goes to the admin addresses only; texts are cut short and
passed through redact_ids, so no account id or key reaches a mail.

The state (each open issue, the history, today's mail count) is one database setting, small and bounded (HISTORY_MAX entries,
HISTORY_DAYS days)."""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable

from . import db, leader

IST = timezone(timedelta(hours=5, minutes=30))
KEY = "autofix:state"
TICK = 600                          # seconds between sweeps (the jobs' own schedulers run every few minutes; this only follows up)
FIRST_WAIT = 300                    # after boot, so a restart's own catch-up runs first
TRIES = 3
BACKOFF = (15 * 60, 45 * 60, 2 * 3600)     # before try 1, 2, 3 (counted from when the issue was seen, then from the last try)
SETTLE = 20 * 60                    # after the last try, how long its run gets to land before the issue escalates
REMEDY_LIMIT = 10 * 60              # a remedy that hasn't returned by then is left to end on its own (job_status.bounded)
MAILS_PER_DAY = 6                   # escalation mails a day at most (IST day); the rest wait in Needs your attention
# the sweep in the background; the test suite and the browser tests' server turn it off (their fake world must not be re-run under them)
ON = os.environ.get("AUTOFIX", "1").strip().lower() not in ("0", "false", "no", "off")
HISTORY_MAX = 40
HISTORY_DAYS = 7
TEXT_MAX = 300


@dataclass
class Check:
    """One thing that can go wrong. `problem`: what is wrong now, or None. `fix`: the remedy (None: only the owner can fix it, so it
    escalates once the same window as a remedied check has passed, the job's own schedule being the remedy; with `owner_only`, at
    once). `fix_text`: what the remedy does, in the history's words ("re-ran the job"). `action`: what the owner must do
    when it escalates. `to`: the Admin page that shows it."""
    id: str
    name: str
    problem: str | None
    fix: Callable[[], object] | None = None
    fix_text: str = "tried again"
    action: str = "Open Admin to see what failed."
    to: str = "/admin"
    owner_only: bool = False        # only the owner can fix it (a key, a payment, a setting): escalates at once
    tries: int = TRIES
    backoff: tuple = BACKOFF
    settle: float = SETTLE
    extra: dict = field(default_factory=dict)


_sources: list[Callable[[], list[Check]]] = []
_lock = threading.Lock()


def source(fn: Callable[[], list[Check]]) -> Callable[[], list[Check]]:
    """Register a function that lists checks (each call lists them as they are now)."""
    _sources.append(fn)
    return fn


def fingerprint(check_id: str, problem: str) -> str:
    """The issue's identity: the check and its problem with the numbers taken out, so "running for 2 h" and "running for 3 h" are one
    issue and a different failure is a new one."""
    norm = re.sub(r"\d+", "#", problem.lower())
    norm = re.sub(r"\s+", " ", norm).strip()[:200]
    return hashlib.sha1(f"{check_id}|{norm}".encode()).hexdigest()[:16]


def _clean(text: str | None) -> str:
    from .connect.redact import redact_ids
    return redact_ids(re.sub(r"\s+", " ", str(text or "")).strip())[:TEXT_MAX]


def _empty() -> dict:
    return {"open": {}, "history": [], "mail": {"day": None, "sent": 0}}


def load() -> dict:
    try:
        st = db.json_value(db.get_setting(KEY), {})
    except Exception:
        st = {}
    if not st:
        return _empty()
    base = _empty()
    base.update({k: st.get(k, base[k]) for k in base})
    return base


def save(st: dict) -> None:
    try:
        db.set_setting(KEY, json.dumps(st, default=str))
    except Exception as e:                  # the sweep carries on; the next one writes it
        print("autofix: couldn't keep the state:", str(e)[:120])


def _at(now: datetime) -> str:
    return now.astimezone(timezone.utc).isoformat(timespec="seconds")


def _clock(iso: str | None) -> str:
    if not iso:
        return ""
    t = datetime.fromisoformat(iso).astimezone(IST)
    return f"{t.day} {t:%b} {t.hour % 12 or 12}:{t:%M} {'AM' if t.hour < 12 else 'PM'} IST"


def _note(st: dict, now: datetime, check: Check | dict, event: str, text: str) -> None:
    c = check if isinstance(check, dict) else {"id": check.id, "name": check.name, "to": check.to}
    st["history"].insert(0, {"at": _at(now), "id": c["id"], "name": c["name"], "event": event, "text": _clean(text), "to": c.get("to", "/admin")})
    cut = _at(now - timedelta(days=HISTORY_DAYS))
    st["history"] = [h for h in st["history"] if h["at"] >= cut][:HISTORY_MAX]


def _run(check: Check) -> tuple[bool, str]:
    """Run a remedy, bounded: (whether it ran without an error, what happened)."""
    from . import job_status
    try:
        job_status.bounded(check.fix, REMEDY_LIMIT, f"autofix-{check.id}")
        return True, ""
    except Exception as e:                  # the remedy's own failure is part of the story the escalation tells
        return False, _clean(getattr(e, "detail", None) or str(e) or e.__class__.__name__)


def _send(subject: str, text: str) -> bool:
    from . import alerts
    return alerts.tell_admins(subject, text, label="StratLab needs you", url="/admin") > 0


def escalate(st: dict, now: datetime, check: Check, issue: dict, send: Callable[[str, str], bool] = _send) -> bool:
    """Mail the admins once for this issue (none when already mailed for it), within today's cap. Returns whether a mail went."""
    if issue.get("mailed"):
        return False
    day = now.astimezone(IST).date().isoformat()
    mail = st["mail"] if st["mail"].get("day") == day else {"day": day, "sent": 0}
    st["mail"] = mail
    issue["escalated"] = issue.get("escalated") or _at(now)
    if mail["sent"] >= MAILS_PER_DAY:
        issue["held"] = True                # over today's cap: it stays in Needs your attention, mailed tomorrow if still open
        return False
    tried = issue.get("tried") or []
    did = (f"What was tried: {check.fix_text}, {len(tried)} time{'' if len(tried) == 1 else 's'} "
           f"({', '.join(_clock(t['at']) + (' — ' + t['error'] if t.get('error') else '') for t in tried)}), and it is still failing."
           if tried else "Nothing can fix this automatically.")
    subject = f"[StratLab needs you] {check.name}: {_clean(check.problem)}"[:160]
    text = (f"{check.name}: {_clean(check.problem)}\n\n{did}\n\nWhat to do: {check.action}\n\n"
            f"This is the only mail about this issue until it changes. It is also listed under Needs your attention in Admin.")
    try:
        ok = send(subject, text)
    except Exception as e:
        print("autofix: escalation mail failed:", str(e)[:120])
        ok = False
    if ok:
        mail["sent"] += 1
        issue["mailed"] = _at(now)
        issue.pop("held", None)
        _note(st, now, check, "escalated", f"emailed you: {check.action}")
    return ok


def sweep(checks: list[Check], now: datetime | None = None, st: dict | None = None,
          send: Callable[[str, str], bool] = _send, run: Callable[[Check], tuple[bool, str]] = _run, partial: bool = False) -> dict:
    """One pass over the checks (see the module's note). Returns the state, which the caller saves. `partial`: only these checks
    were listed, so the others' issues are left as they are."""
    now = now or datetime.now(timezone.utc)
    st = st if st is not None else load()
    seen = set()
    for c in checks:
        seen.add(c.id)
        issue = st["open"].get(c.id)
        if not c.problem:
            if issue:                       # it went away: by the remedy, or by itself
                by = (f"{c.fix_text} at {_clock(issue['tried'][-1]['at'])}" if issue.get("tried") else "cleared by itself")
                _note(st, now, issue, "fixed", f"{by} — fixed")
                del st["open"][c.id]
            continue
        fp = fingerprint(c.id, c.problem)
        if not issue or issue.get("fp") != fp:
            issue = {"id": c.id, "name": c.name, "to": c.to, "fp": fp, "problem": _clean(c.problem), "since": _at(now), "tried": [],
                     "tries": c.tries, "next": _at(now + timedelta(seconds=c.backoff[0])) if c.fix else None}
            st["open"][c.id] = issue
        issue.update(name=c.name, problem=_clean(c.problem), action=_clean(c.action), to=c.to)
        tried = issue["tried"]
        if c.fix and len(tried) < c.tries:
            if issue.get("next") and _at(now) >= issue["next"]:
                ok, err = run(c)
                tried.append({"at": _at(now), **({"error": err} if not ok else {})})
                _note(st, now, c, "tried", f"{c.fix_text} (try {len(tried)} of {c.tries})" + (f": {err}" if err else ""))
                wait = c.backoff[len(tried)] if len(tried) < c.tries else c.settle
                issue["next"] = _at(now + timedelta(seconds=wait))
            continue
        if c.fix and issue.get("next") and _at(now) < issue["next"]:
            continue                        # the last try's run is still landing
        if not c.fix and not c.owner_only and _at(now) < _at(datetime.fromisoformat(issue["since"]) + timedelta(seconds=sum(c.backoff) + c.settle)):
            continue                        # no remedy of its own: its next scheduled run is given the same time a remedy would get
        escalate(st, now, c, issue, send)
    for gone in [k for k in st["open"] if k not in seen and not partial]:
        # a check no source lists any more (the job was removed, the provider's key taken out): closed without a word
        del st["open"][gone]
    return st


# ---------- a job's own "Run now", called in-process ----------
_app = None
HEAVY_FLAGS = ("full", "universe", "backfill")      # a remedy re-runs the ordinary read, never the whole-history one


def attach(app) -> None:
    global _app
    _app = app


def _coerce(value: str, annotation):
    kind = annotation if isinstance(annotation, str) else getattr(annotation, "__name__", "")
    if kind == "bool":
        return value.lower() in ("1", "true", "yes", "on")
    if kind in ("int", "float"):
        return int(value) if kind == "int" else float(value)
    return value


def call_route(path: str):
    """Run an Admin POST route (a job's Run now, e.g. "/admin/breadth/run?region=US&full=true") as the button would, without its
    whole-history flags. The admin check is the button's; here the caller is the server itself."""
    import asyncio
    import inspect
    from urllib.parse import parse_qsl, urlsplit

    from fastapi import params
    u = urlsplit(path)
    q = {k: v for k, v in parse_qsl(u.query) if k not in HEAVY_FLAGS}
    for r in getattr(_app, "routes", None) or []:
        if getattr(r, "path", None) == u.path and "POST" in (getattr(r, "methods", None) or ()):
            kw = {}
            for name, p in inspect.signature(r.endpoint).parameters.items():
                if isinstance(p.default, params.Depends):
                    kw[name] = None
                elif name in q:
                    kw[name] = _coerce(q[name], p.annotation)
            out = r.endpoint(**kw)
            return asyncio.run(out) if inspect.iscoroutine(out) else out
    raise LookupError(f"No route {u.path}")


def gather() -> list[Check]:
    out: list[Check] = []
    for fn in list(_sources):
        try:
            out += fn() or []
        except Exception as e:              # one broken source must not stop the others
            print("autofix: a check source failed:", str(e)[:160])
    return out


def tick(now: datetime | None = None) -> dict:
    with _lock:
        st = sweep(gather(), now)
        save(st)
        return st


def report(check: Check, send: Callable[[str, str], bool] = _send, now: datetime | None = None) -> dict:
    """For a check that runs on its own schedule and has already retried (the daily feature check): its issue opened or updated now,
    and escalated at once when it is `owner_only` (one mail per issue, within the day's cap), or closed into the history."""
    with _lock:
        st = sweep([check], now, load(), send=send, partial=True)
        save(st)
        return st


def loop():
    if not ON:
        return
    time.sleep(FIRST_WAIT)
    while True:
        try:
            if leader.leading():            # another container leads: it runs the sweep
                tick()
        except Exception as e:              # a bug here must not end the loop
            print("autofix: sweep failed:", str(e)[:160])
        time.sleep(TICK)


def status(st: dict | None = None) -> dict:
    """What Admin shows: the issues being fixed (with the next try), those escalated (with the action), and the history."""
    st = st if st is not None else load()
    trying, escalated = [], []
    for i in st["open"].values():
        row = {"id": i["id"], "name": i["name"], "problem": i.get("problem"), "since": i.get("since"), "to": i.get("to", "/admin"),
               "tries": len(i.get("tried") or []), "of": i.get("tries", TRIES), "next": i.get("next")}
        if i.get("escalated"):
            escalated.append({**row, "action": i.get("action"), "mailed": i.get("mailed"), "held": bool(i.get("held"))})
        else:
            trying.append(row)
    return {"trying": trying, "escalated": escalated, "history": st["history"][:20]}


def annotate(rows: list[dict], st: dict | None = None) -> list[dict]:
    """Admin's job rows with what the self-healing is doing about them: a job being retried is a Check that says so (try 2 of 3, the
    next at …), one whose tries are used up a Problem that says the owner was emailed."""
    st = st if st is not None else load()
    out = []
    for r in rows:
        i = st["open"].get(f"job:{r['id']}")
        if i and r.get("error"):
            if i.get("escalated"):
                r = {**r, "state": "bad", "error": f"{r['error']} Retried automatically {len(i.get('tried') or [])} times without luck"
                                                  f"{'; you were emailed' if i.get('mailed') else ''}."}
            else:
                n = len(i.get("tried") or [])
                when = _clock(i.get("next"))
                if not n and not i.get("next"):     # no remedy of its own: its next scheduled run is the retry
                    text = " It is read again at its next run by itself; nothing to do unless it is still failing in a few hours (you'd be emailed)."
                else:
                    text = (" Being fixed automatically: " + (f"tried {n} of {i.get('tries', TRIES)} times; " if n else "")
                            + (f"next try {when}." if n < i.get("tries", TRIES) and when else "the last try's run is landing."))
                r = {**r, "state": "warn", "error": r["error"] + text}
        out.append(r)
    return out
