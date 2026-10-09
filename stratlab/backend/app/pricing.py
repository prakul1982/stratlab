"""Prices by currency for visitors outside India. Rupee prices live in plans.py; every other currency follows them
automatically: the rupee price at today's exchange rate, rounded to a tidy amount (rates are read once a day). US
dollars, euros and pounds have their own built-in prices instead ($8 and $20 a month). The admin can change any price
in Admin → Prices, and clear it to go back to the default.

Charging: a currency is charged in that currency when its Razorpay plan IDs are set in Admin (plans are created in
the Razorpay dashboard, one per currency, plan and period). Until then visitors see the local price for reference
and pay the rupee price, which their card converts."""
import json

from . import db
from .plans import PLANS

KEY = "prices"
RATES = "fx-rates"             # app_settings: {"at": ISO, "rates": {"USD": 88.2, ...}} rupees per unit, read daily

# code: (symbol, name, monthly Basic, monthly Pro); yearly is ten months (two free), as in rupees. These amounts are
# used until the first exchange rate is read; after that the rupee price at today's rate, except for FIXED below.
CURRENCIES = {
    "INR": ("₹", "Indian rupee", None, None),
    "USD": ("$", "US dollar", 8, 20),
    "EUR": ("€", "Euro", 8, 19),
    "GBP": ("£", "British pound", 7, 16),
    "AUD": ("A$", "Australian dollar", 9, 27),
    "CAD": ("C$", "Canadian dollar", 8, 24),
    "SGD": ("S$", "Singapore dollar", 7, 22),
    "AED": ("AED ", "UAE dirham", 22, 64),
    "SAR": ("SAR ", "Saudi riyal", 22, 64),
    "CHF": ("CHF ", "Swiss franc", 5, 14),
    "JPY": ("¥", "Japanese yen", 900, 2650),
    "HKD": ("HK$", "Hong Kong dollar", 47, 135),
    "NZD": ("NZ$", "New Zealand dollar", 10, 29),
    "SEK": ("SEK ", "Swedish krona", 62, 185),
    "NOK": ("NOK ", "Norwegian krone", 64, 190),
    "DKK": ("DKK ", "Danish krone", 42, 125),
    "ZAR": ("R", "South African rand", 110, 325),
    "MYR": ("RM", "Malaysian ringgit", 27, 79),
    "QAR": ("QAR ", "Qatari riyal", 22, 64),
}
# priced on their own, like comparable apps abroad, instead of following the rupee price (the admin can still change them)
FIXED = {"USD", "EUR", "GBP"}

# countries that use each currency (ISO 3166 codes); anywhere else outside India sees US dollars
COUNTRIES = {
    "IN": "INR", "US": "USD", "GB": "GBP", "AU": "AUD", "CA": "CAD", "SG": "SGD", "AE": "AED", "SA": "SAR", "CH": "CHF",
    "JP": "JPY", "HK": "HKD", "NZ": "NZD", "SE": "SEK", "NO": "NOK", "DK": "DKK", "ZA": "ZAR", "MY": "MYR", "QA": "QAR",
    **{c: "EUR" for c in ("AT", "BE", "CY", "DE", "EE", "ES", "FI", "FR", "GR", "HR", "IE", "IT", "LT", "LU", "LV", "MT",
                          "NL", "PT", "SI", "SK")},
}

FIELDS = ("basic", "pro", "basic_year", "pro_year")
PLAN_FIELDS = ("plan_basic", "plan_pro", "plan_basic_year", "plan_pro_year")


def nice(v: float) -> int:
    """A tidy price: whole units under 100, then steps of 5, 50 and 500 (yen and krona run into the thousands)."""
    step = 1 if v < 100 else 5 if v < 1000 else 50 if v < 10000 else 500
    return max(step, int(round(v / step) * step))


_rates_cache: list = [0.0, {}]


def rates() -> dict:
    """{code: rupees per unit} from the last daily read, cached for ten minutes; {} before the first read."""
    import time
    if time.time() - _rates_cache[0] < 600:
        return _rates_cache[1]
    try:
        got = (json.loads(db.get_setting(RATES) or "{}").get("rates")) or {}
    except Exception:
        got = _rates_cache[1]
    _rates_cache[:] = [time.time(), got]
    return got


# units of a currency per US dollar, fixed by its central bank: used only when no market rate can be read
PEGS = {"SAR": 3.75, "QAR": 3.64, "AED": 3.6725, "HKD": 7.80}


def cross_rate(code: str, quote) -> float:
    """Rupees per unit of `code`. `quote(pair)` gives a market price for a pair such as "EURINR=X" (rupees per euro),
    "USDINR=X" or "SAR=X" (riyals per dollar), or None. The rupee pair first; else rupees per dollar over the
    currency's units per dollar; else, for a pegged currency, rupees per dollar over the peg (R7O-008)."""
    def read(pair):
        try:
            v = quote(pair)
            return float(v) if v and float(v) > 0 else None
        except Exception:
            return None
    direct = read(f"{code}INR=X")
    if direct:
        return direct
    usd_inr = read("USDINR=X") or read("INR=X")
    if not usd_inr:
        raise ValueError("no rupee rate for the dollar")
    if code == "USD":
        return usd_inr
    per_usd = read(f"{code}=X") or read(f"USD{code}=X") or PEGS.get(code)
    if not per_usd:
        raise ValueError("no rate")
    return usd_inr / per_usd


def refresh_rates(fetch) -> dict:
    """Read every currency's rate (rupees per unit) with `fetch(code)`; keep the last good one for any that fails."""
    from datetime import datetime, timezone
    try:
        old = json.loads(db.get_setting(RATES) or "{}")
    except Exception:
        old = {}
    out, errors = dict(old.get("rates") or {}), []
    for code in CURRENCIES:
        if code == "INR":
            continue
        try:
            r = float(fetch(code))
            if r > 0:
                out[code] = r
        except Exception as e:
            errors.append(f"{code}: {str(e)[:60]}")
    state = {"at": datetime.now(timezone.utc).isoformat(), "rates": out, "errors": errors}
    db.set_setting(RATES, json.dumps(state))
    _rates_cache[0] = 0.0
    return state


def defaults() -> dict:
    """Default prices: the rupee price at today's rate, tidied; the built-in amounts for FIXED currencies, and for the
    rest until a rate has been read."""
    out, fx = {}, dict(rates())
    for code, per_usd in PEGS.items():          # a pegged currency the daily read missed: the dollar's rate over the peg
        if not fx.get(code) and fx.get("USD"):
            fx[code] = fx["USD"] / per_usd
    inr = {f: PLANS[f.split("_")[0]]["price" + ("_year" if f.endswith("_year") else "")] for f in FIELDS}
    for code, (_, _, basic, pro) in CURRENCIES.items():
        if code == "INR":
            row = dict(inr)
        elif fx.get(code) and code not in FIXED:
            row = {f: nice(inr[f] / fx[code]) for f in ("basic", "pro")}
            row.update(basic_year=row["basic"] * 10, pro_year=row["pro"] * 10)
        else:
            row = {"basic": basic, "pro": pro, "basic_year": basic * 10, "pro_year": pro * 10}
        out[code] = {**row, **{f: None for f in PLAN_FIELDS}, "rate": fx.get(code)}
    return out


# The landing and plans pages ask for prices on every visit: the admin's changes are kept in memory for a minute
# (a change made here is seen at once).
_saved_cache: list = [0.0, None]
SAVED_TTL = 60


def forget():
    _saved_cache[:] = [0.0, None]


def _saved() -> dict:
    import copy
    import time
    if _saved_cache[1] is not None and time.monotonic() - _saved_cache[0] < SAVED_TTL:
        return copy.deepcopy(_saved_cache[1])
    try:
        raw = db.get_setting(KEY)
        got = json.loads(raw) if raw else {}
    except Exception:
        return {}
    _saved_cache[:] = [time.monotonic(), got]
    return copy.deepcopy(got)


def table() -> dict:
    """{code: {symbol, name, basic, pro, basic_year, pro_year, charged_in}} with the admin's changes applied.
    `charged_in` is the currency the card is actually charged in for that row (its own, or rupees)."""
    saved, out = _saved(), {}
    for code, row in defaults().items():
        mine = saved.get(code) or {}
        row = {**row, **{k: v for k, v in mine.items() if k in FIELDS + PLAN_FIELDS},
               "auto": not any(f in mine for f in FIELDS)}
        if code == "INR":                                  # rupee prices are plans.py's, charged on the main plans
            row.update({f: PLANS[f.split("_")[0]]["price" + ("_year" if f.endswith("_year") else "")] for f in FIELDS})
        symbol, name = CURRENCIES[code][:2]
        own = code == "INR" or (row.get("plan_basic") and row.get("plan_pro"))
        # `converted`: the amount is the rupee charge (GST included) at today's rate, rounded, so Plans can say so; a
        # fixed price (dollars, euros, pounds) or one the admin typed in isn't (R7O-008)
        row["converted"] = bool(code != "INR" and code not in FIXED and row["auto"] and row.get("rate"))
        # `no_rate`: an automatic price that should follow the rupee price but has no exchange rate to follow, so the amount
        # is only the built-in default (R7M-003: "SAR 22" for a ₹699 charge that is about SAR 27). Visitors aren't shown
        # it (public()); Admin flags it. A price the admin typed in, and dollars, euros and pounds, never need a rate.
        row["no_rate"] = bool(code != "INR" and code not in FIXED and row["auto"] and not row.get("rate"))
        out[code] = {**row, "symbol": symbol, "name": name, "charged_in": code if own else "INR",
                     "yearly_charged_in": code if code == "INR" or (row.get("plan_basic_year") and row.get("plan_pro_year")) else "INR"}
    return out


def public() -> dict:
    """What the landing page and Plans need: prices, symbols and which currency is charged. Plan IDs stay on the
    server. Each currency shows the admin price table's amount ($8 and $20 for dollars, the owner's choice, 7 Oct);
    `charged_in` says when a card is still charged the rupee price instead."""
    shown = {c: r for c, r in table().items() if not r.get("no_rate")}
    return {"currencies": {c: {**{k: v for k, v in r.items() if k not in PLAN_FIELDS + ("rate", "auto", "no_rate")}, **charge_about(c, r)}
                           for c, r in shown.items()},
            "countries": {k: c for k, c in COUNTRIES.items() if c in shown}}


def charge_about(code: str, row: dict) -> dict:
    """{"charge_about": {field: the rupee charge in this currency at today's rate}} for a currency with its own fixed price
    that is still charged in rupees, so Plans can say what the card is actually charged beside the price it shows
    (R8O-006: Basic €8 and £7, charged as ₹699, about €6.45 and £5.47); {} otherwise. Two decimals (none for yen)."""
    rate = row.get("rate")
    if code == "INR" or row.get("converted") or not rate or rate <= 0:
        return {}
    inr = {f: PLANS[f.split("_")[0]]["price" + ("_year" if f.endswith("_year") else "")] for f in FIELDS}
    out = {}
    for f in FIELDS:
        charged = row.get("yearly_charged_in" if f.endswith("_year") else "charged_in")
        if charged == "INR":
            v = inr[f] / rate
            out[f] = round(v) if code == "JPY" else round(v, 2)
    return {"charge_about": out} if out else {}


def save(changes: dict) -> dict:
    """Store the admin's prices and Razorpay plan IDs. Unknown currencies and fields are ignored; a blank plan ID
    clears it (back to charging in rupees)."""
    saved = _saved()
    for code, row in (changes or {}).items():
        if code not in CURRENCIES or code == "INR" or not isinstance(row, dict):
            continue
        cur = saved.setdefault(code, {})
        for f in FIELDS:
            if f in row:
                v = row[f]
                if v is None or v == "":
                    cur.pop(f, None)
                elif isinstance(v, (int, float)) and 0 < v < 10_000_000:
                    cur[f] = round(float(v), 2) if v != int(v) else int(v)
                else:
                    raise ValueError(f"{code} {f.replace('_', ' ')}: a price must be a positive number.")
        for f in PLAN_FIELDS:
            if f in row:
                v = str(row[f] or "").strip()
                if v and not (v.startswith("plan_") and len(v) <= 40 and v.replace("_", "").isalnum()):
                    raise ValueError(f"{code}: \"{v[:40]}\" doesn't look like a Razorpay plan ID (plan_…).")
                if v:
                    cur[f] = v
                else:
                    cur.pop(f, None)
    forget()
    try:
        db.set_setting(KEY, json.dumps(saved))
    finally:
        forget()
    return table()


def plan_id(currency: str, plan: str, period: str) -> str | None:
    """The Razorpay plan to subscribe to for this currency, or None to use the rupee plan."""
    if currency in (None, "", "INR"):
        return None
    row = table().get(currency) or {}
    return row.get(f"plan_{plan}{'_year' if period == 'year' else ''}") or None


def all_plan_ids() -> dict[str, tuple[str, str, str]]:
    """{plan id: (currency, plan, period)} for every currency's plans, so a renewal can be matched to its plan."""
    out = {}
    for code, row in table().items():
        for plan in ("basic", "pro"):
            for period, suffix in (("month", ""), ("year", "_year")):
                pid = row.get(f"plan_{plan}{suffix}")
                if pid:
                    out[pid] = (code, plan, period)
    return out
