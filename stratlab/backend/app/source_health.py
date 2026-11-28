"""Each outside source's last good answer and last failure, for Admin's "Data sources" card (admin100, 27 Nov 2026).

The owner reported "errors in Admin" twice while the exchange's archive turned this server away on one host (fix98): nothing in Admin
said which source failed, since when, or that another host was serving the same files. Every read of an outside source now notes how it
went here (record), and Admin shows one row a source with the truth and a plain verdict (rows):

  - a good answer after a failure clears the row at once: a source is never shown broken after its next good read;
  - one failed read, or a short run of them, is a source not answering for a moment: "Retrying", not a warning (it is asked again by
    itself, and pages use their last good copy meanwhile);
  - a source that keeps failing (FAILS_LASTING reads in a row over LASTING_AFTER) is a Check, and one with no good answer for a day a
    Problem, said with what it holds up and that nothing in Admin fixes it, unless it is one only the owner can fix (the email service, the
    payment keys), which then says exactly what to do and goes to Needs your attention;
  - a file served by another host after the first refused (the archive's mirrors) is OK, with a note naming both hosts.

Small and bounded: one entry per source (MAX_KEYS), kept in memory and written to one database setting at most every PERSIST_EVERY seconds
(or at once when a source turns from good to failing or back, at most every FLIP_EVERY), so a restart still shows the last known state.
Recording never raises and never slows a read: it is a few dictionary writes."""
from __future__ import annotations

import json
import re
import threading
import time
from datetime import datetime, timedelta, timezone

KEY = "sourcehealth"
MAX_KEYS = 24
PERSIST_EVERY = 300           # seconds between writes of the whole table while nothing flips
FLIP_EVERY = 30               # seconds between writes caused by a source turning good or bad
FAILS_LASTING = 3             # failed reads in a row...
LASTING_AFTER = 30 * 60       # ...over at least this long: a Check, not a passing blip
DOWN_AFTER = 24 * 3600        # no good answer for this long: a Problem (data is a day old)
OWNER_FAILS = 2               # an owner-fixed source (mail, payments): failing this many times in a row is the owner's to look at
NOTE_FOR = 24 * 3600          # a fallback or a passing failure is mentioned on a good row for this long
IST = timezone(timedelta(hours=5, minutes=30))

# key: (label, what it feeds, whether only the owner can fix it, Admin page)
KNOWN: dict[str, tuple[str, str, bool, str]] = {
    # the day's login itself is the Broker data light's (Services), with the owner's step when it is needed; this row is its reads
    "broker": ("Zerodha (broker data)", "Indian prices, candles and the option chains", False, "/admin/data"),
    "nse-archive": ("Exchange file archive (NSE)", "the list of companies, official closes, F&O, ban, lot-size, participant and lending files",
                    False, "/admin/data"),
    "nse-feed": ("Exchange announcements (NSE)", "company filings, insider trades and deals", False, "/admin/data"),
    "bse": ("BSE", "the filings of companies listed only on BSE", False, "/admin/data"),
    "sec": ("The SEC (EDGAR)", "US company figures and filings", False, "/admin/data"),
    "mail": ("Email service", "alert emails, newsletters and sign-in links", True, "/admin/system"),
    "payments": ("Razorpay", "subscriptions and payment events", True, "/admin/money"),
}
# a research source's own name (intel.net.Source.name) -> its key here
NAMES = {"The SEC": "sec"}

_st: dict[str, dict] = {}
_lock = threading.Lock()
_wrote = {"at": 0.0}
_loaded = {"done": False}


def key_of(name: str) -> str:
    """A source's key: a known one, else its name made into a key ("Yahoo Finance" -> "src:yahoo-finance")."""
    if name in KNOWN:
        return name
    if name in NAMES:
        return NAMES[name]
    return "src:" + re.sub(r"[^a-z0-9]+", "-", str(name).lower()).strip("-")[:40]


def _clean(text) -> str | None:
    if not text:
        return None
    try:
        from .connect.redact import redact_ids
        text = redact_ids(str(text))
    except Exception:
        text = str(text)
    text = re.sub(r"https?://\S+", lambda m: re.sub(r"[?#].*$", "", m.group(0)), text)     # no query strings (keys, tokens)
    return re.sub(r"\s+", " ", text).strip()[:200]


def record(name: str, ok: bool, error: str | None = None, via: str | None = None, refused: str | None = None,
           label: str | None = None, now: float | None = None) -> None:
    """How one read of `name` went. `via`: the host that served it when it wasn't the first asked (a mirror); `refused`: what the first
    host said then ("nsearchives.nseindia.com refused (403)"). `label`: a display name for a source not in KNOWN. Never raises."""
    try:
        k = key_of(name)
        t = time.time() if now is None else now
        with _lock:
            row = _st.get(k)
            if row is None:
                if len(_st) >= MAX_KEYS:
                    return
                row = _st[k] = {"label": label or (KNOWN[k][0] if k in KNOWN else str(name))[:60]}
            was_failing = bool(row.get("fails"))
            if ok:
                row.update(ok_at=t, fails=0, since=None)
                if via:
                    row.update(via=via, via_at=t, refused=_clean(refused))
                elif row.get("via_at") and t - row["via_at"] > NOTE_FOR:
                    row.pop("via", None)
            else:
                row.update(fail_at=t, error=_clean(error) or "no answer", fails=int(row.get("fails") or 0) + 1)
                row["since"] = row.get("since") or t
            flipped = was_failing != bool(row.get("fails"))
            due = t - _wrote["at"] >= (FLIP_EVERY if flipped else PERSIST_EVERY)
            if due:
                _wrote["at"] = t
                snapshot = json.dumps(_st)
        if due:
            _persist(snapshot)
    except Exception as e:                      # a note about a read must never break the read
        print("source health:", str(e)[:120])


def _persist(text: str) -> None:
    try:
        from . import db
        db.set_setting(KEY, text)
    except Exception as e:
        print("source health: couldn't keep it:", str(e)[:120])


def _load() -> None:
    """The table kept before this server started, merged under what this server has seen (once)."""
    if _loaded["done"]:
        return
    _loaded["done"] = True
    try:
        from . import db
        saved = db.json_value(db.get_setting(KEY), {}) or {}
    except Exception:
        saved = {}
    if not isinstance(saved, dict):
        return
    with _lock:
        for k, old in list(saved.items())[:MAX_KEYS]:
            if not isinstance(old, dict):
                continue
            now = _st.get(k)
            if now is None:
                if len(_st) < MAX_KEYS:
                    _st[k] = {**old, "before_restart": True}
                continue
            # this server's own reads win; a time this server hasn't seen yet comes from before the restart
            for at in ("ok_at", "fail_at"):
                if old.get(at) and not now.get(at):
                    now[at] = old[at]
                    if at == "fail_at" and not now.get("error"):
                        now["error"] = old.get("error")


def reset() -> None:
    """Forget everything (tests)."""
    with _lock:
        _st.clear()
        _wrote["at"] = 0.0
        _loaded["done"] = True


def _when(t: float | None) -> str | None:
    return datetime.fromtimestamp(t, timezone.utc).isoformat(timespec="seconds") if t else None


def _clock(t: float) -> str:
    d = datetime.fromtimestamp(t, IST)
    return f"{d.day} {d:%b}, {d.hour % 12 or 12}:{d:%M} {'AM' if d.hour < 12 else 'PM'} IST"


def _span(seconds: float) -> str:
    m = int(seconds // 60)
    if m < 60:
        return f"{max(m, 1)} min"
    h = m // 60
    return f"{h} h" if h < 48 else f"{h // 24} days"


def _bare(error: str | None) -> str:
    """An error as a clause inside a sentence: no full stop of its own."""
    return (error or "no answer").rstrip(". ") or "no answer"


def owner_action(k: str, error: str | None) -> str:
    """What the owner does about an owner-fixed source that keeps failing, by what it said."""
    e = (error or "").lower()
    if k == "mail":
        if "ip address" in e or "authorized ip" in e:
            return ("In Brevo, open your name (top right) → Security → Authorized IPs and turn IP blocking off, then press Send a test email "
                    "in Admin → System.")
        if re.search(r"\b(401|403)\b|unauthori|invalid|key", e):
            return "The email service turned the server's key down: put a working key in Railway → Variables, then press Send a test email in Admin → System."
        return "Press Send a test email in Admin → System: if it fails too, the error there says what to change in the email service."
    if k == "payments":
        if re.search(r"\b(401|403)\b|authentication|unauthori|invalid|key", e):
            return "Razorpay turned the server's keys down: check RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET in Railway, then press Check payments setup in Admin → Money."
        return "Press Check payments setup in Admin → Money: it says what Razorpay answers."
    return "Open Admin to see what failed."


def judge(k: str, row: dict, now: float | None = None) -> dict:
    """One source's row: its light (ok, warn, bad), a word, the line that says what is true, and whether the owner must act."""
    now = time.time() if now is None else now
    label, what, owner_fix, to = KNOWN.get(k, (row.get("label") or k, "", False, "/admin/data"))
    ok_at, fail_at = row.get("ok_at"), row.get("fail_at")
    fails = int(row.get("fails") or 0)
    base = {"key": k, "label": label, "what": what, "to": to, "last_ok": _when(ok_at), "last_fail": _when(fail_at),
            "error": row.get("error") if fail_at else None, "fails": fails, "before_restart": bool(row.get("before_restart")),
            "owner": False, "action": None}
    if not ok_at and not fail_at:
        idle = {"mail": "No email sent since the server started.",
                "payments": "Not read since the server started: Money's lists, the setup check and Razorpay's payment events read it."}
        return {**base, "state": "ok", "word": "Not asked yet", "detail": idle.get(k, "Not asked since the server started; it is read when a page or job needs it.")}
    failing = bool(fail_at) and (not ok_at or fail_at > ok_at) and fails > 0
    if not failing:
        notes = []
        if row.get("via") and row.get("via_at") and now - row["via_at"] <= NOTE_FOR:
            notes.append(f"Served by {row['via']}" + (f" after {row['refused']}" if row.get("refused") else " after the first host refused")
                         + ": the same files come from the other host, so nothing to do.")
        if fail_at and now - fail_at <= NOTE_FOR:
            notes.append(f"A read failed at {_clock(fail_at)} ({_bare(row.get('error'))}); the next one worked.")
        return {**base, "state": "ok", "word": "OK",
                "detail": " ".join([f"Last good answer {_span(now - ok_at)} ago ({_clock(ok_at)})."] + notes)}
    since = row.get("since") or fail_at
    good = f" Last good answer {_span(now - ok_at)} ago ({_clock(ok_at)})." if ok_at else " No good answer on record."
    why = _bare(row.get("error"))
    if owner_fix:
        if fails >= OWNER_FAILS:
            action = owner_action(k, why)
            return {**base, "state": "bad", "word": "Fix", "owner": True, "action": action,
                    "detail": f"Failing since {_clock(since)}, {fails} tries in a row: {why}.{good} {action}"}
        return {**base, "state": "ok", "word": "Retrying",
                "detail": f"One try failed at {_clock(fail_at)}: {why}. The next one is tried by itself; you are told here if it fails again.{good}"}
    down_for = now - (ok_at or since)
    if down_for >= DOWN_AFTER:
        return {**base, "state": "bad", "word": "Down",
                "detail": f"No good answer for {_span(down_for)}: {why} ({fails} tries in a row).{good} Pages that need it show their last good copy. "
                          "This is the source's side (it turns the server away or doesn't answer); nothing in Admin fixes it, and StratLab keeps asking."}
    if fails >= FAILS_LASTING and now - since >= LASTING_AFTER:
        return {**base, "state": "warn", "word": "Not answering",
                "detail": f"Not answering since {_clock(since)}: {why} ({fails} tries in a row).{good} StratLab keeps asking and uses its last good copy "
                          "meanwhile; nothing for you to do."}
    return {**base, "state": "ok", "word": "Retrying",
            "detail": f"Didn't answer at {_clock(fail_at)}: {why}. Asked again by itself; nothing to do.{good}"}


def rows(now: float | None = None) -> list[dict]:
    """Every source's row: the known ones first, in their order (asked or not), then the others StratLab read, by name."""
    _load()
    with _lock:
        st = {k: dict(v) for k, v in _st.items()}
    order = list(KNOWN) + sorted((k for k in st if k not in KNOWN), key=lambda k: str(st[k].get("label") or k).lower())
    return [judge(k, st.get(k, {}), now) for k in order]


def watch(name: str, fn, label: str | None = None):
    """fn() (one call to a source), noted here by how it ended: an answer (even "nothing for that") is good; the source not answering,
    refusing or sending a page instead of data is a failure. StratLab's own rate limit or breaker is not the source's doing: not noted."""
    from .intel.net import SourceError
    try:
        out = fn()
    except SourceError as e:
        text = str(e)
        if e.busy and not re.search(r"our rate limit|isn't answering right now", text):
            record(name, False, text, label=label)
        elif not e.busy:
            record(name, True, label=label)
        raise
    except Exception as e:
        record(name, False, f"{e.__class__.__name__}: {str(e)[:120]}", label=label)
        raise
    record(name, True, label=label)
    return out
