"""Prices by currency for visitors outside India. Rupee prices live in plans.py; every other currency starts at a
rounded conversion of them and can be changed in Admin → Prices without a deploy.

Charging: a currency is charged in that currency when its Razorpay plan IDs are set in Admin (plans are created in
the Razorpay dashboard, one per currency, plan and period). Until then visitors see the local price for reference
and pay the rupee price, which their card converts."""
import json

from . import db
from .plans import PLANS

KEY = "prices"

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


def defaults() -> dict:
    out = {}
    for code, (_, _, basic, pro) in CURRENCIES.items():
        if code == "INR":
            basic, pro = PLANS["basic"]["price"], PLANS["pro"]["price"]
        out[code] = {"basic": basic, "pro": pro, "basic_year": basic * 10, "pro_year": pro * 10,
                     **{f: None for f in PLAN_FIELDS}}
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
        row = {**row, **{k: v for k, v in (saved.get(code) or {}).items() if k in FIELDS + PLAN_FIELDS}}
        if code == "INR":                                  # rupee prices are plans.py's, charged on the main plans
            row.update({f: PLANS[f.split("_")[0]]["price" + ("_year" if f.endswith("_year") else "")] for f in FIELDS})
        symbol, name = CURRENCIES[code][:2]
        own = code == "INR" or (row.get("plan_basic") and row.get("plan_pro"))
        out[code] = {**row, "symbol": symbol, "name": name, "charged_in": code if own else "INR",
                     "yearly_charged_in": code if code == "INR" or (row.get("plan_basic_year") and row.get("plan_pro_year")) else "INR"}
    return out


def public() -> dict:
    """What the Plans page needs: prices, symbols and which currency is charged. Plan IDs stay on the server."""
    return {"currencies": {c: {k: v for k, v in r.items() if k not in PLAN_FIELDS} for c, r in table().items()},
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
