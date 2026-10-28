"""Lifecycle emails: a welcome, a nudge to test a first strategy, trial and launch-offer reminders, a what's-new note
after two quiet weeks, and payment receipts.

- Each email goes to a user at most once, remembered in app_settings as lifecycle:<uid> ({email key: when sent})
  before it is sent; a send that fails is forgotten again, so the next sweep tries once more (a tip, up to TIP_TRIES
  attempts, counted in the same record as "tries:<email key>"). A receipt, plan change or invite reward that fails is
  also kept in lifecyclepending:<uid> and retried by the sweep (4 tries within a day).
- Everything but receipts and plan changes is a "tips and reminders" email: people turn those off in Account or from
  the link in each one, and get at most one a day. Receipts and plan changes are about the account and always go.
- The welcome goes from the first visit after signing up. The rest go from an hourly sweep in India's daytime
  (Job below, modelled on the newsletters' job), so nobody is emailed at 3 am.
Like the newsletters, these state facts about the account and the app: never what to trade."""
import json
import threading
import time
from datetime import date, datetime, timedelta, timezone

from . import alerts, db, leader
from . import email_kit as kit
from .plans import IST, PLANS, _dt, access_plan, effective_plan, free_basic_until, promo_active, promo_until, trial_end

SENT = "lifecycle:"              # lifecycle:<uid>: {"welcome": "2026-10-03T10:00:00+00:00", "receipt:pay_1": ...}
PREFS = "emailprefs:"            # emailprefs:<uid>: {"tips": false} once turned off
SEEN = "lastseen:"               # lastseen:<uid>: the India date of their last visit
PENDING = "lifecyclepending:"    # lifecyclepending:<uid>: {email key: {kind, ctx, tries, first}} for account emails that failed
MARK = "lifecyclejob:last"       # the hour the sweep last ran
CATEGORY = "tips"                # the unsubscribe link's category
EVER = "2000-01-01T00:00:00+00:00"

WELCOME_WINDOW = timedelta(days=2)                       # only brand-new accounts are welcomed
DAY2_WINDOW = (timedelta(days=1), timedelta(days=7))     # the nudge goes on day 2, or soon after if the sweep missed it
INACTIVE_DAYS = 14
INACTIVE_UNTIL = 30                                      # quiet for longer than this and the "what's new" note is no longer sent
TIP_TRIES = 3                                            # attempts at one tips email before it is given up
RETRIES = 4                                              # account emails: tries before giving up, within a day
RETRY_WINDOW = timedelta(hours=26)
GAP = timedelta(hours=20)                                # at most one tips email a day
HOURS = (8, 21)                                          # India time: the sweep runs from 8 am to 9 pm

# kind: (name for Admin, transactional)
EMAILS = {
    "welcome": ("Welcome, right after signing up", False),
    "day2": ("Day 2: test your first strategy", False),
    "trial_before": ("Paper-trading trial ends tomorrow", False),
    "trial_end": ("Paper-trading trial ends today", False),
    "promo_before": ("Launch offer ends tomorrow", False),
    "promo_end": ("Launch offer ends today", False),
    "inactive": ("What's new, after 14 quiet days", False),
    "receipt": ("Payment receipt", True),
    "plan_ended": ("Plan changed to Free", True),
    "invite_reward": ("Invite reward: free Basic time", True),
}
ORDER = ("trial_end", "promo_end", "trial_before", "promo_before", "welcome", "day2", "inactive")   # most urgent first

# the inactive email's "what's new": (title, one line, where in the app)
WHATS_NEW = [
    ("Newsletters", "A Market Brief for India and the US after each close, and My Stocks: what changed for the "
                    "companies you follow.", "/news"),
    ("Company deep dive", "Growth, margins, capex and cash flow from the reported numbers, with a read of the company's "
                          "own presentations and calls.", "/research"),
    ("Filings and red flags", "Fund raises, pledges, resignations and defaults your watchlist companies reported to "
                              "the exchange.", "/research/filings"),
    ("Sector rotation", "Which sectors moved between quadrants on the rotation chart, down to each sector's stocks.",
     "/research/rotation"),
    ("Companies listed only on BSE", "Search, charts, backtests and paper trading take them by BSE symbol or code.",
     "/research"),
]

BACKGROUND = True                # tests turn this off to send in the calling thread


def _now(now: datetime | None) -> datetime:
    return now or datetime.now(timezone.utc)


def later(fn, *args):
    """Run a send off the request (a payment webhook shouldn't wait on the mail service)."""
    def run():
        try:
            fn(*args)
        except Exception as e:
            print("lifecycle email failed:", str(e)[:160])
    if BACKGROUND:
        threading.Thread(target=run, daemon=True, name="lifecycle-email").start()
    else:
        run()


# ---------- preferences and records ----------
def tips_on(uid: str) -> bool:
    """Tips and reminders are on unless the user turned them off."""
    try:
        return db.json_value(db.get_setting(PREFS + uid), {}).get("tips") is not False
    except Exception:
        return True


def set_tips(uid: str, on: bool) -> dict:
    db.set_setting(PREFS + uid, json.dumps({"uid": uid, "tips": bool(on)}))
    return {"tips": bool(on)}


def sent(uid: str) -> dict:
    """{email key: when it was sent} for one user."""
    return db.json_value(db.get_setting(SENT + uid), {})


def _capped(record: dict, key: str) -> bool:
    """A tips email whose attempts were all used up."""
    t = record.get("tries:" + key)
    try:
        return int(t["n"]) >= TIP_TRIES
    except (KeyError, TypeError, ValueError):
        return False


def _claim(uid: str, key: str, now: datetime, capped: bool = False) -> bool:
    """Record the email as sent, unless it already was (or, for `capped`, its attempts are used up). True when this
    caller should send it."""
    won = []

    def mark(raw):
        have = db.json_value(raw, {})
        won.clear()
        if key in have or (capped and _capped(have, key)):
            return None
        won.append(1)
        return json.dumps({**have, key: now.isoformat()})
    db.update_setting(SENT + uid, mark)           # atomic, so two containers can't both claim it
    return bool(won)


def _release(uid: str, key: str, tried: datetime | None = None):
    """Forget the claim after a failed send; with `tried`, count the attempt (see TIP_TRIES)."""
    def drop(raw):
        have = db.json_value(raw, {})
        have.pop(key, None)
        if tried:
            n = have.get("tries:" + key)
            have["tries:" + key] = {"n": (int(n["n"]) if isinstance(n, dict) and str(n.get("n")).isdigit() else 0) + 1, "at": tried.isoformat()}
        return json.dumps(have)
    db.update_setting(SENT + uid, drop)


def _pend(uid: str, key: str, kind: str, ctx: dict | None, now: datetime):
    """Keep a failed account email for the sweep to retry."""
    def add(raw):
        have = db.json_value(raw, {})
        old = have.get(key) or {}
        have[key] = {"kind": kind, "ctx": old.get("ctx") or ctx or {}, "tries": int(old.get("tries") or 0) + 1,
                     "first": old.get("first") or now.isoformat()}
        return json.dumps(have, default=lambda o: o.isoformat())
    db.update_setting(PENDING + uid, add)


def _unpend(uid: str, key: str):
    def drop(raw):
        have = db.json_value(raw, {})
        return json.dumps(have) if have.pop(key, None) is not None else None
    db.update_setting(PENDING + uid, drop)


def address(profile: dict) -> str | None:
    """Account emails go to the address the user signs in with."""
    return (profile.get("email") or "").strip() or None


# ---------- the emails ----------
def _day(d: date) -> str:
    """A day in the app's format: Fri, 9 Oct 2026."""
    return kit.fmt_date(d, weekday=True)


def _last_day(end: datetime) -> date:
    """The India date of the last moment before `end` (an offer ending at midnight ends the day before). Taken to the
    minute, as every page and email says the time: 00:00:30 is said "12:00 am", so it too ends the day before."""
    return (end.replace(second=0, microsecond=0) - timedelta(seconds=1)).astimezone(IST).date()


def _end_text(end: datetime) -> str:
    """An instant in India time, as the pages say it: on Thu 22 Oct at 5:20 pm IST. Midnight is the end of the day
    before, not 12:00 am of the next one: at the end of Thu 22 Oct (India time)."""
    t = end.astimezone(IST).replace(second=0, microsecond=0)      # said to the minute, as the pages do
    if (t.hour, t.minute) == (0, 0):
        d = _last_day(t)
        return f"at the end of {d:%a} {d.day} {d:%b} (India time)"
    return f"on {t:%a} {t.day} {t:%b} at {t.hour % 12 or 12}:{t:%M} {'am' if t.hour < 12 else 'pm'} IST"


def _url(path: str) -> str:
    return kit.site(path)


def _compose(subject: str, paras: list[str], cta: tuple[str, str] | None = None, items: list | None = None,
             transactional: bool = False, label: str = "Your account", tiles: list | None = None,
             extra: list | None = None) -> tuple[str, str, str]:
    """(subject, html, text) in the shared email kit. The first paragraph is the one-line summary under the title.
    Tips carry the {unsubscribe_url} placeholder; account emails say why they can't be turned off."""
    blocks = [kit.tiles(tiles)] if tiles else []
    blocks += [kit.para(p) for p in paras[1:]]
    if items:
        blocks.append(kit.bullets([(title, line, _url(path) if path else None) for title, line, path in items]))
    if transactional:
        footer = kit.Footer(why="You get this because you have a StratLab account.",
                            transactional="It is about your account, so it is sent even with tips and reminders turned off.",
                            manage=kit.MANAGE_TIPS)
    else:
        footer = kit.Footer(why="You get tips and reminders because you have a StratLab account.",
                            unsubscribe="Turn off tips and reminders", manage=kit.MANAGE_TIPS)
    html, text = kit.render(subject, blocks + list(extra or []), footer, label=label, date=kit.today_label(),
                            summary=paras[0] if paras else None, cta=cta, subject=subject)
    return subject, html, text


def own_plan(profile: dict) -> str:
    """The plan the account has apart from the launch offer: what it pays for or was given, the site owner's Pro, or
    Basic while free Basic time from invites lasts (access_plan without the offer)."""
    try:
        from .admin import recorded_owner
        if recorded_owner(profile):
            return "pro"
    except Exception:
        pass
    plan = effective_plan(profile)
    if plan == "free":
        try:
            if free_basic_until(profile):
                return "basic"
        except Exception:
            pass
    return plan


def brief_line(profile: dict) -> str:
    """What the Market Brief is for this account (R23-005: the welcome promised "after each market closes" to Free
    accounts, which get the weekly edition): daily on Basic and up; on Free, the Saturday digest, with the daily one
    while the launch offer gives everyone Pro, said with the offer's end as the pages say it."""
    from .plans import allows
    if allows(own_plan(profile), "newsletter"):
        return "a short email after each market closes."
    end = promo_until()
    if promo_active() and end:
        return (f"a short email after each market closes during the launch offer, which ends {_end_text(end)}; "
                "then a weekly email on Saturday morning on the Free plan.")
    return "a weekly email on Saturday morning on the Free plan. The daily one, after each market closes, comes with Basic and up."


def build(kind: str, profile: dict, ctx: dict | None = None) -> tuple[str, str, str]:
    """(subject, html, text) for one email. `ctx` carries what the email is about: the trial's or offer's end, the
    invoice for a receipt, the plan that ended."""
    if kind not in EMAILS:
        raise ValueError(f"Unknown email: {kind}")
    ctx = ctx or {}
    tx = EMAILS[kind][1]
    if kind == "welcome":
        return _compose("Welcome to StratLab", [
            "StratLab tests trading ideas on years of real prices, after real costs, and lays out the facts on Indian and "
            "US companies. Here is where to start:"], ("Open StratLab", "/"), [
            ("Test an idea", "describe it in plain words, or start from a ready-made one.", "/new"),
            ("Look into a company", "the numbers, its filings and the business in its own words.", "/research"),
            ("Trade it on paper", "run a strategy live with pretend money.", "/paper"),
            ("Get the Market Brief", brief_line(profile), "/settings#newsletters")], label="Welcome")
    if kind == "day2":
        return _compose("Test your first strategy in two minutes", [
            "You haven't run a backtest yet. Start from a ready-made idea, such as a moving-average crossover, or "
            "describe your own in plain words.",
            "You'll see how it did on years of real prices, after costs, with four checks for luck."],
            ("Test an idea", "/new"), label="Getting started")
    if kind in ("trial_before", "trial_end"):
        last = ctx.get("last_day") or date.today()
        when = "tomorrow" if kind == "trial_before" else "today"
        return _compose(f"Your paper-trading trial ends {when}", [
            f"Your free paper trading runs until the end of {_day(last)} (India time).",
            "After that, the Basic or Pro plan keeps paper trading going. Your notebooks and backtests stay either way."],
            ("See plans", "/plans"), label="Your trial")
    if kind in ("promo_before", "promo_end"):
        when = "tomorrow" if kind == "promo_before" else "today"
        end = ctx.get("end") or datetime.now(timezone.utc)
        return _compose(f"The launch offer ends {when}", [
            f"Every Pro feature has been free for everyone during the launch offer. It ends {_end_text(end)}.",
            "After that, the Free plan's limits apply again unless you choose a plan. Your notebooks, backtests and "
            "watchlist stay either way."], ("See plans", "/plans"), label="Launch offer")
    if kind == "inactive":
        return _compose("What's new in StratLab", ["It's been a couple of weeks. Here is what's new:"],
                        ("Open StratLab", "/"), WHATS_NEW, label="What's new")
    if kind == "receipt":
        inv = ctx.get("invoice") or {}
        plan = PLANS.get(ctx.get("plan") or "pro", PLANS["pro"])["name"]
        period = "yearly" if ctx.get("period") == "year" else "monthly"
        total = inv.get("total")
        cur = inv.get("currency") or "INR"
        amount = kit.money(total, cur, 2) if isinstance(total, (int, float)) else "See the invoice"
        return _compose(f"Receipt: StratLab {plan} plan", [
            f"Thanks for your payment. You're on the {plan} plan, billed {period}.",
            f"Invoice number {inv.get('number') or ''}. It is saved in Account, where you can print it or save it as a PDF."], ("See your invoices", "/account"),
            transactional=tx, label="Receipt", extra=receipt_blocks(inv),
            tiles=[kit.Tile("Amount paid", amount), kit.Tile("Date", kit.fmt_date(inv["date"]) if inv.get("date") else "–")])
    if kind == "plan_ended":
        plan = PLANS.get(ctx.get("plan") or "pro", PLANS["pro"])["name"]
        now_plan = ctx.get("access") or access_plan(profile)
        if now_plan == "free":
            return _compose("Your StratLab plan has changed to Free", [
                f"Your {plan} subscription has stopped, so your account is on the Free plan now.",
                "Your notebooks, backtests and watchlist stay. You can choose a plan again any time."],
                ("See plans", "/plans"), transactional=tx, label="Your plan")
        end = promo_until()
        now_has = (f"Every Pro feature is free for everyone during the launch offer, which ends {_end_text(end)}."
                   if promo_active() and end else f"Your account is on the {PLANS[now_plan]['name']} plan now.")
        return _compose("Your StratLab subscription has stopped", [
            f"Your {plan} subscription has stopped.", now_has,
            "Your notebooks, backtests and watchlist stay. You can choose a plan again any time."],
            ("See plans", "/plans"), transactional=tx, label="Your plan")
    if kind == "invite_reward":
        how = ctx.get("kind")
        if ctx.get("role") == "newcomer":
            first = ("You joined StratLab through a friend's invite and used it on 3 different days in your first 2 "
                     "weeks, so you get a free month of the Basic plan.")
        elif how == "payment":
            first = "A friend you invited has subscribed to StratLab, so you get a free month of the Basic plan."
        elif how == "extra":
            first = (f"A friend you invited has subscribed to StratLab, so you get {ctx.get('days') or 8} extra days "
                     "of the Basic plan.")
        else:
            first = ("A friend you invited is now using StratLab, so you and your friend each get a free month of the "
                     "Basic plan.")
        # the rules and Basic's limits as two short cards, not two walls of text (LIVE1C-036: a 71-word paragraph)
        rules = kit.card("How it works", [
            kit.Row("Your friend", sub="Joins with your link, uses StratLab on 3 different days in their first 2 weeks, and gets a month of Basic free."),
            kit.Row("You", sub="Get a free month for each of your first 2 friends who do this each year, and for each of your first 2 friends who subscribe."),
            kit.Row("After that", sub="Every friend who subscribes adds 8 days, up to 8 times in a year.")])
        b = PLANS["basic"]
        includes = kit.card("Basic includes", [
            kit.Row("Backtests", value=f"{b['backtests_per_month']} a month"), kit.Row("AI strategy builds", value=f"{b['ai_builds_per_month']} a month"),
            kit.Row("Paper trading", value=f"{b['live_limit']} sessions at a time"), kit.Row("Company deep dives", value=f"{b['deepdives_per_month']} a month"),
            kit.Row("Decks", value=f"{b['decks_per_month']} a month")], foot="Every indicator, trade notifications and the daily newsletters too.")
        until = ctx.get("until")
        if ctx.get("banked") and not until:
            when = ("You're on a paid plan, so the free time is kept for you: it starts if your account moves to the "
                    "Free plan.")
        elif isinstance(until, datetime):
            when = f"Your free Basic runs until {_day(_last_day(until))} (India time)."
            if ctx.get("banked"):
                when += " More free time is kept for you in case your paid plan stops."
        else:
            when = "Your free Basic has started."
        title = (f"You've got {ctx.get('days') or 8} extra days of StratLab Basic" if how == "extra"
                 else "You've got a free month of StratLab Basic")
        return _compose(title, [first, when, "Nothing to pay and nothing to set up. Invite more friends from the Invite friends page."],
                        ("See your invites", "/invite"), transactional=tx, label="Invite reward", extra=[includes, rules])
    raise ValueError(f"Unknown email: {kind}")


def receipt_blocks(inv: dict) -> list:
    """The tax invoice's own details in the receipt, from the invoice as invoices.make stored it: the plan's taxable
    value, each GST line (CGST and SGST, or IGST) and the total; who billed it with their GSTIN, who it is billed to,
    and the place of supply. An invoice without those details (an older one) shows only what it has."""
    cur = inv.get("currency") or "INR"
    item, taxes, s, b = inv.get("item") or {}, inv.get("taxes") or [], inv.get("seller") or {}, inv.get("buyer") or {}
    out = []
    if isinstance(item.get("taxable"), (int, float)) and isinstance(inv.get("total"), (int, float)):
        rows = [[f"{item.get('description') or 'Subscription'}" + (f" (SAC {item['sac']})" if item.get("sac") else ""),
                 kit.money(item["taxable"], cur, 2)]]
        rows += [[t["name"], kit.money(t["amount"], cur, 2)] for t in taxes if isinstance(t.get("amount"), (int, float))]
        rows.append([f"Total paid ({'including GST' if any(t.get('rate') for t in taxes) else 'no GST charged' if not taxes else 'GST at 0%'})",
                     kit.money(inv["total"], cur, 2)])
        out.append(kit.table(["Item", "Amount"], rows, right=(1,), title=("Tax invoice " if s.get("gstin") else "Invoice ") + str(inv.get("number") or "")))
    parties = []
    if s.get("gstin"):
        parties.append(kit.Row("From", sub=s.get("legal_name") or "StratLab", lines=(f"GSTIN {s['gstin']}",)))
    elif s.get("legal_name"):
        parties.append(kit.Row("From", sub=s["legal_name"], lines=("Not registered under GST",)))
    else:                                       # seller details not set yet: just the name, nothing a customer would read as a placeholder
        parties.append(kit.Row("From", sub="StratLab"))
    if b.get("name") or b.get("gstin"):
        parties.append(kit.Row("Billed to", sub=b.get("name") or b.get("email") or "",
                               lines=tuple(x for x in (f"GSTIN {b['gstin']}" if b.get("gstin") else "",
                                                       f"Place of supply: {inv['place_of_supply']}" if inv.get("place_of_supply") else "") if x)))
    if parties:
        out.append(kit.card("Invoice details", parties, foot=inv.get("note") or None))
    return out


def basic_includes() -> str:
    """What a month of Basic gives, from plans.py's limits, for the invite reward email."""
    b = PLANS["basic"]
    return (f"Basic includes {b['backtests_per_month']} backtests and {b['ai_builds_per_month']} AI strategy builds a "
            f"month, every indicator, {b['live_limit']} paper trading sessions at a time with trade notifications, "
            f"{b['deepdives_per_month']} company deep dives and {b['decks_per_month']} decks a month, and the daily "
            "newsletters.")


def sample(kind: str, now: datetime | None = None) -> dict:
    """Made-up details for Admin's preview and test send."""
    now = _now(now)
    tomorrow = now.astimezone(IST).date() + timedelta(days=1)
    # the offer ends at the end of an Indian day, as plans.set_promo makes it (LIVE1C-037: "1:56 am" in one sample and "4:56 am" in the other)
    midnight = lambda d: datetime.combine(d + timedelta(days=1), datetime.min.time(), IST)           # noqa: E731
    if kind in ("trial_before", "promo_before"):
        return {"last_day": tomorrow, "end": midnight(tomorrow)}
    if kind in ("trial_end", "promo_end"):
        return {"last_day": now.astimezone(IST).date(), "end": midnight(now.astimezone(IST).date())}
    if kind == "receipt":
        return {"plan": "pro", "period": "month", "invoice": sample_invoice(now)}
    if kind == "plan_ended":
        return {"plan": "pro", "access": "free"}
    if kind == "invite_reward":
        return {"role": "referrer", "until": now + timedelta(days=30), "banked": 0}
    return {}


def sample_invoice(now: datetime) -> dict:
    """A made-up invoice shaped as invoices.make stores one, with its GST worked out by the invoices' own rules: the
    seller set in Admin → Invoices and a buyer in the same state. While that has no GSTIN the sample is the plain invoice a
    real payment gets today (no GST lines, "not registered under GST"), never one with made-up GST details (R9P-003)."""
    from . import invoices
    s = invoices.seller()
    buyer = {"name": "A. Reader", "email": "you@example.com", "address": "", "state": s.get("state") or "27", "country": "IN", "gstin": ""}
    total = float(PLANS["pro"]["price"])
    lines, supply, note = invoices.tax_lines(total, s, buyer)
    tax = round(sum(x["amount"] for x in lines), 2)
    # "SAMPLE", not "0001": a forwarded test can't be taken for the first real invoice (R93-007)
    return {"number": f"{s.get('prefix') or 'SL'}/{invoices.fy(now)}/SAMPLE", "date": now.astimezone(IST).date().isoformat(),
            "payment_id": "pay_sample", "seller": s, "buyer": buyer, "supply": supply, "note": note, "currency": "INR",
            "item": {"description": "StratLab Pro plan, monthly subscription", "sac": invoices.SAC, "taxable": round(total - tax, 2)},
            "taxes": lines, "total": total, "place_of_supply": invoices.STATES.get(buyer["state"], "India")}


def send(profile: dict, kind: str, key: str | None = None, ctx: dict | None = None, now: datetime | None = None) -> bool:
    """Send one email once. False when it went before, tips are off (for a tip), there's no address, or it failed."""
    key, now = key or kind, _now(now)
    uid, to = profile.get("id"), address(profile)
    transactional = EMAILS[kind][1]
    if not uid or not to or not alerts.email_ready():
        return False
    if not transactional and not tips_on(uid):
        return False
    if not _claim(uid, key, now, capped=not transactional):
        return False
    try:
        subject, html, text = build(kind, profile, ctx)
        html, text, headers = kit.finish(html, text, uid, None if transactional else CATEGORY)
        alerts.send_email(to, subject, text, html=html, headers=headers)
    except Exception as e:
        _release(uid, key, None if transactional else now)
        if transactional:
            _pend(uid, key, kind, ctx, now)
        print(f"lifecycle email {kind} failed:", str(e)[:160])
        return False
    if transactional:
        _unpend(uid, key)
    return True


def send_test(kind: str, profile: dict, to: str) -> str:
    """Admin's test: the email with made-up details, to `to`, marked as a test and not recorded. Returns the subject."""
    subject, html, text = build(kind, profile, sample(kind))
    html, text, headers = kit.finish(html, text, profile["id"], None if EMAILS[kind][1] else CATEGORY)
    subject = f"[Test] {subject}"
    alerts.send_email(to, subject, text, html=html, headers=headers)
    return subject


def preview(kind: str, profile: dict) -> dict:
    subject, html, text = build(kind, profile, sample(kind))
    html, text = kit.preview_links(html, text)           # the preview's unsubscribe link just opens Manage emails
    return {"kind": kind, "subject": subject, "html": html, "text": text, "transactional": EMAILS[kind][1]}


# ---------- account emails, from billing ----------
def receipt(profile: dict, invoice: dict, plan: str, period: str) -> bool:
    """One receipt per payment."""
    return send(profile, "receipt", f"receipt:{invoice.get('payment_id') or invoice.get('number')}",
                {"invoice": invoice, "plan": plan, "period": period})


def plan_ended(profile: dict, sub_id: str, plan: str | None) -> bool:
    """One note per subscription that stopped."""
    try:
        profile = db.get_profile(profile["id"])        # as it is now, after the subscription ended (the caller's copy is from before)
    except Exception as e:
        print("plan ended: profile not re-read,", str(e)[:120])
        # the caller's copy is from before the end (still on the paid plan): word the email as the account is now, on
        # Free with no subscription (the launch offer and free Basic time are still read as usual by access_plan)
        profile = {**profile, "plan": "free", "plan_status": "cancelled", "razorpay_subscription_id": None,
                   "cancel_at_period_end": False}
    return send(profile, "plan_ended", f"plan_ended:{sub_id}", {"plan": plan if plan in PLANS else "pro"})


# ---------- what's due ----------
_seen_today: dict[str, str] = {}


def is_new(profile: dict, now: datetime) -> bool:
    try:
        return now - _dt(profile["created_at"]) < WELCOME_WINDOW
    except (KeyError, TypeError, ValueError):
        return False


def seen(profile: dict, now: datetime | None = None) -> bool:
    """Called on each visit: remembers the day (once a day per user) and welcomes a brand-new account. True when it
    did anything."""
    now = _now(now)
    uid, today = profile.get("id"), now.astimezone(IST).date().isoformat()
    if not uid or _seen_today.get(uid) == today:
        return False
    if len(_seen_today) > 50000:
        _seen_today.clear()
    _seen_today[uid] = today
    db.set_setting(SEEN + uid, today)
    if is_new(profile, now) and alerts.email_ready() and "welcome" not in sent(uid):
        later(send, profile, "welcome", None, None, now)
    return True


def ran_backtest(uid: str) -> bool:
    return db.count_usage(uid, "backtest", EVER) > 0


def _recent_tip(record: dict, now: datetime) -> bool:
    """A tips email went in the last GAP."""
    for key, at in record.items():
        if EMAILS.get(key.split(":")[0], ("", True))[1]:
            continue
        try:
            if now - _dt(at) < GAP:
                return True
        except (TypeError, ValueError):
            continue
    return False


def due(profile: dict, now: datetime, record: dict, seen_day: str | None, promo_end: datetime | None,
        backtested=None) -> list[tuple[str, str, dict]]:
    """(kind, key, details) of every tips email due for this user now, most urgent first. `promo_end` is when a
    running launch offer ends; `backtested` answers whether they've run a backtest (asked only when it matters)."""
    if _recent_tip(record, now):
        return []
    today = now.astimezone(IST).date()
    out: dict[str, tuple[str, str, dict]] = {}
    free = effective_plan(profile) == "free" and not free_basic_until(profile, now)   # free Basic from invites counts
    started = profile.get("live_trial_started_at")
    if started and free:
        try:
            ends = trial_end(_dt(started), PLANS["free"]["live_trial_days"])
        except (TypeError, ValueError):
            ends = None
        # a launch offer that outlasts the trial makes it moot: everyone has Pro until then
        if ends and now < ends and not (promo_end and promo_end >= ends):
            last = _last_day(ends)
            if today == last:
                out["trial_end"] = ("trial_end", "trial_end", {"last_day": last})
            elif today == last - timedelta(days=1):
                out["trial_before"] = ("trial_before", "trial_before", {"last_day": last})
    if promo_end and now < promo_end and free:
        last = _last_day(promo_end)
        for kind, day in (("promo_end", last), ("promo_before", last - timedelta(days=1))):
            if today == day:                       # one per offer: a later offer can remind again
                out[kind] = (kind, f"{kind}:{last.isoformat()}", {"last_day": last, "end": promo_end})
    try:
        age = now - _dt(profile["created_at"])
    except (KeyError, TypeError, ValueError):
        age = None
    if age is not None and age < WELCOME_WINDOW:
        out["welcome"] = ("welcome", "welcome", {})
    if age is not None and DAY2_WINDOW[0] <= age < DAY2_WINDOW[1] and "day2" not in record:
        if backtested is None or not backtested():
            out["day2"] = ("day2", "day2", {})
    if seen_day:
        try:
            quiet = (today - date.fromisoformat(seen_day)).days
        except (TypeError, ValueError):
            quiet = 0
        if INACTIVE_DAYS <= quiet < INACTIVE_UNTIL:
            out["inactive"] = ("inactive", "inactive", {})
    return [out[k] for k in ORDER if k in out and out[k][1] not in record and not _capped(record, out[k][1])]


def sweep(now: datetime | None = None) -> int:
    """Send every tips email that is due, at most one per user. Returns how many went."""
    now = _now(now)
    if not alerts.email_ready():
        return 0
    records = {k[len(SENT):]: db.json_value(v, {}) for k, v in db.all_settings_with_prefix(SENT)}
    off = {k[len(PREFS):] for k, v in db.all_settings_with_prefix(PREFS) if db.json_value(v, {}).get("tips") is False}
    seen_days = {k[len(SEEN):]: v for k, v in db.all_settings_with_prefix(SEEN)}
    end = promo_until()
    end = end if end and now < end else None
    count = 0
    for p in db.all_profiles():
        uid = p.get("id")
        if not uid or uid in off or not address(p):
            continue
        for kind, key, ctx in due(p, now, records.get(uid, {}), seen_days.get(uid), end, lambda: ran_backtest(uid)):
            if send(p, kind, key, ctx, now):
                count += 1
                break
    return count + retry_pending(now)


def retry_pending(now: datetime) -> int:
    """Send again the account emails (receipts, plan changes, invite rewards) that failed, up to RETRIES times
    within RETRY_WINDOW. Returns how many went."""
    count, profiles = 0, None
    for k, v in db.all_settings_with_prefix(PENDING):
        uid = k[len(PENDING):]
        for key, p in db.json_value(v, {}).items():
            try:
                give_up = p["tries"] >= RETRIES or now - _dt(p["first"]) > RETRY_WINDOW
            except (KeyError, TypeError, ValueError):
                give_up = True
            if give_up or key in sent(uid):           # out of tries, or it went another way
                _unpend(uid, key)
                continue
            ctx = dict(p.get("ctx") or {})
            if isinstance(ctx.get("until"), str):
                ctx["until"] = _dt(ctx["until"])
            profiles = profiles if profiles is not None else {x.get("id"): x for x in db.all_profiles()}
            if uid in profiles and send(profiles[uid], p["kind"], key, ctx, now):
                count += 1
    return count


# ---------- the schedule ----------
class Job:
    """Checks every five minutes; sweeps once an hour in India's daytime. The hour is marked in the database before
    sweeping, and each email is recorded per user, so a restart never sends twice."""

    def __init__(self):
        self.last: str | None = None
        self.status = {"last_run": None, "sent": 0, "last_error": None}

    def start(self):
        threading.Thread(target=self._loop, daemon=True, name="lifecycle-emails").start()

    def _loop(self):
        while True:
            try:
                if leader.leading():      # another container leads: it runs this pass
                    self.tick(datetime.now(timezone.utc))
            except Exception as e:
                self.status["last_error"] = str(e)[:200]
                print("lifecycle emails:", e)
            time.sleep(300)

    def due(self, now: datetime) -> str | None:
        """The India hour to sweep for, when it's daytime and that hour hasn't been swept."""
        local = now.astimezone(IST)
        if not HOURS[0] <= local.hour < HOURS[1]:
            return None
        slot = local.strftime("%Y-%m-%dT%H")
        if self.last == slot:
            return None
        if db.get_setting(MARK) == slot:              # swept this hour before a restart
            self.last = slot
            return None
        return slot

    def tick(self, now: datetime) -> int:
        slot = self.due(now)
        if not slot:
            return 0
        before, was = self.last, db.get_setting(MARK)
        self.last = slot
        db.set_setting(MARK, slot)
        try:
            sent_now = sweep(now)
        except Exception:
            self.last = before                       # the hour isn't used up: the next pass sweeps again
            if was is None:
                db.delete_setting(MARK)
            else:
                db.set_setting(MARK, was)
            raise
        self.status.update(last_run=now.isoformat(), sent=sent_now, last_error=None)
        return sent_now
