"""The owner's Monday email: the last seven days in a few lines. Only formatting here; main.py gathers the facts."""
from datetime import datetime, timedelta

from .plans import PLANS

SEND_AT = (0, 9, 0)                 # Monday, 9:00 IST
WEEK_KEY = "weekly-summary-week"


def week_of(now: datetime) -> str:
    """The ISO week a time falls in, like 2026-W40: one summary per week."""
    y, w, _ = now.isocalendar()
    return f"{y}-W{w:02d}"


def due(now: datetime) -> bool:
    """Monday from 9:00 on: the summary goes out then (or as soon as the server is back, if it was down at 9)."""
    return now.weekday() == SEND_AT[0] and (now.hour, now.minute) >= SEND_AT[1:]


def next_send(now: datetime) -> datetime:
    at = now.replace(hour=SEND_AT[1], minute=SEND_AT[2], second=0, microsecond=0) + timedelta(days=(SEND_AT[0] - now.weekday()) % 7)
    return at if at > now else at + timedelta(days=7)


def _n(k: int, word: str, plural: str = "") -> str:
    return f"{k} {word if k == 1 else plural or word + 's'}"


def _when(at, now: datetime) -> str:
    """" (Mon 12 Oct, 09:30)" for a run's time, in the summary's own zone; empty when the run has none."""
    try:
        t = datetime.fromisoformat(str(at).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return ""
    if t.tzinfo and now.tzinfo:
        t = t.astimezone(now.tzinfo)
    return f" ({t:%a} {t.day} {t:%b}, {t:%H:%M})"


def summary(now: datetime, facts: dict) -> tuple[str, str]:
    """(subject, text) from the week's facts: users, checks, audits, errors and the admin link."""
    since = now - timedelta(days=7)
    st = facts["stats"]
    words = lambda counts: ", ".join(f"{PLANS[p]['name']} {k}" for p, k in (counts or {}).items() if k) or "none"   # noqa: E731
    if "paying" in st:
        # paying (a subscription) apart from a plan the owner gave by hand, as Admin → Overview tells them apart (R6V-010)
        plan_lines = [f"- Paying: {words(st['paying'])}", f"- Given by the owner, not paying: {words(st.get('given'))}"]
    else:
        plan_lines = [f"- Paid: {words(st['paid'])}"]
    lines = [f"StratLab, {since.day} {since:%b} to {now.day} {now:%b %Y}", "",
             "Users",
             f"- {st['new']} new this week, {st['users']} in all",
             *plan_lines,
             # counted from the same seven days as the line above (usage events since `since`), never the month's (R7M-006)
             f"- {_n(st['experiments'], 'experiment')} run, {_n(st['ai'], 'AI build')} in the last 7 days", ""]

    checks = facts["checks"]
    failed_runs = [c for c in checks if c.get("fail")]
    lines.append("Daily checks")
    if not checks:
        lines.append("- None ran this week")
    elif not failed_runs:
        lines.append(f"- {_n(len(checks), 'run')}, all passed")
    else:
        # each failed run once, when it ran and the checks that failed in it: the list is as long as the count (R23-003:
        # "9 runs, 5 with failures" listed per-check counts adding up to 8)
        runs = [f"{', '.join(c.get('failed') or []) or 'see Admin'}{_when(c.get('at'), now)}" for c in failed_runs]
        lines.append(f"- {_n(len(checks), 'run')}, {len(failed_runs)} with failures: {'; '.join(runs)}")
        lines.append("- Counted: every run of the daily checks in these 7 days, automatic and Run now. Each failed run is "
                     "listed once, with the checks that failed in it.")
    lines.append("")

    lines.append("New listings (whole-market audit)")
    for market, a in facts["audits"].items():
        if not a.get("enabled"):
            lines.append(f"- {market}: audit is off")
            continue
        line = f"- {market}: {a['checked']} checked this week"
        if a["issues"]:
            bad = "; ".join(f"{i['symbol']} ({', '.join(_n(k, w, pl) for w, k, pl in (('mismatch', i['mismatches'], 'mismatches'), ('error', i['errors'], '')) if k)})"
                            for i in a["issues"][:6])
            line += f", {len(a['issues'])} with problems: {bad}"
        else:
            line += ", no mismatches or errors"
        lines.append(line)
    # each error once (R23-003: "4 this week; 23 more from before the restart" counted the 4 twice): the week's errors,
    # split by the last restart when the split is known
    since_restart, before = facts.get("errors_week_since_restart"), facts.get("errors_week_before_restart")
    split = (f" ({since_restart} since the last restart, {before} before it)"
             if facts["errors"] and since_restart is not None and before is not None else "")
    lines += ["", "Server errors", f"- {_n(facts['errors'], 'server error')} this week{split}"]
    if facts.get("admin_url"):
        lines += ["", f"Admin page: {facts['admin_url']}"]

    listings = sum(len(a.get("issues") or []) for a in facts["audits"].values())
    trouble = [x for x in ((f"{_n(len(failed_runs), 'run')} with failures" if failed_runs else ""),
                           (f"{_n(listings, 'listing')} with problems" if listings else ""),
                           (_n(facts["errors"], "server error") if facts["errors"] else "")) if x]
    subject = f"StratLab weekly: {_n(st['new'], 'new user')}, " + (", ".join(trouble) or "all quiet")
    return subject, "\n".join(lines)
