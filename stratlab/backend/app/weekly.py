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
    lines = [f"StratLab, {since:%d %b} to {now:%d %b %Y}", "",
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
        names = sorted({n for c in failed_runs for n in c.get("failed") or []})
        lines.append(f"- {_n(len(checks), 'run')}, {len(failed_runs)} with failures: {', '.join(names[:8]) or 'see Admin'}")
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
    listed = facts.get("errors_listed")
    # the same count Admin → System shows beside it, so the two never seem to disagree (R6V-010)
    lines += ["", "Server errors", f"- {_n(facts['errors'], 'error')} this week"
              + (f" ({listed} listed on Admin → System since the last restart)" if listed is not None and listed != facts["errors"] else "")]
    if facts.get("admin_url"):
        lines += ["", f"Admin page: {facts['admin_url']}"]

    trouble = len(failed_runs) + sum(len(a.get("issues") or []) for a in facts["audits"].values()) + facts["errors"]
    subject = f"StratLab weekly: {_n(st['new'], 'new user')}, " + ("all quiet" if not trouble else f"{_n(trouble, 'thing')} to look at")
    return subject, "\n".join(lines)
