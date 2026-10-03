"""Prices by currency for visitors outside India. Rupee prices live in plans.py; every other currency follows them
automatically: the rupee price at today's exchange rate, rounded to a tidy amount (rates are read once a day). The
admin can fix any price in Admin → Prices instead, and clear it to go back to automatic.

Charging: a currency is charged in that currency when its Razorpay plan IDs are set in Admin (plans are created in
the Razorpay dashboard, one per currency, plan and period). Until then visitors see the local price for reference
and pay the rupee price, which their card converts."""
import json

from . import db
from .plans import PLANS

KEY = "prices"
RATES = "fx-rates"             # app_settings: {"at": ISO, "rates": {"USD": 88.2, ...}} rupees per unit, read daily

# code: (symbol, name, monthly Basic, monthly Pro); yearly is ten months (two free), as in rupees
CURRENCIES = {
    "INR": ("₹", "Indian rupee", None, None),
    "USD": ("$", "US dollar", 12, 35),
    "EUR": ("€", "Euro", 11, 32),
    "GBP": ("£", "British pound", 9, 27),
    "AUD": ("A$", "Australian dollar", 18, 54),
    "CAD": ("C$", "Canadian dollar", 16, 48),
    "SGD": ("S$", "Singapore dollar", 15, 45),
    "AED": ("AED ", "UAE dirham", 45, 129),
    "SAR": ("SAR ", "Saudi riyal", 45, 129),
    "CHF": ("CHF ", "Swiss franc", 10, 29),
    "JPY": ("¥", "Japanese yen", 1800, 5300),
    "HKD": ("HK$", "Hong Kong dollar", 95, 275),
    "NZD": ("NZ$", "New Zealand dollar", 20, 59),
    "SEK": ("SEK ", "Swedish krona", 125, 369),
    "NOK": ("NOK ", "Norwegian krone", 129, 379),
    "DKK": ("DKK ", "Danish krone", 85, 249),
    "ZAR": ("R", "South African rand", 219, 649),
    "MYR": ("RM", "Malaysian ringgit", 55, 159),
    "QAR": ("QAR ", "Qatari riyal", 45, 129),
}

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
    """Automatic prices: the rupee price at today's rate, tidied; the built-in amounts until a rate has been read."""
    out, fx = {}, rates()
    inr = {f: PLANS[f.split("_")[0]]["price" + ("_year" if f.endswith("_year") else "")] for f in FIELDS}
    for code, (_, _, basic, pro) in CURRENCIES.items():
        if code == "INR":
            row = dict(inr)
        elif fx.get(code):
            row = {f: nice(inr[f] / fx[code]) for f in ("basic", "pro")}
            row.update(basic_year=row["basic"] * 10, pro_year=row["pro"] * 10)
        else:
            row = {"basic": basic, "pro": pro, "basic_year": basic * 10, "pro_year": pro * 10}
        out[code] = {**row, **{f: None for f in PLAN_FIELDS}, "rate": fx.get(code)}
    return out


def _saved() -> dict:
    try:
        raw = db.get_setting(KEY)
        return json.loads(raw) if raw else {}
    except Exception:
        return {}


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
        out[code] = {**row, "symbol": symbol, "name": name, "charged_in": code if own else "INR",
                     "yearly_charged_in": code if code == "INR" or (row.get("plan_basic_year") and row.get("plan_pro_year")) else "INR"}
    return out


def public() -> dict:
    """What the Plans page needs: prices, symbols and which currency is charged. Plan IDs stay on the server."""
    return {"currencies": {c: {k: v for k, v in r.items() if k not in PLAN_FIELDS + ("rate", "auto")} for c, r in table().items()},
            "countries": COUNTRIES}


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
    db.set_setting(KEY, json.dumps(saved))
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
